"""The drift check's population is the inventory, not the golden store.

`run_drift_check()` iterated `_list_golden_configs()`, which listed the
deprecated `golden_configs/` directory. A device onboarded after the migration
-- golden in `config_repo/`, no legacy file -- was **checked by nothing and
appeared in no count**: not an error, not a skip, simply absent. A report of
"all 9 device(s) clean" over a ten-device inventory is textually identical to
one over a nine-device inventory, so nothing could have surfaced it.

The device with no baseline at all had the same problem from the other
direction: `_load_golden_config_file()` returning None was a bare `return`.
"This device has no golden config" is the most actionable thing a drift check
can say, and it was the one thing it stayed silent about.

Every device now lands in exactly one bucket, and the totals are checked
against the inventory size.
"""

import pytest


def _device(name, ip):
    return {"hostname": name, "ip": ip, "username": "u", "password": "p",
            "device_type": "cisco_ios"}


@pytest.fixture
def fleet(monkeypatch):
    """Three devices. r1 clean, r2 drifted, r3 has no golden at all."""
    from modules import drift_check

    devices = [_device("r1", "203.0.113.1"), _device("r2", "203.0.113.2"),
               _device("r3", "203.0.113.3")]
    golden = {"203.0.113.1": "hostname r1\n!\nend\n",
              "203.0.113.2": "hostname r2\n!\nend\n"}
    running = {"203.0.113.1": "hostname r1\n!\nend\n",
               "203.0.113.2": "hostname r2\n!\nip route 0.0.0.0 0.0.0.0 Null0\nend\n",
               "203.0.113.3": "hostname r3\n!\nend\n"}

    monkeypatch.setattr("modules.device.get_current_device_list",
                        lambda: ("lab", "lab.csv"))
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path: list(devices))
    # Drift reads the golden through _golden_record (C104: as committed,
    # with a refusal distinct from "no golden").
    monkeypatch.setattr("modules.goldens._golden_record",
                        lambda ip, list_name="": {"text": golden.get(ip), "path": "", "commit": "",
                                    "source": "", "refused": ""})
    monkeypatch.setattr("modules.connection.get_persistent_connection",
                        lambda dev, pool, lock: dev["ip"])
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, cmd: running[conn])
    monkeypatch.setattr("modules.approval_queue.add_approval",
                        lambda **kw: {"ok": True})
    return {"devices": devices, "golden": golden, "running": running,
            "module": drift_check}


class TestEveryDeviceIsAccountedFor:

    def test_the_totals_add_up_to_the_inventory(self, fleet):
        r = fleet["module"].run_drift_check("test")
        assert r["inventory"] == 3
        assert r["checked"] + len(r["skipped"]) + len(r["errors"]) == 3

    def test_a_device_with_no_golden_is_named(self, fleet):
        """Previously a bare `return` — no error, no skip, no trace."""
        r = fleet["module"].run_drift_check("test")
        assert [s["hostname"] for s in r["skipped"]] == ["r3"]
        assert "no golden config" in r["skipped"][0]["reason"]

    def test_the_summary_states_the_coverage(self, fleet):
        r = fleet["module"].run_drift_check("test")
        assert "checked 2 of 3" in r["summary"], r["summary"]

    def test_the_unchecked_device_is_in_the_summary(self, fleet):
        r = fleet["module"].run_drift_check("test")
        assert "r3" in r["summary"], r["summary"]

    def test_drift_is_still_detected(self, fleet):
        r = fleet["module"].run_drift_check("test")
        assert r["drifted"] == 1
        assert r["drifted_devices"][0]["hostname"] == "r2"

    def test_the_clean_device_is_clean(self, fleet):
        r = fleet["module"].run_drift_check("test")
        assert r["clean"] == 1


class TestTheLegacyStoreDoesNotDecideWhoIsChecked:
    """The headline. A device is checked because it is in the inventory."""

    def test_a_device_absent_from_the_legacy_store_is_still_checked(
            self, fleet, monkeypatch):
        # The old enumerator's answer. If anything still consults it, r1 and
        # r2 drop out of the run entirely.
        monkeypatch.setattr("modules.goldens._list_golden_configs",
                            lambda: [])
        r = fleet["module"].run_drift_check("test")
        assert r["inventory"] == 3
        assert r["checked"] == 2, (
            "the golden store was empty; the inventory was not")
        assert r["drifted"] == 1

    def test_an_empty_inventory_is_not_a_clean_fleet(self, fleet, monkeypatch):
        monkeypatch.setattr("modules.device.load_saved_devices", lambda p: [])
        r = fleet["module"].run_drift_check("test")
        assert r["checked"] == 0
        assert "clean" not in r["summary"].lower(), r["summary"]


