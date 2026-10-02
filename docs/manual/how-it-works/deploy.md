# Deploy a change

A deploy moves a device toward its committed intent: it sends the lines intent has and the
device lacks, checks the device is still working, and records what landed.

## Before the deploy: the plan

You change intent (edit and commit it), then plan the deploy. Planning reads, and sends
nothing:

1. **The device's committed golden** is the capture the plan computes against.
2. **Intent is rendered** through the network's approved template, with the monitoring
   profile's lines merged in.
3. **The program is computed**: each line intent has and the capture lacks, preceded by the
   section it belongs to (`interface …`, `router ospf …`), one `exit` per section. This exact
   list is what will be sent, byte for byte.
4. **Every line is attributed**: from your edit, or already pending before it (something on
   the device drifted since the last capture), or from the monitoring profile.
5. **Gates** are checked and drawn by name: the template can reproduce this device; nothing
   in the program is a dangerous line you have not authorised with a reason; no credential
   would change; the device is not held by another operation.

The confirm is bound to a hash of that program. If the device or intent moves before you
confirm, the deploy refuses with nothing sent.

## The run, stage by stage

The deploy then runs one pipeline per device. Its stages, in the order the code declares
them:

1. `netbox_query`: reads the device's NetBox record for context, if NetBox is configured.
2. `template_render`: the confirmed program is used as it is; nothing is re-rendered.
3. `ci_gate`: a local check, before any session opens: every line that matches a dangerous
   pattern must be one you authorised, exactly.
4. `pre_snapshot`: the first SSH session. Reads the running configuration (kept for a
   rollback) and the routing neighbours, routes and interfaces, for verify to compare.
5. `config_diff`: refuses a program the device already holds in full (nothing to send).
6. `deploy`: sends the program in configuration mode, merge-only. Nothing is negated unless
   it is a removal you chose (Mode B).
7. `post_snapshot`: reads the same facts again, on a NEW session.
8. `verify`: compares. A routing neighbour lost, a route table that shrank, or a protocol
   intent declares that is not up is waited out for its settle window first (OSPF 45 s, BGP
   60 s, RIP 90 s; BGP is read again after its hold time). A loss that persists fails verify;
   a failure triggers a rollback.
9. `save_golden`: the device's configuration after the change is committed as its golden,
   only once verify passed, as you.
10. `audit_log`: a record of the whole run, written whatever happened.

## When verify fails: the rollback

A rollback undoes what LANDED, which on a partial push differs from what was sent: an old
line is sent back where the change replaced it, and a new line is negated where there was
none. The rollback is read back on a fresh session and says what it achieved (restored,
incomplete, failed). The failed change is recorded against intent, so the next plan will not
offer it again until you revert the intent or lift the block with a reason.

## What is recorded

- **The golden commit**, naming the program's hash and the person who confirmed.
- **A receipt** per device: what was sent, the checks that ran, the rollback if any. The
  device page's History tab shows it.

## Many devices at once

A batch deploys one device after another, in the order you set, and stops if verify fails on
devices repeatedly (the circuit breaker). Sequential on purpose: a bad change stops after
the first device it breaks, instead of reaching the whole fleet at once.
