# Mercury's charter (APPROVED 2026-10-07)

The governing definition, written 2026-10-07 when the operator re-anchored the project, and
approved the same day. Where another document disagrees with this page, this page governs, and
the other is re-labelled.

## The first principle: if a step can be automated, it is (the operator, 2026-11-14)

Mercury exists to make network management easy and automatic. **If a step CAN be automated,
it IS**, unless a strong reason, usually a security one, says otherwise, and that reason is
written where the step is. "Not built yet" is not a reason. If people still do a lot by
hand, they will not use Mercury: they will go back to the CLI.

**The bar for the design:** Mercury is intuitive, easy to use and easy to navigate, and a
network engineer who works in the CLI sees its value at once. Needing to ask where something
is shows the design is too complex. Mercury is judged by the jobs an engineer does ("is my
network OK?", "what broke, and why?", "what changed, and who?", "push this", "undo that", "add
a device", "rotate the passwords", "show me this device", "prove it worked"), not by its
features: every common job is faster or clearer in Mercury than on the command line, and one
where the CLI wins is a finding (the human-perspective review, C3588).

- **Every flow built or touched lists each step that still needs a person, and why.** A build's
  report names the manual actions it adds or keeps, each one's reason, and what would automate
  it.
- **A manual step's reason comes from a fixed list:** approving a change plan; entering a
  secret; a judgment or risk decision (credentials and AAA, an irreversible change, adopting a
  device's state into intent); paid spend beyond the caps. Every person-facing action (a
  button, a form, a command a row tells someone to run) is declared automated or manual, with
  its reason, in one action registry, and a test fails on an undeclared action or a reason
  outside the list (C3585). One approval covers a whole plan, its canary and every wave, never
  one click per device or per wave.
- **A person is told when automation stops,** never asked to watch it work: a failure rolls
  back, stops the run and notifies the team, and the person then decides.
- **Examples it settles:** a rollout advances wave to wave by itself after its one approval; a
  deploy's verify includes the probe that shows the change works; onboarding adds and probes
  the read-only account; every account rotates on a schedule; no Needs attention row tells a
  person to run a shell command; host steps are API calls; a departure row shows its lines
  (the automation pass, C3584).

This sits beside "Mercury automates labour; people make decisions" (CLAUDE.md,
docs/MANUAL_STEPS.md): the fixed list is what a decision is.

## What Mercury is

- **NMAS** is the platform: the VM where the services run together.
- **Mercury** is its frontend and control plane, the one-stop control centre. It compiles
  information from the sources of truth, reads and writes them, and executes automation on the
  network. **It is not a source of truth:** the facts belong to other systems.

## The sources of truth

| Facts | Owner | Mercury |
|---|---|---|
| Devices: existence, identity, role, site, platform, status; IPAM as decided | **NetBox** | reads them; writes only as the first step of a confirmed operation |
| Intent, configurations (goldens, baselines), templates | **The network's git repository on the Mercury host** (the operator, 2026-10-18). A remote (GitHub, Gitea or GitLab, a kit's upstream Mercury) is an optional off-host copy, never required | the one writer, through confirmed operations, every write a commit |
| DHCP | **Kea** | the front end to its reservations |
| Monitoring | **Prometheus / Grafana** | reads; generates targets and rules from the inventory |
| Logs | **Loki** | reads |
| The queryable archive past retention | **MinIO** | reads |

### The network's repository: on the host; a remote is optional

The operator's decision, 2026-10-18 (it replaces "its remote chosen by the deploying team" of
2026-10-16):
- **The source of truth is the repository on the Mercury host.** Mercury reads what is
  committed there and is its one writer.
- **A remote is an optional off-host copy.** It may be GitHub, Gitea or GitLab, or a kit's
  upstream Mercury. It is never required.
- **Mercury works fully offline, with no remote at all.** A missing remote is not an error,
  and no screen asks for one.
- **A GitHub-specific check runs only when a GitHub remote is configured.** This covers
  privacy, deploy-key scope and the API.
