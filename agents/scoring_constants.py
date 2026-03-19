"""
Shared scoring constants for Growth Engine agents.

All threshold values, score interpretations, and impact/effort mappings
are centralized here to ensure consistency across all agents.
"""

# =============================================================================
# SCORE INTERPRETATION THRESHOLDS
# Used by analyst, strategist, guardian, and prospector agents
# =============================================================================

SCORE_THRESHOLDS = {
    'excellent': 80,    # >= 80
    'good': 60,         # >= 60
    'average': 40,      # >= 40
    'poor': 20,         # >= 20
    # Below 20 = critical
}

def interpret_score(score: int) -> str:
    """Consistent score interpretation across all agents.
    Returns: 'excellent' | 'good' | 'average' | 'poor' | 'critical'
    """
    if score >= SCORE_THRESHOLDS['excellent']:
        return 'excellent'
    elif score >= SCORE_THRESHOLDS['good']:
        return 'good'
    elif score >= SCORE_THRESHOLDS['average']:
        return 'average'
    elif score >= SCORE_THRESHOLDS['poor']:
        return 'poor'
    else:
        return 'critical'

def interpret_score_detailed(score: int) -> dict:
    """Returns interpretation with label, color, and description."""
    level = interpret_score(score)
    return {
        'excellent': {
            'level': 'excellent', 'label': 'Erinomainen', 'label_en': 'Excellent',
            'color': '#22c55e', 'description': 'Top performance, competitive advantage'
        },
        'good': {
            'level': 'good', 'label': 'Hyvä', 'label_en': 'Good',
            'color': '#3b82f6', 'description': 'Above average, room for optimization'
        },
        'average': {
            'level': 'average', 'label': 'Keskitaso', 'label_en': 'Average',
            'color': '#f59e0b', 'description': 'Average performance, improvement needed'
        },
        'poor': {
            'level': 'poor', 'label': 'Heikko', 'label_en': 'Poor',
            'color': '#ef4444', 'description': 'Below average, significant gaps'
        },
        'critical': {
            'level': 'critical', 'label': 'Kriittinen', 'label_en': 'Critical',
            'color': '#991b1b', 'description': 'Critical issues requiring immediate attention'
        },
    }[level]


# =============================================================================
# RISK LEVEL THRESHOLDS
# =============================================================================

RISK_THRESHOLDS = {
    'low': 60,      # score >= 60 = low risk
    'medium': 40,   # score >= 40 = medium risk
    # Below 40 = high risk
}

def score_to_risk_level(score: int) -> str:
    """Convert a score (0-100) to risk level. Lower score = higher risk."""
    if score >= RISK_THRESHOLDS['low']:
        return 'low'
    elif score >= RISK_THRESHOLDS['medium']:
        return 'medium'
    else:
        return 'high'


# =============================================================================
# IMPACT / EFFORT SCORING
# Standardized across all agents
# =============================================================================

IMPACT_SCORES = {
    'critical': 100,
    'high': 75,
    'medium': 50,
    'low': 25,
}

# Inverted: low effort = high score (easier = better ROI)
EFFORT_SCORES = {
    'low': 90,
    'medium': 50,
    'high': 20,
}

def calculate_roi_score(impact: str, effort: str) -> int:
    """Calculate ROI score from impact and effort levels.
    Returns 0-100 where higher = better ROI.
    """
    impact_val = IMPACT_SCORES.get(impact, IMPACT_SCORES['medium'])
    effort_val = EFFORT_SCORES.get(effort, EFFORT_SCORES['medium'])
    return int((impact_val * effort_val) / 100)


# =============================================================================
# COMPETITIVE COMPARISON THRESHOLDS
# =============================================================================

# Minimum point difference to classify as "ahead" or "behind"
COMPETITIVE_DIFF_THRESHOLD = 10

# Minimum score for a competitor to be classified as "relevant"
COMPETITOR_RELEVANCE_THRESHOLD = 65

# High-threat competitor threshold
COMPETITOR_HIGH_THREAT_THRESHOLD = 80

# Market gap detection: competitor average below this = weak area
MARKET_GAP_THRESHOLD = 45


# =============================================================================
# REVENUE & FINANCIAL DEFAULTS
# =============================================================================

# Default annual revenue when not provided (EU SME median)
DEFAULT_ANNUAL_REVENUE_EUR = 500_000

# Risk thresholds as PERCENTAGE of revenue (not fixed EUR amounts)
RISK_REVENUE_THRESHOLDS = {
    'critical': 0.10,    # > 10% of annual revenue at risk
    'high': 0.05,        # > 5% of annual revenue at risk
    'medium': 0.02,      # > 2% of annual revenue at risk
    # Below 2% = low risk
}

# Maximum annual risk cap (percentage of revenue)
MAX_RISK_PERCENT = 0.25  # 25% cap

def classify_financial_risk(annual_risk_eur: float, annual_revenue_eur: float = None) -> str:
    """Classify financial risk using percentage of revenue, not fixed amounts."""
    revenue = annual_revenue_eur or DEFAULT_ANNUAL_REVENUE_EUR
    risk_pct = annual_risk_eur / max(1, revenue)

    if risk_pct > RISK_REVENUE_THRESHOLDS['critical']:
        return 'critical'
    elif risk_pct > RISK_REVENUE_THRESHOLDS['high']:
        return 'high'
    elif risk_pct > RISK_REVENUE_THRESHOLDS['medium']:
        return 'medium'
    else:
        return 'low'


