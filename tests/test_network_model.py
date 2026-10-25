"""The network context model (PHASE8_PLAN 15.15; modules/network_model.py): a network compiled
from its inventory and committed intent, versioned by both, kept in memory, and the subgraph
around a subject (`context_for`) with the Topology reader's observed overlay.

On test_device_v2's lab (the list Lab, a real repository) with the nine REAL fleet configs
parsed by the real parsers and committed as intent (their interfaces, routing and platform:
what the model reads), an inventory naming each with a NetBox id, and the Topology reader's
value built by the real reader from the real captures (tests/test_topology_graph.py's
`_graph`: LLDP, the routing tables). r5 is cabled and retired (no intent here), as on the host.

- **The model:** links are the subnets two or more devices share, IPv4 and IPv6 alike; the OSPF
  adjacencies are exactly what the Neighbours tab's own per-device code (`neighbours.expected`)
  implies, a control computed by a different path; ids are NetBox's, stable over a rebuild;
  nothing but the topology class's fields is copied (a row's credentials, a NetBox description,
  an interface description never are).
- **context_for:** what a subject and its hops reach (the alerting router reaches the switch on
  its core segment at one hop: C1547's case), compact YAML with sorted keys and no anchors, the
  observed overlaid with its read time, and a read that cannot be used stated on every item.
- **The version:** asking again builds nothing; a golden committed alone builds nothing; a
  change to intent or to the inventory's fields rebuilds; a hit asks git once.
- **A read writes nothing:** the data folder is the same after a build and a subgraph.
- **Scale:** a 900-device fleet builds within a bound and a subgraph of it stays small; a
  segment of 900 is listed, not walked.
"""
import json
import os
import time

import pytest
import yaml

from modules import network_model as NM
from tests import test_topology_graph as TG
from tests.test_device_v2 import _store, _unstore, lab  # noqa: F401 (the fixture)

#: The Topology reader's read, and the clock a minute after it.
READ_AT = "2026-10-15T08:20:00Z"
NOW = 1792052460.0                      # 2026-10-15T08:21:00Z
HOSTS = ["r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4"]
#: A secret's shape planted in a NetBox description and an interface description.
PLANTED = "snmp-server community Pl4ntedModelSecret RO"


def _nb(host):
    return 100 + HOSTS.index(host)


def _inventory():
    return [{"hostname": h, "ip": f"192.0.2.{30 + i}", "_netbox_id": _nb(h),
             "role": "router" if h.startswith("r") else "switch", "_site": "site-a",
             "_platform": "cisco_iosxe" if h.startswith("r") else "cisco_ios",
             "device_type": "cisco_xe" if h.startswith("r") else "cisco_ios",
             "username": "nmas", "password": "gAAAAplantedEncryptedPassword",
             "secret": "gAAAAplantedEncryptedSecret", "description": PLANTED,
             "comments": PLANTED} for i, h in enumerate(HOSTS)]


def commit_fleet(repo, hosts=HOSTS, edit=None):
    """Commit the real configs' interfaces, routing and platform as each host's intent; an
    interface description carries the planted secret's shape. *edit* changes one before."""
    from modules.nsot import hostvars
    from tests.intent_fixture import commit_intent

    intents = TG._intents()
    os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
    for h in hosts:
        hv = {"hostname": h, "platform": intents[h]["platform"],
              "interfaces": intents[h]["interfaces"], "routing": intents[h]["routing"]}
        hv["interfaces"][0]["description"] = PLANTED
        if edit:
            edit(h, hv)
        with open(os.path.join(repo, "host_vars", f"{h}.yml"), "w", encoding="utf-8") as fh:
            fh.write(hostvars.to_yaml(hv))
    return commit_intent(repo)


def store_observed(at=READ_AT, graph=None):
    _store(NM.OBSERVED_READER, {"configured": True, "networks": {"Lab": graph or TG._graph()},
                                "read_at": at}, at=at)


@pytest.fixture
def net(lab, monkeypatch):  # noqa: F811
    inv = _inventory()
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in inv])
    commit_fleet(lab["repo"])
    store_observed()
    monkeypatch.setattr(NM, "_now", lambda: NOW)
    NM.forget()
    NM.BUILDS.clear()
    lab.update(inventory=inv)
    yield lab
    NM.forget()
    _unstore(NM.OBSERVED_READER)


def _model():
    m, err = NM.model_for("Lab")
    assert m is not None, err
    return m


