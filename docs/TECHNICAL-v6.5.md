# Brandista Competitive Intelligence API - Technical Documentation

**Last Updated:** 2026-01-15
**Version:** 6.5.0 (Growth Engine 2.0 with Core Web Vitals & WCAG 2.1)
**Language:** Python 3.11+ / FastAPI

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Brandista Competitive Intelligence                  │
│                        Growth Engine 2.0                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Website     │  │   Agent      │  │      Company             │  │
│  │  Analysis    │  │   Swarm      │  │      Intel               │  │
│  │  /api/v1/    │  │ /api/v1/     │  │   /api/v1/company/       │  │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬──────────────┘  │
│         │                 │                      │                  │
│         ▼                 ▼                      ▼                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  GrowthEngineOrchestrator                    │   │
│  │                                                              │   │
│  │  Execution Plan:                                             │   │
│  │  [Scout] → [Analyst] → [Guardian, Prospector] → [Strategist] │   │
│  │                              ↓                               │   │
│  │                          [Planner]                           │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│         ┌────────────────────┼────────────────────┐                │
│         ▼                    ▼                    ▼                │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐        │
│  │  RunContext │      │ Blackboard  │      │ MessageBus  │        │
│  │  (per-req)  │      │  (shared)   │      │  (pub/sub)  │        │
│  └─────────────┘      └─────────────┘      └─────────────┘        │
│                              │                                      │
│         ┌────────────────────┼────────────────────┐                │
│         ▼                    ▼                    ▼                │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐        │
│  │ Collaboration│     │   Task      │      │  Learning   │        │
│  │  Manager    │      │ Delegation  │      │   System    │        │
│  └─────────────┘      └─────────────┘      └─────────────┘        │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  PostgreSQL (SQLite dev)          Redis (Sessions, RunStore)       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Multi-Agent System

### Agents (Execution Order)

| Agent | Role | Description | Timeout |
|-------|------|-------------|---------|
| `scout` | Data Gatherer | Web scraping, SPA rendering, data extraction | 120s |
| `analyst` | Business Analyst | Competitive analysis, SWOT, market positioning | 90s |
| `guardian` | Threat Detector | Risk assessment, competitive threats | 60s |
| `prospector` | Opportunity Finder | Growth opportunities, market gaps | 90s |
| `strategist` | Strategy Synthesizer | Strategic recommendations, action items | 120s |
| `planner` | Action Planner | 90-day action plan, prioritization | 90s |

### Execution Plan

```python
EXECUTION_PLAN = [
    ['scout'],                      # Phase 1: Data gathering
    ['analyst'],                    # Phase 2: Analysis
    ['guardian', 'prospector'],     # Phase 3: Parallel threat/opportunity
    ['strategist'],                 # Phase 4: Strategy synthesis
    ['planner']                     # Phase 5: Action planning
]
```

### Agent Communication

Agents communicate via:

1. **Blackboard** - Shared knowledge store
   - Scout writes: `website_data`, `competitor_data`
   - Analyst writes: `swot_analysis`, `competitive_positioning`
   - Guardian writes: `threats`, `risks`
   - Prospector writes: `opportunities`, `growth_areas`
   - Strategist writes: `strategy`, `recommendations`
   - Planner writes: `action_plan`, `milestones`

2. **MessageBus** - Real-time pub/sub
   - `agent.insight` - New insight discovered
   - `agent.progress` - Progress update
   - `agent.complete` - Agent finished
   - `agent.error` - Error occurred

3. **CollaborationManager** - Cross-agent collaboration
4. **TaskDelegationManager** - Dynamic task assignment

---

## RunContext System

Per-request isolation for concurrent execution:

```python
@dataclass
class RunContext:
    run_id: str                    # Unique identifier
    user_id: Optional[str]         # User who initiated
    url: Optional[str]             # Analysis target
    status: RunStatus              # pending/running/completed/failed/cancelled
    limits: RunLimits              # Timeouts and concurrency limits

    # Isolated instances (no global state!)
    bus: MessageBus
    blackboard: Blackboard
    collaboration: CollaborationManager
    tasks: TaskDelegationManager
    learning: LearningSystem
```

### RunLimits

```python
@dataclass
class RunLimits:
    llm_concurrency: int = 5       # Max concurrent LLM calls
    scrape_concurrency: int = 3    # Max concurrent web scrapes
    total_timeout: float = 180.0   # 3 min total run
    agent_timeout: float = 90.0    # Default per agent
    llm_timeout: float = 60.0      # LLM call timeout
    scrape_timeout: float = 30.0   # Web scrape timeout
```

### RunStore (Redis-backed)

