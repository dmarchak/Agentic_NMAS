# Bulk actions on Devices (design)

**C1307, the operator's request of 2026-10-18: design now, build after Phase 7. Nothing here is
built.** The board for sign-off is [boards/bulk-actions.html](boards/bulk-actions.html) (A: the
Devices list with a filter-built selection and its Actions; B: a bulk Reload's preview; C: the
run, stopped at its first failure). Governing rules: CLAUDE.md's *Product design and the
interface* and *Operations and safety*; the charter, [MERCURY_CHARTER](MERCURY_CHARTER.md),
where anything here disagrees with it.

The request: "Bulk actions on Devices mirror the device page's Actions. Review every device
action and say which make sense in bulk and why. Design for 500–1,000+ devices: selection by
filter (site, role, platform, status) across pages; a preview listing each device's plan;
confirm by hash; batches with a concurrency limit; stop on first failure; progress and a
per-device outcome. Disruptive actions (Reload, Re-apply) need guardrails, e.g. never both VRRP
peers at once, never the management path's switch alongside others, and windows/silences
respected."

## 1. The shape, in one paragraph

A bulk action is **the single-device operation, run per device through its own code, inside
one frame** that every bulk action shares: a **selection** that is a filter resolved by the
server (never a list of names from the browser); a **preview** computed per device by that
operation's own plan, led by counts and grouped by outcome; one **confirm** bound by hash to the
resolved set, every device's plan hash and the batch plan; a **run** that is a job, working in
**batches** (a concurrency limit inside a batch, the circuit breaker judged between batches),
holding each device while it is worked, announcing progress; and a **result and record** per
device, plus one record of the run. Disruptive actions add a **batch planner** whose guardrails
(redundant pairs apart, the management path alone, drained and windowed devices left out, a
maximum blast radius per batch) are part of what is hashed and confirmed. No action gets a
second implementation: Deploy stays `routes/deploy.apply_batch`, Save stays
`modules/nsot/save_op.run`, Reload is `modules/nsot/reload_op.run` called once per device.

## 2. What exists today, read in the code

