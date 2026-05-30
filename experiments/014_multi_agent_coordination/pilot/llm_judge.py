"""
LLM judge for FanOutQA, using AWS Bedrock Claude.

Mirrors fanoutqa.eval.llm.factuality_prompt (A-F classification) but routes
through Bedrock converse() instead of OpenAI. Categories A/B/C/E count as
factually correct (subset / superset / identical / stylistic difference);
D/F count as wrong (disagree / invalid).

Caching: keyed by sha256(judge_model + question + reference + answer) under
pilot/_judge_cache/ to keep reruns cheap and reproducible.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

import boto3

JUDGE_MODEL = os.environ.get("FANOUTQA_JUDGE_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
JUDGE_REGION = os.environ.get("AWS_REGION", "us-west-2")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "_judge_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

_FACTUALITY_SYSTEM = "You are comparing a submitted answer to an expert answer on a given question."

_FACTUALITY_USER = (
    "[BEGIN DATA]\n************\n[Question]: {q}\n************\n"
    "[Expert]: {ref}\n************\n[Submission]: {ans}\n************\n[END DATA]\n\n"
    "Compare the factual content of the submitted answer with the expert answer. "
    "Ignore any differences in style, grammar, or punctuation.\n"
    "The submitted answer may either be a subset or superset of the expert answer, or it may "
    "conflict with it. Determine which case applies. First, write out in a step by step manner "
    "your reasoning about the factual content to be sure that your conclusion is correct. "
    "Avoid simply stating the correct answers at the outset. Then print only the single character "
    '"A", "B", "C", "D", "E", or "F" (without quotes or punctuation) on its own line corresponding '
    "to the correct answer. At the end, repeat just the letter again by itself on a new line.\n"
    "(A) The submitted answer is a subset of the expert answer and is fully consistent with it.\n"
    "(B) The submitted answer is a superset of the expert answer and is fully consistent with it.\n"
    "(C) The submitted answer contains all the same details as the expert answer.\n"
    "(D) There is a disagreement between the submitted answer and the expert answer.\n"
    "(E) The answers differ, but these differences don't matter from the perspective of factuality.\n"
    "(F) The submitted answer does not answer the question or is otherwise invalid."
)

CORRECT_LABELS = {"A", "B", "C", "E"}  # per fanoutqa convention
LABEL_DESC = {
    "A": "subset of expert (consistent)",
    "B": "superset of expert (consistent)",
    "C": "identical to expert",
    "D": "disagreement",
    "E": "stylistic-only difference",
    "F": "did not answer / invalid",
}

_client = None
def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=JUDGE_REGION)
    return _client


def _stringify(x: Any) -> str:
    """Mirror fanoutqa.eval.utils.str_answer: dict→key:value lines, list→comma-joined."""
    if isinstance(x, dict):
        return "\n".join(f"{k}: {_stringify(v)}" for k, v in x.items())
    if isinstance(x, list):
        return ", ".join(_stringify(v) for v in x)
    return str(x)


def _cache_key(question: str, reference: str, answer: str) -> str:
    h = hashlib.sha256()
    h.update(JUDGE_MODEL.encode())
    h.update(b"\x00")
    h.update(question.encode())
    h.update(b"\x00")
    h.update(reference.encode())
    h.update(b"\x00")
    h.update(answer.encode())
    return h.hexdigest()[:24]


def _parse_label(text: str) -> str | None:
    if not text:
        return None
    # The official prompt asks for the letter on its own line at the end.
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    for line in reversed(lines):
        if len(line) == 1 and line in CORRECT_LABELS | {"D", "F"}:
            return line
        m = re.fullmatch(r"\(?([A-F])\)?[.)]?", line)
        if m:
            return m.group(1)
    # fallback: first standalone letter A-F anywhere
    m = re.search(r"\b([A-F])\b", text)
    return m.group(1) if m else None


def llm_judge(question: str, reference, answer: str, *, use_cache: bool = True) -> dict:
    """
    Returns {label: 'A'..'F'|None, correct: bool, raw: str, cache_hit: bool}.
    """
    ref_str = _stringify(reference)
    ans_str = answer or ""
    key = _cache_key(question, ref_str, ans_str)
    cache_path = os.path.join(CACHE_DIR, f"{key}.json")
    if use_cache and os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                cached = json.load(f)
            cached["cache_hit"] = True
            return cached
        except Exception:
            pass

    prompt = _FACTUALITY_USER.format(q=question, ref=ref_str, ans=ans_str)
    try:
        resp = _get_client().converse(
            modelId=JUDGE_MODEL,
            system=[{"text": _FACTUALITY_SYSTEM}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"temperature": 0.0, "maxTokens": 800},
        )
        raw = resp["output"]["message"]["content"][0]["text"]
    except Exception as e:
        return {"label": None, "correct": False, "raw": f"ERROR: {e}", "cache_hit": False, "error": str(e)}

    label = _parse_label(raw)
    out = {
        "label": label,
        "label_desc": LABEL_DESC.get(label, "unparsed"),
        "correct": label in CORRECT_LABELS if label else False,
        "raw": raw,
        "cache_hit": False,
    }
    if use_cache:
        try:
            with open(cache_path, "w") as f:
                json.dump(out, f)
        except Exception:
            pass
    return out


if __name__ == "__main__":
    # quick smoke
    res = llm_judge(
        "What's 2+2?",
        "4",
        "It is four.",
    )
    print(res)
