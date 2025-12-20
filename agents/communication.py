# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Agent Communication Framework
TRUE SWARM AGENTS - Inter-agent messaging system

This enables agents to:
- Send messages to each other in real-time
- Subscribe to events from other agents
- Broadcast to multiple agents
- Request help dynamically
- Coordinate autonomously
"""

import asyncio
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Set
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages agents can send"""
    
    # Alerts & Warnings
    ALERT = "alert"                    # Critical finding requiring attention
    WARNING = "warning"                # Important but not critical
    
    # Data sharing
    DATA = "data"                      # Share data with another agent
    FINDING = "finding"                # Share a discovery
    INSIGHT = "insight"                # Share an analytical insight
    
    # Requests
    REQUEST = "request"                # Request action from another agent
    QUERY = "query"                    # Ask for information
    HELP = "help"                      # Request help with problem
    
    # Collaboration
    PROPOSAL = "proposal"              # Propose a solution/action
    VOTE = "vote"                      # Vote on a proposal
    CONSENSUS = "consensus"            # Announce consensus reached
    
    # Coordination
    TASK_DELEGATE = "task_delegate"    # Delegate a task
    TASK_COMPLETE = "task_complete"    # Report task completion
    PRIORITY_CHANGE = "priority_change" # Request priority change
    
    # Meta
    STATUS = "status"                  # Status update
    ACKNOWLEDGMENT = "acknowledgment"  # Acknowledge receipt


class MessagePriority(Enum):
    """Message priority levels"""
    CRITICAL = 0   # Immediate action required
    HIGH = 1       # Important, handle soon
    MEDIUM = 2     # Normal priority
    LOW = 3        # When convenient


@dataclass
class AgentMessage:
    """
    Message from one agent to another.
    
    This is the core communication unit in the swarm.
    """
    
    # Identity
    id: str                          # Unique message ID
    from_agent: str                  # Sender agent ID
    to_agent: Optional[str] = None   # Recipient (None = broadcast)
    
    # Content
    type: MessageType = MessageType.DATA
    priority: MessagePriority = MessagePriority.MEDIUM
    subject: str = ""                # Brief subject line
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    requires_response: bool = False
    response_to: Optional[str] = None  # ID of message this responds to
    
    # Context
    conversation_id: Optional[str] = None  # Group related messages
    tags: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        """Ensure ID is set"""
        if not self.id:
            self.id = f"{self.from_agent}_{int(self.timestamp.timestamp() * 1000)}"
    
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
            'tags': list(self.tags)
        }


