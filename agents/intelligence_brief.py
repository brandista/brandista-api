# -*- coding: utf-8 -*-
"""
Gustav 2.0 — Executive Intelligence Briefs

Generates concise, CEO-readable intelligence summaries.
"Kuukausiraportti jonka toimitusjohtaja oikeasti lukee"

Anti-hallucination: all content derived from verified data,
LLM prompts include guardrails, output is validated.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime

from .hallucination_guard import (
    IntelligenceGuard,
    DataSource,
    add_guardrails,
    STANDARD_CAVEATS_FI,
    STANDARD_CAVEATS_EN,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutiveBrief:
    """Executive intelligence brief — CEO-readable summary."""
    period: str                      # "Maaliskuu 2026"
    url: str

    # Headline metrics
    overall_score: int = 0
    overall_score_change: int = 0    # +5 / -3
    revenue_at_risk: int = 0
    threats_resolved: int = 0
    new_threats: int = 0
    recurring_threats: int = 0

    # Key findings (max 3, no jargon)
    key_findings: List[Dict] = field(default_factory=list)

    # Competitive position
    competitive_position: str = ''
    competitive_rank: str = ''       # "2. / 5"
    biggest_mover: Dict = field(default_factory=dict)

    # Prediction
    trend_direction: str = 'stable'  # 'improving' / 'stable' / 'declining'
    prediction_fi: str = ''
    prediction_en: str = ''

    # Top actions (max 3)
    top_actions: List[Dict] = field(default_factory=list)

    # LLM-generated narrative
    narrative_fi: str = ''
    narrative_en: str = ''

    # Metadata
    data_quality: Dict = field(default_factory=dict)
    generated_at: str = ''

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return asdict(self)


class IntelligenceBriefGenerator:
    """
    Generates executive intelligence briefs from analysis results.

    Usage:
        gen = IntelligenceBriefGenerator(language='fi')
        brief = gen.generate(
            url='https://bemufix.fi',
            guardian_result=guardian_result,
            delta=delta,
            trend=trend,
            battlecards=battlecards,
        )
    """

    def __init__(self, language: str = 'fi'):
        self.lang = language
        self.guard = IntelligenceGuard(language=language)

    def generate(
        self,
        url: str,
        guardian_result: Dict,
        delta: Optional[Dict] = None,
        trend: Optional[Dict] = None,
        battlecards: Optional[List[Dict]] = None,
        period: str = '',
    ) -> ExecutiveBrief:
        """Generate executive brief from available data."""
        if not period:
            period = datetime.now().strftime('%B %Y')

        ci = guardian_result.get('competitive_intelligence', {})
        cta = guardian_result.get('competitor_threat_assessment', {})
        threats = guardian_result.get('threats', [])
        rasm_score = guardian_result.get('rasm_score', 0)

        # Revenue at risk
        inaction = ci.get('inaction_cost', {})
        rev_at_risk = 0
        monthly_loss = inaction.get('total_monthly_loss', 0)
        if isinstance(monthly_loss, dict):
            rev_at_risk = monthly_loss.get('value', 0) * 12
        elif isinstance(monthly_loss, (int, float)):
            rev_at_risk = int(monthly_loss * 12)

        # Score change from delta
        score_change = 0
        if delta:
            sc = delta.get('score_changes', {})
            score_change = sc.get('overall', {}).get('delta', 0)

        # Threat counts from delta
        new_threats = len(delta.get('new_threats', [])) if delta else len(threats)
        resolved = len(delta.get('resolved_threats', [])) if delta else 0
        recurring = len(delta.get('recurring_threats', [])) if delta else 0

        # Competitive position
        position = cta.get('position', '')
        rank = ''
        if cta.get('your_rank') and cta.get('total'):
            rank = f"{cta['your_rank']}. / {cta['total']}"

        # Biggest mover
        biggest_mover = self._find_biggest_mover(battlecards or ci.get('battlecards', []))

        # Trend
        trend_dir = trend.get('direction', 'stable') if trend else 'stable'
        prediction_fi = trend.get('prediction_fi', '') if trend else ''
        prediction_en = trend.get('prediction_en', '') if trend else ''

        # Key findings (max 3)
        key_findings = self._extract_key_findings(
            threats, delta, ci, cta, self.lang
        )

        # Top actions (max 3)
        top_actions = self._extract_top_actions(ci, guardian_result, self.lang)

        brief = ExecutiveBrief(
            period=period,
            url=url,
            overall_score=rasm_score,
            overall_score_change=score_change,
            revenue_at_risk=rev_at_risk,
            threats_resolved=resolved,
            new_threats=new_threats,
            recurring_threats=recurring,
            key_findings=key_findings,
            competitive_position=position,
            competitive_rank=rank,
            biggest_mover=biggest_mover,
            trend_direction=trend_dir,
            prediction_fi=prediction_fi,
            prediction_en=prediction_en,
            top_actions=top_actions,
            data_quality=self.guard.get_data_quality_summary(),
        )

        # Generate template-based narrative (no LLM needed for basic version)
        brief.narrative_fi = self._build_narrative_fi(brief)
        brief.narrative_en = self._build_narrative_en(brief)

        return brief

    def _find_biggest_mover(self, battlecards: List[Dict]) -> Dict:
        """Find the competitor that moved most (by threat level or score gap)."""
        if not battlecards:
            return {}

        # Sort by annual_risk descending
        sorted_bcs = sorted(
            battlecards,
            key=lambda b: b.get('annual_risk', 0),
            reverse=True
        )

        if sorted_bcs:
            top = sorted_bcs[0]
            return {
                'name': top.get('competitor_name', ''),
                'threat_level': top.get('threat_level', ''),
                'annual_risk': top.get('annual_risk', 0),
            }
        return {}

    def _extract_key_findings(
        self, threats, delta, ci, cta, lang
    ) -> List[Dict]:
        """Extract top 3 most important findings."""
        findings = []

        # 1. Correlations (highest priority)
        correlations = ci.get('correlated_intelligence', [])
        for corr in correlations[:1]:
            findings.append({
                'title_fi': corr.get('title_fi', ''),
                'title_en': corr.get('title_en', ''),
                'impact_fi': f"Vakavuus: {corr.get('combined_severity', '')}",
                'impact_en': f"Severity: {corr.get('combined_severity', '')}",
                'urgency': corr.get('combined_severity', 'medium'),
            })

        # 2. Escalated threats (if delta exists)
        if delta:
            for esc in delta.get('escalated_threats', [])[:1]:
                findings.append({
                    'title_fi': esc.get('explanation_fi', 'Uhka eskaloitui'),
                    'title_en': esc.get('explanation_en', 'Threat escalated'),
                    'impact_fi': f"Nousi: {esc.get('previous_severity', '?')} → {esc.get('current_severity', '?')}",
                    'impact_en': f"Escalated: {esc.get('previous_severity', '?')} → {esc.get('current_severity', '?')}",
                    'urgency': esc.get('current_severity', 'high'),
                })

        # 3. High-threat battlecard
        battlecards = ci.get('battlecards', [])
        high_threats = [b for b in battlecards if b.get('threat_level') == 'high']
        for bc in high_threats[:1]:
            name = bc.get('competitor_name', '')
            findings.append({
                'title_fi': f'Kilpailija {name} on edellä',
                'title_en': f'Competitor {name} is ahead',
                'impact_fi': bc.get('inaction_timeline_fi', ''),
                'impact_en': bc.get('inaction_timeline_en', ''),
                'urgency': 'high',
            })

        return findings[:3]

    def _extract_top_actions(self, ci, guardian_result, lang) -> List[Dict]:
        """Extract top 3 prioritized actions with cost/ROI."""
        actions = []

        # From battlecard actions
        battlecards = ci.get('battlecards', [])
        for bc in battlecards:
            for action in bc.get('actions', []):
                if isinstance(action, dict):
                    actions.append({
                        'action_fi': action.get('action_fi', ''),
                        'action_en': action.get('action_en', ''),
                        'cost': action.get('cost_estimate_eur', 0),
                        'roi': action.get('roi_multiplier', 0),
                        'priority': action.get('priority', 3),
                        'hours': action.get('time_estimate_hours', 0),
                    })

        # Sort by priority then ROI
        actions.sort(key=lambda a: (a['priority'], -a['roi']))

        # Deduplicate by action text
        seen = set()
        unique = []
        for a in actions:
            key = a.get('action_fi', '')
            if key not in seen:
                seen.add(key)
                unique.append(a)

        return unique[:3]

    def _build_narrative_fi(self, brief: ExecutiveBrief) -> str:
        """Build template-based executive narrative in Finnish."""
        parts = []

        # 1. Status
        if brief.overall_score_change > 0:
            parts.append(
                f'Digitaalinen kilpailukykysi vahvistui ({brief.overall_score}/100, '
                f'+{brief.overall_score_change}p edellisestä).'
            )
        elif brief.overall_score_change < 0:
            parts.append(
                f'Digitaalinen kilpailukykysi heikkeni ({brief.overall_score}/100, '
                f'{brief.overall_score_change}p edellisestä).'
            )
        else:
            parts.append(f'Digitaalinen kilpailukykysi on tasolla {brief.overall_score}/100.')

        # 2. Key findings
        if brief.key_findings:
            top_finding = brief.key_findings[0]
            parts.append(f'Tärkein havainto: {top_finding.get("title_fi", "")}.')

        # 3. Threats
        if brief.threats_resolved > 0:
            parts.append(f'{brief.threats_resolved} uhkaa ratkaistu.')
        if brief.new_threats > 0:
            parts.append(f'{brief.new_threats} uutta uhkaa havaittu.')
        if brief.recurring_threats > 0:
            parts.append(
                f'{brief.recurring_threats} uhkaa toistuu eikä ole korjattu.'
            )

        # 4. Revenue at risk
        if brief.revenue_at_risk > 0:
            parts.append(
                f'Arviolta €{brief.revenue_at_risk:,}/vuosi vaarassa '
                f'ilman toimenpiteitä (estimaatti).'
            )

        # 5. Actions
        if brief.top_actions:
            action_strs = []
            for a in brief.top_actions[:3]:
                action_strs.append(
                    f'{a.get("action_fi", "")} '
                    f'({a.get("hours", 0)}h, €{a.get("cost", 0)}, ROI {a.get("roi", 0)}x)'
                )
            parts.append('Suositellut toimenpiteet: ' + '; '.join(action_strs) + '.')

        return ' '.join(parts)

    def _build_narrative_en(self, brief: ExecutiveBrief) -> str:
        """Build template-based executive narrative in English."""
        parts = []

        if brief.overall_score_change > 0:
            parts.append(
                f'Your digital competitiveness improved ({brief.overall_score}/100, '
                f'+{brief.overall_score_change} from previous).'
            )
        elif brief.overall_score_change < 0:
            parts.append(
                f'Your digital competitiveness declined ({brief.overall_score}/100, '
                f'{brief.overall_score_change} from previous).'
            )
        else:
            parts.append(f'Your digital competitiveness is at {brief.overall_score}/100.')

        if brief.key_findings:
            top_finding = brief.key_findings[0]
            parts.append(f'Key finding: {top_finding.get("title_en", "")}.')

        if brief.revenue_at_risk > 0:
            parts.append(
                f'Estimated €{brief.revenue_at_risk:,}/year at risk without action.'
            )

        if brief.top_actions:
            parts.append(
                f'Top {len(brief.top_actions)} recommended actions available.'
            )

        return ' '.join(parts)

    # =========================================================================
    # LLM PROMPT (for enhanced narratives, optional)
    # =========================================================================

    def build_llm_prompt(self, brief: ExecutiveBrief) -> str:
        """Build LLM prompt for enhanced narrative generation.

        Anti-hallucination: only verified data in prompt, guardrails added.
        """
        findings_str = '\n'.join([
            f"  - {f.get('title_fi', '')}: {f.get('impact_fi', '')}"
            for f in brief.key_findings
        ]) or '  (ei merkittäviä havaintoja)'

        actions_str = '\n'.join([
            f"  - {a.get('action_fi', '')} ({a.get('hours', 0)}h, €{a.get('cost', 0)}, ROI {a.get('roi', 0)}x)"
            for a in brief.top_actions
        ]) or '  (ei toimenpiteitä)'

        prompt = f"""Olet toimitusjohtajan neuvonantaja. Kirjoita tiivis liiketoimintakatsaus.

