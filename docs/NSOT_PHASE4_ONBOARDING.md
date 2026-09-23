# Phase 4 — Onboarding wizard (Obj 1.2a(ii))

Plan only. Nothing here is built.

> ## ✅ REDEPLOY BAN LIFTED — 2026-09-22
>
> **Lifted by a successful redeploy, not by the fix being built.** Here is
> what proved it.
>
> The ban existed because `configs/r1.cfg`–`r5.cfg` carried
> `username admin privilege 15 secret 9 …` and had never been booted. Stage B
> measured, on a throwaway C8000v, that vrnetlab's injected
> `username admin privilege 15 password admin` lands first and IOS-XE refuses
> a secret for a user that already has a password: the node came up on
> `admin/admin`, reached `Startup complete`, reported healthy, and answered
> SSH — with a startup file that read correctly and did not apply.
>
> **The redeploy of 2026-09-22, 23:39:**
>
> | | result |
> |---|---|
> | all nine `Startup complete` | routers ~6m30, switches 4m17–5m09 |
> | uptimes | consistent with this boot; no silent reload |
> | username line rejected | **none** |
> | the user-skip fired | exactly once on every router |
> | `secret 9` on all nine | yes; **no device holds `password 0`** |
> | the credential NMAS holds | **accepted on all nine** |
> | old `admin`/`admin` | **refused on all five routers** (`NetmikoAuthenticationException`) |
> | Oxidized | nine successes, all after the redeploy |
> | Save All vs pre-redeploy goldens | `758d1f56` — certificate bodies on r1–r5 only; **zero non-certificate changed lines** |
> | drift | clean, 9/9 |
>
> **What made it safe to try**, in order: the launch patch adopted into
> `~/labs/lab/patches/` (stage C); a break-glass credential record verified on
> the laptop it lives on; stage D2 proving a vIOS boots a real `secret 9`
> startup line, so the switches were not tested for the first time by the
> redeploy itself; and an applicability check whose **negative control was
> watched to fail** — routers `WILL NOT APPLY` with the marker hidden,
> switches unaffected.
>
> That last one nearly did not happen. The check's first version reported
> APPLIES with the marker hidden, because it searched for a *name* rather than
> a call. Nine APPLIES lines were about to enter this record as evidence.
>
> **Kept, not deleted.** The reasoning is what stops the hazard being
> recreated — by a rotation that writes a `secret` line into a startup file on
> a platform whose launch path injects a password first. The persistence
> chain's `startup_applies` stage now refuses that at the moment it would be
> created.

Adding a new device, or a new site, from the GUI: NetBox objects, committed
intent, a rendered config, and either a download for a node that does not
exist yet or a deploy to one that does.

---

## 0. What is already true (measured, not assumed)

Two findings change the design, so they come first.

### `adopt_identity()` is the only minting path — and the default undermines it

`resolve_identity()` deliberately cannot create. Creation is
`adopt_identity()`, "called only by a caller that has decided this really is a
new device". That separation was made after a resolver that could mint trusted
a supplied uid the manifest had never seen, and every deploy created a second
manifest entry.

But the gate in front of it is a **default-on** parameter:

```python
def save_golden(..., allow_new: bool = True, ...)
```

Measured across the repository — seven call sites, **four of which take the
default and can therefore mint**:

| call site | `allow_new` |
|---|---|
| `routes/deploy.py:773` | explicit `False` |
| `modules/pipeline.py:1527` | explicit `False` |
| `modules/nsot/credential_rotation.py:1488` | explicit `False` |
| `app.py:5057` — **Save All** | default → mints |
| `modules/pipeline.py:1435` | default → mints |
| `modules/config_git.py:138` | default → mints |
| `modules/ai_assistant.py:504` | default → mints |

Save All therefore adopts an identity for any device in the inventory the
manifest has never seen, silently, as a side effect of a routine capture. So
does a path reachable from the **AI assistant**, which is the one that should
be least able to create identities and is currently among the four that can.

So "the wizard is the one legitimate minting path" is not true today and
cannot be made true by adding the wizard. It becomes true by flipping the
default:

```python
def save_golden(..., allow_new: bool = False, ...)
```

…and having exactly one caller pass `True`. This is a **prerequisite of Phase
4, not part of it**, and it is the kind of change that reveals callers relying
on the old default — which is the point, since each one is a place minting
happens today without anybody deciding it should.

> A rule enforced by a parameter whose default breaks it is a convention, not
> a rule. The default is the behaviour.

### `_artifact_for()` refuses precisely the device the wizard exists to create

```python
captured = _captured_config(repo, hostname)
if not captured:
    return None, "no golden config for this device"
...
bootstrap = committed is None      # -> refused
```

