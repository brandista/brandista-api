"""
Growth Engine 2.0 - Base Agent
Pohjaluokka kaikille agenteille
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable

from .types import (
    AgentStatus,
    AgentPriority,
    InsightType,
    AgentInsight,
    AgentProgress,
    AgentResult,
    AnalysisContext
)
from .translations import t as translate

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Pohjaluokka Growth Engine -agenteille.
    
    Jokainen agentti:
    - Suorittaa yhden erikoistuneen tehtävän
    - Emittoi real-time insighteja frontendiin
    - Raportoi edistymisensä
    - Voi riippua muista agenteista
    """
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        avatar: str = "🤖",
        personality: str = ""
    ):
        self.id = agent_id
        self.name = name
        self.role = role
        self.avatar = avatar
        self.personality = personality
        
        # State
        self.status = AgentStatus.IDLE
        self.progress = 0
        self.current_task: Optional[str] = None
        self.insights: List[AgentInsight] = []
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
        # Language (set from context in run())
        self._language: str = "fi"
        
        # Dependencies - mitkä agentit pitää ajaa ensin
        self.dependencies: List[str] = []
        
        # Callbacks for real-time updates
        self._on_insight: Optional[Callable[[AgentInsight], None]] = None
        self._on_progress: Optional[Callable[[AgentProgress], None]] = None
    
    def _t(self, key: str, **kwargs) -> str:
        """
        Käännä teksti nykyiselle kielelle.
        
        Esimerkki:
            self._t("scout.found_competitors", count=5, top="Example.com")
        """
        return translate(key, self._language, **kwargs)
    
    def set_callbacks(
        self,
        on_insight: Optional[Callable[[AgentInsight], None]] = None,
        on_progress: Optional[Callable[[AgentProgress], None]] = None
    ):
        """Aseta callbackit real-time päivityksille"""
        self._on_insight = on_insight
        self._on_progress = on_progress
    
    def _emit_insight(
        self,
        message: str,
        priority: AgentPriority = AgentPriority.MEDIUM,
        insight_type: InsightType = InsightType.FINDING,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Emitoi insight frontendiin real-time.
        
        Esimerkki:
            self._emit_insight(
                "Löysin 3 vahvaa kilpailijaa!",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING
            )
        """
        insight = AgentInsight(
            agent_id=self.id,
            agent_name=self.name,
            agent_avatar=self.avatar,
            message=message,
            priority=priority,
            insight_type=insight_type,
            data=data
        )
        
        self.insights.append(insight)
        
        if self._on_insight:
            try:
                self._on_insight(insight)
            except Exception as e:
                logger.error(f"[{self.name}] Insight callback error: {e}")
        
        logger.info(f"[{self.name}] 💡 {message}")
    
    def _update_progress(
        self,
        progress: int,
        task: Optional[str] = None
    ):
        """
        Päivitä edistyminen.
        
        Esimerkki:
            self._update_progress(50, "Analysoimassa kilpailijoita...")
        """
        self.progress = min(100, max(0, progress))
        if task:
            self.current_task = task
        
        progress_update = AgentProgress(
            agent_id=self.id,
            status=self.status,
            progress=self.progress,
            current_task=self.current_task
        )
        
        if self._on_progress:
            try:
                self._on_progress(progress_update)
            except Exception as e:
                logger.error(f"[{self.name}] Progress callback error: {e}")
    
    def _set_status(self, status: AgentStatus):
        """Päivitä tila"""
        self.status = status
        self._update_progress(self.progress)
    
    async def run(self, context: AnalysisContext) -> AgentResult:
        """
        Suorita agentti. Tätä kutsuu orchestrator.
        
        Hoitaa:
        - Pre/post executionin
        - Virheenkäsittelyn
        - Ajanoton
        """
        self.start_time = datetime.now()
        self.insights = []
        self.error = None
        self.result = None
        
        # Set language from context
        self._language = context.language or "fi"
        
        try:
            # Pre-execute
            self._set_status(AgentStatus.THINKING)
            self._update_progress(5, self._t("common.preparing"))
            await self.pre_execute(context)
            
            # Main execution
            self._set_status(AgentStatus.RUNNING)
            self._update_progress(10, self._t("common.executing"))
            
            result_data = await self.execute(context)
            
            # Post-execute
            self._update_progress(95, self._t("common.finalizing"))
            await self.post_execute(result_data)
            
            self.result = result_data
            self._set_status(AgentStatus.COMPLETE)
            self._update_progress(100, "Valmis!")
            
        except Exception as e:
            self.error = str(e)
            self._set_status(AgentStatus.ERROR)
            logger.error(f"[{self.name}] ❌ Error: {e}", exc_info=True)
            
            self._emit_insight(
                f"Virhe: {str(e)[:100]}",
                priority=AgentPriority.CRITICAL,
                insight_type=InsightType.FINDING
            )
        
        self.end_time = datetime.now()
        execution_time = int((self.end_time - self.start_time).total_seconds() * 1000)
        
        return AgentResult(
            agent_id=self.id,
            agent_name=self.name,
            status=self.status,
            execution_time_ms=execution_time,
            insights=self.insights,
            data=self.result or {},
            error=self.error
        )
    
    async def pre_execute(self, context: AnalysisContext):
        """
        Setup ennen suoritusta.
        Override tarvittaessa.
        """
        pass
    
    @abstractmethod
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """
        Päälogiikka - jokainen agentti toteuttaa tämän.
        
        Args:
            context: Jaettu konteksti sisältäen URL:t ja muiden agenttien tulokset
            
        Returns:
            Dict sisältäen agentin tulokset
        """
        raise NotImplementedError
    
    async def post_execute(self, result: Dict[str, Any]):
        """
        Cleanup suorituksen jälkeen.
        Override tarvittaessa.
        """
        pass
    
    def get_dependency_results(
        self,
        context: AnalysisContext,
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Hae riippuvuusagenttien tulokset.
        
        Args:
            context: Analyysikonteksti
            agent_id: Jos annettu, palauta vain tämän agentin tulokset
        
        Esimerkki:
            # Hae kaikki riippuvuudet
            deps = self.get_dependency_results(context)
            scout_data = deps.get('scout', {})
            
            # Hae yhden agentin tulokset
            analyst_data = self.get_dependency_results(context, 'analyst')
        """
        if agent_id:
            # Palauta vain yhden agentin tulokset
            if agent_id in context.agent_results:
                return context.agent_results[agent_id].data
            return {}
        
        # Palauta kaikki riippuvuudet
        results = {}
        for dep_id in self.dependencies:
            if dep_id in context.agent_results:
                results[dep_id] = context.agent_results[dep_id].data
        return results
    
    def get_unified_context_data(
        self,
        context: AnalysisContext,
        key: Optional[str] = None
    ) -> Any:
        """
        🧠 Hae unified context dataa (muisti aiemmista analyyseistä).
        
        Args:
            context: Analyysikonteksti
            key: Jos annettu, palauta vain tämä avain
        
        Returns:
            Unified context data tai None jos ei saatavilla
        
        Esimerkki:
            # Hae kaikki
            uc = self.get_unified_context_data(context)
            
            # Hae tracked competitors
            tracked = self.get_unified_context_data(context, 'tracked_competitors')
            
            # Hae score history
            analyses = self.get_unified_context_data(context, 'recent_analyses')
        """
        if not context.unified_context:
            return None if key else {}
        
        if key:
            return context.unified_context.get(key)
        
        return context.unified_context
    
    def to_info_dict(self) -> Dict[str, Any]:
        """Palauta agentin info frontendille"""
        return {
            'id': self.id,
            'name': self.name,
            'role': self.role,
            'avatar': self.avatar,
            'personality': self.personality,
            'dependencies': self.dependencies,
            'status': self.status.value,
            'progress': self.progress
        }
