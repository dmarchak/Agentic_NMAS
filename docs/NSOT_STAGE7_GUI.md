# Stage 7 — the interface, redesigned

**Status: plan only.** Stages 3.2, 4, 5 and 6 come first. This is posted early
so that work lands in the structure below rather than being arranged twice.

**Governing spec:** [NSOT_PLAN.md](NSOT_PLAN.md). This document is subordinate
to it and changes no behaviour.

---

## 0. Premise

The program's scope changed and the interface is a record of how it grew.
Twelve top-level tabs, each named after a subsystem — Devices, Topology,
Ansible, Jenkins, History, NetBox, Agent, Approvals, Monitoring, Configure,
Git, Logs. That is a menu of the parts the program is made of, which is a
useful map only for somebody who already knows how the program is made.

Almost nothing a person does here is "use NetBox" or "use Jenkins". It is
*look at this device*, *change this device*, *is the network healthy*, *what
changed and who changed it*. The tab names answer a question nobody asks.

Three design commitments, generalising what the deploy plan and baselines
panels already do:

1. **Organised around what a person is trying to do**, not around which module
   implements it.
2. **Understandable by somebody new to network engineering.** A label names
   the thing and a line under it says what happens. *Re-apply this baseline*
   with "re-applies stored configuration; does not remove lines devices have
   gained" is the pattern — the button plus its consequence.
3. **Consequences stated plainly, depth one click away.** The summary says
   what will happen; the detail is available and not in the way. The deploy
   plan does this today: *will add (1)*, then the exact line, then the full
   program.

None of this is a skin. The point is that a person can tell what a control
will do before pressing it, and a person who is not the author can tell at
all.

---

## 0a. Scale: the interface is for an enterprise network, not for nine devices

**Recorded 2026-09-23, before any screen is drawn.** This is a constraint on
the information architecture, not a feature to add afterwards: **an interface
that assumes you can see every device is a different interface from one that
assumes you cannot.** Retrofitting the second onto the first is a rewrite.

### What nine hides, measured

The device table's Jinja loop emits **6 buttons and 1 input per row**, plus
the four NSoT actions. That is fine at nine and is not a design at all at
nine hundred:

| devices | interactive elements in one page |
|---|---|
| 9 | 63 |
| 90 | 630 |
| **900** | **6,300** |

And `index()` does `devices = load_saved_devices(current_list_file)` with no
bound, then renders every one of them server-side. **There are 52
`load_saved_devices()` calls across `app.py` and `routes/`, and not one
pagination parameter anywhere in `routes/`.** The whole-inventory read is not
one mistake in one place; it is the assumption the program is built on.

### Correction, after building the fixture: the premise was wrong

**Both of us had it wrong, and the fixture is what said so.** The constraint
was first written as *"nothing may require loading the whole inventory"*, on
the strength of 52 (really 75) unbounded `load_saved_devices()` call sites —
a number that looks like a lot of work and turns out to be nearly none.

Measured at 900 devices: **the whole read is 0.73 ms.** One per-device `git
log` is **7.2 s**. The gap is four orders of magnitude, and it moves the
constraint:

> **from** "don't read everything"
> **to** "don't do per-device work per request".

That is a different design. The first says *bound the reads*, which would
have sent Stage 7 through 75 call sites that mostly do not matter. The second
says *find the places that touch git, a file or a device per row, and make
those jobs* — far fewer sites, and the ones that decide whether the interface
works at 900.

It also means a call site reading the whole inventory is **not** evidence of
a problem, which is the opposite of what the first version implied. The
evidence is what follows the read.

Recorded because it is the clearest case yet for the fixture existing: the
correction arrived **while** the constraint was being written, not after it
had been implemented.

### The five structural consequences

**1. Selection replaces enumeration.** Search and filters — site, role,
platform, status, drift state, template, credential age — with multi-select
actions are the **primary** interface. The full list is a fallback view, not
the default. "Show me everything and let me find it" is a design for a number
you can hold in your head.

**2. Fleet health is the landing view.** How many drifted, unreachable,
uncaptured, on an unapproved template, overdue for rotation. **The device
list is where you arrive after clicking one of those numbers**, carrying that
filter. This inverts the current shape, where the list is the front door and
health is a badge on a tab.

**3. Per-device actions live on a device page, not on the row.** The row
carries **identity and state** — name, address, platform, reachability, drift,
template status — and nothing else. §2.1's device page already exists in this
plan for other reasons; scale makes it mandatory rather than preferable.

