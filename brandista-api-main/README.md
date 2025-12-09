# Growth Engine 2.0 - Agent System

Six specialized AI agents working together to deliver comprehensive competitive intelligence in 90 seconds.

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
├── orchestrator.py      # Coordinates all agents
agent_api.py             # REST + WebSocket endpoints
```

## Installation

1. Copy `agents/` folder to your project
2. Copy `agent_api.py` to your project root
3. Add to `main.py`:

```python
from agent_api import router as agent_router

app.include_router(agent_router, prefix="/api/v1/agents", tags=["agents"])
```

4. Add to `requirements.txt`:
```
python-whois==0.9.4
```

## API Endpoints

### REST

```
GET  /api/v1/agents/info     → Agent information
POST /api/v1/agents/analyze  → Run full analysis (sync)
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

## Version

- v2.0.0 - Complete refactor with English-only backend
- All agents use real main.py functions
- Competitor threat assessment included
