# Growth Engine Quality Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all security vulnerabilities, data integrity bugs, runtime crashes, and performance issues identified in the systematic code review, leaving the Growth Engine production-safe and significantly more reliable.

**Architecture:** Fixes are organized into 9 independent tasks that each produce a working, testable result. Tasks 1–2 are security-critical and must be done first. Tasks 3–8 are independent of each other. Task 9 adds integration test coverage for the core analysis pipeline.

**Tech Stack:** Python 3.11, FastAPI, asyncpg, passlib[bcrypt], PostgreSQL, Redis, OpenAI GPT-4o-mini

---

## File Map

| File | Change |
|------|--------|
| `main.py` | Fix SECRET_KEY fail-fast, replace SimplePasswordContext, remove hardcoded passwords, fix duplicate OpenAI init, fix CORS env var, remove Manus VM URL |
| `agent_api.py` | Fix WebSocket SECRET_KEY to use shared config, fix bare except, fix `is_running` |
| `agents/config.py` | **CREATE** — single source of truth for SECRET_KEY, shared by main.py and agent_api.py |
| `agents/orchestrator.py` | Add `is_running` property, fix `run_analysis()` to create per-run agent instances |
| `agents/blackboard.py` | Cap `_history` to 500 entries, fix `publish_sync` error handling, fix `get()` expiry mutation under lock |
| `agents/run_context.py` | Fix lazy lock init race condition, fix `create_run_context_sync` threading lock |
| `agents/scoring_constants.py` | Clarify `security` vs `security_posture` — rename or merge to prevent weight confusion |
| `agents/guardian_agent.py` | Use `context.html_content` instead of re-fetching HTML |
| `database.py` | Wrap all psycopg2 calls in `asyncio.run_in_executor`, add connection pool |
| `main.py` (rate limiting) | Enable rate limiting by default with sensible defaults |
| `agents/run_store.py` | Log warning (not silent) when Redis falls back to InMemoryRunStore |
| `tests/test_security.py` | **CREATE** — tests for password hashing, SECRET_KEY, auth |
| `tests/test_agent_isolation.py` | **CREATE** — tests for per-run agent instance isolation |
| `tests/test_integration_pipeline.py` | **CREATE** — integration tests for orchestrator.run_analysis() |

Dead code to delete: `Enhanced_90day_plan.py`, `agent_chat_v2.py`, `agent_reports.py`, `scoring_config.json`

---

## Context: Current State

- **Test baseline**: 545 tests passing, 29 skipped — run `python3 -m pytest tests/ -x -q` before starting
- **Working directory**: `/Users/tuukka/Downloads/Projects/Brandista/koodi/brandista-api-git/`
- **Deploy**: Railway auto-deploys from GitHub push on `main` branch
- **Entry point**: `main.py` (11,500 LOC monolith — `app/main.py` wraps it, is NOT a separate codebase)

---

## Task 1: Security — Fix Authentication & Password Hashing

**Why first:** Hardcoded passwords and weak SHA256 hashing are the most urgent security risks.

**Files:**
- Modify: `main.py` lines 1900–1943

- [ ] **Step 1: Write failing test for bcrypt hashing**

```bash
cat > tests/test_security.py << 'EOF'
"""Tests for authentication security."""
import pytest
from passlib.context import CryptContext


def test_password_hash_is_bcrypt():
    """Password hashes must use bcrypt, not SHA256."""
    from main import pwd_context
    hashed = pwd_context.hash("testpassword")
    # bcrypt hashes start with $2b$
    assert hashed.startswith("$2b$"), f"Expected bcrypt hash, got: {hashed[:10]}"


def test_password_verify_correct():
    from main import pwd_context
    hashed = pwd_context.hash("mypassword")
    assert pwd_context.verify("mypassword", hashed) is True


def test_password_verify_wrong():
    from main import pwd_context
    hashed = pwd_context.hash("mypassword")
    assert pwd_context.verify("wrongpassword", hashed) is False


def test_hardcoded_passwords_not_present():
    """Source code must not contain plaintext passwords."""
    with open("main.py") as f:
        source = f.read()
    for pw in ["user123", "kaikka123", "superpower123"]:
        assert pw not in source, f"Hardcoded password '{pw}' found in main.py"
EOF
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_security.py -v
```
Expected: FAIL — `test_password_hash_is_bcrypt` fails because `SimplePasswordContext` uses SHA256.

- [ ] **Step 3: Replace `SimplePasswordContext` with passlib bcrypt**

Find in `main.py` around line 1900:
```python
class SimplePasswordContext:
    def hash(self, password: str) -> str:
        return hashlib.sha256(f"brandista_{password}_salt".encode()).hexdigest()
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        return self.hash(plain_password) == hashed_password

# ...
pwd_context = SimplePasswordContext()
```

Replace with:
```python
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```

`passlib` is already in `requirements.txt` — no new dependency needed.

- [ ] **Step 4: Remove hardcoded passwords from `USERS_DB`**

Find `USERS_DB` around line 1922:
```python
USERS_DB = {
    "user@example.com": {"hashed_password": pwd_context.hash("user123"), ...},
    "admin@brandista.eu": {"hashed_password": pwd_context.hash("kaikka123"), ...},
    "super@brandista.eu": {"hashed_password": pwd_context.hash("superpower123"), ...}
}
```

