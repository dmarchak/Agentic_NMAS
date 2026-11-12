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

H14 is the diagnosis engine (the amendment's item 1, docs/HEAL_TO_INTENT.md 19.3): `diagnose`
(the runbooks as code: a plan from intent and the network model, every read through the reads
engine as kind ``diagnosis``, the per-device lock, the 70-command cap, `RULES` and the
ranking; "adjacency down with both ends at intent" built, "A can't reach B" H15's) and
`diagnose_parse` (each read's parser, only where a real capture exists). Its record is the step
log's ``diagnosis`` row. Read-only and deterministic: it sends no command that is not a read
and calls no model.

H19 is the action remediations' declarations (the amendment's item 2, 19.4): `actions` (the four
action kinds in the tier table, guards 13a to 13e, `judge`; every kind refused by name until
its part, H20 to H22, builds its operation), `flaps` (self-healing's own syslog read's
after-store step recording each interface's UPDOWN transitions at their receive time, for 13e), and
`diagnose.ACTIONS` with `diagnose.action_for` (an action chosen only from the diagnosis's first,
complete hypothesis).

H20 is the port bounce and the OSPF adjacency reset through it (19.4): `bounce` (the one home of
the fixed program, its hash and authorisation, guard 13c's CEF and only-path reads, 13f's
archive and measured platform, the planned window declared before the send, the held send, the
confirm only once Mercury is back in, verify, the stability window and the repair), the
decision made before an Alert's notice (`consider`) and the act `act.run` takes to it.

H21 is the BGP session clear (19.4, N16): `session_clear` (the decision on the diagnosis's
choice, Tier 1 on a network marked lab and a proposal elsewhere, and the act as the policy or
as the approving person), on `privileged.SESSION_CLEARS` (the command policy, the measured
prompt and settle time, the one held send, its verify and its Tier 2 record).
H22 is the dampening proposal (19.4, 19.6 rows 8 and 8b): `dampening` (raised after a bounce
still flapping or 13d's second need, in AUTO only; intent's ``set_dampening`` patch and its
deploy bound by one hash; Approve refused by name until the ``interface.dampening`` removal its
rollback needs is measured on the device's platform; the act as the approving person, verified
by ``show interfaces dampening`` on the deploy's own session).
"""
