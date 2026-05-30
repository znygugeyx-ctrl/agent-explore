"""
PlanCraft MCP server.

One process per task. Loads a single PlanCraft task's initial inventory and
target, exposes Minecraft-style crafting actions as MCP tools, and dumps
the final inventory for the verifier.

Crafting model (mirrors PlanCraft):
- Slots 1-9 = 3x3 crafting grid input
- Slot 0 = crafting output (auto-populated when grid forms valid recipe)
- Slots 10-45 = main inventory
- Slot 41 = furnace input slot for smelting

Env vars:
- PC_TASK_FILE  : path to JSON file with {slotted_inventory, target} for the task
- PC_STATE_OUT  : path to write final inventory snapshot

Run as: python3 plancraft_server.py
"""
from __future__ import annotations
import atexit
import json
import os
import signal
import sys
from typing import Any

TASK_FILE = os.environ.get("PC_TASK_FILE")
STATE_OUT = os.environ.get("PC_STATE_OUT", "/tmp/plancraft_state.json")
if not TASK_FILE or not os.path.isfile(TASK_FILE):
    print(f"PC_TASK_FILE not set or not a file: {TASK_FILE!r}", file=sys.stderr)
    sys.exit(2)

from plancraft.environment.env import PlancraftEnvironment  # noqa: E402
from plancraft.environment.actions import (  # noqa: E402
    MoveAction, SmeltAction, StopAction,
)

# -------- Load task --------
with open(TASK_FILE) as f:
    TASK = json.load(f)

# slotted_inventory: {"12": {"type":..., "quantity":...}} → keys must be int
INITIAL_INV = {int(k): v for k, v in TASK["slotted_inventory"].items()}
TARGET = TASK["target"]
TASK_ID = TASK.get("id", "unknown")
MAX_STEPS = int(TASK.get("max_steps", 30))

ENV = PlancraftEnvironment(inventory=dict(INITIAL_INV))
HISTORY: list[dict] = []   # action log
CUR_INV: dict[int, dict] = dict(INITIAL_INV)
STEPS_TAKEN = 0
STOPPED = False
STOP_REASON: str | None = None


def _snapshot_inv() -> dict:
    """Return current inventory as {int_slot: {type, quantity}}."""
    # ENV doesn't expose .inventory; we maintain our own mirror via step results
    return dict(CUR_INV)


def _has_target() -> bool:
    """Check if TARGET item exists anywhere in the inventory."""
    for slot, info in CUR_INV.items():
        if info and info.get("type") == TARGET and (info.get("quantity") or 0) > 0:
            return True
    return False


import threading as _threading  # noqa: E402

_DUMP_LOCK = _threading.Lock()


def dump_state():
    out = {
        "task_id": TASK_ID,
        "target": TARGET,
        "max_steps": MAX_STEPS,
        "steps_taken": STEPS_TAKEN,
        "stopped": STOPPED,
        "stop_reason": STOP_REASON,
        "final_inventory": {str(k): v for k, v in CUR_INV.items()},
        "has_target": _has_target(),
        "history": HISTORY,
    }
    tmp = STATE_OUT + ".tmp"
    try:
        with _DUMP_LOCK:
            with open(tmp, "w") as f:
                json.dump(out, f, default=str)
            os.replace(tmp, STATE_OUT)
    except Exception as e:
        print(f"failed to dump state: {e}", file=sys.stderr)


atexit.register(dump_state)
def _sig_handler(signum, frame):
    dump_state()
    sys.exit(0)
for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    try: signal.signal(_sig, _sig_handler)
    except Exception: pass


# -------- MCP tools --------
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("plancraft")


@mcp.tool(
    name="get_target",
    description=(
        "Returns the target item the agent must produce. The task is complete when this "
        "item appears in the inventory."
    ),
)
def get_target() -> dict:
    return {"target": TARGET, "max_steps": MAX_STEPS, "steps_taken": STEPS_TAKEN}


