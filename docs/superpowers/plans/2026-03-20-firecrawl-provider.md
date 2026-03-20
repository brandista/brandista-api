# Firecrawl Provider Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract `get_website_content()` from `main.py` into a testable `agents/content_fetch/` provider abstraction and add Firecrawl as a managed provider with circuit breaker, Redis cache, and quality gates.

**Architecture:** Three independent providers (`http_provider`, `firecrawl_provider`, `playwright_provider`) each returning a typed result; an `orchestrator` sequences them with fallback logic and manages the in-memory cache. `main.py` becomes a thin re-export. Return type `Tuple[Optional[str], bool]` is unchanged.

**Tech Stack:** Python 3.11, FastAPI, httpx, firecrawl-py SDK, redis, playwright, pytest-asyncio

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `agents/content_fetch/__init__.py` | Create | Re-exports `get_website_content` |
| `agents/content_fetch/orchestrator.py` | Create | Cache, provider sequencing, fallback, metrics log |
| `agents/content_fetch/http_provider.py` | Create | httpx preflight — returns `httpx.Response \| None` |
| `agents/content_fetch/firecrawl_provider.py` | Create | firecrawl-py SDK, circuit breaker, Redis cache, quality gate |
| `agents/content_fetch/playwright_provider.py` | Create | Playwright render — returns `str \| None` |
| `app/config.py` | Modify | Add 4 Firecrawl env vars |
| `requirements.txt` | Modify | Add `firecrawl-py` |
| `main.py` | Modify | Replace lines 3357–3666 with imports |
| `tests/unit/content_fetch/__init__.py` | Create | Empty |
| `tests/unit/content_fetch/test_http_provider.py` | Create | httpx mock tests |
| `tests/unit/content_fetch/test_firecrawl_provider.py` | Create | SDK mock, circuit breaker, cache, quality gate |
| `tests/unit/content_fetch/test_playwright_provider.py` | Create | playwright mock tests |
| `tests/unit/content_fetch/test_orchestrator.py` | Create | Full chain, cache, backward compat |
| `CHANGELOG.md` | Modify | v3.2.0 entry |

---

## Task 1: Config and dependencies

**Files:**
- Modify: `app/config.py` (after line 107, in SPA & CONTENT FETCH section)
- Modify: `requirements.txt` (after line 69, in BROWSER AUTOMATION section)

- [ ] **Step 1: Add Firecrawl env vars to app/config.py**

In `app/config.py`, after the existing `COOKIE_SELECTORS` block (around line 111), add:

```python
# ============================================================================
# FIRECRAWL SETTINGS
# ============================================================================

FIRECRAWL_API_KEY            = os.getenv("FIRECRAWL_API_KEY")
FIRECRAWL_ENABLED            = os.getenv("FIRECRAWL_ENABLED", "false").lower() == "true"
FIRECRAWL_TIMEOUT            = int(os.getenv("FIRECRAWL_TIMEOUT", "15"))
FIRECRAWL_MULTI_PAGE_ENABLED = os.getenv("FIRECRAWL_MULTI_PAGE_ENABLED", "false").lower() == "true"
```

- [ ] **Step 2: Add firecrawl-py to requirements.txt**

After the `playwright==1.45.0` line, add:

```
firecrawl-py==1.13.4
```

- [ ] **Step 3: Verify pip install works**

```bash
cd /Users/tuukka/Downloads/Projects/Brandista/koodi/brandista-api-git
pip install firecrawl-py==1.13.4
```

Expected: installs without errors. If 1.13.4 is not found, run `pip index versions firecrawl-py` and pin the latest 1.x release instead — update requirements.txt and the spec accordingly.

- [ ] **Step 4: Commit**

```bash
git add app/config.py requirements.txt
git commit -m "feat(content_fetch): add Firecrawl config vars and dependency"
```

---

## Task 2: http_provider

**Files:**
- Create: `agents/content_fetch/http_provider.py`
- Create: `tests/unit/content_fetch/__init__.py`
- Create: `tests/unit/content_fetch/test_http_provider.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/content_fetch/__init__.py` (empty).

Create `tests/unit/content_fetch/test_http_provider.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


@pytest.mark.asyncio
async def test_fetch_http_success_returns_response():
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = "<html><body>Hello</body></html>"

    with patch("agents.content_fetch.http_provider.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        from agents.content_fetch.http_provider import fetch_http
        result = await fetch_http("https://example.com")

    assert result is not None
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_fetch_http_non_200_returns_response():
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404

    with patch("agents.content_fetch.http_provider.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        from agents.content_fetch.http_provider import fetch_http
        result = await fetch_http("https://example.com")

    assert result is not None
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_fetch_http_exception_returns_none():
    with patch("agents.content_fetch.http_provider.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client_cls.return_value = mock_client

        from agents.content_fetch.http_provider import fetch_http
        result = await fetch_http("https://example.com")

    assert result is None


@pytest.mark.asyncio
async def test_fetch_http_non_ok_status_500_returns_none():
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500

    with patch("agents.content_fetch.http_provider.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        from agents.content_fetch.http_provider import fetch_http
        result = await fetch_http("https://example.com")

    assert result is None
```

