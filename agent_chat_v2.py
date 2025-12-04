"""
Growth Engine 2.0 - Enhanced Agent Chat
Parannettu chat-toiminto täydellä kontekstilla + keskusteluhistorian tallennus
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# DATABASE: Chat History Tables
# ============================================================================

CHAT_HISTORY_TABLE_SQL = """
-- Keskusteluhistoria agenttien kanssa
CREATE TABLE IF NOT EXISTS agent_chat_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    analysis_id INTEGER,
    url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS agent_chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES agent_chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    agent_id VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indeksit nopeaan hakuun
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON agent_chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_agent ON agent_chat_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_analysis ON agent_chat_sessions(analysis_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON agent_chat_messages(session_id);
"""


def _get_connection():
    """Hae PostgreSQL-yhteys DATABASE_URL:sta"""
    import psycopg2
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    try:
        return psycopg2.connect(database_url)
    except Exception as e:
        logger.error(f"[Chat] DB connection error: {e}")
        return None


def init_chat_tables():
    """Alusta chat-taulut"""
    try:
        conn = _get_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute(CHAT_HISTORY_TABLE_SQL)
            conn.commit()
            conn.close()
            logger.info("[Chat] Database tables initialized")
            return True
    except Exception as e:
        logger.error(f"[Chat] Failed to init tables: {e}")
    return False


# ============================================================================
# CHAT SESSION MANAGEMENT
# ============================================================================

def get_or_create_session(
    user_id: str,
    agent_id: str,
    analysis_id: Optional[int] = None,
    url: Optional[str] = None
) -> Optional[int]:
    """Hae tai luo chat-sessio"""
    try:
        conn = _get_connection()
        if not conn:
            return None
        
        with conn.cursor() as cur:
            # Etsi aktiivinen sessio tälle agentille ja analyysille
            if analysis_id:
                cur.execute("""
                    SELECT id FROM agent_chat_sessions 
                    WHERE user_id = %s AND agent_id = %s AND analysis_id = %s AND is_active = TRUE
                    ORDER BY updated_at DESC LIMIT 1
                """, (user_id, agent_id, analysis_id))
            else:
                cur.execute("""
                    SELECT id FROM agent_chat_sessions 
                    WHERE user_id = %s AND agent_id = %s AND is_active = TRUE
                    ORDER BY updated_at DESC LIMIT 1
                """, (user_id, agent_id))
            
            row = cur.fetchone()
            if row:
                session_id = row[0]
                # Päivitä updated_at
                cur.execute("""
                    UPDATE agent_chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s
                """, (session_id,))
                conn.commit()
                conn.close()
                return session_id
            
            # Luo uusi sessio
            cur.execute("""
                INSERT INTO agent_chat_sessions (user_id, agent_id, analysis_id, url)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (user_id, agent_id, analysis_id, url))
            
            session_id = cur.fetchone()[0]
            conn.commit()
            conn.close()
            
            logger.info(f"[Chat] Created session {session_id} for {user_id}/{agent_id}")
            return session_id
            
    except Exception as e:
        logger.error(f"[Chat] Session error: {e}")
        return None


def save_chat_message(
    session_id: int,
    role: str,
    content: str,
    agent_id: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> Optional[int]:
    """Tallenna chat-viesti"""
    try:
        conn = _get_connection()
        if not conn:
            return None
        
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO agent_chat_messages (session_id, role, content, agent_id, metadata)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (session_id, role, content, agent_id, json.dumps(metadata or {})))
            
            message_id = cur.fetchone()[0]
            conn.commit()
            conn.close()
            return message_id
            
    except Exception as e:
        logger.error(f"[Chat] Save message error: {e}")
        return None