def _dev(h):
    return f"dev:{_nb(h)}"


# ------------------------------------------------------------------------------- the model

class TestTheModel:
    def test_the_core_segment_is_one_link_v4_and_v6(self, net):
        m = _model()
        core = m["links"]["link:10.255.3.0/24"]
        assert {x["dev"] for x in core["members"]} == {_dev(h) for h in
                                                       ("r1", "r2", "r3", "r4", "s3", "s4")}
        six = m["links"]["link:2001:db8:3::/64"]
        assert {x["dev"] for x in six["members"]} == {x["dev"] for x in core["members"]}
        assert {"address": "2001:db8:3::11/64", "dev": _dev("r1"), "interface": "Gi2"} \
            in six["members"]

    def test_the_ospf_adjacencies_are_the_neighbours_tabs_own(self, net):
        """The control, by another path: `neighbours.expected`, one device at a time."""
        from modules import neighbours as N
        from modules.neighbours import committed_intents

        intents, _e = committed_intents(net["repo"])
        want = set()
        for h in intents:
            for e in N.expected(intents, h):
                if e["proto"] in ("ospf", "ospfv3") and e["managed"]:
                    want.add((e["proto"], frozenset((h, e["peer"])), e["network"]))
        names = {v: k for k, v in _model()["names"].items()}
        # An id ends with its second end and the subnet: adj:<proto>:<a>~<b>:<subnet>.
        got = {(a["proto"], frozenset(names[d] for d in a["between"]),
                a["id"].split(a["between"][1] + ":", 1)[1])
               for a in _model()["adjacencies"].values() if a["proto"] != "bgp"}
        assert len(want) >= 20 and got == want

    def test_bgp_to_a_peer_outside_management_is_named_by_its_address(self, net):
        bgp = [a for a in _model()["adjacencies"].values() if a["proto"] == "bgp"]
        outside = {d for a in bgp for d in a["between"] if d.startswith("ext:")}
        # r3's and r4's eBGP sessions to the retired r5, each over IPv4 and IPv6.
        assert outside == {"ext:198.51.100.1", "ext:2001:db8:51::2", "ext:198.51.100.3",
                           "ext:2001:db8:51:1::2"}
        assert all(a.get("outside_management") for a in bgp
                   if any(d.startswith("ext:") for d in a["between"]))

    def test_ids_are_netbox_ids_and_stable_over_a_rebuild(self, net):
        first = _model()
        NM.forget()
        again = _model()
        assert first["names"] == again["names"] == {h: _dev(h) for h in HOSTS}
        assert json.dumps(first["adjacencies"], sort_keys=True) == \
            json.dumps(again["adjacencies"], sort_keys=True)

    def test_a_device_with_no_netbox_id_takes_its_manifest_identity(self):
        rows = [{"hostname": "a1"}, {"hostname": "a2"}]
        manifest = {"devices": {"uid:6a333b63-a554-4cbc-9deb-c759252d0805": {"name": "a1"}}}
        ids = NM._ids(NM._rows(rows), manifest, ["a1", "a2"])
        assert ids == {"a1": "dev:u6a333b63", "a2": "dev:@a2"}

    def test_only_the_topology_classs_fields_are_copied(self, net):
        text = json.dumps(_model())
        for planted in ("Pl4ntedModelSecret", "gAAAAplanted", "description", "comments",
                        "community", "username"):
            assert planted not in text, planted
        node = _model()["nodes"][_dev("r1")]
        assert set(node) <= {"id", "name", "role", "site", "platform", "address", "interfaces",
                             "ospf", "ospfv3", "bgp", "intent", "inventory"}
        keys = {k for i in node["interfaces"] for k in i}
        assert keys <= {"name", "addresses", "vrf", "mode", "vlan", "trunk_vlans", "shutdown",
                        "ospf_area", "ospfv3_area"}

    def test_a_segment_whose_members_share_an_address_is_not_walked(self, net):
        """Every router's management interface holds the same address (each a separate
        segment, or a conflict): drawn, and never a way from one router to another."""
        mgmt = [l for l in _model()["links"].values() if l.get("vrf")]
        assert mgmt and all(l["expanded"] is False
                            and "an address another member holds" in l["note"] for l in mgmt)
        shared = {l["id"] for l in mgmt}
        assert not any(v in shared for e in _model()["edges"].values() for v in e.values())


# ------------------------------------------------------------------------------ context_for

