# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Parallel Orchestrator
TRUE SWARM AGENTS - Parallel execution engine

This enables:
- Parallel execution of independent agents (3x faster)
- Intelligent dependency resolution
- Dynamic phase planning
- Resource optimization

BEFORE: 90 seconds (serial 1→2→3→4→5→6)
AFTER:  30 seconds (parallel phases)

Think of this as a smart project manager that knows
which tasks can run in parallel vs. which need to wait.
"""

import asyncio
import logging
from typing import Dict, Any, List, Set, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict

from .types import AnalysisContext, AgentResult
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPhase:
    """
    A phase of parallel execution.
    
    Agents in the same phase run in parallel.
    Each phase waits for previous phase to complete.
    """
    phase_number: int
    agents: List[str]
    dependencies_met: Set[str] = field(default_factory=set)
    estimated_duration: float = 10.0
    
    def __repr__(self):
        return f"Phase {self.phase_number}: {self.agents}"


class DependencyGraph:
    """
    Dependency graph for agents.
    
    Analyzes agent dependencies and builds execution phases.
    """
    
    def __init__(self, agents: Dict[str, BaseAgent]):
        """
        Initialize dependency graph.
        
        Args:
            agents: Dictionary of agent_id -> BaseAgent
        """
        self.agents = agents
        self.dependencies: Dict[str, Set[str]] = {}
        self.dependents: Dict[str, Set[str]] = defaultdict(set)
        
        # Build dependency graph
        self._build_graph()
    
    def _build_graph(self):
        """Build dependency graph from agent dependencies"""
        for agent_id, agent in self.agents.items():
            self.dependencies[agent_id] = set(agent.dependencies)
            
            # Track reverse dependencies
            for dep in agent.dependencies:
                self.dependents[dep].add(agent_id)
        
        logger.info("[DependencyGraph] 📊 Graph built:")
        for agent_id, deps in self.dependencies.items():
            if deps:
                logger.info(f"  {agent_id} depends on: {deps}")
    
    def get_phases(self) -> List[ExecutionPhase]:
        """
        Calculate execution phases.
        
        Agents with no dependencies run in phase 0.
        Agents that depend only on phase 0 run in phase 1.
        And so on.
        
        Returns:
            List of ExecutionPhase objects
        """
        phases: List[ExecutionPhase] = []
        assigned: Set[str] = set()
        phase_number = 0
        
        while len(assigned) < len(self.agents):
            # Find agents that can run in this phase
            phase_agents = []
            
            for agent_id, deps in self.dependencies.items():
                if agent_id in assigned:
                    continue
                
                # Check if all dependencies are met
                if deps.issubset(assigned):
                    phase_agents.append(agent_id)
            
            if not phase_agents:
                # Circular dependency or error
                remaining = set(self.agents.keys()) - assigned
                logger.error(
                    f"[DependencyGraph] ❌ Cannot resolve dependencies for: {remaining}"
                )
                # Add them to final phase anyway
                phase_agents = list(remaining)
            
            # Create phase
            phase = ExecutionPhase(
                phase_number=phase_number,
                agents=phase_agents,
                dependencies_met=assigned.copy()
            )
            phases.append(phase)
            
            # Mark as assigned
            assigned.update(phase_agents)
            phase_number += 1
        
        logger.info(f"[DependencyGraph] 🎯 Created {len(phases)} execution phases:")
        for phase in phases:
            logger.info(f"  Phase {phase.phase_number}: {phase.agents}")
        
        return phases
    
    def get_independent_agents(self) -> List[str]:
        """Get agents with no dependencies (can run first)"""
        return [
            agent_id for agent_id, deps in self.dependencies.items()
            if not deps
        ]
    
    def get_critical_path(self) -> List[str]:
        """
        Get critical path (longest dependency chain).
        
        This is the minimum execution time.
        """
        def get_depth(agent_id: str, memo: Dict[str, int]) -> int:
            if agent_id in memo:
                return memo[agent_id]
            
            deps = self.dependencies.get(agent_id, set())
            if not deps:
                memo[agent_id] = 0
                return 0
            
            max_depth = max(get_depth(dep, memo) for dep in deps)
            memo[agent_id] = max_depth + 1
            return max_depth + 1
        
        memo: Dict[str, int] = {}
        depths = {
            agent_id: get_depth(agent_id, memo)
            for agent_id in self.agents.keys()
        }
        
        # Find longest path
        critical_agent = max(depths.items(), key=lambda x: x[1])[0]
        
        # Trace back
        path = [critical_agent]
        current = critical_agent
        
        while self.dependencies.get(current):
            deps = self.dependencies[current]
            # Pick dependency with highest depth
            next_agent = max(
                deps,
                key=lambda a: depths.get(a, 0)
            )
            path.append(next_agent)
            current = next_agent
        
        path.reverse()
        return path


class ParallelOrchestrator:
    """
    Parallel execution orchestrator.
    
    This is the smart scheduler that runs agents in parallel
    while respecting dependencies.
    
    PERFORMANCE IMPROVEMENT:
    - Serial: agent1(15s) → agent2(15s) → ... = 90s
    - Parallel: [agent1, agent2](15s) → [agent3, agent4](15s) → ... = 30s
    """
    
    def __init__(self, agents: Dict[str, BaseAgent]):
        """
        Initialize parallel orchestrator.
        
        Args:
            agents: Dictionary of agent_id -> BaseAgent
        """
        self.agents = agents
        self.dependency_graph = DependencyGraph(agents)
        self.execution_phases = self.dependency_graph.get_phases()
        
        # Statistics
        self.stats = {
            'total_phases': len(self.execution_phases),
            'agents_per_phase': [len(p.agents) for p in self.execution_phases],
            'critical_path': self.dependency_graph.get_critical_path(),
            'max_parallelism': max(
                len(p.agents) for p in self.execution_phases
            )
        }
        
        logger.info(
            f"[ParallelOrchestrator] 🚀 Initialized with {len(self.execution_phases)} phases"
        )
        logger.info(
            f"[ParallelOrchestrator] ⚡ Max parallelism: {self.stats['max_parallelism']} agents"
        )
        logger.info(
            f"[ParallelOrchestrator] 📏 Critical path: {' → '.join(self.stats['critical_path'])}"
        )
    
    async def execute(
        self,
        context: AnalysisContext,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, AgentResult]:
        """
        Execute all agents in parallel phases.
        
        Args:
            context: Analysis context
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary of agent_id -> AgentResult
        """
        start_time = datetime.now()
        results: Dict[str, AgentResult] = {}
        
        total_agents = len(self.agents)
        completed_agents = 0
        
        logger.info(
            f"[ParallelOrchestrator] 🎬 Starting parallel execution "
            f"({len(self.execution_phases)} phases, {total_agents} agents)"
        )
        
        # Execute each phase
        for phase in self.execution_phases:
            phase_start = datetime.now()
            
            logger.info(
                f"[ParallelOrchestrator] 📍 Phase {phase.phase_number}: "
                f"Running {len(phase.agents)} agents in parallel"
            )
            
            # Store results in context for dependencies
            context.agent_results = results
            
            # Run agents in parallel
            phase_tasks = []
            for agent_id in phase.agents:
                agent = self.agents[agent_id]
                
                # Initialize swarm capabilities
                agent._init_swarm()
                
                # Create async task
                task = asyncio.create_task(
                    agent.run(context),
                    name=f"agent_{agent_id}"
                )
                phase_tasks.append((agent_id, task))
            
            # Wait for all agents in phase to complete
            for agent_id, task in phase_tasks:
                try:
                    result = await task
                    results[agent_id] = result
                    completed_agents += 1
                    
                    # Progress callback
                    if progress_callback:
                        progress = int((completed_agents / total_agents) * 100)
                        progress_callback(progress, agent_id, result)
                    
                    logger.info(
                        f"[ParallelOrchestrator] ✅ {agent_id} completed "
                        f"({result.execution_time_ms}ms)"
                    )
                    
                except Exception as e:
                    logger.error(
                        f"[ParallelOrchestrator] ❌ {agent_id} failed: {e}",
                        exc_info=True
                    )
                    # Create error result
                    results[agent_id] = AgentResult(
                        agent_id=agent_id,
                        agent_name=self.agents[agent_id].name,
                        status='error',
                        execution_time_ms=0,
                        insights=[],
                        data={},
                        error=str(e)
                    )
            
            phase_duration = (datetime.now() - phase_start).total_seconds()
            logger.info(
                f"[ParallelOrchestrator] ⏱️ Phase {phase.phase_number} "
                f"completed in {phase_duration:.2f}s"
            )
        
        total_duration = (datetime.now() - start_time).total_seconds()
        
        logger.info(
            f"[ParallelOrchestrator] 🏁 All agents completed in {total_duration:.2f}s"
        )
        logger.info(
            f"[ParallelOrchestrator] 📊 Performance: "
            f"{len(self.execution_phases)} phases, "
            f"avg {total_duration/len(self.execution_phases):.2f}s per phase"
        )
        
        # Calculate speedup vs serial
        estimated_serial_time = sum(
            r.execution_time_ms for r in results.values()
        ) / 1000.0
        speedup = estimated_serial_time / total_duration if total_duration > 0 else 1.0
        
        logger.info(
            f"[ParallelOrchestrator] 🚀 Speedup: {speedup:.2f}x "
            f"(estimated serial: {estimated_serial_time:.2f}s)"
        )
        
        return results
    
    def get_execution_plan(self) -> Dict[str, Any]:
        """
        Get execution plan summary.
        
        Returns:
            Dictionary with execution plan details
        """
        return {
            'total_phases': len(self.execution_phases),
            'phases': [
                {
                    'phase': p.phase_number,
                    'agents': p.agents,
                    'parallelism': len(p.agents)
                }
                for p in self.execution_phases
            ],
            'critical_path': self.stats['critical_path'],
            'max_parallelism': self.stats['max_parallelism'],
            'estimated_speedup': self._estimate_speedup()
        }
    
    def _estimate_speedup(self) -> float:
        """
        Estimate speedup vs. serial execution.
        
        Assumes each agent takes ~15 seconds.
        """
        avg_agent_time = 15.0  # seconds
        
        # Serial time
        serial_time = len(self.agents) * avg_agent_time
        
        # Parallel time = number of phases * avg time
        parallel_time = len(self.execution_phases) * avg_agent_time
        
        speedup = serial_time / parallel_time if parallel_time > 0 else 1.0
        return round(speedup, 2)
    
    def visualize_execution_plan(self) -> str:
        """
        Create ASCII visualization of execution plan.
        
        Returns:
            String with visual representation
        """
        lines = []
        lines.append("=" * 60)
        lines.append("PARALLEL EXECUTION PLAN")
        lines.append("=" * 60)
        
        for phase in self.execution_phases:
            lines.append(f"\nPhase {phase.phase_number}:")
            lines.append("┌" + "─" * 58 + "┐")
            
            for agent_id in phase.agents:
                agent = self.agents[agent_id]
                deps = ", ".join(agent.dependencies) if agent.dependencies else "None"
                lines.append(f"│ {agent.name:20s} (depends on: {deps:30s}) │")
            
            lines.append("└" + "─" * 58 + "┘")
            
            if phase.phase_number < len(self.execution_phases) - 1:
                lines.append("       ↓ ↓ ↓")
        
        lines.append("\n" + "=" * 60)
        lines.append(f"Critical Path: {' → '.join(self.stats['critical_path'])}")
        lines.append(f"Estimated Speedup: {self._estimate_speedup()}x")
        lines.append("=" * 60)
        
        return "\n".join(lines)


def create_parallel_orchestrator(
    agents: Dict[str, BaseAgent]
) -> ParallelOrchestrator:
    """
    Factory function to create parallel orchestrator.
    
    Args:
        agents: Dictionary of agents
        
    Returns:
        ParallelOrchestrator instance
    """
    return ParallelOrchestrator(agents)
