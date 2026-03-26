"""Fetch web pages via local Playwright headless browser.

Returns raw HTML by default. Format conversion (markdown, text, etc.)
is handled externally via after_tool_exec hooks in experiments.

Dependencies:
    playwright (+ chromium browser: python3 -m playwright install chromium)
"""

from __future__ import annotations

from playwright.async_api import async_playwright

from core.tools import tool


async def _fetch_page_execute(tool_call_id: str, params: dict) -> dict:
    url = params["url"]
    wait_selector = params.get("wait_selector")

    if not url:
        raise ValueError("URL cannot be empty")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    import asyncio

    async def _do_fetch() -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Brief wait for JS rendering, but don't wait for networkidle
                await page.wait_for_timeout(2000)
                if wait_selector:
                    await page.wait_for_selector(wait_selector, timeout=10000)
                return await page.content()
            finally:
                await browser.close()

    # Total timeout: 3 minutes to prevent runaway fetches
    html = await asyncio.wait_for(_do_fetch(), timeout=180)

    if not html or not html.strip():
        raise ValueError("Page returned empty content")

    return {
        "url": url,
        "content": html,
        "content_length": len(html),
    }


fetch_page = tool(
    name="fetch_page",
    description=(
        "Fetch and read a web page using a real browser, supporting JavaScript-rendered content. "
        "Returns the page content for analysis. Use this to read full content of URLs from web_search."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch.",
            },
            "wait_selector": {
                "type": "string",
                "description": "Optional CSS selector to wait for before extracting content.",
            },
        },
        "required": ["url"],
    },
)(_fetch_page_execute)
