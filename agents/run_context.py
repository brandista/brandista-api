# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - RunContext
Per-request isolation container for concurrent analysis runs.

This is the KEY to safe concurrent execution:
- Each analysis request gets its own RunContext
- RunContext contains isolated instances of bus, blackboard, etc.
- No global state = no cross-contamination between runs
- 10 users can run analyses simultaneously without interference

Usage:
    ctx = RunContext.create()
    result = await orchestrator.run_analysis(ctx, url="...")

    # Debug a specific run:
    ctx = RunContext.get_by_id("abc123")
    print(ctx.blackboard.get_snapshot())
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum

from .communication import MessageBus
from .blackboard import Blackboard
from .collaboration import CollaborationManager
from .task_delegation import TaskDelegationManager
from .learning import LearningSystem

logger = logging.getLogger(__name__)


class RunStatus(Enum):
    """Status of an analysis run"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class RunLimits:
    """
    Concurrency and timeout limits for a run.
    Prevents resource exhaustion.
    """
    # Semaphores
    llm_concurrency: int = 5          # Max concurrent LLM calls
    scrape_concurrency: int = 3       # Max concurrent web scrapes

    # Timeouts (seconds) - generous for analysis tasks
    total_timeout: float = 180.0      # 3 min total run timeout
    agent_timeout: float = 90.0       # 90s per agent (analysis takes time)
    llm_timeout: float = 60.0         # 60s LLM call timeout
    scrape_timeout: float = 30.0      # 30s web scrape timeout

    def __post_init__(self):
        """Create semaphores"""
        self._llm_semaphore: Optional[asyncio.Semaphore] = None
        self._scrape_semaphore: Optional[asyncio.Semaphore] = None

    @property
    def llm_semaphore(self) -> asyncio.Semaphore:
        """Get or create LLM semaphore"""
        if self._llm_semaphore is None:
            self._llm_semaphore = asyncio.Semaphore(self.llm_concurrency)
        return self._llm_semaphore

    @property
    def scrape_semaphore(self) -> asyncio.Semaphore:
        """Get or create scrape semaphore"""
        if self._scrape_semaphore is None:
            self._scrape_semaphore = asyncio.Semaphore(self.scrape_concurrency)
        return self._scrape_semaphore


@dataclass
class RunTrace:
    """
    Optional tracing/logging for a run.
    Useful for debugging and monitoring.
    """
    enabled: bool = True
    events: List[Dict[str, Any]] = field(default_factory=list)

    def log(self, event_type: str, agent_id: str = None, data: Any = None):
        """Log an event"""
        if not self.enabled:
            return

        self.events.append({
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'agent_id': agent_id,
            'data': data
        })

    def get_events(self, agent_id: str = None, event_type: str = None) -> List[Dict]:
        """Filter events"""
        events = self.events

        if agent_id:
            events = [e for e in events if e.get('agent_id') == agent_id]
        if event_type:
            events = [e for e in events if e.get('type') == event_type]

        return events

    def to_dict(self) -> Dict[str, Any]:
        """Export trace data"""
        return {
            'enabled': self.enabled,
            'event_count': len(self.events),
            'events': self.events
        }


class RunContext:
    """
    Isolated execution context for a single analysis run.

    This container holds ALL state for one analysis:
    - Message bus (inter-agent communication)
    - Blackboard (shared memory)
    - Task manager (dynamic task delegation)
    - Collaboration manager (consensus building)
    - Limits (semaphores, timeouts)
    - Trace (logging/debugging)

    KEY PRINCIPLE: Agents NEVER access global singletons.
    They receive RunContext and use ctx.message_bus, ctx.blackboard, etc.
    """

    # Registry of active runs (for debugging)
    _active_runs: Dict[str, 'RunContext'] = {}
    _registry_lock = asyncio.Lock()

    def __init__(
        self,
        run_id: str = None,
        limits: RunLimits = None,
        trace_enabled: bool = True,
        user_id: str = None,
        metadata: Dict[str, Any] = None
    ):
        # Identity
        self.run_id = run_id or str(uuid.uuid4())[:12]
        self.user_id = user_id
        self.metadata = metadata or {}

        # Timestamps
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

        # Status
        self.status = RunStatus.PENDING
        self.error: Optional[str] = None

        # Isolated instances (NOT global singletons!)
        self.message_bus = MessageBus()
        self.blackboard = Blackboard()
        self.task_manager = TaskDelegationManager()
        self.collaboration_manager = CollaborationManager()
        self.learning_system = LearningSystem()

        # Limits
        self.limits = limits or RunLimits()

        # Trace
        self.trace = RunTrace(enabled=trace_enabled)

        # Cancellation
        self._cancelled = False
        self._cancel_event = asyncio.Event()

        # Callbacks for progress updates
        self._on_progress: Optional[Callable] = None
        self._on_agent_start: Optional[Callable] = None
        self._on_agent_complete: Optional[Callable] = None
        self._on_insight: Optional[Callable] = None

        logger.info(f"[RunContext] Created run_id={self.run_id}")

    @classmethod
    def create(
        cls,
        user_id: str = None,
        limits: RunLimits = None,
        trace_enabled: bool = True,
        **metadata
    ) -> 'RunContext':
        """
        Factory method to create a new RunContext.
        Automatically registers in active runs.
        """
        ctx = cls(
            limits=limits,
            trace_enabled=trace_enabled,
            user_id=user_id,
            metadata=metadata
        )

        # Register
        cls._active_runs[ctx.run_id] = ctx

        return ctx

    @classmethod
    def get_by_id(cls, run_id: str) -> Optional['RunContext']:
        """Get a run context by ID (for debugging)"""
        return cls._active_runs.get(run_id)

    @classmethod
    def get_active_runs(cls) -> List['RunContext']:
        """Get all active runs"""
        return list(cls._active_runs.values())

    @classmethod
    def cleanup_old_runs(cls, max_age_seconds: float = 3600):
        """Remove old completed runs from registry"""
        now = datetime.now()
        to_remove = []

        for run_id, ctx in cls._active_runs.items():
            if ctx.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
                age = (now - ctx.created_at).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(run_id)

        for run_id in to_remove:
            del cls._active_runs[run_id]

        if to_remove:
            logger.info(f"[RunContext] Cleaned up {len(to_remove)} old runs")

    def set_callbacks(
        self,
        on_progress: Callable = None,
        on_agent_start: Callable = None,
        on_agent_complete: Callable = None,
        on_insight: Callable = None
    ):
        """Set progress callbacks (for WebSocket updates)"""
        self._on_progress = on_progress
        self._on_agent_start = on_agent_start
        self._on_agent_complete = on_agent_complete
        self._on_insight = on_insight

    def start(self):
        """Mark run as started"""
        self.status = RunStatus.RUNNING
        self.started_at = datetime.now()
        self.trace.log('run_started')
        logger.info(f"[RunContext] Run {self.run_id} started")

    def complete(self, success: bool = True, error: str = None):
        """Mark run as completed"""
        self.status = RunStatus.COMPLETED if success else RunStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
        self.trace.log('run_completed', data={'success': success, 'error': error})

        duration = self.duration
        logger.info(f"[RunContext] Run {self.run_id} completed in {duration:.2f}s (success={success})")

    def cancel(self, reason: str = "User cancelled"):
        """Cancel the run"""
        self._cancelled = True
        self._cancel_event.set()
        self.status = RunStatus.CANCELLED
        self.error = reason
        self.completed_at = datetime.now()
        self.trace.log('run_cancelled', data={'reason': reason})
        logger.info(f"[RunContext] Run {self.run_id} cancelled: {reason}")

    @property
    def is_cancelled(self) -> bool:
        """Check if run is cancelled"""
        return self._cancelled

    @property
    def duration(self) -> float:
        """Get run duration in seconds"""
        if self.started_at is None:
            return 0.0

        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    async def wait_for_cancel(self, timeout: float = None) -> bool:
        """Wait for cancellation event"""
        try:
            await asyncio.wait_for(self._cancel_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def emit_progress(self, agent_id: str, progress: float, message: str = None):
        """Emit progress update (thread-safe)"""
        self.trace.log('progress', agent_id=agent_id, data={'progress': progress, 'message': message})

        if self._on_progress:
            try:
                self._on_progress(self.run_id, agent_id, progress, message)
            except Exception as e:
                logger.error(f"[RunContext] Progress callback error: {e}")

    def emit_agent_start(self, agent_id: str, agent_name: str):
        """Emit agent start event"""
        self.trace.log('agent_start', agent_id=agent_id, data={'name': agent_name})

        if self._on_agent_start:
            try:
                self._on_agent_start(self.run_id, agent_id, agent_name)
            except Exception as e:
                logger.error(f"[RunContext] Agent start callback error: {e}")

    def emit_agent_complete(self, agent_id: str, result: Any):
        """Emit agent complete event"""
        self.trace.log('agent_complete', agent_id=agent_id, data={'status': str(result.status) if hasattr(result, 'status') else 'unknown'})

        if self._on_agent_complete:
            try:
                self._on_agent_complete(self.run_id, agent_id, result)
            except Exception as e:
                logger.error(f"[RunContext] Agent complete callback error: {e}")

    def emit_insight(self, agent_id: str, insight: Any):
        """Emit insight event"""
        self.trace.log('insight', agent_id=agent_id, data={'type': str(insight.type) if hasattr(insight, 'type') else 'unknown'})

        if self._on_insight:
            try:
                self._on_insight(self.run_id, agent_id, insight)
            except Exception as e:
                logger.error(f"[RunContext] Insight callback error: {e}")

    def get_state(self) -> Dict[str, Any]:
        """Get complete run state (for debugging)"""
        return {
            'run_id': self.run_id,
            'user_id': self.user_id,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration': self.duration,
            'error': self.error,
            'metadata': self.metadata,
            'message_bus_stats': self.message_bus.get_stats(),
            'blackboard_stats': self.blackboard.get_stats(),
            'trace': self.trace.to_dict() if self.trace.enabled else None
        }

    def __repr__(self) -> str:
        return f"RunContext(id={self.run_id}, status={self.status.value}, duration={self.duration:.2f}s)"


# Convenience functions (for backwards compatibility during migration)

def create_run_context(
    user_id: str = None,
    limits: RunLimits = None,
    **kwargs
) -> RunContext:
    """Create a new RunContext"""
    return RunContext.create(user_id=user_id, limits=limits, **kwargs)


def get_run_context(run_id: str) -> Optional[RunContext]:
    """Get RunContext by ID"""
    return RunContext.get_by_id(run_id)
