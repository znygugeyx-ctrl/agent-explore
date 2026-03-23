"""Standalone context observer server.

Usage:
    python -m observer.server             # default port 7777
    python -m observer.server --port 8888

Receives events from observer.client via HTTP POST.
Persists to JSONL files under observer/data/.
Serves web UI at http://localhost:7777 and SSE stream for live updates.
"""

from __future__ import annotations

import argparse
import json
import queue
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

DATA_DIR = Path(__file__).parent / "data"

_clients: list[queue.Queue] = []
_clients_lock = threading.Lock()
_write_lock = threading.Lock()


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class _ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # suppress per-request logs

    # -- Routing --

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            self._html()
        elif p == "/events":
            self._sse()
        elif p == "/api/runs":
            self._api_runs()
        elif m := re.match(r"^/api/runs/([^/]+)/tasks$", p):
            self._api_run_tasks(m.group(1))
        elif m := re.match(r"^/api/runs/([^/]+)/tasks/([^/]+)$", p):
            self._api_task_events(m.group(1), m.group(2))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/api/events":
            self._receive_event()
        else:
            self.send_response(404)
            self.end_headers()

    # -- Handlers --

    def _html(self):
        body = _HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        cq: queue.Queue = queue.Queue(maxsize=500)
        with _clients_lock:
            _clients.append(cq)
        try:
            while True:
                try:
                    msg = cq.get(timeout=15)
                    if msg is None:
                        break
                    self.wfile.write(msg.encode())
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with _clients_lock:
                _clients.remove(cq)

    def _receive_event(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            event = json.loads(body)
            _persist(event)
            _broadcast(event)
            self.send_response(204)
        except Exception:
            self.send_response(400)
        self.end_headers()

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _api_runs(self):
        runs = []
        if DATA_DIR.exists():
            dirs = sorted(DATA_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for d in dirs:
                if d.is_dir():
                    files = list(d.glob("*.jsonl"))
                    runs.append({
                        "run_id": d.name,
                        "task_count": len(files),
                        "last_ts": d.stat().st_mtime,
                    })
        self._json(runs)

    def _api_run_tasks(self, run_id: str):
        run_dir = DATA_DIR / _safe(run_id)
        tasks = []
        if run_dir.exists():
            files = sorted(run_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
            for f in files:
                task_id = f.stem
                turns = 0
                last_ts = f.stat().st_mtime
                try:
                    lines = f.read_text(encoding="utf-8").strip().splitlines()
                    if lines:
                        first = json.loads(lines[0])
                        task_id = first.get("task_id", f.stem)
                        last_ts = json.loads(lines[-1]).get("ts", last_ts)
                        turns = sum(1 for l in lines if '"context"' in l and
                                    json.loads(l).get("type") == "context")
                except Exception:
                    pass
                tasks.append({
                    "file": f.stem,
                    "task_id": task_id,
                    "turns": turns,
                    "last_ts": last_ts,
                })
        self._json(tasks)

    def _api_task_events(self, run_id: str, task_file: str):
        f = DATA_DIR / _safe(run_id) / f"{_safe(task_file)}.jsonl"
        events = []
        if f.exists():
            for line in f.read_text(encoding="utf-8").strip().splitlines():
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
        self._json(events)


# ---------------------------------------------------------------------------
# Persistence + broadcast
# ---------------------------------------------------------------------------

def _safe(s: str) -> str:
    return re.sub(r"[^\w\-]", "_", s)


def _persist(event: dict) -> None:
    run_id = event.get("run_id", "unknown")
    task_id = event.get("task_id", "unknown")
    run_dir = DATA_DIR / _safe(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    f = run_dir / f"{_safe(task_id)}.jsonl"
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with _write_lock:
        with f.open("a", encoding="utf-8") as fp:
            fp.write(line)


def _broadcast(event: dict) -> None:
    payload = f"event: agent\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
    with _clients_lock:
        for cq in list(_clients):
            try:
                cq.put_nowait(payload)
            except queue.Full:
                pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global DATA_DIR
    parser = argparse.ArgumentParser(description="Context observer server")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--data", type=str, default=str(DATA_DIR))
    args = parser.parse_args()

    DATA_DIR = Path(args.data)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    server = _ThreadedServer(("localhost", args.port), _Handler)
    print(f"Observer: http://localhost:{args.port}")
    print(f"Data:     {DATA_DIR.resolve()}")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


# ---------------------------------------------------------------------------
# Embedded UI
# ---------------------------------------------------------------------------

_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Context Observer</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'SF Mono',Menlo,Consolas,monospace;font-size:13px;background:#1a1a1a;color:#d4d4d4;display:flex;height:100vh;overflow:hidden}

/* Sidebar */
#sidebar{width:220px;min-width:220px;background:#252526;border-right:1px solid #3c3c3c;display:flex;flex-direction:column;overflow:hidden}
#sb-header{padding:10px 12px;font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#858585;border-bottom:1px solid #3c3c3c;display:flex;align-items:center;gap:6px}
#sb-refresh{margin-left:auto;background:none;border:none;color:#858585;cursor:pointer;font-size:14px;line-height:1;padding:2px 4px}
#sb-refresh:hover{color:#ccc}
#run-list{flex:1;overflow-y:auto;padding:4px 0}

.run-item{cursor:pointer;user-select:none}
.run-hdr{padding:7px 12px;display:flex;align-items:center;gap:6px;color:#ccc;font-size:12px}
.run-hdr:hover{background:#2a2d2e}
.run-hdr.active{background:#1e3a5f}
.run-arr{font-size:9px;width:10px;display:inline-block;transition:transform .15s}
.run-arr.open{transform:rotate(90deg)}
.run-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.run-count{font-size:10px;color:#555}

.task-list{display:none;padding-left:0}
.task-list.open{display:block}
.task-item{padding:6px 12px 6px 26px;cursor:pointer;display:flex;align-items:center;gap:6px;color:#aaa;font-size:12px;border-left:3px solid transparent}
.task-item:hover{background:#2a2d2e}
.task-item.active{background:#094771;border-left-color:#007acc;color:#fff}
.task-dot{width:7px;height:7px;border-radius:50%;background:#555;flex-shrink:0}
.task-dot.live{background:#73c991;animation:pulse 1.5s infinite}
.task-dot.done{background:#555}
.task-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.task-meta{font-size:10px;color:#555}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* Main */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden}
#top-bar{padding:8px 16px;background:#252526;border-bottom:1px solid #3c3c3c;display:flex;align-items:center;gap:12px;min-height:44px;flex-shrink:0}
#top-title{font-size:12px;color:#858585}
#tok-wrap{flex:1;max-width:300px;display:none}
#tok-label{font-size:10px;color:#858585;margin-bottom:3px}
.tok-bar{height:5px;background:#3c3c3c;border-radius:3px;overflow:hidden}
.tok-fill{height:100%;background:#007acc;border-radius:3px;transition:width .4s}
#as-btn{margin-left:auto;padding:4px 10px;font-size:11px;background:#3c3c3c;border:none;color:#ccc;border-radius:3px;cursor:pointer}
#as-btn.on{background:#007acc;color:#fff}
#turns{flex:1;overflow-y:auto;padding:12px}
#empty{color:#555;text-align:center;margin-top:100px;font-size:14px;line-height:2}

/* Turn cards */
.turn-card{background:#252526;border:1px solid #3c3c3c;border-radius:6px;margin-bottom:12px;overflow:hidden}
.turn-hdr{padding:7px 12px;background:#2d2d2d;display:flex;align-items:center;gap:8px;font-size:12px;color:#858585;border-bottom:1px solid #3c3c3c;flex-wrap:wrap}
.t-num{color:#007acc;font-weight:bold}
.t-stats{margin-left:auto;display:flex;gap:10px;font-size:11px;flex-wrap:wrap}
.st{color:#858585}.st b{color:#d4d4d4;font-weight:normal}

/* Sections */
.sec{border-bottom:1px solid #2a2a2a}
.sec:last-child{border-bottom:none}
.sec-hdr{padding:5px 12px;cursor:pointer;display:flex;align-items:center;gap:6px;font-size:11px;color:#858585;user-select:none}
.sec-hdr:hover{background:#2a2d2e}
.sec-arr{font-size:9px;width:10px;display:inline-block;transition:transform .15s}
.sec-arr.o{transform:rotate(90deg)}
.sec-title{font-size:11px;text-transform:uppercase;letter-spacing:.5px}
.sec-meta{margin-left:auto;font-size:10px;color:#555}
.sec-body{display:none;padding:4px 12px 8px}
.sec-body.o{display:block}

/* Messages */
.msg{margin:4px 0;padding-left:8px;border-left:3px solid #3c3c3c}
.msg.user{border-left-color:#4fc1ff}
.msg.assistant{border-left-color:#c586c0}
.msg.tool_result{border-left-color:#4ec9b0}
.msg-role{font-size:10px;font-weight:bold;text-transform:uppercase;letter-spacing:.5px;margin-bottom:2px}
.r-user{color:#4fc1ff}.r-assistant{color:#c586c0}.r-tool_result{color:#4ec9b0}
.msg-text{color:#d4d4d4;white-space:pre-wrap;word-break:break-word;font-size:12px}

/* Content blocks */
.b-think{background:#1e1e2e;border-radius:4px;padding:4px 8px;margin:3px 0}
.b-think-hdr{font-size:10px;color:#858585;cursor:pointer;display:flex;align-items:center;gap:4px}
.b-think-body{display:none;color:#858585;font-size:12px;white-space:pre-wrap;margin-top:4px}
.b-think-body.o{display:block}
.b-tc{background:#1e2a1e;border-radius:4px;padding:5px 8px;margin:3px 0}
.b-tc-name{color:#dcdcaa;font-size:12px;font-weight:bold}
.b-tc-args{color:#9cdcfe;font-size:12px;margin-top:2px;white-space:pre-wrap}
.b-tr{background:#1e2a2e;border-radius:4px;padding:5px 8px;margin:3px 0}
.b-tr-hdr{font-size:10px;color:#858585;cursor:pointer;display:flex;align-items:center;gap:4px}
.b-tr-hdr.err{color:#f48771}
.b-tr-body{display:none;font-size:12px;white-space:pre-wrap;color:#9cdcfe;margin-top:4px;max-height:300px;overflow-y:auto}
.b-tr-body.o{display:block}

/* Tools list */
.tool-row{padding:4px 0;border-bottom:1px solid #2d2d2d}
.tool-row:last-child{border-bottom:none}
.tool-name{color:#dcdcaa;font-weight:bold;font-size:12px}
.tool-desc{color:#858585;font-size:11px;margin-top:1px}
.tool-schema-hdr{font-size:10px;color:#555;cursor:pointer;margin-top:2px;display:flex;align-items:center;gap:3px}
.tool-schema-body{display:none;color:#9cdcfe;font-size:11px;white-space:pre;background:#1e1e1e;padding:4px;border-radius:3px;margin-top:3px;overflow-x:auto;max-height:250px;overflow-y:auto}
.tool-schema-body.o{display:block}

.sys-text{color:#d4d4d4;white-space:pre-wrap;font-size:12px}
.waiting{color:#555;font-style:italic;padding:8px 12px;font-size:12px}

::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#424242;border-radius:3px}
</style>
</head>
<body>
<div id="sidebar">
  <div id="sb-header">
    <span>Runs</span>
    <button id="sb-refresh" onclick="loadRuns()" title="Refresh">↻</button>
  </div>
  <div id="run-list"></div>
</div>
<div id="main">
  <div id="top-bar">
    <span id="top-title">Context Observer</span>
    <div id="tok-wrap">
      <div id="tok-label">0 tokens</div>
      <div class="tok-bar"><div class="tok-fill" id="tok-fill" style="width:0%"></div></div>
    </div>
    <button id="as-btn" class="on" onclick="toggleAS()">Auto-scroll</button>
  </div>
  <div id="turns">
    <div id="empty">No task selected.<br>Start the agent or pick a run from the sidebar.</div>
  </div>
</div>
<script>
// ---- State ----
const S = {
  runs: [],
  runTasks: {},          // run_id → tasks array
  expandedRuns: new Set(),
  sel: null,             // {run_id, task_file, task_id}
  liveTasks: new Set(),  // "run_id/task_file" currently live
  taskTokens: {},        // "run_id/task_file" → last input token count
  autoScroll: true,
  ctxWin: 128000,
};

// ---- SSE ----
function connect() {
  const es = new EventSource('/events');
  es.addEventListener('agent', e => onLive(JSON.parse(e.data)));
  es.onerror = () => { setTimeout(connect, 2000); es.close(); };
}
connect();

function onLive(ev) {
  const key = ev.run_id + '/' + _safe(ev.task_id);
  S.liveTasks.add(key);

  // Update sidebar metadata
  const existing = S.runTasks[ev.run_id];
  if (existing) {
    const t = existing.find(t => t.file === _safe(ev.task_id));
    if (t) {
      if (ev.type === 'context') t.turns = Math.max(t.turns || 0, ev.turn);
      t.live = true;
    } else {
      existing.push({ file: _safe(ev.task_id), task_id: ev.task_id, turns: ev.turn || 0, live: true });
    }
    renderRunTasks(ev.run_id);
  } else {
    // New run — refresh sidebar
    loadRuns();
  }

  // Update token bar
  if (ev.type === 'response' && ev.data?.usage?.input) {
    S.taskTokens[key] = ev.data.usage.input;
  }

  // Update main panel if this task is selected
  if (S.sel && S.sel.run_id === ev.run_id && S.sel.task_file === _safe(ev.task_id)) {
    if (ev.type === 'response' && ev.data?.usage?.input) {
      updateTokenBar(ev.data.usage.input);
    }
    applyEvent(ev);
    if (S.autoScroll) scrollBottom();
  }
}

// ---- Sidebar ----
async function loadRuns() {
  try {
    const res = await fetch('/api/runs');
    S.runs = await res.json();
    renderRuns();
  } catch(e) {}
}

function renderRuns() {
  const el = document.getElementById('run-list');
  el.innerHTML = '';
  for (const r of S.runs) {
    const div = document.createElement('div');
    div.className = 'run-item';
    div.id = 'run_' + r.run_id;
    const isOpen = S.expandedRuns.has(r.run_id);
    div.innerHTML = `
      <div class="run-hdr" onclick="toggleRun('${r.run_id}')">
        <span class="run-arr${isOpen?' open':''}">▶</span>
        <span class="run-name">${esc(r.run_id)}</span>
        <span class="run-count">${r.task_count}</span>
      </div>
      <div class="task-list${isOpen?' open':''}" id="tl_${r.run_id}"></div>`;
    el.appendChild(div);
    if (isOpen && S.runTasks[r.run_id]) renderRunTasks(r.run_id);
  }
}

async function toggleRun(run_id) {
  if (S.expandedRuns.has(run_id)) {
    S.expandedRuns.delete(run_id);
    renderRuns();
  } else {
    S.expandedRuns.add(run_id);
    renderRuns();
    if (!S.runTasks[run_id]) {
      try {
        const res = await fetch('/api/runs/' + run_id + '/tasks');
        S.runTasks[run_id] = await res.json();
        renderRunTasks(run_id);
      } catch(e) {}
    }
  }
}

function renderRunTasks(run_id) {
  const el = document.getElementById('tl_' + run_id);
  if (!el) return;
  const tasks = S.runTasks[run_id] || [];
  el.innerHTML = '';
  for (const t of tasks) {
    const key = run_id + '/' + t.file;
    const isLive = S.liveTasks.has(key);
    const isSel = S.sel && S.sel.run_id === run_id && S.sel.task_file === t.file;
    const div = document.createElement('div');
    div.className = 'task-item' + (isSel ? ' active' : '');
    div.onclick = () => selectTask(run_id, t.file, t.task_id);
    div.innerHTML = `<span class="task-dot ${isLive?'live':'done'}"></span>
      <span class="task-name">${esc(t.task_id)}</span>
      <span class="task-meta">T${t.turns||0}</span>`;
    el.appendChild(div);
  }
}

// ---- Task selection ----
async function selectTask(run_id, task_file, task_id) {
  S.sel = { run_id, task_file, task_id };
  renderRunTasks(run_id);

  document.getElementById('turns').innerHTML = '<div class="waiting">Loading...</div>';
  document.getElementById('tok-wrap').style.display = 'none';

  try {
    const res = await fetch('/api/runs/' + run_id + '/tasks/' + task_file);
    const events = await res.json();
    renderHistory(events);
  } catch(e) {
    document.getElementById('turns').innerHTML = '<div class="waiting">Failed to load.</div>';
  }
}

function renderHistory(events) {
  const container = document.getElementById('turns');
  container.innerHTML = '';
  // Group events by turn
  const turns = {};
  for (const ev of events) {
    const t = ev.turn || 0;
    if (!turns[t]) turns[t] = [];
    turns[t].push(ev);
  }
  for (const n of Object.keys(turns).map(Number).sort((a,b)=>a-b)) {
    renderTurnFromEvents(n, turns[n]);
  }
  // Update token bar from last response
  const lastResp = [...events].reverse().find(e => e.type === 'response');
  if (lastResp?.data?.usage?.input) updateTokenBar(lastResp.data.usage.input);
  if (S.autoScroll) scrollBottom();
}

function renderTurnFromEvents(n, events) {
  const ctx = events.find(e => e.type === 'context');
  const resp = events.find(e => e.type === 'response');
  const tools = events.filter(e => e.type === 'tool_result');
  if (!ctx) return;
  addTurnCard(n, ctx.data, resp ? resp.data : null, tools.map(e => e.data));
}

// ---- Live event application ----
function applyEvent(ev) {
  const n = ev.turn;
  const cardId = 'tc-' + n;
  if (ev.type === 'context') {
    if (!document.getElementById(cardId)) {
      addTurnCard(n, ev.data, null, []);
    }
  } else if (ev.type === 'response') {
    if (!document.getElementById(cardId)) return;
    fillResponse(n, ev.data);
    fillStats(n, ev.data);
  } else if (ev.type === 'tool_result') {
    if (!document.getElementById(cardId)) return;
    appendToolResult(n, ev.data);
  }
}

// ---- Turn rendering ----
function addTurnCard(n, ctx, resp, toolResults) {
  const container = document.getElementById('turns');
  // Remove empty state
  const empty = document.getElementById('empty');
  if (empty) empty.remove();

  const card = document.createElement('div');
  card.className = 'turn-card';
  card.id = 'tc-' + n;
  const isFirst = n === 1;

  card.innerHTML = `
    <div class="turn-hdr">
      <span class="t-num">Turn ${n}</span>
      <span class="st">msgs: <b>${ctx.messages.length}</b></span>
      <span class="st">tools: <b>${ctx.tool_count}</b></span>
      <div class="t-stats" id="ts-${n}"><span style="color:#555">—</span></div>
    </div>
    ${secSys(ctx.system_prompt, isFirst)}
    ${secMsgs(ctx.messages)}
    ${secTools(ctx.tools)}
    <div id="tr-${n}">${resp ? '' : '<div class="waiting">Waiting for model…</div>'}</div>`;

  container.appendChild(card);

  if (resp) fillResponse(n, resp);
  if (resp) fillStats(n, resp);
  for (const t of toolResults) appendToolResult(n, t);
}

function fillStats(n, resp) {
  const el = document.getElementById('ts-' + n);
  if (!el || !resp.usage) return;
  const u = resp.usage;
  const cp = u.input > 0 ? Math.round(u.cache_read / u.input * 100) : 0;
  el.innerHTML = `
    <span class="st">in: <b>${(u.input||0).toLocaleString()}</b></span>
    <span class="st">out: <b>${(u.output||0).toLocaleString()}</b></span>
    ${u.cache_read ? `<span class="st">cache: <b>${cp}%</b></span>` : ''}
    ${u.ttft_seconds ? `<span class="st">TTFT: <b>${u.ttft_seconds.toFixed(2)}s</b></span>` : ''}
    <span class="st">stop: <b>${resp.stop_reason||''}</b></span>`;
}

function fillResponse(n, resp) {
  const el = document.getElementById('tr-' + n);
  if (!el) return;
  const html = (resp.content || []).map(renderBlock).join('');
  el.innerHTML = `<div class="sec">
    <div class="sec-hdr" onclick="togSec(this)">
      <span class="sec-arr o">▶</span>
      <span class="sec-title">Model Response</span>
      <span class="sec-meta">${resp.stop_reason||''}</span>
    </div>
    <div class="sec-body o">
      <div class="msg assistant">${html || '<span style="color:#555">no text content</span>'}</div>
    </div>
  </div>`;
}

function appendToolResult(n, data) {
  const el = document.getElementById('tr-' + n);
  if (!el) return;
  const txt = (data.result || []).map(c => c.text || '').join('');
  const isErr = data.is_error;
  const div = document.createElement('div');
  div.className = 'sec';
  div.innerHTML = `
    <div class="sec-hdr" onclick="togSec(this)">
      <span class="sec-arr">▶</span>
      <span class="sec-title" style="color:${isErr?'#f48771':'#4ec9b0'}">Tool Result: ${esc(data.tool_name)}</span>
      <span class="sec-meta">${isErr?'error':'ok'}</span>
    </div>
    <div class="sec-body">
      <div style="font-size:11px;color:#858585;margin-bottom:3px">args: ${esc(JSON.stringify(data.arguments))}</div>
      <div style="white-space:pre-wrap;color:#9cdcfe;font-size:12px">${esc(txt)}</div>
    </div>`;
  el.appendChild(div);
}

// ---- Section builders ----
function secSys(text, expanded) {
  if (!text) return '';
  return `<div class="sec">
    <div class="sec-hdr" onclick="togSec(this)">
      <span class="sec-arr${expanded?' o':''}">▶</span>
      <span class="sec-title">System Prompt</span>
      <span class="sec-meta">${text.length} chars</span>
    </div>
    <div class="sec-body${expanded?' o':''}"><div class="sys-text">${esc(text)}</div></div>
  </div>`;
}

function secMsgs(msgs) {
  if (!msgs.length) return '';
  return `<div class="sec">
    <div class="sec-hdr" onclick="togSec(this)">
      <span class="sec-arr o">▶</span>
      <span class="sec-title">Messages</span>
      <span class="sec-meta">${msgs.length}</span>
    </div>
    <div class="sec-body o">${msgs.map(renderMsg).join('')}</div>
  </div>`;
}

function secTools(tools) {
  if (!tools || !tools.length) return '';
  const rows = tools.map(t => `
    <div class="tool-row">
      <div class="tool-name">${esc(t.name)}</div>
      <div class="tool-desc">${esc(t.description||'')}</div>
      <div class="tool-schema-hdr" onclick="this.nextElementSibling.classList.toggle('o')">
        <span>▶</span> parameters schema
      </div>
      <div class="tool-schema-body">${esc(JSON.stringify(t.parameters, null, 2))}</div>
    </div>`).join('');
  return `<div class="sec">
    <div class="sec-hdr" onclick="togSec(this)">
      <span class="sec-arr">▶</span>
      <span class="sec-title">Tools in Context</span>
      <span class="sec-meta">${tools.length}</span>
    </div>
    <div class="sec-body">${rows}</div>
  </div>`;
}

// ---- Message / block rendering ----
function renderMsg(m) {
  const label = m.role === 'tool_result' ? `TOOL RESULT (${m.tool_name||''})` : m.role.toUpperCase();
  let body = '';
  if (m.role === 'user') {
    const txt = typeof m.content === 'string' ? m.content : (m.content||[]).map(c=>c.text||'').join('');
    body = `<div class="msg-text">${esc(txt)}</div>`;
  } else if (m.role === 'assistant') {
    body = (m.content||[]).map(renderBlock).join('');
  } else if (m.role === 'tool_result') {
    const txt = (m.content||[]).map(c=>c.text||'').join('');
    body = `<div class="b-tr">
      <div class="b-tr-hdr${m.is_error?' err':''}" onclick="togInline(this)">
        <span>▶</span>${m.is_error?'Error':'Result'}<span style="font-size:10px;color:#555;margin-left:4px">(click to expand)</span>
      </div>
      <div class="b-tr-body">${esc(txt)}</div>
    </div>`;
  }
  return `<div class="msg ${m.role}">
    <div class="msg-role r-${m.role}">${label}</div>${body}
  </div>`;
}

function renderBlock(b) {
  if (b.type === 'text') return `<div class="msg-text">${esc(b.text)}</div>`;
  if (b.type === 'thinking') {
    const prev = b.thinking.slice(0, 80).replace(/\n/g,' ');
    return `<div class="b-think">
      <div class="b-think-hdr" onclick="togInline(this)">
        <span>▶</span> Thinking (${b.thinking.length} chars)
        <span style="font-size:10px;color:#555;margin-left:6px">${esc(prev)}…</span>
      </div>
      <div class="b-think-body">${esc(b.thinking)}</div>
    </div>`;
  }
  if (b.type === 'tool_call') return `<div class="b-tc">
    <div class="b-tc-name">🔧 ${esc(b.name)}</div>
    <div class="b-tc-args">${esc(JSON.stringify(b.arguments, null, 2))}</div>
  </div>`;
  return '';
}

// ---- UI helpers ----
function togSec(hdr) {
  hdr.nextElementSibling.classList.toggle('o');
  hdr.querySelector('.sec-arr').classList.toggle('o');
}
function togInline(el) {
  el.nextElementSibling.classList.toggle('o');
  el.querySelector('span:first-child').textContent =
    el.nextElementSibling.classList.contains('o') ? '▼' : '▶';
}
function toggleAS() {
  S.autoScroll = !S.autoScroll;
  document.getElementById('as-btn').classList.toggle('on', S.autoScroll);
}
function updateTokenBar(tokens) {
  const pct = Math.min(tokens / S.ctxWin * 100, 100);
  document.getElementById('tok-fill').style.width = pct + '%';
  document.getElementById('tok-label').textContent =
    `${tokens.toLocaleString()} / ${(S.ctxWin/1000).toFixed(0)}K tokens (${pct.toFixed(1)}%)`;
  document.getElementById('tok-wrap').style.display = '';
}
function scrollBottom() {
  const c = document.getElementById('turns');
  c.scrollTop = c.scrollHeight;
}
function _safe(s) { return s ? s.replace(/[^\w\-]/g, '_') : s; }
function esc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ---- Init ----
loadRuns();
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