**4. Everything is bounded, paginated, and every fleet-wide operation is a
job.** Save All is one commit and a couple of minutes at nine. At nine
hundred it needs progress, partial results, and the ability to **target a
subset** — which the batch machinery already models: the deploy path reports
per-device outcomes, a circuit breaker, and `Failed-Devices:` in the commit.
Drift already reports `checked N of M`. The pattern exists; the UI has never
had to use it.

**5. Nothing may do per-device work to render a page — including the counts
on the landing view.** *"Not a full read wearing a summary"* stands, but the
reason is the per-device operation, not the read: the six landing numbers are
six **per-device questions** — is this drifted, is its template approved,
when was its credential rotated — and answering them by iterating is **900
`git log` calls, 7.2 seconds**. The read itself is 0.73 ms. Those counts come
from bounded queries against git, the manifest and NetBox, or from cached
counts **with their staleness visible**.

### What this costs, stated

* **It contradicts §1.3's frequency argument in one place.** "Something done
  thirty times an hour must be one click from where the device is" assumed
  the device is on screen. At scale the device is found, not seen, so the
  frequent path is *search → device page*, and search has to be fast enough
  to be the click.
* **`index()` returning the whole list is load-bearing for the current
  page**, and the existing device table, bulk selection, drag-ordering and
  the topology view all read from it. Bounding it is not a small edit.
* **Point 5 has no cheap implementation.** Either the counts are maintained
  as state (a cache that can go stale — and a stale count on a health
  landing view is precisely the silent-failure shape this project keeps
  finding), or they are bounded queries against stores that can answer them
  (git, the manifest, NetBox), which is more work and more honest.
* **It may reopen the `local` CSV inventory.** A CSV read in full per
  request is the whole-inventory assumption in its most literal form, and at
  nine hundred devices a NetBox-sourced list is not an option among two.

### Measured, 2026-09-23, with `scripts/nmas-scale-report`

`tests/fixtures/fleet_scale.py` builds a fleet of any size with a realistic
spread — sites, platforms, roles, and **states**: healthy, no golden,
drifted, unreachable, unapproved template, rotation overdue. A uniform fleet
renders fast and proves nothing; it is the mixture that forces filtering.

| devices | page bytes | render |
|---|---|---|
| 9 | 667,538 | 0.001 s |
| 90 | 848,538 | 0.002 s |
| 900 | **2,662,857** | 0.009 s |

**100× the devices is only 4× the page — and that ratio understates the
problem.** Decomposed:

* **fixed cost 647,383 bytes** — identical at 9 and at 900, shipped on every
  page load. That is its own finding and has nothing to do with scale.
* **2,239 bytes per device**, flatly linear, with no bound.

Projected: **11.8 MB at 5,000 devices, 23.0 MB at 10,000**, in one page.

The ratio is reassuring and wrong, which is exactly why the marginal figure
is the one recorded.

### Which of the unbounded reads actually hurt — and the answer is almost none

75 `load_saved_devices()` call sites, more than the 52 first counted.
Measured at 900 devices:

| | |
|---|---|
| `load_saved_devices()` over 900 rows | **0.73 ms** |
| find one device by IP, after the read | 0.01 ms |
| build an IP index, after the read | 0.03 ms |

**The read is not the cost.** At 900 devices it is under a millisecond, and
`index()` performing two of them per render is 1.5 ms of the 9 ms.

What costs is **what follows the read**, per device:

| one operation per device, at 900 | |
|---|---|
| a golden file read | 0.3 s |
| a `git log` | **7.2 s** |
| an SSH round trip | **225 s** |

So "52 unbounded reads" is the wrong unit of work, and treating them as 52
equal items would spend the effort in the wrong place. The rule that falls
out is sharper and shorter:

> **Bounding the read fixes almost nothing. Bounding the per-device
> operation is the whole job.** A call site that reads the inventory and
> looks one device up is fine at any size. A call site that reads the
> inventory and then touches git, a file or a device per row is a job, not a
> request — which is consequence 4, arrived at from the other direction.

That also decides consequence 5. The landing counts must not come from a
full read **not because the read is slow** — it is not — but because the
counts themselves are per-device questions: *is this device drifted, is its
template approved, when was its credential rotated*. Answering those by
iterating is 900 git calls. **Bounded queries against git, the manifest and
NetBox, or cached counts with their staleness visible — never a full read
wearing a summary.**

