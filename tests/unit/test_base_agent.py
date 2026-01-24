# -*- coding: utf-8 -*-
"""
Unit tests for BaseAgent

Tests:
- Agent initialization
- Insight emission
- Progress updates
- Swarm stats tracking
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch

from agents.base_agent import BaseAgent
from agents.agent_types import (
    AnalysisContext,
    AgentStatus,
    AgentPriority,
    InsightType,
    AgentInsight,
    AgentProgress,
    AgentResult,
    SwarmEvent,
    SwarmEventType
)
from agents.communication import MessageType, MessagePriority


# =============================================================================
# CONCRETE TEST AGENT
# =============================================================================

class ConcreteAgent(BaseAgent):
    """
    Concrete implementation of BaseAgent for testing.
    Minimal implementation that allows testing base functionality.
    """

    def __init__(self, agent_id: str = "test_agent", name: str = "TestAgent"):
        super().__init__(
            agent_id=agent_id,
            name=name,
            role="Testaaja",
            avatar="",
            personality="Test personality"
        )
        self.execute_called = False
        self.execute_result = {'test': 'data'}

    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """Minimal execute implementation"""
        self.execute_called = True
        self._emit_insight(
            "Test insight",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        self._update_progress(50, "Testing...")
        return self.execute_result


class FailingAgent(BaseAgent):
    """Agent that raises an exception during execute"""

    def __init__(self):
        super().__init__(
            agent_id="failing_agent",
            name="FailingAgent",
            role="Fails",
            avatar=""
        )

    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        raise ValueError("Intentional test failure")


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================

class TestAgentInitialization:
    """Tests for agent initialization"""

    def test_agent_initialization_basic(self):
        """Test basic agent initialization with required parameters"""
        agent = ConcreteAgent(agent_id="scout", name="Scout")

        assert agent.id == "scout"
        assert agent.name == "Scout"
        assert agent.role == "Testaaja"
        assert agent.avatar == ""
        assert agent.personality == "Test personality"

    def test_agent_initialization_default_state(self):
        """Test default agent state after initialization"""
        agent = ConcreteAgent()

        assert agent.status == AgentStatus.IDLE
        assert agent.progress == 0
        assert agent.current_task is None
        assert agent.insights == []
        assert agent.result is None
        assert agent.error is None
        assert agent.start_time is None
        assert agent.end_time is None

    def test_agent_initialization_swarm_state(self):
        """Test swarm-related state after initialization"""
        agent = ConcreteAgent()

        assert agent._swarm_initialized is False
        assert agent._message_bus is None
        assert agent._blackboard is None
        assert agent._collaboration_manager is None
        assert agent._task_manager is None
        assert agent._learning_system is None

    def test_agent_initialization_swarm_stats(self):
        """Test initial swarm stats"""
        agent = ConcreteAgent()

        expected_stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'blackboard_writes': 0,
            'blackboard_reads': 0,
            'collaborations': 0,
            'tasks_delegated': 0
        }
        assert agent._swarm_stats == expected_stats

    def test_agent_initialization_language_default(self):
        """Test default language is Finnish"""
        agent = ConcreteAgent()
        assert agent._language == "fi"

    def test_agent_initialization_empty_dependencies(self):
        """Test dependencies list is empty by default"""
        agent = ConcreteAgent()
        assert agent.dependencies == []

    def test_agent_to_info_dict(self):
        """Test agent info dict generation"""
        agent = ConcreteAgent(agent_id="test", name="Test")
        agent.status = AgentStatus.RUNNING
        agent.progress = 50

        info = agent.to_info_dict()

        assert info['id'] == "test"
        assert info['name'] == "Test"
        assert info['role'] == "Testaaja"
        assert info['avatar'] == ""
        assert info['personality'] == "Test personality"
        assert info['status'] == "running"
        assert info['progress'] == 50
        assert info['dependencies'] == []


# =============================================================================
# INSIGHT EMISSION TESTS
# =============================================================================

class TestInsightEmission:
    """Tests for insight emission functionality"""

    def test_emit_insight_basic(self):
        """Test basic insight emission"""
        agent = ConcreteAgent()

        agent._emit_insight(
            message="Test finding",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )

        assert len(agent.insights) == 1
        insight = agent.insights[0]
        assert insight.message == "Test finding"
        assert insight.priority == AgentPriority.MEDIUM
        assert insight.insight_type == InsightType.FINDING
        assert insight.agent_id == "test_agent"
        assert insight.agent_name == "TestAgent"

    @pytest.mark.asyncio
    async def test_emit_insight_with_data(self):
        """Test insight emission with data payload"""
        agent = ConcreteAgent()
        data = {'key': 'value', 'count': 5}

        agent._emit_insight(
            message="Test with data",
            priority=AgentPriority.HIGH,
            insight_type=InsightType.FINDING,
            data=data
        )

        insight = agent.insights[0]
        assert insight.data == data

    @pytest.mark.asyncio
    async def test_emit_insight_with_collaboration_metadata(self):
        """Test insight emission with collaboration metadata"""
        agent = ConcreteAgent()

        agent._emit_insight(
            message="Collaborative insight",
            priority=AgentPriority.HIGH,
            insight_type=InsightType.COLLABORATION,
            from_collaboration=True,
            contributing_agents=['agent1', 'agent2']
        )

        insight = agent.insights[0]
        assert insight.from_collaboration is True
        assert insight.contributing_agents == ['agent1', 'agent2']

    def test_emit_insight_callback_called(self, capture_insights):
        """Test that insight callback is called"""
        captured, callback = capture_insights
        agent = ConcreteAgent()
        agent.set_callbacks(on_insight=callback)

        agent._emit_insight(
            message="Callback test",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )

        assert len(captured) == 1
        assert captured[0].message == "Callback test"

    def test_emit_insight_callback_error_handled(self):
        """Test that callback errors are handled gracefully"""
        agent = ConcreteAgent()

        def failing_callback(insight):
            raise ValueError("Callback error")

        agent.set_callbacks(on_insight=failing_callback)

        # Should not raise
        agent._emit_insight(
            message="Should not fail",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )

        assert len(agent.insights) == 1

    def test_emit_insight_all_types(self):
        """Test emission of all insight types"""
        agent = ConcreteAgent()

        for insight_type in InsightType:
            agent._emit_insight(
                message=f"Test {insight_type.value}",
                priority=AgentPriority.MEDIUM,
                insight_type=insight_type
            )

        assert len(agent.insights) == len(InsightType)

    @pytest.mark.asyncio
    async def test_emit_insight_all_priorities(self):
        """Test emission with all priority levels"""
        agent = ConcreteAgent()

        for priority in AgentPriority:
            agent._emit_insight(
                message=f"Test {priority.value}",
                priority=priority,
                insight_type=InsightType.FINDING
            )

        assert len(agent.insights) == len(AgentPriority)


# =============================================================================
# PROGRESS UPDATE TESTS
# =============================================================================

class TestProgressUpdate:
    """Tests for progress update functionality"""

    def test_update_progress_basic(self):
        """Test basic progress update"""
        agent = ConcreteAgent()

        agent._update_progress(50, "Half done")

        assert agent.progress == 50
        assert agent.current_task == "Half done"

    def test_update_progress_bounds(self):
        """Test progress is bounded between 0 and 100"""
        agent = ConcreteAgent()

        agent._update_progress(-10)
        assert agent.progress == 0

        agent._update_progress(150)
        assert agent.progress == 100

    def test_update_progress_without_task(self):
        """Test progress update without task change"""
        agent = ConcreteAgent()
        agent.current_task = "Previous task"

        agent._update_progress(75)

        assert agent.progress == 75
        assert agent.current_task == "Previous task"

    def test_update_progress_callback_called(self):
        """Test that progress callback is called"""
        agent = ConcreteAgent()
        progress_updates = []

        def callback(progress: AgentProgress):
            progress_updates.append(progress)

        agent.set_callbacks(on_progress=callback)
        agent._update_progress(50, "Testing")

        assert len(progress_updates) == 1
        assert progress_updates[0].progress == 50
        assert progress_updates[0].current_task == "Testing"

    def test_update_progress_includes_swarm_stats(self):
        """Test that progress update includes swarm stats"""
        agent = ConcreteAgent()
        agent._swarm_stats['messages_sent'] = 5
        agent._swarm_stats['messages_received'] = 3

        progress_updates = []

        def callback(progress: AgentProgress):
            progress_updates.append(progress)

        agent.set_callbacks(on_progress=callback)
        agent._update_progress(50)

        progress = progress_updates[0]
        assert progress.messages_sent == 5
        assert progress.messages_received == 3


# =============================================================================
# SWARM STATS TRACKING TESTS
# =============================================================================

class TestSwarmStatsTracking:
    """Tests for swarm statistics tracking"""

    @pytest.mark.asyncio
    async def test_swarm_stats_reset_on_run(self, sample_context, mock_message_bus, mock_blackboard):
        """Test that swarm stats are reset when run() is called"""
        agent = ConcreteAgent()
        agent._swarm_stats['messages_sent'] = 10
        agent._swarm_stats['messages_received'] = 5

        # Mock swarm systems
        with patch.object(agent, '_init_swarm') as mock_init:
            with patch.object(agent, '_broadcast', new_callable=AsyncMock):
                await agent.run(sample_context)

        assert agent._swarm_stats['messages_sent'] == 0
        assert agent._swarm_stats['messages_received'] == 0

    @pytest.mark.asyncio
    async def test_swarm_stats_in_result(self, sample_context):
        """Test that swarm stats are included in AgentResult"""
        agent = ConcreteAgent()

        with patch.object(agent, '_init_swarm'):
            with patch.object(agent, '_broadcast', new_callable=AsyncMock):
                result = await agent.run(sample_context)

        assert 'swarm_stats' in result.__dict__
        assert isinstance(result.swarm_stats, dict)
        assert 'messages_sent' in result.swarm_stats

    def test_swarm_stats_structure(self):
        """Test swarm stats have correct structure"""
        agent = ConcreteAgent()

        expected_keys = [
            'messages_sent',
            'messages_received',
            'blackboard_writes',
            'blackboard_reads',
            'collaborations',
            'tasks_delegated'
        ]

        for key in expected_keys:
            assert key in agent._swarm_stats
            assert isinstance(agent._swarm_stats[key], int)


# =============================================================================
# AGENT EXECUTION TESTS
# =============================================================================

class TestAgentExecution:
    """Tests for agent execution lifecycle"""

    @pytest.mark.asyncio
    async def test_run_sets_status_complete(self, sample_context):
        """Test that run() sets status to COMPLETE on success"""
        agent = ConcreteAgent()

        with patch.object(agent, '_init_swarm'):
            with patch.object(agent, '_broadcast', new_callable=AsyncMock):
                result = await agent.run(sample_context)

        assert result.status == AgentStatus.COMPLETE
        assert agent.status == AgentStatus.COMPLETE

    @pytest.mark.asyncio
    async def test_run_sets_status_error_on_failure(self, sample_context):
        """Test that run() sets status to ERROR on failure"""
        agent = FailingAgent()

        with patch.object(agent, '_init_swarm'):
            with patch.object(agent, '_broadcast', new_callable=AsyncMock):
                result = await agent.run(sample_context)

        assert result.status == AgentStatus.ERROR
        assert agent.status == AgentStatus.ERROR
        assert "Intentional test failure" in result.error

    @pytest.mark.asyncio
    async def test_run_records_execution_time(self, sample_context):
        """Test that execution time is recorded"""
        agent = ConcreteAgent()

        with patch.object(agent, '_init_swarm'):
            with patch.object(agent, '_broadcast', new_callable=AsyncMock):
                result = await agent.run(sample_context)

        # execution_time_ms may be 0 for very fast tests, but timestamps should be set
        assert result.execution_time_ms >= 0
        assert agent.start_time is not None
        assert agent.end_time is not None
        assert agent.end_time >= agent.start_time

    @pytest.mark.asyncio
    async def test_run_calls_execute(self, sample_context):
        """Test that run() calls execute()"""
        agent = ConcreteAgent()

        with patch.object(agent, '_init_swarm'):
            with patch.object(agent, '_broadcast', new_callable=AsyncMock):
                await agent.run(sample_context)

        assert agent.execute_called is True

    @pytest.mark.asyncio
    async def test_run_sets_language_from_context(self, context_factory):
        """Test that language is set from context"""
        context = context_factory(language="en")
        agent = ConcreteAgent()

        with patch.object(agent, '_init_swarm'):
            with patch.object(agent, '_broadcast', new_callable=AsyncMock):
                await agent.run(context)

        assert agent._language == "en"

    @pytest.mark.asyncio
    async def test_run_result_contains_data(self, sample_context):
        """Test that result contains execute() return data"""
        agent = ConcreteAgent()
        agent.execute_result = {'custom': 'data', 'value': 123}

        with patch.object(agent, '_init_swarm'):
            with patch.object(agent, '_broadcast', new_callable=AsyncMock):
                result = await agent.run(sample_context)

        assert result.data == {'custom': 'data', 'value': 123}

    @pytest.mark.asyncio
    async def test_run_includes_insights(self, sample_context):
        """Test that result includes emitted insights"""
        agent = ConcreteAgent()

        with patch.object(agent, '_init_swarm'):
            with patch.object(agent, '_broadcast', new_callable=AsyncMock):
                result = await agent.run(sample_context)

        # ConcreteAgent emits one insight in execute()
        assert len(result.insights) >= 1
        assert any(i.message == "Test insight" for i in result.insights)


# =============================================================================
# CALLBACK TESTS
# =============================================================================

class TestCallbacks:
    """Tests for callback functionality"""

    def test_set_callbacks_all(self, capture_insights, capture_swarm_events):
        """Test setting all callbacks"""
        insights, insight_cb = capture_insights
        events, event_cb = capture_swarm_events
        progress_updates = []

        def progress_cb(p):
            progress_updates.append(p)

        agent = ConcreteAgent()
        agent.set_callbacks(
            on_insight=insight_cb,
            on_progress=progress_cb,
            on_swarm_event=event_cb
        )

        assert agent._on_insight == insight_cb
        assert agent._on_progress == progress_cb
        assert agent._on_swarm_event == event_cb

    def test_set_callbacks_partial(self, capture_insights):
        """Test setting only some callbacks"""
        insights, callback = capture_insights
        agent = ConcreteAgent()

        agent.set_callbacks(on_insight=callback)

        assert agent._on_insight == callback
        assert agent._on_progress is None
        assert agent._on_swarm_event is None


# =============================================================================
# DEPENDENCY RESULTS TESTS
# =============================================================================

class TestDependencyResults:
    """Tests for dependency result access"""

    def test_get_dependency_results_single(self, context_factory, sample_scout_result):
        """Test getting single dependency result"""
        context = context_factory()
        context.agent_results = {'scout': sample_scout_result}

        agent = ConcreteAgent()
        result = agent.get_dependency_results(context, 'scout')

        assert result == sample_scout_result.data
        assert 'company' in result

    def test_get_dependency_results_missing(self, context_factory):
        """Test getting missing dependency returns empty dict"""
        context = context_factory()
        context.agent_results = {}

        agent = ConcreteAgent()
        result = agent.get_dependency_results(context, 'scout')

        assert result == {}

    def test_get_dependency_results_all(
        self,
        context_factory,
        sample_scout_result,
        sample_analyst_result
    ):
        """Test getting all dependency results"""
        context = context_factory()
        context.agent_results = {
            'scout': sample_scout_result,
            'analyst': sample_analyst_result
        }

        agent = ConcreteAgent()
        agent.dependencies = ['scout', 'analyst']

        results = agent.get_dependency_results(context)

        assert 'scout' in results
        assert 'analyst' in results
        assert results['scout'] == sample_scout_result.data
