"""
Growth Engine 2.0 - Agent API Endpoints
REST & WebSocket endpointit agenttijärjestelmälle
"""

import json
import logging
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header
from pydantic import BaseModel, Field

def serialize_for_json(obj: Any) -> Any:
    """
    Recursively convert Pydantic models and other non-serializable objects to JSON-safe types.
    """
    if obj is None:
        return None
    
    # Handle Pydantic models (v1 and v2)
    if hasattr(obj, 'model_dump'):
        return serialize_for_json(obj.model_dump())
    if hasattr(obj, 'dict'):
        return serialize_for_json(obj.dict())
    
    # Handle dictionaries
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    
    # Handle lists and tuples
    if isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    
    # Handle sets
    if isinstance(obj, set):
        return [serialize_for_json(item) for item in obj]
    
    # Handle datetime
    if isinstance(obj, datetime):
        return obj.isoformat()
    
    # Handle enums
    if hasattr(obj, 'value'):
        return obj.value
    
    # Return primitives as-is
    if isinstance(obj, (str, int, float, bool)):
        return obj
    
    # Fallback: try to convert to string
    try:
        return str(obj)
    except:
        return None

# Auth functions - lazy import to avoid circular dependency
def _get_auth_functions():
    """Lazy import auth functions from main to avoid circular import"""
    try:
        from main import get_current_user, UserInfo
        return get_current_user, UserInfo
    except ImportError:
        # Fallback if main not available
        from pydantic import BaseModel as PydanticBaseModel
        
        class UserInfo(PydanticBaseModel):
            username: str
            role: str = "user"
        
        async def get_current_user(authorization: Optional[str] = None) -> Optional[UserInfo]:
            return UserInfo(username="anonymous", role="user")
        
        return get_current_user, UserInfo

# Will be initialized on first use
_auth_cache = {}

def get_auth():
    """Get auth functions (cached)"""
    if 'funcs' not in _auth_cache:
        _auth_cache['funcs'] = _get_auth_functions()
    return _auth_cache['funcs']

# Create dependency for FastAPI
async def get_current_user_dep(authorization: Optional[str] = Header(None)):
    """FastAPI dependency wrapper for auth"""
    get_current_user_func, _ = get_auth()
    return await get_current_user_func(authorization)

from agents import (
    get_orchestrator,
    AgentInsight,
    AgentProgress,
    AgentResult,
    WSMessageType,
    WSMessage,
    SwarmEvent,  # For agent communication events
    # RunContext for per-request isolation
    RunContext,
    RunStatus,
    create_run_context,
    create_run_context_sync,
    get_run_context,
    # NEW: RunStore functions for Redis-backed persistence
    get_run_from_store,
    list_runs_from_store,
    cancel_run
)

logger = logging.getLogger(__name__)

# Router
router = APIRouter(prefix="/api/v1/agents", tags=["Agent System"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class AgentAnalysisRequest(BaseModel):
    """Agentti-analyysin pyyntö"""
    url: str = Field(..., description="Analysoitava URL")
    competitor_urls: List[str] = Field(default=[], description="Kilpailijoiden URL:it (max 5)")
    language: str = Field(default="fi", description="Kieli: 'fi' tai 'en'")
    industry_context: Optional[str] = Field(default=None, description="Toimiala-konteksti")
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com",
                "competitor_urls": ["https://competitor1.com", "https://competitor2.com"],
                "language": "fi",
                "industry_context": "saas"
            }
        }


class AgentInfo(BaseModel):
    """Agentin tiedot"""
    id: str
    name: str
    role: str
    avatar: str
    personality: str
    dependencies: List[str]
    status: str
    progress: int


class AgentInfoResponse(BaseModel):
    """Agenttien tiedot -vastaus"""
    agents: List[AgentInfo]
    execution_flow: List[List[str]]


class AnalysisResultResponse(BaseModel):
    """Analyysin lopputulos"""
    success: bool
    execution_time_ms: int
    url: str
    competitor_count: int
    overall_score: int
    composite_scores: dict
    critical_insights: List[dict]
    high_insights: List[dict]
    action_plan: Optional[dict]
    errors: List[str]


# ============================================================================
# REST ENDPOINTS
# ============================================================================

@router.get("/info", response_model=AgentInfoResponse)
async def get_agents_info():
    """
    Palauta kaikkien agenttien tiedot.
    Käytetään frontendissä agent-korttien renderöintiin.
    """
    orchestrator = get_orchestrator()
    
    return AgentInfoResponse(
        agents=[AgentInfo(**info) for info in orchestrator.get_agent_info()],
        execution_flow=orchestrator.get_execution_plan()
    )


@router.post("/analyze", response_model=AnalysisResultResponse)
async def run_agent_analysis(request: AgentAnalysisRequest):
    """
    Suorita täysi agentti-analyysi (synkroninen).
    
    Käyttö: Yksinkertaisiin integraatioihin joissa ei tarvita real-time päivityksiä.
    
    HUOM: Tämä endpoint odottaa kunnes analyysi on valmis (~90s).
    Käytä WebSocket-endpointtia real-time päivityksiin.
    """
    logger.info(f"[Agent API] Starting analysis for {request.url}")
    
    # Validoi
    if len(request.competitor_urls) > 5:
        raise HTTPException(400, "Maximum 5 competitors allowed")
    
    orchestrator = get_orchestrator()
    
    try:
        result = await orchestrator.run_analysis(
            url=request.url,
            competitor_urls=request.competitor_urls,
            language=request.language,
            industry_context=request.industry_context
        )
        
        return AnalysisResultResponse(
            success=result.success,
            execution_time_ms=result.execution_time_ms,
            url=result.url,
            competitor_count=result.competitor_count,
            overall_score=result.overall_score,
            composite_scores=result.composite_scores,
            critical_insights=[i.dict() for i in result.critical_insights],
            high_insights=[i.dict() for i in result.high_insights],
            action_plan=result.action_plan,
            errors=result.errors
        )
        
    except Exception as e:
        logger.error(f"[Agent API] Analysis error: {e}", exc_info=True)
        raise HTTPException(500, f"Analysis failed: {str(e)}")


