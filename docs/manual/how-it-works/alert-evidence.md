# An alert's evidence pack

When an alert fires, {{product}} gathers what a person would gather by hand: the alert, its
device's recent History, the device's Intent check, its expected and reported neighbours, and
the log lines around the alert's onset. It does this once, when the alert is first seen
firing, and keeps the result, the alert's **evidence pack**, so it reads the same while the
alert fires and after it resolves. **Monitoring › Alerts** draws one card per firing alert,
and the packs of alerts no longer firing below them. Nothing in a pack is decided by a model,
and no device is asked or changed.

![An alert's evidence pack: the Grafana alerts reader stores an alert as firing; after that read, a pack is built once for each firing alert that has none; its device is resolved as Needs attention resolves it; History, the Intent check's state, the neighbours and the log lines around the onset are read, each section naming its source, when it was read and whether it could be; every string is masked, every section and piece given its own reference, and the pack hashed; it is kept in the evidence pack record, and Monitoring's Alerts tab draws it.](diagrams/alert-evidence.svg)

## When a pack is built {#when}

After each read of Grafana's alerts (every 60 s), each alert whose condition holds and which
has no pack yet gets one: an alert is the rule, its labels and when its condition first held,
so an alert that resolves and fires again is a new alert with a new pack. A rule reading no
data, or one that cannot evaluate, is not firing, and gets none. At most ten packs are built
after one read; the rest wait for the next, and the tab says how many are waiting. Nothing
reaches {{product}} from Grafana by a webhook: the reader asks.

## What it holds {#sections}

Six sections, each naming its source, when it was read, and its state: **read**, **read,
nothing found**, **nothing to read** (no device, no committed golden, no onset), **not
configured**, or **could not be read**, with why. A source that fails is a section saying so,
never a shorter pack.

1. **The alert:** its rule, state, value, labels, silences, and its onset (when the trouble
   began, as Needs attention works it out).
2. **The device:** found the way Needs attention finds an alert's device (from the rule's
   device label, the syslog line's origin, or the polled address), and its network. An address
   two networks share, or a name no inventory holds, is said, never guessed.
3. **Recent History:** the device's deploys and restores, goldens, intent, restarts, reloads
   and planned windows over the last 7 days, the newest 20, from the History tab's own reader.
4. **Intent check:** whether the device's committed golden matches its intent (matches,
   differs with how many lines, or cannot be compared, with why). Only the state: the lines
   are configuration, and stay on the device's Intent tab.
5. **Neighbours:** the adjacencies its intent implies and what the device reports, from the
   Neighbours tab's own view.
6. **Log lines around the onset:** the device's lines from 15 minutes before the onset to 15
   minutes after it (or until the pack was built, if sooner), asked through History › Query's
   logs builder with Mercury's heartbeat lines left out; the 50 nearest the onset are kept and
   the rest counted.

## References and the hash {#references}

Every section has a reference (`logs`) and every piece in it one of its own (`logs:3`), drawn
beside it. The pack is hashed: a sha256 over its canonical form, shown on the card, the same
for the same evidence and different if any piece differs. A card whose stored pack no longer
matches its hash says so. An explanation that cites the pack (Phase 8's Explain) is checked
against these references: a citation that names no piece is refused.

## What is in it, and what never is {#masked}

Every string in a pack is masked before it is hashed or kept, as every line {{product}} shows
is: a password, secret, community or key in a log line is a placeholder. A pack holds alert
labels, masked log lines and the Intent check's state, never a configuration line or a
credential. A line that reads like an instruction (in an interface description, a log line or
a label) is kept and drawn as text; nothing in a pack is followed.

## Where it is kept {#kept}

In the evidence pack record (`evidence_packs.jsonl` in the data folder, one line per pack, or
the records database once moved: Settings › Installation › Connections, the Record stores
card). If the record cannot be read, no pack is built, and the tab says so.
