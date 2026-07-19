"""Map a case + IFC model into a typed CheckInput, dispatched per rule.

A "case" is one entry from controlled_cases.json. It is either:
  - pinned_ifc:       element_id is an IfcSpace GlobalId; values are read from the model.
  - constructed_case: values (or an explicit review trigger) are supplied by hand.

legal_space_use is always a constructed annotation (the IFC does not legally classify
rooms), so it carries source_mode = constructed_case regardless of the element mode.
"""

from __future__ import annotations

from typing import Any

from .ifc_reader import IFCModel
from .models import (
    CheckInput,
    Observation,
    Provenance,
    ReasonCode,
    RuleObject,
    SourceMode,
)
from .units import SI_UNIT, expected_dimension, to_si


def build_check_input(case: dict[str, Any], model: IFCModel | None, rule: RuleObject) -> CheckInput:
    element_id = case["element_id"]
    mode = SourceMode(case.get("element_source_mode", "constructed_case"))
    legal_use = case.get("legal_space_use")

    ci = CheckInput(
        element_id=element_id,
        element_source_mode=mode,
        legal_space_use=legal_use,
        legal_space_use_source_mode=(
            SourceMode.CONSTRUCTED_CASE if legal_use is not None else None
        ),
    )
    if mode == SourceMode.PINNED_IFC and model is not None:
        ci.element_name = model.space_name(element_id)
    else:
        ci.element_name = case.get("element_name")

    if rule.rule_id == "R2_finished_height":
        _map_r2(case, model, ci)
    elif rule.rule_id == "R1_glazing_ratio":
        _map_r1(case, model, ci)
    return ci


# --------------------------------------------------------------------------- R2

def _map_r2(case: dict[str, Any], model: IFCModel | None, ci: CheckInput) -> None:
    if ci.element_source_mode == SourceMode.PINNED_IFC:
        if model is None:
            _miss(ci, "finished_ceiling_height_m", "no IFC model loaded")
            return
        obs = model.read_finished_height(ci.element_id)
        if obs is None:
            _miss(ci, "finished_ceiling_height_m", "space or quantity set absent")
            return
        if obs.provenance.value_si is None:
            ci.observations["finished_ceiling_height_m"] = obs
            ci.data_quality_flags.extend(obs.provenance.data_quality_flags)
            if "slab_to_slab_height_present_not_substitutable" in obs.provenance.data_quality_flags:
                ci.reason_codes.append(ReasonCode.DEFINITION_MISMATCH)
                ci.review_details.append(
                    "DEFINITION_MISMATCH: only slab-to-slab Height present; not substitutable"
                )
            else:
                _miss(ci, "finished_ceiling_height_m", "FinishCeilingHeight absent")
            return
        ci.observations["finished_ceiling_height_m"] = obs
        return

    # constructed
    raw_value, raw_unit = _measurement(case, "finished_ceiling_height_m")
    slab = case.get("slab_height_m")
    if raw_value is not None:
        _add_constructed(
            ci, "finished_ceiling_height_m", raw_value, raw_unit,
            "constructed_case.finished_ceiling_height_m",
        )
    elif slab is not None:
        # slab-to-slab height is a valid length, but the WRONG definition for R2; keep it
        # visible (rejected observation) instead of substituting it.
        ci.observations["finished_ceiling_height_m"] = _seen_but_unusable_obs(
            "finished_ceiling_height_m", float(slab), "m", "constructed_case.slab_height_m",
            flags=["slab_to_slab_height_present_not_substitutable"],
        )
        ci.data_quality_flags.append("slab_to_slab_height_present_not_substitutable")
        ci.reason_codes.append(ReasonCode.DEFINITION_MISMATCH)
        ci.review_details.append(
            "DEFINITION_MISMATCH: only slab-to-slab Height present; not substitutable"
        )
    else:
        _miss(ci, "finished_ceiling_height_m", "no height data")


# --------------------------------------------------------------------------- R1

