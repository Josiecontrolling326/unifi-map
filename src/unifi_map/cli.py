"""Command line interface.

Two stages, deliberately separable:

  fetch   talk to the controller, cache raw JSON
  render  turn cached JSON into diagrams

Keeping them apart means you can re-render endlessly while iterating on style
without hammering the controller, and each cached snapshot is a record of what
the network looked like at that moment.

`fetch --support-file` fills the same cache from a support file archive rather
than a controller, so everything downstream behaves identically.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

from . import __version__
from .assets import AssetStore, IconAsset
from .client import Snapshot, UniFiClient, UniFiError
from .config import ConfigError, load_config
from .layout import GraphvizError, GraphvizMissing, compute_layout, run_dot, stagger
from .model import Kind, Topology, build_topology, client_networks, filter_by_network
from .obfuscate import id_map, obfuscate
from .overrides import OverrideError
from .overrides import apply as apply_overrides
from .overrides import load as load_overrides
from .render_dot import ICON_SETS, LAYOUTS, Style, render_dot
from .render_drawio import render_drawio
from .support import SupportFileError, load_support_file
from .svg_post import inline_svg_images
from .theme import THEMES, get_theme

log = logging.getLogger("unifi_map")

DEFAULT_CACHE = Path("cache")
DEFAULT_OUT = Path("out")
# Artwork lives apart from snapshots so --cache-dir can point at a read-only
# dataset without downloads being written into it.
DEFAULT_ASSET_CACHE = Path("cache/assets")
# Picked up automatically when present, so the flag is only needed to point
# somewhere else.
DEFAULT_OVERRIDES = Path("overrides.toml")

# svg first: it is the format that actually solves the readability problem.
ALL_FORMATS = ("svg", "pdf", "png", "dot", "drawio")

# Below this many clients a view is not wide enough to need staggering, and
# unflatten instead chains sibling APs into a pointless diagonal cascade.
STAGGER_MIN_CLIENTS = 15


def _safe_name(text: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in text]
    return "".join(keep).strip("-").lower() or "network"


def _stagger_for(topo: Topology, requested: int, style: Style) -> int:
    if requested <= 0 or not style.staggers:
        return 0
    clients = sum(
        1 for n in topo.nodes.values() if n.kind in (Kind.WIRED_CLIENT, Kind.WIRELESS_CLIENT)
    )
    return requested if clients >= STAGGER_MIN_CLIENTS else 0


def cmd_fetch(args: argparse.Namespace) -> int:
    if args.support_file:
        return _fetch_from_support_file(args)

    config = load_config(args.env_file)
    client = UniFiClient(config)
    log.info("Reading %s (site %s)", config.host, config.site)
    snapshot = client.snapshot()

    store = AssetStore(cache_dir=args.asset_cache)
    # Kept beside the artwork rather than in the snapshot: it describes
    # Ubiquiti's catalogue, not this network, and a support file has no copy of
    # it, so caching it here is what lets `--support-file` resolve client icons.
    store.save_fingerprint_db(snapshot.get("fingerprint"))

    try:
        font, codepoints = client.fetch_icon_font()
        store.save_icon_font(font, codepoints)
        log.info("Cached the controller's icon font (%d client glyphs).", len(codepoints))
    except UniFiError as exc:
        # Only needed for clients with no usable fingerprint; not fatal.
        log.warning("Could not cache the icon font (%s); generic client glyphs disabled.", exc)

    snapshot.write(args.cache_dir)
    log.info("Wrote snapshot to %s/", args.cache_dir)
    for name, payload in sorted(snapshot.payloads.items()):
        log.info("  %-14s %s", name, _describe(payload))
    return 0


def _fetch_from_support_file(args: argparse.Namespace) -> int:
    """Populate the snapshot cache from a support file instead of a controller.

    Deliberately writes the same cache `fetch` writes, so every render option,
    including per-network diagrams, overrides and obfuscation, works afterwards
    without knowing the difference. No credentials are read and no request is
    made, which is what makes a support file a safe thing to be sent.
    """
    store = AssetStore(cache_dir=args.asset_cache, offline=getattr(args, "offline", False))
    # Not in the archive. Downloading it is opt-in, because someone reading a
    # support file has often chosen this path precisely to avoid outbound
    # traffic; an already-cached copy is used either way, being purely local.
    fingerprint_db = store.fingerprint_db(download=args.fetch_fingerprints)
    if fingerprint_db is None and not args.fetch_fingerprints:
        log.info(
            "Client product artwork is off: it needs Ubiquiti's fingerprint "
            "database, which a support file does not contain. Pass "
            "--fetch-fingerprints to download it (about 1 MB, cached "
            "afterwards). Nothing else here touches the network."
        )

    snapshot = load_support_file(args.support_file, args.support_site, fingerprint_db)
    snapshot.write(args.cache_dir)
    log.info("Wrote snapshot to %s/", args.cache_dir)
    for name, payload in sorted(snapshot.payloads.items()):
        log.info("  %-14s %s", name, _describe(payload))
    return 0


def _describe(payload: object) -> str:
    """Summarise a payload for the fetch log.

    v1 endpoints wrap records in `data`; the v2 topology endpoint returns a dict
    of `vertices`/`edges` instead, which would otherwise read as "0 records" and
    look like a failure.
    """
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return f"{len(data)} records"
        keys = [k for k in payload if k != "meta"]
        parts = [
            f"{k}={len(payload[k])}" if isinstance(payload[k], list | dict) else f"{k}={payload[k]}"
            for k in keys
        ]
        return ", ".join(parts) or "empty"
    if isinstance(payload, list):
        return f"{len(payload)} records"
    return "no data"


def _resolve_icons(topo: Topology, store: AssetStore, theme) -> dict[str, IconAsset]:
    """Map node id to cached artwork, fetching as needed.

    UniFi devices are matched on sysid against Ubiquiti's hardware catalog.
    Clients are matched on their fingerprint dev_id against Ubiquiti's client
    artwork, which is what the topology view itself renders; clients with no
    usable fingerprint fall back to the controller's own icon-font glyph, the
    same way the UI does.

    All of it is Ubiquiti's and none of it is vendored into this repository: it
    is downloaded on first use and cached.
    """
    icons: dict[str, IconAsset] = {}

    # --- UniFi hardware ---
    devices = {n.sysid for n in topo.nodes.values() if n.sysid is not None}
    by_sysid: dict[int, IconAsset | None] = {s: store.icon(s) for s in sorted(devices)}
    for node in topo.nodes.values():
        if node.sysid is None:
            continue
        asset = by_sysid.get(node.sysid)
        if asset is not None:
            icons[node.id] = asset
        # Prefer the catalog's product name over the terse model code.
        product = store.product_name(node.sysid)
        if product:
            node.detail = product

    device_total = len(devices)
    device_found = sum(1 for a in by_sysid.values() if a is not None)
    log.info("Artwork: %d/%d UniFi devices", device_found, device_total)

    # --- clients ---
    client_nodes = [n for n in topo.nodes.values() if n.glyph_name is not None]
    if not client_nodes:
        return icons

    dev_ids = {n.dev_id for n in client_nodes if n.dev_id is not None}
    by_dev_id: dict[int, IconAsset | None] = {d: store.client_icon(d) for d in sorted(dev_ids)}

    glyph_cache: dict[str, IconAsset | None] = {}
    from_glyph = 0
    from_fingerprint = 0
    from_hardware = 0
    for node in client_nodes:
        asset = by_dev_id.get(node.dev_id) if node.dev_id is not None else None
        if asset is not None:
            from_fingerprint += 1
        elif (hardware := _hardware_asset(node, store)) is not None:
            asset = hardware
            from_hardware += 1
        else:
            # Same fallback the UI uses: a generic user/guest x wired/wireless
            # glyph from the controller's icon font.
            name = node.glyph_name
            if name not in glyph_cache:
                glyph_cache[name] = store.client_glyph(name, theme.text_muted)
            asset = glyph_cache[name]
            if asset is not None:
                from_glyph += 1
        if asset is not None:
            icons[node.id] = asset

    # Counted per node, not per dev_id: several clients can share a fingerprint.
    plain = len(client_nodes) - from_fingerprint - from_hardware - from_glyph
    log.info(
        "Artwork: %d/%d clients (%d product, %d UniFi hardware, %d generic glyph, %d none)",
        from_fingerprint + from_hardware + from_glyph,
        len(client_nodes),
        from_fingerprint,
        from_hardware,
        from_glyph,
        plain,
    )
    return icons


def _hardware_asset(node, store: AssetStore) -> IconAsset | None:
    """Artwork for UniFi hardware that shows up as a client.

    A Protect camera on a switch port is a client with no fingerprint, so the
    Network app offers nothing to look up. Its hostname can be matched against
    the hardware catalog instead, narrowed by what another app says it is.
    """
    if not node.hardware_type and not (node.oui and "ubiquiti" in node.oui.lower()):
        return None

    sysid = store.sysid_for_name(node.label, device_type=node.hardware_type)
    if sysid is None:
        return None

    asset = store.icon(sysid)
    if asset is not None:
        product = store.product_name(sysid)
        if product:
            node.detail = product
    return asset


def _write_outputs(
    dot_source: str,
    topo: Topology,
    out_dir: Path,
    stem: str,
    formats: list[str],
    style: Style,
    icons: dict[str, IconAsset],
    stagger_depth: int = 0,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # Every icon this render used, and nothing else, may be embedded.
    icon_paths = {asset.path for asset in icons.values() if asset.path is not None}

    # Stagger once, up front, so the SVG/PDF and the draw.io coordinates are
    # computed from byte-identical DOT and therefore agree exactly.
    dot_source = stagger(dot_source, stagger_depth)

    if "dot" in formats:
        path = out_dir / f"{stem}.dot"
        path.write_text(dot_source, encoding="utf-8")
        log.info("  %s", path)

    for fmt in ("svg", "pdf", "png"):
        if fmt not in formats:
            continue
        data = run_dot(dot_source, fmt)
        if fmt == "svg":
            # Graphviz references artwork by filesystem path; inline it so the
            # SVG is a single portable file.
            data = inline_svg_images(data, allowed=icon_paths)
        path = out_dir / f"{stem}.{fmt}"
        path.write_bytes(data)
        log.info("  %s (%.1f KiB)", path, len(data) / 1024)

    if "drawio" in formats:
        layout = compute_layout(dot_source)
        xml = render_drawio(topo, layout, stem, style.theme, icons)
        path = out_dir / f"{stem}.drawio"
        path.write_text(xml, encoding="utf-8")
        log.info("  %s (%.1f KiB)", path, len(xml.encode()) / 1024)


def cmd_render(args: argparse.Namespace) -> int:
    snapshot = Snapshot.read(args.cache_dir)
    topo = build_topology(
        snapshot,
        include_clients=not args.no_clients,
        include_offline=args.show_offline == "yes",
    )

    try:
        style = Style(
            theme=get_theme(args.theme),
            icons=args.icons,
            layout=args.layout,
            legend=args.legend,
            title_block=args.title_block,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    tally = topo.counts()
    log.info(
        "Topology: %s",
        ", ".join(f"{count} {kind}" for kind, count in sorted(tally.items())) or "empty",
    )
    log.info("Style: icons=%s layout=%s theme=%s", style.icons, style.layout, args.theme)

    override_icons: dict[str, IconAsset] = {}
    path = args.overrides or (DEFAULT_OVERRIDES if DEFAULT_OVERRIDES.is_file() else None)
    if path is not None:
        overrides = load_overrides(path)
        result = apply_overrides(topo, overrides)
        topo = result.topology
        override_icons = result.icons
        log.info(
            "Overrides from %s: %d link(s), %d nested, %d renamed, %d hidden%s",
            path,
            result.links_added,
            result.hosted_applied,
            result.renamed,
            len(result.hidden),
            f" ({', '.join(result.hidden)})" if result.hidden else "",
        )

    icons: dict[str, IconAsset] = {}
    store = AssetStore(cache_dir=args.asset_cache, offline=args.offline)
    if style.icons == "unifi":
        icons = _resolve_icons(topo, store, style.theme)

    # Artwork the user supplied wins over anything looked up for them.
    icons.update(override_icons)

    if args.obfuscate:
        # Artwork is resolved first and then carried across, because UniFi
        # hardware appearing as a client is matched on its hostname and
        # scrubbing that first would lose the picture.
        mapping = id_map(topo)
        icons = {mapping[k]: v for k, v in icons.items() if k in mapping}
        topo = obfuscate(topo)
        log.info("Obfuscated: names, addresses, MACs, network names and SSIDs replaced.")

    title = args.title or "Network map"
    subtitle = _subtitle(tally)
    formats = list(dict.fromkeys(args.formats))
    stem = _safe_name(args.name)

    log.info("Full map:")
    _write_outputs(
        render_dot(topo, title, style, icons, subtitle),
        topo,
        args.out_dir,
        stem,
        formats,
        style,
        icons,
        _stagger_for(topo, args.stagger, style),
    )

    if args.per_network:
        names = client_networks(topo)
        if not names:
            log.warning("No client networks found; skipping per-network views.")
        for name in names:
            view = filter_by_network(topo, name)
            log.info("Network view %r:", name)
            _write_outputs(
                render_dot(view, f"{title}: {name}", style, icons, _subtitle(view.counts())),
                view,
                args.out_dir,
                f"{stem}-{_safe_name(name)}",
                formats,
                style,
                icons,
                _stagger_for(view, args.stagger, style),
            )

    return 0


def _subtitle(tally: dict[str, int]) -> str:
    devices = sum(tally.get(k, 0) for k in ("gateway", "switch", "ap", "bridge"))
    clients = tally.get("wired_client", 0) + tally.get("wireless_client", 0)
    stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return f"{devices} UniFi devices · {clients} clients · generated {stamp}"


def cmd_all(args: argparse.Namespace) -> int:
    result = cmd_fetch(args)
    return result if result != 0 else cmd_render(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unifi-map",
        description="Export a UniFi network topology as zoomable vector diagrams "
        "and editable draw.io files.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Credential file (default: $UNIFI_MAP_ENV, ./.env, ~/.config/unifi-map/env)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE,
        help=f"Where controller snapshots are read/written (default: {DEFAULT_CACHE})",
    )
    parser.add_argument(
        "--asset-cache",
        type=Path,
        default=DEFAULT_ASSET_CACHE,
        help=f"Where downloaded artwork is cached (default: {DEFAULT_ASSET_CACHE}). "
        "Kept separate from --cache-dir so a read-only snapshot directory stays clean.",
    )
    parser.add_argument(
        "--support-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="Read the topology from a UniFi support file (.tgz) instead of a "
        "controller. Needs no credentials and no network access.",
    )
    parser.add_argument(
        "--support-site",
        default=None,
        metavar="NAME",
        help="Which site to map from a multi-site support file "
        "(default: the one with the most devices)",
    )
    parser.add_argument(
        "--fetch-fingerprints",
        action="store_true",
        help="Allow downloading Ubiquiti's client fingerprint database, which is "
        "what gives clients real product artwork when reading a support file. "
        "Off by default: reading a support file otherwise contacts nothing.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"unifi-map {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    render_flags = argparse.ArgumentParser(add_help=False)
    render_flags.add_argument(
        "-f",
        "--formats",
        nargs="+",
        choices=ALL_FORMATS,
        default=["svg", "drawio"],
        help="Output formats (default: svg drawio)",
    )
    render_flags.add_argument(
        "--icons",
        choices=ICON_SETS,
        default="unifi",
        help="unifi: real Ubiquiti product artwork, fetched and cached at runtime. "
        "builtin: geometric shapes only, no network access (default: unifi)",
    )
    render_flags.add_argument(
        "--layout",
        choices=LAYOUTS,
        default="unifi",
        help="unifi: left-to-right tree like the UniFi UI, no port labels. "
        "sane: top-down and leaf-staggered, with port labels, built to be "
        "readable on a busy network (default: unifi)",
    )
    render_flags.add_argument(
        "--theme", choices=sorted(THEMES), default="light", help="Colour theme (default: light)"
    )
    render_flags.add_argument(
        "--offline",
        action="store_true",
        help="Never reach the network for artwork; use only what is already cached",
    )
    render_flags.add_argument("--name", default="network-map", help="Output filename stem")
    render_flags.add_argument(
        "--overrides",
        type=Path,
        default=None,
        help=f"Manual corrections: links the controller cannot see, nesting, "
        f"renames, your own artwork, and hiding. Defaults to {DEFAULT_OVERRIDES} "
        "when that file exists",
    )
    render_flags.add_argument(
        "--obfuscate",
        action="store_true",
        help="Replace hostnames, addresses, MACs, network names and SSIDs with "
        "stable placeholders, keeping topology, roles and artwork intact, so the "
        "diagram can be shared",
    )
    render_flags.add_argument(
        "--title",
        default=None,
        help="Diagram title (default: Network map). Note that --obfuscate cannot "
        "clean a title you supply yourself",
    )
    render_flags.add_argument(
        "--no-clients", action="store_true", help="Infrastructure only, no clients"
    )
    render_flags.add_argument(
        "--show-offline",
        choices=("yes", "no"),
        default="no",
        help="Include devices the controller lists but that are not currently "
        "connected. Defaults to no, because a controller keeps remembering "
        "hardware long after it has been pulled from the rack; use yes when you "
        "want to see what it still thinks exists (default: no)",
    )
    render_flags.add_argument(
        "--per-network",
        action="store_true",
        help="Also emit one diagram per client network, which keeps a busy map readable",
    )
    render_flags.add_argument(
        "--legend",
        dest="legend",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Show the legend (default: on for --layout sane, off for --layout unifi)",
    )
    render_flags.add_argument(
        "--title-block",
        dest="title_block",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Show the title and subtitle above the map. A title sets a minimum "
        "canvas width, so turning it off crops dead space on a narrow map "
        "(default: on for --layout sane, off for --layout unifi)",
    )
    render_flags.add_argument(
        "--stagger",
        type=int,
        default=12,
        metavar="N",
        help="With --layout sane, stagger leaf nodes into rows of ~N to control "
        "aspect ratio (0 disables; higher is taller and narrower; default 12)",
    )

    sub.add_parser(
        "fetch", help="Cache controller data (or read --support-file instead)"
    ).set_defaults(func=cmd_fetch)
    sub.add_parser(
        "render", parents=[render_flags], help="Render diagrams from cache"
    ).set_defaults(func=cmd_render)
    sub.add_parser("all", parents=[render_flags], help="Fetch then render").set_defaults(
        func=cmd_all
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )
    try:
        return int(args.func(args))
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        return 2
    except OverrideError as exc:
        log.error("Overrides: %s", exc)
        return 2
    except GraphvizMissing as exc:
        log.error("%s", exc)
        return 3
    except (UniFiError, GraphvizError, SupportFileError) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
