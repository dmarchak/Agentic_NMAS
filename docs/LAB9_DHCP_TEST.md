# Lab 9 Objective 4: the DHCP steering test (at the lab)

DHCP steering (SDN › Apps, the **DHCP steering** card; docs/manual/how-it-works/dhcp-steering.md)
makes each host's DHCP broadcast unicast to the router from the edge port it enters, and drops
a server reply arriving on any port but the router's. This is the test a person runs at the lab
to show it works on the real fabric. Mercury's own checks stop at the switches' tables (each
flow read back as sent); a lease from a host is the test only a person at a host can run.

Names are roles: **the router** (the DHCP server), **host A** and **host B** (two end hosts on
the same edge switch, if the lab has two there; else on any two edge ports), **lab9** (the
network in Mercury).

## Before the test (once)

In NetBox, with the operator's login (docs/LAB9_NETBOX_STEPS.md sections 8 and 9 hold the rest):
1. **The router's Service:** on the router, **Add a Service**: name `dhcp`, protocol UDP, port
   67, and in **IP addresses** the address of the interface that serves the hosts (its
   address on the hosts' subnet). Leave the tag `mercury-protected` OFF: the config context's
   `dhcp` and `dhcp-reply` classes (section 9) already protect DHCP, owned by
   `feature:dhcp-unicast`; a tagged Service makes a class owned by nobody, which refuses the
   trusted-port drop.
2. **The router's MAC:** on that interface, its primary MAC address (NetBox 4.2: **Devices ›
   MAC Addresses › Add**, then choose it as the interface's **Primary MAC address**). It is the
   router's own MAC for that interface (`show interfaces <name>` on the router names it as
   "address is").
3. **Its cable:** that interface connected to the switch port it plugs into, status Connected,
   the port tagged `openflow` with its `openflow_port` number.
4. **Every switch on the way:** each has its `openflow_datapath_id`, and each port on a cable
   between two switches is tagged `openflow` with its `openflow_port`.
5. In Mercury: SDN › Apps, **NSOT export**, **Export from NetBox…**, then **Commit the export**.

- **PASS:** the DHCP steering card names the router, its address, its MAC and the switch port
  ("on <switch> port <n>"), says "protected", and names the edge switches. A value NetBox does
  not record is named on the card instead: fix it in NetBox and export again.

## The test

1. **Steer.** SDN › Apps, DHCP steering, **Preview steering…**. Read the rows: on each edge
   switch, one "client request, unicast to the server" per host port and two "server reply on
   an edge port, dropped"; on each switch between, one "steered request, toward the server".
   Press **Steer DHCP on N switch(es)**.
   - **PASS:** the card says "DHCP steering applied", Verified, every switch "read back as sent".
2. **Watch host B.** On host B, start a capture of DHCP: `sudo tcpdump -ni <its interface>
   -e port 67 or port 68` (or Wireshark with the filter `bootp`).
3. **Renew host A's lease.** On host A (Linux): `sudo dhclient -r <interface>` then
   `sudo dhclient -v <interface>`; on Windows: `ipconfig /release` then `ipconfig /renew`; on
   macOS: System Settings › Network › the interface › Details › TCP/IP › **Renew DHCP Lease**.
4. **Look.**
   - **PASS, the lease:** host A gets an address from the router's pool: `dhclient -v` prints
     `DHCPOFFER of <address> from <the router's address>` and `bound to <address>`
     (`ipconfig /all` names the router as **DHCP Server**).
   - **PASS, no flood:** host B's capture shows NO `DHCP, Request` or `Discover` from host A's
     MAC. (Host A's broadcast left its edge port as unicast to the router.)
   - **PASS, the counters:** SDN › Flows, host A's edge switch: the steering flow with match
     `in_port=<host A's port>` and `udp_dst=67` has its packet count risen by host A's DISCOVER
     and REQUEST (2 or more since the last read; SDN › Flows reads every 30 s). Back on SDN ›
     Apps, the card's **Counted** line has risen too.
5. **Remove (when the test is done, or to compare).** **Remove steering…**, then **Remove N
   steering flow(s)**.
   - **PASS:** the card says "Removed DHCP steering"; renewing host A's lease again, host B's
     capture now shows host A's broadcast DISCOVER (it floods as before).

Not covered: DHCPv6 (UDP 546 and 547) is not steered, so a host's DHCPv6 solicit floods as
before. That is expected, and the card says so.

## On a FAIL, send

- which step failed and what it showed, word for word (the card's text, `dhclient -v`'s output,
  or the capture's lines);
- SDN › Apps' DHCP steering card at rest (a screenshot), and the preview's rows if the preview
  refused;
- SDN › Flows on host A's edge switch and on the router's switch (screenshots), showing the
  steering flows and their packet counts;
- History, the newest SDN flow operations (each switch's run);
- the time the test ran (UTC), so the controller's and Mercury's logs can be read for it.
