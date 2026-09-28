"""A NetBox preview or import says what it is doing while it runs (the
operator, 2026-09-28: "a slow operation that says what it's doing is usable; a
fast one that goes blank isn't").

Measured on the host: a 9-device import preview took 54 s, 303 requests to
NetBox at 176 ms mean, behind a bare spinner. The page gives each request an
id, the sync reports under it (`modules.op_progress`: requests counted at the
session, the device it is on), the modal polls it, and the in-flight panel
(C99) lists it with every device operation.
"""

import json

import pytest

from tests.fake_netbox import FakeNetBox
from tests.js_source import read_shipped

PID = "0123456789abcdef01234567"


class HookedNetBox(FakeNetBox):
    """FakeNetBox with a requests-style response hook list, so the session
    hook that counts requests is exercised as the real session runs it."""

    def __init__(self):
        super().__init__()
        self.hooks = {"response": []}

    def _fire(self, r):
        for hook in self.hooks["response"]:
            hook(r)
        return r

    def get(self, *a, **k):
        return self._fire(super().get(*a, **k))

    def post(self, *a, **k):
        return self._fire(super().post(*a, **k))


@pytest.fixture(autouse=True)
def fresh():
    from modules import op_progress

    op_progress._ops.clear()
    yield
    op_progress._ops.clear()


class TestTheRegistry:
    def test_start_tick_update_finish(self):
        from modules import op_progress

        assert op_progress.start(PID, "previewed for import", "NetBox (Lab)", actor="p")
        op_progress.update(PID, phase="reading and planning each device", devices_total=9,
                           devices_done=3, current="r4")
        for _ in range(42):
            op_progress.tick(PID)
        got = op_progress.get(PID)
        assert got["requests"] == 42
        assert got["step_words"] == ("42 request(s) to NetBox so far; device 4 of 9 (r4); "
                                     "reading and planning each device")
        op_progress.finish(PID)
        assert op_progress.get(PID)["finished_at"] and op_progress.running() == []

    def test_an_id_not_ours_records_nothing(self):
        from modules import op_progress

        assert not op_progress.start("../../etc", "x", "y")
        assert not op_progress.start("", "x", "y")
        assert op_progress._ops == {}

    def test_a_running_op_is_in_the_panel_row_shape(self):
        from modules import op_progress
        from modules.nsot import device_ops

        op_progress.start(PID, "previewed for import", "NetBox (Lab)", actor="p")
        row = op_progress.running()[0]
        assert row["device"] == "NetBox (Lab)" and row["words"] == "previewed for import"
        # The shape the one panel draws for a device operation.
        assert {"device", "words", "actor", "held_for_s", "step_words", "step_ago_s",
                "stalled"} <= set(row)
        assert device_ops  # imported: the panel's other source


def test_the_real_sync_counts_its_requests(monkeypatch):
    import modules.netbox_client as nbc
    from modules import netbox_guard, op_progress

    nb = HookedNetBox()
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                           "token": "t"})
    monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: nb)
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    op_progress.start(PID, "previewed for import", "NetBox (probe)")
    nbc.sync_list_to_netbox("probe-progress", [], dry_run=True, progress_id=PID)
    got = op_progress.get(PID)
    assert got["requests"] > 0, "the session hook counted nothing"
    assert got["phase"] == "cables between devices"


class TestTheRoutes:
    def _client(self, monkeypatch):
        from modules import netbox_guard
        import modules.netbox_client as nbc
        import routes.netbox_safety as ns

        monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                               "token": "t"})
        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
        monkeypatch.setattr(ns, "_load_list_devices",
                            lambda name: ("Default", [{"hostname": "r9", "ip": "192.0.2.9"}]))

        def fake_sync(name, devs, dry_run=False, progress_id="", **k):
            from modules import op_progress
            op_progress.tick(progress_id)
            return {"plan": {"creates": [], "updates": [], "deletes": []}}

        monkeypatch.setattr(nbc, "sync_list_to_netbox", fake_sync)
        import app as A
        return A.app.test_client()

    def test_a_preview_reports_under_the_page_s_id(self, monkeypatch):
        c = self._client(monkeypatch)
        c.post("/netbox/safety/import/preview", json={"list_name": "Default", "progress_id": PID})
        d = c.get(f"/netbox/safety/progress/{PID}").get_json()
        assert d["state"] == "finished" and d["progress"]["requests"] == 1
        assert d["progress"]["outcome"] == "done"

    def test_an_unknown_id_is_unknown_never_not_running(self, monkeypatch):
        c = self._client(monkeypatch)
        d = c.get("/netbox/safety/progress/ffffffffffffffffffffffff").get_json()
        assert d == {"ok": True, "state": "unknown", "progress": None}

    def test_the_in_flight_panel_lists_it(self, monkeypatch):
        from modules import op_progress

        c = self._client(monkeypatch)
        op_progress.start(PID, "previewed for import", "NetBox (Default)", actor="p")
        d = c.get("/operations/in_flight").get_json()
        assert any(r["device"] == "NetBox (Default)" for r in d["running"]), d["running"]


class TestTheShippedText:
    def _text(self, payload):
        import dukpy

        from tests.test_concepts_are_taught import lift

        src = read_shipped("static/js/gen/partials__netbox_safety_modal.1.js")
        return dukpy.evaljs(lift(src, "nbProgressText") + f"\nnbProgressText({json.dumps(payload)})")

    def test_every_state_says_something(self):
        from modules import op_progress

        op_progress.start(PID, "previewed for import", "NetBox (Lab)")
        op_progress.update(PID, devices_total=9, devices_done=3, current="r4",
                           phase="reading and planning each device")
        op_progress.tick(PID)
        running = {"ok": True, "state": "running", "progress": op_progress.get(PID)}
        assert self._text(running).startswith("1 request(s) to NetBox so far; device 4 of 9 (r4)")
        op_progress.finish(PID)
        assert self._text({"ok": True, "state": "finished",
                           "progress": op_progress.get(PID)}).startswith("Done in ")
        assert self._text({"ok": True, "state": "unknown", "progress": None}).startswith("Waiting")
        # A failed poll is said, never drawn as nothing.
        assert "Could not read its progress" in self._text({"ok": False})
        assert "Could not read its progress" in self._text(None)
