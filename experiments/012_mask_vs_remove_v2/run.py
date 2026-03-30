"""Experiment 012 v4: Mask vs Remove — Main Runner.

4 strategies:
  all            — 60 tools, no restriction (baseline)
  remove_dynamic — per-turn 5 tools only (best accuracy, worst TTFT)
  mask_hint      — 60 tools + available-tool hint injected into user message
  mask_logit     — 60 tools + group-level token blocking

Usage:
    python -m experiments.012_mask_vs_remove_v2.run --model qwen3_8b --run 1
    python -m experiments.012_mask_vs_remove_v2.run --model qwen3_8b --run 1 \\
        --strategies all remove_dynamic mask_logit --num-tasks 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import yaml

import core.providers  # noqa: F401 — registers providers

from core.llm import complete, extract_tool_calls
from core.tools import AgentTool
from core.types import (
    Context,
    Model,
    ModelCost,
    StreamOptions,
    TextContent,
    ToolResultMessage,
    UserMessage,
)
from .metrics import TurnMetrics, TaskOutcome, compute_turn_cost, summarize_outcomes
from .strategies import build_strategy, collect_group_tokens
from .tools import ALL_TOOLS, TOOL_GROUPS

try:
    from observer.client import (
        _emit as _obs_emit,
        _ser_message as _obs_ser_msg,
        _ser_tool as _obs_ser_tool,
        _ser_usage as _obs_ser_usage,
    )
    _OBSERVER_AVAILABLE = True
except Exception:
    _OBSERVER_AVAILABLE = False

EXPERIMENT_DIR = Path(__file__).parent
logger = logging.getLogger(__name__)


# ── Config / model ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open(EXPERIMENT_DIR / "config.yaml") as f:
        return yaml.safe_load(f)


def build_model(model_key: str, config: dict) -> Model:
    m = config["models"][model_key]
    c = m.get("cost", {})
    return Model(
        id=m["id"],
        name=m["name"],
        provider=m["provider"],
        base_url=m.get("base_url", ""),
        cost=ModelCost(
            input=c.get("input", 0.0),
            output=c.get("output", 0.0),
            cache_read=c.get("cache_read", 0.0),
            cache_write=c.get("cache_write", 0.0),
        ),
    )


# ── Task loading ───────────────────────────────────────────────────────────────

def load_tasks(path: Path) -> list[dict]:
    tasks = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks


# ── vLLM cache metrics ─────────────────────────────────────────────────────────

async def get_vllm_cache_metrics(base_url: str) -> dict[str, float]:
    import aiohttp
    url = base_url.removesuffix("/v1").removesuffix("/") + "/metrics"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                text = await resp.text()
        result = {}
        for line in text.splitlines():
            if line.startswith("vllm:prefix_cache_queries_total"):
                result["queries"] = float(line.split()[-1])
            elif line.startswith("vllm:prefix_cache_hits_total"):
                result["hits"] = float(line.split()[-1])
        return result
    except Exception:
        return {}


# ── Observer helpers ───────────────────────────────────────────────────────────

def obs_emit_context(run_id: str, task_id: str, turn: int, context: Context) -> None:
    if not _OBSERVER_AVAILABLE:
        return
    try:
        _obs_emit({
            "ts": time.time(),
            "run_id": run_id,
            "task_id": task_id,
            "type": "context",
            "turn": turn,
            "data": {
                "system_prompt": context.system_prompt,
                "messages": [_obs_ser_msg(m) for m in context.messages],
                "tools": [_obs_ser_tool(t) for t in (context.tools or [])],
                "tool_count": len(context.tools) if context.tools else 0,
            },
        })
    except Exception:
        pass


def obs_emit_response(run_id: str, task_id: str, turn: int, response: Any) -> None:
    if not _OBSERVER_AVAILABLE:
        return
    try:
        _obs_emit({
            "ts": time.time(),
            "run_id": run_id,
            "task_id": task_id,
            "type": "response",
            "turn": turn,
            "data": {
                "content": [
                    {"type": b.type, **({k: v for k, v in vars(b).items() if k != "type"})}
                    for b in response.content
                ],
                "stop_reason": response.stop_reason,
                "usage": _obs_ser_usage(response.usage),
            },
        })
    except Exception:
        pass


# ── Single turn LLM call ───────────────────────────────────────────────────────

async def call_llm_once(
    model: Model,
    context: Context,
    options: StreamOptions,
    max_retries: int = 3,
) -> Any:
    for attempt in range(1, max_retries + 1):
        response = await complete(model, context, options)
        if response.error_message is None:
            return response
        err = response.error_message.lower()
        if "too long" in err or "validation" in err:
            return response
        if attempt < max_retries:
            wait = [10, 30, 60][min(attempt - 1, 2)] if ("throttl" in err or "too many" in err) else min(2 ** (attempt + 1), 30)
            logger.warning("LLM error (attempt %d/%d): %s — retry in %ds", attempt, max_retries, response.error_message, wait)
            await asyncio.sleep(wait)
    return response


# ── Multi-turn task runner ─────────────────────────────────────────────────────

async def run_multiturn_task(
    task: dict,
    strategy_name: str,
    model: Model,
    options: StreamOptions,
    config: dict,
    group_token_map: dict[str, int] | None = None,
    run_id: int = 1,
    obs_run_id: str = "exp_012",
) -> TaskOutcome:
    task_id = task["id"]
    outcome = TaskOutcome(task_id=task_id, strategy=strategy_name, model_name=model.name, run_id=run_id)

    all_tools: list[AgentTool] = ALL_TOOLS
    tool_lookup: dict[str, AgentTool] = {t.name: t for t in all_tools}

    raw_schedule: dict[str, list[str]] = task.get("tool_availability_schedule") or {}
    schedule: dict[int, list[str]] = {int(k): v for k, v in raw_schedule.items()}

    strategy = build_strategy(strategy_name, schedule, group_token_map)

    system_prompt = config.get("system_prompt", "You are a helpful assistant. Always use a tool.")
    turns: list[str] = task["turns"]
    gt_tools: list[str | None] = task.get("ground_truth_tools") or [None] * len(turns)
    messages: list[Any] = []

    for turn_idx, (user_msg, gt_tool) in enumerate(zip(turns, gt_tools)):
        turn_tools, extra_params = strategy(all_tools, turn_idx)

        # mask_hint returns a user_message_prefix; extract before merging into StreamOptions
        user_prefix = extra_params.pop("user_message_prefix", "")
        actual_user_msg = user_prefix + user_msg if user_prefix else user_msg

        turn_options = options
        if extra_params:
            merged = {**(options.extra or {}), **extra_params}
            turn_options = replace(options, extra=merged)

        context = Context(
            system_prompt=system_prompt,
            messages=messages + [UserMessage(content=actual_user_msg)],
            tools=turn_tools if turn_tools else None,
        )

        obs_task_id = f"{strategy_name}_{task_id}_r{run_id}"
        obs_emit_context(obs_run_id, obs_task_id, turn_idx + 1, context)

        t_start = time.monotonic()
        response = await call_llm_once(model, context, turn_options)
        latency = time.monotonic() - t_start

        obs_emit_response(obs_run_id, obs_task_id, turn_idx + 1, response)

        if response.error_message:
            outcome.error = response.error_message
            break

        tool_calls = extract_tool_calls(response)
        tool_called = tool_calls[0].name if tool_calls else None

        tool_result_content = ""
        if tool_calls:
            tc = tool_calls[0]
            agent_tool = tool_lookup.get(tc.name)
            if agent_tool:
                try:
                    mock_result = await agent_tool.execute(tc.id, tc.arguments)
                    tool_result_content = json.dumps(mock_result)
                except Exception as e:
                    tool_result_content = json.dumps({"error": str(e)})
            else:
                tool_result_content = json.dumps({"error": f"Tool {tc.name!r} not found"})

        usage = response.usage
        cost_in, cost_out, cost_cr, cost_total = compute_turn_cost(usage, model.cost)

        tm = TurnMetrics(
            turn_idx=turn_idx,
            ttft_seconds=usage.ttft_seconds,
            latency_seconds=latency,
            input_tokens=usage.input,
            output_tokens=usage.output,
            cache_read_tokens=usage.cache_read,
            cache_write_tokens=usage.cache_write,
            tools_presented=len(turn_tools),
            tools_available=len(schedule.get(turn_idx, [])),
            tool_called=tool_called,
            ground_truth_tool=gt_tool or "",
            correct=(tool_called is not None and tool_called == gt_tool),
            cost_input=cost_in,
            cost_output=cost_out,
            cost_cache_read=cost_cr,
            cost_total=cost_total,
        )
        outcome.turns.append(tm)

        messages.append(UserMessage(content=actual_user_msg))
        messages.append(response)
        if tool_calls:
            tc = tool_calls[0]
            messages.append(ToolResultMessage(
                tool_call_id=tc.id,
                tool_name=tc.name,
                content=[TextContent(text=tool_result_content)],
            ))

    return outcome


# ── Strategy runner ────────────────────────────────────────────────────────────

async def run_strategy(
    strategy_name: str,
    model: Model,
    tasks: list[dict],
    config: dict,
    run_id: int,
    group_token_map: dict[str, int] | None = None,
    vllm_base_url: str | None = None,
    obs_run_id: str = "exp_012",
) -> tuple[list[TaskOutcome], dict]:
    options = StreamOptions(
        temperature=config.get("temperature", 0.0),
        max_tokens=config.get("max_tokens", 512),
    )

    cache_before = {}
    if vllm_base_url:
        cache_before = await get_vllm_cache_metrics(vllm_base_url)

    sem = asyncio.Semaphore(config.get("max_parallel", 3))

    async def run_one(task: dict) -> TaskOutcome:
        async with sem:
            t0 = time.monotonic()
            result = await run_multiturn_task(task, strategy_name, model, options, config, group_token_map, run_id, obs_run_id)
            elapsed = time.monotonic() - t0
            status = "✓" if result.accuracy >= 1.0 else f"{result.accuracy:.0%}"
            print(f"  [{strategy_name}] {task['id']:50s} {status}  {elapsed:.1f}s  turns={result.num_turns}")
            return result

    outcomes = await asyncio.gather(*[run_one(t) for t in tasks])

    cache_metrics = {}
    if vllm_base_url:
        cache_after = await get_vllm_cache_metrics(vllm_base_url)
        q_delta = cache_after.get("queries", 0) - cache_before.get("queries", 0)
        h_delta = cache_after.get("hits", 0) - cache_before.get("hits", 0)
        if q_delta > 0:
            cache_metrics = {"queries": q_delta, "hits": h_delta, "hit_rate": h_delta / q_delta}

    return list(outcomes), cache_metrics


# ── Results saving ─────────────────────────────────────────────────────────────

def save_results(
    strategy: str,
    model_name: str,
    run_id: int,
    outcomes: list[TaskOutcome],
    cache_metrics: dict,
    summary: dict,
) -> Path:
    results_dir = EXPERIMENT_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    fname = f"{strategy}_{model_name.lower().replace('-', '_')}_run{run_id}.json"
    out = {
        "strategy": strategy,
        "model": model_name,
        "run_id": run_id,
        "summary": summary,
        "cache_metrics": cache_metrics,
        "outcomes": [asdict(o) for o in outcomes],
    }
    path = results_dir / fname
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  [saved] {path}")
    return path


# ── Main ───────────────────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    config = load_config()
    model = build_model(args.model, config)
    is_vllm = model.provider == "openai_compat"
    vllm_base_url = config.get("vllm_base_url") if is_vllm else None

    tasks_path = EXPERIMENT_DIR / "tasks" / "bfcl_multi_turn.jsonl"
    if not tasks_path.exists():
        print(f"[error] Tasks file not found: {tasks_path}")
        print("Run: python -m experiments.012_mask_vs_remove_v2.prepare_tasks_synthetic")
        return

    tasks = load_tasks(tasks_path)
    if args.num_tasks:
        tasks = tasks[: args.num_tasks]
    total_turns = sum(len(t["turns"]) for t in tasks)
    print(f"[run] Model={model.name}  Tasks={len(tasks)}  TotalTurns={total_turns}  Run={args.run}")

    provider_type = "vllm" if is_vllm else "bedrock"
    all_strategies = config["strategies"][provider_type]
    strategies = args.strategies if args.strategies else all_strategies
    strategies = [s for s in strategies if s in all_strategies]
    print(f"[run] Strategies: {strategies}")

    # Collect group-level token map for mask_logit
    group_token_map: dict[str, int] | None = None
    if is_vllm and "mask_logit" in strategies:
        print("[prep] Collecting group token map for mask_logit...")
        all_tool_names = [t.name for t in ALL_TOOLS]
        group_token_map = await collect_group_tokens(vllm_base_url, model.id, all_tool_names)
        print(f"  Group token map ({len(group_token_map)} groups):")
        for grp, tid in sorted(group_token_map.items()):
            print(f"    {grp:10s} → token_id={tid}")
        all_tids = list(group_token_map.values())
        assert len(set(all_tids)) == len(all_tids), (
            f"TOKEN COLLISION DETECTED: {group_token_map}"
        )
        print(f"  [ok] All {len(group_token_map)} group tokens are unique — no collisions")

    obs_run_id = f"exp_012_{model.name.lower().replace('-', '_').replace('/', '_')}_run{args.run}"
    print(f"[obs] run_id={obs_run_id}  → http://localhost:7777")

    for strategy_name in strategies:
        print(f"\n── Strategy: {strategy_name} ──")
        outcomes, cache_metrics = await run_strategy(
            strategy_name, model, tasks, config, args.run, group_token_map, vllm_base_url, obs_run_id
        )
        summary = summarize_outcomes(list(outcomes))
        hit_rate = cache_metrics.get("hit_rate", 0)
        print(f"  accuracy={summary.get('accuracy_mean', 0):.1%}  "
              f"ttft_mean={summary.get('ttft_mean', 0):.3f}s  "
              f"cache_hit={hit_rate:.1%}")
        save_results(strategy_name, model.name, args.run, list(outcomes), cache_metrics, summary)

    print("\n[done]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=["qwen3_8b", "qwen3_14b", "claude_haiku"])
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--num-tasks", type=int, default=None)
    parser.add_argument("--strategies", nargs="+", default=None)
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main(parser.parse_args()))
