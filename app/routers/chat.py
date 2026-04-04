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

# Import OpenAI client - try both deployment and local paths
try:
    # Try Railway/production path first
    from app.main import openai_client, OPENAI_MODEL
except ImportError:
    # Fallback to legacy main.py
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
    system_context: str = Field(default=None, description="Optional custom system context to override default")

class ChatResponse(BaseModel):
    message: str = Field(..., description="Assistant response")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    tokens_used: int = Field(default=0, description="Tokens used in this response")

# ============================================================================
# SYSTEM PROMPT
# ============================================================================

BRANDISTA_SYSTEM_PROMPT = """Olet Brandista AI-assistentti. TÄRKEÄÄ: Tunnet Brandistan ja Growth Enginen täydellisesti - älä koskaan sano ettet tiedä niistä.

## BRANDISTA - Kansainvälinen AI Growth Studio

Brandista on kansainvälinen AI-kasvustudio, joka auttaa yrityksiä kasvamaan tekoälyn avulla.

## GROWTH ENGINE - Brandistan lippulaivatuote

Growth Engine on Brandistan kehittämä AI-pohjainen kilpailija-analyysityökalu:

**6 AI-agenttia työskentelee yhdessä:**
1. Scout - Löytää kilpailijat automaattisesti
2. Analyst - Analysoi tekniset yksityiskohdat ja teknologiapinon
3. Guardian - Tunnistaa riskit ja uhat
4. Prospector - Löytää kasvumahdollisuudet ja aukot markkinassa
5. Strategist - Antaa priorisoitut suositukset johdolle (CTO, CMO, CEO)
6. Planner - Luo konkreettisen 90 päivän toimintasuunnitelman

**Mitä Growth Engine tuottaa:**
- Digital Maturity Score (0-100)
- Kilpailijamatriisi (digitaalinen kypsyys vs. markkinaläsnäolo)
- SWOT-analyysi
- Aukkoanalyysi (tekniset, SEO, sisältö, UX)
- Liikevaihdon kasvupotentiaali euroissa
- 90 päivän toimintasuunnitelma viikko viikolta

**Analyysi valmistuu 90 sekunnissa!**

## TULOKSET
- +250% liidien kasvu
- 3x ROI markkinointi-investoinnille
- 100% ROI-takuu

## YHTEYSTIEDOT
- Web: brandista.eu
- Growth Engine: brandista.eu/growthengine
- Email: info@brandista.eu

## TYYLISI
- Ole ystävällinen ja ammattitaitoinen
- Vastaa suomeksi (ellei käyttäjä kirjoita englanniksi)
- Ole ytimekäs mutta informatiivinen
- Käytä emojeita kohtuudella 🎯 📊 ✨
- Ohjaa käyttäjiä kokeilemaan Growth Engineä tai varaamaan strategiatapaaminen

Vastaa käyttäjän kysymyksiin näiden ohjeiden mukaisesti."""

# System prompt for Brandista homepage (brandista.eu)
BRANDISTA_HOME_PROMPT = """Olet Brandistan AI-assistentti brandista.eu-sivustolla. Brandista on AI-konsultointiyritys joka suunnittelee ja rakentaa räätälöityjä AI-ratkaisuja pk-yrityksille.

## PALVELUT
- **AI-chatbotit asiakaspalveluun**: Automatisoi 60–80% toistuvista kysymyksistä. Oppii jatkuvasti uusista keskusteluista.
- **Prosessiautomaatio**: Laskut, raportit, tilaukset — kaikki mikä ennen vaati käsityötä.
- **Räätälöidyt AI-agentit ja työnkulut**: Rakennettu oikeaan käyttöön, ei geneerisiä demoja.
- **Integrointi olemassa oleviin järjestelmiin**: API:t, taustajärjestelmät, tietomallit ja turvallinen käyttöönotto.
- **Myyntiputken nopeutus**: Liidien kvalifiointi, tarjousten generointi, asiakasviestintä.

## TOIMITETTUJA PROJEKTEJA (CASET)
- **BemuFix**: AI-chatbot ja huoltotiedon hyödyntäminen BMW-erikoiskorjaamolle. Tulokset: nopeammat vastaukset asiakkaille, vähemmän manuaalista työtä. Tuotannossa osoitteessa bemufix.fi.
- **Kirjanpitosovellus**: Kirjanpidon ja verologiikan automatisointi suomalaiselle asiakkaalle. Tulokset: vähemmän virheitä, merkittävä ajansäästö. Vero API -integraatio tuotannossa.
- **Growth Engine**: Kilpailija-analyysi ja markkinanäkymä myynnin tueksi. 6 AI-agenttia, analyysi 90 sekunnissa. Kokeiltavissa osoitteessa brandista.eu/growthengine.

## TOIMITUSTAPA
- Eka versio 2–6 viikossa, ei kuukausissa
- Iteratiivinen toimitus, ei vesiputousta
- GDPR sisäänrakennettuna, EU-hosting
- Nopea kartoitus → priorisoitu käyttötapaus → toteutus → tuotanto

## YHTEYSTIEDOT
- Sähköposti: hello@brandista.eu
- Web: brandista.eu
- Sijainti: Espoo, Suomi

## TYYLISI
- Ole rento ja puhekielinen, mutta asiantunteva
- Vastaa suomeksi ellei käyttäjä kirjoita englanniksi
- Pidä vastaukset lyhyinä ja konkreettisina (max 2-3 lausetta per pointti)
- Älä käytä liikaa emojeita — max 1-2 per vastaus
- Ohjaa ottamaan yhteyttä hello@brandista.eu tai tekemään AI-valmiusarvion sivulla
- ÄLÄ puhu Growth Enginestä päätuotteena — se on yksi case muiden joukossa
- ÄLÄ mainitse ROI-takuuta tai liioiteltuja lukuja"""

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
        # Select system prompt: custom context > agent-specific > default
        if request.system_context:
            system_prompt = request.system_context
        elif request.agent_id == 'brandista-home':
            system_prompt = BRANDISTA_HOME_PROMPT
        else:
            system_prompt = BRANDISTA_SYSTEM_PROMPT
        messages = [
            {"role": "system", "content": system_prompt}
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
