# Architecture

How Agentic NMAS is put together: entry points, modules, and the paths data
takes through them. See [NSOT_PLAN.md](NSOT_PLAN.md) for where it is heading.

*Corrected 2026-10-02:* the sections below were written at Phase 0. The statements that
stopped being true (Jenkins, `check_runner.py`, `/configure/apply`, the two golden stores,
the unwired pipeline, the agent's auto-continue, the persistence pipeline living outside the
repository) are rewritten in place, each saying what replaced it. The moved CLAUDE.md
narrative at the end of this file is the detailed, dated record.

---

## Entry points

| Entry point | Purpose |
|---|---|
| `app.py` | Flask app, SocketIO, all pre-existing routes. Creates `app`, registers blueprints, starts background daemons. |
| `routes/` | Blueprints for everything added from Phase 0 onward. |
| `modules/drift_check.py` | Scheduled drift comparison; needs no Claude API. |
| `scripts/` | Host CLIs (deploy, retire, rotate, the probes, the generators) and the hooks. |

(`modules/check_runner.py`, a CLI Jenkins invoked, went with Jenkins in P.4.)

`app.py` is monolithic by design for what predates the NSoT work. New routes go
in `routes/`; new UI goes in `templates/v2/` (the redesign), after a signed-off mockup.

## Startup sequence

```
app.py import                  starts NO thread (C36): importing app is side-effect free
  ├─ modules.config            paths, settings, env overrides
  ├─ Flask app created         (PyInstaller-aware template/static paths)
  ├─ SocketIO attached         async_mode="threading", manage_session=False
  ├─ routes.register_blueprints(app)
  ├─ settings_schema.migrate() seed defaults, encrypt legacy plaintext secrets
  └─ … all route definitions …

python app.py (__main__ only)
  └─ _start_background_daemons()
        ├─ the reader jobs      modules/readers/: job health, Grafana alerts, freshness,
        │                       integration health, reachability (C92, replaced ping_worker),
        │                       and the rest in reader_job.DECLARED_MODULES
        ├─ the session reaper, the Prometheus targets keeper, the drift scheduler
        ├─ event monitor
        ├─ SNMP trap receiver and NetFlow collector (the legacy collector, removed at cutover)
        └─ agent_runner         autonomous AI daemon, off until Stage 8
```

## Data ownership

| Data | Owner | Location |
|---|---|---|
| Device inventory + credentials | NMAS | `data/lists/{slug}/devices.csv`, Fernet-encrypted fields |
| Settings, integration config | NMAS | `data/user_settings.json`, secrets Fernet-encrypted |
| Encryption key | NMAS | `data/key.key` — **back this up** |
| Golden configs and committed intent | NMAS | `data/lists/{slug}/config_repo/` (`golden/`, `host_vars/`), read as committed; `golden_configs/` is a read-only legacy fallback, retirable (7.8) |
| Sites, devices, interfaces, IPs | NetBox | remote; NMAS reads freely, writes are gated |
| NMAS-created NetBox object ids | NMAS | `data/netbox_created_ids.json` |
| Metrics, logs, config history | External tools | Phase 5 |

## Per-list data layout

```
data/lists/{slug}/
├── devices.csv              inventory; password/secret Fernet-encrypted
├── variables.json           discovered network facts
├── golden_configs/          legacy, read-only (the store before Phase 2)
├── config_repo/             THE NSoT repository: golden/, host_vars/, templates/,
│                            profiles/, .nsot/ (manifest, staging, rolled_back.json)
├── backups/
├── approval_queue.json      human review for destructive AI actions
└── collector_config.json    SNMP/NetFlow ports, communities (legacy collector)
```

## Principal flows

### Config push: the confirmed deploy path, and nothing else

```
/deploy/plan                 routes/deploy.py
  → render committed intent  the network's template, the monitoring profile merged
  → the exact program        merge-only additions, re-creates, selected removals
  → gates, each by name      fidelity, approval, ASCII, dangerous lines, credentials, holder
  → preview                  drawn by the shared preview-confirm component, masked
/deploy/apply                a verified person confirms the program's hash
  → recompute and compare    refused, naming what moved
  → modules/pipeline.py      9 stages: snapshot, push, verify (scoped), rollback on failure
  → one golden commit        save_golden(), the baseline decided in the commit
  → receipts                 one masked row per device, read back on History
```

Restores, capture, seed, revert and retry, rotation, persist and retire are their own
operations with the same preview, confirm, result and record. `/configure/apply`, the old
direct push (with "Jenkins verify" after it), was removed in P.3 and answers 404
(`tests/test_p3_cuts.py`).

### AI agent

```
run_chat()                   modules/ai_assistant.py
  → read-first               golden configs + variables before any SSH
  → tool loop                until the task completes; a question it asks is for a
                             person (no auto-continue since P.3 step 8)
  → device commands          read-only allowlist only (modules/readonly_commands.py);
                             every device-changing tool was removed in P.3 step 8
  → destructive actions      queued in approval_queue.py; only a person resolves one
```

`agent_runner.py` runs the same machinery autonomously in the background and
pauses when a user opens the chat panel.

### NetBox import (gated)

```
Click "Import to NetBox (discovery)"
  → routes/netbox_safety.py  preview
      └─ sync_list_to_netbox(dry_run=True)
           └─ netbox_guard.dry_run()      thread-local
                └─ _nb_post/_nb_patch     record intent, return synthetic id
  → modal shows create/update preview
  → confirm (optionally enabling writes)
  → sync_list_to_netbox()                 background thread
       └─ _nb_post  → assert_writes_allowed()
                    → inject nmas-managed tag
                    → record created id
```

The dry run is the same code path as the real import, which is why the preview
is accurate.

### NetBox removal (provenance-gated)

```
remove_list_from_netbox(list_name)
  → read data/netbox_created_ids.json
  → for each endpoint, in referential-integrity order:
       fetch object → still tagged nmas-managed?
         yes → delete
         no  → report as skipped (operator-owned)
```

Both conditions are required. Neither alone is sufficient: a tag can be added by
hand, and the id record can go stale against a rebuilt NetBox.

## Write chokepoints

Every NetBox write in the codebase passes through one of three functions in
`modules/netbox_client.py`:

| Function | Gate behaviour |
|---|---|
| `_nb_post` | raises `NetBoxWriteBlocked`; tags and records on success |
| `_nb_patch` | raises `NetBoxWriteBlocked` |
| `_nb_delete` | logs and returns `False`; forgets the id on success |

Gating these three gates the entire surface — which is what makes
`test_netbox_write_gate.py` a meaningful proof rather than a spot check.

## Settings

```
data/user_settings.json
  ├─ settings_schema_version
  ├─ plain values
  └─ secrets, stored as  enc:v1:<fernet-token>
```

`modules/settings_schema.py` owns defaults, validation, and migration.
`modules/secrets_store.py` owns encryption. Resolution order for portability
settings is **environment → user setting → OS-appropriate default**.

## The lab's config-persistence pipeline (lab tooling)

*Corrected 2026-10-02:* this section was written when the pipeline lived only on the host.
Since then the sync script is in the repository (`scripts/oxidized-to-config.sh`), its
units are templates in `deploy/systemd/`, and **since C319 (2026-10-01) each startup file is
built from the device's golden at the newest EARNED baseline** (credentials from the current
golden) by `scripts/nmas-startup-source`, with Oxidized only a reported cross-check, never
the source. It is lab tooling under the Stage 10 boundary (NSOT_STAGE10_PLAN 6.0). The text
below is kept as the record of why it exists and what it guards against; where it names
Oxidized as the source, read the baseline.

**Was: not part of this codebase, and the NSoT depends on it being true.** Documented
here because the repo should at least say it exists, what it guarantees, and
where it connects.

### Why it exists

Containerlab nodes are ephemeral. `write memory` saves to the *container's*
NVRAM, but `containerlab deploy --cleanup` boots every node from the
**startup-config files on the containerlab VM** (`<lab-host>`,
`~/labs/lab/configs/`). Anything not in those files is lost on redeploy.

So there are two different claims, and only one of them was ever guaranteed:

| claim | guaranteed by |
|---|---|
| "this is what the device is running" | the NSoT golden repo |
| "this is what the device will boot as" | **nothing, until this pipeline** |

### The pieces

| path (on the NMAS, `<nmas-host>`) | what |
|---|---|
| `~/lab-configs/oxidized-to-config.sh` | the sanitiser/sync, 318 lines |
| `~/bin/clab-sync` | `flock -n` wrapper, runs it with `--yes` |
| `/etc/systemd/system/clab-sync.service` | `Type=oneshot`, **`User=<user>`** |
| `/etc/systemd/system/clab-sync.timer` | `OnBootSec=10min`, `OnUnitActiveSec=30min`, `Persistent=true` |

### What it does

Reads Oxidized's stored configs from its git output backend
(`/opt/oxidized/rcn-lab.git`, files named by **device IP** per `router.db`) and
sanitises them into replayable startup-configs:

- strips PKI certificate chains, the `clab-mgmt` VRF and `GigabitEthernet1` on
  routers, banners, `license`/`platform` lines, `call-home`;
- **re-injects `no shutdown`** into any interface carrying an address that does
  not explicitly say `shutdown`. A running-config records `shutdown` but never
  `no shutdown`, so harvesting a working device and replaying it brings every
  routed port up administratively down. This cost a full rebuild on 2026-08-30.

Then validates every file before anything is copied — a failure copies nothing
and fails the unit:

- exactly one `end`, exactly one `hostname` (an empty file has neither, and the
  older check could not tell that from a good one);
- no management-interface, certificate or banner leakage;
- no addressed interface missing `no shutdown`;
- a **truncation guard**: interface and `router` block counts in Oxidized's copy
  must survive into the output. Proven by fault injection — a simulated
  truncation at the first `router` block passed every older check on all nine
  devices, and the guard refused all nine.

On success: rsync to a stage dir on the clab VM, diff, timestamped backup, copy,
and commit in `~/labs/lab` (identity `clab-sync`). The file header carries
Oxidized's **commit sha**, not a timestamp — a timestamp made every run "change"
every file.

**No manual approval, by design.** Validation is the gate, and the output only
affects the *next* redeploy — it never touches a live device.

### How it connects to the NSoT

```
device ──SSH──> Oxidized ──git──> /opt/oxidized/rcn-lab.git
                                        │
                              oxidized-to-config.sh (sanitise + validate)
                                        │
                              <lab-host>:~/labs/lab/configs/*.cfg
                                        │
                              containerlab deploy --cleanup
```

Two consequences the NSoT must respect:

1. **Oxidized logs into the same devices with the same account NMAS uses.** Its
   credentials are a *single global* `username`/`password` in
   `/opt/oxidized/config`; `router.db` maps only `name: 0` (the IP). So rotating
   that account breaks Oxidized for every device at once unless Oxidized is
   updated too — see `docs/NSOT_SET_CREDENTIAL_PLAN.md` §GAP 1.
2. **If Oxidized's login fails, the startup files silently stop updating.** The
   sync reads Oxidized's repo, so a credential failure upstream looks like "no
   changes" downstream, not like an error.

### It should be version-controlled (DONE since: the script and the unit templates are in this repository)

The script, the wrapper and the units live only on the NMAS filesystem. They are
load-bearing — the truncation guard above is the kind of logic whose history
matters — and they have no history at all. Once Phase 2b lands, `infra/` in the
per-list config repo is the natural home, which also means they reach the
private remote with everything else.

## Conventions

- Return dicts shaped `{"ok": bool, "error": str, ...}`
- Module-level `log = logging.getLogger(__name__)`
- Integrations never raise into a request handler; they return `ok: False`
- No IPv4 literals in `modules/integrations/`, `modules/nsot/`, `routes/`
- `pathlib`/`os.path` only — no hardcoded separators or drive letters

---

## The CLAUDE.md architecture narrative (moved from CLAUDE.md on 2026-10-02)