- **Durability is stated, not nagged** (post-Phase 7). Mercury says whether an off-host copy
  exists (a remote, or the VM's backup) and how old it is. An installation that chose a
  single copy is not in error.
- **A remote's commits that Mercury lacks are foreign changes** (C1315, post-Phase 7). They are
  reviewed and taken in, or declined, through preview and confirm, designed together with the
  edge kit's offline sync. They are never a reason to hold Mercury's own pushes behind a
  terminal step.
- **"Mercury is the one writer" is policy.** No GitHub ruleset holds it on the remote for now.
- **Every use of GitHub is optional, the app's own included** (the operator, 2026-10-30, C2241).
  This covers a network's remote, and also the app's own repository, its CI verdict and the
  Update check. Mercury works as expected offline, with only its local files and its own git
  repositories. An outside service that could not be asked is stated where it is read ("not
  asked: why, last answered when") and under Needs attention's What was checked. It is never a
  Needs attention row, and never critical. A problem the service did answer, such as a remote
  holding commits Mercury lacks, is a different state.

What still assumes a remote, each place marked fine or must change, is `docs/REMOTE_OPTIONAL.md`.

## Hardware tiers (the operator, 2026-10-18)

| Tier | The host | What it runs |
|---|---|---|
| **Minimum** | 4 vCPU, 8 GiB, about 100 GB | an edge kit; about 100 devices |
| **Standard** | 4 to 8 vCPU, 16 GiB | about 1,000 devices |
| **Large** | 16 or more vCPU, 32 GiB or more | Standard's fleet, and the local model (PHASE8_PLAN section 10) |

- **Core 1.0 must fit Minimum.**
- **Hosted AI adds no hardware.** The local model is what needs Large.
- **The device counts are targets, not measurements,** until a fleet of that size is run on
  that tier. Each is replaced by its measurement when one is taken.
- **The lab's NMAS host is a Standard host:** 4 vCPU and 15.6 GiB (PHASE8_PLAN 10.8, measured
  2026-10-14), with 11 devices.
- These tiers replace any earlier capacity line. The Stage 10 plan's install sizing points here
  (NSOT_STAGE10_PLAN section 7.4).

## New devices: Mercury is a front door to NetBox, never a second inventory

A device exists in NetBox before Mercury touches it, by one of two entry points:
1. **Pick a Planned device from NetBox:** the preferred, design-first path. ZTP and discovery
   match a booting device to its Planned record by MAC or serial.
2. **Create one in Mercury:** written INTO NETBOX FIRST as Planned, as a confirmed step,
   prefilled with what the device reports (serial, model, platform), after a duplicate check
   on name, address and serial.

Onboarding's (and adopt's) success sets the device Active. Mercury keeps no list of its own.

## Credentials: the one accepted exception

NetBox dropped its native secrets in 3.0 and is not meant for device credentials. The fact is
split:
- **NetBox holds WHICH credential applies:** a credential-profile name on the device, its role
  or its site.
- **Mercury holds the SECRET VALUES**, because Mercury executes rotation. They sit behind a small
  secrets-backend interface, so HashiCorp Vault or OpenBao can replace the local store later
  (Stage 10).

## What goes

**Oxidized is retired.** It is a second, redundant configuration history, and the network's git
repository owns configurations. Mercury's own scheduled read-and-compare replaces its polling.

## Mercury's own records

Receipts, acknowledgements, approvals, rollback blocks, restart windows, runbook runs and the
readers' stored values are the audit trail of Mercury's actions. Mercury owns them, and they
are consolidated into ONE store (a database of its own, archived to MinIO past retention).

## The test for every feature

It must make a network engineer's life easier than the CLI alone, or they will go around it.
Simple first; cleverness later.

**Every feature states its industry need** (the operator, 2026-10-25): the problem network
engineers have, how established commercial tools address it, and how Mercury meets or improves
on it at enterprise scale. A feature without a stated industry need is questioned before it is
built. The need is a section of each feature card (PHASE8_PLAN section 3).