### The test that keeps it honest

Whatever is built, **a fixture of 900 devices renders the landing view and
the device list within a bound**, and a test asserts the page does not grow
linearly with the inventory. Without it, this section is a paragraph
everybody agrees with and nobody checks — and nine devices will pass every
test written at nine devices.

`tests/test_scale.py` holds that test today, pinned against the numbers
above: it asserts the per-device marginal cost is what it is, so the day
someone bounds the device list the test **fails and has to be updated with a
new number**. A bound that improves things should have to be recorded, not
slip in unnoticed — and until then the test states the status quo rather
than an aspiration.

---

## 0b. A separate finding: 647 KB shipped before the first device

**Nothing to do with scale, and true today at nine devices.**

The rendered page decomposes into:

| | |
|---|---|
| **fixed cost** | **647,383 bytes** — identical at 9 devices and at 900 |
| **per device** | **2,239 bytes** — linear, unbounded |

At the current nine devices that is a **667 KB page of which 97% is fixed** —
markup, inline CSS and 123 inline JavaScript functions, re-sent on every
load, before a single device row.

The two numbers belong together, and that is the point of recording them as
one finding: **the reassuring ratio cannot be quoted without the linear
term.** "100× the devices is only 4× the page" is true and is an artefact of
the fixed cost dominating at small sizes. The honest statement is *647 KB
fixed plus 2.2 KB per device*, which gives **2.7 MB at 900** and **11.8 MB at
5,000**.

Both halves have their own fix and neither fixes the other:

* the fixed cost is the `index.html` problem the conventions already name —
  *"`app.py` and `index.html` must not grow beyond registration and
  `{% include %}`"* — and it is addressed by moving script into files the
  browser can cache, not by bounding anything;
* the per-device cost is §0a's, and is addressed by not rendering every
  device.

Measured with `scripts/nmas-scale-report`; pinned in `tests/test_scale.py` so
either number changing has to be recorded rather than noticed later.

---

## 1. Method: inventory the actions before drawing a screen

The current tabs are not evidence of anything except the order features were
added. So the redesign is argued from **what the interface can do**, measured,
not from what it currently looks like.

### 1.1 What is there now, measured 2026-09-23

| | |
|---|---|
| HTTP routes registered | **217** — 149 in `app.py`, 68 across 11 blueprints |
| Top-level tabs | **12** |
| `index.html` | **8,233 lines**, 123 inline JavaScript functions |
| Modals | **15** |
| Settings modal | ~23 inputs in one dialog |
| Per-device NSoT actions on a device row | **4** (template preview, deploy plan, edit intent, golden history) |
| Actions on the per-device page (`device.html`) | **5**, all backup/restore |

### 1.2 Routes no template or script mentions

Measured by walking `templates/` and `static/` for every route's literal path
stem, excluding eight that are deliberately not GUI (`/`, static, favicon,
`/jenkins/webhook`, `/identity/status`, `/download`, `/ci/appdir`,
`/server/restart`):

**48 of 217 routes are unreachable from any page.**

They fall into four groups, and the groups matter more than the number:

**(a) Phase 3 features with no entry point — the serious ones.**

```
POST /templates/revoke/<path>          withdraw a template approval
POST /templates/bindings               edit which template a device uses
POST /templatize/extract/<host>        extract host_vars from a capture
GET  /templatize/report                round-trip coverage for the fleet
GET  /templatize/staged                what extraction has staged
GET  /templatize/rendered/<host>       the render, for reading
GET  /templatize/rolled-back           devices blocked after a rollback
POST /templatize/rolled-back/<host>/retry   authorise a retry
GET  /templatize/rolled-back/retries   the retry record
```

`rolled-back` is the sharpest case. A rollback blocks the next plan for that
device deliberately, and `authorise_retry()` is the explicit recorded action
that lifts it — **reachable by `curl` and by nothing else.** A device can
enter a blocked state from the GUI and can only leave it from a terminal.

`revoke` is the same shape: `approval.revoke()` writes a tombstone with a
reason precisely so a withdrawal is a recorded finding rather than a deletion,
and the interface offers no way to make one.

**(b) Credential management.**

```
GET,POST /inventory/credentials/profiles
DELETE   /inventory/credentials/profiles/<name>
POST     /inventory/credentials/copy-inherited/<list>
GET      /inventory/dependents/<list>
```

