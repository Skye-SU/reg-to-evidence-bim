# Reg-to-Evidence — final self-check

A frank inventory of what this build does, what it deliberately does **not** do, and the
few things worth doing next. Scored against the build's Definition of Done.
Verified state at time of writing: **36 tests green**; `run`, `evaluate`, `extract` all
produce committed artifacts under `examples/output/`, offline and deterministic.

## Covered

**Deterministic core (P0)**

- Full pipeline `source manifest → normalized rule → source-integrity → applicability → IFC mapping (provenance) → deterministic check → evidence record + report`
(`reg_to_check/`, `examples/output/report.md`).
- **R2** (`Cap.123F Reg.24(1)`): pass / fail / review, reading `FinishCeilingHeight` from a
pinned real IFC fixture.
- **R1** (`Cap.123F Reg.30(2)(a)(i)`): pass / fail / review. Real spaces route to review
(glazing fraction absent); constructed cases drive the ratio pass/fail.
- Typed domain objects, explicit reason codes, no `eval()`, no dynamic requirement strings.

**Data honesty (P0)**

- Provenance on every observation: model SHA-256, IFC schema, GlobalId, property path, raw
value + raw unit, SI value + SI unit, extraction method, data-quality flags.
- Refuses to fabricate: slab-to-slab `Height` ≠ finished height (`DEFINITION_MISMATCH`);
outer window `Area` ≠ glass area (`MISSING_DATA`); window must tie to space via
`IfcRelSpaceBoundary` (`RELATIONSHIP_UNVERIFIED`); `ObjectType` is never treated as legal use.
- `rejected_observations` keeps "seen but not used" values on the audit record.

**Units**

- Safely convertible non-SI units (mm, cm, ft; mm², cm², ft²) are converted and judged.
- `UNIT_MISMATCH` only for a missing / unknown / dimension-inconsistent unit → review,
never silent coercion (`reg_to_check/units.py`, `test_r2_slice.py`).

**Reliability layer**

- Source integrity: manifest is the sole excerpt home; a tampered excerpt or a drifted /
unknown / dangling `source_id` blocks any hard judgment and routes to review.
- Human-review router: any source/data/applicability reason code → `needs_review`, never pass/fail.

**Evaluation harness**

- 22 `(rule_id, element_id)` gold cases authored before running; outcome 22/22, applicability
22/22, review precision/recall 100% (11 positives, 11 negatives), 0 mismatches.
- Reason-code / branch coverage reported and self-flagged (`examples/output/eval_report.md`).
- Fault coverage across all four designed categories: source hash (fault-injection test),
unit (three cases), required field (`CTRL-NODATA`), space-window relationship (`CTRL-R1-NOWINDOW`).

**Controlled LLM rule extraction (P1)**

- `RuleCandidate` proposals gated by schema + source-span/hash + gold diff before acceptance;
drift / hash tamper / smuggled fields are rejected (`reg_to_check/extractor.py`,
`tests/test_extraction.py`, `examples/output/extraction_report.md`).
- The extractor output is provably off the compliance path (guarded by a test); the checker
reads only the human `rules.yaml`.
- Ships a cached, offline stand-in response — pluggable for a live provider adapter.

## Not covered (deliberate scope boundaries)

- **R3 (travel distance)** — designed but not implemented. No geometry / graph
reasoning, by design.
- **Live LLM call** — only a cached stand-in is bundled, to stay offline and deterministic.
This demonstrates the validation gates, not a specific model's extraction quality.
- **Real non-SI IFC fixture** — unit conversion is exercised via constructed values, not by a
fixture whose IFC project units are non-SI.
- **Element-level aggregation** — output is per-`(rule_id, element_id)` records; an
element-level summary (`fail_with_open_reviews` etc.) is not built. Findings coexist, un-aggregated.
- **Legal completeness** — check logic is simplified: R2 omits the 2.3 m under-beam proviso and  
Reg 24(2); R1 omits the 1/16 openable-area sub-requirement and the prescribed-window condition.  
out of scope by design.
- **Structural note (not a gap):** several proposed modules (`taxonomy`, `router`, `aggregate`,
`evidence`) were folded into `models` / `mapping` / `checker` / `report` to keep the slice
small; `controlled_ifc` and `external_precomputed` source modes exist in the enum but are unused.

## Cannot claim (honesty boundary)

- Not that any existing system lacks audit / HITL / evidence linking and that this fills a gap.
- Not that the tool "understands HK building law" or is fit for government approval.
- Not that an IFC-reported quantity is a legally equivalent, surveyed measurement.
- Not EU AI Act / ISO 42001 compliance; not a research-grade benchmark.

## Future work

Three concrete next steps:

1. **Geometry & graph reasoning** — compute travel distance from IFC topology/geometry (R3),
  rather than accepting a precomputed scalar.
2. **Rule scaling** — reliable extraction/evaluation across multiple clauses, cross-references,
  tables, exceptions, and version changes.
3. **Professional validation** — an architect / plan-checker confirms applicability, quantity
  semantics, and gold labels.

### Agent roadmap (V0 → V1 → V2)

This build is intentionally **V0**: a deterministic tool core with a validated extraction
gate — not yet an agent. Those same tools are exactly what an agent would call, so the
natural evolution is:

- **V0 · Deterministic tool core (this build).** Source integrity, applicability, IFC
observation + unit/provenance mapping, deterministic pass/fail/review, an evaluation
harness, and a schema/span/gold-gated LLM `RuleCandidate` that never touches the verdict.
- **V1 · Single-agent orchestrator.** An LLM agent parses a natural-language request, selects
the relevant clauses/rules, and calls the V0 tools (extractor, source verifier, IFC reader,
checker). The deterministic checker still issues every pass/fail; the agent only plans,
explains, and turns missing data / definition mismatch / unverified relationships into
human-review questions.
- **V2 · Multi-agent workflow.** Split responsibilities into role-scoped agents (task planning,
rule proposal, BIM evidence retrieval, deterministic checking, verification/critic,
human-review routing, reporting) for larger AEC compliance runs.

Design invariant across every version: **the hard compliance judgment stays in the
deterministic checker; the LLM never issues a verdict.**