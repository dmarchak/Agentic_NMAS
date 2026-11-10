# The container harness's recordings

Real Ryu 4.34 reading real Open vSwitch, in the container harness (tests/containers/compose.yml,
`scripts/nmas-harness`): none of it is typed.

| File | How it was made | What is real, what was chosen |
|---|---|---|
| `ovs-userspace-ryu-4.34-py3.5.json` | `scripts/nmas-harness record --python 3.5 --out tests/fixtures/sdn/harness/ovs-userspace-ryu-4.34-py3.5.json`, 2026-11-07 ~04:16 UTC on the development laptop: Ryu 4.34 on Python 3.5.10 (python:3.5-slim, tests/containers/ryu/constraints-3.5.txt) with `ofctl_rest`, `rest_topology` and the harness's 1.0-and-1.3 pin, reading Ubuntu 24.04's Open vSwitch 3.3.9 on its userspace datapath (two bridges, datapath ids 3 and 4, tests/containers/ovs/bridges.conf), through `tests/containers/record_answers.py` in the runner. Each answer's status and body text as Ryu sent it, keyed by path. | All of it is Ryu's and OVS's, but for **one edit, stated in the file's `_edit`**: `/stats/tablefeatures/3` keeps the first two and the last of OVS's 254 tables (13 MB a switch whole; the others differ only by their id and their NEXT_TABLES), re-serialised by `json.dumps`. The bridges, their port names and numbers, and the port held down are the harness's choice; the dummy ports' addresses (aa:55:aa:55:00:xx) are OVS's, and each bridge's own port's is random per run. |

Read by `tests/fixtures/sdn/ryu_recorded.py` (`RecordedRyu(HARNESS)`), so the tests run
Mercury's real Ryu driver on these answers with no socket: `tests/test_sdn_port_health.py` (T9)
and `tests/test_sdn_table_placement.py` (T10).

## DHCP steering's proof (Lab 9 Objective 6, the REST path; C2904)

`dhcp-steering-ovs-3.3.9-ryu-4.34-py3.5.json` is a **recorded measurement**, made 2026-11-10
04:03 to 04:05 UTC on the development laptop. The suite cannot start a container (its children
are confined), and `ofproto/trace` runs in the OVS container, which the runner cannot reach, so
it is a recording and `tests/test_dhcp_steer_harness.py` holds it to the code.

How, each step a command:
1. `scripts/nmas-harness up --python 3.5` (Ryu 4.34 on Python 3.5.10, OVS 3.3.9 userspace).
2. On the laptop, `python tests/fixtures/sdn/harness/dhcp_steer_proof.py render requests.json`:
   `dhcp_steer.compile` over the harness's NSOT export (that script's `harness_export`: br3 and
   br4 cabled port 2 to port 2, the end host h1 on br3 port 1, the DHCP server rtr, MAC
   00:00:5e:00:53:01, on br4 port 1), each flow rendered by Mercury's Ryu driver.
3. In the runner, inside the internal network, as the caller's uid with the requests' folder
   mounted at `/out`: `docker compose -f tests/containers/compose.yml -p mercury-harness
   --profile check run --rm -v <folder>:/out --user <uid>:<gid> --entrypoint python runner
   /out/dhcp_steer_proof.py apply /out/requests.json /out/applied.json`: each request through
   the driver's one send path (`RyuDriver.apply`) to ofctl_rest, then each table read back.
4. `docker exec mercury-harness-ovs-1 ovs-appctl ofproto/trace <bridge> '<flow>'` for the four
   packets the file's `traces` name (each with its exact flow text), and `ovs-vsctl list
   controller` and `ovs-appctl dpif/show` beside them.
5. `scripts/nmas-harness down`.

**What it shows.** The DHCPDISCOVER entering br3 port 1 matched the request flow (cookie
0x4d45000000000002), `set_field:00:00:5e:00:53:01->eth_dst`, `output:2`; crossed the patch;
on br4 matched the transit flow (cookie 0x4d45000000000001), `output:1`, the server's port
(datapath port 4, `dpif/show`): `Datapath actions: set(eth(dst=00:00:5e:00:53:01)),4`. A
broadcast and a unicast server reply arriving on br3 port 1 each matched a drop flow (cookies
0x...03 and 0x...04): `drop`. The server's own reply on br4 port 1 matched no steering flow.

**One thing OVS did beside the tables:** each DHCP reply trace says "outputting DHCP packet to
local port for in-band control" (`Datapath actions: 103`, the bridge's LOCAL port). That is
OVS's in-band control (the harness's controllers have no `connection_mode`, so in-band, OVS's
default), which hands a DHCP reply to the bridge's own interface whatever the flows say; it
reaches no other OpenFlow port. Whether the lab's OVS hosts run in-band is the register's row.

**To make it again,** the steps above; for the recording of the table above, the same command; the harness's images build from
tests/containers/ (network access is needed once, to pull the base images and Ryu's packages).
**Still to make, at the lab:** the ProCurve's own `tablefeatures` answer (the design's section
9); until it is a fixture, the ProCurve's tables are its platform profile's
(`modules/platforms/profiles/aruba_os_switch.yml`, C2601).
