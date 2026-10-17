# Runbooks and procedures: engineers' own repeatable work, without a script runner (a FUTURE design; not built)

**FUTURE, post-cutover (Phase 8 or later); not Phase 7 work.** Decided by the operator on
2026-10-17 and registered as C1147. Written that day from the operator's brief and from the code
at that date, in the form of the 2026-10-16 design notes. Documents only: nothing here is code.
Under the charter ([MERCURY_CHARTER.md](MERCURY_CHARTER.md), "New findings") it is FUTURE.

## 1. The need

Engineers want to save their own procedures and run them again: the checks they do before and
after a change, the evidence they collect for a ticket, and the sequence of steps a recurring
change takes. Elsewhere, they would write a script or an Ansible playbook for this.

Mercury will not run their scripts (section 5 says why). Instead it offers three things, each
built on a path that already has its guards:

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

- **No new write path to a device.** A test can hold this. Runbooks reach devices only through
  `reads.run`. Procedures reach devices only by calling the operations' own routes or functions.
  Neither module imports the sender, `open_ssh`, or a config-mode call.
- **No stored or embedded credentials.** Runbooks and procedures name no credential. The reads
  engine and the operations resolve credentials as they do today.
- **No second inventory.** Targets resolve from Mercury's own devices. An exported Ansible
  inventory is output, never read back.
- **No unreviewed code.** A runbook is commands and a parser template. A procedure is a list of
  operation names and their parameters. Neither carries Python, Jinja that runs on the server
  outside the template sandbox, or a shell command.

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