- [ ] **Step 2: Run tests — expect ImportError/ModuleNotFoundError**

```bash
python3 -m pytest tests/unit/content_fetch/test_http_provider.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agents.content_fetch.http_provider'`

- [ ] **Step 3: Create `agents/content_fetch/http_provider.py`**

```python
"""HTTP preflight provider — cheap first fetch for technical signals and baseline HTML."""

import logging
from typing import Optional

import httpx

from app.config import USER_AGENT, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


async def fetch_http(url: str, timeout: int = REQUEST_TIMEOUT) -> Optional[httpx.Response]:
    """
    Fetch a URL with httpx. Returns the response object (including non-200
    status codes for 301/302/404) or None on network errors and 5xx responses.
    """
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=True,
            limits=httpx.Limits(max_keepalive_connections=8, max_connections=16),
        ) as client:
            res = await client.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            )
            if res.status_code == 200 or res.status_code in (301, 302, 303, 307, 308, 404):
                return res
            logger.warning("[http] non-200 status %s for %s", res.status_code, url)
            return None
    except Exception as e:
        logger.warning("[http] fetch error for %s: %s", url, e)
        return None
```

Also create `agents/content_fetch/__init__.py` (empty for now, will be filled in Task 6):

```python
# agents/content_fetch/__init__.py
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python3 -m pytest tests/unit/content_fetch/test_http_provider.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/content_fetch/__init__.py agents/content_fetch/http_provider.py \
    tests/unit/content_fetch/__init__.py tests/unit/content_fetch/test_http_provider.py
git commit -m "feat(content_fetch): add http_provider with tests"
```

---

## Task 3: playwright_provider

**Files:**
- Create: `agents/content_fetch/playwright_provider.py`
- Create: `tests/unit/content_fetch/test_playwright_provider.py`

The implementation is a direct extraction of `_render_spa()` from `main.py:3479–3635`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/content_fetch/test_playwright_provider.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_render_spa_returns_html_on_success():
    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html><body>Rendered</body></html>")
    mock_page.evaluate = AsyncMock(return_value=[])
    mock_page.route = AsyncMock()
    mock_page.on = MagicMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_playwright = AsyncMock()
    mock_playwright.chromium = mock_chromium
    mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_playwright.__aexit__ = AsyncMock(return_value=False)

    with patch("agents.content_fetch.playwright_provider.PLAYWRIGHT_AVAILABLE", True), \
         patch("agents.content_fetch.playwright_provider.async_playwright", return_value=mock_playwright):
        from agents.content_fetch.playwright_provider import render_spa
        result = await render_spa("https://example.com")

    assert result is not None
    assert "Rendered" in result


@pytest.mark.asyncio
async def test_render_spa_returns_none_when_playwright_unavailable():
    with patch("agents.content_fetch.playwright_provider.PLAYWRIGHT_AVAILABLE", False):
        from agents.content_fetch.playwright_provider import render_spa
        result = await render_spa("https://example.com")

    assert result is None


@pytest.mark.asyncio
async def test_render_spa_returns_none_on_exception():
    with patch("agents.content_fetch.playwright_provider.PLAYWRIGHT_AVAILABLE", True), \
         patch("agents.content_fetch.playwright_provider.async_playwright",
               side_effect=Exception("browser crashed")):
        from agents.content_fetch.playwright_provider import render_spa
        result = await render_spa("https://example.com")

    assert result is None
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python3 -m pytest tests/unit/content_fetch/test_playwright_provider.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `agents/content_fetch/playwright_provider.py`**

Copy the `_render_spa` logic from `main.py:3479–3635` into a standalone async function. Imports come from `app.config` and existing module-level variables in `main.py` (which will remain there during Phase 1).

