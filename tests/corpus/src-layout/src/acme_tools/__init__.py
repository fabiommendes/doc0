"""Acme tools."""

from .widgets import Widget

__all__ = ["Widget", "make_widget"]


def make_widget(name: str) -> Widget:
    """Make a widget."""
    return Widget(name)
