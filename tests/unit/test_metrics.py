# -*- coding: utf-8 -*-
"""
Tests for observability metrics module
"""

import pytest
import time
from agents.observability.metrics import (
    MetricsCollector,
    Counter,
    Gauge,
    Histogram,
    get_metrics,
    reset_metrics,
    agent_execution_started,
    agent_execution_completed,
    agent_execution_failed,
    agent_insight_emitted,
    message_sent,
    message_received,
    blackboard_write,
    blackboard_read,
    collaboration_started,
    collaboration_completed,
    llm_request_started,
    llm_request_completed,
    analysis_started,
    analysis_completed,
)


@pytest.fixture(autouse=True)
def reset_metrics_before_each():
    """Reset metrics before each test"""
    reset_metrics()
    yield
    reset_metrics()


class TestCounter:
    """Tests for Counter metric type"""

    def test_counter_increment(self):
        """Counter increments correctly"""
        counter = Counter('test_counter', 'Test counter', ['label1'])
        counter.inc(label1='value1')
        counter.inc(label1='value1')
        counter.inc(label1='value2')

        assert counter._values[(('label1', 'value1'),)] == 2.0
        assert counter._values[(('label1', 'value2'),)] == 1.0

    def test_counter_increment_by_value(self):
        """Counter increments by specific value"""
        counter = Counter('test_counter', 'Test counter', ['label1'])
        counter.inc(5.0, label1='value1')

        assert counter._values[(('label1', 'value1'),)] == 5.0

    def test_counter_export(self):
        """Counter exports in Prometheus format"""
        counter = Counter('test_counter', 'Test counter', ['label1'])
        counter.inc(label1='value1')

        output = counter.export()
        assert '# HELP test_counter Test counter' in output
        assert '# TYPE test_counter counter' in output
        assert 'test_counter{label1="value1"} 1.0' in output


class TestGauge:
    """Tests for Gauge metric type"""

    def test_gauge_set(self):
        """Gauge sets value correctly"""
        gauge = Gauge('test_gauge', 'Test gauge', ['label1'])
        gauge.set(10.0, label1='value1')

        assert gauge._values[(('label1', 'value1'),)] == 10.0

    def test_gauge_inc_dec(self):
        """Gauge increments and decrements"""
        gauge = Gauge('test_gauge', 'Test gauge', ['label1'])
        gauge.set(10.0, label1='value1')
        gauge.inc(5.0, label1='value1')
        gauge.dec(3.0, label1='value1')

        assert gauge._values[(('label1', 'value1'),)] == 12.0

    def test_gauge_export(self):
        """Gauge exports in Prometheus format"""
        gauge = Gauge('test_gauge', 'Test gauge', ['label1'])
        gauge.set(42.0, label1='value1')

        output = gauge.export()
        assert '# TYPE test_gauge gauge' in output
        assert 'test_gauge{label1="value1"} 42.0' in output


class TestHistogram:
    """Tests for Histogram metric type"""

    def test_histogram_observe(self):
        """Histogram records observations"""
        histogram = Histogram('test_histogram', 'Test histogram', ['label1'],
                             buckets=[1.0, 5.0, 10.0, float('inf')])
        histogram.observe(0.5, label1='value1')
        histogram.observe(3.0, label1='value1')
        histogram.observe(7.0, label1='value1')

        data = histogram._data[(('label1', 'value1'),)]
        assert data['count'] == 3
        assert data['sum'] == 10.5  # 0.5 + 3.0 + 7.0

    def test_histogram_buckets(self):
        """Histogram bucket counts are correct"""
        histogram = Histogram('test_histogram', 'Test histogram', ['label1'],
                             buckets=[1.0, 5.0, 10.0, float('inf')])

        histogram.observe(0.5, label1='value1')  # <= 1.0, 5.0, 10.0, inf
        histogram.observe(3.0, label1='value1')  # <= 5.0, 10.0, inf
        histogram.observe(7.0, label1='value1')  # <= 10.0, inf

        data = histogram._data[(('label1', 'value1'),)]
        assert data['buckets'][1.0] == 1   # Only 0.5
        assert data['buckets'][5.0] == 2   # 0.5, 3.0
        assert data['buckets'][10.0] == 3  # 0.5, 3.0, 7.0
        assert data['buckets'][float('inf')] == 3

    def test_histogram_export(self):
        """Histogram exports in Prometheus format"""
        histogram = Histogram('test_histogram', 'Test histogram', ['label1'],
                             buckets=[1.0, 5.0, float('inf')])
        histogram.observe(0.5, label1='value1')

        output = histogram.export()
        assert '# TYPE test_histogram histogram' in output
        assert '_bucket' in '\n'.join(output)
        assert '_sum' in '\n'.join(output)
        assert '_count' in '\n'.join(output)


