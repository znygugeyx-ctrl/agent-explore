"""50 deterministic tools for Experiment 003: prefix cache validation.

Tools 1-10: "filler" tools at the FRONT of the list. These are the targets for
Remove/Mask strategies. Removing from the front maximally disrupts prefix cache.

Tools 11-50: "active" tools used by tasks. Includes the 8 original tools from
Exp 002 plus 32 new simple deterministic tools.
"""

from __future__ import annotations

import math
import hashlib

from core.tools import AgentTool, tool


# ============================================================
# FILLER TOOLS (positions 1-10) — targets for Remove/Mask
# ============================================================

async def _hex_encode_exec(tid: str, p: dict) -> dict:
    return {"result": p["text"].encode().hex()}

hex_encode = tool(
    name="hex_encode",
    description="Encode a string to its hexadecimal representation. Each character becomes two hex digits.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to hex-encode"},
    }, "required": ["text"]},
)(  _hex_encode_exec)


async def _hex_decode_exec(tid: str, p: dict) -> dict:
    return {"result": bytes.fromhex(p["hex_string"]).decode(errors="replace")}

hex_decode = tool(
    name="hex_decode",
    description="Decode a hexadecimal string back to its original text representation.",
    parameters={"type": "object", "properties": {
        "hex_string": {"type": "string", "description": "The hex string to decode"},
    }, "required": ["hex_string"]},
)(_hex_decode_exec)


async def _rot13_exec(tid: str, p: dict) -> dict:
    import codecs
    return {"result": codecs.encode(p["text"], "rot_13")}

rot13 = tool(
    name="rot13",
    description="Apply ROT13 substitution cipher to text. Each letter is shifted 13 positions in the alphabet.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The text to ROT13-encode"},
    }, "required": ["text"]},
)(_rot13_exec)


async def _ascii_value_exec(tid: str, p: dict) -> dict:
    return {"result": ord(p["character"])}

ascii_value = tool(
    name="ascii_value",
    description="Get the ASCII numeric value of a single character.",
    parameters={"type": "object", "properties": {
        "character": {"type": "string", "description": "A single character"},
    }, "required": ["character"]},
)(_ascii_value_exec)


async def _vowel_count_exec(tid: str, p: dict) -> dict:
    count = sum(1 for c in p["text"].lower() if c in "aeiou")
    return {"result": count}

vowel_count = tool(
    name="vowel_count",
    description="Count the number of vowels (a, e, i, o, u) in a given text string.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The text to count vowels in"},
    }, "required": ["text"]},
)(_vowel_count_exec)


async def _consonant_count_exec(tid: str, p: dict) -> dict:
    count = sum(1 for c in p["text"].lower() if c.isalpha() and c not in "aeiou")
    return {"result": count}

consonant_count = tool(
    name="consonant_count",
    description="Count the number of consonants (non-vowel letters) in a given text string.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The text to count consonants in"},
    }, "required": ["text"]},
)(_consonant_count_exec)


async def _is_palindrome_exec(tid: str, p: dict) -> dict:
    s = p["text"].lower().replace(" ", "")
    return {"result": s == s[::-1]}

is_palindrome = tool(
    name="is_palindrome",
    description="Check if a given text is a palindrome (reads the same forwards and backwards).",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The text to check"},
    }, "required": ["text"]},
)(_is_palindrome_exec)


async def _factorial_exec(tid: str, p: dict) -> dict:
    return {"result": math.factorial(int(p["n"]))}

factorial = tool(
    name="factorial",
    description="Calculate the factorial of a non-negative integer n. Returns n! = n * (n-1) * ... * 1.",
    parameters={"type": "object", "properties": {
        "n": {"type": "integer", "description": "Non-negative integer"},
    }, "required": ["n"]},
)(_factorial_exec)


async def _fibonacci_exec(tid: str, p: dict) -> dict:
    n = int(p["n"])
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return {"result": a}

fibonacci = tool(
    name="fibonacci",
    description="Calculate the nth Fibonacci number (0-indexed). F(0)=0, F(1)=1, F(n)=F(n-1)+F(n-2).",
    parameters={"type": "object", "properties": {
        "n": {"type": "integer", "description": "Index in Fibonacci sequence (0-based)"},
    }, "required": ["n"]},
)(_fibonacci_exec)


