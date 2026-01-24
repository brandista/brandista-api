# -*- coding: utf-8 -*-
"""
Unit tests for MessageBus and Communication Framework

Tests:
- Agent registration
- Message send/receive
- Broadcast functionality
- Priority queue ordering
- Circuit breaker
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock

from agents.communication import (
    MessageBus,
    AgentMessage,
    MessageType,
    MessagePriority,
    DeliveryStatus,
    CircuitBreaker,
    get_message_bus,
    reset_message_bus
)


# =============================================================================
# AGENT REGISTRATION TESTS
# =============================================================================

class TestAgentRegistration:
    """Tests for agent registration with MessageBus"""

    def test_register_agent_basic(self, real_message_bus):
        """Test basic agent registration"""
        bus = real_message_bus

        bus.register_agent(agent_id="scout")

        assert "scout" in bus._queues
        assert "scout" in bus._subscriptions

    def test_register_agent_with_callback(self, real_message_bus):
        """Test agent registration with callback"""
        bus = real_message_bus
        callback = MagicMock()

        bus.register_agent(agent_id="analyst", callback=callback)

        assert "analyst" in bus._callbacks
        assert bus._callbacks["analyst"] == callback

    def test_register_agent_with_subscriptions(self, real_message_bus):
        """Test agent registration with custom subscriptions"""
        bus = real_message_bus
        subscriptions = [MessageType.ALERT, MessageType.DATA]

        bus.register_agent(agent_id="guardian", subscribe_to=subscriptions)

        assert bus._subscriptions["guardian"] == set(subscriptions)

    def test_register_agent_default_subscriptions(self, real_message_bus):
        """Test default subscriptions when none provided"""
        bus = real_message_bus

        bus.register_agent(agent_id="test")

        expected_defaults = {
            MessageType.ALERT,
            MessageType.REQUEST,
            MessageType.HELP,
            MessageType.TASK_DELEGATE,
            MessageType.CONSENSUS
        }
        assert bus._subscriptions["test"] == expected_defaults

    def test_register_agent_does_not_overwrite_queue(self, real_message_bus):
        """Test that re-registering doesn't create new queue"""
        bus = real_message_bus

        bus.register_agent(agent_id="test")
        queue1 = bus._queues["test"]

        bus.register_agent(agent_id="test")
        queue2 = bus._queues["test"]

        assert queue1 is queue2

    def test_subscribe_adds_message_types(self, real_message_bus):
        """Test subscribing to additional message types"""
        bus = real_message_bus
        bus.register_agent(agent_id="test", subscribe_to=[MessageType.ALERT])

        bus.subscribe("test", [MessageType.DATA, MessageType.FINDING])

        assert MessageType.ALERT in bus._subscriptions["test"]
        assert MessageType.DATA in bus._subscriptions["test"]
        assert MessageType.FINDING in bus._subscriptions["test"]

    def test_unsubscribe_removes_message_types(self, real_message_bus):
        """Test unsubscribing from message types"""
        bus = real_message_bus
        bus.register_agent(
            agent_id="test",
            subscribe_to=[MessageType.ALERT, MessageType.DATA]
        )

        bus.unsubscribe("test", [MessageType.ALERT])

        assert MessageType.ALERT not in bus._subscriptions["test"]
        assert MessageType.DATA in bus._subscriptions["test"]

    def test_unsubscribe_all(self, real_message_bus):
        """Test unsubscribing from all message types"""
        bus = real_message_bus
        bus.register_agent(
            agent_id="test",
            subscribe_to=[MessageType.ALERT, MessageType.DATA]
        )

        bus.unsubscribe("test")

        assert len(bus._subscriptions["test"]) == 0


# =============================================================================
# MESSAGE SEND/RECEIVE TESTS
# =============================================================================

