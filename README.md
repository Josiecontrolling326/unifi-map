# unifi-map

[![CI](https://github.com/gitkodak/unifi-map/actions/workflows/ci.yml/badge.svg)](https://github.com/gitkodak/unifi-map/actions/workflows/ci.yml)

Export a UniFi network topology as **zoomable vector diagrams** and **editable
draw.io files**, using real Ubiquiti product artwork.

The UniFi Network web UI has no topology export, and screenshots don't help: the
topology view is a fixed-size viewport wrapping a pan/zoom canvas, so full-page
capture extensions return only the visible region. Zooming out far enough to fit
the whole network is exactly what makes the labels unreadable.

So this doesn't scrape pixels. The UI draws that map from JSON endpoints on the
console; this pulls the same data and renders it properly.

![Example output: the demo network in the default UniFi layout, dark theme](docs/images/example-unifi-dark.png)

*The defaults, `--layout unifi --theme dark`, which approximate what the console
itself shows: left to right from the Internet, orthogonal links, and no title or
legend because the UniFi UI has neither. Note what a demo can and cannot show
here. The UniFi hardware carries its real artwork, because the dataset holds real
hardware ids, but most of the **clients** are invented and have no fingerprint, so
they fall back to plain shapes. Against a live network, expect nearly all of them
to resolve as well.*

![The same network in the readable sane layout](docs/images/example-sane-dark.png)

*The same data with `--layout sane`: top down, leaf nodes staggered to keep the
aspect ratio sane, port numbers on the links, and a title block and legend. On a
busy network this is usually the one worth handing to somebody else. Run
`make demo` to reproduce both, then point it at your own controller.*

## How this was built

Essentially all of the code here was written by an AI assistant (Claude), working
from my direction, review, and testing against my own network. 100% vibe-coded.
I decided what it should do and what "good" looked like; it wrote nearly every
line.

It works well for me. It has tests, and the design decisions have reasons behind
them. It has not been audited line by line by a human, and I'm not going to
pretend otherwise. It only ever reads from your controller (there is no code
path here that changes anything on it), but it does want admin credentials, so
read `client.py` if that matters to you. It's short.

Use it or don't, your call.

## Output

| Format | Why |
| --- | --- |
| `svg` | Vector. Zoom to any size, labels stay crisp. Artwork is embedded, so it's one portable file. |
| `pdf` | Vector, for printing. |
| `png` | Raster, when something insists on it. |
| `drawio` | Real editable shapes, pre-positioned with Graphviz's layout. Confirmed working in [draw.io](https://app.diagrams.net). Lucid also documents `.drawio` import, though that has not been tried. |
| `dot` | Graphviz source, to tweak styling by hand. |

## Install

```bash
sudo apt install graphviz          # provides `dot` and `unflatten`
python3 -m venv .venv && .venv/bin/pip install -e .
```

Requires Python 3.11+. Graphviz is required; `unflatten` is optional but
improves layout on large networks.

## Credentials

```bash
cp .env.example .env      # then edit
```

Or set `UNIFI_MAP_ENV=/path/to/credentials` to keep them outside the project.
Files are searched in order: `--env-file`, `$UNIFI_MAP_ENV`, `./.env`,
`~/.config/unifi-map/env`. Real environment variables always win.

```bash
UNIFI_HOST=unifi.example.com
UNIFI_API_KEY=...
UNIFI_SITE=default
UNIFI_VERIFY_TLS=true
```

| Variable | Required | Default | What it is |
| --- | --- | --- | --- |
| `UNIFI_HOST` | yes | | Hostname or IP of the console or controller |
| `UNIFI_API_KEY` | yes | | An API key (see below) |
| `UNIFI_SITE` | no | `default` | Which site to read (see below) |
| `UNIFI_VERIFY_TLS` | no | `true` | `true`, `false`, or a path to a CA bundle |

### `UNIFI_API_KEY`

Create a key in the UniFi OS settings, under the integrations section (the exact
wording moves between versions). This tool only ever reads, so read-only
permission is enough.

A key is the only supported credential. There is no login and no session, so
nothing has to be kept alive or refreshed.

A key inherits the permissions of the account that created it, and UniFi does not
appear to offer a narrower one. `SECURITY.md` explains why, what was tried, and
what this tool actually requests, which is ten GET requests and nothing else.

### `UNIFI_HOST`

Just the host, optionally with a port: `unifi.example.com`, `192.168.1.1`, or
`unifi.example.com:8443`. No path. A scheme is optional and `https://` is
assumed, so `unifi.example.com` and `https://unifi.example.com` are equivalent.

### `UNIFI_SITE`

A UniFi controller can manage several *sites* (separate networks under one
controller). If you have never created a second one, yours is `default` and you
can ignore this.

The catch is that this wants the site's **internal name**, which is not the
label shown in the UI. They are separate fields: on a single-site console the
internal name is `default` while the UI label is `Default`. On a controller
where you created and named sites yourself, the internal name is usually an
opaque short string that looks nothing like the name you typed.

Two ways to find the right value:

- **From the URL.** Open the site in the web UI and look at the address bar. The
  segment after `/site/` is the internal name.
- **Ask the controller.** `GET /proxy/network/api/self/sites` lists every site
  your account can see. Use the `name` field, not `desc`; `desc` is the UI label.

Only a single-site controller has actually been tested, so if you run several
sites and something looks wrong or empty, this variable is the first thing to
check.

### `UNIFI_VERIFY_TLS`

`true` (the default) verifies the certificate normally. Use `false` when you are
connecting to a bare IP, because consoles serve a self-signed certificate there
and verification will fail. Any other value is treated as a path to a CA bundle,
which is what you want if you terminate TLS with a private CA.

If you connect to a bare IP, set this to `false`:

```bash
UNIFI_HOST=192.168.1.1
UNIFI_VERIFY_TLS=false
```

### Alternative variable names

Every variable also answers to a `UDM_*` spelling, so an existing credential file
does not need renaming: `UDM_HOST`, `UDM_API_KEY`, `UDM_SITE`, `UDM_VERIFY_TLS`.
If both spellings are set, the `UNIFI_*` one wins.

`UNIFI_MAP_ENV` is not read from the credential file itself; it is the
environment variable that says *where* the credential file is.

Tested against UniFi Network 10.5.67 on a UDM Pro Max, with a single site.

## Try it without touching your network

A synthetic dataset ships in `examples/demo/`, so you can see the output before
pointing this at real infrastructure. No credentials, no controller:

```bash
make demo
# or:
unifi-map --cache-dir examples/demo --out-dir out/demo render --per-network
```

Every MAC, address and hostname in it is invented. Some identifiers are
deliberately real, because they are what artwork lookup joins on:

- **Hardware `sysid` values are real**, so every UniFi device in the demo draws
  its actual product artwork.
- **A few client `dev_id` values are real** (a laptop, a phone, a TV, a
  thermostat and so on), so those clients get real artwork too.

The rest of the clients are pure invention with no fingerprint, so they render as
plain shapes. That is the demo being honest rather than a defect: made-up devices
cannot have product artwork. The generic icon-font glyph is not available either,
because that font comes from a live controller. Against a real controller both
gaps close, and coverage is usually near total.

The dataset deliberately includes an offline device, four VLANs, and a client the
controller cannot place, so those behaviours are visible too.

Regenerate it with `make demo-snapshot` (see `scripts/make_demo_snapshot.py`).

## Usage

```bash
unifi-map all                              # fetch + render
unifi-map fetch                            # snapshot the controller into cache/
unifi-map render                           # render from the cached snapshot
unifi-map render --per-network              # one diagram per VLAN as well
unifi-map render --no-clients               # infrastructure only
unifi-map render -f svg pdf drawio dot      # pick formats
```

`fetch` and `render` are separate on purpose: you can re-render endlessly while
adjusting style without hammering the controller, and each cached snapshot is a
record of what the network looked like at that moment.

### What actually touches the network

Worth being precise about, because there are two caches and they behave
differently:

| Command | Controller | Artwork |
| --- | --- | --- |
| `fetch` | Always. Never checks the cache first, so it always overwrites the snapshot with current state. | Fetches the icon font if it is missing |
| `render` | Never. Reads whatever snapshot is in `--cache-dir`, however old. | Downloads any artwork not already cached, unless `--offline` |
| `all` | Always, because it is `fetch` then `render` | Same as `render` |

So `unifi-map all` does not skip the fetch when a cache already exists; it
refreshes unconditionally. If you want to re-render without going near the
controller, use `render`.

And `render` is not automatically offline. On a cold artwork cache it reaches
Ubiquiti's CDN for product images. Pass `--offline` to forbid that, or
`--icons builtin` to avoid needing artwork at all. Once the artwork cache is
warm, `render` makes no network calls in practice, but that is a consequence of
the cache being populated rather than a guarantee of the command.

### Style options

```bash
--icons unifi|builtin      # default: unifi
--layout unifi|sane        # default: unifi
--theme light|dark         # default: light
```

**Defaults reproduce the UniFi web view.** Out of the box you get what the
console shows you, just exportable and zoomable. The one deliberate exception is
`--show-offline`, below.

**`--icons unifi`** uses real Ubiquiti product artwork for both UniFi hardware
*and* clients (the same images the topology view shows). Fetched on first run and
cached. **`--icons builtin`** uses geometric shapes only: no network access, no
external assets.

**`--layout unifi`** approximates the UniFi UI: left-to-right tree, orthogonal
links, no port labels, no title or legend chrome, canvas trimmed to the drawing.
See below for how close that actually gets.
**`--layout sane`** is top-down with leaf staggering, port numbers on links, a
title block and a legend, built to actually be readable on a busy network. Try
both; on a network with many clients `sane` is usually the one you want to hand
to someone else.

### How close is `--layout unifi`?

Close, not exact. It won't look *exactly* like the controller UI, and it can't:
the tooling necessarily leaves its mark on the output. I've made my best attempt
to get as close as possible.

Concretely, what differs:

- **Graphviz does the layout, not UniFi.** The tree is connected the same way, but
  the order siblings appear in and the precise spacing are Graphviz's decisions.
- **Link routing is orthogonal but not identical.** Corners, channel spacing and
  where a line breaks are up to the renderer.
- **Fingerprints are sometimes wrong.** Client artwork comes from Ubiquiti's
  fingerprint database, and it misidentifies things (a phone shown as an
  appliance, that sort of thing). That is upstream data, not a rendering bug;
  correcting it is what the planned overrides are for.
- **Typography and label content differ.** This uses Helvetica/Arial and shows
  name, address and product name; the UI has its own font and its own idea of
  what belongs on a node.
- **It's a static picture.** No hover, no expanding and collapsing, no live state.

If you need the real thing, the real thing is in your browser. This is for when
you need it in a file.

**`--show-offline yes|no`** (default `no`) controls whether devices the
controller still lists but that aren't connected appear. This is the one place
the defaults deviate from the web view, on purpose: a controller keeps
remembering hardware long after it's been pulled from the rack, and the UI gives
you no way to hide it. Use `yes` to see everything yours still thinks exists.

Further knobs: `--legend` / `--no-legend`, `--title-block` / `--no-title-block`,
`--stagger N` (aspect-ratio control for `sane`), `--offline` (never touch the
network for artwork), `--title`, `--name`, `--out-dir`, `--cache-dir`,
`--asset-cache` (artwork cache, kept separate from snapshots).

## Reading the diagram

Colour is never the only signal. The accent palette is
[Okabe-Ito](https://jfly.uni-koeln.de/color/), chosen to stay separable under
red-green colour blindness, and every distinction is *also* carried by artwork,
shape, or line style, so the diagram survives greyscale printing.

| Element | Encoding |
| --- | --- |
| UniFi device | Real product artwork, matched on hardware `sysid` |
| Client | Real product artwork, matched on fingerprint `dev_id` |
| UniFi hardware appearing as a client | Its catalogue artwork, matched by hostname (see below) |
| Unrecognised client | A generic user/guest x wired/wireless glyph, the same fallback the UI uses |
| Client network | Border colour, plus the VLAN in the label |
| Wired link | Solid line |
| Wireless link | Dashed line |
| Offline device | Dashed border, `OFFLINE` in the label |

With `--layout sane`, edge labels are switch port numbers (`port 12`) or the
radio for wireless clients.

The legend only lists what a given render actually encodes. A node drawn as
artwork has no border and no fill, so it carries no accent colour and gets no
role swatch; its role is the artwork. Swatches appear only for roles that fell
back to shapes in that render, under "Without artwork". `--layout unifi` omits
the legend entirely, matching the UniFi UI.

### "Uplink not reported by controller"

You will probably never see this node, but it exists for the case where the
controller genuinely does not know where something is attached.

`stat/sta` only reports a client's uplink when that uplink is a UniFi device, so
anything behind a non-UniFi box (VMs and containers behind a NAS, or a client on
an unmanaged switch) comes back with no `sw_mac` at all. Those are resolved
against the controller's own topology graph, where a client can be another
client's uplink, which is how the console draws them correctly.

Anything still unresolved after that is anchored to an explicit placeholder,
rather than left floating (which looks like a bug) or attached to a guessed
parent (which would invent a connection that does not exist).

## Sharing a map: `--obfuscate`

A rendered map is not anonymous. Labels carry hostnames, addresses, VLAN names
and your WAN address, and an SVG holds all of it as selectable text. That makes
it awkward to ask for help with a layout problem.

```bash
unifi-map render --obfuscate --theme dark
```

![The same real network, obfuscated](docs/images/example-obfuscated-dark.png)

*A real network, obfuscated. Every device is a pseudonym, addresses are
renumbered, and the connections, roles and artwork are untouched. Note the four
clients hanging off one host near the middle: those are VMs behind a NAS, which
`stat/sta` cannot place and the controller's own graph can.*

**Replaced:** hostnames and device names, IP addresses, MAC addresses (including
the node identifiers in the DOT and draw.io output, which are derived from them),
network and VLAN names, SSIDs, the ISP name and the WAN address.

**Kept**, because otherwise the result is useless for the purpose: how everything
is connected, device roles, models and artwork, port numbers, counts, and which
clients sit on which network. Addresses are renumbered but stay grouped, so the
VLAN structure is still visible.

Pseudonyms are stable. The same device is `client-07` in every render of the same
snapshot, so a follow-up screenshot lines up with the first. They are assigned by
a fixed ordering rather than derived from the real name, since a hash of a short
hostname is trivially reversible.

### What it does not hide

Two things worth understanding before you post a map publicly:

- **The artwork still shows what your devices are.** A TV, a thermostat, a NAS
  and a games console are all recognisable from their pictures, and some carry
  brand marks. If that matters, add `--icons builtin` for geometric shapes and no
  artwork at all.
- **`--title` is yours.** If you pass a title containing your name or your
  network's name, it will be rendered exactly as given. The default is a neutral
  "Network map".

This runs on the model before anything is drawn, so no renderer can leak a value
that has already been removed. A test renders SVG, DOT and draw.io and asserts
that not one original hostname, address, MAC, network name or SSID appears in any
of them, because a mode that cleans one format and leaves another readable would
be worse than none at all.

## Manual overrides

Three things a controller cannot tell you, which you can state in an
`overrides.toml` (picked up automatically when it exists, or pass `--overrides`):

```toml
# A link the controller is not in the path of.
[[link]]
from = "nas"
to = "Rack Switch"
port = 10
speed = "10G"

# Something running inside something else.
[[hosted]]
guest = "build-runner"
host = "hypervisor"
note = "VM"

# A wrong fingerprint, corrected. Ubiquiti's database is confident and
# sometimes wrong: mine insists my network-attached bidet is a smart
# toothbrush.
[[node]]
match = "10.0.30.22"
name = "Network Bidet"
icon = "assets/bidet.png"

# Something you would rather not draw at all.
[[node]]
match = "Garage"
hide = true
note = "radios disabled on purpose, online but doing nothing"
```

Selectors are tried as a MAC address, then an IP, then the label on the map. One
that matches nothing, or several nodes, stops the run rather than being ignored.

Anything you assert is drawn **dotted**, and the legend says so, so a claim of
yours is never mistaken for something the controller reported.

Only leaf nodes can be hidden. Hiding a switch would orphan everything behind it,
and there is no honest answer to what should happen to the children, so it is
refused with an error naming them.

See [`docs/overrides.md`](docs/overrides.md) for the full format.

## Also planned

- **An ISP logo on the Internet node.** The controller already reports
  `isp_name` (the node is labelled with it, "Carl's Discount Internet & Tackle" rather than
  "Internet"), but no source for a provider logo has been located yet.
- **An infrastructure view** alongside the topology view: gateway, switches, APs
  and their uplinks presented as a rack/cabling diagram rather than a client
  tree. `--no-clients` is a rough approximation of this today.

## Artwork, licensing and attribution

This repository contains **no** Ubiquiti artwork. Device images are Ubiquiti's
intellectual property; they are fetched at runtime from Ubiquiti's public
endpoints and cached under `cache/`, which is gitignored. Nothing is
redistributed here.

If you'd rather not fetch anything, use `--icons builtin`.

UniFi and Ubiquiti are trademarks of Ubiquiti Inc. This project is not
affiliated with or endorsed by Ubiquiti.

The code is MIT licensed; see [LICENSE](LICENSE).

## How it works

### Where the artwork comes from

Three separate sources, none of them vendored here:

| What | Source | Key |
| --- | --- | --- |
| UniFi hardware | `static.ui.com/fingerprint/ui/public.json` + `.../ui/images/...` | hardware `sysid` |
| Clients | `static.ui.com/fingerprint/0/{dev_id}_257x257.png` | fingerprint `dev_id` from `stat/sta` |
| UniFi gear seen as a client | the same catalogue as UniFi hardware | hostname, plus a device type from another app |
| Generic client glyphs | the controller's own icon font (`fonts/ubnt-icon`) | user/guest x wired/wireless |

The client artwork endpoint is `staticFingerprintOld` in the Network UI's own
config. The controller also serves the fingerprint database itself at
`/proxy/network/v2/api/fingerprint_devices/0` (5789 devices), which is what turns
an unnamed client into "Govee H61E1 / Smart Light Strip".

Note that the controller does **not** host device images: every path under its
web app's static assets returns the SPA's HTML 404. Only the icon font is local.

### UniFi hardware that appears as a client

A UniFi device on a switch port that the Network app has not adopted (a Protect
camera, for example) is just a client: no fingerprint, so nothing to look up. Its
hostname is the only handle, and hostnames are ambiguous. `g3-flex` matches both
`UVC-G3-FLEX`, a Protect camera, and `UA-G3-Flex`, an Access door reader.

So the hostname is matched against the hardware catalogue, and a match is only
used when it is unique. To break ties, other UniFi apps are asked what they know:
if Protect reports that MAC as a camera, only camera entries are considered, and
`g3-flex` then resolves to exactly one. If a name stays ambiguous, the generic
glyph is used rather than a coin flip.

This needs no extra configuration. `/proxy/protect/integration/v1/cameras` is
fetched when present and ignored when Protect is not installed.

### Matching

Devices are matched to Ubiquiti's device catalog on **sysid**, not model name:
the controller's `model` string doesn't reliably match the catalog's shortnames
(a USW Pro HD 24 PoE reports `USWED72` while the catalog calls it `USPH24P`).

The graph is built from `stat/device` uplinks plus `stat/sta` and `networkconf`,
then completed with the controller's own `v2/.../topology` graph for clients the
first two cannot place. That endpoint is read defensively, since it is a v2 API
whose structure has changed before: anything unexpected in it yields nothing
rather than raising, so a controller upgrade degrades the map instead of breaking
the run.

## What has been checked, and what has not

Some of this is observed behaviour and some of it is reasonable inference. The
difference matters if you hit a problem, so:

**Checked directly**, against UniFi Network 10.5.67 on a UDM Pro Max:
authentication, every endpoint used, artwork lookup for both UniFi hardware and
clients, the icon font fallback, both layouts, both themes, all five output
formats, the offline and no-artwork paths, and opening the generated `.drawio`
in draw.io.

**Not checked:**

- **More than one site.** The test console has a single site. The advice above
  about internal site names comes from how UniFi behaves generally, not from
  something observed here, which is why it points you at the URL and the API
  rather than telling you what the value will look like.
- **Importing into Lucid.** Lucid documents `.drawio` import; that has not been
  tried with a file from this tool.
- **Any controller other than a UDM Pro Max**, or any Network version other than
  10.5.67. Older or newer controllers may move or reshape these endpoints.

If any of these turn out to be broken, that is a bug worth reporting rather than
a known limitation.

## Caveats

- Only **active** clients appear. A powered-off device isn't in `stat/sta` and
  won't be on the map.
- Wireless client counts drift between runs as devices roam and sleep. Two
  snapshots minutes apart won't match exactly; that's the network, not a bug.
- `cache/` holds a MAC, hostname and IP inventory of every device on your
  network. It's gitignored and written `0600`. Don't commit it or paste it into
  an issue.
