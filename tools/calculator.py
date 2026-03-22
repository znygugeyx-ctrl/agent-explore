"""Calculator tool - safe math expression evaluator."""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

from core.tools import tool

# Safe operators for expression evaluation
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "pi": math.pi,
    "e": math.e,
}


def _safe_eval(node: ast.AST) -> Any:
    """Recursively evaluate an AST node with only safe operations."""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    elif isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value}")
    elif isinstance(node, ast.BinOp):
        op = _SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    elif isinstance(node, ast.UnaryOp):
        op = _SAFE_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCS:
            args = [_safe_eval(a) for a in node.args]
            return _SAFE_FUNCS[node.func.id](*args)
        raise ValueError("Unsupported function call")
    elif isinstance(node, ast.Name):
        if node.id in _SAFE_FUNCS:
            return _SAFE_FUNCS[node.id]
        raise ValueError(f"Unsupported name: {node.id}")
    else:
        raise ValueError(f"Unsupported expression type: {type(node).__name__}")


def safe_eval(expression: str) -> float:
    """Safely evaluate a math expression. No arbitrary code execution."""
    tree = ast.parse(expression, mode="eval")
    return float(_safe_eval(tree))


async def _calculator_execute(tool_call_id: str, params: dict) -> dict:
    """Execute the calculator tool."""
    expression = params["expression"]
    result = safe_eval(expression)
    return {"expression": expression, "result": result}


calculator = tool(
    name="calculator",
    description="Evaluate a mathematical expression. Supports: +, -, *, /, //, %, **, sqrt, log, sin, cos, abs, round, min, max, pi, e.",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The mathematical expression to evaluate",
            }
        },
        "required": ["expression"],
    },
)(_calculator_execute)
