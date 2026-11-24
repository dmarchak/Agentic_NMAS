# Direction C, "Document": one readable page per object

Every page in Mercury reads top to bottom like a well-edited document. It opens with one plain
sentence that answers the person's question, then a short list of key facts, then sections the
person can open for the evidence. There are no cards anywhere. Hairline rules, whitespace and
type carry the structure.

## Principles

1. **The first sentence is the answer.** Under every title is one sentence in plain language
   ("r2 is reachable and runs its intent; one change waits for approval"), with the source's
   age on the line below it.
2. **Then the key facts,** as a two-column definition list: eight pairs at most, each with its
   provenance in muted type beside it.
3. **Then the sections, each one level down.** Each section is a native `<details>` element
   with a heading and a one-line summary. Its state sits on the right of the heading. Closed,
   a section still says what it holds.
4. **An outline on the right** lists the page's sections and each one's state, so the shape of
   the page and anything wrong in it can be seen without scrolling.
5. **No cards.** Rules, whitespace, a 15px body and strong headings do the work that boxes do
   today. A fleet is a table with a sentence of counts above it.
6. **Every page has the same skeleton:** crumbs, title, sentence, facts, sections, outline.
   Learning one page teaches all of them.
7. **Status is a mark and a word** (a diamond for critical, a square for warning, a dot for OK,
   a ring for waiting, a dashed ring for unknown), never colour alone.

## Sources

From [design/research.md](../../research.md):

