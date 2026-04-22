# -*- coding: utf-8 -*-
"""
Unit tests for agents/battlecard_builder.py

Covers:
- Pure helpers: _extract_category_score, _build_benchmark, _build_category_comparison,
  _threat_level_from_gap, _build_competitor_assessments
- Public async entry: build_competitive_intelligence — happy path + edge cases
"""

import pytest
import sys
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

from agents.battlecard_builder import (
    _extract_category_score,
    _build_benchmark,
    _build_category_comparison,
    _threat_level_from_gap,
    _build_competitor_assessments,
    _generate_executive_summary,
    _detect_cross_competitor_patterns,
    enrich_with_ai_insights,
    build_competitive_intelligence,
)


# =============================================================================
# FIXTURES
# =============================================================================

def _analysis(score: int, breakdown: Dict[str, int] | None = None, ai_score: int = 0) -> Dict[str, Any]:
    """Shape of a real analysis dict — basic_analysis.digital_maturity_score + breakdown."""
    return {
        'url': 'https://example.fi',
        'final_score': score,
        'basic_analysis': {
            'digital_maturity_score': score,
            'score_breakdown': breakdown or {},
        },
        'enhanced_features': {
            'ai_search_visibility': {'overall_ai_search_score': ai_score},
        },
    }


# =============================================================================
# _extract_category_score
# =============================================================================

class TestExtractCategoryScore:
    def test_seo_normalized_from_20_to_100(self):
        a = _analysis(60, breakdown={'seo_basics': 10})
        assert _extract_category_score(a, 'seo') == 50

    def test_security_normalized_from_15_to_100(self):
        a = _analysis(60, breakdown={'security': 15})
        assert _extract_category_score(a, 'security') == 100

    def test_performance_normalized_from_5_to_100(self):
        a = _analysis(60, breakdown={'performance': 4})
        assert _extract_category_score(a, 'performance') == 80

    def test_missing_breakdown_returns_zero(self):
        a = _analysis(60, breakdown={})
        assert _extract_category_score(a, 'content') == 0

    def test_ai_visibility_from_enhanced_features(self):
        a = _analysis(60, ai_score=75)
        assert _extract_category_score(a, 'ai_visibility') == 75

    def test_ai_visibility_fallback_to_detailed_analysis(self):
        a = {
            'basic_analysis': {},
            'detailed_analysis': {'ai_search_visibility': {'overall_ai_search_score': 42}},
        }
        assert _extract_category_score(a, 'ai_visibility') == 42


# =============================================================================
# _build_benchmark
# =============================================================================

class TestBuildBenchmark:
    def test_empty_competitors_returns_solo_position(self):
        result = _build_benchmark(_analysis(70), [])
        assert result['your_score'] == 70
        assert result['your_position'] == 1
        assert result['total_analyzed'] == 1
        assert result['avg_competitor_score'] == 0

    def test_ahead_of_all_competitors(self):
        target = _analysis(80)
        comps = [_analysis(60), _analysis(50), _analysis(40)]
        result = _build_benchmark(target, comps)
        assert result['your_position'] == 1
        assert result['max_competitor_score'] == 60
        assert result['min_competitor_score'] == 40
        assert result['avg_competitor_score'] == 50

    def test_behind_all_competitors(self):
        target = _analysis(30)
        comps = [_analysis(60), _analysis(70), _analysis(80)]
        result = _build_benchmark(target, comps)
        assert result['your_position'] == 4
        assert result['total_analyzed'] == 4

    def test_uses_final_score_preferred_over_breakdown(self):
        # final_score set directly
        target = _analysis(75)
        comps = [_analysis(50)]
        result = _build_benchmark(target, comps)
        assert result['your_score'] == 75


# =============================================================================
# _build_category_comparison
# =============================================================================

