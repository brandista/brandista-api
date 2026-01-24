# -*- coding: utf-8 -*-
"""
Growth Engine Swarm - Pytest Configuration and Shared Fixtures

Provides:
- Mock LLM responses (deterministic)
- Mock MessageBus
- Mock Blackboard
- Test context factory
- Cassette-based recording/playback for external calls
"""

import pytest
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Callable
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass, field

# Import the actual classes to be mocked
from agents.communication import (
    MessageBus,
    AgentMessage,
    MessageType,
    MessagePriority,
    DeliveryStatus,
    CircuitBreaker,
    reset_message_bus
)
from agents.blackboard import (
    Blackboard,
    BlackboardEntry,
    DataCategory,
    Subscription,
    reset_blackboard
)
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
from agents.collaboration import (
    CollaborationManager,
    CollaborationSession,
    CollaborationResult,
    VoteType,
    reset_collaboration_manager
)
from agents.task_delegation import (
    TaskDelegationManager,
    DynamicTask,
    TaskStatus,
    TaskPriority,
    reset_task_manager
)

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# =============================================================================
# CASSETTE SYSTEM - Record/Replay external responses
# =============================================================================

@dataclass
class CassetteEntry:
    """A recorded request/response pair"""
    request_key: str
    response_data: Any
    recorded_at: datetime = field(default_factory=datetime.now)


