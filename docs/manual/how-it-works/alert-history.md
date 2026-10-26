# Alert history: past alerts and their evidence

{{product}} keeps every state change of every Grafana alert: when it went pending, when it
fired, when it resolved, when it read no data or could not evaluate. **Monitoring › Alerts ›
History** lists the alerts that fired and resolved, each with its evidence pack when one was
kept, and **Build evidence** for one that has none. Every time here is **Grafana's**, never a
device's clock and never when {{product}} happened to read it. Nothing here asks or changes a
device.

![The alert history: after each read of Grafana's alerts, every transition it shows (pending, firing, resolved, no data, error), timed by Grafana, is recorded once in the alert history; Grafana's own state history is read in once by the backfill, the same transition never recorded twice; History groups them into past alerts by rule; Build evidence rebuilds a past alert's pack as of its time, each section marked captured, rebuilt or cannot be rebuilt, and keeps it frozen for Explain; past its network's retention a transition moves to the data lake.](diagrams/alert-history.svg)

## What is recorded, and when {#recorded}

After each read of Grafana's alerts (every 60 s), each alert the read shows pending, firing,
reading no data or not evaluating is recorded with its rule, its labels, the device they name
(by the rule's device label, else the polled address) and the time Grafana says that state
began. A resolve is recorded from the alert's normal state, at the time Grafana says it became
normal, when its last recorded state was not normal; the reader keeps alerts that resolved
within the last hour, so a missed read still sees a resolve.

Each transition is recorded **once**: it is known by its rule, its labels, the state Grafana
named and the second it began, whoever records it. A second read, a second worker, and the
backfill below never add a second line for it.

## Grafana's past {#backfill}

What fired before {{product}} kept history is in Grafana's own state history. The script
`scripts/nmas-alert-backfill`, run once on the host as the app's user, reads it a day at a time
back to the oldest Grafana holds, splitting any day that fills a page, and records each
transition the same way, so running it again adds nothing. A move between two normal states (a
rule edited) is not a transition and is not kept. `--dry-run` counts without recording.

## History {#history}

The summary comes first: how many alerts fired and resolved in the range, on how many devices,
how many have an evidence pack, and the counts of the rest (pending and never fired, read no
data, could not evaluate). Below it, where the transitions came from and how far back they go.
Filter by words (rule, device or label), by rule, by device, by time (the last 24 hours, 7 days,
30 days, 90 days or all), and **Fired** or **All**. Each rule is a closed group with its count
(a rule generated per device, such as a heartbeat, is one group); open it for its alerts, the
newest first, at most 100 drawn. A row names the device, when it fired and resolved and for how
long, and its pack. Open a row for every state it passed through, and its pack or Build
evidence. An alert whose resolve Grafana did not record, and which the reader no longer holds,
says so.

## Build evidence {#build}

A past alert with no pack offers **Build evidence**. It is busy on itself until the pack is
drawn in its place. With hosted AI allowed, Explain is beside the pack. It is recorded as the
person who pressed it.

1. `find`: the alert, from the alert history, and any pack already kept for it; one that is
   kept is drawn, never built again.
2. `rebuild`: its pack as of the alert's time (when it fired), its window from 15 minutes before
   the onset: History up to then, the Intent check at the repository's commit current then (the
   golden, intent, templates and profile all of that commit, read from a throwaway copy), the
   health figures of the alert's device and its log lines over the window.
3. `mark`: each section marked (below), and the pack marked **rebuilt afterwards**.
4. `keep`: masked, hashed and kept in the evidence pack record: frozen, so every Explain of it
   reads the same pack.
5. `show`: the pack drawn in place of the button, with Explain.

## What each section says it is {#marks}

Every pack built since 26 Oct 2026 marks each section:

- **captured at the time:** read when the alert was found firing. Every section of a pack built
  by the reader, and the alert itself in a rebuilt pack (its transitions were recorded when they
  happened);
- **rebuilt afterwards:** built later from what keeps its past, saying from what (History less
  what it recorded after the alert's time; the Intent check at the commit then; Prometheus and
  Loki asked over the alert's window; the device's inventory row as it is now);
- **cannot be rebuilt:** what reads a store keeping only its latest value: the neighbours, the
  network as observed, and the endpoints attached around the device. They say so, and why; a
  later read is never put in their place. The health figures of the devices around it go with
  them: only the alert's own device is read.

The marks are in the pack, and in what Explain sends, so a rebuilt or missing part is never
read as observed. A pack built before the marks says "parts not marked".

## Retention and the data lake {#retention}

Each network sets how many days the history keeps a transition (`alert_history_retention_days`,
90 by default; docs/SETTINGS.md), counted from Grafana's time. Once a day, a transition older
than the longest retention of the networks sharing its Grafana is copied, masked, to the
network's S3/MinIO archive (`alert-history/<network>/…`), recorded as moved, and left out of
History. With no archive configured nothing moves, and the reader's log says so. The moved lines
stay in the record itself: dropping them needs a rewrite the records stores do not have yet.

## Where it is kept {#kept}

In the alert history record (`alert_history.jsonl` in the data folder, one line per transition,
or the records database once moved: Settings › Installation › Connections, the Record stores
card). If the record cannot be read, nothing is recorded, and History says so rather than
showing a quiet network.
