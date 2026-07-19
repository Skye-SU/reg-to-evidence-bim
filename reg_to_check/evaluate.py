"""Tiny regression / evaluation harness.

Runs the pipeline over the controlled cases and scores predictions against the
hand-authored gold set. Reports outcome accuracy, applicability accuracy, review
precision/recall (treating `needs_review` as the positive class), and which decision
branches / reason codes were exercised.

This is a small regression benchmark for the slice, NOT a research-grade benchmark; it
does not cite external evaluation frameworks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .checker import run_check
from .ifc_reader import IFCModel
from .models import EvidenceRecord, ReasonCode, SourceRecord, RuleObject

# Terminal decision branches the pipeline can end on (coverage denominator).
BRANCH_UNIVERSE = [
    "source_integrity_failure",
    "not_applicable",
    "scope_unknown_review",
    "mapping_review",
    "evaluate_pass",
    "evaluate_fail",
]
REASON_CODE_UNIVERSE = [c.value for c in ReasonCode]


def _terminal_branch(record: EvidenceRecord) -> str:
    last = record.decision_path[-1] if record.decision_path else ""
    if last.startswith("source_integrity:fail"):
        return "source_integrity_failure"
    return {
        "applicability:not_applicable": "not_applicable",
        "applicability:unknown": "scope_unknown_review",
        "mapping:needs_review": "mapping_review",
        "evaluate:pass": "evaluate_pass",
        "evaluate:fail": "evaluate_fail",
    }.get(last, last or "unknown")


def _reason_codes_in(record: EvidenceRecord) -> set[str]:
    seen: set[str] = set()
    for text in record.review_reasons:
        for code in REASON_CODE_UNIVERSE:
            if code in text:
                seen.add(code)
    return seen


def evaluate(
    cases: list[dict[str, Any]],
    rules: dict[str, RuleObject],
    sources: dict[str, SourceRecord],
    model: IFCModel | None,
    gold: dict[str, Any],
) -> dict[str, Any]:
    # run pipeline
    predicted: dict[tuple[str, str], EvidenceRecord] = {}
    for c in cases:
        for rule_id in c["rules"]:
            predicted[(rule_id, c["element_id"])] = run_check(c, rules[rule_id], sources, model)

    expected = {(g["rule_id"], g["element_id"]): g for g in gold["expected"]}

    outcome_correct = 0
    applic_correct = 0
    mismatches: list[dict[str, Any]] = []
    tp = fp = fn = tn = 0
    status_dist: dict[str, int] = {}
    branches_hit: set[str] = set()
    reason_codes_hit: set[str] = set()

    for key, exp in expected.items():
        rec = predicted.get(key)
        if rec is None:
            mismatches.append({"key": list(key), "error": "no prediction produced"})
            continue

        status_dist[rec.status.value] = status_dist.get(rec.status.value, 0) + 1
        branches_hit.add(_terminal_branch(rec))
        reason_codes_hit |= _reason_codes_in(rec)

        status_ok = rec.status.value == exp["status"]
        applic_ok = rec.applicability.value == exp["applicability"]
        outcome_correct += int(status_ok)
        applic_correct += int(applic_ok)
        if not (status_ok and applic_ok):
            mismatches.append(
                {
                    "key": list(key),
                    "expected": {"status": exp["status"], "applicability": exp["applicability"]},
                    "predicted": {"status": rec.status.value, "applicability": rec.applicability.value},
                }
            )

        # review = positive class
        pred_review = rec.status.value == "needs_review"
        gold_review = exp["status"] == "needs_review"
        tp += int(pred_review and gold_review)
        fp += int(pred_review and not gold_review)
        fn += int(not pred_review and gold_review)
        tn += int(not pred_review and not gold_review)

    n = len(expected)
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None

    return {
        "n_checks": len(predicted),
        "n_gold": n,
        "outcome_accuracy": outcome_correct / n if n else None,
        "outcome_correct": outcome_correct,
        "applicability_accuracy": applic_correct / n if n else None,
        "applicability_correct": applic_correct,
        "review": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall,
            "positives_in_gold": tp + fn,
        },
        "status_distribution": status_dist,
        "branch_coverage": {
            "hit": sorted(branches_hit),
            "missing": sorted(set(BRANCH_UNIVERSE) - branches_hit),
            "count": f"{len(branches_hit & set(BRANCH_UNIVERSE))}/{len(BRANCH_UNIVERSE)}",
        },
        "reason_code_coverage": {
            "hit": sorted(reason_codes_hit),
            "missing": sorted(set(REASON_CODE_UNIVERSE) - reason_codes_hit),
            "count": f"{len(reason_codes_hit)}/{len(REASON_CODE_UNIVERSE)}",
        },
        "mismatches": mismatches,
    }


def render_eval_markdown(metrics: dict[str, Any]) -> str:
    def pct(x):
        return f"{x*100:.1f}%" if isinstance(x, (int, float)) else "n/a"

    rv = metrics["review"]
    lines = [
        "# Reg-to-Evidence — evaluation report",
        "",
        "Tiny regression benchmark for this slice (gold labels authored before running). "
        "Not a research-grade benchmark.",
        "",
        f"- Checks scored: **{metrics['n_gold']}**",
        f"- Outcome accuracy: **{pct(metrics['outcome_accuracy'])}** "
        f"({metrics['outcome_correct']}/{metrics['n_gold']})",
        f"- Applicability accuracy: **{pct(metrics['applicability_accuracy'])}** "
        f"({metrics['applicability_correct']}/{metrics['n_gold']})",
        f"- Review detection (positive = needs_review): "
        f"precision **{pct(rv['precision'])}**, recall **{pct(rv['recall'])}** "
        f"(tp={rv['tp']}, fp={rv['fp']}, fn={rv['fn']}, tn={rv['tn']}, "
        f"gold positives={rv['positives_in_gold']})",
        "",
        f"- Status distribution: {metrics['status_distribution']}",
        f"- Branch coverage: {metrics['branch_coverage']['count']} — "
        f"hit {metrics['branch_coverage']['hit']}; missing {metrics['branch_coverage']['missing']}",
        f"- Reason-code coverage: {metrics['reason_code_coverage']['count']} — "
        f"hit {metrics['reason_code_coverage']['hit']}; missing {metrics['reason_code_coverage']['missing']}",
        "",
    ]
    if metrics["mismatches"]:
        lines.append(f"## Mismatches ({len(metrics['mismatches'])})")
        for m in metrics["mismatches"]:
            lines.append(f"- `{m}`")
    else:
        lines.append("**No mismatches: all predictions match the gold set.**")
    lines.append("")

    notes = [
        _COVERAGE_NOTE.get(c, f"`{c}` is not yet exercised by any case")
        for c in metrics["reason_code_coverage"]["missing"]
    ]
    if notes:
        lines.append("> Coverage notes: " + "; ".join(notes) + ".")
        lines.append("")
    return "\n".join(lines)


# Why a given reason code may legitimately be absent from a live run's coverage.
_COVERAGE_NOTE = {
    "SOURCE_INTEGRITY_FAILURE": (
        "`SOURCE_INTEGRITY_FAILURE` is exercised by fault-injection tests, not the normal "
        "case set (no tampered clause is shipped in the cases)"
    ),
}