```python
# Redis keys:
run:{run_id}:meta      # JSON - created_at, user_id, url, etc
run:{run_id}:status    # string - pending/running/completed/failed/cancelled
run:{run_id}:result    # JSON - final result
run:{run_id}:trace     # LIST - trace events
run:{run_id}:cancelled # string "1" (short TTL for cancellation)
runs:index             # ZSET - timestamp -> run_id for listing
runs:status:{status}   # SET - run_ids by status
```

---

## API Endpoints

### Website Analysis

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/analyze` | Start website analysis |
| GET | `/api/v1/analysis/{analysis_id}` | Get analysis result |
| GET | `/api/v1/history` | Get analysis history |

### Agent System

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/agents/analyze` | Start agent analysis |
| GET | `/api/v1/agents/status` | Get all agents status |
| GET | `/api/v1/agents/{agent_id}` | Get specific agent |
| WS | `/api/v1/agents/ws` | WebSocket for real-time updates |

### Run Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/agents/runs` | List runs (with filters) |
| GET | `/api/v1/agents/runs/{run_id}` | Get specific run |
| POST | `/api/v1/agents/runs/{run_id}/cancel` | Cancel running analysis |
| GET | `/api/v1/agents/runs/{run_id}/events` | Get run events (SSE) |

### Company Intel

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/company/intel` | Get company intelligence |
| GET | `/api/v1/company/cache/{domain}` | Get cached intel |

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/magic-link` | Request magic link |
| GET | `/api/v1/auth/verify` | Verify magic link |
| GET | `/api/v1/auth/google` | Google OAuth login |
| GET | `/api/v1/auth/google/callback` | Google OAuth callback |

---

## WebSocket Protocol

### Connection

```javascript
const ws = new WebSocket('wss://api.brandista.fi/api/v1/agents/ws?token=...');
```

### Message Types

| Type | Direction | Description |
|------|-----------|-------------|
| `start_analysis` | Client → Server | Start new analysis |
| `cancel_analysis` | Client → Server | Cancel running analysis |
| `agent_insight` | Server → Client | New insight from agent |
| `agent_progress` | Server → Client | Progress update |
| `agent_complete` | Server → Client | Agent finished |
| `swarm_event` | Server → Client | Cross-agent communication |
| `analysis_complete` | Server → Client | Full analysis done |
| `error` | Server → Client | Error occurred |

### Example Messages

```json
// Client: Start analysis
{
    "type": "start_analysis",
    "payload": {
        "url": "https://example.com",
        "competitor_urls": ["https://competitor.com"],
        "language": "fi"
    }
}

// Server: Agent progress
{
    "type": "agent_progress",
    "payload": {
        "agent_id": "scout",
        "progress": 75,
        "message": "Analyzing page structure..."
    }
}

// Server: Agent insight
{
    "type": "agent_insight",
    "payload": {
        "agent_id": "analyst",
        "insight": {
            "type": "strength",
            "content": "Strong mobile optimization",
            "confidence": 0.85
        }
    }
}
```

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `OPENAI_API_KEY` | OpenAI API key for agents |
| `JWT_SECRET_KEY` | JWT signing secret |

### OAuth (Optional)

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth secret |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL |

### Email (Optional)

| Variable | Description |
|----------|-------------|
| `SMTP_HOST` | SMTP server host |
| `SMTP_PORT` | SMTP server port |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `FROM_EMAIL` | Sender email address |

### Other

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | 8000 |
| `LOG_LEVEL` | Logging level | INFO |
| `ALLOWED_ORIGINS` | CORS origins | * |
| `RUN_DATA_TTL` | Run data TTL (seconds) | 604800 (7 days) |
| `PAGESPEED_API_KEY` | Google PageSpeed Insights API key | (optional) |

---

## File Structure

```
brandista-api/
├── main.py                    # Main FastAPI application
├── agent_api.py               # Agent REST & WebSocket endpoints
├── database.py                # Database models & connections
├── auth_magic_link.py         # Magic link authentication
├── email_notifications.py     # Email sending
├── company_intel.py           # Company intelligence service
├── unified_context.py         # Unified analysis context
│
├── agents/                    # Multi-Agent System
│   ├── __init__.py           # Package exports
│   ├── orchestrator.py       # GrowthEngineOrchestrator
│   ├── base_agent.py         # BaseAgent class
│   ├── agent_types.py        # Type definitions
│   │
│   ├── scout_agent.py        # Web scraping & data gathering
│   ├── analyst_agent.py      # Business analysis
│   ├── guardian_agent.py     # Threat detection
│   ├── prospector_agent.py   # Opportunity finding
│   ├── strategist_agent.py   # Strategy synthesis
│   ├── planner_agent.py      # Action planning
│   │
│   ├── run_context.py        # Per-request isolation
│   ├── run_store.py          # Redis-backed state storage
│   ├── blackboard.py         # Shared knowledge store
│   ├── communication.py      # MessageBus pub/sub
│   ├── collaboration.py      # Cross-agent collaboration
│   ├── task_delegation.py    # Dynamic task assignment
│   ├── learning.py           # Learning system
│   └── translations.py       # Multi-language support
│
├── app/                       # Additional modules
│   ├── company_intel.py
│   ├── company_intel_api.py
│   └── scout_company_intel_integration.py
│
└── docs/
    └── TECHNICAL-v6.4.md     # This file
```

