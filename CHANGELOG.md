# Changelog

Notable changes, newest first. This project follows
[semantic versioning](https://semver.org/).

**Pre-1.0 means the CLI is not stable yet.** Flags and defaults may change
between minor versions while the tool settles. Once there is reason to think the
interface is right, that becomes 1.0 and breaking changes need a major bump.

The version lives in `src/unifi_map/__init__.py` and `pyproject.toml` reads it
from there, so there is only ever one number to change.

### When to bump

The version describes what a *user* would notice, not how much work happened.
Bump when releasing, not per commit: several commits usually make one version.

- **Patch** (0.2.0 to 0.2.1) for fixes and internal changes. Someone upgrading
  gets the same commands, the same flags and better behaviour.
- **Minor** (0.2.0 to 0.3.0) for anything new: a flag, an output format, a
  capability. Also, while pre-1.0, for changes that would otherwise be breaking,
  such as a renamed flag or a changed default.
- **Major** (0.x to 1.0, then 1.x to 2.0) once the interface is declared stable,
  for anything that breaks an existing invocation.

Below 1.0 the promise is deliberately weak: the leading zero says the CLI is
still settling. That is why a changed default is a minor bump here and would be
a major one later.

Refactors, docs and tests alone do not need a release at all.

## Unreleased

### Changed

- `SECURITY.md` no longer says "Nothing is uploaded anywhere" about artwork
  fetching. No body is sent, but the URLs carry `sysid`, `dev_id` and `asn`,
  which together disclose a partial hardware inventory to Ubiquiti's CDN. The
  section now says what is actually revealed and what is not.
- CI actions are pinned to commit SHAs rather than mutable tags, Dependabot
  keeps them and the Python dependencies moving, and a non-gating `pip-audit`
  job reports advisories.

### Fixed

- An API key is no longer visible to Graphviz or any other child process. It is
  never written into the process environment, and the environment passed to
  child processes has the key variables removed in case one was exported. Both
  Graphviz executables are now run by resolved absolute path rather than by
  name.
- draw.io labels are HTML-escaped. Every cell sets `html=1`, and draw.io decodes
  the XML attribute and then parses the result as HTML, so a device named
  `<img src=x onerror=...>` previously arrived as an element rather than as
  text. Device names are set by whoever named the device.
- The documented way to create a credential file is now `install -m 600` rather
  than `cp`, which inherited the umask and usually left an API key
  world-readable. `unifi-map` now warns when it reads one others can see.
- A real Ubiquiti device MAC in the test fixtures was replaced with a
  locally administered one.
- Rendering no longer overwrites a `.dot` or `.drawio` that this tool did not
  write. A hand-edited diagram is left alone, with `--force` to override.
  Re-rendering output it recognises as its own is unchanged and needs no flag.
- Output files are written atomically, so an interrupted or failed render leaves
  the previous file intact rather than a truncated one.
- The API key is no longer sent on if a redirect points at a different host.
  `requests` does this for `Authorization` and nothing else, and ours is a
  custom header. It mattered because `UNIFI_VERIFY_TLS=false` is documented as
  the ordinary setting for a bare IP, so with verification off anyone in the
  path could have redirected the tool and collected a working admin key.
  Redirects themselves still work, including on a reverse proxy.

### Added

- The Internet node now shows the upstream provider's brand mark, matched on the
  ASN the controller already reports beside the ISP name. Providers Ubiquiti have
  no mark for, and any map rendered with `--obfuscate`, get a plain cloud
  instead of a bare polygon.

### Changed

- `--obfuscate` also drops the ASN. It identifies the provider as squarely as
  the name does, and would otherwise redraw their logo on a map whose purpose is
  being safe to publish.

## 0.2.0 - 2026-07-30

### Added

- `--support-file` reads the topology from a UniFi support file archive instead
  of a controller. It needs no credentials and no network access, which makes it
  a safe way to share a real topology when reporting a bug. Add `--support-site`
  to pick a site from a multi-site archive.

  Against a live fetch of the same network it produced identical infrastructure
  and an identical wireless client count. VLAN names, subnets, switch port
  numbers, SSIDs, client addresses, the ISP name and Protect camera artwork all
  survive.

  Reading a support file makes no outbound request at all.

- `--icon-font DIR` loads the generic client glyph font from a copy you made
  yourself, needing neither credentials nor a network. `--fetch-icon-font` gets
  it from a controller instead, which does need an API key and says so. Without
  either, unidentified clients draw as plain shapes. Ubiquiti publish no copy of
  this font, so there is no route to it that avoids a controller, and it is not
  shipped here.

  Some client artwork is recoverable, opt-in via `--fetch-fingerprints`, but
  expect substantially less of it than a live fetch gives: 13 of 47 clients
  against 42 of 48 on the same network. A support file stores no fingerprint id.
  What can be reconstructed is the subset the console named *itself*, after the
  product it identified, since that name can be looked back up against
  Ubiquiti's published fingerprint database. The console only names a client
  that way when it sent no DHCP hostname and was never renamed, which is a
  minority. The database is about 1 MB, downloaded only when the flag is given,
  then cached.

- Manual overrides are now applied, not just parsed. `--overrides` (or an
  `overrides.toml` in the working directory) can add links the controller cannot
  see, declare that one node runs inside another, rename a device, supply your
  own artwork, and hide a node entirely.
- Asserted links are drawn dotted in both SVG and draw.io, and the legend gains
  a "Stated in overrides" entry, so a claim is never mistaken for an observation.
- `--version`.

### Fixed

- Artwork supplied through an override is now embedded in the SVG. It was being
  left as a filesystem path, which both broke portability and disclosed a local
  path, usually containing a username, even under `--obfuscate`.

- Clients behind a non-UniFi device are now placed correctly instead of being
  collected under "Uplink not reported by controller". `stat/sta` only reports an
  uplink when it is a UniFi device, so VMs and containers behind a NAS, or
  clients on an unmanaged switch, appeared unplaced. The controller's own
  topology graph knows where they are, and the console has been drawing them
  correctly all along. On the network this was found on, that node disappeared
  entirely.

## 0.1.0

First versioned release. The tool was already public and working before this
point; the version simply starts being tracked here.

### Output

- SVG and PDF, vector, so labels stay sharp at any zoom. Artwork is embedded in
  the SVG so it is a single portable file.
- `.drawio` with real editable shapes, positioned using Graphviz's layout.
  Confirmed working in draw.io.
- PNG, and Graphviz `.dot` for hand tweaking.
- Optional per-network diagrams, each keeping the full gateway, switch and access
  point skeleton so they read as slices of one map.

### Artwork

- UniFi hardware drawn with its real product artwork, matched on hardware
  `sysid` against Ubiquiti's device catalogue.
- Clients drawn with their real product artwork, matched on the fingerprint
  `dev_id` the controller already reports.
- UniFi hardware that appears as a client, such as a Protect camera on a switch
  port, matched by hostname against the hardware catalogue, disambiguated by
  asking Protect what the device actually is.
- Anything unrecognised falls back to the controller's own icon font glyph, the
  same fallback the UniFi interface uses.
- No artwork is vendored. It is fetched at runtime and cached, and
  `--icons builtin` needs no network at all.

### Presentation

- Two layouts. `unifi` approximates the console view; `sane` is top down with
  leaf nodes staggered and port numbers on the links.
- Light and dark themes.
- Okabe-Ito accent palette, with every distinction also carried by artwork, shape
  or line style so the output survives greyscale and red-green colour blindness.
- A legend that describes only what a given render actually encodes.

### Privacy

- `--obfuscate` replaces hostnames, addresses, MAC addresses, network and VLAN
  names, SSIDs, the ISP name and the WAN address, while keeping the connections,
  roles, artwork and port numbers that make a diagram worth discussing.

### Behaviour

- `--show-offline` defaults to `no`, because a controller remembers hardware long
  after it leaves the rack and the interface offers no way to hide it.
- Clients whose uplink the controller does not report are anchored to an explicit
  placeholder rather than left floating or attached to a guessed parent.
- The Internet node is labelled with the ISP name the controller reports.
- `fetch` and `render` are separate, so styling can be iterated without querying
  the controller again.

### Other

- Authenticates with an API key. The tool only ever reads; `session.get` is the
  only HTTP verb in the source.
- A synthetic demo dataset, so the output can be seen without pointing the tool
  at real infrastructure.
- Manual overrides: schema and loader only. Applying them is not implemented yet.
