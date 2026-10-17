"""C330 (2026-10-02): a refused NetBox confirm could still turn the master write switch ON.

The three apply routes called `_maybe_permit_writes()` before `_authorize()` checked the
one-shot token and the plan, so a confirm carrying `permit_writes` with an expired token or
a moved plan was refused AND left `netbox_allow_writes` on, written through
`set_user_setting` with no actor. CLAUDE.md: the switch is "never flipped as a side effect".

Through the import's real preview and confirm core (`netbox_ops.dry_run` and
`netbox_ops.start_import`, which v2's NetBox page's preview job and confirm call; today's
/netbox/safety routes called them until the NetBox tab left at 7.8, 2026-10-17) and the REAL
switch (`netbox_guard.writes_allowed` reading the settings store); only NetBox itself is
faked, as in the token round-trip test.
"""

import pytest

from tests.test_netbox_preview_token_round_trip import PLAN

ACTOR = "ops@example.com"


class _Inline:
    def __init__(self, target=None, **_k):
        self.target = target

    def start(self):
        self.target()


@pytest.fixture
def plan(monkeypatch):
    import modules.netbox_client as nbc
    from modules.settings_schema import write_settings

    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                           "token": "t"})
    devices = [{"hostname": "r9", "ip": "192.0.2.9"}]
    monkeypatch.setattr("modules.netbox_ops.list_devices", lambda name: ("Default", devices))
    value = {"value": PLAN}
    monkeypatch.setattr(nbc, "sync_list_to_netbox",
                        lambda name, devs, dry_run=False, **k: {"plan": value["value"]})
    monkeypatch.setattr(nbc, "set_sync_running", lambda *a, **k: None)
    monkeypatch.setattr("modules.netbox_ops.threading.Thread", _Inline)
    assert write_settings({"netbox_allow_writes": False}, actor="test")["ok"]
    yield value
    write_settings({"netbox_allow_writes": False}, actor="test")


def _switch():
    from modules.netbox_guard import writes_allowed
    return writes_allowed()


def _preview():
    from modules import netbox_ops
    d = netbox_ops.dry_run("import", "Default", ACTOR)
    assert d["ok"], d
    return d["token"]


def _confirm(data):
    """``(status, payload)``: 200 and the start for a confirm that passed."""
    from modules import netbox_ops
    try:
        return 200, netbox_ops.start_import("import", "Default", data, ACTOR)
    except netbox_ops.Refused as exc:
        return exc.status, exc.payload


class TestTheSwitchMovesOnlyWithAConfirmThatPasses:
    def test_an_expired_token_leaves_the_switch_off(self, plan):
        status, body = _confirm({"token": "not-a-token", "permit_writes": True})
        assert status in (400, 409), body
        assert _switch() is False, "a refused confirm turned the master switch on"

    def test_a_moved_plan_leaves_the_switch_off(self, plan):
        token = _preview()
        plan["value"] = dict(PLAN, create_count=2,
                             creates=PLAN["creates"] + [dict(PLAN["creates"][0], name="r10")])
        status, body = _confirm({"token": token, "permit_writes": True})
        assert status == 409 and body.get("stale"), body
        assert _switch() is False, "a refused confirm turned the master switch on"

    def test_a_confirm_that_passes_turns_it_on(self, plan):
        token = _preview()
        status, body = _confirm({"token": token, "permit_writes": True})
        assert status == 200 and body["status"] == "started", body
        assert _switch() is True

    def test_without_asking_the_switch_stays_off_and_refuses(self, plan):
        token = _preview()
        status, body = _confirm({"token": token})
        assert status == 403 and body.get("blocked"), body
        assert _switch() is False
