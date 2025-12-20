# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Collaborative Problem Solving
TRUE SWARM AGENTS - Multi-agent collaboration sessions

This enables agents to:
- Work together on complex problems
- Share perspectives and expertise
- Debate solutions
- Reach consensus
- Make collective decisions

Think of this as a "meeting room" where agents collaborate.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Set, Callable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

from .communication import (
    MessageBus,
    AgentMessage,
    MessageType,
    MessagePriority,
    get_message_bus
)
from .blackboard import (
    Blackboard,
    get_blackboard
)

logger = logging.getLogger(__name__)


class CollaborationPhase(Enum):
    """Phases of collaboration"""
    INITIATED = "initiated"          # Session started
    GATHERING = "gathering"          # Collecting input
    BRAINSTORMING = "brainstorming"  # Generating ideas
    DEBATING = "debating"            # Discussing options
    VOTING = "voting"                # Voting on solution
    CONSENSUS = "consensus"          # Agreement reached
    COMPLETE = "complete"            # Session complete
    FAILED = "failed"                # Could not reach agreement


@dataclass
class CollaborationInput:
    """Input from an agent in collaboration session"""
    agent_id: str
    phase: CollaborationPhase
    content: Any
    timestamp: datetime = field(default_factory=datetime.now)
    confidence: float = 1.0  # 0-1, how confident is agent
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'agent_id': self.agent_id,
            'phase': self.phase.value,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'confidence': self.confidence
        }


@dataclass
class CollaborationResult:
    """Result of collaboration session"""
    session_id: str
    problem: str
    solution: Optional[Any]
    consensus_reached: bool
    participating_agents: List[str]
    inputs: List[CollaborationInput]
    final_votes: Dict[str, Any]
    duration_seconds: float
    phase: CollaborationPhase
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'session_id': self.session_id,
            'problem': self.problem,
            'solution': self.solution,
            'consensus_reached': self.consensus_reached,
            'participating_agents': self.participating_agents,
            'inputs': [i.to_dict() for i in self.inputs],
            'final_votes': self.final_votes,
            'duration_seconds': self.duration_seconds,
            'phase': self.phase.value
        }


