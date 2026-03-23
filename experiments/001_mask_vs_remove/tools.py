"""8 deterministic tools for the mask vs remove experiment."""

from __future__ import annotations

import math

from core.tools import AgentTool, tool
from tools.calculator import calculator


# --- Tool 2: string_reverse ---

async def _string_reverse_exec(tool_call_id: str, params: dict) -> dict:
    text = params["text"]
    return {"original": text, "reversed": text[::-1]}

string_reverse = tool(
    name="string_reverse",
    description="Reverse a string. Returns the input string reversed.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The string to reverse"},
        },
        "required": ["text"],
    },
)(_string_reverse_exec)


# --- Tool 3: char_count ---

async def _char_count_exec(tool_call_id: str, params: dict) -> dict:
    text = params["text"]
    char = params["char"]
    count = text.count(char)
    return {"text": text, "char": char, "count": count}

char_count = tool(
    name="char_count",
    description="Count the number of occurrences of a character in a string.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The text to search in"},
            "char": {"type": "string", "description": "The character to count (single character)"},
        },
        "required": ["text", "char"],
    },
)(_char_count_exec)


# --- Tool 4: base_convert ---

async def _base_convert_exec(tool_call_id: str, params: dict) -> dict:
    number_str = params["number"]
    from_base = params["from_base"]
    to_base = params["to_base"]
    decimal_value = int(number_str, from_base)
    if to_base == 10:
        result = str(decimal_value)
    elif to_base == 2:
        result = bin(decimal_value)[2:]
    elif to_base == 8:
        result = oct(decimal_value)[2:]
    elif to_base == 16:
        result = hex(decimal_value)[2:]
    else:
        digits = []
        n = decimal_value
        while n > 0:
            digits.append(str(n % to_base))
            n //= to_base
        result = "".join(reversed(digits)) if digits else "0"
    return {"original": number_str, "from_base": from_base, "to_base": to_base, "result": result}

base_convert = tool(
    name="base_convert",
    description="Convert a number between different bases (2, 8, 10, 16, etc.).",
    parameters={
        "type": "object",
        "properties": {
            "number": {"type": "string", "description": "The number as a string"},
            "from_base": {"type": "integer", "description": "The base of the input number"},
            "to_base": {"type": "integer", "description": "The target base"},
        },
        "required": ["number", "from_base", "to_base"],
    },
)(_base_convert_exec)


# --- Tool 5: caesar_cipher ---

async def _caesar_cipher_exec(tool_call_id: str, params: dict) -> dict:
    text = params["text"]
    shift = params["shift"]
    mode = params.get("mode", "encode")
    if mode == "decode":
        shift = -shift
    result = []
    for ch in text:
        if ch.isalpha():
            base = ord("A") if ch.isupper() else ord("a")
            result.append(chr((ord(ch) - base + shift) % 26 + base))
        else:
            result.append(ch)
    return {"original": text, "shift": params["shift"], "mode": mode, "result": "".join(result)}

caesar_cipher = tool(
    name="caesar_cipher",
    description="Encode or decode text using Caesar cipher with a given shift value.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The text to encode/decode"},
            "shift": {"type": "integer", "description": "The shift value (1-25)"},
            "mode": {
                "type": "string",
                "enum": ["encode", "decode"],
                "description": "Whether to encode or decode. Default: encode",
            },
        },
        "required": ["text", "shift"],
    },
)(_caesar_cipher_exec)


# --- Tool 6: temperature_convert ---

async def _temperature_convert_exec(tool_call_id: str, params: dict) -> dict:
    value = params["value"]
    from_unit = params["from_unit"].upper()
    to_unit = params["to_unit"].upper()
    # Convert to Celsius first
    if from_unit == "C":
        celsius = value
    elif from_unit == "F":
        celsius = (value - 32) * 5 / 9
    elif from_unit == "K":
        celsius = value - 273.15
    else:
        return {"error": f"Unknown unit: {from_unit}"}
    # Convert from Celsius to target
    if to_unit == "C":
        result = celsius
    elif to_unit == "F":
        result = celsius * 9 / 5 + 32
    elif to_unit == "K":
        result = celsius + 273.15
    else:
        return {"error": f"Unknown unit: {to_unit}"}
    return {"value": value, "from_unit": from_unit, "to_unit": to_unit, "result": round(result, 2)}

temperature_convert = tool(
    name="temperature_convert",
    description="Convert temperature between Celsius (C), Fahrenheit (F), and Kelvin (K).",
    parameters={
        "type": "object",
        "properties": {
            "value": {"type": "number", "description": "The temperature value"},
            "from_unit": {"type": "string", "description": "Source unit: C, F, or K"},
            "to_unit": {"type": "string", "description": "Target unit: C, F, or K"},
        },
        "required": ["value", "from_unit", "to_unit"],
    },
)(_temperature_convert_exec)


# --- Tool 7: gcd ---

async def _gcd_exec(tool_call_id: str, params: dict) -> dict:
    a, b = params["a"], params["b"]
    result = math.gcd(a, b)
    return {"a": a, "b": b, "gcd": result}

gcd = tool(
    name="gcd",
    description="Calculate the greatest common divisor (GCD) of two integers.",
    parameters={
        "type": "object",
        "properties": {
            "a": {"type": "integer", "description": "First integer"},
            "b": {"type": "integer", "description": "Second integer"},
        },
        "required": ["a", "b"],
    },
)(_gcd_exec)


# --- Tool 8: word_count ---

async def _word_count_exec(tool_call_id: str, params: dict) -> dict:
    text = params["text"]
    words = text.split()
    return {"text": text, "word_count": len(words)}

word_count = tool(
    name="word_count",
    description="Count the number of words in a text string (split by whitespace).",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The text to count words in"},
        },
        "required": ["text"],
    },
)(_word_count_exec)


# --- All tools list ---

ALL_TOOLS: list[AgentTool] = [
    calculator,
    string_reverse,
    char_count,
    base_convert,
    caesar_cipher,
    temperature_convert,
    gcd,
    word_count,
]
