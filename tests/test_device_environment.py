"""What a device's environment owns, read from NetBox (C663 step 3, the operator, 2026-10-11).

The emulator's boot workarounds were platform tables in Mercury's code (an injected account on
every C8000v, Gi1 and Gi0/0 reserved by platform). They are NetBox facts now, per device: the
interfaces NetBox marks management-only, and the config context's `environment_owned_lines`.
A device with none has none; a NetBox that cannot be read refuses, never "nothing there".
"""

import pytest

from modules.nsot import device_environment as DE
from tests.fake_netbox import FakeNetBox

BASE = "http://netbox.example.invalid"


def _world(context=None, mgmt=("GigabitEthernet1",), plain=("GigabitEthernet2",),
           name="r6"):
    nb = FakeNetBox()
    dev = nb.seed("dcim/devices", {"name": name, "config_context": context or {}})
    for n in mgmt:
        nb.seed("dcim/interfaces", {"name": n, "device": {"id": dev["id"]}, "mgmt_only": True})
    for n in plain:
        nb.seed("dcim/interfaces", {"name": n, "device": {"id": dev["id"]}, "mgmt_only": False})
    return nb, (lambda: (True, "", nb, BASE))


EMULATED = {DE.CONTEXT_KEY: ["username admin privilege 15 password admin",
                             "ip ssh maxstartups 128"]}


class TestItReadsTheTwoFacts:
    def test_the_management_only_interfaces_are_reserved_and_no_other(self):
        _nb, ready = _world()
        env = DE.read("r6", ready=ready)
        assert list(env.reserved) == ["GigabitEthernet1"], "the control: Gi2 is not mgmt_only"
        assert "management-only (mgmt_only)" in env.reserved["GigabitEthernet1"]
        assert env.source.startswith("NetBox device r6 (id ")

    def test_the_owned_lines_say_an_injected_account_and_ssh(self):
        _nb, ready = _world(EMULATED)
        env = DE.read("r6", ready=ready)
        assert env.injects_user is True and env.owns_ssh is True

    def test_a_device_with_none_has_none(self):
        _nb, ready = _world({}, mgmt=())
        env = DE.read("r6", ready=ready)
        assert env.reserved == {} and env.owned_lines == ()
        assert env.injects_user is False and env.owns_ssh is False

    def test_a_username_word_elsewhere_is_not_an_injected_account(self):
        """`username` must open the line: a description naming it is not an account."""
        _nb, ready = _world({DE.CONTEXT_KEY: [" description the username lives here"]})
        assert DE.read("r6", ready=ready).injects_user is False


class TestAbsentAndUnreadableAreDifferent:
    def test_not_configured_is_an_empty_environment_said_by_its_source(self):
        env = DE.read("r6", ready=lambda: (False, "not configured", None, ""))
        assert env == DE.Environment(source="NetBox is not configured")

    def test_not_in_netbox_is_an_empty_environment_said_by_its_source(self):
        _nb, ready = _world()
        env = DE.read("s9", ready=ready)
        assert env.reserved == {} and env.source == "s9 is not in NetBox"

    def test_an_unreadable_netbox_refuses(self):
        class Down:
            def get(self, *a, **k):
                raise ConnectionError("refused")

        with pytest.raises(DE.EnvironmentUnreadable) as err:
            DE.read("r6", ready=lambda: (True, "", Down(), BASE))
        assert "NetBox could not be asked for r6" in str(err.value)

    def test_two_devices_of_one_name_refuse_naming_both(self):
        nb, ready = _world()
        nb.seed("dcim/devices", {"name": "r6"})
        with pytest.raises(DE.EnvironmentUnreadable) as err:
            DE.read("r6", ready=ready)
        assert "2 devices named r6" in str(err.value)

    def test_a_context_that_is_not_a_list_of_lines_refuses(self):
        _nb, ready = _world({DE.CONTEXT_KEY: "username admin"})
        with pytest.raises(DE.EnvironmentUnreadable) as err:
            DE.read("r6", ready=ready)
        assert "not a list of lines" in str(err.value)


class TestTheImportNeverClearsTheFlag:
    """The import set `mgmt_only` from a name heuristic on every sync, so a flag a person set
    on an emulator's Gi1 would be cleared at the next import: the fact NetBox owns, owned by
    the tool again. It is raised where the heuristic recognises a port and never lowered."""

    @pytest.fixture(autouse=True)
    def _writes_open(self, monkeypatch):
        """The write gate opened for the fake, so an update REACHES it: with the gate shut
        both cases write nothing, and the first would pass for the wrong reason (measured)."""
        from modules import netbox_guard
        monkeypatch.setattr(netbox_guard, "assert_writes_allowed", lambda *a, **k: None)
        monkeypatch.setattr(netbox_guard, "record_modified", lambda *a, **k: None)

    def _ensure(self, nb, name, mgmt_only):
        from modules import netbox_client as nc
        # The device the interface is on, held as NetBox would hold it: the lookup filters by
        # it, and NetBox answers 400 to a device it does not hold (C1240).
        nb.seed("dcim/devices", {"id": 1, "name": "r6"})
        return nc._ensure_interface(nb, BASE, device_id=1, name=name, description="",
                                    mac=None, mtu=None, enabled=True, speed_mbps=None,
                                    mgmt_only=mgmt_only)

    def test_a_flag_a_person_set_survives_the_import(self):
        nb = FakeNetBox()
        nb.seed("dcim/interfaces", {"name": "GigabitEthernet1", "device": {"id": 1},
                                    "mgmt_only": True, "enabled": True, "description": "",
                                    "type": {"value": "1000base-t"}})
        self._ensure(nb, "GigabitEthernet1", mgmt_only=False)
        assert not [p for p in nb.patches if "mgmt_only" in p[2]], nb.patches

    def test_a_recognised_management_port_is_still_raised(self):
        """The control: the rule still writes, upward."""
        nb = FakeNetBox()
        nb.seed("dcim/interfaces", {"name": "MgmtEth0", "device": {"id": 1},
                                    "mgmt_only": False, "enabled": True, "description": "",
                                    "type": {"value": "1000base-t"}})
        self._ensure(nb, "MgmtEth0", mgmt_only=True)
        assert [p[2]["mgmt_only"] for p in nb.patches if "mgmt_only" in p[2]] == [True]


class TestTheRecordRebuildsTheSameRender:
    def test_a_record_carries_no_line_and_rebuilds_the_same_facts(self):
        _nb, ready = _world(EMULATED)
        env = DE.read("r6", ready=ready)
        rec = env.record()
        assert "password" not in str(rec), "an injected account's line carries its password"
        again = DE.Environment.from_record(rec)
        assert (again.injects_user, again.owns_ssh, again.management_interfaces) == \
               (env.injects_user, env.owns_ssh, env.management_interfaces)

    def test_the_same_render_from_the_record(self):
        from modules.nsot.bootstrap_config import render_bootstrap

        _nb, ready = _world(EMULATED)
        env = DE.read("r6", ready=ready)
        args = dict(hostname="r6", username="admin", secret="x", manager_interface="Gi2",
                    manager_address="192.0.2.32", manager_mask="255.255.255.0")
        assert render_bootstrap("cisco_iosxe", environment=env, **args) == render_bootstrap(
            "cisco_iosxe", environment=DE.Environment.from_record(env.record()), **args)

    def test_an_absent_record_is_no_environment(self):
        again = DE.Environment.from_record({})
        assert again.reserved == {} and not again.injects_user and not again.owns_ssh
