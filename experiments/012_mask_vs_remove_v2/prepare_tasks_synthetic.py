"""Generate synthetic multi-turn tasks for Experiment 012 v4.

15 tasks with 3–10 turns each. Tool groups cycle across turns to maximise
variety and cache-accumulation effects in longer conversations.

Design principles:
  - Each turn uses exactly ONE tool from ONE active group
  - Prompts are composite (scenario-based), not trivial tool-name hints
  - Long tasks (8-10 turns) are designed to stress-test prefix cache stability
  - Repeated groups within a task use different tools and different prompts

Usage:
    python -m experiments.012_mask_vs_remove_v2.prepare_tasks_synthetic
"""

from __future__ import annotations

import json
from pathlib import Path

from .tools import TOOL_GROUPS, ALL_TOOLS

# ── Task specs ────────────────────────────────────────────────────────────────
# "schedule": list of group-prefix per turn (determines tool_availability_schedule)
# "ground_truth_tools": specific tool per turn (must belong to the scheduled group)
# "turns": composite user prompt per turn

TASK_SPECS: list[dict] = [

    # ── Short tasks (3-4 turns) ───────────────────────────────────────────────

    {
        "id": "chain_M_T_U",
        "schedule": ["math", "text", "unit"],
        "ground_truth_tools": ["math_gcd", "text_reverse", "unit_temp"],
        "turns": [
            "I want to simplify the fraction 48/36. What is the largest number that evenly divides both?",
            "If you spelled the word 'Python' backwards, what would you get?",
            "Water boils at 100°C. What is that temperature in Fahrenheit?",
        ],
    },

    {
        "id": "chain_C_M_T_U",
        "schedule": ["code", "math", "text", "unit"],
        "ground_truth_tools": ["code_caesar", "math_factorial", "text_count_words", "unit_base"],
        "turns": [
            "Send a secret note by rotating each letter in 'HELLO' forward by 5 positions.",
            "In how many different orders can 7 people stand in a line?",
            "The sentence 'To be or not to be that is the question' — how many words does it contain?",
            "I need to represent the number 255 in binary for a subnet mask. What is the binary form?",
        ],
    },

    {
        "id": "chain_T_C_M",
        "schedule": ["text", "code", "math"],
        "ground_truth_tools": ["text_count_chars", "code_rot13", "math_sqrt"],
        "turns": [
            "My password policy requires at least 12 characters. How long is the string 'MachineLearning'?",
            "Obfuscate the word 'PYTHON' using the standard ROT13 cipher.",
            "A square park has an area of 625 square metres. How long is one side?",
        ],
    },

    {
        "id": "chain_U_T_C",
        "schedule": ["unit", "text", "code"],
        "ground_truth_tools": ["unit_miles", "text_upper", "code_md5"],
        "turns": [
            "A road sign says the next town is 26.2 miles away. How many kilometres is that?",
            "Convert the greeting 'hello world' to all capital letters.",
            "Generate an MD5 fingerprint of the string 'password123' for integrity checking.",
        ],
    },

    {
        "id": "chain_M_U_T_C",
        "schedule": ["math", "unit", "text", "code"],
        "ground_truth_tools": ["math_power", "unit_kg", "text_lower", "code_base64"],
        "turns": [
            "A server doubles its capacity each year. Starting from 1 unit, how many units are there after 10 years?",
            "A suitcase weighs 5 kilograms. Convert that to pounds for the airline limit.",
            "Normalize the username 'JohnDoe123' to all lowercase for case-insensitive lookup.",
            "Encode the credential string 'hello:world' in Base64 for an HTTP Authorization header.",
        ],
    },

    # ── Medium tasks (5-6 turns) ──────────────────────────────────────────────

    {
        "id": "chain_M_T_U_C_M_T",
        "schedule": ["math", "text", "unit", "code", "math", "text"],
        "ground_truth_tools": ["math_gcd", "text_reverse", "unit_temp", "code_caesar", "math_sqrt", "text_count_words"],
        "turns": [
            "I want to reduce the fraction 120/45 to lowest terms. What is the GCD of 120 and 45?",
            "What does the word 'OpenAI' look like spelled backwards?",
            "Normal human body temperature is 37°C. What is that in Fahrenheit?",
            "Encrypt the word 'SECRET' by advancing each letter 13 positions in the alphabet.",
            "A square tile has an area of 144 cm². What is the length of one side?",
            "Count the words in: 'All that glitters is not gold'",
        ],
    },

    {
        "id": "chain_C_U_T_M_C",
        "schedule": ["code", "unit", "text", "math", "code"],
        "ground_truth_tools": ["code_hex", "unit_bytes", "text_upper", "math_add", "code_md5"],
        "turns": [
            "Convert the two-character string 'Hi' to its hexadecimal byte representation.",
            "A downloaded file is 2.5 megabytes. How many kilobytes is that?",
            "Convert the phrase 'data science' to uppercase for a heading.",
            "A recipe uses 375 grams of flour and 140 grams of sugar. What is the total weight of dry ingredients?",
            "Generate an MD5 hash of the string 'admin123' for a password check.",
        ],
    },

    {
        "id": "chain_T_M_C_U_T",
        "schedule": ["text", "math", "code", "unit", "text"],
        "ground_truth_tools": ["text_count_chars", "math_factorial", "code_rot13", "unit_miles", "text_lower"],
        "turns": [
            "I need to check whether 'Cryptography' is longer than 10 characters. How many characters does it have?",
            "How many distinct arrangements are possible for 5 different books on a shelf?",
            "Apply ROT13 to the message 'HELLO WORLD'.",
            "A 5K race is approximately 3.1 miles. Convert 3.1 miles to kilometres.",
            "Lowercase the environment variable name 'HTTP_REQUEST_TIMEOUT' for config parsing.",
        ],
    },

    {
        "id": "chain_U_C_M_T_U_C",
        "schedule": ["unit", "code", "math", "text", "unit", "code"],
        "ground_truth_tools": ["unit_kg", "code_base64", "math_power", "text_reverse", "unit_temp", "code_caesar"],
        "turns": [
            "A newborn weighs 3.5 kg. Convert that to pounds for the US birth record.",
            "Encode the credential 'user:pass' in Base64 for Basic Authentication.",
            "What is 2 raised to the power of 8?",
            "Reverse the string 'Algorithm' to get its mirror spelling.",
            "Room temperature is 68°F. What is the equivalent in Celsius?",
            "Shift every letter in the word 'WORLD' forward by 3 positions.",
        ],
    },

    # ── Long tasks (7-10 turns) ───────────────────────────────────────────────

    {
        "id": "chain_M_C_T_U_M_C_T",
        "schedule": ["math", "code", "text", "unit", "math", "code", "text"],
        "ground_truth_tools": ["math_gcd", "code_hex", "text_count_chars", "unit_base", "math_factorial", "code_md5", "text_upper"],
        "turns": [
            "Find the largest divisor shared by 84 and 56.",
            "Encode the two-letter string 'OK' as its hexadecimal bytes.",
            "How many characters are in the phrase 'Artificial Intelligence'?",
            "Convert the decimal number 42 to binary.",
            "In how many ways can 4 contestants finish a race (no ties)?",
            "Compute the MD5 hash of the string 'hello'.",
            "Capitalise 'machine learning' — convert it entirely to uppercase.",
        ],
    },

    {
        "id": "chain_T_U_M_C_T_U_M_C",
        "schedule": ["text", "unit", "math", "code", "text", "unit", "math", "code"],
        "ground_truth_tools": ["text_reverse", "unit_temp", "math_sqrt", "code_rot13", "text_count_words", "unit_miles", "math_gcd", "code_base64"],
        "turns": [
            "Reverse the word 'Experiment' to see what it looks like backwards.",
            "Convert the freezing point of water, 0°C, to Fahrenheit.",
            "A square chessboard has area 256 cm². What is the length of one side?",
            "Apply ROT13 to the token 'SECRET' to obfuscate it.",
            "Count the words in: 'the quick brown fox jumps over the lazy dog'",
            "Convert 100 miles to kilometres for a distance comparison.",
            "Find the GCD of 72 and 48 to simplify their ratio.",
            "Encode the API key string 'api_key:xyz789' in Base64 for transmission.",
        ],
    },

    {
        "id": "chain_C_M_T_U_C_M_T_U_C",
        "schedule": ["code", "math", "text", "unit", "code", "math", "text", "unit", "code"],
        "ground_truth_tools": ["code_caesar", "math_power", "text_lower", "unit_kg", "code_md5", "math_factorial", "text_count_chars", "unit_base", "code_rot13"],
        "turns": [
            "Encrypt the word 'DATA' using a Caesar cipher with a shift of 7.",
            "Calculate 3 raised to the power of 5.",
            "Convert 'HELLO WORLD' to lowercase for normalisation.",
            "Convert 10 kilograms to pounds for a shipping label.",
            "Generate an MD5 hash of the password 'qwerty'.",
            "How many different orderings exist for 6 distinct items?",
            "Count the characters in 'reinforcement learning'.",
            "Convert the decimal number 100 to binary.",
            "Apply ROT13 to the word 'ENIGMA'.",
        ],
    },

    {
        "id": "chain_U_M_C_T_U_M_C_T_U_M",
        "schedule": ["unit", "math", "code", "text", "unit", "math", "code", "text", "unit", "math"],
        "ground_truth_tools": ["unit_temp", "math_gcd", "code_hex", "text_reverse", "unit_bytes", "math_sqrt", "code_base64", "text_count_words", "unit_miles", "math_add"],
        "turns": [
            "Convert 212°F to Celsius — that is the boiling point of water in Fahrenheit.",
            "What is the greatest common divisor of 90 and 60?",
            "Convert the two-character string 'AB' to its hexadecimal byte representation.",
            "Reverse the word 'Gradient' to get its mirror.",
            "Convert 1024 kilobytes to megabytes.",
            "A square room has an area of 196 m². What is the length of each wall?",
            "Encode 'admin:secret' in Base64 for an authentication token.",
            "Count the words in: 'she sells seashells by the seashore'",
            "The marathon distance is 42.195 km. Convert that to miles.",
            "A project took 48 hours in week 1 and 37 hours in week 2. What is the total?",
        ],
    },

    {
        "id": "chain_M_T_C_U_M_T_C_U_M_T",
        "schedule": ["math", "text", "code", "unit", "math", "text", "code", "unit", "math", "text"],
        "ground_truth_tools": ["math_power", "text_upper", "code_caesar", "unit_kg", "math_gcd", "text_lower", "code_md5", "unit_temp", "math_factorial", "text_count_chars"],
        "turns": [
            "How many bytes are in 2 to the power of 32?",
            "Capitalise 'neural network' — convert it entirely to uppercase.",
            "Encode the word 'PYTHON' using a Caesar cipher with shift 4.",
            "Convert 70 kilograms to pounds.",
            "Find the GCD of 36 and 24 to simplify a ratio.",
            "Lowercase the constant name 'MAX_RETRY_COUNT' for a config key.",
            "Get the MD5 fingerprint of the string 'secret'.",
            "Convert -40°C to Fahrenheit (they are equal at this point).",
            "How many ways can 8 books be ordered on a shelf?",
            "Count the characters in the phrase 'deep learning'.",
        ],
    },

    {
        "id": "chain_T_C_U_M_T_C_U_M_T_C",
        "schedule": ["text", "code", "unit", "math", "text", "code", "unit", "math", "text", "code"],
        "ground_truth_tools": ["text_count_words", "code_rot13", "unit_base", "math_sqrt", "text_reverse", "code_hex", "unit_miles", "math_power", "text_upper", "code_caesar"],
        "turns": [
            "Count the words in the phrase: 'to infinity and beyond'",
            "Apply ROT13 to the word 'HELLO' to obfuscate it.",
            "Convert the decimal number 128 to binary.",
            "Estimate the square root of 196.",
            "Reverse the string 'Transformer' to check its palindrome properties.",
            "Convert the two-letter string 'Go' to its hexadecimal bytes.",
            "The speed of light is about 186,000 miles per second. Convert 186000 miles to kilometres.",
            "Compute 2 to the power of 16.",
            "Convert 'attention is all you need' entirely to uppercase.",
            "Encrypt the word 'CIPHER' with a Caesar shift of 10.",
        ],
    },
]

