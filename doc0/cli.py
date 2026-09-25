"""
CLI commands for the doc0 package.
"""

import builtins
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from .base import Doc0
from .theme import ThemeError

__all__ = [
    "main",
    #: Standalone commands
    "test",
    "build",
    "serve",
]

app = typer.Typer(
    name="doc0",
    help="Generate documentation with zero configuration.",
    no_args_is_help=True,
)

#: The `--theme` option shared by `build` and `serve`. Validation happens in
#: `Doc0.load` (via `doc0.theme.resolve_theme`), not here, so an invalid
#: value -- from the flag or from pyproject.toml -- is reported the same way.
ThemeOption = Annotated[str | None, typer.Option("--theme", help="Select the Sphinx theme")]


def _load(theme: str | None) -> Doc0:
    """
    Load the current project, converting an invalid theme into a clean
    CLI usage error (exit code 2, no traceback) instead of a bare
    ValueError.

    ``typer.BadParameter`` is used rather than ``click.UsageError``: this
    typer version vendors its own click fork internally (``typer._click``)
    and only recognizes exceptions from that fork, not from the standalone
    ``click`` package. ``typer.BadParameter`` is a public re-export of that
    fork's ``UsageError`` subclass, so it's caught the same way.
    """
    try:
        return Doc0.load(Path.cwd(), theme=theme)
    except ThemeError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def test() -> None:
    """
    Run all doctests for the project.
    """
    doc = Doc0.load(Path.cwd())
    doc.test()


@app.command()
def build(theme: ThemeOption = None) -> None:
    """
    Build the documentation for the current project.
    """
    doc = _load(theme)
    doc.build()


@app.command()
def serve(theme: ThemeOption = None) -> None:
    """
    Serve the documentation in the live server.
    """
    doc = _load(theme)
    doc.serve()


def _debug(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
    import rich
    from rich.panel import Panel

    if not args and not kwargs:
        rich.print(sys._getframe(1).f_locals)
        return

    if args:
        rich.print(*args)

    if kwargs:
        for k, v in kwargs.items():
            rich.print(Panel(str(v), title=k, border_style="b"))


def main() -> None:
    """
    Start the main CLI application for the doc0 package.
    """
    app()


# Debug hack for efficienet print-based debugging ;)
builtins.dbg = _debug  # type: ignore
