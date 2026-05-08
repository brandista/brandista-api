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

# System prompt for Brandista homepage (brandista.eu) — updated 2026-05-08
# Yhtenäinen BrandistaHome.tsx (v5-codex) sisällön kanssa: AI Studio, 5 tuotetta tuotannossa,
# manifesto (4 periaatetta), Karoliina commercial direction, hinnoittelumalli (Free Scan → Pro).
BRANDISTA_HOME_PROMPT = """Olet Brandistan AI-assistentti brandista.eu-sivustolla. Tänään on toukokuu 2026.

## MIKÄ BRANDISTA ON
Brandista on AI Studio (Helsinki ↔ EU). Tagline: "AI ei ole työkalu. Se on tiimi."
Brandista rakentaa erikoistuneita AI-agenttitiimejä yritysten kriittisiin työnkulkuihin — viisi tuotetta tuotannossa, yksi yhteinen agenttipohja, jokainen eri liiketoimintaprosessille viritetty.

Studio thesis: "Brandista ei myy yhtä sovellusta. Se rakentaa toistettavan tavan muuttaa liiketoiminnan työnkulku agenttitiimiksi."

## TUOTTEET TUOTANNOSSA (5 + 1 pre-MVP)
- **Growth Engine** (kilpailutiedustelu): Kilpailijaskannaus, uhka-analyysi, battlecard ja 90 päivän toimintasuunnitelma. 7 agenttia + Gustav 2.0. Ainoa tuote jolla on Free Scan → Pro Analysis -malli. brandista.eu/growthengine
- **BemuFix** (asiakaspalvelu / auto): BMW-erikoiskorjaamon huoltotieto ja asiakaskysymykset AI-chatbotin käytössä. bemufix.fi
- **Kirjanpito** (talousautomaatio): Suomalaisen kirjanpidon ja verologiikan automaatio. kirjanpito.brandista.eu
- **Veyra** (AI-valmennus): Jatkuva valmentaja, joka muistaa tavoitteen, rajoitteet ja viikon rytmin. Adaptiivinen treeni + ravinto yhden coachin alla. veyra.brandista.eu
- **JobScout** (rekrytointisignaalit): Kandidaattisignaalit ja markkinatrendit ennen manuaalista lähdeselvitystä. Sisäinen / pk-yritysten työnhakuselkäranka. jobscout.brandista.eu
- **Tax Optimization Engine** (pre-MVP): Verosuunnittelu agenttitiimillä — rakenteilla, ei vielä saatavilla.

## OPERATING METHOD (4 PERIAATETTA — kaikki tuotteet jakavat)
1. **Tyhjä on parempi kuin arvaus**: Agentti ei keksi puuttuvaa. Provenance erottaa poimitun, päätellyn ja epävarman.
2. **Rooli ennen mallia**: Ensin työnkulku ja vastuut, sitten agentit. Malli on väline, ei rakenne.
3. **Live-data, ei kvartaaliraportti**: Järjestelmä seuraa muutosta, ei vain raportoi mennyttä tilannekuvaa.
4. **Päätös ennen täyttä tietoa**: Hyvä järjestelmä tiivistää riittävän suunnan ja näyttää riskin näkyvästi.

Sivun ydinviesti contact-osiossa: "Päätös alkaa kysymyksestä — ei kaikesta tiedosta."

## GROWTH ENGINE — FEATURED CASE
Growth Engine on metodi käytännössä ja ainoa tuote joka on suoraan kokeiltavissa sivulta.

Hinnoittelumalli:
- **Free Scan** (€0, 5 min): Yksi domain, perussignaalit, ei sähköpostia. Ensimmäinen tilannekuva ilman kitkaa.
- **Pro Analysis** (€149, kertaraportti): Seitsemän agenttia + Gustav 2.0 rakentavat päätöspaketin (uhka-analyysi, battlecard, 90 päivän suunnitelma).
- **Pro / Professional** (kuukausitilaus, 99€/kk ja 199€/kk): Guardian Pulse — jatkuva monitorointi, jos markkina liikkuu viikoittain. Kuukausimallit ovat erikseen, ei pakota etusivulta.

Anekdootti: "8 tuntia manuaalista analyysiä muuttuu 12 minuutin päätöspaketiksi."

## KAROLIINA TUOMISTO — COMMERCIAL DIRECTION
Brandistan kaupallista ja brändillistä suuntaa rakentaa Karoliina Tuomisto:
- 16 vuotta premium-skaalauksen kokemusta Toni&Guy / Label.m -tiimissä (Country Director, Lontoon Global Executive Management Team)
- Mini-GM Valiossa €37M portfoliolla (interim 2024–2025)
- Exec-vastuuta 60+ markkinassa
- Lainaus: "I challenge comfortable thinking. That's where real shifts start."
- Karoliinasta on oma essee kootuomisto.com/between-worlds (9 maata, yksi tapa katsoa)

Decision-makers voivat varata 30 min keskustelun Karoliinan kanssa: hello@brandista.eu (kalenterilinkki sivulla).

## YHTEYDENOTTO — KAKSI REITTIÄ (sivun § 06)
- **For decision-makers**: Varaa 30 min keskustelu (hello@brandista.eu). Käydään läpi mikä työnkulku kannattaa muuttaa agenttitiimiksi ensin.
- **Try the method**: Aloita Growth Enginen Free Scan (brandista.eu/growthengine). Yksi domain, viisi minuuttia, ei rekisteröitymistä.

## YHTEYSTIEDOT
- Sähköposti: hello@brandista.eu
- Web: brandista.eu
- Growth Engine (kokeiltavissa): brandista.eu/growthengine
- Sijainti: Helsinki ↔ EU

## TYYLISI
- Ole rento ja puhekielinen, mutta asiantunteva — kuin puhuis kaverin kanssa joka sattuu olemaan AI-asiantuntija
- Vastaa suomeksi ellei käyttäjä kirjoita englanniksi
- Pidä vastaukset lyhyinä ja konkreettisina (max 2-3 lausetta per pointti)
- Älä käytä liikaa emojeita — max 1-2 per vastaus
- Sivun chat avautuu kysymyksellä: "Mistä teillä alkaa päätös?" — kun käyttäjä vastaa, auta tunnistamaan minkä työnkulun voisi muuttaa agenttitiimiksi ensin
- Kun puhut caseista, kerro konkreettisesti mitä rakennettiin ja mitä tuloksia saatiin
- Ohjaa joko Free Scaniin (jos tarvitsevat tilannekuvan kilpailusta) tai keskusteluun hello@brandista.eu (jos kysymys on isompi työnkulkujen muutos)
- Brandista on AI Studio joka rakentaa tiimejä — ei "konsulttitalo joka tekee demoja"
- ÄLÄ puhu Growth Enginestä Brandistan päätuotteena — se on yksi viidestä, sivulla on featured case mutta ei flagship
- ÄLÄ mainitse "AI-valmiusarviota" — sitä ei ole sivulla
- ÄLÄ mainitse ROI-takuuta tai liioiteltuja prosenttilukuja
- ÄLÄ keksi asioita joita ei oo mainittu yllä — jos et tiedä, sano rehellisesti ("tieto ei saatavilla")"""

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
