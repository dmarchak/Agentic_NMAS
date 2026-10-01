"""The device page's Neighbours (register C38; NSOT_GUI_BRIEF 3.3; step 4),
from `modules/neighbours`.

Expected adjacencies come from the nine REAL fleet configs, parsed by the real
parsers as committed intent would hold them; what the devices report is
Prometheus's REAL answer for `ospfNbrState`, `ospfv3NbrState`,
`cbgpPeer2State` and `up`, captured read-only from the host on 2026-10-01
(`tests/fixtures/prometheus/neighbours.json`). Every failure state is a
minimal edit of that answer. Nothing here opens a session to a device: the
page reads Prometheus.
"""

import copy
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "prometheus", "neighbours.json")
UP = 'up{job=~"ospf|ospfv3|bgp"}'
METRICS = ("ospfNbrState", "ospfv3NbrState", "cbgpPeer2State")


def _intents():
    from modules.nsot.parsers import get_parser
    out = {}
    for f in sorted(os.listdir(FLEET)):
        host = f[:-4]
        dialect = "cisco_iosxe" if host.startswith("r") else "cisco_ios"
        out[host] = get_parser(dialect).parse(open(os.path.join(FLEET, f), encoding="utf-8").read())
    return out


def _capture():
    return json.load(open(CAPTURE, encoding="utf-8"))


def _for(cap, host):
    res = {m: [r for r in cap[m]["data"]["result"] if r["metric"].get("device") == host]
           for m in METRICS}
    up = {r["metric"]["job"]: int(r["value"][1]) for r in cap[UP]["data"]["result"]
          if r["metric"]["device"] == host}
    return res, up


def _view(host, intents=None, cap=None):
    from modules import neighbours as N
    intents = intents if intents is not None else _intents()
    res, up = _for(cap or _capture(), host)
    return N.compare(intents, host, res, up)


def _rows(view, proto):
    return next((p["rows"] for p in view["protocols"] if p["proto"] == proto), [])


class TestTheFleetAsItIs:
    def test_the_capture_is_real_and_whole(self):
        cap = _capture()
        assert len(cap["ospfNbrState"]["data"]["result"]) >= 30
        assert {r["metric"]["device"] for r in cap[UP]["data"]["result"]} >= {"r1", "r3", "s3"}

    def test_r3_expects_what_it_reports_every_adjacency_up(self):
        v = _view("r3")
        ospf = {(r["peer"], r["via"]) for r in _rows(v, "ospf")}
        # Its core segment (five peers) and the /31 to r4: r4 twice, one per link.
        assert ospf == {("r1", "GigabitEthernet3"), ("r2", "GigabitEthernet3"),
                        ("r4", "GigabitEthernet3"), ("s3", "GigabitEthernet3"),
                        ("s4", "GigabitEthernet3"), ("r4", "GigabitEthernet4")}
        assert len(_rows(v, "ospfv3")) == 4
        assert {r["address"] for r in _rows(v, "bgp")} == {"198.51.100.1", "2001:db8:51::2"}
        assert v["counts"] == {"up": 12, "down": 0, "not_seen": 0, "unexpected": 0}

    def test_s3s_passive_management_segment_is_not_expected(self):
        """C prime's property: s3 forms no adjacency on Vlan99."""
        rows = _rows(_view("s3"), "ospf")
        assert {r["via"] for r in rows} == {"Vlan100"} and len(rows) == 5
        assert all(r["state"] == "up" for r in rows)

    def test_ospf_on_s3s_management_segment_is_still_not_s3s_neighbour(self):
        """The case the fleet cannot show by itself: a device running OSPF on
        Vlan99's subnet (the shape option C would have deployed). A minimal
        edit of r1's REAL intent: its core interface readdressed onto
        10.255.0.0/24 and its network statement with it. s3's Vlan99 is
        passive, so no adjacency is expected of s3; the new device expects one
        it will never get, and says so."""
        intents = _intents()
        r6 = copy.deepcopy(intents["r1"])
        for iface in r6["interfaces"]:
            if iface["name"] == "GigabitEthernet2":
                iface["ipv4"] = "10.255.0.32 255.255.255.0"
        r6["routing"]["ospf"][0]["networks"] = ["network 10.255.0.0 0.0.0.255 area 0"]
        intents["r6"] = r6
        assert not any(r["peer"] == "r6" for r in _rows(_view("s3", intents=intents), "ospf"))
        from modules import neighbours as N
        assert [e["peer"] for e in N.expected(intents, "r6") if e["proto"] == "ospf"] == []

    def test_two_way_is_up_between_two_drothers(self):
        rows = {r["peer"]: r for r in _rows(_view("r1"), "ospf")}
        assert rows["r2"]["state"] == "up" and rows["r2"]["words"] == "2-way"
        assert rows["r3"]["words"] == "full"

    def test_a_rip_device_has_no_adjacency_rows(self):
        assert _view("s1")["protocols"] == []


