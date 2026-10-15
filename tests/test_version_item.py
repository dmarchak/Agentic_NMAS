"""The running version (7.2 step 17, today's status bar's version item until it left at 7.8;
Help › About draws it): what is running, whether it is the checkout's commit, and its CI
verdict, each from the ONE implementation of that answer (the operator, 2026-09-28):
`routes.health._COMMIT`, job health's running-version row (C129) as its reader stored it, and
`scripts/nmas-deploy`'s own `ci_verdict()` through the ci-verdict reader. Nothing here computes
any of the three again."""

import ast
import dataclasses
import os

import pytest

from modules import attention as A
from modules import config
from modules import reader_job as R
from modules.readers import ci_verdict as CV
from routes import health as H
from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = 1_790_000_000.0


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))


def store_ci(commit, code):
    mod = CV.deploy_script()
    reader = dataclasses.replace(CV.READER, read=lambda: CV.read(
        commit=commit, verdict=lambda root, c: (code, f"sentence for {c[:10]}")))
    return R.run_once(reader, clock=lambda: T0), mod


def store_version_row(state, detail):
    from modules.readers import job_health_reader as JHR
    reader = dataclasses.replace(JHR.READER, read=lambda: {"health": {"jobs": [
        {"unit": "running-version", "state": state, "detail": detail}]}})
    return R.run_once(reader, clock=lambda: T0)


class TestOneImplementation:
    def test_the_verdict_is_the_deploy_script_s_own(self):
        mod = CV.deploy_script()
        assert os.path.samefile(mod.__file__, os.path.join(ROOT, "scripts", "nmas-deploy"))
        assert callable(mod.ci_verdict) and callable(mod.verdict_of_runs)

    def test_no_module_defines_a_second_verdict(self):
        """AST, over the program: the verdict logic lives in the script alone."""
        names = {"ci_verdict", "verdict_of_runs"}
        found = []
        for path in tracked("modules", suffix=".py") + \
                tracked("routes", suffix=".py", recursive=False) + [os.path.join(ROOT, "app.py")]:
            tree = ast.parse(open(path, encoding="utf-8").read())
            found += [f"{os.path.relpath(path, ROOT)}:{n.name}" for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name in names]
        assert found == [], found

    def test_the_exit_code_is_named_by_the_script_s_own_constants(self):
        mod = CV.deploy_script()
        assert [CV.state_of(mod, c) for c in (mod.OK, mod.CI_REFUSED, mod.COULD_NOT_ASK,
                                              mod.CI_PENDING, mod.CI_CANCELLED)] == [
            "verified", "failed", "could_not_ask", "pending", "cancelled"]

    def test_an_unknown_loaded_commit_is_a_failed_read(self, monkeypatch):
        monkeypatch.setattr(H, "_COMMIT", None)
        with pytest.raises(RuntimeError, match="loaded commit is unknown"):
            CV.read()

    def test_it_is_declared_with_its_rate_limit_basis(self):
        assert CV.READER in R.readers() and CV.READER.interval_seconds == 900
        assert "60 unauthenticated requests" in CV.READER.interval_basis


class TestTheCompositionComposes:
    """`version_facts()`, which Help › About draws (through /health/version for today's status
    bar until both left at 7.8, 2026-10-15)."""

    def test_it_composes_the_stored_answers_and_computes_none(self, monkeypatch):
        store_version_row("mixed_version", "MIXED VERSION: checkout at abc, service running def")
        mod = store_ci(H._COMMIT, CV.deploy_script().OK)[1]
        calls = []
        from modules import job_health as J
        monkeypatch.setattr(J, "version_rows", lambda *a, **k: calls.append("version_rows") or [])
        monkeypatch.setattr(mod, "ci_verdict", lambda *a: calls.append("ci_verdict") or (0, ""))
        body = H.version_facts()
        assert calls == [], f"the composition computed: {calls}"
        assert body["running"] == H._COMMIT
        assert body["version"]["state"] == "mixed_version" and "MIXED" in body["version"]["detail"]
        assert body["ci"]["state"] == "verified" and body["ci"]["value_at"] == R._iso(T0)

    def test_a_verdict_for_another_commit_is_not_this_commit_s(self):
        store_version_row("ok", "running x")
        store_ci("f" * 40, CV.deploy_script().OK)
        ci = H.version_facts()["ci"]
        assert ci["state"] == "not_judged" and "not judged yet" in ci["sentence"]

    def test_nothing_stored_says_what_is_missing(self):
        body = H.version_facts()
        assert body["version"]["state"] == "unknown" and body["ci"]["state"] == "unknown"
        assert "not judged yet" in body["ci"]["sentence"]


class TestTheSource:
    def test_a_running_commit_ci_failed_is_a_danger_row(self):
        store_ci(H._COMMIT, CV.deploy_script().CI_REFUSED)
        (row,) = A.ci_source()["rows"]
        assert row["level"] == "danger" and "its CI run failed" in row["what"]

    def test_a_verified_commit_is_no_row(self):
        store_ci(H._COMMIT, CV.deploy_script().OK)
        assert A.ci_source()["rows"] == []

    def test_another_commit_s_verdict_is_never_read_as_this_one_s(self):
        store_ci("f" * 40, CV.deploy_script().CI_REFUSED)
        res = A.ci_source()
        assert res["rows"] == [] and "not judged yet" in res["checked"]

    def test_nothing_stored_is_unreadable(self):
        res = A.ci_source(cached={"state": "absent", "doc": None, "why": "never"})
        assert res["state"] == "unreadable"


# Today's status bar (static/js/nmas_status_bar.js), whose version item and who-you-are item
# were drawn by the shipped script tested here, left at 7.8 (2026-10-15) with /health/version.
# Their v2 homes: Help › About draws each version state (tests/test_v2_pages.py, TestHelpAbout,
# test_about_draws_each_version_state) and who you are; every v2 page's top bar draws who you are
# through `identity.viewer()`, the same `identify()` as /identity/status
# (tests/test_device_v2.py).