Replace with environment-variable-driven init:
```python
def _build_users_db() -> dict:
    """
    Load admin users from environment variables.
    Set ADMIN_USER_EMAIL and ADMIN_USER_PASSWORD_HASH env vars.
    Generate hash with: python3 -c "from passlib.context import CryptContext; c=CryptContext(schemes=['bcrypt']); print(c.hash('yourpassword'))"
    """
    users = {}
    admin_email = os.getenv("ADMIN_USER_EMAIL")
    admin_hash = os.getenv("ADMIN_USER_PASSWORD_HASH")
    super_email = os.getenv("SUPER_USER_EMAIL")
    super_hash = os.getenv("SUPER_USER_PASSWORD_HASH")

    if admin_email and admin_hash:
        users[admin_email] = {
            "hashed_password": admin_hash,
            "role": "admin",
            "name": os.getenv("ADMIN_USER_NAME", "Admin"),
        }
    if super_email and super_hash:
        users[super_email] = {
            "hashed_password": super_hash,
            "role": "super",
            "name": os.getenv("SUPER_USER_NAME", "Super"),
        }

    if not users:
        logger.warning(
            "⚠️ No admin users configured via env vars. "
            "Set ADMIN_USER_EMAIL and ADMIN_USER_PASSWORD_HASH."
        )
    return users

USERS_DB = _build_users_db()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_security.py -v
```
Expected: All 4 tests PASS.

- [ ] **Step 6: Verify full test suite still passes**

```bash
python3 -m pytest tests/ -x -q
```
Expected: 545 passed (or more with new tests), 0 failures.

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_security.py
git commit -m "fix(security): replace SHA256 with bcrypt, remove hardcoded passwords

- Replace SimplePasswordContext with passlib CryptContext (bcrypt)
- Remove hardcoded user123/kaikka123/superpower123 from source
- Load admin users from ADMIN_USER_EMAIL/ADMIN_USER_PASSWORD_HASH env vars
- Add tests/test_security.py"
```

---

## Task 2: Security — Fix SECRET_KEY + Shared Config Module

**Why:** `main.py` and `agent_api.py` each define their own `SECRET_KEY` with different fallbacks. JWT tokens created in main.py may not verify in WebSocket handler and vice versa.

**Files:**
- Create: `agents/config.py`
- Modify: `main.py` line 369
- Modify: `agent_api.py` line 454

- [ ] **Step 1: Create `agents/config.py` — single source of truth**

```python
# agents/config.py
"""
Shared configuration for the Growth Engine.
All modules must import SECRET_KEY from here, never re-define it.
"""
import os
import logging

logger = logging.getLogger(__name__)

def _get_secret_key() -> str:
    key = os.getenv("SECRET_KEY")
    if key:
        return key
    env = os.getenv("ENVIRONMENT", "").lower()
    railway = os.getenv("RAILWAY_ENVIRONMENT", "")
    if env == "production" or railway:
        raise RuntimeError(
            "SECRET_KEY environment variable is required in production. "
            "Set it in Railway variables."
        )
    # Development fallback — stable across restarts, clearly insecure
    dev_key = "DEV-ONLY-INSECURE-KEY-SET-SECRET_KEY-IN-PRODUCTION"
    logger.warning(
        "⚠️  Using insecure dev SECRET_KEY. "
        "Set SECRET_KEY environment variable before deploying to production."
    )
    return dev_key

SECRET_KEY = _get_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
```

- [ ] **Step 2: Update `main.py` to import from shared config**

Find line 369:
```python
SECRET_KEY = os.getenv("SECRET_KEY", "brandista-key-" + os.urandom(32).hex())
```

Replace with:
```python
from agents.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
```

Remove any other local definitions of `ALGORITHM` or `ACCESS_TOKEN_EXPIRE_MINUTES` if they exist near line 369 (they'll now come from config).

- [ ] **Step 3: Update `agent_api.py` to import from shared config**

Find line 454:
```python
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
```

Replace with:
```python
from agents.config import SECRET_KEY, ALGORITHM
```

- [ ] **Step 4: Add test for SECRET_KEY consistency**

Add to `tests/test_security.py`:
```python
def test_secret_key_is_deterministic_on_reload():
    """SECRET_KEY must not change on module reload (would invalidate all JWTs)."""
    import importlib
    import agents.config as cfg
    key_before = cfg.SECRET_KEY
    importlib.reload(cfg)
    key_after = cfg.SECRET_KEY
    assert key_before == key_after, \
        "SECRET_KEY changed after reload — all existing JWTs would be invalidated"


def test_secret_key_not_random_per_import():
    """SECRET_KEY must be stable across imports (not regenerated each time)."""
    from agents.config import SECRET_KEY as key1
    from agents.config import SECRET_KEY as key2
    assert key1 == key2, "SECRET_KEY must not change between imports"
