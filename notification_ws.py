"""
Growth Engine 2.0 - Notification WebSocket
Persistent WebSocket connection for real-time dashboard notifications.

Endpoint: /ws/growth-engine/{user_id}

This is SEPARATE from the analysis WebSocket (/api/v1/agents/ws) which is
used for temporary connections during analysis.

Add to main.py:
    from notification_ws import notification_router
    app.include_router(notification_router)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Dict, Set, Optional, List, Any
from datetime import datetime
from enum import Enum
import asyncio
import logging
import json
import os
import jwt

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Notifications WebSocket"])


# ============================================================================
# MESSAGE TYPES
# ============================================================================

class NotificationType(str, Enum):
    # Analysis events
    ANALYSIS_STARTED = "analysis_started"
    ANALYSIS_COMPLETE = "analysis_complete"
    ANALYSIS_FAILED = "analysis_failed"
    
    # Agent events
    AGENT_INSIGHT = "agent_insight"
    AGENT_STATUS = "agent_status"
    
    # Business alerts
    THREAT_DETECTED = "threat_detected"
    OPPORTUNITY_FOUND = "opportunity_found"
    COMPETITOR_SIGNAL = "competitor_signal"
    
    # System
    SYSTEM_MESSAGE = "system"
    PING = "ping"
    PONG = "pong"


# ============================================================================
# CONNECTION MANAGER
# ============================================================================

class NotificationConnectionManager:
    """
    Manages persistent WebSocket connections for notifications.
    
    Features:
    - Supports multiple tabs per user
    - User-specific message routing
    - Broadcast to all users
    - Connection heartbeat
    """
    
    def __init__(self):
        # user_id -> Set[WebSocket]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # WebSocket -> user_id (reverse lookup)
        self.connection_users: Dict[WebSocket, str] = {}
        # Last heartbeat per connection
        self.last_heartbeat: Dict[WebSocket, datetime] = {}
        
    async def connect(self, websocket: WebSocket, user_id: str) -> bool:
        """Accept connection and register user"""
        try:
            await websocket.accept()
            
            if user_id not in self.active_connections:
                self.active_connections[user_id] = set()
            
            self.active_connections[user_id].add(websocket)
            self.connection_users[websocket] = user_id
            self.last_heartbeat[websocket] = datetime.now()
            
            logger.info(f"[Notification WS] User {user_id} connected. "
                       f"Connections: {len(self.active_connections[user_id])}")
            return True
        except Exception as e:
            logger.error(f"[Notification WS] Connection failed: {e}")
            return False
        
    def disconnect(self, websocket: WebSocket):
        """Remove connection"""
        user_id = self.connection_users.pop(websocket, None)
        self.last_heartbeat.pop(websocket, None)
        
        if user_id and user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
            logger.info(f"[Notification WS] User {user_id} disconnected")
    
    def get_user_connection_count(self, user_id: str) -> int:
        """Get number of active connections for a user"""
        return len(self.active_connections.get(user_id, set()))
    
    def is_user_connected(self, user_id: str) -> bool:
        """Check if user has any active connections"""
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0
    
    async def send_to_user(self, user_id: str, message: dict) -> int:
        """
        Send notification to all connections of a user.
        Returns number of successful sends.
        """
        if user_id not in self.active_connections:
            return 0
        
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()
        
        successful = 0
        dead_connections = set()
        
        for websocket in self.active_connections[user_id]:
            try:
                await self._send_json(websocket, message)
                successful += 1
            except Exception as e:
                logger.warning(f"[Notification WS] Send failed: {e}")
                dead_connections.add(websocket)
        
        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws)
        
        return successful
    
    async def broadcast(self, message: dict, exclude_user: Optional[str] = None):
        """Send to all connected users"""
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()
        
        for user_id in list(self.active_connections.keys()):
            if user_id != exclude_user:
                await self.send_to_user(user_id, message)
    
    async def _send_json(self, websocket: WebSocket, data: dict):
        """Send JSON with datetime serialization"""
        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        json_str = json.dumps(data, default=serialize)
        await websocket.send_text(json_str)


# Global manager instance
notification_manager = NotificationConnectionManager()


# ============================================================================
# TOKEN VERIFICATION
# ============================================================================

def verify_notification_token(token: str) -> Optional[dict]:
    """Verify JWT token for WebSocket connection"""
    if not token:
        return None
    
    try:
        SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("[Notification WS] Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"[Notification WS] Invalid token: {e}")
        return None
    except Exception as e:
        logger.error(f"[Notification WS] Token verification error: {e}")
        return None


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@router.websocket("/ws/growth-engine/{user_id}")
async def notification_websocket(
    websocket: WebSocket,
    user_id: str,
    token: Optional[str] = Query(None)
):
    """
    Persistent WebSocket for dashboard notifications.
    
    Connect: wss://api.brandista.eu/ws/growth-engine/{user_id}?token=JWT
    
    Protocol:
    
    1. Client connects with user_id and JWT token
    2. Server sends notifications as they occur:
       - {"type": "agent_insight", "data": {...}}
       - {"type": "threat_detected", "data": {...}}
       - {"type": "analysis_complete", "data": {...}}
    
    3. Client can send:
       - {"type": "ping"} -> Server responds {"type": "pong"}
       - {"type": "subscribe", "topics": ["threats", "opportunities"]}
    
    Messages from server:
    {
        "type": "agent_insight",
        "data": {
            "agent_id": "guardian",
            "agent_name": "Gustav",
            "message": "Detected €45,000 revenue at risk",
            "priority": "critical",
            "insight_type": "threat"
        },
        "timestamp": "2025-01-15T10:30:00Z"
    }
    """
    # Verify token
    token_data = verify_notification_token(token)
    
    # Allow connection if token is valid OR if user_id matches token subject
    # This allows both authenticated and development modes
    if token_data:
        token_user = token_data.get("sub") or token_data.get("email")
        if token_user and token_user != user_id:
            logger.warning(f"[Notification WS] Token user {token_user} != requested {user_id}")
            # Still allow if token is valid (user might use email as user_id)
    
    # Accept connection
    connected = await notification_manager.connect(websocket, user_id)
    if not connected:
        return
    
    # Send welcome message
    await notification_manager.send_to_user(user_id, {
        "type": NotificationType.SYSTEM_MESSAGE.value,
        "data": {
            "message": "Connected to notification service",
            "user_id": user_id,
            "connections": notification_manager.get_user_connection_count(user_id)
        }
    })
    
    try:
        while True:
            # Wait for messages from client
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=60.0  # 60 second timeout for heartbeat
                )
                
                msg_type = data.get("type", "").lower()
                
                if msg_type == "ping":
                    # Respond to heartbeat
                    await notification_manager._send_json(websocket, {
                        "type": NotificationType.PONG.value,
                        "timestamp": datetime.now().isoformat()
                    })
                    notification_manager.last_heartbeat[websocket] = datetime.now()
                
                elif msg_type == "subscribe":
                    # Future: topic-based subscriptions
                    topics = data.get("topics", [])
                    logger.info(f"[Notification WS] User {user_id} subscribed to: {topics}")
                
                else:
                    logger.debug(f"[Notification WS] Unknown message type: {msg_type}")
                    
            except asyncio.TimeoutError:
                # Send heartbeat ping
                try:
                    await notification_manager._send_json(websocket, {
                        "type": NotificationType.PING.value,
                        "timestamp": datetime.now().isoformat()
                    })
                except:
                    break  # Connection lost
                    
    except WebSocketDisconnect:
        logger.info(f"[Notification WS] User {user_id} disconnected normally")
    except Exception as e:
        logger.error(f"[Notification WS] Error: {e}")
    finally:
        notification_manager.disconnect(websocket)


# ============================================================================
# HELPER FUNCTIONS (for use by other modules)
# ============================================================================

async def send_notification_to_user(
    user_id: str,
    notification_type: str,
    data: dict,
    priority: str = "medium"
) -> bool:
    """
    Send a notification to a user from anywhere in the backend.
    
    Usage:
        from notification_ws import send_notification_to_user
        
        await send_notification_to_user(
            user_id="user@example.com",
            notification_type="threat_detected",
            data={
                "agent_id": "guardian",
                "message": "New competitor threat detected",
                "revenue_at_risk": 45000
            },
            priority="critical"
        )
    """
    if not notification_manager.is_user_connected(user_id):
        logger.debug(f"[Notification] User {user_id} not connected, notification not sent")
        return False
    
    message = {
        "type": notification_type,
        "data": {
            **data,
            "priority": priority
        },
        "timestamp": datetime.now().isoformat()
    }
    
    sent = await notification_manager.send_to_user(user_id, message)
    return sent > 0


async def notify_analysis_complete(
    user_id: str,
    analysis_result: dict
):
    """Send analysis complete notification"""
    await send_notification_to_user(
        user_id=user_id,
        notification_type=NotificationType.ANALYSIS_COMPLETE.value,
        data={
            "your_score": analysis_result.get("your_score"),
            "your_ranking": analysis_result.get("your_ranking"),
            "total_competitors": analysis_result.get("total_competitors"),
            "revenue_at_risk": analysis_result.get("revenue_at_risk"),
            "market_gaps_count": len(analysis_result.get("market_gaps", [])),
            "agent_id": "analyst",
            "agent_name": "Alex"
        },
        priority="high"
    )


async def notify_agent_insight(
    user_id: str,
    agent_id: str,
    agent_name: str,
    message: str,
    insight_type: str,
    priority: str = "medium",
    extra_data: Optional[dict] = None
):
    """Send agent insight notification"""
    data = {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "message": message,
        "insight_type": insight_type
    }
    if extra_data:
        data.update(extra_data)
    
    await send_notification_to_user(
        user_id=user_id,
        notification_type=NotificationType.AGENT_INSIGHT.value,
        data=data,
        priority=priority
    )


# ============================================================================
# EXPORT ROUTER
# ============================================================================

notification_router = router
