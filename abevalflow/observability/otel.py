"""OpenTelemetry setup for ABEvalFlow pipeline tracing.

Provides lazy-init OTEL instrumentation with three modes:

- **Standalone OTLP** (``OTEL_EXPORTER_OTLP_ENDPOINT`` only):
  Configures a TracerProvider with OTLP gRPC exporter.  Spans from
  ``@timed_gate`` and ``chat_completion_with_usage`` are exported.
- **MLflow dual-export** (both ``OTEL_EXPORTER_OTLP_ENDPOINT`` and
  ``MLFLOW_TRACKING_URI``): Delegates to MLflow's built-in OTLP bridge.
  Phase B spans are **not** exported in this mode — only MLflow's own
  auto-instrumented traces reach the collector.
- **MLflow-only** (``MLFLOW_TRACKING_URI`` only): MLflow handles its
  own tracing.  No TracerProvider is configured, so ``get_tracer()``
  returns the global no-op — Phase B spans are silently discarded.
- **Neither set**: no-op (zero overhead).

Phase B scope: spans are emitted only inside the ``aggregate_scorecard``
process (gates + LLM client).  Other entry points (store, Tekton steps)
do not call ``setup_tracer_provider()``.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_provider_initialized = False


def is_otel_enabled() -> bool:
    """Check whether any observability backend is configured.

    Returns True when *either* ``OTEL_EXPORTER_OTLP_ENDPOINT`` or
    ``MLFLOW_TRACKING_URI`` is set.  Note: Phase B spans (gate / LLM)
    are only exported in standalone-OTLP mode.  In MLflow-only mode the
    TracerProvider is the global no-op, so those spans are discarded.
    """
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") or os.environ.get("MLFLOW_TRACKING_URI"))


def setup_tracer_provider() -> None:
    """Configure the global TracerProvider based on environment.

    Idempotent — safe to call multiple times. Configuration:
    - Only OTEL_EXPORTER_OTLP_ENDPOINT: standalone TracerProvider with OTLP exporter
    - Only MLFLOW_TRACKING_URI: MLflow handles tracing internally
    - Both: MLflow dual-export (spans in both MLflow UI and OTLP endpoint)
    - Neither: no-op (global default tracer)
    """
    global _provider_initialized
    if _provider_initialized:
        return

    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI")

    if not otel_endpoint and not mlflow_uri:
        _provider_initialized = True
        return

    if mlflow_uri and otel_endpoint:
        # Dual-export: MLflow's own OTLP bridge forwards MLflow traces to
        # the collector.  We do NOT set a custom TracerProvider here, so
        # Phase B spans (gate / LLM) are still no-ops in this mode.
        os.environ.setdefault("MLFLOW_TRACE_ENABLE_OTLP_DUAL_EXPORT", "true")
        logger.info("OTEL: MLflow dual-export enabled (MLflow UI + %s)", otel_endpoint)
        _provider_initialized = True
        return

    if mlflow_uri and not otel_endpoint:
        # MLflow-only: no TracerProvider configured — get_tracer() returns
        # the global no-op, so Phase B spans are silently discarded.
        logger.info("OTEL: MLflow-only tracing (no OTLP endpoint)")
        _provider_initialized = True
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": os.environ.get("OTEL_SERVICE_NAME", "abevalflow"),
            }
        )
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=otel_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("OTEL: standalone TracerProvider configured (endpoint=%s)", otel_endpoint)
    except ImportError:
        logger.warning("OTEL: opentelemetry packages not installed — tracing disabled")

    _provider_initialized = True


def shutdown_tracer_provider() -> None:
    """Flush pending spans and shut down the TracerProvider."""
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
    except ImportError:
        pass


def get_tracer(name: str = "abevalflow"):
    """Return a tracer instance (real or no-op).

    Returns the OTEL API no-op tracer if opentelemetry is not installed
    or not configured, so callers never need to check availability.
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


class _NoOpSpan:
    """Minimal no-op span for when opentelemetry is not installed."""

    def set_attribute(self, key, value):
        pass

    def set_status(self, *args, **kwargs):
        pass

    def record_exception(self, exception):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _NoOpTracer:
    """Minimal no-op tracer for when opentelemetry is not installed."""

    def start_as_current_span(self, name, **kwargs):
        return _NoOpSpan()