class TestMessageSendReceive:
    """Tests for message sending and receiving"""

    @pytest.mark.asyncio
    async def test_send_direct_message(self, real_message_bus):
        """Test sending a direct message to specific agent"""
        bus = real_message_bus
        received_messages = []

        async def callback(msg):
            received_messages.append(msg)

        bus.register_agent(agent_id="sender")
        bus.register_agent(agent_id="receiver", callback=callback)

        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            type=MessageType.DATA,
            subject="Test message",
            payload={"key": "value"}
        )

        await bus.send(message)

        assert len(received_messages) == 1
        assert received_messages[0].subject == "Test message"
        assert received_messages[0].payload == {"key": "value"}

    @pytest.mark.asyncio
    async def test_send_updates_stats(self, real_message_bus):
        """Test that sending updates statistics"""
        bus = real_message_bus
        bus.register_agent(agent_id="sender")
        bus.register_agent(agent_id="receiver")

        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            type=MessageType.DATA,
            subject="Test"
        )

        await bus.send(message)

        stats = bus.get_stats()
        assert stats['total_sent'] == 1
        assert stats['total_delivered'] == 1

    @pytest.mark.asyncio
    async def test_send_stores_message(self, real_message_bus):
        """Test that sent messages are stored"""
        bus = real_message_bus
        bus.register_agent(agent_id="sender")
        bus.register_agent(agent_id="receiver")

        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            type=MessageType.DATA,
            subject="Stored message"
        )

        await bus.send(message)

        assert message.id in bus._messages
        assert len(bus._message_history) == 1

    @pytest.mark.asyncio
    async def test_receive_from_queue(self, real_message_bus):
        """Test receiving message from queue"""
        bus = real_message_bus
        bus.register_agent(agent_id="sender")
        bus.register_agent(agent_id="receiver")

        message = AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            type=MessageType.DATA,
            subject="Queue test"
        )

        await bus.send(message)
        received = await bus.receive("receiver", timeout=1.0)

        assert received is not None
        assert received.subject == "Queue test"

    @pytest.mark.asyncio
    async def test_receive_timeout(self, real_message_bus):
        """Test that receive times out when no message"""
        bus = real_message_bus
        bus.register_agent(agent_id="receiver")

        received = await bus.receive("receiver", timeout=0.1)

        assert received is None

    @pytest.mark.asyncio
    async def test_receive_all_messages(self, real_message_bus):
        """Test receiving all pending messages"""
        bus = real_message_bus
        bus.register_agent(agent_id="sender")
        bus.register_agent(agent_id="receiver")

        for i in range(3):
            message = AgentMessage(
                from_agent="sender",
                to_agent="receiver",
                type=MessageType.DATA,
                subject=f"Message {i}"
            )
            await bus.send(message)

        messages = await bus.receive_all("receiver")

        assert len(messages) == 3


# =============================================================================
# BROADCAST TESTS
# =============================================================================

class TestBroadcast:
    """Tests for broadcast functionality"""

    @pytest.mark.asyncio
    async def test_broadcast_to_subscribers(self, real_message_bus):
        """Test broadcast reaches all subscribers"""
        bus = real_message_bus
        received = {'agent1': [], 'agent2': [], 'agent3': []}

        async def callback1(msg):
            received['agent1'].append(msg)

        async def callback2(msg):
            received['agent2'].append(msg)

        async def callback3(msg):
            received['agent3'].append(msg)

        bus.register_agent(
            "sender",
            subscribe_to=[MessageType.ALERT]
        )
        bus.register_agent(
            "agent1",
            callback=callback1,
            subscribe_to=[MessageType.ALERT]
        )
        bus.register_agent(
            "agent2",
            callback=callback2,
            subscribe_to=[MessageType.ALERT]
        )
        bus.register_agent(
            "agent3",
            callback=callback3,
            subscribe_to=[MessageType.DATA]  # Different type
        )

        await bus.broadcast(
            from_agent="sender",
            message_type=MessageType.ALERT,
            subject="Broadcast test",
            payload={"alert": "important"}
        )

        assert len(received['agent1']) == 1
        assert len(received['agent2']) == 1
        assert len(received['agent3']) == 0  # Not subscribed to ALERT

    @pytest.mark.asyncio
    async def test_broadcast_excludes_sender(self, real_message_bus):
        """Test broadcast doesn't deliver to sender"""
        bus = real_message_bus
        received = []

        async def callback(msg):
            received.append(msg)

        bus.register_agent(
            "sender",
            callback=callback,
            subscribe_to=[MessageType.ALERT]
        )

        await bus.broadcast(
            from_agent="sender",
            message_type=MessageType.ALERT,
            subject="Self test",
            payload={}
        )

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_broadcast_with_priority(self, real_message_bus):
        """Test broadcast respects priority"""
        bus = real_message_bus
        received = []

        async def callback(msg):
            received.append(msg)

        bus.register_agent("sender")
        bus.register_agent(
            "receiver",
            callback=callback,
            subscribe_to=[MessageType.ALERT]
        )

        await bus.broadcast(
            from_agent="sender",
            message_type=MessageType.ALERT,
            subject="Priority test",
            payload={},
            priority=MessagePriority.CRITICAL
        )

        assert len(received) == 1
        assert received[0].priority == MessagePriority.CRITICAL


# =============================================================================
# PRIORITY QUEUE ORDERING TESTS
# =============================================================================

