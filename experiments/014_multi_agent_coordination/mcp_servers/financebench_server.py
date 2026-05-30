"""
FinanceBench MCP server.

Exposes a small SEC filings library (84 10-K/10-Q PDFs as page-level text,
extracted from FinanceBench's published evidence). Tools mirror what an
analyst would do: list filings, open a filing, search inside it, read pages.

One process per task. The pre-loaded corpus is the union of evidence from
ALL questions (so distractors are present); the agent must locate relevant
pages for its specific question.

Env vars:
- FB_DATA  : path to financebench_open_source.jsonl
"""
from __future__ import annotations
import json
import os
import re
import sys
from collections import defaultdict
from typing import Any

DATA = os.environ.get("FB_DATA")
if not DATA or not os.path.isfile(DATA):
    print(f"FB_DATA not set or not a file: {DATA!r}", file=sys.stderr)
    sys.exit(2)

# -------- Build corpus --------
# Each filing is keyed by doc_name; each filing has dict of page_num -> page_text.
FILINGS: dict[str, dict[int, str]] = defaultdict(dict)
FILING_META: dict[str, dict[str, Any]] = {}

with open(DATA) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        rec = json.loads(line)
        doc = rec["doc_name"]
        company = rec.get("company")
        doc_type = rec.get("doc_type")
        period = rec.get("doc_period")
        FILING_META.setdefault(doc, {
            "doc_name": doc, "company": company,
            "doc_type": doc_type, "doc_period": period,
        })
        for ev in (rec.get("evidence") or []):
            page = ev.get("evidence_page_num")
            text = ev.get("evidence_text_full_page") or ev.get("evidence_text")
            if page is None or text is None: continue
            # de-dupe: same page should be identical
            FILINGS[doc][int(page)] = text

# Snapshot summary
print(f"financebench corpus: {len(FILINGS)} filings, "
      f"{sum(len(p) for p in FILINGS.values())} total pages",
      file=sys.stderr)

# -------- MCP tools --------
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("financebench")


@mcp.tool(
    name="list_filings",
    description=(
        "List all available SEC filings in the corpus. Returns a list of "
        "{doc_name, company, doc_type, doc_period} for each filing."
    ),
)
def list_filings() -> list[dict]:
    return [FILING_META[d] for d in sorted(FILINGS.keys())]


@mcp.tool(
    name="search_filings",
    description=(
        "Search the available filings by company name and/or year. Returns matching "
        "filings. company is a partial substring match (case-insensitive); year is exact match."
    ),
)
def search_filings(company: str = "", year: str = "", doc_type: str = "") -> list[dict]:
    company_q = company.lower().strip()
    year_q = str(year).strip()
    type_q = doc_type.lower().strip()
    out = []
    for d, meta in FILING_META.items():
        if company_q and company_q not in (meta.get("company") or "").lower():
            continue
        if year_q and str(meta.get("doc_period") or "") != year_q:
            continue
        if type_q and type_q not in (meta.get("doc_type") or "").lower():
            continue
        out.append(meta)
    return out


@mcp.tool(
    name="open_filing",
    description=(
        "Open a specific filing by doc_name (e.g. '3M_2018_10K'). Returns the list "
        "of available pages and a brief summary."
    ),
)
def open_filing(doc_name: str) -> dict:
    if doc_name not in FILINGS:
        return {"error": f"unknown doc_name: {doc_name}",
                "available_examples": list(FILINGS.keys())[:5]}
    pages = sorted(FILINGS[doc_name].keys())
    return {
        "doc_name": doc_name,
        "company": FILING_META[doc_name].get("company"),
        "doc_type": FILING_META[doc_name].get("doc_type"),
        "doc_period": FILING_META[doc_name].get("doc_period"),
        "pages_available": pages,
        "n_pages": len(pages),
    }


@mcp.tool(
    name="read_page",
    description=(
        "Read a specific page from a filing. Returns the full text of that page. "
        "Use list_filings/search_filings/open_filing first to find the right doc and page."
    ),
)
def read_page(doc_name: str, page_num: str) -> dict:
    if doc_name not in FILINGS:
        return {"error": f"unknown doc_name: {doc_name}"}
    try:
        page = int(page_num)
    except Exception:
        return {"error": f"page_num must be an integer, got: {page_num!r}"}
    if page not in FILINGS[doc_name]:
        return {"error": f"page {page} not available in {doc_name}",
                "pages_available": sorted(FILINGS[doc_name].keys())}
    return {
        "doc_name": doc_name, "page_num": page,
        "text": FILINGS[doc_name][page],
    }


@mcp.tool(
    name="search_in_filing",
    description=(
        "Search for a regex / keyword within a specific filing. Returns up to 5 matching pages "
        "with the page number and a snippet around each match. Useful for locating tables "
        "(e.g. 'capital expenditure', 'net income', 'effective tax rate')."
    ),
)
def search_in_filing(doc_name: str, query: str, max_results: str = "5") -> dict:
    if doc_name not in FILINGS:
        return {"error": f"unknown doc_name: {doc_name}"}
    try:
        max_n = int(max_results)
    except Exception:
        max_n = 5
    pat = re.compile(re.escape(query), re.IGNORECASE) if query else None
    hits = []
    for page_num in sorted(FILINGS[doc_name].keys()):
        text = FILINGS[doc_name][page_num]
        if pat is None or pat.search(text):
            # find first match position
            m = pat.search(text) if pat else None
            if m:
                start = max(0, m.start() - 120)
                end = min(len(text), m.end() + 360)
                snippet = text[start:end]
            else:
                snippet = text[:480]
            hits.append({"page_num": page_num, "snippet": snippet})
            if len(hits) >= max_n: break
    return {"doc_name": doc_name, "query": query, "n_hits": len(hits), "hits": hits}


if __name__ == "__main__":
    mcp.run(transport="stdio")
