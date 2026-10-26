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
Templates compared: templates/v2/_alert_evidence.html, templates/v2/_evidence_pack.html, templates/v2/_explain.html
Templates sha256: `0f6077ca63250f9e09b5e169c2757681d0d88e94a4a56d37f2e375ce0f2c76a2`

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
