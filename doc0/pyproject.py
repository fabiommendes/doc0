from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path
from typing import Any, Iterable, NotRequired, TypedDict, overload
from warnings import warn

from .module import ModuleSpec

log = getLogger(__name__)
type TomlValue = str | int | float | bool | None | list[Any] | dict[str, Any]


@dataclass
class PyProject:
    """
    A Python project with its source and documentation.
    """

    #: Path to the root of the project
    root: Path

    #: Raw data from the pyproject.toml file
    data: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        Load the pyproject.toml file if it exists.
        """
        pyproject_path = self.root / "pyproject.toml"
        if pyproject_path.exists():
            with pyproject_path.open("rb") as f:
                self.data = tomllib.load(f)
        else:
            warn("pyproject.toml not found")

    @property
    def project(self) -> dict[str, TomlValue]:
        return self.data.get("project", {})

    @property
    def name(self) -> str:
        return self.get("project.name", type=str)

    @property
    def version(self) -> str:
        return self.get("project.version", type=str)

    @property
    def description(self) -> str:
        return self.get("project.description", type=str)

    @property
    def authors(self) -> list[Author]:
        data = self.get("project.authors", type=list)
        return [Author(**item) for item in data]

    def __getitem__(self, key: str) -> TomlValue:
        data = self.data
        for part in key.split("."):
            try:
                data = data[part]
            except KeyError:
                raise KeyError(key)
        return data

    @overload
    def get[T](self, key: str, /, *, default: T | None = None, type: type[T]) -> T: ...

    @overload
    def get(self, key: str, /, default: TomlValue = None) -> TomlValue: ...

    def get(self, key: str, /, default: Any = None, *, type: Any = None) -> Any:
        """
        Get configuration key and possibly assert it has the given type.

        Args:
            key: The key to get, using dot notation for nested keys.
            default: The default value to return if the key is not found.
            type: The type to assert the value has. If None, no assertion is made.
        """
        try:
            value = self[key]
        except KeyError:
            value = default
        if type is not None and value is not None and not isinstance(value, type):
            msg = f"Expected {key} to be of type {type.__name__}, got {type(value).__name__}"
            raise TypeError(msg)
        return value

    def find_root_modules(self) -> Iterable[ModuleSpec]:
        """
        Find all root modules in the project.

        Returns:
            An iterable of root module specifications.
        """
        # We try various heuristics to find the root modules of the project.
        # The first is to look for explicit configuration in the pyproject.toml
        # file.
        if self._is_uv_build_system():
            log.info("uv build system detected")
            yield from self._find_uv_root_modules()
        elif self._is_src_layout():
            yield from self._find_src_root_modules()
        elif self._is_toplevel_package_layout():
            log.info("toplevel package layout detected")
            yield from self._find_toplevel_package_root_modules()
        else:
            raise RuntimeError("Could not determine the layout of the project")

    def _is_uv_build_system(self) -> bool:
        build_system: dict[str, str] = self.data.get("build-system", {})
        return build_system.get("build-backend") == "uv_build"

    def _is_src_layout(self) -> bool:
        # Check if there is a src directory with a package inside it.
        src_dir = self.root / "src"
        if not src_dir.is_dir():
            return False
        for item in src_dir.iterdir():
            if item.is_dir() and (item / "__init__.py").exists():
                return True
        return False

    def _is_toplevel_package_layout(self) -> bool:
        package_dir = self.root / self.name
        return package_dir.is_dir() and (package_dir / "__init__.py").exists()

    def _find_uv_root_modules(self) -> Iterable[ModuleSpec]:
        uv_conf = self.get("tool.uv.build-backend", type=dict)
        root = self.root / uv_conf.get("module-root", "")
        name = uv_conf.get("module-name")
        if name is None:
            return
        if isinstance(name, str) and "," in name:
            name = [part.strip() for part in name.split(",")]

        if isinstance(name, list):
            yield from (ModuleSpec(name=part, path=root / part) for part in name)
        elif isinstance(name, str):
            yield ModuleSpec(name=name, path=root / name)
        else:
            msg = f"Invalid option: tool.uv.build-backend.module-name={name!r}"
            raise ValueError(msg)

    def _find_src_root_modules(self) -> Iterable[ModuleSpec]:
        src_dir = self.root / "src"
        for item in src_dir.iterdir():
            if item.is_dir() and (item / "__init__.py").exists():
                yield ModuleSpec(name=item.name, path=item)
            elif item.suffix == ".py":
                yield ModuleSpec(name=item.stem, path=item)

    def _find_toplevel_package_root_modules(self) -> Iterable[ModuleSpec]:
        package_dir = self.root / self.name
        yield ModuleSpec(name=self.name, path=package_dir)


#
# Auxiliary types
#
class Author(TypedDict):
    name: str
    email: NotRequired[str]
