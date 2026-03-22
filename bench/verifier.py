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
