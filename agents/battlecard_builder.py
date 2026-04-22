# -*- coding: utf-8 -*-
"""
Battlecard Builder — lightweight adapter to run CompetitiveIntelligenceEngine
without requiring the full agent swarm.

The engine itself (competitive_intelligence.py) is agent-agnostic: it takes raw
analyses and produces battlecards, correlations, and inaction cost. But its
inputs (benchmark, category_comparison, competitor_assessments) are normally
built by AnalystAgent and GuardianAgent during a full /api/analyze run.

This module extracts just enough logic to build those inputs from raw target +
competitor analyses, so battlecards can be generated from lightweight flows
like /api/competitor-discovery.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agents.battlecard_builder")


_CATEGORIES = ['seo', 'performance', 'security', 'content', 'ux', 'ai_visibility']

_CATEGORY_MAP = {
    'seo': 'seo_basics',
    'security': 'security',
    'content': 'content',
    'performance': 'performance',
    'ux': 'mobile',
    'ai_visibility': 'ai_visibility',
}


def _extract_category_score(analysis: Dict[str, Any], category: str) -> int:
    """Extract a single category score (0-100) from an analysis dict."""
    basic = analysis.get('basic_analysis', analysis.get('basic', {}))
    breakdown = basic.get('score_breakdown', {})
    key = _CATEGORY_MAP.get(category, category)

    if category == 'ai_visibility':
        enhanced = analysis.get('enhanced_features', {}) or {}
        ai_vis = enhanced.get('ai_search_visibility') or analysis.get('detailed_analysis', {}).get('ai_search_visibility', {})
        if isinstance(ai_vis, dict):
            return int(ai_vis.get('overall_ai_search_score', 0))
        return 0

    raw = breakdown.get(key, 0)
    max_values = {
        'security': 15, 'seo_basics': 20, 'content': 20,
        'performance': 5, 'mobile': 15, 'social': 10, 'technical': 15,
    }
    if key in max_values and max_values[key] > 0:
        return int((raw / max_values[key]) * 100)
    return int(raw)


def _build_benchmark(target_analysis: Dict, competitor_analyses: List[Dict]) -> Dict[str, Any]:
    your_score = target_analysis.get('final_score') or \
                 target_analysis.get('basic_analysis', {}).get('digital_maturity_score', 0)

    if not competitor_analyses:
        return {
            'your_score': your_score,
            'avg_competitor_score': 0,
            'max_competitor_score': 0,
            'min_competitor_score': 0,
            'your_position': 1,
            'total_analyzed': 1,
        }

    comp_scores = [
        c.get('final_score') or c.get('basic_analysis', {}).get('digital_maturity_score', 0)
        for c in competitor_analyses
    ]
    all_scores = sorted([your_score] + comp_scores, reverse=True)

    return {
        'your_score': your_score,
        'avg_competitor_score': round(sum(comp_scores) / len(comp_scores)),
        'max_competitor_score': max(comp_scores),
        'min_competitor_score': min(comp_scores),
        'your_position': all_scores.index(your_score) + 1,
        'total_analyzed': len(all_scores),
    }


def _build_category_comparison(target_analysis: Dict, competitor_analyses: List[Dict]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for cat in _CATEGORIES:
        your = _extract_category_score(target_analysis, cat)
        if competitor_analyses:
            comp_scores = [_extract_category_score(c, cat) for c in competitor_analyses]
            avg = sum(comp_scores) / len(comp_scores) if comp_scores else 0
        else:
            avg = 0
        diff = your - avg
        out[cat] = {
            'your_score': your,
            'competitor_avg': round(avg),
            'difference': round(diff),
            'status': 'ahead' if diff > 5 else 'behind' if diff < -5 else 'even',
        }
    return out


def _threat_level_from_gap(score_diff: int) -> str:
    """score_diff = their_score - your_score. Positive = they're ahead."""
    if score_diff >= 10:
        return 'high'
    if score_diff >= 0:
        return 'medium'
    return 'low'


