"""
Growth Engine 2.0 - Strategist Agent
🎯 "The Strategic Advisor" - Synteesi ja priorisointi
"""

import logging
from typing import Dict, Any, List

from .base_agent import BaseAgent
from .types import (
    AnalysisContext,
    AgentPriority,
    InsightType
)

logger = logging.getLogger(__name__)


STRATEGIST_TASKS = {
    "calculating_scores": {"fi": "Lasketaan kokonaispistemääriä...", "en": "Calculating composite scores..."},
    "analyzing_position": {"fi": "Analysoidaan kilpailuasemaa...", "en": "Analyzing competitive position..."},
    "prioritizing": {"fi": "Priorisoidaan strategisesti...", "en": "Prioritizing strategically..."},
    "compiling_insights": {"fi": "Kootaan avainlöydökset...", "en": "Compiling key insights..."},
    "generating_summary": {"fi": "Generoidaan yhteenveto...", "en": "Generating executive summary..."},
}

MATURITY_LEVELS = {
    "advanced": {"fi": "Edistyksellinen", "en": "Advanced"},
    "developed": {"fi": "Kehittynyt", "en": "Developed"},
    "average": {"fi": "Keskitaso", "en": "Average"},
    "developing": {"fi": "Kehittyvä", "en": "Developing"},
    "beginner": {"fi": "Aloitteleva", "en": "Beginner"},
}

POSITIONS = {
    "leader": {"fi": "🏆 Markkinajohtaja", "en": "🏆 Market Leader"},
    "challenger": {"fi": "🥈 Haastaja", "en": "🥈 Challenger"},
    "middle": {"fi": "🎯 Keskikastia", "en": "🎯 Middle of pack"},
    "behind": {"fi": "⚠️ Jälkijunassa", "en": "⚠️ Falling behind"},
}


