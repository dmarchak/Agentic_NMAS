"""C225: a device's role in the inventory, corrected through one recorded path.

The rows are the host's `default` list as measured 2026-09-30 (the four
switches `router`, r6 with no role; no credential column), written into a
list in the suite's own store through the real CSV writer.
"""

import json
import os
import stat
import subprocess
import sys

import pytest

from tests.test_onboard_pending import repo  # noqa: F401  (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HOST_ROWS = [("s1", "router", "cisco_ios", "10.255.1.21"), ("s2", "router", "cisco_ios", "10.255.1.22"),
             ("r1", "router", "cisco_iosxe", "10.255.1.11"), ("r6", "", "cisco_iosxe", "10.255.0.32")]


@pytest.fixture
def lab():
    from modules import device
    from modules.nsot import listref

    ok, msg = device.create_device_list("RoleLab")
    assert ok, msg
    ref = listref.resolve("RoleLab")
    device.write_devices_csv([{"hostname": h, "role": r, "platform": p, "ip": ip,
                               "device_type": "cisco_ios", "username": "u",
                               "password": "enc-a", "secret": "enc-b"}
                              for h, r, p, ip in HOST_ROWS], ref.csv_path)
    yield ref
    device.delete_device_list("RoleLab") if hasattr(device, "delete_device_list") else None


def _csv(ref):
    return open(ref.csv_path, encoding="utf-8").read()


def _roles(ref):
    from modules.device import load_saved_devices
    return {d["hostname"]: d.get("role", "") for d in load_saved_devices(ref.csv_path)}


class TestThePreview:
    def test_a_switch_called_a_router_is_previewed_and_nothing_is_written(self, lab):
        from modules import inventory_edit as E

        before = _csv(lab)
        p = E.plan("RoleLab", "s1", "switch", "s1 is a vIOS L2 switch, not a router")
        assert p["confirmable"] and (p["before"], p["after"]) == ("router", "switch")
        assert [g["state"] for g in p["gates"]] == ["pass", "pass", "pass"]
        assert p["follows"][0].startswith("Prometheus: s1's SNMP targets carry role='switch' (was 'router')")
        assert any("NetBox: the next import" in f for f in p["follows"])
        assert "No device is contacted and no configuration changes" in p["not_done"]
        assert _csv(lab) == before

    def test_r6_with_no_role_says_its_targets_carried_none(self, lab):
        from modules import inventory_edit as E

        p = E.plan("RoleLab", "r6", "router", "r6 is a C8000v router at the branch site")
        assert p["before"] == "" and "(they carried no role)" in p["follows"][0]

    @pytest.mark.parametrize("role, reason, gate, why", [
        ("core", "the reason is fine here", "a known role", "'core' is not one of router, switch, firewall"),
        ("router", "the reason is fine here", "a change", "already 'router': nothing would change"),
        ("switch", "", "a stated reason", "has no reason"),
        ("switch", "fix", "a stated reason", "too short to be a reason"),
    ])
    def test_each_refusal_is_a_gate_by_name(self, lab, role, reason, gate, why):
        from modules import inventory_edit as E

        p = E.plan("RoleLab", "s1", role, reason)
        assert not p["confirmable"]
        failed = [g for g in p["gates"] if g["state"] == "fail"]
        assert [g["gate"] for g in failed] == [gate] and why in failed[0]["why"]

    def test_an_unknown_device_is_refused_by_name(self, lab):
        from modules import inventory_edit as E

        with pytest.raises(E.RoleEditRefused, match="s9 is not in RoleLab's inventory"):
            E.plan("RoleLab", "s9", "switch", "a reason of the right shape")

    def test_a_netbox_sourced_list_is_refused_naming_netbox(self, lab, monkeypatch):
        from modules import inventory_edit as E

        monkeypatch.setattr("modules.inventory.source_config.is_netbox_sourced", lambda n: True)
        with pytest.raises(E.RoleEditRefused, match="Edit it in NetBox"):
            E.plan("RoleLab", "s1", "switch", "a reason of the right shape")


