#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Context API for Growth Engine 2.0
=================================
REST API endpoints for unified context management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from unified_context import (
    get_unified_context,
    get_user_profile,
    save_user_profile,
    get_recent_analyses,
    save_analysis,
    get_tracked_competitors,
    add_tracked_competitor,
    get_discovered_competitors,
    save_discovered_competitor,
    update_discovered_status,
    get_agent_insights,
    init_unified_context_tables,
    UnifiedContext
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/context", tags=["Context"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ProfileCreate(BaseModel):
    url: str
    industry: Optional[str] = None
    market: Optional[str] = None
    known_competitors: Optional[List[str]] = []
    revenue_estimate: Optional[float] = None
    company_size: Optional[str] = None
    goals: Optional[List[str]] = []


class CompetitorTrack(BaseModel):
    url: str
    domain: Optional[str] = None
    name: Optional[str] = None
    business_id: Optional[str] = None
    industry: Optional[str] = None


class DiscoveredStatusUpdate(BaseModel):
    url: str
    status: str  # new, reviewed, tracking, ignored


class AnalysisSave(BaseModel):
    url: str
    score: int
    ranking: int = 1
    total_competitors: int = 1
    revenue_at_risk: float = 0
    rasm_score: int = 0
    benchmark: Optional[Dict] = {}
    threats: Optional[List] = []
    opportunities: Optional[List] = []
    action_plan: Optional[Dict] = {}
    raw_results: Optional[Dict] = {}
    duration_seconds: float = 0


class ContextResponse(BaseModel):
    user_id: str
    profile: Optional[Dict] = None
    recent_analyses: List[Dict] = []
    tracked_competitors: List[Dict] = []
    discovered_competitors: List[Dict] = []
    historical_insights: List[Dict] = []
    trends: Dict = {}
    agent_prompt: Optional[str] = None


# ============================================================================
# INITIALIZATION
# ============================================================================

@router.on_event("startup")
async def startup_init_tables():
    """Initialize database tables on startup"""
    init_unified_context_tables()


# ============================================================================
# UNIFIED CONTEXT ENDPOINTS
# ============================================================================

@router.get("/{user_id}", response_model=ContextResponse)
async def get_context(
    user_id: str,
    include_prompt: bool = Query(False, description="Include agent prompt text")
):
    """
    Get unified context for a user.
    This is the main endpoint that aggregates all data for AI agents.
    """
    try:
        context = get_unified_context(user_id)
        
        response = ContextResponse(
            user_id=user_id,
            profile=context.profile,
            recent_analyses=context.recent_analyses,
            tracked_competitors=context.tracked_competitors,
            discovered_competitors=context.discovered_competitors,
            historical_insights=context.historical_insights,
            trends=context.trends
        )
        
        if include_prompt:
            response.agent_prompt = context.to_agent_prompt()
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to get context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{user_id}/prompt")
async def get_context_prompt(
    user_id: str,
    agent_id: Optional[str] = Query(None, description="Get agent-specific prompt")
):
    """
    Get context as agent prompt text.
    Useful for injecting into agent system prompts.
    """
    from unified_context import context_to_agent_system_prompt
    
    try:
        context = get_unified_context(user_id)
        
        if agent_id:
            prompt = context_to_agent_system_prompt(context, agent_id)
        else:
            prompt = context.to_agent_prompt()
        
        return {
            "user_id": user_id,
            "agent_id": agent_id,
            "prompt": prompt,
            "context_summary": {
                "analyses_count": len(context.recent_analyses),
                "tracked_count": len(context.tracked_competitors),
                "discovered_count": len(context.discovered_competitors),
                "insights_count": len(context.historical_insights)
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get prompt: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PROFILE ENDPOINTS
# ============================================================================

@router.get("/{user_id}/profile")
async def get_profile(user_id: str):
    """Get user profile"""
    profile = get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.post("/{user_id}/profile")
async def create_or_update_profile(user_id: str, profile: ProfileCreate):
    """Create or update user profile"""
    success = save_user_profile(
        user_id=user_id,
        url=profile.url,
        industry=profile.industry,
        market=profile.market,
        known_competitors=profile.known_competitors
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save profile")
    
    return {"status": "ok", "message": "Profile saved"}


# ============================================================================
# ANALYSIS ENDPOINTS
# ============================================================================

@router.get("/{user_id}/analyses")
async def list_analyses(
    user_id: str,
    limit: int = Query(10, ge=1, le=100)
):
    """Get recent analyses for user"""
    return get_recent_analyses(user_id, limit=limit)


@router.post("/{user_id}/analyses")
async def save_analysis_result(user_id: str, analysis: AnalysisSave):
    """Save analysis result"""
    analysis_id = save_analysis(
        user_id=user_id,
        url=analysis.url,
        score=analysis.score,
        ranking=analysis.ranking,
        total_competitors=analysis.total_competitors,
        revenue_at_risk=analysis.revenue_at_risk,
        rasm_score=analysis.rasm_score,
        benchmark=analysis.benchmark,
        threats=analysis.threats,
        opportunities=analysis.opportunities,
        action_plan=analysis.action_plan,
        raw_results=analysis.raw_results,
        duration_seconds=analysis.duration_seconds
    )
    
    if not analysis_id:
        raise HTTPException(status_code=500, detail="Failed to save analysis")
    
    return {"status": "ok", "analysis_id": analysis_id}


# ============================================================================
# TRACKED COMPETITORS (RADAR) ENDPOINTS
# ============================================================================

@router.get("/{user_id}/tracked")
async def list_tracked_competitors(
    user_id: str,
    active_only: bool = Query(True)
):
    """Get tracked competitors (Radar)"""
    return get_tracked_competitors(user_id, active_only=active_only)


@router.post("/{user_id}/tracked")
async def track_competitor(user_id: str, competitor: CompetitorTrack):
    """Add competitor to tracking (Radar)"""
    success = add_tracked_competitor(
        user_id=user_id,
        url=competitor.url,
        domain=competitor.domain,
        name=competitor.name,
        business_id=competitor.business_id,
        industry=competitor.industry
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to track competitor")
    
    return {"status": "ok", "message": "Competitor tracked"}


@router.delete("/{user_id}/tracked")
async def untrack_competitor(user_id: str, url: str):
    """Remove competitor from tracking"""
    from unified_context import connect_db
    
    conn = connect_db()
    if not conn:
        raise HTTPException(status_code=500, detail="Database unavailable")
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tracked_competitors
            SET is_active = FALSE
            WHERE user_id = %s AND url = %s
        """, (user_id, url))
        conn.commit()
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Competitor not found")
        
        return {"status": "ok", "message": "Competitor untracked"}
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# DISCOVERED COMPETITORS ENDPOINTS
# ============================================================================

@router.get("/{user_id}/discovered")
async def list_discovered_competitors(
    user_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200)
):
    """Get discovered competitors"""
    return get_discovered_competitors(user_id, status=status, limit=limit)


@router.post("/{user_id}/discovered/status")
async def update_discovery_status(user_id: str, update: DiscoveredStatusUpdate):
    """Update discovered competitor status"""
    valid_statuses = ['new', 'reviewed', 'tracking', 'ignored']
    if update.status not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )
    
    success = update_discovered_status(user_id, update.url, update.status)
    
    if not success:
        raise HTTPException(status_code=404, detail="Discovered competitor not found")
    
    # If marking as "tracking", also add to tracked competitors
    if update.status == 'tracking':
        discovered = get_discovered_competitors(user_id)
        comp = next((c for c in discovered if c['url'] == update.url), None)
        if comp:
            add_tracked_competitor(
                user_id=user_id,
                url=comp['url'],
                domain=comp.get('domain'),
                name=comp.get('name'),
                company_intel=comp.get('company_intel')
            )
    
    return {"status": "ok", "message": f"Status updated to {update.status}"}


# ============================================================================
# INSIGHTS ENDPOINTS
# ============================================================================

@router.get("/{user_id}/insights")
async def list_insights(
    user_id: str,
    agent_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=500)
):
    """Get historical agent insights"""
    return get_agent_insights(
        user_id=user_id,
        agent_id=agent_id,
        days=days,
        limit=limit
    )


# ============================================================================
# TRENDS ENDPOINT
# ============================================================================

@router.get("/{user_id}/trends")
async def get_trends(user_id: str):
    """Get calculated trends for user"""
    context = get_unified_context(user_id)
    return {
        "user_id": user_id,
        "trends": context.trends,
        "summary": {
            "total_analyses": len(context.recent_analyses),
            "tracked_competitors": len(context.tracked_competitors),
            "new_discoveries": len([
                c for c in context.discovered_competitors 
                if c.get('status') == 'new'
            ])
        }
    }
