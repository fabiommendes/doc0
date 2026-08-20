# Agent instructions for doc0

This file orients coding agents (and humans) working in this repository.
`CLAUDE.md` in this same directory is a symlink to this file, so both
Claude Code and generic "AGENTS.md" tooling read the same content.

## What this project is

`doc0` is a zero-configuration documentation generator for Python
projects. It introspects a project's `pyproject.toml` and source tree,
then generates and drives a Sphinx project under `<root>/docs`. See
README.md for the user-facing pitch.

## Environment setup

Requires Python >= 3.13 (the source uses PEP 695 generics and `type`
statements, e.g. `def get[T](...)`, `type TomlValue = ...` -- these are
syntax errors on 3.11/3.12-earlier interpreters).

```bash
uv sync --all-groups   # installs runtime deps + the dev group (ruff, pytest, pytest-cov)
```

## Common commands

All defined as taskipy tasks in `pyproject.toml`; run with `uv run task <name>`.

| Task | Command | Purpose |
|---|---|---|
| `test` | `pytest tests` | Run the test suite |
| `coverage` | `pytest tests --cov=doc0 --cov-report=term-missing` | Run tests with coverage report |
| `lint` | `ruff check .` | Lint |
| `docs` | `sphinx-build -b html docs/source docs/build -n` | Build doc0's own documentation |
| `docs-serve` | `sphinx-autobuild docs/source docs/build -n` | Live-reload doc server |
| `build` | `uv build` | Build distributable package |
| `release` | lint + test + docs + build + tag | Full release flow |

CI (`.github/workflows/ci.yml`) runs `lint` and `coverage` on every push
and PR. A change is not done until both pass locally.

## Source layout

- `doc0/base.py` -- `Doc0` (the main entry point: `load`/`init`/`build`/`serve`/`test`),
  plus `Conf`, `Index`, and the rendering helpers they use.
- `doc0/pyproject.py` -- `PyProject`: parses `pyproject.toml` and detects the
  project's layout (uv build-backend / src / toplevel package) to find root modules.
- `doc0/module.py` -- `ModuleSpec` (locate + load a module from disk) and
  `Module` (a loaded module's docstring/exports/rendering). `Module.render()`
  uses `doc0/exports.py` to decide between an ordered, sectioned listing and
  a plain `automodule` fallback.
- `doc0/exports.py` -- internal (not re-exported): statically parses a
  module's `__all__` literal via `ast` + `tokenize` into ordered,
  `#:`-delimited sections with optional multi-paragraph body text, when it
  can be done reliably (see the module docstring for the exact rules and a
  documented edge-case limitation). Falls back to `None` for anything
  dynamic, computed, or that doesn't match the module's runtime `__all__`.
- `doc0/util.py` -- small standalone helpers (`validate_theme`, `first_existing`).
- `doc0/cli.py` -- the `doc0` console script, built with Typer (`app.command()`
  for `build`/`serve`/`test`).
- `doc0/__init__.py` -- the package's public surface: `Doc0`, `Module`,
  `ModuleSpec`, `PyProject`. Anything not re-exported here is internal, even
  if it isn't underscore-prefixed (e.g. `Conf`, `Index` in `base.py`).

## Testing conventions

Tests live in `tests/` and are **scenario-based, public-API-only** -- see
the module docstring in `tests/conftest.py` for the full rationale. In
short:

- Drive everything through `doc0`'s public entry points (`Doc0.load()` and
  its methods, `PyProject`, `ModuleSpec`/`Module`, `validate_theme`, the CLI
  via `typer.testing.CliRunner`). Do not unit-test private (`_`-prefixed)
  methods directly -- exercise them indirectly through a realistic scenario.
- Build fixture projects on disk with the helpers in `tests/conftest.py`
  (`make_pyproject_toml`, `make_package`, `make_module_file`, `write`) rather
  than mocking doc0's own internals.
- `Doc0.build()`/`serve()` import Sphinx/sphinx-autobuild lazily; the
  `fake_sphinx` fixture stubs those imports via `sys.modules` so tests don't
  need the real (heavy) dependencies installed.
- When a test reveals a real bug, prefer fixing the bug over adjusting the
  test to match broken behavior. If a fix is out of scope for the change at
  hand, write the test as an explicit characterization test with a
  docstring explaining the bug it documents, rather than silently asserting
  the buggy output. Keep such docstrings in sync when the bug does get
  fixed later -- a characterization test whose docstring still describes a
  bug that was already fixed is actively misleading.

Aim for coverage close to 100% on `doc0/`; gaps should be either genuinely
unreachable defensive code (call this out explicitly) or a signal that a
public code path needs a new scenario.

## Code conventions

- Python 3.13+, `from __future__ import annotations` at the top of modules
  that need it for forward references.
- Dataclasses over plain classes for data-carrying types.
- Prefer precise typing (PEP 695 generics, `TypedDict`, `Annotated`) --
  this project runs `mypy --strict` (see `[tool.mypy]` in `pyproject.toml`).
- Follow `ruff check .`; there is no separate formatter config beyond ruff's
  defaults.
- Avoid shadowing builtins with parameter names (e.g. `type`, `id`, `list`)
  inside a function body that also needs the builtin -- this codebase has
  been bitten by exactly that once (see git history around `PyProject.get()`).

## Known rough edges

Keep this section current -- update it whenever a similar issue is found
or fixed, so it stays a reliable map rather than stale trivia.

- `Index`/`Conf` (in `base.py`) and other non-underscore names not listed
  in `doc0/__init__.py.__all__` are internal, but nothing enforces that at
  import time. Don't grow the public API by accident -- if something
  needs to become public, add it to `__all__` deliberately.
