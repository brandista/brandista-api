# -*- coding: utf-8 -*-
"""Unit tests for hallucination_guard.py — anti-hallucination system."""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestDataProvenance:
    """Test data provenance tracking."""

    def _get_tracker(self):
        from agents.hallucination_guard import ProvenanceTracker, DataSource
        return ProvenanceTracker(), DataSource

    def test_track_basic_claim(self):
        tracker, DS = self._get_tracker()
        record = tracker.track(
            claim='seo_score', value=42,
            source=DS.SCORE_CALCULATION,
        )
        assert record.claim == 'seo_score'
        assert record.value == 42
        assert record.source == DS.SCORE_CALCULATION
        assert record.confidence.value == 'calculated'

    def test_track_score_shortcut(self):
        tracker, DS = self._get_tracker()
        record = tracker.track_score('content', 75)
        assert record.claim == 'content_score'
        assert record.value == 75
        assert record.source == DS.SCORE_CALCULATION

    def test_track_estimate_with_range(self):
        tracker, DS = self._get_tracker()
        record = tracker.track_estimate(
            claim='monthly_risk', value=800,
            methodology='gap × organic_share / 12',
            best_case=400, worst_case=1200,
        )
        assert record.value == 800
        assert record.confidence.value == 'estimated'
        assert len(record.caveats) == 2  # fi + en range

    def test_sources_summary(self):
        tracker, DS = self._get_tracker()
        tracker.track('a', 1, DS.HTML_ANALYSIS)
        tracker.track('b', 2, DS.WHOIS)
        tracker.track('c', 3, DS.HTML_ANALYSIS)  # duplicate source

        sources = tracker.get_sources_summary()
        assert 'html_analysis' in sources
        assert 'whois' in sources
        assert len(sources) == 2  # deduplicated

    def test_confidence_weakest_link(self):
        tracker, DS = self._get_tracker()
        tracker.track('a', 1, DS.HTML_ANALYSIS)      # verified
        tracker.track('b', 2, DS.SCORE_CALCULATION)   # calculated
        tracker.track('c', 3, DS.LLM_GENERATED)       # speculative

        # Overall should be speculative (weakest)
        assert tracker.get_confidence_level() == 'speculative'

    def test_confidence_all_verified(self):
        tracker, DS = self._get_tracker()
        tracker.track('a', 1, DS.HTML_ANALYSIS)
        tracker.track('b', 2, DS.WHOIS)
        tracker.track('c', 3, DS.USER_INPUT)

        assert tracker.get_confidence_level() == 'verified'

    def test_to_dict(self):
        tracker, DS = self._get_tracker()
        tracker.track('test', 42, DS.HTML_ANALYSIS)

        d = tracker.to_dict()
        assert 'records' in d
        assert 'sources_used' in d
        assert 'overall_confidence' in d
        assert len(d['records']) == 1

    def test_empty_tracker(self):
        tracker, DS = self._get_tracker()
        assert tracker.get_confidence_level() == 'speculative'
        assert tracker.get_sources_summary() == []


class TestPromptGuardrails:
    """Test prompt anti-hallucination guardrails."""

    def _get_fns(self):
        from agents.hallucination_guard import add_guardrails, build_grounded_prompt
        return add_guardrails, build_grounded_prompt

    def test_add_guardrails_fi(self):
        add_guardrails, _ = self._get_fns()
        result = add_guardrails("Test prompt", 'fi')
        assert 'ÄLÄ keksi' in result
        assert 'KÄYTÄ VAIN' in result
        assert 'Test prompt' in result

    def test_add_guardrails_en(self):
        add_guardrails, _ = self._get_fns()
        result = add_guardrails("Test prompt", 'en')
        assert 'DO NOT invent' in result
        assert 'Use ONLY' in result

    def test_build_grounded_prompt_replaces_vars(self):
        _, build_grounded_prompt = self._get_fns()
        template = "Kilpailija: {name}, pisteet: {score}"
        facts = {'name': 'Das Auto', 'score': 72}
        result = build_grounded_prompt(template, facts, 'fi')

        assert 'Das Auto' in result
        assert '72' in result

    def test_build_grounded_prompt_missing_vars(self):
        _, build_grounded_prompt = self._get_fns()
        template = "Kilpailija: {name}, liikevaihto: {revenue}"
        facts = {'name': 'Das Auto'}  # revenue missing
        result = build_grounded_prompt(template, facts, 'fi')

        assert 'Das Auto' in result
        assert 'tieto ei saatavilla' in result

    def test_build_grounded_prompt_none_values(self):
        _, build_grounded_prompt = self._get_fns()
        template = "Data: {value}"
        facts = {'value': None}
        result = build_grounded_prompt(template, facts, 'fi')

        assert 'tieto ei saatavilla' in result


