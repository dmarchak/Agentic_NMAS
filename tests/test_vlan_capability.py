"""C1692: an intent patch adds a VLAN only where a VLAN database is DECLARED or MEASURED (the
operator's decision, 2026-10-28), `modules/nsot/vlan_capability.py` and
`modules/nsot/intent_patch.py`.

- **Declared**: Mercury's platform table (`modules/nsot/platform_capabilities.json`), by config
  dialect and NetBox device type (the inventory's ``_model``, from NetBox's
  ``device_type.model``), compared whole.
- **Measured**: the device's own answer to `show vlan id 1`, as Show commands recorded it (the
  reads engine run for real, its session faked at its seam). The yes answers are two lab
  vIOS-L2 switches' real captures (tests/fixtures/console/vios_l2_*_show_vlan_id_1.txt). **No
  router's answer to the check is captured** (C1692's measurement is owed): the no answer here
  is IOS-XE's and IOS's real refusal of a command they lack (`show foobar`,
  tests/fixtures/operational/*__show_foobar.txt), used for its shape only.
- **Unknown** (neither): refused, naming the check to run.
- **Never a name or a role**: a device named and roled like a switch is answered by its
  declaration or its measurement alone.

A VLAN id carries no address, so the IPv4/IPv6 parity rule has no case here.
"""

import copy
import os
import time

import pytest
import yaml

from tests.test_committed_before_p1 import host  # noqa: F401  (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")


def capture(*parts) -> str:
    with open(os.path.join(FIX, *parts), encoding="ascii") as fh:
        return fh.read()


#: The two switches' real answers to the check: VTP server and transparent.
SWITCH_ANSWERS = (capture("console", "vios_l2_s1_show_vlan_id_1.txt"),
                  capture("console", "vios_l2_s5_show_vlan_id_1.txt"))
#: IOS-XE's and IOS's real refusal of a command they lack (for `show foobar`): the shape a
#: device without the command answers with. NOT a router's answer to the check (none captured).
REFUSALS = (capture("operational", "r3__show_foobar.txt"),
            capture("operational", "s1__show_foobar.txt"))
#: A real answer of another shape (`show ip interface brief`): neither yes nor no.
OTHER = capture("operational", "r1__show_ip_interface_brief.txt")


def measure(list_name: str, hostname: str, answer: str, command: str = "",
            when: float = None) -> dict:
    """Run the check on *hostname* through the reads engine (Show commands' own path: refused
    first, held, masked, capped, recorded), its session faked at its one seam to answer
    *answer*. The inventory is the device alone, for the run only."""
    from modules.nsot import reads, vlan_capability

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("modules.device.load_saved_devices", lambda path=None: [
            {"hostname": hostname, "ip": "192.0.2.21", "device_type": "cisco_ios"}])
        mp.setattr("modules.commands.run_device_command", lambda conn, c, **kw: answer)
        if when is not None:
            mp.setattr(reads.time, "time", lambda: when)
        return reads.run(list_name, [hostname], [command or vlan_capability.CHECK],
                         "a.person@example.invalid", session=lambda dev, fn: fn(object()))


@pytest.fixture
def net(monkeypatch, tmp_path):
    """A network folder in a temporary place, an inventory the test sets, and no name cut."""
    from modules.nsot import vlan_capability
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / name))
    monkeypatch.setattr("modules.nsot.retire.name_cuts", lambda name: {})
    devices = []
    monkeypatch.setattr(vlan_capability, "_inventory", lambda name: [dict(d) for d in devices])
    return devices


#: Devices named and roled like switches; only the declaration or the measurement answers.
ROUTER_NAMED_LIKE_A_SWITCH = {"hostname": "access-switch-1", "role": "switch",
                              "platform": "cisco_iosxe", "_model": "C8000V"}
PLAIN_SWITCH = {"hostname": "core-switch-1", "role": "switch", "platform": "cisco_ios"}


# ── the check ────────────────────────────────────────────────────────────────

