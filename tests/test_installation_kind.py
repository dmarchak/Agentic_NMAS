"""The installation kind (C2521; docs/LAB9_SDN_GAP.md 2.3; modules/installation_kind.py).

The operator's report of 2026-11-05: the laptop kit's Needs attention drew 29 rows, nearly all
checks of the server's own install. On ``installation_kind: laptop_kit`` each is marked "not
applicable on a laptop kit" under What was checked, one line naming the check and why, and is
not a row; on ``host`` (the default) every one is the row it always was; a real problem (NetBox
not answering, a device's reachability reader failing) is a row on either.

The fixture is a measurement, not typed from memory: a laptop-kit installation planted in a
scratch data folder (`kit_settings.py init`), every reader run once in a loopback-only network
namespace (as `scripts/nmas-test` confines), then job health's not-ok rows, the readers'
liveness rows and the stored reader values the server-only sources read, captured as they
were (2026-11-05). The only edits: the checkout's and data folder's paths, and the GitHub
account name, replaced by placeholders. That run raised 31 rows; the operator's kit raised 29.
"""
import copy
import json
import os

import pytest

from modules import attention as A
from modules import installation_kind as K
from modules import job_health as J

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "tests", "fixtures", "installation_kind",
                       "laptop_kit_survey.json"), encoding="utf-8") as _fh:
    FIX = json.load(_fh)
COMMIT = FIX["cached"]["ci-verdict"]["doc"]["last_good"]["value"]["commit"]

#: A step the running release owes, as `host_steps.owed` answers it (the survey's first).
OWED = {"ok": True, "steps": [{
    "id": "8bd2539600ef:d852b747", "sha": "8bd2539600ef" + "0" * 28,
    "step": "install the local CI runner when the operator chooses, by docs/LOCAL_CI.md",
    "check_state": "not_checkable", "check": ""}]}

#: Every row the survey's sources raised on the server's install, by id: what `host` must
#: keep raising, and what a laptop kit marks, all but kea_ztp_fragment's.
HOST_ROWS = sorted(
    [f"job_health:{u}" for u in (
        "nmas-heartbeat-check", "nmas-netbox-backup", "nmas-netbox-restore-test",
        "nmas-startup-check", "nmas-telemetry-check", "updater", "vm-images",
        "setting:kea_ztp_fragment", "setting:snmp_exporter_config", "setting:syslog_host",
        "setting:yang_push_script", "reader:app-pushed", "reader:ci-agreement",
        "reader:coverage-reporting", "reader:grafana-alerts", "reader:grafana-dashboards",
        "reader:scheduled-jobs")]
    + ["host_steps:8bd2539600ef:d852b747", "pushed:unreadable", f"ci:{COMMIT[:10]}",
       "ci_agreement:unreadable", "scheduled_jobs:unreadable", "grafana:unreadable"])

#: What a laptop kit leaves as a row: the ZTP guard (left in doubt: ZTP is a capability a kit
#: could use; the existing not-applicable declaration answers it, C2521's report).
KIT_ROWS = ["job_health:setting:kea_ztp_fragment"]

#: The lines a laptop kit adds under What was checked, each naming its check.
KIT_MARKED_JOBS = sorted(set(u.split(":", 1)[1] for u in HOST_ROWS
                             if u.startswith("job_health:")) - {"setting:kea_ztp_fragment"})
KIT_MARKED_SOURCES = ["ci", "ci_agreement", "grafana", "host_steps", "pushed", "scheduled_jobs"]


@pytest.fixture
def kind(tmp_path, monkeypatch):
    """The installation's settings file, in this test's folder: ``kind(value, **settings)``
    writes it (no value: the key absent, as every release before this one)."""
    from modules import config

    path = tmp_path / "user_settings.json"

    def set_kind(value=None, **settings):
        doc = dict(settings)
        if value is not None:
            doc["installation_kind"] = value
        path.write_text(json.dumps(doc), encoding="utf-8")

    set_kind()
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(path))
    return set_kind


