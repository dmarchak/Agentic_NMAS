# Logs

What the network's devices sent to syslog, by device: how many lines at a severity over a time
range, which devices sent the most, what each sent most often, and each device's own lines one
click away. The sidebar's Logs opens it, for the network you are on
(`/v2/logs?list=<network>`). Mercury's own log is in Settings › Installation › Diagnostics, and
one device's recent lines are also its device page's Logs tab
([the device page](device-page#logs-tab)).

## The question {#question}

- **The range**: the last 24 h, 7 d, 30 d or 120 d. A range in days is today so far and the
  days before it, in UTC.
- **Severity**: error or worse (0 to 3), warning or worse, or every severity. It sets the
  headline and the table, and an opened device's lines.
- **Copy the link**: the address carries the whole question, so a link shows the same view.

## How it is counted {#counted}

Mercury's logs reader counts each day's lines once, from the network's Loki, by device and
mnemonic, and re-reads today and the last 24 hours every 5 minutes; the view sums what it kept.
Asking Loki for months of counts on every visit would take tens of seconds, and Loki answers at
most 30 days at a time. A line is the device's when it names the device in its own syslog origin
(as the device page's Logs tab matches it); a line that names no device is counted apart. The
heartbeat lines are left out.

## What the range can hold {#coverage}

A notice says when the range reaches past what is kept: days before the log store's first line
("nothing to show is not nothing happened"), days past the network's Logs retention (deleted),
and days the reader is still counting (it adds up to 7 past days each read). It also says when
Loki holds lines older than the network's Logs retention setting says it keeps: the setting may
be lower than what Loki keeps (Settings › Integrations, Loki, Logs retention).

## The devices {#devices}

Each device that sent a line at the severity asked: its lines in the range, its newest line, and
its most frequent mnemonic. The devices that sent nothing at that severity are named below the
table, and lines from names that are not this network's devices are counted apart.

## A device's lines {#lines}

Open a device to filter its lines by severity, mnemonic, time (From and To, UTC:
`2026-10-04` or `2026-10-04 09:30`, or `now`) and text, see its trend by mnemonic (lines per
day, from the first day counted), and read its lines newest first, 50 at a time (**the next
50**). Each line is drawn at the time Mercury's collector received it, never the device's own
clock, and masked like every other configuration text. Its lines are asked from Loki when you
open it, at most 30 days at a time; a longer range shows the newest 30 days and says so.
**Open the device's Logs tab** goes to its own page.
