"""Step-by-step walkthrough of logit masking, with verbose output at each stage.

Run:
    python -m experiments.002_logit_masking.demo_walkthrough
"""

from __future__ import annotations

import asyncio
import json
import textwrap
import urllib.request

import core.providers  # noqa: registers openai_compat

BASE_URL = "http://localhost:8000/v1"
MODEL_ID = "Qwen/Qwen3-8B"

TOOL_NAMES = [
    "calculator", "string_reverse", "char_count", "base_convert",
    "caesar_cipher", "temperature_convert", "gcd", "word_count",
]

TASK_PROMPT = "First calculate 2**8 + 2**6 using the calculator tool. Then find the GCD of that result and 192 using the gcd tool. Give just the final number."
RELEVANT_TOOLS = ["calculator", "gcd"]

SEP = "─" * 72

def header(title: str):
    print(f"\n{'━' * 72}")
    print(f"  {title}")
    print(f"{'━' * 72}")

def step(n: int, title: str):
    print(f"\n{SEP}")
    print(f"  STEP {n}: {title}")
    print(SEP)


# ── Step 1: Tokenize ─────────────────────────────────────────────────────────

async def step1_tokenize() -> dict[str, list[int]]:
    step(1, "Call vLLM /tokenize to get token IDs for each tool name")

    base = BASE_URL.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = base + "/tokenize"
    print(f"  Endpoint: POST {url}")
    print()

    raw_map: dict[str, set[int]] = {name: set() for name in TOOL_NAMES}

    for name in TOOL_NAMES:
        variants = [name, f" {name}"]
        ids_per_variant = {}
        for variant in variants:
            data = json.dumps({"model": MODEL_ID, "prompt": variant}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
            first_token = result["tokens"][0]
            ids_per_variant[repr(variant)] = first_token
            raw_map[name].add(first_token)

        relevant_marker = "✓ RELEVANT" if name in RELEVANT_TOOLS else "✗ to block"
        print(f"  {name:<22} {relevant_marker}")
        for variant_repr, tid in ids_per_variant.items():
            print(f"    variant {variant_repr:<26} → token_id = {tid}")

    # Filter tokens shared by 3+ tool names
    token_frequency: dict[int, int] = {}
    for tokens in raw_map.values():
        for tid in tokens:
            token_frequency[tid] = token_frequency.get(tid, 0) + 1

    token_map: dict[str, list[int]] = {}
    for name in TOOL_NAMES:
        safe = [t for t in raw_map[name] if token_frequency[t] < 3]
        token_map[name] = sorted(safe)

    print()
    print("  Filtering: drop tokens shared by 3+ tool names (too generic)")
    print(f"  Final token_map: {json.dumps(token_map, indent=4)}")
    return token_map


# ── Step 2: Build logit_bias ──────────────────────────────────────────────────

def step2_build_logit_bias(token_map: dict[str, list[int]]) -> dict[str, int]:
    step(2, f"Build logit_bias: block all tools NOT in relevant_tools={RELEVANT_TOOLS}")

    logit_bias: dict[str, int] = {}
    for tool_name, token_ids in token_map.items():
        if tool_name not in RELEVANT_TOOLS:
            for tid in token_ids:
                logit_bias[str(tid)] = -100
            print(f"  BLOCK  {tool_name:<22} token_ids={token_ids}  → logit_bias[-100]")
        else:
            print(f"  ALLOW  {tool_name:<22} token_ids={token_ids}  → (no penalty)")

    print()
    print(f"  logit_bias dict ({len(logit_bias)} entries):")
    print(f"  {json.dumps(logit_bias)}")
    print()
    print("  Effect: at each sampling step, vLLM computes:")
    print("    adjusted_logit[token_id] = raw_logit[token_id] + logit_bias.get(token_id, 0)")
    print("    -100 offset → e^(logit-100) ≈ 0 in softmax → token probability ≈ 0%")
    return logit_bias


# ── Step 3: Show actual HTTP request ─────────────────────────────────────────

def step3_show_request(logit_bias: dict[str, int], tools_json: list[dict]):
    step(3, "Construct the chat.completions API request (what gets sent to vLLM)")

    request_body = {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant with access to tools..."},
            {"role": "user",   "content": TASK_PROMPT},
        ],
        "tools": f"<{len(tools_json)} tool definitions — all 8 still present>",
        "stream": True,
        "max_tokens": 1024,
        "temperature": 0.0,
        "logit_bias": logit_bias,   # <── THIS is the key addition
    }

    print("  POST http://localhost:8000/v1/chat/completions")
    print()
    print("  Key fields:")
    print(f'    "model"       : "{MODEL_ID}"')
    print(f'    "tools"       : {len(tools_json)} definitions (ALL 8 tools — model can see all)')
    print(f'    "temperature" : 0.0')
    print(f'    "logit_bias"  : {json.dumps(logit_bias)}')
    print()
    print("  Note: logit_bias is the ONLY difference vs. the All-strategy request.")
    print("        The tool definitions list is identical — model sees all 8 tools.")


# ── Step 4: Actually call the LLM ─────────────────────────────────────────────