@mcp.tool(
    name="get_inventory",
    description=(
        "Returns the current inventory state. Slots 0 = crafting output, "
        "1-9 = 3x3 crafting grid input, 10-45 = main inventory storage, "
        "44 = furnace fuel, 45 = furnace output (smelt result)."
    ),
)
def get_inventory() -> dict:
    return {
        "inventory": {str(k): v for k, v in CUR_INV.items() if v and v.get("quantity")},
        "has_target": _has_target(),
        "target": TARGET,
        "steps_taken": STEPS_TAKEN,
    }


def _apply_step(action_obj) -> dict:
    """Run one step of the env, update CUR_INV mirror, log history."""
    global STEPS_TAKEN
    STEPS_TAKEN += 1
    try:
        res = ENV.step(action=action_obj)
    except Exception as e:
        HISTORY.append({"step": STEPS_TAKEN, "error": f"{type(e).__name__}: {e}"})
        return {"error": f"{type(e).__name__}: {e}"}
    new_inv = res.get("inventory", {})
    # res inventory keys are str — normalize to int and rebuild mirror
    CUR_INV.clear()
    for k, v in new_inv.items():
        if v and (v.get("quantity") or 0) > 0:
            CUR_INV[int(k)] = v
    inv_summary = {str(k): v for k, v in CUR_INV.items()}
    HISTORY.append({
        "step": STEPS_TAKEN,
        "action": action_obj.__class__.__name__,
        "params": action_obj.model_dump() if hasattr(action_obj, "model_dump") else str(action_obj),
        "inventory_after": inv_summary,
        "has_target": _has_target(),
    })
    # Persist state on every step (defensive — process may be killed without
    # graceful exit when CC closes stdio).
    try: dump_state()
    except Exception: pass
    return {
        "inventory": inv_summary,
        "has_target": _has_target(),
        "steps_taken": STEPS_TAKEN,
    }


@mcp.tool(
    name="move",
    description=(
        "Move 'quantity' items from slot_from to slot_to. "
        "To craft: place ingredients in slots 1-9 (3x3 grid), then move from slot 0 (output) "
        "to a free slot in 10-45 to collect the crafted item. Slot indices are integers."
    ),
)
def move(slot_from: str, slot_to: str, quantity: str = "1") -> dict:
    if STOPPED:
        return {"error": "stop() already called; restart the task"}
    if STEPS_TAKEN >= MAX_STEPS:
        return {"error": f"max_steps ({MAX_STEPS}) reached"}
    try:
        sf = int(slot_from); st = int(slot_to); q = int(quantity)
    except Exception as e:
        return {"error": f"all params must be integers: {e}"}
    return _apply_step(MoveAction(slot_from=sf, slot_to=st, quantity=q))


@mcp.tool(
    name="smelt",
    description=(
        "Smelt items in the furnace. Move 'quantity' raw ingredient from slot_from "
        "to furnace input (slot 44), the smelted result will be at slot 45 then move to slot_to."
    ),
)
def smelt(slot_from: str, slot_to: str, quantity: str = "1") -> dict:
    if STOPPED:
        return {"error": "stop() already called; restart the task"}
    if STEPS_TAKEN >= MAX_STEPS:
        return {"error": f"max_steps ({MAX_STEPS}) reached"}
    try:
        sf = int(slot_from); st = int(slot_to); q = int(quantity)
    except Exception as e:
        return {"error": f"all params must be integers: {e}"}
    return _apply_step(SmeltAction(slot_from=sf, slot_to=st, quantity=q))


@mcp.tool(
    name="stop",
    description=(
        "Indicate task is finished (or impossible). Provide a brief reason. "
        "Call this AFTER the target item is in the inventory; the verifier "
        "will check has_target. Use reason='impossible' if the task can't be solved."
    ),
)
def stop(reason: str = "done") -> dict:
    global STOPPED, STOP_REASON
    STOPPED = True
    STOP_REASON = reason
    HISTORY.append({"step": STEPS_TAKEN, "action": "Stop", "reason": reason})
    dump_state()
    return {
        "stopped": True,
        "reason": reason,
        "has_target": _has_target(),
        "steps_taken": STEPS_TAKEN,
    }


if __name__ == "__main__":
    print(f"plancraft MCP server: task_id={TASK_ID} target={TARGET} "
          f"initial_slots={list(INITIAL_INV.keys())} max_steps={MAX_STEPS}",
          file=sys.stderr)
    mcp.run(transport="stdio")
