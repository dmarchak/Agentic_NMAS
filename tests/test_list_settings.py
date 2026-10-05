"""P.8 step 2: a network's settings, and the one resolver (NSOT_P8_DESIGN, sections 2 and 3).

The Default network's layer is the global settings file (decision 1: nothing copied). Another
list keeps its own `settings.json`; a network-scoped key resolves to the list's own value, else
Default's, except that an integration inherits as a GROUP: setting any key of a group makes the
group the list's own, and its other keys read their schema default, never Default's (a list's
own Grafana never receives Default's token). A declaration of "not applicable here" stops the
lookup. Host-wide keys are the global value for every list. Driven on a temporary store, with
real child processes for the concurrent writes.
"""

import json
import os
import stat
import subprocess
import sys

import pytest

from modules import config
from modules import list_settings as L

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A temporary data folder whose global settings set Default's Grafana."""
    from modules.secrets_store import encrypt_value

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
    settings = tmp_path / "user_settings.json"
    settings.write_text(json.dumps({"grafana_url": "http://192.0.2.10:3000",
                                    "grafana_token": encrypt_value("default-token"),
                                    "flask_port": 5000}), encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(settings))
    return tmp_path


class TestResolving:
    def test_default_is_the_global_file(self, store):
        assert L.resolve("Default", "grafana_url") == ("http://192.0.2.10:3000", L.SET_HERE)
        assert L.resolve("Default", "loki_url")[1] == L.UNSET_EVERYWHERE
        assert L.secret("Default", "grafana_token") == "default-token"

    def test_another_list_inherits_defaults_group(self, store):
        assert L.resolve("Branch", "grafana_url") == ("http://192.0.2.10:3000", L.INHERITED)
        assert L.secret("Branch", "grafana_token") == "default-token"

    def test_a_group_set_here_is_this_lists_own_and_never_gets_defaults_credential(self, store):
        assert L.write("Branch", {"grafana_url": "http://192.0.2.20:3000"})["ok"] is True
        assert L.resolve("Branch", "grafana_url") == ("http://192.0.2.20:3000", L.SET_HERE)
        value, origin = L.resolve("Branch", "grafana_token")
        assert origin == L.UNSET_HERE and value == ""
        assert L.secret("Branch", "grafana_token") == "", "Default's token went to another Grafana"
        # Another group is untouched: still inherited.
        assert L.resolve("Branch", "prometheus_url")[1] in (L.INHERITED, L.UNSET_EVERYWHERE)

    def test_a_secret_set_here_is_encrypted_at_rest_and_read_back(self, store):
        L.write("Branch", {"grafana_url": "http://192.0.2.20:3000", "grafana_token": "branch-t"})
        raw = (store / "lists" / "branch" / "settings.json").read_text(encoding="utf-8")
        assert "branch-t" not in raw
        assert L.secret("Branch", "grafana_token") == "branch-t"
        p = store / "lists" / "branch" / "settings.json"
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600

    def test_not_applicable_stops_the_lookup(self, store):
        p = store / "lists" / "branch"
        p.mkdir(parents=True)
        (p / "settings.json").write_text(json.dumps({"values": {}, "not_applicable": {
            "grafana": {"by": "a@example.invalid", "why": "no Grafana"}}}), encoding="utf-8")
        assert L.resolve("Branch", "grafana_url") == (None, L.NOT_APPLICABLE)

    def test_a_host_key_is_the_global_value_for_every_list(self, store):
        assert L.resolve("Branch", "flask_port") == (5000, L.HOST)


