"""Quick test: run 2 agent tasks with the context observer attached."""

import asyncio
import importlib.util
import sys
from pathlib import Path

import core.providers
from core.agent import AgentConfig, run_agent
from observer.client import attach_observer
from core.types import Model, StreamOptions

# Load tools from experiment directory (folder name starts with digit, not a valid package name)
_spec = importlib.util.spec_from_file_location(
    "exp001_tools",
    Path(__file__).parent / "experiments/001_mask_vs_remove/tools.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
ALL_TOOLS = _mod.ALL_TOOLS

MODEL = Model(
    id="us.anthropic.claude-sonnet-4-20250514-v1:0",
    name="Sonnet",
    provider="bedrock",
)

SYSTEM_PROMPT = """You are a helpful assistant with access to tools. Use tools to compute answers.
After getting the tool result, respond with ONLY the final answer value."""

TASKS = [
    ("task_calc", "What is 98347 * 4729 + 18374 / 23? Use the calculator tool."),
    ("task_str",  "Reverse the string 'anthropic language model' using the string_reverse tool, then count how many times the letter 'a' appears in the reversed result using the char_count tool."),
    ("task_dict", "详细的介绍你自己，中文回答."),
]


async def run_task(task_id: str, prompt: str):
    config = AgentConfig(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        tools=ALL_TOOLS,
        stream_options=StreamOptions(max_tokens=1024),
    )
    attach_observer(config, task_id=task_id)
    messages = await run_agent(config, prompt)
    print(f"[{task_id}] done — {len(messages)} messages")


async def main():
    # Run tasks sequentially so output is easy to follow
    for task_id, prompt in TASKS:
        await run_task(task_id, prompt)


if __name__ == "__main__":
    asyncio.run(main())
