"""
Analysis History Database Module
Production-ready database integration for storing analysis results
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
import json
import asyncpg
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AnalysisRecord:
    """Single analysis record"""
    id: int
    user_id: str
    analysis_type: str
    url: str
    company_name: Optional[str]
    status: str
    progress: int
    created_at: datetime
    completed_at: Optional[datetime]
    score: Optional[int] = None
    competitors_count: Optional[int] = None


@dataclass
class UserUsage:
    """User usage statistics"""
    user_id: str
    single_analyses_this_month: int
    discoveries_this_month: int
    total_single_analyses: int
    total_discoveries: int
    total_competitors_analyzed: int
    single_analysis_limit: int
    discovery_limit: int


class AnalysisHistoryDB:
    """Database manager for analysis history"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Initialize database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("✅ Analysis history database pool created")
            
            # Run schema initialization
            await self.initialize_schema()
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to analysis history DB: {e}")
            raise
    
    async def disconnect(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database pool closed")
    
    async def initialize_schema(self):
        """Initialize database schema if not exists"""
        schema_file = "/home/claude/analysis_history_schema.sql"
        try:
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
            
            async with self.pool.acquire() as conn:
                await conn.execute(schema_sql)
            
            logger.info("✅ Database schema initialized")
        except FileNotFoundError:
            logger.warning("⚠️ Schema file not found, skipping initialization")
        except Exception as e:
            logger.error(f"❌ Schema initialization failed: {e}")
    
    # ========================================================================
    # QUOTA CHECKING
    # ========================================================================
    
    async def check_user_limit(
        self,
        user_id: str,
        analysis_type: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if user can perform analysis.
        Returns (can_proceed, error_message)
        """
        try:
            async with self.pool.acquire() as conn:
                can_proceed = await conn.fetchval(
                    "SELECT check_user_analysis_limit($1, $2)",
                    user_id, analysis_type
                )
                
                if not can_proceed:
                    # Get current usage for error message
                    usage = await conn.fetchrow(
                        """SELECT 
                            single_analyses_this_month,
                            discoveries_this_month,
                            single_analysis_limit,
                            discovery_limit
                        FROM user_analysis_usage 
                        WHERE user_id = $1""",
                        user_id
                    )
                    
                    if usage:
                        if analysis_type == 'single':
                            limit = usage['single_analysis_limit']
                            current = usage['single_analyses_this_month']
                        else:
                            limit = usage['discovery_limit']
                            current = usage['discoveries_this_month']
                        
                        return False, f"Monthly limit reached: {current}/{limit} {analysis_type} analyses used"
                    else:
                        return False, "Usage data not found"
                
                return True, None
                
        except Exception as e:
            logger.error(f"Error checking user limit: {e}")
            return True, None  # Fail open
    
    async def increment_usage(
        self,
        user_id: str,
        analysis_type: str,
        competitors_count: int = 0
    ):
        """Increment user usage counters"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT increment_user_usage($1, $2, $3)",
                    user_id, analysis_type, competitors_count
                )
        except Exception as e:
            logger.error(f"Error incrementing usage: {e}")
    
    async def get_user_usage(self, user_id: str) -> Optional[UserUsage]:
        """Get user usage statistics"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT * FROM user_analysis_usage 
                    WHERE user_id = $1""",
                    user_id
                )
                
                if row:
                    return UserUsage(**dict(row))
                return None
                
        except Exception as e:
            logger.error(f"Error getting user usage: {e}")
            return None
    
    # ========================================================================
    # SINGLE ANALYSIS STORAGE
    # ========================================================================
    
    async def save_single_analysis(
        self,
        user_id: str,
        url: str,
        company_name: Optional[str],
        language: str,
        analysis_result: Dict[str, Any]
    ) -> int:
        """
        Save single analysis result to database.
        Returns analysis_id
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Create analysis record
                    analysis_id = await conn.fetchval(
                        """INSERT INTO analyses (
                            user_id, analysis_type, url, company_name, 
                            language, status, completed_at
                        ) VALUES ($1, 'single', $2, $3, $4, 'completed', NOW())
                        RETURNING id""",
                        user_id, url, company_name, language
                    )
                    
                    # Extract scores
                    basic = analysis_result.get('basic_analysis', {})
                    score_breakdown = basic.get('score_breakdown', {})
                    
                    # Save analysis result
                    await conn.execute(
                        """INSERT INTO analysis_results (
                            analysis_id, url, digital_maturity_score,
                            security_score, seo_score, content_score,
                            technical_score, mobile_score, social_score,
                            performance_score, basic_analysis, technical_audit,
                            content_analysis, seo_analysis, social_analysis,
                            ux_analysis, competitive_analysis, ai_analysis,
                            smart_actions, framework_detected, has_spa,
                            used_playwright
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                            $11, $12, $13, $14, $15, $16, $17, $18, $19,
                            $20, $21, $22
                        )""",
                        analysis_id,
                        url,
                        basic.get('digital_maturity_score'),
                        score_breakdown.get('security', 0),
                        score_breakdown.get('seo_basics', 0),
                        score_breakdown.get('content', 0),
                        score_breakdown.get('technical', 0),
                        score_breakdown.get('mobile', 0),
                        score_breakdown.get('social', 0),
                        score_breakdown.get('performance', 0),
                        json.dumps(analysis_result.get('basic_analysis')),
                        json.dumps(analysis_result.get('technical_audit')),
                        json.dumps(analysis_result.get('content_analysis')),
                        json.dumps(analysis_result.get('seo_analysis')),
                        json.dumps(analysis_result.get('social_analysis')),
                        json.dumps(analysis_result.get('ux_analysis')),
                        json.dumps(analysis_result.get('competitive_analysis')),
                        json.dumps(analysis_result.get('ai_analysis')),
                        json.dumps(analysis_result.get('smart_actions')),
                        basic.get('framework_detected'),
                        basic.get('has_spa', False),
                        analysis_result.get('used_playwright', False)
                    )
                    
                    # Increment usage
                    await self.increment_usage(user_id, 'single')
                    
                    logger.info(f"✅ Saved single analysis: {analysis_id} for {user_id}")
                    return analysis_id
                    
        except Exception as e:
            logger.error(f"❌ Error saving single analysis: {e}")
            raise
    
    # ========================================================================
    # COMPETITOR DISCOVERY STORAGE
    # ========================================================================
    
    async def save_competitor_discovery(
        self,
        user_id: str,
        url: str,
        industry: str,
        country_code: str,
        max_competitors: int,
        search_terms: List[str],
        search_provider: str,
        competitors: List[Dict[str, Any]],
        summary: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Save competitor discovery results.
        Returns analysis_id
        """
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Create main analysis record
                    analysis_id = await conn.fetchval(
                        """INSERT INTO analyses (
                            user_id, analysis_type, url, industry,
                            country_code, status, completed_at
                        ) VALUES ($1, 'discovery', $2, $3, $4, 'completed', NOW())
                        RETURNING id""",
                        user_id, url, industry, country_code
                    )
                    
                    # Create discovery record
                    discovery_id = await conn.fetchval(
                        """INSERT INTO competitor_discoveries (
                            analysis_id, max_competitors, competitors_found,
                            competitors_analyzed, search_terms, search_provider,
                            summary
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        RETURNING id""",
                        analysis_id,
                        max_competitors,
                        len(competitors),
                        len([c for c in competitors if c.get('basic_analysis')]),
                        json.dumps(search_terms),
                        search_provider,
                        json.dumps(summary) if summary else None
                    )
                    
                    # Save each competitor result
                    for idx, comp in enumerate(competitors, 1):
                        basic = comp.get('basic_analysis', {})
                        score_breakdown = basic.get('score_breakdown', {})
                        
                        await conn.execute(
                            """INSERT INTO competitor_results (
                                discovery_id, domain, url, company_name,
                                digital_maturity_score, security_score,
                                seo_score, content_score, technical_score,
                                mobile_score, social_score, performance_score,
                                basic_analysis, technical_audit, content_analysis,
                                detailed_analysis, rank_in_results, analyzed_at
                            ) VALUES (
                                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                                $11, $12, $13, $14, $15, $16, $17, NOW()
                            )""",
                            discovery_id,
                            comp.get('domain', ''),
                            comp.get('url', ''),
                            comp.get('company_name'),
                            basic.get('digital_maturity_score'),
                            score_breakdown.get('security', 0),
                            score_breakdown.get('seo_basics', 0),
                            score_breakdown.get('content', 0),
                            score_breakdown.get('technical', 0),
                            score_breakdown.get('mobile', 0),
                            score_breakdown.get('social', 0),
                            score_breakdown.get('performance', 0),
                            json.dumps(comp.get('basic_analysis')),
                            json.dumps(comp.get('technical_audit')),
                            json.dumps(comp.get('content_analysis')),
                            json.dumps(comp.get('detailed_analysis')),
                            idx
                        )
                    
                    # Increment usage
                    await self.increment_usage(
                        user_id, 
                        'discovery', 
                        len(competitors)
                    )
                    
                    logger.info(
                        f"✅ Saved competitor discovery: {analysis_id} "
                        f"({len(competitors)} competitors) for {user_id}"
                    )
                    return analysis_id
                    
        except Exception as e:
            logger.error(f"❌ Error saving competitor discovery: {e}")
            raise
    
    # ========================================================================
    # RETRIEVAL
    # ========================================================================
    
    async def get_user_history(
        self,
        user_id: str,
        limit: int = 20,
        analysis_type: Optional[str] = None
    ) -> List[AnalysisRecord]:
        """Get user's analysis history"""
        try:
            async with self.pool.acquire() as conn:
                query = """
                    SELECT * FROM recent_analyses 
                    WHERE user_id = $1
                """
                params = [user_id]
                
                if analysis_type:
                    query += " AND analysis_type = $2"
                    params.append(analysis_type)
                
                query += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1)
                params.append(limit)
                
                rows = await conn.fetch(query, *params)
                
                return [
                    AnalysisRecord(
                        id=row['id'],
                        user_id=row['user_id'],
                        analysis_type=row['analysis_type'],
                        url=row['url'],
                        company_name=row['company_name'],
                        status=row['status'],
                        progress=100,
                        created_at=row['created_at'],
                        completed_at=row['completed_at'],
                        score=row.get('score'),
                        competitors_count=row.get('competitors_count')
                    )
                    for row in rows
                ]
                
        except Exception as e:
            logger.error(f"Error getting user history: {e}")
            return []
    
    async def get_analysis_details(
        self,
        analysis_id: int,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get full analysis details"""
        try:
            async with self.pool.acquire() as conn:
                # Verify ownership
                owner = await conn.fetchval(
                    "SELECT user_id FROM analyses WHERE id = $1",
                    analysis_id
                )
                
                if owner != user_id:
                    logger.warning(f"Unauthorized access attempt: {user_id} -> {analysis_id}")
                    return None
                
                # Get analysis
                analysis = await conn.fetchrow(
                    "SELECT * FROM analyses WHERE id = $1",
                    analysis_id
                )
                
                if not analysis:
                    return None
                
                result = dict(analysis)
                
                # Get type-specific data
                if analysis['analysis_type'] == 'single':
                    details = await conn.fetchrow(
                        "SELECT * FROM analysis_results WHERE analysis_id = $1",
                        analysis_id
                    )
                    if details:
                        result['result'] = {
                            'basic_analysis': json.loads(details['basic_analysis']) if details['basic_analysis'] else None,
                            'technical_audit': json.loads(details['technical_audit']) if details['technical_audit'] else None,
                            'content_analysis': json.loads(details['content_analysis']) if details['content_analysis'] else None,
                            'ai_analysis': json.loads(details['ai_analysis']) if details['ai_analysis'] else None,
                            'smart_actions': json.loads(details['smart_actions']) if details['smart_actions'] else None
                        }
                
                elif analysis['analysis_type'] == 'discovery':
                    # Get discovery metadata
                    discovery = await conn.fetchrow(
                        "SELECT * FROM competitor_discoveries WHERE analysis_id = $1",
                        analysis_id
                    )
                    
                    if discovery:
                        # Get all competitors
                        competitors = await conn.fetch(
                            """SELECT * FROM competitor_results 
                            WHERE discovery_id = $1 
                            ORDER BY rank_in_results""",
                            discovery['id']
                        )
                        
                        result['discovery'] = dict(discovery)
                        result['competitors'] = [
                            {
                                'domain': c['domain'],
                                'url': c['url'],
                                'company_name': c['company_name'],
                                'digital_maturity_score': c['digital_maturity_score'],
                                'basic_analysis': json.loads(c['basic_analysis']) if c['basic_analysis'] else None
                            }
                            for c in competitors
                        ]
                
                return result
                
        except Exception as e:
            logger.error(f"Error getting analysis details: {e}")
            return None
