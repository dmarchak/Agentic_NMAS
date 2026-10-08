# Show commands: ask devices read-only commands

Every exec command Mercury sends a device for a person goes one way: **Ask the device** on a
device's page asks one device, and **Show commands** asks many at once. The agent uses the same
way, recorded as acting for the person who asked it. Only Tier 1 of the command policy runs here
(below): no device's configuration is changed, there is no configuration mode, and anything
else is refused before any device is asked, naming its tier and where to go instead.

![Show commands: every command is checked against Tier 1 of the command policy before any device is asked, and a refused run asks none and is recorded; each device is held while it is read, several at once up to the network's limit, and a device another operation holds is skipped and named; each answer is masked as a golden is and kept up to the network's cap, saying when it was cut; the run is recorded: who, when, the commands and each device's outcome. No device's configuration is changed.](diagrams/show-commands.svg)

## The steps

1. `refuse`: every command is checked against Tier 1 of the command policy, whole: the
   command word, each argument (one token of its shape) and what follows a `|` (`include`,
   `exclude`, `begin`, `section`, `count`). A line break, a URL, `| redirect` or anything
   outside Tier 1 refuses the whole run, naming the command, its tier and where to go instead.
   `show tech-support` is refused across more than one device (ask it of one, on its page).
   Read: nothing. Sent: nothing. Recorded: the refusal, as a run that asked no device.
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

## The command policy: what runs here {#tiers}

Every command is in one of three tiers, decided by a list of what is allowed, never by a list of
what is not: a command in no tier is refused, naming the nearest command that runs.

**Tier 1, non-destructive: runs here.**

| Command | What it takes |
|---|---|
| `show …` | anything, filtered only by `include`, `exclude`, `begin`, `section` or `count` |
| `ping` | `[vrf <name>] [ip\|ipv6] <target>`, then `repeat` 1 to 100, `size` 36 to 1500, `timeout` 0 to 10 s, `source <interface or address>`, `df-bit` |
| `traceroute` | `[vrf <name>] [ip\|ipv6] <target>`, then `numeric`, `timeout` 1 to 10 s, `probe` 1 to 5, `ttl <min> <max>` (1 to 30), `source`, `port` |
| `dir`, `more` | a local file system only (`flash:`, `bootflash:`, `nvram:`, `system:`, …), never a transfer protocol (`tftp:`, `ftp:`, `http:`, `scp:`, …) |
| `verify /md5` | a file on a local file system, and optionally the MD5 it should have |
| `send log` | `[<level 0 to 7>] <one plain line>`, at most 120 characters, never piped |
| `terminal` | `length` or `width`, 0 to 512: for this session only |

A ping or traceroute is bounded by its own worst case, worked out from what you typed and the
device's defaults (a ping: repeat x timeout; a traceroute: probes x timeout x hops). The worst
case may be at most 300 seconds, so a plain `traceroute <target>` (3 x 3 s x 30 hops = 270 s)
runs. A larger one is refused, naming its worst case and the limit. Mercury waits for the answer
that long, plus 30 seconds.

The agent runs the reads and `verify /md5`. A line in a device's log and the session's
settings are a person's to send.

**Tier 2, changes the device's state, recoverably: not here.** `clear counters`,
`clear arp-cache`, `clear ip bgp <peer> soft`, `clear logging`, `undebug all`. These will be the
"Run a privileged command" operation: a preview of what it affects, a confirm, and a record. It
is drafted and not built yet, and the refusal says so.

**Tier 3, destructive: refused.** Each refusal names the operation that does it properly, or
says that none does:

- `reload` restarts the device. Reload is an operation, built with Revert by reload, and not on
  v2 yet.
- `write erase`, `erase`, `delete`, `format` change or destroy the device's files or its saved
  configuration.
- `copy` moves files into or off the device. A configuration reaches a device by deploy, and a
  golden is taken by Capture.
- `clear ip bgp *` and `clear ip ospf process` drop sessions and adjacencies.
- `debug` loads the device. Its logs are read on the device page's Logs tab.
- `crypto key zeroize` destroys the key Mercury reaches the device with.
- `request` and `install` change the device's software.

**Configure mode** runs only in the deploy pipeline: change the device's intent and deploy it.
**Saving** (`write memory`, `copy running-config startup-config`) is the pipeline's last step,
and the device page's Persist does it on its own.

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
