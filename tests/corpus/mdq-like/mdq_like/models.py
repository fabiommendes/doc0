"""Question models."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Question", "Choice"]


@dataclass
class Choice:
    """One answer option."""

    text: str
    correct: bool = False


@dataclass
class Question:
    """A question with its choices."""

    stem: str
    choices: list[Choice] = field(default_factory=list)
