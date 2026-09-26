"""Register C31: "nothing to set here" is a recorded decision, not an empty
setting.

`yang_push_script` was empty on the host, and the script it names was dead:
nothing ran it, and its credential was the vrnetlab factory default that no
device had accepted since 2026-09-22. Setting the key would have made job
health read `ok` for a script that cannot work. Leaving it empty read
`unset_guard`, which says somebody forgot. Neither was true.
"""

import importlib.machinery
import importlib.util
import os

import pytest

from modules import job_health as J
from modules import settings_schema as ss

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = "yang_push_script"
GUARDS = {KEY: ["the rotation's consumer warning"],
          "clab_host": ["verify_startup_file"]}


@pytest.fixture
def store(monkeypatch):
    data = {}
    monkeypatch.setattr(ss, "load_user_settings", lambda: dict(data))
    monkeypatch.setattr(ss, "save_user_settings",
                        lambda d: (data.clear(), data.update(d)))
    return data


def _rows(store):
    return {r["unit"]: r for r in J.settings_rows(GUARDS, load=lambda: dict(store))}


class TestTheDeclaration:
    def test_it_records_who_when_and_why(self, store):
        out = ss.declare_not_applicable(KEY, "dmarchak", "script retired (C31)")
        assert out["ok"], out
        d = store["settings_not_applicable"][KEY]
        assert d["by"] == "dmarchak" and d["reason"] == "script retired (C31)"
        assert d["at"].endswith("Z")

    @pytest.mark.parametrize("actor,reason", [("", "why"), ("me", ""), ("me", "   ")])
    def test_no_actor_or_no_reason_is_refused(self, store, actor, reason):
        assert not ss.declare_not_applicable(KEY, actor, reason)["ok"]
        assert "settings_not_applicable" not in store

    def test_a_set_key_is_refused(self, store):
        """A value and a declaration that it has none would contradict."""
        store[KEY] = "/home/x/yang-push-sub.py"
        out = ss.declare_not_applicable(KEY, "me", "retired")
        assert not out["ok"] and "SET" in out["error"]

    def test_a_key_with_a_non_empty_default_is_refused(self, store):
        assert not ss.declare_not_applicable("syslog_trap_level", "me", "x")["ok"]

    def test_withdraw_removes_it(self, store):
        ss.declare_not_applicable(KEY, "me", "retired")
        assert ss.withdraw_not_applicable(KEY, "me")["ok"]
        assert KEY not in store["settings_not_applicable"]


class TestJobHealthTellsTheTwoApart:
    def test_forgotten_is_unset_guard(self, store):
        """The floor: an undeclared empty key still reads as a gap."""
        assert _rows(store)[f"setting:{KEY}"]["state"] == "unset_guard"

    def test_declared_is_not_applicable_and_names_who(self, store):
        ss.declare_not_applicable(KEY, "dmarchak", "script retired (C31)")
        row = _rows(store)[f"setting:{KEY}"]
        assert row["state"] == "not_applicable"
        assert "dmarchak" in row["detail"] and "script retired" in row["detail"]
        assert _rows(store)["setting:clab_host"]["state"] == "unset_guard"

    def test_set_and_declared_is_a_contradiction(self, store):
        ss.declare_not_applicable(KEY, "me", "retired")
        store[KEY] = "/home/x/yang-push-sub.py"
        assert _rows(store)[f"setting:{KEY}"]["state"] == "contradiction"

    def test_health_counts_it_without_calling_it_a_fault(self):
        rows = [{"unit": "setting:a", "state": "not_applicable", "detail": ""},
                {"unit": "setting:b", "state": "contradiction", "detail": ""}]
        h = J.health(0, run=lambda cmd: (1, ""), images=[], settings=rows,
                     rotations=[], owner=[])
        assert "setting:a" not in h["not_ok"] and "setting:b" in h["not_ok"]
        assert "declared not applicable" in h["headline"]


class TestTheRotationStopsWarningAboutARetiredConsumer:
    def test_a_declared_consumer_is_not_listed(self, store):
        from modules.nsot import credential_rotation as cr
        ss.declare_not_applicable(KEY, "me", "retired")
        names = [c["name"] for c in cr.consumer_report("r1", "192.0.2.1")]
        assert "yang-push-sub.py" not in names and "Oxidized" in names

    def test_an_undeclared_one_still_is(self, store):
        """The floor: forgetting the setting must still warn."""
        from modules.nsot import credential_rotation as cr
        names = [c["name"] for c in cr.consumer_report("r1", "192.0.2.1")]
        assert "yang-push-sub.py" in names


def _script():
    path = os.path.join(ROOT, "scripts", "nmas-setting-not-applicable")
    loader = importlib.machinery.SourceFileLoader("nmas_setting_na", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


class TestTheScript:
    def test_it_declares_as_the_os_user(self, store, monkeypatch):
        monkeypatch.setattr("getpass.getuser", lambda: "dmarchak")
        assert _script().main([KEY, "--reason", "retired"]) == 0
        assert store["settings_not_applicable"][KEY]["by"] == "dmarchak"

    def test_a_refusal_exits_1(self, store, capsys):
        assert _script().main([KEY]) == 1
        assert "REFUSED" in capsys.readouterr().err
