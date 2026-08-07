"""Validation de la configuration Runtime Security."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pathtrace.security.model import (
    EnforcementMode,
    RiskLevel,
    RuleMatch,
    SecurityActionType,
    SecurityDecisionType,
    SecurityRule,
)


class SecurityConfigError(ValueError):
    """La section security de la configuration est invalide."""


@dataclass(frozen=True)
class SecurityTelemetryConfig:
    enabled: bool = False
    otlp_endpoint: str | None = None
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class SecuritySettings:
    mode: EnforcementMode
    rules: tuple[SecurityRule, ...]
    telemetry: SecurityTelemetryConfig


def parse_security_settings(raw: dict[str, Any] | None) -> SecuritySettings:
    value = raw or {}
    _reject_unknown(value, {"mode", "rules", "telemetry"}, "security")
    mode = _enum(EnforcementMode, value.get("mode", "enforce"), "security.mode")

    raw_rules = value.get("rules", [])
    if not isinstance(raw_rules, list):
        raise SecurityConfigError("security.rules doit être une liste")
    rules = tuple(_parse_rule(item, index) for index, item in enumerate(raw_rules))
    identifiers = [rule.identifier for rule in rules]
    if len(identifiers) != len(set(identifiers)):
        raise SecurityConfigError("security.rules contient des identifiants dupliqués")

    telemetry = _parse_telemetry(value.get("telemetry", {}))
    return SecuritySettings(mode=mode, rules=rules, telemetry=telemetry)


def _parse_rule(raw: Any, index: int) -> SecurityRule:
    prefix = f"security.rules[{index}]"
    if not isinstance(raw, dict):
        raise SecurityConfigError(f"{prefix} doit être un objet")
    _reject_unknown(
        raw,
        {"id", "action", "decision", "match", "reason", "risk_level"},
        prefix,
    )
    identifier = _required_text(raw.get("id"), f"{prefix}.id")
    action_type = _enum(SecurityActionType, raw.get("action"), f"{prefix}.action")
    decision = _decision(raw.get("decision"), f"{prefix}.decision")
    match = _parse_match(raw.get("match"), f"{prefix}.match")
    reason = _required_text(raw.get("reason"), f"{prefix}.reason")
    default_risk = {
        SecurityDecisionType.ALLOW: RiskLevel.LOW,
        SecurityDecisionType.REQUIRE_APPROVAL: RiskLevel.MEDIUM,
        SecurityDecisionType.BLOCK: RiskLevel.HIGH,
    }[decision]
    risk = _enum(
        RiskLevel,
        raw.get("risk_level", default_risk.value),
        f"{prefix}.risk_level",
    )
    return SecurityRule(
        identifier=identifier,
        action_type=action_type,
        decision=decision,
        match=match,
        reason=reason,
        risk_level=risk,
    )


def _parse_match(raw: Any, prefix: str) -> RuleMatch:
    if not isinstance(raw, dict):
        raise SecurityConfigError(f"{prefix} doit être un objet")
    _reject_unknown(raw, {"command", "resource", "tool", "mcp_server"}, prefix)
    match = RuleMatch(
        commands=_patterns(raw.get("command"), f"{prefix}.command"),
        resources=_patterns(raw.get("resource"), f"{prefix}.resource"),
        tools=_patterns(raw.get("tool"), f"{prefix}.tool"),
        mcp_servers=_patterns(raw.get("mcp_server"), f"{prefix}.mcp_server"),
    )
    if not any((match.commands, match.resources, match.tools, match.mcp_servers)):
        raise SecurityConfigError(f"{prefix} doit contenir au moins un pattern")
    return match


def _parse_telemetry(raw: Any) -> SecurityTelemetryConfig:
    if not isinstance(raw, dict):
        raise SecurityConfigError("security.telemetry doit être un objet")
    _reject_unknown(raw, {"enabled", "otlp_endpoint", "headers"}, "security.telemetry")
    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise SecurityConfigError("security.telemetry.enabled doit être un booléen")
    endpoint = raw.get("otlp_endpoint")
    if endpoint is not None:
        endpoint = _required_text(endpoint, "security.telemetry.otlp_endpoint")
    raw_headers = raw.get("headers", {})
    if not isinstance(raw_headers, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in raw_headers.items()
    ):
        raise SecurityConfigError("security.telemetry.headers doit contenir des chaînes")
    return SecurityTelemetryConfig(
        enabled=enabled,
        otlp_endpoint=endpoint,
        headers=tuple(sorted(raw_headers.items())),
    )


def _patterns(raw: Any, field: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, list) or not values or not all(
        isinstance(item, str) and item for item in values
    ):
        raise SecurityConfigError(f"{field} doit être une chaîne ou une liste non vide")
    return tuple(values)


def _decision(enum_value: Any, field: str) -> SecurityDecisionType:
    if isinstance(enum_value, str):
        enum_value = enum_value.upper()
    return _enum(SecurityDecisionType, enum_value, field)


def _enum(enum_type: type, value: Any, field: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        accepted = ", ".join(item.value for item in enum_type)
        raise SecurityConfigError(f"{field} accepte uniquement : {accepted}") from error


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SecurityConfigError(f"{field} doit être une chaîne non vide")
    return value.strip()


def _reject_unknown(raw: dict[str, Any], allowed: set[str], prefix: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        names = ", ".join(unknown)
        raise SecurityConfigError(
            f"{prefix} contient des propriétés inconnues : {names}"
        )
