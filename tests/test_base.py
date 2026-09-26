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
from doc0.tree import DocTree, WritePolicy
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


# (--theme / Doc0.load(theme=...), [tool.doc-zero] theme) -> Sphinx theme.
# A pyproject value of None means the key is absent.
THEME_CASES = [
    pytest.param(None, None, "alabaster", id="default"),
    pytest.param(None, '"rtd"', "sphinx_rtd_theme", id="pyproject-alias-rtd"),
    pytest.param(
        None, '"readthedocs"', "sphinx_rtd_theme", id="pyproject-alias-readthedocs"
    ),
    pytest.param(None, '"default"', "alabaster", id="pyproject-alias-default"),
    pytest.param(None, '"furo"', "furo", id="pyproject-plain-name"),
    pytest.param(
        None, '"sphinx_material.theme"', "sphinx_material.theme", id="dotted-name"
    ),
    pytest.param("rtd", None, "sphinx_rtd_theme", id="cli-alias"),
    pytest.param("sphinx_book_theme", '"rtd"', "sphinx_book_theme", id="cli-wins"),
    pytest.param("default", '"furo"', "alabaster", id="cli-alias-wins"),
    pytest.param("furo", '"bad theme"', "furo", id="unused-pyproject-value-ignored"),
]

THEME_ERROR_CASES = [
    pytest.param("bad theme", None, ["'bad theme'", "--theme"], id="invalid-cli"),
    pytest.param("", '"furo"', ["--theme"], id="empty-cli"),
    pytest.param(
        None, '"bad theme"', ["'bad theme'", "tool.doc-zero"], id="invalid-pyproject"
    ),
    pytest.param(None, "42", ["42", "tool.doc-zero"], id="non-string-pyproject"),
]


def theme_project(root: Path, pyproject_theme: str | None) -> Path:
    extra = ""
    if pyproject_theme is not None:
        extra = f"\n[tool.doc-zero]\ntheme = {pyproject_theme}\n"
    return make_loadable_project(root, name="acme", extra_toml=extra)


@pytest.mark.parametrize(("cli", "pyproject_theme", "expected"), THEME_CASES)
def test_load_resolves_theme(tmp_path, cli, pyproject_theme, expected):
    theme_project(tmp_path, pyproject_theme)

    doc = Doc0.load(tmp_path, theme=cli)

    assert doc.theme == expected
    conf = doc.generate().files[doc.doc_root / "conf.py"].content
    assert f"html_theme = {expected!r}" in conf


@pytest.mark.parametrize(("cli", "pyproject_theme", "fragments"), THEME_ERROR_CASES)
def test_load_rejects_invalid_theme_naming_its_source(
    tmp_path, cli, pyproject_theme, fragments
):
    theme_project(tmp_path, pyproject_theme)

    with pytest.raises(ValueError) as excinfo:
        Doc0.load(tmp_path, theme=cli)

    for fragment in fragments:
        assert fragment in str(excinfo.value)


def test_load_defaults_root_to_cwd(tmp_path, monkeypatch):
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)
    monkeypatch.chdir(tmp_path)

    doc = Doc0.load()

    assert doc.root == tmp_path


# ---------------------------------------------------------------------------
# A minimal, loadable project fixture
# ---------------------------------------------------------------------------


def make_loadable_project(tmp_path, **toml_kwargs):
    """
    A project whose sole root module is a single .py file.

    Goes through the "uv build system" layout with module-name "acme" and
    module-root "" (the project root), resolving to the single-file module
    <root>/acme.py. This shape is kept simple and dependency-free for tests
    that only care about the docs-generation pipeline, not module layout
    detection (which has its own coverage in test_pyproject.py).
    """
    make_pyproject_toml(
        tmp_path,
        build_backend="uv_build",
        module_name="acme",
        **toml_kwargs,
    )
    make_module_file(
        tmp_path / "acme.py",
        docstring="The acme package.",
        all_=["main"],
    )
    return tmp_path


# ---------------------------------------------------------------------------
# generate(): the doc tree as data
# ---------------------------------------------------------------------------


def generate(root: Path, **load_kwargs) -> tuple[Doc0, DocTree]:
    doc = Doc0.load(root, **load_kwargs)
    return doc, doc.generate()


def snapshot(root: Path) -> dict[str, str | None]:
    """Every path under *root*, with file contents (None for directories)."""
    return {
        str(p.relative_to(root)): (p.read_text() if p.is_file() else None)
        for p in sorted(root.rglob("*"))
        if "__pycache__" not in p.parts
    }


