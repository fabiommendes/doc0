"""Flat package."""

__all__ = ["VERSION", "greet"]

VERSION = "2.0.0"


def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"
