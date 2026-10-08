# Show commands: Ask the device and fleet-wide show commands (C547, C548; APPROVED 2026-10-08)

The operator, 2026-10-08: "no more command line or terminals". A person reads a device through
Mercury, never a console: one device on its page (C547, the "Ask the device" tab, signed off
as a name only), many devices on one screen (C548, replacing today's Bulk Operation). Both use
ONE engine, which is also the Stage 8 agent's evidence engine (NSOT_PLAN 8.16: "one engine, two
users"). Nothing here changes a device. Built after this design and its boards are signed off.

## 1. What exists today (surveyed 2026-10-08)

- **The allowlist** (`modules/readonly_commands.py`, `refusal()`): a command passes only when
  every part does: the verb (`show`, `ping`, `traceroute`, `dir`, `more`), the first `|`
  modifier (`begin`, `count`, `exclude`, `include`, `section`, and their unambiguous
  abbreviations), any later `|` read as regex alternation; refused: `redirect`, `tee`,
  `append`, `format`, a URL, a line break, a control character, `?`, `ping` with no target.
  Its tests pin the C61 exfiltration case and one list only.
- **`/run_command/<ip>`** (today's device page): runs ANY exec command. The allowlist decides
  only whether the device is held; nothing is refused. The output lives in the browser's
  session; nothing is recorded (`operation_stages`: NO_RECORD).
- **Bulk Operation** (`/bulk_execute`, `modules/bulk_ops.py`): config mode refused, its own
  pool of 5, prompts auto-answered for `reload` and `write erase`, in memory only, NO_RECORD.
- **The AI assistant's read tools** (`modules/ai_assistant.py`): refuse by the allowlist, their
  own pool of 5, the answer to the chat only, no record.
- **The v2 tab** "Ask the device" is declared and drawn disabled (`routes/device_v2.py` TABS,
  not BUILT).

So three paths read devices, none records a read, and one of them refuses nothing.

## 2. The engine (one, for a person and the agent)

`modules/nsot/reads.py`, one function: `run(list, devices, commands, actor, purpose)`.

- **Refuse first, whole command, by the allowlist:** each command through `refusal()`; a refused
  command is named with its rule ("`show run | redirect …`: redirect WRITES") and nothing runs.
  Every command must pass before any device is asked.
- **Hold the device while reading** (8.16: "the same device holds while reading"), through
  `device_ops`: a device another operation holds is refused BY NAME ("r2 is being deployed to
  by <person>"), never queued, and the others are read. A long read never blocks a deploy
  silently: the deploy's refusal names the read and its person.
- **Read through the one sender** (`commands.run_device_command` on `connection.open_ssh`'s
  sessions), bounded per command by `config_read.read_timeout()`; a read that times out is that
  device's failure, named, never a partial answer drawn as whole.
- **Across devices concurrently**, `fanout.read_each` (cap 16), each device's failure its own.
  More than one device is a JOB (enterprise scale: no per-device work per request), announcing
  its progress (`reads`) and its end.
- **Masked on the way out AND at rest** (`redact.redact_text`): the answer stored and drawn is
  the masked one. `show running-config` reads like the golden on the Intent tab.
- **Recorded, every run:** who (`identity.request_actor()`; the agent as "the agent, for
  <person>"), when, the network, the devices, each command, each device's outcome (answered,
  refused and why, failed and why, busy and who) and the masked answer with its SHA-256. A
  per-network append-only record, locked and replaced atomically, read by History as a new
  kind, "Show commands", filterable by device and person. Kept 30 days, then the answers move to MinIO
  and the who-when-what kept (decision R2).
- **The agent** (Stage 8) calls `run()` with its purpose; it opens no session of its own, and
  its reads are a person's reads in History.

Today's three paths move onto it at cutover: `/run_command` and Bulk Operation retire (their
v2 screens replace them), and the AI tools call `run()`.

## 3. Ask the device (C547, one device, its page's tab)

- **The command box,** checked as typed (the intent editor's pattern): a refused command says
  why beside the box and Run stays disabled; a passing one shows "read-only" on hover.
- **Pick instead of type:** the network's saved command sets (section 5), this platform's
  common reads (a short built-in list per platform: interfaces, routing, neighbours, VRRP, MAC
  table, NTP, logging, archive differences), and this device's recent reads.
- **Run** is busy on itself until the answer arrives (never a timer); the answer is drawn in
  place under the command, in a scrolling `pre` that never leaves its card, with how long it
  took and when, the person on hover. A failure says which and why; a device held says by whom.
- **Again later:** the device's recent reads (this person's and others'), collapsed, each
  re-openable; "compare with the last answer" shows the lines that changed (the same command
  read twice: did the counters move, did the route appear).
- **Never** a write: there is no config mode, no free-form session, and nothing the allowlist
  refuses is sent.

## 4. Fleet-wide reads (C548, many devices, its own screen)

Where: OBSERVE in the sidebar, a new item "Show commands" (decision R4), replacing today's Bulk Operation.

- **Pick devices** by name (search), role, platform, site or network, with the count shown
  ("31 devices"); a device in no reachable state is named before the run.
- **Pick commands:** one or more, each checked as typed; or a saved command set.
- **Run** starts a job; the screen shows its progress (devices answered of the total) and can be
  left and come back to.
- **The result leads with a summary** (the large-fleet rule): per command, how many answered,
  failed, refused or were busy, and how many DISTINCT answers there were ("show ntp status: 27
  synchronised alike, 3 differ, 1 failed").
- **Grouped and collapsed:** devices whose answers are the same (after removing what always
  differs: timestamps, uptimes, counters the platform names; one normaliser per platform,
  measured) form one group, its answer shown once; a group opens to its devices; a device opens
  to its own answer. Never one long expanded list (900 devices).
- **Compare:** two devices side by side (the lines each lacks marked), or "only the differences"
  against a group the person chooses (by default the largest): each device's lines that its
  group's answer lacks, and the reverse.
- **Filter and search** inside the result (a device, a string in the answers).
- **Saved command sets** (section 5): "Run again" on a past run; "Save as a set" from the
  commands picked.

## 5. Saved command sets

A set is a name, a description and its commands, per network, committed in the network's
repository (`command_sets/<name>.yml`, through `repo.commit()` as the person, so a set has a
history and a reviewer), each command checked by the allowlist when saved and again when run.
Both screens offer them. (Decision R3: committed, against a setting.)

## 6. The allowlist review (what an engineer needs)

Every `show` with the safe filters already passes, so `show running-config | include` and
`| section`, `show ip route <prefix>`, `show archive config differences`, `show vrrp brief`,
`show mac address-table`, `show interfaces`, `show ntp associations` and `show logging` are
allowed today; nothing needs adding to read them. The review is the other way, what inside
`show` must be bounded or refused (decision R1):

- **Heavy reads:** `show tech-support` (minutes, megabytes, CPU on a small device). Proposed:
  refused on the fleet screen, allowed on one device with its bound named.
- **Unbounded output:** every answer is capped (bytes per device, measured), and a capped
  answer says it was cut, never drawn as whole.
- **`more <file>`** reads any file on flash or nvram, `nvram:startup-config` included: allowed,
  masked like every answer.
- **`ping` and `traceroute`** send traffic: allowed, a target required (as today), a repeat
  count bounded.

Each is shown read-only the way the allowlist is today: its test names the command and the rule,
and the first run of each new kind on r2 and s1 (through the engine, never a console) records
that the device's configuration did not change (the drift check's next read, clean).

## 7. Never let a wrong thing look like a working thing

- A capped answer reads "cut at N kB", never as the whole.
- A device that did not answer is never in a group of answers; "27 alike" counts only devices
  that answered.
- A normaliser that hides a difference is the danger: what it removes is listed on the screen
  ("ignored: uptime, last input"), per platform, and "show the raw answers" turns it off.
- A refused command never runs on some devices and not others: all pass, or none runs.

## 8. Decisions (the operator, 2026-10-08: the design and boards A to E APPROVED)

- **First, before the build (C570, bucket A, done the same day):** the device page's command
  route and Bulk Operation refuse anything the allowlist refuses, before any device is
  contacted, and the file routes take each spliced field as one token.
- **R1, the allowlist review:** `show tech-support` refused fleet-wide, allowed on one device;
  each answer capped at a MEASURED size. Added by the operator: a CONCURRENCY LIMIT for fleet
  reads (fewer than `fanout`'s 16 at once, measured against the lab's slowest device), and a
  HEAVY COMMAND warning before a run (s3 is CPU-starved): a command the engine knows to be
  heavy, or a device it knows to be weak, is named at the confirm.
- **R2, retention:** answers kept 30 days, then MOVED to MinIO (the charter's queryable archive
  past retention, `modules/nsot/archive.py`), never deleted, on a retention SETTING; who, when
  and what kept for good.
- **R3, saved sets:** committed in the network's repository (history, reviewable), not a setting.
- **R4, the fleet screen:** under OBSERVE, named **"Show commands"** (what engineers call it),
  not "Reads"; the History kind follows it.
- **R5, order:** the engine, then Ask the device (its tab), then Show commands, then the
  agent's tools onto the engine; `/run_command` and Bulk Operation retire at cutover.

## 10. As built (2026-10-08, overnight), and where it differs from the boards

Built in four commits (the engine 2999207; Ask the device 7d0eb12; Show commands 2bb5d83; the
agent's tools b4df3d8), on the boards as signed off, with these differences. **The operator
ACCEPTED all three differences (2026-10-08 morning)** and corrected two premises, below.

- **The run carries the filters and a fingerprint, not the device names.** Board B lists the
  matched devices; the form carries the filters and a fingerprint of that list, and the run
  computes the match again and is refused, naming both, when it moved. A form carrying 900 names
  broke the large-fleet rule.
- **Grouping is exact**: devices group when their whole masked answer is identical. Board C's
  "ignored when grouping" columns need a per-platform normaliser MEASURED first (which columns
  change on their own); until then the page says nothing is ignored, and no "raw answers" switch
  is drawn because there is nothing to switch off.
- **The heavy warning names commands only** (accepted for now). The premise was wrong: Mercury
  DOES have device CPU, through Prometheus (IOS-XE's telemetry subscription 101,
  cpu-utilization; SNMP for the switches). A "device under load" warning reading it is FUTURE
  (C575).
- **Answers past retention stay on the host.** The premise was wrong: MinIO EXISTS (the data
  lake: raw telemetry, `mdt/` 30 days, `syslog/` 2 years); what is missing is MERCURY'S
  connection to it (settings, credentials, an S3 client; the per-network S3 archive integration
  is not configured on the host and its SDK is not installed). The 30-day move is folded into
  Phase 4, which needs the same connection (NSOT_PHASE4_RECORDS_POSTGRES.md); `reads.expire` is
  its hook, and nothing calls it until then.
- **The agent's reads (the operator's decision):** every device read is a recorded engine run,
  the agent's included, and the agent reads a device's CONFIGURATION from GitHub's golden first,
  asking the device only for live state. The three `execute_command*` tools are on the engine
  (b4df3d8); `get_running_config` and the rule checks are C576.

## 11. The command policy: three tiers (the operator, 2026-10-08, replacing "show only")

The operator wants the enable-mode commands an engineer uses day to day, and everything that
changes or disrupts a device kept out of silent execution. Refusing configure mode alone is not
enough: `reload`, `write erase`, `erase startup-config`, `copy … running|startup`, `configure
replace`, `delete`, `format`, `clear ip bgp *`, `clear ip ospf process`, `debug`, `crypto key
zeroize` and `request`/`install` are all exec mode. So three tiers, decided by an ALLOWLIST of
verbs with validated arguments, never a denylist (exec is an open set): anything unrecognised is
refused, naming the nearest allowed alternative.

- **Tier 1, non-destructive** (runs as a read through the engine: refused first, held, masked,
  recorded, capped, bounded): `show` as today; `ping` and `traceroute` with a bounded repeat and
  timeout; `dir` and `more` on LOCAL file systems only (never a URL, never `tftp:`, `http:`,
  `scp:`); `verify /md5` of a local file; `send log [<level>] "<text>"` (one plain line, no line
  break, length-capped); the session-only terminal settings the engine needs. Each argument one
  token of its shape (the file-name rule, `cli_tokens`). BUILT next (section 12).
- **Tier 2, state-changing but recoverable** (`clear counters`, `clear arp`, `clear ip bgp
  <peer> soft`, `clear logging`, `undebug all`, …): a "Run a privileged command…" OPERATION:
  preview (what it affects), confirm, record. A DRAFT design and mockup for sign-off first.
- **Tier 3, destructive**: refused, each naming its own operation: `reload` → Reload or Revert by
  reload; `write erase`, `erase`, `delete`, `format`, `copy` into running or startup, `configure
  replace`, `crypto key zeroize`, `request`/`install`, `debug` (beyond `undebug`) → refused with
  the reason.
- **Configure mode** stays refused everywhere outside the deploy pipeline.
- **The refusal says which tier, and where to go instead**, never only "not a read".
- **"Test the logging path"**: an action sending a `send log` message to chosen devices, then
  watching Loki for each, reporting per device "received after N s" or "not received within
  30 s"; on Show commands' run model, drawn on the existing boards if it needs no new screen,
  else a mockup first.

## 9. Boards to draw (the mockup, for sign-off)

Ask the device: (1) empty, with the sets and common reads; (2) a command refused as typed; (3)
an answer in place, with the recent reads; (4) compare with the last answer; (5) the device held
by another operation. Fleet reads: (6) picking devices and commands; (7) running, with
progress; (8) the result's summary with groups collapsed; (9) a group open, a device open; (10)
two devices side by side; (11) only the differences; (12) saved sets. History: (13) a Reads row.
Each at phone width as well.
