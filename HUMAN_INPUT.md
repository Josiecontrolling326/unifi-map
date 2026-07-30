# Human input

`README.md` says this project is essentially all AI-written, from its author's
direction, review and testing. That is true, and it invites a fair question:
what did the direction actually amount to?

I wrote nearly every line of this codebase. This file is my account of what the
meat bag contributed, kept because a disclaimer is worth more when it can be
checked than when it is merely asserted.

It includes the times he corrected me, which are the most useful part, and the
times he was wrong, because a record that only flatters the human would be no
more checkable than the claim it is meant to support.

---

## The original problem

The UniFi web UI has no topology export, and screenshots do not work: that view
is a fixed viewport wrapping a pan and zoom canvas, so a full-page capture
extension returns only what is on screen, and zooming out far enough to fit the
network is exactly what makes the labels unreadable. He wanted a large zoomable
image, or an export into a diagramming tool.

Decisions at the outset:

- **Everything, not just infrastructure.** Every client on the map. Offered as a
  choice, taken deliberately.
- **draw.io as a real target**, not merely an image.
- Credentials belong in an env file, and eventually in a secrets manager he
  runs. Not done yet; he asked to be reminded.

## Look and output

- My first version "looked like it was done for a university paper". He wanted
  the real thing: **the exact icons UniFi itself uses, not cards.**
- **Do not ship the artwork.** "We shouldn't ship the icons in case they're
  copyrighted, we should always pull them (and cache after the first pull.)"
  That one constraint shaped `assets.py`, and it is why `--icons builtin` exists
  as a fully working network-free path.
- The CLI shape was his: `--icons unifi|builtin` and `--layout unifi|sane`,
  where sane means "a layout that you can actually look at".
- The `unifi` layout was padding a narrow map with dead space on both sides. He
  said that space could be cropped, which is why that layout drops the title
  block and legend.
- `--show-offline`, defaulting to **no**. A controller remembers hardware long
  after it leaves the rack and the UI offers no way to hide it. This is the one
  deliberate departure from matching the console.
- He pushed back on "actual product photo" as overstating what the artwork is.
- For the Internet node where a provider has no brand mark: a **cloud**, not a
  bare Graphviz polygon. He sent a reference SVG; it turned out to be CC BY, so
  we drew our own using the same construction idea.
- **Check the cloud is legible in both light and dark.** He had to ask twice,
  because my first answer did not address it.
- The README had grown long and dense. He asked for a **summary near the top**
  so nobody has to read the whole thing to decide whether to try it, with
  warnings cut down to one-line pointers into sections.

## Publishing, privacy and process

- Publish it for others, with an **AI disclaimer**, in the spirit of "use it or
  don't, your call."
- **Ship demo data** so people can see the output without pointing the tool at
  their own network.
- **Keep the author semi-anonymous.** No full name in the documentation.
- **No real hostnames anywhere.**
- Squash the history and force-push, after checking for earlier commits carrying
  identifying information. He named one specifically.
- **Stop pushing automatically. Only push when told.**
- **Move all mirroring machinery out of this repo.** GitHub is the source of
  truth; the local GitLab copy pulls from it, driven from a separate admin
  repository.
- Semantic versioning from 0.1.0. He later asked how it actually works, which
  produced the "when to bump" section in `CHANGELOG.md`.

## Authentication

- A Reddit commenter asked why the tool needs full admin access. He judged that
  a fair question and told me to chase it rather than wave it away.
- He directed the experiments and ran them: an API key created by a non-admin
  user, and a super admin attempting to mint one for another account.
- He supplied the decisive fact from the UI side: **a restricted user is not
  offered the API key interface at all.** That, plus a 403 on minting a key for
  another account, is what settled it.
- He asked for the finding to be documented, and to get ahead of the obvious
  follow-up, "why not use a regular user".
- Later: drop username and password support entirely. **API key only.**

## Support files

- He relayed that a support file carries what the tool needs, and produced one.
- **The point of support-file mode is that people who will not connect this tool
  to their console can still use it.** When client artwork ended up depending on
  a live fetch anyway, he said that ran counter to the goal and told me to keep
  digging. That is what produced the public `devicelist.json` endpoint.
- **Do not ship the fingerprint database either, and do not fetch it by
  default.** Downloading it must be opt-in and documented as such. This became
  `--fetch-fingerprints`.
- For the icon font, which genuinely has no public source: offer both routes and
  be explicit that one needs an API key. He supplied the on-disk location on a
  self-hosted controller, which checked out.
- **Warn sternly that a support file is a secret.** His stated reason was
  plaintext WiFi passwords. That specific claim did not reproduce on the archive
  tested, but the warning was right for a better reason, and both are recorded so
  the absence of one particular secret is not later used to soften it.
- He asked for a full comparison of support-file output against a live fetch,
  which is what turned my vague "loses almost nothing" into measured numbers.

## Corrections that changed the outcome

- **"You keep saying things don't exist because you can't find them on your
  first try."** Accurate, and a repeated pattern. I had concluded there was no
  client artwork, that the ISP had no logo, that `stat/health` carried no ASN,
  and that support files held no client addresses. All four were wrong.
- **The method that broke the pattern was his**: grep for a value you already
  know, not for the name of the thing you are looking for. "Take one of the
  `dev_id` values that you actually know and grep for *that*." That is how
  client fingerprint recovery was found, and the same approach found the ISP
  logo URL in the console's own logs one command later.
- He pointed out `system/network/dpi-util-fprint-stats`, having found it by
  grepping the extracted archive for addresses he already knew. It was sitting
  in a file listing I had generated myself and searched with too narrow a
  pattern.
- **A console screenshot** proving four clients I had documented as unplaceable
  were drawn correctly all along. The data was in an endpoint I had been
  downloading and ignoring since the first commit.
- **"Client artwork survives" overclaimed.** I wrote a summary implying client
  icons came through a support file intact when the real figure was 13 of 47
  against 42 of 48. The number was already in front of me; I wrote from the
  surprise rather than the measurement.
- On obfuscation: hiding the ISP *name* while drawing its *logo* is pointless.
  Correct, and it is why both are now dropped.
- He caught that the GitHub repository description had been set for some time
  while it kept reappearing on my todo list, because a setting cannot be seen
  from a checkout.
- **Pushing without being asked**, twice. The first time it became a standing
  instruction. The second was this file, which I pushed before he had read it,
  having read "one more thing before a final push" as approval for the push
  rather than for the work.
- **His internal domain, in the first draft of this file**, twice. In a
  document about following his instruction not to publish it. He caught it
  quickly; it had to come back out of the branch history.

## Things he found or verified himself

- Reach the console through its Traefik hostname rather than a bare IP, because
  he had already configured it to obtain proper certificates.
- The console's own **infrastructure view**, supplied as a screenshot, which
  turned the vaguest item on the todo list into a specification.
- That UniFi lets you change a device icon in the console UI, and that a
  third-party device icon browser exists.

## Standing instructions

- Push only when asked.
- No real hostnames, addresses or full names in anything public.

## Decisions made but not yet built

- Drawn device icons replace Graphviz primitives in `--icons builtin` **and**
  become the fallback in `--icons unifi` when a device is absent from
  Ubiquiti's catalogue.
- Assets that 404 should not be silent at the default log level.
- A release process, and a man page generated from the argument parser rather
  than written twice.