The entire resolution chain — device override → designated credential list →
role profile → site profile → default — is configurable only over HTTP.
"Copy inherited credentials into device overrides", which exists so a list can
be decoupled before its credential source is deleted, has no button.

**(c) State that exists and is never shown.**

```
GET,POST,DELETE /list/variables…      the variable store, full CRUD
GET,POST        /list/compliance_policy
GET             /list/golden_configs
GET             /list/drift_status
GET             /backup_stats
```

**(d) Superseded or genuinely dead.**

```
POST /netbox/sync, /netbox/sync_all, /netbox/remove   superseded by the guarded Import/Remove
GET  /netbox/query/…  (6 routes)                      the AI agent's NetBox reads
POST /configure/build_pipelines, /configure/pipeline_success
GET  /configure/audit/<id>, /configure/audit_latest
POST /execute_command, /run_script/<ip>, /disconnect/<ip>
GET  /connection_status/<ip>, /ai/tool_cache_snapshot, /ai/events…
POST /add_quick_action, /delete_quick_action, /bulk_clear/<id>
POST /remote/adopt
```

`test_blueprint_reachability.py` catches a *blueprint* the page never reaches.
It passes today, because every blueprint has at least one reachable route —
so an unreachable route inside a reachable blueprint is invisible to it. That
is the first concrete deliverable of this stage and it is independent of any
redesign: **extend the check to per-route, with an allowlist that must shrink.**

### 1.3 The inventory itself

Every action the interface can perform, with who does it, how often, and what
has to be on screen for it to be safe. *Frequency* is the design input:
something done weekly can afford a dialog; something done thirty times an hour
cannot.

#### Per-device — the bulk of the work

| Action | Who | How often | What it needs on screen to be safe |
|---|---|---|---|
| View golden config | anyone | many times a day | capture time; masked by default; *reveal* clearly gated |
| Golden history / diff | anyone | daily | which two refs; commit actor and source |
| Template preview | operator | daily | which capture, and when; coverage; every blocking reason |
| **Edit committed intent** | operator | per change | validation with line and column; render diff; what a deploy would push |
| **Deploy plan** | operator | per change | the exact command list, split into *this edit* vs *pre-existing*; dangerous lines named; removal warnings; the confirm hash |
| Apply a deploy | operator | per change | same list, recomputed, byte-identical to what was confirmed |
| Rollback state / authorise retry | operator | rare, after a failure | which lines failed; that a retry re-sends them; **has no UI at all today** |
| Backup now / restore / compare | operator | weekly | age of each backup; that restore is a push |
| Per-device drift | anyone | daily | golden vs running, age of both |
| Credentials for this device | admin | rare | where the credential comes from (`_cred_source`); never the value |
| Live terminal | operator | ad hoc | which device; that this is a real session |
| Interfaces / facts / neighbours | anyone | daily | whether this is live or from a capture, and when |
| Per-device metrics and logs | anyone | on incident | the time range; that the source is Prometheus/Loki |

#### Fleet-wide

| Action | Who | How often | What it needs on screen to be safe |
|---|---|---|---|
| Save all goldens | operator | daily | which devices changed; that it is one commit; whether it earns a baseline |
| Baselines / re-apply | operator | rare, high stakes | add / replace / **residue**, per device; that residue is not removed; stale devices named |
| Push / remote state | operator | continuous, passive | last push, what was pushed, **and failures** |
| Drift check | scheduler + operator | 4-hourly | `checked N of M`, every unchecked device named with its reason |
| Approvals queue | operator | daily | what the agent saw vs what will be sent; that approving a confirm-ending item does not send |
| Inventory / onboarding | admin | per device | source (CSV or NetBox); per-device skip reasons |
| NetBox import / remove | admin | rare | dry-run preview; exact object counts; the write gate's two conditions |
| Template library / approval | operator | per template change | which devices are bound; the round-trip result per device; that an edit revokes |
| Settings | admin | rare | which secrets are set, never their values |
| Monitoring | anyone | continuous | which tool answered, when, and whether it is stale |

Three things fall out of the table before any screen is drawn:

- **Most rows are per-device**, and today they are scattered across Devices,
  History, Git, Monitoring, Configure and a separate `device.html` page.
- **The high-stakes rows are rare**, so they can afford a full-screen review
  step. The frequent rows must be one click from wherever the device is.
- **Three rows have no UI at all** — rollback retry, template revocation,
  credential profiles.

