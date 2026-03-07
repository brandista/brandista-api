# -*- coding: utf-8 -*-
"""Unit tests for intelligence_brief.py — Gustav 2.0 executive briefs."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def _make_guardian_result():
    return {
        'rasm_score': 55,
        'threats': [
            {'category': 'seo', 'severity': 'high', 'title': 'SEO critical'},
            {'category': 'content', 'severity': 'medium', 'title': 'Content thin'},
        ],
        'competitor_threat_assessment': {
            'position': 'Challenged',
            'your_rank': 3,
            'total': 5,
            'assessments': [
                {'name': 'Das Auto', 'url': 'https://dasauto.fi', 'digital_score': 72, 'threat_level': 'high'},
            ],
        },
        'competitive_intelligence': {
            'battlecards': [{
                'competitor_name': 'Das Auto',
                'threat_level': 'high',
                'annual_risk': 15000,
                'monthly_risk': 1250,
                'inaction_timeline_fi': 'Reagoi 4 viikossa',
                'inaction_timeline_en': 'React in 4 weeks',
                'actions': [
                    {'action_fi': 'Julkaise blogi', 'action_en': 'Publish blog',
                     'cost_estimate_eur': 250, 'roi_multiplier': 7.2, 'priority': 1,
                     'time_estimate_hours': 3},
                ],
            }],
            'correlated_intelligence': [{
                'title_fi': 'Sisältövajehyökkäys',
                'title_en': 'Content Gap Attack',
                'combined_severity': 'high',
                'monthly_risk': 500,
            }],
            'inaction_cost': {
                'total_monthly_loss': {'value': 800, 'is_estimate': True},
                'total_annual_loss': {'value': 9600, 'is_estimate': True},
            },
        },
    }


class TestBriefGeneration:
    def test_generates_brief(self):
        from agents.intelligence_brief import IntelligenceBriefGenerator
        gen = IntelligenceBriefGenerator(language='fi')
        brief = gen.generate(
            url='https://bemufix.fi',
            guardian_result=_make_guardian_result(),
        )
        assert brief.url == 'https://bemufix.fi'
        assert brief.overall_score == 55
        assert brief.period != ''

    def test_brief_has_key_findings(self):
        from agents.intelligence_brief import IntelligenceBriefGenerator
        gen = IntelligenceBriefGenerator(language='fi')
        brief = gen.generate(
            url='https://bemufix.fi',
            guardian_result=_make_guardian_result(),
        )
        assert len(brief.key_findings) > 0
        assert len(brief.key_findings) <= 3

    def test_brief_has_top_actions(self):
        from agents.intelligence_brief import IntelligenceBriefGenerator
        gen = IntelligenceBriefGenerator(language='fi')
        brief = gen.generate(
            url='https://bemufix.fi',
            guardian_result=_make_guardian_result(),
        )
        assert len(brief.top_actions) > 0
        assert brief.top_actions[0].get('action_fi') != ''

    def test_brief_narrative_fi(self):
        from agents.intelligence_brief import IntelligenceBriefGenerator
        gen = IntelligenceBriefGenerator(language='fi')
        brief = gen.generate(
            url='https://bemufix.fi',
            guardian_result=_make_guardian_result(),
        )
        assert brief.narrative_fi != ''
        assert '55' in brief.narrative_fi or 'kilpailuky' in brief.narrative_fi.lower()

    def test_brief_with_delta(self):
        from agents.intelligence_brief import IntelligenceBriefGenerator
        gen = IntelligenceBriefGenerator(language='fi')
        delta = {
            'new_threats': [{'explanation_fi': 'Uusi uhka'}],
            'resolved_threats': [{'explanation_fi': 'Ratkaistu'}],
            'escalated_threats': [],
            'recurring_threats': [{'threat': {}, 'occurrences': 3}],
            'score_changes': {'overall': {'delta': -3}},
        }
        brief = gen.generate(
            url='https://bemufix.fi',
            guardian_result=_make_guardian_result(),
            delta=delta,
        )
        assert brief.overall_score_change == -3
        assert brief.threats_resolved == 1
        assert brief.new_threats == 1

    def test_brief_to_dict(self):
        from agents.intelligence_brief import IntelligenceBriefGenerator
        gen = IntelligenceBriefGenerator(language='fi')
        brief = gen.generate(
            url='https://bemufix.fi',
            guardian_result=_make_guardian_result(),
        )
        d = brief.to_dict()
        assert isinstance(d, dict)
        assert 'key_findings' in d
        assert 'narrative_fi' in d

    def test_brief_revenue_at_risk(self):
        from agents.intelligence_brief import IntelligenceBriefGenerator
        gen = IntelligenceBriefGenerator(language='fi')
        brief = gen.generate(
            url='https://bemufix.fi',
            guardian_result=_make_guardian_result(),
        )
        assert brief.revenue_at_risk > 0

    def test_llm_prompt_has_guardrails(self):
        from agents.intelligence_brief import IntelligenceBriefGenerator
        gen = IntelligenceBriefGenerator(language='fi')
        brief = gen.generate(
            url='https://bemufix.fi',
            guardian_result=_make_guardian_result(),
        )
        prompt = gen.build_llm_prompt(brief)
        assert 'KÄYTÄ VAIN' in prompt
        assert 'ÄLÄ keksi' in prompt
        assert 'arviolta' in prompt
