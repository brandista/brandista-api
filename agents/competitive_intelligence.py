# -*- coding: utf-8 -*-
"""
Gustav 2.0 — Competitive Intelligence Engine

Generates business-value battlecards, threat narratives,
action playbooks with ROI, and inaction cost calculations.

This is NOT a technical scoring module — it translates data into
business intelligence that a CEO can act on.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime

from .scoring_constants import (
    SCORE_THRESHOLDS,
    FACTOR_STATUS_THRESHOLDS,
    COMPETITIVE_DIFF_THRESHOLD,
    DEFAULT_ANNUAL_REVENUE_EUR,
    RISK_REVENUE_THRESHOLDS,
    MAX_RISK_PERCENT,
    interpret_score,
    calculate_roi_score,
    classify_financial_risk,
    get_competitive_position,
)
from .hallucination_guard import (
    IntelligenceGuard,
    DataSource,
    ConfidenceLevel,
    add_guardrails,
    wrap_estimate,
    STANDARD_CAVEATS_FI,
    STANDARD_CAVEATS_EN,
)

logger = logging.getLogger(__name__)

# =============================================================================
# ACTION COST MATRIX — konkreettiset kustannusarviot per toimenpidetyyppi
# =============================================================================

ACTION_COST_MATRIX = {
    'new_service_page': {
        'hours': 4,
        'cost_eur': 350,
        'description_fi': 'Uusi palvelusivu',
        'description_en': 'New service page',
        'monthly_traffic_estimate': 50,
        'conversion_rate': 0.03,
    },
    'blog_article': {
        'hours': 3,
        'cost_eur': 250,
        'description_fi': 'Blogiartikkeli',
        'description_en': 'Blog article',
        'monthly_traffic_estimate': 30,
        'conversion_rate': 0.02,
    },
    'schema_markup': {
        'hours': 2,
        'cost_eur': 150,
        'description_fi': 'Schema-merkintöjen lisäys',
        'description_en': 'Add schema markup',
        'monthly_traffic_estimate': 0,
        'seo_boost_percent': 5,
    },
    'technical_fix': {
        'hours': 3,
        'cost_eur': 250,
        'description_fi': 'Tekninen korjaus',
        'description_en': 'Technical fix',
        'monthly_traffic_estimate': 0,
        'performance_boost_percent': 10,
    },
    'llms_txt': {
        'hours': 1,
        'cost_eur': 80,
        'description_fi': 'llms.txt AI-näkyvyystiedosto',
        'description_en': 'llms.txt AI visibility file',
        'monthly_traffic_estimate': 10,
        'conversion_rate': 0.05,
    },
    'faq_schema': {
        'hours': 2,
        'cost_eur': 150,
        'description_fi': 'FAQ-sivun ja scheman luonti',
        'description_en': 'FAQ page and schema creation',
        'monthly_traffic_estimate': 20,
        'conversion_rate': 0.02,
    },
    'content_expansion': {
        'hours': 6,
        'cost_eur': 500,
        'description_fi': 'Sisällön laajentaminen (2000+ sanaa)',
        'description_en': 'Content expansion (2000+ words)',
        'monthly_traffic_estimate': 40,
        'conversion_rate': 0.025,
    },
    'performance_optimization': {
        'hours': 4,
        'cost_eur': 350,
        'description_fi': 'Suorituskykyoptimointi (kuvat, lazy loading)',
        'description_en': 'Performance optimization (images, lazy loading)',
        'monthly_traffic_estimate': 0,
        'performance_boost_percent': 15,
    },
    'meta_optimization': {
        'hours': 2,
        'cost_eur': 150,
        'description_fi': 'Meta-tagien ja title-optimointi',
        'description_en': 'Meta tags and title optimization',
        'monthly_traffic_estimate': 15,
        'conversion_rate': 0.01,
    },
}

# Industry average deal values for ROI calculation
INDUSTRY_AVG_DEAL_VALUE = {
    'auto_repair': 250,
    'jewelry': 400,
    'ecommerce': 80,
    'saas': 500,
    'restaurant': 30,
    'healthcare': 200,
    'general': 150,
}

# Organic traffic share of revenue by industry
INDUSTRY_ORGANIC_SHARE = {
    'auto_repair': 0.40,
    'jewelry': 0.35,
    'ecommerce': 0.50,
    'saas': 0.45,
    'restaurant': 0.30,
    'healthcare': 0.35,
    'general': 0.40,
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ActionItem:
    """Konkreettinen toimenpide kustannusarvioineen ja ROI-laskelmalla."""
    action_fi: str
    action_en: str
    category: str               # 'content' / 'technical' / 'seo' / 'ai_visibility'
    action_type: str            # key from ACTION_COST_MATRIX
    cost_estimate_eur: int
    time_estimate_hours: int
    expected_monthly_return: int
    roi_multiplier: float
    priority: int               # 1 = immediately, 2 = this week, 3 = this month
    reasoning_fi: str
    reasoning_en: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class CompetitiveBattlecard:
    """Head-to-head vertailu kilpailijaa vastaan + toimenpidesuunnitelma."""
    competitor_name: str
    competitor_url: str
    competitor_score: int
    your_score: int

    # Head-to-head (8 ulottuvuutta)
    you_win: List[Dict] = field(default_factory=list)
    they_win: List[Dict] = field(default_factory=list)
    neutral: List[Dict] = field(default_factory=list)

    # LLM-generoitu uhkatarina
    threat_narrative_fi: str = ''
    threat_narrative_en: str = ''

    # Toimenpide-playbook
    actions: List[ActionItem] = field(default_factory=list)

    # Revenue impact
    monthly_risk: int = 0
    annual_risk: int = 0
    inaction_timeline_fi: str = ''
    inaction_timeline_en: str = ''

    # Metadata
    threat_level: str = 'medium'
    confidence: float = 0.7
    data_sources: List[str] = field(default_factory=list)
    generated_at: str = ''

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['actions'] = [a.to_dict() if hasattr(a, 'to_dict') else a for a in self.actions]
        return d


@dataclass
class CorrelatedIntelligence:
    """Korreloitu uhkamalli — yhdistää useita signaaleja yhdeksi tarinaksi."""
    correlation_id: str
    correlation_type: str       # 'content_gap_attack', 'digital_erosion', etc.
    title_fi: str
    title_en: str
    narrative_fi: str           # LLM-generoitu tarina
    narrative_en: str
    evidence: List[Dict]        # Todisteet [{category, your_score, comp_score, detail}]
    combined_severity: str      # 'critical' / 'high' / 'medium' / 'low'
    actions: List[ActionItem] = field(default_factory=list)
    monthly_risk: int = 0
    annual_risk: int = 0
    confidence: float = 0.7

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['actions'] = [a.to_dict() if hasattr(a, 'to_dict') else a for a in self.actions]
        return d


# =============================================================================
# CORRELATION RULES
# =============================================================================

CORRELATION_RULES = [
    {
        'id': 'content_gap_attack',
        'title_fi': 'Sisältövajehyökkäys',
        'title_en': 'Content Gap Attack',
        'required_categories': ['content', 'seo'],
        'trigger': lambda scores, comp: (
            scores.get('content', 100) < 40
            and any(c.get('digital_score', 0) - scores.get('overall', 0) > 15 for c in comp)
        ),
        'severity': 'high',
    },
    {
        'id': 'digital_erosion',
        'title_fi': 'Digitaalinen rapautuminen',
        'title_en': 'Digital Erosion',
        'required_categories': ['performance', 'seo', 'mobile'],
        'trigger': lambda scores, comp: (
            scores.get('performance', 100) < 50
            and scores.get('seo', 100) < 50
        ),
        'severity': 'high',
    },
    {
        'id': 'competitive_surge',
        'title_fi': 'Kilpailijoiden rynnäkkö',
        'title_en': 'Competitive Surge',
        'required_categories': ['competitive'],
        'trigger': lambda scores, comp: (
            sum(1 for c in comp if c.get('threat_level') == 'high') >= 2
        ),
        'severity': 'high',
    },
    {
        'id': 'ai_invisibility',
        'title_fi': 'AI-näkymättömyyskriisi',
        'title_en': 'AI Invisibility Crisis',
        'required_categories': ['ai_visibility', 'content'],
        'trigger': lambda scores, comp: (
            scores.get('ai_visibility', 100) < 40
            and scores.get('content', 100) < 50
        ),
        'severity': 'medium',
    },
    {
        'id': 'trust_collapse',
        'title_fi': 'Luottamusromahdus',
        'title_en': 'Trust Collapse',
        'required_categories': ['security', 'performance'],
        'trigger': lambda scores, comp: (
            scores.get('security', 100) < 40
            and scores.get('performance', 100) < 40
        ),
        'severity': 'critical',
    },
    {
        'id': 'market_displacement',
        'title_fi': 'Markkina-aseman menetys',
        'title_en': 'Market Displacement',
        'required_categories': ['competitive', 'content', 'ai_visibility'],
        'trigger': lambda scores, comp: (
            scores.get('content', 100) < 40
            and scores.get('ai_visibility', 100) < 50
            and any(c.get('threat_level') == 'high' for c in comp)
        ),
        'severity': 'critical',
    },
]


# =============================================================================
# MAIN ENGINE
# =============================================================================

class CompetitiveIntelligenceEngine:
    """
    Generates business-value competitive intelligence from raw analysis data.

    Usage:
        engine = CompetitiveIntelligenceEngine(
            your_analysis=your_analysis,
            competitor_analyses=competitor_analyses,
            competitor_assessments=competitor_threat_assessment['assessments'],
            category_comparison=category_comparison,
            benchmark=benchmark,
            annual_revenue=500000,
            industry='auto_repair',
            language='fi',
        )
        battlecards = engine.generate_battlecards()
        correlations = engine.detect_correlations()
        inaction = engine.calculate_total_inaction_cost()
    """

    def __init__(
        self,
        your_analysis: Dict[str, Any],
        competitor_analyses: List[Dict[str, Any]],
        competitor_assessments: List[Dict[str, Any]],
        category_comparison: Dict[str, Any],
        benchmark: Dict[str, Any],
        annual_revenue: int = DEFAULT_ANNUAL_REVENUE_EUR,
        industry: str = 'general',
        language: str = 'fi',
    ):
        self.your = your_analysis
        self.competitors = competitor_analyses
        self.assessments = competitor_assessments
        self.categories = category_comparison
        self.benchmark = benchmark
        self.revenue = annual_revenue
        self.industry = industry
        self.lang = language
        self.avg_deal = INDUSTRY_AVG_DEAL_VALUE.get(industry, 150)
        self.organic_share = INDUSTRY_ORGANIC_SHARE.get(industry, 0.40)

        # Extract your scores for quick access
        self.your_score = self.benchmark.get('your_score', 0)
        self.your_scores = self._extract_category_scores(your_analysis)

        # Anti-hallucination guard — tracks provenance + validates outputs
        self.guard = IntelligenceGuard(language=language)
        self._track_input_provenance()

    def _track_input_provenance(self):
        """Track provenance of all input data — every number is traceable."""
        p = self.guard.provenance

        # Your scores — from HTML analysis + scoring algorithm
        for cat, score in self.your_scores.items():
            p.track_score(f'your_{cat}', score)

        # Competitor scores — from HTML analysis
        for comp in self.assessments:
            name = comp.get('name', comp.get('url', 'unknown'))
            p.track(
                claim=f'competitor_{name}_score',
                value=comp.get('digital_score', 0),
                source=DataSource.HTML_ANALYSIS,
                raw_evidence=f"Scraped from {comp.get('url', '')}",
            )
            # Company intel source
            intel = comp.get('company_intel', {})
            if intel.get('source') == 'registry':
                p.track(
                    claim=f'competitor_{name}_revenue',
                    value=intel.get('revenue', 0),
                    source=DataSource.BUSINESS_REGISTRY,
                    raw_evidence='YTJ/Kauppalehti yritystietohaku',
                )

        # Revenue — user-provided or default
        revenue_source = DataSource.USER_INPUT if self.revenue != DEFAULT_ANNUAL_REVENUE_EUR else DataSource.INDUSTRY_BENCHMARK
        p.track(
            claim='annual_revenue',
            value=self.revenue,
            source=revenue_source,
            caveats=['Käyttäjän syöttämä' if revenue_source == DataSource.USER_INPUT
                     else 'Oletusarvo: EU SME mediaani €500,000'],
        )

        # Industry benchmarks
        p.track(
            claim='avg_deal_value',
            value=self.avg_deal,
            source=DataSource.INDUSTRY_BENCHMARK,
            methodology=f'Toimialan {self.industry} keskiarvo',
            caveats=['Toimialakohtainen estimaatti, ei yrityskohtainen'],
        )
        p.track(
            claim='organic_traffic_share',
            value=self.organic_share,
            source=DataSource.INDUSTRY_BENCHMARK,
            methodology=f'Toimialan {self.industry} tyypillinen orgaanisen liikenteen osuus',
            caveats=['Estimaatti — todellinen osuus riippuu yrityksen markkinointimixistä'],
        )

    # =========================================================================
    # BATTLECARD GENERATION
    # =========================================================================

    def generate_battlecards(self) -> List[CompetitiveBattlecard]:
        """Generate a battlecard for each competitor."""
        battlecards = []

        for i, comp in enumerate(self.competitors):
            assessment = self._find_assessment(comp)
            if not assessment:
                continue

            battlecard = self._build_battlecard(comp, assessment)
            battlecards.append(battlecard)

        # Sort: highest threat first
        threat_order = {'high': 0, 'medium': 1, 'low': 2}
        battlecards.sort(key=lambda b: (threat_order.get(b.threat_level, 2), -b.annual_risk))

        return battlecards

    def _build_battlecard(
        self,
        comp: Dict[str, Any],
        assessment: Dict[str, Any],
    ) -> CompetitiveBattlecard:
        """Build a single competitive battlecard."""
        comp_name = assessment.get('name', '') or self._domain_from_url(comp.get('url', ''))
        comp_url = comp.get('url', '')
        comp_score = assessment.get('digital_score', 0)
        comp_basic = comp.get('basic_analysis', {})
        comp_breakdown = comp_basic.get('score_breakdown', {})

        your_basic = self.your.get('basic_analysis', {})
        your_breakdown = your_basic.get('score_breakdown', {})

        # --- Head-to-head comparison across 8 dimensions ---
        you_win, they_win, neutral = self._compare_dimensions(
            your_breakdown, comp_breakdown, comp_basic, comp_name, comp_score, assessment
        )

        # --- Calculate inaction cost (with provenance tracking) ---
        score_gap = max(0, comp_score - self.your_score)
        organic_revenue = self.revenue * self.organic_share
        # If competitor is ahead, estimate traffic loss proportional to gap
        monthly_risk = 0
        traffic_loss_pct = 0.0
        if score_gap > 0:
            # Rough model: each 10-point gap = ~5% organic traffic loss over 6 months
            traffic_loss_pct = min(0.25, (score_gap / 10) * 0.05)
            monthly_risk = int((organic_revenue * traffic_loss_pct) / 12)

        # Track this estimate's provenance
        self.guard.provenance.track_estimate(
            claim=f'monthly_risk_vs_{comp_name}',
            value=monthly_risk,
            methodology=f'score_gap({score_gap}) × organic_rev(€{int(organic_revenue)}) × loss_pct({traffic_loss_pct:.0%}) / 12',
            best_case=int(monthly_risk * 0.5),
            worst_case=int(monthly_risk * 1.5),
        )
        annual_risk = monthly_risk * 12

        # --- Generate action playbook ---
        actions = self._generate_actions(they_win, comp_name)

        # --- Inaction timeline ---
        if score_gap > 20:
            timeline_fi = f'{comp_name} on jo merkittävästi edellä — reagoi välittömästi'
            timeline_en = f'{comp_name} is already significantly ahead — act immediately'
        elif score_gap > 10:
            timeline_fi = f'{comp_name} ohittaa sinut hakutuloksissa arviolta 4-6 viikossa'
            timeline_en = f'{comp_name} will overtake you in search results in approx. 4-6 weeks'
        elif score_gap > 0:
            timeline_fi = f'{comp_name} vahvistuu — ilman toimenpiteitä ero kasvaa 2-3 kuukaudessa'
            timeline_en = f'{comp_name} is strengthening — without action the gap grows in 2-3 months'
        else:
            timeline_fi = f'Olet edellä {comp_name} — ylläpidä etumatkaa'
            timeline_en = f'You are ahead of {comp_name} — maintain your lead'

        # --- Data sources ---
        sources = ['HTML-analyysi']
        if assessment.get('company_intel', {}).get('source') == 'registry':
            sources.append('YTJ/Kauppalehti')
        if assessment.get('signals', {}).get('domain_age', {}).get('age_years'):
            sources.append('WHOIS')

        # --- Threat narrative (built from data, LLM can enhance later) ---
        narrative_fi = self._build_threat_narrative_fi(
            comp_name, comp_score, you_win, they_win, assessment, monthly_risk
        )
        narrative_en = self._build_threat_narrative_en(
            comp_name, comp_score, you_win, they_win, assessment, monthly_risk
        )

        return CompetitiveBattlecard(
            competitor_name=comp_name,
            competitor_url=comp_url,
            competitor_score=comp_score,
            your_score=self.your_score,
            you_win=you_win,
            they_win=they_win,
            neutral=neutral,
            threat_narrative_fi=narrative_fi,
            threat_narrative_en=narrative_en,
            actions=actions,
            monthly_risk=monthly_risk,
            annual_risk=annual_risk,
            inaction_timeline_fi=timeline_fi,
            inaction_timeline_en=timeline_en,
            threat_level=assessment.get('threat_level', 'medium'),
            confidence=0.85 if assessment.get('company_intel', {}).get('source') == 'registry' else 0.65,
            data_sources=sources,
            generated_at=datetime.now().isoformat(),
        )

    def _compare_dimensions(
        self,
        your_breakdown: Dict,
        comp_breakdown: Dict,
        comp_basic: Dict,
        comp_name: str,
        comp_score: int,
        assessment: Dict,
    ) -> tuple:
        """Compare across 8 business-relevant dimensions."""
        you_win, they_win, neutral = [], [], []

        your_basic = self.your.get('basic_analysis', {})
        your_tech = self.your.get('detailed_analysis', {}).get('technical_audit', {})
        your_content = self.your.get('detailed_analysis', {}).get('content_analysis', {})

        # 1. CONTENT
        your_words = your_content.get('word_count', 0) or your_basic.get('word_count', 0)
        comp_words = comp_basic.get('word_count', 0)
        self._add_comparison(
            you_win, they_win, neutral,
            area_fi='Sisältö', area_en='Content',
            your_val=your_words, comp_val=comp_words,
            format_fn=lambda v: f'{v} sanaa',
            higher_better=True,
            threshold=200,
            impact=self._impact_from_gap(your_words, comp_words, 500),
        )

        # 2. SEO
        your_seo = your_breakdown.get('seo', your_breakdown.get('seo_basics', 0))
        comp_seo = comp_breakdown.get('seo', comp_breakdown.get('seo_basics', 0))
        self._add_comparison(
            you_win, they_win, neutral,
            area_fi='SEO', area_en='SEO',
            your_val=your_seo, comp_val=comp_seo,
            format_fn=lambda v: f'{v}/100',
            higher_better=True,
            threshold=5,
        )

        # 3. PERFORMANCE
        your_perf = your_tech.get('performance_score', your_breakdown.get('performance', 0))
        comp_perf = comp_breakdown.get('performance', 0)
        self._add_comparison(
            you_win, they_win, neutral,
            area_fi='Suorituskyky', area_en='Performance',
            your_val=your_perf, comp_val=comp_perf,
            format_fn=lambda v: f'{v}/100' if v > 15 else f'{v}/5',
            higher_better=True,
            threshold=5,
        )

        # 4. SECURITY / TRUST
        your_sec = your_breakdown.get('security', 0)
        comp_sec = comp_breakdown.get('security', 0)
        self._add_comparison(
            you_win, they_win, neutral,
            area_fi='Luottamus ja turvallisuus', area_en='Trust & Security',
            your_val=your_sec, comp_val=comp_sec,
            format_fn=lambda v: f'{v}/15',
            higher_better=True,
            threshold=2,
        )

        # 5. MOBILE
        your_mobile = your_breakdown.get('mobile', 0)
        comp_mobile = comp_breakdown.get('mobile', 0)
        self._add_comparison(
            you_win, they_win, neutral,
            area_fi='Mobiili', area_en='Mobile',
            your_val=your_mobile, comp_val=comp_mobile,
            format_fn=lambda v: f'{v}/15',
            higher_better=True,
            threshold=2,
        )

        # 6. COMPANY SIZE (from assessment signals)
        comp_employees = assessment.get('company_intel', {}).get('employees')
        if comp_employees:
            detail_fi = f'{comp_name}: {comp_employees} työntekijää'
            detail_en = f'{comp_name}: {comp_employees} employees'
            if comp_employees > 10:
                they_win.append({
                    'area_fi': 'Yrityksen koko', 'area_en': 'Company Size',
                    'detail_fi': detail_fi, 'detail_en': detail_en,
                    'impact': 'medium',
                })
            else:
                neutral.append({
                    'area_fi': 'Yrityksen koko', 'area_en': 'Company Size',
                    'detail_fi': detail_fi, 'detail_en': detail_en,
                    'impact': 'low',
                })

        # 7. DIGITAL BREADTH (page count approximation)
        comp_social = comp_basic.get('social_platforms', 0)
        your_social = your_basic.get('social_platforms', 0)
        if comp_social > your_social + 1:
            they_win.append({
                'area_fi': 'Digitaalinen laajuus', 'area_en': 'Digital Breadth',
                'detail_fi': f'{comp_name}: {comp_social} sosiaalista kanavaa vs sinun {your_social}',
                'detail_en': f'{comp_name}: {comp_social} social channels vs your {your_social}',
                'impact': 'medium',
            })
        elif your_social > comp_social + 1:
            you_win.append({
                'area_fi': 'Digitaalinen laajuus', 'area_en': 'Digital Breadth',
                'detail_fi': f'Sinulla {your_social} sosiaalista kanavaa vs {comp_name} {comp_social}',
                'detail_en': f'You have {your_social} social channels vs {comp_name} {comp_social}',
                'impact': 'medium',
            })

        # 8. GROWTH SIGNALS
        signals = assessment.get('signals', {})
        growth = signals.get('growth_signals', {})
        if growth.get('is_hiring'):
            they_win.append({
                'area_fi': 'Kasvusignaalit', 'area_en': 'Growth Signals',
                'detail_fi': f'{comp_name} rekrytoi aktiivisesti — kasvupanostus',
                'detail_en': f'{comp_name} is actively hiring — growth investment',
                'impact': 'medium',
            })
        if growth.get('active_blog'):
            they_win.append({
                'area_fi': 'Sisältöaktiivisuus', 'area_en': 'Content Activity',
                'detail_fi': f'{comp_name} bloggaa aktiivisesti',
                'detail_en': f'{comp_name} has an active blog',
                'impact': 'medium',
            })

        return you_win, they_win, neutral

    def _add_comparison(
        self, you_win, they_win, neutral,
        area_fi, area_en, your_val, comp_val,
        format_fn, higher_better=True, threshold=5, impact=None,
    ):
        """Helper: add a comparison entry to the right bucket."""
        diff = (your_val - comp_val) if higher_better else (comp_val - your_val)

        if abs(diff) < threshold:
            neutral.append({
                'area_fi': area_fi, 'area_en': area_en,
                'detail_fi': f'Tasapeli: sinä {format_fn(your_val)} vs {format_fn(comp_val)}',
                'detail_en': f'Even: you {format_fn(your_val)} vs {format_fn(comp_val)}',
                'impact': 'low',
            })
        elif diff > 0:
            you_win.append({
                'area_fi': area_fi, 'area_en': area_en,
                'detail_fi': f'Sinä {format_fn(your_val)} vs {format_fn(comp_val)}',
                'detail_en': f'You {format_fn(your_val)} vs {format_fn(comp_val)}',
                'impact': impact or ('high' if diff > threshold * 3 else 'medium'),
            })
        else:
            they_win.append({
                'area_fi': area_fi, 'area_en': area_en,
                'detail_fi': f'Kilpailija {format_fn(comp_val)} vs sinä {format_fn(your_val)}',
                'detail_en': f'Competitor {format_fn(comp_val)} vs you {format_fn(your_val)}',
                'impact': impact or ('critical' if abs(diff) > threshold * 3 else 'high'),
            })

    # =========================================================================
    # ACTION PLAYBOOK GENERATION
    # =========================================================================

    def _generate_actions(self, they_win: List[Dict], comp_name: str) -> List[ActionItem]:
        """Generate prioritized actions based on where competitor wins."""
        actions = []

        for weakness in they_win:
            area = weakness.get('area_fi', '').lower()
            impact = weakness.get('impact', 'medium')

            action_items = self._actions_for_weakness(area, impact, comp_name)
            actions.extend(action_items)

        # Deduplicate by action_type
        seen = set()
        unique_actions = []
        for a in actions:
            if a.action_type not in seen:
                seen.add(a.action_type)
                unique_actions.append(a)

        # Sort by ROI descending
        unique_actions.sort(key=lambda a: a.roi_multiplier, reverse=True)

        # Return top 5
        return unique_actions[:5]

    def _actions_for_weakness(self, area: str, impact: str, comp_name: str) -> List[ActionItem]:
        """Map a weakness area to concrete action items."""
        items = []

        if 'sisältö' in area or 'content' in area:
            items.append(self._make_action(
                'blog_article',
                action_fi=f'Julkaise blogiartikkeli kilpailijan {comp_name} vahvuusalueelta',
                action_en=f'Publish blog article in {comp_name}\'s strength area',
                category='content', priority=1 if impact == 'critical' else 2,
                reasoning_fi=f'{comp_name} voittaa sisällössä — uusi artikkeli tuo orgaanista liikennettä',
                reasoning_en=f'{comp_name} wins on content — new article brings organic traffic',
            ))
            items.append(self._make_action(
                'content_expansion',
                action_fi='Laajenna olemassa olevan pääsivun sisältöä 2000+ sanaan',
                action_en='Expand main page content to 2000+ words',
                category='content', priority=2,
                reasoning_fi='Pidempi sisältö rankaa paremmin ja kattaa enemmän hakutermejä',
                reasoning_en='Longer content ranks better and covers more search terms',
            ))

        if 'seo' in area:
            items.append(self._make_action(
                'meta_optimization',
                action_fi='Optimoi meta-tagit ja title-tägit',
                action_en='Optimize meta tags and title tags',
                category='seo', priority=2,
                reasoning_fi='Meta-optimointi on nopein tapa parantaa hakutuloksia',
                reasoning_en='Meta optimization is the fastest way to improve search results',
            ))
            items.append(self._make_action(
                'schema_markup',
                action_fi='Lisää kattava schema-merkintä (LocalBusiness + FAQ)',
                action_en='Add comprehensive schema markup (LocalBusiness + FAQ)',
                category='seo', priority=2,
                reasoning_fi='Schema parantaa hakutulosten näkyvyyttä ja klikkausprosenttia',
                reasoning_en='Schema improves search result visibility and click-through rate',
            ))

        if 'suorituskyky' in area or 'performance' in area:
            items.append(self._make_action(
                'performance_optimization',
                action_fi='Optimoi sivuston nopeus (kuvat, lazy loading, välimuisti)',
                action_en='Optimize site speed (images, lazy loading, caching)',
                category='technical', priority=2,
                reasoning_fi='53% mobiiliikävijöistä poistuu jos lataus kestää yli 3 sekuntia',
                reasoning_en='53% of mobile visitors leave if loading takes over 3 seconds',
            ))

        if 'ai' in area or 'näkyvyys' in area:
            items.append(self._make_action(
                'llms_txt',
                action_fi='Luo llms.txt AI-näkyvyystiedosto',
                action_en='Create llms.txt AI visibility file',
                category='ai_visibility', priority=1,
                reasoning_fi='llms.txt kertoo AI-hakukoneille mitä sivustosi tarjoaa — nopea voitto',
                reasoning_en='llms.txt tells AI search engines what your site offers — quick win',
            ))
            items.append(self._make_action(
                'faq_schema',
                action_fi='Luo FAQ-sivu ja FAQ-schema',
                action_en='Create FAQ page and FAQ schema',
                category='ai_visibility', priority=2,
                reasoning_fi='FAQ-sisältö on AI-hakukoneiden suosikkia — helppo indeksoida',
                reasoning_en='FAQ content is favored by AI search engines — easy to index',
            ))

        if 'kasvu' in area or 'growth' in area or 'aktiivisuus' in area:
            items.append(self._make_action(
                'blog_article',
                action_fi='Aloita säännöllinen bloggaaminen (2 artikkelia/kk)',
                action_en='Start regular blogging (2 articles/month)',
                category='content', priority=3,
                reasoning_fi='Aktiivinen blogi rakentaa asiantuntijuutta ja tuo orgaanista liikennettä',
                reasoning_en='Active blog builds authority and brings organic traffic',
            ))

        if 'luottamus' in area or 'trust' in area or 'turvallisuus' in area:
            items.append(self._make_action(
                'technical_fix',
                action_fi='Korjaa turvallisuusasetukset (SSL, HSTS, CSP)',
                action_en='Fix security settings (SSL, HSTS, CSP)',
                category='technical', priority=1,
                reasoning_fi='Turvallisuusongelmat karkottavat asiakkaita ja laskevat hakusijoituksia',
                reasoning_en='Security issues drive away customers and lower search rankings',
            ))

        return items

    def _make_action(
        self, action_type: str,
        action_fi: str, action_en: str,
        category: str, priority: int,
        reasoning_fi: str, reasoning_en: str,
    ) -> ActionItem:
        """Create an ActionItem with cost/ROI from the matrix."""
        matrix = ACTION_COST_MATRIX.get(action_type, ACTION_COST_MATRIX['technical_fix'])

        monthly_traffic = matrix.get('monthly_traffic_estimate', 0)
        conversion_rate = matrix.get('conversion_rate', 0.02)
        monthly_return = int(monthly_traffic * conversion_rate * self.avg_deal)
        annual_return = monthly_return * 12
        cost = matrix['cost_eur']
        roi = round(annual_return / max(1, cost), 1)

        return ActionItem(
            action_fi=action_fi,
            action_en=action_en,
            category=category,
            action_type=action_type,
            cost_estimate_eur=cost,
            time_estimate_hours=matrix['hours'],
            expected_monthly_return=monthly_return,
            roi_multiplier=roi,
            priority=priority,
            reasoning_fi=reasoning_fi,
            reasoning_en=reasoning_en,
        )

    # =========================================================================
    # THREAT CORRELATION
    # =========================================================================

    def detect_correlations(self) -> List[CorrelatedIntelligence]:
        """Detect correlated threat patterns from current analysis data."""
        correlations = []

        # Build assessment list for trigger evaluation
        comp_list = self.assessments or []

        for rule in CORRELATION_RULES:
            try:
                if rule['trigger'](self.your_scores, comp_list):
                    evidence = self._build_evidence(rule)
                    actions = self._correlation_actions(rule['id'])

                    # Calculate risk
                    organic_rev = self.revenue * self.organic_share
                    severity_multiplier = {'critical': 0.15, 'high': 0.10, 'medium': 0.05, 'low': 0.02}
                    monthly_risk = int(organic_rev * severity_multiplier.get(rule['severity'], 0.05) / 12)

                    correlations.append(CorrelatedIntelligence(
                        correlation_id=f"corr_{rule['id']}_{datetime.now().strftime('%Y%m%d')}",
                        correlation_type=rule['id'],
                        title_fi=rule['title_fi'],
                        title_en=rule['title_en'],
                        narrative_fi=self._correlation_narrative_fi(rule, evidence),
                        narrative_en=self._correlation_narrative_en(rule, evidence),
                        evidence=evidence,
                        combined_severity=rule['severity'],
                        actions=actions,
                        monthly_risk=monthly_risk,
                        annual_risk=monthly_risk * 12,
                        confidence=0.80 if len(evidence) >= 3 else 0.65,
                    ))
            except Exception as e:
                logger.warning(f"[CI] Correlation rule {rule['id']} failed: {e}")

        return correlations

    def _build_evidence(self, rule: Dict) -> List[Dict]:
        """Build evidence chain for a correlation."""
        evidence = []
        for cat in rule['required_categories']:
            cat_data = self.categories.get(cat, {})
            evidence.append({
                'category': cat,
                'your_score': cat_data.get('your_score', self.your_scores.get(cat, 0)),
                'competitor_avg': cat_data.get('competitor_avg', 0),
                'status': cat_data.get('status', 'behind'),
                'gap': cat_data.get('difference', 0),
            })
        return evidence

    def _correlation_actions(self, correlation_type: str) -> List[ActionItem]:
        """Return recommended actions for a correlation type."""
        action_map = {
            'content_gap_attack': ['blog_article', 'content_expansion', 'new_service_page'],
            'digital_erosion': ['performance_optimization', 'meta_optimization', 'technical_fix'],
            'competitive_surge': ['content_expansion', 'schema_markup', 'performance_optimization'],
            'ai_invisibility': ['llms_txt', 'faq_schema', 'content_expansion'],
            'trust_collapse': ['technical_fix', 'performance_optimization'],
            'market_displacement': ['content_expansion', 'blog_article', 'llms_txt'],
        }

        action_types = action_map.get(correlation_type, ['technical_fix'])
        actions = []
        for at in action_types:
            matrix = ACTION_COST_MATRIX.get(at, ACTION_COST_MATRIX['technical_fix'])
            actions.append(self._make_action(
                at,
                action_fi=matrix['description_fi'],
                action_en=matrix['description_en'],
                category='mixed',
                priority=1,
                reasoning_fi=f'Osa {correlation_type}-korrelaation korjausta',
                reasoning_en=f'Part of {correlation_type} correlation fix',
            ))
        return actions

    def _correlation_narrative_fi(self, rule: Dict, evidence: List[Dict]) -> str:
        """Build a Finnish narrative for a correlation."""
        parts = []
        for e in evidence:
            gap_str = ''
            if e['gap'] < 0:
                gap_str = f" ({abs(e['gap'])}p kilpailijoiden keskiarvon alla)"
            parts.append(f"{e['category']}: {e['your_score']}/100{gap_str}")

        evidence_str = '. '.join(parts)
        return f"{rule['title_fi']}: Useampi alue heikkenee samanaikaisesti. {evidence_str}. Yhdessä nämä muodostavat vakavan liiketoimintariskin."

    def _correlation_narrative_en(self, rule: Dict, evidence: List[Dict]) -> str:
        """Build an English narrative for a correlation."""
        parts = []
        for e in evidence:
            gap_str = ''
            if e['gap'] < 0:
                gap_str = f" ({abs(e['gap'])}p below competitor average)"
            parts.append(f"{e['category']}: {e['your_score']}/100{gap_str}")

        evidence_str = '. '.join(parts)
        return f"{rule['title_en']}: Multiple areas declining simultaneously. {evidence_str}. Together these form a serious business risk."

    # =========================================================================
    # INACTION COST
    # =========================================================================

    def calculate_total_inaction_cost(self) -> Dict[str, Any]:
        """
        Calculate the total cost of not acting on any threats.

        Based on: score gaps × organic revenue share × time.

        Anti-hallucination: all numbers are deterministic calculations from
        verified inputs. Results are wrapped as estimates with best/worst ranges.
        """
        organic_revenue = self.revenue * self.organic_share

        # Per-category risk
        category_risks = {}
        total_monthly = 0

        for cat, data in self.categories.items():
            gap = data.get('difference', 0)
            if gap < 0:  # We're behind
                # Each 10-point gap ≈ 5% of organic traffic for that category
                traffic_loss_pct = min(0.20, (abs(gap) / 10) * 0.05)
                # Category weight (not all categories equal impact)
                cat_weight = {
                    'seo': 0.30, 'content': 0.25, 'performance': 0.15,
                    'ai_visibility': 0.15, 'security': 0.10, 'ux': 0.05,
                }.get(cat, 0.10)
                monthly_loss = int(organic_revenue * traffic_loss_pct * cat_weight / 12)
                category_risks[cat] = {
                    'gap': gap,
                    'monthly_loss': self.guard.wrap_financial_estimate(
                        value=monthly_loss,
                        estimate_type='inaction_cost',
                    ),
                    'annual_loss': self.guard.wrap_financial_estimate(
                        value=monthly_loss * 12,
                        estimate_type='inaction_cost',
                    ),
                }
                total_monthly += monthly_loss

        # Track provenance for the total
        self.guard.provenance.track_estimate(
            claim='total_inaction_cost_monthly',
            value=total_monthly,
            methodology=(
                f'Sum of per-category losses: score_gap × organic_rev(€{int(organic_revenue)}) '
                f'× traffic_loss_pct × category_weight / 12'
            ),
            best_case=int(total_monthly * 0.5),
            worst_case=int(total_monthly * 1.5),
        )

        return {
            'total_monthly_loss': self.guard.wrap_financial_estimate(
                value=total_monthly,
                estimate_type='inaction_cost',
            ),
            'total_annual_loss': self.guard.wrap_financial_estimate(
                value=total_monthly * 12,
                estimate_type='inaction_cost',
            ),
            'category_breakdown': category_risks,
            'organic_revenue_base': int(organic_revenue),
            'organic_share': self.organic_share,
            'explanation_fi': (
                f'Jos et tee mitään, menetät arviolta €{total_monthly:,}/kk orgaanisessa liikenteessä. '
                f'Tämä perustuu kilpailijoiden etumatkaan {len(category_risks)} kategoriassa '
                f'ja {int(self.organic_share*100)}% orgaanisen liikenteen osuuteen liikevaihdostasi. '
                f'Vaihteluväli: €{int(total_monthly*0.5):,} - €{int(total_monthly*1.5):,}/kk.'
            ),
            'explanation_en': (
                f'If you do nothing, you lose an estimated €{total_monthly:,}/month in organic traffic. '
                f'Based on competitor lead in {len(category_risks)} categories '
                f'and {int(self.organic_share*100)}% organic traffic share of your revenue. '
                f'Range: €{int(total_monthly*0.5):,} - €{int(total_monthly*1.5):,}/month.'
            ),
            'data_quality': self.guard.get_data_quality_summary(),
        }

    # =========================================================================
    # THREAT NARRATIVE BUILDERS
    # =========================================================================

    def _build_threat_narrative_fi(
        self, comp_name, comp_score, you_win, they_win, assessment, monthly_risk
    ) -> str:
        """Build a data-driven threat narrative in Finnish."""
        parts = []

        # Opening: competitor positioning
        score_diff = comp_score - self.your_score
        if score_diff > 20:
            parts.append(f'{comp_name} on digitaalisesti merkittävästi edellä sinua ({comp_score} vs {self.your_score} pistettä).')
        elif score_diff > 0:
            parts.append(f'{comp_name} ({comp_score}p) on hieman edellä sinua ({self.your_score}p) digitaalisesti.')
        else:
            parts.append(f'Olet digitaalisesti edellä kilpailijaa {comp_name} ({self.your_score}p vs {comp_score}p).')

        # Where they beat you (max 2 most impactful)
        critical_losses = [w for w in they_win if w.get('impact') in ('critical', 'high')][:2]
        if critical_losses:
            loss_details = ' ja '.join([w.get('detail_fi', '') for w in critical_losses])
            parts.append(f'Kriittisimmät erot: {loss_details}.')

        # Company intel context
        intel = assessment.get('company_intel', {})
        if intel.get('revenue'):
            parts.append(f'Kilpailijan liikevaihto on €{int(intel["revenue"]):,} (lähde: YTJ).')
        if intel.get('employees'):
            parts.append(f'Henkilöstöä {intel["employees"]}.')

        # Revenue impact
        if monthly_risk > 0:
            parts.append(f'Toimimattomuuden hinta: arviolta €{monthly_risk:,}/kk menetettynä orgaanisena liikenteenä.')

        return ' '.join(parts)

    def _build_threat_narrative_en(
        self, comp_name, comp_score, you_win, they_win, assessment, monthly_risk
    ) -> str:
        """Build a data-driven threat narrative in English."""
        parts = []

        score_diff = comp_score - self.your_score
        if score_diff > 20:
            parts.append(f'{comp_name} is significantly ahead digitally ({comp_score} vs {self.your_score} points).')
        elif score_diff > 0:
            parts.append(f'{comp_name} ({comp_score}p) is slightly ahead of you ({self.your_score}p) digitally.')
        else:
            parts.append(f'You are digitally ahead of {comp_name} ({self.your_score}p vs {comp_score}p).')

        critical_losses = [w for w in they_win if w.get('impact') in ('critical', 'high')][:2]
        if critical_losses:
            loss_details = ' and '.join([w.get('detail_en', '') for w in critical_losses])
            parts.append(f'Critical gaps: {loss_details}.')

        intel = assessment.get('company_intel', {})
        if intel.get('revenue'):
            parts.append(f'Competitor revenue: €{int(intel["revenue"]):,} (source: registry).')

        if monthly_risk > 0:
            parts.append(f'Cost of inaction: estimated €{monthly_risk:,}/month in lost organic traffic.')

        return ' '.join(parts)

    # =========================================================================
    # LLM PROMPT BUILDERS (for enhanced narratives)
    # =========================================================================

    def build_threat_story_prompt(self, battlecard: CompetitiveBattlecard) -> str:
        """Build LLM prompt for generating an enhanced threat narrative.

        Anti-hallucination: prompt contains ONLY verified data points,
        guardrails suffix forbids inventing numbers or facts.
        """
        you_win_str = '\n'.join([f"  - {w['area_fi']}: {w['detail_fi']}" for w in battlecard.you_win])
        they_win_str = '\n'.join([f"  - {w['area_fi']}: {w['detail_fi']}" for w in battlecard.they_win])

        prompt = f"""Olet liiketoiminta-analyytikko. Kirjoita 3-5 lauseen uhkatarina yrittäjälle.

