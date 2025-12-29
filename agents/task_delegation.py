# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Task Delegation Framework
TRUE SWARM EDITION - Dynamic task creation and assignment
"""

import asyncio
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Set
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class DynamicTask:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    task_type: str = "custom"
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_by: str = ""
    assigned_to: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    result: Any = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    timeout: float = 30.0
    retries: int = 0
    max_retries: int = 2
    tags: Set[str] = field(default_factory=set)
    
    def is_expired(self) -> bool:
        if self.status not in [TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS]:
            return False
        start = self.started_at or self.assigned_at or self.created_at
        return (datetime.now() - start).total_seconds() > self.timeout
    
    def can_retry(self) -> bool:
        return self.retries < self.max_retries


@dataclass
class AgentCapability:
    agent_id: str
    task_types: Set[str] = field(default_factory=set)
    specializations: Set[str] = field(default_factory=set)
    current_load: int = 0
    max_load: int = 5
    success_rate: float = 1.0
    
    def can_accept_task(self, task_type: str) -> bool:
        if self.current_load >= self.max_load:
            return False
        if self.task_types and task_type not in self.task_types:
            return False
        return True
    
    def score_for_task(self, task: DynamicTask) -> float:
        score = 0.0
        if task.task_type in self.task_types:
            score += 30
        load_factor = 1 - (self.current_load / max(self.max_load, 1))
        score += load_factor * 25
        score += self.success_rate * 25
        return score


class TaskDelegationManager:
    def __init__(self):
        self._tasks: Dict[str, DynamicTask] = {}
        self._completed_tasks: List[DynamicTask] = []
        self._agent_capabilities: Dict[str, AgentCapability] = {}
        self._agent_queues: Dict[str, asyncio.Queue] = {}
        self._waiting: Dict[str, asyncio.Future] = {}
        self._on_task_completed: Optional[Callable] = None
        self._stats = {
            'total_created': 0,
            'total_completed': 0,
            'total_failed': 0,
            'total_timeout': 0,
            'by_type': defaultdict(int),
            'by_agent': defaultdict(lambda: {'assigned': 0, 'completed': 0, 'failed': 0})
        }
        logger.info("[TaskDelegationManager] 📋 Task manager initialized")
    
    def register_agent(self, agent_id: str, task_types: Optional[Set[str]] = None, max_load: int = 5):
        self._agent_capabilities[agent_id] = AgentCapability(
            agent_id=agent_id, task_types=task_types or set(), max_load=max_load
        )
        if agent_id not in self._agent_queues:
            self._agent_queues[agent_id] = asyncio.Queue()
    
    def create_task(self, created_by: str, task_type: str, description: str,
                    parameters: Optional[Dict[str, Any]] = None,
                    priority: TaskPriority = TaskPriority.MEDIUM,
                    timeout: float = 30.0) -> DynamicTask:
        task = DynamicTask(
            task_type=task_type, description=description,
            parameters=parameters or {}, created_by=created_by,
            priority=priority, timeout=timeout
        )
        self._tasks[task.task_id] = task
        self._stats['total_created'] += 1
        self._stats['by_type'][task_type] += 1
        logger.info(f"[TaskDelegationManager] 📝 Task {task.task_id} created by {created_by}")
        return task
    
    async def delegate_task(self, task: DynamicTask, to_agent: str) -> bool:
        if to_agent not in self._agent_capabilities:
            return False
        cap = self._agent_capabilities[to_agent]
        if not cap.can_accept_task(task.task_type):
            return False
        
        task.assigned_to = to_agent
        task.assigned_at = datetime.now()
        task.status = TaskStatus.ASSIGNED
        cap.current_load += 1
        await self._agent_queues[to_agent].put(task)
        self._stats['by_agent'][to_agent]['assigned'] += 1
        logger.info(f"[TaskDelegationManager] 📨 Task {task.task_id} -> {to_agent}")
        return True
    
    async def auto_assign_task(self, task: DynamicTask, candidates: Optional[List[str]] = None) -> Optional[str]:
        candidate_ids = candidates or list(self._agent_capabilities.keys())
        scores = [(aid, self._agent_capabilities[aid].score_for_task(task))
                  for aid in candidate_ids 
                  if aid in self._agent_capabilities and self._agent_capabilities[aid].can_accept_task(task.task_type)]
        if not scores:
            return None
        scores.sort(key=lambda x: x[1], reverse=True)
        best = scores[0][0]
        success = await self.delegate_task(task, best)
        return best if success else None
    
    def complete_task(self, task_id: str, result: Any, agent_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.assigned_to != agent_id:
            return False
        
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        task.result = result
        
        if agent_id in self._agent_capabilities:
            self._agent_capabilities[agent_id].current_load -= 1
        
        self._stats['total_completed'] += 1
        self._stats['by_agent'][agent_id]['completed'] += 1
        self._completed_tasks.append(task)
        
        if task_id in self._waiting and not self._waiting[task_id].done():
            self._waiting[task_id].set_result(result)
        
        logger.info(f"[TaskDelegationManager] ✅ Task {task_id} completed")
        return True
    
    def fail_task(self, task_id: str, error: str, agent_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        
        task.error = error
        task.retries += 1
        
        if agent_id in self._agent_capabilities:
            self._agent_capabilities[agent_id].current_load -= 1
        
        if task.can_retry():
            task.status = TaskStatus.PENDING
            task.assigned_to = None
            return True
        
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.now()
        self._stats['total_failed'] += 1
        self._stats['by_agent'][agent_id]['failed'] += 1
        
        if task_id in self._waiting and not self._waiting[task_id].done():
            self._waiting[task_id].set_exception(Exception(error))
        
        logger.error(f"[TaskDelegationManager] ❌ Task {task_id} failed: {error}")
        return True
    
    async def wait_for_task(self, task: DynamicTask, timeout: Optional[float] = None) -> Any:
        if task.status == TaskStatus.COMPLETED:
            return task.result
        if task.status == TaskStatus.FAILED:
            raise Exception(task.error or "Task failed")
        
        future = asyncio.Future()
        self._waiting[task.task_id] = future
        
        try:
            return await asyncio.wait_for(future, timeout=timeout or task.timeout)
        except asyncio.TimeoutError:
            task.status = TaskStatus.TIMEOUT
            self._stats['total_timeout'] += 1
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_created': self._stats['total_created'],
            'total_completed': self._stats['total_completed'],
            'total_failed': self._stats['total_failed'],
            'total_timeout': self._stats['total_timeout'],
            'by_type': dict(self._stats['by_type']),
            'by_agent': {k: dict(v) for k, v in self._stats['by_agent'].items()}
        }
    
    def reset(self):
        self._tasks.clear()
        self._completed_tasks.clear()
        self._agent_capabilities.clear()
        self._agent_queues.clear()
        self._waiting.clear()
        self._stats = {
            'total_created': 0, 'total_completed': 0, 'total_failed': 0,
            'total_timeout': 0, 'by_type': defaultdict(int),
            'by_agent': defaultdict(lambda: {'assigned': 0, 'completed': 0, 'failed': 0})
        }


_task_manager: Optional[TaskDelegationManager] = None

def get_task_manager() -> TaskDelegationManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskDelegationManager()
    return _task_manager

def reset_task_manager():
    global _task_manager
    if _task_manager:
        _task_manager.reset()
    _task_manager = None
