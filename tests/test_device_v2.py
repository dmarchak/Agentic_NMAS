"""The redesign's device page (the spike, NSOT_GUI_BRIEF 9b), Overview and
Monitoring, through the real app with real captures:

- the dashboard model is `rcn-lab1-snmp` as Grafana returned it (the panel
  FILTERING fixture: the ORIGINAL device dashboard, not this lab's, which is
  `nmas-device`; see TestTheLabsDeviceDashboard), stored by the
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
    """Serves the captured search, the three captured models (`rcn-lab1-snmp`,
    the panel-FILTERING fixture; `rcn-lab-overview`, this lab's FLEET dashboard;
    `nmas-device`, its DEVICE dashboard; every
    other dashboard a minimal model with no device variable), the captured
    data sources, the label values it is told, and query answers by panel."""

    def __init__(self, label_values=None, answers=None, fail_query=""):
        self.label_values = label_values if label_values is not None else ["r1", "r3"]
        self.answers = answers or {}
        self.fail_query = fail_query
        self.queries = []
        self.gets = []
        # Rule 11: a dashboard Grafana holds that the STORED list predates
        # (the operator's import of nmas-device), and Grafana unreachable.
        self.extra = {}
        self.dashboards_down = False
        # Dashboards imported after the search capture (2026-09-29): nmas-device.
        self.more_search = []

    def _get(self, path, **params):
        self.gets.append((path, params))
        if path == "api/search":
            return {"ok": True, "response": _Resp(_fixture("dashboards", "search.json") + self.more_search)}
        if path.startswith("api/dashboards/uid/"):
            uid = path.rsplit("/", 1)[-1]
            if self.dashboards_down:
                return {"ok": False, "error": "Could not connect to the Grafana URL"}
            titles = {d["uid"]: d["title"] for d in _fixture("dashboards", "search.json")}
            if uid in self.extra:
                model = self.extra[uid]
            elif uid in ("rcn-lab1-snmp", "rcn-lab-overview", "nmas-device"):
                model = _fixture("dashboards", f"{uid}.json")
            elif uid in titles:
                model = {"title": titles[uid], "panels": [], "templating": {"list": []}}
            else:
                return {"ok": False, "error": "HTTP 404", "status": 404}          # as Grafana answers
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


# The panel-FILTERING fixture, not this lab's device dashboard (CLAUDE.md, "Standing
# facts"): `rcn-lab1-snmp` was the ORIGINAL device dashboard, and its real model
# selects the device in 4 of its 8 panels, the contrast these tests are about.
# This lab's device dashboard is `nmas-device` (TestTheLabsDeviceDashboard).
FILTERING_FIXTURE = "rcn-lab1-snmp"
SETTINGS = {"grafana_device_dashboard_uid": FILTERING_FIXTURE, "grafana_device_variable": "device",
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


def _get_json(lab, url):
    r = lab["client"].get(url)
    return r.status_code, r.get_json()


def _text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _with_nmas_device(lab):
    """This lab's DEVICE dashboard: `nmas-device`'s model as Grafana returned it
    on 2026-10-01 (read-only), listed by the search and stored by the real reader."""
    from modules.readers import grafana_dashboards

    lab["fake"].more_search = [{"type": "dash-db", "uid": "nmas-device", "title": "NMAS device"}]
    _store("grafana-dashboards", grafana_dashboards.read(lab["fake"]))
    lab["settings"]["grafana_device_dashboard_uid"] = "nmas-device"


class TestTheLabsDeviceDashboard:
    """The DEVICE role's real dashboard (CLAUDE.md, "Standing facts"): every one
    of nmas-device's 27 panels selects the device, so the device page draws
    them all and leaves none out, unlike the filtering fixture's 4 of 8."""

    def test_every_panel_is_drawn_or_folded_and_none_left_out(self, lab):
        _with_nmas_device(lab)
        _r, html = _get(lab, "/v2/device/r3/monitoring")
        drawn = re.findall(r'data-panel-src="/v2/device/r3/panel/nmas-device/(\d+)', html)
        model = _fixture("dashboards", "nmas-device.json")
        ids = {p["id"] for p in model["panels"] if p["type"] != "row"}
        assert len(ids) == 27 and set(map(int, drawn)) <= ids and len(drawn) >= 20
        folded = len(ids) - len(drawn)
        assert "left out" not in _text(html)
        assert folded == 0 or re.search(rf"\b{folded} panel", _text(html)), "a missing panel must be a stated fold"
        assert "Grafana draws it, this page does not" not in html      # every panel is native

    def test_a_panel_reads_the_device_through_its_own_query(self, lab):
        _with_nmas_device(lab)
        _r, html = _get(lab, "/v2/device/r3/monitoring")
        src = re.findall(r'data-panel-src="([^"]+)"', html)[0].replace("&amp;", "&")
        code, body = _get_json(lab, src)
        assert code == 200 and "read_at" in body
        assert any("r3" in q["queries"][0]["expr"] for q in lab["fake"].queries)


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
        # Overview, Intent, History, Logs, NetBox and Neighbours (step 4,
        # 2026-10-01) and Monitoring are built; Ask the device is not.
        tabs = html[html.index('role="tablist"'):html.index('id="tab-body"')]
        assert tabs.count('aria-disabled="true"') == 1

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

    def test_an_unreadable_startup_check_says_it_will_read_it_again(self, lab, monkeypatch):
        """The 06:03 run (2026-10-01): an unreadable device is not a startup
        config that lacks the credential, and its reason arrives without
        Netmiko's paragraph of advice."""
        from modules.nsot import startup_check

        monkeypatch.setattr(startup_check, "read_results", lambda: {"at": 1.0, "devices": [
            {"list": "Lab", "device": "r3", "state": "unknown", "detail":
             "could not ask: ReadTimeout: \n\nPattern not detected: 'terminal width 511' "
             "in output.\n\nThings you might try to fix this:\n1. Explicitly set ..."}]})
        text = _text(_get(lab, "/v2/device/r3/overview")[1])
        assert "the hourly check could not read it" in text
        assert "it reads it again at the next run" in text
        assert "Things you might try" not in text
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

    def test_a_uid_grafana_does_not_hold_is_named_on_its_live_answer(self, lab):
        lab["settings"]["grafana_device_dashboard_uid"] = "gone-uid"
        _, html = _get(lab, "/v2/device/r3/monitoring")
        assert "Grafana holds no dashboard with UID" in html and "gone-uid" in html
        assert "asked now" in html
        assert ("api/dashboards/uid/gone-uid", {}) in lab["fake"].gets          # it was ASKED

    def test_a_uid_the_stored_list_predates_is_drawn_never_called_gone(self, lab):
        """The operator's case (2026-09-30): nmas-device imported after the
        stored list was read. Grafana is asked, and the dashboard is drawn."""
        model = dict(_fixture("dashboards", "rcn-lab1-snmp.json"), title="NMAS device", uid="nmas-device")
        lab["fake"].extra["nmas-device"] = model
        lab["settings"]["grafana_device_dashboard_uid"] = "nmas-device"
        _, html = _get(lab, "/v2/device/r3/monitoring")
        assert "Grafana holds no dashboard" not in html
        assert "data-panel-src" in html and "Read from Grafana now" in html and "predates" in html
        code, body = _get_json(lab, "/v2/device/r3/panel/nmas-device/2")
        assert code == 200 and body.get("ok"), body

    def test_grafana_unreachable_is_not_confirmed_never_gone(self, lab):
        lab["fake"].dashboards_down = True
        lab["settings"]["grafana_device_dashboard_uid"] = "maybe-uid"
        _, html = _get(lab, "/v2/device/r3/monitoring")
        assert "Grafana holds no dashboard" not in html
        assert "could not be asked now" in html and "Whether it exists is not known" in html
        code, body = _get_json(lab, "/v2/device/r3/panel/maybe-uid/2")
        assert code == 503 and "could not be asked now" in body["error"]

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

    def test_no_note_sits_under_the_range_controls(self, lab):
        """2026-10-02: retention and step are on the controls' hover and behind the (i)."""
        _, html = _get(lab, "/v2/device/r3/monitoring")
        assert "Prometheus serves up to" not in html and "Dashboards read" not in html
        assert re.search(r'<div class="seg" role="group" aria-label="Time range" '
                         r'title="The live store keeps 90 days\. Step \d+ s for ', html)
        assert 'data-manual="monitoring#time-range"' in html

    def test_a_range_past_the_limit_is_refused_naming_it_never_trimmed(self, lab):
        _, html = _get(lab, "/v2/device/r3/monitoring?range=last+120d")
        # Said AT the control where it was typed (2026-10-02), naming the limit and the range.
        form = re.search(r'<form class="range-custom".*?</form>', html, re.S).group(0)
        assert 'aria-invalid="true" aria-describedby="range-in-err"' in form
        assert re.search(r'<p class="range-refused" id="range-in-err" role="alert">.*?'
                         r"Refused: the live store keeps 90 days, and no history store is set \(grafana_history_datasource_uid\); this range is 120 days\.", form, re.S)
        assert "data-panel-src" not in html and "notice-warn" not in html

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
        """Drawn as Grafana draws it: the panel's own `organize` step drops
        the columns it excludes and renames the rest (Value is State), and the
        State column carries the panel's value mapping (1 up, 2 down)."""
        code, p = self._panel(lab, 3)
        assert code == 200 and p["type"] == "table" and p["rows"]
        assert p["columns"] == ["Description", "Interface", "State"]
        state = p["column_mappings"][2]
        assert state[0]["type"] == "value" and state[0]["options"]["1"]["text"] == "up"
        assert p["column_mappings"][:2] == [[], []]

    def test_a_panel_with_no_organize_step_keeps_its_columns(self):
        from modules import panels

        panel = {"type": "table", "targets": [{"refId": "A"}]}
        answer = {"results": {"A": {"frames": [{"schema": {"fields": [
            {"name": "Time"}, {"name": "Value", "labels": {"ifName": "Gi1", "device": "r3"}}]},
            "data": {"values": [[1], [1]]}}]}}}
        p = panels.render_payload(panel, answer, 3600)
        assert p["columns"][-1] == "value" and p["column_mappings"][-1] == []

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
        with pytest.raises(panels.RangeRefused, match=r"the live store keeps 90 days, and no history store is set \(grafana_history_datasource_uid\); this range is 91 days"):
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

    def test_the_keys_it_wires_are_in_the_vocabulary_and_each_is_heard(self, lab, monkeypatch):
        from modules import deploy_job, invalidation

        keys = json.loads(_eval("nmas_v2.js", "NMAS_V2", "KEYS"))
        assert keys and set(keys) <= set(invalidation.VOCABULARY)
        # A batch apply RUNNING (P.9 d2) listens for its job's announcements.
        monkeypatch.setattr(deploy_job, "state", lambda job: {
            "job": job, "state": "running", "order": ["r3"], "elapsed_s": 1, "payload": None,
            "error": "", "steps": [{"device": "r3", "state": "running", "took_s": 1}]})
        # The device page's Capture card READING (7.3) listens for its preview job, the
        # Rotate card ROTATING for its job, and a card refused because its device is held for
        # the hold's release.
        from modules.nsot import capture_job, device_ops
        monkeypatch.setattr(capture_job, "get", lambda job: {"state": "running", "elapsed_s": 1})
        monkeypatch.setattr(device_ops, "busy_text", lambda l, h: "r3 is being deployed to")
        heard = " ".join(_get(lab, u)[1] for u in ("/v2/device/r3", "/v2/device/r3/overview",
                                                    "/v2/device/r3/monitoring", "/v2/attention",
                                                    "/v2/help/installation",
                                                    "/v2/monitoring/coverage/table",
                                                    "/v2/monitoring/apply/job/x",
                                                    "/v2/device/r3/capture/job/x",
                                                    "/v2/device/r3/rotate/job/x"))
        from modules import device_page
        from modules.nsot import rotate_op
        from routes import device_v2
        monkeypatch.setattr(rotate_op, "plan", lambda l, h: {"ok": False, "device": h,
                                                             "list_name": l, "error": "x"})
        # This lab's list is in no registry, which a write path refuses: here only the card's
        # listener is asked for, so the device is found as the page finds it.
        monkeypatch.setattr(device_v2, "_named_device",
                            lambda n, l, t="": (*device_page.find_device(n), None))
        heard += lab["client"].post("/v2/device/r3/rotate/preview",
                                    data={"list": "Lab"}).get_data(as_text=True)
        # +6 2026-10-02: every key attention.SOURCE_KEYS names; +1 capture_preview (7.3);
        # +2 2026-10-03: rotation and device_holds (7.3's rotate card); +1 device_progress
        # (C370: a running job's stepper); +1 credential_health (P.21's reader, on Needs
        # attention); +1 coverage_reporting (Coverage's not-reporting reader).
        assert len(keys) == 30
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


