"""The redesign's device page (the spike, NSOT_GUI_BRIEF 9b), Overview and
Monitoring, through the real app with real captures:

- the dashboard model is `rcn-lab1-snmp` as Grafana returned it, stored by the
  REAL `grafana_dashboards.read()` over a fake client serving the capture;
- the panel answers are real `api/ds/query` answers (`tests/fixtures/grafana/
  dsquery/`): throughput for r3 by its address, the interface-state table,
  and C232's empty answer for `device="r3"`;
- the golden is r2's real config, committed through `save_golden()`.

Every page and fragment carries the strict policy and no inline script or
style; each Monitoring state is drawn in its own words; only panels whose
queries select the device are drawn, and the rest are listed with why; a
panel's query is the dashboard's, never the browser's; the shipped scripts'
pure helpers are executed in duktape.
"""

import html as html_mod
import json
import os
import re
import time

import dukpy
import pytest

from tests.test_intent_match import R2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "grafana")


def _fixture(*parts):
    with open(os.path.join(FIX, *parts), encoding="utf-8") as fh:
        return json.load(fh)


class _Resp:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class FakeGrafana:
    """Serves the captured search, the captured `rcn-lab1-snmp` model (every
    other dashboard a minimal model with no device variable), the captured
    data sources, the label values it is told, and query answers by panel."""

    def __init__(self, label_values=None, answers=None, fail_query=""):
        self.label_values = label_values if label_values is not None else ["r1", "r3"]
        self.answers = answers or {}
        self.fail_query = fail_query
        self.queries = []
        self.gets = []

    def _get(self, path, **params):
        self.gets.append((path, params))
        if path == "api/search":
            return {"ok": True, "response": _Resp(_fixture("dashboards", "search.json"))}
        if path.startswith("api/dashboards/uid/"):
            uid = path.rsplit("/", 1)[-1]
            if uid == "rcn-lab1-snmp":
                model = _fixture("dashboards", "rcn-lab1-snmp.json")
            else:
                model = {"title": f"Dashboard {uid}", "panels": [], "templating": {"list": []}}
            return {"ok": True, "response": _Resp({"dashboard": model})}
        if path == "api/frontend/settings":
            ds = _fixture("dashboards", "datasources.json")
            return {"ok": True, "response": _Resp({
                "defaultDatasource": next(d["name"] for d in ds if d["is_default"]),
                "datasources": {d["name"]: {"uid": d["uid"], "type": d["type"]} for d in ds}})}
        if "/api/v1/label/" in path:
            return {"ok": True, "response": _Resp({"status": "success", "data": self.label_values})}
        return {"ok": False, "error": f"unexpected {path}"}

    def query(self, body):
        self.queries.append(body)
        if self.fail_query:
            return {"ok": False, "error": self.fail_query}
        expr = body["queries"][0]["expr"]
        for needle, answer in self.answers.items():
            if needle in expr:
                return {"ok": True, "body": answer}
        return {"ok": True, "body": {"results": {}}}


def _store(name, value, at="2026-09-30T10:00:00Z"):
    from modules import reader_job

    path = reader_job.store_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"last_good": {"value": value, "value_at": at}}, fh)


def _unstore(name):
    from modules import reader_job

    try:
        os.remove(reader_job.store_path(name))
    except FileNotFoundError:
        pass


