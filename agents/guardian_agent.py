"""
Growth Engine 2.0 - Guardian Agent
🛡️ "The Risk Manager" - RASM™, uhka-analyysi ja Competitor Threat Assessment
"""

import logging
import asyncio
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from .base_agent import BaseAgent
from .types import (
    AnalysisContext,
    AgentPriority,
    InsightType
)

logger = logging.getLogger(__name__)


GUARDIAN_TASKS = {
    "building_risk_register": {"fi": "Rakennetaan riskiregisteriä...", "en": "Building risk register..."},
    "calculating_impact": {"fi": "Lasketaan liikevaihtovaikutusta...", "en": "Calculating revenue impact..."},
    "identifying_threats": {"fi": "Tunnistetaan uhkia...", "en": "Identifying threats..."},
    "prioritizing_actions": {"fi": "Priorisoidaan toimenpiteitä...", "en": "Prioritizing actions..."},
    "calculating_rasm": {"fi": "Lasketaan RASM-pistemäärää...", "en": "Calculating RASM score..."},
    "assessing_competitors": {"fi": "Arvioidaan kilpailijoiden uhkatasoa...", "en": "Assessing competitor threat levels..."},
}

THREAT_TITLES = {
    "seo": {"fi": "Heikko hakukonenäkyvyys", "en": "Poor search engine visibility"},
    "mobile": {"fi": "Puutteellinen mobiilioptimointi", "en": "Inadequate mobile optimization"},
    "ssl": {"fi": "SSL-sertifikaatti puuttuu", "en": "SSL certificate missing"},
    "performance": {"fi": "Hidas sivusto", "en": "Slow website"},
    "competitive": {"fi": "Jäät kilpailijoista jälkeen", "en": "Falling behind competitors"},
    "content": {"fi": "Heikko sisällön laatu", "en": "Poor content quality"},
}

THREAT_LEVEL_LABELS = {
    "high": {"fi": "KORKEA UHKA", "en": "HIGH THREAT"},
    "medium": {"fi": "KOHTALAINEN UHKA", "en": "MEDIUM THREAT"},
    "low": {"fi": "MATALA UHKA", "en": "LOW THREAT"},
}

COMPETITOR_INSIGHTS = {
    "high_threat": {
        "fi": "🔴 {name}: {label} — Pisteet {score}/100, {reason}",
        "en": "🔴 {name}: {label} — Score {score}/100, {reason}"
    },
    "medium_threat": {
        "fi": "🟡 {name}: {label} — Pisteet {score}/100, {reason}",
        "en": "🟡 {name}: {label} — Score {score}/100, {reason}"
    },
    "low_threat": {
        "fi": "🟢 {name}: {label} — Pisteet {score}/100, {reason}",
        "en": "🟢 {name}: {label} — Score {score}/100, {reason}"
    },
    "assessment_complete": {
        "fi": "🎯 Kilpailija-arviointi valmis: {high} korkean uhkan, {medium} kohtalaisen, {low} matalan",
        "en": "🎯 Competitor assessment complete: {high} high threat, {medium} medium, {low} low"
    },
}