async def _prime_check_exec(tid: str, p: dict) -> dict:
    n = int(p["n"])
    if n < 2:
        return {"result": False}
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return {"result": False}
    return {"result": True}

prime_check = tool(
    name="prime_check",
    description="Check if a given integer is a prime number. Returns true if prime, false otherwise.",
    parameters={"type": "object", "properties": {
        "n": {"type": "integer", "description": "The integer to check for primality"},
    }, "required": ["n"]},
)(_prime_check_exec)


# ============================================================
# ACTIVE TOOLS (positions 11-50) — used by tasks
# ============================================================

# --- Original 8 tools from Exp 002 (positions 11-18) ---

from tools.calculator import calculator

async def _string_reverse_exec(tid: str, p: dict) -> dict:
    text = p["text"]
    return {"original": text, "reversed": text[::-1]}

string_reverse = tool(
    name="string_reverse",
    description="Reverse a string. Returns the input string reversed.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to reverse"},
    }, "required": ["text"]},
)(_string_reverse_exec)


async def _char_count_exec(tid: str, p: dict) -> dict:
    return {"count": p["text"].count(p["char"])}

char_count = tool(
    name="char_count",
    description="Count occurrences of a specific character in a string.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to search in"},
        "char": {"type": "string", "description": "The character to count"},
    }, "required": ["text", "char"]},
)(_char_count_exec)


async def _base_convert_exec(tid: str, p: dict) -> dict:
    value = int(str(p["number"]), int(p["from_base"]))
    to_base = int(p["to_base"])
    if to_base == 10:
        return {"result": str(value)}
    digits = []
    n = abs(value)
    while n:
        digits.append("0123456789abcdef"[n % to_base])
        n //= to_base
    result = "".join(reversed(digits)) or "0"
    if value < 0:
        result = "-" + result
    return {"result": result}

base_convert = tool(
    name="base_convert",
    description="Convert a number from one base to another (supports bases 2-16).",
    parameters={"type": "object", "properties": {
        "number": {"type": "string", "description": "The number to convert (as string)"},
        "from_base": {"type": "integer", "description": "The base of the input number"},
        "to_base": {"type": "integer", "description": "The target base"},
    }, "required": ["number", "from_base", "to_base"]},
)(_base_convert_exec)


async def _caesar_cipher_exec(tid: str, p: dict) -> dict:
    text, shift = p["text"], int(p["shift"])
    mode = p.get("mode", "encode")
    if mode == "decode":
        shift = -shift
    result = []
    for c in text:
        if c.isalpha():
            base = ord("A") if c.isupper() else ord("a")
            result.append(chr((ord(c) - base + shift) % 26 + base))
        else:
            result.append(c)
    return {"result": "".join(result)}

caesar_cipher = tool(
    name="caesar_cipher",
    description="Encode or decode text using Caesar cipher with a given shift value.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The text to encode/decode"},
        "shift": {"type": "integer", "description": "Number of positions to shift"},
        "mode": {"type": "string", "enum": ["encode", "decode"], "description": "encode or decode"},
    }, "required": ["text", "shift"]},
)(_caesar_cipher_exec)


async def _temperature_convert_exec(tid: str, p: dict) -> dict:
    val = float(p["value"])
    f, t = p["from_unit"].upper(), p["to_unit"].upper()
    if f == t:
        return {"result": val}
    conversions = {
        ("C", "F"): lambda v: v * 9 / 5 + 32,
        ("F", "C"): lambda v: (v - 32) * 5 / 9,
        ("C", "K"): lambda v: v + 273.15,
        ("K", "C"): lambda v: v - 273.15,
        ("F", "K"): lambda v: (v - 32) * 5 / 9 + 273.15,
        ("K", "F"): lambda v: (v - 273.15) * 9 / 5 + 32,
    }
    fn = conversions.get((f[0], t[0]))
    if fn is None:
        return {"error": f"Unknown conversion: {f} -> {t}"}
    return {"result": fn(val)}