Both refusals are correct for the deploy path and both are fatal for
onboarding. A new device has **no capture** (it may not exist yet) and **no
committed intent** (the wizard is what produces it). `build_artifact()`
compares a render against a capture; with no capture there is nothing to
compare, and the refusal of `bootstrap` exists precisely so that a device's
status quo is never mistaken for its goal.

The shape of the answer already exists in this codebase. `RestoreTarget` is
not a variant of `RenderArtifact`; it is a **different source** that
duck-types the three things `plan_batch()` reads, so the batch runner is
untouched and its blocking reasons are its own short list rather than
`deployable`'s borrowed and hoped to line up.

Phase 4 needs the third member of that family.

---

## 1. `BootstrapTarget` — a third source, not a third flag

| | intent from | compared against | exists on the device? |
|---|---|---|---|
| `RenderArtifact` | committed `host_vars` | the golden capture | yes |
| `RestoreTarget` | a git ref | the golden capture | yes |
| **`BootstrapTarget`** | **the wizard's inputs** | **nothing** | **maybe not** |

Same properties below the intent layer — confirm hash, ASCII guard,
provenance, `error_pattern`, failure capture, circuit breaker, staging, the
single golden commit — and its **own** blocking reasons:

- the template does not exist for this platform, or is unapproved;
- the render contains a mask (`assert_no_mask`), or a non-printable byte
  (`assert_sendable`);
- a named secret is not in the credential store;
- **the device already has an identity in the manifest.** Onboarding a device
  that is already onboarded is not an onboarding, and this is the check that
  keeps `adopt_identity()` honest.

What it does **not** inherit is the merge-only diff, because there is nothing
to diff. A bootstrap config is the whole config, and that difference must be
visible in the UI rather than implied: the operator is confirming *"this
device will be configured as follows"*, not *"these lines will be added"*.

### The deploy question this raises

A bootstrap deploy to a reachable device sends the **whole** rendered config,
not a merge. That is a different and larger act than every deploy this system
performs today, and it deserves saying plainly on the confirm screen. Two
sub-cases, and I would treat them differently:

- **the device is unreachable** — download only. No deploy path at all.
- **the device is reachable and has a configuration** — it is not a new
  device in the sense the wizard means. Refuse, and point at the ordinary
  deploy path.
- **the device is reachable and is at factory defaults** — the genuine case,
  and the only one where a bootstrap deploy makes sense.

Distinguishing the second from the third needs a capture, which needs
credentials, which the wizard is in the middle of collecting. This is the
first open question in §7.

---

## 2. NetBox writes go through the Phase 0 gate unchanged

The wizard creates a device, interfaces, IP addresses and a primary IP. Those
are writes, and the existing rule is fail-closed: `netbox_allow_writes` **and**
a single-use token bound to a hash of that exact plan, issued by a preview,
burned on use, five-minute expiry.

The wizard's Review step **is** the preview. It must:

- show every object that would be created, including dependent objects under
  a device that does not exist yet (placeholder ids), and shared objects
  counted once rather than once per device — the preview count is the
  executed count;
- tag everything it creates `nmas-managed` and record the ids in
  `data/netbox_created_ids.json`, so a later removal deletes only the
  intersection of "tagged" and "ours";
- recompute the plan on execute and abort with "NetBox changed since preview"
  if the hash differs.

No new write path. If the wizard needs one, that is a signal the wizard is
wrong, not that the gate is.

---

## 3. Ordering: what is created when, and what happens when step N fails

The wizard produces artifacts in three different stores — NetBox, the git
repo, and the credential store — and they cannot be made atomic. So the order
is chosen by **what is recoverable**:

1. **Credential profile binding** — local, reversible, no external effect.
2. **NetBox objects** — gated, tagged, recorded. Recoverable through the
   existing provenance-based removal.
3. **`host_vars` commit** — `adopt_identity()` mints here, in one commit with
   the device's initial intent.
4. **Render** — pure computation.
5. **Download or deploy** — the only irreversible step, and the only one
   behind a confirm.

A failure at step 2 leaves nothing committed. A failure at step 3 leaves
NetBox objects that are tagged and recorded, so the existing Remove path
cleans them; the wizard should offer that directly rather than leaving the
operator to find it.

**Step 3 before step 4 matters.** Rendering before committing intent would let
an operator download a config built from intent that was never recorded — a
device configured from something the NSoT does not have.

---

## 4. Wizard steps

Per the plan, with what each step must actually establish:

1. **Site** — existing, or new (a NetBox site plus `group_vars/site_<slug>.yml`).
2. **Identity** — name, manufacturer, platform, device type, role. The name is
   checked against the manifest **and** NetBox; a collision in either is a
   refusal, not a warning.
3. **Addressing** — management IP, WAN interface and IP/prefix, with an IPAM
   availability check and optional "next available in prefix". Availability is
   re-checked at execute, because the preview's answer ages.