class Cassette:
    """
    Record and replay system for deterministic testing.
    Records external calls (HTTP, LLM, etc.) and replays them in tests.
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self.entries: Dict[str, CassetteEntry] = {}
        self.recording: bool = False
        self.playback: bool = False
        self._call_count: Dict[str, int] = {}

    def start_recording(self):
        """Start recording mode"""
        self.recording = True
        self.playback = False
        self.entries.clear()
        self._call_count.clear()
        logger.info(f"[Cassette:{self.name}] Recording started")

    def start_playback(self):
        """Start playback mode"""
        self.recording = False
        self.playback = True
        self._call_count.clear()
        logger.info(f"[Cassette:{self.name}] Playback started with {len(self.entries)} entries")

    def record(self, request_key: str, response_data: Any):
        """Record a request/response pair"""
        if not self.recording:
            return

        # Support multiple calls with same key
        count = self._call_count.get(request_key, 0)
        full_key = f"{request_key}#{count}"
        self._call_count[request_key] = count + 1

        self.entries[full_key] = CassetteEntry(
            request_key=request_key,
            response_data=response_data
        )
        logger.debug(f"[Cassette:{self.name}] Recorded: {full_key}")

    def replay(self, request_key: str) -> Optional[Any]:
        """Replay a recorded response"""
        if not self.playback:
            return None

        # Support multiple calls with same key
        count = self._call_count.get(request_key, 0)
        full_key = f"{request_key}#{count}"
        self._call_count[request_key] = count + 1

        entry = self.entries.get(full_key)
        if entry:
            logger.debug(f"[Cassette:{self.name}] Replayed: {full_key}")
            return entry.response_data

        logger.warning(f"[Cassette:{self.name}] No recording for: {full_key}")
        return None

    def has_entry(self, request_key: str) -> bool:
        """Check if entry exists for request"""
        count = self._call_count.get(request_key, 0)
        full_key = f"{request_key}#{count}"
        return full_key in self.entries


@pytest.fixture
def cassette():
    """Provide a fresh cassette for each test"""
    return Cassette("test")


# =============================================================================
# MOCK MESSAGE BUS
# =============================================================================

class MockMessageBus:
    """
    Mock MessageBus for testing agent communication.
    Tracks all sent messages and allows inspection.
    """

    def __init__(self):
        self._messages: List[AgentMessage] = []
        self._callbacks: Dict[str, Callable] = {}
        self._subscriptions: Dict[str, Set[MessageType]] = {}
        self._queues: Dict[str, asyncio.Queue] = {}
        self._circuit_breaker = CircuitBreaker()
        self._delivered: List[tuple] = []  # (agent_id, message)

    def register_agent(
        self,
        agent_id: str,
        callback: Optional[Callable] = None,
        subscribe_to: Optional[List[MessageType]] = None
    ):
        """Register an agent with the mock bus"""
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()
        if callback:
            self._callbacks[agent_id] = callback
        if subscribe_to:
            self._subscriptions[agent_id] = set(subscribe_to)
        else:
            self._subscriptions[agent_id] = {
                MessageType.ALERT,
                MessageType.REQUEST,
                MessageType.HELP,
                MessageType.TASK_DELEGATE,
                MessageType.CONSENSUS
            }

    async def send(
        self,
        message: AgentMessage,
        wait_for_response: bool = False,
        timeout: float = 30.0
    ) -> Optional[AgentMessage]:
        """Send a message and track it"""
        self._messages.append(message)

        # Determine recipients
        if message.to_agent:
            recipients = [message.to_agent]
        else:
            # Broadcast to all subscribers of this message type
            recipients = [
                agent_id for agent_id, types in self._subscriptions.items()
                if message.type in types and agent_id != message.from_agent
            ]

        # Deliver to recipients
        for recipient in recipients:
            self._delivered.append((recipient, message))
            if recipient in self._callbacks:
                callback = self._callbacks[recipient]
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(message)
                    else:
                        callback(message)
                except Exception as e:
                    logger.error(f"MockMessageBus callback error: {e}")

        return None

    async def broadcast(
        self,
        from_agent: str,
        message_type: MessageType,
        subject: str,
        payload: Dict[str, Any],
        priority: MessagePriority = MessagePriority.MEDIUM,
        tags: Optional[Set[str]] = None
    ) -> bool:
        """Broadcast a message"""
        message = AgentMessage(
            from_agent=from_agent,
            to_agent=None,
            type=message_type,
            priority=priority,
            subject=subject,
            payload=payload,
            tags=tags or set()
        )
        await self.send(message)
        return True

    def get_sent_messages(self) -> List[AgentMessage]:
        """Get all sent messages"""
        return self._messages.copy()

    def get_messages_to(self, agent_id: str) -> List[AgentMessage]:
        """Get messages sent to specific agent"""
        return [msg for agent, msg in self._delivered if agent == agent_id]

    def get_messages_from(self, agent_id: str) -> List[AgentMessage]:
        """Get messages sent from specific agent"""
        return [msg for msg in self._messages if msg.from_agent == agent_id]

    def get_messages_of_type(self, message_type: MessageType) -> List[AgentMessage]:
        """Get messages of specific type"""
        return [msg for msg in self._messages if msg.type == message_type]

    def clear(self):
        """Clear all messages"""
        self._messages.clear()
        self._delivered.clear()

    def reset(self):
        """Full reset"""
        self._messages.clear()
        self._callbacks.clear()
        self._subscriptions.clear()
        self._queues.clear()
        self._delivered.clear()


@pytest.fixture
def mock_message_bus():
    """Provide a fresh mock message bus"""
    bus = MockMessageBus()
    yield bus
    bus.reset()


@pytest.fixture
def real_message_bus():
    """Provide a real message bus for integration tests"""
    reset_message_bus()
    from agents.communication import get_message_bus
    bus = get_message_bus()
    yield bus
    reset_message_bus()


# =============================================================================
# MOCK BLACKBOARD
# =============================================================================

class MockBlackboard:
    """
    Mock Blackboard for testing shared memory operations.
    Tracks all publications and allows inspection.
    """

    def __init__(self):
        self._data: Dict[str, BlackboardEntry] = {}
        self._subscriptions: Dict[str, List[Subscription]] = {}
        self._history: List[BlackboardEntry] = []
        self._notifications: List[tuple] = []  # (agent_id, entry)

    async def publish(
        self,
        key: str,
        value: Any,
        agent_id: str,
        ttl: Optional[int] = None,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        category: Optional[DataCategory] = None
    ) -> BlackboardEntry:
        """Publish data to blackboard"""
        existing = self._data.get(key)
        version = (existing.version + 1) if existing else 1

        entry = BlackboardEntry(
            key=key,
            value=value,
            agent_id=agent_id,
            ttl=ttl,
            tags=tags or set(),
            metadata=metadata or {},
            category=category,
            version=version
        )

        self._data[key] = entry
        self._history.append(entry)

        # Notify subscribers
        await self._notify_subscribers(entry)

        return entry

    def get(
        self,
        key: str,
        agent_id: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """Get value from blackboard"""
        entry = self._data.get(key)
        if entry is None:
            return default
        if entry.is_expired():
            del self._data[key]
            return default
        return entry.value

    def get_entry(self, key: str) -> Optional[BlackboardEntry]:
        """Get full entry"""
        entry = self._data.get(key)
        if entry and entry.is_expired():
            del self._data[key]
            return None
        return entry

    def query(
        self,
        pattern: str,
        agent_id: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        category: Optional[DataCategory] = None,
        limit: int = 100
    ) -> List[BlackboardEntry]:
        """Query blackboard with pattern"""
        import re
        regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
        regex = re.compile(f'^{regex_pattern}$')

        results = []
        for key, entry in self._data.items():
            if len(results) >= limit:
                break
            if entry.is_expired():
                continue
            if not regex.match(key):
                continue
            if category and entry.category != category:
                continue
            if tags and not tags.issubset(entry.tags):
                continue
            results.append(entry)

        return results

    def subscribe(
        self,
        pattern: str,
        agent_id: str,
        callback: Callable[[BlackboardEntry], None],
        categories: Optional[Set[DataCategory]] = None
    ):
        """Subscribe to pattern"""
        sub = Subscription(
            pattern=pattern,
            agent_id=agent_id,
            callback=callback,
            categories=categories
        )
        if pattern not in self._subscriptions:
            self._subscriptions[pattern] = []
        self._subscriptions[pattern].append(sub)

    async def _notify_subscribers(self, entry: BlackboardEntry):
        """Notify matching subscribers"""
        import re
        for pattern, subs in self._subscriptions.items():
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            regex = re.compile(f'^{regex_pattern}$')

            if not regex.match(entry.key):
                continue

            for sub in subs:
                if sub.agent_id == entry.agent_id:
                    continue
                if sub.categories and entry.category not in sub.categories:
                    continue

                self._notifications.append((sub.agent_id, entry))
                try:
                    if asyncio.iscoroutinefunction(sub.callback):
                        await sub.callback(entry)
                    else:
                        sub.callback(entry)
                except Exception as e:
                    logger.error(f"MockBlackboard callback error: {e}")

    def get_all_entries(self) -> Dict[str, BlackboardEntry]:
        """Get all current entries"""
        return {k: v for k, v in self._data.items() if not v.is_expired()}

    def get_history(self) -> List[BlackboardEntry]:
        """Get publication history"""
        return self._history.copy()

    def get_notifications(self) -> List[tuple]:
        """Get all notifications sent"""
        return self._notifications.copy()

    def clear(self):
        """Clear all data"""
        self._data.clear()
        self._history.clear()
        self._notifications.clear()

    def reset(self):
        """Full reset"""
        self._data.clear()
        self._subscriptions.clear()
        self._history.clear()
        self._notifications.clear()


@pytest.fixture
def mock_blackboard():
    """Provide a fresh mock blackboard"""
    bb = MockBlackboard()
    yield bb
    bb.reset()


@pytest.fixture
def real_blackboard():
    """Provide a real blackboard for integration tests"""
    reset_blackboard()
    from agents.blackboard import get_blackboard
    bb = get_blackboard()
    yield bb
    reset_blackboard()


# =============================================================================
# TEST CONTEXT FACTORY
# =============================================================================

@pytest.fixture
def context_factory():
    """Factory for creating test AnalysisContext objects"""

    def _create_context(
        url: str = "https://example.com",
        competitor_urls: Optional[List[str]] = None,
        language: str = "fi",
        industry_context: Optional[str] = None,
        user_id: Optional[str] = None,
        unified_context: Optional[Dict[str, Any]] = None,
        agent_results: Optional[Dict[str, AgentResult]] = None,
        revenue_input: Optional[Dict[str, Any]] = None
    ) -> AnalysisContext:
        """Create a test context with specified parameters"""
        return AnalysisContext(
            url=url,
            competitor_urls=competitor_urls or [],
            language=language,
            industry_context=industry_context,
            user_id=user_id,
            unified_context=unified_context,
            agent_results=agent_results or {},
            revenue_input=revenue_input
        )

    return _create_context


@pytest.fixture
def sample_context(context_factory):
    """Provide a sample context for basic tests"""
    return context_factory(
        url="https://testcompany.fi",
        competitor_urls=["https://competitor1.fi", "https://competitor2.fi"],
        language="fi",
        industry_context="technology"
    )


@pytest.fixture
def sample_scout_result():
    """Provide a sample Scout agent result"""
    return AgentResult(
        agent_id="scout",
        agent_name="Scout",
        status=AgentStatus.COMPLETE,
        execution_time_ms=1500,
        insights=[
            AgentInsight(
                agent_id="scout",
                agent_name="Scout",
                agent_avatar="",
                message="Found 3 competitors",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
        ],
        data={
            'company': 'Test Company',
            'url': 'https://testcompany.fi',
            'industry': 'technology',
            'competitor_urls': ['https://competitor1.fi', 'https://competitor2.fi'],
            'competitor_count': 2,
            'discovery_method': 'auto_discovered',
            'competitors_enriched': [
                {'url': 'https://competitor1.fi', 'company_name': 'Competitor 1'},
                {'url': 'https://competitor2.fi', 'company_name': 'Competitor 2'}
            ],
            'your_company_intel': {
                'name': 'Test Company',
                'business_id': '1234567-8',
                'revenue': 500000,
                'employees': 10
            }
        },
        swarm_stats={
            'messages_sent': 3,
            'messages_received': 0,
            'blackboard_writes': 2,
            'blackboard_reads': 0,
            'collaborations': 0,
            'tasks_delegated': 0
        }
    )


@pytest.fixture
def sample_analyst_result():
    """Provide a sample Analyst agent result"""
    return AgentResult(
        agent_id="analyst",
        agent_name="Analyst",
        status=AgentStatus.COMPLETE,
        execution_time_ms=3000,
        insights=[],
        data={
            'your_analysis': {
                'final_score': 65,
                'basic_analysis': {
                    'digital_maturity_score': 65,
                    'title': 'Test Company',
                    'meta_description': 'A test company',
                    'mobile_ready': True,
                    'score_breakdown': {
                        'security': 12,
                        'seo_basics': 15,
                        'content': 16,
                        'technical': 12,
                        'mobile': 10
                    }
                }
            },
            'competitor_analyses': [],
            'benchmark': {
                'your_score': 65,
                'avg_competitor_score': 55,
                'your_position': 1,
                'total_analyzed': 3
            },
            'category_comparison': {
                'seo': {'your_score': 75, 'competitor_avg': 60, 'difference': 15, 'status': 'ahead'},
                'performance': {'your_score': 55, 'competitor_avg': 60, 'difference': -5, 'status': 'even'},
                'security': {'your_score': 80, 'competitor_avg': 70, 'difference': 10, 'status': 'ahead'}
            },
            'your_score': 65
        }
    )


# =============================================================================
# MOCK LLM RESPONSES
# =============================================================================

class MockLLMResponses:
    """Deterministic mock LLM responses for testing"""

    INDUSTRY_DETECTION = {
        'technology': 'technology',
        'jewelry': 'jewelry',
        'ecommerce': 'ecommerce',
        'default': 'general'
    }

    COMPETITOR_SCORES = {
        'default': 50,
        'high': 85,
        'low': 25
    }

    @staticmethod
    def get_industry(html_content: str) -> str:
        """Return deterministic industry based on content"""
        content_lower = html_content.lower()
        if 'tech' in content_lower or 'software' in content_lower:
            return 'technology'
        if 'jewelry' in content_lower or 'koru' in content_lower:
            return 'jewelry'
        if 'shop' in content_lower or 'store' in content_lower:
            return 'ecommerce'
        return 'general'

    @staticmethod
    def get_analysis_score(url: str) -> int:
        """Return deterministic score based on URL"""
        if 'good' in url:
            return 85
        if 'bad' in url:
            return 25
        return 50


@pytest.fixture
def mock_llm():
    """Provide mock LLM responses"""
    return MockLLMResponses()


# =============================================================================
# HELPER FIXTURES
# =============================================================================

@pytest.fixture
def event_loop():
    """Create an event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset all global state before each test"""
    # Reset before test
    reset_message_bus()
    reset_blackboard()
    reset_collaboration_manager()
    reset_task_manager()

    yield

    # Reset after test
    reset_message_bus()
    reset_blackboard()
    reset_collaboration_manager()
    reset_task_manager()


@pytest.fixture
def capture_insights():
    """Capture insights emitted by agents"""
    insights = []

    def callback(insight: AgentInsight):
        insights.append(insight)

    return insights, callback


@pytest.fixture
def capture_swarm_events():
    """Capture swarm events emitted by agents"""
    events = []

    def callback(event: SwarmEvent):
        events.append(event)

    return events, callback
