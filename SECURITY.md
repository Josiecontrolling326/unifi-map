# Security

## Reporting

If you find something you would rather not discuss in public, open a private
security advisory through GitHub's "Report a vulnerability" button on the
Security tab. If that is unavailable, email sakodak@gmail.com.

Please do not open a public issue for anything that would expose someone's
network before they can update.

This is a hobby project maintained in spare time. Expect a reply in days rather
than hours.

## What this tool does with your credentials

It reads an API key from the environment or from a credential file, sends it in
an `X-API-KEY` header, and makes GET requests. That is the whole of it.

- `src/unifi_map/config.py` is the only module that reads the environment.
- `src/unifi_map/client.py` is the only module that talks to your controller.

Both are short. If you are evaluating whether to trust this, those two files are
the ones to read.

## It only ever reads

There is no code path that changes anything on your controller: no POST, no PUT,
no PATCH, no DELETE. The tool cannot adopt, restart, reconfigure or forget
anything, because it never asks the controller to.

## Scope of the API key, which is broader than this tool needs

Read this part before you create a key.

**A UniFi API key inherits the permissions of the account that created it.** It is
not scoped to the thing you made it for. Checking a key created under a super
admin against `GET /proxy/network/api/self` reports `is_super: true`, and a POST
with that key is rejected for having an invalid body rather than for being
unauthorised. In other words the key was allowed to write.

So although this tool only ever reads, **the credential you hand it can do more
than that**. That is a property of UniFi's key model, not a requirement of this
tool.

What follows:

- **Create the key under the least privileged admin account you can**, not under
  your super admin. The key is as powerful as the account behind it.
- **A key cannot be scoped, and the account probably cannot be either.**
  Inspecting keys through `GET /proxy/users/api/v2/user/self/keys` shows a
  `key_permissions` field that is empty on every key, alongside a `permissions`
  map reading `{"network.management": ["admin"]}` and a `scopes` list containing
  everything the account can do. Nothing populates the per-key field, so a key is
  simply the account that made it.

### Why this asks for more access than it uses

This is the obvious objection, and it deserves a straight answer rather than a
shrug. The short version: UniFi does not appear to offer a credential narrow
enough to match what the tool does, and the places you would expect to find one
each dead end.

**Read-only roles exist.** `GET /proxy/users/api/v2/roles` shows
`custom_administrator` roles carrying permissions like
`{"network.management": ["readonly"], "protect.management": ["readonly"]}`, which
is exactly what this tool needs. So the permission model can express it.

**But scoping only exists for admins.** There is no way to give a plain user
limited application permissions; you get there by making them an admin and then
restricting the admin. That is an awkward arrangement, and it is the reason the answer
to "why not just use a normal account" is not "you should".

**A key can only be created by the account that will own it.** This is enforced
by the platform, not merely hidden in the interface. A super admin can *read*
another user's keys through `GET /proxy/users/api/v2/user/{id}/keys`, but the
matching POST is refused outright:

```json
{"code": -5, "codeS": "CODE_OPERATION_FORBIDDEN",
 "msg": "Action not allowed.", "error": "cannot create api key for others"}
```

**And a restricted account cannot create one for itself.** Signed in as a
read-only user, the API key interface is not available. So that route closes too.

Putting those together, on the version tested there is no path to a read-only
API key at all:

1. Permissions can only be scoped by making the account an admin and then
   restricting it. There is no scoping for ordinary users.
2. A privileged account cannot mint a key on a restricted account's behalf. The
   platform refuses.
3. A restricted account cannot mint one for itself. The interface does not offer
   it.

That is not a design decision by this tool. It is the credential UniFi is
willing to issue.

**A regular, non-admin user is not a way out either.** Local-only accounts are an
admin concept. Creating an ordinary user means a cloud login, so you would be
maintaining an email address for the sole purpose of holding an API key, and it
is entirely untested whether the resulting key would even work against the local
API.

Ubiquiti's own community has an open thread asking for read-only API keys:
<https://community.ui.com/questions/Read-Only-API-key-yet/940e5b06-bc4d-4742-9760-cbb6f8882f60>

So the honest position is: **assume the key you give this tool carries the full
permissions of the account that created it.** Use a dedicated key rather than
sharing one, keep it in a secrets store if you have one, and revoke it rather
than rotating a password if it leaks. The tool's own behaviour is the part you
can actually verify, and it is one command away.

If you find a version or a path where a genuinely restricted key works, that is a
very welcome issue. The tool only reads, so it should work; nobody has been able
to construct the credential to prove it.

If you want to confirm the read-only claim rather than take it on trust, grep the
source for a mutating request:

```bash
grep -rnE '\.(post|put|patch|delete)\(' src/
```

That comes back empty. `src/unifi_map/client.py` is the only module that talks to
your controller, and it makes ten GET requests and nothing else.

## The data this produces is sensitive

This is the part people underestimate.

- **`cache/`** holds raw controller responses: a MAC address, hostname and IP
  inventory of every active device on your network, plus your WAN address. Files
  are written mode `0600` and the directory is gitignored. Do not commit one, do
  not attach one to an issue, and do not paste one into a chat window.
- **`out/`** holds the rendered diagrams. These are not anonymous either. Labels
  carry hostnames, IP addresses, your VLAN names and your public WAN address, and
  the SVG has all of it as selectable text. Think before sharing a render of a
  real network.

If you want to show someone what the output looks like, use the shipped demo
dataset (`make demo`). It is entirely synthetic.

When filing an issue, redact or use the demo data. Nobody needs your real
inventory to help you.

## Outbound network access

Beyond your controller, the tool fetches device artwork from Ubiquiti's public
endpoints (`static.ui.com`) on first use and caches it locally. Nothing is
uploaded anywhere.

To avoid that entirely, use `--icons builtin`, which draws geometric shapes and
touches no external host, or `--offline`, which forbids fetching and uses only
what is already cached.

## TLS

Certificate verification is on by default. `UNIFI_VERIFY_TLS=false` disables it,
which is sometimes necessary because consoles serve a self-signed certificate on
their bare IP address. Understand that this makes the connection
interceptable on an untrusted network. Pointing the tool at a hostname with a
valid certificate, or at a CA bundle path, is better where possible.

## What is not audited

Stated plainly, since it bears on how much you should trust this: most of the
code was written by an AI assistant under the maintainer's direction and testing.
It has tests, and the design decisions have reasons recorded in `CLAUDE.md`, but
it has not had a line-by-line human security review.