4. **Routing** — OSPF (area, passive interfaces), RIPv2, BGP (local AS,
   neighbour, remote AS), or static.
5. **Template** — filtered by platform, and **must be approved** for that
   platform. An unapproved template is a refusal with the reason, not a
   silent render.
6. **Credentials** — an existing profile, or the device override. Resolution
   follows the existing first-match-wins order, and the chosen source is
   displayed, because `_cred_source` exists so the origin is visible.
7. **Review** — the NetBox plan, the `host_vars` YAML, and the rendered config
   with secrets masked. `intended/` is masked and is never a deploy source;
   the deploy re-renders with real secrets in memory and `assert_no_mask()`
   guards it.

---

## 5. Change flows

"Change routing protocol settings" and "Add interface" edit YAML/NetBox and
then run render → diff → deploy. These are **not** bootstrap: the device
exists, has a capture and has committed intent, so they are ordinary
`RenderArtifact` work and must go down the existing path rather than growing a
parallel one.

---

## 6. Tests

- `adopt_identity()` is reachable from exactly one caller, asserted by AST;
  every other `save_golden` call site resolves or refuses.
- Onboarding a device that already has a manifest identity is refused.
- A `BootstrapTarget` with an unapproved template, a masked render, a
  non-printable byte, or a missing secret is not deployable, each with its own
  reason.
- The Review step's NetBox object count equals the executed count, including
  dependent and shared objects.
- A token from a stale preview is refused with "NetBox changed since preview".
- A failure between NetBox creation and the `host_vars` commit leaves NetBox
  objects that the existing removal path can delete — tagged and recorded.
- A bootstrap deploy sends the whole config and says so; a merge-only deploy
  to a bootstrap device is impossible by construction.
- The rendered download and the deployed config are byte-identical for the
  same inputs, secrets excepted.

---

## 7. Open questions — I would want these decided before building

1. **How does the wizard tell "factory defaults" from "already configured"?**
   It needs a capture to know, and credentials to capture. Options: require
   reachability + a capture before offering deploy (safest, and makes the
   wizard useless for a device that does not exist yet — which is half its
   purpose); or offer deploy only when the operator asserts the device is new,
   which is a claim the tool cannot check. I lean to: **download is always
   available; deploy requires a successful capture showing no `hostname` and
   no configured interfaces**, and anything else refuses with what it found.

2. **Does a new site's `group_vars/site_<slug>.yml` commit separately?** One
   commit for the site and one for the device reads better in `git log`, but
   makes a half-onboarded state representable. I lean to one commit, since
   `save_golden`'s "one call is one commit" already carries that idea.

3. **Should the wizard write `devices.csv`?** For a local list it must, or the
   device is invisible to every other part of the app. For a NetBox-sourced
   list identity is read-only and the device arrives on the next refresh —
   two quite different flows behind one wizard, and the difference should be
   visible to the operator rather than smoothed over.

4. **`allow_new` default flip** — prerequisite, but it will change behaviour
   for Save All on a device the manifest has not seen. Today that silently
   adopts; afterwards it refuses and names the device. I think that is right,
   and it is a behaviour change to make deliberately rather than discover.

---

## 8. Decisions taken (and what they changed)

1. **Factory-default is "nothing beyond the per-platform bootstrap profile".**
   "No hostname and no configured interfaces" is never true here —
   containerlab nodes boot with a hostname, a `clab-mgmt` VRF, a management
   interface and a user. A routing process, or a data interface with an
   address, means configured: refuse unless acknowledged.

   **The profile is measured, not written.** See
   `docs/bootstrap-probe/` — a throwaway topology sharing nothing with
   `rcn-lab1`, whose captures become fixtures with their provenance.

2. **`BootstrapTarget` keeps merge-only semantics.** Download is always
   available; deploy requires a capture, and shows the diff and the residue
   like every other deploy. This is a smaller departure from `RenderArtifact`
   than first planned — the only thing it lacks is *committed* intent to
   render from, not the merge.

3. **One commit per wizard run**, site and device together, trailers naming
   both. NetBox cannot be atomic with git: if device creation fails after the
   site is created, the result reports the site created and the device not.

4. **Local lists** get a `devices.csv` row via `write_devices_csv()` carrying
   the adopted identity. **NetBox-sourced lists** get the NetBox device,
   credentials as a credential-store device override, and the next refresh
   picks it up — identity there is read-only, so the wizard must not pretend
   otherwise.

5. **The last wizard step offers `set_credential`**, so an onboarded device
   moves to a device-generated type-9 secret rather than keeping whatever
   bootstrap credential it came with.

6. **`allow_new` flipped first**, in `3dc7730`. Done.
