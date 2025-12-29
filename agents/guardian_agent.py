# -*- coding: utf-8 -*-
# Version: 2.1.0 - TRUE SWARM EDITION
"""
Growth Engine 2.0 - Guardian Agent
TRUE SWARM EDITION - Reactively processes Scout alerts

The Risk Manager - RASM, threat analysis and Competitor Threat Assessment

SWARM FEATURES:
- Receives high-threat competitor alerts from Scout
- Broadcasts critical risks to Strategist immediately
- Collaborates with Prospector on risk/opportunity balance
- Publishes threat data to blackboard for Planner
"""

import logging
import asyncio
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

from urllib.parse import urlparse

from .base_agent import BaseAgent
from .agent_types import (
    AnalysisContext,
    AgentPriority,
    InsightType
)
from .communication import MessageType, MessagePriority, AgentMessage
from .blackboard import DataCategory

logger = logging.getLogger(__name__)


GUARDIAN_TASKS = {
    "building_risk_register": {"fi": "Rakennetaan riskiregisteria...", "en": "Building risk register..."},
    "calculating_impact": {"fi": "Lasketaan liikevaihtovaikutusta...", "en": "Calculating revenue impact..."},
    "identifying_threats": {"fi": "Tunnistetaan uhkia...", "en": "Identifying threats..."},
    "prioritizing_actions": {"fi": "Priorisoidaan toimenpiteita...", "en": "Prioritizing actions..."},
    "calculating_rasm": {"fi": "Lasketaan RASM-pistemaaraa...", "en": "Calculating RASM score..."},
    "assessing_competitors": {"fi": "Arvioidaan kilpailijoiden uhkatasoa...", "en": "Assessing competitor threat levels..."},
}

THREAT_TITLES = {
    "seo": {"fi": "Heikko hakukonenakyvyys", "en": "Poor search engine visibility"},
    "mobile": {"fi": "Puutteellinen mobiilioptimointi", "en": "Inadequate mobile optimization"},
    "ssl": {"fi": "SSL-sertifikaatti puuttuu", "en": "SSL certificate missing"},
    "performance": {"fi": "Hidas sivusto", "en": "Slow website"},
    "competitive": {"fi": "Jaat kilpailijoista jalkeen", "en": "Falling behind competitors"},
    "content": {"fi": "Heikko sisallon laatu", "en": "Poor content quality"},
    "ai_visibility": {"fi": "Heikko AI-hakunakyvyys", "en": "Poor AI search visibility"},
}

THREAT_LEVEL_LABELS = {
    "high": {"fi": "KORKEA UHKA", "en": "HIGH THREAT"},
    "medium": {"fi": "KOHTALAINEN UHKA", "en": "MEDIUM THREAT"},
    "low": {"fi": "MATALA UHKA", "en": "LOW THREAT"},
}

COMPETITOR_INSIGHTS = {
    "high_threat": {
        "fi": "[HIGH] {name}: {label} - Pisteet {score}/100, {reason}",
        "en": "[HIGH] {name}: {label} - Score {score}/100, {reason}"
    },
    "medium_threat": {
        "fi": "[MED] {name}: {label} - Pisteet {score}/100, {reason}",
        "en": "[MED] {name}: {label} - Score {score}/100, {reason}"
    },
    "low_threat": {
        "fi": "[LOW] {name}: {label} - Pisteet {score}/100, {reason}",
        "en": "[LOW] {name}: {label} - Score {score}/100, {reason}"
    },
    "assessment_complete": {
        "fi": "[TARGET] Kilpailija-arviointi valmis: {high} korkean uhkan, {medium} kohtalaisen, {low} matalan",
        "en": "[TARGET] Competitor assessment complete: {high} high threat, {medium} medium, {low} low"
    },
}