# ------------------------------------------------ the spike review's fixes

TEAM = "example-team.cloudflareaccess.com"
AUD = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
TUNNEL = "192.0.2.21"


@pytest.fixture(scope="module")
def signing_key():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def access(monkeypatch, signing_key):
    """Cloudflare Access configured, verifying against a key this test holds:
    the REAL `identify()` runs (the module's tests opt out of the harness's
    stand-in person with `real_identity`)."""
    from modules import identity

    values = {"cf_access_team_domain": TEAM, "cf_access_aud": AUD,
              "cf_access_trusted_peers": TUNNEL}
    monkeypatch.setattr(identity, "_setting", lambda key, default=None: values.get(key, default))

    class _Key:
        key = signing_key.public_key()

    class _Client:
        def get_signing_key_from_jwt(self, token):
            return _Key()

    monkeypatch.setattr(identity, "_get_jwks_client", lambda: _Client())
    return values


def _assertion(key, email="operator@example.com"):
    import jwt
    now = int(time.time())
    return jwt.encode({"type": "app", "aud": AUD, "iss": f"https://{TEAM}", "email": email,
                       "iat": now, "exp": now + 600, "sub": "uuid-1"}, key, algorithm="RS256")


@pytest.mark.real_identity
class TestTheViewerIsTheVerifiedIdentity:
    """The spike drew every person as `unauthenticated` (the operator,
    2026-09-30): it read `request_actor()`, which answers only inside a GATED
    request, and a GET page is never gated. Now the page and every fragment
    draw `identity.viewer()`, the same `identify()` the gate and
    `/identity/status` (today's pages) call."""

    def _ask(self, lab, url, token=None, peer=TUNNEL):
        headers = {"Cf-Access-Jwt-Assertion": token} if token else {}
        r = lab["client"].get(url, headers=headers, environ_base={"REMOTE_ADDR": peer})
        return r.get_data(as_text=True)

    def test_the_page_and_a_fragment_draw_the_verified_person(self, lab, access, signing_key):
        token = _assertion(signing_key)
        for url in ("/v2/device/r3", "/v2/who"):
            html = self._ask(lab, url, token)
            assert 'data-identified="yes"' in html, url
            assert "operator@example.com" in html and "unauthenticated" not in html, url

    def test_it_agrees_with_the_path_todays_pages_use(self, lab, access, signing_key):
        token = _assertion(signing_key, email="second@example.com")
        status = lab["client"].get("/identity/status", headers={"Cf-Access-Jwt-Assertion": token},
                                   environ_base={"REMOTE_ADDR": TUNNEL}).get_json()
        assert status["is_identified"] and status["actor"] == "second@example.com"
        assert status["actor"] in self._ask(lab, "/v2/who", token)

    def test_no_assertion_is_refused_and_says_why(self, lab, access):
        for url in ("/v2/device/r3", "/v2/who"):
            html = html_mod.unescape(self._ask(lab, url))
            assert 'data-identified="no"' in html and "Not identified" in html, url
            assert "carried no Cf-Access-Jwt-Assertion header" in html, url

    def test_a_valid_assertion_from_an_untrusted_peer_is_refused(self, lab, access, signing_key):
        html = self._ask(lab, "/v2/who", _assertion(signing_key), peer="192.0.2.99")
        assert 'data-identified="no"' in html and "operator@example.com" not in html

    def test_the_old_path_would_have_drawn_unauthenticated(self, lab, access, signing_key):
        """The control: on the same verified request, `request_actor()` still
        answers `unauthenticated`, which is exactly what the chip showed."""
        import app as A
        from modules import identity

        with A.app.test_request_context("/v2/who", headers={
                "Cf-Access-Jwt-Assertion": _assertion(signing_key)},
                environ_base={"REMOTE_ADDR": TUNNEL}):
            assert identity.request_actor() == identity.UNAUTHENTICATED
            assert identity.viewer().actor == "operator@example.com"

    def test_no_v2_route_reads_the_gate_only_actor(self):
        src = open(os.path.join(ROOT, "routes", "device_v2.py"), encoding="utf-8").read()
        code = re.sub(r'""".*?"""', "", src, flags=re.S)
        assert "request_actor(" not in code and "identity.viewer()" in code


