"""
Scenario tests for doc0.util's public API: ``validate_theme``.
"""

from __future__ import annotations

import pytest

from doc0.util import validate_theme


@pytest.mark.parametrize(
    "theme",
    ["alabaster", "sphinx_rtd_theme", "sphinx_book_theme", "a", "a_b_c123"],
)
def test_validate_theme_accepts_valid_identifiers(theme):
    assert validate_theme(theme) == theme


def test_validate_theme_accepts_dotted_theme_names():
    assert validate_theme("sphinx_material.theme") == "sphinx_material.theme"


@pytest.mark.parametrize(
    "theme",
    ["bad theme", "1starts-with-digit", "has-a-dash", "", "trailing.", "a..b"],
)
def test_validate_theme_rejects_invalid_names(theme):
    with pytest.raises(ValueError, match="is not a valid Sphinx theme"):
        validate_theme(theme)
