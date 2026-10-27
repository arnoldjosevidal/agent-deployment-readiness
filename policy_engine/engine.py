"""Pure, deterministic tool authorization. No model calls or side effects."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping
import json


class Decision(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    rule_id: str
    reason: str


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    tool_name: str
    decision: Decision
    # Each entry requires an exact argument value. Extra arguments are rejected.
    exact_args: Mapping[str, Any] = field(default_factory=dict)
    # Explicit authorized context facts, e.g. {"task_scope": "calendar_read"}.
    required_context: Mapping[str, Any] = field(default_factory=dict)


class PolicyEngine:
    """Explicit allow/approval rules, exact matching, deny by default.

    BLOCK rules take precedence over other matching rules. Conflicting rules
    fail closed. Approval is never interpreted as an execution grant.
    """

    def __init__(self, rules: list[PolicyRule] | tuple[PolicyRule, ...] = ()) -> None:
        ids = [r.rule_id for r in rules]
        if len(ids) != len(set(ids)) or any(not x for x in ids):
            raise ValueError("Rule IDs must be unique and nonempty")
        if any(not r.tool_name for r in rules):
            raise ValueError("Tool names must be nonempty")
        self.rules = tuple(rules)

    @staticmethod
    def _same(a: Any, b: Any) -> bool:
        try:
            return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            return False

    def evaluate(self, tool_name: str, args: Any, context: Any = None) -> Verdict:
        if not isinstance(tool_name, str) or not tool_name:
            return Verdict(Decision.BLOCK, "INVALID_TOOL", "Missing tool name")
        if not isinstance(args, dict) or not all(isinstance(k, str) for k in args):
            return Verdict(Decision.BLOCK, "INVALID_ARGS", "Arguments must be an object with string keys")
        if not isinstance(context, dict):
            context = {}
        matched = []
        for rule in self.rules:
            if rule.tool_name != tool_name:
                continue
            # Reject extra arguments; prevents smuggling new destinations or options.
            if set(args) != set(rule.exact_args):
                continue
            if not all(self._same(args[k], v) for k, v in rule.exact_args.items()):
                continue
            if not all(k in context and self._same(context[k], v) for k, v in rule.required_context.items()):
                continue
            matched.append(rule)
        if not matched:
            return Verdict(Decision.BLOCK, "DEFAULT_DENY", "No exact authorized rule")
        for rule in matched:
            if rule.decision == Decision.BLOCK:
                return Verdict(Decision.BLOCK, rule.rule_id, "Explicit deny rule")
        if any(r.decision != matched[0].decision for r in matched):
            return Verdict(Decision.BLOCK, "CONFLICT", "Conflicting authorization rules")
        rule = matched[0]
        return Verdict(rule.decision, rule.rule_id, "Exact rule matched")
