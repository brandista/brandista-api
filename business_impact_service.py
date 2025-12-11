# -*- coding: utf-8 -*-
"""
Growth Engine 2.0 - Unified Business Impact Service
====================================================
SINGLE SOURCE OF TRUTH for all revenue/business impact calculations.

This module is used by:
1. /api/v1/competitive-radar (main.py)
2. /api/v1/calculate-impact (main.py)
3. /api/v1/analyze (main.py)
4. Guardian Agent (agents/guardian_agent.py)
5. Orchestrator (agents/orchestrator.py)

All endpoints MUST use this module to ensure consistent results.

VERSION: 2024-12-11
AUTHOR: Growth Engine Team
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS - Industry & Revenue Configuration
# =============================================================================

# EU SME Average Revenue (source: Eurostat 2023)
EU_SME_AVERAGE_REVENUE = 450_000

# Revenue impact multipliers based on score improvement potential
# Lower score = higher improvement potential = higher revenue impact
SCORE_IMPACT_MULTIPLIERS = {
    'very_low': {'min': 0, 'max': 30, 'low_mult': 0.05, 'high_mult': 0.09},   # Score 0-30: 5-9% potential
    'low': {'min': 30, 'max': 50, 'low_mult': 0.04, 'high_mult': 0.07},       # Score 30-50: 4-7% potential
    'medium': {'min': 50, 'max': 70, 'low_mult': 0.03, 'high_mult': 0.05},    # Score 50-70: 3-5% potential
    'high': {'min': 70, 'max': 100, 'low_mult': 0.02, 'high_mult': 0.04},     # Score 70-100: 2-4% potential
}

# Lead generation estimates based on SEO + Content scores
LEAD_GENERATION_FACTORS = {
    'low': {'divisor': 40, 'min': 3},      # Low quality: ~3 leads base
    'medium': {'divisor': 30, 'min': 5},   # Medium: ~5 leads base
    'high': {'divisor': 25, 'min': 8},     # High: ~8 leads base
}


# =============================================================================
# ENUMS - Calculation metadata
# =============================================================================

class CalculationBasis(str, Enum):
    """How revenue was determined - affects confidence level"""
    COMPANY_INTEL = "company_intel"  # From Finnish company registry (PRH/YTJ) - HIGHEST priority
    PROVIDED = "provided"            # User gave annual/monthly revenue
    CALCULATED = "calculated"        # Calculated from traffic metrics
    ESTIMATED = "estimated"          # Using EU SME average (450k€) - LOWEST priority
    HYBRID = "hybrid"                # Partial data provided


class ConfidenceLevel(str, Enum):
    """Confidence in the calculation - displayed to user"""
    HIGH = "H"    # Real revenue data (company_intel or provided)
    MEDIUM = "M"  # Calculated or partial data
    LOW = "L"     # Estimate only


# =============================================================================
# RESULT DATA CLASS
# =============================================================================

@dataclass
class UnifiedBusinessImpact:
    """
    Unified business impact result used across ALL endpoints.
    This is the SINGLE data structure that gets converted to different formats.
    
    Compatible with:
    - BusinessImpact (main.py simple model)
    - BusinessImpactDetailed (main.py detailed model)
    - Guardian Agent revenue_impact format
    """
    
    # === Primary revenue uplift values ===
    revenue_uplift_low: int = 0
    revenue_uplift_high: int = 0
    revenue_uplift_expected: int = 0
    
    # === Formatted strings for UI display ===
    revenue_uplift_range: str = ""       # "€5k - €15k/year (€400 - €1.2k/mo)"
    monthly_revenue_range: str = ""      # "€400 - €1.2k"
    
    # === Revenue at Risk (from Guardian/RASM) ===
    revenue_at_risk: int = 0
    revenue_at_risk_percentage: float = 0.0
    
    # === Calculation metadata ===
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    calculation_basis: CalculationBasis = CalculationBasis.ESTIMATED
    annual_revenue_used: int = EU_SME_AVERAGE_REVENUE
    
    # === Improvement analysis ===
    improvement_areas: List[str] = field(default_factory=list)
    metrics_used: Dict[str, Any] = field(default_factory=dict)
    methodology_note: str = ""
    
    # === Lead generation (legacy) ===
    lead_gain_low: int = 0
    lead_gain_high: int = 0
    lead_gain_estimate: str = ""
    
    # === Trust effect (legacy) ===
    customer_trust_effect: str = ""
    
    # === Scenarios for detailed view ===
    potential_scenarios: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            # Primary fields
            'revenue_uplift_range': self.revenue_uplift_range,
            'monthly_revenue_range': self.monthly_revenue_range,
            'revenue_at_risk': self.revenue_at_risk,
            'revenue_at_risk_percentage': self.revenue_at_risk_percentage,
            
            # Numeric values
            'revenue_uplift_low': self.revenue_uplift_low,
            'revenue_uplift_high': self.revenue_uplift_high,
            'revenue_uplift_expected': self.revenue_uplift_expected,
            
            # Metadata
            'confidence': self.confidence.value,
            'calculation_basis': self.calculation_basis.value,
            'annual_revenue_used': self.annual_revenue_used,
            
            # Details
            'improvement_areas': self.improvement_areas,
            'metrics_used': self.metrics_used,
            'methodology_note': self.methodology_note,
            
            # Legacy
            'lead_gain_estimate': self.lead_gain_estimate,
            'customer_trust_effect': self.customer_trust_effect,
            
            # Scenarios
            'potential_scenarios': self.potential_scenarios,
        }
    
    def to_simple_business_impact(self) -> Dict[str, Any]:
        """
        Convert to simple BusinessImpact format (main.py)
        Used by: ai_analysis.business_impact
        """
        return {
            'lead_gain_estimate': self.lead_gain_estimate,
            'revenue_uplift_range': self.revenue_uplift_range,
            'confidence': self.confidence.value,
            'customer_trust_effect': self.customer_trust_effect,
        }
    
    def to_detailed_business_impact(self) -> Dict[str, Any]:
        """
        Convert to BusinessImpactDetailed format (main.py)
        Used by: /api/v1/calculate-impact response
        """
        return {
            'lead_gain_estimate': self.lead_gain_estimate,
            'revenue_uplift_range': self.revenue_uplift_range,
            'monthly_revenue_range': self.monthly_revenue_range,
            'confidence': self.confidence.value,
            'customer_trust_effect': self.customer_trust_effect,
            'calculation_basis': self.calculation_basis.value,
            'metrics_used': self.metrics_used,
            'improvement_areas': self.improvement_areas,
            'potential_scenarios': self.potential_scenarios,
        }
    
    def to_guardian_format(self) -> Dict[str, Any]:
        """
        Convert to Guardian Agent format
        Used by: agents/guardian_agent.py
        """
        return {
            'total_monthly_risk': self.revenue_at_risk // 12 if self.revenue_at_risk else 0,
            'total_annual_risk': self.revenue_at_risk,
            'revenue_uplift_potential': {
                'low': self.revenue_uplift_low,
                'high': self.revenue_uplift_high,
                'expected': self.revenue_uplift_expected,
                'formatted': self.revenue_uplift_range,
            },
            'confidence': {
                'level': self.confidence.value,
                'note': self.methodology_note,
            },
            'calculation_basis': self.calculation_basis.value,
            'annual_revenue_used': self.annual_revenue_used,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _format_currency(amount: int) -> str:
    """Format currency for display: €5,000 → €5k, €1,500,000 → €1.5M"""
    if amount >= 1_000_000:
        return f"€{amount/1_000_000:.1f}M"
    elif amount >= 1000:
        return f"€{amount//1000}k"
    else:
        return f"€{amount:,}"


def _get_score_multipliers(score: int) -> Tuple[float, float]:
    """Get revenue impact multipliers based on digital maturity score"""
    for level, config in SCORE_IMPACT_MULTIPLIERS.items():
        if config['min'] <= score < config['max']:
            return config['low_mult'], config['high_mult']
    # Default for score >= 100
    return 0.02, 0.04


def _calculate_lead_estimates(seo_score: int, content_score: int) -> Tuple[int, int]:
    """Calculate lead generation estimates based on SEO and content scores"""
    combined = seo_score + content_score
    lead_low = max(3, combined // 40)
    lead_high = max(lead_low + 2, combined // 25)
    return lead_low, lead_high


# =============================================================================
# CORE CALCULATION FUNCTION
# =============================================================================

def calculate_unified_business_impact(
    # Required inputs
    digital_maturity_score: int,
    
    # Revenue inputs (priority: company_intel > provided > calculated > estimated)
    company_intel_revenue: Optional[int] = None,
    annual_revenue: Optional[int] = None,
    monthly_revenue: Optional[int] = None,
    monthly_visitors: Optional[int] = None,
    conversion_rate: Optional[float] = None,
    average_order_value: Optional[float] = None,
    
    # Score breakdowns for improvement areas
    seo_score: int = 0,
    mobile_score: int = 0,
    content_score: int = 0,
    ux_score: int = 0,
    security_score: int = 0,
    
    # Risk data (from Guardian/RASM - passed through, not calculated here)
    revenue_at_risk: int = 0,
    
    # Language for methodology notes
    language: str = 'en'
) -> UnifiedBusinessImpact:
    """
    THE unified business impact calculator.
    
    This function MUST be used by all endpoints to ensure consistent results.
    
    Revenue determination priority:
    1. company_intel_revenue (Finnish PRH/YTJ data - most accurate)
    2. annual_revenue (user provided)
    3. monthly_revenue * 12 (user provided)
    4. Calculated from traffic metrics
    5. EU SME average (€450,000)
    
    Args:
        digital_maturity_score: Overall website score (0-100)
        company_intel_revenue: Revenue from Finnish company registry
        annual_revenue: User-provided annual revenue
        monthly_revenue: User-provided monthly revenue
        monthly_visitors: Monthly website visitors
        conversion_rate: Conversion rate percentage (e.g., 2.5 for 2.5%)
        average_order_value: Average order value in euros
        seo_score: SEO subscore (0-100)
        mobile_score: Mobile subscore (0-100)
        content_score: Content subscore (0-100)
        ux_score: UX subscore (0-100)
        security_score: Security subscore (0-100)
        revenue_at_risk: Pre-calculated revenue at risk (from Guardian)
        language: 'en' or 'fi' for methodology notes
    
    Returns:
        UnifiedBusinessImpact with all calculated values
    """
    
    # =========================================================================
    # STEP 1: Determine annual revenue (priority order)
    # =========================================================================
    
    final_annual_revenue = EU_SME_AVERAGE_REVENUE
    calculation_basis = CalculationBasis.ESTIMATED
    metrics_used: Dict[str, Any] = {}
    
    # Priority 1: Company Intel (Finnish registry - HIGHEST confidence)
    if company_intel_revenue and company_intel_revenue > 0:
        final_annual_revenue = company_intel_revenue
        calculation_basis = CalculationBasis.COMPANY_INTEL
        metrics_used['source'] = 'company_intel'
        metrics_used['company_intel_revenue'] = company_intel_revenue
        logger.info(f"[BusinessImpact] Using Company Intel revenue: €{final_annual_revenue:,}")
    
    # Priority 2: User-provided annual revenue
    elif annual_revenue and annual_revenue > 0:
        final_annual_revenue = annual_revenue
        calculation_basis = CalculationBasis.PROVIDED
        metrics_used['source'] = 'user_provided_annual'
        metrics_used['annual_revenue'] = annual_revenue
        logger.info(f"[BusinessImpact] Using provided annual revenue: €{final_annual_revenue:,}")
    
    # Priority 3: User-provided monthly revenue
    elif monthly_revenue and monthly_revenue > 0:
        final_annual_revenue = monthly_revenue * 12
        calculation_basis = CalculationBasis.PROVIDED
        metrics_used['source'] = 'user_provided_monthly'
        metrics_used['monthly_revenue'] = monthly_revenue
        metrics_used['calculated_annual'] = final_annual_revenue
        logger.info(f"[BusinessImpact] Calculated from monthly: €{final_annual_revenue:,}")
    
    # Priority 4: Calculate from traffic metrics
    elif monthly_visitors and conversion_rate and average_order_value:
        if monthly_visitors > 0 and conversion_rate > 0 and average_order_value > 0:
            monthly_orders = monthly_visitors * (conversion_rate / 100)
            calculated_monthly = int(monthly_orders * average_order_value)
            final_annual_revenue = calculated_monthly * 12
            calculation_basis = CalculationBasis.CALCULATED
            metrics_used['source'] = 'traffic_calculation'
            metrics_used['monthly_visitors'] = monthly_visitors
            metrics_used['conversion_rate'] = conversion_rate
            metrics_used['average_order_value'] = average_order_value
            metrics_used['calculated_monthly_revenue'] = calculated_monthly
            metrics_used['calculated_annual_revenue'] = final_annual_revenue
            logger.info(f"[BusinessImpact] Calculated from traffic: €{final_annual_revenue:,}")
    
    # Priority 5: Default estimate (EU SME average)
    else:
        metrics_used['source'] = 'eu_sme_average'
        metrics_used['note'] = f"Using EU SME average (€{EU_SME_AVERAGE_REVENUE:,})"
        logger.info(f"[BusinessImpact] Using EU SME average: €{final_annual_revenue:,}")
    
    # =========================================================================
    # STEP 2: Calculate revenue uplift potential
    # =========================================================================
    
    score = max(0, min(100, digital_maturity_score))  # Clamp 0-100
    low_mult, high_mult = _get_score_multipliers(score)
    
    # Calculate improvement potential based on gap to 100
    score_gap = max(10, 100 - score)
    improvement_factor = score_gap / 100  # 0.1 to 1.0
    
    # Apply multipliers with improvement factor
    growth_rate_low = low_mult * improvement_factor
    growth_rate_high = high_mult * improvement_factor
    
    # Calculate revenue impact
    revenue_uplift_low = int(final_annual_revenue * growth_rate_low)
    revenue_uplift_high = int(final_annual_revenue * growth_rate_high)
    revenue_uplift_expected = (revenue_uplift_low + revenue_uplift_high) // 2
    
    monthly_low = revenue_uplift_low // 12
    monthly_high = revenue_uplift_high // 12
    
    # =========================================================================
    # STEP 3: Identify improvement areas
    # =========================================================================
    
    improvement_areas = []
    
    if seo_score < 60:
        improvement_areas.append("SEO optimization" if language == 'en' else "SEO-optimointi")
    if mobile_score < 60:
        improvement_areas.append("Mobile experience" if language == 'en' else "Mobiilikokemus")
    if content_score < 60:
        improvement_areas.append("Content depth and quality" if language == 'en' else "Sisällön laatu ja syvyys")
    if ux_score < 60:
        improvement_areas.append("User experience design" if language == 'en' else "Käyttäjäkokemus")
    if security_score < 60:
        improvement_areas.append("Security and trust signals" if language == 'en' else "Turvallisuus ja luottamussignaalit")
    if score < 50:
        improvement_areas.append("Technical foundation" if language == 'en' else "Tekninen perusta")
    
    # =========================================================================
    # STEP 4: Determine confidence level
    # =========================================================================
    
    if calculation_basis == CalculationBasis.COMPANY_INTEL:
        confidence = ConfidenceLevel.HIGH
    elif calculation_basis == CalculationBasis.PROVIDED:
        confidence = ConfidenceLevel.HIGH
    elif calculation_basis == CalculationBasis.CALCULATED:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.LOW
    
    # =========================================================================
    # STEP 5: Calculate revenue at risk percentage
    # =========================================================================
    
    risk_percentage = 0.0
    if final_annual_revenue > 0 and revenue_at_risk > 0:
        risk_percentage = round((revenue_at_risk / final_annual_revenue) * 100, 2)
    
    # =========================================================================
    # STEP 6: Format output strings
    # =========================================================================
    
    revenue_uplift_range = (
        f"{_format_currency(revenue_uplift_low)} - {_format_currency(revenue_uplift_high)}/year "
        f"({_format_currency(monthly_low)} - {_format_currency(monthly_high)}/mo)"
    )
    
    monthly_revenue_range = f"{_format_currency(monthly_low)} - {_format_currency(monthly_high)}"
    
    # =========================================================================
    # STEP 7: Generate methodology note
    # =========================================================================
    
    if language == 'fi':
        if calculation_basis == CalculationBasis.COMPANY_INTEL:
            methodology_note = f"Laskenta perustuu yrityksen todelliseen liikevaihtoon (€{final_annual_revenue:,}) PRH/YTJ-rekisteristä."
        elif calculation_basis == CalculationBasis.PROVIDED:
            methodology_note = f"Laskenta perustuu antamaasi liikevaihtoon (€{final_annual_revenue:,}/v)."
        elif calculation_basis == CalculationBasis.CALCULATED:
            methodology_note = f"Laskenta perustuu liikennetietoihin (arvioitu €{final_annual_revenue:,}/v)."
        else:
            methodology_note = f"Laskenta perustuu EU:n pk-yrityksen keskiarvoon (€{final_annual_revenue:,}/v)."
    else:
        if calculation_basis == CalculationBasis.COMPANY_INTEL:
            methodology_note = f"Based on actual company revenue (€{final_annual_revenue:,}) from Finnish business registry."
        elif calculation_basis == CalculationBasis.PROVIDED:
            methodology_note = f"Based on your provided revenue (€{final_annual_revenue:,}/year)."
        elif calculation_basis == CalculationBasis.CALCULATED:
            methodology_note = f"Based on traffic metrics (estimated €{final_annual_revenue:,}/year)."
        else:
            methodology_note = f"Based on EU SME average revenue (€{final_annual_revenue:,}/year)."
    
    # =========================================================================
    # STEP 8: Lead generation estimates
    # =========================================================================
    
    lead_low, lead_high = _calculate_lead_estimates(seo_score, content_score)
    lead_gain_estimate = f"{lead_low}-{lead_high} leads/mo" if language == 'en' else f"{lead_low}-{lead_high} liidiä/kk"
    
    # =========================================================================
    # STEP 9: Trust effect
    # =========================================================================
    
    if score >= 70:
        trust_effect = "Strong trust signals - improves perceived quality (NPS +3-5)" if language == 'en' else "Vahvat luottamussignaalit - parantaa koettua laatua (NPS +3-5)"
    elif score >= 50:
        trust_effect = "Moderate trust signals (NPS +1-3)" if language == 'en' else "Kohtalaiset luottamussignaalit (NPS +1-3)"
    else:
        trust_effect = "Weak trust signals - potential negative impact" if language == 'en' else "Heikot luottamussignaalit - mahdollinen negatiivinen vaikutus"
    
    # =========================================================================
    # STEP 10: Potential scenarios for detailed view
    # =========================================================================
    
    potential_scenarios = {
        "quick_wins": {
            "timeframe": "1-3 months" if language == 'en' else "1-3 kuukautta",
            "effort": "low",
            "revenue_uplift": f"€{revenue_uplift_low//3:,} - €{revenue_uplift_low//2:,}",
            "actions": [
                "Fix critical SEO issues" if language == 'en' else "Korjaa kriittiset SEO-ongelmat",
                "Improve mobile viewport" if language == 'en' else "Paranna mobiilinkäytettävyys",
                "Add analytics tracking" if language == 'en' else "Lisää analytiikkaseuranta"
            ]
        },
        "standard_improvement": {
            "timeframe": "3-6 months" if language == 'en' else "3-6 kuukautta",
            "effort": "medium",
            "revenue_uplift": f"€{revenue_uplift_low:,} - €{int(revenue_uplift_low*1.5):,}",
            "actions": [
                "Content strategy execution" if language == 'en' else "Sisältöstrategian toteutus",
                "Technical SEO overhaul" if language == 'en' else "Tekninen SEO-uudistus",
                "UX optimization" if language == 'en' else "Käyttäjäkokemuksen optimointi"
            ]
        },
        "comprehensive_transformation": {
            "timeframe": "6-12 months" if language == 'en' else "6-12 kuukautta",
            "effort": "high",
            "revenue_uplift": f"€{int(revenue_uplift_high*0.8):,} - €{revenue_uplift_high:,}",
            "actions": [
                "Complete digital strategy" if language == 'en' else "Kokonaisvaltainen digitaalistrategia",
                "Marketing automation" if language == 'en' else "Markkinointiautomaatio",
                "Conversion optimization" if language == 'en' else "Konversio-optimointi"
            ]
        }
    }
    
    # =========================================================================
    # RETURN UNIFIED RESULT
    # =========================================================================
    
    logger.info(
        f"[BusinessImpact] Calculated: score={score}, revenue=€{final_annual_revenue:,}, "
        f"uplift={revenue_uplift_range}, confidence={confidence.value}, basis={calculation_basis.value}"
    )
    
    return UnifiedBusinessImpact(
        revenue_uplift_low=revenue_uplift_low,
        revenue_uplift_high=revenue_uplift_high,
        revenue_uplift_expected=revenue_uplift_expected,
        revenue_uplift_range=revenue_uplift_range,
        monthly_revenue_range=monthly_revenue_range,
        revenue_at_risk=revenue_at_risk,
        revenue_at_risk_percentage=risk_percentage,
        confidence=confidence,
        calculation_basis=calculation_basis,
        annual_revenue_used=final_annual_revenue,
        improvement_areas=improvement_areas,
        metrics_used=metrics_used,
        methodology_note=methodology_note,
        lead_gain_low=lead_low,
        lead_gain_high=lead_high,
        lead_gain_estimate=lead_gain_estimate,
        customer_trust_effect=trust_effect,
        potential_scenarios=potential_scenarios,
    )


# =============================================================================
# BACKWARD COMPATIBILITY WRAPPERS
# =============================================================================

def to_legacy_business_impact(result: UnifiedBusinessImpact) -> Dict[str, Any]:
    """
    Convert to legacy BusinessImpact format for backwards compatibility.
    Use result.to_simple_business_impact() instead in new code.
    """
    return result.to_simple_business_impact()


def to_detailed_business_impact(result: UnifiedBusinessImpact) -> Dict[str, Any]:
    """
    Convert to detailed BusinessImpactDetailed format.
    Use result.to_detailed_business_impact() instead in new code.
    """
    return result.to_detailed_business_impact()


def to_guardian_format(result: UnifiedBusinessImpact) -> Dict[str, Any]:
    """
    Convert to Guardian Agent format.
    Use result.to_guardian_format() instead in new code.
    """
    return result.to_guardian_format()


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def create_business_impact_from_analysis(
    basic_analysis: Dict[str, Any],
    content_analysis: Optional[Dict[str, Any]] = None,
    ux_analysis: Optional[Dict[str, Any]] = None,
    revenue_input: Optional[Dict[str, Any]] = None,
    company_intel: Optional[Dict[str, Any]] = None,
    revenue_at_risk: int = 0,
    language: str = 'en'
) -> UnifiedBusinessImpact:
    """
    Helper function to create UnifiedBusinessImpact from analysis data.
    
    This is the recommended way to call calculate_unified_business_impact
    when you have analysis dictionaries rather than individual values.
    
    Args:
        basic_analysis: BasicAnalysis dict with digital_maturity_score, score_breakdown
        content_analysis: ContentAnalysis dict with content_quality_score
        ux_analysis: UXAnalysis dict with overall_ux_score
        revenue_input: RevenueInputRequest dict with revenue data
        company_intel: Company intel dict with revenue from PRH/YTJ
        revenue_at_risk: Pre-calculated revenue at risk
        language: 'en' or 'fi'
    
    Returns:
        UnifiedBusinessImpact
    """
    content_analysis = content_analysis or {}
    ux_analysis = ux_analysis or {}
    revenue_input = revenue_input or {}
    company_intel = company_intel or {}
    
    # Extract score breakdown
    breakdown = basic_analysis.get('score_breakdown', {})
    
    return calculate_unified_business_impact(
        digital_maturity_score=basic_analysis.get('digital_maturity_score', 0),
        company_intel_revenue=company_intel.get('revenue'),
        annual_revenue=revenue_input.get('annual_revenue'),
        monthly_revenue=revenue_input.get('monthly_revenue'),
        monthly_visitors=revenue_input.get('monthly_visitors'),
        conversion_rate=revenue_input.get('conversion_rate'),
        average_order_value=revenue_input.get('average_order_value'),
        seo_score=breakdown.get('seo_basics', 0),
        mobile_score=breakdown.get('mobile', 0),
        content_score=content_analysis.get('content_quality_score', 0),
        ux_score=ux_analysis.get('overall_ux_score', 0),
        security_score=breakdown.get('security', 0),
        revenue_at_risk=revenue_at_risk,
        language=language
    )


# =============================================================================
# MODULE INFO
# =============================================================================

__all__ = [
    'calculate_unified_business_impact',
    'create_business_impact_from_analysis',
    'UnifiedBusinessImpact',
    'CalculationBasis',
    'ConfidenceLevel',
    'EU_SME_AVERAGE_REVENUE',
    # Backward compatibility
    'to_legacy_business_impact',
    'to_detailed_business_impact',
    'to_guardian_format',
]
