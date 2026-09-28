"""Integration health as a reader job (7.2 step 16; modules/readers/
integration_health.py), consumed by the status bar on every page AND by Needs
attention: one stored value, two consumers, so they cannot disagree. The
Settings panel's Test button stays a live check (reader_job rule 11)."""

import os
import time

import dukpy
import pytest

from modules import attention as A
from modules import config
from modules import reader_job as R
from modules.readers import integration_health as IH

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = 1_790_000_000.0


def fake(name, label, state, message="", sleep=0.0, raises=None):
    class C:
        pass
    C.name, C.label = name, label

    def status(self):
        if sleep:
            time.sleep(sleep)
        if raises:
            raise raises
        return {"ok": True, "state": state, "label": label, "message": message}
    C.status = status
    return C


REG = {"prometheus": fake("prometheus", "Prometheus", "up", "Prometheus 2.45.3"),
       "grafana": fake("grafana", "Grafana", "down", "Could not connect to http://grafana"),
       "s3": fake("s3", "S3 archive", "not_configured", "Not configured — set in Settings")}


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))


def stored(registry=REG):
    import dataclasses
    return R.run_once(dataclasses.replace(IH.READER, read=lambda: IH.read(registry)),
                      clock=lambda: T0)


class TestTheRead:
    def test_each_integration_is_recorded_with_its_state_and_probe_time(self):
        v = IH.read(REG)
        states = {i["name"]: i["state"] for i in v["integrations"]}
        assert states == {"prometheus": "up", "grafana": "down", "s3": "not_configured"}
        assert v["counts"] == {"up": 1, "down": 1, "not_configured": 1}
        assert all(isinstance(i["took_ms"], int) for i in v["integrations"])

    def test_the_probes_run_in_parallel_so_one_slow_one_bounds_the_read(self):
        slow = {f"i{n}": fake(f"i{n}", f"I{n}", "up", sleep=0.4) for n in range(5)}
        t0 = time.monotonic()
        IH.read(slow)
        assert time.monotonic() - t0 < 1.2, "five 0.4 s probes in sequence would take 2 s"

    def test_a_probe_that_raises_is_down_with_its_reason(self):
        v = IH.read({"x": fake("x", "X", "up", raises=ConnectionError("refused"))})
        (i,) = v["integrations"]
        assert i["state"] == "down" and "ConnectionError: refused" in i["message"]

    def test_a_message_is_redacted(self):
        v = IH.read({"x": fake("x", "X", "down", "said snmp-server community Pl4ntedC0mm RO")})
        assert "Pl4ntedC0mm" not in str(v)

    def test_no_integrations_is_a_failed_read(self):
        with pytest.raises(ValueError, match="no integrations"):
            IH.read({})

    def test_it_is_declared_with_its_measured_basis(self):
        assert IH.READER in R.readers() and IH.READER.interval_seconds == 60
        assert "266 ms" in IH.READER.interval_basis and "parallel" in IH.READER.interval_basis


class TestTheRoute:
    @pytest.fixture
    def client(self):
        import app as Ap
        return Ap.app.test_client()

    def test_nothing_stored_is_503_and_not_all_up(self, client):
        r = client.get("/settings/integrations/status")
        assert r.status_code == 503 and "not probed yet" in r.get_json()["error"]

    def test_it_serves_the_stored_value_and_never_probes(self, client, monkeypatch):
        stored()
        from modules.integrations.base import IntegrationClient

        # Counted, never raised: the old live path caught every exception per
        # integration, so a raising probe was swallowed and passed unseen (the
        # first control of this test passed, 2026-09-28).
        probes = []
        monkeypatch.setattr(IntegrationClient, "status",
                            lambda self: probes.append(self.name) or {"state": "up"})
        body = client.get("/settings/integrations/status").get_json()
        assert probes == [], f"the status route probed: {probes}"
        assert body["ok"] and body["value_at"] == R._iso(T0) and body["stale_after_seconds"] == 180
        assert [s["name"] for s in body["statuses"]] == ["prometheus", "grafana", "s3"]

    def test_the_test_button_stays_a_live_check(self, client, monkeypatch):
        """Rule 11: a person asking NOW is a check, never a cached report."""
        from modules.integrations.prometheus import PrometheusIntegration
        monkeypatch.setattr(PrometheusIntegration, "test_connection",
                            lambda self: {"ok": True, "message": "asked live"})
        r = client.post("/settings/integrations/prometheus/test")
        assert r.status_code == 200, r.get_json()
        assert r.get_json().get("message") == "asked live"


