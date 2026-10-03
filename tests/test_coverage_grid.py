"""Monitoring > Coverage, the redrawn grid (artboard A, signed off 2026-10-02): icons only,
each with its why on hover and in words for a screen reader; selection only through the row
boxes, a device with nothing the profile can supply having no box to tick; the bar above the
grid naming the devices ticked and their missing templates, with "Deploy missing templates…"
and Clear; a not-reporting cell a link to its diagnosis, never offered for a deploy.

On test_profile_apply's lab: r2's REAL golden and intent, and r6 in its real shape (r2's with
every `snmp` line removed). r2's SNMP is made to fail with the real reader capture's one edit
(tests/test_coverage_reporting.py).
"""

import json
import os
import re

import pytest

from tests.test_coverage_page import R2, R6
from tests.test_coverage_reporting import _capture, _down, read  # noqa: F401 (the fixture)
from tests.test_profile_apply import _commit_proposal, lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _table(lab, monkeypatch, report=None):
    from modules.nsot import listref
    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda *a, **k: [dict(R2), dict(R6)])
    if report is not None:
        monkeypatch.setattr("time.time", lambda: report["read_at"])
        monkeypatch.setattr("modules.device_page._cached", lambda name: (report, "", ""))
    r = lab["client"].get("/v2/monitoring/coverage/table")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _cell(html, host, column):
    """One cell's markup, found by the words its title starts with."""
    for td in re.findall(r'<td class="gc" data-state="[^"]+">.*?</td>|<td class="gc" '
                         r'data-state="[^"]+" title="[^"]*">.*?</td>', html, re.S):
        if f'"{host} · {column}: ' in td:
            return td
    raise AssertionError(f"no {host} · {column} cell")


def _box(html, host):
    m = re.search(r'<input type="checkbox"[^>]*(?:value="%s"|aria-label="%s:)[^>]*>' % (host, host),
                  html)
    assert m, host
    return m.group(0)


@pytest.fixture
def r2_snmp_down(read):
    value, _p, _l = read(_down(_capture(), "r2", jobs=("cisco_8000v", "lldp", "ospf", "ospfv3")))
    return value


class TestTheCells:
    def test_each_state_is_its_icon_with_its_why_in_words(self, lab, monkeypatch, r2_snmp_down):
        _commit_proposal()
        html = _table(lab, monkeypatch, r2_snmp_down)
        # Configured: a tick, "configured" for a screen reader, the arrival on hover.
        ok = _cell(html, "r2", "Syslog")
        assert '<span class="sr-only">configured</span><span class="m-ok"' in ok
        assert 'title="r2 · Syslog: configured; a line ' in ok
        # Not configured, the profile supplying it: the quiet ring, and how to deploy it.
        gap = _cell(html, "r6", "SNMP")
        assert '<span class="m-no" aria-hidden="true"></span>' in gap
        assert ('title="r6 · SNMP: not configured: missing — the profile supplies it. Select the '
                'device to deploy it"') in gap
        # Not reporting: the amber mark, a link to the tab where the cause is found.
        nr = _cell(html, "r2", "SNMP")
        assert 'href="/v2/device/r2?tab=monitoring"' in nr and '<span class="m-nr"' in nr
        assert "a deploy does not fix this" in nr
        # Not applicable: blank, its why on hover and for a screen reader.
        blank = re.findall(r'<td class="gc" data-state="(?:unused|not_applicable|excluded)" '
                           r'title="[^"]+">(.*?)</td>', html, re.S)
        assert blank, "the lab draws no not-applicable cell (the floor)"
        assert all('class="m-' not in td and td.startswith('<span class="sr-only">') for td in blank)

    def test_not_configured_that_the_profile_cannot_supply_offers_no_deploy(self, lab, monkeypatch):
        html = _table(lab, monkeypatch)
        gap = _cell(html, "r6", "SNMP")
        assert 'data-state="gap_open"' in gap and "Select the device" not in gap
        assert "no monitoring profile yet" in gap


