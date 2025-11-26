"""
Growth Engine 2.0 - Agent API
REST and WebSocket endpoints for agent-based analysis
"""

import logging
import json
import asyncio
from typing import Optional, List, Any
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel

from agents import (
    AgentOrchestrator,
    AgentInsight,
    AgentProgress,
    AgentStatus
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class AgentAnalysisRequest(BaseModel):
    url: str
    competitor_urls: Optional[List[str]] = None
    industry: Optional[str] = None
    country_code: str = "fi"


class AgentInfo(BaseModel):
    id: str
    name: str
    role: str
    avatar: str
    personality: str
    status: str
    progress: int
    dependencies: List[str]


class AgentAnalysisResponse(BaseModel):
    success: bool
    duration_seconds: float
    agents_completed: int
    agents_failed: int
    results: dict
    errors: List[str]
    insights: List[dict]


# ============================================================================
# REST ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_agents_info():
    """Get information about all available agents"""
    orchestrator = AgentOrchestrator()
    return {
        "agents": orchestrator.get_agent_info(),
        "execution_order": orchestrator.execution_tiers,
        "total_agents": len(orchestrator.agents)
    }


@router.post("/analyze", response_model=AgentAnalysisResponse)
async def run_analysis(request: AgentAnalysisRequest):
    """
    Run complete agent-based analysis (synchronous).
    For real-time updates, use the WebSocket endpoint instead.
    """
    orchestrator = AgentOrchestrator()
    
    try:
        result = await orchestrator.run_analysis(
            url=request.url,
            competitor_urls=request.competitor_urls,
            industry=request.industry,
            country_code=request.country_code,
            user=None  # TODO: Get from auth
        )
        
        return AgentAnalysisResponse(
            success=result.success,
            duration_seconds=result.duration_seconds,
            agents_completed=result.agents_completed,
            agents_failed=result.agents_failed,
            results=result.results,
            errors=result.errors,
            insights=[{
                'agent_id': i.agent_id,
                'message': i.message,
                'priority': i.priority.value,
                'insight_type': i.insight_type.value,
                'timestamp': i.timestamp.isoformat(),
                'data': i.data
            } for i in result.insights]
        )
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(500, str(e))


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@router.websocket("/ws")
async def websocket_analysis(websocket: WebSocket):
    """
    WebSocket endpoint for real-time agent analysis.
    
    Client sends:
        { "action": "start", "url": "https://...", "competitor_urls": [...], "industry": "..." }
    
    Server sends:
        { "type": "insight", "data": { "agent_id": "scout", "message": "...", ... } }
        { "type": "progress", "data": { "agent_id": "scout", "progress": 50, "message": "..." } }
        { "type": "status", "data": { "agent_id": "scout", "status": "running" } }
        { "type": "complete", "data": { "success": true, "duration_seconds": 45.2, ... } }
        { "type": "error", "data": { "message": "..." } }
    """
    await websocket.accept()
    logger.info("[WS] Client connected")
    
    try:
        while True:
            # Wait for message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            action = message.get('action')
            
            if action == 'start':
                await _handle_start_analysis(websocket, message)
            elif action == 'ping':
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": f"Unknown action: {action}"}
                })
                
    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected")
    except Exception as e:
        logger.error(f"[WS] Error: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"message": str(e)}
            })
        except:
            pass


async def _handle_start_analysis(websocket: WebSocket, message: dict):
    """Handle start analysis request via WebSocket"""
    
    url = message.get('url')
    if not url:
        await websocket.send_json({
            "type": "error",
            "data": {"message": "URL is required"}
        })
        return
    
    competitor_urls = message.get('competitor_urls', [])
    industry = message.get('industry')
    country_code = message.get('country_code', 'fi')
    
    logger.info(f"[WS] Starting analysis for {url}")
    
    # Create orchestrator with WebSocket callbacks
    orchestrator = AgentOrchestrator()
    
    async def send_insight(insight: AgentInsight):
        await websocket.send_json({
            "type": "insight",
            "data": {
                "agent_id": insight.agent_id,
                "message": insight.message,
                "priority": insight.priority.value,
                "insight_type": insight.insight_type.value,
                "timestamp": insight.timestamp.isoformat(),
                "data": insight.data
            }
        })
    
    async def send_progress(progress: AgentProgress):
        await websocket.send_json({
            "type": "progress",
            "data": {
                "agent_id": progress.agent_id,
                "progress": progress.progress,
                "message": progress.message,
                "timestamp": progress.timestamp.isoformat()
            }
        })
    
    async def send_status(agent_id: str, status: AgentStatus):
        await websocket.send_json({
            "type": "status",
            "data": {
                "agent_id": agent_id,
                "status": status.value
            }
        })
    
    # Wrapper functions to handle async callbacks
    def on_insight(insight: AgentInsight):
        asyncio.create_task(send_insight(insight))
    
    def on_progress(progress: AgentProgress):
        asyncio.create_task(send_progress(progress))
    
    def on_status(agent_id: str, status: AgentStatus):
        asyncio.create_task(send_status(agent_id, status))
    
    orchestrator.set_callbacks(
        on_insight=on_insight,
        on_progress=on_progress,
        on_status=on_status
    )
    
    try:
        # Run analysis
        result = await orchestrator.run_analysis(
            url=url,
            competitor_urls=competitor_urls,
            industry=industry,
            country_code=country_code,
            user=None  # TODO: Get from auth
        )
        
        # Send completion message
        await websocket.send_json({
            "type": "complete",
            "data": {
                "success": result.success,
                "duration_seconds": result.duration_seconds,
                "agents_completed": result.agents_completed,
                "agents_failed": result.agents_failed,
                "results": result.results,
                "errors": result.errors
            }
        })
        
        logger.info(f"[WS] Analysis complete: {result.duration_seconds:.1f}s")
        
    except Exception as e:
        logger.error(f"[WS] Analysis error: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "data": {"message": str(e)}
        })
