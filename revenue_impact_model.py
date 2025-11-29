"""
Revenue Impact Model - Minimal version
"""

from typing import Dict, Any, List
from dataclasses import dataclass


@dataclass
class RiskImpactItem:
    risk_id: str
    risk_name: str
    description: str
    annual_impact_low: int
    annual_impact_high: int
    annual_impact_expected: int
    impact_percentage: float
    affected_revenue_base: int
    affected_area: str
    fix_effort: str
    fix_cost_range: str
    fix_time_range: str
    priority: int
    roi_ratio: float


@dataclass 
class RevenueImpactAnalysis:
    company_name: str
    annual_revenue: int
    industry: str
    digital_revenue: int
    digital_revenue_share: float
    organic_revenue: int
    mobile_revenue: int
    risks: List[RiskImpactItem]
    total_impact_low: int
    total_impact_high: int
    total_impact_expected: int
    total_impact_percentage: float
    total_fix_cost_low: int
    total_fix_cost_high: int
    estimated_roi_ratio: float
    confidence_level: str
    confidence_note: str
    methodology_note: str


def detect_industry(url: str, basic_analysis: Dict[str, Any], company_intel: Dict[str, Any] = None) -> str:
    """Detect industry from URL and data"""
    url_lower = url.lower()
    
    if any(x in url_lower for x in ["kulta", "koru", "jewelry", "gold"]):
        return "jewelry"
    if any(x in url_lower for x in ["shop", "store", "kauppa"]):
        return "ecommerce"
    
    return "retail"


def detect_risks_from_analysis(basic: Dict, technical: Dict, content: Dict) -> List[str]:
    """Detect risks from analysis data"""
    risks = []
    
    breakdown = basic.get("score_breakdown", {})
    
    if breakdown.get("security", 15) < 10:
        risks.append("ssl_missing")
    if breakdown.get("mobile", 15) < 9:
        risks.append("mobile_not_optimized")
    if breakdown.get("seo_basics", 20) < 12:
        risks.append("seo_weak")
    if breakdown.get("content", 20) < 12:
        risks.append("thin_content")
        
    return risks


def calculate_revenue_impact(
    annual_revenue: int,
    detected_risks: List[str],
    industry: str = "retail",
    company_name: str = "Company",
    language: str = "fi"
) -> RevenueImpactAnalysis:
    """Calculate revenue impact"""
    
    # Industry digital shares
    digital_shares = {
        "ecommerce": 0.85,
        "retail": 0.35,
        "jewelry": 0.25,
        "saas": 0.90,
        "b2b_services": 0.20,
        "manufacturing": 0.10
    }
    
    digital_share = digital_shares.get(industry, 0.30)
    digital_revenue = int(annual_revenue * digital_share)
    organic_revenue = int(digital_revenue * 0.35)
    mobile_revenue = int(digital_revenue * 0.55)
    
    # Calculate risks
    risk_impacts = {
        "ssl_missing": 0.15,
        "mobile_not_optimized": 0.12,
        "seo_weak": 0.10,
        "thin_content": 0.08,
        "page_speed_critical": 0.15
    }
    
    risk_items = []
    total_impact = 0
    diminishing = 1.0
    
    for risk_id in detected_risks:
        impact_rate = risk_impacts.get(risk_id, 0.05)
        impact = int(digital_revenue * impact_rate * diminishing)
        total_impact += impact
        diminishing *= 0.75
        
        risk_items.append(RiskImpactItem(
            risk_id=risk_id,
            risk_name=risk_id.replace("_", " ").title(),
            description="Risk detected",
            annual_impact_low=int(impact * 0.7),
            annual_impact_high=int(impact * 1.3),
            annual_impact_expected=impact,
            impact_percentage=round(impact_rate * 100, 1),
            affected_revenue_base=digital_revenue,
            affected_area="digital",
            fix_effort="medium",
            fix_cost_range="1000-5000 EUR",
            fix_time_range="7-30 days",
            priority=len(risk_items) + 1,
            roi_ratio=round(impact / 3000, 1)
        ))
    
    # Cap at 40%
    total_impact = min(total_impact, int(digital_revenue * 0.4))
    
    return RevenueImpactAnalysis(
        company_name=company_name,
        annual_revenue=annual_revenue,
        industry=industry,
        digital_revenue=digital_revenue,
        digital_revenue_share=digital_share,
        organic_revenue=organic_revenue,
        mobile_revenue=mobile_revenue,
        risks=risk_items,
        total_impact_low=int(total_impact * 0.7),
        total_impact_high=int(total_impact * 1.3),
        total_impact_expected=total_impact,
        total_impact_percentage=round((total_impact / annual_revenue) * 100, 2),
        total_fix_cost_low=len(risk_items) * 1000,
        total_fix_cost_high=len(risk_items) * 5000,
        estimated_roi_ratio=round(total_impact / (len(risk_items) * 3000), 1) if risk_items else 0,
        confidence_level="medium",
        confidence_note="Based on industry averages",
        methodology_note=f"Industry: {industry}, digital share: {digital_share*100}%"
    )


def revenue_impact_to_dict(analysis: RevenueImpactAnalysis) -> Dict[str, Any]:
    """Convert to dict"""
    return {
        "company_name": analysis.company_name,
        "annual_revenue": analysis.annual_revenue,
        "industry": analysis.industry,
        "digital_revenue": analysis.digital_revenue,
        "digital_revenue_share": analysis.digital_revenue_share,
        "organic_revenue": analysis.organic_revenue,
        "mobile_revenue": analysis.mobile_revenue,
        "risks": [
            {
                "risk_id": r.risk_id,
                "risk_name": r.risk_name,
                "description": r.description,
                "annual_impact_low": r.annual_impact_low,
                "annual_impact_high": r.annual_impact_high,
                "annual_impact_expected": r.annual_impact_expected,
                "impact_percentage": r.impact_percentage,
                "affected_revenue_base": r.affected_revenue_base,
                "affected_area": r.affected_area,
                "fix_effort": r.fix_effort,
                "fix_cost_range": r.fix_cost_range,
                "fix_time_range": r.fix_time_range,
                "priority": r.priority,
                "roi_ratio": r.roi_ratio
            }
            for r in analysis.risks
        ],
        "total_impact_low": analysis.total_impact_low,
        "total_impact_high": analysis.total_impact_high,
        "total_impact_expected": analysis.total_impact_expected,
        "total_impact_percentage": analysis.total_impact_percentage,
        "total_fix_cost_low": analysis.total_fix_cost_low,
        "total_fix_cost_high": analysis.total_fix_cost_high,
        "estimated_roi_ratio": analysis.estimated_roi_ratio,
        "confidence_level": analysis.confidence_level,
        "confidence_note": analysis.confidence_note,
        "methodology_note": analysis.methodology_note
    }
