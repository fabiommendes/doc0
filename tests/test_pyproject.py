"""
Scenario tests for doc0's project-introspection public API: ``PyProject``.
"""

from __future__ import annotations

import pytest
from conftest import make_module_file, make_package, make_pyproject_toml, write

from doc0 import PyProject

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
    make_pyproject_toml(
        tmp_path, name="acme", version="1.2.3", description="Acme tools."
    )

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
    assert authors[0].get("email") == "ada@example.com"
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

    with pytest.raises(
        TypeError, match="Expected project.version to be of type int, got str"
    ):
        project.get("project.version", type=int)

# ---------------------------------------------------------------------------
# find_root_modules(): layout resolution
# ---------------------------------------------------------------------------
#
# Each row is a small project on disk: the pyproject.toml text, the files to
# create (paths ending in "/" are packages, i.e. get an __init__.py; anything
# else is a single-file module), and the expected root modules as
# (module name, path relative to the project root) pairs, in order.

UV = '[build-system]\nrequires = ["uv_build"]\nbuild-backend = "uv_build"\n'
HATCH = '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n'


def project_toml(name: str = "acme", extra: str = "") -> str:
    return f'[project]\nname = "{name}"\nversion = "0.1.0"\n\n{extra}'


def uv_toml(name: str = "acme", backend_table: str | None = None) -> str:
    extra = UV
    if backend_table is not None:
        extra += f"\n[tool.uv.build-backend]\n{backend_table}"
    return project_toml(name, extra)


def build_tree(root, toml: str, files: list[str]) -> None:
    write(root / "pyproject.toml", toml)
    for entry in files:
        if entry.endswith("/"):
            make_package(root / entry.rstrip("/"))
        else:
            make_module_file(root / entry)


LAYOUT_CASES = [
    # --- uv_build backend: explicit configuration --------------------------
    pytest.param(
        uv_toml(backend_table='module-name = "acme"\nmodule-root = ""\n'),
        ["acme/"],
        [("acme", "acme")],
        id="uv-explicit-name-empty-root",
    ),
    pytest.param(
        uv_toml(backend_table='module-name = "acme"\nmodule-root = "lib"\n'),
        ["lib/acme/"],
        [("acme", "lib/acme")],
        id="uv-explicit-module-root",
    ),
    pytest.param(
        uv_toml(backend_table='module-name = "one, two"\nmodule-root = ""\n'),
        ["one/", "two/"],
        [("one", "one"), ("two", "two")],
        id="uv-comma-separated-module-names",
    ),
    pytest.param(
        uv_toml(backend_table='module-name = ["one", "two"]\nmodule-root = ""\n'),
        ["one/", "two/"],
        [("one", "one"), ("two", "two")],
        id="uv-list-of-module-names",
    ),
    pytest.param(
        uv_toml(backend_table='module-name = "other"\nmodule-root = ""\n'),
        ["other/", "acme/"],
        [("other", "other")],
        id="uv-wins-over-toplevel-package",
    ),
    # --- uv_build backend: uv's documented defaults (regression, bug 2) ----
    pytest.param(
        uv_toml(backend_table=None),
        ["src/acme/"],
        [("acme", "src/acme")],
        id="uv-no-backend-table-defaults-to-src-and-project-name",
    ),
    pytest.param(
        uv_toml(backend_table='module-root = "src"\n'),
        ["src/acme/"],
        [("acme", "src/acme")],
        id="uv-no-module-name-defaults-to-project-name",
    ),
    pytest.param(
        uv_toml(name="My-Pkg.Tools", backend_table=None),
        ["src/my_pkg_tools/"],
        [("my_pkg_tools", "src/my_pkg_tools")],
        id="uv-default-module-name-is-normalized-and-lowercased",
    ),
    pytest.param(
        uv_toml(backend_table='module-root = ""\n'),
        ["acme/"],
        [("acme", "acme")],
        id="uv-empty-module-root-means-project-root",
    ),
    pytest.param(
        uv_toml(backend_table='module-name = "foo.bar"\n'),
        ["src/foo/bar/"],
        [("foo.bar", "src/foo/bar")],
        id="uv-dotted-module-name-is-namespace-package",
    ),
    # --- src layout --------------------------------------------------------
    pytest.param(
        project_toml(extra=HATCH),
        ["src/acme/", "src/loose.py"],
        [("acme", "src/acme"), ("loose", "src/loose.py")],
        id="src-layout-packages-and-modules",
    ),
    pytest.param(
        project_toml(),
        ["src/acme/"],
        [("acme", "src/acme")],
        id="src-layout-without-build-system",
    ),
    # --- toplevel package layout -------------------------------------------
    pytest.param(
        project_toml(extra=HATCH),
        ["acme/"],
        [("acme", "acme")],
        id="toplevel-package",
    ),
    pytest.param(
        project_toml(name="my-pkg", extra=HATCH),
        ["my_pkg/"],
        [("my_pkg", "my_pkg")],
        id="toplevel-package-hyphenated-project-name",  # regression, bug 1
    ),
]


@pytest.mark.parametrize(("toml", "files", "expected"), LAYOUT_CASES)
def test_find_root_modules_resolves_layout(tmp_path, toml, files, expected):
    build_tree(tmp_path, toml, files)

    specs = PyProject(root=tmp_path).find_root_modules()

    assert [(s.name, s.path) for s in specs] == [
        (name, tmp_path / rel) for name, rel in expected
    ]


UNRESOLVABLE_CASES = [
    pytest.param(project_toml(extra=HATCH), [], id="nothing-to-find"),
    pytest.param(
        project_toml(extra=HATCH),
        ["src/loose.py", "src/not_a_package/.keep"],
        id="src-dir-without-packages",
    ),
    pytest.param(
        project_toml(name="my-pkg", extra=HATCH),
        ["my-pkg/"],
        id="toplevel-dir-not-named-after-normalized-name",
    ),
    pytest.param('[project]\nversion = "0.1.0"\n', [], id="project-without-name"),
]


@pytest.mark.parametrize(("toml", "files"), UNRESOLVABLE_CASES)
def test_find_root_modules_raises_one_error_naming_every_layout_tried(
    tmp_path, toml, files
):
    build_tree(tmp_path, toml, files)
    project = PyProject(root=tmp_path)

    with pytest.raises(RuntimeError) as excinfo:
        project.find_root_modules()

    message = str(excinfo.value)
    assert message.startswith("Could not determine the layout of the project")
    for layout in ("uv_build", "src", "toplevel"):
        assert layout in message


def test_find_root_modules_uv_missing_module_raises_clear_error(tmp_path):
    # uv_build is declared, so its (default) module location is authoritative:
    # a missing module is a configuration error, not "try another layout".
    build_tree(tmp_path, uv_toml(backend_table=None), ["acme/"])
    project = PyProject(root=tmp_path)

    with pytest.raises(RuntimeError) as excinfo:
        project.find_root_modules()

    message = str(excinfo.value)
    assert "uv_build" in message
    assert "acme" in message
    assert str(tmp_path / "src" / "acme") in message


def test_find_root_modules_uv_rejects_invalid_module_name_type(tmp_path):
    build_tree(tmp_path, uv_toml(backend_table="module-name = 42\n"), [])
    project = PyProject(root=tmp_path)

    with pytest.raises(ValueError, match="Invalid option"):
        project.find_root_modules()
