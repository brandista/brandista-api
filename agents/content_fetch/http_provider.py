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
