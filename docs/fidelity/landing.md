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
Templates compared: templates/v2/landing.html, templates/v2/_attention.html, templates/v2/_recent.html
Templates sha256: `924ca92a334c0557a58bceea2c23c1fff6368a253a6fc27d02ab0885815d349a`

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
