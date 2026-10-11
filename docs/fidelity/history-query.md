# Fidelity: History › Query (C667, board A)

History's Query tab as built, compared region by region with its signed-off board (C650's
step). Read from shots of the board and the page side by side, in the same headless Firefox, the
page fed by the logs reader's value built from the real captures of the lab's Loki
(`tests/test_board_shots.py::test_history_query`).

Board: `AskLibrary.dc.html` (History › Query board A, "ask the history, starting from a
question", 1440 wide), signed off with boards B and C on canvas v31 (NSOT_STAGE7_PLAN 15.5 to
15.9). The board has no phone variant.
Shots: desktop 1440; phone 390 (the page held to a 390 px column, and its first screen).
Compared 2026-10-11. History's own page (heading, remote line, tabs) is board D's and is not
compared here; History stays on the fidelity check's UNCHECKED list until board D is.
Templates compared: templates/v2/history.html, templates/v2/_history_body.html, templates/v2/_history_query.html

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Tabs | Timeline, Query, Baselines, Authorisations; Query on | the same | **same** |
| Lede | "Ask the network's history. Pick a question, then a device and a time range; …" | the same words | **same** |
| What the history holds | one strip: "Metrics from 30 Aug: the last 90 days at full detail, older from the long-term store (5-minute, then 1-hour detail)"; "Logs: kept 2 years (… Logs retention, Settings)"; "Archived syslog files: kept 2 years (their own class)"; "read 2 min ago" | one strip: metrics' full-detail days from the setting, and whether a long-term store is set (else "nothing older is kept"); logs' retention from the setting and the store's first day from the logs reader; when the logs were read | **deviation** (log: the strip says only what Mercury measures; the metrics' first sample and the archive's class are not read yet) |
| Ready-made questions | six cards, each a link to its answer | the same six in the same order; Syslog by device a link to board C's page; the five not built drawn dashed, "not built yet", no link | **later** (B is the next step; the other four follow) |
| Saved by your team | saved views, one pinned, and a dashed "Ask your own (PromQL or LogQL)…" | a line saying saving a view and asking your own are the next step, nothing saved yet | **later** |
| Phone | (no phone board) | one column: the strip's parts and the cards stacked | **same** (the board's own 900 px rule) |