class TestTheModelAndPlatform:
    def _golden(self, name):
        return open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", f"{name}.cfg"),
                    encoding="utf-8").read()

    def test_the_model_is_read_from_the_committed_golden_with_its_basis(self):
        from modules import device_page as D

        assert D.model_from_golden(self._golden("r2")) == ("C8000V", "the golden's Chassis type line")
        model, basis = D.model_from_golden(self._golden("s1"))
        assert model == "vios_l2" and "image line" in basis and "no chassis model" in basis
        assert D.model_from_golden("hostname x\nlicense udi pid ISR4331/K9 sn X\n") == \
            ("ISR4331/K9", "the golden's license udi line")
        assert D.model_from_golden("hostname x\n")[0] == ""
        assert D.model_from_golden("")[1] == "no committed golden to read it from"

    def test_the_page_names_model_and_platform_and_where_each_came_from(self, lab, monkeypatch):
        import modules.device as device_mod

        rows = [dict(r, platform="cisco_iosxe") for r in device_mod.load_saved_devices("x")]
        monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: rows)
        text = html_mod.unescape(_get(lab, "/v2/device/r3")[1])
        assert "C8000V" in text and "cisco_iosxe" in text
        assert "from the golden's Chassis type line" in text and "from the inventory" in text

    def test_a_device_with_no_golden_says_so(self, lab):
        text = html_mod.unescape(_get(lab, "/v2/device/r9/overview")[1])
        assert "no committed golden to read it from" in text


