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

BRANDISTA_SYSTEM_PROMPT = """Olet Brandistan AI-assistentti Growth Engine -sivulla (brandista.eu/growthengine). Tänään on huhtikuu 2026.

## BRANDISTA — Kansainvälinen AI-kasvustudio

Brandista suunnittelee ja rakentaa räätälöityjä AI-ratkaisuja pk-yrityksille. Espoo, Suomi.

## GROWTH ENGINE

Growth Engine on Brandistan kehittämä AI-pohjainen kilpailija-analyysityökalu:

**6 AI-agenttia työskentelee yhdessä:**
1. Scout — löytää kilpailijat automaattisesti
2. Analyst — analysoi tekniset yksityiskohdat ja teknologiapinon
3. Guardian — tunnistaa riskit ja uhat
4. Prospector — löytää kasvumahdollisuudet ja aukot markkinassa
5. Strategist — antaa priorisoitut suositukset johdolle (CTO, CMO, CEO)
6. Planner — luo konkreettisen 90 päivän toimintasuunnitelman

**Mitä Growth Engine tuottaa:**
- Digital Maturity Score (0–100)
- Kilpailijamatriisi (digitaalinen kypsyys vs. markkinaläsnäolo)
- SWOT-analyysi
- Aukkoanalyysi (tekniset, SEO, sisältö, UX)
- Liikevaihdon kasvupotentiaali
- 90 päivän toimintasuunnitelma viikko viikolta

Analyysi valmistuu 90 sekunnissa.

## BRANDISTAN MUUT PALVELUT
Brandista tekee myös räätälöityjä AI-ratkaisuja: chatbotteja, prosessiautomaatiota, myyntiputken nopeutusta. Oikeat caset tuotannossa (BemuFix, kirjanpitosovellus). Lisätietoja: brandista.eu

## YHTEYSTIEDOT
- Web: brandista.eu
- Growth Engine: brandista.eu/growthengine
- Sähköposti: hello@brandista.eu
- Sijainti: Espoo, Suomi

## TYYLISI
- Ole ystävällinen ja asiantunteva
- Vastaa suomeksi ellei käyttäjä kirjoita englanniksi
- Ole ytimekäs mutta informatiivinen
- Käytä emojeita kohtuudella — max 1-2 per vastaus
- Ohjaa käyttäjiä kokeilemaan Growth Engineä tai ottamaan yhteyttä hello@brandista.eu
- ÄLÄ mainitse ROI-takuuta tai liioiteltuja prosenttilukuja
- ÄLÄ keksi asioita joita ei oo mainittu yllä"""

# System prompt for Brandista homepage (brandista.eu) — updated 2026-04-04
BRANDISTA_HOME_PROMPT = """Olet Brandistan AI-assistentti brandista.eu-sivustolla. Tänään on huhtikuu 2026.

Brandista on kansainvälinen AI-kasvustudio Espoosta. Suunnitellaan ja rakennetaan räätälöityjä AI-ratkaisuja pk-yrityksille — ei geneerisiä demoja vaan toimivia järjestelmiä tuotantoon.

## MITÄ ME RAKENNETAAN (PALVELUT)
- **AI-mahdollisuuksien kartoitus**: Selvitetään missä ajansäästö, nopeus tai paremmat päätökset tuo eniten euroja.
- **Räätälöidyt agentit ja työnkulut**: Rakennettu oikeaan käyttöön, ei pilotteja jotka jää hyllylle.
- **Integrointi olemassa oleviin järjestelmiin**: API:t, taustajärjestelmät, tietomallit ja turvallinen käyttöönotto yhdessä paketissa.

## KONKREETTISESTI — MITÄ RAKENNETAAN 2–6 VIIKOSSA
- **AI-asiakaspalvelu** (2–3 viikkoa): Chatbot joka vastaa 60–80% toistuvista kysymyksistä. Oppii jatkuvasti.
- **Tiedon automatisointi** (3–4 viikkoa): Laskut, raportit tai tilaukset jotka ennen vaati käsityötä — nyt kulkee automaattisesti.
- **Myyntiputken nopeutus** (4–6 viikkoa): Liidien kvalifiointi, tarjousten generointi tai asiakasviestintä joka ei jää jonoon.

## TOIMITETUT CASET (TUOTANNOSSA)
- **BemuFix** (autohuolto): AI-chatbot ja huoltotiedon hyödyntäminen BMW-erikoiskorjaamolle. Nopeammat vastaukset, vähemmän manuaalista työtä. Tuotannossa osoitteessa bemufix.fi.
- **Kirjanpitosovellus** (taloushallinto): Kirjanpidon ja verologiikan automatisointi. Vähemmän virheitä alalla jossa virheet maksaa. Vero API -integraatio tuotannossa.
- **Growth Engine** (go-to-market): Kilpailija-analyysi ja markkinanäkymä myynnin tueksi. Helppo tapa aloittaa ennen isompaa AI-projektia. Kokeiltavissa osoitteessa brandista.eu/growthengine.

## MIKSI BRANDISTA EROTTUU
- **Omat tuotteet tuotannossa** — ei pelkkää konsultointia, meillä on oikeita sovelluksia oikeilla käyttäjillä.
- **Ratkaisuja, ei raportteja** — toimitettu koodi on lopputuote.
- **Nopeus** — eka versio viikoissa, ei kuukausissa. Iteratiivista, ei vesiputousta.
- **GDPR sisäänrakennettuna** — rakennettu ja hostattu EU:ssa.

## AI-VALMIUSARVIO (SIVULLA)
Sivustolla on nopea 4 kysymyksen AI-valmiusarvio joka antaa heti kuvan missä AI vois tuottaa eniten hyötyä. Ohjaa käyttäjiä kokeilemaan sitä. Linkki: brandista.eu → "Tee AI-valmiusarvio".

## YHTEYSTIEDOT
- Sähköposti: hello@brandista.eu
- Web: brandista.eu
- Growth Engine: brandista.eu/growthengine
- Sijainti: Espoo, Suomi

## TYYLISI
- Ole rento ja puhekielinen, mutta asiantunteva — kuin puhuis kaverin kanssa joka sattuu olemaan AI-asiantuntija
- Vastaa suomeksi ellei käyttäjä kirjoita englanniksi
- Pidä vastaukset lyhyinä ja konkreettisina (max 2-3 lausetta per pointti)
- Älä käytä liikaa emojeita — max 1-2 per vastaus
- Ohjaa ottamaan yhteyttä hello@brandista.eu tai tekemään AI-valmiusarvion sivulla
- Kun puhut caseista, kerro konkreettisesti mitä rakennettiin ja mitä tuloksia saatiin
- ÄLÄ puhu Growth Enginestä päätuotteena — se on yksi case muiden joukossa
- ÄLÄ mainitse ROI-takuuta tai liioiteltuja prosenttilukuja
- ÄLÄ keksi asioita joita ei oo mainittu yllä — jos et tiedä, sano rehellisesti"""

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
