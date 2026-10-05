# CLAUDE.md — Agentic Network Management and Automation (NMAS)

**SESSION START: at the start of a session or after a compaction, re-read CLAUDE.md and the
open queue (docs/OPEN_FINDINGS.md's Count and open sections, and the plan item in progress)
before acting.**

## Project

A Flask application that manages, automates and monitors Cisco IOS and IOS-XE devices, built by
[Author], being converted into a Network Source of Truth: intent and golden configs in git,
rendered through templates, previewed as an exact program, confirmed by hash, pushed merge-only,
verified, rolled back on failure, and recorded. Single host; identity comes from an access
proxy's verified assertion. **Stack:** Python 3.10+ (CI 3.12.3), Flask, Flask-SocketIO, Netmiko,
the Anthropic API, NetBox, Grafana/Prometheus/Loki, Oxidized, Kea. The v2 interface
(`templates/v2/`, vendored htmx and Alpine, strict CSP) replaces today's Bootstrap pages at
cutover. Jenkins was removed in P.4.

**Governing documents** (read the one for the area before starting work there):
[NSOT_PLAN](docs/NSOT_PLAN.md) (the spec, P-items, Stages 8 and 9) ·
[NSOT_STAGE7_PLAN](docs/NSOT_STAGE7_PLAN.md) (the interface; tasks in
[NSOT_TASKS](docs/NSOT_TASKS.md), design in [NSOT_GUI_BRIEF](docs/NSOT_GUI_BRIEF.md), retirement
in [CUTOVER](docs/CUTOVER.md)) · [NSOT_STAGE10_PLAN](docs/NSOT_STAGE10_PLAN.md) (the release; 6.0
is the lab-specifics rule) · [OPEN_FINDINGS](docs/OPEN_FINDINGS.md) (the register; its *Count*
is the one statement of what is open) · [CONCURRENCY_AUDIT](docs/CONCURRENCY_AUDIT.md) (P.15) ·
[NSOT_AUTHORIZATION](docs/NSOT_AUTHORIZATION.md) · [SECRETS](docs/SECRETS.md) ·
[SETTINGS](docs/SETTINGS.md) · [UPDATE](docs/UPDATE.md) · [DEPLOY_LINUX](docs/DEPLOY_LINUX.md) ·
[NSOT_WRITEUP](docs/NSOT_WRITEUP.md) and its notebook [NSOT_WRITEUP_NOTES](docs/NSOT_WRITEUP_NOTES.md)
· the manual, `docs/manual/` (served at `/v2/help/<page>`).
**[docs/LESSONS.md](docs/LESSONS.md) holds the incident behind each rule below**, in one section per
rule; each rule's [why] link opens it. **Read it when a rule's reason matters, and before changing
or removing a rule.**
**Moved out of this file:** [ARCHITECTURE](docs/ARCHITECTURE.md) (the full module map and every
decision's narrative), [TESTING](docs/TESTING.md) (what the suite checks; the per-file table).

## Standing rules

Each rule ends with where it is enforced; `[not mechanised]` means only this file holds it.

### Working method

- **Walk the path for real:** a path never run fails on first use, and the suite cannot say so.
  Every operation gets a real run on the host; watch what else moves. [not mechanised] [why](docs/LESSONS.md#walk-the-path-for-real)
- **Read-only measurement of lab services is the agent's to run**, through `scripts/nmas-host`,
  printing counts and names, never values. Writes, devices, Proxmox and the lab host are the
  operator's. [tests/test_nmas_host.py: no forwards, no ssh options]
- **Search the register first, record a finding the turn it is raised with its bucket (A, B,
  UNKNOWN, C; the criterion applied), and move a fixed row to Closed the same turn.**
  [buckets and placement: tests/test_register_hygiene.py; search-first: not mechanised] [why](docs/LESSONS.md#record-findings-in-the-register)
- **Sweep stopping rule:** a sweep registers all it finds and fixes only the A items it found;
  the rest waits however cheap. Bound a sweep by a property-defined survey. [not mechanised] [why](docs/LESSONS.md#the-sweep-stopping-rule)
- **Survey before fixing, and let the survey move the fix; constrain the shape of a class rather
  than enumerate its members.** [not mechanised] [why](docs/LESSONS.md#survey-first-and-constrain-the-shape)
- **A stated problem is a hypothesis.** Ask the cheapest question that halves the space first;
  run the command a document names before calling it wrong; a tool's output is a claim. [not mechanised] [why](docs/LESSONS.md#a-stated-problem-is-a-hypothesis)
- **Severity is a claim about the world, measured;** an unmeasured one is UNKNOWN, naming the one
  measurement. [not mechanised] [why](docs/LESSONS.md#severity-is-measured)
- **A document asserting a property the code lacks stops the next person looking.** Read the code
  before writing the sentence; every rule here names its check, and every citation names a
  file and section that exist. [this file's rules and citations everywhere:
  tests/test_claude_md.py; the sentences themselves: not mechanised] [why](docs/LESSONS.md#documents-that-assert-what-code-lacks)
- **A writeup entry is written the turn its stage or sub-task closes**, numbers and forecast
  checked; forecast only from a finished stage of the same kind; publish once, at the end. [not mechanised] [why](docs/LESSONS.md#writeup-entries-and-forecasts)
- **Sequence by dependency and by whether it works, never "before a demo". The frontend decides;
  the backend is rewired to serve it, and test churn is a stated cost, never a veto.** [not mechanised]

### Git, the gate and deploys

- **The gate:** `git add -A` → `scripts/nmas-stage-guard` → the suite in CI's interpreter and
  command (docs/TESTING.md, "CI's interpreter here") → commit; report each new file the guard lists.
  [hooks/pre-commit runs the guard; tests/test_stage_guard.py; the order: not mechanised] [why](docs/LESSONS.md#the-gate-and-the-stage-guard)
- **A gate's result is this run's:** remove the result file first, chain with `&&`, never pipe a
  command whose exit code counts, never write a count before the run that makes it. [not mechanised] [why](docs/LESSONS.md#gate-results-from-this-run)
- **Gate `git commit -F` on the message file's first line naming THIS commit**, in a `case` that
  can stop it; a failed write leaves the previous message. [not mechanised] [why](docs/LESSONS.md#the-commit-message-file)
- **Push every commit and name the pushed sha; never rewrite pushed history** (correct with a
  forward commit). [not mechanised]
- **Never stack a commit on a RED CI; never wait idle for a green one.** Push, name the sha and
  start the next task while CI runs; when a run fails, stop new work and fix forward before
  anything else. Nothing unverified reaches the host: `nmas-deploy --wait` and the Update button
  refuse a commit CI has not passed. [the host refusing it: tests/test_nmas_deploy.py,
  tests/test_update_when_ci_passes.py; the rest: not mechanised] [why](docs/LESSONS.md#no-commits-on-a-red-ci)
- **Deploys are the operator's** (`nmas-deploy --wait`). Never deploy, pull or write in the live
  checkout on the host. [nmas-deploy needs CI's pass: tests/test_nmas_deploy.py; the agent:
  hook scripts/hooks/claude-no-host-writes, tests/test_claude_host_writes_hook.py]
- **Prose goes through the Edit and Write tools, never a heredoc into an interpreter.**
  [hook: scripts/hooks/claude-no-heredoc-interpreter (.claude/settings.json); tests/test_claude_heredoc_hook.py] [why](docs/LESSONS.md#text-through-file-tools)
- **CLAUDE.md is the operator's: a change it needs is given to the operator as the exact
  lines to paste, and committed after they have pasted them.**
  [hook: scripts/hooks/claude-no-claude-md-edits (.claude/settings.json); tests/test_claude_md_edit_hook.py]
- **A diff must not remove a definition something still calls.**
  [scripts/check_removed_definitions.py in hooks/pre-commit and CI; tests/test_check_removed_definitions.py] [why](docs/LESSONS.md#removed-definitions-still-called)
- **A commit touching a host-installed file** (`deploy/update/`, `scripts/nmas-deploy`, `scripts/nmas-oxidized-cred`,
  `deploy/systemd/`, `deploy/topology/`) carries `Host-Step:`/`Host-Step-After:` or
  `Host-Step-None: <why>`; a step fills every value (no `<…>`), renders into a fresh `mktemp -d`
  folder, and installs files by name, never a glob.
  [scripts/nmas-host-step-check in hooks/commit-msg and CI; tests/test_host_step_check.py] [why](docs/LESSONS.md#host-steps-in-commits)
- **A commit records what it deliberately did not do** (`Not-Done:`, `Refused:`). [not mechanised] [why](docs/LESSONS.md#record-what-was-not-done)
- **Install the hooks:** `ln -sf ../../scripts/hooks/pre-commit .git/hooks/pre-commit`, and the
  same for `commit-msg`. [not mechanised: a clone's hooks are outside the repository; CI runs
  the same checks over every pushed range]
- **Commit through `scripts/nmas-gate`** (stage, stage guard, the suite in CI's interpreter with
  its result file cleared first, the verdict, the message's first line, commit, push): one
  program for the five rules above. [tests/test_nmas_gate.py]

### Publication (the repository is public, its history unrewritten)

- **Nothing personal or installation-specific is published.** Neutral voice (the operator, the
  tool; never "I" or "we"); placeholders `<operator>`, `<user>`, `<home>`, `<nmas-host>`,
  `<lab-host>`, `<hypervisor>`, `<tunnel-host>`, `<laptop>`, `<LAN>`, `<domain>`, `<repo>`,
  `<account>`, `[Author]`, `<redacted>`. Real values: `data/lab_hosts.json`,
  `data/publication_denylist.txt` (gitignored). New test addresses are 192.0.2.x; an excused line
  is one hash-keyed entry in `tests/publication_exemptions.py`.
  [tests/test_nothing_personal_is_published.py; scripts/nmas-stage-guard] [why](docs/LESSONS.md#nothing-personal-is-published)
- **The product is network-agnostic; nothing lab- or person-specific in it, from the moment it is
  written.** It is lab tooling (`lab/`), an optional integration off unless configured, or
  gitignored local configuration. A rule about how a device ARRIVED (containerlab, vrnetlab, ZTP)
  is never keyed on what it IS. [tests/test_lab_specifics.py, an exact inventory] [why](docs/LESSONS.md#nothing-lab-specific-in-the-product)
- **No personal-data connectors** (email, calendar, cloud files); ask the operator. [denied in
  .claude/settings.json; tests/test_claude_host_writes_hook.py] [why](docs/LESSONS.md#no-personal-data-connectors)
- **`deploy/systemd/` holds templates**, rendered by `scripts/nmas-render-units`. [tests/test_nmas_host.py]

### Product design and the interface

- **Needs attention: every row names something wrong AND an action, and says how it clears**
  (resolving, acknowledged, or time). A fact nobody acts on is its source's finding under What
  was checked, never a row. [tests/test_attention_rows_act.py; tests/test_acknowledge.py (`CLEARS`)]
- **The screen answers the person's question; the evidence is one level down.** A notice says
  what to do or does not appear; a stale or unreadable source is itself a row.
  [partly: tests/test_needs_attention.py] [why](docs/LESSONS.md#the-screen-answers-the-question)
- **No new screen or tab without a mockup and the operator's sign-off; a mockup draws every link
  and control the built screen will have.** [every v2 page and device tab named with its sign-off,
  the unsigned list only shrinking: tests/signed_off_screens.py, tests/test_signed_off_screens.py;
  that the mockup drew every control: not mechanised]
- **No new capability on a v1 page: today's interface only shrinks until cutover; a v1 control,
  handler or function count may fall and never rise.** [tests/test_no_new_v1_capability.py]
- **An element carrying `hx-select` disinherits it; a v2 action that cannot draw its answer says
  "Couldn't load: <why>" in place.** [tests/test_v2_swaps_never_silent.py]
- **Built for large fleets: a screen listing devices or results leads with a summary (counts by
  outcome), groups and collapses, offers filter and search, and never draws one long expanded
  list; per-device detail opens on expand.** [no long expanded list at test_scale's 900
  devices, the gaps named and only shrinking: tests/test_large_fleets.py; the summary, grouping
  and search: not mechanised]
- **The manual covers every screen and operation:** a page per sidebar item and device tab, a How
  it works page per operation naming each step its code declares, a diagram on each in the flow
  of the text, "How does this work?" beside every action, all clicked in a real browser. A v2
  screen is not done without them. [tests/test_manual.py; tests/test_v2_layout_in_a_browser.py]
- **A v2 control is busy on itself until the answer arrives (never a timer) and the result
  updates in place; no narration beside it, provenance on hover; no toast.**
  [no toast: tests/test_v2_pages.py; busy: tests/test_update_button.py (Update, About) only]
- **Every v2 page is under `csp.STRICT_POLICY`, draws the viewer through `identity.viewer()`, and
  colours by tokens with dark values; libraries are vendored, never a CDN.** [per-page tests, e.g.
  tests/test_device_v2.py; tests/test_v2_theme.py; tests/test_csp.py] [why](docs/LESSONS.md#strict-pages-and-vendored-libraries)
- **Every action ends in something readable now and later** (a result, a refusal with its reason,
  a wait naming who, a running step). Colour is part of the result: never green over a partial;
  lead with the state to act on. [tests/test_results_are_drawn.py; tests/test_in_flight.py] [why](docs/LESSONS.md#every-action-ends-readable)
- **Never let a wrong thing look like a working thing:** for each feature name the state in which
  it is wrong and looks right, and what makes it visible. [not mechanised] [why](docs/LESSONS.md#never-let-a-wrong-thing-look-right)
- **A refusal or guard names the comparison it made and both operands, never a guessed cause.**
  [not mechanised] [why](docs/LESSONS.md#refusals-name-both-operands)
- **A view showing a subset says so; absent and unreadable are different states.** [partly:
  tests/test_settings_file_integrity.py and per-panel tests] [why](docs/LESSONS.md#subsets-and-distinct-states)
- **A preview that knows the operation changes nothing says so at the confirm, and the button
  names the work it still does; one decision, one control; a removal says whether the data
  survives and where.** [not mechanised] [why](docs/LESSONS.md#previews-that-change-nothing)
- **A change leaves every screen showing the new state:** each mutating route declares what it
  invalidates, each job announces its keys, panels re-fetch and show their value's age; no polling.
  [tests/test_invalidation_map.py; tests/test_live_contract.py; tests/test_announce.py] [why](docs/LESSONS.md#every-screen-shows-the-new-state)
- **Every carried field is drawn; the server reads nothing the form cannot send; every route is
  reachable and every page request resolves.** [tests/test_payload_is_rendered.py;
  tests/test_server_reads_nothing_the_form_cannot_send.py; tests/test_route_reachability.py;
  tests/test_page_requests_resolve.py] [why](docs/LESSONS.md#every-carried-field-is-drawn)
- **Enterprise scale: no per-device work per request;** a per-device question is a job.
  [tests/test_scale.py; the fixed-read test in tests/test_devices_v2.py] [why](docs/LESSONS.md#enterprise-scale)

### Operations and safety

- **Every device-changing operation: preview (the exact program, masked) → confirm by hash as a
  verified person → apply holding the device → verify → rollback on failure → record** (commit and
  receipt), readable again. [every confirm- and approve-gated route declares its five stages,
  each resolved, the gaps named and only shrinking: modules/operation_stages.py,
  tests/test_operation_stages.py; the stages themselves: tests/test_preview_confirm.py,
  tests/test_deploy_receipts.py, tests/test_pipeline.py] [why](docs/LESSONS.md#the-device-operation-lifecycle)
- **What is confirmed is what is sent, byte for byte;** recomputed at apply and refused, naming
  what moved. [tests/test_deploy_contract.py; tests/test_deploy_plan_apply_seam.py] [why](docs/LESSONS.md#what-is-confirmed-is-what-is-sent)
- **Merge-only; a removal is Mode B** (a person selects each unit with a reason, and only a shape
  measured to remove exactly itself). [tests/test_deploy_safety.py; tests/test_removal.py] [why](docs/LESSONS.md#merge-only-and-mode-b)
- **A deploy or restore may add an account, never change one;** a dangerous line or re-added
  secret needs a stated reason, in the hash and the receipt.
  [tests/test_credential_never_changes_on_deploy.py; tests/test_authorised_lines.py] [why](docs/LESSONS.md#accounts-reasons-and-authorisations)
- **Verify scales to what the program touches** (management sections QUICK, the rest FULL), waits
  out settle windows and BGP's hold time; an unreadable read neither passes nor fails.
  [tests/test_verify_scope.py; tests/test_bgp_hold_watch.py; tests/test_verify_reads_reliably.py] [why](docs/LESSONS.md#verify-and-settle-windows)
- **Rollback undoes what LANDED and says what it achieved per device.** [tests/test_pipeline.py] [why](docs/LESSONS.md#rollback-undoes-what-landed)
- **A change to the path the tool reaches a device on needs a repair route independent of that
  path** (management address, vty, credential, route to the manager). [not mechanised] [why](docs/LESSONS.md#changing-the-path-to-the-device)
- **Every mutating route and socket event is declared in `modules/route_gates.py`**, gated before
  input, recording `identity.request_actor()`; reveal, approve and confirm need a person.
  [tests/test_route_gates.py; tests/test_identity.py] [why](docs/LESSONS.md#route-gates-and-verified-identity)
- **One operation per device across processes, refused by name, never queued; a session write
  needs the device held.** [tests/test_device_ops.py; tests/test_session_write_guard.py] [why](docs/LESSONS.md#one-operation-per-device)
- **Several people, tabs and worker processes are assumed:** a protection counts only across
  processes; a confirm is bound to what was previewed; a multi-writer store is locked and replaced
  atomically; an unreadable store refuses writes. [tests/test_repo_lock_across_processes.py,
  tests/test_approval_queue_store.py, tests/test_store_integrity_c158_c160.py,
  tests/test_settings_concurrency.py; open items: docs/CONCURRENCY_AUDIT.md] [why](docs/LESSONS.md#many-people-tabs-and-processes)
- **Reads across devices run concurrently (`fanout.read_each`); a serial loop states why;** the
  deploy batch is sequential for its circuit breaker. [tests/test_device_loops_state_why.py] [why](docs/LESSONS.md#concurrent-reads-across-devices)
- **One owner per piece of state; one home per action** (one resolver, one table, one write path;
  two entry points share one code path). [tests/test_one_home_per_action.py (device effects);
  tests/test_platform_keying.py; tests/test_one_template_resolver.py; otherwise not mechanised] [why](docs/LESSONS.md#one-owner-one-home)
- **Readers take what is COMMITTED; a writer stages exactly its files; every commit goes through
  `repo.commit()` and publishes.** [tests/test_readers_use_what_is_committed.py;
  tests/test_commits_stage_what_they_wrote.py; tests/test_every_commit_publishes.py] [why](docs/LESSONS.md#readers-take-what-is-committed)
- **`Actor:` is who is accountable, `Actor-Verified:` how it was established, `Source:` a slug.**
  [tests/test_actor_verified_trailer.py; tests/test_no_second_commit_path.py]
- **A write path carries its list; only a read may derive the active one.**
  [tests/test_listref.py (four modules); tests/test_onboard_wizard_renders.py (onboarding)] [why](docs/LESSONS.md#write-paths-carry-their-list)
- **A read writes nothing and creates no list; a preview runs the real code, so every write that
  code makes is the preview's write too.**
  [tests/test_reads_write_nothing.py; tests/test_reads_create_no_list.py;
  `TestNoPreviewWritesTheStore` in tests/test_no_post_returns_a_stored_secret.py] [why](docs/LESSONS.md#reads-and-previews-write-nothing)
- **NetBox writes need the master switch and a declared authority;** NMAS deletes only what is
  tagged AND recorded as created; an update records its before; deleting a list never deletes
  NetBox objects. [tests/test_netbox_write_gate.py; tests/test_netbox_write_authority.py;
  tests/test_netbox_update_provenance.py; tests/test_list_delete_never_touches_netbox.py] [why](docs/LESSONS.md#netbox-writes-and-provenance)
- **Secrets are masked on the way OUT (goldens stay verbatim), audit records masked at rest, by
  position and by value; no credential value is printed, logged or returned.**
  [tests/test_no_get_returns_a_stored_secret.py, tests/test_no_post_returns_a_stored_secret.py,
  tests/test_no_agent_tool_leaks_a_stored_secret.py, tests/test_provider_redaction.py] [why](docs/LESSONS.md#secrets-masked-on-the-way-out)
- **Secret files are owner-only from creation (`config.open_secure`); anything kept that holds a
  credential is tracked against the credentials held now.** [tests/test_secret_file_modes.py;
  tests/test_breakglass_currency.py; tests/test_golden_panel_says_what_to_do.py] [why](docs/LESSONS.md#secret-files-and-kept-credentials)
- **Refusing by resemblance is safe, allowing by resemblance is not:** read-only is the whole
  command on an allowlist; a removal shape is allowed only once measured.
  [tests/test_readonly_commands.py; tests/test_removal.py] [why](docs/LESSONS.md#refusing-and-allowing-by-resemblance)
- **Send, read, decide: a secret goes only in answer to the prompt asking for it; anything reaching
  a CLI is printable ASCII.** [tests/test_bootstrap_config.py] [why](docs/LESSONS.md#send-read-decide)
- **Stop a process by identity, never by pattern; no IPv4 literals in `modules/nsot/`,
  `modules/integrations/`, `routes/`.** [tests/test_no_pattern_kill.py; tests/test_no_ip_literals.py] [why](docs/LESSONS.md#identity-not-pattern)
- **A ZTP reservation carries no route or resolver, and nothing on the segment answers broadcast
  DNS** (a configless device phones Cisco). [tests/test_ztp_reservations.py] [why](docs/LESSONS.md#ztp-reservations-and-broadcast-dns)
- **Any operation that restarts devices declares its planned-restart window BEFORE it acts**
  (the tool's Reload, the lab redeploy script, anything else), through `POST /restarts/planned`;
  a window recorded after the restart it covers is only a CORRECTION, with its reason.
  [the late refusal, the correction and the Reload's window: tests/test_restarts.py,
  tests/test_acknowledge.py; that every restarting operation declares one: not mechanised]

### Measurement and testing

- **Never derive an event's time from a device's uptime** (slow vIOS clocks): a restart is the
  counter falling; an event's time is the syslog's receive time. [tests/test_restarts.py] [why](docs/LESSONS.md#device-clocks-and-event-times)
- **Proxmox task logs are in the hypervisor's local time (UTC−6 in this lab), not UTC;** convert
  before comparing. [not mechanised]
- **Test data reaches every column and state a check photographs, clicks or asserts.** Fixtures are
  real captures with minimal edits, never typed from memory. [partly: tests/test_payload_is_rendered.py
  (`EMPTY_IN_FIXTURE`); tests/test_v2_layout_in_a_browser.py] [why](docs/LESSONS.md#fixtures-that-reach-the-case)
- **Every new check is shown able to fail:** remove the property, see the aimed tests fail (not
  crash), read WHICH failed, restore from a copy (never git); a passing control is a missing test.
  [no bytecode: `PYTHONDONTWRITEBYTECODE` in scripts/nmas-test; the rest not mechanised] [why](docs/LESSONS.md#every-check-shown-able-to-fail)
- **A scan has a floor on its population and a planted case it finds; a control's expectation
  comes by a path independent of the code it breaks.** [partly: many tests' floors; not required of new scans] [why](docs/LESSONS.md#floors-and-independent-controls)
- **An absence is a finding only if the store that would hold it was checked and shown able to
  find one; a lookup that misses is a fact about the query.** [not mechanised] [why](docs/LESSONS.md#absence-as-a-finding)
- **Define a population by the property, never a proxy;** list what it assumes stays true. A gate
  keyed on something that moves for other reasons, or one that always refuses, is broken.
  [not mechanised] [why](docs/LESSONS.md#populations-by-property)
- **Match code by parsing or anchoring, never as a substring of a file with prose about it.**
  [not mechanised] [why](docs/LESSONS.md#match-by-parsing-or-anchoring)
- **Confirm the RESULT, not the exit code; prove a copy by using it where it landed; a check of
  the code is not a check of the install.** [not mechanised] [why](docs/LESSONS.md#confirm-the-result)
- **Bounds are about 2.5x a measured time, written beside it; a firing bound names what ran; a poll
  that cannot ask says so; choose a library's default too.** [tests/test_suite_bound.py;
  tests/test_ssh_sessions.py] [why](docs/LESSONS.md#bounds-from-measurement)
- **A read returning exactly its page size is truncated; a claim about all time needs a window that
  covers it; keep the whole record, then summarise.** [tests/test_reader_job.py (full pages)] [why](docs/LESSONS.md#truncated-reads-and-whole-records)
- **A stored answer is dated by its value and judged against its promise;** a failed read keeps the
  last good value. [tests/test_reader_job.py; tests/test_live_contract.py] [why](docs/LESSONS.md#stored-answers-and-their-promises)
- **A test run leaves the person's home untouched: a browser session keeps its downloads and
  profile in its own folder.** [tests/test_home_untouched.py]
- **No test touches a live network, device or store; no duplicate dict key or definition; every
  script reaches its imports.** [tests/test_network_guard.py; tests/test_harness_isolation.py;
  tests/test_no_duplicate_dict_keys.py; tests/test_no_duplicate_definitions.py;
  tests/test_script_entry_points.py] [why](docs/LESSONS.md#test-isolation-and-scans)

## Module map (compact; full map in docs/ARCHITECTURE.md)

- **Legacy core:** `app.py` (routes, SocketIO; new routes go in `routes/`), `modules/ai_assistant.py`,
  `agent_runner.py` (off until Stage 8), `netbox_client.py` (three write chokepoints), `topology.py`,
  `pipeline.py` (the 9-stage deploy every deploy and restore runs), `configure.py`, collectors.
- **Stores and safety:** `settings_schema.py`, `secrets_store.py`, `credentials.py`, `filestore.py`,
  `netbox_guard.py`, `netbox_authz.py`, `outbound.py`, `redact.py`, `identity.py`, `route_gates.py`,
  `csp.py`, `readonly_commands.py`, `connection.py` (`open_ssh`), `config_read.py`, `fanout.py`,
  `inventory/`, `integrations/`.
- **NSoT core, `modules/nsot/`:** `repo.py` (`save_golden`, `commit`, `RepoLock`), `manifest.py`,
  `hostvars.py`, `parsers/`, `roundtrip.py`, `normalize.py`, `templates_repo.py`, `approval.py`,
  `render_artifact.py`, `deploy.py`, `recreate.py`, `removal.py`, `verify_scope.py`, `restore.py`,
  `receipts.py`, `authorisation.py`, `device_ops.py`, `intent_match.py`, `golden_state.py`,
  `profile*.py`, `platform.py`, `listref.py`, `freshness.py`, `ztp*.py`, `onboard.py`,
  `credential_rotation.py`, and the operations `seed`, `intent_ops`, `persist_op`, `rotate_op`,
  `adopt`, `retire`.
- **Operations and screens:** `preview_confirm.py`, `invalidation.py`, `attention.py`,
  `acknowledgements.py`, `reader_job.py` + `readers/`, `capture_job.py`, `deploy_job.py`,
  `job_health.py`, `restarts.py`, `monitoring_coverage.py`, `prometheus_targets.py`,
  `update_op.py` (root-owned updater in `deploy/update/`), `manual.py`, and the v2 pages' data
  (`device_page.py`, `device_list.py`, `panels.py`, `neighbours.py`, `device_logs.py`,
  `device_netbox.py`, `history_sources.py`).
- **Interface:** `routes/` blueprints (`routes.register_blueprints(app)`), v2 in `routes/v2.py` and
  `routes/device_v2.py`, `templates/v2/`, `static/js/nmas_*.js`, `static/css/nmas-v2.css`. Legacy
  pages retire at cutover; the break-glass terminal was removed (R39, 2026-10-05). `telnetlib.py`
  in the root is a Python 3.13+ shim.

## Key architecture (narratives in docs/ARCHITECTURE.md)

- **Per list:** `data/lists/{slug}/` holds `devices.csv` (Fernet-encrypted credentials) and
  `config_repo/` (`golden/`, `host_vars/`, `templates/`, `.nsot/`). `data/key.key` opens every
  secret: back it up.
- **Goldens:** `config_repo/golden/`, enumerated by `repo.list_goldens()`, written only by
  `save_golden()` (one call, one commit); `golden_configs/` is a read-only legacy fallback.
- **Intent** is committed `host_vars/<device>.yml`; secrets are refs keyed
  `credentials.template_secret_key()`. Identity is resolved, never minted by accident.
- **Tags:** `golden/<device>/<ts>`; `baseline/<ts>` earned by measurement, never by mode;
  `golden-state/<ts>` configured AND working. Template approval keys on the import closure.
- **Inventory:** `local` (CSV) or `netbox` per list; `load_saved_devices()` dispatches with no I/O.
  Credentials resolve: device override → designated list → role → site → default profile.
- **Settings:** `data/user_settings.json` only through `write_settings()` (undeclared keys refused)
  under `config.settings_lock()`; a version bump seeds only what it declares; `ratify()` records.
- **Identity:** a verified access assertion AND a trusted peer; no localhost exemption.
- **Redaction** at the provider boundary, on every log handler, and on every response carrying
  config. The approval queue resolves nothing without a person.
- **Environment:** `NMAS_HOST`, `NMAS_PORT` (5000), `NMAS_HEADLESS=1`, `NMAS_TFTP_ROOT`; deployment is
  headless Ubuntu (docs/DEPLOY_LINUX.md). The AI agent changes no device (read-only allowlist);
  Stage 8 makes it a responder that proposes and never confirms.

## Running the App

```bash
pip install -r requirements.txt
python app.py                      # opens http://127.0.0.1:5000
NMAS_HEADLESS=1 python app.py      # headless (no browser)
```

Settings (API key, integrations, TFTP, server bind) are all configurable
from the UI Settings panel — no restart needed except for bind host/port.

## Reaching the lab hosts

The operator's decision, 2026-09-29. Each host has two paths: a LAN address,
and a hostname behind Cloudflare Zero Trust Access on the operator's `homelab`
tunnel. The laptop's `~/.ssh/config` routes those hostnames through
`ProxyCommand cloudflared access ssh --hostname %h`.

| Host | `nmas-host` name | Placeholder in the docs | User |
|---|---|---|---|
| the NMAS host | `nmas` | `<nmas-host>`, tunnel `ssh-nmas.<domain>` | `<user>` |
| the containerlab VM | `clab` | `<lab-host>`, tunnel `ssh-clab.<domain>` | `<user>` |
| Proxmox | `pve` | `<hypervisor>`, tunnel `ssh-pve.<domain>` | `root` |

**The real addresses, tunnel hostnames and users are in `data/lab_hosts.json`**, a
local file (`data/` is gitignored), because the repository is public
(2026-09-29). `scripts/nmas-host` reads it and refuses, naming the file, when it is
absent (exit 78); `nmas-host <host> --field <user|lan|tunnel>` prints one value,
asking nothing. The same file is read on the HOST by the clab sync
(`oxidized-to-config.sh`, for `NMAS_URL` and `CLAB`; it refuses without it) and
by `scripts/nmas-render-units` (the unit templates), so it must exist there too
(docs/DEPLOY_LINUX.md). Other placeholders in
the docs: `<operator>` (the operator's email), `<home>` (a home directory),
`<tunnel-host>` (cloudflared's LAN address), `<laptop>`, `<LAN>`, `<repo>` (the
NSoT config repository), `<account>` (the GitHub account).

- **One helper makes the choice, and every host read goes through it:
  `scripts/nmas-host <nmas|clab|pve> -- <command>`.** For scp and rsync,
  `--target` prints `user@address`. It tries a TCP connect to the LAN
  address's port 22 with a 3 s bound: the LAN if it answers (no token), else
  the tunnel. Deciding per command would be two ways of reaching one machine,
  and two owners of one fact. It also names the path it used on stderr
  ("via LAN" or "via tunnel"), so a failure is attributable. **Report the
  path with every host result.**
- **An expired Access token is a STOP, never a retry.** Only the operator can
  get a token, because getting one opens a browser. An expired token fails
  with `websocket: bad handshake` and
  `Connection closed by UNKNOWN port 65535`. `nmas-host` recognises it, exits
  75, and names the host and the operator's command,
  `cloudflared access login https://<host>`. Tell the operator which host,
  and do not loop and do not try to log in. A retry loop against an expired
  token is a wait that cannot observe what it waits for, the same defect as
  the `gh` poll that could never ask.
- **Reaching a host from further away widens nothing.** Host commands stay
  read-only. `nmas-deploy` is the operator's. No writes to `data/`, devices,
  NetBox, Grafana or the lab without the operator.
- **Hosts only, never devices.** Network devices are reachable only through
  the tool. Never open a tunnel path, a jump chain or a port forward that
  reaches a router or switch, because that would rebuild the terminal 7.8
  removes. `nmas-host` passes no ssh option through (an unknown flag is
  refused), and it runs every session with `ClearAllForwardings=yes`.
  `scripts/nmas-lab-tunnel` predates this rule and forwards to lab nodes,
  including a probe runbook's SSH forwards to device addresses (C212).
- **Proxmox is root.** `ssh-pve` is read-only unless the operator asks for a
  specific action there. Name any command before running it: `nmas-host`
  prints every command before it runs.

## Standing facts about this lab

- **No lab run, staged run or probe inside the nightly backup window, 08:30 to 09:00 UTC**
  (the hypervisor logs it as 02:30 local): the backup loads the lab host, and a measurement taken
  then measures the backup. [not mechanised]
- **Staged runs and probes never run on s3:** it is CPU-starved and carries the management path
  for the fleet (C93). Use s1 for IOS and r2 for IOS-XE. [not mechanised]

**Grafana's dashboard ROLES (the operator, 2026-10-01; they had drifted twice).** Two roles,
each named by a setting, by UID, never hard-coded and never defaulted in code (both
settings default to empty, and the page says so):

| Role | Setting | This lab's dashboard | Where it is drawn |
|---|---|---|---|
| FLEET (the Monitoring page's default) | `grafana_fleet_dashboard_uid` | `rcn-lab-overview` ("RCN Lab — Monitoring, Telemetry, Alerting and Data Lake"); the key was ABSENT on the host when read on 2026-10-01 (it ships with the fleet page), so it is set in Settings once that release is deployed | `/v2/monitoring` |
| DEVICE (every device page) | `grafana_device_dashboard_uid` (variable `device`, value `hostname`) | `nmas-device`, built by `deploy/grafana/build_nmas_device.py`, imported in Grafana and set on the host (read 2026-10-01) | `/v2/device/<name>`, Monitoring tab |

**`rcn-lab1-snmp` is NEITHER.** It was the ORIGINAL device dashboard, replaced by
`nmas-device` on 2026-09-30. Its real model stays a FIXTURE
(`tests/fixtures/grafana/dashboards/`) for tests about panel FILTERING in general (8 panels,
4 selecting a device), named as such. A test that asserts a ROLE uses that role's real
dashboard: the fleet page `rcn-lab-overview`'s captured model, the device page
`nmas-device`'s. Before asserting what a role's dashboard is, read the host's settings.

## Tests

```bash
scripts/nmas-test         # the suite, confined to loopback (C46); args go to pytest
scripts/nmas-test -n auto # in parallel
pytest                    # unconfined; says so in its header
```

- **The gate runs CI's command in CI's interpreter** (`scripts/nmas-ci-env`, two workers,
  coverage; docs/TESTING.md). Failing CI runs: `scripts/nmas-ci-log` (never print its token).
- **Bounds:** `NMAS_TEST_TIMEOUT` (300 s) names each process's test and stack when it fires;
  `faulthandler_timeout = 45`; CI's job bound is 10 min.
- **No live network, three layers** (C46): the test process refuses non-loopback connects, every
  child is refused by construction, and `scripts/nmas-test` runs in a loopback namespace
  (`network: CONFINED`). **No live store:** a temporary `NMAS_DATA_DIR`, and a run fails if the
  checkout's `data/` changes (C32); importing `app` starts nothing (C36).
- **Per-file coverage:** the table in docs/TESTING.md; add a row there for a new test file.

## Conventions

- New routes in `routes/`; `app.py` and `index.html` grow only by registration and include. New
  screens in `templates/v2/`, after a signed-off mockup.
- A new mutating route is declared in `modules/route_gates.py` and `modules/invalidation.py`.
  [tests/test_route_gates.py; tests/test_invalidation_map.py]
- A new setting is declared in the schema with a default reproducing prior behaviour, and is
  surfaced or documented in docs/SETTINGS.md. [tests/test_settings_write_path.py]
- Return `{"ok": bool, "error": str, ...}`; module-level `log = logging.getLogger(__name__)`;
  `pathlib`/`os.path`; every integration call logs and surfaces its failure. [not mechanised]
- `.env` holds `ANTHROPIC_API_KEY` (plaintext by design, gitignored).
