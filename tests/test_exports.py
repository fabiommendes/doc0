"""
Scenario tests for the ``__all__``-ordering / ``#:``-section feature.

Driven entirely through ``doc0.Module.render()`` (via ``ModuleSpec``),
which is the public surface this feature actually changes -- the
underlying parser in ``doc0.exports`` is an internal implementation
detail, exercised here only indirectly through realistic module source.
"""

from __future__ import annotations

import textwrap

from conftest import make_module_file

from doc0.module import ModuleSpec

CLASS_AND_FUNCS_BODY = """\
class Foo:
    pass


class Bar:
    pass


def make_foo():
    return Foo()


def make_bar():
    return Bar()
"""


def render(tmp_path, all_source, name="mod", body=CLASS_AND_FUNCS_BODY):
    module_file = make_module_file(
        tmp_path / f"{name}.py", all_source=textwrap.dedent(all_source), body=body
    )
    spec = ModuleSpec(name=name, path=module_file)
    return spec.load_module().render()


# ---------------------------------------------------------------------------
# The motivating example: multiple titled sections, ordering preserved
# ---------------------------------------------------------------------------


def test_titled_sections_preserve_declaration_order_and_group_members(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = [
            #: Types
            "Foo",
            "Bar",
            #: Utility functions
            "make_foo",
            "make_bar",
        ]
        """,
    )

    assert rendered.splitlines() == [
        "mod",
        "===",
        "",
        ".. automodule:: mod",
        "",
        "Types",
        "-----",
        "",
        ".. autoclass:: mod.Foo",
        "   :members:",
        "   :member-order: bysource",
        "",
        ".. autoclass:: mod.Bar",
        "   :members:",
        "   :member-order: bysource",
        "",
        "Utility functions",
        "-----------------",
        "",
        ".. autofunction:: mod.make_foo",
        "",
        ".. autofunction:: mod.make_bar",
    ]


def test_entries_before_first_section_form_unlabeled_leading_group(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = [
            "Foo",
            #: Utility functions
            "make_foo",
        ]
        """,
    )

    # No heading for the leading group -- straight into the directive.
    assert rendered.splitlines() == [
        "mod",
        "===",
        "",
        ".. automodule:: mod",
        "",
        ".. autoclass:: mod.Foo",
        "   :members:",
        "   :member-order: bysource",
        "",
        "Utility functions",
        "-----------------",
        "",
        ".. autofunction:: mod.make_foo",
    ]


# ---------------------------------------------------------------------------
# Section body paragraphs
# ---------------------------------------------------------------------------


def test_section_with_single_paragraph_body(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = [
            #: Types
            #:
            #: Foo and Bar are the core data types.
            "Foo",
        ]
        """,
    )

    assert rendered.splitlines() == [
        "mod",
        "===",
        "",
        ".. automodule:: mod",
        "",
        "Types",
        "-----",
        "",
        "Foo and Bar are the core data types.",
        "",
        ".. autoclass:: mod.Foo",
        "   :members:",
        "   :member-order: bysource",
    ]


def test_section_body_continuation_lines_do_not_need_the_colon_marker(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = [
            #: Types
            #:
            # Foo and Bar are the core data types.
            "Foo",
        ]
        """,
    )

    assert "Foo and Bar are the core data types." in rendered.splitlines()


def test_section_body_supports_multiple_paragraphs(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = [
            #: Types
            #:
            #: First paragraph.
            #:
            #: Second paragraph.
            "Foo",
        ]
        """,
    )

    lines = rendered.splitlines()
    body_start = lines.index("-----") + 1
    body = lines[body_start : body_start + 4]
    assert body == ["", "First paragraph.", "", "Second paragraph."]


def test_title_only_section_has_no_body_paragraph(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = [
            #: Types
            "Foo",
        ]
        """,
    )

    lines = rendered.splitlines()
    heading_index = lines.index("Types")
    # Heading, underline, blank, then straight into the directive -- no
    # stray blank paragraph line in between.
    assert lines[heading_index : heading_index + 5] == [
        "Types",
        "-----",
        "",
        ".. autoclass:: mod.Foo",
        "   :members:",
    ]


