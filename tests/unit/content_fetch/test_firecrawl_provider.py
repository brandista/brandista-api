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
