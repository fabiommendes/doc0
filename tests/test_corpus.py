"""
Always-green corpus: real Sphinx builds of the projects in tests/corpus.

See tests/corpus/corpus.toml for the format and what "green" means. Local
projects build in-process on every test run; external projects are cloned
and built in their own virtualenv, and only run with ``pytest -m slow``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from doc0 import Doc0

CORPUS = Path(__file__).parent / "corpus"
MANIFEST = tomllib.loads((CORPUS / "corpus.toml").read_text())
DOC0_ROOT = Path(__file__).parent.parent


def check_pages(build_dir: Path, pages: dict[str, list[str]], *, exact: bool) -> None:
    """
    Check that each page exists and documents its objects. With ``exact``,
    the API pages must be exactly the listed ones.
    """
    assert (build_dir / "index.html").is_file()
    for page, objects in pages.items():
        path = build_dir / page
        assert path.is_file(), f"missing page {page}"
        html = path.read_text()
        missing = [obj for obj in objects if f'id="{obj}"' not in html]
        assert not missing, f"{page} does not document {missing}"

    if exact:
        built = {
            path.relative_to(build_dir).as_posix()
            for path in (build_dir / "api").glob("*.html")
            if path.name != "_index.html"
        }
        assert built == set(pages)


@pytest.mark.parametrize("name", sorted(MANIFEST["local"]))
def test_local_corpus_project_is_green(tmp_path: Path, name: str):
    project = tmp_path / name
    shutil.copytree(CORPUS / name, project)

    assert Doc0.load(project).build() == 0

    check_pages(project / "dist" / "docs", MANIFEST["local"][name]["pages"], exact=True)


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(MANIFEST.get("external", {})))
def test_external_corpus_project_is_green(tmp_path: Path, name: str):
    entry = MANIFEST["external"][name]
    checkout, venv = tmp_path / name, tmp_path / "venv"
    run(["git", "clone", "-q", "--depth", "1", "--branch", entry["ref"], entry["git"], checkout])
    project = checkout / entry.get("subdir", "")
    run(["uv", "venv", "-q", "--python", sys.executable, venv])
    run(["uv", "pip", "install", "-q", "--python", venv / "bin" / "python",
         project, DOC0_ROOT, *entry.get("install", [])])

    result = run([venv / "bin" / "doc0", "build"], cwd=project, check=False)

    assert result.returncode == 0, result.stdout[-3000:]
    check_pages(project / "dist" / "docs", entry["pages"], exact=False)


def run(
    args: list[str | Path], *, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**_clean_env(), "NO_COLOR": "1"},
        timeout=900,
    )
    if check and result.returncode:
        pytest.fail(f"{args[0]} failed:\n{result.stdout}\n{result.stderr}"[-3000:])
    result.stdout += result.stderr
    return result


def _clean_env() -> dict[str, str]:
    # Don't let the test runner's virtualenv leak into the project's.
    return {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
