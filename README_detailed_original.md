# Reg-to-Evidence — auditable compliance review for IFC/BIM models

An AI-assisted prototype that turns a building rule plus IFC/BIM model data into a
**traceable, reviewable evidence record** — source clause, observed value, required value,
gap, provenance, and an explicit human-review flag when the evidence is insufficient.
It is an evidence / audit layer, not a verdict oracle: a deterministic checker decides
pass / fail / review, and insufficient evidence is routed to a human rather than guessed.

> **Scope of this build.**
> - **R2** (`Cap.123F Reg.24(1)`, finished floor-to-ceiling height ≥ 2.5 m): full pass /
>   fail / review, reading finished height from a real IFC model.
> - **R1** (`Cap.123F Reg.30(2)(a)(i)`, glazing area ≥ 1/10 floor area): full pass / fail /
>   review. On the real fixture the glazing fraction is absent, so glass area is not
>   derivable and real spaces route to review; constructed cases exercise the ratio pass/fail.
> - **Units**: hand-authored values may be given in non-SI units. Safely convertible units
>   (mm, cm, ft; mm², cm², ft² …) are converted and judged normally; only a missing, unknown,
>   or dimension-inconsistent unit is a `UNIT_MISMATCH` (→ review, never silent coercion).
> - **R3** (travel distance): designed but not implemented.

## What the slice proves

`source manifest → normalized rule → source-integrity check → applicability → IFC
mapping (with provenance) → deterministic check / review routing → evidence record + report.`

- Reads **real** quantities from a pinned IFC fixture (KIT/FZK-Haus) with full provenance
  (model SHA-256, IfcSpace GlobalId, property path, raw + SI value/unit): `FinishCeilingHeight`
  for R2, `NetFloorArea` and window relationships for R1.
- Distinguishes legal text, normalized rule, IFC observation, and final result — they are
  never collapsed into one "AI answer".
- Routes insufficient evidence to review instead of guessing:
  - legal use not established → `RULE_SCOPE_UNKNOWN`
  - only a slab-to-slab `Height` present → `DEFINITION_MISMATCH` (never substituted for R2)
  - window `Area` present but `GlazingAreaFraction` absent → `MISSING_DATA` (R1: outer window
    area is **not** treated as glass area)
  - no window can be tied to the space → `RELATIONSHIP_UNVERIFIED` (R1)
  - unit missing / unknown / dimension-inconsistent → `UNIT_MISMATCH` (a *convertible* non-SI
    unit is not a fault — it is converted and judged)
  - required observation missing → `MISSING_DATA`
- A tampered source excerpt is rejected by the hash check and **forced into review**, so a
  real pass cannot survive silent clause drift. An unknown/dangling `source_id` degrades the
  same way (routed to review), never a crash.
- Every record keeps a **`rejected_observations`** trail: values that were read from the model
  but deliberately *not* used for the verdict (e.g. a slab-to-slab `Height` seen while judging
  R2, or an outer-window `Area` seen while judging R1). The audit shows not just what was used,
  but what was seen and knowingly set aside — the "knowing when to stop" is itself on the record.
- An **LLM-proposed rule** is accepted only after passing three gates (schema, source-span/hash,
  gold diff); the model's output never feeds a compliance verdict — the checker reads only the
  human-authored `rules.yaml` (see *LLM rule extraction* below).

The honest headline is R1 on real data: rather than invent a glass area from the window's
outer `Area`, the tool stops the check for human review. The same instinct drives the unit
handling — it converts what it safely can, and refuses (rather than coerces) what it cannot.

## 60-second run

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e .
.venv/bin/reg-to-check run \
  --manifest sources/source_manifest.yaml \
  --rules rules.yaml \
  --ifc data/fixtures/AC20-FZK-Haus.ifc \
  --cases data/controlled_cases.json \
  --out out/
