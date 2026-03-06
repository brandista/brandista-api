# -*- coding: utf-8 -*-
"""
Unit tests for agents/scoring_constants.py

Tests all threshold functions, tier classifications, and edge cases.
"""

import pytest
from agents.scoring_constants import (
    SCORE_THRESHOLDS,
    FACTOR_STATUS_THRESHOLDS,
    RISK_THRESHOLDS,
    IMPACT_SCORES,
    EFFORT_SCORES,
    CHATGPT_WEIGHTS,
    PERPLEXITY_WEIGHTS,
    STRATEGIC_CATEGORY_WEIGHTS,
    interpret_score,
    interpret_score_detailed,
    score_to_risk_level,
    calculate_roi_score,
    classify_financial_risk,
    factor_status,
    get_positioning_tier,
    get_competitive_position,
    classify_tech_modernity,
    DEFAULT_ANNUAL_REVENUE_EUR,
)


# =============================================================================
# interpret_score
# =============================================================================

class TestInterpretScore:
    def test_excellent(self):
        assert interpret_score(80) == 'excellent'
        assert interpret_score(100) == 'excellent'
        assert interpret_score(95) == 'excellent'

    def test_good(self):
        assert interpret_score(60) == 'good'
        assert interpret_score(79) == 'good'

    def test_average(self):
        assert interpret_score(40) == 'average'
        assert interpret_score(59) == 'average'

    def test_poor(self):
        assert interpret_score(20) == 'poor'
        assert interpret_score(39) == 'poor'

    def test_critical(self):
        assert interpret_score(0) == 'critical'
        assert interpret_score(19) == 'critical'

    def test_boundaries(self):
        """Test exact boundary values"""
        assert interpret_score(80) == 'excellent'
        assert interpret_score(79) == 'good'
        assert interpret_score(60) == 'good'
        assert interpret_score(59) == 'average'
        assert interpret_score(40) == 'average'
        assert interpret_score(39) == 'poor'
        assert interpret_score(20) == 'poor'
        assert interpret_score(19) == 'critical'


class TestInterpretScoreDetailed:
    def test_returns_dict_with_required_keys(self):
        result = interpret_score_detailed(75)
        assert 'level' in result
        assert 'label' in result
        assert 'label_en' in result
        assert 'color' in result
        assert 'description' in result

    def test_fi_labels(self):
        assert interpret_score_detailed(85)['label'] == 'Erinomainen'
        assert interpret_score_detailed(65)['label'] == 'Hyvä'
        assert interpret_score_detailed(45)['label'] == 'Keskitaso'
        assert interpret_score_detailed(25)['label'] == 'Heikko'
        assert interpret_score_detailed(5)['label'] == 'Kriittinen'


# =============================================================================
# factor_status
# =============================================================================

class TestFactorStatus:
    def test_excellent(self):
        assert factor_status(70) == 'excellent'
        assert factor_status(100) == 'excellent'

    def test_good(self):
        assert factor_status(50) == 'good'
        assert factor_status(69) == 'good'

    def test_needs_improvement(self):
        assert factor_status(30) == 'needs_improvement'
        assert factor_status(49) == 'needs_improvement'

    def test_poor(self):
        assert factor_status(0) == 'poor'
        assert factor_status(29) == 'poor'

    def test_boundaries(self):
        assert factor_status(70) == 'excellent'
        assert factor_status(69) == 'good'
        assert factor_status(50) == 'good'
        assert factor_status(49) == 'needs_improvement'
        assert factor_status(30) == 'needs_improvement'
        assert factor_status(29) == 'poor'


# =============================================================================
# score_to_risk_level
# =============================================================================

class TestScoreToRiskLevel:
    def test_low_risk(self):
        assert score_to_risk_level(60) == 'low'
        assert score_to_risk_level(100) == 'low'

    def test_medium_risk(self):
        assert score_to_risk_level(40) == 'medium'
        assert score_to_risk_level(59) == 'medium'

    def test_high_risk(self):
        assert score_to_risk_level(0) == 'high'
        assert score_to_risk_level(39) == 'high'


# =============================================================================
# calculate_roi_score
# =============================================================================

class TestCalculateRoiScore:
    def test_best_roi(self):
        """Critical impact + low effort = best ROI"""
        score = calculate_roi_score('critical', 'low')
        assert score == 90  # 100 * 90 / 100

    def test_worst_roi(self):
        """Low impact + high effort = worst ROI"""
        score = calculate_roi_score('low', 'high')
        assert score == 5  # 25 * 20 / 100

    def test_medium_medium(self):
        score = calculate_roi_score('medium', 'medium')
        assert score == 25  # 50 * 50 / 100

    def test_unknown_defaults_to_medium(self):
        score = calculate_roi_score('unknown', 'unknown')
        assert score == 25  # medium * medium


# =============================================================================
# classify_financial_risk
# =============================================================================

