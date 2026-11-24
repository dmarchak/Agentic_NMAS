# Direction B: Inbox (triage first, keyboard first)

Seven static screens on the brief's fake data (`design/proposals/_shared/BRIEF.md`), coloured
only by `../_shared/tokens.css`. Open any `.html` file directly; `shots/` holds them shot at
1920x1080 and 1366x768 by `tools/review_screenshots.py --static`.

## Principles

1. **Home is one queue of everything that needs a person**: incidents, Needs attention rows,
   changes and fixes waiting for approval, failed jobs. Most urgent first, grouped Critical,
   Waiting on a person, Warnings. Each row is a sentence naming what is wrong, one action, and
   how it clears.
2. **Keyboard first, never keyboard only.** `j`/`k` move, `Enter` opens, `e` runs the row's one
   action, `a` acknowledges, `g` then a letter changes view, `/` filters, `Ctrl K` searches or
   asks. Every key is printed beside the control it drives, and every control is also a button.
3. **Every object is a full page with one layout**: a header line saying what is wrong and what
   to do next (with the one action), then a single timeline of what happened, newest first.
   Facts and checks sit in a narrow rail beside it. Devices, changes and incidents all follow it.
4. **Progress is a step log that grows in place**, like a CI run: each step shows its state, its
   duration, and opens to its evidence. Roll back is drawn as the step that runs only on failure.
5. **The assistant is the command palette.** `Ctrl K` answers inline, marked AI, with numbered
   sources, the model and the cost so far. Its hand-offs open Mercury's own gated flows. It never
   applies a change.
6. **Lean header, dense body.** The header gets generous whitespace; rows below are tight (one
   sentence plus one quiet "clears when" line).
7. **Five views in the sidebar, with counts**: Inbox, Devices, Changes, History, Settings.
   Everything else is reached from an object page or `Ctrl K`.

## Sources (from design/research.md)

