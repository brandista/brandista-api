# -*- coding: utf-8 -*-
"""
Tests for distributed tracing module
"""

import pytest
import asyncio
import time
from unittest.mock import MagicMock, patch

from agents.observability.tracing import (
    Tracer,
    Span,
    SpanStatus,
    SpanExporter,
    ConsoleExporter,
    InMemoryExporter,
    get_tracer,
    reset_tracer,
    trace_agent_execution,
    trace_llm_request,
    trace_blackboard_operation,
    trace_message_send,
    trace_api_call,
)


@pytest.fixture(autouse=True)
def reset_tracer_before_each():
    """Reset tracer before each test"""
    reset_tracer()
    yield
    reset_tracer()


@pytest.fixture
def memory_exporter():
    """Create in-memory exporter for testing"""
    return InMemoryExporter()


@pytest.fixture
def tracer(memory_exporter):
    """Create tracer with in-memory exporter"""
    return Tracer(
        service_name="test-service",
        exporters=[memory_exporter],
        use_otel=False,
        sample_rate=1.0,
    )


class TestSpan:
    """Tests for Span class"""

    def test_span_creation(self):
        """Span is created with correct fields"""
        span = Span(
            trace_id="trace123",
            span_id="span456",
            name="test.operation"
        )

        assert span.trace_id == "trace123"
        assert span.span_id == "span456"
        assert span.name == "test.operation"
        assert span.status == SpanStatus.UNSET

    def test_span_set_attribute(self):
        """Span attributes can be set"""
        span = Span(trace_id="t", span_id="s", name="test")

        span.set_attribute("key", "value")
        span.set_attribute("count", 42)

        assert span.attributes["key"] == "value"
        assert span.attributes["count"] == 42

    def test_span_set_multiple_attributes(self):
        """Multiple attributes can be set at once"""
        span = Span(trace_id="t", span_id="s", name="test")

        span.set_attributes({
            "a": 1,
            "b": 2,
            "c": 3,
        })

        assert span.attributes["a"] == 1
        assert span.attributes["b"] == 2
        assert span.attributes["c"] == 3

    def test_span_add_event(self):
        """Events can be added to span"""
        span = Span(trace_id="t", span_id="s", name="test")

        span.add_event("event1", {"key": "value"})

        assert len(span.events) == 1
        assert span.events[0]["name"] == "event1"
        assert span.events[0]["attributes"]["key"] == "value"

    def test_span_set_status_ok(self):
        """Span status can be set to OK"""
        span = Span(trace_id="t", span_id="s", name="test")

        span.set_status(SpanStatus.OK)

        assert span.status == SpanStatus.OK

    def test_span_set_status_error(self):
        """Span status can be set to ERROR with description"""
        span = Span(trace_id="t", span_id="s", name="test")

        span.set_status(SpanStatus.ERROR, "Something went wrong")

        assert span.status == SpanStatus.ERROR
        assert span.attributes["status.description"] == "Something went wrong"

    def test_span_record_exception(self):
        """Exception can be recorded"""
        span = Span(trace_id="t", span_id="s", name="test")

        try:
            raise ValueError("Test error")
        except ValueError as e:
            span.record_exception(e)

        assert span.status == SpanStatus.ERROR
        assert len(span.events) == 1
        assert span.events[0]["name"] == "exception"
        assert span.events[0]["attributes"]["exception.type"] == "ValueError"

    def test_span_end(self):
        """Span can be ended"""
        span = Span(trace_id="t", span_id="s", name="test")

        time.sleep(0.01)  # Small delay
        span.end()

        assert span.end_time is not None
        assert span.duration_ms > 0

    def test_span_duration_while_running(self):
        """Duration can be calculated while span is running"""
        span = Span(trace_id="t", span_id="s", name="test")

        time.sleep(0.01)

        # Duration available before end
        assert span.duration_ms > 0

    def test_span_to_dict(self):
        """Span can be converted to dictionary"""
        span = Span(
            trace_id="trace123",
            span_id="span456",
            name="test.operation",
            agent_id="scout"
        )
        span.set_attribute("key", "value")
        span.end()

        result = span.to_dict()

        assert result["trace_id"] == "trace123"
        assert result["span_id"] == "span456"
        assert result["name"] == "test.operation"
        assert result["agent_id"] == "scout"
        assert result["attributes"]["key"] == "value"
        assert "duration_ms" in result


