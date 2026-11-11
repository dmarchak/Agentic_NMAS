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
   A run takes at most 10 commands; more refuses it. Read: nothing. Sent: nothing. Recorded: the refusal, as a run that asked no device.
2. `hold`: each device is held while it is read, as an operation holds it. A device another
   operation holds is skipped, naming who holds it and since when; it is never queued. While
   a read holds a device, a deploy to it is refused, naming the read and its person.
3. `read`: one session to the device, each command asked in turn and its answer read whole,
   bounded by the network's read timeout. Several devices are read at once, up to the
   network's limit (`reads_max_workers`, six unless changed). A device that does not answer,
   or a command that fails, is named with why; nothing is drawn as an answer it did not give.
   A reason longer than 400 characters is kept to its first 400, and says in place how many
   it had and how many were cut. A Linux host or Open vSwitch server answers through a terminal, so its programs colour and
   page their output; those terminal control codes are removed from the answer, and nothing
   else is.
4. `mask`: each answer is masked as a golden is, by the position of every secret and by every
   credential the installation holds, before it is kept or drawn.
5. `cap`: an answer longer than the network's cap (`reads_answer_cap_kib`, 32 KiB unless
   changed) is kept to the cap and marked cut, with its whole size and a fingerprint of the
   whole answer, so two answers still compare. The page says how many bytes are kept and
   shown, and how many were cut. Only the cap cuts an answer: a long line is kept whole.
6. `record`: the run is written when it starts and when it ends: who (a person, or the agent
   for a person), when, the network, the commands, each device's outcome and its masked
   answers. The start is written before the run's page opens, so the page of a run that has
   only just started says running, and it reads the record again each time the run says a
   device has answered and when it ends (and once more as the page's live updates first
   connect, so a run that ended in that moment is not left drawn as running). A run whose
   job fails before it finishes is recorded as failed, with the reason and what it had read,
   and its page says so. History shows it. Answers are kept for the network's retention
   (`reads_retention_days`, 30 unless changed), then moved to the network's S3/MinIO archive;
   who, when and what stay for good. With no archive configured the answers stay here.

## A read an operation makes is the operation's {#an-operations-reads}

An operation or a heal that reads a device as part of its own run asks through this same way:
the same command policy (without a person's extras: no session setting, no log line), the same
hold, mask, cap, store and retention. Its read is kept naming the run it belongs to (the
operation, the run's id and the step that asked), and it is recorded as the operation's own
read for the person who started the operation, never as a run that person made here.

Such a read is not a row of its own. History's Show commands rows, **Recent runs** on Show
commands and **Recent reads** on a device's Ask the device tab show the runs a person (or the
agent, for a person) asked, and nothing else. An operation's reads are in the operation's own record,
under the step that made them: each read with when it was asked, what was asked, whether it
passed, was read and did not, or could not be read, and what it found in a line. The answer
itself stays here, masked, and the record names it. History's row of the operation says the
reads of each step in one line, counted ("26 reads, about 13 s apart: 1 pass, 25 fail"). A
step keeps at most 120 reads, each line at most 200 characters; past that it keeps the first
and the newest and says how many it dropped.

Today this holds for [Re-subscribe a telemetry stream](telemetry-resubscribe) (its reads
before and its verify) and for self-healing's port bounce and BGP session clear (the reads
their decision makes, [How self-healing works](heal)). A diagnosis's reads, a path trace's,
the controller app deploy's host reads, a privileged command's preview and the AI analysis's
reads are still runs of their own on History, each naming what it was for.