- Counts by outcome first, each a filter; only things in a failing state listed: Marvis Actions
  ([HPE Mist](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-actions-overview.html)),
  Datadog Triggered Monitors ([Datadog Manage Monitors](https://docs.datadoghq.com/monitors/manage/)).
  Research pattern 7.
- Grouped lists with sticky group headers; a row opens a peek, the full page one more step:
  [Linear display options](https://linear.app/docs/display-options),
  [Linear Peek](https://linear.app/docs/peek). Research patterns 8 and 10.
- Hover to see why a suggestion appears; suggestions accepted or declined inline:
  [Linear Triage Intelligence](https://linear.app/docs/triage-intelligence).
- The step log with per-step durations, expandable steps, the failed step opened:
  [GitHub Actions workflow run logs](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs),
  [Vercel build logs](https://vercel.com/docs/deployments/logs). A vertical stepper for a known
  linear flow: [Carbon progress indicator](https://carbondesignsystem.com/components/progress-indicator/usage/).
  Research pattern 12.
- Feedback by duration (busy on the control up to about 10 s, then a job with its own page):
  [Primer loading](https://primer.style/product/ui-patterns/loading). Research pattern 11.
- Answers that cite their evidence and end each hypothesis confirmed, ruled out or can't tell:
  [Datadog Bits Investigation](https://docs.datadoghq.com/bits_ai/bits_investigation/investigate_issues/),
  [Grafana Assistant Workspace](https://grafana.com/docs/grafana-cloud/machine-learning/assistant/workspace/).
- AI content labelled, the label naming model and cost:
  [Carbon for AI](https://carbondesignsystem.com/guidelines/carbon-for-ai/),
  [Microsoft Learn, UX guidance](https://learn.microsoft.com/en-us/microsoft-cloud/dev/copilot/isv/ux-guidance).
- A change from the assistant is a plan a person approves, never applied by the assistant:
  [Vercel Agent permissions](https://vercel.com/docs/agent/chat/permissions).
- Page context attached automatically and drawn as chips above the prompt:
  [Grafana Assistant](https://grafana.com/blog/llm-grafana-assistant/). Marvis opens its
  assistant with Ctrl+K ([Marvis conversational assistant](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-conv-assistant-enhanced.html)).
- The answer on the surface, disclosure only for supplements, never nested:
  [Carbon disclosures](https://carbondesignsystem.com/patterns/disclosures-pattern/),
  [Primer progressive disclosure](https://primer.style/product/ui-patterns/progressive-disclosure).
  Empty, no match, unreadable and loading as four states; a failed source degrades only its
  section: [Primer degraded experiences](https://primer.style/product/ui-patterns/degraded-experiences).
- Not in research.md: Linear's inbox and keyboard model, which this direction borrows most
  from (`https://linear.app/docs/inbox`, `https://linear.app/docs/keyboard-shortcuts`). Cited
  from the products' own pages, not checked by the research agent.

## The four concerns

**The AI assistant.** One entry point: `Ctrl K` (the top bar's search box is the same palette).
Typed text that names a device or view navigates; a question answers inline in the overlay, over
the page it was asked from. The overlay shows the context it sent as chips (Incident #57, r3, r4,
the last 30 min of logs, masked), the answer streaming with numbered citations, each source with
Open, the AI mark, the model and the cost so far, and Stop. Hand-offs are buttons: **Propose a
fix** (opens the gated fix flow: preview, confirm by hash, apply, verify, record), Read r4 too
(an allowlisted read), Copy, and **Pin to the side**, which keeps the conversation open beside
every page for a longer investigation. The top bar's AI chip carries today's spend and the
background features that are on. An incident's diagnosis lands in that incident's timeline as an
AI-marked entry, so the answer stays on the object, not only in a chat.

**Dense pages without card overload.** No cards stacked in a grid. A page is a header, then one
list: queue rows, timeline entries, steps, or settings rows. Facts sit in a narrow rail of
two to five quiet panels with label/value lines. Today's worst page (Settings, Network: 14
near-identical cards, `worst-1.html`) becomes 18 rows in six named groups. Each row is a label,
one plain line, the control, and one quiet word for where its value comes from (Default, Lab's
own, n/a); the word opens the inherit, own, or not-applicable choice. The consequential
setting, Inventory source, comes first. The incident page (`worst-2.html`, 7 top-level cards and
31 collapsibles today) becomes a lifecycle line, the header line with its action, one timeline,
and a rail.

**Progress after a click.** A control is busy on itself until its answer arrives. Anything
longer than a few seconds becomes a page of its own with a step log (`change.html`): Preview,
Confirmed by hash, Apply to r2 (holding the device), Verify (running, its sub-steps listed, the
hold-time wait drawn as "38 s of 90 s" with a meter and the reads that prove it), Record
(waiting), and Roll back drawn hatched with a dashed mark as "runs only if Verify fails". The same
running step shows as one line in the Inbox's Running now rail, in the device's header line and
in its timeline. Leaving and coming back shows the same step.

**Minimalism without hiding information.** The header line answers the question. Evidence is
one level down, behind a labelled "Evidence" disclosure on the timeline entry. A subset always
says so ("4 acknowledged rows hidden (show)"; "no match · 3 settings (Show)"; "Showing 1 of 10").
Unreadable is its own state, never empty: Grafana unreadable for 2 min is an Inbox row, and the
device's Alerts check says "unreadable; last read showed none firing" in grey, not a green "none".

## What a person sees first

| Screen | First thing seen at 1366x768 |
|---|---|
| `home.html` | "10 things need a person", then the focused critical row: r3 lost its OSPF neighbour r4, with Troubleshoot (`e`) and how it clears. |
| `worst-1.html` | Settings › Network for Lab: what inherits (8 Default, 9 Lab's own, 1 n/a), then Inventory source (NetBox, filtered by site, 912 devices). |
| `worst-2.html` | Incident #57's lifecycle line, then "A fix waits for your approval: set r4 Gi0/0/1's MTU back to 1500", with Review the fix (`e`). |
| `device.html` | r2's addresses, then "Change #141 is verifying on r2: 38 s of 90 s. Nothing to do now", then its tabs. |
| `settings.html` | The search holding "heal", 6 matches in 3 sections, the Automation section with its four matches marked. |
| `change.html` | "Verifying on r2: waiting out BGP's hold time, 38 s of 90 s", then the step log with Verify open. |
| `assistant.html` | The palette over incident #57: the question, the context chips, the answer streaming with sources 1 and 2, and Propose a fix. |

## Clicks for the three most common tasks

1. **Find why a device is unhealthy: 1 click** (or `Enter`) from the Inbox, where the problem is
   already a row. The object page's header line is the answer; its evidence is one more click
   ("Evidence" on the timeline entry). For a device that is not in the queue: `Ctrl K`, type
   "r2", `Enter` (no click), or Devices › a filtered row (2 clicks).
2. **Push an intent change: 4 clicks plus the edit.** Open the device (`Ctrl K` "r2"), Intent tab
   (1), Edit, then Preview (2) shows the exact program, masked. Confirm by hash (3) is the one
   decision. The step log then runs by itself, and Record needs no click. The 4th click is
   opening the change from the device's header line, which is optional.
3. **Turn a setting on: 2 clicks.** Settings (1, or `g s`), type in the search, press the toggle
   (2). From `Ctrl K` ("heal batch"), the palette jumps to the row: 1 click.

## Density

- Queue rows are 52 to 64 px: a one-line sentence (wrapping to two at 1366) and a 12 px "clears
  when" line. Nine to ten rows show above the fold at 1366x768 under a 130 px header. All three
  critical rows and both waiting rows show without scrolling.
- Timeline entries are about 28 px; ten fit in the first screen of a device's Overview.
- Settings rows are 56 to 80 px (label, one line of description, provenance).
- The sidebar is 200 px and the rail 270 to 380 px. The main column keeps at least 650 px at
  1366 wide.

## How the assistant fits

It is one surface, the palette, reached from every page with the same key. It knows the page it
was opened on and says so. Its answers end in Mercury's own hand-offs (a fix flow, an
allowlisted read, a page). It never adds a second way to do a job. Pinning keeps it beside the
page for long work, which the research's strongest pattern asks for (Grafana and Marvis keep
the assistant open across navigation). The AI chip in the top bar is always visible: "AI $0.04
today · 1 background on", or "AI off".

## How progress shows

As a step log that grows in place. Done steps show a green tick and their duration, the
running step is open with a blue ring and its sub-steps, and waiting steps are grey. The
on-failure step is hatched with a dashed mark. Each step opens to its evidence: the program,
the hash, the reads with their times. Colour never says more than the result: a partial verify
would show amber "partly verified", never green. The same state appears in the Inbox rail, the
device header and the device timeline, each a link to the change page.

## Build estimate

About **34 build days**, from the v2 frame that exists today:

| Piece | Days |
|---|---|
| Frame: sidebar of five views with counts, top bar, the shared object-page layout | 3 |
| The Inbox: one queue merging Needs attention, incidents, approvals and failed jobs; groups, filters, acknowledged, same-cause grouping at fleet scale | 6 |
| The keyboard layer (vendored script under the strict CSP; focus kept across htmx swaps and refreshes) | 2 |
| Object pages: the header line's resolver for device, change and incident; one timeline from the existing history sources | 7 |
| The step log for changes, fixes and heals, from the existing run stepper | 3 |
| Settings: five sections, search with marked matches, inline save, toggles; Network section regrouped | 5 |
| The palette and assistant: navigation, inline streaming answer, sources, hand-offs, pin to the side | 4 |
| The incident page redrawn on the shared layout | 2 |
| Manual pages, board fidelity records, browser tests at 1366 and phone width | 2 |

## Risks

1. **The header line is a verdict, and a wrong one looks right.** Each object needs one resolver
   that picks the single most important "what is wrong / what to do next" when several things
   are true at once (r2 has a change verifying, a drifted line and an unreadable alert source).
   A resolver that picks the wrong one, or a stale value drawn without its age, hides the real
   problem behind a calm sentence. It needs a declared precedence and the source's age on hover,
   and every input it ignored must stay visible in the timeline or the rail.
2. **One queue floods at fleet scale.** At 912 devices, one site outage can raise hundreds of
   rows and push the critical incident below the fold. The queue must group same-cause rows
   ("240 devices at site B unreachable: one row, one action") before it ships. Each source's
   row kinds then need a cause key. The keyboard layer adds a second, smaller risk: focus and
   selection must survive htmx swaps and live updates, or `j`/`k` lose their place. The palette
   overlay can also feel cramped for a long investigation until "Pin to the side" is built.
