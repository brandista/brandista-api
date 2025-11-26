"""
Growth Engine 2.0 - Agent Orchestrator
Coordinates the execution of all agents in the correct order
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field

from .types import AnalysisContext, AgentStatus, AgentInsight, AgentProgress
from .scout_agent import ScoutAgent
from .analyst_agent import AnalystAgent
from .guardian_agent import GuardianAgent
from .prospector_agent import ProspectorAgent
from .strategist_agent import StrategistAgent
from .planner_agent import PlannerAgent

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationResult:
    """Result of a complete analysis run"""
    success: bool
    duration_seconds: float
    agents_completed: int
    agents_failed: int
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    insights: List[AgentInsight] = field(default_factory=list)


class AgentOrchestrator:
    """
    Orchestrates the execution of all Growth Engine agents.
    
    Execution order (respecting dependencies):
    1. Scout (no dependencies)
    2. Analyst (depends on Scout)
    3. Guardian + Prospector (parallel, depend on Analyst)
    4. Strategist (depends on Analyst, Guardian, Prospector)
    5. Planner (depends on Analyst, Strategist)
    """
    
    def __init__(self):
        # Initialize all agents
        self.agents = {
            'scout': ScoutAgent(),
            'analyst': AnalystAgent(),
            'guardian': GuardianAgent(),
            'prospector': ProspectorAgent(),
            'strategist': StrategistAgent(),
            'planner': PlannerAgent()
        }
        
        # Execution tiers (agents in same tier can run in parallel)
        self.execution_tiers = [
            ['scout'],                      # Tier 1: Discovery
            ['analyst'],                    # Tier 2: Analysis
            ['guardian', 'prospector'],     # Tier 3: Risk + Opportunities (parallel)
            ['strategist'],                 # Tier 4: Strategy
            ['planner']                     # Tier 5: Planning
        ]
        
        self._insights: List[AgentInsight] = []
        self._on_insight: Optional[Callable] = None
        self._on_progress: Optional[Callable] = None
        self._on_status: Optional[Callable] = None
    
    def set_callbacks(
        self,
        on_insight: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
        on_status: Optional[Callable] = None
    ):
        """Set callbacks for real-time updates"""
        self._on_insight = on_insight
        self._on_progress = on_progress
        self._on_status = on_status
    
    async def run_analysis(
        self,
        url: str,
        competitor_urls: Optional[List[str]] = None,
        industry: Optional[str] = None,
        country_code: str = "fi",
        user: Optional[Any] = None
    ) -> OrchestrationResult:
        """Run complete analysis with all agents"""
        
        start_time = datetime.now()
        self._insights = []
        
        # Create shared context
        context = AnalysisContext(
            url=url,
            competitor_urls=competitor_urls or [],
            industry=industry,
            country_code=country_code,
            user=user,
            agent_results={},
            on_insight=self._handle_insight,
            on_progress=self._handle_progress,
            on_status=self._handle_status
        )
        
        logger.info(f"[Orchestrator] Starting analysis for {url}")
        logger.info(f"[Orchestrator] Competitors: {len(competitor_urls or [])}")
        logger.info(f"[Orchestrator] Agents: {list(self.agents.keys())}")
        
        results = {}
        errors = []
        agents_completed = 0
        agents_failed = 0
        
        # Execute each tier
        for tier_idx, tier in enumerate(self.execution_tiers):
            logger.info(f"[Orchestrator] Executing Tier {tier_idx + 1}: {tier}")
            
            # Run agents in this tier (parallel if multiple)
            tier_tasks = []
            for agent_id in tier:
                agent = self.agents.get(agent_id)
                if agent:
                    tier_tasks.append(self._run_agent(agent, context))
            
            # Wait for all agents in tier to complete
            tier_results = await asyncio.gather(*tier_tasks, return_exceptions=True)
            
            # Process results
            for idx, result in enumerate(tier_results):
                agent_id = tier[idx]
                
                if isinstance(result, Exception):
                    logger.error(f"[Orchestrator] {agent_id} failed: {result}")
                    errors.append(f"{agent_id}: {str(result)}")
                    agents_failed += 1
                else:
                    # Store result for dependent agents
                    context.agent_results[agent_id] = result
                    results[agent_id] = result
                    agents_completed += 1
                    logger.info(f"[Orchestrator] {agent_id} completed")
        
        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()
        
        logger.info(
            f"[Orchestrator] Analysis complete in {duration:.1f}s "
            f"({agents_completed} succeeded, {agents_failed} failed)"
        )
        
        return OrchestrationResult(
            success=agents_failed == 0,
            duration_seconds=duration,
            agents_completed=agents_completed,
            agents_failed=agents_failed,
            results=results,
            errors=errors,
            insights=self._insights
        )
    
    async def _run_agent(self, agent, context: AnalysisContext) -> Dict[str, Any]:
        """Run a single agent with error handling"""
        try:
            return await agent.run(context)
        except Exception as e:
            logger.error(f"[Orchestrator] Agent {agent.agent_id} error: {e}", exc_info=True)
            raise
    
    def _handle_insight(self, insight: AgentInsight):
        """Handle insight from agent"""
        self._insights.append(insight)
        if self._on_insight:
            self._on_insight(insight)
    
    def _handle_progress(self, progress: AgentProgress):
        """Handle progress update from agent"""
        if self._on_progress:
            self._on_progress(progress)
    
    def _handle_status(self, agent_id: str, status: AgentStatus):
        """Handle status change from agent"""
        if self._on_status:
            self._on_status(agent_id, status)
    
    def get_agent_info(self) -> List[Dict[str, Any]]:
        """Get info about all agents"""
        return [agent.to_dict() for agent in self.agents.values()]
    
    def reset(self):
        """Reset all agents to idle state"""
        for agent in self.agents.values():
            agent._status = AgentStatus.IDLE
            agent._progress = 0
        self._insights = []
