# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Dynamic Task Delegation
TRUE SWARM AGENTS - Agents delegate tasks to each other

This enables agents to:
- Create tasks dynamically during execution
- Delegate tasks to other agents
- Request help with specific problems
- Track task completion
- Build complex workflows on the fly

Think of this as agents being able to "hire" each other.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import uuid

from .communication import (
    MessageBus,
    AgentMessage,
    MessageType,
    MessagePriority,
    get_message_bus
)
from .blackboard import (
    Blackboard,
    get_blackboard
)

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution status"""
    PENDING = "pending"        # Not started
    ASSIGNED = "assigned"      # Assigned to agent
    IN_PROGRESS = "in_progress"  # Being worked on
    COMPLETED = "completed"    # Successfully completed
    FAILED = "failed"          # Failed to complete
    CANCELLED = "cancelled"    # Cancelled before completion


class TaskPriority(Enum):
    """Task priority levels"""
    CRITICAL = 0   # Drop everything
    HIGH = 1       # Important
    MEDIUM = 2     # Normal
    LOW = 3        # When convenient


@dataclass
class DynamicTask:
    """
    A task that one agent delegates to another.
    
    Tasks are created on-the-fly during analysis when an agent
    realizes it needs help from another agent's expertise.
    """
    
    # Identity
    task_id: str
    created_by: str          # Agent that created task
    assigned_to: Optional[str] = None  # Agent assigned to task
    
    # Content
    task_type: str = "generic"  # Type of task (e.g. "deep_analysis", "competitor_check")
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Execution
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    timeout: float = 30.0  # Max execution time
    
    # Results
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    assigned_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Callbacks
    on_complete: Optional[Callable] = None
    on_error: Optional[Callable] = None
    
    # Metadata
    parent_task_id: Optional[str] = None  # For subtasks
    tags: set = field(default_factory=set)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'task_id': self.task_id,
            'created_by': self.created_by,
            'assigned_to': self.assigned_to,
            'task_type': self.task_type,
            'description': self.description,
            'parameters': self.parameters,
            'priority': self.priority.value,
            'status': self.status.value,
            'timeout': self.timeout,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at.isoformat(),
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'parent_task_id': self.parent_task_id,
            'tags': list(self.tags),
            'context': self.context
        }
    
    def duration(self) -> Optional[float]:
        """Get task duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class TaskDelegationManager:
    """
    Manager for dynamic task delegation.
    
    This is the task queue and coordination layer.
    Agents create tasks, manager assigns and tracks them.
    """
    
    def __init__(self):
        # All tasks
        self.tasks: Dict[str, DynamicTask] = {}
        
        # Agent queues: agent_id -> [task_ids]
        self.agent_queues: Dict[str, List[str]] = {}
        
        # Task execution futures
        self.task_futures: Dict[str, asyncio.Future] = {}
        
        # Communication
        self.message_bus = get_message_bus()
        self.blackboard = get_blackboard()
        
        # Statistics
        self.stats = {
            'total_created': 0,
            'total_completed': 0,
            'total_failed': 0,
            'by_agent': {},
            'by_type': {}
        }
        
        logger.info("[TaskManager] 📋 Task delegation manager initialized")
    
    def create_task(
        self,
        created_by: str,
        task_type: str,
        description: str,
        parameters: Dict[str, Any],
        priority: TaskPriority = TaskPriority.MEDIUM,
        timeout: float = 30.0,
        tags: Optional[set] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> DynamicTask:
        """
        Create a new task.
        
        Args:
            created_by: Agent creating the task
            task_type: Type of task
            description: Human-readable description
            parameters: Task parameters
            priority: Task priority
            timeout: Max execution time
            tags: Optional tags
            context: Optional context data
            
        Returns:
            Created DynamicTask
        
        Example:
            task = manager.create_task(
                created_by='guardian',
                task_type='deep_security_analysis',
                description='Analyze competitor security in depth',
                parameters={'url': 'example.com'},
                priority=TaskPriority.HIGH
            )
        """
        task = DynamicTask(
            task_id=str(uuid.uuid4()),
            created_by=created_by,
            task_type=task_type,
            description=description,
            parameters=parameters,
            priority=priority,
            timeout=timeout,
            tags=tags or set(),
            context=context or {}
        )
        
        # Store task
        self.tasks[task.task_id] = task
        
        # Update stats
        self.stats['total_created'] += 1
        
        if created_by not in self.stats['by_agent']:
            self.stats['by_agent'][created_by] = {
                'created': 0,
                'completed': 0
            }
        self.stats['by_agent'][created_by]['created'] += 1
        
        if task_type not in self.stats['by_type']:
            self.stats['by_type'][task_type] = 0
        self.stats['by_type'][task_type] += 1
        
        # Publish to blackboard
        self.blackboard.publish(
            key=f"tasks.pending.{task.task_id}",
            value=task.to_dict(),
            agent_id=created_by,
            tags={'task', 'pending', task_type}
        )
        
        logger.info(
            f"[TaskManager] ✨ Task created: {task_type} by {created_by}"
        )
        
        return task
    
    async def delegate_task(
        self,
        task: DynamicTask,
        to_agent: str
    ) -> bool:
        """
        Delegate task to specific agent.
        
        Args:
            task: Task to delegate
            to_agent: Agent to assign to
            
        Returns:
            True if delegated successfully
        """
        task.assigned_to = to_agent
        task.assigned_at = datetime.now()
        task.status = TaskStatus.ASSIGNED
        
        # Add to agent's queue
        if to_agent not in self.agent_queues:
            self.agent_queues[to_agent] = []
        self.agent_queues[to_agent].append(task.task_id)
        
        # Send task delegation message
        await self.message_bus.send(
            AgentMessage(
                id=f"task_{task.task_id}",
                from_agent=task.created_by,
                to_agent=to_agent,
                type=MessageType.TASK_DELEGATE,
                priority=self._map_priority(task.priority),
                subject=f"Task: {task.description}",
                payload={
                    'task_id': task.task_id,
                    'task_type': task.task_type,
                    'parameters': task.parameters,
                    'timeout': task.timeout,
                    'context': task.context
                },
                requires_response=True
            )
        )
        
        # Update blackboard
        self.blackboard.delete(f"tasks.pending.{task.task_id}")
        self.blackboard.publish(
            key=f"tasks.assigned.{task.task_id}",
            value=task.to_dict(),
            agent_id=task.created_by,
            tags={'task', 'assigned', task.task_type}
        )
        
        logger.info(
            f"[TaskManager] 📤 Task {task.task_id} delegated to {to_agent}"
        )
        
        return True
    
    async def auto_assign_task(
        self,
        task: DynamicTask,
        candidate_agents: List[str]
    ) -> bool:
        """
        Automatically assign task to best agent.
        
        This is smart delegation - picks the agent based on:
        - Agent's specialization
        - Current workload
        - Task priority
        
        Args:
            task: Task to assign
            candidate_agents: List of agents that can handle this
            
        Returns:
            True if assigned
        """
        if not candidate_agents:
            logger.warning(
                f"[TaskManager] ⚠️ No candidates for task {task.task_id}"
            )
            return False
        
        # Score each candidate
        scores = {}
        for agent_id in candidate_agents:
            score = self._score_agent_for_task(agent_id, task)
            scores[agent_id] = score
        
        # Pick best agent
        best_agent = max(scores.items(), key=lambda x: x[1])[0]
        
        # Delegate to best agent
        return await self.delegate_task(task, best_agent)
    
    def _score_agent_for_task(
        self,
        agent_id: str,
        task: DynamicTask
    ) -> float:
        """
        Score how suitable an agent is for a task.
        
        Higher score = better fit.
        """
        score = 1.0
        
        # Check current workload
        current_tasks = len(self.agent_queues.get(agent_id, []))
        workload_penalty = current_tasks * 0.2
        score -= workload_penalty
        
        # Boost for specialization
        # (would check agent capabilities here)
        
        # Boost for past success with this task type
        # (would check historical performance)
        
        return max(0.1, score)
    
    def _map_priority(self, task_priority: TaskPriority) -> MessagePriority:
        """Map task priority to message priority"""
        mapping = {
            TaskPriority.CRITICAL: MessagePriority.CRITICAL,
            TaskPriority.HIGH: MessagePriority.HIGH,
            TaskPriority.MEDIUM: MessagePriority.MEDIUM,
            TaskPriority.LOW: MessagePriority.LOW
        }
        return mapping.get(task_priority, MessagePriority.MEDIUM)
    
    async def wait_for_task(
        self,
        task: DynamicTask
    ) -> Any:
        """
        Wait for task to complete and return result.
        
        Args:
            task: Task to wait for
            
        Returns:
            Task result
            
        Raises:
            asyncio.TimeoutError: If task times out
            Exception: If task fails
        """
        # Create future for this task
        if task.task_id not in self.task_futures:
            self.task_futures[task.task_id] = asyncio.Future()
        
        future = self.task_futures[task.task_id]
        
        try:
            # Wait with timeout
            result = await asyncio.wait_for(
                future,
                timeout=task.timeout
            )
            return result
            
        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = "Task timed out"
            task.completed_at = datetime.now()
            
            logger.error(
                f"[TaskManager] ⏱️ Task {task.task_id} timed out"
            )
            raise
    
    def complete_task(
        self,
        task_id: str,
        result: Any,
        agent_id: str
    ):
        """
        Mark task as completed.
        
        Called by agent when task is done.
        
        Args:
            task_id: Task ID
            result: Task result
            agent_id: Agent that completed it
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"[TaskManager] ⚠️ Unknown task: {task_id}")
            return
        
        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = datetime.now()
        
        # Update stats
        self.stats['total_completed'] += 1
        self.stats['by_agent'][agent_id]['completed'] += 1
        
        # Remove from queue
        if agent_id in self.agent_queues:
            if task_id in self.agent_queues[agent_id]:
                self.agent_queues[agent_id].remove(task_id)
        
        # Resolve future
        if task_id in self.task_futures:
            self.task_futures[task_id].set_result(result)
        
        # Update blackboard
        self.blackboard.delete(f"tasks.assigned.{task_id}")
        self.blackboard.publish(
            key=f"tasks.completed.{task_id}",
            value=task.to_dict(),
            agent_id=agent_id,
            tags={'task', 'completed', task.task_type},
            ttl=3600  # Keep for 1 hour
        )
        
        # Call completion callback
        if task.on_complete:
            try:
                if asyncio.iscoroutinefunction(task.on_complete):
                    asyncio.create_task(task.on_complete(task))
                else:
                    task.on_complete(task)
            except Exception as e:
                logger.error(f"[TaskManager] Callback error: {e}")
        
        logger.info(
            f"[TaskManager] ✅ Task {task_id} completed by {agent_id} "
            f"in {task.duration():.1f}s"
        )
    
    def fail_task(
        self,
        task_id: str,
        error: str,
        agent_id: str
    ):
        """Mark task as failed"""
        task = self.tasks.get(task_id)
        if not task:
            return
        
        task.status = TaskStatus.FAILED
        task.error = error
        task.completed_at = datetime.now()
        
        # Update stats
        self.stats['total_failed'] += 1
        
        # Remove from queue
        if agent_id in self.agent_queues:
            if task_id in self.agent_queues[agent_id]:
                self.agent_queues[agent_id].remove(task_id)
        
        # Resolve future with exception
        if task_id in self.task_futures:
            self.task_futures[task_id].set_exception(
                Exception(error)
            )
        
        # Call error callback
        if task.on_error:
            try:
                if asyncio.iscoroutinefunction(task.on_error):
                    asyncio.create_task(task.on_error(task))
                else:
                    task.on_error(task)
            except Exception as e:
                logger.error(f"[TaskManager] Error callback error: {e}")
        
        logger.error(
            f"[TaskManager] ❌ Task {task_id} failed: {error}"
        )
    
    def get_task(self, task_id: str) -> Optional[DynamicTask]:
        """Get task by ID"""
        return self.tasks.get(task_id)
    
    def get_agent_tasks(
        self,
        agent_id: str,
        status: Optional[TaskStatus] = None
    ) -> List[DynamicTask]:
        """Get all tasks for an agent"""
        tasks = []
        
        for task_id in self.agent_queues.get(agent_id, []):
            task = self.tasks.get(task_id)
            if task and (status is None or task.status == status):
                tasks.append(task)
        
        return tasks
    
    def get_pending_tasks(self) -> List[DynamicTask]:
        """Get all pending tasks"""
        return [
            task for task in self.tasks.values()
            if task.status == TaskStatus.PENDING
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get delegation statistics"""
        return {
            **self.stats,
            'active_tasks': len([
                t for t in self.tasks.values()
                if t.status in [TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS]
            ]),
            'agent_queues': {
                agent: len(queue)
                for agent, queue in self.agent_queues.items()
            }
        }


# Global manager instance
_task_manager: Optional[TaskDelegationManager] = None


def get_task_manager() -> TaskDelegationManager:
    """Get or create global task manager"""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskDelegationManager()
    return _task_manager


def reset_task_manager():
    """Reset global manager (for testing)"""
    global _task_manager
    _task_manager = None
