"""Documentation checks.

The README is long, which is exactly why the summary at the top links into it.
Those links break silently: renaming a heading does not fail anything, the anchor
just stops resolving and quietly sends the reader to the top of the page. That is
the failure this file exists to catch.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = [
    Path(__file__).resolve().parents[1] / name
    for name in ("README.md", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md")
]

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.M)
_INTERNAL_LINK = re.compile(r"\]\(#([^)]+)\)")


def _anchor(title: str) -> str:
    """GitHub's slug for a heading: lowercased, punctuation dropped, spaces hyphenated."""
    slug = title.lower().replace("`", "")
    slug = re.sub(r"[^\w\s-]", "", slug)
    return re.sub(r"\s+", "-", slug.strip())


@pytest.mark.parametrize("path", [p for p in DOCS if p.is_file()], ids=lambda p: p.name)
def test_every_internal_link_resolves_to_a_heading(path: Path):
    text = path.read_text(encoding="utf-8")
    anchors = {_anchor(m.group(2)) for m in _HEADING.finditer(text)}
    broken = sorted({link for link in _INTERNAL_LINK.findall(text) if link not in anchors})
    assert not broken, f"{path.name} links to headings that do not exist: {broken}"


def test_the_feature_list_is_the_first_section():
    """It exists so nobody has to read the whole file to decide whether to try it.

    Directly below the screenshots and above everything else, which is where it
    was asked to be. Anything that pushes it further down defeats the point.
    """
    lines = (DOCS[0]).read_text(encoding="utf-8").splitlines()
    headings = [(i, line) for i, line in enumerate(lines) if line.startswith("## ")]
    assert headings, "README has no sections at all"
    index, first = headings[0]
    assert first == "## Features", f"first section is {first!r}, not the feature list"
    assert index < 60, f"feature list has drifted to line {index}; it should stay above the fold"
