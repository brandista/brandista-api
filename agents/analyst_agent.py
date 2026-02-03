# -*- coding: utf-8 -*-
# Version: 2025-11-30-1000
# Changes: score_breakdown direct use, ai_visibility category, competitors_enriched passthrough, score_interpretation, top_findings
"""
Growth Engine 2.0 - Analyst Agent
"The Data Scientist" - Syvallinen analyysi ja benchmark-vertailu
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent
from .agent_types import (
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
    TRUE SWARM EDITION - Responds to analysis requests from other agents
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

        # ========================================================================
        # SWARM STATE - Active message handling
        # ========================================================================
        self._analysis_requests: List[Dict[str, Any]] = []

    def _get_subscribed_message_types(self):
        """Subscribe to requests"""
        from .communication import MessageType
        return [
            MessageType.REQUEST,
            MessageType.DATA
        ]

    async def _handle_request(self, message):
        """
        Handle analysis requests from other agents.
        ACTIVE HANDLING - provide on-demand analysis.
        """
        from .communication import MessageType
        from datetime import datetime

        request_type = message.payload.get('request_type', '')

        self._analysis_requests.append({
            'from': message.from_agent,
            'type': request_type,
            'timestamp': datetime.now().isoformat()
        })

        if request_type == 'category_detail':
            # Another agent wants detailed category analysis
            category = message.payload.get('category', '')
            url = message.payload.get('url', '')

            detail = self._get_category_detail(category, url)

            await self._send_message(
                to_agent=message.from_agent,
                message_type=MessageType.DATA,
                subject=f"Category detail: {category}",
                payload={'category': category, 'detail': detail}
            )
            logger.info(f"[Analyst] 📊 Sent category detail to {message.from_agent}")

        elif request_type == 'quick_benchmark':
            # Quick benchmark request
            url = message.payload.get('url', '')
            benchmark = await self._quick_benchmark(url)

            await self._send_message(
                to_agent=message.from_agent,
                message_type=MessageType.DATA,
                subject=f"Quick benchmark: {url[:30]}",
                payload={'benchmark': benchmark}
            )
            logger.info(f"[Analyst] 📊 Sent quick benchmark to {message.from_agent}")

    def _get_category_detail(self, category: str, url: str = '') -> Dict[str, Any]:
        """Get detailed analysis for a specific category"""
        return {
            'category': category,
            'analysis_available': True,
            'note': f"Detailed {category} analysis for {url or 'target'}"
        }

    async def _quick_benchmark(self, url: str) -> Dict[str, Any]:
        """Quick benchmark analysis"""
        return {
            'url': url,
            'quick_score': 50,
            'note': 'Quick benchmark - full analysis in execute()'
        }

    def _task(self, key: str) -> str:
        return ANALYST_TASKS.get(key, {}).get(self._language, key)
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        from main import _perform_comprehensive_analysis_internal
        
        scout_results = self.get_dependency_results(context, 'scout')
        competitor_urls = scout_results.get('competitor_urls', []) if scout_results else []
        
        # 🧠 NEW: Get historical score for comparison
        previous_score = None
        score_trend = None
        previous_date = None
        
        if context.unified_context:
            logger.info(f"[Analyst] 🧠 UNIFIED CONTEXT AVAILABLE - Checking score history")
            
            recent_analyses = context.unified_context.get('recent_analyses') or []
            if recent_analyses and len(recent_analyses) > 0:
                last_analysis = recent_analyses[0]
                previous_score = last_analysis.get('score', 0)
                previous_date = last_analysis.get('created_at', '')[:10]
                
                logger.info(f"[Analyst] Previous score: {previous_score}/100 ({previous_date})")
                
                self._emit_insight(
                    f"📈 Edellinen pisteesi: {previous_score}/100 ({previous_date})",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING,
                    data={'previous_score': previous_score, 'date': previous_date}
                )
            
            # Get overall trend from trends
            trends = context.unified_context.get('trends') or {}
            if trends and 'score_change' in trends:
                score_trend = trends['score_change']
                logger.info(f"[Analyst] Overall score trend: {score_trend:+.1f} points")
        
        self._update_progress(15, self._task("analyzing_target"))

        # Emit conversation to Guardian
        self._emit_conversation(
            'guardian',
            "Aloitan teknisen analyysin. Raportoin löydökseni sinulle pian.",
            "Starting technical analysis. Will report findings to you shortly."
        )

        self._emit_insight(
            self._t("analyst.starting"),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # 1. Analysoi kohdesivusto
        # Agents use "ai_enhanced" for full analysis (AI visibility + creative boldness)
        try:
            your_analysis = await _perform_comprehensive_analysis_internal(
                context.url,
                language=context.language,
                analysis_type="ai_enhanced"
            )
            
            # Map digital_maturity_score to final_score for consistency
            # Score is nested inside basic_analysis, not at root level!
            basic_analysis = your_analysis.get('basic_analysis', {})
            your_analysis['final_score'] = basic_analysis.get('digital_maturity_score', 0)
            your_score = your_analysis.get('final_score', 0)
            
            logger.info(f"[Analyst] basic_analysis keys: {list(basic_analysis.keys())}")
            logger.info(f"[Analyst] digital_maturity_score: {basic_analysis.get('digital_maturity_score', 'NOT FOUND')}")
            logger.info(f"[Analyst] final_score set to: {your_score}")
            
            # 🧠 NEW: Compare with previous score if available
            if previous_score is not None:
                score_change = your_score - previous_score
                if score_change > 0:
                    self._emit_insight(
                        f"🎉 Kehitystä! Pisteesi nousi {score_change:+.0f} pistettä (oli {previous_score}, nyt {your_score})",
                        priority=AgentPriority.HIGH,
                        insight_type=InsightType.FINDING,
                        data={'score_change': score_change, 'previous': previous_score, 'current': your_score}
                    )
                elif score_change < 0:
                    self._emit_insight(
                        f"⚠️ Huomio: Pisteesi laski {score_change:.0f} pistettä (oli {previous_score}, nyt {your_score})",
                        priority=AgentPriority.HIGH,
                        insight_type=InsightType.FINDING,
                        data={'score_change': score_change, 'previous': previous_score, 'current': your_score}
                    )
                else:
                    self._emit_insight(
                        f"➡️ Pisteesi pysyi samana: {your_score}/100",
                        priority=AgentPriority.MEDIUM,
                        insight_type=InsightType.FINDING,
                        data={'score_change': 0, 'score': your_score}
                    )
            else:
                # First analysis - just show score
                self._emit_insight(
                    self._t("analyst.score", score=your_score),
                    priority=AgentPriority.HIGH,
                    insight_type=InsightType.FINDING,
                    data={'score': your_score}
                )
            
            # Mobiili-insight - käytä basic_analysis
            breakdown = basic_analysis.get('score_breakdown', {})
            mobile_score = breakdown.get('mobile', 0)
            
            # mobile on 0-15 scale, 9+ = OK (60%)
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
        
        # Pass through competitors_enriched from Scout for Guardian
        competitors_enriched = scout_results.get('competitors_enriched', []) if scout_results else []
        
        # 5. NEW: Score interpretation (avoid false precision)
        your_score = your_analysis.get('final_score', 0)
        score_interpretation = self._interpret_score(your_score)
        
        # 6. NEW: Top 3 findings for Strategist & Planner
        top_findings = self._extract_top_findings(
            your_analysis, 
            category_comparison, 
            benchmark
        )
        
        return {
            'your_analysis': your_analysis,
            'competitor_analyses': competitor_analyses,
            'benchmark': benchmark,
            'category_comparison': category_comparison,
            'your_score': your_score,
            'competitors_enriched': competitors_enriched,
            # NEW: Interpretations to avoid false precision
            'score_interpretation': score_interpretation,
            'top_findings': top_findings
        }
    
    async def _analyze_competitor(self, url: str, language: str) -> Optional[Dict[str, Any]]:
        from main import _perform_comprehensive_analysis_internal, get_domain_from_url

        # Competitors use "comprehensive" level (no AI visibility/creative boldness)
        try:
            analysis = await _perform_comprehensive_analysis_internal(
                url,
                language=language,
                analysis_type="comprehensive"
            )
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
        # Added ai_visibility for 2025 - AI search readiness
        categories = ['seo', 'performance', 'security', 'content', 'ux', 'ai_visibility']
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
        """
        Extract category score from analysis data.
        
        Uses main.py score_breakdown directly when available, with fallback calculations.
        
        main.py score_breakdown categories (max points):
        - security: 15
        - seo_basics: 20
        - content: 20
        - technical: 15
        - mobile: 15
        - social: 10
        - performance: 5
        
        These are normalized to 0-100 scale for comparison.
        """
        basic = analysis.get('basic_analysis', analysis.get('basic', {}))
        breakdown = basic.get('score_breakdown', {})
        
        # Map our category names to score_breakdown keys
        category_map = {
            'seo': 'seo_basics',
            'security': 'security',
            'content': 'content',
            'performance': 'performance',
            'mobile': 'mobile',
            'technical': 'technical',
            'ux': 'mobile',  # UX maps to mobile (closest proxy)
        }
        
        # Max points per category in main.py
        max_points = {
            'seo_basics': 20,
            'security': 15,
            'content': 20,
            'technical': 15,
            'mobile': 15,
            'social': 10,
            'performance': 5,
        }
        
        breakdown_key = category_map.get(category, category)
        
        if breakdown_key in breakdown:
            # Normalize to 0-100 scale
            raw_score = breakdown.get(breakdown_key, 0)
            max_score = max_points.get(breakdown_key, 20)
            normalized = int((raw_score / max_score) * 100) if max_score > 0 else 0
            return min(100, max(0, normalized))
        
        # Fallback: calculate manually if score_breakdown not available
        if category == 'seo':
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
            tech = analysis.get('detailed_analysis', {}).get('technical_audit', analysis.get('technical', {}))
            return tech.get('performance_score', 50)
            
        elif category == 'security':
            tech = analysis.get('detailed_analysis', {}).get('technical_audit', analysis.get('technical', {}))
            security = 50
            if tech.get('has_ssl'):
                security += 30
            if tech.get('security_headers', {}).get('x-frame-options'):
                security += 10
            if tech.get('security_headers', {}).get('content-security-policy'):
                security += 10
            return min(security, 100)
            
        elif category == 'content':
            content = analysis.get('detailed_analysis', {}).get('content_analysis', analysis.get('content', {}))
            return content.get('quality_score', content.get('content_quality_score', 50))
            
        elif category == 'ux' or category == 'mobile':
            ux_score = 50
            if basic.get('mobile_ready') in ['Kyllä', 'Yes', True]:
                ux_score += 25
            if basic.get('has_clear_cta'):
                ux_score += 25
            return min(ux_score, 100)
        
        elif category == 'ai_visibility':
            # AI/GEO Visibility Score - readiness for ChatGPT, Perplexity, etc.
            # Based on factors that help AI systems understand and cite content
            ai_score = 0
            content = analysis.get('detailed_analysis', {}).get('content_analysis', analysis.get('content', {}))
            tech = analysis.get('detailed_analysis', {}).get('technical_audit', analysis.get('technical', {}))
            
            # Structured data (Schema.org) - critical for AI understanding
            if basic.get('has_schema') or tech.get('has_structured_data'):
                ai_score += 25
            
            # Clear, factual content structure
            word_count = content.get('word_count', 0)
            if word_count >= 1500:
                ai_score += 20
            elif word_count >= 800:
                ai_score += 10
            
            # FAQ sections (direct answers AI can cite)
            html_content = basic.get('html_content', '').lower()
            if 'faq' in html_content or 'frequently asked' in html_content or 'usein kysyt' in html_content:
                ai_score += 15
            
            # Clear headings structure (H1, H2, H3)
            if basic.get('h1_text'):
                ai_score += 10
            if basic.get('has_proper_heading_hierarchy', True):
                ai_score += 10
            
            # Author/expertise signals (E-E-A-T)
            if 'author' in html_content or 'kirjoittaja' in html_content or 'about us' in html_content:
                ai_score += 10
            
            # SSL (trust signal)
            if tech.get('has_ssl') or basic.get('has_ssl'):
                ai_score += 10
            
            return min(ai_score, 100)
        
        return 50
    
    def _interpret_score(self, score: int) -> Dict[str, Any]:
        """
        Interpret score to avoid false precision.
        Returns level (Low/Medium/High) + description.
        
        Scale:
        - 0-39: Low (Critical issues)
        - 40-59: Medium (Needs improvement)  
        - 60-74: Good (Solid foundation)
        - 75-89: High (Strong position)
        - 90-100: Excellent (Industry leader)
        """
        if score >= 90:
            level = 'excellent'
            level_label = {'fi': 'Erinomainen', 'en': 'Excellent'}.get(self._language)
            description = {'fi': 'Toimialan kärkitasoa', 'en': 'Industry leading'}.get(self._language)
        elif score >= 75:
            level = 'high'
            level_label = {'fi': 'Korkea', 'en': 'High'}.get(self._language)
            description = {'fi': 'Vahva asema', 'en': 'Strong position'}.get(self._language)
        elif score >= 60:
            level = 'good'
            level_label = {'fi': 'Hyvä', 'en': 'Good'}.get(self._language)
            description = {'fi': 'Hyvä pohja, parannettavaa', 'en': 'Solid foundation, room to improve'}.get(self._language)
        elif score >= 40:
            level = 'medium'
            level_label = {'fi': 'Keskitaso', 'en': 'Medium'}.get(self._language)
            description = {'fi': 'Vaatii parannuksia', 'en': 'Needs improvement'}.get(self._language)
        else:
            level = 'low'
            level_label = {'fi': 'Matala', 'en': 'Low'}.get(self._language)
            description = {'fi': 'Kriittisiä puutteita', 'en': 'Critical issues'}.get(self._language)
        
        return {
            'score': score,
            'level': level,
            'level_label': level_label,
            'description': description,
            'scale': {
                'min': 0,
                'max': 100,
                'good_threshold': 60,
                'high_threshold': 75
            }
        }
    
    def _extract_top_findings(
        self,
        your_analysis: Dict[str, Any],
        category_comparison: Dict[str, Any],
        benchmark: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Extract top 3 most important findings for Strategist & Planner.
        Prioritizes: critical issues > competitive gaps > opportunities
        """
        findings = []
        
        basic = your_analysis.get('basic_analysis', {})
        detailed = your_analysis.get('detailed_analysis', {})
        tech = detailed.get('technical_audit', {})
        
        # 1. CRITICAL ISSUES (highest priority)
        
        # SSL missing = critical
        if tech.get('has_ssl') is False:
            findings.append({
                'type': 'critical',
                'category': 'security',
                'title': {'fi': 'SSL-sertifikaatti puuttuu', 'en': 'SSL certificate missing'}.get(self._language),
                'impact': 'high',
                'priority': 1
            })
        
        # No analytics = blind
        if not tech.get('has_analytics') and not basic.get('has_analytics'):
            findings.append({
                'type': 'critical',
                'category': 'analytics',
                'title': {'fi': 'Analytiikka puuttuu', 'en': 'Analytics missing'}.get(self._language),
                'impact': 'high',
                'priority': 2
            })
        
        # Mobile issues
        if basic.get('mobile_ready') not in ['Kyllä', 'Yes', True]:
            findings.append({
                'type': 'critical',
                'category': 'mobile',
                'title': {'fi': 'Mobiilioptimointi puuttuu', 'en': 'Mobile optimization missing'}.get(self._language),
                'impact': 'high',
                'priority': 3
            })
        
        # 2. COMPETITIVE GAPS (where you're behind)
        for cat, data in category_comparison.items():
            if data.get('status') == 'behind' and data.get('difference', 0) < -10:
                cat_names = {
                    'seo': {'fi': 'SEO', 'en': 'SEO'},
                    'performance': {'fi': 'Suorituskyky', 'en': 'Performance'},
                    'security': {'fi': 'Tietoturva', 'en': 'Security'},
                    'content': {'fi': 'Sisältö', 'en': 'Content'},
                    'ux': {'fi': 'Käyttökokemus', 'en': 'UX'},
                    'ai_visibility': {'fi': 'AI-näkyvyys', 'en': 'AI Visibility'},
                }
                findings.append({
                    'type': 'gap',
                    'category': cat,
                    'title': {
                        'fi': f'{cat_names.get(cat, {}).get("fi", cat)}: {data["difference"]} pistettä jäljessä',
                        'en': f'{cat_names.get(cat, {}).get("en", cat)}: {data["difference"]} points behind'
                    }.get(self._language),
                    'impact': 'medium',
                    'priority': 5,
                    'gap': data.get('difference', 0)
                })
        
        # 3. OPPORTUNITIES (where you're ahead)
        for cat, data in category_comparison.items():
            if data.get('status') == 'ahead' and data.get('difference', 0) > 15:
                cat_names = {
                    'seo': {'fi': 'SEO', 'en': 'SEO'},
                    'performance': {'fi': 'Suorituskyky', 'en': 'Performance'},
                    'content': {'fi': 'Sisältö', 'en': 'Content'},
                }
                findings.append({
                    'type': 'strength',
                    'category': cat,
                    'title': {
                        'fi': f'Vahvuus: {cat_names.get(cat, {}).get("fi", cat)} +{data["difference"]} pistettä',
                        'en': f'Strength: {cat_names.get(cat, {}).get("en", cat)} +{data["difference"]} points'
                    }.get(self._language),
                    'impact': 'positive',
                    'priority': 10
                })
        
        # Sort by priority and return top 3
        findings.sort(key=lambda x: x.get('priority', 99))
        return findings[:3]