class TestTheSelection:
    def test_the_bar_names_the_ticked_devices_and_their_missing_templates(self, lab, monkeypatch,
                                                                          r2_snmp_down):
        _commit_proposal()
        html = _table(lab, monkeypatch, r2_snmp_down)
        bar = re.search(r'<div class="cov-bar" id="cov-bar"([^>]*)>(.*?)</div>', html, re.S)
        assert bar and "hidden" not in bar.group(1).replace('x-bind:hidden="nonePicked"', "")
        assert ">1 device selected</strong>" in bar.group(2)
        assert "· r6 · 1 missing template</span>" in bar.group(2)
        assert "Deploy missing templates…" in bar.group(2) and ">Clear</button>" in bar.group(2)
        assert 'data-missing="1" checked' in _box(html, "r6")
        # Not reporting is diagnosed, never redeployed: r2 has nothing to tick.
        r2 = _box(html, "r2")
        assert "disabled" in r2 and "A template not reporting is diagnosed, not redeployed" in r2
        assert 'x-ref="all" x-on:change="pickAll"' in html

    def test_nothing_offered_draws_no_bar_and_no_header_box(self, lab, monkeypatch):
        html = _table(lab, monkeypatch)
        assert 'id="cov-bar"' not in html and 'x-ref="all"' not in html
        assert "Nothing to deploy: the network has no monitoring profile yet" in _box(html, "r6")

    @pytest.mark.parametrize("names, missing, words", [
        (["r7", "s5", "s6"], 9, ("3 devices selected", "· r7, s5, s6 · 9 missing templates")),
        (["r6"], 1, ("1 device selected", "· r6 · 1 missing template")),
    ])
    def test_the_bar_s_words_as_the_browser_computes_them(self, names, missing, words):
        import dukpy
        src = open(os.path.join(ROOT, "static", "js", "nmas_apply.js"), encoding="utf-8").read()
        got = dukpy.evaljs("var window = {};\n" + src + "\nwindow.NMAS_APPLY.coverageWords("
                           f"{json.dumps(names)}, {missing})")
        assert (got["summary"], got["detail"]) == words

    def test_a_real_browser_recounts_clears_and_selects_all(self, lab, monkeypatch):
        from tests import browser
        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the server-drawn bar is tested above")
        import app as A
        from modules.nsot import listref
        _commit_proposal()
        monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda *a, **k: [dict(R2), dict(R6)])
        with browser.Served(A.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url("/v2/monitoring/coverage"))
                b.wait_for("return window.Alpine && document.querySelector('#cov-bar') "
                           "&& !document.querySelector('#cov-bar').hidden")
                b.click("#cov-bar button[type=button]")
                assert b.wait_for("return document.querySelector('#cov-bar').hidden")
                assert not b.js("return document.querySelector('#cov-r6').checked")
                b.click("#cov-r6")
                b.wait_for("return !document.querySelector('#cov-bar').hidden")
                assert b.js("return document.querySelector('#cov-bar strong').textContent") == \
                    "1 device selected"
                # The row ticked is highlighted (the stylesheet's :has, no script).
                bg = b.js("return getComputedStyle(document.querySelector('#cov-r6')"
                          ".closest('tr').querySelector('th')).backgroundColor")
                assert bg not in ("rgba(0, 0, 0, 0)", "transparent"), bg
                b.click("#cov-bar button[type=button]")
                b.click("input[x-ref=all]")
                assert b.wait_for("return document.querySelector('#cov-r6').checked")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()


class TestNtpAndLldp:
    """Artboard A's seven columns. NTP and LLDP are the grid's alone (never a Needs attention
    row); an absent `lldp run` is LLDP off only where the platform's default is MEASURED off."""

    def test_configured_and_what_is_not_read_said(self, lab, monkeypatch):
        html = _table(lab, monkeypatch)
        ntp, lldp = _cell(html, "r2", "NTP"), _cell(html, "r2", "LLDP")
        assert 'data-state="unknown"' in _cell(html, "r6", "LLDP")
        assert 'data-state="ok"' in ntp and "configured; whether it synchronises is not read here" in ntp
        assert 'data-state="ok"' in lldp and "whether it finds neighbours is not read here" in lldp
        # Not read is not "unknown": the page's one line for an unjudged reader stays away.
        assert 'id="cov-reporting-unknown"' not in html or "not read here" not in html.split(
            'id="cov-reporting-unknown"')[1].split("</p>")[0]

    def test_an_absent_lldp_run_where_the_default_is_not_measured_is_unknown(self, lab, monkeypatch):
        """r6 in its real shape carries no `lldp run`; IOS-XE's default is not measured."""
        _commit_proposal()
        html = _table(lab, monkeypatch)
        cell = _cell(html, "r6", "LLDP")
        assert 'data-state="unknown"' in cell
        assert ("unknown — its configuration has no `lldp run`, and whether LLDP runs without it "
                "on IOS-XE is not measured") in cell
        assert 'data-missing="1"' in _box(html, "r6"), "r6 offered for SNMP alone, never LLDP"
        assert 'id="cov-legend-unknown"' in html

    def test_where_the_default_is_measured_off_it_is_missing(self, lab, monkeypatch, tmp_path):
        from modules.nsot import profile_propose
        planted = tmp_path / "defaults.json"
        planted.write_text(json.dumps({"by_dialect": {"cisco_iosxe": {"lldp run": {"state": "off"}}}}))
        monkeypatch.setattr(profile_propose, "DEFAULTS_FILE", str(planted))
        _commit_proposal()
        html = _table(lab, monkeypatch)
        cell = _cell(html, "r6", "LLDP")
        assert 'data-state="gap"' in cell and "missing — the profile supplies it" in cell
        assert 'data-missing="2"' in _box(html, "r6")
        assert 'id="cov-legend-unknown"' not in html, "no unknown cell, no legend for one"

    def test_ntp_with_no_servers_set_and_no_section_is_not_used(self, lab):
        from tests.test_coverage_page import _fleet, _row
        from modules import prometheus_targets as P

        def golden(ref, host):
            text = P.read_golden(ref, host)
            return "\n".join(l for l in text.splitlines() if not l.startswith("ntp server"))
        cell = _row(_fleet(lab, golden=golden), "r2")["cells"]["ntp"]
        assert cell == {"state": "unused", "words": "not used — no NTP servers are set (ntp_servers) "
                                                   "and the profile has no NTP section"}
        cell = _row(_fleet(lab, settings={"ntp_servers": ["192.0.2.1"]}, golden=golden),
                    "r2")["cells"]["ntp"]
        assert cell["state"] == "gap_open"
        # A profile holding an NTP section (proposed from the fleet) is the network using NTP,
        # with no ntp_servers set: the gap is one the profile supplies.
        _commit_proposal()
        cell = _row(_fleet(lab, golden=golden), "r2")["cells"]["ntp"]
        assert cell == {"state": "gap", "words": "missing — the profile supplies it"}

    def test_no_needs_attention_row_reads_them(self):
        from modules import monitoring_coverage as M
        assert set(M.CHECKS) == {"snmp", "syslog", "heartbeat", "telemetry"}
