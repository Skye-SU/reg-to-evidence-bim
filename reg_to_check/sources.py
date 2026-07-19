"""Source registration + deterministic source-integrity check.

The manifest is the only place the legal excerpt lives. A rule declares the hash it
expects (`source_span_hash`); this module recomputes the hash from the manifest excerpt
and compares. This proves the report's clause text was not silently altered or
LLM-generated. It does NOT prove the online law is still in force.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from .models import ReasonCode, RuleObject, SourceRecord


def excerpt_sha256(text: str) -> str:
    """Canonical hash of an excerpt string, prefixed so the algorithm is explicit."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_sources(manifest_path: str | Path) -> dict[str, SourceRecord]:
    data = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
    records: dict[str, SourceRecord] = {}
    for raw in data.get("sources", []):
        rec = SourceRecord(**raw)
        records[rec.source_id] = rec
    return records


def verify_source_integrity(
    rule: RuleObject, sources: dict[str, SourceRecord]
) -> tuple[bool, ReasonCode | None, str]:
    """Return (ok, reason_code, detail).

    Fails (and later blocks any hard pass/fail) when the clause is unknown, the clause
    id disagrees, or the recomputed excerpt hash does not match the declared hash.
    """
    src = sources.get(rule.source_id)
    if src is None:
        return False, ReasonCode.SOURCE_INTEGRITY_FAILURE, f"unknown source_id {rule.source_id!r}"

    if src.clause_id != rule.source_clause_id:
        return (
            False,
            ReasonCode.SOURCE_INTEGRITY_FAILURE,
            f"clause id mismatch: manifest {src.clause_id!r} vs rule {rule.source_clause_id!r}",
        )

    recomputed = excerpt_sha256(src.excerpt)
    if recomputed != src.excerpt_sha256:
        return (
            False,
            ReasonCode.SOURCE_INTEGRITY_FAILURE,
            f"manifest excerpt hash drifted: stored {src.excerpt_sha256} vs recomputed {recomputed}",
        )
    if recomputed != rule.source_span_hash:
        return (
            False,
            ReasonCode.SOURCE_INTEGRITY_FAILURE,
            f"rule span hash mismatch: rule {rule.source_span_hash} vs manifest {recomputed}",
        )
    return True, None, "source integrity verified"
