# Changelog

Notable changes, newest first. This project follows
[semantic versioning](https://semver.org/).

**Pre-1.0 means the CLI is not stable yet.** Flags and defaults may change
between minor versions while the tool settles. Once there is reason to think the
interface is right, that becomes 1.0 and breaking changes need a major bump.

The version lives in `src/unifi_map/__init__.py` and `pyproject.toml` reads it
from there, so there is only ever one number to change.

## Unreleased

### Added

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
