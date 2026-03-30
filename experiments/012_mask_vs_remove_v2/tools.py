"""Tool definitions for Experiment 012 v3.

60 tools organized into 12 named groups with common prefixes.
- 4 active groups (math_, text_, unit_, code_): 5 tools each = 20 active tools
- 8 filler groups (auth_, file_, net_, db_, sys_, log_, cache_, queue_): 5 tools each = 40 filler tools

Group-level prefix design guarantees zero token collision:
  - Each group has a unique prefix word (math, text, unit, code, auth, ...)
  - mask_logit blocks an entire group's prefix token when that group is unavailable
  - The available group's prefix token NEVER enters logit_bias → collision-free
"""

from __future__ import annotations

from typing import Any

from core.tools import AgentTool


# ── Parameter helpers ─────────────────────────────────────────────────────────

def _str_param(desc: str) -> dict:
    return {"type": "string", "description": desc}


def _num_param(desc: str) -> dict:
    return {"type": "number", "description": desc}


def _int_param(desc: str) -> dict:
    return {"type": "integer", "description": desc}


def _make_tool(name: str, description: str, properties: dict, required: list[str]) -> AgentTool:
    async def execute(tool_call_id: str, params: dict[str, Any]) -> dict:
        return {"result": f"{name}_result", "status": "ok", "input": params}
    return AgentTool(
        name=name,
        description=description,
        parameters={"type": "object", "properties": properties, "required": required},
        execute=execute,
    )


# ── Active group 1: math_ ─────────────────────────────────────────────────────

MATH_TOOLS: list[AgentTool] = [
    _make_tool(
        "math_add",
        "Add two numbers together and return the sum.",
        {"a": _num_param("First number"), "b": _num_param("Second number")},
        ["a", "b"],
    ),
    _make_tool(
        "math_gcd",
        "Compute the greatest common divisor (GCD) of two integers.",
        {"a": _int_param("First integer"), "b": _int_param("Second integer")},
        ["a", "b"],
    ),
    _make_tool(
        "math_sqrt",
        "Compute the square root of a non-negative number.",
        {"value": _num_param("Non-negative number")},
        ["value"],
    ),
    _make_tool(
        "math_factorial",
        "Compute the factorial of a non-negative integer.",
        {"n": _int_param("Non-negative integer")},
        ["n"],
    ),
    _make_tool(
        "math_power",
        "Raise a base number to an integer exponent.",
        {"base": _num_param("Base number"), "exp": _int_param("Exponent")},
        ["base", "exp"],
    ),
]

# ── Active group 2: text_ ─────────────────────────────────────────────────────

TEXT_TOOLS: list[AgentTool] = [
    _make_tool(
        "text_reverse",
        "Reverse the characters in a string.",
        {"value": _str_param("Input string to reverse")},
        ["value"],
    ),
    _make_tool(
        "text_count_chars",
        "Count the number of characters in a string.",
        {"value": _str_param("Input string")},
        ["value"],
    ),
    _make_tool(
        "text_count_words",
        "Count the number of words in a string.",
        {"value": _str_param("Input string")},
        ["value"],
    ),
    _make_tool(
        "text_upper",
        "Convert a string to uppercase.",
        {"value": _str_param("Input string")},
        ["value"],
    ),
    _make_tool(
        "text_lower",
        "Convert a string to lowercase.",
        {"value": _str_param("Input string")},
        ["value"],
    ),
]

# ── Active group 3: unit_ ─────────────────────────────────────────────────────

UNIT_TOOLS: list[AgentTool] = [
    _make_tool(
        "unit_temp",
        "Convert a temperature value between Celsius, Fahrenheit, and Kelvin.",
        {
            "value": _num_param("Temperature value"),
            "from_unit": _str_param("Source unit: celsius, fahrenheit, or kelvin"),
            "to_unit": _str_param("Target unit: celsius, fahrenheit, or kelvin"),
        },
        ["value", "from_unit", "to_unit"],
    ),
    _make_tool(
        "unit_base",
        "Convert a number between numeric bases (e.g. decimal to binary, hex to octal).",
        {
            "value": _str_param("Number as string in source base"),
            "from_base": _int_param("Source base (2–36)"),
            "to_base": _int_param("Target base (2–36)"),
        },
        ["value", "from_base", "to_base"],
    ),
    _make_tool(
        "unit_miles",
        "Convert a distance between miles and kilometers.",
        {
            "value": _num_param("Distance value"),
            "direction": _str_param("Conversion direction: miles_to_km or km_to_miles"),
        },
        ["value", "direction"],
    ),
    _make_tool(
        "unit_kg",
        "Convert a weight between kilograms and pounds.",
        {
            "value": _num_param("Weight value"),
            "direction": _str_param("Conversion direction: kg_to_pounds or pounds_to_kg"),
        },
        ["value", "direction"],
    ),
    _make_tool(
        "unit_bytes",
        "Convert a data size between bytes, KB, MB, and GB.",
        {
            "value": _num_param("Size value"),
            "from_unit": _str_param("Source unit: bytes, kb, mb, or gb"),
            "to_unit": _str_param("Target unit: bytes, kb, mb, or gb"),
        },
        ["value", "from_unit", "to_unit"],
    ),
]

# ── Active group 4: code_ ─────────────────────────────────────────────────────

