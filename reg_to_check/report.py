"""Render evidence records to a human-readable Markdown report (rule-aware)."""

from __future__ import annotations

from .models import EvidenceRecord

_STATUS_MARK = {
    "pass": "PASS",
    "fail": "FAIL",
    "needs_review": "REVIEW",
    "not_applicable": "N/A",
}


def _observed_str(r: EvidenceRecord) -> str:
    if not r.observed:
        return "-"
    parts = []
    for k, v in r.observed.items():
        if isinstance(v, (int, float)):
            parts.append(f"{k}={v:.3f}")
        else:
            parts.append(f"{k}={v}")
    return "; ".join(parts)


def _provenance_str(r: EvidenceRecord) -> str:
    parts = []
    if r.input_provenance:
        modes = {p.get("source_mode") for p in r.input_provenance.values() if isinstance(p, dict)}
        fields = ", ".join(sorted(r.input_provenance.keys()))
        parts.append(f"{'/'.join(sorted(m for m in modes if m))} [{fields}]")
        convs = []
        for f, p in sorted(r.input_provenance.items()):
            rv, sv = p.get("raw_value"), p.get("value_si")
            ru, su = p.get("raw_unit"), p.get("unit_si")
            # only surface a genuine (value-changing) conversion, not metre->m spelling
            if rv is not None and sv is not None and abs(rv - sv) > 1e-9:
                convs.append(f"{f} {rv} {ru}->{sv} {su}")
        if convs:
            parts.append("converted: " + ", ".join(convs))
    if r.rejected_observations:
        rej = ", ".join(sorted(o.get("field_name", "?") for o in r.rejected_observations))
        parts.append(f"rejected: {rej}")
    return "; ".join(parts) if parts else "-"


def render_markdown(records: list[EvidenceRecord], *, fixture_sha256: str | None) -> str:
    lines: list[str] = []
    lines.append("# Reg-to-Evidence — report")
    lines.append("")
    lines.append("- R2 (`Cap.123F Reg.24(1)`): finished floor-to-ceiling height >= 2.5 m — full pass/fail/review.")
    lines.append("- R1 (`Cap.123F Reg.30(2)(a)(i)`): glazing area >= 1/10 floor area — full pass/fail/review (real fixture spaces route to review; glazing area not derivable there).")
    lines.append("")
    lines.append(
        "> Demonstration only. Real regulatory excerpts; simplified check logic. "
        "Model-reported quantities are not independently surveyed. Not compliance advice."
    )
    lines.append("")
    if fixture_sha256:
        lines.append(f"Pinned IFC fixture SHA-256: `{fixture_sha256}`")
        lines.append("")

    lines.append("| rule | element | name | applicability | status | observed | gap | provenance | review reasons |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in records:
        gap_s = f"{r.gap:+.3f}" if r.gap is not None else "-"
        reasons = "; ".join(r.review_reasons) if r.review_reasons else "-"
        lines.append(
            f"| {r.rule_id} | `{r.element_id}` | {r.element_name or '-'} | {r.applicability.value} | "
            f"**{_STATUS_MARK.get(r.status.value, r.status.value)}** | {_observed_str(r)} | "
            f"{gap_s} | {_provenance_str(r)} | {reasons} |"
        )

    lines.append("")
    counts: dict[str, int] = {}
    for r in records:
        counts[r.status.value] = counts.get(r.status.value, 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    lines.append(f"**Summary:** {len(records)} checks — {summary}")
    lines.append("")
    return "\n".join(lines)
