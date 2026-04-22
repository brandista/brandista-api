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


def _battlecard_to_prompt_context(bc: Dict[str, Any], your_score: int, language: str) -> str:
    """Compact, structured text block describing one battlecard for an LLM prompt."""
    you_win = bc.get('you_win', []) or []
    they_win = bc.get('they_win', []) or []
    actions = bc.get('actions', []) or []

    def _dim_line(d: Dict[str, Any]) -> str:
        dim = d.get('dimension') or d.get('name') or ''
        diff = d.get('difference') or d.get('diff') or ''
        return f"- {dim} ({diff})" if diff else f"- {dim}"

    def _action_line(a: Dict[str, Any]) -> str:
        title = a.get('title') or a.get('action') or ''
        roi = a.get('roi') or a.get('roi_score') or ''
        return f"- {title} (ROI: {roi})" if roi else f"- {title}"

    they_win_txt = '\n'.join(_dim_line(d) for d in they_win[:5]) or ('(ei vahvuuksia)' if language == 'fi' else '(no strengths)')
    you_win_txt = '\n'.join(_dim_line(d) for d in you_win[:5]) or ('(ei voittoja)' if language == 'fi' else '(no wins)')
    actions_txt = '\n'.join(_action_line(a) for a in actions[:3]) or ('(ei toimenpiteitä)' if language == 'fi' else '(no actions)')

    timeline = bc.get('inaction_timeline_fi' if language == 'fi' else 'inaction_timeline_en', '')

    if language == 'fi':
        return (
            f"KILPAILIJA: {bc.get('competitor_name', '')}\n"
            f"- URL: {bc.get('competitor_url', '')}\n"
            f"- Pistemäärä: {bc.get('competitor_score', 0)}/100\n"
            f"- Sinun pistemäärä: {your_score}/100\n"
            f"- Uhkataso: {bc.get('threat_level', 'medium')}\n"
            f"- Kuukausiriski: €{bc.get('monthly_risk', 0):,}\n"
            f"- Vuotuinen riski: €{bc.get('annual_risk', 0):,}\n"
            f"- Aikajana: {timeline}\n\n"
            f"KILPAILIJAN VAHVUUDET (voittaa sinut):\n{they_win_txt}\n\n"
            f"SINUN VAHVUUDET (voitat kilpailijan):\n{you_win_txt}\n\n"
            f"SUOSITELLUT TOIMENPITEET:\n{actions_txt}"
        )
    return (
        f"COMPETITOR: {bc.get('competitor_name', '')}\n"
        f"- URL: {bc.get('competitor_url', '')}\n"
        f"- Score: {bc.get('competitor_score', 0)}/100\n"
        f"- Your score: {your_score}/100\n"
        f"- Threat level: {bc.get('threat_level', 'medium')}\n"
        f"- Monthly risk: €{bc.get('monthly_risk', 0):,}\n"
        f"- Annual risk: €{bc.get('annual_risk', 0):,}\n"
        f"- Timeline: {timeline}\n\n"
        f"COMPETITOR STRENGTHS (beats you):\n{they_win_txt}\n\n"
        f"YOUR STRENGTHS (you beat them):\n{you_win_txt}\n\n"
        f"RECOMMENDED ACTIONS:\n{actions_txt}"
    )


async def _generate_executive_summary(
    bc: Dict[str, Any],
    your_score: int,
    language: str,
    safe_llm_call,
) -> Optional[str]:
    """Generate one 3-4 sentence executive summary for a single battlecard."""
    ctx = _battlecard_to_prompt_context(bc, your_score, language)

    if language == 'fi':
        prompt = (
            "Olet executive-tason kilpailuanalyytikko. Kirjoita kohdeyrityksen "
            "toimitusjohtajalle 3-4 lauseen tiivistelmä tästä kilpailijasta.\n\n"
            f"{ctx}\n\n"
            "OHJEET:\n"
            "- Käytä VAIN yllä olevia lukuja. Älä keksi uusia numeroita.\n"
            "- Sävy: selkeä, suora, toimintasuuntautunut. Ei markkinointipuheen kliseitä.\n"
            "- Aloita suurimmasta uhkasta tai mahdollisuudesta.\n"
            "- Mainitse 1 konkreettinen toimenpide.\n\n"
            "Vastaa pelkkänä tekstinä, ei JSON:ia. 3-4 lausetta."
        )
    else:
        prompt = (
            "You are an executive-level competitive analyst. Write a 3-4 sentence "
            "summary of this competitor for the target company's CEO.\n\n"
            f"{ctx}\n\n"
            "INSTRUCTIONS:\n"
            "- Use ONLY the numbers above. Do not invent new numbers.\n"
            "- Tone: clear, direct, action-oriented. No marketing fluff.\n"
            "- Lead with the biggest threat or opportunity.\n"
            "- Mention 1 concrete action.\n\n"
            "Respond as plain text, not JSON. 3-4 sentences."
        )

    known_facts = {
        'competitor_name': bc.get('competitor_name', ''),
        'competitor_score': bc.get('competitor_score', 0),
        'your_score': your_score,
        'threat_level': bc.get('threat_level', ''),
        'monthly_risk': bc.get('monthly_risk', 0),
        'annual_risk': bc.get('annual_risk', 0),
    }

    text = await safe_llm_call(
        prompt,
        language=language,
        known_facts=known_facts,
        max_tokens=300,
        temperature=0.4,
        label=f"exec_summary_{bc.get('competitor_name', 'unknown')[:20]}",
    )
    return text.strip() if text else None


