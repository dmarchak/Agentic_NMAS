# Mercury GUI redesign: incident and automation boards (design brief)

**For:** Claude Code, working in `<account>`/Agentic_NMAS (Mercury).
**From:** the operator, after the CSCI 5840 Lab 10 demo on Nov 17, 2026.
**Status:** design brief. Draft the redesigned boards as reviewable mockups first. Ship nothing until the operator approves the mockups.
**Scope:** Mercury `main` (the Lab 10 server). **Don't touch the Lab 9 SDN kit or its pin.**

---

## 1. Why

The Lab 10 demo worked, but the GUI fell short of the other teams'. Their incident views showed an easy-to-read **chain of events, a summary, actions taken, and evidence** at a glance. Ours makes the engineer dig through cards and text to rebuild what happened.

Page loads were also slow:
- incident pages took more than 10 s, with a blank screen first;
- self-healing status updates lagged.

Other teams ran on localhost, so instant isn't the bar. Mercury goes over the internet, but it must still feel fast (targets in §6).

## 2. The operator's standing rules (they bind the design)

- **"AI makes a plan, a human approves it, that's it."** Approval is needed only for **changes to device configuration**. Read-only tools (show, ping, traceroute) never need it. Don't design in extra confirmation steps, gates or safety screens.
- Self-healing on plus an approved fix means it runs, with no holds.
- Only a **healed** outcome closes an incident.
- Model and effort per AI task will become user choices. Leave room to show which model ran and what it cost.
- The only AI limit the operator cares about is the **spending limit**. Show cost; don't build token-limit UI.

## 3. What the industry does (research summary)

| Pattern | Reference products | What to copy |
|---|---|---|
| **Answer first, in four lines** | incident.io Investigations; Datadog Bits AI SRE | A summary at the top: *what's happening, likely cause, the evidence for it, what to do next.* Bits ends with an evidence-backed conclusion **or an explicit "inconclusive"**. |
| **Hypotheses with evidence, ruled-out ones kept** | incident.io; Datadog | Each hypothesis links to its sources. Rejected theories stay visible with a reason, so the engineer can challenge them. |
| **Live reasoning, then a tree** | Datadog Bits (Investigation Steps → Hypothesis Tree) | While running: a live step log. When finished: a collapsible tree of what was checked and concluded. |
| **A sparse timeline you can expand and annotate** | incident.io timeline | The default shows key moments only (status and severity changes, pinned notes). "View all activity" shows everything. Events can be retitled and given descriptions. |
| **Category tiles, then issue rows** | Juniper Mist Marvis Actions | Tiles per category with open counts, plus a trend graph. Each issue row shows site, device, issue, **recommended action** and a "view more" for ports and details. |
| **A lifecycle and autonomy badge** | Juniper Marvis | The status flow is Open → In progress → **Self-driven** (awaiting validation) → **AI Validated**. A recurrence reopens the issue. Each action type is "self-driving" (autonomous) or "driver-assist" (needs a human). Filter by status; bulk status changes; CSV export. |
| **Confidence as a number** | PagerDuty Probable Origin | A right-side card with the top 3 likely origins, each with a **likelihood %**, link, service and status. It appears only when there are results. |
| **Correlation and tabs** | Moogsoft incident details | Correlated alerts become one incident. The header holds number, priority, severity and status. The body has tabs (Alerts / Metrics / Details). |
| **Runbook steps with per-step status** | Rundeck / PagerDuty Runbook Automation | Each workflow step is a row with a status icon, duration and an expandable output log. |
| **Accuracy reporting** | Datadog Reports tab; incident.io dashboard | Investigations over time, mean time to conclusion, and diagnosis accuracy. |

