"""
Theme resolution: the one place that decides which Sphinx theme is used.

Internal module: not re-exported from ``doc0``.
"""

from __future__ import annotations

from .pyproject import PyProject
from .util import validate_theme

#: Sphinx theme aliases doc0 accepts, and the default theme's alias.
SPHINX_THEME_ALIASES = {
    "rtd": "sphinx_rtd_theme",
    "readthedocs": "sphinx_rtd_theme",
    "default": "alabaster",
}

#: The theme used when neither ``--theme`` nor ``[tool.doc-zero] theme`` is set.
DEFAULT_THEME = "default"


class ThemeError(ValueError):
    """
    An invalid theme, with a message naming where the value came from.
    """


def resolve_theme(cli_theme: str | None, pyproject: PyProject) -> str:
    """
    Resolve the Sphinx theme name to use.

    Precedence: ``cli_theme`` if it is not None (an empty string counts as
    given), else the ``[tool.doc-zero] theme`` key in pyproject.toml, else
    ``DEFAULT_THEME``. Only the chosen value is validated -- an unused
    pyproject value is never inspected, even if it would be invalid.

    The chosen value must be a string that passes ``validate_theme``,
    otherwise a ``ThemeError`` is raised naming the bad value and its
    source ("--theme" or "[tool.doc-zero] theme in pyproject.toml"). Once
    validated, known aliases (``rtd``/``readthedocs`` -> ``sphinx_rtd_theme``,
    ``default`` -> ``alabaster``) are expanded; any other name passes
    through unchanged.
    """
    if cli_theme is not None:
        value: object = cli_theme
        source = "--theme"
    else:
        # Read the raw value ourselves (no `type=` assertion) so an invalid
        # type doesn't raise PyProject.get's TypeError before we can report
        # a proper ThemeError.
        value = pyproject.get("tool.doc-zero.theme", default=DEFAULT_THEME)
        source = "[tool.doc-zero] theme in pyproject.toml"

    if not isinstance(value, str):
        raise ThemeError(f"Invalid theme {value!r} from {source}: expected a string.")

    try:
        validate_theme(value)
    except ValueError:
        msg = f"Invalid theme {value!r} from {source}: not a valid Sphinx theme name."
        raise ThemeError(msg) from None

    return SPHINX_THEME_ALIASES.get(value, value)
