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
    ProjectConfig,
    load_project_config,
)
from pathtrace.security.audit import SecurityAuditEvent, publish_fail_open
from pathtrace.security.config import (
    SecurityTelemetryConfig,
    SecurityConfigError,
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
from pathtrace.security.sources import SecuritySource, security_sources, provider_source
from pathtrace.hooks.security import evaluate_source, enforce_sources, audited_decision
from pathtrace.provider_paths import provider_security_path
from pathtrace.security.telemetry import build_security_audit_publisher


@dataclass(frozen=True)
class HookPipelineResult:
    response: dict[str, Any] | None = None
    trace_path: Path | None = None


def process_hook(adapter: FrameworkAdapter, event_slug: str, payload: dict[str, Any],
                 project_dir: Path, *, configured_only: bool = False,
                 security_installed: bool = False) -> HookPipelineResult:
    try:
        return _process_hook(adapter, event_slug, payload, project_dir,
                             configured_only, security_installed)
    except SecurityConfigError as error:
        if event_slug == "pre-tool-use":
            return HookPipelineResult(response=_enforce_failure(adapter, payload, error.__cause__ or error))
        raise


def _load_hook_config(project_dir: Path, framework: str, configured_only: bool,
                      security_installed: bool) -> ProjectConfig:
    try:
        return load_project_config(project_dir)
    except ProjectConfigError as error:
        if _must_fail_closed_for_invalid_config(project_dir, framework,
                                               configured_only, security_installed):
            raise SecurityConfigError(str(error)) from error
        if provider_source(framework):
            return ProjectConfig(frozenset(), explicit=False)
        raise


def _process_hook(adapter: FrameworkAdapter, event_slug: str, payload: dict[str, Any],
                  project_dir: Path, configured_only: bool, installed: bool) -> HookPipelineResult:
    framework = getattr(adapter, "name", "unknown")
    config = _load_hook_config(project_dir, framework, configured_only, installed)
    sources = security_sources(framework, config) if event_slug == "pre-tool-use" else []
    response = _security_response(adapter, payload, sources) if event_slug == "pre-tool-use" else None
    observe = _observe_enabled(config, framework, configured_only)
    trace = adapter.handle(event_slug, payload, project_dir) if observe else None
    return HookPipelineResult(response=response, trace_path=trace)


def _observe_enabled(config: ProjectConfig, framework: str, configured_only: bool) -> bool:
    provider_configured = framework != "unknown" and provider_security_path(framework).is_file()
    if not config.explicit and (configured_only or provider_configured):
        return False
    return Feature.OBSERVE in config.features_for(framework)


def _security_response(adapter: FrameworkAdapter, payload: dict[str, Any],
                       sources: list[SecuritySource]) -> dict[str, Any] | None:
    failure = lambda error: _failure_decision(_fallback_action(adapter, payload), error)
    evaluated = [(s, evaluate_source(adapter, payload, s, failure)) for s in sources]
    decisions = [d for _, d in evaluated if d is not None]
    response, enforcement = enforce_sources(adapter, decisions)
    for source, decision in evaluated:
        if decision is not None:
            _publish_decision(_telemetry_from_invalid_config(source.raw),
                              audited_decision(decision, enforcement))
    return response


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
    return True


def _text(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None