**IPv6 parity: a feature that works only over IPv4 management is unfinished** (the operator,
2026-10-17). Every feature works on an IPv6-only management network; the audit, the designs and
the measurement plan are `docs/IPV6_PARITY.md`, the epic C1245 (FUTURE, Phase 8's first).

## Implement by concept, approve by outcome

**Mercury lets someone who understands a technology conceptually implement it without knowing
how to configure it** (the operator, 2026-11-06). Such a person can't judge CLI lines or flow
rules, so asking them to approve a change set makes the approval a formality. Mercury asks them
to approve what they can judge, and proves the rest. The outcome view is the default, never the
only view: an expert can always work at the mechanism level, by hand.

1. **Approve the outcome, not the mechanism.** Every preview of a change, and every AI
   proposal, leads with what will be true afterwards, in concepts. Then come the blast radius
   (the devices touched, the traffic classes affected, and each protected class untouched or
   not), the checks that will prove it, and how to undo it. The exact change set is one level
   down, never removed, and it is still what is confirmed and sent.
2. **Verify against stated outcomes.** Every intent, and every generated job, carries
   outcome checks in plain Given/When/Then, written or confirmed by the person. They are
   checked before by simulation on the network's model, and after on the network. A failed
   check before refuses the change; a failed check after rolls it back. A check Mercury cannot
   decide is shown as "can't tell", never as a pass, and the person sees that before approving.
3. **Trade-offs are asked, once.** A trade-off the person can't judge (failing open or closed,
   a timeout, a wider scope) is never chosen silently: it is stated in plain terms, with the
   cost of each side, and asked once per network. The answer is recorded (who, when, the costs
   shown), shown in every later explain-back with how to change it, and asked again only when
   its context changes.
4. **Expert review happens once, in the catalogue.** What Mercury can do by intent is a
   catalogue of typed entries, each with its compiler per platform and its verification,
   reviewed once as code by someone who understands the mechanism. Applying an entry needs
   only outcome-level approval, within the network's autonomy tiers. A request outside the
   catalogue becomes a generated job, and a knowledgeable reviewer must publish it.

**The test, beside the industry need:** a feature that changes the network states the outcome
a non-expert approves, and the checks that prove it.

## Two standing rules: the AI troubleshoots by itself, and every screen leads with its bottom line