class TestPriorityQueueOrdering:
    """Tests for priority-based message ordering"""

    @pytest.mark.asyncio
    async def test_priority_ordering_critical_first(self, real_message_bus):
        """Test that CRITICAL messages are received first"""
        bus = real_message_bus
        bus.register_agent(agent_id="sender")
        bus.register_agent(agent_id="receiver")

        # Send in reverse priority order
        priorities = [
            MessagePriority.LOW,
            MessagePriority.MEDIUM,
            MessagePriority.HIGH,
            MessagePriority.CRITICAL
        ]

        for priority in priorities:
            message = AgentMessage(
                from_agent="sender",
                to_agent="receiver",
                type=MessageType.DATA,
                priority=priority,
                subject=f"Priority {priority.value}"
            )
            await bus.send(message)

        # Receive all and check order
        received = await bus.receive_all("receiver")

        assert len(received) == 4
        assert received[0].priority == MessagePriority.CRITICAL
        assert received[1].priority == MessagePriority.HIGH
        assert received[2].priority == MessagePriority.MEDIUM
        assert received[3].priority == MessagePriority.LOW

    @pytest.mark.asyncio
    async def test_same_priority_fifo(self, real_message_bus):
        """Test that same priority messages maintain FIFO order"""
        bus = real_message_bus
        bus.register_agent(agent_id="sender")
        bus.register_agent(agent_id="receiver")

        for i in range(5):
            message = AgentMessage(
                from_agent="sender",
                to_agent="receiver",
                type=MessageType.DATA,
                priority=MessagePriority.MEDIUM,
                subject=f"Message {i}"
            )
            await bus.send(message)
            await asyncio.sleep(0.01)  # Ensure different timestamps

        received = await bus.receive_all("receiver")

        assert len(received) == 5
        for i, msg in enumerate(received):
            assert msg.subject == f"Message {i}"


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================