# =============================================================================
# CONTENT QUALITY THRESHOLDS
# =============================================================================

# Word count thresholds for content depth scoring
CONTENT_WORD_COUNT = {
    'comprehensive': 2500,   # 2500+ words = comprehensive
    'good': 1500,            # 1500+ = good depth
    'moderate': 800,         # 800+ = moderate
    # Below 800 = thin content
}

# Mobile score threshold (on 0-15 scale used in score_breakdown)
MOBILE_SCORE_OK_THRESHOLD = 9  # 60% of 15

# Meta description optimal length range
META_DESC_OPTIMAL_MIN = 120
META_DESC_OPTIMAL_MAX = 160


# =============================================================================
# AI VISIBILITY FACTOR WEIGHTS
# Used in analyze_ai_search_visibility() in main.py
# =============================================================================

CHATGPT_WEIGHTS = {
    'content_depth': 0.25,
    'structured_data': 0.20,
    'conversational_format': 0.20,
    'ai_accessibility': 0.15,
    'semantic_structure': 0.10,
    'authority_signals': 0.10,
}

PERPLEXITY_WEIGHTS = {
    'authority_signals': 0.25,
    'ai_accessibility': 0.20,
    'content_depth': 0.20,
    'structured_data': 0.15,
    'semantic_structure': 0.10,
    'conversational_format': 0.10,
}


# =============================================================================
# STRATEGIC SCORING WEIGHTS
# Used in strategist_agent.py composite score calculation
# =============================================================================

STRATEGIC_CATEGORY_WEIGHTS = {
    'seo': 0.10,
    'performance': 0.10,
    'security': 0.10,          # Technical security audit score (from analyst/category comparison)
    'content': 0.20,
    'ux': 0.15,
    'ai_visibility': 0.15,
    'security_posture': 0.10,  # RASM risk-assessment score (from guardian_agent, rasm_score)
    'competitive_edge': 0.10,
}
assert abs(sum(STRATEGIC_CATEGORY_WEIGHTS.values()) - 1.0) < 0.001, \
    f"STRATEGIC_CATEGORY_WEIGHTS must sum to 1.0, got {sum(STRATEGIC_CATEGORY_WEIGHTS.values())}"

# Strategic defense/growth mode thresholds
STRATEGIC_DEFENSE_THRESHOLD = 50   # Below 50 = defense mode (1.5x weight)
STRATEGIC_GROWTH_THRESHOLD = 60    # Above 60 = growth mode (1.5x weight)


# =============================================================================
# FACTOR-LEVEL STATUS THRESHOLDS
# Used in individual analysis factor scoring (schema, semantic, content, etc.)
# =============================================================================

FACTOR_STATUS_THRESHOLDS = {
    'excellent': 70,    # >= 70
    'good': 50,         # >= 50
    'needs_improvement': 30,  # >= 30
    # Below 30 = poor
}

def factor_status(score: int) -> str:
    """Classify a single factor score into status level.
    Returns: 'excellent' | 'good' | 'needs_improvement' | 'poor'
    """
    if score >= FACTOR_STATUS_THRESHOLDS['excellent']:
        return 'excellent'
    elif score >= FACTOR_STATUS_THRESHOLDS['good']:
        return 'good'
    elif score >= FACTOR_STATUS_THRESHOLDS['needs_improvement']:
        return 'needs_improvement'
    else:
        return 'poor'


# =============================================================================
# INDUSTRY BENCHMARKS
# =============================================================================

INDUSTRY_AVERAGE_SCORE = 45      # Baseline industry average for positioning
INDUSTRY_TOP_QUARTILE = 70       # Top 25% of industry
INDUSTRY_BOTTOM_QUARTILE = 30    # Bottom 25% of industry

# Positioning tiers based on overall score
POSITIONING_TIERS = [
    (75, 'Digital Leader'),
    (60, 'Strong Performer'),
    (45, 'Developing'),
    (0,  'Below Average'),
]

def get_positioning_tier(score: int) -> str:
    """Return positioning tier label based on overall score."""
    for threshold, label in POSITIONING_TIERS:
        if score >= threshold:
            return label
    return 'Below Average'

# Relative competitive positioning (SWOT) — difference vs competitor average
COMPETITIVE_POSITION_TIERS = [
    (15, 'Digital Leader'),
    (5,  'Strong Performer'),
    (0,  'Competitive'),
    (-10, 'Challenged'),
]
COMPETITIVE_POSITION_DEFAULT = 'Urgent Action Required'

def get_competitive_position(your_score: int, avg_competitor_score: float) -> str:
    """Return competitive position label based on gap vs competitor average."""
    diff = your_score - avg_competitor_score
    for threshold, label in COMPETITIVE_POSITION_TIERS:
        if diff >= threshold:
            return label
    return COMPETITIVE_POSITION_DEFAULT


# Technology modernity classification
TECH_MODERNITY_TIERS = [
    (85, 'cutting_edge'),
    (65, 'modern'),
    (40, 'standard'),
    (20, 'basic'),
    (0,  'legacy'),
]

def classify_tech_modernity(score: int) -> str:
    """Classify technology stack modernity level."""
    for threshold, label in TECH_MODERNITY_TIERS:
        if score >= threshold:
            return label
    return 'legacy'
