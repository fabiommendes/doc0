"""
Shared scenario builders for the doc0 test harness.

These tests exercise doc0 exclusively through its public API:

* ``doc0.Doc0``    -- the toplevel entry point (``load``, ``init``, ``build``,
  ``serve``, ``test``, ``write_rst_files``, ``write_readme_md``)
* ``doc0.PyProject`` -- project introspection (``get``, ``__getitem__``,
  properties, ``find_root_modules``)
* ``doc0.Module`` / ``doc0.module.ModuleSpec`` -- module loading/rendering
* ``doc0.util.validate_theme`` -- the one standalone public helper
* ``doc0.cli.app`` -- the Typer CLI application

No private (``_``-prefixed) method is called directly. Instead, each fixture
builds a small, realistic project on disk (a "scenario") and the tests drive
it through the public entry points above, so that private helpers are only
exercised indirectly -- the same way a real user of doc0 would exercise them.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest


# ---------------------------------------------------------------------------
# Project scaffolding helpers
# ---------------------------------------------------------------------------


_MISSING = object()


def write(path: Path, content: str) -> Path:
    """Write dedented text content to *path*, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))
    return path


def make_pyproject_toml(
    root: Path,
    *,
    name: str = "mypkg",
    version: str = "0.1.0",
    description: str = "A test package.",
    authors: list[dict[str, str]] | None = None,
    build_backend: str | None = "uv_build",
    module_name: str | list[str] | None = None,
    module_root: str = "",
    extra_toml: str = "",
    include_authors: bool = True,
) -> Path:
    """
    Write a pyproject.toml file with configurable knobs so that we can drive
    every branch of PyProject.find_root_modules() and Conf.from_pyproject().
    """
    lines = ["[project]", f'name = "{name}"', f'version = "{version}"', f'description = "{description}"']

    if include_authors:
        if authors is None:
            authors = [{"name": "Ada Lovelace", "email": "ada@example.com"}]
        author_toml = ", ".join(
            "{ " + ", ".join(f'{k} = "{v}"' for k, v in a.items()) + " }" for a in authors
        )
        lines.append(f"authors = [{author_toml}]")

    toml = "\n".join(lines) + "\n\n"

    if build_backend is not None:
        toml += textwrap.dedent(f"""
            [build-system]
            requires = ["uv_build"]
            build-backend = "{build_backend}"
            """)

    if build_backend == "uv_build":
        toml += "\n[tool.uv.build-backend]\n"
        if module_name is not None:
            if isinstance(module_name, list):
                joined = ",".join(module_name)
                toml += f'module-name = "{joined}"\n'
            else:
                toml += f'module-name = "{module_name}"\n'
        toml += f'module-root = "{module_root}"\n'

    toml += extra_toml

    return write(root / "pyproject.toml", toml)


def make_module_file(
    path: Path,
    *,
    docstring: str | None = "A test module.",
    all_: list[str] | None = _MISSING,
    all_source: str | None = None,
    body: str = "",
) -> Path:
    """
    Write a single-file Python module used as a doc0 scan target.

    Pass `all_` for a plain ``__all__ = [...]`` list (order preserved, no
    comments). Pass `all_source` instead for raw ``__all__`` source text
    verbatim -- e.g. to include ``#:`` section comments, which `repr()`
    can't produce.
    """
    parts = []
    if docstring is not None:
        parts.append(f'"""{docstring}"""\n')
    if all_source is not None:
        parts.append(all_source if all_source.endswith("\n") else all_source + "\n")
    elif all_ is not _MISSING:
        parts.append(f"__all__ = {all_!r}\n")
    parts.append(body)
    return write(path, "\n".join(parts))


def make_package(
    path: Path,
    *,
    docstring: str | None = "A test package.",
    all_: list[str] | None = _MISSING,
) -> Path:
    """Create a package directory with an __init__.py."""
    make_module_file(path / "__init__.py", docstring=docstring, all_=all_)
    return path


# ---------------------------------------------------------------------------
# Fake sphinx / sphinx-autobuild for Doc0.build() / Doc0.serve()
# ---------------------------------------------------------------------------


class Recorder:
    """Records calls made to a stubbed-out function."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(list(argv))
        return 0


def _install_fake_module(monkeypatch: pytest.MonkeyPatch, dotted: str, **attrs: object) -> ModuleType:
    """
    Insert a fake module named *dotted* into sys.modules (creating parent
    packages as needed) so that ``from <dotted> import <attr>`` succeeds
    without the real dependency being installed.
    """
    parts = dotted.split(".")
    built = ""
    parent: ModuleType | None = None
    for part in parts:
        built = f"{built}.{part}" if built else part
        if built in sys.modules:
            mod = sys.modules[built]
        else:
            mod = ModuleType(built)
            monkeypatch.setitem(sys.modules, built, mod)
        if parent is not None and not hasattr(parent, part):
            setattr(parent, part, mod)
        parent = mod
    for key, value in attrs.items():
        setattr(parent, key, value)
    return parent  # type: ignore[return-value]


@pytest.fixture
def fake_sphinx(monkeypatch: pytest.MonkeyPatch) -> dict[str, Recorder]:
    """
    Stub out the ``sphinx.cmd.build`` and ``sphinx_autobuild.__main__``
    entry points that Doc0.build()/Doc0.serve() import lazily, so tests can
    exercise the full public build()/serve() flow without the (heavy) real
    Sphinx dependency installed.
    """
    build_recorder = Recorder()
    serve_recorder = Recorder()
    _install_fake_module(monkeypatch, "sphinx.cmd.build", main=build_recorder)
    _install_fake_module(monkeypatch, "sphinx_autobuild.__main__", main=serve_recorder)
    return {"build": build_recorder, "serve": serve_recorder}
