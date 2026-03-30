"""Prepare BFCL v3 multi-turn tasks for Experiment 012.

Steps:
1. Download BFCL v3 multi_turn_base dataset (HuggingFace or GitHub)
2. Filter tasks with >= min_tools tools and >= min_turns turns
3. Pad tool pool to target_total with filler tools (from tools.py)
4. Use Claude Opus 4.6 to generate tool_availability_schedule per task
5. Save to tasks/bfcl_multi_turn.jsonl

Usage:
    python -m experiments.012_mask_vs_remove_v2.prepare_tasks \\
        --num-tasks 10 --min-tools 5 --min-turns 3 --output tasks/bfcl_multi_turn.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).parent

# BFCL v3 multi-turn base data URL (gorilla GitHub raw)
BFCL_URL = (
    "https://raw.githubusercontent.com/ShishirPatil/gorilla"
    "/main/berkeley-function-call-leaderboard/data/BFCL_v3_multi_turn_base.json"
)


# ── Data loading ──────────────────────────────────────────────────────────────

def _download_bfcl(cache_path: Path) -> list[dict]:
    """Download BFCL multi_turn_base JSON and cache locally."""
    if cache_path.exists():
        print(f"[cache] Using cached BFCL data: {cache_path}")
        with open(cache_path) as f:
            return json.load(f)

    print(f"[download] Fetching BFCL from GitHub...")
    try:
        with urllib.request.urlopen(BFCL_URL, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(data, f)
        print(f"[download] Saved {len(data)} entries to {cache_path}")
        return data
    except Exception as e:
        print(f"[error] GitHub download failed: {e}")
        print(f"\nPlease manually download BFCL v3 multi_turn data and place it at:")
        print(f"  {cache_path}")
        print(f"\nSource: https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard/data")
        sys.exit(1)


def _load_bfcl_hf() -> list[dict] | None:
    """Try loading from HuggingFace datasets (gorilla-llm/Berkeley-Function-Calling-Leaderboard)."""
    try:
        from datasets import load_dataset
        ds = load_dataset(
            "gorilla-llm/Berkeley-Function-Calling-Leaderboard",
            "multi_turn_base",
            split="test",
            trust_remote_code=True,
        )
        return list(ds)
    except Exception as e:
        print(f"[hf] HuggingFace load failed ({e}), falling back to GitHub...")
        return None


def load_bfcl_data(tasks_dir: Path) -> list[dict]:
    """Load BFCL multi_turn_base data, trying HuggingFace then GitHub."""
    cache_path = tasks_dir / "_bfcl_raw.json"
    data = _load_bfcl_hf()
    if data is None:
        data = _download_bfcl(cache_path)
    return data


# ── Filtering ─────────────────────────────────────────────────────────────────

def parse_bfcl_entry(entry: dict) -> dict | None:
    """Parse a BFCL entry into a normalized dict. Returns None if format is unrecognized."""
    # Support both list-of-dicts and direct-dict formats
    funcs = entry.get("function") or entry.get("functions") or []
    if isinstance(funcs, dict):
        funcs = list(funcs.values())

    questions = entry.get("question") or []
    # question may be [[{role, content}], [{role, content}], ...]
    # or [{role, content}, ...]
    turns = []
    for q in questions:
        if isinstance(q, list):
            user_msgs = [m["content"] for m in q if m.get("role") == "user"]
            if user_msgs:
                turns.append(user_msgs[0])
        elif isinstance(q, dict) and q.get("role") == "user":
            turns.append(q["content"])

    ground_truth = entry.get("ground_truth") or []

    return {
        "id": entry.get("id", "unknown"),
        "functions": funcs,
        "turns": turns,
        "ground_truth": ground_truth,
    }


def filter_tasks(
    data: list[dict],
    min_tools: int,
    min_turns: int,
    num_tasks: int,
) -> list[dict]:
    """Filter BFCL entries and return up to num_tasks valid tasks."""
    results = []
    for entry in data:
        parsed = parse_bfcl_entry(entry)
        if parsed is None:
            continue
        if len(parsed["functions"]) < min_tools:
            continue
        if len(parsed["turns"]) < min_turns:
            continue
        if len(parsed["ground_truth"]) < min_turns:
            continue
        results.append(parsed)
        if len(results) >= num_tasks:
            break
    return results


# ── Schedule generation via Claude Opus ──────────────────────────────────────

SCHEDULE_CACHE_PATH = EXPERIMENT_DIR / "tasks" / "_schedule_cache.json"


def _load_schedule_cache() -> dict[str, dict[str, list[str]]]:
    if SCHEDULE_CACHE_PATH.exists():
        with open(SCHEDULE_CACHE_PATH) as f:
            return json.load(f)
    return {}


def _save_schedule_cache(cache: dict) -> None:
    SCHEDULE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULE_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


async def _generate_schedule_for_task(
    task_id: str,
    functions: list[dict],
    turns: list[str],
    ground_truth: list[list[dict]],
    model,
) -> dict[str, list[str]]:
    """Call Claude Opus 4.6 to derive tool_availability_schedule for one task."""
    from core.llm import complete
    from core.types import Context, UserMessage

    func_names = [f["name"] for f in functions]

    # Build ground truth summary
    gt_summary = []
    for i, gt_turn in enumerate(ground_truth):
        if isinstance(gt_turn, list):
            calls = [c.get("name", "?") for c in gt_turn if isinstance(c, dict)]
        else:
            calls = [str(gt_turn)]
        gt_summary.append(f"  Turn {i}: {', '.join(calls) if calls else '(no call)'}")

    prompt = f"""You are analyzing a multi-turn task to determine dynamic tool availability.

