"""Vertical-slice tests.

R2 and R1: full pass/fail/review. Real fixture spaces route R1 to review (GlazingAreaFraction
absent); constructed cases exercise R1's ratio pass/fail. Units: safely convertible non-SI
values are converted (not faults); missing/unknown/dimension-inconsistent units are
UNIT_MISMATCH. Plus source-integrity fault injection and a CLI smoke test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reg_to_check.checker import (
    evaluate_ratio_minimum,
    run_check,
)
from reg_to_check.cli import run_pipeline
from reg_to_check.evaluate import evaluate
from reg_to_check.ifc_reader import IFCModel
from reg_to_check.models import Applicability, CheckStatus, ReasonCode
from reg_to_check.rules import load_rules
from reg_to_check.sources import excerpt_sha256, load_sources, verify_source_integrity
from reg_to_check.units import to_si

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sources" / "source_manifest.yaml"
RULES = ROOT / "rules.yaml"
FIXTURE = ROOT / "data" / "fixtures" / "AC20-FZK-Haus.ifc"
CASES = ROOT / "data" / "controlled_cases.json"
GOLD = ROOT / "data" / "gold_set.json"


@pytest.fixture(scope="module")
def context():
    sources = load_sources(MANIFEST)
    rules = load_rules(RULES)
    model = IFCModel(FIXTURE)
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    return sources, rules, model, cases


def _run_all(context):
    """Return {(rule_id, element_id): record} for every wired (case, rule)."""
    sources, rules, model, cases = context
    out = {}
    for c in cases:
        for rule_id in c["rules"]:
            out[(rule_id, c["element_id"])] = run_check(c, rules[rule_id], sources, model)
    return out


# ------------------------------------------------------------------ gold set

def test_gold_set_outcomes_match(context):
    results = _run_all(context)
    gold = json.loads(GOLD.read_text(encoding="utf-8"))["expected"]
    assert len(gold) == len(results)
    for exp in gold:
        rec = results[(exp["rule_id"], exp["element_id"])]
        assert rec.status.value == exp["status"], (exp["rule_id"], exp["element_id"])
        assert rec.applicability.value == exp["applicability"], (exp["rule_id"], exp["element_id"])


# ------------------------------------------------------------------ R2

def test_r2_real_pass_reads_finished_height_from_ifc(context):
    rec = _run_all(context)[("R2_finished_height", "347jFE2yX7IhCEIALmupEH")]
    assert rec.status is CheckStatus.PASS
    assert rec.observed["finished_ceiling_height_m"] == pytest.approx(2.5)
    prov = rec.input_provenance["finished_ceiling_height_m"]
    assert prov["source_mode"] == "pinned_ifc"
    assert prov["property_path"].endswith("FinishCeilingHeight")
    assert prov["model_sha256"]


def test_r2_threshold_equality_is_pass(context):
    rec = _run_all(context)[("R2_finished_height", "347jFE2yX7IhCEIALmupEH")]
    assert rec.gap == pytest.approx(0.0)
    assert rec.status is CheckStatus.PASS


def test_r2_constructed_fail(context):
    rec = _run_all(context)[("R2_finished_height", "CTRL-LOWROOM")]
    assert rec.status is CheckStatus.FAIL
    assert rec.gap == pytest.approx(-0.2)


def test_r2_scope_unknown_routes_to_review(context):
    rec = _run_all(context)[("R2_finished_height", "0e_hbkIQ5DMQlIJ$2V3j_m")]
    assert rec.status is CheckStatus.NEEDS_REVIEW
    assert rec.applicability is Applicability.UNKNOWN
    assert rec.human_review_flag is True


def test_r2_slab_height_not_substitutable(context):
    rec = _run_all(context)[("R2_finished_height", "CTRL-SLABONLY")]
    assert rec.status is CheckStatus.NEEDS_REVIEW
    assert any(ReasonCode.DEFINITION_MISMATCH.value in r for r in rec.review_reasons)
    assert "finished_ceiling_height_m" not in rec.observed


def test_rejected_observation_is_kept_in_audit_trail(context):
    # the slab height was SEEN (with provenance) but must not enter judgment
    rec = _run_all(context)[("R2_finished_height", "CTRL-SLABONLY")]
    assert rec.rejected_observations, "slab height should be preserved for audit"
    rej = rec.rejected_observations[0]
    assert rej["field_name"] == "finished_ceiling_height_m"
    assert rej["provenance"]["property_path"] == "constructed_case.slab_height_m"
    assert rej["provenance"]["raw_value"] == 2.4
    # and it never leaked into the judged provenance
    assert "finished_ceiling_height_m" not in rec.input_provenance


def test_r2_not_applicable_is_not_pass(context):
    rec = _run_all(context)[("R2_finished_height", "3$f2p7VyLB7eox67SA_zKE")]
    assert rec.status is CheckStatus.NOT_APPLICABLE


# ------------------------------------------------------------------ R1 (pass/fail/review)

def test_r1_real_habitation_routes_to_review_missing_glazing_fraction(context):
    # Real bedroom: windows exist and floor area is read, but glass area cannot be
    # derived (GlazingAreaFraction absent) -> review, never pass/fail.
    rec = _run_all(context)[("R1_glazing_ratio", "347jFE2yX7IhCEIALmupEH")]
    assert rec.applicability is Applicability.APPLICABLE
    assert rec.status is CheckStatus.NEEDS_REVIEW
    assert rec.human_review_flag is True
    assert any(ReasonCode.MISSING_DATA.value in r for r in rec.review_reasons)
    assert any("GlazingAreaFraction" in r for r in rec.review_reasons)
    # floor area WAS read from the real model, with provenance
    assert "floor_area_m2" in rec.input_provenance
    assert rec.input_provenance["floor_area_m2"]["source_mode"] == "pinned_ifc"
    # but no glass area is ever emitted
    assert "glazing_area_m2" not in rec.observed


def test_r1_office_and_kitchen_are_in_scope(context):
    results = _run_all(context)
    for elem in ("2RSCzLOBz4FAK$_wE8VckM", "17JZcMFrf5tOftUTidA0d3"):
        rec = results[("R1_glazing_ratio", elem)]
        assert rec.applicability is Applicability.APPLICABLE
        assert rec.status is CheckStatus.NEEDS_REVIEW


def test_r1_relationship_unverified(context):
    rec = _run_all(context)[("R1_glazing_ratio", "CTRL-R1-NOWINDOW")]
    assert rec.status is CheckStatus.NEEDS_REVIEW
    assert any(ReasonCode.RELATIONSHIP_UNVERIFIED.value in r for r in rec.review_reasons)


def test_r1_constructed_pass_computes_ratio(context):
    rec = _run_all(context)[("R1_glazing_ratio", "CTRL-R1-PASS")]
    assert rec.status is CheckStatus.PASS
    assert rec.observed["ratio"] == pytest.approx(0.15)
    assert rec.gap == pytest.approx(0.05)


def test_r1_constructed_fail_computes_ratio(context):
    rec = _run_all(context)[("R1_glazing_ratio", "CTRL-R1-FAIL")]
    assert rec.status is CheckStatus.FAIL
    assert rec.observed["ratio"] == pytest.approx(0.075)


def test_r1_threshold_equality_is_pass(context):
    rec = _run_all(context)[("R1_glazing_ratio", "CTRL-R1-EQ")]
    assert rec.status is CheckStatus.PASS
    assert rec.observed["ratio"] == pytest.approx(0.10)


def test_r1_covers_pass_fail_and_review(context):
    results = _run_all(context)
    r1_statuses = {rec.status for (rid, _), rec in results.items() if rid == "R1_glazing_ratio"}
    assert {CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.NEEDS_REVIEW} <= r1_statuses


def test_ratio_helper_is_correct():
    assert evaluate_ratio_minimum(2.0, 20.0, 0.10)[0] is CheckStatus.PASS
    assert evaluate_ratio_minimum(1.5, 20.0, 0.10)[0] is CheckStatus.FAIL


# ------------------------------------------------------------------ units

def test_to_si_converts_safe_non_si_without_fault():
    # length + area, non-SI but safely convertible -> no reason code
    v, unit, code, _ = to_si(2600, "mm", "length")
    assert code is None and unit == "m" and v == pytest.approx(2.6)
    v, unit, code, _ = to_si(30000, "cm2", "area")
    assert code is None and unit == "m2" and v == pytest.approx(3.0)
    # SI passthrough
    assert to_si(2.5, "m", "length")[0] == pytest.approx(2.5)


def test_to_si_flags_only_genuine_unit_faults():
    assert to_si(2.5, None, "length")[2] is ReasonCode.UNIT_MISMATCH        # missing
    assert to_si(2.5, "cubit", "length")[2] is ReasonCode.UNIT_MISMATCH     # unknown
    assert to_si(2.5, "m2", "length")[2] is ReasonCode.UNIT_MISMATCH        # dimension
    assert to_si(3.0, "m", "area")[2] is ReasonCode.UNIT_MISMATCH           # dimension
    # a faulted conversion never yields a usable value
    assert to_si(2.5, "cubit", "length")[0] is None


def test_constructed_area_raw_unit_is_m2_not_m(context):
    # regression for the item-1 bug: area observations must not label raw_unit "m"
    rec = _run_all(context)[("R1_glazing_ratio", "CTRL-R1-PASS")]
    prov = rec.input_provenance["glazing_area_m2"]
    assert prov["raw_unit"] == "m2"
    assert prov["unit_si"] == "m2"


def test_convertible_non_si_cases_are_judged_not_flagged(context):
    results = _run_all(context)
    mm = results[("R2_finished_height", "CTRL-R2-MM")]
    assert mm.status is CheckStatus.PASS
    assert mm.observed["finished_ceiling_height_m"] == pytest.approx(2.6)
    assert mm.input_provenance["finished_ceiling_height_m"]["raw_unit"] == "mm"
    assert not any(ReasonCode.UNIT_MISMATCH.value in r for r in mm.review_reasons)

    cm2 = results[("R1_glazing_ratio", "CTRL-R1-CM2")]
    assert cm2.status is CheckStatus.PASS
    assert cm2.observed["glazing_area_m2"] == pytest.approx(3.0)


@pytest.mark.parametrize(
    "element_id",
    ["CTRL-UNIT-MISSING", "CTRL-UNIT-UNKNOWN", "CTRL-UNIT-DIM"],
)
def test_unit_fault_cases_route_to_review_with_unit_mismatch(context, element_id):
    rec = _run_all(context)[("R2_finished_height", element_id)]
    assert rec.status is CheckStatus.NEEDS_REVIEW
    assert rec.human_review_flag is True
    assert any(ReasonCode.UNIT_MISMATCH.value in r for r in rec.review_reasons)
    # the bad value is preserved for audit, never coerced into the judged provenance
    assert "finished_ceiling_height_m" not in rec.input_provenance
    assert any(o["field_name"] == "finished_ceiling_height_m" for o in rec.rejected_observations)


# ------------------------------------------------------------------ source integrity

def test_source_integrity_ok(context):
    sources, rules, _, _ = context
    for rule in rules.values():
        ok, code, _ = verify_source_integrity(rule, sources)
        assert ok and code is None, rule.rule_id


def test_unknown_source_id_routes_to_review_gracefully(context):
    # regression for the deleted eager `sources[rule.source_id]`: an unknown source_id
    # must degrade to SOURCE_INTEGRITY_FAILURE review, NOT raise KeyError.
    sources, rules, model, cases = context
    bogus = rules["R2_finished_height"].model_copy(update={"source_id": "NON_EXISTENT_SOURCE"})
    pass_case = next(c for c in cases if c["element_id"] == "347jFE2yX7IhCEIALmupEH")
    rec = run_check(pass_case, bogus, sources, model)  # must not raise
    assert rec.status is CheckStatus.NEEDS_REVIEW
    assert rec.source_integrity_verified is False
    assert rec.human_review_flag is True


def test_source_integrity_fault_injection_blocks_hard_judgment(context):
    sources, rules, model, cases = context
    rule = rules["R2_finished_height"]
    tampered = {k: v.model_copy(deep=True) for k, v in sources.items()}
    tampered[rule.source_id].excerpt += " TAMPERED"
    ok, code, _ = verify_source_integrity(rule, tampered)
    assert not ok and code is ReasonCode.SOURCE_INTEGRITY_FAILURE
    pass_case = next(c for c in cases if c["element_id"] == "347jFE2yX7IhCEIALmupEH")
    rec = run_check(pass_case, rule, tampered, model)
    assert rec.status is CheckStatus.NEEDS_REVIEW
    assert rec.source_integrity_verified is False


def test_excerpt_hashes_are_stable():
    sources = load_sources(MANIFEST)
    for src in sources.values():
        assert excerpt_sha256(src.excerpt) == src.excerpt_sha256, src.source_id


# ------------------------------------------------------------------ CLI

def test_cli_smoke(tmp_path):
    records = run_pipeline(
        str(MANIFEST), str(RULES), str(FIXTURE), str(CASES), str(tmp_path), run_id="test-run"
    )
    assert len(records) == 22
    assert (tmp_path / "evidence_records.json").exists()
    assert (tmp_path / "report.md").exists()


# ------------------------------------------------------------------ evaluation harness

def test_evaluation_harness_scores_gold_perfectly(context):
    sources, rules, model, cases = context
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    m = evaluate(cases, rules, sources, model, gold)
    assert m["mismatches"] == []
    assert m["outcome_accuracy"] == 1.0
    assert m["applicability_accuracy"] == 1.0
    assert m["review"]["precision"] == 1.0
    assert m["review"]["recall"] == 1.0
    # design guardrail: enough review positives to make precision/recall meaningful
    assert m["review"]["positives_in_gold"] >= 3
    # UNIT_MISMATCH is now exercised by the live cases
    assert "UNIT_MISMATCH" in m["reason_code_coverage"]["hit"]
    # SOURCE_INTEGRITY_FAILURE remains covered by fault-injection tests, not the case set
    assert "SOURCE_INTEGRITY_FAILURE" in m["reason_code_coverage"]["missing"]
