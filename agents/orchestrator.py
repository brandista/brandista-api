"""
Growth Engine 2.0 - Orchestrator
Koordinoi agenttien suoritusta ja hallitsee tiedonkulkua
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

from .types import (
    AgentStatus,
    AgentInsight,
    AgentProgress,
    AgentResult,
    AnalysisContext,
    OrchestrationResult,
    WSMessage,
    WSMessageType
)
from .base_agent import BaseAgent
from .scout_agent import ScoutAgent
from .analyst_agent import AnalystAgent
from .guardian_agent import GuardianAgent
from .prospector_agent import ProspectorAgent
from .strategist_agent import StrategistAgent
from .planner_agent import PlannerAgent

logger = logging.getLogger(__name__)


class GrowthEngineOrchestrator:
    """
    Growth Engine Orchestrator
    
    Koordinoi 6 agentin suoritusta:
    1. Scout → 2. Analyst → 3. Guardian + Prospector (rinnakkain) → 4. Strategist → 5. Planner
    
    Hoitaa:
    - Riippuvuuksien hallinnan
    - Rinnakkaisen suorituksen (tier 3)
    - Real-time päivitykset WebSocketiin
    - Virheenkäsittelyn ja graceful degradation
    """
    
    # Suoritusjärjestys (tierit)
    EXECUTION_PLAN = [
        ['scout'],                      # Tier 1: Kilpailijoiden haku
        ['analyst'],                    # Tier 2: Syvällinen analyysi
        ['guardian', 'prospector'],     # Tier 3: Uhkat + Mahdollisuudet (RINNAKKAIN)
        ['strategist'],                 # Tier 4: Synteesi
        ['planner']                     # Tier 5: 90-päivän suunnitelma
    ]
    
    def __init__(self):
        """Alusta orchestrator ja rekisteröi agentit"""
        
        self.agents: Dict[str, BaseAgent] = {}
        self._register_agents()
        
        # Callbacks
        self._on_insight: Optional[Callable] = None
        self._on_progress: Optional[Callable] = None
        self._on_agent_complete: Optional[Callable] = None
        self._on_agent_start: Optional[Callable] = None  # NEW: Notify when agent starts
        
        # State
        self.is_running = False
        self.start_time: Optional[datetime] = None
        self.context: Optional[AnalysisContext] = None
    
    def _register_agents(self):
        """Rekisteröi kaikki agentit"""
        
        agents = [
            ScoutAgent(),
            AnalystAgent(),
            GuardianAgent(),
            ProspectorAgent(),
            StrategistAgent(),
            PlannerAgent()
        ]
        
        for agent in agents:
            self.agents[agent.id] = agent
            logger.info(f"[Orchestrator] Registered agent: {agent.name} ({agent.id})")
    
    def set_callbacks(
        self,
        on_insight: Optional[Callable[[AgentInsight], None]] = None,
        on_progress: Optional[Callable[[AgentProgress], None]] = None,
        on_agent_complete: Optional[Callable[[str, AgentResult], None]] = None,
        on_agent_start: Optional[Callable[[str, str], None]] = None  # NEW: (agent_id, agent_name)
    ):
        """
        Aseta callbackit real-time päivityksille.
        Nämä välitetään agenteille.
        """
        self._on_insight = on_insight
        self._on_progress = on_progress
        self._on_agent_complete = on_agent_complete
        self._on_agent_start = on_agent_start  # NEW
        
        # Välitä agenteille
        for agent in self.agents.values():
            agent.set_callbacks(
                on_insight=self._handle_insight,
                on_progress=self._handle_progress
            )
    
    def _handle_insight(self, insight: AgentInsight):
        """Käsittele agentti-insight"""
        if self._on_insight:
            try:
                self._on_insight(insight)
            except Exception as e:
                logger.error(f"[Orchestrator] Insight callback error: {e}")
    
    def _handle_progress(self, progress: AgentProgress):
        """Käsittele edistymispäivitys"""
        if self._on_progress:
            try:
                self._on_progress(progress)
            except Exception as e:
                logger.error(f"[Orchestrator] Progress callback error: {e}")
    
    async def run_analysis(
        self,
        url: str,
        competitor_urls: List[str] = None,
        language: str = "fi",
        industry_context: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> OrchestrationResult:
        """
        Suorita täysi agentti-analyysi.
        
        Args:
            url: Analysoitava URL
            competitor_urls: Lista kilpailijoiden URL:ista (valinnainen)
            language: Kieli ('fi' tai 'en')
            industry_context: Toimiala-konteksti (valinnainen)
            user_id: Käyttäjä-ID unified contextin hakuun
            
        Returns:
            OrchestrationResult sisältäen kaikkien agenttien tulokset
        """
        
        self.is_running = True
        self.start_time = datetime.now()
        
        # Hae unified context jos user_id annettu
        unified_context_data = None
        if user_id:
            try:
                from unified_context import get_unified_context
                unified_ctx = get_unified_context(user_id)
                unified_context_data = unified_ctx.to_dict()
                logger.info(f"[Orchestrator] Loaded unified context for {user_id}: "
                           f"{len(unified_ctx.recent_analyses)} analyses, "
                           f"{len(unified_ctx.tracked_competitors)} tracked")
            except Exception as e:
                logger.warning(f"[Orchestrator] Could not load unified context: {e}")
        
        # Luo konteksti
        self.context = AnalysisContext(
            url=url,
            competitor_urls=competitor_urls or [],
            language=language,
            industry_context=industry_context,
            user_id=user_id,
            unified_context=unified_context_data
        )
        
        logger.info(f"[Orchestrator] Starting analysis for {url}")
        logger.info(f"[Orchestrator] Competitors: {competitor_urls}")
        logger.info(f"[Orchestrator] Language: {language}")
        
        errors = []
        
        try:
            # Suorita tierit järjestyksessä
            for tier_idx, tier_agents in enumerate(self.EXECUTION_PLAN, 1):
                logger.info(f"[Orchestrator] === TIER {tier_idx}: {tier_agents} ===")
                
                # Tarkista riippuvuudet
                if not self._check_dependencies(tier_agents):
                    error_msg = f"Dependencies not met for tier {tier_idx}"
                    logger.error(f"[Orchestrator] {error_msg}")
                    errors.append(error_msg)
                    continue
                
                # Suorita agentit (rinnakkain jos useampi)
                if len(tier_agents) > 1:
                    # Rinnakkainen suoritus
                    results = await self._run_parallel(tier_agents)
                else:
                    # Yksittäinen agentti
                    results = [await self._run_agent(tier_agents[0])]
                
                # Tallenna tulokset kontekstiin
                for result in results:
                    if result:
                        self.context.agent_results[result.agent_id] = result
                        
                        if self._on_agent_complete:
                            self._on_agent_complete(result.agent_id, result)
                        
                        if result.status == AgentStatus.ERROR:
                            errors.append(f"{result.agent_name}: {result.error}")
                
                logger.info(f"[Orchestrator] Tier {tier_idx} complete")
        
        except Exception as e:
            logger.error(f"[Orchestrator] Fatal error: {e}", exc_info=True)
            errors.append(f"Orchestration error: {str(e)}")
        
        finally:
            self.is_running = False
        
        # Koosta lopputulos
        end_time = datetime.now()
        execution_time = int((end_time - self.start_time).total_seconds() * 1000)
        
        return self._build_result(execution_time, errors)
    
    async def _run_agent(self, agent_id: str) -> Optional[AgentResult]:
        """Suorita yksittäinen agentti"""
        
        agent = self.agents.get(agent_id)
        if not agent:
            logger.error(f"[Orchestrator] Agent not found: {agent_id}")
            return None
        
        logger.info(f"[Orchestrator] Running agent: {agent.name}")
        
        # NEW: Notify that agent is starting
        if self._on_agent_start:
            try:
                self._on_agent_start(agent_id, agent.name)
            except Exception as e:
                logger.error(f"[Orchestrator] on_agent_start callback error: {e}")
        
        try:
            result = await agent.run(self.context)
            logger.info(f"[Orchestrator] Agent {agent.name} completed: {result.status}")
            return result
            
        except Exception as e:
            logger.error(f"[Orchestrator] Agent {agent_id} failed: {e}", exc_info=True)
            return AgentResult(
                agent_id=agent_id,
                agent_name=agent.name,
                status=AgentStatus.ERROR,
                execution_time_ms=0,
                error=str(e)
            )
    
    async def _run_parallel(self, agent_ids: List[str]) -> List[AgentResult]:
        """Suorita useampi agentti rinnakkain"""
        
        logger.info(f"[Orchestrator] Running parallel: {agent_ids}")
        
        tasks = [self._run_agent(agent_id) for agent_id in agent_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Käsittele poikkeukset
        processed = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                agent_id = agent_ids[idx]
                agent = self.agents.get(agent_id)
                processed.append(AgentResult(
                    agent_id=agent_id,
                    agent_name=agent.name if agent else agent_id,
                    status=AgentStatus.ERROR,
                    execution_time_ms=0,
                    error=str(result)
                ))
            elif result:
                processed.append(result)
        
        return processed
    
    def _check_dependencies(self, agent_ids: List[str]) -> bool:
        """Tarkista onko riippuvuudet täytetty"""
        
        for agent_id in agent_ids:
            agent = self.agents.get(agent_id)
            if not agent:
                continue
            
            for dep_id in agent.dependencies:
                if dep_id not in self.context.agent_results:
                    logger.warning(f"[Orchestrator] Dependency {dep_id} not met for {agent_id}")
                    return False
                
                dep_result = self.context.agent_results[dep_id]
                if dep_result.status == AgentStatus.ERROR:
                    logger.warning(f"[Orchestrator] Dependency {dep_id} failed for {agent_id}")
                    # Salli silti jatkaminen (graceful degradation)
        
        return True
    
    def _build_result(
        self,
        execution_time: int,
        errors: List[str]
    ) -> OrchestrationResult:
        """Rakenna lopputulos"""
        
        # Kerää kaikki insightit
        all_insights = []
        for result in self.context.agent_results.values():
            all_insights.extend(result.insights)
        
        # Järjestä prioriteetin mukaan
        critical = [i for i in all_insights if i.priority.value == 1]
        high = [i for i in all_insights if i.priority.value == 2]
        
        # Hae kokonaispistemäärä strategistilta
        strategist_result = self.context.agent_results.get('strategist')
        overall_score = 50
        composite_scores = {}
        
        if strategist_result and strategist_result.data:
            overall_score = strategist_result.data.get('overall_score', 50)
            composite_scores = strategist_result.data.get('composite_scores', {})
        
        # Hae toimintasuunnitelma plannerilta
        planner_result = self.context.agent_results.get('planner')
        action_plan = None
        if planner_result and planner_result.data:
            action_plan = planner_result.data
        
        # Laske onnistuminen
        success = len(errors) == 0 and overall_score > 0
        
        return OrchestrationResult(
            success=success,
            execution_time_ms=execution_time,
            url=self.context.url,
            competitor_count=len(self.context.competitor_urls),
            overall_score=overall_score,
            composite_scores=composite_scores,
            agent_results={k: v for k, v in self.context.agent_results.items()},
            critical_insights=critical,
            high_insights=high,
            action_plan=action_plan,
            errors=errors
        )
    
    def get_agent_info(self) -> List[Dict[str, Any]]:
        """Palauta kaikkien agenttien info frontendille"""
        return [agent.to_info_dict() for agent in self.agents.values()]
    
    def get_execution_plan(self) -> List[List[str]]:
        """Palauta suoritusjärjestys"""
        return self.EXECUTION_PLAN


# Singleton instance
_orchestrator: Optional[GrowthEngineOrchestrator] = None


def get_orchestrator() -> GrowthEngineOrchestrator:
    """Hae tai luo orchestrator-instanssi"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = GrowthEngineOrchestrator()
    return _orchestrator
