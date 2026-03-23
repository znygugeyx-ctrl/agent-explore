"""对照实验：把 logit_bias 施加在模型"需要"的工具上，观察行为。

Run:
    python -m experiments.002_logit_masking.demo_block_needed
"""

from __future__ import annotations

import asyncio
import json

from openai import AsyncOpenAI
import core.providers  # noqa

BASE_URL  = "http://localhost:8000/v1"
MODEL_ID  = "Qwen/Qwen3-8B"

# 任务需要 calculator + gcd
TASK_PROMPT = (
    "First calculate 2**8 + 2**6 using the calculator tool. "
    "Then find the GCD of that result and 192 using the gcd tool. "
    "Give just the final number."
)

# 从 run1 里直接取已知的 token map（省去重复 tokenize）
TOKEN_MAP: dict[str, list[int]] = {
    "calculator":          [29952, 88821],
    "string_reverse":      [914,   917  ],
    "char_count":          [1161,  1762 ],
    "base_convert":        [2331,  3152 ],
    "caesar_cipher":       [924,   2162 ],
    "temperature_convert": [9315,  34558],
    "gcd":                 [44858, 91289],
    "word_count":          [1158,  3409 ],
}

SEP = "─" * 72

def header(t: str):
    print(f"\n{'━'*72}\n  {t}\n{'━'*72}")

def section(t: str):
    print(f"\n{SEP}\n  {t}\n{SEP}")


async def run_case(
    label: str,
    logit_bias: dict[str, int],
    note: str,
) -> dict[int, dict]:
    """Send the request with a given logit_bias, stream + collect tool calls."""
    from .tools import ALL_TOOLS

    tools_payload = [
        {"type": "function", "function": {
            "name": t.name, "description": t.description, "parameters": t.parameters,
        }}
        for t in ALL_TOOLS
    ]

    client = AsyncOpenAI(base_url=BASE_URL, api_key="no-key")
    params: dict = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": (
                "You are a helpful assistant with access to tools. "
                "Use the appropriate tool for EACH step. "
                "After completing ALL steps, respond with ONLY the final answer."
            )},
            {"role": "user", "content": TASK_PROMPT},
        ],
        "tools": tools_payload,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": 1024,
        "temperature": 0.0,
    }
    if logit_bias:
        params["logit_bias"] = logit_bias

    section(f"CASE: {label}")
    print(f"  Note: {note}")
    if logit_bias:
        print(f"  logit_bias ({len(logit_bias)} entries): {json.dumps(logit_bias)}")
    else:
        print("  logit_bias: (none)")
    print()

    tool_calls: dict[int, dict] = {}
    think_buf = ""
    text_buf  = ""
    in_think  = False
    usage_info: dict = {}

    response = await client.chat.completions.create(**params)
    async for chunk in response:
        if chunk.usage:
            usage_info = {
                "input": chunk.usage.prompt_tokens,
                "output": chunk.usage.completion_tokens,
            }
        choice = chunk.choices[0] if chunk.choices else None
        if not choice:
            continue
        delta = choice.delta
        if delta.content:
            text_buf += delta.content
            # track <think> block separately for display
            for ch in delta.content:
                if text_buf.endswith("<think>"):
                    in_think = True
                if in_think:
                    think_buf += ch
                else:
                    pass
                if text_buf.endswith("</think>"):
                    in_think = False

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls:
                    tool_calls[idx] = {"name": "", "args": ""}
                if tc.function:
                    if tc.function.name:
                        tool_calls[idx]["name"] += tc.function.name
                    if tc.function.arguments:
                        tool_calls[idx]["args"] += tc.function.arguments

    # ── Display results ───────────────────────────────────────────────────
    # Show full think block
    if "<think>" in text_buf and "</think>" in text_buf:
        think_content = text_buf.split("<think>")[1].split("</think>")[0].strip()
        print("  <think> block (full):")
        for line in think_content.splitlines():
            print(f"    {line}")
        print()

    answer_text = text_buf.split("</think>")[-1].strip() if "</think>" in text_buf else text_buf.strip()
    if answer_text:
        print(f"  Final text output: {answer_text!r}")

    print(f"\n  Tool calls attempted ({len(tool_calls)}):")
    if tool_calls:
        for idx, tc in tool_calls.items():
            try:
                args = json.loads(tc["args"])
            except Exception:
                args = tc["args"]
            print(f"    [{idx}] name={tc['name']!r}  args={args}")
    else:
        print("    (none)")

    if usage_info:
        print(f"\n  Token usage: input={usage_info.get('input')}  output={usage_info.get('output')}")

    return tool_calls


