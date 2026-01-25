# Growth Engine 2.0 - Agent System

Six specialized AI agents working together to deliver comprehensive competitive intelligence in 90 seconds.

## 🆕 Refactored Modular Structure

The API has been refactored into a clean, modular architecture:

```
app/
├── main.py          # FastAPI application entry point
├── config.py        # Centralized configuration
├── dependencies.py  # Auth, rate limiting
├── routers/         # API endpoints by domain
├── services/        # Business logic
└── models/          # Pydantic models
```

## Quick Start

### Installation

1. Clone the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys and configuration
```

4. Run the server:
```bash
# New modular entry point (recommended)
uvicorn app.main:app --reload --port 8000

# Legacy entry point (still supported)
uvicorn main:app --reload --port 8000
```

5. Access the API:
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GROWTH ENGINE 2.0                            │
├─────────────────────────────────────────────────────────────────┤
│  Tier 1: Scout        → Finds competitors                      │
│  Tier 2: Analyst      → Deep analysis of all sites             │
│  Tier 3: Guardian     → Risks + Competitor threat assessment   │
│          Prospector   → Opportunities + Market gaps (parallel) │
│  Tier 4: Strategist   → Strategic recommendations              │
│  Tier 5: Planner      → 90-day action plan                     │
└─────────────────────────────────────────────────────────────────┘
```

## Agents

| Agent | Role | Uses from main.py |
|-------|------|-------------------|
| 🔍 Scout | Market Explorer | `multi_provider_search()`, `generate_smart_search_terms()` |
| 📊 Analyst | Data Scientist | `_perform_comprehensive_analysis_internal()` |
| 🛡️ Guardian | Risk Manager | `build_risk_register()`, `compute_business_impact()` |
| 💎 Prospector | Growth Hacker | `_build_differentiation_matrix()`, `_discover_real_market_gaps()`, `generate_competitive_swot_analysis()` |
| 🎯 Strategist | Strategic Advisor | `_calculate_market_positioning()`, `_generate_strategic_recommendations()`, `analyze_creative_boldness()` |
| 📋 Planner | Project Manager | `generate_enhanced_90day_plan()` |

## Language

**Backend: 100% English**
- All code, comments, variables in English
- All API responses in English
- All insight messages in English
- No translations in backend

**Frontend: Handles translations**
- `translations.ts` maps English → Finnish
- `LanguageContext` controls display language
- User sees content in their chosen language

## Files

```
app/
├── main.py              # FastAPI app (NEW modular structure)
├── config.py            # Configuration management
├── dependencies.py      # Auth & rate limiting
├── routers/             # API endpoints
├── services/            # Business logic
└── models/              # Pydantic models

agents/
├── __init__.py          # Exports
├── types.py             # Core types (AnalysisContext, AgentStatus, etc.)
├── base_agent.py        # Base class for all agents
├── scout_agent.py       # 🔍 Competitor discovery
├── analyst_agent.py     # 📊 Deep analysis
├── guardian_agent.py    # 🛡️ Risk + Competitor threat assessment
├── prospector_agent.py  # 💎 Opportunities + SWOT
├── strategist_agent.py  # 🎯 Strategic recommendations
├── planner_agent.py     # 📋 90-day plan
└── orchestrator.py      # Coordinates all agents

agent_api.py             # REST + WebSocket endpoints
```

## API Endpoints

### REST

```
GET  /health                   → Health check
GET  /api/v1/agents/info      → Agent information
POST /api/v1/agents/analyze   → Run full analysis (sync)
```

### WebSocket

```
WS /api/v1/agents/ws

# Client sends:
{ "action": "start", "url": "https://example.com", "competitor_urls": [...] }

# Server sends (real-time):
{ "type": "insight", "data": { "agent_id": "scout", "message": "...", ... } }
{ "type": "progress", "data": { "agent_id": "scout", "progress": 50, ... } }
{ "type": "status", "data": { "agent_id": "scout", "status": "running" } }
{ "type": "complete", "data": { "success": true, "duration_seconds": 45.2 } }
```

## Example Output

```json
{
  "type": "insight",
  "data": {
    "agent_id": "scout",
    "message": "🎯 Found 5 solid competitors! Top match: Acme Corp (87% relevance)",
    "priority": "high",
    "insight_type": "finding"
  }
}
```

## Competitor Threat Assessment (Guardian)

Guardian now includes automatic competitor threat assessment:

```
🔴 Acme Corp: HIGH THREAT — Score 78/100, +15 points ahead, est. 5+ years, ~20+ employees
🟡 TechStart: MEDIUM THREAT — Score 65/100, actively hiring
🟢 NewPlayer: LOW THREAT — Score 82/100, new player, no strong signals
```

Signals analyzed:
- Digital score difference
- Domain age (WHOIS)
- Company size estimation
- Growth signals (hiring, active blog)
- Trust signals (case studies, certifications)

## Migration Guide

See [MIGRATION.md](MIGRATION.md) for detailed migration instructions from the legacy structure.

## Version

- v6.5.0 - Refactored modular architecture
- v2.0.0 - Complete refactor with English-only backend
- All agents use real main.py functions
- Competitor threat assessment included