def get_chat_history(
    session_id: int,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Hae chat-historia"""
    try:
        conn = _get_connection()
        if not conn:
            return []
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT role, content, agent_id, metadata, created_at
                FROM agent_chat_messages
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (session_id, limit))
            
            rows = cur.fetchall()
            conn.close()
            
            # Käännä järjestys (vanhimmasta uusimpaan)
            messages = []
            for row in reversed(rows):
                messages.append({
                    "role": row[0],
                    "content": row[1],
                    "agent_id": row[2],
                    "metadata": row[3] or {},
                    "created_at": row[4].isoformat() if row[4] else None
                })
            
            return messages
            
    except Exception as e:
        logger.error(f"[Chat] Get history error: {e}")
        return []


def get_user_chat_sessions(
    user_id: str,
    agent_id: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Hae käyttäjän chat-sessiot"""
    try:
        conn = _get_connection()
        if not conn:
            return []
        
        with conn.cursor() as cur:
            if agent_id:
                cur.execute("""
                    SELECT s.id, s.agent_id, s.analysis_id, s.url, s.created_at, s.updated_at,
                           (SELECT COUNT(*) FROM agent_chat_messages WHERE session_id = s.id) as message_count
                    FROM agent_chat_sessions s
                    WHERE s.user_id = %s AND s.agent_id = %s AND s.is_active = TRUE
                    ORDER BY s.updated_at DESC
                    LIMIT %s
                """, (user_id, agent_id, limit))
            else:
                cur.execute("""
                    SELECT s.id, s.agent_id, s.analysis_id, s.url, s.created_at, s.updated_at,
                           (SELECT COUNT(*) FROM agent_chat_messages WHERE session_id = s.id) as message_count
                    FROM agent_chat_sessions s
                    WHERE s.user_id = %s AND s.is_active = TRUE
                    ORDER BY s.updated_at DESC
                    LIMIT %s
                """, (user_id, limit))
            
            rows = cur.fetchall()
            conn.close()
            
            sessions = []
            for row in rows:
                sessions.append({
                    "id": row[0],
                    "agent_id": row[1],
                    "analysis_id": row[2],
                    "url": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                    "updated_at": row[5].isoformat() if row[5] else None,
                    "message_count": row[6]
                })
            
            return sessions
            
    except Exception as e:
        logger.error(f"[Chat] Get sessions error: {e}")
        return []


# ============================================================================
# ENHANCED SYSTEM PROMPTS - Full Context
# ============================================================================

AGENT_PERSONALITIES = {
    "scout": {
        "name": "Sofia",
        "avatar": "🔍",
        "role": "Market Intelligence",
        "traits": "Utelias, tarkkanäköinen, analyyttinen"
    },
    "analyst": {
        "name": "Alex",
        "avatar": "📊",
        "role": "Data Science",
        "traits": "Tarkka, numeroihin keskittyvä, metodinen"
    },
    "guardian": {
        "name": "Gustav",
        "avatar": "🛡️",
        "role": "Risk Manager",
        "traits": "Varovainen, suojeleva, rehellinen riskeistä"
    },
    "prospector": {
        "name": "Petra",
        "avatar": "💎",
        "role": "Growth Hacker",
        "traits": "Energinen, optimistinen, mahdollisuuksiin keskittyvä"
    },
    "strategist": {
        "name": "Stefan",
        "avatar": "🎯",
        "role": "Strategy Director",
        "traits": "Viisas, kokonaisuuksia näkevä, johtajuustaitoinen"
    },
    "planner": {
        "name": "Pinja",
        "avatar": "📋",
        "role": "Project Manager",
        "traits": "Järjestelmällinen, käytännöllinen, toteutuskeskeinen"
    }
}


def build_enhanced_system_prompt(
    agent_id: str,
    language: str,
    analysis_context: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict]] = None,
    unified_context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Rakenna täydellinen system prompt agentille.
    
    Sisältää:
    1. Agentin persoonallisuus
    2. Oman analyysin TÄYDET tulokset
    3. Muiden agenttien relevantit tulokset (cross-agent context)
    4. Käyttäjän historia (unified context)
    5. Aiempi keskusteluhistoria tämän agentin kanssa
    """
    
    agent = AGENT_PERSONALITIES.get(agent_id, AGENT_PERSONALITIES["analyst"])
    
    # Base personality
    if language == "fi":
        prompt = f"""Olet {agent['name']}, Brandistan {agent['role']}. {agent['avatar']}

