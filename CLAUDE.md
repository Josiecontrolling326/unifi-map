# CLAUDE.md: unifi-map

Pulls the UniFi topology from a controller's JSON API and renders it as vector
diagrams and editable draw.io files, using real Ubiquiti product artwork. See
`README.md` for usage; this covers what's easy to get wrong when changing it.

This is intended to be published publicly, so keep it site-agnostic and
non-identifying: no real hostnames, subnets, SSIDs, device addresses or
site-specific defaults in code, tests, docs or fixtures. Test data should look
like a plausible generic network, not like anyone's actual one.

## Commands

```bash
make check     # ruff format --check, ruff check, pytest (run before committing)
make map       # fetch + render against the live controller
make sane      # render in the readable (non-UniFi) layout
make offline   # builtin icons, no network access
make demo      # render the shipped demo dataset, no controller needed
make test      # pytest only
```

Single test: `.venv/bin/python -m pytest tests/test_assets.py::TestCatalog`

Tests never touch the network. Fixtures in `tests/conftest.py` are synthetic
payloads with invented MACs; `tests/test_assets.py` writes a catalog straight
into a temp cache so `AssetStore` reads from disk.

## Pipeline

Each stage owns one concern; nothing downstream of `model.py` sees raw
controller JSON.

1. **`config.py`** is the only module that reads `os.environ`. Accepts `UNIFI_*`
   and `UDM_*` names. Keep it that way: it's what makes a future Vault/OpenBao
   backend a single-file change. Credentials are `UNIFI_HOST` plus
   `UNIFI_API_KEY`, and nothing else.
2. **`client.py`** is the only module that talks to the controller. Auth is an
   `X-API-KEY` header set once in the constructor; there is no login, session or
   CSRF token. Network application paths are prefixed `/proxy/network`. `unwrap()` absorbs both the v1 `{"data": [...]}`
   envelope and bare v2 lists, returning `[]` on anything unexpected so a
   controller upgrade thins the diagram instead of raising.
   **`support.py`** is the alternative source: it reads the same `Snapshot` out
   of a support file archive, with no credentials and no network. Keep the two
   interchangeable, so anything added to one is considered for the other.
3. **`model.py`** normalizes into `Topology`. All schema quirks land here.
4. **`assets.py`** is the only module that fetches artwork. Cached under
   `--asset-cache` (default `cache/assets`), deliberately separate from the
   snapshot cache so `--cache-dir examples/demo` doesn't get downloads written
   into it.
5. **`layout.py`** is the only module that shells out to Graphviz (`dot`,
   `unflatten`).
6. **`render_dot.py` / `render_drawio.py` / `svg_post.py`** are pure functions
   from `Topology` to text. `theme.py` holds every colour, shape and label.

## Artwork constraints

- **Never vendor Ubiquiti artwork into the repo.** It is their IP. It is fetched
  at runtime and cached under `cache/` (gitignored). `--icons builtin` must stay
  a fully working, network-free path.
- **Match devices on `sysid`, not `model`.** The controller's `model` string does
  not reliably match the catalog's `shortnames` (`USWED72` vs `USPH24P`).
  Catalog sysids are hex strings, the controller reports decimal ints; all 1178
  catalog values are unambiguously hex, so strict base-16 parsing is correct.