class CollaborationSession:
    """
    Multi-agent collaboration session.
    
    This is where the magic happens - agents work TOGETHER
    to solve complex problems that require multiple perspectives.
    
    Example use cases:
    - "Should we enter mobile-first market?"
    - "What's our biggest competitive threat?"
    - "How to prioritize Q1 initiatives?"
    """
    
    def __init__(
        self,
        session_id: str,
        problem: str,
        agents: List[str],
        facilitator: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        Initialize collaboration session.
        
        Args:
            session_id: Unique session identifier
            problem: Problem to solve
            agents: List of agent IDs to involve
            facilitator: Optional agent leading the session
            timeout: Max time for session (seconds)
        """
        self.session_id = session_id
        self.problem = problem
        self.agents = set(agents)
        self.facilitator = facilitator or list(agents)[0]
        self.timeout = timeout
        
        # Session state
        self.phase = CollaborationPhase.INITIATED
        self.inputs: List[CollaborationInput] = []
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None
        
        # Communication
        self.message_bus = get_message_bus()
        self.blackboard = get_blackboard()
        
        # Blackboard key for this session
        self.bb_key = f"collab.{session_id}"
        
        logger.info(
            f"[Collaboration] 🤝 Session '{session_id}' started: {problem}"
        )
        logger.info(
            f"[Collaboration] 👥 Participants: {', '.join(agents)}"
        )
    
    async def run(self) -> CollaborationResult:
        """
        Run the collaboration session through all phases.
        
        Returns:
            CollaborationResult with solution and consensus info
        """
        try:
            # Phase 1: Gather initial perspectives
            self.phase = CollaborationPhase.GATHERING
            await self._gather_perspectives()
            
            # Phase 2: Brainstorm solutions
            self.phase = CollaborationPhase.BRAINSTORMING
            solutions = await self._brainstorm_solutions()
            
            # Phase 3: Debate solutions
            if len(solutions) > 1:
                self.phase = CollaborationPhase.DEBATING
                await self._debate_solutions(solutions)
            
            # Phase 4: Vote on best solution
            self.phase = CollaborationPhase.VOTING
            votes = await self._vote_on_solutions(solutions)
            
            # Phase 5: Check consensus
            self.phase = CollaborationPhase.CONSENSUS
            solution, consensus = await self._check_consensus(votes)
            
            self.phase = CollaborationPhase.COMPLETE
            
        except asyncio.TimeoutError:
            logger.warning(
                f"[Collaboration] ⏱️ Session '{self.session_id}' timed out"
            )
            self.phase = CollaborationPhase.FAILED
            solution = None
            consensus = False
            votes = {}
        
        except Exception as e:
            logger.error(
                f"[Collaboration] ❌ Session failed: {e}",
                exc_info=True
            )
            self.phase = CollaborationPhase.FAILED
            solution = None
            consensus = False
            votes = {}
        
        finally:
            self.end_time = datetime.now()
        
        duration = (self.end_time - self.start_time).total_seconds()
        
        result = CollaborationResult(
            session_id=self.session_id,
            problem=self.problem,
            solution=solution,
            consensus_reached=consensus,
            participating_agents=list(self.agents),
            inputs=self.inputs,
            final_votes=votes,
            duration_seconds=duration,
            phase=self.phase
        )
        
        # Publish result to blackboard
        self.blackboard.publish(
            key=f"{self.bb_key}.result",
            value=result.to_dict(),
            agent_id=self.facilitator
        )
        
        logger.info(
            f"[Collaboration] ✅ Session complete: "
            f"consensus={consensus}, solution={solution}"
        )
        
        return result
    
    async def _gather_perspectives(self):
        """Gather initial perspectives from all agents"""
        logger.info(
            f"[Collaboration] 📊 Gathering perspectives on: {self.problem}"
        )
        
        # Publish problem to blackboard
        self.blackboard.publish(
            key=f"{self.bb_key}.problem",
            value={
                'problem': self.problem,
                'agents': list(self.agents),
                'phase': 'gathering'
            },
            agent_id=self.facilitator,
            tags={'collaboration', 'active'}
        )
        
        # Request perspectives from all agents
        for agent_id in self.agents:
            await self.message_bus.send(
                AgentMessage(
                    id=f"{self.session_id}_request_{agent_id}",
                    from_agent=self.facilitator,
                    to_agent=agent_id,
                    type=MessageType.REQUEST,
                    priority=MessagePriority.HIGH,
                    subject=f"Collaboration: {self.problem}",
                    payload={
                        'session_id': self.session_id,
                        'action': 'provide_perspective',
                        'problem': self.problem
                    },
                    requires_response=True,
                    conversation_id=self.session_id
                )
            )
        
        # Wait for responses (with timeout)
        await asyncio.sleep(2.0)  # Give agents time to respond
        
        # Collect perspectives from blackboard
        entries = self.blackboard.query(
            pattern=f"{self.bb_key}.perspective.*"
        )
        
        for entry in entries:
            self.inputs.append(
                CollaborationInput(
                    agent_id=entry.agent_id,
                    phase=CollaborationPhase.GATHERING,
                    content=entry.value
                )
            )
        
        logger.info(
            f"[Collaboration] 📥 Collected {len(entries)} perspectives"
        )
    
    async def _brainstorm_solutions(self) -> List[Dict[str, Any]]:
        """Brainstorm potential solutions"""
        logger.info("[Collaboration] 💡 Brainstorming solutions...")
        
        # Request ideas from all agents
        for agent_id in self.agents:
            await self.message_bus.send(
                AgentMessage(
                    id=f"{self.session_id}_brainstorm_{agent_id}",
                    from_agent=self.facilitator,
                    to_agent=agent_id,
                    type=MessageType.REQUEST,
                    priority=MessagePriority.MEDIUM,
                    subject="Propose solutions",
                    payload={
                        'session_id': self.session_id,
                        'action': 'propose_solution',
                        'problem': self.problem,
                        'perspectives': [i.to_dict() for i in self.inputs]
                    },
                    conversation_id=self.session_id
                )
            )
        
        # Wait for proposals
        await asyncio.sleep(2.0)
        
        # Collect proposals
        proposals = self.blackboard.query(
            pattern=f"{self.bb_key}.proposal.*"
        )
        
        solutions = []
        for entry in proposals:
            solutions.append(entry.value)
            self.inputs.append(
                CollaborationInput(
                    agent_id=entry.agent_id,
                    phase=CollaborationPhase.BRAINSTORMING,
                    content=entry.value
                )
            )
        
        logger.info(
            f"[Collaboration] 💡 Generated {len(solutions)} solution proposals"
        )
        
        return solutions
    
    async def _debate_solutions(self, solutions: List[Dict[str, Any]]):
        """Let agents debate the proposed solutions"""
        logger.info(
            f"[Collaboration] 🗣️ Debating {len(solutions)} solutions..."
        )
        
        # Publish solutions for debate
        self.blackboard.publish(
            key=f"{self.bb_key}.solutions",
            value=solutions,
            agent_id=self.facilitator
        )
        
        # Request opinions from all agents
        for agent_id in self.agents:
            await self.message_bus.send(
                AgentMessage(
                    id=f"{self.session_id}_debate_{agent_id}",
                    from_agent=self.facilitator,
                    to_agent=agent_id,
                    type=MessageType.REQUEST,
                    priority=MessagePriority.MEDIUM,
                    subject="Evaluate solutions",
                    payload={
                        'session_id': self.session_id,
                        'action': 'evaluate_solutions',
                        'solutions': solutions
                    },
                    conversation_id=self.session_id
                )
            )
        
        # Wait for debate
        await asyncio.sleep(2.0)
        
        # Collect evaluations
        evaluations = self.blackboard.query(
            pattern=f"{self.bb_key}.evaluation.*"
        )
        
        for entry in evaluations:
            self.inputs.append(
                CollaborationInput(
                    agent_id=entry.agent_id,
                    phase=CollaborationPhase.DEBATING,
                    content=entry.value
                )
            )
        
        logger.info(
            f"[Collaboration] 📝 Collected {len(evaluations)} evaluations"
        )
    
    async def _vote_on_solutions(
        self,
        solutions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Let agents vote on solutions.
        
        Each agent can vote with weighted preference.
        """
        logger.info("[Collaboration] 🗳️ Voting on solutions...")
        
        if not solutions:
            return {}
        
        # Request votes
        for agent_id in self.agents:
            await self.message_bus.send(
                AgentMessage(
                    id=f"{self.session_id}_vote_{agent_id}",
                    from_agent=self.facilitator,
                    to_agent=agent_id,
                    type=MessageType.REQUEST,
                    priority=MessagePriority.HIGH,
                    subject="Vote on solutions",
                    payload={
                        'session_id': self.session_id,
                        'action': 'vote',
                        'solutions': solutions
                    },
                    requires_response=True,
                    conversation_id=self.session_id
                )
            )
        
        # Wait for votes
        await asyncio.sleep(1.5)
        
        # Collect votes from blackboard
        vote_entries = self.blackboard.query(
            pattern=f"{self.bb_key}.vote.*"
        )
        
        votes = {}
        for entry in vote_entries:
            votes[entry.agent_id] = entry.value
            self.inputs.append(
                CollaborationInput(
                    agent_id=entry.agent_id,
                    phase=CollaborationPhase.VOTING,
                    content=entry.value,
                    confidence=entry.value.get('confidence', 1.0)
                )
            )
        
        logger.info(f"[Collaboration] 📊 Collected {len(votes)} votes")
        
        return votes
    
    async def _check_consensus(
        self,
        votes: Dict[str, Any]
    ) -> tuple[Optional[Any], bool]:
        """
        Check if consensus was reached.
        
        Consensus requires:
        - Majority agreement (>50%)
        - Or weighted agreement (>60% with confidence)
        
        Returns:
            (solution, consensus_reached)
        """
        if not votes:
            return None, False
        
        # Count votes for each solution
        solution_votes: Dict[str, List[tuple[str, float]]] = {}
        
        for agent_id, vote in votes.items():
            choice = vote.get('choice')
            confidence = vote.get('confidence', 1.0)
            
            if choice not in solution_votes:
                solution_votes[choice] = []
            
            solution_votes[choice].append((agent_id, confidence))
        
        # Calculate weighted scores
        total_agents = len(votes)
        scores = {}
        
        for solution, agent_votes in solution_votes.items():
            # Simple majority
            count = len(agent_votes)
            majority_pct = count / total_agents
            
            # Weighted score (with confidence)
            weighted_score = sum(conf for _, conf in agent_votes) / total_agents
            
            scores[solution] = {
                'count': count,
                'majority_pct': majority_pct,
                'weighted_score': weighted_score,
                'agents': [aid for aid, _ in agent_votes]
            }
        
        # Find best solution
        best_solution = max(
            scores.items(),
            key=lambda x: x[1]['weighted_score']
        )
        
        solution_key = best_solution[0]
        solution_data = best_solution[1]
        
        # Check consensus
        consensus = (
            solution_data['majority_pct'] > 0.5
            or solution_data['weighted_score'] > 0.6
        )
        
        logger.info(
            f"[Collaboration] 🎯 Best solution: {solution_key} "
            f"(majority={solution_data['majority_pct']:.1%}, "
            f"weighted={solution_data['weighted_score']:.1%})"
        )
        
        if consensus:
            logger.info("[Collaboration] ✅ Consensus reached!")
        else:
            logger.warning("[Collaboration] ⚠️ No consensus")
        
        return solution_key, consensus


class CollaborationManager:
    """
    Manager for all collaboration sessions.
    
    Tracks active sessions, provides API for creating sessions.
    """
    
    def __init__(self):
        self.sessions: Dict[str, CollaborationSession] = {}
        self.completed_sessions: List[CollaborationResult] = []
        
        logger.info("[CollaborationManager] 📋 Manager initialized")
    
    async def create_session(
        self,
        problem: str,
        agents: List[str],
        facilitator: Optional[str] = None,
        timeout: float = 30.0
    ) -> CollaborationResult:
        """
        Create and run a new collaboration session.
        
        Args:
            problem: Problem to solve
            agents: Agent IDs to involve
            facilitator: Optional facilitator
            timeout: Max session time
            
        Returns:
            CollaborationResult
        """
        session_id = f"collab_{int(datetime.now().timestamp() * 1000)}"
        
        session = CollaborationSession(
            session_id=session_id,
            problem=problem,
            agents=agents,
            facilitator=facilitator,
            timeout=timeout
        )
        
        self.sessions[session_id] = session
        
        # Run session
        result = await session.run()
        
        # Store result
        self.completed_sessions.append(result)
        
        # Clean up
        del self.sessions[session_id]
        
        return result
    
    def get_session(self, session_id: str) -> Optional[CollaborationSession]:
        """Get active session by ID"""
        return self.sessions.get(session_id)
    
    def get_active_sessions(self) -> List[CollaborationSession]:
        """Get all active sessions"""
        return list(self.sessions.values())
    
    def get_completed_sessions(
        self,
        limit: int = 10
    ) -> List[CollaborationResult]:
        """Get recent completed sessions"""
        return self.completed_sessions[-limit:]


# Global manager instance
_collaboration_manager: Optional[CollaborationManager] = None


def get_collaboration_manager() -> CollaborationManager:
    """Get or create global collaboration manager"""
    global _collaboration_manager
    if _collaboration_manager is None:
        _collaboration_manager = CollaborationManager()
    return _collaboration_manager


def reset_collaboration_manager():
    """Reset global manager (for testing)"""
    global _collaboration_manager
    _collaboration_manager = None
