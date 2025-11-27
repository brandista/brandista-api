"""
Growth Engine 2.0 - Company Intelligence API
Due Diligence endpoints for Finnish company data

Endpoints:
    GET  /api/v1/company/search?q=Valio
    GET  /api/v1/company/{business_id}
    GET  /api/v1/company/domain/{domain}
    POST /api/v1/company/enrich  (batch enrich competitors)
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from company_intel import CompanyIntel, get_company_intel, search_companies

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class CompanySearchResult(BaseModel):
    business_id: str
    name: str
    founded_year: Optional[int] = None
    industry: Optional[str] = None
    city: Optional[str] = None
    status: Optional[str] = None


class CompanyProfile(BaseModel):
    business_id: str
    name: Optional[str] = None
    founded_year: Optional[int] = None
    registration_date: Optional[str] = None
    company_age_years: Optional[int] = None
    
    # Address
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    
    # Classification
    industry: Optional[str] = None
    industry_code: Optional[str] = None
    company_form: Optional[str] = None
    status: Optional[str] = None
    size_category: Optional[str] = None
    
    # Financial (from Kauppalehti)
    revenue: Optional[int] = None
    revenue_text: Optional[str] = None
    employees: Optional[int] = None
    employees_text: Optional[str] = None
    profit: Optional[int] = None
    profit_text: Optional[str] = None
    
    # Meta
    sources: List[str] = []
    fetched_at: Optional[str] = None


class CompanySearchResponse(BaseModel):
    query: str
    count: int
    results: List[CompanySearchResult]


class EnrichRequest(BaseModel):
    """Request to enrich competitor list with company intel"""
    competitors: List[dict]


class EnrichResponse(BaseModel):
    """Response with enriched competitors"""
    enriched_count: int
    competitors: List[dict]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/search", response_model=CompanySearchResponse)
async def search_company(
    q: str = Query(..., min_length=2, description="Company name to search"),
    limit: int = Query(5, ge=1, le=20, description="Max results")
):
    """
    Search Finnish companies by name.
    
    Uses YTJ (PRH) official registry.
    
    Example: /api/v1/company/search?q=Valio
    """
    logger.info(f"[CompanyAPI] Search: {q}")
    
    intel = CompanyIntel()
    try:
        results = await intel.search_company(q, max_results=limit)
        
        return CompanySearchResponse(
            query=q,
            count=len(results),
            results=[CompanySearchResult(**r) for r in results]
        )
    except Exception as e:
        logger.error(f"[CompanyAPI] Search error: {e}")
        raise HTTPException(500, f"Search failed: {str(e)}")
    finally:
        await intel.close()


@router.get("/id/{business_id}", response_model=CompanyProfile)
async def get_company_by_id(business_id: str):
    """
    Get full company profile by Y-tunnus (business ID).
    
    Combines data from:
    - YTJ (official registry) - basic info, industry
    - Kauppalehti - financial data (revenue, employees)
    
    Example: /api/v1/company/id/0116754-4
    """
    logger.info(f"[CompanyAPI] Get by ID: {business_id}")
    
    intel = CompanyIntel()
    try:
        profile = await intel.get_company_profile(business_id)
        
        if not profile:
            raise HTTPException(404, f"Company not found: {business_id}")
        
        return CompanyProfile(**profile)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CompanyAPI] Get error: {e}")
        raise HTTPException(500, f"Fetch failed: {str(e)}")
    finally:
        await intel.close()


@router.get("/domain/{domain}", response_model=CompanyProfile)
async def get_company_by_domain(domain: str):
    """
    Find company by domain name.
    
    Extracts company name from domain, searches YTJ,
    returns best match with full profile.
    
    Example: /api/v1/company/domain/valio.fi
    """
    logger.info(f"[CompanyAPI] Get by domain: {domain}")
    
    intel = CompanyIntel()
    try:
        profile = await intel.get_company_from_domain(domain)
        
        if not profile:
            raise HTTPException(404, f"No company found for domain: {domain}")
        
        return CompanyProfile(**profile)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CompanyAPI] Domain lookup error: {e}")
        raise HTTPException(500, f"Lookup failed: {str(e)}")
    finally:
        await intel.close()


@router.post("/enrich", response_model=EnrichResponse)
async def enrich_competitors(request: EnrichRequest):
    """
    Batch enrich competitor list with company intelligence.
    
    Input: List of competitors with 'url' field
    Output: Same list with added company_intel, company_name, revenue, employees
    
    Example request:
    {
        "competitors": [
            {"url": "https://valio.fi", "score": 80},
            {"url": "https://arla.fi", "score": 75}
        ]
    }
    """
    logger.info(f"[CompanyAPI] Enrich {len(request.competitors)} competitors")
    
    intel = CompanyIntel()
    enriched = []
    enriched_count = 0
    
    try:
        for competitor in request.competitors:
            result = await intel.enrich_competitor(competitor.copy())
            enriched.append(result)
            
            if result.get('company_intel'):
                enriched_count += 1
        
        logger.info(f"[CompanyAPI] ✅ Enriched {enriched_count}/{len(request.competitors)}")
        
        return EnrichResponse(
            enriched_count=enriched_count,
            competitors=enriched
        )
    except Exception as e:
        logger.error(f"[CompanyAPI] Enrich error: {e}")
        raise HTTPException(500, f"Enrichment failed: {str(e)}")
    finally:
        await intel.close()


# =============================================================================
# QUICK TEST ENDPOINT
# =============================================================================

@router.get("/test")
async def test_company_intel():
    """Quick test to verify company intel is working"""
    intel = CompanyIntel()
    try:
        # Test YTJ search
        results = await intel.search_company("Valio", max_results=1)
        
        ytj_ok = len(results) > 0
        ytj_result = results[0] if results else None
        
        # Test full profile if we got a result
        kl_ok = False
        profile = None
        if ytj_result:
            profile = await intel.get_company_profile(ytj_result['business_id'])
            kl_ok = profile and 'kauppalehti' in profile.get('sources', [])
        
        return {
            "status": "ok" if ytj_ok else "partial",
            "ytj": {
                "status": "ok" if ytj_ok else "error",
                "sample": ytj_result
            },
            "kauppalehti": {
                "status": "ok" if kl_ok else "unavailable",
                "has_revenue": profile.get('revenue') is not None if profile else False,
                "has_employees": profile.get('employees') is not None if profile else False
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
    finally:
        await intel.close()
