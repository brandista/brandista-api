# Brandista API - Technical Architecture

**Version:** 2.1.0 (TRUE SWARM EDITION)
**Last Updated:** January 2026

## Overview

Brandista is an AI-powered B2B lead generation and sales intelligence platform built on a multi-agent swarm architecture. The system uses specialized AI agents that collaborate to find, analyze, and score potential business leads.

## Project Structure

```
brandista-api-git/
├── main.py                    # FastAPI application entry point
├── agent_api.py               # Agent orchestration endpoints
├── agent_chat_v2.py           # Chat interface for agents
├── agent_reports.py           # Report generation
├── database.py                # SQLAlchemy models and connection
├── auth_magic_link.py         # Passwordless authentication
├── stripe_module.py           # Billing and subscriptions
├── email_notifications.py     # SendGrid email integration
├── translations_module.py     # i18n support (Finnish/English)
├── unified_context.py         # Shared context management
├── company_intel.py           # Company intelligence features
├── redis_tasks.py             # Background task queue
├── agents/                    # AI Agent implementations
│   ├── core/                  # Core agent infrastructure
│   ├── specialized/           # Domain-specific agents
│   ├── observability/         # Monitoring, logging, tracing
│   ├── persistence/           # Data storage (Blackboard, Redis)
│   ├── resilience/            # Circuit breakers, retry policies
│   └── security/              # Input validation, sanitization
└── tests/                     # Test suite (372 tests)
```

## Core Components

### 1. FastAPI Application (`main.py`)

The main entry point configures:
- CORS middleware for frontend integration
- Authentication middleware
- API routers for all endpoints
- Database connection pooling
- Redis connection for caching

**Key Endpoints:**
- `/api/auth/*` - Authentication (magic links, sessions)
- `/api/analysis/*` - Lead analysis and scoring
- `/api/agents/*` - Agent orchestration
- `/api/billing/*` - Stripe subscription management
- `/api/company-intel/*` - Company intelligence

### 2. Database Layer (`database.py`)

**ORM:** SQLAlchemy with PostgreSQL

**Key Models:**
- `User` - User accounts and authentication
- `Company` - Analyzed companies
- `Analysis` - Analysis results and scores
- `Subscription` - Billing subscriptions
- `APIUsage` - Usage tracking for rate limiting

### 3. Authentication (`auth_magic_link.py`)

Passwordless authentication via magic links:
1. User enters email
2. System generates secure token
3. Magic link sent via SendGrid
4. Token validated and session created

**Security Features:**
- Token expiration (15 minutes)
- Single-use tokens
- Rate limiting on requests

## Agent Architecture

### Swarm Orchestration Pattern

The system uses a **blackboard architecture** where agents share information through a central data store:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Scout     │     │  Analyst    │     │  Guardian   │
│   Agent     │     │   Agent     │     │   Agent     │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                    ┌──────┴──────┐
                    │  Blackboard │
                    │   (Redis)   │
                    └─────────────┘
```

### Specialized Agents

#### 1. Scout Agent (`agents/specialized/scout/`)
**Purpose:** Find and discover potential leads

**Capabilities:**
- Web scraping for company information
- YTJ (Finnish Business Register) integration
- Initial company profiling
- Lead source identification

**Tools:**
- `search_ytj` - Query Finnish business register
- `web_search` - Search the web for company info
- `scrape_website` - Extract data from company websites

#### 2. Analyst Agent (`agents/specialized/analyst/`)
**Purpose:** Deep analysis and scoring of leads

**Capabilities:**
- Financial analysis
- Market positioning assessment
- Growth potential scoring
- Technology stack detection

**Scoring Dimensions:**
- Company size and revenue
- Growth trajectory
- Technology adoption
- Market fit

#### 3. Guardian Agent (`agents/specialized/guardian/`)
**Purpose:** Quality control and validation

**Capabilities:**
- Data validation
- Duplicate detection
- Compliance checking
- Quality scoring

#### 4. Orchestrator (`agents/specialized/orchestrator/`)
**Purpose:** Coordinate agent collaboration

**Responsibilities:**
- Task distribution
- Agent lifecycle management
- Result aggregation
- Error handling

### Agent Communication

Agents communicate through the **Blackboard Pattern**:

```python
# Writing to blackboard
await blackboard.write(
    key="company:12345",
    data={"name": "Acme Oy", "score": 85},
    category="leads",
    source="scout"
)

# Reading from blackboard
entry = await blackboard.read("company:12345")

# Subscribing to updates
async for entry in blackboard.subscribe("leads"):
    process_lead(entry)
```

## Infrastructure Modules

### Observability (`agents/observability/`)

#### Metrics (`metrics.py`)
Prometheus-compatible metrics:
- `Counter` - Monotonically increasing values
- `Gauge` - Values that can go up/down
- `Histogram` - Distribution of values

```python
from agents.observability import Counter, Histogram

requests = Counter("http_requests_total", "Total HTTP requests")
latency = Histogram("request_latency_seconds", "Request latency")

requests.inc(labels={"method": "GET", "path": "/api/leads"})
latency.observe(0.125, labels={"endpoint": "analysis"})
```

#### Tracing (`tracing.py`)
OpenTelemetry-compatible distributed tracing:

```python
from agents.observability import Tracer

tracer = Tracer("scout-agent")

async with tracer.start_span("analyze_company") as span:
    span.set_attribute("company_id", "12345")
    result = await analyze(company)
    span.add_event("analysis_complete")
```

#### Logging (`logging.py`)
Structured JSON logging with sensitive data masking:

```python
from agents.observability import get_logger, set_correlation_id

logger = get_logger("agent.scout")
set_correlation_id("req-abc123")

