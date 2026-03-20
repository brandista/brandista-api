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
