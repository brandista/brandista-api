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
