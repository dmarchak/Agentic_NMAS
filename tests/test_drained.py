"""A device is DRAINED when no host traffic transits it, MEASURED (C551, the operator
2026-10-06, reworking C550's hand-set mark; `modules/drained.py`).

- The judgement: every up, non-loopback, non-VRF interface other than the management path
  (the interface the committed golden gives the management address) under 0.5 pkt/s in AND
  out over 3 minutes is drained; one busy interface, a missing reading, or a management
  address on no interface (or a loopback) is not; a down or VRF interface is not judged.
- The goldens are read with one `git grep`, the interfaces with their addresses and VRFs.
- The words name the interfaces, their rates and since when.
- The page header and the Devices list draw the badge from the measurement; the Actions menu
  has no manual mark, and its routes are gone.
- Needs attention: a Grafana alert whose every device is drained raises no row and is said
  under What was checked; an alert naming a device in service still does.
"""

import os
import subprocess

import pytest

from modules import drained as D
from tests.test_persist_screen import lab  # noqa: F401 (the fixture)

GOLDEN = {"r2": {"GigabitEthernet1": {"address": [], "vrf": False},
                 "GigabitEthernet2": {"address": ["192.0.2.12"], "vrf": False},
                 "GigabitEthernet3": {"address": ["198.51.100.1"], "vrf": False},
                 "GigabitEthernet4": {"address": ["198.51.100.5"], "vrf": True},
                 "Loopback0": {"address": ["203.0.113.2"], "vrf": False}}}


def _series(gi3_in=0.0, gi3_out=0.1, peak=0.2, gi1_up=2):
    up = {("r2", "Gi1"): gi1_up, ("r2", "Gi2"): 1, ("r2", "Gi3"): 1, ("r2", "Gi4"): 1,
          ("r2", "Lo0"): 1}
    busy = {("r2", "Gi2"): 40.0, ("r2", "Gi4"): 30.0, ("r2", "Gi1"): 19.0}
    return {"up": up, "in": {**busy, ("r2", "Gi3"): gi3_in}, "out": {**busy, ("r2", "Gi3"): gi3_out},
            "max_in": {**busy, ("r2", "Gi3"): peak}, "max_out": {**busy, ("r2", "Gi3"): peak}}


class TestTheJudgement:
    def test_quiet_on_all_but_the_management_path_is_drained(self):
        (v,) = D.judge({"r2": "192.0.2.12"}, GOLDEN, _series()).values()
        assert v["drained"] and v["judged"] == ["Gi3"] and v["management"] == "GigabitEthernet2"
        assert v["rates"]["Gi3"] == (0.0, 0.1)

    def test_one_busy_interface_is_not_drained(self):
        (v,) = D.judge({"r2": "192.0.2.12"}, GOLDEN, _series(peak=10.0)).values()
        assert not v["drained"] and v["judged"] == ["Gi3"]

    def test_the_control_a_down_interface_is_judged_once_up(self):
        (v,) = D.judge({"r2": "192.0.2.12"}, GOLDEN, _series(gi1_up=1)).values()
        assert not v["drained"] and v["judged"] == ["Gi1", "Gi3"]

    def test_a_missing_reading_is_not_drained(self):
        s = _series()
        del s["max_out"][("r2", "Gi3")]
        (v,) = D.judge({"r2": "192.0.2.12"}, GOLDEN, s).values()
        assert not v["drained"]

    def test_an_unknown_management_path_is_not_judged(self):
        (v,) = D.judge({"r2": "192.0.2.99"}, GOLDEN, _series()).values()
        assert not v["drained"] and "management path is not known" in v["why"]
        (v,) = D.judge({"r2": "203.0.113.2"}, GOLDEN, _series()).values()
        assert not v["drained"] and "Loopback0" in v["why"]
        (v,) = D.judge({"r9": "192.0.2.12"}, GOLDEN, _series()).values()
        assert not v["drained"] and "no committed golden" in v["why"]

    def test_the_words(self):
        (v,) = D.judge({"r2": "192.0.2.12"}, GOLDEN, _series()).values()
        v["since"] = 1791323880.0     # 2026-10-06T21:58:00Z
        assert D.words(v) == ("no host traffic on Gi3 (in 0.0/s, out 0.1/s) since 21:58 UTC; "
                              "management path GigabitEthernet2 not counted")


