"""Board FC phase 2 (b), PHASE8_PLAN 22.2 (1) and (2): a layer's change planned across the devices
it reaches, nothing sent and nothing written (`modules/nsot/fleet_change.plan_layer`), on r2's
real config and committed intent (`tests.test_capture.build_capture_lab`) through the deploy's
own `plan_devices`, r2's inventory row tagged.

- **A tag layer gaining an NTP server** r2 lacks: r2's change is that one line, "1 device, 1
  group", and nothing is committed (the repository's HEAD unmoved, no layer file).
- **r2's own value** over the change: r2 is unchanged, "this device" holds it.
- **A before the layer does not hold** refuses the change naming the path and both values.
- **What a layer cannot carry** (interfaces) and **a secret value** are refused before any
  device is planned.
- **An unreadable inventory** refuses by name; **a group no device has** says so.
- **One hash:** the same plan twice is one hash; another after is another.
"""

import subprocess

import pytest

from modules.nsot import bulk_intent as B
from modules.nsot import fleet_change as F
from tests.test_monitoring_profile_plan import _intent, lab  # noqa: F401

NTP = [{"path": ["ntp_servers"], "before": B.ABSENT, "after": ["192.0.2.123"]}]


@pytest.fixture
def r2(lab, monkeypatch):  # noqa: F811
    """r2 holding no NTP server of its own (committed), its row tagged blind-lab."""
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars

    intent = _intent(lab["repo"])
    intent["ntp_servers"] = []
    hostvars.write_committed(lab["repo"], intent)
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    from modules.nsot import restore
    real = restore._devices_of
    rows = [dict(r, _tags=["blind-lab"] if r.get("hostname") == "r2" else [])
            for r in real("Lab")]
    assert any(r["hostname"] == "r2" for r in rows), rows
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(r) for r in rows])
    return {"repo": lab["repo"], "rows": rows}


def _head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


class TestATagLayersChange:
    def test_r2s_change_is_the_one_line_and_nothing_is_committed(self, r2):
        import os
        head = _head(r2["repo"])
        got = F.plan_layer("Lab", "tag-blind-lab", NTP)
        assert got["ok"], got["error"]
        assert got["devices"] == [{"device": "r2", "change": ["ntp server 192.0.2.123"],
                                   "pending": got["devices"][0]["pending"],
                                   "command_hash": got["devices"][0]["command_hash"]}]
        assert got["headline"] == "1 device, 1 group"
        assert got["groups"] == [{"lines": ["ntp server 192.0.2.123"], "devices": ["r2"]}]
        assert got["layer"]["file"] == "layers/tag-blind-lab.yml" and got["layer"]["before"] == {}
        assert _head(r2["repo"]) == head, "a plan commits nothing"
        assert not os.path.exists(os.path.join(r2["repo"], "layers"))

    def test_the_devices_own_value_leaves_it_unchanged_naming_who_holds_it(self, r2):
        from modules.nsot import hostvars
        from modules.nsot.repo import save_host_vars
        intent = _intent(r2["repo"])
        intent["ntp_servers"] = ["192.0.2.200"]
        hostvars.write_committed(r2["repo"], intent)
        assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
        got = F.plan_layer("Lab", "tag-blind-lab", NTP)
        assert got["ok"] and got["devices"] == [], got
        assert got["unchanged"] == [{"device": "r2", "by": "this device"}], got["unchanged"]


    def test_lines_already_pending_are_counted_never_called_the_change(self, r2):
        from modules.nsot import hostvars
        from modules.nsot.repo import save_host_vars
        intent = _intent(r2["repo"])
        intent["domain_name"] = "pending.example"            # committed, never deployed
        hostvars.write_committed(r2["repo"], intent)
        assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
        got = F.plan_layer("Lab", "tag-blind-lab", NTP)
        [d] = got["devices"]
        assert d["change"] == ["ntp server 192.0.2.123"], d
        assert d["pending"] >= 1, "the pending domain line rides along and is counted"

    def test_a_device_already_holding_the_value_says_so(self, r2):
        """r2's golden holds `ntp server 10.255.1.10` (its captured config) and its own intent
        no longer names it: the layer naming it changes nothing on r2."""
        got = F.plan_layer("Lab", "tag-blind-lab", [dict(NTP[0], after=["10.255.1.10"])])
        assert got["ok"] and got["devices"] == [], got
        assert got["unchanged"] == [{"device": "r2", "by":
                                     "nothing to send: the device already holds it"}], got


