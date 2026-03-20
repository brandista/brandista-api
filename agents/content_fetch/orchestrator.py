"""
Unified content fetching orchestrator.

Migrated from main.py:get_website_content (lines ~3433–3666).
Provides Phase 1 (HTTP + Playwright) and Phase 2 (Firecrawl + fallbacks) flows.
"""

import hashlib
import logging
import time
from typing import Dict, Any, Optional, Tuple

from fastapi import HTTPException

from app.config import (
    CONTENT_FETCH_MODE,
    FIRECRAWL_ENABLED,
    REQUEST_TIMEOUT,
    SPA_CACHE_TTL,
)
from agents.url_utils import get_domain_from_url
from agents.content_fetch.http_provider import fetch_http
from agents.content_fetch.playwright_provider import render_spa
from agents.content_fetch.firecrawl_provider import scrape as firecrawl_scrape

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory cache (module-level, mirrors content_cache in main.py)
# ---------------------------------------------------------------------------

_content_cache: Dict[str, Dict[str, Any]] = {}


def _get_cache_key(url: str, mode: str, force_spa: bool) -> str:
    """Generate a deterministic cache key that captures all fetch-shape parameters."""
    payload = f"{url}|{mode}|{force_spa}"
    return f"content_{hashlib.md5(payload.encode(), usedforsecurity=False).hexdigest()}"


def _is_cache_valid(entry: Dict[str, Any]) -> bool:
    """Return True if the cache entry was stored within SPA_CACHE_TTL seconds."""
    return (time.time() - entry["timestamp"]) < SPA_CACHE_TTL


# ---------------------------------------------------------------------------
# SPA detection helpers (copied from main.py to avoid circular import)
# ---------------------------------------------------------------------------

def is_spa_domain(url: str) -> bool:
    """Check if domain suggests SPA usage."""
    domain = get_domain_from_url(url).lower()
    spa_hints = [
        "brandista.eu", "www.brandista.eu",
        "app.", "dashboard.", "admin.", "portal.",
    ]
    return any(hint in domain for hint in spa_hints)


def detect_spa_markers(html: str) -> bool:
    """Enhanced SPA detection with multiple marker categories."""
    if not html or len(html.strip()) < 100:
        return False

    html_lower = html.lower()

    strong_markers = [
        'id="root"', 'id="app"', 'id="__next"', 'id="nuxt"',
        "data-reactroot", "data-react-helmet", "ng-version=",
        '"__webpack_require__"', '"webpackchunkname"',
        "window.__initial_state__", "window.__preloaded_state__",
    ]

    framework_markers = [
        "react", "vue.js", "angular", "svelte", "next.js",
        "nuxt", "gatsby", "vite", "webpack", "parcel",
    ]

    build_markers = [
        "built with vite", "created-by-webpack", "generated-by",
        "build-time:", "chunk-", "runtime-", "vendor-",
    ]

    strong_count = sum(1 for m in strong_markers if m in html_lower)
    framework_count = sum(1 for m in framework_markers if m in html_lower)
    build_count = sum(1 for m in build_markers if m in html_lower)

    return strong_count >= 1 or (framework_count >= 2 and build_count >= 1)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def get_website_content(
    url: str,
    force_spa: bool = False,
    timeout: int = REQUEST_TIMEOUT,
    mode: str = CONTENT_FETCH_MODE,
) -> Tuple[Optional[str], bool]:
    """
    Unified content fetching with in-memory caching.

    Returns (html, used_spa) where used_spa=True only when Playwright was used.

    Phase 1 (FIRECRAWL_ENABLED=False — default):
        aggressive/force_spa  → Playwright first, HTTP fallback
        balanced              → HTTP first, Playwright if SPA markers detected

    Phase 2 (FIRECRAWL_ENABLED=True):
        Firecrawl → Playwright fallback → HTTP last resort

    The timeout parameter applies to fetch_http and render_spa only; firecrawl_scrape
    uses FIRECRAWL_TIMEOUT from config independently.
    """
    cache_key = _get_cache_key(url, mode=mode, force_spa=force_spa)
    if cache_key in _content_cache and _is_cache_valid(_content_cache[cache_key]):
        cached = _content_cache[cache_key]
        logger.info("[content] cache hit: %s", url)
        return cached["content"], cached["used_spa"]

    # ------------------------------------------------------------------
    # Phase 2 — Firecrawl enabled
    # ------------------------------------------------------------------
    if FIRECRAWL_ENABLED:
        http_res = await fetch_http(url, timeout=timeout)
        baseline_html = (
            http_res.text if (http_res and http_res.status_code == 200 and http_res.text)
            else ""
        )

        fc_html = await firecrawl_scrape(
            url, baseline_html=baseline_html, mode=mode, force_spa=force_spa
        )
        if fc_html:
            _content_cache[cache_key] = {
                "content": fc_html,
                "used_spa": False,
                "timestamp": time.time(),
            }
            return fc_html, False

        # Playwright fallback
        if detect_spa_markers(baseline_html) or force_spa or mode == "aggressive":
            spa_html = await render_spa(url, timeout=timeout)
            if spa_html:
                _content_cache[cache_key] = {
                    "content": spa_html,
                    "used_spa": True,
                    "timestamp": time.time(),
                }
                return spa_html, True

        # HTTP last resort
        if baseline_html and len(baseline_html.strip()) >= 100:
            _content_cache[cache_key] = {
                "content": baseline_html,
                "used_spa": False,
                "timestamp": time.time(),
            }
            return baseline_html, False

        raise HTTPException(
            status_code=400, detail="Website returned insufficient content"
        )

    # ------------------------------------------------------------------
    # Phase 1 — HTTP + Playwright only (default path)
    # ------------------------------------------------------------------
    used_spa = False
    html: Optional[str] = None

    if mode == "aggressive" or force_spa:
        html = await render_spa(url, timeout=timeout)
        if html:
            used_spa = True
        else:
            http_res = await fetch_http(url, timeout=timeout)
            html = (
                http_res.text
                if (http_res and http_res.status_code == 200 and http_res.text)
                else None
            )
            used_spa = False
    else:
        http_res = await fetch_http(url, timeout=timeout)
        baseline_html = (
            http_res.text if (http_res and http_res.status_code == 200 and http_res.text)
            else ""
        )
        if detect_spa_markers(baseline_html) or force_spa or is_spa_domain(url):
            spa_result = await render_spa(url, timeout=timeout)
            html = spa_result or baseline_html
            used_spa = bool(spa_result)
        else:
            html = baseline_html
            used_spa = False

    if not html or len(html.strip()) < 100:
        raise HTTPException(
            status_code=400, detail="Website returned insufficient content"
        )

    _content_cache[cache_key] = {
        "content": html,
        "used_spa": used_spa,
        "timestamp": time.time(),
    }
    return html, used_spa