logger.info("Processing lead", extra={"company": "Acme Oy"})
# Output: {"level": "INFO", "message": "Processing lead",
#          "correlation_id": "req-abc123", "company": "Acme Oy", ...}
```

**Sensitive Data Masking:**
- API keys and tokens
- Email addresses
- Credit card numbers
- Finnish personal IDs (HETU)
- Phone numbers

### Persistence (`agents/persistence/`)

#### Blackboard (`blackboard.py`)
In-memory shared data store:
- Key-value storage with metadata
- Category-based indexing
- TTL support for expiration
- Query by category, source, time

#### Redis Blackboard (`redis_blackboard.py`)
Redis-backed persistence with pub/sub:
- Same API as in-memory blackboard
- Real-time notifications via pub/sub
- Automatic JSON serialization
- Connection pooling

#### Hybrid Blackboard (`hybrid_blackboard.py`)
Zero-downtime migration support:

```python
hybrid = HybridBlackboard(memory_bb, redis_bb)

# Migration phases
hybrid.set_mode(BlackboardMode.MEMORY_ONLY)   # Start here
hybrid.set_mode(BlackboardMode.DUAL_WRITE)    # Write both
hybrid.set_mode(BlackboardMode.REDIS_ONLY)    # Complete migration
```

### Resilience (`agents/resilience/`)

#### Circuit Breaker (`circuit_breaker.py`)
Prevents cascading failures:

```python
from agents.resilience import CircuitBreaker

breaker = CircuitBreaker(
    name="openai_api",
    failure_threshold=5,    # Open after 5 failures
    success_threshold=2,    # Close after 2 successes
    timeout=60.0            # Try again after 60s
)

@breaker
async def call_openai(prompt):
    return await openai.chat.completions.create(...)
```

**States:**
- `CLOSED` - Normal operation
- `OPEN` - Failing fast, rejecting calls
- `HALF_OPEN` - Testing if service recovered

#### Retry Policies (`retry.py`)
Automatic retry with backoff:

```python
from agents.resilience import retry, ExponentialBackoff

@retry(
    max_attempts=3,
    backoff=ExponentialBackoff(base_delay=1.0, max_delay=60.0, jitter=0.1)
)
async def unreliable_api_call():
    ...
```

### Security (`agents/security/`)

#### Input Validation (`validation.py`)
Pydantic-based validation schemas:

```python
from agents.security import CompanyAnalysisRequest

request = CompanyAnalysisRequest(
    company_name="Acme Oy",
    business_id="1234567-8",
    analysis_depth="comprehensive"
)
```

#### Sanitization (`sanitization.py`)
Security protections:
- SSRF prevention (blocks internal IPs)
- Prompt injection detection
- HTML/XSS sanitization
- SQL injection prevention

```python
from agents.security import SecuritySanitizer

sanitizer = SecuritySanitizer()

# SSRF check
if not sanitizer.is_safe_url("http://192.168.1.1"):
    raise SecurityError("Internal IP blocked")

# Prompt injection check
if sanitizer.detect_prompt_injection(user_input):
    raise SecurityError("Potential prompt injection")
```

## External Integrations

### OpenAI API
- GPT-4 for agent reasoning
- Embeddings for semantic search
- Function calling for tool use

### YTJ (Finnish Business Register)
- Company lookup by business ID
- Financial data retrieval
- Official company information

### Stripe
- Subscription management
- Usage-based billing
- Webhook handling for events

### SendGrid
- Transactional emails
- Magic link delivery
- Notification emails

### Redis
- Session storage
- Cache layer
- Background task queue
- Real-time pub/sub

## Testing

**Test Suite:** 372 tests (29 skipped when Redis unavailable)

```bash
# Run all tests
pytest tests/ -v

# Run specific module
pytest tests/unit/test_resilience.py -v

# Run with coverage
pytest tests/ --cov=agents --cov-report=html
```

**Test Categories:**
- `tests/unit/` - Unit tests for individual components
- `tests/integration/` - Integration tests with dependencies

## Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/brandista

# Redis
REDIS_URL=redis://localhost:6379

# OpenAI
OPENAI_API_KEY=sk-...

# Stripe
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# SendGrid
SENDGRID_API_KEY=SG....

# Application
SECRET_KEY=your-secret-key
ENVIRONMENT=production
LOG_LEVEL=INFO
```

## Deployment

**Platform:** Railway

**Configuration Files:**
- `railway.json` - Railway deployment config
- `nixpacks.toml` - Build configuration
- `requirements.txt` - Python dependencies

**Health Check:** `GET /health`

## Performance Considerations

1. **Connection Pooling** - Database and Redis connections pooled
2. **Async/Await** - All I/O operations are async
3. **Circuit Breakers** - Prevent cascade failures to external APIs
4. **Caching** - Redis caching for frequently accessed data
5. **Background Tasks** - Long-running tasks queued in Redis

## Security Measures

1. **Authentication** - Magic link passwordless auth
2. **Input Validation** - Pydantic schemas for all inputs
3. **SSRF Protection** - URL validation blocks internal IPs
4. **Prompt Injection** - Detection and blocking
5. **Sensitive Data Masking** - Automatic in logs
6. **Rate Limiting** - Per-user and per-endpoint limits

## Monitoring

### Metrics Endpoint
`GET /metrics` - Prometheus-format metrics

### Key Metrics
- `http_requests_total` - Request counts by endpoint
- `http_request_duration_seconds` - Latency histogram
- `agent_tasks_total` - Agent task counts
- `circuit_breaker_state` - Circuit breaker states
- `active_users` - Currently active users

### Logging
- Structured JSON format for log aggregation
- Correlation IDs for request tracing
- Automatic sensitive data masking