@router.get("/status")
async def get_orchestrator_status():
    """Palauta orchestratorin tila"""
    orchestrator = get_orchestrator()

    return {
        "is_running": orchestrator.is_running,
        "agents_registered": len(orchestrator.agents),
        "execution_plan": orchestrator.get_execution_plan()
    }


# ============================================================================
# RUN CONTEXT ENDPOINTS (NEW in 2.2.0)
# ============================================================================

@router.get("/run/{run_id}")
async def get_run_status(run_id: str):
    """
    Get status of a specific analysis run.
    Reads from RunStore (Redis) so works across workers.
    """
    # First try local context (faster for active runs on this worker)
    run_ctx = get_run_context(run_id)
    if run_ctx:
        return run_ctx.get_state()

    # Otherwise fetch from RunStore (Redis)
    run_data = await get_run_from_store(run_id)
    if not run_data:
        raise HTTPException(404, f"Run {run_id} not found")

    return {
        "run_id": run_id,
        "user_id": run_data.get('meta', {}).get('user_id'),
        "url": run_data.get('meta', {}).get('url'),
        "status": run_data.get('status', 'unknown'),
        "created_at": run_data.get('meta', {}).get('created_at'),
        "started_at": run_data.get('meta', {}).get('started_at'),
        "completed_at": run_data.get('meta', {}).get('completed_at'),
        "error": run_data.get('result', {}).get('error') if run_data.get('result') else None,
        "metadata": run_data.get('meta', {}).get('metadata', {}),
        "has_result": run_data.get('result') is not None
    }


@router.get("/runs")
async def list_runs(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    user_id: Optional[str] = None
):
    """
    List analysis runs with filtering.
    Reads from RunStore (Redis) so works across workers.

    Query params:
    - limit: Max results (default 50)
    - offset: Skip N results (for pagination)
    - status: Filter by status (pending/running/completed/failed/cancelled)
    - user_id: Filter by user
    """
    runs = await list_runs_from_store(
        limit=limit,
        offset=offset,
        status=status,
        user_id=user_id
    )

    return {
        "count": len(runs),
        "limit": limit,
        "offset": offset,
        "filters": {"status": status, "user_id": user_id},
        "runs": [
            {
                "run_id": r.get('run_id') or r.get('meta', {}).get('run_id'),
                "user_id": r.get('meta', {}).get('user_id'),
                "url": r.get('meta', {}).get('url'),
                "status": r.get('status', 'unknown'),
                "created_at": r.get('meta', {}).get('created_at'),
                "has_result": r.get('result') is not None
            }
            for r in runs
        ]
    }


