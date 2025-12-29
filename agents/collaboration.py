# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Agent Collaboration Framework
TRUE SWARM EDITION - Multi-agent problem solving

This enables agents to:
- Collaborate on complex problems
- Share perspectives and vote on solutions
- Reach consensus through structured dialogue
- Combine expertise from multiple agents

This is where the swarm becomes smarter than any individual agent.
"""

import asyncio
import logging
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)


class CollaborationPhase(Enum):
    """Phases of a collaboration session"""
    INITIATED = "initiated"
    GATHERING_PERSPECTIVES = "gathering_perspectives"
    GENERATING_PROPOSALS = "generating_proposals"
    VOTING = "voting"
    FINALIZING = "finalizing"
    COMPLETE = "complete"
    FAILED = "failed"
    TIMEOUT = "timeout"


class VoteType(Enum):
    """Types of votes"""
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"
    MODIFY = "modify"


@dataclass
class AgentPerspective:
    """An agent's perspective on a problem"""
    agent_id: str
    perspective: str
    confidence: float = 1.0
    supporting_data: Dict[str, Any] = field(default_factory=dict)
    concerns: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Proposal:
    """A proposed solution"""
    proposal_id: str
    proposed_by: str
    content: str
    rationale: str
    implementation_steps: List[str] = field(default_factory=list)
    estimated_impact: Optional[str] = None
    confidence: float = 1.0
    supporting_agents: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Vote:
    """An agent's vote on a proposal"""
    agent_id: str
    proposal_id: str
    vote_type: VoteType
    weight: float = 1.0
    reasoning: str = ""
    suggested_modifications: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CollaborationResult:
    """Result of a collaboration session"""
    session_id: str
    problem: str
    consensus_reached: bool
    winning_proposal: Optional[Proposal] = None
    solution: Optional[str] = None
    confidence: float = 0.0
    participating_agents: List[str] = field(default_factory=list)
    perspectives: List[AgentPerspective] = field(default_factory=list)
    proposals: List[Proposal] = field(default_factory=list)
    votes: List[Vote] = field(default_factory=list)
    dissenting_opinions: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    phase_reached: CollaborationPhase = CollaborationPhase.INITIATED
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'session_id': self.session_id,
            'problem': self.problem,
            'consensus_reached': self.consensus_reached,
            'solution': self.solution,
            'confidence': self.confidence,
            'participating_agents': self.participating_agents,
            'duration_seconds': self.duration_seconds,
            'dissenting_opinions': self.dissenting_opinions
        }


@dataclass
class CollaborationSession:
    """Active collaboration session"""
    session_id: str
    problem: str
    facilitator: str
    agents: List[str]
    phase: CollaborationPhase = CollaborationPhase.INITIATED
    perspectives: Dict[str, AgentPerspective] = field(default_factory=dict)
    proposals: Dict[str, Proposal] = field(default_factory=dict)
    votes: Dict[str, List[Vote]] = field(default_factory=lambda: defaultdict(list))
    created_at: datetime = field(default_factory=datetime.now)
    timeout: float = 60.0
    consensus_threshold: float = 0.7
    min_participation: float = 0.5
    
    # Async coordination
    perspective_event: asyncio.Event = field(default_factory=asyncio.Event)
    proposal_event: asyncio.Event = field(default_factory=asyncio.Event)
    vote_event: asyncio.Event = field(default_factory=asyncio.Event)
    
    def is_expired(self) -> bool:
        elapsed = (datetime.now() - self.created_at).total_seconds()
        return elapsed > self.timeout
    
    def participation_rate(self) -> float:
        total = len(self.agents)
        participated = len(set(
            list(self.perspectives.keys()) +
            [p.proposed_by for p in self.proposals.values()]
        ))
        return participated / total if total > 0 else 0
    
    def has_quorum(self) -> bool:
        return self.participation_rate() >= self.min_participation


