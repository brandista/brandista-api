"""Firecrawl provider — SDK-based content fetch with circuit breaker and Redis cache."""

import asyncio
import hashlib
import json
import logging
import threading
import time
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
def _validate_config():
    if FIRECRAWL_ENABLED and not FIRECRAWL_API_KEY:
        raise ValueError(
            "FIRECRAWL_ENABLED=true but FIRECRAWL_API_KEY is not set. "
            "Set FIRECRAWL_API_KEY environment variable or disable FIRECRAWL_ENABLED."
        )

_validate_config()

try:
    from firecrawl import FirecrawlApp as _FirecrawlApp
    _FIRECRAWL_AVAILABLE = True
except ImportError:
    _FirecrawlApp = None  # type: ignore
    _FIRECRAWL_AVAILABLE = False
    if FIRECRAWL_ENABLED:
        logger.warning("[firecrawl] firecrawl-py not installed but FIRECRAWL_ENABLED=true")

_FIRECRAWL_APP: Optional[object] = None  # module-level singleton, created once


def _get_firecrawl_app():
    global _FIRECRAWL_APP
    if _FIRECRAWL_APP is None:
        _FIRECRAWL_APP = _FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    return _FIRECRAWL_APP

_REDIS_CLIENT = None  # lazy init
_REDIS_LOCK = threading.Lock()


def _get_redis():
    global _REDIS_CLIENT
    if _REDIS_CLIENT is None and REDIS_URL:
        with _REDIS_LOCK:
            if _REDIS_CLIENT is None:  # double-checked locking
                try:
                    import redis as redis_lib
                    _REDIS_CLIENT = redis_lib.from_url(REDIS_URL, decode_responses=True)
                except Exception as e:
                    logger.warning("[firecrawl] Redis init failed: %s", e)
    return _REDIS_CLIENT


def _cache_key(url: str, mode: str = "", force_spa: bool = False) -> str:
    # Include version + fetch shape so config/quality-gate changes don't serve stale results
    payload = f"{url}|{mode}|{force_spa}"
    return f"firecrawl:v1:{hashlib.md5(payload.encode()).hexdigest()}"


def _redis_get(url: str, mode: str = "", force_spa: bool = False) -> Optional[str]:
    try:
        r = _get_redis()
        if r:
            return r.get(_cache_key(url, mode, force_spa))
    except Exception as e:
        logger.debug("[firecrawl] Redis GET failed: %s", e)
    return None


def _redis_set(url: str, html: str, mode: str = "", force_spa: bool = False, ttl: int = 3600) -> None:
    try:
        r = _get_redis()
        if r:
            r.setex(_cache_key(url, mode, force_spa), ttl, html)
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
    # Clean text must be > 500 chars (content depth check)
    text = _clean_text(firecrawl_html)
    if len(text) <= 500:
        return False
    # Firecrawl must not serve an error page or cookie wall
    if _is_error_or_cookiewall(firecrawl_html):
        return False
    # Firecrawl must deliver at least 10% more raw content than HTTP baseline
    # (both sides measured as raw HTML; if no baseline, any non-empty result passes)
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
        # Half-open: allow probe only after a positive recovery_timeout has elapsed
        if self._recovery > 0 and (datetime.now() - self._opened_at).total_seconds() > self._recovery:
            return False  # half-open: allow probe
        return True

    def allow_probe(self) -> bool:
        """True when breaker is in half-open state (past recovery timeout)."""
        if self._failures < self._threshold:
            return False
        if self._opened_at is None:
            return False
        # recovery_timeout=0 means always allow probe once opened
        if self._recovery == 0:
            return True
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


async def scrape(
    url: str,
    baseline_html: Optional[str] = None,
    mode: str = "",
    force_spa: bool = False,
) -> Optional[str]:
    """
    Fetch URL via Firecrawl SDK. Returns HTML string or None if disabled,
    circuit open, quality gate fails, or any error occurs.
    """
    if not FIRECRAWL_ENABLED or not _FIRECRAWL_AVAILABLE:
        return None

    if _circuit_breaker.is_open() and not _circuit_breaker.allow_probe():
        logger.info("[firecrawl] circuit OPEN — skipping %s", url)
        return None

    # Redis cache check (key includes mode + force_spa to avoid stale hits after config changes)
    cached = _redis_get(url, mode=mode, force_spa=force_spa)
    if cached:
        logger.info("[firecrawl] cache HIT for %s", url)
        logger.info("[content_fetch] provider=firecrawl url=%s duration=0.0s content_len=%d fallback=false cache=hit", url, len(cached))
        return cached

    t0 = time.monotonic()
    try:
        loop = asyncio.get_running_loop()
        app = _get_firecrawl_app()

        result = await loop.run_in_executor(
            None,
            lambda: app.scrape_url(
                url,
                formats=["html", "markdown"],
                timeout=FIRECRAWL_TIMEOUT,
            ),
        )

        html = result.get("html", "") if isinstance(result, dict) else ""
        duration = time.monotonic() - t0

        if not _quality_gate(html, baseline_html):
            logger.info("[firecrawl] quality gate FAILED for %s", url)
            logger.info("[content_fetch] provider=firecrawl url=%s duration=%.1fs content_len=%d fallback=true fallback_reason=firecrawl_quality_gate cache=miss", url, duration, len(html))
            _circuit_breaker.record_failure()
            return None

        logger.info("[content_fetch] provider=firecrawl url=%s duration=%.1fs content_len=%d fallback=false cache=miss", url, duration, len(html))
        _circuit_breaker.record_success()
        _redis_set(url, html, mode=mode, force_spa=force_spa)
        return html

    except Exception as e:
        duration = time.monotonic() - t0
        logger.warning("[firecrawl] scrape failed for %s: %s", url, e)
        logger.warning("[content_fetch] provider=firecrawl url=%s duration=%.1fs content_len=0 fallback=true fallback_reason=firecrawl_error cache=miss", url, duration)
        _circuit_breaker.record_failure()
        return None
