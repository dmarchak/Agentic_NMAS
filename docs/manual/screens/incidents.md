# Incidents

**Incidents**, under **Troubleshooting** in the sidebar, lists every self-healing incident on
the network the page is about: what is open now, and how each closed one ended. It is each
incident's home: every row opens the [incident's own page](incident), and that page's
breadcrumb leads back here, to **Incidents**, then **Open** or **Closed**. Opening the list
starts nothing and changes nothing; nothing on it acts on a device.

The sidebar is navigation only: its **Incidents** item carries no count. [Needs
attention](needs-attention) is the one inbox and its badge the one count, and every open
incident that needs a person is on it, its item linking to that incident's page. Incidents is
where an incident lives, open or closed; Needs attention is where a person looks first.

The page opens with the control strip, for this network, the one place its switches are:
**Self-healing** (on is Auto until someone turns it off, on any network; off is Dry run) and
**Automatic AI troubleshooting** (on, the AI investigates by itself when Mercury's fix
fails; off, back to Manual), each with its gear to its full setting, both showing the state now
and usable only by a person who may change those settings. With open incidents Automatic would
start on, one line beside its switch says so ("Also starts on N open incidents, about $X"); it
is refused until the network's spending limits are acknowledged in Settings, and the refusal
links there ([the control strip](heal-batch#self-healing-toggle)). The top bar's status chip
opens it here.

## The last 30 days {#fleet-view}

Above the tabs, on both of them, the network's incidents at a glance:

- **The outcome line:** of the incidents detected in the last 30 days, how many were
  self-healed (Mercury fixed them, by its own fix or a saved script), AI-fixed (a person
  approved the AI's plan), person-fixed, and how many are still open; beside them, how many
  closed without a fix (cleared, declined, or closed with no proof of a fix) and how many were
  fixed with nobody recorded, when there are any.
- **A tile per category** (Interfaces, Routing, Config drift, Alerts, Other), each with its open
  incidents and a bar per day of its detections over the 30 days. A category is the kind of
  the incident's first symptom (an err-disabled port is Interfaces, an adjacency down is
  Routing), else of the change that opened it. SDN and Telemetry say what they need: their
  incidents are Needs attention's rows today, not this list's.

Each row also carries its **autonomy**: **Self-heal** (Mercury fixes it, or fixed it, with no
person), **AI + approval** (the AI has a part in it and a person approves its plan) or
**Manual** (a person fixes it).

## Open and Closed {#tabs}

Two tabs, each with its count:

- **Open**: every incident a person or Mercury still has to finish. A summary line first, its
  counts by what each waits for, then one group for each:
  - **Needs a person**: it stands on a decision only a person can act on, a proposed fix waits,
    a fix was applied and its verify failed, a fix a person ran stopped without fixing it, or
    its telemetry stream is lost (that fix changes the device's configuration, so a person
    approves it);
  - **Mercury working**: Mercury is working on it now, whatever the incident said before (a
    dry run's would-heal, a hold, Watching): a heal runs on it (its own, or one of a
    self-healing batch's restores), a saved fix runs on it, the AI is investigating it, or a
    fix a person approved is running or has passed its verify and waits for the symptom to
    clear;
  - **Watching**: Mercury is still reading the device, before it decides.
- **Closed**: how each one ended, who fixed it first:
  - **Fixed by AI**: an AI plan a person approved ran and was verified ("AI plan approved by
    <person> at <time>");
  - **Fixed by Mercury: saved script**: a saved fix's run verified it ("<fix>, learned from an
    AI fix on <device>, approved by <person> when saved");
  - **Fixed by Mercury** (no person took part: the network's policy, in Auto, applied it),
    **Fixed by a person** (a person approved the fix) and **Fixed, who is not recorded**;
  - **Cleared** (it closed with no repair recorded) and **Declined** (a person declined the fix
    that was proposed, and what it would have fixed has since gone: until then it is on Open,
    needing a person).

The tabs follow the incident's own page: an incident it says is resolved (Fixed, Cleared,
Declined) is on Closed, every other one on Open. An incident closes only on a healed outcome,
so one its record closed on a heal that did not heal, before only a healed heal closed an
incident, with nothing confirming the fix since, is on Open under **Needs a person**, with its
row on Needs attention; Mercury confirms it once by reading the device, and with its proof it
moves to Closed as Fixed ([Confirm first](heal#confirm)). Its state is the one the incident's
own page says, worked out by the same
code, so the list and the page never disagree. The time beside the tabs says when the list was
read; the list redraws itself whenever self-healing records a step.

## A row {#row}

Each row is a card of three lines: the incident's state (and **Drill** for a declared fault
drill, its id on hover: a drill never reads as real) and its title, the same plain-words title
as the heading of its page, its device on the title's hover; its impact, from Mercury's own
table; and its status:

- on **Open**, while Mercury works on it, what it is doing now, with a spinner: the step a run
  is on, counting the seconds since it began ("Self-healing: restoring edge2 · Apply",
  "Self-healing: fixing with saved script <fix> · verifying"), or the AI's investigation. A
  heal that is only starting reads "· starting". While it needs a person, why, in one short
  reason, word for word its page's status line (the same line its Needs attention row says): "A
  saved script can fix this: <fix>", "The AI's plan is ready: needs your approval", "Mercury
  refuses its fix as it stands: …", the AI's latest finding (labelled **AI**), a lost stream's
  "Mercury has no fix it runs by itself for a lost stream; …", "No saved fix for <cause> yet:
  the AI can investigate" or "No saved fix, and the AI found no safe plan"; with none of those, "Waiting for a person: " and the decision's own
  reason ("would put back “<line>” on <interface> (self-healing was in dry run)"), never a
  reasonless line. A held incident says what holds it and when the next automatic heal is
  allowed. Otherwise what it waits for, and when it began;
- on **Closed**, who fixed it, its time to repair, and when it ended (a fixed incident when its
  fix was verified, a declined or cleared one when it closed). A
  close on a verified run says who fixed it as its group does, and how long the problem lasted
  and how long the fix took ("lasted 6 min; the fix took 41 s");
- where the AI investigated it, **AI investigating since** its start while it runs, and its
  one-line outcome once it ended (what it proposes, or why it stopped), its **AI** label beside
  it, updated as the investigation starts and ends, with no reload.

Times are in your own time zone, with UTC on hover. Select the title to open the incident's
page, which has the whole story: its timeline, what Mercury did, and what to do.

## Search and the device filter {#search}

With many incidents, the groups start closed: open one to see its rows. Each group draws its
first 50 rows and says how many more it holds. To narrow the list, type words from a title, a
device or an incident's id in the search box, choose a device, and press **Show**: only the
incidents that match are drawn, with how many of the tab's match. **Show all** clears both.
Searching reads the list again and changes nothing.

## What is not listed {#not-listed}

- An incident folded into another (a symptom on a neighbour that joined the incident that
  caused it) is not a row of its own: it is part of the incident it joined, and its page
  opens that one. The list says how many were folded.
- Self-healing keeps a network's open incidents and its newest 200 closed ones. An older
  incident that reached a decision is still listed, from its step log, as its page is; one
  that never reached a decision is no longer kept. Every heal is also on
  [History](history).
- Only self-healing incidents are listed yet. An alert incident and an SDN incident are on
  [Needs attention](needs-attention) until their pages are built.
- **Problems** (recurring faults, one row per device and kind), **Drills** and **Reports**
  are planned for Troubleshooting and are not built yet.

## Self-healing {#self-healing}

The sidebar's **Self-healing** item, under Incidents, opens the network's
[Self-healing tab in Settings](settings#self-healing), where its policy and who is told are
set. The item carries no chip. While a network's self-healing runs in **Auto**, the top bar
says so instead ([the Self-healing chip](getting-started#self-healing-auto)); in dry run or
off nothing is drawn.
