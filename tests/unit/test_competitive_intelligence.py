# -*- coding: utf-8 -*-
"""Unit tests for competitive_intelligence.py — Gustav 2.0 battlecards & intelligence."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# =============================================================================
# FIXTURES: Realistic test data
# =============================================================================

def _make_your_analysis(score=55, word_count=559):
    """Create a realistic your_analysis dict."""
    return {
        'basic_analysis': {
            'website': 'bemufix.fi',
            'digital_maturity_score': score,
            'word_count': word_count,
            'social_platforms': 2,
            'score_breakdown': {
                'seo': 12, 'seo_basics': 12,
                'content': 6,
                'performance': 8,
                'security': 10,
                'mobile': 12,
                'social': 3,
            },
        },
        'detailed_analysis': {
            'technical_audit': {'performance_score': 72},
            'content_analysis': {'word_count': word_count},
            'ai_search_visibility': {'overall_ai_search_score': 35},
        },
        'enhanced_features': {
            'ai_search_visibility': {'overall_ai_search_score': 35},
        },
    }


def _make_competitor_analysis(url='https://dasauto.fi', word_count=2400, score=72):
    """Create a realistic competitor analysis dict."""
    return {
        'url': url,
        'basic_analysis': {
            'website': url,
            'digital_maturity_score': score,
            'word_count': word_count,
            'social_platforms': 4,
            'score_breakdown': {
                'seo': 15, 'seo_basics': 15,
                'content': 12,
                'performance': 10,
                'security': 12,
                'mobile': 13,
                'social': 5,
            },
        },
    }


def _make_assessment(url='https://dasauto.fi', name='Das Auto', score=72, threat='high'):
    """Create a realistic competitor threat assessment."""
    return {
        'url': url,
        'name': name,
        'digital_score': score,
        'threat_level': threat,
        'company_intel': {
            'source': 'registry',
            'revenue': 850000,
            'employees': 8,
        },
        'signals': {
            'domain_age': {'age_years': 5},
            'growth_signals': {'is_hiring': True, 'active_blog': True},
        },
    }


def _make_benchmark(your_score=55, avg_comp=68):
    return {
        'your_score': your_score,
        'avg_competitor_score': avg_comp,
        'your_position': 3,
        'total_analyzed': 4,
    }


def _make_category_comparison():
    return {
        'seo': {'your_score': 42, 'competitor_avg': 65, 'status': 'behind', 'difference': -23},
        'content': {'your_score': 36, 'competitor_avg': 72, 'status': 'behind', 'difference': -36},
        'performance': {'your_score': 72, 'competitor_avg': 60, 'status': 'ahead', 'difference': 12},
        'ai_visibility': {'your_score': 35, 'competitor_avg': 50, 'status': 'behind', 'difference': -15},
    }


def _make_engine(**kwargs):
    from agents.competitive_intelligence import CompetitiveIntelligenceEngine
    defaults = {
        'your_analysis': _make_your_analysis(),
        'competitor_analyses': [_make_competitor_analysis()],
        'competitor_assessments': [_make_assessment()],
        'category_comparison': _make_category_comparison(),
        'benchmark': _make_benchmark(),
        'annual_revenue': 500_000,
        'industry': 'auto_repair',
        'language': 'fi',
    }
    defaults.update(kwargs)
    return CompetitiveIntelligenceEngine(**defaults)


# =============================================================================
# TESTS: Battlecard Generation
# =============================================================================

class TestBattlecardGeneration:
    """Test battlecard generation."""

    def test_generates_battlecard_for_each_competitor(self):
        engine = _make_engine()
        battlecards = engine.generate_battlecards()
        assert len(battlecards) == 1
        assert battlecards[0].competitor_name == 'Das Auto'

    def test_battlecard_has_required_fields(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]

        assert bc.competitor_url == 'https://dasauto.fi'
        assert bc.competitor_score == 72
        assert bc.your_score == 55
        assert isinstance(bc.you_win, list)
        assert isinstance(bc.they_win, list)
        assert isinstance(bc.actions, list)
        assert bc.threat_level == 'high'
        assert bc.generated_at != ''

    def test_battlecard_has_data_sources(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        assert 'HTML-analyysi' in bc.data_sources
        assert 'YTJ/Kauppalehti' in bc.data_sources  # registry source

    def test_battlecard_content_comparison(self):
        """When competitor has more content, it should be in they_win."""
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]

        # Competitor: 2400 words vs our 559 → they_win
        content_losses = [w for w in bc.they_win if 'Sisältö' in w.get('area_fi', '')]
        assert len(content_losses) > 0

    def test_battlecard_to_dict(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        d = bc.to_dict()
        assert isinstance(d, dict)
        assert 'competitor_name' in d
        assert 'actions' in d

    def test_multiple_competitors(self):
        comps = [
            _make_competitor_analysis('https://dasauto.fi', 2400, 72),
            _make_competitor_analysis('https://bmwhelsinki.fi', 1800, 65),
        ]
        assessments = [
            _make_assessment('https://dasauto.fi', 'Das Auto', 72, 'high'),
            _make_assessment('https://bmwhelsinki.fi', 'BMW Helsinki', 65, 'medium'),
        ]
        engine = _make_engine(
            competitor_analyses=comps,
            competitor_assessments=assessments,
        )
        battlecards = engine.generate_battlecards()
        assert len(battlecards) == 2
        # Sorted by threat level (high first)
        assert battlecards[0].threat_level == 'high'

    def test_no_competitors(self):
        engine = _make_engine(
            competitor_analyses=[],
            competitor_assessments=[],
        )
        battlecards = engine.generate_battlecards()
        assert battlecards == []


class TestBattlecardMoneyEstimates:
    """Test that financial estimates are properly tracked."""

    def test_monthly_risk_calculated(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        # Competitor 72 vs our 55 → gap of 17 → should have risk
        assert bc.monthly_risk > 0
        assert bc.annual_risk == bc.monthly_risk * 12

    def test_no_risk_when_ahead(self):
        engine = _make_engine(
            benchmark=_make_benchmark(your_score=80, avg_comp=60),
            competitor_assessments=[_make_assessment(score=60, threat='low')],
        )
        bc = engine.generate_battlecards()[0]
        # We're ahead (80 > 60) → no risk from being behind
        assert bc.monthly_risk == 0

    def test_confidence_with_registry_data(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        # Has registry source → higher confidence
        assert bc.confidence == 0.85

    def test_confidence_without_registry(self):
        assessment = _make_assessment()
        assessment['company_intel']['source'] = 'estimated'
        engine = _make_engine(competitor_assessments=[assessment])
        bc = engine.generate_battlecards()[0]
        assert bc.confidence == 0.65


# =============================================================================
# TESTS: Action Playbook
# =============================================================================

class TestActionPlaybook:
    """Test action recommendation generation."""

    def test_actions_generated_for_weaknesses(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        assert len(bc.actions) > 0

    def test_actions_have_cost_and_roi(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        for action in bc.actions:
            assert action.cost_estimate_eur > 0
            assert action.time_estimate_hours > 0
            assert action.roi_multiplier >= 0
            assert action.priority in (1, 2, 3)

    def test_actions_sorted_by_roi(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        if len(bc.actions) > 1:
            rois = [a.roi_multiplier for a in bc.actions]
            assert rois == sorted(rois, reverse=True)

    def test_actions_max_5(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        assert len(bc.actions) <= 5

    def test_actions_bilingual(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        for action in bc.actions:
            assert action.action_fi != ''
            assert action.action_en != ''
            assert action.reasoning_fi != ''
            assert action.reasoning_en != ''


# =============================================================================
# TESTS: Threat Correlation
# =============================================================================

class TestCorrelationDetection:
    """Test correlated threat pattern detection."""

    def test_content_gap_attack_detected(self):
        """content < 40 AND competitor ahead by >15 → content_gap_attack."""
        cats = _make_category_comparison()
        cats['content']['your_score'] = 30  # Below 40
        engine = _make_engine(category_comparison=cats)
        corrs = engine.detect_correlations()

        types = [c.correlation_type for c in corrs]
        assert 'content_gap_attack' in types

    def test_digital_erosion_detected(self):
        """performance < 50 AND seo < 50 → digital_erosion."""
        cats = _make_category_comparison()
        cats['performance']['your_score'] = 38
        cats['seo']['your_score'] = 42
        # Force your_scores via your_analysis
        your = _make_your_analysis(score=40)
        your['basic_analysis']['score_breakdown']['performance'] = 38
        your['detailed_analysis']['technical_audit']['performance_score'] = 38

        engine = _make_engine(
            your_analysis=your,
            category_comparison=cats,
        )
        corrs = engine.detect_correlations()

        types = [c.correlation_type for c in corrs]
        assert 'digital_erosion' in types

    def test_ai_invisibility_detected(self):
        """ai_visibility < 40 AND content < 50 → ai_invisibility."""
        cats = _make_category_comparison()
        cats['ai_visibility']['your_score'] = 25
        cats['content']['your_score'] = 35
        your = _make_your_analysis(score=40)
        your['enhanced_features']['ai_search_visibility']['overall_ai_search_score'] = 25

        engine = _make_engine(your_analysis=your, category_comparison=cats)
        corrs = engine.detect_correlations()

        types = [c.correlation_type for c in corrs]
        assert 'ai_invisibility' in types

    def test_correlation_has_evidence(self):
        cats = _make_category_comparison()
        cats['content']['your_score'] = 30
        engine = _make_engine(category_comparison=cats)
        corrs = engine.detect_correlations()

        for corr in corrs:
            assert len(corr.evidence) > 0
            assert corr.combined_severity in ('critical', 'high', 'medium', 'low')

    def test_correlation_has_actions(self):
        cats = _make_category_comparison()
        cats['content']['your_score'] = 30
        engine = _make_engine(category_comparison=cats)
        corrs = engine.detect_correlations()

        for corr in corrs:
            assert len(corr.actions) > 0

    def test_no_correlations_when_scores_good(self):
        """High scores → no correlations triggered."""
        cats = {
            'seo': {'your_score': 80, 'competitor_avg': 70, 'status': 'ahead', 'difference': 10},
            'content': {'your_score': 75, 'competitor_avg': 65, 'status': 'ahead', 'difference': 10},
            'performance': {'your_score': 85, 'competitor_avg': 70, 'status': 'ahead', 'difference': 15},
            'ai_visibility': {'your_score': 70, 'competitor_avg': 55, 'status': 'ahead', 'difference': 15},
            'security': {'your_score': 80, 'competitor_avg': 70, 'status': 'ahead', 'difference': 10},
            'mobile': {'your_score': 85, 'competitor_avg': 75, 'status': 'ahead', 'difference': 10},
        }
        # Must also set high scores in the analysis breakdown so _extract_category_scores
        # returns values above correlation thresholds
        your = _make_your_analysis(score=80)
        your['basic_analysis']['score_breakdown'] = {
            'seo': 80, 'seo_basics': 80,
            'content': 75,
            'performance': 85,
            'security': 80,
            'mobile': 85,
            'social': 70,
        }
        your['detailed_analysis']['technical_audit']['performance_score'] = 85
        your['enhanced_features']['ai_search_visibility']['overall_ai_search_score'] = 70

        engine = _make_engine(
            your_analysis=your,
            category_comparison=cats,
            benchmark=_make_benchmark(your_score=80, avg_comp=65),
            competitor_assessments=[_make_assessment(score=65, threat='low')],
        )
        corrs = engine.detect_correlations()
        assert len(corrs) == 0


# =============================================================================
# TESTS: Inaction Cost
# =============================================================================

class TestInactionCost:
    """Test inaction cost calculation."""

    def test_inaction_cost_structure(self):
        engine = _make_engine()
        cost = engine.calculate_total_inaction_cost()

        assert 'total_monthly_loss' in cost
        assert 'total_annual_loss' in cost
        assert 'category_breakdown' in cost
        assert 'explanation_fi' in cost
        assert 'explanation_en' in cost
        assert 'data_quality' in cost

    def test_inaction_cost_has_estimates(self):
        """Financial values should be wrapped as estimates."""
        engine = _make_engine()
        cost = engine.calculate_total_inaction_cost()

        monthly = cost['total_monthly_loss']
        assert isinstance(monthly, dict)
        assert monthly['is_estimate'] is True
        assert 'best_case' in monthly
        assert 'worst_case' in monthly

    def test_inaction_cost_categories(self):
        engine = _make_engine()
        cost = engine.calculate_total_inaction_cost()

        breakdown = cost['category_breakdown']
        # We're behind in seo, content, ai_visibility → should have entries
        assert len(breakdown) > 0

    def test_no_inaction_cost_when_ahead(self):
        cats = {
            'seo': {'your_score': 80, 'competitor_avg': 70, 'difference': 10},
            'content': {'your_score': 75, 'competitor_avg': 65, 'difference': 10},
        }
        engine = _make_engine(category_comparison=cats)
        cost = engine.calculate_total_inaction_cost()

        monthly = cost['total_monthly_loss']
        assert monthly['value'] == 0

    def test_inaction_cost_range(self):
        """Best case should be less than worst case."""
        engine = _make_engine()
        cost = engine.calculate_total_inaction_cost()

        monthly = cost['total_monthly_loss']
        if monthly['value'] > 0:
            assert monthly['best_case'] < monthly['value']
            assert monthly['worst_case'] > monthly['value']


# =============================================================================
# TESTS: Full Intelligence Generation
# =============================================================================

class TestFullIntelligence:
    """Test generate_full_intelligence() — main entry point."""

    def test_full_intelligence_structure(self):
        engine = _make_engine()
        result = engine.generate_full_intelligence()

        assert 'battlecards' in result
        assert 'correlated_intelligence' in result
        assert 'inaction_cost' in result
        assert 'data_quality' in result
        assert 'provenance' in result
        assert 'transparency' in result

    def test_data_quality_included(self):
        engine = _make_engine()
        result = engine.generate_full_intelligence()
        dq = result['data_quality']

        assert 'quality_score' in dq
        assert dq['total_data_points'] > 0
        assert 'data_quality_fi' in dq
        assert 'data_quality_en' in dq

    def test_provenance_tracks_inputs(self):
        engine = _make_engine()
        result = engine.generate_full_intelligence()
        prov = result['provenance']

        assert len(prov['records']) > 0
        assert len(prov['sources_used']) > 0

    def test_transparency_envelope(self):
        engine = _make_engine()
        result = engine.generate_full_intelligence()
        trans = result['transparency']

        assert 'confidence' in trans
        assert 'methodology_fi' in trans
        assert 'data_sources' in trans


# =============================================================================
# TESTS: LLM Prompt Builders
# =============================================================================

class TestPromptBuilders:
    """Test LLM prompt generation with anti-hallucination."""

    def test_threat_story_prompt_has_guardrails(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        prompt = engine.build_threat_story_prompt(bc)

        assert 'KÄYTÄ VAIN' in prompt
        assert 'ÄLÄ keksi' in prompt
        assert 'Das Auto' in prompt
        assert str(bc.your_score) in prompt

    def test_threat_story_prompt_marks_estimates(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        prompt = engine.build_threat_story_prompt(bc)

        assert 'arviolta' in prompt or 'estimaatti' in prompt

    def test_executive_brief_prompt_has_guardrails(self):
        engine = _make_engine()
        bcs = engine.generate_battlecards()
        corrs = engine.detect_correlations()
        cost = engine.calculate_total_inaction_cost()

        prompt = engine.build_executive_brief_prompt(bcs, corrs, cost)
        assert 'KÄYTÄ VAIN' in prompt
        assert 'ÄLÄ keksi' in prompt

    def test_executive_brief_prompt_has_data(self):
        engine = _make_engine()
        bcs = engine.generate_battlecards()
        corrs = engine.detect_correlations()
        cost = engine.calculate_total_inaction_cost()

        prompt = engine.build_executive_brief_prompt(bcs, corrs, cost)
        assert 'Das Auto' in prompt
        assert str(engine.your_score) in prompt


# =============================================================================
# TESTS: Narrative Builders
# =============================================================================

class TestNarrativeBuilders:
    """Test template-based narratives (no LLM, deterministic)."""

    def test_threat_narrative_fi_when_behind(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        assert 'Das Auto' in bc.threat_narrative_fi
        assert str(bc.competitor_score) in bc.threat_narrative_fi

    def test_threat_narrative_fi_when_ahead(self):
        engine = _make_engine(
            benchmark=_make_benchmark(your_score=80, avg_comp=60),
            competitor_assessments=[_make_assessment(score=60, threat='low')],
        )
        bc = engine.generate_battlecards()[0]
        assert 'edellä' in bc.threat_narrative_fi.lower()

    def test_threat_narrative_bilingual(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        assert bc.threat_narrative_fi != ''
        assert bc.threat_narrative_en != ''
        # Finnish version should have Finnish words
        assert any(w in bc.threat_narrative_fi for w in ['pistettä', 'edellä', 'hieman', 'Kriittisimmät', 'Olet'])

    def test_narrative_includes_revenue_from_registry(self):
        engine = _make_engine()
        bc = engine.generate_battlecards()[0]
        # Assessment has revenue 850000 from registry
        assert '850' in bc.threat_narrative_fi  # €850,000


class TestInactionTimeline:
    """Test inaction timeline messages."""

    def test_timeline_big_gap(self):
        """Gap > 20 → immediate action."""
        assessment = _make_assessment(score=80)
        engine = _make_engine(
            benchmark=_make_benchmark(your_score=55, avg_comp=75),
            competitor_assessments=[assessment],
        )
        bc = engine.generate_battlecards()[0]
        assert 'välittömästi' in bc.inaction_timeline_fi.lower() or 'edellä' in bc.inaction_timeline_fi.lower()

    def test_timeline_medium_gap(self):
        """Gap 10-20 → 4-6 weeks."""
        assessment = _make_assessment(score=70)
        engine = _make_engine(
            benchmark=_make_benchmark(your_score=55, avg_comp=65),
            competitor_assessments=[assessment],
        )
        bc = engine.generate_battlecards()[0]
        assert 'viikko' in bc.inaction_timeline_fi.lower() or 'viikossa' in bc.inaction_timeline_fi.lower() or 'kuukaude' in bc.inaction_timeline_fi.lower()

    def test_timeline_when_ahead(self):
        """No gap → maintain lead."""
        assessment = _make_assessment(score=50, threat='low')
        engine = _make_engine(
            benchmark=_make_benchmark(your_score=80, avg_comp=50),
            competitor_assessments=[assessment],
        )
        bc = engine.generate_battlecards()[0]
        assert 'edellä' in bc.inaction_timeline_fi.lower() or 'ylläpidä' in bc.inaction_timeline_fi.lower()