---

## 2. Information architecture

### 2.1 The proposal

Two top-level destinations, plus a persistent service bar.

```
┌──────────────────────────────────────────────────────────────┐
│ NMAS   [ Fleet ]  [ Monitoring ]        ● ● ● ● ● ●   ⚙      │  service bar
├──────────────────────────────────────────────────────────────┤
```

**`Fleet`** — the device list, and the home of everything fleet-wide. Four
sub-views:

| View | Holds |
|---|---|
| **Devices** | the list; search; per-device entry; bulk selection |
| **Changes** | approvals queue, deploy history, drift, rollback-blocked devices |
| **Versions** | commits, tags, baselines, per-device history, remote and push state (§4) |
| **Library** | templates, bindings, approvals, round-trip coverage |

**`Device`** — one device, reached by clicking a row. Not a modal: a page with
its own URL, because it is where the work happens and it must be linkable.
Tabs within it:

| Tab | Holds |
|---|---|
| **Overview** | reachability, platform, credential source, last golden, last backup, drift state, a live metric strip |
| **Config** | golden at HEAD, running, diff, backups, restore |
| **Intent** | committed `host_vars`, the editor, template preview, **deploy plan** |
| **History** | golden timeline, deploy and rollback record, intent commits |
| **Monitoring** | this device's Grafana panels, its Loki lines, its interfaces |

**Settings** stays a modal but is split into sections; 23 inputs in one dialog
is a list, not a form.

### 2.2 Why two, and not five

The tempting shape is one tab per noun — Devices, Config, Intent, Versions,
Monitoring. It reproduces the current problem at a smaller scale: a person
still has to know which noun holds the thing they want, and the answer for
"what is wrong with r3" is four of them.

Two destinations means one decision: *am I looking at the fleet, or at a
device?* Everything else is inside whichever answer.

### 2.3 What it costs

**Every existing entry point has to land somewhere, and some do not fit.**
This is the honest part of the proposal.

| Today | Lands | Note |
|---|---|---|
| Devices tab | Fleet → Devices | the row gains an "open" affordance |
| Bulk ops (command, file, routes, reload) | Fleet → Devices, on selection | unchanged |
| Save All | Fleet → Versions | it is a commit, not a device action |
| Topology tab | Fleet → Devices, as a view toggle | §5 |
| Ansible tab | **removed** | §6 |
| Jenkins tab | Fleet → Changes, as a CI strip on the deploy record | §6 |
| History tab | Device → History, and Fleet → Changes | §6 |
| NetBox tab | Settings → Inventory, plus a Monitoring summary card | §6 |
| Agent tab | Fleet → Changes | §6 |
| Approvals tab | Fleet → Changes | keeps its badge on the Fleet tab |
| Monitoring tab | `Monitoring` destination | §3 |
| Configure tab | Device → Intent, or removed | §6 — the open question |
| Git tab | Fleet → Versions | §4 |
| Logs tab | split: app log → Monitoring; list management → Settings | today it holds both, plus discovery and the settings modal |
| `device.html` | folded into Device → Config | one device page, not two |

**Costs, stated:**

- **`index.html` is 8,233 lines with 123 inline functions.** It cannot be
  rearranged incrementally and safely at once. The migration is per-view, each
  view moving to `templates/partials/` with its script, leaving `index.html`
  as layout and `{% include %}` — which the conventions already require of new
  UI and which no existing UI obeys.
- **Every moved control is a chance to lose one.** The route inventory in §1.2
  is the checklist: after each move, the per-route reachability test must have
  strictly fewer allowlisted entries than before.
- **Muscle memory breaks.** One user, so the cost is bounded, but the old tab
  ids are linked from notes and docs. The old `#devicesPane`-style anchors
  should redirect rather than 404.
- **A device page needs a URL**, so `/device/<hostname>` becomes a real route
  with the list context in it — `list_name` is carried, never re-derived, for
  the reason the deploy pipeline learned.
- **The AI chat panel lives in `base.html`** and assumes the dashboard's
  layout. It has to survive the reorganisation; it is not in scope to change,
  and it is in scope not to break.

---

## 3. Monitoring becomes the destination

Today it is a status board: six cards, each saying up or down with a number.
That answers "is the stack alive", which is a question about the *tools*. The
destination has to answer questions about the *network*.

### 3.1 Grafana, embedded

**This is the centrepiece and the only part that needs infrastructure work.**

