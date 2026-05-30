# 014 Multi-Agent Coordination Architecture Comparison

Compare three agent coordination architectures across three agentic benchmarks.

## Architectures

| Mode (id) | Description |
|---|---|
| **Single** (`single`) | One agent, all tools available, full observation in single context |
| **Swarm** (`sw`) | `TeamCreate` + 2 teammates (planner + executor) communicating via mailbox |
| **Verify** (`owv`) | Lead solves freely; **must** spawn `verifier` subagent before final ANSWER. Verifier independently re-checks via tools |

## Benchmarks

| Benchmark | Source | What it measures |
|---|---|---|
| WorkBench | https://github.com/olly-styles/WorkBench | Workplace task execution (calendar/email/CRM/etc) |
| FinanceBench | https://github.com/patronus-ai/financebench | SEC 10-K Q&A — multi-step retrieval |
| PlanCraft | https://github.com/gautierdag/plancraft | Minecraft crafting — strong sequential dependency |

Each benchmark contributes 30 tasks (10 easy / 10 medium / 10 hard); 3 modes × 90 tasks = **270 runs**.

## Setup

```bash
# 1. Vendored benchmarks (not committed; clone yourself)
mkdir -p _vendor && cd _vendor
git clone --depth 1 https://github.com/olly-styles/WorkBench.git
mkdir -p financebench
curl -fsSL https://raw.githubusercontent.com/patronus-ai/financebench/main/data/financebench_open_source.jsonl \
  -o financebench/financebench_open_source.jsonl
cd ..

# 2. Python deps
pip install plancraft fanoutqa evalplus mcp fastapi uvicorn pydantic boto3 datasets

# 3. Set CC binary path (if not on PATH)
export CLAUDE_BIN=/path/to/claude

# 4. Sample tasks
cd pilot
python3 prepare_workbench.py 30
python3 prepare_financebench.py 30
python3 prepare_plancraft.py 30

# 5. Start dashboard
python3 -m uvicorn dashboard.server:app --host 127.0.0.1 --port 7799 &

# 6. Run pilot — 90 tasks × 2 modes (single + sw) ≈ 12h
PILOT_MODES=single,sw python3 run_full_pilot.py 30

# 7. Run Verify mode (90 tasks) ≈ 1.5h
PILOT_MODES=owv python3 run_full_pilot.py 30
```

Dashboard at http://127.0.0.1:7799 — score matrix, per-run tool/message timeline, fs trace for swarm runs.

## Files

- `mcp_servers/` — three MCP servers exposing benchmark tools (sandbox-isolated per task)
- `runner/cc_runner.py` — unified `run_single / run_ow / run_sw` API; SW gets `SwarmFsWatcher` for mailbox observability
- `pilot/run_full_pilot.py` — main pilot driver with `PILOT_MODES` env var to select modes
- `pilot/run_owv_demo.py` — manual single-task demo of the Verify protocol
- `pilot/dashboard/` — FastAPI server + static UI for live observation
- `results/multi-agent-experiment.md` — main report (Chinese)
- `results/analysis.md` — earlier analysis (Chinese)
- `results/data/runs_slim.jsonl` — 270 runs, slimmed (no raw_stream / fs_trace), ~800KB

## Probe Files

`probe_pty/` — early feasibility probes (pty-based CC driver, MCP server bring-up). Kept for reference; superseded by the full pilot.

## Key Findings

- **Single > Verify ≈ 0% gap** on WorkBench / FinanceBench; Single beats Verify by 7pp on PlanCraft
- **Swarm trails by 18pp overall** (63% vs 81%); on PlanCraft medium drops to 30% vs Single 100%
- **Verify costs +68% tokens** vs Single — verifier independently re-runs tools, lead also continues to act after verifier returns
- **PlanCraft Medium is the largest divergence**: strong sequential dependency breaks swarm's plan-execute split

See `results/multi-agent-experiment.md` for full analysis with failure case studies.
