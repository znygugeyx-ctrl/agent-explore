"""Answer verification for benchmarks."""

from __future__ import annotations

import re
import string
from abc import ABC, abstractmethod
from typing import Any

from core.llm import complete
from core.types import Context, Model, TextContent, UserMessage


class BaseVerifier(ABC):
    """Base class for answer verifiers."""

    @abstractmethod
    async def verify(
        self,
        question: str,
        expected: str,
        predicted: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Verify if predicted answer matches expected.

        Returns (is_correct, reasoning).
        """
        ...


class ExactMatchVerifier(BaseVerifier):
    """Normalized string comparison."""

    async def verify(
        self,
        question: str,
        expected: str,
        predicted: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        norm_expected = self._normalize(expected)
        norm_predicted = self._normalize(predicted)

        if norm_expected == norm_predicted:
            return True, "Exact match"

        # Try numeric comparison
        try:
            if abs(float(norm_expected) - float(norm_predicted)) < 1e-6:
                return True, "Numeric match"
        except ValueError:
            pass

        return False, f"Expected '{expected}', got '{predicted}'"

    @staticmethod
    def _normalize(s: str) -> str:
        s = s.strip().lower()
        s = re.sub(r"\s+", " ", s)
        s = s.translate(str.maketrans("", "", string.punctuation))
        return s


class ContainsVerifier(BaseVerifier):
    """Check if expected answer is contained in prediction."""

    async def verify(
        self,
        question: str,
        expected: str,
        predicted: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        norm_expected = expected.strip().lower()
        norm_predicted = predicted.strip().lower()
        if norm_expected in norm_predicted:
            return True, "Answer contained in response"
        return False, f"Expected '{expected}' not found in response"


class LLMJudgeVerifier(BaseVerifier):
    """Use an LLM to judge answer correctness."""

    JUDGE_PROMPT = """You are an evaluation judge. Determine if the predicted answer is equivalent to the expected answer.

Question: {question}
Expected Answer: {expected}
Predicted Answer: {predicted}

Respond with exactly one word: "CORRECT" or "INCORRECT", followed by a brief explanation."""

    def __init__(self, model: Model):
        self.model = model

    async def verify(
        self,
        question: str,
        expected: str,
        predicted: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        prompt = self.JUDGE_PROMPT.format(
            question=question, expected=expected, predicted=predicted
        )
        context = Context(messages=[UserMessage(content=prompt)])
        response = await complete(self.model, context)

        text = "".join(
            b.text for b in response.content if isinstance(b, TextContent)
        ).strip()

        is_correct = text.upper().startswith("CORRECT")
        return is_correct, text


class GAIAVerifier(BaseVerifier):
    """GAIA-style verifier: exact match with normalization, then LLM judge fallback.

    Ported from miroflow's GAIACommonVerifier. Handles numbers, comma/semicolon
    lists, and plain strings. Falls back to LLM judge when exact match fails.
    """

    JUDGE_PROMPT = (
        "You are an evaluation assistant. Determine if the predicted answer "
        "is equivalent to the labeled answer.\n\n"
        "Question: {question}\n"
        "Labeled Answer: {expected}\n"
        "Predicted Answer: {predicted}\n\n"
        'Respond with exactly "Correct" or "Incorrect". No other text.'
    )

    def __init__(self, judge_model: Model):
        self.judge_model = judge_model

    # -- Normalization helpers (from GAIA evaluation protocol) --

    @staticmethod
    def _normalize_number(s: str) -> float:
        for char in ["$", "%", ","]:
            s = s.replace(char, "")
        try:
            return float(s)
        except ValueError:
            return float("inf")

    @staticmethod
    def _normalize_str(s: str, remove_punct: bool = True) -> str:
        no_spaces = re.sub(r"\s", "", s)
        if remove_punct:
            translator = str.maketrans("", "", string.punctuation)
            return no_spaces.lower().translate(translator)
        return no_spaces.lower()

    @staticmethod
    def _is_float(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    @staticmethod
    def _split_string(s: str) -> list[str]:
        return re.split(r"[,;]", s)

    def _exact_match(self, predicted: str, expected: str) -> bool:
        if predicted is None:
            return False
        # Numeric comparison
        if self._is_float(expected):
            return self._normalize_number(predicted) == float(expected)
        # List comparison
        if any(c in expected for c in [",", ";"]):
            gt_elems = self._split_string(expected)
            pred_elems = self._split_string(predicted)
            if len(gt_elems) != len(pred_elems):
                return False
            for p, g in zip(pred_elems, gt_elems):
                if self._is_float(g):
                    if self._normalize_number(p) != float(g):
                        return False
                else:
                    if self._normalize_str(p, False) != self._normalize_str(g, False):
                        return False
            return True
        # String comparison
        return self._normalize_str(predicted) == self._normalize_str(expected)

    async def verify(
        self,
        question: str,
        expected: str,
        predicted: str,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        # Fast path: exact match
        if self._exact_match(predicted, expected):
            return True, "GAIA exact match"

        # Slow path: LLM judge
        prompt = self.JUDGE_PROMPT.format(
            question=question, expected=expected, predicted=predicted
        )
        context = Context(messages=[UserMessage(content=prompt)])
        response = await complete(self.judge_model, context)
        text = "".join(
            b.text for b in response.content if isinstance(b, TextContent)
        ).strip()

        is_correct = text.strip().rstrip(".").lower() == "correct"
        return is_correct, f"GAIA LLM judge: {text}"
