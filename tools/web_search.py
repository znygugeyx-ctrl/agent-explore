"""Web search tool via Google Serper API.

Supports multiple API keys via SERPER_API_KEYS (comma-separated).
Falls back to SERPER_API_KEY for single-key compat.
On 400/403, rotates to next key with backoff. Only marks a key as
permanently exhausted after consecutive failures across multiple calls.
"""

from __future__ import annotations

import asyncio
import logging
import os
import ssl
import threading
import time

import aiohttp
import certifi

from core.tools import tool

logger = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"

# A key is marked exhausted after this many consecutive 400/403 responses
_EXHAUST_THRESHOLD = 5


class _KeyRing:
    """Thread-safe rotating key pool for Serper API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: list[str] = []
        self._index = 0
        self._fail_count: dict[int, int] = {}   # key_index -> consecutive 400 count
        self._exhausted: set[int] = set()
        self._load_keys()

    def _load_keys(self) -> None:
        multi = os.environ.get("SERPER_API_KEYS", "")
        if multi:
            self._keys = [k.strip() for k in multi.split(",") if k.strip()]
        if not self._keys:
            single = os.environ.get("SERPER_API_KEY", "")
            if single:
                self._keys = [single]

    @property
    def available(self) -> bool:
        return len(self._keys) > 0 and len(self._exhausted) < len(self._keys)

    def current(self) -> str:
        with self._lock:
            if not self._keys:
                raise RuntimeError(
                    "No Serper API keys configured. "
                    "Set SERPER_API_KEYS (comma-separated) or SERPER_API_KEY."
                )
            if len(self._exhausted) >= len(self._keys):
                raise RuntimeError("All Serper API keys exhausted.")
            return self._keys[self._index]

    def report_success(self, key: str) -> None:
        """Reset failure counter on success."""
        with self._lock:
            try:
                idx = self._keys.index(key)
            except ValueError:
                return
            self._fail_count[idx] = 0

    def report_failure(self, key: str) -> str:
        """Record a 400/403 failure. Rotate to next key. Returns next key to try."""
        with self._lock:
            try:
                idx = self._keys.index(key)
            except ValueError:
                return self._keys[self._index]

            self._fail_count[idx] = self._fail_count.get(idx, 0) + 1
            count = self._fail_count[idx]

            if count >= _EXHAUST_THRESHOLD:
                self._exhausted.add(idx)
                remaining = len(self._keys) - len(self._exhausted)
                logger.warning(
                    "Serper key #%d exhausted (%d consecutive 400s), %d key(s) remaining",
                    idx + 1, count, remaining,
                )
            else:
                logger.info(
                    "Serper key #%d got 400 (%d/%d before exhaust), rotating",
                    idx + 1, count, _EXHAUST_THRESHOLD,
                )

            # Rotate to next non-exhausted key
            for i in range(1, len(self._keys) + 1):
                nxt = (idx + i) % len(self._keys)
                if nxt not in self._exhausted:
                    self._index = nxt
                    return self._keys[nxt]

            raise RuntimeError("All Serper API keys exhausted.")


_key_ring = _KeyRing()


async def _web_search_execute(tool_call_id: str, params: dict) -> dict:
    q = params["q"]
    num = params.get("num", 10)

    payload = {"q": q, "gl": "us", "hl": "en", "num": num}

    max_retries = 6  # more retries to allow key rotation + backoff
    for attempt in range(1, max_retries + 1):
        api_key = _key_ring.current()
        try:
            ssl_ctx = ssl.create_default_context(cafile=certifi.where())
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as session:
                async with session.post(
                    SERPER_URL,
                    json=payload,
                    headers={
                        "X-API-KEY": api_key,
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status in (400, 403):
                        _key_ring.report_failure(api_key)
                        # Backoff before retry with next key
                        await asyncio.sleep(min(2 ** attempt, 15))
                        continue
                    resp.raise_for_status()
                    data = await resp.json()

            _key_ring.report_success(api_key)
            organic = data.get("organic", [])[:num]
            return {
                "query": q,
                "organic": [
                    {
                        "title": r.get("title", ""),
                        "link": r.get("link", ""),
                        "snippet": r.get("snippet", ""),
                    }
                    for r in organic
                ],
                "suggestions": [],
            }
        except RuntimeError:
            raise
        except Exception:
            if attempt >= max_retries:
                raise
            await asyncio.sleep(min(2 ** attempt, 30))

    raise RuntimeError("web_search: max retries exceeded (all attempts returned 400)")


web_search = tool(
    name="web_search",
    description=(
        "Search the web using Google Search. "
        "Returns organic results with title, link, and snippet."
    ),
    parameters={
        "type": "object",
        "properties": {
            "q": {
                "type": "string",
                "description": "Search query string.",
            },
            "num": {
                "type": "integer",
                "description": "Number of results to return (default 10).",
            },
        },
        "required": ["q"],
    },
)(_web_search_execute)