class TestInMemoryExporter:
    """Tests for InMemoryExporter"""

    def test_export_stores_spans(self):
        """Exporter stores spans"""
        exporter = InMemoryExporter()
        span = Span(trace_id="t", span_id="s", name="test")

        exporter.export([span])

        assert len(exporter.get_spans()) == 1

    def test_export_limits_stored_spans(self):
        """Exporter limits number of stored spans"""
        exporter = InMemoryExporter(max_spans=5)

        for i in range(10):
            span = Span(trace_id="t", span_id=f"s{i}", name="test")
            exporter.export([span])

        # Should only keep last 5
        assert len(exporter.get_spans()) == 5

    def test_find_spans_by_name(self):
        """Can find spans by name"""
        exporter = InMemoryExporter()
        exporter.export([
            Span(trace_id="t", span_id="s1", name="agent.execute"),
            Span(trace_id="t", span_id="s2", name="llm.request"),
            Span(trace_id="t", span_id="s3", name="agent.execute"),
        ])

        results = exporter.find_spans(name="agent.execute")

        assert len(results) == 2

    def test_find_spans_by_trace_id(self):
        """Can find spans by trace ID"""
        exporter = InMemoryExporter()
        exporter.export([
            Span(trace_id="trace1", span_id="s1", name="test"),
            Span(trace_id="trace2", span_id="s2", name="test"),
            Span(trace_id="trace1", span_id="s3", name="test"),
        ])

        results = exporter.find_spans(trace_id="trace1")

        assert len(results) == 2

    def test_find_spans_by_agent_id(self):
        """Can find spans by agent ID"""
        exporter = InMemoryExporter()
        exporter.export([
            Span(trace_id="t", span_id="s1", name="test", agent_id="scout"),
            Span(trace_id="t", span_id="s2", name="test", agent_id="analyst"),
            Span(trace_id="t", span_id="s3", name="test", agent_id="scout"),
        ])

        results = exporter.find_spans(agent_id="scout")

        assert len(results) == 2

    def test_find_spans_by_status(self):
        """Can find spans by status"""
        exporter = InMemoryExporter()

        span1 = Span(trace_id="t", span_id="s1", name="test")
        span1.set_status(SpanStatus.OK)

        span2 = Span(trace_id="t", span_id="s2", name="test")
        span2.set_status(SpanStatus.ERROR)

        span3 = Span(trace_id="t", span_id="s3", name="test")
        span3.set_status(SpanStatus.OK)

        exporter.export([span1, span2, span3])

        results = exporter.find_spans(status=SpanStatus.ERROR)

        assert len(results) == 1

    def test_clear_removes_all(self):
        """Clear removes all spans"""
        exporter = InMemoryExporter()
        exporter.export([
            Span(trace_id="t", span_id="s1", name="test"),
            Span(trace_id="t", span_id="s2", name="test"),
        ])

        exporter.clear()

        assert len(exporter.get_spans()) == 0


