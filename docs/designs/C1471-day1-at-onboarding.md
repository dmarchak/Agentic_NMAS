# C1471: Day 1 configured as part of onboarding (design note, not built)

The register's row C1471: ZTP onboarding is Day 0 only, and Day 1 (the device's full service
configuration) is a separate, manual sequence of Seed intent, a hand-written intent and a
deploy. The full design and its options are in [DAY1_AUTOMATION](../DAY1_AUTOMATION.md); this
note records where Lab 9 left it and the smallest next step. Written 2026-10-24 by the
overnight run, for the operator's review.

## Where it stands

- Lab 9 showed Day 1 as one approved, verified change. On s5 (2026-10-24 00:42 UTC, commit
  `4f19c600`), the device's page took an intent edit, then Plan a deploy, its preview, a
  confirm by hash, 22 lines sent, saved and verified. Every step but the edit is Mercury's
  existing deploy path.
- The step a person still takes is the intent itself, typed in the editor. That is labour
  under the charter's rule (MANUAL_STEPS): Mercury could derive it from what NetBox already
  plans (the VLANs, the access ports and their hosts, the trunk).

## The smallest next step: a Day 1 intent proposed at Verify (DAY1_AUTOMATION 2.1)

1. **Derive.** When Verify promotes a device, a reader turns its NetBox Planned record and its
   role into a proposed intent: VLANs from the site's VLAN group, access ports from the
   interfaces' untagged VLAN, the trunk from the cable to the parent. This is one function over
   NetBox reads Mercury already makes (`device_netbox`, `netbox_after_intent`), and it writes
   nothing.
2. **Show it as a deploy preview.** The Verify card's result offers "Plan Day 1…", which opens
   the device's existing deploy preview with that intent staged: the exact program, masked,
   with its hash. The person approves by hash; that is the one decision.
3. **Apply through the deploy path.** The usual sequence: hold, send, verify, roll back on
   failure, receipt. Nothing new on the device side. C1646's VLAN read-back is needed first;
   it is in code as of 2026-10-24.

## What it is not

- Not Day 0 over TFTP. Day 0 stays minimal, with no service configuration and no lasting
  secret in clear text.
- Not an automatic deploy. The approval stays a person's decision by hash. Only the typing
  goes.

## Size and dependencies

- **M.** The derivation reader, about a day with its tests on real NetBox captures; the
  Verify card's offer and the staged preview, about a day; the manual page and a walk, half a
  day.
- **Needs:** C1646 (verify reads VLANs where a switch keeps them), and a mockup and sign-off
  for the Verify card's new offer (a new control).
- **Open questions for the operator:**
  - whether the proposal is offered for every role, or only switches first;
  - what happens when NetBox plans nothing for the device: no offer, or an empty proposal
    that says so.
