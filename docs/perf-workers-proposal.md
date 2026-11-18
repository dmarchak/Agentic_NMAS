# Heal and AI workers, and shell-first pages

**Proposal — not built.** Nothing here is implemented. It is written for the operator's
decision (the request of 2026-11-18: "move heal and AI runs out of the web process (the cause,
C3923), plus shell-first render. Propose only; don't build."). Charter bucket: CORE (the
enterprise-scale rule and "No page load or badge poll waits on ..."). Register rows it answers:
C3923, C3914, C3166; it leans on C3922, C3912 and C3907.

It is an early, narrow slice of the target architecture the plans already name: NSOT_PLAN
9.S phase 3 and NSOT_STAGE10_PLAN's 10.W ("a web tier with no background work, and a worker
tier running device work from a queue"). Nothing here contradicts 10.W; section 2.9 says what
it leaves to it.

## 1. The problem, measured

### 1.1 What runs in the web process today

Mercury is one process, `flask-app.service`, on Werkzeug's development server
(`socketio.run(..., allow_unsafe_werkzeug=True)`, app.py) with Flask-SocketIO in
`async_mode="threading"`. Every page request, every background service and every job is a
thread under one interpreter lock. The services `_start_background_daemons` starts (app.py) and
the jobs that run beside requests:

| Work | Where it starts | Kind of cost |
|---|---|---|
| Heal detect pass, decide, act (each heal a job), batch, retry, confirm-closed, auto-diagnose | `heal/detect.py` `start` (thread, every 30 s and on a trigger), `heal/act.py` `run`, `heal/batch.py`, `heal/retry.py`, `heal/auto_diagnose.py` | SSH sessions (crypto, prompt reads), renders, store rewrites |
| AI troubleshooting, the fix-it read-ahead, approved plan runs, the SDN loop | `troubleshoot_job.start`, `ai/fixit_troubleshoot.py`, `routes/fixit_v2.py`, `sdn/loop.py` | streamed answers parsed as they arrive, device reads, prompt building, masking |
| Reader jobs (about 34 readers, one thread each) | `reader_job.start` | HTTP reads of Grafana, Loki, NetBox; parsing |
| Needs attention's background store | `attention_store.start` | a recompute per network, debounced 2 s while a heal announces |
| Drift checker, heartbeat, Prometheus keeper, warm-up, scheduled rotation | app.py | periodic |
| Every job started by `capture_job.start` | a `threading.Thread` per job (`modules/nsot/capture_job.py`) | whatever the job does |

Waiting on a socket releases the interpreter lock; Python work does not. A page's own build,
the heals' crypto and renders, the AI's stream parsing and the store recomputes all take turns
on one core's worth of Python.

### 1.2 The numbers already measured

| What | Alone | In the live process | Source |
|---|---|---|---|
| The AI's request and scope | 2.6 s, 2.7 s (cold, on the host) | 31.3 s, 24.4 s | C3923 (the final take, 2026-11-17 05:19 to 05:23 UTC) |
| The AI switch's press | 0.5 s | 11.6 s | C3923 |
| Approve's press | 0.1 s | 9.1 s | C3923 |
| The Self-healing press | 0.03 s (preview and strip, nothing open) | 6.6 s in the take; about 10 s reported | f123edeb; C3907 |
| The incident page's build | 0.24 s warm, 1.82 s cold (cProfile, own process) | median 4.17 s (43 requests, 2026-11-17 06:00 to 23:59 UTC) | b70788f9 |
| The incident page, whole request | | median 12.07 s (take G), 7.26 s after the speed pass (its AI section 3.21 s, outside the build 3.27 s) | e1f77fef; the morning report of 2026-11-18, Phase 2 |
| The incidents list | | median 6.47 s (take G), 3.79 s after (held rows 1.81 s, outside 1.33 s) | e1f77fef; cc90d9e0; the morning report |
| The Fixes page | builder 0.13 s warm, 0.40 s cold | median 2.42 s | e1f77fef; the morning report |
| One device render | 0.09 to 0.20 s with the bytecode cache | 1.92 s, 1.63 s of it compiling (cProfile); r2's plan render 7.3 s in the take | C3922 (built on branch, 2c5e82c1) |
| Masking in an incident page's build | 0.31 s after the cache | 1.56 s before (1,120 calls, 63,858 `re.escape`) | 16dc1ee8 (C3921, closed) |
| Needs attention's heal-only recompute | | 0.85 s, every 2 s while a heal runs (0.17 s of it the kept write, now at most every 30 s) | 8814c5b5 |
| Needs attention and its badge | | p50 2.1 s and 1.4 s, max 64 s and 60 s; the badge queued 1.6 s to 26 s at a heal's end | C3166 (2026-11-12, before its held store) |
| Self-healing On to all Fixed | | about 1 min 36 s to 1 min 47 s; about 39 s that no lap names before the apply | C3912 |