class TestTheSource:
    def test_a_configured_integration_that_is_down_is_a_danger_row(self):
        stored()
        res = A.integrations_source()
        (row,) = res["rows"]
        assert row["id"] == "integrations:grafana" and row["level"] == "danger"
        assert row["what"] == "Grafana is not answering"
        assert "Could not connect" in row["cause"] and "Test button" in row["action"]["label"]
        assert "1 up, 1 down, 1 not configured" in res["checked"]
        assert res["stale_after_seconds"] == 180 and res["value_at"] == R._iso(T0)

    def test_unconfigured_is_a_state_never_a_row(self):
        stored({"s3": REG["s3"]})
        assert A.integrations_source()["rows"] == []

    def test_nothing_stored_is_unreadable(self):
        res = A.integrations_source(cached={"state": "absent", "doc": None, "why": "never"})
        assert res["state"] == "unreadable" and "not probed yet" in res["rows"][0]["cause"]


BAR = os.path.join(ROOT, "static", "js", "nmas_status_bar.js")


def bar(payload, now_iso):
    src = open(BAR, encoding="utf-8").read()
    js = ("var window = {}; var document = undefined;\n" + src.replace(
        "})(typeof window !== 'undefined' ? window : this);", "})(window);")
        + "\nwindow.statusBarHtml(dukpy['d'], Date.parse(dukpy['now']));")
    return dukpy.evaljs(js, d=payload, now=now_iso)


PAYLOAD = {"ok": True, "value_at": "2026-09-28T21:30:00Z", "stale_after_seconds": 180,
           "statuses": [{"name": "prometheus", "label": "Prometheus", "state": "up",
                         "message": "Prometheus 2.45.3", "took_ms": 6},
                        {"name": "grafana", "label": "Grafana", "state": "down",
                         "message": "Could not connect", "took_ms": 5003}]}


class TestTheShippedBar:
    def test_fresh_badges_name_their_state_and_the_bar_says_its_age(self):
        html = bar(PAYLOAD, "2026-09-28T21:30:40Z")
        assert 'data-integration="grafana"' in html and "Grafana down" in html
        assert 'data-status-bar-age="fresh"' in html and "40 s ago" in html

    def test_past_its_promise_the_bar_says_stale(self):
        html = bar(PAYLOAD, "2026-09-28T21:34:00Z")
        assert 'data-status-bar-age="stale"' in html and "older than the 180 s" in html

    def test_a_failed_read_is_never_drawn_as_all_up(self):
        html = bar({"ok": False, "error": "not probed yet"}, "2026-09-28T21:30:00Z")
        assert "not the same as every integration being up" in html

    def test_every_page_carries_it(self):
        base = open(os.path.join(ROOT, "templates", "base.html"), encoding="utf-8").read()
        assert 'id="nmasStatusBar"' in base and "filename='js/nmas_status_bar.js'" in base


class TestTheCompactStamp:
    def test_a_panel_that_draws_its_own_age_gets_no_second_age_line(self):
        from tests.test_live_contract import _run
        out = _run("""
          var p = panel2('bar'); var redraws = 0;
          NMAS.stamp('bar', T, 180, 'Bar', function () { redraws++; }, {ownAge: true});
          T += 200000; NMAS.tick();
          [p.children.length, redraws];
        """)
        assert out == [0, 2]


class TestTheSettingsStrip:
    def test_a_failed_read_says_so_instead_of_leaving_the_strip_blank(self):
        src = open(os.path.join(ROOT, "static", "js", "gen",
                                "partials__settings_integrations.1.js"), encoding="utf-8").read()
        body = src[src.index("async function loadIntegrationStatus"):]
        body = body[:body.index("\n}\n")]
        assert "if (!d.ok) return;" not in body
        assert "not the same as every integration being up" in body
