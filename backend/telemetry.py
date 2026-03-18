"""OpenTelemetry setup for Sentinel Pulse."""
import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.pymongo import PymongoInstrumentor

logger = logging.getLogger("SentinelPulse")

APP_VERSION = "1.0.0-beta"
MAX_STORED_SPANS = 500

# In-memory span store for the /api/traces endpoint
_span_store: list[dict] = []


class InMemorySpanExporter(SpanExporter):
    """Exports spans to an in-memory list for API access."""

    def export(self, spans):
        for span in spans:
            entry = {
                "trace_id": format(span.context.trace_id, "032x"),
                "span_id": format(span.context.span_id, "016x"),
                "parent_span_id": format(span.parent.span_id, "016x") if span.parent else None,
                "name": span.name,
                "kind": span.kind.name if span.kind else "INTERNAL",
                "status": span.status.status_code.name if span.status else "UNSET",
                "start_time": span.start_time,
                "end_time": span.end_time,
                "duration_ms": round((span.end_time - span.start_time) / 1_000_000, 2) if span.end_time and span.start_time else 0,
                "attributes": dict(span.attributes) if span.attributes else {},
                "events": [
                    {"name": e.name, "timestamp": e.timestamp, "attributes": dict(e.attributes) if e.attributes else {}}
                    for e in (span.events or [])
                ],
            }
            _span_store.append(entry)
            if len(_span_store) > MAX_STORED_SPANS:
                del _span_store[: len(_span_store) - MAX_STORED_SPANS]
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=None):
        return True


_in_memory_exporter = InMemorySpanExporter()


def setup_telemetry(app):
    """Initialize OpenTelemetry tracing for the application."""
    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: "sentinel-pulse",
        ResourceAttributes.SERVICE_VERSION: APP_VERSION,
    })

    provider = TracerProvider(resource=resource)

    # Always add in-memory exporter for /api/traces
    provider.add_span_processor(SimpleSpanProcessor(_in_memory_exporter))

    # Optional: OTLP exporter for external collectors (Jaeger, Grafana Tempo, etc.)
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            otlp_exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info("OTLP trace exporter configured: %s", otlp_endpoint)
        except Exception as e:
            logger.warning("Failed to configure OTLP exporter: %s", e)

    # Optional: Console exporter for debugging
    if os.environ.get("OTEL_CONSOLE_EXPORT", "").lower() == "true":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    # Auto-instrument PyMongo
    PymongoInstrumentor().instrument()

    logger.info("OpenTelemetry tracing initialized (service=sentinel-pulse)")


def get_tracer(name: str = "sentinel-pulse"):
    """Get a tracer instance for creating custom spans."""
    return trace.get_tracer(name, APP_VERSION)


def get_stored_spans(limit: int = 100, name_filter: str = "") -> list[dict]:
    """Retrieve recent stored spans, optionally filtered by name."""
    spans = _span_store
    if name_filter:
        spans = [s for s in spans if name_filter.lower() in s["name"].lower()]
    return list(reversed(spans[-limit:]))