```

- [ ] **Step 5: Fix CORS to remove hardcoded Manus VM URL**

In `main.py` around line 1749, find:
```python
"https://3000-ip92lxeccquecaiidxzl0-6aa4782a.manusvm.computer"
```

Remove that line. Also move Railway URL to env var:
```python
# Replace hardcoded Railway URL with:
*([os.getenv("RAILWAY_BACKEND_URL")] if os.getenv("RAILWAY_BACKEND_URL") else []),
```

- [ ] **Step 6: Run tests**

```bash
python3 -m pytest tests/test_security.py -v
```
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add agents/config.py main.py agent_api.py tests/test_security.py
git commit -m "fix(security): shared SECRET_KEY config, fix CORS

- Create agents/config.py as single source of truth for SECRET_KEY
- SECRET_KEY fails fast in production if not set via env var
- Both main.py and agent_api.py now import from agents/config
- Remove Manus VM URL from CORS whitelist
- Move Railway backend URL to RAILWAY_BACKEND_URL env var"
```

---

## Task 3: Fix Agent Isolation — Per-Run Fresh Instances

**Why:** All users share the same agent instances in the singleton orchestrator. Concurrent analyses overwrite each other's state. This causes data leaks between users.

**Files:**
- Modify: `agents/orchestrator.py`

- [ ] **Step 1: Write failing test for isolation**

```bash
cat > tests/test_agent_isolation.py << 'EOF'
"""Tests for agent instance isolation between concurrent runs."""
import pytest
import asyncio
from agents.orchestrator import GrowthEngineOrchestrator


def test_run_analysis_creates_fresh_agents():
    """Each call to run_analysis must use fresh agent instances."""
    orchestrator = GrowthEngineOrchestrator()

    # Simulate two concurrent runs getting different agent instances
    agents_run1 = orchestrator._create_agents_for_run()
    agents_run2 = orchestrator._create_agents_for_run()

    for agent_id in agents_run1:
        assert agents_run1[agent_id] is not agents_run2[agent_id], \
            f"Agent {agent_id} is the same instance across runs — state leak risk"


def test_orchestrator_has_is_running_property():
    """orchestrator.is_running must exist and return a bool."""
    orchestrator = GrowthEngineOrchestrator()
    result = orchestrator.is_running
    assert isinstance(result, bool)
EOF
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_agent_isolation.py -v
```
Expected: FAIL — `_create_agents_for_run` does not exist, `is_running` raises AttributeError.

- [ ] **Step 3: Add `_create_agents_for_run()` and `is_running` to orchestrator**

In `agents/orchestrator.py`, find `__init__` and `_register_agents`. Add a set to track active runs and wire up the new methods:

```python
def __init__(self):
    self.agents: Dict[str, BaseAgent] = {}
    self._active_runs: set[str] = set()  # Track active run IDs for is_running
    self._register_agents()

@property
def is_running(self) -> bool:
    """Returns True if any analysis run is currently active."""
    return len(self._active_runs) > 0

def _create_agents_for_run(self) -> Dict[str, "BaseAgent"]:
    """
    Create fresh agent instances for a single analysis run.
    MUST be called per-run, never shared between concurrent users.
    """
    from agents.scout_agent import ScoutAgent
    from agents.analyst_agent import AnalystAgent
    from agents.guardian_agent import GuardianAgent
    from agents.prospector_agent import ProspectorAgent
    from agents.strategist_agent import StrategistAgent
    from agents.planner_agent import PlannerAgent

    agents = {}
    for agent in [
        ScoutAgent(),
        AnalystAgent(),
        GuardianAgent(),
        ProspectorAgent(),
        StrategistAgent(),
        PlannerAgent(),
    ]:
        agents[agent.id] = agent
    return agents
```

- [ ] **Step 4: Update `run_analysis()` to use fresh agents per run**

Find `run_analysis()` in `orchestrator.py`. It uses `self.agents` (shared singletons). Change it to create fresh instances AND thread them through all helper methods.

First, update `run_analysis()` to create and register the run:

```python
async def run_analysis(self, url: str, run_id: str, user_id: str = None, **kwargs):
    # Create fresh agents for this specific run — prevents state leak between users
    run_agents = self._create_agents_for_run()
    self._active_runs.add(run_id)
    try:
        # ... rest of run_analysis passes run_agents to _run_agent/_run_parallel
    finally:
        self._active_runs.discard(run_id)
```

Next, update `_run_agent()` to accept and use `run_agents` instead of `self.agents`:

```python
async def _run_agent(self, agent_id: str, context, run_agents: Dict[str, "BaseAgent"], **kwargs):
    agent = run_agents.get(agent_id)  # Use per-run instance, not self.agents
    if not agent:
        logger.warning("[Orchestrator] Agent %s not found in run_agents", agent_id)
        return None
    return await agent.execute(context, **kwargs)
```

Similarly update `_run_parallel()`:

```python
async def _run_parallel(self, agent_ids: list, context, run_agents: Dict[str, "BaseAgent"], **kwargs):
    tasks = [self._run_agent(aid, context, run_agents, **kwargs) for aid in agent_ids]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

Update all call sites of `_run_agent()` and `_run_parallel()` inside `run_analysis()` to pass `run_agents`.

Note: `self.agents` can remain for backward compatibility and status queries but must never be used during execution.

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_agent_isolation.py tests/ -x -q
```
Expected: New isolation tests pass, all 545 existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add agents/orchestrator.py tests/test_agent_isolation.py
git commit -m "fix(agents): per-run fresh agent instances to prevent state leaks

