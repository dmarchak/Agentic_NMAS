# Show commands

Ask many devices the same read-only commands at once, and see where their answers differ.
Nothing here changes a device's configuration; only Tier 1 of
[the command policy](show-commands#tiers) runs. For one device, use **Ask the device** on its
page. How a read runs: [Show commands: ask devices read-only commands](show-commands).

## A new read {#new-read}

**Devices**: filter by name (a part of it, or a pattern such as `r*`, several separated by
commas), role, platform and site. The card names how many devices match and lists them (the
first 30, then how many more); **Run** asks exactly those. Each device is held while it is read,
several at once up to the network's limit, and one another operation holds is skipped and named.

**Commands**: one or more, each checked as you type: `read-only`, a heavy read's cost, or which
tier it is in and where to go instead. **Add a command** and **Remove** change the list; up to 10
per run. Every command must be in Tier 1 before any device is asked, and `show tech-support` is asked of one device only,
on its page.

**Or a saved set**: the network's saved sets, each with its commands; **Use** fills the card
with them. **Save these commands as a set…** commits the card's commands to the network's
repository under a name, as you; a name already taken is refused.

**Run** starts the run and opens its page. It is recorded in History, as yours.

**Test the logging path on N devices** sends each chosen device one line for its log and
watches Loki for it, 30 seconds per device; it needs no command. It is off, saying why on hover,
when Loki is not configured. How it works:
[Test the logging path](logging-path).

## The result {#the-result}

A run's page leads with the summary: per command, how many devices answered (and how many of
those answers were empty), how many distinct answers there were, and which failed or were
skipped. While it runs, it shows how many devices are done and draws the answers as they
arrive; you can leave and come back.

The answers are **grouped**: devices whose answer is the same form one group, its answer shown
once, collapsed, named by its devices in a neutral colour (nothing was expected, so no group is
"right" or "wrong"). A group opens to its answer and its devices; a device opens its own answer
on its page. An empty answer says "No output (empty answer)". A device that did not answer is
never inside a group: it is listed as failed (red) or skipped (amber), with why. An answer
longer than the network's cap says it was cut.

**Ignore when grouping**: when the answers begin with a table's header line, its columns are
offered to tick; **Group again** blanks the ticked ones and groups again. The choice is
recorded with the run, as you, and named above the groups; no device is asked again.

**Find a device** and **Find in the answers** narrow the groups. **Compare against** chooses
the reference: nobody, until you choose a device, or "the most common answer" when at least two
devices share one. **Show** chooses every answer grouped, only the differences (each group's
lines against the reference you chose), or the failed and skipped. **Compare … with**, on a
group, sets one of its devices beside a device you choose, each side's lines the other lacks
marked. How grouping and comparing work: [How answers are grouped](show-commands#grouping).

## A logging-path test's result {#logging-path}

The page leads with what to act on: how many devices' lines were **not received within 30 s**
(red), **not sent** (amber), **unknown** (Loki could not be asked: neither), and **received**
(green, with how long each took). A device not received says when Loki last received anything
from it, and offers **Open its Logs** and **Test it again**; **Test again** repeats the whole
test.

## Recent runs {#recent-runs}

The network's latest runs, each with who ran it, the commands, how many devices, and the outcome;
open one to read its answers again.
