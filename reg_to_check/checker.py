"""Deterministic checks + the per-(rule, element) pipeline.

Order is fixed and each stage can stop the pipeline:
  source integrity -> applicability -> mapping/data quality -> deterministic evaluate.
No dynamic eval. check_type is dispatched explicitly.

Scope note: both `min_threshold` (R2) and `ratio_minimum` (R1) are fully wired to
pass/fail/review. On the pinned fixture R1's glazing area is not derivable, so real spaces
route to review; constructed cases exercise the ratio pass/fail path.
"""

from __future__ import annotations

from typing import Any

from .applicability import decide_applicability
from .ifc_reader import IFCModel
from .mapping import build_check_input
from .models import (
    Applicability,
    CheckInput,
    CheckStatus,
    EvidenceRecord,
    Observation,
    ReasonCode,
    RuleObject,
    SourceRecord,
)
from .sources import verify_source_integrity


def evaluate_min_threshold(value_si: float, threshold: float) -> tuple[CheckStatus, float]:
    gap = round(value_si - threshold, 9)
    return (CheckStatus.PASS if value_si >= threshold else CheckStatus.FAIL), gap


def evaluate_ratio_minimum(
    numerator_si: float, denominator_si: float, threshold: float
) -> tuple[CheckStatus, float, float]:
    ratio = numerator_si / denominator_si
    gap = round(ratio - threshold, 9)
    return (CheckStatus.PASS if ratio >= threshold else CheckStatus.FAIL), gap, ratio


def run_check(
    case: dict[str, Any],
    rule: RuleObject,
    sources: dict[str, SourceRecord],
    model: IFCModel | None,
    run_id: str = "demo-r2-001",
) -> EvidenceRecord:
    decision_path: list[str] = []

    # ---- stage 1: source integrity (blocks hard judgment on failure) ----
    # verify_source_integrity handles an unknown source_id gracefully; do not look the
    # source up eagerly here (that would raise KeyError before the graceful path).
    ok, code, detail = verify_source_integrity(rule, sources)
    if not ok:
        decision_path.append(f"source_integrity:fail({code.value if code else '?'})")
        return _record(
            case, rule, Applicability.UNKNOWN, CheckStatus.NEEDS_REVIEW,
            gap=None, observed={}, integrity=False, review_reasons=[detail],
            dq_flags=[], human_review=True, decision_path=decision_path, run_id=run_id,
            element_name=case.get("element_name"), provenance={},
        )
    decision_path.append("source_integrity:ok")

    ci: CheckInput = build_check_input(case, model, rule)

    # ---- stage 2: applicability (only `applicable` proceeds) ----
    applicability, app_code, app_detail = decide_applicability(rule, ci)
    decision_path.append(f"applicability:{applicability.value}")
    if applicability == Applicability.NOT_APPLICABLE:
        return _record(
            case, rule, applicability, CheckStatus.NOT_APPLICABLE,
            gap=None, observed={}, integrity=True, review_reasons=[],
            dq_flags=ci.data_quality_flags, human_review=False,
            decision_path=decision_path, run_id=run_id, element_name=ci.element_name,
            provenance=_provenance(ci), rejected=_rejected(ci),
        )
    if applicability == Applicability.UNKNOWN:
        return _record(
            case, rule, applicability, CheckStatus.NEEDS_REVIEW,
            gap=None, observed={}, integrity=True,
            review_reasons=[f"{app_code.value}: {app_detail}"],
            dq_flags=ci.data_quality_flags, human_review=True,
            decision_path=decision_path, run_id=run_id, element_name=ci.element_name,
            provenance=_provenance(ci), rejected=_rejected(ci),
        )

    # ---- stage 3: mapping / data-quality gates -> review ----
    usable = {op: ci.observations.get(op) for op in rule.operands}
    missing_ops = [op for op, o in usable.items() if o is None or o.provenance.value_si is None]
    if ci.reason_codes or missing_ops:
        reasons = list(ci.review_details)
        for op in missing_ops:
            if not any(op in r for r in reasons):
                reasons.append(f"{ReasonCode.MISSING_DATA.value}: {op} not usable")
        decision_path.append("mapping:needs_review")
        return _record(
            case, rule, applicability, CheckStatus.NEEDS_REVIEW,
            gap=None, observed=_observed_partial(usable), integrity=True,
            review_reasons=reasons, dq_flags=ci.data_quality_flags, human_review=True,
            decision_path=decision_path, run_id=run_id, element_name=ci.element_name,
            provenance=_provenance(ci), rejected=_rejected(ci),
        )
    decision_path.append("mapping:ok")

    # ---- stage 4: deterministic evaluate ----
    if rule.check_type == "min_threshold":
        value = usable[rule.operands[0]].provenance.value_si
        status, gap = evaluate_min_threshold(value, rule.threshold)
        observed = {rule.operands[0]: value}
    elif rule.check_type == "ratio_minimum":
        num = usable[rule.operands[0]].provenance.value_si
        den = usable[rule.operands[1]].provenance.value_si
        status, gap, ratio = evaluate_ratio_minimum(num, den, rule.threshold)
        observed = {rule.operands[0]: num, rule.operands[1]: den, "ratio": round(ratio, 6)}
    else:
        raise ValueError(f"unsupported check_type {rule.check_type!r}")

    decision_path.append(f"evaluate:{status.value}")
    return _record(
        case, rule, applicability, status, gap=gap, observed=observed, integrity=True,
        review_reasons=[], dq_flags=ci.data_quality_flags, human_review=False,
        decision_path=decision_path, run_id=run_id, element_name=ci.element_name,
        provenance=_provenance(ci), rejected=_rejected(ci),
    )


def _observed_partial(usable: dict[str, Observation | None]) -> dict:
    out = {}
    for op, o in usable.items():
        if o is not None and o.provenance.value_si is not None:
            out[op] = o.provenance.value_si
    return out


def _provenance(ci: CheckInput) -> dict:
    return {
        field: obs.provenance.model_dump(mode="json", exclude_none=True)
        for field, obs in ci.observations.items()
        if obs.provenance.value_si is not None
    }


def _rejected(ci: CheckInput) -> list[dict]:
    """Observations that were seen but have no usable SI value (e.g. a slab-to-slab
    height flagged as non-substitutable). Preserved for the audit trail; never judged."""
    out = []
    for field, obs in ci.observations.items():
        if obs.provenance.value_si is None:
            out.append(
                {
                    "field_name": field,
                    "provenance": obs.provenance.model_dump(mode="json", exclude_none=True),
                }
            )
    return out


def _record(
    case, rule, applicability, status, *, gap, observed, integrity, review_reasons,
    dq_flags, human_review, decision_path, run_id, element_name, provenance,
    rejected=None,
) -> EvidenceRecord:
    required = {rule.check_type: f">= {rule.threshold} {rule.unit_si}"}
    return EvidenceRecord(
        element_id=case["element_id"],
        element_name=element_name,
        rule_id=rule.rule_id,
        applicability=applicability,
        status=status,
        observed=observed,
        required=required,
        gap=gap,
        source_clause_id=rule.source_clause_id,
        source_id=rule.source_id,
        source_span_hash=rule.source_span_hash,
        source_integrity_verified=integrity,
        input_provenance=provenance or {},
        rejected_observations=rejected or [],
        review_reasons=review_reasons,
        data_quality_flags=dq_flags,
        human_review_flag=human_review,
        decision_path=decision_path,
        simplification_note=rule.simplification_note,
        rule_schema_version=rule.rule_schema_version,
        run_id=run_id,
    )
