"""Monitoring opens on the FLEET dashboard (the operator, 2026-10-01, as
NSOT_GUI_BRIEF 14.2 agreed): a per-network setting names it by UID, the page's
selector lists every dashboard Grafana holds and changes the view, never the
default, and Coverage is a tab beside it.

The ROLE is tested with the role's real dashboard (CLAUDE.md, "Standing facts"):
this lab's fleet dashboard is `rcn-lab-overview`, its model as Grafana returned
it on 2026-10-01 (read-only; the topology image's public hostname replaced),
14 panels in six rows, four of them types this app does not draw (an alert
list, a text panel, two logs panels), each kept in its place and saying so.
`rcn-lab1-snmp`, the panel-FILTERING fixture, appears only where a test is
about filtering: a dashboard chosen here draws the panels a device page leaves
out. On test_device_v2's lab: the real app, the real dashboards reader, real
`api/ds/query` answers.
"""

import re

from tests.test_device_v2 import (FILTERING_FIXTURE, _fixture, _get, _get_json,  # noqa: F401
                                  _text, lab)

FLEET = "rcn-lab-overview"
NOT_DRAWN_HERE = {2: "alertlist", 20: "text", 17: "logs", 18: "logs"}


def _panels(html):
    return re.findall(r'data-panel-src="([^"]*)"', html)


def _elsewhere(html):
    return re.findall(r'<section class="panel panel-elsewhere[^>]*>\s*<div class="panel-head"><h3>([^<]*)</h3>'
                      r'<span class="panel-type mono">([^<]*)</span>', html)


class TestTheFleetPage:
    def test_with_no_fleet_dashboard_set_it_says_so_and_offers_every_dashboard(self, lab):
        r, html = _get(lab, "/v2/monitoring")
        assert r.status_code == 200
        text = _text(html)
        assert "No fleet dashboard is set for this network." in text
        assert "Fleet dashboard UID" in text and _panels(html) == []
        assert re.search(r"Every dashboard Grafana holds: \d+\.", text)
        assert f'href="/v2/monitoring?dashboard={FLEET}&amp;range=1h"' in html

    def test_the_labs_fleet_dashboard_draws_every_panel_in_its_place(self, lab):
        lab["settings"]["grafana_fleet_dashboard_uid"] = FLEET
        _r, html = _get(lab, "/v2/monitoring")
        model = _fixture("dashboards", f"{FLEET}.json")
        native = [p["id"] for p in model["panels"] if p["type"] not in ("row", *NOT_DRAWN_HERE.values())]
        sourced = [int(re.search(r"/(\d+)\?", s).group(1)) for s in _panels(html)]
        assert len(native) == 10 and sorted(sourced) == sorted(native)
        assert all(re.fullmatch(rf"/v2/monitoring/panel/{FLEET}/\d+\?range=1h", s) for s in _panels(html))
        assert sorted(t for _title, t in _elsewhere(html)) == sorted(NOT_DRAWN_HERE.values())
        assert html.count("Grafana draws it, this page does not.") == 4
        for row in ("Health and alerts", "Reachability and latency", "Traps and syslog"):
            assert re.search(rf'<h2 class="panel-row">{row}', html), row
        assert re.search(r'<span class="grow">[^<]*</span><span class="mono muted">rcn-lab-overview</span>'
                         r' <span class="badge badge-info">default</span>', html)

    def test_a_panel_grafana_draws_links_to_it_where_grafanas_address_is_known(self, lab):
        lab["settings"].update(grafana_fleet_dashboard_uid=FLEET, grafana_url="http://grafana.example.invalid:3000")
        _r, html = _get(lab, "/v2/monitoring")
        for pid in NOT_DRAWN_HERE:
            assert f'href="http://grafana.example.invalid:3000/d/{FLEET}?viewPanel={pid}"' in html
        assert "(reachable from the LAN only)" in html
        lab["settings"]["grafana_url"] = ""
        _r, html = _get(lab, "/v2/monitoring")
        assert "viewPanel" not in html and html.count("Grafana draws it, this page does not.") == 4

    def test_a_filtering_dashboard_chosen_here_draws_what_a_device_page_leaves_out(self, lab):
        """FILTERING, named as such: the fixture's 8 panels, 4 selecting a device."""
        _r, html = _get(lab, f"/v2/monitoring?dashboard={FILTERING_FIXTURE}")
        _r, dev = _get(lab, "/v2/device/r3/monitoring")
        assert len(_panels(html)) + len(_elsewhere(html)) == 8 and len(_panels(dev)) == 4
        assert "4 panels left out" in _text(dev) and "left out" not in _text(html)

    def test_choosing_a_dashboard_changes_the_view_never_the_setting(self, lab):
        lab["settings"]["grafana_fleet_dashboard_uid"] = FLEET
        _r, html = _get(lab, f"/v2/monitoring?dashboard={FILTERING_FIXTURE}")
        assert f"/v2/monitoring/panel/{FILTERING_FIXTURE}/" in html and f"/panel/{FLEET}/" not in html
        assert lab["settings"]["grafana_fleet_dashboard_uid"] == FLEET

    def test_a_uid_grafana_says_is_gone_is_said_as_its_answer(self, lab):
        lab["settings"]["grafana_fleet_dashboard_uid"] = "no-such-dashboard"
        _r, html = _get(lab, "/v2/monitoring")
        text = _text(html)
        assert ("Grafana holds no dashboard with UID no-such-dashboard" in text
                or "is not in the stored list, and Grafana could not be asked now" in text)
        assert _panels(html) == []

    def test_a_panel_is_the_dashboards_own_query(self, lab):
        lab["settings"]["grafana_fleet_dashboard_uid"] = FLEET
        _r, html = _get(lab, "/v2/monitoring")
        src = _panels(html)[0]
        code, body = _get_json(lab, src)
        assert code == 200 and "read_at" in body
        assert lab["fake"].queries, "nothing reached Grafana"
        code, body = _get_json(lab, f"/v2/monitoring/panel/{FLEET}/99999?range=1h")
        assert code == 404 and body["error"] == f"{FLEET} holds no panel 99999"
        pid = src.split("/")[-1].split("?")[0]
        code, body = _get_json(lab, f"/v2/monitoring/panel/{FLEET}/{pid}?range=400d")
        assert code == 400

    def test_a_panel_grafana_draws_is_never_queried_here(self, lab):
        before = len(lab["fake"].queries)
        for pid, kind in NOT_DRAWN_HERE.items():
            code, body = _get_json(lab, f"/v2/monitoring/panel/{FLEET}/{pid}?range=1h")
            assert code == 400 and body["error"] == f"panel {pid} is a {kind} panel: Grafana draws it, this page does not"
        assert len(lab["fake"].queries) == before

    def test_the_fragment_redraws_on_the_dashboards_key(self, lab):
        _r, html = _get(lab, "/v2/monitoring/dashboard")
        assert html.lstrip().startswith('<div class="monitoring" id="fleet"')
        assert 'hx-trigger="nmas:dashboards from:body"' in html



