# -*- coding: utf-8 -*-
"""
Gustav 2.0 — Threat History & Predictive Analytics

Stores analysis snapshots, computes deltas between analyses,
detects recurring threats, and predicts trend directions.

This module works WITHOUT a database — snapshots are stored in-memory
for single session and can be persisted via the API layer to PostgreSQL later.

Anti-hallucination: all predictions include confidence + methodology + caveats.
"""

import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from .hallucination_guard import (
    IntelligenceGuard,
    DataSource,
    ConfidenceLevel,
    STANDARD_CAVEATS_FI,
    STANDARD_CAVEATS_EN,
)
from .scoring_constants import SCORE_THRESHOLDS

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ThreatSnapshot:
    """A point-in-time snapshot of analysis state."""
    url: str
    user_id: str
    run_id: str
    overall_score: int
    rasm_score: int
    category_scores: Dict[str, int]  # {seo: 45, content: 30, ...}
    threats: List[Dict] = field(default_factory=list)
    competitor_scores: List[Dict] = field(default_factory=list)
    revenue_at_risk: int = 0
    battlecard_count: int = 0
    correlation_count: int = 0
    created_at: str = ''

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_guardian_result(cls, url: str, user_id: str, run_id: str,
                            guardian_result: Dict) -> 'ThreatSnapshot':
        """Create snapshot from guardian agent's execute() result."""
        threats = guardian_result.get('threats', [])

        # Extract category scores from threats or risk register
        cat_scores = {}
        for threat in threats:
            cat = threat.get('category', '')
            if cat and 'score' in threat:
                cat_scores[cat] = threat['score']

        # Extract from competitive intelligence if available
        ci = guardian_result.get('competitive_intelligence', {})
        inaction = ci.get('inaction_cost', {})
        revenue_at_risk = 0
        if isinstance(inaction.get('total_annual_loss'), dict):
            revenue_at_risk = inaction['total_annual_loss'].get('value', 0)
        elif isinstance(inaction.get('total_annual_loss'), (int, float)):
            revenue_at_risk = int(inaction['total_annual_loss'])

        # Competitor scores
        comp_scores = []
        cta = guardian_result.get('competitor_threat_assessment', {})
        for a in cta.get('assessments', []):
            comp_scores.append({
                'url': a.get('url', ''),
                'name': a.get('name', ''),
                'score': a.get('digital_score', 0),
                'threat_level': a.get('threat_level', 'unknown'),
            })

        return cls(
            url=url,
            user_id=user_id,
            run_id=run_id,
            overall_score=guardian_result.get('rasm_score', 0),
            rasm_score=guardian_result.get('rasm_score', 0),
            category_scores=cat_scores,
            threats=[{
                'category': t.get('category'),
                'severity': t.get('severity'),
                'title': t.get('title', ''),
            } for t in threats],
            competitor_scores=comp_scores,
            revenue_at_risk=revenue_at_risk,
            battlecard_count=len(ci.get('battlecards', [])),
            correlation_count=len(ci.get('correlated_intelligence', [])),
        )


@dataclass
class ThreatDelta:
    """Change between two analysis snapshots."""
    new_threats: List[Dict] = field(default_factory=list)
    escalated_threats: List[Dict] = field(default_factory=list)
    mitigated_threats: List[Dict] = field(default_factory=list)
    resolved_threats: List[Dict] = field(default_factory=list)
    recurring_threats: List[Dict] = field(default_factory=list)
    stable_threats: List[Dict] = field(default_factory=list)

    score_changes: Dict[str, Any] = field(default_factory=dict)
    rasm_delta: int = 0
    previous_snapshot_date: str = ''
    days_between_analyses: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)

    @property
    def total_changes(self) -> int:
        return (len(self.new_threats) + len(self.escalated_threats) +
                len(self.resolved_threats) + len(self.mitigated_threats))

    @property
    def is_improving(self) -> bool:
        return (len(self.resolved_threats) + len(self.mitigated_threats) >
                len(self.new_threats) + len(self.escalated_threats))


@dataclass
class TrendPrediction:
    """Predicted trend based on historical data."""
    category: str           # 'overall' or category name
    direction: str          # 'improving' | 'stable' | 'declining'
    rate_per_analysis: float  # Points change per analysis
    current_score: int
    threshold_target: int   # Nearest important threshold
    analyses_to_threshold: int  # How many analyses until threshold
    weeks_to_threshold: int

    contributing_factors: List[Dict] = field(default_factory=list)
    prediction_fi: str = ''
    prediction_en: str = ''
    confidence: float = 0.5
    data_points_used: int = 0

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# THREAT HISTORY MANAGER
# =============================================================================

