"""Lightweight verifiers for the three pilot benchmarks."""
import json
import re
import subprocess
import tempfile
import os


def _extract_answer_line(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"ANSWER\s*=\s*(.+?)\s*$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # fallback: last non-empty line
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    return lines[-1] if lines else None


# ---------- T1: MATH-500 ----------

def _normalize_math(s: str) -> str:
    if s is None:
        return ""
    s = s.strip()
    s = s.strip("$").strip()
    # strip enclosing \left( \right) and braces
    s = re.sub(r"\\left\s*", "", s)
    s = re.sub(r"\\right\s*", "", s)
    s = s.replace(" ", "")
    s = s.replace("\\,", "").replace("\\!", "")
    s = s.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    s = s.rstrip(".")
    return s


def verify_math(model_text: str, expected: str) -> dict:
    extracted = _extract_answer_line(model_text)
    norm_pred = _normalize_math(extracted or "")
    norm_exp = _normalize_math(expected)
    ok = norm_pred == norm_exp
    return {
        "ok": ok,
        "score": 1.0 if ok else 0.0,
        "extracted": extracted,
        "norm_pred": norm_pred,
        "norm_expected": norm_exp,
    }


# ---------- T2: FanOutQA ----------

def _normalize_str(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _flatten_answer(ans):
    """Recursively collect string leaves."""
    out = []
    if isinstance(ans, dict):
        for v in ans.values():
            out += _flatten_answer(v)
    elif isinstance(ans, list):
        for v in ans:
            out += _flatten_answer(v)
    else:
        out.append(str(ans))
    return out


def _tokenize(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", str(s).lower()))


def _string_overlap(pred: str, gold: str) -> float:
    """Token-level F1 (closest practical proxy to fanoutqa string-match)."""
    p = _tokenize(pred); g = _tokenize(gold)
    if not g: return 0.0
    if not p: return 0.0
    inter = p & g
    if not inter: return 0.0
    prec = len(inter) / len(p)
    rec = len(inter) / len(g)
    return 2 * prec * rec / (prec + rec)


_ARTICLES_RE = re.compile(r"\b(a|an|the)\b", re.IGNORECASE)


def _squad_normalize(s: str) -> str:
    """SQuAD-style answer normalization: lowercase, strip articles, strip punct, collapse whitespace."""
    s = s.lower()
    s = _ARTICLES_RE.sub(" ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def verify_bamboogle(model_text: str, expected, *, question: str | None = None,
                     answer_aliases: list[str] | None = None) -> dict:
    """
    Bamboogle (and any short-answer multi-hop QA): SQuAD-style EM + token-F1.
    Match against expected answer + any aliases. EM=correct passes; token-F1 reported as score.
    """
    extracted = _extract_answer_line(model_text) or ""
    golds = [str(expected)] + list(answer_aliases or [])
    golds = [g for g in golds if g]

    n_pred = _squad_normalize(extracted)
    pred_toks = set(n_pred.split())

    em_hit = False
    best_f1 = 0.0
    contains_hit = False
    for g in golds:
        n_gold = _squad_normalize(g)
        if not n_gold: continue
        # EM
        if n_pred == n_gold:
            em_hit = True
            best_f1 = 1.0
            break
        # token F1
        gold_toks = set(n_gold.split())
        if pred_toks and gold_toks:
            inter = pred_toks & gold_toks
            if inter:
                prec = len(inter) / len(pred_toks)
                rec = len(inter) / len(gold_toks)
                f1 = 2 * prec * rec / (prec + rec)
                if f1 > best_f1: best_f1 = f1
        # SQuAD-style "contains" — gold is a substring of prediction (after normalize)
        if n_gold in n_pred:
            contains_hit = True

    # Pass criterion: EM, OR (high F1 ≥ 0.6 AND contains).
    # Bamboogle answers are short; if F1 ≥ 0.6 the model basically said the right thing.
    ok = em_hit or (best_f1 >= 0.6 and contains_hit)

    return {
        "ok": ok,
        "score": 1.0 if em_hit else best_f1,
        "em": em_hit,
        "f1": round(best_f1, 3),
        "contains": contains_hit,
        "extracted": extracted,
        "normalized_pred": n_pred,
        "normalized_golds": [_squad_normalize(g) for g in golds],
    }


def verify_fanoutqa(model_text: str, expected, *, question: str | None = None) -> dict:
    """
    Per FanOutQA paper: official metric is GPT-4 factuality judge (A/B/C/E correct,
    D/F wrong). We use Claude on Bedrock as judge. Token-F1 retained as a sanity
    backup metric reported alongside.
    """
    extracted = _extract_answer_line(model_text)
    pred_blob = extracted or model_text or ""

    expected_leaves = _flatten_answer(expected)

    # token-F1 (cheap, no LLM cost) — kept as supplementary diagnostic
    blob = (pred_blob + "\n" + (model_text or "")).lower()
    per_leaf_f1 = []
    hits_strict = 0
    for leaf in expected_leaves:
        leaf_str = str(leaf)
        n_pred = _normalize_str(blob)
        n_leaf = _normalize_str(leaf_str)
        if n_leaf and n_leaf in n_pred:
            hits_strict += 1
            per_leaf_f1.append(1.0)
            continue
        per_leaf_f1.append(_string_overlap(blob, leaf_str))
    n = len(expected_leaves) or 1
    token_f1 = sum(per_leaf_f1) / n

    # LLM judge (primary metric)
    judge_result = None
    if question:
        try:
            from .llm_judge import llm_judge  # type: ignore
        except ImportError:
            from llm_judge import llm_judge  # type: ignore
        try:
            judge_result = llm_judge(question, expected, pred_blob or model_text or "")
        except Exception as e:
            judge_result = {"label": None, "correct": False, "error": str(e)}

    if judge_result and judge_result.get("label") is not None:
        ok = bool(judge_result.get("correct"))
        score = 1.0 if ok else 0.0
    else:
        # No judge available (e.g., offline) → fall back to token-F1 ≥ 0.5
        ok = token_f1 >= 0.5
        score = token_f1

    return {
        "ok": ok,
        "score": score,
        "judge": judge_result,
        "token_f1": round(token_f1, 3),
        "strict_match_rate": round(hits_strict / n, 3),
        "extracted": extracted,
        "n_leaves": len(expected_leaves),
        "per_leaf_f1": [round(x, 2) for x in per_leaf_f1],
    }


# ---------- T3: HumanEval+ ----------

def _extract_code(text: str, entry_point: str) -> str | None:
    if not text:
        return None
    # try fenced block first
    fenced = re.findall(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    candidates = list(fenced) + [text]
    for c in candidates:
        if f"def {entry_point}" in c:
            # cut from def onward
            idx = c.index(f"def {entry_point}")
            return c[idx:]
    return None


def verify_humanevalplus(
    model_text: str, expected: str, *, entry_point: str, prompt_signature: str, test_code: str
) -> dict:
    code = _extract_code(model_text, entry_point)
    if code is None:
        # if model returned only a body, prepend prompt signature
        if entry_point in model_text:
            code = prompt_signature + "\n" + model_text
        else:
            return {"ok": False, "score": 0.0, "reason": "no function found"}

    full_program = (
        prompt_signature
        + "\n"
        + code
        + "\n\n"
        + test_code
        + f"\n\ncheck({entry_point})\n"
    )
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "soln.py")
        with open(path, "w") as f:
            f.write(full_program)
        try:
            proc = subprocess.run(
                ["python3", path],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=td,
            )
            ok = proc.returncode == 0
            return {
                "ok": ok,
                "score": 1.0 if ok else 0.0,
                "rc": proc.returncode,
                "stderr_tail": (proc.stderr or "")[-300:],
                "extracted_code": code[:400],
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "score": 0.0, "reason": "timeout"}


# ---------- Dispatcher ----------

def verify(task: dict, model_text: str) -> dict:
    bm = task.get("benchmark")
    if bm == "math500":
        return verify_math(model_text, task["expected_answer"])
    if bm == "bamboogle":
        meta = task.get("metadata") or {}
        return verify_bamboogle(
            model_text,
            task["expected_answer"],
            question=meta.get("question"),
            answer_aliases=meta.get("answer_aliases"),
        )
    if bm == "fanoutqa":
        meta = task.get("metadata") or {}
        question = meta.get("question")
        return verify_fanoutqa(model_text, task["expected_answer"], question=question)
    if bm == "humanevalplus":
        meta = task["metadata"]
        return verify_humanevalplus(
            model_text,
            task["expected_answer"],
            entry_point=meta["entry_point"],
            prompt_signature=meta["prompt_signature"],
            test_code=meta["test_code"],
        )
    return {"ok": False, "score": 0.0, "reason": f"unknown benchmark {bm}"}
