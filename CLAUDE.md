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

- **ISP logo on the Internet node.** `wan_info()` reads `isp_name` from
  `stat/health`, so the node is already labelled ("Carl's Discount Internet & Tackle"). The logo is
  real: the UniFi infrastructure view renders a brand mark beside each WAN entry,
  a brand mark for the primary on WAN1 and another for the backup on WAN2 (in
  testing, Carl's Discount Internet & Tackle and Cruelty Cable Co.). Both are present, so
  expect a systematic lookup keyed on something like the ISP name or ASN, not a
  sparse hand-maintained table.

  Where it is *not*: searched `/275`, `/905`, `/989`, `/main~0`, `/main~2` and the
  legacy `/manage/` bundles for `isp*Logo|Icon|Image|Brand`, `/isp` URL
  templates, and carrier/provider logo identifiers. Only hits were
  `${NCA}/network-cloud/v2/isp-metrics`, an `/isp-viewer` route, and a legacy
  `ispThroughput.pug`. None of them build an image URL.

  What `images.svc.ui.com` turned out to be: a generic image resizing proxy,
  `https://images.svc.ui.com/?u=<source-url>&w=<px>&q=<quality>`, built by a
  shared `<img>` component in `main~2` that also takes `srcFallbackOffline` and
  `srcFallbackBundled`. It is not ISP-specific and resolves nothing on its own;
  the real logo URL has to arrive as data in the `u` parameter.

  The only ISP data reference in the bundles is
  `${NCA}/network-cloud/v2/isp-metrics`, a **cloud** endpoint, so the logo URL
  may well be cloud-provided. But the local `stat/health` WAN subsystem does
  carry an **`asn`** alongside `isp_name`, `isp_organization` and `wan_ip`, and
  an ASN is exactly the sort of key a brand-logo service keys on. That is
  available from a local API key, so do not write this off as cloud-only without
  testing it.

  Concrete next step: take the ASN from `stat/health` (a real one, not a
  documentation value) and see whether any
  Ubiquiti-hosted path resolves a logo from it, then feed whatever URL that
  yields through the `images.svc.ui.com/?u=...` proxy. If nothing local resolves
  it, only then treat cloud as the answer.

  Do not repeat: greps for `isp*Logo|Icon|Image|Brand`, `/isp` templates or
  carrier/provider identifiers across `/275`, `/905`, `/989`, `/main~0`,
  `/main~2` and the legacy `/manage/` bundles. Also do not look for a webpack
  chunk id-to-hash map; the React bundles do not expose one in the usual form.

- **Infrastructure view.** A rack/cabling-style view of gateway, switches, APs
  and uplinks, separate from the client topology. `--no-clients` approximates it.

- **A `--support-file` mode.** Evaluated and viable; see the support file section
  below for exactly which three files to read and what it would cost.

- **Repository description on GitHub.** Not a file, it is a setting, which is why
  it keeps getting forgotten. Keep it consistent with `pyproject.toml`:
  "Export your UniFi network topology as zoomable SVG, PDF, or an editable
  draw.io diagram, with real Ubiquiti device artwork."

Done since this list was last accurate: overrides are applied rather than only
parsed, CI exists, obfuscation exists, versioning started at 0.1.0, `SECURITY.md`
and `CONTRIBUTING.md` and the issue and PR templates were written, and clients
behind non-UniFi devices are placed from the controller's own graph.

## Support files could be a second input, and nearly work already

Someone suggested a UniFi support file carries what this tool needs. Inspected
one on 2026-07-30 (154 MiB, 2451 entries) and it very nearly does. Under
`unifi/`:

- `devices.json` holds the full device records for each site, 67 fields
  including `mac`, `model`, `sysid`, `type`, `uplink`, `port_table`, `ip` and
  `state`. That is `stat/device` in all but name, so device artwork would work.
- `topology.json` is the same graph as the v2 endpoint: vertices typed DEVICE or
  CLIENT, and edges carrying `downlinkMac`, `uplinkMac`, `type`, `essid`,
  `protocol` and `networkId`. Every connection, including client behind client.
- `infrastructure.json` carries `ispData` with the provider name, **asn** and
  WAN address, plus `gatewayMac` and `wanMode`.

What is absent, and what it costs:

- **Client records.** CLIENT vertices carry only `mac`, `name` and `type`. No IP
  address, no `dev_id`, no `network_id`, no `is_guest`. So clients would render
  with names and correct connections but no addresses and no client artwork.
- **Network names.** Edges carry `networkId`, so VLAN grouping still works, but
  the names would be opaque ids unless `setting.json` turns out to hold
  `networkconf` (its `site_settings` key was not inspected).

So a `--support-file` mode is worth building and would produce a genuinely
useful map, mostly losing client artwork and addresses. It also needs no
credentials, which makes it the obvious way for someone to share a real
topology for a bug report. Note the file is enormous and full of logs; read only
the three JSON files above and never extract the whole archive.

Incidentally `ispData.asn` is in there too, which is another route to the ISP
logo question.

## Data hygiene

`cache/` and `out/` are gitignored; snapshots are written `0600`. A snapshot is a
full MAC/hostname/IP inventory. Never commit one or paste it into an issue.
