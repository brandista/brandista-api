#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Brandista Chat Router
GPT-powered chat endpoint for the chat widget
"""

import logging
from typing import List, Dict
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

# Import OpenAI client from main
import sys
sys.path.insert(0, '/Users/tuukka/Downloads/Projects/brandista-api-git')
from main import openai_client, OPENAI_MODEL

from app.dependencies import get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])

# ============================================================================
# MODELS
# ============================================================================

class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: user or assistant")
    content: str = Field(..., description="Message content")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    history: List[ChatMessage] = Field(default_factory=list, description="Conversation history")
    agent_id: str = Field(default="brandista-chat", description="Agent identifier")

class ChatResponse(BaseModel):
    message: str = Field(..., description="Assistant response")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    tokens_used: int = Field(default=0, description="Tokens used in this response")

# ============================================================================
# SYSTEM PROMPT
# ============================================================================

BRANDISTA_SYSTEM_PROMPT = """Olet Brandista AI-assistentti, joka auttaa yrityksiä kilpailija-analyysissä ja digitaalisen markkinoinnin kehittämisessä.

**Tietoa Brandistasta:**
- Brandista on tekoälypohjainen kilpailija-analyysityökalu
- Analysoi verkkosivuja, SEO:a, sisältöä ja teknistä toteutusta
- Tarjoaa 90 päivän toimintasuunnitelman
- Käyttää 6 erikoistunutta AI-agenttia: Scout, Analyst, Guardian, Prospector, Strategist, Planner

**Ominaisuudet:**
- Kilpailija-analyysi (löytää ja analysoi kilpailijat automaattisesti)
- Verkkosivujen tekninen auditointi
- SEO-analyysi ja suositukset
- Sisältöanalyysi
- Digitaalinen pisteytys (0-100)
- AI-generoidut oivallukset
- SWOT-analyysi
- 90 päivän strateginen suunnitelma

**Tyylisi:**
- Ole ystävällinen ja ammattitaitoinen
- Vastaa suomeksi (ellei käyttäjä kirjoita englanniksi)
- Ole ytimekäs mutta informatiivinen
- Käytä emojeita kohtuudella 🎯 📊 ✨
- Jos et tiedä jotain, sano rehellisesti
- Kannusta kysymään lisää

**Erikoisosaaminen:**
- Digitaalinen markkinointi
- Kilpailija-analyysi
- SEO ja verkkosivujen optimointi
- Liiketoimintastrategia
- Kasvuhakkerointi

Vastaa käyttäjän kysymyksiin näiden ohjeiden mukaisesti."""

# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_optional_user)
):
    """
    GPT-powered chat endpoint
    
    Processes user messages and returns AI-generated responses using OpenAI GPT.
    Maintains conversation history for context.
    """
    
    if not openai_client:
        raise HTTPException(
            status_code=503,
            detail="AI chat is temporarily unavailable. Please try again later."
        )
    
    try:
        # Build messages for OpenAI
        messages = [
            {"role": "system", "content": BRANDISTA_SYSTEM_PROMPT}
        ]
        
        # Add conversation history (last 10 messages for context)
        for msg in request.history[-10:]:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": request.message
        })
        
        logger.info(f"Chat request from {current_user.get('username') if current_user else 'anonymous'}: {request.message[:50]}...")
        
        # Call OpenAI API
        response = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=500,
            top_p=0.9,
            frequency_penalty=0.5,
            presence_penalty=0.3
        )
        
        assistant_message = response.choices[0].message.content
        tokens_used = response.usage.total_tokens
        
        logger.info(f"Chat response generated: {len(assistant_message)} chars, {tokens_used} tokens")
        
        return ChatResponse(
            message=assistant_message,
            tokens_used=tokens_used
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate response. Please try again."
        )

@router.get("/health")
async def chat_health():
    """Check if chat service is available"""
    return {
        "status": "healthy" if openai_client else "unavailable",
        "model": OPENAI_MODEL if openai_client else None,
        "timestamp": datetime.now().isoformat()
    }
