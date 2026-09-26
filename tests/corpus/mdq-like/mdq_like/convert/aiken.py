"""The Aiken plain-text format."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Choice, Question

__all__ = ["Aiken", "AikenQuestion"]


@dataclass
class AikenQuestion:
    """A parsed Aiken question."""

    stem: str
    answer: str


class Aiken:
    """Convert Aiken questions to :class:`Question`."""

    def convert(self, source: AikenQuestion) -> Question:
        """Convert one question."""
        return Question(source.stem, [Choice(source.answer, correct=True)])
