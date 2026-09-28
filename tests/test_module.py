"""
Scenario tests for doc0's module-loading public API: ModuleSpec and Module.
"""

from __future__ import annotations

import pytest
from conftest import make_module_file, make_package

from doc0 import Module, ModuleSpec
from doc0.module import find_public_modules

# ---------------------------------------------------------------------------
# ModuleSpec construction
# ---------------------------------------------------------------------------


def test_modulespec_rejects_missing_path(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        ModuleSpec(name="ghost", path=tmp_path / "nope.py")


def test_modulespec_rejects_non_python_file(tmp_path):
    not_python = tmp_path / "data.txt"
    not_python.write_text("hello")
    with pytest.raises(ValueError, match="not a Python file"):
        ModuleSpec(name="data", path=not_python)


def test_modulespec_for_init_py_normalizes_to_package_dir(tmp_path):
    pkg_dir = make_package(tmp_path / "pkg")
    spec = ModuleSpec(name="pkg", path=pkg_dir / "__init__.py")
    assert spec.path == pkg_dir
    assert spec.is_package is True
    assert spec.source_path == pkg_dir / "__init__.py"


def test_modulespec_for_plain_file_is_not_a_package(tmp_path):
    module_file = make_module_file(tmp_path / "leaf.py")
    spec = ModuleSpec(name="leaf", path=module_file)
    assert spec.is_package is False
    assert spec.source_path == module_file


# ---------------------------------------------------------------------------
# load_module()
# ---------------------------------------------------------------------------


def test_load_module_on_a_package_should_work(tmp_path):
    """
    load_module() uses source_path (the package's __init__.py) plus
    submodule_search_locations to build the spec, so package-shaped
    modules -- not just single files -- load correctly.
    """
    pkg_dir = make_package(
        tmp_path / "greetings",
        docstring="Greeting utilities.",
        all_=["hello"],
    )
    spec = ModuleSpec(name="greetings", path=pkg_dir)
    mod = spec.load_module()
    assert mod.module.__doc__ == "Greeting utilities."


def test_load_module_for_single_file_module_exposes_docstring_and_exports(tmp_path):
    module_file = make_module_file(
        tmp_path / "greetings.py",
        docstring="Greeting utilities.",
        all_=["hello"],
    )
    spec = ModuleSpec(name="greetings", path=module_file)

    module = spec.load_module()

    assert isinstance(module, Module)
    assert module.name == "greetings"
    assert module.source_path == module_file
    assert module.docstring == "Greeting utilities."
    assert module.exports == ["hello"]


def test_load_module_for_module_without_all_reports_no_exports(tmp_path):
    # Omitting all_ entirely (the default) means no __all__ is written.
    module_file = make_module_file(tmp_path / "plain.py", docstring="Plain module.")

    spec = ModuleSpec(name="plain", path=module_file)
    module = spec.load_module()

    assert module.docstring == "Plain module."
    assert module.exports is None


def test_load_module_reuses_already_imported_module(tmp_path, monkeypatch):
    import sys
    import types

    fake = types.ModuleType("already_loaded")
    fake.__doc__ = "cached"
    monkeypatch.setitem(sys.modules, "already_loaded", fake)

    module_file = make_module_file(tmp_path / "unused.py", docstring="unused")
    spec = ModuleSpec(name="already_loaded", path=module_file)

    module = spec.load_module()

    assert module.module is fake
    assert module.docstring == "cached"


def test_load_module_raises_for_invalid_source(tmp_path):
    module_file = make_module_file(
        tmp_path / "broken.py", body="this is not valid python !!!"
    )
    spec = ModuleSpec(name="broken", path=module_file)

    with pytest.raises(SyntaxError):
        spec.load_module()


# ---------------------------------------------------------------------------
# iter_submodules()
# ---------------------------------------------------------------------------


def test_iter_submodules_walks_files_and_packages_in_sorted_order(tmp_path):
    root = make_package(tmp_path / "app")
    make_module_file(root / "util.py")
    sub_pkg = make_package(root / "sub")
    make_module_file(sub_pkg / "deep.py")

    spec = ModuleSpec(name="app", path=root)
    found = [s.name for s in spec.iter_submodules()]

    # A package's own __init__.py is the package itself, never a submodule.
    assert found == ["app.sub", "app.sub.deep", "app.util"]


def test_iter_submodules_order_does_not_depend_on_creation_order(tmp_path):
    root = make_package(tmp_path / "app")
    for name in ("zeta", "alpha", "mid", "beta"):
        make_module_file(root / f"{name}.py")

    spec = ModuleSpec(name="app", path=root)

    assert [s.name for s in spec.iter_submodules()] == [
        "app.alpha",
        "app.beta",
        "app.mid",
        "app.zeta",
    ]


def test_iter_submodules_skip_private_excludes_underscore_prefixed(tmp_path):
    root = make_package(tmp_path / "app")
    make_module_file(root / "public.py")
    make_module_file(root / "_private.py")
    make_package(root / "_hidden")
    make_module_file(root / "_hidden" / "inner.py")

    spec = ModuleSpec(name="app", path=root)
    found = [s.name for s in spec.iter_submodules(skip_private=True)]

    assert found == ["app.public"]


def test_iter_submodules_skips_names_that_are_not_python_identifiers(tmp_path):
    root = make_package(tmp_path / "app")
    make_module_file(root / "ok.py")
    make_module_file(root / "my-script.py")
    make_module_file(root / "static-files" / "helper.py")

    spec = ModuleSpec(name="app", path=root)

    assert [s.name for s in spec.iter_submodules()] == ["app.ok"]


def test_iter_submodules_on_a_plain_module_yields_nothing(tmp_path):
    module_file = make_module_file(tmp_path / "leaf.py")
    spec = ModuleSpec(name="leaf", path=module_file)

    assert list(spec.iter_submodules()) == []


def test_iter_submodules_recurses_into_dir_without_init_but_does_not_yield_it(tmp_path):
    root = make_package(tmp_path / "app")
    (root / "not_a_package").mkdir()
    (root / "not_a_package" / "readme.txt").write_text("hi")
    (root / "not_a_package" / "orphan.py").write_text("x = 1\n")

    spec = ModuleSpec(name="app", path=root)
    found = [s.name for s in spec.iter_submodules()]

    # The directory itself is never yielded as a spec (no __init__.py), but
    # iter_submodules still recurses into it and picks up .py files there.
    assert found == ["app.not_a_package.orphan"]


# ---------------------------------------------------------------------------
# find_public_modules()
# ---------------------------------------------------------------------------
#
# Each row is a fixture tree under tmp_path: path -> docstring (None = no
# docstring). Paths ending in "/" are packages; "ns/x.py" under a dir with
# no "/"-entry is a plain (namespace) directory. The roots are given as
# (name, relative path); the expected value is the ordered list of names.

DOC = "Documented."

PUBLIC_MODULE_CASES = [
    pytest.param(
        {"solo.py": None},
        [("solo", "solo.py")],
        ["solo"],
        id="root-module-is-public-even-without-docstring",
    ),
    pytest.param(
        {
            "pm_a/": DOC,
            "pm_a/zeta.py": DOC,
            "pm_a/alpha.py": DOC,
            "pm_a/nodoc.py": None,
            "pm_a/_private.py": DOC,
            "pm_a/_hidden/": DOC,
            "pm_a/_hidden/inner.py": DOC,
        },
        [("pm_a", "pm_a")],
        ["pm_a", "pm_a.alpha", "pm_a.zeta"],
        id="private-and-docstringless-submodules-are-skipped",
    ),
    pytest.param(
        {
            "pm_b/": None,
            "pm_b/sub/": DOC,
            "pm_b/sub/deep.py": DOC,
            "pm_b/ns/orphan.py": DOC,
            "pm_b/undocumented/": None,
            "pm_b/undocumented/inner.py": DOC,
        },
        [("pm_b", "pm_b")],
        [
            "pm_b",
            "pm_b.ns.orphan",
            "pm_b.sub",
            "pm_b.sub.deep",
            "pm_b.undocumented.inner",
        ],
        id="nested-packages-and-namespace-dirs",
    ),
    pytest.param(
        {"pm_one/": DOC, "pm_one/x.py": DOC, "pm_two/": DOC, "pm_two/y.py": DOC},
        [("pm_one", "pm_one"), ("pm_two", "pm_two")],
        ["pm_one", "pm_two", "pm_one.x", "pm_two.y"],
        id="roots-first-then-submodules-of-each-root",
    ),
]


def build_tree(root, tree):
    for rel, docstring in tree.items():
        if rel.endswith("/"):
            make_package(root / rel.rstrip("/"), docstring=docstring)
        else:
            make_module_file(root / rel, docstring=docstring)


@pytest.mark.parametrize(("tree", "roots", "expected"), PUBLIC_MODULE_CASES)
def test_find_public_modules(tmp_path, tree, roots, expected):
    build_tree(tmp_path, tree)
    specs = [ModuleSpec(name=name, path=tmp_path / rel) for name, rel in roots]

    modules = find_public_modules(specs)

    assert [m.name for m in modules] == expected
    assert all(isinstance(m, Module) for m in modules)


def test_find_public_modules_warns_about_missing_or_empty_all(tmp_path, caplog):
    pkg = make_package(tmp_path / "pm_w", docstring="Root, no __all__.")
    make_module_file(pkg / "api.py", docstring="Public API.", all_=["thing"])
    make_module_file(pkg / "legacy.py", docstring="No __all__ here.")
    make_module_file(pkg / "empty.py", docstring="Exports nothing.", all_=[])
    # No __all__, but explicit re-exports define its API: no warning.
    make_module_file(pkg / "_impl.py", body="def run():\n    pass\n")
    make_module_file(pkg / "cli.py", docstring="CLI.", body="from ._impl import run as run\n")

    with caplog.at_level("WARNING"):
        find_public_modules([ModuleSpec(name="pm_w", path=pkg)])

    messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert messages == [
        "Module pm_w.empty do not export any symbols",
        "Module pm_w.legacy has no __all__ attribute",
    ]


def test_find_public_modules_names_the_module_that_failed_to_import(tmp_path):
    pkg = make_package(tmp_path / "pm_err")
    broken = make_module_file(pkg / "broken.py", body="this is not valid python !!!")

    with pytest.raises(SyntaxError) as excinfo:
        find_public_modules([ModuleSpec(name="pm_err", path=pkg)])

    notes = "\n".join(getattr(excinfo.value, "__notes__", []))
    assert "pm_err.broken" in notes
    assert str(broken) in notes


def test_find_public_modules_supports_relative_imports_in_uninstalled_project(
    tmp_path,
):
    """Regression: modules used to be executed without being registered in
    sys.modules, so ``from .util import X`` failed unless the project was
    installed."""
    pkg = make_package(tmp_path / "pm_rel", docstring="Root.", body="from .util import X\n")
    make_module_file(pkg / "util.py", docstring="Util.", body="X = 1\n")
    make_module_file(pkg / "api.py", docstring="Api.", body="from .util import X\n")

    modules = find_public_modules([ModuleSpec(name="pm_rel", path=pkg)])

    assert [m.name for m in modules] == ["pm_rel", "pm_rel.api", "pm_rel.util"]
    assert modules[1].module.X == 1


def test_find_public_modules_loads_dataclasses_with_postponed_annotations(tmp_path):
    """Regression (seen in mdq): ``@dataclass`` under ``from __future__ import
    annotations`` looks its module up in sys.modules, which crashed when the
    module was executed without being registered there."""
    pkg = make_package(tmp_path / "pm_dc", docstring="Root.")
    sub = make_package(pkg / "convert", docstring="Converters.")
    make_module_file(
        sub / "aiken.py",
        docstring="Aiken.",
        body=(
            "from __future__ import annotations\n"
            "from dataclasses import dataclass\n"
            "from ..models import Question\n"
            "\n"
            "@dataclass\n"
            "class AikenQuestion:\n"
            "    stem: str\n"
            "    question: Question | None = None\n"
        ),
    )
    make_module_file(pkg / "models.py", docstring="Models.", body="class Question: ...\n")

    modules = find_public_modules([ModuleSpec(name="pm_dc", path=pkg)])

    by_name = {m.name: m.module for m in modules}
    aiken = by_name["pm_dc.convert.aiken"]
    assert aiken.AikenQuestion("stem").stem == "stem"
    # One module object per name: the relative import sees the same models.
    assert aiken.Question is by_name["pm_dc.models"].Question


# ---------------------------------------------------------------------------
# Module.render()
# ---------------------------------------------------------------------------


def test_module_render_falls_back_to_blanket_members_without_all(tmp_path):
    module_file = make_module_file(tmp_path / "widgets.py", docstring="Widgets.")
    spec = ModuleSpec(name="widgets", path=module_file)
    module = spec.load_module()

    rendered = module.render()

    assert rendered.splitlines() == [
        "widgets",
        "=======",
        "",
        ".. automodule:: widgets",
        "   :members:",
    ]


def test_module_render_lists_all_entries_explicitly_in_order(tmp_path):
    module_file = make_module_file(
        tmp_path / "widgets.py",
        all_=["Widget", "make_widget"],
        body="class Widget:\n    pass\n\n\ndef make_widget():\n    return Widget()\n",
    )
    spec = ModuleSpec(name="widgets", path=module_file)
    module = spec.load_module()

    rendered = module.render()

    assert rendered.splitlines() == [
        "widgets",
        "=======",
        "",
        ".. automodule:: widgets",
        "",
        ".. autoclass:: widgets.Widget",
        "   :members:",
        "   :member-order: bysource",
        "",
        ".. autofunction:: widgets.make_widget",
    ]


def test_module_render_lists_explicit_reexports_when_there_is_no_all(tmp_path):
    """Packages like typer have no __all__ and expose their API with
    ``from x import y as y`` re-exports, which autodoc's ``:members:``
    skips. Those, plus public classes and functions defined in the module,
    are listed explicitly in source order."""
    pkg = make_package(tmp_path / "reexp", body=(
        "import os\n"
        "from shutil import get_terminal_size as get_terminal_size\n"
        "from . import colors as colors\n"
        "from ._impl import App as App\n"
        "from ._impl import helper\n"
        "\n"
        "def main():\n"
        "    '''Entry point.'''\n"
        "\n"
        "def _private():\n"
        "    pass\n"
    ))
    make_module_file(pkg / "colors.py", docstring="Colors.")
    make_module_file(
        pkg / "_impl.py",
        body="class App:\n    '''An app.'''\n\ndef helper():\n    pass\n",
    )
    module = ModuleSpec(name="reexp", path=pkg).load_module()

    assert module.render().splitlines() == [
        "reexp",
        "=====",
        "",
        ".. automodule:: reexp",
        "",
        ".. autofunction:: reexp.get_terminal_size",
        "",
        ".. autoclass:: reexp.App",
        "   :members:",
        "   :member-order: bysource",
        "",
        ".. autofunction:: reexp.main",
    ]
