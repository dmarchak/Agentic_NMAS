# Show commands

Ask many devices the same read-only commands at once, and see where their answers differ.
Nothing here changes a device. For one device, use **Ask the device** on its page. How a read
runs: [Show commands: ask devices read-only commands](show-commands).

## A new read {#new-read}

**Devices**: filter by name (a part of it, or a pattern such as `r*`, several separated by
commas), role, platform and site. The card names how many devices match and lists them (the
first 30, then how many more); **Run** asks exactly those. Each device is held while it is read,
several at once up to the network's limit, and one another operation holds is skipped and named.

**Commands**: one or more, each checked as you type: `read-only`, a heavy read's cost, or why it
is not a read. **Add a command** and **Remove** change the list; up to 10 per run. Every command
must be a read before any device is asked, and `show tech-support` is asked of one device only,
on its page.

**Or a saved set**: the network's saved sets, each with its commands; **Use** fills the card
with them. **Save these commands as a set…** commits the card's commands to the network's
repository under a name, as you; a name already taken is refused.

**Run** starts the run and opens its page. It is recorded in History, as yours.

## The result {#the-result}

A run's page leads with the summary: per command, how many devices answered, how many distinct
answers there were (and how many devices differ from the largest group), and which failed or
were skipped. While it runs, it shows how many devices are done and draws the answers as they
arrive; you can leave and come back.

The answers are **grouped**: devices whose whole masked answer is the same form one group, its
answer shown once, collapsed. A group opens to its answer and its devices; a device opens its own
answer on its page. A device that did not answer is never inside a group: it is listed as failed
or skipped, with why. An answer longer than the network's cap says it was cut.

**Find a device** and **Find in the answers** narrow the groups. **Show** chooses every answer
grouped, only the differences (each group's lines against the largest group), or the failed and
skipped. **Compare** on a group sets one of its devices beside the largest group's, each side's
lines the other lacks marked.

## Recent runs {#recent-runs}

The network's latest runs, each with who ran it, the commands, how many devices, and the outcome;
open one to read its answers again.