class TestTheGoldens:
    def test_one_grep_reads_interfaces_addresses_and_vrfs(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "golden").mkdir(parents=True)
        (repo / "golden" / "r2.cfg").write_text(
            "hostname r2\ninterface GigabitEthernet2\n ip address 192.0.2.12 255.255.255.0\n"
            "interface GigabitEthernet4\n vrf forwarding MGMT\n ip address 198.51.100.5 "
            "255.255.255.252\ninterface Loopback0\n ip address 203.0.113.2 255.255.255.255\n")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "g"]):
            subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
        got = D.interfaces_from_goldens(str(repo))["r2"]
        assert got["GigabitEthernet2"] == {"address": ["192.0.2.12"], "vrf": False, "areas": set()}
        assert got["GigabitEthernet4"]["vrf"] is True
        assert got["Loopback0"]["address"] == ["203.0.113.2"]


class TestR2sRealGolden:
    """The operator, 2026-10-06: every device here is managed on Loopback0, so the management
    path is the interfaces in the loopback's OSPF area (r2: Gi2, by `ipv6 ospf 1 area 0` and
    `network 10.255.3.0 0.0.0.255 area 0`); Gi1 is in the clab-mgmt VRF; Gi3 is data. r2 is
    drained exactly when Gi3 is under the floor."""

    @pytest.fixture(scope="class")
    def r2(self, tmp_path_factory):
        import shutil
        repo = tmp_path_factory.mktemp("repo")
        (repo / "golden").mkdir()
        shutil.copy(os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet",
                                 "r2.cfg"), repo / "golden" / "r2.cfg")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "g"]):
            subprocess.run(["git", "-C", str(repo), *cmd], check=True, env=env)
        ifs = D.interfaces_from_goldens(str(repo))
        # The management address is Loopback0's own, taken from the golden.
        return ifs, ifs["r2"]["Loopback0"]["address"][0]

    @staticmethod
    def _series(gi3):
        up = {("r2", n): 1 for n in ("GigabitEthernet1", "GigabitEthernet2", "GigabitEthernet3",
                                     "Loopback0", "Null0", "VoIP-Null0")}
        busy = {("r2", "GigabitEthernet1"): 20.0, ("r2", "GigabitEthernet2"): 40.0}
        g3 = ("r2", "GigabitEthernet3")
        return {"up": up, "in": {**busy, g3: gi3}, "out": {**busy, g3: gi3},
                "max_in": {**busy, g3: gi3}, "max_out": {**busy, g3: gi3}}

    def test_the_areas_are_read(self, r2):
        ifs, _addr = r2
        assert ifs["r2"]["Loopback0"]["areas"] == {"0"}
        assert ifs["r2"]["GigabitEthernet2"]["areas"] == {"0"}
        assert ifs["r2"]["GigabitEthernet3"]["areas"] == set()
        assert ifs["r2"]["GigabitEthernet1"]["vrf"] is True

    # The host's ifDescr names (read 2026-10-06); 5.87 pkt/s is the measured polling of s2
    # across Gi3 (below the management-polling level); Null0 and VoIP-Null0 are never judged.
    @pytest.mark.parametrize("gi3,drained", [(0.0, True), (5.87, True), (9.99, True),
                                             (10.0, False), (25.0, False)])
    def test_r2_is_drained_exactly_when_gi3_is_under_the_floor(self, r2, gi3, drained):
        ifs, addr = r2
        (v,) = D.judge({"r2": addr}, ifs, self._series(gi3)).values()
        assert v["drained"] is drained
        assert v["judged"] == ["GigabitEthernet3"] and v["management"] == "GigabitEthernet2"


class PromQLError(ValueError):
    pass


_DUR = r"[0-9]+(?:ms|s|m|h|d|w|y)"
#: The functions these queries may call, and how many arguments each takes.
_FUNCS = {"rate": 1, "max_over_time": 1}


