"""
Dashboard server for the 014 multi-agent pilot.

- POST /api/runs       : ingest one completed run record
- GET  /api/runs       : list all runs
- GET  /api/runs/{id}  : full detail incl. event stream
- GET  /api/stream     : SSE feed of new run events
- GET  /                : main dashboard
- GET  /run/{id}        : per-run detail page

Stores everything in-memory + JSONL on disk for reload.
"""
import asyncio
import json
import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
JSONL_PATH = os.path.join(DATA_DIR, "runs.jsonl")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI()

# In-memory state
RUNS: dict[str, dict] = {}
SUBSCRIBERS: list[asyncio.Queue] = []


def _load():
    if os.path.exists(JSONL_PATH):
        with open(JSONL_PATH) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    RUNS[r["run_id"]] = r
                except Exception:
                    pass


_load()


async def broadcast(event: dict):
    dead = []
    for q in SUBSCRIBERS:
        try:
            q.put_nowait(event)
        except Exception:
            dead.append(q)
    for q in dead:
        SUBSCRIBERS.remove(q)


class RunIn(BaseModel):
    run_id: str | None = None
    experiment: str  # e.g. "pilot_2026-05-24"
    benchmark: str   # math500 | fanoutqa | humanevalplus
    task_id: str
    mode: str        # single | ow | sw
    prompt: str
    expected_answer: Any
    final_text: str | None = None
    elapsed_s: float
    rc: int
    timeout: bool = False
    n_events: int = 0
    tool_uses: list = []
    agent_spawns: list = []
    send_messages: list = []
    team_create_calls: list = []
    verify: dict = {}
    raw_stream: list = []  # parsed jsonl events for visualization
    fs_trace: list = []     # SW filesystem snapshots
    team_name: str | None = None
    verifier_rounds: list = []  # OW-V verifier round records
    usage: dict = {}            # input_tokens / cache_* / output_tokens / total_tokens
    cost_usd: float | None = None
    started_at: float | None = None
    finished_at: float | None = None


@app.post("/api/runs")
async def post_run(rin: RunIn):
    rid = rin.run_id or uuid.uuid4().hex[:12]
    rec = rin.dict()
    rec["run_id"] = rid
    rec["finished_at"] = rec.get("finished_at") or time.time()
    RUNS[rid] = rec
    with open(JSONL_PATH, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    await broadcast({"event": "run", "run_id": rid, "summary": _summary(rec)})
    return {"ok": True, "run_id": rid}


def _summary(r: dict) -> dict:
    v = r.get("verify") or {}
    u = r.get("usage") or {}
    return {
        "run_id": r["run_id"],
        "experiment": r.get("experiment"),
        "benchmark": r.get("benchmark"),
        "task_id": r.get("task_id"),
        "mode": r.get("mode"),
        "ok": bool(v.get("ok")),
        "score": v.get("score", 0.0),
        "elapsed_s": r.get("elapsed_s"),
        "n_tool_uses": len(r.get("tool_uses") or []),
        "n_agent_spawns": len(r.get("agent_spawns") or []),
        "n_send_messages": len(r.get("send_messages") or []),
        "n_verifier_rounds": len(r.get("verifier_rounds") or []),
        "input_tokens": u.get("input_tokens", 0),
        "cache_creation_tokens": u.get("cache_creation_input_tokens", 0),
        "cache_read_tokens": u.get("cache_read_input_tokens", 0),
        "output_tokens": u.get("output_tokens", 0),
        "total_tokens": u.get("total_tokens", 0),
        "cost_usd": r.get("cost_usd"),
        "finished_at": r.get("finished_at"),
        "timeout": r.get("timeout", False),
    }


@app.get("/api/runs")
async def list_runs():
    items = [_summary(r) for r in RUNS.values()]
    items.sort(key=lambda x: x.get("finished_at") or 0, reverse=True)
    return items


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    r = RUNS.get(run_id)
    if not r:
        return JSONResponse({"error": "not found"}, status_code=404)
    return r


@app.get("/api/stream")
async def stream(request: Request):
    q: asyncio.Queue = asyncio.Queue()
    SUBSCRIBERS.append(q)

    async def gen():
        try:
            yield f"data: {json.dumps({'event':'hello'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(item, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield f": ping\n\n"
        finally:
            if q in SUBSCRIBERS:
                SUBSCRIBERS.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/run/{run_id}", response_class=HTMLResponse)
async def detail(run_id: str):
    return FileResponse(os.path.join(STATIC_DIR, "detail.html"))


# Mount static last
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7799, log_level="info")
