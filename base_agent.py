"""
Growth Engine 2.0 - Base Agent
Foundation class for all agents - English only, no translations
"""

import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime

from .types import (
    AnalysisContext,
    AgentStatus,
    AgentPriority,
    InsightType,
    AgentInsight,
    AgentProgress
)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Base class for all Growth Engine agents.
    
    All text output is in English - frontend handles translations.
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        avatar: str,
        personality: str
    ):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.avatar = avatar
        self.personality = personality
        
        self._status = AgentStatus.IDLE
        self._progress = 0
        self._context: Optional[AnalysisContext] = None
        self._insights: List[AgentInsight] = []
        
        # Dependencies (other agent IDs that must complete first)
        self.dependencies: List[str] = []
    
    @property
    def status(self) -> AgentStatus:
        return self._status
    
    @status.setter
    def status(self, value: AgentStatus):
        self._status = value
        if self._context and self._context.on_status:
            self._context.on_status(self.agent_id, value)
    
    async def run(self, context: AnalysisContext) -> Dict[str, Any]:
        """Execute the agent's analysis"""
        self._context = context
        self._insights = []
        self._progress = 0
        
        try:
            self.status = AgentStatus.RUNNING
            self._update_progress(5, f"{self.name} starting...")
            
            # Execute agent-specific logic
            result = await self.execute(context)
            
            self._update_progress(100, f"{self.name} complete")
            self.status = AgentStatus.COMPLETED
            
            return result
            
        except Exception as e:
            logger.error(f"[{self.agent_id}] Error: {e}", exc_info=True)
            self.status = AgentStatus.FAILED
            self._emit_insight(
                f"Analysis failed: {str(e)}",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
            raise
    
    @abstractmethod
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """Agent-specific execution logic - must be implemented by subclasses"""
        pass
    
    def _emit_insight(
        self,
        message: str,
        priority: AgentPriority = AgentPriority.MEDIUM,
        insight_type: InsightType = InsightType.FINDING,
        data: Optional[Dict[str, Any]] = None
    ):
        """Emit an insight to the frontend"""
        insight = AgentInsight(
            agent_id=self.agent_id,
            message=message,
            priority=priority,
            insight_type=insight_type,
            timestamp=datetime.now(),
            data=data
        )
        
        self._insights.append(insight)
        
        if self._context and self._context.on_insight:
            self._context.on_insight(insight)
        
        logger.info(f"[{self.agent_id}] {priority.value.upper()}: {message}")
    
    def _update_progress(self, progress: int, message: str):
        """Update progress percentage"""
        self._progress = min(100, max(0, progress))
        
        progress_update = AgentProgress(
            agent_id=self.agent_id,
            progress=self._progress,
            message=message,
            timestamp=datetime.now()
        )
        
        if self._context and self._context.on_progress:
            self._context.on_progress(progress_update)
        
        logger.debug(f"[{self.agent_id}] Progress: {self._progress}% - {message}")
    
    def get_dependency_results(self, context: AnalysisContext, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get results from a dependency agent"""
        return context.agent_results.get(agent_id)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize agent info"""
        return {
            'id': self.agent_id,
            'name': self.name,
            'role': self.role,
            'avatar': self.avatar,
            'personality': self.personality,
            'status': self._status.value,
            'progress': self._progress,
            'dependencies': self.dependencies
        }