SETTINGS = {"grafana_device_dashboard_uid": "rcn-lab1-snmp", "grafana_device_variable": "device",
            "grafana_device_variable_value": "hostname",
            "nsot_git_author_name": "NMAS", "nsot_git_author_email": "nmas@localhost"}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """The real app; a list 'Lab' holding r3 (with r2's real config as its
    committed golden) and r9 (nothing committed); the dashboards stored by the
    real reader over the fake client."""
    import app as A
    from modules import device_page
    from modules.nsot.repo import GoldenItem, save_golden
    from modules.readers import grafana_dashboards

    list_dir = tmp_path / "lab"
    os.makedirs(list_dir / "config_repo", exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    settings = dict(SETTINGS)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: settings.get(key, default))
    devices = [{"hostname": "r3", "ip": "10.255.1.13", "device_type": "cisco_xe", "username": "nmas"},
               {"hostname": "r9", "ip": "192.0.2.9", "device_type": "cisco_ios", "username": "nmas"}]
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(d) for d in devices])
    save_golden("Lab", [GoldenItem("r3", open(R2, encoding="utf-8").read(), "10.255.1.13",
                                   platform="cisco_iosxe")],
                source="capture", actor="operator@example.com", allow_new=True, baseline=False)
    fake = FakeGrafana(answers={
        "rate(ifHCInOctets": _fixture("dsquery", "throughput.json")["answer"],
        "ifOperStatus": _fixture("dsquery", "state.json")["answer"]})
    monkeypatch.setattr("modules.integrations.grafana.GrafanaIntegration", lambda *a, **k: fake)
    device_page._VALUES_CACHE.clear()
    _store("grafana-dashboards", grafana_dashboards.read(fake))
    _store("reachability", {"devices": {"10.255.1.13": {
        "answering": True, "since": "2026-09-30T08:00:00Z", "checked_at": "2026-09-30T10:00:00Z",
        "last_result": "answered"}}})
    yield {"client": A.app.test_client(), "fake": fake, "settings": settings,
           "repo": str(list_dir / "config_repo")}
    for name in ("grafana-dashboards", "reachability", "freshness", "grafana-alerts", "integrations"):
        _unstore(name)


def _get(lab, url):
    r = lab["client"].get(url)
    return r, r.get_data(as_text=True)


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ---------------------------------------------------------------- the policy

class TestThePolicyIsStrict:
    URLS = ["/v2/device/r3", "/v2/device/r3?tab=monitoring", "/v2/device/r3/overview",
            "/v2/device/r3/monitoring", "/v2/device/r3/status", "/v2/strip", "/v2/device/nope"]

    def test_every_page_and_fragment_carries_the_strict_policy(self, lab):
        from modules import csp

        for url in self.URLS:
            r, _ = _get(lab, url)
            assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY, url
        assert "'unsafe-inline'" not in csp.STRICT_POLICY and "unsafe-eval" not in csp.STRICT_POLICY

    def test_no_inline_script_or_style_or_handler_is_rendered(self, lab):
        for url in self.URLS:
            _, html = _get(lab, url)
            assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), url
            assert not re.search(r"\sstyle=", html), url
            assert not re.search(r"\son[a-z]+=", html), url
            assert "<style" not in html, url

    def test_the_scan_sees_an_inline_style_when_there_is_one(self):
        # The floor: the patterns above find what they are for.
        assert re.search(r"\sstyle=", '<div style="x">') and re.search(r"\son[a-z]+=", '<a onclick="x">')
        assert re.search(r"<script(?![^>]*\bsrc=)[^>]*>", "<script>alert(1)</script>")
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", '<script defer src="/a.js"></script>')

    def test_every_script_and_stylesheet_the_page_loads_is_served_by_the_app(self, lab):
        _, html = _get(lab, "/v2/device/r3")
        refs = re.findall(r'(?:src|href)="(/static/[^"?]+)', html)
        assert len(refs) >= 8
        for ref in refs:
            assert os.path.exists(os.path.join(ROOT, ref.lstrip("/"))), ref


# ------------------------------------------------------------------- the page

