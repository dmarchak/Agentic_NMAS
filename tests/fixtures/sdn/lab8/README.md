# Lab 8 run fixtures (Ryu 4.34 over Open vSwitch 2.17.12, Mininet 2.3.0)

tests/test_sdn_lab8.py reads these. Each is Ryu's own `ofctl_rest` answer (or, where named,
Mercury's own output), captured from the lab's controller on the NMAS host on 2026-10-27
between 09:14 and 09:34 UTC while the threat ran inside Mininet (`lab/sdn/lab8_topology.py`,
`lab/sdn/lab8_threats.sh`), by the run's harness (the worktree's own `modules/` copied to the
host's `/tmp`, run with Mercury's interpreter against `http://127.0.0.1:8080`: the driver's
`_http` GET of each path, its status, body and content type kept as the S1 fixtures keep
them). Mininet's hosts are 192.0.2.1 to .4 (IPv6 2001:db8:8::1 to ::4); the switches s1 (dpid 1:
h1 on port 1, h2 on 2, s2 on 3) and s2 (dpid 2: h3 on 1, h4 on 2, s1 on 3). The run's evidence,
with every command and its output, is the operator's reports folder, `lab8/`.

| File | Captured | The one edit |
|---|---|---|
| `scan_s1.json` | 09:21:4x, h1 SYN-scanning h3 (hping3, 300 ports at 50 a second): the switch list, s1's flows (the controller's L4 flows, one per probed port, its L2 flows, the LLDP flow at 65535 and the table-miss), ports twice 2 s apart (`sample` 1 and 2), meters (none) and meter features | s2's answers left out and the switch list cut to `[1]` |
| `l2_only_s1.json` | 09:14:2x, the first topology after pings and TCP runs between the pairs: s1's table holds only L2 flows (the lab application learns a MAC pair at L2 on its first packet that is not IPv4 TCP or UDP, and every later packet of the pair, TCP and UDP included, then matches that flow) | as above |
| `flood_s1.json` | 09:25:5x, h2 flooding h4 (iperf UDP, 20 Mbit/s): s1's flows (with Mercury's applied rate-limit flow, cookie 0x4d45d0ee98a11b65), ports, meter 1's configuration and statistics, and the meter features (max_meter 200000, max_bands 1, DROP only, KBPS, PKTPS, BURST, STATS) | as above; the test also takes Mercury's applied flow out of the table, to stand where the response was previewed |
| `flood_detection.json` | Mercury's own output: the flood rule's detection on s1 port 2 at 09:25:30, 1,782.7 packets a second against its baseline (the harness's `observe`) | none (the test sets its network, "lab8" in the run, to Default) |
| `unauthorised_s2.json` | 09:31:4x, after `lab8_threats.sh redirect`: s2's flows with the unauthorised flow (cookie 0xbad0, priority 100, IPv4 to h3 sent out h4's port) | s1's answers left out and the switch list cut to `[2]` |
| `walk_intent_s1.json` | Mercury's own records, not Ryu's: the flow intent of the network SDN lab on s1 as of 23:08:47 on 2026-10-27 (the operator's walk, not the 09:1x run): the three flows its rate_limit_source response for the scan from 192.0.2.1 installed at 23:05:23 (priority 300, METER:1), read from the NMAS host (`flow_intent.read`) on 2026-10-28. tests/test_sdn_classify_walk_cases.py rebuilds the walk's injected flow (cookie 0xbad1, which took the place of the flow to h3) over it | each row's actor fields left out, its response cut to the fields a displaced flow's piece names (`detect.displaced_piece`) |
| `modify_strict.json` | 09:32, the driver's own answers: a flow added on s2 (Mercury's cookie, hard 300 s, a drop for 198.51.100.77, no host's), read back; one modify-strict sending a new cookie, idle 40 s, hard 90 s and new actions, read back; the cleanup, read back | none |

**What the modify-strict measurement shows:** Open vSwitch kept the flow's cookie, idle and hard
timeouts and replaced only its actions, as OpenFlow 1.3.5 section 6.4 says. So an edit of a
flow's timeouts is a delete-strict and an add (`flow_ops.MODIFY_KEEPS`), and `tests.sdn_fakes.
FakeRyu` applies a modify the same way.
