# -*- coding: utf-8 -*-
"""Unit tests for guardian_pulse.py — Gustav 2.0 lightweight monitoring."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestContentHashTracker:
    def _get_tracker(self):
        from agents.guardian_pulse import ContentHashTracker
        return ContentHashTracker()

    def test_compute_hashes(self):
        tracker = self._get_tracker()
        hashes = tracker.compute_hashes('https://dasauto.fi', {
            'title': 'Das Auto - BMW Huolto',
            'meta_description': 'BMW huolto Helsinki',
            'word_count': 1500,
            'schema_types': ['LocalBusiness', 'AutoRepair'],
            'page_count': 15,
        })
        assert 'title' in hashes
        assert 'meta_description' in hashes
        assert 'content_bucket' in hashes
        assert hashes['content_bucket'] == '3'  # 1500 // 500 = 3
        assert hashes['page_count'] == '15'

    def test_no_changes_on_first_check(self):
        tracker = self._get_tracker()
        hashes = tracker.compute_hashes('https://dasauto.fi', {
            'title': 'Das Auto',
            'word_count': 1500,
        })
        changes = tracker.detect_changes('https://dasauto.fi', hashes, 'Das Auto')
        assert len(changes) == 0  # First check, no previous to compare

    def test_detect_title_change(self):
        tracker = self._get_tracker()
        # First check
        h1 = tracker.compute_hashes('https://dasauto.fi', {'title': 'Das Auto v1', 'word_count': 1500})
        tracker.detect_changes('https://dasauto.fi', h1, 'Das Auto')

        # Second check with different title
        h2 = tracker.compute_hashes('https://dasauto.fi', {'title': 'Das Auto v2', 'word_count': 1500})
        changes = tracker.detect_changes('https://dasauto.fi', h2, 'Das Auto')

        assert len(changes) >= 1
        title_changes = [c for c in changes if c.change_type == 'meta_change']
        assert len(title_changes) == 1

    def test_detect_content_expansion(self):
        tracker = self._get_tracker()
        h1 = tracker.compute_hashes('https://dasauto.fi', {'word_count': 500, 'title': 'T'})
        tracker.detect_changes('https://dasauto.fi', h1, 'Das Auto')

        h2 = tracker.compute_hashes('https://dasauto.fi', {'word_count': 2500, 'title': 'T'})
        changes = tracker.detect_changes('https://dasauto.fi', h2, 'Das Auto')

        content_changes = [c for c in changes if c.change_type == 'content_expansion']
        assert len(content_changes) == 1

    def test_detect_new_pages(self):
        tracker = self._get_tracker()
        h1 = tracker.compute_hashes('https://dasauto.fi', {'page_count': 15, 'title': 'T'})
        tracker.detect_changes('https://dasauto.fi', h1, 'Das Auto')

        h2 = tracker.compute_hashes('https://dasauto.fi', {'page_count': 20, 'title': 'T'})
        changes = tracker.detect_changes('https://dasauto.fi', h2, 'Das Auto')

        page_changes = [c for c in changes if c.change_type == 'new_pages']
        assert len(page_changes) == 1
        assert 'Das Auto' in page_changes[0].details_fi
        assert '5' in page_changes[0].details_fi  # 20 - 15 = 5

    def test_detect_schema_change(self):
        tracker = self._get_tracker()
        h1 = tracker.compute_hashes('https://dasauto.fi', {
            'schema_types': ['LocalBusiness'], 'title': 'T', 'word_count': 500
        })
        tracker.detect_changes('https://dasauto.fi', h1, 'Das Auto')

        h2 = tracker.compute_hashes('https://dasauto.fi', {
            'schema_types': ['LocalBusiness', 'AutoRepair', 'FAQPage'], 'title': 'T', 'word_count': 500
        })
        changes = tracker.detect_changes('https://dasauto.fi', h2, 'Das Auto')

        schema_changes = [c for c in changes if c.change_type == 'schema_upgrade']
        assert len(schema_changes) == 1

    def test_no_changes_when_same(self):
        tracker = self._get_tracker()
        data = {'title': 'Das Auto', 'word_count': 1500, 'page_count': 15}
        h1 = tracker.compute_hashes('https://dasauto.fi', data)
        tracker.detect_changes('https://dasauto.fi', h1, 'Das Auto')

        h2 = tracker.compute_hashes('https://dasauto.fi', data)
        changes = tracker.detect_changes('https://dasauto.fi', h2, 'Das Auto')
        assert len(changes) == 0


class TestGuardianPulse:
    def _get_pulse(self):
        from agents.guardian_pulse import GuardianPulse
        return GuardianPulse()

    def test_healthy_site(self):
        pulse = self._get_pulse()
        result = pulse.run_pulse_check(
            url='https://bemufix.fi',
            your_status={'status_code': 200, 'response_time_ms': 450, 'ssl_valid': True},
        )
        assert result.status == 'ok'
        assert len(result.alerts) == 0

    def test_site_down_alert(self):
        pulse = self._get_pulse()
        result = pulse.run_pulse_check(
            url='https://bemufix.fi',
            your_status={'status_code': 500, 'response_time_ms': 0},
        )
        assert result.status == 'critical'
        assert any(a['type'] == 'site_down' for a in result.alerts)

    def test_slow_site_alert(self):
        pulse = self._get_pulse()
        result = pulse.run_pulse_check(
            url='https://bemufix.fi',
            your_status={'status_code': 200, 'response_time_ms': 5000, 'ssl_valid': True},
        )
        assert result.status == 'warning'
        assert any(a['type'] == 'slow_response' for a in result.alerts)

    def test_ssl_issue_alert(self):
        pulse = self._get_pulse()
        result = pulse.run_pulse_check(
            url='https://bemufix.fi',
            your_status={'status_code': 200, 'response_time_ms': 450, 'ssl_valid': False},
        )
        assert result.status == 'critical'
        assert any(a['type'] == 'ssl_issue' for a in result.alerts)

    def test_competitor_change_detection(self):
        pulse = self._get_pulse()
        pulse.register_monitoring(
            url='https://bemufix.fi',
            competitor_urls=['https://dasauto.fi'],
            competitor_names={'https://dasauto.fi': 'Das Auto'},
        )

        # First pulse — establishes baseline
        result1 = pulse.run_pulse_check(
            url='https://bemufix.fi',
            your_status={'status_code': 200, 'response_time_ms': 450, 'ssl_valid': True},
            competitor_data=[{
                'url': 'https://dasauto.fi',
                'page_data': {'title': 'Das Auto v1', 'word_count': 1000, 'page_count': 10},
            }],
        )
        assert result1.changes_detected == 0

        # Second pulse — detect changes
        result2 = pulse.run_pulse_check(
            url='https://bemufix.fi',
            your_status={'status_code': 200, 'response_time_ms': 450, 'ssl_valid': True},
            competitor_data=[{
                'url': 'https://dasauto.fi',
                'page_data': {'title': 'Das Auto v2 BMW', 'word_count': 3000, 'page_count': 18},
            }],
        )
        assert result2.changes_detected > 0

    def test_pulse_check_to_dict(self):
        pulse = self._get_pulse()
        result = pulse.run_pulse_check(
            url='https://bemufix.fi',
            your_status={'status_code': 200, 'response_time_ms': 450},
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert 'status' in d
        assert 'checks_performed' in d

    def test_alert_prompt_has_guardrails(self):
        from agents.guardian_pulse import GuardianPulse, CompetitorChange
        pulse = GuardianPulse()

        change = CompetitorChange(
            competitor_url='https://dasauto.fi',
            competitor_name='Das Auto',
            change_type='new_pages',
            severity='high',
            business_impact='competitive_move',
            details_fi='Das Auto lisäsi 5 uutta sivua',
            details_en='Das Auto added 5 new pages',
        )

        prompt = pulse.build_alert_prompt(change, your_score=55, comp_score=72)
        assert 'KÄYTÄ VAIN' in prompt
        assert 'ÄLÄ keksi' in prompt
        assert 'Das Auto' in prompt