class TestWhatGoesWrongIsNamed:
    def test_a_neighbour_the_device_stopped_reporting_is_not_seen(self):
        cap = _capture()
        cap["ospfNbrState"]["data"]["result"] = [
            r for r in cap["ospfNbrState"]["data"]["result"]
            if not (r["metric"]["device"] == "r3" and r["metric"]["ospfNbrIpAddr"] == "10.255.2.15")]
        v = _view("r3", cap=cap)
        gone = [r for r in _rows(v, "ospf") if r["state"] == "not_seen"]
        assert [(r["peer"], r["via"]) for r in gone] == [("r4", "GigabitEthernet4")]
        assert v["counts"]["not_seen"] == 1

    def test_a_stuck_neighbour_is_down_with_its_state(self):
        cap = _capture()
        for r in cap["ospfNbrState"]["data"]["result"]:
            if r["metric"]["device"] == "r1" and r["metric"]["ospfNbrIpAddr"] == "10.255.3.13":
                r["value"][1] = "3"
        row = next(r for r in _rows(_view("r1", cap=cap), "ospf") if r["peer"] == "r3")
        assert row["state"] == "down" and row["words"] == "init"

    def test_a_bgp_session_not_established_is_down(self):
        cap = _capture()
        for r in cap["cbgpPeer2State"]["data"]["result"]:
            if r["metric"]["cbgpPeer2RemoteAddr"] == "198.51.100.1":
                r["value"][1] = "3"
        row = next(r for r in _rows(_view("r3", cap=cap), "bgp") if r["address"] == "198.51.100.1")
        assert row["state"] == "down" and row["words"] == "active"

    def test_a_neighbour_intent_does_not_imply_is_unexpected(self):
        intents = _intents()
        del intents["s4"]                     # s4's adjacency is no longer implied
        v = _view("r1", intents=intents)
        extra = [r for r in _rows(v, "ospf") if r["state"] == "unexpected"]
        assert [r["address"] for r in extra] == ["10.255.3.24"]
        assert extra[0]["managed"] is False

    def test_a_peer_outside_management_is_said(self):
        intents = _intents()
        del intents["r5"]                     # r5 retired: not in committed intent
        rows = _rows(_view("r3", intents=intents), "bgp")
        assert rows and all(not r["managed"] and r["peer"] == "" for r in rows)
        assert all(r["state"] == "up" for r in rows)

    def test_an_unscraped_protocol_is_not_measured_never_not_seen(self):
        cap = _capture()
        cap[UP]["data"]["result"] = [r for r in cap[UP]["data"]["result"]
                                     if not (r["metric"]["device"] == "r3" and r["metric"]["job"] == "bgp")]
        cap["cbgpPeer2State"]["data"]["result"] = []
        v = _view("r3", cap=cap)
        bgp = next(p for p in v["protocols"] if p["proto"] == "bgp")
        assert bgp["measured"] is False and "does not scrape BGP from r3" in bgp["why"]
        assert {r["state"] for r in bgp["rows"]} == {"unknown"}
        assert v["counts"]["not_seen"] == 0

    def test_a_failed_scrape_is_said(self):
        cap = _capture()
        for r in cap[UP]["data"]["result"]:
            if r["metric"]["device"] == "r3" and r["metric"]["job"] == "ospf":
                r["value"][1] = "0"
        ospf = next(p for p in _view("r3", cap=cap)["protocols"] if p["proto"] == "ospf")
        assert "last `ospf` scrape of r3 failed" in ospf["why"]


class TestTheFleetIsReadInFixedCalls:
    def test_two_git_calls_whatever_the_size(self, tmp_path, monkeypatch):
        """The scale rule: the whole fleet's intent in one ls-tree and one
        cat-file, never a read per device."""
        import subprocess
        import yaml
        from modules import neighbours as N
        repo = str(tmp_path)
        subprocess.run(["git", "init", "-q", repo], check=True)
        os.makedirs(os.path.join(repo, "host_vars"))
        intents = _intents()
        for host, hv in intents.items():
            with open(os.path.join(repo, "host_vars", f"{host}.yml"), "w", encoding="utf-8") as fh:
                yaml.safe_dump(dict(hv, hostname=host), fh)
        subprocess.run(["git", "-C", repo, "add", "host_vars"], check=True)
        subprocess.run(["git", "-C", repo, "-c", "user.email=t@example.com", "-c", "user.name=t",
                        "commit", "-q", "-m", "intent"], check=True)
        calls, real_run = [], subprocess.run

        def counting(argv, *a, **k):
            if argv[:2] == ["git", "-C"]:
                calls.append(argv[3])
            return real_run(argv, *a, **k)
        monkeypatch.setattr(subprocess, "run", counting)
        docs, err = N.committed_intents(repo)
        assert err == "" and set(docs) == set(intents) and len(docs) == 9
        assert docs["r3"]["routing"]["ospf"] == intents["r3"]["routing"]["ospf"]
        assert calls == ["ls-tree", "cat-file"]

    def test_no_intent_committed_is_empty_not_an_error(self, tmp_path):
        import subprocess
        from modules import neighbours as N
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        assert N.committed_intents(str(tmp_path)) == ({}, "")


