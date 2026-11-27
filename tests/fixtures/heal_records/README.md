# Real heal and fix-it records (C4090)

Captured from the installation on 2026-11-24 (00:51 UTC) by `scripts/nmas-config-read --records`
(the kinds `heal-incidents`, `heal-decisions`, `heal-steps` and `fixit`, network Default), every
line masked by Mercury's `redact_text` as the capture printed it (`<redacted:...>` values stay
masked). Read by `_fixit_captured` in tests/v2_context.py, the provider that draws the incident
card's loops below for tests/test_v2_context_is_drawn.py (the operator's ruling of 2026-11-23:
each loop drawn from a real captured record of its kind).

## The files and the loops each feeds

| File | What it holds | Loops it draws |
|---|---|---|
| `healed_tail.json` | Incident `hi-977e71ad809c` on r3 (a configuration change healed to intent, closed fixed and verified), its one decision row and its four step-log rows, whole | `templates/v2/_fixit_section.html` `C.tail.steps` (the step log's `records.tail`: save, golden commit, read again); `templates/v2/_inc_proof.html` `P.checks` (the close's `fixed.verify`) |
| `plan_errdisable.json` | Incident `hi-0614b58f49f7` on s5 (port security err-disabled Gi0/3), and proposal `p1` of its fix-it record, the AI's err-disable recovery plan, with the fix-it record's device identity | `_fixit_section.html` `st.checked` (the proposal's `shown.preconditions_read`) and `lines.verify` (the built-in command plan's verify, rendered by its own code from the proposal's parameters) |
| `plan_collector.json` | Incident `hi-22cfdc299000` on r7 (lost telemetry streams 101 and 102), and proposal `p2` of its fix-it record, the AI's re-subscribe with the collector step, with the collector session it kept | `_fixit_section.html` `parts`, `part.actions` (the host's close of the kept session) and `part.lines` (the device's lines) |

| `held_decisions.jsonl` | Three decision rows held by a guard a person resolves, the newest of each guard on Default with no `until` (from the same capture, 2026-11-24): guard 4 on r7 (2026-11-14, its golden departs from its intent), guard 6 on r6 (2026-11-17, many devices at once), guard 9 on r4 (2026-11-08, healed past its rate), one JSON line each as `decisions.jsonl` keeps them | tests/test_human_readable.py's Needs attention, History and device surfaces (`_plant_held`: the held rows, C2820's survey item 4) |

## The s1 walk's records (2026-11-27)

Captured on the installation during the operator's s1 walk (one BPDU from the end host into s1
Gi1/0, err-disabled by BPDU guard, twice), read by `_fixit_walk_records` in tests/v2_context.py:

| File | What it holds | Loops it draws |
|---|---|---|
| `proof_reads.json` | The proof the card draws for incident `hi-f90c700a7d45`, fixed by the operator's press of BPDU guard recovery (access ports): `fixit.proof.of_run` on its run, its two verify checks, its net-zero words and the four reads the run made, each answer masked by the proof module itself, captured at 21:43 UTC | `templates/v2/_inc_proof.html` `P.reads` |
| `fix_offers.json` | The card's next fix (`fixit.section.view`'s `bluf.fix`) for incident `hi-ebc220c86c8f` while two saved fixes matched it: BPDU guard recovery (access ports), Automatic, and (any port), Manual, in `more`; captured at 22:06 UTC before either was pressed | `templates/v2/_fixit_section.html` `(F.more or ())` |
| `open_bpdu.json` | Incident `hi-ebc220c86c8f` itself, standing, with its one decision row and its three step-log rows, whole, by `nmas-config-read --records` at 22:13 UTC: the open incident `fix_offers.json`'s fix is drawn on (a closed one's page draws no next fix) | the page `fix_offers.json` draws on |

Their edits, and nothing else: in `proof_reads.json` the end hosts h1 and h2 in the interface
descriptions renamed `edge-h1` and `edge-h2`; in `open_bpdu.json` 10.255.1.21 replaced by
192.0.2.121, the person's email by `alex@example.com`, and h1 renamed `edge-h1`.
`fix_offers.json` is as captured.

The stores' layout is tests/fixtures/incident_page/'s: `incidents`, `decisions` and `steps` as
the stores hold them; `page` the incident drawn; `line` one fix-it record line as kept.

## The edits, and nothing else

- Every IPv4 address replaced by one in 192.0.2.0/24, one mapping for the folder:
  10.255.0.10 to 192.0.2.10, 10.255.4.6 to 192.0.2.46, 10.255.1.10 to 192.0.2.110 and
  10.255.4.14 to 192.0.2.54. The records hold no IPv6 address. `held_decisions.jsonl` adds
  172.20.20.1 to 192.0.2.20 and 10.255.4.4 to 192.0.2.44 (its records: the same edits and
  nothing else).
- The person's email and their account name replaced by `alex@example.com`.
- The end host `H7` (not of the generic r1-r9, s1-s9, edge-, core- or leaf- kind) renamed
  `edge-h7`.
- Only the records named above are copied from each capture; each record is copied whole.
- No internal URL, domain or path was in them (`/usr/bin/ss`, in the collector's dry run, is the
  system's own).

## What the first captures could not draw (answered 2026-11-27)

`P.reads` and `(F.more or ())` are drawn from the s1 walk's records above; `P.net_zero.lines`
was removed from `_inc_proof.html` by the operator's decision of 2026-11-27 (a net-zero run that
differs is rolled back and refused, so no Fixed proof holds such lines). As first written:

Three loops still need a record these four captures do not hold:

- `_inc_proof.html` `P.reads` and `P.net_zero.lines`: a fix's proof lists reads and a net-zero
  difference only from a command plan run's own record (the privileged runs store, its
  `net_zero.differs`) and the read engine's records of that run, or from a heal verify step
  that keeps `reads`. The 31 captured `fixed.verify` lists keep no `reads`, no step-log row
  keeps a step with `reads`, and the runs the other 33 fixed incidents name are not captured.
- `_fixit_section.html` `(F.more or ())`: a second saved fix offered beside the first needs
  the saved fixes store holding two fixes whose match holds one open incident. The captures
  name one saved fix (`script-bpdu-guard-recovery-access-ports`, on 22 closes), and not its
  store.