# ============================================================================
# GUARDIAN TRANSLATIONS - used by _t() method
# ============================================================================
GUARDIAN_TRANSLATIONS = {
    "guardian.no_data": {
        "fi": "⚠️ Ei analyysidataa saatavilla riskiarviointiin",
        "en": "⚠️ No analysis data available for risk assessment"
    },
    "guardian.starting_rasm": {
        "fi": "🛡️ Aloitetaan Revenue Attack Surface Mapping...",
        "en": "🛡️ Starting Revenue Attack Surface Mapping..."
    },
    "guardian.risk_critical": {
        "fi": "🚨 KRIITTINEN: €{amount} vuosittainen liikevaihtoriski tunnistettu!",
        "en": "🚨 CRITICAL: €{amount} annual revenue at risk identified!"
    },
    "guardian.risk_high": {
        "fi": "⚠️ KORKEA RISKI: €{amount} vuosittainen liikevaihtoriski",
        "en": "⚠️ HIGH RISK: €{amount} annual revenue at risk"
    },
    "guardian.risk_medium": {
        "fi": "🟡 Kohtalainen riski: €{amount} vuosittainen liikevaihtovaikutus",
        "en": "🟡 Moderate risk: €{amount} annual revenue impact"
    },
    "guardian.threat_critical": {
        "fi": "🚨 KRIITTINEN UHKA [{category}]: {title}",
        "en": "🚨 CRITICAL THREAT [{category}]: {title}"
    },
    "guardian.threat_high": {
        "fi": "⚠️ KORKEA UHKA [{category}]: {title}",
        "en": "⚠️ HIGH THREAT [{category}]: {title}"
    },
    "guardian.priority_action": {
        "fi": "🎯 Prioriteetti #{idx}: {title} (ROI: {roi}x)",
        "en": "🎯 Priority #{idx}: {title} (ROI: {roi}x)"
    },
    "guardian.complete": {
        "fi": "✅ Riskianalyysi valmis: {count} uhkaa tunnistettu, RASM-pistemäärä: {score}/100",
        "en": "✅ Risk analysis complete: {count} threats identified, RASM score: {score}/100"
    },
    "guardian.competitor_assessment_complete": {
        "fi": "🎯 Kilpailija-arviointi valmis",
        "en": "🎯 Competitor assessment complete"
    },
}


