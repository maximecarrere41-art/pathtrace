"""Pipeline partagé Observe et Runtime Security pour un hook fournisseur."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pathtrace.adapters.base import FrameworkAdapter
from pathtrace.config import (
    CONFIG_PATH,
    Feature,
    ProjectConfigError,
    load_project_config,
)
from pathtrace.security.audit import SecurityAuditEvent, publish_fail_open
from pathtrace.security.config import (
    SecurityTelemetryConfig,
    parse_security_settings,
)
from pathtrace.security.model import (
    EnforcementMode,
    RiskLevel,
    SecurityAction,
    SecurityActionType,
    SecurityDecision,
    SecurityDecisionType,
)
from pathtrace.security.policy import PolicyEngine
from pathtrace.security.telemetry import build_security_audit_publisher


@dataclass(frozen=True)
class HookPipelineResult:
    response: dict[str, Any] | None = None
    trace_path: Path | None = None


def process_hook(
    adapter: FrameworkAdapter,
    event_slug: str,
    payload: dict[str, Any],
    project_dir: Path,
    *,
    configured_only: bool = False,
    security_installed: bool = False,
) -> HookPipelineResult:
    framework = getattr(adapter, "name", "unknown")
    try:
        config = load_project_config(project_dir)
    except ProjectConfigError as error:
        if event_slug == "pre-tool-use" and _must_fail_closed_for_invalid_config(
            project_dir,
            framework,
            configured_only,
            security_installed,
        ):
            return HookPipelineResult(
                response=_enforce_failure(adapter, payload, error)
            )
        raise
    if configured_only and not config.explicit:
        return HookPipelineResult()
    response = None
    features = config.features_for(framework)

    if event_slug == "pre-tool-use" and Feature.SECURITY in features:
        action = _fallback_action(adapter, payload)
        settings = None
        try:
            action = adapter.to_security_action(payload)
            settings = parse_security_settings(config.security)
            decision = PolicyEngine(settings).evaluate(action)
        except Exception as error:
            if _configured_mode(config.security) is EnforcementMode.AUDIT_ONLY:
                decision = None
            else:
                decision = _failure_decision(action, error)

        if decision is not None and (
            settings is not None
            and settings.mode is EnforcementMode.AUDIT_ONLY
        ):
            approval = (
                "not_requested_audit_only"
                if decision.decision is SecurityDecisionType.REQUIRE_APPROVAL
                else None
            )
            decision = decision.with_enforcement(
                result="allowed_audit_only",
                approval_status=approval,
            )
        elif decision is not None:
            enforcement = adapter.enforce_security(decision)
            response = enforcement.response
            decision = decision.with_enforcement(
                result=enforcement.result,
                approval_status=enforcement.approval_status,
            )
        if decision is not None:
            telemetry = (
                settings.telemetry
                if settings is not None
                else _telemetry_from_invalid_config(config.security)
            )
            _publish_decision(telemetry, decision)

    trace_path = None
    if Feature.OBSERVE in features:
        trace_path = adapter.handle(event_slug, payload, project_dir)
    return HookPipelineResult(response=response, trace_path=trace_path)


def _failure_decision(
    action: SecurityAction,
    error: Exception,
) -> SecurityDecision:
    return SecurityDecision(
        action=action,
        decision=SecurityDecisionType.BLOCK,
        enforcement_mode=EnforcementMode.ENFORCE,
        policy="pathtrace.security.fail_closed",
        rule_id="pathtrace-security-evaluation-error",
        reason=(
            "Security policy evaluation failed; action blocked fail-closed "
            f"({type(error).__name__})."
        ),
        risk_level=RiskLevel.CRITICAL,
    )


def _enforce_failure(
    adapter: FrameworkAdapter,
    payload: dict[str, Any],
    error: Exception,
) -> dict[str, Any] | None:
    decision = _failure_decision(_fallback_action(adapter, payload), error)
    enforcement = adapter.enforce_security(decision)
    return enforcement.response


def _fallback_action(
    adapter: FrameworkAdapter,
    payload: dict[str, Any],
) -> SecurityAction:
    return SecurityAction(
        action_type=SecurityActionType.TOOL,
        framework=getattr(adapter, "name", "unknown"),
        session_id=_text(payload, "session_id", "sessionId"),
        turn_id=_text(payload, "turn_id", "turnId"),
        tool=_text(payload, "tool_name", "toolName", "name"),
        cwd=_text(payload, "cwd", "working_directory", "workingDirectory"),
    )


def _configured_mode(raw_security: Any) -> EnforcementMode:
    if (
        isinstance(raw_security, dict)
        and raw_security.get("mode") == EnforcementMode.AUDIT_ONLY.value
    ):
        return EnforcementMode.AUDIT_ONLY
    return EnforcementMode.ENFORCE


def _telemetry_from_invalid_config(raw_security: Any) -> SecurityTelemetryConfig:
    if not isinstance(raw_security, dict):
        return SecurityTelemetryConfig()
    try:
        return parse_security_settings(
            {"telemetry": raw_security.get("telemetry", {})}
        ).telemetry
    except Exception:
        return SecurityTelemetryConfig()


def _publish_decision(
    telemetry: SecurityTelemetryConfig,
    decision: SecurityDecision,
) -> None:
    try:
        publisher = build_security_audit_publisher(telemetry)
        publish_fail_open(publisher, SecurityAuditEvent.from_decision(decision))
    except Exception:
        return


def _must_fail_closed_for_invalid_config(
    project_dir: Path,
    framework: str,
    configured_only: bool,
    security_installed: bool,
) -> bool:
    path = project_dir / CONFIG_PATH
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return path.is_file() and (configured_only or security_installed)
    if not isinstance(value, dict):
        return False
    frameworks = value.get("frameworks")
    if isinstance(frameworks, dict):
        features = frameworks.get(framework)
    else:
        features = value.get("features")
    if not isinstance(features, list) or Feature.SECURITY.value not in features:
        return False
    return _configured_mode(value.get("security")) is EnforcementMode.ENFORCE


def _text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None
