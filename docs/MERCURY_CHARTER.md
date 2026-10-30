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
- **A person reviews, edits and confirms it.** It runs through the same pipeline as every
  operation, and is recorded as "proposed by the agent, confirmed by <person>".
- **The safety floor applies:** never the management path; success judged by measurement.
- **With the agent off,** the action falls back to its built-in runbook or to manual intent
  edits. Nothing is possible ONLY with AI.

This is Stage 8's recorded authority: the agent proposes, never confirms.

## New findings

Each is judged against this page as **CORE** (it serves what Mercury is, above), **LAB** (a
quirk of this lab: parked) or **FUTURE** (worth doing, not now: parked, recorded), before any
design work starts. Only CORE findings are active.
