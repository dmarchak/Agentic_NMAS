"""Re-measuring the heartbeat windows from the app (NSOT_PLAN P.7; the operator,
2026-10-01: "the fix is a console command with a placeholder; re-measuring a
window must be an action in the app"). On s3's REAL arrivals and sysUpTime
around its reboot (`tests/fixtures/heartbeat/s3_reboot.json`), through the
script's OWN measurement (`scripts/nmas-heartbeat-rules`, loaded): the preview
draws each device's installed and new window with what it is measured from and
the check's verdict, writes nothing, and names its datasource from the
installed rules (never a placeholder); the confirm measures again, refuses a
moved measurement, writes the file and records who; the page then names the
ONE host step with every value filled in, until the installed file is the one
written. The heartbeat check's Needs attention action opens the page."""

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def lab(monkeypatch, tmp_path):
    from modules import heartbeat_windows as HW
    with open(os.path.join(ROOT, "tests", "fixtures", "heartbeat", "s3_reboot.json"),
              encoding="utf-8") as fh:
        s3 = json.load(fh)
    H = HW._script()
    restarts = []
    for series in s3["sysUpTime"]:
        restarts.extend(H.restart_windows([tuple(v) for v in series["values"]]))
    written = tmp_path / "written" / "nmas-heartbeat.yaml"
    installed = tmp_path / "etc" / "nmas-heartbeat.yaml"
    installed.parent.mkdir()
    doc = H.build({"s3": {"basis": "measured", "window": 1337, "lo": 515.1, "hi": 575.5,
                          "n": 40, "rate": 0.55}}, "lokiuid1", 300)
    installed.write_text(H.render(doc), encoding="utf-8")
    monkeypatch.setattr(H, "OUT", str(written))
    monkeypatch.setattr(H, "_loki_url", lambda arg: "http://loki.invalid")
    monkeypatch.setattr(H, "expected_devices", lambda: ({"s3", "s9"}, []))
    state = {"arrivals": list(s3["arrivals"])}
    monkeypatch.setattr(H, "loki_arrivals", lambda url, h, hours=6, query="":
                        [] if query or h != "s3" else list(state["arrivals"]))
    monkeypatch.setattr(H, "prometheus_restarts", lambda hosts, hours=6: ({"s3": restarts}, ""))
    monkeypatch.setattr(HW, "_script", lambda: H)
    monkeypatch.setattr(HW, "INSTALLED", str(installed))
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: 300 if key == "syslog_heartbeat_seconds" else default)
    return {"H": H, "HW": HW, "written": written, "installed": installed, "state": state}


def _plan(lab):
    return lab["HW"].plan(lab["H"], str(lab["installed"]))


class TestThePreview:
    def test_each_device_installed_beside_measured_with_the_checks_verdict(self, lab):
        p = _plan(lab)
        rows = {r["device"]: r for r in p["rows"]}
        s3 = rows["s3"]
        assert s3["installed"] == {"window": 1337, "basis": "measured"}
        assert s3["new"]["basis"] == "measured" and s3["restarts"] == 1
        assert s3["check"].startswith("current    s3: window 1337 s")
        # A device told to heartbeat with no rule: MISSING, and it changes.
        assert rows["s9"]["installed"] is None and rows["s9"]["changes"]
        assert rows["s9"]["check"].startswith("MISSING    s9")
        assert "restarts excluded" in p["restarts"] and "s3 (1)" in p["restarts"]

    def test_the_datasource_comes_from_the_installed_rules_never_a_placeholder(self, lab):
        p = _plan(lab)
        assert p["uid"] == "lokiuid1" and "lokiuid1" in p["text"] and "<" not in p["uid"]

    def test_the_preview_writes_nothing(self, lab):
        _plan(lab)
        assert not lab["written"].exists()

    def test_no_loki_is_refused_by_name(self, lab, monkeypatch):
        monkeypatch.setattr(lab["H"], "_loki_url", lambda arg: "")
        with pytest.raises(lab["HW"].Refused, match="no Loki to measure from"):
            _plan(lab)

    def test_an_unknown_datasource_is_refused_never_guessed(self, lab, monkeypatch):
        lab["installed"].unlink()
        monkeypatch.delenv("NMAS_GRAFANA_LOKI_UID", raising=False)
        with pytest.raises(lab["HW"].Refused, match="datasource's UID is not known"):
            _plan(lab)


