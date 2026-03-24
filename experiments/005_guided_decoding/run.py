"""Experiment 005: Guided Decoding — Structural Guarantee vs Semantic Quality.

Usage:
    python -m experiments.005_guided_decoding.run [--runs N] [--base-url URL]

Compares three strategies for extracting structured JSON from natural language:
- free:   no schema constraint
- prompt: schema in system prompt only
- guided: response_format json_schema (xgrammar hard masking)

All conditions use /no_think suffix to disable Qwen3 chain-of-thought,
isolating the effect of structural constraint from thinking suppression.
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
import urllib.request

import core.providers  # noqa: F401 — registers providers

EXPERIMENT_DIR = Path(__file__).parent
RESULTS_DIR = EXPERIMENT_DIR / "results"
TASKS_FILE = EXPERIMENT_DIR / "tasks.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SCHEMA = {
    "type": "object",
    "required": ["name", "age", "role", "location", "skills", "available"],
    "properties": {
        "name":      {"type": "string"},
        "age":       {"type": "integer"},
        "role":      {"type": "string", "enum": ["engineer", "designer", "manager", "analyst", "other"]},
        "location":  {"type": "string"},
        "skills":    {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "available": {"type": "boolean"},
    },
}

SCHEMA_STR = json.dumps(SCHEMA)

STRATEGY_NAMES = ["free", "prompt", "guided"]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FieldResult:
    extracted: Any
    expected: Any
    correct: bool | None    # None = judgment deferred to LLM judge
    judge_verdict: str = "" # "correct" / "hallucination" / "reasonable" / "unreasonable"
    judge_reason: str = ""


@dataclass
class TaskResult:
    task_id: str
    group: str
    subgroup: str
    strategy: str
    run_id: int
    raw_response: str = ""
    has_think: bool = False
    parse_success: bool = False
    schema_valid: bool = False
    schema_errors: list[str] = field(default_factory=list)
    parsed: dict = field(default_factory=dict)
    field_results: dict[str, FieldResult] = field(default_factory=dict)
    latency_s: float = 0.0
    output_tokens: int = 0
    error: str | None = None


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

def load_tasks() -> list[dict]:
    tasks = []
    with open(TASKS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks


# ---------------------------------------------------------------------------
# Schema validation (manual, no dependency)
# ---------------------------------------------------------------------------

VALID_ROLES = {"engineer", "designer", "manager", "analyst", "other"}

def validate_schema(obj: dict) -> tuple[bool, list[str]]:
    errors = []
    for req in ["name", "age", "role", "location", "skills", "available"]:
        if req not in obj:
            errors.append(f"缺少字段: {req}")
    if "name" in obj and not isinstance(obj["name"], str):
        errors.append("name 应为 string")
    if "age" in obj and not isinstance(obj["age"], int):
        errors.append(f"age 应为 integer, 实际: {type(obj['age']).__name__}")
    if "role" in obj and obj["role"] not in VALID_ROLES:
        errors.append(f"role '{obj['role']}' 不在枚举值中")
    if "location" in obj and not isinstance(obj["location"], str):
        errors.append("location 应为 string")
    if "skills" in obj:
        if not isinstance(obj["skills"], list):
            errors.append("skills 应为 array")
        elif len(obj["skills"]) > 3:
            errors.append(f"skills 超过 maxItems=3 (实际 {len(obj['skills'])})")
        elif not all(isinstance(s, str) for s in obj["skills"]):
            errors.append("skills 元素应为 string")
    if "available" in obj and not isinstance(obj["available"], bool):
        errors.append(f"available 应为 boolean, 实际: {type(obj['available']).__name__}")
    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Field-level accuracy (no LLM needed for Group A + range checks)
# ---------------------------------------------------------------------------

def check_fields_without_judge(parsed: dict, task: dict) -> dict[str, FieldResult]:
    expected = task.get("expected", {})
    results: dict[str, FieldResult] = {}

    for fname in ["name", "age", "role", "location", "skills", "available"]:
        extracted = parsed.get(fname)
        exp = expected.get(fname)

        # Group C: expected is None → hallucination check (deferred to judge)
        if exp is None:
            results[fname] = FieldResult(extracted=extracted, expected=None, correct=None)
            continue

        # age_range for B3
        if fname == "age" and "acceptable_age_range" in task:
            lo, hi = task["acceptable_age_range"]
            ok = isinstance(extracted, int) and lo <= extracted <= hi
            results[fname] = FieldResult(extracted=extracted, expected=f"range [{lo},{hi}]", correct=ok)
            continue

        # acceptable_role for B1/B102
        if fname == "role" and "acceptable_role" in task:
            ok = extracted in task["acceptable_role"]
            results[fname] = FieldResult(extracted=extracted, expected=task["acceptable_role"], correct=ok)
            continue

        # ambiguous field → deferred to LLM judge
        if fname in task.get("ambiguous_fields", []):
            results[fname] = FieldResult(extracted=extracted, expected=exp, correct=None)
            continue

        # exact match
        if fname == "skills":
            ok = isinstance(extracted, list) and sorted(extracted) == sorted(exp or [])
        else:
            ok = extracted == exp
        results[fname] = FieldResult(extracted=extracted, expected=exp, correct=ok)

    return results


# ---------------------------------------------------------------------------
# Single LLM call (direct HTTP, no agent loop needed)
# ---------------------------------------------------------------------------

def _build_payload(prompt_text: str, strategy: str, base_model_id: str) -> dict:
    user_msg = prompt_text + " /no_think"

    if strategy == "free":
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user",   "content": user_msg},
        ]
        payload: dict = {"model": base_model_id, "messages": messages,
                         "max_tokens": 512, "temperature": 0.0}

    elif strategy == "prompt":
        sys = (
            "从文本中提取信息，输出符合以下 schema 的纯 JSON（无 markdown，无额外说明）：\n"
            + SCHEMA_STR
        )
        messages = [
            {"role": "system", "content": sys},
            {"role": "user",   "content": user_msg},
        ]
        payload = {"model": base_model_id, "messages": messages,
                   "max_tokens": 512, "temperature": 0.0}

    else:  # guided
        messages = [
            {"role": "system", "content": "从文本中提取结构化信息。"},
            {"role": "user",   "content": user_msg},
        ]
        payload = {
            "model": base_model_id, "messages": messages,
            "max_tokens": 512, "temperature": 0.0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "person_profile", "schema": SCHEMA, "strict": True},
            },
        }

    return payload


def _http_post(url: str, payload: dict, timeout: int = 30) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


async def call_llm(base_url: str, model_id: str, payload: dict) -> tuple[str, int, float]:
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
# LLM judge for Group B (ambiguous) and Group C (missing)
# ---------------------------------------------------------------------------

async def llm_judge_field(
    base_url: str, model_id: str,
    source_text: str, field_name: str,
    extracted_value: Any, expected_value: Any,
    is_hallucination_check: bool,
) -> tuple[str, str]:
    """Returns (verdict, reason). verdict ∈ {reasonable, unreasonable, hallucination, grounded}."""
    if is_hallucination_check:
        prompt = (
            f"原文：「{source_text}」\n\n"
            f"模型将字段 `{field_name}` 提取为：{json.dumps(extracted_value, ensure_ascii=False)}\n\n"
            f"原文中是否有足够信息来得出这个具体值？\n"
            f"只回答「有依据」或「幻觉」，然后用一句话说明原因。"
        )
    else:
        prompt = (
            f"原文：「{source_text}」\n\n"
            f"模型将字段 `{field_name}` 提取为：{json.dumps(extracted_value, ensure_ascii=False)}\n"
            f"参考答案为：{json.dumps(expected_value, ensure_ascii=False)}\n\n"
            f"基于原文，模型的提取结果是否合理？\n"
            f"只回答「合理」或「不合理」，然后用一句话说明原因。"
        )

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "你是一个客观的信息提取评估员。"},
            {"role": "user",   "content": prompt + " /no_think"},
        ],
        "max_tokens": 128,
        "temperature": 0.0,
    }
    url = base_url.rstrip("/") + "/chat/completions"
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _http_post, url, payload, 20)
        raw = result["choices"][0]["message"]["content"] or ""
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        if is_hallucination_check:
            verdict = "grounded" if "有依据" in raw else "hallucination"
        else:
            verdict = "reasonable" if "合理" in raw and "不合理" not in raw else "unreasonable"
        return verdict, raw
    except Exception as e:
        return "error", str(e)


# ---------------------------------------------------------------------------
# Run a single task
# ---------------------------------------------------------------------------

async def run_task(
    task: dict,
    strategy: str,
    run_id: int,
    base_url: str,
    model_id: str,
) -> TaskResult:
    result = TaskResult(
        task_id=task["id"],
        group=task["group"],
        subgroup=task["subgroup"],
        strategy=strategy,
        run_id=run_id,
    )
    payload = _build_payload(task["prompt"], strategy, model_id)

    try:
        content, out_tokens, latency = await call_llm(base_url, model_id, payload)
        result.raw_response = content
        result.latency_s = latency
        result.output_tokens = out_tokens
        result.has_think = "<think>" in content

        # Strip think block before parsing
        stripped = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        # For free strategy: search for JSON object anywhere in response
        if strategy == "free":
            m = re.search(r"\{[\s\S]*\}", stripped)
            stripped = m.group(0) if m else stripped

        # Parse JSON
        try:
            result.parsed = json.loads(stripped)
            result.parse_success = True
        except json.JSONDecodeError:
            result.parse_success = False
            return result

        # Schema validation
        result.schema_valid, result.schema_errors = validate_schema(result.parsed)

        # Field-level accuracy (no LLM needed)
        result.field_results = check_fields_without_judge(result.parsed, task)

        # LLM judge for deferred fields
        judge_tasks = []
        for fname, fr in result.field_results.items():
            if fr.correct is None:
                is_halluc = fr.expected is None
                judge_tasks.append((fname, fr, is_halluc))

        if judge_tasks:
            judge_coroutines = [
                llm_judge_field(
                    base_url, model_id,
                    task["prompt"], fname,
                    fr.extracted, fr.expected,
                    is_halluc,
                )
                for fname, fr, is_halluc in judge_tasks
            ]
            verdicts = await asyncio.gather(*judge_coroutines)
            for (fname, fr, _), (verdict, reason) in zip(judge_tasks, verdicts):
                fr.judge_verdict = verdict
                fr.judge_reason = reason
                if fr.expected is None:
                    fr.correct = verdict == "grounded"
                else:
                    fr.correct = verdict == "reasonable"

    except Exception as e:
        result.error = str(e)
        logger.error("Task %s / strategy %s failed: %s", task["id"], strategy, e)

    return result


# ---------------------------------------------------------------------------
# Run all tasks for one strategy
# ---------------------------------------------------------------------------

async def run_strategy(
    tasks: list[dict],
    strategy: str,
    run_id: int,
    base_url: str,
    model_id: str,
    concurrency: int = 4,
) -> list[TaskResult]:
    sem = asyncio.Semaphore(concurrency)

    async def bounded(task):
        async with sem:
            r = await run_task(task, strategy, run_id, base_url, model_id)
            ok = "OK" if r.parse_success and r.schema_valid else ("PARSE_FAIL" if not r.parse_success else "SCHEMA_FAIL")
            logger.info("[Run%d %s] %s: %s (%.2fs)", run_id, strategy, task["id"], ok, r.latency_s)
            return r

    return list(await asyncio.gather(*[bounded(t) for t in tasks]))


# ---------------------------------------------------------------------------
# Report (Chinese)
# ---------------------------------------------------------------------------

def _rate(results: list[TaskResult], pred) -> str:
    total = len(results)
    if total == 0:
        return "N/A"
    n = sum(1 for r in results if pred(r))
    return f"{n}/{total} ({n/total:.0%})"


def generate_report(all_results: list[TaskResult]) -> str:
    by_strategy: dict[str, list[TaskResult]] = {}
    for r in all_results:
        by_strategy.setdefault(r.strategy, []).append(r)

    def avg(vals):
        return sum(vals) / len(vals) if vals else 0.0

    lines = [
        "# 实验 005：Guided Decoding — 结构保证 vs 语义质量\n",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        "模型：Qwen3-8B（/no_think 模式），30 个任务，3 个策略\n",
        "---\n",
    ]

    # --- H1: 结构正确性 ---
    lines.append("## H1：结构正确性\n")
    lines.append("| 策略   | JSON 解析成功率 | Schema 验证通过率 | 平均延迟 | 平均输出 token |")
    lines.append("|--------|----------------|------------------|----------|----------------|")
    for name in STRATEGY_NAMES:
        rs = by_strategy.get(name, [])
        parse_r = _rate(rs, lambda r: r.parse_success)
        schema_r = _rate(rs, lambda r: r.schema_valid)
        lats = [r.latency_s for r in rs if r.error is None]
        toks = [r.output_tokens for r in rs if r.error is None]
        lines.append(
            f"| {name:6s} | {parse_r:14s} | {schema_r:16s} | "
            f"{avg(lats):5.2f}s   | {avg(toks):14.0f} |"
        )

    # --- H2/H3/H4: 按子组字段准确率 ---
    lines.append("\n## H2–H4：各子组字段准确率\n")

    subgroup_labels = {
        "clear":              "A  清晰 case（精确匹配）",
        "role_ambiguity":     "B1 role 歧义（LLM judge）",
        "available_ambiguity":"B2 available 歧义（LLM judge）",
        "age_ambiguity":      "B3 age 近似（范围匹配）",
    }
    focus_fields = {
        "clear":               ["name", "age", "role", "location", "skills", "available"],
        "role_ambiguity":      ["role"],
        "available_ambiguity": ["available"],
        "age_ambiguity":       ["age"],
    }

    for sg, label in subgroup_labels.items():
        lines.append(f"\n### {label}\n")
        lines.append("| 策略   | " + " | ".join(f"{f:10s}" for f in focus_fields[sg]) + " |")
        lines.append("|--------|" + "------------|" * len(focus_fields[sg]))
        for name in STRATEGY_NAMES:
            rs = [r for r in by_strategy.get(name, []) if r.subgroup == sg]
            cells = []
            for fname in focus_fields[sg]:
                frs = [r.field_results[fname] for r in rs if fname in r.field_results]
                scored = [fr for fr in frs if fr.correct is not None]
                if not scored:
                    cells.append("N/A       ")
                else:
                    n_ok = sum(1 for fr in scored if fr.correct)
                    cells.append(f"{n_ok}/{len(scored)} ({n_ok/len(scored):.0%})  ")
            lines.append("| " + f"{name:6s} | " + " | ".join(cells) + " |")

    # --- H5: 缺失信息处理（幻觉检测）---
    lines.append("\n## H5：缺失信息处理（Group C 幻觉率）\n")
    lines.append("| 策略   | 子组             | 缺失字段    | 幻觉次数 / 总次数 |")
    lines.append("|--------|------------------|------------|-------------------|")
    for sg, missing_field in [("missing_age", "age"), ("missing_available", "available")]:
        for name in STRATEGY_NAMES:
            rs = [r for r in by_strategy.get(name, []) if r.subgroup == sg]
            frs = [r.field_results[missing_field]
                   for r in rs if missing_field in r.field_results]
            judged = [fr for fr in frs if fr.judge_verdict]
            n_halluc = sum(1 for fr in judged if fr.judge_verdict == "hallucination")
            total = len(judged) if judged else len(frs)
            lines.append(
                f"| {name:6s} | {sg:16s} | {missing_field:10s} | "
                f"{n_halluc}/{total}（{n_halluc/total:.0%} 幻觉）    |"
                if total > 0 else
                f"| {name:6s} | {sg:16s} | {missing_field:10s} | N/A               |"
            )

    # --- H6: 延迟对比 ---
    lines.append("\n## H6：延迟对比（/no_think 模式）\n")
    lines.append("| 策略   | 平均延迟 | 最小延迟 | 最大延迟 |")
    lines.append("|--------|----------|----------|----------|")
    for name in STRATEGY_NAMES:
        lats = [r.latency_s for r in by_strategy.get(name, []) if r.error is None]
        if lats:
            lines.append(
                f"| {name:6s} | {avg(lats):5.2f}s   | {min(lats):5.2f}s   | {max(lats):5.2f}s   |"
            )

    # --- 假设验证小结 ---
    lines.append("\n## 假设验证小结\n")
    lines.append("| 假设 | 内容                                     | 验证结果 |")
    lines.append("|------|------------------------------------------|----------|")
    lines.append("| H1   | guided 100% 结构合法                     | 待确认   |")
    lines.append("| H2   | Group A 三策略语义准确率相当              | 待确认   |")
    lines.append("| H3   | Group B1 guided role 准确率低于 prompt   | 待确认   |")
    lines.append("| H4   | Group B2 available 策略间差异            | 待确认   |")
    lines.append("| H5   | Group C guided 幻觉率高于 prompt         | 待确认   |")
    lines.append("| H6   | /no_think 后三策略延迟无明显差异          | 待确认   |")

    # --- 每任务详情 ---
    lines.append("\n## 各任务详情（所有策略，第 1 轮）\n")
    lines.append("| 任务 ID | 子组              | 策略   | 解析 | Schema | 延迟  |")
    lines.append("|---------|-------------------|--------|------|--------|-------|")
    tasks_seen = {}
    for r in all_results:
        if r.run_id != 1:
            continue
        parse_mark = "✓" if r.parse_success else "✗"
        schema_mark = "✓" if r.schema_valid else "✗"
        lines.append(
            f"| {r.task_id:7s} | {r.subgroup:17s} | {r.strategy:6s} | "
            f"{parse_mark:4s} | {schema_mark:6s} | {r.latency_s:4.2f}s |"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 005: Guided Decoding")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--base-url", default="http://localhost:8001/v1")
    parser.add_argument("--model-id", default="Qwen/Qwen3-8B")
    parser.add_argument("--strategies", nargs="+", default=STRATEGY_NAMES)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    tasks = load_tasks()
    logger.info("加载 %d 个任务", len(tasks))

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_results: list[TaskResult] = []

    for run_id in range(1, args.runs + 1):
        for strategy in args.strategies:
            logger.info("=== Run %d / 策略: %s ===", run_id, strategy)
            results = await run_strategy(
                tasks, strategy, run_id,
                args.base_url, args.model_id, args.concurrency,
            )
            all_results.extend(results)

            out_path = RESULTS_DIR / f"{strategy}_run{run_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump([asdict(r) for r in results], f, indent=2, ensure_ascii=False)
            logger.info("已保存: %s", out_path)

    report = generate_report(all_results)
    report_path = RESULTS_DIR / "report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("报告已保存: %s", report_path)
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(main())