def _build_competitor_assessments(
    competitor_analyses: List[Dict],
    your_score: int,
    competitors_enriched: Optional[List[Dict]] = None,
) -> List[Dict[str, Any]]:
    """
    Produce assessments list compatible with CompetitiveIntelligenceEngine.

    Minimum required fields per assessment: url, name, digital_score, threat_level,
    signals, company_intel. Missing fields default to empty/honest values — follows
    the 3 honesty rules (empty > guess).
    """
    lookup: Dict[str, Dict] = {}
    if competitors_enriched:
        for e in competitors_enriched:
            if e.get('url'):
                lookup[e['url']] = e
            if e.get('domain'):
                lookup[e['domain']] = e

    out: List[Dict[str, Any]] = []
    for comp in competitor_analyses:
        url = comp.get('url', '')
        domain = comp.get('domain', '')
        enriched = lookup.get(url) or lookup.get(domain) or {}

        digital_score = comp.get('final_score') or \
                        comp.get('basic_analysis', {}).get('digital_maturity_score', 0)
        score_diff = digital_score - your_score
        name = (enriched.get('company_name')
                or enriched.get('name')
                or comp.get('name')
                or domain
                or url)

        revenue = enriched.get('revenue')
        employees = enriched.get('employees')
        has_registry = bool(revenue or employees)

        out.append({
            'url': url,
            'name': name,
            'digital_score': digital_score,
            'score_diff': score_diff,
            'threat_level': _threat_level_from_gap(score_diff),
            'signals': {
                'digital_score': digital_score,
                'score_diff': score_diff,
                'has_real_data': has_registry,
            },
            'company_intel': {
                'revenue': revenue,
                'employees': employees,
                'source': 'registry' if has_registry else 'estimated',
            },
        })

    threat_order = {'high': 0, 'medium': 1, 'low': 2}
    out.sort(key=lambda a: (threat_order.get(a['threat_level'], 2), -a['digital_score']))
    return out


async def build_competitive_intelligence(
    target_analysis: Dict[str, Any],
    competitor_analyses: List[Dict[str, Any]],
    competitors_enriched: Optional[List[Dict[str, Any]]] = None,
    industry: str = 'general',
    language: str = 'fi',
    annual_revenue: int = 500000,
) -> Dict[str, Any]:
    """
    Generate competitive intelligence (battlecards, correlations, inaction cost)
    from raw target + competitor full analyses, without a full agent swarm.

    Returns the dict produced by CompetitiveIntelligenceEngine.generate_full_intelligence(),
    or a minimal error dict if the engine fails.
    """
    if not competitor_analyses:
        return {
            'battlecards': [],
            'correlated_intelligence': [],
            'inaction_cost': {},
            'data_quality': {'quality_score': 0, 'reason': 'ei kilpailija-analyyseja'},
        }

    try:
        from .competitive_intelligence import CompetitiveIntelligenceEngine
    except ImportError as e:
        logger.error(f"[battlecard_builder] CompetitiveIntelligenceEngine import failed: {e}")
        return {
            'battlecards': [],
            'correlated_intelligence': [],
            'inaction_cost': {},
            'error': f'engine_unavailable: {e}',
        }

    benchmark = _build_benchmark(target_analysis, competitor_analyses)
    category_comparison = _build_category_comparison(target_analysis, competitor_analyses)
    assessments = _build_competitor_assessments(
        competitor_analyses,
        your_score=benchmark['your_score'],
        competitors_enriched=competitors_enriched,
    )

    try:
        engine = CompetitiveIntelligenceEngine(
            your_analysis=target_analysis,
            competitor_analyses=competitor_analyses,
            competitor_assessments=assessments,
            category_comparison=category_comparison,
            benchmark=benchmark,
            annual_revenue=annual_revenue,
            industry=industry,
            language=language,
        )
        result = engine.generate_full_intelligence()
        bc_count = len(result.get('battlecards', []))
        logger.info(f"[battlecard_builder] Generated {bc_count} battlecards for {len(competitor_analyses)} competitors")
        return result
    except Exception as e:
        logger.error(f"[battlecard_builder] Engine failed: {e}", exc_info=True)
        return {
            'battlecards': [],
            'correlated_intelligence': [],
            'inaction_cost': {},
            'error': str(e),
        }
