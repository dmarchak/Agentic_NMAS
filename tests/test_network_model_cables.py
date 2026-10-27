"""NetBox's cables as a source of the network model's links (C1863; modules/network_model.py).

On tests/test_network_model.py's lab (the list Lab, the nine REAL fleet configs parsed and
committed as intent, r1 to r4 and s1 to s4), its inventory naming each device by the NetBox id
the lab's NetBox gives it, and the lab NetBox's REAL cables (tests/fixtures/netbox/cables.json:
dcim/cables read through Mercury's NetBox integration client on the host, 2026-10-27; 17
cables, among them r5 to r8 and s5, which are not in this model, a console cable and a cable
with no ends). NetBox is answered by a stand-in session under the real
`NetBoxIntegration._get`, page by page, so nothing leaves the test.
"""
import hashlib
import json
import os

import pytest
import yaml

from modules import network_model as NM
from modules.integrations.netbox import NetBoxIntegration
from tests import test_network_model as TM
from tests.test_device_v2 import _unstore, lab  # noqa: F401 (the fixture)

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "netbox",
                       "cables.json")
BASE = "http://netbox.example.test:8000"


def _capture() -> dict:
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _netbox_ids() -> dict:
    """Each device's NetBox id, read from the capture's own terminations (an independent path
    from the model's)."""
    out = {}
    for c in _capture()["results"]:
        for t in c["a_terminations"] + c["b_terminations"]:
            dev = (t.get("object") or {}).get("device")
            if dev:
                out[dev["name"]] = dev["id"]
    return out


class _Response:
    def __init__(self, status, doc):
        self.status_code, self._doc, self.headers, self.text = status, doc, {}, ""

    def json(self):
        return self._doc


class _NetBox:
    """NetBox's dcim/cables over the capture, in pages of the limit asked; counts its GETs."""

    def __init__(self, results=None, status=200):
        self.results = list(_capture()["results"] if results is None else results)
        self.status, self.gets = status, []

    def get(self, url, params=None, timeout=None):
        from urllib.parse import parse_qs, urlparse
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        q.update({k: str(v) for k, v in (params or {}).items()})
        self.gets.append((urlparse(url).path, dict(q)))
        if self.status != 200:
            return _Response(self.status, {"detail": "a stand-in refusal"})
        limit, offset = int(q.get("limit", 50)), int(q.get("offset", 0))
        page = self.results[offset:offset + limit]
        nxt = (f"{BASE}/api/dcim/cables/?limit={limit}&offset={offset + limit}"
               if offset + limit < len(self.results) else None)
        return _Response(200, {"count": len(self.results), "next": nxt, "previous": None,
                               "results": page})


@pytest.fixture
def cabled(lab, monkeypatch):  # noqa: F811
    """test_network_model's lab, its inventory naming each device by its real NetBox id, the
    list Lab on NetBox (its source file, written by the real `source_config.save`), and NetBox
    answered by `_NetBox`."""
    from modules.inventory import source_config

    ids = _netbox_ids()
    inv = TM._inventory()
    for row in inv:
        row["_netbox_id"] = ids[row["hostname"]]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in inv])
    TM.commit_fleet(lab["repo"])
    TM.store_observed()
    monkeypatch.setattr(NM, "_now", lambda: TM.NOW)
    # The lab's list folder, where a read finds the source file as a write put it.
    monkeypatch.setattr("modules.config.list_data_path",
                        lambda name: os.path.dirname(lab["repo"]))
    assert source_config.save("Lab", {"source": "netbox"})["source"] == "netbox"
    nb = _NetBox()

    class Client(NetBoxIntegration):
        url = BASE

        def is_configured(self):
            return True

        def session(self):
            return nb

    clients = []
    monkeypatch.setattr("modules.integrations.get_integration",
                        lambda name, list_name="": clients.append(list_name) or Client(
                            list_name=list_name))
    clock = {"t": 1000.0}
    monkeypatch.setattr(NM, "_clock", lambda: clock["t"])
    NM.forget()
    NM.BUILDS.clear()
    lab.update(inventory=inv, netbox=nb, ids=ids, clock=clock, clients=clients)
    yield lab
    NM.forget()
    _unstore(NM.OBSERVED_READER)


def _model():
    m, err = NM.model_for("Lab")
    assert m is not None, err
    return m


def _dev(lab, host):
    return f"dev:{lab['ids'][host]}"


def _cable(cid):
    return next(c for c in _capture()["results"] if c["id"] == cid)


