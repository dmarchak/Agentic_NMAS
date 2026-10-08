# Show commands: ask devices read-only commands

Every read-only command Mercury sends a device for a person goes one way: **Ask the device**
on a device's page asks one device, and **Show commands** asks many at once. The agent will use
the same way, recorded as acting for the person who asked it. Nothing is changed on any device:
there is no configuration mode, and anything that is not a read is refused before any device
is asked.

![Show commands: every command is checked against the read-only allowlist before any device is asked, and a refused run asks none and is recorded; each device is held while it is read, several at once up to the network's limit, and a device another operation holds is skipped and named; each answer is masked as a golden is and kept up to the network's cap, saying when it was cut; the run is recorded: who, when, the commands and each device's outcome. Nothing is changed on any device.](diagrams/show-commands.svg)

## The steps

1. `refuse`: every command is checked against the read-only allowlist, whole: the command
   word (`show`, `ping`, `traceroute`, `dir`, `more`) and what follows a `|` (`include`,
   `exclude`, `begin`, `section`, `count`). A line break, a URL, `| redirect` or anything else
   refuses the whole run, naming the command and why. `show tech-support` is refused across
   more than one device (ask it of one, on its page). Read: nothing. Sent: nothing. Recorded:
   the refusal, as a run that asked no device.
2. `hold`: each device is held while it is read, as an operation holds it. A device another
   operation holds is skipped, naming who holds it and since when; it is never queued. While
   a read holds a device, a deploy to it is refused, naming the read and its person.
3. `read`: one session to the device, each command asked in turn and its answer read whole,
   bounded by the network's read timeout. Several devices are read at once, up to the
   network's limit (`reads_max_workers`, six unless changed). A device that does not answer,
   or a command that fails, is named with why; nothing is drawn as an answer it did not give.
4. `mask`: each answer is masked as a golden is, by the position of every secret and by every
   credential the installation holds, before it is kept or drawn.
5. `cap`: an answer longer than the network's cap (`reads_answer_cap_kib`, 32 KiB unless
   changed) is kept to the cap and marked cut, with its whole size and a fingerprint of the
   whole answer, so two answers still compare.
6. `record`: the run is written when it starts and when it ends: who (a person, or the agent
   for a person), when, the network, the commands, each device's outcome and its masked
   answers. History shows it. Answers are kept for the network's retention
   (`reads_retention_days`, 30 unless changed), then moved to the network's S3/MinIO archive;
   who, when and what stay for good. With no archive configured the answers stay here.

## Saved sets {#saved-sets}

A saved set is a name and its commands, kept in the network's repository: one file per set,
committed as the person who saved it, so a set has a history and can be reviewed. Each command is
checked against the allowlist when the set is saved and again whenever it runs. A name already
taken is refused rather than overwritten. Sets are offered on Show commands and, by name, on Ask
the device.

## Heavy commands

Some reads cost the device: `show tech-support` runs for minutes, `show logging` unfiltered
returns the whole buffer, `show ip bgp` the whole table. The command box names the cost before
you run one. Narrow a long read with `| include`, `| begin` or `| section`.
