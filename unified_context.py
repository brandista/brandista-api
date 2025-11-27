#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Context Module for Growth Engine 2.0
============================================
Provides intelligent context awareness across all dashboard tabs.

This module enables agents to:
- Access analysis history
- Know about tracked competitors (Radar)
- See discovered competitors
- Understand user profile and preferences
- Track their own insights over time
"""

import psycopg2
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv("DATABASE_URL")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class UnifiedContext:
    """Complete context for AI agents"""
    user_id: str
    profile: Optional[Dict[str, Any]] = None
    recent_analyses: List[Dict[str, Any]] = None
    tracked_competitors: List[Dict[str, Any]] = None
    discovered_competitors: List[Dict[str, Any]] = None
    historical_insights: List[Dict[str, Any]] = None
    trends: Dict[str, Any] = None
    
    def __post_init__(self):
        self.recent_analyses = self.recent_analyses or []
        self.tracked_competitors = self.tracked_competitors or []
        self.discovered_competitors = self.discovered_competitors or []
        self.historical_insights = self.historical_insights or []
        self.trends = self.trends or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_agent_prompt(self) -> str:
        """Generate context summary for agent prompts"""
        lines = []
        
        # Profile
        if self.profile:
            lines.append(f"## User Profile")
            lines.append(f"- Website: {self.profile.get('url', 'N/A')}")
            lines.append(f"- Industry: {self.profile.get('industry', 'N/A')}")
            lines.append(f"- Market: {self.profile.get('market', 'N/A')}")
            lines.append("")
        
        # Analysis history
        if self.recent_analyses:
            lines.append(f"## Analysis History ({len(self.recent_analyses)} recent)")
            for i, analysis in enumerate(self.recent_analyses[:3]):
                score = analysis.get('score', 0)
                date = analysis.get('created_at', '')[:10]
                lines.append(f"- {date}: Score {score}/100")
            lines.append("")
        
        # Tracked competitors (Radar)
        if self.tracked_competitors:
            lines.append(f"## Tracked Competitors ({len(self.tracked_competitors)})")
            for comp in self.tracked_competitors[:5]:
                name = comp.get('name') or comp.get('domain', 'Unknown')
                score = comp.get('last_score', 0)
                lines.append(f"- {name}: {score}/100")
            lines.append("")
        
        # Discovered competitors
        if self.discovered_competitors:
            new_count = len([c for c in self.discovered_competitors if c.get('status') == 'new'])
            lines.append(f"## Discovered Competitors ({len(self.discovered_competitors)}, {new_count} new)")
            lines.append("")
        
        # Trends
        if self.trends:
            lines.append(f"## Trends")
            if 'score_change' in self.trends:
                change = self.trends['score_change']
                direction = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                lines.append(f"- Score trend: {direction} {change:+.1f} points")
            if 'top_threat' in self.trends:
                lines.append(f"- Top threat: {self.trends['top_threat']}")
            if 'best_opportunity' in self.trends:
                lines.append(f"- Best opportunity: {self.trends['best_opportunity']}")
            lines.append("")
        
        return "\n".join(lines)


# ============================================================================
# DATABASE SCHEMA
# ============================================================================

def init_unified_context_tables():
    """Initialize all tables for unified context"""
    conn = connect_db()
    if not conn:
        logger.warning("No database connection - skipping unified context init")
        return False
    
    try:
        cursor = conn.cursor()
        
        # 1. User Profiles (Growth Engine profiles)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL UNIQUE,
                url VARCHAR(500),
                industry VARCHAR(100),
                market VARCHAR(100),
                known_competitors TEXT[],
                revenue_estimate DECIMAL(15,2),
                company_size VARCHAR(50),
                goals TEXT[],
                preferences JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. Analysis History
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS analyses (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                url VARCHAR(500) NOT NULL,
                score INTEGER,
                ranking INTEGER,
                total_competitors INTEGER,
                revenue_at_risk DECIMAL(15,2),
                rasm_score INTEGER,
                benchmark JSONB,
                threats JSONB,
                opportunities JSONB,
                action_plan JSONB,
                raw_results JSONB,
                duration_seconds DECIMAL(10,2),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyses_user_id ON analyses(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at DESC)
        """)
        
        # 3. Tracked Competitors (Radar)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tracked_competitors (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                url VARCHAR(500) NOT NULL,
                domain VARCHAR(255),
                name VARCHAR(255),
                business_id VARCHAR(50),
                industry VARCHAR(100),
                last_score INTEGER,
                last_analysis JSONB,
                company_intel JSONB,
                tracking_since TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                notes TEXT,
                UNIQUE(user_id, url)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tracked_user_id ON tracked_competitors(user_id)
        """)
        
        # 4. Discovered Competitors
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discovered_competitors (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                url VARCHAR(500) NOT NULL,
                domain VARCHAR(255),
                name VARCHAR(255),
                discovery_source VARCHAR(100),
                relevance_score DECIMAL(5,2),
                status VARCHAR(50) DEFAULT 'new',
                company_intel JSONB,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                UNIQUE(user_id, url)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_discovered_user_id ON discovered_competitors(user_id)
        """)
        
        # 5. Agent Insights (historical)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_insights (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                analysis_id INTEGER REFERENCES analyses(id),
                agent_id VARCHAR(50) NOT NULL,
                agent_name VARCHAR(100),
                insight_type VARCHAR(50),
                priority VARCHAR(20),
                message TEXT NOT NULL,
                data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_insights_user_id ON agent_insights(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_insights_agent_id ON agent_insights(agent_id)
        """)
        
        conn.commit()
        logger.info("✅ Unified context tables initialized")
        return True
        
    except Exception as e:
        logger.error(f"Failed to init unified context tables: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# DATABASE HELPERS
# ============================================================================

def connect_db():
    """Get database connection"""
    if not DATABASE_URL:
        return None
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None


# ============================================================================
# PROFILE MANAGEMENT
# ============================================================================

def save_user_profile(
    user_id: str,
    url: str,
    industry: str = None,
    market: str = None,
    known_competitors: List[str] = None,
    **kwargs
) -> bool:
    """Save or update user profile"""
    conn = connect_db()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_profiles (user_id, url, industry, market, known_competitors, preferences)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                url = EXCLUDED.url,
                industry = EXCLUDED.industry,
                market = EXCLUDED.market,
                known_competitors = EXCLUDED.known_competitors,
                preferences = user_profiles.preferences || EXCLUDED.preferences,
                updated_at = CURRENT_TIMESTAMP
        """, (
            user_id, 
            url, 
            industry, 
            market, 
            known_competitors or [],
            json.dumps(kwargs.get('preferences', {}))
        ))
        conn.commit()
        logger.info(f"✅ Saved profile for {user_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to save profile: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user profile"""
    conn = connect_db()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT url, industry, market, known_competitors, revenue_estimate, 
                   company_size, goals, preferences, created_at, updated_at
            FROM user_profiles
            WHERE user_id = %s
        """, (user_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                'user_id': user_id,
                'url': row[0],
                'industry': row[1],
                'market': row[2],
                'known_competitors': row[3] or [],
                'revenue_estimate': float(row[4]) if row[4] else None,
                'company_size': row[5],
                'goals': row[6] or [],
                'preferences': row[7] or {},
                'created_at': row[8].isoformat() if row[8] else None,
                'updated_at': row[9].isoformat() if row[9] else None
            }
        return None
    except Exception as e:
        logger.error(f"Failed to get profile: {e}")
        return None
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# ANALYSIS HISTORY
# ============================================================================

def save_analysis(
    user_id: str,
    url: str,
    score: int,
    ranking: int = 1,
    total_competitors: int = 1,
    revenue_at_risk: float = 0,
    rasm_score: int = 0,
    benchmark: Dict = None,
    threats: List = None,
    opportunities: List = None,
    action_plan: Dict = None,
    raw_results: Dict = None,
    duration_seconds: float = 0
) -> Optional[int]:
    """Save analysis result, return analysis ID"""
    conn = connect_db()
    if not conn:
        return None
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO analyses (
                user_id, url, score, ranking, total_competitors,
                revenue_at_risk, rasm_score, benchmark, threats,
                opportunities, action_plan, raw_results, duration_seconds
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id, url, score, ranking, total_competitors,
            revenue_at_risk, rasm_score,
            json.dumps(benchmark or {}),
            json.dumps(threats or []),
            json.dumps(opportunities or []),
            json.dumps(action_plan or {}),
            json.dumps(raw_results or {}),
            duration_seconds
        ))
        
        analysis_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"✅ Saved analysis {analysis_id} for {user_id}")
        return analysis_id
    except Exception as e:
        logger.error(f"Failed to save analysis: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()


def get_recent_analyses(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent analyses for user"""
    conn = connect_db()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, url, score, ranking, total_competitors, revenue_at_risk,
                   rasm_score, benchmark, threats, opportunities, action_plan,
                   duration_seconds, created_at
            FROM analyses
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, limit))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'url': row[1],
                'score': row[2],
                'ranking': row[3],
                'total_competitors': row[4],
                'revenue_at_risk': float(row[5]) if row[5] else 0,
                'rasm_score': row[6],
                'benchmark': row[7] or {},
                'threats': row[8] or [],
                'opportunities': row[9] or [],
                'action_plan': row[10] or {},
                'duration_seconds': float(row[11]) if row[11] else 0,
                'created_at': row[12].isoformat() if row[12] else None
            })
        return results
    except Exception as e:
        logger.error(f"Failed to get analyses: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# TRACKED COMPETITORS (RADAR)
# ============================================================================

def add_tracked_competitor(
    user_id: str,
    url: str,
    domain: str = None,
    name: str = None,
    **kwargs
) -> bool:
    """Add competitor to tracking (Radar)"""
    conn = connect_db()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tracked_competitors (
                user_id, url, domain, name, business_id, industry,
                last_score, last_analysis, company_intel
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, url) DO UPDATE SET
                name = COALESCE(EXCLUDED.name, tracked_competitors.name),
                last_score = COALESCE(EXCLUDED.last_score, tracked_competitors.last_score),
                last_analysis = COALESCE(EXCLUDED.last_analysis, tracked_competitors.last_analysis),
                company_intel = COALESCE(EXCLUDED.company_intel, tracked_competitors.company_intel),
                last_checked = CURRENT_TIMESTAMP,
                is_active = TRUE
        """, (
            user_id, url, domain, name,
            kwargs.get('business_id'),
            kwargs.get('industry'),
            kwargs.get('last_score'),
            json.dumps(kwargs.get('last_analysis', {})),
            json.dumps(kwargs.get('company_intel', {}))
        ))
        conn.commit()
        logger.info(f"✅ Tracked competitor: {url}")
        return True
    except Exception as e:
        logger.error(f"Failed to track competitor: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_tracked_competitors(user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
    """Get tracked competitors for user"""
    conn = connect_db()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, url, domain, name, business_id, industry,
                   last_score, last_analysis, company_intel, 
                   tracking_since, last_checked, notes
            FROM tracked_competitors
            WHERE user_id = %s
        """
        if active_only:
            query += " AND is_active = TRUE"
        query += " ORDER BY last_checked DESC NULLS LAST"
        
        cursor.execute(query, (user_id,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'url': row[1],
                'domain': row[2],
                'name': row[3],
                'business_id': row[4],
                'industry': row[5],
                'last_score': row[6],
                'last_analysis': row[7] or {},
                'company_intel': row[8] or {},
                'tracking_since': row[9].isoformat() if row[9] else None,
                'last_checked': row[10].isoformat() if row[10] else None,
                'notes': row[11]
            })
        return results
    except Exception as e:
        logger.error(f"Failed to get tracked competitors: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# DISCOVERED COMPETITORS
# ============================================================================

def save_discovered_competitor(
    user_id: str,
    url: str,
    domain: str = None,
    name: str = None,
    discovery_source: str = 'scout',
    relevance_score: float = 0,
    company_intel: Dict = None
) -> bool:
    """Save discovered competitor"""
    conn = connect_db()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO discovered_competitors (
                user_id, url, domain, name, discovery_source,
                relevance_score, company_intel
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id, url) DO UPDATE SET
                relevance_score = GREATEST(discovered_competitors.relevance_score, EXCLUDED.relevance_score),
                company_intel = COALESCE(EXCLUDED.company_intel, discovered_competitors.company_intel)
        """, (
            user_id, url, domain, name, discovery_source,
            relevance_score, json.dumps(company_intel or {})
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save discovered competitor: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_discovered_competitors(
    user_id: str, 
    status: str = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get discovered competitors"""
    conn = connect_db()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, url, domain, name, discovery_source, relevance_score,
                   status, company_intel, discovered_at, reviewed_at
            FROM discovered_competitors
            WHERE user_id = %s
        """
        params = [user_id]
        
        if status:
            query += " AND status = %s"
            params.append(status)
        
        query += " ORDER BY relevance_score DESC, discovered_at DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'url': row[1],
                'domain': row[2],
                'name': row[3],
                'discovery_source': row[4],
                'relevance_score': float(row[5]) if row[5] else 0,
                'status': row[6],
                'company_intel': row[7] or {},
                'discovered_at': row[8].isoformat() if row[8] else None,
                'reviewed_at': row[9].isoformat() if row[9] else None
            })
        return results
    except Exception as e:
        logger.error(f"Failed to get discovered competitors: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


def update_discovered_status(user_id: str, url: str, status: str) -> bool:
    """Update discovered competitor status (new/reviewed/tracking/ignored)"""
    conn = connect_db()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE discovered_competitors
            SET status = %s, reviewed_at = CURRENT_TIMESTAMP
            WHERE user_id = %s AND url = %s
        """, (status, user_id, url))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to update status: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# AGENT INSIGHTS
# ============================================================================

def save_agent_insight(
    user_id: str,
    agent_id: str,
    message: str,
    agent_name: str = None,
    insight_type: str = None,
    priority: str = 'medium',
    data: Dict = None,
    analysis_id: int = None
) -> bool:
    """Save agent insight for historical tracking"""
    conn = connect_db()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO agent_insights (
                user_id, analysis_id, agent_id, agent_name,
                insight_type, priority, message, data
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id, analysis_id, agent_id, agent_name,
            insight_type, priority, message, json.dumps(data or {})
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to save insight: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()
        conn.close()


def get_agent_insights(
    user_id: str,
    agent_id: str = None,
    limit: int = 50,
    days: int = 30
) -> List[Dict[str, Any]]:
    """Get historical agent insights"""
    conn = connect_db()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, analysis_id, agent_id, agent_name, insight_type,
                   priority, message, data, created_at
            FROM agent_insights
            WHERE user_id = %s AND created_at > NOW() - INTERVAL '%s days'
        """
        params = [user_id, days]
        
        if agent_id:
            query += " AND agent_id = %s"
            params.append(agent_id)
        
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'analysis_id': row[1],
                'agent_id': row[2],
                'agent_name': row[3],
                'insight_type': row[4],
                'priority': row[5],
                'message': row[6],
                'data': row[7] or {},
                'created_at': row[8].isoformat() if row[8] else None
            })
        return results
    except Exception as e:
        logger.error(f"Failed to get insights: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


# ============================================================================
# UNIFIED CONTEXT - THE MAIN FUNCTION
# ============================================================================

def get_unified_context(user_id: str) -> UnifiedContext:
    """
    Get complete unified context for AI agents.
    This is the main function that aggregates all data sources.
    """
    context = UnifiedContext(user_id=user_id)
    
    # 1. User Profile
    context.profile = get_user_profile(user_id)
    
    # 2. Recent Analyses (last 10)
    context.recent_analyses = get_recent_analyses(user_id, limit=10)
    
    # 3. Tracked Competitors (Radar)
    context.tracked_competitors = get_tracked_competitors(user_id)
    
    # 4. Discovered Competitors
    context.discovered_competitors = get_discovered_competitors(user_id, limit=20)
    
    # 5. Historical Insights (last 30 days)
    context.historical_insights = get_agent_insights(user_id, days=30, limit=100)
    
    # 6. Calculate Trends
    context.trends = calculate_trends(context)
    
    logger.info(f"📊 Unified context for {user_id}: "
                f"{len(context.recent_analyses)} analyses, "
                f"{len(context.tracked_competitors)} tracked, "
                f"{len(context.discovered_competitors)} discovered")
    
    return context


def calculate_trends(context: UnifiedContext) -> Dict[str, Any]:
    """Calculate trends from historical data"""
    trends = {}
    
    analyses = context.recent_analyses or []
    if len(analyses) >= 2:
        # Score trend
        latest_score = analyses[0].get('score', 0)
        previous_score = analyses[1].get('score', 0)
        trends['score_change'] = latest_score - previous_score
        trends['score_direction'] = 'up' if trends['score_change'] > 0 else 'down' if trends['score_change'] < 0 else 'stable'
        
        # Revenue risk trend
        latest_risk = analyses[0].get('revenue_at_risk', 0)
        previous_risk = analyses[1].get('revenue_at_risk', 0)
        trends['risk_change'] = latest_risk - previous_risk
    
    # Find most mentioned threat/opportunity from insights
    insights = context.historical_insights or []
    threat_counts = {}
    opportunity_counts = {}
    
    for insight in insights:
        insight_type = insight.get('insight_type', '')
        message = insight.get('message', '')[:50]  # First 50 chars as key
        
        if insight_type == 'threat':
            threat_counts[message] = threat_counts.get(message, 0) + 1
        elif insight_type == 'opportunity':
            opportunity_counts[message] = opportunity_counts.get(message, 0) + 1
    
    if threat_counts:
        trends['top_threat'] = max(threat_counts, key=threat_counts.get)
    if opportunity_counts:
        trends['best_opportunity'] = max(opportunity_counts, key=opportunity_counts.get)
    
    # Competitor movement
    tracked = context.tracked_competitors or []
    if tracked:
        improving = [c for c in tracked if c.get('last_score', 0) > 50]
        trends['competitors_improving'] = len(improving)
        trends['total_tracked'] = len(tracked)
    
    return trends


# ============================================================================
# CONTEXT API HELPERS
# ============================================================================

def context_to_agent_system_prompt(context: UnifiedContext, agent_id: str) -> str:
    """
    Generate agent-specific system prompt addition based on context.
    Each agent gets relevant parts of the context.
    """
    base_context = context.to_agent_prompt()
    
    agent_specific = []
    
    if agent_id == 'scout':
        # Scout cares about discovered vs tracked
        tracked_urls = {c.get('url') for c in context.tracked_competitors}
        new_discoveries = [c for c in context.discovered_competitors 
                         if c.get('url') not in tracked_urls and c.get('status') == 'new']
        if new_discoveries:
            agent_specific.append(f"\n## New Discoveries Not Yet Tracked: {len(new_discoveries)}")
    
    elif agent_id == 'analyst':
        # Analyst cares about score history
        if context.recent_analyses:
            scores = [a.get('score', 0) for a in context.recent_analyses]
            agent_specific.append(f"\n## Score History: {scores[:5]}")
            agent_specific.append(f"Average: {sum(scores)/len(scores):.1f}")
    
    elif agent_id == 'guardian':
        # Guardian cares about risk trends
        if context.trends.get('risk_change'):
            change = context.trends['risk_change']
            agent_specific.append(f"\n## Risk Trend: €{change:+,.0f} since last analysis")
    
    elif agent_id == 'prospector':
        # Prospector cares about past opportunities
        past_opps = [i for i in context.historical_insights 
                    if i.get('insight_type') == 'opportunity']
        if past_opps:
            agent_specific.append(f"\n## Past Opportunities Identified: {len(past_opps)}")
    
    elif agent_id == 'strategist':
        # Strategist needs the big picture
        agent_specific.append(f"\n## Strategic Overview")
        if context.trends.get('score_direction'):
            agent_specific.append(f"- Trend: {context.trends['score_direction']}")
        if context.trends.get('competitors_improving'):
            agent_specific.append(f"- Competitors improving: {context.trends['competitors_improving']}/{context.trends.get('total_tracked', 0)}")
    
    elif agent_id == 'planner':
        # Planner cares about past action plans
        if context.recent_analyses:
            last_plan = context.recent_analyses[0].get('action_plan', {})
            if last_plan:
                total_actions = last_plan.get('total_actions', 0)
                agent_specific.append(f"\n## Previous Plan: {total_actions} actions")
    
    return base_context + "\n".join(agent_specific)
