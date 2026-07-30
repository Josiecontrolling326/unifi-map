"""Make Graphviz SVG output self-contained.

Graphviz can only read an `<IMG SRC=...>` from the filesystem, so the SVG it
emits references artwork by absolute path. That file is fine locally but breaks
the moment the SVG is moved, emailed or opened on another machine. Rewriting
each reference into a base64 data URI makes the diagram a single portable file.
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Matches xlink:href="..." and href="..." on <image> elements.
_HREF = re.compile(rb'(?P<attr>(?:xlink:)?href=")(?P<path>[^"]+\.png)(?P<tail>")')


def inline_svg_images(svg: bytes, allowed_root: Path | None = None) -> bytes:
    """Replace on-disk PNG references in *svg* with base64 data URIs.

    *allowed_root* restricts which files may be embedded, so a crafted device
    name cannot cause arbitrary files to be read into the output.
    """
    cache: dict[bytes, bytes] = {}
    root = allowed_root.resolve() if allowed_root else None

    def replace(match: re.Match[bytes]) -> bytes:
        raw = match.group("path")
        if raw.startswith(b"data:"):
            return match.group(0)
        if raw in cache:
            return match.group("attr") + cache[raw] + match.group("tail")

        try:
            path = Path(raw.decode("utf-8")).resolve()
        except (UnicodeDecodeError, OSError):
            return match.group(0)

        if root is not None and not path.is_relative_to(root):
            log.debug("Refusing to inline %s: outside %s", path, root)
            return match.group(0)
        if not path.is_file():
            return match.group(0)

        encoded = base64.b64encode(path.read_bytes())
        uri = b"data:image/png;base64," + encoded
        cache[raw] = uri
        return match.group("attr") + uri + match.group("tail")

    return _HREF.sub(replace, svg)
