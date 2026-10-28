import logging

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider

from opentelemetry.sdk.resources import Resource

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter


SERVICE_NAME = "village-pond-planning-system"
OTLP_ENDPOINT = "http://localhost:4318"


def setup_observability():
    resource = Resource.create({
        "service.name": SERVICE_NAME,
        "service.version": "1.0.0",
        "deployment.environment": "local",
    })

    # -----------------------
    # TRACES
    # -----------------------
    tracer_provider = TracerProvider(resource=resource)

    span_exporter = OTLPSpanExporter(
        endpoint=f"{OTLP_ENDPOINT}/v1/traces"
    )

    tracer_provider.add_span_processor(
        BatchSpanProcessor(span_exporter)
    )

    trace.set_tracer_provider(tracer_provider)

    # -----------------------
    # METRICS
    # -----------------------
    metric_exporter = OTLPMetricExporter(
        endpoint=f"{OTLP_ENDPOINT}/v1/metrics"
    )

    metric_reader = PeriodicExportingMetricReader(
        metric_exporter,
        export_interval_millis=5000,
    )

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
    )

    metrics.set_meter_provider(meter_provider)

    # -----------------------
    # LOGS
    # -----------------------
    logger_provider = LoggerProvider(resource=resource)

    log_exporter = OTLPLogExporter(
        endpoint=f"{OTLP_ENDPOINT}/v1/logs"
    )

    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(log_exporter)
    )

    set_logger_provider(logger_provider)

    otel_handler = LoggingHandler(
        level=logging.INFO,
        logger_provider=logger_provider,
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(otel_handler)

    logging.info("OpenTelemetry observability initialized")


def get_tracer(name: str):
    return trace.get_tracer(name)


def get_meter(name: str):
    return metrics.get_meter(name)