The earlier reachability problem does not apply: Grafana is publicly reachable
at `grafana.dmarchak.dev` and NMAS at `nmas.dmarchak.dev`, both through
Cloudflare. **No proxy is needed for the embed.** The iframe points at the
public hostname; the card's own data fetch stays server-side via
`127.0.0.1:3000`, so the panel still renders when the tunnel is down and
Grafana credentials never reach the browser.

> `routes/monitoring_stack.py`'s module docstring currently states that an
> `<iframe>` "would work on the console at the lab host and show nothing at
> all to a remote viewer". That was true when written and is now wrong for
> Grafana specifically. It must be corrected in the same commit as the embed,
> not left as a comment contradicting the code beside it.

**Two blockers remain, both infrastructure changes, both named rather than
assumed away:**

**(a) Grafana must permit framing.**
`[security] allow_embedding = true` in `grafana.ini`, plus
`content_security_policy` / `frame-ancestors` permitting
`https://nmas.dmarchak.dev`. Grafana defaults to `allow_embedding = false` and
sends `X-Frame-Options: deny`; with that in place the iframe renders a blank
box and the only signal is in the browser console. Anonymous or embedded-token
access must also be decided: a dashboard that requires a Grafana login inside
an iframe shows a login form, which is worse than an error.

**(b) Cloudflare Access, if it fronts Grafana, blocks framing too.**
Access interposes its own login and sets framing headers of its own, so a
policy is needed for the embed path — a service-token or bypass policy scoped
to the dashboard URLs, not to Grafana as a whole.

> **The iframe test result was not supplied with this request** — the message
> contained the placeholder rather than output. So (a) and (b) are recorded
> here as *named, expected* blockers on the strength of how Grafana and Access
> behave by default, **not as measured findings.** Before any embed work
> starts, the test is: load `https://grafana.dmarchak.dev/d/<uid>` in an
> `<iframe>` on a page served from `nmas.dmarchak.dev`, off-LAN, and record
> the response headers and what renders. Two named blockers that turn out to
> be one, or three, changes the work; assuming them is the habit this project
> has spent five stages removing.

**Design, once framing works:**

- **Fleet view**: the lab's overview dashboard, embedded full-width, kiosk
  mode, theme matched.
- **Device view**: the same dashboard filtered to that device via
  `var-instance=<hostname>` in the iframe URL — one dashboard, parameterised,
  not one per device.
- **A visible fallback.** If the frame fails to load, the card says *which* of
  the two blockers it looks like and links to the dashboard directly. A blank
  rectangle is the failure mode this whole document is against.

### 3.2 Kea — full lease detail

Today: a count. `kea.py`'s `_active_leases()` filters to currently-valid
leases, so an expired lease is invisible and a device that lost its address an
hour ago looks identical to one that never had one.

Proposed: a lease table — **address, client identifier / MAC, hostname,
lease start, expiry, state** — with expired and historic leases included and
marked. Filter by subnet and by state. This is what makes "r6 did not get an
address" answerable without an SSH session.

Needs: `lease4-get-all` (and `lease6-get-all`) rather than the summary
command, and a decision about page size, since a lab of nine is not a
constraint but the code should not assume it.

### 3.3 Loki — queryable

Today: a line count and the ten most recent lines over six hours
(`monitor(limit=10, hours=6)`). That is a liveness check wearing the clothes
of a log viewer.

Proposed: a query panel with **device, time range, severity, and free text**,
building a LogQL query server-side. Results paginated, with the device and
timestamp of each line. Selecting a device in the Fleet view pre-fills it, and
the Device → Monitoring tab is the same panel scoped to that device.

Free text goes through the same treatment as everything else that leaves the
host: the query is built server-side and results are redacted on the way out,
because a log line can carry a secret and `redact_text()` is where that is
already decided.

### 3.4 Oxidized, NetBox, Prometheus

- **Oxidized: unchanged.** The card works and says what it needs to.
- **NetBox: a summary card, not a browser.** It is a backend source of truth,
  and a human reading it here is reading a worse copy of the NetBox UI. Device
  count, last sync, the write gate's state, and a link out.
- **Prometheus: unchanged as a card**, since the human-facing view of its data
  is Grafana.

### 3.5 The service-status bar

One indicator per integration, on **every** page, top right: six dots, each
green / amber / red / grey with a tooltip naming the tool, the last successful
check, and the failure if any. Clicking one goes to that tool's card.

