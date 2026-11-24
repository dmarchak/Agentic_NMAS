# Direction A: Workbench (list and detail)

Every section of Mercury uses one frame. On the left is a dense list: counts by outcome, filters
and search, and grouped rows that collapse. In the middle is the selected item's detail. On the
right, the assistant is docked as a collapsible column. A person never leaves the list to look at
one thing, and every page has the same layout, so learning one page teaches all of them.

Screens: [home](home.html) · [worst-1](worst-1.html) · [worst-2](worst-2.html) ·
[device](device.html) · [settings](settings.html) · [change](change.html) ·
[assistant](assistant.html). Each links `../_shared/tokens.css`, then `style.css`. There is no
JavaScript. Each screen draws the state the brief names.

## Principles

1. **List on the left, detail on the right, on every page.** Selecting a row swaps only the
   detail. The selection is kept in the URL, so a refresh shows the same item.
2. **Counts by outcome come first.** Each list opens with a strip of counts by outcome, and each
   count is a filter. Healthy is a number, not 889 rows.
3. **Detail is made of sections, not cards.** Hairlines separate the sections. A sticky outline
   inside the pane lists them with their counts. The section that needs acting on comes first.
4. **The answer is in the header.** The detail header holds the item's state in one line, its
   one action and, while work runs, a step strip. Evidence is one level down.
5. **The sidebar is a 52 px icon rail.** That width goes to the list. Labels show on hover, and
   the `»` button expands the rail.
6. **The assistant is a third column.** It is collapsed to a 36 px strip until opened. Its
   context is the selected item, shown as chips.
7. **Dense but calm.** Body text is 13 px. Rows are 30 px in tables and about 44 px with a second
   line. There is one accent colour (`--accent`). Status colours always come with a word, and
   AI is always marked in `--ai`.

## Sources (design/research.md)