```python
"""Playwright SPA rendering provider — last-resort fallback for JS-heavy sites."""

import logging
from typing import Optional

from app.config import (
    USER_AGENT,
    SPA_MAX_SCROLL_STEPS,
    SPA_SCROLL_PAUSE_MS,
    SPA_EXTRA_WAIT_MS,
    SPA_WAIT_FOR_SELECTOR,
    PLAYWRIGHT_TIMEOUT,
    CAPTURE_XHR,
    MAX_XHR_BYTES,
    BLOCK_HEAVY_RESOURCES,
    COOKIE_AUTO_DISMISS,
    COOKIE_SELECTORS,
)

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    async_playwright = None  # type: ignore


async def render_spa(url: str, timeout: int = PLAYWRIGHT_TIMEOUT) -> Optional[str]:
    """
    Render a URL using Playwright (headless Chromium). Returns rendered HTML
    (including JSON-LD and captured XHR blobs) or None on any failure.
    """
    if not PLAYWRIGHT_AVAILABLE or async_playwright is None:
        logger.warning("[playwright] not available; skipping SPA render for %s", url)
        return None

    try:
        import json as _json

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1440, "height": 900},
                locale="en-US",
            )
            page = await context.new_page()
            xhr_store = []

            async def route_handler(route):
                try:
                    req = route.request
                    if BLOCK_HEAVY_RESOURCES and req.resource_type in {"image", "media", "font"}:
                        await route.abort()
                        return
                    await route.continue_()
                except Exception:
                    try:
                        await route.continue_()
                    except Exception:
                        pass

            async def response_listener(response):
                try:
                    req = response.request
                    ct = (response.headers.get("content-type") or "").lower()
                    if CAPTURE_XHR and (
                        req.resource_type in {"xhr", "fetch"}
                        or "application/json" in ct
                    ):
                        body = await response.body()
                        if body and len(body) <= MAX_XHR_BYTES:
                            try:
                                text = body.decode("utf-8", errors="ignore")
                            except Exception:
                                text = ""
                            if text.strip():
                                xhr_store.append({
                                    "url": req.url,
                                    "status": response.status,
                                    "content_type": ct,
                                    "length": len(body),
                                    "body": text,
                                })
                except Exception:
                    pass

            await page.route("**/*", route_handler)
            page.on("response", response_listener)

            # Cookie banner auto-dismiss (best-effort)
            if COOKIE_AUTO_DISMISS:
                try:
                    for selector in COOKIE_SELECTORS.split(","):
                        try:
                            await page.click(selector.strip(), timeout=1500)
                            break
                        except Exception:
                            pass
                except Exception:
                    pass

            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            try:
                await page.wait_for_load_state("networkidle", timeout=SPA_EXTRA_WAIT_MS)
            except Exception:
                pass

            # Auto-scroll to trigger lazy loading
            for _ in range(SPA_MAX_SCROLL_STEPS):
                try:
                    await page.evaluate("window.scrollBy(0, window.innerHeight)")
                    await page.wait_for_timeout(SPA_SCROLL_PAUSE_MS)
                except Exception:
                    break

            if SPA_WAIT_FOR_SELECTOR:
                try:
                    await page.wait_for_selector(SPA_WAIT_FOR_SELECTOR, timeout=3000)
                except Exception:
                    pass

            # Harvest JSON-LD
            try:
                jsonld_list = await page.evaluate("""() => {
                    const nodes = Array.from(
                        document.querySelectorAll('script[type="application/ld+json"]')
                    );
                    return nodes.map(n => n.textContent || '').filter(Boolean);
                }""")
                jsonld_blob = (
                    "\n<!--JSONLD-->" + "\n".join(jsonld_list) + "\n<!--/JSONLD-->"
                    if jsonld_list else ""
                )
            except Exception:
                jsonld_blob = ""

            # XHR blob
            xhr_blob = (
                "\n<!--XHR-->" + _json.dumps(xhr_store) + "\n<!--/XHR-->"
                if xhr_store else ""
            )

            html = await page.content()
            await context.close()
            await browser.close()

            return html + jsonld_blob + xhr_blob

    except Exception as e:
        logger.warning("[playwright] render failed for %s: %s", url, e)
        return None
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python3 -m pytest tests/unit/content_fetch/test_playwright_provider.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Run full test suite to ensure nothing broken**

```bash
python3 -m pytest tests/ -x -q
```

Expected: all existing tests PASS

- [ ] **Step 6: Commit**

```bash
git add agents/content_fetch/playwright_provider.py \
    tests/unit/content_fetch/test_playwright_provider.py
git commit -m "feat(content_fetch): add playwright_provider with tests"
```

---

## Task 4: firecrawl_provider

**Files:**
- Create: `agents/content_fetch/firecrawl_provider.py`
- Create: `tests/unit/content_fetch/test_firecrawl_provider.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/content_fetch/test_firecrawl_provider.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


# ── Quality gate ──────────────────────────────────────────────────────────────

def test_quality_gate_passes_good_content():
    from agents.content_fetch.firecrawl_provider import _quality_gate
    firecrawl_html = "<html>" + "word " * 200 + "</html>"
    baseline_html = "<html>short</html>"
    assert _quality_gate(firecrawl_html, baseline_html) is True


def test_quality_gate_fails_empty_html():
    from agents.content_fetch.firecrawl_provider import _quality_gate
    assert _quality_gate("", "<html>baseline</html>") is False


def test_quality_gate_fails_insufficient_text():
    from agents.content_fetch.firecrawl_provider import _quality_gate
    html = "<html><body>Too short</body></html>"
    assert _quality_gate(html, "<html>baseline</html>") is False


def test_quality_gate_fails_not_better_than_baseline():
    from agents.content_fetch.firecrawl_provider import _quality_gate
    long_baseline = "<html>" + "word " * 300 + "</html>"
    short_firecrawl = "<html>" + "word " * 50 + "</html>"
    assert _quality_gate(short_firecrawl, long_baseline) is False


def test_quality_gate_baseline_none_treated_as_empty():
    from agents.content_fetch.firecrawl_provider import _quality_gate
    firecrawl_html = "<html>" + "word " * 200 + "</html>"
    # baseline=None should not raise TypeError
    assert _quality_gate(firecrawl_html, None) is True


def test_quality_gate_detects_cookie_wall():
    from agents.content_fetch.firecrawl_provider import _quality_gate
    cookie_wall = "<html><body>" + "Please accept cookies " * 30 + "</body></html>"
    # Less than 500 meaningful words → gate fails
    assert _quality_gate(cookie_wall, "") is False