The pattern: the same work is 10 to 30 times slower in the live process than alone (C3923),
and an incident page that builds in 0.24 s in its own process takes 4.17 s in the live one
(b70788f9). The morning report's reading is contention for the one interpreter, not the build.

### 1.3 What is not measured

- **What holds the interpreter while a heal and an AI run go.** UNKNOWN (C3923's own bucket).
  The one measurement: a py-spy record of the flask-app process during one Self-healing On and
  one AI run (`py-spy record --pid <MainPID> --duration 120 --rate 50`, the command in
  C3923). It decides which work moves first (section 4) and whether the render cache (C3922)
  alone recovers most of it.
- **The host's cores and the app's memory.** UNKNOWN here. The one measurement: `nproc` and
  `ps -o rss= -p <MainPID>` on `<nmas-host>`, idle and during a heal. Workers help only if a
  second core is free; their cost is a second resident image.
- **Needs attention, device page and Logs tab since C3166's held store.** UNKNOWN: Server-
  Timing is on the incident, incidents and Fixes pages only (e1f77fef). The one measurement:
  the request log's medians for those routes over a day with heals.

## 2. Proposal A: heal and AI runs in worker processes

### 2.1 The shape

Two worker processes from one template unit, `nmas-worker@.service`, its two instances named
heal and ai (rendered by `scripts/nmas-render-units`, as every unit is), each
importing the same checkout and running the same code a job runs today. The web process keeps
pages, routes, Socket.IO, the reader jobs and Needs attention's store. A press still answers at
once (C3866's rule); only where its job's thread lives moves.

- **The heal worker** runs the detect pass's loop, the decision, every heal act and batch, the
  retry and confirm-closed threads, and approved plan runs.
- **The AI worker** runs AI troubleshooting investigations, the fix-it read-ahead, auto-
  diagnose's AI step and the SDN loop.

One unit per kind, not one worker for both: the take's heal batch contended with itself (four
restores and two scripts in one interpreter spent most of 60 to 65 s compiling, C3922), and an
AI stream beside a heal batch would contend the same way. The instance name is the only
difference; one code path. Industry practice is the same split: NetBox runs its background jobs
in `rqworker` processes, Nautobot in Celery workers, AWX in its dispatcher, each apart from the
web workers.

### 2.2 How a press hands work over

Today `capture_job.start(list, label, actor, work, ...)` takes a closure and runs it on a
thread. A closure cannot cross a process. The handover becomes a **job record**:

1. The route builds what it builds today, then calls the same `capture_job.start` with a
   **named entry point** and its arguments (for example `heal.act.run_decision(network,
   decision_id)`, `troubleshoot_job.investigate(network, incident_id, trigger)`) in place of a
   closure. The record holds the kind, the entry point's name from a declared table, its
   arguments (JSON), the carried identity (actor, actor kind, how it was verified), the device,
   card and page fields `capture_job` already keeps, and the state `running`.
2. The record is written as a file under the data folder (`filestore.write_atomic` under a
   `PathLock`, owner-only by `config.open_secure`), so `capture_job`'s registry becomes the one
   registry both processes read. This is the audit's own fix for R10 ("shared job store").
3. The web process wakes the worker over the relay socket (2.3); the worker also reads the job
   folder at its start, so a wake lost while it restarted costs nothing but the wait for it.
4. The worker runs the entry point on its own thread at once, as `run()` does today. **The
   record is a handover, never a wait line**: a job is started the moment it is written, and a
   worker that cannot start it refuses it in its record, named. The device rule stays "one
   operation per device, refused by name, never queued".

Why files and not a database row: the records database is off until its host is set
(`records_db.py`), and the expand-then-contract rule makes a store move a two-release step.
The record's shape moves to the records database with 10.W. Why not Redis: it is a new
service, not in the lock, and its licence is the operator's (item 3 of the four stops).

The carried identity is a trust boundary: today `identity.carried` hands the verified identity
to a thread; across processes the worker trusts the record because only the service user can
write the data folder. `Actor-Verified:` must still say how the person was verified, so the
record carries the verification, never a fresh claim. This is the part the independent review
reads hardest.

### 2.3 How progress reaches pages

`invalidation.announce` needs the app's socket emitter and raises "no emitter" in any other
process. The proposal adds a **relay**: a Unix domain socket in the data folder (mode 0600,
owned by the service user), with a listener thread in the web process.

- In a worker, the emitter `invalidation.set_emitter` receives is the relay's client: the
  worker's `announce(keys, by, ok)` forwards the call, and the web process runs the real
  `announce`. So the generation moves (the held incident page and incidents list rebuild,
  b70788f9, cc90d9e0), Needs attention's store is marked (`attention_store.mark`), the reader
  wakes run (`reader_wakes.wake`) and Socket.IO emits, all in their one home. The message is
  key names only, as `announce` already requires: no data crosses the relay.
- The worker's per-job live state goes in its job record, not process memory:
  `op_progress`'s steps, `troubleshoot_job`'s `_steps` and `_shown` (the incident's live step;
  `routes/incident_v2.py` `step` already says "another process runs it draws the part empty").
  The In progress chip reads the records.
- The heal trigger's `detect.wake()` (`heal/triggers.py`, called in the web process where the
  listeners are) is sent over the same relay the other way, so a sighted trigger still starts a
  pass at once rather than at the next 30 s pass.

