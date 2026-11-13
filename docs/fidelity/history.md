# Fidelity: History (the Timeline and Baselines tabs)

History as built, compared region by region with its approved boards (C650's step), after the
operator's walk W1 (2026-10-16, steps 6, 12, 40 and 45, the last reading the whole sitting back
from it). Read from shots of the boards and the page side by side, in the same headless Firefox
(`tests/test_board_shots.py::test_history`), fed twice: first the real records of
`tests/test_device_v2.py`'s lab written as `tests/test_device_history_v2.py` writes them (r3's
golden, an intent commit, a failed and a deployed receipt, and the repository's own commits:
shot `history-real`, the same rows as r3's tab in docs/fidelity/tab-history.md); then the
browser layout test's widest timeline (`tests/test_v2_layout_in_a_browser.py`'s `_timeline`: a
denied baseline decision's long words, a nine-device golden marked known wrong, the identity
line counting 52 commits of which 11 are not verified) and its `BASELINES` (one denied and
stale, one earned). Read beside them: the operator's W1 captures 08 (the logging test's row
opened), 11 (r4's and s4's layout rows from the topology drag), 34 and 35 (the sitting's rows,
top and bottom, "Showing the newest 50 of 316"), at about half desktop width.

Boards, on the "NMAS v2 mockups" canvas, page "Coverage (built), templates, stepper, History":
`HistoryTimeline.dc.html` (board D, 1280), History as one timeline (C369), signed off
2026-10-03 and built; `History.dc.html` (1280), the earlier History board (the Commits tab,
signed off 2026-10-02 with NSOT_GUI_BRIEF 3.4), which board D superseded; and
`HistoryIdentity.dc.html` (7.5, 1440), History's identity line in its four states and the
filter it adds, signed off 2026-10-11 under the Phase 7 mode (docs/STANDING_APPROVAL_LOG.md).
The Query tab is compared in its own records: docs/fidelity/history-query.md (board A,
AskLibrary), docs/fidelity/history-metric.md (board B), docs/fidelity/logs.md (board C,
Syslog by device), docs/fidelity/history-ask-logs.md and docs/fidelity/history-ask-metrics.md
(Ask your own); History › Remote set-up is a card drawn and counted as signed off on
2026-10-10 with no board file.
Shots: board D and the earlier board at 1280, the identity board at 1440; the page at 1280,
1440 and 390, its rows closed (`history-rows`) and the newest opened (`history-open`); the
Kind menu open (`history-kinds-menu`, 1280); Show only these (`history-unverified`, 1440,
the fixture's counts unfiltered); the Baselines tab (`history-baselines`, 1280 and 390); the
real records (`history-real`, 1280).
Compared 2026-10-16.
Templates compared: templates/v2/history.html, templates/v2/_history_body.html, templates/v2/_history_remote.html, templates/v2/_history_timeline.html, templates/v2/_timeline.html
Hashed again 2026-11-11 for declared fault drills (the operator's decision of that day):
`_history_timeline.html`'s region also re-reads on `fault_drills` (a declaration made), so a
new "Fault drill declared" row appears without a reload; the kind filter gains "Fault drills
declared" under What happened to a device, from the server's table. Nothing drawn moved;
compared by the template diff, not a new shot. Templates sha256 before:
`c5934949831ac771dec940997d03f4533f00c2d1078d7ebe01bc8287a43fb728`.
Hashed again 2026-11-12 (board E2a, the gate's findings): a row's "The identity as recorded"
is drawn after the row's own record, closed, with its key (`data-keep`), where it followed the
By line; nothing else on a row moves. Compared by the template diff, not a new shot. Templates
sha256 before: `0f6b4254f0101d560cab3289ac66306ee840770edb8001d86b70eed01bbf9706`.
Hashed again 2026-11-12 (C3172, C3175: the operator's findings of that day): an opened row's
body in `_timeline.html` gains **Open the card**, above its links, for an operation's run whose
record keeps its steps (a self-healing run, a telemetry re-subscribe or re-add), opening that
run's card on its device's page (`run_href`); no board draws it: **deviation** (log: History
rows open their run's card). A self-healing row's closed "Details for the record" now draws
each person by display name, as an open record's values are; the identity stays under "The
identity as recorded". Nothing else on a row moves. Compared by the template diff, not a new
shot. Templates sha256 before:
`81d816682befcba75169984a2372e68c3fd4e3a6175670c71f8e41424d57e89c`.
Hashed again 2026-11-12 (the incident page's first slice, the operator's item 5: one place
per incident): an opened self-healing row's line of **Open the card** also draws **Open the
incident**, a link to that incident's own page (`/v2/incident/<id>`), beside the card's
button; a decision that ran nothing (no card) draws the link alone. No board of this page
draws it: **deviation** (log: Board incident-page F built for History, 1). Nothing else on a
row moves. Compared by the template diff, not a new shot. Templates sha256 before:
`c7001f001587bf7f384d82ff84c9e93321b0f2ff43d2f5b7d39f6390b672c946`.
Compared again 2026-11-13 (C3399; the operator's two notes: Grafana's no-op save bursts, and runs of identical rows, "e.g. Show commands ×25"): `_timeline.html`'s row moved into one macro, `timeline_row`, drawing exactly what the row drew before; a run of adjacent rows alike in kind, what, devices, who, outcome and marks is one closed details row in the row's own place, its line the row's words with "×N" and the first and last times through `clock`, opening to each row drawn by the same macro; a row with a commit or an AI call always stands alone; a burst of Grafana saves whose hash did not move is one `alert_rule` row ("Grafana re-saved N rules: no change to what they evaluate"). Board D draws one row per record: **deviation** (log: History: a run of alike rows is one row, ×N). No other element moves and no other region's verdict moved; compared by the template's diff and the page's render (tests/test_history_grouping.py's page tests, through the real Show commands press), not by new shots. Templates sha256 before: `60973fb243e7652053a41055f6111dc8aec542d7ab55421503190221332f2412`.
Compared again 2026-11-13 (C3290; the operator's test of 2026-11-13, "Local times FAILS on History": an alert rule change's record read "Saved in Grafana 2026-11-12T02:33:45Z"): `_timeline.html` draws a row's words, its marks, its detail, its correction and every value of its record through `people | times` (routes/v2.py), so a record's value that is an instant is `_macros.clock`'s, with its date and seconds, in the viewer's kept zone with the UTC instant on hover, and an instant inside a row's words is the clock's too. No element moves and no region's verdict moved; compared by the template's diff and the walk's render (tests/test_no_utc_drawn.py, which reads History's alert rule rows with their records), not by new shots; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times: the words Python builds"). Templates sha256 before: `5ff7225111c495223a65da35f868dc077139d5ef57861ccf448e46eb1b53e593`.
Compared again 2026-11-13 (the operator's approved rule, "no Device column on a device's own History tab"): `_timeline.html` drops the Device heading and cell only when it is drawn with a device named (`here`, a device's tab); on this page, drawn without one, the heading, the cell and the grid are as they were, and a line gains no mark. No element of this page moves and no region's verdict moved; compared by the template's diff and from new shots at 1280 (~/Documents/nmas-reports/captures/gui-overnight-2/fixes/3-history-before.png and -after.png). The tab's own record: tab-history.md. Templates sha256 before: `f14e18efb12dfb26b2894503000f7adde95aa61dff86ee161eeb056a9f6a5110`.
Templates sha256: `da28f2440497acf4cee57939c59dbe089a5b8184c9e2571a0fb61e7764eb015e`

**Compared again 2026-11-11 (board E2a, display names):** by the templates' diff against the
regions below, not from new shots. In `_timeline.html` and `_history_remote.html`, each place
that draws a person now draws them through the `people` filter, by display name (the name the
person set, else the part of their identity before the "@"): a row's who, the words of its
line and its marks, its detail, its By, who acknowledged it, an open record's values, and who
last pushed or verified the remote; the Person filter lists the same names
(`history_sources._kept`). In the same element and position, with no other word changed; where
the board draws an identity the built screen draws the name, a deviation logged once for every
screen (log: Display names: a person is drawn by display name on every screen). One element is
new: under an opened row's By, where the recorded actor holds an identity, a closed disclosure
"The identity as recorded" holding it (log: Board E2a built, 6). A self-healing row's "Details
for the record" stays as recorded. Every other verdict stands.

Compared again 2026-11-11 (the operator's sitting on the lab's hardware, 2026-11-10: "The
History record's Device column says 'fleet' instead of the switch", "the History 'What' column
readable", and the configure's record "must name its source and each value's origin ... and
give before -> after for each changed value"), by the template diff and new shots of
tests/test_sdn_switches_v2.py's and tests/test_dhcp_steer_v2.py's records at 1280 and 1920,
before and after: one region moved, an opened row's body in `_timeline.html`. An OpenFlow
configuration's row draws, above its detail, what it was built from (`_sdn_built_from.html`:
the NSOT export and its commit as links, each value with where it came from) and a list of
each value before → after; no board draws an SDN row, so there is no board region to compare
it with, and every other row is as it was (both blocks are drawn only for a row that carries
them). The Device and What columns' words changed in the data, not the template. Templates
sha256 before: `60731557c955c921ab33af47b25fe04cbc045737f5ef508178c4711cb660dc55`.

Compared again 2026-11-10 (Lab 9 B5, board lab9-sdn H), by the template diff: History's tabs
gain a fourth, **Export**, after Baselines, and `_history_body.html` draws its body
(`_history_export.html`, compared in docs/fidelity/history-export.md); board D draws three tabs:
**deviation** (log: Board lab9-sdn H built, 1). No other region moved. Templates sha256 before:
`ddabe41c00ad0c438e4f147d6e3664bcfad706e6fdf63edf870d27f780e1766b`.

Compared again 2026-11-09 (C2773), against board H's artboards C and K, by the template diff (no
new shot: tests/test_heal_change_record_download.py draws the row through the real templates):
a self-healing row, opened, whose change record was made draws **Download the change record
(.md)** (a small button-styled link, `download`, its provenance on hover) in the row's links line
after **Show the change**, for a heal to intent and an action alike; a dry run and a heal refused
before its program draw none. The board's words, **same**; its place, the incident card's head,
**deviation** (log: Board H built: Download the change record (.md) in the opened History heal
row's links line). No other region moved. Templates sha256 before:
`49d92b598bb7934177e176c424e7927e463e8e7d05cf128f9b226bddee39acfc`.

Compared again 2026-11-09 (C2817, C2809, C2823), by the template diff: the regions and verdicts
are tab-history.md's of the same date (one template, `_timeline.html`, draws both): a
self-healing row its decision ended leads with its plain line, its cause's facts first when
opened, its mark drawn on its control, its record under a collapsed **Details for the
record**; every other kind unchanged. **deviation** (log: C2817 12). Templates sha256 before:
`681ef96c7d48387383d3c9eb2c7705820ab540480cb92a4699c1b60a6aaa7fe2`.

Hashed again 2026-11-08 ~20:5x UTC for C2810, for one attribute: the timeline's foot in
`_timeline.html` carries `data-key="tl-foot"`, so the live merge keeps the foot Load more drew in
its place instead of drawing the first page's again; nothing drawn moves. Compared by reading
the diff, with no new shot. Before:
`199585e8b10a94923a907b1adaa99aff6283ad51e1e7bb0909d84fe052928a26`.

Compared again 2026-11-07 (board H's amendment, H26: the read loop's History rows), against
board H's artboard M, by the template diff (no new shot): `_timeline.html`'s kind table gains
`ai_read` ("AI read", muted; danger when the read was refused or failed), under the Kind menu's
**AI calls** (`history_sources.KIND_GROUPS`: the group's kinds are now `ai_call` and
`ai_read`). Each read an AI call asked for is one row ("AI read 1 of incident hi-…: r4 show
interfaces GigabitEthernet4: run, 1900 bytes as device state, 0 lines withheld"), opening to its
record (why, the hypothesis, the verdict and reason, the egress class, whom it signed in as, its
run on History › Reads, the bytes and sha256 sent and whole, whether it left the host) and three
links: **Open pass 1's call, which asked for it**, **Open pass 2's call, which carried it**,
**Open the read on History › Reads**. The board draws one card per analysis with its passes and
reads indented under it: **deviation** (log: Board H built: each AI read is its own History row
beside its two calls). The board's "History › Reads rd-91f2" is the link's words: **deviation**
(log: Board H built: a read's run opened by "Open the read on History › Reads"). The board's
"1.9 KiB sent as device state, masked, 0 lines dropped" is drawn in bytes and "lines withheld":
**deviation** (log: Board H built: an AI read's size in bytes, its dropped lines "withheld"). A
Show commands row (History › Reads) gains **Signed in as** in its record (C2661). No other
region moved. Templates sha256 before:
`67e2b64f6a1f5452586836766b08ff4e92c81fcc390b0e8343bf61969eabb779`.

Compared again 2026-11-07 (board H, H9's rest, C2399: a dry-run record's Right / Wrong), against
board H's artboard C and the shots `heal-mark` (1440, 1280 and 390; tests/test_board_shots.py::
test_heal_mark): `_timeline.html` draws "Was this the right fix?", **Right** and **Wrong…**
(templates/v2/_heal_mark.html) in a self-healing dry-run row, opened. The regions and their
verdicts are tab-history.md's of the same date (one template draws both): **same** words,
**deviation** (log: Board H built: Right / Wrong in the opened History row; Board H built:
Wrong… asks why in place; Board H built: no Open beside Right / Wrong). No other region of the
page moved. Templates sha256 before:
`ecd1f599966a88a880623895baffbca979ea5c7a4de363a0b121257210a48c19`.

Compared again 2026-11-05 (board H's amendment, H16's second part: History's kind diagnosis),
by the template diff: `_timeline.html`'s kind table gains `diagnosis` ("diagnosis", info), and
the Kind menu's What ran on a device gains **Diagnoses** (`history_sources.KIND_GROUPS`); a
diagnosis a person ran is one row ("Diagnosis on <device>: <runbook> (<target>): <what it
found>") on every device it read, opening to its record (hypotheses, ruled out, not checked,
its hops, its reads' runs and every step), as every row opens. Board K draws a "diagnosed"
chip under the kind Heal where the built page draws the kind Diagnoses: **deviation**
(proposed log line: "History's Kind menu gains Diagnoses"). No other region moved. Templates
sha256 before: `e7b05604308a5e4760bb53bc046f151441ded64df0d9e8fde15eb656fca08f24`.

Compared again 2026-11-04 (board H, H6: the self-healing step log and the policy identity), by
the template diff: `_timeline.html`'s kind table gains `heal` ("self-healing", info, drawn
danger when the heal rolled back, failed after sending or was interrupted), and the Kind menu's
What ran on a device gains **Self-healing** (`history_sources.KIND_GROUPS`); a heal's row
opens, as every row does, to its record: the incident, its decisions, the mode, the policy, the
program (masked) and its hash, the golden commit, the receipt, the re-check, the change record,
the NetBox journal entry, then each step. Board D draws no heal kind: **deviation** (log:
History's Kind menu gains Self-healing). The identity line (`_history_body.html`) counts a
commit made under a confirmed policy (`Actor-Verified: policy`) under its own words, muted, and
never in "Show only these"; with no other commit unverified it reads "All N commits carry a
verified identity (n by the policy a verified person confirmed)". The board's identity line
drew no policy value: **deviation** (same log line). H9 draws the step log's own screen (board
H, artboard C). No other region changed. Templates sha256 before:
`af5e85f45135f9432a225da354e46aa49d25fec8c39cb262dbf895b657923416`.

**Compared again 2026-11-03 (C2384, board H's H9):** `_history_timeline.html`'s `hx-trigger`
gained `nmas:notifications from:body`, so the timeline re-reads when a notification's delivery
is recorded (`modules/notify/delivery.py` announces `notifications`). As on 2026-10-25, the
attribute is the template's only change and draws nothing: the page and every fragment render
the same bytes but that attribute. No region's verdict changed.
Templates sha256 before: `8bdfcb069539fad0d6c111eeba65cf3591ed89e50af0cef68e93f270acbc4e9b`.

Compared again 2026-11-04 (board H, H6: the self-healing step log and the policy identity), by
the template diff: `_timeline.html`'s kind table gains `heal` ("self-healing", info, drawn
danger when the heal rolled back, failed after sending or was interrupted), and the Kind menu's
What ran on a device gains **Self-healing** (`history_sources.KIND_GROUPS`); a heal's row
opens, as every row does, to its record: the incident, its decisions, the mode, the policy, the
program (masked) and its hash, the golden commit, the receipt, the re-check, the change record,
the NetBox journal entry, then each step. Board D draws no heal kind: **deviation** (log:
History's Kind menu gains Self-healing). The identity line (`_history_body.html`) counts a
commit made under a confirmed policy (`Actor-Verified: policy`) under its own words, muted, and
never in "Show only these"; with no other commit unverified it reads "All N commits carry a
verified identity (n by the policy a verified person confirmed)". The board's identity line
drew no policy value: **deviation** (same log line). H9 draws the step log's own screen (board
H, artboard C). No other region changed. Templates sha256 before:
`af5e85f45135f9432a225da354e46aa49d25fec8c39cb262dbf895b657923416` (after H9's comparison above;
both changes are in the templates hashed at the top).

Compared again 2026-11-02 (C2268, PHASE8_PLAN 21.2 (4)), by the template and a real browser
(tests/test_live_refresh_history.py): Verify and Push now say their answer in a slot under the
remote header instead of beside the button inside it, so the header's own redraw (the push's
`remote` announcement) leaves it; the words, colour and place under the header are as before.
No region's verdict moved. Templates sha256 before:
`02da4d7d15a7e22855741baeac32c6f4ccc7562555039e508788d267cbcec518`.

Compared again 2026-11-02 (C2003, the operator's decision: the stall captures itself), by the
template diff: `_timeline.html`'s kind table gains `stall` ("page stall", danger), and the Kind
menu's Decisions and records gains **Page stalls (live updates)** (`history_sources.KIND_GROUPS`).
A row draws as every kind's; board D draws no stall kind: **deviation** (log: History's Kind
menu gains Page stalls). No other region changed. Templates sha256 before:
`5376cf9b4a43a244ea7c2aa08f36ea200ec6bab2b584d0e4597038ff2c72baee`.

Compared again 2026-11-01 (the overnight brief, item 6), by the template: the identity line is not drawn when the kinds chosen show no commit ("No commit shown (kinds: ai_calls)…" counted nothing a person could act on); with no kind chosen, or a person or device that shows none, it still says so. No other region changed. Templates sha256 before: `f8111df04f15575e2311b6fad8790f46f4e2261ac5bb52e7c31a4c7dcf73dfcf`.

Compared again 2026-10-16 (C522) after `_history_body.html`'s Baselines card gained a heading
row: the count of baselines ("2 baselines") and "How does this work?" in words (to the restore's
page, "Restore and re-apply a baseline"), C503's rule of one worded link per card; each row's
Re-apply… keeps its (i). `history-baselines` shot again at 1280 and 390 (the count and the link
on one row at both). Neither board draws the Baselines
tab's content (board D names the tab; the earlier board's Baseline column was superseded), so the
Baselines region's verdict is unchanged; no other region moved.

Compared again 2026-10-16 (C945) after `_history_remote.html` gained two states of its
uncommitted clause: "No repository yet: the network's first commit makes it." for a network
whose folder has no `.git`, and "The working tree could not be read: <git's error>." for any
other failure (it read "The working tree could not be read." for both). Neither state is on a
board or in a shot: board D draws the remote line in sync and committed. The header rendered
from the template as it was and as it is, in five states (in sync and clean, 7 and 2 paths
uncommitted, no remote and clean, ahead with a failed push): every byte the same. No region's
verdict changed.

Compared again 2026-10-16 (C957) after `_timeline.html` gained one state: a network with no
repository yet draws one muted notice above the rows, "No repository yet: the network's first
commit makes it. Until then the golden history, the intent history, the saves that measured
devices, the repository's other commits and the baseline decisions have nothing to show.", in
place of five warnings that each history "could not be read". The state is on no board or
shot: board D draws a network with a repository. The rows rendered from `timeline_rows` as it
was and as it is, in five states each with and without a device (the layout test's widest
timeline, a device's restart row, errors with a cut list, empty, empty with no repository
key): every byte the same. No region's verdict changed.

Compared again 2026-10-16 (C1016) after `_history_remote.html`'s failed Verify gained each
failed check's remedy: the line "Last verified <when> (<who>): failed:" and under it one item
per failed check, its name and detail and "To fix:" with the check's own remedy (the words the
set-up card's write probe draws), where it was one line of names and details. The state is on
no board or shot: board D draws the remote line in sync, and no shot has a failed Verify. The
header rendered from the template as it was and as it is, in six states (in sync and clean, 7
paths uncommitted, ahead with a failed push, Verify passed read-only, Verify passed with the
write probe, no remote): every byte the same. No region's verdict changed.

Compared again 2026-10-17 (C1027, the operator's B5 from W2) after `_history_remote.html`'s
chip gained the state `uncommitted` (`remote_publication.describe` now answers it, a warning,
when the working tree holds anything uncommitted, where it answered "in sync" beside "1 path(s)
are not committed", W2's screenshot 76): the chip reads "not committed" in warn. The state is on
no board or shot: board D draws the remote line in sync and committed. The header rendered from
the template as it was and as it is, in six states (in sync and clean, in sync with 7 paths
uncommitted as the old `describe` drew it, ahead with a failed push, no remote, Verify passed,
and the new uncommitted state): every byte the same but the new state's chip ("not pushed" as
it was, "not committed" now). No region's verdict changed.

Compared again 2026-10-17 (C1030, the operator's B8 from W2) after the timeline gained a NetBox source: `_timeline.html`
draws its kind as "NetBox" in words, and a failed or partial NetBox row in danger, as every
other kind's failure; `_history_timeline.html` redraws on the `netbox` key, so an import that
lands while the page is open appears. The kind menu gains "NetBox imports and removals" under
Decisions and records (`history_sources.KIND_GROUPS`, not a template). No board or shot draws a
NetBox row: board D's kinds predate it, as do the other kinds recorded since (the Kind menu's
deviation). The rows rendered from `timeline_rows` and the card as they were and as they are,
for 648 rows (every kind drawn before, each with eight outcomes and three marks, half with a
device, with an error line): every byte the same, but the card's `hx-trigger`, which gains
`nmas:netbox from:body`. No region's verdict changed.

Compared again 2026-10-17 (C1089) after `_timeline.html` gained one kind, Mercury's Grafana
writes: "Grafana" in words (muted), and a write Grafana refused in danger, as every other kind's
failure; the Kind menu gains "Grafana writes" under Decisions and records
(`history_sources.KIND_GROUPS`, not a template). No board or shot draws a Grafana row, as none
drew a NetBox row (the Kind menu's deviation). The rows rendered from `timeline_rows` and the card
with the template as it was and as it is, for 672 rows (every kind drawn before, NetBox now
among them, each with eight outcomes and three marks, half with a device, with an error line):
every byte the same. No region's verdict changed.

Compared again 2026-10-17 (C1136) after `_history_remote.html` gained, under the header's row,
a list of the uncommitted paths (the first five) each with what it is and what clears it, by
the folder it is in (a golden: Capture as golden; intent: the device's Intent tab; a template:
Templates' Edit…; Mercury's own record: the network's next commit; anything else: changed
outside Mercury on the host), as today's Git tab said until it left at 7.8 (P7-21). The state
is on no board or shot: board D draws the remote line in sync and committed. The header
rendered from the template as it was and as it is, in seven states (in sync and clean, in sync
with 7 paths uncommitted, the uncommitted state, ahead with a failed push, no remote, Verify
passed, and uncommitted with two paths described): every byte the same but the last, which
gains the list (its chip unchanged, "not committed"). The remote line's region reads
**deviation** as before (its log line names the set-up and these additions).

Compared again 2026-10-18 (the operator's walk of 2026-10-18, B: r2's last golden, 6 days old,
sat behind daily Save All rows, and was reached only by scrolling this page) after three
changes. `_history_body.html` gained, under the filters, the Kind choices one click away: a
segmented row, All, Goldens, Intent, Deploys and restores, Measured, unchanged, Restarts, each a
link keeping the device, person and time filters, the chosen one pressed
(`history_sources.QUICK_KINDS`; the reader keeps the kind before its newest-N cut). The Kind
menu gained Goldens and Intent under The repository (data, `history_sources.KIND_GROUPS`).
`_history_timeline.html` draws a filter it did not apply as its own notice above the rows, "Not
applied: the kind filter 'bogus' is not a kind History records" (a device or person that is not
a name the same way), where a device that was not a name had been drawn among the stores that
could not be read, ending "the timeline below lacks it". None of it is on a board: board D draws
the Kind menu only. The page rendered on test_device_v2's lab from the templates as they were and
as they are: Baselines, Query and the timeline fragment every byte the same; every kind, commits
for one device, and a device filter that is not a name differ only by the Kind row and that
notice. No shot was retaken: Firefox could not start in the runner where this was compared
(tests/test_v2_layout_in_a_browser.py skipped), so the row's wrap at phone width is the
stylesheet's (`.seg.hist-quick` wraps within its width), not measured. One region added, The
Kind choices; The Kind menu's Built amended; no other region's verdict changed.
Templates sha256 before: `6a448609b62db7fda7b875e667b98cb6db107e60b70f8bfdcac9a7e5b505d35d`.

**Compared again 2026-10-25 (Phase 8's 8.0b):** `_history_timeline.html`'s `hx-trigger` gained
`nmas:ai_calls from:body`, so the fleet's timeline re-reads when an AI call is recorded (the AI
card's Test; `modules/invalidation.py`'s `ai_calls`). The attribute is the template's only change
(`git diff` of the five templates: that one line), and it draws nothing: the page and every
fragment render the same bytes but that attribute. The new kind, AI calls, is data
(`history_sources.KIND_GROUPS`), drawn as every kind is. No region's verdict changed.
Templates sha256 before: `cdffbb36d100c038f4ab2da4ed517c128a34e590facd3d74e5b8629b5e0afd3c`.

**Compared again 2026-10-26 (PHASE8_PLAN 15.14, the operator, 2026-10-26: "the exact wording
of the prompt that was given and the exact structured response from the AI when expanded,
similar to how device configuration changes have a window in their history record"):**
`_timeline.html` changed in three ways:
- An AI call's opened row gains "Show the prompt and the answer". It fetches
  `/v2/history/ai-call/<id>` (`_history_ai_call.html`, new) into its own full-width line
  under the row's links.
- The window shows only what the row's record lacks: Most tokens out, Thinking, and why the
  answer stopped, in words. Under "Sent to the model" it shows each part of the request as it
  left the host:
  - the instructions;
  - each context and data block, by its name, in the commit change's `pre.hist-diff` box,
    wrapped (`.hist-ai .hist-diff`), the bytes unchanged;
  - a part over 4,000 characters folded, with its size.

  Under "Received" it shows the answer, laid out for reading.
- The kind is drawn as "AI call" in words, no longer its code name `ai_call`. A call whose
  verdict is not ok (cut off at max_tokens, refused, or not in its schema), or whose answer
  its feature refused, is drawn in danger, as every kind's failure is.

No board draws an AI call: the kind is later than board D.

Shot `history-ai-call` (`tests/test_board_shots.py::test_history_ai_call`, on
tests/test_ai_explain's world: Explain's real request and a planted answer) at 1280 and phone
width, the row closed and then opened and pressed.
- The first shot measured the opened page at 10,634 px wide. The window was a flex item of
  the links row, which grows to its content, so one long line of a context block widened the
  page. It is now `.tl-window` (full width, `min-width: 0`).
- The page then measured 1,268 px at 1280 and 488 CSS px at phone width, with no horizontal
  scroll.
- The commit change's window sits in the same kind of span, and a long diff line would widen
  the page the same way: registered, not changed here.

Rows without a call render as before, but for the separator after a row's last device link,
which is drawn only when a commit follows (a call's window now starts its own line).
"An opened row" amended; no other region's verdict changed.
Templates sha256 before: `5da74570cc50f940ed61bf6c098fcf28cb900e83af3272c0d135a809e8abf9c8`.

**Compared again 2026-10-26 (15.14 part B; the operator, 2026-10-25: "Load more … by a keyset
cursor on the time and the id … Jump to date … the cursor and the filters live in the URL"):**
four templates changed.
- `_timeline.html`: each row carries its id (`id="<row id>"`, an AI call's its own `ai-…`),
  its windows keyed by it (`diff-<id>`, `rv-<id>`) so the rows Load more appends never share
  one; under the last row a foot holds **Load more** (a small button, "Loading…" and disabled
  while its answer is out), or "No older record than these.", and, when a store that can give
  only its newest rows could not be read far enough back, one muted line naming it. An AI
  call's opened row gains "Open what it produced" (its last use row's page and anchor).
- `_history_timeline.html`: the count reads "Showing the newest 50 of 316 read · Load more, at
  the foot, reads the next 50"; at a place, "Showing the 50 before <stamp>" (or "on or before
  <day> (UTC)") with Back to the newest; `?call=<id>` reads "One AI call, <id>, opened" with
  Every AI call and Every record. Its redraw now keeps every filter, `identity` included
  (it dropped it), and the place.
- `_history_body.html`: the filter bar gains **Jump to** (a date field) after Since, one
  height with the others (tests/test_v2_layout_in_a_browser.py's filter-bar check, which now
  measures it); the Kind choices and the menu's Every kind and Commits only keep the day.
- `_history_ask_words.html` (Query's builders): the filled notice's "(model, $x" gains ",
  this call in History)" (docs/fidelity/history-ask-metrics.md, history-ask-logs.md).

Board D draws "Showing the newest 12 of 41 · Show more" beside the filters, and no foot: Show
more there (and as built until now) asked for twice as many rows from the top. As built, the
count stays at the card's head and Show more is replaced by Load more at the foot, which
appends the next rows under the last one read, so a person reading down meets it where the
rows end; the board draws no date control, no paging place and no AI call. The board shots
were taken again before the commit (`test_history` and `test_history_ai_call`, the three
boards beside the page at 1280, 1440 and 390): Jump to sits in the filter bar after Since,
the card's head says "Showing the newest 2", and its foot "No older record than these.".
Load more was also clicked in Firefox (tests/test_history_paging.py, `TestInABrowser`): busy and
disabled while held, 50 rows appended to 100 and then 120, each once, "No older record than
these." at the end, the place pushed into the address and Back returning to it, and no
horizontal scroll at 390 px. "The count" amended and a region added, Load more and Jump to;
no other region's verdict changed.
Templates sha256 before: `476c427c7071d5b88678e04045e8954423620a7c0b85d75224812b5613d9b35a`.

Compared again 2026-10-26 (feature 7's part 2, links both ways): `_timeline.html` draws, on an
opened commit row whose commit carries an `AI-Call:` trailer (an intent change drafted in words
and committed by a person), "Open the AI call that drafted it", to that call's own row
(`/v2/history?call=<id>`), before Show the change. Board F7 draws it (1d, canvas version 146);
History's own boards draw no AI-drafted commit. Its test is tests/test_ai_intent_change.py's
`test_a_draft_commits_with_its_trailers_and_the_links_both_ways` (the device's History tab,
the link and the call's id drawn). No shot retaken: the link is one anchor in the row's links
line, as drawn on F7; no other region moved. The hash written again.
Templates sha256 before: `a0d4d6854fb30fe0bb8e5b4f8d153807e1665a1c507d80ad3f6c30cd0f383683`.

Compared again 2026-10-26 (C1775, AI call ↔ intent commit ↔ deploy receipt): `_timeline.html`
draws, on a deploy's receipt row whose receipt names the intent commit it deployed, "Open the
intent change it deployed", and on an intent change's row "Open its deploys", each to
`/v2/history?commit=<sha>&since=` (that commit's row and every receipt naming it);
`_history_timeline.html` heads that view "Commit <sha> and the deploys that sent it: N rows,
among the newest 50 of each record" (a subset, said). The receipt's record gains "Intent
deployed": the commit, "not recorded" for a receipt from before C1775, or a restore's "none".
Board F7 draws them (1d, canvas version 148). Tests: tests/test_ai_intent_change.py's
`test_a_deploy_receipt_records_its_intent_commit_and_history_links_both_ways`. No other region
moved; the hash written again.
Templates sha256 before: `9c14e0f3676722b4540f3ef2954553a814a48fcc1bb2084e6dc5569e9f83cfb5`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | History, after Devices | the same, current | **same** |
| Heading | "History" (the identity board adds the (i) beside it) | "History" and its (i); the network's one line under it ("Default: what happened to the network and its devices, and when", capture 08) | **same** |
| The remote line | "in sync", "Everything is committed and pushed to the remote (checked 1 min ago)"; Push now and Verify the remote at the right | the state's chip and the remote's own sentence (`remote_publication.describe`: "in sync … and pushed to <repo> (checked 1 min ago)" in capture 08), its (i), Remote set-up… and Verify the remote with its (i); Set up the remote… when none is set (the shots); Push now when something is unpushed (the template) | **deviation** (log: Board: History › Remote set-up) |
| Tabs | Timeline, Baselines, Authorisations (D); Timeline, Baselines, Authorisations, Query, Remote (the identity board) | Timeline, Query, Baselines; the remote is the card above | **deviation** (log: History's Authorisations tab left its page with C708 (2026-10-12)) |
| Filters | Device ("Any device, and the fleet"), Person ("Anyone"), Kind, Since; Show on the identity board | the same four and Show (capture 34); every filter in the address, so a view is a link | **same** |
| The Kind menu | "Every kind except 2": the kinds in two columns under The repository, What ran on a device, What happened to a device, Decisions and records, Retries authorised and Freshness authorised off; Every kind · Commits only | one column under the same four headings, every kind by default (none ticked is every kind); the kinds recorded since (Privileged commands, Reloads, Credential profiles, Expected islands, Topology layouts, Saved views, Reveals, Show commands) in their groups, Freshness authorised not a kind; Goldens and Intent each its own kind under The repository, beside Commits (2026-10-18); Every kind · Commits only | **deviation** (log: History: the Kind menu) |
| The Kind choices | none: the Kind menu is the only way to a kind | under the filters, one segmented row of links: All, Goldens, Intent, Deploys and restores, Measured, unchanged, Restarts; each keeps the device, person and time filters and the page's network, the chosen one pressed; the kind is kept before the newest-N cut, so a golden older than the newest page is found; a kind not known is not applied and said by name above the rows (the operator's walk, 2026-10-18, B; tests/test_history_kind_filter.py) | **deviation** (log: History: Kind choices one click away, Goldens first, the operator's walk of 2026-10-18) |
| The count | "Showing the newest 12 of 41 · Show more" beside the filters | at the head of the timeline card, "Showing the newest 50 of 316 read · Load more, at the foot, reads the next 50" when more are older (the shape of capture 34's "Showing the newest 50 of 316 · Show more"); at a place, "Showing the 50 before <stamp>" or "on or before <day> (UTC)", with Back to the newest (15.14 part B) | **deviation** (log: History: Load more by keyset and jump to date (15.14 part B)) |
| Load more and Jump to (15.14 part B) | not drawn: Show more beside the count | under the last row, Load more (busy on itself, "Loading…"), appending the next 50 older than the last shown in place and pushing the page's address with that place (`before=<time>~<id>`), every filter kept; "No older record than these." at the end; a store read only by its newest rows that a page could not reach named under them; Jump to, a date field in the filter bar after Since (`on=`); one AI call by `?call=<id>`, opened (tests/test_history_paging.py) | **deviation** (log: History: Load more by keyset and jump to date (15.14 part B)) |
| The identity line (7.5) | "41 of 52 commits in this window carry a verified identity (signed in through the access proxy)", chips 8 host login, 3 not verified, 0 before verification was recorded, Show only these 11 | the same words and chips ("39 of 62 commits … 16 host login, 7 not verified, Show only these 23" in capture 34), a kind with no commit not drawn (no "0 …" chip); Show only these wraps under the line at 1280 | **deviation** (log: History: the identity line draws no empty chip) |
| The identity line's other states | all verified in ok colour; a filter set says what is shown; no commit says so, never "0 of 0"; Show only these with Show every identity | the same four (the template; `history-unverified` shows the last, its counts the fixture's, unfiltered) | **same** |
| Rows | When, Kind, Device, What, Who; one line each | the same five; When as a v2 stamp with the UTC time on hover; a disclosure mark before each row; a long What cut with "…" on its one line (the layout rows, capture 35) | **same** |
| Kind | a chip per kind in words | the board's kinds in words; a kind recorded since and not in the chip table is drawn by its code name, and "show_commands" is cut to "show_comman" by the column (captures 08, 34, 35; C901) | **deviation** (log: History: a kind's chip shows its code name, cut to "show_comman" (C901)) |
| An update's colour | an "update" chip in the kind's own colour; red only for a failure | a successful update ("The app updated to <sha>: updated") is drawn red: `_timeline.html` reads any update outcome but "confirmed", "done" and "ok" as a failure; it was the sitting's only red row (capture 35; C901) | **deviation** (log: History: a successful update drawn red (C901)) |
| What | the record in words, its detail faint after " · " | the same; an intent edit made on v2 reads "Intent committed (extraction)" (C895), a rotation writes "rotated persistence not attempted" before "rotated and persisted" (C896), and a Save All adds a "persist" row per device under its own (C898; captures 34 and 35) | **deviation** (log: History: an intent edit on v2 reads as an extraction (C895)) |
| A decision and a known-wrong record | "decision", "baseline earned" with its tag; "corrected" on a persist | "decision" with the decision's words, its Baseline field in the opened row; " · record known wrong", its note in the opened row | **same** |
| An opened row | under the row at full width: who and how identified, via what, how long; the run's stages; Open r3's History · The commit | the detail and the commit's sha, By the person as identified, the record's fields (Run, Devices, Outcome for the logging test in capture 08), Show the change, Open <device>'s History for each device of several, and on a golden row "A golden is a record of what the device ran …" and Reveal <device>'s version…; on an AI call (15.14), the call's record (About, Prompt, Schema, Model, Tokens, Cost, Verdict, Then) and Show the prompt and the answer, which opens its window on its own line: the request's bound, thinking and why the answer stopped, each part sent and the answer received (`history-ai-call`), and Open what it produced, its last use row's page and anchor (15.14 part B) | **deviation** (log: History: an opened row's links) |
| How a row's person was identified | the identity board's table puts "host login" as a chip after the person in Who | in the opened row ("By … (host login, not verified)"), as the board's note says ("as today, in the expanded row") | **deviation** (log: History: how a row's person was identified) |
| The fleet's own records | rows with no device read "fleet"; a commit is one row naming its devices | the same; but a golden commit that also writes a path outside `golden/` and `host_vars/` (here r3's first, which adopts it into the manifest) is drawn twice, as r3's golden and again as a fleet commit, "golden: 1 device(s) via capture" (`history-real`) | **deviation** (log: History: a device's first golden drawn again as a fleet commit (a defect, register C650 follow-up)) |
| The earlier board (History.dc.html) | a Commits tab; a Workflow filter; a Baseline column; Re-apply this baseline… under a Save All | superseded by board D: Commits a kind (Commits only), Workflow folded into Kind, a baseline decision its own row; Re-apply… on the Baselines tab | **same** |
| Baselines | its own tab (board D: "Baselines and Authorisations keep their tabs") | headed by the count and "How does this work?" (C522); one line per baseline (tag, taken, earned, can be re-applied, Re-apply… with its (i)), why it was denied or withdrawn and what it claims opened under it, "Judged … in the background"; the walk's step 40 re-applied the newest from it | **same** |
| Query | board A's library (compared in docs/fidelity/history-query.md and its sibling records) | the same records | **same** |
| Phone | no phone board | the filters wrap to a second line, the identity chips wrap, each row's cells stack | **same** |