# ── Circuit breaker ───────────────────────────────────────────────────────────

def test_circuit_breaker_opens_after_three_failures():
    from agents.content_fetch.firecrawl_provider import CircuitBreaker
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=300)
    cb.record_failure()
    cb.record_failure()
    assert cb.is_open() is False
    cb.record_failure()
    assert cb.is_open() is True


def test_circuit_breaker_closed_initially():
    from agents.content_fetch.firecrawl_provider import CircuitBreaker
    cb = CircuitBreaker()
    assert cb.is_open() is False


def test_circuit_breaker_half_open_after_timeout():
    from agents.content_fetch.firecrawl_provider import CircuitBreaker
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
    cb.record_failure()
    assert cb.is_open() is True
    # With recovery_timeout=0, should allow probe
    assert cb.allow_probe() is True


def test_circuit_breaker_resets_on_success():
    from agents.content_fetch.firecrawl_provider import CircuitBreaker
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0)
    cb.record_failure()
    assert cb.is_open() is True
    cb.record_success()
    assert cb.is_open() is False


# ── scrape() integration (SDK mocked) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_scrape_returns_html_on_success():
    rich_html = "<html><body>" + " ".join(["word"] * 300) + "</body></html>"

    mock_sdk = MagicMock()
    mock_sdk.scrape_url = MagicMock(return_value={"html": rich_html, "markdown": "content"})

    with patch("agents.content_fetch.firecrawl_provider.FIRECRAWL_ENABLED", True), \
         patch("agents.content_fetch.firecrawl_provider.FIRECRAWL_API_KEY", "test-key"), \
         patch("agents.content_fetch.firecrawl_provider.FirecrawlApp", return_value=mock_sdk), \
         patch("agents.content_fetch.firecrawl_provider._redis_get", return_value=None), \
         patch("agents.content_fetch.firecrawl_provider._redis_set", return_value=None):
        from agents.content_fetch import firecrawl_provider
        firecrawl_provider._circuit_breaker.record_success()  # ensure closed
        result = await firecrawl_provider.scrape("https://example.com", baseline_html="<html>short</html>")

    assert result is not None
    assert "word" in result


@pytest.mark.asyncio
async def test_scrape_returns_none_when_disabled():
    with patch("agents.content_fetch.firecrawl_provider.FIRECRAWL_ENABLED", False):
        from agents.content_fetch.firecrawl_provider import scrape
        result = await scrape("https://example.com", baseline_html="")
    assert result is None


@pytest.mark.asyncio
async def test_scrape_returns_none_when_circuit_open():
    with patch("agents.content_fetch.firecrawl_provider.FIRECRAWL_ENABLED", True), \
         patch("agents.content_fetch.firecrawl_provider.FIRECRAWL_API_KEY", "test-key"):
        from agents.content_fetch import firecrawl_provider
        # Force circuit open
        firecrawl_provider._circuit_breaker._failures = 99
        firecrawl_provider._circuit_breaker._opened_at = datetime.now()
        result = await firecrawl_provider.scrape("https://example.com", baseline_html="")
    assert result is None


@pytest.mark.asyncio
async def test_scrape_returns_cached_result():
    cached_html = "<html><body>cached content</body></html>"
    with patch("agents.content_fetch.firecrawl_provider.FIRECRAWL_ENABLED", True), \
         patch("agents.content_fetch.firecrawl_provider.FIRECRAWL_API_KEY", "test-key"), \
         patch("agents.content_fetch.firecrawl_provider._redis_get", return_value=cached_html):
        from agents.content_fetch import firecrawl_provider
        firecrawl_provider._circuit_breaker.record_success()
        result = await firecrawl_provider.scrape("https://example.com", baseline_html="")
    assert result == cached_html
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python3 -m pytest tests/unit/content_fetch/test_firecrawl_provider.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `agents/content_fetch/firecrawl_provider.py`**