Sources:
- [Datadog Bits AI SRE: investigate issues](https://docs.datadoghq.com/bits_ai/bits_ai_sre/investigate_issues/)
- [incident.io: Investigations powered by Nexus](https://incident.io/blog/introducing-investigations-powered-by-nexus)
- [incident.io: incident timeline](https://incident.io/changelog/tell-the-full-story-with-your-incident-timeline)
- [Juniper Marvis Actions overview](https://juniper.net/documentation/us/en/software/mist/marvis/topics/concept/marvis-actions-overview.html)
- [PagerDuty Probable Origin](https://docs.pagerduty.com/ai-automation/aiops/probable-origin)
- [Moogsoft incident details](https://docs.moogsoft.com/moogsoft-cloud/en/incident-details.html)

## 4. Boards to redesign

Draft each board as a mockup with **realistic data taken from real Mercury records**. Use the Lab 10 demo incidents: r6, r7, s5, the five injected faults and their self-heal and AI runs. Don't invent data shapes Mercury doesn't have. Where a panel needs data Mercury doesn't record yet, mark it **"needs: …"** on the mockup.

### 4.1 Incident detail (the priority)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ r7 · Gi0/1 down · Sev 2 · OPEN 4m12s        [model · $0.004]                  │
│ ●Detected ─ ●Self-heal tried ─ ●Diagnosing ─ ◉Fix proposed ─ ○Approved ─     │
│   ○Applying ─ ○Verifying ─ ○Healed           (each node: time; click = jump)  │
├──────────────────────────────────────────────┬───────────────────────────────┤
│ SUMMARY                                       │ CONFIDENCE                    │
│ What: …   Likely cause: …                     │ Hypothesis A  82%  chosen     │
│ Evidence: [show int Gi0/1] [syslog 14:02]     │ Hypothesis B  11%  ruled out  │
│ Next: Approve plan P-123 (2 commands)         │                               │
├──────────────────────────────────────────────┤ RELATED                       │
│ PLAN  P-123   risk: low   [ Approve ]          │ Past: r7 Nov 12 healed by …   │
│  1 interface Gi0/1 / no shutdown   ○ pending   │ Same device: 2 in 7 d         │
│  2 (verify) show int Gi0/1         ○ pending   │                               │
│  → after approval each row: ✓/✗ · 1.2 s · ▸log │ AI CALL                       │
├──────────────────────────────────────────────┤ model · tokens · $ · latency  │
│ HYPOTHESES (tree)  ▸ A … evidence chips       │                               │
│                    ▸ B ruled out: reason      │                               │
├──────────────────────────────────────────────┴───────────────────────────────┤
│ TIMELINE (key moments) ··· [View all activity]                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Lifecycle bar.** Mercury's real states: Detected → Self-heal tried (script name; success or fail) → Diagnosing (AI) → Fix proposed → Approved (by whom) → Applying → Verifying → **Healed** or **Failed / Needs attention**. Every node shows a timestamp and links to its timeline entry. This bar *is* the "chain of events".
- **Summary card.** Exactly four lines (What / Likely cause / Evidence / Next), generated from the existing AI response and self-heal records. If the AI ended without a fix, say **"Inconclusive: …"** plainly.
- **Evidence chips.** Every claim in the summary and the hypotheses carries chips: a show-command output, a syslog line, a metric sparkline, a config diff. Clicking a chip expands the raw evidence inline, masked as today.
- **Plan card.** Shows the command diff and risk, with **one Approve button** (only because the plan changes config) and no other confirmations. After approval it becomes a runbook view: per-step ✓/✗, duration, expandable output, then the verify results. Read-only steps run without approval.
- **Hypotheses.** A collapsible tree: the chosen hypothesis plus the ruled-out ones, each with a one-line reason and evidence chips. Show the live step log while the AI is still running.
- **Right rail.** Confidence (top 3, with %), related and past incidents (same device or same fix script, and how they were resolved), the AI call (model, tokens, $, latency, link to History).
- **Timeline.** Key moments only by default, with "View all activity" for the full log. No video timestamps or demo-specific text.

### 4.2 Incidents board / Needs attention (fleet view)

- **Category tiles** (Interfaces, Routing, Config drift, Telemetry, SDN, …), each with open counts and a 30-day trend sparkline.
- **Outcome strip:** "this period: N self-healed · N AI-fixed (approved) · N human-fixed · N open". This is Mercury's version of Marvis's resolved list.
- **Issue rows:** device · issue · lifecycle badge · recommended or running action · age · autonomy badge (**Self-heal** / **AI + approval** / **Manual**). Rows are sortable and filterable by status, and can be exported to CSV.
- **Status filters** mirror the lifecycle. A recurrence reopens the incident and shows "recurred ×N".

### 4.3 Automation runs (self-heal scripts and approved AI plans)

- A runbook-style execution view, also used inside 4.1's plan card: trigger, steps with status, duration and output, verify outcome, the incident it closed, and who approved it (where approval applied).
- Keep the list as **one sortable list with a Source column (AI / Manual)**, as the operator asked for the Fixes page.

### 4.4 AI analysis results (the SDN analyst, B1/B4 findings)

- The same summary-first card. Findings appear as rows with severity, a one-line why and evidence chips.
- The planted-issue sheet sits beside them (found / missed / why). Keep the existing data; only the presentation changes.

### 4.5 Reports

Show incidents over time, mean time to heal, self-heal success rate, AI diagnosis accuracy (from the existing "you said right / wrong" verdicts) and AI cost per week.

## 5. Visual and interaction rules

- **Scannable at a glance:** status colour and lifecycle position must read in under 2 seconds from across the room. That's the demo test.
- **One primary action per screen state.** Usually it's nothing, sometimes Approve.
- **Progressive disclosure:** summaries first, raw output behind chips and "view more".
- **Live updates** while an incident is active (the existing live channel), changing only what changed. Never blank the page.
- **Consistent badges** across all boards for lifecycle, autonomy and source.
- Dark and light themes both readable; it must work at a 1080p projector size.

## 6. Performance requirements (part of the redesign)

**Targets** (Mercury hosted, reached over the internet):
- **Server time ≤ 300 ms** for the page shell.
- **First useful content ≤ 1 s.**
- **Each async panel ≤ 1.5 s.**
- **Live status changes visible ≤ 2 s** after they happen.
- **No blank screens**, ever.

Method:
1. **Measure before changing anything.**
   - Add `Server-Timing` headers per section (database, NetBox, AI history, metrics) on the incident, incidents-list and fixes pages.
   - Record cold and warm timings from the laptop over the real network path.
   - Report the top 5 costs per page.
2. **Shell first:** render the header, the lifecycle bar and the summary from one indexed query. Load the slow panels (evidence, hypotheses, related, metrics) asynchronously behind skeletons.
3. **Precompute:**
   - Store each incident's summary, lifecycle state and counts when they change. Don't rebuild them on every load.
   - Remove per-row repeated NetBox or database calls (N+1 queries).
4. **Payload:** compression on, paginated lists, long cache headers on static assets.
5. **Re-measure** and include before/after numbers in the report.

## 7. What to deliver, in order

1. **Inventory (read-only).** For each current page that 4.1–4.5 replace:
   - its route, templates and data sources;
   - what's already recorded versus missing for each panel;
   - the measured load timings from §6 step 1.
2. **Mockups** of 4.1 and 4.2 first, then 4.3–4.5:
   - static HTML in a `design/` folder (no production routes changed);
   - filled with real records from the Lab 10 demo incidents;
   - with screenshots at 1920×1080 and at phone width.
   - Mark every "needs: …" data gap.
3. **Wait for the operator's review** of the mockups. The operator marks changes. A screen counts as approved once the operator says so for it.
4. **Then a build plan:** phased, with the performance work (§6 steps 2–4) first, since it helps the current pages too. Follow the usual rules: tests, deploy only via nmas-deploy, never 02:30–03:30 Denver, and tell the operator before every deploy.

## 8. Out of scope

- The Lab 9 SDN kit and its pin (the lab is in progress, due Nov 30).
- Changing AI behaviour, prompts or approval rules. This is presentation and performance only.
- New features beyond the panels above, unless a mockup shows a data gap that blocks a panel. Name the gap; don't build it.
