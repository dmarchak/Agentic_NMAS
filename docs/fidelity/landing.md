# Fidelity: Needs attention (the landing page)

Needs attention as built, compared region by region with its signed-off boards (C650's step),
after the operator's walk W1 (2026-10-16, steps 1, 34, 37, 39 and 44, which kept it open in its
own tab for the whole sitting). Read from shots of the boards and the page side by side, in the
same headless Firefox (`tests/test_board_shots.py::test_landing`), on the browser layout test's
lab (tests/test_profile_apply.py's: r2's real configuration as its golden and its parsed intent),
with the management section proposed and `_common.j2` committed as the shipped version from
before P1 (tests/test_template_bring.py's stale lab, so C566's row is raised by the real
`template_behind_source`), and every other source as the payload check's provider builds it
(`tests/payload_providers.needs_attention`: job health over the systemd and journal shapes
measured on the host, a real drift run, an approval, an overdue onboarding, a rollback block, a
failed deploy, a denied baseline, an authorisation and a source that raises). Two receipts (a
deploy and a refused restore) written through the real receipt store. The test store's readers
never ran, so job health adds a row per reader: the shot holds 44 rows, where the board draws 5;
the regions are what is compared. Read beside them: the operator's W1 capture 01 (one Warning
row, the host step for 99664f2792, "1 item · 25 sources checked", Recent changes with five
deploys), at about half desktop width; and captures 32 to 35, whose top bar carries Update
available.

