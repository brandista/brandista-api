
Growth Engine 2.0 - Analyst Agent
📊 "The Data Scientist" - Syvällinen analyysi ja benchmark-vertailu
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
    "finalizing": {"fi": "Viimeistellään analyysiä...", "en": "Finalizing analysis..."},
}


class AnalystAgent(BaseAgent):
    """
    📊 Analyst Agent - Data-analyytikko
    """
    
    def __init__(self):
        super().__init__(
            agent_id="analyst",
            name="Analyst",
            role="Data-analyytikko",
            avatar="📊",
            personality="Tarkka ja datavetoinen analyytikko"
        )
        self.dependencies = ['scout']
    
    def _task(self, key: str) -> str:
        return ANALYST_TASKS.get(key, {}).get(self._language, key)
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        from main import _perform_comprehensive_analysis_internal
        
        scout_results = self.get_dependency_results(context, 'scout')
        competitor_urls = scout_results.get('competitor_urls', []) if scout_results else []
        
        self._update_progress(15, self._task("analyzing_target"))
        
        self._emit_insight(
            self._t("analyst.starting"),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # 1. Analysoi kohdesivusto
        try:
            your_analysis = await _perform_comprehensive_analysis_internal(
                context.url,
                language=context.language
            )
            
            # Map digital_maturity_score to final_score for consistency
            # Score is nested inside basic_analysis, not at root level!
            basic = your_analysis.get('basic_analysis', {})
            your_analysis['final_score'] = basic.get('digital_maturity_score', 0) or your_analysis.get('digital_maturity_score', 0)
            your_score = your_analysis.get('final_score', 0)
            
            self._emit_insight(
                self._t("analyst.score", score=your_score),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING,
                data={'score': your_score}
            )
            
            # Mobiili-insight - tarkista useita kenttiä
            basic = your_analysis.get('basic', {})
            
            # 1. Tarkista mobile_score_raw (0-100 scale)
            mobile_score_raw = basic.get('mobile_score_raw', 0)
            
            # 2. Tarkista responsive_design.score
            responsive = basic.get('responsive_design', {})
            responsive_score = responsive.get('score', 0) if isinstance(responsive, dict) else 0
            
            # 3. Tarkista has_viewport
            has_viewport = basic.get('has_viewport', basic.get('has_mobile_viewport', False))
            
            # 4. Fallback: breakdown.mobile (0-15 scale -> convert to 0-100)
            breakdown = basic.get('score_breakdown', {})
            mobile_weighted = breakdown.get('mobile', 0)
            mobile_from_breakdown = int((mobile_weighted / 15) * 100) if mobile_weighted else 0
            
            # Käytä parasta saatavilla olevaa arvoa
            mobile_score = mobile_score_raw or responsive_score or mobile_from_breakdown
            
            # Mobile on OK jos score >= 60 JA viewport löytyy
            mobile_ok = mobile_score >= 60 and has_viewport
            
            logger.info(f"[Analyst] Mobile check: score_raw={mobile_score_raw}, responsive={responsive_score}, breakdown={mobile_from_breakdown}, viewport={has_viewport} -> OK={mobile_ok}")
            
            if mobile_ok:
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
        competitor_analyses = []
        
        if not competitor_urls:
            self._emit_insight(
                self._t("analyst.no_competitors"),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
        else:
            self._update_progress(35, self._task("analyzing_competitors"))
            
            self._emit_insight(
                self._t("analyst.analyzing_competitors", count=len(competitor_urls)),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING
            )
            
            # Analysoi rinnakkain
            tasks = []
            for url in competitor_urls[:5]:
                tasks.append(self._analyze_competitor(url, context.language))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    self._emit_insight(
                        self._t("analyst.competitor_failed", idx=idx+1),
                        priority=AgentPriority.LOW,
                        insight_type=InsightType.FINDING
                    )
                    continue
                    
                if result:
                    competitor_analyses.append(result)
                    
                    comp_score = result.get('final_score', 0)
                    comp_name = result.get('domain', f'Competitor {idx+1}')
                    diff = comp_score - your_analysis.get('final_score', 0)
                    
                    if diff > 10:
                        self._emit_insight(
                            self._t("analyst.competitor_stronger", 
                                   name=comp_name, score=comp_score, diff=f"+{diff}"),
                            priority=AgentPriority.HIGH,
                            insight_type=InsightType.THREAT,
                            data={'competitor': comp_name, 'score': comp_score, 'diff': diff}
                        )
                    elif diff < -10:
                        self._emit_insight(
                            self._t("analyst.competitor_weaker",
                                   name=comp_name, score=comp_score, diff=str(diff)),
                            priority=AgentPriority.MEDIUM,
                            insight_type=InsightType.OPPORTUNITY,
                            data={'competitor': comp_name, 'score': comp_score, 'diff': diff}
                        )
                    else:
                        self._emit_insight(
                            self._t("analyst.competitor_equal",
                                   name=comp_name, score=comp_score),
                            priority=AgentPriority.LOW,
                            insight_type=InsightType.FINDING,
                            data={'competitor': comp_name, 'score': comp_score}
                        )
                
                self._update_progress(35 + (idx + 1) * 10, f"Analysoitu {idx + 1}/{len(competitor_urls)}...")
        
        # 3. Laske benchmark
        self._update_progress(75, self._task("calculating_benchmark"))
        
        benchmark = self._calculate_benchmark(your_analysis, competitor_analyses)
        
        # Benchmark insight
        your_position = benchmark.get('your_position', 1)
        total = benchmark.get('total_analyzed', 1)
        avg = benchmark.get('avg_competitor_score', 0)
        your_score = benchmark.get('your_score', 0)
        
        if your_position <= (total / 2):
            self._emit_insight(
                self._t("analyst.benchmark_ahead",
                       position=your_position, total=total, avg=avg, score=your_score),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING,
                data=benchmark
            )
        else:
            self._emit_insight(
                self._t("analyst.benchmark_behind",
                       position=your_position, avg=avg, score=your_score),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT,
                data=benchmark
            )
        
        # 4. Vertaa kategorioittain
        self._update_progress(85, self._task("comparing_categories"))
        
        category_comparison = self._compare_categories(your_analysis, competitor_analyses)
        
        return {
            'your_analysis': your_analysis,
            'competitor_analyses': competitor_analyses,
            'benchmark': benchmark,
            'category_comparison': category_comparison,
            'your_score': your_analysis.get('final_score', 0)
        }
    
    async def _analyze_competitor(self, url: str, language: str) -> Optional[Dict[str, Any]]:
        from main import _perform_comprehensive_analysis_internal, get_domain_from_url
        
        try:
            analysis = await _perform_comprehensive_analysis_internal(url, language=language)
            analysis['domain'] = get_domain_from_url(url)
            analysis['url'] = url
            # Map digital_maturity_score to final_score for consistency
            # Score is nested inside basic_analysis, not at root level!
            basic = analysis.get('basic_analysis', {})
            analysis['final_score'] = basic.get('digital_maturity_score', 0) or analysis.get('digital_maturity_score', 0)
            return analysis
        except Exception as e:
            logger.error(f"[Analyst] Competitor analysis failed for {url}: {e}")
            return None
    
    def _calculate_benchmark(
        self,
        your_analysis: Dict[str, Any],
        competitor_analyses: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        your_score = your_analysis.get('final_score', 0)
        
        if not competitor_analyses:
            return {
                'your_score': your_score,
                'avg_competitor_score': 0,
                'max_competitor_score': 0,
                'min_competitor_score': 0,
                'your_position': 1,
                'total_analyzed': 1
            }
        
        comp_scores = [c.get('final_score', 0) for c in competitor_analyses]
        
        all_scores = [your_score] + comp_scores
        all_scores.sort(reverse=True)
        your_position = all_scores.index(your_score) + 1
        
        return {
            'your_score': your_score,
            'avg_competitor_score': round(sum(comp_scores) / len(comp_scores)),
            'max_competitor_score': max(comp_scores),
            'min_competitor_score': min(comp_scores),
            'your_position': your_position,
            'total_analyzed': len(all_scores)
        }
    
    def _compare_categories(
        self,
        your_analysis: Dict[str, Any],
        competitor_analyses: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        categories = ['seo', 'performance', 'security', 'content', 'ux']
        comparison = {}
        
        for cat in categories:
            your_cat_score = self._extract_category_score(your_analysis, cat)
            
            if competitor_analyses:
                comp_cat_scores = [
                    self._extract_category_score(c, cat) 
                    for c in competitor_analyses
                ]
                avg_comp = sum(comp_cat_scores) / len(comp_cat_scores) if comp_cat_scores else 0
            else:
                avg_comp = 0
            
            diff = your_cat_score - avg_comp
            
            comparison[cat] = {
                'your_score': your_cat_score,
                'competitor_avg': round(avg_comp),
                'difference': round(diff),
                'status': 'ahead' if diff > 5 else 'behind' if diff < -5 else 'even'
            }
        
        return comparison
    
    def _extract_category_score(self, analysis: Dict[str, Any], category: str) -> int:
        if category == 'seo':
            basic = analysis.get('basic', {})
            seo_score = 0
            if basic.get('title'):
                seo_score += 25
            if basic.get('meta_description'):
                seo_score += 25
            if basic.get('h1_text'):
                seo_score += 25
            if basic.get('canonical'):
                seo_score += 25
            return seo_score
            
        elif category == 'performance':
            tech = analysis.get('technical', {})
            return tech.get('performance_score', 50)
            
        elif category == 'security':
            tech = analysis.get('technical', {})
            security = 50
            if tech.get('has_ssl'):
                security += 30
            if tech.get('security_headers', {}).get('x-frame-options'):
                security += 10
            if tech.get('security_headers', {}).get('content-security-policy'):
                security += 10
            return min(security, 100)
            
        elif category == 'content':
            content = analysis.get('content', {})
            return content.get('quality_score', 50)
            
        elif category == 'ux':
            basic = analysis.get('basic', {})
            ux_score = 50
            if basic.get('mobile_ready') in ['Kyllä', 'Yes', True]:
                ux_score += 25
            if basic.get('has_clear_cta'):
                ux_score += 25
            return min(ux_score, 100)
        
        return 50