class TestTheApply:
    REASON = "s1 is a vIOS L2 switch, not a router"

    def test_it_writes_the_one_field_and_records_who_and_why(self, lab):
        from modules import inventory_edit as E
        from modules.device import load_saved_devices

        other = [d for d in load_saved_devices(lab.csv_path) if d["hostname"] != "s1"]
        p = E.plan("RoleLab", "s1", "switch", self.REASON)
        rec = E.apply("RoleLab", "s1", "switch", self.REASON, p["fingerprint"],
                      actor="operator@example.com", actor_verified="access")
        assert rec["recorded"] and _roles(lab)["s1"] == "switch"
        assert [d for d in load_saved_devices(lab.csv_path) if d["hostname"] != "s1"] == other
        s1 = next(d for d in load_saved_devices(lab.csv_path) if d["hostname"] == "s1")
        assert (s1["password"], s1["secret"], s1["ip"]) == ("enc-a", "enc-b", "10.255.1.21")
        path = os.path.join(lab.data_dir, "inventory_edits.jsonl")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        row = json.loads(open(path, encoding="utf-8").read().splitlines()[-1])
        assert {k: row[k] for k in ("device", "field", "before", "after", "reason", "actor",
                                     "actor_verified")} == {
            "device": "s1", "field": "role", "before": "router", "after": "switch",
            "reason": self.REASON, "actor": "operator@example.com", "actor_verified": "access"}
        h = E.history("RoleLab", "s1")
        assert h["state"] == "ok" and h["rows"][0]["after"] == "switch"

    def test_a_moved_inventory_is_refused_naming_both_fingerprints(self, lab):
        from modules import inventory_edit as E

        p = E.plan("RoleLab", "s1", "firewall", self.REASON)
        q = E.plan("RoleLab", "s1", "switch", self.REASON)
        E.apply("RoleLab", "s1", "switch", self.REASON, q["fingerprint"], actor="a", actor_verified="access")
        before = _csv(lab)
        with pytest.raises(E.RoleEditRefused, match=f"confirmed {p['fingerprint']}, now "):
            E.apply("RoleLab", "s1", "firewall", self.REASON, p["fingerprint"], actor="a",
                    actor_verified="access")
        assert _csv(lab) == before

    def test_no_actor_is_refused_before_anything_is_written(self, lab):
        from modules import inventory_edit as E

        p = E.plan("RoleLab", "s1", "switch", self.REASON)
        before = _csv(lab)
        with pytest.raises(E.RoleEditRefused, match="records who"):
            E.apply("RoleLab", "s1", "switch", self.REASON, p["fingerprint"], actor="",
                    actor_verified="none")
        assert _csv(lab) == before

    def test_a_record_that_cannot_be_written_says_the_role_is_written(self, lab, monkeypatch):
        from modules import config, inventory_edit as E

        def boom(*a, **k):
            raise PermissionError("denied")
        p = E.plan("RoleLab", "s1", "switch", self.REASON)
        monkeypatch.setattr(config, "open_secure", boom)
        rec = E.apply("RoleLab", "s1", "switch", self.REASON, p["fingerprint"], actor="a",
                      actor_verified="access")
        assert rec["recorded"] is False and "PermissionError" in rec["record_error"]
        assert _roles(lab)["s1"] == "switch"

    def test_the_edit_is_a_sender_for_the_prometheus_targets(self, lab, monkeypatch):
        from modules import inventory_edit as E, prometheus_targets as P

        sent = []
        monkeypatch.setattr(P, "inventory_changed", sent.append)
        p = E.plan("RoleLab", "s2", "switch", self.REASON)
        E.apply("RoleLab", "s2", "switch", self.REASON, p["fingerprint"], actor="a", actor_verified="access")
        assert sent and sent[-1].endswith("devices.csv was written")

    def test_no_history_is_absent_and_a_damaged_one_unreadable(self, lab):
        from modules import inventory_edit as E

        assert E.history("RoleLab") == {"state": "absent", "rows": []}
        with open(os.path.join(lab.data_dir, "inventory_edits.jsonl"), "w") as fh:
            fh.write("{not json\n")
        assert E.history("RoleLab")["state"] == "unreadable"


class TestTheCommand:
    def _run(self, *args):
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "nmas-inventory-role"),
                               *args], capture_output=True, text=True, timeout=60)

    def test_the_preview_writes_nothing_and_apply_records_the_host_shell(self, lab):
        before = _csv(lab)
        r = self._run("RoleLab", "s1", "switch", "--reason", "s1 is a vIOS L2 switch")
        assert r.returncode == 0, r.stderr
        assert "role router -> switch" in r.stdout and "preview only: nothing written" in r.stdout
        assert _csv(lab) == before
        r = self._run("RoleLab", "s1", "switch", "--reason", "s1 is a vIOS L2 switch", "--apply")
        assert r.returncode == 0, r.stderr
        assert "written and recorded: s1's role is switch" in r.stdout
        row = json.loads(open(os.path.join(lab.data_dir, "inventory_edits.jsonl")).read().splitlines()[-1])
        assert row["actor_verified"] == "host-shell" and _roles(lab)["s1"] == "switch"

    def test_a_refusal_exits_1_and_writes_nothing(self, lab):
        before = _csv(lab)
        r = self._run("RoleLab", "s1", "switch", "--apply")
        assert r.returncode == 1 and "has no reason" in r.stdout and _csv(lab) == before


def test_the_audit_file_is_classified_no_secret():
    src = open(os.path.join(ROOT, "scripts", "nmas-check-secret-storage"), encoding="utf-8").read()
    assert '("lists/*/inventory_edits.jsonl", "no-secret")' in src


