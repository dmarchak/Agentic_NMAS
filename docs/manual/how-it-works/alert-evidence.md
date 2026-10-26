# An alert's evidence pack

When an alert fires, {{product}} gathers what a person would gather by hand: the alert, its
device's recent History, the device's Intent check, its expected and reported neighbours, the
network around it as it was observed, the health of the devices near it, and the log lines
around the alert's onset. It does this once, when the alert is first seen firing, and keeps
the result, the alert's **evidence pack**, so it reads the same while the alert fires and
after it resolves: what it holds is as of the alert's time, never as of when it is read.
**Monitoring › Alerts** draws one card per firing alert, and the packs of alerts no longer
firing below them. Nothing in a pack is decided by a model, and no device is asked or changed.

![An alert's evidence pack: the Grafana alerts reader stores an alert as firing; after that read, a pack is built once for each firing alert that has none; its device is resolved as Needs attention resolves it; History, the Intent check's state, the neighbours, the observed network around it, the health of every device within two hops and the log lines around the onset are read as of the alert's time, each section naming its source, when it was read and whether it could be; every string is masked, every section and piece given its own reference, and the pack hashed; it is kept in the evidence pack record, and Monitoring's Alerts tab draws it.](diagrams/alert-evidence.svg)

## When a pack is built {#when}

After each read of Grafana's alerts (every 60 s), each alert whose condition holds and which
has no pack yet gets one: an alert is the rule, its labels and when its condition first held,
so an alert that resolves and fires again is a new alert with a new pack. A rule reading no
data, or one that cannot evaluate, is not firing, and gets none. At most ten packs are built
after one read; the rest wait for the next, and the tab says how many are waiting. Nothing
reaches {{product}} from Grafana by a webhook: the reader asks.

## What it holds {#sections}

Eight sections, each naming its source, when it was read, and its state: **read**, **read,
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
   Neighbours tab's own view, Prometheus asked as of the alert's time.
