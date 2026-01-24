# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Prometheus Metrics
Comprehensive metrics for monitoring agent performance, LLM usage, and swarm activity

Version: 3.0.0

Usage:
    from agents.observability import agent_execution_completed, get_metrics

    # Record metric
    agent_execution_completed('scout', 1500, 'complete')

    # Get all metrics for /metrics endpoint
    metrics_output = get_metrics().export()
"""

import time
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from contextlib import contextmanager


@dataclass
class MetricValue:
    """Single metric value with labels"""
    name: str
    value: float
    labels: Dict[str, str]
    timestamp: datetime = field(default_factory=datetime.now)
    metric_type: str = "counter"  # counter, gauge, histogram, summary


@dataclass
class HistogramBucket:
    """Histogram bucket for latency tracking"""
    le: float  # less than or equal
    count: int = 0


class Histogram:
    """Simple histogram implementation for latency tracking"""

    DEFAULT_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, float('inf')]

    def __init__(self, name: str, description: str, labels: List[str], buckets: List[float] = None):
        self.name = name
        self.description = description
        self.label_names = labels
        self.buckets = buckets or self.DEFAULT_BUCKETS
        self._data: Dict[tuple, Dict[str, Any]] = defaultdict(lambda: {
            'buckets': {b: 0 for b in self.buckets},
            'sum': 0.0,
            'count': 0
        })
        self._lock = threading.Lock()

    def observe(self, value: float, **labels):
        """Record an observation"""
        label_key = tuple(sorted(labels.items()))

        with self._lock:
            data = self._data[label_key]
            data['sum'] += value
            data['count'] += 1

            for bucket in self.buckets:
                if value <= bucket:
                    data['buckets'][bucket] += 1

    def export(self) -> List[str]:
        """Export in Prometheus format"""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} histogram"
        ]

        with self._lock:
            for label_key, data in self._data.items():
                labels_str = ",".join(f'{k}="{v}"' for k, v in label_key)

                # Buckets
                for bucket, count in sorted(data['buckets'].items()):
                    le = "+Inf" if bucket == float('inf') else str(bucket)
                    lines.append(f'{self.name}_bucket{{{labels_str},le="{le}"}} {count}')

                # Sum and count
                lines.append(f'{self.name}_sum{{{labels_str}}} {data["sum"]}')
                lines.append(f'{self.name}_count{{{labels_str}}} {data["count"]}')

        return lines


class Counter:
    """Simple counter implementation"""

    def __init__(self, name: str, description: str, labels: List[str]):
        self.name = name
        self.description = description
        self.label_names = labels
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def inc(self, value: float = 1.0, **labels):
        """Increment counter"""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] += value

    def export(self) -> List[str]:
        """Export in Prometheus format"""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} counter"
        ]

        with self._lock:
            for label_key, value in self._values.items():
                if label_key:
                    labels_str = ",".join(f'{k}="{v}"' for k, v in label_key)
                    lines.append(f'{self.name}{{{labels_str}}} {value}')
                else:
                    lines.append(f'{self.name} {value}')

        return lines


class Gauge:
    """Simple gauge implementation"""

    def __init__(self, name: str, description: str, labels: List[str]):
        self.name = name
        self.description = description
        self.label_names = labels
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()

    def set(self, value: float, **labels):
        """Set gauge value"""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] = value

    def inc(self, value: float = 1.0, **labels):
        """Increment gauge"""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] += value

    def dec(self, value: float = 1.0, **labels):
        """Decrement gauge"""
        label_key = tuple(sorted(labels.items()))
        with self._lock:
            self._values[label_key] -= value

    def export(self) -> List[str]:
        """Export in Prometheus format"""
        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} gauge"
        ]

        with self._lock:
            for label_key, value in self._values.items():
                if label_key:
                    labels_str = ",".join(f'{k}="{v}"' for k, v in label_key)
                    lines.append(f'{self.name}{{{labels_str}}} {value}')
                else:
                    lines.append(f'{self.name} {value}')

        return lines


class MetricsCollector:
    """
    Central metrics collector for Growth Engine.

    Collects and exports Prometheus-compatible metrics for:
    - Agent execution (time, status, insights)
    - Swarm communication (messages, blackboard, collaborations)
    - LLM usage (tokens, cost, latency)
    - Analysis requests (throughput, errors)
    """

    def __init__(self):
        self._metrics: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._initialize_metrics()

    def _initialize_metrics(self):
        """Initialize all metrics"""

        # ============== AGENT METRICS ==============

        # Agent execution counter
        self._metrics['agent_executions_total'] = Counter(
            'growth_engine_agent_executions_total',
            'Total number of agent executions',
            ['agent_id', 'status']
        )

        # Agent execution duration
        self._metrics['agent_execution_seconds'] = Histogram(
            'growth_engine_agent_execution_seconds',
            'Agent execution duration in seconds',
            ['agent_id'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, float('inf')]
        )

        # Agent insights emitted
        self._metrics['agent_insights_total'] = Counter(
            'growth_engine_agent_insights_total',
            'Total number of insights emitted by agents',
            ['agent_id', 'priority', 'insight_type']
        )

        # Currently running agents
        self._metrics['agents_running'] = Gauge(
            'growth_engine_agents_running',
            'Number of currently running agents',
            ['agent_id']
        )

        # ============== SWARM METRICS ==============

        # Messages sent between agents
        self._metrics['messages_sent_total'] = Counter(
            'growth_engine_messages_sent_total',
            'Total messages sent between agents',
            ['from_agent', 'to_agent', 'message_type']
        )

        # Messages received
        self._metrics['messages_received_total'] = Counter(
            'growth_engine_messages_received_total',
            'Total messages received by agents',
            ['agent_id', 'message_type']
        )

        # Blackboard operations
        self._metrics['blackboard_writes_total'] = Counter(
            'growth_engine_blackboard_writes_total',
            'Total blackboard write operations',
            ['agent_id', 'category']
        )

        self._metrics['blackboard_reads_total'] = Counter(
            'growth_engine_blackboard_reads_total',
            'Total blackboard read operations',
            ['agent_id']
        )

        # Blackboard entries
        self._metrics['blackboard_entries'] = Gauge(
            'growth_engine_blackboard_entries',
            'Current number of entries in blackboard',
            []
        )

        # Collaboration sessions
        self._metrics['collaborations_total'] = Counter(
            'growth_engine_collaborations_total',
            'Total collaboration sessions',
            ['status']  # started, completed, failed, timeout
        )

        self._metrics['collaborations_active'] = Gauge(
            'growth_engine_collaborations_active',
            'Currently active collaboration sessions',
            []
        )

        # ============== LLM METRICS ==============

        # LLM requests
        self._metrics['llm_requests_total'] = Counter(
            'growth_engine_llm_requests_total',
            'Total LLM API requests',
            ['agent_id', 'model', 'status']
        )

        # LLM latency
        self._metrics['llm_request_seconds'] = Histogram(
            'growth_engine_llm_request_seconds',
            'LLM request latency in seconds',
            ['agent_id', 'model'],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, float('inf')]
        )

        # LLM tokens
        self._metrics['llm_tokens_total'] = Counter(
            'growth_engine_llm_tokens_total',
            'Total LLM tokens used',
            ['agent_id', 'model', 'token_type']  # input, output
        )

        # LLM cost (estimated)
        self._metrics['llm_cost_usd_total'] = Counter(
            'growth_engine_llm_cost_usd_total',
            'Estimated LLM API cost in USD',
            ['agent_id', 'model']
        )

        # ============== ANALYSIS METRICS ==============

        # Analysis requests
        self._metrics['analysis_requests_total'] = Counter(
            'growth_engine_analysis_requests_total',
            'Total analysis requests',
            ['status', 'language']
        )

        # Analysis duration
        self._metrics['analysis_duration_seconds'] = Histogram(
            'growth_engine_analysis_duration_seconds',
            'Full analysis duration in seconds',
            ['language'],
            buckets=[5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, float('inf')]
        )

        # Analysis scores
        self._metrics['analysis_score'] = Histogram(
            'growth_engine_analysis_score',
            'Analysis overall scores',
            [],
            buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        )

        # Competitors analyzed
        self._metrics['competitors_analyzed_total'] = Counter(
            'growth_engine_competitors_analyzed_total',
            'Total competitors analyzed',
            []
        )

        # ============== ERROR METRICS ==============

        # Errors by type
        self._metrics['errors_total'] = Counter(
            'growth_engine_errors_total',
            'Total errors',
            ['agent_id', 'error_type']
        )

        # Security events
        self._metrics['security_events_total'] = Counter(
            'growth_engine_security_events_total',
            'Security-related events (injection attempts, validation failures)',
            ['event_type']
        )

    def export(self) -> str:
        """Export all metrics in Prometheus format"""
        lines = []

        with self._lock:
            for metric in self._metrics.values():
                lines.extend(metric.export())
                lines.append("")  # Empty line between metrics

        return "\n".join(lines)

    def export_dict(self) -> Dict[str, Any]:
        """Export metrics as dictionary (for JSON API)"""
        result = {}

        with self._lock:
            for name, metric in self._metrics.items():
                if isinstance(metric, Counter):
                    result[name] = dict(metric._values)
                elif isinstance(metric, Gauge):
                    result[name] = dict(metric._values)
                elif isinstance(metric, Histogram):
                    result[name] = dict(metric._data)

        return result

    def reset(self):
        """Reset all metrics (useful for testing)"""
        with self._lock:
            self._initialize_metrics()

    # ============== METRIC RECORDING METHODS ==============

    def record_agent_execution(self, agent_id: str, duration_seconds: float, status: str):
        """Record agent execution metrics"""
        self._metrics['agent_executions_total'].inc(agent_id=agent_id, status=status)
        self._metrics['agent_execution_seconds'].observe(duration_seconds, agent_id=agent_id)

    def record_agent_insight(self, agent_id: str, priority: str, insight_type: str):
        """Record agent insight emission"""
        self._metrics['agent_insights_total'].inc(
            agent_id=agent_id,
            priority=priority,
            insight_type=insight_type
        )

    def record_message_sent(self, from_agent: str, to_agent: str, message_type: str):
        """Record message sent"""
        self._metrics['messages_sent_total'].inc(
            from_agent=from_agent,
            to_agent=to_agent or 'broadcast',
            message_type=message_type
        )

    def record_message_received(self, agent_id: str, message_type: str):
        """Record message received"""
        self._metrics['messages_received_total'].inc(
            agent_id=agent_id,
            message_type=message_type
        )

    def record_blackboard_write(self, agent_id: str, category: str = 'default'):
        """Record blackboard write"""
        self._metrics['blackboard_writes_total'].inc(agent_id=agent_id, category=category)

    def record_blackboard_read(self, agent_id: str):
        """Record blackboard read"""
        self._metrics['blackboard_reads_total'].inc(agent_id=agent_id)

    def set_blackboard_entries(self, count: int):
        """Set current blackboard entry count"""
        self._metrics['blackboard_entries'].set(count)

    def record_collaboration(self, status: str):
        """Record collaboration session"""
        self._metrics['collaborations_total'].inc(status=status)

    def set_active_collaborations(self, count: int):
        """Set active collaboration count"""
        self._metrics['collaborations_active'].set(count)

    def record_llm_request(self, agent_id: str, model: str, status: str,
                           duration_seconds: float = None,
                           input_tokens: int = None, output_tokens: int = None,
                           cost_usd: float = None):
        """Record LLM request metrics"""
        self._metrics['llm_requests_total'].inc(agent_id=agent_id, model=model, status=status)

        if duration_seconds is not None:
            self._metrics['llm_request_seconds'].observe(duration_seconds, agent_id=agent_id, model=model)

        if input_tokens is not None:
            self._metrics['llm_tokens_total'].inc(input_tokens, agent_id=agent_id, model=model, token_type='input')

        if output_tokens is not None:
            self._metrics['llm_tokens_total'].inc(output_tokens, agent_id=agent_id, model=model, token_type='output')

        if cost_usd is not None:
            self._metrics['llm_cost_usd_total'].inc(cost_usd, agent_id=agent_id, model=model)

    def record_analysis(self, status: str, language: str, duration_seconds: float = None,
                       score: int = None, competitor_count: int = None):
        """Record analysis request metrics"""
        self._metrics['analysis_requests_total'].inc(status=status, language=language)

        if duration_seconds is not None:
            self._metrics['analysis_duration_seconds'].observe(duration_seconds, language=language)

        if score is not None:
            self._metrics['analysis_score'].observe(score)

        if competitor_count is not None:
            self._metrics['competitors_analyzed_total'].inc(competitor_count)

    def record_error(self, agent_id: str, error_type: str):
        """Record error"""
        self._metrics['errors_total'].inc(agent_id=agent_id, error_type=error_type)

    def record_security_event(self, event_type: str):
        """Record security event"""
        self._metrics['security_events_total'].inc(event_type=event_type)

    def set_agent_running(self, agent_id: str, running: bool):
        """Set agent running status"""
        if running:
            self._metrics['agents_running'].inc(agent_id=agent_id)
        else:
            self._metrics['agents_running'].dec(agent_id=agent_id)

    @contextmanager
    def track_agent_execution(self, agent_id: str):
        """Context manager to track agent execution time"""
        self.set_agent_running(agent_id, True)
        start_time = time.time()
        status = 'complete'

        try:
            yield
        except Exception as e:
            status = 'error'
            self.record_error(agent_id, type(e).__name__)
            raise
        finally:
            duration = time.time() - start_time
            self.record_agent_execution(agent_id, duration, status)
            self.set_agent_running(agent_id, False)

    @contextmanager
    def track_llm_request(self, agent_id: str, model: str = 'gpt-4'):
        """Context manager to track LLM request"""
        start_time = time.time()
        status = 'success'

        try:
            yield
        except Exception:
            status = 'error'
            raise
        finally:
            duration = time.time() - start_time
            self._metrics['llm_requests_total'].inc(agent_id=agent_id, model=model, status=status)
            self._metrics['llm_request_seconds'].observe(duration, agent_id=agent_id, model=model)


# ============== SINGLETON INSTANCE ==============

_metrics_collector: Optional[MetricsCollector] = None
_lock = threading.Lock()


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector instance"""
    global _metrics_collector

    if _metrics_collector is None:
        with _lock:
            if _metrics_collector is None:
                _metrics_collector = MetricsCollector()

    return _metrics_collector