```python
"""Firecrawl provider — SDK-based content fetch with circuit breaker and Redis cache."""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from bs4 import BeautifulSoup

from app.config import (
    FIRECRAWL_API_KEY,
    FIRECRAWL_ENABLED,
    FIRECRAWL_TIMEOUT,
    REDIS_URL,
)

logger = logging.getLogger(__name__)

# Startup validation — fail fast if Firecrawl is enabled but key is missing
if FIRECRAWL_ENABLED and not FIRECRAWL_API_KEY:
    raise ValueError(
        "FIRECRAWL_ENABLED=true but FIRECRAWL_API_KEY is not set. "
        "Set the env var or disable Firecrawl with FIRECRAWL_ENABLED=false."
    )

try:
    from firecrawl import FirecrawlApp
    _FIRECRAWL_AVAILABLE = True
except ImportError:
    FirecrawlApp = None  # type: ignore
    _FIRECRAWL_AVAILABLE = False
    if FIRECRAWL_ENABLED:
        logger.warning("[firecrawl] firecrawl-py not installed but FIRECRAWL_ENABLED=true")

_REDIS_CLIENT = None  # lazy init


def _get_redis():
    global _REDIS_CLIENT
    if _REDIS_CLIENT is None and REDIS_URL:
        try:
            import redis as redis_lib
            _REDIS_CLIENT = redis_lib.from_url(REDIS_URL, decode_responses=True)
        except Exception as e:
            logger.warning("[firecrawl] Redis init failed: %s", e)
    return _REDIS_CLIENT


def _cache_key(url: str) -> str:
    return f"firecrawl:{hashlib.md5(url.encode()).hexdigest()}"


def _redis_get(url: str) -> Optional[str]:
    try:
        r = _get_redis()
        if r:
            return r.get(_cache_key(url))
    except Exception as e:
        logger.debug("[firecrawl] Redis GET failed: %s", e)
    return None


def _redis_set(url: str, html: str, ttl: int = 3600) -> None:
    try:
        r = _get_redis()
        if r:
            r.setex(_cache_key(url), ttl, html)
    except Exception as e:
        logger.debug("[firecrawl] Redis SET failed: %s", e)


def _clean_text(html: str) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(separator=" ").strip()
    except Exception:
        return html


def _is_error_or_cookiewall(html: str) -> bool:
    lower = html.lower()
    signals = [
        "access denied", "403 forbidden", "404 not found",
        "enable javascript", "please enable cookies",
        "you have been blocked", "captcha", "cloudflare ray id",
    ]
    return any(s in lower for s in signals)


def _quality_gate(firecrawl_html: str, baseline_html: Optional[str]) -> bool:
    """Return True if Firecrawl result is good enough to use."""
    if not firecrawl_html:
        return False
    text = _clean_text(firecrawl_html)
    if len(text.split()) < 100:
        return False
    if _is_error_or_cookiewall(firecrawl_html):
        return False
    baseline_len = len(baseline_html or "")
    if len(firecrawl_html) <= baseline_len * 1.1:
        return False
    return True


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 300):
        self._threshold = failure_threshold
        self._recovery = recovery_timeout
        self._failures = 0
        self._opened_at: Optional[datetime] = None

    def is_open(self) -> bool:
        if self._failures < self._threshold:
            return False
        if self._opened_at is None:
            return True
        # Check if recovery window has passed
        if (datetime.now() - self._opened_at).total_seconds() > self._recovery:
            return False  # half-open: allow probe
        return True

    def allow_probe(self) -> bool:
        """True when breaker is in half-open state (past recovery timeout)."""
        if self._failures < self._threshold:
            return False
        if self._opened_at is None:
            return False
        return (datetime.now() - self._opened_at).total_seconds() > self._recovery

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold and self._opened_at is None:
            self._opened_at = datetime.now()
            logger.warning("[firecrawl] circuit breaker OPEN after %d failures", self._failures)

    def record_success(self) -> None:
        if self._failures > 0:
            logger.info("[firecrawl] circuit breaker CLOSED after success")
        self._failures = 0
        self._opened_at = None


# Module-level singleton circuit breaker
_circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=300)


async def scrape(url: str, baseline_html: Optional[str] = None) -> Optional[str]:
    """
    Fetch URL via Firecrawl SDK. Returns HTML string or None if disabled,
    circuit open, quality gate fails, or any error occurs.
    """
    if not FIRECRAWL_ENABLED or not _FIRECRAWL_AVAILABLE:
        return None

    if _circuit_breaker.is_open() and not _circuit_breaker.allow_probe():
        logger.info("[firecrawl] circuit OPEN — skipping %s", url)
        return None

    # Redis cache check
    cached = _redis_get(url)
    if cached:
        logger.info("[firecrawl] cache HIT for %s", url)
        return cached

    try:
        loop = asyncio.get_event_loop()
        app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

        result = await loop.run_in_executor(
            None,
            lambda: app.scrape_url(
                url,
                formats=["html", "markdown"],
                timeout=FIRECRAWL_TIMEOUT,
            ),
        )

        html = result.get("html", "") if isinstance(result, dict) else ""

        if not _quality_gate(html, baseline_html):
            logger.info("[firecrawl] quality gate FAILED for %s", url)
            _circuit_breaker.record_failure()
            return None

        _circuit_breaker.record_success()
        _redis_set(url, html)
        return html

    except Exception as e:
        logger.warning("[firecrawl] scrape failed for %s: %s", url, e)
        _circuit_breaker.record_failure()
        return None
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python3 -m pytest tests/unit/content_fetch/test_firecrawl_provider.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/content_fetch/firecrawl_provider.py \
    tests/unit/content_fetch/test_firecrawl_provider.py
git commit -m "feat(content_fetch): add firecrawl_provider — circuit breaker, Redis cache, quality gate"
```

---

## Task 5: orchestrator

**Files:**
- Create: `agents/content_fetch/orchestrator.py`
- Create: `tests/unit/content_fetch/test_orchestrator.py`

This is the core migration: `get_content_cache_key`, `is_content_cache_valid`, `content_cache`, `detect_spa_markers`, `is_spa_domain`, `validate_rendered_content`, and the full `get_website_content` logic move here.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/content_fetch/test_orchestrator.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional, Tuple
import httpx


def _make_http_response(text: str = "<html>baseline</html>", status: int = 200):
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status
    mock.text = text
    return mock


