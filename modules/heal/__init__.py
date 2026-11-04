"""Heal to intent (board H, Lab 10; docs/HEAL_TO_INTENT.md): deterministic code that returns a
device to its committed intent, IBN's Respond function. No AI in the loop.

H1 (this package's first part) is `policy`: each network's heal policy and its settings, the
mode (off, dry run, AUTO) under C2009's guard with AUTO's expiry, a change to the policy
previewed and confirmed by hash as a verified person, each network's one-click Turn off, and
the installation-wide kill switch. Triggers (H2), decide (H3) and act (H4) read it.

H2 is the triggers and the detect pass: `triggers` (after-store steps on the readers and the
drift record, each asking "check this device now"), `attribution` (a configuration change is
Mercury's or from outside, the person named), `incidents` (one incident per cause, the
blast-radius fold, the per-network lock across processes), `grace` (two reads the grace period
apart), `hold` (the topology hold, guard 5) and `detect` (the reads, until an incident is ready
for the decision). H3 takes a ready incident with `incidents.ready` and `incidents.claim`.

H3 is the decision: `kinds` (the intersection rule, N13's units, the tier table), `guards`
(section 6, in order), `decide` (each ready incident judged and its one program computed with
its hash, recorded, its incident closed, deferred or kept for H4 and H5) and `decisions` (the
record, the dry run's Right / Wrong, the halts). H4 takes a heal with `decisions.to_apply` and
`decisions.take`, and recomputes `decide.program` from its own read.

H4 is `act`: a taken heal applied as the policy through THE plan and THE apply
(`routes.deploy.plan_devices` and `apply_batch`, with the heal's read as their capture source,
so stage 4 compares the device with it), each removal carrying the policy's words as its
stated reason (N9, C2402), verified by the pipeline, then each healed unit at intent and a
removed feature's symptom gone (N13) before its save, the golden read again, and the outcome
recorded (`decisions.applied`, `incidents.close`); one job per incident.

H6 is the records: `steplog` (every heal and dry-run decision's steps, masked, a records
store kept per network, read by History's ``heal`` source), the golden commit's
``Source: heal_to_intent`` and ``Actor-Verified: policy``, `change_record` (deterministic, no
AI call), `journal` (the NetBox journal entry, under the master switch and the policy's
declared authority) and `interrupted` (a heal whose job ended before it recorded its outcome:
found by its mark, recorded, its incident closed, raised in Needs attention).
"""