class TestRefusedBeforeAnyDevice:
    def test_a_before_the_layer_does_not_hold_names_the_path_and_both(self, r2):
        got = F.plan_layer("Lab", "tag-blind-lab", [
            {"path": ["ntp_servers"], "before": ["192.0.2.1"], "after": ["192.0.2.123"]}])
        assert not got["ok"]
        assert 'ntp_servers holds nothing, the change expected ["192.0.2.1"]' in got["error"]

    def test_a_per_device_section_is_refused(self, r2):
        got = F.plan_layer("Lab", "tag-blind-lab", [
            {"path": ["interfaces"], "before": B.ABSENT, "after": [{"name": "Gi2"}]}])
        assert not got["ok"] and "interfaces describes one device" in got["error"], got

    def test_a_value_a_reached_device_holds_is_refused(self, r2, monkeypatch):
        """A stored value pasted into a layer: the guard reads each reached device's values
        (it narrows by device), so r2's is found. The capture lab's store answers no value,
        so r2's one value is the store's answer here."""
        from modules import credentials
        value, key = "Lab-Not-Real-Value-77", "lab:r2:user_lab_secret"
        monkeypatch.setattr(credentials, "list_template_secrets",
                            lambda list_name="": [{"name": key}])
        monkeypatch.setattr(credentials, "get_template_secret",
                            lambda name: value if name == key else "")
        got = F.plan_layer("Lab", "tag-blind-lab", [
            {"path": ["domain_name"], "before": B.ABSENT, "after": value}])
        assert not got["ok"] and "secret value" in got["error"], got
        assert value not in got["error"], "the refusal never prints the value"

    def test_an_entry_that_does_not_render_is_refused_not_raised(self, r2):
        got = F.plan_layer("Lab", "tag-blind-lab", [
            {"path": ["users"], "before": B.ABSENT, "after": [{"name": "lab", "privilege": 15}]}])
        assert not got["ok"] and got["error"].startswith("the change does not render"), got


class TestItsGroup:
    def test_an_unreadable_inventory_refuses_by_name(self, r2, monkeypatch):
        def down(list_name):
            raise ConnectionError("NetBox answered 503")
        monkeypatch.setattr("modules.nsot.restore._devices_of", down)
        got = F.plan_layer("Lab", "tag-blind-lab", NTP)
        assert not got["ok"] and "NetBox answered 503" in got["error"]
        assert "no group is taken from an earlier read" in got["error"]

    def test_a_group_no_device_has_says_so(self, r2):
        got = F.plan_layer("Lab", "tag-nobody", NTP)
        assert not got["ok"] and "reaches no device" in got["error"], got


class TestTheHash:
    def test_one_plan_is_one_hash_and_another_after_another(self, r2):
        a, b = F.plan_layer("Lab", "tag-blind-lab", NTP), F.plan_layer("Lab", "tag-blind-lab", NTP)
        assert a["hash"] and a["hash"] == b["hash"]
        other = F.plan_layer("Lab", "tag-blind-lab", [dict(NTP[0], after=["192.0.2.124"])])
        assert other["ok"] and other["hash"] != a["hash"]

    def test_the_after_moves_the_hash_when_no_program_does(self, r2):
        """r2's own value overrides both afters, so no device's program differs: the layer's
        after alone must still move the hash, or one approval would cover another change."""
        from modules.nsot import hostvars
        from modules.nsot.repo import save_host_vars
        intent = _intent(r2["repo"])
        intent["ntp_servers"] = ["192.0.2.200"]
        hostvars.write_committed(r2["repo"], intent)
        assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
        a = F.plan_layer("Lab", "tag-blind-lab", NTP)
        b = F.plan_layer("Lab", "tag-blind-lab", [dict(NTP[0], after=["192.0.2.124"])])
        assert a["devices"] == b["devices"] == [] and a["hash"] != b["hash"]
