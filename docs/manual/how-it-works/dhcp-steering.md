# Steer DHCP to the network's server

On an SDN fabric, a host asking for an address broadcasts its DHCP request, and every switch
floods it to every port. **DHCP steering** on [SDN › Apps](sdn#apps) makes each such request
unicast from the moment it enters the fabric: at each edge port (a port an end host is cabled
to) the request is rewritten to the DHCP server's MAC and sent along one path to the server's
port, never flooded. A server reply arriving on any port but the server's is dropped, so a host
cannot answer for the server (the trusted-port rule).

Everything is read from the network's committed NSOT export, never typed and never learned
from the controller: the server is the router carrying a NetBox Service named `dhcp` on UDP
67, with its address, the MAC of the interface that address sits on, and the switch port that
interface is cabled to; each end host's switch port; and the cables between switches. Every
flow is written through the same flow operation as SDN › Flows, as
`feature:dhcp-unicast`, the owner the NSOT's protected classes `dhcp` and `dhcp-reply` name,
so no other writer may install a flow on UDP 67.

**IPv6 is not covered.** DHCPv6 (UDP 546 and 547) is not steered: it floods as before. A server
with no IPv4 address is refused, saying so.

![DHCP steering: the flows are compiled from the committed NSOT export alone (the DHCP server from its NetBox Service dhcp, its MAC and switch port; each end host's edge port; the paths between switches from the cables); each switch's table is read through the controller and one plan per switch renders every request and its REST body; you confirm, bound to their hash; the preview is made again and a moved hash sends nothing; each switch, the server's first, is held, sent its requests and read back; a failure rolls that switch back and puts back the switches already changed; each flow is recorded with its owner, feature:dhcp-unicast. DHCPv6 is not steered.](diagrams/dhcp-steering.svg)

## The flows {#flows}

On each switch, in table 0:
- **a client request**, one per edge port: a UDP packet to port 67, to `255.255.255.255` and
  `ff:ff:ff:ff:ff:ff`, entering that port, has its destination MAC rewritten to the server's
  and leaves on the port toward the server (the server's own port on the server's switch);
- **a steered request**, one on each switch on a path after the edge, the server's switch
  among them: a UDP packet to port 67 and `255.255.255.255` addressed to the server's MAC
  leaves on the port toward the server;
- **a server reply dropped**, two per edge port: a UDP packet from port 67 to port 68 entering
  that port, addressed to `255.255.255.255` or to the server's own subnet, is dropped.

The IP destination is matched and never rewritten: a host with no address sends to
`255.255.255.255`, and the server takes that broadcast delivered to its own MAC, so the request
is unicast on the wire and reads the same to the server. Matching it also keeps every flow
apart from the management traffic Mercury protects, and from a host's renewal, which is
already unicast to the server.

Each flow's priority is ten above the highest flow on its switch that could take the same
packets and is not Mercury's (the fabric's forwarding), and at least 300; the controller's own
flows for its channel and for link discovery match other packets, so they stay above.

## The steps {#steps}

1. `compile`: Mercury reads the committed NSOT export and compiles the flows: the server, each
   edge port, and the path from each edge switch to the server's switch, breadth first over the
   cables between OpenFlow switches (a port tagged `openflow`, not a management port). A value
   NetBox does not record is refused by name: no Service `dhcp`, a Service not on UDP 67, no
   MAC on the server's interface, no cable, a switch with no datapath id, a port with no
   `openflow_port`, an end host on no switch port, or no path.
2. `plan`: each switch's flow table is read through the controller now, and one plan per
   switch is made by the flow operation: each flow already on its switch as compiled is kept,
   anything else of this feature's on that switch is removed by delete-strict, and each new
   flow is added with a fresh Mercury cookie. The preview lists every request with its REST
   body and priority, and its hash. Nothing is sent.
3. `hash`: you press **Steer DHCP on <N> switch(es)**, as a verified person. Mercury makes the
   whole preview again, from the export, the tables and the cookies the preview drew, and
   compares its hash with the one you confirmed; if anything moved, nothing is sent and the
   card names both hashes.
4. `hold`: each switch is held across processes while its plan runs, so no other flow
   operation runs on it at the same time.
5. `send`: the switches go in order, the server's switch first and the edges last, so no
   request is rewritten before its path is there. Each request is sent through the controller
   exactly as the preview showed it.
6. `verify`: each switch's table is read back: every flow added must be there with its cookie,
   match, priority and actions, and every flow removed gone. Testing a lease from a host is
   yours ([the test list](#test)).
7. `rollback`: a switch whose request is refused, or whose table does not read back as sent,
   is rolled back by the flow operation; then each switch this confirm already changed is put
   back, newest first, and the card says what came back.
8. `record`: each flow is recorded in the network's flow intent with its owner,
   `feature:dhcp-unicast`, and who confirmed it; each switch's run is recorded as a flow
   operation, which History shows.

## Settings {#settings}

**Edit settings…** chooses where to steer: **every edge switch**, or chosen ones. A switch on
the way to the server is steered whichever you choose, since the request has to reach the
server. Nothing is stored: **Preview…** carries the choice to the preview, and what is steered
is the flow intent itself.

## The preview {#preview}

The preview names the server, the export it was compiled from, and every request, one row each,
with its switch, what it does, its priority and its REST body. A flow already as compiled is
kept and counted, not sent again. A switch with steering flows this choice no longer asks for
(an edge switch no longer chosen) has them removed in the same plan.

## Nothing to send {#nothing}

When every flow is already on its switch as compiled, the preview says so and offers no
confirm.

## The confirm {#confirm}

The confirm is yours, as a verified person; Mercury does not steer for a service or an
unverified caller. It carries the cookies the preview drew, so the requests it sends are the
ones you read.

## Remove steering {#remove}

**Remove steering…** previews the removal of exactly the flows this feature recorded, each by
delete-strict on its table, priority, match and cookie, never a wildcard: a neighbouring flow
with the same match is untouched. A recorded flow already gone from its switch is named, and
its record is closed at the confirm. Press **Remove <N> steering flow(s)** to remove them, as a
verified person, bound to the preview's hash. The NSOT export and the NetBox Service are
untouched.

## Refusals {#refusals}

Each refusal names what it compared, with both sides, and sends nothing: a value the export does
not record (step 1), an edge switch chosen that has no end host, a switch whose table cannot be
read, a protected class the flow would meet and this feature does not own, or a preview that
moved.

The card at rest runs the preview's own first two steps (reading the committed export and
compiling it). While either refuses, the card reads **can't compile**, says why and what to do
(export from NetBox on the NSOT export card when none is committed; correct NetBox and export
again otherwise), and **Preview steering…** and Edit settings…' **Preview…** are greyed with
that reason: a preview that could only be refused is not offered.

## The result {#result}

The result lists each switch with its outcome and how many flows read back as sent, what was
put back after a failure, and the records closed. Each switch's run is on History.

## The counts {#counts}

The card's **Counted** line adds up the steering flows' own packet counters, as the SDN reader
last read them (never a controller call when the card is drawn): the requests steered and the
replies dropped from another port, since each flow was installed.

## Testing it at the lab {#test}

docs/LAB9_DHCP_TEST.md is the test list: a host's lease renewed, what PASS looks like (the
lease from the router, the steering flows' counters rising on SDN › Flows, no broadcast
DISCOVER seen on another host), and what to send on a FAIL.
