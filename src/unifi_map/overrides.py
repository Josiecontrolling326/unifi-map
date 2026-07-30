"""Manual topology overrides: schema and loader.

STATUS: the schema and loader below are implemented and tested. Applying them to
a :class:`~unifi_map.model.Topology` is NOT implemented yet; see ``apply()`` and
``docs/overrides.md``. Nothing in the render path calls this module.

Why this exists
---------------
The controller cannot see parts of a real network:

- A direct link it does not participate in. A NAS on a 10G SFP+ DAC to a switch
  shows up with no ``sw_mac``, so the renderer can only anchor it to the
  "uplink not reported by controller" placeholder.
- Gear the controller reports as online but which is not meaningfully on the
  network, such as an access point whose radios were disabled deliberately. It
  is not offline, so ``--show-offline no`` will not remove it, and it is pure
  noise on the map.
- Anything nested inside another host. VMs and containers appear as their own
  clients with no indication that they live on a particular hypervisor.

And some things the controller reports are simply wrong. Ubiquiti's fingerprint
database misidentifies devices (a network-attached bidet confidently labelled a
smart toothbrush), which produces both the wrong name and the wrong artwork.

None of this can be inferred safely, and guessing would invent topology that does
not exist, so instead the user states it, in a small TOML file.

TOML is used because Python 3.11+ reads it from the standard library
(``tomllib``), it takes comments, and it is pleasant to hand-edit. No new
dependency.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class OverrideError(ValueError):
    """Raised for a malformed overrides file."""


@dataclass(frozen=True)
class Link:
    """An explicit connection the controller does not report.

    ``source`` and ``target`` are selectors, not ids: a MAC, an IP, or a
    hostname/device name. Resolution is deliberately deferred so a file stays
    readable and survives a device being renamed in one place only.
    """

    source: str
    target: str
    port: str | None = None
    speed: str | None = None
    note: str | None = None
    wireless: bool = False

    @property
    def label(self) -> str | None:
        """What to print on the edge."""
        parts = [p for p in (f"port {self.port}" if self.port else None, self.speed) if p]
        return " · ".join(parts) or None


@dataclass(frozen=True)
class Hosted:
    """A node that runs inside another node: a VM, container or jail."""

    guest: str
    host: str
    note: str | None = None


@dataclass(frozen=True)
class NodeOverride:
    """A correction to how one node is presented.

    Exists because Ubiquiti's fingerprint is sometimes wrong, and a wrong
    fingerprint yields both a wrong name and wrong artwork. `icon` points at a
    file the user supplies; nothing is fetched for it.
    """

    match: str
    name: str | None = None
    icon: Path | None = None
    note: str | None = None
    # Drop the node from the map entirely: gear the controller still calls online
    # but which is idle by choice, or a host you would rather not put on a map
    # you are sharing. Leaf nodes only; see the TODO about children.
    hide: bool = False


@dataclass
class Overrides:
    links: list[Link] = field(default_factory=list)
    hosted: list[Hosted] = field(default_factory=list)
    nodes: list[NodeOverride] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.links or self.hosted or self.nodes)


def _require_str(table: dict, key: str, context: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise OverrideError(f"{context}: '{key}' is required and must be a non-empty string")
    return value.strip()


def _optional_str(table: dict, key: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    # Ports are naturally written unquoted in TOML, so accept an int too.
    if isinstance(value, int | float):
        return str(int(value))
    if not isinstance(value, str):
        raise OverrideError(f"'{key}' must be a string or number, got {type(value).__name__}")
    return value.strip() or None


def parse(payload: dict, base_dir: Path | None = None) -> Overrides:
    """Build :class:`Overrides` from an already-decoded TOML mapping.

    *base_dir* is what relative ``icon`` paths resolve against: the directory
    holding the overrides file, so a config plus an assets folder can be moved
    around together.
    """
    result = Overrides()

    for index, raw in enumerate(payload.get("link") or [], start=1):
        if not isinstance(raw, dict):
            raise OverrideError(f"[[link]] #{index} must be a table")
        context = f"[[link]] #{index}"
        result.links.append(
            Link(
                source=_require_str(raw, "from", context),
                target=_require_str(raw, "to", context),
                port=_optional_str(raw, "port"),
                speed=_optional_str(raw, "speed"),
                note=_optional_str(raw, "note"),
                wireless=bool(raw.get("wireless", False)),
            )
        )

    for index, raw in enumerate(payload.get("hosted") or [], start=1):
        if not isinstance(raw, dict):
            raise OverrideError(f"[[hosted]] #{index} must be a table")
        context = f"[[hosted]] #{index}"
        result.hosted.append(
            Hosted(
                guest=_require_str(raw, "guest", context),
                host=_require_str(raw, "host", context),
                note=_optional_str(raw, "note"),
            )
        )

    for index, raw in enumerate(payload.get("node") or [], start=1):
        if not isinstance(raw, dict):
            raise OverrideError(f"[[node]] #{index} must be a table")
        context = f"[[node]] #{index}"
        icon_raw = _optional_str(raw, "icon")
        icon: Path | None = None
        if icon_raw:
            candidate = Path(icon_raw).expanduser()
            # Relative to the overrides file, not the working directory, so the
            # same config works regardless of where the tool is run from.
            if not candidate.is_absolute() and base_dir is not None:
                candidate = base_dir / candidate
            icon = candidate
        name = _optional_str(raw, "name")
        note = _optional_str(raw, "note")
        hide = bool(raw.get("hide", False))
        if name is None and icon is None and not hide:
            raise OverrideError(f"{context}: needs at least one of 'name', 'icon' or 'hide'")
        result.nodes.append(
            NodeOverride(
                match=_require_str(raw, "match", context),
                name=name,
                icon=icon,
                note=note,
                hide=hide,
            )
        )

    return result


def load(path: Path) -> Overrides:
    """Read and validate an overrides file."""
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OverrideError(f"No overrides file at {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise OverrideError(f"{path} is not valid TOML: {exc}") from exc
    return parse(payload, base_dir=path.parent)


# TODO: wire overrides into the render path. Remaining work, roughly in order:
#
# 1. resolve(selector, topo) -> node id. Match a MAC exactly first, then an IP,
#    then a case-insensitive label. Ambiguous or unmatched selectors must be a
#    loud error, never a silent no-op; a typo that quietly does nothing is
#    worse than a failed run.
# 2. apply(topo, overrides). For each Link, add an Edge and drop the node's
#    anchor to UNKNOWN_UPLINK_ID if it has one; remove the placeholder entirely
#    once nothing references it. For each Hosted, re-parent guest onto host with
#    an edge styled to read as containment rather than a cable.
# 3. A distinct visual treatment so a user-asserted link is never mistaken for
#    something the controller reported. Probably a dotted edge plus the note as
#    the label.
# 4. NodeOverride hide: LEAF NODES ONLY. Refuse to hide a node that has
#    children, naming the node and its children in the error. There is no good
#    answer otherwise: dropping the children silently loses real devices, and
#    reattaching them to the hidden node's parent invents a link that does not
#    exist. For a leaf, drop the node, the edge to its parent, and
#    UNKNOWN_UPLINK_ID if nothing points at it any more. Report a count of
#    hidden nodes rather than silently shrinking the map.
# 5. NodeOverride: substitute name, and load `icon` as a user-supplied
#    IconAsset. It must be measured the same way cached artwork is, so aspect
#    ratio still drives the cell size. A missing or unreadable icon file has to
#    be a loud error, not a silent fall back to the wrong fingerprint artwork.
# 6. CLI: --overrides PATH, defaulting to ./overrides.toml when present.
# 7. Round-trip help: a subcommand that lists unplaced nodes and suspicious
#    fingerprints as a starter overrides file, so the user edits rather than
#    writes from scratch.
def apply(topo, overrides: Overrides):
    """Not implemented yet. See the TODO above and docs/overrides.md."""
    raise NotImplementedError(
        "Applying overrides is not implemented yet. The schema and loader are "
        "stable; see docs/overrides.md for the intended behaviour."
    )