class GuardianAgent(BaseAgent):
    """
    🛡️ Guardian Agent - Riskienhallitsija (RASM)
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
        self._language = 'en'  # Default language, updated in execute()
    
    def _t(self, key: str, **kwargs) -> str:
        """
        Get translation for key with optional format arguments.
        
        Usage:
            self._t("guardian.risk_critical", amount="50,000")
            self._t("guardian.complete", count=5, score=75)
        """
        translation = GUARDIAN_TRANSLATIONS.get(key, {}).get(self._language)
        
        if not translation:
            # Fallback to English
            translation = GUARDIAN_TRANSLATIONS.get(key, {}).get('en', key)
        
        if not translation:
            # If still no translation, return the key itself
            return key
        
        # Format with kwargs if provided
        if kwargs:
            try:
                return translation.format(**kwargs)
            except KeyError as e:
                logger.warning(f"[Guardian] Translation format error for {key}: {e}")
                return translation
        
        return translation
    
    def _task(self, key: str) -> str:
        return GUARDIAN_TASKS.get(key, {}).get(self._language, key)
    
    def _threat_title(self, key: str) -> str:
        return THREAT_TITLES.get(key, {}).get(self._language, key)
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        # Update language from context
        self._language = getattr(context, 'language', 'en') or 'en'
        
        from main import build_risk_register
        
        analyst_results = self.get_dependency_results(context, 'analyst')
        scout_results = self.get_dependency_results(context, 'scout')
        
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
        
        self._update_progress(15, self._task("building_risk_register"))
        
        self._emit_insight(
            self._t("guardian.starting_rasm"),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # 1. Rakenna riskiregisteri
        try:
            risk_register = build_risk_register(
                your_analysis.get('basic', {}),
                your_analysis.get('technical', {}),
                your_analysis.get('content', {}),
                self._language  # Use already extracted language
            )
        except Exception as e:
            logger.error(f"[Guardian] Risk register error: {e}")
            risk_register = []
        
        self._update_progress(30, self._task("calculating_impact"))
        
        # 2. Laske revenue impact
        annual_revenue = 500000  # Default €500k
        
        # Try new calculation method first, fallback to simple calculation
        try:
            # Calculate annual risk from risk_register items
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
        except Exception as e:
            logger.warning(f"[Guardian] Risk calculation fallback: {e}")
            business_impact = {
                'total_monthly_risk': 0,
                'total_annual_risk': 0
            }
        
        annual_risk = business_impact.get('total_annual_risk', 0)
        
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
            scout_data=scout_results
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
        
        # 5. Laske RASM-pistemäärä
        rasm_score = self._calculate_rasm_score(threats, your_analysis)
        
        self._emit_insight(
            self._t("guardian.complete", count=len(threats), score=rasm_score),
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data={'threat_count': len(threats), 'rasm_score': rasm_score}
        )
        
        return {
            'threats': threats,
            'risk_register': risk_register,
            'revenue_impact': business_impact,
            'priority_actions': priority_actions,
            'rasm_score': rasm_score,
            'competitor_threat_assessment': competitor_threat_assessment
        }
    
    def _identify_threats(
        self,
        analysis: Dict[str, Any],
        benchmark: Dict[str, Any],
        category_comparison: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        threats = []
        
        basic = analysis.get('basic', {})
        tech = analysis.get('technical', {})
        content = analysis.get('content', {})
        
        # SEO threats
        seo_comp = category_comparison.get('seo', {})
        if seo_comp.get('your_score', 100) < 50:
            threats.append({
                'category': 'seo',
                'title': self._threat_title('seo'),
                'severity': 'high' if seo_comp.get('your_score', 100) < 30 else 'medium',
                'score': seo_comp.get('your_score', 0),
                'impact': 'high',
                'description': 'SEO optimization needed',
                'recommendation': 'Improve meta tags, headings, and content structure'
            })
        
        # Mobile threats
        mobile_comp = category_comparison.get('mobile', {})
        if mobile_comp.get('your_score', 100) < 50:
            threats.append({
                'category': 'mobile',
                'title': self._threat_title('mobile'),
                'severity': 'high' if mobile_comp.get('your_score', 100) < 30 else 'medium',
                'score': mobile_comp.get('your_score', 0),
                'impact': 'high',
                'description': 'Mobile optimization needed',
                'recommendation': 'Implement responsive design and mobile-first approach'
            })
        
        # SSL threat
        if not tech.get('has_ssl', True):
            threats.append({
                'category': 'ssl',
                'title': self._threat_title('ssl'),
                'severity': 'critical',
                'score': 0,
                'impact': 'critical',
                'description': 'SSL certificate missing',
                'recommendation': 'Install SSL certificate immediately'
            })
        
        # Performance threats
        perf_comp = category_comparison.get('performance', {})
        if perf_comp.get('your_score', 100) < 50:
            threats.append({
                'category': 'performance',
                'title': self._threat_title('performance'),
                'severity': 'medium',
                'score': perf_comp.get('your_score', 0),
                'impact': 'medium',
                'description': 'Website performance issues',
                'recommendation': 'Optimize images, reduce scripts, enable caching'
            })
        
        # Content threats
        content_comp = category_comparison.get('content', {})
        if content_comp.get('your_score', 100) < 40:
            threats.append({
                'category': 'content',
                'title': self._threat_title('content'),
                'severity': 'medium',
                'score': content_comp.get('your_score', 0),
                'impact': 'medium',
                'description': 'Content quality issues',
                'recommendation': 'Improve content depth and quality'
            })
        
        # Competitive threat
        avg_score = benchmark.get('avg_score', 0)
        your_score = analysis.get('score', 0)
        if your_score < avg_score - 10:
            threats.append({
                'category': 'competitive',
                'title': self._threat_title('competitive'),
                'severity': 'high' if your_score < avg_score - 20 else 'medium',
                'score': your_score,
                'impact': 'high',
                'description': f'Score {your_score} vs industry avg {avg_score}',
                'recommendation': 'Focus on closing the gap with competitors'
            })
        
        return sorted(threats, key=lambda x: {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}.get(x.get('severity', 'low'), 4))
    
    async def _assess_competitor_threats(
        self,
        competitor_analyses: List[Dict[str, Any]],
        your_score: int,
        scout_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Arvioi kilpailijoiden uhkataso käyttäen moniulotteista signaalien analyysiä.
        """
        
        assessments = []
        threat_counts = {'high': 0, 'medium': 0, 'low': 0}
        
        for competitor in competitor_analyses:
            url = competitor.get('url', '')
            domain = urlparse(url).netloc.replace('www.', '') if url else 'unknown'
            
            # Kerää signaalit
            signals = {
                'digital_score': competitor.get('score', 0),
                'score_diff': competitor.get('score', 0) - your_score,
                'domain_age': self._analyze_domain_age(domain, scout_data),
                'company_size': self._estimate_company_size(competitor),
                'growth_signals': self._detect_growth_signals(competitor),
                'trust_signals': self._detect_trust_signals(competitor)
            }
            
            # Laske uhkataso
            threat_score, reasoning = self._calculate_threat_level(signals)
            
            # Määritä uhkataso
            if threat_score >= 7:
                threat_level = 'high'
            elif threat_score >= 4:
                threat_level = 'medium'
            else:
                threat_level = 'low'
            
            threat_counts[threat_level] += 1
            
            assessment = {
                'domain': domain,
                'url': url,
                'name': self._extract_domain_name(url),
                'digital_score': signals['digital_score'],
                'threat_score': threat_score,
                'threat_level': threat_level,
                'threat_label': THREAT_LEVEL_LABELS[threat_level][self._language],
                'reasoning': reasoning,
                'signals': signals
            }
            
            assessments.append(assessment)
            
            # Emit insight for high threats
            if threat_level == 'high':
                self._emit_competitor_insight(assessment)
        
        # Sort by threat score
        assessments.sort(key=lambda x: x['threat_score'], reverse=True)
        
        # Emit summary
        summary_text = COMPETITOR_INSIGHTS["assessment_complete"][self._language].format(
            high=threat_counts['high'],
            medium=threat_counts['medium'],
            low=threat_counts['low']
        )
        
        self._emit_insight(
            summary_text,
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING,
            data=threat_counts
        )
        
        return {
            'assessments': assessments,
            'threat_counts': threat_counts,
            'highest_threat': assessments[0] if assessments else None
        }
    
    def _prioritize_actions(
        self,
        threats: List[Dict[str, Any]],
        risk_register: List[Any]
    ) -> List[Dict[str, Any]]:
        """Priorisoi toimenpiteet ROI:n perusteella"""
        
        actions = []
        
        for threat in threats:
            # Calculate ROI score (impact / effort)
            impact_scores = {'critical': 10, 'high': 7, 'medium': 4, 'low': 1}
            impact = impact_scores.get(threat.get('impact', 'low'), 1)
            
            # Estimate effort (1-10, lower is easier)
            effort = 5  # Default medium effort
            
            roi_score = impact / effort * 10
            
            actions.append({
                'title': threat.get('title', 'Unknown'),
                'category': threat.get('category', ''),
                'roi_score': roi_score,
                'impact': threat.get('impact', 'medium'),
                'recommendation': threat.get('recommendation', ''),
                'threat_severity': threat.get('severity', 'medium')
            })
        
        # Sort by ROI score
        return sorted(actions, key=lambda x: x['roi_score'], reverse=True)
    
    def _calculate_rasm_score(
        self,
        threats: List[Dict[str, Any]],
        analysis: Dict[str, Any]
    ) -> int:
        """
        Calculate Revenue Attack Surface Mapping score (0-100).
        Higher score = more protected, lower attack surface.
        """
        
        base_score = 100
        
        # Deduct for each threat
        severity_deductions = {'critical': 25, 'high': 15, 'medium': 8, 'low': 3}
        
        for threat in threats:
            severity = threat.get('severity', 'low')
            deduction = severity_deductions.get(severity, 3)
            base_score -= deduction
        
        # Ensure score is between 0 and 100
        return max(0, min(100, base_score))
    
    def _analyze_domain_age(self, domain: str, scout_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analysoi domain-ikä (arvio)"""
        
        result = {
            'domain': domain,
            'is_established': False,
            'is_new': False,
            'age_years': 0
        }
        
        # Simple heuristics based on domain characteristics
        # In production, you'd use WHOIS data
        if any(tld in domain for tld in ['.fi', '.com', '.eu']):
            # Assume established if common TLD
            result['is_established'] = True
            result['age_years'] = 5
        
        return result
    
    def _estimate_company_size(self, competitor: Dict[str, Any]) -> Dict[str, Any]:
        """Arvioi yrityksen koko signaalien perusteella"""
        
        signals = {
            'estimated_employees': 'unknown',
            'content_volume': 'unknown'
        }
        
        content = competitor.get('content', {})
        word_count = content.get('word_count', 0)
        
        if word_count > 2000:
            signals['content_volume'] = 'high'
            signals['estimated_employees'] = '10+'
        elif word_count > 500:
            signals['content_volume'] = 'medium'
            signals['estimated_employees'] = '5-10'
        else:
            signals['content_volume'] = 'low'
            signals['estimated_employees'] = '1-5'
        
        # Muita signaaleja HTML:stä (jos saatavilla)
        html = competitor.get('html', '') or ''
        html_lower = html.lower()
        
        if any(term in html_lower for term in ['careers', 'jobs', 'työpaikat', 'avoimet']):
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
        
        html = competitor.get('html', '') or ''
        html_lower = html.lower()
        content = competitor.get('content', {})
        
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
        
        technical = competitor.get('technical', {})
        html = competitor.get('html', '') or ''
        html_lower = html.lower()
        
        # SSL
        if technical.get('has_ssl'):
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
        
        Korkea uhka = vahva digitaalinen läsnäolo + vakiintunut yritys + kasvusignaalit
        Matala uhka = heikko läsnäolo TAI uusi startup ilman resursseja
        """
        score = 5  # Baseline
        reasons = []
        
        # 1. Digitaalinen pistemäärä vs. sinun
        score_diff = signals.get('score_diff', 0)
        if score_diff > 20:
            score += 2
            reasons.append(f"+{score_diff} points ahead" if self._language == 'en' else f"+{score_diff} pistettä edellä")
        elif score_diff > 10:
            score += 1
            reasons.append(f"+{score_diff} points ahead" if self._language == 'en' else f"+{score_diff} pistettä edellä")
        elif score_diff < -20:
            score -= 2
            reasons.append(f"{score_diff} points behind" if self._language == 'en' else f"{score_diff} pistettä jäljessä")
        elif score_diff < -10:
            score -= 1
        
        # 2. Domain-ikä
        domain_age = signals.get('domain_age', {})
        if domain_age.get('is_established'):
            score += 1.5
            years = domain_age.get('age_years', 0)
            reasons.append(f"est. {years:.0f}+ years" if self._language == 'en' else f"perustettu {years:.0f}+ v sitten")
        elif domain_age.get('is_new'):
            score -= 1.5
            reasons.append("new player" if self._language == 'en' else "uusi toimija")
        
        # 3. Yrityksen koko
        company_size = signals.get('company_size', {})
        employees = company_size.get('estimated_employees', 'unknown')
        if employees == '20+':
            score += 1.5
            reasons.append(f"~{employees} employees" if self._language == 'en' else f"~{employees} työntekijää")
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
            reasons.append("proven track record" if self._language == 'en' else "referenssejä")
        if trust.get('trust_score', 0) >= 5:
            score += 0.5
        
        # Rajoita 1-10
        score = max(1, min(10, round(score)))
        
        # Yhdistä syyt
        reasoning = ", ".join(reasons[:3]) if reasons else ("no strong signals" if self._language == 'en' else "ei vahvoja signaaleja")
        
        return score, reasoning
    
    def _emit_competitor_insight(self, assessment: Dict[str, Any]):
        """Lähetä insight kilpailija-arvioinnista"""
        
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
