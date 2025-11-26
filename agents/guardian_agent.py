"""
Growth Engine 2.0 - Guardian Agent
🛡️ "The Risk Manager" - RASM™ + Competitor Threat Assessment
Uses: build_risk_register(), compute_business_impact()
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse

from .base_agent import BaseAgent
from .types import AnalysisContext, AgentPriority, InsightType

logger = logging.getLogger(__name__)


class GuardianAgent(BaseAgent):
    """
    🛡️ Guardian Agent - Risk Manager
    
    Responsibilities:
    - Build risk register from analysis
    - Calculate revenue impact (RASM)
    - Identify threats and vulnerabilities
    - Assess competitor threat levels
    - Prioritize actions by ROI
    """
    
    def __init__(self):
        super().__init__(
            agent_id="guardian",
            name="Guardian",
            role="Risk Manager",
            avatar="🛡️",
            personality="Vigilant security expert who spots risks before they become problems"
        )
        self.dependencies = ['scout', 'analyst']
    
    async def execute(self, context: AnalysisContext) -> Dict[str, Any]:
        """Perform risk analysis and competitor threat assessment"""
        
        from main import compute_business_impact, build_risk_register
        
        analyst_results = self.get_dependency_results(context, 'analyst')
        scout_results = self.get_dependency_results(context, 'scout')
        
        if not analyst_results:
            self._emit_insight(
                "⚠️ No Analyst data — limited risk assessment",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.THREAT
            )
            return {'threats': [], 'risk_register': [], 'rasm_score': 0}
        
        your_analysis = analyst_results.get('your_analysis', {})
        competitor_analyses = analyst_results.get('competitor_analyses', [])
        your_score = analyst_results.get('your_score', 0)
        
        self._emit_insight(
            "🛡️ Starting risk analysis — scanning for vulnerabilities...",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.FINDING
        )
        
        # 1. Build risk register
        self._update_progress(15, "Building risk register...")
        
        try:
            basic = your_analysis.get('basic_analysis', {})
            technical = your_analysis.get('detailed_analysis', {}).get('technical_audit', {})
            content = your_analysis.get('detailed_analysis', {}).get('content_analysis', {})
            
            risk_register = build_risk_register(basic, technical, content, 'en')
            
            self._emit_insight(
                f"📋 Identified {len(risk_register)} risk items",
                priority=AgentPriority.LOW,
                insight_type=InsightType.FINDING
            )
        except Exception as e:
            logger.error(f"[Guardian] Risk register error: {e}")
            risk_register = []
        
        # 2. Calculate revenue impact
        self._update_progress(30, "Calculating revenue impact...")
        
        annual_revenue = 500000  # Default €500k - could be user input
        
        try:
            business_impact = compute_business_impact(risk_register, annual_revenue)
            annual_risk = business_impact.get('total_annual_risk', 0)
            
            if annual_risk > 50000:
                self._emit_insight(
                    f"🚨 CRITICAL: €{annual_risk:,.0f}/year at risk!",
                    priority=AgentPriority.CRITICAL,
                    insight_type=InsightType.THREAT,
                    data={'annual_risk': annual_risk}
                )
            elif annual_risk > 20000:
                self._emit_insight(
                    f"⚠️ HIGH RISK: €{annual_risk:,.0f}/year exposure identified",
                    priority=AgentPriority.HIGH,
                    insight_type=InsightType.THREAT,
                    data={'annual_risk': annual_risk}
                )
            elif annual_risk > 0:
                self._emit_insight(
                    f"📊 Moderate risk: €{annual_risk:,.0f}/year exposure",
                    priority=AgentPriority.MEDIUM,
                    insight_type=InsightType.FINDING,
                    data={'annual_risk': annual_risk}
                )
        except Exception as e:
            logger.error(f"[Guardian] Business impact error: {e}")
            business_impact = {'total_monthly_risk': 0, 'total_annual_risk': 0}
            annual_risk = 0
        
        # 3. Identify specific threats
        self._update_progress(45, "Identifying threats...")
        
        threats = self._identify_threats(your_analysis, analyst_results.get('category_comparison', {}))
        
        for threat in threats[:5]:
            severity = threat.get('severity', 'medium')
            title = threat.get('title', 'Unknown threat')
            
            if severity == 'critical':
                self._emit_insight(
                    f"🔴 CRITICAL: {title}",
                    priority=AgentPriority.CRITICAL,
                    insight_type=InsightType.THREAT,
                    data=threat
                )
            elif severity == 'high':
                self._emit_insight(
                    f"🟠 HIGH: {title}",
                    priority=AgentPriority.HIGH,
                    insight_type=InsightType.THREAT,
                    data=threat
                )
        
        # 4. Competitor Threat Assessment
        self._update_progress(60, "Assessing competitor threats...")
        
        competitor_threat_assessment = await self._assess_competitor_threats(
            competitor_analyses=competitor_analyses,
            your_score=your_score
        )
        
        # 5. Prioritize actions
        self._update_progress(80, "Prioritizing actions...")
        
        priority_actions = self._prioritize_actions(threats, risk_register)
        
        for idx, action in enumerate(priority_actions[:3]):
            roi = action.get('roi_score', 0)
            self._emit_insight(
                f"💡 Priority #{idx + 1}: {action.get('title', '')} (ROI: {roi:.1f}x)",
                priority=AgentPriority.HIGH,
                insight_type=InsightType.RECOMMENDATION,
                data=action
            )
        
        # 6. Calculate RASM score
        self._update_progress(90, "Calculating RASM score...")
        
        rasm_score = self._calculate_rasm_score(threats)
        
        self._emit_insight(
            f"🛡️ RASM Score: {rasm_score}/100 — "
            f"{len(threats)} threats identified, "
            f"{len(priority_actions)} actions recommended",
            priority=AgentPriority.MEDIUM,
            insight_type=InsightType.METRIC,
            data={'rasm_score': rasm_score, 'threat_count': len(threats)}
        )
        
        return {
            'threats': threats,
            'risk_register': [r.dict() if hasattr(r, 'dict') else r for r in risk_register],
            'revenue_impact': business_impact,
            'priority_actions': priority_actions,
            'rasm_score': rasm_score,
            'competitor_threat_assessment': competitor_threat_assessment
        }
    
    def _identify_threats(
        self, 
        analysis: Dict[str, Any],
        category_comparison: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Identify specific threats from analysis"""
        threats = []
        
        basic = analysis.get('basic_analysis', {})
        detailed = analysis.get('detailed_analysis', {})
        tech = detailed.get('technical_audit', {})
        
        # SSL threat
        if not tech.get('has_ssl', True):
            threats.append({
                'category': 'security',
                'title': 'Missing SSL certificate',
                'severity': 'critical',
                'impact': 'critical',
                'effort': 'low'
            })
        
        # Mobile threat
        if basic.get('mobile_ready') not in ['Yes', True, 'Kyllä']:
            threats.append({
                'category': 'mobile',
                'title': 'Poor mobile experience',
                'severity': 'high',
                'impact': 'high',
                'effort': 'medium'
            })
        
        # Performance threat
        perf_score = tech.get('performance_score', 50)
        if perf_score < 50:
            threats.append({
                'category': 'performance',
                'title': f'Slow page speed (score: {perf_score})',
                'severity': 'high' if perf_score < 30 else 'medium',
                'impact': 'high',
                'effort': 'medium'
            })
        
        # SEO threat
        seo_comp = category_comparison.get('seo', {})
        if seo_comp.get('status') == 'behind' and seo_comp.get('diff', 0) < -15:
            threats.append({
                'category': 'seo',
                'title': 'Weak search visibility vs competitors',
                'severity': 'high',
                'impact': 'high',
                'effort': 'medium'
            })
        
        # Content threat
        content_comp = category_comparison.get('content', {})
        if content_comp.get('status') == 'behind' and content_comp.get('diff', 0) < -15:
            threats.append({
                'category': 'content',
                'title': 'Thin content compared to competitors',
                'severity': 'medium',
                'impact': 'medium',
                'effort': 'high'
            })
        
        return threats
    
    async def _assess_competitor_threats(
        self,
        competitor_analyses: List[Dict[str, Any]],
        your_score: int
    ) -> Dict[str, Any]:
        """Assess competitor threat levels"""
        
        if not competitor_analyses:
            return {'assessments': [], 'summary': {'high': 0, 'medium': 0, 'low': 0}}
        
        assessments = []
        
        for comp in competitor_analyses:
            try:
                assessment = await self._assess_single_competitor(comp, your_score)
                assessments.append(assessment)
            except Exception as e:
                logger.warning(f"[Guardian] Competitor assessment failed: {e}")
                continue
        
        # Sort by threat level
        threat_order = {'high': 0, 'medium': 1, 'low': 2}
        assessments.sort(key=lambda x: (threat_order.get(x['threat_level'], 2), -x['digital_score']))
        
        # Count by level
        summary = {'high': 0, 'medium': 0, 'low': 0}
        for a in assessments:
            level = a.get('threat_level', 'medium')
            summary[level] = summary.get(level, 0) + 1
        
        # Emit insights for top threats
        for assessment in assessments[:3]:
            self._emit_competitor_insight(assessment)
        
        if assessments:
            self._emit_insight(
                f"🎯 Competitor assessment: {summary['high']} high threat, "
                f"{summary['medium']} medium, {summary['low']} low",
                priority=AgentPriority.MEDIUM,
                insight_type=InsightType.FINDING,
                data={'summary': summary}
            )
        
        return {'assessments': assessments, 'summary': summary}
    
    async def _assess_single_competitor(
        self, 
        competitor: Dict[str, Any], 
        your_score: int
    ) -> Dict[str, Any]:
        """Assess a single competitor's threat level"""
        
        url = competitor.get('url', '')
        name = competitor.get('name', self._extract_domain_name(url))
        digital_score = competitor.get('score', 0)
        score_diff = digital_score - your_score
        
        # Check domain age
        domain_age = await self._check_domain_age(url)
        
        # Estimate company size from signals
        company_size = self._estimate_company_size(competitor)
        
        # Detect growth signals
        growth_signals = self._detect_growth_signals(competitor)
        
        # Calculate threat level
        threat_score = 5  # Baseline
        reasons = []
        
        # Score difference
        if score_diff > 20:
            threat_score += 2
            reasons.append(f"+{score_diff} points ahead")
        elif score_diff > 10:
            threat_score += 1
            reasons.append(f"+{score_diff} points ahead")
        elif score_diff < -20:
            threat_score -= 2
            reasons.append(f"{abs(score_diff)} points behind")
        
        # Domain age
        if domain_age.get('is_established'):
            threat_score += 1.5
            years = domain_age.get('age_years', 0)
            reasons.append(f"est. {years:.0f}+ years")
        elif domain_age.get('is_new'):
            threat_score -= 1.5
            reasons.append("new player")
        
        # Company size
        if company_size.get('estimated_employees') == '20+':
            threat_score += 1.5
            reasons.append(f"~{company_size.get('estimated_employees')} employees")
        
        # Growth signals
        if growth_signals.get('is_hiring'):
            threat_score += 1
            reasons.append("actively hiring")
        
        threat_score = max(1, min(10, round(threat_score)))
        
        if threat_score >= 7:
            threat_level = 'high'
        elif threat_score >= 4:
            threat_level = 'medium'
        else:
            threat_level = 'low'
        
        return {
            'url': url,
            'name': name,
            'digital_score': digital_score,
            'score_diff': score_diff,
            'threat_score': threat_score,
            'threat_level': threat_level,
            'reasoning': ', '.join(reasons[:3]) if reasons else 'no strong signals',
            'signals': {
                'domain_age': domain_age,
                'company_size': company_size,
                'growth_signals': growth_signals
            }
        }
    
    async def _check_domain_age(self, url: str) -> Dict[str, Any]:
        """Check domain age via WHOIS"""
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
                    'age_years': round(age_years, 1),
                    'is_established': age_years >= 2,
                    'is_new': age_years < 1
                }
        except Exception as e:
            logger.debug(f"[Guardian] WHOIS failed for {url}: {e}")
        
        return {'age_years': None, 'is_established': None, 'is_new': None}
    
    def _estimate_company_size(self, competitor: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate company size from website signals"""
        basic = competitor.get('basic_analysis', {})
        content = competitor.get('detailed_analysis', {}).get('content_analysis', {})
        
        word_count = content.get('word_count', 0)
        page_count = basic.get('page_count', 0)
        
        if word_count > 10000 or page_count > 50:
            return {'estimated_employees': '20+', 'content_volume': 'high'}
        elif word_count > 3000 or page_count > 20:
            return {'estimated_employees': '5-20', 'content_volume': 'medium'}
        else:
            return {'estimated_employees': '1-5', 'content_volume': 'low'}
    
    def _detect_growth_signals(self, competitor: Dict[str, Any]) -> Dict[str, Any]:
        """Detect growth signals"""
        signals = {'is_hiring': False, 'active_blog': False}
        
        content = competitor.get('detailed_analysis', {}).get('content_analysis', {})
        if content.get('blog_count', 0) > 5:
            signals['active_blog'] = True
        
        return signals
    
    def _emit_competitor_insight(self, assessment: Dict[str, Any]):
        """Emit insight for a competitor assessment"""
        level = assessment['threat_level']
        name = assessment['name']
        score = assessment['digital_score']
        reasoning = assessment['reasoning']
        
        emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(level, '⚪')
        label = {'high': 'HIGH THREAT', 'medium': 'MEDIUM THREAT', 'low': 'LOW THREAT'}.get(level, 'UNKNOWN')
        
        priority = {
            'high': AgentPriority.HIGH,
            'medium': AgentPriority.MEDIUM,
            'low': AgentPriority.LOW
        }.get(level, AgentPriority.MEDIUM)
        
        self._emit_insight(
            f"{emoji} {name}: {label} — Score {score}/100, {reasoning}",
            priority=priority,
            insight_type=InsightType.THREAT if level == 'high' else InsightType.FINDING,
            data=assessment
        )
    
    def _extract_domain_name(self, url: str) -> str:
        """Extract domain name from URL"""
        try:
            domain = urlparse(url).netloc or url
            domain = domain.replace('www.', '')
            return domain.split('.')[0].capitalize()
        except:
            return url
    
    def _prioritize_actions(
        self, 
        threats: List[Dict[str, Any]], 
        risk_register: List[Any]
    ) -> List[Dict[str, Any]]:
        """Prioritize actions by impact and effort"""
        
        impact_scores = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}
        effort_scores = {'low': 3, 'medium': 2, 'high': 1}
        
        actions = []
        for threat in threats:
            impact = impact_scores.get(threat.get('impact', 'medium'), 2)
            effort = effort_scores.get(threat.get('effort', 'medium'), 2)
            roi = impact * effort
            
            actions.append({
                'title': f"Fix: {threat.get('title', 'Unknown')}",
                'category': threat.get('category', 'general'),
                'impact': threat.get('impact', 'medium'),
                'effort': threat.get('effort', 'medium'),
                'roi_score': roi
            })
        
        actions.sort(key=lambda x: x['roi_score'], reverse=True)
        return actions
    
    def _calculate_rasm_score(self, threats: List[Dict[str, Any]]) -> int:
        """Calculate RASM (Revenue Attack Surface Mapping) score"""
        score = 100
        
        severity_penalties = {'critical': 25, 'high': 15, 'medium': 8, 'low': 3}
        
        for threat in threats:
            severity = threat.get('severity', 'medium')
            score -= severity_penalties.get(severity, 8)
        
        return max(0, min(100, score))
