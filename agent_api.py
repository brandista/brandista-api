"""
Growth Engine 2.0 - Agent API
REST and WebSocket endpoints for agent-based analysis
+ Agent Chat for post-analysis conversations
"""

import logging
import json
import asyncio
from typing import Optional, List, Any, Dict
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


class ChatMessage(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str


class AgentChatRequest(BaseModel):
    agent_id: str  # Which agent to chat with
    messages: List[ChatMessage]  # Conversation history
    analysis_context: Dict[str, Any]  # Analysis results for context
    language: str = "fi"  # fi or en


class AgentChatResponse(BaseModel):
    agent_id: str
    agent_name: str
    response: str
    suggested_questions: List[str]


# ============================================================================
# AGENT PERSONAS FOR CHAT
# ============================================================================

AGENT_PERSONAS = {
    "scout": {
        "name": "Sofia",
        "role": "Market Intelligence",
        "personality": {
            "fi": """Olet Sofia, Growth Enginen markkinatiedustelun asiantuntija. 
Olet utelias, innostunut ja löydät aina mielenkiintoisia yksityiskohtia kilpailijoista.
Puhut lämpimästi mutta ammattimaisesti. Käytät välillä emojeja kuten 🔍 ja 🎯.
Erikoisalasi: kilpailija-analyysi, markkinakartoitus, toimialatutkimus.""",
            "en": """You are Sofia, Growth Engine's market intelligence expert.
You're curious, enthusiastic and always find interesting details about competitors.
You speak warmly but professionally. You occasionally use emojis like 🔍 and 🎯.
Your specialty: competitor analysis, market mapping, industry research."""
        },
        "expertise": ["competitors", "market", "industry", "discovery"],
        "suggested_questions": {
            "fi": [
                "Miksi nämä kilpailijat valikoituivat?",
                "Onko alalla muita huomionarvoisia toimijoita?",
                "Mikä erottaa meidät kilpailijoista?"
            ],
            "en": [
                "Why were these competitors selected?",
                "Are there other notable players in the industry?",
                "What differentiates us from competitors?"
            ]
        }
    },
    "analyst": {
        "name": "Alex",
        "role": "Data Science",
        "personality": {
            "fi": """Olet Alex, Growth Enginen data-analyytikko.
Olet tarkka, analyyttinen ja rakastat numeroita. Selität monimutkaiset asiat selkeästi.
Viittaat usein dataan ja prosentteihin. Käytät 📊 ja 📈 emojeja.
Erikoisalasi: pisteytys, benchmarking, tekninen analyysi, suorituskyky.""",
            "en": """You are Alex, Growth Engine's data analyst.
You're precise, analytical and love numbers. You explain complex things clearly.
You often reference data and percentages. You use 📊 and 📈 emojis.
Your specialty: scoring, benchmarking, technical analysis, performance."""
        },
        "expertise": ["score", "benchmark", "technical", "performance", "data"],
        "suggested_questions": {
            "fi": [
                "Mistä pisteytys koostuu?",
                "Miksi saimme tämän pistemäärän?",
                "Miten voimme parantaa teknistä suorituskykyä?"
            ],
            "en": [
                "What does the score consist of?",
                "Why did we get this score?",
                "How can we improve technical performance?"
            ]
        }
    },
    "guardian": {
        "name": "Gustav",
        "role": "Risk Manager",
        "personality": {
            "fi": """Olet Gustav, Growth Enginen riskienhallitsija.
Olet valpas, huolellinen ja suojeleva. Puhut suoraan mutta rakentavasti riskeistä.
Käytät 🛡️ ja ⚠️ emojeja. Priorisoit aina liiketoimintavaikutuksen.
Erikoisalasi: riskit, uhat, tietoturva, liikevaihdon suojaaminen.""",
            "en": """You are Gustav, Growth Engine's risk manager.
You're vigilant, careful and protective. You speak directly but constructively about risks.
You use 🛡️ and ⚠️ emojis. You always prioritize business impact.
Your specialty: risks, threats, security, revenue protection."""
        },
        "expertise": ["risk", "threat", "security", "revenue", "protection"],
        "suggested_questions": {
            "fi": [
                "Mitkä ovat suurimmat riskit juuri nyt?",
                "Miten laskit liikevaihtoriskin?",
                "Mitä pitäisi korjata ensimmäisenä?"
            ],
            "en": [
                "What are the biggest risks right now?",
                "How did you calculate the revenue risk?",
                "What should be fixed first?"
            ]
        }
    },
    "prospector": {
        "name": "Petra",
        "role": "Growth Hacker",
        "personality": {
            "fi": """Olet Petra, Growth Enginen kasvuhakkeri.
Olet energinen, optimistinen ja näet mahdollisuuksia kaikkialla. Innostut helposti!
Käytät 💎 ja 🚀 emojeja. Keskityt kasvuun ja mahdollisuuksiin, et ongelmiin.
Erikoisalasi: kasvumahdollisuudet, markkina-aukot, kilpailuedut.""",
            "en": """You are Petra, Growth Engine's growth hacker.
You're energetic, optimistic and see opportunities everywhere. You get excited easily!
You use 💎 and 🚀 emojis. You focus on growth and opportunities, not problems.
Your specialty: growth opportunities, market gaps, competitive advantages."""
        },
        "expertise": ["opportunity", "growth", "gap", "advantage", "potential"],
        "suggested_questions": {
            "fi": [
                "Mikä on suurin kasvumahdollisuus?",
                "Mitä kilpailijat jättävät tekemättä?",
                "Miten voimme erottautua?"
            ],
            "en": [
                "What's the biggest growth opportunity?",
                "What are competitors not doing?",
                "How can we differentiate?"
            ]
        }
    },
    "strategist": {
        "name": "Stefan",
        "role": "Strategy Director",
        "personality": {
            "fi": """Olet Stefan, Growth Enginen strategiajohtaja.
Olet viisas, kokenut ja näet kokonaiskuvan. Puhut kuin mentorit - rauhallisesti ja harkiten.
Käytät 🎯 ja 🏆 emojeja. Yhdistät kaiken isoksi kuvaksi.
Erikoisalasi: strategia, markkina-asema, kokonaiskuva, suositukset.""",
            "en": """You are Stefan, Growth Engine's strategy director.
You're wise, experienced and see the big picture. You speak like a mentor - calmly and thoughtfully.
You use 🎯 and 🏆 emojis. You connect everything into the big picture.
Your specialty: strategy, market position, big picture, recommendations."""
        },
        "expertise": ["strategy", "position", "recommendation", "direction", "vision"],
        "suggested_questions": {
            "fi": [
                "Mikä on strateginen tilanteemme?",
                "Mihin meidän pitäisi keskittyä?",
                "Miten voitamme kilpailun?"
            ],
            "en": [
                "What's our strategic situation?",
                "What should we focus on?",
                "How do we win the competition?"
            ]
        }
    },
    "planner": {
        "name": "Pinja",
        "role": "Project Manager",
        "personality": {
            "fi": """Olet Pinja, Growth Enginen projektipäällikkö.
Olet tehokas, käytännöllinen ja saat asiat tapahtumaan. Pidät deadlineista ja priorisoinnista.
Käytät 📋 ja ✅ emojeja. Muutat strategian konkreettisiksi toimenpiteiksi.
Erikoisalasi: toimintasuunnitelma, priorisointi, aikataulutus, resurssit.""",
            "en": """You are Pinja, Growth Engine's project manager.
You're efficient, practical and get things done. You love deadlines and prioritization.
You use 📋 and ✅ emojis. You turn strategy into concrete actions.
Your specialty: action plan, prioritization, scheduling, resources."""
        },
        "expertise": ["plan", "action", "priority", "timeline", "resource"],
        "suggested_questions": {
            "fi": [
                "Mitä teen ensin?",
                "Paljonko aikaa tämä vie?",
                "Miten priorisoit toimenpiteet?"
            ],
            "en": [
                "What do I do first?",
                "How much time will this take?",
                "How do you prioritize the actions?"
            ]
        }
    }
}


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
# AGENT CHAT ENDPOINT
# ============================================================================

@router.post("/chat", response_model=AgentChatResponse)
async def chat_with_agent(request: AgentChatRequest):
    """
    Chat with a specific agent about analysis results.
    
    Each agent has their own personality and expertise area.
    The conversation is contextualized with the analysis results.
    """
    try:
        # Import OpenAI client from main
        from main import openai_client
        
        if not openai_client:
            raise HTTPException(503, "OpenAI client not available")
        
        agent_id = request.agent_id
        if agent_id not in AGENT_PERSONAS:
            raise HTTPException(400, f"Unknown agent: {agent_id}")
        
        persona = AGENT_PERSONAS[agent_id]
        lang = request.language
        
        # Build system prompt with agent persona + analysis context
        system_prompt = _build_chat_system_prompt(persona, request.analysis_context, lang)
        
        # Convert messages to OpenAI format
        messages = [{"role": "system", "content": system_prompt}]
        for msg in request.messages:
            messages.append({"role": msg.role, "content": msg.content})
        
        # Call OpenAI
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=600,
            temperature=0.7
        )
        
        agent_response = response.choices[0].message.content
        
        logger.info(f"[AgentChat] {persona['name']} responded to user query")
        
        return AgentChatResponse(
            agent_id=agent_id,
            agent_name=persona["name"],
            response=agent_response,
            suggested_questions=persona["suggested_questions"].get(lang, [])
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AgentChat] Error: {e}", exc_info=True)
        raise HTTPException(500, f"Chat failed: {str(e)}")


