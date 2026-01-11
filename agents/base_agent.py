# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Base Agent
TRUE SWARM EDITION - Every agent actively communicates

This is the foundation for all agents with REAL swarm capabilities:
- Automatic message broadcasting on key findings
- Reactive blackboard subscriptions
- Collaborative problem solving
- Continuous learning

Now with RunContext support for per-request isolation.
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Set, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .run_context import RunContext

# Production safety: Disallow global singleton fallback by default
ALLOW_GLOBAL_SINGLETON_FALLBACK = os.environ.get(
    'ALLOW_GLOBAL_SINGLETON_FALLBACK', 'false'
).lower() in ('true', '1', 'yes')

from .agent_types import (
    AgentStatus,
    AgentPriority,
    InsightType,
    AgentInsight,
    AgentProgress,
    AgentResult,
    AnalysisContext,
    SwarmEvent,
    SwarmEventType
)
from .translations import t as translate

# Swarm imports
from .communication import (
    MessageBus,
    AgentMessage,
    MessageType,
    MessagePriority,
    get_message_bus
)
from .blackboard import (
    Blackboard,
    BlackboardEntry,
    DataCategory,
    get_blackboard
)
from .collaboration import (
    CollaborationManager,
    CollaborationSession,
    CollaborationResult,
    VoteType,
    get_collaboration_manager
)
from .task_delegation import (
    TaskDelegationManager,
    DynamicTask,
    TaskStatus,
    TaskPriority,
    get_task_manager
)
from .learning import (
    LearningSystem,
    get_learning_system
)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Base class for Growth Engine agents.
    
    TRUE SWARM FEATURES:
    - Auto-broadcasts key findings to other agents
    - Subscribes to relevant blackboard updates
    - Can collaborate on complex decisions
    - Learns from experience
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        avatar: str = "🤖",
        personality: str = ""
    ):
        self.id = agent_id
        self.name = name
        self.role = role
        self.avatar = avatar
        self.personality = personality
        
        # State
        self.status = AgentStatus.IDLE
        self.progress = 0
        self.current_task: Optional[str] = None
        self.insights: List[AgentInsight] = []
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
        # Language
        self._language: str = "fi"
        
        # Dependencies
        self.dependencies: List[str] = []
        
        # Callbacks
        self._on_insight: Optional[Callable[[AgentInsight], None]] = None
        self._on_progress: Optional[Callable[[AgentProgress], None]] = None
        self._on_swarm_event: Optional[Callable[[SwarmEvent], None]] = None
        
        # Swarm systems - initialized on first use
        self._message_bus: Optional[MessageBus] = None
        self._blackboard: Optional[Blackboard] = None
        self._collaboration_manager: Optional[CollaborationManager] = None
        self._task_manager: Optional[TaskDelegationManager] = None
        self._learning_system: Optional[LearningSystem] = None
        self._swarm_initialized = False

        # RunContext for per-request isolation (NEW)
        self._run_context: Optional['RunContext'] = None

        # Context reference
        self._context: Optional[AnalysisContext] = None
        
        # Swarm stats for this run
        self._swarm_stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'blackboard_writes': 0,
            'blackboard_reads': 0,
            'collaborations': 0,
            'tasks_delegated': 0
        }
        
        # Message queue for received messages
        self._received_messages: List[AgentMessage] = []
        
        # Blackboard updates received
        self._blackboard_updates: List[BlackboardEntry] = []
    
    def _t(self, key: str, **kwargs) -> str:
        """Translate text to current language"""
        return translate(key, self._language, **kwargs)
    
    def set_callbacks(
        self,
        on_insight: Optional[Callable[[AgentInsight], None]] = None,
        on_progress: Optional[Callable[[AgentProgress], None]] = None,
        on_swarm_event: Optional[Callable[[SwarmEvent], None]] = None
    ):
        """Set callbacks for real-time updates"""
        self._on_insight = on_insight
        self._on_progress = on_progress
        self._on_swarm_event = on_swarm_event

    def set_run_context(self, run_context: 'RunContext'):
        """
        Set RunContext for per-request isolation.
        This injects isolated swarm systems instead of globals.

        IMPORTANT:
        A single BaseAgent instance must not be used for multiple concurrent runs.
        We detect unsafe concurrent reuse: if we're already initialized for a
        different run_id, switching contexts would corrupt shared state.
        """
        # Detect unsafe concurrent reuse
        current_run_id = getattr(self, "_active_run_id", None)
        if (
            current_run_id is not None
            and current_run_id != run_context.run_id
            and getattr(self, "_swarm_initialized", False)
        ):
            # Log a warning - in practice, orchestrator resets between runs
            logger.warning(
                f"[{self.name}] Switching RunContext (was={current_run_id}, "
                f"new={run_context.run_id}). Ensure no concurrent runs share this agent."
            )

        self._run_context = run_context
        self._active_run_id = run_context.run_id
        self._swarm_initialized = False  # Force re-init with new context
        logger.debug(f"[{self.name}] RunContext set: {run_context.run_id}")

    # ========================================================================
    # SWARM INITIALIZATION
    # ========================================================================

    def _init_swarm(self):
        """Initialize swarm capabilities - uses RunContext if available, else globals"""
        if self._swarm_initialized:
            return

        # Use RunContext systems if available (per-request isolation)
        if self._run_context:
            self._message_bus = self._run_context.message_bus
            self._blackboard = self._run_context.blackboard
            self._collaboration_manager = self._run_context.collaboration_manager
            self._task_manager = self._run_context.task_manager
            self._learning_system = self._run_context.learning_system
            logger.debug(f"[{self.name}] Using RunContext systems (run_id={self._run_context.run_id})")
        else:
            # Production safety check
            if not ALLOW_GLOBAL_SINGLETON_FALLBACK:
                raise RuntimeError(
                    f"[{self.name}] No RunContext provided and ALLOW_GLOBAL_SINGLETON_FALLBACK=false. "
                    "In production, all agents must receive a RunContext for isolation. "
                    "Set ALLOW_GLOBAL_SINGLETON_FALLBACK=true for development/testing."
                )

            # Fallback to global singletons (backwards compatibility - dev only)
            logger.warning(
                f"[{self.name}] ⚠️ FALLBACK: Using global singletons instead of RunContext. "
                "This can cause cross-contamination in concurrent requests. "
                "Set ALLOW_GLOBAL_SINGLETON_FALLBACK=false in production."
            )
            self._message_bus = get_message_bus()
            self._blackboard = get_blackboard()
            self._collaboration_manager = get_collaboration_manager()
            self._task_manager = get_task_manager()
            self._learning_system = get_learning_system()
        
        # Register with message bus
        self._message_bus.register_agent(
            agent_id=self.id,
            callback=self._on_message_received,
            subscribe_to=self._get_subscribed_message_types()
        )
        
        # Register with task manager
        self._task_manager.register_agent(
            agent_id=self.id,
            task_types=self._get_task_capabilities(),
            max_load=3
        )
        
        # Set up blackboard subscriptions
        self._setup_blackboard_subscriptions()
        
        self._swarm_initialized = True
        logger.info(f"[{self.name}] 🤝 Swarm capabilities initialized")
    
    def _get_subscribed_message_types(self) -> List[MessageType]:
        """Get message types to subscribe to - override in subclass"""
        return [
            MessageType.ALERT,
            MessageType.REQUEST,
            MessageType.HELP,
            MessageType.CONSENSUS,
            MessageType.TASK_DELEGATE
        ]
    
    def _get_task_capabilities(self) -> Set[str]:
        """Get task types this agent can handle - override in subclass"""
        return set()
    
    def _setup_blackboard_subscriptions(self):
        """Set up blackboard subscriptions - override in subclass"""
        # Default: subscribe to critical findings from all agents
        if self._blackboard:
            self._blackboard.subscribe(
                pattern="*.critical",
                agent_id=self.id,
                callback=self._on_blackboard_update
            )
            self._blackboard.subscribe(
                pattern="*.alert",
                agent_id=self.id,
                callback=self._on_blackboard_update
            )
    
    # ========================================================================
    # MESSAGE HANDLING
    # ========================================================================
    
    async def _on_message_received(self, message: AgentMessage):
        """Handle incoming message from another agent"""
        self._received_messages.append(message)
        self._swarm_stats['messages_received'] += 1
        
        logger.info(
            f"[{self.name}] 📨 Received {message.type.value} from "
            f"{message.from_agent}: {message.subject}"
        )
        
        # Fire swarm event
        self._emit_swarm_event(
            SwarmEventType.MESSAGE_RECEIVED,
            message.from_agent,
            message.subject,
            {'message_type': message.type.value, 'payload': message.payload}
        )
        
        # Handle by type
        if message.type == MessageType.ALERT:
            await self._handle_alert(message)
        elif message.type == MessageType.REQUEST:
            await self._handle_request(message)
        elif message.type == MessageType.HELP:
            await self._handle_help_request(message)
        elif message.type == MessageType.TASK_DELEGATE:
            await self._handle_delegated_task(message)
    
    async def _handle_alert(self, message: AgentMessage):
        """Handle alert from another agent - override in subclass"""
        pass
    
    async def _handle_request(self, message: AgentMessage):
        """Handle request from another agent - override in subclass"""
        pass
    
    async def _handle_help_request(self, message: AgentMessage):
        """Handle help request - override in subclass"""
        pass
    
    async def _handle_delegated_task(self, message: AgentMessage):
        """Handle delegated task"""
        task_data = message.payload.get('task')
        if task_data:
            logger.info(f"[{self.name}] 📋 Received delegated task: {task_data.get('description')}")
    
    def _on_blackboard_update(self, entry: BlackboardEntry):
        """Handle blackboard update"""
        self._blackboard_updates.append(entry)
        self._swarm_stats['blackboard_reads'] += 1
        
        logger.debug(f"[{self.name}] 📋 Blackboard update: {entry.key}")
        
        self._emit_swarm_event(
            SwarmEventType.BLACKBOARD_SUBSCRIBE,
            entry.agent_id,
            entry.key,
            {'value_preview': str(entry.value)[:100]}
        )
    
    # ========================================================================
    # SENDING MESSAGES
    # ========================================================================
    
    async def _send_message(
        self,
        to_agent: str,
        message_type: MessageType,
        subject: str,
        payload: Dict[str, Any],
        priority: MessagePriority = MessagePriority.MEDIUM,
        wait_for_response: bool = False,
        timeout: float = 10.0
    ) -> Optional[AgentMessage]:
        """Send message to another agent"""
        if not self._message_bus:
            self._init_swarm()
        
        message = AgentMessage(
            from_agent=self.id,
            to_agent=to_agent,
            type=message_type,
            priority=priority,
            subject=subject,
            payload=payload,
            requires_response=wait_for_response
        )
        
        response = await self._message_bus.send(
            message,
            wait_for_response=wait_for_response,
            timeout=timeout
        )
        
        self._swarm_stats['messages_sent'] += 1
        
        self._emit_swarm_event(
            SwarmEventType.MESSAGE_SENT,
            self.id,
            subject,
            {'to': to_agent, 'type': message_type.value}
        )
        
        logger.info(f"[{self.name}] 📤 Sent {message_type.value} to {to_agent}: {subject}")
        
        return response
    
    async def _broadcast(
        self,
        message_type: MessageType,
        subject: str,
        payload: Dict[str, Any],
        priority: MessagePriority = MessagePriority.MEDIUM
    ):
        """Broadcast message to all subscribed agents"""
        if not self._message_bus:
            self._init_swarm()
        
        await self._message_bus.broadcast(
            from_agent=self.id,
            message_type=message_type,
            subject=subject,
            payload=payload,
            priority=priority
        )
        
        self._swarm_stats['messages_sent'] += 1
        
        self._emit_swarm_event(
            SwarmEventType.MESSAGE_SENT,
            self.id,
            subject,
            {'type': message_type.value, 'broadcast': True}
        )
        
        logger.info(f"[{self.name}] 📢 Broadcast {message_type.value}: {subject}")
    
    async def _alert_all(self, subject: str, data: Dict[str, Any]):
        """Send alert to all agents"""
        await self._broadcast(
            MessageType.ALERT,
            subject,
            data,
            MessagePriority.HIGH
        )
    
    async def _share_finding(self, finding: str, data: Dict[str, Any]):
        """Share a finding with all agents"""
        await self._broadcast(
            MessageType.FINDING,
            finding,
            data,
            MessagePriority.MEDIUM
        )
    
    # ========================================================================
    # BLACKBOARD OPERATIONS
    # ========================================================================
    
    async def _publish_to_blackboard(
        self,
        key: str,
        value: Any,
        category: Optional[DataCategory] = None,
        ttl: Optional[int] = None,
        tags: Optional[Set[str]] = None
    ):
        """Publish data to shared blackboard"""
        if not self._blackboard:
            self._init_swarm()
        
        full_key = f"{self.id}.{key}"
        
        await self._blackboard.publish(
            key=full_key,
            value=value,
            agent_id=self.id,
            category=category,
            ttl=ttl,
            tags=tags
        )
        
        self._swarm_stats['blackboard_writes'] += 1
        
        self._emit_swarm_event(
            SwarmEventType.BLACKBOARD_PUBLISH,
            self.id,
            full_key,
            {'category': category.value if category else None}
        )
        
        logger.debug(f"[{self.name}] 📌 Published to blackboard: {full_key}")
    
    def _read_from_blackboard(self, key: str) -> Any:
        """Read data from blackboard"""
        if not self._blackboard:
            self._init_swarm()
        
        value = self._blackboard.get(key, agent_id=self.id)
        self._swarm_stats['blackboard_reads'] += 1
        return value
    
    def _query_blackboard(
        self,
        pattern: str,
        category: Optional[DataCategory] = None
    ) -> List[BlackboardEntry]:
        """Query blackboard with pattern"""
        if not self._blackboard:
            self._init_swarm()
        
        entries = self._blackboard.query(
            pattern=pattern,
            agent_id=self.id,
            category=category
        )
        self._swarm_stats['blackboard_reads'] += len(entries)
        return entries
    
    # ========================================================================
    # COLLABORATION
    # ========================================================================
    
    async def _start_collaboration(
        self,
        problem: str,
        with_agents: List[str],
        timeout: float = 30.0
    ) -> Optional[CollaborationResult]:
        """Start a collaboration session"""
        if not self._collaboration_manager:
            self._init_swarm()
        
        self._emit_swarm_event(
            SwarmEventType.COLLABORATION_START,
            self.id,
            problem[:50],
            {'agents': with_agents}
        )
        
        result = await self._collaboration_manager.create_session(
            problem=problem,
            agents=[self.id] + with_agents,
            facilitator=self.id,
            timeout=timeout
        )
        
        self._swarm_stats['collaborations'] += 1
        
        if result.consensus_reached:
            self._emit_swarm_event(
                SwarmEventType.COLLABORATION_CONSENSUS,
                self.id,
                f"Consensus: {result.solution[:50] if result.solution else 'None'}",
                {'confidence': result.confidence}
            )
        
        return result
    
    def _submit_perspective(
        self,
        session_id: str,
        perspective: str,
        confidence: float = 1.0,
        concerns: Optional[List[str]] = None
    ):
        """Submit perspective to collaboration session"""
        if not self._collaboration_manager:
            return
        
        self._collaboration_manager.submit_perspective(
            session_id=session_id,
            agent_id=self.id,
            perspective=perspective,
            confidence=confidence,
            concerns=concerns
        )
    
    def _vote(
        self,
        session_id: str,
        proposal_id: str,
        vote_type: VoteType,
        reasoning: str = ""
    ):
        """Vote on a proposal"""
        if not self._collaboration_manager:
            return
        
        self._collaboration_manager.submit_vote(
            session_id=session_id,
            agent_id=self.id,
            proposal_id=proposal_id,
            vote_type=vote_type,
            reasoning=reasoning
        )
        
        self._emit_swarm_event(
            SwarmEventType.COLLABORATION_VOTE,
            self.id,
            f"Voted {vote_type.value}",
            {'proposal': proposal_id}
        )
    
    # ========================================================================
    # TASK DELEGATION
    # ========================================================================
    
    async def _delegate_task(
        self,
        to_agent: str,
        task_type: str,
        description: str,
        parameters: Dict[str, Any],
        wait_for_result: bool = True,
        timeout: float = 30.0
    ) -> Optional[Any]:
        """Delegate a task to another agent"""
        if not self._task_manager:
            self._init_swarm()
        
        task = self._task_manager.create_task(
            created_by=self.id,
            task_type=task_type,
            description=description,
            parameters=parameters,
            timeout=timeout
        )
        
        success = await self._task_manager.delegate_task(task, to_agent)
        
        if not success:
            logger.warning(f"[{self.name}] Failed to delegate task to {to_agent}")
            return None
        
        self._swarm_stats['tasks_delegated'] += 1
        
        self._emit_swarm_event(
            SwarmEventType.TASK_DELEGATED,
            self.id,
            description[:50],
            {'to': to_agent, 'task_type': task_type}
        )
        
        if wait_for_result:
            try:
                result = await self._task_manager.wait_for_task(task, timeout)
                return result
            except asyncio.TimeoutError:
                logger.warning(f"[{self.name}] Task timeout: {task.task_id}")
                return None
        
        return None
    
    # ========================================================================
    # LEARNING
    # ========================================================================
    
    def _log_prediction(
        self,
        prediction_type: str,
        predicted_value: Any,
        confidence: float = 1.0,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log a prediction for later verification"""
        if not self._learning_system:
            self._init_swarm()
        
        # Adjust confidence based on history
        should_adjust, modifier = self._learning_system.should_adjust_confidence(
            self.id, prediction_type
        )
        if should_adjust:
            confidence = min(1.0, confidence * modifier)
        
        return self._learning_system.log_prediction(
            agent_id=self.id,
            prediction_type=prediction_type,
            predicted_value=predicted_value,
            confidence=confidence,
            context=context
        )
    
    def _verify_prediction(self, prediction_id: str, actual_value: Any):
        """Verify a previous prediction"""
        if not self._learning_system:
            return
        
        self._learning_system.verify_prediction(prediction_id, actual_value)
    
    # ========================================================================
    # INSIGHT AND PROGRESS
    # ========================================================================
    
    def _emit_insight(
        self,
        message: str,
        priority: AgentPriority = AgentPriority.MEDIUM,
        insight_type: InsightType = InsightType.FINDING,
        data: Optional[Dict[str, Any]] = None,
        from_collaboration: bool = False,
        contributing_agents: Optional[List[str]] = None
    ):
        """Emit insight to frontend and optionally to swarm"""
        insight = AgentInsight(
            agent_id=self.id,
            agent_name=self.name,
            agent_avatar=self.avatar,
            message=message,
            priority=priority,
            insight_type=insight_type,
            data=data,
            from_collaboration=from_collaboration,
            contributing_agents=contributing_agents or []
        )
        
        self.insights.append(insight)
        
        if self._on_insight:
            try:
                self._on_insight(insight)
            except Exception as e:
                logger.error(f"[{self.name}] Insight callback error: {e}")
        
        logger.info(f"[{self.name}] 💡 {message}")
        
        # AUTO-BROADCAST critical/high priority insights
        if priority in [AgentPriority.CRITICAL, AgentPriority.HIGH]:
            asyncio.create_task(self._share_insight_with_swarm(insight))
    
    async def _share_insight_with_swarm(self, insight: AgentInsight):
        """Share important insight with other agents"""
        if not self._message_bus:
            return
        
        await self._broadcast(
            MessageType.INSIGHT,
            insight.message[:100],
            {
                'full_message': insight.message,
                'priority': insight.priority.value,
                'type': insight.insight_type.value,
                'data': insight.data
            },
            MessagePriority.HIGH if insight.priority == AgentPriority.CRITICAL else MessagePriority.MEDIUM
        )
        
        # Also publish to blackboard
        category = {
            InsightType.THREAT: DataCategory.THREAT,
            InsightType.OPPORTUNITY: DataCategory.OPPORTUNITY,
            InsightType.FINDING: DataCategory.INSIGHT,
            InsightType.RECOMMENDATION: DataCategory.RECOMMENDATION
        }.get(insight.insight_type, DataCategory.INSIGHT)
        
        key = f"insight.{insight.insight_type.value}"
        if insight.priority == AgentPriority.CRITICAL:
            key = f"critical.{insight.insight_type.value}"
        
        await self._publish_to_blackboard(
            key=key,
            value={
                'message': insight.message,
                'data': insight.data,
                'timestamp': insight.timestamp.isoformat()
            },
            category=category,
            ttl=3600  # 1 hour
        )
    
    def _update_progress(self, progress: int, task: Optional[str] = None):
        """Update progress"""
        self.progress = min(100, max(0, progress))
        if task:
            self.current_task = task
        
        progress_update = AgentProgress(
            agent_id=self.id,
            status=self.status,
            progress=self.progress,
            current_task=self.current_task,
            messages_sent=self._swarm_stats['messages_sent'],
            messages_received=self._swarm_stats['messages_received']
        )
        
        if self._on_progress:
            try:
                self._on_progress(progress_update)
            except Exception as e:
                logger.error(f"[{self.name}] Progress callback error: {e}")
    
    def _emit_swarm_event(
        self,
        event_type: Union[SwarmEventType, str],
        data_or_from_agent: Union[Dict[str, Any], str] = None,
        subject: str = None,
        data: Dict[str, Any] = None
    ):
        """
        Emit swarm event for monitoring.

        Supports two call signatures:
        1. Simple: _emit_swarm_event('event_type', {data_dict})
        2. Full: _emit_swarm_event(SwarmEventType.X, 'from_agent', 'subject', {data})
        """
        if not self._on_swarm_event:
            return

        # Handle simple signature: _emit_swarm_event('type', {data})
        if isinstance(data_or_from_agent, dict):
            event_data = data_or_from_agent
            # Convert string to enum if needed
            if isinstance(event_type, str):
                try:
                    event_type = SwarmEventType(event_type)
                except ValueError:
                    # Unknown event type - still emit it
                    pass

            event = SwarmEvent(
                event_type=event_type,
                from_agent=event_data.get('from', self.id),
                to_agent=event_data.get('to'),
                subject=event_data.get('message', '')[:100] if event_data.get('message') else '',
                data=event_data
            )
        else:
            # Handle full signature: _emit_swarm_event(type, from_agent, subject, data)
            event = SwarmEvent(
                event_type=event_type,
                from_agent=data_or_from_agent or self.id,
                subject=subject or '',
                data=data or {}
            )

        try:
            self._on_swarm_event(event)
            logger.debug(f"[{self.name}] 🐝 Swarm event emitted: {event.event_type}")
        except Exception as e:
            logger.warning(f"[{self.name}] Swarm event callback error: {e}")

        # Also add to context if available
        if self._context:
            self._context.add_swarm_event(event)
    
    def _set_status(self, status: AgentStatus):
        """Update status"""
        self.status = status
        self._update_progress(self.progress)
    
    # ========================================================================
    # EXECUTION
    # ========================================================================
    
    async def run(self, context: AnalysisContext) -> AgentResult:
        """Run agent - called by orchestrator"""
        self.start_time = datetime.now()
        self.insights = []
        self.error = None
        self.result = None
        self._context = context
        
        # Reset swarm stats
        self._swarm_stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'blackboard_writes': 0,
            'blackboard_reads': 0,
            'collaborations': 0,
            'tasks_delegated': 0
        }
        self._received_messages = []
        self._blackboard_updates = []
        
        # Set language
        self._language = context.language or "fi"
        
        # Initialize swarm
        self._init_swarm()
        
        try:
            # Announce start
            await self._broadcast(
                MessageType.AGENT_STARTED,
                f"{self.name} started",
                {'agent_id': self.id, 'dependencies': self.dependencies}
            )
            
            # Pre-execute
            self._set_status(AgentStatus.THINKING)
            self._update_progress(5, self._t("common.preparing"))
            await self.pre_execute(context)
            
            # Main execution
            self._set_status(AgentStatus.RUNNING)
            self._update_progress(10, self._t("common.executing"))
            
            result_data = await self.execute(context)
            
            # Post-execute
            self._update_progress(95, self._t("common.finalizing"))
            await self.post_execute(result_data)
            
            self.result = result_data
            self._set_status(AgentStatus.COMPLETE)
            self._update_progress(100, "Valmis!")
            
            # Announce completion
            await self._broadcast(
                MessageType.AGENT_COMPLETE,
                f"{self.name} completed",
                {
                    'agent_id': self.id,
                    'swarm_stats': self._swarm_stats,
                    'insights_count': len(self.insights)
                }
            )
            
        except Exception as e:
            self.error = str(e)
            self._set_status(AgentStatus.ERROR)
            logger.error(f"[{self.name}] ❌ Error: {e}", exc_info=True)
            
            # Announce error
            await self._broadcast(
                MessageType.AGENT_ERROR,
                f"{self.name} failed: {str(e)[:100]}",
                {'agent_id': self.id, 'error': str(e)}
            )
            
            self._emit_insight(
                f"Virhe: {str(e)[:100]}",
                priority=AgentPriority.CRITICAL,
                insight_type=InsightType.FINDING
            )
        
        self.end_time = datetime.now()
        execution_time = int((self.end_time - self.start_time).total_seconds() * 1000)
        
        return AgentResult(
            agent_id=self.id,
            agent_name=self.name,
            status=self.status,
            execution_time_ms=execution_time,
            insights=self.insights,
            data=self.result or {},
            error=self.error,
            swarm_stats=self._swarm_stats
        )
    
    async def pre_execute(self, context: AnalysisContext):
        """Setup before execution - override if needed"""
        pass
    
    @abstractmethod
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """Main logic - each agent implements this"""
        raise NotImplementedError
    
    async def post_execute(self, result: Dict[str, Any]):
        """Cleanup after execution - override if needed"""
        pass
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def get_dependency_results(
        self,
        context: AnalysisContext,
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get results from dependency agents"""
        if agent_id:
            if agent_id in context.agent_results:
                return context.agent_results[agent_id].data
            return {}
        
        results = {}
        for dep_id in self.dependencies:
            if dep_id in context.agent_results:
                results[dep_id] = context.agent_results[dep_id].data
        return results
    
    def get_unified_context_data(
        self,
        context: AnalysisContext,
        key: Optional[str] = None
    ) -> Any:
        """Get unified context data (historical)"""
        if not context.unified_context:
            return None if key else {}
        
        if key:
            return context.unified_context.get(key)
        return context.unified_context
    
    def get_swarm_data(self, pattern: str) -> List[Any]:
        """Get data from blackboard matching pattern"""
        entries = self._query_blackboard(pattern)
        return [e.value for e in entries]
    
    def to_info_dict(self) -> Dict[str, Any]:
        """Return agent info for frontend"""
        return {
            'id': self.id,
            'name': self.name,
            'role': self.role,
            'avatar': self.avatar,
            'personality': self.personality,
            'dependencies': self.dependencies,
            'status': self.status.value,
            'progress': self.progress
        }
