"""Controlled LLM rule-extraction loop — validated, never trusted.

The idea: an LLM reads a manifest excerpt (public legal text only) and proposes a typed
`RuleCandidate`. Before that candidate is allowed anywhere near a decision it must pass
three deterministic gates:

  1. schema validation      — parses into `RuleCandidate` (typed, no free-form fields)
  2. source-span / hash      — the candidate's clause id + span hash must match the exact
                               manifest excerpt (proves it is bound to the cited span,
                               not a hallucinated one)
  3. gold diff               — every checkable field must equal the human-authored gold
                               rule in `rules.yaml`

Two hard boundaries:
  * The LLM output is NEVER used for compliance judgment. The deterministic checker reads
    only the human `rules.yaml`; this module is a QA gate on candidate rules, off the
    decision path.
  * No live model call is bundled. The shipped extractor replays a committed cached
    response so the whole pipeline is offline and deterministic. The extractor is
    pluggable: swap `cached_extractor` for a provider adapter (sending only the public
    excerpt + this schema) to go live — the three gates stay identical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .models import RuleObject, SourceRecord
from .sources import excerpt_sha256

# checkable fields an extractor must produce from the excerpt, compared field-for-field
# against the human gold rule.
GOLD_FIELDS = (
    "check_type", "operands", "threshold", "unit_si", "applies_to_legal_use",
    "source_id", "source_clause_id", "source_span_hash",
)


class RuleCandidate(BaseModel):
    """A proposed normalized rule (e.g. from an LLM). Typed on purpose: an ill-formed
    proposal fails schema validation before it can be compared to anything."""

    model_config = {"extra": "forbid"}

    rule_id: str
    source_id: str
    source_clause_id: str
    source_span_hash: str
    check_type: str
    operands: list[str]
    threshold: float
    unit_si: str
    applies_to_legal_use: list[str]


class CandidateValidation(BaseModel):
    rule_id: str
    schema_ok: bool
    clause_ok: bool
    source_hash_ok: bool
    gold_diff: dict[str, dict[str, Any]]
    accepted: bool
    notes: list[str] = []


# An extractor takes the source record (public excerpt + metadata) and returns a raw dict
# (as an LLM would emit JSON). Kept as a narrow callable so no core code binds to a vendor.
ExtractorFn = Callable[[SourceRecord], dict[str, Any] | None]


def cached_extractor(cache_path: str | Path) -> ExtractorFn:
    """Replay a committed response file. This is a stand-in for a live LLM call; the
    validation gates below treat its output exactly as they would a live one."""
    data = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    candidates: dict[str, Any] = data.get("candidates", {})

    def _extract(source: SourceRecord) -> dict[str, Any] | None:
        return candidates.get(source.source_id)

    return _extract


def validate_candidate(
    candidate: RuleCandidate, source: SourceRecord, gold: RuleObject
) -> CandidateValidation:
    """Run gates 2 (source-span/hash) and 3 (gold diff) on an already-parsed candidate."""
    clause_ok = (
        candidate.source_id == source.source_id
        and candidate.source_clause_id == source.clause_id
    )
    recomputed = excerpt_sha256(source.excerpt)
    source_hash_ok = candidate.source_span_hash == recomputed == source.excerpt_sha256

    gold_diff: dict[str, dict[str, Any]] = {}
    for field in GOLD_FIELDS:
        cv = getattr(candidate, field)
        gv = getattr(gold, field)
        differs = sorted(cv) != sorted(gv) if field == "applies_to_legal_use" else cv != gv
        if differs:
            gold_diff[field] = {"candidate": cv, "gold": gv}

    notes: list[str] = []
    if not clause_ok:
        notes.append("clause id / source id does not match the manifest")
    if not source_hash_ok:
        notes.append("span hash does not match the exact manifest excerpt")
    if gold_diff:
        notes.append(f"differs from gold rule in: {', '.join(sorted(gold_diff))}")

    accepted = clause_ok and source_hash_ok and not gold_diff
    return CandidateValidation(
        rule_id=candidate.rule_id,
        schema_ok=True,
        clause_ok=clause_ok,
        source_hash_ok=source_hash_ok,
        gold_diff=gold_diff,
        accepted=accepted,
        notes=notes,
    )


def extract_and_validate(
    raw: dict[str, Any] | None, source: SourceRecord, gold: RuleObject
) -> CandidateValidation:
    """Gate 1 (schema) then gates 2-3. A malformed proposal is rejected here, never parsed
    into anything the rest of the system would consume."""
    if raw is None:
        return CandidateValidation(
            rule_id="?", schema_ok=False, clause_ok=False, source_hash_ok=False,
            gold_diff={}, accepted=False, notes=[f"no candidate produced for {source.source_id}"],
        )
    try:
        candidate = RuleCandidate(**raw)
    except ValidationError as exc:
        return CandidateValidation(
            rule_id=str(raw.get("rule_id", "?")), schema_ok=False, clause_ok=False,
            source_hash_ok=False, gold_diff={}, accepted=False,
            notes=[f"schema validation failed: {exc.error_count()} error(s)"],
        )
    return validate_candidate(candidate, source, gold)


def run_extraction(
    sources: dict[str, SourceRecord],
    rules: dict[str, RuleObject],
    extractor: ExtractorFn,
) -> list[CandidateValidation]:
    """Extract + validate one candidate per source that a gold rule cites."""
    gold_by_source = {r.source_id: r for r in rules.values()}
    out: list[CandidateValidation] = []
    for source_id, source in sources.items():
        gold = gold_by_source.get(source_id)
        if gold is None:
            continue  # source not referenced by any gold rule; nothing to diff against
        out.append(extract_and_validate(extractor(source), source, gold))
    return out


def render_extraction_markdown(validations: list[CandidateValidation]) -> str:
    accepted = sum(v.accepted for v in validations)
    lines = [
        "# Reg-to-Evidence — LLM rule-extraction validation",
        "",
        "An extractor proposes a typed rule from each manifest excerpt; each proposal is "
        "gated by schema validation, source-span/hash validation, and a gold diff before it "
        "is accepted. The LLM output never feeds a compliance judgment — the checker reads "
        "only the human-authored `rules.yaml`.",
        "",
        "> The shipped extractor replays a committed cached response (no live model call is "
        "bundled). Swap it for a provider adapter to go live; the gates are unchanged.",
        "",
        f"- Candidates validated: **{len(validations)}**; accepted: **{accepted}/{len(validations)}**",
        "",
        "| rule | schema | clause | span hash | gold diff | accepted |",
        "|---|---|---|---|---|---|",
    ]
    for v in validations:
        diff = "—" if not v.gold_diff else ", ".join(sorted(v.gold_diff))
        lines.append(
            f"| {v.rule_id} | {_yn(v.schema_ok)} | {_yn(v.clause_ok)} | {_yn(v.source_hash_ok)} | "
            f"{diff} | {'**yes**' if v.accepted else '**NO**'} |"
        )
    lines.append("")
    for v in validations:
        if v.notes:
            lines.append(f"- `{v.rule_id}`: {'; '.join(v.notes)}")
    lines.append("")
    return "\n".join(lines)


def _yn(ok: bool) -> str:
    return "ok" if ok else "FAIL"
