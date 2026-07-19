"""Unit normalization for constructed observations.

Policy (deliberate, and this is the whole point of the module):

  * A non-SI unit that is *safely convertible* to the expected SI dimension is CONVERTED
    (mm -> m, cm2 -> m2, ft -> m ...). This is NOT a fault; the check proceeds normally.
  * `UNIT_MISMATCH` is reserved for genuine unit faults, and only these:
      - missing unit          (no unit given)
      - unknown unit          (not in the registry -> not safely convertible)
      - dimension mismatch    (e.g. an area unit supplied for a length operand)

  A UNIT_MISMATCH yields `value_si = None`, so the operand is unusable and the check
  routes to review — the bad unit is preserved on the record, never silently coerced.

Values read from the pinned IFC model are already scaled to SI in `ifc_reader` using the
model's own unit assignment; this module is for hand-authored (constructed) values.
"""

from __future__ import annotations

from .models import ReasonCode

# unit (normalized) -> (dimension, factor to SI)
_LENGTH: dict[str, float] = {
    "m": 1.0, "dm": 1e-1, "cm": 1e-2, "mm": 1e-3, "km": 1e3,
    "ft": 0.3048, "in": 0.0254,
}
_AREA: dict[str, float] = {
    "m2": 1.0, "dm2": 1e-2, "cm2": 1e-4, "mm2": 1e-6, "km2": 1e6,
    "ft2": 0.09290304, "in2": 0.00064516,
}
_FACTOR: dict[str, float] = {**_LENGTH, **_AREA}
_DIMENSION_OF: dict[str, str] = {
    **{u: "length" for u in _LENGTH},
    **{u: "area" for u in _AREA},
}
SI_UNIT: dict[str, str] = {"length": "m", "area": "m2"}

# spelled-out / IFC-style spellings -> canonical registry key
_ALIASES: dict[str, str] = {
    "metre": "m", "meter": "m", "metres": "m", "meters": "m",
    "millimetre": "mm", "millimeter": "mm",
    "centimetre": "cm", "centimeter": "cm",
    "kilometre": "km", "kilometer": "km",
    "foot": "ft", "feet": "ft", "inch": "in", "inches": "in",
    "squaremetre": "m2", "squaremeter": "m2", "sqm": "m2", "sm": "m2",
    "squarefoot": "ft2", "squarefeet": "ft2", "sqft": "ft2",
    "squaremillimetre": "mm2", "squarecentimetre": "cm2",
}


def normalize_unit(raw_unit: str | None) -> str:
    if raw_unit is None:
        return ""
    s = str(raw_unit).strip().lower().replace("²", "2").replace("^2", "2")
    s = s.replace(" ", "").replace("_", "")
    return _ALIASES.get(s, s)


def expected_dimension(field_name: str) -> str:
    """Convention: a `_m2` suffix means the operand is an area; otherwise a length."""
    return "area" if field_name.endswith("_m2") else "length"


def to_si(
    raw_value: float | None, raw_unit: str | None, expected_dim: str
) -> tuple[float | None, str, ReasonCode | None, str | None]:
    """Return (value_si, canonical_si_unit, reason_code, detail).

    reason_code is None on success (including trivial 1:1 SI). It is UNIT_MISMATCH only
    for a missing / unknown / dimension-inconsistent unit.
    """
    si_unit = SI_UNIT[expected_dim]
    if raw_value is None:
        # A missing *value* is not a unit fault; leave it to the MISSING_DATA path.
        return None, si_unit, None, None

    unit = normalize_unit(raw_unit)
    if not unit:
        return None, si_unit, ReasonCode.UNIT_MISMATCH, "unit missing"

    dim = _DIMENSION_OF.get(unit)
    if dim is None:
        return None, si_unit, ReasonCode.UNIT_MISMATCH, f"unknown/non-convertible unit {raw_unit!r}"
    if dim != expected_dim:
        return (
            None, si_unit, ReasonCode.UNIT_MISMATCH,
            f"dimension mismatch: {raw_unit!r} has dimension {dim!r}, expected {expected_dim!r}",
        )

    return raw_value * _FACTOR[unit], si_unit, None, None