class GuardianAgent(BaseAgent):
    """
    🛡️ Guardian Agent - Riskienhallitsija (RASM)
    TRUE SWARM EDITION
    """
    
    def __init__(self):
        super().__init__(
            agent_id="guardian",
            name="Guardian",
            role="Riskienhallitsija",
            avatar="🛡️",
            personality="Valpas ja huolellinen turvallisuusasiantuntija"
        )
        self.dependencies = ['scout', 'analyst']
        self._scout_alerts: List[Dict[str, Any]] = []
    
    def _get_subscribed_message_types(self) -> List[MessageType]:
        """Guardian subscribes to alerts and findings"""
        return [
            MessageType.ALERT,
            MessageType.FINDING,
            MessageType.DATA,
            MessageType.REQUEST
        ]
    
    def _get_task_capabilities(self) -> Set[str]:
        """Tasks Guardian can handle"""
        return {'risk_assessment', 'threat_analysis', 'competitor_threat'}
    
    def _setup_blackboard_subscriptions(self):
        """Subscribe to competitor data"""
        if self._blackboard:
            self._blackboard.subscribe(
                pattern="scout.competitors.*",
                agent_id=self.id,
                callback=self._on_competitor_data
            )
    
    def _on_competitor_data(self, entry):
        """React to competitor data from Scout"""
        logger.info(f"[Guardian] 📋 Received competitor data from blackboard: {entry.key}")
    
    async def _handle_alert(self, message: AgentMessage):
        """Handle alerts from Scout about high-threat competitors"""
        if message.from_agent == 'scout' and 'competitors' in message.payload:
            self._scout_alerts.append(message.payload)
            logger.info(f"[Guardian] 🚨 Received Scout alert about {len(message.payload.get('competitors', []))} threats")
    
    def _task(self, key: str) -> str:
        return GUARDIAN_TASKS.get(key, {}).get(self._language, key)
    
    def _threat_title(self, key: str) -> str:
        return THREAT_TITLES.get(key, {}).get(self._language, key)
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        from main import build_risk_register
        
        analyst_results = self.get_dependency_results(context, 'analyst')
        scout_results = self.get_dependency_results(context, 'scout')
        
        # 🧠 UNIFIED CONTEXT: Track historical threats and revenue trends
        historical_threats = []
        previous_rasm_score = None
        recurring_threats_count = 0
        
        if context.unified_context:
            logger.info(f"[Guardian] 🧠 UNIFIED CONTEXT AVAILABLE - Checking threat history")
            
            # Get previous RASM score for trend analysis
            recent_analyses = context.unified_context.get('recent_analyses', [])
            if recent_analyses:
                for analysis in recent_analyses:
                    if 'rasm_score' in analysis:
                        previous_rasm_score = analysis.get('rasm_score', 0)
                        logger.info(f"[Guardian] Previous RASM: {previous_rasm_score}/100")
                        break
            
            # Get historical threat insights
            hist_insights = context.unified_context.get('historical_insights', [])
            historical_threats = [
                i for i in hist_insights 
                if i.get('insight_type') == 'threat' or i.get('type') == 'threat'
            ]
            
            if historical_threats:
                logger.info(f"[Guardian] Found {len(historical_threats)} historical threats")
                # Track most recent threats (last 30 days)
                recent_threats = [t for t in historical_threats[:10]]
                recurring_threats_count = len(recent_threats)
                
                if recurring_threats_count > 0:
                    self._emit_insight(
                        f"⚠️ {recurring_threats_count} uhkaa havaittu aiemmin - tarkistetaan onko korjattu",
                        priority=AgentPriority.MEDIUM,
                        insight_type=InsightType.FINDING,
                        data={'historical_threats': recurring_threats_count}
                    )
            
            # Check if threats are getting better or worse
            trends = context.unified_context.get('trends', {})
            if trends and 'top_threat' in trends:
                top_threat = trends['top_threat']
                logger.info(f"[Guardian] Previous top threat: {top_threat}")
        
        if not analyst_results:
            self._emit_insight(
                self._t("guardian.no_data"),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
            return {'threats': [], 'risk_register': [], 'rasm_score': 0}
        
        your_analysis = analyst_results.get('your_analysis', {})
        benchmark = analyst_results.get('benchmark', {})
        category_comparison = analyst_results.get('category_comparison', {})
        competitor_analyses = analyst_results.get('competitor_analyses', [])
        your_score = analyst_results.get('your_score', 0)
        
        # Get enriched company intel - try analyst first (passed through), then scout
        competitors_enriched = analyst_results.get('competitors_enriched', [])
        if not competitors_enriched and scout_results:
            competitors_enriched = scout_results.get('competitors_enriched', [])
        
        self._update_progress(15, self._task("building_risk_register"))
        
        self._emit_insight(
            self._t("guardian.starting_rasm"),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # Get data from correct keys
        basic_data = your_analysis.get('basic_analysis', your_analysis.get('basic', {}))
        detailed = your_analysis.get('detailed_analysis', {})
        technical_data = detailed.get('technical_audit', your_analysis.get('technical', {}))
        content_data = detailed.get('content_analysis', your_analysis.get('content', {}))
        
        # 1. Rakenna riskiregisteri (vanha tapa, sailytetaan yhteensopivuus)
        try:
            risk_register = build_risk_register(
                basic_data,
                technical_data,
                content_data,
                context.language
            )
        except Exception as e:
            logger.error(f"[Guardian] Risk register error: {e}")
            risk_register = []
        
        self._update_progress(30, self._task("calculating_impact"))
        
        # 2. UUSI: Realistinen Revenue Impact Model
        try:
            from revenue_impact_model import (
                calculate_revenue_impact, 
                detect_risks_from_analysis,
                detect_industry,
                revenue_impact_to_dict
            )
            USE_NEW_REVENUE_MODEL = True
            logger.info("[Guardian] [OK] revenue_impact_model loaded successfully")
        except ImportError as e:
            logger.warning(f"[Guardian] [WARN] revenue_impact_model not available, using fallback: {e}")
            USE_NEW_REVENUE_MODEL = False
        
        # Hae liikevaihto
        annual_revenue = 500000  # Default EUR500k fallback
        revenue_source = "default"
        company_name = "Company"
        revenue_warning = None
        
        try:
            your_company_intel = scout_results.get('your_company_intel', {}) if scout_results else {}
            
            if your_company_intel and your_company_intel.get('revenue'):
                annual_revenue = int(your_company_intel.get('revenue', 500000))
                revenue_source = "company_intel"
                company_name = your_company_intel.get('name', 'Company')
                logger.info(f"[Guardian] ✅ Using REAL revenue from Company Intel: EUR{annual_revenue:,} ({company_name})")
            elif your_company_intel and your_company_intel.get('name'):
                # Company found but no revenue data
                company_name = your_company_intel.get('name', 'Company')
                revenue_warning = f"Company '{company_name}' found but revenue data not available - using estimate"
                logger.warning(f"[Guardian] ⚠️ {revenue_warning}")
            elif context.revenue_input:
                annual_revenue = int(context.revenue_input.get('annual_revenue', 500000))
                revenue_source = "user_input"
                logger.info(f"[Guardian] Using user-provided revenue: EUR{annual_revenue:,}")
            else:
                revenue_warning = "No company data found - using EUR500k default estimate"
                logger.warning(f"[Guardian] ⚠️ {revenue_warning}")
                
        except Exception as e:
            logger.warning(f"[Guardian] Revenue fetch failed, using default: {e}")
            annual_revenue = 500000
            revenue_warning = f"Revenue fetch failed: {e}"
        
        # Kayta uutta mallia jos saatavilla
        if USE_NEW_REVENUE_MODEL:
            # Tunnista toimiala (basic_data, technical_data, content_data defined above)
            industry = detect_industry(
                context.url,
                basic_data,
                scout_results.get('your_company_intel', {}) if scout_results else None
            )
            logger.info(f"[Guardian] Detected industry: {industry}")
            
            # Tunnista riskit analyysidatasta
            detected_risks = detect_risks_from_analysis(
                basic_data,
                technical_data,
                content_data
            )
            logger.info(f"[Guardian] Detected risks: {detected_risks}")
            
            # Hae HTML sisalto presence-tunnistusta varten
            html_content = basic_data.get('html_content', '')
            if not html_content:
                # Yritetaan hakea URL:sta
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.get(context.url)
                        html_content = resp.text[:50000]  # Max 50KB
                except Exception as e:
                    logger.warning(f"[Guardian] Could not fetch HTML for presence detection: {e}")
                    html_content = ''
            
            # Laske realistinen revenue impact
            revenue_impact_analysis = calculate_revenue_impact(
                annual_revenue=annual_revenue,
                detected_risks=detected_risks,
                industry=industry,
                company_name=company_name,
                language=context.language,
                html_content=html_content
            )
            
            # Muunna dictiksi
            revenue_impact_data = revenue_impact_to_dict(revenue_impact_analysis)
            
            # Emit insight
            total_impact = revenue_impact_analysis.total_impact_expected
            if total_impact > 100000:
                self._emit_insight(
                    f"[WARN] {'Arvioitu vuotuinen riski' if self._language == 'fi' else 'Estimated annual risk'}: EUR{total_impact:,.0f} ({revenue_impact_analysis.total_impact_percentage}% {'liikevaihdosta' if self._language == 'fi' else 'of revenue'})",
                    priority=AgentPriority.CRITICAL,
                    insight_type=InsightType.THREAT,
                    data={'annual_risk': total_impact, 'percentage': revenue_impact_analysis.total_impact_percentage}
                )
            elif total_impact > 20000:
                self._emit_insight(
                    f"[TIP] {'Arvioitu vuotuinen riski' if self._language == 'fi' else 'Estimated annual risk'}: EUR{total_impact:,.0f}",
                    priority=AgentPriority.HIGH,
                    insight_type=InsightType.THREAT,
                    data={'annual_risk': total_impact}
                )
            
            # Log methodology
            logger.info(f"[Guardian] Revenue Impact: EUR{total_impact:,} ({revenue_impact_analysis.confidence_level} confidence)")
            logger.info(f"[Guardian] Methodology: {revenue_impact_analysis.methodology_note}")
            
            # Vanha business_impact sailytetaan yhteensopivuutta varten
            business_impact = {
                'total_monthly_risk': total_impact // 12,
                'total_annual_risk': total_impact,
                # Uusi rikas data
                'revenue_impact_analysis': revenue_impact_data
            }
            
            annual_risk = total_impact
        else:
            # FALLBACK: Vanha yksinkertainen laskenta
            logger.info("[Guardian] Using fallback revenue calculation")
            risk_multipliers = {12: 0.06, 9: 0.04, 8: 0.03, 6: 0.02}
            total_risk_percent = 0
            for risk_item in risk_register:
                risk_score = getattr(risk_item, 'risk_score', 0) if hasattr(risk_item, 'risk_score') else (risk_item.get('risk_score', 0) if isinstance(risk_item, dict) else 0)
                multiplier = risk_multipliers.get(risk_score, risk_score * 0.005)
                total_risk_percent += multiplier
            
            total_risk_percent = min(total_risk_percent, 0.25)
            annual_risk = int(annual_revenue * total_risk_percent)
            
            business_impact = {
                'total_monthly_risk': annual_risk // 12,
                'total_annual_risk': annual_risk
            }
        
        # Emit revenue risk insight
        if annual_risk > 50000:
            self._emit_insight(
                self._t("guardian.risk_critical", amount=f"{annual_risk:,.0f}"),
                priority=AgentPriority.CRITICAL,
                insight_type=InsightType.THREAT,
                data={'annual_risk': annual_risk}
            )
        elif annual_risk > 20000:
            self._emit_insight(
                self._t("guardian.risk_high", amount=f"{annual_risk:,.0f}"),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT,
                data={'annual_risk': annual_risk}
            )
        elif annual_risk > 0:
            self._emit_insight(
                self._t("guardian.risk_medium", amount=f"{annual_risk:,.0f}"),
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING,
                data={'annual_risk': annual_risk}
            )
        
        self._update_progress(45, self._task("identifying_threats"))
        
        # 3. Tunnista uhkat
        threats = self._identify_threats(your_analysis, benchmark, category_comparison)
        
        # Emit threat insights
        for threat in threats[:5]:
            severity = threat.get('severity', 'medium')
            cat = threat.get('category', '')
            title = self._threat_title(cat) if cat in THREAT_TITLES else threat.get('title', '')
            
            if severity == 'critical':
                self._emit_insight(
                    self._t("guardian.threat_critical", category=cat.upper(), title=title),
                    priority=AgentPriority.CRITICAL,
                    insight_type=InsightType.THREAT,
                    data=threat
                )
            elif severity == 'high':
                self._emit_insight(
                    self._t("guardian.threat_high", category=cat.upper(), title=title),
                    priority=AgentPriority.HIGH,
                    insight_type=InsightType.THREAT,
                    data=threat
                )
        
        self._update_progress(60, self._task("assessing_competitors"))
        
        # 4. NEW: Competitor Threat Assessment
        competitor_threat_assessment = await self._assess_competitor_threats(
            competitor_analyses=competitor_analyses,
            your_score=your_score,
            scout_data=scout_results,
            competitors_enriched=competitors_enriched  # Real company intel
        )
        
        self._update_progress(75, self._task("prioritizing_actions"))
        
        # 5. Priorisoi toimenpiteet
        priority_actions = self._prioritize_actions(threats, risk_register)
        
        # Emit top priority actions
        for idx, action in enumerate(priority_actions[:3]):
            roi = action.get('roi_score', 0)
            self._emit_insight(
                self._t("guardian.priority_action", 
                       idx=idx+1, 
                       title=action.get('title', ''),
                       roi=f"{roi:.1f}"),
                priority=AgentPriority.HIGH,
                insight_type=InsightType.RECOMMENDATION,
                data=action
            )
        
        self._update_progress(90, self._task("calculating_rasm"))
        
        # 5. Laske RASM-pistemaara
        rasm_score = self._calculate_rasm_score(threats, your_analysis)
        
        self._emit_insight(
            self._t("guardian.complete", count=len(threats), score=rasm_score),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data={'threat_count': len(threats), 'rasm_score': rasm_score}
        )
        
        # ====================================================================
        # SWARM: Share risk findings with other agents
        # ====================================================================
        
        # 1. Publish threats to blackboard
        await self._publish_to_blackboard(
            key="threats.identified",
            value={
                'threats': threats,
                'rasm_score': rasm_score,
                'critical_count': len([t for t in threats if t.get('severity') == 'high'])
            },
            category=DataCategory.THREAT
        )
        
        # 2. Alert Strategist about critical threats
        critical_threats = [t for t in threats if t.get('severity') == 'high']
        if critical_threats:
            await self._send_message(
                to_agent='strategist',
                message_type=MessageType.ALERT,
                subject=f"Critical threats found: {len(critical_threats)}",
                payload={
                    'critical_threats': critical_threats,
                    'rasm_score': rasm_score,
                    'priority_actions': priority_actions[:3]  # Top 3
                },
                priority=MessagePriority.HIGH
            )
            logger.info(f"[Guardian] 🚨 Alerted Strategist about {len(critical_threats)} critical threats")
        
        # 3. Share competitor threat assessment with Prospector
        if competitor_threat_assessment:
            await self._send_message(
                to_agent='prospector',
                message_type=MessageType.DATA,
                subject="Competitor threat levels",
                payload={
                    'assessment': competitor_threat_assessment,
                    'high_threats': [c for c in competitor_threat_assessment if c.get('threat_level') == 'high']
                }
            )
        
        # 4. Publish priority actions for Planner
        await self._publish_to_blackboard(
            key="actions.priority",
            value={
                'actions': priority_actions,
                'total_impact': sum(a.get('revenue_impact', 0) for a in priority_actions)
            },
            category=DataCategory.ACTION
        )
        
        # 5. Broadcast RASM score to all
        await self._share_finding(
            f"RASM Score: {rasm_score}/100 with {len(threats)} identified threats",
            {
                'rasm_score': rasm_score,
                'threat_count': len(threats),
                'critical_count': len(critical_threats)
            }
        )
        
        return {
            'threats': threats,
            'risk_register': risk_register,
            'revenue_impact': business_impact,
            'priority_actions': priority_actions,
            'rasm_score': rasm_score,
            'competitor_threat_assessment': competitor_threat_assessment,
            # Revenue data transparency
            'revenue_data': {
                'annual_revenue': annual_revenue,
                'source': revenue_source,
                'warning': revenue_warning,
                'company_name': company_name
            }
        }
    
    def _identify_threats(
        self,
        analysis: Dict[str, Any],
        benchmark: Dict[str, Any],
        category_comparison: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        threats = []
        
        basic = analysis.get('basic_analysis', analysis.get('basic', {}))
        # Technical data is in detailed_analysis.technical_audit, not at root level
        tech = analysis.get('detailed_analysis', {}).get('technical_audit', analysis.get('technical', {}))
        content = analysis.get('detailed_analysis', {}).get('content_analysis', analysis.get('content', {}))
        
        # Debug logging
        logger.info(f"[Guardian] Analysis keys: {list(analysis.keys())}")
        logger.info(f"[Guardian] Tech keys: {list(tech.keys()) if tech else 'EMPTY'}")
        logger.info(f"[Guardian] has_ssl value: {tech.get('has_ssl', 'NOT FOUND')}")
        
        # SEO threats
        seo_comp = category_comparison.get('seo', {})
        if seo_comp.get('your_score', 100) < 50:
            threats.append({
                'category': 'seo',
                'title': self._threat_title('seo'),
                'severity': 'high' if seo_comp.get('your_score', 100) < 30 else 'medium',
                'score': seo_comp.get('your_score', 0),
                'impact': 'high',
                'effort': 'medium'
            })
        
        # Mobile threats
        if basic.get('mobile_ready') not in ['Kylla', 'Yes', True]:
            threats.append({
                'category': 'mobile',
                'title': self._threat_title('mobile'),
                'severity': 'high',
                'impact': 'high',
                'effort': 'medium'
            })
        
        # SSL threats
        if not tech.get('has_ssl'):
            threats.append({
                'category': 'ssl',
                'title': self._threat_title('ssl'),
                'severity': 'critical',
                'impact': 'critical',
                'effort': 'low'
            })
        
        # Performance threats
        perf_score = tech.get('performance_score', 50)
        if perf_score < 50:
            threats.append({
                'category': 'performance',
                'title': self._threat_title('performance'),
                'severity': 'high' if perf_score < 30 else 'medium',
                'score': perf_score,
                'impact': 'medium',
                'effort': 'high'
            })
        
        # Competitive threats
        your_score = benchmark.get('your_score', 0)
        avg_comp = benchmark.get('avg_competitor_score', 0)
        if your_score < avg_comp - 15:
            threats.append({
                'category': 'competitive',
                'title': self._threat_title('competitive'),
                'severity': 'high',
                'your_score': your_score,
                'competitor_avg': avg_comp,
                'gap': avg_comp - your_score,
                'impact': 'high',
                'effort': 'high'
            })
        
        # Content threats
        content_score = content.get('quality_score', 50)
        if content_score < 40:
            threats.append({
                'category': 'content',
                'title': self._threat_title('content'),
                'severity': 'medium',
                'score': content_score,
                'impact': 'medium',
                'effort': 'medium'
            })
        
        # AI Visibility threats (2025 priority)
        ai_score = self._calculate_ai_visibility_score(basic, tech, content)
        if ai_score < 40:
            threats.append({
                'category': 'ai_visibility',
                'title': self._threat_title('ai_visibility'),
                'severity': 'high' if ai_score < 25 else 'medium',
                'score': ai_score,
                'impact': 'high',  # Growing importance
                'effort': 'medium'
            })
        
        # Sort by severity
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        threats.sort(key=lambda x: severity_order.get(x.get('severity', 'low'), 3))
        
        return threats
    
    def _calculate_ai_visibility_score(
        self, 
        basic: Dict[str, Any], 
        tech: Dict[str, Any], 
        content: Dict[str, Any]
    ) -> int:
        """Calculate AI/GEO visibility score for threat detection."""
        ai_score = 0
        
        # Structured data
        if basic.get('has_schema') or tech.get('has_structured_data'):
            ai_score += 25
        
        # Content depth
        word_count = content.get('word_count', 0)
        if word_count >= 1500:
            ai_score += 20
        elif word_count >= 800:
            ai_score += 10
        
        # FAQ presence
        html_content = basic.get('html_content', '').lower()
        if 'faq' in html_content or 'frequently asked' in html_content:
            ai_score += 15
        
        # Clear structure
        if basic.get('h1_text'):
            ai_score += 15
        
        # Authority signals
        if 'author' in html_content or 'about us' in html_content:
            ai_score += 15
        
        # SSL
        if tech.get('has_ssl') or basic.get('has_ssl'):
            ai_score += 10
        
        return min(ai_score, 100)
    
    def _prioritize_actions(
        self,
        threats: List[Dict[str, Any]],
        risk_register: List[Any]
    ) -> List[Dict[str, Any]]:
        actions = []
        
        impact_scores = {'critical': 100, 'high': 75, 'medium': 50, 'low': 25}
        effort_scores = {'low': 100, 'medium': 60, 'high': 30}
        
        for threat in threats:
            impact = impact_scores.get(threat.get('impact', 'medium'), 50)
            effort = effort_scores.get(threat.get('effort', 'medium'), 60)
            
            roi_score = (impact * effort) / 100
            
            actions.append({
                'title': threat.get('title', ''),
                'category': threat.get('category', ''),
                'severity': threat.get('severity', 'medium'),
                'impact': threat.get('impact', 'medium'),
                'effort': threat.get('effort', 'medium'),
                'roi_score': roi_score
            })
        
        actions.sort(key=lambda x: x.get('roi_score', 0), reverse=True)
        
        return actions
    
    def _calculate_rasm_score(
        self,
        threats: List[Dict[str, Any]],
        analysis: Dict[str, Any]
    ) -> int:
        # Start with 100 and subtract based on threats
        score = 100
        
        severity_penalties = {'critical': 25, 'high': 15, 'medium': 8, 'low': 3}
        
        for threat in threats:
            severity = threat.get('severity', 'medium')
            penalty = severity_penalties.get(severity, 8)
            score -= penalty
        
        return max(0, min(100, score))
    
    # ========================================
    # COMPETITOR THREAT ASSESSMENT
    # ========================================
    
    async def _assess_competitor_threats(
        self,
        competitor_analyses: List[Dict[str, Any]],
        your_score: int,
        scout_data: Optional[Dict[str, Any]] = None,
        competitors_enriched: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Arvioi kilpailijoiden todellinen uhkataso.
        
        Ei riita, etta kilpailijan digitaalinen pistemaara on korkea.
        Pitaa myos arvioida: onko tama vakavasti otettava toimija?
        
        Uses real company intel (revenue, employees) when available.
        """
        if not competitor_analyses:
            return {
                'assessments': [],
                'summary': {'high': 0, 'medium': 0, 'low': 0}
            }
        
        # Build lookup for enriched data by URL/domain
        enriched_lookup = {}
        if competitors_enriched:
            for enriched in competitors_enriched:
                # Match by URL or domain
                url = enriched.get('url', '')
                domain = enriched.get('domain', '')
                if url:
                    enriched_lookup[url] = enriched
                if domain:
                    enriched_lookup[domain] = enriched
        
        assessments = []
        
        for comp in competitor_analyses:
            try:
                # Find matching enriched data
                comp_url = comp.get('url', '')
                comp_domain = comp.get('domain', '')
                enriched_data = enriched_lookup.get(comp_url) or enriched_lookup.get(comp_domain) or {}
                
                assessment = await self._assess_single_competitor(
                    competitor=comp,
                    your_score=your_score,
                    scout_data=scout_data,
                    enriched_data=enriched_data  # Pass real company intel
                )
                assessments.append(assessment)
            except Exception as e:
                logger.warning(f"[Guardian] Competitor assessment failed: {e}")
                continue
        
        # Sort by threat level (high first)
        threat_order = {'high': 0, 'medium': 1, 'low': 2}
        assessments.sort(key=lambda x: (threat_order.get(x['threat_level'], 2), -x['digital_score']))
        
        # Count by threat level
        summary = {'high': 0, 'medium': 0, 'low': 0}
        for a in assessments:
            level = a.get('threat_level', 'medium')
            summary[level] = summary.get(level, 0) + 1
        
        # Emit insights for top threats
        for assessment in assessments[:3]:
            self._emit_competitor_insight(assessment)
        
        # Emit summary
        insight_text = COMPETITOR_INSIGHTS['assessment_complete'][self._language].format(
            high=summary['high'],
            medium=summary['medium'],
            low=summary['low']
        )
        self._emit_insight(
            insight_text,
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data={'competitor_summary': summary}
        )
        
        return {
            'assessments': assessments,
            'summary': summary
        }
    
    async def _assess_single_competitor(
        self,
        competitor: Dict[str, Any],
        your_score: int,
        scout_data: Optional[Dict[str, Any]] = None,
        enriched_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Arvioi yksittaisen kilpailijan uhkataso.
        
        Uses real company intel (revenue, employees) when available from enriched_data.
        Falls back to HTML-based estimation when real data not available.
        """
        
        url = competitor.get('url', '')
        name = competitor.get('name', '') or self._extract_domain_name(url)
        digital_score = competitor.get('final_score', 0) or competitor.get('score', 0)
        
        # Get real company data if available
        real_revenue = None
        real_employees = None
        company_name = name
        
        if enriched_data:
            real_revenue = enriched_data.get('revenue')
            real_employees = enriched_data.get('employees')
            if enriched_data.get('name'):
                company_name = enriched_data.get('name')
            logger.info(f"[Guardian] Using real company intel for {company_name}: revenue={real_revenue}, employees={real_employees}")
        
        # Keraa signaalit
        signals = {
            'digital_score': digital_score,
            'score_diff': digital_score - your_score,  # Positive = they're ahead
            'domain_age': await self._check_domain_age(url),
            'company_size': self._get_company_size(competitor, enriched_data),  # Uses real data when available
            'growth_signals': self._detect_growth_signals(competitor),
            'trust_signals': self._detect_trust_signals(competitor),
            # Real company intel
            'real_revenue': real_revenue,
            'real_employees': real_employees,
            'has_real_data': bool(real_revenue or real_employees),
        }
        
        # Laske uhkataso (now uses real company intel)
        threat_score, reasoning = self._calculate_threat_level(signals)
        
        # Maarita threat level
        if threat_score >= 7:
            threat_level = 'high'
        elif threat_score >= 4:
            threat_level = 'medium'
        else:
            threat_level = 'low'
        
        return {
            'url': url,
            'name': company_name,
            'digital_score': digital_score,
            'score_diff': signals['score_diff'],
            'threat_score': threat_score,
            'threat_level': threat_level,
            'threat_label': THREAT_LEVEL_LABELS[threat_level][self._language],
            'signals': signals,
            'reasoning': reasoning,
            # Include real company data in output
            'company_intel': {
                'revenue': real_revenue,
                'employees': real_employees,
                'source': 'registry' if enriched_data else 'estimated'
            }
        }
    
    async def _check_domain_age(self, url: str) -> Dict[str, Any]:
        """Tarkista domainin ika WHOIS:sta"""
        try:
            import whois
            domain = urlparse(url).netloc or url
            domain = domain.replace('www.', '')
            
            w = whois.whois(domain)
            
            creation_date = w.creation_date
            if isinstance(creation_date, list):
                creation_date = creation_date[0]
            
            if creation_date:
                age_days = (datetime.now() - creation_date).days
                age_years = age_days / 365.25
                
                return {
                    'created': creation_date.isoformat() if hasattr(creation_date, 'isoformat') else str(creation_date),
                    'age_days': age_days,
                    'age_years': round(age_years, 1),
                    'is_established': age_years >= 2,  # 2+ vuotta = vakiintunut
                    'is_new': age_years < 1  # Alle vuosi = uusi
                }
        except Exception as e:
            logger.debug(f"[Guardian] WHOIS lookup failed for {url}: {e}")
        
        return {
            'created': None,
            'age_days': None,
            'age_years': None,
            'is_established': None,
            'is_new': None
        }
    
    def _get_company_size(
        self, 
        competitor: Dict[str, Any], 
        enriched_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get company size - uses real registry data when available,
        falls back to HTML-based estimation.
        """
        
        # If we have real data, use it
        if enriched_data:
            real_employees = enriched_data.get('employees')
            real_revenue = enriched_data.get('revenue')
            
            if real_employees or real_revenue:
                # Categorize by real data
                if real_employees:
                    if real_employees >= 50:
                        size_category = 'large'
                        estimated = '50+'
                    elif real_employees >= 20:
                        size_category = 'medium'
                        estimated = '20-50'
                    elif real_employees >= 5:
                        size_category = 'small'
                        estimated = '5-20'
                    else:
                        size_category = 'micro'
                        estimated = '1-5'
                elif real_revenue:
                    # Estimate from revenue (rough: €100k/employee)
                    if real_revenue >= 5_000_000:
                        size_category = 'large'
                        estimated = '50+'
                    elif real_revenue >= 2_000_000:
                        size_category = 'medium'
                        estimated = '20-50'
                    elif real_revenue >= 500_000:
                        size_category = 'small'
                        estimated = '5-20'
                    else:
                        size_category = 'micro'
                        estimated = '1-5'
                
                return {
                    'source': 'registry',
                    'real_employees': real_employees,
                    'real_revenue': real_revenue,
                    'size_category': size_category,
                    'estimated_employees': estimated,
                    'confidence': 'high'
                }
        
        # Fall back to HTML estimation
        estimated = self._estimate_company_size(competitor)
        estimated['source'] = 'estimated'
        estimated['confidence'] = 'low'
        return estimated
    
    def _estimate_company_size(self, competitor: Dict[str, Any]) -> Dict[str, Any]:
        """Arvioi yrityksen koko meta-signaaleista"""
        
        # Use correct keys from Analyst Agent output
        basic = competitor.get('basic_analysis', competitor.get('basic', {}))
        detailed = competitor.get('detailed_analysis', {})
        content = detailed.get('content_analysis', competitor.get('content', {}))
        
        signals = {
            'has_careers_page': False,
            'has_multiple_locations': False,
            'has_team_page': False,
            'content_volume': 'low',
            'estimated_employees': 'unknown'
        }
        
        # Tarkista sivustolta loytyvat signaalit
        page_count = basic.get('page_count', 0)
        word_count = content.get('word_count', 0)
        
        # Content volume arvioi
        if word_count > 10000 or page_count > 50:
            signals['content_volume'] = 'high'
            signals['estimated_employees'] = '20+'
        elif word_count > 3000 or page_count > 20:
            signals['content_volume'] = 'medium'
            signals['estimated_employees'] = '5-20'
        else:
            signals['content_volume'] = 'low'
            signals['estimated_employees'] = '1-5'
        
        # Muita signaaleja HTML:sta (jos saatavilla)
        html = basic.get('html_content', competitor.get('html', '')) or ''
        html_lower = html.lower()
        
        if any(term in html_lower for term in ['careers', 'jobs', 'tyopaikat', 'avoimet']):
            signals['has_careers_page'] = True
            signals['estimated_employees'] = '10+'
        
        if any(term in html_lower for term in ['our team', 'tiimimme', 'meet the team']):
            signals['has_team_page'] = True
        
        if any(term in html_lower for term in ['locations', 'toimipisteet', 'offices']):
            signals['has_multiple_locations'] = True
            signals['estimated_employees'] = '20+'
        
        return signals
    
    def _detect_growth_signals(self, competitor: Dict[str, Any]) -> Dict[str, Any]:
        """Tunnista kasvusignaalit"""
        
        signals = {
            'is_hiring': False,
            'recent_updates': False,
            'active_blog': False,
            'growth_indicators': []
        }
        
        # Get HTML from basic_analysis or fallback
        basic = competitor.get('basic_analysis', competitor.get('basic', {}))
        html = basic.get('html_content', competitor.get('html', '')) or ''
        html_lower = html.lower()
        
        # Get content from detailed_analysis
        detailed = competitor.get('detailed_analysis', {})
        content = detailed.get('content_analysis', competitor.get('content', {}))
        
        # Rekrytointi = kasvusignaali
        hiring_terms = ['hiring', 'we\'re hiring', 'join our team', 'rekrytoimme', 'tule meille', 'open positions']
        if any(term in html_lower for term in hiring_terms):
            signals['is_hiring'] = True
            signals['growth_indicators'].append('hiring')
        
        # Aktiivinen blogi
        blog_count = content.get('blog_count', 0)
        if blog_count > 5:
            signals['active_blog'] = True
            signals['growth_indicators'].append('active_content')
        
        # Recent updates (copyright year, last modified)
        current_year = datetime.now().year
        if str(current_year) in html or str(current_year - 1) in html:
            signals['recent_updates'] = True
        
        return signals
    
    def _detect_trust_signals(self, competitor: Dict[str, Any]) -> Dict[str, Any]:
        """Tunnista luottamussignaalit"""
        
        signals = {
            'has_ssl': False,
            'has_testimonials': False,
            'has_case_studies': False,
            'has_certifications': False,
            'trust_score': 0
        }
        
        # Get data from correct keys
        basic = competitor.get('basic_analysis', competitor.get('basic', {}))
        detailed = competitor.get('detailed_analysis', {})
        technical = detailed.get('technical_audit', competitor.get('technical', {}))
        html = basic.get('html_content', competitor.get('html', '')) or ''
        html_lower = html.lower()
        
        # SSL
        if technical.get('has_ssl') or basic.get('has_ssl'):
            signals['has_ssl'] = True
            signals['trust_score'] += 2
        
        # Testimonials / Reviews
        if any(term in html_lower for term in ['testimonial', 'review', 'asiakaspalaute', 'referenss']):
            signals['has_testimonials'] = True
            signals['trust_score'] += 2
        
        # Case studies
        if any(term in html_lower for term in ['case study', 'case studies', 'success story', 'asiakastarina']):
            signals['has_case_studies'] = True
            signals['trust_score'] += 3
        
        # Certifications
        if any(term in html_lower for term in ['certified', 'certification', 'iso', 'sertifioi']):
            signals['has_certifications'] = True
            signals['trust_score'] += 2
        
        return signals
    
    def _calculate_threat_level(self, signals: Dict[str, Any]) -> tuple:
        """
        Laske kilpailijan uhkataso 1-10.
        
        Korkea uhka = vahva digitaalinen lasnaolo + vakiintunut yritys + kasvusignaalit + resurssit
        Matala uhka = heikko lasnaolo TAI uusi startup ilman resursseja
        
        Uses real company intel (revenue, employees) when available for more accurate assessment.
        """
        score = 5  # Baseline
        reasons = []
        
        # 1. Digitaalinen pistemaara vs. sinun
        score_diff = signals.get('score_diff', 0)
        if score_diff > 20:
            score += 2
            reasons.append(f"+{score_diff} points ahead" if self._language == 'en' else f"+{score_diff} pistetta edella")
        elif score_diff > 10:
            score += 1
            reasons.append(f"+{score_diff} points ahead" if self._language == 'en' else f"+{score_diff} pistetta edella")
        elif score_diff < -20:
            score -= 2
            reasons.append(f"{score_diff} points behind" if self._language == 'en' else f"{score_diff} pistetta jaljessa")
        elif score_diff < -10:
            score -= 1
        
        # 2. Domain-ika
        domain_age = signals.get('domain_age', {})
        if domain_age.get('is_established'):
            score += 1.5
            years = domain_age.get('age_years', 0)
            reasons.append(f"est. {years:.0f}+ years" if self._language == 'en' else f"perustettu {years:.0f}+ v sitten")
        elif domain_age.get('is_new'):
            score -= 1.5
            reasons.append("new player" if self._language == 'en' else "uusi toimija")
        
        # 3. Yrityksen koko - PREFER REAL DATA
        company_size = signals.get('company_size', {})
        real_revenue = signals.get('real_revenue')
        real_employees = signals.get('real_employees')
        
        if real_revenue or real_employees:
            # Use real data - more accurate threat assessment
            if real_revenue:
                if real_revenue >= 5_000_000:
                    score += 2.5
                    reasons.append(f"€{real_revenue/1_000_000:.1f}M revenue" if self._language == 'en' else f"€{real_revenue/1_000_000:.1f}M liikevaihto")
                elif real_revenue >= 1_000_000:
                    score += 1.5
                    reasons.append(f"€{real_revenue/1_000_000:.1f}M revenue" if self._language == 'en' else f"€{real_revenue/1_000_000:.1f}M liikevaihto")
                elif real_revenue >= 500_000:
                    score += 0.5
                elif real_revenue < 200_000:
                    score -= 1
                    reasons.append("small revenue" if self._language == 'en' else "pieni liikevaihto")
            
            if real_employees:
                if real_employees >= 50:
                    score += 1.5
                    reasons.append(f"{real_employees} employees" if self._language == 'en' else f"{real_employees} tyontekijaa")
                elif real_employees >= 20:
                    score += 1
                    reasons.append(f"{real_employees} employees" if self._language == 'en' else f"{real_employees} tyontekijaa")
                elif real_employees <= 3:
                    score -= 0.5
        else:
            # Fallback to estimated data
            employees = company_size.get('estimated_employees', 'unknown')
            if employees == '20+' or employees == '50+':
                score += 1.5
                reasons.append(f"~{employees} employees" if self._language == 'en' else f"~{employees} tyontekijaa")
            elif employees == '1-5':
                score -= 1
        
        # 4. Kasvusignaalit
        growth = signals.get('growth_signals', {})
        if growth.get('is_hiring'):
            score += 1
            reasons.append("actively hiring" if self._language == 'en' else "rekrytoi aktiivisesti")
        if growth.get('active_blog'):
            score += 0.5
        
        # 5. Trust signals
        trust = signals.get('trust_signals', {})
        if trust.get('has_case_studies'):
            score += 1
            reasons.append("proven track record" if self._language == 'en' else "referensseja")
        if trust.get('trust_score', 0) >= 5:
            score += 0.5
        
        # Rajoita 1-10
        score = max(1, min(10, round(score)))
        
        # Yhdista syyt
        reasoning = ", ".join(reasons[:3]) if reasons else ("no strong signals" if self._language == 'en' else "ei vahvoja signaaleja")
        
        return score, reasoning
    
    def _emit_competitor_insight(self, assessment: Dict[str, Any]):
        """Laheta insight kilpailija-arvioinnista"""
        
        level = assessment['threat_level']
        name = assessment['name']
        label = assessment['threat_label']
        score = assessment['digital_score']
        reasoning = assessment['reasoning']
        
        insight_key = f"{level}_threat"
        insight_text = COMPETITOR_INSIGHTS[insight_key][self._language].format(
            name=name,
            label=label,
            score=score,
            reason=reasoning
        )
        
        priority = {
            'high': AgentPriority.HIGH,
            'medium': AgentPriority.MEDIUM,
            'low': AgentPriority.LOW
        }.get(level, AgentPriority.MEDIUM)
        
        self._emit_insight(
            insight_text,
            priority=priority,
            insight_type=InsightType.THREAT if level == 'high' else InsightType.FINDING,
            data={
                'competitor': name,
                'threat_level': level,
                'threat_score': assessment['threat_score'],
                'digital_score': score,
                'signals': assessment['signals']
            }
        )
    
    def _extract_domain_name(self, url: str) -> str:
        """Pura domain nimeksi"""
        try:
            domain = urlparse(url).netloc or url
            domain = domain.replace('www.', '')
            # example.com -> Example
            name = domain.split('.')[0].capitalize()
            return name
        except:
            return url
