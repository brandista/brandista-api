"""
Growth Engine 2.0 - Base Agent
Pohjaluokka kaikille agenteille

SWARM CAPABILITIES:
- Inter-agent messaging
- Shared blackboard access
- Collaborative problem solving
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Tuple

from .types import (
    AgentStatus,
    AgentPriority,
    InsightType,
    AgentInsight,
    AgentProgress,
    AgentResult,
    AnalysisContext
)
from .translations import t as translate

# SWARM IMPORTS
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
    get_blackboard
)
from .collaboration import (
    CollaborationManager,
    CollaborationSession,
    CollaborationResult,
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
    Prediction,
    LearningStats,
    get_learning_system
)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Pohjaluokka Growth Engine -agenteille.
    
    ENHANCED WITH SWARM CAPABILITIES:
    - Can send messages to other agents
    - Can publish/subscribe to shared blackboard
    - Can collaborate on complex problems
    - Can learn and adapt
    
    Jokainen agentti:
    - Suorittaa yhden erikoistuneen tehtävän
    - Emittoi real-time insighteja frontendiin
    - Raportoi edistymisensä
    - Voi riippua muista agenteista
    - UUSI: Kommunikoi muiden agenttien kanssa
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
        
        # Language (set from context in run())
        self._language: str = "fi"
        
        # Dependencies - mitkä agentit pitää ajaa ensin
        self.dependencies: List[str] = []
        
        # Callbacks for real-time updates
        self._on_insight: Optional[Callable[[AgentInsight], None]] = None
        self._on_progress: Optional[Callable[[AgentProgress], None]] = None
        
        # SWARM CAPABILITIES - Access to message bus and blackboard
        self._message_bus: Optional[MessageBus] = None
        self._blackboard: Optional[Blackboard] = None
        self._context: Optional[AnalysisContext] = None
        self._collaboration_manager: Optional[CollaborationManager] = None
        self._task_manager: Optional[TaskDelegationManager] = None
        self._learning_system: Optional[LearningSystem] = None
    
    def _t(self, key: str, **kwargs) -> str:
        """
        Käännä teksti nykyiselle kielelle.
        
        Esimerkki:
            self._t("scout.found_competitors", count=5, top="Example.com")
        """
        return translate(key, self._language, **kwargs)
    
    def set_callbacks(
        self,
        on_insight: Optional[Callable[[AgentInsight], None]] = None,
        on_progress: Optional[Callable[[AgentProgress], None]] = None
    ):
        """Aseta callbackit real-time päivityksille"""
        self._on_insight = on_insight
        self._on_progress = on_progress
    
    def _emit_insight(
        self,
        message: str,
        priority: AgentPriority = AgentPriority.MEDIUM,
        insight_type: InsightType = InsightType.FINDING,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Emitoi insight frontendiin real-time.
        
        Esimerkki:
            self._emit_insight(
                "Löysin 3 vahvaa kilpailijaa!",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING
            )
        """
        insight = AgentInsight(
            agent_id=self.id,
            agent_name=self.name,
            agent_avatar=self.avatar,
            message=message,
            priority=priority,
            insight_type=insight_type,
            data=data
        )
        
        self.insights.append(insight)
        
        if self._on_insight:
            try:
                self._on_insight(insight)
            except Exception as e:
                logger.error(f"[{self.name}] Insight callback error: {e}")
        
        logger.info(f"[{self.name}] 💡 {message}")
    
    def _update_progress(
        self,
        progress: int,
        task: Optional[str] = None
    ):
        """
        Päivitä edistyminen.
        
        Esimerkki:
            self._update_progress(50, "Analysoimassa kilpailijoita...")
        """
        self.progress = min(100, max(0, progress))
        if task:
            self.current_task = task
        
        progress_update = AgentProgress(
            agent_id=self.id,
            status=self.status,
            progress=self.progress,
            current_task=self.current_task
        )
        
        if self._on_progress:
            try:
                self._on_progress(progress_update)
            except Exception as e:
                logger.error(f"[{self.name}] Progress callback error: {e}")
    
    def _set_status(self, status: AgentStatus):
        """Päivitä tila"""
        self.status = status
        self._update_progress(self.progress)
    
    async def run(self, context: AnalysisContext) -> AgentResult:
        """
        Suorita agentti. Tätä kutsuu orchestrator.
        
        Hoitaa:
        - Pre/post executionin
        - Virheenkäsittelyn
        - Ajanoton
        """
        self.start_time = datetime.now()
        self.insights = []
        self.error = None
        self.result = None
        
        # Set language from context
        self._language = context.language or "fi"
        
        try:
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
            
        except Exception as e:
            self.error = str(e)
            self._set_status(AgentStatus.ERROR)
            logger.error(f"[{self.name}] ❌ Error: {e}", exc_info=True)
            
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
            error=self.error
        )
    
    async def pre_execute(self, context: AnalysisContext):
        """
        Setup ennen suoritusta.
        Override tarvittaessa.
        """
        pass
    
    @abstractmethod
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """
        Päälogiikka - jokainen agentti toteuttaa tämän.
        
        Args:
            context: Jaettu konteksti sisältäen URL:t ja muiden agenttien tulokset
            
        Returns:
            Dict sisältäen agentin tulokset
        """
        raise NotImplementedError
    
    async def post_execute(self, result: Dict[str, Any]):
        """
        Cleanup suorituksen jälkeen.
        Override tarvittaessa.
        """
        pass
    
    def get_dependency_results(
        self,
        context: AnalysisContext,
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Hae riippuvuusagenttien tulokset.
        
        Args:
            context: Analyysikonteksti
            agent_id: Jos annettu, palauta vain tämän agentin tulokset
        
        Esimerkki:
            # Hae kaikki riippuvuudet
            deps = self.get_dependency_results(context)
            scout_data = deps.get('scout', {})
            
            # Hae yhden agentin tulokset
            analyst_data = self.get_dependency_results(context, 'analyst')
        """
        if agent_id:
            # Palauta vain yhden agentin tulokset
            if agent_id in context.agent_results:
                return context.agent_results[agent_id].data
            return {}
        
        # Palauta kaikki riippuvuudet
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
        """
        🧠 Hae unified context dataa (muisti aiemmista analyyseistä).
        
        Args:
            context: Analyysikonteksti
            key: Jos annettu, palauta vain tämä avain
        
        Returns:
            Unified context data tai None jos ei saatavilla
        
        Esimerkki:
            # Hae kaikki
            uc = self.get_unified_context_data(context)
            
            # Hae tracked competitors
            tracked = self.get_unified_context_data(context, 'tracked_competitors')
            
            # Hae score history
            analyses = self.get_unified_context_data(context, 'recent_analyses')
        """
        if not context.unified_context:
            return None if key else {}
        
        if key:
            return context.unified_context.get(key)
        
        return context.unified_context
    
    # ========================================================================
    # SWARM CAPABILITIES - Inter-agent communication and collaboration
    # ========================================================================
    
    def _init_swarm(self):
        """Initialize swarm capabilities (called by orchestrator)"""
        self._message_bus = get_message_bus()
        self._blackboard = get_blackboard()
        self._collaboration_manager = get_collaboration_manager()
        self._task_manager = get_task_manager()
        self._learning_system = get_learning_system()
        
        # Register with message bus
        self._message_bus.register_agent(
            agent_id=self.id,
            callback=self._on_message_received
        )
        
        # Subscribe to default message types
        self._subscribe_default_messages()
        
        logger.info(f"[{self.name}] 🤝 Swarm capabilities initialized")
    
    def _subscribe_default_messages(self):
        """
        Subscribe to default message types.
        Override in subclass to customize.
        """
        # By default, subscribe to alerts and requests
        self._message_bus.subscribe(
            agent_id=self.id,
            message_types=[
                MessageType.ALERT,
                MessageType.REQUEST,
                MessageType.HELP
            ]
        )
    
    async def _on_message_received(self, message: AgentMessage):
        """
        Handle incoming message from another agent.
        Override in subclass to customize behavior.
        
        Args:
            message: Incoming message
        """
        logger.info(
            f"[{self.name}] 📨 Received {message.type.value} from "
            f"{message.from_agent}: {message.subject}"
        )
        
        # Default handling - log and store
        # Subclasses should override for custom behavior
    
    async def _send_message(
        self,
        to_agent: str,
        message_type: MessageType,
        subject: str,
        payload: Dict[str, Any],
        priority: MessagePriority = MessagePriority.MEDIUM,
        requires_response: bool = False
    ) -> bool:
        """
        Send message to another agent.
        
        Args:
            to_agent: Target agent ID
            message_type: Type of message
            subject: Brief subject
            payload: Message data
            priority: Message priority
            requires_response: Whether response is expected
            
        Returns:
            True if sent successfully
        
        Example:
            await self._send_message(
                to_agent='guardian',
                message_type=MessageType.ALERT,
                subject='High threat competitor found',
                payload={'url': 'example.com', 'score': 95}
            )
        """
        if not self._message_bus:
            logger.warning(f"[{self.name}] ⚠️ Swarm not initialized, cannot send message")
            return False
        
        message = AgentMessage(
            id=f"{self.id}_{int(datetime.now().timestamp() * 1000)}",
            from_agent=self.id,
            to_agent=to_agent,
            type=message_type,
            priority=priority,
            subject=subject,
            payload=payload,
            requires_response=requires_response
        )
        
        return await self._message_bus.send(message)
    
    async def _broadcast_message(
        self,
        message_type: MessageType,
        subject: str,
        payload: Dict[str, Any],
        priority: MessagePriority = MessagePriority.MEDIUM
    ) -> bool:
        """
        Broadcast message to all subscribed agents.
        
        Example:
            await self._broadcast_message(
                message_type=MessageType.FINDING,
                subject='Critical security issue found',
                payload={'issue': 'no_ssl', 'severity': 'critical'}
            )
        """
        if not self._message_bus:
            return False
        
        return await self._message_bus.broadcast(
            from_agent=self.id,
            message_type=message_type,
            subject=subject,
            payload=payload,
            priority=priority
        )
    
    def _publish_to_blackboard(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[set] = None
    ):
        """
        Publish data to shared blackboard.
        
        Args:
            key: Hierarchical key (e.g. "scout.competitors.new")
            value: Data to publish
            ttl: Optional time-to-live in seconds
            tags: Optional tags
        
        Example:
            self._publish_to_blackboard(
                key=f"{self.id}.competitors.high_threat",
                value={'url': 'example.com', 'score': 95},
                tags={'threat', 'immediate'}
            )
        """
        if not self._blackboard:
            logger.warning(f"[{self.name}] ⚠️ Blackboard not initialized")
            return
        
        self._blackboard.publish(
            key=key,
            value=value,
            agent_id=self.id,
            ttl=ttl,
            tags=tags
        )
    
    def _read_from_blackboard(self, key: str) -> Any:
        """
        Read data from blackboard.
        
        Args:
            key: Key to read
            
        Returns:
            Value or None
        """
        if not self._blackboard:
            return None
        
        return self._blackboard.get(key, agent_id=self.id)
    
    def _query_blackboard(
        self,
        pattern: str,
        tags: Optional[set] = None
    ) -> List[BlackboardEntry]:
        """
        Query blackboard with pattern.
        
        Args:
            pattern: Glob pattern (e.g. "scout.*", "*.high_threat")
            tags: Optional filter by tags
            
        Returns:
            List of matching entries
        
        Example:
            # Get all scout findings
            entries = self._query_blackboard("scout.*")
            
            # Get all high threat items
            threats = self._query_blackboard("*.high_threat")
        """
        if not self._blackboard:
            return []
        
        return self._blackboard.query(
            pattern=pattern,
            agent_id=self.id,
            tags=tags
        )
    
    def _subscribe_to_blackboard(
        self,
        pattern: str,
        callback: Callable[[BlackboardEntry], None]
    ):
        """
        Subscribe to blackboard updates.
        
        Args:
            pattern: Glob pattern to match
            callback: Function to call on match
        
        Example:
            def on_threat(entry):
                print(f"Threat found: {entry.value}")
            
            self._subscribe_to_blackboard("*.high_threat", on_threat)
        """
        if not self._blackboard:
            return
        
        self._blackboard.subscribe(
            pattern=pattern,
            agent_id=self.id,
            callback=callback
        )
    
    async def _request_help(
        self,
        problem: str,
        from_agents: Optional[List[str]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Request help from other agents.
        
        Args:
            problem: Description of problem
            from_agents: Optional specific agents to ask
            data: Optional context data
            
        Example:
            await self._request_help(
                problem="Need deeper competitor analysis",
                from_agents=['analyst'],
                data={'competitor': 'example.com'}
            )
        """
        if from_agents:
            # Send to specific agents
            for agent_id in from_agents:
                await self._send_message(
                    to_agent=agent_id,
                    message_type=MessageType.HELP,
                    subject=problem,
                    payload=data or {},
                    priority=MessagePriority.HIGH,
                    requires_response=True
                )
        else:
            # Broadcast help request
            await self._broadcast_message(
                message_type=MessageType.HELP,
                subject=problem,
                payload=data or {},
                priority=MessagePriority.HIGH
            )
        
        return True
    
    # ========================================================================
    # COLLABORATION - Multi-agent problem solving
    # ========================================================================
    
    async def _start_collaboration(
        self,
        problem: str,
        with_agents: List[str],
        timeout: float = 30.0
    ) -> Optional[Any]:
        """
        Start a collaboration session with other agents.
        
        Use this when you need multiple perspectives to solve a problem.
        
        Args:
            problem: Problem to solve
            with_agents: List of agent IDs to collaborate with
            timeout: Max session time
            
        Returns:
            Solution if consensus reached, None otherwise
        
        Example:
            solution = await self._start_collaboration(
                problem="Should we prioritize mobile optimization?",
                with_agents=['analyst', 'prospector', 'strategist']
            )
        """
        if not self._collaboration_manager:
            logger.warning(f"[{self.name}] ⚠️ Collaboration not initialized")
            return None
        
        result = await self._collaboration_manager.create_session(
            problem=problem,
            agents=[self.id] + with_agents,
            facilitator=self.id,
            timeout=timeout
        )
        
        return result.solution if result.consensus_reached else None
    
    async def _contribute_to_collaboration(
        self,
        session_id: str,
        phase: str,
        content: Any
    ):
        """
        Contribute to ongoing collaboration session.
        
        Called when agent receives collaboration request.
        
        Args:
            session_id: Collaboration session ID
            phase: Which phase (perspective, proposal, vote, etc)
            content: Your contribution
        """
        if not self._blackboard:
            return
        
        # Publish contribution to blackboard
        self._blackboard.publish(
            key=f"collab.{session_id}.{phase}.{self.id}",
            value=content,
            agent_id=self.id,
            tags={'collaboration', phase}
        )
    
    # ========================================================================
    # TASK DELEGATION - Dynamic task creation and assignment
    # ========================================================================
    
    async def _delegate_task(
        self,
        to_agent: str,
        task_type: str,
        description: str,
        parameters: Dict[str, Any],
        priority: TaskPriority = TaskPriority.MEDIUM,
        wait_for_result: bool = True,
        timeout: float = 30.0
    ) -> Optional[Any]:
        """
        Delegate a task to another agent.
        
        Use this when you need another agent's expertise.
        
        Args:
            to_agent: Agent to delegate to
            task_type: Type of task
            description: Task description
            parameters: Task parameters
            priority: Task priority
            wait_for_result: Whether to wait for completion
            timeout: Max wait time
            
        Returns:
            Task result if wait_for_result=True, None otherwise
        
        Example:
            result = await self._delegate_task(
                to_agent='analyst',
                task_type='deep_analysis',
                description='Analyze competitor in depth',
                parameters={'url': 'example.com'},
                priority=TaskPriority.HIGH
            )
        """
        if not self._task_manager:
            logger.warning(f"[{self.name}] ⚠️ Task delegation not initialized")
            return None
        
        # Create task
        task = self._task_manager.create_task(
            created_by=self.id,
            task_type=task_type,
            description=description,
            parameters=parameters,
            priority=priority,
            timeout=timeout
        )
        
        # Delegate to agent
        await self._task_manager.delegate_task(task, to_agent)
        
        # Wait for result if requested
        if wait_for_result:
            try:
                result = await self._task_manager.wait_for_task(task)
                return result
            except asyncio.TimeoutError:
                logger.error(
                    f"[{self.name}] ⏱️ Task {task.task_id} timed out"
                )
                return None
        
        return None
    
    async def _auto_delegate_task(
        self,
        task_type: str,
        description: str,
        parameters: Dict[str, Any],
        candidates: List[str],
        priority: TaskPriority = TaskPriority.MEDIUM,
        wait_for_result: bool = True,
        timeout: float = 30.0
    ) -> Optional[Any]:
        """
        Auto-delegate task to best available agent.
        
        Task manager will pick the best agent based on:
        - Specialization
        - Current workload
        - Past performance
        
        Args:
            task_type: Type of task
            description: Task description
            parameters: Task parameters
            candidates: List of agents that can handle this
            priority: Task priority
            wait_for_result: Whether to wait
            timeout: Max wait time
            
        Returns:
            Task result if wait_for_result=True
        """
        if not self._task_manager:
            return None
        
        # Create task
        task = self._task_manager.create_task(
            created_by=self.id,
            task_type=task_type,
            description=description,
            parameters=parameters,
            priority=priority,
            timeout=timeout
        )
        
        # Auto-assign
        assigned = await self._task_manager.auto_assign_task(
            task,
            candidates
        )
        
        if not assigned:
            return None
        
        # Wait if requested
        if wait_for_result:
            try:
                result = await self._task_manager.wait_for_task(task)
                return result
            except asyncio.TimeoutError:
                return None
        
        return None
    
    def _complete_task(
        self,
        task_id: str,
        result: Any
    ):
        """
        Mark a delegated task as complete.
        
        Call this when you finish a task that was delegated to you.
        
        Args:
            task_id: Task ID
            result: Task result
        """
        if not self._task_manager:
            return
        
        self._task_manager.complete_task(
            task_id=task_id,
            result=result,
            agent_id=self.id
        )
    
    def _fail_task(
        self,
        task_id: str,
        error: str
    ):
        """
        Mark a task as failed.
        
        Args:
            task_id: Task ID
            error: Error message
        """
        if not self._task_manager:
            return
        
        self._task_manager.fail_task(
            task_id=task_id,
            error=error,
            agent_id=self.id
        )
    
    # ========================================================================
    # LEARNING & ADAPTATION - Learn from experience
    # ========================================================================
    
    def _log_prediction(
        self,
        prediction_type: str,
        predicted_value: Any,
        confidence: float = 1.0,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a prediction for later verification.
        
        Use this when making predictions that can be verified later.
        
        Args:
            prediction_type: Type of prediction
            predicted_value: Your prediction
            confidence: How confident (0-1)
            context: Additional context
            
        Returns:
            prediction_id for later verification
        
        Example:
            # Strategist predicts score will increase
            pred_id = self._log_prediction(
                prediction_type='score_change',
                predicted_value=+7,
                confidence=0.85,
                context={'current_score': 65}
            )
            
            # Store pred_id to verify later
            self._prediction_ids.append(pred_id)
        """
        if not self._learning_system:
            return ""
        
        return self._learning_system.log_prediction(
            agent_id=self.id,
            prediction_type=prediction_type,
            predicted_value=predicted_value,
            confidence=confidence,
            context=context
        )
    
    def _verify_prediction(
        self,
        prediction_id: str,
        actual_value: Any
    ):
        """
        Verify a previous prediction with actual results.
        
        Args:
            prediction_id: ID from _log_prediction
            actual_value: What actually happened
        
        Example:
            # Later, when results are known
            self._verify_prediction(
                prediction_id=stored_pred_id,
                actual_value=+5  # Actually increased by 5
            )
        """
        if not self._learning_system:
            return
        
        self._learning_system.verify_prediction(
            prediction_id=prediction_id,
            actual_value=actual_value
        )
    
    def _get_learning_stats(self) -> Optional[Any]:
        """
        Get learning statistics for this agent.
        
        Returns:
            LearningStats object with accuracy, calibration, trend
        """
        if not self._learning_system:
            return None
        
        return self._learning_system.get_agent_stats(self.id)
    
    def _should_adjust_confidence(
        self,
        prediction_type: str
    ) -> Tuple[bool, float]:
        """
        Check if confidence should be adjusted based on past accuracy.
        
        Args:
            prediction_type: Type of prediction
            
        Returns:
            (should_adjust, confidence_modifier)
        
        Example:
            adjust, modifier = self._should_adjust_confidence('score_change')
            if adjust:
                my_confidence *= modifier  # Reduce if historically inaccurate
        """
        if not self._learning_system:
            return False, 1.0
        
        return self._learning_system.should_adjust_confidence(
            agent_id=self.id,
            prediction_type=prediction_type
        )
    
    def _get_learned_rules(self) -> List[Dict[str, Any]]:
        """
        Get adaptation rules learned from experience.
        
        Returns:
            List of learned rules (prefer/avoid patterns)
        """
        if not self._learning_system:
            return []
        
        return self._learning_system.get_learned_rules(self.id)
    
    def to_info_dict(self) -> Dict[str, Any]:
        """Palauta agentin info frontendille"""
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
