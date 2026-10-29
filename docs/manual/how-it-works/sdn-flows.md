# Change an SDN switch's flows, and respond to a threat

Every flow and meter Mercury adds, edits or removes on an SDN switch goes one way, whether you
asked for it on [SDN › Flows](sdn#flows) (**Add flow…**, **Edit…**, **Remove…**) or confirmed a
response on [SDN › Responses](sdn#responses). Mercury talks to the switch only through its
controller; nothing logs in to the switch.

![A change to an SDN switch's flows, a person's or a response's: the plan reads the switch's flow table through its controller, checks OpenFlow 1.3's match prerequisites and refuses before any request exists, and renders the exact REST requests and the undo of each; you confirm, bound to their hash; holding the switch, the plan is made again and a moved hash sends nothing; each request is sent through the controller; Verify reads the table back, a meter's counters twice; a failed request or check rolls back what landed, newest first, and reads the table back; the run is recorded in the network's flow intent, and History shows it.](diagrams/sdn-flows.svg)

## What each change is

- **Add**: one flow, with Mercury's cookie (Mercury sets it). A flow already at the same table,
  priority and match is refused: OpenFlow would replace it without a word, so edit or remove
  that one instead.
- **Edit** (Mercury's own flows only): new actions are a **modify-strict**, the flow's match,
  priority, cookie and timeouts unchanged. A change of its match, priority or table, or of its
  timeouts (OpenFlow 1.3 keeps a flow's timeouts on a modify), is a **delete-strict** of the old
  flow and an **add** of the new one, as one operation; the preview says so, and a rollback puts
  the old flow back.
- **Remove**: a **delete-strict** by the flow's table, priority, match and its whole cookie,
  never a wildcard. The table-miss flow (priority 0, matching everything) needs
  `remove table-miss` typed: without it the switch stops asking its controller about new
  traffic. Removing a flow of the controller's own warns that a reactive application may install
  it again on the next matching packet.
- **A meter**: one meter, its bands checked against the switch's meter features (how many bands
  it allows, which band types, kbps or packets a second, a burst). A meter a flow still points at
  is not removed.

**OpenFlow 1.3's match prerequisites are checked first.** A field without the field it needs is
refused, naming both: `tcp_dst` needs `ip_proto` 6, `udp_dst` 17, an `ipv4_*` field `eth_type`
0x0800, an `ipv6_*` field 0x86dd, ARP's fields 0x0806, ICMPv4's `ip_proto` 1 and ICMPv6's 58, and
the rest of the specification's table. An address of the wrong family is refused too.

## The steps

1. `plan`: Mercury reads the switch's flow table (and its meters where a change touches one)
   through the controller, checks the change, and renders **exactly these requests**: the method,
   the path and the body the controller is sent, each with its undo. A refusal says what it
   compared, and nothing is sent.
2. `hash`: you confirm as yourself, bound to the requests' hash and to the flows they touch as
   they were read. At the apply the plan is made again; if the switch's table or the requests
   moved, nothing is sent and both hashes are named.
3. `hold`: the switch is held, so one change at a time reaches it; a second is refused, naming
   who holds it.
4. `send`: each request is sent through the controller, exactly as rendered. The controller's
   answer says the request was sent, not that the switch installed it.
5. `verify`: the table is read back (a few times, half a second apart): each flow added or edited
   is there with its cookie, match, priority, actions and hard timeout; each removed flow is
   gone; each meter is there with its band, or gone. A meter's band is then counted twice a few
   seconds apart: its drop count rising while traffic matches shows the limit working; a drop
   flow's packets are counted the same way. These counters are reported, never a failure: the
   traffic may simply not be flowing. **Testing traffic between the hosts is yours**: Verify
   checks installation and counters, and a probe that sends test traffic is registered for later.
6. `rollback`: a request the controller refused, or a check that failed, sends the undo of each
   request that landed, newest first, then reads the table back and says what came back. The
   card reads amber, naming the check and both values.
7. `record`: the network's flow intent keeps each flow Mercury added (its expected match and
   actions), edited, or removed, each meter, and the whole run: who confirmed it (or AUTO, with
   its reason), the requests and their hash, each answer, Verify's checks and the outcome.
   History shows it under SDN flow operations.

## A response to a threat

A detection (a scan, a flood or an unauthorised flow) is answered by an action from the
response catalogue, chosen in code: **drop the source** (one flow dropping the source's packets,
risk low), **rate-limit the source** (one meter with a single drop band, and a flow through it
for every host the controller's topology lists, other than the source, so the meter caps all
the source's traffic on that switch: each host sent out of its own port when it hangs on the
switch, else out of the first link toward its switch; the scan's target first; the switch's
live flows give the ports only when the topology cannot be read, since a scan's own flows
expire within seconds; a host the topology cannot place, or one it does not list yet, is not
metered, and the preview names each under What will not happen, with the fact that only the
source's IPv4 traffic is metered; risk low), or **remove the unauthorised flow**
(delete-strict, and Mercury's own flow put back where it displaced one, for the time its hard
timeout has left, never its whole timeout again, and not at all once it has expired; risk
medium). Every flow a
response adds carries a hard timeout (600 seconds unless you set another in the preview, at most
the network's ceiling), so a mistaken response expires by itself; its meter is removed by Mercury
once those flows have expired. A drop or a rate limit acts on the detection's source; a
flood's comes from its port ([Where a port's source comes from](#port-source), below).

The action proposed is the rule's default in the network's **response policy** (SDN ›
Responses, the rules), chosen in code, unless an AI classification proposed another (below).
The policy also limits which actions each rule may take on the network: a preview or a confirm
of any other is refused, naming the action, the rule and what is allowed. In **HITL** (the
default) a response waits for you on SDN › Responses. In **AUTO**, which a person turns on for
one network with a reason and an expiry, the loop applies only actions within the allowed risk,
each recorded as autonomous with that reason and with who chose the action. Until the AUTO
production-readiness gate is complete, AUTO is turned on only on a network marked **lab** (its
stage, on Settings › Integrations › SDN controllers), and on each pass the loop checks the stage
again: a network not marked lab, or whose stage cannot be read, gets no unattended action, and
every response waits for you. **AUTO never acts on an inferred source:** a drop or a rate limit
runs unattended only on a source the flows themselves name. A detection whose source came from
the controller's topology ([below](#port-source)), or that names no single source (several hosts
on its port, or a topology not read when it fired, so the source would be looked up or chosen),
always waits for you, whatever the allowed risk, saying "the source was inferred from the
topology: a person confirms it" with the comparison it made: AUTO applies only a source the flows
themselves name, the flows entering that port name none, and where the source came from. It is a
row of Needs attention like any response awaiting you, and Mercury refuses an unattended confirm
of such a source too, sending nothing. **When AUTO cannot preview its response** (the switch
is no longer on the controller, the connection is gone, the plan refused), nothing is sent and
the response waits for you as in HITL, its card saying "AUTO could not preview <action>: <why>"
and its Needs attention row naming that failure and that AUTO sent nothing; it clears when you
confirm the response or dismiss it. Every response,
AUTO's or yours, writes one line to the loop's log: who applied which action on which switch,
the operation, and the resulting entries as Verify read them back.

### Where a port's source comes from {#port-source}

A flood, and the scan rule's packet-rate fallback, judge a port, not a source. Their source is
the one address the flows entering that port name. Where those flows name none (they match MAC
addresses only, as the controller's application installs them after a ping), **the detection
names the host the controller's topology lists on that port** (the SDN reader's stored read of
the controller's hosts and links), by its address: its first IPv4 address, else its first IPv6
address that is not link-local. The detection says how ("from the controller's topology: the one
host on port 2, 192.0.2.2 (00:00:00:00:00:02)"), and both the card and the AI classification
read it, so the AI may propose acting on that host. A host listed there with no address to
match (only a link-local one, say) beside one with an address does not count against it, and is
named. When the topology cannot resolve the port to exactly one host, the source stays unnamed
and the detection says why:

- **several hosts** on the port: each is named with its address and MAC, and the card offers a
  **source** picker beside Preview, limited to those hosts. The preview is built for the host
  you choose (its address is in the requests the confirm's hash binds, and the preview says
  "chosen from the N hosts the controller's topology lists on port P: …"); a host that is not one
  of them is refused, naming it and the hosts listed, at the preview and again at the confirm,
  and the AI may name the hosts but never proposes one as the source;
- **no host** on the port, **no address to match**, or the port is **a link to another switch**
  (the source is not attached there; the switch it enters by names it): there is no host to
  choose, so the card says why and offers no Preview; dismiss it with a reason;
- **the topology could not be read** when it fired (not read yet, older than the SDN reader's
  promise, or the controller offering no topology): the preview looks the host up in the
  controller's topology again when you press it, and is refused saying why if it still cannot.

The source is matched in one family: a host named by its IPv4 address is dropped or rate-limited
by that address, so the same host's IPv6 traffic is not matched (and a host named by an IPv6
address keeps its IPv4 traffic and any other IPv6 address). **The preview says so under What
will not happen**, for a drop as for a rate limit, and names the host's other addresses as the
controller's topology lists them when you press Preview ("The controller's topology lists this
host (00:00:00:00:00:01) with the addresses 2001:db8:8::1, fe80::200:ff:fe00:1 (link-local):
traffic from them is not dropped by this response"). Where it cannot name them it says which:
the topology lists the host with no other address (it lists only addresses it has seen the host
send from), does not list the host, or could not be read, with why.

### A threat already answered {#already-mitigated}

A response does not stop a detection at once: a scan's sightings stay in its window (60 seconds
by default) after its source is dropped or rate-limited, so the same scan can fire again while
the response is working. **A detection that fires again while one of Mercury's responses holds
its source off is recorded, not proposed**: no card, no AI call, nothing sent, in HITL and in
AUTO alike. The loop's log on SDN › Responses says it fired again while mitigated by response
<id> (the card you confirmed, or AUTO's operation) until <time>, the response's hard timeout.

A response holds a detection off when all of these are true:

- it drops or rate-limits a source, for the same rule, on the same switch;
- it is for the same source, in any spelling of its IPv4 or IPv6 address, or for the same
  detection (a flood over flows that match MAC addresses only names no address, and is held by
  its own port);
- its hard timeout has not passed;
- it is **in force**: every one of its flows is on the switch as the loop read it in that pass,
  and the SDN reader has not read its meter missing.

A response that matches but is not in force is **lost**: the detection is answered as new, and
its log line names the lost response and what is missing, beside its Needs attention row and its
**Re-apply…** on SDN › Flows ([Re-apply a lost response](#reapply)). One that has expired is
named too. The loop checks a held detection again on every pass: once its response expires or
is lost while the detection is still firing, the hold is released, the log says why, and the
detection is classified and answered as new in that pass. A held detection that resolves
releases its hold. **Across switches:** a response applied at its incident's known ingress
switch ([Incidents](#incidents)) holds the source off on every switch of the same controller,
since the source enters by that switch's port, so another switch's detection of the same rule
and source under it is already mitigated too. A response applied where the ingress could not
be told holds its own switch only.

### Incidents {#incidents}

One attack is seen by every switch on its path: the controller's application installs the
source's flows on each switch it crosses, so each switch's rule fires. Mercury answers it once.

1. **Grouped.** In each pass, the detections that fired and are not already mitigated are
   grouped by their rule and their source, the source compared in one spelling (an IPv4 or IPv6
   address compressed, a MAC address in lower case with colons). Only the scan and flood rules
   are grouped: an unauthorised flow is one flow on one switch, and a detection that names no
   single source (a flood or the scan's packet-rate fallback whose port neither its flows nor
   the controller's topology resolve to one host: [Where a port's source comes
   from](#port-source)) has nothing to tie it to another switch, so each is its own incident.
   **One exception, a link port.** A flood over flows that match MAC addresses only is named
   from the topology only on the switch where its host is attached; every switch behind it
   sees the same flood arrive on an inter-switch link port, which names no source. Its flows
   still carry the sending hosts' MAC addresses, so such a detection joins the one incident of
   the same rule (in the same pass, or one awaiting you within the window) whose source is one
   of those hosts, by its MAC or any address the controller's topology lists for it. It is
   listed under **Seen also**, its words saying which MAC its flows carry and whose host that
   is. With no such incident it stays its own; with several (more than one attack behind one
   link) it stays its own too, because the link cannot tell them apart. A response is never
   proposed at such a link port while the incident has a switch that names the source.
2. **The window.** The window is the rule's own, the one it fires within: the scan's
   `sdn_scan_window_seconds` (60 by default) and the flood's `sdn_flood_window_seconds` (30), set
   in the rules on SDN › Responses; there is no second setting. A detection in a later pass
   joins an incident still awaiting you when it is of the same rule and source and at most that
   window after the incident's last sighting: it is recorded as **seen also**, and nothing is
   classified or proposed. One later than that is a new incident.
3. **The ingress switch.** The response is proposed at the switch where the source's host port
   is: the controller's topology, as the SDN reader stored it on its last read (never a
   controller call in the loop), listing a host with the source's address or MAC on a port that
   is not a link's end. When exactly one such port is listed, on a switch whose rule fired, that
   switch is the ingress. Otherwise the ingress cannot be told (no source named, the topology not
   read now, no host or several ports listing the source, or the source on a switch that has not
   fired), the card says why, and the switch that saw it first (the earliest detection; on a tie,
   the first reported) is proposed.
4. **One AI call.** Classification runs once per incident, on the ingress switch's detection
   and its evidence pack, so 50 switches seeing one scan are one call, not 50.
5. **One response.** In HITL, one response awaits you, on one row of SDN › Responses and one
   row of Needs attention; in AUTO, the loop applies it once, at the ingress. The response's
   record keeps its incident (whether its switch is the known ingress, and how many switches
   saw it), which is what lets it hold the source off across switches (above).
6. **Inactive.** An incident is no longer active once none of its switches shows it: one
   switch's detection resolving while another's still fires keeps it active.

The loop's log names each incident seen on several switches in one line: the rule and source,
how many switches, the window, the ingress and the switches seen also.

No response, in any mode, may cover the network's **control channel**: a flow whose match could
carry LLDP (the controller's topology discovery), names one of the controller's addresses (its
connection's URL and southbound address, when each is an address; a prefix holding one counts),
or allows OpenFlow's port (6653, 6633, or the southbound address's own) is refused at the
preview and again at the confirm, naming the change and what it covers; nothing is sent. A
removal is refused only for a flow that names control traffic itself. Mercury does not know the
address each switch reaches the controller from, so a switch's own in-band control address is
not compared.

## Re-apply a lost response {#reapply}

A switch that restarts or reboots drops its flows and meters before their hard timeout, so a
response can stop working while its record says it is still in force. The SDN reader compares
each response's recorded flows and meter with what the switch holds, every 30 seconds. While a
response has something missing and its hard timeout has time left, **Needs attention** has a
row for it. The row names the network, the switch (its datapath id and the name it reports),
the response (its action, its source and its operation), what is missing, and the time left.
The row clears when the reader finds the flows installed again, or when the hard timeout
passes, the moment the response would have expired anyway, or when a **newer response answers
the same threat on that switch**. That happens when the threat is still there: its detection
fires again, the lost response no longer holds it off, so it is answered as new
([A threat already answered](#already-mitigated)), and you apply that newer response. Once the
newer one is in force, by the same test the loop uses (the same rule, the same switch, the same
source or the same detection, and every one of its flows and its meter in place as the reader
last read them), the lost one's row goes, and Needs attention's **What was checked** names the
lost response and the one answering it. A newer response for another source, another rule or
another switch, or one that is itself not in force, leaves the row up; so does a controller
that has not answered since, because whether the newer response is in force is then not known.

On [SDN › Flows](sdn#flows) a lost response answered this way is drawn **Answered**, naming
the newer response and until when it is in force, with no Re-apply…, judged by the same test
over the same SDN read the page draws.

The row opens the switch on [SDN › Flows](sdn#flows). There the response is drawn **Not in
force**, with **Re-apply…**:

1. `plan`: Mercury reads the switch's flow table and meters now. The preview puts back exactly
   the response's flows that are missing, and its meter if that is gone too (the meter first,
   so the flows can point at it). Each comes back as recorded: the same cookie, match, priority
   and actions. Flows still installed are left alone. A drop or rate limit put back still
   matches its one source address, so its preview says again, under What will not happen, that
   the same host's other family is not matched, naming the host's other addresses as the
   controller's topology lists them now (the sentence its own preview said; see
   [Where a port's source comes from](#port-source)).
2. `hash`: you confirm as yourself, bound to the requests' hash.
3. The hard timeout is **never extended**. Each flow goes back for the time its record has
   left, less 60 seconds, the time a confirm may take. A confirm more than 60 seconds after the
   preview is refused, naming both timeouts, and nothing is sent: preview again. A response
   with less than 60 seconds left is not re-applied: let it expire, or answer the threat again
   on SDN › Responses if it is still there. A response whose threat a newer response already
   answers on the switch, as read at the preview or again at the confirm, is not re-applied
   either: the refusal names the newer response, and nothing is sent. Putting the old one back
   would be a second answer to one threat (a drop beside a newer rate limit would drop what
   the newer answer only limits); this is what you see on a page drawn before the newer
   response was applied.
4. `hold`, `send`, `verify` and `rollback` run as for every change above.
5. `record`: the run is recorded as a **re-apply** of the response, naming the operation that
   first applied it, and it gets its line in the loop's log. The response's own records stand
   as they were, so it keeps the expiry it was applied with.

Mercury never re-applies a response by itself, in any mode. Doing that waits for the AUTO
production-readiness gate. A flow you added yourself on SDN › Flows is not a response: when it
goes missing it is drawn **Mercury's, missing** on Flows, with no row and no Re-apply….

## Classify a detection with AI {#classify}

**Classify** on a response awaiting you asks a model what the detection is: whether it is a
threat, its kind (a port scan, a flood, an unauthorised flow, another, or none), how severe, the
hosts and switch it touches, what it recommends and why, and which catalogue action fits, with
its parameters and the evidence it rests on. It is one recorded AI call as you, capped like
every AI call; History lists it under AI calls. The rules found the detection; the model only
advises, and nothing is sent to a switch until you preview and confirm the response as before.

The loop can ask the same question by itself for each detection it finds, but only where an
admin turned the background feature **The SDN loop classifies each detection with AI** on for
this network, after seeing its estimate (calls a day from the network's own detection history,
and their cost), with its own day and month caps. It is off by default, and while it is off the
loop records the refusal, sends nothing and proposes the catalogue's default. **The screen that
turns it on, Settings › AI, is not built yet**: until it is, the feature stays off on every
network, and Classify is a press of yours.

When one pass finds several detections, the loop asks about them **at once, each its own call**,
up to a fixed number at a time, so the responses wait about one call rather than one call per
detection. Each detection's answer is its own: a call that fails, or one a cap refuses, leaves
only that detection without a classification (its rule's default awaits you, said), and the
others are classified as usual. Every call's worst case is held against the caps while it is in
flight, so calls at once never pass a cap together; when the cap fits only some of them, the
ones that reached it first are sent. The log and the responses keep the order the rules found
the detections, whichever call finishes first: each detection's classify line names how long its
own call took, and the pass adds one line with the classify step's total.

**What an unauthorised flow does is decided in code, not left to the model.** When the rule
finds one, Mercury reads the switch's table as collected and says, in the detection's words and
as its **effect**, what the flow does to the traffic it takes, compared with the flow below it
that would take that traffic without it:

- **lifts**: it took the place of one of Mercury's drops or meters (the same table, priority and
  match, recorded and no longer installed), or sits above an installed one taking its traffic,
  and does not keep it: Mercury's mitigation is undone;
- **shadows**: the same, over a Mercury flow it replaces with other actions;
- **drops**: it has no output;
- **diverts**: it sends traffic out another port than the controller's own flow for that
  traffic does;
- **forwards**: it sends it where the controller's own flow does, changing it no more;
- **unknown**, naming why: a flow above it takes all its traffic first; it continues to another
  table or a group; it changes the packet where the controller's flow does not; or below it only
  the table-miss (which asks the controller) or flows that are not authorised would take it.

Traffic of the flow that only the table-miss would take is said to be the controller's to
decide. A Mercury flow it displaced goes into the evidence as a piece of its own, with its own id
(`intent:<connection>:<switch>:<cookie>`), what it was (its cookie, match, actions and timeouts)
and the response that installed it, so the model can cite it; the controller's flows the effect
names are sent beside the unauthorised flow. How severe it is is the model's to say, above a
floor the effect sets in code: a flow that lifts, shadows, diverts or drops is at least **high**.
A lower rating is raised, and the classification shows the model's own rating beside it and
why; forwards and unknown set no floor.

1. `pack`: the detection's evidence pack, as kept when it fired, its hash checked. A pack that
   changed since, or none kept, is refused and nothing is sent.
2. `egress`: the flows and port rates are the network's topology class, so they are sent only
   while that class is allowed for the network; otherwise nothing is sent, and the card says
   why. The catalogue sent is only the actions the network's response policy allows for the
   detection's rule.
3. `ask`: one call through the AI gateway: the detection, its flows and port rates with their
   evidence ids, the names a device may be given, the network's response timeouts, and the
   response catalogue. The loop's call is refused unless its feature is on and within its caps.
4. `check`: Mercury checks the answer in code before anything of it is used: the action is in
   the catalogue, answers the detection's rule and is one the network's response policy allows
   for it (one outside it is refused, and the rule's default awaits you, never AUTO's); a
   source is one the detection saw; a flow is
   the one it names; a hard timeout is within the network's ceiling; at least one evidence id is
   cited, and every one cited was sent; every affected device is one the evidence names. An
   answer that fails is refused, saying which check, and the proposal stays as it was.
5. `propose`: the classification is drawn on the response's card (marked AI, with the model,
   the cost and the call) and its action becomes the one proposed, with its parameters filled
   into the preview. An answer that finds no threat, or proposes no catalogue action, leaves the
   action for you to decide, and the loop never applies such a response in AUTO.

**What it never does:** it never confirms, never sends a request, and never changes the
response's timeouts beyond the network's ceiling. A refusal from the gateway (hosted AI off, no
key, a cap reached) is drawn beside **Classify**, which is shown disabled with the reason while
AI cannot answer; Preview and Dismiss stay usable.
