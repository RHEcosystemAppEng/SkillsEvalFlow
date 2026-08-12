"""Observability decorators for timing and tracing."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

from abevalflow.observability.otel import get_tracer

logger = logging.getLogger(__name__)


def _set_status_ok(span):
    """Set span status to OK, handling missing opentelemetry gracefully."""
    try:
        from opentelemetry.trace import StatusCode

        span.set_status(StatusCode.OK)
    except ImportError:
        pass


def _set_status_error(span, description: str):
    """Set span status to ERROR, handling missing opentelemetry gracefully."""
    try:
        from opentelemetry.trace import StatusCode

        span.set_status(StatusCode.ERROR, description)
    except ImportError:
        pass


def timed_gate(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that times gate execution and emits an OTEL span.

    When OTEL is configured, creates a span with gate name, duration,
    pass/fail status, and score as attributes. When OTEL is not
    configured, the span is a no-op but timing is still logged.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer("abevalflow.gates")
        gate_name = func.__qualname__

        with tracer.start_as_current_span(f"gate.{gate_name}") as span:
            start = time.time()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                duration_ms = int((time.time() - start) * 1000)
                span.set_attribute("gate.duration_ms", duration_ms)
                _set_status_error(span, str(exc))
                span.record_exception(exc)
                raise

            duration_ms = int((time.time() - start) * 1000)
            logger.info("Gate %s executed in %dms", func.__qualname__, duration_ms)

            span.set_attribute("gate.name", gate_name)
            span.set_attribute("gate.duration_ms", duration_ms)
            if hasattr(result, "passed"):
                span.set_attribute("gate.passed", result.passed)
                if result.score is not None:
                    span.set_attribute("gate.score", result.score)
                span.set_attribute("gate.gate_type", str(result.gate_type))
                span.set_attribute("gate.mode", str(result.mode))
                if result.passed:
                    _set_status_ok(span)
                else:
                    _set_status_error(span, f"gate {gate_name} failed")

            if hasattr(result, "_duration_ms"):
                result._duration_ms = duration_ms

            return result

    return wrapper