class TestNoDeviceFallsThroughSilently:

    def test_a_device_that_produces_no_outcome_is_reported(self, fleet,
                                                           monkeypatch):
        """The failure mode the restructuring removed, forced open.

        A device is dropped before it reaches any branch. The run must say a
        device produced no outcome rather than quietly reporting a smaller
        total -- which is precisely how the legacy-store population hid an
        unchecked device for the whole of Phase 3.
        """
        import concurrent.futures

        real_pool = concurrent.futures.ThreadPoolExecutor

        class _DropsOne(real_pool):
            def map(self, fn, items, *a, **kw):
                return super().map(fn, list(items)[:-1], *a, **kw)

        monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", _DropsOne)
        r = fleet["module"].run_drift_check("test")

        assert r["inventory"] == 3
        assert any("no outcome" in e["reason"] for e in r["errors"]), r["errors"]
        assert r["checked"] + len(r["skipped"]) + len(r["errors"]) == 3

    def test_stale_devices_are_skipped_with_a_reason(self, fleet, monkeypatch):
        import sys
        import types

        fake = types.ModuleType("modules.inventory")
        fake.is_stale = lambda ip, list_name="": ip == "203.0.113.2"
        monkeypatch.setitem(sys.modules, "modules.inventory", fake)
        r = fleet["module"].run_drift_check("test")
        reasons = {s["hostname"]: s["reason"] for s in r["skipped"]}
        assert "NetBox" in reasons["r2"]
        assert r["checked"] + len(r["skipped"]) + len(r["errors"]) == 3

    def test_an_unreachable_device_is_an_error_not_a_gap(self, fleet,
                                                         monkeypatch):
        def _boom(conn, cmd):
            if conn == "203.0.113.1":
                raise OSError("connection refused")
            return fleet["running"][conn]

        monkeypatch.setattr("modules.commands.run_device_command", _boom)
        r = fleet["module"].run_drift_check("test")
        assert [e["hostname"] for e in r["errors"]] == ["r1"]
        assert r["checked"] + len(r["skipped"]) + len(r["errors"]) == 3


# ---------------------------------------------------------------------------
# Devices outside config drift's population (the Lab 9 kit's rows, 2026-11-10)
# ---------------------------------------------------------------------------

def _row(name, ip, device_type, **more):
    return dict({"hostname": name, "ip": ip, "username": "u", "password": "p",
                 "device_type": device_type}, **more)


#: The kit's kinds of device, addresses of both families: two IOS devices (one observe-only),
#: neither with a golden; a switch of each discovery driver's family; an Open vSwitch server;
#: the controller's host; a device with no login; and one whose platform nothing names.
MIXED = [
    _row("r1", "192.0.2.1", "cisco_ios"),
    _row("sw2960", "192.0.2.2", "cisco_ios", _management="observe"),
    _row("sw-a", "192.0.2.3", "arista_eos"),
    _row("sw-h", "2001:db8::4", "hp_procurve"),
    _row("ovs1", "192.0.2.5", "ovs_linux"),
    _row("ctl", "2001:db8::6", "linux", role="host"),
    _row("gone", "192.0.2.7", "cisco_ios", _login="no credentials resolve for it"),
    _row("box", "192.0.2.8", "some_other_driver"),
]


@pytest.fixture
def mixed(monkeypatch):
    from modules import drift_check

    asked = []
    monkeypatch.setattr("modules.device.get_current_device_list", lambda: ("lab9", "lab9.csv"))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: list(MIXED))
    monkeypatch.setattr("modules.goldens._golden_record",
                        lambda ip, list_name="": {"text": None, "path": "", "commit": "",
                                                  "source": "", "refused": ""})
    monkeypatch.setattr("modules.connection.get_persistent_connection",
                        lambda dev, pool, lock: asked.append(dev["hostname"]) or dev["ip"])
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, cmd: "")
    monkeypatch.setattr("modules.approval_queue.add_approval", lambda **kw: {"ok": True})
    return {"module": drift_check, "asked": asked}


