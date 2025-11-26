"""
Growth Engine 2.0 - Prospector Agent
💎 "The Growth Hacker" - Finds opportunities and market gaps
Uses: _build_differentiation_matrix(), _discover_real_market_gaps(), generate_competitive_swot_analysis()
"""

import logging
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent
from .agent_types import AnalysisContext, AgentPriority, InsightType

logger = logging.getLogger(__name__)


class ProspectorAgent(BaseAgent):
    """
    💎 Prospector Agent - Growth Hacker
    
    Responsibilities:
    - Build differentiation matrix
    - Discover real market gaps
    - Generate competitive SWOT analysis
    - Find untapped opportunities
    """
    
    def __init__(self):
        super().__init__(
            agent_id="prospector",
            name="Prospector",
            role="Growth Hacker",
            avatar="💎",
            personality="Optimistic visionary who spots opportunities others miss"
        )
        self.dependencies = ['analyst']
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """Find opportunities and market gaps"""
        
        # Import the REAL functions from main.py
        from main import (
            _build_differentiation_matrix,
            _discover_real_market_gaps,
            generate_competitive_swot_analysis
        )
        
        analyst_results = self.get_dependency_results(context, 'analyst')
        
        if not analyst_results:
            self._emit_insight(
                "⚠️ No Analyst data — limited opportunity analysis",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
            return {'market_gaps': [], 'swot': None, 'differentiation_matrix': {}}
        
        your_analysis = analyst_results.get('your_analysis', {})
        competitor_analyses = analyst_results.get('competitor_analyses', [])
        
        self._emit_insight(
            "💎 Hunting for opportunities — let's find your edge...",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # 1. Build Differentiation Matrix
        self._update_progress(15, "Building differentiation matrix...")
        
        try:
            differentiation_matrix = await _build_differentiation_matrix(
                your_analysis=your_analysis,
                competitor_analyses=competitor_analyses,
                language='en',
                industry_context=context.industry
            )
            
            # Extract key differentiators
            your_advantages = differentiation_matrix.get('your_advantages', [])
            competitor_advantages = differentiation_matrix.get('competitor_advantages', [])
            
            if your_advantages:
                self._emit_insight(
                    f"💪 Your edge: {', '.join(your_advantages[:3])}",
                    priority=AgentPriority.HIGH,
                    insight_type=InsightType.OPPORTUNITY,
                    data={'advantages': your_advantages}
                )
            
            if competitor_advantages:
                self._emit_insight(
                    f"👀 Competitors excel at: {', '.join(competitor_advantages[:3])}",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING,
                    data={'competitor_advantages': competitor_advantages}
                )
                
        except Exception as e:
            logger.error(f"[Prospector] Differentiation matrix failed: {e}")
            differentiation_matrix = {}
            self._emit_insight(
                f"⚠️ Couldn't build differentiation matrix: {str(e)}",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
        
        # 2. Discover Real Market Gaps
        self._update_progress(40, "Discovering market gaps...")
        
        try:
            market_gaps = await _discover_real_market_gaps(
                your_analysis=your_analysis,
                competitor_analyses=competitor_analyses,
                language='en'
            )
            
            self._emit_insight(
                f"🔍 Found {len(market_gaps)} market gaps!",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
            
            # Emit top 3 gaps as opportunities
            for idx, gap in enumerate(market_gaps[:3]):
                title = gap.get('title', gap.get('gap', 'Unknown opportunity'))
                potential = gap.get('potential', 'high')
                
                emoji = '💎' if potential == 'high' else '✨' if potential == 'medium' else '💡'
                
                self._emit_insight(
                    f"{emoji} Market gap: {title}",
                    priority=AgentPriority.HIGH if potential == 'high' else AgentPriority.MEDIUM,
                    insight_type=InsightType.OPPORTUNITY,
                    data=gap
                )
                
        except Exception as e:
            logger.error(f"[Prospector] Market gaps discovery failed: {e}")
            market_gaps = []
            self._emit_insight(
                f"⚠️ Market gap analysis limited: {str(e)}",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
        
        # 3. Generate Competitive SWOT Analysis
        self._update_progress(70, "Generating SWOT analysis...")
        
        try:
            swot = await generate_competitive_swot_analysis(
                your_analysis=your_analysis,
                competitor_analyses=competitor_analyses,
                language='en'
            )
            
            # Extract and emit key SWOT insights
            strengths = swot.get('strengths', [])
            weaknesses = swot.get('weaknesses', [])
            opportunities = swot.get('opportunities', [])
            threats = swot.get('threats', [])
            
            if strengths:
                self._emit_insight(
                    f"💪 Key strength: {strengths[0] if isinstance(strengths[0], str) else strengths[0].get('item', 'N/A')}",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING
                )
            
            if opportunities:
                top_opp = opportunities[0] if isinstance(opportunities[0], str) else opportunities[0].get('item', 'N/A')
                self._emit_insight(
                    f"🚀 Top opportunity: {top_opp}",
                    priority=AgentPriority.HIGH,
                    insight_type=InsightType.OPPORTUNITY
                )
            
            if weaknesses:
                self._emit_insight(
                    f"⚠️ Key weakness to address: {weaknesses[0] if isinstance(weaknesses[0], str) else weaknesses[0].get('item', 'N/A')}",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING
                )
            
        except Exception as e:
            logger.error(f"[Prospector] SWOT analysis failed: {e}")
            swot = None
            self._emit_insight(
                f"⚠️ SWOT analysis limited: {str(e)}",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
        
        # 4. Synthesize opportunities
        self._update_progress(90, "Synthesizing opportunities...")
        
        opportunities_summary = self._synthesize_opportunities(
            differentiation_matrix=differentiation_matrix,
            market_gaps=market_gaps,
            swot=swot
        )
        
        total_opportunities = len(market_gaps) + len(differentiation_matrix.get('your_advantages', []))
        
        self._emit_insight(
            f"✅ Opportunity scan complete: {total_opportunities} growth opportunities identified",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data={'total_opportunities': total_opportunities}
        )
        
        return {
            'differentiation_matrix': differentiation_matrix,
            'market_gaps': market_gaps,
            'swot': swot,
            'opportunities_summary': opportunities_summary
        }
    
    def _synthesize_opportunities(
        self,
        differentiation_matrix: Dict[str, Any],
        market_gaps: List[Dict[str, Any]],
        swot: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Synthesize all opportunity data into actionable summary"""
        
        quick_wins = []
        strategic_plays = []
        defensive_moves = []
        
        # From market gaps
        for gap in market_gaps:
            effort = gap.get('effort', 'medium')
            potential = gap.get('potential', 'medium')
            
            entry = {
                'title': gap.get('title', gap.get('gap', 'Unknown')),
                'source': 'market_gap',
                'potential': potential
            }
            
            if effort == 'low' and potential in ['high', 'medium']:
                quick_wins.append(entry)
            elif potential == 'high':
                strategic_plays.append(entry)
        
        # From differentiation matrix
        for adv in differentiation_matrix.get('competitor_advantages', []):
            defensive_moves.append({
                'title': f"Close gap: {adv}",
                'source': 'differentiation',
                'potential': 'medium'
            })
        
        # From SWOT opportunities
        if swot:
            for opp in swot.get('opportunities', [])[:2]:
                opp_text = opp if isinstance(opp, str) else opp.get('item', '')
                strategic_plays.append({
                    'title': opp_text,
                    'source': 'swot',
                    'potential': 'high'
                })
        
        return {
            'quick_wins': quick_wins[:5],
            'strategic_plays': strategic_plays[:5],
            'defensive_moves': defensive_moves[:3],
            'total_count': len(quick_wins) + len(strategic_plays) + len(defensive_moves)
        }
