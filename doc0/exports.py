# Static parsing of ``__all__`` list/tuple literals.
#
# Recovers declaration order and ``#:``-comment section headers from a
# module's source, when ``__all__`` is a plain, statically analyzable
# list/tuple of string literals. Anything else (computed values, string
# concatenation, conditional assignment, mismatches with the module's actual
# runtime ``__all__``, ...) is reported as "not statically determinable" so
# callers can fall back to a simpler, unordered listing.
#
# Section syntax::
#
#     __all__ = [
#         "Foo",
#         "Bar",
#         #: Utility functions
#         "make_foo",
#         #: Advanced
#         #:
#         #: These require care -- see the guide before using them.
#         #: They are not stable across releases.
#         "make_bar",
#     ]
#
# A section is opened by a standalone comment line (nothing but whitespace
# before the ``#``) whose text starts with ``#:``. That line's text (after
# the marker) is the section title. Every standalone comment line
# immediately following it -- with no blank source line or entry in
# between -- is that section's body, rendered verbatim as paragraph text; a
# blank comment line (``#:`` or ``#`` with nothing else) is a paragraph
# break, and continuation lines don't need the ``#:`` marker themselves
# (plain ``#`` works once a section has been opened). Entries before the
# first section-opening comment form a leading, unlabeled section.
#
# A standalone comment block whose *first* line is not a ``#:`` line is
# just incidental commentary: it's ignored, and does not start a section --
# even if a `#:` line appears later in that same contiguous block. Only a
# `#:` line reached with no other comment line directly above it opens a
# section.

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

__all__ = ["Section", "parse_export_sections"]

_SECTION_MARKER = "#:"


@dataclass
class Section:
    """
    A named (or unlabeled) group of exported symbol names, in declaration
    order.
    """

    #: The section title, taken from a ``#:``-opened comment block
    #: preceding this group's first entry. None for the leading,
    #: unlabeled group of entries that appear before any such block (or
    #: for the whole list, if it has no section comments at all).
    title: str | None

    #: Body paragraph lines for this section, verbatim from the comment
    #: block (empty strings mark paragraph breaks). Always empty when
    #: title is None.
    body: list[str] = field(default_factory=list)

    #: Exported symbol names belonging to this section, in declaration order.
    names: list[str] = field(default_factory=list)


def parse_export_sections(
    source_path: Path, module: ModuleType
) -> list[Section] | None:
    """
    Parse ``__all__`` in the given source file into ordered, ``#:``-delimited
    sections, if -- and only if -- it can be statically and reliably
    determined.

    Returns None when ``__all__`` is missing, is not a single top-level
    plain list/tuple of string literals, or its statically-parsed names
    don't exactly match the module's actual runtime ``__all__`` (e.g.
    because it's built dynamically, conditionally, or mutated after
    definition) -- callers should fall back to whatever default listing
    they'd otherwise use in that case.
    """
    runtime_all = getattr(module, "__all__", None)
    if runtime_all is None:
        return None

    try:
        source = source_path.read_text()
    except OSError:
        return None

    node = _find_all_literal(source)
    if node is None:
        return None

    names = _extract_string_literal_names(node)
    if names is None or names != list(runtime_all):
        return None

    return _split_into_sections(source, node, names)


def _find_all_literal(source: str) -> ast.List | ast.Tuple | None:
    """
    Find a single, top-level, unconditional ``__all__ = [...]`` (or
    ``(...)``) assignment and return its list/tuple node, or None if
    there isn't exactly one such simple assignment.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    found: ast.List | ast.Tuple | None = None
    for stmt in tree.body:
        if "__all__" not in _assignment_targets(stmt):
            continue
        value = stmt.value  # type: ignore[union-attr]
        if not isinstance(value, (ast.List, ast.Tuple)) or found is not None:
            # Not a plain literal, or a second __all__ assignment: too
            # ambiguous to trust statically.
            return None
        found = value

    return found


def _assignment_targets(stmt: ast.stmt) -> list[str]:
    if isinstance(stmt, ast.Assign):
        return [target.id for target in stmt.targets if isinstance(target, ast.Name)]
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return [stmt.target.id]
    return []


def _extract_string_literal_names(node: ast.List | ast.Tuple) -> list[str] | None:
    names = []
    for element in node.elts:
        if not (isinstance(element, ast.Constant) and isinstance(element.value, str)):
            return None
        names.append(element.value)
    return names


def _split_into_sections(
    source: str, node: ast.List | ast.Tuple, names: list[str]
) -> list[Section]:
    """
    For each entry, look at the contiguous run of standalone comment
    lines immediately preceding it (if any) to decide whether it opens a
    new section, then group entries accordingly.
    """
    comment_lines = _standalone_comment_lines(source, node)

    sections: list[Section] = []
    current = Section(title=None)
    sections.append(current)

    previous_end_line = node.lineno  # exclusive lower bound for the next backward scan

    for element, name in zip(node.elts, names):
        run = _preceding_comment_run(comment_lines, previous_end_line, element.lineno)
        if run and run[0].startswith(_SECTION_MARKER):
            title = run[0][len(_SECTION_MARKER) :].strip()
            body = [_strip_comment_marker(line) for line in run[1:]]
            body = _strip_blank_edges(body)
            current = Section(title=title, body=body)
            sections.append(current)
        current.names.append(name)
        previous_end_line = element.lineno + 1

    return [section for section in sections if section.names]


def _strip_blank_edges(body: list[str]) -> list[str]:
    """
    Drop leading/trailing blank paragraph-break lines (they're just the
    blank-line-after-title artifact, not meaningful spacing); internal
    blank lines between paragraphs are kept.
    """
    start = 0
    end = len(body)
    while start < end and not body[start]:
        start += 1
    while end > start and not body[end - 1]:
        end -= 1
    return body[start:end]


def _strip_comment_marker(text: str) -> str:
    if text.startswith(_SECTION_MARKER):
        return text[len(_SECTION_MARKER) :].strip()
    return text[1:].strip()  # plain "#" comment


def _preceding_comment_run(
    comment_lines: dict[int, str], lower_bound: int, before_line: int
) -> list[str]:
    """
    Collect the contiguous run of standalone comment lines ending right
    before `before_line`, without crossing `lower_bound` (the line right
    after the previous entry, or the list's opening line).
    """
    run: list[str] = []
    line_no = before_line - 1
    while line_no >= lower_bound and line_no in comment_lines:
        run.append(comment_lines[line_no])
        line_no -= 1
    run.reverse()
    return run


def _standalone_comment_lines(
    source: str, node: ast.List | ast.Tuple
) -> dict[int, str]:
    """
    Return {line_number: raw_comment_text} for every comment that is the
    only non-whitespace content on its line, within the span of `node`.
    """
    end_line = node.end_lineno or node.lineno
    lines: dict[int, str] = {}

    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        line_no, col = tok.start
        if not (node.lineno <= line_no <= end_line):
            continue
        if tok.line[:col].strip():
            # Something other than whitespace precedes the comment on its
            # line: a trailing same-line comment, not standalone.
            continue
        lines[line_no] = tok.string

    return lines