The permission on the socket is the gate: no HTTP route is added, so no route sits outside
`route_gates.py` and nothing relaxes "no localhost exemption". The existing precedent for a
process telling the app something is `nmas-job-finished` posting `/jobs/finished`; the relay
does not reuse that route because it would make an ungated loopback route a writer of every
announcement.

### 2.4 The cross-process guarantees: which hold

Hold unchanged (each already a `flock` or `PathLock`, built for host CLIs beside the app):

- device holds (`device_ops`, one `flock` per device; a dead holder's file is a leftover);
- the list repository's `RepoLock` (`filestore.PathLock`, R1 fixed 2026-10-02);
- SSH session slots across processes (R11, fixed 2026-10-04);
- the heal lock per network (`incidents.HealLock`), the incidents store's `PathLock`, the
  decisions rate lock, the policy store's lock;
- the heal mark (`heal/interrupted.py`: a `flock` per decision held while the act's process
  lives), so a worker that dies mid-heal is found and reaped as a restart is today;
- the AI calls record's index lock (`ai/calls.py`), so spend and caps stay one count.

Break, and must move with the work (R10 and R37's rows):

- `capture_job._jobs`, `op_progress._ops`, `troubleshoot_job._steps` and `_shown`: to the job
  record (2.2, 2.3);
- the redaction cache: a credential written in the web process leaves a worker's value table
  stale for up to 30 s (positional masking still applies; CONCURRENCY_AUDIT 3.9). A credential
  write announces, and the relay delivers it to workers too, so each drops its table at once;
- the AI session pool and the in-process SSH session list (C3974): per worker, which is where
  the AI's device reads then live; the slots above still bound the vty lines.

### 2.5 Stop, Off and caps

Stop everywhere and Off are fields in the policy store, read by `act.stopped_now` at each poll
through `policy.current`: already cross-process, unchanged. The troubleshoot watchdog's
`capture_job.stop` becomes a field in the job record ("stop asked, why") that the worker reads
between steps; the record's state is set failed at once, as today. AI Off and the caps are read
by the gateway at admit from the settings and calls stores, unchanged (C3924's gap between admit
and the caps is its own row and moves with the AI worker unchanged).

### 2.6 Deploys and restarts

- One checkout, one commit: `nmas-deploy` and the Update button restart the web process and
  both workers together, and `/health` reports each worker's commit and last heartbeat, so the
  smoke check refuses a release where a worker runs another commit. A worker never runs code
  from a checkout mid-pull (the hazard behind "no deploy under an evaluation").
- Draining: on stop a worker takes no new job, waits for its running jobs up to
  `TimeoutStopSec` (about 2.5 times the longest measured job: the heal batch's 1 min 47 s gives
  about 4.5 minutes), then exits; a job still running is reaped as interrupted by the existing
  heal mark. The deploy's refusal while a device is held (R5) is unchanged.
- The new units, the render and the `nmas-deploy` change (it has a root-owned copy) are host
  steps, each with its `Host-Step:` trailer.

### 2.7 Failure modes

- **A worker down.** Each worker writes a heartbeat to its record folder every 10 s. A press
  whose worker has not beaten for 30 s is refused at once, naming the worker and its last beat
  ("the heal worker has not answered since 05:19:02 UTC; nothing was started"), never queued.
  Needs attention gains one row per silent worker, its action "Restart the worker"
  (an admin control on the row, a Mercury operation, not a terminal step), clearing when
  the heartbeat returns.
- **The relay down.** `announce` in the worker raises, as it does today without an emitter;
  `capture_job._announce` already records `announced: false` and the page's "Check now" still
  reads the record. The heartbeat row names it.
- **A job record unreadable.** It is refused, as an unreadable store refuses writes today.

### 2.8 The host's cost

No new work: the same work on another core. Added: two resident Python images (UNKNOWN until
measured, section 1.3) and one listener thread. If `<nmas-host>` has one free core, the two
workers share it with each other and the web process gains most; if it has none, workers buy
nothing and the py-spy record should be read before building.

### 2.9 Tests and the harness

- One code path: the worker loop is a function; tests run it on a thread in the test process
  over a temporary data folder and a real Unix socket (the loopback confinement allows it), so
  every test of a heal or an AI run still drives the real handover. A test with a real child
  worker (the `test_repo_lock_across_processes` pattern) proves the cross-process half; it is
  not unit-tier coverage, so the loop's own unit tests keep the coverage ratchet.
- Churn: tests that hand `capture_job.start` a closure for a moved kind, the heal tests' starter
  fakes (`batch.py`'s `starter`), `test_in_flight`, `test_announce`, `test_live_contract`,
  `test_attention_rows_act` (the new row), `test_operation_stages` (no stage changes),
  CONCURRENCY_AUDIT's R10 row, docs/ARCHITECTURE.md and docs/DEPLOY_LINUX.md. Churn is a stated
  cost, never a veto.
- The independent review: the runner and plan execution write to devices, so the review the
  fast lane keeps applies before any deploy.
- Left to 10.W: gunicorn and nginx, several web workers, Socket.IO across web workers, the
  reader jobs and Needs attention's store in the worker tier, the records database.

### 2.10 Reused and New

Reused: `capture_job` (its record fields, start, stop, announce and purge rules); `invalidation`
(`announce`, `set_emitter`, `generation`, `_changed`); `filestore` (`PathLock`, `write_atomic`);
`config.open_secure`; `identity.carried` and `ai_carried`; `device_ops` holds; `RepoLock`;
`heal.interrupted` (mark and reap); `act.stopped_now`; `op_progress`'s step shapes;
`scripts/nmas-render-units`; `/health` and nmas-deploy's smoke check; job health's reader
pattern for the heartbeat row.
New: the declared entry-point table (closures cannot cross processes); the relay socket and its
listener (no cross-process announce exists); the worker loop and its unit (nothing runs Mercury
work outside the web process but host CLIs); the heartbeat and its row.

## 3. Proposal B: shell-first render

### 3.1 The targets

The operator's: the server's shell in 300 ms or less, first content in 1 s or less, each panel
in 1.5 s or less.

### 3.2 What exists

- The pattern is already in base.html: the In progress chip, the Update slot, the strip, the
  heal-auto chip and the AI chip each draw as an empty slot with
  `hx-get ... hx-trigger="load, nmas:<key> from:body"` and fill by their own request. The
  incident page's proposal and Re-subscribe cards load on open (`hx-trigger="toggle once"`).
- Held values: Needs attention's background store (C3166), the held incidents list and its
  single flight (cc90d9e0), the held incident page and its single flight (b70788f9), the
  reader stores. A panel that reads one of them computes nothing.
- The rules a panel already meets: "Couldn't load: <why>" in place
  (`test_v2_swaps_never_silent`), each source's age drawn, live re-fetch on its own keys, strict
  CSP.

### 3.3 The change

Each heavy page's route returns its shell (base.html, headings, the BLUF line where it is held,
an empty slot per panel saying what it is reading); each panel is its own GET reading its held
value, re-fetched on its own announce keys instead of the whole page's `hx-select` re-GET.

| Page | Today | Panels |
|---|---|---|
| Incident | one build; the live region re-GETs the whole page on `drift`, `privileged`, `in_progress` (incident.html) | the card and status (held); the AI troubleshooting section (3.21 s median now); the Needs attention item (1.63 s in take G); heal card and diagnosis; heal analysis |
| Incidents list | held rows 1.81 s, control strip, render | the outcome line and tiles; each tab's rows; the control strip |
| Fixes | the listing, render | the listing alone |
| Needs attention, device page, Logs tab | held store; the Logs tab's buffer (C3166's slices) | per section, once their Server-Timing is in |

Costs: more requests per page view (each pays identity, CSP and the after-request hooks: the
shell's own Server-Timing says how much); finer invalidation keys per panel; board fidelity
compared again for each changed template (`test_board_fidelity`); tests that read a page's
content read its panels.

What B does not do: under contention the shell's 300 ms is as hostage to the interpreter as
the page was. B moves the wait off the first paint; A takes away what the wait is.

## 4. Order and sizing

0. **Measure first** (small): deploy the branch's Server-Timing, held page, single flight and
   the render cache (C3922), then take C3923's py-spy record during one Self-healing On and one
   AI run, with `nproc` and the RSS figures. It may show renders or one hot path dominating,
   which would reorder what follows.
1. **A's machinery with the heal worker** (large): the job record, the entry-point table, the
   relay, the unit, the heartbeat row, the deploy's drain. Heal first by default: its detect
   loop runs continuously and its batch contends with itself; the py-spy record may put the
   AI first instead.
2. **The AI worker** (medium): the second instance on the machinery of step 1.
3. **B on the incident page** (medium), then the incidents list (small), then the Fixes page
   (small), then the C3166 pages once measured.

Risks: the identity carried in a record (2.2); version skew between processes, closed by always
restarting together; a lost wake (closed by the worker reading its folder at start); memory on
the host; test churn.

Before and after, by Server-Timing section (e1f77fef's names): `total`, `render`, `resolve`,
`timeline and state`, `AI troubleshooting section`, `heal running and status`, `Needs attention
item`, `heal card and diagnosis`, `heal analysis`, `held page` (incident); `groups and model`,
`held rows`, `control strip` (incidents list); `fixes listing` (Fixes). Beside them, from the
log: the presses' lines (f123edeb, 5a808325), C3912's laps (press to Fixed, AI On to plan,
Approve to Fixed) and C3923's ratios, alone against live.

## 5. Open questions for the operator

1. Two worker units (heal, AI) or one worker for both to start?
2. The job record as files now, moving to the records database with 10.W: agreed, or the
   records database first (it is off until its host is set)?
3. The relay as a Unix socket with file permission as its gate: agreed, or should it carry a
   token as well?
4. Restart all processes together on every deploy (no skew, a drain wait), or allow a web-only
   restart while a worker drains?
5. The worker-down row's action: a Restart control on Needs attention (an admin operation), or
   only the row naming it?
6. Should Needs attention's background store and the reader jobs follow into a worker in this
   step, or stay for 10.W?
7. B's panels per page: build on the incident page first, or wait for the py-spy record and
   A's first step?
8. Is the C3922 render cache's deploy, before this, the operator's morning test as planned?
