# Manual topology overrides

**Status: designed, not yet applied.** The schema and loader in
`src/unifi_map/overrides.py` are implemented and tested. Applying them during
rendering is not built yet: `apply()` raises `NotImplementedError`, and nothing
in the render path calls it. This document is the specification for that work.

## The problem

A controller can only report what it participates in, so two real relationships
are invisible to it:

**Links it isn't in the path of.** A NAS connected to a switch over a 10G SFP+
DAC often has no `sw_mac` in `stat/sta`. The renderer has nothing to attach it
to, so it lands under the "Uplink not reported by controller" placeholder.

**Nesting.** A VM or container appears as an ordinary client with its own MAC and
IP. Nothing in the data says it lives inside a particular hypervisor, so it is
drawn as a peer of the host it runs on, which is actively misleading.

**Noise that is technically online.** An access point whose radios you disabled
on purpose is still `state: 1` to the controller, so `--show-offline no` will not
remove it. It is not broken and it is not offline; it is just not doing anything,
and on a busy map that is clutter.

**Wrong identification.** Ubiquiti's fingerprint database is confident and
sometimes wrong, and a wrong fingerprint costs you twice: the client gets the
wrong name *and* the wrong artwork. A network-attached bidet reliably
identified as a smart toothbrush is not a rendering bug this tool can fix by
being cleverer; the upstream data says toothbrush.

None of this can be inferred safely. Guessing a plausible parent, or quietly
substituting a generic icon when the fingerprint looks improbable, would both
amount to inventing data. So the user states it.

## Format

TOML, because Python 3.11+ reads it from the standard library (`tomllib`), it
takes comments, and it's pleasant to hand-edit. No new dependency.

See [`examples/overrides.toml`](../examples/overrides.toml) for a working file.

### `[[link]]`

| Key | Required | Meaning |
| --- | --- | --- |
| `from` | yes | Selector for one end |
| `to` | yes | Selector for the other end |
| `port` | no | Port number, for the edge label. May be unquoted. |
| `speed` | no | e.g. `"10G"`, for the edge label |
| `note` | no | Free text |
| `wireless` | no | `true` renders the link dashed |

### `[[hosted]]`

| Key | Required | Meaning |
| --- | --- | --- |
| `guest` | yes | Selector for the nested node |
| `host` | yes | Selector for the node it runs on |
| `note` | no | e.g. `"VM"`, `"container"` |

### `[[node]]`

Corrects how a single node is presented.

| Key | Required | Meaning |
| --- | --- | --- |
| `match` | yes | Selector for the node to correct |
| `name` | no* | Replacement label |
| `icon` | no* | Path to artwork you supply |
| `hide` | no* | `true` drops the node from the map entirely |
| `note` | no | Free text |

\* at least one of `name`, `icon` or `hide` is required; an entry that changes
nothing is rejected rather than silently ignored.

```toml
[[node]]
match = "10.0.30.22"
name = "Network Bidet"
icon = "assets/bidet.png"
note = "UniFi is convinced this is a smart toothbrush"
```

#### Hiding a node

```toml
[[node]]
match = "10.0.20.99"
hide = true
note = "super-secret naughty server, not for the group chat"
```

Two reasons you might want this. One is noise: "online" and "actually
participating" are different things and the controller only reports the first, so
an access point whose radios you disabled on purpose is still `state: 1` and
`--show-offline no` cannot touch it. The other is discretion, for when the map is
going to somebody else and not everything on your network is their business.

**Only leaf nodes can be hidden.** Hiding a switch or an access point would orphan
everything behind it, and there is no good answer to what should happen to the
children (dropping them silently loses real devices, reattaching them to the
hidden node's parent invents a link that does not exist). So hiding a node that
has children is refused with an error naming the node and its children, rather
than guessed at.

Relative `icon` paths resolve against **the overrides file's directory**, not the
working directory, so a config and its assets folder can be moved together and
still work regardless of where you run the tool from.

Artwork you supply is never fetched or cached; it is read from where you put it.
Any image format Graphviz can load works; it is fitted to the same box and
aspect-ratio rules as fetched artwork.

### Selectors

`from`, `to`, `guest` and `host` accept a MAC, an IP, or a hostname/device name
as displayed on the map. Names rather than ids keep the file readable and mean a
device renamed in the controller only has to be corrected in one place.

## Remaining work

1. **`resolve(selector, topo) -> node id`.** Match a MAC exactly first, then an
   IP, then a case-insensitive label. An ambiguous or unmatched selector must be
   a loud error; a typo that silently does nothing is worse than a failed run.
2. **Hiding.** For each `node` with `hide = true`, refuse if the node has
   children, naming the node and its children in the error. Otherwise drop the
   node, the edge to its parent, and `UNKNOWN_UPLINK_ID` if nothing points at it
   any more. Report how many nodes were hidden rather than silently shrinking the
   map, so a too-broad selector is noticed.

   Worth considering as an alternative or complement: the controller reports
   per-radio state on an access point, so disabled radios may be detectable
   without the user saying anything. That would be inference rather than
   instruction, so it belongs behind its own flag if it happens at all, and it is
   not a reason to leave `hide` unimplemented.
3. **`apply(topo, overrides)`.** For each `link`, add an `Edge` and drop the
   node's anchor to `UNKNOWN_UPLINK_ID`; remove the placeholder once nothing
   references it. For each `hosted`, re-parent `guest` onto `host`. For each
   `node`, substitute the label and load `icon` as a user-supplied `IconAsset`,
   measured the same way cached artwork is so aspect ratio still drives cell
   size. A missing or unreadable `icon` file must be a loud error, not a silent
   fall back to the wrong fingerprint artwork.
4. **Distinct visual treatment.** A user-asserted link must never be mistaken
   for something the controller reported. Probably a dotted edge carrying the
   note. Containment should read as containment, not as a cable (a nested
   cluster, or a distinctly styled edge).
5. **CLI.** `--overrides PATH`, defaulting to `./overrides.toml` when present.
6. **Round-trip help.** A subcommand that emits the currently unplaced nodes, and
   clients whose fingerprint looks improbable, as a starter overrides file, so
   the user edits rather than writes from scratch.

## Design constraints

- **Overrides add, they don't silently rewrite.** If an override contradicts what
  the controller reported, say so rather than quietly preferring one.
- **Never invent topology.** This feature exists precisely so the tool doesn't
  have to guess. Its output must remain distinguishable from observed data.
- **A stale override should fail loudly.** Devices get replaced and renamed; an
  overrides file that no longer matches must complain, not degrade silently.
