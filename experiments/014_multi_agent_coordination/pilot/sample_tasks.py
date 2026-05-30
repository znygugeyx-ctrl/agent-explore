"""
Pick 2 representative tasks from each benchmark for the pilot run.
Output: pilot/tasks/{t1_math.jsonl, t2_fanoutqa.jsonl, t3_humanevalplus.jsonl}
"""
import json
import os
import random

OUT_DIR = os.path.join(os.path.dirname(__file__), "tasks")
os.makedirs(OUT_DIR, exist_ok=True)


def sample_math():
    from datasets import load_dataset
    ds = load_dataset("HuggingFaceH4/MATH-500", split="test")
    # pick 1 level-3 + 1 level-5 to span difficulty
    by_level = {}
    for row in ds:
        by_level.setdefault(row["level"], []).append(row)
    rng = random.Random(42)
    picks = []
    for lvl in (3, 5):
        if lvl in by_level:
            picks.append(rng.choice(by_level[lvl]))
    out = []
    for r in picks:
        out.append({
            "id": r["unique_id"],
            "benchmark": "math500",
            "prompt": (
                f"Solve this math problem. Show brief reasoning, then on the final line "
                f"write exactly: ANSWER=<your answer in LaTeX>\n\n"
                f"Problem: {r['problem']}"
            ),
            "expected_answer": r["answer"],
            "metadata": {"level": r["level"], "subject": r["subject"]},
        })
    return out


def sample_bamboogle(n: int = 2):
    """Sample multi-hop questions from Bamboogle (125 hand-picked, EM-evaluable)."""
    from datasets import load_dataset
    ds = load_dataset("chiayewken/bamboogle", split="test")
    rng = random.Random(42)
    indices = rng.sample(range(len(ds)), n)
    out = []
    for i in indices:
        row = ds[i]
        question = row["Question"]
        answer = row["Answer"]
        out.append({
            "id": f"bamboogle/{i}",
            "benchmark": "bamboogle",
            "prompt": (
                "Answer the following multi-hop question. You have WebSearch and WebFetch available; "
                "use them to look up the necessary facts. The question requires composing 2-3 lookups.\n\n"
                "Reply with brief reasoning, then on the final line write exactly:\n"
                "ANSWER=<your short answer, just the key fact — a name, year, place, or short phrase>\n\n"
                f"Question: {question}"
            ),
            "expected_answer": answer,
            "metadata": {
                "question": question,
                "answer_aliases": [answer],  # bamboogle has only one gold answer per Q
            },
        })
    return out


# Backwards compat alias
sample_fanoutqa = sample_bamboogle


def sample_humanevalplus():
    from evalplus.data import get_human_eval_plus
    problems = get_human_eval_plus()
    keys = sorted(problems.keys(), key=lambda k: int(k.split('/')[1]))
    rng = random.Random(42)
    picks = rng.sample(keys, 2)
    out = []
    for k in picks:
        p = problems[k]
        out.append({
            "id": k,
            "benchmark": "humanevalplus",
            "prompt": (
                "Implement the function described below. Return ONLY the complete Python function "
                "definition (no markdown fences). On the final line of your reply, place the function "
                "definition. Above the function, you may write brief comments.\n\n"
                f"```python\n{p['prompt']}```\n\n"
                f"Reply with the function `{p['entry_point']}` implemented."
            ),
            "expected_answer": p["canonical_solution"],
            "metadata": {
                "task_id": k,
                "entry_point": p["entry_point"],
                "test_code": p["test"],
                "prompt_signature": p["prompt"],
            },
        })
    return out


def write(name, rows):
    p = os.path.join(OUT_DIR, name)
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} -> {p}")


if __name__ == "__main__":
    import sys
    n_bamboogle = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    write("t1_math.jsonl", sample_math())
    write("t2_bamboogle.jsonl", sample_bamboogle(n=n_bamboogle))
    write("t3_humanevalplus.jsonl", sample_humanevalplus())