**The operator's design change, 2026-11-14, standing:**
- **R1. When Mercury's code fix fails, the AI troubleshoots automatically. No button starts
  it.** A code fix that fails, does not verify, or does not exist for the incident's kind
  starts AI troubleshooting once per failure, within the caps ($1.00 an incident, $80 a day).
  A cap that would be exceeded starts nothing, and the card says which cap and offers Hand
  over. It is a background AI feature under CLAUDE.md's AI cost safety rules, unchanged: the
  switch "Start AI troubleshooting automatically when Mercury's fix fails" is **off by default
  on every network**, offered as one switch in the AI settings with its estimate beside it
  (per incident, the per-incident cap, the day cap), and only a person turns it on or off
  (the operator, 2026-11-14: "keep CLAUDE.md as it is"). **Turning it on catches up on the
  person's choice** (the operator, 2026-11-15): it first lists every open incident whose fix
  failed or that has no fix ("starts on these N open incidents, about $X"), each tickable,
  records what was chosen, and starts on those within the caps; after that every new failure
  starts by itself. An incident left unticked keeps one "Start AI troubleshooting" button for
  a person's press. **A hold a person must resolve counts as no fix Mercury can run alone**
  (the operator, 2026-11-15; a guard-4, 6 or 9 hold): the AI diagnoses and proposes within
  its catalog, and where the fix needs a person's approval (a template bring-in) it says so
  as its finding and offers Hand over. **In every mode of self-healing** (the operator, 2026-11-15: "the AI only
  proposes, and nothing runs without a person's approval, so it investigates in Dry run
  too"). **An incident that ended in a missing capability starts again by itself, once,
  within its cap, when the missing operation is deployed.** The AI's NEVERs stand: it
  proposes, and a person approves by hash. **Cost:** one background AI call per failure where a person turned
  it on, inside the caps. **Prevents:** an incident waiting for a person to press a button
  whose outcome was already decided, and spend no person approved.
- **R2. BLUF, bottom line up front, on every screen, card and notification.** The top is three
  plain lines:
  1. what happened, in the engineer's words ("r7 stopped sending telemetry at 09:30"), never
     Mercury's codes (CONFIG_I, g4, cant_fix, "departs (-2)");
  2. the impact on the network or on Mercury ("Mercury can't see r7's interfaces or CPU;
     traffic is unaffected");
  3. how to fix it: the one next action as a button, or the AI's proposal with Approve, Modify
     and Deny.

  Everything else sits below, collapsed: evidence, attempts, guards and holds, alert text,
  timings, costs, History links. Severity follows impact: critical only for a network outage.
  The impact line comes from Mercury's own table per incident or fault kind, never written by
  the AI, and a test fails on a kind without its what, impact and fix. Nothing that already
  failed on an incident is offered as its next action. A guard or hold working as designed is
  a plain line in the details, never a failure. **Cost:** one table entry per kind, and each
  screen's top drawn from it. **Prevents:** a person reading Mercury's internals to find out
  what broke, what it costs them and what to press.

- **R4. Incidents are problems, not signals** (the operator, 2026-11-14). Syslog lines, alerts,
  lost streams and reads are evidence. Mercury classifies evidence into a problem (device,
  object, condition, cause, who is affected) and titles the incident by it ("s1 Gi1/0
  err-disabled by BPDU guard: h1 is offline", never "alert 'Critical syslog received'
  firing"); the alerts are listed as evidence under it, and related signals fold into the one
  problem. Before any action the device is read to confirm the classification; evidence and
  device disagreeing is no action, said. A saved script matches on the classified problem's
  fields, never an alert's name or a raw line. Evidence Mercury cannot classify goes to the
  AI, which names the problem in the same fields; a person saving the fix saves the
  classification rule with the operation, seeing and editing the match first. R2's BLUF table
  is keyed by problem. **Cost:** one classifier per problem kind, and a device read before
  acting. **Prevents:** incidents named after their symptoms, a fix chosen from an alert's
  name, and a script matching a problem it was never made for.

- **R5. Simple by default** (the operator, 2026-11-15). Every screen and card shows, by
  default, only a title (one line), the impact (one line), a status (one line) and one
  primary action, plus at most one secondary link. The default view has no paragraphs, IDs,
  hashes, citations, prompt versions, cost breakdowns, guard names or form fields. Everything
  else sits behind ONE "Details" control per card, which opens the full record: logs, the
  AI's reasoning and evidence, attempts, timings, hashes, holds, costs, the full plan record
  and customise forms. **Budgets, enforced by tests on the demo-path pages:** at most 3 lines
  of default-visible text per card, at most 2 visible buttons per card, and 0 visible form
  fields until "Customize" is pressed. **Acceptance:** the five-second test per screen, in
  which a newcomer can say what's wrong and what to press. Built only from mockups the
  operator approved. **Cost:** a Details control per card, and a budget test per demo-path
  page. **Prevents:** a screen that makes a person read Mercury's record to find the one
  thing to press.

## Standing rules decided 2026-11-14 to 2026-11-16 (the operator)

Each is the operator's decision in those sessions; where a rule is also stated elsewhere, the
place is named. Where this list and another document disagree, the charter governs.

- **R3. An event is decided on its own device read, at once; verify scales to what the fix
  touches and passes the moment its direct checks pass.** An err-disable or port-security
  line opens its incident and is classified from the device read, not after an alert's minute;
  a fix's verify reads what it changed (a port's status, its spanning tree, its own section) and
  ends when those checks pass, never on a fixed wait beyond the rule's own windows (the 10 s
  re-trip window, the connect check). Snapshots and verify are scoped by what the plan touches:
  access ports read the port, a routed, uplink or trunk interface keeps its protocols' checks,
  anything unclassified keeps the full snapshots; the rule applied is recorded on the run.
  A fix's confirmation reads only its own device; waiting on a lock (another check, another
  device's run) is a declared wait in the wait registry (`modules/waits.py`), drawn as one,
  never an outcome (the operator, 2026-11-16, after r6 ended "partial" on another act's
  drift-check lock, C3864).
- **Proportionality: a plan's disruption never exceeds its problem's impact.** Options are
  ranked least disruptive first; a step whose impact exceeds the problem's (an outage to fix a
  monitoring-only problem) is never the primary fix. A reload is the last resort, offered only
  as a separate "schedule a reload" choice, a person's explicit decision in a maintenance
  window, after the lesser fixes failed. The AI's composing prompt carries this rule, and the
  preflight compares a step's impact with the problem's (C3837).
