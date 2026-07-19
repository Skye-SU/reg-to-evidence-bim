# Reg-to-Evidence — evaluation report

Tiny regression benchmark for this slice (gold labels authored before running). Not a research-grade benchmark.

- Checks scored: **22**
- Outcome accuracy: **100.0%** (22/22)
- Applicability accuracy: **100.0%** (22/22)
- Review detection (positive = needs_review): precision **100.0%**, recall **100.0%** (tp=11, fp=0, fn=0, tn=11, gold positives=11)

- Status distribution: {'pass': 8, 'not_applicable': 1, 'needs_review': 11, 'fail': 2}
- Branch coverage: 5/6 — hit ['evaluate_fail', 'evaluate_pass', 'mapping_review', 'not_applicable', 'scope_unknown_review']; missing ['source_integrity_failure']
- Reason-code coverage: 5/6 — hit ['DEFINITION_MISMATCH', 'MISSING_DATA', 'RELATIONSHIP_UNVERIFIED', 'RULE_SCOPE_UNKNOWN', 'UNIT_MISMATCH']; missing ['SOURCE_INTEGRITY_FAILURE']

**No mismatches: all predictions match the gold set.**

> Coverage notes: `SOURCE_INTEGRITY_FAILURE` is exercised by fault-injection tests, not the normal case set (no tampered clause is shipped in the cases).
