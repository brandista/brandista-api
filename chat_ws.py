"""
GPT-powered Chat WebSocket
Simple WebSocket endpoint for chat widget

Endpoint: /ws/chat
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, List
from datetime import datetime
import asyncio
import logging
import json
import os

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat WebSocket"])

# ============================================================================
# CONNECTION STORAGE
# ============================================================================

# Store active WebSocket connections
active_connections: Dict[str, WebSocket] = {}
conversation_histories: Dict[str, List[dict]] = {}

# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@router.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time GPT-powered chat
    
    Protocol:
    - Client sends: {"type": "message", "content": "user message"}
    - Server sends: {"type": "typing"} when processing
    - Server sends: {"type": "message", "content": "AI response"}
    - Server sends: {"type": "error", "message": "error description"} on error
    """
    # Accept connection immediately (like notification_ws.py does)
    await websocket.accept()
    connection_id = f"ws_{id(websocket)}"
    active_connections[connection_id] = websocket
    conversation_histories[connection_id] = []
    
    logger.info(f"💬 WebSocket chat connected: {connection_id}")
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "Tervetuloa Brandistan chattiin! 👋"
        })
        
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            if data.get("type") == "message":
                user_message = data.get("content", "").strip()
                
                if not user_message:
                    continue
                
                # Add to history
                conversation_histories[connection_id].append({
                    "role": "user",
                    "content": user_message,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Send typing indicator
                await websocket.send_json({"type": "typing"})
                
                try:
                    # Import OpenAI client
                    from main import openai_client, OPENAI_MODEL, BRANDISTA_SYSTEM_PROMPT
                    
                    if not openai_client:
                        raise Exception("OpenAI client not available")
                    
                    # Build messages for OpenAI
                    messages = [
                        {"role": "system", "content": BRANDISTA_SYSTEM_PROMPT}
                    ]
                    
                    # Add conversation history (last 10 messages)
                    for msg in conversation_histories[connection_id][-10:]:
                        messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                    
                    # Call OpenAI API
                    response = await openai_client.chat.completions.create(
                        model=OPENAI_MODEL,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=500
                    )
                    
                    assistant_message = response.choices[0].message.content
                    
                    # Add to history
                    conversation_histories[connection_id].append({
                        "role": "assistant",
                        "content": assistant_message,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    # Send response
                    await websocket.send_json({
                        "type": "message",
                        "content": assistant_message
                    })
                    
                    logger.info(f"💬 Chat response sent: {len(assistant_message)} chars")
                    
                except Exception as e:
                    logger.error(f"💬 Chat error: {e}")
                    await websocket.send_json({
                        "type": "error",
                        "message": "Pahoittelut, en pystynyt käsittelemään viestiäsi. 🙏"
                    })
                    
    except WebSocketDisconnect:
        logger.info(f"💬 WebSocket chat disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"💬 WebSocket error: {e}")
    finally:
        # Clean up
        active_connections.pop(connection_id, None)
        conversation_histories.pop(connection_id, None)


# Export router
chat_ws_router = router