The project overview, the module map and the key architecture decisions below are
CLAUDE.md's text, moved verbatim when CLAUDE.md was cut to the standing rules. Line
counts and dates in it are as they were written. Two sentences found stale were not
moved (the consolidation's stale.md lists them). A citation of CLAUDE.md written
before 2026-10-02 (in the writeup, the register, a code comment) refers to this text.

### Project Overview

Flask-based web application for managing, automating, and monitoring Cisco IOS
network devices. Built by [Author] as a capstone/school project. The app is
a single-host management tool — not a multi-tenant SaaS — so there is no built-in
auth system.

**Stack:** Python 3.10+, Flask, Flask-SocketIO, Netmiko/Paramiko (SSH), Anthropic
Claude API (AI agent), vis.js (topology), Bootstrap 5, NetBox (source of
truth). Jenkins was removed in P.4 (docs/NSOT_CI.md).

The project is mid-way through a planned conversion into a Network Source of
Truth (NSoT) framework. **[docs/NSOT_PLAN.md](docs/NSOT_PLAN.md) is the governing
spec for that work** — read it before starting any NSoT phase.

### Module map

Line counts are accurate as of Phase 0 (2026-09-20). Everything listed is
tracked in git.

#### Core
- **[app.py](app.py)** (5,301) — Flask routes and SocketIO handlers. Monolithic
  by design for pre-existing features; **new routes go in `routes/` instead**.
- **[modules/ai_assistant.py](modules/ai_assistant.py)** (7,195) — AI agent core:
  tool definitions, `run_chat()`, golden config management, read-first workflow
- **[modules/agent_runner.py](modules/agent_runner.py)** (1,363) — background
  autonomous agent daemon; pauses when the user opens chat
- **[modules/netbox_client.py](modules/netbox_client.py)** (3,231) — NetBox
  IPAM/DCIM client. Reads freely; **writes are gated** (see below)
- **[modules/topology.py](modules/topology.py)** (1,207) — CDP/OSPF/BGP/DMVPN
  discovery; vis.js graph with hub/spoke labels
- **[modules/pipeline.py](modules/pipeline.py)** (1,159) — 9-stage
  `PipelineRunner` (NetBox query → render → CI gate → snapshot → diff → deploy →
  snapshot → verify/rollback → audit). **Wired in**: `routes/deploy.py`
  `_deploy_one` runs it for every NSoT deploy AND every restore. (This line
  said "built but not wired into the UI" until 2026-09-26, long after Phase 3
  wired it: a document asserting a property the code no longer had.) Its
  `ci_gate` stage is a LOCAL dangerous-command check and its docstring says
  so (P.4 step 2). The Jenkins status read and the "syntax check" it used to
  claim were removed with Jenkins.
- **[modules/configure.py](modules/configure.py)** (1,093) — IOS config generator
  for 10 feature types (its Jenkins script and XML generators went in P.4)

#### Collectors and checks
- **[modules/snmp_collector.py](modules/snmp_collector.py)** (763) — SNMP v1/v2c
  trap receiver + OID polling
- **[modules/netflow_collector.py](modules/netflow_collector.py)** (381)
- **[modules/drift_check.py](modules/drift_check.py)** (415) — drift checker
  needing no Claude API; diffs against golden config
- **[modules/collector_config.py](modules/collector_config.py)** (238) — per-list
  collector settings, including trap/NetFlow ports

#### NSoT / Phase 0–3c additions
- **[modules/settings_schema.py](modules/settings_schema.py)** (314) — settings
  defaults, JSON Schema validation, and forward migration
- **[modules/netbox_guard.py](modules/netbox_guard.py)** (276) — NetBox write
  gate, dry-run preview, and created-object provenance
- **[modules/secrets_store.py](modules/secrets_store.py)** (150) — Fernet
  encryption-at-rest for settings secrets
- **[modules/netbox_authz.py](modules/netbox_authz.py)** — one-shot write
  authorization: plan hashing and single-use tokens
- **[modules/inventory/](modules/inventory/)** — per-list inventory source, the
  NetBox→device-dict adapter, and the cache that makes dispatch I/O-free
- **[modules/credentials.py](modules/credentials.py)** — encrypted credential
  profiles and the resolver
- **[modules/nsot/context.py](modules/nsot/context.py)** — `build_render_context()`,
  the single way templates get data
- **[modules/nsot/repo.py](modules/nsot/repo.py)** — `save_golden()`, the one
  golden write path; trailers, tags, renames, CI notes, locking. And
  `commit()`, THE commit in a list's repository, which publishes (hands the
  commit to the push hook): nothing else names `commit` to git (C223, abandon's
  commit never reached the hook); `publish()` is called directly only by a
  caller that tags between committing and pushing. **ONE lock per repository, held
  across processes** (`RepoLock`, CONCURRENCY_AUDIT R1, 2026-10-02: it was a
  `threading.Lock`, so a host CLI's commit was serialised with the app's by nothing):
  `stage_exactly()` and `commit()` refuse outside it, a commit names the paths it staged,
  the holder is recorded beside the repository (`<repo>.lock.holder`) and a long wait is
  logged naming it; a save compares what is COMMITTED (R25); a failed tag is reported
  (`tag_failures`, R24)
- **[modules/nsot/manifest.py](modules/nsot/manifest.py)** — identity map
  (`nb:<id>` / `uid:<uuid>`), pending renames, `sync_platforms()`
- **[modules/nsot/normalize.py](modules/nsot/normalize.py)** — every
  config-line filter, one per job
- **[modules/nsot/migrate.py](modules/nsot/migrate.py)** — dry-run-first
  migration with duplicate merging; one-shot, guarded by `.nsot/migrated.json`
- **[modules/nsot/restore.py](modules/nsot/restore.py)** — re-apply a ref
  through the confirmed deploy path; device and intent as one unit
- **[modules/nsot/hooks.py](modules/nsot/hooks.py)**,
  **[archive.py](modules/nsot/archive.py)** — background post-commit push/archive
- **[modules/nsot/parsers/](modules/nsot/parsers/)** — config → host_vars, one
  module per platform (`cisco_ios.py`, `cisco_iosxe.py`)
- **[modules/nsot/roundtrip.py](modules/nsot/roundtrip.py)** — render vs. real,
  ordering policy, coverage report
- **[modules/nsot/hostvars.py](modules/nsot/hostvars.py)** — YAML staging,
  secret handoff
- **[modules/nsot/ifnames.py](modules/nsot/ifnames.py)** — canonical interface names
- **[modules/nsot/bootstrap_config.py](modules/nsot/bootstrap_config.py)** —
  the minimal config a new device boots with; one producer for the measurement
  probe and the Phase 4 wizard, ASCII-guarded over its whole output
- **[modules/nsot/render_artifact.py](modules/nsot/render_artifact.py)** — the
  deployability gate; frozen, computed, no override
- **[modules/nsot/templates_repo.py](modules/nsot/templates_repo.py)** — the
  per-network template library and bindings
- **[modules/nsot/approval.py](modules/nsot/approval.py)** — template approval
  keyed on the template's closure hash (scheme 3, P.5)
- **[modules/nsot/deploy.py](modules/nsot/deploy.py)** — the deploy contract,
  merge-only diff, transport, circuit breaker, batch orchestration
- **[modules/nsot/convergence.py](modules/nsot/convergence.py)** — per-protocol
  settle windows
- **[modules/nsot/freshness.py](modules/nsot/freshness.py)** — is Oxidized's
  copy of a device the approved one; the gate, the signal, and the
  authorisation path
- **[modules/nsot/ztp.py](modules/nsot/ztp.py)** — P.6: the Kea reservation
  writer (a candidate tested with `kea-dhcp4 -t` before the live fragment is
  touched, then reload and read-back naming both operands) and D4's posture
  (no route or resolver option at any level; nothing on the segment answers
  broadcast DNS), at plan time and as a job-health row
- **[modules/nsot/ztp_responder.py](modules/nsot/ztp_responder.py)** — P.6:
  the read-only TFTP responder; serves a pending `ztp` device its config,
  rendered per request, only to its reserved address and only the file
  option 67 names, and only once the reveal row is written. Run by
  `scripts/nmas-ztp-responder` under `deploy/systemd/nmas-ztp-responder.socket`
- **[modules/integrations/](modules/integrations/)** — one client per external
  tool (NetBox, Prometheus, Grafana, Loki, Oxidized, Kea, topology service, NSoT
  git, S3). Phase 0 ships `test_connection()` only; Phase 5 adds read clients.
- **[modules/nsot/capture_job.py](modules/nsot/capture_job.py)** — C188 step 2:
  the capture preview as a background JOB. The POST answers at once; the reads
  run on their own thread, shown by the in-flight panel (`op_progress`), and the
  job announces `capture_preview` (C58, `invalidation.ANNOUNCERS`) when it
  finishes; the page reads the result by id. In memory: a restart loses a job,
  and its GET says so
- **[modules/nsot/device_ops.py](modules/nsot/device_ops.py)** — C98: one
  operation per device at a time, across processes (a `flock` the kernel
  releases when its holder dies), refused by name with the holder's age,
  last progress step and a "may be stuck" note, never queued and never
  forced. C101 enforces it where the write happens: `connection.open_ssh`
  refuses a non-read command or a config or save call on a session whose
  thread does not hold the device
- **[modules/outbound.py](modules/outbound.py)** — config text on its way out:
  masked unless a person reveals it with `?reveal=1`, recorded. The golden
  routes and the backup download call it (C56): one pattern, not two
- **[modules/config_read.py](modules/config_read.py)** — C271: a device's configuration
  READ so it can be trusted, and JUDGED before anything records or compares it. One
  `show running-config`, waited for with `nsot_config_read_timeout`, never retried on its
  session (the retry stitched r2's capture: config, prompt and echoed command, config again);
  `problems()` refuses a second `end`, a prompt line, an echoed command, a `hostname` naming
  another device, and a capture over 1.6x its committed golden, saying "the device's output
  could not be read reliably". Used by the capture, `run_device_command` for any configuration
  read, drift, and `save_golden` (on evidence only). **C272: the rule is every command's.**
  `run_device_command` sends each command ONCE with that bound and never re-sends; a NUL
  prompt is read again before anything is sent; a show reply holding an echoed command or the
  session's own prompt is refused (`output_problems()`); and a read that raises SPENDS its
  session (`SPENT_ATTR`), which nothing reads again and the connection pool replaces. Verify
  says what it could not read (`unreadable`): before the push it refuses with nothing sent,
  after it verify neither passes nor fails on it and rolls nothing back for it
- **[modules/readonly_commands.py](modules/readonly_commands.py)** — C61:
  the ONE read-only command allowlist, whole command: verb, every output
  modifier after a `|`, no URL, no target-less ping, no line editing. The
  agent's tools use it; the lens, `/run_command` and `bulk_execute` adopt it
  in 7.3
- **[modules/nsot/authorisation.py](modules/nsot/authorisation.py)** — C140,
  C79: the ONE mechanism for a line that needs an authorisation (a dangerous
  line, or a secret a restore would add): its key, the reason's shape rule,
  the problems, the fingerprint. 8.8's written override reuses it
- **[modules/nsot/receipts.py](modules/nsot/receipts.py)** — C60 (7.1): the
  deploy receipt, one masked row per device per batch, written by the deploy
  and restore apply paths after the golden commit: the program sent and its
  hash against the confirmed one, the actor, the checks that RAN (or why
  none did), rollback, and the commit. The follow-up window is not built,
  and each row says so
- **[modules/attention.py](modules/attention.py)** — Stage 7.2: Needs
  attention. One row constructor (what, devices, since, cause, operands,
  the one action, a level, an empty triage slot for Stage 8) that refuses a
  row with no cause or action; one source contract (read time, read cost,
  what was looked at; an unreadable source is a row). `GET /attention`,
  drawn by **[static/js/nmas_attention.js](static/js/nmas_attention.js)**.
  **Every row names something wrong AND an action a person can take** (the
  operator, 2026-10-02, C323): `ROW_KINDS` declares every kind a source can
  emit with both, and `row()` refuses an undeclared kind, an information level
  (there is none) and an action that says there is nothing to do. A fact
  nobody acts on (a retired device's leftover lab file, a release available,
  a check missing a device for one run) is said in its source's finding under
  What was checked, or on its own page, never as a row
- **[modules/filestore.py](modules/filestore.py)** — C158: the ONE fix for a
  store the program read-modify-writes: `PathLock` (an RLock plus a
  cross-process `flock`, re-entrant per thread and PATH), `write_atomic` (a
  temp per write, `os.replace`), `read_json_for_write` (unreadable refuses,
  kept as `.corrupt-<ts>`). The credential store, both NetBox provenance
  records, `rolled_back.json` and devices.csv use it
- **[modules/nsot/record_exceptions.py](modules/nsot/record_exceptions.py)** —
  commits whose record is known to be wrong, by full hash (the eleven
  rotation commits recorded `Source: manual`, C104). History is not
  rewritten; a reader draws the exception beside the record. Also
  WITHDRAWN baselines, by commit (C177): a restore point a person decided
  is never re-applied, refused by `restore.build_targets` and drawn with
  its reason, and drawn as deleted once its tag is gone
- **[modules/nsot/seed.py](modules/nsot/seed.py)** — C148 (7.3 step 1):
  SEED INTENT, a device's first full intent parsed from its COMMITTED golden,
  previewed against the intent committed now, confirmed by a hash of the
  document and the golden, parsed again at apply, one commit of exactly the
  seeded files (`Source: seed`). Only absent or bootstrap-only intent is
  seeded; what the template does not model is named, never blocked here.
  Client: **[static/js/nmas_seed.js](static/js/nmas_seed.js)**, the Device
  page's Seed intent
- **[modules/nsot/rotate_op.py](modules/nsot/rotate_op.py)** — 7.3: ROTATE from the
  Device page, `credential_rotation` as one operation: a preview (the plan's preflight,
  which READS the account's line live, and the program with the password masked), a
  confirm by the plan's fingerprint as a person, and an apply run as a JOB (rotate plus
  persist can pass the 100 s edge limit), holding the device across both, carrying the
  person's verified identity into the thread (`identity.carried()`, so the commit reads
  `Actor-Verified: access`), announcing `rotation`, every state drawn with its one
  action. `nmas-rotation-recover` (C210) settles a credential a dead job staged. Route
  `routes/rotate.py`, client **[static/js/nmas_rotate.js](static/js/nmas_rotate.js)**;
  the job registry is `capture_job`, which takes a kind and its announce keys
- **[modules/breakglass_export.py](modules/breakglass_export.py)** — 7.3: the
  break-glass export from the BROWSER. Built, sealed and VERIFIED in memory (the sealed
  bytes opened with the passphrase and every device, credential digest and the escrowed
  key checked before anything is sent); the passphrase twice and 12+ characters, refused
  before anything is built; a reveal row before anything leaves; the export log records
  "downloaded by X at T" with the sha256. The file never touches the host's disk. Kept
  apart from `modules/breakglass.py`, the record format, which stays independent of the
  app's stores. Route `routes/breakglass.py` (gate `reveal`); ONE client,
  **[static/js/nmas_breakglass.js](static/js/nmas_breakglass.js)**, opened by any element
  with `data-nmas-open="breakglass_export"`: the rotate result's next step, Needs
  attention's break-glass row, the Settings page
- **[modules/nsot/intent_ops.py](modules/nsot/intent_ops.py)** — 7.3: REVERT and RETRY,
  the two ways out of a rollback, which mean opposite things (revert: the change was
  wrong, undo ONE intent commit's change keeping every later one, `Source: revert`;
  retry: it was right, lift the block with a reason in the shape of one, recorded in the
  retry log). Previewed, confirmed by hash with the list carried, applied holding the
  device. A revert computes with `hostvars.plan_revert()` (one computation for preview and
  apply) and MEASURES the block after its commit, clearing it only when it no longer
  blocks (C214: the old route cleared it after any revert). One classifier for the list
  and both screens, `routes/templatize.note_applicability()`. Client
  **[static/js/nmas_intent_ops.js](static/js/nmas_intent_ops.js)**
