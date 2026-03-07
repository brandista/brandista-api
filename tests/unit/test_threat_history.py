# -*- coding: utf-8 -*-
"""Unit tests for threat_history.py — Gustav 2.0 threat history & predictions."""

import pytest
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def _make_snapshot(score, rasm=None, threats=None, cats=None, created_at=None, run_id=None):
    from agents.threat_history import ThreatSnapshot
    return ThreatSnapshot(
        url='https://bemufix.fi',
        user_id='test_user',
        run_id=run_id or f'run_{score}',
        overall_score=score,
        rasm_score=rasm or score,
        category_scores=cats or {'seo': score - 10, 'content': score - 20},
        threats=threats or [
            {'category': 'seo', 'severity': 'medium', 'title': 'SEO issues'},
        ],
        created_at=created_at or datetime.now().isoformat(),
    )


def _make_manager():
    from agents.threat_history import ThreatHistoryManager
    return ThreatHistoryManager()


class TestSnapshotStorage:
    def test_save_snapshot(self):
        mgr = _make_manager()
        snap = _make_snapshot(55)
        date = mgr.save_snapshot(snap)
        assert date is not None
        assert mgr.get_snapshot_count('https://bemufix.fi') == 1

    def test_multiple_snapshots(self):
        mgr = _make_manager()
        mgr.save_snapshot(_make_snapshot(55, run_id='r1'))
        mgr.save_snapshot(_make_snapshot(58, run_id='r2'))
        mgr.save_snapshot(_make_snapshot(52, run_id='r3'))
        assert mgr.get_snapshot_count('https://bemufix.fi') == 3

    def test_newest_first(self):
        mgr = _make_manager()
        mgr.save_snapshot(_make_snapshot(55, run_id='r1'))
        mgr.save_snapshot(_make_snapshot(60, run_id='r2'))
        snaps = mgr.get_snapshots('https://bemufix.fi')
        assert snaps[0].overall_score == 60  # Newest first

    def test_from_guardian_result(self):
        from agents.threat_history import ThreatSnapshot
        result = {
            'rasm_score': 55,
            'threats': [
                {'category': 'seo', 'severity': 'high', 'title': 'SEO critical'},
            ],
            'competitor_threat_assessment': {'assessments': []},
            'competitive_intelligence': {'inaction_cost': {}},
        }
        snap = ThreatSnapshot.from_guardian_result(
            'https://bemufix.fi', 'user1', 'run_1', result
        )
        assert snap.rasm_score == 55
        assert len(snap.threats) == 1


class TestDeltaComputation:
    def test_no_delta_on_first_snapshot(self):
        mgr = _make_manager()
        snap = _make_snapshot(55)
        mgr.save_snapshot(snap)
        delta = mgr.compute_delta('https://bemufix.fi', snap)
        assert delta is None

    def test_delta_detects_new_threats(self):
        mgr = _make_manager()
        snap1 = _make_snapshot(55, threats=[
            {'category': 'seo', 'severity': 'medium', 'title': 'SEO issues'},
        ])
        mgr.save_snapshot(snap1)

        snap2 = _make_snapshot(52, threats=[
            {'category': 'seo', 'severity': 'medium', 'title': 'SEO issues'},
            {'category': 'content', 'severity': 'high', 'title': 'Content gap'},
        ])
        mgr.save_snapshot(snap2)

        delta = mgr.compute_delta('https://bemufix.fi', snap2)
        assert delta is not None
        assert len(delta.new_threats) == 1
        assert delta.new_threats[0]['threat']['category'] == 'content'

    def test_delta_detects_resolved_threats(self):
        mgr = _make_manager()
        snap1 = _make_snapshot(55, threats=[
            {'category': 'seo', 'severity': 'high', 'title': 'SEO'},
            {'category': 'security', 'severity': 'medium', 'title': 'SSL'},
        ])
        mgr.save_snapshot(snap1)

        snap2 = _make_snapshot(60, threats=[
            {'category': 'seo', 'severity': 'medium', 'title': 'SEO'},
        ])
        mgr.save_snapshot(snap2)

        delta = mgr.compute_delta('https://bemufix.fi', snap2)
        assert len(delta.resolved_threats) == 1
        assert delta.resolved_threats[0]['threat']['category'] == 'security'

    def test_delta_detects_escalated_threats(self):
        mgr = _make_manager()
        snap1 = _make_snapshot(55, threats=[
            {'category': 'seo', 'severity': 'medium', 'title': 'SEO'},
        ])
        mgr.save_snapshot(snap1)

        snap2 = _make_snapshot(50, threats=[
            {'category': 'seo', 'severity': 'critical', 'title': 'SEO'},
        ])
        mgr.save_snapshot(snap2)

        delta = mgr.compute_delta('https://bemufix.fi', snap2)
        assert len(delta.escalated_threats) == 1
        assert delta.escalated_threats[0]['previous_severity'] == 'medium'
        assert delta.escalated_threats[0]['current_severity'] == 'critical'

    def test_delta_detects_mitigated_threats(self):
        mgr = _make_manager()
        snap1 = _make_snapshot(55, threats=[
            {'category': 'seo', 'severity': 'high', 'title': 'SEO'},
        ])
        mgr.save_snapshot(snap1)

        snap2 = _make_snapshot(60, threats=[
            {'category': 'seo', 'severity': 'low', 'title': 'SEO'},
        ])
        mgr.save_snapshot(snap2)

        delta = mgr.compute_delta('https://bemufix.fi', snap2)
        assert len(delta.mitigated_threats) == 1

    def test_delta_score_changes(self):
        mgr = _make_manager()
        snap1 = _make_snapshot(55, cats={'seo': 42, 'content': 30})
        mgr.save_snapshot(snap1)

        snap2 = _make_snapshot(52, cats={'seo': 38, 'content': 30})
        mgr.save_snapshot(snap2)

        delta = mgr.compute_delta('https://bemufix.fi', snap2)
        assert delta.score_changes['overall']['delta'] == -3
        assert delta.score_changes['by_category']['seo']['delta'] == -4
        assert delta.score_changes['by_category']['content']['delta'] == 0

    def test_is_improving(self):
        mgr = _make_manager()
        snap1 = _make_snapshot(55, threats=[
            {'category': 'seo', 'severity': 'high', 'title': 'SEO'},
            {'category': 'content', 'severity': 'medium', 'title': 'Content'},
        ])
        mgr.save_snapshot(snap1)

        snap2 = _make_snapshot(60, threats=[])
        mgr.save_snapshot(snap2)

        delta = mgr.compute_delta('https://bemufix.fi', snap2)
        assert delta.is_improving is True


