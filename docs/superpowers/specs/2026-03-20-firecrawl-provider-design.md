# Firecrawl Provider Integration — Design Spec

**Date**: 2026-03-20
**Status**: Approved
**Version**: 1.1

---

## Context

`main.py` is an 11 500-line monolith. Its `get_website_content()` function (line 3433) is the sole content-fetching entrypoint used by both `main.py:7492` (run_analysis) and `agents/scout_agent.py:154`. Currently it runs in "aggressive" mode: Playwright launches first for every request, which is slow and resource-heavy.

Firecrawl is being added as a managed provider that delivers better rendered HTML/text for AI and content analysis, while keeping HTTP preflight for technical signals and Playwright as a last-resort fallback.

---

## Goals

1. Add Firecrawl as a content provider without breaking existing callers.
2. Isolate each provider so it can be tested and configured independently.
3. Default to `FIRECRAWL_ENABLED=false` so the refactor ships without behavior change first.
4. Add observability (per-fetch structured log line) from day one.
5. Protect against Firecrawl regressions with quality gates and a circuit breaker.

## Non-Goals (this iteration)

- Multi-page enrichment (`/about`, `/services`, etc.) — separate future iteration.
- Integration into `app/main.py` modular refactor — deferred until that is deployed.
- Replacing Playwright entirely — it remains as fallback.

---

## Architecture

### New directory

```
agents/content_fetch/
├── __init__.py              # re-exports get_website_content for backward compat
├── orchestrator.py          # provider sequencing, fallback, cache, metrics
├── http_provider.py         # httpx preflight (migrated from main.py _fetch_http)
├── firecrawl_provider.py    # firecrawl-py SDK, circuit breaker, Redis cache
└── playwright_provider.py   # Playwright render (migrated from main.py _render_spa)
```

### main.py change

`get_website_content()` at line 3433 becomes a thin import:

```python
from agents.content_fetch import get_website_content  # noqa: F401
```

The 230-line implementation moves into `orchestrator.py`. **Return type stays `Tuple[Optional[str], bool]`** — no callers change.

**`agents/scout_agent.py` import chain**: `scout_agent.py:91` imports `get_website_content` from `main` (`from main import get_website_content`). Since `main.py` re-exports from `agents.content_fetch`, this chain continues to work without touching `scout_agent.py`. Do not update the scout agent import as part of this change — that cleanup belongs to a future module migration.

### In-memory cache migration

`main.py` currently maintains a module-level `content_cache` dict (line ~372) with `get_content_cache_key` and `is_content_cache_valid` helpers. These must be migrated faithfully into `orchestrator.py` — **not dropped** — to guarantee zero behavior change in Phase 1. The in-memory cache covers all providers (HTTP, Playwright). Firecrawl results get an additional Redis-backed cache on top (see below). The two caches are complementary: in-memory for speed within a worker, Redis for cross-request deduplication.

---

## Provider Details

### http_provider.py

- Extracted from current `_fetch_http` inner function.
- Returns `httpx.Response | None`.
- Used as cheap preflight for all fetches regardless of which provider wins.
- Supplies status, headers, redirect chain, and baseline HTML to the orchestrator.
- If preflight returns `None` (timeout, network error, bot block), `baseline_html` is treated as `""` (empty string, length 0) for quality gate comparisons.

### firecrawl_provider.py

```python
app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
result = app.scrape_url(url, formats=["html", "markdown"], timeout=FIRECRAWL_TIMEOUT)
```

`FIRECRAWL_TIMEOUT` is passed directly to `scrape_url` — it is not dead config.

**Startup validation**: at module level (not deferred to first call), if `FIRECRAWL_ENABLED=true` and `FIRECRAWL_API_KEY` is `None`, raise `ValueError` immediately — consistent with how `agents/config.py` handles `SECRET_KEY`. This prevents silent degradation to Playwright on every request.

**Redis client initialization**: deferred to first use (not at module import), so the module can be imported safely in local development without a Redis connection.

**Circuit breaker** (in-memory, per worker process):
- Opens after 3 consecutive failures.
- Half-open after 5 minutes: one probe request allowed.
- If probe succeeds → closed; if probe fails → back to open.
- Note: Railway production runs a single Uvicorn worker (Nixpacks default). The per-process breaker is therefore sufficient and does not need Redis backing. If multi-worker is ever enabled, revisit this.

**Redis cache**:
- Key: `firecrawl:v1:{md5(url|mode|force_spa)}` — includes provider version and fetch shape so config changes and quality-gate revisions don't silently serve stale results
- TTL: 3600s (1 hour)
- Skips SDK call on cache hit, returns cached html.

**Quality gate** (result accepted only if all pass):
```
len(clean_text(html)) > 500
AND not is_error_or_cookiewall(html)
AND len(firecrawl_html) > len(baseline_html or "") * 1.1
```
- If `baseline_html` is `None` or empty, the third condition simplifies to `len(firecrawl_html) > 0`.
- If gate fails → returns `None` → orchestrator falls through to Playwright.

### playwright_provider.py

- Extracted from current `_render_spa` inner function.
- Identical behavior: cookie dismiss, XHR capture, JSON-LD harvest, scroll steps.
- Returns `str | None`.

---

## Orchestrator Flow — Phase 1 (FIRECRAWL_ENABLED=false, zero behavior change)

Phase 1 preserves the **exact current execution order** from `main.py:3433–3666`:
- aggressive mode: Playwright first → HTTP fallback
- balanced/light mode: HTTP first → Playwright if SPA markers or force_spa