```

A committed sample run (no need to execute anything) is in [`examples/output/`](examples/output/).

## Results on the current cases

22 checks: `pass=8, fail=2, not_applicable=1, needs_review=11`. See
[`examples/output/report.md`](examples/output/report.md).

- **R2** (13 records): passes from the real model (incl. the 2.5 m = 2.5 m equality case)
  and a `2600 mm → 2.6 m` unit-conversion pass; one not-applicable; one scope-unknown review;
  a constructed fail; reviews for definition mismatch, missing data, and three unit faults
  (missing / unknown / dimension-inconsistent).
- **R1** (9 records): real habitation/office/kitchen spaces route to review because
  `GlazingAreaFraction` is absent (`MISSING_DATA`); `RELATIONSHIP_UNVERIFIED` when no window
  ties to the space; constructed pass (0.15), fail (0.075), threshold-equality pass (0.10),
  and a `30000 cm² → 3.0 m²` conversion pass.

## Evaluation

A tiny regression harness scores every prediction against a gold set authored before running
(`data/gold_set.json`). On the current cases: **outcome accuracy 22/22, applicability 22/22,
review detection precision/recall 100% (11 review positives, 11 negatives), 0 mismatches.** It
also reports branch / reason-code coverage: 5/6 reason codes are exercised by the live run;
only `SOURCE_INTEGRITY_FAILURE` is left to fault-injection tests (no tampered clause ships in
the case set), which the report flags itself. This is a regression benchmark for the slice,
not a research-grade benchmark.

```bash
.venv/bin/reg-to-check evaluate \
  --manifest sources/source_manifest.yaml --rules rules.yaml \
  --ifc data/fixtures/AC20-FZK-Haus.ifc --cases data/controlled_cases.json \
  --gold data/gold_set.json --out out/
```

Committed report: [`examples/output/eval_report.md`](examples/output/eval_report.md).

## LLM rule extraction (validated, not trusted)

An extractor proposes a typed `RuleCandidate` from each manifest excerpt; the proposal is
accepted only after three deterministic gates: **(1) schema** (parses into the typed model,
extra fields forbidden), **(2) source-span/hash** (its clause id + span hash must match the
exact manifest excerpt), **(3) gold diff** (every checkable field must equal the human rule in
`rules.yaml`). A drifted threshold, an out-of-scope use, a tampered hash, or a smuggled
`verdict` field is rejected — and the LLM output is never on the compliance decision path.

The shipped extractor **replays a committed cached response**
([`examples/cached_llm_response.json`](examples/cached_llm_response.json)) so the pipeline is
offline and deterministic; **no live model call is bundled.** Going live is a one-function swap
(a provider adapter sending only the public excerpt + the schema); the gates are unchanged.

```bash
.venv/bin/reg-to-check extract \
  --manifest sources/source_manifest.yaml --rules rules.yaml \
  --cache examples/cached_llm_response.json --out out/
```

Committed report: [`examples/output/extraction_report.md`](examples/output/extraction_report.md).

## Data provenance

| source mode | meaning |
|---|---|
| `pinned_ifc` | read from `data/fixtures/AC20-FZK-Haus.ifc` (SHA-256 pinned) |
| `constructed_case` | hand-authored value, explicitly not from any model |

Pinned fixture: KIT / FZK-Haus standard test model (ArchiCAD export, declares IFC4),
retrieved from steptools mirror on 2026-07-18,
SHA-256 `ea6f04eaf92fac4d7ad0038bc3d2dfea4c094dd3f516ecc33c50bf1835ca108d`.
`legal_space_use` is always a constructed annotation — the IFC does not legally classify
rooms.

## Limitations (honest scope)

- Real regulatory excerpts, but the check logic is **simplified for demonstration**: R2
  omits the 2.3 m under-beam proviso and the sloping-ceiling rule (Reg 24(2)); R1 omits the
  1/16 openable-area sub-requirement and the prescribed-window condition (Reg 30(2)(a)(ii)).
- R1 pass/fail is exercised only by **constructed** cases; the real fixture lacks a derivable
  glazing area, so every real R1 space routes to review.
- The unit converter covers common length/area units; it is not a general units-of-measure
  engine (no volume/temperature/etc.), and does not read non-SI *IFC* fixtures.
- The LLM rule-extraction loop ships a **cached, offline stand-in** response — no live model
  call is bundled. It demonstrates the validation gates, not a specific model's quality.
- Model-reported quantities are not independently surveyed or professionally validated.
- Results are pre-screening demonstrations, **not compliance advice or approval decisions**.
- The source-integrity check proves the excerpt was not altered locally; it does **not**
  prove the online law is still in force.

## Layout

```
reg_to_check/       # models, sources, rules, applicability, ifc_reader, mapping, units,
                    #   checker, evaluate, extractor, report, cli
sources/            # source_manifest.yaml (clause + excerpt + hash)
rules.yaml          # normalized R1/R2 rules referencing the manifest by hash
data/fixtures/      # pinned IFC fixture
data/controlled_cases.json, data/gold_set.json
examples/cached_llm_response.json   # cached extractor stand-in (no live call bundled)
examples/output/    # committed samples: report.md + eval_report.md + extraction_report.md + *.json
tests/              # R1/R2 pass/fail/review, units, source-integrity fault injection,
                    #   eval harness, extraction gates, CLI smoke
SELF_CHECK.md       # final self-check: covered / not covered / future work
```