| What | Where (file, function) | What it does today | What the design does with it |
|---|---|---|---|
| The device page's Actions | `templates/v2/_actions_menu.html`, served by `routes/device_v2.actions_menu` | 12 rows: Plan a deploy…, Capture, Seed intent…, Restore from…, Remove lines (Mode B)…, Revert intent…, Retry rolled-back change…, Rotate credential…, Persist, Run a privileged command…, Reload…, Retire… | Judged one by one in section 3 |
| Device actions outside that menu | `routes/device_v2.rekey` / `rekey_confirm` (C906), `routes/device_v2.golden_reveal`, `routes/intent_v2` (edit, check, acknowledge, commit, reopen), `routes/v2.decline_card` / `decline_confirm` (C718) | Re-key a host key; reveal a golden's secrets; edit intent; decline a profile section | Judged in section 3 |
| The Devices list | `modules/device_list.listing(ref, q, state, platform)`, `routes/v2.devices` / `devices_table`, `templates/v2/_devices.html` | Filters by a name-or-address substring, the intent state (`device_list.STATES`) and platform, all server-side; draws EVERY matching row (excused in `tests/test_large_fleets.py` `EXCUSED`, owed by C450); ticks are checkboxes whose names the form sends. There is no `matching` function and no site, role or status filter. Rows carry `role`; NetBox-sourced inventory rows carry `_site` (`modules/inventory/netbox_source.py`) | The selection becomes a filter (section 4); paging and the summary come with C450 |
| Devices › Plan a deploy for the ticked devices | `routes/v2.devices_deploy` → `routes/v2._apply_ctx` (scope `intent`) → `routes/deploy.plan_devices`; confirm `routes/v2.profile_apply_confirm` → `modules/deploy_job.start` → `routes/deploy.apply_batch` | Each device's whole-intent program; the person may reorder (C888); the confirm carries every device's capture and command hash from the page (`CONFIRM_JSON_FIELDS`), and the order must be exactly those devices | Bulk Deploy IS this path, fed by the filter selection and a server-held plan |
| Devices › Save (ticked, every device, or `scope=no_golden`) | `routes/v2.save` / `save_confirm` / `save_job`, `modules/nsot/save_op.plan` / `run` / `start` | Plan from stored records only; confirm bound to the plan's hash; a job; `WORKERS = 6` concurrent (Show commands' cap, C605, not measured); no stop on failure; one commit (`Source: save` or `save_all`) | Bulk Save IS this path; its confirm stops posting device names |
| Devices › Change a setting on the ticked devices | `routes/bulk_intent_v2.preview` / `apply`, over `routes/templatize.bulk_plan_of` / `bulk_apply_of` | One intent change, one commit, nothing sent | Unchanged; fed by the filter selection |
| History › re-apply a baseline | `routes/v2.history_reapply` / `history_reapply_confirm` → `modules/deploy_job.start_restore` → `routes/deploy.run_targets` | A baseline tag re-applied across the network, each device's program recomputed and refused alone if its hash moved | This is "Re-apply" in the request; it gets the batch frame's guardrails as a disruptive action |
| The circuit breaker | `modules/nsot/deploy.CircuitBreaker` | Counts a device that did not end deployed with its verify passed (C10); drift at apply is not counted. `limit` is `deploy_verify_failure_limit` (default 2) or 1 (Coverage's combined deploy, "stops at its first failure") | Every bulk run uses it, limit 1 (section 7.3) |
| The batch runner | `modules/nsot/deploy.run_batch`, `max_workers` | Sequential by default (`deploy_max_workers` = 1): "vIOS-L2 has limited vty lines, and Oxidized, the drift checker, the ping worker and a nine-device batch can all want the same device at once". **With more than one worker every device is submitted before any result is back, so the breaker cannot stop the rest** (its own comment) | Gains batches: concurrency inside a batch, the breaker between batches (section 7.1). This is the change that lets a bulk run be both concurrent and stoppable |
| Holds | `modules/nsot/device_ops.acquire_many` / `release_many`, `hold`, `busy_text`, `interrupted` | One operation per device across processes; a busy device is refused alone with its holder named. `apply_batch` holds every device for the whole batch | Held per batch, not per run (section 7.2) |
| Reload | `modules/nsot/reload_op.plan` / `judge` / `run`, `routes/device_v2.reload_card` / `reload_start` / `reload_confirm` | Preview reads the device (`read_device`) and judges six gates; the confirm carries a reason and the preview's fingerprint; the run re-reads and refuses if the fingerprint moved, **declares its planned-restart window before sending** (`restarts.record_planned`), reloads, waits for SSH bounded by `wait_bound` (2.5 × `BOOT_SECONDS`: IOS-XE 390 s measured, IOS unmeasured with the 900 s placeholder), ends the window early on return, verifies, and records one committed row (`reload_op.record`) | Called once per device by the bulk run; nothing reimplemented |
| Planned-restart windows and their silences | `modules/restarts.record_planned` (refuses a window after the restart it covers unless a correction), `silence_window` (C1025: Grafana silences per window, plus `SETTLE_SECONDS`), `end_window`, `holding`; `POST /restarts/planned` (`routes/restarts.planned`) | One writer for windows | Unchanged; the guardrails read `holding` |
| Blast radius | `modules/nsot/blast_radius.radius` (pure) / `for_device` | From committed intent's subnets and this host's addresses: the devices Mercury loses reach to while one restarts; `state` `known` (with `cut`) or `unknown` (with why); a switch's VLAN subnets go down with it; a layer-2-only carrier is not seen (`CAVEAT`) | The management-path guardrail (section 8.3) |
| Drained | `modules/drained.py` (`ENABLED = False`, C552); [NSOT_DRAINED_DESIGN](NSOT_DRAINED_DESIGN.md) re-labelled by the charter: NetBox's status is the fact | The measured badge is off; the NetBox custom status is designed, not built | The guardrail reads NetBox's status (section 8.4) |
| Scheduled rotation | `modules/nsot/scheduled_rotation.py` | "Rotate due devices now" and a timer: one at a time, at most K a run, the first failure stops the run, never two runs at once (an exclusive `flock`), never inside a no-change window (`no_change_windows`, the installation's setting since C1317) | The bulk form of Rotate, unchanged; its single-run rule is copied (section 7.6) |
| Fan-out reads | `modules/fanout.read_each`, `MAX_WORKERS = 16` ("a cap and not a measured optimum") | Concurrent reads across devices | The Reload preview's reads; the ceiling on any batch size |
| Jobs | `modules/nsot/capture_job.start` / `get` (in memory, `KEEP_S` 1800, a restart loses a job and says so) | Every long operation's job | The bulk preview and run are jobs; the run also writes its own record (section 7.7) |
| Announcements | `modules/invalidation.announce(keys, by, ok)`; `modules/deploy_job` `PROGRESS_KEYS` / `DONE_KEYS` | Panels re-fetch on a key | A run announces per device step and per batch |

## 3. Every device action, judged for bulk

"Exists" means a bulk form is built today and the frame only moves its selection onto the
filter; "Yes" is new; "Later" is sound but not first; "No" says why it stays one device at a
time.

| Action (where it lives) | Bulk | Why |
|---|---|---|
| **Plan a deploy…** (`_actions_menu.html`; `routes/device_v2.deploy`) | **Exists** | Devices › Plan a deploy for the ticked devices, `routes/deploy.apply_batch`. Moves onto the filter selection, the server-held plan and batches. Disruptive in its effect (it changes running configuration), so it takes the guardrails of section 8 except the restart window, which it does not need. |
| **Capture** (`routes/device_v2.capture`) | **No, as itself; Save is its bulk form** | Recording a golden without saving to startup is deliberately not offered in bulk: "the record would say one thing and a reboot bring another" (`save_op` docstring). One device's Capture stays for recording a hand change before deciding. |
| **Seed intent…** (`routes/device_v2.seed`; `modules/nsot/seed.py`) | **Later** | Commits only, sends nothing, and the selection is natural (intent state `no_intent`, `device_list.STATES`). Each device's document still wants reading: the preview would group by what the template cannot reproduce. After the frame, for brownfield fleets. |
| **Restore from…** (`routes/device_v2.restore`) | **Exists for one moment across the network; No for per-device moments** | History › re-apply a baseline (`deploy_job.start_restore`) is the bulk form. Choosing a different moment per device is a person's judgment per device. Re-apply is disruptive: it takes section 8's guardrails. |
| **Remove lines (Mode B)…** | **No** | Mode B is a person selecting each unit with a reason, and only a shape measured to remove exactly itself (`modules/nsot/removal.py`). The same removal on hundreds of devices is an intent or template change, then a deploy. |
| **Revert intent…** / **Retry rolled-back change…** (`routes/device_v2.revert`, `retry`) | **No** | Each is offered only while a rollback blocks one change on one device (`routes/device_v2._block_state` → `intent_ops.block_state`). They answer one change. |
| **Rotate credential…** (`routes/device_v2.rotate`; `modules/nsot/rotate_op.py`) | **Exists, as scheduled rotation** | `scheduled_rotation.py` runs `rotate_op.run` one device at a time, first failure stops, by profile policy, with "Rotate due devices now". A filter-built rotation would be a second path; the most it should ever be is that runner handed a filter (Later, only if asked). Rotation is one at a time because a failed rotation can leave a device unmanageable (`rotate_op` docstring, B15, C53, C106). |
| **Persist** (`routes/device_v2.persist`; `persist_op.py`) | **Exists, as Save** | Save is built from `onboard.persist_on_device`, the one save (`save_op` docstring), and records the golden in the same step. |
| **Run a privileged command…** (`routes/privileged_v2.py`; `modules/nsot/privileged.py`) | **Later, the argument-free commands only** | `clear logging` and `undebug all` take no argument; `clear counters` and `clear arp-cache` take an interface from each device's own golden and refuse the management one, so their argument is per device by construction. Each run keeps its before-state (T2-4), so a fleet-wide clear keeps a thousand before-states: measure its size first. The agent never runs one (T2-3). |
| **Reload…** (`routes/device_v2.reload_card`; `reload_op.py`) | **Yes, new, with guardrails** | A fleet reload is a real need (an image or a boot change rolled out, a memory leak cleared). It is the most disruptive action: sections 8 and 9 are mostly about it. |
| **Retire…** (`routes/device_v2.retire`; `modules/nsot/retire.py`) | **No** | It clears the credential, removes intent and golden, releases the identity and masks NetBox's stored context: an exit, each a person's decision. A decommission of many devices starts as NetBox's status (the charter: NetBox owns a device's existence); retiring them stays one at a time. |
| **Re-key host key** (`routes/device_v2.rekey`; `rekey_op.py`, C906) | **No** | A changed host key is a rebuild or an attack, judged on two fingerprints by a person. The legitimate bulk case, a redeploy, is already a planned-restart window with `new_host_keys` (`restarts.record_planned`). |
| **Reveal a golden's secrets** (`routes/device_v2.golden_reveal`) | **No** | A person reading one device's secrets; a bulk reveal would be an export, which Credentials › break-glass export already is, under its own controls. |
| **Edit intent / Acknowledge / Reopen** (`routes/intent_v2.py`) | **Edit: exists** (Change a setting on N, `routes/bulk_intent_v2.py`); **Acknowledge, Reopen: No** | An acknowledgement is one device's departure judged by a person. |
| **Decline a profile section** (`routes/v2.decline_card`; `decline.py`, C718) | **No** | A decline is one device's exception with a reason. The same exception on hundreds of devices is a profile change (Monitoring › Profile, `routes/v2.profile_propose_commit`). |
| **Apply the monitoring profile** (Coverage, `/v2/monitoring/apply`) | **Exists** | The batch Apply's own scope, on the same `apply_batch`. |
| **Show commands / Ask** (`routes/reads_v2.show_commands`) | **Exists** | Reads, many devices at once, on the reads engine. Not part of this frame: reads change nothing and need no confirm. |
| **Adopt / Onboard** | **Not a bulk of existing devices** | They bring devices in; Onboarding has its own list flow. |

So the frame's first actions are **Deploy, Save and Change a setting** (moved onto it) and
**Reload** (new). **Re-apply a baseline** moves onto it next. Seed and the argument-free
privileged commands are later candidates. The rest stay per device.

## 4. Selection: a filter, resolved by the server

**What the person builds.** On Devices, the filter bar gains **site** and **role** and
**status** beside today's search, intent state and platform:

| Filter | Read from | Notes |
|---|---|---|
| search | name or address substring (`device_list.listing`'s `q`) | as today |
| intent state | `device_list.intent_state` | as today |
| platform | `platform.platform_for_device` | as today |
| role | the inventory row's `role` | NetBox's role for a NetBox-sourced network; the local CSV's column otherwise |
| site | the inventory row's `_site` (NetBox) | a local network has no site until [SITES_DESIGN](SITES_DESIGN.md) is built (FUTURE); the filter says "every device is in this network's one site" rather than offering an empty choice |
| status | NetBox's device status (active, planned, offline, drained once C551's status exists) and reachability (answering, not answering) | two facts, drawn as two filters, never merged |

Ticking stays for small selections. **"Select all N matching"** selects the filter itself,
across every page. A selection is then a small object:
`{list, filter: {q, state, platform, role, site, status, reach}, except: [names]}` where
`except` holds the rows the person unticked from a filter selection (bounded: at most one page,
50; more than that is a narrower filter).

**The server resolves it, twice.** The preview resolves the filter against the inventory with
the same function the list draws with (`device_list.listing`, extended with the new filters;
one resolver, CLAUDE.md "one owner"), and records the **set hash**, a sha256 over the sorted
device names. The confirm resolves the filter again. When the two sets differ, the confirm is
**refused with nothing sent**, naming both operands: "the filter now selects 642 devices; the
preview planned 640. Joined since the preview: sw-acc-0901, sw-acc-0902 (onboarded at 01:12
UTC). Left: none. Preview again." A device the filter gains after the confirm is never added to
a running batch; one that leaves the inventory mid-run is refused alone at its turn ("not in
the inventory now").

**Never hundreds of names from the client.** The preview's plan is held by the server under a
plan id (in memory, as `capture_job` holds a preview, `KEEP_S` 1800); the confirm sends the
plan id, the filter, the set hash and the plan hash, nothing per device. This removes the
per-device fields today's confirms carry (`CONFIRM_JSON_FIELDS` for Deploy; the `device`
fields `routes/v2.save_confirm` reads for Save) once those paths move onto the frame. A restart
loses the plan, and the confirm says so: "the preview this confirm names is gone (the app
restarted at 01:40 UTC); preview again."

