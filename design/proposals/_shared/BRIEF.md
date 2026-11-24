# The proposals' shared brief (the week plan of 2026-11-23, Stage 3)

Every proposal draws the same screens on the same fake data, so the operator compares
directions, not content. Each proposal is a folder `design/proposals/<letter>-<name>/` with a
`README.md` and one static HTML file per screen below, linking `../_shared/tokens.css` and its
own `style.css`. No JavaScript is needed; where a state changes (a panel open, a step running),
draw the state the screen names. No CDN, no external font or image: system fonts and inline SVG.

## The screens (file names fixed across proposals)

1. `home.html`: what a person sees first: what needs them now (Needs attention: 3 critical,
   5 warnings, 2 waiting on a person), what is running, and the fleet at a glance.
2. `worst-1.html` and `worst-2.html`: the two worst card-heavy pages of today's interface
   (design/review/WORST_CARD_PAGES.md, ranks 1 and 2), redrawn in the proposal's direction with
   the same information.
3. `device.html`: a device's page (r2, an IOS-XE router): its state in one line, intent against
   what it runs, its checks, recent changes, its tabs (Overview, Intent, History, Monitoring,
   Logs, NetBox, Neighbours, Ask the device).
4. `settings.html`: Settings with five sections (Me, Network, Automation, AI, System), a search
   box, a one-line plain description under every setting, and toggles (not cards) for on/off.
   Draw the Automation section open, the search box holding "heal" with its matches marked.
5. `change.html`: a configuration change from click to verified, its progress tracker mid-run:
   Preview (the exact commands, a secret masked) done, Confirmed by hash done, Apply to r2
   (holding the device) done, Verify running (BGP hold time being waited out, "38 s of 90 s"),
   Record waiting; Roll back drawn as the step that runs only on failure.
6. `assistant.html`: the AI assistant open mid-answer on the incident "r3 OSPF neighbour to r4
   down", page context shown, the answer streaming with two sources (a manual section and a
   `show ip ospf neighbor` read of r3, each with Open), the model and the cost so far
   ("claude-sonnet · $0.004"), marked as AI, and a "Propose a fix" hand-off that opens the gated
   fix flow (the assistant never applies a change).

## Fake data (use only this; the repository is public)

- Network "Lab"; devices r1 to r6 (routers, IOS-XE), s1 to s4 (switches, IOS); addresses from
  192.0.2.0/24 and 2001:db8::/32 only; people "alex@example.com", "sam@example.com".
- For the fleet-scale screens, say "912 devices" in summaries and draw a filtered page of rows.

## Mercury's rules every proposal keeps (CLAUDE.md, "Product design and the interface")

- The screen answers the person's question; the evidence is one level down.
- Needs attention: each row names what is wrong, one action, and how it clears.
- A control is busy on itself until its answer arrives; the result updates in place; no toast.
- Large fleets: a list leads with counts by outcome, groups and collapses, filters and searches;
  never one long expanded list.
- Every action ends readable (a result, a refusal with its reason, a wait naming who). Colour is
  part of the result: never green over a partial.
- Absent and unreadable are different states; a stale source says its age ("checked 20 s ago").
- A device change: preview (exact, masked) → confirm by hash → apply holding the device → verify
  → roll back on failure → record.
- The rubric the build will be judged by: the answer within 5 s without scrolling at 1366x768;
  one home per task; toggles, not cards, for on/off; plain language; the same layout pattern on
  every page; a refresh keeps what the person was looking at.

## The README (each proposal)

Principles (5 to 8 lines), sources (from design/research.md, with links), how it answers each of
the four concerns (the AI assistant; dense pages without card overload; progress after a click;
minimalism without hiding information), what a person sees first, the clicks for the three most
common tasks (find why a device is unhealthy; push an intent change; turn a setting on), density,
how the assistant fits, how progress shows, an estimate of build days and the risks.
