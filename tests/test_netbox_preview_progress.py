"""A NetBox preview or import says what it is doing while it runs (the
operator, 2026-09-28: "a slow operation that says what it's doing is usable; a
fast one that goes blank isn't").

Measured on the host: a 9-device import preview took 54 s, 303 requests to
NetBox at 176 ms mean, behind a bare spinner. Each preview has an id (v2's
NetBox page: its job's; today's modal sent its own until today's NetBox tab left
at 7.8, 2026-10-17), the sync reports under it (`modules.op_progress`: requests
counted at the session, the device it is on), the job's card draws it on the one
stepper, and the in-flight panel (C99) lists it with every device operation.
"""

import pytest

from tests.fake_netbox import FakeNetBox
from tests.test_netbox_v2 import nb  # noqa: F401 (the fixture: NetBox faked at its edge)
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

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
    """Through v2's NetBox page (today's NetBox tab, whose preview took the page's
    `progress_id` and whose /netbox/safety/progress/<id> the modal polled, left at 7.8,
    2026-10-17): a preview job reports under its own id, and its card draws it on the one
    stepper (tests/test_one_stepper.py holds the card's every state)."""

    @pytest.fixture
    def page(self, networks, nb, monkeypatch):
        import modules.netbox_client as nbc

        def fake_sync(name, devs, dry_run=False, progress_id="", **k):
            from modules import op_progress
            op_progress.tick(progress_id)
            return {"plan": {"creates": [], "updates": [], "deletes": []}}

        monkeypatch.setattr(nbc, "sync_list_to_netbox", fake_sync)
        return networks["client"]

    def test_a_preview_reports_under_its_job_s_id(self, page):
        import re

        from modules import op_progress

        card = page.post("/v2/netbox/preview", data={"operation": "import", "list": "Branch"},
                         headers={"HX-Request": "true"}).get_data(as_text=True)
        job = re.search(r"/v2/netbox/job/([0-9a-f]{32})", card).group(1)
        got = op_progress.get(job)
        assert got["requests"] == 1 and got["outcome"] == "done", got
        assert got["finished_at"]

    def test_an_unknown_job_is_unknown_never_not_running(self, page):
        html = page.get("/v2/netbox/job/" + "f" * 32).get_data(as_text=True)
        assert "This job is not known here" in html and "preview again" in html

    def test_the_in_flight_panel_lists_it(self, page):
        from modules import op_progress

        op_progress.start(PID, "previewed for import", "NetBox (Default)", actor="p")
        d = page.get("/operations/in_flight").get_json()
        assert any(r["device"] == "NetBox (Default)" for r in d["running"]), d["running"]


