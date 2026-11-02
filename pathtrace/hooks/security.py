from dataclasses import replace
from collections.abc import Callable, Sequence
from typing import Any

from pathtrace.adapters.base import FrameworkAdapter, SecurityEnforcement
from pathtrace.security.config import parse_security_settings
from pathtrace.security.model import SecurityDecision
from pathtrace.security.policy import DECISION_PRIORITY, PolicyEngine
from pathtrace.security.sources import SecuritySource


def evaluate_source(adapter: FrameworkAdapter, payload: dict[str, Any],
                    source: SecuritySource, failure: Callable[[Exception], SecurityDecision]) -> SecurityDecision:
    try:
        action = adapter.to_security_action(payload)
        decision = PolicyEngine(parse_security_settings(source.raw)).evaluate(action)
    except Exception as error:
        decision = failure(error)
    return replace(decision, policy=f"pathtrace.security.{source.scope}")


def enforce_sources(adapter: FrameworkAdapter, decisions: Sequence[SecurityDecision]
                    ) -> tuple[dict[str, Any] | None, SecurityEnforcement | None]:
    if not decisions:
        return None, None
    selected = max(decisions, key=lambda d: DECISION_PRIORITY[d.decision])
    enforcement = adapter.enforce_security(selected)
    return enforcement.response, enforcement


def audited_decision(decision: SecurityDecision,
                     enforcement: SecurityEnforcement | None) -> SecurityDecision:
    return decision.with_enforcement(result=enforcement.result,
                                     approval_status=enforcement.approval_status)
