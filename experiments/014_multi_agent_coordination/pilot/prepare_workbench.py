"""
Sample WorkBench tasks. Output: pilot/tasks/t1_workbench.jsonl

Each task includes:
- id: domain/index
- benchmark: "workbench"
- prompt: natural-language query for the agent
- expected_actions: list of `tool.func(arg=value)` strings (ground-truth)
- domain: which sandbox domain(s) involved
"""
import csv
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXP_ROOT = os.path.dirname(HERE)
WBENCH_REPO = os.path.join(EXP_ROOT, "_vendor", "WorkBench")
QA_DIR = os.path.join(WBENCH_REPO, "data", "processed", "queries_and_answers")
OUT = os.path.join(HERE, "tasks", "t1_workbench.jsonl")

# Domain → CSV name
DOMAIN_FILES = {
    "calendar": "calendar_queries_and_answers.csv",
    "email": "email_queries_and_answers.csv",
    "analytics": "analytics_queries_and_answers.csv",
    "project_management": "project_management_queries_and_answers.csv",
    "customer_relationship_manager": "customer_relationship_manager_queries_and_answers.csv",
    "multi_domain": "multi_domain_queries_and_answers.csv",
}


def load_domain(domain: str) -> list[dict]:
    path = os.path.join(QA_DIR, DOMAIN_FILES[domain])
    out = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            out.append({
                "domain_idx": i,
                "domain": domain,
                "query": row["query"],
                "answer_actions_str": row["answer"],
                "domains_in_task": row.get("domains", domain),
            })
    return out


def parse_actions(s: str) -> list[str]:
    """answer column is repr of a list of strings"""
    try:
        import ast
        v = ast.literal_eval(s)
        if isinstance(v, list):
            return [str(x) for x in v]
    except Exception:
        pass
    return [s]


def _action_count(r):
    try:
        import ast as _ast
        v = _ast.literal_eval(r["answer_actions_str"])
        return len(v) if isinstance(v, list) else 1
    except Exception:
        return 1


def _stratified_sample(rng, total: int = 30):
    """Build 10 easy + 10 medium + 10 hard tasks across domains."""
    # Load all rows tagged with domain
    all_rows = {}
    for dom in DOMAIN_FILES:
        rows = load_domain(dom)
        seen = set()
        uniq = []
        for r in rows:
            if r["query"] in seen: continue
            seen.add(r["query"])
            uniq.append(r)
        all_rows[dom] = uniq

    # Easy: single-action single-domain (calendar/email/analytics)
    easy_pool = []
    for dom in ("calendar", "email", "analytics"):
        for r in all_rows[dom]:
            if _action_count(r) == 1:
                easy_pool.append(r)

    # Medium: 2-3 actions, single-domain (project_management / CRM preferred)
    medium_pool = []
    for dom in ("project_management", "customer_relationship_manager", "calendar", "email"):
        for r in all_rows[dom]:
            ac = _action_count(r)
            if 2 <= ac <= 3:
                medium_pool.append(r)

    # Hard: multi_domain with ≥2 actions (cross-domain coordination)
    hard_pool = []
    for r in all_rows["multi_domain"]:
        if _action_count(r) >= 2:
            hard_pool.append(r)

    print(f"  pool sizes: easy={len(easy_pool)} medium={len(medium_pool)} hard={len(hard_pool)}")
    n_each = total // 3
    easy = rng.sample(easy_pool, min(n_each, len(easy_pool)))
    medium = rng.sample(medium_pool, min(n_each, len(medium_pool)))
    hard = rng.sample(hard_pool, min(n_each, len(hard_pool)))
    out = []
    for r, lvl in [(x, "easy") for x in easy] + [(x, "medium") for x in medium] + [(x, "hard") for x in hard]:
        r["difficulty"] = lvl
        out.append(r)
    return out


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    rng = random.Random(202)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    rows = _stratified_sample(rng, total=total)

    out_rows = []
    for r in rows:
        dom = r["domain"]
        out_rows.append({
            "id": f"workbench/{dom}/{r['domain_idx']}",
            "benchmark": "workbench",
            "prompt": (
                "You are operating in a workplace sandbox. Use the available MCP tools "
                "(prefixed with calendar_, email_, analytics_, project_management_, "
                "customer_relationship_manager_, company_directory_) to fulfill the user's request. "
                "Make all necessary state changes via the appropriate tool calls. "
                "The current time is 2023-11-30 09:00:00. After you have made all required tool calls, "
                "reply with: ANSWER=done\n\n"
                f"User request: {r['query']}"
            ),
            "expected_answer": parse_actions(r["answer_actions_str"]),
            "metadata": {
                "domain": dom,
                "domain_idx": r["domain_idx"],
                "query": r["query"],
                "domains_in_task": r["domains_in_task"],
                "difficulty": r["difficulty"],
                "n_actions": _action_count(r),
            },
        })

    with open(OUT, "w") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(out_rows)} tasks → {OUT}")


if __name__ == "__main__":
    main()