def _cached(name):
    """The captured stored value, dated at this read: these tests are about which rows a kind
    raises, never about a value's age (a source past its promise is its own row)."""
    import time

    got = copy.deepcopy(FIX["cached"][name])
    good = (got.get("doc") or {}).get("last_good")
    if good and good.get("value_at"):
        good["value_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return got


def _sources(jobs=None):
    jobs = copy.deepcopy(FIX["jobs"] + FIX["readers"]) if jobs is None else jobs
    return [lambda: A.job_health_source(health=lambda: {"jobs": jobs}),
            lambda: A.host_steps_source(owed=copy.deepcopy(OWED)),
            lambda: A.pushed_source(cached=_cached("app-pushed")),
            lambda: A.ci_source(cached=_cached("ci-verdict")),
            lambda: A.ci_agreement_source(cached=_cached("ci-agreement")),
            lambda: A.scheduled_jobs_source(cached=_cached("scheduled-jobs")),
            lambda: A.grafana_source(cached=_cached("grafana-alerts"))]


@pytest.fixture
def page(monkeypatch):
    from routes import health

    monkeypatch.setattr(health, "_COMMIT", COMMIT)
    return lambda jobs=None: A.needs_attention(sources=_sources(jobs))


def _ids(p):
    return sorted(r["id"] for r in p["rows"])


def _marked(line):
    """A What-was-checked line is a mark when its drawn words begin with the kit's mark."""
    return line["checked"].startswith(K.MARK + ": ")


def _steady(p):
    """*p* without the times each read takes or makes."""
    drop = ("read_at", "value_at", "took_ms", "since")
    return json.loads(json.dumps(
        {"rows": [{k: v for k, v in r.items() if k not in drop} for r in p["rows"]],
         "sources": [{k: v for k, v in s.items() if k not in drop} for s in p["sources"]]}))


class TestALaptopKitMarksTheServersChecks:
    def test_it_raises_none_of_the_server_only_rows(self, kind, page):
        kind("laptop_kit")
        assert _ids(page()) == KIT_ROWS

    def test_each_is_one_line_under_what_was_checked_marked_not_applicable(self, kind, page):
        kind("laptop_kit")
        lines = page()["sources"]
        marked = [s for s in lines if _marked(s)]
        jobs = sorted(s["source"].split(":", 1)[1] for s in marked
                      if s["source"].startswith("job_health:"))
        assert jobs == KIT_MARKED_JOBS
        assert sorted(s["source"] for s in marked
                      if not s["source"].startswith("job_health:")) == KIT_MARKED_SOURCES
        for s in marked:
            assert s["checked"].startswith("not applicable on a laptop kit: "), s
            assert len(s["checked"]) > len("not applicable on a laptop kit: ") + 40, (
                f"{s['label']} is marked without saying why")
            assert s["count"] == 0 and s["state"] == "read", "a mark is never a row or unread"

    def test_a_marked_check_names_itself_and_its_state(self, kind, page):
        kind("laptop_kit")
        labels = {s["label"] for s in page()["sources"] if _marked(s)}
        assert "Job health › nmas-heartbeat-check is not installed" in labels
        assert "Job health › reader:grafana-alerts has never succeeded" in labels
        assert "Host steps a running release owes" in labels

    def test_job_healths_own_line_counts_the_marks(self, kind, page):
        kind("laptop_kit")
        (jh,) = [s for s in page()["sources"] if s["source"] == "job_health"]
        assert f"{len(KIT_MARKED_JOBS)} not applicable on a laptop kit" in jh["checked"]
        assert jh["count"] == 1 and not _marked(jh)

    def test_the_badge_counts_only_the_rows_left(self, kind, page):
        kind("laptop_kit")
        assert page()["badge"]["n"] == len(KIT_ROWS)


class TestAHostRaisesThemAsBefore:
    def test_the_default_raises_every_row(self, kind, page):
        assert _ids(page()) == HOST_ROWS

    def test_host_set_is_the_default_exactly(self, kind, page):
        before = _steady(page())
        kind("host")
        assert _steady(page()) == before

    def test_a_host_marks_nothing(self, kind, page):
        kind("host")
        assert not [s for s in page()["sources"] if _marked(s)]


class TestARealProblemStaysARowOnAKit:
    def _integrations(self, state, message):
        value = {"integrations": [{"name": "netbox", "label": "NetBox", "state": state,
                                   "message": message, "took_ms": 3}],
                 "counts": {"up": 0, "down": 1, "refused": 0, "not_configured": 0}}
        return {"state": "ok", "doc": {"stale_after_seconds": 180,
                                       "last_good": {"value": value,
                                                     "value_at": "2026-11-05T05:52:45Z"}}}

    @pytest.mark.parametrize("url", ["http://127.0.0.1:8001", "http://[::1]:8001"])
    def test_netbox_not_answering_is_a_danger_row(self, kind, url):
        kind("laptop_kit", netbox_url=url)
        res = A.integrations_source(cached=self._integrations(
            "down", f"Could not connect to {url}"))
        (r,) = res["rows"]
        assert r["id"] == "integrations:netbox" and r["level"] == "danger"
        assert not res.get("not_applicable") and not res.get("marked")

    @pytest.mark.parametrize("unit,state", [
        ("reader:reachability", "failing"), ("reader:netbox-lag", "never_succeeded"),
        ("rotation:r1", "not_recorded"), ("running-version", "mixed_version"),
        ("ssh-leak:192.0.2.11", "leaked"), ("ssh-leak:2001:db8::11", "leaked")])
    def test_a_check_of_the_kits_own_work_is_a_row(self, kind, page, unit, state):
        kind("laptop_kit")
        got = page([{"unit": unit, "what": "planted", "state": state, "detail": "planted"}])
        assert f"job_health:{unit}" in _ids(got)

    def test_a_configured_grafana_makes_its_readers_rows_again(self, kind, page):
        kind("laptop_kit", grafana_url="http://[2001:db8::30]:3000")
        ids = _ids(page())
        assert {"job_health:reader:grafana-alerts", "job_health:reader:grafana-dashboards",
                "grafana:unreadable"} <= set(ids)
        assert "job_health:reader:coverage-reporting" not in ids, (
            "coverage reads Prometheus and Loki, still not configured")

    def test_a_configured_proxmox_images_row_is_a_row(self, kind, page):
        kind("laptop_kit")
        got = page([{"unit": "vm-images:101", "what": "planted", "state": "missing",
                     "detail": "planted"}])
        assert "job_health:vm-images:101" in _ids(got)

    def test_a_set_monitoring_setting_contradicting_a_declaration_is_a_row(self, kind, page):
        kind("laptop_kit")
        got = page([{"unit": "setting:syslog_host", "what": "planted",
                     "state": "contradiction", "detail": "planted"}])
        assert "job_health:setting:syslog_host" in _ids(got)


class TestTheSetting:
    def test_the_default_is_host_the_prior_behaviour(self, kind):
        from modules.settings_schema import DEFAULTS

        assert DEFAULTS["installation_kind"] == "host"
        assert K.kind() == "host" and not K.is_laptop_kit()

    def test_an_undeclared_value_reads_as_host(self, kind):
        kind("server")
        assert K.kind() == "host"

    def test_an_unreadable_settings_file_reads_as_host(self, kind, tmp_path):
        (tmp_path / "user_settings.json").write_text("{not json", encoding="utf-8")
        assert K.kind() == "host"
        assert K.job({"unit": "updater", "state": "not_installed"}) == ""

    def test_the_schema_takes_the_two_kinds_and_refuses_another(self, kind):
        from modules.settings_schema import write_settings

        assert write_settings({"installation_kind": "laptop_kit"}, actor="test")["ok"]
        assert K.is_laptop_kit()
        got = write_settings({"installation_kind": "server"}, actor="test")
        assert not got["ok"] and "installation_kind" in got["error"]
        assert K.is_laptop_kit()

    def test_it_is_the_installations_alone(self):
        from modules.settings_scope import HOST, SCOPES

        assert SCOPES["installation_kind"][0] == HOST

    def test_every_unit_it_names_is_one_job_health_writes(self):
        """The table names real checks: the systemd units declared in `job_health.JOBS`, the
        readers registered, the guard settings found, so a renamed one cannot leave a mark on
        nothing while its row returns."""
        import app  # noqa: F401  (registers every reader, as the app does)
        from modules import reader_job

        units = {j["unit"] for j in J.JOBS} | {"updater", "vm-images"}
        units |= {f"reader:{r.name}" for r in reader_job.readers()}
        assert set(K.JOB_UNITS) <= units, set(K.JOB_UNITS) - units
        assert {u for u, _s in K.JOB_UNIT_STATES} <= units
        assert set(K.READER_SERVICES) <= units
        assert set(K.SETTINGS) <= set(J._guard_settings())
        assert set(K.SOURCES) | set(K.SOURCE_SERVICES) <= {
            fn().get("source") for fn in _sources()} | {"job_health"}
