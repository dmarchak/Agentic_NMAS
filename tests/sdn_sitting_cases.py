"""The Lab 9 sitting's evaluation cases for the SDN analyst, built from the analyst tests' own
fabric (tests/fixtures/ai_cases/sdn_analyse/lab9_sitting.json; modules/sdn/b4_eval.py's role
``sitting``). Not a test module: tests/test_sdn_b4_eval.py holds the committed file to what
`document` builds, so the file is never typed by hand.

**What they model** (the Lab 9 sitting of 2026-11-10, on the lab's hardware; nothing of the lab
is here): the analyst without tools missed a planted flow that sent traffic for one destination
out of a port leading away from it, and both techniques reported a flow dropping DHCP replies
and a flow forwarding DHCP requests as a conflict, although no packet matches both.

**The fabric** is tests/test_sdn_analyst.py's `LabRyu`: the recorded controller's switch list,
links and port descriptions, real; flow tables, counters and the host table planted in Ryu
4.34's shapes (the recording holds none). Two hosts are planted, each on an edge port of the
recording (a port no link uses): `NEAR` on Open vSwitch 3's port 3 and `FAR` on the far edge
switch's port 17. The forwarding between them is planted along the recording's own links:
Open vSwitch 3 port 2 to Open vSwitch 4 port 2, Open vSwitch 4 port 1 to the far edge switch's
port 18.

- **misdirected-icmp-ipv4, -ipv6** (planted, to be found): on Open vSwitch 4, a flow above the
  forwarding ones sends ICMP (ICMPv6) for `FAR` out port 3, the link to another switch, while
  every other flow for `FAR` leaves by port 1, toward the switch `FAR` is on.
- **dhcp-disjoint-ipv4, -ipv6** (benign): on the far edge switch's edge port, DHCP steering's
  two flows in `modules/sdn/dhcp_steer.py`'s shapes (and DHCPv6's counterparts): requests from
  the port forwarded toward the server, replies arriving on it dropped. Their matches are
  disjoint (`flow_ops.disjoint`), so neither shadows the other.

Addresses are documentation ranges (198.51.100.0/24, 2001:db8::/32); the MACs are locally
administered.
"""
import json

from modules.sdn import analyst as AN
from modules.sdn import closed_loop as CL
from modules.sdn import connections as C
from tests.sdn_fakes import Response
from tests.test_sdn_analyst import NET, OVS3_FLOWS, LabRyu, collect

FILE = "tests/fixtures/ai_cases/sdn_analyse/lab9_sitting.json"
CONNECTION = "ctl-1"
#: The recording's switches these cases plant flows on (datapath ids): Open vSwitch 3 and 4, and
#: the far edge switch, whose port 17 no link uses.
OVS3, OVS4, EDGE = 3, 4, 2843895626628
#: (the switch, its edge port, the port's name in the recording)
NEAR_PORT, FAR_PORT = (OVS3, 3, "eno4"), (EDGE, 17, "Ethernet17")
NEAR = {"mac": "0a:00:00:00:00:10", "ipv4": "198.51.100.10", "ipv6": "2001:db8::10"}
FAR = {"mac": "0a:00:00:00:00:20", "ipv4": "198.51.100.20", "ipv6": "2001:db8::20"}
#: The DHCP server the steering flows send requests to, beside `NEAR` on its port.
SERVER = {"mac": "0a:00:00:00:00:43", "ipv4": "198.51.100.43", "ipv6": "2001:db8::43"}
MISS = OVS3_FLOWS[0]
IPV4, IPV6, ICMP, ICMPV6, UDP = 2048, 34525, 1, 58, 17
ALL_SEVERITIES = ["none", "info", "low", "medium", "high", "critical"]
SITTING = "the Lab 9 sitting of 2026-11-10"


def _out(port):
    return [{"type": "OUTPUT", "port": port}]