class TestANewDeviceIsAskedItsRole:
    """C225's other half (the operator, 2026-09-30): onboarding and adopt
    hard-coded `router`, so the next switch onboarded would be wrong."""

    def test_the_network_suggests_only_when_every_device_on_the_platform_agrees(self, lab):
        from modules import inventory_edit as E

        assert E.suggest_role("RoleLab", "cisco_iosxe") == {}          # r1 router, r6 none
        p = E.plan("RoleLab", "s1", "switch", "a reason of the right shape")
        E.apply("RoleLab", "s1", "switch", "a reason of the right shape", p["fingerprint"],
                actor="a", actor_verified="access")
        assert E.suggest_role("RoleLab", "cisco_ios") == {}            # s1 switch, s2 router
        q = E.plan("RoleLab", "s2", "switch", "a reason of the right shape")
        E.apply("RoleLab", "s2", "switch", "a reason of the right shape", q["fingerprint"],
                actor="a", actor_verified="access")
        assert E.suggest_role("RoleLab", "cisco_ios") == {"role": "switch", "count": 2}

    def test_no_role_is_refused_saying_why_and_naming_the_suggestion(self, lab):
        from modules import inventory_edit as E

        for h in ("s1", "s2"):
            p = E.plan("RoleLab", h, "switch", "a reason of the right shape")
            E.apply("RoleLab", h, "switch", "a reason of the right shape", p["fingerprint"],
                    actor="a", actor_verified="access")
        why = E.role_problem("", "RoleLab", "cisco_ios")
        assert why.startswith("no role was chosen: the role becomes the device's Prometheus role label")
        assert "never guessed from the platform" in why
        assert "Every cisco_ios device in RoleLab is a switch (2), which is a suggestion, not a rule." in why
        assert E.role_problem("core").startswith("'core' is not one of router, switch, firewall")
        assert E.role_problem("Switch") == ""

    def test_the_wizard_plan_refuses_no_role_and_carries_a_chosen_one(self, tmp_path, monkeypatch):
        from modules.nsot.onboard import build_plan

        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.nsot.onboard._name_in_manifest", lambda *a: (False, True))
        monkeypatch.setattr("modules.nsot.onboard._name_in_netbox", lambda *a: (False, True))
        args = dict(hostname="sw9", platform="cisco_ios", list_name="probe", mgmt_ip="203.0.113.9",
                    mgmt_mask="255.255.255.0", manager_interface="GigabitEthernet0/1",
                    secret="bootstrap-only")
        none = build_plan(**args)
        assert any(r.startswith("no role was chosen") for r in none.blocking_reasons)
        chosen = build_plan(role="switch", **args)
        assert not any("role" in r for r in chosen.blocking_reasons)
        assert chosen.role == "switch" and chosen.summary["role"] == "switch"

    def test_the_role_reaches_the_manifest_and_the_promoted_row(self, repo):
        from modules.config import get_list_data_dir
        from modules.device import load_saved_devices
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import promote_device
        from modules.nsot.repo import GoldenItem, adopt_identity

        identity = adopt_identity(repo, GoldenItem("sw9", "", "203.0.113.39"))
        _m.upsert_device(repo, identity, "sw9", mgmt_ip="203.0.113.39", platform="cisco_ios",
                         pending=True, role="switch")
        assert _m.find_by_name(repo, "sw9")[1]["role"] == "switch"
        out = promote_device(repo, "sw9", "probe", username="admin", password="Rotated-9", secret="")
        assert out.get("ok"), out
        row = load_saved_devices(os.path.join(get_list_data_dir("probe"), "devices.csv"))[0]
        assert row["role"] == "switch"

    def test_neither_onboarding_nor_adopt_hard_codes_router_any_more(self):
        for path in ("modules/nsot/onboard.py", "modules/nsot/adopt.py"):
            src = open(os.path.join(ROOT, path), encoding="utf-8").read()
            assert '"role": "router"' not in src, path

    def test_adopt_asks_it_first_among_the_gates(self):
        src = open(os.path.join(ROOT, "modules", "nsot", "adopt.py"), encoding="utf-8").read()
        assert 'gate("role", not problem' in src and '"role": role,' in src


def test_a_host_command_is_labelled_never_a_bare_login(lab):
    from modules import inventory_edit as E

    p = E.plan("RoleLab", "s1", "switch", "s1 is a vIOS L2 switch")
    rec = E.apply("RoleLab", "s1", "switch", "s1 is a vIOS L2 switch", p["fingerprint"],
                  actor="someone", actor_verified="host-shell")
    assert rec["actor_label"] == "someone (host login, not a verified identity)"
    assert E.actor_label("op@example.com", "access") == "op@example.com"
    # A row written before the label existed is labelled when read.
    path = os.path.join(lab.data_dir, "inventory_edits.jsonl")
    lines = open(path).read().splitlines()
    old = json.loads(lines[-1])
    old.pop("actor_label")
    open(path, "w").write(json.dumps(old) + "\n")
    assert E.history("RoleLab")["rows"][0]["actor_label"] == "someone (host login, not a verified identity)"
