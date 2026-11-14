# Mercury's UI rules

Every v2 screen follows these rules. The complete GUI review the operator queued on 2026-11-11
(it starts once every Lab 10 feature is verified on the host) researches established practice
and rewrites this file into the full rule set, each rule marked enforceable by a test or not,
with the tests it proposes. Until then this file holds the rules already in force: the operator
said on 2026-11-11 that every new UI follows them before the review, and added more on
2026-11-12.

Each rule says where it is held: a test, or `[not mechanised]` when only this file holds it.

## Pages wait on nothing

**No page load or badge poll waits on Grafana, Loki, NetBox, a device or a computation:
every page draws at once from data the background already holds, shows each source's age
("checked 20 s ago"), and updates itself while open; there is no refresh button** (the
operator, 2026-11-12; C3166: Needs attention's badge queued from 1.6 s to 26 s during a heal,
and a device's Logs tab waited 5 to 15 s on Loki). Each source refreshes on its own cadence,
fast while viewed or alerting and slowly while idle; an event recomputes only the sources it
touches, debounced, so a heal's step announcements cause one recompute; a fix made through
Mercury still clears its row within seconds. **Display only:** the held values draw pages; the
heal pipeline (detect, decide, guards, apply, verify, can't-fix), deploys and their before and
after reads always read live. Cost: one background refresh per source, and the CPU and memory
it adds on the host, stated. Prevents: a page as slow as its slowest source, a request storm
whenever a heal announces, and a decision made on a page's stale copy.
[the routes that still wait, named and only shrinking, every other GET route calling out
nothing: tests/test_no_page_waits.py; display only: tests/test_attention_display_only.py;
Needs attention's background store, its cadence and its one recompute per burst:
tests/test_attention_store.py]

What it means on a screen, as slice 1 built it for Needs attention:

- The value drawn is the one the background holds (modules/attention_store.py); before the
  first one lands the screen says "Reading …", busy, and fills itself when it does.
- Every value says its age: the list says when it was checked and how old its oldest source's
  read is, and What was checked has a Checked column, one age per source.
- A refresh that fails keeps the last good value and says so, on its source's line and in the
  summary; a source past its own promise is a Needs attention row of its own.
- The sidebar's count is pushed over the page's live connection when it moves; after the page
  loads it is asked for again only on that page's own acknowledgement, which the background
  has already taken into account (a person's own press is drawn at once).

## In force now, before the review (the operator, 2026-11-11)

Each is `[not mechanised]` until the review proposes its test.

- **One primary action** per card or page.
- **Menus hold items and short reasons**, never paragraphs.
- **A status notice is a banner**, not menu text (the held-device banner, not a line inside
  the Actions menu).
- **A card's text stops at a stated length**, and more goes to its page (the collapsed
  last-run line).
- **Each fact appears once** on a screen (a failure is said once).
- **Tables never scroll inside a card.**
- **A stepper uses labels of 2 to 4 words** (the short stepper labels; never a sentence in a
  stepper column).
- **One main area per page.**
- **No secrets or emails on screen** (a person is named by display name; an identity is held
  only in a collapsed record, board E2a).
- **One time zone per screen:** local time, with UTC on hover (the operator, 2026-11-11, on the
  run card: "The card mixes "20:01 UTC" with steps in MST"). Every time a template draws goes
  through `_macros.clock`, drawn by the server in the viewer's kept zone (a per-person setting,
  from the browser on the first visit; the operator, 2026-11-12), the zone named once per
  screen, the record's UTC on hover. Python builds no time words for a screen: a builder
  writes the instant (ISO UTC) into its words or a record's value, and the template draws
  them through the `times` filter (routes/v2.py), which gives each instant to the same clock;
  a quoted text (a log line, a program, a model's prompt) is marked `data-verbatim` and left
  (C3290, the operator, 2026-11-13). [the templates and the zone: tests/test_local_times.py;
  every response the v2 walk receives, its known gaps named and only shrinking:
  tests/test_no_utc_drawn.py]

## Rules added 2026-11-12 (the operator)

Each is `[not mechanised]` until the review proposes its test (for the first, the review's
proposal: an action's response draws inside a dialog anchored to it, focus inside, Escape
closes).

- **An action does not open a second card or menu elsewhere on the page.** If a confirm step
  is justified (a preview, a reason, a hash, as for any change Mercury makes on its own), it
  opens as a MODAL over the page, anchored to the action, with focus moved into it, and closed
  by Cancel or Escape. Never a card appearing somewhere else on the page.
- **Self-healing:** the Fix kinds table's Heal / Dry run only toggle IS the control; pressing
  it opens that modal (what this changes, reason, Confirm). The mode is a dropdown (Off / Dry
  run / Auto) opening the same modal (C3158). [Built 2026-11-13 (the GUI review's item 7): each
  toggle a button opening its kind's modal, the dropdown's choice opening its mode's, Change
  fix kinds… and each hard stop's Edit… theirs, a refused confirm's opened again:
  tests/test_heal_tab_v2.py, in Firefox too (pressed from the keyboard, anchored, the focus
  inside, Escape and Cancel closing it, the focus and the dropdown back)]
- **A time limit is never a typed UTC string** ("Auto until"): quick choices (1 h, 2 h, 4 h,
  8 h, 24 h, 7 days) plus a date-time picker in local time, showing the UTC beside it. [Auto
  until on Self-healing, 2026-11-13: the picker read in the viewer's kept zone and converted
  once by the server, a quick choice resolved once and drawn into the picker, the confirm in
  the viewer's time naming the zone: tests/test_heal_tab_v2.py; every other time limit: not
  mechanised]
- **Every "…" button in Mercury is reviewed for the modal rule**, and listed with its fix (the
  review's section 3).
- **No control moves when its own result appears** (the operator, 2026-11-13, on Run the check
  again: "the message pushes the button onto a new line. The button never moves: draw the
  message below it (or in reserved space)"; C3401). A control's answer (a refusal, "Checked
  just now", a failure, its busy words) is drawn below it or in space reserved for it, never
  beside it where it can wrap the control onto another line; a busy label is laid in the same
  cell as the idle one, so the control is as wide busy as idle; and a control placed after
  words that its own press changes (an age, "read just now") is placed by something those
  words cannot move. Cost: a reserved place per control, and a real-browser check of each.
  Prevents: a person's pointer left on empty space, or on another control, by the answer to
  their own press. [Run the check again at 1280 and 390, before a press, at its busy answer,
  after the list's redraw and after a refused repeat: tests/test_recheck.py
  (`test_the_button_never_moves_when_its_own_answer_appears`); the page's scrollbar keeping
  its place, so that a row opened on History, a device's History tab or Needs attention moves
  nothing sideways when the page begins to scroll (C3468, `scrollbar-gutter: stable` on the
  page): tests/test_no_control_moves.py; every other control: not mechanised]

## Proposed by the GUI review of the recorded screens (2026-11-13)

The review of the screens the course lab's video records (Needs attention, the incident page,
the heal card, History, Settings › Self-healing, Logs, the can't-fix email, AI
troubleshooting; the review's report, kept with the operator's reports, holds the screenshots
and the measurements behind each rule). **Proposals: none is in force until the operator approves it**,
and none changes a rule above. Each names its source and, where a test can hold it, the test it
proposes (none is written yet). The rules above stay as they are, word for word.

### Summary first, detail one level down

- **A list screen opens with one summary line of counts by state** (Needs attention's "55 items
  · 9 critical · 43 warning", Logs' "77 lines … 3 error or worse"), before any row (Few: the
  glanceable summary first; NN/g progressive disclosure). [Proposed test: a browser walk of
  each list screen finds a summary element with a count before the first row.]
- **Rows of one shape collapse into one row.** Rows that differ only in a name (33 rows
  "reader:<name> has never run on this host" in the landing walk's world) are one row naming
  the count, the names one click down; adjacent identical log lines (same device, mnemonic and
  message once its numbers are removed) are one "×N" row with the first and last times, as
  History's runs are (C3399) (PagerDuty: group related alerts into one incident; alert
  fatigue). Measured: 33 of the landing walk's 55 rows are one shape. [Proposed test: in the landing walk's world no two Needs attention rows share their
  words once each device or source name is replaced by a token; in the Logs fixture no two
  adjacent rows share device, mnemonic and digit-stripped message.] [Built for Needs attention
  with the review's item 10 (C3457; provisional, operator review pending): rows from one
  source, of one kind, whose words differ only in their subject are one row from two of them
  (`attention.group_alike`, applied as the page is drawn, the members under it as C2970's
  collector row holds its own), its level its worst member's, its action theirs or Open the
  list; every count stays the findings' and says its rows; and every row's line names its
  action (`attention.first_action`'s control, else its words, else how it clears). Measured on
  the landing walk's world: 56 rows drawn before, 17 after; 5 of 9 critical lines drew no
  action before, none after. tests/test_attention_alike.py: no two drawn rows share their words
  once each subject is a token, each finding drawn once as itself, the counts, every line's
  action, 900 alike devices one closed row, and in Firefox Open the list and the line's words.]
- **An opened Needs attention row is a summary, not the incident.** Opened, a row says at most
  three things (what is wrong in one sentence, whether it needs a person, its one action) and
  links to its home ("Open the incident" as the row's first link, never its last); the
  steps taken, the diagnosis, the analysis, a proposal's six parts and the record are on the
  incident page. Measured: the heal proposal's opened row is 634 words and about 1,100 px tall
  at 1280 px. [Proposed test: for each self-healing, lost-stream and proposal row in the
  landing and heal worlds, the opened row's body is at most 60 words before its link to the
  incident page.]
- **Disclosure stops at two levels:** no `<details>` inside a `<details>` inside a
  `<details>` in a page's main area (NN/g: designs past two levels lose people). [Proposed
  test: a scan of each rendered recorded screen.]

### One state, one action

- **An incident's state is said once, from one function,** and every part of its page agrees:
  the header badge, What to do and AI troubleshooting never disagree (measured: "No person
  needed" and "Nothing yet: Mercury is working on it" beside "Stopped … Nothing more runs
  unless you choose") (Nielsen 1, visibility of system status; CLAUDE.md, "Never let a wrong
  thing look like a working thing"). [Built with the review's item 2 (C3450; the operator,
  2026-11-13: "Build review items 1, 2, 5, 6, 9 first"): `incident_page.status`, held by
  tests/test_incident_state.py (each planted state, every section carrying it, no words of
  the other state) and tests/test_incident_stream.py (a stopped fix-it attempt draws "Needs a
  person" in the header and an action in What to do).]
- **A page that says a person is needed carries that person's action on itself:** What to do
  holds the one action as a button (Review the fix…, Re-subscribe…, Lift the halt…), never
  "what a person may do about it is on Needs attention". Measured: the incident page has no
  button in any of its four planted states. [Built with the review's item 2 (C3450): the
  action is the incident's own Needs attention item's (`incident_page.item_of`,
  `attention.first_action`), and every planted incident page whose state is "Needs a person"
  draws exactly one primary button inside What to do: tests/test_incident_state.py,
  tests/test_incident_stream.py. Not built: Lift the halt… on the page (a halt's item names no
  incident), and a dry-run record's Right and Wrong…, two answers with no primary.]
- **Each fact once, measured:** an outcome ("verify failed") is drawn at most twice on a
  screen, once as a state word in a header cell and once with its reason in its stage
  (measured: five times on the rolled-back incident). [Built with the review's item 6 (C3454):
  the header's cells and the attempt line say the state, the reason on the hover; a failure's
  why is said once, by the first stage that failed, and a later stage says its state alone
  (`run_stepper.stages`). tests/test_incident_titles.py: every planted incident's page says
  "verify failed" at most once (each failed verify exactly once) and each failed step's words
  at most once, on the page and on the card its device's History reopens.]
- **The stepper never says "failed" for a decision that worked:** a can't-fix stage reads
  "Can't fix: needs a person", not "Decide failed". [Built with the review's item 6 (C3454): a
  decision's can't-fix is the stepper's `needs` state (`run_card.DECISION_NEEDS`), amber
  (`--warn-mark`), never red; a stage's sentence is at most `run_stepper.STAGE_SAID_WORDS` (12)
  words, its whole one level down. tests/test_incident_titles.py: the planted can't-fix
  incidents' stepper holds no "failed", the stage's words and class, the CSS token, and every
  planted page's stages within 12 words.]

### Words on the page

- **A title is a summary of at most 70 characters;** a configuration line, a command or an id
  is in the body, never the h1 or the breadcrumb's last crumb (measured: the incident titles
  are the configuration line, 95 characters, two lines at 1280 px). [Built for incidents with
  the review's item 5 (C3453): ONE title builder, `said.title`, for the incident page's h1, its
  breadcrumb's last crumb (cut with an ellipsis, the whole on hover), the email's lead and the
  lines Needs attention and History lead with. tests/test_incident_titles.py: every planted
  incident's title at most 70 characters, holding none of its records' lines and no mnemonic,
  code key, id or address, and its h1 one line at 1280 px in Firefox. Every other recorded
  screen's h1: not measured yet.]
- **Mode and state words have one spelling:** Off, Dry run, Auto (never "AUTO", "auto",
  "dry_run" on a screen or in an email). [Proposed test: a scan of the recorded screens' text
  and the email for `\bAUTO\b`, `dry_run`, `cant_fix`.]
- **No raw time or code in a control's label:** a button names a time in the viewer's zone
  ("Turn on Auto until Tue 18 Nov, 04:49") and never an ISO instant (measured: "Turn on Auto
  for Default until 2026-11-18T11:49:00Z"). [Proposed test: tests/test_no_utc_drawn.py's
  walk refuses an ISO instant or "UTC" inside a button's or a link's text.]
- **A notice that is context, not a warning, is a line under the header,** never a banner
  above the h1 (GOV.UK: at most one notification banner, only for what the person must
  know); the incident's "Folded into" and "Related" notices become one "Related:" line.
  [Proposed test: nothing but a danger or warning notice precedes a recorded screen's h1.]

### Tables and controls

- **A cell holding a time, a mnemonic, an id or a hash never breaks inside it** (measured on
  Logs at 1280 px: "15:19:1 / 8" and "%SSH-4-SSH2_UNEXPECTED_MS / G"); the column is as
  wide as its widest token, and the message column takes what is left. [Proposed test: at
  1280 px every `td` of a time or mnemonic column in Logs, History and the incident timeline
  is one line tall.]
- **Something drawn as a control is one:** a segmented control's segments are buttons or
  labelled inputs, or the segments are drawn as plain text (measured: Settings ›
  Self-healing's Heal / Dry run only segments are spans that look pressable; C3158 makes
  them the control). [Proposed test: every `.seg-btn` in a rendered page is a `button` or a
  `label` for an input.]
- **Choices of one decision are drawn alike and together:** AI troubleshooting's Retry with
  more information…, Cancel and Hand over… are three buttons in one row, left to right in
  that order, each opening its modal (today two are disclosure triangles and one a button,
  spread across the row) (Nielsen 4, consistency). [Built with the review's item 8 (C3455):
  the three are one row of secondary buttons, each opening its modal anchored to it
  (`templates/v2/_modal.html`, v2's first; static/js/nmas_v2.js, "The modal"), Cancel's modal
  its confirm, and the section draws no primary, so What to do's is the page's one.
  tests/test_fixit_section_v2.py: `TestTheChoices` (the row, alike, none primary, each naming
  its modal) and, in Firefox, `TestTheModals` (each opens as a modal on its press, anchored,
  the focus inside; Escape closes it, the focus back on its button; a confirm's answer drawn
  in place, the focus on it). Every other "…" control in section 2.9's list: not built.]
- **A destructive action that reaches everything sits first in its own danger card,** never
  after the last card of a long page (Stop self-healing everywhere…). [not mechanised]

### WCAG 2.2 AA, measured on the recorded screens

- **Text contrast 1.4.3:** body text at least 4.5:1, large text 3:1. Measured: the muted
  token `--ink-3` (#9AA3AE) on white is 2.55:1 and draws every section label ("What to do",
  "Detected", "What happened") on every recorded screen; its replacement is at least 4.5:1
  on the card background in light and dark. [Proposed test: tests/test_v2_theme.py computes
  each text token's ratio against each background token, in both themes.]
- **Non-text contrast 1.4.11:** an icon that is a control (the compact "How does this work?"
  (i), drawn in `--ink-3`) and a control's border are at least 3:1 against what is next to
  them. [Proposed test: the same token check for icon and border tokens.]
- **Target size 2.5.8:** every pointer target is at least 24 by 24 CSS px, or spaced so a
  24 px circle on it touches no other target. Measured: the compact (i) is 15 px, 4 px from
  its button; a `summary` is 17 to 22 px tall. [Proposed test: a browser walk of the recorded
  screens measures each button, summary and icon link.]
- **Focus visible 2.4.7 and not obscured 2.4.11:** the global `:focus-visible` outline (2 px,
  the accent) stays on every control, and a control focused by Tab is never wholly under the
  sticky top bar. [Proposed test: a browser walk tabs through each recorded screen, reading
  each focused element's outline and its rectangle against the top bar's.]
- **Keyboard 2.1.1:** every action is reachable and operable by keyboard; no click handler on
  an element that cannot take focus. [Proposed test: a template scan refuses `x-on:click` or
  `hx-trigger="click"` on a `div` or `span` without a `role` and a `tabindex`.]

### The can't-fix email

- **The email leads with the outcome and the link:** its first three lines say what happened,
  whether it needs the reader, and "Open in Mercury: <link>"; it holds no host command, no code
  key (`interface.ip-access-group`, `cisco_iosxe`, `CONFIG_I`) and no model or measurement
  internals, and says the outcome once (today in Outcome and again in the Decide step).
  [Proposed test: tests/test_cant_fix_email.py's `check_email` holds the link line within the
  first six lines and no `scripts/` in the text.]
