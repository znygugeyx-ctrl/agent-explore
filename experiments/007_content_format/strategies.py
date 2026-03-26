"""Content format strategies for experiment 007.

Each strategy transforms the raw HTML returned by fetch_page into a different
format via an after_tool_exec hook. The agent sees the converted content;
the underlying tool always fetches raw HTML.

Strategies:
    raw_html   - No conversion (control). Agent receives full HTML.
    markdown   - HTML → Markdown via MarkItDown (same lib as miroflow production).
    text_only  - Visible text extraction via BeautifulSoup. No structure preserved.
    pruned_html - Cleaned HTML: scripts/styles/nav/ads removed, semantic tags kept.
"""

from __future__ import annotations

import io
import json
import re

from bs4 import BeautifulSoup
from markitdown import MarkItDown

from core.types import TextContent, ToolCall, ToolResultMessage

# ---------------------------------------------------------------------------
# Format converters
# ---------------------------------------------------------------------------


def _identity(html: str) -> str:
    """raw_html: return as-is."""
    return html


def _html_to_markdown(html: str) -> str:
    """Convert HTML to markdown via MarkItDown."""
    md = MarkItDown()
    result = md.convert_stream(io.BytesIO(html.encode("utf-8")))
    text = result.text_content.strip()
    return text if text else html


def _html_to_text(html: str) -> str:
    """Extract visible text only. No structure preserved."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _prune_html(html: str) -> str:
    """Remove noise elements, keep semantic HTML structure."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove non-content elements
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "svg"]):
        tag.decompose()
    # Remove common ad/tracking/popup patterns by class or id
    noise_pattern = re.compile(
        r"ad[-_]?|sidebar|cookie|popup|modal|banner|newsletter|social[-_]?share",
        re.IGNORECASE,
    )
    for el in soup.find_all(attrs={"class": noise_pattern}):
        el.decompose()
    for el in soup.find_all(attrs={"id": noise_pattern}):
        el.decompose()
    # Remove empty divs/spans left behind
    for tag in soup.find_all(["div", "span"]):
        if not tag.get_text(strip=True) and not tag.find(["img", "table", "ul", "ol"]):
            tag.decompose()
    return str(soup)


CONVERTERS: dict[str, callable] = {
    "raw_html": _identity,
    "markdown": _html_to_markdown,
    "text_only": _html_to_text,
    "pruned_html": _prune_html,
}

STRATEGY_NAMES = list(CONVERTERS.keys())


# ---------------------------------------------------------------------------
# Hook factory
# ---------------------------------------------------------------------------


def build_format_hook(strategy: str):
    """Build an after_tool_exec hook that converts fetch_page content.

    The hook intercepts fetch_page results, applies the format conversion,
    and updates the content and metadata before the agent sees it.
    """
    if strategy not in CONVERTERS:
        raise ValueError(f"Unknown strategy: {strategy}. Choose from {STRATEGY_NAMES}")
    converter = CONVERTERS[strategy]

    async def after_tool_exec(
        tc: ToolCall, result: ToolResultMessage
    ) -> ToolResultMessage:
        # Only transform fetch_page results; pass everything else through
        if tc.name != "fetch_page" or result.is_error:
            return result

        try:
            data = json.loads(result.content[0].text)
            raw_html = data["content"]
            converted = converter(raw_html)
            data["content"] = converted
            data["content_length"] = len(converted)
            data["format"] = strategy
            result.content = [TextContent(text=json.dumps(data, ensure_ascii=False))]
        except (json.JSONDecodeError, KeyError, IndexError):
            pass  # If parsing fails, return result as-is

        return result

    return after_tool_exec
