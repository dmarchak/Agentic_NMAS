"""C2336 (the operator, 2026-11-03, sessions 7 and 8): Check drift now on one device, the
read-only way to confirm a revert from the device's own page. The same read and comparison a
drift run makes, of one device, merged into the network's stored last run so its drift row says
what this read found; a run of the network in progress refuses it by name; the network's
schedule does not move.

The device reads are faked as tests/payload_providers.py's drift run fakes them (r1 clean, r2
drifted, r3 with no golden, r4 unreachable), through the real `run_drift_check` and
`check_device`.
"""

import pytest

from modules import attention as A
from modules import drift_check as D
from tests import payload_providers as P


@pytest.fixture
def world(monkeypatch, tmp_path):
    from modules.config import get_current_list_name
    first = P._drift_run(monkeypatch, tmp_path)
    return {"first": first, "list": get_current_list_name(), "mp": monkeypatch}


def _stored(world):
    return D._load_state(world["list"])["last_result"]


class TestTheMerge:
    RUN = {"ok": True, "inventory": 4, "checked": 2, "drifted": 1, "clean": 1,
           "drifted_devices": [{"hostname": "r2", "diff_lines": 4, "changed_lines": 1}],
           "errors": [{"hostname": "r4", "reason": "timed out"}],
           "skipped": [{"hostname": "r3", "reason": "no golden config saved"}],
           "timestamp": "2026-11-03 01:14:31", "triggered_by": "scheduled"}

    def test_a_device_put_back_leaves_drifted_and_the_counts_follow(self):
        one = {"ok": True, "drifted_devices": [], "errors": [], "skipped": []}
        got = D.merged(dict(self.RUN), one, "r2", "op@example.invalid")
        assert got["drifted_devices"] == [] and (got["checked"], got["drifted"], got["clean"]) \
            == (2, 0, 2)
        assert got["device_checks"]["r2"]["state"] == "clean"
        assert got["device_checks"]["r2"]["by"] == "op@example.invalid"
        assert (got["timestamp"], got["triggered_by"]) == ("2026-11-03 01:14:31", "scheduled"), \
            "the run's own time and trigger stay the run's"

    def test_a_device_unreachable_before_and_checked_now_is_counted(self):
        one = {"ok": True, "drifted_devices": [{"hostname": "r4", "diff_lines": 3,
                                                "changed_lines": 1, "read_at": 5.0}],
               "errors": [], "skipped": []}
        got = D.merged(dict(self.RUN), one, "r4", "op@example.invalid")
        assert [e["hostname"] for e in got["errors"]] == []
        assert {d["hostname"] for d in got["drifted_devices"]} == {"r2", "r4"}
        assert (got["checked"], got["drifted"], got["clean"]) == (3, 2, 1)
        assert got["device_checks"]["r4"]["read_at"] == 5.0

    def test_the_other_devices_entries_are_untouched(self):
        one = {"ok": True, "drifted_devices": [], "errors": [], "skipped": []}
        got = D.merged(dict(self.RUN), one, "r1", "op@example.invalid")
        assert got["drifted_devices"] == self.RUN["drifted_devices"]
        assert got["errors"] == self.RUN["errors"] and got["skipped"] == self.RUN["skipped"]


class TestOneDevice:
    def test_a_device_put_back_is_read_now_and_its_drift_row_clears(self, world):
        assert any(r["id"].endswith("drifted:r2") for r in A.drift_source()["rows"])
        world["mp"].setattr("modules.commands.run_device_command",
                            lambda conn, cmd: "hostname r2\n!\nend\n")
        got = D.check_device(world["list"], "r2", by="op@example.invalid")
        assert (got["ok"], got["state"]) == (True, "clean"), got
        stored = _stored(world)
        assert all(d["hostname"] != "r2" for d in stored["drifted_devices"])
        assert stored["device_checks"]["r2"]["state"] == "clean"
        assert not any(r["id"].endswith("drifted:r2") for r in A.drift_source()["rows"])
        assert any(r["id"].endswith("unreachable:r4") or "r4" in r["id"]
                   for r in A.drift_source()["rows"]), "the other devices' rows stand"

    def test_a_device_still_changed_is_said_with_its_lines_and_its_read(self, world):
        got = D.check_device(world["list"], "r2", by="op@example.invalid")
        assert (got["state"], got["changed_lines"]) == ("drifted", 1), got
        entry = next(d for d in _stored(world)["drifted_devices"] if d["hostname"] == "r2")
        assert entry["changed_lines"] == 1 and entry["read_at"]

    def test_the_schedule_does_not_move(self, world):
        before = D._load_state(world["list"]).get("last_check_ts")
        D.check_device(world["list"], "r1", by="op@example.invalid")
        assert D._load_state(world["list"]).get("last_check_ts") == before

    def test_a_run_in_progress_refuses_it_by_name(self, world):
        with D._OneRun(D._run_lock_path(world["list"]), "scheduled"):
            with pytest.raises(D.DriftRunning):
                D.check_device(world["list"], "r2", by="op@example.invalid")

    def test_a_device_not_in_the_inventory_says_so(self, world):
        got = D.check_device(world["list"], "nope", by="op@example.invalid")
        assert got["ok"] is False and "not in" in got["error"], got


from tests.test_device_revert_retry_v2 import page  # noqa: E402,F401 (fixtures)
from tests.test_intent_ops import classify, lab  # noqa: E402,F401 (the fixtures page needs)


class TestTheCard:
    def test_the_menu_row_and_the_card_and_its_result(self, monkeypatch, page):  # noqa: F811
        """Through the routes, r2 in the list Lab as the device page reads it: the Actions menu
        offers Check drift now…, its card offers the read, and the POST draws what the read
        found in place."""
        lab = dict(page, list="Lab")
        c = lab["client"]
        menu = c.get("/v2/device/r2/actions?tab=overview").get_data(as_text=True)
        assert 'hx-get="/v2/device/r2/drift/check?back=overview' in menu and \
            "Check drift now…" in menu
        card = c.get("/v2/device/r2/drift/check?back=overview").get_data(as_text=True)
        assert "Check drift now on r2" in card and 'hx-post="/v2/device/r2/drift/check/now' in card
        calls = []
        monkeypatch.setattr(D, "check_device", lambda list_name, host, by: calls.append(
            (list_name, host, by)) or {"ok": True, "state": "drifted", "hostname": host,
                                        "changed_lines": 2, "summary": "", "error": ""})
        r = c.post("/v2/device/r2/drift/check/now", data={"list": lab.get("list", "Lab"),
                                                         "back": "overview"})
        body = r.get_data(as_text=True)
        assert r.status_code == 200 and "r2 differs from its golden by 2 changed lines" in body
        assert calls and calls[0][1] == "r2"
        monkeypatch.setattr(D, "check_device", lambda list_name, host, by: (_ for _ in ()).throw(
            D.DriftRunning({"triggered_by": "scheduled", "started_at": "2026-11-03 05:40:00"})))
        body = c.post("/v2/device/r2/drift/check/now",
                      data={"list": lab.get("list", "Lab")}).get_data(as_text=True)
        assert "Couldn't check r2: a drift check of" in body and "is running" in body