class TestTheCheck:
    def test_the_check_is_a_read_the_allowlist_takes(self):
        from modules import readonly_commands
        from modules.nsot import vlan_capability
        assert readonly_commands.refusal(vlan_capability.CHECK) == ""

    @pytest.mark.parametrize("command, ok", [
        ("show vlan id 1", True), ("sh vlan id 1", True), ("SHOW VLAN ID 1", True),
        ("show vlan id 10", False), ("show vlan brief", False),
        ("show vlan id 1 | include default", False), ("show vlan id 1|include", False),
        ("show vlan id", False)])
    def test_only_the_whole_check_is_the_check(self, command, ok):
        from modules.nsot import vlan_capability
        assert vlan_capability.is_check(command) is ok

    @pytest.mark.parametrize("answer", SWITCH_ANSWERS, ids=["vtp-transparent", "vtp-server"])
    def test_a_switch_lists_vlan_1(self, answer):
        from modules.nsot import vlan_capability
        got = vlan_capability.read_answer(answer)
        assert got["has"] is True and "it lists VLAN 1 (1    default" in got["why"], got

    @pytest.mark.parametrize("answer", REFUSALS, ids=["ios-xe", "ios"])
    def test_a_device_refusing_the_command_has_none(self, answer):
        from modules.nsot import vlan_capability
        got = vlan_capability.read_answer(answer)
        assert got["has"] is False
        assert "it refuses the command (% Invalid input detected at '^' marker.)" == got["why"]

    @pytest.mark.parametrize("answer", ["", OTHER, "% Ambiguous command:  \"show vlan\""])
    def test_any_other_answer_is_unreadable(self, answer):
        from modules.nsot import vlan_capability
        assert vlan_capability.read_answer(answer)["has"] is None


# ── the declaration ──────────────────────────────────────────────────────────

class TestTheDeclaration:
    def test_the_router_type_is_declared_without_one(self):
        from modules.nsot import vlan_capability
        got = vlan_capability.declared("cisco_iosxe", "C8000V")
        assert got["has"] is False and got["device_type"] == "C8000V"
        assert vlan_capability.declared("cisco_iosxe", "c8000v")["has"] is False

    @pytest.mark.parametrize("dialect, model", [
        ("cisco_iosxe", "C8000V-X"), ("cisco_iosxe", "C8000"), ("cisco_ios", "C8000V"),
        ("cisco_iosxe", ""), ("", "C8000V")])
    def test_only_a_whole_device_type_in_its_dialect_is_declared(self, dialect, model):
        from modules.nsot import vlan_capability
        assert vlan_capability.declared(dialect, model) is None

    def test_every_entry_names_its_basis_and_a_yes_only_by_measurement(self):
        """Refusing is the safe side: a "no" may join by the vendor's documentation, its
        measurement owed; a "yes" only by a measurement whose capture is in the fixtures."""
        from modules.nsot import vlan_capability
        table = vlan_capability._table()["vlan_database"]
        entries = [(d, m, e) for d, types in table.items() for m, e in types.items()]
        assert len(entries) >= 1, "the floor: the router type"
        for dialect, model, entry in entries:
            assert isinstance(entry["has"], bool) and entry["source"], (dialect, model)
            if entry["has"]:
                assert entry["basis"] == "measured", (dialect, model)
                assert os.path.isfile(os.path.join(FIX, entry["fixture"])), (dialect, model)
            elif entry["basis"] != "measured":
                assert entry["owed"], (dialect, model)


# ── of: declared, else measured, else unknown ────────────────────────────────