class TestCircuitBreaker:
    """Tests for circuit breaker functionality"""

    def test_circuit_breaker_initial_state(self):
        """Test circuit breaker starts closed"""
        cb = CircuitBreaker(failure_threshold=3)

        assert not cb.is_open("agent1")

    def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit opens after reaching failure threshold"""
        cb = CircuitBreaker(failure_threshold=3)

        for _ in range(3):
            cb.record_failure("agent1")

        assert cb.is_open("agent1")

    def test_circuit_breaker_success_resets_count(self):
        """Test that success resets failure count"""
        cb = CircuitBreaker(failure_threshold=3)

        cb.record_failure("agent1")
        cb.record_failure("agent1")
        cb.record_success("agent1")

        assert not cb.is_open("agent1")
        assert cb._failures["agent1"] == 0

    def test_circuit_breaker_half_open_after_timeout(self):
        """Test circuit goes half-open after reset timeout"""
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)

        cb.record_failure("agent1")
        cb.record_failure("agent1")
        assert cb.is_open("agent1")

        # Wait for reset timeout
        import time
        time.sleep(0.15)

        # Should now be half-open (allow one try)
        assert not cb.is_open("agent1")

    def test_circuit_breaker_per_agent(self):
        """Test circuit breaker tracks agents independently"""
        cb = CircuitBreaker(failure_threshold=2)

        cb.record_failure("agent1")
        cb.record_failure("agent1")

        assert cb.is_open("agent1")
        assert not cb.is_open("agent2")

    @pytest.mark.asyncio
    async def test_message_bus_uses_circuit_breaker(self, real_message_bus):
        """Test that MessageBus respects circuit breaker"""
        bus = real_message_bus
        bus._circuit_breaker = CircuitBreaker(failure_threshold=2)

        bus.register_agent("sender")
        bus.register_agent("failing_agent")

        # Simulate failures
        bus._circuit_breaker.record_failure("failing_agent")
        bus._circuit_breaker.record_failure("failing_agent")

        assert bus._circuit_breaker.is_open("failing_agent")

        # Message should go to dead letter queue
        message = AgentMessage(
            from_agent="sender",
            to_agent="failing_agent",
            type=MessageType.DATA,
            subject="Should fail"
        )

        await bus.send(message)

        assert len(bus._dead_letters) == 1


# =============================================================================
# MESSAGE HISTORY AND RETRIEVAL TESTS
# =============================================================================

class TestMessageHistory:
    """Tests for message history and retrieval"""

    @pytest.mark.asyncio
    async def test_get_conversation(self, real_message_bus):
        """Test retrieving conversation by ID"""
        bus = real_message_bus
        bus.register_agent("agent1")
        bus.register_agent("agent2")

        conv_id = "test_conversation"

        for i in range(3):
            message = AgentMessage(
                from_agent="agent1",
                to_agent="agent2",
                type=MessageType.DATA,
                subject=f"Message {i}",
                conversation_id=conv_id
            )
            await bus.send(message)

        # Send unrelated message
        other_message = AgentMessage(
            from_agent="agent1",
            to_agent="agent2",
            type=MessageType.DATA,
            subject="Other",
            conversation_id="different"
        )
        await bus.send(other_message)

        conversation = bus.get_conversation(conv_id)

        assert len(conversation) == 3
        assert all(msg.conversation_id == conv_id for msg in conversation)

    @pytest.mark.asyncio
    async def test_get_messages_by_type(self, real_message_bus):
        """Test retrieving messages by type"""
        bus = real_message_bus
        bus.register_agent("sender")
        bus.register_agent("receiver")

        await bus.send(AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            type=MessageType.ALERT,
            subject="Alert"
        ))
        await bus.send(AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            type=MessageType.DATA,
            subject="Data"
        ))

        alerts = bus.get_messages_by_type(MessageType.ALERT)

        assert len(alerts) == 1
        assert alerts[0].type == MessageType.ALERT

    @pytest.mark.asyncio
    async def test_get_agent_messages(self, real_message_bus):
        """Test retrieving messages for specific agent"""
        bus = real_message_bus
        bus.register_agent("agent1")
        bus.register_agent("agent2")
        bus.register_agent("agent3")

        await bus.send(AgentMessage(
            from_agent="agent1",
            to_agent="agent2",
            type=MessageType.DATA,
            subject="1 to 2"
        ))
        await bus.send(AgentMessage(
            from_agent="agent2",
            to_agent="agent1",
            type=MessageType.DATA,
            subject="2 to 1"
        ))
        await bus.send(AgentMessage(
            from_agent="agent3",
            to_agent="agent1",
            type=MessageType.DATA,
            subject="3 to 1"
        ))

        agent1_msgs = bus.get_agent_messages("agent1")

        assert len(agent1_msgs) == 3

    def test_clear_history(self, real_message_bus):
        """Test clearing message history"""
        bus = real_message_bus
        bus._messages["test"] = MagicMock()
        bus._message_history.append(MagicMock())

        bus.clear_history()

        assert len(bus._messages) == 0
        assert len(bus._message_history) == 0


# =============================================================================
# STATISTICS TESTS
# =============================================================================

class TestStatistics:
    """Tests for message bus statistics"""

    @pytest.mark.asyncio
    async def test_stats_structure(self, real_message_bus):
        """Test stats have correct structure"""
        bus = real_message_bus

        stats = bus.get_stats()

        assert 'total_sent' in stats
        assert 'total_delivered' in stats
        assert 'total_failed' in stats
        assert 'active_agents' in stats
        assert 'by_type' in stats
        assert 'by_agent' in stats

    @pytest.mark.asyncio
    async def test_stats_by_agent(self, real_message_bus):
        """Test per-agent statistics"""
        bus = real_message_bus
        bus.register_agent("sender")
        bus.register_agent("receiver")

        for _ in range(3):
            await bus.send(AgentMessage(
                from_agent="sender",
                to_agent="receiver",
                type=MessageType.DATA,
                subject="Test"
            ))

        stats = bus.get_stats()

        assert stats['by_agent']['sender']['sent'] == 3
        assert stats['by_agent']['receiver']['received'] == 3

    @pytest.mark.asyncio
    async def test_stats_by_type(self, real_message_bus):
        """Test per-type statistics"""
        bus = real_message_bus
        bus.register_agent("sender")
        bus.register_agent("receiver")

        await bus.send(AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            type=MessageType.ALERT,
            subject="Alert"
        ))
        await bus.send(AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            type=MessageType.ALERT,
            subject="Alert 2"
        ))
        await bus.send(AgentMessage(
            from_agent="sender",
            to_agent="receiver",
            type=MessageType.DATA,
            subject="Data"
        ))

        stats = bus.get_stats()

        assert stats['by_type']['alert'] == 2
        assert stats['by_type']['data'] == 1


# =============================================================================
# RESET TESTS
# =============================================================================

class TestReset:
    """Tests for message bus reset"""

    def test_reset_clears_all_state(self, real_message_bus):
        """Test that reset clears all state"""
        bus = real_message_bus
        bus.register_agent("test")
        bus._messages["test"] = MagicMock()
        bus._stats['total_sent'] = 10

        bus.reset()

        assert len(bus._messages) == 0
        assert len(bus._queues) == 0
        assert len(bus._subscriptions) == 0
        assert bus._stats['total_sent'] == 0