class TestBuildCategoryComparison:
    def test_all_categories_present(self):
        target = _analysis(60, breakdown={'seo_basics': 15, 'security': 12})
        comps = [_analysis(50, breakdown={'seo_basics': 10, 'security': 10})]
        result = _build_category_comparison(target, comps)
        for cat in ('seo', 'performance', 'security', 'content', 'ux', 'ai_visibility'):
            assert cat in result
            assert 'your_score' in result[cat]
            assert 'competitor_avg' in result[cat]
            assert 'difference' in result[cat]
            assert result[cat]['status'] in ('ahead', 'behind', 'even')

    def test_ahead_when_diff_greater_than_5(self):
        target = _analysis(60, breakdown={'seo_basics': 20})  # 100
        comps = [_analysis(50, breakdown={'seo_basics': 5})]  # 25
        result = _build_category_comparison(target, comps)
        assert result['seo']['status'] == 'ahead'

    def test_behind_when_diff_less_than_minus_5(self):
        target = _analysis(60, breakdown={'seo_basics': 5})  # 25
        comps = [_analysis(50, breakdown={'seo_basics': 20})]  # 100
        result = _build_category_comparison(target, comps)
        assert result['seo']['status'] == 'behind'

    def test_even_when_scores_close(self):
        target = _analysis(60, breakdown={'seo_basics': 10})  # 50
        comps = [_analysis(50, breakdown={'seo_basics': 10})]  # 50
        result = _build_category_comparison(target, comps)
        assert result['seo']['status'] == 'even'


# =============================================================================
# _threat_level_from_gap
# =============================================================================

class TestThreatLevelFromGap:
    def test_high_when_10_plus_ahead(self):
        assert _threat_level_from_gap(10) == 'high'
        assert _threat_level_from_gap(25) == 'high'

    def test_medium_when_slightly_ahead_or_equal(self):
        assert _threat_level_from_gap(0) == 'medium'
        assert _threat_level_from_gap(9) == 'medium'

    def test_low_when_behind(self):
        assert _threat_level_from_gap(-1) == 'low'
        assert _threat_level_from_gap(-20) == 'low'


# =============================================================================
# _build_competitor_assessments
# =============================================================================

class TestBuildCompetitorAssessments:
    def test_matches_enriched_by_url(self):
        comps = [
            {'url': 'https://a.fi', 'final_score': 60, 'basic_analysis': {'digital_maturity_score': 60}},
        ]
        enriched = [{'url': 'https://a.fi', 'company_name': 'A Oy', 'revenue': 500000, 'employees': 5}]
        result = _build_competitor_assessments(comps, your_score=50, competitors_enriched=enriched)
        assert result[0]['name'] == 'A Oy'
        assert result[0]['company_intel']['revenue'] == 500000
        assert result[0]['company_intel']['source'] == 'registry'

    def test_without_enriched_falls_back_to_estimated_source(self):
        comps = [
            {'url': 'https://a.fi', 'final_score': 60, 'basic_analysis': {'digital_maturity_score': 60}},
        ]
        result = _build_competitor_assessments(comps, your_score=50, competitors_enriched=None)
        assert result[0]['company_intel']['source'] == 'estimated'
        assert result[0]['company_intel']['revenue'] is None
        assert result[0]['signals']['has_real_data'] is False

    def test_threat_level_sorted_high_first(self):
        comps = [
            {'url': 'https://low.fi', 'final_score': 30, 'basic_analysis': {'digital_maturity_score': 30}},  # low
            {'url': 'https://high.fi', 'final_score': 70, 'basic_analysis': {'digital_maturity_score': 70}},  # high
            {'url': 'https://mid.fi', 'final_score': 55, 'basic_analysis': {'digital_maturity_score': 55}},  # medium
        ]
        result = _build_competitor_assessments(comps, your_score=50, competitors_enriched=None)
        levels = [a['threat_level'] for a in result]
        assert levels == ['high', 'medium', 'low']

    def test_score_diff_calculation(self):
        comps = [{'url': 'https://a.fi', 'final_score': 75, 'basic_analysis': {'digital_maturity_score': 75}}]
        result = _build_competitor_assessments(comps, your_score=60)
        assert result[0]['score_diff'] == 15


# =============================================================================
# build_competitive_intelligence — public async entry
# =============================================================================

