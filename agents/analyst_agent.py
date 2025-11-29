"""
Growth Engine 2.0 - Analyst Agent
The Data Scientist - Deep analysis and benchmark comparison
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent
from .types import (
    AnalysisContext,
    AgentPriority,
    InsightType
)

logger = logging.getLogger(__name__)


ANALYST_TASKS = {
    "analyzing_target": {"fi": "Analysoimassa kohdesivustoa...", "en": "Analyzing target website..."},
    "analyzing_competitors": {"fi": "Analysoimassa kilpailijoita...", "en": "Analyzing competitors..."},
    "calculating_benchmark": {"fi": "Laskemassa benchmark-vertailua...", "en": "Calculating benchmark comparison..."},
    "comparing_categories": {"fi": "Vertailemassa kategorioita...", "en": "Comparing categories..."},
    "finalizing": {"fi": "Viimeistellaan analyysia...", "en": "Finalizing analysis..."},
}


class AnalystAgent(BaseAgent):
    """Analyst Agent - Data Scientist"""
    
    def __init__(self):
        super().__init__(
            agent_id="analyst",
            name="Analyst",
            role="Data-analyytikko",
            avatar="A",
            personality="Tarkka ja datavetoinen analyytikko"
        )
        self.dependencies = ['scout']
    
    def _task(self, key: str) -> str:
        return ANALYST_TASKS.get(key, {}).get(self._language, key)
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        from main import _perform_comprehensive_analysis_internal
        
        scout_results = self.get_dependency_results(context, 'scout')
        
        self._update_progress(10, self._task("analyzing_target"))
        
        self._emit_insight(
            self._t("analyst.starting"),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # 1. Analysoi kohdesivusto
        try:
            your_analysis = await _perform_comprehensive_analysis_internal(
                context.url,
                use_playwright=True,
                language=context.language
            )
            
            basic = your_analysis.get('basic', {})
            your_analysis['final_score'] = basic.get('digital_maturity_score', 0) or your_analysis.get('digital_maturity_score', 0)
            your_score = your_analysis.get('final_score', 0)
            
            self._emit_insight(
                self._t("analyst.score", score=your_score),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING,
                data={'score': your_score}
            )
            
            # Mobile check - simple
            breakdown = basic.get('score_breakdown', {})
            mobile_score = breakdown.get('mobile', 0)
            
            if mobile_score >= 9:
                self._emit_insight(
                    self._t("analyst.mobile_ok"),
                    priority=AgentPriority.LOW,
                    insight_type=InsightType.FINDING
                )
            else:
                self._emit_insight(
                    self._t("analyst.mobile_bad"),
                    priority=AgentPriority.HIGH,
                    insight_type=InsightType.THREAT
                )
                
        except Exception as e:
            logger.error(f"[Analyst] Target analysis error: {e}")
            self._emit_insight(
                self._t("analyst.analysis_failed", error=str(e)),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
            your_analysis = {'final_score': 0}
        
        # 2. Analysoi kilpailijat
        self._update_progress(40, self._task("analyzing_competitors"))
        
        competitor_analyses = []
        validated_competitors = scout_results.get('validated_competitors', []) if scout_results else []
        
        for i, comp in enumerate(validated_competitors):
            comp_url = comp if isinstance(comp, str) else comp.get('url', '')
            if not comp_url:
                continue
                
            try:
                self._emit_insight(
                    self._t("analyst.analyzing_competitor", url=comp_url),
                    priority=AgentPriority.LOW,
                    insight_type=InsightType.FINDING
                )
                
                comp_analysis = await _perform_comprehensive_analysis_internal(
                    comp_url,
                    use_playwright=True,
                    language=context.language
                )
                
                comp_basic = comp_analysis.get('basic', {})
                comp_analysis['final_score'] = comp_basic.get('digital_maturity_score', 0) or comp_analysis.get('digital_maturity_score', 0)
                comp_analysis['url'] = comp_url
                competitor_analyses.append(comp_analysis)
                
            except Exception as e:
                logger.warning(f"[Analyst] Competitor {comp_url} analysis failed: {e}")
        
        # 3. Laske benchmark
        self._update_progress(70, self._task("calculating_benchmark"))
        
        your_score = your_analysis.get('final_score', 0)
        comp_scores = [c.get('final_score', 0) for c in competitor_analyses if c.get('final_score', 0) > 0]
        
        if comp_scores:
            avg_score = sum(comp_scores) / len(comp_scores)
            max_score = max(comp_scores)
            min_score = min(comp_scores)
        else:
            avg_score = your_score
            max_score = your_score
            min_score = your_score
        
        all_scores = [your_score] + comp_scores
        all_scores_sorted = sorted(all_scores, reverse=True)
        your_ranking = all_scores_sorted.index(your_score) + 1
        total_in_ranking = len(all_scores_sorted)
        
        benchmark = {
            'your_score': your_score,
            'competitor_avg': round(avg_score, 1),
            'competitor_max': max_score,
            'competitor_min': min_score,
            'your_ranking': your_ranking,
            'total_competitors': total_in_ranking,
            'gap_to_leader': max_score - your_score if max_score > your_score else 0,
            'lead_over_avg': your_score - avg_score if your_score > avg_score else 0
        }
        
        # Emit ranking insight
        if your_ranking == 1:
            self._emit_insight(
                self._t("analyst.ranking_leader", total=total_in_ranking),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.OPPORTUNITY
            )
        elif your_ranking <= 3:
            self._emit_insight(
                self._t("analyst.ranking_top3", rank=your_ranking, total=total_in_ranking),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
        else:
            self._emit_insight(
                self._t("analyst.ranking_behind", rank=your_ranking, total=total_in_ranking, gap=benchmark['gap_to_leader']),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
        
        # 4. Kategoria-vertailu
        self._update_progress(85, self._task("comparing_categories"))
        
        categories = ['security', 'seo_basics', 'content', 'technical', 'mobile', 'social']
        category_comparison = {}
        
        your_breakdown = your_analysis.get('basic', {}).get('score_breakdown', {})
        
        for cat in categories:
            your_cat_score = your_breakdown.get(cat, 0)
            comp_cat_scores = []
            
            for comp in competitor_analyses:
                comp_breakdown = comp.get('basic', {}).get('score_breakdown', {})
                comp_cat_scores.append(comp_breakdown.get(cat, 0))
            
            if comp_cat_scores:
                avg_cat = sum(comp_cat_scores) / len(comp_cat_scores)
                max_cat = max(comp_cat_scores)
            else:
                avg_cat = your_cat_score
                max_cat = your_cat_score
            
            category_comparison[cat] = {
                'your_score': your_cat_score,
                'competitor_avg': round(avg_cat, 1),
                'competitor_max': max_cat,
                'difference': round(your_cat_score - avg_cat, 1),
                'status': 'leading' if your_cat_score > avg_cat else ('behind' if your_cat_score < avg_cat else 'equal')
            }
        
        # Find strengths and weaknesses
        strengths = [cat for cat, data in category_comparison.items() if data['status'] == 'leading']
        weaknesses = [cat for cat, data in category_comparison.items() if data['status'] == 'behind']
        
        if strengths:
            self._emit_insight(
                self._t("analyst.strengths", categories=", ".join(strengths)),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.OPPORTUNITY
            )
        
        if weaknesses:
            self._emit_insight(
                self._t("analyst.weaknesses", categories=", ".join(weaknesses)),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
        
        self._update_progress(100, self._task("finalizing"))
        
        return {
            'your_analysis': your_analysis,
            'your_score': your_score,
            'competitor_analyses': competitor_analyses,
            'benchmark': benchmark,
            'category_comparison': category_comparison,
            'your_ranking': your_ranking,
            'total_competitors': total_in_ranking
        }