def _ctx(subject="r1", hops=1):
    got = NM.context_for("Lab", subject, hops=hops)
    assert got["ok"], got
    return got, yaml.safe_load(got["yaml"])


class TestTheSubgraph:
    def test_one_hop_from_the_router_reaches_the_switch_on_its_core_segment(self, net):
        """C1547's case: an OSPF drop on a router whose core segment is carried by a starved
        switch. One hop from the router reaches the switch, by the segment and by the cable."""
        got, doc = _ctx("r1", 1)
        reached = {d: v["via"] for d, v in got["reached"].items()}
        assert reached[_dev("s3")] == "link:10.255.3.0/24"
        assert set(reached) == {_dev(h) for h in ("r1", "r2", "r3", "r4", "s1", "s3", "s4")}
        assert doc["devices"][_dev("s3")]["hop"] == 1
        assert doc["devices"][_dev("s3")]["name"] == "s3"
        assert any(_dev("s3") in c and "Gi1/0" in c for c in doc["cables"])
        assert ("hop", 2) not in {(k, v["hop"]) for k, v in doc["devices"].items()}

    def test_hops_bound_what_is_reached(self, net):
        zero, _d = _ctx("r1", 0)
        assert list(zero["reached"]) == [_dev("r1")]
        two, _d = _ctx("r1", 2)
        assert two["reached"][_dev("s2")]["hop"] == 2
        assert NM.reach("Lab", "r1", 1)[0] == (0, _dev("r1"), "r1", "")

    def test_the_subject_by_netbox_id_by_its_id_or_by_a_link(self, net):
        assert _ctx(str(_nb("r1")))[1]["subject"] == _dev("r1")
        assert _ctx(_dev("r1"))[1]["subject"] == _dev("r1")
        got, doc = _ctx("link:10.255.2.14/31", 0)
        assert set(got["reached"]) == {_dev("r3"), _dev("r4")}
        assert NM.context_for("Lab", "nothing-here")["ok"] is False

    def test_only_the_subject_carries_detail_at_one_hop(self, net):
        _g, doc = _ctx("r1", 1)
        assert "interfaces" in doc["devices"][_dev("r1")]
        assert doc["devices"][_dev("s3")]["detail"] == "beyond the hops asked: identity only"
        assert "interfaces" not in doc["devices"][_dev("s3")]
        # The subject's own adjacencies only: r2 to r3 is not the subject's.
        assert not any(set(a["between"]) == {_dev("r2"), _dev("r3")}
                       for a in doc["adjacencies"].values())

    def test_the_yaml_is_compact_sorted_and_holds_every_id(self, net):
        got, doc = _ctx("r1", 1)
        assert "&id" not in got["yaml"] and "*id" not in got["yaml"]
        assert list(doc) == sorted(doc)
        for i in got["ids"]:
            assert i in got["yaml"], i
        assert set(got["ids"]) == set(doc["devices"]) | set(doc["links"]) | \
            set(doc["adjacencies"]) | set(doc["cables"])

    def test_observed_is_overlaid_with_its_read_time(self, net):
        _g, doc = _ctx("r1", 1)
        aid = NM._adj_id("ospf", _dev("r1"), _dev("r3"), "10.255.3.0/24")
        a = doc["adjacencies"][aid]
        assert a["expected"] is True
        assert a["observed"] == {"state": "up", "words": "full", "read_at": READ_AT}
        cable = next(c for k, c in doc["cables"].items() if _dev("s1") in k)
        assert cable["reported"] == "by one end, the other polled and silent"
        assert doc["observed"]["read_at"] == READ_AT and doc["observed"]["state"] == "read"

    def test_a_down_adjacency_is_observed_down(self, net):
        graph = TG._graph()
        for l in graph["layers"]["ospf"]:
            if {l["a"], l["b"]} == {"r1", "r3"}:
                l.update(state="down", words="init")
        store_observed(graph=graph)
        _g, doc = _ctx("r1", 1)
        aid = NM._adj_id("ospf", _dev("r1"), _dev("r3"), "10.255.3.0/24")
        assert doc["adjacencies"][aid]["observed"]["state"] == "down"

    @pytest.mark.parametrize("case,words", [
        ("absent", "could not read (the Topology reader has not read yet)"),
        ("stale", "could not read (the Topology reader's last read, at 2026-10-15T07:00:00Z, "
                  "is older than its promise of 1500 s, so it is not current)"),
        ("other", "could not read (the Topology reader's last read holds nothing for Lab)"),
    ])
    def test_a_read_that_cannot_be_used_is_said_on_every_item(self, net, case, words):
        if case == "absent":
            _unstore(NM.OBSERVED_READER)
        elif case == "stale":
            store_observed(at="2026-10-15T07:00:00Z")
        else:
            _store(NM.OBSERVED_READER, {"configured": True, "networks": {}}, at=READ_AT)
        _g, doc = _ctx("r1", 1)
        assert doc["observed"]["state"] == words
        assert doc["adjacencies"] and all(a["observed"] == words
                                          for a in doc["adjacencies"].values())
        assert doc["cables"] == words

    def test_the_summary_is_the_same_bytes_and_holds_no_time(self, net):
        import re
        a, _d = _ctx("r1", 1)
        store_observed(at="2026-10-15T08:21:00Z")
        b, _d = _ctx("s3", 1)
        assert a["summary"] == b["summary"]
        assert not re.search(r"\d{4}-\d\d-\d\dT\d\d:\d\d", a["summary"])
        assert yaml.safe_load(a["summary"])["devices"] == len(HOSTS)


