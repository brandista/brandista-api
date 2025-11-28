"""
Growth Engine 2.0 - Agent System Types
Tyypit ja datamallit agenttijärjestelmälle
"""

from enum import Enum
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class AgentStatus(str, Enum):
    """Agentin tila"""
    IDLE = "idle"
    THINKING = "thinking"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"
    WAITING = "waiting"  # Odottaa riippuvuuksia


class AgentPriority(int, Enum):
    """Insight-prioriteetti"""
    CRITICAL = 1   # Kriittinen - näytetään heti
    HIGH = 2       # Korkea - tärkeä löydös
    MEDIUM = 3     # Normaali
    LOW = 4        # Matala - taustatieto


class InsightType(str, Enum):
    """Insight-tyyppi UX:ää varten"""
    THREAT = "threat"           # 🛡️ Guardian
    OPPORTUNITY = "opportunity" # 💎 Prospector
    FINDING = "finding"         # 🔍 Scout / 📊 Analyst
    RECOMMENDATION = "recommendation"  # 🎯 Strategist
    ACTION = "action"           # 📋 Planner


class AgentInsight(BaseModel):
    """Yksittäinen agentti-insight (real-time streamiin)"""
    agent_id: str
    agent_name: str
    agent_avatar: str
    message: str
    priority: AgentPriority
    insight_type: InsightType
    timestamp: datetime = Field(default_factory=datetime.now)
    data: Optional[Dict[str, Any]] = None  # Lisädata (esim. €-summa)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class AgentProgress(BaseModel):
    """Agentin edistyminen (real-time streamiin)"""
    agent_id: str
    status: AgentStatus
    progress: int = Field(ge=0, le=100)  # 0-100%
    current_task: Optional[str] = None
    
    
class AgentResult(BaseModel):
    """Agentin lopputulos"""
    agent_id: str
    agent_name: str
    status: AgentStatus
    execution_time_ms: int
    insights: List[AgentInsight] = []
    data: Dict[str, Any] = {}
    error: Optional[str] = None


class AnalysisContext(BaseModel):
    """Konteksti joka jaetaan agenttien välillä"""
    # Input
    url: str
    competitor_urls: List[str] = []
    language: str = "fi"
    industry_context: Optional[str] = None
    user_id: Optional[str] = None  # For unified context lookup
    
    # Revenue input (for accurate ROI calculations)
    revenue_input: Optional[Dict[str, Any]] = None  # {'annual_revenue': 500000} or {'monthly_revenue': 40000}
    
    # Shared state (päivittyy agenttien edetessä)
    agent_results: Dict[str, AgentResult] = {}
    
    # Raw data (täytetään analyysin aikana)
    html_content: Optional[str] = None
    website_data: Optional[Dict[str, Any]] = None
    competitor_data: List[Dict[str, Any]] = []
    
    # Unified Context (historical data from all tabs)
    unified_context: Optional[Dict[str, Any]] = None
    
    class Config:
        arbitrary_types_allowed = True


class OrchestrationResult(BaseModel):
    """Koko analyysin lopputulos"""
    success: bool
    execution_time_ms: int
    url: str
    competitor_count: int
    
    # Kokonaistulokset
    overall_score: int = Field(ge=0, le=100)
    composite_scores: Dict[str, int] = {}
    
    # Agenttien tulokset
    agent_results: Dict[str, AgentResult] = {}
    
    # Kootut insightit prioriteetin mukaan
    critical_insights: List[AgentInsight] = []
    high_insights: List[AgentInsight] = []
    
    # Toimintasuunnitelma
    action_plan: Optional[Dict[str, Any]] = None
    
    # Virheet
    errors: List[str] = []


# WebSocket message types
class WSMessageType(str, Enum):
    """WebSocket-viestitypit"""
    AGENT_STATUS = "agent_status"
    AGENT_INSIGHT = "agent_insight"
    AGENT_PROGRESS = "agent_progress"
    ANALYSIS_COMPLETE = "analysis_complete"
    ERROR = "error"


class WSMessage(BaseModel):
    """WebSocket-viesti"""
    type: WSMessageType
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
