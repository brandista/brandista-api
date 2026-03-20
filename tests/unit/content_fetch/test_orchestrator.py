"""TDD tests for agents/content_fetch/orchestrator.py — get_website_content()."""

import pytest
import time
from typing import Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _long_html(n: int = 200) -> str:
    return "<html><body>" + "x" * n + "</body></html>"


# ---------------------------------------------------------------------------
# Test 1 — cache hit: no providers called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_returns_without_calling_providers():
    """A warm cache entry is returned directly — providers must not be called."""
    from agents.content_fetch import orchestrator

    url = "https://cache-hit.example.com"
    html = _long_html(300)

    # Manually plant a valid cache entry
    key = orchestrator._get_cache_key(url, mode="balanced", force_spa=False)
    orchestrator._content_cache[key] = {
        "content": html,
        "used_spa": False,
        "timestamp": time.time(),
    }

    with patch("agents.content_fetch.orchestrator.fetch_http") as mock_http, \
         patch("agents.content_fetch.orchestrator.render_spa") as mock_spa:

        result_html, used_spa = await orchestrator.get_website_content(
            url, force_spa=False, mode="balanced"
        )

    mock_http.assert_not_called()
    mock_spa.assert_not_called()
    assert result_html == html
    assert used_spa is False

    # Clean up
    del orchestrator._content_cache[key]


# ---------------------------------------------------------------------------
# Test 2 — Phase 1, aggressive mode: Playwright first, HTTP fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase1_aggressive_mode_playwright_first_then_http_fallback():
    """In aggressive mode render_spa is called first; if it returns None, fetch_http is used."""
    from agents.content_fetch import orchestrator

    url = "https://aggressive.example.com"
    baseline = _long_html(250)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = baseline

    with patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", False), \
         patch("agents.content_fetch.orchestrator.render_spa", new_callable=AsyncMock, return_value=None) as mock_spa, \
         patch("agents.content_fetch.orchestrator.fetch_http", new_callable=AsyncMock, return_value=mock_response) as mock_http:

        result_html, used_spa = await orchestrator.get_website_content(
            url, force_spa=False, mode="aggressive"
        )

    mock_spa.assert_called_once_with(url, timeout=30)
    mock_http.assert_called_once_with(url, timeout=30)
    assert result_html == baseline
    assert used_spa is False

    # Clean up cache
    orchestrator._content_cache.clear()


# ---------------------------------------------------------------------------
# Test 3 — Phase 1, balanced mode, plain HTTP (no SPA markers)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase1_balanced_http_only_no_spa():
    """Balanced mode: plain HTTP page → no Playwright call → (html, False)."""
    from agents.content_fetch import orchestrator

    url = "https://plain.example.com"
    # HTML without any SPA markers, long enough
    plain_html = "<html><body>" + "plain content " * 20 + "</body></html>"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = plain_html

    with patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", False), \
         patch("agents.content_fetch.orchestrator.fetch_http", new_callable=AsyncMock, return_value=mock_response), \
         patch("agents.content_fetch.orchestrator.render_spa", new_callable=AsyncMock) as mock_spa, \
         patch("agents.content_fetch.orchestrator.detect_spa_markers", return_value=False), \
         patch("agents.content_fetch.orchestrator.is_spa_domain", return_value=False):

        result_html, used_spa = await orchestrator.get_website_content(
            url, force_spa=False, mode="balanced"
        )

    mock_spa.assert_not_called()
    assert result_html == plain_html
    assert used_spa is False

    orchestrator._content_cache.clear()


# ---------------------------------------------------------------------------
# Test 4 — Phase 1, balanced mode, SPA markers detected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase1_balanced_spa_markers_triggers_playwright():
    """Balanced mode: SPA markers in HTTP response → render_spa called → (html, True)."""
    from agents.content_fetch import orchestrator

    url = "https://spa.example.com"
    spa_baseline = '<html><body id="root">' + "x" * 200 + "</body></html>"
    rendered = "<html><body>" + "rendered content " * 30 + "</body></html>"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = spa_baseline

    with patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", False), \
         patch("agents.content_fetch.orchestrator.fetch_http", new_callable=AsyncMock, return_value=mock_response), \
         patch("agents.content_fetch.orchestrator.render_spa", new_callable=AsyncMock, return_value=rendered) as mock_spa, \
         patch("agents.content_fetch.orchestrator.detect_spa_markers", return_value=True), \
         patch("agents.content_fetch.orchestrator.is_spa_domain", return_value=False):

        result_html, used_spa = await orchestrator.get_website_content(
            url, force_spa=False, mode="balanced"
        )

    mock_spa.assert_called_once_with(url, timeout=30)
    assert result_html == rendered
    assert used_spa is True

    orchestrator._content_cache.clear()