It replaces the Monitoring tab's job of "is the stack alive" and frees the
destination to be about the network. It must be cheap: one `/monitoring/stack`
poll on a slow interval, cached server-side, and **it must never block a page
render** — the current cards already fetch independently for this reason, and
that property is load-bearing.

---

## 4. Versions — the version-control home

Today the Git tab holds a commit box and a commit list. Meanwhile the golden
repository panel, baselines, per-device golden history, the remote card and
push state all live under Devices, because that is where they were needed when
they were built.

That is backwards. `config_repo/` is the source of truth for configuration and
intent; its history is the audit trail for every gated action except reveals.
It deserves the destination.

**Fleet → Versions holds:**

- **Commits** — subject, actor, source, trailers, the devices touched.
  Filterable by device and by source (`manual`, `save_all`, `pipeline`,
  `approval`, `ai`, `onboarding`, `extraction`, `repair`).
- **Tags** — `golden/<device>/<ts>` and `baseline/<ts>`, with what a baseline
  claims and why it was earned.
- **Baselines and re-apply** — moved wholesale from the Devices tab, unchanged
  in behaviour, still reporting add / replace / residue per device.
- **Per-device history** — the same timeline the device page shows, here
  across all devices.
- **Remote** — the card, last push, **and `last_push_failure`**, which is the
  field that exists because a commit that could have been published and was
  not must never be silent.
- **Diffs** — masked by default, `?reveal=1` gated to a person and recorded.

**The `Actor:`/`Source:` trailers become visible here.** They are written on
every commit and the interface currently shows neither, so the thing that
distinguishes "a person approved this" from "a script did" is recorded and
never displayed.

---

## 5. Topology

**The destination is the Grafana view. Removal is not scheduled.**

The condition is explicit: the NetworkX/vis.js topology stays exactly as it is
until an embedded Grafana view actually shows the topology, verified on
screen, off-LAN. Not "once the node-graph panel is configured" — until the
picture is there.

Rationale: it is the only thing that works today, it is the demo, and the
replacement depends on §3.1's two blockers plus a data path that does not
exist yet (topology into Prometheus or a node-graph datasource). A plan that
schedules the removal of a working view against an unbuilt replacement is how
a working view gets removed.

Interim: the topology moves from a top-level tab to a **view toggle on Fleet →
Devices** — list or map, same data, same selection. It stops being a
destination and becomes a way of looking at the device list, which is what it
is.

---

## 6. Redundancy pass

Each item: **keep**, **fold in**, or **remove**, with a reason. Nothing is
removed on suspicion; anything whose status is uncertain gets measured first.

| Feature | Verdict | Reason |
|---|---|---|
| **Ansible tab** | **remove** | The NSoT path is template → render → merge-only deploy, with a confirm hash and a rollback. Ansible is a second, ungated way to change a device that shares none of those guards. Two config paths is the problem Phase 3 exists to end. `awGenerate`/`awDownload` produce artefacts nothing consumes. |
| **Jenkins tab** | **fold in — but see the open decision** | CI is real and the pipeline's stage 3 gate depends on it. But it is *part of a deploy*, not a destination: it belongs as a CI strip on the deploy record in Fleet → Changes. `modules/pipeline.py` and `pipeline_builder.py` stay — they are NMAS's own 9-stage pipeline, not Jenkins. **Whether Jenkins survives at all is an open decision** (GitHub Actions vs Jenkins, recorded in NSOT_PLAN.md): the CI strip holds either way, but what it links to follows from that. Do not remove Jenkins pipeline management in this stage while the decision is open. |
| **Agent tab** | **fold in** | The agent's *output* — queued approvals, events — belongs in Changes. Its controls (pause, timers, trigger) are settings. A tab for "the agent" is a tab about an implementation. |
| **Configure tab** | **open question, measure first** | `/configure/apply` is explicitly "untouched and the quick path". But 15 actions and a wizard overlap the intent path, and four `/configure/*` routes are already unreachable. The decision needs a measurement this plan does not have: **is `/configure/apply` used, and for what?** If it is the fast path for one-off changes, keep it, scoped and labelled as unmanaged. If it is a second config generator nobody uses, remove it. Deciding either way from this document would be deciding by omission — the mistake `_scan_device` nearly repeated. |
| **History tab** | **fold in** | Command/config history is per-device context. It belongs on Device → History, with the fleet-wide view in Changes. |
| **NetBox tab** | **fold in** | Import/Remove are admin operations → Settings → Inventory. Health → a Monitoring card. The six `/netbox/query/*` routes are the AI agent's and need no UI. `netboxSyncAll`/`netboxSyncCurrent`/`/netbox/remove` are the **unguarded** predecessors of the gated Import/Remove and should be **removed**, not moved — leaving a second path around the write gate is the same shape as leaving `_run_drift_check` in place. |
| **Logs tab** | **split** | It holds the app log, list management, subnet discovery *and* the settings modal. The log → Monitoring; the rest → Settings. |
| **SNMP / NetFlow collectors** | **keep, relocate** | Real receivers with real data. They belong in Monitoring next to Loki, not on a settings-shaped tab. Their config → Settings. |
| **Quick actions** | **remove** | `add_quick_action` / `delete_quick_action` are unreachable; the feature has no surface. |
| **`/execute_command`, `/run_script`** | **measure, then likely remove** | Unreachable, and they are arbitrary execution paths outside every guard on the deploy path. If nothing calls them they go. |
| **`config_git.write_and_stage`** | **remove** | Carried forward from Stage 3.3: zero callers, the stage-then-commit-later golden path that `save_golden()` replaced. |
| **`device.html`** | **fold in** | A second device page with five backup actions. One device page. |

