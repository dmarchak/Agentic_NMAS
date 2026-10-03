"""Coverage's not-reporting reader (artboard A, signed off 2026-10-02): when each device's
monitoring data last ARRIVED, one query per source for the fleet, and the judgement of a
configured cell as reporting, not reporting (with for how long and where to look), unproven
(syslog with no heartbeat) or unjudged (the reader's own failure, never the device's).

The data is the REAL capture from the host (2026-10-03, addresses 192.0.2.x): Prometheus's
active targets, the last-good-scrape and telemetry queries, and Loki's syslog and heartbeat
range queries, for the lab's nine devices, every one reporting. Each failing state is that
capture with the one edit that makes it, never a document typed from memory.
"""

import copy
import json
import os
import re

import pytest

from modules.readers import coverage_reporting as CR
from tests.test_profile_apply import lab  # noqa: F401 (the fixture: r2's real golden)

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURE = os.path.join(HERE, "fixtures", "coverage_reporting", "capture.json")
LOGS = os.path.join(HERE, "fixtures", "loki", "device_logs.json")
NINE = ["r1", "r2", "r3", "r4", "r6", "s1", "s2", "s3", "s4"]
#: The windows Grafana's installed heartbeat rules held on the host, read 2026-10-03.
WINDOWS = {"r1": 750, "r2": 750, "r3": 767, "r4": 749, "r6": 750, "s1": 818, "s2": 828,
           "s3": 1337, "s4": 1005}


def _capture():
    with open(CAPTURE, encoding="utf-8") as fh:
        return json.load(fh)


class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _Client:
    """Prometheus or Loki answering from the capture, recording each query it is asked."""

    def __init__(self, cap, label, configured=True, fail=()):
        self.cap, self.label, self.configured, self.fail, self.asked = cap, label, configured, fail, []

    def is_configured(self):
        return self.configured

    def _get(self, path, **params):
        q = params.get("query", "")
        self.asked.append((path, q))
        if path == "api/v1/targets":
            key = "targets"
        elif path == "api/v1/query":
            key = "up" if "up{" in q else "telemetry"
        else:
            key = "heartbeat" if "HEARTBEAT" in q else "syslog"
        if key in self.fail:
            return {"ok": False, "error": "Could not connect to http://192.0.2.1:9090"}
        return {"ok": True, "response": _Resp(self.cap[key])}


@pytest.fixture
def read(monkeypatch):
    """The reader over a (possibly edited) capture, at the capture's own time."""
    monkeypatch.setattr(CR, "windows", lambda: {h: {"window": w, "basis": "measured"}
                                                for h, w in WINDOWS.items()})
    from modules import settings_schema
    before = settings_schema.get_setting      # a lab's settings, when one is installed first
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda k, d=None: 300 if k == "syslog_heartbeat_seconds" else before(k, d))

    def run(cap=None, prom_fail=(), loki_fail=(), loki_configured=True):
        cap = cap or _capture()
        prom = _Client(cap, "Prometheus", fail=prom_fail)
        loki = _Client(cap, "Loki", configured=loki_configured, fail=loki_fail)
        value = CR.read(now=cap["captured_at"], prom=prom, loki=loki)
        return value, prom, loki
    return run


def _judge(value, column, host, **kw):
    return CR.judge(column, host, value, now=value["read_at"], **kw)


def _down(cap, host, jobs=None, minutes_ago=12):
    """*host*'s targets (or only *jobs*) failing, their last good scrape *minutes_ago*."""
    for t in cap["targets"]["data"]["activeTargets"]:
        if t["labels"].get("device") == host and (jobs is None or t["labels"]["job"] in jobs):
            t["health"], t["lastError"] = "down", "request timeout"
    for r in cap["up"]["data"]["result"]:
        if r["metric"]["device"] == host and (jobs is None or r["metric"]["job"] in jobs):
            r["value"][1] = str(cap["captured_at"] - minutes_ago * 60)
    return cap


