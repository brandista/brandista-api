"""
Growth Engine 2.0 - Analyst Agent
📊 "The Data Scientist" - Deep analysis of all websites
Uses: _perform_comprehensive_analysis_internal()
"""

import logging
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent
from .types import AnalysisContext, AgentPriority, InsightType

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    """
    📊 Analyst Agent - Data Scientist
    
    Responsibilities:
    - Perform comprehensive analysis on your website
    - Analyze all competitor websites
    - Calculate digital maturity scores
    - Build category comparisons
    - Create benchmark data
    """
    
    def __init__(self):
        super().__init__(
            agent_id="analyst",
            name="Analyst",
            role="Data Scientist",
            avatar="📊",
            personality="Precise, data-driven researcher who loves numbers"
        )
        self.dependencies = ['scout']
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """Perform comprehensive analysis"""
        
        from main import _perform_comprehensive_analysis_internal, get_domain_from_url
        
        scout_results = self.get_dependency_results(context, 'scout')
        
        if not scout_results:
            self._emit_insight(
                "⚠️ No Scout data — running limited analysis",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
            competitor_urls = context.competitor_urls
        else:
            competitor_urls = scout_results.get('competitor_urls', [])
        
        self._emit_insight(
            "📊 Starting deep analysis — crunching the numbers...",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # 1. Analyze YOUR website
        self._update_progress(10, "Analyzing your website...")
        
        try:
            your_analysis = await _perform_comprehensive_analysis_internal(
                url=context.url,
                language='en',
                user=context.user
            )
            
            your_score = your_analysis.get('basic_analysis', {}).get('digital_maturity_score', 0)
            company = your_analysis.get('basic_analysis', {}).get('company', 'Your company')
            
            self._emit_insight(
                f"✅ Your score: {your_score}/100 — let's see how you stack up",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.METRIC,
                data={'your_score': your_score, 'company': company}
            )
            
        except Exception as e:
            logger.error(f"[Analyst] Your analysis failed: {e}")
            self._emit_insight(
                f"❌ Failed to analyze your website: {str(e)}",
                priority=AgentPriority.CRITICAL,
                insight_type=InsightType.THREAT
            )
            raise
        
        # 2. Analyze COMPETITORS
        self._update_progress(30, "Analyzing competitors...")
        
        competitor_analyses = []
        failed_count = 0
        
        total_competitors = len(competitor_urls)
        
        for idx, comp_url in enumerate(competitor_urls):
            progress = 30 + int((idx / max(total_competitors, 1)) * 50)
            self._update_progress(progress, f"Analyzing competitor {idx + 1}/{total_competitors}...")
            
            try:
                comp_analysis = await _perform_comprehensive_analysis_internal(
                    url=comp_url,
                    language='en',
                    user=context.user
                )
                
                comp_score = comp_analysis.get('basic_analysis', {}).get('digital_maturity_score', 0)
                comp_name = comp_analysis.get('basic_analysis', {}).get('company', get_domain_from_url(comp_url))
                
                comp_analysis['url'] = comp_url
                comp_analysis['name'] = comp_name
                comp_analysis['score'] = comp_score
                
                competitor_analyses.append(comp_analysis)
                
                # Compare to your score
                diff = comp_score - your_score
                if diff > 10:
                    emoji = "🔴"
                    status = f"+{diff} points ahead"
                elif diff < -10:
                    emoji = "🟢"
                    status = f"{abs(diff)} points behind"
                else:
                    emoji = "🟡"
                    status = "neck and neck"
                
                self._emit_insight(
                    f"{emoji} {comp_name}: {comp_score}/100 — {status}",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING,
                    data={'competitor': comp_name, 'score': comp_score, 'diff': diff}
                )
                
            except Exception as e:
                logger.error(f"[Analyst] Competitor analysis failed for {comp_url}: {e}")
                failed_count += 1
                continue
        
        if failed_count > 0:
            self._emit_insight(
                f"⚠️ {failed_count} competitor(s) couldn't be analyzed",
                priority=AgentPriority.LOW,
                insight_type=InsightType.FINDING
            )
        
        self._update_progress(85, "Building benchmark...")
        
        # 3. Calculate benchmark
        benchmark = self._calculate_benchmark(your_analysis, competitor_analyses)
        
        # 4. Category comparison
        category_comparison = self._build_category_comparison(your_analysis, competitor_analyses)
        
        # 5. Determine ranking
        all_scores = [your_score] + [c.get('score', 0) for c in competitor_analyses]
        all_scores.sort(reverse=True)
        your_rank = all_scores.index(your_score) + 1
        total = len(all_scores)
        
        if your_rank == 1:
            rank_msg = "🏆 You're #1 — leading the pack!"
            priority = AgentPriority.HIGH
        elif your_rank <= 2:
            rank_msg = f"📊 Ranking #{your_rank} — room to climb"
            priority = AgentPriority.MEDIUM
        else:
            rank_msg = f"📊 Ranking #{your_rank}/{total} — time to level up"
            priority = AgentPriority.HIGH
        
        self._emit_insight(
            rank_msg,
            priority=priority,
            insight_type=InsightType.METRIC,
            data={'rank': your_rank, 'total': total, 'your_score': your_score}
        )
        
        self._update_progress(95, "Analysis complete!")
        
        self._emit_insight(
            f"✅ Deep analysis complete: {len(competitor_analyses) + 1} sites analyzed, "
            f"benchmark avg: {benchmark.get('avg_score', 0):.0f}/100",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data={'analyzed_count': len(competitor_analyses) + 1}
        )
        
        return {
            'your_analysis': your_analysis,
            'competitor_analyses': competitor_analyses,
            'benchmark': benchmark,
            'category_comparison': category_comparison,
            'your_score': your_score,
            'your_rank': your_rank,
            'total_analyzed': total
        }
    
    def _calculate_benchmark(
        self, 
        your_analysis: Dict[str, Any], 
        competitor_analyses: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate benchmark statistics"""
        
        all_scores = [your_analysis.get('basic_analysis', {}).get('digital_maturity_score', 0)]
        all_scores.extend([c.get('score', 0) for c in competitor_analyses])
        
        if not all_scores:
            return {'avg_score': 0, 'max_score': 0, 'min_score': 0}
        
        return {
            'avg_score': sum(all_scores) / len(all_scores),
            'max_score': max(all_scores),
            'min_score': min(all_scores),
            'your_score': all_scores[0],
            'competitor_avg': sum(all_scores[1:]) / len(all_scores[1:]) if len(all_scores) > 1 else 0
        }
    
    def _build_category_comparison(
        self, 
        your_analysis: Dict[str, Any], 
        competitor_analyses: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build category-by-category comparison"""
        
        your_breakdown = your_analysis.get('basic_analysis', {}).get('score_breakdown', {})
        
        categories = ['seo', 'mobile', 'performance', 'security', 'content']
        comparison = {}
        
        for cat in categories:
            your_cat_score = your_breakdown.get(cat, 50)
            
            comp_scores = []
            for comp in competitor_analyses:
                comp_breakdown = comp.get('basic_analysis', {}).get('score_breakdown', {})
                comp_scores.append(comp_breakdown.get(cat, 50))
            
            avg_comp = sum(comp_scores) / len(comp_scores) if comp_scores else 50
            
            comparison[cat] = {
                'your_score': your_cat_score,
                'competitor_avg': avg_comp,
                'diff': your_cat_score - avg_comp,
                'status': 'ahead' if your_cat_score > avg_comp else 'behind' if your_cat_score < avg_comp else 'even'
            }
        
        return comparison