class TestWhereTheAnswerComesFrom:
    def test_declared_no_for_a_device_named_and_roled_like_a_switch(self, net):
        from modules.nsot import vlan_capability
        net.append(ROUTER_NAMED_LIKE_A_SWITCH)
        got = vlan_capability.of("Lab", "access-switch-1")
        assert (got["has"], got["source"]) == (False, "declared")
        assert got["words"].startswith(
            "declared: no VLAN database (Mercury's platform table, cisco_iosxe device type "
            "C8000V, documented: ")
        assert (got["platform"], got["device_type"]) == ("cisco_iosxe", "C8000V")

    def test_undeclared_and_unmeasured_is_unknown_naming_the_check(self, net):
        from modules.nsot import vlan_capability
        net.append(PLAIN_SWITCH)
        got = vlan_capability.of("Lab", "core-switch-1")
        assert (got["has"], got["source"]) == (None, "unknown")
        assert got["words"] == ("not declared and not measured: run `show vlan id 1` on "
                                "core-switch-1 (Show commands, or Ask the device on its page) "
                                "to measure it, or name its device type in NetBox, by which "
                                "Mercury's platform table declares a VLAN database (none is "
                                "named)")

    def test_unknown_with_a_device_type_names_the_table_has_none_for_it(self, net):
        """What would answer it (C2043): the measurement, or the NetBox device type the
        platform table declares by; a type it does not list is named as not declared."""
        from modules.nsot import vlan_capability
        net.append(dict(PLAIN_SWITCH, _model="IOSv-L2"))
        got = vlan_capability.of("Lab", "core-switch-1")
        assert (got["has"], got["source"]) == (None, "unknown")
        assert got["words"].endswith(
            "to measure it; Mercury's platform table declares nothing for cisco_ios device "
            "type IOSv-L2")

    @pytest.mark.parametrize("answer", SWITCH_ANSWERS, ids=["vtp-transparent", "vtp-server"])
    def test_measured_yes_from_a_recorded_answer(self, net, answer):
        from modules.nsot import vlan_capability
        net.append(PLAIN_SWITCH)
        run = measure("Lab", "core-switch-1", answer)
        got = vlan_capability.of("Lab", "core-switch-1")
        assert (got["has"], got["source"]) == (True, "measured"), got
        assert f"Show commands run {run['id']}: it lists VLAN 1" in got["words"]
        assert got["words"].startswith("measured: a VLAN database (core-switch-1's answer to "
                                       "`show vlan id 1` at ")
        assert got["at"] and got["at"] in got["words"]

    def test_measured_no_from_a_refusal(self, net):
        from modules.nsot import vlan_capability
        net.append(PLAIN_SWITCH)
        measure("Lab", "core-switch-1", REFUSALS[0])
        got = vlan_capability.of("Lab", "core-switch-1")
        assert (got["has"], got["source"]) == (False, "measured")
        assert "measured: no VLAN database" in got["words"]

    def test_the_declaration_is_read_before_a_measurement(self, net):
        from modules.nsot import vlan_capability
        net.append(ROUTER_NAMED_LIKE_A_SWITCH)
        measure("Lab", "access-switch-1", SWITCH_ANSWERS[0])
        assert vlan_capability.of("Lab", "access-switch-1")["source"] == "declared"

    def test_a_newer_unreadable_answer_keeps_the_older_readable_one(self, net):
        from modules.nsot import vlan_capability
        net.append(PLAIN_SWITCH)
        now = time.time()
        measure("Lab", "core-switch-1", SWITCH_ANSWERS[1], when=now - 60)
        measure("Lab", "core-switch-1", OTHER, when=now)
        got = vlan_capability.of("Lab", "core-switch-1")
        assert (got["has"], got["source"]) == (True, "measured")

    def test_the_newest_readable_answer_wins(self, net):
        from modules.nsot import vlan_capability
        net.append(PLAIN_SWITCH)
        now = time.time()
        measure("Lab", "core-switch-1", SWITCH_ANSWERS[1], when=now - 60)
        measure("Lab", "core-switch-1", REFUSALS[1], when=now)
        assert vlan_capability.of("Lab", "core-switch-1")["has"] is False

    def test_a_filtered_answer_is_not_a_measurement(self, net):
        from modules.nsot import vlan_capability
        net.append(PLAIN_SWITCH)
        measure("Lab", "core-switch-1", SWITCH_ANSWERS[0],
                command="show vlan id 1 | include default")
        assert vlan_capability.of("Lab", "core-switch-1")["source"] == "unknown"

    def test_an_answer_from_before_the_names_cut_is_an_earlier_devices(self, net,
                                                                       monkeypatch):
        """Retired, abandoned or created since: the name is a new device's, which inherits
        nothing (CLAUDE.md, the device lifecycle)."""
        from modules.nsot import vlan_capability
        net.append(PLAIN_SWITCH)
        now = time.time()
        measure("Lab", "core-switch-1", SWITCH_ANSWERS[0], when=now - 3600)
        monkeypatch.setattr("modules.nsot.retire.name_cuts", lambda name: {
            "core-switch-1": {"name": "core-switch-1", "epoch": int(now - 60), "why": "created",
                              "at": ""}})
        assert vlan_capability.of("Lab", "core-switch-1")["source"] == "unknown"

    def test_another_devices_answer_is_not_this_ones(self, net):
        from modules.nsot import vlan_capability
        net.extend([PLAIN_SWITCH, dict(PLAIN_SWITCH, hostname="core-switch-2")])
        measure("Lab", "core-switch-2", SWITCH_ANSWERS[0])
        assert vlan_capability.of("Lab", "core-switch-1")["source"] == "unknown"

    def test_a_netbox_device_carries_its_device_type(self, monkeypatch, tmp_path):
        """The NetBox adapter keeps NetBox's device type model as ``_model``, never sent to a
        device (`inventory.strip_metadata`)."""
        from modules import credentials, inventory
        from modules.inventory import netbox_source
        monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "creds.json"))
        credentials.save_profile("default", "admin", "pw", "en")
        raw = {"id": 7, "name": "edge1", "primary_ip4": {"address": "192.0.2.7/24"},
               "platform": {"slug": "cisco-ios-xe"}, "role": {"slug": "router"},
               "site": {"slug": "lab"}, "device_type": {"model": "C8000V", "slug": "c8000v"}}
        (dev,), _s, _w = netbox_source.adapt_devices([raw])
        assert dev["_model"] == "C8000V" and "_model" not in inventory.strip_metadata(dev)
        (bare,), _s, _w = netbox_source.adapt_devices([dict(raw, device_type=None)])
        assert bare["_model"] == ""


