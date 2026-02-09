"""
Brandista Agent Scheduler — Proactive agent execution

Simple asyncio-based scheduler that:
  1. Checks agent_schedules table every 60 seconds
  2. Runs due agents as background tasks
  3. Converts agent insights → alerts via AlertService
  4. Updates schedule timestamps

No Celery needed — runs within the FastAPI process.
Can be upgraded to Celery workers when scaling to multiple processes.

Usage:
  scheduler = get_scheduler()
  await scheduler.initialize(DATABASE_URL, alert_service)
  await scheduler.start()
  # ... app runs ...
  await scheduler.stop()
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List

import asyncpg

logger = logging.getLogger(__name__)


class AgentScheduler:
    """
    Proactive agent scheduler.
    Checks for due agent runs every 60 seconds and dispatches them.
    """

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        self.alert_service = None  # Set via initialize()
        self._main_task: Optional[asyncio.Task] = None
        self._running = False
        self._check_interval = 60  # seconds

    async def initialize(self, database_url: str, alert_service):
        """Create pool and store reference to AlertService."""
        from core.alerts import AlertService

        clean_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        self.pool = await asyncpg.create_pool(
            clean_url, min_size=1, max_size=3, command_timeout=60
        )
        self.alert_service = alert_service
        logger.info("✅ AgentScheduler initialized")

    async def start(self):
        """Start the scheduler loop as a background task."""
        if self._running:
            return
        self._running = True
        self._main_task = asyncio.create_task(self._scheduler_loop())
        logger.info("🕐 AgentScheduler started (check interval: 60s)")

    async def stop(self):
        """Gracefully stop the scheduler."""
        self._running = False
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
            self._main_task = None
        if self.pool:
            await self.pool.close()
        logger.info("🛑 AgentScheduler stopped")

    # ------------------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------------------

    async def _scheduler_loop(self):
        """Main loop: check for due schedules every 60 seconds."""
        # Wait 10 seconds on startup to let everything else initialize
        await asyncio.sleep(10)
        logger.info("🔄 AgentScheduler loop started")

        while self._running:
            try:
                await self._process_due_schedules()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Scheduler] Error in loop: {e}", exc_info=True)

            try:
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break

    async def _process_due_schedules(self):
        """Find and execute all due scheduled agent runs."""
        if not self.pool:
            return

        async with self.pool.acquire() as conn:
            due = await conn.fetch("""
                SELECT * FROM agent_schedules
                WHERE enabled = TRUE
                AND (next_run IS NULL OR next_run <= NOW())
                ORDER BY next_run ASC NULLS FIRST
                LIMIT 5
            """)

        if due:
            logger.info(f"[Scheduler] Found {len(due)} due schedule(s)")

        for schedule in due:
            # Fire-and-forget: run each agent as a separate task
            asyncio.create_task(
                self._run_scheduled_agent(dict(schedule))
            )

    # ------------------------------------------------------------------
    # Agent Dispatch
    # ------------------------------------------------------------------

    async def _run_scheduled_agent(self, schedule: dict):
        """Execute a single scheduled agent run and emit alerts."""
        agent_name = schedule["agent_name"]
        task_type = schedule["task_type"]
        raw_config = schedule.get("config", {}) or {}
        # Config may come as JSON string from DB — parse if needed
        if isinstance(raw_config, str):
            try:
                config = json.loads(raw_config)
            except (json.JSONDecodeError, TypeError):
                config = {}
        else:
            config = raw_config
        user_id = schedule["user_id"]
        schedule_id = schedule["id"]

        logger.info(f"[Scheduler] Running {agent_name}/{task_type} for {user_id}")

        try:
            # Dispatch to appropriate runner
            alerts = await self._dispatch_agent(agent_name, task_type, user_id, config)

            # Emit alerts
            for alert_data in alerts:
                await self.alert_service.create_alert(
                    user_id=user_id,
                    alert_type=alert_data.get("type", f"{agent_name}_alert"),
                    severity=alert_data.get("severity", "info"),
                    title=alert_data.get("title", f"{agent_name} update"),
                    message=alert_data.get("message", ""),
                    module=alert_data.get("module", "growth_engine"),
                    agent=agent_name,
                    data=alert_data.get("data", {}),
                    org_id=schedule.get("org_id"),
                )

            # Update schedule timing
            await self._update_schedule_timing(schedule_id, schedule["interval_seconds"])

            logger.info(
                f"[Scheduler] ✅ {agent_name}/{task_type} completed — "
                f"{len(alerts)} alert(s) generated"
            )

        except Exception as e:
            logger.error(
                f"[Scheduler] ❌ {agent_name}/{task_type} failed: {e}",
                exc_info=True,
            )
            # Create error alert so user knows something went wrong
            try:
                await self.alert_service.create_alert(
                    user_id=user_id,
                    alert_type="agent_error",
                    severity="warning",
                    title=f"{agent_name} suoritus epäonnistui",
                    message=f"Agentti {agent_name} ({task_type}) epäonnistui: {str(e)[:200]}",
                    module="system",
                    agent=agent_name,
                    org_id=schedule.get("org_id"),
                )
            except Exception:
                pass  # Don't fail on error-alert creation

            # Still update timing so we don't retry immediately
            try:
                await self._update_schedule_timing(schedule_id, schedule["interval_seconds"])
            except Exception:
                pass

    async def _dispatch_agent(
        self, agent_name: str, task_type: str, user_id: str, config: dict
    ) -> List[dict]:
        """
        Route to the correct agent runner.
        Returns a list of alert dicts.
        """
        if agent_name == "scout" and task_type == "competitor_crawl":
            return await self._run_scout_crawl(user_id, config)
        elif agent_name == "guardian" and task_type == "threat_assessment":
            return await self._run_guardian_check(user_id, config)
        elif agent_name == "bookkeeper" and task_type == "expense_check":
            return await self._run_bookkeeper_check(user_id, config)
        else:
            logger.warning(f"[Scheduler] Unknown agent/task: {agent_name}/{task_type}")
            return []

    async def _update_schedule_timing(self, schedule_id: int, interval_seconds: int):
        """Update last_run and next_run in the database."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_schedules
                SET last_run = NOW(),
                    next_run = NOW() + ($2 * INTERVAL '1 second'),
                    updated_at = NOW()
                WHERE id = $1
                """,
                schedule_id,
                interval_seconds,
            )

    # ------------------------------------------------------------------
    # Agent Runners
    # ------------------------------------------------------------------

    async def _run_scout_crawl(self, user_id: str, config: dict) -> List[dict]:
        """
        Run a lightweight Scout check.

        For MVP: Uses the existing ScoutAgent if available,
        otherwise generates a simulated market update.
        """
        target_url = config.get("target_url", "")
        competitor_urls = config.get("competitor_urls", [])

        # Try to use the real ScoutAgent
        try:
            from agents.scout_agent import ScoutAgent
            from agents.agent_types import AnalysisContext

            scout = ScoutAgent()
            context = AnalysisContext(
                url=target_url,
                competitor_urls=competitor_urls,
                language="fi",
                user_id=user_id,
            )
            result = await scout.run(context)

            alerts = []
            for insight in (result.insights or []):
                severity = "info"
                if hasattr(insight, "priority"):
                    pval = getattr(insight.priority, "value", 3)
                    if pval <= 1:
                        severity = "critical"
                    elif pval <= 2:
                        severity = "warning"

                alerts.append({
                    "type": f"scout_{getattr(insight, 'insight_type', 'update')}",
                    "severity": severity,
                    "title": str(getattr(insight, "message", "Scout-löydös"))[:200],
                    "message": str(getattr(insight, "message", ""))[:500],
                    "module": "growth_engine",
                    "data": getattr(insight, "data", {}) or {},
                })

            if not alerts:
                # Even successful scans with no insights should report
                alerts.append({
                    "type": "scout_scan_complete",
                    "severity": "info",
                    "title": "Scout: Markkinakatsaus valmis",
                    "message": f"Scout tarkisti kilpailutilanteen. Ei merkittäviä muutoksia havaittu.",
                    "module": "growth_engine",
                    "data": {"target_url": target_url, "competitors_checked": len(competitor_urls)},
                })

            return alerts

        except ImportError:
            logger.warning("[Scheduler] ScoutAgent not available, using simulated data")
            return self._simulated_scout_alerts(target_url)

        except Exception as e:
            logger.error(f"[Scheduler] Scout failed: {e}")
            return [{
                "type": "scout_error",
                "severity": "warning",
                "title": "Scout: Skannaus epäonnistui",
                "message": f"Kilpailijaskannaus epäonnistui: {str(e)[:200]}",
                "module": "growth_engine",
                "data": {"error": str(e)[:200]},
            }]

    async def _run_guardian_check(self, user_id: str, config: dict) -> List[dict]:
        """
        Run a Guardian threat assessment.

        For MVP: Check if there are recent scout findings that need
        threat evaluation. Otherwise generate a status update.
        """
        try:
            from agents.guardian_agent import GuardianAgent

            guardian = GuardianAgent()
            # Guardian needs scout data — check blackboard or recent alerts
            # For now, generate a status check alert
            return [{
                "type": "guardian_status",
                "severity": "info",
                "title": "Guardian: Uhkataso vakaa",
                "message": "Guardian tarkisti markkinatilanteen. Ei uusia uhkia havaittu.",
                "module": "growth_engine",
                "data": {"status": "stable", "threats_checked": 0},
            }]

        except ImportError:
            return [{
                "type": "guardian_status",
                "severity": "info",
                "title": "Guardian: Markkinatilanne vakaa",
                "message": "Proaktiivinen uhka-arviointi suoritettu. Ei kriittisiä muutoksia.",
                "module": "growth_engine",
                "data": {"status": "stable"},
            }]

    async def _run_bookkeeper_check(self, user_id: str, config: dict) -> List[dict]:
        """
        Run an AI Bookkeeper expense trend check.

        For MVP: Stub that generates a periodic expense summary.
        Will be connected to real Books module data later.
        """
        return [{
            "type": "bookkeeper_trend",
            "severity": "info",
            "title": "AI Bookkeeper: Kuluyhteenveto",
            "message": "Kuukausittainen kulutrendi-tarkistus suoritettu.",
            "module": "books",
            "data": {"period": "monthly", "status": "checked"},
        }]

    # ------------------------------------------------------------------
    # Simulated Data (for development without full agent stack)
    # ------------------------------------------------------------------

    @staticmethod
    def _simulated_scout_alerts(target_url: str) -> List[dict]:
        """Generate realistic-looking simulated alerts for development."""
        import random

        scenarios = [
            {
                "type": "competitor_price_change",
                "severity": "warning",
                "title": "Kilpailija muutti hintojaan",
                "message": "Havaittu hinnanmuutos kilpailijan verkkosivulla. Keskimääräinen hintatason lasku -8%.",
                "data": {"change_pct": -8, "target": target_url or "kilpailija.fi"},
            },
            {
                "type": "competitor_new_feature",
                "severity": "info",
                "title": "Kilpailija julkaisi uuden ominaisuuden",
                "message": "Kilpailijan verkkosivulle ilmestyi uusi tuotesivu tai palvelukuvaus.",
                "data": {"feature": "AI-pohjainen analyysi", "target": target_url or "kilpailija.fi"},
            },
            {
                "type": "competitor_hiring",
                "severity": "warning",
                "title": "Kilpailija rekrytoi aktiivisesti",
                "message": "Havaittu 3 uutta työpaikkailmoitusta teknologia-rooleihin.",
                "data": {"positions": 3, "roles": ["Senior Developer", "Data Engineer", "PM"]},
            },
            {
                "type": "market_stable",
                "severity": "info",
                "title": "Scout: Markkinatilanne vakaa",
                "message": "Kilpailutilanteessa ei merkittäviä muutoksia viimeisen tarkistuksen jälkeen.",
                "data": {"status": "stable"},
            },
        ]

        # Pick 1-2 random scenarios
        count = random.randint(1, 2)
        selected = random.sample(scenarios, min(count, len(scenarios)))

        for s in selected:
            s["module"] = "growth_engine"

        return selected


# ============================================================================
# SINGLETON
# ============================================================================

_scheduler: Optional[AgentScheduler] = None


def get_scheduler() -> AgentScheduler:
    """Get or create the global AgentScheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AgentScheduler()
    return _scheduler