def _ends(cid):
    c = _cable(cid)
    return [(t["object"]["device"]["name"], t["object"]["name"])
            for t in c["a_terminations"] + c["b_terminations"]]


class TestTheLinks:
    def test_a_cable_joins_the_intent_subnet_it_carries_v4_and_v6(self, cabled):
        """Cable 3 is r1's GigabitEthernet2 to s3's GigabitEthernet1/0: r1's Gi2 is on the
        core segment in both families, and s3 is a member of it, so both of the segment's
        links say they came from intent and NetBox, naming the cable."""
        assert _ends(3) == [("s3", "GigabitEthernet1/0"), ("r1", "GigabitEthernet2")]
        m = _model()
        for lid in ("link:10.255.3.0/24", "link:2001:db8:3::/64"):
            link = m["links"][lid]
            assert link["source"] == "both", (lid, link)
            assert 3 in link["netbox_cables"]
            assert {_dev(cabled, "r1"), _dev(cabled, "s3")} <= {x["dev"] for x in
                                                                 link["members"]}
        assert "link:netbox-cable:3" not in m["links"], "joined: never a link of its own too"

    def test_a_cable_no_intent_subnet_joins_is_a_link_of_its_own(self, cabled):
        """Cable 1, s1's Gi0/3 to s2's Gi0/3 (a trunk: the switches share subnets only on
        their VLAN interfaces), is a link of its own."""
        assert _ends(1) == [("s1", "GigabitEthernet0/3"), ("s2", "GigabitEthernet0/3")]
        link = _model()["links"]["link:netbox-cable:1"]
        assert link == {"id": "link:netbox-cable:1", "source": "netbox_cable",
                        "netbox_cable": 1,
                        "members": sorted([{"dev": _dev(cabled, "s1"), "interface": "Gi0/3"},
                                           {"dev": _dev(cabled, "s2"), "interface": "Gi0/3"}],
                                          key=lambda x: (x["dev"], x["interface"]))}

    def test_a_device_with_no_intent_is_reached_only_through_its_cables(self, cabled):
        """r5 is in NetBox's inventory with nothing committed (retired here, as on the host):
        intent gives it no link, and its two cables (r3's Gi2, r4's Gi2) make it one hop from
        each. Control: the same network read as a local CSV reaches no r5."""
        assert _ends(9) == [("r3", "GigabitEthernet2"), ("r5", "GigabitEthernet2")]
        assert _ends(11) == [("r4", "GigabitEthernet2"), ("r5", "GigabitEthernet3")]
        cabled["inventory"].append({"hostname": "r5", "ip": "192.0.2.39",
                                    "_netbox_id": cabled["ids"]["r5"], "role": "router"})
        NM.forget()
        m = _model()
        r5 = _dev(cabled, "r5")
        assert m["nodes"][r5]["intent"] == "none committed: nothing is implied"
        assert m["links"]["link:netbox-cable:9"]["source"] == "netbox_cable"
        assert m["edges"][r5] == {_dev(cabled, "r3"): "link:netbox-cable:9",
                                  _dev(cabled, "r4"): "link:netbox-cable:11"}
        reached = NM.context_for("Lab", "r3", hops=1)["reached"]
        assert reached[r5] == {"hop": 1, "via": "link:netbox-cable:9"}
        from modules.inventory import source_config
        source_config.save("Lab", {"source": "local"})
        NM.forget()
        assert r5 not in NM.context_for("Lab", "r3", hops=3)["reached"]

    def test_every_link_says_its_source(self, cabled):
        m = _model()
        assert {ln["source"] for ln in m["links"].values()} <= set(NM.LINK_SOURCES)
        by = m["counts"]["links_by_source"]
        assert sum(by.values()) == len(m["links"]) and by["both"] and by["netbox_cable"]
        assert all(ln["source"] == "intent" for lid, ln in m["links"].items()
                   if not ln.get("netbox_cables") and not lid.startswith("link:netbox-cable:"))

    def test_a_cable_whose_ends_the_model_does_not_know_is_counted_not_drawn(self, cabled):
        """Counted by an independent path over the capture: a cable with a side that is not
        one interface (the console cable, the cable with no ends), and one with an end on a
        device not in this model (r5 to r8, s5)."""
        known = set(TM.HOSTS)
        not_two, unknown, drawable = 0, 0, 0
        for c in _capture()["results"]:
            a, b = c["a_terminations"], c["b_terminations"]
            if len(a) != 1 or len(b) != 1 or any(
                    t["object_type"] != "dcim.interface" for t in a + b):
                not_two += 1
            elif {t["object"]["device"]["name"] for t in a + b} - known:
                unknown += 1
            else:
                drawable += 1
        assert not_two == 2 and unknown and drawable, (not_two, unknown, drawable)
        said = _model()["netbox_cables"]
        assert said["state"] == "read" and said["count"] == 17
        assert said["not_drawn"] == {"not_two_interfaces": not_two, "unknown_device": unknown}
        assert said["drawn"] == drawable == said["joined"] + said["own"]
        drawn = {x for ln in _model()["links"].values() for x in
                 ln.get("netbox_cables", []) + [ln.get("netbox_cable")] if x}
        for c in _capture()["results"]:
            names = {(t.get("object") or {}).get("device", {}).get("name")
                     for t in c["a_terminations"] + c["b_terminations"]
                     if (t.get("object") or {}).get("device")}
            if names - known:
                assert c["id"] not in drawn, c["id"]

    def test_an_end_is_known_by_its_netbox_id_never_its_name(self, cabled):
        """A device NetBox names r1 under another id is not this model's r1: by name, cable 7
        (r1 to s1) would be drawn; by id it is counted."""
        moved = json.loads(json.dumps(_capture()["results"]))
        for c in moved:
            for t in c["a_terminations"] + c["b_terminations"]:
                dev = (t.get("object") or {}).get("device")
                if dev and dev["name"] == "r1":
                    dev["id"] = 999
        cabled["netbox"].results = moved
        NM.forget()
        m = _model()
        drawn = {x for ln in m["links"].values() for x in
                 ln.get("netbox_cables", []) + [ln.get("netbox_cable")] if x}
        assert 7 not in drawn and 3 not in drawn
        assert m["netbox_cables"]["not_drawn"]["unknown_device"] > \
            _unknown_with(_capture()["results"])

    def test_a_cables_label_is_never_carried(self, cabled):
        """A label is NetBox free text: one planted with a secret's shape is in no link and in
        nothing a subgraph sends."""
        planted = json.loads(json.dumps(_capture()["results"]))
        for c in planted:
            c["label"] = TM.PLANTED
        cabled["netbox"].results = planted
        NM.forget()
        got = NM.context_for("Lab", "r1", hops=2)
        assert got["ok"] and TM.PLANTED not in got["yaml"]
        assert TM.PLANTED not in json.dumps(_model())