class TestTheRealFleetReports:
    def test_one_query_per_source_for_the_whole_fleet(self, read):
        value, prom, loki = read()
        assert sorted(p for p, _q in prom.asked) == ["api/v1/query", "api/v1/query", "api/v1/targets"]
        assert [p for p, _q in loki.asked] == ["loki/api/v1/query_range"] * 2
        assert all(s["ok"] for s in value["sources"].values())
        # Every device, from the one answer each: no query names a device.
        assert sorted(value["targets"]) == sorted(value["syslog"]) == sorted(value["heartbeat"]) == NINE
        assert not any(h in q for _p, q in prom.asked + loki.asked for h in NINE)

    def test_every_configured_source_of_the_nine_reports(self, read):
        value, _p, _l = read()
        for host in NINE:
            for col in ("snmp", "heartbeat"):
                assert _judge(value, col, host)["state"] == "reporting", (host, col)
            assert _judge(value, "syslog", host, heartbeat_configured=True)["state"] == "reporting"
        # IP SLA's targets come from nmas-snmp-ipsla.json: the five devices that run a probe.
        ipsla = [h for h in NINE if _judge(value, "ip_sla", h)["state"] == "reporting"]
        assert ipsla == ["r1", "r2", "r3", "r4", "s3"]
        telemetry = [h for h in NINE if _judge(value, "telemetry", h)["state"] == "reporting"]
        assert telemetry == ["r1", "r2", "r3", "r4", "r6"]

    def test_the_name_pulled_from_each_line_is_the_name_the_anchored_query_matches(self):
        """NAME_RX is applied by Loki; the same expression over the REAL captured lines of
        r3 and s3 names the device of every line (measured on the host: 3,326 lines over
        24 h, every count equal to the anchored per-device query's)."""
        with open(LOGS, encoding="utf-8") as fh:
            logs = json.load(fh)
        n = 0
        for host in ("r3", "s3"):
            for stream in logs[host]["body"]["data"]["result"]:
                for _ns, line in stream["values"]:
                    m = re.search(CR.NAME_RX, line)
                    assert m and m.group("dev") == host, line
                    # C13, measured 2026-09-25: a device /etc/hosts did not list had its
                    # ADDRESS in rsyslog's hostname field. The name still comes from the
                    # device's own origin-id, never from that field.
                    unlisted = re.sub(r"^(\w{3}\s+\d+\s+[\d:]+\s+)\S+", r"\g<1>192.0.2.16", line)
                    assert unlisted != line
                    assert re.search(CR.NAME_RX, unlisted).group("dev") == host, unlisted
                    n += 1
        assert n >= 20


