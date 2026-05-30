"""Sample FinanceBench tasks. Output: pilot/tasks/t2_financebench.jsonl"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXP_ROOT = os.path.dirname(HERE)
DATA = os.path.join(EXP_ROOT, "_vendor", "financebench", "financebench_open_source.jsonl")
OUT = os.path.join(HERE, "tasks", "t2_financebench.jsonl")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    rng = random.Random(202)
    rows = []
    with open(DATA) as f:
        for line in f:
            line = line.strip()
            if line: rows.append(json.loads(line))
    print(f"Loaded {len(rows)} financebench questions")

    import re as _re
    # Stratify into 3 difficulty buckets:
    #  - easy: information-extraction (single number lookup, no calc)
    #  - medium: metrics-generated single-period calc (one ratio/margin)
    #  - hard: metrics-generated cross-period or multi-step (DPO change, ratio trend)
    easy_pool = []
    medium_pool = []
    hard_pool = []
    for r in rows:
        a = str(r.get("answer", ""))
        if a.lower().strip().startswith(("yes", "no")):
            continue  # exclude pure yes/no
        q = r.get("question", "")
        qt = r.get("question_type")
        # cross-period detection
        cross_period = any(k in q.lower() for k in [
            "change", "difference", "growth", "compare", "between fy",
            "from fy", "to fy", "trend", "improved", "declined",
        ])
        nums_in_answer = _re.findall(r"-?\$?\(?-?[\d,]+\.?\d*\)?", a)
        if qt == "metrics-generated":
            # Determine if it requires computation (formula given in Q) vs pure extraction
            has_formula = any(k in q.lower() for k in [
                "defined as", "formula", "= (", "compute", "calculate",
            ])
            if cross_period or len(nums_in_answer) >= 2:
                hard_pool.append(r)
            elif has_formula:
                medium_pool.append(r)
            else:
                easy_pool.append(r)
        else:
            # information-extraction / domain-relevant — usually a direct lookup
            if cross_period or len(nums_in_answer) >= 2:
                medium_pool.append(r)
            else:
                easy_pool.append(r)
    print(f"  pools: easy={len(easy_pool)} medium={len(medium_pool)} hard={len(hard_pool)}")

    n_each = n // 3
    rng.shuffle(easy_pool); rng.shuffle(medium_pool); rng.shuffle(hard_pool)
    easy = easy_pool[:n_each]
    medium = medium_pool[:n_each]
    hard = hard_pool[:n_each]
    picks = []
    for r, lvl in [(x, "easy") for x in easy] + [(x, "medium") for x in medium] + [(x, "hard") for x in hard]:
        r["_difficulty"] = lvl
        picks.append(r)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out_rows = []
    import re as _re
    for r in picks:
        # parse year and type from doc_name e.g. "NETFLIX_2017_10K" or "3M_2023Q2_10Q"
        doc_name = r.get("doc_name", "")
        ym = _re.search(r"_(\d{4}(?:Q\d)?)_", doc_name)
        year = ym.group(1) if ym else "?"
        dt = "10-K" if "10K" in doc_name else ("10-Q" if "10Q" in doc_name else "filing")
        out_rows.append({
            "id": f"financebench/{r['financebench_id']}",
            "benchmark": "financebench",
            "prompt": (
                "You are a financial analyst with access to a library of SEC filings via "
                "MCP tools (mcp__financebench__list_filings, mcp__financebench__search_filings, "
                "mcp__financebench__open_filing, mcp__financebench__search_in_filing, "
                "mcp__financebench__read_page). Find the right filing, locate the relevant page, "
                "extract the answer, and reply with brief reasoning, then on the final line:\n"
                "ANSWER=<your answer — number, percentage, yes/no, or short phrase>\n\n"
                f"Question: {r['question']}\n\n"
                f"(Hint: relevant filing is {r['company']}'s {dt} for fiscal {year} — "
                f"doc_name='{doc_name}'.)"
            ),
            "expected_answer": r["answer"],
            "metadata": {
                "financebench_id": r["financebench_id"],
                "company": r.get("company"),
                "doc_name": r.get("doc_name"),
                "question_type": r.get("question_type"),
                "doc_period": r.get("doc_period"),
                "question": r["question"],
                "justification": r.get("justification"),
                "difficulty": r.get("_difficulty", "unknown"),
            },
        })

    with open(OUT, "w") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(out_rows)} → {OUT}")


if __name__ == "__main__":
    main()