def _unknown_with(results):
    known = set(TM.HOSTS)
    n = 0
    for c in results:
        a, b = c["a_terminations"], c["b_terminations"]
        if len(a) == 1 and len(b) == 1 and all(t["object_type"] == "dcim.interface"
                                               for t in a + b):
            if {t["object"]["device"]["name"] for t in a + b} - known:
                n += 1
    return n


class TestTheSubgraph:
    def test_r1s_subgraph_names_each_links_source_and_the_read(self, cabled):
        got = NM.context_for("Lab", "r1", hops=1)
        doc = yaml.safe_load(got["yaml"])
        core = doc["links"]["link:10.255.3.0/24"]
        # The four router-to-core-switch cables, each a router's port on the segment.
        assert [_ends(c) for c in (3, 4, 5, 6)] == [
            [("s3", "GigabitEthernet1/0"), ("r1", "GigabitEthernet2")],
            [("s3", "GigabitEthernet0/2"), ("r3", "GigabitEthernet3")],
            [("s4", "GigabitEthernet1/0"), ("r2", "GigabitEthernet2")],
            [("s4", "GigabitEthernet0/2"), ("r4", "GigabitEthernet3")]]
        assert core["source"] == "both" and core["netbox_cables"] == [3, 4, 5, 6]
        assert doc["links"]["link:2001:db8:3::/64"]["source"] == "both"
        said = doc["netbox_cables"]
        assert said["cables"] == 17 and said["read_at"]
        assert {x["why"] for x in said["not_drawn"]} == {
            NM.NOT_DRAWN_WORDS["not_two_interfaces"], NM.NOT_DRAWN_WORDS["unknown_device"]}
        assert set(got["ids"]) >= set(doc["links"])

    def test_a_local_csv_network_reads_no_cables_and_says_so(self, cabled):
        from modules.inventory import source_config
        assert source_config.save("Lab", {"source": "local"})["source"] == "local"
        NM.forget()
        got = NM.context_for("Lab", "r1", hops=1)
        doc = yaml.safe_load(got["yaml"])
        assert cabled["netbox"].gets == [] and cabled["clients"] == []
        assert "local CSV, which holds no cables" in doc["netbox_cables"]
        assert {ln["source"] for ln in doc["links"].values()} == {"intent"}
        m = _model()
        assert m["version"]["cables"] == "none"
        # The key a network with no cables had before cables were a source, computed here.
        v = m["version"]
        assert v["key"] == "nm-" + hashlib.sha256(
            f"{v['intent']} {v['manifest']} {v['inventory']}".encode()).hexdigest()[:12]