# ── Backward compatibility ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_tuple_str_bool():
    rich_html = "<html><body>" + "word " * 100 + "</body></html>"
    with patch("agents.content_fetch.orchestrator.fetch_http",
               AsyncMock(return_value=_make_http_response(rich_html))), \
         patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", False), \
         patch("agents.content_fetch.orchestrator.CONTENT_FETCH_MODE", "balanced"), \
         patch("agents.content_fetch.orchestrator._content_cache", {}):
        from agents.content_fetch.orchestrator import get_website_content
        result = await get_website_content("https://example.com")
    assert isinstance(result, tuple)
    assert len(result) == 2
    html, used_spa = result
    assert isinstance(html, str)
    assert isinstance(used_spa, bool)


@pytest.mark.asyncio
async def test_used_spa_false_when_http_wins():
    rich_html = "<html><body>" + "word " * 100 + "</body></html>"
    with patch("agents.content_fetch.orchestrator.fetch_http",
               AsyncMock(return_value=_make_http_response(rich_html))), \
         patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", False), \
         patch("agents.content_fetch.orchestrator.CONTENT_FETCH_MODE", "balanced"), \
         patch("agents.content_fetch.orchestrator._content_cache", {}):
        from agents.content_fetch.orchestrator import get_website_content
        _, used_spa = await get_website_content("https://example.com")
    assert used_spa is False


@pytest.mark.asyncio
async def test_used_spa_true_when_playwright_wins():
    sparse_html = "<html><body>Loading...</body></html>"
    playwright_html = "<html><body>" + "word " * 100 + "</body></html>"
    with patch("agents.content_fetch.orchestrator.fetch_http",
               AsyncMock(return_value=_make_http_response(sparse_html))), \
         patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", False), \
         patch("agents.content_fetch.orchestrator.CONTENT_FETCH_MODE", "aggressive"), \
         patch("agents.content_fetch.orchestrator.render_spa",
               AsyncMock(return_value=playwright_html)), \
         patch("agents.content_fetch.orchestrator._content_cache", {}):
        from agents.content_fetch.orchestrator import get_website_content
        _, used_spa = await get_website_content("https://example.com")
    assert used_spa is True


# ── In-memory cache ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cache_hit_returns_without_fetch():
    from datetime import datetime
    cached_entry = {
        "content": "<html>cached</html>",
        "used_spa": False,
        "timestamp": datetime.now(),
    }
    fake_cache = {"content_" + __import__("hashlib").md5(b"https://example.com").hexdigest(): cached_entry}

    with patch("agents.content_fetch.orchestrator._content_cache", fake_cache), \
         patch("agents.content_fetch.orchestrator.fetch_http") as mock_fetch:
        from agents.content_fetch.orchestrator import get_website_content
        html, used_spa = await get_website_content("https://example.com")

    mock_fetch.assert_not_called()
    assert html == "<html>cached</html>"
    assert used_spa is False


# ── Firecrawl path ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_firecrawl_result_wins_over_http():
    baseline = "<html><body>short</body></html>"
    firecrawl_html = "<html><body>" + "word " * 200 + "</body></html>"

    with patch("agents.content_fetch.orchestrator.fetch_http",
               AsyncMock(return_value=_make_http_response(baseline))), \
         patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", True), \
         patch("agents.content_fetch.orchestrator.scrape",
               AsyncMock(return_value=firecrawl_html)), \
         patch("agents.content_fetch.orchestrator._content_cache", {}):
        from agents.content_fetch.orchestrator import get_website_content
        html, used_spa = await get_website_content("https://example.com")

    assert html == firecrawl_html
    assert used_spa is False


# ── Total failure returns (None, False) ────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_none_when_all_providers_fail():
    with patch("agents.content_fetch.orchestrator.fetch_http",
               AsyncMock(return_value=None)), \
         patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", False), \
         patch("agents.content_fetch.orchestrator.CONTENT_FETCH_MODE", "balanced"), \
         patch("agents.content_fetch.orchestrator.render_spa",
               AsyncMock(return_value=None)), \
         patch("agents.content_fetch.orchestrator._content_cache", {}):
        from agents.content_fetch.orchestrator import get_website_content
        result = await get_website_content("https://example.com")
    assert result == (None, False)


@pytest.mark.asyncio
async def test_does_not_raise_http_exception():
    """Orchestrator must not raise HTTPException — that is the caller's responsibility."""
    with patch("agents.content_fetch.orchestrator.fetch_http",
               AsyncMock(return_value=None)), \
         patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", False), \
         patch("agents.content_fetch.orchestrator.render_spa",
               AsyncMock(return_value=None)), \
         patch("agents.content_fetch.orchestrator._content_cache", {}):
        from agents.content_fetch.orchestrator import get_website_content
        # Should not raise
        result = await get_website_content("https://example.com")
    assert result[0] is None
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
python3 -m pytest tests/unit/content_fetch/test_orchestrator.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create `agents/content_fetch/orchestrator.py`**

