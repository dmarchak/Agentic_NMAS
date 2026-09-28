"""The NetBox import's confirmation survives the trip: a REAL preview's token,
driven into the REAL apply (2026-09-28).

The operator: "This confirmation has expired or was already used", repeatedly,
5 seconds after a preview. Measured on the host, the token was issued and
never found: the import previews wrapped their whole response in
`outbound.mask_payload`, which masks by KEY, and `token` is a secret key name.
So since C77's sweep every import preview sent `<redacted:token>`, and the
import could not be confirmed at all. Each half was tested alone (the preview
for secrets, the apply for tokens); nothing drove one into the other, the
`/deploy/plan` -> `/deploy/apply` seam lesson again.
"""

import pytest

PLAN = {"creates": [{"endpoint": "dcim/devices", "name": "r9", "id": -2, "payload": {}}],
        "updates": [], "deletes": [], "create_count": 1, "update_count": 0,
        "delete_count": 0, "creates_by_type": {"dcim/devices": 1}, "updates_by_type": {},
        "deletes_by_type": {}}


@pytest.fixture
def client(monkeypatch):
    from modules import netbox_guard
    import modules.netbox_client as nbc
    import routes.netbox_safety as ns

    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                           "token": "t"})
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    devices = [{"hostname": "r9", "ip": "192.0.2.9"}]
    monkeypatch.setattr(ns, "_load_list_devices", lambda name: ("Default", devices))
    monkeypatch.setattr(ns, "_all_lists_with_devices", lambda: [("Default", devices)])
    ran = []
    monkeypatch.setattr(nbc, "sync_list_to_netbox",
                        lambda name, devs, dry_run=False: (ran.append(dry_run), {"plan": PLAN})[1])
    monkeypatch.setattr(nbc, "sync_all_lists_to_netbox",
                        lambda items, dry_run=False: (ran.append(dry_run), {"plan": PLAN})[1])
    monkeypatch.setattr(nbc, "set_sync_running", lambda *a, **k: None)
    import app as A

    return A.app.test_client(), ran


@pytest.mark.parametrize("op", ["import", "import_all"])
def test_the_token_a_preview_returns_confirms_the_apply(client, op):
    c, ran = client
    body = {"list_name": "Default"} if op == "import" else {}
    d = c.post(f"/netbox/safety/{op}/preview", json=body).get_json()
    assert d["ok"], d
    assert not d["token"].startswith("<redacted"), "the confirmation was masked on its way out"
    r = c.post(f"/netbox/safety/{op}/apply", json=dict(body, token=d["token"]))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status"] == "started"


def test_the_preview_is_still_masked(client, monkeypatch):
    """The fix moved the mask, it did not remove it: a planted secret in the
    preview is still masked; only the token passes intact."""
    import modules.preview_confirm as pc

    real = pc.netbox_import_preview

    def planted(d, confirm, **k):
        p = real(d, confirm, **k)
        p["what"]["summary"] += " snmp-server community PlantedC0mmunity RO"
        return p

    monkeypatch.setattr(pc, "netbox_import_preview", planted)
    c, _ran = client
    d = c.post("/netbox/safety/import/preview", json={"list_name": "Default"}).get_json()
    assert "PlantedC0mmunity" not in str(d["preview"])
    assert not d["token"].startswith("<redacted")