class TestThePage:
    def test_it_names_the_device_its_status_and_the_built_tabs(self, lab):
        r, html = _get(lab, "/v2/device/r3")
        assert r.status_code == 200
        text = _text(html)
        assert "r3" in text and "Answering" in text and "10.255.1.13" in text
        assert 'hx-get="/v2/device/r3/overview"' in html and 'hx-get="/v2/device/r3/monitoring"' in html
        assert text.count("Not in the spike") == 0          # a title, not text
        assert html.count('aria-disabled="true"') == 6

    def test_an_unknown_device_is_a_404_naming_it_and_the_list(self, lab):
        r, html = _get(lab, "/v2/device/nope")
        assert r.status_code == 404
        assert "no device named 'nope' in the list 'Lab'" in html_mod.unescape(html)

    def test_a_name_is_matched_exactly_never_by_prefix(self, lab):
        assert _get(lab, "/v2/device/r")[0].status_code == 404
        assert _get(lab, "/v2/device/R3")[0].status_code == 200

    def test_the_status_refetches_on_the_reachability_announcement(self, lab):
        _, html = _get(lab, "/v2/device/r3/status")
        assert 'hx-trigger="nmas:reachability from:body"' in html

    def test_a_device_the_reader_has_no_row_for_is_not_probed_yet(self, lab):
        _, html = _get(lab, "/v2/device/r9/status")
        assert "Not probed yet" in html and "Answering" not in html


# --------------------------------------------------------------- Overview

class TestOverview:
    def test_the_golden_is_its_commit_and_absent_intent_is_said(self, lab):
        from modules.nsot import repo as R

        _, html = _get(lab, "/v2/device/r3/overview")
        sha = R.git(lab["repo"], "log", "-1", "--format=%h", "--", "golden/r3.cfg")[1].strip()
        assert sha and sha in html
        text = _text(html)
        assert "capture" in text and "operator@example.com" in text
        assert "none committed · nothing declares what it should look like" in text

    def test_each_check_is_drawn_and_an_absent_source_is_unknown_never_a_pass(self, lab):
        _, html = _get(lab, "/v2/device/r3/overview")
        for name in ("Drift", "Freshness", "Reboot-safe", "Alerts"):
            assert f"<strong>{name}</strong>" in html
        assert html.count("check check-ok") == 0
        assert "no drift run recorded for this list" in html

    def test_an_unapproved_copy_and_a_firing_alert_are_danger(self, lab):
        _store("freshness", {"lists": {"Lab": {"devices": [{"device": "r3", "verdict": "unapproved"}]}}})
        _store("grafana-alerts", {"instances": [
            {"kind": "condition", "rule": "Device unreachable", "address": "10.255.1.13"},
            {"kind": "condition", "rule": "Another device's", "device": "r1"}]})
        _, html = _get(lab, "/v2/device/r3/overview")
        assert html.count("check check-danger") == 2
        assert "a change nobody approved" in html and "Device unreachable" in html
        assert "Another device" not in html

    def test_it_refetches_when_a_reader_it_draws_from_announces(self, lab):
        _, html = _get(lab, "/v2/device/r3/overview")
        for key in ("reachability", "alerts", "freshness", "drift"):
            assert f"nmas:{key} from:body" in html


# -------------------------------------------------------------- Monitoring