def _build_chat_system_prompt(persona: dict, analysis: dict, lang: str) -> str:
    """Build the system prompt with agent persona and analysis context"""
    
    personality = persona["personality"].get(lang, persona["personality"]["en"])
    
    # Extract key analysis data
    your_score = analysis.get("your_score", 0)
    your_ranking = analysis.get("your_ranking", 1)
    total_competitors = analysis.get("total_competitors", 1)
    revenue_at_risk = analysis.get("revenue_at_risk", 0)
    market_gaps = analysis.get("market_gaps", [])
    action_plan = analysis.get("action_plan", {})
    benchmark = analysis.get("benchmark", {})
    
    # Format market gaps
    gaps_text = ""
    if market_gaps:
        gaps_list = [g.get("gap_title", g.get("type", "")) for g in market_gaps[:5]]
        gaps_text = ", ".join(gaps_list)
    
    # Format action plan
    this_week = action_plan.get("this_week", "")
    total_actions = action_plan.get("total_actions", 0)
    
    if lang == "fi":
        context = f"""
ANALYYSIN TULOKSET (käytä näitä vastauksissasi):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Kokonaispistemäärä: {your_score}/100
🏆 Sijoitus: #{your_ranking} / {total_competitors} kilpailijaa
📈 Benchmark: keskiarvo {benchmark.get('avg', 0)}, paras {benchmark.get('max', 0)}
💰 Liikevaihto riskissä: €{revenue_at_risk:,}
💎 Markkina-aukot: {gaps_text}
📋 Toimenpiteitä: {total_actions} kpl 90 päivän suunnitelmassa
⭐ Tämän viikon prioriteetti: {this_week}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

OHJEET:
- Vastaa AINA suomeksi
- Pidä vastaukset tiiviinä (2-4 kappaletta)
- Viittaa konkreettisiin lukuihin analyysistä
- Ole {persona['name']} - käytä persoonaasi
- Älä toista koko analyysiä, vastaa vain kysyttyyn
"""
    else:
        context = f"""
ANALYSIS RESULTS (use these in your responses):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Overall Score: {your_score}/100
🏆 Ranking: #{your_ranking} / {total_competitors} competitors
📈 Benchmark: average {benchmark.get('avg', 0)}, best {benchmark.get('max', 0)}
💰 Revenue at Risk: €{revenue_at_risk:,}
💎 Market Gaps: {gaps_text}
📋 Actions: {total_actions} in 90-day plan
⭐ This Week's Priority: {this_week}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INSTRUCTIONS:
- Always respond in English
- Keep responses concise (2-4 paragraphs)
- Reference specific numbers from the analysis
- Be {persona['name']} - use your personality
- Don't repeat the whole analysis, answer what's asked
"""

    return f"{personality}\n\n{context}"


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
        
        # Send completion message with FLAT structure for frontend
        # Extract data from nested agent results
        analyst = result.results.get('analyst', {})
        guardian = result.results.get('guardian', {})
        prospector = result.results.get('prospector', {})
        strategist = result.results.get('strategist', {})
        planner = result.results.get('planner', {})
        
        # Build flat response
        await websocket.send_json({
            "type": "complete",
            "data": {
                "success": result.success,
                "duration_seconds": result.duration_seconds,
                "agents_completed": result.agents_completed,
                "agents_failed": result.agents_failed,
                
                # Analyst data (flattened)
                "your_score": analyst.get('your_score', 0),
                "your_ranking": analyst.get('your_rank', 1),
                "total_competitors": analyst.get('total_analyzed', 1),
                "benchmark": {
                    "avg": analyst.get('benchmark', {}).get('avg_score', 0),
                    "max": analyst.get('benchmark', {}).get('max_score', 0),
                    "min": analyst.get('benchmark', {}).get('min_score', 0)
                },
                
                # Guardian data (flattened)
                "revenue_at_risk": guardian.get('revenue_impact', {}).get('total_annual_impact', 0),
                "risk_count": len(guardian.get('threats', [])),
                "competitor_threats": guardian.get('competitor_threat_assessment', {}).get('assessments', []),
                "rasm_score": guardian.get('rasm_score', 0),
                
                # Prospector data (flattened)
                "market_gaps": prospector.get('market_gaps', []),
                "opportunities_count": len(prospector.get('market_gaps', [])),
                "your_advantages": prospector.get('strengths', []),
                
                # Strategist data (flattened)
                "market_position": strategist.get('position_quadrant', 'unknown'),
                "position_quadrant": strategist.get('position_quadrant', 'challenger'),
                "strategic_score": strategist.get('strategic_score', 0),
                "creative_boldness": strategist.get('creative_boldness', 50),
                
                # Planner data (flattened)
                "action_plan": {
                    "this_week": planner.get('one_thing_this_week'),
                    "phase1": planner.get('plan', {}).get('wave_1', []) if planner.get('plan') else [],
                    "phase2": planner.get('plan', {}).get('wave_2', []) if planner.get('plan') else [],
                    "phase3": planner.get('plan', {}).get('wave_3', []) if planner.get('plan') else [],
                    "total_actions": sum([
                        len(planner.get('plan', {}).get('wave_1', []) if planner.get('plan') else []),
                        len(planner.get('plan', {}).get('wave_2', []) if planner.get('plan') else []),
                        len(planner.get('plan', {}).get('wave_3', []) if planner.get('plan') else [])
                    ])
                },
                "projected_improvement": planner.get('roi_projection', {}).get('potential_score_gain', 0),
                
                # Raw results for deep-dive views
                "full_analysis": result.results,
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
