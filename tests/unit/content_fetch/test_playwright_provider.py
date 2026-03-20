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