class TestTracer:
    """Tests for Tracer class"""

    def test_start_span(self, tracer):
        """Start span creates span"""
        span = tracer.start_span("test.operation")

        assert span.name == "test.operation"
        assert span.trace_id is not None
        assert span.span_id is not None

    def test_start_span_with_agent_id(self, tracer):
        """Start span sets agent ID"""
        span = tracer.start_span("test", agent_id="scout")

        assert span.agent_id == "scout"

    def test_start_span_with_attributes(self, tracer):
        """Start span with initial attributes"""
        span = tracer.start_span("test", attributes={"key": "value"})

        assert span.attributes["key"] == "value"

    def test_end_span(self, tracer, memory_exporter):
        """End span finishes and exports"""
        span = tracer.start_span("test")

        tracer.end_span(span)

        # Flush to export
        tracer.flush()

        assert span.end_time is not None
        assert len(memory_exporter.get_spans()) == 1

    def test_end_span_with_status(self, tracer):
        """End span can set status"""
        span = tracer.start_span("test")

        tracer.end_span(span, SpanStatus.ERROR)

        assert span.status == SpanStatus.ERROR

    def test_trace_context_manager(self, tracer, memory_exporter):
        """Trace context manager works"""
        with tracer.trace("test.operation") as span:
            span.set_attribute("key", "value")

        tracer.flush()

        assert len(memory_exporter.get_spans()) == 1
        assert memory_exporter.get_spans()[0].status == SpanStatus.OK

    def test_trace_context_manager_error(self, tracer, memory_exporter):
        """Trace context manager handles errors"""
        with pytest.raises(ValueError):
            with tracer.trace("test.operation") as span:
                raise ValueError("Test error")

        tracer.flush()

        assert len(memory_exporter.get_spans()) == 1
        assert memory_exporter.get_spans()[0].status == SpanStatus.ERROR

    @pytest.mark.asyncio
    async def test_trace_async_context_manager(self, tracer, memory_exporter):
        """Async trace context manager works"""
        async with tracer.trace_async("test.async") as span:
            await asyncio.sleep(0.01)
            span.set_attribute("async", True)

        tracer.flush()

        assert len(memory_exporter.get_spans()) == 1

    def test_trace_function_decorator(self, tracer, memory_exporter):
        """Function decorator traces function"""
        @tracer.trace_function("custom.operation")
        def my_function():
            return "result"

        result = my_function()

        tracer.flush()

        assert result == "result"
        assert len(memory_exporter.get_spans()) == 1
        assert memory_exporter.get_spans()[0].name == "custom.operation"

    @pytest.mark.asyncio
    async def test_trace_async_function_decorator(self, tracer, memory_exporter):
        """Function decorator traces async function"""
        @tracer.trace_function("async.operation")
        async def my_async_function():
            await asyncio.sleep(0.01)
            return "async result"

        result = await my_async_function()

        tracer.flush()

        assert result == "async result"
        assert len(memory_exporter.get_spans()) == 1

    def test_nested_spans(self, tracer, memory_exporter):
        """Nested spans maintain parent-child relationship"""
        with tracer.trace("parent") as parent_span:
            with tracer.trace("child") as child_span:
                pass

        tracer.flush()

        assert child_span.parent_id == parent_span.span_id
        assert child_span.trace_id == parent_span.trace_id

    def test_inject_context(self, tracer):
        """Context can be injected for propagation"""
        with tracer.trace("test"):
            context = tracer.inject_context()

        assert "trace_id" in context
        assert "span_id" in context

    def test_extract_context(self, tracer):
        """Context can be extracted from carrier"""
        tracer.extract_context({
            "trace_id": "external_trace",
            "span_id": "external_span",
        })

        span = tracer.start_span("test")

        assert span.trace_id == "external_trace"
        assert span.parent_id == "external_span"

    def test_clear_context(self, tracer):
        """Context can be cleared"""
        with tracer.trace("test"):
            tracer.clear_context()

        assert tracer.get_current_trace_id() is None
        assert tracer.get_current_span_id() is None

    def test_sample_rate_zero(self):
        """Sample rate of 0 exports nothing"""
        exporter = InMemoryExporter()
        tracer = Tracer(
            service_name="test",
            exporters=[exporter],
            use_otel=False,
            sample_rate=0.0,
        )

        with tracer.trace("test"):
            pass

        tracer.flush()

        # Nothing should be exported
        assert len(exporter.get_spans()) == 0


