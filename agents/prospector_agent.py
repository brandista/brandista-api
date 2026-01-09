# -*- coding: utf-8 -*-
# Version: 2025-11-30-1050
# Changes: Extended quick wins (analytics, schema, viewport), SWOT with absolute weaknesses
"""
Growth Engine 2.0 - Prospector Agent
"The Growth Hacker" - Market gaps and growth opportunities

Responsibilities:
1. Find market gaps (where you're ahead or competitors are weak)
2. Identify quick wins (low-effort, high-impact improvements)
3. Discover competitive advantages
4. Generate SWOT analysis
5. Compile growth opportunities

Data flow:
- Input: AnalysisContext + Scout results + Analyst results
- Output: market_gaps, quick_wins, competitive_advantages, growth_opportunities, swot
"""

import logging
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent
from .agent_types import (
    AnalysisContext,
    AgentPriority,
    InsightType
)

logger = logging.getLogger(__name__)


PROSPECTOR_TASKS = {
    "finding_gaps": {"fi": "Etsitään markkinaaukkoja...", "en": "Finding market gaps..."},
    "finding_quick_wins": {"fi": "Tunnistetaan quick wins...", "en": "Identifying quick wins..."},
    "analyzing_advantages": {"fi": "Analysoidaan kilpailuetuja...", "en": "Analyzing competitive advantages..."},
    "generating_swot": {"fi": "Generoidaan SWOT-analyysiä...", "en": "Generating SWOT analysis..."},
    "compiling_opportunities": {"fi": "Kootaan kasvumahdollisuuksia...", "en": "Compiling growth opportunities..."},
}


