# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Distributed Tracing
OpenTelemetry-compatible tracing for agent operations

Version: 3.0.0

Provides distributed tracing for:
- Agent executions
- LLM requests
- Blackboard operations
- Message passing
- External API calls

Works with or without OpenTelemetry installed.
"""

import asyncio
import logging
import time
import uuid
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Union
from functools import wraps
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import OpenTelemetry
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode, SpanKind
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.sdk.trace import TracerProvider, Span as OTelSpan
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    TracerProvider = None


class SpanStatus(Enum):
    """Span status"""
    OK = "ok"
    ERROR = "error"
    UNSET = "unset"


@dataclass
class Span:
    """
    Lightweight span for tracing.

    Compatible with OpenTelemetry spans but works standalone.
    """
    trace_id: str
    span_id: str
    name: str
    parent_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.UNSET
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)
    links: List[str] = field(default_factory=list)

    # Service info
    service_name: str = "growth-engine"
    agent_id: Optional[str] = None

    def set_attribute(self, key: str, value: Any):
        """Set span attribute"""
        self.attributes[key] = value

    def set_attributes(self, attributes: Dict[str, Any]):
        """Set multiple attributes"""
        self.attributes.update(attributes)

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Add event to span"""
        self.events.append({
            'name': name,
            'timestamp': time.time(),
            'attributes': attributes or {}
        })

    def set_status(self, status: SpanStatus, description: Optional[str] = None):
        """Set span status"""
        self.status = status
        if description:
            self.attributes['status.description'] = description

    def record_exception(self, exception: Exception):
        """Record exception"""
        self.add_event('exception', {
            'exception.type': type(exception).__name__,
            'exception.message': str(exception),
        })
        self.set_status(SpanStatus.ERROR, str(exception))

    def end(self, end_time: Optional[float] = None):
        """End the span"""
        self.end_time = end_time or time.time()

    @property
    def duration_ms(self) -> float:
        """Get span duration in milliseconds"""
        if self.end_time is None:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'trace_id': self.trace_id,
            'span_id': self.span_id,
            'parent_id': self.parent_id,
            'name': self.name,
            'service_name': self.service_name,
            'agent_id': self.agent_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration_ms': self.duration_ms,
            'status': self.status.value,
            'attributes': self.attributes,
            'events': self.events,
            'links': self.links,
        }


class SpanExporter:
    """Base class for span exporters"""

    def export(self, spans: List[Span]):
        """Export spans"""
        raise NotImplementedError

    def shutdown(self):
        """Shutdown exporter"""
        pass


class ConsoleExporter(SpanExporter):
    """Export spans to console (for development)"""

    def __init__(self, verbose: bool = False):
        self._verbose = verbose

    def export(self, spans: List[Span]):
        for span in spans:
            status_emoji = "✓" if span.status == SpanStatus.OK else "✗" if span.status == SpanStatus.ERROR else "○"
            agent_info = f" [{span.agent_id}]" if span.agent_id else ""

            logger.info(
                f"[Trace] {status_emoji} {span.name}{agent_info} "
                f"({span.duration_ms:.2f}ms) trace={span.trace_id[:8]}"
            )

            if self._verbose:
                for key, value in span.attributes.items():
                    logger.debug(f"  {key}: {value}")

                for event in span.events:
                    logger.debug(f"  Event: {event['name']}")


class InMemoryExporter(SpanExporter):
    """Store spans in memory (for testing)"""

    def __init__(self, max_spans: int = 1000):
        self._spans: List[Span] = []
        self._max_spans = max_spans

    def export(self, spans: List[Span]):
        self._spans.extend(spans)

        # Trim if over limit
        if len(self._spans) > self._max_spans:
            self._spans = self._spans[-self._max_spans:]

    def get_spans(self) -> List[Span]:
        """Get all stored spans"""
        return self._spans.copy()

    def clear(self):
        """Clear all spans"""
        self._spans.clear()

    def find_spans(
        self,
        name: Optional[str] = None,
        trace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        status: Optional[SpanStatus] = None,
    ) -> List[Span]:
        """Find spans matching criteria"""
        result = self._spans

        if name:
            result = [s for s in result if s.name == name]
        if trace_id:
            result = [s for s in result if s.trace_id == trace_id]
        if agent_id:
            result = [s for s in result if s.agent_id == agent_id]
        if status:
            result = [s for s in result if s.status == status]

        return result


