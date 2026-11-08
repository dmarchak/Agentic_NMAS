# Mercury's charter (APPROVED 2026-10-07)

The governing definition, written 2026-10-07 when the operator re-anchored the project, and
approved the same day. Where another document disagrees with this page, this page governs, and
the other is re-labelled.

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

## New findings

Each is judged against this page as **CORE** (it serves what Mercury is, above), **LAB** (a
quirk of this lab: parked) or **FUTURE** (worth doing, not now: parked, recorded), before any
design work starts. Only CORE findings are active.