class TestBuildCompetitiveIntelligence:
    @pytest.mark.asyncio
    async def test_empty_competitors_returns_safe_empty(self):
        result = await build_competitive_intelligence(
            target_analysis=_analysis(60),
            competitor_analyses=[],
        )
        assert result['battlecards'] == []
        assert result['correlated_intelligence'] == []
        assert result['inaction_cost'] == {}
        assert 'ei kilpailija' in result.get('data_quality', {}).get('reason', '')

    @pytest.mark.asyncio
    async def test_happy_path_returns_battlecards(self):
        target = _analysis(60, breakdown={
            'seo_basics': 12, 'security': 12, 'content': 15,
            'performance': 3, 'mobile': 12, 'social': 7, 'technical': 12,
        }, ai_score=55)
        comp = _analysis(70, breakdown={
            'seo_basics': 16, 'security': 13, 'content': 17,
            'performance': 4, 'mobile': 13, 'social': 8, 'technical': 13,
        }, ai_score=65)
        comp['url'] = 'https://threat.fi'
        comp['domain'] = 'threat.fi'

        enriched = [{
            'url': 'https://threat.fi',
            'company_name': 'Threat Oy',
            'revenue': 800000,
            'employees': 10,
        }]

        result = await build_competitive_intelligence(
            target_analysis=target,
            competitor_analyses=[comp],
            competitors_enriched=enriched,
            industry='jewelry',
            language='fi',
            annual_revenue=500000,
        )

        assert len(result.get('battlecards', [])) == 1
        bc = result['battlecards'][0]
        assert bc['competitor_name'] == 'Threat Oy'
        assert bc['competitor_score'] == 70
        assert bc['your_score'] == 60
        assert bc['threat_level'] == 'high'  # 10 points ahead
        assert bc['monthly_risk'] > 0  # score_gap drives risk
        assert 'transparency' in result
        assert 'provenance' in result
        assert 'data_quality' in result

    @pytest.mark.asyncio
    async def test_target_ahead_produces_low_threat_battlecards(self):
        target = _analysis(80, breakdown={'seo_basics': 18, 'security': 14})
        comp = _analysis(40, breakdown={'seo_basics': 8, 'security': 7})
        comp['url'] = 'https://behind.fi'

        result = await build_competitive_intelligence(
            target_analysis=target,
            competitor_analyses=[comp],
            competitors_enriched=None,
            industry='general',
        )

        assert len(result.get('battlecards', [])) == 1
        bc = result['battlecards'][0]
        assert bc['threat_level'] == 'low'
        assert bc['monthly_risk'] == 0  # you're ahead → no risk from gap

    @pytest.mark.asyncio
    async def test_result_shape_matches_engine_contract(self):
        """Engine contract: battlecards, correlated_intelligence, inaction_cost, data_quality, provenance, transparency."""
        target = _analysis(60)
        comp = _analysis(55)
        comp['url'] = 'https://c.fi'
        result = await build_competitive_intelligence(
            target_analysis=target,
            competitor_analyses=[comp],
        )
        required = {'battlecards', 'correlated_intelligence', 'inaction_cost',
                    'data_quality', 'provenance', 'transparency'}
        assert required.issubset(result.keys())


# =============================================================================
# AI INSIGHTS ENRICHMENT (3a executive summaries + 3c cross-patterns)
# =============================================================================

@pytest.fixture
def fake_battlecard() -> Dict[str, Any]:
    """A minimal battlecard dict as produced by CompetitiveIntelligenceEngine."""
    return {
        'competitor_name': 'Acme Oy',
        'competitor_url': 'https://acme.fi',
        'competitor_score': 70,
        'your_score': 55,
        'threat_level': 'high',
        'monthly_risk': 5000,
        'annual_risk': 60000,
        'you_win': [{'dimension': 'performance', 'difference': '+10'}],
        'they_win': [
            {'dimension': 'seo', 'difference': '+15'},
            {'dimension': 'content', 'difference': '+8'},
        ],
        'actions': [{'title': 'Improve SEO', 'roi': 8.5}],
        'inaction_timeline_fi': 'Acme ohittaa 4-6 viikossa',
        'inaction_timeline_en': 'Acme overtakes in 4-6 weeks',
    }