```
check in-memory cache (content_cache)
    → if hit, return cached (html, used_spa)

# Preserve current mode logic exactly:
if mode == "aggressive" OR force_spa:
    html = playwright_provider(url)          # Playwright first (current behavior)
    if not html:
        html = http_provider(url)            # HTTP fallback
        used_spa = False
else:
    http_res = http_provider(url)
    baseline_html = http_res.text if 200 else ""
    if detect_spa_markers(baseline_html) OR force_spa OR is_spa_domain(url):
        html = playwright_provider(url) OR baseline_html
    else:
        html = baseline_html
        used_spa = False

if not html or len(html.strip()) < 100:
    raise HTTPException(400, "Website returned insufficient content")   # PRESERVED

store in in-memory cache
return (html, used_spa)
```

## Orchestrator Flow — Phase 2 (FIRECRAWL_ENABLED=true, new sequencing)

When Firecrawl is enabled, the orchestrator switches to the new provider order:

```
check in-memory cache (content_cache)
    → if hit, return cached (html, used_spa)

# New order: HTTP preflight → Firecrawl → Playwright
http_preflight(url)
    → baseline_html (str | ""), headers

check circuit breaker — if open, skip Firecrawl
check Redis cache — if hit, update in-memory cache, return (html, False)
call firecrawl_provider(url, baseline_html)
run quality gate
if passes → store in Redis + in-memory cache, return (html, False)

# Playwright fallback
if detect_spa_markers(baseline_html) OR force_spa OR mode == "aggressive":
    html = playwright_provider(url)
    if html → store, return (html, True)

# Last resort
if baseline_html and len(baseline_html.strip()) >= 100:
    store, return (baseline_html, False)

raise HTTPException(400, "Website returned insufficient content")
```

**HTTPException boundary**: preserved in both phases — the orchestrator raises `HTTPException(400)` on total failure, consistent with `main.py:3657`. This is NOT moved to callers.

**`used_spa=True`** only when Playwright was used — preserves existing semantics.

---

## Configuration (app/config.py additions)

```python
FIRECRAWL_API_KEY            = os.getenv("FIRECRAWL_API_KEY")
FIRECRAWL_ENABLED            = os.getenv("FIRECRAWL_ENABLED", "false").lower() == "true"
FIRECRAWL_TIMEOUT            = int(os.getenv("FIRECRAWL_TIMEOUT", "15"))
FIRECRAWL_MULTI_PAGE_ENABLED = os.getenv("FIRECRAWL_MULTI_PAGE_ENABLED", "false").lower() == "true"
```

Note: `CONTENT_PRIMARY_PROVIDER` was removed — the orchestrator flow is fixed (HTTP → Firecrawl → Playwright) and a runtime switch adds complexity without current value.

---

## Observability

Every fetch emits one structured INFO log line using the full URL (no redaction of paths; query parameters are omitted if they appear sensitive):

```
[content_fetch] provider=firecrawl url=https://example.com duration=2.3s \
    content_len=45231 fallback=false cache=miss
[content_fetch] provider=playwright url=https://example.com duration=8.1s \
    content_len=12400 fallback=true fallback_reason=firecrawl_quality_gate
[content_fetch] provider=http url=https://example.com duration=0.4s \
    content_len=8200 fallback=false
```

---

## Testing

New test directory: `tests/unit/content_fetch/`

| File | What it covers |
|------|---------------|
| `test_http_provider.py` | httpx mock, timeout, redirect, non-200 |
| `test_firecrawl_provider.py` | SDK mock, quality gate pass/fail, circuit breaker open/close/half-open, cache hit/miss, None baseline_html handling, missing API key validation |
| `test_playwright_provider.py` | async_playwright mock, XHR capture, cookie dismiss |
| `test_orchestrator.py` | full fallback chain, in-memory cache hit/miss/TTL, metrics log output, backward compat return type `(str, bool)`, `(None, False)` on total failure, no HTTPException raised |

All existing tests must continue to pass without modification.

---

## Rollout Phases (Railway)

| Phase | Env change | Effect |
|-------|-----------|--------|
| 1 — Refactor only | `FIRECRAWL_ENABLED=false` (default) | Zero behavior change, providers extracted, in-memory cache migrated |
| 2 — Firecrawl on | `FIRECRAWL_ENABLED=true`, `FIRECRAWL_API_KEY=<key>` | Firecrawl used, Playwright still fallback |
| 3 — Tune | Monitor logs 1 week; if fallback_rate < 10% | Consider reducing CONTENT_FETCH_MODE from "aggressive" |

---

## Dependencies

```
firecrawl-py==1.13.4    # pinned — active release cadence, pin to tested version
```

Redis is already available (`REDIS_URL` env exists).

---

## Files Changed

| File | Change |
|------|--------|
| `agents/content_fetch/__init__.py` | New — re-exports get_website_content |
| `agents/content_fetch/orchestrator.py` | New — core logic migrated from main.py:3433–3666, in-memory cache preserved |
| `agents/content_fetch/http_provider.py` | New — _fetch_http migrated |
| `agents/content_fetch/firecrawl_provider.py` | New — Firecrawl SDK + circuit breaker + Redis cache + startup validation |
| `agents/content_fetch/playwright_provider.py` | New — _render_spa migrated |
| `app/config.py` | Add 4 Firecrawl env vars |
| `main.py` | Replace lines 3433–3666 with thin import (re-export preserved for scout_agent) |
| `requirements.txt` | Add firecrawl-py==1.13.4 |
| `tests/unit/content_fetch/` | New — 4 test files |
| `CHANGELOG.md` | v3.2.0 entry |
