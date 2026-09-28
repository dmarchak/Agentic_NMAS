"""C155: deleting a device list never deletes NetBox objects.

It used to, with no preview and no confirmation, when `netbox_remove_on_list_delete`
was on (the one-shot token is consumed by the NetBox tab's routes, not at the
write); and with the setting off it FORGOT the created-object record while the
objects stayed, leaving them tagged and unrecorded, out of Remove's reach for
good. Removal has one home, the NetBox tab's previewed Remove: a list that
still owns recorded objects is refused, naming them.
"""

import json

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    import app as A
    from modules import identity, netbox_guard
    import modules.netbox_client as nbc

    record = tmp_path / "netbox_created_ids.json"
    monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE", str(record))
    who = identity.Identity(actor="p@example.invalid", email="p@example.invalid",
                            kind="person", verified=True, outcome="ok",
                            peer="198.51.100.7", peer_trusted=True, header_present=True)
    monkeypatch.setattr(identity, "identify", lambda _r: who)
    deleted, netbox = [], []
    monkeypatch.setattr(A, "delete_device_list_func",
                        lambda name: deleted.append(name) or (True, f"Deleted '{name}'"))
    for name in ("remove_list_from_netbox", "remove_device_from_netbox", "_nb_delete"):
        monkeypatch.setattr(nbc, name, lambda *a, **k: netbox.append((a, k)) or {"ok": True})
    A.app.config["TESTING"] = False
    return A.app.test_client(), record, deleted, netbox


def _delete(c):
    return c.delete("/device_lists/probe-r1", headers={"Accept": "application/json"})


def test_a_list_that_still_owns_recorded_objects_is_refused_naming_them(client):
    c, record, deleted, netbox = client
    record.write_text(json.dumps({"probe_r1": {"dcim/devices": [{"id": 14, "name": "probe-r1a"}]}}))
    r = _delete(c)
    body = r.get_json()
    assert r.status_code == 409 and "dcim/devices/14 probe-r1a" in body["message"], body
    assert "NetBox tab" in body["message"] and "Nothing was changed" in body["message"]
    assert deleted == [] and netbox == []
    assert json.loads(record.read_text())["probe_r1"], "the record was kept, not forgotten"


def test_a_list_with_nothing_recorded_is_deleted_and_netbox_is_never_touched(client):
    """The floor, and the teardown's case (R2b removed probe-r1's objects)."""
    c, record, deleted, netbox = client
    record.write_text(json.dumps({"probe_r1": {"dcim/devices": []}, "default": {}}))
    r = _delete(c)
    assert r.status_code == 200, r.get_json()
    assert deleted == ["probe-r1"] and netbox == []
    assert "probe_r1" not in json.loads(record.read_text())


def test_an_unreadable_record_is_refused_not_read_as_owning_nothing(client):
    c, record, deleted, netbox = client
    record.write_text('{"probe_r1": {"dcim/dev')
    r = _delete(c)
    assert r.status_code == 409 and "could not be read" in r.get_json()["message"]
    assert deleted == [] and netbox == []


def test_nothing_reads_the_retired_setting():
    """C155: the key stays in the schema (keys are never deleted) and is read
    by nothing, so no path can turn the cascade back on."""
    import os
    import re

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    readers = []
    for base in ("modules", "routes", "app.py", "templates", "static/js/gen"):
        path = os.path.join(root, base)
        files = [path] if os.path.isfile(path) else [
            os.path.join(d, f) for d, _s, fs in os.walk(path) for f in fs
            if f.endswith((".py", ".html", ".js"))]
        for p in files:
            text = open(p, encoding="utf-8", errors="replace").read()
            if re.search(r"\bnetbox_remove_on_list_delete\b", text):
                readers.append(os.path.relpath(p, root))
    assert readers == ["modules/settings_schema.py"], readers
