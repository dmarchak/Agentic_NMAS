# Agentic NMAS — Network Source of Truth

**CSCI 5840 — Labs 4 & 5, Part 1**
Dustin Marchak

A Flask application that manages a nine-device Cisco lab (five IOS-XE routers,
four vIOS-L2 switches) as a **Network Source of Truth**: intent is committed to
git, configuration is rendered from templates, every push is confirmed against
an exact command list, and every golden capture is a commit with a tag.

Nine devices. 1,776 tests, none of which touches a live network. 198 commits.

---

## 1.1 Version control

**Every golden configuration is a git commit.** `data/lists/<slug>/config_repo/`
is a real repository per device list: `golden/<device>.cfg`, `host_vars/`,
`templates/`, and `.nsot/manifest.json`.

- **One write path.** Everything that promotes a golden goes through
  `nsot.repo.save_golden()`. **One call is one commit**, so a nine-device
  "Save All" produces one commit, not nine.
- **Identity, not filename.** The manifest keys each device on `nb:<netbox_id>`
  or `uid:<uuid4>`, so a rename is a `git mv` committed alone — which is what
  keeps `git log --follow` working across it.
- **Timestamps live in git, not in the file.** The `! Saved:` header was removed
  because it produced a diff on every save. Commits carry `Source`, `Actor`,
  `Device-Id` and `Device-Name` trailers.
- **A private GitHub remote**, per list, adopted rather than assumed. Before the
  first push the history is scanned for secrets and the operator must
  acknowledge what it found; auto-push is a separate, gated decision that cannot
  widen what is published without a person.

[SCREENSHOT: the Git tab showing the golden repo commit log, with a Save All commit listing several devices and its `golden/<device>/<ts>` tags]

[SCREENSHOT: the Remote card on the Golden tab — verified private remote, the history-scan acknowledgement, auto-push enabled]

**What the history contains.** The first push to `dmarchak/rcn-nsot-config` was
61 commits and 33 tags. The scan found only dead credentials plus nine
read-only, ACL-restricted SNMP communities, each acknowledged explicitly before
publishing. Golden configs are stored **verbatim** and masked on the way *out*
instead — masking them at rest would make `golden/` depend on `data/key.key`,
which is not in the repository, so a private remote would hold configs nobody
could restore a network from.

---

## 1.2a GUI with monitoring and device input

### Monitoring — the Integrations panel

The Monitoring tab now opens with one read-only card per tool in the lab's
stack: **NetBox** (device and site counts), **Prometheus** (targets up/total,
naming the ones that are down), **Loki** (recent log lines), **Oxidized**
(per-device last fetch status and time), **Kea** (active leases), **Grafana**
(reachable, plus a link).

Two design points that were forced by the deployment rather than chosen:

- **Everything is fetched server-side.** The browser reaches NMAS through a
  Cloudflare tunnel; the tools are LAN-only. A browser-side `fetch` or an
  `<iframe>` works on the console at the lab host and shows nothing at all to a
  remote viewer.
- **One endpoint per tool, not one for all six.** An aggregate endpoint takes as
  long as its slowest member and fails as a unit — the exact behaviour the panel
  exists to avoid. Each card fails independently and visibly, including a client
  that raises.

The pre-NSoT SNMP/NetFlow collector is unchanged, moved into one collapsed
"Built-in collectors (legacy)" section below.

[SCREENSHOT: the Monitoring tab — the six Integrations cards with live values, and the collapsed legacy section beneath]

### Device input

- **Add Device** writes the CSV row *and* mints the device's identity at add
  time. It used to be created by whichever `save_golden` ran first, so "when
  does this device get an identity" had no answer anybody could point at.
- **NetBox import runs a read-only dry run first** and shows every object that
  would change. Confirming is one-shot: the token is bound to a hash of that
  exact plan, expires in five minutes, and is burned even on a failed
  validation.