class TestDevicesOutsideConfigDrift:
    """The operator, 2026-11-10, on the Lab 9 kit: "drift-check rows for never-checked
    devices". An Arista or ProCurve switch and an Open vSwitch server each read "was not
    checked for drift: no golden config saved", a warning whose action was Capture; Mercury
    keeps a golden only for a platform it parses (`repo.save_golden` refuses another, C452), so
    the row named an action Mercury refuses. Such a device is outside config drift's
    population, named with its reason in the run's record, as a host and a device with no
    login already were; a device that can be captured keeps its row."""

    def test_a_device_whose_platform_has_no_golden_is_excluded_by_name_never_skipped(
            self, mixed):
        r = mixed["module"].run_drift_check("test")
        excluded = {e["hostname"]: e for e in r["excluded"]}
        assert sorted(excluded) == ["ctl", "gone", "ovs1", "sw-a", "sw-h"]
        assert {h: e["kind"] for h, e in excluded.items()} == {
            "ctl": "host", "gone": "no_login", "ovs1": "no_golden_platform",
            "sw-a": "no_golden_platform", "sw-h": "no_golden_platform"}
        assert excluded["sw-a"]["reason"] == (
            "Arista EOS (driver arista_eos): Mercury keeps a golden only for a platform whose "
            "configuration it parses (cisco_ios, cisco_iosxe), so there is none to compare it "
            "with")
        assert excluded["sw-h"]["reason"].startswith("HP ProCurve / ArubaOS-Switch (driver "
                                                     "hp_procurve)")
        assert excluded["ovs1"]["reason"].startswith("Open vSwitch (driver ovs_linux)")
        assert excluded["ctl"]["reason"] == "a host: not in config drift"
        assert excluded["gone"]["reason"] == "no credentials resolve for it"

    def test_what_can_be_captured_stays_a_skipped_device_and_nothing_is_asked_of_the_rest(
            self, mixed):
        r = mixed["module"].run_drift_check("test")
        skipped = {s["hostname"]: s for s in r["skipped"]}
        assert sorted(skipped) == ["box", "r1", "sw2960"], "each can be given a golden or a name"
        assert all(s["reason"] == "no golden config saved" for s in skipped.values())
        assert skipped["sw2960"].get("observe") is True and "observe" not in skipped["r1"]
        assert r["inventory"] == 3 and r["checked"] == 0
        assert r["checked"] + len(r["skipped"]) + len(r["errors"]) == r["inventory"]
        assert mixed["asked"] == [], "no session is opened to a device with nothing to compare"
        assert "Not in config drift: " in r["summary"] and "sw-a (Arista EOS" in r["summary"]

    def test_a_dialect_named_for_a_discovery_driver_is_in_the_population(self):
        from modules import drift_check as D

        assert D.not_in_config_drift(_row("x", "192.0.2.9", "arista_eos",
                                          platform="cisco_ios")) == {}
        assert D.not_in_config_drift(_row("r1", "2001:db8::9", "cisco_ios")) == {}
        assert D.not_in_config_drift(_row("box", "192.0.2.8", "some_other_driver")) == {}
        assert D.not_in_config_drift(_row("a", "192.0.2.3", "arista_eos"))["kind"] == \
            D.OUTSIDE_NO_GOLDEN

    def test_its_device_page_says_it_is_never_checked_never_unchanged(self, mixed, monkeypatch):
        """A device outside the population was compared with nothing: its Since last capture
        row must not read "unchanged at the last run"."""
        from modules import device_page

        r = mixed["module"].run_drift_check("test")
        monkeypatch.setattr(device_page, "_drift_last", lambda ref: dict(r, timestamp="t"))
        for host, begins in (("sw-a", "Arista EOS (driver arista_eos)"),
                             ("ctl", "a host: not in config drift")):
            row = device_page.drift_row(None, host)
            assert row["state"] == "unknown", row
            assert row["text"].startswith(f"not in config drift, never checked: {begins}")
        assert device_page.drift_row(None, "r1")["text"] == "skipped by the last run"