class TestMonitoringStates:
    def test_the_panels_drawn_are_those_that_select_the_device(self, lab):
        from modules import panels

        _, html = _get(lab, "/v2/device/r3/monitoring")
        dash = _fixture("dashboards", "rcn-lab1-snmp.json")
        expected = []
        for p in dash["panels"]:           # independently of panels.py: the raw model
            exprs = " ".join(t.get("expr") or "" for t in p.get("targets") or [])
            if p["type"] != "row" and re.search(r"\$\{?device\b", exprs):
                expected.append(p["id"])
        assert len(expected) == 4
        drawn = [int(x) for x in re.findall(r'/panel/rcn-lab1-snmp/(\d+)', html)]
        assert sorted(drawn) == sorted(expected)
        assert panels.uses_variable('x{device=~"$device"}', "device")

    def test_the_rest_are_listed_with_why(self, lab):
        _, html = _get(lab, "/v2/device/r3/monitoring")
        text = _text(html)
        assert "panels left out: their queries do not select by device" in text
        for title in ("Devices online", "Devices offline", "LinkDown Logs"):
            assert title in text

    def test_the_selector_offers_only_dashboards_with_the_variable(self, lab):
        _, html = _get(lab, "/v2/device/r3/monitoring")
        offered = re.findall(r'role="option"[^>]*>\s*<span class="grow">([^<]+)', html)
        assert offered == ["RCN Lab 1 - SNMP per device"]
        assert "1 of the 5 Grafana holds" in _text(html)

    def test_a_dashboard_with_no_device_variable_draws_nothing_and_says_why(self, lab):
        _, html = _get(lab, "/v2/device/r3/monitoring?dashboard=rcn-lab-overview")
        text = _text(html)
        assert "cannot be filtered to one device" in text and "None are drawn" in text
        assert "data-panel-src" not in html

    def test_no_dashboard_set_names_the_setting(self, lab):
        lab["settings"]["grafana_device_dashboard_uid"] = ""
        _, html = _get(lab, "/v2/device/r3/monitoring")
        assert "No device dashboard is set for this network" in html
        assert "Device dashboard UID" in html

    def test_a_uid_grafana_does_not_hold_is_named(self, lab):
        lab["settings"]["grafana_device_dashboard_uid"] = "gone-uid"
        _, html = _get(lab, "/v2/device/r3/monitoring")
        assert "Grafana holds no dashboard with UID" in html and "gone-uid" in html

    def test_dashboards_not_read_yet_is_its_own_state(self, lab):
        _unstore("grafana-dashboards")
        _, html = _get(lab, "/v2/device/r3/monitoring")
        assert "have not been read yet" in html and "data-panel-src" not in html

    def test_a_variable_listing_nothing_is_c232_named_never_a_blank(self, lab):
        lab["fake"].label_values = []
        _, html = _get(lab, "/v2/device/r3/monitoring")
        text = _text(html)
        assert "lists no devices at all" in text and "C232" in text
        assert "data-panel-src" in html            # the panels still try

    def test_a_device_the_variable_does_not_list_is_named(self, lab):
        lab["fake"].label_values = ["r1", "r2"]
        _, html = _get(lab, "/v2/device/r3/monitoring")
        assert "Prometheus holds no series for r3" in _text(html)

    def test_a_listed_device_draws_no_warning(self, lab):
        _, html = _get(lab, "/v2/device/r3/monitoring")
        assert "notice-warn" not in html

    def test_a_range_past_the_limit_is_refused_naming_it_never_trimmed(self, lab):
        _, html = _get(lab, "/v2/device/r3/monitoring?range=last+120d")
        text = _text(html)
        assert "That range is refused" in text and "90 days" in text
        assert "data-panel-src" not in html

    def test_a_custom_range_is_carried_into_every_panel_url(self, lab):
        _, html = _get(lab, "/v2/device/r3/monitoring?range=last+3d")
        srcs = re.findall(r'data-panel-src="([^"]+)"', html)
        assert srcs and all("range=last+3d" in s or "range=last%203d" in s for s in srcs)


