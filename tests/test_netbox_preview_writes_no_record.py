"""C1596: a preview of a NetBox change writes none of Mercury's NetBox records.

Abandon's preview of s5 (2026-10-23) ran `remove_device_from_netbox` under the dry run: the
simulated delete "succeeded" and its caller forgot the object, for real, so the preview disowned
a record it only pretended to remove (the confirm, re-planning, then refused it as "not in
Mercury's created-object record"). CLAUDE.md: a preview runs the real code, so every write that
code makes is the preview's write too.

The rule is one, in the guard (`netbox_guard._write_json_atomic`, every write of the created,
modified and adopted records): under `netbox_guard.dry_run()` nothing is written. Each writer is
driven inside a dry run with the three stores read before and after, byte for byte; each is
driven outside one too, the control that the instrument sees its write. The remover is driven
through a fake NetBox, as Abandon's preview drives it.
"""

import os

import pytest

from modules import netbox_guard as guard
from tests.fake_netbox import FakeNetBox

LIST = "probe-c1596"
STORES = ("_CREATED_IDS_FILE", "_MODIFIED_FILE", "_ADOPTED_FILE")


@pytest.fixture
def stores(tmp_path, monkeypatch):
    for name in STORES:
        monkeypatch.setattr(guard, name, str(tmp_path / f"{name.lower()}.json"))
    monkeypatch.setattr(guard, "_db_store", lambda path: None)   # the files, not the database
    guard.record_created(LIST, "dcim/devices", 7, "kept-device")
    guard.record_created(LIST, "dcim/interfaces", 8, "Gi1")
    return [getattr(guard, n) for n in STORES]


def _snapshot(paths):
    out = {}
    for p in paths:
        try:
            with open(p, "rb") as fh:
                out[os.path.basename(p)] = fh.read()
        except FileNotFoundError:
            out[os.path.basename(p)] = None
    return out


#: Every writer of the three records, each with arguments that reach its write.
WRITERS = {
    "record_created": lambda: guard.record_created(LIST, "dcim/devices", 9, "new-device"),
    "forget_created one": lambda: guard.forget_created(LIST, "dcim/devices", 7),
    "forget_created all": lambda: guard.forget_created(LIST),
    "mark_created_retired": lambda: guard.mark_created_retired(
        LIST, "dcim/devices", [7], device="kept-device", by="t@example.com"),
    "record_modified": lambda: guard.record_modified(
        LIST, "dcim/devices", 7, {"description": {"before": "a", "after": "b"}},
        name="kept-device", actor="t@example.com"),
    "record_adopted": lambda: guard.record_adopted(
        LIST, "kept-device", [("dcim/devices", 7, "kept-device")], actor="t@example.com",
        reason="adopted for the test", authority="the test"),
}


@pytest.mark.parametrize("name", sorted(WRITERS))
def test_a_writer_inside_a_dry_run_writes_no_record(stores, name):
    before = _snapshot(stores)
    with guard.dry_run():
        WRITERS[name]()
    assert _snapshot(stores) == before, f"{name} wrote a record inside a dry run"


@pytest.mark.parametrize("name", sorted(WRITERS))
def test_the_same_writer_outside_one_writes_its_record(stores, name):
    """The control: the instrument sees each writer's write when it is real."""
    before = _snapshot(stores)
    WRITERS[name]()
    assert _snapshot(stores) != before, f"{name} wrote nothing outside a dry run"


@pytest.fixture
def netbox(stores, monkeypatch):
    import modules.netbox_client as nbc

    nb = FakeNetBox()
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                           "token": "t"})
    monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: nb)
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})
    monkeypatch.setattr(guard, "writes_allowed", lambda: True)
    monkeypatch.setattr(guard, "assert_writes_allowed", lambda *a: None)
    tag = [{"slug": guard.MANAGED_TAG_SLUG, "name": guard.MANAGED_TAG}]
    dev = nb.seed("dcim/devices", {"name": "bp-c1596", "tags": tag})
    guard.record_created(LIST, "dcim/devices", dev["id"], "bp-c1596")
    return nb, dev


def test_the_device_remover_s_preview_keeps_its_record(netbox, stores):
    """s5's case: the preview says the device would be removed, NetBox is untouched, and the
    created-object record still claims it, so the confirm can act on it."""
    from modules.netbox_client import remove_device_from_netbox

    nb, dev = netbox
    before = _snapshot(stores)
    out = remove_device_from_netbox(LIST, "bp-c1596", dry_run=True, actor="t@example.com",
                                    authority="the test", netbox_id=dev["id"])
    assert out["ok"] and [d["id"] for d in out["deleted"]] == [dev["id"]], out
    assert nb.deletes == [], "the preview deleted in NetBox"
    assert _snapshot(stores) == before, "the preview wrote the created-object record"
    assert guard.was_created_by_nmas(LIST, "dcim/devices", dev["id"])


def test_the_device_remover_s_real_run_forgets_what_it_deleted(netbox, stores):
    """The control: the confirm deletes and forgets."""
    from modules.netbox_client import remove_device_from_netbox

    nb, dev = netbox
    out = remove_device_from_netbox(LIST, "bp-c1596", actor="t@example.com",
                                    authority="the test", netbox_id=dev["id"])
    assert out["ok"] and ("dcim/devices", dev["id"]) in nb.deletes, out
    assert not guard.was_created_by_nmas(LIST, "dcim/devices", dev["id"])


def test_a_list_removal_previewed_inside_a_dry_run_keeps_the_record(netbox, stores):
    """`remove_list_from_netbox` keeps its own `if not dry_run` (C130); the guard's rule holds
    under any caller's dry run as well."""
    from modules.netbox_client import remove_list_from_netbox

    nb, _dev = netbox
    before = _snapshot(stores)
    with guard.dry_run():
        remove_list_from_netbox(LIST, dry_run=True)
    assert nb.deletes == [] and _snapshot(stores) == before
