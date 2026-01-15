#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analysis History API for Brandista Frontend
Provides endpoints to fetch historical analysis data, trends, and stats

Endpoints:
- GET /api/v1/history - Get user's analysis history
- GET /api/v1/history/{analysis_id} - Get single analysis details
- GET /api/v1/history/trends/{url} - Get trend data for URL
- GET /api/v1/history/stats - Get user statistics
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ============================================================================
# API Router
# ============================================================================

history_router = APIRouter(prefix="/api/v1/history", tags=["Analysis History"])

# ============================================================================
# Response Models
# ============================================================================

class AnalysisSummary(BaseModel):
    """Summary of a single analysis"""
    id: int
    analysis_type: str  # 'single' or 'discovery'
    url: str
    company_name: Optional[str] = None
    score: Optional[int] = None
    threats_count: int = 0
    competitors_count: int = 0
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

class HistoryResponse(BaseModel):
    """Response for history list"""
    analyses: List[AnalysisSummary]
    total: int
    page: int
    page_size: int

class TrendPoint(BaseModel):
    """Single trend data point"""
    date: datetime
    score: int
    threats_count: int
    revenue_at_risk: float

class TrendResponse(BaseModel):
    """Trend data response"""
    url: str
    period_days: int
    data_points: List[TrendPoint]
    score_change: int
    threats_change: int

class StatsResponse(BaseModel):
    """User statistics response"""
    total_analyses: int
    analyses_this_month: int
    discoveries_this_month: int
    analyses_limit: int
    discoveries_limit: int
    avg_score: Optional[float] = None
    total_threats_detected: int
    total_revenue_protected: float

# ============================================================================
# Database Helper
# ============================================================================

_pool = None

async def get_db_pool():
    """Get or create database connection pool"""
    global _pool
    if _pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return None
        try:
            import asyncpg
            _pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=5,
                command_timeout=60
            )
        except Exception as e:
            logger.error(f"Failed to create DB pool: {e}")
            return None
    return _pool

# ============================================================================
# ENDPOINTS
# ============================================================================

@history_router.get("", response_model=HistoryResponse)
async def get_analysis_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    analysis_type: Optional[str] = Query(None, description="Filter by type: single or discovery"),
    # current_user = Depends(get_current_user)  # Add auth when ready
):
    """
    Get paginated list of user's analysis history.

    Returns recent analyses with summary information.
    """
    pool = await get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    # TODO: Get from authenticated user
    user_id = "demo_user"

    try:
        async with pool.acquire() as conn:
            # Build query
            where_clauses = ["user_id = $1"]
            params = [user_id]

            if analysis_type:
                where_clauses.append(f"analysis_type = ${len(params) + 1}")
                params.append(analysis_type)

            where_sql = " AND ".join(where_clauses)

            # Get total count
            total = await conn.fetchval(f"""
                SELECT COUNT(*) FROM analyses
                WHERE {where_sql}
            """, *params)

            # Get paginated results
            offset = (page - 1) * page_size
            params.extend([page_size, offset])

            rows = await conn.fetch(f"""
                SELECT
                    a.id,
                    a.analysis_type,
                    a.url,
                    a.company_name,
                    a.status,
                    a.created_at,
                    a.completed_at,
                    COALESCE(ar.digital_maturity_score, 0) as score,
                    COALESCE(cd.competitors_found, 0) as competitors_count
                FROM analyses a
                LEFT JOIN analysis_results ar ON ar.analysis_id = a.id
                LEFT JOIN competitor_discoveries cd ON cd.analysis_id = a.id
                WHERE {where_sql}
                ORDER BY a.created_at DESC
                LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """, *params)

            analyses = []
            for row in rows:
                analyses.append(AnalysisSummary(
                    id=row['id'],
                    analysis_type=row['analysis_type'],
                    url=row['url'],
                    company_name=row['company_name'],
                    score=row['score'],
                    threats_count=0,  # TODO: Add threat count
                    competitors_count=row['competitors_count'],
                    status=row['status'],
                    created_at=row['created_at'],
                    completed_at=row['completed_at']
                ))

            return HistoryResponse(
                analyses=analyses,
                total=total,
                page=page,
                page_size=page_size
            )

    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")


