"""Source of truth › NetBox on v2 (cutover blocker 2, 2026-10-10), through the real app on a
temporary store (tests/test_settings_v2's `networks`). The sync is replaced at its edge as the
token round-trip test replaces it (a plan of one device to create); everything between (the
job, the preview component, the one-shot token, the master switch, the import's result) is the
real code. A job's thread runs inline here, so each answer is there when the test reads it.
"""

import re

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

PLAN = {"creates": [{"endpoint": "dcim/devices", "name": "r9", "id": -2, "payload": {}}],
        "updates": [], "deletes": [], "create_count": 1, "update_count": 0,
        "delete_count": 0, "creates_by_type": {"dcim/devices": 1}, "updates_by_type": {},
        "deletes_by_type": {}}


class _Inline:
    def __init__(self, target=None, **_k):
        self.target = target

    def start(self):
        self.target()


@pytest.fixture
def nb(networks, monkeypatch, tmp_path):
    import modules.netbox_client as nbc
    from modules import device, netbox_guard

    device.write_devices_csv([{"hostname": "r9", "ip": "192.0.2.9"}],
                             str(networks["dir"] / "lists" / "branch" / "devices.csv"))
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://192.0.2.8", "token": "t"})
    for name in ("_CREATED_IDS_FILE", "_MODIFIED_FILE", "_ADOPTED_FILE", "_REMOVALS_FILE"):
        monkeypatch.setattr(netbox_guard, name, str(tmp_path / f"{name.strip('_').lower()}"))
    switch = {"on": False}
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: switch["on"])

    def write_settings(changes, actor=""):
        switch["on"] = bool(changes.get("netbox_allow_writes", switch["on"]))
        return {"ok": True}
    monkeypatch.setattr("modules.settings_schema.write_settings", write_settings)
    plan = {"value": PLAN}
    sent = []

    def sync(name, devs, dry_run=False, **k):
        if not dry_run:
            sent.append(name)
        return {"plan": plan["value"]}
    monkeypatch.setattr(nbc, "sync_list_to_netbox", sync)
    monkeypatch.setattr(nbc, "set_sync_running", lambda *a, **k: None)
    monkeypatch.setattr(nbc, "sync_status_with_results", lambda: {"lists": {"Branch": {
        "timestamp": "2026-10-10T05:00:00Z", "result": {
            "level": "success", "happened": {"summary": "1 object created in NetBox for Branch."},
            "did_not": {"items": []}}}}})
    monkeypatch.setattr("modules.netbox_jobs.threading.Thread", _Inline)
    monkeypatch.setattr("modules.netbox_ops.threading.Thread", _Inline)
    return {"switch": switch, "plan": plan, "sent": sent}


def _post(n, path, data=None):
    r = n["client"].post(path, data=data or {}, headers={"HX-Request": "true"})
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


def _job(html):
    return re.search(r'/v2/netbox/job/([0-9a-f]{32})', html).group(1)


class TestThePage:
    def test_it_draws_every_network_under_the_strict_policy(self, networks, nb):
        from modules import csp
        r = networks["client"].get("/v2/netbox")
        html = re.sub(r"\s+", " ", r.get_data(as_text=True))
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert re.search(r'class="nav-item active" href="/v2/netbox" aria-current="page"', html)
        for name in ("Default", "Branch", "Lab-3", "Remote"):
            assert f"<td>{name}</td>" in html, name
        assert "Writes are <strong>off</strong>" in html and "Import every network…" in html

    def test_the_sidebar_no_longer_sends_netbox_to_today_s_page(self, networks, nb):
        html = networks["client"].get("/v2/devices").get_data(as_text=True)
        assert 'data-todays-page="netbox"' not in html


class TestImport:
    def test_preview_then_confirm_with_writes_permitted(self, networks, nb):
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Branch"})
        job = _job(card)
        card = re.sub(r"\s+", " ",
                      networks["client"].get(f"/v2/netbox/job/{job}").get_data(as_text=True))
        assert "create dcim/devices r9" in card and "turn NetBox writes on with this confirm" in card
        assert nb["sent"] == [], "the preview writes nothing"
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm", {"permit_writes": "on"})
        assert r.status_code == 200, html
        assert nb["sent"] == ["Branch"] and nb["switch"]["on"] is True
        done = re.sub(r"\s+", " ", networks["client"].get(f"/v2/netbox/job/{job}").get_data(as_text=True))
        assert "1 object created in NetBox for Branch." in done

    def test_writes_off_and_not_permitted_is_refused_and_nothing_written(self, networks, nb):
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Branch"})
        r, html = _post(networks, f"/v2/netbox/job/{_job(card)}/confirm")
        assert r.status_code == 403 and "NetBox writes are off for every network" in html
        assert nb["sent"] == [] and nb["switch"]["on"] is False

    def test_a_moved_plan_is_refused_and_the_switch_stays_off(self, networks, nb):
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Branch"})
        nb["plan"]["value"] = dict(PLAN, creates=PLAN["creates"] * 2, create_count=2)
        r, html = _post(networks, f"/v2/netbox/job/{_job(card)}/confirm", {"permit_writes": "on"})
        assert r.status_code == 409 and nb["sent"] == [] and nb["switch"]["on"] is False

    def test_a_token_is_used_once(self, networks, nb):
        nb["switch"]["on"] = True
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Branch"})
        job = _job(card)
        assert _post(networks, f"/v2/netbox/job/{job}/confirm")[0].status_code == 200
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        assert r.status_code == 409 and "not one ready to confirm" in html


class TestRefusals:
    @pytest.mark.parametrize("data,said", [
        ({"operation": "sideways", "list": "Branch"}, "no operation"),
        ({"operation": "import", "list": "Nowhere"}, "there is no network"),
    ])
    def test_a_preview_that_cannot_start_is_refused(self, networks, nb, data, said):
        r, html = _post(networks, "/v2/netbox/preview", data)
        assert r.status_code == 404 and said in html

    def test_a_network_with_no_devices_says_so_in_its_card(self, networks, nb):
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "import", "list": "Lab-3"})
        assert "has no devices" in card


class TestRemove:
    def test_preview_then_remove_is_recorded_and_drawn(self, networks, nb, monkeypatch):
        import modules.netbox_client as nbc
        nb["switch"]["on"] = True
        deleted = [{"endpoint": "dcim/devices", "id": 7, "name": "r9", "reason": ""}]
        monkeypatch.setattr(nbc, "remove_list_from_netbox", lambda name, **k: {
            "ok": True, "deleted": deleted, "skipped": [], "failed": [], "complete": True,
            "dry_run": bool(k.get("dry_run"))})
        _r, card = _post(networks, "/v2/netbox/preview", {"operation": "remove", "list": "Branch"})
        job = _job(card)
        r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
        assert r.status_code == 200 and "deleted from NetBox for Branch" in html, html
        page = networks["client"].get("/v2/netbox").get_data(as_text=True)
        assert "1 recorded" in page