temperature_convert = tool(
    name="temperature_convert",
    description="Convert temperature between Celsius, Fahrenheit, and Kelvin units.",
    parameters={"type": "object", "properties": {
        "value": {"type": "number", "description": "Temperature value"},
        "from_unit": {"type": "string", "description": "Source unit (C, F, or K)"},
        "to_unit": {"type": "string", "description": "Target unit (C, F, or K)"},
    }, "required": ["value", "from_unit", "to_unit"]},
)(_temperature_convert_exec)


async def _gcd_exec(tid: str, p: dict) -> dict:
    return {"result": math.gcd(int(p["a"]), int(p["b"]))}

gcd = tool(
    name="gcd",
    description="Find the greatest common divisor (GCD) of two integers using Euclidean algorithm.",
    parameters={"type": "object", "properties": {
        "a": {"type": "integer", "description": "First integer"},
        "b": {"type": "integer", "description": "Second integer"},
    }, "required": ["a", "b"]},
)(_gcd_exec)


async def _word_count_exec(tid: str, p: dict) -> dict:
    return {"count": len(p["text"].split())}

word_count = tool(
    name="word_count",
    description="Count the number of words in a text string (split by whitespace).",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The text to count words in"},
    }, "required": ["text"]},
)(_word_count_exec)


# --- New active tools (positions 19-50) ---

async def _lcm_exec(tid: str, p: dict) -> dict:
    a, b = int(p["a"]), int(p["b"])
    return {"result": abs(a * b) // math.gcd(a, b)}

lcm = tool(
    name="lcm",
    description="Find the least common multiple (LCM) of two integers.",
    parameters={"type": "object", "properties": {
        "a": {"type": "integer", "description": "First integer"},
        "b": {"type": "integer", "description": "Second integer"},
    }, "required": ["a", "b"]},
)(_lcm_exec)


async def _modulo_exec(tid: str, p: dict) -> dict:
    return {"result": int(p["a"]) % int(p["b"])}

modulo = tool(
    name="modulo",
    description="Calculate the remainder when dividing a by b (a mod b).",
    parameters={"type": "object", "properties": {
        "a": {"type": "integer", "description": "Dividend"},
        "b": {"type": "integer", "description": "Divisor"},
    }, "required": ["a", "b"]},
)(_modulo_exec)


async def _power_exec(tid: str, p: dict) -> dict:
    return {"result": int(p["base"]) ** int(p["exponent"])}

power = tool(
    name="power",
    description="Calculate base raised to the power of exponent (base^exponent).",
    parameters={"type": "object", "properties": {
        "base": {"type": "integer", "description": "The base number"},
        "exponent": {"type": "integer", "description": "The exponent"},
    }, "required": ["base", "exponent"]},
)(_power_exec)


async def _abs_value_exec(tid: str, p: dict) -> dict:
    return {"result": abs(float(p["number"]))}

abs_value = tool(
    name="abs_value",
    description="Calculate the absolute value of a number.",
    parameters={"type": "object", "properties": {
        "number": {"type": "number", "description": "The number"},
    }, "required": ["number"]},
)(_abs_value_exec)


async def _floor_div_exec(tid: str, p: dict) -> dict:
    return {"result": int(p["a"]) // int(p["b"])}

floor_div = tool(
    name="floor_div",
    description="Perform integer (floor) division of a by b, discarding the remainder.",
    parameters={"type": "object", "properties": {
        "a": {"type": "integer", "description": "Dividend"},
        "b": {"type": "integer", "description": "Divisor"},
    }, "required": ["a", "b"]},
)(_floor_div_exec)


async def _string_length_exec(tid: str, p: dict) -> dict:
    return {"result": len(p["text"])}

string_length = tool(
    name="string_length",
    description="Return the length (number of characters) of a text string.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to measure"},
    }, "required": ["text"]},
)(_string_length_exec)


async def _to_uppercase_exec(tid: str, p: dict) -> dict:
    return {"result": p["text"].upper()}

to_uppercase = tool(
    name="to_uppercase",
    description="Convert all characters in a string to uppercase.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to convert"},
    }, "required": ["text"]},
)(_to_uppercase_exec)


