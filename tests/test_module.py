"""
Scenario tests for doc0's module-loading public API: ModuleSpec and Module.
"""

from __future__ import annotations

import pytest
from conftest import make_module_file, make_package

from doc0 import Module, ModuleSpec

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


def test_load_module_raises_when_spec_from_file_location_returns_none(tmp_path, monkeypatch):
    """
    load_module() also has a defensive check for the case where
    importlib.util.spec_from_file_location() itself returns None. That
    doesn't happen for a real file under normal use, so we drive it via
    the documented importlib collaborator to exercise that branch of the
    public method.
    """
    import importlib.util

    module_file = make_module_file(tmp_path / "specless.py", docstring="x")
    spec = ModuleSpec(name="specless", path=module_file)

    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *a, **kw: None)

    with pytest.raises(ImportError, match="Cannot load module"):
        spec.load_module()


def test_load_module_raises_when_spec_has_no_loader(tmp_path, monkeypatch):
    """
    load_module() has a defensive check for the case where importlib hands
    back a spec with no loader attached. That combination doesn't occur
    for a plain file under normal use, so we drive it via the documented
    importlib collaborator to exercise that branch of the public method.
    """
    import importlib.util

    module_file = make_module_file(tmp_path / "loaderless.py", docstring="x")
    spec = ModuleSpec(name="loaderless", path=module_file)

    real_spec = importlib.util.spec_from_file_location(spec.name, spec.path)
    assert real_spec is not None

    real_spec.loader = None
    monkeypatch.setattr(
        importlib.util, "spec_from_file_location", lambda *a, **kw: real_spec
    )

    with pytest.raises(ImportError, match="Cannot load module"):
        spec.load_module()


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


def test_iter_submodules_walks_files_and_packages(tmp_path):
    root = make_package(tmp_path / "app")
    make_module_file(root / "util.py")
    sub_pkg = make_package(root / "sub")
    make_module_file(sub_pkg / "deep.py")

    spec = ModuleSpec(name="app", path=root)
    found = {s.name for s in spec.iter_submodules()}

    # Note: iter_submodules() also yields each package's own __init__.py as
    # a pseudo-submodule (e.g. "app.__init__"), since it does not special-
    # case that filename when walking .py files in a package directory.
    assert found == {
        "app.util",
        "app.sub",
        "app.sub.deep",
        "app.__init__",
        "app.sub.__init__",
    }


def test_iter_submodules_skip_private_excludes_underscore_prefixed(tmp_path):
    root = make_package(tmp_path / "app")
    make_module_file(root / "public.py")
    make_module_file(root / "_private.py")
    make_package(root / "_hidden")

    spec = ModuleSpec(name="app", path=root)
    found = {s.name for s in spec.iter_submodules(skip_private=True)}

    assert found == {"app.public"}


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
    found = {s.name for s in spec.iter_submodules()}

    # The directory itself is never yielded as a spec (no __init__.py), but
    # iter_submodules still recurses into it and picks up .py files there.
    assert found == {"app.__init__", "app.not_a_package.orphan"}


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
        "",
        ".. autofunction:: widgets.make_widget",
    ]