def _map_r1(case: dict[str, Any], model: IFCModel | None, ci: CheckInput) -> None:
    """R1 glazing ratio.

    On the pinned fixture the glazing fraction is absent, so glass area is not derivable
    and real spaces route to review. Constructed cases supply floor and glass area
    directly (optionally in non-SI units) to exercise the ratio pass/fail path.
    """
    if ci.element_source_mode == SourceMode.PINNED_IFC:
        if model is None:
            _miss(ci, "floor_area_m2", "no IFC model loaded")
            _miss(ci, "glazing_area_m2", "no IFC model loaded")
            return
        floor = model.read_floor_area(ci.element_id)
        if floor is not None:
            ci.observations["floor_area_m2"] = floor
            ci.data_quality_flags.extend(floor.provenance.data_quality_flags)
        else:
            _miss(ci, "floor_area_m2", "NetFloorArea absent")

        glazing, code, detail = model.read_space_glazing(ci.element_id)
        if glazing is not None:
            ci.observations["glazing_area_m2"] = glazing
        else:
            ci.reason_codes.append(code)
            ci.review_details.append(f"{code.value}: {detail}")
        return

    # constructed
    floor_v, floor_u = _measurement(case, "floor_area_m2")
    if floor_v is not None:
        _add_constructed(ci, "floor_area_m2", floor_v, floor_u, "constructed_case.floor_area_m2")

    glaz_v, glaz_u = _measurement(case, "glazing_area_m2")
    trigger = case.get("glazing_review_reason")
    if glaz_v is not None:
        _add_constructed(ci, "glazing_area_m2", glaz_v, glaz_u, "constructed_case.glazing_area_m2")
    elif trigger is not None:
        code = ReasonCode(trigger)
        ci.reason_codes.append(code)
        ci.review_details.append(f"{code.value}: constructed review case")
    else:
        _miss(ci, "glazing_area_m2", "no glazing data")


# --------------------------------------------------------------------------- helpers

def _measurement(case: dict[str, Any], field: str) -> tuple[float | None, str | None]:
    """Resolve a constructed value + unit for `field`.

    Prefer an explicit `{"value": .., "unit": ".."}` under `measurements` (which may carry a
    non-SI or faulty unit); otherwise fall back to a plain top-level number, interpreted as
    already being in the canonical SI unit for the field's dimension.
    """
    meas = case.get("measurements") or {}
    if field in meas:
        m = meas[field] or {}
        v = m.get("value")
        return (None if v is None else float(v)), m.get("unit")
    v = case.get(field)
    if v is not None:
        return float(v), SI_UNIT[expected_dimension(field)]
    return None, None


def _add_constructed(
    ci: CheckInput, field: str, raw_value: float, raw_unit: str | None, path: str
) -> None:
    """Build a constructed observation, converting the unit to SI. A unit fault is recorded
    as UNIT_MISMATCH (value_si stays None -> unusable -> review), never silently coerced."""
    value_si, unit_si, code, detail = to_si(raw_value, raw_unit, expected_dimension(field))
    flags = [f"unit_mismatch:{detail}"] if code is not None else []
    obs = Observation(
        field_name=field,
        provenance=Provenance(
            source_mode=SourceMode.CONSTRUCTED_CASE,
            raw_value=raw_value,
            raw_unit=raw_unit,
            value_si=value_si,
            unit_si=unit_si,
            property_path=path,
            extraction_method="hand_authored",
            data_quality_flags=flags,
        ),
    )
    ci.observations[field] = obs
    if code is not None:
        ci.reason_codes.append(code)
        ci.review_details.append(f"{code.value}: {field} — {detail}")


def _seen_but_unusable_obs(
    field: str, raw_value: float, raw_unit: str, path: str, *, flags: list[str]
) -> Observation:
    """A value that was read but is deliberately NOT usable for judgment (value_si = None),
    e.g. a slab-to-slab height offered where a finished height is required."""
    return Observation(
        field_name=field,
        provenance=Provenance(
            source_mode=SourceMode.CONSTRUCTED_CASE,
            raw_value=raw_value,
            raw_unit=raw_unit,
            value_si=None,
            unit_si=SI_UNIT[expected_dimension(field)],
            property_path=path,
            extraction_method="hand_authored",
            data_quality_flags=flags,
        ),
    )


def _miss(ci: CheckInput, field: str, detail: str) -> None:
    ci.missing_fields.append(field)
    ci.reason_codes.append(ReasonCode.MISSING_DATA)
    ci.review_details.append(f"MISSING_DATA: {field} — {detail}")