# ---------------------------------------------------------------------------
# Stray / incidental comments
# ---------------------------------------------------------------------------


def test_standalone_comment_not_starting_with_colon_is_ignored(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = [
            "Foo",
            # just a stray note, not a section
            "Bar",
        ]
        """,
    )

    # Both stay in the single unlabeled leading section -- no heading appears.
    lines = rendered.splitlines()
    assert not any(line and set(line) == {"-"} for line in lines)
    assert ".. autoclass:: mod.Foo" in lines
    assert ".. autoclass:: mod.Bar" in lines


def test_trailing_same_line_comment_is_not_a_section_marker(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = [
            "Foo",  #: looks like a marker but is trailing
            "Bar",
        ]
        """,
    )

    lines = rendered.splitlines()
    assert not any(line and set(line) == {"-"} for line in lines)


def test_stray_comment_immediately_before_a_colon_line_suppresses_that_section(
    tmp_path,
):
    """
    Documented limitation: a section is only recognized when the *first*
    line of its contiguous comment block starts with ``#:``. If an
    unrelated bare '#' comment sits directly above (no blank line
    separating them), the whole block -- including the '#:' line -- is
    swallowed as incidental commentary rather than opening a section.
    """
    rendered = render(
        tmp_path,
        """\
        __all__ = [
            "Foo",
            # stray note
            #: Utility functions
            "make_foo",
        ]
        """,
    )

    lines = rendered.splitlines()
    assert "Utility functions" not in lines
    assert ".. autofunction:: mod.make_foo" in lines


# ---------------------------------------------------------------------------
# Directive selection by runtime type
# ---------------------------------------------------------------------------


def test_directive_selection_class_function_and_plain_data(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = [
            "Foo",
            "make_foo",
            "VERSION",
        ]
        """,
        body="class Foo:\n    pass\n\n\ndef make_foo():\n    return Foo()\n\n\nVERSION = '1.0'\n",
    )

    lines = rendered.splitlines()
    assert ".. autoclass:: mod.Foo" in lines
    assert "   :members:" in lines
    assert ".. autofunction:: mod.make_foo" in lines
    assert ".. autodata:: mod.VERSION" in lines


# ---------------------------------------------------------------------------
# Fallback: not statically determinable
# ---------------------------------------------------------------------------


def test_falls_back_when_all_is_built_dynamically(tmp_path):
    rendered = render(
        tmp_path,
        """\
        _extra = ["Bar"]
        __all__ = ["Foo"] + _extra
        """,
        body="class Foo:\n    pass\n\n\nBar = 1\n",
    )

    assert rendered.splitlines()[-2:] == [".. automodule:: mod", "   :members:"]


def test_falls_back_when_all_has_non_string_entries(tmp_path):
    rendered = render(
        tmp_path,
        """\
        NAME = "Foo"
        __all__ = [NAME]
        """,
        body="Foo = 1\n",
    )

    assert rendered.splitlines()[-2:] == [".. automodule:: mod", "   :members:"]


def test_falls_back_when_runtime_all_is_mutated_after_definition(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = ["Foo"]
        __all__.append("Bar")
        """,
        body="Foo = 1\nBar = 2\n",
    )

    assert rendered.splitlines()[-2:] == [".. automodule:: mod", "   :members:"]


def test_tuple_all_is_supported_same_as_list(tmp_path):
    rendered = render(
        tmp_path,
        """\
        __all__ = (
            #: Types
            "Foo",
        )
        """,
        body="class Foo:\n    pass\n",
    )

    assert "Types" in rendered.splitlines()
    assert ".. autoclass:: mod.Foo" in rendered.splitlines()