class ThreatHistoryManager:
    """
    Manages threat analysis history for trend detection and delta computation.

    In-memory storage for now — can be backed by PostgreSQL via API layer.
    Anti-hallucination: all predictions include confidence, methodology, and caveats.
    """

    def __init__(self):
        # In-memory storage: url → list of snapshots (newest first)
        self._snapshots: Dict[str, List[ThreatSnapshot]] = {}
        self.guard = IntelligenceGuard(language='fi')

    def save_snapshot(self, snapshot: ThreatSnapshot) -> str:
        """Save a snapshot. Returns the snapshot date."""
        url = snapshot.url
        if url not in self._snapshots:
            self._snapshots[url] = []

        self._snapshots[url].insert(0, snapshot)  # Newest first

        # Track provenance
        self.guard.provenance.track(
            claim=f'snapshot_{snapshot.run_id}',
            value=snapshot.overall_score,
            source=DataSource.SCORE_CALCULATION,
            raw_evidence=f'Snapshot from {snapshot.created_at}',
        )

        logger.info(
            f"[ThreatHistory] Saved snapshot for {url}: "
            f"score={snapshot.overall_score}, threats={len(snapshot.threats)}, "
            f"total_snapshots={len(self._snapshots[url])}"
        )
        return snapshot.created_at

    def get_snapshots(self, url: str, limit: int = 10) -> List[ThreatSnapshot]:
        """Get recent snapshots for a URL."""
        return self._snapshots.get(url, [])[:limit]

    def get_snapshot_count(self, url: str) -> int:
        """Get number of snapshots for a URL."""
        return len(self._snapshots.get(url, []))

    # =========================================================================
    # DELTA COMPUTATION
    # =========================================================================

    def compute_delta(
        self,
        url: str,
        current_snapshot: ThreatSnapshot,
    ) -> Optional[ThreatDelta]:
        """
        Compare current snapshot to the previous one.

        Returns None if there's no previous snapshot to compare to.

        Categorizes each threat change:
        - NEW: First time seen
        - ESCALATED: Severity increased
        - MITIGATED: Severity decreased
        - RESOLVED: Was present before, now gone
        - RECURRING: Present 3+ times in a row
        - STABLE: No change
        """
        snapshots = self._snapshots.get(url, [])
        if len(snapshots) < 2:
            return None

        previous = snapshots[1]  # [0] is the current one we just saved

        delta = ThreatDelta()

        # --- Threat comparison ---
        prev_threats_by_cat = {}
        for t in previous.threats:
            cat = t.get('category', 'unknown')
            prev_threats_by_cat[cat] = t

        curr_threats_by_cat = {}
        for t in current_snapshot.threats:
            cat = t.get('category', 'unknown')
            curr_threats_by_cat[cat] = t

        severity_order = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}

        for cat, curr_t in curr_threats_by_cat.items():
            if cat not in prev_threats_by_cat:
                # NEW threat
                delta.new_threats.append({
                    'threat': curr_t,
                    'explanation_fi': f'Uusi uhka: {curr_t.get("title", cat)} havaittu ensimmäistä kertaa.',
                    'explanation_en': f'New threat: {curr_t.get("title", cat)} detected for the first time.',
                })
            else:
                prev_t = prev_threats_by_cat[cat]
                curr_sev = severity_order.get(curr_t.get('severity', 'low'), 1)
                prev_sev = severity_order.get(prev_t.get('severity', 'low'), 1)

                if curr_sev > prev_sev:
                    delta.escalated_threats.append({
                        'threat': curr_t,
                        'previous_severity': prev_t.get('severity'),
                        'current_severity': curr_t.get('severity'),
                        'explanation_fi': (
                            f'Eskaloitui: {curr_t.get("title", cat)} '
                            f'({prev_t.get("severity")} → {curr_t.get("severity")})'
                        ),
                        'explanation_en': (
                            f'Escalated: {curr_t.get("title", cat)} '
                            f'({prev_t.get("severity")} → {curr_t.get("severity")})'
                        ),
                    })
                elif curr_sev < prev_sev:
                    delta.mitigated_threats.append({
                        'threat': curr_t,
                        'previous_severity': prev_t.get('severity'),
                        'current_severity': curr_t.get('severity'),
                        'explanation_fi': (
                            f'Lieventynyt: {curr_t.get("title", cat)} '
                            f'({prev_t.get("severity")} → {curr_t.get("severity")})'
                        ),
                        'explanation_en': (
                            f'Mitigated: {curr_t.get("title", cat)} '
                            f'({prev_t.get("severity")} → {curr_t.get("severity")})'
                        ),
                    })
                else:
                    delta.stable_threats.append({'threat': curr_t})

        # RESOLVED: was in previous but not in current
        for cat, prev_t in prev_threats_by_cat.items():
            if cat not in curr_threats_by_cat:
                delta.resolved_threats.append({
                    'threat': prev_t,
                    'explanation_fi': f'Ratkaistu: {prev_t.get("title", cat)} ei enää havaittu.',
                    'explanation_en': f'Resolved: {prev_t.get("title", cat)} no longer detected.',
                })

        # RECURRING: check if same category threat exists in 3+ consecutive snapshots
        for cat, curr_t in curr_threats_by_cat.items():
            occurrences = 0
            for snap in snapshots:
                if any(t.get('category') == cat for t in snap.threats):
                    occurrences += 1
                else:
                    break
            if occurrences >= 3:
                delta.recurring_threats.append({
                    'threat': curr_t,
                    'occurrences': occurrences,
                    'explanation_fi': (
                        f'Toistuva: {curr_t.get("title", cat)} havaittu '
                        f'{occurrences} peräkkäisessä analyysissa eikä sitä ole korjattu.'
                    ),
                    'explanation_en': (
                        f'Recurring: {curr_t.get("title", cat)} detected in '
                        f'{occurrences} consecutive analyses and not fixed.'
                    ),
                })

        # --- Score changes ---
        delta.rasm_delta = current_snapshot.rasm_score - previous.rasm_score
        delta.score_changes = {
            'overall': {
                'prev': previous.overall_score,
                'curr': current_snapshot.overall_score,
                'delta': current_snapshot.overall_score - previous.overall_score,
            },
            'by_category': {},
        }

        all_cats = set(list(previous.category_scores.keys()) +
                       list(current_snapshot.category_scores.keys()))
        for cat in all_cats:
            prev_val = previous.category_scores.get(cat, 0)
            curr_val = current_snapshot.category_scores.get(cat, 0)
            d = curr_val - prev_val
            delta.score_changes['by_category'][cat] = {
                'prev': prev_val,
                'curr': curr_val,
                'delta': d,
                'direction': 'improving' if d > 0 else ('declining' if d < 0 else 'stable'),
            }

        delta.previous_snapshot_date = previous.created_at

        # Calculate days between analyses
        try:
            curr_dt = datetime.fromisoformat(current_snapshot.created_at)
            prev_dt = datetime.fromisoformat(previous.created_at)
            delta.days_between_analyses = (curr_dt - prev_dt).days
        except (ValueError, TypeError):
            delta.days_between_analyses = 0

        return delta

    # =========================================================================
    # TREND PREDICTION
    # =========================================================================

    def predict_trend(
        self,
        url: str,
        category: str = 'overall',
        analysis_interval_days: int = 14,
    ) -> Optional[TrendPrediction]:
        """
        Predict trend direction using linear regression from history.

        Requires at least 3 data points for any prediction.
        Anti-hallucination: confidence based on data points, caveats included.

        Returns None if insufficient data.
        """
        snapshots = self._snapshots.get(url, [])
        if len(snapshots) < 3:
            return None

        # Extract scores for this category
        scores = []
        for snap in reversed(snapshots):  # Oldest first for regression
            if category == 'overall':
                scores.append(snap.overall_score)
            else:
                scores.append(snap.category_scores.get(category, 0))

        if len(scores) < 3:
            return None

        # Simple linear regression: y = mx + b
        n = len(scores)
        x_vals = list(range(n))
        x_mean = sum(x_vals) / n
        y_mean = sum(scores) / n

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, scores))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)

        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator

        current_score = scores[-1]

        # Determine direction
        if abs(slope) < 1.0:
            direction = 'stable'
        elif slope > 0:
            direction = 'improving'
        else:
            direction = 'declining'

        # Find nearest threshold
        threshold_target = self._find_nearest_threshold(current_score, direction)

        # Calculate time to threshold
        if abs(slope) > 0.1 and threshold_target != current_score:
            analyses_to_threshold = max(1, abs(
                int((threshold_target - current_score) / slope)
            ))
        else:
            analyses_to_threshold = 99  # Effectively "not applicable"

        weeks_to_threshold = analyses_to_threshold * (analysis_interval_days / 7)

        # Confidence based on data points
        if n >= 7:
            confidence = 0.90
        elif n >= 5:
            confidence = 0.80
        else:
            confidence = 0.60  # 3-4 data points

        # Rate per week
        rate_per_week = slope * (7 / analysis_interval_days)

        # Build prediction text
        prediction_fi = self._build_prediction_fi(
            category, direction, slope, current_score,
            threshold_target, analyses_to_threshold, weeks_to_threshold, n
        )
        prediction_en = self._build_prediction_en(
            category, direction, slope, current_score,
            threshold_target, analyses_to_threshold, weeks_to_threshold, n
        )

        # Track provenance
        self.guard.provenance.track_estimate(
            claim=f'trend_{category}',
            value=slope,
            methodology=f'Linear regression from {n} data points (scores: {scores})',
        )

        return TrendPrediction(
            category=category,
            direction=direction,
            rate_per_analysis=round(slope, 1),
            current_score=current_score,
            threshold_target=threshold_target,
            analyses_to_threshold=analyses_to_threshold,
            weeks_to_threshold=int(weeks_to_threshold),
            prediction_fi=prediction_fi,
            prediction_en=prediction_en,
            confidence=confidence,
            data_points_used=n,
        )

    def _find_nearest_threshold(self, score: int, direction: str) -> int:
        """Find the nearest scoring threshold in the direction of movement."""
        thresholds = sorted(SCORE_THRESHOLDS.values())  # [20, 40, 60, 80]

        if direction == 'declining':
            # Find highest threshold below current score
            for t in reversed(thresholds):
                if t < score:
                    return t
            return 0
        elif direction == 'improving':
            # Find lowest threshold above current score
            for t in thresholds:
                if t > score:
                    return t
            return 100
        else:
            # Stable: find nearest
            nearest = min(thresholds, key=lambda t: abs(t - score))
            return nearest

    def _build_prediction_fi(
        self, category, direction, slope, current, threshold,
        analyses_to, weeks_to, data_points
    ) -> str:
        cat_name = {
            'overall': 'Kokonaispisteesi',
            'seo': 'SEO-pisteesi',
            'content': 'Sisältöpisteesi',
            'performance': 'Suorituskykypisteesi',
            'security': 'Turvallisuuspisteesi',
            'ai_visibility': 'AI-näkyvyyspisteesi',
        }.get(category, f'{category}-pisteesi')

        if direction == 'declining':
            return (
                f'{cat_name} on laskenut keskimäärin {abs(slope):.1f}p per analyysi '
                f'viimeisen {data_points} analyysin aikana (nyt {current}/100). '
                f'Nykyisellä vauhdilla saavutat kriittisen rajan ({threshold}p) '
                f'arviolta {analyses_to} analyysin ({weeks_to} viikon) kuluttua. '
                f'(Ennuste perustuu {data_points} datapisteeseen, luotettavuus: '
                f'{"korkea" if data_points >= 5 else "kohtalainen"}.)'
            )
        elif direction == 'improving':
            return (
                f'{cat_name} on noussut keskimäärin {slope:.1f}p per analyysi '
                f'viimeisen {data_points} analyysin aikana (nyt {current}/100). '
                f'Nykyisellä vauhdilla saavutat seuraavan tason ({threshold}p) '
                f'arviolta {analyses_to} analyysin ({weeks_to} viikon) kuluttua.'
            )
        else:
            return (
                f'{cat_name} on pysynyt vakaana ({current}/100) '
                f'viimeisen {data_points} analyysin aikana.'
            )

    def _build_prediction_en(
        self, category, direction, slope, current, threshold,
        analyses_to, weeks_to, data_points
    ) -> str:
        if direction == 'declining':
            return (
                f'{category.capitalize()} score has declined by an average of '
                f'{abs(slope):.1f} points per analysis over the last {data_points} analyses '
                f'(currently {current}/100). At this rate, you will reach the critical '
                f'threshold ({threshold}) in approximately {analyses_to} analyses '
                f'({weeks_to} weeks). (Based on {data_points} data points, confidence: '
                f'{"high" if data_points >= 5 else "moderate"}.)'
            )
        elif direction == 'improving':
            return (
                f'{category.capitalize()} score has improved by an average of '
                f'{slope:.1f} points per analysis over the last {data_points} analyses '
                f'(currently {current}/100). At this rate, you will reach the next level '
                f'({threshold}) in approximately {analyses_to} analyses ({weeks_to} weeks).'
            )
        else:
            return (
                f'{category.capitalize()} score has remained stable ({current}/100) '
                f'over the last {data_points} analyses.'
            )

    # =========================================================================
    # RECURRING THREATS
    # =========================================================================

    def get_recurring_threats(
        self, url: str, min_occurrences: int = 3
    ) -> List[Dict]:
        """
        Find threats that appear in consecutive analyses without being fixed.

        Adds cumulative cost estimate for "unpaid bills."
        """
        snapshots = self._snapshots.get(url, [])
        if len(snapshots) < min_occurrences:
            return []

        # Count consecutive occurrences per category
        cat_streaks: Dict[str, int] = {}
        for snap in snapshots:
            current_cats = {t.get('category') for t in snap.threats}
            for cat in current_cats:
                cat_streaks[cat] = cat_streaks.get(cat, 0) + 1
            # Break streaks for categories not in this snapshot
            for cat in list(cat_streaks.keys()):
                if cat not in current_cats:
                    cat_streaks[cat] = 0

        recurring = []
        for cat, streak in cat_streaks.items():
            if streak >= min_occurrences:
                # Find the threat details from latest snapshot
                latest_threat = None
                for t in snapshots[0].threats:
                    if t.get('category') == cat:
                        latest_threat = t
                        break

                recurring.append({
                    'category': cat,
                    'occurrences': streak,
                    'threat': latest_threat,
                    'first_seen_approximate': snapshots[min(streak - 1, len(snapshots) - 1)].created_at,
                    'explanation_fi': (
                        f'Tämä uhka ({cat}) on havaittu {streak} peräkkäisessä analyysissa '
                        f'eikä sitä ole korjattu.'
                    ),
                    'explanation_en': (
                        f'This threat ({cat}) has been detected in {streak} consecutive '
                        f'analyses and has not been fixed.'
                    ),
                })

        return recurring

    # =========================================================================
    # FULL HISTORY ANALYSIS
    # =========================================================================

    def analyze_history(
        self,
        url: str,
        current_snapshot: ThreatSnapshot,
    ) -> Dict[str, Any]:
        """
        Complete history analysis: delta + trend + recurring.
        Main entry point for guardian_agent.py integration.
        """
        # Save the snapshot first
        self.save_snapshot(current_snapshot)

        result = {
            'snapshot_count': self.get_snapshot_count(url),
            'delta': None,
            'trend_overall': None,
            'trends_by_category': {},
            'recurring_threats': [],
            'data_quality': self.guard.get_data_quality_summary(),
        }

        # Delta
        delta = self.compute_delta(url, current_snapshot)
        if delta:
            result['delta'] = delta.to_dict()

        # Overall trend
        trend = self.predict_trend(url, 'overall')
        if trend:
            result['trend_overall'] = trend.to_dict()

        # Category trends
        for cat in current_snapshot.category_scores:
            cat_trend = self.predict_trend(url, cat)
            if cat_trend:
                result['trends_by_category'][cat] = cat_trend.to_dict()

        # Recurring threats
        result['recurring_threats'] = self.get_recurring_threats(url)

        return result

    # =========================================================================
    # SERIALIZATION (for DB persistence via API layer)
    # =========================================================================

    def export_snapshots(self, url: str) -> List[Dict]:
        """Export all snapshots for a URL as dicts (for DB storage)."""
        return [s.to_dict() for s in self._snapshots.get(url, [])]

    def import_snapshots(self, url: str, snapshot_dicts: List[Dict]):
        """Import snapshots from DB (called at startup)."""
        snapshots = []
        for d in snapshot_dicts:
            snapshots.append(ThreatSnapshot(**{
                k: v for k, v in d.items()
                if k in ThreatSnapshot.__dataclass_fields__
            }))
        self._snapshots[url] = snapshots
        logger.info(f"[ThreatHistory] Imported {len(snapshots)} snapshots for {url}")
