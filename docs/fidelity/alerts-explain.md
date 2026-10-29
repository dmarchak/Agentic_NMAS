# Fidelity: Monitoring › Alerts, an alert's evidence pack and Explain (P1, 2026-10-26)

Board: `AlertsExplain.dc.html` (canvas "NMAS v2 mockups", page "P1, Monitoring › Alerts",
version 143), drawn 2026-10-26 and signed off under the Phase 7 mode
(docs/STANDING_APPROVAL_LOG.md). It was owed since 15.12: the Alerts tab (PHASE8_PLAN 15.9,
P1) was built ahead of its board by the operator's ruling of 2026-10-25, its board and record
batched to the sprint's Saturday. The board's first draft drew the tabs and a flat list wrongly;
it was redrawn to the built structure (version 143) before this comparison, since the built
one is the signed-off Monitoring page's and the large-fleet rule's.

Shots: `tests/test_board_shots.py::test_monitoring_alerts_explain` (`alerts-explain-tab`,
`-open`, `-explained` at 1440, 1280 and 390, beside `alerts-explain-board` at 1440), on
test_device_v2's lab with tests/v2_context.py's `_alert_evidence` set-up: r3's real heartbeat
instance and a silenced syslog instance firing, each pack built by the real trigger over the
Loki and Prometheus captures; the first card opened; Explain pressed with hosted AI allowed and
an answer planted (a hypothesis citing `alert`, needing a person).
Templates compared: templates/v2/_alert_evidence.html, templates/v2/_evidence_pack.html, templates/v2/_explain.html, templates/v2/_explain_block.html, templates/v2/_explain_beta.html, templates/v2/_explain_ask.html
Templates sha256: `dd0da45972844f5bfbc6a40515e7313b01d139c36a8cb220c52f1c24f7b1272a`