A read an operation made before this was built (2026-11-11) was kept as a Show commands run
of the person who started the operation, and nothing in it names the operation's run. History
shows such a row as it was recorded: its detail line says what it was for ("telemetry
re-subscribe: subscription 102's receiver"). Mercury does not guess which run it belonged to.

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
| `send log` | `[<level>] <one plain line>`, at most 120 characters, never piped. Levels 4 to 7 run freely; 0 to 3 (they can fire critical alert rules) need a stated reason of three words or more, recorded, and the word TEST in the line. Typing such a line brings a reason field under the commands (one reason covers every such line in the run) or under Ask the device's box; the line says "needs a reason" and Run stays off until it has three words, then "allowed, with your reason", or "not a test" when TEST is missing. The run's result and its History row name the reason |
| `terminal` | `length` or `width`, 0 to 512: for this session only |

A ping or traceroute is bounded by its own worst case, worked out from what you typed and the
device's defaults (a ping: repeat x timeout; a traceroute: probes x timeout x hops). The worst
case may be at most 300 seconds, so a plain `traceroute <target>` (3 x 3 s x 30 hops = 270 s)
runs. A larger one is refused, naming its worst case and the limit. Mercury waits for the answer
that long, plus 30 seconds.

The agent runs the reads and `verify /md5`. A line in a device's log and the session's
settings are a person's to send.

### On an Open vSwitch server {#ovs}

A device whose platform is Open vSwitch on Linux (the `ovs_linux` driver) is read by its own
list, and by nothing else; these commands are asked only of such a device, and are refused on
every other. Each is the whole command exactly as listed; all but the version read run under
`sudo -n`, which never prompts for a password.
`<bridge>` and `<port>` are one interface name each (letters, digits, `_`, `.` and `-`,
beginning with a letter or a digit, at most 15 characters); nothing else may follow, and no
option may be added.

| Command | What it prints |
|---|---|
| `ovs-vsctl --version` | the Open vSwitch version |
| `sudo -n ovs-vsctl show` | the database as a tree: bridges, ports, interfaces, controllers |
| `sudo -n ovs-vsctl list-br`, `list-ports <bridge>` | the bridges; one bridge's ports |
| `sudo -n ovs-vsctl get-controller <bridge>`, `get-fail-mode <bridge>` | a bridge's controller targets; its fail mode |
| `sudo -n ovs-vsctl get bridge <bridge> protocols`, `datapath_id`, `fail_mode` or `other_config` | one column of a bridge (also `--if-exists get bridge <bridge> other-config:datapath-id`) |
| `sudo -n ovs-vsctl get interface <port> ofport` or `ofport_request` | a port's OpenFlow port number, given or requested |
| `sudo -n ovs-vsctl list bridge`, `list port`, `list interface`, each alone or with one name | a table's records, or one record |
| `sudo -n ovs-vsctl list controller` (also `--columns=target,is_connected list controller`) | the controllers and whether each is connected |
| `sudo -n ovs-ofctl -O OpenFlow13 show <bridge>` | the switch's features and ports |
| `sudo -n ovs-ofctl -O OpenFlow13 dump-flows <bridge>` | the bridge's flow entries |
| `sudo -n ovs-ofctl -O OpenFlow13 dump-ports <bridge>`, `dump-ports-desc <bridge>` | its ports' counters; its ports' descriptions |
| `sudo -n ovs-ofctl -O OpenFlow13 dump-tables <bridge>` | its tables' statistics |

A command that changes the switch (`set`, `add-br`, `del-port`, `add-flow`, `mod-flows`), a
second command, an option such as `--db`, another table or column, and another program
(`ovs-appctl`) are refused. A command typed close to a listed one is refused naming the listed
form: `ovs-vsctl show` answers that the listed form is `sudo -n ovs-vsctl show`, and
`ovs-ofctl dump-flows <bridge>` that it is `sudo -n ovs-ofctl -O OpenFlow13 dump-flows <bridge>`.
Mercury never rewrites what you typed: what is sent is what you saw. The answers are masked as
every answer is, and a line holding a credential word is masked after that word.

**Tier 2, changes the device's state, recoverably: not here.** `clear counters`,
`clear arp-cache`, `clear logging`, `undebug all` (and `clear ip bgp <peer> soft`, not yet
measured). Each is the operation [Run a privileged command](privileged), one device at a time
from its page's Actions menu: a preview of what it affects, a confirm with a reason, and a
record. The refusal here says so.

**Tier 3, destructive: refused.** Each refusal names the operation that does it properly, or
says that none does:

- `reload` restarts the device. Use the device page's **Actions › Reload…** ([Reload a
  device](reload)): it shows what else goes down, judges five gates, declares the
  planned-restart window before it acts and checks the device came back.
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

## How answers are grouped and compared {#grouping}

- **Grouped when the answer is the same.** Devices whose whole masked answer is identical form
  one group. A cut answer, or one moved to the archive, groups by the fingerprint of its whole
  answer.
- **Columns you tick are ignored.** When the answers begin with a table's header line (for
  example `Neighbor ID  Pri  State  Dead Time ...`), its columns are offered to tick. Ticked
  columns are blanked (drawn as `·`) before answers are compared, so a column that changes on
  its own, such as OSPF's Dead Time, no longer keeps every device apart. Your choice is
  recorded with the run, as you; the answers are kept whole, and no device is asked again.
  Ignoring a column groups answers that differ only in it. It cannot make different answers
  alike: each router lists its neighbours and never itself, so neighbour lists stay apart.
- **Nobody is the reference until you choose one.** "Compare against" starts at nobody. You may
  choose a device, or "the most common answer", which is offered only when at least two
  devices share an answer. With a reference chosen, each group says whether it is the same as
  the reference, or how many lines only one of them has; "Only the differences" shows them.
- **No colour without an expectation.** Nothing was expected of these answers, so a group is
  drawn neutral, named by its devices. Colour is kept for real states: a failed read is red, a
  skipped device amber.
- **An empty answer says so:** "No output (empty answer)", drawn apart from a read that failed.

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