class TestClassifyFinancialRisk:
    def test_critical_risk(self):
        # > 10% of 500k = > 50k
        assert classify_financial_risk(60_000) == 'critical'

    def test_high_risk(self):
        # > 5% of 500k = > 25k
        assert classify_financial_risk(30_000) == 'high'

    def test_medium_risk(self):
        # > 2% of 500k = > 10k
        assert classify_financial_risk(15_000) == 'medium'

    def test_low_risk(self):
        # < 2% of 500k = < 10k
        assert classify_financial_risk(5_000) == 'low'

    def test_custom_revenue(self):
        # 60k risk on 1M revenue = 6% = high
        assert classify_financial_risk(60_000, 1_000_000) == 'high'
        # 60k risk on 100k revenue = 60% = critical
        assert classify_financial_risk(60_000, 100_000) == 'critical'


# =============================================================================
# get_positioning_tier
# =============================================================================

class TestGetPositioningTier:
    def test_tiers(self):
        assert get_positioning_tier(75) == 'Digital Leader'
        assert get_positioning_tier(60) == 'Strong Performer'
        assert get_positioning_tier(45) == 'Developing'
        assert get_positioning_tier(30) == 'Below Average'
        assert get_positioning_tier(0) == 'Below Average'

    def test_boundaries(self):
        assert get_positioning_tier(75) == 'Digital Leader'
        assert get_positioning_tier(74) == 'Strong Performer'
        assert get_positioning_tier(60) == 'Strong Performer'
        assert get_positioning_tier(59) == 'Developing'
        assert get_positioning_tier(45) == 'Developing'
        assert get_positioning_tier(44) == 'Below Average'


# =============================================================================
# get_competitive_position
# =============================================================================

class TestGetCompetitivePosition:
    def test_leader(self):
        assert get_competitive_position(80, 60) == 'Digital Leader'   # diff = +20

    def test_strong(self):
        assert get_competitive_position(70, 60) == 'Strong Performer'  # diff = +10

    def test_competitive(self):
        assert get_competitive_position(60, 60) == 'Competitive'  # diff = 0

    def test_challenged(self):
        assert get_competitive_position(55, 60) == 'Challenged'  # diff = -5

    def test_urgent(self):
        assert get_competitive_position(40, 60) == 'Urgent Action Required'  # diff = -20

    def test_boundaries(self):
        assert get_competitive_position(75, 60) == 'Digital Leader'   # +15
        assert get_competitive_position(74, 60) == 'Strong Performer'  # +14
        assert get_competitive_position(65, 60) == 'Strong Performer'  # +5
        assert get_competitive_position(64, 60) == 'Competitive'      # +4
        assert get_competitive_position(60, 60) == 'Competitive'      # 0
        assert get_competitive_position(50, 60) == 'Challenged'       # -10
        assert get_competitive_position(49, 60) == 'Urgent Action Required'  # -11


# =============================================================================
# classify_tech_modernity
# =============================================================================

class TestClassifyTechModernity:
    def test_tiers(self):
        assert classify_tech_modernity(90) == 'cutting_edge'
        assert classify_tech_modernity(70) == 'modern'
        assert classify_tech_modernity(50) == 'standard'
        assert classify_tech_modernity(25) == 'basic'
        assert classify_tech_modernity(10) == 'legacy'

    def test_boundaries(self):
        assert classify_tech_modernity(85) == 'cutting_edge'
        assert classify_tech_modernity(84) == 'modern'
        assert classify_tech_modernity(65) == 'modern'
        assert classify_tech_modernity(64) == 'standard'
        assert classify_tech_modernity(40) == 'standard'
        assert classify_tech_modernity(39) == 'basic'
        assert classify_tech_modernity(20) == 'basic'
        assert classify_tech_modernity(19) == 'legacy'


# =============================================================================
# Weight consistency checks
# =============================================================================

class TestWeightConsistency:
    def test_chatgpt_weights_sum_to_1(self):
        total = sum(CHATGPT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"ChatGPT weights sum to {total}, expected 1.0"

    def test_perplexity_weights_sum_to_1(self):
        total = sum(PERPLEXITY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Perplexity weights sum to {total}, expected 1.0"

    def test_strategic_weights_sum_to_1(self):
        total = sum(STRATEGIC_CATEGORY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Strategic weights sum to {total}, expected 1.0"

    def test_chatgpt_and_perplexity_same_factors(self):
        """Both weight sets must cover the same 6 factors"""
        assert set(CHATGPT_WEIGHTS.keys()) == set(PERPLEXITY_WEIGHTS.keys())

    def test_all_weights_positive(self):
        for name, weights in [('ChatGPT', CHATGPT_WEIGHTS), ('Perplexity', PERPLEXITY_WEIGHTS)]:
            for factor, weight in weights.items():
                assert weight > 0, f"{name} weight for '{factor}' is {weight}, must be positive"