def reset_metrics():
    """Reset metrics (useful for testing)"""
    global _metrics_collector

    with _lock:
        if _metrics_collector is not None:
            _metrics_collector.reset()


# ============== CONVENIENCE FUNCTIONS ==============

def agent_execution_started(agent_id: str):
    """Record agent execution started"""
    get_metrics().set_agent_running(agent_id, True)


def agent_execution_completed(agent_id: str, duration_ms: int, status: str):
    """Record agent execution completed"""
    collector = get_metrics()
    collector.record_agent_execution(agent_id, duration_ms / 1000.0, status)
    collector.set_agent_running(agent_id, False)


def agent_execution_failed(agent_id: str, duration_ms: int, error_type: str):
    """Record agent execution failed"""
    collector = get_metrics()
    collector.record_agent_execution(agent_id, duration_ms / 1000.0, 'error')
    collector.record_error(agent_id, error_type)
    collector.set_agent_running(agent_id, False)


def agent_insight_emitted(agent_id: str, priority: str, insight_type: str):
    """Record agent insight emitted"""
    get_metrics().record_agent_insight(agent_id, priority, insight_type)


def message_sent(from_agent: str, to_agent: Optional[str], message_type: str):
    """Record message sent"""
    get_metrics().record_message_sent(from_agent, to_agent, message_type)


