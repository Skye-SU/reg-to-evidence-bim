"""Tests for the controlled LLM rule-extraction loop.

The point of these tests is not that the extractor is clever — it is that the three gates
(schema, source-span/hash, gold diff) have teeth, and that nothing the extractor emits can
reach the compliance decision.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from reg_to_check.extractor import (
    cached_extractor,
    extract_and_validate,
    run_extraction,
)
from reg_to_check.rules import load_rules
from reg_to_check.sources import load_sources

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sources" / "source_manifest.yaml"
RULES = ROOT / "rules.yaml"
CACHE = ROOT / "examples" / "cached_llm_response.json"

R24 = "HK_CAP123F_R24_CURRENT"  # -> R2_finished_height


@pytest.fixture(scope="module")
def ctx():
    sources = load_sources(MANIFEST)
    rules = load_rules(RULES)
    raw = json.loads(CACHE.read_text(encoding="utf-8"))["candidates"]
    return sources, rules, raw


def _gold_for(rules, source_id):
    return next(r for r in rules.values() if r.source_id == source_id)


def test_shipped_candidates_all_accepted(ctx):
    sources, rules, _ = ctx
    validations = run_extraction(sources, rules, cached_extractor(CACHE))
    assert len(validations) == 2
    for v in validations:
        assert v.schema_ok and v.clause_ok and v.source_hash_ok
        assert v.gold_diff == {}
        assert v.accepted


def test_gold_diff_catches_threshold_drift(ctx):
    sources, rules, raw = ctx
    tampered = dict(raw[R24], threshold=2.6)  # LLM proposes wrong number
    v = extract_and_validate(tampered, sources[R24], _gold_for(rules, R24))
    assert v.schema_ok is True  # well-formed...
    assert "threshold" in v.gold_diff  # ...but caught by the gold diff
    assert v.accepted is False


def test_gold_diff_catches_scope_drift(ctx):
    sources, rules, raw = ctx
    tampered = dict(raw[R24], applies_to_legal_use=["habitation", "office", "kitchen"])
    v = extract_and_validate(tampered, sources[R24], _gold_for(rules, R24))
    assert "applies_to_legal_use" in v.gold_diff
    assert v.accepted is False


def test_span_hash_tamper_is_rejected(ctx):
    sources, rules, raw = ctx
    tampered = dict(raw[R24], source_span_hash="sha256:deadbeef")
    v = extract_and_validate(tampered, sources[R24], _gold_for(rules, R24))
    assert v.source_hash_ok is False
    assert v.accepted is False


def test_schema_rejects_malformed_candidate(ctx):
    sources, rules, raw = ctx
    broken = {k: val for k, val in raw[R24].items() if k != "threshold"}  # missing field
    v = extract_and_validate(broken, sources[R24], _gold_for(rules, R24))
    assert v.schema_ok is False
    assert v.accepted is False


def test_schema_rejects_extra_fields(ctx):
    sources, rules, raw = ctx
    sneaky = dict(raw[R24], verdict="pass")  # extractor tries to smuggle a decision in
    v = extract_and_validate(sneaky, sources[R24], _gold_for(rules, R24))
    assert v.schema_ok is False
    assert v.accepted is False


def test_extractor_is_off_the_compliance_path():
    # architectural guarantee: the deterministic checker never touches candidates.
    import reg_to_check.checker as checker_mod

    src = inspect.getsource(checker_mod)
    assert "extractor" not in src
    assert "RuleCandidate" not in src
