"""
WorkBench MCP server.

One process per task. Loads a fresh sandbox at startup, exposes all 26
WorkBench tools as MCP tools, and dumps the final sandbox state to a JSON
file when shutting down so an external verifier can compare against
ground truth.

Env vars:
- WBENCH_REPO  : absolute path to the cloned WorkBench repo
- WBENCH_TASK_ID : task identifier; final state goes to /tmp/wbench_state_<id>.json
- WBENCH_STATE_OUT : optional override path for state dump

Run as: python3 workbench_server.py
"""
from __future__ import annotations

import atexit
import json
import os
import sys
from typing import Any

WBENCH_REPO = os.environ.get("WBENCH_REPO")
if not WBENCH_REPO or not os.path.isdir(WBENCH_REPO):
    print(f"WBENCH_REPO not set or not a dir: {WBENCH_REPO!r}", file=sys.stderr)
    sys.exit(2)

# WorkBench tools use relative paths like data/processed/calendar_events.csv
# so we must chdir into the repo before importing.
os.chdir(WBENCH_REPO)
sys.path.insert(0, WBENCH_REPO)

# Import WorkBench domain modules. Each module loads its CSV at import time.
from src.tools import (  # noqa: E402
    calendar,
    email as email_mod,
    analytics,
    project_management,
    customer_relationship_manager as crm,
    company_directory,
)

# Reset all states for a clean run.
calendar.reset_state()
email_mod.reset_state()
analytics.reset_state()
project_management.reset_state()
crm.reset_state()

DOMAIN_MODULES = {
    "calendar": calendar,
    "email": email_mod,
    "analytics": analytics,
    "project_management": project_management,
    "customer_relationship_manager": crm,
    "company_directory": company_directory,
}

STATE_VARS = {
    "calendar": "CALENDAR_EVENTS",
    "email": "EMAILS",
    "analytics": "PLOTS_DATA",
    "project_management": "PROJECT_TASKS",
    "customer_relationship_manager": "CRM_DATA",
    "company_directory": None,
}


import threading as _threading  # noqa: E402

_DUMP_LOCK = _threading.Lock()


def dump_state():
    """Write final sandbox state for verifier (atomic write to avoid races)."""
    out = {}
    for dom, var in STATE_VARS.items():
        if var is None:
            continue
        mod = DOMAIN_MODULES[dom]
        if hasattr(mod, var):
            df = getattr(mod, var)
            if hasattr(df, "to_dict"):
                out[dom] = df.to_dict(orient="records")
    out_path = os.environ.get(
        "WBENCH_STATE_OUT",
        f"/tmp/wbench_state_{os.environ.get('WBENCH_TASK_ID', 'default')}.json",
    )
    tmp_path = out_path + ".tmp"
    try:
        with _DUMP_LOCK:
            with open(tmp_path, "w") as f:
                json.dump(out, f, default=str)
            os.replace(tmp_path, out_path)
    except Exception as e:
        print(f"failed to dump state to {out_path}: {e}", file=sys.stderr)


atexit.register(dump_state)


# Also dump on SIGTERM/SIGINT (CC closes stdio without giving us a clean exit).
import signal as _signal  # noqa: E402

def _sig_handler(signum, frame):
    dump_state()
    sys.exit(0)

for _sig in (_signal.SIGTERM, _signal.SIGINT, _signal.SIGHUP):
    try:
        _signal.signal(_sig, _sig_handler)
    except Exception:
        pass


# -------- Build MCP tool wrappers --------
from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp_server = FastMCP("workbench")


import inspect  # noqa: E402


def _make_wrapper(name: str, underlying):
    """Build a wrapper that exposes the same signature as `underlying` so FastMCP
    can introspect parameter names/types. Returns the wrapper callable."""
    sig = inspect.signature(underlying)

    # Build a real Python function with the same signature (string-typed args).
    # We use exec to synthesize so the signature is preserved literally.
    params = list(sig.parameters.values())
    arg_names = [p.name for p in params]
    # all WorkBench tool args are str|None with default None (or '' for queries)
    # Build "param=None, ..." or use original default
    def _fmt_default(p):
        if p.default is inspect.Parameter.empty:
            return ""
        d = p.default
        if d is None:
            return "=None"
        if isinstance(d, str):
            return f"={d!r}"
        return f"={d!r}"
    sig_str = ", ".join(f"{p.name}: str{_fmt_default(p)}" for p in params)
    src = (
        f"def _wrapper({sig_str}):\n"
        f"    try:\n"
        f"        kwargs = {{ {', '.join(f'{a!r}: {a}' for a in arg_names)} }}\n"
        f"        result = _underlying(**kwargs)\n"
        f"        try: _dump_state()\n"
        f"        except Exception: pass\n"
        f"        return result if isinstance(result, (str, dict, list, int, float, bool)) else str(result)\n"
        f"    except Exception as e:\n"
        f"        return f'ERROR: {{type(e).__name__}}: {{e}}'\n"
    )
    ns: dict = {"_underlying": underlying, "_dump_state": dump_state}
    exec(src, ns)
    wrapper = ns["_wrapper"]
    wrapper.__name__ = name.replace(".", "_")
    wrapper.__doc__ = (underlying.__doc__ or "").strip()
    return wrapper


def _register_tool(full_name: str, underlying):
    wrapper = _make_wrapper(full_name, underlying)
    desc = (underlying.__doc__ or "").strip().split("\n")[0][:200] or full_name
    mcp_server.tool(name=full_name.replace(".", "_"), description=desc)(wrapper)


# Register every WorkBench tool. Iterate over modules' attributes finding
# objects with .name and .func (LangChain @tool wrappers).
_seen = set()
for dom_name, mod in DOMAIN_MODULES.items():
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if hasattr(obj, "name") and hasattr(obj, "func") and callable(obj.func):
            tool_full_name = obj.name
            if tool_full_name in _seen:
                continue
            _seen.add(tool_full_name)
            try:
                _register_tool(tool_full_name, obj.func)
            except Exception as e:
                print(f"  ! failed to wrap {tool_full_name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    print(f"workbench MCP server starting (repo={WBENCH_REPO})", file=sys.stderr)
    n_tools = len(mcp_server._tool_manager._tools) if hasattr(mcp_server, "_tool_manager") else "?"
    print(f"  registered {n_tools} tools", file=sys.stderr)
    mcp_server.run(transport="stdio")