class StrategistAgent(BaseAgent):
    """
    🎯 Strategist Agent - Strateginen neuvonantaja
    """
    
    def __init__(self):
        super().__init__(
            agent_id="strategist",
            name="Strategist",
            role="Strateginen neuvonantaja",
            avatar="🎯",
            personality="Viisas ja kauaskatseinen strategi"
        )
        self.dependencies = ['scout', 'analyst', 'guardian', 'prospector']
    
    def _task(self, key: str) -> str:
        return STRATEGIST_TASKS.get(key, {}).get(self._language, key)
    
    def _maturity(self, key: str) -> str:
        return MATURITY_LEVELS.get(key, {}).get(self._language, key)
    
    def _position(self, key: str) -> str:
        return POSITIONS.get(key, {}).get(self._language, key)
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        analyst_results = self.get_dependency_results(context, 'analyst')
        guardian_results = self.get_dependency_results(context, 'guardian')
        prospector_results = self.get_dependency_results(context, 'prospector')
        
        self._emit_insight(
            self._t("strategist.starting"),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        self._update_progress(20, self._task("calculating_scores"))
        
        # 1. Laske kokonaispistemäärät
        composite_scores = self._calculate_composite_scores(
            analyst_results,
            guardian_results,
            prospector_results
        )
        
        overall_score = composite_scores.get('overall', 50)
        maturity_level = self._get_maturity_level(overall_score)
        
        self._emit_insight(
            self._t("strategist.overall_score", score=overall_score, level=maturity_level),
            priority=AgentPriority.HIGH,
            insight_type=InsightType.FINDING,
            data={'overall_score': overall_score, 'level': maturity_level}
        )
        
        self._update_progress(35, self._task("analyzing_position"))
        
        # 2. Analysoi kilpailuasema
        competitive_position = self._analyze_competitive_position(
            analyst_results.get('benchmark', {}) if analyst_results else {}
        )
        
        self._emit_insight(
            self._t("strategist.position", position=competitive_position.get('label', '')),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data=competitive_position
        )
        
        self._update_progress(50, self._task("prioritizing"))
        
        # 3. Priorisoi strategisesti
        strategic_priorities = self._prioritize_strategically(
            guardian_results.get('priority_actions', []) if guardian_results else [],
            prospector_results.get('growth_opportunities', []) if prospector_results else [],
            overall_score
        )
        
        for idx, priority in enumerate(strategic_priorities[:3]):
            self._emit_insight(
                self._t("strategist.priority", idx=idx+1, title=priority.get('title', '')),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.RECOMMENDATION,
                data=priority
            )
        
        self._update_progress(65, self._task("compiling_insights"))
        
        # 4. Koosta avainlöydökset
        key_insights = self._compile_key_insights(
            analyst_results,
            guardian_results,
            prospector_results
        )
        
        self._update_progress(80, self._task("generating_summary"))
        
        # 5. Generoi executive summary
        executive_summary = self._generate_executive_summary(
            overall_score,
            maturity_level,
            competitive_position,
            strategic_priorities,
            guardian_results,
            prospector_results
        )
        
        # 6. Generoi suositukset
        recommendations = self._generate_recommendations(
            strategic_priorities,
            overall_score
        )
        
        # Final summary insight
        threats_count = len(guardian_results.get('threats', [])) if guardian_results else 0
        opps_count = len(prospector_results.get('growth_opportunities', [])) if prospector_results else 0
        
        self._emit_insight(
            self._t("strategist.complete",
                   threats=threats_count,
                   opportunities=opps_count,
                   priorities=len(strategic_priorities)),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        return {
            'executive_summary': executive_summary,
            'overall_score': overall_score,
            'composite_scores': composite_scores,
            'maturity_level': maturity_level,
            'strategic_priorities': strategic_priorities,
            'key_insights': key_insights,
            'competitive_position': competitive_position,
            'recommendations': recommendations
        }
    
    def _calculate_composite_scores(
        self,
        analyst_results: Dict[str, Any],
        guardian_results: Dict[str, Any],
        prospector_results: Dict[str, Any]
    ) -> Dict[str, int]:
        scores = {}
        
        if analyst_results:
            cat_comp = analyst_results.get('category_comparison', {})
            for cat in ['seo', 'performance', 'security', 'content', 'ux']:
                scores[cat] = cat_comp.get(cat, {}).get('your_score', 50)
        
        # Security posture from Guardian
        if guardian_results:
            scores['security_posture'] = guardian_results.get('rasm_score', 50)
        
        # Growth potential from Prospector
        if prospector_results:
            opps = prospector_results.get('growth_opportunities', [])
            high_impact = len([o for o in opps if o.get('impact') == 'high'])
            scores['growth_potential'] = min(100, 40 + high_impact * 15)
        
        # Competitive edge from benchmark
        if analyst_results:
            benchmark = analyst_results.get('benchmark', {})
            your_score = benchmark.get('your_score', 50)
            avg_comp = benchmark.get('avg_competitor_score', 50)
            edge = your_score - avg_comp
            scores['competitive_edge'] = max(0, min(100, 50 + edge))
        
        # Calculate weighted overall
        weights = {
            'seo': 0.20,
            'performance': 0.15,
            'security': 0.15,
            'content': 0.15,
            'ux': 0.15,
            'security_posture': 0.10,
            'competitive_edge': 0.10
        }
        
        weighted_sum = 0
        weight_total = 0
        
        for key, weight in weights.items():
            if key in scores:
                weighted_sum += scores[key] * weight
                weight_total += weight
        
        if weight_total > 0:
            scores['overall'] = round(weighted_sum / weight_total)
        else:
            scores['overall'] = 50
        
        return scores
    
    def _get_maturity_level(self, score: int) -> str:
        if score >= 80:
            return self._maturity("advanced")
        elif score >= 65:
            return self._maturity("developed")
        elif score >= 50:
            return self._maturity("average")
        elif score >= 35:
            return self._maturity("developing")
        else:
            return self._maturity("beginner")
    
    def _analyze_competitive_position(self, benchmark: Dict[str, Any]) -> Dict[str, Any]:
        your_position = benchmark.get('your_position', 1)
        total = benchmark.get('total_analyzed', 1)
        
        if total <= 1:
            return {
                'position': 'unknown',
                'label': {'fi': 'Ei vertailutietoja', 'en': 'No comparison data'}.get(self._language),
                'rank': 1,
                'total': 1
            }
        
        percentile = (total - your_position + 1) / total
        
        if your_position == 1:
            position_key = 'leader'
        elif percentile >= 0.66:
            position_key = 'challenger'
        elif percentile >= 0.33:
            position_key = 'middle'
        else:
            position_key = 'behind'
        
        return {
            'position': position_key,
            'label': self._position(position_key),
            'rank': your_position,
            'total': total,
            'percentile': round(percentile * 100)
        }
    
    def _prioritize_strategically(
        self,
        guardian_actions: List[Dict[str, Any]],
        growth_opportunities: List[Dict[str, Any]],
        overall_score: int
    ) -> List[Dict[str, Any]]:
        all_priorities = []
        
        # Determine weight balance
        defense_weight = 1.5 if overall_score < 50 else 1.0
        growth_weight = 1.5 if overall_score >= 60 else 1.0
        
        # Add guardian actions
        for action in guardian_actions:
            roi = action.get('roi_score', 50)
            strategic_score = roi * defense_weight
            all_priorities.append({
                'source': 'defense',
                'title': action.get('title', ''),
                'category': action.get('category', ''),
                'impact': action.get('impact', 'medium'),
                'effort': action.get('effort', 'medium'),
                'strategic_score': strategic_score,
                'type': 'risk_mitigation'
            })
        
        # Add growth opportunities
        for opp in growth_opportunities:
            impact_scores = {'high': 80, 'medium': 50, 'low': 30}
            effort_scores = {'low': 80, 'medium': 50, 'high': 30}
            
            impact = impact_scores.get(opp.get('impact', 'medium'), 50)
            effort = effort_scores.get(opp.get('effort', 'medium'), 50)
            roi = (impact + effort) / 2
            strategic_score = roi * growth_weight
            
            all_priorities.append({
                'source': 'growth',
                'title': opp.get('title', ''),
                'category': opp.get('category', ''),
                'impact': opp.get('impact', 'medium'),
                'effort': opp.get('effort', 'medium'),
                'strategic_score': strategic_score,
                'type': 'growth_opportunity'
            })
        
        # Sort by strategic score
        all_priorities.sort(key=lambda x: x.get('strategic_score', 0), reverse=True)
        
        return all_priorities[:10]
    
    def _compile_key_insights(
        self,
        analyst_results: Dict[str, Any],
        guardian_results: Dict[str, Any],
        prospector_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        insights = []
        
        # From analyst
        if analyst_results:
            benchmark = analyst_results.get('benchmark', {})
            insights.append({
                'source': 'analyst',
                'type': 'benchmark',
                'data': benchmark
            })
        
        # From guardian
        if guardian_results:
            insights.append({
                'source': 'guardian',
                'type': 'risk',
                'threat_count': len(guardian_results.get('threats', [])),
                'rasm_score': guardian_results.get('rasm_score', 0)
            })
        
        # From prospector
        if prospector_results:
            insights.append({
                'source': 'prospector',
                'type': 'opportunity',
                'opportunity_count': len(prospector_results.get('growth_opportunities', [])),
                'quick_win_count': len(prospector_results.get('quick_wins', []))
            })
        
        return insights
    
    def _generate_executive_summary(
        self,
        overall_score: int,
        maturity_level: str,
        competitive_position: Dict[str, Any],
        strategic_priorities: List[Dict[str, Any]],
        guardian_results: Dict[str, Any],
        prospector_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Strengths
        strengths = []
        if competitive_position.get('position') in ['leader', 'challenger']:
            strengths.append({'fi': 'Vahva kilpailuasema', 'en': 'Strong competitive position'}.get(self._language))
        
        if guardian_results and guardian_results.get('rasm_score', 0) > 70:
            strengths.append({'fi': 'Hyvä tietoturvataso', 'en': 'Good security posture'}.get(self._language))
        
        # Weaknesses
        weaknesses = []
        if guardian_results:
            for threat in guardian_results.get('threats', [])[:2]:
                weaknesses.append(threat.get('title', ''))
        
        # Top priorities
        top_priorities = [p.get('title', '') for p in strategic_priorities[:3]]
        
        return {
            'overall_score': overall_score,
            'maturity_level': maturity_level,
            'position': competitive_position.get('label', ''),
            'strengths': strengths,
            'weaknesses': weaknesses,
            'top_priorities': top_priorities
        }
    
    def _generate_recommendations(
        self,
        priorities: List[Dict[str, Any]],
        overall_score: int
    ) -> Dict[str, List[str]]:
        immediate = []
        short_term = []
        medium_term = []
        
        for idx, p in enumerate(priorities):
            title = p.get('title', '')
            effort = p.get('effort', 'medium')
            
            if effort == 'low' and len(immediate) < 3:
                immediate.append(title)
            elif effort == 'medium' and len(short_term) < 3:
                short_term.append(title)
            elif len(medium_term) < 3:
                medium_term.append(title)
        
        return {
            'immediate': immediate,  # 1-2 weeks
            'short_term': short_term,  # 1-3 months
            'medium_term': medium_term  # 3-6 months
        }
