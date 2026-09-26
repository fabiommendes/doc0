"""Private diagnostics module, re-exported by the package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Diagnostic:
    """A problem found in a document."""

    message: str
    line: int | None = None