Persoonallisuutesi: {agent['traits']}
Puhut suomea luontevasti. Ole ytimekäs mutta informatiivinen.
Käytä emojeja sopivasti korostamaan tärkeitä pointteja.

TÄRKEÄÄ: Sinulla on pääsy kaikkiin analyysin tuloksiin. Vastaa konkreettisesti käyttäen dataa.
"""
    else:
        prompt = f"""You are {agent['name']}, Brandista's {agent['role']}. {agent['avatar']}

Personality: {agent['traits']}
Be concise but informative. Use emojis appropriately to highlight key points.

IMPORTANT: You have access to all analysis results. Answer concretely using data.
"""
    
    # Add full analysis context
    if analysis_context:
        prompt += _build_analysis_section(agent_id, analysis_context, language)
    
    # Add cross-agent context
    if analysis_context and analysis_context.get('agent_results'):
        prompt += _build_cross_agent_section(agent_id, analysis_context, language)
    
    # Add unified context (user history)
    if unified_context:
        prompt += _build_unified_context_section(unified_context, language)
    
    # Add chat history summary
    if chat_history and len(chat_history) > 0:
        prompt += _build_chat_history_section(chat_history, language)
    
    return prompt


def _build_analysis_section(agent_id: str, ctx: Dict, language: str) -> str:
    """Rakenna agentin oman analyysin osio"""
    
    section = "\n\n" + ("=" * 50) + "\n"
    section += "📊 ANALYYSIN TULOKSET\n" if language == "fi" else "📊 ANALYSIS RESULTS\n"
    section += ("=" * 50) + "\n\n"
    
    # Common data
    section += f"URL: {ctx.get('url', 'N/A')}\n"
    section += f"Score: {ctx.get('your_score', 0)}/100\n"
    section += f"Ranking: #{ctx.get('your_ranking', 1)} / {ctx.get('total_competitors', 1)}\n"
    section += f"Revenue at Risk: €{ctx.get('revenue_at_risk', 0):,}\n\n"
    
    # Agent-specific detailed data
    agent_results = ctx.get('agent_results', {})
    
    if agent_id == "scout":
        scout_data = agent_results.get('scout', {}).get('data', {})
        section += "🔍 SINUN LÖYDÖKSESI:\n" if language == "fi" else "🔍 YOUR FINDINGS:\n"
        section += f"- Competitors found: {len(scout_data.get('competitor_urls', []))}\n"
        section += f"- URLs: {json.dumps(scout_data.get('competitor_urls', []), indent=2)}\n"
        if scout_data.get('competitors_enriched'):
            section += f"- Enriched data: {json.dumps(scout_data.get('competitors_enriched', [])[:3], indent=2)}\n"
    
    elif agent_id == "analyst":
        analyst_data = agent_results.get('analyst', {}).get('data', {})
        section += "📊 SINUN ANALYYSISI:\n" if language == "fi" else "📊 YOUR ANALYSIS:\n"
        section += f"- Your analysis: {json.dumps(analyst_data.get('your_analysis', {}), indent=2)[:2000]}\n"
        section += f"- Benchmark: {json.dumps(analyst_data.get('benchmark', {}), indent=2)}\n"
        section += f"- Competitor analyses count: {len(analyst_data.get('competitor_analyses', []))}\n"
    
    elif agent_id == "guardian":
        guardian_data = agent_results.get('guardian', {}).get('data', {})
        section += "🛡️ SINUN RISKIANALYYSISI:\n" if language == "fi" else "🛡️ YOUR RISK ANALYSIS:\n"
        section += f"- RASM Score: {guardian_data.get('rasm_score', 0)}/100\n"
        section += f"- Revenue Impact: {json.dumps(guardian_data.get('revenue_impact', {}), indent=2)}\n"
        section += f"- Threat Assessment: {json.dumps(guardian_data.get('competitor_threat_assessment', {}), indent=2)[:2000]}\n"
        section += f"- Vulnerabilities: {json.dumps(guardian_data.get('vulnerabilities', []), indent=2)[:1000]}\n"
    
    elif agent_id == "prospector":
        prospector_data = agent_results.get('prospector', {}).get('data', {})
        section += "💎 SINUN LÖYTÄMÄSI MAHDOLLISUUDET:\n" if language == "fi" else "💎 YOUR OPPORTUNITIES:\n"
        section += f"- Market Gaps: {json.dumps(prospector_data.get('market_gaps', []), indent=2)}\n"
        section += f"- Competitive Advantages: {json.dumps(prospector_data.get('competitive_advantages', []), indent=2)}\n"
        section += f"- Quick Wins: {json.dumps(prospector_data.get('quick_wins', []), indent=2)}\n"
    
    elif agent_id == "strategist":
        strategist_data = agent_results.get('strategist', {}).get('data', {})
        section += "🎯 SINUN STRATEGIASI:\n" if language == "fi" else "🎯 YOUR STRATEGY:\n"
        section += f"- Position Quadrant: {strategist_data.get('position_quadrant', 'N/A')}\n"
        section += f"- Market Position: {strategist_data.get('market_position', 'N/A')}\n"
        section += f"- Strategic Score: {strategist_data.get('strategic_score', 0)}\n"
        section += f"- Recommendations: {json.dumps(strategist_data.get('recommendations', []), indent=2)[:1500]}\n"
    
    elif agent_id == "planner":
        planner_data = agent_results.get('planner', {}).get('data', {})
        section += "📋 SINUN SUUNNITELMASI:\n" if language == "fi" else "📋 YOUR PLAN:\n"
        section += f"- Phases: {len(planner_data.get('phases', []))}\n"
        section += f"- Quick Start: {json.dumps(planner_data.get('quick_start_guide', []), indent=2)}\n"
        section += f"- ROI Projection: {json.dumps(planner_data.get('roi_projection', {}), indent=2)}\n"
        section += f"- Milestones: {json.dumps(planner_data.get('milestones', []), indent=2)[:1000]}\n"
    
    return section


def _build_cross_agent_section(agent_id: str, ctx: Dict, language: str) -> str:
    """Rakenna muiden agenttien relevantit tulokset"""
    
    section = "\n\n" + ("-" * 50) + "\n"
    section += "🤝 MUIDEN TIIMILÄISTEN LÖYDÖKSET:\n" if language == "fi" else "🤝 TEAM FINDINGS:\n"
    section += ("-" * 50) + "\n\n"
    
    agent_results = ctx.get('agent_results', {})
    
    # Jokainen agentti saa tiivistelmän muiden tuloksista
    
    if agent_id != "scout":
        scout = agent_results.get('scout', {}).get('data', {})
        competitors = scout.get('competitor_urls', [])
        section += f"🔍 Sofia (Scout): Löysi {len(competitors)} kilpailijaa\n"
        if competitors:
            section += f"   Kilpailijat: {', '.join(competitors[:5])}\n"
    
    if agent_id != "analyst":
        analyst = agent_results.get('analyst', {}).get('data', {})
        benchmark = analyst.get('benchmark', {})
        section += f"📊 Alex (Analyst): Score {ctx.get('your_score', 0)}/100, "
        section += f"Rank #{benchmark.get('your_position', 1)}/{benchmark.get('total_analyzed', 1)}\n"
    
    if agent_id != "guardian":
        guardian = agent_results.get('guardian', {}).get('data', {})
        threats = ctx.get('competitor_threats', [])
        section += f"🛡️ Gustav (Guardian): €{ctx.get('revenue_at_risk', 0):,} riskissä, "
        section += f"{len(threats)} uhkaa tunnistettu\n"
        if threats:
            top_threat = threats[0] if threats else {}
            section += f"   Suurin uhka: {top_threat.get('company', 'N/A')} ({top_threat.get('threat_level', 'N/A')})\n"
    
    if agent_id != "prospector":
        gaps = ctx.get('market_gaps', [])
        advantages = ctx.get('your_advantages', [])
        section += f"💎 Petra (Prospector): {len(gaps)} markkinaaukkoa, {len(advantages)} kilpailuetua\n"
        if gaps:
            section += f"   Paras mahdollisuus: {gaps[0].get('gap', 'N/A')}\n"
    
    if agent_id != "strategist":
        section += f"🎯 Stefan (Strategist): Positio: {ctx.get('position_quadrant', 'N/A')}\n"
    
    if agent_id != "planner":
        plan = ctx.get('action_plan', {})
        section += f"📋 Pinja (Planner): {plan.get('total_actions', 0)} toimenpidettä, "
        section += f"+{ctx.get('projected_improvement', 0)} pistettä odotettu parannus\n"
    
    return section


def _build_unified_context_section(unified_ctx: Dict, language: str) -> str:
    """Rakenna käyttäjän historia"""
    
    section = "\n\n" + ("-" * 50) + "\n"
    section += "👤 KÄYTTÄJÄN HISTORIA:\n" if language == "fi" else "👤 USER HISTORY:\n"
    section += ("-" * 50) + "\n\n"
    
    # Recent analyses
    recent = unified_ctx.get('recent_analyses', [])
    if recent:
        section += f"Aiemmat analyysit ({len(recent)} kpl):\n" if language == "fi" else f"Previous analyses ({len(recent)}):\n"
        for analysis in recent[:3]:
            section += f"- {analysis.get('url', 'N/A')}: {analysis.get('score', 0)}/100 "
            section += f"({analysis.get('created_at', 'N/A')})\n"
    
    # Tracked competitors
    tracked = unified_ctx.get('tracked_competitors', [])
    if tracked:
        section += f"\nSeuratut kilpailijat: {', '.join(tracked[:5])}\n"
    
    # Trends
    trends = unified_ctx.get('trends', {})
    if trends:
        section += f"\nTrendit: Score {trends.get('score_trend', 'N/A')}, "
        section += f"Risk {trends.get('risk_trend', 'N/A')}\n"
    
    return section


def _build_chat_history_section(history: List[Dict], language: str) -> str:
    """Rakenna aiempi keskusteluhistoria"""
    
    section = "\n\n" + ("-" * 50) + "\n"
    section += "💬 AIEMPI KESKUSTELU:\n" if language == "fi" else "💬 PREVIOUS CONVERSATION:\n"
    section += ("-" * 50) + "\n\n"
    
    # Viimeiset 5 viestiä
    recent_messages = history[-5:] if len(history) > 5 else history
    
    for msg in recent_messages:
        role = "Käyttäjä" if msg['role'] == 'user' else "Sinä"
        if language == "en":
            role = "User" if msg['role'] == 'user' else "You"
        section += f"{role}: {msg['content'][:200]}...\n" if len(msg['content']) > 200 else f"{role}: {msg['content']}\n"
    
    section += "\n(Jatka keskustelua luontevasti / Continue the conversation naturally)\n"
    
    return section


# ============================================================================
# ENHANCED SUGGESTED QUESTIONS
# ============================================================================

def get_contextual_questions(
    agent_id: str,
    language: str,
    analysis_context: Optional[Dict] = None
) -> List[str]:
    """Generoi kontekstiin sopivat ehdotetut kysymykset"""
    
    questions = []
    
    if language == "fi":
        if agent_id == "scout":
            questions = [
                "Kuka on vaarallisin kilpailijani?",
                "Mitä kilpailijat tekevät paremmin kuin minä?",
                "Onko markkinoilla uusia tulokkaita?"
            ]
            # Contextual additions
            if analysis_context:
                competitors = analysis_context.get('competitor_urls', [])
                if len(competitors) > 0:
                    questions.insert(0, f"Kerro lisää kilpailijasta {competitors[0].split('/')[2] if '/' in competitors[0] else competitors[0]}")
        
        elif agent_id == "analyst":
            questions = [
                "Miksi pisteeni on juuri tämä?",
                "Missä olen kilpailijoita edellä?",
                "Mitä teknisiä puutteita minulla on?"
            ]
            score = analysis_context.get('your_score', 0) if analysis_context else 0
            if score < 50:
                questions.insert(0, "Miten nostan pisteeni yli 50:n?")
            elif score > 70:
                questions.insert(0, "Miten pääsen huipulle?")
        
        elif agent_id == "guardian":
            questions = [
                "Mikä on suurin yksittäinen riski?",
                "Miten suojaudun kilpailijoilta?",
                "Mitä teen ensimmäiseksi?"
            ]
            risk = analysis_context.get('revenue_at_risk', 0) if analysis_context else 0
            if risk > 0:
                questions.insert(0, f"Miten €{risk:,} riski muodostuu?")
        
        elif agent_id == "prospector":
            questions = [
                "Mikä on helpoin quick win?",
                "Missä kilpailijat jättävät rahaa pöydälle?",
                "Mikä kasvumahdollisuus on suurin?"
            ]
            gaps = analysis_context.get('market_gaps', []) if analysis_context else []
            if gaps:
                questions.insert(0, f"Kerro lisää: {gaps[0].get('gap', 'ensimmäisestä aukosta')}")
        
        elif agent_id == "strategist":
            questions = [
                "Mikä on markkina-asemani?",
                "Mihin minun pitäisi keskittyä?",
                "Miten voitan kilpailijat?"
            ]
            quadrant = analysis_context.get('position_quadrant', '') if analysis_context else ''
            if quadrant:
                questions.insert(0, f"Mitä '{quadrant}' positio tarkoittaa käytännössä?")
        
        elif agent_id == "planner":
            questions = [
                "Mitä teen ensimmäisellä viikolla?",
                "Paljonko tämä maksaa toteuttaa?",
                "Mikä on odotettu ROI?"
            ]
            plan = analysis_context.get('action_plan', {}) if analysis_context else {}
            if plan.get('this_week'):
                action = plan['this_week'].get('action', '')
                if action:
                    questions.insert(0, f"Miten toteutan: {action[:50]}...?")
    
    else:  # English
        if agent_id == "scout":
            questions = ["Who is my biggest competitor?", "What do competitors do better?", "Any new market entrants?"]
        elif agent_id == "analyst":
            questions = ["Why is my score this?", "Where am I ahead?", "What technical gaps do I have?"]
        elif agent_id == "guardian":
            questions = ["What's the biggest risk?", "How is the risk calculated?", "What should I do first?"]
        elif agent_id == "prospector":
            questions = ["What's the easiest quick win?", "Where's the biggest opportunity?", "What are my advantages?"]
        elif agent_id == "strategist":
            questions = ["What's my market position?", "What should I focus on?", "How do I beat competitors?"]
        elif agent_id == "planner":
            questions = ["What do I do in week one?", "How much will this cost?", "What's the expected ROI?"]
    
    return questions[:4]  # Max 4 questions


# ============================================================================
# ENHANCED CHAT ENDPOINT
# ============================================================================

from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional

router = APIRouter()


class EnhancedChatRequest(BaseModel):
    """Parannettu chat-pyyntö"""
    agent_id: str = Field(..., description="Agent ID (scout, analyst, guardian, prospector, strategist, planner)")
    message: str = Field(..., description="User's message")
    session_id: Optional[int] = Field(None, description="Existing session ID (optional)")
    analysis_id: Optional[int] = Field(None, description="Related analysis ID")
    analysis_context: Optional[Dict[str, Any]] = Field(None, description="Full analysis context")
    language: str = Field("fi", description="Language: 'fi' or 'en'")
    include_history: bool = Field(True, description="Include chat history in context")


class EnhancedChatResponse(BaseModel):
    """Parannettu chat-vastaus"""
    response: str
    agent_id: str
    agent_name: str
    agent_avatar: str
    session_id: int
    suggested_questions: List[str]
    message_id: Optional[int] = None


@router.post("/chat/v2", response_model=EnhancedChatResponse)
async def enhanced_agent_chat(
    request: EnhancedChatRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Enhanced chat with AI agent.
    
    Features:
    - Full analysis context (own data + cross-agent)
    - Chat history persistence
    - Unified context (user history)
    - Contextual suggested questions
    """
    try:
        # Get user from token
        user_id = "anonymous"
        if authorization:
            try:
                import jwt
                token = authorization.replace("Bearer ", "")
                SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
                payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
                user_id = payload.get("sub", "anonymous")
            except:
                pass
        
        agent_id = request.agent_id
        agent = AGENT_PERSONALITIES.get(agent_id)
        
        if not agent:
            raise HTTPException(400, f"Unknown agent: {agent_id}")
        
        # Get or create session
        session_id = request.session_id
        if not session_id:
            session_id = get_or_create_session(
                user_id=user_id,
                agent_id=agent_id,
                analysis_id=request.analysis_id,
                url=request.analysis_context.get('url') if request.analysis_context else None
            )
        
        # Get chat history
        chat_history = []
        if request.include_history and session_id:
            chat_history = get_chat_history(session_id, limit=10)
        
        # Get unified context
        unified_context = None
        if user_id != "anonymous":
            try:
                from unified_context import get_unified_context
                unified_ctx = get_unified_context(user_id)
                unified_context = unified_ctx.to_dict() if unified_ctx else None
            except:
                pass
        
        # Build enhanced system prompt
        system_prompt = build_enhanced_system_prompt(
            agent_id=agent_id,
            language=request.language,
            analysis_context=request.analysis_context,
            chat_history=chat_history,
            unified_context=unified_context
        )
        
        # Build messages for OpenAI
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add history
        for msg in chat_history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # Add current message
        messages.append({
            "role": "user",
            "content": request.message
        })
        
        # Call OpenAI
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=800,
            temperature=0.7
        )
        
        agent_response = response.choices[0].message.content
        
        # Save messages to history
        user_msg_id = None
        assistant_msg_id = None
        
        if session_id:
            user_msg_id = save_chat_message(
                session_id=session_id,
                role="user",
                content=request.message,
                metadata={"analysis_id": request.analysis_id}
            )
            
            assistant_msg_id = save_chat_message(
                session_id=session_id,
                role="assistant",
                content=agent_response,
                agent_id=agent_id,
                metadata={"model": "gpt-4o-mini"}
            )
        
        # Get contextual suggested questions
        suggested = get_contextual_questions(
            agent_id=agent_id,
            language=request.language,
            analysis_context=request.analysis_context
        )
        
        return EnhancedChatResponse(
            response=agent_response,
            agent_id=agent_id,
            agent_name=agent["name"],
            agent_avatar=agent["avatar"],
            session_id=session_id or 0,
            suggested_questions=suggested,
            message_id=assistant_msg_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Chat V2] Error: {e}", exc_info=True)
        raise HTTPException(500, f"Chat error: {str(e)}")


@router.get("/chat/sessions")
async def get_chat_sessions(
    agent_id: Optional[str] = None,
    limit: int = 10,
    authorization: Optional[str] = Header(None)
):
    """Get user's chat sessions"""
    user_id = "anonymous"
    if authorization:
        try:
            import jwt
            token = authorization.replace("Bearer ", "")
            SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = payload.get("sub", "anonymous")
        except:
            pass
    
    sessions = get_user_chat_sessions(user_id, agent_id, limit)
    return {"sessions": sessions}


@router.get("/chat/history/{session_id}")
async def get_session_history(
    session_id: int,
    limit: int = 50,
    authorization: Optional[str] = Header(None)
):
    """Get chat history for a session"""
    messages = get_chat_history(session_id, limit)
    return {"session_id": session_id, "messages": messages}


# ============================================================================
# REGISTER ROUTES
# ============================================================================

def register_enhanced_chat_routes(app):
    """Register enhanced chat routes"""
    app.include_router(router, prefix="/api/v1/agents", tags=["Agent Chat V2"])
    
    # Init database tables
    init_chat_tables()
    
    logger.info("[Chat V2] Enhanced chat routes registered")