CODE_TOOLS: list[AgentTool] = [
    _make_tool(
        "code_caesar",
        "Apply a Caesar cipher shift to a text string.",
        {"text": _str_param("Input text"), "shift": _int_param("Shift amount (1–25)")},
        ["text", "shift"],
    ),
    _make_tool(
        "code_rot13",
        "Apply ROT13 substitution cipher to a text string.",
        {"text": _str_param("Input text")},
        ["text"],
    ),
    _make_tool(
        "code_base64",
        "Encode or decode a string using Base64.",
        {
            "text": _str_param("Input text"),
            "mode": _str_param("Operation: encode or decode"),
        },
        ["text", "mode"],
    ),
    _make_tool(
        "code_hex",
        "Encode or decode a string using hexadecimal representation.",
        {
            "text": _str_param("Input text"),
            "mode": _str_param("Operation: encode or decode"),
        },
        ["text", "mode"],
    ),
    _make_tool(
        "code_md5",
        "Compute the MD5 hash of a string.",
        {"text": _str_param("Input text to hash")},
        ["text"],
    ),
]

ACTIVE_TOOLS: list[AgentTool] = MATH_TOOLS + TEXT_TOOLS + UNIT_TOOLS + CODE_TOOLS


# ── Filler group builder ──────────────────────────────────────────────────────

def _filler_group(prefix: str, suffixes: list[tuple[str, str]]) -> list[AgentTool]:
    """Build 5 filler tools with a common prefix."""
    tools = []
    for suffix, desc in suffixes:
        tools.append(_make_tool(
            f"{prefix}_{suffix}",
            desc,
            {"value": _str_param("Input value")},
            ["value"],
        ))
    return tools


AUTH_TOOLS = _filler_group("auth", [
    ("login",   "Authenticate a user and return a session token."),
    ("logout",  "Invalidate an existing session token."),
    ("refresh", "Refresh an expiring session token."),
    ("verify",  "Verify that a session token is valid."),
    ("reset",   "Send a password reset link to a user email."),
])

FILE_TOOLS = _filler_group("file", [
    ("read",    "Read the contents of a file at the given path."),
    ("write",   "Write text content to a file at the given path."),
    ("delete",  "Delete a file at the given path."),
    ("copy",    "Copy a file from source path to destination path."),
    ("rename",  "Rename a file at the given path to a new name."),
])

NET_TOOLS = _filler_group("net", [
    ("ping",    "Ping a host and return round-trip latency."),
    ("resolve", "Resolve a domain name to its IP addresses."),
    ("fetch",   "Fetch the raw HTTP response from a URL."),
    ("scan",    "Scan open ports on a given host."),
    ("trace",   "Trace the network path to a given host."),
])

DB_TOOLS = _filler_group("db", [
    ("query",   "Execute a read-only SQL query and return rows."),
    ("insert",  "Insert a record into a database table."),
    ("update",  "Update matching records in a database table."),
    ("delete",  "Delete matching records from a database table."),
    ("schema",  "Return the schema definition for a database table."),
])

SYS_TOOLS = _filler_group("sys", [
    ("info",    "Return operating system and hardware information."),
    ("env",     "Read an environment variable by name."),
    ("kill",    "Terminate a process by its PID."),
    ("disk",    "Return disk usage statistics for a given path."),
    ("uptime",  "Return how long the system has been running."),
])

LOG_TOOLS = _filler_group("log", [
    ("write",   "Append a log entry at the given severity level."),
    ("read",    "Read recent log entries filtered by level or keyword."),
    ("clear",   "Clear log entries older than a given number of days."),
    ("export",  "Export log entries to a file in the given format."),
    ("search",  "Search log entries matching a given pattern."),
])

CACHE_TOOLS = _filler_group("cache", [
    ("get",     "Retrieve a value from the cache by key."),
    ("set",     "Store a value in the cache with an optional TTL."),
    ("delete",  "Remove a key-value pair from the cache."),
    ("flush",   "Clear all entries from the cache."),
    ("stats",   "Return cache hit/miss statistics."),
])

QUEUE_TOOLS = _filler_group("queue", [
    ("push",    "Push a message onto the end of a named queue."),
    ("pop",     "Pop and return the next message from a named queue."),
    ("peek",    "Peek at the next message without removing it."),
    ("length",  "Return the current length of a named queue."),
    ("clear",   "Clear all messages from a named queue."),
])

FILLER_TOOLS: list[AgentTool] = (
    AUTH_TOOLS + FILE_TOOLS + NET_TOOLS + DB_TOOLS +
    SYS_TOOLS + LOG_TOOLS + CACHE_TOOLS + QUEUE_TOOLS
)

ALL_TOOLS: list[AgentTool] = FILLER_TOOLS + ACTIVE_TOOLS  # 60 tools total

# ── Group index ───────────────────────────────────────────────────────────────

TOOL_GROUPS: dict[str, list[str]] = {
    "math":  [t.name for t in MATH_TOOLS],
    "text":  [t.name for t in TEXT_TOOLS],
    "unit":  [t.name for t in UNIT_TOOLS],
    "code":  [t.name for t in CODE_TOOLS],
    "auth":  [t.name for t in AUTH_TOOLS],
    "file":  [t.name for t in FILE_TOOLS],
    "net":   [t.name for t in NET_TOOLS],
    "db":    [t.name for t in DB_TOOLS],
    "sys":   [t.name for t in SYS_TOOLS],
    "log":   [t.name for t in LOG_TOOLS],
    "cache": [t.name for t in CACHE_TOOLS],
    "queue": [t.name for t in QUEUE_TOOLS],
}

assert len(ALL_TOOLS) == 60, f"Expected 60 tools, got {len(ALL_TOOLS)}"
assert len(ACTIVE_TOOLS) == 20
assert len(FILLER_TOOLS) == 40
