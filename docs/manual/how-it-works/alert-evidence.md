# An alert's evidence pack

When an alert fires, {{product}} gathers what a person would gather by hand: the alert, the
other alerts in its network around the same time, its device's recent History, the device's
Intent check, its expected and reported neighbours, the network around it as it was observed,
the health of the devices near it, the monitoring side over the same time (the polling, the SNMP
exporter and the host that polls), and the log lines around the alert's onset. It does this
once, when the alert is first seen firing, and keeps
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

Eleven sections, each naming its source, when it was read, and its state: **read**, **read,
nothing found**, **nothing to read** (no device, no committed golden, no onset), **not
configured**, or **could not be read**, with why. A source that fails is a section saying so,
never a shorter pack.

1. **The alert:** its rule, state, value, labels, silences, and its onset (when the trouble
   began, as Needs attention works it out).
2. **Other alerts in the network around the onset:** every other alert of the same network
   that was active from 15 minutes before the onset to the alert's time, from the alert
   history (see [below](#concurrent)).
3. **The device:** found the way Needs attention finds an alert's device (from the rule's
   device label, the syslog line's origin, or the polled address), and its network. An address
   two networks share, or a name no inventory holds, is said, never guessed.
4. **Recent History:** the device's deploys and restores, goldens, intent, restarts, reloads
   and planned windows over the last 7 days, the newest 20, from the History tab's own reader.
5. **Intent check:** whether the device's committed golden matches its intent (matches,
   differs with how many lines, or cannot be compared, with why). Only the state: the lines
   are configuration, and stay on the device's Intent tab.
6. **Neighbours:** the adjacencies its intent implies and what the device reports, from the
   Neighbours tab's own view, Prometheus asked as of the alert's time.
7. **The network around it, as observed:** the adjacencies and cables the Topology reader last
   read (LLDP and the routing tables), CAPTURED when the pack is built and kept with it, "as of"
   the alert's time: the items touching any device within two hops, each with its id and the
   read's own time. Explain uses this capture, never a later read, so an alert explained days
   later is explained against the network as it was. A read that cannot be used (never made,
   older than the reader's promise, or later than the alert) is said, with why. A pack built
   before captures existed says "observed state not captured with this pack".
8. **What is attached around it, as observed:** the endpoints (hosts, phones, printers) the
   endpoint reader located on the alert's device and on each device one hop from it: name (from
   its DHCP lease), MAC, addresses, interface, VLAN, and when it was last seen there, in words
   ("last seen edge1 GigabitEthernet1/0, 3 h ago", "stale" past the network's age). CAPTURED
   when the pack is built, only from a read made as of the alert's time. Mercury keeps only the
   latest read, with no endpoint history yet, so an older alert's pack says the read is not its
   own, with why, never a later read in its place. Endpoints are the topology class: Explain
   sends them only when the network's topology switch is on.
9. **Health of the devices around it:** a few figures for the alert's device and every device
   within two hops of it (a shared segment's members are one hop, as in the network model;
   at most 24 devices, nearest first, the rest counted; in a pack rebuilt afterwards, two hops
   in the network model as it is now, said so: see
   [Alert history](alert-history#marks)), each summarising the incident's
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
10. **The monitoring side over the window:** the collector's side of the same window (see
   [below](#observer)): the scrape jobs polling these devices, each across all its targets, the
   SNMP exporter, and the host Prometheus runs on.
11. **Log lines around the onset:** the device's lines from 15 minutes before the onset to 15
   minutes after it (or until the pack was built, if sooner), asked through History › Query's
   logs builder with Mercury's heartbeat lines left out; the 50 nearest the onset are kept and
   the rest counted.

## An SDN detection's pack {#sdn}

{{product}}'s own SDN detection (the scan, flood and unauthorised flow rules, run over each
collection of a network's SDN controllers: see [SDN flows](sdn-flows)) is an alert too. The
Alerts tab names its source **SDN detection**, with when it last judged a collection; if its
state cannot be read, the tab says so and lists none of its detections, never an empty list.
Its card names the **switch** (its DPID and controller connection), since a controller's switch
is no device.

Its pack is built once, when the detection first fires, from the collection the detection
rests on, and holds three sections: **the alert** (read from SDN detection, as {{product}}
recorded it), **the device** ("nothing to read": a controller's switch is in no inventory), and
**the SDN flows and port rates the detection rests on**, captured at the detection's time. That
section names the switch (its DPID, the name it reports as the SDN reader last read it, or why
the name is not known, and its controller), what it keeps (the flows, displaced flows, ports
and earlier sightings, and "N of M flows kept" when the 50-flow bound cut it), and then each
piece in words:

- **the detection:** the rule's words; what it measured (the value, its unit, the sample or
  window, how long it held and since when); what it was held against (the threshold, its
  setting, and for a flood the factor, baseline and floor); its confidence and why; its effect,
  for an unauthorised flow; the source and targets, and the port; and what it rests on, each a
  link to its piece (an id the pack does not keep is drawn as the id, with how many were left
  out);
- **a port:** packets and bytes a second received and sent, packets dropped each way, and the
  counts over the sample (its seconds, and how far apart the two reads were asked);
- **a flow:** its table and priority, its match exactly as the switch reported it (IPv4 and
  IPv6 addresses whole, `eth_type` in hex), its actions ("no action" drops what it matches),
  its packets and bytes, how long it had been installed at the read, its idle and hard timeouts,
  and its cookie;
- **{{product}}'s flow, displaced:** a flow {{product}} recorded at the place an unauthorised
  flow now holds, with its state, its match and actions, when it was installed and the response
  that installed it;
- **an earlier sighting:** a scan's port seen in an earlier collection whose flow has gone;
- **the flow granularity** on the switch (L4, L3, L2 or none, with each count), and whether the
  scan rule falls back to packet rates there.

A piece the detection cites says **cited by the detection**.

**Meters.** The collection reads flows and port counters, never meters, so a meter is not part
of the pack and is never cited. Under the pieces, **Meters these flows name** lists each meter a
flow's actions name (`METER:1`) as the SDN reader last read it: its rate and band, the burst,
the packets and bytes its band dropped, the packets in and the flows using it, with when that
read was and whether it was after the pack was built. A meter the reader cannot give is said
with why: the reader has not read the network, its store cannot be read, its read holds no such
switch, the switch's meters were not read, or the switch held no such meter at that read.

## Other alerts around the onset {#concurrent}

An alert rarely fires alone: when several devices stop answering in the same minute, the cause
is usually beneath them all (a shared link, the host they run on), and an alert read on its own
points at the wrong device. So the pack lists every **other** alert of the same network that
was active in the incident's window (the health figures' own: from 15 minutes before the onset
to the alert's time), from the [alert history](alert-history), each as it stood **at the
alert's time**:

- its rule, and its device (with the device's id where the network model knows it) or, for an
  alert whose labels name no device, the address it was polled at (IPv4 or IPv6);
- its state then (pending, firing, no data, error, or resolved), when it started, when it fired
  and when it resolved, each in Grafana's time. A resolve after the alert's time is not in the
  pack: it was not known then;
- **same alert**, when it is an earlier episode of this very alert (the same rule and labels
  flapping in the window). The alert's own episode is not listed.

Each has its own reference, `concurrent:<episode id>`, the alert history's id for that
episode. An alert begun before the window whose resolve was never recorded is counted and not
listed: its state in the window is not known. At most 40 are kept, those whose start is nearest
the onset, and the section says how many there were (in this lab's history, 95 windows in 100
held 23 or fewer; the busiest held 67). In a pack built as the alert fired the
section is captured at the time; in a replayed or rebuilt pack it is rebuilt afterwards from the
alert history, cut at the alert's time. A history that cannot be read, or holds nothing yet,
is said.

## The monitoring side {#observer}

When several devices stop answering in the same minute, the cause may be the poller itself
(Prometheus, the SNMP exporter, the host they run on) or something beneath the devices (the
path to them, the host they run on), as well as each device. The health section is the devices'
side; this section is the collector's, over the same window (from 15 minutes before the onset
to the alert's time):

- **Each scrape job** polling the alert's device or a device within two hops of it, read across
  **all** its targets, not only those devices: how many targets, scrapes and failed scrapes, how
  many targets failed at least once; minute by minute, the most targets failing at once and
  when, the first and last failing minute, and the minutes with half or more failing; the
  slowest scrape against the job's timeout, and the quickest failed scrape. A failure that runs
  to the timeout is a target that did not answer in time; one over in under 5 seconds was
  **refused** (by the exporter or Prometheus), never a device's silence (measured over 44 days in
  this lab: every device-side failure ran 20 to 55 seconds). The timeout and interval are read
  from Prometheus's configuration as it is now, which may differ from the alert's time, and the
  section says so. At most 20 jobs; the rest are counted.
- **The SNMP exporter**, as Prometheus holds it: the packets it sent and retried and its
  slowest completed walk, how many targets it refused, and its own scrape when Prometheus
  scrapes it (otherwise said: not collected).
- **The host Prometheus runs on**, from the node exporter Prometheus scrapes on that host (an
  instance at `localhost`, `127.0.0.1` or `[::1]`): CPU busy and the 1-minute load, each its
  lowest, average and highest over the window and when the highest was, beside its **usual**
  (the median over the day before the window) and the host's CPU count; and the memory
  available. With no such node exporter, these say so.

Each piece has its own reference (`observer:job:<job>`, `observer:exporter`,
`observer:host:cpu`, `observer:host:load`, `observer:host:memory`) and its own read state, as a
health figure does: a question Prometheus could not answer is said on each piece it would have
filled, never a zero. Six questions are asked in all, each summed by job or by host, so their
size does not grow with the fleet, and each is bounded at the connection's own 5 seconds
(they took 0.06 seconds at most in this lab). In a pack built as the alert fired the section is
captured at the time; in a replayed or rebuilt pack it is rebuilt afterwards, Prometheus asked
over the alert's window, and marked so. A pack kept before 27 Oct 2026 (schema 5 or older) holds
none; its card offers Build again.

## References and the hash {#references}

Every section has a reference (`logs`) and every piece in it one of its own (`logs:3`; a
health figure's is its id, `health:dev:12:cpu`; another alert's, `concurrent:<episode id>`),
drawn beside it.

**One device has one id.** Every section that names a device by id (the health figures, the
other alerts) names it by the id {{product}}'s network model gives it, the same id the
topology Explain sends uses, so a figure is cited as `health:<that id>:<figure>`. A device the
model does not know is `dev:@<name>`. A pack kept before 27 Oct 2026, or built while the model
could not be read, may name a device `dev:@<name>` where the model now has another id: Explain
names it by the model's id as it sends the pack, never changing the kept pack, checks the
answer against what it sent, and links each citation to the piece on the card. The pack is hashed: a sha256 over its canonical form, shown on the card, the same
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
2. `kept`: an answer already kept with this pack (below) is drawn, and nothing is sent. Only
   **Explain again** goes on to ask.
3. `topology`: the part of the network around the alert's device, from {{product}}'s network
   model (below): the device and everything one link, adjacency or cable away from it, with
   what the pack captured as observed when the alert fired (never read again). It goes unless
   the network has the topology class turned off; the answer then says "No topology was sent
   with the pack" and why. It opens with a **coverage header**: each layer of the network's
   context (inventory, intent, adjacency, performance, events, endpoints, flows) as present,
   partial or not collected, with its source and age, so a gap is said rather than left to be
   guessed. Endpoints and flows are not collected yet.
4. `ask`: the pack (its health figures among it) and the topology go as data (masked when they
   were built, and masked again on the way out), the pack's layout, the topology's layout, the
   network's summary and the allowed reads as the instructions' context; no tool is offered,
   so the model can only read. The model is told to cite each figure by its reference, never
   to state a figure the pack does not hold, to say when a device's own figures do not explain
   it, and to offer a cause the evidence does not show only as a hypothesis, with the read that
   would confirm it. With the topology class off, only the alert's device's own figures go
   (which devices are near it is topology), and the pack says the rest were withheld.
5. `check`: every hypothesis must cite pieces of the pack as it was sent, by their references,
   or items of the topology that was sent, by their ids, and name one read-only command a
   person could run to confirm it (a `show`, `ping` or `traceroute`, as Show commands allows).
   One that cites a reference neither holds (an id of the network the topology sent did not
   include, or a health figure that was withheld, counts as not held), or names a command that
   is not a read, makes the whole answer "couldn't analyse", and nothing is shown. An answer of
   **no fault found** holds no hypothesis and must cite the evidence it checked, each piece one
   the pack or the topology holds and one that was read (a section that was unreadable or
   absent is not healthy evidence); one that does not is "couldn't analyse" too. And every
   device the answer names, in its rationale or a hypothesis, must be cited somewhere in it (its
   figures, its alerts, its log lines or its id in the topology): a name is matched whole
   against the devices the pack and the topology sent name (`edge1` inside `edge10` is not
   edge1; a device of the network that was never sent is not one the answer could cite, so it
   is not asked for). When the answer names a device the pack holds and cites nothing of it,
   {{product}} cites it itself: the device's other alert in the pack, else its first health
   figure, or the alert itself for the alert's own device. That citation is {{product}}'s, not
   the model's: it is kept with the answer apart from the model's own and drawn under **cited
   by Mercury**. A device the pack holds nothing of (one only the topology knows) still makes
   the answer "couldn't analyse", naming it. An adjacency cited with its two ends in the other
   order, or a topology id written with `topology:` before it, is read as the id the topology
   sent, and what the answer wrote is on that reference's hover.
6. `keep`: the model's answer (hypotheses, no fault found, "the pack cannot say", or "couldn't
   analyse") is kept with the pack, beside any earlier one. A refusal before the model answered
   (hosted AI off, a cap, the provider down) is not an answer and is not kept.
7. `show`: a short rationale, then at most three hypotheses, the most likely first, each with
   the references it cites (a pack piece is a link to it above; a topology id is drawn as text)
   and its confirming read; under them, **cited by Mercury** lists each citation
   {{product}} added (the device, where the answer named it, and the pack's piece, linked),
   never among a hypothesis's own. It is a hypothesis, not a finding: nothing was run. Run the read
   through **Show commands** to check it. Or **no fault found**: what the evidence shows, and
   each piece it checked, linked. That is an assessment of the pack, not of the network: only
   what the pack holds was checked, and an alert can fire on a passing blip or a threshold set
   too low. Explain is told to say so rather than invent a cause.

### An answer is kept with its pack {#kept-answers}

A pack is frozen, so the same pack, prompt version and model ask the same question. Each answer
is kept with its pack, keyed by those three (the records store **Explain answers**, moved on
**Settings › Installation › Connections**, Record stores, as every records store is): opening the alert again, reloading the page, or following
History's link to the call draws it, marked **kept with the pack** with when it was explained
(who pressed it, on hover), and nothing is sent. Pressing **Explain** on a page drawn before the
answer was kept draws the kept answer too.

With an answer kept, the button is **Explain again**: a new recorded call, said beside it with
its cost ("A new call, up to $…; this answer stays"). Its answer is kept beside the first; the
newest is drawn, with the count of earlier ones, and each stays in History. If the kept answers
cannot be read, Explain sends nothing and says why (whether the pack was explained already is not
known); Explain again still asks.

### One press, one call {#one-press}

Each press of an AI control carries its own key. A press sent twice (a retry, a form sent again)
returns the first one's call; a second press of the same alert while the first is still being
answered (a double click, or a press after the page was reloaded mid-call, by you or someone
else) waits for that call and draws its answer. Neither sends anything to the provider; each is
its presser's own row in History, "joined call …, nothing sent", costing nothing and counted as
no call, and the call's row names who joined it. A press joins only a call with everything
that shapes the answer or who may see it the same: the feature, the network, the subject, the
prompt and its version, the model, and the presser's access scope (what Mercury allows them,
as a person, a service or unverified). A press sent again under another access scope is
refused, naming both, and is never handed the call. This holds for every AI control, not only
Explain.

## What of the network Explain sends {#topology}

{{product}} compiles each network into a model with no AI call: its devices (name, role, site,
platform and management address, from the inventory and NetBox), the subnets two or more
devices share by committed intent (the links), the adjacencies intent implies (OSPF, OSPFv3
and BGP), each interface's addresses, VRF and VLANs, and OSPF and BGP membership (router id,
areas, passive interfaces, AS and peers). It never holds a configuration line, a description
or a credential: it holds what intent means for the topology, not the intent itself. It is
rebuilt only when the committed intent, the inventory or (on NetBox) the cables change.

**NetBox's cables.** For a network whose inventory is NetBox, the model also reads the cables
NetBox documents, through the NetBox connection (Settings › Installation), read-only: at most
once per the network's inventory refresh interval (five minutes unless the network's source
says otherwise), the same read kept between. A cable between two interfaces of devices in the
model (known by their NetBox ids) whose two devices share a subnet in intent joins that link,
which then says it came from **both**; one that joins no subnet (a switch-to-switch trunk, a
device with nothing committed) is a link of its own, `link:netbox-cable:<cable id>`, so the
devices it joins are a hop apart. Every link says its source: **intent**, **netbox_cable** or
**both**. A cable whose ends are not two interfaces of devices the model knows (a console
cable, an end in another network, a cable with no ends) is counted, by why, and not drawn. A
cable's label is NetBox free text and is never sent. The topology Explain sends says when the
cables were read and how many were left out (`netbox_cables`). A network on a local CSV
inventory has no cables, and the topology says so; a read that fails is said, and the links
are intent's alone.

Explain sends the alert's device and what is one hop from it: the devices on its links (a
switch carrying its segment among them), each with its hop and what reached it, the links and
the device's adjacencies, and the cables LLDP reports. What was observed rides on each item
with the time it was read: the Topology reader's read the pack captured when the alert fired
(its section 7), never a read made when Explain is pressed. A read that could not be used then
(never made, too old, later than the alert, or holding nothing for this network), or a pack
that captured none, is written "could not read" with why, never left out. The expected half
(devices, links, what intent implies) is the network model as it is when Explain is pressed.
With a pack built after its alert (replayed, or rebuilt from the alert history) the topology
says so itself, in its `as_now` line: "the network model as it is now ... not as it was at the
alert's time: it may differ from then", and, for a rebuilt pack, that nothing observed then
was captured. The answer says the same under it ("The network sent with the pack is the network
model as it is now ..."). A segment of more than 16
devices, or one whose devices share an address, is listed and not walked through. Each item
has a stable id (`dev:<NetBox id>`, `link:<subnet>`, `adj:...`, `cable:...`) that a hypothesis
may cite.

**The topology class** is on for every network by default. It is the network's setting
`ai_topology_class`; turned off, Explain sends the pack alone and says so beside the answer,
and a setting that cannot be read counts as off. No screen turns it off yet: its control on
the network's Settings is registered to build (C1713). A classification marking that forces AI
off is planned and not built yet: nothing reads one today.

## Build again {#rebuild}

A pack is frozen once kept, so a pack kept by an earlier release holds only what that release
gathered: one kept before 27 Oct 2026 (schema 4 or older) holds no other alerts around the
onset and the health of the alert's device alone. Its card says which schema it was kept with
and which this release builds, and, for a past alert the alert history holds, offers **Build
again**: "Build again with this release's evidence: other alerts, two-hop health, the monitoring
side, one id per device; the pack kept now stays". A pack kept before the monitoring side was
gathered (schema 5) says it holds none, and offers Build again too. It is busy on itself until the new pack is drawn in its
place, and is recorded as the person who pressed it. It reaches no device.

1. `find`: the kept pack, and any pack already built again from it; one that is kept is drawn,
   never built twice (two people pressing it at once get one pack).
2. `check`: the kept pack's schema against this release's: a pack of this release's schema is
   not built again (the refusal names both); and its past alert, from the alert history (the
   one it names, or the one whose alert and time it matches). A pack whose alert the history
   does not hold, or one still firing, cannot be built again, and the card says why in place of
   the button.
3. `rebuild`: a new pack as [Build evidence](alert-history#build) builds one, as of the alert's
   time: the other alerts in the window, History up to then, the Intent check at the commit
   then, the health figures of every device within two hops in the network model as it is now
   (NetBox's cables among its links, on a NetBox network), and the log lines; one id per
   device. It names the pack it was built from: its id, schema, when it was built and its hash.
4. `keep`: kept beside the old pack in the evidence pack record, under its own id (the alert's,
   ending `-s6` for schema 6). The old pack is never rewritten or deleted: it stays in the same
   record, and opens from the new one's **Show it**.
5. `show`: the new pack drawn in place, with Explain. From now on the alert's row on History,
   and the Alerts tab's list, open the new pack, and Explain from it reads it. The old pack,
   opened, says it was built again and offers **Show it** for the new one; Explain on it still
   reads the old pack, as it was.

Every Explain answer names the pack it read: its id, schema, and when it was built (and the
alert's time it is as of), so two answers about one alert are never confused.

## Where it is kept {#kept}

In the evidence pack record (`evidence_packs.jsonl` in the data folder, one line per pack, or
the records database once moved: Settings › Installation › Connections, the Record stores
card). If the record cannot be read, no pack is built, and the tab says so.