class TestExecutiveSummary:
    @pytest.mark.asyncio
    async def test_returns_llm_text_when_available(self, fake_battlecard):
        fake_llm = AsyncMock(return_value="  Acme on 15 pistettä edellä. Toimi nyt.  ")
        result = await _generate_executive_summary(
            fake_battlecard, your_score=55, language='fi', safe_llm_call=fake_llm
        )
        assert result == "Acme on 15 pistettä edellä. Toimi nyt."
        # Check known_facts was passed for validation
        called_kwargs = fake_llm.call_args.kwargs
        assert called_kwargs['known_facts']['competitor_name'] == 'Acme Oy'
        assert called_kwargs['known_facts']['competitor_score'] == 70
        assert called_kwargs['known_facts']['your_score'] == 55

    @pytest.mark.asyncio
    async def test_returns_none_when_llm_returns_none(self, fake_battlecard):
        fake_llm = AsyncMock(return_value=None)
        result = await _generate_executive_summary(
            fake_battlecard, your_score=55, language='fi', safe_llm_call=fake_llm
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_english_prompt_used_for_en_language(self, fake_battlecard):
        fake_llm = AsyncMock(return_value="Acme is 15 points ahead.")
        await _generate_executive_summary(
            fake_battlecard, your_score=55, language='en', safe_llm_call=fake_llm
        )
        prompt = fake_llm.call_args.args[0]
        assert 'executive-level competitive analyst' in prompt
        assert 'COMPETITOR STRENGTHS' in prompt


class TestCrossCompetitorPatterns:
    @pytest.mark.asyncio
    async def test_returns_empty_for_single_battlecard(self, fake_battlecard):
        fake_llm = AsyncMock(return_value='{"patterns": []}')
        result = await _detect_cross_competitor_patterns(
            [fake_battlecard], your_score=55, language='fi', safe_llm_call=fake_llm
        )
        assert result == []
        # LLM not called when <2 battlecards
        fake_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_parses_valid_patterns(self, fake_battlecard):
        bc2 = dict(fake_battlecard, competitor_name='Beta Oy', competitor_score=65)
        fake_llm = AsyncMock(return_value=(
            '{"patterns": [{"pattern": "Both beat you in SEO", '
            '"evidence": "Acme +15, Beta +12", '
            '"affected_competitors": ["Acme Oy", "Beta Oy"], '
            '"strategic_implication": "Systemic SEO gap", '
            '"confidence": "extracted"}]}'
        ))
        result = await _detect_cross_competitor_patterns(
            [fake_battlecard, bc2], your_score=55, language='fi', safe_llm_call=fake_llm
        )
        assert len(result) == 1
        assert result[0]['pattern'] == 'Both beat you in SEO'
        assert 'Acme Oy' in result[0]['affected_competitors']
        assert result[0]['confidence'] == 'extracted'

    @pytest.mark.asyncio
    async def test_skips_malformed_patterns(self, fake_battlecard):
        bc2 = dict(fake_battlecard, competitor_name='Beta Oy')
        fake_llm = AsyncMock(return_value=(
            '{"patterns": ['
            '{"pattern": "Valid", "evidence": "data"}, '
            '{"pattern": "", "evidence": "empty pattern skipped"}, '
            '{"not a dict": "also skipped"}'
            ']}'
        ))
        result = await _detect_cross_competitor_patterns(
            [fake_battlecard, bc2], your_score=55, language='fi', safe_llm_call=fake_llm
        )
        assert len(result) == 1
        assert result[0]['pattern'] == 'Valid'

    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty(self, fake_battlecard):
        bc2 = dict(fake_battlecard, competitor_name='Beta Oy')
        fake_llm = AsyncMock(return_value='not valid json')
        result = await _detect_cross_competitor_patterns(
            [fake_battlecard, bc2], your_score=55, language='fi', safe_llm_call=fake_llm
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_llm_none_returns_empty(self, fake_battlecard):
        bc2 = dict(fake_battlecard, competitor_name='Beta Oy')
        fake_llm = AsyncMock(return_value=None)
        result = await _detect_cross_competitor_patterns(
            [fake_battlecard, bc2], your_score=55, language='fi', safe_llm_call=fake_llm
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_invalid_confidence_defaults_to_inferred(self, fake_battlecard):
        bc2 = dict(fake_battlecard, competitor_name='Beta Oy')
        fake_llm = AsyncMock(return_value=(
            '{"patterns": [{"pattern": "X", "evidence": "Y", "confidence": "high"}]}'
        ))
        result = await _detect_cross_competitor_patterns(
            [fake_battlecard, bc2], your_score=55, language='fi', safe_llm_call=fake_llm
        )
        assert result[0]['confidence'] == 'inferred'

    @pytest.mark.asyncio
    async def test_caps_at_4_patterns(self, fake_battlecard):
        bc2 = dict(fake_battlecard, competitor_name='Beta')
        patterns_json = '{"patterns": [' + ','.join(
            f'{{"pattern": "p{i}", "evidence": "e{i}"}}' for i in range(10)
        ) + ']}'
        fake_llm = AsyncMock(return_value=patterns_json)
        result = await _detect_cross_competitor_patterns(
            [fake_battlecard, bc2], your_score=55, language='fi', safe_llm_call=fake_llm
        )
        assert len(result) == 4


class TestEnrichWithAiInsights:
    @pytest.mark.asyncio
    async def test_graceful_when_safe_llm_call_unavailable(self, fake_battlecard, monkeypatch):
        # Simulate main.py missing / no safe_llm_call
        fake_main = MagicMock(spec=[])  # no safe_llm_call attribute
        monkeypatch.setitem(sys.modules, 'main', fake_main)

        intelligence = {'battlecards': [fake_battlecard]}
        result = await enrich_with_ai_insights(intelligence, language='fi')
        # Without safe_llm_call, intelligence returned unchanged
        assert 'ai_executive_summary_fi' not in result['battlecards'][0]

    @pytest.mark.asyncio
    async def test_empty_battlecards_returns_early(self, monkeypatch):
        fake_main = MagicMock()
        fake_main.safe_llm_call = AsyncMock(return_value="should not be called")
        monkeypatch.setitem(sys.modules, 'main', fake_main)

        result = await enrich_with_ai_insights({'battlecards': []}, language='fi')
        assert result == {'battlecards': []}
        fake_main.safe_llm_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_adds_summaries_and_patterns(self, fake_battlecard, monkeypatch):
        bc2 = dict(fake_battlecard, competitor_name='Beta Oy', competitor_score=65)

        # Mock safe_llm_call — different return per label
        async def fake_llm(prompt, **kwargs):
            label = kwargs.get('label', '')
            if 'exec_summary' in label:
                return f"Summary for {kwargs['known_facts']['competitor_name']}"
            if label == 'cross_competitor_patterns':
                return ('{"patterns": [{"pattern": "Shared SEO gap", '
                        '"evidence": "Acme +15, Beta +12", '
                        '"confidence": "extracted"}]}')
            return None

        fake_main = MagicMock()
        fake_main.safe_llm_call = fake_llm
        monkeypatch.setitem(sys.modules, 'main', fake_main)

        intelligence = {'battlecards': [fake_battlecard, bc2]}
        result = await enrich_with_ai_insights(intelligence, language='fi')

        # 3a — per-battlecard summaries
        assert result['battlecards'][0]['ai_executive_summary_fi'] == 'Summary for Acme Oy'
        assert result['battlecards'][1]['ai_executive_summary_fi'] == 'Summary for Beta Oy'
        # 3c — cross-patterns
        assert len(result['cross_competitor_insights']) == 1
        assert result['cross_competitor_insights'][0]['pattern'] == 'Shared SEO gap'

    @pytest.mark.asyncio
    async def test_llm_exceptions_dont_crash(self, fake_battlecard, monkeypatch):
        async def flaky_llm(prompt, **kwargs):
            raise RuntimeError("OpenAI down")

        fake_main = MagicMock()
        fake_main.safe_llm_call = flaky_llm
        monkeypatch.setitem(sys.modules, 'main', fake_main)

        bc2 = dict(fake_battlecard, competitor_name='Beta')
        intelligence = {'battlecards': [fake_battlecard, bc2]}
        result = await enrich_with_ai_insights(intelligence, language='fi')

        # No summaries added, no crash, cross_competitor_insights empty
        assert 'ai_executive_summary_fi' not in result['battlecards'][0]
        assert result.get('cross_competitor_insights') == []

    @pytest.mark.asyncio
    async def test_english_adds_en_field(self, fake_battlecard, monkeypatch):
        async def fake_llm(prompt, **kwargs):
            if 'exec_summary' in kwargs.get('label', ''):
                return "English summary"
            return '{"patterns": []}'

        fake_main = MagicMock()
        fake_main.safe_llm_call = fake_llm
        monkeypatch.setitem(sys.modules, 'main', fake_main)

        bc2 = dict(fake_battlecard, competitor_name='Beta')
        result = await enrich_with_ai_insights({'battlecards': [fake_battlecard, bc2]}, language='en')
        assert result['battlecards'][0]['ai_executive_summary_en'] == 'English summary'
        assert 'ai_executive_summary_fi' not in result['battlecards'][0]
