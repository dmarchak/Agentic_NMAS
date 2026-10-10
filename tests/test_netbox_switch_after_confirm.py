"""C330 (2026-10-02): a refused NetBox confirm could still turn the master write switch ON.

The three apply routes called `_maybe_permit_writes()` before `_authorize()` checked the
one-shot token and the plan, so a confirm carrying `permit_writes` with an expired token or
a moved plan was refused AND left `netbox_allow_writes` on, written through
`set_user_setting` with no actor. CLAUDE.md: the switch is "never flipped as a side effect".

Through the real preview and apply routes and the REAL switch (`netbox_guard.writes_allowed`
reading the settings store); only NetBox itself is faked, as in the token round-trip test.
"""

import pytest

from tests.test_netbox_preview_token_round_trip import PLAN


@pytest.fixture
def client(monkeypatch):
    import modules.netbox_client as nbc
    import routes.netbox_safety as ns
    from modules.settings_schema import write_settings

    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                           "token": "t"})
    devices = [{"hostname": "r9", "ip": "192.0.2.9"}]
    monkeypatch.setattr("modules.netbox_ops.list_devices", lambda name: ("Default", devices))
    plan = {"value": PLAN}
    monkeypatch.setattr(nbc, "sync_list_to_netbox",
                        lambda name, devs, dry_run=False, **k: {"plan": plan["value"]})
    monkeypatch.setattr(nbc, "set_sync_running", lambda *a, **k: None)
    assert write_settings({"netbox_allow_writes": False}, actor="test")["ok"]
    import app as A
    yield A.app.test_client(), plan
    write_settings({"netbox_allow_writes": False}, actor="test")


def _switch():
    from modules.netbox_guard import writes_allowed
    return writes_allowed()


def _preview(c):
    d = c.post("/netbox/safety/import/preview", json={"list_name": "Default"}).get_json()
    assert d["ok"], d
    return d["token"]


class TestTheSwitchMovesOnlyWithAConfirmThatPasses:
    def test_an_expired_token_leaves_the_switch_off(self, client):
        c, _plan = client
        r = c.post("/netbox/safety/import/apply", json={
            "list_name": "Default", "token": "not-a-token", "permit_writes": True})
        assert r.status_code in (400, 409), r.get_json()
        assert _switch() is False, "a refused confirm turned the master switch on"

    def test_a_moved_plan_leaves_the_switch_off(self, client):
        c, plan = client
        token = _preview(c)
        plan["value"] = dict(PLAN, create_count=2,
                             creates=PLAN["creates"] + [dict(PLAN["creates"][0], name="r10")])
        r = c.post("/netbox/safety/import/apply", json={
            "list_name": "Default", "token": token, "permit_writes": True})
        assert r.status_code == 409 and r.get_json().get("stale"), r.get_json()
        assert _switch() is False, "a refused confirm turned the master switch on"

    def test_a_confirm_that_passes_turns_it_on(self, client):
        c, _plan = client
        token = _preview(c)
        r = c.post("/netbox/safety/import/apply", json={
            "list_name": "Default", "token": token, "permit_writes": True})
        assert r.status_code == 200, r.get_json()
        assert _switch() is True

    def test_without_asking_the_switch_stays_off_and_refuses(self, client):
        c, _plan = client
        token = _preview(c)
        r = c.post("/netbox/safety/import/apply", json={"list_name": "Default", "token": token})
        assert r.status_code == 403 and r.get_json().get("blocked")
        assert _switch() is False
