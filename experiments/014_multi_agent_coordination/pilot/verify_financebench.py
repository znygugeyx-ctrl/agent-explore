"""
FinanceBench verifier: numeric normalization + string contains.

Many answers are dollar amounts ($1577.00, $-0.02), percentages (24.6%),
or short yes/no. We normalize numbers (strip $, commas, %, parens for negatives)
and check exact match; otherwise fall back to a tokenized substring match.
"""
from __future__ import annotations
import re


_NUM_RE = re.compile(r"-?\$?\s*\(?\s*-?\s*[\d,]+\.?\d*\s*\)?\s*[%MmBb]?")


def _to_float(s: str) -> float | None:
    """Pull the FIRST number out of a string and normalize. Handles:
    $1,577.00, -0.02, 24.6%, $(2,853), 5.4 million, 1.5B
    """
    if s is None: return None
    s = str(s).strip()
    # find numeric token
    m = re.search(r"-?\$?\s*\(?\s*-?\s*[\d,]+\.?\d*\s*\)?", s)
    if not m: return None
    tok = m.group(0)
    sign = -1.0 if (tok.strip().startswith("(") or tok.strip().startswith("-") or tok.strip().startswith("$-") or tok.strip().startswith("-$")) else 1.0
    digits = re.sub(r"[^\d.]", "", tok)
    if not digits or digits == ".": return None
    try:
        v = float(digits) * sign
    except Exception:
        return None
    # check for unit suffix in the original string
    rest_after = s[m.end():m.end()+15].lower()
    if "million" in rest_after or rest_after.strip().startswith("m"):
        v *= 1.0  # already in millions for our values; financebench answers don't multiply
    if "billion" in rest_after or rest_after.strip().startswith("b"):
        # the answer is usually given without billions multiplier
        pass
    return v


def _all_numbers(s: str) -> list[float]:
    """Extract all numbers from text."""
    out = []
    for m in re.finditer(r"-?\$?\s*\(?\s*-?\s*[\d,]+\.?\d*\s*\)?", str(s) or ""):
        v = _to_float(m.group(0))
        if v is not None:
            out.append(v)
    return out


def _normalize_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^\w\s.\-]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def verify(model_text: str, expected_answer: str, *, question: str = "") -> dict:
    """Score one FinanceBench prediction."""
    extracted = _extract_answer(model_text)
    pred_for_score = extracted or model_text or ""

    expected_str = str(expected_answer).strip()
    exp_num = _to_float(expected_str)

    result = {
        "ok": False,
        "score": 0.0,
        "extracted": extracted,
        "expected": expected_str,
        "match_type": None,
    }

    # Type 1: yes/no — detect both bare "yes"/"no" AND "yes, ..." / "no, ..."
    exp_first = re.split(r"[,.\s]", expected_str.lower().strip(), maxsplit=1)[0]
    if exp_first in ("yes", "no"):
        pred_l = pred_for_score.lower().strip()
        # Accept if pred starts with yes/no (with optional separator) OR contains it as first word
        pred_first = re.split(r"[,.\s—–\-]", pred_l, maxsplit=1)[0]
        if pred_first == exp_first:
            result["ok"] = True; result["score"] = 1.0
            result["match_type"] = "yes_no"
            return result
        # Also check the full reply (e.g., agent explained reasoning then said "Yes")
        full = (model_text or "").lower()
        if re.search(rf"\b{exp_first}\b", full[:200]):
            result["ok"] = True; result["score"] = 1.0
            result["match_type"] = "yes_no_in_reply"
            return result
        result["match_type"] = "yes_no"
        return result

    # Type 2: numeric
    if exp_num is not None:
        pred_nums = _all_numbers(pred_for_score)
        # also search the full reply for the number (model may surround it with words)
        all_pred_nums = _all_numbers(pred_for_score) + _all_numbers(model_text or "")
        # tolerance: 0.01 absolute or 1% relative
        for v in all_pred_nums:
            tol = max(0.01, abs(exp_num) * 0.01)
            if abs(v - exp_num) <= tol:
                result["ok"] = True; result["score"] = 1.0
                result["match_type"] = "numeric"; result["pred_num"] = v
                return result
        result["match_type"] = "numeric"
        result["pred_nums_seen"] = all_pred_nums[:10]
        result["expected_num"] = exp_num
        return result

    # Type 3: free-text — token-F1 + exact substring
    norm_pred = _normalize_text(pred_for_score + " " + (model_text or ""))
    norm_exp = _normalize_text(expected_str)
    if norm_exp and norm_exp in norm_pred:
        result["ok"] = True; result["score"] = 1.0
        result["match_type"] = "contains"; return result
    # token F1
    pset = set(norm_pred.split()); eset = set(norm_exp.split())
    if pset and eset:
        inter = pset & eset
        if inter:
            prec = len(inter) / len(pset)
            rec = len(inter) / len(eset)
            f1 = 2 * prec * rec / (prec + rec)
            result["score"] = f1
            result["ok"] = f1 >= 0.6
            result["match_type"] = "token_f1"
            result["f1"] = round(f1, 3)
    return result


def _extract_answer(model_text: str) -> str | None:
    if not model_text: return None
    m = re.search(r"ANSWER\s*=\s*(.+?)\s*$", model_text, re.MULTILINE)
    if m: return m.group(1).strip()
    # fallback: last non-empty line
    lines = [l.strip() for l in model_text.strip().splitlines() if l.strip()]
    return lines[-1] if lines else None