# ── the patch refuses ────────────────────────────────────────────────────────

def _committed(name: str) -> dict:
    return yaml.safe_load(capture("committed", f"{name}.yml"))


ADD = {"op": "add_vlan", "vlan": 40, "name": "GUESTS"}


class TestThePatchRefuses:
    def test_declared_yes_adds_it(self, net, monkeypatch):
        from modules.nsot import intent_patch, vlan_capability
        table = copy.deepcopy(vlan_capability._table())
        table["vlan_database"]["cisco_ios"] = {"IOSv-L2": {
            "has": True, "basis": "measured", "source": "the test's declaration"}}
        monkeypatch.setattr(vlan_capability, "_table", lambda: table)
        net.append(dict(PLAIN_SWITCH, _model="IOSv-L2"))
        cap = vlan_capability.of("Lab", "core-switch-1")
        assert cap["source"] == "declared"
        got = intent_patch.apply(dict(_committed("s1"), hostname="core-switch-1"),
                                 {"hostname": "core-switch-1", "operations": [ADD]}, cap)
        assert got["ok"] and {"extra": [], "id": "40", "name": "GUESTS"} in got["doc"]["vlans"]

    def test_declared_no_refuses_naming_device_platform_type_and_source(self, net):
        """C1692 itself: the router's real committed intent holds `vlans: []`."""
        from modules.nsot import intent_patch, vlan_capability
        net.append(dict(ROUTER_NAMED_LIKE_A_SWITCH, hostname="r2"))
        doc = _committed("r2")
        assert doc["vlans"] == [], "the floor: the router's intent holds an empty list"
        got = intent_patch.apply(doc, {"hostname": "r2", "operations": [ADD]},
                                 vlan_capability.of("Lab", "r2"))
        assert (got["ok"], got["status"], got["stage"]) == (False, 409, "capability")
        assert got["error"].startswith(
            "operations[0] adds VLAN 40, and r2 (cisco_iosxe, device type C8000V) has no VLAN "
            "database: declared: no VLAN database (Mercury's platform table, cisco_iosxe "
            "device type C8000V, documented: ")
        assert got["error"].endswith(". Nothing is added")

    def test_undeclared_and_unmeasured_refuses_naming_the_check(self, net):
        from modules.nsot import intent_patch, vlan_capability
        net.append(dict(PLAIN_SWITCH, hostname="s1"))
        got = intent_patch.apply(_committed("s1"), {"hostname": "s1", "operations": [ADD]},
                                 vlan_capability.of("Lab", "s1"))
        assert got["stage"] == "capability"
        assert got["error"] == (
            "operations[0] adds VLAN 40, and whether s1 (cisco_ios, device type not named) "
            "has a VLAN database is not declared and not measured: run `show vlan id 1` on s1 "
            "(Show commands, or Ask the device on its page) to measure it, or name its device "
            "type in NetBox, by which Mercury's platform table declares a VLAN database (none "
            "is named). A VLAN is added only where a VLAN database is declared or measured")

    def test_none_given_is_unknown_and_refused(self):
        from modules.nsot import intent_patch
        got = intent_patch.apply(_committed("s1"), {"hostname": "s1", "operations": [ADD]})
        assert got["stage"] == "capability" and "run `show vlan id 1` on s1" in got["error"]

    @pytest.mark.parametrize("answer, ok", [(SWITCH_ANSWERS[0], True), (REFUSALS[0], False)],
                             ids=["measured-yes", "measured-no"])
    def test_measured_answers_decide(self, net, answer, ok):
        from modules.nsot import intent_patch, vlan_capability
        net.append(dict(PLAIN_SWITCH, hostname="s1"))
        measure("Lab", "s1", answer)
        got = intent_patch.apply(_committed("s1"), {"hostname": "s1", "operations": [ADD]},
                                 vlan_capability.of("Lab", "s1"))
        assert got["ok"] is ok, got
        if not ok:
            assert "has no VLAN database: measured: no VLAN database (s1's answer to " \
                   "`show vlan id 1` at " in got["error"]

    def test_already_held_is_still_asked(self):
        """An add the intent already holds sends nothing new, and is still refused without a
        VLAN database: the question is the device's, not the document's."""
        from modules.nsot import intent_patch
        got = intent_patch.apply(_committed("s1"), {"hostname": "s1", "operations": [
            {"op": "add_vlan", "vlan": 20}]}, {"has": False, "words": "planted"})
        assert got["stage"] == "capability"

    def test_removing_a_vlan_needs_no_capability(self):
        """A removal takes a line out of intent; a merge-only deploy sends nothing for it."""
        from modules.nsot import intent_patch
        doc = _committed("s1")
        doc["vlans"].append({"extra": [], "id": "40", "name": "GUESTS"})
        got = intent_patch.apply(doc, {"hostname": "s1", "operations": [
            {"op": "remove_vlan", "vlan": 40}]})
        assert got["ok"] and got["changes"][0]["device_keeps"] is True