---

## 7. Sequencing

Each step is independently shippable and leaves the interface working. Nothing
here starts before Stage 6 closes.

| Step | Work | Why first |
|---|---|---|
| **7.0** | Per-route reachability test, allowlist seeded from §1.2, allowed only to shrink | It is the checklist for every later step, and it is worth having whether or not the redesign happens |
| **7.1** | Entry points for the three features that have none: rollback retry, template revocation, credential profiles | They are defects today, independent of layout |
| **7.2** | The service-status bar, on the existing layout | Small, visible, and proves the shared-header pattern before anything moves |
| **7.3** | `Device` page at `/device/<hostname>`, folding in `device.html` and the four NSoT actions | The largest win; everything per-device stops being scattered |
| **7.4** | `Fleet → Versions`: Git tab absorbs the golden panel, baselines, remote | §4 |
| **7.5** | Monitoring: Grafana embed **after (a) and (b) are done and the iframe test is recorded**; then Kea leases, then Loki query | §3, and the blockers gate it |
| **7.6** | `Fleet → Changes`: approvals, deploys, drift, Jenkins strip, agent output | §6 folds |
| **7.7** | Settings split; Logs tab dissolved | §6 |
| **7.8** | Redundancy removals, each with `check_removed_definitions.py` and a recorded reason | Last, so nothing is removed before its replacement is on screen |
| **7.9** | Topology: **only if** an embedded view shows the topology | §5 |

---

## 8. Acceptance

- **Per-route reachability**: the allowlist is strictly smaller after each
  step, and empty except for deliberate non-GUI routes at the end.
- **Every action in §1.3 has exactly one home**, and a test asserts each named
  entry point is present in the rendered page — the rule that has caught four
  unreachable features so far.
- **Consequence text is tested, not just written.** `test_tab_descriptions_are_true.py`
  already pins a description against what the code does; every new
  consequence line gets the same treatment, because a description that
  outlives its mechanism is how the NetBox tab came to promise a live scan
  that nothing performed.
- **The Grafana embed either renders or says which blocker it hit.** A blank
  frame fails acceptance.
- **Drift, approvals and push state all state their coverage**, per Stage 3.3:
  a count that cannot be short cannot warn.
- **No behaviour change.** Stage 7 moves controls and adds entry points. Any
  change to what a control *does* is a different stage.

---

## 9. Open questions

1. **`/configure/apply`** — keep as the labelled quick path, or remove? Needs
   the usage measurement in §6 before it is decided.
2. **Device page vs. panel.** A real URL is better for linking and for the AI
   agent to reference; a panel keeps the fleet context visible. Proposed: a
   page, with the device list collapsible beside it.
3. **Grafana authentication inside the frame** — anonymous read-only org,
   embedded token, or an Access service policy. This is (b)'s detail and the
   answer changes what the iframe URL looks like.
4. **Does the AI chat panel belong on the Device page?** It has per-device
   context there that it has to be told today.
5. **One dashboard parameterised by device, or a per-device dashboard?**
   Parameterised is proposed; it depends on what the lab's dashboards already
   do, which has not been measured here.
