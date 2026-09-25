"""
Scenario tests for doc0's console-script public API: the doc0 CLI
(installed via ``[project.scripts] doc0 = "doc0.cli:main"``).

Doc0's own build()/serve()/test() behavior is already covered end-to-end in
test_base.py. Here we drive the CLI boundary itself with Typer's CliRunner
and patch Doc0's methods to confirm the commands parse arguments correctly
and wire up to the right calls -- this is what the CLI, as a distinct
public entry point, is responsible for.
"""

from __future__ import annotations

import re

import pytest
from conftest import make_module_file, make_pyproject_toml
from typer.testing import CliRunner

from doc0 import Doc0
from doc0.cli import app

runner = CliRunner()


@pytest.fixture
def project(tmp_path, monkeypatch):
    make_pyproject_toml(tmp_path, name="acme", build_backend=None)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def record_calls(monkeypatch):
    calls: list[tuple[str, tuple]] = []
    for method in ("build", "serve", "test"):

        def make_fake(name):
            def fake(self, *a, **kw):
                calls.append((name, a))

            return fake

        monkeypatch.setattr(Doc0, method, make_fake(method))
    return calls


def test_build_command_invokes_doc0_build(project, record_calls):
    result = runner.invoke(app, ["build"])

    assert result.exit_code == 0
    assert record_calls == [("build", ())]


def test_build_command_accepts_theme_option(project, record_calls, monkeypatch):
    themes = []
    monkeypatch.setattr(Doc0, "build", lambda self: themes.append(self.theme))

    result = runner.invoke(app, ["build", "--theme", "sphinx_rtd_theme"])

    assert result.exit_code == 0
    assert themes == ["sphinx_rtd_theme"]


def test_build_command_rejects_invalid_theme(project, record_calls):
    result = runner.invoke(app, ["build", "--theme", "bad theme"])

    assert result.exit_code != 0
    assert not record_calls


def test_serve_command_invokes_doc0_serve(project, record_calls):
    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0
    assert record_calls == [("serve", ())]


def test_serve_command_accepts_theme_option(project, record_calls, monkeypatch):
    themes = []
    monkeypatch.setattr(Doc0, "serve", lambda self: themes.append(self.theme))

    result = runner.invoke(app, ["serve", "--theme", "sphinx_rtd_theme"])

    assert result.exit_code == 0
    assert themes == ["sphinx_rtd_theme"]


def test_test_command_invokes_doc0_test(project, record_calls):
    result = runner.invoke(app, ["test"])

    assert result.exit_code == 0
    assert record_calls == [("test", ())]


def test_no_args_shows_help_and_does_not_run_any_command(project, record_calls):
    result = runner.invoke(app, [])

    assert not record_calls
    assert "doc0" in result.output or result.exit_code == 0


def test_main_entry_point_runs_the_app(project, record_calls, monkeypatch):
    """``doc0.cli.main`` is the console-script entry point installed as
    ``doc0``; it should simply invoke the Typer app."""
    import sys

    from doc0.cli import main

    monkeypatch.setattr(sys, "argv", ["doc0", "build"])

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code in (0, None)
    assert record_calls == [("build", ())]


# ---------------------------------------------------------------------------
# --theme end to end: CLI flag + pyproject -> conf.py, via a real build/serve
# (Sphinx itself stubbed by fake_sphinx)
# ---------------------------------------------------------------------------


def themed_project(root, pyproject_theme):
    extra = ""
    if pyproject_theme is not None:
        extra = f'\n[tool.doc-zero]\ntheme = "{pyproject_theme}"\n'
    make_pyproject_toml(
        root, name="acme", build_backend="uv_build", module_name="acme", extra_toml=extra
    )
    make_module_file(root / "acme.py", docstring="Acme.", all_=[])


@pytest.mark.parametrize("command", ["build", "serve"])
@pytest.mark.parametrize(
    ("flag", "pyproject_theme", "expected"),
    [
        pytest.param(None, None, "alabaster", id="default"),
        pytest.param(None, "rtd", "sphinx_rtd_theme", id="pyproject-alias"),
        pytest.param("furo", "rtd", "furo", id="flag-wins"),
        pytest.param("readthedocs", None, "sphinx_rtd_theme", id="flag-alias"),
    ],
)
def test_theme_reaches_conf_py(
    tmp_path, monkeypatch, fake_sphinx, command, flag, pyproject_theme, expected
):
    themed_project(tmp_path, pyproject_theme)
    monkeypatch.chdir(tmp_path)
    args = [command] + ([] if flag is None else ["--theme", flag])

    result = runner.invoke(app, args)

    assert result.exit_code == 0, result.output
    conf = (tmp_path / "docs" / "conf.py").read_text()
    assert f"html_theme = {expected!r}" in conf
    assert len(fake_sphinx[command].calls) == 1


@pytest.mark.parametrize("command", ["build", "serve"])
@pytest.mark.parametrize(
    ("flag", "pyproject_theme", "source"),
    [
        pytest.param("bad theme", None, "--theme", id="invalid-flag"),
        pytest.param(None, "bad theme", "tool.doc-zero", id="invalid-pyproject"),
    ],
)
def test_invalid_theme_is_a_clean_usage_error_naming_its_source(
    tmp_path, monkeypatch, fake_sphinx, command, flag, pyproject_theme, source
):
    themed_project(tmp_path, pyproject_theme)
    monkeypatch.chdir(tmp_path)
    args = [command] + ([] if flag is None else ["--theme", flag])

    result = runner.invoke(app, args)

    assert result.exit_code == 2
    assert isinstance(result.exception, SystemExit)  # no traceback
    # Typer forces rich styling under GITHUB_ACTIONS, which splits "--theme".
    output = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "'bad theme'" in output
    assert source in output
    assert not fake_sphinx[command].calls
    assert not (tmp_path / "docs").exists()