```python
"""
Content fetch orchestrator — sequences providers, manages in-memory cache.
Public API: get_website_content(url, force_spa, timeout, mode) -> (html, used_spa)
"""

import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from app.config import (
    CONTENT_FETCH_MODE,
    FIRECRAWL_ENABLED,
    REQUEST_TIMEOUT,
    SPA_CACHE_TTL,
)
from agents.content_fetch.http_provider import fetch_http
from agents.content_fetch.playwright_provider import render_spa

logger = logging.getLogger(__name__)

# ── In-memory content cache (migrated from main.py:372) ──────────────────────
_content_cache: Dict[str, Dict[str, Any]] = {}


def _cache_key(url: str) -> str:
    return f"content_{hashlib.md5(url.encode()).hexdigest()}"


def _cache_valid(timestamp: datetime) -> bool:
    return (datetime.now() - timestamp).total_seconds() < SPA_CACHE_TTL


def detect_spa_markers(html: str) -> bool:
    if not html or len(html.strip()) < 100:
        return False
    html_lower = html.lower()
    strong_markers = [
        'id="root"', 'id="app"', 'id="__next"', 'id="nuxt"',
        "data-reactroot", "data-react-helmet", "ng-version=",
        '"__webpack_require__"', '"webpackChunkName"',
        "window.__initial_state__", "window.__preloaded_state__",
    ]
    framework_markers = ["react", "vue.js", "angular", "svelte", "next.js",
                         "nuxt", "gatsby", "vite", "webpack", "parcel"]
    build_markers = ["built with vite", "created-by-webpack", "generated-by",
                     "build-time:", "chunk-", "runtime-", "vendor-"]
    strong_count = sum(1 for m in strong_markers if m in html_lower)
    framework_count = sum(1 for m in framework_markers if m in html_lower)
    build_count = sum(1 for m in build_markers if m in html_lower)
    return strong_count >= 1 or (framework_count >= 2 and build_count >= 1)


def is_spa_domain(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).hostname or ""
    except Exception:
        domain = url
    spa_hints = ["brandista.eu", "www.brandista.eu", "app.", "dashboard.", "admin.", "portal."]
    return any(hint in domain for hint in spa_hints)


async def get_website_content(
    url: str,
    force_spa: bool = False,
    timeout: int = REQUEST_TIMEOUT,
    mode: str = CONTENT_FETCH_MODE,
) -> Tuple[Optional[str], bool]:
    """
    Unified content fetch. Returns (html, used_spa).
    used_spa=True only when Playwright was used.
    Returns (None, False) if all providers fail — callers handle HTTPException.
    """
    key = _cache_key(url)
    cached = _content_cache.get(key)
    if cached and _cache_valid(cached["timestamp"]):
        logger.info("[content_fetch] cache HIT for %s", url)
        return cached["content"], cached["used_spa"]

    start = time.monotonic()
    used_spa = False
    html: Optional[str] = None

    # ── 1. HTTP preflight ────────────────────────────────────────────────────
    http_res = await fetch_http(url, timeout=timeout)
    baseline_html: str = ""
    if http_res and http_res.status_code == 200 and http_res.text:
        baseline_html = http_res.text

    # ── 2. Firecrawl (if enabled) ────────────────────────────────────────────
    if FIRECRAWL_ENABLED:
        try:
            from agents.content_fetch.firecrawl_provider import scrape
            result = await scrape(url, baseline_html=baseline_html or None)
            if result:
                duration = time.monotonic() - start
                logger.info(
                    "[content_fetch] provider=firecrawl url=%s duration=%.1fs content_len=%d fallback=false",
                    url, duration, len(result),
                )
                html = result
                _store_cache(key, html, False)
                return html, False
        except Exception as e:
            logger.warning("[content_fetch] Firecrawl error for %s: %s", url, e)

    # ── 3. Playwright fallback ───────────────────────────────────────────────
    needs_playwright = force_spa or mode == "aggressive" or detect_spa_markers(baseline_html) or is_spa_domain(url)
    if needs_playwright:
        pw_result = await render_spa(url)
        if pw_result:
            duration = time.monotonic() - start
            fallback_reason = "firecrawl_disabled" if not FIRECRAWL_ENABLED else "firecrawl_failed"
            logger.info(
                "[content_fetch] provider=playwright url=%s duration=%.1fs content_len=%d fallback=true fallback_reason=%s",
                url, duration, len(pw_result), fallback_reason,
            )
            _store_cache(key, pw_result, True)
            return pw_result, True

    # ── 4. Last resort: baseline HTTP ────────────────────────────────────────
    if baseline_html and len(baseline_html.strip()) >= 100:
        duration = time.monotonic() - start
        logger.info(
            "[content_fetch] provider=http url=%s duration=%.1fs content_len=%d fallback=false",
            url, duration, len(baseline_html),
        )
        _store_cache(key, baseline_html, False)
        return baseline_html, False

    logger.warning("[content_fetch] all providers failed for %s", url)
    return None, False


def _store_cache(key: str, html: str, used_spa: bool) -> None:
    _content_cache[key] = {"content": html, "used_spa": used_spa, "timestamp": datetime.now()}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
python3 -m pytest tests/unit/content_fetch/test_orchestrator.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add agents/content_fetch/orchestrator.py \
    tests/unit/content_fetch/test_orchestrator.py
git commit -m "feat(content_fetch): add orchestrator — provider sequencing, cache, metrics"
```