- Master-detail, peeking at one item without leaving the list (research b5):
  [Linear Peek](https://linear.app/docs/peek),
  [Datadog Infrastructure List](https://docs.datadoghq.com/infrastructure/list/).
- Counts by outcome first, each a filter (b1):
  [Marvis Actions](https://networkingdocs.hpe.com/documentation/us/en/software/mist/mist-aiops/topics/concept/marvis-actions-overview.html),
  [Carbon status indicators](https://carbondesignsystem.com/patterns/status-indicator-pattern/).
- Compact tables and grouped lists with sticky headers (b2, b3):
  [Carbon data table](https://carbondesignsystem.com/components/data-table/usage/),
  [Linear display options](https://linear.app/docs/display-options),
  [Grafana alert rules](https://grafana.com/docs/grafana/latest/alerting/monitor-status/view-alert-rules/).
- Filter chips and a stated subset (b4):
  [Stripe filter controls](https://docs.stripe.com/stripe-apps/patterns/filter-controls.md).
- An assistant in a side panel that stays open, with page context as tags (a1, a3):
  [Grafana Assistant](https://grafana.com/blog/llm-grafana-assistant/),
  [Grafana Workspace](https://grafana.com/docs/grafana-cloud/machine-learning/assistant/workspace/),
  [Microsoft Copilot UX guidance](https://learn.microsoft.com/en-us/microsoft-cloud/dev/copilot/isv/ux-guidance).
- Citations, an AI label, cost shown, and a hand-off as a plan a person approves (a5 to a8):
  [Datadog Bits Investigation](https://docs.datadoghq.com/bits_ai/bits_investigation/investigate_issues/),
  [Carbon for AI](https://carbondesignsystem.com/guidelines/carbon-for-ai/),
  [Vercel Agent permissions](https://vercel.com/docs/agent/chat/permissions).
- Feedback that fits how long the work takes, busy on the control, and jobs that outlive the page
  (c1, c2, c6):
  [Primer loading](https://primer.style/product/ui-patterns/loading),
  [Carbon inline loading](https://carbondesignsystem.com/components/inline-loading/usage/),
  [Copilot sessions](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/cloud-agent/track-copilot-sessions).
- A progress indicator for a linear flow (c4):
  [Carbon progress indicator](https://carbondesignsystem.com/components/progress-indicator/usage/).
  This direction draws it horizontally, in the header. Carbon recommends a vertical one; see
  Risks.

## How it answers the four concerns

**The AI assistant.** It is a column docked on the right of every page. Collapsed, it is a 36 px
strip that names its context ("Ask about r2") and has the `.` shortcut. Open, it is 360 px wide
and the detail's outline folds away to make room. Its context is the selected item, drawn as
chips (incident, r3, r4) under the header. Every answer carries the AI label, the model, and the
cost so far ("claude-sonnet · $0.004"). Each source is numbered in the text and has its own Open.
"Propose a fix" hands off to the gated fix flow (preview, then confirm by hash), and the panel
says that the assistant never applies a change. While an answer streams, Stop is busy on itself.

**Dense pages without too many cards.** No page uses a card. A list row is one line plus one
quieter line. Detail sections are separated by hairlines and listed in a sticky outline. Each
setting is one row: a label, one plain sentence, and its control (a toggle, a segmented choice or
a number). The two worst card pages show the effect. Settings › Network had 18 cards: it becomes
15 index rows and 7 outlined sections with one Save bar. The Incident page had 4 story cards
before the card holding the action, and 6 more nested inside it: it becomes a header with the
title, the state and the action stated once, a step strip, and 5 sections.

**Progress after a click.** A control is busy on itself until its answer arrives. Work that runs
longer than about ten seconds becomes a job, drawn in three places that read the same
announcements:
- A step strip in the detail header (see [change](change.html)). It has done, running, waiting
  and on-failure-only states. The running step names its wait ("38 s of 90 s") and has a bar.
- A five-segment mini strip on the job's list row and on any related item, such as r2's device
  page.
- The Activity tray in the top bar, drawn open on [device](device.html). It lists everything
  running, then what finished in the last hour, each with Open.

**Minimalism without hiding information.** Nothing is folded away that answers the question. The
header states the answer, the first section is the one to act on, and the other sections are one
scroll or one outline click away, never behind a disclosure. Collapsing is only for groups of
like rows ("8 sections match", "5 more verified today", "Other sites 902"), and each collapsed
group gives its count. Unreadable and absent are separate states: a dashed ring with
"could not be read", against "not compared" or "none".

## What a person sees first

The top-left of the list pane on Needs attention: 10 rows, of which 3 are critical, 5 are
warnings and 2 are waiting on a person. Under that is the fleet as one bar (912 devices: 889
healthy, 14 drifting, 6 not answering, 3 not read yet), then what is running ("r2 change
verifying 38/90 s · drift check 412/912"). The rows follow: critical first, then those waiting on
a person, then warnings. The top critical row is already selected, so the detail pane answers it:
what is wrong, the one action ("Open the incident") and how it clears. All of this shows without
scrolling at 1366x768.

## Clicks for the three most common tasks

| Task | Path | Clicks |
|---|---|---|
| Find why a device is unhealthy | Needs attention already lists it: click its row, and the detail shows what is wrong and the evidence. If it is not listed: Devices, the "Drifting" or "Not answering" count, then the row; the Overview's first section is the difference and the checks follow. | **1** (3 by Devices; 0 by typing its name after `/`) |
| Push an intent change | Devices, the r2 row, Change intent… (edit in place), Preview, then Confirm by hash. Apply, verify and record then run with no further click, shown in the step strip. | **5** from home (3 from the device page) |
| Turn a setting on | Settings, type in the search (rows are marked as you type), click the toggle, then Save in the bar at the bottom. A self-healing setting asks Preview and confirm…, then the confirm with a reason. | **3** (4 for a heal setting) |

## Density

At 1366x768, Needs attention shows the counts, the fleet bar and the running line in the list.
Below them come the 3 critical rows, the 2 waiting on a person and the first warnings; the last
warnings are one scroll away. The detail shows the whole first answer. The device list shows 10 devices in two groups, with
the address, intent and age of each. Settings shows 12 matching settings in the index and 7
setting rows in the detail. At 1920x1080, the list stays 392 px wide and the detail grows.

## How the assistant fits

The assistant is the third column of the frame, not a pop-over. It never covers the item it is
asked about. It is collapsed by default and remembers per person whether it is open. Opening it
narrows the list to 340 px and folds the outline into the tabs, so the detail keeps about 610 px
at 1366. Asking about a list row or a failed check sets the context to that object, and the chips
show and remove it. Its fix hand-off goes into the same change flow and step strip as any other
change (see [change](change.html)).

## How progress shows

A control is busy on itself, with no toast. The result updates in place, and colour is never
green over a partial result. A long job gets the step strip in its detail header. The order is
Preview, Confirmed by hash, Apply (holding the device), Verify, Record, and then Roll back, drawn
apart with a dashed edge and "runs only on failure". The verify section comes first under the
header while it runs, with every check and its age. The same job shows as a mini strip on related
rows and in the Activity tray. Incidents use the same strip (Detected, Diagnosed, Fix proposed,
Approve by hash, Apply and verify, Record), so one visual teaches both.

## Estimate and risks

**About 50 build days:**

| Work | Days |
|---|---|
| The frame: top bar, icon rail, three-column grid, selection in the URL, keyboard | 5 |
| The list component: summary strip, chips, sticky groups, paging at 900+ rows | 5 |
| Detail sections with a sticky outline, and the step strip with the tray on the existing announcements | 6 |
| The assistant restyled as a docked column with context chips | 3 |
| Porting the sections: Needs attention 2, Devices and their 8 tabs 6, Changes 3, Incidents 4, Settings with search, rows and one Save 6, the other 11 sections 8 | 29 |
| Manual pages, board fidelity, and test churn | 2 |

The days for manual pages, board fidelity and test churn are a floor. They are likely more.

**Top two risks:**
1. **Width.** At 1366 with the assistant open, the detail has about 610 px, and wide tables (the
   evidence table, intent against running) must reflow. Below about 1200 px, the list has to
   become a drawer, and that breakpoint is not drawn here. Pages that are not lists at heart
   (Topology, Monitoring's dashboards, SDN's flows) fit list and detail poorly. They would need a
   full-width mode that the frame allows but this proposal does not draw.
2. **Every section splits into a list fragment and a detail fragment.** Each section needs a list
   endpoint and a detail endpoint, with the selection kept in the URL. The device page becomes
   the Devices list's detail, and a full-width "open alone" view is still needed for links
   shared from outside. That doubles the routes the invalidation map and the page-request tests
   cover. The horizontal step strip also goes against Carbon's advice to draw progress vertically
   and not for conditional steps. This proposal keeps the strip horizontal so it fits in the
   header, and sets the conditional Roll back apart.

## Notes on the drawings

- worst-1 and worst-2 are WORST_CARD_PAGES.md's ranks 1 and 2: Settings › Lab › Network, and the
  Incident page. Each keeps the information of today's template (`templates/v2/settings.html`
  with its 14 `_settings_card.html` groups, `_network_source.html`, `_code_repo.html`,
  `_ai_classes.html` and `_network_delete.html`; `templates/v2/incident.html` with
  `_inc_story.html` and `_fixit_section.html`). On the Incident page, the AI call's model,
  tokens and cost, the timeline and the record are moved one tab down.
- The "Self-healing: Auto lasts" card moves from Settings › Network to Automation ›
  Self-healing, so it has one home. Settings › Network links to it.
- The Activity tray is drawn open only on [device](device.html). It is a drop-down, so it covers
  part of the detail on that screen.
