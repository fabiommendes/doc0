"""
CLI commands for the doc0 package.
"""

import builtins
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from .base import Doc0
from .util import validate_theme

__all__ = ["test", "build", "serve", "main", "app"]

app = typer.Typer(
    name="doc0",
    help="Generate documentation with zero configuration.",
    no_args_is_help=True,
)


@app.command()
def test() -> None:
    """
    Run all doctests for the project.
    """
    doc = Doc0.load(Path.cwd())
    doc.test()


@app.command()
def build(
    theme: Annotated[
        str,
        typer.Option(
            ..., "--theme", help="Select the Sphinx theme", callback=validate_theme
        ),
    ] = "alabaster",
) -> None:
    """
    Build the documentation for the current project.
    """
    theme = validate_theme(theme)
    doc = Doc0.load(Path.cwd(), theme=theme)
    doc.build()


@app.command()
def serve(
    theme: Annotated[
        str,
        typer.Option(..., "--theme", help="Select the Sphinx theme"),
    ] = "alabaster",
) -> None:
    """
    Serve the documentation in the live server.
    """
    theme = validate_theme(theme)
    doc = Doc0.load(Path.cwd(), theme=theme)
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
