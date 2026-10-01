"""Host steps have a KIND and are checked where the tool can check them (the
operator, 2026-09-30, after a580660: its step installed a file that exists only
AFTER the update, and the Update page demanded it be said done BEFORE; and the
ticked "Done" box never reached the request).

`Host-Step:` is done before the update and holds it; `Host-Step-After:` never
holds it and is a Needs attention row until done. `[<check>]` names the tool's
own check, so "done" is measured (a symlink's target, a service's restart)
instead of claimed.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

from tests.test_update_button import _plan_kw, _updater, _value

ROOT = Path(__file__).resolve().parent.parent
BODY = ("change\n\nHost-Step: install python3-foo\n"
        "Host-Step-After: [topology-renderer] install the renderer as a symlink and restart it\n"
        "Host-Step-After: tell the team\nHost-Step-None: a comment\n")


@pytest.fixture
def store(tmp_path, monkeypatch):
    from modules import host_steps
    monkeypatch.setattr(host_steps, "DONE", str(tmp_path / "done.jsonl"))
    return tmp_path


class TestTheTrailers:
    def test_each_kind_and_check_is_read(self):
        from modules import host_steps
        assert host_steps.parse(BODY) == [
            {"when": "before", "check": "", "step": "install python3-foo"},
            {"when": "after", "check": "topology-renderer",
             "step": "install the renderer as a symlink and restart it"},
            {"when": "after", "check": "", "step": "tell the team"}]

    def test_the_root_updater_never_sees_an_after_step(self):
        """So an AFTER step needs no re-install of the updater to work."""
        assert [s.strip() for s in _updater().HOST_STEP.findall(BODY)] == ["install python3-foo"]

    def test_the_terminal_deploy_reads_both_kinds(self):
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader("nmas_deploy_hs", str(ROOT / "scripts" / "nmas-deploy"))
        mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(mod)
        got = mod.HOST_STEP.findall(BODY)
        assert [(bool(a), c, s) for a, c, s in got] == [
            (False, "", "install python3-foo"),
            (True, "topology-renderer", "install the renderer as a symlink and restart it"),
            (True, "", "tell the team")]


def _systemctl(epoch):
    def run(argv, **kw):
        out = f"ExecMainStartTimestamp=@{epoch}\n" if epoch is not None else ""
        return subprocess.CompletedProcess(argv, 0 if epoch is not None else 1, out, "")
    return run


class TestTheTopologyRendererCheck:
    @pytest.fixture
    def tree(self, tmp_path):
        src = tmp_path / "repo" / "deploy" / "topology" / "rcn-topology.py"
        src.parent.mkdir(parents=True)
        src.write_text("x\n")
        os.utime(src, (1000, 1000))
        return tmp_path, src

    def test_absent_and_a_copy_are_not_done(self, tree):
        from modules import host_steps
        tmp, src = tree
        link = tmp / "rcn-topology.py"
        got = host_steps.check_topology_renderer(str(tmp / "repo"), str(link), run=_systemctl(2000))
        assert got["state"] == "not_done" and "absent" in got["detail"]
        link.write_text("a copy\n")
        got = host_steps.check_topology_renderer(str(tmp / "repo"), str(link), run=_systemctl(2000))
        assert got["state"] == "not_done" and "not a symlink" in got["detail"]

    def test_a_symlink_elsewhere_is_not_done_naming_it(self, tree):
        from modules import host_steps
        tmp, src = tree
        other = tmp / "other.py"
        other.write_text("y\n")
        link = tmp / "rcn-topology.py"
        link.symlink_to(other)
        got = host_steps.check_topology_renderer(str(tmp / "repo"), str(link), run=_systemctl(2000))
        assert got["state"] == "not_done" and str(other) in got["detail"]

    def test_the_service_must_have_restarted_after_the_file_changed(self, tree):
        from modules import host_steps
        tmp, src = tree
        link = tmp / "rcn-topology.py"
        link.symlink_to(src)
        assert host_steps.check_topology_renderer(str(tmp / "repo"), str(link),
                                                  run=_systemctl(500))["state"] == "not_done"
        assert host_steps.check_topology_renderer(str(tmp / "repo"), str(link),
                                                  run=_systemctl(2000))["state"] == "done"
        assert host_steps.check_topology_renderer(str(tmp / "repo"), str(link),
                                                  run=_systemctl(None))["state"] == "unknown"

    def test_an_unnamed_check_is_not_checkable_and_a_raising_one_unknown(self, monkeypatch):
        from modules import host_steps
        assert host_steps.check({"check": ""})["state"] == "not_checkable"
        assert "no check named" in host_steps.check({"check": "nosuch"})["detail"]
        monkeypatch.setitem(host_steps.CHECKS, "boom", lambda root: 1 / 0)
        assert host_steps.check({"check": "boom"})["state"] == "unknown"


class TestTheBeforeGate:
    def _s(self, state, sha="c" * 40):
        return {"sha": sha, "step": "do it", "check_state": state, "check_detail": "found X"}

    def test_a_step_checked_done_needs_no_tick(self):
        from modules.update_op import step_gate
        assert step_gate([self._s("done")], []) == ("", ["c" * 40])

    def test_a_step_checked_not_done_refuses_whatever_was_ticked(self):
        from modules.update_op import step_gate
        bad, ack = step_gate([self._s("not_done")], ["c" * 40])
        assert "not done yet, as checked" in bad and "found X" in bad and ack == []

    def test_an_unchecked_step_needs_its_tick_and_says_so(self):
        from modules.update_op import step_gate
        bad, _ = step_gate([self._s("not_checkable")], [])
        assert "has not been ticked as done" in bad
        assert step_gate([self._s("not_checkable")], ["c" * 40]) == ("", ["c" * 40])

    def test_the_preview_draws_each_kind(self, store, monkeypatch):
        import app as A
        from modules import host_steps, update_op
        monkeypatch.setitem(host_steps.CHECKS, "ok-check", lambda root: {"state": "done", "detail": "read fine"})
        v = _value(host_steps=[{"sha": "c" * 40, "step": "checked one", "check": "ok-check", "when": "before"},
                               {"sha": "d" * 40, "step": "ticked one", "check": "", "when": "before"}],
                   after_steps=[{"sha": "e" * 40, "step": "after one", "check": "", "when": "after"}])
        real = update_op.plan
        monkeypatch.setattr(update_op, "plan", lambda **kw: real(**_plan_kw(value=v)))
        html = A.app.test_client().get("/v2/update/panel").get_data(as_text=True)
        assert "Before the update" in html and "After the update" in html
        assert 'data-host-step="d' in html and 'data-host-step="c' not in html
        assert "checked: read fine" in html and "never hold the update back" in html


def _log(*commits):
    return "".join(f"{sha}\x1f{body}\x1e" for sha, body in commits)


class TestWhatTheRunningReleaseOwes:
    def test_after_steps_owed_until_checked_or_said_done(self, store, monkeypatch):
        from modules import host_steps
        monkeypatch.setitem(host_steps.CHECKS, "topology-renderer",
                            lambda root: {"state": "not_done", "detail": "absent"})
        text = _log(("a" * 40, BODY))
        got = host_steps.owed("a" * 40, log_text=text)
        assert got["ok"] and [s["step"] for s in got["steps"]] == [
            "install the renderer as a symlink and restart it", "tell the team"]
        assert host_steps.record_done("a" * 40, "tell the team", "p@example.invalid")["ok"]
        said = host_steps.owed("a" * 40, log_text=text)["said_done"]
        assert [(d["step"], d["by"]) for d in said] == [("tell the team", "p@example.invalid")]
        monkeypatch.setitem(host_steps.CHECKS, "topology-renderer",
                            lambda root: {"state": "done", "detail": "ok"})
        assert host_steps.owed("a" * 40, log_text=text)["steps"] == []

    def test_no_person_records_nothing_and_an_unreadable_record_is_said(self, store):
        from modules import host_steps
        assert not host_steps.record_done("a" * 40, "x", "")["ok"]
        (store / "done.jsonl").write_text("{not json\n")
        got = host_steps.owed("a" * 40, log_text=_log(("a" * 40, BODY)))
        assert not got["ok"] and "could not be read" in got["error"]

    def test_needs_attention_draws_each_owed_step_with_the_update_page(self, store, monkeypatch):
        from modules import attention
        from routes import health
        monkeypatch.setattr(health, "_COMMIT", "a" * 40)
        owed = {"ok": True, "steps": [{"sha": "a" * 40, "step": "tell the team", "id": "a:1",
                                       "check_state": "not_checkable", "check_detail": ""}]}
        (r,) = attention.host_steps_source(owed=owed)["rows"]
        assert r["level"] == "warning" and "tell the team" in r["what"]
        assert r["action"]["open"] == "app_update"
        bad = attention.host_steps_source(owed={"ok": False, "steps": [], "error": "git said no"})
        assert bad["state"] == "unreadable" and "git said no" in json.dumps(bad)


class TestSayingItIsDone:
    def test_the_route_records_only_an_owed_uncheckable_step(self, store, monkeypatch):
        import app as A
        from modules import host_steps, identity
        from routes import health
        monkeypatch.setattr(health, "_COMMIT", "a" * 40)
        monkeypatch.setattr(identity, "request_actor", lambda: "p@example.invalid")
        monkeypatch.setitem(host_steps.CHECKS, "topology-renderer",
                            lambda root: {"state": "not_done", "detail": "absent"})
        monkeypatch.setattr(host_steps, "_log", lambda root, rng, limit, run=None: _log(("a" * 40, BODY)))
        c = A.app.test_client()
        r = c.post("/update/host-step/done", json={"sha": "a" * 40, "step": "tell the team"})
        assert r.status_code == 200 and "p@example.invalid" in r.get_json()["message"]
        row = json.loads((store / "done.jsonl").read_text().splitlines()[0])
        assert row["by"] == "p@example.invalid" and row["step"] == "tell the team"
        r = c.post("/update/host-step/done", json={
            "sha": "a" * 40, "step": "install the renderer as a symlink and restart it"})
        assert r.status_code == 409 and "checks this step itself" in r.get_json()["error"]
        r = c.post("/update/host-step/done", json={"sha": "a" * 40, "step": "invented"})
        assert r.status_code == 409


class TestTheBoxIsReadWhereItIsDrawn:
    def test_the_click_reads_the_boxes_from_the_preview_that_holds_them(self):
        js = (ROOT / "static" / "js" / "nmas_update.js").read_text()
        assert "el.closest('#update-preview')" in js
        html = (ROOT / "templates" / "v2" / "_update.html").read_text()
        preview = html[html.index('id="update-preview"'):]
        assert "data-host-step=" in preview[:preview.index("</section>")]


class TestOneStepAskedTwiceIsOneRow:
    """The operator, 2026-10-01, updating 1954ce7 -> 8bef2e1: "Still to do on the
    host" listed the SAME re-install twice, once for 4a61081 and once for
    dde8495. It is one re-install: one row naming both commits. The two
    commits' REAL trailers, read from git."""

    A, B = "4a610813d7194fc122531d6f8ad4c3129a3e8163", "dde849524de80a9f666892544bdb49dac7c022e0"

    def _text(self):
        out = subprocess.run(["git", "-C", str(ROOT), "log", "--no-walk", "--format=%H%x1f%B%x1e",
                              self.B, self.A], capture_output=True, text=True)
        if out.returncode != 0:
            pytest.skip(f"this checkout lacks the two commits: {out.stderr.strip()[:120]}")
        return out.stdout

    def test_the_updaters_re_install_is_owed_once_naming_both(self, store, monkeypatch):
        from modules import host_steps
        monkeypatch.setitem(host_steps.CHECKS, "updater",
                            lambda root: {"state": "not_done", "detail": "the copy differs"})
        steps = host_steps.owed(self.B, log_text=self._text())["steps"]
        assert len(steps) == 1, steps
        assert steps[0]["shas"] == [self.A, self.B]        # oldest first
        assert steps[0]["step"].startswith("re-install the updater's copy of scripts/nmas-deploy")

    def test_the_page_and_needs_attention_draw_one_row(self, store, monkeypatch):
        import app as A
        from modules import attention, host_steps
        from routes import health
        monkeypatch.setitem(host_steps.CHECKS, "updater",
                            lambda root: {"state": "not_done", "detail": "the copy differs"})
        text = self._text()
        monkeypatch.setattr(host_steps, "_log", lambda root, rng, limit, run=None: text)
        monkeypatch.setattr(health, "_COMMIT", self.B)
        html = A.app.test_client().get("/v2/update/panel").get_data(as_text=True)
        card = html[html.index('id="update-owed-steps"'):]
        card = card[:card.index("</ul>")]
        assert card.count("<li") == 1 and f"({self.A[:10]}, {self.B[:10]})" in card
        (r,) = attention.host_steps_source()["rows"]
        assert f"{self.A[:10]}, {self.B[:10]}" in r["what"]

    def test_saying_one_row_done_says_it_for_each_commit(self, store, monkeypatch):
        import app as A
        from modules import host_steps, identity
        from routes import health
        body = "x\n\nHost-Step-After: tell the team\n"
        text = _log(("b" * 40, body), ("a" * 40, body))
        monkeypatch.setattr(host_steps, "_log", lambda root, rng, limit, run=None: text)
        monkeypatch.setattr(health, "_COMMIT", "b" * 40)
        monkeypatch.setattr(identity, "request_actor", lambda: "p@example.invalid")
        (s,) = host_steps.owed("b" * 40)["steps"]
        r = A.app.test_client().post("/update/host-step/done",
                                     json={"sha": s["sha"], "step": "tell the team"})
        assert r.status_code == 200
        assert host_steps.owed("b" * 40)["steps"] == []
        (d,) = host_steps.owed("b" * 40)["said_done"]
        assert d["shas"] == ["a" * 40, "b" * 40]

    def test_different_steps_stay_apart(self, store):
        from modules import host_steps
        text = _log(("b" * 40, "x\n\nHost-Step-After: tell the team\n"),
                    ("a" * 40, "x\n\nHost-Step-After: tell the other team\n"))
        assert len(host_steps.owed("b" * 40, log_text=text)["steps"]) == 2
