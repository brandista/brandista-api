# -*- coding: utf-8 -*-
"""
Integration tests for Agent Communication

Tests real inter-agent communication flows:
- Scout to Analyst data flow
- Guardian alert to Strategist
- Blackboard subscription triggers
"""

import pytest
import asyncio
from datetime import datetime
from typing import Dict, Any, List
from unittest.mock import MagicMock, AsyncMock, patch

from agents.base_agent import BaseAgent
from agents.scout_agent import ScoutAgent
from agents.analyst_agent import AnalystAgent
from agents.guardian_agent import GuardianAgent
from agents.strategist_agent import StrategistAgent
from agents.agent_types import (
    AnalysisContext,
    AgentStatus,
    AgentPriority,
    InsightType,
    AgentResult
)
from agents.communication import (
    MessageBus,
    AgentMessage,
    MessageType,
    MessagePriority,
    get_message_bus,
    reset_message_bus
)
from agents.blackboard import (
    Blackboard,
    BlackboardEntry,
    DataCategory,
    get_blackboard,
    reset_blackboard
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def integrated_message_bus():
    """Provide a real message bus for integration tests"""
    reset_message_bus()
    bus = get_message_bus()
    yield bus
    reset_message_bus()


@pytest.fixture
def integrated_blackboard():
    """Provide a real blackboard for integration tests"""
    reset_blackboard()
    bb = get_blackboard()
    yield bb
    reset_blackboard()


@pytest.fixture
def scout_result_data():
    """Sample Scout agent result data"""
    return {
        'company': 'Test Company Oy',
        'url': 'https://testcompany.fi',
        'industry': 'technology',
        'competitor_urls': [
            'https://competitor1.fi',
            'https://competitor2.fi'
        ],
        'competitor_count': 2,
        'discovery_method': 'auto_discovered',
        'competitors_enriched': [
            {
                'url': 'https://competitor1.fi',
                'company_name': 'Competitor One',
                'revenue': 1000000,
                'employees': 15
            },
            {
                'url': 'https://competitor2.fi',
                'company_name': 'Competitor Two',
                'revenue': 500000,
                'employees': 8
            }
        ],
        'your_company_intel': {
            'name': 'Test Company Oy',
            'business_id': '1234567-8',
            'revenue': 750000,
            'employees': 12
        }
    }


@pytest.fixture
def analyst_result_data():
    """Sample Analyst agent result data"""
    return {
        'your_analysis': {
            'final_score': 68,
            'basic_analysis': {
                'digital_maturity_score': 68,
                'title': 'Test Company',
                'meta_description': 'Tech solutions',
                'mobile_ready': True,
                'has_ssl': True,
                'score_breakdown': {
                    'security': 13,
                    'seo_basics': 16,
                    'content': 15,
                    'technical': 12,
                    'mobile': 12
                }
            },
            'detailed_analysis': {
                'technical_audit': {
                    'has_ssl': True,
                    'performance_score': 72
                },
                'content_analysis': {
                    'quality_score': 65,
                    'word_count': 1200
                }
            }
        },
        'competitor_analyses': [
            {
                'url': 'https://competitor1.fi',
                'domain': 'competitor1.fi',
                'final_score': 72,
                'basic_analysis': {'digital_maturity_score': 72}
            },
            {
                'url': 'https://competitor2.fi',
                'domain': 'competitor2.fi',
                'final_score': 55,
                'basic_analysis': {'digital_maturity_score': 55}
            }
        ],
        'benchmark': {
            'your_score': 68,
            'avg_competitor_score': 63,
            'max_competitor_score': 72,
            'min_competitor_score': 55,
            'your_position': 2,
            'total_analyzed': 3
        },
        'category_comparison': {
            'seo': {'your_score': 80, 'competitor_avg': 70, 'difference': 10, 'status': 'ahead'},
            'performance': {'your_score': 72, 'competitor_avg': 75, 'difference': -3, 'status': 'even'},
            'security': {'your_score': 87, 'competitor_avg': 80, 'difference': 7, 'status': 'ahead'},
            'content': {'your_score': 75, 'competitor_avg': 65, 'difference': 10, 'status': 'ahead'}
        },
        'your_score': 68,
        'competitors_enriched': []
    }


# =============================================================================
# SCOUT TO ANALYST DATA FLOW TESTS
# =============================================================================

@pytest.mark.integration
class TestScoutToAnalystDataFlow:
    """Tests for data flow from Scout to Analyst"""

    @pytest.mark.asyncio
    async def test_analyst_receives_scout_results(
        self,
        context_factory,
        scout_result_data,
        integrated_message_bus
    ):
        """Test that Analyst correctly receives and uses Scout's results"""
        # Create context with Scout results
        scout_result = AgentResult(
            agent_id="scout",
            agent_name="Scout",
            status=AgentStatus.COMPLETE,
            execution_time_ms=1000,
            data=scout_result_data
        )

        context = context_factory(url="https://testcompany.fi")
        context.agent_results = {'scout': scout_result}

        # Create Analyst and get dependency results
        analyst = AnalystAgent()
        scout_data = analyst.get_dependency_results(context, 'scout')

        assert scout_data is not None
        assert scout_data['industry'] == 'technology'
        assert len(scout_data['competitor_urls']) == 2

    @pytest.mark.asyncio
    async def test_analyst_uses_scout_competitor_urls(
        self,
        context_factory,
        scout_result_data
    ):
        """Test that Analyst uses competitor URLs from Scout"""
        scout_result = AgentResult(
            agent_id="scout",
            agent_name="Scout",
            status=AgentStatus.COMPLETE,
            execution_time_ms=1000,
            data=scout_result_data
        )

        context = context_factory()
        context.agent_results = {'scout': scout_result}

        analyst = AnalystAgent()
        scout_data = analyst.get_dependency_results(context, 'scout')

        competitor_urls = scout_data.get('competitor_urls', [])
        assert 'https://competitor1.fi' in competitor_urls
        assert 'https://competitor2.fi' in competitor_urls

    @pytest.mark.asyncio
    async def test_scout_publishes_to_blackboard_for_analyst(
        self,
        integrated_blackboard
    ):
        """Test Scout publishes data that Analyst can read"""
        bb = integrated_blackboard

        # Simulate Scout publishing
        await bb.publish(
            key="scout.industry",
            value={
                'detected': 'technology',
                'company': 'Test Company',
                'confidence': 0.8
            },
            agent_id="scout",
            category=DataCategory.ANALYSIS
        )

        await bb.publish(
            key="scout.competitors.discovered",
            value={
                'urls': ['https://comp1.fi', 'https://comp2.fi'],
                'count': 2
            },
            agent_id="scout",
            category=DataCategory.COMPETITOR
        )

        # Analyst reads from blackboard
        industry_data = bb.get("scout.industry")
        competitors_data = bb.get("scout.competitors.discovered")

        assert industry_data['detected'] == 'technology'
        assert competitors_data['count'] == 2

    @pytest.mark.asyncio
    async def test_data_flow_message_chain(
        self,
        integrated_message_bus
    ):
        """Test message flow from Scout to Analyst"""
        bus = integrated_message_bus
        received_messages = []

        async def analyst_callback(msg):
            received_messages.append(msg)

        # Register agents
        bus.register_agent(
            agent_id="scout",
            subscribe_to=[MessageType.REQUEST]
        )
        bus.register_agent(
            agent_id="analyst",
            callback=analyst_callback,
            subscribe_to=[MessageType.DATA, MessageType.FINDING]
        )

        # Scout sends data to Analyst
        message = AgentMessage(
            from_agent="scout",
            to_agent="analyst",
            type=MessageType.DATA,
            subject="Target company intel",
            payload={
                'company_name': 'Test Company',
                'industry': 'technology'
            }
        )

        await bus.send(message)

        assert len(received_messages) == 1
        assert received_messages[0].payload['industry'] == 'technology'


# =============================================================================
# GUARDIAN ALERT TO STRATEGIST TESTS
# =============================================================================

@pytest.mark.integration
class TestGuardianAlertToStrategist:
    """Tests for Guardian alerting Strategist about critical threats"""

    @pytest.mark.asyncio
    async def test_strategist_receives_guardian_alert(
        self,
        integrated_message_bus
    ):
        """Test Strategist receives critical alerts from Guardian"""
        bus = integrated_message_bus
        received_alerts = []

        async def strategist_callback(msg):
            received_alerts.append(msg)

        # Register agents
        bus.register_agent(
            agent_id="guardian",
            subscribe_to=[MessageType.ALERT]
        )
        bus.register_agent(
            agent_id="strategist",
            callback=strategist_callback,
            subscribe_to=[MessageType.ALERT, MessageType.DATA]
        )

        # Guardian sends critical threat alert
        alert = AgentMessage(
            from_agent="guardian",
            to_agent="strategist",
            type=MessageType.ALERT,
            priority=MessagePriority.HIGH,
            subject="Critical threats found: 2",
            payload={
                'critical_threats': [
                    {'category': 'ssl', 'severity': 'critical'},
                    {'category': 'mobile', 'severity': 'high'}
                ],
                'rasm_score': 45,
                'priority_actions': [
                    {'title': 'Add SSL', 'roi_score': 95}
                ]
            }
        )

        await bus.send(alert)

        assert len(received_alerts) == 1
        assert received_alerts[0].priority == MessagePriority.HIGH
        assert len(received_alerts[0].payload['critical_threats']) == 2

    @pytest.mark.asyncio
    async def test_guardian_publishes_threats_to_blackboard(
        self,
        integrated_blackboard
    ):
        """Test Guardian publishes threats that Strategist can read"""
        bb = integrated_blackboard

        # Simulate Guardian publishing threats
        await bb.publish(
            key="guardian.threats.identified",
            value={
                'threats': [
                    {'category': 'ssl', 'severity': 'critical', 'title': 'SSL missing'},
                    {'category': 'seo', 'severity': 'high', 'title': 'Poor SEO'}
                ],
                'rasm_score': 55,
                'critical_count': 1
            },
            agent_id="guardian",
            category=DataCategory.THREAT
        )

        # Strategist queries threats
        threats = bb.query_by_category(DataCategory.THREAT)

        assert len(threats) >= 1
        assert threats[0].value['rasm_score'] == 55

    @pytest.mark.asyncio
    async def test_strategist_uses_guardian_priority_actions(
        self,
        context_factory,
        scout_result_data,
        analyst_result_data
    ):
        """Test Strategist uses Guardian's priority actions"""
        guardian_result = AgentResult(
            agent_id="guardian",
            agent_name="Guardian",
            status=AgentStatus.COMPLETE,
            execution_time_ms=2000,
            data={
                'threats': [
                    {'category': 'ssl', 'severity': 'critical'}
                ],
                'rasm_score': 50,
                'priority_actions': [
                    {
                        'title': 'Add SSL certificate',
                        'category': 'ssl',
                        'severity': 'critical',
                        'impact': 'critical',
                        'effort': 'low',
                        'roi_score': 100
                    },
                    {
                        'title': 'Improve SEO',
                        'category': 'seo',
                        'severity': 'high',
                        'impact': 'high',
                        'effort': 'medium',
                        'roi_score': 75
                    }
                ]
            }
        )

        scout_result = AgentResult(
            agent_id="scout",
            agent_name="Scout",
            status=AgentStatus.COMPLETE,
            execution_time_ms=1000,
            data=scout_result_data
        )

        analyst_result = AgentResult(
            agent_id="analyst",
            agent_name="Analyst",
            status=AgentStatus.COMPLETE,
            execution_time_ms=3000,
            data=analyst_result_data
        )

        context = context_factory()
        context.agent_results = {
            'scout': scout_result,
            'analyst': analyst_result,
            'guardian': guardian_result,
            'prospector': AgentResult(
                agent_id="prospector",
                agent_name="Prospector",
                status=AgentStatus.COMPLETE,
                execution_time_ms=1500,
                data={'growth_opportunities': []}
            )
        }

        strategist = StrategistAgent()
        guardian_data = strategist.get_dependency_results(context, 'guardian')

        assert guardian_data is not None
        assert len(guardian_data['priority_actions']) == 2
        assert guardian_data['priority_actions'][0]['roi_score'] == 100


# =============================================================================
# BLACKBOARD SUBSCRIPTION TRIGGER TESTS
# =============================================================================

@pytest.mark.integration
class TestBlackboardSubscriptionTrigger:
    """Tests for blackboard subscription triggers"""

    @pytest.mark.asyncio
    async def test_subscription_triggers_on_publish(
        self,
        integrated_blackboard
    ):
        """Test that subscriptions are triggered when data is published"""
        bb = integrated_blackboard
        notifications = []

        def on_competitor_data(entry):
            notifications.append(entry)

        # Guardian subscribes to Scout's competitor data
        bb.subscribe(
            pattern="scout.competitors.*",
            agent_id="guardian",
            callback=on_competitor_data
        )

        # Scout publishes competitor data
        await bb.publish(
            key="scout.competitors.discovered",
            value={
                'urls': ['https://comp.fi'],
                'count': 1
            },
            agent_id="scout",
            category=DataCategory.COMPETITOR
        )

        assert len(notifications) == 1
        assert notifications[0].key == "scout.competitors.discovered"

    @pytest.mark.asyncio
    async def test_critical_pattern_subscription(
        self,
        integrated_blackboard
    ):
        """Test subscription to critical findings pattern"""
        bb = integrated_blackboard
        critical_alerts = []

        async def on_critical(entry):
            critical_alerts.append(entry)

        # Subscribe to all critical findings
        bb.subscribe(
            pattern="*.critical",
            agent_id="monitor",
            callback=on_critical
        )

        # Various agents publish critical findings
        await bb.publish(
            key="scout.critical",
            value={'alert': 'High threat competitor'},
            agent_id="scout"
        )

        await bb.publish(
            key="guardian.critical",
            value={'alert': 'SSL missing'},
            agent_id="guardian"
        )

        await bb.publish(
            key="analyst.normal",  # Should NOT trigger
            value={'data': 'normal finding'},
            agent_id="analyst"
        )

        assert len(critical_alerts) == 2

    @pytest.mark.asyncio
    async def test_category_filtered_subscription(
        self,
        integrated_blackboard
    ):
        """Test subscription with category filter"""
        bb = integrated_blackboard
        threat_alerts = []

        def on_threat(entry):
            threat_alerts.append(entry)

        # Subscribe only to threat category
        bb.subscribe(
            pattern="*.*",
            agent_id="strategist",
            callback=on_threat,
            categories={DataCategory.THREAT}
        )

        # Publish different categories
        await bb.publish(
            key="guardian.threat1",
            value={'type': 'ssl'},
            agent_id="guardian",
            category=DataCategory.THREAT
        )

        await bb.publish(
            key="prospector.opportunity1",
            value={'type': 'growth'},
            agent_id="prospector",
            category=DataCategory.OPPORTUNITY  # Should NOT trigger
        )

        assert len(threat_alerts) == 1
        assert threat_alerts[0].category == DataCategory.THREAT

    @pytest.mark.asyncio
    async def test_multiple_subscribers_same_pattern(
        self,
        integrated_blackboard
    ):
        """Test multiple agents subscribing to same pattern"""
        bb = integrated_blackboard
        guardian_received = []
        strategist_received = []

        def guardian_callback(entry):
            guardian_received.append(entry)

        def strategist_callback(entry):
            strategist_received.append(entry)

        # Both subscribe to Scout's findings
        bb.subscribe(
            pattern="scout.*",
            agent_id="guardian",
            callback=guardian_callback
        )
        bb.subscribe(
            pattern="scout.*",
            agent_id="strategist",
            callback=strategist_callback
        )

        # Scout publishes
        await bb.publish(
            key="scout.industry",
            value={'detected': 'technology'},
            agent_id="scout"
        )

        assert len(guardian_received) == 1
        assert len(strategist_received) == 1

    @pytest.mark.asyncio
    async def test_async_callback_in_subscription(
        self,
        integrated_blackboard
    ):
        """Test async callback in subscription"""
        bb = integrated_blackboard
        processed = []

        async def async_processor(entry):
            await asyncio.sleep(0.01)  # Simulate async processing
            processed.append(entry.key)

        bb.subscribe(
            pattern="test.*",
            agent_id="processor",
            callback=async_processor
        )

        await bb.publish(
            key="test.data",
            value="async test",
            agent_id="publisher"
        )

        assert "test.data" in processed


# =============================================================================
# FULL AGENT CHAIN TESTS
# =============================================================================

@pytest.mark.integration
class TestFullAgentChain:
    """Tests for full agent communication chains"""

    @pytest.mark.asyncio
    async def test_data_flows_through_agents(
        self,
        integrated_message_bus,
        integrated_blackboard
    ):
        """Test data flows correctly through agent chain"""
        bus = integrated_message_bus
        bb = integrated_blackboard

        message_log = []

        async def log_message(msg):
            message_log.append({
                'from': msg.from_agent,
                'to': msg.to_agent,
                'type': msg.type.value
            })

        # Register all agents
        for agent_id in ['scout', 'analyst', 'guardian', 'strategist']:
            bus.register_agent(
                agent_id=agent_id,
                callback=log_message,
                subscribe_to=[
                    MessageType.DATA,
                    MessageType.FINDING,
                    MessageType.ALERT
                ]
            )

        # Simulate Scout finding and sharing
        await bus.broadcast(
            from_agent="scout",
            message_type=MessageType.FINDING,
            subject="Discovered 3 competitors",
            payload={'competitor_count': 3}
        )

        # Guardian responds with alert
        await bus.send(AgentMessage(
            from_agent="guardian",
            to_agent="strategist",
            type=MessageType.ALERT,
            subject="Critical threats",
            payload={'threat_count': 2}
        ))

        # Verify message flow
        scout_broadcasts = [m for m in message_log if m['from'] == 'scout']
        guardian_alerts = [m for m in message_log if m['from'] == 'guardian' and m['type'] == 'alert']

        assert len(scout_broadcasts) >= 3  # Broadcast to 3 other agents
        assert len(guardian_alerts) >= 1

    @pytest.mark.asyncio
    async def test_blackboard_data_shared_across_agents(
        self,
        integrated_blackboard
    ):
        """Test blackboard enables data sharing across agents"""
        bb = integrated_blackboard

        # Scout publishes initial data
        await bb.publish(
            key="scout.analysis.complete",
            value={
                'industry': 'technology',
                'competitors': 5
            },
            agent_id="scout",
            category=DataCategory.ANALYSIS
        )

        # Analyst adds to it
        await bb.publish(
            key="analyst.benchmark.complete",
            value={
                'your_score': 68,
                'avg_competitor': 65
            },
            agent_id="analyst",
            category=DataCategory.ANALYSIS
        )

        # Guardian adds threats
        await bb.publish(
            key="guardian.threats.complete",
            value={
                'rasm_score': 72,
                'critical_count': 1
            },
            agent_id="guardian",
            category=DataCategory.THREAT
        )

        # Strategist can query all analysis data
        analysis_entries = bb.query_by_category(DataCategory.ANALYSIS)
        threat_entries = bb.query_by_category(DataCategory.THREAT)

        assert len(analysis_entries) == 2
        assert len(threat_entries) == 1

        # Strategist can get specific data
        scout_data = bb.get("scout.analysis.complete")
        analyst_data = bb.get("analyst.benchmark.complete")

        assert scout_data['industry'] == 'technology'
        assert analyst_data['your_score'] == 68
