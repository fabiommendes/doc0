from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib.metadata import version as module_version
from pathlib import Path
from typing import Any, Iterable, Iterator, TypedDict

from .module import Module, find_public_modules
from .pyproject import PyProject
from .readme import readme_body
from .theme import resolve_theme
from .tree import DocFile, DocTree, WritePolicy
from .util import first_existing

type ModuleName = str

NOT_GIVEN: Any = object()
COPYRIGHT_RE = re.compile(
    r"[cC]opyright\s+(?:\(c\)\s+)?(?P<year>\d+)\s*(:?,?\s+(?P<author>[^\n]+))?"
)
DEFAULT_EXTENSIONS = [
    "sphinx.ext.autodoc",
    "sphinx_mdinclude",
    # "myst_parser",
]
README_PLACEHOLDER = (
    "This is the documentation for {name}. "
    "Please include a README.md file in the documentation root directory."
)
READTHEDOCS_TEMPLATE = """
# Read the Docs configuration file
# See https://docs.readthedocs.io/en/stable/config-file/v2.html for details

# Required
version: 2

# Set the OS, Python version, and other tools you might need
build:
  os: ubuntu-24.04
  tools:
    python: "3.13"

# Build documentation in the "{docs}/" directory with Sphinx
sphinx:
  configuration: {docs}/conf.py

# Optionally, but recommended,
# declare the Python requirements required to build your documentation
# See https://docs.readthedocs.io/en/stable/guides/reproducible-builds.html
python:
  install:
    - requirements: {docs}/requirements.txt
"""


@dataclass
class Doc0:
    """
    The root type representing the documentation of your project.
    """

    #: The pyproject.toml file for the project.
    pyproject: PyProject

    #: Base location for the documentation assets
    doc_root: Path

    #: The resolved Sphinx theme name to use for the documentation.
    theme: str

    @classmethod
    def load(
        cls,
        root: Path | None = None,
        /,
        *,
        theme: str | None = None,
        docs: str = "docs",
    ) -> Doc0:
        """
        Load project in the given path.

        ``theme`` is the CLI-provided value, if any; the final theme is
        resolved via ``doc0.theme.resolve_theme`` (CLI value, else
        ``[tool.doc-zero] theme`` in pyproject.toml, else the default).
        """
        root = root or Path.cwd()
        pyproject = PyProject(root=root)
        resolved_theme = resolve_theme(theme, pyproject)

        return Doc0(
            doc_root=root / docs,
            pyproject=pyproject,
            theme=resolved_theme,
        )

    @property
    def root(self) -> Path:
        """
        The root of the project.
        """
        return self.pyproject.root

    def init(self) -> None:
        """
        Generate the documentation content and write it to disk.
        """
        self.generate().write()

    def generate(self) -> DocTree:
        """
        Compute the documentation tree as data, without writing anything to
        disk (no directory is created, no file is read except the project's
        inputs: pyproject.toml, README.md, LICENSE, and the source modules).
        """
        pyproject = self.pyproject
        root = self.root
        doc_root = self.doc_root

        public_modules = find_public_modules(pyproject.find_root_modules())

        conf = Conf.from_pyproject(pyproject, theme=self.theme, license_text=_read_license(root))
        index = Index(
            name=pyproject.name,
            tutorials=_select_diataxis_entry(doc_root, "tutorial"),
            how_to_guides=_select_diataxis_entry(doc_root, "how-to-guide"),
            user_guides=_select_diataxis_entry(doc_root, "user-guide"),
            explanations=_select_diataxis_entry(doc_root, "explanation"),
            concepts=_select_diataxis_entry(doc_root, "concept"),
            api_modules=[module.name for module in public_modules],
        )

        files: dict[Path, DocFile] = {
            doc_root / "conf.py": DocFile(conf.render()),
            doc_root / "index.rst": DocFile(index.render()),
            doc_root / "_readme.md": DocFile(_readme_content(root, pyproject.name)),
            doc_root / "api" / "_index.rst": DocFile(render_modules_index(public_modules)),
        }
        for module in public_modules:
            files[doc_root / "api" / f"{module.name}.rst"] = DocFile(module.render())

        docs_rel = doc_root.relative_to(root).as_posix()
        files[doc_root / "requirements.txt"] = DocFile(
            f"doc-zero>={module_version('doc-zero')}", policy=WritePolicy.IF_MISSING
        )
        files[root / ".readthedocs.yml"] = DocFile(
            READTHEDOCS_TEMPLATE.format(docs=docs_rel), policy=WritePolicy.IF_MISSING
        )

        return DocTree(
            files=files,
            dirs=[doc_root / "_static"],
            owned_dirs=[doc_root / "api"],
        )

    def build(self) -> None:
        """
        Build the documentation using sphinx.
        """
        from sphinx.cmd.build import main

        self.init()
        main([str(self.doc_root), str(self.root / "dist" / "docs")])

    def serve(self) -> None:
        """
        Start the live server.
        """
        from sphinx_autobuild.__main__ import main

        self.init()
        main([str(self.doc_root), str(self.root / "dist" / "docs")])

    def test(self) -> None:
        """
        Execute all doctests.
        """