class TestPanelData:
    def _panel(self, lab, pid, rng="1h"):
        r = lab["client"].get(f"/v2/device/r3/panel/rcn-lab1-snmp/{pid}?range={rng}")
        return r.status_code, r.get_json()

    def test_a_time_series_is_drawn_from_the_real_answer(self, lab):
        code, p = self._panel(lab, 2)
        assert code == 200 and p["ok"] and p["type"] == "timeseries" and p["unit"] == "bps"
        assert p["series"] and all(len(s["times"]) == len(s["values"]) for s in p["series"])
        # The dashboard's own legend ("in  {{ifName}}  {{ifAlias}}") filled from the labels.
        assert all(s["label"].startswith(("in ", "out ")) and "{{" not in s["label"] for s in p["series"])

    def test_the_query_is_the_dashboards_with_the_device_filled(self, lab):
        self._panel(lab, 2)
        sent = lab["fake"].queries[-1]["queries"]
        dash = _fixture("dashboards", "rcn-lab1-snmp.json")
        model = next(p for p in dash["panels"] if p["id"] == 2)
        exclude = next(v for v in dash["templating"]["list"] if v["name"] == "exclude")["current"]["value"]
        assert [q["expr"] for q in sent] == [t["expr"].replace("$device", "r3").replace("$exclude", exclude)
                                             for t in model["targets"]]
        assert all("$__rate_interval" in q["expr"] for q in sent)     # Grafana's own, left for Grafana
        assert lab["fake"].queries[-1]["from"] == "now-3600s"

    def test_the_table_is_rows_from_the_instant_answer(self, lab):
        code, p = self._panel(lab, 3)
        assert code == 200 and p["type"] == "table" and p["rows"] and "value" in p["columns"]

    def test_an_empty_answer_is_an_empty_series_list_the_page_names(self, lab):
        lab["fake"].answers = {"rate(ifHCInOctets": _fixture("dsquery", "empty_device.json")["answer"]}
        code, p = self._panel(lab, 2)
        assert code == 200 and p["series"] == []

    def test_a_panel_that_does_not_select_the_device_is_refused(self, lab):
        code, p = self._panel(lab, 101)
        assert code == 404 and "not a device panel" in p["error"]

    def test_a_refused_range_and_a_grafana_failure_each_say_so(self, lab):
        code, p = self._panel(lab, 2, "last+200d")
        assert code == 400 and "90 days" in p["error"]
        lab["fake"].fail_query = "HTTP 500 from Grafana"
        code, p = self._panel(lab, 2)
        assert code == 502 and "HTTP 500 from Grafana" in p["error"]

    def test_the_range_chosen_is_the_range_asked(self, lab):
        from modules import panels

        for rng, seconds in (("1h", 3600), ("last+3d", 259200), ("7d", 604800)):
            self._panel(lab, 2, rng)
            q = lab["fake"].queries[-1]
            assert q["from"] == f"now-{seconds}s", rng
            assert q["queries"][0]["intervalMs"] == panels.step_for(seconds) * 1000, rng   # the step widens

    def test_nothing_a_browser_sends_reaches_the_query(self, lab):
        lab["client"].get("/v2/device/r3/panel/rcn-lab1-snmp/2?range=1h&expr=up&device=r1")
        assert all("r1" not in q["expr"] and q["expr"] != "up" for q in lab["fake"].queries[-1]["queries"])


class TestRanges:
    def test_presets_and_relative_ranges_read_as_seconds(self):
        from modules import panels

        assert [panels.parse_range(t) for t in ("1h", "last 90 minutes", "3d", "last 2 hours", "")] \
            == [3600, 5400, 259200, 7200, 3600]

    @pytest.mark.parametrize("text", ["yesterday", "last 0d", "-3d", "3 weeks", "1h; drop"])
    def test_anything_else_is_refused_by_name(self, text):
        from modules import panels

        with pytest.raises(panels.RangeRefused, match="is not a range"):
            panels.parse_range(text)

    def test_the_limit_refuses_past_it_and_passes_at_it(self):
        from modules import panels

        panels.check_range(90 * 86400, "prometheus")
        with pytest.raises(panels.RangeRefused, match="Prometheus keeps 90 days; this range is 91 days"):
            panels.check_range(91 * 86400, "prometheus")
        with pytest.raises(panels.RangeRefused, match="30 days 1 hour"):
            panels.check_range(31 * 86400, "loki")

    def test_the_step_keeps_a_series_under_its_point_bound(self):
        from modules import panels

        for seconds in (900, 3600, 86400, 7 * 86400, 90 * 86400):
            step = panels.step_for(seconds)
            assert step >= 15 and seconds / step <= panels.MAX_POINTS, seconds


# ------------------------------------------------------------ the scripts

def _js(name):
    with open(os.path.join(ROOT, "static", "js", name), encoding="utf-8") as fh:
        return fh.read()


def _eval(name, api, expr):
    return dukpy.evaljs("var window = {};\n" + _js(name) + f"\nJSON.stringify(window.{api}.{expr});")