---

## Database Models

### Core Models

```python
# Analysis - Website analysis results
class Analysis:
    id: int
    url: str
    user_id: str
    score: float
    results: JSON
    created_at: datetime

# User - User accounts
class User:
    id: str
    email: str
    role: str  # user, admin
    created_at: datetime

# MagicLink - Authentication links
class MagicLink:
    id: str
    email: str
    token: str
    expires_at: datetime
    used: bool
```

---

## Deployment

### Railway/Render

```bash
# Build
pip install -r requirements.txt

# Start
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Health Check

```bash
GET /health
```

Response:
```json
{
    "status": "healthy",
    "version": "6.5.0",
    "redis": "connected",
    "database": "connected",
    "agents": {
        "scout": "idle",
        "analyst": "idle",
        "guardian": "idle",
        "prospector": "idle",
        "strategist": "idle",
        "planner": "idle"
    }
}
```

---

## Comparison: Brandista vs BemuFix

| Feature | Brandista (Python) | BemuFix (TypeScript) |
|---------|-------------------|---------------------|
| **Purpose** | Competitive Intelligence | Auto Service Chat |
| **Framework** | FastAPI | Express.js |
| **Agents** | 6 (Scout→Planner) | 6 (VehicleScout→CommHub) |
| **RunContext** | ✅ Full implementation | ✅ Ported from Brandista |
| **RunStore** | Redis + InMemory | Redis |
| **Blackboard** | ✅ | ✅ (CollectiveKnowledge) |
| **MessageBus** | ✅ Pub/Sub | ✅ AgentMessenger |
| **WebSocket** | ✅ Native | ✅ Socket.IO |
| **Notifications** | Email only | Email + SMS + WhatsApp |

---

## Version History

| Version | Features |
|---------|----------|
| 5.0 | Initial multi-agent system |
| 6.0 | Growth Engine architecture |
| 6.2 | Blackboard, MessageBus |
| 6.3 | Collaboration, Task Delegation |
| 6.4 | RunContext, RunStore, cancellation support |
| 6.4.4 | Production-ready, Redis-backed persistence |
| 6.5.0 | Core Web Vitals (PageSpeed API), WCAG 2.1 accessibility |

---

## Core Web Vitals (v6.5.0)

Real performance metrics from Google PageSpeed Insights API:

| Metric | Good | Needs Improvement | Description |
|--------|------|-------------------|-------------|
| LCP | < 2.5s | < 4s | Largest Contentful Paint |
| FID | < 100ms | < 300ms | First Input Delay |
| INP | < 200ms | < 500ms | Interaction to Next Paint |
| CLS | < 0.1 | < 0.25 | Cumulative Layout Shift |
| TTFB | < 800ms | - | Time to First Byte |
| FCP | < 1.8s | < 3s | First Contentful Paint |

Returns: `opportunities` and `diagnostics` for improvements.

---

## WCAG 2.1 Accessibility (v6.5.0)

Comprehensive accessibility checks:

| WCAG | Level | Criterion |
|------|-------|-----------|
| 3.1.1 | A | Language (html lang attribute) |
| 1.1.1 | A | Non-text Content (alt texts) |
| 2.4.1 | A | Bypass Blocks (skip links) |
| 4.1.2 | A | Name/Role/Value (ARIA labels) |
| 1.3.1 | A | Info and Relationships (heading hierarchy) |
| 2.4.4 | A | Link Purpose (vague link detection) |
| 2.4.7 | AA | Focus Visible (CSS focus indicators) |
| 2.1.1 | A | Keyboard (tabindex, keyboard handlers) |
| 1.4.3 | AA | Contrast (potential contrast issues) |
| 1.4.1 | A | Use of Color (color-only indicators) |

---

## Next Steps (v6.6 Roadmap)

1. **Streaming Responses** - SSE for real-time analysis updates
2. **Analysis Templates** - Pre-configured analysis types
3. **Batch Analysis** - Multiple URLs in single request
4. **Webhook Callbacks** - Notify external systems on completion
5. **Analysis Comparison** - Compare analyses over time