- The controller does **not** serve device *images* locally (verified on Network
  10.5.67: every plausible path under `/proxy/network/manage/angular/<hash>/`
  returns the SPA's HTML 404). It DOES serve the icon font, and it serves the
  fingerprint database at `/proxy/network/v2/api/fingerprint_devices/0`.
- **Client artwork is `static.ui.com/fingerprint/0/{dev_id}_{size}.png`**, keyed
  on the fingerprint `dev_id` in `stat/sta` (`dev_id_override` wins). Only
  257x257, 129x129 and 101x101 exist; any other size 302s to ui.com, so treat a
  redirect as "absent" and do not follow it. This is `staticFingerprintOld` in
  the Network UI config.
- **Two frontends exist. Read the right one.** `/manage/` is the legacy Angular
  app; its `getIconClassName` resolves clients to just four icon-font glyphs, so
  reading it will convince you no client artwork exists. The app the browser
  actually loads is the React one served from the UniFi OS root (`/275.*.js`,
  `/main~2.*.js`), and that is where the real image URLs live. When hunting an
  asset, find it in the bundle the browser loads rather than inferring from a
  failed guess.
- **ISP brand marks are `static.ui.com/asn/{asn}_{size}.png`**, keyed on the
  `asn` that `stat/health` reports beside `isp_name`. Sizes 257, 129, 101, 51
  and 25 square. There is no provider table and none is wanted: the ASN is the
  whole lookup.

  Unlike the `/fingerprint/` paths on the same host, a missing ASN or size
  returns a genuine 404 here, so absence is detectable. Do not carry the
  fingerprint paths' "200 means nothing" assumption over to this one.

  This was hunted through the web bundles for a long time and was never there.
  It was found in one grep of a **support file's own logs**: the speed-test
  daemon logs the URL it builds as `ispImg`. The bundle search is on the
  do-not-repeat list further down and should have been abandoned much earlier
  for a search of data the device had already written down.
- **The Internet node falls back to a locally drawn cloud**, not to a bare
  polygon. `_render_cloud()` is a few Pillow ellipses and a bar, ours rather than
  Ubiquiti's, so it needs no network and raises no licensing question. Every
  circle's lowest point sits exactly on the baseline; a puff reaching past it
  leaves a lump hanging off the flat bottom edge.
- **`--obfuscate` drops the ASN**, alone among the artwork keys. `sysid`,
  `dev_id` and `oui` all survive because they say what hardware *is*; an ASN says
  who the owner buys transit from, and drawing the provider's logo on a map
  meant for publishing would give the game away no matter what the label said.
  The icon dict is built before `obfuscate()` runs, so `cmd_render` also swaps
  the mark for the cloud; clearing `Node.asn` alone is not enough.
- Artwork must degrade: no network, no Pillow, or unknown hardware all fall back
  to the shape renderer rather than failing the run.

## Rendering constraints

- **Don't switch `--layout sane` edges to `splines=ortho`.** It looks tidier but
  Graphviz cannot place edge labels on orthogonal routes, so port numbers drift
  far from their link and float beside unrelated nodes. `--layout unifi` *does*
  use ortho, and deliberately suppresses port labels for exactly this reason.
- **Edges are emitted parent → child, the reverse of how they're stored**, so the
  root lands at the top (TB) or left (LR) rather than trailing at the far end.
- **`--layout unifi` omits the title block and legend.** A graph label sets a
  minimum canvas width, which pads a tall narrow map with dead space on both
  sides. The UniFi UI has neither, so dropping them is faithful *and* tighter.
- **Stagger once, before rendering.** `_write_outputs()` applies `unflatten`
  then feeds the *same* DOT to the SVG render and the draw.io coordinate pass.
  Different DOT means draw.io positions disagree with the SVG.
- **`unflatten` reformats the file.** It re-tabs and drops trailing semicolons,
  so `sed`-style patches against generated `.dot` files silently no-op. Change
  `render_dot.py` instead.
- **Graphviz identifiers cannot contain a raw MAC.** DOT reads `:` as a port
  specifier, so `_node_id()` strips colons; `render_drawio.py` reuses it so
  layout lookups line up.
- **Graphviz `<IMG SRC>` needs a filesystem path**, not a data URI.
  `svg_post.inline_svg_images()` rewrites those paths into data URIs afterwards,
  restricted to the icon cache dir so a crafted device name cannot pull in
  arbitrary files.
- **draw.io wants `data:image/png,<base64>`**: comma, *not* `;base64,`.
- **`mxGeometry` needs `as="geometry"`.** `as` is a Python keyword and cannot be
  a `SubElement` kwarg; `_geometry()` sets it afterwards. Without it draw.io
  silently ignores every position and piles all shapes at the origin.
- **Size icon cells to the real aspect ratio** via `IconAsset.display_size()`.
  Rack switches are wide and short; a square cell letterboxes them into a thin
  strip surrounded by dead space.
- **Colour is never the only channel.** The accent palette is Okabe-Ito and every
  distinction is also carried by artwork, shape or line style. Don't add a
  red/green pair that carries meaning alone.
- **Never invent a product match.** `AssetStore.sysid_for_name()` is how UniFi
  hardware appearing as a client gets artwork, and it returns a match only when
  exactly one catalogue entry matches. `g3-flex` genuinely matches both
  `UVC-G3-FLEX` (Protect camera) and `UA-G3-Flex` (Access reader), so ties are
  broken with a device type from another app (Protect's camera list), never by
  preference or ordering. Ambiguous stays ambiguous and falls back to the glyph.
- **`stat/sta` is not the whole graph.** It reports a client's uplink only when
  that uplink is a UniFi device, so anything behind a non-UniFi box has no
  `sw_mac`. `topology_uplinks()` reads the controller's own `v2` graph, where a
  CLIENT can be another client's uplink, and `_place_remaining()` runs after every
  client exists because an uplink is frequently another client. This was missed
  for a long time: the placeholder node was blamed on the controller when the
  data was in an endpoint already being fetched and ignored. Check the console
  against the output before concluding the controller does not know something.
- **Never invent topology.** Clients whose uplink the controller doesn't report
  get anchored to `UNKNOWN_UPLINK_ID`. Don't guess a plausible parent switch.
- **`Topology.infrastructure` includes `Kind.UNKNOWN`** so that placeholder
  survives per-network filtering. Removing it re-orphans those clients.

## Defaults reproduce the UniFi web view

`--icons unifi --layout unifi --theme light` is chosen so the tool matches what
the console shows out of the box. Don't change a default to something "better
looking" without a reason; the point is fidelity first, with `sane` available
for readability.

The single deliberate exception is `--show-offline no`: the UI offers no way to
hide stale hardware, which was specifically wanted. `build_topology()` still
defaults `include_offline=True` (a library shouldn't drop data silently); only the
CLI flips it.

When excluding offline devices, they are left out of `device_macs` too, so the
uplink pass must skip any device not in `topo.nodes`; indexing it directly was a
real KeyError.

## `--layout unifi` is an approximation, and the docs say so

It is deliberately not claimed to be pixel-identical to the controller UI:
Graphviz owns the layout, so sibling order and spacing are its decisions, link
routing differs in its corners and channels, typography and label content are
ours, clients fall back to shapes because the client fingerprint icon database
is not reachable, and the output is static. The README has a section spelling
this out. Keep improving fidelity if you like, but do not let the documentation
start implying an exactness that is not there.

## Whether `unifi` layout is narrower than `sane` is data-dependent

It is on a real network with many sibling clients (1305pt vs 4648pt observed),
and inverts on a small fixture where tree depth dominates. Don't assert it.

## Demo dataset

`examples/demo/` is generated by `scripts/make_demo_snapshot.py`; edit the
script, not the JSON. MACs use the locally-administered `02:` prefix and
addresses are RFC 1918, but the **sysids are real** because that is the artwork
join key; fake ones would leave the demo unable to show icons. `tests/test_demo.py`
enforces both of those properties. The dataset intentionally includes an offline
device, four VLANs, and an unplaceable client so those behaviours are visible.

## Overrides

Implemented end to end: schema, loader, `resolve()` and `apply()`. Notes:

- `resolve()` tries MAC, then IP, then label. Unmatched or ambiguous is a loud
  error, never a silent no-op.
- `apply()` works on a copy and returns an `ApplyResult` carrying counts, the
  hidden labels and any user-supplied icons, so the CLI can report what happened
  rather than guess.
- **Order matters.** Links and nesting are applied before hiding, so hiding a
  node that an override just gave a child is correctly refused.
- Hiding is leaf-only by design. Do not add child-reparenting; there is no
  honest answer to what should happen to them.
- Asserted edges carry `Edge.asserted` and render dotted in both backends. Keep
  them visually distinct from observed links.
- User artwork is loaded through `assets.local_icon()`, which raises rather than
  falling back, and override icons are merged over looked-up ones in the CLI.

## Open work

Restored after being deleted by accident in 9b18a1a, where a section replacement
spanned two headings and took this with it. If you replace a range between
headings, check what was in between.

- **Infrastructure view.** A rack/cabling-style view of gateway, switches, APs
  and uplinks, separate from the client topology. `--no-clients` approximates it.

- **Decide what "making a release" actually means here.** Today it is: edit
  `__version__`, write the CHANGELOG entry, tag, push, mirror. That is a version
  bump, not a release, and the gap is worth closing deliberately rather than by
  accident. Questions to answer, roughly in order of how much they change:

  - **Is installation meant to be `pip install unifi-map`?** Right now the only
    documented install is a git clone plus `pip install -e .`. Publishing to
    PyPI is the single biggest decision, because it implies owning a name,
    keeping metadata honest, and never breaking a published artifact. If the
    answer is no, say so in the README so people stop wondering.
  - **Should the tag build anything?** `[project.scripts]` already declares a
    `unifi-map` entry point and the backend is plain setuptools, so `sdist` and
    `wheel` need no new machinery. A tag-triggered workflow could attach both to
    a GitHub Release. CI currently only runs on push to `main`, so it would need
    a `tags:` trigger.
  - **Are release notes duplicated?** A GitHub Release body and the CHANGELOG
    entry say the same thing. Generate one from the other rather than writing
    both by hand and letting them drift.
  - **What is checked before a tag?** At minimum `make check`, that
    `__version__` matches the CHANGELOG's newest heading, and that the heading
    is not still `Unreleased`. A version bumped without a CHANGELOG entry is the
    likely mistake and is cheap to catch.
  - **Reproducibility.** Graphviz is a system dependency, so the wheel is not
    self-contained. Decide whether that is documented (it is, in Install) or
    whether a container image is wanted.

  Write the outcome down as a short `RELEASING.md` rather than leaving it in a
  maintainer's head; that is the actual deliverable.

- **A man page, generated from the source rather than written twice.**
  `build_parser()` in `cli.py` is already the single source of truth for every
  flag and its help text, so the man page should come from it. Hand-writing one
  guarantees it goes stale, which is worse than not having one.

  Likely approach: `argparse-manpage`, which imports a parser and emits roff,
  and can be wired to `build_parser` directly. `help2man` is the lower-effort
  alternative but shells out to `--help` and produces a flatter result.

  Two things matter more than the tool choice:

  - **Generate it in `make` and fail if it is stale.** The pattern to copy is
    the sibling `cyberpower-prometheus-exporter` repo, whose `make check`
    regenerates its docs then runs `git diff --exit-code`. Without that the
    generated file drifts exactly like a hand-written one would.
  - **Decide whether the page is committed.** Committing it makes it visible and
    reviewable in diffs, which is the reason to prefer it; generating at build
    time keeps the tree clean but means nobody notices when help text becomes
    unreadable as a man page.

  Note that argparse help strings are currently written to read well in a
  terminal. Some will want rephrasing once they appear as a formatted page, and
  the long explanations in the README (support files, the glyph font, the three
  artwork routes) belong in a `DESCRIPTION` section rather than as flag help.

Done since this list was last accurate: overrides are applied rather than only
parsed, CI exists, obfuscation exists, `SECURITY.md` and `CONTRIBUTING.md` and
the issue and PR templates were written, clients behind non-UniFi devices are
placed from the controller's own graph, `--support-file` is implemented, and
0.2.0 is released.

**The GitHub repository description is set**, and matches `pyproject.toml`.
Verified against the API rather than assumed, because it is a setting rather
than a file and so cannot be seen from a checkout. Check it the same way before
listing it as outstanding again:

```bash
curl -s https://api.github.com/repos/gitkodak/unifi-map | jq -r .description
```

## `--support-file` is a second input, and loses almost nothing

`support.py` reads a console support file into the same `Snapshot` the API
produces, so nothing downstream knows the difference. Verified against a live
fetch of the same network: identical infrastructure (7 AP, 1 gateway, 3 switch),
identical wireless client count, one extra wired client live because the archive
was an hour older. Only client *product* artwork is lost.

The seven members read, and nothing else:

| Member | Stands in for |
| --- | --- |
| `unifi/devices.json` | `stat/device`, including `sysid` |
| `unifi/topology.json` | the v2 topology graph |
| `unifi/infrastructure.json` | `stat/health` WAN, via `ispData` |
| `system/run/dnsmasq.lease` | client addresses |
| `system/network/ip-neigh` | client addresses, statically assigned |
| `system/network/dpi-util-fprint-stats` | addresses of last resort, and fingerprints |
| `unifi-protect/cameras/cameras.json` | Protect's camera list |

Three earlier conclusions here were wrong, all from not looking hard enough:

- **Network names are recoverable**, from the *gateway's* `network_table` in
  `devices.json`, which carries the same `_id`/`name`/`vlan`/`ip_subnet` as
  `rest/networkconf`. All five LANs matched the live endpoint exactly. It is
  `setting.json` that is useless: its contents are `**dynamic-hidden**`. Live
  `networkconf` additionally returns the WAN and VPN networks, which
  `network_table` omits and no client belongs to.
- **Client addresses are recoverable**, from the DHCP lease file plus the
  neighbour table, which between them covered 43 of 47 clients. Neither is under
  `unifi/`, which is why the first pass declared them absent.
- **Client fingerprints are recoverable**, from the client's own name; see
  below. Two passes concluded otherwise. The first missed
  `system/network/dpi-util-fprint-stats` entirely, though it sat in a manifest
  already generated, because the greps covered `lease|dhcp|client|arp` and never
  `dpi` or `fprint`. The second found that file and stopped there, having
  decided the answer was "a fingerprint field, or nothing". The thing that
  worked was grepping for a **known `dev_id` value** and for known MACs, rather
  than for the name of the thing being looked for.

That last file needs care rather than enthusiasm. It is the gateway's live DPI
engine, and `ml.deviceNameID` is genuinely the same id space as `dev_id`, but it
is an inference with its own `confidence`, not the controller's settled answer.
Hence `MIN_FINGERPRINT_CONFIDENCE = 80`: its address is trusted freely, its
fingerprint only when the gateway is sure. It added no addresses at all on the
network it was developed against (all 38 of its hosts already had one), and it
is kept only because a network with a thin lease file may differ.

### Client artwork comes from the name, not from a fingerprint field

The real join is that **the console names an un-aliased client
`"<product name> <last two MAC octets>"`, and that product name is the
fingerprint catalogue entry it resolved to.** The fingerprint is therefore
present in the archive as text. `_dev_id_from_name()` reverses it: 12 clients
resolved, 0 wrong.

The strictness is load-bearing. The trailing octets must genuinely be that
client's, which is what proves the console generated the name rather than a
person, and the remaining text must equal exactly one catalogue entry. A looser
substring rule was measured first and got 8 of 11 right, mapping a human-named
`RokuUltraGreatRoom` onto `Roku Ultra` when the controller said `Roku Device`.
Do not relax this back to containment.

This needs the fingerprint database, which the archive lacks. **Ubiquiti publish
it**, at `static.ui.com/fingerprint/0/devicelist.json`
(`CLIENT_CATALOG_URL`), so no controller is involved. 13 of 47 clients drew real
product artwork on a completely cold cache with no console contact, and all 13
matched what the controller reports.

Two rules follow, and they pull in different directions:

- **It must stay controller-free.** Support-file mode exists precisely so people
  who will not point this tool at their console can still use it, so anything
  reintroducing an API dependency defeats it.
- **It must stay opt-in.** `AssetStore.fingerprint_db()` takes `download=False`
  by default and the CLI gates it behind `--fetch-fingerprints`, because the
  same person who declines to touch their console will not expect an unasked
  request to a CDN either. A cache that already exists is read regardless, since
  that is not network access. Never vendor the database; it is Ubiquiti's, like
  the artwork.

**The icon font is a genuine dead end.** The four generic client glyphs come
from `manage/angular/<build>/fonts/ubnt.ttf`, a custom Ubiquiti IcoMoon build
(note the `?6vxos8` cache-buster) served only by a controller. It is nowhere in
a support file, and `cdn.pkg{,.dev}.svc.ui.com/unifi-network-ui/<version>/...`
returns 403 for every path including a deliberately bogus control. So a
support-file map without a controller draws unfingerprinted clients as shapes,
which is the documented degradation and is fine. Do not vendor the font either.

Dead ends already checked, do not repeat: `mca-dump.fingerprints.hosts` carries
`custom`, `ml` and `tdts` per host, but only `ml` shares the controller's id
space (three Rokus show `tdts=292` where the controller says `27`), and it adds
no coverage over the DPI file. `dpi-flow-stats` log lines
(`fp ml for mac: ... [Name - id]@n%`) hold the ML top-3 but cover only 16 MACs
and are logs. Guessing CDN paths does not work:
`static.ui.com/fingerprint/{0/,}{public,index,devices,fingerprint}.json` all
return the same 19177-byte marketing page, as does a deliberately bogus path, so
always check a control before believing a 200. `devicelist.json` was found by
grepping the *support file's own logs* for `https?://.*fingerprint.*`, after
guessing had failed twice; `static.ubnt.com` serves it identically.

Reading Protect's camera list keeps the other case that matters: UniFi hardware
sitting on a switch port as a client still resolves its artwork, because the
camera/Access-reader ambiguity can still be broken.

Constraints worth keeping:

- **Never extract the archive.** It is ~150 MiB over ~2500 entries and mostly
  logs, including per-client remote logs. It is read as a `r|gz` stream, decoded
  into memory, and the wanted members are picked off as they go past.
- **It is attacker-supplied.** The whole point is that a stranger can send you
  one to reproduce a bug, so members are size-capped and anything that is not a
  regular file is skipped.
- Port numbers come from `uplinkPortNumber`, the port on the uplink device.
  `downlinkPortNumber` is the client's own interface and is absent on client
  edges; taking it would silently drop every port label.
- `devices.json` is a list of one object per site, plus a `super` pseudo-site
  that is always empty. Multi-site archives pick the largest and say so.

## Data hygiene

`cache/` and `out/` are gitignored; snapshots are written `0600`. A snapshot is a
full MAC/hostname/IP inventory. Never commit one or paste it into an issue.
