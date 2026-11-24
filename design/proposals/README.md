# Three GUI directions for Mercury: comparison and recommendation

The week plan of 2026-11-23, Stage 3. Three directions, each drawn on the same six screens and
the same fake data (`_shared/BRIEF.md`), with Mercury's colour tokens (`_shared/tokens.css`):

- **A, Workbench** (`A-workbench/`): every section is a dense list with the selected item's
  detail beside it; the assistant is a docked third column.
- **B, Inbox** (`B-inbox/`): home is one queue of what needs a person, keyboard first; every
  object page is a "what is wrong, what next" line and one timeline; the assistant is a Ctrl K
  palette.
- **C, Document** (`C-document/`): every page reads top to bottom: a one-sentence summary, key
  facts, then sections that open; no cards; the assistant is a slide-over drawer.

Open each folder's `home.html` in a browser (they are static files), or the shots in each
`shots/1366x768/` and `shots/1920x1080/` (in `design/proposals.zip`; regenerate with
`tools/review_screenshots.py --static design/proposals`). Each README has its principles, its
sources from `design/research.md`, and how it answers the four concerns. The pages they redraw
as "the two worst" are design/review/WORST_CARD_PAGES.md's ranks 1 and 2: Settings › network ›
Network (18 cards) and the incident page.

## Side by side

| | A, Workbench | B, Inbox | C, Document |
|---|---|---|---|
| What a person sees first | Needs attention's counts, the fleet bar and running work on the left; the top critical row already open on the right, with its action and how it clears | "10 things need a person", the critical rows each with one action and its keyboard key; running work and the fleet in a side column | One sentence: "Three things need you now: …", then the counts as facts, then the critical rows as a table |
| Find why a device is unhealthy | 1 click from Needs attention | 1 click (or Enter) | 1 click |
| Push an intent change | 3 from the device page (5 from home) | 3 plus the edit | 3 plus the edit |
| Turn a setting on | 3 (Settings, toggle, Save) | 2 (Settings, toggle), or 1 from Ctrl K | 2 (Settings, toggle; it saves in place) |
| Density | Highest: list and detail on one screen; detail is about 610 px wide at 1366 with the assistant open | High in rows, generous in headers | Lowest: 15 px body type, a reading measure, an outline column |
| The assistant | A docked column, always one click away, context the selected item | A palette over the page; "Pin to the side" not yet drawn for long investigations | A drawer over a dimmed page with Ask, Sources and History tabs |
| Progress after a click | A step strip in the detail's header and an Activity tray in the top bar | A timeline that grows in place, each step opening to its evidence (CI step-log style) | A vertical stepper pinned under the page title, each step with its time and evidence |
| Build days (each README's own estimate) | about 50 | about 34 | about 30 |
| Main risk | Width: below about 1200 px the list must become a drawer, and Topology, Monitoring and SDN need a full-width mode (not drawn); every section needs a list and a detail route | The one header line picks the wrong "most important" thing, and one queue floods at fleet scale unless rows of one cause group | The summary sentence can be wrong while looking right; long pages lean on search and the outline |

The estimates are not measured the same way: A's counts porting every section (29 of its 50
days) and a floor for manual pages and test churn; B's and C's count the screens drawn and a
port of the rest more lightly. Read them as A ≈ 1.5 × B or C, not as exact days.

## What each gets wrong in its drawing (to fix before any build)

- A draws a horizontal step strip, against Carbon's advice to show multi-step progress
  vertically (research.md, concern c); its Activity tray covers part of the device page.
- B's palette is cramped for an investigation until "Pin to the side" exists; two of its Settings
  rows are mockup settings Mercury does not have (its README says which).
- C draws a "Check every source again" button on home; Mercury's rule is no refresh button
  (pages update themselves and show each source's age), so it goes.

## Recommendation: C, Document, with two pieces of B

**C as the base.** It is the direct form of Mercury's first interface rule, "the screen answers
the person's question; the evidence is one level down": every page opens with the answer in a
sentence, then the facts, then the evidence behind a disclosure. It removes cards entirely rather
than restyling them, it is the cheapest of the three, and its pattern (summary, facts, sections,
outline) is the same on every page, which the rubric asks for. Settings, the worst page today,
becomes one searchable document with toggles, which is the plan's Settings ask almost word for
word.

**Two pieces of B:**
1. **Needs attention as B's queue:** the grouped rows with the one action button at the row's
   end and the keyboard keys (j/k, Enter, e). C's home already draws the rows as a table; B's
   action column and keys make it faster to work through.
2. **B's step timeline for running work** inside C's pinned stepper: each step opening to its
   evidence (the read, the masked lines) where it is, as CI step logs do.

**What C must answer in its build:** the assistant docked rather than modal (the design note
asks for a right-docked panel that stays open across pages: C's drawer without the dimming, so
the page stays usable beside it), and the summary sentence built from the same data as the facts
under it, with every stale, unreadable and partial state tested, since it is the line read most.

## The question for the operator

Which direction to build: A, B, C, or C with B's queue and timeline (the recommendation). The
week plan's Stage 5 build items wait for the answer (docs/handoff/OPERATOR.md#gui-direction).