FAKTAT (käytä VAIN näitä, älä keksi):
- Sinun yritys: ({self.your.get('basic_analysis', {}).get('website', '')})
- Kilpailija: {battlecard.competitor_name} ({battlecard.competitor_url})
- Sinun kokonaispistemäärä: {battlecard.your_score}/100
- Kilpailijan kokonaispistemäärä: {battlecard.competitor_score}/100

MISSÄ VOITAT:
{you_win_str or '  (ei merkittäviä etuja)'}

MISSÄ HÄVIÄT:
{they_win_str or '  (ei merkittäviä heikkouksia)'}

TALOUDELLINEN VAIKUTUS:
- Toimimattomuuden hinta: arviolta €{battlecard.monthly_risk}/kk (estimaatti)
- Aikaikkunas: {battlecard.inaction_timeline_fi}

OHJE: Kirjoita suomeksi. Älä käytä teknistä jargonia. Kerro konkreettisesti:
1. Mitä kilpailija tekee paremmin (faktoihin perustuen)
2. Mitä se tarkoittaa liiketoiminnalle (asiakasvaikutus)
3. Kuinka nopeasti tilanne eskaloituu jos ei reagoida

ÄLÄ käytä sanoja: "uhka", "riski", "pisteytys", "score". Puhu liiketoimintakielellä.
Merkitse kaikki euromäärät sanalla "arviolta" koska ne ovat estimaatteja."""

        # Add anti-hallucination guardrails
        return add_guardrails(prompt, 'fi')

    def build_executive_brief_prompt(
        self,
        battlecards: List[CompetitiveBattlecard],
        correlations: List[CorrelatedIntelligence],
        inaction_cost: Dict,
    ) -> str:
        """Build LLM prompt for generating an executive brief.

        Anti-hallucination: all data is pre-calculated and injected,
        guardrails suffix forbids inventing numbers or facts.
        """
        bc_summary = '\n'.join([
            f"  - {b.competitor_name}: uhkataso {b.threat_level}, arviolta €{b.monthly_risk}/kk"
            for b in battlecards
        ])

        corr_summary = '\n'.join([
            f"  - {c.title_fi}: {c.combined_severity}, arviolta €{c.monthly_risk}/kk"
            for c in correlations
        ]) if correlations else '  (ei korreloituja uhkia)'

        position = get_competitive_position(self.your_score, self.benchmark.get('avg_competitor_score', 0))

        # Extract monthly loss value (may be wrapped estimate dict)
        monthly_loss = inaction_cost.get('total_monthly_loss', 0)
        if isinstance(monthly_loss, dict):
            monthly_loss = monthly_loss.get('value', 0)
        annual_loss = inaction_cost.get('total_annual_loss', 0)
        if isinstance(annual_loss, dict):
            annual_loss = annual_loss.get('value', 0)

        prompt = f"""Olet toimitusjohtajan neuvonantaja. Kirjoita tiivis liiketoimintakatsaus.

