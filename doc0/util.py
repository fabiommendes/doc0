from pathlib import Path
from typing import Any, Callable, Iterable, overload


def validate_theme(theme: str) -> str:
    """
    Validate the provided theme for Sphinx documentation.

    Args:
        theme (str): The name of the Sphinx theme to validate.

    Raises
        ValueError: If the provided theme is not a valid Sphinx theme.

    Examples:
        >>> validate_theme("alabaster")
        'alabaster'
        >>> validate_theme("bad theme")
        Traceback (most recent call last):
            ...
        ValueError: 'bad theme' is not a valid Sphinx theme.
    """
    parts = theme.split(".")
    for part in parts:
        if not part.isidentifier():
            raise ValueError(f"'{theme}' is not a valid Sphinx theme.")

    return theme


@overload
def maybe_map[T, R](fn: Callable[[T], R], value: T | None, /) -> R | None: ...


@overload
def maybe_map[T, R](fn: Callable[[T], R], /) -> Callable[[T | None], R | None]: ...


def maybe_map[T, R](fn: Callable[[T], R], /, *args: Any) -> Any:
    """
    Apply a function to a value if it is not None, otherwise return None.

    Curried.
    """
    if args:
        value = args[0]
        if value is not None:
            return fn(value)
    else:
        return lambda value: maybe_map(fn, value)
    return None


def first_existing(paths: Iterable[Path]) -> Path | None:
    """
    Return the first existing path from the provided iterable of paths.
    """
    for path in paths:
        if path.exists():
            return path
    return None