async def _detect_cross_competitor_patterns(
    battlecards: List[Dict[str, Any]],
    your_score: int,
    language: str,
    safe_llm_call,
) -> List[Dict[str, Any]]:
    """One LLM call: find cross-competitor patterns a single-competitor view would miss."""
    if len(battlecards) < 2:
        return []

    summaries = []
    for i, bc in enumerate(battlecards, 1):
        you_win = [d.get('dimension') or d.get('name') or '' for d in (bc.get('you_win') or [])[:3]]
        they_win = [d.get('dimension') or d.get('name') or '' for d in (bc.get('they_win') or [])[:3]]
        summaries.append(
            f"{i}. {bc.get('competitor_name', '')} (score={bc.get('competitor_score', 0)}, "
            f"threat={bc.get('threat_level', '')}, "
            f"beats you in: {', '.join(they_win) or '-'}, "
            f"you beat them in: {', '.join(you_win) or '-'})"
        )
    comp_block = '\n'.join(summaries)

    if language == 'fi':
        prompt = (
            "Olet kilpailutiedustelu-analyytikko. Sinulle on annettu "
            f"{len(battlecards)} kilpailijan tiivistelmät. Tehtäväsi: löydä "
            "KUVIOITA jotka yksittäinen kilpailija-analyysi ei paljasta.\n\n"
            f"KOHDEYRITYKSEN PISTEMÄÄRÄ: {your_score}/100\n\n"
            f"KILPAILIJAT:\n{comp_block}\n\n"
            "ESIMERKKEJÄ HYÖDYLLISISTÄ KUVIOISTA:\n"
            "- Yhteiset vahvuudet: 'Kaikki 4 kilpailijaa voittavat SEO:ssa — systemaattinen takamatka'\n"
            "- Yhteiset heikkoudet: 'Ei yksikään kilpailija tee mobiilia hyvin — markkinarako'\n"
            "- Jakauma: 'Top 2 hallitsevat sisältöä, muut kilpailevat hinnalla'\n\n"
            "VAATIMUKSET JOKA KUVIOLLE:\n"
            "- pattern: Mitä havaitsit (1 lause)\n"
            "- evidence: KONKREETTISET yritysten nimet ja pisteet datasta (älä keksi)\n"
            "- affected_competitors: Lista kilpailijanimistä\n"
            "- strategic_implication: Mitä tämä tarkoittaa kohteelle (1 lause)\n"
            "- confidence: 'extracted' (suoraan datasta) tai 'inferred' (pääteltävissä — selitä miksi)\n\n"
            "VAIN KUVIOT JOTKA DATASSA ON. Ei kuvioita → tyhjä lista. Max 4 kuviota.\n\n"
            "Vastaa JSON-objektina:\n"
            "{\"patterns\": [{\"pattern\": \"...\", \"evidence\": \"...\", "
            "\"affected_competitors\": [\"...\"], \"strategic_implication\": \"...\", "
            "\"confidence\": \"extracted|inferred\"}]}"
        )
    else:
        prompt = (
            "You are a competitive intelligence analyst. You are given summaries of "
            f"{len(battlecards)} competitors. Your task: find PATTERNS a single-competitor "
            "view would miss.\n\n"
            f"TARGET COMPANY SCORE: {your_score}/100\n\n"
            f"COMPETITORS:\n{comp_block}\n\n"
            "EXAMPLES OF USEFUL PATTERNS:\n"
            "- Shared strengths: 'All 4 competitors beat you in SEO — systematic gap'\n"
            "- Shared weaknesses: 'None do mobile well — market opportunity'\n"
            "- Distribution: 'Top 2 dominate content, others compete on price'\n\n"
            "EACH PATTERN MUST HAVE:\n"
            "- pattern: What you observed (1 sentence)\n"
            "- evidence: CONCRETE company names and scores from the data (don't invent)\n"
            "- affected_competitors: List of competitor names\n"
            "- strategic_implication: What this means for the target (1 sentence)\n"
            "- confidence: 'extracted' (directly from data) or 'inferred' (reasoned — explain why)\n\n"
            "ONLY PATTERNS PRESENT IN THE DATA. No patterns → empty list. Max 4 patterns.\n\n"
            "Respond as JSON: {\"patterns\": [{\"pattern\": \"...\", \"evidence\": \"...\", "
            "\"affected_competitors\": [\"...\"], \"strategic_implication\": \"...\", "
            "\"confidence\": \"extracted|inferred\"}]}"
        )

    known_facts: Dict[str, Any] = {'competitor_count': len(battlecards), 'your_score': your_score}
    for bc in battlecards:
        name = bc.get('competitor_name', '')
        if name:
            known_facts[f"competitor_{name}_score"] = bc.get('competitor_score', 0)

    text = await safe_llm_call(
        prompt,
        language=language,
        known_facts=known_facts,
        max_tokens=1200,
        temperature=0.4,
        response_format={"type": "json_object"},
        label='cross_competitor_patterns',
    )

    if not text:
        return []

    import json
    try:
        data = json.loads(text)
        patterns = data.get('patterns', [])
        if not isinstance(patterns, list):
            return []
        validated: List[Dict[str, Any]] = []
        for p in patterns[:4]:
            if not isinstance(p, dict) or not p.get('pattern') or not p.get('evidence'):
                continue
            conf = p.get('confidence', '').lower()
            if conf not in ('extracted', 'inferred'):
                conf = 'inferred'
            validated.append({
                'pattern': str(p.get('pattern', ''))[:300],
                'evidence': str(p.get('evidence', ''))[:500],
                'affected_competitors': [str(c)[:80] for c in (p.get('affected_competitors') or [])][:10],
                'strategic_implication': str(p.get('strategic_implication', ''))[:300],
                'confidence': conf,
            })
        return validated
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning(f"[battlecard_builder] Cross-pattern JSON parse failed: {e}")
        return []