## 5. The preview

Computed as a job (section 9), drawn in place, the person's question first:

1. **One line that answers**: "Reload 611 of the 640 selected, in 106 batches; 17 refused and
   12 left out, each named below. About 14 h at 6 a batch."
2. **Counts by outcome**, the action's own groups: for Reload, *will reload*, *refused* (a gate
   fails: by gate), *left out* (by guardrail), *acknowledged departures* (gate 2's `ack`).
3. **The guardrails, each with what it found** (section 8): pairs found and how they were split,
   path devices and their batches, devices left out and how each clears.
4. **The batches**: the canary, then each batch's devices and its estimated time, collapsed.
5. **Each device's exact plan one level down**: for Reload its six gates as `reload_op.judge`
   drew them and its batch; for Deploy its masked program (the existing per-device preview,
   `preview_confirm.deploy_preview`); for Save its row from `save_op.plan`. Groups are
   collapsed and searchable, with an outcome filter, 50 rows a page inside a group.
6. **What will not happen and why**, stated: nothing is sent to a refused or left-out device; a
   reload cannot be undone (no rollback, `reload_op` docstring); devices that join the filter
   later are not added.
7. **The confirm**: the reason (required, three words or more, as Tier 2's T2-2), the batch
   size, the latest time a batch may start, and one button naming the work: "Reload 611
   devices in 106 batches". A refused group carries its remedy as a control that opens that
   action on that group by the plan id (for unsaved changes: "Save these 9 first…", which opens
   Save on them; the Reload preview is drawn again afterwards).

## 6. The confirm, by hash

The plan hash is a sha256 over a canonical JSON of: the action; the network; the filter; the
set hash; every device's own plan hash (Deploy's `command_fingerprint`, Reload's
`judge(...)["fingerprint"]`, Save's plan hash), sorted by device; the batch plan (the ordered
batches); the options (batch size, latest start); the reason; and the confirming person (a
verified person, as every confirm is: `modules/route_gates.py`). Changing the batch size or
the latest start redraws the batch plan and its hash; the button is bound to what is drawn.

At the confirm the server re-resolves the set (section 4) and recomputes the batch plan from the
same inputs; a different plan hash refuses, naming what moved (the set, a device's plan, or the
guardrail inputs: "rtr-edg-0117's VRRP peer changed: intent committed at 01:20 UTC"). At each
device's turn, its own operation's apply-time check runs as it does for one device today
(`apply_batch`'s recomputed command hash; `reload_op.run`'s fingerprint re-read): a device that
moved is refused alone, nothing sent to it, and it does not count as a failure (as
`CircuitBreaker.counts` treats drift).

## 7. The run

### 7.1 Batches and their concurrency

`run_batch` gains **batches**: a list of batches, each run with up to its size concurrently;
the breaker is judged when a batch ends, and no batch starts after it trips. One batch of one
device per batch is today's sequential behaviour exactly, so Deploy keeps its behaviour by
default. The loop moves into one function the three paths share (the deploy batch, Save's pool
in `save_op.run`, and the bulk Reload), so "a batch" means one thing.

Defaults per action, each inherited and named on the screen as inherited:

| Action | Default batch size | Where it comes from | Ceiling |
|---|---|---|---|
| Deploy | `deploy_max_workers` (default 1) | the network's setting; its reason (vty lines, many readers wanting one device) still holds | 16 (`settings_schema`) |
| Save | 6 | `save_op.WORKERS`, Show commands' cap (C605), not measured | 16 |
| Reload | a **canary batch of 1**, then **6** | nothing measures reload concurrency, and a reload's session is short (most of its time is the device booting), so vty lines do not bound it; 6 is the operator's own cap on concurrent device work (C605), named on the preview as a placeholder until a bulk reload's record measures it | 16 (`fanout.MAX_WORKERS`) |

The canary exists because the first device measures the boot on this network: a reload that
does not come back stops the run with one device down instead of six.

### 7.2 Holds

A device is held (`device_ops.acquire_many`) **at the start of its batch** and released when
its record is written, not for the whole run. `apply_batch` holds every device for the whole
batch today; across a run of many hours that would refuse every other operation (Save, the
scheduled rotation, a person's Capture) on a thousand devices for the night. A device another
operation holds when its batch starts is refused alone, naming the holder, and never queued
(CLAUDE.md "one operation per device"); a refusal is not a failure.

### 7.3 Stop on first failure

Every bulk run uses `CircuitBreaker(limit=1)`, the rule Coverage's combined deploy already uses.
When a device fails, the devices already working in its batch finish (a reload sent cannot be
called back; a push already in progress verifies and rolls back as it does today), no further
batch starts, and every device not reached is "not attempted — the run stops at its first
failure, which was on X" (`CircuitBreaker.reason`).

What failure means, per action:

| Action | Failure (counts) | Not a failure (refused alone, nothing sent) |
|---|---|---|
| Deploy | `CircuitBreaker.counts`: not deployed, or a verify that did not pass (C10) | drifted at apply (C78), program hash moved, held |
| Reload | `reload_op.run` outcomes `unread`, `no_window`, `not_reloaded`, `not_back`, `unverified`, `differs`; and, in bulk only, a Grafana silence that failed where Grafana is configured (section 8.1) | `moved` (fingerprint changed), `refused` (a gate fails now), `busy` |
| Save | — | Save keeps going (as `save_op.run` does today): a failed save harms no other device and leaves the device as it was. Its result is partial and says so. **Answered (question 3, the operator, 2026-10-18):** Save keeps going, and its partial result says so |

The person can also **Stop after this batch**: no new batch starts; the working devices
finish. A mutating route, declared in `route_gates.py`, a person only, recorded.

### 7.4 Progress, by announcement

The run announces a key (`bulk_run`) through `invalidation.announce` when a device steps and when
a batch ends; the card re-fetches its summary and whichever group is open. No polling. Each
device's steps are its operation's own stepper (`reload_op.STEPS`; `save_op.DEVICE_STEPS`;
the deploy's), drawn on expand; the in-flight panel (`modules/in_flight.py`) shows the run with
its batch and the devices working now.

### 7.5 The result

It leads with what to act on, never with the counts: "Stopped at batch 9 of 106: rtr-edg-0117
did not answer on SSH's port within 16 min 15 s. Its VRRP peer rtr-edg-0118 carries the group
alone and was not attempted." Then the counts (reloaded and verified, failed, refused at their
turn, not attempted, left out at the preview), then the batches, collapsed. **Green only when
every device of the selection ended in the action's good outcome and none was left out at the
preview**; a run that did all it planned but planned less than the selection is amber, and
says how many were left out and where they are named. Controls: open the failed device's page,
**Plan the rest…** (a new preview over the run's not-attempted devices, by run id, never by a
list of names), the run in History.

### 7.6 One disruptive run per network

At most one bulk run of a disruptive action (Reload, Deploy, Re-apply) runs in a network at a
time, refused by name across processes (`scheduled_rotation`'s exclusive lock, the shape that
exists). The pair and path guardrails are computed for one run; two runs could each be safe and
together reload both members of a pair. Save and Change a setting are not limited this way.
**Decided (question 8, the operator, 2026-10-18):** one disruptive bulk run per network at a time.

### 7.7 The record

Each device's record is its operation's own: Reload's committed row (`reload_op.record`),
Deploy's receipts and golden commit (`apply_batch`), Save's commit and persist rows. The run adds
**one record of its own**, written when it starts and again when it ends (`.nsot/bulk_runs.jsonl`
in the network's repository, through `repo._commit_paths`, the one commit path): who, why, the
filter, the set and plan hashes, the batch plan, each device's outcome, and where it stopped.
History draws the run as one row that expands to its devices.

**A restart mid-run.** The job is in memory and is lost; the holds are files, and
`device_ops.interrupted` already records a hold left behind. The run's start record without
an end is a Needs attention row: "Bulk reload by operator@example.com stopped when the app
restarted at 02:10 UTC, during batch 9 (6 devices, each possibly mid-reload): open each to see
whether it came back. It clears when a person ends the run's record, or Plans the rest." It is
never resumed by itself.

## 8. Guardrails for disruptive actions

### 8.1 The planned-restart window, and its silence

Each device's window is declared by `reload_op.run` before its reload is sent, as today, with
its Grafana silence (`restarts.silence_window`), and ended when the device returns. The bulk run
adds no second writer of windows. In bulk, a silence that failed where Grafana is configured
counts as a failure and stops the run after that batch: one device alerting is a row, a
thousand is a storm. "Grafana is not configured for this network" is said on the preview and
does not stop anything. A Re-apply or Deploy restarts nothing and declares no window.
**Agreed (question 7, the operator, 2026-10-18):** a failed silence stops a bulk Reload
(planned-restart windows' silences, C1025), never a single one.

### 8.2 Never both members of a redundant pair

**Found from committed intent**, in one pass over every device's `host_vars`
(`neighbours.committed_intents`, which `blast_radius.for_device` already uses):

- **VRRP**: `interfaces[].vrrp_groups[]` (the address-family form: `group`, `family`,
  `settings`) and `interfaces[].vrrp` (the line form), as `parsers/base.py` emits them.
- **HSRP and GLBP**: `standby` and `glbp` lines have no handler in `parsers/base.py`, so the
  parser keeps them verbatim in the interface's `unmodeled` list
  (`hostvars.INTERFACE_DEFAULTS`); they are matched there by an anchored pattern
  (`^standby\s+(\d+)\s+ip\s+(\S+)`), never by a substring.
- **Two devices are a redundant pair (or group)** when each has an interface in the same
  subnet (from its `ipv4` or `ipv6`) carrying the same group number. A group with three
  members is a group: at most one member per batch.

**What happens:** members of a group never share a batch; batches run in order and a batch ends
only when every device's verify has ended, so the second member starts only after the first is
back and verified. A member whose peer **outside the selection** is not answering now, is held,
or is inside a planned-restart window (`restarts.holding`) is **left out**: reloading it would
take the group's last member down. At its batch's start this is checked again, so a peer that
went down during the run refuses the device then.

**When it cannot be read, refuse, never guess.** A device with no committed intent, intent that
could not be read, or an `unmodeled` line beginning `vrrp`, `standby` or `glbp` that the pattern
does not parse is **refused in bulk** ("whether rtr-x has a redundancy peer could not be read:
<why>"), with its remedy: Seed intent, or reload it alone from its own page.

**What intent cannot show** (said on the preview, as `blast_radius.CAVEAT` is): redundancy
without a first-hop protocol (two route reflectors, dual-homed links, a stack). **Answered (question 1, the operator,
2026-10-18):** a redundancy group is declared in NetBox, as a custom field or tag naming the group.
NetBox owns identity and role.

### 8.3 Never the management path's device alongside others

**How it is known: measured, never named.** `blast_radius.radius` already answers it for one
device: the devices Mercury loses reach to while it is down, from committed intent and this
host's own addresses. A device whose `cut` is non-empty **carries the management path**. The
product never keys on a hostname: the lab switch that carries the path today is found by this
measurement, and any network's is.

**The rules:** a path device runs in a batch **alone**; no device in its cut shares its batch;
path devices run **last**, the one with the smallest cut first, so that if one does not come
back the run has already done everything it can still reach, and the result names the devices
now cut off. A device whose radius is `unknown` (no committed intent; this host's networks
unreadable; no subnet of this host's holding any device) is treated as a possible path device:
alone. When every device's radius is unknown, every batch is one device, and the preview says
so with the reason.

**The layer-2 gap:** a switch carrying the management VLAN with no address in it is not seen
(`blast_radius.CAVEAT`). **Answered (question 2, the operator, 2026-10-18):** a declaration in NetBox, as for redundancy,
which may only ADD a device to the path set, never remove one the measurement found. CLAUDE.md's rule that "a change to the path the tool reaches a device on
needs a repair route independent of that path" applies: the preview of a run that includes a
path device names the repair route (console, out-of-band) as the person's to confirm in the
reason, not Mercury's to provide.

### 8.4 Drained, other windows, held devices, no-change windows

- **Drained**: the measured badge is off (`drained.ENABLED = False`, C552), and the charter
  makes NetBox's status the fact. Once C551's custom status exists, a device NetBox calls
  drained is **left out of a bulk action by default** (someone took it out of service on
  purpose; its runbook, P.22, brings it back), named, with "Include drained devices" offered
  with a stated reason. Until then nothing is called drained. **Answered (question 4, the operator,
  2026-10-18):** left out by default, as designed.
- **Another planned-restart window** covering a device now (`restarts.holding`): left out,
  naming the window's declarer and end.
- **Held** at the preview (`device_ops.busy_text`): left out, naming the holder; at its batch's
  start, refused alone.
- **No-change windows**: no batch starts inside one, and no batch starts that its estimated time
  (the wait bound plus the read and verify) would carry into one; the run ends there as
  "stopped: a no-change window begins at 02:00 UTC", the rest not attempted, with Plan the rest….
  **Answered (question 5) by C1317, 2026-10-18:** the windows are the installation's setting,
  `no_change_windows` (`modules/change_windows.py`), empty by default. The scheduled rotation
  already reads it, and a bulk run reads the same one home. The constant left the product.
- **The person's own window**: "start batches until" on the confirm, judged the same way.

### 8.5 The maximum blast radius per batch

Three bounds, each drawn on the preview with its value:

1. **The batch size** (section 7.1).
2. **At most a quarter of any site-and-role group in one batch** (rounded down, at least one):
   four access switches at a site go one at a time; forty go ten at a time if the batch size
   allows. A placeholder named as one on the preview, until measured (question 6, the operator,
   2026-10-18).
3. **Path devices alone** (8.3) and **redundant members apart** (8.2).

### 8.6 The batch planner

Deterministic, so the same inputs give the same plan and the same hash:

1. Remove the left-out and refused devices (each named with its reason).
2. Put the path devices aside (8.3).
3. Batch 1 is the **canary**: the first remaining device in (site, role, name) order.
4. Fill batches in (site, role, name) order: a device joins the current batch if the batch is
   under its size, holds no member of the device's redundancy group, and stays within the
   site-and-role quarter; otherwise the next device is tried; when none fits, the batch closes.
5. Append the path devices, one batch each, smallest cut first.
6. Estimate each batch as its slowest member's `reload_op.wait_bound` plus the read and verify
   (measured once, section 9), and the whole run as their sum; mark the batches that fit before
   the person's latest start and the next no-change window.

## 9. At 1,000 devices

**What must be a job** (anything that can pass Cloudflare's 100 s edge limit, as `capture_job`'s
docstring measured): the preview's per-device plan (Reload reads every device, `read_device`, a
session each, through `fanout.read_each` at 16); the Deploy plan (`plan_devices` at 1,000: not
measured); the guardrail computation (one `committed_intents` read, then `blast_radius.radius`
per device, which is pure, so the intents are read once); and the run.

**What the screen draws:** the one-line answer, the counts, the guardrails' findings, and
collapsed groups; per-device detail on expand, 50 rows a page inside a group, a search and an
outcome filter (the large-fleet rule; `tests/test_large_fleets.py` must hold the new pages with
no excuse). The Devices list itself needs C450's paging and summary before "Select all N
matching" means anything.

**Timings to measure first, before any default is set:**

| Measure | Why | Where |
|---|---|---|
| A Reload preview's read per device, per platform | the preview's length at 1,000 | a bulk preview of the lab's devices |
| A `cisco_ios` reload, to SSH answering | `reload_op.BOOT_SECONDS["cisco_ios"]` is unmeasured (900 s placeholder); every IOS estimate rests on it | one reload of an IOS device, its record |
| `plan_devices` at 900 devices | whether a bulk Deploy's preview fits a job's patience | `tests/test_scale.py`'s fleet, timed |
| The guardrails at 900 devices | radius per device and the pair pass | the same fleet |
| One reload record's commit and publish (`reload_op.record`) | a thousand commits and pushes in a run; whether a batch's records should share one commit | the host |
| Grafana silences for a batch of 16 | `silence_window` puts one or more per device | the host's Grafana |
| The card's redraw on each announcement, with 16 devices stepping | whether announcements need coalescing | a browser on the host |
| `device_ops` holds folder with 1,000 entries | per-batch holds come and go all night | the suite's scale fleet |

**What a run takes**, from the one measured boot (IOS-XE, 390 s, bound 16 min 15 s): about 8
minutes a batch, so 611 devices at 6 a batch (106 batches) is about 14 hours and at 16 a batch
(42 batches) about 6 hours. The preview says this before the confirm, so a run that cannot fit
its window is seen before it starts.

## 10. Where a wrong thing could look right

| Feature | Wrong, looking right | What makes it visible |
|---|---|---|
| Filter selection | the filter moved between preview and confirm, and the confirm ran a different set | the set hash, refused, naming joined and left |
| Pair guardrail | a pair the parser cannot see (HSRP in an unexpected form) reloaded together | an unparsed `vrrp`/`standby`/`glbp` line refuses the device; the caveat is drawn |
| Path guardrail | a layer-2 carrier not seen, batched with the devices behind it | the caveat drawn on every preview; the declaration (open question 2) |
| Progress | a stalled job drawn as "running" | the stepper's per-step time and `device_ops`'s `STALL_AFTER_SECONDS`, as today |
| Result | "611 reloaded" over a run that left 12 out | amber, never green, while anything was left out |
| Stop | a batch that tripped while concurrent devices kept going | the result names which devices were already working and finished |

## 11. Out of scope

Scheduling a bulk run for later (a person confirms and watches it; a timer is the rotation's
model, not this); rollback of a reload (none exists); bulk Retire, Re-key, Mode B, Revert, Retry
(section 3); actions across networks (SITES_DESIGN's "read across, write within"); an
image upgrade (a reload with a new boot file is NSOT_REVERT_BY_RELOAD's and a later design's).

## 12. Open questions for the operator

**ANSWERED by the operator, 2026-10-18 (evening). The build waits for Core 1.0's order.**
1. **Redundancy without a first-hop protocol:** declared in NetBox, as a custom field or tag
   naming the redundancy group. NetBox owns identity and role.
2. **The layer-2 management-path gap:** an add-only declaration, in NetBox as in 1.
3. **Save after a failure:** Save keeps going (today's behaviour), and its partial result says so.
4. **Drained devices:** left out of bulk actions by default, as designed.
5. **No-change windows:** answered by C1317. They are the installation's setting,
   `no_change_windows` (`modules/change_windows.py`), none by default.
6. **The per-batch bounds:** a canary of 1, then 6, a ceiling of 16, and a quarter of a
   site-and-role group. These are placeholders until measured, and the preview names them as
   placeholders.
7. **Agreed:** a failed Grafana silence stops a bulk Reload (planned-restart windows' silences,
   C1025). It does not stop a single Reload.
8. **One disruptive bulk run per network at a time.**

The questions as they were asked:

1. **Redundancy without a first-hop protocol** (route reflectors, stacks, dual-homed pairs):
   declare a redundancy group, and where: a NetBox tag or custom field (NetBox owns identity and
   role), or a committed intent key?
2. **The layer-2 management-path gap**: a declaration that can only add a device to the path set,
   and where it lives (as 1)?
3. **Save and the first failure**: keep Save going (today's behaviour), or stop it too?
4. **Drained**: left out of bulk actions by default (as designed), or preferred for a Reload?
5. **No-change windows as a network setting**, moving `scheduled_rotation.BACKUP_WINDOW` into it
   (and out of product code)?
6. **The per-batch bounds**: a canary of 1, then 6, ceiling 16; a quarter of a site-and-role
   group: as placeholders until measured?
7. **A failed Grafana silence stops a bulk Reload** (it does not stop a single one): agreed?
8. **One bulk run per network for disruptive actions**: or per action?

## 13. The order to build it in

1. Measure (section 9's table); nothing is defaulted before.
2. C450: the Devices list's summary, paging and the site, role and status filters.
3. The selection object and its server resolution, with the set hash; Save and Change a setting
   moved onto it (no new action yet, two existing ones lose their name lists).
4. Batches in `run_batch` (one function for the deploy, Save and Reload), per-batch holds, the
   breaker at limit 1; bulk Deploy moved onto the frame.
5. The run record, the interrupted row, Stop after this batch, Plan the rest….
6. The guardrails: pairs, path, left-out devices, no-change windows, the planner, with tests
   each shown able to fail.
7. Bulk Reload: preview job, confirm, run, result; its manual pages ("How it works" for the
   batch frame and for bulk Reload); the board compared with the built page
   (`tests/test_board_fidelity.py`).
8. Re-apply a baseline onto the frame.
9. Later candidates: Seed intent, the argument-free privileged commands.

## 14. The board

[boards/bulk-actions.html](boards/bulk-actions.html), at 1440 wide, every control the built
screens would have: **A**, Devices filtered to 640 devices with "Select all 640 matching" and
the bulk Actions menu (rows offered, and the actions not offered in bulk with why); **B**, the
bulk Reload preview (the answer line, counts by outcome, the guardrails: a VRRP pair split
across batches 7 and 8, the path devices held to their own last batches, drained devices left
out, the windows; the batches; a device's six gates on expand; the reason, batch size, latest
start and the confirm naming the work); **C**, the run stopped at its first failure (the
answer, the peer left carrying its group alone, the batches with their outcomes, the failed
device's steps, and Plan the rest…), with the running state's header and its Stop after this
batch. Example names and 192.0.2.x addresses only.