async def _to_lowercase_exec(tid: str, p: dict) -> dict:
    return {"result": p["text"].lower()}

to_lowercase = tool(
    name="to_lowercase",
    description="Convert all characters in a string to lowercase.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to convert"},
    }, "required": ["text"]},
)(_to_lowercase_exec)


async def _string_repeat_exec(tid: str, p: dict) -> dict:
    return {"result": p["text"] * int(p["times"])}

string_repeat = tool(
    name="string_repeat",
    description="Repeat a string a specified number of times.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to repeat"},
        "times": {"type": "integer", "description": "Number of repetitions"},
    }, "required": ["text", "times"]},
)(_string_repeat_exec)


async def _string_slice_exec(tid: str, p: dict) -> dict:
    return {"result": p["text"][int(p["start"]):int(p["end"])]}

string_slice = tool(
    name="string_slice",
    description="Extract a substring from start index to end index (exclusive).",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The source string"},
        "start": {"type": "integer", "description": "Start index (0-based, inclusive)"},
        "end": {"type": "integer", "description": "End index (exclusive)"},
    }, "required": ["text", "start", "end"]},
)(_string_slice_exec)


async def _replace_char_exec(tid: str, p: dict) -> dict:
    return {"result": p["text"].replace(p["old"], p["new"])}

replace_char = tool(
    name="replace_char",
    description="Replace all occurrences of a substring with another substring in text.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The source string"},
        "old": {"type": "string", "description": "Substring to find"},
        "new": {"type": "string", "description": "Replacement substring"},
    }, "required": ["text", "old", "new"]},
)(_replace_char_exec)


async def _count_digits_exec(tid: str, p: dict) -> dict:
    return {"result": sum(1 for c in str(p["text"]) if c.isdigit())}

count_digits = tool(
    name="count_digits",
    description="Count the number of digit characters (0-9) in a string.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to search"},
    }, "required": ["text"]},
)(_count_digits_exec)


async def _sum_digits_exec(tid: str, p: dict) -> dict:
    return {"result": sum(int(c) for c in str(p["number"]) if c.isdigit())}

sum_digits = tool(
    name="sum_digits",
    description="Calculate the sum of all digits in a number.",
    parameters={"type": "object", "properties": {
        "number": {"type": "integer", "description": "The number whose digits to sum"},
    }, "required": ["number"]},
)(_sum_digits_exec)


async def _is_even_exec(tid: str, p: dict) -> dict:
    return {"result": int(p["number"]) % 2 == 0}

is_even = tool(
    name="is_even",
    description="Check if an integer is even. Returns true if even, false if odd.",
    parameters={"type": "object", "properties": {
        "number": {"type": "integer", "description": "The integer to check"},
    }, "required": ["number"]},
)(_is_even_exec)


async def _max_of_two_exec(tid: str, p: dict) -> dict:
    return {"result": max(float(p["a"]), float(p["b"]))}

max_of_two = tool(
    name="max_of_two",
    description="Return the larger of two numbers.",
    parameters={"type": "object", "properties": {
        "a": {"type": "number", "description": "First number"},
        "b": {"type": "number", "description": "Second number"},
    }, "required": ["a", "b"]},
)(_max_of_two_exec)


async def _min_of_two_exec(tid: str, p: dict) -> dict:
    return {"result": min(float(p["a"]), float(p["b"]))}

min_of_two = tool(
    name="min_of_two",
    description="Return the smaller of two numbers.",
    parameters={"type": "object", "properties": {
        "a": {"type": "number", "description": "First number"},
        "b": {"type": "number", "description": "Second number"},
    }, "required": ["a", "b"]},
)(_min_of_two_exec)


async def _percentage_exec(tid: str, p: dict) -> dict:
    return {"result": float(p["part"]) / float(p["whole"]) * 100}

percentage = tool(
    name="percentage",
    description="Calculate what percentage 'part' is of 'whole'. Returns (part/whole)*100.",
    parameters={"type": "object", "properties": {
        "part": {"type": "number", "description": "The part value"},
        "whole": {"type": "number", "description": "The whole value"},
    }, "required": ["part", "whole"]},
)(_percentage_exec)