def _to(host: dict, port: int, packets: int) -> list:
    """The two forwarding flows for *host*, IPv4 and IPv6, out *port*."""
    return [{"priority": 100, "cookie": 0, "match": {"eth_type": IPV4, "ipv4_dst": host["ipv4"]},
             "actions": _out(port), "packet_count": packets, "byte_count": packets * 100},
            {"priority": 100, "cookie": 0, "match": {"eth_type": IPV6, "ipv6_dst": host["ipv6"]},
             "actions": _out(port), "packet_count": packets // 3,
             "byte_count": packets // 3 * 100}]


def forwarding() -> dict:
    """Each switch's planted table with nothing wrong in it: `NEAR` and `FAR` reach each other
    along the recording's links, each switch with its table-miss flow."""
    return {OVS3: [MISS] + _to(FAR, 2, 900) + _to(NEAR, 3, 840),
            OVS4: [MISS] + _to(FAR, 1, 900) + _to(NEAR, 2, 840),
            EDGE: [MISS] + _to(FAR, 17, 900) + _to(NEAR, 18, 840)}


def misdirected(family: str) -> dict:
    """The planted flow: ICMP for `FAR` out Open vSwitch 4's port 3, away from it."""
    match = ({"eth_type": IPV4, "ip_proto": ICMP, "ipv4_dst": FAR["ipv4"]} if family == "ipv4"
             else {"eth_type": IPV6, "ip_proto": ICMPV6, "ipv6_dst": FAR["ipv6"]})
    return {"priority": 200, "cookie": 0, "match": match, "actions": _out(3),
            "packet_count": 240, "byte_count": 23520}


def dhcp(family: str) -> dict:
    """DHCP steering's flows on the far edge switch's edge port and along the path to the
    server: ``{"request", "reply_drop", "transit": {dpid: flow}}``."""
    if family == "ipv4":
        base = {"eth_type": IPV4, "ip_proto": UDP, "ipv4_dst": "255.255.255.255"}
        request = dict(base, in_port=FAR_PORT[1], eth_dst="ff:ff:ff:ff:ff:ff", udp_dst=67)
        steer = [{"type": "SET_FIELD", "field": "eth_dst", "value": SERVER["mac"]}]
        transit = dict(base, eth_dst=SERVER["mac"], udp_dst=67)
        drop = dict(base, in_port=FAR_PORT[1], udp_src=67, udp_dst=68)
    else:
        base = {"eth_type": IPV6, "ip_proto": UDP}
        request = dict(base, in_port=FAR_PORT[1], ipv6_dst="ff02::1:2", udp_dst=547)
        steer = []
        transit = dict(base, ipv6_dst="ff02::1:2", udp_dst=547)
        drop = dict(base, in_port=FAR_PORT[1], udp_src=547, udp_dst=546)

    def flow(match, actions, packets):
        return {"priority": 1000, "cookie": 0, "match": match, "actions": actions,
                "packet_count": packets, "byte_count": packets * 342}
    return {"request": flow(request, steer + _out(18), 12), "reply_drop": flow(drop, [], 0),
            "transit": {OVS4: flow(transit, _out(2), 12), OVS3: flow(transit, _out(3), 12)}}


class SittingRyu(LabRyu):
    """`LabRyu`, and the planted host table (Ryu 4.34's ``rest_topology`` shape), each host's
    port taken from the recording's own port description."""

    def _host(self, host: dict, at: tuple) -> dict:
        dpid, port_no, name = at
        desc = self.rec.answer("GET", f"/stats/portdesc/{dpid}")[str(dpid)]
        port = next(p for p in desc if p["port_no"] == port_no and p["name"] == name)
        return {"mac": host["mac"], "ipv4": [host["ipv4"]], "ipv6": [host["ipv6"]],
                "port": {"dpid": f"{dpid:016x}", "port_no": f"{port_no:08x}",
                         "hw_addr": port["hw_addr"], "name": name}}

    def request(self, method, url, **kwargs):
        if url.endswith("/v1.0/topology/hosts"):
            self.sent.append(dict(kwargs, method=method, url=url))
            return Response(200, json.dumps([self._host(NEAR, NEAR_PORT),
                                             self._host(SERVER, NEAR_PORT),
                                             self._host(FAR, FAR_PORT)]))
        return super().request(method, url, **kwargs)


def collection(flows: dict) -> dict:
    """The collection of the fabric with *flows* planted (`closed_loop.collect_threat_data` with
    its links, then the hosts, as the analyst's collection job reads them), through Mercury's
    real Ryu driver; as JSON keeps it."""
    session = SittingRyu(flows=flows)
    got, _session = collect(session, links=True)
    AN._read_hosts(NET, got, lambda net, name: C.driver_for(net, name, session=session))
    return json.loads(json.dumps(got, sort_keys=True, default=str))


def _ref(dpid: int, flow: dict) -> str:
    ref = CL.flow_ref(CONNECTION, dpid, flow)
    return ref if flow["actions"] else AN.drop_ref(ref)


def cases() -> list:
    """The four cases, each with its collection and its expectation. Needs the analyst tests'
    world (a network with the recorded controller's connection saved)."""
    out = []
    for family, words in (("ipv4", "ICMP"), ("ipv6", "ICMPv6")):
        planted = misdirected(family)
        flows = forwarding()
        flows[OVS4] = flows[OVS4] + [planted]
        out.append({
            "key": f"misdirected-icmp-{family}",
            "name": f"{words} for a host sent out a port that leads away from it ({family})",
            "about": (f"Modelled on {SITTING}, where the analyst without tools missed a planted "
                      f"misdirected flow. On Open vSwitch 4 a flow at priority 200 sends {words} "
                      f"for {FAR[family]} out port 3, the link to another switch; every other "
                      f"flow for that host leaves by port 1, the link to the switch it is on "
                      "(the fabric's own links, and the host table for the trace tool). To be "
                      "found by a kept finding citing the flow, at any severity above info."),
            "expect": {"threat_detected": True, "severity": ["low", "medium", "high", "critical"],
                       "cites_any": [_ref(OVS4, planted)]},
            "collection": collection(flows)})
    for family, words in (("ipv4", "DHCP"), ("ipv6", "DHCPv6")):
        steer = dhcp(family)
        flows = forwarding()
        flows[EDGE] = flows[EDGE] + [steer["request"], steer["reply_drop"]]
        for dpid, flow in steer["transit"].items():
            flows[dpid] = flows[dpid] + [flow]
        out.append({
            "key": f"dhcp-disjoint-{family}",
            "name": (f"A drop of {words} replies beside a forward of {words} requests: disjoint "
                     f"matches, no conflict ({family})"),
            "about": (f"Modelled on {SITTING}, where both techniques set a flow dropping DHCP "
                      "replies against a flow forwarding DHCP requests and reported a conflict. "
                      f"On the far edge switch's edge port, {words} requests from the port are "
                      f"forwarded toward the server and {words} replies arriving on it are "
                      "dropped (the trusted-port rule, modules/sdn/dhcp_steer.py's shapes); no "
                      "packet matches both, so neither shadows the other. Benign: no kept "
                      "finding above info may cite both flows together. Other findings (the "
                      "recording's own port down) are not judged here."),
            "expect": {"threat_detected": False, "severity": ALL_SEVERITIES,
                       "disjoint": [[_ref(EDGE, steer["reply_drop"]),
                                     _ref(EDGE, steer["request"])]]},
            "collection": collection(flows)})
    return out


def document() -> dict:
    from modules.ai import profiles

    return {
        "task": "sdn_analyse", "model": profiles.task("sdn_analyse")["model"],
        "network": "default", "path": "collection",
        "about": (f"The SDN analyst's cases modelled on {SITTING} (modules/sdn/b4_eval.py, the "
                  "role sitting): two planted misdirected flows (IPv4 and IPv6) to be found, and "
                  "two benign pairs of DHCP flows whose matches are disjoint (IPv4 and DHCPv6), "
                  "which no finding may set against each other. Built by "
                  "tests/sdn_sitting_cases.py from the analyst tests' fabric (the recorded "
                  "controller's switches, links and port descriptions; flow tables, counters "
                  "and hosts planted): each case's collection is what Mercury's collector "
                  "returned through its real Ryu driver, with nothing of the lab's hardware or "
                  "its data. Never blind: the expectations were written knowing what the "
                  "sitting got wrong. No model was called in building this set, and none is "
                  "recorded here; model names the task's pin its runs are judged on."),
        "cases": cases()}


def text() -> str:
    """The committed file's exact text."""
    return json.dumps(document(), indent=1, sort_keys=True) + "\n"
