# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Agent System Types
TRUE SWARM EDITION - Enhanced with real-time communication types

Version: 2.1.0 - Full Swarm Implementation
"""

from enum import Enum
from typing import Dict, List, Any, Optional, Set
from pydantic import BaseModel, Field
from datetime import datetime


class AgentStatus(str, Enum):
    """Agent state"""
    IDLE = "idle"
    THINKING = "thinking"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    WAITING = "waiting"
    COLLABORATING = "collaborating"  # NEW: In collaboration session
    LISTENING = "listening"          # NEW: Processing incoming messages


class AgentPriority(int, Enum):
    """Insight priority"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class InsightType(str, Enum):
    """Insight type for UX"""
    THREAT = "threat"
    OPPORTUNITY = "opportunity"
    FINDING = "finding"
    RECOMMENDATION = "recommendation"
    ACTION = "action"
    COLLABORATION = "collaboration"  # NEW: From multi-agent discussion
    CONSENSUS = "consensus"          # NEW: Agreed upon by multiple agents


class SwarmEventType(str, Enum):
    """Types of swarm events for real-time monitoring"""
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"
    BLACKBOARD_PUBLISH = "blackboard_publish"
    BLACKBOARD_SUBSCRIBE = "blackboard_subscribe"
    COLLABORATION_START = "collaboration_start"
    COLLABORATION_VOTE = "collaboration_vote"
    COLLABORATION_CONSENSUS = "collaboration_consensus"
    TASK_DELEGATED = "task_delegated"
    TASK_COMPLETED = "task_completed"
    AGENT_ALERT = "agent_alert"
    LEARNING_UPDATE = "learning_update"
    # NEW: Real-time agent conversation events for frontend visualization
    AGENT_CONVERSATION = "agent_conversation"
    COLLABORATION_STARTED = "collaboration_started"
    COLLABORATION_COMPLETE = "collaboration_complete"
    COLLABORATION_ENDED = "collaboration_ended"
    PLAN_VALIDATED = "plan_validated"


class AgentInsight(BaseModel):
    """Single agent insight (for real-time stream)"""
    agent_id: str
    agent_name: str
    agent_avatar: str
    message: str
    priority: AgentPriority
    insight_type: InsightType
    timestamp: datetime = Field(default_factory=datetime.now)
    data: Optional[Dict[str, Any]] = None
    
    # NEW: Swarm metadata
    from_collaboration: bool = False
    contributing_agents: List[str] = []
    confidence: float = 1.0
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class SwarmEvent(BaseModel):
    """Real-time swarm activity event"""
    event_type: SwarmEventType
    from_agent: str
    to_agent: Optional[str] = None
    subject: str
    timestamp: datetime = Field(default_factory=datetime.now)
    data: Dict[str, Any] = {}
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AgentProgress(BaseModel):
    """Agent progress (for real-time stream)"""
    agent_id: str
    status: AgentStatus
    progress: int = Field(ge=0, le=100)
    current_task: Optional[str] = None
    
    # NEW: Swarm activity
    messages_sent: int = 0
    messages_received: int = 0
    collaborations_active: int = 0


class AgentResult(BaseModel):
    """Agent final result"""
    agent_id: str
    agent_name: str
    status: AgentStatus
    execution_time_ms: int
    insights: List[AgentInsight] = []
    data: Dict[str, Any] = {}
    error: Optional[str] = None
    
    # NEW: Swarm metrics
    swarm_stats: Dict[str, Any] = Field(default_factory=lambda: {
        'messages_sent': 0,
        'messages_received': 0,
        'blackboard_writes': 0,
        'blackboard_reads': 0,
        'collaborations_participated': 0,
        'tasks_delegated': 0,
        'tasks_received': 0
    })