def promql_parse(text: str) -> str:
    """A strict parser for the PromQL subset the drained queries use (no PromQL library is
    installed here or in CI): `expr := func "(" expr ")" [range] | metric [matchers] [range]`,
    `range := "[" dur "]" | "[" dur ":" dur "]"`, matchers `name op "go-string"`, joined by
    commas. Returns the text; raises PromQLError naming the offset."""
    import re as _re
    pos = 0

    def fail(why):
        raise PromQLError(f"{why} at offset {pos}: {text[pos:pos + 30]!r}")

    def ws():
        nonlocal pos
        while pos < len(text) and text[pos] == " ":
            pos += 1

    def take(pattern):
        nonlocal pos
        m = _re.compile(pattern).match(text, pos)
        if not m:
            return None
        pos = m.end()
        return m.group(0)

    def string():
        if not take(r'"'):
            fail("a string must open with a double quote")
        while True:
            if pos >= len(text):
                fail("an unterminated string")
            if take(r'"'):
                return
            if take(r"\\"):
                if not take(r'[abfnrtv\\"]'):
                    fail("an invalid escape in a string")
            else:
                take(r'[^"\\]')

    def matchers():
        if not take(r"\{"):
            return
        ws()
        while True:
            if not take(r"[a-zA-Z_][a-zA-Z0-9_]*"):
                fail("a label name")
            if not take(r"=~|!~|!=|="):
                fail("a matcher operator")
            string()
            ws()
            if take(r"\}"):
                return
            if not take(r","):
                fail("a comma or a closing brace")
            ws()

    def rng():
        if take(r"\["):
            if not take(_DUR):
                fail("a duration")
            if take(r":") and not take(_DUR):
                fail("a subquery step")
            if not take(r"\]"):
                fail("a closing bracket")

    def expr():
        ws()
        name = take(r"[a-zA-Z_:][a-zA-Z0-9_:]*")
        if not name:
            fail("a metric or function name")
        ws()
        if take(r"\("):
            if name not in _FUNCS:
                fail(f"an unknown function {name}")
            expr()
            ws()
            if not take(r"\)"):
                fail(f"{name}( is not closed")
        else:
            matchers()
        rng()

    expr()
    ws()
    if pos != len(text):
        fail("text after the expression")
    return text


class TestTheQueries:
    """The operator, 2026-10-06: 26ce5ad's peaks query was refused (HTTP 400): it never closed
    `max_over_time(`, and it selected `device`/`ifName` where the series carry `instance` and
    `ifDescr`."""

    def test_every_query_parses_and_selects_by_instance(self):
        qs = D.queries(["192.0.2.12", "192.0.2.22"])
        assert sorted(qs) == ["in", "max_in", "max_out", "out", "up"]
        for q in qs.values():
            promql_parse(q)
            assert 'instance=~"192\\\\.0\\\\.2\\\\.12|192\\\\.0\\\\.2\\\\.22"' in q
        assert qs["max_in"] == ('max_over_time(rate(ifHCInUcastPkts{instance=~"192\\\\.0\\\\.2'
                                '\\\\.12|192\\\\.0\\\\.2\\\\.22"}[2m])[180s:30s])')
        promql_parse(D.since_query("ifHCInUcastPkts", "192.0.2.12", ["GigabitEthernet3"]))

    @pytest.mark.parametrize("broken,why", [
        ('max_over_time(rate(ifHCInUcastPkts{device=~"r2"}[2m])[180s:30s]', "is not closed"),
        ('rate(ifHCInUcastPkts{instance=~"192\\.0\\.2\\.12"}[2m])', "invalid escape"),
        ('rate(ifHCInUcastPkts{instance=~"192"}[2m]', "is not closed"),
        ('max_over_time(rate(x[2m])[180s:])', "a subquery step"),
    ])
    def test_the_control_the_parser_refuses_what_prometheus_refused(self, broken, why):
        with pytest.raises(PromQLError, match=why):
            promql_parse(broken)

    def test_series_are_read_by_instance_and_ifdescr(self):
        rows = [{"metric": {"instance": "192.0.2.12", "ifDescr": "GigabitEthernet3"},
                 "value": [0, "0.25"]},
                {"metric": {"instance": "192.0.2.99", "ifDescr": "GigabitEthernet3"},
                 "value": [0, "9"]}]
        assert D._by_interface(rows, {"192.0.2.12": "r2"}) == {("r2", "GigabitEthernet3"): 0.25}


VERDICT = {"device": "r2", "drained": True, "judged": ["Gi3"], "management": "GigabitEthernet2",
           "rates": {"Gi3": (0.0, 0.0)}, "since": 1791323880.0}