class TestTrendPrediction:
    def _fill_history(self, mgr, scores):
        for i, score in enumerate(scores):
            snap = _make_snapshot(
                score,
                cats={'seo': score - 10, 'content': score - 20},
                run_id=f'run_{i}',
                created_at=(datetime.now() - timedelta(days=(len(scores) - i) * 14)).isoformat(),
            )
            mgr.save_snapshot(snap)

    def test_no_prediction_with_few_points(self):
        mgr = _make_manager()
        mgr.save_snapshot(_make_snapshot(55, run_id='r1'))
        mgr.save_snapshot(_make_snapshot(52, run_id='r2'))
        trend = mgr.predict_trend('https://bemufix.fi')
        assert trend is None

    def test_declining_trend(self):
        mgr = _make_manager()
        self._fill_history(mgr, [60, 55, 50, 45])  # Declining

        trend = mgr.predict_trend('https://bemufix.fi')
        assert trend is not None
        assert trend.direction == 'declining'
        assert trend.rate_per_analysis < 0

    def test_improving_trend(self):
        mgr = _make_manager()
        self._fill_history(mgr, [40, 45, 50, 55])  # Improving

        trend = mgr.predict_trend('https://bemufix.fi')
        assert trend.direction == 'improving'
        assert trend.rate_per_analysis > 0

    def test_stable_trend(self):
        mgr = _make_manager()
        self._fill_history(mgr, [55, 55, 56, 55])  # Stable

        trend = mgr.predict_trend('https://bemufix.fi')
        assert trend.direction == 'stable'

    def test_confidence_with_many_points(self):
        mgr = _make_manager()
        self._fill_history(mgr, [60, 55, 50, 45, 40, 35, 30])

        trend = mgr.predict_trend('https://bemufix.fi')
        assert trend.confidence >= 0.90

    def test_confidence_with_few_points(self):
        mgr = _make_manager()
        self._fill_history(mgr, [55, 50, 45])

        trend = mgr.predict_trend('https://bemufix.fi')
        assert trend.confidence < 0.80

    def test_prediction_text_exists(self):
        mgr = _make_manager()
        self._fill_history(mgr, [60, 55, 50, 45])

        trend = mgr.predict_trend('https://bemufix.fi')
        assert trend.prediction_fi != ''
        assert trend.prediction_en != ''
        assert 'lasku' in trend.prediction_fi.lower() or 'lasken' in trend.prediction_fi.lower()

    def test_category_trend(self):
        mgr = _make_manager()
        self._fill_history(mgr, [60, 55, 50, 45])

        trend = mgr.predict_trend('https://bemufix.fi', category='seo')
        assert trend is not None
        assert trend.category == 'seo'


class TestRecurringThreats:
    def test_detects_recurring(self):
        mgr = _make_manager()
        threats = [{'category': 'seo', 'severity': 'medium', 'title': 'SEO'}]
        for i in range(4):
            mgr.save_snapshot(_make_snapshot(55, threats=threats, run_id=f'r{i}'))

        recurring = mgr.get_recurring_threats('https://bemufix.fi', min_occurrences=3)
        assert len(recurring) >= 1
        assert recurring[0]['category'] == 'seo'
        assert recurring[0]['occurrences'] >= 3

    def test_no_recurring_with_too_few(self):
        mgr = _make_manager()
        for i in range(2):
            mgr.save_snapshot(_make_snapshot(55, run_id=f'r{i}'))

        recurring = mgr.get_recurring_threats('https://bemufix.fi', min_occurrences=3)
        assert len(recurring) == 0


class TestFullHistoryAnalysis:
    def test_analyze_history_structure(self):
        mgr = _make_manager()
        # Add 3 snapshots for trend prediction
        for i, score in enumerate([60, 55, 50]):
            mgr.save_snapshot(_make_snapshot(score, run_id=f'r{i}'))

        current = _make_snapshot(45, run_id='r_current')
        result = mgr.analyze_history('https://bemufix.fi', current)

        assert 'snapshot_count' in result
        assert 'delta' in result
        assert 'trend_overall' in result
        assert 'recurring_threats' in result
        assert 'data_quality' in result
        assert result['snapshot_count'] == 4  # 3 previous + current

    def test_export_import_snapshots(self):
        mgr = _make_manager()
        mgr.save_snapshot(_make_snapshot(55, run_id='r1'))
        mgr.save_snapshot(_make_snapshot(60, run_id='r2'))

        exported = mgr.export_snapshots('https://bemufix.fi')
        assert len(exported) == 2

        mgr2 = _make_manager()
        mgr2.import_snapshots('https://bemufix.fi', exported)
        assert mgr2.get_snapshot_count('https://bemufix.fi') == 2