@router.post("/run/{run_id}/cancel")
async def cancel_run_endpoint(run_id: str, reason: str = "User cancelled"):
    """
    Cancel a running analysis.

    Idempotent - safe to call multiple times.
    Works across workers via Redis.
    """
    # Check if already cancelled or completed
    run_data = await get_run_from_store(run_id)
    if not run_data:
        # Also check local context
        run_ctx = get_run_context(run_id)
        if not run_ctx:
            raise HTTPException(404, f"Run {run_id} not found")

    current_status = run_data.get('status') if run_data else None

    # Idempotent: if already cancelled, return success
    if current_status == 'cancelled':
        return {
            "success": True,
            "run_id": run_id,
            "status": "cancelled",
            "message": "Already cancelled"
        }

    # Cannot cancel completed/failed runs
    if current_status in ('completed', 'failed'):
        return {
            "success": False,
            "run_id": run_id,
            "status": current_status,
            "message": f"Cannot cancel - run is already {current_status}"
        }

    # Cancel via RunStore (works across workers)
    success = await cancel_run(run_id, reason)

    # Also emit a final WS event if we have a local connection
    if run_id in manager.run_connections:
        try:
            await manager.send_json(manager.run_connections[run_id], {
                "type": "run_cancelled",
                "run_id": run_id,
                "data": {"reason": reason, "status": "cancelled"},
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.warning(f"[Cancel] Could not send WS cancel event: {e}")

    return {
        "success": success,
        "run_id": run_id,
        "status": "cancelled",
        "message": f"Cancelled: {reason}"
    }


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

class ConnectionManager:
    """Hallitse WebSocket-yhteyksiä with run_id routing"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # Track connections by run_id for targeted messaging
        self.run_connections: Dict[str, WebSocket] = {}
        # Lock for thread-safe dict access
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, run_id: str = None):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
            if run_id:
                self.run_connections[run_id] = websocket
        logger.info(f"[WS] Client connected. Total: {len(self.active_connections)}, run_id: {run_id}")

    async def disconnect(self, websocket: WebSocket, run_id: str = None):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            if run_id and run_id in self.run_connections:
                del self.run_connections[run_id]
        logger.info(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def register_run(self, run_id: str, websocket: WebSocket):
        """Register a run_id to websocket mapping."""
        async with self._lock:
            self.run_connections[run_id] = websocket

    async def unregister_run(self, run_id: str):
        """Remove a run_id mapping (call after analysis completes)."""
        async with self._lock:
            if run_id in self.run_connections:
                del self.run_connections[run_id]
        logger.debug(f"[WS] Run {run_id} unregistered")
    
    async def send_json(self, websocket: WebSocket, data: dict):
        """Send JSON with proper datetime serialization"""
        import json
        
        def serialize_datetime(obj):
            """Convert datetime objects to ISO format strings"""
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        try:
            # Serialize with custom handler for datetime
            json_str = json.dumps(data, default=serialize_datetime)
            await websocket.send_text(json_str)
        except Exception as e:
            logger.error(f"[WS] Send error: {e}")


manager = ConnectionManager()


def verify_ws_token(token: str) -> Optional[dict]:
    """Verify JWT token for WebSocket connection"""
    import os
    import jwt
    
    if not token:
        return None
    
    try:
        SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("[WS] Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"[WS] Invalid token: {e}")
        return None
    except Exception as e:
        logger.error(f"[WS] Token verification error: {e}")
        return None


@router.websocket("/ws")
async def websocket_agent_analysis(
    websocket: WebSocket,
    token: Optional[str] = None
):
    """
    WebSocket endpoint real-time agentti-analyysille.
    
    Yhdistä: wss://host/api/v1/agents/ws?token=JWT_TOKEN
    
    Protokolla:
    1. Client lähettää: {"action": "start", "url": "...", "competitor_urls": [...], "language": "fi"}
    2. Server streamaa:
       - {"type": "agent_status", "data": {...}}
       - {"type": "agent_insight", "data": {...}}
       - {"type": "agent_progress", "data": {...}}
       - {"type": "analysis_complete", "data": {...}}
    """
    # Validate token
    user = verify_ws_token(token)
    if not user:
        logger.warning(f"[WS] Connection rejected - invalid or missing token")
        await websocket.close(code=4001, reason="Invalid or missing token")
        return
    
    logger.info(f"[WS] Authenticated: {user.get('sub', 'unknown')}")

    # Track current run_id for this connection
    current_run_id = None

    await manager.connect(websocket)

    try:
        while True:
            # Odota viestiä clientiltä
            data = await websocket.receive_json()

            action = data.get("action")

            if action == "start":
                # Aloita analyysi
                url = data.get("url")
                competitor_urls = data.get("competitor_urls", [])
                language = data.get("language", "fi")
                industry_context = data.get("industry_context")
                # NEW: User-provided revenue data (Feb 2026)
                annual_revenue = data.get("annual_revenue")  # EUR, e.g. 500000
                business_id = data.get("business_id")  # Y-tunnus, e.g. "0116297-6"

                if not url:
                    await manager.send_json(websocket, {
                        "type": WSMessageType.ERROR.value,
                        "data": {"error": "URL is required"}
                    })
                    continue

                # Create RunContext for this analysis (async for RunStore persistence)
                user_id = user.get('sub')
                run_context = await create_run_context(user_id=user_id, url=url)
                current_run_id = run_context.run_id
                await manager.register_run(current_run_id, websocket)

                logger.info(f"[WS] Starting analysis for {url} (run_id={current_run_id})")
                
                # Luo orchestrator
                orchestrator = get_orchestrator()
                
                # Queue for real-time message sending
                message_queue = asyncio.Queue()
                send_task_running = True
                
                # Background task to send messages in real-time
                async def message_sender():
                    while send_task_running or not message_queue.empty():
                        try:
                            msg = await asyncio.wait_for(message_queue.get(), timeout=0.1)
                            await manager.send_json(websocket, msg)
                            await asyncio.sleep(0.02)  # Small delay between messages
                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            logger.error(f"[WS] Failed to send message: {e}")
                
                # Start the sender task
                sender_task = asyncio.create_task(message_sender())
                
                # List to also collect messages for final processing
                pending_messages = []
                
                # Send run_started message immediately
                await manager.send_json(websocket, {
                    "type": "run_started",
                    "run_id": current_run_id,
                    "data": {"url": url, "status": "started"},
                    "timestamp": datetime.now().isoformat()
                })

                # Callbackit jotka lähettävät viestit HETI (include run_id in ALL messages)
                def sync_insight(insight: AgentInsight):
                    try:
                        msg = {
                            "type": WSMessageType.AGENT_INSIGHT.value,
                            "run_id": current_run_id,  # NEW: Include run_id
                            "data": {
                                "agent_id": insight.agent_id,
                                "agent_name": insight.agent_name,
                                "agent_avatar": insight.agent_avatar,
                                "message": insight.message,
                                "priority": insight.priority.value if hasattr(insight.priority, 'value') else insight.priority,
                                "insight_type": insight.insight_type.value if hasattr(insight.insight_type, 'value') else insight.insight_type,
                                "timestamp": insight.timestamp.isoformat() if hasattr(insight.timestamp, 'isoformat') else str(insight.timestamp),
                                "data": insight.data
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        # Send immediately via queue
                        message_queue.put_nowait(msg)
                        pending_messages.append(msg)
                        logger.info(f"[WS] Queued insight: {insight.agent_name} - {insight.message[:50]}...")
                    except Exception as e:
                        logger.error(f"[WS] Failed to queue insight: {e}")
                
                def sync_progress(progress: AgentProgress):
                    try:
                        # 🔍 DEBUG: Log every progress callback
                        logger.info(f"[WS] 📊 sync_progress called: agent={progress.agent_id}, progress={progress.progress}%, task={progress.current_task}")

                        msg = {
                            "type": WSMessageType.AGENT_PROGRESS.value,
                            "run_id": current_run_id,  # NEW: Include run_id
                            "data": {
                                "agent_id": progress.agent_id,
                                "status": progress.status.value if hasattr(progress.status, 'value') else progress.status,
                                "progress": progress.progress,
                                "current_task": progress.current_task
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        # Send immediately via queue
                        message_queue.put_nowait(msg)
                        pending_messages.append(msg)
                        logger.info(f"[WS] ✅ Progress queued for {progress.agent_id}: {progress.progress}%")
                    except Exception as e:
                        logger.error(f"[WS] Failed to queue progress: {e}")
                
                def sync_complete(agent_id: str, result: AgentResult):
                    try:
                        msg = {
                            "type": WSMessageType.AGENT_STATUS.value,
                            "run_id": current_run_id,  # NEW: Include run_id
                            "data": {
                                "agent_id": agent_id,
                                "status": result.status.value if hasattr(result.status, 'value') else result.status,
                                "execution_time_ms": result.execution_time_ms,
                                "insights_count": len(result.insights),
                                "has_error": result.error is not None
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        # Send immediately via queue
                        message_queue.put_nowait(msg)
                        pending_messages.append(msg)
                    except Exception as e:
                        logger.error(f"[WS] Failed to queue status: {e}")
                
                def sync_start(agent_id: str, agent_name: str):
                    """NEW: Callback when agent starts running"""
                    try:
                        msg = {
                            "type": WSMessageType.AGENT_STATUS.value,
                            "run_id": current_run_id,  # NEW: Include run_id
                            "data": {
                                "agent_id": agent_id,
                                "status": "running",
                                "agent_name": agent_name
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        message_queue.put_nowait(msg)
                        pending_messages.append(msg)
                        logger.info(f"[WS] Agent {agent_name} started - status sent")
                    except Exception as e:
                        logger.error(f"[WS] Failed to queue start status: {e}")

                def sync_swarm_event(event: SwarmEvent):
                    """Callback for agent-to-agent communication events"""
                    try:
                        msg = {
                            "type": "swarm_event",
                            "run_id": current_run_id,  # NEW: Include run_id
                            "data": {
                                "event_type": event.event_type.value if hasattr(event.event_type, 'value') else event.event_type,
                                "from_agent": event.from_agent,
                                "to_agent": event.to_agent,
                                "subject": event.subject,
                                "timestamp": event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
                                "data": event.data
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        message_queue.put_nowait(msg)
                        pending_messages.append(msg)
                        logger.info(f"[WS] 🐝 Swarm event: {event.from_agent} -> {event.to_agent or 'blackboard'}: {event.subject}")
                    except Exception as e:
                        logger.error(f"[WS] Failed to queue swarm event: {e}")

                orchestrator.set_callbacks(
                    on_insight=sync_insight,
                    on_progress=sync_progress,
                    on_agent_complete=sync_complete,
                    on_agent_start=sync_start,
                    on_swarm_event=sync_swarm_event  # NEW: Agent communication events
                )
                
                # Suorita analyysi
                try:
                    # Build revenue_input if user provided annual_revenue
                    revenue_input = None
                    if annual_revenue:
                        revenue_input = {
                            'annual_revenue': int(annual_revenue),
                            'source': 'user_provided'
                        }
                        logger.info(f"[WS] User provided revenue: EUR {annual_revenue:,}")

                    result = await orchestrator.run_analysis(
                        url=url,
                        competitor_urls=competitor_urls,
                        language=language,
                        industry_context=industry_context,
                        user_id=user_id,  # Pass user_id for unified context
                        revenue_input=revenue_input,  # NEW: User-provided revenue
                        business_id=business_id,  # NEW: User-provided Y-tunnus
                        run_context=run_context  # NEW: Pass RunContext for isolation
                    )
                    
                    # Stop the sender task and wait for remaining messages
                    send_task_running = False
                    await asyncio.sleep(0.3)  # Give time for final messages
                    sender_task.cancel()
                    try:
                        await sender_task
                    except asyncio.CancelledError:
                        pass
                    
                    logger.info(f"[WS] Analysis complete. Sent {len(pending_messages)} messages in real-time.")
                    
                    # Extract data from agent results for frontend
                    agent_results = result.agent_results or {}
                    
                    # Analyst data - structure: {your_analysis, competitor_analyses, benchmark, your_score}
                    analyst_data = agent_results.get('analyst', {})
                    analyst_result = analyst_data.data if hasattr(analyst_data, 'data') else analyst_data
                    
                    # Get benchmark which contains ranking info
                    benchmark_raw = analyst_result.get('benchmark', {})
                    your_score = analyst_result.get('your_score', 0) or benchmark_raw.get('your_score', 0) or result.overall_score
                    your_ranking = benchmark_raw.get('your_rank', benchmark_raw.get('your_position', 1))
                    total_competitors_from_analyst = benchmark_raw.get('total_analyzed', 1)
                    avg_score = benchmark_raw.get('avg_competitor_score', 0)
                    best_score = benchmark_raw.get('max_competitor_score', your_score)
                    
                    # Map benchmark to frontend format
                    benchmark = {
                        'avg': avg_score,
                        'max': best_score,
                        'min': benchmark_raw.get('min_competitor_score', 0),
                        # Also include raw fields for compatibility
                        'your_score': your_score,
                        'avg_competitor_score': avg_score,
                        'max_competitor_score': best_score,
                        'your_position': your_ranking,
                        'total_analyzed': total_competitors_from_analyst
                    }
                    
                    # Get your_analysis for detailed data
                    your_analysis = analyst_result.get('your_analysis', {})
                    
                    logger.info(f"[WS] Analyst data: score={your_score}, rank={your_ranking}, total={total_competitors_from_analyst}")
                    logger.info(f"[WS] Benchmark: avg={avg_score}, max={best_score}")
                    
                    # Guardian data
                    guardian_data = agent_results.get('guardian', {})
                    guardian_result = guardian_data.data if hasattr(guardian_data, 'data') else guardian_data
                    revenue_impact = guardian_result.get('revenue_impact', {})
                    revenue_at_risk = revenue_impact.get('total_annual_risk', 0)
                    competitor_threats = guardian_result.get('competitor_threat_assessment', {}).get('assessments', [])
                    rasm_score = guardian_result.get('rasm_score', 0)
                    
                    # Log competitor threat scores
                    for ct in competitor_threats[:3]:
                        logger.info(f"[WS] Competitor threat: {ct.get('name')} score={ct.get('digital_score')}")
                    
                    # Map competitor_threats to frontend format
                    competitor_threats_mapped = []
                    for ct in competitor_threats:
                        # Extract signal descriptions from signals object
                        signals_obj = ct.get('signals', {})
                        signal_descriptions = []
                        
                        if signals_obj.get('domain_age', {}).get('is_established'):
                            age = signals_obj.get('domain_age', {}).get('age_years', 0)
                            signal_descriptions.append(f"Established {int(age)}+ years")
                        if signals_obj.get('trust_signals', {}).get('has_ssl'):
                            signal_descriptions.append("SSL secured")
                        if signals_obj.get('growth_signals', {}).get('is_hiring'):
                            signal_descriptions.append("Actively hiring")
                        if signals_obj.get('company_size', {}).get('estimated_employees'):
                            emp = signals_obj['company_size']['estimated_employees']
                            signal_descriptions.append(f"{emp} employees")
                        
                        # Extract domain from URL
                        url = ct.get('url', '')
                        domain = url.replace('https://', '').replace('http://', '').split('/')[0] if url else ''
                        
                        competitor_threats_mapped.append({
                            'domain': domain,
                            'company': ct.get('name', domain),
                            'url': url,
                            'score': ct.get('digital_score', 0),
                            'score_diff': ct.get('score_diff', 0),
                            'threat_level': ct.get('threat_level', 'medium'),
                            'threat_score': ct.get('threat_score', 5),
                            'threat_label': ct.get('threat_label', ''),
                            'reasoning': ct.get('reasoning', ''),
                            'signals': signal_descriptions if signal_descriptions else ['No specific signals']
                        })
                    
                    competitor_threats = competitor_threats_mapped
                    
                    # Prospector data
                    prospector_data = agent_results.get('prospector', {})
                    prospector_result = prospector_data.data if hasattr(prospector_data, 'data') else prospector_data
                    market_gaps = prospector_result.get('market_gaps', [])
                    
                    # Strategist data
                    strategist_data = agent_results.get('strategist', {})
                    strategist_result = strategist_data.data if hasattr(strategist_data, 'data') else strategist_data
                    position_quadrant = strategist_result.get('position_quadrant', 'challenger')
                    
                    # Map action_plan to frontend format
                    action_plan_mapped = None
                    projected_improvement = 0
                    planner_data = agent_results.get('planner', {})
                    planner = planner_data.data if hasattr(planner_data, 'data') else planner_data
                    
                    if planner:
                        phases = planner.get('phases', [])
                        quick_start = planner.get('quick_start_guide', [])
                        roi = planner.get('roi_projection', {})
                        projected_improvement = roi.get('potential_score_gain', 0)
                        
                        # Get first quick start action as "this week"
                        this_week = None
                        if quick_start and len(quick_start) > 0:
                            first_action = quick_start[0]
                            this_week = {
                                'action': first_action.get('title', first_action.get('action', '')),
                                'impact_points': first_action.get('impact_points', projected_improvement // 3 if projected_improvement else 5),
                                'effort_hours': first_action.get('time_estimate', first_action.get('effort_hours', '4-8h')),
                                'roi_estimate': first_action.get('roi_estimate', 0),
                                'category': first_action.get('category', 'optimization'),
                                'priority': first_action.get('priority', 1)
                            }
                        elif phases and len(phases) > 0 and phases[0].get('tasks'):
                            # Fallback: use first task from phase 1
                            first_task = phases[0]['tasks'][0]
                            this_week = {
                                'action': first_task.get('title', ''),
                                'impact_points': projected_improvement // 3 if projected_improvement else 5,
                                'effort_hours': '1 day',
                                'roi_estimate': 0,
                                'category': first_task.get('category', 'general'),
                                'priority': 1
                            }
                        
                        # Extract and MAP phase tasks to frontend format
                        # Frontend expects: {action: string, impact_points: number, ...}
                        # Backend provides: {title: string, category: string, effort: string}
                        def map_task(task, default_points=5):
                            effort_points = {'low': 3, 'medium': 5, 'high': 8}
                            return {
                                'action': task.get('title', task.get('action', '')),
                                'impact_points': task.get('impact_points', effort_points.get(task.get('effort', 'medium'), 5)),
                                'effort_hours': task.get('timeframe', task.get('time_estimate', {'low': '2-4h', 'medium': '1-2 days', 'high': '3-5 days'}.get(task.get('effort', 'medium'), '1 day'))),
                                'category': task.get('category', 'general'),
                                'priority': task.get('priority', 2),
                                'roi_estimate': task.get('roi_estimate', 0)
                            }
                        
                        phase1_raw = phases[0].get('tasks', []) if len(phases) > 0 else []
                        phase2_raw = phases[1].get('tasks', []) if len(phases) > 1 else []
                        phase3_raw = phases[2].get('tasks', []) if len(phases) > 2 else []
                        
                        phase1 = [map_task(t, 5) for t in phase1_raw]
                        phase2 = [map_task(t, 4) for t in phase2_raw]
                        phase3 = [map_task(t, 3) for t in phase3_raw]
                        
                        total_actions = len(phase1) + len(phase2) + len(phase3)
                        
                        action_plan_mapped = {
                            'this_week': this_week,
                            'phase1': phase1,
                            'phase2': phase2,
                            'phase3': phase3,
                            'total_actions': total_actions,
                            'projected_improvement': projected_improvement,
                            'milestones': planner.get('milestones', []),
                            'resource_estimate': planner.get('resource_estimate', {})
                        }
                    
                    # Get Scout data for competitor info
                    scout_data = agent_results.get('scout', {})
                    scout_result = scout_data.data if hasattr(scout_data, 'data') else scout_data
                    competitor_urls_found = scout_result.get('competitor_urls', []) if scout_result else []
                    
                    # Get Company Intelligence data from Scout
                    competitors_enriched = scout_result.get('competitors_enriched', []) if scout_result else []
                    
                    # Extract your company info (from analysed URL)
                    your_company = None
                    if scout_result and scout_result.get('your_company_intel'):
                        your_company = scout_result.get('your_company_intel')
                    
                    # Map competitor companies with their intel
                    competitor_companies = []
                    for comp in competitors_enriched:
                        company_intel = comp.get('company_intel')
                        if company_intel:
                            competitor_companies.append({
                                'name': company_intel.get('name'),
                                'business_id': company_intel.get('business_id'),
                                'city': company_intel.get('city'),
                                'industry': company_intel.get('industry'),
                                'employees': company_intel.get('employees'),
                                'employees_text': company_intel.get('employees_text'),
                                'revenue': company_intel.get('revenue'),
                                'revenue_text': company_intel.get('revenue_text'),
                                'ytj_url': company_intel.get('ytj_url'),
                                'kauppalehti_url': company_intel.get('kauppalehti_url'),
                                'source': company_intel.get('source'),
                            })
                    
                    # Reconcile total_competitors: use max of Analyst benchmark and Scout findings
                    total_competitors = max(
                        total_competitors_from_analyst,
                        len(competitor_urls_found) + 1  # Scout found N competitors + your site
                    ) if competitor_urls_found else total_competitors_from_analyst
                    logger.info(f"[WS] total_competitors reconciled: analyst={total_competitors_from_analyst}, scout_found={len(competitor_urls_found)}, final={total_competitors}")
                    
                    # Update benchmark with reconciled total
                    benchmark['total_analyzed'] = total_competitors
                    
                    # Get additional Strategist data
                    market_position = strategist_result.get('market_position', '') if strategist_result else ''
                    strategic_score = strategist_result.get('strategic_score', 0) if strategist_result else 0
                    creative_boldness = strategist_result.get('creative_boldness', 50) if strategist_result else 50
                    
                    # Get Prospector advantages (map to strings for frontend)
                    advantages_raw = prospector_result.get('competitive_advantages', []) if prospector_result else []
                    your_advantages = [adv.get('title', str(adv)) if isinstance(adv, dict) else str(adv) for adv in advantages_raw]
                    
                    # Get Guardian risk count
                    risks = guardian_result.get('risks', []) if guardian_result else []
                    risk_count = len(risks) if risks else len(competitor_threats)
                    
                    # Map market_gaps to frontend format (gap, description, potential_value, difficulty, competitors_missing)
                    market_gaps_mapped = []
                    for mg in market_gaps:
                        market_gaps_mapped.append({
                            'gap': mg.get('title', mg.get('gap', '')),
                            'description': mg.get('description', f"Category: {mg.get('category', 'general')}"),
                            'potential_value': mg.get('potential_value', mg.get('advantage', 0) * 100),
                            'difficulty': mg.get('difficulty', 'medium' if mg.get('impact') == 'medium' else 'easy' if mg.get('impact') == 'high' else 'hard'),
                            'competitors_missing': mg.get('competitors_missing', len(competitor_urls_found))
                        })
                    
                    # DEBUG: Log what we're about to send
                    logger.info(f"[WS] competitor_threats count: {len(competitor_threats)}")
                    logger.info(f"[WS] action_plan_mapped: phase1={len(action_plan_mapped.get('phase1', []))} phase2={len(action_plan_mapped.get('phase2', []))} phase3={len(action_plan_mapped.get('phase3', []))} this_week={action_plan_mapped.get('this_week') is not None}" if action_plan_mapped else "[WS] action_plan_mapped: None")
                    logger.info(f"[WS] market_gaps_mapped count: {len(market_gaps_mapped)}")
                    
                    # Log AI analysis data
                    ai_analysis_data = your_analysis.get('ai_analysis', {})
                    logger.info(f"[WS] ai_analysis keys: {list(ai_analysis_data.keys()) if ai_analysis_data else 'empty'}")
                    if ai_analysis_data.get('ai_search_visibility'):
                        logger.info(f"[WS] ai_search_visibility score: {ai_analysis_data.get('ai_search_visibility', {}).get('overall_ai_search_score', 'N/A')}")
                    
                    # Lähetä lopputulos with all mapped data
                    await manager.send_json(websocket, {
                        "type": WSMessageType.ANALYSIS_COMPLETE.value,
                        "run_id": current_run_id,  # NEW: Include run_id
                        "data": {
                            "success": result.success,
                            "duration_seconds": result.execution_time_ms / 1000,
                            "agents_completed": len([r for r in agent_results.values() if r]),
                            "agents_failed": len(result.errors),
                            
                            # URL (from original request)
                            "url": url,
                            
                            # Scout data (NEW)
                            "competitors_found": len(competitor_urls_found),
                            "competitor_urls": competitor_urls_found,
                            
                            # Company Intelligence (Due Diligence)
                            "your_company": your_company,
                            "competitor_companies": competitor_companies,
                            
                            # Analyst data (flattened)
                            "your_score": your_score,
                            "your_ranking": your_ranking,
                            "total_competitors": total_competitors,
                            "benchmark": benchmark,
                            
                            # Guardian data (flattened)
                            "revenue_at_risk": revenue_at_risk,
                            "competitor_threats": competitor_threats,
                            "rasm_score": rasm_score,
                            "risk_count": risk_count,  # NEW
                            "revenue_impact_analysis": revenue_impact.get('revenue_impact_analysis', {}),  # NEW: Detailed breakdown
                            
                            # Prospector data
                            "market_gaps": market_gaps_mapped,  # Now mapped to frontend format
                            "opportunities_count": len(market_gaps_mapped),
                            "your_advantages": your_advantages,  # NEW
                            
                            # Strategist data (expanded)
                            "position_quadrant": position_quadrant,
                            "market_position": market_position,  # NEW
                            "strategic_score": strategic_score,  # NEW
                            "creative_boldness": creative_boldness,  # NEW
                            "market_trajectory": strategist_result.get('market_trajectory', {}), # NEW Agent 3.0
                            "guardian_vetos": strategist_result.get('guardian_vetos', []), # NEW Agent 3.0
                            
                            # Planner data
                            "action_plan": action_plan_mapped,
                            "projected_improvement": projected_improvement,
                            "dependency_management": True, # NEW Agent 3.0
                            
                            # Legacy fields
                            "overall_score": result.overall_score,
                            "composite_scores": result.composite_scores,
                            "errors": result.errors,
                            
                            # AI Analysis data (from your_analysis)
                            "your_company_intel": your_company,  # Alias for compatibility
                            "ai_analysis": serialize_for_json(your_analysis.get('ai_analysis', {})),
                            
                            # Full agent results for deep dive views (serialized to avoid Pydantic issues)
                            "agent_results": serialize_for_json({
                                "scout": {"data": scout_result},
                                "analyst": {"data": analyst_result},
                                "guardian": {"data": guardian_result},
                                "prospector": {"data": prospector_result},
                                "strategist": {"data": strategist_result},
                                "planner": {"data": planner}
                            })
                        },
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Save to unified context (async, don't block response)
                    try:
                        from unified_context import save_analysis, save_agent_insight
                        
                        # Save analysis
                        analysis_id = save_analysis(
                            user_id=user_id,
                            url=url,
                            score=your_score,
                            ranking=your_ranking,
                            total_competitors=total_competitors,
                            revenue_at_risk=revenue_at_risk,
                            rasm_score=rasm_score,
                            benchmark=benchmark,
                            threats=competitor_threats,
                            opportunities=market_gaps,
                            action_plan=action_plan_mapped,
                            raw_results={
                                'analyst': analyst_result,
                                'guardian': guardian_result,
                                'prospector': prospector_result,
                                'strategist': strategist_result,
                                'planner': planner
                            },
                            duration_seconds=result.execution_time_ms / 1000
                        )
                        
                        # Save insights
                        if analysis_id:
                            for msg in pending_messages:
                                if msg.get('type') == WSMessageType.AGENT_INSIGHT.value:
                                    insight_data = msg.get('data', {})
                                    save_agent_insight(
                                        user_id=user_id,
                                        agent_id=insight_data.get('agent_id'),
                                        message=insight_data.get('message', ''),
                                        agent_name=insight_data.get('agent_name'),
                                        insight_type=insight_data.get('insight_type'),
                                        priority=insight_data.get('priority'),
                                        data=insight_data.get('data'),
                                        analysis_id=analysis_id
                                    )
                        
                        logger.info(f"[WS] Saved analysis {analysis_id} to unified context")
                    except Exception as save_error:
                        logger.warning(f"[WS] Could not save to unified context: {save_error}")
                    
                    # Send notification to user's dashboard (if connected)
                    try:
                        from notification_ws import notify_analysis_complete
                        # asyncio is already imported at module level
                        asyncio.create_task(notify_analysis_complete(
                            user_id=user_id,
                            analysis_result={
                                "your_score": your_score,
                                "your_ranking": your_ranking,
                                "total_competitors": total_competitors,
                                "revenue_at_risk": revenue_at_risk,
                                "market_gaps": market_gaps_mapped,
                                "url": url
                            }
                        ))
                        logger.info(f"[WS] Notification sent to user {user_id}")
                    except Exception as notify_error:
                        logger.debug(f"[WS] Notification not sent (user may not have dashboard open): {notify_error}")

                    # Clean up run_id mapping after analysis completes
                    await manager.unregister_run(current_run_id)

                except Exception as e:
                    logger.error(f"[WS] Analysis error: {e}", exc_info=True)
                    await manager.send_json(websocket, {
                        "type": WSMessageType.ERROR.value,
                        "data": {"error": str(e)},
                        "timestamp": datetime.now().isoformat()
                    })
            
            elif action == "ping":
                await manager.send_json(websocket, {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
            
            else:
                await manager.send_json(websocket, {
                    "type": WSMessageType.ERROR.value,
                    "data": {"error": f"Unknown action: {action}"}
                })
    
    except WebSocketDisconnect:
        await manager.disconnect(websocket, current_run_id)
        logger.info(f"[WS] Client disconnected (run_id={current_run_id})")

    except Exception as e:
        logger.error(f"[WS] Error: {e}", exc_info=True)
        await manager.disconnect(websocket, current_run_id)


# ============================================================================
# CHAT ENDPOINT - Agent chat for follow-up questions
# ============================================================================

class ChatRequest(BaseModel):
    agent_id: str
    messages: List[Dict[str, str]]
    analysis_context: Optional[Dict[str, Any]] = None
    language: str = "en"

class ChatResponse(BaseModel):
    response: str
    agent_id: str
    suggested_questions: List[str] = []

# Agent system prompts for chat
AGENT_CHAT_PROMPTS = {
    "scout": {
        "fi": """Olet Sofia, Brandistan markkinatiedustelija. Olet juuri analysoinut käyttäjän kilpailijat.
Persoonallisuutesi: Utelias, tarkkanäköinen, analyyttinen. Puhut suomea.
Vastaa käyttäjän kysymyksiin kilpailijoista, markkinatilanteesta ja löydöksistäsi.
Ole ytimekäs mutta informatiivinen. Käytä emojeja sopivasti. 🔍""",
        "en": """You are Sofia, Brandista's market intelligence expert. You just analyzed the user's competitors.
Personality: Curious, observant, analytical.
Answer questions about competitors, market situation, and your findings.
Be concise but informative. Use emojis appropriately. 🔍"""
    },
    "analyst": {
        "fi": """Olet Alex, Brandistan data-analyytikko. Olet juuri analysoinut käyttäjän sivuston ja kilpailijat.
Persoonallisuutesi: Tarkka, numeroihin keskittyvä, metodinen. Puhut suomea.
Vastaa kysymyksiin pisteistä, vertailuista ja teknisistä yksityiskohdista.
Anna konkreettisia lukuja kun mahdollista. 📊""",
        "en": """You are Alex, Brandista's data analyst. You just analyzed the user's site and competitors.
Personality: Precise, numbers-focused, methodical.
Answer questions about scores, comparisons, and technical details.
Provide concrete numbers when possible. 📊"""
    },
    "guardian": {
        "fi": """Olet Gustav, Brandistan riskienhallitsija. Olet juuri tunnistanut käyttäjän liiketoimintariskit.
Persoonallisuutesi: Varovainen, suojeleva, rehellinen riskeistä. Puhut suomea.
Vastaa kysymyksiin riskeistä, uhkista ja niiden euromääräisistä vaikutuksista.
Ole suora mutta rakentava - tarjoa aina myös ratkaisuja. 🛡️""",
        "en": """You are Gustav, Brandista's risk manager. You just identified risks to the user's business.
Personality: Cautious, protective, honest about risks.
Answer questions about risks, threats, and their monetary impact.
Be direct but constructive - always offer solutions too. 🛡️"""
    },
    "prospector": {
        "fi": """Olet Petra, Brandistan kasvuhakkeri. Olet juuri löytänyt käyttäjälle kasvumahdollisuuksia.
Persoonallisuutesi: Energinen, optimistinen, mahdollisuuksiin keskittyvä. Puhut suomea.
Vastaa kysymyksiin markkinaaukoista, kasvumahdollisuuksista ja quick wineistä.
Ole innostava ja konkreettinen. 💎""",
        "en": """You are Petra, Brandista's growth hacker. You just found growth opportunities for the user.
Personality: Energetic, optimistic, opportunity-focused.
Answer questions about market gaps, growth opportunities, and quick wins.
Be inspiring and concrete. 💎"""
    },
    "strategist": {
        "fi": """Olet Stefan, Brandistan strategiajohtaja. Olet juuri rakentanut käyttäjälle strategisen näkemyksen.
Persoonallisuutesi: Viisas, kokonaisuuksia näkevä, johtajuustaitoinen. Puhut suomea.
Vastaa kysymyksiin strategiasta, markkina-asemasta ja prioriteeteista.
Anna strategista perspektiiviä. 🎯""",
        "en": """You are Stefan, Brandista's strategy director. You just built a strategic vision for the user.
Personality: Wise, big-picture thinker, leadership-oriented.
Answer questions about strategy, market position, and priorities.
Provide strategic perspective. 🎯"""
    },
    "planner": {
        "fi": """Olet Pinja, Brandistan projektimanageri. Olet juuri luonut käyttäjälle 90 päivän toimintasuunnitelman.
Persoonallisuutesi: Järjestelmällinen, käytännöllinen, toteutuskeskeinen. Puhut suomea.
Vastaa kysymyksiin aikatauluista, tehtävistä, resursseista ja ROI:sta.
Ole konkreettinen ja auta priorisoimaan. 📋""",
        "en": """You are Pinja, Brandista's project manager. You just created a 90-day action plan for the user.
Personality: Organized, practical, execution-focused.
Answer questions about timelines, tasks, resources, and ROI.
Be concrete and help prioritize. 📋"""
    }
}

SUGGESTED_QUESTIONS = {
    "scout": {
        "fi": ["Kuka on pahin kilpailijani?", "Mitä kilpailijat tekevät paremmin?", "Onko markkinoilla uusia tulokkaita?"],
        "en": ["Who is my biggest competitor?", "What do competitors do better?", "Are there new market entrants?"]
    },
    "analyst": {
        "fi": ["Miksi pisteeni on tämä?", "Missä olen kilpailijoita edellä?", "Mitä teknisiä puutteita minulla on?"],
        "en": ["Why is my score this?", "Where am I ahead of competitors?", "What technical gaps do I have?"]
    },
    "guardian": {
        "fi": ["Mikä on suurin riski?", "Miten 65000€ riski muodostuu?", "Mitä teen ensimmäiseksi?"],
        "en": ["What's the biggest risk?", "How is the €65,000 risk calculated?", "What should I do first?"]
    },
    "prospector": {
        "fi": ["Mikä on helpoin quick win?", "Missä kilpailijat jättävät rahaa pöydälle?", "Mikä kasvumahdollisuus on suurin?"],
        "en": ["What's the easiest quick win?", "Where do competitors leave money on the table?", "What's the biggest growth opportunity?"]
    },
    "strategist": {
        "fi": ["Mikä on markkina-asemani?", "Mihin minun pitäisi keskittyä?", "Miten voitan kilpailijat?"],
        "en": ["What's my market position?", "What should I focus on?", "How do I beat competitors?"]
    },
    "planner": {
        "fi": ["Mitä teen ensimmäisellä viikolla?", "Paljonko tämä maksaa?", "Mikä on odotettu ROI?"],
        "en": ["What do I do in week one?", "How much will this cost?", "What's the expected ROI?"]
    }
}


@router.post("/chat", response_model=ChatResponse)
async def agent_chat(
    request: ChatRequest,
    current_user = Depends(get_current_user_dep)
):
    """
    Chat with an AI agent about analysis results.
    """
    try:
        from openai import AsyncOpenAI
        
        openai_client = AsyncOpenAI()
        
        agent_id = request.agent_id
        language = request.language
        
        # Get agent system prompt
        system_prompt = AGENT_CHAT_PROMPTS.get(agent_id, AGENT_CHAT_PROMPTS["analyst"])[language]
        
        # Add analysis context to system prompt
        if request.analysis_context:
            context_summary = f"""

Analyysin tulokset / Analysis results:
- Pistemäärä / Score: {request.analysis_context.get('your_score', 0)}/100
- Sijoitus / Ranking: #{request.analysis_context.get('your_ranking', 1)} / {request.analysis_context.get('total_competitors', 1)}
- Liikevaihto riskissä / Revenue at risk: €{request.analysis_context.get('revenue_at_risk', 0):,}
- Kilpailijauhat / Competitor threats: {len(request.analysis_context.get('competitor_threats', []))}
- Markkinaaukot / Market gaps: {len(request.analysis_context.get('market_gaps', []))}
"""
            # Add detailed context based on agent
            if agent_id == "guardian" and request.analysis_context.get('competitor_threats'):
                threats = request.analysis_context.get('competitor_threats', [])
                context_summary += "\nKilpailijauhat / Threats:\n"
                for t in threats[:3]:
                    context_summary += f"- {t.get('company', 'Unknown')}: {t.get('threat_level', 'medium')} threat, score {t.get('score', 0)}/100\n"
            
            if agent_id == "prospector" and request.analysis_context.get('market_gaps'):
                gaps = request.analysis_context.get('market_gaps', [])
                context_summary += "\nMarkkinaaukot / Market gaps:\n"
                for g in gaps[:3]:
                    context_summary += f"- {g.get('gap', 'Unknown')}: {g.get('difficulty', 'medium')}, potential €{g.get('potential_value', 0)}\n"
            
            if agent_id == "planner" and request.analysis_context.get('action_plan'):
                plan = request.analysis_context.get('action_plan', {})
                context_summary += f"\nToimintasuunnitelma / Action plan:\n"
                context_summary += f"- Total actions: {plan.get('total_actions', 0)}\n"
                context_summary += f"- Projected improvement: +{request.analysis_context.get('projected_improvement', 0)} points\n"
                if plan.get('this_week'):
                    tw = plan['this_week']
                    context_summary += f"- This week: {tw.get('action', '')} (+{tw.get('impact_points', 0)} points)\n"
            
            system_prompt += context_summary
        
        # Build messages for OpenAI
        openai_messages = [{"role": "system", "content": system_prompt}]
        
        for msg in request.messages:
            openai_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        # Call OpenAI
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=openai_messages,
            max_tokens=500,
            temperature=0.7
        )
        
        agent_response = response.choices[0].message.content
        
        # Get suggested questions
        suggested = SUGGESTED_QUESTIONS.get(agent_id, SUGGESTED_QUESTIONS["analyst"])[language]
        
        return ChatResponse(
            response=agent_response,
            agent_id=agent_id,
            suggested_questions=suggested
        )
        
    except Exception as e:
        logger.error(f"[Chat] Error: {e}", exc_info=True)
        error_msg = "Pahoittelut, jotain meni pieleen. Yritä uudelleen!" if request.language == "fi" else "Sorry, something went wrong. Please try again!"
        return ChatResponse(
            response=error_msg,
            agent_id=request.agent_id,
            suggested_questions=[]
        )


# ============================================================================
# HELPER: Lisää router main.py:hyn
# ============================================================================

def register_agent_routes(app):
    """
    Rekisteröi agent-routet FastAPI-appiin.
    
    Käyttö main.py:ssä:
        from agent_api import register_agent_routes
        register_agent_routes(app)
    """
    app.include_router(router)
    logger.info("[Agent API] Routes registered")