class TestThePanelsFollowTheDashboardsLayout:
    def test_the_layout_is_the_dashboards_own_order_width_and_rows(self):
        from modules import panels

        dash = _fixture("dashboards", "rcn-lab1-snmp.json")
        from modules.readers import grafana_dashboards as G
        drawn, _ = panels.split_device_panels({"panels": G._panels(dash)}, "device")
        items = panels.layout(drawn)
        rows = [i["title"] for i in items if i["kind"] == "row"]
        placed = [(i["panel"]["id"], i["x"], i["w"], i["h"]) for i in items if i["kind"] == "panel"]
        assert rows == ["Fleet reachability", "$device"]
        # 102 keeps its place beside 101, which is left out; the device panels
        # are full width in Grafana too.
        assert placed == [(102, 12, 12, 6), (2, 0, 24, 9), (3, 0, 24, 9), (4, 0, 24, 7)]

    def test_rearranging_in_grafana_rearranges_the_page(self, lab):
        """A minimal edit of the real model: throughput and errors side by side
        at the top of the row, the rest where they were."""
        from modules import reader_job

        path = reader_job.store_path("grafana-dashboards")
        doc = json.load(open(path, encoding="utf-8"))
        for p in doc["last_good"]["value"]["dashboards"]["rcn-lab1-snmp"]["panels"]:
            if p["id"] == 2:
                p["gridPos"] = {"x": 0, "y": 8, "w": 12, "h": 9}
            if p["id"] == 4:
                p["gridPos"] = {"x": 12, "y": 8, "w": 12, "h": 9}
            if p["id"] == 3:
                p["gridPos"] = {"x": 0, "y": 17, "w": 24, "h": 15}
        json.dump(doc, open(path, "w", encoding="utf-8"))
        html = _get(lab, "/v2/device/r3/monitoring")[1]
        order = [(int(i), x, w) for x, w, i in re.findall(
            r'class="panel gx-(\d+) gw-(\d+)"[^>]*panel/rcn-lab1-snmp/(\d+)', html)]
        assert order == [(102, "12", "12"), (2, "0", "12"), (4, "12", "12"), (3, "0", "24")]
        assert '<h2 class="panel-row">r3</h2>' in html

    def test_a_panel_overhanging_the_grid_is_clamped_never_wrapped(self):
        from modules import panels

        items = panels.layout([{"id": 1, "gridPos": {"x": 20, "y": 0, "w": 12, "h": 2}}])
        assert (items[0]["x"], items[0]["w"], items[0]["h"]) == (20, 4, 3)

    def test_the_chart_height_follows_gridpos_h(self):
        out = json.loads(_eval("nmas_panels.js", "NMAS_PANELS",
                               "chartHeight ? [15, 7, 2, null].map(function (h) "
                               "{ return window.NMAS_PANELS.chartHeight(h); }) : 0"))
        assert out == [380, 140, 120, 170]

    def test_every_column_start_and_width_has_its_rule(self):
        css = open(os.path.join(ROOT, "static", "css", "nmas-v2.css"), encoding="utf-8").read()
        for i in range(24):
            assert f".gx-{i} {{ grid-column-start: {i + 1}; }}" in css
        for i in range(1, 25):
            assert f".gw-{i} {{ grid-column-end: span {i}; }}" in css
        assert ".panels > .panel, .panels > .panel-row { grid-column: 1 / -1; }" in css