# ── every path to a commit reads it ──────────────────────────────────────────

class TestEveryPathReadsIt:
    """`preview`, `commit` and `commit_many` read the device's VLAN database themselves, so no
    caller (feature 7's intent change in words, or any later one) can leave it out."""

    PATCH = {"hostname": "s1", "operations": [ADD]}

    def test_the_preview_refuses_until_it_is_measured(self, host):  # noqa: F811
        from modules.nsot import intent_patch
        got = intent_patch.preview("Lab", "s1", self.PATCH)
        assert got["ok"] is False and got["stage"] == "capability" and got["base"]
        measure("Lab", "s1", SWITCH_ANSWERS[0])
        got = intent_patch.preview("Lab", "s1", self.PATCH)
        assert got["ok"] and got["changed"], got

    def test_the_commit_reads_it_again(self, host):  # noqa: F811
        """Measured at the preview, refused at the commit when a newer answer says no."""
        from modules.nsot import intent_patch
        measure("Lab", "s1", SWITCH_ANSWERS[0], when=time.time() - 60)
        shown = intent_patch.preview("Lab", "s1", self.PATCH)
        assert shown["ok"], shown
        measure("Lab", "s1", REFUSALS[1])
        got = intent_patch.commit("Lab", "s1", self.PATCH, "add guests", shown["base"],
                                  "a.person")
        assert got["ok"] is False and got["stage"] == "capability"
        got = intent_patch.commit_many("Lab", [("s1", self.PATCH, shown["base"])],
                                       "add guests", "a.person")
        assert got["ok"] is False and got["stage"] == "capability"

    def test_a_patch_adding_no_vlan_reads_nothing(self, host, monkeypatch):  # noqa: F811
        from modules.nsot import intent_patch, vlan_capability
        monkeypatch.setattr(vlan_capability, "of",
                            lambda *a: pytest.fail("read for a patch adding no VLAN"))
        got = intent_patch.preview("Lab", "s1", {"hostname": "s1", "operations": [
            {"op": "set_description", "interface": "Gi0/1", "description": "uplink"}]})
        assert got["ok"], got