- **[modules/nsot/adopt.py](modules/nsot/adopt.py)** — 7.3, ADOPT (being built): bring a
  device the tool did not build into management. Step 1, `add_tool_account()`: ADD the tool's
  own account (`nmas`, never the supplied name) through the SUPPLIED credential, with rotation's
  staging, held session, fresh-login verify and record; an existing account by that name is
  refused as somebody's; a failed verify removes only what was added; the supplied account is
  never changed. `nmas-rotation-recover` does not cover it (no inventory row yet).
  **The SUPPLIED credential is never written** (the operator, 2026-09-29): it is somebody else's
  login, useless to the tool once its own account is proven, and its owner still holds it if
  adoption fails. In memory for the call only (`redact.transient_secret()` for log lines, a scrub
  of the result); staging is for the credential the TOOL generates. **A device whose SSH logins
  would never consult a local account is refused before anything is sent, naming why**
  (`local_login_verdict()`: vty `login local` without AAA; with AAA, `local` FIRST in the login
  and exec lists the vty uses, because `local` after a server group is tried only when the
  servers do not answer). Step 2, `plan()` and `apply()`: a preview that READS the device
  with the supplied credential (persist as running against startup, NetBox's existing objects
  and the import's own dry run over the capture) and an apply that holds the device, refuses a
  moved fingerprint, then adds the account, sends the network's monitoring profile (P.9 (c):
  computed from the preview's capture, in its program and fingerprint, read back), persists,
  commits the first golden
  (`Source: adopt`), imports into NetBox recording what EXISTED as adopted
  (`data/netbox_adopted.json`, never the created record), and promotes last. A stopped run
  RESUMES on the tool's own record. **Every local credential the golden would carry in a
  reversible form (`username … password 0|7`, `enable password`) is refused by name**; the
  SUPPLIED account's alone may be converted, by the person's named opt-in ("Store this
  account as a secret — same password; the device hashes it"): rotation's program on the held
  session after the tool's account is proven, a fresh login as the owner with the same
  password, and the original line put back and proven if that fails (the operator,
  2026-09-29). SNMP communities are the accepted exception. Recovery of a staged tool
  password: `nmas-adopt-recover` (a sidecar holds the address)
- **[modules/nsot/persist_op.py](modules/nsot/persist_op.py)** — C164 (7.3): PERSIST
  from the Device page, the operation `nmas-persist-native` runs on the host: a preview
  that contacts no device, a confirm bound to the plan's hash, the device held while
  `onboard.persist_on_device` saves and reads back (the ONE save, C53), and the outcome
  recorded where job health's rotation row reads it. Route `routes/persist.py`, client
  **[static/js/nmas_persist.js](static/js/nmas_persist.js)**
- **[modules/readers/netbox_secrets.py](modules/readers/netbox_secrets.py)** — does
  NetBox hold a credential in any device's stored config context: hourly, over what
  NetBox HOLDS (never a list), judged by the secret-storage checker's own scan, slots
  and counts only. Needs attention draws one danger row per device, with the mask
  command where NMAS wrote the context and "remove it in NetBox" where it did not
- **[modules/fanout.py](modules/fanout.py)** — the concurrency rule's one helper:
  `read_each(fn, items)` reads across devices AT ONCE, bounded, results in the items'
  order, a failure that item's alone. For READS only; the deploy batch stays
  sequential for its circuit breaker
- **[modules/netbox_context_mask.py](modules/netbox_context_mask.py)** — C139: masking
  the credentials NetBox holds in a device's stored config context, ONE implementation
  for `scripts/nmas-netbox-mask-context` and retire. Population: what NetBox holds (the
  checker's scan); authority: the modification record; read back after the write
- **[modules/nsot/retire.py](modules/nsot/retire.py)** — C11 (7.3): the
  whole exit, one implementation for two entry points. `nmas-retire` OPENS
  the break-glass record; the Device page's Retire… (`routes/retire.py`,
  **[static/js/nmas_retire.js](static/js/nmas_retire.js)**) trusts the
  EXPORT LOG (`breakglass_logged`) and says so, because it cannot reach a
  file on a laptop
- **[modules/nsot/removal.py](modules/nsot/removal.py)** — Mode B (7.3
  step 2): removing a line the device has and intent lacks, SELECTED units (residue leaves, whole stanzas) to the exact
  program, verbatim, each refusal with its reason (IOS will not remove it, a
  numbered ACL entry, the management path, an account, a named object still
  used). Never "converge to intent": a person chooses each unit. And only a
  line matching a SHAPE measured on its platform by
  `scripts/nmas-removal-probe` to remove exactly itself
  (`removal_measured.json`): `no <line>` can remove more than the line.
  Through the deploy path since 2b: one `with_removals()` for plan, apply
  and the run; a reason per removal; verify reads each gone; the undo
  re-adds the device's own lines (`restore_program`), never a negation.
  The screen (2c) selects BY ID (`unit_id`), because the plan is masked and
  a secret-position line's text could never be sent back
- **[modules/deploy_job.py](modules/deploy_job.py)** — P.9 (d2), 2026-10-01: a batch deploy
  run as a JOB, in the ROLLOUT ORDER the v2 preview set (`/v2/monitoring/apply`, Monitoring >
  Coverage's batch Apply), through `routes.deploy.apply_batch`, the one apply `/deploy/apply` also
  calls (and `plan_devices`, the one plan): the confirm answers at once, the person's identity
  carried into the thread, each device's start and finish recorded and announced (`deploy_job`), so
  the page draws done, running and pending devices in order, then the result from the receipts.
  Client **[static/js/nmas_apply.js](static/js/nmas_apply.js)**
- **[modules/nsot/recreate.py](modules/nsot/recreate.py)** — C290 (2026-10-01): a RUNNING
  IP SLA operation intent changes is deleted, re-created from intent and rescheduled, because
  IOS refuses to modify one in place. `routes/deploy._program()` is THE program computation
  (deploy plan and apply, the pipeline's run, the restore's preview and apply, a test holds
  `merge_commands` to that one call): additions, then re-creates, then removals. Previewed
  with the definition it replaces, verified by reading it back, rolled back by restoring the
  old definition from the snapshot. The delete is the removal shape
  `global.ip-sla-operation`, refused until `nmas-removal-probe` measures it per platform
  (staged run 9); an operation a `track` or reaction names is refused naming the line
- **[modules/nsot/golden_state.py](modules/nsot/golden_state.py)** — E7:
  a baseline that is CONFIGURED AND WORKING. Every routing protocol a
  device's committed intent declares is judged up from real output (OSPF and
  OSPFv3 FULL or 2WAY, BGP established, RIP sources, RIPng next hops),
  failing closed with reasons; the baseline tag carries the claim and the
  snapshot, and `golden-state/<ts>` marks only a working fleet.
  `scripts/nmas-golden-state` takes one (dry-run by default)
- **[modules/reader_job.py](modules/reader_job.py)** — Stage 7.2: the
  READER JOB, one background read of an outside service, stored with the
  time of its value, a failed read keeping the last good value, its
  liveness a job-health row, and an announcement when it finishes (C58).
  Job health is the first reader (it was 9.8 s of a 10 s landing page,
  measured); Grafana is the second; the rest reuse it, so its thirteen rules
  are written in its docstring, each naming its finding (the thirteenth, C244:
  every run records what CAUSED it, scheduled or whose request, with its
  duration, and a run a person asked for is always announced). Readers live in
  **[modules/readers/](modules/readers/)**, listed in
  `reader_job.DECLARED_MODULES`. `readers/grafana_alerts.py` reads the
  ruler, the rules view and the Alertmanager every 60 s: three kinds
  (condition, no data, error), which device and from where (label, the
  line's origin-id by `ORIGIN_ID_PATTERN`, or an address), incidents grouped
  on the onset, a stalled evaluator, and completeness from Grafana's own
  counts. Since 2026-09-30 it also reads the silence list: a silenced alert
  stays a row at its level, saying who silenced it in Grafana and until when.
  `readers/freshness_reader.py` stores the Oxidized freshness
  signal per list every 300 s (it ran per device on every page load);
  the sanitiser's gate stays live on purpose. `readers/integration_health.py`
  probes every integration in parallel every 60 s for the status bar (on
  every page, `static/js/nmas_status_bar.js`) and Needs attention alike;
  the Settings Test button stays a live check (rule 11).
  `readers/baseline_usability.py` judges whether any stored baseline can be
  re-applied without changing a held credential (C75), recomputing only when
  HEAD or the tag set moves (the full judgement is 8 to 9 s on the host), for
  Needs attention's "no stored baseline can be re-applied" row.
  `readers/ci_verdict.py` stores the running commit's CI verdict by LOADING
  `scripts/nmas-deploy` and calling its own `ci_verdict()` (one
  implementation); `GET /health/version` composes it with `_COMMIT` and
  job health's running-version row and computes none of them.
  `readers/remote_publication.py` (C223) compares each list repository's HEAD
  with the REMOTE's own branch (`git ls-remote` through the repository's own
  `origin`, never the push hook's record) every 120 s and after every commit,
  and the tool's tags the remote lacks. A push the hook HELD at the publication gate
  (C278) is recorded (`remote.record_push_held`) and drawn red at once with its reason and
  "acknowledge, then push". The gate holds only for a NEW secret value or kind (C280:
  each live secret by a salted fingerprint, listed with its devices on the Remote card;
  another copy of an acknowledged value is never held). An unpushed commit with no hold is red past 10 min; a tag
  a hook call named and could not send is kept (`pending_tags`) and sent by the next push,
  never computed from what the remote lacks (a withdrawn baseline would ride along);
  its one sentence, `describe()`, is drawn by the Git tab ("Everything is
  committed · N commit(s) not pushed…"), the Remote card and Needs attention.
  `readers/reachability.py` (C92) probes every list's devices every 5 s and
  judges "answering" over consecutive misses against ONE
  `miss_threshold()` (3, measured); it OWNS `STATUS`, which the app hands
  every consumer as `device_status_cache`, and announces on a change with a
  60 s keepalive. `readers/grafana_dashboards.py` stores every dashboard's
  model, trimmed, keyed by UID, every 300 s, announcing `dashboards` only on a
  change (30 min keepalive). `readers/lab_startup.py` (C303, 2026-10-01) runs
  **[modules/lab_startup.py](modules/lab_startup.py)** every 600 s: each device's
  lab startup file (the file a redeploy boots) against its committed golden
  rendered through the clab sync's OWN sanitiser (`kind_for`, `sanitise` and
  `render_device` lifted from `scripts/oxidized-to-config.sh`), line for line,
  the header aside; equal on all nine on the host when built. One SSH read per
  lab directory; a credential named by its slot, never its value; a missing file,
  an unknown lab and a `.cfg` no device owns (r5's) each said. Needs attention's
  `lab_startup_source`
- **The redesign's SPIKE (NSOT_GUI_BRIEF 9b, 2026-09-30)**: the device page's
  Overview and Monitoring tab in option A at `/v2/device/<name>`
  (**[routes/device_v2.py](routes/device_v2.py)**, `templates/v2/`,
  **[static/css/nmas-v2.css](static/css/nmas-v2.css)**,
  **[static/js/nmas_v2.js](static/js/nmas_v2.js)**,
  **[static/js/nmas_panels.js](static/js/nmas_panels.js)**), under
  `csp.STRICT_POLICY` (no inline script or style). What it reads is
  **[modules/device_page.py](modules/device_page.py)** (every fact from a record
  the app already keeps); **[modules/panels.py](modules/panels.py)** is the pure
  panel logic (which panels select the device, the bounded range and step, the
  `api/ds/query` request, the answer as series, and `layout()`: each panel at its own
  `gridPos`). `scripts/nmas-vendor` vendors an npm package's files after checking the
  tarball's sha512 against the registry. **Option A was APPROVED on the spike (2026-09-30).**
  **A control that starts work shows it is busy ON ITSELF and the result updates in place**
  (the operator, 2026-09-30; NSOT_GUI_BRIEF section 6): no narration beside a control, no
  provenance in a row unless it changes what the person should do (the cause and duration
  on hover and in the record), words only for a refusal, a failure or a late answer.
  Every v2 page and fragment draws the viewer through `identity.viewer()`, the same
  `identify()` as `/identity/status`; never `request_actor()`, which answers only inside a
  gated request (C233). **Step 4 began the same day** in **[routes/v2.py](routes/v2.py)**: the
  landing page (`/v2/`, Needs attention drawn from `attention.needs_attention()`, masked as
  `/attention` masks it, with its evidence one level down and the recent deploys and restores)
  and Help > About (`/v2/help/about`: the running commit, its CI verdict, whether it is what
  is pushed, the checkout, who is looking; the version from `routes.health.version_facts()`,
  the one composition `/health/version` serves). The top bar carries no commit. **Devices**
  (`/v2/devices`, 2026-10-01, `modules/device_list.py`): every device with its status, address,
  platform, intent state AS OF ITS LAST MEASUREMENT and when that was (the golden's last
  change on hover), pending onboardings as rows, searched and filtered, from a FIXED number of
  reads (one bounded `git log` over `golden/`, one over the commits carrying `Intent-Match:`,
  one `ls-tree`; never per device). **A measurement is any save that read the device**
  (2026-10-02, the operator): a Save All that found it unchanged counts, so every save names
  each device it read in `Devices-Measured:`, and `device_list.last_measured()` is the one
  reader (the Overview's Last measured uses it too); the selection
  plans a deploy on today's page until v2 carries one. **The device page's actions on v2**
  (7.3; the mockup signed off 2026-10-02), **[modules/device_actions.py](modules/device_actions.py)**
  and `templates/v2/_capture.html`: an operation's card drawn in place of the tab, from the
  operation's OWN job and apply (`routes.golden.start_capture_preview`, `apply_captures`,
  which `/golden/capture/*` call too); the card starts its read and then listens for its
  job's announcement, the confirm carries the read's hash and the list, and the result is
  drawn in place. Capture first; persist, rotate and deploy with Mode B follow. The device page's tabs since: **Intent**
  (read-only: the document committed at HEAD, its last commit, the profile sections it
  inherits), **History** (goldens, intent commits and receipts as one timeline) and
  **Neighbours** (**[modules/neighbours.py](modules/neighbours.py)**, C38: the adjacencies the
  fleet's committed intent implies, read in two git calls, against what Prometheus last scraped
  from the device's routing tables; it opens no device session) and **Logs**
  (**[modules/device_logs.py](modules/device_logs.py)**: the device's syslog from Loki over 24 h,
  matched by its origin-id as the heartbeat rules match it, heartbeats folded into a count by
  their EXACT line form so an error naming the applet is still listed (C21), each line placed
  by when the NMAS received it and a device time IOS marks unsynchronised said) and **NetBox**
  (**[modules/device_netbox.py](modules/device_netbox.py)**, read-only: the record by exact name,
  and WHO OWNS IT by NMAS's provenance: created (tag AND record), adopted, a person's, or the two
  disagreeing; NMAS's recorded writes to it; and NetBox's platform beside the inventory's, A4
  drawn where people look, through `platform.dialect_for_netbox_slug()`, which says `ios` maps to
  nothing rather than defaulting it). Only Ask the device is unbuilt.
  `readers/adjacencies.py` (C38's second consumer) runs the Neighbours comparison over every
  list each minute for Needs attention: one row per LINK naming its pair, raised after two
  consecutive reads (a deploy's settle window passes first).
  `readers/app_pushed.py` asks `git ls-remote origin refs/heads/main` for the application
  repository and judges the running commit at the tip, behind (it FETCHES a tip it lacks,
  and says unknown only when the fetch fails) or not on the remote, for About and Needs
  attention's `pushed` row, whose action is the Update button. Behind the tip it also stores
  what the Update preview shows: the commits between, `Host-Step:` trailers, the updater's own
  files a release changes, the checkout's state, the tip's CI verdict (once per tip) and
  since when the tip has been ahead. **Dark mode** (the operator, 2026-09-30): a System/Light/Dark menu in the
  top bar, kept per browser (`static/js/nmas_theme.js`, loaded in the head so the choice is on
  `<html>` before the first paint); every colour on a v2 page is a token with a dark value
  (`prefers-color-scheme` unless Light is chosen, or `data-theme="dark"`), and the charts read
  the tokens and redraw on `nmas:theme`. Today's pages are not themed: the redesign replaces them
- **[modules/update_op.py](modules/update_op.py)** — THE UPDATE BUTTON (2026-09-30,
  [docs/UPDATE.md](docs/UPDATE.md)): the app updates itself from the GUI and holds NO
  privilege. The preview is the `app-pushed` reader's stored value (the commits between, the
  target's CI verdict by `nmas-deploy`'s gate, `Host-Step:` trailers, the checkout's state,
  since when the tip has been ahead); the confirm is bound to its hash; the apply writes a
  REQUEST file into `data/update/requests/` and nothing else. The ROOT-OWNED
  **[deploy/update/nmas-update](deploy/update/nmas-update)** (installed in /usr/local/sbin,
  started by `nmas-update.path`, its gate a root-owned copy of `scripts/nmas-deploy`)
  re-checks CI itself, runs git only as the service user (`runuser`), names every program it
  runs by ABSOLUTE path and self-tests them before each run (C246), restarts, confirms by
  identity and rolls back a version not up in 120 s, recording to /var/lib/nmas-update. The
  page (`/v2/update`, **[routes/update.py](routes/update.py)**,
  **[static/js/nmas_update.js](static/js/nmas_update.js)**) waits on /health, never a
  timer; job health's `updater` row checks the install is root-owned and not writable by
  the service user (`scripts/nmas-update-check`)
- **[modules/prometheus_targets.py](modules/prometheus_targets.py)** — C232, C229: the SNMP
  scrape targets generated from the inventory as `file_sd` files, each target labelled
  `device` and `role` (per platform dialect, every device, and the devices whose committed
  golden defines an IP SLA operation). The APP keeps them current: a keeper thread writes
  `prometheus_targets_dir` (empty by default: nothing written) whenever a `devices.csv` is
  written or a NetBox inventory refreshed, with a 300 s backstop, recording each run. Job
  health's `prometheus-targets` row checks the files on disk against the inventory and the
  running Prometheus against the files, reading what Prometheus has LOADED beside what it
  has discovered (C234): not loaded, not yet discovered (`settling`, dated, no attention
  row) and differs are three states. No action names a console command. Also the ROUTING
  files (`ospf`, `ospfv3` IOS-XE only, `bgp`) from the goldens, read by the snmp_exporter
  modules in `deploy/snmp_exporter/` (generated with prom/snmp-generator 0.29 after staged run
  5 measured which tables each platform answers; `scripts/nmas-snmp-add-modules` is the
  operator's proven append). The device dashboard, `deploy/grafana/nmas-device.json` (UID
  `nmas-device`), is built by `deploy/grafana/build_nmas_device.py`: every panel selects
  `$device`, telemetry primary where it measures the same thing, CPU drawn from both sources
  named (they differ about 5x), uptime only where the clock keeps real time, and reboots and
  the clock rate everywhere. The operator's one-time install:
  [docs/PROMETHEUS_TARGETS.md](docs/PROMETHEUS_TARGETS.md)
- **[modules/nsot/profile.py](modules/nsot/profile.py)** — P.9 step (a): the network's
  MONITORING PROFILE, one committed `profiles/monitoring.yml` per list, data in the parsers'
  `host_vars` shape. `effective()` is THE merge (sections by platform and role, the device's
  own value winning, an EMPTY value never an override, an exclusion with its reason);
  `effective_for()` reads the committed profile (or the ref's) and the inventory role. Every
  render of intent calls it (a scan holds it): the deploy plan and apply, `intent_match`, the
  editor, bulk intent, restore validation. The plan attributes `from_profile` lines apart. One
  commit (`profile:`, `Source: profile`); the profile's secret under
  `credentials.profile_secret_key()`, which hydration reads after the device's own. Design:
  [docs/MONITORING_PROFILE.md](docs/MONITORING_PROFILE.md)
- **[modules/nsot/profile_propose.py](modules/nsot/profile_propose.py)** and
  **[profile_apply.py](modules/nsot/profile_apply.py)** — P.9 step (b): PROPOSE the network's
  profile DERIVED FROM THE CONNECTORS (`connector_value()`: the syslog settings, snmp_exporter's
  auth module, Telegraf's listener, the NTP servers, the LLDP scrape; set on Settings >
  Integrations > Monitoring profile), the fleet's committed intent the CROSS-CHECK naming a
  device configured differently (a connector left empty falls back to what the fleet agrees on,
  saying so; two versions never reconciled by the tool), confirmed by hash and
  committed as the person; APPLY it as the deploy scoped to the profile's lines (`scope: profile`
  on `/deploy/plan` and `/deploy/apply`), recomputed at apply and where it connects. Client
  **[static/js/nmas_profile.js](static/js/nmas_profile.js)**; the apply is the deploy wizard
- **[modules/nsot/startup_source.py](modules/nsot/startup_source.py)** — C319, plan item 4
  (2026-10-01): what each lab startup file is built FROM: the device's golden at the list's newest
  EARNED baseline (not withdrawn, not deleted, `Baseline: earned`), every credential family
  (accounts, enable, SNMP communities) from its CURRENT golden (C309). `scripts/nmas-startup-source`
  writes them for the clab sync, which sanitises and copies them; Oxidized is the sync's cross-check,
  reported, never a block. A device the baseline lacks is not built, named, the rest written
- **[modules/nsot/verify_scope.py](modules/nsot/verify_scope.py)** — C316 (2026-10-01): which
  verify a program gets. Every top-level section management (terminal lines, logging, SNMP, NTP,
  banners, users) is QUICK: no wait for BGP's hold time, each new line read back; anything else or
  unnamed is FULL. One classifier for the deploy and restore previews (`program.verify`) and the
  pipeline's verify stage
- **[modules/oxidized_fetch.py](modules/oxidized_fetch.py)** — C314 (2026-10-01): a commit that
  changed a golden asks Oxidized to fetch those devices NOW (`GET /node/next/<node>`, the node
  named by `oxidized_node_identity`), as a post-commit hook, so every deploy, restore, Mode B,
  profile or IP SLA apply, adopt, onboarding and rotation reaches it; each request recorded per
  list (`oxidized_fetch_requests.json`, newest per device). It asks and never waits; what reads
  Oxidized's copy (the freshness signal, the clab sync's cross-check) sees the change sooner. (Its
  lab-startup "Oxidized hasn't fetched" row went with C319, which builds the files from the baseline)
- **[modules/fleet_history.py](modules/fleet_history.py)** — HISTORY (NSOT_GUI_BRIEF 3.4, the
  mockup signed off 2026-10-02; `/v2/history`): the remote's one sentence with Push now and Verify
  (`static/js/nmas_history.js`), the network's commits (ONE bounded `git log` whose device,
  person, workflow and time filters git applies, one more for the filter choices; each row's
  actor with how it was established, what its commit earned, a known record exception beside
  it, and its change MASKED on request), the baselines from the `baseline-usability` reader's
  stored judgement (now carrying what each earned), and the freshness authorisations
- **[modules/manual.py](modules/manual.py)** — THE MANUAL (NSOT_GUI_BRIEF 10 and 10a, the
  operator, 2026-10-02): `docs/manual/` (Getting started, How it works per operation, Screens per
  sidebar item and device-page tab, SVG diagrams drawn with token classes), rendered at
  `/v2/help/<page>` and, one section at a time, in the frame's side help panel that every screen's
  `info()` link opens (ONE source). The renderer is a strict in-repo subset (every character
  escaped, no raw HTML, an unknown link form refused), because no Markdown library is on the host.
  `PAGES`, `SCREENS`, `DEVICE_TABS` and `OPERATIONS` (each operation's step list read from the
  code that declares it) are what `tests/test_manual.py` holds the manual to. **A v2 screen is not
  done until its manual page and info link exist** (the operator, 2026-10-02). The cutover
  checklist (every legacy route: built, planned, removed or undecided) is
  [docs/CUTOVER.md](docs/CUTOVER.md)
- **[modules/restarts.py](modules/restarts.py)** and **readers/restarts.py** — device
  RESTARTS (the operator, 2026-10-02: five passed unnoticed): found where the SNMP uptime
  counter FELL (`resets(sysUpTime[w]) > 0`, then where), never now-minus-uptime, which the
  slow vIOS clocks make drift (it turned one lab redeploy into four switch "restarts");
  planned only when the tool reloaded it (its reload records the window first) or was told
  (`scripts/nmas-planned-restart`); the device's own reason and crash file read once. An
  unplanned one is a Needs attention row for 7 days, DANGER with a crash file; every one is
  in the device's History. **A window declared after a restart it covers is refused** unless
  marked a CORRECTION with its own reason (C344), so a window never clears an unplanned
  restart after the fact. A script that restarts devices (the lab redeploy) declares its
  window through **[routes/restarts.py](routes/restarts.py)** (`POST /restarts/planned`, gate
  configure, operation `planned_restart`), recorded as the verified caller
- **[modules/acknowledgements.py](modules/acknowledgements.py)** — C344 (2026-10-02): a person
  ACKNOWLEDGES an event row on Needs attention (an unplanned restart, a line authorised again
  and again: `attention.ACKNOWLEDGED_HERE`) with a reason in the shape of one, recorded with
  who, how established and when (`POST /attention/acknowledge`); keyed on the row AND its
  event, so it never covers a later one. **Every row says how it clears**
  (`attention.CLEARS`: the condition resolving, a person acknowledging, or time), drawn as
  "Clears when …"
- **[modules/heartbeat_windows.py](modules/heartbeat_windows.py)** — P.7's heartbeat generator
  as an ACTION (C300, 2026-10-01): the heartbeat re-measure (`/v2/monitoring/heartbeat`, reached ONLY from the check's Needs attention row, never a tab: the operator, 2026-10-02) previews
  each device's installed window beside the one measured now (`scripts/nmas-heartbeat-rules`
  LOADED, the one implementation; restarts excluded, C299), offers a write only where the
  hourly check fails, writes the rules file as the person, and draws the ONE host step with
  every value filled in until the installed file is the one written. The check's Needs
  attention action opens it; no remedy is a command with a placeholder
- **[modules/nsot/ip_sla_policy.py](modules/nsot/ip_sla_policy.py)** — P.9 (d4), the ADD
  path (2026-10-01): IP SLA probes SUGGESTED from the profile's `ip_sla` policy (`peers` from
  the adjacencies committed intent implies, `gateway` from the global static default, `none`),
  every 60 s by default, a switch's path to a router placed ON THE ROUTER, a path already
  measured skipped, each with its expected CPU cost (measured on vIOS only); one intent commit
  of the ticked ones (`Source: ip-sla`), then the batch Apply with deploy scope `ip_sla`
  (`routes/deploy.SCOPES`, `_scoped()`), which sends only IP SLA lines. Page
  `/v2/monitoring/ip-sla` (`templates/v2/ip_sla.html`), reached only from Coverage's cells and NOT a tab (the operator, 2026-10-02: it folds into the profile's proposal, mockup first). Changing a
  running probe is the re-create (C290), gated on staged run 9
- **[modules/monitoring_coverage.py](modules/monitoring_coverage.py)** — C236: which
  integrations each device is CONFIGURED for, from its committed golden (SNMP, syslog, the
  heartbeat), expected only where the connector is configured (Prometheus; Loki). A device
  missing one is a job-health `not_monitored` row, drawn by Needs attention as "r6 is not
  monitored by SNMP"; an unreadable golden is `unknown`. The prometheus targets take only a
  device it shows configured for SNMP. The monitoring profile that fixes a gap is P.9,
  designed in [docs/MONITORING_PROFILE.md](docs/MONITORING_PROFILE.md), not built
- **[modules/inventory_edit.py](modules/inventory_edit.py)** — C225: a device's ROLE in a
  local list's inventory, the ONE recorded path: a preview (gates, what follows: the Prometheus
  targets' label, the topology icon, NetBox at its next import; what it does not do), a confirm
  by fingerprint, the one field written under the CSV lock, and an audit row in the list's
  `inventory_edits.jsonl` (0600: actor, how established, reason). `scripts/nmas-inventory-role`
  is its interim entry point; the Device page's role edit is proposed on the same module
- **[modules/invalidation.py](modules/invalidation.py)** — Stage 7.0: what
  each mutating route invalidates, in a finite vocabulary of data keys; the
  response carries it. Client: **[static/js/nmas_invalidation.js](static/js/nmas_invalidation.js)**
  (panels subscribe; a failed re-fetch marks the panel stale with a time).
  Since 7.2 it also carries the LIVE-DATA CONTRACT every panel inherits: a
  background job ANNOUNCES its keys over the socket (C58), the channel's
  heartbeat proves it alive, each panel shows the AGE of its value against
  the source's promise (`stale_after_seconds`) on a local tick that makes no
  request, a dead channel is marked on every panel's data, and a reconnect
  catches every panel up. No data polling: every change has a sender
- **[modules/preview_confirm.py](modules/preview_confirm.py)** — Stage 7.1:
  the preview-then-confirm contract. One builder for the six parts (what,
  what will NOT happen, program, operands, gates, confirm), refusing a part
  that is empty without saying so; per-screen adapters (`deploy_preview`).
  One renderer: **[static/js/nmas_preview_confirm.js](static/js/nmas_preview_confirm.js)**
  Its RESULT half (7.1 steps 2 and 3): `operation_result()` builds what
  happened FROM the receipt rows the apply wrote, the server computes the
  level (colour is only drawn, never decided in the browser), and
  `receipt_history()` serves the record back (`GET /deploy/receipts`, the
  Device page's Changes tab)
  Capture's client (7.1 step 4, Device page and Save All):
  **[static/js/nmas_capture.js](static/js/nmas_capture.js)**. Restore scope
  (7.1 step 5, C80: the Device page's "Restore from…" and the Baselines
  panel's scope, which starts empty):
  **[static/js/nmas_restore_scope.js](static/js/nmas_restore_scope.js)**
- **[routes/](routes/)** — Flask blueprints: `settings_integrations.py`,
  `netbox_safety.py`, `inventory.py`, `golden.py`, `templatize.py`,
  `templates.py`, `deploy.py`, `freshness.py`, `devices_view.py` (the device
  list's regions, redrawn in place), `list_param.py` (a read of an unknown
  list refused, C51), `retire.py` (7.3: retire, previewed and confirmed), `templatize.py` (seed, revert and retry among the intent routes),
  `persist.py` (7.3: persist, previewed and confirmed),
  `operations.py` (C99: what is running on the list's
  devices and what finished recently, drawn by
  **[static/js/nmas_in_flight.js](static/js/nmas_in_flight.js)**, one panel
  above every modal)

#### Other
`approval_queue.py`, `config_git.py`, `device.py`, `connection.py`, `bulk_ops.py`,
`backups.py`, `variable_discovery.py`, `event_monitor.py`, `ccie_kb.py`,
`terminal.py`, `commands.py`, `agent_timers.py`, `ai_usage_log.py`, `quick_actions.py`,
`utils.py`, `config.py`

#### Templates
`base.html` (2,442 — layout + AI chat panel), `index.html` (8,045 — main
dashboard), `device.html` (1,239 — per-device page), and
`templates/partials/` for new UI.


### Key Architecture Decisions

- **Data storage:** `data/lists/{slug}/` per device list — devices.csv
  (Fernet-encrypted creds), variables.json, golden_configs/, backups/,
  approval_queue.json, config_repo/
- **Migration is one-directional and runs once.** `config_repo/golden/` is the
  golden store; `golden_configs/` survives as a deprecated **read-only**
  fallback, consulted by `_find_golden_config_file()` only when the manifest has
  no entry for a device. It is never an input to migration again, and nothing
  writes there. `apply()` refuses when `.nsot/migrated.json` exists (`409`), and
  independently of that guard cannot produce an empty commit.
- **One enumerator: `repo.list_goldens()`, keyed on the manifest** (Phase 3.3).
  `_list_golden_configs()` was `os.listdir(golden_configs/)` and nothing else,
  while `_load_golden_config_file()` resolved through the manifest —
  **enumeration and content came from different stores**, and 17 executable
  call sites across 9 modules asked the enumerator which devices have a
  golden. The nine reference devices were enumerable only because their
  pre-migration files still sat in the legacy directory: **that coverage was
  inherited, not designed.** A device onboarded after the migration was
  checked by nothing and reported by the event monitor as having no golden,
  while its config sat in `config_repo/`. `_list_golden_configs()` is now a
  thin adapter over `list_goldens()`, so every caller was fixed without being
  touched, and `saved_at` is the **commit** time rather than the file's mtime.
  Legacy-only devices are still returned, flagged `legacy`, and
  `legacy_only_goldens()` is the store's **retirement condition** — when it is
  empty for every list, the directory and the header scan go. `GET
  /golden/legacy_store` reports it on the Golden tab.
- **Platform lives in the manifest, sourced from the inventory.** The `platform`
  CSV column (local lists) or the NetBox platform slug (NetBox lists), resolved
  through `platform_for_device()` and refreshed by `manifest.sync_platforms()`
  on every inventory change — not only at migration.
- **AI read-first:** the agent checks golden configs and variables before opening
  any SSH session
- **Secrets are redacted at the provider boundary** (`modules/redact.py`),
  immediately before `messages.create()` — `system`, `messages` and `tools`.
  Not at the golden reader: `show running-config`, backups, drift diffs and any
  free-form command carry the same values, so per-reader redaction is N places
  that must each remember and a new tool inherits the gap. Values are replaced
  by `<redacted:<ref>>`, so the model still knows a secret is there. Values
  shorter than 8 characters are left alone — redacting `RO` wherever it
  appeared would corrupt every config and protect nothing.
- **Redaction is value-based AND positional, and the second does the work
  here.** Measured on the live fleet, **14 of 18** stored secrets fall under
  the 8-char value floor — every SNMP community (6) and every plaintext router
  password (7) — so value matching alone covered almost none of the real
  exposure. `redact_positional()` masks whatever occupies a secret's syntactic
  slot (`snmp-server community <X>`, `username … password|secret <X>`,
  `enable secret <X>`, `key-string <X>`, `tacacs/radius key <X>`, line
  `password <X>`, `ppp chap password <X>`) regardless of length, and regardless
  of whether the store has ever seen it — so an un-onboarded device is covered
  too. Fleet result: **0 unmasked secret-position lines across all nine**. The
  word "public" in an interface description is deliberately left alone; the
  community is already masked where it is a community.
- `credentials.device_credential_values()` decrypts CSV fields with
  `device.decrypt_field` (raw Fernet), **not** `secrets_store.decrypt_value`,
  which returns anything unprefixed unchanged — using it collected 100-char
  ciphertext that no device would ever echo.
- **Config push workflow:** the confirmed deploy path, and nothing else
  (P.3): plan, confirm by hash, then the pipeline snapshots, pushes
  merge-only, verifies and saves the golden. The older "push, then Jenkins
  CI, and a CI pass auto-approves" described a Jenkins nothing configured,
  and P.4 removed it.
- **Approval queue:** destructive AI actions go through `approval_queue.py`. Its store
  is one file per list, every read-modify-write under ONE cross-process lock with an atomic
  replace; an unreadable queue refuses every write and answers every read with its reason;
  reads write nothing (CONCURRENCY_AUDIT R4, 2026-10-02).
  **Nothing resolves an item without a human**: the only callers of `resolve()`
  are three HTTP routes, expiry marks items `expired` and never executes, and
  neither `agent_runner` nor `event_monitor` nor any AI tool can approve — they
  only *add*. `revert_to_golden` **hands off to the confirmed restore path**
  instead of executing. It used to push a stored diff with no confirm hash, no
  mask check, no sendability check, and an unbounded `no <command>` per added
  line. Approving one now opens the restore preview for that device **at
  HEAD** — a single-device revert *is* a Mode A re-apply of its HEAD golden —
  and the operator confirms a program computed **now**, from the device as it
  is now.
- **Every queued kind now ends in a confirmation** (C105, 2026-09-27). A
  drift item's "record the running config as the golden" read the device
  and committed with NO preview on approve, one click per item, and drift
  queues one for every drifted device: a second capture path inside the
  queue, the least guarded one. It hands off to the capture operation now
  (read now, previewed, confirmed by hash, recorded as the verified person
  with `Source: capture`), and the capture closes the item only for a
  device it recorded. **Approve-all approves nothing by itself**: it opens
  ONE capture preview for every drift item's device and names reverts for
  individual review. It is `not_device` in the gate table, because it
  records nothing; the capture apply, gated `approve`, does.
- **The queued diff never reaches a device.** It was computed when the drift
  was noticed, which is not when the operator is looking; a program the
  approver never read is what the confirm hash exists to prevent. It travels as
  **advisory context** ("what the agent saw"), is displayed above the fresh
  program labelled *not what will be sent*, and is echoed by the route and
  nothing else — a test asserts the only line mentioning it is the echo.
- **Approving a confirm-ending item does not resolve it.** It stays pending
  with an "Awaiting confirmation" note, because marking it approved would have
  the queue claiming a change nobody has sent. `mark_done()` closes it when the
  restore succeeds, and **only** for devices that actually succeeded — an item
  closed on a failed push is the queue claiming work that did not happen.
  Without it, items linger and the operator learns to clear the queue by
  rejecting things, which is the habit that makes an approval queue worthless.
- **Connection pool:** Netmiko SSH connections reused via `modules/connection.py`;
  the reachability reader (C92) tracks answering / not answering over
  consecutive probes; `session_reaper` closes idle pooled sessions
- **No auto-continue** (P.3 step 8): the agent loops tool calls until the task completes, and a
  question it asks is for a person. It used to answer its own confirmation questions with a canned
  "yes, continue"; only the continuation of a reply the token limit cut off remains
- **telnetlib shim:** `telnetlib.py` in root — Python 3.13 removed it from stdlib

#### NetBox write safety (Phase 0)

NetBox reads are unrestricted. **Writes are fail-closed** and go through exactly
three chokepoints in `netbox_client.py`: `_nb_post`, `_nb_patch`, `_nb_delete`.

Two independent conditions must both hold before a write from the **NetBox
tab** (import, import-all, Remove) executes. **Only there** (C155, measured
2026-09-28): the chokepoints check the master switch alone, and the token is
consumed by the NetBox tab's routes before they call the writer, so any other
path that reaches a writer passes on the switch: onboarding's phase 2 and
Abandon, the host scripts, and list deletion's opt-in NetBox removal (which
deletes with no preview and no token when `netbox_remove_on_list_delete` is
on or a request carries `remove_from_netbox`). The sentence said "before
any write" until then. **Since the same day the check IS where the write
happens** (the operator's decision, the C101 move): `assert_writes_allowed()`
refuses a real write that declares no AUTHORITY (`for_list(..., authority=)`),
and each path names the confirmation it stands on: the NetBox tab's one-time
token, a person's Verify (onboarding phase 2) or Abandon, or a host script's
`--apply`. The created-object and modification records store it beside the
actor, so a NetBox write says WHO and ON WHAT BASIS, as a commit does:

1. `netbox_allow_writes` — the **master switch**, meaning "this instance may
   write to NetBox at all". Defaults off. A persistent operator decision; it is
   never flipped as a side effect of confirming an operation.
2. A **single-use authorization token** (`modules/netbox_authz.py`) issued by a
   preview and bound to a hash of that exact plan.

- **Import and Remove still work.** Clicking either runs a read-only dry run
  (allowed regardless of the gate, since it writes nothing) and shows a preview
  of every object that would change.
- **Confirming is one-shot.** Execute consumes the token, recomputes the plan,
  and aborts with "NetBox changed since preview" if the hash differs. Tokens
  expire in 5 minutes and are burned even on a failed validation, so they cannot
  be replayed.
- **The preview count is the executed count**, including dependent objects under
  a device that does not exist yet (placeholder ids) and shared objects counted
  once rather than once per device.
- Every object NMAS **creates** is tagged `nmas-managed` and its id recorded in
  `data/netbox_created_ids.json`. Objects NMAS merely updates are never tagged —
  the tag is injected in `_nb_post` only, never `_nb_patch`.
- **Removal deletes only the intersection** of those two: tagged *and* in NMAS's
  own record. A region, site, VRF, or device a human curated is reported as
  skipped. Removal previously deleted everything in the site regardless of origin.
- Deleting a device list **never deletes NetBox objects** (C155, the
  operator's decision, 2026-09-28): removal has one home, the NetBox tab's
  previewed and confirmed Remove. A list that still owns recorded objects is
  REFUSED, naming them, because forgetting the record while the objects stay
  leaves them tagged and unrecorded, out of Remove's reach for good. Until
  then an opt-in setting deleted them with no preview and no token, and its
  switch is gone.

#### Inventory sources (Phase 1)

A device list is either `local` (a CSV — the default, and what every
pre-existing list uses) or `netbox`, set per list in
`data/lists/{slug}/source.json`. An absent file means `local`.

- **`load_saved_devices()` is the single dispatch point.** It has ~79 call
  sites across 11 modules; routing the decision through it means bulk ops, the
  terminal, backups, drift, topology, the connection pool and the AI tools all
  work on a NetBox list without changes.
- **Dispatch never performs network I/O.** A background refresh queries NetBox
  and resolves + encrypts credentials once per refresh; dispatch serves finished
  dicts from memory. The adapter returns credentials **still Fernet-encrypted**,
  matching a CSV row, because callers decrypt at use.
- The last good inventory is persisted to `netbox_inventory_cache.json` —
  **identity only, never credentials** — so a restart during an outage still
  yields the last known list, badged stale. Credentials are re-resolved on
  rehydrate.
- **Identity is read-only.** CSV writers refuse, and the UI disables Add Device,
  Delete, Discover→Add and Refresh Hostnames with an "Edit in NetBox" tooltip.
  Drag-and-drop ordering is supposed to be stored in `source.json`, and it is NOT wired: `/reorder` refuses on a NetBox-sourced list and the source.json route has no caller (register D7).

**Credential resolution** (`modules/credentials.py`), first match wins: device
override → the list's *designated* `credential_list` (one list, never a scan) →
role profile → site profile → default profile. Every device carries
`_cred_source` so the origin is visible. Deleting a designated credential list
warns about dependent lists; "Copy inherited credentials into device overrides"
decouples on demand.

**Incomplete NetBox data:** a device missing `primary_ip4`, an unmapped
platform, or unresolvable credentials is **skipped with a per-device reason**,
never failing the whole list. An unmapped *role* is only a warning — it resolves
to `""` and topology falls back to hostname inference. Set
`platform_default_netmiko_type` to trade a platform skip for a warning.

**Stale devices:** a device that vanishes from NetBox keeps its golden configs
and backups but becomes **inert** — the approval executor, drift checker, and AI
tools refuse to act on it, and its pooled SSH session is closed.

#### Golden config repository (Phase 2)

`data/lists/{slug}/config_repo/` is the NSoT repo: `golden/<device>.cfg`,
`.nsot/manifest.json`, `infra/`, `.gitattributes`.

- **Every reader takes what is COMMITTED, never the working tree** (C104,
  2026-09-27; the operator's reframing: "one write path, committed
  immediately" made the COMMIT atomic and said nothing about what the
  READERS take, and the store the readers used and the store the writer
  commits to were one directory with rules on only one side). Measured: a
  `save_golden()` whose commit failed left the golden written and staged,
  and the drift checker, the NetBox import, onboarding, the freshness gate
  and the agent read goldens from disk, so a file no save had committed
  already governed the tool. Intent was worse: `read_committed()` opened the
  working file, so a hand edit to `host_vars/` nobody committed was what the
  deploy plan DEPLOYED, and what the baseline's intent comparison, bulk
  intent's compare-and-set, rotation and the editor read.
  **Structural now, not incidental:** goldens are read as `HEAD:<rel>`
  through `repo.committed_golden_for()` (and `_golden_record()` for a device
  by address), intent through `committed_at_head()`, and goldens are
  enumerated from `git ls-tree HEAD`. **The first pass said "one resolver"
  and was false**: six more functions resolved a golden's path and opened
  it themselves, the deploy plan's capture among them (the diff it plans
  from and the hash its confirm is bound to), plus rotation twice, the vty
  count, extraction and Refresh Hostnames, and three scripts, two of them
  producing template-approval evidence. The test that should have caught
  them asserted "the resolver has one caller" over `modules/` and `routes/`
  only: the wrong property, over too small a population (no `app.py`, no
  scripts). The rule now checked is the property itself, across the
  program and its scripts: a function that resolves a golden's or intent's
  path never opens a file, with each exception named. A working file that differs is ignored and named in
  the log; a file nothing committed is refused by path; a golden whose last
  commit carries no `Source:` (the save path's trailer, on all nine on the
  host) is refused naming the path and the commit. So the next writer that
  fails in a new way cannot make its file authoritative.
  **Visible too:** the Git tab's status lists every uncommitted path with
  what it means (it said "working tree clean" whenever nothing was STAGED),
  and each writer that stages undoes it when its commit fails. The manual
  commit is removed: it was used three times on the host (30 Aug, 1 Sep,
  15 Sep, before saves committed in their own call), and since then it had
  nothing to commit but residue. (First recorded as "never used, in 100
  commits": the search looked for `Source: manual`, a trailer the tab wrote
  only from D10. A lookup that misses is a fact about the query.)
  `tests/test_readers_use_what_is_committed.py` hand-writes an uncommitted
  change and drives each consumer; its first drift control passed because
  the test computed its expected value with the reader under test.
  **And every WRITER stages exactly the files it wrote** (C175, A, fixed
  2026-09-28): every writer ran `git add -A <tree>`, so another device's
  uncommitted hand edit rode into an unrelated commit, with a real
  `Source:`, and was then read as committed. The reader rule from the
  other end. `repo.stage_exactly()` refuses a directory and refuses when
  the index already holds a path outside the commit, naming it; the
  migration is the one declared exception, and a scan finds the next
  writer that hands over a tree.
- **One write path.** Everything that promotes a golden config goes through
  `nsot.repo.save_golden()`. **One call is one commit**, even for a nine-device
  Save All. An unchanged device creates no commit but is still reported.
- **Identity is resolved, never minted by accident.** `resolve_identity()` takes
  the item's identity, else the manifest by IP, else by name — and mints only
  when `allow_new=True`. The pipeline passes `allow_new=False`: a deploy targets
  a device the inventory already knows, so arriving with no identity is a bug,
  not an onboarding. A function that creates identity when none is supplied
  always masks a caller that forgot to supply it.
- **Timestamps live in git**, not in the file. The file keeps one stable header
  line; `! Saved:` / `! Source:` are gone because they produced a diff on every
  save. Commits carry `Source`, `Actor`, `Device-Id`, `Device-Name` trailers,
  and annotated tags `golden/<device>/<UTC>` and `baseline/<UTC>`.
- **An `Actor:` trailer is WHO is accountable, never WHAT ran.**
  `repo.ACTOR_CONVENTION`. Three kinds: a **person** (email, or the OS user
  for a command run on the host); **`ai-agent`**, the exception that proves
  the rule since it genuinely decides without anyone typing a command; and
  **`service:<client-id>`**, matching the identity layer's own prefix. A
  one-off script is none of these — nobody is accountable to a program — so
  it records the person in `Actor:` and names itself in a `Tool:` trailer.
  `Source:` names the workflow (`manual`, `save_all`, `pipeline`, `approval`,
  `ai`, `onboarding`, `extraction`, `repair`, `rotation`) and is free text by
  design: an enum would have to be edited before any new workflow could
  commit. **Until 2026-09-27 the code did the opposite** (C104): a list, and
  anything outside it silently rewritten to `manual`, so all eleven rotation
  commits on the host name the wrong workflow. Any lowercase slug is now
  recorded as given, a malformed one is refused before anything is written,
  and an AST test checks every literal `source=` in the program. The
  first repair commit carries `Actor: description-repair` and predates this;
  it is left alone, and is why the convention is written down.
- **`Actor-Verified:` says how the `Actor:` was established** (D10, P.3 step
  10): `access` (a request whose gate verified that same actor), `host-shell`
  (a CLI on the host) or `none`. It is written in ONE place, `repo.git()`,
  for any message carrying `Actor:`, so no writer has to remember it. It is
  decided by the code at the moment of the commit, never by date: the host
  ran old code after `c5a34c1` was pushed. A commit without it predates P.3,
  and its `Actor:` is a claim.
- **Identity, not filename.** The manifest keys on `nb:<netbox_id>` or
  `uid:<uuid4>`. A rename is a `git mv` committed **alone**, which is what keeps
  `git log --follow` working across it.
- **Refresh never writes to git.** An inventory refresh records
  `pending_rename` in the manifest only; the `git mv` happens at the next
  `save_golden` or via "Sync device names to repo". Both names resolve while
  pending.
- **Re-apply goes through the confirmed deploy path**, not the approval queue.
  Every read at a ref goes through `repo.RefSource`, whose allowlist is a
  **constructor argument** — restore declares `("golden/", "host_vars/")`, so
  asking for `templates/`, `bindings.yml` or `.approvals.json` raises
  `ScopeRefused`. Templates are code; rolling them back to restore a *network*
  would silently revert template fixes. `RestoreTarget` duck-types what
  `plan_batch()` reads, so the confirm hash, ASCII guard, provenance,
  `error_pattern`, failure capture, circuit breaker, staging and single golden
  commit all apply unchanged.
- **It is additive, and labelled as such.** The button says *Re-apply this
  baseline*; the confirm reports `add` / `replace` / `residue` per device and
  states that residue is **not** removed. Removals are Mode B, not built.
  Queued items from the old path are rejected with a reason on first use —
  executing one would push whole-config text through the unguarded executor.
- **Device and committed intent are one unit, per device.** Restoring the
  config alone leaves the next template plan offering to undo the restore, so
  the ref's `host_vars` are re-committed **verbatim** in the **same commit** as
  that device's golden capture — for devices whose push succeeded only, staged
  to `.nsot/staging/restored_intent/` across the crash window. Verbatim needs
  `repo.git_raw()`: `git()` strips stdout and drops the trailing newline, which
  would land a one-byte diff labelled "restore".
- **Intent restore is a forward commit.** Nothing is reset or force-pushed; the
  replaced intent stays reachable by `git log -- host_vars/<device>.yml`.
- **Un-onboarding is opt-in, never a default.** A ref predating a device's
  onboarding has no intent to restore, and deleting today's would un-do a human
  review — so the default outcome is **skip**. Ticking it re-runs the
  *preview*, because a skipped device has no command list and confirming
  commands nobody was shown is what the confirm hash exists to prevent.
- **`validate_restored_intent()` refuses at plan time** when a ref's intent no
  longer round-trips through today's templates, or names a secret the
  credential store no longer holds.
- **`baseline/<ts>` is earned by measurement, not granted by mode.** A skipped
  device counts only if it was **measured**, so a restore baseline requires
  *every inventory device measured equivalent to the ref, whatever path got it
  there*. A device with nothing to send is still read back
  (`_measure_unchanged`), because "nothing to change" was decided against a
  **stored** capture; an unreachable device contributes nothing and declines
  the tag. **Residue therefore denies a restore baseline** — merge-only cannot
  remove it, so the network is not at the ref. Deploy baselines stay
  coverage-only: their goldens *are* the post-deploy captures.
- **`save_golden()`'s empty-commit guard covers the whole commit**, not just
  `golden/`. A restore to a ref a device already matches changes no golden and
  still moves its intent; `extra_paths` staged content keeps the commit alive.
  A call with neither still creates nothing, EXCEPT a baseline decision (C184,
  2026-09-28): a Save All that changes no golden still DECIDES the baseline, and
  that decision gets an empty commit whose subject says no configuration changed,
  carrying `Baseline:` and `Intent-Match:`, so a denial and its reason are kept
  and an earned tag has its own commit. Without it the reason lived in a toast.
- Stale devices are skipped and **named** in the confirm dialog.
- **Migration is dry-run by default.** It merges case-insensitive and IP-level
  duplicates keeping the newest content, reports every merge, and backs up
  rather than deletes.
- **Every commit that moves a device carries `.nsot/manifest.json`.** The
  rename commit stages `.nsot` alongside `golden`, so a clone or bundle restore
  at that commit resolves the new name instead of falling through to the legacy
  header scan. `save_templates()` deliberately does not touch the manifest.
- **`.gitignore` rules are applied on repo access, not only at creation.**
  `ensure_repo_hygiene()` runs from `git()`; `GITIGNORE_RULES` is the list. A
  repo created before a rule existed is topped up on first touch.
- **Every commit publishes, by construction** (C223, 2026-09-29): `repo.commit()`
  commits and hands the commit to the hooks, and a scan fails the suite on any
  other git call naming `commit`. Abandon, the rename commit, the migration and
  `config_git`'s first commit each called git directly and never reached the
  push hook, so a commit could stay on the host with nothing said. Whether the
  history IS on the remote is measured by asking the remote (the
  `remote-publication` reader), never taken from the hook's own record.
- **Post-commit hooks register where the repo module is USED, not where the
  app starts.** `hooks.run_post_commit()` calls `ensure_default_hooks()`
  first. Registration lived in `app.py`, so a commit from any process without
  Flask — a CLI repair, a cron job, a maintenance script — met an empty
  registry and `run_post_commit()` returned silently: measured, a fresh
  interpreter reports `[]` until `app` is imported. The 1.4 repair commit went
  in that way and stayed local while the Remote card accurately showed the
  previous push. An empty registry on a list that **has** a remote is now an
  error and records `last_push_failure`, because "a commit that could have
  been published and was not" must never be silent. A list with no remote
  stays quiet, or the error stops meaning anything. Hooks run on a background
  thread with short timeouts and never block a commit. Push never
  force-pushes.
- `nsot_device_tag_retention` (default 50) prunes per-device tags only;
  `baseline/*` tags and all commits are kept.

**Config-line filters** live in `modules/nsot/normalize.py`. They are *not* one
list — four different jobs, and `push_safe_lines()` filtering `end` is a
truncation guard, not cleanup. `test_normalize_equivalence.py` pins each to its
prior behaviour.

#### Templatization (Phase 3a)

Config → `host_vars` YAML → render → compare. **Read-only**: extractions go to
`config_repo/.nsot/staging/host_vars/` (gitignored); 3b adds the reviewed commit.

Current coverage across all nine reference devices (R1–R5, S1–S4):
**100% modeled, 100% round-trip fidelity, zero unmodeled constructs — under the
depth-aware comparison**, and `merge_commands()` against each device's own
capture is empty for all nine.

An earlier "100% across nine" was measured by a comparison that could not see
nesting depth. `split_blocks()` flattens every indented line into one list, so
`roundtrip._sections()` compared a two-level block as one level — and the
cisco_iosxe template, whose render hoists BGP networks and neighbor activations
out of their address-families to the top of `router bgp`, scored 100%. **The
fixtures contained the address-families all along; parse and render flattened
symmetrically, so both sides agreed with each other while both disagreed with
the device.** `scripts/nsot_metric_diff.py` reports flat vs depth-aware per
device and lists every nested construct in the corpus; the two now agree
everywhere.

- **BGP address-families own their contents.**
  `routing.bgp.address_families` is `[{afi, networks, neighbors, settings}]`.
  Nothing belongs at the top level of `router bgp` that the device puts inside
  a family. The old shape put `network 8.8.8.8 mask …` and
  `network 2001:DB8::/32` in one list and left the `address-family` headers in
  `settings` as ordinary text.
- The existing `test_bgp_address_families_on_r3_r4_r5` asserted
  `any("address-family" in s for s in bgp["settings"])` — **it pinned the
  flattening as correct**, under a name that made the construct look covered.

Decision rule for what to model: **any construct appearing on 2+ devices, or
any routing/redundancy protocol in the network design.**
`test_fleet_coverage.py` enforces it.

- **One parser module per platform** (`cisco_ios`, `cisco_iosxe`). A new vendor
  is a new module plus a template directory — that is the multi-vendor story.
- **Secrets are hashes.** `enable secret 9 $9$…` has a per-hash salt and cannot
  be regenerated; the store holds the hash string and templates emit it
  verbatim. `secret_kind: hash` marks values Part 2's rotation must skip.
- **Comparison is depth-aware.** `modules/nsot/sections.py` holds the
  indentation→ancestry algorithm; `_sections()` keys on a line's full container
  path (`router bgp 65002 > address-family ipv4`). A container is a key, never
  also a child of its parent — listing it in both counted it twice. The global
  scope `""` is a scope, not a section: it contributes no section-level match
  (a wholly unknown config scored 16.7% instead of 0 when it did) and is
  **unordered**, because a template emits globals in its own order and the flat
  comparison never checked that either.
- **Ordered comparison by default.** Reordered ACLs / prefix-lists / route-maps
  / `ip sla` fail. The unordered allowlist covers only what the device treats
  as a set, plus interface bodies (IOS reorders those itself). With paths,
  `section_is_unordered()` tests **every component** and
  **order-significant anywhere wins** — a route-map nested in an unordered
  block is still a route-map.
- **Interface names are canonicalized** on both sides (`Gi0/0` →
  `GigabitEthernet0/0`), including references inside lines.
- **Coverage is reported honestly**: `modeled_coverage` counts `unmodeled`
  against it; `round_trip_fidelity` is separate.
- `strip_for_roundtrip()` removes what a template *cannot render* — distinct
  from volatile.
- **Every volatile pattern anchors to column 0** unless listed in
  `NESTED_OK_PREFIXES`. `version 17.6` is the image version; `  version 2`
  under `router rip` is RIPv2. Stripping the latter from both sides of a
  comparison hid the loss entirely, so only extraction-side tests catch it.

#### Template library and the deploy gate (Phase 3b)

`config_repo/templates/` holds the network's templates, seeded by copy from
`modules/nsot/templates/`. Templates are **per-platform**; per-device divergence
belongs in `host_vars`, with an explicit `bindings.yml` override as the
exception.

- **Nothing in 3b opens a socket.** Previews diff against captured artifacts
  only — a golden config and the newest stored backup, each labelled with its
  capture time. "Refresh capture" delegates to the existing backup route.
- **`deployable` is a computed property on a frozen dataclass.** A device with
  unmodelled constructs cannot reach a deployable render by any code path.
  `build_artifact()` is the only constructor and always validates.
- **`intended/` and previews are masked, so neither is ever a deploy source.**
  3c must re-render from the template with real secrets in memory;
  `assert_no_mask()` guards that path. Validation runs on the truthful render.
- **Unmodelled constructs can be acknowledged**, not dismissed: `unmodeled_ack`
  in `host_vars` must list the exact lines, is committed to git, and is
  invalidated by any new or removed unmodelled line.
- **Approval is the TEMPLATE: its closure hash and who approved it (scheme 3,
  P.5, built 2026-09-26).** A claim about the template, never about a device:
  whether a device is reproduced faithfully is its own plan's
  `template_report`, gating in `blocking_reasons` per device with the lines
  named, so a device the template cannot reproduce is blocked ALONE instead
  of blocking every other device on its platform. Approving validates against
  the bound devices, needs **at least one** to round-trip, and records every
  device's result as evidence (validated, failed with the reason, not
  validated for want of a capture). The hash covers the **whole import
  closure** — a template is `base.j2` plus every macro file it imports, and
  `_common.j2` holds the routing, interface and service macros for both
  platforms, so editing any file revokes every approval whose closure
  contains it. The badge says what an approval **covers and what it does
  not** (`approval.COVERS` / `DOES_NOT_COVER`), because without the second
  sentence scheme 3 reads as weaker than scheme 2 to anyone who does not know
  why. History, each a correction: scheme 1 hashed each device's host_vars,
  so a deploy revoked its own approval; scheme 2 hashed the bound device set,
  so onboarding one device revoked every approval on its platform and one
  device the template could not reproduce blocked all the others (D11, D2).
  Records carry a `scheme`; an older one is never silently honoured, so the
  move to scheme 3 is an explicit re-approval. **Observed on the host
  2026-09-26:** after the deploy every deploy refused until a person
  re-approved both templates (`be60f59`, all nine devices round-tripping). By
  design, and the operator's reading of it is the rule: an older fingerprint
  answered a different question, so honouring it would be a gate that passes
  because nobody migrated it. The cost is one deliberate act; the alternative
  is a gate nobody can tell is stale.
- **Revocation is a recorded finding, not a deletion.** `approval.revoke()`
  requires a reason and writes a tombstone carrying it, the actor, and what was
  withdrawn. Popping the record made a withdrawal indistinguishable from "never
  approved" — both block a deploy, so the gate was never wrong, but the finding
  was thrown away. `is_approved()` refuses a `revoked` record **first**, ahead
  of the scheme and fingerprint checks, so no later computation can overturn
  the decision. `POST /templates/revoke/<path>` is the reachable path.
- Template commits use their own namespace (`template:`) and create **no tags**.
  **Seeding commits itself** (`template: seed library`), so an approval's diff
  is the approval rather than the whole library.

#### Deploy from template (Phase 3c)

The only part of the NSoT work that reaches a device.

- **Intent is committed, never inferred.** `config_repo/host_vars/<device>.yml`
  is the only intent source on the deploy path; `.nsot/staging/host_vars/` is
  gitignored scratch. A device with no committed intent is `bootstrap` and
  **not deployable** — deriving intent from the device's own capture makes the
  diff empty by construction. A change is made by editing committed intent and
  committing it (`host_vars: <device> <summary>`), not by configuring the
  device and re-extracting. A device's FIRST full intent is
  seeded from its committed golden (`modules/nsot/seed.py`, C148), once: only
  absent or bootstrap-only intent is ever seeded.
- **Design rule — gate on template fidelity, never on intent drift.**
  `template_report` (render of the capture's own parse vs the capture) answers
  "can this template reproduce this device as it is"; if not, a render from
  intent is untrustworthy whatever the intent says, so it gates. `report`
  (render of committed intent vs the capture) is *drift* — the change being
  deployed — and gating on it would make every change block itself. Approval is
  keyed on capture-parsed host_vars for the same reason: it is a claim about
  the template, not about one device's intent.
- **Every pushed line is attributed before the confirm.** Merge-only pushes
  every line the render has and the device lacks, so anything that drifted on
  the device since the capture rides along. The plan renders the *previous*
  committed intent against the same capture and splits `to_add` into
  `from_this_edit` and `pre_existing`.
- **Secrets are scoped to their device list.** The credential-store key is
  `<list-slug>:<hostname>:<ref>`, built **only** by
  `credentials.template_secret_key()`. It used to be `<hostname>:<ref>`, built
  by four f-strings in three modules over one installation-wide store, so two
  lists each holding an `r1` shared a key: the second list's extraction
  silently replaced the first's, and the first network then deployed the
  second's SNMP community with every guard on the deploy path satisfied.
  `set_template_secret()` refuses to replace a secret another list owns, which
  covers a caller that builds the key by hand. Legacy keys migrate on startup.
  `assert_no_secret_values()` deliberately scans **every** list's secrets,
  narrowed only by device — it is a leak guard, and narrowing it by list would
  make a wrong derivation silently check nothing.
- **Masking is OUTBOUND, never at rest.** Golden configs are stored verbatim.
  Masking them would make `golden/` depend on `data/key.key`, which is not in
  the repository — so a private remote would hold configs nobody can restore a
  network from, defeating the point of having one. Secrets are redacted on the
  way *out* instead (provider payloads, API responses, logs). Rotation is what
  kills plaintext already in history; masking new commits does nothing about
  it.
- **Secrets:** committed host_vars hold `secret_refs`; values live in the
  credential store. `write_committed()` refuses a `secrets:` mapping or any
  resolved value, checked structurally and by value. `hydrate_secrets()` is the
  only place names become values, in memory, at deploy time.

- **The 3b contract, in order**: refuse a non-deployable artifact → re-render
  with **real** secrets in memory → `assert_no_mask()` → only then connect.
  `intended/` is masked and is never read on this path.
- **Merge-only.** Missing lines are added; lines on the device the template does
  not mention are **removal warnings**, never negated. `assert_merge_only()`
  checks provenance rather than grepping for `no`, because a template may
  legitimately contain `no ip http server`.
  **What that costs, since Mode B is not built** (the operator, 2026-09-28): a
  hand change becomes permanent in the record until someone undoes it by hand.
  The tool can adopt the line into intent or leave it; it cannot remove it.
- **What the operator confirms is what is sent, byte for byte** — not a
  superset, not a safe one. `merge_commands()` builds the exact program: each
  added line preceded by its full ancestor chain in order, one `exit` per open
  level at the end of each contiguous group, never `end`. The list is
  recomputed at apply and compared against the confirmed fingerprint; a
  mismatch is refused with "the device or intent changed since you confirmed".
  `PipelineContext.rendered_commands` **derives** from `confirmed_commands`
  when one is set — assigning over it raises `ConfirmedCommandsOverwritten`, so
  no stage can substitute its own render. `test_deploy_contract.py` runs the
  full pipeline with a spy transport and asserts the list reaching the wire is
  the list the plan published.
- **The target list is carried, never re-derived.** `PipelineContext.list_name`
  is set once by the originating request. The pipeline asked
  `get_current_list_name()` at three points *after* the push, including the
  golden commit — and that function reads a file on disk, so a list switch
  during a 45–90s convergence window committed one network's captures into
  another's repository. `allow_new=False` hid it until two networks shared a
  device name or address, i.e. exactly the multi-network case. `restore`'s
  `_devices_of()` is the same correction: a function taking `list_name` must
  not read its inventory from the active list.
- **Transport is per platform.** `supports_netconf: false` goes straight to SSH
  with no attempt — not a fallback after a timeout.
- **`deployable` subsumes sendability.** `build_artifact()` measures
  non-printable bytes on the truthful render (never the masked one — the mask
  is U+2022) and `blocking_reasons` carries them, so there is one answer to
  "can this go out" rather than an artifact saying yes and `merge_commands()`
  saying no later.
- **Dangerous commands are authorised at plan time, per device.** The CI gate's
  `allowed_dangerous` override existed since Phase 0 but `_deploy_one()` could
  not supply it, so any program containing `shutdown`, `no ip address`,
  `no router ospf`, `reload`, `erase nvram` or `crypto key zeroize` was
  unrunnable. The plan flags each dangerous line as an exact string; the
  authorisation is `{device: [{line, reason}]}`, is folded into the
  confirmation hash alongside the commands, and apply recomputes both. An
  authorisation matching nothing in the program is refused — a typo means the
  line it was meant to cover is *not* authorised.
  **Every authorised line carries the person's stated reason** (C140, the
  operator's decision (a), 2026-09-28). Until then it was `{device: [lines]}`:
  the receipt recorded which lines and who, never why, so an authorised
  `shutdown` read afterwards exactly like a misclick. ONE mechanism,
  `modules/nsot/authorisation.py`, for both classes that need one: a
  dangerous line, and a secret-position line a restore would ADD (C79). The
  reason's minimum is SHAPE, never quality (not empty, three words, not a
  copy of the line); it is drawn as TESTIMONY ("stated reason"), never as a
  cause; it is in the confirm hash and the receipt; and each preview shows
  how often that line was authorised on that device before (the aggregate:
  the same line again and again is the pattern worth seeing). The pipeline's
  gate and a restore target's checks run on every path, so they honour only
  an authorisation whose reason has the shape of one. 8.8's written override
  reuses this module. A line is named by `authorisation.key()`, its secret
  positions masked, because the browser only ever sees a masked program.
- **Rollback is exempt from that gate, structurally** — it never passes through
  stage 3. Undoing an authorised `no shutdown` is `shutdown`, and a gate that
  blocked the repair would leave the device in the state the rollback was
  called to fix. `assert_rollback_provenance()` is the authorisation; exempt
  lines are recorded in the deploy result.
- **Anything that reaches a CLI is printable ASCII — comments included.**
  `assert_sendable()` refuses any other byte before connecting, and
  `hostvars.assert_printable()` refuses it at commit. An em dash is three UTF-8
  bytes; IOS consumes the first, loses sync, and truncates the line, which
  surfaces as a Netmiko echo timeout rather than as an invalid character. The
  rule is **not** "the deploy path": the same character later hung a vIOS boot
  from a *comment* in a startup config, because vrnetlab types that file into
  the console line by line and waits for a prompt after each one. The C8000v
  booted the identical content, since it loads its startup config as a file —
  so one platform can never reveal the property. Everything
  `modules/nsot/bootstrap_config.py` emits goes through `assert_sendable()`
  over the **whole** rendered text, and on console-replayed platforms it emits
  no prose comments at all.
- **Rollback undoes what LANDED, not what was pushed.** On a partial push those
  differ by definition, and with `error_pattern` live a rollback line answering
  a rejected push line can itself be refused and take the repair down. Rejected
  lines are reported as *not undone — never applied*. An unreadable capture
  means everything pushed is undone, which is the conservative answer.
- **The broad command key applies only to free-form values** (`description`,
  `banner`, `remark`, `name`). Everything else needs a precise-key match; a
  miss means there is no prior value and the answer is to negate. Searching
  harder is what matched `ip mtu 20000` to `ip address …`.
- **Rollback is computed, not replayed.** `rollback_commands()` inverts exactly
  what was pushed — re-send the old line where the pre-change config set the
  same thing differently, negate where it did not set it at all. A replay is a
  *merge* and cannot remove a line, so it could never undo a `shutdown`.
  `assert_rollback_provenance()` bounds the one place this tool generates `no`.
- **Rollback restores the device; the intent is separate.** A rollback records
  `.nsot/rolled_back.json` against the device's current intent commit, which
  blocks the next plan — otherwise it would propose exactly what just failed.
  The block is **containment, not equality**: it stands while the failed lines
  (each within its header chain) are still among the lines that would be sent,
  so an unrelated edit that adds its own sent line cannot bundle the failed
  change back out. Lifting it deliberately is `authorise_retry()`, an explicit
  recorded action. "Revert intent"
  (`POST /templatize/committed/<host>/revert`) applies the **inverse of that
  commit's own diff** onto current intent as a forward commit — keeping later
  unrelated commits, and refusing with the paths named when a later commit
  touched the same settings. A snapshot restore would either bring the
  rolled-back change back or discard the unrelated edit.
- **Reads never commit.** `ensure_repo_hygiene()` appends `.gitignore` rules on
  every `git()` call; only `init_repo()` commits the top-up, and it is reached
  solely from write paths.
- **A rollback says what it ACHIEVED, per device, never only that it ran**
  (C112, 2026-09-27). A rollback that raised was drawn "rolled back", a
  device with no pre-change snapshot was recorded nowhere, and a sent undo
  was never read back. Now each device's rollback is `restored` (read back
  over a fresh connection: the undo computed again against what landed now
  is empty), `nothing_to_undo`, `incomplete`, `sent_unverified`, `failed`
  or `not_attempted`; the receipt and the screen carry it, and
  `final_status` is `rollback_failed` unless every device is back. It is
  the most dangerous moment to draw a wrong thing as a working one.
- **Rollback fires whenever a push was attempted**, and targets every device
  not explicitly skipped — including one whose push failed mid-stream, which is
  the state most in need of restoring.
- **A failed push reports what landed** over a **fresh** connection, never the
  pooled one — that path runs only after something went wrong on the pooled
  session, so it is the most likely to be handed a broken instrument. A failed
  capture drops the pooled connection too. The read timeout is
  `nsot_config_read_timeout` (default 120s): `write memory` leaves an emulated
  device slow for tens of seconds, measured at 5.5s idle and >16s straight
  after a save, and Netmiko's 10s default sits inside that window.
- **A failed push reports what landed.** `_capture_failure_state()` reads each
  attempted device back and diffs against the pre-change snapshot before any
  rollback. "The push failed" and "the device is unchanged" are different
  claims; a device that cannot be read reports `device_changed: None`.
- **Every neighbour loss and every route shrink waits out a settle window,
  and fails only if it persists** (C114, C115, the operator's decisions,
  2026-09-27). The neighbour tolerance is 0 (it was 1, and `drop <= 1` let a
  device lose its ONLY neighbour and pass without waiting), and the route
  check runs on deploys and restores (it was skipped while the result drew
  "routes 22 -> 22" as compared), re-read in a 90 s `routes` window.
- **BGP is read once more no earlier than its hold time after the push** (C178, built
  2026-09-29): IOS keeps a broken session Established until the hold timer expires, so
  a read before then cannot show the break. The hold time is the CONFIGURED one, an
  upper bound on the negotiated one (conservative), and a BGP device's deploy takes up
  to 180 s longer for it. The negotiated per-peer value waits on a real `show bgp all
  neighbors` capture.
- **Verification uses settle windows** (OSPF 45s, BGP 60s, RIP 90s) and reports
  *not yet converged* distinctly from *failed*. **Until 2026-09-27 the
  routing check was real on 4 of 9 devices, measured against real output,
  and it is fixed.** It had read only the first protocol found (C62), a BGP
  count that matched no real row (C64), and the empty `"application"` table
  in place of RIP's (C65). So r3, r4, s1 and s2 compared 0 with 0, and the
  sentence here, "RIP is checked via the Routing Information Sources
  table", was false. Every protocol is compared now, BGP counts
  established sessions, RIP reads its own section, the route count is
  networks plus subnets (C66), the canary needs a non-loopback interface
  (C67), and progress means the count ROSE (C68). Acceptance from real
  captures: `tests/test_pipeline_reads_real_output.py`.
- **Stage 8.5 saves golden** after verify, on partial success, from the
  post-deploy config stage 7 now captures.
- **Batch**: sequential by default, circuit breaker on repeated *verify*
  failures, drift skips rather than aborts, every device accounted for.
- **Each path's baseline is keyed on the claim its tag makes.** A *deploy*
  baseline says "this commit's goldens are the network" — the goldens are the
  post-deploy captures, so it is true by construction for devices that
  succeeded, and only coverage remains (all targeted devices succeeded, whole
  inventory targeted). A *restore* baseline says "the network is back to the
  ref's state", which is a content claim and is measured per device with
  `roundtrip.configs_equivalent()` — section-aware, over `strip_for_diff`, so
  bare `!` and ordering cannot decide it.
- **A batch is an event: one golden commit, one baseline.** Stage 8.5 hands its
  capture back (`defer_golden`) instead of committing, so `save_golden`'s "one
  call is one commit" is preserved rather than special-cased. The subject and
  `Devices:` name the successful subset, `Failed-Devices:` the rest.
  `save_golden` no longer needs `len(changed) > 1` to tag — a baseline marks a
  moment, not a device count — but **coverage still governs**, so a batch
  targeting one device out of nine is denied the tag with the other eight
  named. A batch where every device fails commits nothing and tags nothing. Captures are staged to
  `.nsot/staging/post_deploy/` as each device completes, so a crash between
  8.5 and the commit is recoverable without re-reading devices that may have
  changed since.

#### Settings

All settings live in `data/user_settings.json` with a `settings_schema_version`.
`modules/settings_schema.py` seeds defaults and migrates forward; old keys are
never deleted. **Every new default reproduces the behaviour that predates the
setting** — `netbox_allow_writes` is the one deliberate exception.

**A version bump seeds only the keys it declares.** `SEEDS_BY_VERSION` is a
whitelist and the default is *nothing*: a key added to `DEFAULTS` between
releases is read through its default and **left absent from the file** until
some version deliberately claims it. A denylist ("a bump must not seed a
`require_*` key") would protect the keys somebody thought of and leave the
next security-relevant setting unprotected. Measured before the change: a
bump to v2 seeded **98 keys on a v1 install, including all eight identity
gates**, silently rewriting every "defaulted" as "set explicitly" everywhere.
v1 is recorded as `"*"` rather than rewritten — changing what a released
migration did is a lie about history.

**`migrate()` never writes a value nobody chose.** Absence is information:
`origin: default` means nobody has considered this setting, and writing it
destroys that irrecoverably. A default is also a live link to the project's
judgement — an explicit value wins for ever, so a seeded install silently
stops receiving a considered change to a default.

**Recording a decision is `ratify()`, and it can only ratify.** It writes
`get_setting(key)` — the value already in force — so the act cannot alter
behaviour, which is what lets the read-only posture panel offer it: a
compromised session cannot lower a gate through a control that can only write
the value already applying. It requires an actor, because a ratification with
nobody behind it is a seeded default wearing a better name. Three states
result: **defaulted** (nobody decided), **ratified** (written, equals the
default), **chosen** (written, differs).

**`write_settings()` is the one path into `user_settings.json`, and a key the
schema does not declare is refused rather than stored.** A validation failure
writes nothing at all — a half-applied settings write is worse than a
rejected one. Eight keys the Settings form had always written
(`ai_enabled`, `background_agent_enabled`, six `wf_*`) were undeclared and are
now in the schema; every default reproduces the value the code fell back to
before.

**Secrets are in more than one store** — see [docs/SECRETS.md](docs/SECRETS.md),
whose table is the claim. `user_settings.json` holds the ones
`secrets_store.SECRET_KEYS` covers (**a second store needs a second
mechanism**: a name in that tuple encrypts only what is in that file);
`.env` holds `ANTHROPIC_API_KEY` in **plaintext by design**, since
encrypting it would have the app decrypt its own key at startup using a key
in the same directory with the same mode. `data/jenkins_checks.json` is a
**retired** store (P.4): nothing reads it, and `nmas-check-secret-storage`
names it as a finding until it is deleted. The checker reports every store
by name and never by value. `scripts/nmas-settings-diff` lists
what in the file **differs from its default** — the only surviving signal for "what somebody chose" once a re-seed has written every key, since
`origin_of()` then answers `file` for all of them. Names only; a secret reads
`set`, and re-entering one means going back to the system that issued it.

**Modes are set at CREATION, at `0600`/`0700`, by `config.open_secure()` and
`config.secure_dir()`.** Nothing in the program set a mode before 2026-09-23:
`os.makedirs()` and `open()` take the process umask, so on the deployment host
`data/` was `0755` and every file in it `0644` — world-readable, including
`key.key` and an `.env` holding the Anthropic API key, for three weeks.
Fixing modes by hand fixes one install; the creation site fixes every install.
`open_secure()` applies the mode **before** writing (`os.open(..., 0o600)`),
because creating `0644` and chmod-ing after leaves a window with the secret on
disk and world-readable.

**`data/key.key` is the floor.** Everything "encrypted" is encrypted with it,
so its mode and the encryption are one control, not two — a group-readable key
means the ciphertext beside it was never protected. It has **two producers**
(`device.load_key`, `secrets_store._get_fernet`), deliberately separate, so
both create it owner-only and `device.load_key` also tightens an existing one.
The checker tests it first and separately.

**Every read-modify-write of `user_settings.json` holds `config.settings_lock()`,
and every write uses its own temp file** (C20, 2026-09-25). Measured before
the fix: two threads each writing 150 keys left the file **unreadable** in 2 of
2 runs. Every writer used one temp name, so two documents landed in one inode,
and nothing serialised the read-modify-write. The unreadable-file guard then
refused every write: nothing was erased, and nothing could be saved. The lock
is an RLock in-process plus `flock` on `user_settings.json.lock` across
processes, because a CLI such as `nmas-retire` writes settings while the app
runs. After the fix: 300 of 300, threads and processes. An AST scan requires
the lock in any function that both loads and saves. **`write_settings()` is
not the only write path**: the general-settings POST in
`routes/settings_integrations.py` does its own read-modify-write. `migrate()`
RUNS on every GET of that panel, and WRITES only when the schema version is
behind or a secret is still plaintext. Both hold the lock now. The bypass is
recorded, not yet removed.
**Where it came from, and whether it fired.** The shared temp name arrived
in `4f8a0f1` (2026-09-23 18:26), the fix for that day's erasure. So it is
NOT the erasure's mechanism, which was truncate-in-place followed by a write
built on `{}`. It is a defect the fix introduced, and it was latent for two
days. On the live host on 2026-09-25 there were no `user_settings.json.corrupt-*`
copies and no stray temp files, so as far as anything durable shows, it never
fired there. A lost update leaves no trace, so that half cannot be ruled out.
The C7 frozen defaults come from the erasure's reseed, not from this.

**Encryption at rest here protects COPIES THAT TRAVEL, and nothing on the
live disk.** That is a property of the design, not a flaw in it. NMAS works
unattended: the drift schedule opens SSH sessions, redaction decrypts every
secret every 30 s to build its value table, the NetBox refresh resolves
credentials, and the freshness signal authenticates to Oxidized. So the key
has to be readable by the process with nobody present, and **whoever holds
the disk holds every secret**, whatever the store's format. What the
encryption buys is that a copy of `data/` without `key.key` (a backup, an
exported file, a leaked fragment) is worthless. The one design that keeps
the key off the disk supplies it when the service starts (a passphrase or a
TPM seal). **Declined 2026-09-25 with that reason**: it costs a person at
every reboot and buys nothing a deployment running unattended can use.

**A key copy and a copy of `data/` are one fix in two halves** (B5/B6).
Measured 2026-09-25: no vzdump job exists, so `key.key` was a single copy,
and so was everything it opens. Escrowing the key alone recovers nothing
after a disk loss, because the ciphertext dies with it. The key is escrowed
in the break-glass record (sealed by the passphrase, so the record still
does not DEPEND on the key), and **`nmas-breakglass verify --live` proves it
is the right key by decrypting the values actually stored on the host with
the ESCROWED key**. A copy of the wrong key looks exactly like a working one,
and a fingerprint match only says which file was copied. On the host, through
a sealed record: 45 of 45 opened, and a random key 0 of 45. `restore-key`
refuses to replace an existing file.

**Tightening a mode does not undo exposure.** Anything that read a secret
while it was readable still has it; rotation is what makes past exposure moot.

**`0600` is right for a file the APP owns, and wrong for a handoff.** A file
one service writes and another reads has to name the reader — measured the
hard way: `chmod 600` on Kea's password file, root-owned, stopped the Control
Agent (running as `_kea`) from reading its own password. `0640` owned by the
service user is the target there. `scripts/nmas-oxidized-cred` already has the
right shape and is the one place NMAS writes for another service: it
preserves the original's mode and owner rather than asserting its own.

**A trailing newline is part of the password.** Kea includes it; `$(...)`
strips it; the result is a 401 that reads as a wrong password and is a
one-byte difference. Anything writing a credential to a file another service
reads writes it with no trailing newline and says so at the write site.
`nmas-oxidized-cred` refuses a newline outright rather than stripping one —
silently stripping would store something other than what was supplied.

**Every schema key is surfaced or documented file-only with a reason**
([docs/SETTINGS.md](docs/SETTINGS.md)), and a test fails on a key that is
neither. **`pause_agent()` persists nothing** — it sets an in-memory Event, so
a pause is lost on restart while `background_agent_enabled` (the persistent
switch, which had no control until 3.2d) survives. Two controls that look like
one switch, and only the invisible one survives a restart.

Secrets (API tokens, passwords, access keys) are encrypted at rest with the
existing Fernet key via `modules/secrets_store.py`. They are never logged, never
committed, and masked in the UI as write-only fields with a set/unset badge. The
NetBox token was previously stored in plaintext and is upgraded in place on first
run.

#### Portability

Development is Windows 11; the deployment target is headless Ubuntu. See
[docs/DEPLOY_LINUX.md](docs/DEPLOY_LINUX.md).

| Setting | Env override | Default |
|---|---|---|
| Bind host | `NMAS_HOST` | `0.0.0.0` |
| Port | `NMAS_PORT` | `5000` |
| Auto-open browser | `NMAS_HEADLESS=1` disables | on |
| TFTP root | `NMAS_TFTP_ROOT` | `C:/TFTP-Root` on Windows, `/srv/tftp` elsewhere |

`config.py` no longer creates the TFTP root at import time. Call
`config.ensure_tftp_root()` at the point of use instead.

