"""Objets du domaine Runtime Security."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class SecurityActionType(str, Enum):
    SHELL = "shell"
    GIT = "git"
    FILESYSTEM = "filesystem"
    MCP = "mcp"
    NETWORK = "network"
    TOOL = "tool"


class SecurityDecisionType(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class EnforcementMode(str, Enum):
    ENFORCE = "enforce"
    AUDIT_ONLY = "audit_only"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SecurityAction:
    action_type: SecurityActionType
    framework: str
    session_id: str | None = None
    turn_id: str | None = None
    tool: str | None = None
    command: str | None = None
    resource: str | None = None
    mcp_server: str | None = None
    cwd: str | None = None


@dataclass(frozen=True)
class RuleMatch:
    commands: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    mcp_servers: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecurityRule:
    identifier: str
    action_type: SecurityActionType
    decision: SecurityDecisionType
    match: RuleMatch
    reason: str
    risk_level: RiskLevel


@dataclass(frozen=True)
class SecurityDecision:
    action: SecurityAction
    decision: SecurityDecisionType
    enforcement_mode: EnforcementMode
    policy: str = "pathtrace.security"
    rule_id: str | None = None
    reason: str = "No matching security rule"
    risk_level: RiskLevel = RiskLevel.LOW
    approval_status: str | None = None
    enforcement_result: str | None = None

    def with_enforcement(
        self,
        *,
        result: str,
        approval_status: str | None = None,
    ) -> SecurityDecision:
        return replace(
            self,
            enforcement_result=result,
            approval_status=approval_status,
        )