def compare(cases: list[tuple[str, dict]]):
    section("COMPARISON SUMMARY")
    print(f"  {'Case':<35} {'Tool calls':<40} {'Verdict'}")
    print(f"  {'-'*35} {'-'*40} {'-'*20}")
    for label, tcs in cases:
        names = [tc["name"] for tc in tcs.values()] if tcs else []
        correct    = sorted(names) == sorted(["calculator", "gcd"])
        used_blocked = any(n in ["calculator", "gcd"] for n in names)
        if "Block needed" in label:
            verdict = "✗ BLOCKED — can't call needed tools" if not correct else "✓ somehow worked"
        else:
            verdict = "✓ correct" if correct else "✗ wrong tools"
        print(f"  {label:<35} {str(names):<40} {verdict}")
    print()


async def main():
    import sys
    cd_only = "--cd-only" in sys.argv

    header("对照实验：把 logit_bias 施加在模型「需要」的工具上")
    print(f"  Task : {TASK_PROMPT}")
    print(f"  Model: {MODEL_ID}")

    results: list[tuple[str, dict]] = []

    if not cd_only:
        print()
        print("  实验设计：")
        print("  Case A — 正常 (All):      无 logit_bias，模型自由选择")
        print("  Case B — 正确 mask:       屏蔽 6 个无关工具 (string_reverse 等)")
        print("  Case C — 反转 mask:       屏蔽 2 个必需工具 (calculator + gcd) ← 对照组")
        print("  Case D — 全部屏蔽:        8 个工具全屏蔽，模型完全没有出路")

        # ── Case A ───────────────────────────────────────────────────────
        tcs = await run_case(
            label="Case A — No mask (baseline)",
            logit_bias={},
            note="全部 8 个工具可用，无任何 logit 干预",
        )
        results.append(("Case A — No mask", tcs))

        # ── Case B ───────────────────────────────────────────────────────
        logit_bias_correct: dict[str, int] = {}
        for name in [n for n in TOKEN_MAP if n not in ("calculator", "gcd")]:
            for tid in TOKEN_MAP[name]:
                logit_bias_correct[str(tid)] = -100
        tcs = await run_case(
            label="Case B — Correct mask (block irrelevant)",
            logit_bias=logit_bias_correct,
            note="屏蔽 6 个无关工具；calculator + gcd 可正常生成",
        )
        results.append(("Case B — Correct mask", tcs))

    # ── Case C ───────────────────────────────────────────────────────────
    logit_bias_inverted: dict[str, int] = {}
    for name in ("calculator", "gcd"):
        for tid in TOKEN_MAP[name]:
            logit_bias_inverted[str(tid)] = -100
    tcs = await run_case(
        label="Case C — INVERTED mask (block needed tools)",
        logit_bias=logit_bias_inverted,
        note="屏蔽 calculator + gcd；这两个工具的 token 无法生成",
    )
    results.append(("Case C — Block needed tools", tcs))

    # ── Case D ───────────────────────────────────────────────────────────
    logit_bias_all: dict[str, int] = {}
    for name, tids in TOKEN_MAP.items():
        for tid in tids:
            logit_bias_all[str(tid)] = -100
    tcs = await run_case(
        label="Case D — Block ALL tools",
        logit_bias=logit_bias_all,
        note="全部 8 个工具的 token 都被屏蔽，模型没有任何工具可以调用",
    )
    results.append(("Case D — Block all tools", tcs))

    if not cd_only:
        compare(results)

    section("结论")
    print("""
  Case A: 模型正确选择 calculator + gcd（由模型的语义理解驱动）

  Case B: 同 A，且有硬件级保证——即使模型想写 string_reverse 也写不出来

  Case C: ← 这就是 v1 实验的 bug 场景
    - 模型在 <think> 里仍然知道要用 calculator/gcd（token屏蔽不影响推理）
    - 但生成阶段写不出 "calculator" 或 "gcd" 这两个词
    - 模型会尝试变通：
        • 用其他工具凑合（string_reverse 等）
        • 在 <think> 里做心算然后直接输出
        • 尝试拼写变体（如 "Calc"、带前缀）
        • 耗尽 max_tokens 仍无有效工具调用

  Case D: 极端情况——模型完全无法使用任何工具
    - 只能做心算或拒绝回答

  核心结论：logit_bias 控制的是"生成能力"，不是"推理能力"
    模型的 <think> 内容不受影响——它仍然知道正确答案是什么
    但它被物理阻止写出对应的工具名
    """)


if __name__ == "__main__":
    asyncio.run(main())
