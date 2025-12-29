# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Agent Communication Framework
TRUE SWARM EDITION - Production-ready inter-agent messaging

This is the nervous system of the swarm. Every agent-to-agent
communication flows through the MessageBus.

Features:
- Async message delivery with guaranteed ordering
- Priority-based message queues
- Request-response patterns
- Broadcast with subscription filtering
- Message history and replay
- Dead letter handling
- Circuit breaker for failing agents
"""

import asyncio
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages agents can send"""
    
    # Alerts & Warnings
    ALERT = "alert"
    WARNING = "warning"
    
    # Data sharing
    DATA = "data"
    FINDING = "finding"
    INSIGHT = "insight"
    ANALYSIS_RESULT = "analysis_result"
    
    # Requests
    REQUEST = "request"
    QUERY = "query"
    HELP = "help"
    RESPONSE = "response"
    
    # Collaboration
    PROPOSAL = "proposal"
    VOTE = "vote"
    CONSENSUS = "consensus"
    PERSPECTIVE = "perspective"
    
    # Coordination
    TASK_DELEGATE = "task_delegate"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"
    PRIORITY_CHANGE = "priority_change"
    
    # Lifecycle
    AGENT_READY = "agent_ready"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETE = "agent_complete"
    AGENT_ERROR = "agent_error"
    
    # Meta
    STATUS = "status"
    ACKNOWLEDGMENT = "acknowledgment"
    HEARTBEAT = "heartbeat"


class MessagePriority(Enum):
    """Message priority levels"""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


class DeliveryStatus(Enum):
    """Message delivery status"""
    PENDING = "pending"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class AgentMessage:
    """
    Message from one agent to another.
    This is the core communication unit in the swarm.
    """
    
    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    from_agent: str = ""
    to_agent: Optional[str] = None  # None = broadcast
    
    # Content
    type: MessageType = MessageType.DATA
    priority: MessagePriority = MessagePriority.MEDIUM
    subject: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    requires_response: bool = False
    response_to: Optional[str] = None
    
    # Context
    conversation_id: Optional[str] = None
    correlation_id: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    
    # Delivery tracking
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING
    delivered_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'from_agent': self.from_agent,
            'to_agent': self.to_agent,
            'type': self.type.value,
            'priority': self.priority.value,
            'subject': self.subject,
            'payload': self.payload,
            'timestamp': self.timestamp.isoformat(),
            'requires_response': self.requires_response,
            'response_to': self.response_to,
            'conversation_id': self.conversation_id,
            'tags': list(self.tags),
            'delivery_status': self.delivery_status.value
        }
    
    def is_expired(self) -> bool:
        """Check if message has expired"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def create_response(
        self,
        from_agent: str,
        payload: Dict[str, Any],
        message_type: MessageType = MessageType.RESPONSE
    ) -> 'AgentMessage':
        """Create a response message"""
        return AgentMessage(
            from_agent=from_agent,
            to_agent=self.from_agent,
            type=message_type,
            priority=self.priority,
            subject=f"Re: {self.subject}",
            payload=payload,
            response_to=self.id,
            conversation_id=self.conversation_id or self.id
        )


@dataclass
class PendingResponse:
    """Tracks a pending response"""
    message_id: str
    future: asyncio.Future
    timeout: float
    created_at: datetime = field(default_factory=datetime.now)


class CircuitBreaker:
    """Circuit breaker for failing agents"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0
    ):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._failures: Dict[str, int] = defaultdict(int)
        self._open_circuits: Dict[str, datetime] = {}
    
    def record_failure(self, agent_id: str):
        """Record a failure for an agent"""
        self._failures[agent_id] += 1
        if self._failures[agent_id] >= self.failure_threshold:
            self._open_circuits[agent_id] = datetime.now()
            logger.warning(f"[CircuitBreaker] Circuit OPEN for {agent_id}")
    
    def record_success(self, agent_id: str):
        """Record a success, reset failure count"""
        self._failures[agent_id] = 0
        if agent_id in self._open_circuits:
            del self._open_circuits[agent_id]
            logger.info(f"[CircuitBreaker] Circuit CLOSED for {agent_id}")
    
    def is_open(self, agent_id: str) -> bool:
        """Check if circuit is open (agent is failing)"""
        if agent_id not in self._open_circuits:
            return False
        
        # Check if reset timeout has passed
        opened_at = self._open_circuits[agent_id]
        if (datetime.now() - opened_at).total_seconds() > self.reset_timeout:
            # Half-open: allow one try
            del self._open_circuits[agent_id]
            self._failures[agent_id] = self.failure_threshold - 1
            return False
        
        return True