- **Disclosure only for supplements:** the answer stays on the surface, and each chevron has a
  text label. See [Primer progressive disclosure](https://primer.style/product/ui-patterns/progressive-disclosure)
  and [Carbon disclosures](https://carbondesignsystem.com/patterns/disclosures-pattern/) (research d1).
- **Evidence one level down:** a verdict opens to its cause and then to the affected items.
  See [Mist SLEs](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/service-level-expectations.html)
  and the [Grafana panel inspector](https://grafana.com/docs/grafana/latest/panels-visualizations/panel-inspector/) (research d2).
- **Status as shape, symbol and word:** see [Carbon status indicators](https://carbondesignsystem.com/patterns/status-indicator-pattern/) (research d6).
- **A vertical stepper for a known linear flow:** see the [Carbon progress indicator](https://carbondesignsystem.com/components/progress-indicator/usage/).
  Steps open their own logs, as in [GitHub Actions run logs](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs) (research c4, c5).
- **Jobs outlive the page:** see [Track Copilot sessions](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/track-copilot-sessions) (research c6).
- **An assistive side panel:** see the [Microsoft Copilot UX guidance](https://learn.microsoft.com/en-us/microsoft-cloud/dev/copilot/isv/ux-guidance)
  and the [Grafana Assistant](https://grafana.com/blog/llm-grafana-assistant/). Cited sources
  open in a Sources view, as in [Grafana Workspace](https://grafana.com/docs/grafana-cloud/machine-learning/assistant/workspace/).
  A change is handed off as a plan a person approves, as in [Vercel Agent permissions](https://vercel.com/docs/agent/chat/permissions) (research a1, a5, a8).
- **AI labelled, with its cost:** see [Carbon for AI](https://carbondesignsystem.com/guidelines/carbon-for-ai/)
  and [Vercel Agent pricing](https://vercel.com/docs/agent/pricing) (research a6, a7).
- **Counts by outcome first; a table for a fleet:** see the [Marvis Actions overview](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-actions-overview.html)
  and the [Carbon data table](https://carbondesignsystem.com/components/data-table/usage/) (research b1, b2).

## The four concerns

- **The AI assistant.** The assistant is a 500px drawer that slides in from the right edge.
  The page behind it is dimmed but stays readable, so the person can check the incident
  against the answer. The drawer has three tabs: Ask, Sources and History. Its context line
  names what it is looking at (an incident, its devices, a time window), and the person can
  change it. Answers stream with numbered citations. Each source is listed with what it is and
  when it was read, and each has an Open button. The drawer's foot always shows the model and
  the cost so far, and the AI tag marks everything the model wrote. "Propose a fix" hands off to
  the normal gated flow (preview, confirm by hash, apply, verify, record). The assistant never
  applies anything.
- **Dense pages without card overload.** Structure comes from type and rules. A page's sections
  collapse to one line each, which still carries its state and its gist. The outline gives the
  whole page's shape at once. Worst-1 replaces 18 cards with 8 sections under one search, and
  the one consequential setting, Inventory source, comes first. Worst-2 replaces about 13
  nested cards with one sentence, eight facts and eight sections.
- **Progress after a click.** A control is busy on itself while it waits (the drawer's Stop
  button shows this). A device operation gets a page of its own with a vertical stepper pinned
  under the title. Each step shows its time and one line of what it did, and a step can open
  its evidence. A running step names what it is waiting for, with a bar ("waiting out BGP
  hold time, 38 s of 90 s"). Roll back is drawn as a dashed step that runs only if Verify
  fails. Leaving the page doesn't stop the job, which stays under Running now.
- **Minimalism without hiding information.** Nothing needed to decide is collapsed: the
  sentence, the facts and the one action are always on top. A closed section is never silent,
  because its summary line names what is inside it ("Loki read 9 min ago (promise 2 min)"), so
  a problem shows even while folded. Unknown, stale and absent each have their own mark and
  their own words.

## What a person sees first

The sentence under the title. On the home page: "Three things need you now: r3 lost its OSPF
neighbour to r4, r5 stopped answering, and s4 lost its management access list." Right below
it, at 1366x768 and without scrolling, come the key facts and the first section's rows, each
with its one action.

| Screen | What it shows first |
|---|---|
| `home.html` | The sentence naming the three critical items, the facts (3 critical, 2 waiting, 5 warnings, 2 running, 898 of 912 healthy), then the critical rows, each with what is wrong, since when, how it clears and its action |
| `device.html` | "r2 is reachable and runs its intent; one change waits for approval", r2's facts (reachable, addresses, intent and golden commits, what it runs), then Intent against what it runs with the pending change and Review change |
| `settings.html` | "Self-healing proposes and never applies by itself", the search box holding "heal" with its 7 matches counted by section, and the Automation section open with the matches marked, the toggles, and the unsaved change pinned to the foot |
| `change.html` | "Applied to r2; now verifying", then the stepper pinned under the title: three steps done, Verify at 38 s of 90 s, Record waiting, and Roll back as a conditional step |
| `assistant.html` | The incident page dimmed behind the drawer, which opens with its context line, the question, the answer streaming with citations, two sources each with Open, Propose a fix, and the model and cost |
| `worst-1.html` | Settings › Lab › Network: "Lab's 912 devices come from NetBox, read 4 min ago", with Inventory source first, not after 14 single-number cards |
| `worst-2.html` | The incident: "r3 lost its adjacency to r4 at 10:42; the likely cause is r4's hello interval…", one Review the fix button, eight facts, the proposed fix, then why |

**Worst-1 and worst-2** are ranks 1 and 2 of `design/review/WORST_CARD_PAGES.md`. Rank 1 is
Settings › *network* › Network (18 cards). Rank 2 is the Incident page (about 7 top-level
cards and 6 nested). Both keep their page's information:

- **Worst-1:** inventory source with skipped devices and warnings, excluded VRFs, the reads
  engine settings, the configuration read timeout, endpoint timings, deploy workers, the
  failure limit, verify settle windows (now a table, not raw JSON), retention, Auto duration,
  SDN escalation, code repository, What AI may send, and Delete. Each value says where it
  comes from.
- **Worst-2:** the summary, hypotheses (chosen and ruled out), the "needs" notes for
  confidence, severity and risk, the AI call, the fix and its guards, evidence, timeline, What
  Mercury has done, Seen before, and The record.

## Clicks for the three most common tasks

| Task | Clicks | Path |
|---|---|---|
| Find why a device is unhealthy | **1** | Home: the critical row's action (Open incident, or Diagnose r5). The incident page's first sentence names the likely cause, and Evidence is one more click. From a device page, the answer is its first sentence (0). |
| Push an intent change | **3** + typing | Device page: Change intent (1). Edit the intent, then Preview (2). Confirm by hash (3). The change page opens with its stepper. A second person's approval is theirs, from their home page's "Waiting on a person". |
| Turn a setting on | **2** + typing | Settings (1), type in the search, then press the toggle (2), which saves in place. A self-healing policy setting adds Preview the change and Confirm by hash (4). From the top bar, "Go to a device, page or setting" opens the setting itself (1 + typing, then the toggle). |

## Density

The body is 15px with a 1.6 line height, and the document column is about 860px at 1366
wide. A table row is about 40px, and the facts list holds 8 pairs in 4 rows. At 1366x768 the
title, sentence, facts and the first section's first 2 or 3 rows fit above the fold. That is
less dense than a dashboard, on purpose. Fleet lists keep density through tables, which a
long list pages and groups (a sentence of counts above, then groups that collapse).

## How the assistant fits

Ask in the top bar, "Ask about r2" on a device, and "Ask the assistant" on an incident all
open the same drawer, with that page's context attached. The drawer stays open across
navigation, as the Grafana Assistant's sidebar does, and its History tab keeps past questions.
Spend shows in the top bar's AI chip and at the drawer's foot. The drawer never draws an apply
button; "Propose a fix" leads into the ordinary change flow.

## How progress shows

- **Under about 10 seconds:** the control is busy on itself and its answer replaces it in place.
- **Longer, or any device operation:** a job page with the pinned vertical stepper, each step
  showing its time, one line of what it did, and "show evidence".
- **On the home page:** "Running now" says one line per job ("r2 verifying (38 s of 90 s)").
  The device's Held by fact names the job holding the device.

## Estimate

About **30 build days**:

- The frame, the stylesheet and the outline component: 2 days.
- Home: 1.5 days.
- The device Overview and its tabs in the new skeleton: 3 days.
- Settings regrouped into five sections with server-side search, including Network: 5 days.
- The change page on the existing run stepper: 1.5 days.
- The assistant drawer on the existing assistant panel: 2 days.
- The incident page: 2 days.
- The remaining v2 pages moved to the skeleton: 9 days.
- Board fidelity, the manual and test churn: 4 days.

## Risks

1. **The sentence can be wrong while looking right.** Every page's first line is new code,
   composed from the same facts the page draws below it. If its builder misses a state (a stale
   source, a partial verify), the most-read line on the page is the wrong one. Each sentence
   needs one builder per page, fed by the same model as the facts, with tests that put each
   unreadable and partial state through it.
2. **A folded section still hides things, and long pages scroll.** The outline's states and
   each section's summary line carry the warning while it is closed. But open and closed state
   must survive a refresh (in the URL hash) to meet "a refresh keeps what the person was
   looking at". Below about 1280px the outline has to fold into a line under the title. Pages
   with many sections, such as Settings, depend on search working well.
