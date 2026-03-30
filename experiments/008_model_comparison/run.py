"""Run experiment 008: MiroThinker-1.7-mini on GAIA search tasks.

Custom agent loop for XML/MCP-style tool calling. MiroThinker does not use
OpenAI function calling; instead it outputs <use_mcp_tool> XML blocks.

Usage:
    python -m experiments.008_model_comparison.run [--runs N] [--pilot]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from bench.verifier import GAIAVerifier
from core.types import Model
import core.providers  # noqa: F401
from observer.client import _emit
from tools.fetch_page import fetch_page as _fetch_page_tool
from tools.web_search import web_search as _web_search_tool

EXPERIMENT_DIR = Path(__file__).parent
RESULTS_DIR = EXPERIMENT_DIR / "results"
TASKS_FILE = Path(__file__).parent.parent / "007_content_format" / "tasks.jsonl"

BASE_URL = "http://localhost:8001/v1"
MODEL_ID = "miromind-ai/MiroThinker-1.7-mini"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool descriptions for MiroThinker XML format
# ---------------------------------------------------------------------------

TOOL_DESCRIPTIONS = """You have access to the following tools:

<tools>
<tool>
<name>web_search</name>
<description>Search the web using Google Search. Returns organic results with title, link, and snippet. Use this to find relevant pages.</description>
<input_schema>{"type": "object", "properties": {"q": {"type": "string", "description": "Search query string."}, "num": {"type": "integer", "description": "Number of results (default 10)."}}, "required": ["q"]}</input_schema>
</tool>
<tool>
<name>fetch_page</name>
<description>Fetch the text content of a web page by URL. Use this to read the full content of a specific page after finding it via web_search.</description>
<input_schema>{"type": "object", "properties": {"url": {"type": "string", "description": "The full URL to fetch (must start with http:// or https://)."}, "wait_selector": {"type": "string", "description": "Optional CSS selector to wait for before extracting content."}}, "required": ["url"]}</input_schema>
</tool>
</tools>

To use a tool, output a tool call block EXACTLY in this format (at the end of your message):
<use_mcp_tool>
<server_name>browser</server_name>
<tool_name>TOOL_NAME</tool_name>
<arguments>
{"key": "value"}
</arguments>
</use_mcp_tool>

You may use one tool at a time. Wait for the result before calling the next tool."""

SYSTEM_PROMPT = f"""You are a research assistant that answers factual questions by searching the web.

{TOOL_DESCRIPTIONS}

RULES:
1. You MUST call web_search before answering ANY question. NEVER answer from memory.
2. After getting search results, use fetch_page to read relevant URLs.
3. If the first page doesn't have the answer, search again or try other URLs.
4. When you have found the answer, respond with ONLY the final answer value.
   Do NOT include explanation. Good: "42" or "Paris". Bad: "Based on my research..."
5. Your very first action must ALWAYS be a web_search call."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TaskSpec:
    id: str
    prompt: str
    expected_answer: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskOutcome:
    task_id: str
    run_id: int = 0
    correct: bool = False
    answer: str = ""
    expected: str = ""
    verification_reason: str = ""
    num_turns: int = 0
    num_web_search_calls: int = 0
    num_fetch_page_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    latency_seconds: float = 0.0
    error: str | None = None
    level: int = 0


# ---------------------------------------------------------------------------
# HTML → text (same as 007 text_only strategy)
# ---------------------------------------------------------------------------

def _html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ---------------------------------------------------------------------------
# XML tool call parsing
# ---------------------------------------------------------------------------