def test_generate_writes_nothing_to_disk(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")  # no README.md, no docs/
    before = snapshot(tmp_path)

    Doc0.load(tmp_path).generate()

    assert snapshot(tmp_path) == before


def test_generate_lists_every_file_with_its_write_policy(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc, tree = generate(tmp_path)
    docs = tmp_path / "docs"

    assert {path: f.policy for path, f in tree.files.items()} == {
        docs / "conf.py": WritePolicy.OVERWRITE,
        docs / "index.rst": WritePolicy.OVERWRITE,
        docs / "_readme.md": WritePolicy.OVERWRITE,
        docs / "api" / "acme.rst": WritePolicy.OVERWRITE,
        docs / "api" / "_index.rst": WritePolicy.OVERWRITE,
        docs / "requirements.txt": WritePolicy.IF_MISSING,
        tmp_path / ".readthedocs.yml": WritePolicy.IF_MISSING,
    }
    assert tree.dirs == [docs / "_static"]
    assert tree.owned_dirs == [docs / "api"]


def test_generate_requirements_pin_doc_zero(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc, tree = generate(tmp_path)

    assert tree.files[doc.doc_root / "requirements.txt"].content.startswith(
        "doc-zero>="
    )


def test_generate_places_everything_under_a_custom_docs_dir(tmp_path: Path):
    """Regression: requirements.txt used to go to <root>/docs regardless."""
    make_loadable_project(tmp_path, name="acme")
    doc, tree = generate(tmp_path, docs="site")
    site = tmp_path / "site"

    assert site / "requirements.txt" in tree.files
    outside_site = [p for p in tree.files if site not in p.parents]
    assert outside_site == [tmp_path / ".readthedocs.yml"]

    rtd = tree.files[tmp_path / ".readthedocs.yml"].content
    assert "configuration: site/conf.py" in rtd
    assert "requirements: site/requirements.txt" in rtd


# --- API pages and public-module discovery ---------------------------------


def test_generate_documents_a_package_shaped_root_module(tmp_path):
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)
    make_package(tmp_path / "acme", docstring="The acme package.", all_=["main"])

    doc, tree = generate(tmp_path)

    assert doc.doc_root / "api" / "acme.rst" in tree.files
    index = tree.files[doc.doc_root / "index.rst"].content
    assert "Welcome to the acme documentation!" in index


def test_generate_documents_exactly_the_public_modules_in_order(tmp_path):
    """
    Which modules are public, and in what order, is decided by
    find_public_modules() (see test_module.py); generate() writes one page
    per public module and lists them in that order in api/_index.rst.
    """
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)
    pkg = make_package(tmp_path / "acme", docstring="The acme package.", all_=["main"])
    for name in ("zeta", "alpha", "mid"):
        make_module_file(pkg / f"{name}.py", docstring=f"{name}.", all_=[])
    make_module_file(pkg / "helpers.py", docstring=None)
    make_module_file(pkg / "_private.py")

    doc, tree = generate(tmp_path)

    expected = ["acme", "acme.alpha", "acme.mid", "acme.zeta"]
    api = doc.doc_root / "api"
    pages = sorted(p.stem for p in tree.files if p.parent == api)
    assert pages == sorted([*expected, "_index"])
    api_index = tree.files[api / "_index.rst"].content
    toctree = [
        line.strip()
        for line in api_index.splitlines()
        if line.startswith("   ") and not line.strip().startswith(":")
    ]
    assert toctree == expected


def test_generate_api_page_and_index_for_single_file_module(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc, tree = generate(tmp_path)

    index = tree.files[doc.doc_root / "index.rst"].content
    assert ".. mdinclude:: _readme.md" in index
    assert "   api/_index" in index

    api_index = tree.files[doc.doc_root / "api" / "_index.rst"].content
    assert "   acme" in api_index

    module_rst = tree.files[doc.doc_root / "api" / "acme.rst"].content
    assert module_rst.splitlines()[:2] == ["acme", "===="]
    assert ".. automodule:: acme" in module_rst


# --- index.rst: diataxis sections ------------------------------------------


@pytest.mark.parametrize(
    ("entry", "toctree_entry"),
    [
        ("tutorials/", "tutorials"),
        ("how-to-guides/", "how-to-guides"),
        ("user-guides/", "user-guides"),
        ("explanations/", "explanations"),
        ("concepts/", "concepts"),
        ("concept.rst", "concept"),
        ("user-guide.md", "user-guide"),
    ],
)
def test_generate_index_includes_diataxis_section_when_present(
    tmp_path: Path, entry, toctree_entry
):
    make_loadable_project(tmp_path, name="acme")
    target = tmp_path / "docs" / entry.rstrip("/")
    if entry.endswith("/"):
        target.mkdir(parents=True)
    else:
        write(target, "Content.\n")

    doc, tree = generate(tmp_path)

    index = tree.files[doc.doc_root / "index.rst"].content
    assert f"   {toctree_entry}" in index


def test_generate_index_omits_diataxis_sections_when_absent(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc, tree = generate(tmp_path)

    index = tree.files[doc.doc_root / "index.rst"].content
    for entry in ("tutorial", "how-to-guide", "user-guide", "explanation", "concept"):
        assert f"   {entry}" not in index


# --- _readme.md ------------------------------------------------------------


def readme_md(tmp_path: Path, readme: str | None) -> str:
    make_loadable_project(tmp_path, name="acme")
    if readme is not None:
        write(tmp_path / "README.md", readme)
    doc, tree = generate(tmp_path)
    assert tmp_path / "README.md" not in tree.files
    return tree.files[doc.doc_root / "_readme.md"].content


def test_generate_readme_placeholder_goes_to_docs_not_project_root(tmp_path: Path):
    """Regression: the placeholder used to be written to <root>/README.md."""
    assert "acme" in readme_md(tmp_path, None)


@pytest.mark.parametrize(
    ("readme", "expected"),
    [
        pytest.param(
            "# Acme\n\nAcme does things.\n", "Acme does things.", id="atx-title"
        ),
        pytest.param(
            "Acme\n====\n\nAcme does things.\n",
            "Acme does things.",
            id="setext-title",
        ),
        pytest.param(
            "# Acme\n\nBadges and noise.\n\n<!-- doc0-start -->\n\nAcme does things.\n",
            "\n\nAcme does things.\n",
            id="doc0-start-marker",
        ),
        pytest.param(
            "Just a plain paragraph, no title.\n",
            "Just a plain paragraph, no title.",
            id="no-title",
        ),
        pytest.param("", "", id="empty"),
    ],
)
def test_generate_readme_extracts_body_from_project_readme(
    tmp_path: Path, readme, expected
):
    assert readme_md(tmp_path, readme) == expected


def test_generate_readme_accepts_the_documented_doc_zero_start_marker(tmp_path: Path):
    """The user guide documents ``<!-- doc-zero-start -->``; the code used to
    accept only ``<!-- doc0-start -->``."""
    readme = "# Acme\n\n[![PyPI](https://img.shields.io/pypi/v/acme)](x)\n\n<!-- doc-zero-start -->\nBody.\n"
    assert readme_md(tmp_path, readme) == "\nBody.\n"


def test_generate_readme_marker_keeps_everything_after_it_verbatim(tmp_path: Path):
    """Badges after the marker are the user's explicit choice: keep them."""
    readme = "Noise.\n<!-- doc0-start -->\n![CI](https://img.shields.io/x)\nBody.\n"
    assert readme_md(tmp_path, readme) == "\n![CI](https://img.shields.io/x)\nBody.\n"


@pytest.mark.parametrize(
    ("readme", "expected"),
    [
        pytest.param(
            "Noise.\n<!-- doc-zero-start -->\nBody.\n<!-- doc-zero-end -->\nFooter.\n",
            "\nBody.\n",
            id="start-and-end-markers",
        ),
        pytest.param(
            "Noise.\n<!--doc0-start-->\nBody.\n<!--doc0-end-->\nFooter.\n",
            "\nBody.\n",
            id="legacy-markers-without-spaces",
        ),
        pytest.param(
            "# Acme\n"
            "\n"
            "![PyPI](https://img.shields.io/pypi/v/acme)\n"
            "\n"
            "Acme does things.\n"
            "<!-- doc-zero-end -->\n"
            "## Contributing\n",
            "Acme does things.",
            id="end-marker-only-applies-default-rules-to-the-rest",
        ),
        pytest.param(
            "<!-- doc-zero-end -->\nNoise.\n<!-- doc-zero-start -->\nBody.\n",
            "\nBody.\n",
            id="end-marker-before-start-marker-is-ignored",
        ),
    ],
)
def test_generate_readme_end_marker_drops_everything_after_it(
    tmp_path: Path, readme, expected
):
    assert readme_md(tmp_path, readme) == expected


@pytest.mark.parametrize(
    ("readme", "expected"),
    [
        pytest.param(
            "# Acme\n"
            "\n"
            "[![PyPI](https://img.shields.io/pypi/v/acme.svg)](https://pypi.org/project/acme)\n"
            "[![Docs](https://readthedocs.org/projects/acme/badge/?version=latest)](https://acme.rtfd.io)\n"
            "[![CI](https://github.com/me/acme/actions/workflows/ci.yml/badge.svg)](https://github.com/me/acme/actions)\n"
            "\n"
            "Acme does things.\n",
            "Acme does things.",
            id="badge-lines-under-title",
        ),
        pytest.param(
            "# Acme\n"
            "\n"
            "[![Coverage](https://coveralls.io/repos/github/me/acme/badge.svg?branch=main)](https://coveralls.io/x) "
            "![codecov](https://codecov.io/gh/me/acme/graph/badge.svg) "
            "![Downloads](https://static.pepy.tech/badge/acme)\n"
            "\n"
            "Acme does things.\n",
            "Acme does things.",
            id="several-badges-on-one-line",
        ),
        pytest.param(
            "[![PyPI](https://badge.fury.io/py/acme.svg)](https://pypi.org/project/acme)\n"
            "\n"
            "# Acme\n"
            "\n"
            "Acme does things.\n",
            "Acme does things.",
            id="badges-above-title",
        ),
        pytest.param(
            "# Acme\n"
            "\n"
            "[![PyPI][pypi-badge]][pypi-link]\n"
            "\n"
            "Acme does things. See [the docs][docs].\n"
            "\n"
            "[pypi-badge]: https://img.shields.io/pypi/v/acme\n"
            "[pypi-link]: https://pypi.org/project/acme\n"
            "[docs]: https://acme.rtfd.io\n",
            "Acme does things. See [the docs][docs].\n\n[docs]: https://acme.rtfd.io",
            id="reference-style-badges-and-their-definitions",
        ),
        pytest.param(
            "# Acme\n"
            "\n"
            '<a href="https://pypi.org/project/acme"><img src="https://img.shields.io/pypi/v/acme" alt="PyPI"></a>\n'
            '<img src="https://img.shields.io/badge/license-MIT-blue">\n'
            "\n"
            "Acme does things.\n",
            "Acme does things.",
            id="html-badges",
        ),
        pytest.param(
            "# Acme\n"
            "\n"
            "Acme does things.\n"
            "\n"
            "![Build status](https://img.shields.io/badge/build-passing-green)\n"
            "\n"
            "More text.\n",
            "Acme does things.\n\nMore text.",
            id="badge-line-later-in-document",
        ),
        pytest.param(
            "# Acme\n"
            "\n"
            "Acme is ![stable](https://img.shields.io/badge/stable-yes-green) software.\n",
            "Acme is ![stable](https://img.shields.io/badge/stable-yes-green) software.",
            id="inline-badge-in-prose-is-kept",
        ),
        pytest.param(
            "# Acme\n"
            "\n"
            "![Architecture](docs/_static/architecture.png)\n"
            "[![Screenshot](https://example.com/shot.png)](https://example.com)\n",
            "![Architecture](docs/_static/architecture.png)\n"
            "[![Screenshot](https://example.com/shot.png)](https://example.com)",
            id="non-badge-images-are-kept",
        ),
        pytest.param(
            "# Acme\n"
            "\n"
            '<img src="docs/logo.png" alt="Acme logo">\n'
            "\n"
            "Acme does things. ![PyPI][pypi]\n"
            "\n"
            "[pypi]: https://img.shields.io/pypi/v/acme\n",
            '<img src="docs/logo.png" alt="Acme logo">\n\nAcme does things. ![PyPI][pypi]\n\n[pypi]: https://img.shields.io/pypi/v/acme',
            id="non-badge-html-image-and-inline-reference-badge-are-kept",
        ),
        pytest.param(
            "# Acme\n"
            "\n"
            "Acme does things.\n"
            "\n"
            "![PyPI][pypi]\n"
            "\n"
            "[pypi]: https://img.shields.io/pypi/v/acme\n",
            "Acme does things.",
            id="badge-definitions-at-end-of-file",
        ),
        pytest.param(
            "# Acme\n"
            "\n"
            "```markdown\n"
            "![PyPI](https://img.shields.io/pypi/v/acme)\n"
            "```\n",
            "```markdown\n![PyPI](https://img.shields.io/pypi/v/acme)\n```",
            id="badges-inside-code-fences-are-kept",
        ),
    ],
)
def test_generate_readme_strips_known_badges_by_default(
    tmp_path: Path, readme, expected
):
    assert readme_md(tmp_path, readme) == expected


# --- conf.py ---------------------------------------------------------------


def conf_py(tmp_path: Path, license: str | None = None, **toml_kwargs) -> str:
    make_loadable_project(tmp_path, name="acme", **toml_kwargs)
    if license is not None:
        write(tmp_path / "LICENSE", license)
    doc, tree = generate(tmp_path)
    return tree.files[doc.doc_root / "conf.py"].content


def test_conf_uses_first_author_name_and_email_from_pyproject(tmp_path: Path):
    conf = conf_py(
        tmp_path, authors=[{"name": "Ada Lovelace", "email": "ada@example.com"}]
    )
    assert "author = 'Ada Lovelace <ada@example.com>'" in conf


def test_conf_falls_back_to_unknown_author_without_pyproject_authors_or_license(
    tmp_path: Path,
):
    conf = conf_py(tmp_path, include_authors=False)
    assert "copyright = 'unknown author'" in conf


def test_conf_reads_year_and_author_from_license_copyright_notice(tmp_path: Path):
    conf = conf_py(
        tmp_path,
        license="Copyright (c) 2019, Grace Hopper\n\nAll rights reserved.\n",
        include_authors=False,
    )
    assert "copyright = '2019, Grace Hopper'" in conf


def test_conf_pyproject_author_takes_precedence_over_license_author(tmp_path: Path):
    conf = conf_py(
        tmp_path,
        license="Copyright (c) 2019, Grace Hopper\n",
        authors=[{"name": "Ada Lovelace"}],
    )
    assert "author = 'Ada Lovelace'" in conf
    assert "copyright = '2019, Ada Lovelace'" in conf


def test_conf_ignores_license_without_a_recognizable_copyright_notice(
    tmp_path: Path,
):
    """
    A LICENSE with no "Copyright <year>" line is not an error: the year is
    simply omitted and the author falls back like when there is no LICENSE.
    """
    conf = conf_py(
        tmp_path, license="This software is provided as-is.\n", include_authors=False
    )
    assert "copyright = 'unknown author'" in conf


def test_conf_includes_default_sphinx_extensions_and_theme(tmp_path: Path):
    conf = conf_py(tmp_path)
    assert "extensions = ['sphinx.ext.autodoc', 'sphinx_mdinclude']" in conf
    assert "html_theme = 'alabaster'" in conf


# ---------------------------------------------------------------------------
# init(): writing the tree
# ---------------------------------------------------------------------------


def test_init_writes_the_generated_tree(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    tree = doc.generate()

    doc.init()

    for path, file in tree.files.items():
        assert path.read_text() == file.content, path
    assert (doc.doc_root / "_static").is_dir()


def test_init_overwrites_owned_files_but_keeps_user_owned_ones(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    write(doc.doc_root / "conf.py", "# stale\n")
    write(doc.doc_root / "index.rst", "stale\n")
    write(doc.doc_root / "requirements.txt", "my-requirements\n")
    write(tmp_path / ".readthedocs.yml", "# my rtd config\n")

    doc.init()

    assert "project = 'acme'" in (doc.doc_root / "conf.py").read_text()
    assert "Welcome to the acme" in (doc.doc_root / "index.rst").read_text()
    assert (doc.doc_root / "requirements.txt").read_text() == "my-requirements\n"
    assert (tmp_path / ".readthedocs.yml").read_text() == "# my rtd config\n"


def test_init_removes_stale_api_pages(tmp_path: Path):
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path)
    write(doc.doc_root / "api" / "removed_module.rst", "stale\n")

    doc.init()

    assert sorted(p.name for p in (doc.doc_root / "api").iterdir()) == [
        "_index.rst",
        "acme.rst",
    ]


def test_init_with_custom_docs_dir_writes_only_there(tmp_path: Path):
    """Regression for requirements.txt landing in docs/ and README.md at the root."""
    make_loadable_project(tmp_path, name="acme")
    doc = Doc0.load(tmp_path, docs="site")

    doc.init()

    site = tmp_path / "site"
    assert (site / "requirements.txt").is_file()
    assert (site / "_readme.md").is_file()
    assert (site / "_static").is_dir()
    assert not (tmp_path / "docs").exists()
    assert not (tmp_path / "README.md").exists()


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


@pytest.mark.parametrize("returncode", [0, 2])
def test_build_returns_the_sphinx_exit_status(
    tmp_path: Path, fake_sphinx: dict[str, Recorder], returncode: int
):
    """Regression: build() used to drop Sphinx's exit status, so a failed
    build still looked successful."""
    make_loadable_project(tmp_path, name="acme")
    fake_sphinx["build"].returncode = returncode

    assert Doc0.load(tmp_path).build() == returncode


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
