"""IFC reader.

Reads IfcSpace quantities from a pinned fixture and returns Observations carrying full
provenance (model hash, GlobalId, property path, raw + SI value/unit): finished ceiling
height for R2, and net floor area + window relationships for R1. It deliberately reads
slab-to-slab `Height` into a SEPARATE proxy field so the mapping layer can refuse to
hard-judge R2 on it (per Cap 123F Reg 24 the requirement is finished floor-to-ceiling height).
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import ifcopenshell
from ifcopenshell.util import element as ifc_element
from ifcopenshell.util import unit as ifc_unit

from .models import Observation, Provenance, ReasonCode, SourceMode

# ArchiCAD/FZK export names the space quantity set "BaseQuantities"; the IFC standard
# name is "Qto_SpaceBaseQuantities". Accept either.
_SPACE_QSET_NAMES = ("Qto_SpaceBaseQuantities", "BaseQuantities")
_WINDOW_QSET_NAMES = ("Qto_WindowBaseQuantities", "BaseQuantities")


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class IFCModel:
    """Thin wrapper over an opened IFC file, pinned by its SHA-256."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self.model_sha256 = file_sha256(path)
        self._f = ifcopenshell.open(self.path)
        self.schema = self._f.schema
        self.length_scale_to_m = ifc_unit.calculate_unit_scale(self._f)
        self.length_unit_name = self._length_unit_name()

    def _length_unit_name(self) -> str:
        for u in self._f.by_type("IfcSIUnit"):
            if u.UnitType == "LENGTHUNIT":
                prefix = (u.Prefix or "").lower()
                return f"{prefix}{(u.Name or '').lower()}"
        return "unknown"

    @lru_cache(maxsize=None)
    def _space_by_guid(self, guid: str):
        for sp in self._f.by_type("IfcSpace"):
            if sp.GlobalId == guid:
                return sp
        return None

    def _space_qset(self, space) -> dict:
        psets = ifc_element.get_psets(space, qtos_only=False)
        for name in _SPACE_QSET_NAMES:
            if name in psets:
                return {"_set_name": name, **psets[name]}
        # fall back: any set that carries a plausible height quantity
        for name, props in psets.items():
            if "FinishCeilingHeight" in props or "Height" in props:
                return {"_set_name": name, **props}
        return {}

    def read_finished_height(self, guid: str) -> Observation | None:
        """Return an Observation for finished_ceiling_height_m, or None if the space
        or the quantity set is absent. Provenance encodes exactly where it came from."""
        space = self._space_by_guid(guid)
        if space is None:
            return None
        qset = self._space_qset(space)
        if not qset:
            return None

        set_name = qset["_set_name"]
        raw = qset.get("FinishCeilingHeight")
        if raw is None:
            # No finished height. Record slab Height (if any) as a proxy flag so the
            # mapping layer can raise DEFINITION_MISMATCH instead of silently using it.
            slab = qset.get("Height")
            flags = ["finished_ceiling_height_absent"]
            if slab is not None:
                flags.append("slab_to_slab_height_present_not_substitutable")
            prov = Provenance(
                source_mode=SourceMode.PINNED_IFC,
                raw_value=slab,
                raw_unit=self.length_unit_name,
                value_si=None,
                unit_si="m",
                model_sha256=self.model_sha256,
                ifc_schema=self.schema,
                element_global_id=guid,
                property_path=f"{set_name}.Height" if slab is not None else None,
                extraction_method="ifcopenshell.util.element.get_psets",
                data_quality_flags=flags,
            )
            return Observation(field_name="finished_ceiling_height_m", provenance=prov)

        value_si = float(raw) * self.length_scale_to_m
        prov = Provenance(
            source_mode=SourceMode.PINNED_IFC,
            raw_value=float(raw),
            raw_unit=self.length_unit_name,
            value_si=value_si,
            unit_si="m",
            model_sha256=self.model_sha256,
            ifc_schema=self.schema,
            element_global_id=guid,
            property_path=f"{set_name}.FinishCeilingHeight",
            extraction_method="ifcopenshell.util.element.get_psets",
            data_quality_flags=[],
        )
        return Observation(field_name="finished_ceiling_height_m", provenance=prov)

    def space_name(self, guid: str) -> str | None:
        space = self._space_by_guid(guid)
        if space is None:
            return None
        return space.LongName or space.Name

    def read_floor_area(self, guid: str) -> Observation | None:
        """Read NetFloorArea as a floor_area_m2 candidate. Flags that NetFloorArea is
        not necessarily identical to the Reg 30 'area of the floor of the room'."""
        space = self._space_by_guid(guid)
        if space is None:
            return None
        qset = self._space_qset(space)
        raw = qset.get("NetFloorArea") if qset else None
        if raw is None:
            return None
        # area unit scale = length scale squared for SI-declared area units
        value_si = float(raw) * (self.length_scale_to_m ** 2)
        prov = Provenance(
            source_mode=SourceMode.PINNED_IFC,
            raw_value=float(raw),
            raw_unit="square_metre",
            value_si=value_si,
            unit_si="m2",
            model_sha256=self.model_sha256,
            ifc_schema=self.schema,
            element_global_id=guid,
            property_path=f"{qset['_set_name']}.NetFloorArea",
            extraction_method="ifcopenshell.util.element.get_psets",
            data_quality_flags=["net_floor_area_vs_reg30_definition_requires_review"],
        )
        return Observation(field_name="floor_area_m2", provenance=prov)

    @lru_cache(maxsize=None)
    def _windows_bounding_space(self, guid: str) -> tuple:
        """Windows physically bounding this space, via IfcRelSpaceBoundary. Tuple so it
        is hashable/cacheable."""
        windows = []
        for b in self._f.by_type("IfcRelSpaceBoundary"):
            sp = getattr(b, "RelatingSpace", None)
            el_ = getattr(b, "RelatedBuildingElement", None)
            if sp is not None and sp.GlobalId == guid and el_ is not None and el_.is_a("IfcWindow"):
                windows.append(el_)
        return tuple(windows)

    def _window_area_and_fraction(self, window) -> tuple[float | None, float | None]:
        psets = ifc_element.get_psets(window, qtos_only=False)
        area = None
        for name in _WINDOW_QSET_NAMES:
            if name in psets and "Area" in psets[name]:
                area = psets[name]["Area"]
                break
        fraction = psets.get("Pset_WindowCommon", {}).get("GlazingAreaFraction")
        return area, fraction

    def read_space_glazing(
        self, guid: str
    ) -> tuple[Observation | None, ReasonCode | None, str]:
        """Attempt to derive total glass area for a space.

        glass_area = sum(Window.Area * GlazingAreaFraction) over windows bounding the
        space. Returns (observation, reason_code, detail). The observation is only
        produced when every bounding window yields a usable glass area; otherwise the
        reason_code explains why the check must go to review.
        """
        space = self._space_by_guid(guid)
        if space is None:
            return None, ReasonCode.MISSING_DATA, "space not found in model"

        windows = self._windows_bounding_space(guid)
        if not windows:
            return (
                None,
                ReasonCode.RELATIONSHIP_UNVERIFIED,
                "no window could be related to this space via IfcRelSpaceBoundary",
            )

        scale_area = self.length_scale_to_m ** 2
        total_glass = 0.0
        window_paths = []
        for w in windows:
            area, fraction = self._window_area_and_fraction(w)
            if area is None:
                return (
                    None,
                    ReasonCode.MISSING_DATA,
                    f"window {w.GlobalId} has no Area quantity",
                )
            if fraction is None:
                # Window Area is outer opening area, NOT glass area. Without the glazing
                # fraction the glass area is not derivable -> review (do not guess).
                return (
                    None,
                    ReasonCode.MISSING_DATA,
                    f"window {w.GlobalId} has Area but no GlazingAreaFraction; "
                    "glass area not derivable",
                )
            total_glass += float(area) * float(fraction) * scale_area
            window_paths.append(w.GlobalId)

        prov = Provenance(
            source_mode=SourceMode.PINNED_IFC,
            value_si=total_glass,
            unit_si="m2",
            model_sha256=self.model_sha256,
            ifc_schema=self.schema,
            element_global_id=guid,
            property_path="sum(window.Area * Pset_WindowCommon.GlazingAreaFraction)",
            extraction_method="ifcopenshell IfcRelSpaceBoundary + get_psets",
            data_quality_flags=[f"windows:{','.join(window_paths)}"],
        )
        return Observation(field_name="glazing_area_m2", provenance=prov), None, "ok"