class TestWriting:
    def test_a_host_key_is_refused_for_a_list(self, store):
        out = L.write("Branch", {"flask_port": 5001, "grafana_url": "http://192.0.2.20:3000"})
        assert out["ok"] is False and out["refused"] == ["flask_port"]
        assert not (store / "lists" / "branch" / "settings.json").exists()

    def test_defaults_write_goes_to_the_global_file(self, store):
        assert L.write("Default", {"loki_url": "http://192.0.2.10:3100"})["ok"] is True
        stored = json.loads((store / "user_settings.json").read_text(encoding="utf-8"))
        assert stored["loki_url"] == "http://192.0.2.10:3100"

    def test_an_unreadable_store_refuses_and_is_kept(self, store):
        p = store / "lists" / "branch"
        p.mkdir(parents=True)
        (p / "settings.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(L.ListSettingsUnreadable):
            L.resolve("Branch", "grafana_url")
        out = L.write("Branch", {"grafana_url": "http://192.0.2.20:3000"})
        assert out["ok"] is False and "could not be read" in out["error"]
        assert (p / "settings.json").read_text(encoding="utf-8") == "{not json"


def _store_doc(store, name="branch"):
    p = store / "lists" / name / "settings.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _standalone(store, name="branch", **extra):
    p = store / "lists" / name
    p.mkdir(parents=True, exist_ok=True)
    doc = {"values": {}, "not_applicable": {}, "mode": "standalone"}
    doc.update(extra)
    (p / "settings.json").write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture
def with_loki(store):
    """Default also sets Loki, so two groups are inherited today."""
    p = store / "user_settings.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["loki_url"] = "http://192.0.2.10:3100"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return store


class TestInheritingIsAChoice:
    """NSOT_P8_DESIGN section 8 (the operator, 2026-10-05): a network inherits from Default
    or is standalone; each group chooses inherit, its own or not applicable; a standalone
    network's unset value is "not configured for this network", never Default's."""

    def test_a_store_with_no_mode_behaves_exactly_as_before(self, store):
        p = store / "lists" / "branch"
        p.mkdir(parents=True)
        (p / "settings.json").write_text(json.dumps({"values": {}, "not_applicable": {}}),
                                         encoding="utf-8")
        assert L.mode("Branch") == L.INHERIT
        assert L.resolve("Branch", "grafana_url") == ("http://192.0.2.10:3000", L.INHERITED)
        assert L.secret("Branch", "grafana_token") == "default-token"

    def test_a_standalone_network_never_reads_defaults_value_or_secret(self, store):
        _standalone(store)
        assert L.resolve("Branch", "grafana_url") == ("", L.NOT_CONFIGURED)
        assert L.secret("Branch", "grafana_token") == "", "Default's token reached a standalone"
        assert L.value("Branch", "grafana_url", "fallback") == "fallback"
        # A group of one reads its schema default, never Default's.
        assert L.resolve("Branch", "deploy_max_workers") == (1, L.NOT_CONFIGURED)

    def test_a_standalone_networks_group_that_chose_inherit_reads_defaults(self, store):
        _standalone(store, groups={"grafana": "inherit"})
        assert L.resolve("Branch", "grafana_url") == ("http://192.0.2.10:3000", L.INHERITED)
        assert L.secret("Branch", "grafana_token") == "default-token"
        assert L.resolve("Branch", "loki_url")[1] == L.NOT_CONFIGURED

    def test_own_with_nothing_set_is_not_configured(self, store):
        p = store / "lists" / "branch"
        p.mkdir(parents=True)
        (p / "settings.json").write_text(json.dumps({"values": {}, "not_applicable": {},
                                                     "groups": {"grafana": "own"}}),
                                         encoding="utf-8")
        assert L.resolve("Branch", "grafana_url") == ("", L.NOT_CONFIGURED)
        assert L.secret("Branch", "grafana_token") == ""
        assert L.resolve("Branch", "loki_url")[1] in (L.INHERITED, L.UNSET_EVERYWHERE)

    def test_not_applicable_still_stops_the_lookup_in_a_standalone_network(self, store):
        _standalone(store, not_applicable={"grafana": {"by": "a", "why": "no Grafana here"}})
        assert L.resolve("Branch", "grafana_url") == (None, L.NOT_APPLICABLE)

    def test_a_write_keeps_the_mode_and_the_groups_choices(self, store):
        _standalone(store, groups={"loki": "inherit", "kea": "own"})
        assert L.write("Branch", {"deploy_max_workers": 3})["ok"] is True
        doc = _store_doc(store)
        assert doc["mode"] == "standalone"
        assert doc["groups"] == {"loki": "inherit", "kea": "own"}

    def test_a_value_written_to_a_group_that_chose_inherit_makes_it_its_own(self, store):
        _standalone(store, groups={"grafana": "inherit"})
        L.write("Branch", {"grafana_url": "http://192.0.2.20:3000"})
        assert _store_doc(store)["groups"]["grafana"] == "own"
        assert L.secret("Branch", "grafana_token") == ""


class TestTheModeSwitch:
    def test_standalone_names_exactly_the_inherited_groups_that_become_unconfigured(
            self, with_loki):
        L.write("Branch", {"prometheus_url": "http://192.0.2.40:9090"})
        plan = L.plan_mode("Branch", L.STANDALONE)
        assert sorted(plan["unconfigured"]) == ["Grafana", "Loki"]
        moving = {r["group"]: (r["today_state"], r["after_state"]) for r in plan["moving"]}
        assert moving["grafana"] == ("inherited", "not_configured")
        assert "prometheus" not in moving, "a group with its own values moved with the mode"
        assert plan["confirmable"] is True
        assert "Grafana and Loki are inherited from Default today" in " ".join(plan["what"])

    def test_a_groups_own_choice_stands_when_the_mode_moves(self, with_loki):
        p = with_loki / "lists" / "branch"
        p.mkdir(parents=True)
        (p / "settings.json").write_text(json.dumps(
            {"values": {}, "not_applicable": {}, "groups": {"loki": "inherit"}}),
            encoding="utf-8")
        plan = L.plan_mode("Branch", L.STANDALONE)
        assert plan["unconfigured"] == ["Grafana"]
        assert "Loki" in " ".join(plan["what_not"])

    def test_the_reverse_names_what_it_picks_up(self, with_loki):
        _standalone(with_loki)
        plan = L.plan_mode("Branch", L.INHERIT)
        assert sorted(plan["picked"]) == ["Grafana", "Loki"]
        assert "picks up Default's" in " ".join(plan["what"])

    def test_a_preview_writes_nothing(self, store):
        L.plan_mode("Branch", L.STANDALONE)
        L.plan_group("Branch", "grafana", L.NA, reason="no Grafana at this site at all")
        assert not (store / "lists" / "branch").exists()

    def test_a_preview_never_carries_a_secret(self, store):
        raw = json.dumps([L.plan_mode("Branch", L.STANDALONE),
                          L.plan_group("Branch", "grafana", L.OWN,
                                       values={"grafana_token": "branch-secret-t"})])
        assert "default-token" not in raw and "branch-secret-t" not in raw
        stored = json.loads((store / "user_settings.json").read_text())["grafana_token"]
        assert stored not in raw, "the stored ciphertext reached a preview"

    def test_apply_switches_and_records(self, with_loki):
        plan = L.plan_mode("Branch", L.STANDALONE)
        out = L.apply_mode("Branch", L.STANDALONE, plan["fingerprint"], "op@example.invalid",
                           "access", seen=plan["operands"])
        assert out["recorded"] is True and out["kind"] == "mode"
        assert L.mode("Branch") == L.STANDALONE
        assert L.resolve("Branch", "grafana_url")[1] == L.NOT_CONFIGURED
        rec = L.changes("Branch")
        assert rec["state"] == "ok" and rec["rows"][0]["actor"] == "op@example.invalid"
        assert {m[0] for m in rec["rows"][0]["moved"]} >= {"grafana", "loki"}
        p = with_loki / "lists" / "branch" / L.RECORD
        assert stat.S_IMODE(os.stat(p).st_mode) == 0o600

    def test_a_confirm_whose_settings_moved_is_refused_naming_both(self, with_loki):
        plan = L.plan_mode("Branch", L.STANDALONE)
        # Another person changes Default's Grafana between the preview and the confirm.
        L.write("Default", {"grafana_url": "http://192.0.2.99:3000"})
        with pytest.raises(L.SwitchRefused) as exc:
            L.apply_mode("Branch", L.STANDALONE, plan["fingerprint"], "op@example.invalid",
                         seen=plan["operands"])
        msg = str(exc.value)
        assert "http://192.0.2.10:3000" in msg and "http://192.0.2.99:3000" in msg
        assert "Nothing was saved" in msg
        assert L.mode("Branch") == L.INHERIT

    def test_no_actor_and_the_default_network_are_refused(self, store):
        plan = L.plan_mode("Branch", L.STANDALONE)
        with pytest.raises(L.SwitchRefused):
            L.apply_mode("Branch", L.STANDALONE, plan["fingerprint"], "")
        with pytest.raises(L.SwitchRefused):
            L.plan_mode("Default", L.STANDALONE)


class TestTheGroupSwitch:
    def test_back_to_inheriting_removes_its_values_and_the_record_keeps_them(self, store):
        L.write("Branch", {"grafana_url": "http://192.0.2.20:3000", "grafana_token": "br-t"})
        plan = L.plan_group("Branch", "grafana", L.INHERIT)
        assert plan["removed"] == ["grafana_token", "grafana_url"]
        rows = {r["key"]: r for r in plan["rows"]}
        assert rows["grafana_url"]["after"] == "http://192.0.2.10:3000"
        assert rows["grafana_token"]["today"] == "set"
        out = L.apply_group("Branch", "grafana", L.INHERIT, plan["fingerprint"],
                            "op@example.invalid", "access", seen=plan["operands"])
        assert L.resolve("Branch", "grafana_url") == ("http://192.0.2.10:3000", L.INHERITED)
        assert out["removed"]["grafana_url"] == "http://192.0.2.20:3000"
        raw = (store / "lists" / "branch" / L.RECORD).read_text()
        assert "br-t" not in raw, "a removed secret reached the record in plain text"
        from modules.secrets_store import decrypt_value
        assert decrypt_value(out["removed"]["grafana_token"]) == "br-t"

    def test_its_own_with_values_writes_them_encrypted(self, store):
        plan = L.plan_group("Branch", "grafana", L.OWN,
                            values={"grafana_url": "http://192.0.2.60:3000",
                                    "grafana_token": "own-t"})
        L.apply_group("Branch", "grafana", L.OWN, plan["fingerprint"], "op@example.invalid",
                      values={"grafana_url": "http://192.0.2.60:3000",
                              "grafana_token": "own-t"}, seen=plan["operands"])
        assert L.secret("Branch", "grafana_token") == "own-t"
        assert "own-t" not in (store / "lists" / "branch" / "settings.json").read_text()

    def test_values_typed_in_the_confirm_card_are_validated_and_written_as_sent(self, store):
        """Boards B and C take the values in the confirm card itself: the fingerprint binds
        TODAY's values as shown, and what is typed is validated at apply, never trusted."""
        plan = L.plan_group("Branch", "grafana", L.OWN)
        with pytest.raises(L.SwitchRefused) as exc:
            L.apply_group("Branch", "grafana", L.OWN, plan["fingerprint"], "op@example.invalid",
                          values={"grafana_verify_tls": "not a switch"}, seen=plan["operands"])
        assert "grafana_verify_tls" in str(exc.value)
        L.apply_group("Branch", "grafana", L.OWN, plan["fingerprint"], "op@example.invalid",
                      values={"grafana_url": "http://192.0.2.61:3000"}, seen=plan["operands"])
        assert L.resolve("Branch", "grafana_url") == ("http://192.0.2.61:3000", L.SET_HERE)

    def test_a_forged_fingerprint_is_refused(self, store):
        plan = L.plan_group("Branch", "grafana", L.NA, reason="no Grafana at this site")
        with pytest.raises(L.SwitchRefused) as exc:
            L.apply_group("Branch", "grafana", L.NA, "0" * 16, "op@example.invalid",
                          reason="no Grafana at this site", seen=plan["operands"])
        assert "not that preview's" in str(exc.value)

    def test_not_applicable_needs_a_reason_and_records_who(self, store):
        plan = L.plan_group("Branch", "kea", L.NA, reason="")
        assert plan["confirmable"] is False
        reason = "addresses come from the ISP's DHCP here"
        plan = L.plan_group("Branch", "kea", L.NA, reason=reason)
        L.apply_group("Branch", "kea", L.NA, plan["fingerprint"], "op@example.invalid",
                      reason=reason, seen=plan["operands"])
        decl = _store_doc(store)["not_applicable"]["kea"]
        assert decl["by"] == "op@example.invalid" and decl["why"] == reason
        assert L.resolve("Branch", "kea_url") == (None, L.NOT_APPLICABLE)

    def test_a_switch_to_what_it_already_is_is_refused(self, store):
        plan = L.plan_group("Branch", "grafana", L.INHERIT)
        assert plan["confirmable"] is False
        assert "already inherit from Default" in plan["gates"][-1]["why"]


HOLDER = '''
import sys, time
sys.path.insert(0, {root!r})
from modules.filestore import PathLock
with PathLock(sys.argv[1]):
    print("held", flush=True)
    time.sleep(2)
'''


def test_a_write_waits_while_another_process_holds_the_lists_store(store):
    """The store's read-modify-write holds its lock across processes: with the lock held
    elsewhere for 2 s, a write lands only after it is let go, and the holder's absence of a
    write cannot be overwritten by a stale copy. (A race test of two writers could not fail:
    the overlap a lost update needs is narrower than one write, so it is shown this way.)"""
    import time

    p = store / "lists" / "branch"
    p.mkdir(parents=True)
    holder = subprocess.Popen([sys.executable, "-c", HOLDER.format(root=ROOT),
                               str(p / "settings.json")], stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    started = time.time()
    assert L.write("Branch", {"deploy_max_workers": 3})["ok"] is True
    waited = time.time() - started
    holder.communicate(timeout=30)
    assert waited >= 1.5, f"the write landed after {waited:.2f} s while the lock was held"
