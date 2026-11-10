"""DHCP steering's harness proof (Lab 9 Objective 6, the REST path; C2904): the flows
`modules/sdn/dhcp_steer.py` compiles for the harness's two bridges, rendered by Mercury's Ryu
driver, sent through the driver's one send path to real Ryu 4.34's ofctl_rest, then traced
through real Open vSwitch by `ovs-appctl ofproto/trace` (README.md beside this file says when
and how it was run). Two modes:

    python dhcp_steer_proof.py render <requests.json>         on the laptop (Mercury's Python)
    python dhcp_steer_proof.py apply <requests.json> <out.json>
                                                              in the harness's runner, inside
                                                              the internal network

**The harness's NSOT export** (`harness_export`): the bridges of tests/containers/ovs/
bridges.conf as two OpenFlow switches (``br3``, datapath id 3; ``br4``, datapath id 4) cabled
port 2 to port 2 (the patch); an end host ``h1`` on br3 port 1; the DHCP server ``rtr`` (MAC
00:00:5e:00:53:01, 198.51.100.1/24, a NetBox Service ``dhcp`` UDP 67) on br4 port 1. The
addresses are documentation addresses. Priorities are `flow_ops.response_priority`'s over the
harness's empty tables (its floor, 300); cookies are Mercury's, fixed (ids 1 to 4) so the
recording is stable. `tests/test_dhcp_steer_harness.py` holds the recording to what the code
renders now.
"""

import json
import os
import sys

SERVER_MAC = "00:00:5e:00:53:01"


def _iface(iid, device, name, port=None, mac="", addresses=(), of=False):
    out = {"id": iid, "device": device, "name": name, "type": {"value": "virtual"},
           "enabled": True, "mgmt_only": False, "mode": None, "untagged_vlan": None,
           "tagged_vlans": [], "tags": [{"slug": "openflow"}] if of else [],
           "ip_addresses": [{"address": a} for a in addresses],
           "custom_fields": {"openflow_port": port} if port is not None else {}}
    if mac:
        out["primary_mac_address"] = {"mac_address": mac}
    return out


def _cable(a, b):
    return {"a_terminations": [{"object": {"device": {"name": a[0]}, "name": a[1]}}],
            "b_terminations": [{"object": {"device": {"name": b[0]}, "name": b[1]}}],
            "status": {"value": "connected"}, "label": ""}


def harness_export() -> dict:
    """The harness as an NSOT export document (`nsot.export.document`'s, parsed)."""
    from modules.nsot import export as X

    site = {"id": 1, "slug": "harness"}

    def dev(did, name, role, dpid=None, primary=None, tags=()):
        return {"id": did, "name": name, "status": {"value": "active"}, "role": {"slug": role},
                "platform": None, "site": site, "device_type": {"slug": "harness"},
                "primary_ip4": {"address": primary} if primary else None, "primary_ip6": None,
                "oob_ip": None, "tags": [{"slug": t} for t in tags],
                "custom_fields": ({"openflow_datapath_id": f"{dpid:016x}"} if dpid else {}),
                "config_context": {}}

    br3, br4, rtr, h1 = ({"id": 3, "name": "br3"}, {"id": 4, "name": "br4"},
                         {"id": 7, "name": "rtr"}, {"id": 9, "name": "h1"})
    records = {
        "devices": [dev(3, "br3", "openflow-switch", 3), dev(4, "br4", "openflow-switch", 4),
                    dev(7, "rtr", "router")],
        "hosts": [dev(9, "h1", "end-host", tags=(X.HOST_TAG,))],
        "interfaces": [
            _iface(31, br3, "s3-eth1", 1, of=True), _iface(32, br3, "s3-eth2", 2, of=True),
            _iface(41, br4, "s4-eth1", 1, of=True), _iface(42, br4, "s4-eth2", 2, of=True),
            _iface(71, rtr, "Gi0/1", mac=SERVER_MAC, addresses=("198.51.100.1/24",)),
            _iface(91, h1, "eth0", mac="aa:bb:cc:00:00:01", addresses=("198.51.100.101/24",))],
        "services": [{"device": rtr, "name": "dhcp", "protocol": {"value": "udp"},
                      "ports": [67], "ipaddresses": [{"address": "198.51.100.1/24"}],
                      "tags": []}],
        "cables": [_cable(("br3", "s3-eth2"), ("br4", "s4-eth2")),
                   _cable(("h1", "eth0"), ("br3", "s3-eth1")),
                   _cable(("rtr", "Gi0/1"), ("br4", "s4-eth1"))],
        "vlans": [], "prefixes": []}
    return X.parse(X.document("harness", "4.2.6", records))


def rendered() -> list:
    """Each compiled flow rendered by Mercury's Ryu driver, in the order the confirm sends
    them (the server's switch first): ``[{"dpid", "role", "request"}]``."""
    from modules.sdn import dhcp_steer as D, flow_intent as F, flow_ops as O
    from modules.sdn.drivers.base import Connection
    from modules.sdn.drivers.ryu import RyuDriver

    c = D.compile(harness_export())
    if not c["ok"]:
        raise SystemExit(c["error"])
    drv = RyuDriver(Connection("http://harness"))
    out, n = [], 0
    for dpid in c["order"]:
        for flow in c["switches"][dpid]["flows"]:
            n += 1
            spec = {"table_id": 0, "priority": O.response_priority([], match=flow["match"]),
                    "cookie": F.mercury_cookie(n), "match": flow["match"],
                    "actions": flow["actions"], "idle_timeout": 0, "hard_timeout": 0}
            got = drv.render_add_flow(dpid, spec)
            out.append({"dpid": dpid, "role": flow["role"],
                        "request": {k: got[k] for k in ("method", "path", "body")}})
    return out


def apply(requests: list) -> dict:
    """Each request through the driver's one send path, then each switch's table read back."""
    from modules.sdn.drivers.base import Connection
    from modules.sdn.drivers.ryu import RyuDriver

    drv = RyuDriver(Connection(os.environ["NMAS_HARNESS_REST"], timeout=5.0))
    answers = [dict(r, answer=drv.apply(dict(r["request"], ok=True))) for r in requests]
    tables = {}
    for dpid in sorted({r["dpid"] for r in requests}):
        got = drv.flows(dpid)
        tables[str(dpid)] = got.get("flows") if got.get("ok") else got.get("error")
    return {"sent": answers, "tables": tables}


def main(argv) -> int:
    if argv[1:2] == ["render"]:
        with open(argv[2], "w", encoding="utf-8") as fh:
            json.dump(rendered(), fh, indent=2, sort_keys=True)
        return 0
    if argv[1:2] == ["apply"]:
        with open(argv[2], encoding="utf-8") as fh:
            requests = json.load(fh)
        with open(argv[3], "w", encoding="utf-8") as fh:
            json.dump(apply(requests), fh, indent=2, sort_keys=True, default=str)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
