# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Agent System
TRUE SWARM EDITION

A complete multi-agent system with real inter-agent communication.
"""

from .agent_types import (
    AgentStatus,
    AgentPriority,
    InsightType,
    AgentInsight,
    AgentProgress,
    AgentResult,
    AnalysisContext,
    OrchestrationResult,
    SwarmEvent,
    SwarmEventType,
    WSMessageType,
    WSMessage
)

from .base_agent import BaseAgent

from .scout_agent import ScoutAgent
from .analyst_agent import AnalystAgent
from .guardian_agent import GuardianAgent
from .prospector_agent import ProspectorAgent
from .strategist_agent import StrategistAgent
from .planner_agent import PlannerAgent

from .orchestrator import (
    GrowthEngineOrchestrator,
    get_orchestrator,
    reset_orchestrator
)

from .communication import (
    MessageBus,
    MessageType,
    MessagePriority,
    AgentMessage,
    get_message_bus,
    reset_message_bus
)

from .blackboard import (
    Blackboard,
    BlackboardEntry,
    DataCategory,
    get_blackboard,
    reset_blackboard
)

from .collaboration import (
    CollaborationManager,
    CollaborationResult,
    VoteType,
    get_collaboration_manager,
    reset_collaboration_manager
)

from .task_delegation import (
    TaskDelegationManager,
    DynamicTask,
    TaskStatus,
    TaskPriority,
    get_task_manager,
    reset_task_manager
)

from .learning import (
    LearningSystem,
    get_learning_system,
    reset_learning_system
)

__version__ = "2.1.0"
__all__ = [
    # Types
    'AgentStatus', 'AgentPriority', 'InsightType',
    'AgentInsight', 'AgentProgress', 'AgentResult',
    'AnalysisContext', 'OrchestrationResult',
    'SwarmEvent', 'SwarmEventType',
    'WSMessageType', 'WSMessage',
    
    # Agents
    'BaseAgent',
    'ScoutAgent', 'AnalystAgent', 'GuardianAgent',
    'ProspectorAgent', 'StrategistAgent', 'PlannerAgent',
    
    # Orchestrator
    'GrowthEngineOrchestrator', 'get_orchestrator', 'reset_orchestrator',
    
    # Communication
    'MessageBus', 'MessageType', 'MessagePriority', 'AgentMessage',
    'get_message_bus', 'reset_message_bus',
    
    # Blackboard
    'Blackboard', 'BlackboardEntry', 'DataCategory',
    'get_blackboard', 'reset_blackboard',
    
    # Collaboration
    'CollaborationManager', 'CollaborationResult', 'VoteType',
    'get_collaboration_manager', 'reset_collaboration_manager',
    
    # Tasks
    'TaskDelegationManager', 'DynamicTask', 'TaskStatus', 'TaskPriority',
    'get_task_manager', 'reset_task_manager',
    
    # Learning
    'LearningSystem', 'get_learning_system', 'reset_learning_system'
]
