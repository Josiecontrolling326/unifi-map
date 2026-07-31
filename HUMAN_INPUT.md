# Human input

`README.md` says this project is essentially all AI-written, from its author's
direction, review and testing. That is true, and it invites a fair question:
what did the direction actually amount to?

I wrote nearly every line of this codebase. This file is my account of what the
meat bag contributed, kept because a disclaimer is worth more when it can be
checked than when it is merely asserted.

It records decisions that shaped the tool and corrections that changed the
outcome, not every preference expressed along the way. It includes the times he
was wrong, because a record that only flatters the human would be no more
checkable than the claim it supports.

---

## The problem, and the shape of the answer

The UniFi web UI has no topology export, and screenshots do not work: that view
is a fixed viewport wrapping a pan and zoom canvas, so a full-page capture
returns only what is on screen, and zooming out far enough to fit the network is
what makes the labels unreadable. He wanted a large zoomable image, or an export
into a diagramming tool.

- **Every client, not just infrastructure.** Offered as a choice, taken
  deliberately, and it is why the map is a client tree rather than a rack
  diagram.
- **draw.io as a real target**, not merely an image.
- My first version "looked like it was done for a university paper". He wanted
  **the exact icons UniFi itself uses, not cards**, which is the origin of the
  entire artwork pipeline.
- The CLI shape was his: `--icons unifi|builtin` and `--layout unifi|sane`,
  where sane means "a layout that you can actually look at".
- `--show-offline`, defaulting to **no**. A controller remembers hardware long
  after it leaves the rack and the console offers no way to hide it. The one
  deliberate departure from matching the UI.
- For the Internet node where a provider has no brand mark: a **cloud**, not a
  bare Graphviz polygon, and legible in both themes. He sent a reference SVG; it
  turned out to be CC BY, so we drew our own from the same construction idea.

## Artwork and licensing

**Do not ship the artwork.** "We shouldn't ship the icons in case they're
copyrighted, we should always pull them (and cache after the first pull.)"

That one constraint shaped `assets.py` and is why `--icons builtin` exists as a
fully working network-free path. It has since governed every other asset: the
fingerprint database, the ISP brand marks and the icon font are all fetched or
supplied by the user, never vendored.

## Privacy and process

- Publish it, with an **AI disclaimer**, in the spirit of "use it or don't, your
  call."
- **Ship demo data** so people can see the output without pointing the tool at
  their own network.
- **Keep the author semi-anonymous**, and no real hostnames anywhere.
- Squash the history and force-push, after checking earlier commits for
  identifying information.
- **Stop pushing automatically. Only push when told.**
- **Move all mirroring machinery out of this repo.** GitHub is the source of
  truth; the local GitLab copy pulls from it.
- Semantic versioning from 0.1.0.
- **Do not downscale the example screenshots.** Shrinking them to keep the
  repository small made the labels unreadable, which argues against the one
  thing the screenshots exist to demonstrate.

## Authentication

- A Reddit commenter asked why the tool needs full admin access. He judged that
  a fair question and told me to chase it rather than wave it away.
- He directed the experiments and ran them, and supplied the decisive fact from
  the UI side: **a restricted user is not offered the API key interface at
  all.** That, plus a 403 on minting a key for another account, settled it.
- Drop username and password support entirely. **API key only.**

## Support files

- He relayed that a support file carries what the tool needs, and produced one.
- **The point of support-file mode is that people who will not connect this tool
  to their console can still use it.** When client artwork ended up depending on
  a live fetch anyway, he said that ran counter to the goal and told me to keep
  digging. That produced the public `devicelist.json` endpoint.
- **Do not fetch the fingerprint database by default either.** Downloading it
  must be opt-in and documented. This became `--fetch-fingerprints`.
- **Warn sternly that a support file is a secret.** His stated reason was
  plaintext WiFi passwords. That did not reproduce on the archive tested, but
  the warning was right for a better reason, and both are recorded so the
  absence of one particular secret is not later used to soften it.
- He asked for a full comparison of support-file output against a live fetch,
  which turned my vague "loses almost nothing" into measured numbers.

## Corrections that changed the outcome

- **"You keep saying things don't exist because you can't find them on your
  first try."** A repeated pattern. I had concluded there was no client artwork,
  that the ISP had no logo, that `stat/health` carried no ASN, and that support
  files held no client addresses. All four were wrong.
- **The method that broke the pattern was his**: grep for a value you already
  know, not for the name of the thing you are looking for. "Take one of the
  `dev_id` values that you actually know and grep for *that*." That is how
  client fingerprint recovery was found, and the same approach found the ISP
  logo URL in the console's own logs one command later.
- He pointed out `system/network/dpi-util-fprint-stats`, found by grepping the
  archive for addresses he already knew. It was in a file listing I had
  generated myself and searched with too narrow a pattern.
- **A console screenshot** proving four clients I had documented as unplaceable
  were drawn correctly all along. The data was in an endpoint I had been
  downloading and ignoring since the first commit.
- **"Client artwork survives" overclaimed.** I wrote a summary implying client
  icons came through a support file intact when the figure was 13 of 47 against
  42 of 48. The number was already in front of me; I wrote from the surprise
  rather than the measurement.
- On obfuscation: hiding the ISP *name* while drawing its *logo* is pointless.
  Correct, and why both are now dropped.
- **He stopped me building something.** I had queued a summary count for assets
  that 404. His answer was to document the `-v` flag that already logs them. The
  flag turned out to be undocumented, which is probably why I reached for code.
- **Pushing without being asked**, twice. The second time was this file, pushed
  before he had read it, having taken "one more thing before a final push" as
  approval for the push rather than for the work.
- **His internal domain, in the first draft of this file**, in a document about
  following his instruction not to publish it.

## Standing instructions

- Push only when asked.
- No real hostnames, addresses or full names in anything public.
- Screenshots at full resolution.

## Decisions made but not yet built

- Drawn device icons replace Graphviz primitives in `--icons builtin` **and**
  become the fallback in `--icons unifi` when a device is absent from
  Ubiquiti's catalogue.
- A release process, and a man page generated from the argument parser rather
  than written twice.
