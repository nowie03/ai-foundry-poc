"""
OpenTelemetry bootstrap for the Azure AI Foundry harness.

Call setup_telemetry(config) in each script before any client construction.
Call setup_telemetry_from_env(service_name=...) in standalone processes (local_mcp).

If no OTEL endpoint is configured, both functions are no-ops — developers
without a collector are unaffected and zero OTEL overhead is incurred.
"""
from __future__ import annotations

import atexit
import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import HarnessConfig

logger = logging.getLogger(__name__)


def setup_telemetry(config: HarnessConfig) -> None:
    """Configure OTEL tracing and logging from a loaded HarnessConfig."""
    _apply(
        endpoint=config.otel_endpoint,
        service_name=config.otel_service_name,
        content_recording=config.otel_content_recording,
        bearer_token=config.otel_bearer_token,
        log_level=config.otel_log_level,
    )


def setup_telemetry_from_env(*, service_name: str) -> None:
    """Configure OTEL tracing and logging by reading env vars directly.

    service_name is always used as-is and is NOT overridden by OTEL_SERVICE_NAME,
    so standalone processes (e.g. local_mcp) keep their own identity regardless
    of what .env sets for the main harness.
    """
    _apply(
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or None,
        service_name=service_name,
        content_recording=os.environ.get("OTEL_CAPTURE_CONTENT", "false").lower() == "true",
        bearer_token=os.environ.get("OTEL_EXPORTER_OTLP_BEARER_TOKEN") or None,
        log_level=os.environ.get("OTEL_LOG_LEVEL", "INFO").upper(),
    )


def _apply(
    endpoint: str | None,
    service_name: str,
    content_recording: bool,
    bearer_token: str | None = None,
    log_level: str = "INFO",
) -> None:
    if not endpoint:
        logger.debug("OTEL_EXPORTER_OTLP_ENDPOINT not set — telemetry disabled")
        return

    # Set env gates before any instrumentation import reads them
    if not os.environ.get("AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"):
        os.environ["AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING"] = "true"
    if content_recording:
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true"

    # ── Shared infrastructure ─────────────────────────────────────────────────
    try:
        from opentelemetry.sdk.resources import Resource
        from azure.core.settings import settings
        # pyrefly: ignore [missing-import]
        from azure.core.tracing.ext.opentelemetry_span import OpenTelemetrySpan
    except ImportError as exc:
        logger.warning(
            "OTEL packages not fully installed — telemetry disabled. "
            "Run: pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-exporter-otlp-proto-http azure-core-tracing-opentelemetry. "
            "Missing: %s",
            exc,
        )
        return

    resource = Resource.create({"service.name": service_name})
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}

    # Normalise to explicit signal-specific paths so the exporter uses them as-is
    base = endpoint.rstrip("/")
    if base.endswith("/v1/traces"):
        base = base.removesuffix("/v1/traces")
    traces_endpoint = f"{base}/v1/traces"
    logs_endpoint = f"{base}/v1/logs"

    # ── Trace pipeline ────────────────────────────────────────────────────────
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        # pyrefly: ignore [missing-import]
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        trace_provider = TracerProvider(resource=resource)
        trace_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=traces_endpoint, headers=headers))
        )
        trace.set_tracer_provider(trace_provider)
        atexit.register(lambda: (trace_provider.force_flush(), trace_provider.shutdown()))

        settings.tracing_implementation.set_value(OpenTelemetrySpan)

        # pyrefly: ignore [missing-import]
        from azure.ai.projects.telemetry import AIProjectInstrumentor
        AIProjectInstrumentor().instrument(enable_content_recording=content_recording)
    except Exception as exc:
        logger.warning("OTEL trace pipeline failed: %s", exc)
        return

    # ── Log pipeline ──────────────────────────────────────────────────────────
    try:
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        # pyrefly: ignore [missing-import]
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

        log_provider = LoggerProvider(resource=resource)
        log_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=logs_endpoint, headers=headers))
        )
        set_logger_provider(log_provider)
        atexit.register(lambda: (log_provider.force_flush(), log_provider.shutdown()))

        otel_level = getattr(logging, log_level, logging.INFO)
        handler = LoggingHandler(level=otel_level, logger_provider=log_provider)
        root = logging.getLogger()
        # Lower root logger level if needed so records reach our handler;
        # existing console handlers with explicit levels are unaffected.
        if root.level == logging.NOTSET or root.level > otel_level:
            root.setLevel(otel_level)
        root.addHandler(handler)
    except Exception as exc:
        logger.warning("OTEL log pipeline failed (traces still active): %s", exc)

    logger.info(
        "OTEL active — service=%s log_level=%s content_recording=%s",
        service_name, log_level, content_recording,
    )