- Add _create_agents_for_run() that creates fresh instances per analysis
- run_analysis() now uses per-run agents instead of shared self.agents
- Add is_running property using self._active_runs set (tracked in run_analysis)
- Add tests/test_agent_isolation.py"
```

---

## Task 4: Fix Runtime Crashes & Async Bugs

Fix three issues that cause crashes or silent failures in production.

**Files:**
- Modify: `agent_api.py` lines 50–60, 240
- Modify: `agents/blackboard.py` lines 251–259, 275–290
- Modify: `agents/run_context.py` lines 180–187

- [ ] **Step 1: Fix bare `except:` in `agent_api.py`**

Find around line 55:
```python
    except:
        return None
```
Replace with:
```python
    except Exception:
        return None
```

- [ ] **Step 2: Fix `is_running` AttributeError in `agent_api.py`**

The fix in Task 3 (adding `is_running` property to orchestrator) resolves this. Verify:

Find `agent_api.py` line 240:
```python
"is_running": orchestrator.is_running,
```
This will now work after Task 3. No change needed here.

- [ ] **Step 3: Fix `publish_sync` in `blackboard.py`**

Find around line 251:
```python
def publish_sync(self, key: str, value: Any, agent_id: str, **kwargs):
    """Synchronous publish (schedules async)"""
    asyncio.create_task(self.publish(key, value, agent_id, **kwargs))
```

Replace with:
```python
def publish_sync(self, key: str, value: Any, agent_id: str, **kwargs):
    """
    Synchronous publish — schedules async publish if event loop is running,
    otherwise logs a warning. Never silently swallows errors.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "[Blackboard] publish_sync called outside async context — "
            "entry will not be published. key=%s agent=%s", key, agent_id
        )
        return

    task = loop.create_task(self.publish(key, value, agent_id, **kwargs))

    def _handle_error(t: asyncio.Task):
        exc = t.exception()
        if exc:
            logger.error(
                "[Blackboard] publish_sync async task failed: %s", exc,
                exc_info=exc
            )

    task.add_done_callback(_handle_error)
```

- [ ] **Step 4: Fix `Blackboard.get()` — expiry deletion is best-effort**

`get()` is a **synchronous** method and cannot `await` a lock. The safe fix is to use `dict.pop()` which is atomic under Python's GIL:

Find around line 278:
```python
    if entry.is_expired():
        del self._data[key]
        return default
```

Replace with:
```python
    if entry.is_expired():
        # dict.pop() is GIL-atomic in CPython — safe for best-effort expiry cleanup
        # in a sync method. The async write path holds self._lock for consistency.
        self._data.pop(key, None)
        return default
```

Note: converting `get()` to `async def` would be a larger refactor. The GIL-based approach is safe for CPython and consistent with how Python's built-in cache implementations handle sync expiry.

- [ ] **Step 5: Fix `RunContext._get_lock()` lazy init race condition**

Find `agents/run_context.py` around line 180:
```python
_registry_lock: Optional[asyncio.Lock] = None

@classmethod
def _get_lock(cls) -> asyncio.Lock:
    if cls._registry_lock is None:
        cls._registry_lock = asyncio.Lock()
    return cls._registry_lock
```

**Important Python 3.10+ constraint**: `asyncio.Lock()` must be created inside a running event loop. Creating it at module import time (outside any coroutine) raises a `RuntimeError` in Python 3.12+. The correct fix is to create the lock lazily *inside* an async context, protected by a threading.Lock for the lazy-init check:

```python
import threading

_registry_lock: Optional[asyncio.Lock] = None
_lock_init_guard: threading.Lock = threading.Lock()  # protects lazy init

@classmethod
def _get_lock(cls) -> asyncio.Lock:
    """Get (or create) the async registry lock. Safe for concurrent callers."""
    if cls._registry_lock is None:
        with cls._lock_init_guard:
            # Double-checked locking: check again under threading lock
            if cls._registry_lock is None:
                cls._registry_lock = asyncio.Lock()
    return cls._registry_lock
```

This is safe because:
- `threading.Lock` is GIL-compatible and doesn't require an event loop
- `asyncio.Lock()` is only created once, inside the first coroutine that calls `_get_lock()` (where a running loop is guaranteed)
- The double-check prevents duplicate creation under race conditions

- [ ] **Step 6: Build and test**

```bash
python3 -m pytest tests/ -x -q
```
Expected: All 545+ tests pass.

- [ ] **Step 7: Commit**

```bash
git add agent_api.py agents/blackboard.py agents/run_context.py
git commit -m "fix(runtime): fix crashes and async bugs

- Fix bare except: -> except Exception: in agent_api.py
- Fix publish_sync: add done-callback error logging, handle no-loop case
- Fix Blackboard.get(): use GIL-atomic dict.pop() for sync expiry cleanup
- Fix RunContext._get_lock(): module-level init prevents race condition"
```

---

## Task 5: Fix Database — Async + Connection Pool

**Why:** All database calls use synchronous `psycopg2` and create a new connection per call. In async FastAPI, this blocks the event loop. `asyncpg` is already in requirements.txt.

**Files:**
- Modify: `database.py`

- [ ] **Step 1: Check current database.py structure**

```bash
grep -n "def \|connect_db\|psycopg2\|asyncpg" database.py | head -40
```

- [ ] **Step 2: Add `asyncio.run_in_executor` wrapper for all DB functions**

At the top of `database.py`, add a helper that runs blocking psycopg2 calls off the event loop:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Thread pool for running sync DB operations off the async event loop
_db_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="db-worker")


async def run_in_db_thread(func, *args, **kwargs):
    """Run a synchronous database function in a thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _db_executor,
        lambda: func(*args, **kwargs)
    )