Boards: on "NMAS redesign mockups", page "Landing, devices, device" (signed off 2026-09-29,
NSOT_GUI_BRIEF section 13): `redesign/Main.dc.html` ("Needs attention (landing)", 1440),
`redesign/LandingPhone.dc.html` ("Phone: Needs attention", 390) and `redesign/NavPhone.dc.html`
("Phone: the sidebar as a drawer", 390). On "NMAS v2 mockups": `BrandSidebar.dc.html` (page
"Mercury: the name and the mark", board A, approved 2026-10-05), `KnownNoise.dc.html` (page
"C534, Needs attention: known noise", approved 2026-10-06) and `C566Coverage.dc.html` (page
"C566: a profile change reaches the device on v2", board C, approved 2026-10-07; its Needs
attention row only, the rest is Coverage's). Not compared, marked FOR SIGN-OFF on the canvas
and with no sign-off in docs/STANDING_APPROVAL_LOG.md or the register (C589 and C537 still read
"drawn for sign-off"): `AdjacencyTransient.dc.html` (C589), `TopBarDesktop.dc.html` and
`TopBarPhone.dc.html` (C537 A and B).
Shots: `landing-board-Main-1440`, `landing-page-1440` and `-1280`, `landing-evidence-page-1440`
and `-1280` (What was checked opened); `landing-brand-board-*-1440` beside `landing-brand-page-1440`;
`landing-dark-page-1440`; `landing-phone-board-LandingPhone-390` and `-NavPhone-390` beside
`landing-phone-page-390` and `landing-phone-drawer-page-390` (the menu button clicked).
Compared 2026-10-16.
Templates compared: templates/v2/landing.html, templates/v2/_attention.html, templates/v2/_recent.html, templates/v2/_heal_analysis.html, templates/v2/_attention_recheck.html
Templates sha256 then (local times' included): `6bd7a689cdf2a7a2164120e15e5288b691024e5160e11a14e545fd50c26e8440`

**Compared again 2026-11-12 (local times, docs/UI_RULES.md "One time zone per screen"):** in `_attention.html` and `_heal_analysis.html`, a row's "Clears when … (by …)" time, a Grafana silence's end, Seen before's times and the can't-fix analysis's call time are `_macros.clock`'s: the viewer's own time, the zone named once on the screen, the UTC instant on hover, in the same element and position; a row's words that Python builds keep theirs (C3290). Compared by the templates' diff, not a new shot; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times"). Templates sha256 before: `a2dd9064dceffd54c29c58dc5ebbf1d8d2ac264232a504fd19a344edfb08be0c`.
Templates sha256 then (local times and Run the check again): `38c26a97b54f9e8d8b31d716a193a6ab3e99c32696d9fd6480c32c3c484baeb5`
(Run the check again's fix alone hashed `697ab1d52342ff21f6d78b0fc1bfb166e0b03f2d6820692592cc3b0c189d9cb7`;
this is the set over local times, which touched `_attention.html` too.)

**Compared again 2026-11-13 (the operator's test of the incident page: "A drill's incident
says so"):** in `_attention.html`, a self-healing item about a declared fault drill's incident
draws a "Drill" badge after its **Open the incident**, its hover naming the drill's `fd-` id;
every other item, and the link itself, as compared. The board draws the chip on the incident's
page beside its title: **deviation** (log: Board incident-page B built, 10). Compared by the
template diff and the row tests/test_incident_page.py draws, not a new shot. This slice's edit
alone, over the templates as committed, hashed
`1298bcc70c44306e39f2a8d7e01d7f20c7e0bde6591d436e936a33e3ebcdf3ae`; the hash below is over the
working tree, which also holds the concurrent local-times edit to `_attention.html` (its
`filter times`), compared by its own build.
Templates sha256 then (the drill's badge): `599e34d6a47e6570e6fe341723c2940402076a9e79d1438f2b9bd23e1c3a7940`

**Compared again 2026-11-13 (the operator's test of Run the check again, C3401: "the message
pushes the button onto a new line. The button never moves"; docs/UI_RULES.md, "No control
moves when its own result appears"):** in `_attention.html` and `_attention_recheck.html`,
**Run the check again** is first on the opened row's Details line and pinned to that line's
right (it ended the line, after "· read <age> · <source> ·"), so the age's words, which a press
shortens ("read just now"), never move it; every answer (a refusal, "Checked just now", a
failed check) is drawn below the button, never beside it; and busy it is as wide as idle (its
idle words hidden in the same cell). Words, states and every other region as compared. Board
NA-R draws no such control (the logged deviation, "Needs attention: Run the check again on a
row's Details line"); its place on the line is a further **deviation**, logged
(docs/STANDING_APPROVAL_LOG.md, "Needs attention: Run the check again pinned to its line's
right"). Compared by the template diff and the real-browser test tests/test_recheck.py
(`test_the_button_never_moves_when_its_own_answer_appears`, at 1280 and 390), not a new shot.
Templates sha256 before: `599e34d6a47e6570e6fe341723c2940402076a9e79d1438f2b9bd23e1c3a7940`.
Compared again 2026-11-13 (the operator's approved rules, "raw UTC anywhere left" and "money shown as $"; C3290): `_attention.html` draws a diagnosis hypothesis's claim and next step through `times` (routes/v2.py), and `_heal_analysis.html` its hypothesis's claim the same way and its call's cost through the `usd` filter (`modules.money.usd`, an exact amount). No element moves and no region's verdict moved; compared by the templates' diff, not by new shots; logged once each (docs/STANDING_APPROVAL_LOG.md, "Local times: the words Python builds" and "Money through one formatter"). Templates sha256 before: `bc35314f80a3fcc76b47e556d6bcafee68460faae9b61a34c483e276635bd667`.
Templates sha256: `002adf75ada9ae050b329769aea42c4cebfec0019d93f17c8c4b1e20baa713c7`

**Hashed again 2026-11-12 for Run the check again's two findings** (the operator's test of item
2 on the NMAS host; C3360, C3361). The control's span now carries its row's id and
`data-live-part`, so one press leaves one control after its answer and after the list's live
redraw; and a press answered by a read the person did not start says, in the same place,
"Checked just now (HH:MM): still found" (or "no longer found", or "the check failed: …"), or
is busy on itself while a run it joined ends. Place, words of the idle and busy control and
every other region as compared; the control was already a logged deviation of board NA-R
(docs/STANDING_APPROVAL_LOG.md, "Needs attention: Run the check again on a row's Details
line"), and these are its states, no new region. Compared by the template diff and the real
browser test tests/test_recheck.py presses, not a new shot. Templates sha256 before:
`a2dd9064dceffd54c29c58dc5ebbf1d8d2ac264232a504fd19a344edfb08be0c`.

**Hashed again 2026-11-12, the same day, at the merge:** Run the check again posts to
`/v2/attention/recheck` (`v2.attention_recheck`) where it posted to `/attention/recheck`: a
press on the person's own page is a v2 route (tests/test_no_new_v1_capability.py). The control's
words, place and states are unchanged. Templates sha256 before:
`5d1ec52d7685515e31844b44ea3c13194009d3b21cd48ac32075d0b55952735d`.

**Hashed again 2026-11-12 for Run the check again** (the operator's overnight item 9: "A fix
made through Mercury re-runs the check that raised its row; the row offers 'Run the check
again'"; C3240). An opened row whose reading is a background check's ends its Details line
("since … · read <age> · <source>") with **Run the check again** and its (i), drawn by a new
macro, `templates/v2/_attention_recheck.html`, now compared with the rest: pressed, it is
**Checking…**, disabled and busy on itself, until the list is drawn again with the fresh
reading; a refusal ("Not run again: …", both operands) or a failed run ("The check failed …")
is said beside it, in place. The row's one line, What to do and every other region are as
compared; a row from a source read for every page draws nothing new. Board NA-R draws no such
control: **deviation**, logged in docs/STANDING_APPROVAL_LOG.md ("Needs attention: Run the
check again on a row's Details line"). Compared by the template diff and the page
tests/test_recheck.py draws and presses, not a new shot. Templates sha256 before (the four
templates then compared): `cdc42b110331edb52496d05e40f8dc7fa880f5325088ba594b86209cf946f070`.

**Hashed again 2026-11-12 for the background store** (C3166 slice 1; the operator's rule that
day: "every page draws at once from data the background already holds, shows each source's age
("checked 20 s ago") … there is no refresh button"). `_attention.html` draws the value the
background holds: the summary line gains "checked <age>" (when the list was assembled) and, when
older, "the oldest <age>" (its oldest source's read), each a stamp with its time on hover; a
source whose refresh failed adds "N refresh(es) failed, the last value kept: <sources>" to it,
and on its own line in What was checked "Its refresh <age> failed (<why>): what is shown is its
last good value"; What was checked gains a Checked column, each source's read time, between
Value from and Rows. Before the first value lands the list is one busy line, "Reading Needs
attention… Its sources are read in the background; this fills itself when their first value
lands." The list listens for the store's own announcement (`attention`), this page's own
acknowledgement, a hold's start and end, and a display name's change. The incident link below
is as it was compared. Every other region as compared. Compared by the template diff and the
pages tests/test_attention_store.py draws, not a new shot; board NA-R draws none of the three:
**deviation**, logged in docs/STANDING_APPROVAL_LOG.md. Templates sha256 before:
`917d18b106b382b9924d5debc6825594552a2398f0674aa6e6eb1d4b88d54508`.

**Hashed again 2026-11-12 for the incident page's first slice** (the operator's item 5: "so
the email and Needs attention link to one place per incident"). `_attention.html`: a
self-healing item about one incident (its record names an `hi-` id) ends its Why this
happened with **Open the incident**, a link to that incident's own page, beside the row's one
action and never a second one; every other row as compared. No board of this page draws it:
**deviation** (log: Board incident-page F built for Needs attention, 1). Compared by the
template diff and the row tests/test_incident_page.py draws, not a new shot. Templates sha256
before: `17d74797f049ce151f7f797f8e1f9624f70d1b8468238d122106b29c0a0a6e8f`.

**Hashed again 2026-11-12 for a heal's row in Recent changes** (the operator, that day: "A heal
reads "Heal r3 · by Mercury's self-healing""). `_recent.html`: a heal's receipt is drawn "Heal
<device> · <outcome> · N lines re-applied", by Mercury's self-healing, the policy's setter by
display name after it, N its configuration lines (never the `exit` closing a sub-mode); every
other row as compared. Compared by the template diff and the rows tests/test_deploy_receipts.py
draws, not a new shot; logged in docs/STANDING_APPROVAL_LOG.md. Templates sha256 before:
`b5e4bf34a6fb63674c7eefe797e6dbdf6a2ff6d0b6cc9af559d99531e8d71617`.


**Hashed again 2026-11-11 for a lost stream's severity** (C2970; the operator, 2026-11-10:
"Severity follows impact on service, not 'something broke'… Fix it in the provisioned Grafana
alert rule (its severity label), not by overriding it in Mercury's display"; 2026-11-11:
"Approved, for the video: C2970, telemetry loss is a WARNING while the device answers (escalate
only by folding). Build and gate it."). `_attention.html` gains two lines under a lost stream's
lead sentence, whether its device answers (`fx.answers`, amber when the reading cannot say or
the device missed its last probes) and, one line, what Mercury cannot see until the stream is
back (`fx.unseen`); and one block after What to do, drawn only on the row lost streams on
several devices make: "N devices under this item", each device's own row inside it, closed,
drawn by the same row markup (the row loop is `recursive`). The level's badge and section are
the ones compared: a lost stream's row is now in Warning, by its rule's label. No other row
moves. Board NA-R draws no row inside a row: **deviation**, logged in STANDING_APPROVAL_LOG
("Landing: lost streams on several devices are one Warning row with each device's row under
it"). Compared by the template diff and the rows tests/test_lost_stream_severity.py draws, not
a new shot. Templates sha256 before:
`f073f50f12f58170494dcc643d68a952868ed410565a443d18e457760ce5132e`.

**Hashed again 2026-11-11 for recorded closes** (the operator, that day: "The seven host-step
rows have no action, against our own rule. Add a recorded way to close one"; and for the
scheduled mutation run, "an acknowledge with reason and expiry"; log: Recorded closes).
`_attention.html`: a host step's row draws Open the Update page on its line, with its (i),
where it drew nothing, and in What to do in place of Update…; and the Acknowledged list draws
an acknowledgement with a declared expiry (a scheduled job's failed run) as "Acknowledged by
<name> until the next scheduled run (<when>): <reason>" (`said`). Every other row and every
other acknowledgement is drawn as compared. Compared by the template diff and the rows
tests/test_host_step_decline.py and tests/test_scheduled_job_acknowledge.py draw, not a new
shot. Templates sha256 before: `d4fbaddf4bfdb61a68112f162ffe3c47465a59ea162bd464dce8256424dc9441`.

**Hashed again 2026-11-11 after the operator's test of the held actions on the host** ("2. A
Needs attention row with a run in progress: the run's text on a SECOND line under the title;
only 'Open the run' on the right."). `_attention.html`: a held row's line draws the run's
words on a second line under its title (`held_run`), once on the row, and its right side
Open the run alone (`held_open`); under What to do, "Offered again when the run ends." and
Open the run. A row whose device is not held is drawn as compared. Compared by the template
diff and the rows tests/test_held_actions.py draws, not a new shot. Templates sha256 before:
`0ad1f5c974e4dba68c71ba13fae5b59ab3c4b7c247b691127b4ba296cb1b8596`.

**Hashed again 2026-11-11 after the operator's test of the first slice on the host** ("1. On a
Needs attention card, the last run is ONE line, collapsed by default: 'The last run, 3 h ago:
re-subscribed; the stream did not come back · 12 steps · Show'. Expanded on click. The full
detail stays on the result card."). `_attention.html`: a can't-fix row's steps taken are one
closed line under the cause, "The steps Mercury took: stopped at <step> · N steps · Show",
the stepper inside it (where the hash of 2026-11-11 below drew the stepper open); and the
held row's "Open the run" takes its address from the one macro that builds it (`run_href`,
`_macros.html`), the same address as before. Nothing else on a row moves. Compared by the
template diff and the row tests/test_run_outcomes.py draws, not a new shot. Templates sha256
before: `8dc969d036f434576a2ac665d0a3c0f84c1aac1f0b4c67b46df31516ad3c21fe`.

**Compared again 2026-11-11 (board E2a, display names):** by the templates' diff against the
regions below, not from new shots. In `_attention.html` and `_recent.html`, each place that
draws a person (who read or asked for Mercury's diagnosis, who runs one now, a Grafana
silence's author, who acknowledged a row, who made a recent change) now draws them through the
`people` filter, by display name (the name the person set, else the part of their identity
before the "@"), in the same element and position; the rows' own words, which their sources
write naming people by identity, reach the page through the same filter over the page's model
(`routes/v2._attention`). No region is added, removed or moved, and no other word changes.
Where the board draws an identity the built screen draws the name, a deviation logged once for
every screen (log: Display names: a person is drawn by display name on every screen). Every
other verdict stands.

**Hashed again 2026-11-11 for a held device's actions** (the operator, that day: "While a
device is held by a run, its actions must be disabled, saying 'running since <time>, by
<who>', with a link to the run."). `_attention.html` gains a macro, `held_line`, and one
branch in each of the two places a row's action is drawn (its one line, and What to do): a row
whose action opens an operation on a device a run holds now (`in_flight.mark_held`, read per
request from the hold the server refuses by) draws "<run> running since <time>, by <who>" and
**Open the run** in the action's place, and its action again once the hold ends (the list
also listens for `device_holds` and `in_progress`). A row whose device is not held is drawn as
compared; nothing else in the row moves. Board NA-R draws no held device: **deviation**,
logged in STANDING_APPROVAL_LOG ("Landing: a row's action is drawn as the run while a run
holds its device"). Compared by the template diff and the rows tests/test_held_actions.py
draws, not a new shot. Templates sha256 before:
`aeefc80da2b2d0f7510c64fa2a85b40d35ea660f048dad0ba98077bb638b1345`.

**Hashed again 2026-11-11 for the operator's request of that day** ("Every operation and heal
ends with a visible outcome on its card and under 'Finished' (success / partial / failed, with
the steps taken)"; Lab 10's item (b), "when it can't, notify an engineer with the steps
taken"). `_attention.html` gains one line, in an opened row's **Why this happened**, after the
cause: a self-healing can't-fix row (`attention._heal_cant_fix_rows`, `steps_taken`) draws
**The steps taken** on the one stepper (`_run_stepper.html`): the decision's steps, the one it
stopped at first, each with its state in words. No other row carries `steps_taken`, so no
other row moves; the steps stay under Details for the record as well. Board NA-R keeps a
record's steps under Details only: **deviation**, logged in STANDING_APPROVAL_LOG ("Landing: a
self-healing can't-fix row, opened, draws The steps taken"). Compared by the template diff and
the row tests/test_run_outcomes.py reads, not a new shot. Templates sha256 before:
`99803edad84391646e26be2eb567997783534c563c3cf45f7b3503205507599b`.

**Hashed again 2026-11-11 for the fix-it path** (board recurring-fixes, text only, self-signed
under the Phase 7 mode 2026-11-10: its step 1, the notification, and step 2's fallback, built
without Explain), compared by the template diff against the board's words (no shot: the board
is text; tests/test_seen_before.py draws the row through the real app on the worked example's
times). `_attention.html` gains one block, first in an opened row whose action is
`resubscribe` (`attention.stream_fix`): the lead sentence with the measured time, **Seen
before on <device> (when)** when a past loss matches (or that it could not be checked), **Does
it need you?**, and **Mercury's diagnosis** with when it was read (read, not made, absent or
unreadable), above What to do; and a macro that draws a record's moment for the viewer's zone.
Every other row is unchanged. The deviations are one line of the approval log ("Board
recurring-fixes built 1"). Templates sha256 before:
`4023bd656a6003a1a9cda804c7e3801a05d752a6194ab1ab3194a56b23e755ed`.

| Region | Board | Built | Verdict |
|---|---|---|---|
| The row's one line (step 1) | title · Needs you · since Nov 8, 21:30 UTC (37 h) | its severity, title, age and Re-subscribe…, as board NA-R draws every row; "Needs you" and the 37 hours are the opened row's sentences | **deviation** (log: Board recurring-fixes built 1) |
| The lead sentence (step 1) | "<device> has sent no telemetry to the collector for 37 hours. Monitoring for <device> is blind until it does." | the same words, the time measured from the alert's onset to the reading; the subscriptions named when not every stream of the device is lost; a reading past its promise said as the past | **same** |
| Seen before (step 1) | when it was seen, "fixed by hand on the console, by removing and re-adding the receivers. That fix held 31 minutes", Open that incident | when it was seen, what was lost and for how long, how it ended from what a record shows (a Mercury operation with its record; a configuration change in the device's log with its time; by itself), how long that held from the alert's clear, Open that incident | **deviation** (log: Board recurring-fixes built 1) |
| Seen before, a store unread (step 1's rule) | not drawn | "couldn't be checked: <why>", never read as never seen | **deviation** (log: Board recurring-fixes built 1) |
| Does it need you? (step 1) | "Yes: the fix changes <device>'s configuration, so a person approves it. If you don't, <device>'s telemetry stays lost." | the same words; for a device two networks hold, that no operation is offered and where the reason is | **same** |
| Explain (steps 1 and 2) | the button, busy on itself | not drawn: there is no Explain in this build (the row's kept Explain answer from Monitoring is unchanged) | **later** (the board's steps 2 and 3, By Nov 13: Explain's history retrieval and checked citations) |
| Mercury's diagnosis (step 2's fallback) | under "Couldn't explain: <why>", the finding in words, then Re-subscribe… | drawn directly above What to do: the finding in the record's words with when it was read and by whom, what it says to do next, then Re-subscribe… | **deviation** (log: Board recurring-fixes built 1) |
| Mercury's diagnosis, none (step 2's fallback) | not drawn | absent, not made and unreadable each said as itself; no control on the row runs the diagnosis | **deviation** (log: Board recurring-fixes built 1) |
| A source that can't be read (step 1's failure state) | "Couldn't read Grafana's alerts: <why>" with Read again | the source's own row, "Grafana alerts could not be read", with its reason; no Read again | **deviation** (log: Board recurring-fixes built 1) |
| Details for the record | under the row | what matched and why, what was searched, how each sentence was measured, in the row's collapsed record | **same** |

**Compared again 2026-11-10 for C2838** (re-subscribe a lost telemetry stream), by the template
diff (no new shot; tests/test_heal_resubscribe_v2.py draws the row and its card through the
real app): `_attention.html` gains one branch, for a row whose action is `resubscribe` (every
member a lost-stream rule of one device, `attention.resubscribe_action`): **Re-subscribe
<device>'s telemetry (<ids>)…** on its line, which opens the row to its card, drawn in What to
do when the row is opened (`templates/v2/_resubscribe.html`, read from committed intent), and,
for a device two networks name, the reason it is not offered. The boards draw an alert row's
action as Read the rule in Grafana: one deviation, logged ("C2838 1"). Every other row's line
and What to do are unchanged. Templates sha256 before:
`efb6c6240f451997636916e359ccba78cc0cbbac0fcf5fa20dff3d5d30c887e3`.

| Region | Board | Built | Verdict |
|---|---|---|---|
| A lost telemetry stream's row (C2838) | an alert row: Read the rule in Grafana | Re-subscribe <device>'s telemetry (<ids>)… on its line, its card in the opened row | **deviation** (log: C2838 1) |

**Compared again 2026-11-09 for C2817 and C2823** (the operator's three templates, "right as
drawn", 2026-11-09; ~/Documents/nmas-reports/2026-11-08T2000Z-human-readable-mocks.md), by the
template diff against the mocks' rows (no new shot: tests/test_heal_said.py and
tests/test_human_readable.py draw each row through the real app). `_attention.html` gains, for
self-healing's rows: a dry-run record's **Was that right?** on its line and its Right and
Wrong… in place (on a drift row it attaches to too); a can't-fix's **Open <device> (likely
cause)** first on its line and in What to do, with its hypothesis sentence; the cause's facts
under Why this happened, each at its time in the viewer's zone; and Acknowledge…'s field
asking for the cause. For every row, Details ends with its operands under a collapsed
**Details for the record**, after the devices, since and source. Each deviation from the
boards is logged ("C2817 1", "C2817 9", "C2817 11", "C2817 13", "C2817 14", "C2817 15"). Every
other row's line and What to do are unchanged. Templates sha256 before:
`fe0010daa9ae3bd8365f51182c2e91368365988467fd78ce124e001fd639f3fe`.

| Region | Board | Built | Verdict |
|---|---|---|---|
| A Tier 2 proposal's row (C2817) | Warning, "A fix waits for a person: …" (board H, artboard D) | Critical, "<device>: <what changed>. Mercury has a fix that restarts <process> on <device>: it needs your decision" (mock 1) | **deviation** (log: C2817 1) |
| A dry-run record's row (C2817) | board H's dry-run record on the device's History, marked there | its line plain (mock 2), Was that right? on it, Right and Wrong… in the opened row; no Open <device>'s History (a next step that only navigates) | **deviation** (log: C2817 9) |
| A mark, drawn again (C2809) | a grey line under the record | the answer chosen selected on its control, who and when beside it | **deviation** (log: C2817 10) |
| A can't-fix's row (C2817) | "Self-healing could not fix r1 …" with Open r1 | its line plain (mock 3a); Open <device> (likely cause) first where another device's open change is the likeliest cause, its hypothesis sentence in What to do | **deviation** (log: C2817 11) |
| Why this happened, a heal row (C2823) | the cause in Mercury's words | the decision's facts, each at its time, then a likely cause labelled as a hypothesis, then what Mercury did or would do | **deviation** (log: C2817 2) |
| Details for the record | the operands drawn open under Details | collapsed, last in Details, after the devices, since and source | **deviation** (log: C2817 13) |
| Times | not drawn | a self-healing record's times in the viewer's zone, UTC on hover | **deviation** (log: C2817 14) |
| Acknowledge…, a can't-fix | "Why this needs nothing more" | "The cause, if you know it (recorded with your name)" | **deviation** (log: C2817 15) |
| Every other row | Main.dc.html's rows | unchanged | **same** |
| A row's Details | alerts, since, source | unchanged above the record's disclosure | **same** |

**Compared again 2026-11-09 for C2824** (the operator, 2026-11-09: a change from outside
Mercury that broke something is never offered Capture), by the template diff (no new shot):
`_attention.html`'s What to do gains one branch, for a drift row whose action is
`drift_back`: **Put it back to intent…** (the device's Deploy card) and **Keep it: add it to
intent…** (its Intent tab, the editor open), each with its (i), in place of Capture <device>…
and Deploy intent to <device>…. The row's line draws its title as before ("r6 was changed from
outside Mercury, and something broke at the same time"), and its What to do label the two
actions in words. The boards draw a drifted device's row with Capture and Deploy intent only:
one deviation, logged ("C2824 1"). Every other row's line and What to do are unchanged.
Templates sha256 before: `89f6d0227bcdb1fd109a193d41838b9278c7af6dca1683404327d39ffe6be905`.

| Region | Board | Built | Verdict |
|---|---|---|---|
| A drift row whose change from outside Mercury broke something (C2824) | a drifted device's row offers Capture and Deploy intent (Main.dc.html's drift row) | Put it back to intent… and Keep it: add it to intent…, no Capture | **deviation** (log: C2824 1) |

Hashed again 2026-11-08 ~20:5x UTC for C2810, for one attribute: each row of Recent
(`_recent.html`) carries `data-key`, its stable key, which the live merge matches rows by;
nothing drawn moves. Compared by reading the diff, with no new shot. Before:
`a3b22694cd06df92af9d318cc7a10438d648711f6f7ecd3208a5ea3948d260e3`.

**Compared again 2026-11-07 for H26** (board H's amendment, artboard M's right column: the
analysis as the can't-fix row shows it), by the template diff (no new shot): `_heal_analysis.html`
gains, for an analysis that asked for reads, the loop's own words and a link to its first call
("AI analysis: asked for 3 reads; 2 run, 1 refused; second pass answered (History)."), and its
provenance counts its calls ("2 background calls …") and says a second pass carried the reads'
masked answers as device state. The board's "Asked Mercury for 3 reads: 2 run, 1 refused
(History). 2 background calls, $0.06." is drawn in the step log's words: **deviation** (log:
Board H built: the can't-fix row's reads line in the step's words). An analysis that asked for
none draws no such line, as before. Every other region is unchanged. Templates sha256 before:
`8b5c78abad06c3d87b1f3f0461ff83f9beb9b172fbab9dd0fa66baba569f88be`.

**Compared again 2026-11-07 for H17** (board H's amendment, item 1: 19.3's "the incident's step
log shows it ... with the list expanded"; artboard J's result, artboard L's notice): a
can't-fix row, opened, gains **Mercury's diagnosis** after Why this happened and before the AI
analysis (the order artboard L's notice gives: Mercury's facts, Mercury's diagnosis, the
analysis): its chip, the runbook, who ran it, its reads and devices, each hypothesis whole with
its strength and layer, what was ruled out, where it stopped, and a link to the device's History
with its (i); or that it is running, not made (its words), unreadable, not yet recorded on an
Alert incident, or not run by itself on a Never one (Diagnose… on the row runs one). No artboard
draws the row's own diagnosis block: one deviation, logged ("Board H built: a can't-fix row
draws Mercury's diagnosis in its own section"). Compared by the template diff (no new shot;
the walk's provider in tests/v2_context.py draws its done state). Every other region is
unchanged. Templates sha256 before:
`e6fb7548c903598671015aad67f1425cc912bca4de5d2f1f50a1eb075951df46`.

| Region | Board | Built | Verdict |
|---|---|---|---|
| A can't-fix row's diagnosis (H17) | not drawn on the row: artboard L draws Mercury's diagnosis in the notice, artboard J as Diagnose…'s result | its own section, "Mercury's diagnosis", between Why this happened and the AI analysis, each state said | **deviation** (log: Board H built: a can't-fix row draws Mercury's diagnosis in its own section) |

**Compared again 2026-11-05 for H16's second part** (board H's amendment, artboard I's
callout: "A can't-fix row on Needs attention carries Diagnose… too, the Never tier's
included"), by the template diff: `_attention.html`'s What to do gains, on a row carrying
``diagnose`` (`diagnose_page.from_incident`, the can't-fix rows only), **Diagnose…** with its
(i) and a line saying what it opens ("An adjacency is down" on the interface the incident's
alert named, toward the adjacency's other end, "Can't reach" toward a device unreachable, or
the dialog on its first choice), or "Diagnose… is not offered: <why>". Artboard I draws the
control by its callout only, so the placement after the row's own action is read from board
E's What to do: **same**. No other region moved. Templates sha256 before:
`fc12fb9529ab2d1cc5834c26c0da7a598e3b2a6b8480c2e421d1d1690eac7087`.

**Merged again 2026-11-04 ~20:2x UTC (H8 onto C2471):** H8's can't-fix branch and the halted
row's branch of `_attention.html` were compared apart; the merged template holds both,
unchanged, so the record compares the four templates at the merged hash. Before, on main:
`d6301a5476e7a4684fa8be5951377ae48448dd93db30252d4b08c3f7f182639b`.

**Compared again 2026-11-04 ~17:3x UTC for board H's artboard E, its second row** (C2471): a
halted network's row ("Self-healing halted on <network>: <why>") offers **Lift the halt…** on
its line, which opens the row to its reason and **Lift the halt**, drawn under What to do from
the row itself (`templates/v2/_heal_halt.html`, its own record docs/fidelity/heal-proposal.md).
Every other row's line and What to do are unchanged: the template gains a branch taken only by
a row whose action opens a halt. Compared from `heal-halt-page-1440`, `-1280` and `-390`
(tests/test_board_shots.py `test_heal_proposal`) against artboard E's second row. Templates
sha256 before: `eff778625a86abed48102a468b6c1bccf3194d45bde349d15de15637fbd1553e`.

**Merged 2026-11-04 ~17:5x UTC** (H8's branch, at
`c1bed3687f3c5361fb4a92557c11e33b4e63ceacd2daa91fbd16a606609f9f6e`): H8's record (below, ~02:5x) and artboard E's (~09:0x and
~16:4x) were compared apart, each on its own branch of `_attention.html`; the merged template
holds both branches, unchanged, so the record compares the four templates at the merged hash.
H8's before: `70b3222f713900b746caca142b7451d05955f61939e3bed7a460137604131e5d`; artboard E's:
`eff778625a86abed48102a468b6c1bccf3194d45bde349d15de15637fbd1553e`.

**Compared again 2026-11-04 ~16:4x UTC** (C2448's gate): Review the fix… gains
`data-next-acts="heal_proposal"`, the opener tests/test_next_steps_act.py holds every next step
to. An attribute nothing draws: no region moves, so no shot was taken again. Templates sha256
before: `e95e8e52736b0c4616a046c93cff2f49a8d52b0e2a6afc014fe316449ad8a3d8`.

**Compared again 2026-11-04 ~09:0x UTC for board H's artboard E** (H9, C2448): a self-healing
proposal's row ("A fix waits for a person on <device>") offers **Review the fix…** on its line,
which opens the row to the proposal's card, read when the row is opened and drawn under What to
do (its own record, docs/fidelity/heal-proposal.md). Every other row's line and What to do are
unchanged: the template gains a branch taken only by a row whose action opens a proposal.
Compared from `heal-proposal-page-1440`, `-1280` and `-390` (tests/test_board_shots.py
`test_heal_proposal`) against artboards D (the row's line) and E (the row opened). Templates
sha256 before: `4befa3244b1c2b8057d53182059c8f99649351766efd702aeff0b7fc8553ce4d`.

**Compared again 2026-11-04 ~02:5x UTC for board H's H8** (the AI analysis of a can't-fix,
docs/HEAL_TO_INTENT.md section 12; artboard D): an opened item whose row carries an incident's
analysis (`heal_analysis`, the `heal`/`cant_fix` row) draws, after Why this happened (Mercury's
facts, written by code), an **AI analysis** block loaded when the item opens
(`routes/v2.attention_heal_analysis`, `_heal_analysis.html`): what the analysis kept with the
incident, advisory, its label and score, the rationale, each hypothesis with its next step, or
its state in words (pending, not run, couldn't analyse, the provider not answering); opening it
sends nothing. Every other row is unchanged. Compared by reading the template against
artboard D's order (What to do, Mercury's facts, then the analysis), held by
tests/test_heal_analysis.py (the route's read, its states) and the v2 walk
(`_attention_heal_analysis`). Artboard D draws the analysis inline in the opened row; built,
it is its own block under its heading, loaded on open as Explain's is (board NA-R): a
**deviation**, logged in docs/STANDING_APPROVAL_LOG.md ("Board H, H8: the can't-fix row's AI
analysis loaded on open"). `_heal_analysis.html` joins the templates compared. Templates
sha256 before: `4befa3244b1c2b8057d53182059c8f99649351766efd702aeff0b7fc8553ce4d`.

**Compared again 2026-11-03 ~02:0x UTC for C2316** (the operator's rule for acknowledgements):
a band row's Acknowledge… form (an adjacency logged down, a chronic alert's series) gains one
choice beside the reason, "Until something new happens" or "A planned quiet period: N hours" (1,
2, 4, 8 or 24), and the acknowledged list draws a quiet period's expiry after the entry's band.
Every other row's form is unchanged. Compared by reading the template against board NA-R's row
and its acknowledgement (the board draws the reason alone), held by the v2 walk
(`_attention_quiet_period`) and tests/test_adjacency_log.py. One deviation, logged in
docs/STANDING_APPROVAL_LOG.md ("C2316's quiet period on the Acknowledge… form") and PHASE8_PLAN
19.1. Templates sha256 before: `1bcf40900190f3394b9572f8f4e214a3b52f54b08c1b17edd8ab89e28bfa5ab0`.

**Compared again 2026-11-03 ~00:5x UTC for C2315** (the operator's walk: "not recorded" read
as missing data): a row whose source records no start reads "start not tracked" in its corner
(its hover saying the source does not record when the condition began) and "its source does not
track when it began" in its meta line, where it read "not recorded" and "since not recorded";
a row with a start is unchanged. Compared by reading the template against board NA-R's row (its
corner holds the row's age), words only, no new shot; held by tests/test_needs_attention.py.
Templates sha256 before: `10aa2b6726730fcd537fdf48ec07d48dfe073805ae3906229d6a155b51af9942`.
(2026-11-02, NA-R part 2: an opened item says Explain, loaded from its alert's evidence pack,
or Why this happened, its cause written by code; compared from `nar-opened-page-1440` and the
real-browser test. Before: `e2f39caecee390c1c5bdd3cac33910682d347eec95247ca7fe5b68c45412361f`.)
(2026-11-02: the spend panel's control on a row's line carries its operation and How does this
work?, as its twin under What to do does; nothing else drawn changed.)

Compared again 2026-11-02 (board NA-R, `AttentionRedesign.dc.html`, approved 2026-11-01;
PHASE8_PLAN 20.6, part 1): `_attention.html` draws a collapsible section per severity, its
count in its heading, each item one line (severity, title, age, primary action) opened to What
to do, then Details; the summary counts by severity and links an operation's expected effects
to its card; Acknowledged is its own section. Shots (`test_landing_nar`): `nar-board-
AttentionRedesign-1440` beside `nar-page-1440` and `-1280`, `nar-opened-page-1440` and `-1280`
(the first critical item opened), `nar-phone-page-390` and `nar-phone-opened-page-390`. The
regions are in "Board NA-R" below; the earlier boards' regions for the row's anatomy now hold
one level down. Templates sha256 before:
`505bb09711857f1fe45631860f26fd10adb4198abd2c94458d8249c739818d84`.

Compared again 2026-11-01 (C2295), by the template: the Acknowledge… form of a row whose kind
asks a disposition (lines withheld as instructions) draws a choice before the reason (a true
positive, benign or a test, a false positive); every other row's form is unchanged. No board
draws an acknowledgement's disposition: **deviation**, logged in STANDING_APPROVAL_LOG. No other
region changed. Templates sha256 before:
`a8f86222680902c3742e7568e77154241c0b2e7841a9a88e9263798354604b87`.

Compared again 2026-10-28 (C2056): `_attention.html` gains one branch, for an action whose
`open` is `ai_spend_panel` (an AI spend row): "Open the spend panel", an outline button with its
How does this work?, opening the top bar's spend panel in place, and on a background feature's
row Settings › AI's "Open…" beside it as before. Compared by the template and a new shot,
`ai-attention-page-1440` (docs/fidelity/ai-spend.md, where the AI rows' region is held against
board AI2): the row's level, heading, cause, operands, meta and "Clears when …" lines are the
shape every row has; only the control is new. No region's verdict here changed.

Compared again 2026-10-19 (C1388): the Acknowledge form's answer is drawn in place at once. A
recorded acknowledgement closes the form, saying "Acknowledged.", and offers neither
Acknowledge… nor Cancel again; the row leaves at the list's next redraw. No answer within 6 s
closes the form, saying in amber that whether it was recorded is not known and that the next
redraw shows it. Cancel is drawn only on an open, unsent form. The form's hold marker reads
`data-editing="false"` once answered or closed. Compared by the template and the page
tests/test_live_redraw_keeps_form.py draws in a real browser, not a new shot: the change is
the words under the reason box and one button's visibility. The KnownNoise board draws the
button and the reason box, not what a sent form shows, so the answered states are a new
region, a deviation (below). No other region's verdict changed.

Compared again 2026-10-18 (C1277): a Grafana incident's members (`ops.members`, the list under
a row's operands) now draw, on each member a silence covers, "; silenced in Grafana by <who>
until <YYYY-MM-DD HH:MM> UTC (“<comment>”)", the words "silenced in Grafana" in bold and the
comment escaped, or "by silence <id>, whose author and end Grafana did not return" for a
silence Grafana's list did not return; and on every member its onset and the basis for it
("; onset 18 d ago (when the condition first held)"), as today's panel drew both. On hover: the
member's fingerprint, Alertmanager's start, where its device came from and the silencing ids;
the silence's id and matchers. Compared by the template and the page
tests/test_grafana_reader.py's `TestASilenceStaysARow` draws through GET /v2/attention, not a new
shot: the change is words inside a row's members list. The row's heading and cause already said
"(silenced in Grafana)" and the silence in words before this change; no board draws a member,
so the member line is a new region, a deviation (below). No other region's verdict changed.

Compared again 2026-10-17 (C1189, W4): Recent changes moved, byte for byte, from `landing.html`
into its own part, `_recent.html`, so it re-reads itself when a deploy or restore announces
(`nmas:deploy_job`); drawn once at the page's opening, it had read "No deploy or restore
recorded" on a page open before two deploys while the list above it drew them. Compared by the
template text, not a new shot: the card's markup is identical but for its opening tag, which
gains `id="recent"` and the re-read's three attributes (`hx-get`, `hx-swap`, `hx-trigger`), none
drawn; `landing.html` lost the card and its two macro imports and includes the part. The part
joins this record's templates, so a later change to the card is held here. No region's verdict
changed.

Compared again 2026-10-16 after C543 and C544 changed `_attention.html` (an unsaved deploy's
row opens Persist with its network; the rolled-back row draws Revert intent… and Retry with a
reason… as two links): the rolled-back row's region rewritten; no other region's verdict
changed.

Compared again 2026-10-16 (C493): the row's meta line names each device's network ("tw-a in
Branch", "r1 (Branch or Default)" for a name two networks hold), and each Open <device> link
carries the device's network. Compared by the template and the page the tests draw
(tests/test_attention_names_networks.py), not a new shot: the change is words in the meta line
and link addresses. "A row" rewritten, a deviation logged; no other region's verdict changed.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | Main: an "N" square, "NMAS", no OBSERVE heading; BrandSidebar (later, approved): the Mercury mark beside "Mercury" over "Network Automation Platform", OBSERVE and SOURCE OF TRUTH headings | BrandSidebar's lockup, the gap in the sidebar's colour; OBSERVE (Monitoring, Topology, Show commands, Logs) and SOURCE OF TRUTH (Templates, NetBox, DHCP, Credentials), Help and Settings at the foot (capture 01) | **same** (as BrandSidebar, which supersedes Main's) |
| Sidebar, dark | BrandSidebar: the sidebar darker, the mark's teal unchanged | the same (`landing-dark-page-1440`; the operator's dark theme in capture 01) | **same** |
| Needs attention's count | a red pill on the entry with the number | the count, coloured by the worst row's level ("1" amber in capture 01); while the count is being read it shows "…" in the pill (C901) | **deviation** (log: Landing: the sidebar count shows "…" while it is read (C901)) |
| Top bar | Network picker, "Go to device by name or address", Integrations 6 of 7 with Grafana down, Live, Assistant, the person | the picker, "Go to device by name", the integrations strip, the live dot, the theme menu, the person; no Assistant | **deviation** (log: Landing: the top bar carries no Assistant) |
| Top bar with an update waiting | not drawn | "Update available" added before the strip, and at half desktop width the strip is cut to "Integrations 9 of '" and the person's name cut short (captures 32 to 35; C901) | **deviation** (log: Top bar: Update available truncates Integrations and the person (C901)) |
| Page head | "Needs attention" with an "Info" link, the sub line | the same heading and sub line; the help is the (i) beside the title, as on every v2 page | **same** |
| Summary | "5 items · checked 11 sources at 23:40", right-aligned | "1 item · 25 sources checked" under the sub line (capture 01), naming any source that could not be read; each row carries its own read time | **deviation** (log: Landing: the summary names what could not be read, each row its read time) |
| A row | level, what, cause, then the device link, since and the source's detail; the one action as a button at the right | level, what, cause, the operands, any attached finding ("Also: …"), device with its network ("r1 in Default", C493), since, read time and source, and "Clears when …"; the action under it (capture 01). The operands can be a source's raw words: "check:" with nothing after it and "state: not_checkable" in capture 01, a pasted exception in the walk's RIP rows (C893) | **deviation** (log: Landing: a row carries its operands and how it clears) (log: Landing: a row names each device's network, C493) |
| A row's action | one button named for the act (Persist s1…, Resolve r2…, Push now, Read again) | Open <device> for each device named, the action's words, and a button where the action has a control on v2 ("Open the Update page and say it is done", Update…, its (i), capture 01); a command with Copy where the remedy is a host command | **deviation** (log: Landing: an action is its words, with a button only where v2 has its control) |
| A Grafana incident's members (C1277) | not drawn: a row is its level, what, cause and action | under the operands, each member alert: its rule and kind, its device and where the device came from, its onset with the basis, and on a silenced member "**silenced in Grafana** by operator@example.com until 2026-09-30 10:15 UTC (“send log 2 test &lt;b&gt;”)", the comment escaped; an unresolved silence named by its id; the alert's and the silence's identity on hover (tests/test_grafana_reader.py `TestASilenceStaysARow`, through GET /v2/attention) | **deviation** (log: Landing: a Grafana incident's member draws its onset and any silence, who, until when and why (C1277)) |
| Levels | Critical red, Warning amber, Unknown grey, as the row's left edge and its level word | the same | **same** |
| A source that could not be read | an Unknown row: "This is not the same as no alerts" with the last good read | an Unknown row naming what failed, "This is not the same as nothing needing attention", and the summary says it | **same** |
| What was checked | collapsed: "11 sources, 10 within their promise · oldest: drift, 21 min of 30" | collapsed: "What was checked · 25 sources" (capture 01); opened, a table (source, what it found, value from with the read's duration, rows) and the acknowledgements in force | **deviation** (log: Landing: What was checked's summary is the count of sources) |
| Recent operations | a right-hand column: "Recent operations" with All in History, each with its outcome icon and colour (Partly done amber, Succeeded green), its detail line, time and who | "Recent changes" under the list, full width: deploys and restores from their receipts, the outcome in words with no colour ("deployed · 3 lines", a Mode B removal read like a merge), time and who; no link to History; drawn at page load, not live (C894) | **deviation** (log: Landing: Recent changes has no link to History and no outcome colour (a defect, register C650 follow-up)) |
| Many rows | five rows on the board | every row drawn expanded, worst first, with no grouping by level or source and no filter: 44 rows here run to about 9,500 px at 1440 | **deviation** (log: Landing: many rows are drawn expanded with no grouping (a defect, register C650 follow-up)) |
| C566's row (C566Coverage) | Templates: the profile's management sources section reaches no device, the network's `_common.j2` an older shipped version (9 devices); Bring in the shipped version…; Clears when every applying section renders | raised by the real source on the stale lab: the same words for 2 devices, the template and section as operands, "Bring in the shipped version…" with its (i), and how it clears | **same** |
| The rolled-back row | not on the boards | in the operator's W1 capture, r5's block read "neither has a screen yet"; compared again 2026-10-16 after C544's fix: it offers Revert intent… and Retry with a reason…, two v2 links to the device page's cards | **deviation** (log: Landing: the rolled-back row offers Revert and Retry, a row no board draws) |
| Known noise (KnownNoise sections 1 to 4) | the syslog row names its message; Classify as known noise… opens the card in place; classified lines listed under What was checked with the rate; the rate's Warning row | not built: C534 is LAB and parked in the register | **later** C534 (parked, LAB: the classification of a known message, built after C506) |
| Acknowledge… | on an event row (KnownNoise) | drawn on each row whose source allows it, the reason box in place, busy on itself (compared by the template and tests/test_acknowledge.py; none of this shot's rows offers it) | **same** |
| Acknowledge…, answered (C1388) | not drawn: the board shows the button and the reason box | once sent, Cancel is gone; recorded: the form closes saying "Acknowledged." and the row leaves at the next redraw; refused: the form stays open saying why; no answer within 6 s: the form closes saying, in amber, that whether it was recorded is not known and the next redraw shows it (tests/test_live_redraw_keeps_form.py, in a real browser) | **deviation** (log: Landing: a sent acknowledgement is answered in place within 6 s, with no Cancel once sent) |
| Live redraw | not drawn | the rows redraw without a reload: the walk's rotation rows appeared within about 20 s and left as Save All and the export ended (steps 34, 37 and 39; C539) | **same** |
| Phone (LandingPhone) | the heading with "5 items", "11 sources checked at 23:40", each row a card with its action full width, "2 more below" | the same card stack and summary; each card carries the row's whole anatomy (above) and its action at its own width; no "more below" (the page scrolls) | **deviation** (log: Landing: a row carries its operands and how it clears) |
| Phone top bar (LandingPhone) | menu, the network as a chip, a search icon, the integrations count, the person | menu, the 32 px mark and the network's name, the search box, the strip's dots, the theme menu, the person | **deviation** (log: Landing: the top bar carries no Assistant) |
| The drawer (NavPhone) | the mark, "NMAS" over "Network Default", an X, the entries, Integrations and Live in a box above Help | the mark and "Mercury", the entries under their headings, Help and Settings; no X (the scrim closes it, C475), no network line and no integrations box (both stay in the top bar) | **deviation** (log: Landing: the drawer has no close button, network line or integrations box) |

## Board NA-R (PHASE8_PLAN 20.6), part 1

| Region | Board | Built | Verdict |
|---|---|---|---|
| The summary | "1 critical · 2 warning · 1 acknowledged · 11 sources checked, read 16:40 UTC · 3 expected effects of r8's Reload are on its card" | "51 items · 9 critical · 39 warning · 3 unknown · 10 sources checked · 1 could not be read", the expected effects a link to the Reload's device page, which reopens its card | **same** |
| A section per severity | Critical · 1, Warning · 2, Unknown · 0, open or closed, the count in the heading | the same headings; Critical always open; Warning, Unknown and Acknowledged as this viewer last pressed them (this browser only) | **same** |
| An empty section | "· 0" only when it was open last, else left out | left out | **deviation** (log: Board NA-R built, part 1) |
| The item's line | severity, title naming devices, its age, the primary action | the same four; the title cut with an ellipsis on desktop, wrapped on a phone, whole on hover | **same** |
| Opened: What to do | the action, its button, Acknowledge…, How does this work?, "Clears when …" | the row's controls as they were, then Clears when, then Acknowledge… | **same** |
| Opened: Explain or Why this happened | the kept Explain answer for an alert-backed row; code-written Why this happened for Mercury's own findings | an alert's item loads, when opened, the same block Monitoring › Alerts draws for its first alert's pack (the kept answer, or Explain offered behind its cost; no call by opening); every other item, its cause under Why this happened, "Written by Mercury from its own record: no AI" | **same** |
| Opened: Details | alerts, since, source, the pack, under a divider | the cause, operands, alert members, Also, devices with their networks, since, read, source, under a divider | **same** |
| Acknowledged | its own section, each with who, when, the reason, Remove acknowledgement | its own section with who, when and the reason; no Remove acknowledgement (no route removes one yet) | **deviation** (log: Board NA-R built, part 1) |
| Nothing to act on | one line and What was checked, collapsed | "Every source answered and none reports anything a person must do." and What was checked, collapsed | **same** |
| The sidebar's badge | unacknowledged Critical and Warning items | unacknowledged items of every level, Unknown included (attention.badge_of) | **deviation** (log: Board NA-R built, part 2) |
| Phone | the severity above the title, the action under it | the same (`nar-phone-page-390`) | **same** |
