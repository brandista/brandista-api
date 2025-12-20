"""
Growth Engine 2.0 - Core Types
All types used across agents
"""

from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING = "waiting"


class AgentPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InsightType(str, Enum):
    FINDING = "finding"
    THREAT = "threat"
    OPPORTUNITY = "opportunity"
    RECOMMENDATION = "recommendation"
    METRIC = "metric"


@dataclass
class AnalysisContext:
    """Shared context passed between agents"""
    url: str
    competitor_urls: List[str] = field(default_factory=list)
    industry: Optional[str] = None
    country_code: str = "fi"
    user: Optional[Any] = None
    
    # Results from previous agents
    agent_results: Dict[str, Any] = field(default_factory=dict)
    
    # Callbacks for real-time updates
    on_insight: Optional[Callable] = None
    on_progress: Optional[Callable] = None
    on_status: Optional[Callable] = None


@dataclass
class AgentInsight:
    """Single insight emitted by an agent"""
    agent_id: str
    message: str
    priority: AgentPriority
    insight_type: InsightType
    timestamp: datetime = field(default_factory=datetime.now)
    data: Optional[Dict[str, Any]] = None


@dataclass
class AgentProgress:
    """Progress update from an agent"""
    agent_id: str
    progress: int  # 0-100
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