class TestTheTabsAndTheSidebar:
    def test_monitoring_opens_on_dashboards_with_coverage_beside_it(self, lab):
        _r, html = _get(lab, "/v2/monitoring")
        assert re.search(r'<a class="tab on" href="/v2/monitoring" aria-current="page">Dashboards</a>', html)
        assert '<a class="tab" href="/v2/monitoring/coverage">Coverage</a>' in html
        assert re.search(r'<a class="nav-item active" href="/v2/monitoring" aria-current="page">', html)

    def test_coverage_is_the_other_tab_and_keeps_monitoring_active(self, lab, monkeypatch):
        from modules import monitoring_coverage
        monkeypatch.setattr(monitoring_coverage, "fleet", lambda ref: {
            "list": "Lab", "columns": [], "profile": {"committed": False, "error": "",
                                                      "sections": []},
            "devices": [], "covered": 0, "total": 0})
        _r, html = _get(lab, "/v2/monitoring/coverage")
        assert re.search(r'<a class="tab on" href="/v2/monitoring/coverage" aria-current="page">Coverage</a>', html)
        assert re.search(r'<a class="nav-item active" href="/v2/monitoring" aria-current="page">', html)

    def test_no_note_sits_under_the_controls(self, lab):
        """The operator, 2026-10-02: the retention and step note under the range controls
        crowded the dashboard selector. They are on the controls' hover and behind the (i)."""
        lab["settings"]["grafana_fleet_dashboard_uid"] = FLEET
        _r, html = _get(lab, "/v2/monitoring")
        assert '<p class="limits">' not in html and "Prometheus serves up to" not in html
        assert re.search(r'<div class="seg" role="group" aria-label="Time range" '
                         r'title="The live store keeps 90 days\. Step 15 s for 1 hour: the step '
                         r'widens with the range\.">', html)
        assert 'data-manual="monitoring#time-range"' in html
        assert re.search(r"class=\"btn btn-select\"[^>]*title=\"Grafana's dashboard list, read ", html)

    def test_a_range_past_the_limit_is_refused_at_the_control(self, lab):
        lab["settings"]["grafana_fleet_dashboard_uid"] = FLEET
        _r, html = _get(lab, "/v2/monitoring?range=last+120d")
        form = re.search(r'<form class="range-custom".*?</form>', html, re.S).group(0)
        assert 'value="last 120d" aria-invalid="true"' in form
        assert ("Refused: the live store keeps 90 days, and no history store is set "
                "(grafana_history_datasource_uid); this range is 120 days.") in _text(form)
        assert _panels(html) == [] and "notice-warn" not in html

    def test_monitoring_has_exactly_the_signed_off_tabs(self, lab):
        """The operator, 2026-10-02: a new screen needs a mockup and a sign-off
        BEFORE it is built. IP SLA and Heartbeat were tabs that had neither;
        Monitoring holds the two that were signed off, and a third is a change
        to this test, made with the operator's sign-off."""
        tabs = "templates/v2/_monitoring_tabs.html"
        labels = re.findall(r'class="tab[^"]*"[^>]*>([^<]+)</a>', open(tabs, encoding="utf-8").read())
        assert labels == ["Dashboards", "Coverage"]
        _r, html = _get(lab, "/v2/monitoring")
        nav = html.split('aria-label="Monitoring">', 1)[1].split("</nav>", 1)[0]
        assert re.findall(r">([^<]+)</a>", nav) == ["Dashboards", "Coverage"]

    def test_every_monitoring_url_carries_the_strict_policy(self, lab):
        from modules import csp
        for url in ("/v2/monitoring", "/v2/monitoring/dashboard"):
            r, html = _get(lab, url)
            assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY, url
            assert not re.search(r"\sstyle=|\son[a-z]+=", html), url
