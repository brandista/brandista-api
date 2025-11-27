"""
Growth Engine 2.0 - Agent API Endpoints
REST & WebSocket endpointit agenttijärjestelmälle
"""

import json
import logging
import asyncio
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel, Field

from agents import (
    get_orchestrator,
    AgentInsight,
    AgentProgress,
    AgentResult,
    WSMessageType,
    WSMessage
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
# WEBSOCKET ENDPOINT
# ============================================================================

class ConnectionManager:
    """Hallitse WebSocket-yhteyksiä"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[WS] Client connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"[WS] Client disconnected. Total: {len(self.active_connections)}")
    
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
                
                if not url:
                    await manager.send_json(websocket, {
                        "type": WSMessageType.ERROR.value,
                        "data": {"error": "URL is required"}
                    })
                    continue
                
                logger.info(f"[WS] Starting analysis for {url}")
                
                # Luo orchestrator
                orchestrator = get_orchestrator()
                
                # List to collect messages during analysis
                pending_messages = []
                
                # Callbackit jotka keräävät viestit listaan
                def sync_insight(insight: AgentInsight):
                    try:
                        msg = {
                            "type": WSMessageType.AGENT_INSIGHT.value,
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
                        pending_messages.append(msg)
                        logger.info(f"[WS] Queued insight: {insight.agent_name} - {insight.message[:50]}...")
                    except Exception as e:
                        logger.error(f"[WS] Failed to queue insight: {e}")
                
                def sync_progress(progress: AgentProgress):
                    try:
                        msg = {
                            "type": WSMessageType.AGENT_PROGRESS.value,
                            "data": {
                                "agent_id": progress.agent_id,
                                "status": progress.status.value if hasattr(progress.status, 'value') else progress.status,
                                "progress": progress.progress,
                                "current_task": progress.current_task
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        pending_messages.append(msg)
                    except Exception as e:
                        logger.error(f"[WS] Failed to queue progress: {e}")
                
                def sync_complete(agent_id: str, result: AgentResult):
                    try:
                        msg = {
                            "type": WSMessageType.AGENT_STATUS.value,
                            "data": {
                                "agent_id": agent_id,
                                "status": result.status.value if hasattr(result.status, 'value') else result.status,
                                "execution_time_ms": result.execution_time_ms,
                                "insights_count": len(result.insights),
                                "has_error": result.error is not None
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        pending_messages.append(msg)
                    except Exception as e:
                        logger.error(f"[WS] Failed to queue status: {e}")
                
                orchestrator.set_callbacks(
                    on_insight=sync_insight,
                    on_progress=sync_progress,
                    on_agent_complete=sync_complete
                )
                
                # Suorita analyysi
                try:
                    result = await orchestrator.run_analysis(
                        url=url,
                        competitor_urls=competitor_urls,
                        language=language,
                        industry_context=industry_context
                    )
                    
                    # Send all collected messages to frontend
                    logger.info(f"[WS] Analysis complete. Sending {len(pending_messages)} collected messages...")
                    for msg in pending_messages:
                        try:
                            await manager.send_json(websocket, msg)
                            await asyncio.sleep(0.05)  # Small delay between messages
                        except Exception as e:
                            logger.error(f"[WS] Failed to send message: {e}")
                    
                    # Extract data from agent results for frontend
                    agent_results = result.agent_results or {}
                    
                    # Analyst data - structure: {your_analysis, competitor_analyses, benchmark, your_score}
                    analyst_data = agent_results.get('analyst', {})
                    analyst_result = analyst_data.data if hasattr(analyst_data, 'data') else analyst_data
                    
                    # Get benchmark which contains ranking info
                    benchmark = analyst_result.get('benchmark', {})
                    your_score = analyst_result.get('your_score', 0) or benchmark.get('your_score', 0) or result.overall_score
                    your_ranking = benchmark.get('your_rank', benchmark.get('your_position', 1))
                    total_competitors = benchmark.get('total_analyzed', 1)
                    avg_score = benchmark.get('avg_competitor_score', 0)
                    best_score = benchmark.get('best_score', your_score)
                    
                    # Get your_analysis for detailed data
                    your_analysis = analyst_result.get('your_analysis', {})
                    
                    logger.info(f"[WS] Analyst data: score={your_score}, rank={your_ranking}, total={total_competitors}")
                    
                    # Guardian data
                    guardian_data = agent_results.get('guardian', {})
                    guardian_result = guardian_data.data if hasattr(guardian_data, 'data') else guardian_data
                    revenue_impact = guardian_result.get('revenue_impact', {})
                    revenue_at_risk = revenue_impact.get('total_annual_risk', 0)
                    competitor_threats = guardian_result.get('competitor_threat_assessment', {}).get('assessments', [])
                    rasm_score = guardian_result.get('rasm_score', 0)
                    
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
                                'action': first_action.get('action', first_action.get('title', '')),
                                'impact_points': first_action.get('impact_points', projected_improvement),
                                'effort_hours': first_action.get('effort_hours', first_action.get('time_estimate', '4-8h')),
                                'roi_estimate': first_action.get('roi_estimate', 0)
                            }
                        
                        # Extract phase tasks
                        phase1 = phases[0].get('tasks', []) if len(phases) > 0 else []
                        phase2 = phases[1].get('tasks', []) if len(phases) > 1 else []
                        phase3 = phases[2].get('tasks', []) if len(phases) > 2 else []
                        
                        total_actions = sum(len(p.get('tasks', [])) for p in phases)
                        
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
                    
                    # Lähetä lopputulos with all mapped data
                    await manager.send_json(websocket, {
                        "type": WSMessageType.ANALYSIS_COMPLETE.value,
                        "data": {
                            "success": result.success,
                            "duration_seconds": result.execution_time_ms / 1000,
                            "agents_completed": len([r for r in agent_results.values() if r]),
                            "agents_failed": len(result.errors),
                            
                            # Analyst data (flattened)
                            "your_score": your_score,
                            "your_ranking": your_ranking,
                            "total_competitors": total_competitors,
                            "benchmark": benchmark,
                            
                            # Guardian data (flattened)
                            "revenue_at_risk": revenue_at_risk,
                            "competitor_threats": competitor_threats,
                            "rasm_score": rasm_score,
                            
                            # Prospector data
                            "market_gaps": market_gaps,
                            "opportunities_count": len(market_gaps),
                            
                            # Strategist data
                            "position_quadrant": position_quadrant,
                            
                            # Planner data
                            "action_plan": action_plan_mapped,
                            "projected_improvement": projected_improvement,
                            
                            # Legacy fields
                            "overall_score": result.overall_score,
                            "composite_scores": result.composite_scores,
                            "errors": result.errors
                        },
                        "timestamp": datetime.now().isoformat()
                    })
                    
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
        manager.disconnect(websocket)
        logger.info("[WS] Client disconnected")
    
    except Exception as e:
        logger.error(f"[WS] Error: {e}", exc_info=True)
        manager.disconnect(websocket)


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