# ── Build task records ─────────────────────────────────────────────────────────

_tool_by_name: dict[str, dict] = {
    t.name: {"name": t.name, "description": t.description, "parameters": t.parameters}
    for t in ALL_TOOLS
}
_all_tool_names: list[str] = [t.name for t in ALL_TOOLS]
_filler_tool_names: list[str] = [
    t.name for t in ALL_TOOLS
    if t.name.split("_")[0] in ("auth", "file", "net", "db", "sys", "log", "cache", "queue")
]


def _build_task_record(spec: dict) -> dict:
    schedule = spec["schedule"]
    tool_availability_schedule = {
        str(i): TOOL_GROUPS[grp]
        for i, grp in enumerate(schedule)
    }
    return {
        "id": spec["id"],
        "turns": spec["turns"],
        "ground_truth_tools": spec["ground_truth_tools"],
        "functions": [_tool_by_name[n] for n in _all_tool_names],
        "filler_tool_names": _filler_tool_names,
        "tool_availability_schedule": tool_availability_schedule,
    }


def main() -> None:
    out_path = Path(__file__).parent / "tasks" / "bfcl_multi_turn.jsonl"
    out_path.parent.mkdir(exist_ok=True)

    records = [_build_task_record(s) for s in TASK_SPECS]

    with open(out_path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    print(f"[done] Wrote {len(records)} tasks to {out_path}")
    total_turns = sum(len(r["turns"]) for r in records)
    print(f"       Total turns: {total_turns}  (avg {total_turns / len(records):.1f} per task)")
    for r in records:
        sched = r["tool_availability_schedule"]
        turns = len(r["turns"])
        groups = " → ".join(TASK_SPECS[[s["id"] for s in TASK_SPECS].index(r["id"])]["schedule"])
        gt = ", ".join(r["ground_truth_tools"])
        print(f"  {r['id']:45s}  turns={turns}  [{groups}]")
        print(f"    gt: {gt}")


if __name__ == "__main__":
    main()
