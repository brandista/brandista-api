# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Orchestrator
TRUE SWARM EDITION - Clean, production-ready orchestration

Now with RunContext support for concurrent execution isolation.
Each analysis run gets its own isolated context.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from .agent_types import (
    AgentStatus,
    AgentInsight,
    AgentProgress,
    AgentResult,
    AnalysisContext,
    OrchestrationResult,
    SwarmEvent
)
from .base_agent import BaseAgent
from .scout_agent import ScoutAgent
from .analyst_agent import AnalystAgent
from .guardian_agent import GuardianAgent
from .prospector_agent import ProspectorAgent
from .strategist_agent import StrategistAgent
from .planner_agent import PlannerAgent

from .communication import get_message_bus, reset_message_bus
from .blackboard import get_blackboard, reset_blackboard
from .collaboration import reset_collaboration_manager
from .task_delegation import reset_task_manager

if TYPE_CHECKING:
    from .run_context import RunContext

logger = logging.getLogger(__name__)


class GrowthEngineOrchestrator:
    """
    TRUE SWARM Orchestrator with RunContext support.

    CONCURRENCY NOTE: This orchestrator is a singleton, but all run-specific
    state is stored in RunContext (passed to run_analysis). Instance variables
    like is_running, start_time, context are kept for backwards compatibility
    but should NOT be relied upon for concurrent runs.

    For true concurrent execution, each run_analysis call receives its own
    RunContext which isolates all per-run state.
    """

    EXECUTION_PLAN = [
        ['scout'],
        ['analyst'],
        ['guardian', 'prospector'],
        ['strategist'],
        ['planner']
    ]

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self._register_agents()

        # These are set per-call in run_analysis for backwards compatibility
        # but the actual isolation happens via RunContext
        self._on_insight = None
        self._on_progress = None
        self._on_agent_complete = None
        self._on_agent_start = None
        self._on_swarm_event = None

        logger.info("[Orchestrator] ✅ TRUE SWARM initialized")
    
    def _register_agents(self):
        for agent in [ScoutAgent(), AnalystAgent(), GuardianAgent(), 
                      ProspectorAgent(), StrategistAgent(), PlannerAgent()]:
            self.agents[agent.id] = agent
            logger.info(f"[Orchestrator] Registered: {agent.name}")
    
    def set_callbacks(self, on_insight=None, on_progress=None, 
                      on_agent_complete=None, on_agent_start=None, on_swarm_event=None):
        self._on_insight = on_insight
        self._on_progress = on_progress
        self._on_agent_complete = on_agent_complete
        self._on_agent_start = on_agent_start
        self._on_swarm_event = on_swarm_event
    
    async def run_analysis(
        self,
        url: str,
        competitor_urls: List[str] = None,
        language: str = "fi",
        industry_context: str = None,
        user_id: str = None,
        run_context: Optional['RunContext'] = None  # RunContext for isolation
    ) -> OrchestrationResult:
        """
        Run a full analysis.

        All run-specific state is stored locally or in RunContext.
        This method can run concurrently with different RunContexts.
        """
        # Local state for this run (NOT instance variables!)
        start_time = datetime.now()

        logger.info("=" * 60)
        logger.info("🚀 TRUE SWARM ANALYSIS STARTING")
        if run_context:
            logger.info(f"   Run ID: {run_context.run_id}")
            await run_context.start()  # Async for RunStore persistence
        logger.info("=" * 60)

        # Use RunContext systems if provided, else reset globals (backwards compatible)
        if run_context:
            message_bus = run_context.message_bus
            blackboard = run_context.blackboard
        else:
            # Legacy: reset globals
            reset_message_bus()
            reset_blackboard()
            reset_collaboration_manager()
            reset_task_manager()
            message_bus = get_message_bus()
            blackboard = get_blackboard()

        # Load unified context
        unified_context_data = None
        if user_id:
            try:
                from unified_context import get_unified_context
                unified_context_data = get_unified_context(user_id).to_dict()
            except Exception as e:
                logger.warning(f"[Orchestrator] Unified context error: {e}")

        # Create LOCAL context for this run (not self.context!)
        context = AnalysisContext(
            url=url, competitor_urls=competitor_urls or [], language=language,
            industry_context=industry_context, user_id=user_id,
            unified_context=unified_context_data,
            run_id=run_context.run_id if run_context else None
        )

        logger.info(f"[Orchestrator] 🎯 Target: {url}")

        errors = []

        try:
            # Set callbacks and RunContext for each agent
            for agent in self.agents.values():
                agent.set_callbacks(
                    on_insight=self._on_insight,
                    on_progress=self._on_progress,
                    on_swarm_event=self._on_swarm_event
                )
                # Inject RunContext if provided
                if run_context:
                    agent.set_run_context(run_context)

            # Execute phases
            for phase_idx, phase_agents in enumerate(self.EXECUTION_PLAN, 1):
                # Check for cancellation before each phase
                if run_context and await run_context.check_cancelled():
                    logger.info(f"[Orchestrator] Run cancelled before phase {phase_idx}")
                    errors.append("Run cancelled by user")
                    break

                logger.info(f"[Orchestrator] === PHASE {phase_idx}: {phase_agents} ===")

                self._check_dependencies(phase_agents, context)

                if len(phase_agents) > 1:
                    results = await self._run_parallel(phase_agents, context, run_context)
                else:
                    results = [await self._run_agent(phase_agents[0], context, run_context)]

                for result in results:
                    if result:
                        context.agent_results[result.agent_id] = result
                        if self._on_agent_complete:
                            self._on_agent_complete(result.agent_id, result)
                        if result.status == AgentStatus.ERROR:
                            errors.append(f"{result.agent_name}: {result.error}")

        except Exception as e:
            logger.error(f"[Orchestrator] Fatal error: {e}", exc_info=True)
            errors.append(str(e))

        finally:
            # Mark RunContext as complete (async for RunStore persistence)
            if run_context:
                await run_context.complete(
                    success=len(errors) == 0,
                    error=errors[0] if errors else None
                )

        duration = (datetime.now() - start_time).total_seconds()

        swarm_summary = {
            'total_messages': message_bus.get_stats()['total_sent'],
            'blackboard_entries': len(blackboard.get_all_keys()),
            'run_id': run_context.run_id if run_context else None  # NEW: include run_id
        }

        logger.info(f"📊 Swarm: {swarm_summary['total_messages']} messages, {swarm_summary['blackboard_entries']} blackboard entries")

        return self._build_result(context, int(duration * 1000), duration, errors, swarm_summary, run_context)
    
    async def _run_agent(
        self,
        agent_id: str,
        context: AnalysisContext,
        run_context: Optional['RunContext'] = None
    ) -> Optional[AgentResult]:
        """Run a single agent with proper isolation."""
        agent = self.agents.get(agent_id)
        if not agent:
            return None

        # Check for cancellation before starting agent
        if run_context and await run_context.check_cancelled():
            logger.info(f"[Orchestrator] ⏹️ {agent.name} skipped (run cancelled)")
            return AgentResult(agent_id=agent_id, agent_name=agent.name,
                              status=AgentStatus.ERROR, execution_time_ms=0,
                              error="Run cancelled")

        logger.info(f"[Orchestrator] ▶️ {agent.name}")
        if self._on_agent_start:
            self._on_agent_start(agent_id, agent.name)

        # Get per-agent timeout from RunContext or use default
        timeout = 90.0  # Default fallback
        if run_context and run_context.limits:
            timeout = run_context.limits.get_agent_timeout(agent_id)
            logger.debug(f"[Orchestrator] Agent {agent_id} timeout: {timeout}s")

        try:
            result = await asyncio.wait_for(
                agent.run(context),
                timeout=timeout
            )
            logger.info(f"[Orchestrator] ✅ {agent.name}: {result.status.value}")
            return result
        except asyncio.TimeoutError:
            error_msg = f"Agent timeout after {timeout}s"
            logger.error(f"[Orchestrator] ⏱️ {agent_id}: {error_msg}")
            return AgentResult(agent_id=agent_id, agent_name=agent.name,
                              status=AgentStatus.ERROR, execution_time_ms=int(timeout * 1000),
                              error=error_msg)
        except asyncio.CancelledError:
            logger.info(f"[Orchestrator] ⏹️ {agent_id} cancelled")
            return AgentResult(agent_id=agent_id, agent_name=agent.name,
                              status=AgentStatus.ERROR, execution_time_ms=0,
                              error="Run cancelled")
        except Exception as e:
            logger.error(f"[Orchestrator] ❌ {agent_id}: {e}")
            return AgentResult(agent_id=agent_id, agent_name=agent.name,
                              status=AgentStatus.ERROR, execution_time_ms=0, error=str(e))

    async def _run_parallel(
        self,
        agent_ids: List[str],
        context: AnalysisContext,
        run_context: Optional['RunContext'] = None
    ) -> List[AgentResult]:
        """Run multiple agents in parallel."""
        logger.info(f"[Orchestrator] ⚡ Parallel: {agent_ids}")
        tasks = [self._run_agent(aid, context, run_context) for aid in agent_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                processed.append(AgentResult(
                    agent_id=agent_ids[idx], agent_name=agent_ids[idx],
                    status=AgentStatus.ERROR, execution_time_ms=0, error=str(result)
                ))
            elif result:
                processed.append(result)
        return processed

    def _check_dependencies(self, agent_ids: List[str], context: AnalysisContext) -> bool:
        """Check that all dependencies are met."""
        for agent_id in agent_ids:
            agent = self.agents.get(agent_id)
            if not agent:
                continue
            for dep_id in agent.dependencies:
                if dep_id not in context.agent_results:
                    logger.warning(f"[Orchestrator] Missing dep {dep_id} for {agent_id}")
        return True
    
    def _build_result(
        self,
        context: AnalysisContext,
        exec_ms: int,
        duration: float,
        errors: List[str],
        swarm: Dict,
        run_context: Optional['RunContext'] = None
    ) -> OrchestrationResult:
        """Build final result from local context (not self.context)."""
        all_insights = []
        for r in context.agent_results.values():
            all_insights.extend(r.insights)

        critical = [i for i in all_insights if i.priority.value == 1]
        high = [i for i in all_insights if i.priority.value == 2]

        strategist = context.agent_results.get('strategist')
        overall_score = strategist.data.get('overall_score', 50) if strategist else 50
        composite = strategist.data.get('composite_scores', {}) if strategist else {}

        planner = context.agent_results.get('planner')
        action_plan = planner.data if planner else None

        logger.info(f"✅ Complete in {duration:.2f}s, Score: {overall_score}/100")

        return OrchestrationResult(
            success=len(errors) == 0,
            execution_time_ms=exec_ms,
            duration_seconds=duration,
            url=context.url,
            competitor_count=len(context.competitor_urls),
            overall_score=overall_score,
            composite_scores=composite,
            agent_results=dict(context.agent_results),
            context=context,
            critical_insights=critical,
            high_insights=high,
            action_plan=action_plan,
            errors=errors,
            swarm_summary=swarm,
            run_id=run_context.run_id if run_context else None
        )
    
    def get_agent_info(self) -> List[Dict[str, Any]]:
        return [a.to_info_dict() for a in self.agents.values()]
    
    def get_execution_plan(self) -> List[List[str]]:
        return self.EXECUTION_PLAN


_orchestrator = None

def get_orchestrator() -> GrowthEngineOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = GrowthEngineOrchestrator()
    return _orchestrator

def reset_orchestrator():
    global _orchestrator
    _orchestrator = None
