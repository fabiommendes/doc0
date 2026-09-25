"""
Turn a project's README.md into the body of the docs front page.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

__all__ = ["readme_body"]

START_MARKER_RE = re.compile(r"<!--\s*(?:doc-zero|doc0)-start\s*-->")
END_MARKER_RE = re.compile(r"<!--\s*(?:doc-zero|doc0)-end\s*-->")

#: Hosts that only serve badges. Other hosts (GitHub, Read the Docs,
#: GitLab, ...) are recognized by a "badge" segment in the image URL path.
BADGE_HOSTS = frozenset(
    {
        "img.shields.io",
        "badge.fury.io",
        "badgen.net",
        "coveralls.io",
        "codecov.io",
        "travis-ci.org",
        "travis-ci.com",
        "api.travis-ci.org",
        "api.travis-ci.com",
        "circleci.com",
        "dl.circleci.com",
        "ci.appveyor.com",
        "pepy.tech",
        "static.pepy.tech",
        "results.pre-commit.ci",
        "api.codeclimate.com",
        "sonarcloud.io",
        "snyk.io",
    }
)

_MD_IMG = r"!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])?"
_MD_LINKED_IMG_RE = re.compile(rf"\[\s*({_MD_IMG})\s*\](?:\([^)]*\)|\[[^\]]*\])")
_MD_IMG_RE = re.compile(_MD_IMG)
_MD_IMG_PARTS_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]"
    r"(?:\(\s*<?(?P<url>[^)\s>]*)>?[^)]*\)|\[(?P<ref>[^\]]*)\])?"
)
_HTML_LINKED_IMG_RE = re.compile(r"<a\b[^>]*>\s*(<img\b[^>]*>)\s*</a>", re.IGNORECASE)
_HTML_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_HTML_SRC_RE = re.compile(r"""\bsrc\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_LINK_DEF_RE = re.compile(r"^ {0,3}\[(?P<label>[^\]]+)\]:\s*<?(?P<url>[^\s>]+)>?")
_LABEL_RE = re.compile(r"\[([^\]]+)\]")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def readme_body(src: str) -> str:
    """
    Return the part of a README that belongs in the generated docs.

    If the README has a ``<!-- doc-zero-start -->`` marker (or the older
    ``<!-- doc0-start -->``), everything after it is used verbatim.
    Otherwise, lines made only of known badges are removed, along with
    link definitions only those badges used, and then the leading title.

    In both cases, a ``<!-- doc-zero-end -->`` (or ``<!-- doc0-end -->``)
    marker ends the README: it and everything after it are dropped. An end
    marker that comes before the start marker is ignored.
    """
    parts = START_MARKER_RE.split(src, maxsplit=1)
    if len(parts) == 2:
        return END_MARKER_RE.split(parts[1], maxsplit=1)[0]
    head = END_MARKER_RE.split(src, maxsplit=1)[0]
    return _remove_title(_remove_badges(head))


def _remove_badges(src: str) -> str:
    """
    Remove lines that contain nothing but known badges.

    Badges inline in prose and anything inside fenced code blocks are kept.
    Reference-style link definitions that only removed badges used are
    removed as well.
    """
    lines = src.splitlines()
    in_fence = _fenced_lines(lines)
    definitions: dict[int, str] = {}
    urls: dict[str, str] = {}
    for i, line in enumerate(lines):
        if not in_fence[i] and (match := _LINK_DEF_RE.match(line)):
            label = match["label"].lower()
            definitions[i] = label
            urls.setdefault(label, match["url"])

    dropped = {
        i
        for i, line in enumerate(lines)
        if not in_fence[i] and i not in definitions and _is_badge_line(line, urls)
    }
    if not dropped:
        return src

    def labels_used(keep: set[int] | None = None) -> set[str]:
        return {
            label.lower()
            for i, line in enumerate(lines)
            if i not in definitions and (keep is None or i not in keep)
            for label in _LABEL_RE.findall(line)
        }

    orphaned = labels_used() - labels_used(keep=dropped)
    dropped |= {i for i, label in definitions.items() if label in orphaned}

    out: list[str] = []
    for i, line in enumerate(lines):
        if i in dropped:
            continue
        # Don't leave a double blank line where a dropped block used to be.
        if not line.strip() and i - 1 in dropped and (not out or not out[-1].strip()):
            continue
        out.append(line)
    if len(lines) - 1 in dropped:
        while out and not out[-1].strip():
            out.pop()
    return "\n".join(out)


def _is_badge_line(line: str, urls: dict[str, str]) -> bool:
    """
    True if the line holds at least one known badge and nothing else.
    """
    found = False

    def md_badge(match: re.Match[str]) -> str:
        nonlocal found
        parts = _MD_IMG_PARTS_RE.match(match[1] if match.re is _MD_LINKED_IMG_RE else match[0])
        assert parts is not None  # both patterns start with a markdown image
        url = parts["url"]
        if url is None:
            ref = parts["ref"] or parts["alt"]
            url = urls.get(ref.lower(), "")
        if _is_badge_url(url):
            found = True
            return ""
        return match[0]

    def html_badge(match: re.Match[str]) -> str:
        nonlocal found
        img = match[1] if match.re is _HTML_LINKED_IMG_RE else match[0]
        src = _HTML_SRC_RE.search(img)
        if src and _is_badge_url(src[1]):
            found = True
            return ""
        return match[0]

    rest = _MD_LINKED_IMG_RE.sub(md_badge, line)
    rest = _MD_IMG_RE.sub(md_badge, rest)
    rest = _HTML_LINKED_IMG_RE.sub(html_badge, rest)
    rest = _HTML_IMG_RE.sub(html_badge, rest)
    return found and not rest.strip()


def _is_badge_url(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return False
    host = parts.netloc.lower().removeprefix("www.")
    return host in BADGE_HOSTS or "badge" in parts.path.lower()


def _fenced_lines(lines: list[str]) -> list[bool]:
    """
    Flag each line that is part of a fenced code block, fences included.
    """
    flags: list[bool] = []
    fence: str | None = None
    for line in lines:
        match = _FENCE_RE.match(line)
        if fence is None:
            if match:
                fence = match[1]
            flags.append(fence is not None)
        else:
            flags.append(True)
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence):
                fence = None
    return flags


def _remove_title(src: str) -> str:
    """
    Remove a leading title from the given markdown source.

    Handles both an ATX title (``# Title`` as the first line) and a setext
    H1 title (a first line of text followed by a second line of ``===``).
    Leading blank lines left behind by the removal are stripped.
    """
    lines = src.lstrip("\n").splitlines()
    if not lines:
        return src

    if lines[0].startswith("#"):
        lines.pop(0)
    elif len(lines) >= 2 and re.match(r"^=+$", lines[1]):
        lines.pop(0)
        lines.pop(0)

    return "\n".join(lines).lstrip("\n")
