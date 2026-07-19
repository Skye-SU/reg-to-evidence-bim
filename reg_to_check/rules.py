"""Load normalized rules from rules.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import RuleObject


def load_rules(rules_path: str | Path) -> dict[str, RuleObject]:
    data = yaml.safe_load(Path(rules_path).read_text(encoding="utf-8"))
    rules: dict[str, RuleObject] = {}
    for raw in data.get("rules", []):
        rule = RuleObject(**raw)
        rules[rule.rule_id] = rule
    return rules
