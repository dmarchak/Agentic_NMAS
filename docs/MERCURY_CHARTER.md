# Mercury's charter (for the operator's sign-off)

The governing definition, written 2026-10-07 when the operator re-anchored the project. Where
another document disagrees with this page, this page governs, and the other is re-labelled.

## What Mercury is

- **NMAS** is the platform: the VM where the services run together.
- **Mercury** is its frontend and control plane, the one-stop control centre. It compiles
  information from the sources of truth, reads and writes them, and executes automation on the
  network. **It is not a source of truth:** the facts belong to other systems.

## The sources of truth

| Facts | Owner | Mercury |
|---|---|---|
| Devices: existence, identity, role, site, platform, status; IPAM as decided | **NetBox** | reads them; writes only as the first step of a confirmed operation |
| Intent, configurations (goldens, baselines), templates | **GitHub** (the network's repository) | the one writer, through confirmed operations, every write a commit |
| DHCP | **Kea** | the front end to its reservations |
| Monitoring | **Prometheus / Grafana** | reads; generates targets and rules from the inventory |
| Logs | **Loki** | reads |
| The queryable archive past retention | **MinIO** | reads |

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

**Oxidized is retired.** It is a second, redundant configuration history, and GitHub owns
configurations. Mercury's own scheduled read-and-compare replaces its polling.

## Mercury's own records

Receipts, acknowledgements, approvals, rollback blocks, restart windows, runbook runs and the
readers' stored values are the audit trail of Mercury's actions. Mercury owns them, and they
are consolidated into ONE store (a database of its own, archived to MinIO past retention).

## AI-assisted actions

The Actions menu distinguishes two kinds:
- **Standard actions** are deterministic, the same for every device: capture, deploy intent,
  revert by reload, rotate, onboard.
- **AI-assisted actions** are reasoned per device and topology, not one size for all: drain and
  return to service, a revert without a reload, link moves, troubleshooting.

**An AI-assisted action produces only a PROPOSAL:** the change set across the devices involved,
its expected effects, how success is verified, and its reasoning. It starts from a known
pattern (the platform's drain profile, for example) and fills in what is specific to this
network (on 2026-10-06, s2's static route).
- **A person reviews, edits and confirms it.** It runs through the same pipeline as every
  operation, and is recorded as "proposed by the agent, confirmed by <person>".
- **The safety floor applies:** never the management path; success judged by measurement.
- **With the agent off,** the action falls back to its built-in runbook or to manual intent
  edits. Nothing is possible ONLY with AI.

This is Stage 8's recorded authority: the agent proposes, never confirms.

## The test for every feature

It must make a network engineer's life easier than the CLI alone, or they will go around it.
Simple first; cleverness later.

## New findings

Each is judged against this page as **CORE** (it serves what Mercury is, above), **LAB** (a
quirk of this lab: parked) or **FUTURE** (worth doing, not now: parked, recorded), before any
design work starts. Only CORE findings are active.