---

## Task 6: Wire __init__.py and update main.py

**Files:**
- Modify: `agents/content_fetch/__init__.py`
- Modify: `main.py` (lines 3357–3666)

- [ ] **Step 1: Update `agents/content_fetch/__init__.py`**

```python
"""
agents.content_fetch — public API for website content fetching.

Re-exports get_website_content so existing callers (main.py, scout_agent.py)
continue to work without modification.
"""

from agents.content_fetch.orchestrator import (
    get_website_content,
    detect_spa_markers,
    is_spa_domain,
)

__all__ = ["get_website_content", "detect_spa_markers", "is_spa_domain"]
```

- [ ] **Step 2: Replace get_website_content block in main.py**

In `main.py`, locate the section from line 3357 (`def is_spa_domain`) through line 3666 (end of `get_website_content`). Replace the entire block with:

```python
# ============================================================================
# UNIFIED CONTENT FETCHING — implementation in agents/content_fetch/
# ============================================================================

from agents.content_fetch import (  # noqa: E402
    get_website_content,
    detect_spa_markers,
    is_spa_domain,
)

# In-memory cache reference (kept here for any legacy direct access)
from agents.content_fetch.orchestrator import _content_cache as content_cache  # noqa: E402

def get_content_cache_key(url: str) -> str:
    """Kept for backward compatibility — delegates to orchestrator."""
    import hashlib
    return f"content_{hashlib.md5(url.encode()).hexdigest()}"

def is_content_cache_valid(timestamp) -> bool:
    """Kept for backward compatibility — delegates to orchestrator."""
    from agents.content_fetch.orchestrator import _cache_valid
    return _cache_valid(timestamp)
```

Also remove the `validate_rendered_content` function at line 3400 only if it is not called anywhere else in `main.py`. Check first:

```bash
grep -n "validate_rendered_content" /Users/tuukka/Downloads/Projects/Brandista/koodi/brandista-api-git/main.py
```

If only defined once and never called → delete it. If called elsewhere → leave it.

- [ ] **Step 3: Run the full test suite**

```bash
python3 -m pytest tests/ -x -q
```

Expected: all tests PASS. If any test fails with an import error around `get_website_content`, `detect_spa_markers`, or `content_cache`, check the import path.

- [ ] **Step 4: Smoke-test the import chain manually**

```bash
cd /Users/tuukka/Downloads/Projects/Brandista/koodi/brandista-api-git
python3 -c "from main import get_website_content; print('OK')"
python3 -c "from agents.content_fetch import get_website_content; print('OK')"
```

Both should print `OK`.

- [ ] **Step 5: Commit**

```bash
git add agents/content_fetch/__init__.py main.py
git commit -m "feat(content_fetch): wire __init__.py re-export and replace main.py block"
```

---

## Task 7: CHANGELOG and final verification

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add v3.2.0 entry to CHANGELOG.md**

Add at the top of the changelog (after the header):

```markdown
## [3.2.0] - 2026-03-20

### Added
- **Firecrawl provider integration** (`agents/content_fetch/`): provider abstraction
  with `http_provider`, `firecrawl_provider`, `playwright_provider`, and `orchestrator`.
- `firecrawl_provider`: firecrawl-py SDK, circuit breaker (3 failures → open 5min),
  Redis cache (1h TTL), quality gate, startup validation for missing API key.
- Structured observability log line per fetch: provider, duration, content_len, fallback reason.
- 4 new env vars: `FIRECRAWL_API_KEY`, `FIRECRAWL_ENABLED` (default: false),
  `FIRECRAWL_TIMEOUT` (default: 15s), `FIRECRAWL_MULTI_PAGE_ENABLED` (default: false).

### Changed
- `get_website_content()` migrated from `main.py:3433–3666` to
  `agents/content_fetch/orchestrator.py`. Return type and callers unchanged.
- `main.py` becomes a thin re-export wrapper for backward compatibility.

### Notes
- **Zero behavior change in Phase 1** (`FIRECRAWL_ENABLED=false` default).
- To enable: set `FIRECRAWL_ENABLED=true` and `FIRECRAWL_API_KEY=<key>` in Railway.
```

- [ ] **Step 2: Run full test suite one final time**

```bash
python3 -m pytest tests/ -x -q
```

Expected: all tests PASS

- [ ] **Step 3: Final commit**

```bash
git add CHANGELOG.md
git commit -m "chore: v3.2.0 — Firecrawl provider integration complete"
```

---

## Rollout Checklist

After all tasks complete:

- [ ] **Phase 1 deployed**: verify Railway deploy succeeds with `FIRECRAWL_ENABLED=false` (default)
- [ ] **Phase 2**: add Railway env vars `FIRECRAWL_ENABLED=true` + `FIRECRAWL_API_KEY=fc-2d531b77f04c41beacdf510528365a22`
- [ ] **Monitor logs** for `[content_fetch]` lines — check `fallback=true` rate
- [ ] **Phase 3** (after 1 week): if fallback rate < 10%, consider setting `CONTENT_FETCH_MODE=balanced` to reduce Playwright default usage