async def step4_call_llm(logit_bias: dict[str, int]) -> str:
    step(4, "Fire the request — watch the model generate tool calls")

    from openai import AsyncOpenAI
    from .tools import ALL_TOOLS

    tools_payload = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in ALL_TOOLS
    ]

    client = AsyncOpenAI(base_url=BASE_URL, api_key="no-key")

    params = {
        "model": MODEL_ID,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant with access to tools. "
                    "Use the appropriate tool for EACH step. "
                    "After completing ALL steps, respond with ONLY the final answer."
                ),
            },
            {"role": "user", "content": TASK_PROMPT},
        ],
        "tools": tools_payload,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": 512,
        "temperature": 0.0,
        "logit_bias": logit_bias,
    }

    print(f"  Task: {TASK_PROMPT}")
    print()
    print("  Streaming response tokens:")
    print("  " + "·" * 60)

    tool_calls_accumulated: dict[int, dict] = {}
    full_text = ""

    response = await client.chat.completions.create(**params)
    async for chunk in response:
        choice = chunk.choices[0] if chunk.choices else None
        if not choice:
            continue
        delta = choice.delta
        if delta.content:
            full_text += delta.content
            print(delta.content, end="", flush=True)
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_accumulated:
                    tool_calls_accumulated[idx] = {"name": "", "args": ""}
                if tc.function:
                    if tc.function.name:
                        tool_calls_accumulated[idx]["name"] += tc.function.name
                    if tc.function.arguments:
                        tool_calls_accumulated[idx]["args"] += tc.function.arguments

    print()
    print("  " + "·" * 60)
    print()
    print(f"  Tool calls detected: {len(tool_calls_accumulated)}")
    for idx, tc in tool_calls_accumulated.items():
        try:
            args = json.loads(tc["args"])
        except Exception:
            args = tc["args"]
        print(f"    [{idx}] name={tc['name']!r}  args={args}")
    print()

    # Verify no blocked tools were called
    blocked = [tc["name"] for tc in tool_calls_accumulated.values()
               if tc["name"] not in RELEVANT_TOOLS and tc["name"]]
    if blocked:
        print(f"  ⚠  BLOCKED tools attempted: {blocked}")
    else:
        print("  ✓  No blocked tools attempted — logit_bias worked correctly")

    return tool_calls_accumulated


# ── Step 5: Show what happens with a non-masked call for comparison ───────────

async def step5_compare_no_mask():
    step(5, "Comparison: same request WITHOUT logit_bias (All strategy)")

    from openai import AsyncOpenAI
    from .tools import ALL_TOOLS

    tools_payload = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in ALL_TOOLS
    ]

    client = AsyncOpenAI(base_url=BASE_URL, api_key="no-key")

    params = {
        "model": MODEL_ID,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant with access to tools. "
                    "Use the appropriate tool for EACH step. "
                    "After completing ALL steps, respond with ONLY the final answer."
                ),
            },
            {"role": "user", "content": TASK_PROMPT},
        ],
        "tools": tools_payload,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": 512,
        "temperature": 0.0,
        # NO logit_bias here
    }

    print("  Same prompt + all 8 tools, but NO logit_bias.")
    print("  Model should still pick calculator+gcd (they're the correct tools),")
    print("  but nothing physically prevents it from calling others.")
    print()

    tool_calls_accumulated: dict[int, dict] = {}
    response = await client.chat.completions.create(**params)
    async for chunk in response:
        choice = chunk.choices[0] if chunk.choices else None
        if not choice:
            continue
        delta = choice.delta
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_accumulated:
                    tool_calls_accumulated[idx] = {"name": "", "args": ""}
                if tc.function:
                    if tc.function.name:
                        tool_calls_accumulated[idx]["name"] += tc.function.name
                    if tc.function.arguments:
                        tool_calls_accumulated[idx]["args"] += tc.function.arguments

    print(f"  Tool calls (no mask): {[tc['name'] for tc in tool_calls_accumulated.values()]}")
    print()
    print("  The model chooses the same tools — because it's a clear task.")
    print("  Logit mask adds a hardware-level guarantee on top of the model's judgment.")


# ── Step 6: Summary ───────────────────────────────────────────────────────────

def step6_summary(token_map: dict[str, list[int]], logit_bias: dict[str, int]):
    step(6, "Summary — what just happened")

    print(textwrap.dedent(f"""
  ┌─────────────────────────────────────────────────────────────────┐
  │                    Logit Mask Flow Summary                      │
  └─────────────────────────────────────────────────────────────────┘

  Task        : {TASK_PROMPT[:60]}...
  Relevant    : {RELEVANT_TOOLS}
  Blocked     : {[n for n in TOOL_NAMES if n not in RELEVANT_TOOLS]}

  ① /tokenize endpoint → token IDs for each tool name's first token
      {json.dumps({k: v for k, v in token_map.items() if k not in RELEVANT_TOOLS})}

  ② logit_bias built: token_id → -100 for each blocked token
      {len(logit_bias)} token IDs penalized

  ③ API request: all 8 tool DEFINITIONS sent (model sees full context)
                 + logit_bias injected as extra param

  ④ vLLM sampling loop (runs on GPU, every token):
      logit[i] += logit_bias.get(token_id, 0)
                                    ↑ -100 makes P ≈ 0%

  ⑤ Model calls only calculator + gcd  →  correct answer "64"
      Blocked tools never appear in output, even if model "wanted" them

  Key insight: context-level (what model KNOWS) vs generation-level
               (what model CAN WRITE) are controlled independently.
    """))


async def main():
    header("Logit Masking — Step-by-Step Walkthrough")
    print(f"  Model   : {MODEL_ID}")
    print(f"  Task    : {TASK_PROMPT}")
    print(f"  Relevant: {RELEVANT_TOOLS}")
    print(f"  Blocked : {[n for n in TOOL_NAMES if n not in RELEVANT_TOOLS]}")

    from .tools import ALL_TOOLS
    tools_json = [{"name": t.name} for t in ALL_TOOLS]

    token_map  = await step1_tokenize()
    logit_bias = step2_build_logit_bias(token_map)
    step3_show_request(logit_bias, tools_json)
    await step4_call_llm(logit_bias)
    await step5_compare_no_mask()
    step6_summary(token_map, logit_bias)


if __name__ == "__main__":
    asyncio.run(main())
