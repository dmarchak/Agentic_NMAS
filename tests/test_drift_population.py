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
    monkeypatch.setattr("modules.ai_assistant._load_golden_config_file",
                        lambda ip: golden.get(ip))
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
        monkeypatch.setattr("modules.ai_assistant._list_golden_configs",
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
        fake.is_stale = lambda ip: ip == "203.0.113.2"
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
