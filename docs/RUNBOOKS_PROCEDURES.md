# Runbooks and procedures: engineers' own repeatable work (a FUTURE design; not built)

**Amended 2026-11-06 (the operator's decision 2 on the SDN platform design):** I-1's jobs, saved
and reviewed scripts run in a sandbox, reverse sections 4 and 5's "no script runner" on the
terms those sections now state. The rest of this document, written 2026-10-17, describes the
runbooks and procedures that sit beside jobs, and where it says Mercury runs no scripts it is
superseded by sections 4 and 5.

**FUTURE, post-cutover (Phase 8 or later); not Phase 7 work.** Decided by the operator on
2026-10-17 and registered as C1147. Written that day from the operator's brief and from the code
at that date, in the form of the 2026-10-16 design notes. Documents only: nothing here is code.
Under the charter ([MERCURY_CHARTER.md](MERCURY_CHARTER.md), "New findings") it is FUTURE.

## 1. The need

Engineers want to save their own procedures and run them again: the checks they do before and
after a change, the evidence they collect for a ticket, and the sequence of steps a recurring
change takes. Elsewhere, they would write a script or an Ansible playbook for this.

As written on 2026-10-17, Mercury would not run their scripts; since 2026-11-06 it runs reviewed
ones as I-1's jobs, on section 5's amended terms. Beside jobs it offers three things, each built
on a path that already has its guards:

- **(a) Runbooks:** named, parameterised sets of READ commands across chosen devices, with
  optional parsers and a report.
- **(b) Procedures:** saved sequences of Mercury's OWN gated actions. Each step keeps its
  preview, its confirmation and its record.
- **(c) Ansible for interop only:** export intent or rendered configuration as playbooks, and
  import a playbook's configuration lines through config to intent
  ([CONFIG_TO_INTENT.md](CONFIG_TO_INTENT.md)).

**None of the three adds a write path to a device.**

## 2. What exists today

Read 2026-10-17, in this repository:

- **The reads engine** (`modules/nsot/reads.py`; [NSOT_READS.md](NSOT_READS.md) sections 2 and
  11). It is the one way to ask devices read-only commands. A run goes through these stages:
  - every command is checked, whole, against the allowlist (`modules/readonly_commands.py`'s
    three tiers);
  - each device is held while it is read;
  - commands are sent through the one sender;
  - answers are masked (`redact_text`) and capped;
  - devices are read concurrently, with a bound (`fanout.read_each`);
  - the run is recorded, at its start and its end.

  Show commands (many devices) and the Ask tab (one device) are its two screens.
- **Saved command sets** (`modules/nsot/command_sets.py`, NSOT_READS.md section 5). A set is a
  name, a description and its commands.
  - Sets are per network and committed in the network's repository as the person who saved them.
  - Every command is checked by the allowlist when the set is saved, and again when it runs.

  **A runbook is a command set grown up.**
- **Mercury's gated operations.** Each operation that changes a device declares its stages in
  `modules/operation_stages.py`: preview, confirm, apply holding the device, verify, rollback,
  record. Each mutating route is declared in `modules/route_gates.py` and records
  `identity.request_actor()`.
  - The operations are: intent edit, deploy, persist (save), reload, verify, NetBox import,
    capture, seed, revert, retry, rotate and retire.
  - Each operation's preview binds its confirmation to a hash of what it will do
    (`modules/preview_confirm.py`).
- **The old "Ansible" tab, cut** ([NSOT_FEATURE_AUDIT.md](NSOT_FEATURE_AUDIT.md)). It was not
  Ansible: it replayed AI-saved command lists over Netmiko in config mode. That made it the
  sixth unguarded push path, and it could be triggered from the AI chat even with AI disabled.
  Section 5's decision is that lesson, kept.

## 3. The shape

### (a) Runbooks: reads, saved, parameterised, reported

A runbook is a committed file in the network's repository (`runbooks/<slug>.yml`), saved through
`repo.commit()` as the person. It holds:

- **Parameters**, each with a shape. For example `peer` (an IPv4 address) or `vrf` (a VRF name
  from intent). A value is substituted as ONE token of its shape (`modules/cli_tokens.py`'s rule): a value
  that is not one token is refused, never quoted around.
- **Commands**, each inside Show commands' allowlist and checked whole, after substitution, when
  the runbook is saved and again when it runs. A runbook can never run a command Show commands
  would refuse.
- **Targets:** chosen devices, a role or a site. They are resolved when the runbook runs, and the
  resolved list is shown before the run.
- **Optional parsers.** A parser turns each answer into fields: a TextFSM template (TextFSM is
  already in the lock, through Netmiko), or one of Mercury's own readers. A parser that fails is
  that device's failure, named; it is never an empty row.
- **Optional checks** on those fields (for example "every BGP neighbour Established"), each
  stated as a comparison with both operands drawn.
- **A report:** one page per run with the summary first (counts by outcome), grouped and
  searchable, each device expanding to its masked answers. It is kept as the reads engine keeps
  runs.

A run is a reads-engine run. It is refused first, held, masked, capped, bounded and recorded. A
runbook adds no stage of its own between Mercury and the device.

### (b) Procedures: Mercury's own actions, in order

A procedure is a committed, reviewed sequence of steps. **Each step is one of Mercury's
operations:**
- an intent edit (through config to intent or the Intent tab's document);
- a deploy;
- a persist;
- a reload (inside a declared planned-restart window);
- a verify;
- a NetBox import;
- a runbook run (section a), as a check between steps.

**A procedure runs no action of its own.** When it runs, each step opens that operation's own
preview, with the operation's own words. The person confirms each step that needs a person, by
its hash, exactly as if they had opened the operation themselves. The operation's own record is
written, and the procedure's run records which step it was.

- A step whose verify fails stops the procedure. That step's own rollback runs. The procedure
  says which step stopped, why, and what each earlier step left (as rollback says what it
  achieved per device).
- A runbook check between steps that fails stops the procedure before the next change.
- **A procedure cannot confirm for a person.** A step needing a confirmation waits, naming who,
  and nothing runs past it. Unattended running would need the approval queue's rules, and is
  out of scope until the operator decides it.

**Never let a wrong thing look like a working thing:** a procedure whose steps were reordered or
edited is a new commit, reviewable in git. A run records the procedure's commit, so "ran
procedure X" always names exactly which X ran.

### (c) Ansible, for interoperability only

- **Export.** A network's intent, or its rendered configuration per device, exported as Ansible
  content:
  - the inventory from Mercury's devices (no credentials: a variable the receiver fills from its
    own vault);
  - per-device `host_vars`, or the rendered lines as a `cisco.ios.ios_config` task.

  This is for a team that must hand configuration to another organisation's Ansible. Rendered
  configuration is masked on the way out, as every response carrying configuration is.
- **Import.** A playbook's configuration lines (`ios_config` `lines` and `parents`) are taken
  out of the YAML and passed, as text, through config to intent's preview. The playbook is
  never run. Its lines become intent only after the same parse, not-modelled review, secret
  detection, render-and-reproduce check and commit as a pasted block.

## 4. What it must never do

**Amended 2026-11-06, the operator's decision 2 of that day** (the SDN platform design r4,
section 11, I-1; its first code is the contracts, `modules/jobs/`). Jobs, Mercury's saved
Python scripts, reverse the last rule below on change A's terms. Its intent stands: **no
unreviewed code commits a change.** Runbooks and procedures keep every rule as written. Jobs
meet each rule's intent as the bullets say.

- **No new write path to a device.** A test can hold this. Runbooks reach devices only through
  `reads.run`. Procedures reach devices only by calling the operations' own routes or functions.
  Neither module imports the sender, `open_ssh`, or a config-mode call.
  - **A job's writes build a change plan** (`ctx.changes`, `modules/jobs/sdk.py`). Its commit
    sends the plan only through the guarded write path: B, the approvals, the feature engine,
    `flow_ops`, H's policy push, and the post-checks.
  - A job reaches devices for reads only through the SDK's allowlisted reads. It is never
    given the sender, `open_ssh`, a socket or a token.
- **No stored or embedded credentials.** Runbooks and procedures name no credential. The reads
  engine and the operations resolve credentials as they do today.
  - A job names none either. The SDK uses credentials as opaque handles the job cannot read.
- **No second inventory.** Targets resolve from Mercury's own devices. An exported Ansible
  inventory is output, never read back.
  - A job's scope (the NetBox object types and roles it may reach) resolves from NetBox
    through Mercury.
  - The broker enforces that scope in Mercury's own process, never inside the job's sandbox.
- **No unreviewed code commits a change** (until 2026-11-06: "no unreviewed code"). A runbook
  is commands and a parser template. A procedure is a list of operation names and their
  parameters. Neither carries Python, Jinja that runs on the server outside the template
  sandbox, or a shell command. A job is Python, and:
  - **a Draft is unreviewed:** it runs for its author only, and in plan mode only. It records
    its intended writes and applies nothing;
  - **only a Published version commits.** It was reviewed by someone other than its author
    (self-review only where the installation's policy is single-user, and recorded as such),
    its harness tests passed, and it is pinned by its folder's content hash. Any edit returns
    it to Draft (`modules/jobs/lifecycle.py`);
  - **every job runs in the job sandbox,** Draft or Published, written by a person or by J:
    the static check, the runner's audit hook, and the operating system's unit pair. An
    installation without the sandbox refuses every job run by name. There is never a weaker
    fallback.

  **Built so far:** the contracts and the lifecycle's pure functions (phase P1). The runner,
  the sandbox and the commit path are P4's, so until P4 lands no job runs on any installation.

## 5. Decided against: Mercury running arbitrary or AI-generated playbooks

The operator's decision, 2026-10-17, with its reasons:

1. **It bypasses intent.** A playbook that configures a device changes it outside intent, so
   intent no longer describes the device. The drift checker then reports a drift Mercury itself
   made, and the next deploy either reverts the playbook's change or is refused.
2. **It holds credentials outside the store.** Ansible needs device credentials in its own
   inventory or vault. That is a second home for a secret, outside the credential store's
   currency tracking and masking.
3. **A second inventory and a second supply chain.** Ansible's inventory duplicates Mercury's
   device list, and its collections are packages that change on their own schedule. On offline
   kits ([OFFLINE_OPERATION.md](OFFLINE_OPERATION.md)) every collection is one more artefact to
   carry, verify and keep current.
4. **Unreviewed code with privileged access.** A playbook is code, and an AI-generated one is
   code nobody wrote. Running it would give that code the device access Mercury guards with
   preview, confirm by hash, hold, verify and rollback, without any of those. It is the
   cut "Ansible" tab's defect again (section 2).

Ansible stays possible where it belongs: an organisation that runs Ansible can consume Mercury's
export, and send its lines back through config to intent.

**Amended 2026-11-06, the operator's decision 2 of that day: jobs (I-1) reverse this decision,
on change A's terms.** The decision stands for Ansible playbooks, and for any code outside a
job's terms. A job (the SDN platform design r4, section 11) meets each of the four reasons
above as follows:

1. **Intent:** a job's device change is a change plan, committed through the same feature
   engine, B (the protected set) and post-checks as Mercury's own operations, with a receipt.
   It is never a side channel to the device.
2. **Credentials:** a job holds none. The SDK uses them as opaque handles the job cannot read.
3. **A second inventory and a second supply chain:**
   - the scope resolves from NetBox through Mercury;
   - a job imports only the SDK and an allowlist of plain-data standard-library modules, by
     the static check run before every job. No collection or package comes with a job.
4. **Unreviewed code with privileged access:**
   - a Draft runs only in plan mode, and only for its author;
   - every job runs in the sandbox, behind the broker;
   - only a Published version commits: reviewed by someone other than its author, and pinned
     by its content hash;
   - its commit goes through preview, confirm by hash, hold, verify and rollback, as every
     device-changing operation does;
   - every write carries the run's cookie or receipt id, so the run's undo removes exactly
     what it made.

   A job J writes is a Draft like any other, reviewed by a person before it can commit.

Until P4 builds the runner and the sandbox, no job runs (section 4's note).

## 6. Size, and order

- **(a) runbooks:** M. The reads engine, the allowlist and saved sets exist. The new parts are
  parameters, parsers, checks and the report page.
- **(b) procedures:** M to L. A step runner that only opens operations, one board per state
  (waiting, stopped and what each step left), and a test that it imports no sender.
- **(c) export and import:** S each. Import depends on config to intent being built.

**Order:** (a), then config to intent, then (c), then (b). (b) is the most likely to be asked
for unattended running, so it comes last, after the operator decides that question.

Register: C1147 (FUTURE, the operator's decision, 2026-10-17). docs/PHASE7_BURNDOWN.md section
4 lists it.