class AnalysisContext(BaseModel):
    """Context shared between agents"""
    # Run tracking (NEW)
    run_id: Optional[str] = None  # Links to RunContext

    # Input
    url: str
    competitor_urls: List[str] = []
    language: str = "fi"
    industry_context: Optional[str] = None
    user_id: Optional[str] = None

    # Revenue input (user-provided)
    revenue_input: Optional[Dict[str, Any]] = None
    # Business ID (Y-tunnus, user-provided)
    business_id: Optional[str] = None

    # Shared state (updates as agents progress)
    agent_results: Dict[str, AgentResult] = {}

    # Raw data
    html_content: Optional[str] = None
    website_data: Optional[Dict[str, Any]] = None
    competitor_data: List[Dict[str, Any]] = []

    # Unified Context (historical data)
    unified_context: Optional[Dict[str, Any]] = None

    # NEW: Real-time swarm state
    swarm_events: List[SwarmEvent] = []
    active_collaborations: Dict[str, Any] = {}

    # ========================================================================
    # SHARED KNOWLEDGE - Bemufix-style real-time knowledge sharing
    # ========================================================================
    shared_knowledge: Dict[str, Any] = Field(default_factory=lambda: {
        'detected_threats': [],           # Guardian löytämät uhat
        'detected_opportunities': [],     # Prospector löytämät mahdollisuudet
        'competitor_insights': [],        # Scout kilpailijainsightit
        'priority_actions': [],           # Guardianin priorisoidut toimenpiteet
        'strategic_recommendations': [],  # Strategist suositukset
        'collaboration_results': [],      # Yhteistyön tulokset
        'predictions': [],                # LearningSystem ennusteet
        'agent_contributions': {}         # Kuka lisäsi mitäkin
    })

    class Config:
        arbitrary_types_allowed = True

    def add_swarm_event(self, event: SwarmEvent):
        """Add swarm event to context (for monitoring)"""
        self.swarm_events.append(event)
        # Keep only last 100 events
        if len(self.swarm_events) > 100:
            self.swarm_events = self.swarm_events[-100:]

    def add_to_shared(self, key: str, value: Any, agent_id: str):
        """
        Add data to shared knowledge (Bemufix-style).
        All agents can see this data immediately.
        """
        if key not in self.shared_knowledge:
            self.shared_knowledge[key] = []

        # Add to list or replace value
        if isinstance(self.shared_knowledge[key], list):
            self.shared_knowledge[key].append(value)
        else:
            self.shared_knowledge[key] = value

        # Track who contributed what
        if 'agent_contributions' not in self.shared_knowledge:
            self.shared_knowledge['agent_contributions'] = {}
        if agent_id not in self.shared_knowledge['agent_contributions']:
            self.shared_knowledge['agent_contributions'][agent_id] = []
        self.shared_knowledge['agent_contributions'][agent_id].append({
            'key': key,
            'timestamp': datetime.now().isoformat()
        })

    def get_from_shared(self, key: str, default: Any = None) -> Any:
        """Get data from shared knowledge"""
        return self.shared_knowledge.get(key, default)

    def get_threats_from_agents(self, agent_ids: Optional[List[str]] = None) -> List[Dict]:
        """Get threats, optionally filtered by agent"""
        threats = self.shared_knowledge.get('detected_threats', [])
        if agent_ids:
            return [t for t in threats if t.get('source_agent') in agent_ids]
        return threats

    def get_opportunities_from_agents(self, agent_ids: Optional[List[str]] = None) -> List[Dict]:
        """Get opportunities, optionally filtered by agent"""
        opps = self.shared_knowledge.get('detected_opportunities', [])
        if agent_ids:
            return [o for o in opps if o.get('source_agent') in agent_ids]
        return opps


class OrchestrationResult(BaseModel):
    """Full analysis result"""
    # Run tracking (NEW)
    run_id: Optional[str] = None  # Links to RunContext

    success: bool
    execution_time_ms: int = 0
    duration_seconds: float = 0.0
    url: str = ""
    competitor_count: int = 0
    
    # Results
    overall_score: int = Field(default=50, ge=0, le=100)
    composite_scores: Dict[str, int] = {}
    
    # Agent results
    agent_results: Dict[str, AgentResult] = {}
    context: Optional[AnalysisContext] = None
    
    # Insights by priority
    critical_insights: List[AgentInsight] = []
    high_insights: List[AgentInsight] = []
    
    # Action plan
    action_plan: Optional[Dict[str, Any]] = None
    
    # Errors
    errors: List[str] = []
    error: Optional[str] = None
    
    # NEW: Swarm summary
    swarm_summary: Dict[str, Any] = Field(default_factory=lambda: {
        'total_messages': 0,
        'total_collaborations': 0,
        'consensus_reached': 0,
        'tasks_delegated': 0,
        'cross_agent_insights': 0
    })
    
    metadata: Dict[str, Any] = {}


class WSMessageType(str, Enum):
    """WebSocket message types"""
    AGENT_STATUS = "agent_status"
    AGENT_INSIGHT = "agent_insight"
    AGENT_PROGRESS = "agent_progress"
    ANALYSIS_COMPLETE = "analysis_complete"
    ERROR = "error"
    
    # NEW: Swarm events
    SWARM_EVENT = "swarm_event"
    COLLABORATION_UPDATE = "collaboration_update"
    AGENT_MESSAGE = "agent_message"


class WSMessage(BaseModel):
    """WebSocket message"""
    type: WSMessageType
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
