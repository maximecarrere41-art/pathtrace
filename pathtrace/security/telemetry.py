"""Transport OpenTelemetry optionnel pour les événements Security."""

from __future__ import annotations

from pathtrace.security.audit import (
    NoOpSecurityAuditPublisher,
    SecurityAuditEvent,
    SecurityAuditPublisher,
)
from pathtrace.security.config import SecurityTelemetryConfig


class OpenTelemetrySecurityAuditPublisher:
    """Émet des logs OTLP sans configurer de spans Pathtrace historiques."""

    def __init__(self, config: SecurityTelemetryConfig) -> None:
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.resources import Resource

        exporter = _build_otlp_exporter(config)
        self._provider = LoggerProvider(
            resource=Resource.create({"service.name": "pathtrace-security"})
        )
        self._provider.add_log_record_processor(
            BatchLogRecordProcessor(
                exporter,
                max_queue_size=128,
                max_export_batch_size=1,
                schedule_delay_millis=100,
                export_timeout_millis=500,
            )
        )
        self._logger = self._provider.get_logger("pathtrace.security")

    def publish(self, event: SecurityAuditEvent) -> None:
        self._logger.emit(
            body="pathtrace.security.decision",
            severity_text="INFO",
            attributes=event.attributes(),
        )


def build_security_audit_publisher(
    config: SecurityTelemetryConfig,
) -> SecurityAuditPublisher:
    if not config.enabled or not config.otlp_endpoint:
        return NoOpSecurityAuditPublisher()
    try:
        return OpenTelemetrySecurityAuditPublisher(config)
    except Exception:
        return NoOpSecurityAuditPublisher()


def _logs_endpoint(endpoint: str) -> str:
    normalized = endpoint.rstrip("/")
    return normalized if normalized.endswith("/v1/logs") else f"{normalized}/v1/logs"


def _build_otlp_exporter(config: SecurityTelemetryConfig):
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

    return OTLPLogExporter(
        endpoint=_logs_endpoint(config.otlp_endpoint or ""),
        headers=dict(config.headers),
        timeout=0.5,
    )