# ------------------------------------------------------------------------------ the version

class TestTheVersion:
    def test_asking_again_builds_nothing_and_asks_git_once(self, net, monkeypatch):
        from modules.nsot import repo as R
        _ctx("r1")
        assert NM.BUILDS["Lab"] == 1
        calls = []
        real = R.run_git
        monkeypatch.setattr(R, "run_git", lambda *a, **k: calls.append(a[1:3]) or real(*a, **k))
        _ctx("s3")
        assert NM.BUILDS["Lab"] == 1
        assert calls == [("ls-tree", "HEAD")], calls

    def test_a_golden_committed_alone_rebuilds_nothing(self, net):
        from modules.nsot.repo import GoldenItem, save_golden
        first = _ctx("r1")[0]["version"]
        body = open(net["repo"] + "/golden/r3.cfg", encoding="utf-8").read()
        assert save_golden("Lab", [GoldenItem("r3", body + "!\n", "10.255.1.13",
                                              platform="cisco_iosxe")],
                           source="capture", actor="operator@example.com",
                           baseline=False)["ok"]
        assert _ctx("r1")[0]["version"] == first and NM.BUILDS["Lab"] == 1

    def test_an_intent_change_rebuilds(self, net):
        first = _ctx("r1")[0]["version"]

        def shut(h, hv):
            if h == "r1":
                hv["interfaces"][2]["shutdown"] = True
        commit_fleet(net["repo"], edit=shut)
        got, doc = _ctx("r1")
        assert got["version"] != first and NM.BUILDS["Lab"] == 2
        assert any(i.get("shutdown") for i in doc["devices"][_dev("r1")]["interfaces"])

    def test_an_inventory_change_rebuilds_and_a_refresh_that_found_nothing_new_does_not(
            self, net):
        first = _ctx("r1")[0]["version"]
        for row in net["inventory"]:
            row["password"] = "gAAAAanotherEncryptionOfTheSamePassword"
        assert _ctx("r1")[0]["version"] == first and NM.BUILDS["Lab"] == 1
        net["inventory"][0]["role"] = "switch"
        assert _ctx("r1")[0]["version"] != first and NM.BUILDS["Lab"] == 2


def test_a_read_writes_nothing(net):
    """The model is kept in memory: a build and a subgraph leave the data folder as it was."""
    from modules import config

    def tree():
        out = {}
        for root in (config.DATA_DIR, os.path.dirname(net["repo"])):
            for d, _s, files in os.walk(root):
                for f in files:
                    p = os.path.join(d, f)
                    st = os.stat(p)
                    out[p] = (st.st_size, st.st_mtime_ns)
        return out

    NM.forget()
    before = tree()
    _ctx("r1", 2)
    assert tree() == before


# ------------------------------------------------------------------------------- scale

#: Measured where the test runs, CI's runner (C1741; run #1177, 2026-10-25, browser1 shard
#: under load): a 900-device build, the median of five, 0.569 s (all: 0.381 to 0.817); a
#: one-hop subgraph of it with the model kept, the median of seven, 0.0142 s (all: 0.0084 to
#: 0.0177). The first bounds (0.4 s and 0.01 s) came from the laptop's 0.145 s and 0.0037 s,
#: so the runner, the slower machine, refused them. Each bound is about 2.5x the runner's
#: median, and each test takes a median (C463: one sample on a shared runner measures it).
BUILD_BOUND_S = 1.4
CONTEXT_BOUND_S = 0.036