@dataclass
class Index:
    """
    Content of the index.rst file.
    """

    name: str

    # It uses the framework described at https://diataxis.fr
    tutorials: Path | None = None
    how_to_guides: Path | None = None
    explanations: Path | None = None
    user_guides: Path | None = None

    # Reference is concepts + api documentation
    concepts: Path | None = None
    api_modules: list[str] = field(default_factory=list)

    def render(self) -> str:
        """
        Render the index.rst file.
        """
        return "\n".join(self._iter_lines())

    def _iter_lines(self) -> Iterator[str]:
        yield f"Welcome to the {self.name} documentation!"
        yield "=" * (len(self.name) + 30)
        yield from [
            ".. mdinclude:: _readme.md",
            "",
            "",
            "Table of contents",
            "-----------------",
            "",
            ".. toctree::",
            "   :maxdepth: 3",
            "",
        ]

        if self.tutorials:
            yield f"   {self.tutorials.stem}"
        if self.how_to_guides:
            yield f"   {self.how_to_guides.stem}"
        if self.user_guides:
            yield f"   {self.user_guides.stem}"
        if self.explanations:
            yield f"   {self.explanations.stem}"
        if self.concepts:
            yield f"   {self.concepts.stem}"
        if self.api_modules:
            yield "   api/_index"


@dataclass
class Conf:
    """
    Information to build the conf.py file.
    """

    project: str | None = None
    author: str | None = None
    email: str | None = None
    year: int | None = None
    extensions: list[str] = field(default_factory=DEFAULT_EXTENSIONS.copy)
    theme: str = "default"

    @staticmethod
    def from_pyproject(
        pyproject: PyProject,
        /,
        *,
        theme: str,
        license_text: str | None = None,
    ) -> Conf:
        """
        Create a Conf object from a PyProject object and (optionally) the
        text of the project's LICENSE file.

        The first pyproject author's name/email are used, if any. The year
        and, absent a pyproject author, the author name are taken from the
        LICENSE's copyright notice, if one can be found. A LICENSE without a
        recognizable copyright notice is not an error: the year is simply
        omitted and the author falls back to "unknown author" at render
        time.
        """
        project = pyproject.name
        author: str | None = None
        email: str | None = None
        year: int | None = None

        # Extract author information from the pyproject.toml file
        try:
            author_data = pyproject.authors[0]
            author = author_data["name"]
            email = author_data.get("email")
        except (TypeError, IndexError):  # empty authors list or invalid data
            pass

        # Read the year (and, absent a pyproject author, the author) from
        # the Copyright notice in the LICENSE file.
        if license_text is not None:
            try:
                copyright = find_copyright(license_text)
                year = int(copyright["year"])
                if author is None:
                    author = copyright["author"]
            except ValueError:
                pass

        return Conf(
            project=project,
            author=author,
            email=email,
            year=year,
            theme=theme,
        )

    def render(self) -> str:
        return "\n".join(self._iter_lines())

    def _iter_lines(self) -> Iterator[str]:
        copyright = f"{self.year}, " if self.year else ""
        copyright += self.author or "unknown author"
        author = self.author or "unknown author"
        if self.email:
            author += f" <{self.email}>"

        yield f"project = {self.project or 'unnamed project'!r}"
        yield f"copyright = {copyright!r}"
        yield f"author = {author!r}"
        yield f"extensions = {self.extensions!r}"
        yield "templates_path = ['_templates']"
        yield f"html_theme = {self.theme!r}"
        yield "html_static_path = ['_static']"
        yield "exclude_patterns = ['_readme.md', 'requirements.txt']"


class Copyright(TypedDict):
    year: int
    author: str | None


def find_copyright(src: str) -> Copyright:
    """
    Find the copyright notice in the given source code.
    """
    match = COPYRIGHT_RE.search(src)
    if not match:
        raise ValueError("Copyright notice not found")
    return {
        "year": int(match.group("year")),
        "author": match.group("author"),
    }


def render_modules_index(modules: Iterable[Module]) -> str:
    """
    Render the index.rst file for the API documentation.
    """
    lines = [
        "Modules",
        "=======",
        "",
        ".. toctree::",
        "   :maxdepth: 2",
        "   :caption: Contents:",
        "",
    ]
    for module in modules:
        lines.append(f"   {module.name}")
    return "\n".join(lines)


def _select_diataxis_entry(doc_root: Path, name: str, plural: str | None = None) -> Path | None:
    """
    Select the first existing diataxis entry for ``name`` under
    ``doc_root``: the plural directory, then ``<name>.rst``, then
    ``<name>.md``.
    """
    plural = plural or f"{name}s"
    return first_existing(
        [
            doc_root / plural,
            doc_root / f"{name}.rst",
            doc_root / f"{name}.md",
        ]
    )


def _read_license(root: Path) -> str | None:
    """
    Return the text of ``<root>/LICENSE``, or None if it doesn't exist.
    """
    license_path = root / "LICENSE"
    if license_path.exists():
        return license_path.read_text()
    return None


def _readme_content(root: Path, project_name: str) -> str:
    """
    Compute the content of ``_readme.md`` from ``<root>/README.md``.

    If the README is missing, a placeholder mentioning the project name is
    used. Otherwise, see ``readme_body`` for what is kept.
    """
    readme_path = root / "README.md"
    if not readme_path.exists():
        return README_PLACEHOLDER.format(name=project_name)
    return readme_body(readme_path.read_text())
