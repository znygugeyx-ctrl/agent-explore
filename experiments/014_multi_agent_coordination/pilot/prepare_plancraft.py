"""Sample PlanCraft tasks. Output: pilot/tasks/t3_plancraft.jsonl + per-task state files."""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
import plancraft as _pc
_PC_DATA_DIR = os.path.join(os.path.dirname(_pc.__file__), "data")
DATA = os.environ.get("PC_DATA", os.path.join(_PC_DATA_DIR, "val.json"))
OUT = os.path.join(HERE, "tasks", "t3_plancraft.jsonl")
TASKS_STATE_DIR = os.path.join(HERE, "tasks", "_plancraft_states")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    rng = random.Random(101)

    with open(DATA) as f:
        rows = json.load(f)
    print(f"Loaded {len(rows)} plancraft val tasks")

    # Filter: stratify by optimal_path_length so we get a mix
    by_len = {}
    for r in rows:
        L = r.get("optimal_path_length") or 1
        by_len.setdefault(int(L), []).append(r)
    print(f"  optimal_path_length distribution: {sorted((k, len(v)) for k, v in by_len.items())}")

    # Stratified sample: 10 easy (1-2 steps) + 10 medium (3-4 steps) + 10 hard (5+ steps)
    n_each = n // 3
    easy_lens = [1, 2]
    medium_lens = [3, 4]
    hard_lens = [5, 6, 7, 8, 9, 10, 11, 12]

    def _pick_from_lens(lens, k):
        pool = []
        for L in lens:
            if L in by_len: pool.extend(by_len[L])
        rng.shuffle(pool)
        return [(r, L_for(r)) for r in pool[:k]]

    def L_for(r):
        return int(r.get("optimal_path_length") or 1)

    easy = _pick_from_lens(easy_lens, n_each)
    medium = _pick_from_lens(medium_lens, n_each)
    hard = _pick_from_lens(hard_lens, n_each)

    picks = []
    for (r, L), lvl in [(t, "easy") for t in easy] + [(t, "medium") for t in medium] + [(t, "hard") for t in hard]:
        r["_difficulty"] = lvl
        picks.append(r)
    print(f"  picked: easy={len(easy)} medium={len(medium)} hard={len(hard)}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    os.makedirs(TASKS_STATE_DIR, exist_ok=True)

    out_rows = []
    for r in picks:
        # Persist per-task state file (for MCP server to load)
        # Allow more steps for harder tasks: optimal_path_length × ~6 + buffer
        L = int(r.get("optimal_path_length") or 1)
        max_steps = max(30, L * 6 + 20)
        state = {
            "id": r["id"],
            "slotted_inventory": r["slotted_inventory"],
            "target": r["target"],
            "max_steps": max_steps,
            "optimal_path_length": r.get("optimal_path_length"),
            "optimal_path": r.get("optimal_path"),
        }
        sf = os.path.join(TASKS_STATE_DIR, f"{r['id'].replace('/', '_')}.json")
        with open(sf, "w") as fh:
            json.dump(state, fh)

        # Build a description of the starting inventory for the prompt
        slotted = r["slotted_inventory"]
        n_items = len(slotted)
        sample_items = list(slotted.items())[:8]
        inv_desc = ", ".join(f"slot {k}: {v['quantity']}× {v['type']}" for k, v in sample_items)
        if n_items > 8:
            inv_desc += f", ... ({n_items} slots total)"

        out_rows.append({
            "id": f"plancraft/{r['id']}",
            "benchmark": "plancraft",
            "prompt": (
                "You are playing a Minecraft crafting puzzle. You have an MCP toolset "
                "(mcp__plancraft__get_target, mcp__plancraft__get_inventory, "
                "mcp__plancraft__move, mcp__plancraft__smelt, mcp__plancraft__stop). "
                "Your goal: produce the target item by performing crafting actions. "
                "Slot layout:\n"
                "  - slot 0: crafting output (auto-populated when slots 1-9 form a valid recipe)\n"
                "  - slots 1-9: 3x3 crafting grid (top-left = 1, top-mid = 2, top-right = 3, "
                "middle row = 4-6, bottom row = 7-9)\n"
                "  - slots 10-45: main inventory storage\n"
                "  - slots 44/45: furnace input/output for smelting\n\n"
                "Workflow: (1) call get_target to confirm target. (2) call get_inventory "
                "to see current state. (3) Use move/smelt to produce the target — for crafting, "
                "place ingredients in slots 1-9 then move from slot 0 to a free inventory slot "
                "(10-45). (4) Once target is in inventory, call stop. After stopping, reply "
                "with: ANSWER=done\n\n"
                f"Target: {r['target']}\n"
                f"Starting inventory ({n_items} items): {inv_desc}\n"
                f"Optimal path length: {r.get('optimal_path_length')} step(s).\n"
                f"Max steps: 30."
            ),
            "expected_answer": r["target"],
            "metadata": {
                "plancraft_id": r["id"],
                "target": r["target"],
                "optimal_path": r.get("optimal_path"),
                "optimal_path_length": r.get("optimal_path_length"),
                "num_distractors": r.get("num_distractors"),
                "state_file": sf,
                "difficulty": r.get("_difficulty", "unknown"),
            },
        })

    with open(OUT, "w") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(out_rows)} → {OUT}")


if __name__ == "__main__":
    main()