class TestMetricsCollector:
    """Tests for MetricsCollector"""

    def test_collector_initialization(self):
        """Collector initializes with all metrics"""
        collector = MetricsCollector()

        assert 'agent_executions_total' in collector._metrics
        assert 'agent_execution_seconds' in collector._metrics
        assert 'messages_sent_total' in collector._metrics
        assert 'llm_requests_total' in collector._metrics
        assert 'analysis_requests_total' in collector._metrics

    def test_record_agent_execution(self):
        """Record agent execution metrics"""
        collector = MetricsCollector()
        collector.record_agent_execution('scout', 1.5, 'complete')

        # Check counter
        counter = collector._metrics['agent_executions_total']
        assert counter._values[(('agent_id', 'scout'), ('status', 'complete'))] == 1.0

    def test_record_message_sent(self):
        """Record message sent metrics"""
        collector = MetricsCollector()
        collector.record_message_sent('scout', 'analyst', 'FINDING')

        counter = collector._metrics['messages_sent_total']
        key = (('from_agent', 'scout'), ('message_type', 'FINDING'), ('to_agent', 'analyst'))
        assert counter._values[key] == 1.0

    def test_record_message_broadcast(self):
        """Record broadcast message metrics"""
        collector = MetricsCollector()
        collector.record_message_sent('scout', None, 'ALERT')

        counter = collector._metrics['messages_sent_total']
        key = (('from_agent', 'scout'), ('message_type', 'ALERT'), ('to_agent', 'broadcast'))
        assert counter._values[key] == 1.0

    def test_record_blackboard_operations(self):
        """Record blackboard operations"""
        collector = MetricsCollector()
        collector.record_blackboard_write('scout', 'competitor')
        collector.record_blackboard_read('analyst')

        write_counter = collector._metrics['blackboard_writes_total']
        read_counter = collector._metrics['blackboard_reads_total']

        assert write_counter._values[(('agent_id', 'scout'), ('category', 'competitor'))] == 1.0
        assert read_counter._values[(('agent_id', 'analyst'),)] == 1.0

    def test_record_llm_request(self):
        """Record LLM request metrics"""
        collector = MetricsCollector()
        collector.record_llm_request(
            agent_id='analyst',
            model='gpt-4',
            status='success',
            duration_seconds=2.5,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.06
        )

        requests = collector._metrics['llm_requests_total']
        tokens = collector._metrics['llm_tokens_total']
        cost = collector._metrics['llm_cost_usd_total']

        assert requests._values[(('agent_id', 'analyst'), ('model', 'gpt-4'), ('status', 'success'))] == 1.0
        assert tokens._values[(('agent_id', 'analyst'), ('model', 'gpt-4'), ('token_type', 'input'))] == 1000
        assert tokens._values[(('agent_id', 'analyst'), ('model', 'gpt-4'), ('token_type', 'output'))] == 500

    def test_record_analysis(self):
        """Record analysis metrics"""
        collector = MetricsCollector()
        collector.record_analysis(
            status='success',
            language='fi',
            duration_seconds=45.0,
            score=75,
            competitor_count=5
        )

        requests = collector._metrics['analysis_requests_total']
        competitors = collector._metrics['competitors_analyzed_total']

        assert requests._values[(('language', 'fi'), ('status', 'success'))] == 1.0
        assert competitors._values[()] == 5.0

    def test_export_prometheus_format(self):
        """Export metrics in Prometheus format"""
        collector = MetricsCollector()
        collector.record_agent_execution('scout', 1.0, 'complete')

        output = collector.export()
        assert 'growth_engine_agent_executions_total' in output
        assert 'scout' in output

    def test_export_dict_format(self):
        """Export metrics as dictionary"""
        collector = MetricsCollector()
        collector.record_agent_execution('scout', 1.0, 'complete')

        output = collector.export_dict()
        assert 'agent_executions_total' in output

    def test_reset(self):
        """Reset clears all metrics"""
        collector = MetricsCollector()
        collector.record_agent_execution('scout', 1.0, 'complete')
        collector.reset()

        counter = collector._metrics['agent_executions_total']
        assert len(counter._values) == 0

    def test_track_agent_execution_context_manager(self):
        """Context manager tracks agent execution"""
        collector = MetricsCollector()

        with collector.track_agent_execution('scout'):
            time.sleep(0.01)  # Small delay

        # Should have recorded execution
        counter = collector._metrics['agent_executions_total']
        assert (('agent_id', 'scout'), ('status', 'complete')) in counter._values

    def test_track_agent_execution_error(self):
        """Context manager handles errors"""
        collector = MetricsCollector()

        with pytest.raises(ValueError):
            with collector.track_agent_execution('scout'):
                raise ValueError("Test error")

        # Should have recorded error
        counter = collector._metrics['agent_executions_total']
        assert (('agent_id', 'scout'), ('status', 'error')) in counter._values