- **No time-based holds in self-healing: every occurrence is fixed.** A problem that keeps
  coming back is a recurrence finding, a fix something keeps undoing is a fight finding, each
  said to a person; a fight stops a fix only where the network set it to. Guards 4 (the
  approved state) and 6 (many devices at once) stay, a person deciding. **The retry policy:** a
  failed fix is retried once per trigger (self-healing switched on, a matching fix saved,
  every 24 h while the incident stays open), never in a loop; each retry and its trigger
  recorded on the incident (C3824).
  Faults inside a declared drill or exercise count toward no finding (C3842).
- **Switching self-healing On is the approval for what is already open** (C3823, C3844): its
  line names what it also fixes, and a self-healing batch runs every device at once, each held,
  checked, verified and rolled back on its own; rollouts keep one device first (CLAUDE.md,
  "Reads across devices run concurrently").
- **The AI never interacts with devices.** It reads only through Mercury's reads (the read
  engine's allowlist, as Mercury's account), and every change it proposes is a plan of
  Mercury's own catalog steps, run by Mercury after a person approves it by hash ("AI-assisted
  actions", below).
- **The AI is an engineer, never an admin.** It changes no setting, cap or switch, approves
  nothing, and acts under its own engineer-role identity (C3596, C3597); a person approves
  every plan it proposes.
- **Everything the hash binds is shown before Approve:** every step on every system (each
  system's exact actions as its own numbered step, in order), and what the AI saw and said
  beside the button (C3840); and **Fixed shows its proof** (the verify's reads, their output
  and times, one click deep).
- **No email or person's name in an AI payload:** people are stable HMAC labels
  (`display_names.label`), never an identity, in everything sent to a model.
- **Severity is impact times criticality** (the problem's impact on traffic and service,
  weighted by the affected endpoint's or device's criticality; C3798, after the demo).
- **Compose before reporting a gap.** Before the AI reports that Mercury lacks a capability, it
  composes a plan from Mercury's existing steps (and a provisional shape through the admin's
  approval path); a gap is reported only when no composition of existing steps can do it, and
  Mercury's check says when a catalog step for the problem was not yet tried.