_TOOL_CALL_RE = re.compile(
    r"<use_mcp_tool>\s*"
    r"<server_name>.*?</server_name>\s*"
    r"<tool_name>(.*?)</tool_name>\s*"
    r"<arguments>\s*(.*?)\s*</arguments>\s*"
    r"</use_mcp_tool>",
    re.DOTALL,
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(text: str) -> tuple[str, int]:
    """Remove <think>...</think> blocks. Returns (cleaned_text, approx_think_tokens).

    Handles incomplete blocks: if <think> opens but never closes (max_tokens hit),
    strip everything from the opening tag to end of text.
    """
    think_chars = sum(len(m.group(0)) for m in _THINK_RE.finditer(text))
    cleaned = _THINK_RE.sub("", text)
    # Handle unclosed <think> block (thinking hit max_tokens)
    open_idx = cleaned.find("<think>")
    if open_idx != -1:
        think_chars += len(cleaned) - open_idx
        cleaned = cleaned[:open_idx]
    cleaned = cleaned.strip()
    return cleaned, think_chars // 4


def parse_tool_call(text: str) -> tuple[str, dict] | None:
    """Parse first <use_mcp_tool> block from text. Returns (tool_name, args) or None."""
    m = _TOOL_CALL_RE.search(text)
    if not m:
        return None
    tool_name = m.group(1).strip()
    args_text = m.group(2).strip()
    try:
        args = json.loads(args_text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse tool args: %s", args_text[:200])
        return None
    return tool_name, args


def format_tool_result(tool_name: str, result: str, is_error: bool = False) -> str:
    """Format a tool result as XML for MiroThinker."""
    tag = "error" if is_error else "result"
    return (
        f"<tool_result>\n"
        f"<server_name>browser</server_name>\n"
        f"<tool_name>{tool_name}</tool_name>\n"
        f"<{tag}>\n{result}\n</{tag}>\n"
        f"</tool_result>"
    )


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

# Map MiroThinker's native tool names to our implementations
_SEARCH_TOOLS = {"web_search", "google_search", "search", "search_web"}
_FETCH_TOOLS = {"fetch_page", "fetch_webpage", "scrape_webpage", "browse", "web_browser", "browser"}


async def execute_tool(tool_name: str, args: dict) -> tuple[str, bool]:
    """Execute a tool and return (result_text, is_error)."""
    tool_call_id = f"tc_{int(time.time() * 1000)}"
    try:
        # Normalize: "q" or "query" → "q"
        if "query" in args and "q" not in args:
            args["q"] = args.pop("query")
        # Normalize: "url" variants
        for key in ("link", "webpage_url", "website_url"):
            if key in args and "url" not in args:
                args["url"] = args.pop(key)

        if tool_name in _SEARCH_TOOLS:
            result = await _web_search_tool.execute(tool_call_id, args)
            return json.dumps(result, ensure_ascii=False), False
        elif tool_name in _FETCH_TOOLS:
            result = await _fetch_page_tool.execute(tool_call_id, args)
            if isinstance(result, dict) and "content" in result:
                result["content"] = _html_to_text(result["content"])
                result["content_length"] = len(result["content"])
                result["format"] = "text_only"
            return json.dumps(result, ensure_ascii=False), False
        else:
            return f"Unknown tool: {tool_name}. Available tools: web_search, fetch_page", True
    except Exception as e:
        logger.warning("Tool %s failed: %s", tool_name, e)
        return str(e), True


# ---------------------------------------------------------------------------
# Custom agent loop
# ---------------------------------------------------------------------------

async def run_miro_agent(
    task: TaskSpec,
    client: AsyncOpenAI,
    run_id: int,
    max_turns: int = 30,
) -> TaskOutcome:
    outcome = TaskOutcome(
        task_id=task.id,
        expected=task.expected_answer,
        level=int(task.metadata.get("level", 0)),
    )

    messages: list[dict] = [
        {"role": "user", "content": task.prompt},
    ]

    obs_run_id = "exp_008_256k"
    obs_task_id = f"r{run_id}_{task.id[:8]}"
    turn_n = [0]

    def _obs_context(msgs: list[dict]) -> None:
        turn_n[0] += 1
        _emit({"ts": time.time(), "run_id": obs_run_id, "task_id": obs_task_id,
               "type": "context", "turn": turn_n[0],
               "data": {"system_prompt": SYSTEM_PROMPT, "messages": msgs, "tools": [], "tool_count": 0}})

    def _obs_response(text: str, think_toks: int, in_tok: int, out_tok: int) -> None:
        content = []
        if think_toks > 0:
            content.append({"type": "thinking", "thinking": f"[~{think_toks} thinking tokens]"})
        content.append({"type": "text", "text": text})
        _emit({"ts": time.time(), "run_id": obs_run_id, "task_id": obs_task_id,
               "type": "response", "turn": turn_n[0],
               "data": {"content": content,
                        "usage": {"input": in_tok, "output": out_tok, "cache_read": 0,
                                  "cache_write": 0, "ttft_seconds": 0, "cost_total": 0},
                        "stop_reason": "end_turn", "model": MODEL_ID}})

    def _obs_tool(name: str, args: dict, result: str, is_err: bool) -> None:
        _emit({"ts": time.time(), "run_id": obs_run_id, "task_id": obs_task_id,
               "type": "tool_result", "turn": turn_n[0],
               "data": {"tool_name": name, "arguments": args,
                        "content": [{"type": "text", "text": result[:1000]}],
                        "is_error": is_err}})

    start = time.time()
    final_answer = ""

    try:
        for turn in range(max_turns):
            # Stream the response to keep SSH tunnel alive during long thinking traces
            assistant_text = ""
            prompt_tokens = 0
            completion_tokens = 0

            # Observer: emit the context (what model is about to see)
            _obs_context([{"role": "system", "content": SYSTEM_PROMPT}] + messages)

            stream = await client.chat.completions.create(
                model=MODEL_ID,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                temperature=1.0,
                top_p=0.95,
                max_tokens=8192,
                stream=True,
                stream_options={"include_usage": True},
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    assistant_text += chunk.choices[0].delta.content
                if chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens

            # Track tokens
            outcome.input_tokens += prompt_tokens
            outcome.output_tokens += completion_tokens

            # Strip <think> blocks, count thinking tokens
            clean_text, think_toks = strip_thinking(assistant_text)
            outcome.thinking_tokens += think_toks
            outcome.num_turns += 1

            logger.debug(
                "  turn %d: %d chars (%d think tok), clean=%d chars",
                turn + 1, len(assistant_text), think_toks, len(clean_text),
            )

            messages.append({"role": "assistant", "content": assistant_text})

            # Observer: emit response
            _obs_response(clean_text, think_toks, prompt_tokens, completion_tokens)

            # Check for tool call in clean (non-thinking) text
            tool_call = parse_tool_call(clean_text)

            if tool_call is None:
                # No tool call — this is the final answer
                final_answer = clean_text
                # Strip any remaining XML artifacts
                final_answer = re.sub(r"<[^>]+>", "", final_answer).strip()
                break

            tool_name, args = tool_call
            if tool_name in _SEARCH_TOOLS:
                outcome.num_web_search_calls += 1
                logger.info("  -> web_search [%s]: %s", tool_name, str(args.get("q") or args.get("query", ""))[:80])
            elif tool_name in _FETCH_TOOLS:
                outcome.num_fetch_page_calls += 1
                logger.info("  -> fetch_page [%s]: %s", tool_name, str(args.get("url", ""))[:80])

            result_text, is_error = await execute_tool(tool_name, args)
            tool_result_xml = format_tool_result(tool_name, result_text, is_error)

            messages.append({"role": "user", "content": tool_result_xml})

            # Observer: emit tool result
            _obs_tool(tool_name, args, result_text, is_error)

        else:
            # Reached max_turns without final answer
            final_answer = ""
            logger.warning("Task %s hit max_turns=%d", task.id, max_turns)

    except Exception as e:
        outcome.error = str(e)
        logger.error("Task %s failed: %s", task.id, e)

    outcome.latency_seconds = time.time() - start
    outcome.answer = final_answer
    return outcome


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

def load_tasks(path: Path = TASKS_FILE) -> list[TaskSpec]:
    tasks = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            tasks.append(TaskSpec(
                id=data["id"],
                prompt=data["prompt"],
                expected_answer=data["expected_answer"],
                metadata=data.get("metadata", {}),
            ))
    return tasks


# ---------------------------------------------------------------------------
# Run all tasks for one run
# ---------------------------------------------------------------------------

async def run_all_tasks(
    tasks: list[TaskSpec],
    client: AsyncOpenAI,
    run_id: int,
    verifier: GAIAVerifier,
    max_turns: int = 30,
    concurrency: int = 1,
) -> list[TaskOutcome]:
    sem = asyncio.Semaphore(concurrency)
    completed = [0]

    async def _run_one(task: TaskSpec) -> TaskOutcome:
        async with sem:
            outcome = await run_miro_agent(task, client, run_id, max_turns)
            outcome.run_id = run_id

            # Verify
            if outcome.error is None:
                is_correct, reason = await verifier.verify(
                    task.prompt, task.expected_answer, outcome.answer, task.metadata
                )
                outcome.correct = is_correct
                outcome.verification_reason = reason

            completed[0] += 1
            status = "OK" if outcome.correct else ("ERR" if outcome.error else "WRONG")
            logger.info(
                "[%d/%d] L%d %s: %s | turns=%d search=%d fetch=%d | %.1fs | "
                "in=%d out=%d think=%d tok",
                completed[0], len(tasks), outcome.level, task.id[:12], status,
                outcome.num_turns, outcome.num_web_search_calls, outcome.num_fetch_page_calls,
                outcome.latency_seconds, outcome.input_tokens, outcome.output_tokens,
                outcome.thinking_tokens,
            )
            return outcome

    return list(await asyncio.gather(*[_run_one(t) for t in tasks]))


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(all_runs: list[list[TaskOutcome]]) -> str:
    lines = ["# Experiment 008: MiroThinker-1.7-mini — Results\n"]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"Model: {MODEL_ID} via vLLM (TP=4, EC2 g6e.12xlarge)\n")

    all_outcomes = [o for run in all_runs for o in run]
    n_runs = len(all_runs)
    n_tasks = len(all_runs[0]) if all_runs else 0

    def avg(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    # Summary
    acc = avg([float(o.correct) for o in all_outcomes])
    lat = avg([o.latency_seconds for o in all_outcomes if o.error is None])
    turns = avg([o.num_turns for o in all_outcomes])
    searches = avg([o.num_web_search_calls for o in all_outcomes])
    fetches = avg([o.num_fetch_page_calls for o in all_outcomes])
    inp_tok = avg([o.input_tokens for o in all_outcomes if o.error is None])
    out_tok = avg([o.output_tokens for o in all_outcomes if o.error is None])
    think_tok = avg([o.thinking_tokens for o in all_outcomes if o.error is None])

    lines.append("## Summary\n")
    lines.append(f"- Runs: {n_runs}, Tasks per run: {n_tasks}")
    lines.append(f"- **Overall accuracy: {acc:.1%}** ({sum(o.correct for o in all_outcomes)}/{len(all_outcomes)})")
    lines.append(f"- Avg latency: {lat:.1f}s")
    lines.append(f"- Avg turns: {turns:.1f}")
    lines.append(f"- Avg web_search calls: {searches:.1f}")
    lines.append(f"- Avg fetch_page calls: {fetches:.1f}")
    lines.append(f"- Avg input tokens: {inp_tok:.0f}")
    lines.append(f"- Avg output tokens: {out_tok:.0f}")
    lines.append(f"- Avg thinking tokens: {think_tok:.0f}\n")

    # By level
    lines.append("## Accuracy by Level\n")
    lines.append("| Level | Correct | Total | Accuracy |")
    lines.append("|-------|---------|-------|----------|")
    for lvl in [1, 2, 3]:
        lvl_outcomes = [o for o in all_outcomes if o.level == lvl]
        correct = sum(o.correct for o in lvl_outcomes)
        pct = f"{correct/len(lvl_outcomes):.0%}" if lvl_outcomes else "N/A"
        lines.append(f"| L{lvl} | {correct} | {len(lvl_outcomes)} | {pct} |")
    lines.append("")

    # Comparison with 007 text_only baseline (if available)
    baseline_path = EXPERIMENT_DIR.parent / "007_content_format" / "results"
    if baseline_path.exists():
        lines.append("## vs 007 Claude Haiku 4.5 (text_only baseline)\n")
        lines.append("| Metric | MiroThinker-1.7-mini | Claude Haiku 4.5 (007) |")
        lines.append("|--------|---------------------|------------------------|")
        lines.append(f"| Accuracy | {acc:.1%} | (see 007 report) |")
        lines.append(f"| Avg latency | {lat:.1f}s | (see 007 report) |")
        lines.append(f"| Avg input tokens | {inp_tok:.0f} | (see 007 report) |")
        lines.append("")

    # Per-task details
    lines.append("## Per-Task Results\n")
    lines.append("| Run | Task ID | L | OK | Answer | Turns | S | F | Lat | Think tok |")
    lines.append("|-----|---------|---|----|----|-------|---|---|-----|-----------|")
    for o in all_outcomes:
        mark = "Y" if o.correct else ("E" if o.error else "N")
        ans = (o.answer[:25] + "...") if len(o.answer) > 25 else o.answer
        lines.append(
            f"| {o.run_id} | {o.task_id[:14]} | L{o.level} | {mark} | {ans:25s} | "
            f"{o.num_turns} | {o.num_web_search_calls} | {o.num_fetch_page_calls} | "
            f"{o.latency_seconds:.0f}s | {o.thinking_tokens} |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument("--pilot", action="store_true", help="Run first 3 tasks only")
    parser.add_argument("--concurrency", type=int, default=1)
    args = parser.parse_args()

    client = AsyncOpenAI(base_url=BASE_URL, api_key="EMPTY", timeout=3600.0)

    judge_model = Model(
        id="us.anthropic.claude-sonnet-4-20250514-v1:0",
        name="Claude Sonnet (judge)",
        provider="bedrock",
    )
    verifier = GAIAVerifier(judge_model=judge_model)

    tasks = load_tasks()
    if args.pilot:
        tasks = tasks[:3]
        logger.info("PILOT mode: running first %d tasks", len(tasks))
    logger.info("Loaded %d tasks, runs=%d", len(tasks), args.runs)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    all_runs: list[list[TaskOutcome]] = []

    for run_id in range(1, args.runs + 1):
        out_path = RESULTS_DIR / f"run{run_id}.json"

        # Resume: load existing
        existing: dict[str, TaskOutcome] = {}
        if out_path.exists():
            try:
                saved = json.loads(out_path.read_text())
                for o in saved.get("outcomes", []):
                    existing[o["task_id"]] = TaskOutcome(**o)
            except Exception:
                pass

        if len(existing) == len(tasks):
            logger.info("SKIP (done): %s", out_path)
            all_runs.append([existing[t.id] for t in tasks])
            continue

        missing = [t for t in tasks if t.id not in existing]
        if existing:
            logger.info("PARTIAL resume: %d/%d done", len(existing), len(tasks))

        logger.info("=== Run %d | %d tasks ===", run_id, len(missing))
        new_outcomes = await run_all_tasks(missing, client, run_id, verifier, args.max_turns, args.concurrency)

        # Merge and save
        outcome_map = {o.task_id: o for o in new_outcomes}
        merged = []
        for t in tasks:
            if t.id in outcome_map:
                merged.append(outcome_map[t.id])
            elif t.id in existing:
                merged.append(existing[t.id])

        acc = sum(o.correct for o in merged) / len(merged) if merged else 0
        out_path.write_text(json.dumps({
            "run_id": run_id,
            "model": MODEL_ID,
            "accuracy": acc,
            "outcomes": [asdict(o) for o in merged],
        }, indent=2, ensure_ascii=False))
        logger.info("Saved %s (acc=%.1f%%)", out_path, acc * 100)
        all_runs.append(merged)

    report = generate_report(all_runs)
    report_path = RESULTS_DIR / "report.md"
    report_path.write_text(report)
    logger.info("Report: %s", report_path)
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