class TestNotReporting:
    def test_a_device_whose_snmp_fails_says_for_how_long_and_where_to_look(self, read):
        value, _p, _l = read(_down(_capture(), "r3"))
        got = _judge(value, "snmp", "r3")
        assert got["state"] == "not_reporting" and got["where"] == "monitoring"
        assert got["words"] == "no scrape for 12 min (request timeout)"
        assert _judge(value, "snmp", "r4")["state"] == "reporting"

    def test_one_missed_scrape_is_not_a_device_not_reporting(self, read):
        """C383, measured on the host 2026-10-03: jobs on 30 s intervals miss a scrape or two
        for 67 to 73 s; the grid flapped between 9, 7 and 3 of 9 fully covered."""
        value, _p, _l = read(_down(_capture(), "r1", jobs=("cisco_8000v", "ospfv3"),
                                   minutes_ago=73 / 60))
        assert _judge(value, "snmp", "r1")["state"] == "reporting"
        value, _p, _l = read(_down(_capture(), "r1", minutes_ago=4))
        assert _judge(value, "snmp", "r1")["state"] == "not_reporting"

    def test_a_missed_scrape_announces_nothing(self, read):
        a, _p, _l = read()
        b, _p, _l = read(_down(_capture(), "r4", jobs=("bgp",), minutes_ago=67 / 60))
        assert not CR.changed(a, b)

    def test_one_job_failing_names_the_job_and_says_the_rest_answer(self, read):
        value, _p, _l = read(_down(_capture(), "r3", jobs=("lldp",), minutes_ago=7))
        got = _judge(value, "snmp", "r3")
        assert got["state"] == "not_reporting"
        assert got["words"] == "lldp not scraped for 7 min; the rest answer"

    def test_a_target_prometheus_stopped_scraping_is_not_reporting(self, read):
        cap = _capture()
        for t in cap["targets"]["data"]["activeTargets"]:
            if t["labels"].get("device") == "s1":
                t["lastScrape"] = "2026-10-03T08:00:00Z"
        value, _p, _l = read(cap)
        got = _judge(value, "snmp", "s1")
        assert got["state"] == "not_reporting" and "Prometheus has stopped scraping it" in got["words"]

    def test_no_target_at_all_is_not_scraped(self, read):
        cap = _capture()
        cap["targets"]["data"]["activeTargets"] = [
            t for t in cap["targets"]["data"]["activeTargets"] if t["labels"].get("device") != "r6"]
        value, _p, _l = read(cap)
        assert _judge(value, "snmp", "r6")["words"] == \
            "not scraped: Prometheus has no SNMP target for it"
        assert _judge(value, "ip_sla", "r6")["words"] == \
            "not scraped: Prometheus has no IP SLA target for it"

    def test_ip_sla_is_judged_on_its_own_targets_only(self, read):
        value, _p, _l = read(_down(_capture(), "s3", jobs=("cisco_ipsla",)))
        assert _judge(value, "ip_sla", "s3")["state"] == "not_reporting"
        assert _judge(value, "snmp", "s3")["state"] == "reporting"

    def test_a_stopped_stream(self, read):
        cap = _capture()
        for r in cap["telemetry"]["data"]["result"]:
            if r["metric"]["source"] == "r3":
                r["value"][1] = str(cap["captured_at"] - 9 * 60)
        cap["telemetry"]["data"]["result"] = [
            r for r in cap["telemetry"]["data"]["result"] if r["metric"]["source"] != "r6"]
        value, _p, _l = read(cap)
        assert _judge(value, "telemetry", "r3") == {
            "state": "not_reporting", "words": "no stream for 9 min", "where": "monitoring"}
        assert _judge(value, "telemetry", "r6")["words"] == "no stream for over 3 h"
        assert _judge(value, "telemetry", "r1")["state"] == "reporting"

    def test_a_heartbeat_is_judged_by_its_own_alerts_window(self, read):
        """s3 beats about 7 times an hour; its alert's measured window is 1337 s. A gap of
        16 min is inside it (the alert is quiet, so Coverage is too); r3's 750 s is not."""
        cap = _capture()
        now = cap["captured_at"]
        for s in cap["heartbeat"]["data"]["result"]:
            if s["metric"]["dev"] in ("s3", "r3"):
                # The beats of the last 16 min removed, the last one exactly 16 min ago.
                s["values"] = [v for v in s["values"] if float(v[0]) < now - 16 * 60]
                s["values"].append([now - 16 * 60, "1"])
        value, _p, _l = read(cap)
        assert _judge(value, "heartbeat", "s3")["state"] == "reporting"
        got = _judge(value, "heartbeat", "r3")
        assert got["state"] == "not_reporting" and got["where"] == "logs"
        assert got["words"] == "none for 16 min (its alert's measured window: 13 min)"

    def test_without_an_installed_rule_the_window_is_twice_the_period(self, read, monkeypatch):
        cap = _capture()
        value, _p, _l = read(cap)
        value["windows"] = {}
        value["heartbeat"]["r3"] = value["read_at"] - 11 * 60
        assert _judge(value, "heartbeat", "r3")["words"] == \
            "none for 11 min (twice the heartbeat period: 10 min)"

    def test_syslog_with_a_heartbeat_is_not_reporting_when_no_line_arrives(self, read):
        cap = _capture()
        for key in ("syslog", "heartbeat"):
            cap[key]["data"]["result"] = [s for s in cap[key]["data"]["result"]
                                          if s["metric"]["dev"] != "s2"]
        value, _p, _l = read(cap)
        got = _judge(value, "syslog", "s2", heartbeat_configured=True)
        assert got == {"state": "not_reporting", "words": "no lines for over 3 h", "where": "logs"}

    def test_syslog_without_a_heartbeat_is_unproven_never_not_reporting(self, read):
        """A quiet device sends nothing: only the heartbeat proves the path."""
        cap = _capture()
        cap["syslog"]["data"]["result"] = [s for s in cap["syslog"]["data"]["result"]
                                           if s["metric"]["dev"] != "s2"]
        value, _p, _l = read(cap)
        got = _judge(value, "syslog", "s2", heartbeat_configured=False)
        assert got["state"] == "unproven" and "where" not in got
        assert got["words"] == "nothing proves it arrives: no heartbeat, and no line in over 3 h"
        assert _judge(value, "syslog", "s1", heartbeat_configured=False)["state"] == "reporting"


class TestTheReadersOwnFailureAccusesNoDevice:
    def test_no_reading_and_a_stale_reading_are_unjudged(self, read):
        assert CR.judge("snmp", "r3", None)["state"] == "unjudged"
        value, _p, _l = read(_down(_capture(), "r3"))
        later = value["read_at"] + 10 * 60
        got = CR.judge("snmp", "r3", value, now=later)
        assert got == {"state": "unjudged",
                       "words": "whether it reports is unknown: the last reading is 10 min old"}

    def test_a_source_that_could_not_be_asked_is_unjudged_and_the_rest_are_judged(self, read):
        value, _p, _l = read(loki_fail=("heartbeat",))
        assert not value["sources"]["heartbeat"]["ok"]
        got = _judge(value, "heartbeat", "r3")
        assert got["state"] == "unjudged" and "Loki's heartbeat lines could not be asked" in got["words"]
        assert _judge(value, "syslog", "r3", heartbeat_configured=True)["state"] == "reporting"
        assert _judge(value, "snmp", "r3")["state"] == "reporting"

    def test_loki_not_configured_is_said_and_prometheus_still_read(self, read):
        value, _p, loki = read(loki_configured=False)
        assert value["sources"]["syslog"] == {"ok": False, "error": "Loki is not configured"}
        assert not loki.asked and value["sources"]["targets"]["ok"]

    def test_nothing_answering_is_a_failed_read_which_keeps_the_last_good_value(self, read):
        with pytest.raises(RuntimeError, match="no source could be asked"):
            read(prom_fail=("targets", "up", "telemetry"), loki_fail=("syslog", "heartbeat"))