Available tools ({len(func_names)} total):
{json.dumps(func_names, indent=2)}

Ground truth tool calls per turn:
{chr(10).join(gt_summary)}

User messages per turn:
{json.dumps({str(i): t for i, t in enumerate(turns)}, indent=2)}

Task: For each turn index, specify which tool names should be "available" to the model.

Rules:
1. The tool(s) actually called in ground_truth MUST be in the available set for that turn
2. Include 1-3 additional thematically related tools that a user might also need
3. The rest are "unavailable" at that turn — the majority should be unavailable
4. Aim for 3-7 available tools per turn out of the total

Return ONLY a JSON object, no other text:
{{"0": ["tool_a", "tool_b"], "1": ["tool_c", "tool_d"], ...}}"""

    from core.types import StreamOptions
    context = Context(messages=[UserMessage(content=prompt)])
    options = StreamOptions(temperature=0.0, max_tokens=500)

    try:
        response = await complete(model, context, options)
        text = "".join(
            b.text for b in response.content
            if hasattr(b, "text")
        ).strip()
        # Extract JSON from response
        start = text.find("{")
        end = text.rfind("}") + 1
        schedule_raw = json.loads(text[start:end])
        return {str(k): v for k, v in schedule_raw.items()}
    except Exception as e:
        print(f"[warn] Schedule generation failed for {task_id}: {e}. Using ground-truth fallback.")
        # Fallback: only ground-truth tools are available
        fallback: dict[str, list[str]] = {}
        for i, gt_turn in enumerate(ground_truth):
            if isinstance(gt_turn, list):
                calls = [c.get("name", "") for c in gt_turn if isinstance(c, dict) and c.get("name")]
            else:
                calls = []
            fallback[str(i)] = calls
        return fallback


async def generate_schedules(
    tasks: list[dict],
    model,
) -> dict[str, dict[str, list[str]]]:
    """Generate tool_availability_schedule for all tasks, with caching."""
    cache = _load_schedule_cache()
    updated = False

    for task in tasks:
        tid = task["id"]
        if tid in cache:
            continue
        print(f"[schedule] Generating schedule for {tid}...")
        schedule = await _generate_schedule_for_task(
            tid,
            task["functions"],
            task["turns"],
            task["ground_truth"],
            model,
        )
        cache[tid] = schedule
        updated = True

    if updated:
        _save_schedule_cache(cache)
        print(f"[schedule] Saved {len(cache)} schedules to cache")

    return cache


# ── Output generation ─────────────────────────────────────────────────────────

def extract_gt_tool_names(ground_truth: list) -> list[str | None]:
    """Extract one ground-truth tool name per turn."""
    result = []
    for gt in ground_truth:
        if isinstance(gt, list) and gt:
            first = gt[0]
            result.append(first.get("name") if isinstance(first, dict) else None)
        else:
            result.append(None)
    return result


def build_output_task(
    task: dict,
    schedule: dict[str, list[str]],
    target_total: int,
) -> dict:
    """Build one output JSONL record."""
    from .tools import FILLER_TOOLS, get_filler_names

    func_names = {f["name"] for f in task["functions"]}
    filler_names = [t.name for t in FILLER_TOOLS if t.name not in func_names]
    n_filler = max(0, target_total - len(task["functions"]))

    return {
        "id": task["id"],
        "turns": task["turns"],
        "ground_truth_tools": extract_gt_tool_names(task["ground_truth"]),
        "functions": task["functions"],
        "filler_tool_names": filler_names[:n_filler],
        "tool_availability_schedule": schedule,
    }


def save_jsonl(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    print(f"[output] Saved {len(records)} tasks to {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    import core.providers  # register providers

    # Claude Opus 4.6 via Bedrock for schedule generation
    from core.types import Model, ModelCost
    opus_model = Model(
        id="us.anthropic.claude-opus-4-6-20251101-v1:0",
        name="Claude-Opus-4.6",
        provider="bedrock",
        cost=ModelCost(input=15.0, output=75.0, cache_read=1.5, cache_write=18.75),
    )

    tasks_dir = EXPERIMENT_DIR / "tasks"
    output_path = EXPERIMENT_DIR / args.output

    # 1. Load data
    print("[step 1] Loading BFCL data...")
    data = load_bfcl_data(tasks_dir)
    print(f"  Loaded {len(data)} raw entries")

    # 2. Filter
    print(f"[step 2] Filtering (min_tools={args.min_tools}, min_turns={args.min_turns}, n={args.num_tasks})...")
    tasks = filter_tasks(data, args.min_tools, args.min_turns, args.num_tasks)
    print(f"  Selected {len(tasks)} tasks")
    if not tasks:
        print("[error] No tasks matched filters. Check BFCL data format.")
        sys.exit(1)

    # 3. Generate schedules
    print("[step 3] Generating tool_availability_schedule with Claude Opus 4.6...")
    schedules = await generate_schedules(tasks, opus_model)

    # 4. Build output
    print("[step 4] Building output JSONL...")
    records = []
    for task in tasks:
        schedule = schedules.get(task["id"], {})
        record = build_output_task(task, schedule, args.target_total)
        records.append(record)

    # 5. Save
    save_jsonl(records, output_path)
    print(f"\n[done] {len(records)} tasks ready at {output_path}")
    print("Example task IDs:", [r["id"] for r in records[:3]])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--num-tasks", type=int, default=10)
    parser.add_argument("--min-tools", type=int, default=5)
    parser.add_argument("--min-turns", type=int, default=3)
    parser.add_argument("--target-total", type=int, default=50)
    parser.add_argument("--output", default="tasks/bfcl_multi_turn.jsonl")
    asyncio.run(main(parser.parse_args()))