@history_router.get("/stats", response_model=StatsResponse)
async def get_user_stats():
    """
    Get user's usage statistics and limits.

    Returns total analyses, monthly usage, limits, and aggregate metrics.
    """
    pool = await get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    # TODO: Get from authenticated user
    user_id = "demo_user"

    try:
        async with pool.acquire() as conn:
            # Get usage stats
            usage = await conn.fetchrow("""
                SELECT * FROM user_analysis_usage
                WHERE user_id = $1
            """, user_id)

            # Get aggregate stats
            agg = await conn.fetchrow("""
                SELECT
                    COUNT(*) as total,
                    AVG(ar.digital_maturity_score) as avg_score,
                    SUM(CASE WHEN a.analysis_type = 'single' THEN 1 ELSE 0 END) as single_count,
                    SUM(CASE WHEN a.analysis_type = 'discovery' THEN 1 ELSE 0 END) as discovery_count
                FROM analyses a
                LEFT JOIN analysis_results ar ON ar.analysis_id = a.id
                WHERE a.user_id = $1 AND a.status = 'completed'
            """, user_id)

            # Get threat and revenue stats from scheduled analysis history
            threat_stats = await conn.fetchrow("""
                SELECT
                    COALESCE(SUM(threats_count), 0) as total_threats,
                    COALESCE(SUM(revenue_at_risk), 0) as total_revenue
                FROM analysis_history_trends aht
                JOIN scheduled_analyses sa ON sa.id = aht.scheduled_id
                WHERE sa.user_id = $1
            """, user_id)

            return StatsResponse(
                total_analyses=agg['total'] if agg else 0,
                analyses_this_month=usage['single_analyses_this_month'] if usage else 0,
                discoveries_this_month=usage['discoveries_this_month'] if usage else 0,
                analyses_limit=usage['single_analysis_limit'] if usage else 10,
                discoveries_limit=usage['discovery_limit'] if usage else 3,
                avg_score=round(agg['avg_score'], 1) if agg and agg['avg_score'] else None,
                total_threats_detected=threat_stats['total_threats'] if threat_stats else 0,
                total_revenue_protected=float(threat_stats['total_revenue']) if threat_stats else 0.0
            )

    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")