```

- [ ] **Step 3: Add async wrappers for the most-called sync functions**

For each frequently called sync function (e.g., `get_user`, `save_analysis_result`, `get_analysis_history`), add an async wrapper:

```python
# Example: if sync function is get_user(email: str) -> dict
async def async_get_user(email: str) -> dict:
    return await run_in_db_thread(get_user, email)
```

Find all DB functions called from async FastAPI routes and add async wrappers for them.

- [ ] **Step 4: Add connection pooling with psycopg2 pool**

Find `connect_db()` function. Replace single-connection approach with a pool:

```python
import psycopg2.pool

_connection_pool: psycopg2.pool.ThreadedConnectionPool = None

def get_connection_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _connection_pool
    if _connection_pool is None or _connection_pool.closed:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            return None
        _connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            dsn=db_url,
        )
    return _connection_pool


def connect_db():
    """Get a connection from the pool."""
    pool = get_connection_pool()
    if pool is None:
        return None
    try:
        return pool.getconn()
    except psycopg2.pool.PoolError as e:
        logger.error("[DB] Connection pool error: %s", e)
        return None


def release_connection(conn):
    """Return connection to pool. Call in finally blocks."""
    pool = get_connection_pool()
    if pool and conn:
        pool.putconn(conn)
```

Update all DB functions to use `release_connection()` in `finally` blocks.

- [ ] **Step 5: Fix `unified_context.py` sync call in async orchestrator**

In `agents/orchestrator.py` around line 136:
```python
from unified_context import get_unified_context
unified_context_data = get_unified_context(user_id).to_dict()
```

Replace with:
```python
from database import run_in_db_thread
from unified_context import get_unified_context

raw = await run_in_db_thread(get_unified_context, user_id)
unified_context_data = raw.to_dict() if raw else {}
```

- [ ] **Step 6: Run tests**

```bash
python3 -m pytest tests/ -x -q
```
Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add database.py agents/orchestrator.py
git commit -m "fix(db): connection pool + async wrappers for psycopg2

- Add ThreadedConnectionPool (min=2, max=10) to avoid per-call TCP overhead
- Add run_in_db_thread() helper for non-blocking DB ops in async context
- Fix unified_context.py sync call in async orchestrator
- DB connections now return to pool in finally blocks"
```

---

## Task 6: Fix Scoring Constants + Guardian Duplicate Fetch

Two independent fixes that improve result accuracy.

**Files:**
- Modify: `agents/scoring_constants.py` lines 210–219
- Modify: `agents/guardian_agent.py` lines 449–456

- [ ] **Step 1: Clarify `security` vs `security_posture` in scoring weights**

Read the strategist agent to understand what keys it actually produces:
```bash
grep -n "security\|security_posture" agents/strategist_agent.py | head -20
```

Then read `scoring_constants.py` line 210–219. The current weights have both `security` (0.10) and `security_posture` (0.10). They sum to 1.0, but if strategist only ever provides one of them, 10% of weight is silently dropped.

Determine the correct fix:
- If both are genuinely different dimensions → rename clearly (e.g., `technical_security` and `business_security_posture`) and add a comment
- If one is unused → merge into one entry at 0.20 and remove the other

Apply the fix and add a comment:
```python
STRATEGIC_CATEGORY_WEIGHTS = {
    'seo': 0.10,
    'performance': 0.10,
    'security': 0.20,        # Merged from 'security' + 'security_posture' — both measured same dimension
    'content': 0.20,
    'ux': 0.15,
    'ai_visibility': 0.15,
    'competitive_edge': 0.10,
}
# IMPORTANT: weights must sum to exactly 1.0
assert abs(sum(STRATEGIC_CATEGORY_WEIGHTS.values()) - 1.0) < 0.001, \
    f"STRATEGIC_CATEGORY_WEIGHTS must sum to 1.0, got {sum(STRATEGIC_CATEGORY_WEIGHTS.values())}"
```

Note: This is a judgment call. If `security` and `security_posture` ARE intentionally separate, keep both but add the assert and explicit comment.

- [ ] **Step 2: Add scoring weights test**

Check if `tests/unit/test_scoring_constants.py` already exists:
```bash
ls tests/unit/ | grep scoring
```

