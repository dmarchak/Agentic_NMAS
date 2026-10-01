"""A stat never draws an impossible value (the operator, 2026-10-01: the
Device clock rate panel read -2475% after s3's reboot, sysUpTime having
dropped to zero and the panel's `deriv()` reading the drop as time running
backwards).

Two halves:
- the dashboard's queries over sysUpTime are RESET-AWARE (`rate()`, which
  treats a drop as a counter restart), never `deriv()` or `delta()`, in the
  builder and the JSON it writes (`deploy/grafana/nmas-device.json`);
- the app draws a stat whose panel declares its valid range (Grafana's
  min and max: the clock rate 0 to 110%, the CPU and memory percentages,
  Answering SNMP 0 to 1) as WORDS when a reading falls outside it, and, where
  the panel reads sysUpTime, says when the device restarted, from the
  device's own sysUpTime series.

Every answer below is in Grafana's `api/ds/query` shape, the values the
operator's case: s3 at a clock rate of about 0.55 for an hour, then
restarted, sysUpTime counting again from 0.
"""

import json
import os
import re

import dukpy
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(ROOT, "deploy", "grafana", "nmas-device.json")


def _walk(panels):
    for p in panels:
        yield p
        yield from _walk(p.get("panels") or [])


def _model():
    return json.load(open(DASH, encoding="utf-8"))


def _answer(times_s, values, ref="A"):
    return {"results": {ref: {"frames": [{"schema": {"fields": [{"name": "Time"},
                                                                {"name": "Value", "labels": {"device": "s3"}}]},
                                          "data": {"values": [[t * 1000 for t in times_s], values]}}]}}}


class TestTheQueriesAreResetAware:
    def test_no_query_over_sysuptime_uses_deriv_or_delta(self):
        exprs = [t["expr"] for p in _walk(_model()["panels"]) for t in p.get("targets") or []]
        uptime = [e for e in exprs if "sysUpTime" in e]
        assert len(uptime) >= 4, uptime
        bad = [e for e in uptime if re.search(r"\b(deriv|delta|idelta)\(\s*sysUpTime", e)]
        assert bad == []
        rated = [e for e in uptime if "rate(sysUpTime" in e]
        assert len(rated) >= 3, uptime

    def test_the_json_is_the_builders(self):
        import subprocess
        r = subprocess.run(["python3", os.path.join(ROOT, "deploy", "grafana", "build_nmas_device.py"),
                            "--check"], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_the_stats_with_a_physical_range_declare_it(self):
        ranges = {p["title"]: (p["fieldConfig"]["defaults"].get("min"), p["fieldConfig"]["defaults"].get("max"))
                  for p in _walk(_model()["panels"]) if p.get("type") == "stat"}
        assert ranges["Device clock rate"] == (0, 1.1)
        assert ranges["IOS CPU, 1-minute average"] == (0, 100)
        assert ranges["Memory used"] == (0, 100)
        assert ranges["Answering SNMP"] == (0, 1)
        # A count has no upper bound, so it declares none.
        assert ranges["Reboots detected"] == (None, None)


def _clock_panel():
    from modules.readers.grafana_dashboards import _panels
    return next(p for p in _panels(_model()) if p["title"] == "Device clock rate")


class TestTheAppDrawsWordsNeverTheNumber:
    def test_a_reading_outside_the_range_is_words(self):
        from modules import panels
        out = panels.render_payload(_clock_panel(), _answer([1000], [-24.75]), 3600)
        assert out["value"] is None
        assert out["implausible"]["words"] == "Not a valid reading (outside 0–110%): measuring"
        assert out["implausible"]["value"] == -24.75

    def test_a_reading_inside_the_range_is_the_number(self):
        from modules import panels
        out = panels.render_payload(_clock_panel(), _answer([1000], [0.557]), 3600)
        assert out["value"] == 0.557 and "implausible" not in out

    def test_a_panel_that_declares_no_range_is_never_judged(self):
        from modules import panels
        p = dict(_clock_panel(), min=None, max=None)
        out = panels.render_payload(p, _answer([1000], [-24.75]), 3600)
        assert out["value"] == -24.75 and "implausible" not in out

    def test_the_restart_is_found_where_sysuptime_dropped(self):
        from modules import panels
        # Ticks climbing, then a drop to 3000 (30 s of uptime) at t=1800.
        ans = _answer([0, 600, 1200, 1800, 2400], [100000, 133000, 166000, 3000, 36000], ref="R")
        assert panels.last_restart(ans) == 1800 - 30
        assert panels.last_restart(_answer([0, 600], [1, 2], ref="R")) is None


class TestThePanelRouteSaysWhenItRestarted:
    def test_the_words_name_the_restart_time(self, monkeypatch):
        from modules import device_page
        from tests.test_device_v2 import FakeGrafana, _store
        restart_at = 1_790_000_000 + 1800
        fake = FakeGrafana(answers={
            # The restart probe asks for the bare sysUpTime; checked first.
            'sysUpTime{device="s3"}': _answer([1_790_000_000, restart_at + 30], [180000, 3000], ref="R"),
            "rate(sysUpTime": _answer([restart_at + 60], [-24.75]),
        })
        fake.extra["nmas-device"] = _model()
        from modules.readers import grafana_dashboards
        _store("grafana-dashboards", grafana_dashboards.read(fake))
        monkeypatch.setattr(device_page, "device_dashboard_settings", lambda: {
            "uid": "nmas-device", "variable": "device", "value_from": "hostname"})
        pid = _clock_panel()["id"]
        payload, code = device_page.panel_data({"hostname": "s3", "ip": "192.0.2.23"}, "nmas-device",
                                               pid, "1h", client=fake)
        assert code == 200, payload
        assert payload["value"] is None
        import time as _t
        hhmm = _t.strftime("%H:%M", _t.gmtime(restart_at))       # the drop less its 30 s of uptime
        assert payload["implausible"]["words"] == f"Restarted about {hhmm} UTC: measuring", payload


class TestTheShippedClient:
    def _text(self, p, unit):
        js = open(os.path.join(ROOT, "static", "js", "nmas_panels.js"), encoding="utf-8").read()
        return json.loads(dukpy.evaljs("var window = {};\n" + js +
                                       f"\nJSON.stringify(window.NMAS_PANELS.statText({json.dumps(p)}, '{unit}'));"))

    def test_an_implausible_reading_is_drawn_as_its_words(self):
        out = self._text({"value": None, "implausible": {"words": "Restarted about 13:06 UTC: measuring",
                                                         "value": -24.75}}, "percentunit")
        assert out["text"] == "Restarted about 13:06 UTC: measuring"
        assert "-2475" not in json.dumps(out) and "stat-measuring" in out["cls"]

    def test_a_plausible_reading_is_the_number(self):
        out = self._text({"value": 0.557, "thresholds": []}, "percentunit")
        assert out["text"].startswith("55.7") and "stat-measuring" not in out["cls"]
