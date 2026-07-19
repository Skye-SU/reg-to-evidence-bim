"""CLI entry point.

Examples:
  python -m reg_to_check run \
    --manifest sources/source_manifest.yaml --rules rules.yaml \
    --ifc data/fixtures/AC20-FZK-Haus.ifc --cases data/controlled_cases.json --out out/

  python -m reg_to_check evaluate \
    --manifest sources/source_manifest.yaml --rules rules.yaml \
    --ifc data/fixtures/AC20-FZK-Haus.ifc --cases data/controlled_cases.json \
    --gold data/gold_set.json --out out/

  python -m reg_to_check extract \
    --manifest sources/source_manifest.yaml --rules rules.yaml \
    --cache examples/cached_llm_response.json --out out/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .checker import run_check
from .evaluate import evaluate, render_eval_markdown
from .extractor import cached_extractor, render_extraction_markdown, run_extraction
from .ifc_reader import IFCModel
from .models import EvidenceRecord
from .report import render_markdown
from .rules import load_rules
from .sources import load_sources


def run_pipeline(
    manifest: str, rules_path: str, ifc: str | None, cases_path: str,
    out_dir: str, run_id: str = "demo-r2-001",
) -> list[EvidenceRecord]:
    sources = load_sources(manifest)
    rules = load_rules(rules_path)

    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    model = IFCModel(ifc) if ifc else None

    records: list[EvidenceRecord] = []
    for c in cases:
        for rule_id in c.get("rules", []):
            records.append(run_check(c, rules[rule_id], sources, model, run_id=run_id))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "evidence_records.json").write_text(
        json.dumps([r.model_dump(mode="json", exclude_none=True) for r in records], indent=2),
        encoding="utf-8",
    )
    (out / "report.md").write_text(
        render_markdown(records, fixture_sha256=model.model_sha256 if model else None),
        encoding="utf-8",
    )
    return records


def run_evaluation(
    manifest: str, rules_path: str, ifc: str | None, cases_path: str,
    gold_path: str, out_dir: str,
) -> dict:
    sources = load_sources(manifest)
    rules = load_rules(rules_path)
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    gold = json.loads(Path(gold_path).read_text(encoding="utf-8"))
    model = IFCModel(ifc) if ifc else None

    metrics = evaluate(cases, rules, sources, model, gold)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "eval_report.md").write_text(render_eval_markdown(metrics), encoding="utf-8")
    (out / "eval_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def run_rule_extraction(manifest: str, rules_path: str, cache: str, out_dir: str) -> list:
    sources = load_sources(manifest)
    rules = load_rules(rules_path)
    validations = run_extraction(sources, rules, cached_extractor(cache))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "extraction_report.md").write_text(
        render_extraction_markdown(validations), encoding="utf-8"
    )
    (out / "extraction_validations.json").write_text(
        json.dumps([v.model_dump(mode="json") for v in validations], indent=2),
        encoding="utf-8",
    )
    return validations


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--manifest", required=True)
    p.add_argument("--rules", required=True)
    p.add_argument("--ifc", default=None)
    p.add_argument("--cases", required=True)
    p.add_argument("--out", default="out")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reg-to-check", description="Auditable rule-to-BIM prototype.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the check pipeline and write records + report.")
    _add_common_args(run)
    run.add_argument("--run-id", default="demo-r2-001")

    ev = sub.add_parser("evaluate", help="Score predictions against the gold set.")
    _add_common_args(ev)
    ev.add_argument("--gold", required=True)

    ex = sub.add_parser(
        "extract", help="Validate LLM rule candidates (schema + span/hash + gold diff)."
    )
    ex.add_argument("--manifest", required=True)
    ex.add_argument("--rules", required=True)
    ex.add_argument("--cache", required=True, help="Cached extractor response JSON.")
    ex.add_argument("--out", default="out")

    args = parser.parse_args(argv)

    if args.command == "run":
        records = run_pipeline(
            args.manifest, args.rules, args.ifc, args.cases, args.out, run_id=args.run_id
        )
        counts: dict[str, int] = {}
        per_rule: dict[str, int] = {}
        for r in records:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
            per_rule[r.rule_id] = per_rule.get(r.rule_id, 0) + 1
        rules_str = ", ".join(f"{rid}={n}" for rid, n in sorted(per_rule.items()))
        print(f"[reg-to-check] {len(records)} checks ({rules_str}) -> {counts}")
        print(f"[reg-to-check] wrote {args.out}/evidence_records.json and {args.out}/report.md")
        return 0

    if args.command == "evaluate":
        m = run_evaluation(
            args.manifest, args.rules, args.ifc, args.cases, args.gold, args.out
        )
        rv = m["review"]
        print(
            f"[reg-to-check] evaluate: outcome {m['outcome_correct']}/{m['n_gold']}, "
            f"review precision={rv['precision']} recall={rv['recall']}, "
            f"mismatches={len(m['mismatches'])}"
        )
        print(f"[reg-to-check] wrote {args.out}/eval_report.md and {args.out}/eval_metrics.json")
        return 0

    if args.command == "extract":
        validations = run_rule_extraction(args.manifest, args.rules, args.cache, args.out)
        accepted = sum(v.accepted for v in validations)
        print(
            f"[reg-to-check] extract: {accepted}/{len(validations)} candidates accepted "
            f"(schema + span/hash + gold diff)"
        )
        print(f"[reg-to-check] wrote {args.out}/extraction_report.md and {args.out}/extraction_validations.json")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
