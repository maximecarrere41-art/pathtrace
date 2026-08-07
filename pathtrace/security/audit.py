"""Événements d'audit issus exclusivement des décisions Security."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from pathtrace.model import utc_now
from pathtrace.security.model import SecurityDecision


SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z0-9_.-]*"
    r"(?:api[_-]?key|access[_-]?token|token|password|passwd|secret|authorization)"
    r"[A-Za-z0-9_.-]*)"
    r"(\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s&]+)"
)
SENSITIVE_FLAG = re.compile(
    r"(?i)(--(?:api[_-]?key|access[_-]?token|token|password|secret)\s+)\S+"
)
BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
SENSITIVE_QUERY = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|password|secret)=)[^&#\s]+"
)


class SecurityAuditPublisher(Protocol):
    def publish(self, event: SecurityAuditEvent) -> None:
        """Publie un événement de décision Security."""


@dataclass(frozen=True)
class SecurityAuditEvent:
    timestamp: str
    framework: str
    session_id: str | None
    turn_id: str | None
    action_type: str
    tool: str | None
    mcp_server: str | None
    command: str | None
    resource: str | None
    decision: str
    enforcement_mode: str
    policy: str
    rule_id: str | None
    reason: str
    risk_level: str
    approval_status: str | None
    enforcement_result: str | None

    @classmethod
    def from_decision(cls, decision: SecurityDecision) -> SecurityAuditEvent:
        action = decision.action
        return cls(
            timestamp=utc_now(),
            framework=action.framework,
            session_id=action.session_id,
            turn_id=action.turn_id,
            action_type=action.action_type.value,
            tool=action.tool,
            mcp_server=action.mcp_server,
            command=redact(action.command),
            resource=redact(action.resource),
            decision=decision.decision.value,
            enforcement_mode=decision.enforcement_mode.value,
            policy=decision.policy,
            rule_id=decision.rule_id,
            reason=redact(decision.reason) or "",
            risk_level=decision.risk_level.value,
            approval_status=decision.approval_status,
            enforcement_result=decision.enforcement_result,
        )

    def attributes(self) -> dict[str, str]:
        values = {
            "pathtrace.security.framework": self.framework,
            "pathtrace.security.session_id": self.session_id,
            "pathtrace.security.turn_id": self.turn_id,
            "pathtrace.security.action_type": self.action_type,
            "pathtrace.security.tool": self.tool,
            "pathtrace.security.mcp_server": self.mcp_server,
            "pathtrace.security.command": self.command,
            "pathtrace.security.resource": self.resource,
            "pathtrace.security.decision": self.decision,
            "pathtrace.security.enforcement_mode": self.enforcement_mode,
            "pathtrace.security.policy": self.policy,
            "pathtrace.security.rule_id": self.rule_id,
            "pathtrace.security.reason": self.reason,
            "pathtrace.security.risk_level": self.risk_level,
            "pathtrace.security.approval_status": self.approval_status,
            "pathtrace.security.enforcement_result": self.enforcement_result,
            "pathtrace.security.timestamp": self.timestamp,
        }
        return {key: value for key, value in values.items() if value is not None}


class NoOpSecurityAuditPublisher:
    def publish(self, event: SecurityAuditEvent) -> None:
        return None


def publish_fail_open(
    publisher: SecurityAuditPublisher,
    event: SecurityAuditEvent,
) -> bool:
    try:
        publisher.publish(event)
    except Exception:
        return False
    return True


def redact(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = BEARER_TOKEN.sub("Bearer [REDACTED]", value)
    redacted = SENSITIVE_ASSIGNMENT.sub(r"\1\2[REDACTED]", redacted)
    redacted = SENSITIVE_FLAG.sub(r"\1[REDACTED]", redacted)
    return SENSITIVE_QUERY.sub(r"\1[REDACTED]", redacted)
