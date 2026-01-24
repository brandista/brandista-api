# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Observability Module
Prometheus metrics, structured logging, and distributed tracing

Version: 3.0.0
"""

from .metrics import (
    MetricsCollector,
    get_metrics,
    reset_metrics,
    # Agent metrics
    agent_execution_started,
    agent_execution_completed,
    agent_execution_failed,
    agent_insight_emitted,
    # Swarm metrics
    message_sent,
    message_received,
    blackboard_write,
    blackboard_read,
    collaboration_started,
    collaboration_completed,
    # LLM metrics
    llm_request_started,
    llm_request_completed,
    # Analysis metrics
    analysis_started,
    analysis_completed,
)

from .tracing import (
    Tracer,
    Span,
    SpanStatus,
    SpanExporter,
    ConsoleExporter,
    InMemoryExporter,
    get_tracer,
    reset_tracer,
    # Convenience functions
    trace_agent_execution,
    trace_llm_request,
    trace_blackboard_operation,
    trace_message_send,
    trace_api_call,
)

from .logging import (
    # Formatters
    JSONFormatter,
    ConsoleFormatter,
    StructuredLogger,
    SensitiveDataMasker,
    # Context management
    set_correlation_id,
    get_correlation_id,
    set_trace_context,
    get_trace_context,
    set_agent_context,
    get_agent_context,
    set_user_context,
    clear_context,
    # Decorators
    with_context,
    with_agent,
    # Setup
    setup_logging,
    get_logger,
    get_agent_logger,
)

__all__ = [
    # Metrics
    'MetricsCollector',
    'get_metrics',
    'reset_metrics',
    'agent_execution_started',
    'agent_execution_completed',
    'agent_execution_failed',
    'agent_insight_emitted',
    'message_sent',
    'message_received',
    'blackboard_write',
    'blackboard_read',
    'collaboration_started',
    'collaboration_completed',
    'llm_request_started',
    'llm_request_completed',
    'analysis_started',
    'analysis_completed',
    # Tracing
    'Tracer',
    'Span',
    'SpanStatus',
    'SpanExporter',
    'ConsoleExporter',
    'InMemoryExporter',
    'get_tracer',
    'reset_tracer',
    'trace_agent_execution',
    'trace_llm_request',
    'trace_blackboard_operation',
    'trace_message_send',
    'trace_api_call',
    # Logging
    'JSONFormatter',
    'ConsoleFormatter',
    'StructuredLogger',
    'SensitiveDataMasker',
    'set_correlation_id',
    'get_correlation_id',
    'set_trace_context',
    'get_trace_context',
    'set_agent_context',
    'get_agent_context',
    'set_user_context',
    'clear_context',
    'with_context',
    'with_agent',
    'setup_logging',
    'get_logger',
    'get_agent_logger',
]
