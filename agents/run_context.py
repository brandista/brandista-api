# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - RunContext
Per-request isolation container for concurrent analysis runs.

This is the KEY to safe concurrent execution:
- Each analysis request gets its own RunContext
- RunContext contains isolated instances of bus, blackboard, etc.
- No global state = no cross-contamination between runs
- 10 users can run analyses simultaneously without interference

Now with RunStore integration for Redis-backed state persistence.
Works across multiple workers in production.

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
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

from .communication import MessageBus
from .blackboard import Blackboard
from .collaboration import CollaborationManager
from .task_delegation import TaskDelegationManager
from .learning import LearningSystem
from .run_store import RunStore, RunMeta, RunEvent, get_run_store, InMemoryRunStore

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

    NOTE: llm_semaphore and scrape_semaphore are available for controlling
    concurrent LLM/scrape operations. To use them, wrap LLM/scrape calls:

        async with run_context.limits.llm_semaphore:
            response = await openai.chat.completions.create(...)

        async with run_context.limits.scrape_semaphore:
            result = await scraper.fetch(url)

    TODO: Implement semaphore usage in actual LLM and scraping code.
    """
    # Semaphores
    llm_concurrency: int = 5          # Max concurrent LLM calls
    scrape_concurrency: int = 3       # Max concurrent web scrapes

    # Timeouts (seconds) - generous for analysis tasks
    total_timeout: float = 180.0      # 3 min total run timeout
    agent_timeout: float = 90.0       # 90s default per agent (analysis takes time)
    llm_timeout: float = 60.0         # 60s LLM call timeout
    scrape_timeout: float = 30.0      # 30s web scrape timeout

    # Per-agent timeout overrides (agent_id -> timeout_seconds)
    # Use this for agents that need more/less time than the default
    agent_timeouts: Dict[str, float] = field(default_factory=lambda: {
        'scout': 120.0,      # Scout may need to scrape multiple pages
        'analyst': 90.0,     # Standard analysis
        'guardian': 60.0,    # Threat detection is faster
        'prospector': 90.0,  # Opportunity analysis
        'strategist': 120.0, # Strategy synthesis takes longer
        'planner': 90.0,     # Action plan generation
    })

    def __post_init__(self):
        """Create semaphores"""
        self._llm_semaphore: Optional[asyncio.Semaphore] = None
        self._scrape_semaphore: Optional[asyncio.Semaphore] = None

    def get_agent_timeout(self, agent_id: str) -> float:
        """Get timeout for specific agent, or default"""
        return self.agent_timeouts.get(agent_id, self.agent_timeout)

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
    - RunStore (Redis-backed persistence for multi-worker)

    KEY PRINCIPLE: Agents NEVER access global singletons.
    They receive RunContext and use ctx.message_bus, ctx.blackboard, etc.

    In multi-worker production:
    - Status/result/cancel are persisted to Redis via RunStore
    - In-memory state (semaphores, bus) is local to this worker
    - Cancel checks poll Redis so any worker can cancel
    """

    # Registry of active runs (for debugging - local to this worker)
    _active_runs: Dict[str, 'RunContext'] = {}
    # Lock is created lazily to avoid asyncio issues at import time
    _registry_lock: Optional[asyncio.Lock] = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Get or create the registry lock (lazy init for asyncio safety)."""
        if cls._registry_lock is None:
            cls._registry_lock = asyncio.Lock()
        return cls._registry_lock

    # Shared RunStore (Redis or InMemory)
    _run_store: Optional[RunStore] = None

    def __init__(
        self,
        run_id: str = None,
        limits: RunLimits = None,
        trace_enabled: bool = True,
        user_id: str = None,
        url: str = None,
        metadata: Dict[str, Any] = None,
        run_store: RunStore = None
    ):
        # Identity
        self.run_id = run_id or str(uuid.uuid4())[:12]
        self.user_id = user_id
        self.url = url
        self.metadata = metadata or {}

        # Timestamps
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None

        # Status (local cache, truth is in RunStore)
        self.status = RunStatus.PENDING
        self.error: Optional[str] = None

        # Isolated instances (NOT global singletons!)
        # These remain in-memory for this worker
        self.message_bus = MessageBus()
        self.blackboard = Blackboard()
        self.task_manager = TaskDelegationManager()
        self.collaboration_manager = CollaborationManager()
        self.learning_system = LearningSystem()

        # Limits
        self.limits = limits or RunLimits()

        # Trace
        self.trace = RunTrace(enabled=trace_enabled)

        # RunStore for persistence (Redis in prod, InMemory in dev)
        self.run_store = run_store or self._get_shared_store()

        # Cancellation (local event + RunStore for cross-worker)
        self._cancelled = False
        # Event is created lazily to avoid asyncio issues when instantiating outside async context
        self._cancel_event: Optional[asyncio.Event] = None

        # Callbacks for progress updates
        self._on_progress: Optional[Callable] = None
        self._on_agent_start: Optional[Callable] = None
        self._on_agent_complete: Optional[Callable] = None
        self._on_insight: Optional[Callable] = None

        logger.info(f"[RunContext] Created run_id={self.run_id}")

    def _get_cancel_event(self) -> asyncio.Event:
        """Get or create the cancel event (lazy init for asyncio safety)."""
        if self._cancel_event is None:
            self._cancel_event = asyncio.Event()
        return self._cancel_event

    @classmethod
    def _get_shared_store(cls) -> RunStore:
        """Get or create shared RunStore"""
        if cls._run_store is None:
            cls._run_store = get_run_store()
        return cls._run_store

    @classmethod
    def set_run_store(cls, store: RunStore):
        """Set shared RunStore (call at startup)"""
        cls._run_store = store
        logger.info(f"[RunContext] RunStore set: {type(store).__name__}")

    @classmethod
    async def create(
        cls,
        user_id: str = None,
        url: str = None,
        limits: RunLimits = None,
        trace_enabled: bool = True,
        run_store: RunStore = None,
        **metadata
    ) -> 'RunContext':
        """
        Factory method to create a new RunContext.
        Automatically registers in active runs and RunStore.
        """
        ctx = cls(
            limits=limits,
            trace_enabled=trace_enabled,
            user_id=user_id,
            url=url,
            metadata=metadata,
            run_store=run_store
        )

        # Register locally with lock protection
        async with cls._get_lock():
            cls._active_runs[ctx.run_id] = ctx

        # Persist to RunStore (Redis)
        run_meta = RunMeta(
            run_id=ctx.run_id,
            user_id=user_id,
            url=url,
            created_at=ctx.created_at.isoformat(),
            metadata=metadata
        )
        await ctx.run_store.create_run(ctx.run_id, run_meta)

        return ctx

    @classmethod
    def create_sync(
        cls,
        user_id: str = None,
        url: str = None,
        limits: RunLimits = None,
        trace_enabled: bool = True,
        run_store: RunStore = None,
        **metadata
    ) -> 'RunContext':
        """
        Synchronous factory for backwards compatibility.
        Use create() (async) in new code.
        """
        ctx = cls(
            limits=limits,
            trace_enabled=trace_enabled,
            user_id=user_id,
            url=url,
            metadata=metadata,
            run_store=run_store
        )

        # Register locally only (RunStore will be updated on start())
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
    async def cleanup_old_runs(cls, max_age_seconds: float = 3600):
        """Remove old completed runs from registry (async for lock safety)."""
        now = datetime.now()
        to_remove = []

        async with cls._get_lock():
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

    async def start(self):
        """Mark run as started (persists to RunStore)"""
        self.status = RunStatus.RUNNING
        self.started_at = datetime.now()
        self.trace.log('run_started')

        # Persist to RunStore
        await self.run_store.set_status(self.run_id, 'running')
        await self.run_store.append_trace(self.run_id, RunEvent(
            event_type='run_started',
            data={'started_at': self.started_at.isoformat()}
        ))

        logger.info(f"[RunContext] Run {self.run_id} started")

    async def complete(self, success: bool = True, error: str = None, result: Dict[str, Any] = None):
        """Mark run as completed (persists to RunStore)"""
        self.status = RunStatus.COMPLETED if success else RunStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()
        self.trace.log('run_completed', data={'success': success, 'error': error})

        # Persist to RunStore
        status_str = 'completed' if success else 'failed'
        await self.run_store.set_status(self.run_id, status_str)

        if result:
            await self.run_store.set_result(self.run_id, result)

        await self.run_store.append_trace(self.run_id, RunEvent(
            event_type='run_completed',
            data={
                'success': success,
                'error': error,
                'completed_at': self.completed_at.isoformat(),
                'duration': self.duration
            }
        ))

        duration = self.duration
        logger.info(f"[RunContext] Run {self.run_id} completed in {duration:.2f}s (success={success})")

    async def cancel(self, reason: str = "User cancelled"):
        """
        Cancel the run (persists to RunStore).
        Idempotent - safe to call multiple times.
        """
        if self._cancelled:
            logger.debug(f"[RunContext] Run {self.run_id} already cancelled (idempotent)")
            return

        self._cancelled = True
        self._get_cancel_event().set()
        self.status = RunStatus.CANCELLED
        self.error = reason
        self.completed_at = datetime.now()
        self.trace.log('run_cancelled', data={'reason': reason})

        # Persist to RunStore (sets cancel flag that other workers can poll)
        await self.run_store.cancel(self.run_id)
        await self.run_store.append_trace(self.run_id, RunEvent(
            event_type='run_cancelled',
            data={'reason': reason, 'cancelled_at': self.completed_at.isoformat()}
        ))

        logger.info(f"[RunContext] Run {self.run_id} cancelled: {reason}")

    @property
    def is_cancelled(self) -> bool:
        """Check if run is cancelled (local cache)"""
        return self._cancelled

    async def check_cancelled(self) -> bool:
        """
        Check if run is cancelled (polls RunStore for cross-worker cancel).
        Call this in long-running loops to respect cancel from other workers.
        """
        if self._cancelled:
            return True

        # Poll RunStore (Redis) for cancel from another worker
        cancelled = await self.run_store.is_cancelled(self.run_id)
        if cancelled:
            self._cancelled = True
            self._get_cancel_event().set()
            self.status = RunStatus.CANCELLED
            logger.info(f"[RunContext] Run {self.run_id} cancelled (detected from RunStore)")

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
            await asyncio.wait_for(self._get_cancel_event().wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def emit_progress(self, agent_id: str, progress: float, message: str = None):
        """Emit progress update (persists to RunStore stream)"""
        self.trace.log('progress', agent_id=agent_id, data={'progress': progress, 'message': message})

        # Emit to RunStore stream (for cross-worker WS forwarding)
        await self.run_store.emit_event(self.run_id, RunEvent(
            event_type='agent.progress',
            agent_id=agent_id,
            data={'progress': progress, 'message': message}
        ))

        if self._on_progress:
            try:
                self._on_progress(self.run_id, agent_id, progress, message)
            except Exception as e:
                logger.error(f"[RunContext] Progress callback error: {e}")

    async def emit_agent_start(self, agent_id: str, agent_name: str):
        """Emit agent start event (persists to RunStore stream)"""
        self.trace.log('agent_start', agent_id=agent_id, data={'name': agent_name})

        await self.run_store.emit_event(self.run_id, RunEvent(
            event_type='agent.start',
            agent_id=agent_id,
            data={'name': agent_name}
        ))

        if self._on_agent_start:
            try:
                self._on_agent_start(self.run_id, agent_id, agent_name)
            except Exception as e:
                logger.error(f"[RunContext] Agent start callback error: {e}")

    async def emit_agent_complete(self, agent_id: str, result: Any):
        """Emit agent complete event (persists to RunStore stream)"""
        status_str = str(result.status) if hasattr(result, 'status') else 'unknown'
        self.trace.log('agent_complete', agent_id=agent_id, data={'status': status_str})

        await self.run_store.emit_event(self.run_id, RunEvent(
            event_type='agent.complete',
            agent_id=agent_id,
            data={'status': status_str}
        ))

        if self._on_agent_complete:
            try:
                self._on_agent_complete(self.run_id, agent_id, result)
            except Exception as e:
                logger.error(f"[RunContext] Agent complete callback error: {e}")

    async def emit_insight(self, agent_id: str, insight: Any):
        """Emit insight event (persists to RunStore stream)"""
        insight_type = str(insight.insight_type) if hasattr(insight, 'insight_type') else 'unknown'
        self.trace.log('insight', agent_id=agent_id, data={'type': insight_type})

        # Serialize insight for Redis
        insight_data = {
            'type': insight_type,
            'message': str(insight.message) if hasattr(insight, 'message') else '',
            'priority': str(insight.priority) if hasattr(insight, 'priority') else 'medium'
        }

        await self.run_store.emit_event(self.run_id, RunEvent(
            event_type='agent.insight',
            agent_id=agent_id,
            data=insight_data
        ))

        if self._on_insight:
            try:
                self._on_insight(self.run_id, agent_id, insight)
            except Exception as e:
                logger.error(f"[RunContext] Insight callback error: {e}")

    async def emit_swarm_event(self, event_type: str, data: Dict[str, Any]):
        """Emit generic swarm event (persists to RunStore stream)"""
        self.trace.log(event_type, data=data)

        await self.run_store.emit_event(self.run_id, RunEvent(
            event_type=event_type,
            agent_id=data.get('from_agent'),
            data=data
        ))

    async def read_events(self, last_id: str = "0", count: int = 100, block_ms: int = 0) -> List[RunEvent]:
        """Read events from stream (for WS forwarding)"""
        return await self.run_store.read_events(self.run_id, last_id, count, block_ms)

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

async def create_run_context(
    user_id: str = None,
    url: str = None,
    limits: RunLimits = None,
    **kwargs
) -> RunContext:
    """Create a new RunContext (async)"""
    return await RunContext.create(user_id=user_id, url=url, limits=limits, **kwargs)


def create_run_context_sync(
    user_id: str = None,
    url: str = None,
    limits: RunLimits = None,
    **kwargs
) -> RunContext:
    """Create a new RunContext (sync, for backwards compat)"""
    return RunContext.create_sync(user_id=user_id, url=url, limits=limits, **kwargs)


def get_run_context(run_id: str) -> Optional[RunContext]:
    """Get RunContext by ID (local worker only)"""
    return RunContext.get_by_id(run_id)


async def get_run_from_store(run_id: str) -> Optional[Dict[str, Any]]:
    """Get run data from RunStore (Redis - works across workers)"""
    store = RunContext._get_shared_store()
    return await store.get_run(run_id)


async def list_runs_from_store(
    limit: int = 50,
    offset: int = 0,
    status: str = None,
    user_id: str = None
) -> List[Dict[str, Any]]:
    """List runs from RunStore (Redis - works across workers)"""
    store = RunContext._get_shared_store()
    return await store.list_runs(limit=limit, offset=offset, status=status, user_id=user_id)


async def cancel_run(run_id: str, reason: str = "User cancelled") -> bool:
    """
    Cancel a run by ID (works across workers via Redis).
    Returns True if cancelled, False if run not found.
    """
    # Try local context first
    ctx = RunContext.get_by_id(run_id)
    if ctx:
        await ctx.cancel(reason)
        return True

    # Otherwise cancel via RunStore directly
    store = RunContext._get_shared_store()
    return await store.cancel(run_id)