class TestTheScreens:
    @pytest.fixture
    def drained_r2(self, monkeypatch):
        v = dict(VERDICT, words=D.words(VERDICT))
        monkeypatch.setattr(D, "current", lambda name: {"r2": v} if name == "Lab" else {})
        return v

    def test_the_header_and_the_list_draw_the_measurement(self, lab, drained_r2):  # noqa: F811
        page = lab["client"].get("/v2/device/r2").get_data(as_text=True)
        head = page[page.index('class="title-row"'):page.index('class="sub"')]
        assert "Drained: no host traffic on Gi3 (in 0.0/s, out 0.0/s) since 21:58 UTC" in head
        assert "below the management-polling level" in head and "under 10 unicast pkt/s" in head
        badge = lab["client"].get("/v2/device/r2/drained").get_data(as_text=True)
        assert 'hx-trigger="nmas:reachability from:body"' in badge and "Drained: " in badge
        listing = lab["client"].get("/v2/devices").get_data(as_text=True)
        r2 = listing[listing.index(">r2<"):listing.index(">r2<") + 600]
        assert ">Drained<" in r2 and "no host traffic on Gi3" in r2
        assert "below the management-polling level" in r2
        s9 = listing[listing.index(">s9<"):listing.index(">s9<") + 400]
        assert ">Drained<" not in s9

    def test_the_control_not_drained_draws_no_badge(self, lab, monkeypatch):  # noqa: F811
        monkeypatch.setattr(D, "current", lambda name: {})
        page = lab["client"].get("/v2/device/r2").get_data(as_text=True)
        assert "Drained" not in page[page.index('class="title-row"'):page.index('class="sub"')]

    def test_an_unmeasurable_network_draws_no_badge_and_the_list_says_so(
            self, lab, monkeypatch):  # noqa: F811
        def broken(name):
            raise RuntimeError("Prometheus could not be asked for interface states: refused")
        monkeypatch.setattr(D, "current", broken)
        page = lab["client"].get("/v2/device/r2").get_data(as_text=True)
        assert "Drained" not in page[page.index('class="title-row"'):page.index('class="sub"')]
        listing = lab["client"].get("/v2/devices").get_data(as_text=True)
        assert "whether a device is drained could not be measured" in listing

    def test_nobody_sets_it(self, lab):  # noqa: F811
        page = lab["client"].get("/v2/device/r2").get_data(as_text=True)
        assert 'data-op="drained"' not in page and "Mark drained" not in page
        assert lab["client"].post("/v2/device/r2/drained/confirm").status_code in (404, 405)


class TestNeedsAttention:
    @pytest.fixture
    def alert_on_r1(self, monkeypatch):
        from modules import attention as A
        from modules import device
        from tests.test_grafana_reader import INVENTORY, cached, load, parse, rule
        monkeypatch.setattr(device, "load_saved_devices", lambda *a, **k: list(INVENTORY))
        monkeypatch.setattr(device, "get_device_lists",
                            lambda: [{"name": "Lab", "filename": "lab"}])
        view = load("rules_view")
        inst = next(a for a in rule(view, "Device unreachable (SNMP)")["alerts"]
                    if a["labels"]["instance"] == "10.255.1.11")
        inst["state"], inst["activeAt"] = "Alerting", "2026-09-28T20:20:00Z"
        return lambda: A.grafana_source(cached=cached(parse(view)))

    def test_an_alert_on_a_drained_device_is_said_under_checked_not_raised(
            self, alert_on_r1, monkeypatch):
        v = dict(VERDICT, device="r1")
        monkeypatch.setattr(D, "current", lambda name: {"r1": v} if name == "Lab" else {})
        res = alert_on_r1()
        assert res["rows"] == []
        assert ("1 alert(s) on drained devices, not raised: Device unreachable (SNMP) on r1 "
                "(no host traffic on Gi3") in res["checked"]

    def test_the_control_the_same_alert_undrained_is_a_row(self, alert_on_r1, monkeypatch):
        monkeypatch.setattr(D, "current", lambda name: {})
        (row,) = alert_on_r1()["rows"]
        assert row["devices"] == ["r1"]

    def test_another_device_drained_holds_nothing_back(self, alert_on_r1, monkeypatch):
        monkeypatch.setattr(D, "current", lambda name: {"r2": dict(VERDICT)})
        (row,) = alert_on_r1()["rows"]
        assert row["devices"] == ["r1"]

    def test_an_unmeasurable_network_holds_nothing_back_and_says_so(self, alert_on_r1,
                                                                    monkeypatch):
        def broken(name):
            raise RuntimeError("refused")
        monkeypatch.setattr(D, "current", broken)
        res = alert_on_r1()
        assert len(res["rows"]) == 1
        assert "the drained record could not be read (RuntimeError)" in res["checked"]