def _median(fn, n):
    times = []
    for _ in range(n):
        t = time.perf_counter()
        out = fn()
        times.append(time.perf_counter() - t)
    return sorted(times)[n // 2], times, out


def scale_fleet(routers=300, switches_per=2):
    """A fleet of ``routers * (1 + switches_per)`` devices, IPv6 throughout (2001:db8::/32): a
    ring of routers, each with its switches on a LAN, OSPFv3 on every link, and one management
    segment every device shares (larger than MAX_SEGMENT)."""
    intents, inventory = {}, []
    n = 0
    for i in range(routers):
        r = f"r{i}"
        ifaces = [{"name": "GigabitEthernet1", "ipv6": [f"2001:db8:{i:x}::1/127"],
                   "ospfv3": ["1 area 0"]},
                  {"name": "GigabitEthernet2", "ipv6": [f"2001:db8:{(i - 1) % routers:x}::/127"],
                   "ospfv3": ["1 area 0"]},
                  {"name": "GigabitEthernet3", "ipv6": [f"2001:db8:a{i:x}::1/64"],
                   "ospfv3": ["1 area 0"]},
                  {"name": "GigabitEthernet9", "vrf": "mgmt",
                   "ipv6": [f"2001:db8:ffff::{n + 1:x}/64"]}]
        intents[r] = {"hostname": r, "interfaces": ifaces,
                      "routing": {"ospfv3": [{"raw": [f"router-id 192.0.2.{i % 250 + 1}"]}]}}
        inventory.append({"hostname": r, "_netbox_id": 1000 + n, "role": "router",
                          "_site": f"site-{i // 30}"})
        n += 1
        for j in range(switches_per):
            s = f"s{i}-{j}"
            intents[s] = {"hostname": s, "interfaces": [
                {"name": "Vlan10", "ipv6": [f"2001:db8:a{i:x}::{j + 2:x}/64"],
                 "ospfv3": ["1 area 0"]},
                {"name": "GigabitEthernet0/9", "vrf": "mgmt",
                 "ipv6": [f"2001:db8:ffff::{n + 1:x}/64"]}],
                "routing": {"ospfv3": [{"raw": []}]}}
            inventory.append({"hostname": s, "_netbox_id": 1000 + n, "role": "switch",
                              "_site": f"site-{i // 30}"})
            n += 1
    return intents, inventory


class TestScale:
    def test_a_fleet_of_900_builds_within_its_bound(self):
        intents, inventory = scale_fleet()
        assert len(intents) == 900
        took, times, m = _median(lambda: NM.build("Big", inventory, intents, {},
                                                  version={"key": "nm-scale"}), 5)
        assert took < BUILD_BOUND_S, (f"a 900-device build took {took:.3f} s (median of 5; "
                                      f"all: {', '.join(f'{t:.3f}' for t in times)})")
        assert m["counts"]["devices"] == 900
        assert m["counts"]["adjacencies"]["ospfv3"] == 300 + 300 * 3

    def test_a_subgraph_of_900_is_small_and_quick(self, monkeypatch):
        intents, inventory = scale_fleet()
        m = NM.build("Big", inventory, intents, {}, version={"key": "nm-scale"})
        monkeypatch.setattr(NM, "model_for", lambda net: (m, ""))
        monkeypatch.setattr(NM, "observed", lambda net, model, now=None: {
            "state": "could not read", "why": "planted", "read_at": "", "routing": {},
            "cables": {}, "source": "planted"})
        took, times, got = _median(lambda: NM.context_for("Big", "r7", hops=1), 7)
        assert took < CONTEXT_BOUND_S, (f"a subgraph of 900 took {took:.4f} s (median of 7; "
                                        f"all: {', '.join(f'{t:.4f}' for t in times)})")
        # r7, its two ring neighbours and its two switches; the management segment of 900 is
        # listed with the members reached and never walked.
        assert len(got["reached"]) == 5, got["reached"]
        doc = yaml.safe_load(got["yaml"])
        mgmt = doc["links"]["link:mgmt/2001:db8:ffff::/64"]
        assert mgmt["members_total"] == 900 and len(mgmt["members"]) == 5
        assert "not walked through" in mgmt["note"]
        assert len(got["yaml"]) < 12_000
