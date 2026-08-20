"""
Scenario tests for doc0's project-introspection public API: ``PyProject``.
"""

from __future__ import annotations

import pytest

from doc0 import PyProject

from conftest import make_module_file, make_package, make_pyproject_toml


# ---------------------------------------------------------------------------
# Loading pyproject.toml
# ---------------------------------------------------------------------------


def test_missing_pyproject_toml_warns_and_leaves_data_empty(tmp_path):
    with pytest.warns(UserWarning, match="pyproject.toml not found"):
        project = PyProject(root=tmp_path)

    assert project.data == {}
    assert project.project == {}


def test_present_pyproject_toml_is_parsed_without_warning(tmp_path, recwarn):
    make_pyproject_toml(tmp_path, name="mypkg")

    project = PyProject(root=tmp_path)

    assert not recwarn.list
    assert project.project["name"] == "mypkg"


# ---------------------------------------------------------------------------
# Basic properties
# ---------------------------------------------------------------------------


def test_name_version_description_properties(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", version="1.2.3", description="Acme tools.")

    project = PyProject(root=tmp_path)

    assert project.name == "acme"
    assert project.version == "1.2.3"
    assert project.description == "Acme tools."


def test_name_is_none_when_pyproject_toml_is_absent(tmp_path):
    project = PyProject(root=tmp_path)
    assert project.name is None


def test_authors_property_parses_name_and_email(tmp_path):
    make_pyproject_toml(
        tmp_path,
        authors=[
            {"name": "Ada Lovelace", "email": "ada@example.com"},
            {"name": "Alan Turing"},
        ],
    )

    project = PyProject(root=tmp_path)
    authors = project.authors

    assert authors[0]["name"] == "Ada Lovelace"
    assert authors[0]["email"] == "ada@example.com"
    assert authors[1]["name"] == "Alan Turing"
    assert "email" not in authors[1]


def test_authors_property_raises_when_authors_key_is_absent(tmp_path):
    make_pyproject_toml(tmp_path, include_authors=False)

    project = PyProject(root=tmp_path)

    with pytest.raises(TypeError):
        project.authors


# ---------------------------------------------------------------------------
# __getitem__ / get()
# ---------------------------------------------------------------------------


def test_getitem_returns_nested_value(tmp_path):
    make_pyproject_toml(tmp_path, name="acme")
    project = PyProject(root=tmp_path)

    assert project["project.name"] == "acme"


def test_getitem_raises_keyerror_for_missing_key(tmp_path):
    make_pyproject_toml(tmp_path, name="acme")
    project = PyProject(root=tmp_path)

    with pytest.raises(KeyError):
        project["project.nonexistent"]


def test_get_returns_default_for_missing_key(tmp_path):
    make_pyproject_toml(tmp_path, name="acme")
    project = PyProject(root=tmp_path)

    assert project.get("project.missing", default="fallback") == "fallback"
    assert project.get("project.missing") is None


def test_get_with_type_returns_value_when_type_matches(tmp_path):
    make_pyproject_toml(tmp_path, name="acme")
    project = PyProject(root=tmp_path)

    assert project.get("project.name", type=str) == "acme"


def test_get_with_type_mismatch_raises_typeerror_with_clean_message(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", version="1.0.0")
    project = PyProject(root=tmp_path)

    with pytest.raises(TypeError, match="Expected project.version to be of type int, got str"):
        project.get("project.version", type=int)


# ---------------------------------------------------------------------------
# find_root_modules(): the four branches
# ---------------------------------------------------------------------------


def test_find_root_modules_uv_layout_single_module_name(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", build_backend="uv_build", module_name="acme")
    make_package(tmp_path / "acme", docstring="acme module")

    project = PyProject(root=tmp_path)
    (spec,) = list(project.find_root_modules())

    assert spec.name == "acme"
    assert spec.path == tmp_path / "acme"


def test_find_root_modules_uv_layout_comma_separated_module_names(tmp_path):
    make_pyproject_toml(
        tmp_path, name="acme", build_backend="uv_build", module_name="one, two"
    )
    make_package(tmp_path / "one")
    make_package(tmp_path / "two")

    project = PyProject(root=tmp_path)
    names = {spec.name for spec in project.find_root_modules()}

    assert names == {"one", "two"}


def test_find_root_modules_uv_layout_with_module_root_prefix(tmp_path):
    make_pyproject_toml(
        tmp_path,
        name="acme",
        build_backend="uv_build",
        module_name="acme",
        module_root="lib",
    )
    make_package(tmp_path / "lib" / "acme")

    project = PyProject(root=tmp_path)
    (spec,) = list(project.find_root_modules())

    assert spec.path == tmp_path / "lib" / "acme"


def test_find_root_modules_uv_layout_without_module_name_yields_nothing(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", build_backend="uv_build", module_name=None)

    project = PyProject(root=tmp_path)

    assert list(project.find_root_modules()) == []


def test_find_root_modules_uv_layout_rejects_invalid_module_name_type(tmp_path):
    make_pyproject_toml(
        tmp_path,
        name="acme",
        build_backend="uv_build",
        module_name=None,
        extra_toml="",
    )
    # Inject an invalid (non-str, non-list) module-name value directly.
    toml_path = tmp_path / "pyproject.toml"
    toml_path.write_text(toml_path.read_text() + "module-name = 42\n")

    project = PyProject(root=tmp_path)

    with pytest.raises(ValueError, match="Invalid option"):
        list(project.find_root_modules())


def test_find_root_modules_src_layout(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)
    make_package(tmp_path / "src" / "acme")
    make_module_file(tmp_path / "src" / "loose.py")

    project = PyProject(root=tmp_path)
    names = {spec.name for spec in project.find_root_modules()}

    assert names == {"acme", "loose"}


def test_find_root_modules_toplevel_package_layout(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)
    make_package(tmp_path / "acme")

    project = PyProject(root=tmp_path)
    (spec,) = list(project.find_root_modules())

    assert spec.name == "acme"
    assert spec.path == tmp_path / "acme"


def test_find_root_modules_src_dir_present_but_empty_of_packages_is_not_src_layout(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)
    # A "src" directory exists, but none of its entries is a package (a
    # directory containing __init__.py) -- so _is_src_layout() must still
    # report False and fall through to the next heuristic.
    (tmp_path / "src" / "not_a_package").mkdir(parents=True)
    make_module_file(tmp_path / "src" / "loose.py")

    project = PyProject(root=tmp_path)

    with pytest.raises(RuntimeError, match="Could not determine the layout"):
        list(project.find_root_modules())


def test_find_root_modules_raises_when_layout_cannot_be_determined(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)
    # No src/, no toplevel acme/ package: nothing to find.

    project = PyProject(root=tmp_path)

    with pytest.raises(RuntimeError, match="Could not determine the layout"):
        list(project.find_root_modules())


def test_find_root_modules_prefers_uv_layout_over_toplevel(tmp_path):
    # If a uv build-backend is declared, that heuristic wins even if a
    # same-named toplevel package also happens to exist.
    make_pyproject_toml(tmp_path, name="acme", build_backend="uv_build", module_name="other")
    make_package(tmp_path / "other")
    make_package(tmp_path / "acme")

    project = PyProject(root=tmp_path)
    names = {spec.name for spec in project.find_root_modules()}

    assert names == {"other"}