class TestTheConfirm:
    def test_it_writes_the_file_records_who_and_names_the_host_step(self, lab):
        HW = lab["HW"]
        p = _plan(lab)
        out = HW.apply(p["fingerprint"], "op@example.com", lab["H"], str(lab["installed"]))
        assert out["outcome"] == "written" and lab["written"].read_text() == p["text"]
        assert out["host_step"] == (f"sudo install -m 0644 {lab['written']} {lab['installed']} "
                                    f"&& sudo systemctl restart grafana-server")
        assert HW.last_written()["actor"] == "op@example.com"
        assert HW.state(str(lab["written"]), str(lab["installed"]))["pending"] is True

    def test_installed_is_said_once_the_file_grafana_loads_is_the_written_one(self, lab):
        HW = lab["HW"]
        p = _plan(lab)
        HW.apply(p["fingerprint"], "op@example.com", lab["H"], str(lab["installed"]))
        lab["installed"].write_text(lab["written"].read_text())
        assert HW.state(str(lab["written"]), str(lab["installed"]))["pending"] is False

    def test_a_moved_measurement_writes_nothing(self, lab):
        HW = lab["HW"]
        p = _plan(lab)
        lab["state"]["arrivals"].append(lab["state"]["arrivals"][-1] + 530.0)
        with pytest.raises(HW.Refused, match="moved since the preview"):
            HW.apply(p["fingerprint"], "op@example.com", lab["H"], str(lab["installed"]))
        assert not lab["written"].exists()

    def test_no_actor_is_refused(self, lab):
        with pytest.raises(lab["HW"].Refused, match="who made it"):
            lab["HW"].apply("x", "", lab["H"], str(lab["installed"]))


class TestThePage:
    def test_the_page_draws_rows_and_the_confirm_under_the_strict_policy(self, lab):
        import app as A
        r = A.app.test_client().get("/v2/monitoring/heartbeat")
        page = r.get_data(as_text=True)
        assert r.status_code == 200 and "Content-Security-Policy" in r.headers
        assert 'id="hb-s3"' in page and 'id="hb-s9"' in page and "1337 s" in page
        assert 'id="hb-confirm"' in page
        assert re.search(r'<a class="tab on" href="/v2/monitoring/heartbeat" aria-current="page">'
                         r'Heartbeat</a>', page)

    def test_after_the_confirm_the_page_names_the_host_step_with_real_values(self, lab):
        import app as A
        c = A.app.test_client()
        page = c.get("/v2/monitoring/heartbeat").get_data(as_text=True)
        fp = json.loads(re.search(r"data-body='([^']*)'", page).group(1).replace("&#34;", '"'))
        r = c.post("/v2/monitoring/heartbeat/apply", json=fp)
        assert r.status_code == 200, r.get_json()
        page = c.get("/v2/monitoring/heartbeat").get_data(as_text=True)
        step = re.search(r'<p class="cmd"><code>([^<]*)</code>', page)
        assert step and str(lab["written"]) in step.group(1) and "grafana-server" in step.group(1)
        assert "NOT YET INSTALLED" in page

    def test_the_heartbeat_checks_action_opens_the_page_with_no_placeholder(self):
        from modules import job_health as J
        job = next(j for j in J.JOBS if j["unit"] == "nmas-heartbeat-check")
        assert job["remedy"]["href"] == "/v2/monitoring/heartbeat"
        assert "command" not in job["remedy"] and "<" not in json.dumps(job["remedy"])


class TestOnlyWhatNeedsIt:
    """Measured on the host (2026-10-01): 7 of 9 windows would move by a few
    seconds while all 9 were current. A write costs a Grafana restart, so it
    is offered, and done, only where the hourly check fails."""

    def test_a_current_device_needs_nothing_and_a_missing_one_does(self, lab):
        rows = {r["device"]: r for r in _plan(lab)["rows"]}
        assert rows["s3"]["needs"] is False and rows["s9"]["needs"] is True

    def test_with_every_window_current_there_is_no_confirm_and_apply_refuses(self, lab, monkeypatch):
        import app as A
        monkeypatch.setattr(lab["H"], "expected_devices", lambda: ({"s3"}, []))
        p = _plan(lab)
        assert p["needs"] == 0
        page = A.app.test_client().get("/v2/monitoring/heartbeat").get_data(as_text=True)
        assert 'id="hb-confirm"' not in page and "nothing needs writing" in page
        with pytest.raises(lab["HW"].Refused, match="nothing was written"):
            lab["HW"].apply(p["fingerprint"], "op@example.com", lab["H"], str(lab["installed"]))
        assert not lab["written"].exists()