class TestTheShippedScripts:
    def test_a_value_is_formatted_in_its_unit(self):
        out = json.loads(_eval("nmas_panels.js", "NMAS_PANELS",
                               "formatValue ? [[1234567, 'bps'], [42.123, 'percent'], [null, 'bps'], [0, 'pps']]"
                               ".map(function (a) { return window.NMAS_PANELS.formatValue(a[0], a[1]); }) : 0"))
        assert out == ["1.23 Mb/s", "42.1%", "-", "0 p/s"]

    def test_series_are_aligned_with_gaps_left_null_never_zero(self):
        out = json.loads(_eval("nmas_panels.js", "NMAS_PANELS",
                               "alignSeries([{times: [1, 2, 3], values: [5, 6, 7]}, {times: [2, 4], values: [8, 9]}])"))
        assert out == [[1, 2, 3, 4], [5, 6, 7, None], [None, 8, None, 9]]

    def test_a_stat_takes_the_kind_of_the_last_step_it_reaches(self):
        steps = json.dumps([{"color": "red", "value": None}, {"color": "orange", "value": 1},
                            {"color": "green", "value": 9}])
        out = json.loads(_eval("nmas_panels.js", "NMAS_PANELS",
                               f"thresholdKind ? [0, 3, 9].map(function (v) {{ return window.NMAS_PANELS.thresholdKind(v, {steps}); }}) : 0"))
        assert out == ["danger", "warn", "ok"]

    def test_an_age_reads_in_words(self):
        out = json.loads(_eval("nmas_v2.js", "NMAS_V2",
                               "ageWords ? [0, 30, 600, 7200, 259200].map(function (s) "
                               "{ return window.NMAS_V2.ageWords(1e6, 1e6 + s * 1000); }) : 0"))
        assert out == ["just now", "just now", "10 min ago", "2 h ago", "3 d ago"]

    def test_the_jump_box_goes_to_the_device_by_name_and_nowhere_when_empty(self):
        out = json.loads(_eval("nmas_v2.js", "NMAS_V2",
                               "jumpTarget ? [window.NMAS_V2.jumpTarget('/v2/device/', ' r3 '), "
                               "window.NMAS_V2.jumpTarget('/v2/device/', 'a/b'), "
                               "window.NMAS_V2.jumpTarget('/v2/device/', '  ')] : 0"))
        assert out == ["/v2/device/r3", "/v2/device/a%2Fb", ""]

    def test_the_keys_it_wires_are_in_the_vocabulary_and_each_is_heard(self, lab):
        from modules import invalidation

        keys = json.loads(_eval("nmas_v2.js", "NMAS_V2", "KEYS"))
        assert keys and set(keys) <= set(invalidation.VOCABULARY)
        heard = " ".join(_get(lab, u)[1] for u in ("/v2/device/r3", "/v2/device/r3/overview",
                                                    "/v2/device/r3/monitoring"))
        assert len(keys) == 6
        for key in keys:
            assert f"nmas:{key} from:body" in heard, key
        src = _js("nmas_v2.js")
        for key in keys:        # each written out, so the subscription scan reads it
            assert re.search(r"^\s*NMAS\.subscribe\('%s'" % key, src, re.M), key

    def test_the_dashboards_reader_announces_a_change_and_not_a_read_time(self):
        from modules.readers import grafana_dashboards as G

        a = {"dashboards": {"x": {"title": "X"}}, "datasources": [], "read_at": 1}
        assert not G.changed(a, dict(a, read_at=2))
        assert G.changed(a, dict(a, dashboards={"x": {"title": "Y"}}))
        assert G.READER.announce_at_least_every == G.KEEPALIVE_SECONDS > 0

    def test_a_data_value_reaches_the_screen_as_text_never_markup(self):
        src = _js("nmas_panels.js")
        # Comments stripped: the file's own header explains the rule and names it.
        code = re.sub(r"/\*.*?\*/|//[^\n]*", "", src, flags=re.S)
        assert "innerHTML" in src and "innerHTML" not in code and "insertAdjacentHTML" not in code
        assert "textContent" in src
