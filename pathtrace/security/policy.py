"""Évaluation déterministe des règles Runtime Security."""

from __future__ import annotations

from collections.abc import Callable
from fnmatch import fnmatchcase

from pathtrace.security.action import (
    canonicalize_filesystem_path,
    canonicalize_git_command,
)
from pathtrace.security.config import SecuritySettings
from pathtrace.security.model import (
    SecurityAction,
    SecurityActionType,
    SecurityDecision,
    SecurityDecisionType,
    SecurityRule,
)


DECISION_PRIORITY = {
    SecurityDecisionType.ALLOW: 1,
    SecurityDecisionType.REQUIRE_APPROVAL: 2,
    SecurityDecisionType.BLOCK: 3,
}


class PolicyEngine:
    def __init__(self, settings: SecuritySettings) -> None:
        self.settings = settings

    def evaluate(self, action: SecurityAction) -> SecurityDecision:
        matching = [rule for rule in self.settings.rules if _matches(rule, action)]
        if not matching:
            return SecurityDecision(
                action=action,
                decision=SecurityDecisionType.ALLOW,
                enforcement_mode=self.settings.mode,
            )
        selected = min(
            matching,
            key=lambda rule: (-DECISION_PRIORITY[rule.decision], rule.identifier),
        )
        return SecurityDecision(
            action=action,
            decision=selected.decision,
            enforcement_mode=self.settings.mode,
            rule_id=selected.identifier,
            reason=selected.reason,
            risk_level=selected.risk_level,
        )


def _matches(rule: SecurityRule, action: SecurityAction) -> bool:
    if rule.action_type is not action.action_type:
        return False
    filesystem = action.action_type is SecurityActionType.FILESYSTEM
    git = action.action_type is SecurityActionType.GIT
    checks = (
        _field_matches(
            rule.match.commands,
            action.command,
            normalizer=(
                lambda value: canonicalize_git_command(value, action.cwd)
                if git
                else value
            ),
        ),
        _field_matches(
            rule.match.resources,
            action.resource,
            normalizer=(
                lambda value: canonicalize_filesystem_path(value, action.cwd)
                if filesystem
                else value
            ),
        ),
        _field_matches(rule.match.tools, action.tool),
        _field_matches(rule.match.mcp_servers, action.mcp_server),
    )
    return all(check is not False for check in checks)


def _field_matches(
    patterns: tuple[str, ...],
    value: str | None,
    *,
    normalizer: Callable[[str], str] | None = None,
) -> bool | None:
    if not patterns:
        return None
    if value is None:
        return False
    if normalizer is not None:
        patterns = tuple(normalizer(pattern) for pattern in patterns)
        value = normalizer(value)
    return any(fnmatchcase(value, pattern) for pattern in patterns)
