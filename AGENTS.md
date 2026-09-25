# Agent instructions for doc-zero

`doc-zero` is a zero-configuration documentation generator for Python
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

| Task         | Command                                             | Purpose                            |
| ------------ | --------------------------------------------------- | ---------------------------------- |
| `test`       | `pytest tests`                                      | Run the test suite                 |
| `coverage`   | `pytest tests --cov=doc0 --cov-report=term-missing` | Run tests with coverage report     |
| `lint`       | `ruff check .`                                      | Lint                               |
| `docs`       | `sphinx-build -b html docs/source docs/build -n`    | Build doc-zero's own documentation |
| `docs-serve` | `sphinx-autobuild docs/source docs/build -n`        | Live-reload doc server             |
| `build`      | `uv build`                                          | Build distributable package        |
| `release`    | lint + test + docs + build + tag                    | Full release flow                  |

CI (`.github/workflows/ci.yml`) runs `lint` and `coverage` on every push
and PR. A change is not done until both pass locally.

## Source layout

- `doc0/base.py` -- `Doc0` (the main entry point: `load`/`init`/`generate`/`build`/`serve`/`test`),
  plus `Conf`, `Index`, and the rendering helpers they use. `generate()` is
  the pure step: it reads project inputs (pyproject, README, LICENSE,
  diataxis entries, source modules) and returns a `doc0.tree.DocTree`
  describing the whole doc tree as data, without writing anything. `init()`
  is just `self.generate().write()`.
- `doc0/tree.py` -- `DocTree`/`DocFile`/`WritePolicy`: the doc tree as data
  (absolute path -> content + `OVERWRITE`/`IF_MISSING` policy) and the one
  place that touches disk to write it (`DocTree.write()`), including
  clearing `owned_dirs` (e.g. `docs/api`) so stale generated files vanish.
- `doc0/pyproject.py` -- `PyProject`: parses `pyproject.toml` and resolves the
  project's layout to find root modules. `find_root_modules()` derives the
  shared facts once (`_ProjectFacts`: normalized name, build backend, uv
  config), then tries `uv_build` -> `src` -> `toplevel` in order; each
  `_resolve_*_layout` returns root modules or raises `_LayoutInapplicable`
  with a reason. If none applies, one `RuntimeError` lists every reason.
  Add new layouts there, not as separate detector/finder pairs.
- `doc0/module.py` -- `ModuleSpec` (locate + load a module from disk) and
  `Module` (a loaded module's docstring/exports/rendering). `Module.render()`
  uses `doc0/exports.py` to decide between an ordered, sectioned listing and
  a plain `automodule` fallback. `find_public_modules(roots)` (internal, not
  re-exported) is the single place that decides which modules get
  documented and in what order: roots always, then docstring-bearing,
  non-`_` submodules in sorted `iter_submodules()` order, warning about
  missing/empty `__all__`. `Doc0.generate()` just consumes its result.
- `doc0/exports.py` -- internal (not re-exported): statically parses a
  module's `__all__` literal via `ast` + `tokenize` into ordered,
  `#:`-delimited sections with optional multi-paragraph body text, when it
  can be done reliably (see the module docstring for the exact rules and a
  documented edge-case limitation). Falls back to `None` for anything
  dynamic, computed, or that doesn't match the module's runtime `__all__`.
- `doc0/theme.py` -- internal: `resolve_theme(cli_theme, pyproject)` is the
  one place the Sphinx theme is decided: precedence (`--theme` >
  `[tool.doc-zero] theme` > `"default"`), then validation, then alias
  expansion (`rtd`/`readthedocs` -> `sphinx_rtd_theme`, `default` ->
  `alabaster`). `Doc0.load` calls it, so `Doc0.theme` always holds the
  resolved Sphinx name; invalid values raise `ThemeError` (a `ValueError`)
  naming their source, which the CLI turns into a usage error (exit 2).
- `doc0/readme.py` -- internal: `readme_body(src)` turns README.md into the
  docs front page (`_readme.md`). After a `<!-- doc-zero-start -->` (or
  legacy `<!-- doc0-start -->`) marker, the rest is kept verbatim; otherwise
  badge-only lines (known hosts in `BADGE_HOSTS`, or "badge" in the image
  URL path), their orphaned link definitions, and the leading title are
  removed. Badges inline in prose and inside code fences are kept. In both
  modes, a `<!-- doc-zero-end -->` (or `<!-- doc0-end -->`) marker drops
  itself and everything after it.
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
  than mocking doc-zero's own internals.
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

## Agentic workflow and paths

The `prompts/` directory contains reusable prompt templates for coding agents.

The `dev/` directory is an issue tracker:
- `dev/issues/*.md` - Individual issue files in Markdown format.
- `dev/spec/to-do/*.md` - Specification files for tasks that need to be done.
- `dev/spec/to-review/*.md` - Specification files for tasks that have been completed. Removed after review.

### Glossary

Always read the list of definitions in the glossary using:

```bash
 grep -oP "^## \K.+" GLOSSARY.md
```

If you want to fetch the details of a definition, use:

```bash
awk  'BEGIN { IGNORECASE = 1 } /## <TERM>/{flag=1; next} /##/{flag=0} flag' GLOSSARY.md
```

replacing <TERM> with the term you want to look up.

If a new concept or word is introduced in a conversation, ask the human if it
should be added to the glossary. Be extremely succint when adding entries to the
glossary. Add in alphabetical order.


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
- Layout resolution (`doc0/pyproject.py`) follows uv's rules: the
  normalized name is lowercased with `-`/`.` -> `_`, even for the `toplevel`
  layout, so a mixed-case package dir such as `Acme/` is not found. uv
  stub packages (`foo-stubs` -> `foo-stubs/`) are not handled, and a
  non-string `module-root` silently falls back to `"src"`.
- Module loading (`ModuleSpec.load_module()`) reuses `sys.modules[name]`
  when present and never registers what it loads. So (a) if a module of
  the same name was already imported -- e.g. an installed copy of the
  project, or doc0 documenting itself -- that copy is documented instead
  of the source tree; and (b) a submodule using relative imports
  (`from .util import x`) only loads if the project is importable some
  other way (installed in the environment, as `uv sync` does); otherwise
  generation aborts with `ModuleNotFoundError` (characterized in
  `tests/test_module.py`).