class CollaborationManager:
    """
    Manages multi-agent collaboration sessions.
    
    Enables agents to work together on complex problems
    through structured dialogue and consensus building.
    """
    
    def __init__(self):
        # Active sessions
        self._sessions: Dict[str, CollaborationSession] = {}
        
        # Completed sessions
        self._completed: List[CollaborationResult] = []
        
        # Event callbacks
        self._on_session_start: Optional[Callable] = None
        self._on_phase_change: Optional[Callable] = None
        self._on_consensus: Optional[Callable] = None
        
        # Statistics
        self._stats = {
            'total_sessions': 0,
            'successful_consensus': 0,
            'failed_consensus': 0,
            'timeout_sessions': 0,
            'avg_duration': 0.0,
            'avg_participation': 0.0
        }
        
        # Session counter for IDs
        self._session_counter = 0
        
        logger.info("[CollaborationManager] 🤝 Collaboration manager initialized")
    
    def set_event_callbacks(
        self,
        on_session_start: Optional[Callable] = None,
        on_phase_change: Optional[Callable] = None,
        on_consensus: Optional[Callable] = None
    ):
        """Set event callbacks"""
        self._on_session_start = on_session_start
        self._on_phase_change = on_phase_change
        self._on_consensus = on_consensus
    
    async def create_session(
        self,
        problem: str,
        agents: List[str],
        facilitator: str,
        timeout: float = 60.0,
        consensus_threshold: float = 0.7,
        min_participation: float = 0.5
    ) -> CollaborationResult:
        """
        Create and run a collaboration session.
        
        Args:
            problem: Problem to solve
            agents: List of participating agent IDs
            facilitator: Agent facilitating the session
            timeout: Max session duration
            consensus_threshold: Required agreement level (0-1)
            min_participation: Min participation rate (0-1)
        
        Returns:
            CollaborationResult with solution (if consensus reached)
        """
        self._session_counter += 1
        session_id = f"collab_{self._session_counter}_{int(datetime.now().timestamp())}"
        
        session = CollaborationSession(
            session_id=session_id,
            problem=problem,
            facilitator=facilitator,
            agents=agents,
            timeout=timeout,
            consensus_threshold=consensus_threshold,
            min_participation=min_participation
        )
        
        self._sessions[session_id] = session
        self._stats['total_sessions'] += 1
        
        logger.info(
            f"[CollaborationManager] 🎯 Session {session_id} started: "
            f"'{problem[:50]}...' with {len(agents)} agents"
        )
        
        # Fire callback
        if self._on_session_start:
            try:
                if asyncio.iscoroutinefunction(self._on_session_start):
                    await self._on_session_start(session)
                else:
                    self._on_session_start(session)
            except Exception as e:
                logger.error(f"[CollaborationManager] Callback error: {e}")
        
        # Run collaboration phases
        try:
            result = await self._run_session(session)
            self._completed.append(result)
            return result
            
        except asyncio.TimeoutError:
            logger.warning(f"[CollaborationManager] ⏱️ Session {session_id} timed out")
            self._stats['timeout_sessions'] += 1
            
            result = CollaborationResult(
                session_id=session_id,
                problem=problem,
                consensus_reached=False,
                participating_agents=agents,
                phase_reached=session.phase,
                perspectives=list(session.perspectives.values()),
                duration_seconds=timeout
            )
            self._completed.append(result)
            return result
            
        finally:
            # Clean up
            if session_id in self._sessions:
                del self._sessions[session_id]
    
    async def _run_session(self, session: CollaborationSession) -> CollaborationResult:
        """Run through collaboration phases"""
        start_time = datetime.now()
        
        try:
            # Phase 1: Gather perspectives
            await self._set_phase(session, CollaborationPhase.GATHERING_PERSPECTIVES)
            await asyncio.wait_for(
                self._gather_perspectives(session),
                timeout=session.timeout * 0.3
            )
            
            if not session.has_quorum():
                return self._create_result(session, start_time, "Insufficient participation")
            
            # Phase 2: Generate proposals
            await self._set_phase(session, CollaborationPhase.GENERATING_PROPOSALS)
            await asyncio.wait_for(
                self._generate_proposals(session),
                timeout=session.timeout * 0.3
            )
            
            if not session.proposals:
                # Generate default proposal from perspectives
                await self._synthesize_proposal(session)
            
            # Phase 3: Vote on proposals
            await self._set_phase(session, CollaborationPhase.VOTING)
            await asyncio.wait_for(
                self._conduct_voting(session),
                timeout=session.timeout * 0.3
            )
            
            # Phase 4: Finalize
            await self._set_phase(session, CollaborationPhase.FINALIZING)
            result = await self._finalize_consensus(session, start_time)
            
            await self._set_phase(session, CollaborationPhase.COMPLETE)
            return result
            
        except Exception as e:
            logger.error(f"[CollaborationManager] Session error: {e}", exc_info=True)
            await self._set_phase(session, CollaborationPhase.FAILED)
            return self._create_result(session, start_time, str(e))
    
    async def _set_phase(self, session: CollaborationSession, phase: CollaborationPhase):
        """Update session phase"""
        session.phase = phase
        logger.info(f"[CollaborationManager] 📍 Session {session.session_id}: {phase.value}")
        
        if self._on_phase_change:
            try:
                if asyncio.iscoroutinefunction(self._on_phase_change):
                    await self._on_phase_change(session, phase)
                else:
                    self._on_phase_change(session, phase)
            except Exception:
                pass
    
    async def _gather_perspectives(self, session: CollaborationSession):
        """Wait for perspectives from agents"""
        # Set a short wait - agents should contribute quickly
        await asyncio.sleep(0.1)
        
        # If perspectives were submitted, continue
        if session.perspectives:
            return
        
        # Wait for perspective event or timeout
        try:
            await asyncio.wait_for(
                session.perspective_event.wait(),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            pass
    
    async def _generate_proposals(self, session: CollaborationSession):
        """Wait for proposals"""
        await asyncio.sleep(0.1)
        
        if session.proposals:
            return
        
        try:
            await asyncio.wait_for(
                session.proposal_event.wait(),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            pass
    
    async def _synthesize_proposal(self, session: CollaborationSession):
        """Create proposal from perspectives if none submitted"""
        if not session.perspectives:
            return
        
        # Combine perspectives into a synthesized proposal
        perspectives_text = []
        for p in session.perspectives.values():
            perspectives_text.append(f"- {p.agent_id}: {p.perspective}")
        
        proposal = Proposal(
            proposal_id=f"{session.session_id}_synthesized",
            proposed_by=session.facilitator,
            content=f"Synthesized from {len(session.perspectives)} perspectives",
            rationale="Combined agent insights",
            supporting_agents=list(session.perspectives.keys())
        )
        
        session.proposals[proposal.proposal_id] = proposal
    
    async def _conduct_voting(self, session: CollaborationSession):
        """Conduct voting on proposals"""
        await asyncio.sleep(0.1)
        
        # Wait for votes
        try:
            await asyncio.wait_for(
                session.vote_event.wait(),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            pass
    
    async def _finalize_consensus(
        self,
        session: CollaborationSession,
        start_time: datetime
    ) -> CollaborationResult:
        """Determine final consensus"""
        duration = (datetime.now() - start_time).total_seconds()
        
        # Calculate vote results for each proposal
        best_proposal = None
        best_score = 0.0
        dissenting = []
        
        for proposal_id, proposal in session.proposals.items():
            votes = session.votes.get(proposal_id, [])
            
            if not votes:
                # No votes = auto-approve if from facilitator
                if proposal.proposed_by == session.facilitator:
                    best_proposal = proposal
                    best_score = 0.6
                continue
            
            # Calculate weighted vote score
            total_weight = sum(v.weight for v in votes)
            approve_weight = sum(
                v.weight for v in votes
                if v.vote_type == VoteType.APPROVE
            )
            
            score = approve_weight / total_weight if total_weight > 0 else 0
            
            # Collect dissenting opinions
            for v in votes:
                if v.vote_type == VoteType.REJECT and v.reasoning:
                    dissenting.append(f"{v.agent_id}: {v.reasoning}")
            
            if score > best_score:
                best_score = score
                best_proposal = proposal
        
        # Determine if consensus reached
        consensus_reached = best_score >= session.consensus_threshold
        
        if consensus_reached:
            self._stats['successful_consensus'] += 1
            logger.info(
                f"[CollaborationManager] ✅ Consensus reached in {session.session_id} "
                f"(score: {best_score:.2f})"
            )
            
            # Fire consensus callback
            if self._on_consensus:
                try:
                    if asyncio.iscoroutinefunction(self._on_consensus):
                        await self._on_consensus(session, best_proposal, best_score)
                    else:
                        self._on_consensus(session, best_proposal, best_score)
                except Exception:
                    pass
        else:
            self._stats['failed_consensus'] += 1
            logger.info(
                f"[CollaborationManager] ❌ No consensus in {session.session_id} "
                f"(best score: {best_score:.2f})"
            )
        
        # Update stats
        self._update_stats(duration, session.participation_rate())
        
        return CollaborationResult(
            session_id=session.session_id,
            problem=session.problem,
            consensus_reached=consensus_reached,
            winning_proposal=best_proposal,
            solution=best_proposal.content if best_proposal else None,
            confidence=best_score,
            participating_agents=session.agents,
            perspectives=list(session.perspectives.values()),
            proposals=list(session.proposals.values()),
            votes=[v for votes in session.votes.values() for v in votes],
            dissenting_opinions=dissenting,
            duration_seconds=duration,
            phase_reached=session.phase
        )
    
    def _create_result(
        self,
        session: CollaborationSession,
        start_time: datetime,
        error: str
    ) -> CollaborationResult:
        """Create result for failed session"""
        duration = (datetime.now() - start_time).total_seconds()
        
        return CollaborationResult(
            session_id=session.session_id,
            problem=session.problem,
            consensus_reached=False,
            participating_agents=session.agents,
            perspectives=list(session.perspectives.values()),
            proposals=list(session.proposals.values()),
            duration_seconds=duration,
            phase_reached=session.phase,
            metadata={'error': error}
        )
    
    def _update_stats(self, duration: float, participation: float):
        """Update running statistics"""
        total = self._stats['total_sessions']
        
        # Running average for duration
        old_avg_dur = self._stats['avg_duration']
        self._stats['avg_duration'] = (old_avg_dur * (total - 1) + duration) / total
        
        # Running average for participation
        old_avg_part = self._stats['avg_participation']
        self._stats['avg_participation'] = (old_avg_part * (total - 1) + participation) / total
    
    # ========================================================================
    # External API for agents to contribute
    # ========================================================================
    
    def submit_perspective(
        self,
        session_id: str,
        agent_id: str,
        perspective: str,
        confidence: float = 1.0,
        supporting_data: Optional[Dict[str, Any]] = None,
        concerns: Optional[List[str]] = None
    ) -> bool:
        """Agent submits their perspective"""
        session = self._sessions.get(session_id)
        if not session:
            logger.warning(f"[CollaborationManager] Session {session_id} not found")
            return False
        
        if agent_id not in session.agents:
            logger.warning(f"[CollaborationManager] Agent {agent_id} not in session")
            return False
        
        session.perspectives[agent_id] = AgentPerspective(
            agent_id=agent_id,
            perspective=perspective,
            confidence=confidence,
            supporting_data=supporting_data or {},
            concerns=concerns or []
        )
        
        # Signal that perspective received
        if len(session.perspectives) >= len(session.agents) * session.min_participation:
            session.perspective_event.set()
        
        logger.debug(f"[CollaborationManager] 💭 {agent_id} submitted perspective")
        return True
    
    def submit_proposal(
        self,
        session_id: str,
        agent_id: str,
        content: str,
        rationale: str,
        implementation_steps: Optional[List[str]] = None,
        estimated_impact: Optional[str] = None,
        confidence: float = 1.0
    ) -> Optional[str]:
        """Agent submits a proposal"""
        session = self._sessions.get(session_id)
        if not session:
            return None
        
        proposal_id = f"{session_id}_{agent_id}_{len(session.proposals)}"
        
        proposal = Proposal(
            proposal_id=proposal_id,
            proposed_by=agent_id,
            content=content,
            rationale=rationale,
            implementation_steps=implementation_steps or [],
            estimated_impact=estimated_impact,
            confidence=confidence
        )
        
        session.proposals[proposal_id] = proposal
        session.proposal_event.set()
        
        logger.debug(f"[CollaborationManager] 📝 {agent_id} submitted proposal")
        return proposal_id
    
    def submit_vote(
        self,
        session_id: str,
        agent_id: str,
        proposal_id: str,
        vote_type: VoteType,
        weight: float = 1.0,
        reasoning: str = "",
        suggested_modifications: Optional[str] = None
    ) -> bool:
        """Agent submits a vote"""
        session = self._sessions.get(session_id)
        if not session:
            return False
        
        if proposal_id not in session.proposals:
            return False
        
        vote = Vote(
            agent_id=agent_id,
            proposal_id=proposal_id,
            vote_type=vote_type,
            weight=weight,
            reasoning=reasoning,
            suggested_modifications=suggested_modifications
        )
        
        session.votes[proposal_id].append(vote)
        
        # Check if all agents have voted
        total_votes = sum(len(v) for v in session.votes.values())
        if total_votes >= len(session.agents) * session.min_participation:
            session.vote_event.set()
        
        logger.debug(f"[CollaborationManager] 🗳️ {agent_id} voted {vote_type.value}")
        return True
    
    def get_session(self, session_id: str) -> Optional[CollaborationSession]:
        """Get active session"""
        return self._sessions.get(session_id)
    
    def get_active_sessions(self) -> List[CollaborationSession]:
        """Get all active sessions"""
        return list(self._sessions.values())
    
    def get_completed_sessions(self, limit: int = 100) -> List[CollaborationResult]:
        """Get completed sessions"""
        return self._completed[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return {
            **self._stats,
            'active_sessions': len(self._sessions),
            'completed_sessions': len(self._completed)
        }
    
    def reset(self):
        """Full reset"""
        self._sessions.clear()
        self._completed.clear()
        self._session_counter = 0
        self._stats = {
            'total_sessions': 0,
            'successful_consensus': 0,
            'failed_consensus': 0,
            'timeout_sessions': 0,
            'avg_duration': 0.0,
            'avg_participation': 0.0
        }
        logger.info("[CollaborationManager] 🔄 Collaboration manager reset")


# Global instance
_collaboration_manager: Optional[CollaborationManager] = None


def get_collaboration_manager() -> CollaborationManager:
    """Get or create global collaboration manager"""
    global _collaboration_manager
    if _collaboration_manager is None:
        _collaboration_manager = CollaborationManager()
    return _collaboration_manager


def reset_collaboration_manager():
    """Reset global collaboration manager"""
    global _collaboration_manager
    if _collaboration_manager:
        _collaboration_manager.reset()
    _collaboration_manager = None
