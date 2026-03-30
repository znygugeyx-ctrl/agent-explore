"""Post-tool hook: warn when experiments/*/run.py is written without attach_observer.

Reads tool result JSON from stdin. If the Write tool wrote to an experiment
run.py and the content lacks attach_observer, prints a warning.
Exit code 0 (non-blocking) — attach_observer may be added later.
"""

import json
import re
import sys


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    content = tool_input.get("content", "")

    # Match experiments/<NNN>_*/run.py
    if not re.search(r"experiments/\d+_[^/]+/run\.py$", file_path):
        sys.exit(0)

    if "attach_observer" not in content:
        print(
            f"⚠️  WARNING: {file_path} does not call attach_observer.\n"
            "All experiments MUST attach the observer (see CLAUDE.md).\n"
            "Add: from observer.client import attach_observer\n"
            "     attach_observer(config, task_id=task.id, run_id=\"exp_NNN_name\")"
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