# ---------------------------------------------------------------------------
# The page, through the real route.
# ---------------------------------------------------------------------------

from tests.test_profile_apply import lab  # noqa: E402,F401 (the fixture)


@pytest.fixture
def page(lab, monkeypatch):
    from modules import device_page
    from modules import neighbours as N
    from modules.integrations.prometheus import PrometheusIntegration
    from modules.nsot import listref

    intents = _intents()
    monkeypatch.setattr(N, "committed_intents", lambda repo: (intents, ""))
    rows = {h: {"hostname": h, "ip": "192.0.2.1", "platform": "cisco_iosxe"} for h in intents}
    monkeypatch.setattr(device_page, "find_device",
                        lambda name: (listref.resolve("Lab"), dict(rows[name])))
    cap = _capture()
    asked = []

    class Resp:
        def __init__(self, body):
            self._b = body

        def json(self):
            return self._b

    def fake_get(self, path, **params):
        q = params["query"]
        asked.append(q)
        dev = re.search(r'device="([^"]+)"', q).group(1)
        metric = "up" if q.startswith("up{") else q.split("{")[0]
        key = UP if metric == "up" else metric
        body = copy.deepcopy(cap[key])
        body["data"]["result"] = [r for r in body["data"]["result"] if r["metric"].get("device") == dev]
        return {"ok": True, "response": Resp(body)}

    monkeypatch.setattr(PrometheusIntegration, "is_configured", lambda self: True)
    monkeypatch.setattr(PrometheusIntegration, "_get", fake_get)

    def no_session(*a, **k):
        raise AssertionError("the Neighbours tab opened a session to a device")
    monkeypatch.setattr("modules.connection.open_ssh", no_session)

    def get(url):
        r = lab["client"].get(url)
        return r, r.get_data(as_text=True)
    get.asked = asked
    return get


class TestThePage:
    def test_r3s_neighbours_drawn_linked_and_strict(self, page):
        from modules import csp
        r, html = page("/v2/device/r3/neighbours")
        assert r.status_code == 200 and r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert not re.search(r"\sstyle=|\son[a-z]+=", html)
        assert "Every adjacency intent implies for r3 that is measured is up." in html
        for proto in ("OSPF", "OSPFv3", "BGP"):
            assert f'<h3 class="nb-proto">{proto}</h3>' in html
        assert '<a href="/v2/device/r4">r4</a>' in html
        assert "nothing here opens a session to the device" in html
        # Four instant queries, each filtered to the device.
        assert len(page.asked) == 4 and all('device="r3"' in q for q in page.asked)

    def test_the_tab_is_built(self, page):
        _r, html = page("/v2/device/r3?tab=neighbours")
        assert 'hx-get="/v2/device/r3/neighbours"' in html and 'id="neighbours"' in html

    def test_a_rip_device_says_rip_keeps_no_table(self, page):
        _r, html = page("/v2/device/s1/neighbours")
        assert "s1 runs RIP, which keeps no neighbour table this page reads." in html

    def test_prometheus_not_configured_is_said(self, page, monkeypatch):
        from modules.integrations.prometheus import PrometheusIntegration
        monkeypatch.setattr(PrometheusIntegration, "is_configured", lambda self: False)
        _r, html = page("/v2/device/r3/neighbours")
        assert "Prometheus is not configured" in html and "nb-table" not in html

    def test_prometheus_unreachable_is_said_never_none(self, page, monkeypatch):
        from modules.integrations.prometheus import PrometheusIntegration
        monkeypatch.setattr(PrometheusIntegration, "_get",
                            lambda self, path, **p: {"ok": False, "error": "Could not connect"})
        _r, html = page("/v2/device/r3/neighbours")
        assert "Prometheus could not be asked for ospfNbrState: Could not connect" in html
        assert "reports none" not in html