FAKTAT (käytä VAIN näitä, älä keksi):

KILPAILUASEMA: {position}
- Sinun pisteet: {self.your_score}/100
- Kilpailijoiden keskiarvo: {self.benchmark.get('avg_competitor_score', 0)}/100
- Sijoitus: {self.benchmark.get('your_position', '?')}/{self.benchmark.get('total_analyzed', '?')}

KILPAILIJAT:
{bc_summary}

KORRELAATIOT (yhdistetyt uhkamallit):
{corr_summary}

TOIMIMATTOMUUDEN HINTA (estimaatteja):
- Kuukausittainen menetys: arviolta €{monthly_loss:,}/kk
- Vuosittainen menetys: arviolta €{annual_loss:,}/v

OHJE: Kirjoita 150-250 sanan brief suomeksi. Rakenne:
1. TILANNEKUVA (1-2 lausetta): Missä mennään, suunta
2. TÄRKEIN HAVAINTO (2-3 lausetta): Mikä on kriittisintä
3. KILPAILUTILANNE (2-3 lausetta): Kuka liikkui ja miten
4. TOP 3 TOIMENPIDETTÄ: Konkreettiset, kustannusarvioidut

Älä käytä sanoja: "pisteytys", "score", "algoritmi". Puhu rahasta ja asiakkaista.
Toimitusjohtajan pitää ymmärtää tämä 60 sekunnissa.
Merkitse kaikki euromäärät sanalla "arviolta" koska ne ovat estimaatteja."""

        # Add anti-hallucination guardrails
        return add_guardrails(prompt, 'fi')

    # =========================================================================
    # FULL INTELLIGENCE GENERATION (main entry point)
    # =========================================================================

    def generate_full_intelligence(self) -> Dict[str, Any]:
        """
        Generate complete competitive intelligence with anti-hallucination envelope.

        This is the main entry point for guardian_agent.py integration.
        Returns everything wrapped with data quality and provenance metadata.
        """
        battlecards = self.generate_battlecards()
        correlations = self.detect_correlations()
        inaction_cost = self.calculate_total_inaction_cost()

        # Create transparency envelope
        envelope = self.guard.create_envelope(
            content={
                'battlecards': [b.to_dict() for b in battlecards],
                'correlated_intelligence': [c.to_dict() for c in correlations],
                'inaction_cost': inaction_cost,
            },
            methodology_fi=(
                'Kilpailutiedustelu generoitu HTML-analyysin, pisteytysalgoritmin ja '
                'toimialakohtaisten benchmarkien perusteella. Taloudelliset arviot ovat '
                'estimaatteja jotka perustuvat orgaanisen liikenteen osuuteen ja kilpailijoiden etumatkaan.'
            ),
            methodology_en=(
                'Competitive intelligence generated from HTML analysis, scoring algorithm, '
                'and industry benchmarks. Financial estimates are based on organic traffic '
                'share and competitor lead.'
            ),
        )

        return {
            'battlecards': [b.to_dict() for b in battlecards],
            'correlated_intelligence': [c.to_dict() for c in correlations],
            'inaction_cost': inaction_cost,
            'data_quality': self.guard.get_data_quality_summary(),
            'provenance': self.guard.provenance.to_dict(),
            'transparency': envelope.to_dict(),
        }

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _find_assessment(self, comp: Dict) -> Optional[Dict]:
        """Find the matching threat assessment for a competitor."""
        comp_url = comp.get('url', '')
        for a in self.assessments:
            if a.get('url') == comp_url:
                return a
        # Fallback: match by domain
        comp_domain = self._domain_from_url(comp_url)
        for a in self.assessments:
            if self._domain_from_url(a.get('url', '')) == comp_domain:
                return a
        return None

    def _extract_category_scores(self, analysis: Dict) -> Dict[str, int]:
        """Extract normalized category scores from analysis."""
        scores = {}
        breakdown = analysis.get('basic_analysis', {}).get('score_breakdown', {})

        # Normalized scores (0-100)
        scores['seo'] = breakdown.get('seo', 0)
        scores['content'] = breakdown.get('content', 0)
        scores['performance'] = breakdown.get('performance', 0)
        scores['security'] = breakdown.get('security', 0)
        scores['mobile'] = breakdown.get('mobile', 0)
        scores['social'] = breakdown.get('social', 0)
        scores['overall'] = analysis.get('basic_analysis', {}).get('digital_maturity_score', 0)

        # AI visibility from enhanced features
        ai_vis = analysis.get('enhanced_features', {}).get('ai_search_visibility', {})
        if not ai_vis:
            ai_vis = analysis.get('detailed_analysis', {}).get('ai_search_visibility', {})
        scores['ai_visibility'] = ai_vis.get('overall_ai_search_score', 0) if isinstance(ai_vis, dict) else 0

        return scores

    @staticmethod
    def _domain_from_url(url: str) -> str:
        """Extract domain from URL."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return (parsed.netloc or parsed.path.split('/')[0]).replace('www.', '')

    @staticmethod
    def _impact_from_gap(your_val: int, comp_val: int, high_threshold: int = 500) -> str:
        """Determine impact level from numeric gap."""
        gap = abs(your_val - comp_val)
        if gap > high_threshold:
            return 'critical'
        elif gap > high_threshold / 2:
            return 'high'
        return 'medium'