class Tracer:
    """
    Distributed tracer for Growth Engine.

    Can use OpenTelemetry if available, or works standalone.
    """

    def __init__(
        self,
        service_name: str = "growth-engine",
        exporters: Optional[List[SpanExporter]] = None,
        use_otel: bool = True,
        sample_rate: float = 1.0,
    ):
        """
        Initialize tracer.

        Args:
            service_name: Service name for spans
            exporters: List of span exporters
            use_otel: Use OpenTelemetry if available
            sample_rate: Sampling rate (0.0 to 1.0)
        """
        self._service_name = service_name
        self._exporters = exporters or [ConsoleExporter()]
        self._sample_rate = sample_rate
        self._use_otel = use_otel and OTEL_AVAILABLE

        # OpenTelemetry tracer
        self._otel_tracer = None

        # Active spans by ID
        self._active_spans: Dict[str, Span] = {}

        # Current trace context (per-task)
        self._context: Dict[str, str] = {}

        # Batch processing
        self._pending_spans: List[Span] = []
        self._batch_size = 10
        self._flush_interval = 5.0  # seconds
        self._last_flush = time.time()

        # Initialize OpenTelemetry if available and enabled
        if self._use_otel:
            self._init_otel()

        logger.info(
            f"[Tracer] Initialized (service={service_name}, "
            f"otel={'enabled' if self._use_otel else 'disabled'})"
        )

    def _init_otel(self):
        """Initialize OpenTelemetry"""
        resource = Resource.create({
            "service.name": self._service_name,
            "service.version": "3.0.0",
        })

        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)

        trace.set_tracer_provider(provider)
        self._otel_tracer = trace.get_tracer(self._service_name)

    def _generate_id(self) -> str:
        """Generate unique ID"""
        return uuid.uuid4().hex[:16]

    def _should_sample(self) -> bool:
        """Check if span should be sampled"""
        import random
        return random.random() < self._sample_rate

    def start_span(
        self,
        name: str,
        parent_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Span:
        """
        Start a new span.

        Args:
            name: Span name
            parent_id: Parent span ID
            trace_id: Trace ID (generates new if not provided)
            agent_id: Agent ID
            attributes: Initial attributes

        Returns:
            New span
        """
        # Use context trace_id if not provided
        if trace_id is None:
            trace_id = self._context.get('trace_id') or self._generate_id()

        # Use context parent if not provided
        if parent_id is None:
            parent_id = self._context.get('span_id')

        span = Span(
            trace_id=trace_id,
            span_id=self._generate_id(),
            name=name,
            parent_id=parent_id,
            service_name=self._service_name,
            agent_id=agent_id,
            attributes=attributes or {},
        )

        self._active_spans[span.span_id] = span

        # Update context
        self._context['trace_id'] = trace_id
        self._context['span_id'] = span.span_id

        return span

    def end_span(self, span: Span, status: Optional[SpanStatus] = None):
        """End a span"""
        if status:
            span.set_status(status)
        elif span.status == SpanStatus.UNSET:
            span.set_status(SpanStatus.OK)

        span.end()

        # Remove from active
        self._active_spans.pop(span.span_id, None)

        # Restore parent context
        if span.parent_id:
            self._context['span_id'] = span.parent_id
        elif span.span_id == self._context.get('span_id'):
            self._context.pop('span_id', None)

        # Add to pending
        if self._should_sample():
            self._pending_spans.append(span)

        # Flush if needed
        self._maybe_flush()

    def _maybe_flush(self):
        """Flush spans if batch is full or interval elapsed"""
        now = time.time()

        if (
            len(self._pending_spans) >= self._batch_size or
            now - self._last_flush >= self._flush_interval
        ):
            self.flush()

    def flush(self):
        """Export pending spans"""
        if not self._pending_spans:
            return

        spans = self._pending_spans
        self._pending_spans = []
        self._last_flush = time.time()

        for exporter in self._exporters:
            try:
                exporter.export(spans)
            except Exception as e:
                logger.error(f"[Tracer] Export error: {e}")

    def shutdown(self):
        """Shutdown tracer"""
        self.flush()

        for exporter in self._exporters:
            try:
                exporter.shutdown()
            except Exception:
                pass

    @contextmanager
    def trace(
        self,
        name: str,
        agent_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """
        Context manager for tracing a code block.

        Usage:
            with tracer.trace("operation_name", agent_id="scout"):
                # code to trace
        """
        span = self.start_span(name, agent_id=agent_id, attributes=attributes)

        try:
            yield span
            self.end_span(span, SpanStatus.OK)
        except Exception as e:
            span.record_exception(e)
            self.end_span(span, SpanStatus.ERROR)
            raise

    @asynccontextmanager
    async def trace_async(
        self,
        name: str,
        agent_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """Async context manager for tracing"""
        span = self.start_span(name, agent_id=agent_id, attributes=attributes)

        try:
            yield span
            self.end_span(span, SpanStatus.OK)
        except Exception as e:
            span.record_exception(e)
            self.end_span(span, SpanStatus.ERROR)
            raise

    def trace_function(
        self,
        name: Optional[str] = None,
        agent_id: Optional[str] = None,
    ):
        """Decorator for tracing functions"""
        def decorator(func):
            span_name = name or func.__name__

            if asyncio.iscoroutinefunction(func):
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    async with self.trace_async(span_name, agent_id=agent_id) as span:
                        span.set_attribute('function', func.__name__)
                        return await func(*args, **kwargs)
                return async_wrapper
            else:
                @wraps(func)
                def sync_wrapper(*args, **kwargs):
                    with self.trace(span_name, agent_id=agent_id) as span:
                        span.set_attribute('function', func.__name__)
                        return func(*args, **kwargs)
                return sync_wrapper

        return decorator

    def get_current_trace_id(self) -> Optional[str]:
        """Get current trace ID"""
        return self._context.get('trace_id')

    def get_current_span_id(self) -> Optional[str]:
        """Get current span ID"""
        return self._context.get('span_id')

    def inject_context(self) -> Dict[str, str]:
        """
        Get context for propagation to other services.

        Returns:
            Dictionary with trace context
        """
        return {
            'trace_id': self._context.get('trace_id', ''),
            'span_id': self._context.get('span_id', ''),
        }

    def extract_context(self, carrier: Dict[str, str]):
        """
        Extract context from incoming request.

        Args:
            carrier: Dictionary with trace context
        """
        if 'trace_id' in carrier:
            self._context['trace_id'] = carrier['trace_id']
        if 'span_id' in carrier:
            self._context['span_id'] = carrier['span_id']

    def clear_context(self):
        """Clear current context"""
        self._context.clear()


# Global tracer instance
_tracer: Optional[Tracer] = None


def get_tracer(
    service_name: str = "growth-engine",
    exporters: Optional[List[SpanExporter]] = None,
) -> Tracer:
    """Get or create global tracer"""
    global _tracer
    if _tracer is None:
        _tracer = Tracer(service_name, exporters)
    return _tracer


def reset_tracer():
    """Reset global tracer"""
    global _tracer
    if _tracer:
        _tracer.shutdown()
    _tracer = None


# Convenience functions

def trace_agent_execution(agent_id: str):
    """Decorator for tracing agent execution"""
    return get_tracer().trace_function(f"agent.{agent_id}.execute", agent_id=agent_id)


def trace_llm_request(agent_id: str, model: str):
    """Context manager for tracing LLM request"""
    tracer = get_tracer()

    @contextmanager
    def _trace():
        with tracer.trace("llm.request", agent_id=agent_id) as span:
            span.set_attribute('llm.model', model)
            span.set_attribute('llm.agent_id', agent_id)
            yield span

    return _trace()


def trace_blackboard_operation(agent_id: str, operation: str, key: str):
    """Trace blackboard operation"""
    tracer = get_tracer()
    span = tracer.start_span(f"blackboard.{operation}", agent_id=agent_id)
    span.set_attribute('blackboard.key', key)
    span.set_attribute('blackboard.operation', operation)
    return span


def trace_message_send(from_agent: str, to_agent: Optional[str], message_type: str):
    """Trace message sending"""
    tracer = get_tracer()
    span = tracer.start_span("message.send", agent_id=from_agent)
    span.set_attribute('message.from', from_agent)
    span.set_attribute('message.to', to_agent or 'broadcast')
    span.set_attribute('message.type', message_type)
    return span


def trace_api_call(agent_id: str, api_name: str, endpoint: str):
    """Trace external API call"""
    tracer = get_tracer()
    span = tracer.start_span(f"api.{api_name}", agent_id=agent_id)
    span.set_attribute('api.name', api_name)
    span.set_attribute('api.endpoint', endpoint)
    return span
