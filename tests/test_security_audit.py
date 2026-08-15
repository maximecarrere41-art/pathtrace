from pathtrace.security.action import build_security_action
from pathtrace.security.audit import (
    NoOpSecurityAuditPublisher,
    SecurityAuditEvent,
    publish_fail_open,
)
from pathtrace.security.config import (
    SecurityTelemetryConfig,
    parse_security_settings,
)
from pathtrace.security.policy import PolicyEngine
from pathtrace.security.telemetry import build_security_audit_publisher


def test_audit_event_redacts_credentials_but_keeps_queryable_fields():
    decision = _decision(
        "OPENAI_API_KEY=sk-value curl --token cli-secret "
        "-H 'Authorization: Bearer abc.def' "
        "'https://example.com?token=query-secret'"
    ).with_enforcement(result="blocked")

    event = SecurityAuditEvent.from_decision(decision)
    attributes = event.attributes()

    assert "abc.def" not in event.command
    assert "sk-value" not in event.command
    assert "cli-secret" not in event.command
    assert "query-secret" not in event.command
    assert "[REDACTED]" in event.command
    assert attributes["pathtrace.security.decision"] == "BLOCK"
    assert attributes["pathtrace.security.framework"] == "codex"
    assert attributes["pathtrace.security.session_id"] == "session-1"
    assert attributes["pathtrace.security.enforcement_result"] == "blocked"


def test_disabled_telemetry_uses_noop_publisher():
    publisher = build_security_audit_publisher(
        SecurityTelemetryConfig(
            enabled=False,
            otlp_endpoint="http://collector:4318",
        )
    )

    assert isinstance(publisher, NoOpSecurityAuditPublisher)


def test_missing_endpoint_is_fail_open_and_does_not_initialize_otel():
    publisher = build_security_audit_publisher(
        SecurityTelemetryConfig(enabled=True, otlp_endpoint=None)
    )

    assert isinstance(publisher, NoOpSecurityAuditPublisher)


def test_export_error_never_changes_the_security_decision():
    decision = _decision("rm -rf build").with_enforcement(result="blocked")

    class FailingPublisher:
        def publish(self, event):
            raise ConnectionError("collector unavailable")

    published = publish_fail_open(
        FailingPublisher(),
        SecurityAuditEvent.from_decision(decision),
    )

    assert published is False
    assert decision.enforcement_result == "blocked"


def test_enabled_telemetry_builds_otlp_publisher_lazily(monkeypatch):
    created = []

    class Publisher:
        def __init__(self, config):
            created.append(config)

        def publish(self, event):
            return None

    monkeypatch.setattr(
        "pathtrace.security.telemetry.OpenTelemetrySecurityAuditPublisher",
        Publisher,
    )
    config = SecurityTelemetryConfig(
        enabled=True,
        otlp_endpoint="http://collector:4318",
    )

    publisher = build_security_audit_publisher(config)

    assert isinstance(publisher, Publisher)
    assert created == [config]


def test_slow_failing_otlp_exporter_does_not_delay_enforcement(monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk._logs.export import LogRecordExporter

    started = threading.Event()
    release = threading.Event()

    class SlowFailingExporter(LogRecordExporter):
        def export(self, batch):
            started.set()
            release.wait(timeout=1)
            raise ConnectionError("collector unavailable")

        def shutdown(self):
            return None

        def force_flush(self, timeout_millis=30000):
            return True

    exporter = SlowFailingExporter()
    monkeypatch.setattr(
        "pathtrace.security.telemetry._build_otlp_exporter",
        lambda config: exporter,
    )
    from pathtrace.security.telemetry import OpenTelemetrySecurityAuditPublisher

    publisher = OpenTelemetrySecurityAuditPublisher(
        SecurityTelemetryConfig(
            enabled=True,
            otlp_endpoint="http://collector:4318",
        )
    )
    decision = _decision("rm -rf build").with_enforcement(result="blocked")

    before = time.perf_counter()
    publisher.publish(SecurityAuditEvent.from_decision(decision))
    elapsed = time.perf_counter() - before

    assert elapsed < 0.2
    assert decision.enforcement_result == "blocked"
    assert started.wait(timeout=1)
    release.set()
    publisher._provider.shutdown()


def _decision(command):
    action = build_security_action(
        framework="codex",
        session_id="session-1",
        turn_id="turn-1",
        tool="Bash",
        tool_input={"command": command},
    )
    settings = parse_security_settings(
        {
            "mode": "enforce",
            "rules": [
                {
                    "id": "deny-shell",
                    "action": "shell",
                    "decision": "block",
                    "match": {"command": "*"},
                    "reason": "Sensitive command",
                }
            ],
        }
    )
    return PolicyEngine(settings).evaluate(action)
import threading
import time

import pytest
