# Fidelity: Settings › Installation › Notifications (2026-11-03)

Board: `heal-to-intent.html`, artboard B (1440), docs/boards/heal-to-intent.html, approved by the
operator 2026-11-03 ~19:5x UTC (docs/STANDING_APPROVAL_LOG.md, "Board H approved by the
operator: heal to intent (Lab 10)"). Its yellow callouts are notes for the builder.

Shots: `tests/test_board_shots.py::test_notifications` (`notifications` at 1440, 1280 and 390:
the relay set with its password, a team of two addresses, one verified and one with its code
waiting, and a verified webhook whose last delivery failed with HTTP 503 from a fake receiver),
beside the board's shot from `test_heal_tab` (`heal-tab-board-1440`, artboard B). The states the
shots do not draw (each form open, a refusal, a code typed, an edit to a new URL, a removal's
question) are compared by the templates and tests/test_notify_v2.py.
Templates compared: templates/v2/_notify.html, templates/v2/_notify_relay.html
Templates sha256: `93b7f828057f8c217d4e955526425de4e19b6c3c77a3c8c9cb9970a411b448b8`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it is | Notifications, the last of Installation's tabs, after a General tab | Notifications, the last tab; no General tab | **later** (board TZ's General tab, C2314) |
| The subtitle | "These settings apply to every network. Each network's Self-healing tab chooses which team it tells." | the page's own subtitle, with the board's second sentence on this tab | **same** |
| The three cards | Email relay, Webhooks, Teams across | the same three across where they fit, stacked at phone width | **same** |
| The relay's head | "last sent 18:31 UTC" | the same, or "nothing sent yet", "last failed …" or "off: no relay" | **same** |
| The relay's fields | host, port, Security, username, password, From | the same, each with its note, and Mercury's address for links (notify_link_base, so a message's link opens) | **deviation** (log: Board H built: the relay card adds Mercury's address for links) |
| The password | "set 3 Nov by operator@example.com, never shown", Replace… | the same; Replace… opens a password field with Store it and Cancel in the card | **same** |
| Save, Test send to…, How does this work? | the three | the same; Test send to… opens a choice of the teams' addresses, never a typed one, with Send the test | **deviation** (log: Board H built: Test send to… picks one of the teams' addresses) |
| The relay's note | "Uses the relay you choose…" | the same | **same** |
| Add a webhook… | the button | the button, opening team, name, URL, format and signing secret, and Add and send a code: a webhook is verified by a code as an address is | **deviation** (log: Board H built: a webhook is verified by a code before use) |
| A webhook's row | a table: name over its masked URL, format, last, Test send · Edit… · Remove… | each row stacked in the card: name and team, the URL as scheme and host then "/…", format, last delivery with its error, then the three actions | **deviation** (log: Board H built: a webhook's row stacked, its URL drawn as scheme and host) |
| The formats | four named | Generic, signed built; Slack-, Teams- and PagerDuty-compatible drawn as later and refused | **later** (C2387, after Lab 10) |
| The failure note | three tries, then Needs attention; each attempt in History | the same, as the card's note | **same** |
| Teams: Add a team… | the button | the same, opening the name and Add the team | **same** |
| A destination's row | the address, its chip (verified, code sent), Verify with Send again, Remove | the same chips and code field; a verified one has Turn off or Turn on; Remove… asks first, saying the delivery log rows stay | **deviation** (log: Board H built: Turn off or on, and Remove… asking first) |
| Add an address | the field and Add and send a code | the same | **same** |
| Told about | "Default (from its Self-healing tab)" | each network that chose the team, linked to its Self-healing tab | **same** |
| The delivery log | the link | the same, to History filtered to notifications | **same** |
| The bottom note | the builder's note, and the product's two sentences | the product's sentences, with the code's 15 minutes | **same** |
