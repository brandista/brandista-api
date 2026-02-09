"""
Brandista Alert Service — SSE real-time alerts + REST API

This is the central nerve system for live agent alerts:
  1. AlertService persists alerts to PostgreSQL and broadcasts to SSE clients
  2. SSE endpoint streams alerts in real-time (heartbeat 30s)
  3. REST endpoints for fetching, marking read, acknowledging

Usage:
  # At app startup:
  svc = get_alert_service()
  await svc.initialize(DATABASE_URL)

  # Create an alert (from scheduler/agent):
  await svc.create_alert(user_id="matti@yritys.fi", ...)

  # At app shutdown:
  await svc.shutdown()
"""

import os
import json
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Set, List

import asyncpg
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

# ============================================================================
# DATA TYPES
# ============================================================================

class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    id: str
    type: str
    severity: str
    title: str
    message: str
    module: str
    agent: str
    data: dict = field(default_factory=dict)
    read: bool = False
    acknowledged: bool = False
    org_id: Optional[str] = None
    user_id: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # Ensure created_at is a string
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        return d


# ============================================================================
# SQL SCHEMA
# ============================================================================

CREATE_ALERTS_TABLE = """
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id VARCHAR(255),
    user_id VARCHAR(255),
    type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    title VARCHAR(500) NOT NULL,
    message TEXT NOT NULL,
    module VARCHAR(50),
    agent VARCHAR(50),
    data JSONB DEFAULT '{}',
    read BOOLEAN DEFAULT FALSE,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

CREATE_ALERTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_alerts_org_id ON alerts(org_id);",
    "CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_alerts_unread ON alerts(user_id, read) WHERE read = FALSE;",
]

CREATE_SCHEDULES_TABLE = """
CREATE TABLE IF NOT EXISTS agent_schedules (
    id SERIAL PRIMARY KEY,
    org_id VARCHAR(255),
    user_id VARCHAR(255) NOT NULL,
    agent_name VARCHAR(50) NOT NULL,
    task_type VARCHAR(100) NOT NULL,
    interval_seconds INTEGER NOT NULL DEFAULT 21600,
    enabled BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, agent_name, task_type)
);
"""

CREATE_SCHEDULES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_schedules_next ON agent_schedules(next_run) WHERE enabled = TRUE;",
]


# ============================================================================
# ALERT SERVICE (singleton)
# ============================================================================

class AlertService:
    """
    Central alert management:
    - Persists alerts to PostgreSQL
    - Broadcasts to connected SSE clients via asyncio.Queue
    - Manages alert lifecycle (read/unread, acknowledge)
    """

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        # Per-user SSE client queues: user_id → Set[asyncio.Queue]
        self._client_queues: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self, database_url: str):
        """Create connection pool and ensure tables exist."""
        if self._initialized:
            return

        # asyncpg requires postgresql:// not postgresql+asyncpg://
        clean_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

        try:
            self.pool = await asyncpg.create_pool(
                clean_url,
                min_size=1,
                max_size=5,
                command_timeout=30
            )
            await self._create_tables()
            self._initialized = True
            logger.info("✅ AlertService initialized")
        except Exception as e:
            logger.error(f"❌ AlertService initialization failed: {e}")
            raise

    async def shutdown(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("🛑 AlertService pool closed")

    async def _create_tables(self):
        """Ensure alerts and agent_schedules tables exist, seed default schedules."""
        async with self.pool.acquire() as conn:
            await conn.execute(CREATE_ALERTS_TABLE)
            for idx in CREATE_ALERTS_INDEXES:
                await conn.execute(idx)
            await conn.execute(CREATE_SCHEDULES_TABLE)
            for idx in CREATE_SCHEDULES_INDEXES:
                await conn.execute(idx)

            # Seed default schedules (ON CONFLICT = skip if already exists)
            seed_schedules = [
                ("admin@brandista.eu", "scout", "competitor_crawl", 21600, '{"target_url": "https://brandista.eu", "competitor_urls": []}'),
                ("admin@brandista.eu", "guardian", "threat_assessment", 43200, '{}'),
                ("admin@brandista.eu", "bookkeeper", "expense_check", 86400, '{}'),
            ]
            for user_id, agent, task, interval, config in seed_schedules:
                await conn.execute(
                    """
                    INSERT INTO agent_schedules (user_id, agent_name, task_type, interval_seconds, config, next_run)
                    VALUES ($1, $2, $3, $4, $5::jsonb, NOW())
                    ON CONFLICT (user_id, agent_name, task_type) DO NOTHING
                    """,
                    user_id, agent, task, interval, config,
                )
            logger.info("✅ Alert tables ensured")

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_alert(
        self,
        user_id: str,
        alert_type: str,
        severity: str,
        title: str,
        message: str,
        module: str = "",
        agent: str = "",
        data: Optional[dict] = None,
        org_id: Optional[str] = None,
    ) -> Alert:
        """Persist an alert and broadcast it to SSE clients."""
        alert_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO alerts (id, org_id, user_id, type, severity, title, message, module, agent, data, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
                """,
                uuid.UUID(alert_id),
                org_id,
                user_id,
                alert_type,
                severity,
                title,
                message,
                module,
                agent,
                json.dumps(data or {}),
                now,
            )

        alert = Alert(
            id=alert_id,
            org_id=org_id,
            user_id=user_id,
            type=alert_type,
            severity=severity,
            title=title,
            message=message,
            module=module,
            agent=agent,
            data=data or {},
            created_at=now.isoformat(),
        )

        # Broadcast to connected SSE clients
        await self._broadcast(user_id, alert)

        logger.info(
            f"🔔 Alert created: [{severity.upper()}] {title} "
            f"(user={user_id}, agent={agent})"
        )
        return alert

    async def get_alerts(
        self,
        user_id: str,
        limit: int = 50,
        unread_only: bool = False,
    ) -> List[Alert]:
        """Fetch recent alerts for a user."""
        query = "SELECT * FROM alerts WHERE user_id = $1"
        params = [user_id]

        if unread_only:
            query += " AND read = FALSE"

        query += " ORDER BY created_at DESC LIMIT $" + str(len(params) + 1)
        params.append(limit)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [self._row_to_alert(row) for row in rows]

    async def mark_read(self, user_id: str, alert_id: str) -> bool:
        """Mark a single alert as read."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE alerts SET read = TRUE WHERE id = $1 AND user_id = $2",
                uuid.UUID(alert_id),
                user_id,
            )
        return "UPDATE 1" in result

    async def mark_all_read(self, user_id: str) -> int:
        """Mark all alerts as read. Returns count updated."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE alerts SET read = TRUE WHERE user_id = $1 AND read = FALSE",
                user_id,
            )
        # Result is "UPDATE N"
        try:
            return int(result.split(" ")[1])
        except (IndexError, ValueError):
            return 0

    async def acknowledge(self, user_id: str, alert_id: str) -> bool:
        """Acknowledge (dismiss) an alert."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE alerts SET acknowledged = TRUE, acknowledged_at = NOW()
                WHERE id = $1 AND user_id = $2
                """,
                uuid.UUID(alert_id),
                user_id,
            )
        return "UPDATE 1" in result

    # ------------------------------------------------------------------
    # SSE Client Management
    # ------------------------------------------------------------------

    async def register_client(self, user_id: str) -> asyncio.Queue:
        """Register a new SSE client. Returns a Queue to listen on."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            if user_id not in self._client_queues:
                self._client_queues[user_id] = set()
            self._client_queues[user_id].add(queue)
        logger.info(f"📡 SSE client connected: {user_id} (total: {self._count_clients()})")
        return queue

    async def unregister_client(self, user_id: str, queue: asyncio.Queue):
        """Remove an SSE client."""
        async with self._lock:
            if user_id in self._client_queues:
                self._client_queues[user_id].discard(queue)
                if not self._client_queues[user_id]:
                    del self._client_queues[user_id]
        logger.info(f"📡 SSE client disconnected: {user_id} (total: {self._count_clients()})")

    async def _broadcast(self, user_id: str, alert: Alert):
        """Push alert to all SSE queues for this user."""
        queues = self._client_queues.get(user_id, set())
        dead_queues = set()
        for queue in queues:
            try:
                queue.put_nowait(alert)
            except asyncio.QueueFull:
                dead_queues.add(queue)
        # Clean up dead queues
        for q in dead_queues:
            async with self._lock:
                if user_id in self._client_queues:
                    self._client_queues[user_id].discard(q)

    def _count_clients(self) -> int:
        return sum(len(qs) for qs in self._client_queues.values())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_alert(row) -> Alert:
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)
        return Alert(
            id=str(row["id"]),
            org_id=row.get("org_id"),
            user_id=row.get("user_id"),
            type=row["type"],
            severity=row["severity"],
            title=row["title"],
            message=row["message"],
            module=row.get("module", ""),
            agent=row.get("agent", ""),
            data=data or {},
            read=row.get("read", False),
            acknowledged=row.get("acknowledged", False),
            created_at=row["created_at"].isoformat() if row.get("created_at") else None,
        )


# ============================================================================
# SINGLETON
# ============================================================================

_alert_service: Optional[AlertService] = None


def get_alert_service() -> AlertService:
    """Get or create the global AlertService singleton."""
    global _alert_service
    if _alert_service is None:
        _alert_service = AlertService()
    return _alert_service


# ============================================================================
# JWT VERIFICATION (for SSE query param auth)
# ============================================================================

def _verify_token(token: str) -> Optional[dict]:
    """
    Verify JWT token. Mirrors the pattern from notification_ws.py.
    Returns payload dict or None.
    """
    if not token:
        return None
    try:
        import jwt as pyjwt
        secret = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
        payload = pyjwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except Exception as e:
        logger.warning(f"JWT verification failed: {e}")
        return None


def _get_user_id(payload: dict) -> Optional[str]:
    """Extract user identifier from JWT payload."""
    return payload.get("sub") or payload.get("email") or payload.get("username")


# ============================================================================
# FASTAPI ROUTER — SSE + REST
# ============================================================================

alerts_router = APIRouter(prefix="/api/core/alerts", tags=["Alerts"])


@alerts_router.get("/stream")
async def alert_stream(
    request: Request,
    token: str = Query(..., description="JWT token for authentication"),
):
    """
    Server-Sent Events endpoint for real-time alerts.

    Connect with: new EventSource('/api/core/alerts/stream?token=YOUR_JWT')

    Events:
      - `alert`: New alert data (JSON)
      - `heartbeat`: Keep-alive (every 30s)
      - `connected`: Initial connection confirmation
    """
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = _get_user_id(payload)
    if not user_id:
        raise HTTPException(status_code=401, detail="No user identity in token")

    svc = get_alert_service()

    async def event_generator():
        queue = await svc.register_client(user_id)
        try:
            # 1. Send connection confirmation
            yield _sse_event("connected", {"user_id": user_id, "ts": _now_iso()})

            # 2. Send catch-up: last 10 unread alerts
            try:
                recent = await svc.get_alerts(user_id, limit=10, unread_only=True)
                for alert in reversed(recent):  # oldest first
                    yield _sse_event("alert", alert.to_dict())
            except Exception as e:
                logger.error(f"Catch-up failed: {e}")

            # 3. Real-time loop with heartbeat
            while True:
                try:
                    alert = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield _sse_event("alert", alert.to_dict())
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield _sse_event("heartbeat", {"ts": _now_iso()})

                # Check disconnect
                if await request.is_disconnected():
                    break

        except asyncio.CancelledError:
            pass
        finally:
            await svc.unregister_client(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx/Railway proxy buffering
        },
    )


@alerts_router.get("")
async def get_alerts(
    token: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
):
    """Fetch recent alerts (REST)."""
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = _get_user_id(payload)
    if not user_id:
        raise HTTPException(status_code=401, detail="No user identity")

    svc = get_alert_service()
    alerts = await svc.get_alerts(user_id, limit=limit, unread_only=unread_only)
    return {"alerts": [a.to_dict() for a in alerts], "count": len(alerts)}


@alerts_router.post("/{alert_id}/read")
async def mark_read(
    alert_id: str,
    token: str = Query(...),
):
    """Mark a single alert as read."""
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = _get_user_id(payload)
    svc = get_alert_service()
    success = await svc.mark_read(user_id, alert_id)
    return {"success": success}


@alerts_router.post("/read-all")
async def mark_all_read(token: str = Query(...)):
    """Mark all alerts as read."""
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = _get_user_id(payload)
    svc = get_alert_service()
    count = await svc.mark_all_read(user_id)
    return {"success": True, "count": count}


@alerts_router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    token: str = Query(...),
):
    """Acknowledge (dismiss) an alert."""
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = _get_user_id(payload)
    svc = get_alert_service()
    success = await svc.acknowledge(user_id, alert_id)
    return {"success": success}


# Test endpoint — useful for development
@alerts_router.post("/test")
async def create_test_alert(
    token: str = Query(...),
    severity: str = Query("info"),
    title: str = Query("Test alert"),
    message: str = Query("This is a test alert from the API"),
):
    """Create a test alert (for development/debugging)."""
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = _get_user_id(payload)
    svc = get_alert_service()
    alert = await svc.create_alert(
        user_id=user_id,
        alert_type="test",
        severity=severity,
        title=title,
        message=message,
        module="system",
        agent="test",
    )
    return alert.to_dict()


# ============================================================================
# SCHEDULES REST
# ============================================================================

schedules_router = APIRouter(prefix="/api/core/schedules", tags=["Schedules"])


@schedules_router.get("")
async def get_schedules(token: str = Query(...)):
    """Get all agent schedules for the authenticated user."""
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = _get_user_id(payload)

    svc = get_alert_service()
    async with svc.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM agent_schedules WHERE user_id = $1 ORDER BY agent_name",
            user_id,
        )
    return {
        "schedules": [
            {
                "id": r["id"],
                "agent_name": r["agent_name"],
                "task_type": r["task_type"],
                "interval_seconds": r["interval_seconds"],
                "enabled": r["enabled"],
                "last_run": r["last_run"].isoformat() if r["last_run"] else None,
                "next_run": r["next_run"].isoformat() if r["next_run"] else None,
                "config": r["config"] if isinstance(r["config"], dict) else json.loads(r["config"] or "{}"),
            }
            for r in rows
        ]
    }


@schedules_router.post("")
async def create_schedule(request: Request, token: str = Query(...)):
    """Create or update an agent schedule."""
    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = _get_user_id(payload)

    body = await request.json()
    agent_name = body.get("agent_name")
    task_type = body.get("task_type")
    interval = body.get("interval_seconds", 21600)
    config = body.get("config", {})
    enabled = body.get("enabled", True)

    if not agent_name or not task_type:
        raise HTTPException(status_code=400, detail="agent_name and task_type required")

    svc = get_alert_service()
    async with svc.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_schedules (user_id, agent_name, task_type, interval_seconds, config, enabled, next_run)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, NOW())
            ON CONFLICT (user_id, agent_name, task_type)
            DO UPDATE SET interval_seconds = $4, config = $5::jsonb, enabled = $6, updated_at = NOW()
            """,
            user_id, agent_name, task_type, interval, json.dumps(config), enabled,
        )
    return {"success": True, "message": f"Schedule {agent_name}/{task_type} saved"}


# ============================================================================
# HELPERS
# ============================================================================

def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