def message_received(agent_id: str, message_type: str):
    """Record message received"""
    get_metrics().record_message_received(agent_id, message_type)


def blackboard_write(agent_id: str, category: str = 'default'):
    """Record blackboard write"""
    get_metrics().record_blackboard_write(agent_id, category)


def blackboard_read(agent_id: str):
    """Record blackboard read"""
    get_metrics().record_blackboard_read(agent_id)


def collaboration_started():
    """Record collaboration started"""
    collector = get_metrics()
    collector.record_collaboration('started')
    collector._metrics['collaborations_active'].inc()


def collaboration_completed(success: bool):
    """Record collaboration completed"""
    collector = get_metrics()
    collector.record_collaboration('completed' if success else 'failed')
    collector._metrics['collaborations_active'].dec()


def llm_request_started(agent_id: str, model: str = 'gpt-4'):
    """Start tracking LLM request (returns start time)"""
    return time.time()


def llm_request_completed(agent_id: str, model: str, start_time: float,
                          input_tokens: int = None, output_tokens: int = None):
    """Record LLM request completed"""
    duration = time.time() - start_time

    # Estimate cost (simplified)
    cost = 0.0
    if input_tokens:
        cost += input_tokens * 0.00003  # $0.03 per 1K input tokens (GPT-4)
    if output_tokens:
        cost += output_tokens * 0.00006  # $0.06 per 1K output tokens (GPT-4)

    get_metrics().record_llm_request(
        agent_id=agent_id,
        model=model,
        status='success',
        duration_seconds=duration,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost
    )


def analysis_started():
    """Record analysis started (returns start time)"""
    return time.time()


def analysis_completed(start_time: float, language: str, success: bool,
                       score: int = None, competitor_count: int = None):
    """Record analysis completed"""
    duration = time.time() - start_time

    get_metrics().record_analysis(
        status='success' if success else 'error',
        language=language,
        duration_seconds=duration,
        score=score,
        competitor_count=competitor_count
    )