Add to it (or create `tests/unit/test_scoring_constants.py` if it doesn't exist):
```python
def test_strategic_weights_sum_to_one():
    from agents.scoring_constants import STRATEGIC_CATEGORY_WEIGHTS
    total = sum(STRATEGIC_CATEGORY_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001, \
        f"STRATEGIC_CATEGORY_WEIGHTS sums to {total}, expected 1.0"
```

- [ ] **Step 3: Fix Guardian duplicate HTTP fetch**

In `agents/guardian_agent.py` around line 449–456:
```python
import httpx
async with httpx.AsyncClient(timeout=10.0) as client:
    resp = await client.get(context.url)
    html_content = resp.text[:50000]
```

Replace with:
```python
# Use HTML already fetched by ScoutAgent — stored in run context
html_content = (
    getattr(context, 'html_content', None)
    or getattr(context, 'raw_html', None)
    or ""
)

if not html_content:
    # Fallback: fetch only if not available from earlier agents
    logger.debug("[Guardian] html_content not in context, fetching from %s", context.url)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(context.url)
            html_content = resp.text[:50000]
    except Exception as e:
        logger.warning("[Guardian] Failed to fetch HTML: %s", e)
        html_content = ""
else:
    html_content = html_content[:50000]
    logger.debug("[Guardian] Using cached HTML from context (%d chars)", len(html_content))
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/ -x -q
```
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add agents/scoring_constants.py agents/guardian_agent.py tests/unit/
git commit -m "fix(scoring): clarify security weights, Guardian uses cached HTML

- Fix STRATEGIC_CATEGORY_WEIGHTS: clarify security vs security_posture
- Add runtime assert that weights sum to 1.0
- Guardian now uses context.html_content instead of re-fetching
  (falls back to HTTP only if not available in context)"
```

---

## Task 7: Fix Memory & Reliability Issues

**Files:**
- Modify: `agents/blackboard.py`
- Modify: `agents/run_store.py`

- [ ] **Step 1: Cap Blackboard history to prevent unbounded memory growth**

In `agents/blackboard.py`, find `__init__`:
```python
self._history: List[BlackboardEntry] = []
```

Change to:
```python
self._history: List[BlackboardEntry] = []
self._max_history: int = 500  # Prevent unbounded memory growth
```

Find where `_history.append(entry)` is called (line 218):
```python
self._history.append(entry)
```

Replace with:
```python
self._history.append(entry)
# Trim oldest entries if over limit
if len(self._history) > self._max_history:
    self._history = self._history[-self._max_history:]
```

- [ ] **Step 2: Fix Redis fallback to log a warning**

In `agents/run_store.py`, find the fallback where `InMemoryRunStore` is used when Redis is unavailable. Find the silent fallback (around line 583–590):
```python
# Something like:
except Exception:
    return InMemoryRunStore()
```

Replace with explicit warning:
```python
except Exception as e:
    logger.warning(
        "⚠️  Redis connection failed (%s). Falling back to InMemoryRunStore. "
        "Run state will NOT be shared across workers. "
        "Cancel operations will not propagate. "
        "Set REDIS_URL environment variable to fix this.",
        e
    )
    return InMemoryRunStore()
```

- [ ] **Step 3: Enable rate limiting by default**

**Important**: `RATE_LIMIT_ENABLED` is defined **twice** in `main.py` — around line 413 AND around line 682. Both definitions must be updated, or the second one will override the first.

Search for all definitions:
```bash
grep -n "RATE_LIMIT_ENABLED\|RATE_LIMIT_PER_MINUTE" main.py
```

For **each** occurrence of the `"false"` default, change to `"true"`, and change the per-minute default from `"20"` to `"10"`:
```python
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
```

Remove the duplicate definition (keep only the first one, at the lower line number). If they are in different scopes, keep both updated.

20 analyses per minute is too high (each analysis makes many LLM calls). 10/minute per IP is more reasonable. Set `RATE_LIMIT_ENABLED=false` in dev `.env` if needed.

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/ -x -q
```
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add agents/blackboard.py agents/run_store.py main.py
git commit -m "fix(memory): cap blackboard history, explicit Redis fallback warning

- Blackboard._history capped at 500 entries (FIFO eviction)
- Redis fallback now logs explicit warning with instructions to fix
- Rate limiting enabled by default (10/min per IP)
- Set RATE_LIMIT_ENABLED=false in dev .env to disable"
```

---

## Task 8: Tech Debt Cleanup

Remove dead code and fix code quality issues.

**Files to DELETE:**
- `Enhanced_90day_plan.py` (~36,000 lines, not imported anywhere)
- `agent_chat_v2.py` (~40,000 lines, legacy)
- `agent_reports.py` (~30,000 lines, legacy)
- `scoring_config.json` (legacy, actual constants are in scoring_constants.py)

**Files to modify:**
- `main.py` (remove duplicate OpenAI init, fix debug logging)
- `agent_api.py` (fix bare except already done in Task 4)

- [ ] **Step 1: Find and remove all hard imports of Enhanced_90day_plan**

`agent_chat_v2.py` and `agent_reports.py` are wrapped in `try/except ImportError` — safe to delete.
`Enhanced_90day_plan.py` has at least one **hard (non-optional) import** in `main.py`. Find all of them:

```bash
grep -n "Enhanced_90day_plan\|ActionItem\|Plan90D\|generate_enhanced_90day_plan" main.py
```

For each hard import found (e.g., `from Enhanced_90day_plan import ActionItem, Plan90D, generate_enhanced_90day_plan`):
- Check if `ActionItem`, `Plan90D`, or `generate_enhanced_90day_plan` are actually used in `main.py`
- If used in live code paths → stub them or find their replacement in `agents/planner_agent.py`
- If the import is only used in dead/legacy code sections → remove both the import AND the dead code using them

This step must be completed before Step 2. The app will crash on startup if this import remains.

```bash
grep -rn "scoring_config.json" --include="*.py" .
```
Expected: No references (or only comments).

- [ ] **Step 2: Verify all hard imports are resolved**

```bash
grep -rn "Enhanced_90day_plan\|agent_chat_v2\|agent_reports" --include="*.py" . | grep -v "^./Enhanced_90day_plan\|^./agent_chat_v2\|^./agent_reports"
```

Expected: Only `try/except ImportError` wrapped references remain (or none at all). Zero hard imports.

- [ ] **Step 3: Delete dead code files**

```bash
git rm Enhanced_90day_plan.py agent_chat_v2.py agent_reports.py scoring_config.json
```

- [ ] **Step 4: Remove duplicate OpenAI client initialization**

In `main.py`, find the second initialization around line 829:
```python
if OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    logger.info(f"OpenAI client initialized (model={OPENAI_MODEL})")
```

Remove it entirely (keep only the first one at line 449).

- [ ] **Step 5: Fix overly verbose info-level logging**

Search for debug traces logged at INFO level:
```bash
grep -n 'logger.info.*\[WS\]\|logger.info.*DEBUG\|logger.info.*sync_progress' agent_api.py orchestrator.py base_agent.py | head -20
```

Change these to `logger.debug(...)`:
```python
# Example: change
logger.info("[WS] sync_progress called for run_id=%s", run_id)
# to:
logger.debug("[WS] sync_progress called for run_id=%s", run_id)
```

- [ ] **Step 6: Run tests and verify nothing broke**

```bash
python3 -m pytest tests/ -x -q
```
Expected: All tests pass (deleted files had no tests importing them).

- [ ] **Step 7: Commit**

```bash
git add -u main.py agents/
git rm Enhanced_90day_plan.py agent_chat_v2.py agent_reports.py scoring_config.json
git commit -m "chore: remove dead code, fix logging levels

- Delete Enhanced_90day_plan.py (~36K LOC, unused)
- Delete agent_chat_v2.py (~40K LOC, legacy)
- Delete agent_reports.py (~30K LOC, legacy)
- Delete scoring_config.json (superseded by scoring_constants.py)
- Remove duplicate OpenAI client init in main.py
- Downgrade verbose sync/ws trace logs from INFO to DEBUG"
```

---

## Task 9: Integration Tests for Core Analysis Pipeline

**Why:** 545 unit tests but zero coverage for the actual analysis execution path (`agent.execute()`, `orchestrator.run_analysis()`). This is the most business-critical code.

**Files:**
- Create: `tests/test_integration_pipeline.py`

- [ ] **Step 1: Write integration tests**

```bash
cat > tests/test_integration_pipeline.py << 'EOF'
"""
Integration tests for the Growth Engine core analysis pipeline.
Tests verify the orchestrator and agents execute without crashing.
Uses mocked HTTP/LLM calls to avoid real network requests.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_llm_response():
    """Standard mock OpenAI response for testing."""
    mock = AsyncMock()
    mock.choices = [MagicMock(message=MagicMock(content='{"score": 75, "summary": "test"}'))]
    return mock


@pytest.fixture
def mock_http_response():
    """Standard mock HTTP response for testing."""
    mock = MagicMock()
    mock.status_code = 200
    mock.text = "<html><head><title>Test Site</title></head><body><p>Test content</p></body></html>"
    mock.headers = {"content-type": "text/html"}
    mock.url = "https://example.com"
    return mock


@pytest.mark.asyncio
async def test_orchestrator_creates_fresh_agents_per_run():
    """run_analysis must use fresh agent instances, not shared singletons."""
    from agents.orchestrator import GrowthEngineOrchestrator
    orchestrator = GrowthEngineOrchestrator()

    run1_agents = orchestrator._create_agents_for_run()
    run2_agents = orchestrator._create_agents_for_run()

    for agent_id in run1_agents:
        assert run1_agents[agent_id] is not run2_agents[agent_id], \
            f"Agent {agent_id} shared between runs — concurrent user data could leak"


@pytest.mark.asyncio
async def test_orchestrator_is_running_returns_bool():
    """is_running property must exist and return bool."""
    from agents.orchestrator import GrowthEngineOrchestrator
    orchestrator = GrowthEngineOrchestrator()
    assert isinstance(orchestrator.is_running, bool)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_scout_agent_execute_does_not_crash(mock_http_response):
    """ScoutAgent.execute() must complete without raising exceptions."""
    from agents.scout_agent import ScoutAgent
    from agents.run_context import RunContext

    agent = ScoutAgent()
    ctx = await RunContext.create(
        run_id="test-scout-001",
        url="https://example.com",
        user_id="test-user"
    )

    # httpx.AsyncClient is used as an async context manager — patch the class
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_http_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch("agents.base_agent.BaseAgent._call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = '{"competitors": [], "industry": "technology"}'
            try:
                await agent.execute(ctx)
            except Exception as e:
                pytest.fail(f"ScoutAgent.execute() raised unexpected exception: {e}")


@pytest.mark.asyncio
@pytest.mark.slow
async def test_concurrent_analyses_do_not_share_state(mock_http_response):
    """Two concurrent analyses must not contaminate each other's results."""
    from agents.orchestrator import GrowthEngineOrchestrator
    from agents.run_context import RunContext

    orchestrator = GrowthEngineOrchestrator()

    agents_a = orchestrator._create_agents_for_run()
    agents_b = orchestrator._create_agents_for_run()

    # Simulate state modification in run A
    for agent in agents_a.values():
        if hasattr(agent, 'insights'):
            agent.insights = ["run_a_insight"]

    # Run B agents should be unaffected
    for agent_id, agent in agents_b.items():
        if hasattr(agent, 'insights'):
            assert agent.insights != ["run_a_insight"], \
                f"Agent {agent_id} in run B has state from run A — isolation broken"


def test_scoring_weights_sum_to_one():
    """All weight dicts in scoring_constants must sum to 1.0."""
    from agents.scoring_constants import STRATEGIC_CATEGORY_WEIGHTS

    total = sum(STRATEGIC_CATEGORY_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001, \
        f"STRATEGIC_CATEGORY_WEIGHTS sums to {total:.3f}, not 1.0"
EOF
```

- [ ] **Step 2: Run the new tests**

```bash
python3 -m pytest tests/test_integration_pipeline.py -v
```
Expected: Most tests pass. `test_scout_agent_execute_does_not_crash` may need adjustment based on actual ScoutAgent interface.

- [ ] **Step 3: Run full test suite**

```bash
python3 -m pytest tests/ -x -q
```
Expected: 545+ tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_pipeline.py
git commit -m "test: add integration tests for core analysis pipeline

- test_orchestrator_creates_fresh_agents_per_run
- test_orchestrator_is_running_returns_bool
- test_scout_agent_execute_does_not_crash (slow, mocked LLM/HTTP)
- test_concurrent_analyses_do_not_share_state
- test_scoring_weights_sum_to_one"
```

---

## Final Verification

- [ ] **Run complete test suite one last time**

```bash
cd /Users/tuukka/Downloads/Projects/Brandista/koodi/brandista-api-git
python3 -m pytest tests/ -q
```
Expected: All new + existing tests pass. Zero failures.

- [ ] **Check git log**

```bash
git log --oneline -12
```
Expected: 9 clean commits, one per task.

- [ ] **Push to Railway**

```bash
git push
```
Railway auto-deploys. Monitor Railway logs for startup errors.

- [ ] **Verify Railway startup**

Check Railway logs for:
- ✅ No `SECRET_KEY` warning (env var must be set in Railway)
- ✅ No `AttributeError: is_running`
- ✅ `✅ OpenAI client initialized` (only once, not twice)
- ✅ Connection pool initialized
- ✅ No hardcoded password warnings

---

## Environment Variables to Set in Railway After Deployment

These must be set in the Railway dashboard before the new code is deployed:

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | JWT signing key (required) | `openssl rand -hex 32` |
| `ADMIN_USER_EMAIL` | Admin login email | `admin@brandista.eu` |
| `ADMIN_USER_PASSWORD_HASH` | bcrypt hash of admin password | `python3 -c "from passlib.context import CryptContext; c=CryptContext(schemes=['bcrypt']); print(c.hash('yourpassword'))"` |
| `SUPER_USER_EMAIL` | Super admin email | `super@brandista.eu` |
| `SUPER_USER_PASSWORD_HASH` | bcrypt hash of super password | _(same method)_ |
| `RAILWAY_BACKEND_URL` | Railway backend URL for CORS | `https://fastapi-production-51f9.up.railway.app` |

---

## Summary: What This Plan Fixes

| Task | Issues Fixed | Severity |
|------|-------------|---------|
| 1 — Password security | Hardcoded passwords, SHA256 → bcrypt | 🔴 Critical |
| 2 — Shared config | SECRET_KEY mismatch, random restart key, Manus VM CORS | 🔴 Critical |
| 3 — Agent isolation | Concurrent user state leaks, `is_running` crash | 🔴 Critical |
| 4 — Runtime crashes | `publish_sync` silent failure, `get()` race, lock race | 🟠 Major |
| 5 — Database | Blocking event loop, no connection pool | 🟠 Major |
| 6 — Scoring + Guardian | Weight clarity, duplicate HTTP fetch | 🟡 Moderate |
| 7 — Memory/reliability | Unbounded blackboard, silent Redis fallback, rate limit | 🟡 Moderate |
| 8 — Tech debt | 100K+ LOC dead code, duplicate init, debug logs | ⚪ Minor |
| 9 — Tests | Zero coverage on core pipeline → integration tests | 🟡 Moderate |