FAKTAT (käytä VAIN näitä):
- Ajanjakso: {brief.period}
- Kokonaispistemäärä: {brief.overall_score}/100 (muutos: {brief.overall_score_change:+d})
- Kilpailuasema: {brief.competitive_position or 'ei tiedossa'}
- Sijoitus: {brief.competitive_rank or 'ei tiedossa'}

UHKATILANNE:
- Uudet uhkat: {brief.new_threats}
- Ratkaistut: {brief.threats_resolved}
- Toistuvat (ei korjattu): {brief.recurring_threats}

HAVAINNOT:
{findings_str}

ARVIOIDUT MENETYKSET (estimaatti):
- Revenue at risk: arviolta €{brief.revenue_at_risk:,}/vuosi

SUOSITELLUT TOIMENPITEET:
{actions_str}

TRENDI: {brief.trend_direction}
{brief.prediction_fi or '(ei ennustetta saatavilla)'}

OHJE: Kirjoita 150-250 sanan brief suomeksi. Rakenne:
1. TILANNEKUVA (1-2 lausetta)
2. TÄRKEIN HAVAINTO (2-3 lausetta)
3. TOP 3 TOIMENPIDETTÄ
Puhu rahasta ja asiakkaista, ei tekniikasta.
Merkitse euromäärät sanalla "arviolta"."""

        return add_guardrails(prompt, 'fi')