# ---------------------------------------------------------------------------
# Test 5 — Phase 1, insufficient content → HTTPException(400)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase1_insufficient_content_raises_http_exception():
    """When all providers return empty/short content, HTTPException(400) is raised."""
    from agents.content_fetch import orchestrator

    url = "https://empty.example.com"

    with patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", False), \
         patch("agents.content_fetch.orchestrator.fetch_http", new_callable=AsyncMock, return_value=None), \
         patch("agents.content_fetch.orchestrator.render_spa", new_callable=AsyncMock, return_value=None):

        with pytest.raises(HTTPException) as exc_info:
            await orchestrator.get_website_content(url, force_spa=False, mode="aggressive")

    assert exc_info.value.status_code == 400

    orchestrator._content_cache.clear()


# ---------------------------------------------------------------------------
# Test 6 — Phase 2, Firecrawl success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase2_firecrawl_success_no_playwright():
    """Phase 2: Firecrawl returns html → no Playwright call → (html, False)."""
    from agents.content_fetch import orchestrator

    url = "https://firecrawl.example.com"
    fc_html = "<html><body>" + "firecrawl " * 50 + "</body></html>"
    baseline = _long_html(150)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = baseline

    with patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", True), \
         patch("agents.content_fetch.orchestrator.fetch_http", new_callable=AsyncMock, return_value=mock_response), \
         patch("agents.content_fetch.orchestrator.firecrawl_scrape", new_callable=AsyncMock, return_value=fc_html) as mock_fc, \
         patch("agents.content_fetch.orchestrator.render_spa", new_callable=AsyncMock) as mock_spa:

        result_html, used_spa = await orchestrator.get_website_content(url, mode="balanced")

    mock_fc.assert_called_once()
    mock_spa.assert_not_called()
    assert result_html == fc_html
    assert used_spa is False

    orchestrator._content_cache.clear()


# ---------------------------------------------------------------------------
# Test 7 — Phase 2, Firecrawl → None, fallback to Playwright
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase2_firecrawl_none_falls_back_to_playwright():
    """Phase 2: Firecrawl returns None, SPA markers present → render_spa called → (html, True)."""
    from agents.content_fetch import orchestrator

    url = "https://fc-fallback.example.com"
    spa_html = "<html><body>" + "playwright content " * 30 + "</body></html>"
    baseline = "<html><body>" + "x" * 150 + "</body></html>"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = baseline

    with patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", True), \
         patch("agents.content_fetch.orchestrator.fetch_http", new_callable=AsyncMock, return_value=mock_response), \
         patch("agents.content_fetch.orchestrator.firecrawl_scrape", new_callable=AsyncMock, return_value=None), \
         patch("agents.content_fetch.orchestrator.render_spa", new_callable=AsyncMock, return_value=spa_html) as mock_spa, \
         patch("agents.content_fetch.orchestrator.detect_spa_markers", return_value=True):

        result_html, used_spa = await orchestrator.get_website_content(url, mode="balanced")

    mock_spa.assert_called_once_with(url, timeout=30)
    assert result_html == spa_html
    assert used_spa is True

    orchestrator._content_cache.clear()


# ---------------------------------------------------------------------------
# Test 8 — Phase 2, Firecrawl None + Playwright None → HTTP last resort
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_phase2_last_resort_http():
    """Phase 2: Firecrawl None, Playwright None → baseline >= 100 chars returned → (baseline, False)."""
    from agents.content_fetch import orchestrator

    url = "https://last-resort.example.com"
    baseline = "<html><body>" + "x" * 200 + "</body></html>"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = baseline

    with patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", True), \
         patch("agents.content_fetch.orchestrator.fetch_http", new_callable=AsyncMock, return_value=mock_response), \
         patch("agents.content_fetch.orchestrator.firecrawl_scrape", new_callable=AsyncMock, return_value=None), \
         patch("agents.content_fetch.orchestrator.render_spa", new_callable=AsyncMock, return_value=None), \
         patch("agents.content_fetch.orchestrator.detect_spa_markers", return_value=False):

        result_html, used_spa = await orchestrator.get_website_content(url, mode="balanced")

    assert result_html == baseline
    assert used_spa is False

    orchestrator._content_cache.clear()


# ---------------------------------------------------------------------------
# Test 9 — return type is (str, bool) tuple
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_return_type_is_str_bool_tuple():
    """get_website_content() must return a (str, bool) tuple."""
    from agents.content_fetch import orchestrator

    url = "https://type-check.example.com"
    html = _long_html(300)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html

    with patch("agents.content_fetch.orchestrator.FIRECRAWL_ENABLED", False), \
         patch("agents.content_fetch.orchestrator.fetch_http", new_callable=AsyncMock, return_value=mock_response), \
         patch("agents.content_fetch.orchestrator.render_spa", new_callable=AsyncMock, return_value=html), \
         patch("agents.content_fetch.orchestrator.detect_spa_markers", return_value=False), \
         patch("agents.content_fetch.orchestrator.is_spa_domain", return_value=False):

        result = await orchestrator.get_website_content(url, mode="balanced")

    assert isinstance(result, tuple), "result must be a tuple"
    assert len(result) == 2, "tuple must have exactly 2 elements"
    html_part, spa_part = result
    assert isinstance(html_part, str), "first element must be str"
    assert isinstance(spa_part, bool), "second element must be bool"

    orchestrator._content_cache.clear()
