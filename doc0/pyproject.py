from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path
from typing import Any, NotRequired, TypedDict, overload
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
            msg = f"Expected {key} to be of type {type.__name__}, got {value.__class__.__name__}"
            raise TypeError(msg)
        return value

    def find_root_modules(self) -> list[ModuleSpec]:
        """
        Find all root modules in the project.

        The shared facts of the project (root, normalized project name, build
        backend, and ``[tool.uv.build-backend]`` config) are derived once,
        then each known layout is tried in order until one applies:

        1. ``uv_build`` -- applies iff ``[build-system].build-backend`` is
           ``"uv_build"``. Root modules come from
           ``[tool.uv.build-backend]``'s ``module-root``/``module-name``
           (defaulting to ``"src"`` and the normalized project name,
           respectively). A module that can't be found on disk is a hard
           error: this layout does not fall through to the others.
        2. ``src`` -- applies iff ``<root>/src`` is a directory containing at
           least one package. Root modules are every package directory and
           every top-level ``*.py`` file directly inside ``src/``.
        3. ``toplevel`` -- applies iff ``<root>/<normalized name>/__init__.py``
           exists.

        Returns:
            The list of root module specifications.

        Raises:
            RuntimeError: If no layout applies, or if the ``uv_build`` layout
                applies but a configured module cannot be found on disk.
            ValueError: If ``[tool.uv.build-backend].module-name`` has an
                invalid type.
        """
        facts = self._project_facts()
        layouts = (
            ("uv_build", self._resolve_uv_build_layout),
            ("src", self._resolve_src_layout),
            ("toplevel", self._resolve_toplevel_layout),
        )
        reasons: list[str] = []
        for layout_name, resolve in layouts:
            try:
                return resolve(facts)
            except _LayoutInapplicable as exc:
                reasons.append(f"  - {layout_name}: {exc}")

        tried = "\n".join(reasons)
        msg = f"Could not determine the layout of the project at {facts.root}. Tried:\n{tried}"
        raise RuntimeError(msg)

    def _project_facts(self) -> _ProjectFacts:
        """
        Derive the facts shared by every layout, once.
        """
        name = self.name
        module_name = normalize_package_name(name) if name else ""
        build_system = self.get("build-system", type=dict, default={})
        build_backend = build_system.get("build-backend")
        uv_build_config = self.get("tool.uv.build-backend", type=dict, default={})
        return _ProjectFacts(
            root=self.root,
            module_name=module_name,
            build_backend=build_backend,
            uv_build_config=uv_build_config,
        )

    def _resolve_uv_build_layout(self, facts: _ProjectFacts) -> list[ModuleSpec]:
        if facts.build_backend != "uv_build":
            raise _LayoutInapplicable(f"build-backend is {facts.build_backend!r}, not 'uv_build'")

        log.info("uv build system detected")
        module_root_value = facts.uv_build_config.get("module-root", "src")
        module_root = module_root_value if isinstance(module_root_value, str) else "src"
        root = facts.root / module_root
        name = facts.uv_build_config.get("module-name", facts.module_name)

        if isinstance(name, str) and "," in name:
            names: list[str] = [part.strip() for part in name.split(",")]
        elif isinstance(name, str):
            names = [name]
        elif isinstance(name, list) and all(isinstance(part, str) for part in name):
            names = name
        else:
            msg = f"Invalid option: tool.uv.build-backend.module-name={name!r}"
            raise ValueError(msg)

        specs = []
        for module_name in names:
            # Dotted names are namespace packages: "foo.bar" -> <root>/foo/bar
            expected = root.joinpath(*module_name.split("."))
            path = _existing_module_path(expected)
            if path is None:
                msg = (
                    f"uv_build: module {module_name!r} not found at {expected} "
                    f"(module-root={module_root!r}, module-name={module_name!r})"
                )
                raise RuntimeError(msg)
            specs.append(ModuleSpec(name=module_name, path=path))
        return specs

    def _resolve_src_layout(self, facts: _ProjectFacts) -> list[ModuleSpec]:
        src_dir = facts.root / "src"
        if not src_dir.is_dir() or not any(
            item.is_dir() and (item / "__init__.py").exists() for item in src_dir.iterdir()
        ):
            raise _LayoutInapplicable(f"no package found in {src_dir}")

        specs = []
        for item in sorted(src_dir.iterdir(), key=lambda p: p.name):
            if item.is_dir() and (item / "__init__.py").exists():
                specs.append(ModuleSpec(name=item.name, path=item))
            elif item.suffix == ".py":
                specs.append(ModuleSpec(name=item.stem, path=item))
        return specs

    def _resolve_toplevel_layout(self, facts: _ProjectFacts) -> list[ModuleSpec]:
        if not facts.module_name:
            raise _LayoutInapplicable("project has no name")

        package_dir = facts.root / facts.module_name
        if not (package_dir / "__init__.py").exists():
            raise _LayoutInapplicable(f"no package at {package_dir}")

        log.info("toplevel package layout detected")
        return [ModuleSpec(name=facts.module_name, path=package_dir)]


#
# Auxiliary types
#
class Author(TypedDict):
    name: str
    email: NotRequired[str]


class _LayoutInapplicable(Exception):
    """
    Raised internally by a layout resolver to signal that the layout does
    not apply to this project. The message is the human-readable reason.
    """


@dataclass(frozen=True)
class _ProjectFacts:
    """
    Facts shared by every layout resolver, derived once from the project.
    """

    #: Path to the root of the project.
    root: Path

    #: Normalized project name (see ``normalize_package_name``), or ``""``
    #: if the project has no name.
    module_name: str

    #: The ``[build-system].build-backend`` value, if any.
    build_backend: str | None

    #: The (possibly empty) ``[tool.uv.build-backend]`` table.
    uv_build_config: dict[str, TomlValue]


def _existing_module_path(path: Path) -> Path | None:
    """
    Return the package directory at ``path`` or, failing that, the
    single-file module ``path.py``; ``None`` if neither exists.
    """
    if path.is_dir():
        return path
    py_file = path.with_name(path.name + ".py")
    return py_file if py_file.is_file() else None


def normalize_package_name(name: str) -> str:
    """
    Normalize a package name to a valid Python identifier, following uv's
    documented normalization rule: lowercase, with "-" and "." replaced by
    "_" (e.g. "My-Pkg.Tools" -> "my_pkg_tools").

    Args:
        name: The package name to normalize.

    Returns:
        The normalized package name.
    """
    return name.lower().replace("-", "_").replace(".", "_")