class MessageBus:
    """
    Central message bus for inter-agent communication.
    This is the nervous system of the swarm.
    """
    
    def __init__(self):
        # Message storage
        self._messages: Dict[str, AgentMessage] = {}
        self._message_history: List[AgentMessage] = []
        
        # Agent queues - priority queues per agent
        self._queues: Dict[str, asyncio.PriorityQueue] = {}
        
        # Subscriptions: agent_id -> {message_types}
        self._subscriptions: Dict[str, Set[MessageType]] = {}
        
        # Callbacks: agent_id -> callback function
        self._callbacks: Dict[str, Callable] = {}
        
        # Pending responses: message_id -> PendingResponse
        self._pending_responses: Dict[str, PendingResponse] = {}
        
        # Circuit breaker
        self._circuit_breaker = CircuitBreaker()
        
        # Dead letter queue
        self._dead_letters: List[AgentMessage] = []
        
        # Event callbacks for monitoring
        self._on_message_sent: Optional[Callable] = None
        self._on_message_delivered: Optional[Callable] = None
        
        # Statistics
        self._stats = {
            'total_sent': 0,
            'total_delivered': 0,
            'total_failed': 0,
            'total_expired': 0,
            'by_type': defaultdict(int),
            'by_agent': defaultdict(lambda: {'sent': 0, 'received': 0, 'failed': 0})
        }
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        logger.info("[MessageBus] 🚌 Message bus initialized")
    
    def set_event_callbacks(
        self,
        on_message_sent: Optional[Callable] = None,
        on_message_delivered: Optional[Callable] = None
    ):
        """Set callbacks for message events (for UI updates)"""
        self._on_message_sent = on_message_sent
        self._on_message_delivered = on_message_delivered
    
    def register_agent(
        self,
        agent_id: str,
        callback: Optional[Callable] = None,
        subscribe_to: Optional[List[MessageType]] = None
    ):
        """Register an agent with the message bus"""
        # Create priority queue
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.PriorityQueue()
        
        # Register callback
        if callback:
            self._callbacks[agent_id] = callback
        
        # Set up subscriptions
        if subscribe_to:
            self._subscriptions[agent_id] = set(subscribe_to)
        elif agent_id not in self._subscriptions:
            # Default subscriptions
            self._subscriptions[agent_id] = {
                MessageType.ALERT,
                MessageType.REQUEST,
                MessageType.HELP,
                MessageType.TASK_DELEGATE,
                MessageType.CONSENSUS
            }
        
        # Initialize stats
        if agent_id not in self._stats['by_agent']:
            self._stats['by_agent'][agent_id] = {'sent': 0, 'received': 0, 'failed': 0}
            
            logger.info(f"[MessageBus] ✅ Registered agent: {agent_id}")
    
    def subscribe(self, agent_id: str, message_types: List[MessageType]):
        """Subscribe agent to message types"""
        if agent_id not in self._subscriptions:
            self._subscriptions[agent_id] = set()
        
        self._subscriptions[agent_id].update(message_types)
        logger.debug(f"[MessageBus] 📬 {agent_id} subscribed to: {[t.value for t in message_types]}")
    
    def unsubscribe(self, agent_id: str, message_types: Optional[List[MessageType]] = None):
        """Unsubscribe from message types"""
        if agent_id not in self._subscriptions:
            return
        
        if message_types is None:
            self._subscriptions[agent_id].clear()
        else:
            self._subscriptions[agent_id].difference_update(message_types)
    
    async def send(
        self,
        message: AgentMessage,
        wait_for_response: bool = False,
        timeout: float = 30.0
    ) -> Optional[AgentMessage]:
        """
        Send a message to specific agent or broadcast.
        
        Args:
            message: The message to send
            wait_for_response: Whether to wait for response
            timeout: Response timeout
            
        Returns:
            Response message if wait_for_response=True
        """
        try:
            # Check circuit breaker
            if message.to_agent and self._circuit_breaker.is_open(message.to_agent):
                logger.warning(f"[MessageBus] ⚡ Circuit open for {message.to_agent}, dropping message")
                self._dead_letters.append(message)
                return None
            
            # Store message
            self._messages[message.id] = message
            self._message_history.append(message)
            
            # Update stats
            self._stats['total_sent'] += 1
            self._stats['by_agent'][message.from_agent]['sent'] += 1
            self._stats['by_type'][message.type.value] += 1
            
            # Determine recipients
            recipients = self._get_recipients(message)
            
            if not recipients:
                logger.debug(f"[MessageBus] No recipients for {message.id}")
                return None
            
            # Set up response future if needed
            response_future = None
            if wait_for_response and message.to_agent:
                response_future = asyncio.Future()
                self._pending_responses[message.id] = PendingResponse(
                    message_id=message.id,
                    future=response_future,
                    timeout=timeout
                )
            
            # Deliver to recipients
            for recipient_id in recipients:
                await self._deliver_to_agent(recipient_id, message)
            
            # Fire event callback
            if self._on_message_sent:
                try:
                    if asyncio.iscoroutinefunction(self._on_message_sent):
                        await self._on_message_sent(message)
                    else:
                        self._on_message_sent(message)
                except Exception as e:
                    logger.error(f"[MessageBus] Event callback error: {e}")
            
            logger.info(
                f"[MessageBus] 📨 {message.from_agent} → "
                f"{message.to_agent or 'BROADCAST'}: "
                f"{message.type.value} - {message.subject}"
            )
            
            # Wait for response if requested
            if response_future:
                try:
                    response = await asyncio.wait_for(response_future, timeout=timeout)
                    return response
                except asyncio.TimeoutError:
                    logger.warning(f"[MessageBus] ⏱️ Response timeout for {message.id}")
                    del self._pending_responses[message.id]
                    return None
            
            return None
            
        except Exception as e:
            logger.error(f"[MessageBus] ❌ Send failed: {e}", exc_info=True)
            message.delivery_status = DeliveryStatus.FAILED
            self._stats['total_failed'] += 1
            return None
    
    def _get_recipients(self, message: AgentMessage) -> List[str]:
        """Determine who should receive this message"""
        recipients = []
        
        if message.to_agent:
            # Direct message
            if message.to_agent in self._queues:
                recipients.append(message.to_agent)
        else:
            # Broadcast to subscribers
            for agent_id, subscribed_types in self._subscriptions.items():
                if agent_id == message.from_agent:
                    continue
                
                if message.type in subscribed_types:
                    recipients.append(agent_id)
        
        return recipients
    
    async def _deliver_to_agent(self, agent_id: str, message: AgentMessage):
        """Deliver message to specific agent"""
        try:
            # Put in priority queue (priority, timestamp, message)
            priority_tuple = (
                message.priority.value,
                message.timestamp.timestamp(),
                message
            )
            await self._queues[agent_id].put(priority_tuple)
            
            # Update stats
            self._stats['total_delivered'] += 1
            self._stats['by_agent'][agent_id]['received'] += 1
            
            # Mark as delivered
            message.delivery_status = DeliveryStatus.DELIVERED
            message.delivered_at = datetime.now()
            
            # Call callback if registered
            if agent_id in self._callbacks:
                callback = self._callbacks[agent_id]
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(message)
                    else:
                        callback(message)
                    
                    # Record success
                    self._circuit_breaker.record_success(agent_id)
                    
                except Exception as e:
                    logger.error(f"[MessageBus] Callback error for {agent_id}: {e}")
                    self._circuit_breaker.record_failure(agent_id)
            
            # Check if this is a response to a pending request
            if message.response_to and message.response_to in self._pending_responses:
                pending = self._pending_responses[message.response_to]
                if not pending.future.done():
                    pending.future.set_result(message)
                del self._pending_responses[message.response_to]
            
            # Fire delivery callback
            if self._on_message_delivered:
                try:
                    if asyncio.iscoroutinefunction(self._on_message_delivered):
                        await self._on_message_delivered(message, agent_id)
                    else:
                        self._on_message_delivered(message, agent_id)
                except Exception:
                    pass
            
        except Exception as e:
            logger.error(f"[MessageBus] ❌ Delivery to {agent_id} failed: {e}")
            self._stats['by_agent'][agent_id]['failed'] += 1
            self._circuit_breaker.record_failure(agent_id)
    
    async def receive(
        self,
        agent_id: str,
        timeout: float = 0.1
    ) -> Optional[AgentMessage]:
        """
        Receive next message from queue (non-blocking).
        """
        if agent_id not in self._queues:
            return None
        
        try:
            priority_tuple = await asyncio.wait_for(
                self._queues[agent_id].get(),
                timeout=timeout
            )
            return priority_tuple[2]  # Message is third element
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error(f"[MessageBus] Receive error for {agent_id}: {e}")
            return None
    
    async def receive_all(self, agent_id: str) -> List[AgentMessage]:
        """Receive all pending messages"""
        messages = []
        while True:
            msg = await self.receive(agent_id, timeout=0.01)
            if msg is None:
                break
            messages.append(msg)
        return messages
    
    async def broadcast(
        self,
        from_agent: str,
        message_type: MessageType,
        subject: str,
        payload: Dict[str, Any],
        priority: MessagePriority = MessagePriority.MEDIUM,
        tags: Optional[Set[str]] = None
    ) -> bool:
        """Convenience method to broadcast a message"""
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
    
    async def request_response(
        self,
        from_agent: str,
        to_agent: str,
        message_type: MessageType,
        subject: str,
        payload: Dict[str, Any],
        timeout: float = 30.0
    ) -> Optional[AgentMessage]:
        """Send a request and wait for response"""
        message = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            type=message_type,
            subject=subject,
            payload=payload,
            requires_response=True
        )
        
        return await self.send(message, wait_for_response=True, timeout=timeout)
    
    def acknowledge(self, agent_id: str, message_id: str):
        """Acknowledge receipt of a message"""
        if message_id in self._messages:
            self._messages[message_id].delivery_status = DeliveryStatus.ACKNOWLEDGED
            self._messages[message_id].acknowledged_at = datetime.now()
    
    def get_conversation(self, conversation_id: str) -> List[AgentMessage]:
        """Get all messages in a conversation"""
        return [
            msg for msg in self._message_history
            if msg.conversation_id == conversation_id
        ]
    
    def get_messages_by_type(self, message_type: MessageType) -> List[AgentMessage]:
        """Get all messages of specific type"""
        return [
            msg for msg in self._message_history
            if msg.type == message_type
        ]
    
    def get_agent_messages(
        self,
        agent_id: str,
        sent: bool = True,
        received: bool = True,
        limit: int = 100
    ) -> List[AgentMessage]:
        """Get messages sent/received by agent"""
        messages = []
        
        for msg in reversed(self._message_history):
            if len(messages) >= limit:
                break
            
            if sent and msg.from_agent == agent_id:
                messages.append(msg)
            elif received and msg.to_agent == agent_id:
                messages.append(msg)
        
        return list(reversed(messages))
    
    def get_stats(self) -> Dict[str, Any]:
        """Get message bus statistics"""
        return {
            'total_sent': self._stats['total_sent'],
            'total_delivered': self._stats['total_delivered'],
            'total_failed': self._stats['total_failed'],
            'active_agents': len(self._queues),
            'pending_responses': len(self._pending_responses),
            'dead_letters': len(self._dead_letters),
            'by_type': dict(self._stats['by_type']),
            'by_agent': {k: dict(v) for k, v in self._stats['by_agent'].items()},
            'subscriptions': {
                agent: [t.value for t in types]
                for agent, types in self._subscriptions.items()
            }
        }
    
    def get_dead_letters(self) -> List[AgentMessage]:
        """Get dead letter queue"""
        return self._dead_letters.copy()
    
    def clear_dead_letters(self):
        """Clear dead letter queue"""
        self._dead_letters.clear()
    
    def clear_history(self):
        """Clear message history"""
        self._messages.clear()
        self._message_history.clear()
        logger.info("[MessageBus] 🗑️ Message history cleared")
    
    def reset(self):
        """Full reset of message bus"""
        self._messages.clear()
        self._message_history.clear()
        self._queues.clear()
        self._subscriptions.clear()
        self._callbacks.clear()
        self._pending_responses.clear()
        self._dead_letters.clear()
        self._stats = {
            'total_sent': 0,
            'total_delivered': 0,
            'total_failed': 0,
            'total_expired': 0,
            'by_type': defaultdict(int),
            'by_agent': defaultdict(lambda: {'sent': 0, 'received': 0, 'failed': 0})
        }
        logger.info("[MessageBus] 🔄 Message bus reset")


# Global message bus instance
_message_bus: Optional[MessageBus] = None
_message_bus_lock = asyncio.Lock()


def get_message_bus() -> MessageBus:
    """Get or create global message bus"""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus


def reset_message_bus():
    """Reset global message bus"""
    global _message_bus
    if _message_bus:
        _message_bus.reset()
    _message_bus = None
