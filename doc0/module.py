from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from types import ModuleType
from typing import Iterable, Iterator

from .exports import Section, parse_export_sections, parse_reexport_sections

log = getLogger(__name__)


@dataclass(frozen=True)
class ModuleSpec:
    #: The Python module name
    name: str

    #: The path to the module source file. Packages point to a folder, modules to a file.
    path: Path

    @property
    def is_package(self) -> bool:
        """
        Return True if the module is a package.
        """
        return self.path.is_dir()

    @property
    def source_path(self) -> Path:
        """
        Return the path to the source file for the module.
        """
        if self.is_package:
            return self.path / "__init__.py"
        return self.path

    def __post_init__(self) -> None:
        if not self.path.exists():
            raise ValueError(f"Module path {self.path} does not exist.")

        if self.path.name == "__init__.py":
            super().__setattr__("path", self.path.parent)

        elif not self.path.is_dir() and self.path.suffix != ".py":
            raise ValueError(f"Module path {self.path} is not a Python file.")

    def load_module(self) -> Module:
        """
        Load the module from the spec.

        The module is imported normally, by name, with the directory that
        holds its top-level package put first on ``sys.path``. That way it
        is registered in ``sys.modules`` like any other import, so relative
        imports, dataclasses and anything else that looks a module up by
        name work, and Sphinx's autodoc later sees the same module objects.
        A module already in ``sys.modules`` is reused as is.
        """
        import importlib

        if self.name not in sys.modules:
            import_root = str(self.path.parents[self.name.count(".")])
            if import_root not in sys.path:
                sys.path.insert(0, import_root)
            importlib.invalidate_caches()

        module = importlib.import_module(self.name)
        return Module(source_path=self.source_path, name=self.name, module=module)

    def iter_submodules(self, skip_private: bool = False) -> Iterator[ModuleSpec]:
        """
        Iterate over all sub-modules under this package, depth-first, in
        deterministic order (directory entries sorted by name -- not
        ``Path.iterdir()`` order).

        A package directory yields itself, then its contents, before the
        walk moves on to its next sibling. A directory without
        ``__init__.py`` is a namespace package: it is not yielded itself,
        but is still recursed into. Only ``.py`` files are yielded.

        ``__init__.py`` is never yielded as a pseudo-submodule of its own
        package. Entries whose module name segment is not a valid Python
        identifier (e.g. ``static-files/``, ``my-script.py``) are skipped
        and, for directories, not recursed into -- they can't be imported
        by that dotted name. When ``skip_private`` is set, ``_``-prefixed
        files and directories are skipped the same way.
        """
        if not self.is_package:
            return

        for path in sorted(self.path.iterdir(), key=lambda p: p.name):
            if path.name == "__init__.py":
                continue

            stem = path.stem if path.suffix == ".py" else path.name
            if not stem.isidentifier():
                continue

            if skip_private and stem.startswith("_"):
                continue

            if path.is_dir():
                spec = ModuleSpec(name=f"{self.name}.{path.name}", path=path)
                if (path / "__init__.py").exists():
                    yield spec
                yield from spec.iter_submodules(skip_private=skip_private)

            elif path.suffix == ".py":
                yield ModuleSpec(name=f"{self.name}.{path.stem}", path=path)


@dataclass
class Module:
    """
    A Python module with its source and objects.
    """

    #: Path to the source file
    source_path: Path

    #: Python name for the module.
    name: str

    #: Loaded python module
    module: ModuleType

    @property
    def docstring(self) -> str | None:
        """
        Return the module docstring.
        """
        return self.module.__doc__

    @property
    def exports(self) -> list[str] | None:
        """
        Return the list of exported symbols from the module.
        """
        exports = getattr(self.module, "__all__", None)
        if exports is None:
            return None
        return list(exports)

    def render(self) -> str:
        """
        Render the module documentation as reStructuredText.

        If ``__all__`` can be statically parsed into ordered, ``#:``-delimited
        sections (see ``doc0.exports``), members are listed explicitly, in
        declaration order, grouped under their sections. Otherwise, falls
        back to a single ``automodule`` block listing all members in
        whatever order Sphinx's autodoc picks.
        """
        return "\n".join(self._iter_lines())

    def _iter_lines(self) -> Iterator[str]:
        yield self.name
        yield "=" * len(self.name)
        yield ""

        sections = parse_export_sections(self.source_path, self.module)
        if sections is None:
            sections = parse_reexport_sections(self.source_path, self.module)
        if sections is None:
            yield f".. automodule:: {self.name}"
            yield "   :members:"
            return

        yield f".. automodule:: {self.name}"
        yield ""

        for section in sections:
            yield from self._iter_section_lines(section)

    def _iter_section_lines(self, section: Section) -> Iterator[str]:
        if section.title:
            yield section.title
            yield "-" * len(section.title)
            yield ""

        for line in section.body:
            yield line
        if section.body:
            yield ""

        for name in section.names:
            yield from self._iter_member_lines(name)
            yield ""

    def _iter_member_lines(self, name: str) -> Iterator[str]:
        qualname = f"{self.name}.{name}"
        obj = getattr(self.module, name, None)

        if inspect.isclass(obj):
            yield f".. autoclass:: {qualname}"
            yield "   :members:"
            yield "   :member-order: bysource"
        elif inspect.isroutine(obj):
            yield f".. autofunction:: {qualname}"
        else:
            yield f".. autodata:: {qualname}"


def find_public_modules(roots: Iterable[ModuleSpec]) -> list[Module]:
    """
    Load and return the public modules of a project, in documentation
    order: every root module, in the given order (always included,
    regardless of docstring, never warned about), followed by each root's
    public submodules -- in the given root order, then in
    ``iter_submodules(skip_private=True)`` order.

    A submodule with no docstring is skipped (logged at DEBUG). Submodules
    with no, or an empty, ``__all__`` are still included, but logged at
    WARNING.

    Import errors propagate with their original type, with a note
    attached naming the dotted module name and its source path.
    """
    roots = list(roots)
    public_modules = [_load_module(root) for root in roots]

    for root in roots:
        for sub_module in root.iter_submodules(skip_private=True):
            mod = _load_module(sub_module)
            if mod.docstring is None:
                log.debug("Skipping module %s: no docstring", sub_module.name)
                continue

            if mod.exports is None:
                if parse_reexport_sections(mod.source_path, mod.module) is None:
                    log.warning("Module %s has no __all__ attribute", sub_module.name)
            elif not mod.exports:
                log.warning("Module %s do not export any symbols", sub_module.name)

            public_modules.append(mod)

    return public_modules


def _load_module(spec: ModuleSpec) -> Module:
    """
    Load ``spec``, attaching a note identifying the dotted module name and
    its source path to any exception raised during import, then
    re-raising it unchanged.
    """
    try:
        return spec.load_module()
    except Exception as exc:
        exc.add_note(f"doc0: while importing module {spec.name!r} from {spec.source_path}")
        raise
