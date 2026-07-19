# Reg-to-Evidence — report

- R2 (`Cap.123F Reg.24(1)`): finished floor-to-ceiling height >= 2.5 m — full pass/fail/review.
- R1 (`Cap.123F Reg.30(2)(a)(i)`): glazing area >= 1/10 floor area — full pass/fail/review (real fixture spaces route to review; glazing area not derivable there).

> Demonstration only. Real regulatory excerpts; simplified check logic. Model-reported quantities are not independently surveyed. Not compliance advice.

Pinned IFC fixture SHA-256: `ea6f04eaf92fac4d7ad0038bc3d2dfea4c094dd3f516ecc33c50bf1835ca108d`

| rule | element | name | applicability | status | observed | gap | provenance | review reasons |
|---|---|---|---|---|---|---|---|---|
| R2_finished_height | `347jFE2yX7IhCEIALmupEH` | Schlafzimmer | applicable | **PASS** | finished_ceiling_height_m=2.500 | +0.000 | pinned_ifc [finished_ceiling_height_m] | - |
| R1_glazing_ratio | `347jFE2yX7IhCEIALmupEH` | Schlafzimmer | applicable | **REVIEW** | floor_area_m2=21.410 | - | pinned_ifc [floor_area_m2] | MISSING_DATA: window 1DiYqhfzH9xxuJdVHwXCNa has Area but no GlazingAreaFraction; glass area not derivable; MISSING_DATA: glazing_area_m2 not usable |
| R2_finished_height | `0Lt8gR_E9ESeGH5uY_g9e9` | Wohnen | applicable | **PASS** | finished_ceiling_height_m=2.500 | +0.000 | pinned_ifc [finished_ceiling_height_m] | - |
| R2_finished_height | `2RSCzLOBz4FAK$_wE8VckM` | Buero | applicable | **PASS** | finished_ceiling_height_m=2.500 | +0.000 | pinned_ifc [finished_ceiling_height_m] | - |
| R1_glazing_ratio | `2RSCzLOBz4FAK$_wE8VckM` | Buero | applicable | **REVIEW** | floor_area_m2=12.595 | - | pinned_ifc [floor_area_m2] | MISSING_DATA: window 1TAI4ouKX4Xx4lBDZIu5qM has Area but no GlazingAreaFraction; glass area not derivable; MISSING_DATA: glazing_area_m2 not usable |
| R2_finished_height | `2dQFggKBb1fOc1CqZDIDlx` | Galerie | applicable | **PASS** | finished_ceiling_height_m=4.000 | +1.500 | pinned_ifc [finished_ceiling_height_m] | - |
| R1_glazing_ratio | `2dQFggKBb1fOc1CqZDIDlx` | Galerie | applicable | **REVIEW** | floor_area_m2=74.509 | - | pinned_ifc [floor_area_m2] | MISSING_DATA: window 1zOBw0Gej5Wf0QAJfHnOc0 has Area but no GlazingAreaFraction; glass area not derivable; MISSING_DATA: glazing_area_m2 not usable |
| R2_finished_height | `3$f2p7VyLB7eox67SA_zKE` | Flur | not_applicable | **N/A** | - | - | pinned_ifc [finished_ceiling_height_m] | - |
| R2_finished_height | `0e_hbkIQ5DMQlIJ$2V3j_m` | Bad | unknown | **REVIEW** | - | - | pinned_ifc [finished_ceiling_height_m] | RULE_SCOPE_UNKNOWN: legal_space_use not established; the model does not legally classify the room |
| R1_glazing_ratio | `17JZcMFrf5tOftUTidA0d3` | Küche | applicable | **REVIEW** | floor_area_m2=16.305 | - | pinned_ifc [floor_area_m2] | MISSING_DATA: window 25nJxEpYf8LRDJNkMUVO0m has Area but no GlazingAreaFraction; glass area not derivable; MISSING_DATA: glazing_area_m2 not usable |
| R2_finished_height | `CTRL-LOWROOM` | Constructed low habitable room | applicable | **FAIL** | finished_ceiling_height_m=2.300 | -0.200 | constructed_case [finished_ceiling_height_m] | - |
| R2_finished_height | `CTRL-SLABONLY` | Constructed room with slab-to-slab height only | applicable | **REVIEW** | - | - | rejected: finished_ceiling_height_m | DEFINITION_MISMATCH: only slab-to-slab Height present; not substitutable; MISSING_DATA: finished_ceiling_height_m not usable |
| R2_finished_height | `CTRL-NODATA` | Constructed room with no height data | applicable | **REVIEW** | - | - | - | MISSING_DATA: finished_ceiling_height_m — no height data |
| R1_glazing_ratio | `CTRL-R1-NOWINDOW` | Constructed habitable room, window-space relation unverifiable | applicable | **REVIEW** | floor_area_m2=20.000 | - | constructed_case [floor_area_m2] | RELATIONSHIP_UNVERIFIED: constructed review case; MISSING_DATA: glazing_area_m2 not usable |
| R1_glazing_ratio | `CTRL-R1-PASS` | Constructed habitable room, adequate glazing | applicable | **PASS** | glazing_area_m2=3.000; floor_area_m2=20.000; ratio=0.150 | +0.050 | constructed_case [floor_area_m2, glazing_area_m2] | - |
| R1_glazing_ratio | `CTRL-R1-FAIL` | Constructed habitable room, insufficient glazing | applicable | **FAIL** | glazing_area_m2=1.500; floor_area_m2=20.000; ratio=0.075 | -0.025 | constructed_case [floor_area_m2, glazing_area_m2] | - |
| R1_glazing_ratio | `CTRL-R1-EQ` | Constructed office, glazing exactly at threshold | applicable | **PASS** | glazing_area_m2=2.000; floor_area_m2=20.000; ratio=0.100 | +0.000 | constructed_case [floor_area_m2, glazing_area_m2] | - |
| R2_finished_height | `CTRL-R2-MM` | Constructed habitable room, height given in millimetres | applicable | **PASS** | finished_ceiling_height_m=2.600 | +0.100 | constructed_case [finished_ceiling_height_m]; converted: finished_ceiling_height_m 2600.0 mm->2.6 m | - |
| R1_glazing_ratio | `CTRL-R1-CM2` | Constructed kitchen, glazing given in square centimetres | applicable | **PASS** | glazing_area_m2=3.000; floor_area_m2=20.000; ratio=0.150 | +0.050 | constructed_case [floor_area_m2, glazing_area_m2]; converted: glazing_area_m2 30000.0 cm2->3.0 m2 | - |
| R2_finished_height | `CTRL-UNIT-MISSING` | Constructed room, height value with no unit | applicable | **REVIEW** | - | - | rejected: finished_ceiling_height_m | UNIT_MISMATCH: finished_ceiling_height_m — unit missing |
| R2_finished_height | `CTRL-UNIT-UNKNOWN` | Constructed room, unknown/non-convertible unit | applicable | **REVIEW** | - | - | rejected: finished_ceiling_height_m | UNIT_MISMATCH: finished_ceiling_height_m — unknown/non-convertible unit 'cubit' |
| R2_finished_height | `CTRL-UNIT-DIM` | Constructed room, area unit given for a length operand | applicable | **REVIEW** | - | - | rejected: finished_ceiling_height_m | UNIT_MISMATCH: finished_ceiling_height_m — dimension mismatch: 'm2' has dimension 'area', expected 'length' |

**Summary:** 22 checks — fail=2, needs_review=11, not_applicable=1, pass=8