class ProspectorAgent(BaseAgent):
    """
    💎 Prospector Agent - Kasvuhakkeri
    TRUE SWARM EDITION - Collaborates with Guardian, finds opportunities in threats
    """

    def __init__(self):
        super().__init__(
            agent_id="prospector",
            name="Prospector",
            role="Kasvuhakkeri",
            avatar="💎",
            personality="Optimistinen ja luova visionääri"
        )
        self.dependencies = ['scout', 'analyst']

        # ========================================================================
        # SWARM STATE - Active message handling
        # ========================================================================
        self._guardian_data: List[Dict[str, Any]] = []  # Threat data from Guardian
        self._threat_opportunities: List[Dict[str, Any]] = []  # Opportunities found in threats
        self._collaboration_pending: bool = False

    def _get_subscribed_message_types(self):
        """Subscribe to data and collaboration messages"""
        from .communication import MessageType
        return [
            MessageType.DATA,
            MessageType.REQUEST,
            MessageType.CONSENSUS,
            MessageType.PROPOSAL
        ]

    async def _handle_request(self, message):
        """
        Handle requests from Guardian - opportunity assessment.
        ACTIVE HANDLING - evaluate threats for hidden opportunities.
        """
        from .communication import MessageType
        from datetime import datetime

        request_type = message.payload.get('request_type', '')

        if request_type == 'opportunity_assessment':
            # Guardian asking if there's opportunity in a threat
            threat = message.payload.get('threat', {})
            opportunity = self._assess_opportunity_in_threat(threat)

            # Store for later use
            if opportunity:
                self._threat_opportunities.append(opportunity)

            # Send response back
            await self._send_message(
                to_agent=message.from_agent,
                message_type=MessageType.DATA,
                subject=f"Opportunity assessment: {threat.get('title', 'unknown')[:50]}",
                payload={
                    'opportunity': opportunity,
                    'assessed_threat': threat.get('title'),
                    'has_opportunity': opportunity is not None
                }
            )
            logger.info(f"[Prospector] 💎 Sent opportunity assessment to {message.from_agent}")

    async def _handle_data(self, message):
        """Handle data messages from Guardian"""
        if message.from_agent == 'guardian':
            self._guardian_data.append(message.payload)
            logger.info(f"[Prospector] 📊 Received Guardian data: {message.subject}")

            # If receiving threat assessment, look for opportunities
            assessment = message.payload.get('assessment', {})
            high_threats = message.payload.get('high_threats', [])

            for threat_comp in high_threats:
                opp = self._assess_opportunity_in_threat(threat_comp)
                if opp:
                    self._threat_opportunities.append(opp)

    def _assess_opportunity_in_threat(self, threat: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Find the opportunity hidden in a threat.
        This is the Prospector's core skill - seeing silver linings.
        """
        category = threat.get('category', '').lower()
        severity = threat.get('severity', 'medium')
        title = threat.get('title', '')

        # Competitor weakness = our opportunity
        if 'competitor' in category or 'competitive' in category:
            return {
                'type': 'competitive_advantage',
                'title': f"Capitalize on competitor gap: {title[:50]}",
                'description': f"Competitor showing weakness in {category} - opportunity to differentiate",
                'related_threat': title,
                'impact': 'high',
                'effort': 'medium',
                'confidence': 0.7,
                'source': 'threat_analysis'
            }

        # Market gap = positioning opportunity
        if 'market' in category or 'gap' in category:
            return {
                'type': 'market_positioning',
                'title': f"Market gap opportunity: {title[:50]}",
                'description': f"Identified market gap in {category}",
                'related_threat': title,
                'impact': 'high',
                'effort': 'high',
                'confidence': 0.6,
                'source': 'threat_analysis'
            }

        # SEO/content weakness = quick win
        if category in ['seo', 'content', 'ai_visibility']:
            return {
                'type': 'quick_win',
                'title': f"Quick improvement: {category.upper()}",
                'description': f"Address {category} weakness before competitors",
                'related_threat': title,
                'impact': 'medium',
                'effort': 'low',
                'confidence': 0.8,
                'source': 'threat_analysis'
            }

        return None

    def _task(self, key: str) -> str:
        return PROSPECTOR_TASKS.get(key, {}).get(self._language, key)
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        analyst_results = self.get_dependency_results(context, 'analyst')
        
        # 🧠 UNIFIED CONTEXT: Track implemented opportunities and market position changes
        historical_opportunities = []
        implemented_actions = []
        market_position_improving = False
        
        if context.unified_context:
            logger.info(f"[Prospector] 🧠 UNIFIED CONTEXT AVAILABLE - Checking opportunity history")
            
            # Get historical opportunities to avoid duplicates
            hist_insights = context.unified_context.get('historical_insights', [])
            historical_opportunities = [
                i for i in hist_insights 
                if i.get('insight_type') == 'opportunity' or i.get('type') == 'opportunity'
            ]
            
            # Get implemented actions from Planner
            implemented_actions = [
                i for i in hist_insights
                if i.get('insight_type') == 'action' and i.get('status') == 'completed'
            ]
            
            if historical_opportunities:
                logger.info(f"[Prospector] Found {len(historical_opportunities)} previous opportunities")
                self._emit_insight(
                    f"💡 {len(historical_opportunities)} mahdollisuutta tunnistettu aiemmin",
                    priority=AgentPriority.LOW,
                    insight_type=InsightType.FINDING,
                    data={'historical_count': len(historical_opportunities)}
                )
            
            if implemented_actions:
                logger.info(f"[Prospector] {len(implemented_actions)} actions already implemented")
                self._emit_insight(
                    f"✅ {len(implemented_actions)} toimenpidettä jo toteutettu",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING,
                    data={'implemented_count': len(implemented_actions)}
                )
            
            # Check score trend for market positioning
            trends = context.unified_context.get('trends', {})
            if trends and 'score_change' in trends:
                score_change = trends['score_change']
                if score_change > 0:
                    market_position_improving = True
                    logger.info(f"[Prospector] Market position improving: +{score_change:.1f}")
        
        if not analyst_results:
            self._emit_insight(
                self._t("prospector.no_data"),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.FINDING
            )
            return {'market_gaps': [], 'quick_wins': [], 'growth_opportunities': []}
        
        your_analysis = analyst_results.get('your_analysis', {})
        competitor_analyses = analyst_results.get('competitor_analyses', [])
        category_comparison = analyst_results.get('category_comparison', {})
        
        self._emit_insight(
            self._t("prospector.starting"),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        self._update_progress(20, self._task("finding_gaps"))
        
        # 1. Etsi markkinaaukot
        market_gaps = self._find_market_gaps(category_comparison, competitor_analyses)
        
        for gap in market_gaps[:3]:
            self._emit_insight(
                self._t("prospector.found_gap", title=gap.get('title', '')),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.OPPORTUNITY,
                data=gap
            )
        
        if len(market_gaps) > 3:
            self._emit_insight(
                self._t("prospector.more_gaps", count=len(market_gaps) - 3),
                priority=AgentPriority.LOW,
                insight_type=InsightType.FINDING
            )
        
        self._update_progress(40, self._task("finding_quick_wins"))
        
        # 2. Löydä quick wins
        quick_wins = self._find_quick_wins(your_analysis)
        
        for idx, win in enumerate(quick_wins[:3]):
            effort = win.get('effort', 'medium')
            effort_text = {'low': 'Low', 'medium': 'Medium', 'high': 'High'}.get(effort, effort)
            
            self._emit_insight(
                self._t("prospector.quick_win", 
                       idx=idx+1, 
                       title=win.get('title', ''),
                       effort=effort_text),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.RECOMMENDATION,
                data=win
            )
        
        self._update_progress(60, self._task("analyzing_advantages"))
        
        # 3. Tunnista kilpailuedut
        competitive_advantages = self._identify_competitive_advantages(
            category_comparison, 
            analyst_results.get('benchmark', {})
        )
        
        if competitive_advantages:
            for adv in competitive_advantages[:2]:
                self._emit_insight(
                    self._t("prospector.advantage", title=adv.get('title', '')),
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING,
                    data=adv
                )
        
        self._update_progress(75, self._task("generating_swot"))
        
        # 4. SWOT-analyysi
        try:
            from main import generate_competitive_swot_analysis
            
            swot = await generate_competitive_swot_analysis(
                your_analysis,
                competitor_analyses,
                context.language
            )
        except Exception as e:
            logger.error(f"[Prospector] SWOT generation error: {e}")
            swot = self._generate_basic_swot(your_analysis, category_comparison)
        
        strengths_count = len(swot.get('strengths', []))
        opportunities_count = len(swot.get('opportunities', []))
        
        self._emit_insight(
            self._t("prospector.swot_complete",
                   strengths=strengths_count,
                   opportunities=opportunities_count),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data={'swot_summary': swot}
        )
        
        self._update_progress(90, self._task("compiling_opportunities"))
        
        # 5. Koosta kasvumahdollisuudet
        growth_opportunities = self._compile_growth_opportunities(
            quick_wins, 
            market_gaps, 
            swot.get('opportunities', [])
        )
        
        high_impact = len([o for o in growth_opportunities if o.get('impact') == 'high'])
        
        self._emit_insight(
            self._t("prospector.complete",
                   total=len(growth_opportunities),
                   high_impact=high_impact),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data={'total': len(growth_opportunities), 'high_impact': high_impact}
        )

        # ========================================================================
        # SWARM: Merge threat-based opportunities from Guardian collaboration
        # ========================================================================
        if self._threat_opportunities:
            logger.info(f"[Prospector] 💎 Adding {len(self._threat_opportunities)} opportunities from threat analysis")
            for threat_opp in self._threat_opportunities:
                threat_opp['source_agent'] = self.id
                threat_opp['from_collaboration'] = True
                growth_opportunities.append(threat_opp)

        # ========================================================================
        # SWARM: Add opportunities to SharedKnowledge
        # ========================================================================
        for opp in growth_opportunities:
            opp['source_agent'] = self.id
            context.add_to_shared('detected_opportunities', opp, self.id)

        # Also read threats from shared knowledge and find more opportunities
        shared_threats = context.get_from_shared('detected_threats', [])
        if shared_threats:
            logger.info(f"[Prospector] 🔍 Analyzing {len(shared_threats)} shared threats for opportunities")
            for threat in shared_threats[:5]:  # Check top 5 threats
                if threat.get('source_agent') != self.id:  # Don't duplicate our own
                    additional_opp = self._assess_opportunity_in_threat(threat)
                    if additional_opp:
                        additional_opp['from_shared_knowledge'] = True
                        growth_opportunities.append(additional_opp)
                        context.add_to_shared('detected_opportunities', additional_opp, self.id)

        logger.info(f"[Prospector] ✅ Added {len(growth_opportunities)} opportunities to SharedKnowledge")

        return {
            'market_gaps': market_gaps,
            'quick_wins': quick_wins,
            'competitive_advantages': competitive_advantages,
            'growth_opportunities': growth_opportunities,
            'swot': swot,
            # NEW: Swarm data
            'threat_opportunities': len(self._threat_opportunities),
            'guardian_data_received': len(self._guardian_data),
            'swarm_contributions': {
                'opportunities_from_threats': len(self._threat_opportunities),
                'shared_threats_analyzed': len(shared_threats)
            }
        }
    
    def _find_market_gaps(
        self,
        category_comparison: Dict[str, Any],
        competitor_analyses: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        gaps = []
        
        # Categories where you're ahead
        for cat, data in category_comparison.items():
            if data.get('status') == 'ahead' and data.get('difference', 0) > 10:
                title_map = {
                    'seo': {'fi': 'Vahva SEO-asema', 'en': 'Strong SEO position'},
                    'performance': {'fi': 'Nopeampi sivusto', 'en': 'Faster website'},
                    'security': {'fi': 'Parempi tietoturva', 'en': 'Better security'},
                    'content': {'fi': 'Laadukkaampi sisältö', 'en': 'Higher quality content'},
                    'ux': {'fi': 'Parempi käyttökokemus', 'en': 'Better user experience'},
                }
                
                gaps.append({
                    'type': 'strength_opportunity',
                    'category': cat,
                    'title': title_map.get(cat, {}).get(self._language, cat),
                    'your_score': data.get('your_score', 0),
                    'competitor_avg': data.get('competitor_avg', 0),
                    'advantage': data.get('difference', 0),
                    'impact': 'high'
                })
        
        # Categories where competitors are weak
        if competitor_analyses:
            for cat in ['seo', 'performance', 'content']:
                cat_comp = category_comparison.get(cat, {})
                if cat_comp.get('competitor_avg', 100) < 45:
                    title_map = {
                        'seo': {'fi': 'Kilpailijoiden heikko SEO', 'en': 'Competitors weak SEO'},
                        'performance': {'fi': 'Kilpailijoiden hitaat sivustot', 'en': 'Competitors slow websites'},
                        'content': {'fi': 'Kilpailijoiden heikko sisältö', 'en': 'Competitors weak content'},
                    }
                    
                    gaps.append({
                        'type': 'competitor_weakness',
                        'category': cat,
                        'title': title_map.get(cat, {}).get(self._language, cat),
                        'competitor_avg': cat_comp.get('competitor_avg', 0),
                        'impact': 'medium'
                    })
        
        return gaps
    
    def _find_quick_wins(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        quick_wins = []
        basic = analysis.get('basic_analysis', analysis.get('basic', {}))
        # Tech data is in detailed_analysis.technical_audit, not at root level
        tech = analysis.get('detailed_analysis', {}).get('technical_audit', analysis.get('technical', {}))
        
        # SEO quick wins
        if not basic.get('meta_description') or len(basic.get('meta_description', '')) < 50:
            quick_wins.append({
                'category': 'seo',
                'title': {'fi': 'Lisää meta description', 'en': 'Add meta description'}.get(self._language),
                'impact': 'medium',
                'effort': 'low',
                'timeframe': '1 day'
            })
        
        if not basic.get('h1_text'):
            quick_wins.append({
                'category': 'seo',
                'title': {'fi': 'Lisää H1-otsikko', 'en': 'Add H1 heading'}.get(self._language),
                'impact': 'medium',
                'effort': 'low',
                'timeframe': '1 day'
            })
        
        # Performance quick wins
        if tech.get('performance_score', 100) < 60:
            quick_wins.append({
                'category': 'performance',
                'title': {'fi': 'Optimoi kuvat', 'en': 'Optimize images'}.get(self._language),
                'impact': 'high',
                'effort': 'medium',
                'timeframe': '1 week'
            })
        
        # Security quick wins
        if not tech.get('has_ssl'):
            quick_wins.append({
                'category': 'security',
                'title': {'fi': 'Ota SSL käyttöön', 'en': 'Enable SSL'}.get(self._language),
                'impact': 'high',
                'effort': 'low',
                'timeframe': '1 day'
            })
        
        # UX quick wins
        if not basic.get('has_clear_cta'):
            quick_wins.append({
                'category': 'ux',
                'title': {'fi': 'Lisaa selkea CTA', 'en': 'Add clear CTA'}.get(self._language),
                'impact': 'high',
                'effort': 'low',
                'timeframe': '1 day'
            })
        
        # Analytics quick wins
        if not tech.get('has_analytics') and not basic.get('has_analytics'):
            quick_wins.append({
                'category': 'analytics',
                'title': {'fi': 'Asenna Google Analytics 4', 'en': 'Install Google Analytics 4'}.get(self._language),
                'impact': 'high',
                'effort': 'low',
                'timeframe': '1 day'
            })
        
        # Structured data quick wins
        if not basic.get('has_schema') and not tech.get('has_structured_data'):
            quick_wins.append({
                'category': 'seo',
                'title': {'fi': 'Lisaa strukturoitu data (Schema.org)', 'en': 'Add structured data (Schema.org)'}.get(self._language),
                'impact': 'medium',
                'effort': 'medium',
                'timeframe': '1 week'
            })
        
        # Mobile viewport quick wins
        if not basic.get('has_mobile_viewport') and not basic.get('has_viewport'):
            quick_wins.append({
                'category': 'mobile',
                'title': {'fi': 'Lisaa mobiili viewport', 'en': 'Add mobile viewport'}.get(self._language),
                'impact': 'high',
                'effort': 'low',
                'timeframe': '1 day'
            })
        
        return quick_wins
    
    def _identify_competitive_advantages(
        self,
        category_comparison: Dict[str, Any],
        benchmark: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        advantages = []
        
        for cat, data in category_comparison.items():
            if data.get('status') == 'ahead':
                diff = data.get('difference', 0)
                
                cat_names = {
                    'seo': {'fi': 'Hakukonenäkyvyys', 'en': 'Search visibility'},
                    'performance': {'fi': 'Suorituskyky', 'en': 'Performance'},
                    'security': {'fi': 'Tietoturva', 'en': 'Security'},
                    'content': {'fi': 'Sisällön laatu', 'en': 'Content quality'},
                    'ux': {'fi': 'Käyttökokemus', 'en': 'User experience'},
                }
                
                advantages.append({
                    'category': cat,
                    'title': cat_names.get(cat, {}).get(self._language, cat),
                    'your_score': data.get('your_score', 0),
                    'advantage_points': diff,
                    'strength': 'strong' if diff > 15 else 'moderate'
                })
        
        # Overall advantage
        your_position = benchmark.get('your_position', 1)
        total = benchmark.get('total_analyzed', 1)
        
        if your_position == 1:
            advantages.insert(0, {
                'category': 'overall',
                'title': {'fi': 'Markkinajohtaja', 'en': 'Market leader'}.get(self._language),
                'your_score': benchmark.get('your_score', 0),
                'strength': 'strong'
            })
        
        return advantages
    
    def _generate_basic_swot(
        self,
        analysis: Dict[str, Any],
        category_comparison: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        strengths = []
        weaknesses = []
        opportunities = []
        threats = []
        
        # Get basic analysis data for absolute weaknesses
        basic = analysis.get('basic_analysis', analysis.get('basic', {}))
        detailed = analysis.get('detailed_analysis', {})
        tech = detailed.get('technical_audit', {})
        content = detailed.get('content_analysis', {})
        score_breakdown = basic.get('score_breakdown', {})
        
        cat_names = {
            'seo': 'SEO', 'performance': 'Performance', 'security': 'Security', 
            'content': 'Content', 'ux': 'UX', 'ai_visibility': 'AI Visibility'
        }
        
        # 1. Relative weaknesses (vs competitors)
        for cat, data in category_comparison.items():
            if data.get('status') == 'ahead':
                strengths.append(f"{cat_names.get(cat, cat)}: +{data.get('difference', 0)} points vs competitors")
            elif data.get('status') == 'behind':
                weaknesses.append(f"{cat_names.get(cat, cat)}: {data.get('difference', 0)} points vs competitors")
        
        # 2. ABSOLUTE weaknesses (regardless of competitors)
        # These are things that are objectively bad
        
        # Security issues
        if not tech.get('has_ssl') and not basic.get('has_ssl'):
            weaknesses.append("Missing SSL certificate (critical for trust & SEO)")
        if not basic.get('has_security_headers') and not tech.get('has_security_headers'):
            weaknesses.append("Missing security headers (CSP, X-Frame-Options)")
        
        # SEO issues
        if not basic.get('meta_description'):
            weaknesses.append("Missing meta description (affects CTR)")
        if not basic.get('h1_text'):
            weaknesses.append("Missing H1 heading (affects SEO)")
        if not tech.get('has_sitemap') and not basic.get('has_sitemap'):
            weaknesses.append("Missing XML sitemap")
        
        # Technical issues
        if not tech.get('has_analytics') and not basic.get('has_analytics'):
            weaknesses.append("No analytics tracking (can't measure performance)")
        
        # Mobile issues
        if basic.get('mobile_ready') not in ['Kyllä', 'Yes', True]:
            weaknesses.append("Poor mobile optimization (55%+ traffic is mobile)")
        
        # Content issues
        word_count = content.get('word_count', 0)
        if word_count < 300:
            weaknesses.append(f"Thin content ({word_count} words - aim for 1000+)")
        
        # Performance issues
        speed_score = tech.get('page_speed_score', 100)
        if speed_score < 50:
            weaknesses.append(f"Slow page speed (score: {speed_score}/100)")
        
        # 3. Opportunities based on weaknesses
        if weaknesses:
            opportunities.append("Fix critical issues to improve competitive position")
        if 'SEO' in str(weaknesses):
            opportunities.append("SEO improvements could increase organic traffic 20-50%")
        if 'mobile' in str(weaknesses).lower():
            opportunities.append("Mobile optimization could improve conversion rate")
        
        # 4. Threats
        behind_count = len([c for c in category_comparison.values() if c.get('status') == 'behind'])
        if behind_count >= 2:
            threats.append(f"Behind competitors in {behind_count} categories")
        if not tech.get('has_ssl'):
            threats.append("Google penalizes non-HTTPS sites in rankings")
        
        return {
            'strengths': strengths[:5],  # Limit to top 5
            'weaknesses': weaknesses[:5],
            'opportunities': opportunities[:5],
            'threats': threats[:5]
        }
    
    def _compile_growth_opportunities(
        self,
        quick_wins: List[Dict[str, Any]],
        market_gaps: List[Dict[str, Any]],
        swot_opportunities: List[str]
    ) -> List[Dict[str, Any]]:
        opportunities = []
        
        # Add quick wins as opportunities
        for win in quick_wins:
            opportunities.append({
                'source': 'quick_win',
                'title': win.get('title', ''),
                'category': win.get('category', ''),
                'impact': win.get('impact', 'medium'),
                'effort': win.get('effort', 'medium'),
                'timeframe': win.get('timeframe', '')
            })
        
        # Add market gaps
        for gap in market_gaps:
            opportunities.append({
                'source': 'market_gap',
                'title': gap.get('title', ''),
                'category': gap.get('category', ''),
                'impact': gap.get('impact', 'medium'),
                'effort': 'medium'
            })
        
        # Sort by impact
        impact_order = {'high': 0, 'medium': 1, 'low': 2}
        opportunities.sort(key=lambda x: impact_order.get(x.get('impact', 'medium'), 1))
        
        return opportunities