- **One catalog, two uses.** Every capability the AI uses is a Mercury feature a person can use
  too, with its own person-facing home (C3718; e.g. the collector's log, C3836).
- **Never duplicate what already exists** (CLAUDE.md, "Never duplicate", Reused / New in every
  report), and **one object for a saved fix**: a saved fix is both the self-heal script and
  the reusable action, one entry with its match and how it runs (C3849).
- **On screen, people by display name, never an email or identity** (C3834); a status line is
  one sentence in an engineer's words, its source a small label (AI / Mercury) shown once.
- **Deploys and approvals:** the operator is told before every deploy; anything needing the
  operator's words is parked until they are given, and a renamed approved item is a new item
  (memory, "Park what needs words"). Under the fast lane's skip mode (2026-11-15) a change
  ships without tests, its debt listed in docs/FAST_LANE_DEBT.md, cleared in one full pass
  (tests, fidelity, full gate, CI green) once the features are complete: after the Lab 10
  demo and Lab 9's SDN work, which continues in skip mode, run as long unattended sessions
  (the operator, 2026-11-16). The Lab 10 recording and the demo run on the rehearsed build,
  the backup video their fallback; code that writes to devices keeps its independent review
  before every deploy meanwhile (CLAUDE.md, "Temporary skip mode within the fast lane").

## Human-facing means human-readable

**A standing design rule (the operator, 2026-11-08), applied to everything human-facing from
then on.** It is the reading side of "Implement by concept, approve by outcome": a person who
knows the technology conceptually can act on every item Mercury shows them, without knowing
Mercury's internals.

1. **Plain language first, four questions in order.** Every human-facing surface (Needs
   attention, History, device pages, notifications and emails, Settings, the CLI's human
   output, board pages) leads with plain language that someone who knows the technology
   conceptually can act on. Every item answers four questions, in this order:
   - **What happened, and where?** For example: "r6's OSPF router-id was changed on the
     console to r4's ID; r6 and r4 stopped peering".
   - **Does it need me?** Yes or no, and why: "a fix restarts OSPF on r6, so a person decides".
   - **What do I do?** The one action, as the button on the item: Approve, Decline, Open,
     Acknowledge.
   - **What happens if I don't?** For example: "r7 stays unreachable"; "nothing; this is a
     record".
2. **No dead identifiers.** An incident ID, decision ID, hash, commit or policy ID is never the
   primary content. Each one shown is either a link to the page for the thing it names, or it
   sits under a collapsed "Details for the record" disclosure. If no page exists for it, it goes
   under the disclosure, never in the main text.
3. **Internals are translated or moved under details:** guard numbers and names, step logs
   ("1. claim … 8. record"), fix-type keys (`process_reset`, `missing_line`), "Tier 2", "golden
   departs", "unmodeled", "dry run" phrasing. The main text uses words: "Mercury would have
   fixed this itself (watching only, so nothing was sent)", never "would heal: missing_line
   (Tier 1)". A tier can show as a label after the words, never instead of them.
4. **Who did what is stated truthfully:** "Mercury proposed" against "<person> declined"; a
   console change reads "made on the console, no account named".
5. **Never send a person to look up what Mercury already knows** (added by the operator the same
   day). "Find who changed it on History" is a bug. The row shows, inline: who (the account, or
   "on the console, no account named"), when, from where, and the exact lines added and removed
   (secrets masked), from the CONFIG_I and the diff Mercury already holds. Facts come first; a
   hypothesis is labelled as one and comes after.
6. **Live refresh never interrupts the person** (added the same day). A refresh keeps the scroll
   position, focus, open or closed disclosures, text in inputs, and marks (Right, Wrong). It
   doesn't flash, and nothing above the reader shifts: new items above the viewport show as "N
   new, show them" instead of pushing the page. This applies to every live page.

**The test, beside the industry need:** every item a person sees answers the four questions in
plain words, and every identifier on it is a link or sits under "Details for the record".
Rules 2 and 5 are to be checked by a ratchet test over the rendered pages (a bare identifier
outside a link or a collapsed disclosure, or text sending the reader to look something up on
History, fails, against a backlog that only shrinks), and rule 6 by a browser test per live page
(scroll, an open disclosure, typed text and the layout kept across a refresh); the rest is the
review's.

## Every fix through Mercury

**A standing design rule (the operator, 2026-11-10), beside "Human-facing means human-readable".**
Every fix must be possible through Mercury, in code; no solution may require the CLI.
- A test list, runbook, diagnosis, Needs attention row or manual page whose fix says "at the
  console" (or any device CLI step) names a missing Mercury operation. That operation is
  registered as a row the turn the step is found, and the text says so beside the step.
- A device's console stays break-glass for a person; it is never the only way to a fix.
- Reading is no exception: a read a fix needs goes through Mercury's read-only paths
  ("No terminal steps", CLAUDE.md).

**Cost:** a register row per console step found, and the operation it names built before the
step leaves the text. **Prevents:** fixes that only someone with a device's CLI can make, and
that leave no preview, confirm or record (r7's lost telemetry streams, 2026-11-08 to 11-10: the
known recovery was a console sequence, C2838).

**The test, beside the industry need:** a fix a person is told to make is a Mercury operation,
or its step names the register row for the operation still missing.

## What Mercury knows is chosen, never typed

**A standing design rule (the operator, 2026-11-10), beside "Human-facing means human-readable".**
Any field asking for something Mercury already knows is a selection, not free text: a dropdown,
or a searchable picker when the list is long.

- **What Mercury knows:** platform slugs, credential profile slugs, devices, interfaces, DPIDs,
  controllers, templates, captures, end hosts and the hosts a controller lists (by name, MAC
  and IP), networks, roles, tags, apps and their versions.
- **Where a field must also accept a value Mercury cannot know** (a trace's To address, a new
  name), it is a combo box: the known values are offered as the person types, free text is
  allowed, and the typed value is checked, with a refusal that names its reason ("not a host
  any controller lists").
- **Each option shows what the person recognises:** the NetBox name first, then the MAC, the IP
  or the DPID. Never a bare id.
- **A picker's default is the value that fits the question asked,** never merely the newest
  item of any kind (a capture picker offers the captures of the command the template needs).

**Cost:** a picker and its list per field, and a search where the list is long. **Prevents:** a
person typing what Mercury holds and being refused for a spelling, and a field that takes none
of the names a person knows a thing by (the Lab 9 sitting, 2026-11-10: the credential profile's
slug typed as free text; a trace's From that took neither the router's name nor its IP, although
the controller listed its MAC on a switch port; a capture picker that defaulted to the newest
capture of any command).

**The test, beside the industry need:** on every form, a field whose answer is in a list Mercury
holds is a selection from that list, or a combo box that offers it; the review walks each form
with this question, and a free-text field for a known value is a finding. To be checked by a
scan of the v2 forms against the lists Mercury holds, with a backlog that only shrinks.

## The fix-it path

**The target flow for every Needs attention item (the operator, 2026-11-10; steps 2 to 8 as he
amended them on 2026-11-11).** It is the yardstick for recurring issues and saved fixes now, and
for the ease-of-use review after the labs.

**The rule the steps rest on** (docs/HEAL_TO_INTENT.md, section 12; the operator's words,
2026-11-14): No fix runs from AI text. The AI may propose a plan of catalog operations,
approved once by a person by hash, executed in order, stopping on the first failure; it never
composes commands, runs anything itself, or retries on its own; a saved fix is the operation a
person saved from a verified run. The plan engine (modules/plan_engine.py) runs such a plan:
the toolbar assistant may propose one of its plans; the fix-it path's proposal is still one
operation of the catalog, a plan of one.

**The operator's design notes of 2026-11-14 extend these steps** (docs/HEAL_TO_INTENT.md,
section 20, to plan next; rows C3693 to C3698): self-heal's code checks for a match before any
AI; the AI investigates a can't-fix on its own, under the AI cost safety rules, and the person
is notified to approve; an incident's fix may be a plan of catalog operations, approved once by
hash; the AI reads to verify and reports, advisory to the operation's own verify; a verified fix
may be saved as a self-heal rule (a symptom signature and an operation), starting in Dry run
with its track record shown; every AI answer carries its own feedback on Mercury's tools; and
the AI's actions are recorded as the same kinds a person's are, "AI, requested by <person>",
"approved by <person>". Until they are built, the steps below are the flow as it runs.
1. **The notification:** the person sees it in plain words: what, where, and whether it needs
   them.
2. **The user asks the AI to troubleshoot (Explain).**
3. **The proposal:** the AI reads the device, its logs and its history through read-only tools,
   says whether this has been seen before, and proposes ONE fix as a Mercury operation, shown as
   that operation's preview with its hash.
4. **The approval:** they approve the fix. This is approval only; there is no self-healing choice
   here.
5. **The run:** Mercury runs the approved operation: the device held, each step shown, a record.
6. **The verification:** Mercury verifies, and reports back before anything is saved:
   - a. the device is in the state the fix intended;
   - b. the original symptom has cleared;
   - c. no harm: after a settle period (the heal grace), there is no new alert or incident on the
     device or its blast radius since the change, adjacencies and neighbours are as before, and
     the outcome checks that apply (reach, untouched, datapath) pass. Anything undecidable is
     shown as "can't tell".

   - **It passed:** on the same screen, the result is in plain words with the choice: "Add this
     fix to self-healing: apply alone next time / propose to me next time / don't save". If
     anything reads "can't tell", "apply alone" is not offered, only "propose to me" or "don't
     save", with what couldn't be checked.
   - **It failed** ((a), (b) or (c)): STOP. No save is offered and nothing is retried. Mercury
     shows what it tried, what it found and the cost so far, then offers three choices and no
     other:
     - **Retry with more information:** the person adds their own context; the AI plans again
       from step 3 with that and the failed attempt's evidence. The retry's estimated cost and
       the incident's running total are shown before it is pressed; at the per-incident cap it
       is refused, and only Cancel and Hand over remain. Every attempt's fix needs the person's
       approval, and a proposal that already failed in this incident is flagged, never silently
       proposed again.
     - **Cancel:** nothing more runs; the incident stays open; the attempts stay recorded.
     - **Hand over:** step 8.

     Never an automatic retry.
7. **The save:** a fix is saved only on the person's choice in step 6, and what is saved is the
   operation the person ran and saw verified, with its parameters, never the AI's words. The
   record keeps the verification it was based on.
8. **The hand-over, and any failed step:** a hand-over is a write-up for an engineer of what was
   tried, what is known and the next steps. And if any step fails, the item says which step,
   why, what Mercury already undid, and what the person can do next, as a button where one
   exists. No dead ends, and no "see History".

**Cost:** each Needs attention kind is built and tested against the eight steps, with a browser
walk per kind's worked example. **Prevents:** a fix that ends with no proof it worked or did no
harm, a fix saved on a verification nobody saw, and a failure that leaves the person with nowhere
to go.

**The test, beside the industry need:** an item's path from the notification to fixed is these
eight steps, its clicks counted, and each step's failure state names the step, why, what was
undone, and the next action.

## AI-assisted actions

The Actions menu distinguishes two kinds:
- **Standard actions** are deterministic, the same for every device: capture, deploy intent,
  revert by reload, rotate, onboard.
- **AI-assisted actions** are reasoned per device and topology, not one size for all: drain and
  return to service, a revert without a reload, link moves, troubleshooting.

**An AI-assisted action produces only a PROPOSAL:** the change set across the devices involved,
its expected effects, how success is verified, and its reasoning. It starts from a known
pattern (the platform's drain profile, for example) and fills in what is specific (a
neighbour's static route, for example).
- **A person reviews the outcome, the blast radius and the undo first (the change set one level
  down), edits and confirms it** ("Implement by concept, approve by outcome", above). It runs
  through the same pipeline as every operation, and is recorded as "proposed by the agent,
  confirmed by <person>".
- **The safety floor applies:** never the management path; success judged by measurement.
- **With the agent off,** the action falls back to its built-in runbook or to manual intent
  edits. Nothing is possible ONLY with AI.

This is Stage 8's recorded authority: the agent proposes, never confirms.

**The AI is a senior network engineer using Mercury, not Mercury's admin** (the operator's
change of approach, 2026-11-14):
- **It MAY** read anything Mercury can read, investigate with Mercury's read tools, propose
  catalog operations or a plan of them, draft text for a person to review, and record a
  missing capability (what it wanted, why, for which incident or question), listed for review.
- **It may NEVER** change Mercury's settings (self-healing mode, AI on/off, caps, credentials,
  notifications, roles, templates' approval), approve anything (its own proposals included),
  run a change or start a job itself, compose a device command, see or type a secret, or
  exceed the caps.
- **Its device reads** go through Mercury's reads engine with Mercury's own account, through
  the same protections as Show commands and more (a read of one of the AI's command families,
  a positive list, held whole by the allowlist, its arguments
  checked against golden and intent, the read loop's re-check, every read on History); the
  read-only account is a hardened choice, offered only when every device in scope holds it and
  its probe passed.
- **Its changes:** the AI may propose a plan of catalog operations, approved once by a person
  by hash, executed in order, stopping on the first failure; it never composes commands, runs
  anything itself, or retries on its own; a saved fix is the operation a person saved from a
  verified run (the operator's words, 2026-11-14). Closed loop stays a later phase.

## New findings

Each is judged against this page as **CORE** (it serves what Mercury is, above), **LAB** (a
quirk of this lab: parked) or **FUTURE** (worth doing, not now: parked, recorded), before any
design work starts. Only CORE findings are active.