class TestAnnouncements:
    def test_a_read_that_only_moves_the_times_announces_nothing(self, read):
        a, _p, _l = read()
        b = copy.deepcopy(a)
        b["read_at"] += 60
        for key in ("syslog", "heartbeat", "telemetry"):
            b[key] = {h: t + 60 for h, t in b[key].items()}
        for ts in b["targets"].values():
            for t in ts:
                t["last_scrape"] += 60
        assert not CR.changed(a, b)

    def test_a_verdict_that_could_move_announces(self, read):
        a, _p, _l = read()
        b, _p, _l = read(_down(_capture(), "r3"))
        assert CR.changed(a, b)
        c = copy.deepcopy(a)
        c["read_at"] += 20 * 60      # every heartbeat now outside its window
        assert CR.changed(a, c)

    def test_registered_declared_and_keeping_alive(self):
        from modules import reader_job
        from modules.invalidation import VOCABULARY

        assert "modules.readers.coverage_reporting" in reader_job.DECLARED_MODULES
        assert CR.READER.invalidates == ("coverage_reporting",)
        assert "coverage_reporting" in VOCABULARY
        assert CR.READER.announce_if is CR.changed and CR.READER.announce_at_least_every > 0


class TestTheGrid:
    """Coverage draws the judgement on r2's REAL golden (test_profile_apply's lab): a configured
    cell not reporting is its own state, linking to the device tab where its cause is looked for
    (artboard A: never a redeploy); the reader's failure is said once and accuses no device."""

    @pytest.fixture
    def r2_down(self, read):
        # r2's SNMP jobs failing; its IP SLA target still answers.
        value, _p, _l = read(_down(_capture(), "r2", jobs=("cisco_8000v", "lldp", "ospf", "ospfv3")))
        return value

    def test_a_configured_cell_not_reporting_is_its_own_state(self, lab, r2_down, monkeypatch):
        from tests.test_coverage_page import _fleet, _row

        monkeypatch.setattr("time.time", lambda: r2_down["read_at"])
        c = _fleet(lab, report=(r2_down, "", ""))
        cell = _row(c, "r2")["cells"]["snmp"]
        assert cell["state"] == "not_reporting" and cell["where"] == "monitoring"
        assert cell["words"] == "not reporting — no scrape for 12 min (request timeout)"
        assert _row(c, "r2")["not_reporting"] == ["snmp"]
        # r6 here is r2's golden less its SNMP: it keeps r2's IP SLA probe, and Prometheus
        # has no IP SLA target for it (the real nmas-snmp-ipsla.json lists five, not r6).
        assert _row(c, "r6")["cells"]["ip_sla"]["words"] == \
            "not reporting — not scraped: Prometheus has no IP SLA target for it"
        assert (c["not_reporting"], c["not_reporting_devices"]) == (2, 2)
        # Not reporting is configured: never a gap, never offered for Apply.
        assert "snmp" not in _row(c, "r2")["gaps"]

    def test_no_reading_is_said_once_and_every_configured_cell_stays_configured(self, lab):
        from tests.test_coverage_page import _fleet, _row

        c = _fleet(lab, report=(None, None, "no reader has written coverage-reporting.json"))
        assert c["not_reporting"] == 0
        assert c["reporting_unknown"] == ("whether it reports is unknown: no reader has written "
                                         "coverage-reporting.json")
        cell = _row(c, "r2")["cells"]["snmp"]
        assert cell["state"] == "ok" and cell["reporting"]["state"] == "unjudged"

    def test_the_page_links_the_cell_to_its_diagnosis_and_counts_it(self, lab, r2_down, monkeypatch):
        from tests.test_coverage_page import _page

        monkeypatch.setattr("time.time", lambda: r2_down["read_at"])
        monkeypatch.setattr("modules.device_page._cached", lambda name: (r2_down, "", ""))
        r, html = _page(lab, monkeypatch, "/v2/monitoring/coverage/table")
        assert r.status_code == 200
        cell = re.search(r'<td class="gc" data-state="not_reporting"><a class="nr-link" '
                         r'href="/v2/device/r2\?tab=monitoring" title="([^"]*)"', html)
        assert cell and cell.group(1) == ("r2 · SNMP: not reporting — no scrape for 12 min (request "
                                          "timeout). Opens r2 › Monitoring to find why: a deploy "
                                          "does not fix this")
        assert '<strong class="cov-nr-count">2 not reporting</strong> on 2' in html
        assert "nmas:coverage_reporting from:body" in html
