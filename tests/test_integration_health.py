"""Integration health as a reader job (7.2 step 16; modules/readers/
integration_health.py), consumed by every v2 page's strip in its top bar
(today's status bar until it left at 7.8) AND by Needs attention: one stored value, two
consumers, so they cannot disagree. A card's Test stays a live check (reader_job
rule 11)."""

import os
import time

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
        assert v["counts"] == {"up": 1, "down": 1, "refused": 0, "not_configured": 1}
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
        """Rule 11: a person asking NOW is a check, never a cached report. A card's Test on
        Settings › Default (today's Integrations card's Test until it left at 7.8)."""
        from modules.integrations.prometheus import PrometheusIntegration
        stored()
        monkeypatch.setattr(PrometheusIntegration, "is_configured", lambda self: True)
        monkeypatch.setattr(PrometheusIntegration, "test_connection",
                            lambda self: {"ok": True, "message": "asked live"})
        r = client.post("/v2/settings/network/Default/group/prometheus/test")
        assert r.status_code == 200, r.get_data(as_text=True)
        assert "asked live" in r.get_data(as_text=True)


class TestTheSource:
    def test_a_configured_integration_that_is_down_is_a_danger_row(self):
        stored()
        res = A.integrations_source()
        (row,) = res["rows"]
        assert row["id"] == "integrations:grafana" and row["level"] == "danger"
        assert row["what"] == "Grafana is not answering"
        assert "Could not connect" in row["cause"] and "Test button" in row["action"]["label"]
        assert "1 up, 1 down, 0 refusing the credential, 1 not configured" in res["checked"]
        assert res["stale_after_seconds"] == 180 and res["value_at"] == R._iso(T0)

    def test_a_refused_credential_is_its_own_danger_row_naming_where_to_renew(self, monkeypatch):
        """P.21 (C354): the service answered and refused the credential, so the row names the
        credential and where it is renewed, and a declared expiry if there is one."""
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: "2026-09-30" if key ==
                            "grafana_token_expires" else default)
        stored({"grafana": fake("grafana", "Grafana", "refused",
                                "HTTP 401: Grafana refused the tool's credential")})
        res = A.integrations_source()
        (row,) = res["rows"]
        assert row["kind"] == "refused" and row["level"] == "danger"
        assert row["what"] == "Grafana refuses the tool's credential"
        assert "2026-09-30" in row["cause"]
        assert "Service accounts" in row["action"]["label"]
        assert "Settings › Default, the Grafana card" in row["action"]["label"], (
            "C617: the v2 place, never today's Settings > Integrations")

    def test_a_401_is_refused_never_down_and_grafana_asks_with_its_token(self, monkeypatch):
        """The probe of the shared client: a 401 or 403 is `refused`; Grafana, holding a
        token, asks /api/user (which needs it), never only /api/health (C354)."""
        from modules.integrations.grafana import GrafanaIntegration
        asked = []

        class _R:
            status_code = 401

        class _S:
            def get(self, url, **kw):
                asked.append(url)
                return _R()
        monkeypatch.setattr("modules.integrations.base.get_secret", lambda k, d="": "tok")
        g = GrafanaIntegration()
        monkeypatch.setattr(g, "is_configured", lambda: True)
        monkeypatch.setattr(g, "session", lambda: _S())
        st = g.status()
        assert st["state"] == "refused" and "refused" in st["message"]
        assert asked and asked[0].endswith("/api/user")

    def test_loki_with_a_credential_asks_an_endpoint_that_needs_it(self, monkeypatch):
        """C354: Loki's /ready answers without a credential, so a refused one read as ready."""
        from modules.integrations.loki import LokiIntegration
        asked = []

        class _R:
            status_code = 403

        class _S:
            def get(self, url, **kw):
                asked.append(url)
                return _R()
        monkeypatch.setattr("modules.integrations.base.get_setting",
                            lambda k, d=None: "bearer" if k == "loki_auth_mode" else d)
        lk = LokiIntegration()
        monkeypatch.setattr(lk, "is_configured", lambda: True)
        monkeypatch.setattr(lk, "session", lambda: _S())
        assert lk.status()["state"] == "refused"
        assert asked and asked[0].endswith("/loki/api/v1/labels")

    def test_unconfigured_is_a_state_never_a_row(self):
        stored({"s3": REG["s3"]})
        assert A.integrations_source()["rows"] == []

    def test_nothing_stored_is_unreadable(self):
        res = A.integrations_source(cached={"state": "absent", "doc": None, "why": "never"})
        assert res["state"] == "unreadable" and "not probed yet" in res["rows"][0]["cause"]


def strip_html(client, ago=0.0, registry=REG):
    """The top bar's strip (`/v2/strip`) over a value the reader stored *ago* seconds ago."""
    import dataclasses
    R.run_once(dataclasses.replace(IH.READER, read=lambda: IH.read(registry)),
               clock=lambda: time.time() - ago)
    return client.get("/v2/strip").get_data(as_text=True)


class TestTheStrip:
    """Today's status bar's integration item (7.2 step 16), on its v2 home, every page's strip
    in the top bar, `device_v2.strip`, since today's left at 7.8 (2026-10-15). Its cases, each
    rebased: the strip had drawn a value past its promise green, and left the unconfigured
    out unnamed; both fixed with the move."""

    @pytest.fixture
    def client(self):
        import app as Ap
        return Ap.app.test_client()

    def test_a_down_integration_is_named_in_words(self, client):
        html = strip_html(client)
        assert "Integrations 1 of 2 · Grafana down" in html and 'class="strip-item warn"' in html
        assert "Grafana: Could not connect" in html, "the detail is on hover"

    def test_all_up_is_one_answer_and_the_unconfigured_are_named(self, client):
        html = strip_html(client, registry={k: REG[k] for k in ("prometheus", "s3")})
        assert "Integrations 1 of 1" in html and 'class="strip-item ok"' in html
        assert "not configured: S3 archive" in html

    def test_past_its_promise_the_strip_says_stale_never_green(self, client):
        html = strip_html(client, ago=IH.READER.interval_seconds * 3 + 60,
                          registry={"prometheus": REG["prometheus"]})
        assert 'data-strip="stale"' in html and "Integrations: stale" in html, html
        assert "older than the 180 s its reader promises" in html
        assert 'class="strip-item ok"' not in html

    def test_within_its_promise_it_is_not_stale(self, client):
        """The control: a fresh value is drawn as what it says."""
        html = strip_html(client, ago=30, registry={"prometheus": REG["prometheus"]})
        assert 'class="strip-item ok"' in html and "stale" not in html

    def test_a_failed_read_is_never_drawn_as_all_up(self, client):
        html = client.get("/v2/strip").get_data(as_text=True)
        assert "Integrations not probed yet" in html and 'class="strip-item ok"' not in html

    def test_every_v2_page_carries_it(self):
        base = open(os.path.join(ROOT, "templates", "v2", "base.html"), encoding="utf-8").read()
        assert 'id="nmas-strip"' in base and "url_for('device_v2.strip')" in base
        assert "nmas:integration_health from:body" in base


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
