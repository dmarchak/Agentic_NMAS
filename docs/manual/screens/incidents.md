# Incidents

**Incidents**, under **Troubleshooting** in the sidebar, lists every self-healing incident on
the network the page is about: what is open now, and how each closed one ended. It is each
incident's home: every row opens the [incident's own page](incident), and that page's
breadcrumb leads back here, to **Incidents**, then **Open** or **Closed**. Opening the list
starts nothing and changes nothing; nothing on it acts on a device.

The sidebar's **Incidents** item counts the open incidents ("3 open"), outlined: a count of
things, not an alarm. [Needs attention](needs-attention) keeps the one red badge, and stays
where a person looks first: each of its items about an incident links to that incident's page.

## Open and Closed {#tabs}

Two tabs, each with its count:

- **Open**: every incident a person or Mercury still has to finish. A summary line first, its
  counts by what each waits for, then one group for each:
  - **Needs a person**: it stands on a decision only a person can act on, a proposed fix waits,
    a fix was applied and its verify failed, a fix a person ran stopped without fixing it, or
    its telemetry stream is lost (that fix changes the device's configuration, so a person
    approves it);
  - **Mercury working**: Mercury is fixing it now, or a fix a person approved is running or has
    passed its verify and waits for the symptom to clear;
  - **Watching**: Mercury is still reading the device, and decides once its reads agree, after
    the grace period.
- **Closed**: how each one ended. **Fixed by Mercury** (no person took part: the network's
  policy, in Auto, applied it), **Fixed by a person** (a person approved the fix), **Fixed, who
  is not recorded**, **Cleared** (it closed with no repair recorded) and **Declined** (a person
  declined the fix that was proposed).

The state is the one the incident's own page says, worked out by the same code, so the list
and the page never disagree. The time beside the tabs says when the list was read; the list
redraws itself whenever self-healing records a step.

## A row {#row}

Each row is one line: the incident's state (and **Drill** for a declared fault drill, its id on
hover: a drill never reads as real), its title, the same plain-words title as the heading of
its page, its device, and:

- on **Open**, what it waits for ("a fix waits for a person's approval") and when it began;
- on **Closed**, who fixed it, its time to repair, and when it ended (a fixed incident when its
  fix was verified, a declined one when the fix was declined, a cleared one when it closed).

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
set. Its chip says the mode that runs now: **Off**, **Dry run** (every step but the apply) or
**Auto**, after the installation's stop switch, the policy's confirmation and its expiry, with
the policy's own sentence on hover.
