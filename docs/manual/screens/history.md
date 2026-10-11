# History

What happened to the network and its devices, and when: one timeline of everything the tool
records, the network's baselines, and the Oxidized divergences people once authorised, with
the remote's state at the top.

## The remote {#remote}

One sentence says whether everything is committed and whether it is pushed to the network's
remote repository, with when that was last checked. **Verify the remote** runs the read-only
checks against it (the key's scope, a read, that it is private and the right repository).
**Push now** appears while something is not pushed; it needs a person, and the sentence
redraws once the remote is read again.

Under it, from the network's own record, so they stay whatever redraws the card:
- the last failed push: when, who and why. A successful push clears it.
- the last Verify: when, who, and whether every check passed or which failed.

## Timeline {#timeline}

Every record the tool keeps, across every device, newest first, for the time you choose (7 days
by default). It also holds the records that belong to no one device: a commit to the monitoring
profile or the templates, a Save All's baseline decision, an update of the app. A device's
History tab is this same timeline filtered to that device, read by the same code, so the two
can never show different things.

Each record is one line:

- **When.**
- **Kind.**
- **Device:** one device, a few, how many, "every device" (a window for the whole list), or
  **fleet** for a record about no one device.
- **What.**
- **Who.**

Open a line for the full record underneath. It shows:

- the reason and each step with its result;
- how the person was identified;
- for a commit, **Show the change**: its diff, with every secret masked;
- **Open (device)'s History** for each device the record names.

The Baselines and Authorisations tabs work the same way, with each baseline's reasons and each
authorisation's stated reason under its line.

Filters:

- **Device:** that device's records only; the fleet's own records drop out.
- **Person.**
- **Kind,** in four groups:
  - **The repository:** commits (golden, intent, profile) and measured-unchanged saves.
  - **What ran on a device:** deploys and restores, rotations, persists, onboarding and adopt,
    runs cut off midway, and authorised retries.
  - **What happened to a device:** restarts and planned windows.
  - **Decisions and records:** approvals, acknowledgements, freshness authorisations,
    break-glass exports, baseline decisions and app updates.
- **Since.**

**Every kind** and **Commits only** are one click away. Each filter is part of the page's
address, so a view is a link you can share. A long list shows the newest and says how many there
are, with **Show more**. A record store that could not be read is said above the list. A
commit whose record is known to be wrong says so in its row.

## Reveal a version {#reveal}

A golden row (on a device's History tab, or on History when the commit is one device's) offers
**Reveal <device>'s version…**: the device's golden at that commit, unmasked, drawn under the
row. **Show the change** is masked, like every screen; a reveal is the one place secrets are
drawn in the clear. It needs a verified person, and it is recorded in the reveal record (who,
when, which device and which commit) before the text is drawn; a refusal draws nothing.

## Query {#query}

Ask the network's history, starting from a question. The tab says first **what the history
holds**: how many days of metrics are kept at full detail and whether a long-term store answers
past them (both from this network's settings), and how long logs are kept and when the log
store began (the logs reader's own count). Then the **ready-made questions**, each opening its
answer: **Syslog by device** opens the network's syslog by device (see [Logs](logs));
**Interface errors and discards over time** opens a chart of discards per second, for every
device or, choosing one, by its interfaces, over 24 hours to a year. It is asked of the
network's Grafana the way a Monitoring panel is, from the store that keeps the range: a range
past the days the live store keeps is refused, naming the setting, unless a long-term store is
set. Its own query is shown under the chart; the device, the interface and the range are in
the address, so Copy the link carries the question. **CPU and memory trend** is asked the same
way, per device: each device's CPU (its 5-minute busy) and its memory (the Processor pool's
used share) as two lines on one percent axis; memory is drawn only where the device's scrape
carries a memory pool, and the page says so under the chart. The others (routing neighbour
changes, restarts, telemetry rates) are drawn as not built yet and open nothing. Saving a view, and asking your own PromQL or LogQL,
come next. The sidebar's Logs opens the same Syslog by device page.

## Baselines {#baselines}

Every baseline: when it was taken, what its commit recorded it earned, and whether it can be
re-applied without changing a credential a device holds now (a baseline older than a
rotation cannot). A withdrawn baseline is drawn with why. The judgement is made in the
background whenever a commit or a tag moves.

**Re-apply…** on a baseline's row opens its re-apply: every device the baseline holds, with
the counts first (will be restored, needs a stated reason, blocked, already as the baseline
holds it, and the devices it predates, left as they are), each device's program and checks
one level down. A device whose program needs a stated reason (a dangerous line, a secret
added back) is not part of the batch: its link opens its own Restore at that baseline, where
each line is given its reason. One confirm restores the rest, one device at a time, each
verified and rolled back alone, its configuration and its intent from the baseline; the batch
is drawn below as it runs. See [Restore and re-apply a baseline](restore).

## Authorisations {#authorisations}

Each divergence between Oxidized's copy of a device and its approved golden that a person
authorised, with who, why, and when it expired. These are past records: the freshness gate
they passed was retired with Oxidized (2026-10-08), so nothing adds to them now, and the tab
keeps every one readable. A network that never had one shows none.