async def _round_number_exec(tid: str, p: dict) -> dict:
    return {"result": round(float(p["number"]), int(p.get("decimals", 0)))}

round_number = tool(
    name="round_number",
    description="Round a number to the specified number of decimal places.",
    parameters={"type": "object", "properties": {
        "number": {"type": "number", "description": "The number to round"},
        "decimals": {"type": "integer", "description": "Decimal places (default 0)"},
    }, "required": ["number"]},
)(_round_number_exec)


async def _binary_to_decimal_exec(tid: str, p: dict) -> dict:
    return {"result": int(p["binary"], 2)}

binary_to_decimal = tool(
    name="binary_to_decimal",
    description="Convert a binary string (e.g. '1010') to its decimal integer value.",
    parameters={"type": "object", "properties": {
        "binary": {"type": "string", "description": "Binary string (e.g. '1010')"},
    }, "required": ["binary"]},
)(_binary_to_decimal_exec)


async def _decimal_to_binary_exec(tid: str, p: dict) -> dict:
    return {"result": bin(int(p["decimal"]))[2:]}

decimal_to_binary = tool(
    name="decimal_to_binary",
    description="Convert a decimal integer to its binary string representation (without '0b' prefix).",
    parameters={"type": "object", "properties": {
        "decimal": {"type": "integer", "description": "Decimal integer to convert"},
    }, "required": ["decimal"]},
)(_decimal_to_binary_exec)


async def _celsius_to_kelvin_exec(tid: str, p: dict) -> dict:
    return {"result": float(p["celsius"]) + 273.15}

celsius_to_kelvin = tool(
    name="celsius_to_kelvin",
    description="Convert a temperature from Celsius to Kelvin by adding 273.15.",
    parameters={"type": "object", "properties": {
        "celsius": {"type": "number", "description": "Temperature in Celsius"},
    }, "required": ["celsius"]},
)(_celsius_to_kelvin_exec)


async def _kg_to_pounds_exec(tid: str, p: dict) -> dict:
    return {"result": round(float(p["kg"]) * 2.20462, 2)}

kg_to_pounds = tool(
    name="kg_to_pounds",
    description="Convert weight from kilograms to pounds (1 kg = 2.20462 lbs).",
    parameters={"type": "object", "properties": {
        "kg": {"type": "number", "description": "Weight in kilograms"},
    }, "required": ["kg"]},
)(_kg_to_pounds_exec)


async def _sort_string_exec(tid: str, p: dict) -> dict:
    return {"result": "".join(sorted(p["text"]))}

sort_string = tool(
    name="sort_string",
    description="Sort all characters in a string alphabetically.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to sort"},
    }, "required": ["text"]},
)(_sort_string_exec)


async def _unique_chars_exec(tid: str, p: dict) -> dict:
    seen = []
    for c in p["text"]:
        if c not in seen:
            seen.append(c)
    return {"result": "".join(seen)}

unique_chars = tool(
    name="unique_chars",
    description="Remove duplicate characters from a string, keeping first occurrence order.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to deduplicate"},
    }, "required": ["text"]},
)(_unique_chars_exec)


async def _first_n_chars_exec(tid: str, p: dict) -> dict:
    return {"result": p["text"][:int(p["n"])]}

first_n_chars = tool(
    name="first_n_chars",
    description="Return the first N characters of a string.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The source string"},
        "n": {"type": "integer", "description": "Number of characters to take"},
    }, "required": ["text", "n"]},
)(_first_n_chars_exec)


async def _last_n_chars_exec(tid: str, p: dict) -> dict:
    return {"result": p["text"][-int(p["n"]):]}

last_n_chars = tool(
    name="last_n_chars",
    description="Return the last N characters of a string.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The source string"},
        "n": {"type": "integer", "description": "Number of characters to take"},
    }, "required": ["text", "n"]},
)(_last_n_chars_exec)


async def _char_at_index_exec(tid: str, p: dict) -> dict:
    idx = int(p["index"])
    text = p["text"]
    if 0 <= idx < len(text):
        return {"result": text[idx]}
    return {"error": f"Index {idx} out of range for string of length {len(text)}"}

