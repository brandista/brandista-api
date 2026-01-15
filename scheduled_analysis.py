#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scheduled Analysis System for Brandista Growth Engine
Runs automated recurring analyses and sends threat alerts

Features:
- Daily/weekly scheduled analyses for tracked companies
- Email alerts when new threats detected
- Score change notifications
- Historical trend tracking
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

# APScheduler for background jobs
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False
    logging.warning("APScheduler not installed. Install with: pip install apscheduler")

# Email notifications
from email_notifications import send_email, ADMIN_EMAIL

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

class ScheduleFrequency(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

@dataclass
class ScheduledAnalysisConfig:
    """Configuration for a scheduled analysis"""
    user_id: str
    url: str
    company_name: Optional[str]
    frequency: ScheduleFrequency
    notify_on_threats: bool = True
    notify_on_score_change: bool = True
    score_change_threshold: int = 5  # Notify if score changes by this much
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None

# ============================================================================
# SCHEDULED ANALYSIS MANAGER
# ============================================================================

class ScheduledAnalysisManager:
    """Manages scheduled/recurring analyses"""

    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self.scheduler: Optional[AsyncIOScheduler] = None
        self.pool = None  # asyncpg pool
        self._orchestrator = None

    async def initialize(self):
        """Initialize the scheduler and database connection"""
        if not SCHEDULER_AVAILABLE:
            logger.error("APScheduler not available, scheduled analyses disabled")
            return False

        try:
            # Initialize scheduler
            self.scheduler = AsyncIOScheduler()

            # Initialize database pool
            if self.database_url:
                import asyncpg
                self.pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=1,
                    max_size=5,
                    command_timeout=120
                )
                logger.info("Scheduled analysis database pool created")

                # Create tables if not exist
                await self._create_tables()

            # Add default jobs
            await self._setup_default_jobs()

            # Start scheduler
            self.scheduler.start()
            logger.info("Scheduled analysis manager initialized and running")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize scheduled analysis manager: {e}")
            return False

    async def shutdown(self):
        """Shutdown scheduler and connections"""
        if self.scheduler:
            self.scheduler.shutdown()
        if self.pool:
            await self.pool.close()
        logger.info("Scheduled analysis manager shut down")

    async def _create_tables(self):
        """Create database tables for scheduled analyses"""
        if not self.pool:
            return

        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_analyses (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    url VARCHAR(1024) NOT NULL,
                    company_name VARCHAR(255),
                    frequency VARCHAR(20) DEFAULT 'weekly',
                    notify_on_threats BOOLEAN DEFAULT TRUE,
                    notify_on_score_change BOOLEAN DEFAULT TRUE,
                    score_change_threshold INTEGER DEFAULT 5,
                    enabled BOOLEAN DEFAULT TRUE,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    last_score INTEGER,
                    last_threats_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, url)
                );

                CREATE INDEX IF NOT EXISTS idx_scheduled_user ON scheduled_analyses(user_id);
                CREATE INDEX IF NOT EXISTS idx_scheduled_enabled ON scheduled_analyses(enabled);
                CREATE INDEX IF NOT EXISTS idx_scheduled_next_run ON scheduled_analyses(next_run);
            """)

            # Analysis history for trends
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS analysis_history_trends (
                    id SERIAL PRIMARY KEY,
                    scheduled_id INTEGER REFERENCES scheduled_analyses(id),
                    url VARCHAR(1024) NOT NULL,
                    score INTEGER,
                    threats_count INTEGER DEFAULT 0,
                    revenue_at_risk DECIMAL(15,2),
                    analyzed_at TIMESTAMP DEFAULT NOW(),
                    raw_result JSONB
                );

                CREATE INDEX IF NOT EXISTS idx_history_scheduled ON analysis_history_trends(scheduled_id);
                CREATE INDEX IF NOT EXISTS idx_history_url ON analysis_history_trends(url);
                CREATE INDEX IF NOT EXISTS idx_history_date ON analysis_history_trends(analyzed_at);
            """)

            logger.info("Scheduled analysis tables created/verified")

    async def _setup_default_jobs(self):
        """Setup default scheduled jobs"""
        if not self.scheduler:
            return

        # Run scheduled analyses check every hour
        self.scheduler.add_job(
            self._process_due_analyses,
            IntervalTrigger(hours=1),
            id='process_due_analyses',
            replace_existing=True
        )

        # Daily summary email at 8:00 AM
        self.scheduler.add_job(
            self._send_daily_summary,
            CronTrigger(hour=8, minute=0),
            id='daily_summary',
            replace_existing=True
        )

        logger.info("Default scheduled jobs configured")

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def add_scheduled_analysis(
        self,
        user_id: str,
        url: str,
        company_name: Optional[str] = None,
        frequency: str = "weekly",
        notify_on_threats: bool = True,
        notify_on_score_change: bool = True
    ) -> Optional[int]:
        """
        Add a new scheduled analysis for a user.
        Returns the scheduled analysis ID.
        """
        if not self.pool:
            logger.warning("Database not available for scheduled analysis")
            return None

        try:
            async with self.pool.acquire() as conn:
                # Calculate next run based on frequency
                next_run = self._calculate_next_run(frequency)

                result = await conn.fetchrow("""
                    INSERT INTO scheduled_analyses
                    (user_id, url, company_name, frequency, notify_on_threats,
                     notify_on_score_change, next_run)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (user_id, url)
                    DO UPDATE SET
                        frequency = EXCLUDED.frequency,
                        notify_on_threats = EXCLUDED.notify_on_threats,
                        notify_on_score_change = EXCLUDED.notify_on_score_change,
                        enabled = TRUE,
                        updated_at = NOW()
                    RETURNING id
                """, user_id, url, company_name, frequency, notify_on_threats,
                    notify_on_score_change, next_run)

                logger.info(f"Scheduled analysis created/updated: {user_id} -> {url} ({frequency})")
                return result['id']

        except Exception as e:
            logger.error(f"Failed to add scheduled analysis: {e}")
            return None

    async def remove_scheduled_analysis(self, user_id: str, url: str) -> bool:
        """Remove/disable a scheduled analysis"""
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE scheduled_analyses
                    SET enabled = FALSE, updated_at = NOW()
                    WHERE user_id = $1 AND url = $2
                """, user_id, url)
            return True
        except Exception as e:
            logger.error(f"Failed to remove scheduled analysis: {e}")
            return False

    async def get_user_scheduled_analyses(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all scheduled analyses for a user"""
        if not self.pool:
            return []

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM scheduled_analyses
                    WHERE user_id = $1 AND enabled = TRUE
                    ORDER BY created_at DESC
                """, user_id)

                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get scheduled analyses: {e}")
            return []

    async def get_trend_data(
        self,
        url: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get historical trend data for a URL"""
        if not self.pool:
            return []

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        score,
                        threats_count,
                        revenue_at_risk,
                        analyzed_at
                    FROM analysis_history_trends
                    WHERE url = $1
                    AND analyzed_at > NOW() - INTERVAL '%s days'
                    ORDER BY analyzed_at ASC
                """ % days, url)

                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get trend data: {e}")
            return []

    # ========================================================================
    # INTERNAL: Analysis Processing
    # ========================================================================

    async def _process_due_analyses(self):
        """Process all analyses that are due to run"""
        if not self.pool:
            return

        logger.info("Checking for due scheduled analyses...")

        try:
            async with self.pool.acquire() as conn:
                # Get all due analyses
                due_analyses = await conn.fetch("""
                    SELECT * FROM scheduled_analyses
                    WHERE enabled = TRUE
                    AND (next_run IS NULL OR next_run <= NOW())
                    ORDER BY next_run ASC
                    LIMIT 10
                """)

                if not due_analyses:
                    logger.debug("No scheduled analyses due")
                    return

                logger.info(f"Found {len(due_analyses)} due analyses to process")

                for analysis in due_analyses:
                    await self._run_single_analysis(dict(analysis))

        except Exception as e:
            logger.error(f"Error processing due analyses: {e}")

    async def _run_single_analysis(self, config: Dict[str, Any]):
        """Run a single scheduled analysis"""
        url = config['url']
        user_id = config['user_id']
        scheduled_id = config['id']

        logger.info(f"Running scheduled analysis for {url} (user: {user_id})")

        try:
            # Import orchestrator
            from agents import get_orchestrator
            orchestrator = get_orchestrator()

            # Run the analysis
            result = await orchestrator.run_analysis(
                target_url=url,
                competitor_urls=[],
                industry=None,
                language="fi"
            )

            # Extract key metrics
            score = result.get('your_score', 0)
            threats_count = len(result.get('competitor_threats', []))
            revenue_at_risk = result.get('revenue_at_risk', 0)

            # Get previous values for comparison
            last_score = config.get('last_score')
            last_threats = config.get('last_threats_count', 0)

            # Save to history
            await self._save_analysis_result(
                scheduled_id=scheduled_id,
                url=url,
                score=score,
                threats_count=threats_count,
                revenue_at_risk=revenue_at_risk,
                raw_result=result
            )

            # Check for alerts
            if config.get('notify_on_threats') and threats_count > last_threats:
                new_threats = threats_count - last_threats
                await self._send_threat_alert(
                    user_id=user_id,
                    url=url,
                    company_name=config.get('company_name'),
                    new_threats_count=new_threats,
                    threats=result.get('competitor_threats', [])[:3]  # First 3
                )

            if config.get('notify_on_score_change') and last_score is not None:
                score_change = score - last_score
                threshold = config.get('score_change_threshold', 5)
                if abs(score_change) >= threshold:
                    await self._send_score_change_alert(
                        user_id=user_id,
                        url=url,
                        company_name=config.get('company_name'),
                        old_score=last_score,
                        new_score=score,
                        change=score_change
                    )

            # Update scheduled analysis record
            next_run = self._calculate_next_run(config['frequency'])
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE scheduled_analyses
                    SET last_run = NOW(),
                        next_run = $1,
                        last_score = $2,
                        last_threats_count = $3,
                        updated_at = NOW()
                    WHERE id = $4
                """, next_run, score, threats_count, scheduled_id)

            logger.info(f"Completed scheduled analysis for {url}: score={score}, threats={threats_count}")

        except Exception as e:
            logger.error(f"Failed to run scheduled analysis for {url}: {e}")

    async def _save_analysis_result(
        self,
        scheduled_id: int,
        url: str,
        score: int,
        threats_count: int,
        revenue_at_risk: float,
        raw_result: Dict[str, Any]
    ):
        """Save analysis result to history for trends"""
        if not self.pool:
            return

        try:
            import json
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO analysis_history_trends
                    (scheduled_id, url, score, threats_count, revenue_at_risk, raw_result)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, scheduled_id, url, score, threats_count, revenue_at_risk,
                    json.dumps(raw_result))
        except Exception as e:
            logger.error(f"Failed to save analysis result: {e}")

    def _calculate_next_run(self, frequency: str) -> datetime:
        """Calculate next run time based on frequency"""
        now = datetime.now()

        if frequency == "daily":
            # Next day at 6:00 AM
            next_run = now.replace(hour=6, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
        elif frequency == "weekly":
            # Next Monday at 6:00 AM
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0 and now.hour >= 6:
                days_until_monday = 7
            next_run = (now + timedelta(days=days_until_monday)).replace(
                hour=6, minute=0, second=0, microsecond=0
            )
        elif frequency == "monthly":
            # First day of next month at 6:00 AM
            if now.month == 12:
                next_run = now.replace(year=now.year + 1, month=1, day=1,
                                       hour=6, minute=0, second=0, microsecond=0)
            else:
                next_run = now.replace(month=now.month + 1, day=1,
                                       hour=6, minute=0, second=0, microsecond=0)
        else:
            # Default: 1 week
            next_run = now + timedelta(weeks=1)

        return next_run

    # ========================================================================
    # EMAIL ALERTS
    # ========================================================================

    async def _send_threat_alert(
        self,
        user_id: str,
        url: str,
        company_name: Optional[str],
        new_threats_count: int,
        threats: List[Dict[str, Any]]
    ):
        """Send email alert about new threats"""

        # Get user email from database
        user_email = await self._get_user_email(user_id)
        if not user_email:
            logger.warning(f"No email found for user {user_id}, skipping threat alert")
            return

        company_display = company_name or url

        # Build threat list HTML
        threats_html = ""
        for threat in threats:
            severity = threat.get('severity', 'medium')
            severity_color = {
                'critical': '#dc2626',
                'high': '#ea580c',
                'medium': '#eab308',
                'low': '#22c55e'
            }.get(severity, '#6b7280')

            threats_html += f"""
            <div style="padding: 12px; margin: 8px 0; background: #f8f9fa; border-left: 4px solid {severity_color}; border-radius: 4px;">
                <strong style="color: {severity_color};">{severity.upper()}</strong>: {threat.get('title', 'Tuntematon uhka')}
                <br><span style="color: #6b7280; font-size: 13px;">{threat.get('description', '')[:200]}</span>
            </div>
            """

        subject = f"Uusia uhkia havaittu: {company_display}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #dc2626 0%, #ea580c 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }}
                .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1 style="margin: 0;">Uusia uhkia havaittu</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">{new_threats_count} uutta uhkaa kohteelle {company_display}</p>
            </div>

            <div class="content">
                <p>Hei,</p>
                <p>Guardian-agentti havaitsi <strong>{new_threats_count} uutta uhkaa</strong> seurannassa olevalle sivustolle:</p>

                <div style="background: white; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <strong>Sivusto:</strong> {url}<br>
                    <strong>Yritys:</strong> {company_display}
                </div>

                <h3>Havaitut uhat:</h3>
                {threats_html}

                <p style="text-align: center;">
                    <a href="https://brandista.eu/growthengine/dashboard" class="button">Tarkastele analyysissa</a>
                </p>

                <p style="color: #6b7280; font-size: 13px; margin-top: 30px;">
                    Saat tämän viestin koska olet aktivoinut uhkailmoitukset tälle sivustolle.
                    Voit muuttaa asetuksia Brandista-dashboardissa.
                </p>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Uusia uhkia havaittu: {company_display}

        {new_threats_count} uutta uhkaa havaittu sivustolle {url}

        Tarkastele analyysissa: https://brandista.eu/growthengine/dashboard

        --
        Brandista Growth Engine
        """

        send_email(user_email, subject, html_body, text_body)
        logger.info(f"Threat alert sent to {user_email} for {url}")

    async def _send_score_change_alert(
        self,
        user_id: str,
        url: str,
        company_name: Optional[str],
        old_score: int,
        new_score: int,
        change: int
    ):
        """Send email alert about significant score change"""

        user_email = await self._get_user_email(user_id)
        if not user_email:
            return

        company_display = company_name or url
        direction = "nousi" if change > 0 else "laski"
        direction_en = "increased" if change > 0 else "decreased"
        color = "#22c55e" if change > 0 else "#dc2626"
        emoji = "+" if change > 0 else ""

        subject = f"Score-muutos: {company_display} ({emoji}{change})"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px 10px 0 0; text-align: center; }}
                .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px; }}
                .score-box {{ display: inline-block; padding: 20px 30px; background: white; border-radius: 12px; margin: 10px; text-align: center; }}
                .button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1 style="margin: 0;">Score-muutos havaittu</h1>
                <p style="margin: 10px 0 0 0; opacity: 0.9;">{company_display}</p>
            </div>

            <div class="content">
                <p>Hei,</p>
                <p>Sivustosi digitaalinen kypsyyspistemäärä {direction} merkittävästi:</p>

                <div style="text-align: center; margin: 30px 0;">
                    <div class="score-box">
                        <div style="font-size: 14px; color: #6b7280;">Aiempi</div>
                        <div style="font-size: 36px; font-weight: bold; color: #333;">{old_score}</div>
                    </div>
                    <span style="font-size: 24px; color: #9ca3af;">→</span>
                    <div class="score-box">
                        <div style="font-size: 14px; color: #6b7280;">Uusi</div>
                        <div style="font-size: 36px; font-weight: bold; color: {color};">{new_score}</div>
                    </div>
                </div>

                <div style="text-align: center; padding: 20px; background: white; border-radius: 12px; margin: 20px 0;">
                    <span style="font-size: 48px; font-weight: bold; color: {color};">{emoji}{change}</span>
                    <div style="color: #6b7280;">pistettä</div>
                </div>

                <p style="text-align: center;">
                    <a href="https://brandista.eu/growthengine/dashboard" class="button">Tarkastele muutoksia</a>
                </p>
            </div>
        </body>
        </html>
        """

        text_body = f"""
        Score-muutos: {company_display}

        Pistemäärä {direction}: {old_score} → {new_score} ({emoji}{change})

        Tarkastele: https://brandista.eu/growthengine/dashboard

        --
        Brandista Growth Engine
        """

        send_email(user_email, subject, html_body, text_body)
        logger.info(f"Score change alert sent to {user_email}")

    async def _send_daily_summary(self):
        """Send daily summary of all analyses"""
        logger.info("Generating daily summary email...")

        if not self.pool:
            return

        try:
            async with self.pool.acquire() as conn:
                # Get today's analyses
                analyses = await conn.fetch("""
                    SELECT
                        sa.url,
                        sa.company_name,
                        sa.user_id,
                        aht.score,
                        aht.threats_count,
                        aht.revenue_at_risk
                    FROM analysis_history_trends aht
                    JOIN scheduled_analyses sa ON sa.id = aht.scheduled_id
                    WHERE aht.analyzed_at > NOW() - INTERVAL '24 hours'
                    ORDER BY aht.analyzed_at DESC
                """)

                if not analyses:
                    logger.info("No analyses in last 24 hours, skipping summary")
                    return

                # Build summary email
                subject = f"Brandista Daily Summary: {len(analyses)} analysointia"

                rows_html = ""
                for a in analyses:
                    rows_html += f"""
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{a['company_name'] or a['url']}</td>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: center;">{a['score']}</td>
                        <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: center;">{a['threats_count']}</td>
                    </tr>
                    """

                html_body = f"""
                <!DOCTYPE html>
                <html>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #667eea;">Brandista Daily Summary</h2>
                    <p>{len(analyses)} analysointia suoritettu viimeisen 24 tunnin aikana:</p>

                    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                        <thead>
                            <tr style="background: #f3f4f6;">
                                <th style="padding: 10px; text-align: left;">Sivusto</th>
                                <th style="padding: 10px; text-align: center;">Score</th>
                                <th style="padding: 10px; text-align: center;">Uhat</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>

                    <p><a href="https://brandista.eu/growthengine/dashboard">Avaa Dashboard</a></p>
                </body>
                </html>
                """

                send_email(ADMIN_EMAIL, subject, html_body)
                logger.info(f"Daily summary sent: {len(analyses)} analyses")

        except Exception as e:
            logger.error(f"Failed to send daily summary: {e}")

    async def _get_user_email(self, user_id: str) -> Optional[str]:
        """Get user email from database"""
        if not self.pool:
            return None

        try:
            async with self.pool.acquire() as conn:
                # Try users table first
                result = await conn.fetchval("""
                    SELECT email FROM users WHERE id = $1 OR email = $1
                """, user_id)

                if result:
                    return result

                # user_id might be the email itself
                if '@' in user_id:
                    return user_id

                return None
        except Exception as e:
            logger.error(f"Failed to get user email: {e}")
            return None


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_manager: Optional[ScheduledAnalysisManager] = None

async def get_scheduled_manager() -> ScheduledAnalysisManager:
    """Get or create the scheduled analysis manager singleton"""
    global _manager
    if _manager is None:
        _manager = ScheduledAnalysisManager()
        await _manager.initialize()
    return _manager


# ============================================================================
# API ROUTES
# ============================================================================

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

scheduled_router = APIRouter(prefix="/api/v1/scheduled", tags=["Scheduled Analysis"])

class ScheduleRequest(BaseModel):
    url: str
    company_name: Optional[str] = None
    frequency: str = "weekly"  # daily, weekly, monthly
    notify_on_threats: bool = True
    notify_on_score_change: bool = True

class ScheduleResponse(BaseModel):
    success: bool
    scheduled_id: Optional[int] = None
    message: str

@scheduled_router.post("/add", response_model=ScheduleResponse)
async def add_scheduled_analysis(
    request: ScheduleRequest,
    # current_user = Depends(get_current_user_dep)  # Add auth when ready
):
    """Add a new scheduled/recurring analysis"""
    manager = await get_scheduled_manager()

    # TODO: Get user_id from authenticated user
    user_id = "demo_user"  # Replace with current_user.username

    scheduled_id = await manager.add_scheduled_analysis(
        user_id=user_id,
        url=request.url,
        company_name=request.company_name,
        frequency=request.frequency,
        notify_on_threats=request.notify_on_threats,
        notify_on_score_change=request.notify_on_score_change
    )

    if scheduled_id:
        return ScheduleResponse(
            success=True,
            scheduled_id=scheduled_id,
            message=f"Scheduled {request.frequency} analysis for {request.url}"
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to create scheduled analysis")

@scheduled_router.get("/list")
async def list_scheduled_analyses():
    """List all scheduled analyses for current user"""
    manager = await get_scheduled_manager()

    # TODO: Get user_id from authenticated user
    user_id = "demo_user"

    analyses = await manager.get_user_scheduled_analyses(user_id)
    return {"scheduled_analyses": analyses}

@scheduled_router.get("/trends/{url:path}")
async def get_trends(url: str, days: int = 30):
    """Get historical trend data for a URL"""
    manager = await get_scheduled_manager()

    trends = await manager.get_trend_data(url, days)
    return {"url": url, "days": days, "data": trends}

@scheduled_router.delete("/remove")
async def remove_scheduled_analysis(url: str):
    """Remove/disable a scheduled analysis"""
    manager = await get_scheduled_manager()

    # TODO: Get user_id from authenticated user
    user_id = "demo_user"

    success = await manager.remove_scheduled_analysis(user_id, url)
    return {"success": success}


# ============================================================================
# STARTUP/SHUTDOWN HOOKS
# ============================================================================

async def startup_scheduled_manager():
    """Call this on app startup"""
    await get_scheduled_manager()
    logger.info("Scheduled analysis manager started")

async def shutdown_scheduled_manager():
    """Call this on app shutdown"""
    global _manager
    if _manager:
        await _manager.shutdown()
        _manager = None
    logger.info("Scheduled analysis manager stopped")
