"""Every root-installed helper is covered by the Host-Step check, and job health compares each
installed helper with this release before an operation needs it (the operator, 2026-10-03:
helper drift; modules/host_helpers.py).

- The registry is built from the owners' own constants (the updater's install list, the
  rotation's helper paths, the renderer's link); every source in it is under the Host-Step
  check's paths, and every one of those paths covers something installed.
- The Oxidized helper is still a root-installed file (a commit changing it names a host step)
  until Phase 3's host steps remove it, and has had no job-health row since Phase 3 step 2
  (2026-10-08): nothing runs it (tests/test_oxidized_helper_pin.py holds its steps done).
- The topology renderer's row comes from its host-step check, the same way.
- Every state these rows can take has Needs attention's words; a check that raises is said.
"""

import importlib.machinery
import importlib.util
import os

import pytest

from modules import host_helpers as HH

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_step_check():
    path = os.path.join(ROOT, "scripts", "nmas-host-step-check")
    loader = importlib.machinery.SourceFileLoader("hsc", path)
    spec = importlib.util.spec_from_loader("hsc", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _host_step_paths():
    return _load_step_check().HOST_STEP_PATHS


class TestTheRegistryAndTheHostStepCheck:
    def test_the_registry_is_the_owners(self):
        from modules import host_steps, update_op
        from modules.nsot import credential_rotation as cr
        reg = HH.registry()
        assert len(reg) >= 4
        assert {(h["installed"], h["source"]) for h in reg} >= {
            (p, s) for _n, p, s in update_op.INSTALLED if s}
        assert (cr.HELPER_INSTALLED, cr.HELPER_SOURCE_REL) in {(h["installed"], h["source"])
                                                               for h in reg}
        assert host_steps.TOPOLOGY_LINK in {h["installed"] for h in reg}
        assert all(os.path.exists(os.path.join(ROOT, h["source"])) for h in reg)

    def test_every_root_installed_source_is_under_the_host_step_check(self):
        paths = _host_step_paths()
        uncovered = [s for s in HH.sources() if not any(s.startswith(p) for p in paths)]
        assert uncovered == [], "a root-installed file a commit could change without a host step"

    def test_every_host_step_path_covers_something_installed(self):
        unused = [p for p in _host_step_paths()
                  if not any(s.startswith(p) for s in HH.sources())]
        assert unused == [], unused

    def test_every_helpers_check_exists_and_the_step_check_names_the_same_pairs(self):
        """C416: the commit-msg check's path -> check list and the registry are one fact."""
        from modules import host_steps
        reg = HH.registry()
        assert {h["check"] for h in reg} <= set(host_steps.CHECKS)
        step_checks = _load_step_check().STEP_CHECKS
        for h in reg:
            covering = [c for p, c in step_checks.items() if h["source"].startswith(p)]
            assert covering == [h["check"]], (h["source"], covering)
        for p, c in step_checks.items():
            assert any(h["source"].startswith(p) and h["check"] == c for h in reg), (p, c)

    def test_folds_name_each_helpers_job_health_row(self):
        assert HH.folds() == {"updater": ("job_health:updater", ("differs",)),
                              "topology-renderer": ("job_health:helper:topology-renderer",
                                                    ("differs",))}


@pytest.fixture
def settings(monkeypatch):
    values = {}
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: values.get(key, default))
    return values


def _status(state, **extra):
    return dict({"installed_path": "/usr/local/sbin/nmas-oxidized-cred",
                 "reinstall": "sudo install -o root -g root -m 0755 x /usr/local/sbin/x",
                 "ok": state == "ok", "state": state, "reason": f"the helper is {state}"},
                **extra)


class TestTheTopologyRenderer:
    def test_a_stale_link_is_a_row_naming_its_command(self, settings):
        settings["topology_service_url"] = "http://192.0.2.6:8088"
        row = HH.topology_row(check=lambda: {"state": "not_done", "detail": "points elsewhere"})
        assert row["state"] == "differs" and "ln -sfn" in row["action"]["command"]
        assert HH.topology_row(check=lambda: {"state": "done", "detail": "ok"})["state"] == "ok"

    def test_no_service_and_no_renderer_is_no_row(self, settings, monkeypatch):
        monkeypatch.setattr("os.path.lexists", lambda p: False)
        assert HH.topology_row(check=lambda: {"state": "not_done", "detail": "x"}) == {}


class TestInJobHealthAndNeedsAttention:
    def test_every_state_a_helper_row_takes_has_words(self):
        from modules.attention import _JOB_STATES
        from modules.job_health import OK_STATES
        for state in ("differs", "not_installed", "writable", "cannot_run", "unknown"):
            assert state in _JOB_STATES, state
        assert "ok" in OK_STATES

    def test_a_check_that_raises_is_said(self, monkeypatch):
        def boom():
            raise PermissionError("cannot read the renderer's link")
        monkeypatch.setattr(HH, "topology_row", boom)
        (row,) = HH.helper_rows()
        assert row["state"] == "unknown" and "PermissionError" in row["detail"]

    def test_job_health_carries_the_rows(self, monkeypatch):
        from modules import job_health
        monkeypatch.setattr(HH, "helper_rows", lambda: [{"unit": "helper:x", "state": "differs",
                                                         "max_age_minutes": 0, "what": "w",
                                                         "detail": "d"}])
        got = job_health.health(images=[], settings=[], rotations=[], owner=[], ztp=[],
                                responder=[], startup=[], sessions=[], version=[], readers=[],
                                breakglass=[], prometheus=[], monitoring=[], updater=[])
        assert "helper:x" in got["not_ok"]