class TestTheRead:
    def test_one_read_per_refresh_interval_and_the_key_moves_with_the_cables(self, cabled):
        nb, clock = cabled["netbox"], cabled["clock"]
        first = _model()["version"]["key"]
        assert len(nb.gets) == 1 and NM.BUILDS["Lab"] == 1
        NM.context_for("Lab", "r1", hops=1)
        _model()
        assert len(nb.gets) == 1 and NM.BUILDS["Lab"] == 1, "asked again within the interval"
        clock["t"] += 301
        assert _model()["version"]["key"] == first and len(nb.gets) == 2
        assert NM.BUILDS["Lab"] == 1, "the same cables read again rebuild nothing"
        nb.results = [c for c in nb.results if c["id"] != 3]
        clock["t"] += 301
        m = _model()
        assert m["version"]["key"] != first and NM.BUILDS["Lab"] == 2
        assert m["links"]["link:10.255.3.0/24"]["netbox_cables"] == [4, 5, 6]

    def test_pages_are_followed_up_to_the_bound_and_a_truncated_read_says_so(
            self, cabled, monkeypatch):
        monkeypatch.setattr(NM, "CABLE_PAGE", 5)
        got = NM.read_cables("Lab")
        assert got["state"] == "read" and len(got["cables"]) == 17
        assert [q.get("offset", "0") for _p, q in cabled["netbox"].gets] == ["0", "5", "10",
                                                                             "15"]
        monkeypatch.setattr(NM, "CABLE_PAGES", 2)
        got = NM.read_cables("Lab")
        assert len(got["cables"]) == 10 and got["truncated"] == (
            "10 of 17 cables read, the most one read takes (2 pages of 5)")

    def test_a_read_netbox_refuses_is_said_and_intents_links_stand(self, cabled):
        cabled["netbox"].status = 500
        m = _model()
        assert m["netbox_cables"]["state"] == "could not read"
        assert "HTTP 500" in m["netbox_cables"]["why"]
        assert {ln["source"] for ln in m["links"].values()} == {"intent"}
        doc = yaml.safe_load(NM.context_for("Lab", "r1", hops=1)["yaml"])
        assert doc["netbox_cables"].startswith("could not read (NetBox's cables could not be "
                                               "read (HTTP 500")

    def test_a_netbox_not_configured_is_said(self, cabled, monkeypatch):
        # The real client, over the lab's settings, which name no NetBox.
        monkeypatch.setattr("modules.integrations.get_integration",
                            lambda name, list_name="": NetBoxIntegration(list_name=list_name))
        got = NM.netbox_cables("Lab", refresh_s=0)
        assert got["state"] == "could not read" and "not configured" in got["why"]
        assert cabled["netbox"].gets == []

    def test_the_networks_site_filter_is_asked(self, cabled):
        from modules.inventory import source_config
        assert source_config.save("Lab", {"source": "netbox",
                                          "filters": {"site": "site-a"}})["filters"]["site"] == "site-a"
        NM.read_cables("Lab")
        assert cabled["netbox"].gets[0][1]["site"] == "site-a"
        assert cabled["clients"] == ["Lab"], "the network's own client"


class TestTheRebuiltPack:
    def test_a_rebuilt_packs_two_hops_walk_the_cables(self, cabled):
        """C1851's walk of the model as it is now (a pack rebuilt from the alert history)
        reaches through NetBox's cables: r5, which intent gives no link, is one hop from r3
        and two from r1 (r1 to r3 on the core segment), so its health is read for r1's
        alert."""
        cabled["inventory"].append({"hostname": "r5", "ip": "2001:db8::39",
                                    "_netbox_id": cabled["ids"]["r5"], "role": "router"})
        NM.forget()
        cap = NM.capture("Lab", "r1", hops=2, now=TM.NOW, observe=False)
        assert cap["ok"] and cap["as_now"]
        r5 = _dev(cabled, "r5")
        assert cap["reached"][r5] == {"hop": 2, "via": "link:netbox-cable:9"}
        assert cap["nodes"][r5]["name"] == "r5"
