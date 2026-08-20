from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Iterator

from .exports import Section, parse_export_sections


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

        This executes the module code, if not already loaded.
        """
        import importlib.util

        if self.name in sys.modules:
            module = sys.modules[self.name]
        else:
            if self.is_package:
                submodule_search_locations = [str(self.path)]
            else:
                submodule_search_locations = None
            spec = importlib.util.spec_from_file_location(
                name=self.name,
                location=self.source_path,
                submodule_search_locations=submodule_search_locations,
            )
            if spec is None:
                raise ImportError(f"Cannot load module {self.name} from {self.path}")
            module = importlib.util.module_from_spec(spec)
            if spec.loader is None:
                raise ImportError(f"Cannot load module {self.name} from {self.path}")
            spec.loader.exec_module(module)

        return Module(source_path=self.source_path, name=self.name, module=module)

    def iter_submodules(self, skip_private: bool = False) -> Iterator[ModuleSpec]:
        """
        Iterate over all sub-modules in the project.
        """
        if self.is_package:
            for path in self.path.iterdir():
                if skip_private and path.name.startswith("_"):
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