char_at_index = tool(
    name="char_at_index",
    description="Return the character at a specific index position in a string (0-based).",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The source string"},
        "index": {"type": "integer", "description": "The index position (0-based)"},
    }, "required": ["text", "index"]},
)(_char_at_index_exec)


async def _count_words_with_prefix_exec(tid: str, p: dict) -> dict:
    words = p["text"].split()
    count = sum(1 for w in words if w.lower().startswith(p["prefix"].lower()))
    return {"result": count}

count_words_with_prefix = tool(
    name="count_words_with_prefix",
    description="Count words in text that start with a given prefix (case-insensitive).",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The text to search"},
        "prefix": {"type": "string", "description": "The prefix to match"},
    }, "required": ["text", "prefix"]},
)(_count_words_with_prefix_exec)


async def _string_contains_exec(tid: str, p: dict) -> dict:
    return {"result": p["substring"] in p["text"]}

string_contains = tool(
    name="string_contains",
    description="Check if a string contains a given substring. Returns true or false.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to search in"},
        "substring": {"type": "string", "description": "The substring to find"},
    }, "required": ["text", "substring"]},
)(_string_contains_exec)


async def _starts_with_exec(tid: str, p: dict) -> dict:
    return {"result": p["text"].startswith(p["prefix"])}

starts_with = tool(
    name="starts_with",
    description="Check if a string starts with a given prefix. Returns true or false.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to check"},
        "prefix": {"type": "string", "description": "The prefix to test"},
    }, "required": ["text", "prefix"]},
)(_starts_with_exec)


async def _ends_with_exec(tid: str, p: dict) -> dict:
    return {"result": p["text"].endswith(p["suffix"])}

ends_with = tool(
    name="ends_with",
    description="Check if a string ends with a given suffix. Returns true or false.",
    parameters={"type": "object", "properties": {
        "text": {"type": "string", "description": "The string to check"},
        "suffix": {"type": "string", "description": "The suffix to test"},
    }, "required": ["text", "suffix"]},
)(_ends_with_exec)


async def _join_strings_exec(tid: str, p: dict) -> dict:
    return {"result": p["separator"].join(p["strings"])}

join_strings = tool(
    name="join_strings",
    description="Join a list of strings together using a separator.",
    parameters={"type": "object", "properties": {
        "strings": {"type": "array", "items": {"type": "string"}, "description": "List of strings to join"},
        "separator": {"type": "string", "description": "Separator between strings"},
    }, "required": ["strings", "separator"]},
)(_join_strings_exec)


# ============================================================
# ALL_TOOLS: ordered list (positions 1-50)
# ============================================================

# Filler tools (1-10) — Remove/Mask targets
FILLER_TOOLS = [
    hex_encode, hex_decode, rot13, ascii_value, vowel_count,
    consonant_count, is_palindrome, factorial, fibonacci, prime_check,
]

# Active tools (11-50) — used by tasks
ACTIVE_TOOLS = [
    # Original 8 (11-18)
    calculator, string_reverse, char_count, base_convert,
    caesar_cipher, temperature_convert, gcd, word_count,
    # New 32 (19-50)
    lcm, modulo, power, abs_value, floor_div,
    string_length, to_uppercase, to_lowercase,
    string_repeat, string_slice, replace_char,
    count_digits, sum_digits, is_even, max_of_two,
    min_of_two, percentage, round_number,
    binary_to_decimal, decimal_to_binary,
    celsius_to_kelvin, kg_to_pounds,
    sort_string, unique_chars, first_n_chars,
    last_n_chars, char_at_index, count_words_with_prefix,
    string_contains, starts_with, ends_with, join_strings,
]

ALL_TOOLS: list[AgentTool] = FILLER_TOOLS + ACTIVE_TOOLS
TOOL_NAMES: list[str] = [t.name for t in ALL_TOOLS]
FILLER_NAMES: list[str] = [t.name for t in FILLER_TOOLS]
ACTIVE_NAMES: list[str] = [t.name for t in ACTIVE_TOOLS]
