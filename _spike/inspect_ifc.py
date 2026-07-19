"""Gate 0 IFC fixture spike — one-off inspection probe (NOT part of the main pipeline).

Prints, for a given IFC file, exactly what the R1/R2/R3 rules need:
  - project units (length/area)
  - per-IfcSpace Qto_SpaceBaseQuantities (NetFloorArea, FinishCeilingHeight, Height, ...)
  - windows, their Qto/Pset quantities (Area, GlazingAreaFraction)
  - whether windows can be related to a space via IfcRelSpaceBoundary
Records what actually exists vs. what is missing. No inference from the spec.
"""

import sys
import hashlib
from collections import Counter

import ifcopenshell
from ifcopenshell.util import element as el
from ifcopenshell.util import unit as un


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def qsets_of(entity):
    """Return {set_name: {prop: value}} including quantity sets."""
    return el.get_psets(entity, qtos_only=False)


def main(path):
    print("=" * 78)
    print(f"FILE      : {path}")
    print(f"SHA-256   : {sha256(path)}")
    f = ifcopenshell.open(path)
    print(f"SCHEMA    : {f.schema}")

    # ---- project units ----
    print("\n--- PROJECT UNITS ---")
    try:
        print("  length unit scale to m :", un.calculate_unit_scale(f))
    except Exception as e:
        print("  length unit scale error:", e)
    for u in f.by_type("IfcSIUnit"):
        print(f"  IfcSIUnit  {u.UnitType:16} prefix={u.Prefix} name={u.Name}")

    # ---- entity census ----
    print("\n--- ENTITY CENSUS ---")
    for t in ["IfcSpace", "IfcWindow", "IfcRelSpaceBoundary", "IfcElementQuantity"]:
        print(f"  {t:22} {len(f.by_type(t))}")

    # ---- spaces: quantities relevant to R1(floor area) / R2(height) ----
    print("\n--- IfcSpace QUANTITIES (need: NetFloorArea for R1, FinishCeilingHeight for R2) ---")
    space_field_hits = Counter()
    for sp in f.by_type("IfcSpace")[:8]:
        psets = qsets_of(sp)
        qname = next((k for k in psets if "BaseQuantities" in k or "Qto_Space" in k), None)
        q = psets.get(qname, {}) if qname else {}
        for key in ["NetFloorArea", "GrossFloorArea", "FinishCeilingHeight", "Height", "NetVolume"]:
            if key in q:
                space_field_hits[key] += 1
        print(f"  Space {sp.GlobalId} name={sp.LongName or sp.Name!r}")
        print(f"    quantity set: {qname}")
        print(f"    NetFloorArea={q.get('NetFloorArea')}  GrossFloorArea={q.get('GrossFloorArea')}")
        print(f"    FinishCeilingHeight={q.get('FinishCeilingHeight')}  Height={q.get('Height')}")
    print(f"  >> space field coverage across spaces: {dict(space_field_hits)}")

    # ---- windows: quantities relevant to R1 (glazing area) ----
    print("\n--- IfcWindow QUANTITIES (need: Area + GlazingAreaFraction for R1) ---")
    win_hits = Counter()
    sample = f.by_type("IfcWindow")[:5]
    for w in sample:
        psets = qsets_of(w)
        area = None
        glaz = None
        for setname, props in psets.items():
            for k, v in props.items():
                if k == "Area":
                    area = (setname, v)
                    win_hits["Area"] += 1
                if k == "GlazingAreaFraction":
                    glaz = (setname, v)
                    win_hits["GlazingAreaFraction"] += 1
        # OverallWidth/Height on the IfcWindow entity itself
        ow = getattr(w, "OverallWidth", None)
        oh = getattr(w, "OverallHeight", None)
        print(f"  Window {w.GlobalId} name={w.Name!r}")
        print(f"    psets: {list(psets.keys())}")
        print(f"    Area={area}  GlazingAreaFraction={glaz}  OverallW/H=({ow},{oh})")
    print(f"  >> window field coverage in sample: {dict(win_hits)}")

    # ---- space <-> window relationship via IfcRelSpaceBoundary ----
    print("\n--- SPACE <-> WINDOW RELATIONSHIP (need for R1 glazing-to-room) ---")
    boundaries = f.by_type("IfcRelSpaceBoundary")
    win_boundaries = 0
    example = None
    for b in boundaries:
        rel_el = getattr(b, "RelatedBuildingElement", None)
        if rel_el is not None and rel_el.is_a("IfcWindow"):
            win_boundaries += 1
            if example is None:
                example = b
    print(f"  IfcRelSpaceBoundary total={len(boundaries)}  window-related={win_boundaries}")
    if example is not None:
        sp = example.RelatingSpace
        w = example.RelatedBuildingElement
        print(f"  example: Space {sp.GlobalId} ({sp.LongName or sp.Name!r}) <-> Window {w.GlobalId} ({w.Name!r})")
        print(f"           physical/virtual={example.PhysicalOrVirtualBoundary} internal/external={example.InternalOrExternalBoundary}")

    print("\n" + "=" * 78)


if __name__ == "__main__":
    main(sys.argv[1])