async def enrich_with_ai_insights(
    intelligence: Dict[str, Any],
    language: str = 'fi',
) -> Dict[str, Any]:
    """
    Enrich a competitive_intelligence dict (output of build_competitive_intelligence)
    with AI-generated insights:

    - ai_executive_summary_fi / _en per battlecard (3-4 sentence CEO summary)
    - cross_competitor_insights list at top level (patterns across all competitors)

    Honest fallback (3 rules): if safe_llm_call unavailable or returns None, fields
    stay absent or empty. Never fake data. Never confidence scores.
    """
    # Lazy import to avoid circular dep on main.py
    try:
        from main import safe_llm_call  # type: ignore
    except ImportError:
        logger.info("[battlecard_builder] safe_llm_call unavailable, skipping AI insights")
        return intelligence

    battlecards = intelligence.get('battlecards') or []
    if not battlecards:
        return intelligence

    your_score = (intelligence.get('provenance') or {}).get('your_score') or 0
    # Fallback: read from first battlecard
    if not your_score and battlecards:
        your_score = battlecards[0].get('your_score', 0)

    # 3a — per-battlecard executive summaries (parallel)
    import asyncio as _asyncio
    summary_tasks = [
        _generate_executive_summary(bc, your_score, language, safe_llm_call)
        for bc in battlecards
    ]
    summaries = await _asyncio.gather(*summary_tasks, return_exceptions=True)

    summary_field = 'ai_executive_summary_fi' if language == 'fi' else 'ai_executive_summary_en'
    summaries_added = 0
    for bc, summary in zip(battlecards, summaries):
        if isinstance(summary, Exception):
            logger.warning(f"[battlecard_builder] Summary failed for {bc.get('competitor_name')}: {summary}")
            continue
        if summary:
            bc[summary_field] = summary
            summaries_added += 1

    # 3c — cross-competitor pattern detection (single call)
    try:
        patterns = await _detect_cross_competitor_patterns(
            battlecards, your_score, language, safe_llm_call
        )
        intelligence['cross_competitor_insights'] = patterns
    except Exception as e:
        logger.error(f"[battlecard_builder] Cross-pattern detection failed: {e}")
        intelligence['cross_competitor_insights'] = []

    logger.info(
        f"[battlecard_builder] AI insights: {summaries_added}/{len(battlecards)} summaries, "
        f"{len(intelligence.get('cross_competitor_insights', []))} patterns"
    )
    return intelligence


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
