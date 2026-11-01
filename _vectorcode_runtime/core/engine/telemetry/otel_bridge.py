"""
VECTOR OpenTelemetry Bridge.

Verdict after comparing vector's telemetry vs VECTOR's loguru:
- loguru: excellent for local structured logging (VECTOR keeps this)
- OpenTelemetry: adds distributed tracing, metrics, cloud-exportable spans (VECTOR adds this)

Decision: BOTH. loguru stays as the primary logger.
OpenTelemetry adds spans/traces for cloud deployment visibility.
When VECTOR goes cloud, OTEL traces become essential for debugging distributed agents.

Exports to: stdout (dev) | OTLP endpoint (prod, set OTEL_EXPORTER_OTLP_ENDPOINT)
"""
from __future__ import annotations

__all__ = [
    "get_telemetry",
    "Span",
    "trace_span",
    "VectorTelemetry",
]


import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Generator

from core.config import CONFIG
from loguru import logger

_OTEL_ENDPOINT = CONFIG.get("otel_endpoint", "")
_SERVICE_NAME = "vector-agent-system"
_SERVICE_VERSION = "1.0.0"


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_id: str | None
    start_time: float
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"
    events: list[dict] = field(default_factory=list)

    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms(),
            "attributes": self.attributes,
            "status": self.status,
            "events": self.events,
        }


class VectorTelemetry:
    """
    OpenTelemetry-compatible telemetry for VECTOR.

    When OTEL_EXPORTER_OTLP_ENDPOINT is set → ships spans to observability backend.
    Otherwise → logs spans via loguru (zero infrastructure needed).

    Cloud deployment: set OTEL_EXPORTER_OTLP_ENDPOINT=https://your-collector:4318
    """

    def __init__(self) -> None:
        self._tracer = None
        self._spans: list[Span] = []
        self._current_trace: str | None = None
        self._otel_available = False
        self._init_otel()

    def _init_otel(self) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
            from opentelemetry.sdk.resources import Resource

            resource = Resource.create({
                "service.name": _SERVICE_NAME,
                "service.version": _SERVICE_VERSION,
                "deployment.environment": CONFIG.get("env", "local"),
            })
            provider = TracerProvider(resource=resource)

            if _OTEL_ENDPOINT:
                try:
                    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                    exporter = OTLPSpanExporter(endpoint=f"{_OTEL_ENDPOINT}/v1/traces")
                    provider.add_span_processor(BatchSpanProcessor(exporter))
                    logger.info("[VECTOR][otel] OTLP exporter → {}", _OTEL_ENDPOINT)
                except ImportError:
                    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            else:
                from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
                self._in_memory = InMemorySpanExporter()
                provider.add_span_processor(BatchSpanProcessor(self._in_memory))

            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(_SERVICE_NAME, _SERVICE_VERSION)
            self._otel_available = True
            logger.info("[VECTOR][otel] OpenTelemetry initialized (OTLP={})", bool(_OTEL_ENDPOINT))
        except ImportError:
            logger.info("[VECTOR][otel] opentelemetry-sdk not installed — using loguru-only mode. "
                        "Run: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http")

    @contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Generator[Span, None, None]:
        """
        Context manager creating a traced span.

        Usage:
            with telemetry.span("agent.think", {"agent": "orchestrator"}) as span:
                result = do_work()
                span.attributes["result_len"] = len(result)
        """
        trace_id = self._current_trace or str(uuid.uuid4()).replace("-", "")
        span_id = str(uuid.uuid4()).replace("-", "")[:16]
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=span_id,
            parent_id=None,
            start_time=time.time(),
            attributes=attributes or {},
        )

        if self._otel_available and self._tracer:
            from opentelemetry import trace as otel_trace
            with self._tracer.start_as_current_span(name) as otel_span:
                if attributes:
                    for k, v in attributes.items():
                        otel_span.set_attribute(k, str(v))
                try:
                    yield span
                    span.status = "OK"
                except Exception as e:
                    span.status = "ERROR"
                    otel_span.record_exception(e)
                    raise
                finally:
                    span.end_time = time.time()
                    self._spans.append(span)
                    logger.debug("[VECTOR][otel] span {} ({:.0f}ms)", name, span.duration_ms())
        else:
            try:
                yield span
                span.status = "OK"
            except Exception as e:
                span.status = "ERROR"
                raise
            finally:
                span.end_time = time.time()
                self._spans.append(span)
                logger.debug("[VECTOR][otel] span {} ({:.0f}ms)", name, span.duration_ms())

    def record_metric(self, name: str, value: float, unit: str = "", tags: dict | None = None) -> None:
        """Record a metric (counter, gauge, histogram)."""
        logger.info("[VECTOR][otel][metric] {}={}{} {}", name, value, unit, tags or {})

    def flush(self) -> list[dict]:
        """Return all collected spans as dicts."""
        return [s.to_dict() for s in self._spans]

    def clear(self) -> None:
        self._spans.clear()


_telemetry: VectorTelemetry | None = None


def get_telemetry() -> VectorTelemetry:
    global _telemetry
    if _telemetry is None:
        _telemetry = VectorTelemetry()
    return _telemetry


@contextmanager
def trace_span(name: str, **attributes) -> Generator[Span, None, None]:
    """Convenience: get_telemetry().span(name, attributes)."""
    with get_telemetry().span(name, attributes) as span:
        yield span


if __name__ == "__main__":
    tel = VectorTelemetry()
    with tel.span("test.operation", {"component": "test"}) as span:
        time.sleep(0.01)
        span.attributes["result"] = "ok"
    spans = tel.flush()
    assert len(spans) == 1
    assert spans[0]["name"] == "test.operation"
    assert spans[0]["duration_ms"] > 5
    print(f"OK otel_bridge.py — OTEL available: {tel._otel_available}")