@history_router.get("/trends/{url:path}", response_model=TrendResponse)
async def get_url_trends(
    url: str,
    days: int = Query(30, ge=7, le=365)
):
    """
    Get historical trend data for a specific URL.

    Returns score and threat history over time.
    """
    pool = await get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    score,
                    threats_count,
                    revenue_at_risk,
                    analyzed_at as date
                FROM analysis_history_trends
                WHERE url = $1
                AND analyzed_at > NOW() - INTERVAL '%s days'
                ORDER BY analyzed_at ASC
            """ % days, url)

            if not rows:
                raise HTTPException(status_code=404, detail="No trend data found for this URL")

            data_points = [
                TrendPoint(
                    date=row['date'],
                    score=row['score'] or 0,
                    threats_count=row['threats_count'] or 0,
                    revenue_at_risk=float(row['revenue_at_risk'] or 0)
                )
                for row in rows
            ]

            # Calculate changes
            if len(data_points) >= 2:
                score_change = data_points[-1].score - data_points[0].score
                threats_change = data_points[-1].threats_count - data_points[0].threats_count
            else:
                score_change = 0
                threats_change = 0

            return TrendResponse(
                url=url,
                period_days=days,
                data_points=data_points,
                score_change=score_change,
                threats_change=threats_change
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching trends: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch trends")


@history_router.get("/{analysis_id}")
async def get_analysis_details(analysis_id: int):
    """
    Get full details of a specific analysis.

    Returns complete analysis result including all agent data.
    """
    pool = await get_db_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    # TODO: Get from authenticated user
    user_id = "demo_user"

    try:
        async with pool.acquire() as conn:
            # Get analysis
            analysis = await conn.fetchrow("""
                SELECT * FROM analyses WHERE id = $1
            """, analysis_id)

            if not analysis:
                raise HTTPException(status_code=404, detail="Analysis not found")

            # Verify ownership (uncomment when auth is ready)
            # if analysis['user_id'] != user_id:
            #     raise HTTPException(status_code=403, detail="Not authorized")

            result = dict(analysis)

            if analysis['analysis_type'] == 'single':
                # Get single analysis result
                details = await conn.fetchrow("""
                    SELECT * FROM analysis_results WHERE analysis_id = $1
                """, analysis_id)

                if details:
                    result['result'] = {
                        'digital_maturity_score': details['digital_maturity_score'],
                        'security_score': details['security_score'],
                        'seo_score': details['seo_score'],
                        'content_score': details['content_score'],
                        'technical_score': details['technical_score'],
                        'mobile_score': details['mobile_score'],
                        'social_score': details['social_score'],
                        'performance_score': details['performance_score'],
                        'basic_analysis': json.loads(details['basic_analysis']) if details['basic_analysis'] else None,
                        'technical_audit': json.loads(details['technical_audit']) if details['technical_audit'] else None,
                        'content_analysis': json.loads(details['content_analysis']) if details['content_analysis'] else None,
                        'seo_analysis': json.loads(details['seo_analysis']) if details['seo_analysis'] else None,
                        'ai_analysis': json.loads(details['ai_analysis']) if details['ai_analysis'] else None,
                        'smart_actions': json.loads(details['smart_actions']) if details['smart_actions'] else None
                    }

            elif analysis['analysis_type'] == 'discovery':
                # Get discovery metadata
                discovery = await conn.fetchrow("""
                    SELECT * FROM competitor_discoveries WHERE analysis_id = $1
                """, analysis_id)

                if discovery:
                    # Get competitors
                    competitors = await conn.fetch("""
                        SELECT * FROM competitor_results
                        WHERE discovery_id = $1
                        ORDER BY rank_in_results
                    """, discovery['id'])

                    result['discovery'] = {
                        'max_competitors': discovery['max_competitors'],
                        'competitors_found': discovery['competitors_found'],
                        'search_terms': json.loads(discovery['search_terms']) if discovery['search_terms'] else [],
                        'summary': json.loads(discovery['summary']) if discovery['summary'] else None
                    }

                    result['competitors'] = [
                        {
                            'domain': c['domain'],
                            'url': c['url'],
                            'company_name': c['company_name'],
                            'digital_maturity_score': c['digital_maturity_score'],
                            'rank': c['rank_in_results']
                        }
                        for c in competitors
                    ]

            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching analysis details: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analysis details")


# ============================================================================
# DASHBOARD STATS ENDPOINT (Real data for frontend)
# ============================================================================

@history_router.get("/dashboard/realtime")
async def get_dashboard_realtime_stats():
    """
    Get real-time dashboard statistics.

    This replaces mock data in the frontend with actual database values.
    Returns stats for the Defence Layer and dashboard cards.
    """
    pool = await get_db_pool()
    if not pool:
        # Return mock data if DB not available
        return {
            "threats_detected": 0,
            "threats_mitigated": 0,
            "active_monitoring": 0,
            "revenue_protected": 0,
            "total_analyses": 0,
            "avg_score": 0,
            "data_source": "mock"
        }

    # TODO: Get from authenticated user
    user_id = "demo_user"

    try:
        async with pool.acquire() as conn:
            # Get scheduled analyses count (active monitoring)
            active_monitoring = await conn.fetchval("""
                SELECT COUNT(*) FROM scheduled_analyses
                WHERE user_id = $1 AND enabled = TRUE
            """, user_id)

            # Get latest threat data from history
            latest = await conn.fetchrow("""
                SELECT
                    COALESCE(SUM(threats_count), 0) as threats_total,
                    COALESCE(SUM(revenue_at_risk), 0) as revenue_total,
                    COUNT(*) as analysis_count,
                    AVG(score) as avg_score
                FROM analysis_history_trends aht
                JOIN scheduled_analyses sa ON sa.id = aht.scheduled_id
                WHERE sa.user_id = $1
                AND aht.analyzed_at > NOW() - INTERVAL '30 days'
            """, user_id)

            # Get total analyses
            total = await conn.fetchval("""
                SELECT COUNT(*) FROM analyses
                WHERE user_id = $1 AND status = 'completed'
            """, user_id)

            return {
                "threats_detected": int(latest['threats_total']) if latest else 0,
                "threats_mitigated": 0,  # TODO: Track mitigated threats
                "active_monitoring": active_monitoring or 0,
                "revenue_protected": float(latest['revenue_total']) if latest else 0,
                "total_analyses": total or 0,
                "avg_score": round(float(latest['avg_score']), 1) if latest and latest['avg_score'] else 0,
                "data_source": "database"
            }

    except Exception as e:
        logger.error(f"Error fetching realtime stats: {e}")
        return {
            "threats_detected": 0,
            "threats_mitigated": 0,
            "active_monitoring": 0,
            "revenue_protected": 0,
            "total_analyses": 0,
            "avg_score": 0,
            "data_source": "error",
            "error": str(e)
        }
