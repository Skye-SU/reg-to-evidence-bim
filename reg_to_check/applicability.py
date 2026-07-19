"""Applicability gate.

Runs BEFORE any threshold check. A rule only reaches the checker when it is
`applicable`. `unknown` legal use routes to review; `not_applicable` is not a pass.
The IFC `ObjectType` / room name is never treated as a legal use classification —
legal_space_use must be supplied explicitly (constructed annotation here).
"""

from __future__ import annotations

from .models import Applicability, CheckInput, ReasonCode, RuleObject


def decide_applicability(
    rule: RuleObject, ci: CheckInput
) -> tuple[Applicability, ReasonCode | None, str]:
    use = ci.legal_space_use

    if use is None:
        return (
            Applicability.UNKNOWN,
            ReasonCode.RULE_SCOPE_UNKNOWN,
            "legal_space_use not established; the model does not legally classify the room",
        )

    if use in rule.applies_to_legal_use:
        return Applicability.APPLICABLE, None, f"legal_space_use={use!r} is in scope"

    return (
        Applicability.NOT_APPLICABLE,
        None,
        f"legal_space_use={use!r} is outside Reg 24(1) scope {rule.applies_to_legal_use}",
    )
