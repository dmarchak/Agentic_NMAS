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
(delete-strict, and Mercury's own flow put back where it displaced one, risk medium). Every flow a
response adds carries a hard timeout (600 seconds unless you set another in the preview, at most
the network's ceiling), so a mistaken response expires by itself; its meter is removed by Mercury
once those flows have expired.

The action proposed is the rule's default in the network's **response policy** (SDN ›
Responses, the rules), chosen in code, unless an AI classification proposed another (below).
The policy also limits which actions each rule may take on the network: a preview or a confirm
of any other is refused, naming the action, the rule and what is allowed. In **HITL** (the
default) a response waits for you on SDN › Responses. In **AUTO**, which a person turns on for
one network with a reason and an expiry, the loop applies only actions within the allowed risk,
each recorded as autonomous with that reason and with who chose the action. Every response,
AUTO's or yours, writes one line to the loop's log: who applied which action on which switch,
the operation, and the resulting entries as Verify read them back.

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