6. **The network around it, as observed:** the adjacencies and cables the Topology reader last
   read (LLDP and the routing tables), CAPTURED when the pack is built and kept with it, "as of"
   the alert's time: the items touching any device within two hops, each with its id and the
   read's own time. Explain uses this capture, never a later read, so an alert explained days
   later is explained against the network as it was. A read that cannot be used (never made,
   older than the reader's promise, or later than the alert) is said, with why. A pack built
   before captures existed says "observed state not captured with this pack".
7. **Health of the devices around it:** a few figures for the alert's device and every device
   within two hops of it (a shared segment's members are one hop, as in the network model;
   at most 24 devices, nearest first, the rest counted), each summarising the incident's
   window, never one instant: from 15 minutes before the onset to the alert's time, so a
   spike during the trouble shows even when it has passed by the time the alert is found
   (an onset that is not recorded is said, and the window is the 15 minutes before the alert;
   a window over 70 minutes keeps its last 70, and says so). One short line per device per
   figure:
   - **cpu:** the 5-minute CPU busy, its lowest, average and highest value over the window,
     when the highest was, and which metric the device answered (`cpmCPUTotal5minRev`, or
     `cpuAvgBusy5` on a device that carries only that, as the IOS switches do);
   - **heartbeat:** {{product}}'s syslog heartbeat, the line the heartbeat alerts count: how
     many arrived, the longest gap between two and when it ended, and how long since the last
     at the alert's time;
   - **scrapes:** Prometheus's scrapes of the device (`up`, every job): how many, how many
     failed, the first and the last failed scrape's time, and which jobs failed;
   - **discards:** interface discards, summed over the device's interfaces, in packets per
     second, a point a minute: its lowest, average and highest value, and when the highest was.

   Each figure has its own reference, `health:<device id>:<figure>` (for example
   `health:dev:12:cpu`), and the time it was read. A figure that could not be read, whose
   source is not configured, or that the source holds nothing for says so, never a zero. Four
   questions are asked for all the devices together, never one per device.
8. **Log lines around the onset:** the device's lines from 15 minutes before the onset to 15
   minutes after it (or until the pack was built, if sooner), asked through History › Query's
   logs builder with Mercury's heartbeat lines left out; the 50 nearest the onset are kept and
   the rest counted.

## References and the hash {#references}

Every section has a reference (`logs`) and every piece in it one of its own (`logs:3`; a
health figure's is its id, `health:dev:12:cpu`), drawn beside it. The pack is hashed: a sha256 over its canonical form, shown on the card, the same
for the same evidence and different if any piece differs. A card whose stored pack no longer
matches its hash says so. An explanation that cites the pack (Phase 8's Explain) is checked
against these references: a citation that names no piece is refused.

## What is in it, and what never is {#masked}

Every string in a pack is masked before it is hashed or kept, as every line {{product}} shows
is: a password, secret, community or key in a log line is a placeholder. A pack holds alert
labels, masked log lines, the Intent check's state, observed adjacencies and cables, and metric
figures, never a configuration line or a credential. A line that reads like an instruction (in an interface description, a log line or
a label) is kept and drawn as text; nothing in a pack is followed.

## Explain {#explain}

An open pack has one button, **Explain**. It makes one call to a hosted model, through
{{product}}'s AI gateway: allowed only once hosted AI is allowed on **Settings › Installation ›
AI (hosted)**, capped, and recorded with who pressed it. With hosted AI off it says so, and the
pack is the whole of what {{product}} gathered.

**Explain** carries the **AI** mark: hover it for the task, its pinned model and its cap per
call. When hosted AI cannot answer (it is off, no key is set, or today's cap would be
crossed), Explain is drawn disabled with the reason under it, and the pack is drawn whole as
ever (see [The AI mark](installation-settings#ai-mark)).

1. `pack`: the alert's stored pack is read and its hash checked; a pack that changed since it
   was built is not explained.
2. `topology`: the part of the network around the alert's device, from {{product}}'s network
   model (below): the device and everything one link, adjacency or cable away from it, with
   what the pack captured as observed when the alert fired (never read again). It goes unless
   the network has the topology class turned off; the answer then says "No topology was sent
   with the pack" and why. It opens with a **coverage header**: each layer of the network's
   context (inventory, intent, adjacency, performance, events, endpoints, flows) as present,
   partial or not collected, with its source and age, so a gap is said rather than left to be
   guessed. Endpoints and flows are not collected yet.
3. `ask`: the pack (its health figures among it) and the topology go as data (masked when they
   were built, and masked again on the way out), the pack's layout, the topology's layout, the
   network's summary and the allowed reads as the instructions' context; no tool is offered,
   so the model can only read. The model is told to cite each figure by its reference, never
   to state a figure the pack does not hold, to say when a device's own figures do not explain
   it, and to offer a cause the evidence does not show only as a hypothesis, with the read that
   would confirm it. With the topology class off, only the alert's device's own figures go
   (which devices are near it is topology), and the pack says the rest were withheld.
4. `check`: every hypothesis must cite pieces of the pack as it was sent, by their references,
   or items of the topology that was sent, by their ids, and name one read-only command a
   person could run to confirm it (a `show`, `ping` or `traceroute`, as Show commands allows).
   One that cites a reference neither holds (an id of the network the topology sent did not
   include, or a health figure that was withheld, counts as not held), or names a command that
   is not a read, makes the whole answer "couldn't analyse", and nothing is shown. An answer of
   **no fault found** holds no hypothesis and must cite the evidence it checked, each piece one
   the pack or the topology holds and one that was read (a section that was unreadable or
   absent is not healthy evidence); one that does not is "couldn't analyse" too.
5. `show`: a short rationale, then at most three hypotheses, the most likely first, each with
   the references it cites (a pack piece is a link to it above; a topology id is drawn as text)
   and its confirming read. It is a hypothesis, not a finding: nothing was run. Run the read
   through **Show commands** to check it. Or **no fault found**: what the evidence shows, and
   each piece it checked, linked. That is an assessment of the pack, not of the network: only
   what the pack holds was checked, and an alert can fire on a passing blip or a threshold set
   too low. Explain is told to say so rather than invent a cause.

## What of the network Explain sends {#topology}

{{product}} compiles each network into a model with no AI call: its devices (name, role, site,
platform and management address, from the inventory and NetBox), the subnets two or more
devices share by committed intent (the links), the adjacencies intent implies (OSPF, OSPFv3
and BGP), each interface's addresses, VRF and VLANs, and OSPF and BGP membership (router id,
areas, passive interfaces, AS and peers). It never holds a configuration line, a description
or a credential: it holds what intent means for the topology, not the intent itself. It is
rebuilt only when the committed intent or the inventory changes.

Explain sends the alert's device and what is one hop from it: the devices on its links (a
switch carrying its segment among them), each with its hop and what reached it, the links and
the device's adjacencies, and the cables LLDP reports. What was observed rides on each item
with the time it was read: the Topology reader's read the pack captured when the alert fired
(its section 6), never a read made when Explain is pressed. A read that could not be used then
(never made, too old, later than the alert, or holding nothing for this network), or a pack
that captured none, is written "could not read" with why, never left out. The expected half
(devices, links, what intent implies) is the network model as it is when Explain is pressed. A segment of more than 16
devices, or one whose devices share an address, is listed and not walked through. Each item
has a stable id (`dev:<NetBox id>`, `link:<subnet>`, `adj:...`, `cable:...`) that a hypothesis
may cite.

**The topology class** is on for every network by default. It is the network's setting
`ai_topology_class`; turned off, Explain sends the pack alone and says so beside the answer,
and a setting that cannot be read counts as off. No screen turns it off yet: its control on
the network's Settings is registered to build (C1713). A classification marking that forces AI
off is planned and not built yet: nothing reads one today.

## Where it is kept {#kept}

In the evidence pack record (`evidence_packs.jsonl` in the data folder, one line per pack, or
the records database once moved: Settings › Installation › Connections, the Record stores
card). If the record cannot be read, no pack is built, and the tab says so.
