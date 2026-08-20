from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from importlib.metadata import version as module_version
from logging import getLogger
from pathlib import Path
from typing import Any, Iterable, Iterator, TypedDict

from .module import Module
from .pyproject import PyProject
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
SPHINX_THEME_ALIASES = {
    "rtd": "sphinx_rtd_theme",
    "readthedocs": "sphinx_rtd_theme",
    "default": "alabaster",
}
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

# Build documentation in the "docs/" directory with Sphinx
sphinx:
  configuration: docs/conf.py

# Optionally, but recommended,
# declare the Python requirements required to build your documentation
# See https://docs.readthedocs.io/en/stable/guides/reproducible-builds.html
python:
  install:
    - requirements: docs/requirements.txt
"""

log = getLogger(__name__)


@dataclass
class Doc0:
    """
    The root type representing the documentation of your project.
    """

    #: The pyproject.toml file for the project.
    pyproject: PyProject

    #: Base location for the documentation assets
    doc_root: Path

    #: The theme to use for the documentation.
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
        """
        root = root or Path.cwd()
        pyproject = PyProject(root=root)

        if theme is None:
            theme = pyproject.get("tool.doc0.theme", default="default", type=str)

        return Doc0(
            doc_root=root / docs,
            pyproject=pyproject,
            theme=theme,
        )

    @property
    def root(self) -> Path:
        """
        The root of the project.
        """
        return self.pyproject.root

    def init(self) -> None:
        """
        Assure that the documentation is initialized.

        Call .generate() if the documentation is not initialized.
        """
        self.doc_root.mkdir(parents=True, exist_ok=True)
        (self.doc_root / "_static").mkdir(exist_ok=True)

        # Write/overwrite docs/conf.py.
        conf_path = self.doc_root / "conf.py"
        conf = Conf.from_pyproject(self.pyproject, theme=self.theme)
        conf_path.write_text(conf.render())

        # Write docs/index.rst and docs/api/*
        self.write_rst_files()
        self.write_readme_md()

        # Write the Read the Docs configuration file, if it doesn't exist.
        rtd_path = self.root / ".readthedocs.yml"
        if not rtd_path.exists():
            rtd_path.write_text(READTHEDOCS_TEMPLATE)

        # Write the requirements.txt file for Read the Docs, if it doesn't exist.
        req_path = self.root / "docs" / "requirements.txt"
        if not req_path.exists():
            req_path.write_text(f"doc0>={module_version('doc0')}")

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

    #
    # Write parts of the documentation
    #
    def write_rst_files(self) -> None:
        """
        Write the index, API docs and process the User guide.
        """
        self.doc_root.mkdir(parents=True, exist_ok=True)
        roots = list(self.pyproject.find_root_modules())
        public_modules = [root.load_module() for root in roots]

        for root in roots:
            for sub_module in root.iter_submodules(skip_private=True):
                mod = sub_module.load_module()
                docstring = mod.docstring
                if docstring is None:
                    continue

                if mod.exports is None:
                    msg = "Module %s has no __all__ attribute" % sub_module.name
                    log.warning(msg)
                elif not mod.exports:
                    msg = "Module %s do not export any symbols" % sub_module.name
                    log.warning(msg)

                public_modules.append(mod)

        index = Index.load(self.pyproject.name, self.doc_root, public_modules)
        index_path = self.doc_root / "index.rst"
        index_path.write_text(index.render())

        # Clean the docs/api directory
        api_dir = self.doc_root / "api"
        if api_dir.exists():
            shutil.rmtree(api_dir)
        api_dir.mkdir(parents=True, exist_ok=True)

        # Create the API documentation for each public module and the index.rst file.
        for module in public_modules:
            module_path = self.doc_root / "api" / f"{module.name}.rst"
            module_path.write_text(module.render())
        (self.doc_root / "api" / "_index.rst").write_text(
            render_modules_index(public_modules)
        )

    def write_readme_md(self) -> None:
        """
        Write the README.md file for the documentation.
        """
        readme_path = self.root / "README.md"
        if not readme_path.exists():
            src = f"This is the documentation for {self.pyproject.name}. Please include a README.md file in the documentation root directory."
            readme_path.write_text(src)
            return

        src = readme_path.read_text()
        parts = re.split(r"<!--\s*doc0-start\s*-->", src, maxsplit=1)
        if len(parts) == 1:
            src = remove_md_title(src)
        else:
            src = parts[1]

        (self.doc_root / "_readme.md").write_text(src)


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

    # Reference is concepts + api documentation
    concepts: Path | None = None
    api_modules: list[str] = field(default_factory=list)

    @staticmethod
    def load(name: str, root: Path, modules: Iterable[Module]):
        """
        Load the index.rst configuration from the given root path and modules.

        It will search the root path for the tutorials, how-to guides and
        explanations directories in order to fill-in the appropriate fields.
        """

        module_names = [mod.name for mod in modules]

        def select(name: str, plural: str | None = None) -> Path | None:
            """
            Select the first existing path for the given name.
            """
            plural = plural or name + "s"
            return first_existing(
                [
                    root / plural,
                    root / f"{name}.rst",
                    root / f"{name}.md",
                ]
            )

        tutorials = select("tutorial")
        how_to_guides = select("how-to-guide")
        explanations = select("explanation")
        concepts = select("concept")

        return Index(
            name=name,
            tutorials=tutorials,
            how_to_guides=how_to_guides,
            explanations=explanations,
            concepts=concepts,
            api_modules=module_names,
        )

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
    extra_options: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_pyproject(
        pyproject: PyProject,
        /,
        *,
        theme: str,
        author: str | None = None,
        email: str | None = None,
        year: int | None = None,
        extensions: Iterable[str] = DEFAULT_EXTENSIONS,
        root: Path | None = None,
    ) -> Conf:
        """
        Create Conf object from a PyProject object.
        """
        project = pyproject.name
        extensions = list(extensions or [])
        root = root or pyproject.root

        # Extract author information from the pyproject.toml file
        try:
            author_data = pyproject.authors[0]
            author = author or author_data["name"]
            if not email:
                email = author_data.get("email")
        except (TypeError, IndexError):  # empty authors list or invalid data
            pass

        # Read the year from the Copyright notice in the LICENSE file.
        if (licence_file := Path(root / "LICENSE")).exists():
            copyright = find_copyright(licence_file.read_text())
            if year is None:
                try:
                    year = int(copyright["year"])
                except ValueError:
                    pass
            if author is None:
                author = copyright["author"]

        return Conf(
            project=project,
            author=author,
            email=email,
            year=year,
            extensions=extensions,
            theme=theme,
        )

    def render(self) -> str:
        return "\n".join(self._iter_lines())

    def _iter_lines(self) -> Iterator[str]:
        theme = SPHINX_THEME_ALIASES.get(self.theme, self.theme)
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
        yield f"html_theme = {theme!r}"
        yield "html_static_path = ['_static']"
        yield "exclude_patterns = ['_readme.md', 'requirements.txt']"
        for key, value in sorted(self.extra_options.items()):
            yield f"{key} = {value!r}"


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


def remove_md_title(src: str) -> str:
    """
    Remove the title from the given markdown source code.
    """
    lines = src.splitlines()
    if not lines:
        return src

    # Remove the first line if it is a title
    if lines[0].startswith("#"):
        lines.pop(0)
        # Remove the second line if it is a title underline
        if lines and re.match(r"^=+$", lines[0]):
            lines.pop(0)

    return "\n".join(lines).lstrip("\n")