**Compared again 2026-10-29 (C2174, an alert firing on its data's absence):**
`_evidence_pack.html`'s alert piece gains one clause, drawn only when the piece carries
``absence`` (a rule whose no data is its fault, firing as "Alerting (NoData)"): after the rule,
its kind and state, "The fault is the data's absence: **no heartbeat received for 750 s from
r2** (the rule's no-data state is Alerting: no data is its alert)." No other region changed.
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_explain` (2026-10-29 05:5x UTC,
  at 1440, 1280 and 390 beside the board at 1440): its alert is r3's heartbeat set to Alerting,
  so the clause does not draw and every region reads as before. The clause is shot on History's
  rebuilt pack (`::test_monitoring_alerts_history`, docs/fidelity/alerts-history.md), the same
  template: r2's heartbeat episode of 21 Oct fired on no data.
- **Verdict:** a **deviation**, the one new clause: the board (version 143, revised for the
  beta label) draws no alert firing on no data. Its line is in docs/STANDING_APPROVAL_LOG.md
  ("P1 Alerts and P1-H: an alert firing on its data's absence"). No other region's verdict
  changed.

Templates sha256 before: `d566a67b55f833299f00cd8a4f28fd161db36e1b2edc376308743a21f0207a1c`.

**Compared again 2026-10-28 (PHASE8_PLAN 16.11 item 1, board FB):** `_explain.html` includes
Was this right? (`_ai_feedback.html`) under an answer drawn, after "This call in History", and
never under one Mercury's check refused. The control is board FB's and is compared in its own
record, docs/fidelity/ai-feedback.md (its two deviations logged there); no region of this record
changed, so none was shot again. Templates sha256 before:
`ce98ad506371af173a0693a2fd0f01985b178f8f3a36b1576565104a0b404b29`.

**The two compared together (2026-10-28 ~21:2x UTC):** 16.11 item 1 (the control under an
answer, `_explain.html`) and C1867 (an SDN pack's section, `_evidence_pack.html` and
`_alert_evidence.html`) were each compared alone (their paragraphs here and below; hashes
`a098e62a…` and `505f225f…`); they change different regions, and the hash above is of both
together. No region was shot again for the pair.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Heading and tabs | "Monitoring · Alerts", its line, Dashboards, Coverage, Profile, Alerts (on) | the same, with the page's (i) | **same** |
| The summary | "2 firing · 2 with their evidence pack · 0 earlier packs", the reader and its age | the same words and the reader's name | **same** |
| The filter | a box (rule, device or label) and Show | the same | **same** |
| Grouped by rule | a card per rule, its firing count; a row per device, opening in place | the same: the rule's card, "1 firing", the device's row a disclosure ("s4 · Critical syslog received · since 26 d ago, onset 26 d ago", silenced in Grafana, its pieces) | **same** |
| Explain's control | the AI mark, Explain, its (i) | the same, before the pack's sections | **same** |
| The answer, on top | the hypotheses, each with its evidence by reference and the read that confirms it; the model and cost; "this call in History"; the note that every reference was checked | the same order: the rationale, each hypothesis with "Cites alert" and "To confirm, a read: show logging \| include HEARTBEAT (Show commands)"; "needs a person"; "A hypothesis, not a finding"; "This call in History ($0.0100)" | **same** |
| The confirming read's link | "Ask the device…" | "(Show commands)", the read's own screen | **deviation** (log: P1 Alerts: the confirming read opens Show commands) |
| The evidence, one level down | each section folded under the answer, with its state, opened by a click | each section drawn open under the answer, its state chip and its pieces shown | **later** C1769 (the sections folded) |
| No fault found | the chip, the rationale, "Checked:" with its references | compared by the template and tests/test_ai_explain.py's `test_no_fault_found_is_drawn_with_what_it_checked`, not shot | **same** |
| Couldn't analyse | the refusal naming the reference the pack lacks, the call's History link | compared by the template and tests/test_ai_explain.py (C1761's), not shot | **same** |
| AI off | Explain disabled, the reason and the AI card's link; the pack whole | the same (15.13; tests/test_ai_explain.py's AI-control check) | **same** |
| Phone | not drawn | at 390 the rows and the answer stack; no sideways scroll | **same** |

**Compared again 2026-10-26 (C1778, the endpoint layer in the pack; PHASE8_PLAN 15.15):**
`_evidence_pack.html` gained the pack's ninth section, **What is attached around it, as
observed** (`endpoints`), between the observed network and the health figures. It is drawn as
every section is: its words, its ref, its state chip, its source and why; when captured, a line
saying the read and that Explain reads this capture, never a later read; and each endpoint's
name, MAC and addresses, where it was last seen and its VLAN.
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_explain`, at 1440, 1280 and 390
  beside the board at 1440, on its lab. The opened card shows the new section with "nothing to
  read", because the test alert's device is in no network's inventory, as every section there
  says. At 390 the section stacks like the rest, with no sideways scroll.
- **Verdict:** a **deviation**, the one new region: the board (version 143) has no endpoints
  section. Its line is in docs/STANDING_APPROVAL_LOG.md. No other region's verdict changed.

Templates sha256 before: `0f6077ca63250f9e09b5e169c2757681d0d88e94a4a56d37f2e375ce0f2c76a2`.

**Compared again 2026-10-26 (the alert history: each section's mark, pack schema 4):**
`_evidence_pack.html` draws each section's provenance after its state chip. On a pack built
when its alert fired, that is "captured at the time" in quiet text. On a rebuilt pack it is a
chip, "rebuilt" or "cannot be rebuilt", with its words in full under the heading. The pack line
leads with "rebuilt afterwards" on a rebuilt pack, and with "parts not marked" on one built
before schema 4.
- **Shots:** `test_monitoring_alerts_explain` (a live pack: each section's quiet "captured at
  the time"), and `test_monitoring_alerts_history` for a rebuilt pack (docs/fidelity/
  alerts-history.md), at 1440, 1280 and 390.
- **Verdict:** a **deviation** on the live pack: the board (version 143) draws no mark on a
  section. Its line is in docs/STANDING_APPROVAL_LOG.md ("P1 Alerts: each section's mark"). The
  rebuilt pack's marks are drawn on board P1-H and compared there.

Templates sha256 before: `c89f41c4bf11bad922fb68bb46e9a87531daeb85a2d68a3a94fc6bbccc70dd0d`.

**Compared again 2026-10-27 (C1849 to C1851, pack schema 5; the operator's Walk 2):**
`_evidence_pack.html` gained the pack's tenth section, **Other alerts in the network around the
onset** (`concurrent`), second, under the alert: each other alert's rule, its device (its id on
hover) or polled address, its state at the alert's time as a chip, when it started, fired and
resolved, an earlier episode of the same alert said; "N of M kept, those nearest the onset" past
the cap, and the alerts begun before the window with no resolve recorded counted. The health
section's line names whose figures it holds, in words on a rebuilt pack ("the network model as
it is now ... may differ from then") and on hover otherwise. `_explain.html` draws, under an
answer on a pack built after its alert, "The network sent with the pack is the network model as
it is now ...".
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_explain` and
  `::test_monitoring_alerts_history` (2026-10-27 01:5x UTC, at 1440, 1280 and 390 beside the
  boards at 1440). The opened card shows the new section "nothing to read: the alert history
  holds nothing yet", the shot's lab keeping none; the rebuilt pack on History shows it "read,
  nothing found" and the health line's words. At 390 both stack like the rest, no sideways
  scroll.
- **Verdict:** a **deviation**, the one new region: the board (version 143) has no other-alerts
  section and no as-now line. Its line is in docs/STANDING_APPROVAL_LOG.md ("P1 Alerts: the
  other alerts and the network as now"). No other region's verdict changed.

Templates sha256 before: `d8af8ca8c582be32c31087731006eb42e1338fd31de266dbec3081c23f07446f`.

**Compared again 2026-10-27 (C1862, Build again and the pack an answer read):**
`_evidence_pack.html` draws, under the pack line, the packs of one alert: on a pack of an older
schema than this release's, "Kept with schema 4; this release builds schema 5" and what it
lacks, then **Build again** (busy on itself, its (i)) with "Build again with this release's
evidence: other alerts, two-hop health, one id per device; the pack kept now stays", or "Cannot
be built again: <why>"; on a pack built again, "Built again from pack <id> (schema 4, built
<when>), which stays kept" and **Show it**; on the pack it was built from, a "built again" chip,
"Built again as pack <id> (schema 5, built <when>): History and Explain read that one; this one
stays kept as it was" and **Show it**. `_explain.html` draws, above the call's History link,
"Read pack <id>, schema N, built <when> as of <the alert's time>".
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_explain` (2026-10-27 02:45 UTC,
  `alerts-explain-explained` at 1440, 1280 and 390 beside the board at 1440): the answer's
  "Read pack ep-…, schema 5, built just now as of 12 d ago." under "No topology was sent", above
  "This call in History". The pack lineage regions are shot on History
  (`::test_monitoring_alerts_history_rebuild`, docs/fidelity/alerts-history.md), the same
  template. At 390 both stack, no sideways scroll.
- **Verdict:** **deviation** for the two new regions: the board (version 143) draws neither a
  pack of an older schema nor which pack an answer read. Their lines are in
  docs/STANDING_APPROVAL_LOG.md ("P1 Alerts and P1-H: Build again on a pack of an older
  schema", "P1 Alerts and P1-H: the two packs of one alert", "P1 Alerts: the answer names the
  pack it read"). No other region's verdict changed: a pack of this release's schema built
  once draws as before.

Templates sha256 before: `fe9dc84abf22ba7879d554bf3de7004d535dd8e61e68e38273f12fd863f2e47f`.

**Compared again 2026-10-27 (C1853, the operator's Walk 2: an answer kept with its pack):**
Explain's control and its answer moved from `_evidence_pack.html` into its own block,
`_explain_block.html`, which the pack includes and which Explain's answer replaces whole; the
record now compares it too. An answer is kept with its pack. The card draws the kept one when it
opens, with nothing sent, under the answer's "Read pack <id>, schema N, built <when>" line
(C1862): "kept with the pack · explained <age>", who and when on hover. With one kept, the
button is **Explain again**, with "A new call, up to $…; this answer stays." beside it.
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_explain` (2026-10-27 05:0x UTC,
  at 1440, 1280 and 390 beside the board at 1440), with a fourth state, `alerts-explain-kept`:
  the page drawn again and the card opened. Each width starts with no answer kept. In
  `-explained`, the answer just made is drawn with no kept line, and the button already reads
  Explain again with "A new call, up to $0.1076; this answer stays.". In `-kept`, the same answer
  is drawn with "Read pack ep-…, schema 5, built just now as of 12 d ago.", then "kept with the
  pack · explained just now", then "This call in History ($0.0100)". At 390 both stack, with no
  sideways scroll.

| Region | Board | Built | Verdict |
|---|---|---|---|
| A kept answer, reopened | not drawn (the board draws one answer, made now) | the answer as drawn when made, its pack named, "kept with the pack · explained just now" under it; nothing sent | **deviation** (log: P1 Alerts: a kept answer and Explain again) |
| Explain again | not drawn (the board's button reads Explain after an answer) | with an answer kept, made now or reopened, the button reads Explain again, busy as "Explaining again…", with "A new call, up to $0.1076; this answer stays." beside it, the cost the task's per-call cap | **deviation** (log: P1 Alerts: a kept answer and Explain again) |
| The answer store unreadable | a refusal in the answer's place, as Couldn't analyse is drawn | the same form: "Not explained: the kept Explain answers cannot be read (…)…; nothing was sent", in place of the answer, the button Explain again; compared by the template and tests/test_explain_kept.py, not shot | **same** |

No other region's verdict changed. A pack with no answer kept draws Explain as before.

Templates sha256 before: `3efa0c170da2bdd638f413cc4bae45c38c1d21ee46b1c36cdb5790863e74fe58`
(over the three templates compared before `_explain_block.html` was added).

**Compared again 2026-10-27 (C1896, the monitoring side, pack schema 6):**
`_evidence_pack.html` gained the pack's eleventh section, **The monitoring side over the
window** (`observer`), between the health figures and the log lines: its words, ref, state chip,
mark, source and window as every section has; a line saying whose jobs it reads ("The scrape
jobs polling the alert's device and the devices within two hops, each across all its targets;
the SNMP exporter; the host Prometheus runs on", the timeouts' source on hover); and each piece:
a job's failed scrapes of its scrapes on how many of its targets, from when to when, the most
at once of how many and when, the minutes failing and with half or more, its slowest scrape
against its timeout and its quickest failure; the SNMP exporter's jobs, retried packets, slowest
walk, refused targets and its own scrape; the collector's host's CPU busy and load (min, avg,
max, when, its usual, its CPUs) and memory available (its low and when). A pack of an older schema
says, under its pack line, that it holds no monitoring side, and Build again's words name it.
- **Compared:** by the template and tests/test_evidence_observer.py's
  `test_the_card_draws_each_piece` (the card drawn from Walk 2's captured answers); **not shot**:
  the shots (`tests/test_board_shots.py::test_monitoring_alerts_explain` at 1440, 1280 and 390)
  were held under the laptop's memory rule of 2026-10-27 (browser runs only for a test the
  change itself needs), and are owed before this record's verdict is final.
- **Verdict:** a **deviation**, the one new region: the board (version 143) has no monitoring
  side. Its line is in docs/STANDING_APPROVAL_LOG.md ("P1 Alerts: the monitoring side over the
  window"). No other region's verdict changed.

Templates sha256 before: `3efa0c170da2bdd638f413cc4bae45c38c1d21ee46b1c36cdb5790863e74fe58`.

**Compared again 2026-10-28 (the operator's decision 7, Explain's citations):** `_explain.html`
draws, under an answer's hypotheses (and under no fault found's "Checked"), a line led by the
chip **cited by Mercury**: each citation Mercury added for a device the answer named and the
pack holds but the answer cited nothing of, as "<device>, named in <the rationale or hypothesis
N>: the pack's <reference>", the reference a link to its piece, with "The model did not cite
these" on hover. The model's own citations are drawn as before, never mixed with Mercury's. A
topology id the answer wrote another way (an adjacency's ends swapped, or `topology:` before
it) is drawn as the id sent, with "the answer wrote it …" on its hover. The citations' drawing
moved into two macros in the template; what they draw is unchanged.
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_explain` (2026-10-28 ~19:0x
  UTC, at 1440, 1280 and 390 beside the board at 1440): every region as before ("Cites alert",
  needs a person, the History link, kept with the pack). The new line is not in the shot: the
  shot's first card is the syslog alert's pack, of no one device, so its planted answer names
  none. It is compared by the template and tests/test_explain_named_devices.py's
  `test_mercury_s_citation_is_kept_recorded_and_drawn_as_mercury_s` (the card through the real
  route: the line, its chip, its link, and the hypothesis's own citations without Mercury's), and
  reached by tests/v2_context.py's `_alert_evidence`.
- **Verdict:** a **deviation**, the one new region: the board (version 143) draws only the
  model's citations. Its line is in docs/STANDING_APPROVAL_LOG.md ("P1 Alerts: a citation
  Mercury added, drawn as Mercury's"). No other region's verdict changed.

Templates sha256 before: `cf2cd988031a8a10224da41e016019bf52223a3a3cb4d17208b1491467b165a7`.

**Compared again 2026-10-28 (C1867, an SDN detection's evidence):** against the revised board
`AlertsSdnEvidence.dc.html` (a copy of version 143 with parts 5 to 9 added, signed off under the
Phase 7 mode 2026-10-28; docs/STANDING_APPROVAL_LOG.md, "C1867: board AlertsSdnEvidence"; not
yet on the canvas). `_alert_evidence.html` names Mercury's own detection "SDN detection" (a chip
and its line, or "SDN detection could not be read" with why), and an SDN card or earlier pack
names its switch (DPID and controller connection), never "no one device". `_evidence_pack.html`
draws an SDN pack's head with its switch (DPID, name, connection) and the chip, its alert
section's source as "SDN detection: the alert as Mercury recorded it" (for a pack built before
C1867 too), and its `sdn` section in words: the switch line, the counts kept, then each piece
(the detection with what it measured, against what, its confidence, its effect, from and to,
and what it rests on, linked; each port's rates, drops and counts over its sample; each flow's
match as written, IPv6 addresses whole, actions, packets, bytes, age, timeouts and cookie;
Mercury's displaced flow with its response; the switch's flow granularity), each in its own box,
and the meters its flows name as the SDN reader last read them, said as not part of the pack.
The pack and earlier badges' hover names the schema and when built. A Grafana alert's pack draws
as before.
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_sdn_evidence` (new; 2026-10-28
  ~20:4x UTC, `alerts-sdn-tab` and `alerts-sdn-open` at 1440, 1280 and 390 beside
  `alerts-sdn-board-AlertsSdnEvidence` at 1440), on test_sdn_v2's lab with the unauthorised drop
  flow detected over Ryu's capture and three packs from the Lab 8 recorded cases; and
  `::test_monitoring_alerts_explain` again (every region as before). The boards folder held the
  two boards alone (the canvas's AlertsExplain and the local AlertsSdnEvidence).
- **Regions:** the tab's source line and the SDN card (part 5): **same**. The pack's head, the
  alert section's source and the device's "nothing to read" (part 6): **same**. The `sdn`
  section's switch line, counts and each piece's words (parts 6 and 7): **same**; the board's
  figures were aligned with the built wording (thousands, the granularity's order) before its
  log line. The meters box (part 7): **same**. The states (part 8): **same**, each held by
  tests/test_sdn_evidence_v2.py rather than shot. The sections folded under the answer: drawn
  open, as before (**later** C1769). Phone (part 9): at 390 every piece wraps in its box, no
  sideways scroll: **same**.
- **Verdict:** **same**; no deviation.

Templates sha256 before: `ce98ad506371af173a0693a2fd0f01985b178f8f3a36b1576565104a0b404b29`.

**Compared again 2026-10-29 (the operator's order of 2026-10-29, C2141: Mercury's
needs_human):** `_explain.html` draws, on a **no fault found** whose model answered needs_human
false while the alert's own source shows it firing, a line with the chip **needs a person**
followed by the chip **set by Mercury** and Mercury's reason in words ("The model found no fault
and did not ask for a person, but the alert's own source (…) holds it firing (…) at the alert's
time …: a firing alert whose evidence shows nothing wrong needs a person to look …"), "The
model answered no fault found and did not ask for a person; Mercury set this. The model's answer
is kept as received in History." on hover. It takes the place of "Something in the pack could
not be read.", which stays for a no fault found whose model itself asked for a person. Nothing
else in the template changed.
- **Shots:** not shot again: `tests/test_board_shots.py::test_monitoring_alerts_explain`'s
  planted answer is a hypothesis needing a person (outcome answer), which the guard never
  touches, so every region shot is as before. The new line is compared by the template and
  tests/test_explain_needs_human_guard.py's `test_the_card_draws_set_by_mercury_with_its_reason`
  (the card through the real route: the line, its two chips, its reason, its hover, and the
  other sentence absent), and reached by tests/v2_context.py's `_alert_evidence` (its no fault
  found answer is on a firing alert, so the line is drawn there too).
- **Verdict:** a **deviation**, the one new region: the board (version 143) draws no needs a
  person that Mercury set. Its line is in docs/STANDING_APPROVAL_LOG.md ("P1 Alerts: a needs a
  person Mercury set, drawn as Mercury's"). No other region's verdict changed.

Templates sha256 before: `a1813eccc97ade628667adc86e9d0d427d4590baa8e02678c6a591699bbccdfd`.

**Compared again 2026-10-29 (Explain's ship ruling of 2026-10-29, condition (b): Advisory
(beta)):** against the revised board, `AlertsExplain.dc.html` with a note "Revised 2026-10-29:
Explain Advisory (beta)" (a copy of version 143 with parts 1 to 4 revised in place and parts 5
to 9 added; signed off under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md, "Explain Advisory
(beta): board AlertsExplain revised"; not yet on the canvas). A new template,
`_explain_beta.html`, draws the label from `explain.beta()`, its figure from the one dated
record `explain.MEASURED`; it is added to the templates compared. `_explain.html` opens every
answer it draws with the whole label; `_explain_block.html` draws the chip alone after Explain's
(i) when an answer is drawn under it, else the whole label under the control.
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_explain` (2026-10-29 04:1x UTC,
  at 1440, 1280 and 390 beside the revised board at 1440; the boards folder held the revised
  board alone): `-open` draws the whole label under Explain, `-explained` and `-kept` the chip
  after the (i) with "A new call, up to $…; this answer stays." beside it and the whole label
  first in the answer, above its rationale. At 390 the label wraps under the control and at the
  top of the answer, How was this measured? on its own line; no sideways scroll.
- **Regions not shot,** compared by the template and tests/test_explain_beta.py (each through
  the real route): no fault found and no fault found with Mercury's needs a person (the label
  first, then the answer, then "needs a person" with "set by Mercury"), a refusal (no label on
  it, the whole label under its control), Not measured (a pin the record is not of), and the
  chip's hover naming every field of the record.

| Region | Board | Built | Verdict |
|---|---|---|---|
| The label on an answer | parts 1, 2 and 6: the chip, "81% of recorded cases reliable in measurement (2026-10-29, 21 cases, 10 runs).", How was this measured?, "A person should confirm.", first in the answer | the same words and order, first in the answer, the link opening the manual's section in the side panel | **same** |
| The control with an answer under it | parts 1 and 6: the chip after the (i), then "A new call, …" | the same | **same** |
| The control with no answer under it | parts 4 and 5: the whole label on the line under the control | the same, before the AI-off reason when there is one | **same** |
| A refusal | part 3: no label on the refusal; the control draws the whole label | the same | **same** |
| A needs a person Mercury set | part 6: the label, the answer, then "needs a person", "set by Mercury" and the reason | the same order (the log's earlier deviation for this region, "P1 Alerts: a needs a person Mercury set, drawn as Mercury's", is drawn by the revised board) | **same** |
| Not measured | part 7: the chip, "Not measured: Explain now asks … ; the measurement of 2026-10-29 was of …", the link, "A person should confirm." | the same words from `explain.beta()` | **same** |
| The chip's hover | part 5: the whole record in words | every field of `explain.MEASURED` in words | **same** |
| Phone | part 9: the label wraps, no sideways scroll | at 390 the same | **same** |

No other region's verdict changed. The past alert's disabled Explain (part 8) is compared in
docs/fidelity/alerts-history.md.

Templates sha256 before: `2a07a8c2be05812ce15017e868ed816db837e707f7f7cae5b2aa6b44053058f1`
(over the four templates compared before `_explain_beta.html` was added).

**Compared again 2026-10-29 (the answer card first; the operator's order of 2026-10-29, items 3
and 4a, C2172 item 3 and C2173's first step):** against `AlertsExplain.dc.html` revised again
with a note "Revised 2026-10-29: the answer card first" (the agent's copy of the beta revision,
canvas version 178, parts 1, 2, 3, 4, 6 and 9 redrawn in the card's form, 5, 7 and 8 kept, 10 to
12 new; not yet on the canvas; signed off under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md,
"Board AlertsExplain revised: the answer card first"). A new template, `_explain_ask.html`,
draws Explain's control in its two places (above the pack with no answer, and as the card's
Explain again); it is added to the templates compared. `_explain.html` draws the answer as a
card; `_explain_block.html` draws the card alone when there is an answer, else the control and
what was drawn; `_evidence_pack.html` draws each section collapsed with its count
(`evidence_pack.section_count`) and an alert's end as cleared; `_alert_evidence.html` counts the
firing alerts by kind, each a filter (`evidence_pack.tab`'s `kinds`).
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_explain` (2026-10-29 05:2x UTC,
  at 1440, 1280 and 390 beside the revised board at 1440; the boards folder held the revised
  board alone), the planted answer now three hypotheses: `-tab` (the kinds row), `-open`,
  `-explained` (the card), `-cited` (a chip pressed: the alert section opened and highlighted),
  `-kept`. At 390 the card's header label wraps under its title, Other possibilities stays
  collapsed, the foot's Was this right? and Explain again each take a line; no sideways scroll.
- **Regions not shot,** compared by the template and tests/test_explain_card.py (each through
  the real route): no fault found, Mercury's needs a person, a refusal, hosted AI off, the kinds
  at 900 alerts and their filter, and the alert states (History is compared in
  docs/fidelity/alerts-history.md).

| Region | Board | Built | Verdict |
|---|---|---|---|
| The kinds row | above the filter: "By kind:", a chip per kind with its count, most first; chosen, marked, with Every kind and "N of M firing shown" | the same, after the reader's line, a kind each rule group (`evidence_pack.family`) | **same** |
| The answer card's header | part 1: the AI mark, "Explain's answer", the whole beta label | the same | **same** |
| Most likely cause | part 1: the lead, the claim, who, the chips, the read, "Why:" | the same order and words | **same** |
| Who a hypothesis names | part 1: "Who: no record of who" on each, "added by Mercury" on one Mercury filled | drawn when the answer carries `who` (tests/test_explain_card.py plants it); the answers built now carry none, so none is drawn | **later** C2172 item 1 (who, guaranteed in code) |
| Other possibilities | part 1: "Other possibilities · 2", collapsed, each numbered | the same | **same** |
| Needs a person | parts 1 and 6: the model's reason, or "set by Mercury" with Mercury's | the same | **same** |
| The card's foot | parts 1, 2 and 6: Was this right?, then the AI mark and Explain again (secondary) with its cost, then the pack read and this call in History | the same | **same** |
| No fault found | part 2: the lead, what it found, Checked as chips | the same | **same** |
| A refusal, AI off | parts 3 and 4: no card, the primary Explain with the whole label | the same | **same** |
| The pack's sections | parts 1, 4, 5 and 9: each collapsed, its words, its count, its ref and state | the same | **same** |
| A chip pressed | part 10: its section opens, the piece highlighted and focused, by a click or Enter | the same (tests/test_ai_explain.py's real-browser walk, both ways) | **same** |
| Alert states in a pack | part 12: an earlier pack's "Cleared"; another alert firing then amber, cleared neutral | the same; pending then neutral (the board says nothing of it) | **same** |
| Phone | part 9 | at 390 the same | **same** |

No other region's verdict changed.

Templates sha256 before: `0877edf116dafadaa27e121315778120797d2b0077e37dfa697ca6d9778eb5b0`
(over the five templates compared before `_explain_ask.html` was added, as C2174 left them;
the card was first compared over `d566a67b…`, before C2174, and its paragraph's shots are of
that tree).

**Compared again 2026-10-29 (the answer card merged with "WHO, guaranteed in code", the
operator's order of 2026-10-29; C2172 item 1):** the card's region **later** above (who a
hypothesis names) is now built. Each hypothesis carries `who` as Explain computes it
(`who.who_of`): one entry per actor of each change or action it cites (a History action, a
configuration-change log line, the Intent check's difference), the model's when its claim names
the actor, else Mercury's. `_explain.html` draws each after the claim and before its citations:
"Who:", the actor and how established (or "no record of who"), the chip **who, added by
Mercury** on Mercury's, then "from" and the record as a citation chip; whose words named it on
the line's hover. A hypothesis citing no change draws none. `_evidence_pack.html` draws, under
a differing Intent check's words, "The lines, masked: N lines" and the lines (each "+ " or "- ",
one to a line), or, on an older pack, that they are on the device's Intent tab; then who last
committed the intent, or no record of who.
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_explain` (2026-10-29 06:2x UTC,
  on the combined tree: C2174, the card and WHO; at 1440, 1280 and 390 beside the revised board
  at 1440; the boards folder held the revised board and AlertsHistory), with a sixth state, `alerts-explain-who`: a deploy's receipt planted in each
  device's History (the shape History's reader returns), r3's card opened and explained with a
  planted answer whose Most likely cause cites r3's `history:1` and names no one. The card draws
  "Who: operator@example.com (verified sign-in)", the chip "who, added by Mercury", "from" and
  the `history:1` chip, then "Cites history:1". The other five states are as before (the s4
  pack's History is nothing to read, so its answer draws no Who). At 390 the Who line wraps, the
  chip on its own line; no sideways scroll. C2174's clause ("The fault is the data's absence")
  is inside the alert section, collapsed under the card in every state shot, so it is not in
  these shots; its paragraph above (shot on a tree whose sections were drawn open) and
  tests/test_no_data_is_the_fault.py hold it.
- **Regions not shot,** compared by the template and tests: the model's who (the claim naming
  the actor) and none on a hypothesis citing no change (tests/test_explain_card.py's
  `test_who_a_hypothesis_names_is_the_model_s_or_mercury_s`, through the real route), the intent
  lines and who committed (tests/test_explain_who.py's
  `test_the_pack_card_draws_the_lines_and_who_committed`; the shot's packs hold no differing
  check).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Who a hypothesis names | parts 1 and 9: "Who:" on each hypothesis, "no record of who" on those citing no change; Mercury's "dana@example.com (verified), from Mercury's receipt" with the chip "added by Mercury" | "Who:" only on a hypothesis citing a change or action; Mercury's chip "who, added by Mercury" and the record as a chip after "from" | **deviation** (log: P1 Alerts: who a hypothesis names, as WHO computes it) |
| The Intent check's lines and its last commit | the check's state alone ("Intent check · matches") | the lines masked, one to a line, and who last committed | **deviation** (log: P1 Alerts and P1-H: the intent difference's lines and who committed the intent, in the pack) |

No other region's verdict changed.

Templates sha256 before: `d993cb4d19458d23705970405811b2f466909c5ef5dab082c77eadf3af0fb235`
(the card alone, before C2174 and WHO; never on main: the card, WHO and this comparison land
together, on top of C2174, and the shots above are of that combined tree).