- **NetBox writes are fail-closed** behind two independent conditions — a master
  switch that defaults off, and that single-use token. Removal deletes only the
  intersection of "tagged `nmas-managed`" and "in NMAS's own record", so a
  region or device a human curated is reported as skipped.

[SCREENSHOT: the NetBox import dry-run preview listing objects to be created, with the write gate visible]

[SCREENSHOT: Add Device form, and the resulting manifest entry]

---

## 1.3 Jinja2 templates from existing configs

The pipeline is: **device config → parsed `host_vars` → rendered by template →
compared against the device.**

- **Coverage across all nine devices: 100% modeled, 100% round-trip fidelity,
  zero unmodeled constructs**, under a depth-aware comparison.
- **One parser module per platform** (`cisco_ios`, `cisco_iosxe`). A new vendor
  is a new module plus a template directory.
- **Templates live in the repo** (`config_repo/templates/`) and are approved
  against a binding fingerprint — template hash over the whole import closure,
  plus the sorted set of bound devices. Editing any file in the closure revokes
  every approval that contains it, and revocation writes a tombstone with a
  reason rather than deleting the record.

### Deploy

- **Intent is committed, never inferred.** A device with no committed intent is
  `bootstrap` and not deployable — deriving intent from the device's own capture
  makes the diff empty by construction.
- **Merge-only.** Lines the template does not mention are removal *warnings*,
  never negated.
- **What the operator confirms is what is sent, byte for byte.** The exact
  program is recomputed at apply and compared against the confirmed fingerprint;
  a mismatch is refused. Dangerous lines are authorised individually, per
  device, folded into the same hash.
- **Rollback is computed, not replayed** — a replay is a merge and could never
  undo a `shutdown`. It undoes what *landed*, not what was pushed, which on a
  partial push are different things.
- **Verification uses per-protocol settle windows** (OSPF 45s, BGP 60s, RIP 90s)
  and reports *not yet converged* distinctly from *failed*.

