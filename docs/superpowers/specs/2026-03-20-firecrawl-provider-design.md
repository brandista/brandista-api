# Firecrawl Provider Integration — Design Spec

**Date**: 2026-03-20
**Status**: Approved
**Version**: 1.0

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

`get_website_content()` at line 3433 becomes a thin wrapper:

```python
from agents.content_fetch import get_website_content  # noqa: F401
```

The 230-line implementation moves into `orchestrator.py`. **Return type stays `Tuple[Optional[str], bool]`** — no callers change.

---

## Provider Details

### http_provider.py

- Extracted from current `_fetch_http` inner function.
- Returns `httpx.Response | None`.
- Used as cheap preflight for all fetches regardless of which provider wins.
- Supplies status, headers, redirect chain, and baseline HTML to the orchestrator.

### firecrawl_provider.py

```python
app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
result = app.scrape_url(url, formats=["html", "markdown"])
```

**Circuit breaker** (in-memory, per worker process):
- Opens after 3 consecutive failures.
- Half-open after 5 minutes: one probe request allowed.
- If probe succeeds → closed; if probe fails → back to open.

**Redis cache**:
- Key: `firecrawl:{md5(url)}`
- TTL: 3600s (1 hour)
- Skips SDK call on cache hit, returns cached html + markdown.

**Quality gate** (result accepted only if all pass):
```
len(clean_text(html)) > 500
AND not is_error_or_cookiewall(html)
AND len(firecrawl_html) > len(http_html) * 1.1
```
If gate fails → returns `None` → orchestrator falls through to Playwright.

### playwright_provider.py

- Extracted from current `_render_spa` inner function.
- Identical behavior: cookie dismiss, XHR capture, JSON-LD harvest, scroll steps.
- Returns `str | None`.

---

## Orchestrator Flow

```
http_preflight(url)
    → baseline html + headers (always runs)

if FIRECRAWL_ENABLED:
    check circuit breaker
    check Redis cache
    if cache hit → return cached, used_spa=False
    call firecrawl_provider(url)
    run quality gate
    if passes → cache in Redis, return html, used_spa=False

# Playwright fallback (existing SPA logic preserved)
if detect_spa_markers(baseline_html) OR force_spa OR CONTENT_FETCH_MODE == "aggressive":
    call playwright_provider(url)
    if result → return result, used_spa=True

# Last resort: return baseline HTTP html
return baseline_html, used_spa=False
```

**Result**: `used_spa=True` only when Playwright was used — preserves existing semantics.

---

## Configuration (app/config.py additions)

```python
FIRECRAWL_API_KEY              = os.getenv("FIRECRAWL_API_KEY")
FIRECRAWL_ENABLED              = os.getenv("FIRECRAWL_ENABLED", "false").lower() == "true"
FIRECRAWL_TIMEOUT              = int(os.getenv("FIRECRAWL_TIMEOUT", "15"))
FIRECRAWL_MULTI_PAGE_ENABLED   = os.getenv("FIRECRAWL_MULTI_PAGE_ENABLED", "false").lower() == "true"
CONTENT_PRIMARY_PROVIDER       = os.getenv("CONTENT_PRIMARY_PROVIDER", "http")
```

---

## Observability

Every fetch emits one structured INFO log line:

```
[content_fetch] provider=firecrawl url=example.com duration=2.3s \
    content_len=45231 fallback=false cache=miss
[content_fetch] provider=playwright url=example.com duration=8.1s \
    content_len=12400 fallback=true fallback_reason=firecrawl_quality_gate
[content_fetch] provider=http url=example.com duration=0.4s \
    content_len=8200 fallback=false
```

---

## Testing

New test directory: `tests/unit/content_fetch/`

| File | What it covers |
|------|---------------|
| `test_http_provider.py` | httpx mock, timeout, redirect, non-200 |
| `test_firecrawl_provider.py` | SDK mock, quality gate pass/fail, circuit breaker open/close, cache hit/miss |
| `test_playwright_provider.py` | async_playwright mock, XHR capture, cookie dismiss |
| `test_orchestrator.py` | full fallback chain, metrics log output, backward compat return type |

All existing tests must continue to pass without modification.

---

## Rollout Phases (Railway)

| Phase | Env change | Effect |
|-------|-----------|--------|
| 1 — Refactor only | `FIRECRAWL_ENABLED=false` (default) | Zero behavior change, providers extracted |
| 2 — Firecrawl on | `FIRECRAWL_ENABLED=true` | Firecrawl used, Playwright still fallback |
| 3 — Tune | Monitor logs 1 week; if fallback_rate < 10% | Consider reducing CONTENT_FETCH_MODE from "aggressive" |

---

## Dependencies

```
firecrawl-py    # add to requirements.txt
```

Redis is already available (`REDIS_URL` env exists).

---

## Files Changed

| File | Change |
|------|--------|
| `agents/content_fetch/__init__.py` | New — re-exports get_website_content |
| `agents/content_fetch/orchestrator.py` | New — core logic migrated from main.py:3433–3666 |
| `agents/content_fetch/http_provider.py` | New — _fetch_http migrated |
| `agents/content_fetch/firecrawl_provider.py` | New — Firecrawl SDK + circuit breaker + cache |
| `agents/content_fetch/playwright_provider.py` | New — _render_spa migrated |
| `app/config.py` | Add 5 Firecrawl env vars |
| `main.py` | Replace lines 3433–3666 with thin import wrapper |
| `requirements.txt` | Add firecrawl-py |
| `tests/unit/content_fetch/` | New — 4 test files |
| `CHANGELOG.md` | v3.2.0 entry |