class TestTheSelectorSaysWhyItOffersOne:
    def test_the_count_is_said_beside_it_and_the_rest_are_listed_with_why(self, lab):
        text = html_mod.unescape(_text(_get(lab, "/v2/device/r3/monitoring")[1]))
        assert "1 of 5 dashboards can show a single device" in text
        assert "Not offered: 4 dashboards that cannot show a single device" in text
        assert text.count("no variable named device") == 4
        assert "Node Exporter Full" in text


class TestValueMappings:
    """The operator (2026-09-30): "Yes" and "up" instead of 1, in the app,
    for every dashboard. Grafana's value, range and special kinds, from the
    REAL mappings in rcn-lab1-snmp (panel 104's defaults; panel 3's override
    on its renamed State field)."""

    REAL = [{"options": {"1": {"color": "green", "index": 0, "text": "Up"},
                         "2": {"color": "red", "index": 1, "text": "Down"},
                         "7": {"color": "yellow", "index": 2, "text": "Lower Layer Down"}},
             "type": "value"}]

    def _map(self, values, mappings):
        return json.loads(_eval("nmas_panels.js", "NMAS_PANELS",
                                f"mapValue ? {json.dumps(values)}.map(function (v) {{ "
                                f"return window.NMAS_PANELS.mapValue(v, {json.dumps(mappings)}); }}) : 0"))

    def test_the_real_value_mapping(self):
        assert self._map([1, 2, 7, "1", 1.0, 5], self.REAL) == [
            {"text": "Up", "kind": "ok"}, {"text": "Down", "kind": "danger"},
            {"text": "Lower Layer Down", "kind": "warn"}, {"text": "Up", "kind": "ok"},
            {"text": "Up", "kind": "ok"}, None]

    def test_range_and_special_and_none(self):
        m = [{"type": "range", "options": {"from": 0, "to": 0.5, "result": {"text": "No", "color": "red"}}},
             {"type": "range", "options": {"from": 0.5, "to": None, "result": {"text": "Yes", "color": "green"}}},
             {"type": "special", "options": {"match": "null", "result": {"text": "no data", "color": "text"}}}]
        assert self._map([0, 1, None], m) == [{"text": "No", "kind": "danger"}, {"text": "Yes", "kind": "ok"},
                                              {"text": "no data", "kind": ""}]
        assert self._map([1], []) == [None]

    def test_the_reader_keeps_the_real_mappings_and_the_organize_step(self):
        from modules.readers import grafana_dashboards as G

        dash = _fixture("dashboards", "rcn-lab1-snmp.json")
        got = {p["id"]: p for p in G._panels(dash) if p.get("type") != "row"}
        assert got[104]["mappings"] == self.REAL
        assert got[3]["field_mappings"]["State"][0]["options"]["2"]["text"] == "down"
        assert got[3]["organize"]["rename"] == {"Value": "State", "ifAlias": "Description", "ifName": "Interface"}
        assert "device" in got[3]["organize"]["exclude"]

    def test_the_drawing_uses_them(self):
        src = _js("nmas_panels.js")
        assert "mapValue(p.value, p.mappings)" in src                         # a stat
        assert "mapValue(p.rows[i][j], (p.column_mappings || [])[j])" in src  # a table cell
        assert "mapValue(v, p.mappings)" in src                               # a stepped axis