[SCREENSHOT: the templatize view — a device's extracted host_vars beside the round-trip coverage report showing 100%]

[SCREENSHOT: the deploy confirmation dialog — the exact command list, `from_this_edit` vs `pre_existing` attribution, and any dangerous-line authorisation]

[SCREENSHOT: a completed deploy showing verification per protocol and the post-deploy golden commit]

---

## 1.4 Timestamped golden configs

Every golden save is an annotated tag: `golden/<device>/<UTC>`. A whole-fleet
moment is `baseline/<UTC>`.

**A baseline is earned by measurement, not granted by mode.** Each path's tag is
keyed on the claim it makes:

- a **deploy** baseline says "this commit's goldens are the network" — true by
  construction, because the goldens *are* the post-deploy captures; only
  coverage is checked;
- a **restore** baseline says "the network is back to the ref's state", which is
  a content claim and is measured per device with a section-aware comparison. A
  device with nothing to send is still read back, an unreachable device declines
  the tag, and **residue denies the tag** — merge-only cannot remove it, so the
  network is not at the ref.

A batch is one event: one golden commit, one baseline, naming the successful
subset and the failures.

[SCREENSHOT: the Baselines panel listing `baseline/<ts>` entries with their device coverage, including one denied a tag and the reason]

[SCREENSHOT: `git log --follow` on a renamed device, showing history surviving the rename]

---

# Findings

The most useful results were not features. Four are worth stating.

## 1. Checks that could not fail

A recurring shape: a check that is present, reviewed, passing — and structurally
incapable of failing.

- `assert_no_negation` asserted nothing.
- An `already_migrated` result was computed and never consumed.
- A test named `test_bgp_address_families_on_r3_r4_r5` asserted
  `any("address-family" in s for s in bgp["settings"])` — which **pinned the
  flattening as correct**, under a name that made the construct look covered.
- 1,656 tests existed and **not one of them parsed a line of the application's
  JavaScript**. Python tests checked that markup *contained* the right strings;
  nothing checked the result was a program. An unterminated string literal
  reached a deployed page and took an unrelated panel down with it.

The correction in each case was to make the check exercise the property rather
than describe it.

## 2. Rotating the credentials of a live fleet

All nine devices were rotated to type-9 (scrypt) secrets in two stages.

The instructive failure was r2, which **refused the password it had just
accepted**. Two separate defects sat on top of each other:

- the verifier passed a plaintext password into a function that Fernet-decrypts
  its argument, so it failed *before opening a socket* and reported a **local
  fault as a device verdict** — "MAY BE LOCKED OUT" about a device it never
  contacted;
- underneath that, the real cause: `ERROR: Can not have both a user password and
  a user secret`. IOS-XE refuses a `secret` for a user that already has a
  `password`, and the error-detection pattern did not recognise the bare
  `ERROR:` family at all.

The fix distinguishes *attempted* from *not attempted* and classifies failures
positively in both directions. **A verdict about a remote system requires having
asked it.**

[SCREENSHOT: the credential rotation tool output for one device — plan, confirmation fingerprint, rotate, verify, persist chain]

## 3. A redeploy that would have locked the tool out of five routers

The sharpest result of the project, and it was only found by booting hardware.

After rotation, `r1.cfg`–`r5.cfg` each contained
`username admin privilege 15 secret 9 $9$…`. The persistence chain verified this
by reading the startup file back and finding the hash. **The hash was there. The
check passed. It was the wrong question.**

vrnetlab's launch script concatenates its own
`username admin privilege 15 password admin` *before* the startup config, and
IOS-XE refuses a secret for a user that already has a password.

Rather than argue from the launch script, this was measured on a throwaway lab
on its own network, in three stages:

| stage | question | result |
|---|---|---|
| **A** | what does a fresh node look like? | captures for both platforms |
| **B** | does r1's current startup file actually apply? | **hazard confirmed** |
| **C** | does the proposed fix work? | **fix proven** |

**Stage B**, on hardware: `%CVAC-4-CLI_FAILURE: … 'username admin privilege 15
secret 9 $9$…' was rejected`. After boot the running config held the *password*
form; `admin` was accepted over SSH and the file's own credential refused. And
`Startup complete` was reached in 7m26s, the container reported healthy, the
router answered SSH. **Nothing failed.** A redeploy would have produced five
healthy routers holding credentials nobody had, with startup files that read
correctly — and the first symptom would have been the tool unable to log in to
all five at once, after the state that explained it was gone.

**Stage C** proved the fix: a launch script that skips its own username
injection when the startup config defines that user. Same file (sha256
verified), one variable changed, outcome inverted — `Startup complete` 7m15s, no
CLI failure, the file's credential accepted and `admin` refused.

A `docker inspect` three seconds later read `unhealthy`, and it would have been
easy to write that up as a cost of the patch. It was not: the image's
`/healthcheck.py` reads `/health` and exits with its status — no login, no
credentials, so no mechanism exists by which the patch could affect it. It was
Docker's stale boot-period result, and the same image reports healthy in the
production lab.

**The ban on redeploying the production lab still stands.** Proven on a
throwaway node is not adopted here.

[SCREENSHOT: the stage B boot log showing the CVAC rejection, beside the stage C log showing "not injecting vrnetlab's own username line"]

## 4. Presence vs applicability

The generalisation of finding 3, and the single most transferable lesson.

> A **presence** check asks whether the artefact contains the right bytes. An
> **applicability** check asks whether the machine that reads it will end up in
> the state those bytes describe. They differ exactly when something else writes
> to the same place first — the case nobody thinks of.

The check was not weak. It asked a question whose answer was genuinely *yes*. It
cannot be found by reading it; it was found by booting a node that could be
thrown away.

A second instance surfaced in the same stage: `%CVAC-4-CLI_FAILURE: 'ip
domain-name rcn.lab' was rejected` — IOS-XE 17.6 spells it `ip domain name`. The
node booted, was healthy, and answered SSH **with no domain name set**. Present,
well-formed, silently not in effect.

## 5. The em dash that struck twice

An em dash broke this project in two places that shared no code: a pushed
`description` line, where IOS consumed the first of three UTF-8 bytes and
truncated the rest (surfacing as a Netmiko *timeout*, naming the symptom); and
months later, a **comment** in a startup config, which hung a switch's boot.

The first fix was correct. What was wrong was where it lived — on the *deploy
path*, guarding a command list. A startup config is not a command list, but
vrnetlab types it into a console line by line, so every comment is a CLI
interaction. The other platform booted identical content without complaint,
because it loads its startup config as a file. **One platform can never reveal
the property.**

The rule is not "ASCII where we push". It is: **anything that reaches a CLI is
printable ASCII — comments included.**

---

# Current state and future work

**Working now:** golden repository with tags and a private remote; NetBox
inventory with a fail-closed write gate; parsers and templates at 100% coverage
across all nine devices; template deploy with confirm hashes, merge-only pushes,
computed rollback and per-protocol verification; earned baselines; fleet
credential rotation; the identity layer; the Integrations panel.

**Future work:**

1. **Onboarding wizard.** Design complete; the bootstrap profile is *measured*
   rather than written from knowledge, from stage A captures of both platforms.
2. **r6** — adding a tenth device end-to-end through the wizard. Blocked behind
   the redeploy ban.
3. **Lifting the redeploy ban**, which needs four things: adopt the proven
   launch patch into the lab; the static applicability check live in the
   persistence chain; the routers' credentials recoverable while they are
   unreachable; and the generator fixes (vIOS `crypto key generate rsa`,
   per-platform domain-name syntax). *Items 2–4 are built and tested; none is
   adopted. Built is not deployed, and a plan that treats the two as the same
   thing is how a redeploy happens by accident.*
4. **GUI redesign around the new capabilities.** The Monitoring tab's legacy
   collector is the clearest example: the NSoT work added capabilities faster
   than the interface reorganised around them, and the panel added tonight sits
   above a collapsed section rather than replacing it.
5. **Settings audit** — the settings surface has grown one key at a time.
6. **A resolved `ListRef` type**, so a list name cannot be re-derived from
   global state mid-operation. Three separate defects had that shape.
7. **Docker publishes past the firewall.** `ufw`'s default-deny does **not**
   cover Docker-published ports: Docker writes its own `iptables` rules into
   `DOCKER`/`DOCKER-USER`, which are evaluated ahead of ufw's chains, so a
   published port is reachable from the whole LAN while `ufw status` shows it
   denied. Measured here: NetBox `:8000`, Loki `:3100` and oxidized-web
   `:8888` were all open to the LAN, and **oxidized-web serves every device's
   full running configuration** — the largest exposure of the three by a wide
   margin.

   It surfaced by accident and by contrast: Grafana runs as a **native
   process** rather than a container, so ufw blocked it exactly as
   configured. One service behaving differently from its neighbours is what
   made the rule visible — had everything been containerised, the firewall
   would have looked like it was working.

   The fix is to bind the containers to `127.0.0.1` (the services are only
   consumed by NMAS on the same host) or to add explicit `DOCKER-USER` rules.
   Deferred deliberately: it is a change to running infrastructure and
   belongs in its own measured step, not in a documentation pass.

   It is the same shape as the two findings above. `ufw status` is a
   **presence** check — the rule is in the table — and reachability is the
   **applicability** question. They diverge exactly because something else
   writes to the same place first, which is the case nobody thinks of.

---

## Appendix — verification

```
pytest            # 1776 passed, 1 skipped
```

All HTTP and SSH is mocked; **no test touches a live network.** Fixtures are
sanitized captures of the real nine devices. Design notes, including every
defect above with its measurement, are in
[docs/NSOT_WRITEUP_NOTES.md](NSOT_WRITEUP_NOTES.md).
