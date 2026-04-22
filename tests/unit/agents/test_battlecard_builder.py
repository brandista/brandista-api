# -*- coding: utf-8 -*-
"""
Unit tests for agents/battlecard_builder.py

Covers:
- Pure helpers: _extract_category_score, _build_benchmark, _build_category_comparison,
  _threat_level_from_gap, _build_competitor_assessments
- Public async entry: build_competitive_intelligence — happy path + edge cases
"""

import pytest
from typing import Any, Dict, List

from agents.battlecard_builder import (
    _extract_category_score,
    _build_benchmark,
    _build_category_comparison,
    _threat_level_from_gap,
    _build_competitor_assessments,
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
