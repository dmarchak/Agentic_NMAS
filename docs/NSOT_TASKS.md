# The tasks, and who the interface is for

Written 2026-09-26, before the Stage 7 GUI plan, which is to be organised
around this list rather than around the subsystems the current tabs are named
after. Derived from every route in `app.url_map` (236 rules, 227 paths),
every script in `scripts/`, the current UI, and the plan. Each task is a thing
a person SETS OUT TO DO.

## 1. Who the interface is for

**A network engineer who knows networking, infrastructure as code,
intent-based networking, sources of truth, drift and CI, and has never seen
THIS tool** (the operator's decision, 2026-09-26). This is agreed, with one
refinement below. It is also what makes the tool defensible as coursework: a
stranger can operate it without its author in the room.

**It does not teach networking. It teaches this tool's model**, meaning the
concepts a competent stranger would get wrong:

| Concept | What a stranger assumes | What is true here | Where the interface must show it |
|---|---|---|---|
| **Intent vs device** | The device is the truth, and you edit it | Intent lives in git (`host_vars`); the device is compared against it | Every device view shows intent, device and the difference as three things |
| **Golden vs capture** | A golden is the target config | A golden is an APPROVED CAPTURE of the device, a record rather than a target. The target is intent rendered by a template | Golden history is labelled a record, not a desired state |
| **Merge-only** | A deploy makes the device equal the intent | It only ADDS. Lines on the device that intent lacks are residue, reported and never removed | The deploy plan draws residue as "will NOT be removed" |
| **Preview, then confirm by hash** | Confirm means "go" | Confirm means *this exact program*. If anything moved, it refuses | The confirm screen shows the program, not a diff (D4), and says what a refusal means |
| **Template approval binds to a device set** | Approval is a property of a template | It is a fingerprint of template plus bound devices. Onboarding a device revokes it | The approval badge says what it covers, and why it was revoked |
| **Provenance decides what Remove can touch** | Remove deletes what you point at | It deletes only what NMAS created and recorded | The Remove preview names what it will skip, and why |
| **Pending vs promoted** | A created device is managed | It is managed when the tool has REACHED it | The pending banner, with the three verification states |
| **Merge-only cannot remove** | Revert means undo | Reverting intent is a forward commit, and removing config needs Mode B, which is not built | The revert preview says what it will not undo |
| **A baseline is earned** | A baseline is a snapshot | It is a claim that the network MATCHES a commit, and it is measured | Versions shows why a baseline was, or was not, earned |

**The refinement: teach at the point of action, not in a tutorial.** A
stranger reads the screen in front of them, not the manual. Each concept
above is taught by the screen where it has a consequence: the deploy plan
teaches merge-only by drawing residue, and the Remove preview teaches
provenance by naming what it skips. The expert is served by the same
screens, dense by default, with the explanation one expansion away rather
than in the way. That is one product, not two.

## 2. The task list

Where a person can do it today:
- **GUI**: from a page;
- **CLI**: a script only;
- **curl**: a route no page calls;
- **AI**: the AI chat only (whose tools have never run);
- **none**: not possible yet.

The audit's verdict follows (docs/NSOT_FEATURE_AUDIT.md) where it changes
the task.

### A. Is anything wrong?
| Task | Today | Note |
|---|---|---|
| See which devices are up or down | GUI | |
| Check whether devices have drifted from their golden | GUI (on the Approvals tab) | Scheduling is off (E4) |
| Schedule, disable or re-enable drift checking | GUI | |
| See whether Oxidized's copy of each device is the approved one | GUI, CLI | |
| See whether the integration stack is up | GUI | |
| **See whether scheduled jobs, VM images and pools are healthy** | **CLI, curl** | `nmas-jobs`; 9 rows now |
| Be alerted when a device goes silent | CLI (the alert lives in Grafana) | |
| **Find out why a device went silent** | partly; the core views are **none** | per-device logs, metrics and neighbours (7.5) |
| See what needs a person: approvals, pending onboardings, rollback-blocked devices | GUI, GUI, **curl** | |
| See round-trip template coverage for the fleet | curl | C2 |
| See whether a list's templates are stale seeds | curl, CLI | |
| See a NetBox-sourced list's freshness and skips | GUI | |

### B. What is going on with this one device?
| Task | Today | Note |
|---|---|---|
| Open the device's page | GUI (only while it is online) | |
| Run a show command or a saved quick action | GUI | |
| Open a terminal | GUI | UNDECIDED: keep gated and labelled |
| See its golden history, a version, or a diff | GUI (masked); reveal is curl | |
| See its committed intent | GUI | |
| Preview its template render and coverage | GUI | |
| See its neighbours and adjacencies | GUI (Topology tab) | UNDECIDED |
| See its metrics, logs, Oxidized history and leases | **none** | 7.5, Grafana embedded |
| See which credential source it resolves to | **none** | |
| Look it up in NetBox | curl, AI | |
| Ask the AI about it | GUI | depends on the agent decision |

### C. Change the network
| Task | Today | Note |
|---|---|---|
| **Seed intent for a device that has none** (extract, review, commit) | **curl** | The editor tells you to; no control does it |
| Edit one device's intent, preview, commit | GUI | |
| **Apply one change to many devices' intent** | **CLI** | `nmas-bulk-intent` |
| Plan a deploy and see the exact program | GUI | shows the diff, not the program (D4) |
| Deploy confirmed intent | GUI | ungated (B12) |
| **Deploy several devices in one batch** | **curl** | |
| **Authorise a dangerous line** | **curl** | undeployable from the GUI (D4) |
| **Retry after a rollback** | **curl** | |
| **Revert one intent commit** | **curl** | |
| Remove configuration through intent | **none** | Mode B |
| Configure a feature from a form (about 90 types) | GUI (a direct push) | UNDECIDED: absorb into intent authoring |
| Run a command on many devices | GUI | enable mode KEEP; config mode CUT |
| Reload devices | GUI | KEEP, gated |
| Save running config to startup | GUI (two buttons) | keep one |
| Move files to, from or off flash | GUI | KEEP, gated |
| **Rotate a device's credential** | **CLI** | |
| Approve or reject a queued action | GUI | ungated (B12) |

### D. Undo, restore, recover
| Task | Today | Note |
|---|---|---|
| Re-apply a network-wide baseline | GUI | the preview's coverage is wrong (C23) |
| **Restore one device to its golden, guarded** | GUI only via an approval item | the unguarded replay has two buttons (D5) |
| Restore from a stored backup | GUI (an unguarded push) | CUT |
| Back up a device now | GUI | ABSORB into captures |
| Get back into a locked-out device | CLI (break-glass) | |
| Escrow credentials and the key; verify; restore the key | CLI | |
| Back up NetBox; prove it restores; fetch an off-box copy | CLI, timers, and a documented procedure | P.2 |
| Undo NetBox values NMAS wrote; repair addresses | CLI | |

### E. Bring a device in, take one out, organise
| Task | Today | Note |
|---|---|---|
| Onboard a new device (plan, create, verify, promote, abandon) | GUI | |
| Onboard over DHCP | GUI, with the Kea reservation made outside | |
| **Adopt an existing, already-configured device** | GUI (adds a CSV row only) | ABSORB into onboarding |
| **Retire a device** | **CLI** | the GUI's Delete does the wrong thing (C11) |
| Create, switch or delete a network (device list) | GUI | |
| Make a list NetBox-sourced; set its filters | curl | |
| Refresh a NetBox-sourced inventory | GUI | |
| Reorder devices | GUI | fails on NetBox lists (D7) |
| Commit device renames into the repo | GUI | |
| Assign a device to a containerlab lab | **none** | |

### F. Keep the record
| Task | Today | Note |
|---|---|---|
| Capture every device as golden in one commit | GUI (Save All) | |
| Browse history; commit hand-edited files | GUI (Git tab) | |
| Publish history to a private remote; **connect a remote** | GUI; connect is **curl** | |
| Import into NetBox; remove NMAS-created objects (guarded) | GUI | legacy unguarded routes CUT |
| Keep lab startup files current; **authorise one Oxidized divergence** | CLI; authorise is **curl** | |
| Check a startup file applies with the current credential | CLI | |

### G. Keep the source of truth correct
| Task | Today | Note |
|---|---|---|
| Edit, validate and approve a template | GUI | |
| **Revoke an approval, with a reason** | **curl** | |
| **Change which template a device uses** | **curl** | |
| Take a NetBox census; see what a delete took; audit modifications and IP provenance | CLI | |
| Repair repository identity data | CLI | maintenance, not GUI |

### H. Credentials and secrets
| Task | Today | Note |
|---|---|---|
| **Define credential profiles; decouple a list's credentials** | **curl** | |
| Test a credential; survey orphaned overrides; audit secret storage | CLI | |
| Reveal a secret in a stored config (a person, audited) | curl | |

### I. Configure and run the tool
| Task | Today | Note |
|---|---|---|
| Configure and test integrations | GUI | Proxmox added (B6) |
| Global settings | GUI | secrets leak (B11) |
| See the identity posture; ratify defaults | GUI | the gate is not enforced where it matters (B12) |
| Configure Access, platform and role maps, labs, syslog | **none** (file only) | |
| Deploy new NMAS code to the host | host CLI | CI gate (docs/NSOT_CI.md) |

## 3. What the list says about the GUI

- **About 15 tasks are curl-only and about 25 CLI-only.** The curl-only ones
  are the defects: the GUI can put a device into a state that only curl can
  take it out of (rollback-blocked; an approval that cannot be revoked). The
  CLI-only ones divide into tasks the GUI should own (retire, bulk intent,
  rotation, adopt) and maintenance that should stay CLI (repairs, census,
  diagnostics).
- **No subsystem is a task.** Jenkins, NetBox, Ansible, Git, Oxidized, Kea
  and the AI appear only as the means to several tasks. That is the case
  against subsystem tabs, measured rather than argued.
- **Group A is one view.** Jobs, drift, freshness, heartbeats, approvals,
  pending onboardings and rollback-blocked devices are all *is anything
  wrong right now*, and today they sit in four places and two CLIs.
- **Every device-changing task shares one shape: preview, then confirm.**
  Deploy, restore, onboard, retire, bulk intent, NetBox import and remove
  are already built that way. The GUI should standardise it as one pattern:
  what will happen, what will NOT, the exact program, the operands, and a
  person to confirm.
- **"If a payload carries it, the screen shows it."** D4 (the wizard drops
  the program, `dangerous` and `attribution`), the pending banner's dropped
  list, and the jobs payload with no view are all the same failure. The
  7.0 invalidation map is half of the mechanical answer; a payload-to-render
  check is the other half, for the GUI plan.
