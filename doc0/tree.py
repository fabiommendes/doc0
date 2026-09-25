"""
The generated documentation tree as data, and the writer that puts it on disk.

Internal module: not re-exported from ``doc0``.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class WritePolicy(StrEnum):
    """
    What to do when a generated file already exists on disk.
    """

    #: doc0 owns the file: always replace it.
    OVERWRITE = "overwrite"

    #: The user owns the file once it exists: write it only if missing.
    IF_MISSING = "if-missing"


@dataclass(frozen=True)
class DocFile:
    """
    One generated file: its content and its write policy.
    """

    content: str
    policy: WritePolicy = WritePolicy.OVERWRITE


@dataclass
class DocTree:
    """
    Everything ``doc0`` wants on disk, as data. All paths are absolute.
    """

    #: Files to write, by absolute path.
    files: dict[Path, DocFile] = field(default_factory=dict)

    #: Directories that must exist, even if empty (e.g. ``docs/_static``).
    dirs: list[Path] = field(default_factory=list)

    #: Directories wholly owned by doc0: emptied before writing, so files
    #: that are no longer generated (e.g. pages of deleted modules) vanish.
    owned_dirs: list[Path] = field(default_factory=list)

    def write(self) -> None:
        """
        Write the tree to disk.

        Owned directories are removed (if present) and recreated first, so
        stale generated files (e.g. the API page of a removed module)
        vanish. Every directory in ``dirs`` is then created. Finally, every
        file is written: ``OVERWRITE`` files are always (re)written,
        ``IF_MISSING`` files only when they don't already exist.
        """
        for owned_dir in self.owned_dirs:
            if owned_dir.exists():
                shutil.rmtree(owned_dir)
            owned_dir.mkdir(parents=True, exist_ok=True)

        for directory in self.dirs:
            directory.mkdir(parents=True, exist_ok=True)

        for path, doc_file in self.files.items():
            if doc_file.policy is WritePolicy.IF_MISSING and path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(doc_file.content)
