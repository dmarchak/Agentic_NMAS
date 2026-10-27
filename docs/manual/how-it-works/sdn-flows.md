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
risk low), **rate-limit the source** (one meter with a single drop band, and the source's flows to
each destination the evidence saw through it, risk low), or **remove the unauthorised flow**
(delete-strict, and Mercury's own flow put back where it displaced one, risk medium). Every flow a
response adds carries a hard timeout (600 seconds unless you set another in the preview, at most
the network's ceiling), so a mistaken response expires by itself; its meter is removed by Mercury
once those flows have expired.

No AI classifies a detection yet: background AI calls are not allowed until cost safety is live,
and the card says so. In **HITL** (the default) a response waits for you on SDN › Responses. In
**AUTO**, which a person turns on for one network with a reason and an expiry, the loop applies
only actions within the allowed risk, each recorded as autonomous with that reason.
