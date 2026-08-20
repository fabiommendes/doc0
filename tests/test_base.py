"""
Scenario tests for doc0's toplevel public entry point: the Doc0 class.

These tests build small fixture projects on disk and drive them entirely
through Doc0's public methods and properties.

Sphinx and sphinx-autobuild are stubbed out via the fake_sphinx fixture
(see conftest.py) since Doc0 only imports them

lazily inside build()/serve() -- this lets the full public flow run without
those (heavy) dependencies installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import make_module_file, make_package, make_pyproject_toml, write

from doc0 import Doc0
from tests.conftest import Recorder

# ---------------------------------------------------------------------------
# Doc0.load() / .root
# ---------------------------------------------------------------------------


def test_load_builds_doc_root_under_docs_by_default(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)

    doc = Doc0.load(tmp_path)

    assert doc.doc_root == tmp_path / "docs"
    assert doc.root == tmp_path
    assert doc.theme == "alabaster"


def test_load_accepts_custom_docs_dir_and_theme(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)

    doc = Doc0.load(tmp_path, theme="sphinx_rtd_theme", docs="site")

    assert doc.doc_root == tmp_path / "site"
    assert doc.theme == "sphinx_rtd_theme"


def test_load_defaults_root_to_cwd(tmp_path, monkeypatch):
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)
    monkeypatch.chdir(tmp_path)

    doc = Doc0.load()

    assert doc.root == tmp_path


# ---------------------------------------------------------------------------
# A minimal, loadable project fixture
#
# NOTE: ModuleSpec.load_module() currently passes the package *directory*
# (rather than its __init__.py) to importlib, so it cannot load anything
# package-shaped -- see tests/test_module.py::test_load_module_on_a_package_raises_importerror.
# Doc0.write_rst_files() calls root.load_module() on every project root
# module, so *any* project whose root is a package (the normal case --
# including doc0's own toplevel-package layout) currently fails before it
# gets anywhere near conf.py/index.rst generation. We characterize that
# failure below, and use a single-file root module (which is not
# package-shaped) to exercise the rest of the successful pipeline.
# ---------------------------------------------------------------------------


def make_loadable_project(tmp_path, **toml_kwargs):
    """
    A project whose sole root module is a single .py file, so it can
    actually be loaded despite the load_module() package bug.

    This has to go through the "uv build system" layout heuristic with
    module-name set to the literal filename "acme.py": every *other*
    layout heuristic (src layout, toplevel package layout) can only ever
    discover directories (packages) as root modules, which are exactly
    what load_module() cannot load. The resulting root module's name is
    therefore "acme.py" (including the suffix) rather than "acme" -- a
    direct, visible consequence of the same bug.
    """
    make_pyproject_toml(
        tmp_path,
        build_backend="uv_build",
        module_name="acme.py",
        **toml_kwargs,
    )
    make_module_file(
        tmp_path / "acme.py",
        docstring="The acme package.",
        all_=["main"],
    )
    return tmp_path


# ---------------------------------------------------------------------------
# write_rst_files() / init(): the package-loading bug, end to end
# ---------------------------------------------------------------------------


def test_write_rst_files_for_a_package_shaped_root_module(tmp_path):
    """
    Characterization test for the real-world impact of the load_module()
    bug: a project laid out exactly like doc0 itself (toplevel package with
    __init__.py) fails as soon as init()/build() tries to load it.
    """
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)
    make_package(tmp_path / "acme", docstring="The acme package.", all_=["main"])

    doc = Doc0.load(tmp_path)
    doc.write_rst_files()

    assert (doc.doc_root / "api" / "_index.rst").exists()
    assert (
        "Welcome to the acme documentation!" in (doc.doc_root / "index.rst").read_text()
    )


# ---------------------------------------------------------------------------
# init() / write_rst_files(): happy path
# ---------------------------------------------------------------------------


def test_init_creates_doc_root_static_dir_conf_and_index(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)

    doc.init()

    assert doc.doc_root.is_dir()
    assert (doc.doc_root / "_static").is_dir()
    assert (doc.doc_root / "conf.py").exists()
    assert (doc.doc_root / "index.rst").exists()
    assert (doc.doc_root / "api" / "acme.py.rst").exists()
    assert (doc.doc_root / "api" / "_index.rst").exists()


def test_init_does_not_overwrite_existing_conf_or_index_by_default(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)
    write(doc.doc_root / "conf.py", "# hand-written conf\n")
    write(doc.doc_root / "index.rst", "Hand-written index\n")

    doc.init()

    assert (doc.doc_root / "conf.py").read_text() == "# hand-written conf\n"
    assert (doc.doc_root / "index.rst").read_text() == "Hand-written index\n"


def test_init_force_conf_and_force_index_overwrite_existing_files(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)
    write(doc.doc_root / "conf.py", "# stale\n")
    write(doc.doc_root / "index.rst", "stale\n")

    doc.init(force_conf=True, force_index=True)

    assert "project = 'acme'" in (doc.doc_root / "conf.py").read_text()
    assert "acme" in (doc.doc_root / "index.rst").read_text()


def test_write_rst_files_index_contains_module_and_readme_include(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.write_rst_files()

    index = (doc.doc_root / "index.rst").read_text()
    assert "Welcome to the acme documentation!" in index
    assert ".. mdinclude:: _readme.md" in index
    assert "   api/_index" in index

    api_index = (doc.doc_root / "api" / "_index.rst").read_text()
    assert "   acme.py" in api_index

    module_rst = (doc.doc_root / "api" / "acme.py.rst").read_text()
    assert module_rst.splitlines()[:2] == ["acme.py", "======="]
    assert ".. automodule:: acme.py" in module_rst


@pytest.mark.parametrize(
    ("dirname", "toctree_entry"),
    [
        ("tutorials", "tutorials"),
        ("how-to-guides", "how-to-guides"),
        ("explanations", "explanations"),
        ("concepts", "concepts"),
    ],
)
def test_write_rst_files_includes_diataxis_sections_when_present(
    tmp_path: Path, dirname, toctree_entry
):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)
    (doc.doc_root / dirname).mkdir()

    doc.write_rst_files()

    index = (doc.doc_root / "index.rst").read_text()
    assert f"   {toctree_entry}" in index


def test_write_rst_files_omits_diataxis_sections_when_absent(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.write_rst_files()

    index = (doc.doc_root / "index.rst").read_text()
    for entry in ("tutorials", "how-to-guides", "explanations", "concepts"):
        assert f"   {entry}" not in index


def test_write_rst_files_selects_rst_file_over_missing_directory(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)
    write(doc.doc_root / "concept.rst", "Concepts go here.\n")

    doc.write_rst_files()

    index = (doc.doc_root / "index.rst").read_text()
    assert "   concept" in index


# ---------------------------------------------------------------------------
# write_readme_md()
# ---------------------------------------------------------------------------


def test_write_readme_md_creates_placeholder_when_project_has_no_readme(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.write_readme_md()

    readme = doc.root / "README.md"
    assert readme.exists()
    assert "acme" in readme.read_text()
    # No source README existed, so nothing is copied into the docs tree.
    assert not (doc.doc_root / "_readme.md").exists()


def test_write_readme_md_strips_markdown_title_when_no_marker_present(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    write(
        tmp_path / "README.md",
        """\
        # Acme

        Acme does things.
        """,
    )
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.write_readme_md()

    rendered = (doc.doc_root / "_readme.md").read_text()
    assert not rendered.startswith("# Acme")
    assert "Acme does things." in rendered


def test_write_readme_md_uses_content_after_doc0_start_marker(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    write(
        tmp_path / "README.md",
        """\
        # Acme

        Badges and other noise that should be excluded.

        <!-- doc0-start -->

        Acme does things.
        """,
    )
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.write_readme_md()

    rendered = (doc.doc_root / "_readme.md").read_text()
    assert "Badges and other noise" not in rendered
    assert "Acme does things." in rendered


def test_write_readme_md_leaves_non_title_content_untouched(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    write(tmp_path / "README.md", "Just a plain paragraph, no title.\n")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.write_readme_md()

    rendered = (doc.doc_root / "_readme.md").read_text()
    assert rendered == "Just a plain paragraph, no title."


# ---------------------------------------------------------------------------
# Conf generation via init()/build(): authors, LICENSE copyright, extensions
# ---------------------------------------------------------------------------


def test_conf_uses_first_author_name_and_email_from_pyproject(tmp_path: Path):
    make_loadable_project(
        tmp_path,
        name="acme",
        authors=[{"name": "Ada Lovelace", "email": "ada@example.com"}],
    )
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.init()

    conf = (doc.doc_root / "conf.py").read_text()
    assert "Ada Lovelace <ada@example.com>" in conf


def test_conf_falls_back_to_unknown_author_without_pyproject_authors_or_license(
    tmp_path: Path,
):
    make_loadable_project(tmp_path, name="acme", include_authors=False)
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.init()

    conf = (doc.doc_root / "conf.py").read_text()
    assert "unknown author" in conf


def test_conf_reads_year_and_author_from_license_copyright_notice(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme", include_authors=False)
    write(
        tmp_path / "LICENSE",
        "Copyright (c) 2019, Grace Hopper\n\nAll rights reserved.\n",
    )
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.init()

    conf = (doc.doc_root / "conf.py").read_text()
    assert "copyright = '2019, Grace Hopper'" in conf


def test_conf_pyproject_author_takes_precedence_over_license_author(tmp_path: Path):
    make_loadable_project(
        tmp_path,
        name="acme",
        authors=[{"name": "Ada Lovelace"}],
    )
    write(tmp_path / "LICENSE", "Copyright (c) 2019, Grace Hopper\n")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.init()

    conf = (doc.doc_root / "conf.py").read_text()
    assert "author = 'Ada Lovelace'" in conf
    assert "2019, Ada Lovelace" in conf


def test_init_raises_when_license_exists_but_has_no_recognizable_copyright(
    tmp_path: Path,
):
    make_loadable_project(tmp_path, name="acme", include_authors=False)
    write(tmp_path / "LICENSE", "This software is provided as-is.\n")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    with pytest.raises(ValueError, match="Copyright notice not found"):
        doc.init()


def test_conf_includes_default_sphinx_extensions(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    doc.init()

    conf = (doc.doc_root / "conf.py").read_text()
    assert "sphinx.ext.autodoc" in conf
    assert "sphinx_mdinclude" in conf


# ---------------------------------------------------------------------------
# build() / serve() / test()
# ---------------------------------------------------------------------------


def test_build_initializes_docs_and_invokes_sphinx_with_expected_argv(
    tmp_path: Path, fake_sphinx: dict[str, Recorder]
):
    make_loadable_project(tmp_path, name="acme")

    doc = Doc0.load(tmp_path)
    doc.build()

    assert (doc.doc_root / "conf.py").exists()
    assert (doc.doc_root / "index.rst").exists()
    (argv,) = fake_sphinx["build"].calls
    assert argv == [str(doc.doc_root), str(doc.root / "dist" / "docs")]
    assert not fake_sphinx["serve"].calls


def test_build_always_forces_conf_and_index_regeneration(tmp_path: Path, fake_sphinx):
    make_loadable_project(tmp_path, name="acme")

    doc = Doc0.load(tmp_path)
    doc.doc_root.mkdir(parents=True)

    write(doc.doc_root / "conf.py", "# stale\n")
    write(doc.doc_root / "index.rst", "stale\n")

    doc.build()

    assert "project = 'acme'" in (doc.doc_root / "conf.py").read_text()
    assert (
        "Welcome to the acme documentation!" in (doc.doc_root / "index.rst").read_text()
    )


def test_serve_initializes_docs_and_invokes_sphinx_autobuild_with_expected_argv(
    tmp_path: Path, fake_sphinx: dict[str, Recorder]
):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)

    doc.serve()

    (argv,) = fake_sphinx["serve"].calls
    assert argv == [str(doc.doc_root), str(doc.root / "dist" / "docs")]
    assert not fake_sphinx["build"].calls


def test_test_method_is_currently_a_noop(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)

    assert doc.test() is None