class MessageBus:
    """
    Central message bus for inter-agent communication.
    
    This is the nervous system of the swarm.
    All agent-to-agent communication flows through here.
    """
    
    def __init__(self):
        # Message storage
        self._messages: Dict[str, AgentMessage] = {}
        self._message_history: List[AgentMessage] = []
        
        # Subscriptions: agent_id -> {message_types}
        self._subscriptions: Dict[str, Set[MessageType]] = {}
        
        # Callbacks: agent_id -> callback function
        self._callbacks: Dict[str, Callable] = {}
        
        # Message queues per agent
        self._queues: Dict[str, asyncio.Queue] = {}
        
        # Statistics
        self._stats = {
            'total_sent': 0,
            'total_delivered': 0,
            'by_type': {},
            'by_agent': {}
        }
        
        logger.info("[MessageBus] 🚌 Message bus initialized")
    
    def register_agent(
        self, 
        agent_id: str,
        callback: Optional[Callable] = None,
        subscribe_to: Optional[List[MessageType]] = None
    ):
        """
        Register an agent with the message bus.
        
        Args:
            agent_id: Agent identifier
            callback: Function to call when message received
            subscribe_to: List of message types to subscribe to
        """
        # Create message queue
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()
        
        # Register callback
        if callback:
            self._callbacks[agent_id] = callback
        
        # Set up subscriptions
        if subscribe_to:
            self._subscriptions[agent_id] = set(subscribe_to)
        elif agent_id not in self._subscriptions:
            self._subscriptions[agent_id] = set()
        
        # Initialize stats
        if agent_id not in self._stats['by_agent']:
            self._stats['by_agent'][agent_id] = {
                'sent': 0,
                'received': 0
            }
        
        logger.info(f"[MessageBus] ✅ Registered agent: {agent_id}")
    
    def subscribe(
        self,
        agent_id: str,
        message_types: List[MessageType]
    ):
        """
        Subscribe agent to specific message types.
        
        Agent will receive all messages of these types.
        """
        if agent_id not in self._subscriptions:
            self._subscriptions[agent_id] = set()
        
        self._subscriptions[agent_id].update(message_types)
        
        logger.info(
            f"[MessageBus] 📬 {agent_id} subscribed to: "
            f"{[t.value for t in message_types]}"
        )
    
    def unsubscribe(
        self,
        agent_id: str,
        message_types: Optional[List[MessageType]] = None
    ):
        """Unsubscribe from message types (or all if None)"""
        if agent_id not in self._subscriptions:
            return
        
        if message_types is None:
            self._subscriptions[agent_id].clear()
        else:
            self._subscriptions[agent_id].difference_update(message_types)
    
    async def send(self, message: AgentMessage) -> bool:
        """
        Send a message to specific agent or broadcast.
        
        Args:
            message: The message to send
            
        Returns:
            True if delivered successfully
        """
        try:
            # Store message
            self._messages[message.id] = message
            self._message_history.append(message)
            
            # Update stats
            self._stats['total_sent'] += 1
            self._stats['by_agent'][message.from_agent]['sent'] += 1
            
            msg_type = message.type.value
            if msg_type not in self._stats['by_type']:
                self._stats['by_type'][msg_type] = 0
            self._stats['by_type'][msg_type] += 1
            
            # Determine recipients
            recipients = self._get_recipients(message)
            
            if not recipients:
                logger.warning(
                    f"[MessageBus] ⚠️ No recipients for message {message.id} "
                    f"from {message.from_agent}"
                )
                return False
            
            # Deliver to all recipients
            for recipient_id in recipients:
                await self._deliver_to_agent(recipient_id, message)
            
            logger.info(
                f"[MessageBus] 📨 {message.from_agent} → "
                f"{recipients if message.to_agent else 'BROADCAST'}: "
                f"{message.type.value} - {message.subject}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"[MessageBus] ❌ Send failed: {e}", exc_info=True)
            return False
    
    def _get_recipients(self, message: AgentMessage) -> List[str]:
        """Determine who should receive this message"""
        recipients = []
        
        if message.to_agent:
            # Direct message to specific agent
            if message.to_agent in self._queues:
                recipients.append(message.to_agent)
        else:
            # Broadcast to subscribers
            for agent_id, subscribed_types in self._subscriptions.items():
                # Don't send to self
                if agent_id == message.from_agent:
                    continue
                
                # Check if subscribed to this message type
                if message.type in subscribed_types:
                    recipients.append(agent_id)
        
        return recipients
    
    async def _deliver_to_agent(self, agent_id: str, message: AgentMessage):
        """Deliver message to specific agent"""
        try:
            # Put in queue
            await self._queues[agent_id].put(message)
            
            # Update stats
            self._stats['total_delivered'] += 1
            self._stats['by_agent'][agent_id]['received'] += 1
            
            # Call callback if registered
            if agent_id in self._callbacks:
                callback = self._callbacks[agent_id]
                # Run callback (can be async)
                if asyncio.iscoroutinefunction(callback):
                    await callback(message)
                else:
                    callback(message)
            
        except Exception as e:
            logger.error(
                f"[MessageBus] ❌ Delivery to {agent_id} failed: {e}",
                exc_info=True
            )
    
    async def receive(self, agent_id: str, timeout: float = 1.0) -> Optional[AgentMessage]:
        """
        Receive next message from queue (non-blocking).
        
        Args:
            agent_id: Agent requesting messages
            timeout: How long to wait for message
            
        Returns:
            Next message or None if timeout
        """
        if agent_id not in self._queues:
            return None
        
        try:
            message = await asyncio.wait_for(
                self._queues[agent_id].get(),
                timeout=timeout
            )
            return message
        except asyncio.TimeoutError:
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
        """
        Convenience method to broadcast a message.
        
        Args:
            from_agent: Sender agent ID
            message_type: Type of message
            subject: Brief subject
            payload: Message data
            priority: Message priority
            tags: Optional tags
        """
        message = AgentMessage(
            id=f"{from_agent}_broadcast_{int(datetime.now().timestamp() * 1000)}",
            from_agent=from_agent,
            to_agent=None,  # Broadcast
            type=message_type,
            priority=priority,
            subject=subject,
            payload=payload,
            tags=tags or set()
        )
        
        return await self.send(message)
    
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
        received: bool = True
    ) -> List[AgentMessage]:
        """Get messages sent/received by agent"""
        messages = []
        
        for msg in self._message_history:
            if sent and msg.from_agent == agent_id:
                messages.append(msg)
            if received and msg.to_agent == agent_id:
                messages.append(msg)
        
        return messages
    
    def get_stats(self) -> Dict[str, Any]:
        """Get message bus statistics"""
        return {
            **self._stats,
            'active_agents': len(self._queues),
            'subscriptions': {
                agent: [t.value for t in types]
                for agent, types in self._subscriptions.items()
            }
        }
    
    def clear_history(self):
        """Clear message history (keep stats)"""
        self._messages.clear()
        self._message_history.clear()
        logger.info("[MessageBus] 🗑️ Message history cleared")


# Global message bus instance
_message_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    """Get or create global message bus"""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus


def reset_message_bus():
    """Reset global message bus (for testing)"""
    global _message_bus
    _message_bus = None