class TestGlobalTracer:
    """Tests for global tracer functions"""

    def test_get_tracer_returns_singleton(self):
        """get_tracer returns same instance"""
        t1 = get_tracer()
        t2 = get_tracer()

        assert t1 is t2

    def test_reset_tracer_clears_singleton(self):
        """reset_tracer clears the global instance"""
        t1 = get_tracer()
        reset_tracer()
        t2 = get_tracer()

        assert t1 is not t2


class TestConvenienceFunctions:
    """Tests for convenience tracing functions"""

    def test_trace_agent_execution(self):
        """trace_agent_execution decorator works"""
        reset_tracer()

        @trace_agent_execution("scout")
        def agent_execute():
            return "executed"

        result = agent_execute()

        assert result == "executed"

    def test_trace_llm_request(self):
        """trace_llm_request context manager works"""
        reset_tracer()
        exporter = InMemoryExporter()
        tracer = Tracer(exporters=[exporter], use_otel=False)

        # Use global tracer
        import agents.observability.tracing as tracing_module
        original = tracing_module._tracer
        tracing_module._tracer = tracer

        try:
            with trace_llm_request("analyst", "gpt-4") as span:
                span.set_attribute("tokens", 100)

            tracer.flush()

            assert len(exporter.get_spans()) == 1
            assert exporter.get_spans()[0].attributes["llm.model"] == "gpt-4"
        finally:
            tracing_module._tracer = original

    def test_trace_blackboard_operation(self):
        """trace_blackboard_operation creates span"""
        reset_tracer()
        exporter = InMemoryExporter()
        tracer = Tracer(exporters=[exporter], use_otel=False)

        import agents.observability.tracing as tracing_module
        original = tracing_module._tracer
        tracing_module._tracer = tracer

        try:
            span = trace_blackboard_operation("scout", "write", "scout.data")
            tracer.end_span(span)
            tracer.flush()

            assert len(exporter.get_spans()) == 1
            assert exporter.get_spans()[0].attributes["blackboard.key"] == "scout.data"
        finally:
            tracing_module._tracer = original

    def test_trace_message_send(self):
        """trace_message_send creates span"""
        reset_tracer()
        exporter = InMemoryExporter()
        tracer = Tracer(exporters=[exporter], use_otel=False)

        import agents.observability.tracing as tracing_module
        original = tracing_module._tracer
        tracing_module._tracer = tracer

        try:
            span = trace_message_send("scout", "analyst", "FINDING")
            tracer.end_span(span)
            tracer.flush()

            assert len(exporter.get_spans()) == 1
            assert exporter.get_spans()[0].attributes["message.type"] == "FINDING"
        finally:
            tracing_module._tracer = original

    def test_trace_api_call(self):
        """trace_api_call creates span"""
        reset_tracer()
        exporter = InMemoryExporter()
        tracer = Tracer(exporters=[exporter], use_otel=False)

        import agents.observability.tracing as tracing_module
        original = tracing_module._tracer
        tracing_module._tracer = tracer

        try:
            span = trace_api_call("scout", "ytj", "/companies/search")
            tracer.end_span(span)
            tracer.flush()

            assert len(exporter.get_spans()) == 1
            assert exporter.get_spans()[0].attributes["api.name"] == "ytj"
        finally:
            tracing_module._tracer = original


class TestConsoleExporter:
    """Tests for ConsoleExporter"""

    def test_export_logs_span(self, caplog):
        """Console exporter logs span info"""
        exporter = ConsoleExporter(verbose=True)
        span = Span(
            trace_id="trace123",
            span_id="span456",
            name="test.operation",
            agent_id="scout"
        )
        span.set_status(SpanStatus.OK)
        span.end()

        import logging
        with caplog.at_level(logging.INFO):
            exporter.export([span])

        # Should have logged something
        assert "test.operation" in caplog.text or len(caplog.records) > 0
