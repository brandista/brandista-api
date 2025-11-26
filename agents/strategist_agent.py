"""
Growth Engine 2.0 - Strategist Agent
🎯 "The Strategic Advisor" - Synthesizes insights into strategy
Uses: _calculate_market_positioning(), _generate_strategic_recommendations(), analyze_creative_boldness()
"""

import logging
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent
from .types import AnalysisContext, AgentPriority, InsightType

logger = logging.getLogger(__name__)


class StrategistAgent(BaseAgent):
    """
    🎯 Strategist Agent - Strategic Advisor
    
    Responsibilities:
    - Calculate market positioning
    - Generate strategic recommendations
    - Analyze creative boldness
    - Synthesize all insights into coherent strategy
    """
    
    def __init__(self):
        super().__init__(
            agent_id="strategist",
            name="Strategist",
            role="Strategic Advisor",
            avatar="🎯",
            personality="Wise strategist who sees the big picture and connects the dots"
        )
        self.dependencies = ['analyst', 'guardian', 'prospector']
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """Synthesize insights into strategic recommendations"""
        
        # Import the REAL functions from main.py
        from main import (
            _calculate_market_positioning,
            _generate_strategic_recommendations,
            analyze_creative_boldness
        )
        
        analyst_results = self.get_dependency_results(context, 'analyst')
        guardian_results = self.get_dependency_results(context, 'guardian')
        prospector_results = self.get_dependency_results(context, 'prospector')
        
        if not analyst_results:
            self._emit_insight(
                "⚠️ Missing data — limited strategic analysis",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
            return {'positioning': {}, 'recommendations': [], 'creative_boldness': {}}
        
        your_analysis = analyst_results.get('your_analysis', {})
        competitor_analyses = analyst_results.get('competitor_analyses', [])
        your_score = analyst_results.get('your_score', 0)
        
        # Get data from other agents
        differentiation_matrix = prospector_results.get('differentiation_matrix', {}) if prospector_results else {}
        market_gaps = prospector_results.get('market_gaps', []) if prospector_results else []
        threats = guardian_results.get('threats', []) if guardian_results else []
        
        self._emit_insight(
            "🎯 Pulling it all together into a strategy...",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # 1. Calculate Market Positioning
        self._update_progress(15, "Calculating market position...")
        
        try:
            positioning = await _calculate_market_positioning(
                your_analysis=your_analysis,
                competitor_analyses=competitor_analyses
            )
            
            quadrant = positioning.get('positioning_quadrant', 'Unknown')
            competitive_score = positioning.get('competitive_score', 0)
            
            # Emit positioning insight
            position_emoji = self._get_position_emoji(quadrant)
            self._emit_insight(
                f"{position_emoji} Market position: {quadrant} (score: {competitive_score}/100)",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.METRIC,
                data={'quadrant': quadrant, 'competitive_score': competitive_score}
            )
            
            # Position-specific advice
            position_advice = self._get_position_advice(quadrant)
            if position_advice:
                self._emit_insight(
                    f"💡 {position_advice}",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.RECOMMENDATION
                )
                
        except Exception as e:
            logger.error(f"[Strategist] Market positioning failed: {e}")
            positioning = {'positioning_quadrant': 'Unknown', 'competitive_score': 0}
        
        # 2. Analyze Creative Boldness
        self._update_progress(35, "Analyzing creative boldness...")
        
        try:
            creative_boldness = await analyze_creative_boldness(
                your_analysis=your_analysis,
                competitor_analyses=competitor_analyses,
                language='en'
            )
            
            boldness_score = creative_boldness.get('creative_boldness_score', 0)
            boldness_level = self._get_boldness_level(boldness_score)
            
            self._emit_insight(
                f"🎨 Creative boldness: {boldness_score}/100 — {boldness_level}",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.METRIC,
                data={'boldness_score': boldness_score, 'level': boldness_level}
            )
            
            # Creative recommendations
            creative_recs = creative_boldness.get('recommendations', [])
            if creative_recs:
                self._emit_insight(
                    f"🎨 Creative tip: {creative_recs[0]}",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.RECOMMENDATION
                )
                
        except Exception as e:
            logger.error(f"[Strategist] Creative boldness failed: {e}")
            creative_boldness = {'creative_boldness_score': 0}
        
        # 3. Generate Strategic Recommendations
        self._update_progress(55, "Generating strategic recommendations...")
        
        try:
            recommendations = await _generate_strategic_recommendations(
                your_analysis=your_analysis,
                competitor_analyses=competitor_analyses,
                differentiation_matrix=differentiation_matrix,
                market_gaps=market_gaps,
                language='en'
            )
            
            self._emit_insight(
                f"📋 Generated {len(recommendations)} strategic recommendations",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
            
            # Emit top 3 recommendations
            for idx, rec in enumerate(recommendations[:3]):
                title = rec.get('title', rec.get('recommendation', 'Unknown'))
                priority_level = rec.get('priority', 'medium')
                
                emoji = '🔴' if priority_level == 'critical' else '🟠' if priority_level == 'high' else '🟡'
                
                self._emit_insight(
                    f"{emoji} Strategy #{idx + 1}: {title}",
                    priority=AgentPriority.HIGH if priority_level in ['critical', 'high'] else AgentPriority.MEDIUM,
                    insight_type=InsightType.RECOMMENDATION,
                    data=rec
                )
                
        except Exception as e:
            logger.error(f"[Strategist] Strategic recommendations failed: {e}")
            recommendations = []
        
        # 4. Synthesize Overall Score
        self._update_progress(80, "Calculating overall strategic score...")
        
        overall_score = self._calculate_overall_score(
            your_score=your_score,
            positioning=positioning,
            threats=threats,
            market_gaps=market_gaps
        )
        
        level = self._get_maturity_level(overall_score)
        
        self._emit_insight(
            f"📊 Overall strategic score: {overall_score}/100 — {level}",
            priority=AgentPriority.HIGH,
            insight_type=InsightType.METRIC,
            data={'overall_score': overall_score, 'level': level}
        )
        
        # 5. Final Strategic Summary
        self._update_progress(95, "Finalizing strategy...")
        
        strategic_summary = self._create_strategic_summary(
            positioning=positioning,
            recommendations=recommendations,
            creative_boldness=creative_boldness,
            overall_score=overall_score
        )
        
        self._emit_insight(
            f"✅ Strategic analysis complete — {len(recommendations)} recommendations ready",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        return {
            'positioning': positioning,
            'recommendations': recommendations,
            'creative_boldness': creative_boldness,
            'overall_score': overall_score,
            'strategic_summary': strategic_summary
        }
    
    def _get_position_emoji(self, quadrant: str) -> str:
        """Get emoji for positioning quadrant"""
        quadrant_lower = quadrant.lower()
        if 'leader' in quadrant_lower or 'ahead' in quadrant_lower:
            return '🏆'
        elif 'challenger' in quadrant_lower or 'rising' in quadrant_lower:
            return '🚀'
        elif 'niche' in quadrant_lower or 'specialist' in quadrant_lower:
            return '🎯'
        elif 'behind' in quadrant_lower or 'catch' in quadrant_lower:
            return '⚠️'
        else:
            return '📍'
    
    def _get_position_advice(self, quadrant: str) -> str:
        """Get strategic advice based on position"""
        quadrant_lower = quadrant.lower()
        if 'leader' in quadrant_lower:
            return "Protect your lead — focus on innovation and customer retention"
        elif 'challenger' in quadrant_lower:
            return "You're close to the top — double down on differentiation"
        elif 'niche' in quadrant_lower:
            return "Leverage your specialization — deepen expertise in your niche"
        elif 'behind' in quadrant_lower:
            return "Time to catch up — prioritize quick wins and high-impact improvements"
        return None
    
    def _get_boldness_level(self, score: int) -> str:
        """Get boldness level description"""
        if score >= 80:
            return "Bold innovator"
        elif score >= 60:
            return "Confident player"
        elif score >= 40:
            return "Playing it safe"
        elif score >= 20:
            return "Too conservative"
        else:
            return "Invisible"
    
    def _get_maturity_level(self, score: int) -> str:
        """Get maturity level description"""
        if score >= 80:
            return "Market leader"
        elif score >= 60:
            return "Strong performer"
        elif score >= 40:
            return "Middle of the pack"
        elif score >= 20:
            return "Needs improvement"
        else:
            return "Critical gaps"
    
    def _calculate_overall_score(
        self,
        your_score: int,
        positioning: Dict[str, Any],
        threats: List[Dict[str, Any]],
        market_gaps: List[Dict[str, Any]]
    ) -> int:
        """Calculate overall strategic score"""
        
        # Base: your digital score
        score = your_score * 0.4
        
        # Positioning score
        competitive_score = positioning.get('competitive_score', 50)
        score += competitive_score * 0.3
        
        # Penalty for threats
        critical_threats = sum(1 for t in threats if t.get('severity') == 'critical')
        high_threats = sum(1 for t in threats if t.get('severity') == 'high')
        threat_penalty = (critical_threats * 10) + (high_threats * 5)
        score -= threat_penalty
        
        # Bonus for opportunities
        high_potential_gaps = sum(1 for g in market_gaps if g.get('potential') == 'high')
        opportunity_bonus = min(high_potential_gaps * 5, 15)
        score += opportunity_bonus
        
        return max(0, min(100, int(score)))
    
    def _create_strategic_summary(
        self,
        positioning: Dict[str, Any],
        recommendations: List[Dict[str, Any]],
        creative_boldness: Dict[str, Any],
        overall_score: int
    ) -> Dict[str, Any]:
        """Create strategic summary"""
        
        # Get top 3 priorities
        priorities = []
        for rec in recommendations[:3]:
            priorities.append({
                'title': rec.get('title', rec.get('recommendation', '')),
                'priority': rec.get('priority', 'medium'),
                'impact': rec.get('impact', 'medium')
            })
        
        return {
            'overall_score': overall_score,
            'positioning_quadrant': positioning.get('positioning_quadrant', 'Unknown'),
            'competitive_score': positioning.get('competitive_score', 0),
            'creative_boldness_score': creative_boldness.get('creative_boldness_score', 0),
            'top_priorities': priorities,
            'recommendation_count': len(recommendations)
        }