class TestOutputValidator:
    """Test post-generation LLM output validation."""

    def _get_validator(self, facts=None):
        from agents.hallucination_guard import OutputValidator
        default_facts = {
            'competitor_name': 'Das Auto',
            'your_score': 55,
            'comp_score': 72,
            'monthly_risk': 800,
            'annual_risk': 9600,
        }
        return OutputValidator(facts or default_facts)

    def test_valid_output_passes(self):
        v = self._get_validator()
        result = v.validate(
            "Das Auto on edellä sinua. Toimimattomuuden hinta on arviolta €800/kk."
        )
        assert result.is_valid is True
        assert len(result.issues) == 0

    def test_unknown_company_flagged(self):
        v = self._get_validator()
        result = v.validate(
            "Kilpailija SuperCorp Oy on markkinajohtaja."
        )
        # Should flag unknown company name
        assert len(result.issues) > 0 or len(result.warnings) > 0

    def test_grounded_numbers_pass(self):
        v = self._get_validator()
        result = v.validate(
            "Vuosittainen menetys: arviolta €9,600."
        )
        # 9600 = monthly_risk * 12, should be grounded
        assert result.is_valid is True

    def test_small_scores_pass(self):
        """Scores 0-100 should always pass since they're common."""
        v = self._get_validator()
        result = v.validate(
            "Pisteesi on 55/100 ja kilpailijan 72/100."
        )
        assert result.is_valid is True

    def test_sanitized_output_has_disclaimer(self):
        v = self._get_validator()
        result = v.validate(
            "Kilpailija Kuvitteellinen Yritys ohittaa sinut."
        )
        if not result.is_valid:
            assert '⚠️' in result.sanitized_output


class TestTransparencyMarkers:
    """Test estimate wrapping and transparency."""

    def test_wrap_estimate(self):
        from agents.hallucination_guard import wrap_estimate
        result = wrap_estimate(
            value=800,
            best_case=400,
            worst_case=1200,
            methodology_fi='Testi',
            methodology_en='Test',
            sources=['html_analysis'],
        )
        assert result['value'] == 800
        assert result['best_case'] == 400
        assert result['worst_case'] == 1200
        assert result['is_estimate'] is True
        assert result['confidence'] == 'estimated'

    def test_wrap_verified(self):
        from agents.hallucination_guard import wrap_verified
        result = wrap_verified(42, 'html_analysis')
        assert result['value'] == 42
        assert result['is_estimate'] is False
        assert result['confidence'] == 'verified'


class TestIntelligenceGuard:
    """Test the high-level IntelligenceGuard wrapper."""

    def _get_guard(self):
        from agents.hallucination_guard import IntelligenceGuard
        return IntelligenceGuard(language='fi')

    def test_add_prompt_guardrails(self):
        guard = self._get_guard()
        result = guard.add_prompt_guardrails("Test")
        assert 'KÄYTÄ VAIN' in result

    def test_validate_llm_output(self):
        guard = self._get_guard()
        facts = {'competitor_name': 'TestCo', 'monthly_risk': 500}
        result = guard.validate_llm_output(
            "TestCo on kilpailija. Arviolta €500/kk.",
            facts
        )
        assert result.is_valid is True

    def test_wrap_financial_estimate_inaction(self):
        guard = self._get_guard()
        result = guard.wrap_financial_estimate(
            value=800,
            estimate_type='inaction_cost'
        )
        assert result['value'] == 800
        assert result['is_estimate'] is True
        assert len(result['caveats_fi']) > 0  # Has standard caveats

    def test_wrap_financial_estimate_roi(self):
        guard = self._get_guard()
        result = guard.wrap_financial_estimate(
            value=2400,
            estimate_type='roi_estimate'
        )
        assert result['value'] == 2400
        assert 'ROI' in result['caveats_fi'][0] or 'konversio' in result['caveats_fi'][0]

    def test_create_envelope(self):
        guard = self._get_guard()
        guard.provenance.track_score('seo', 42)

        envelope = guard.create_envelope(
            content={'test': True},
            methodology_fi='Testimetodi',
            methodology_en='Test method',
        )
        assert envelope.confidence in ('verified', 'calculated', 'estimated', 'speculative')
        assert len(envelope.data_sources) > 0
        assert envelope.methodology_fi == 'Testimetodi'

    def test_data_quality_summary(self):
        guard = self._get_guard()
        guard.provenance.track_score('seo', 42)
        guard.provenance.track_score('content', 65)
        guard.provenance.track('rev', 500000, guard.provenance.records[0].source)

        summary = guard.get_data_quality_summary()
        assert 'quality_score' in summary
        assert summary['total_data_points'] == 3
        assert summary['quality_score'] > 0

    def test_data_quality_empty(self):
        guard = self._get_guard()
        summary = guard.get_data_quality_summary()
        assert summary['overall_confidence'] == 'no_data'

    def test_confidence_downgrade_on_validation_fail(self):
        guard = self._get_guard()
        guard.provenance.track_score('seo', 42)  # calculated confidence

        # Simulate validation failure
        guard.validate_llm_output(
            "Kilpailija Olematon Firma Oy ohittaa sinut.",
            {'competitor_name': 'Das Auto'}
        )

        envelope = guard.create_envelope(
            content={},
            methodology_fi='Test',
            methodology_en='Test',
        )
        # If validation found issues, confidence should be downgraded
        if guard._validation_results and not guard._validation_results[-1].is_valid:
            assert envelope.confidence == 'speculative'
