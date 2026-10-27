# SDN

A network's SDN controllers and the flow tables of the switches they manage, under OBSERVE.
The sidebar's SDN opens it for the network you are on (`/v2/sdn?list=<network>`). Its tabs are
**Controllers**, **Flows** and **Responses** (what awaits you, HITL or AUTO, the loop and the
detection rules).

The connections are the network's own, set in Settings › Integrations' SDN controllers card
([Settings](settings#sdn-controllers)): a network never takes Default's controllers. With none
set the page says so, "No SDN controller is connected to this network. Add one in Settings ›
Integrations.", with the link, and draws nothing else.

## How it is read {#read}

Mercury's SDN reader reads each network's controllers every 30 seconds, and the page is drawn
from what it kept, never by asking a controller while you look; it redraws by itself when a
read finishes. For each connection the reader asks its driver for the controller's switches;
for each switch, its flow table, its port counters twice a second apart, what the switch says
it is (its own name, the one Mininet gives it), and its meters and meter features where the
driver reads meters. It then decides whose each flow is, by its cookie (see
[Flows](#flows)). A controller that does not answer keeps what it last read, drawn with that
read's time. A connection saved a moment ago is drawn at once as **not read yet**.

The 30 seconds come from the lab's controller application, which removes an idle flow after 30
seconds: a read every 30 seconds sees each flow at least once.

## Controllers {#controllers}

- **The summary**: how many controllers, how many connected and not answering, how many
  switches, and how old the read is (its time on hover).
- **A card per connection**, its state beside its name: **connected**, **partly read** (some of
  its switches could not be read whole, each named), **not answering**, **driver not built** or
  **not read yet**. A connected card lists:
  - **Driver**, and its status (built; later; unmaintained);
  - **Northbound**, the URL Mercury reads, and whether TLS is used and verified;
  - **Southbound**, where its switches connect: informational, never dialled;
  - **Version**, or "not reported" with why (Ryu's `ofctl_rest` reports none);
  - **Cluster role**: not reported; no driver built yet reads one;
  - **Switches**: how many are connected, each by its datapath id, a link to its flows on
    Flows; they are discovered through the controller and not adopted as devices;
  - **Can**: what the driver declares (read flows, port statistics and meters; write flows and
    meters; delete flows), and what it does not offer (Ryu's reads no topology);
  - **Controller's own flows**: the cookies the connection declares as its application's;
  - **Last read**: when, and what (flows, port statistics and meters of N switches, how many
    failed).
- **Not answering** says since when, what failed and how many reads in a row, and that its
  switches' flows are as last read.
- **Test connection** asks the controller now, with what is saved, and answers in place:
  "Answered: N switches connected" or "Couldn't connect: <the reason>" (see
  [Test connection](#test-connection)).
- **Edit connection** opens Settings › Integrations, where the connection is changed.

## Test connection {#test-connection}

**Test connection** on a controller's card, or on its row in Settings, asks that controller
now through its driver, with what is saved, its stored credential among it. It reads the
switch list and the version, and answers beside the button. It changes nothing: the card's
state stays the reader's last read until its next one. A failure is said in the driver's
words: a refused credential, a controller that did not answer within its timeout, an address
nothing listens on.

## Flows {#flows}

Each switch's flow table, Mercury's expected flows beside what is installed.

- **The summary**, for every switch whatever you filter: how many switches and flows, how many
  are Mercury's, how many the controller's own, how many unauthorised, how many of Mercury's
  are missing, and how many meters, with the controllers read and the read's age.
- **The granularity note**, once per switch where it limits what can be seen: a switch whose
  flows match only Ethernet fields and the switch port (L2), or IP addresses and no transport
  port (L3), cannot show a port scan as distinct destination ports; a scan there shows only as
  packet rates, at lower confidence.
- **The filter**: words matched against the switch, a flow's match, its actions or its cookie;
  **Show** applies it. **Hide the controller's own flows** is ticked by default.
- **The switches**, folded, one row each: its datapath id, its own name, its controller, and
  what is wrong (unauthorised flows, Mercury's flows not as recorded or missing, a switch not
  read whole, a controller not answering) or **as expected**. A switch with something wrong is
  open; the rest open on a click, and stay open when the page redraws.
- **A switch's flows**: owner, priority, match, actions, packets, timeouts (a hard timeout
  with the seconds it has left) and cookie, what is wrong first.
- **Whose a flow is**, decided by its cookie, in code (no AI):
  - **Mercury's**: its cookie is in Mercury's range and recorded for this connection, and the
    switch, table, priority, match and actions are the record's; **Mercury's, not as
    recorded** names each difference;
  - **the controller's own**: its cookie is one the connection declares as its application's;
  - **unauthorised**: anything else, named with why (an unknown cookie; Mercury's range with no
    record; a record withdrawn; another connection's record). It is drawn red, with
    **Remove…** ([Add, edit and remove a flow](#flow-operations)).
  - **Mercury's, missing**: recorded and not installed. **Mercury's, expired**: its hard
    timeout, as set, has passed, so the switch removed it as asked: nothing to do.
- **Meters**: each switch's meters (its id, its rate and what happens above it, the packets
  counted in that band) and whose each is, by the flows that use it; and on how many switches
  meters are supported, from each switch's meter features.

## Add, edit and remove a flow {#flow-operations}

Each switch on Flows has **Add flow…**; each flow has **Remove…**, and each of Mercury's flows
**Edit…**. Each opens its form in place:

- **Add**: the table, the priority, the idle and hard timeouts, the match as `field=value` pairs
  (OpenFlow 1.3's names: `in_port`, `eth_type`, `ipv4_src`, `ipv6_dst`, `ip_proto`, `tcp_dst`…)
  and the actions (`drop`, or `output:<port>`, `meter:<id>`, `group:<id>`, `goto_table:<id>`,
  `set_field:<field>=<value>`). Mercury sets the cookie.
- **Edit**: the same form for one of Mercury's flows. New actions change it in place; a new
  match, priority or timeout is a remove and an add as one action, and the preview says so.
- **Remove**: the flow named by its table, priority, match and cookie, removed by delete-strict.

**Preview** reads the switch now and draws the card: what it does, exactly these requests, what
will not happen, any warning (the table-miss flow, a flow of the controller's own), and Verify.
**Send** confirms it, bound to the requests' hash; the result replaces the card: **Done,
verified**, or **Rolled back** naming the check that failed. A match missing a field it needs is
refused at the preview, naming both. How each step works:
[Change an SDN switch's flows](sdn-flows).

## Responses {#responses}

What to act on first: **N awaiting approval**, the mode and whether the loop is running.

- **A response awaiting you**: the detection (the rule, the source, the switch, its confidence
  and its words, an alert with its evidence pack), why no AI classified it (background AI is not
  allowed until cost safety is live), and the action proposed from the catalogue with its risk.
  Its preview button, named for the action ("Preview the drop traffic from the source…"), builds its card as Flows' changes are (the action's parameters checked
  against the evidence: the source is the detection's, the hard timeout within the network's
  ceiling); **Send** applies it as you. **Dismiss with this reason** closes it, sending nothing.
  A response clears by itself when its detection resolves before anyone acts.
- **Mode**: **HITL**, a person confirms each response, is the default. **Turn AUTO on** takes a
  reason, how many hours (at most 24) and the allowed risk (low: rate-limit and drop; medium:
  also remove a flow). While AUTO is on the card names who turned it on, why and until when;
  **Turn AUTO off** ends it at once. At its expiry the mode is HITL again, and the record says so.
- **The loop**: **Start** runs detect, classify and respond on this network every N seconds (5 to
  600); its log lists each pass's steps, newest first; **Stop** ends it after its current pass,
  and the card says who stopped it and when.
- **Detection rules**: each rule's threshold on this network, and the response timeouts: every
  response flow expires at its hard timeout.

Verify checks installation and counters; testing traffic between the hosts is yours.

## At phone width {#phone}

Each tab stacks: the summary, then the cards. A flow row becomes a block, each value under its
column's name; tables scroll inside their box, never the page.