class TestConvenienceFunctions:
    """Tests for convenience functions"""

    def test_agent_execution_started(self):
        """agent_execution_started updates running gauge"""
        agent_execution_started('scout')

        gauge = get_metrics()._metrics['agents_running']
        assert gauge._values[(('agent_id', 'scout'),)] == 1.0

    def test_agent_execution_completed(self):
        """agent_execution_completed records metrics"""
        agent_execution_started('scout')
        agent_execution_completed('scout', 1500, 'complete')

        collector = get_metrics()
        counter = collector._metrics['agent_executions_total']
        assert (('agent_id', 'scout'), ('status', 'complete')) in counter._values

    def test_agent_execution_failed(self):
        """agent_execution_failed records error"""
        agent_execution_started('scout')
        agent_execution_failed('scout', 500, 'ValueError')

        collector = get_metrics()
        errors = collector._metrics['errors_total']
        assert (('agent_id', 'scout'), ('error_type', 'ValueError')) in errors._values

    def test_agent_insight_emitted(self):
        """agent_insight_emitted records insight"""
        agent_insight_emitted('scout', 'HIGH', 'FINDING')

        counter = get_metrics()._metrics['agent_insights_total']
        assert counter._values[(('agent_id', 'scout'), ('insight_type', 'FINDING'), ('priority', 'HIGH'))] == 1.0

    def test_message_functions(self):
        """message_sent and message_received work"""
        message_sent('scout', 'analyst', 'DATA')
        message_received('analyst', 'DATA')

        collector = get_metrics()
        sent = collector._metrics['messages_sent_total']
        received = collector._metrics['messages_received_total']

        assert len(sent._values) == 1
        assert len(received._values) == 1

    def test_blackboard_functions(self):
        """blackboard_write and blackboard_read work"""
        blackboard_write('scout', 'competitor')
        blackboard_read('analyst')

        collector = get_metrics()
        writes = collector._metrics['blackboard_writes_total']
        reads = collector._metrics['blackboard_reads_total']

        assert len(writes._values) == 1
        assert len(reads._values) == 1

    def test_collaboration_functions(self):
        """collaboration_started and collaboration_completed work"""
        collaboration_started()
        collaboration_completed(success=True)

        collector = get_metrics()
        total = collector._metrics['collaborations_total']

        assert total._values[(('status', 'started'),)] == 1.0
        assert total._values[(('status', 'completed'),)] == 1.0

    def test_llm_request_functions(self):
        """llm_request_started and llm_request_completed work"""
        start = llm_request_started('analyst', 'gpt-4')
        time.sleep(0.01)
        llm_request_completed('analyst', 'gpt-4', start, input_tokens=100, output_tokens=50)

        collector = get_metrics()
        requests = collector._metrics['llm_requests_total']
        assert (('agent_id', 'analyst'), ('model', 'gpt-4'), ('status', 'success')) in requests._values

    def test_analysis_functions(self):
        """analysis_started and analysis_completed work"""
        start = analysis_started()
        time.sleep(0.01)
        analysis_completed(start, 'fi', success=True, score=75, competitor_count=3)

        collector = get_metrics()
        requests = collector._metrics['analysis_requests_total']
        assert (('language', 'fi'), ('status', 'success')) in requests._values


class TestGetMetricsSingleton:
    """Tests for get_metrics singleton"""

    def test_returns_same_instance(self):
        """get_metrics returns same instance"""
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_reset_clears_data(self):
        """reset_metrics clears data but keeps instance"""
        collector = get_metrics()
        collector.record_agent_execution('scout', 1.0, 'complete')

        reset_metrics()

        counter = get_metrics()._metrics['agent_executions_total']
        assert len(counter._values) == 0


class TestSecurityMetrics:
    """Tests for security-related metrics"""

    def test_record_security_event(self):
        """Record security event"""
        collector = MetricsCollector()
        collector.record_security_event('injection_attempt')
        collector.record_security_event('validation_failure')
        collector.record_security_event('injection_attempt')

        counter = collector._metrics['security_events_total']
        assert counter._values[(('event_type', 'injection_attempt'),)] == 2.0
        assert counter._values[(('event_type', 'validation_failure'),)] == 1.0
