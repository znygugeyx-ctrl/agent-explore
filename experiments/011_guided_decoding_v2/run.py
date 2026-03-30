"""Experiment 011: Guided Decoding — Task Complexity × Enum Scale.

Compares guided decoding (xgrammar) vs prompt-only across:
- Track 1: GSM8K math reasoning (3 conditions: prompt_nothink, prompt_think, guided_nothink)
- Track 2: Classification with 5/28/77 enum values (2 conditions: prompt_nothink, guided_nothink)

Usage:
    python -m experiments.011_guided_decoding_v2.run --pilot
    python -m experiments.011_guided_decoding_v2.run --track 1 --model Qwen/Qwen3-8B
    python -m experiments.011_guided_decoding_v2.run --track all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .schemas import SCHEMAS, LABELS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EXPERIMENT_DIR = Path(__file__).parent
TASKS_DIR = EXPERIMENT_DIR / "tasks"
RESULTS_DIR = EXPERIMENT_DIR / "results"

# All tracks now use the same 3 conditions
ALL_CONDITIONS = ["prompt_nothink", "prompt_think", "guided_nothink"]

TRACK1_DATASETS = ["gsm8k"]
TRACK2_DATASETS = ["banking77"]  # Simplified: only 77-enum
TRACK3_DATASETS = ["fewnerd"]
TRACK4_DATASETS = ["recipe"]

# Observer integration
_OBSERVER_URL: str = ""


def _emit_observer(event: dict) -> None:
    """Fire-and-forget POST to observer. Fails silently."""
    if not _OBSERVER_URL:
        return
    try:
        data = json.dumps(event, ensure_ascii=False).encode()
        req = urllib.request.Request(
            _OBSERVER_URL.rstrip("/") + "/api/events",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TaskResult:
    task_id: str
    dataset: str
    condition: str
    model: str
    difficulty: str
    raw_response: str = ""
    has_think: bool = False
    parsed_answer: Any = None
    expected_answer: Any = None
    correct: bool = False
    parse_success: bool = False
    structure_valid: bool = False
    content_correct_fallback: bool = False  # correct via fallback extraction
    entity_f1: float | None = None  # NER only
    latency_s: float = 0.0
    output_tokens: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

def load_tasks(dataset: str) -> list[dict]:
    path = TASKS_DIR / f"{dataset}.jsonl"
    tasks = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks


# ---------------------------------------------------------------------------
# System prompts — identical across conditions (only response_format differs)
# ---------------------------------------------------------------------------

def _system_prompt_gsm8k() -> str:
    return 'Solve the math problem. Respond with JSON only: {"answer": <integer>}'


def _system_prompt_classification(dataset: str) -> str:
    labels = LABELS[dataset]
    labels_str = ", ".join(labels)
    return (
        f"Classify the text into one of these categories: {labels_str}\n"
        f'Respond with JSON only: {{"label": "<category>"}}'
    )


def _system_prompt_recipe() -> str:
    return (
        'Parse the recipe into structured JSON.\n'
        'Respond with JSON only: {"recipe_name": "...", "servings": <int>, '
        '"ingredients": [{"food": "...", "quantity": <number>, "unit": "..."}], '
        '"cuisine_type": "...", "diet_labels": ["..."]}'
    )


def _system_prompt_ner() -> str:
    labels = LABELS["fewnerd"]
    labels_str = "|".join(labels)
    return (
        'Extract all named entities from the text.\n'
        f'Respond with JSON only: {{"entities": [{{"text": "<entity>", "type": "{labels_str}"}}]}}\n'
        'If no entities, return {"entities": []}.'
    )


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------

def _build_payload(
    task: dict,
    condition: str,
    model_id: str,
    max_tokens: int = 16384,
) -> dict:
    dataset = task["dataset"]

    # System prompt — same for all conditions within a dataset
    if dataset == "gsm8k":
        sys_prompt = _system_prompt_gsm8k()
    elif dataset == "fewnerd":
        sys_prompt = _system_prompt_ner()
    elif dataset == "recipe":
        sys_prompt = _system_prompt_recipe()
    else:
        sys_prompt = _system_prompt_classification(dataset)

    # User message — append /no_think unless prompt_think
    user_text = task["prompt"]
    if condition != "prompt_think":
        user_text += " /no_think"

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_text},
    ]

    payload: dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }

    # Guided decoding: add response_format
    if condition == "guided_nothink":
        schema = SCHEMAS[dataset]
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": f"{dataset}_output",
                "schema": schema,
                "strict": True,
            },
        }

    return payload


# ---------------------------------------------------------------------------
# Answer extraction
# ---------------------------------------------------------------------------

def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_gsm8k_answer(text: str, condition: str) -> int | None:
    """Extract integer answer from model response.

    Three-stage: JSON parse → regex last number → None.
    """
    cleaned = _strip_think(text)

    # Stage 1: try JSON parse
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            if "answer" in obj and isinstance(obj["answer"], (int, float)):
                return int(obj["answer"])
        except (json.JSONDecodeError, ValueError):
            pass

    # Stage 2: fallback — last number in text (after stripping think)
    numbers = re.findall(r"-?[\d,]+", cleaned)
    if numbers:
        try:
            return int(numbers[-1].replace(",", ""))
        except ValueError:
            pass

    return None


def _extract_classification_answer(text: str) -> str | None:
    """Extract label from model response."""
    cleaned = _strip_think(text)

    # Stage 1: try JSON parse
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            if "label" in obj:
                return str(obj["label"])
        except json.JSONDecodeError:
            pass

    # Stage 2: fallback — look for label in bare text
    # This is less reliable; mark as parse failure
    return None


def _extract_ner_answer(text: str) -> list[dict] | None:
    """Extract entity list from model response.

    Returns list of {"text": str, "type": str} or None on failure.
    """
    cleaned = _strip_think(text)

    # Stage 1: try JSON parse
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            if "entities" in obj and isinstance(obj["entities"], list):
                return [
                    {"text": e.get("text", ""), "type": e.get("type", "")}
                    for e in obj["entities"]
                    if isinstance(e, dict)
                ]
        except json.JSONDecodeError:
            pass

    # Stage 2: fallback — try to fix broken JSON (missing brackets)
    try:
        # Try adding missing closing brackets
        for suffix in ["}", "]}", "]}"]  :
            try:
                obj = json.loads(cleaned + suffix)
                if "entities" in obj and isinstance(obj["entities"], list):
                    return [
                        {"text": e.get("text", ""), "type": e.get("type", "")}
                        for e in obj["entities"]
                        if isinstance(e, dict)
                    ]
            except (json.JSONDecodeError, ValueError):
                continue
    except Exception:
        pass

    # Stage 3: regex fallback — extract "text"/"type" pairs
    pairs = re.findall(
        r'"text"\s*:\s*"([^"]+)"\s*,\s*"type"\s*:\s*"([^"]+)"', cleaned
    )
    if pairs:
        return [{"text": t, "type": tp} for t, tp in pairs]

    return None


def _validate_ner_schema(text: str) -> bool:
    """Check if response is valid JSON matching the NER schema."""
    cleaned = _strip_think(text)
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if not json_match:
        return False
    try:
        obj = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return False
    if not isinstance(obj.get("entities"), list):
        return False
    valid_types = set(LABELS.get("fewnerd", []))
    for e in obj["entities"]:
        if not isinstance(e, dict):
            return False
        if "text" not in e or "type" not in e:
            return False
        if not isinstance(e["text"], str) or e["type"] not in valid_types:
            return False
    return True


def _validate_structure(text: str, dataset: str) -> bool:
    """Validate JSON structure against expected schema for any dataset."""
    cleaned = _strip_think(text)
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if not json_match:
        return False
    try:
        obj = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return False

    if dataset == "gsm8k":
        return "answer" in obj and isinstance(obj["answer"], (int, float))
    elif dataset == "fewnerd":
        return _validate_ner_schema(text)
    elif dataset == "recipe":
        return _validate_recipe_schema(text)
    else:
        # Classification
        if "label" not in obj:
            return False
        label_val = str(obj["label"])
        valid_labels = LABELS.get(dataset, [])
        return label_val in valid_labels if valid_labels else isinstance(label_val, str)


def _compute_entity_f1(
    predicted: list[dict], expected: list[dict],
) -> tuple[float, float, float]:
    """Compute entity-level precision, recall, F1.

    Entities matched by (text.lower(), type) pairs, ignoring order.
    """
    pred_set = {(e["text"].lower().strip(), e["type"]) for e in predicted}
    gold_set = {(e["text"].lower().strip(), e["type"]) for e in expected}

    if not pred_set and not gold_set:
        return 1.0, 1.0, 1.0
    if not pred_set or not gold_set:
        return 0.0, 0.0, 0.0

    tp = len(pred_set & gold_set)
    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(gold_set) if gold_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _classification_fallback_extract(text: str, dataset: str) -> str | None:
    """Fallback: try to find a valid label in raw text for classification."""
    cleaned = _strip_think(text).lower()
    valid_labels = LABELS.get(dataset, [])
    # Try exact match of any label in text
    for label in valid_labels:
        if label.lower() in cleaned:
            return label
    return None


def _extract_recipe_answer(text: str) -> dict | None:
    """Extract recipe structured data from model response."""
    cleaned = _strip_think(text)

    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            if "ingredients" in obj and isinstance(obj["ingredients"], list):
                return obj
        except json.JSONDecodeError:
            pass

    # Fallback: try fixing broken JSON
    for suffix in ["}", "]}", "]}"]  :
        try:
            obj = json.loads(cleaned + suffix)
            if "ingredients" in obj:
                return obj
        except (json.JSONDecodeError, ValueError):
            continue

    return None


def _validate_recipe_schema(text: str) -> bool:
    """Check if response matches recipe schema."""
    cleaned = _strip_think(text)
    json_match = re.search(r"\{[\s\S]*\}", cleaned)
    if not json_match:
        return False
    try:
        obj = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return False
    required = ["recipe_name", "servings", "ingredients", "cuisine_type", "diet_labels"]
    for field in required:
        if field not in obj:
            return False
    if not isinstance(obj["ingredients"], list):
        return False
    if not isinstance(obj["diet_labels"], list):
        return False
    for ing in obj["ingredients"]:
        if not isinstance(ing, dict):
            return False
        if "food" not in ing or "quantity" not in ing or "unit" not in ing:
            return False
    return True


def _evaluate_recipe(parsed: dict, expected: dict) -> tuple[float, dict]:
    """Evaluate recipe extraction. Returns (overall_score, field_scores)."""
    scores = {}

    # recipe_name: exact match
    scores["recipe_name"] = 1.0 if parsed.get("recipe_name", "").strip().lower() == expected["recipe_name"].strip().lower() else 0.0

    # servings: exact match
    try:
        scores["servings"] = 1.0 if int(parsed.get("servings", -1)) == expected["servings"] else 0.0
    except (ValueError, TypeError):
        scores["servings"] = 0.0

    # cuisine_type: exact match (case-insensitive)
    scores["cuisine_type"] = 1.0 if str(parsed.get("cuisine_type", "")).strip().lower() == expected["cuisine_type"].strip().lower() else 0.0

    # diet_labels: set F1
    pred_diet = {str(d).strip().lower() for d in parsed.get("diet_labels", [])}
    gold_diet = {str(d).strip().lower() for d in expected["diet_labels"]}
    if pred_diet or gold_diet:
        tp = len(pred_diet & gold_diet)
        p = tp / len(pred_diet) if pred_diet else 0
        r = tp / len(gold_diet) if gold_diet else 0
        scores["diet_labels"] = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    else:
        scores["diet_labels"] = 1.0

    # ingredients: food-level F1
    pred_foods = {ing.get("food", "").strip().lower() for ing in parsed.get("ingredients", []) if isinstance(ing, dict)}
    gold_foods = {ing["food"].strip().lower() for ing in expected["ingredients"]}
    if pred_foods or gold_foods:
        tp = len(pred_foods & gold_foods)
        p = tp / len(pred_foods) if pred_foods else 0
        r = tp / len(gold_foods) if gold_foods else 0
        scores["ingredients"] = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    else:
        scores["ingredients"] = 1.0

    # Overall: weighted average (ingredients most important)
    overall = (
        scores["recipe_name"] * 0.1 +
        scores["servings"] * 0.1 +
        scores["ingredients"] * 0.5 +
        scores["cuisine_type"] * 0.15 +
        scores["diet_labels"] * 0.15
    )

    return overall, scores


# ---------------------------------------------------------------------------
# HTTP calls
# ---------------------------------------------------------------------------

def _http_post(url: str, payload: dict, timeout: int = 120, retries: int = 3) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except (ConnectionRefusedError, urllib.error.URLError, OSError) as e:
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                logger.warning("Retry %d/%d after %ds: %s", attempt + 1, retries, wait, e)
                time.sleep(wait)
            else:
                raise


async def _call_llm(base_url: str, payload: dict) -> tuple[str, int, float]:
    """Returns (content, output_tokens, latency_s)."""
    url = base_url.rstrip("/") + "/chat/completions"
    t0 = time.time()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _http_post, url, payload)
    latency = time.time() - t0
    content = result["choices"][0]["message"]["content"] or ""
    out_tokens = result.get("usage", {}).get("completion_tokens", 0)
    return content, out_tokens, latency


# ---------------------------------------------------------------------------
# Single task execution
# ---------------------------------------------------------------------------

async def run_single_task(
    task: dict,
    condition: str,
    model_id: str,
    base_url: str,
    max_tokens: int = 16384,
) -> TaskResult:
    dataset = task["dataset"]
    result = TaskResult(
        task_id=task["id"],
        dataset=dataset,
        condition=condition,
        model=model_id.split("/")[-1],
        difficulty=task.get("difficulty", "unknown"),
        expected_answer=task["expected_answer"],
    )

    payload = _build_payload(task, condition, model_id, max_tokens=max_tokens)

    # Observer: emit context
    model_short = model_id.split("/")[-1]
    obs_run_id = f"011_{model_short}"
    obs_task_id = f"{task['id']}_{condition}"
    _emit_observer({
        "ts": time.time(), "run_id": obs_run_id, "task_id": obs_task_id,
        "type": "context", "turn": 1,
        "data": {
            "system_prompt": payload["messages"][0]["content"],
            "messages": payload["messages"],
            "tools": [], "tool_count": 0,
        },
    })

    try:
        content, out_tokens, latency = await _call_llm(base_url, payload)
        result.raw_response = content
        result.latency_s = latency
        result.output_tokens = out_tokens
        result.has_think = "<think>" in content

        # Observer: emit response
        _emit_observer({
            "ts": time.time(), "run_id": obs_run_id, "task_id": obs_task_id,
            "type": "response", "turn": 1,
            "data": {
                "content": [{"type": "text", "text": content[:500]}],
                "usage": {"output": out_tokens},
                "latency_s": latency,
            },
        })

        # Validate structure (2×2 matrix: structure × content)
        result.structure_valid = _validate_structure(content, dataset)

        # Extract answer
        if dataset == "gsm8k":
            parsed = _extract_gsm8k_answer(content, condition)
            result.parsed_answer = parsed
            result.parse_success = parsed is not None
            if parsed is not None:
                result.correct = parsed == task["expected_answer"]
            # Fallback content check (already uses regex fallback)
            result.content_correct_fallback = result.correct

        elif dataset == "fewnerd":
            parsed = _extract_ner_answer(content)
            result.parsed_answer = parsed
            result.parse_success = parsed is not None
            if parsed is not None:
                expected = task["expected_answer"]
                _, _, f1 = _compute_entity_f1(parsed, expected)
                result.entity_f1 = f1
                result.correct = f1 >= 0.8
                result.content_correct_fallback = result.correct
            else:
                result.entity_f1 = 0.0

        elif dataset == "recipe":
            parsed = _extract_recipe_answer(content)
            result.parsed_answer = parsed
            result.parse_success = parsed is not None
            if parsed is not None:
                expected = task["expected_answer"]
                overall, field_scores = _evaluate_recipe(parsed, expected)
                result.correct = overall >= 0.7
                result.content_correct_fallback = result.correct
            else:
                result.content_correct_fallback = False

        else:
            parsed = _extract_classification_answer(content)
            result.parsed_answer = parsed
            result.parse_success = parsed is not None
            if parsed is not None:
                result.correct = (
                    str(parsed).strip().lower()
                    == str(task["expected_answer"]).strip().lower()
                )
                result.content_correct_fallback = result.correct
            else:
                # Fallback: try to find label in raw text
                fallback = _classification_fallback_extract(content, dataset)
                if fallback is not None:
                    result.content_correct_fallback = (
                        fallback.strip().lower()
                        == str(task["expected_answer"]).strip().lower()
                    )

    except Exception as e:
        result.error = str(e)
        logger.error("Task %s / %s failed: %s", task["id"], condition, e)

    # Observer: emit evaluation result
    _emit_observer({
        "ts": time.time(), "run_id": obs_run_id, "task_id": obs_task_id,
        "type": "result", "turn": 1,
        "data": {
            "correct": result.correct,
            "parse_success": result.parse_success,
            "structure_valid": result.structure_valid,
            "content_correct_fallback": result.content_correct_fallback,
            "entity_f1": result.entity_f1,
            "latency_s": result.latency_s,
            "error": result.error,
        },
    })

    return result


# ---------------------------------------------------------------------------
# Run condition with resume support
# ---------------------------------------------------------------------------

async def run_condition(
    tasks: list[dict],
    condition: str,
    model_id: str,
    base_url: str,
    result_path: Path,
    concurrency: int = 4,
    max_tokens: int = 16384,
) -> list[TaskResult]:
    # Load existing results for resume
    existing: dict[str, dict] = {}
    if result_path.exists():
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            existing = {r["task_id"]: r for r in data}
        except Exception:
            pass

    # Filter to pending tasks
    pending = [t for t in tasks if t["id"] not in existing]
    if not pending:
        logger.info("  All %d tasks already completed, skipping", len(tasks))
        return [TaskResult(**{k: v for k, v in r.items() if k != "metadata"})
                for r in existing.values()]

    if existing:
        logger.info("  Resuming: %d done, %d pending", len(existing), len(pending))

    sem = asyncio.Semaphore(concurrency)

    async def bounded(task: dict) -> TaskResult:
        async with sem:
            r = await run_single_task(task, condition, model_id, base_url, max_tokens)
            status = "OK" if r.correct else ("PARSE_FAIL" if not r.parse_success else "WRONG")
            logger.info(
                "  [%s] %s: %s (%.2fs, answer=%s, expected=%s)",
                condition, task["id"], status, r.latency_s,
                r.parsed_answer, task["expected_answer"],
            )
            return r

    new_results = list(await asyncio.gather(*[bounded(t) for t in pending]))

    # Merge with existing, preserving original task order
    result_map = {**existing}
    for r in new_results:
        result_map[r.task_id] = asdict(r)

    all_results_dicts = [result_map[t["id"]] for t in tasks if t["id"] in result_map]

    # Save
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(all_results_dicts, f, indent=2, ensure_ascii=False)

    return new_results


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(results_dir: Path, dataset: str) -> None:
    """Print a quick summary of results for a dataset."""
    files = sorted(results_dir.glob(f"{dataset}/*.json"))
    if not files:
        return

    logger.info("--- %s summary ---", dataset)
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        total = len(data)
        correct = sum(1 for r in data if r.get("correct"))
        parsed = sum(1 for r in data if r.get("parse_success"))
        lats = [r["latency_s"] for r in data if r.get("latency_s")]
        avg_lat = sum(lats) / len(lats) if lats else 0
        logger.info(
            "  %s: %d/%d correct (%.1f%%), %d/%d parsed, avg %.2fs",
            path.stem, correct, total, 100 * correct / total if total else 0,
            parsed, total, avg_lat,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 011: Guided Decoding v2")
    parser.add_argument("--track", choices=["1", "2", "3", "4", "all"], default="all")
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    parser.add_argument("--base-url", default="http://localhost:8001/v1")
    parser.add_argument("--dataset", help="Run only this dataset")
    parser.add_argument("--condition", help="Run only this condition")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=16384, help="Max output tokens")
    parser.add_argument("--pilot", action="store_true", help="Run 10 tasks per dataset")
    parser.add_argument("--observer-url", default="http://localhost:7777", help="Observer URL")
    args = parser.parse_args()

    global _OBSERVER_URL
    _OBSERVER_URL = args.observer_url

    model_id = args.model
    model_short = model_id.split("/")[-1].lower().replace("/", "-")

    # Determine which datasets and conditions to run
    run_plan: list[tuple[str, list[str]]] = []

    if args.dataset:
        # Single dataset
        ds = args.dataset
        conditions = [args.condition] if args.condition else ALL_CONDITIONS
        run_plan.append((ds, conditions))
    else:
        if args.track in ("1", "all"):
            for ds in TRACK1_DATASETS:
                run_plan.append((ds, ALL_CONDITIONS))
        if args.track in ("2", "all"):
            for ds in TRACK2_DATASETS:
                run_plan.append((ds, ALL_CONDITIONS))
        if args.track in ("3", "all"):
            for ds in TRACK3_DATASETS:
                run_plan.append((ds, ALL_CONDITIONS))
        if args.track in ("4", "all"):
            for ds in TRACK4_DATASETS:
                run_plan.append((ds, ALL_CONDITIONS))

    for dataset, conditions in run_plan:
        logger.info("=== Dataset: %s ===", dataset)
        tasks = load_tasks(dataset)

        if args.pilot:
            tasks = tasks[:10]
            logger.info("  Pilot mode: using first 10 tasks")

        for condition in conditions:
            logger.info("--- Condition: %s, Model: %s ---", condition, model_short)
            result_path = RESULTS_DIR / dataset / f"{model_short}_{condition}.json"
            await run_condition(
                tasks, condition, model_id, args.base_url,
                result_path, args.concurrency, args.max_tokens,
            )

        _print_summary(RESULTS_DIR, dataset)


if __name__ == "__main__":
    asyncio.run(main())
