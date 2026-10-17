"""C155: deleting a network never deletes NetBox objects.

It used to, with no preview and no confirmation, when `netbox_remove_on_list_delete`
was on (the one-shot token is consumed by the NetBox screen's routes, not at the
write); and with the setting off it FORGOT the created-object record while the
objects stayed, leaving them tagged and unrecorded, out of Remove's reach for
good. Removal has one home, Source of truth › NetBox's previewed Remove: a network
that still owns recorded objects is refused, naming them.

Rebased onto v2 at 7.8 (2026-10-17, P7-26), when today's DELETE /device_lists/<name>,
which held this guard, left: Settings' Delete this network… (`network_admin`) had
no such guard (it deleted a network whose recorded NetBox objects were then out of
every Remove's reach, the network gone), so it was carried over, in the preview and
again at the confirm, through `netbox_guard.recorded_objects`.
"""

import json
import re

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)


@pytest.fixture
def nb(networks, monkeypatch):  # noqa: F811
    from modules import netbox_guard
    import modules.netbox_client as nbc

    record = networks["dir"] / "netbox_created_ids.json"
    monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE", str(record))
    netbox = []
    for name in ("remove_list_from_netbox", "remove_device_from_netbox", "_nb_delete"):
        monkeypatch.setattr(nbc, name, lambda *a, **k: netbox.append((a, k)) or {"ok": True})
    return dict(networks, record=record, netbox=netbox)


def _post(n, path, data=None):
    r = n["client"].post(path, data=data or {}, headers={"HX-Request": "true"})
    return r, re.sub(r"\s+", " ", r.get_data(as_text=True))


def _registry(n):
    return json.loads((n["dir"] / "device_lists.json").read_text())["lists"]


def _fp(html):
    m = re.search(r'name="fingerprint" value="([0-9a-f]+)"', html)
    return m.group(1) if m else ""


def test_a_network_that_still_owns_recorded_objects_is_refused_naming_them(nb):
    nb["record"].write_text(json.dumps(
        {"branch": {"dcim/devices": [{"id": 14, "name": "probe-r1a"}]}}))
    _r, pv = _post(nb, "/v2/settings/network/Branch/delete/preview")
    assert "dcim/devices/14 probe-r1a" in pv and "Source of truth › NetBox" in pv, pv
    assert 'name="typed"' not in pv, "no confirm is offered"
    r, html = _post(nb, "/v2/settings/network/Branch/delete",
                    {"typed": "Branch", "fingerprint": _fp(pv) or "x"})
    assert r.status_code == 409 and "dcim/devices/14 probe-r1a" in html
    assert "Branch" in _registry(nb) and nb["netbox"] == []
    assert json.loads(nb["record"].read_text())["branch"], "the record was kept, not forgotten"


#: W4 walk's record as its delete card named it (the operator, W4 step 69, 2026-10-17, screenshot
#: 89): a region, a site and a VRF (types whose cascade is unmeasured, C1097) with devices,
#: interfaces and addresses.
W4_RECORD = {"branch": {
    "dcim/regions": [{"id": 10, "name": "W4 walk"}], "dcim/sites": [{"id": 8, "name": "W4 walk"}],
    "ipam/vrfs": [{"id": 9, "name": "W4 walk"}],
    "dcim/devices": [{"id": 16, "name": "s6"}, {"id": 17, "name": "s5"}],
    "dcim/interfaces": [{"id": 73, "name": "GigabitEthernet1"}]}}


class TestTheRefusalSaysTheWayThrough:
    """C1191 (the operator, W4 step 69, 2026-10-17): a network that ever created NetBox objects
    can be deleted on this lab only by Stop tracking first (C1138's guard here, with Remove
    withheld while a cascade is unmeasured, C1097), and the card sent the person to "Remove
    from NetBox…, or Stop tracking instead…" as if Remove would do. It says the way plainly:
    where Stop tracking is, what it forgets, that NetBox keeps the objects, and why Remove
    cannot delete them here."""

    def test_unmeasured_types_name_stop_tracking_as_the_way_and_say_remove_cannot(self, nb):
        nb["record"].write_text(json.dumps(W4_RECORD))
        _r, pv = _post(nb, "/v2/settings/network/Branch/delete/preview")
        text = re.sub(r"<[^>]+>", " ", pv)
        assert "the way through is Stop tracking" in text, text
        assert "Source of truth › NetBox, Branch&#39;s Remove from NetBox…, then Stop tracking " \
               "instead…" in pv, pv
        assert "deletes nothing in NetBox" in text
        assert "Mercury forgets the 6 objects it created for Branch" in text
        assert "NetBox keeps every one, with its nmas-managed tag" in text
        assert ("Remove from NetBox… cannot delete them here: what NetBox takes with a delete "
                "of dcim/regions, dcim/sites, ipam/vrfs has not been measured") in text
        assert 'name="typed"' not in pv, "still refused: no confirm is offered"

    def test_measured_types_keep_remove_as_a_way(self, nb):
        """The control: a record of devices and interfaces only (cascades measured) names
        Remove from NetBox… as the first way, Stop tracking as the other."""
        nb["record"].write_text(json.dumps(
            {"branch": {"dcim/devices": [{"id": 14, "name": "probe-r1a"}]}}))
        _r, pv = _post(nb, "/v2/settings/network/Branch/delete/preview")
        text = re.sub(r"<[^>]+>", " ", pv)
        assert "cannot delete them here" not in text and "the way through is Stop" not in text
        assert "remove them first on Source of truth › NetBox (Branch&#39;s Remove from " \
               "NetBox…)" in pv, pv
        assert "or forget them there with Stop tracking instead…" in text
        assert "NetBox keeps every one" in text


def test_objects_recorded_after_the_preview_refuse_the_confirm(nb):
    """The confirm checks again: an import between the preview and the confirm is not lost."""
    _r, pv = _post(nb, "/v2/settings/network/Branch/delete/preview")
    assert 'name="typed"' in pv
    nb["record"].write_text(json.dumps(
        {"branch": {"dcim/interfaces": [{"id": 7, "name": "Gi0/1"}]}}))
    r, html = _post(nb, "/v2/settings/network/Branch/delete",
                    {"typed": "Branch", "fingerprint": _fp(pv)})
    assert r.status_code == 409 and "dcim/interfaces/7 Gi0/1" in html
    assert "Branch" in _registry(nb)


def test_a_network_with_nothing_recorded_is_deleted_and_netbox_is_never_touched(nb):
    """The floor, and the teardown's case (R2b removed probe-r1's objects)."""
    nb["record"].write_text(json.dumps({"branch": {"dcim/devices": []}, "default": {}}))
    _r, pv = _post(nb, "/v2/settings/network/Branch/delete/preview")
    r, html = _post(nb, "/v2/settings/network/Branch/delete",
                    {"typed": "Branch", "fingerprint": _fp(pv)})
    assert r.status_code == 200 and "Branch is deleted:" in html, html
    assert "Branch" not in _registry(nb) and nb["netbox"] == []
    assert "branch" not in json.loads(nb["record"].read_text()), "its empty entry is dropped"
    assert "default" in json.loads(nb["record"].read_text())


def test_an_unreadable_record_is_refused_not_read_as_owning_nothing(nb):
    nb["record"].write_text('{"branch": {"dcim/dev')
    _r, pv = _post(nb, "/v2/settings/network/Branch/delete/preview")
    assert "could not be read" in pv and 'name="typed"' not in pv
    r, _html = _post(nb, "/v2/settings/network/Branch/delete",
                     {"typed": "Branch", "fingerprint": "x"})
    assert r.status_code == 409 and "Branch" in _registry(nb) and nb["netbox"] == []


def test_nothing_reads_the_retired_setting():
    """C155: the key stays in the schema (keys are never deleted) and is read
    by nothing, so no path can turn the cascade back on."""
    import os

    from tests.source_index import tracked

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    readers = []
    for base in ("modules", "routes", "app.py", "templates", "static/js/gen"):
        path = os.path.join(root, base)
        files = [path] if os.path.isfile(path) else tracked(path, suffix=(".py", ".html", ".js"))
        for p in files:
            text = open(p, encoding="utf-8", errors="replace").read()
            if re.search(r"\bnetbox_remove_on_list_delete\b", text):
                readers.append(os.path.relpath(p, root))
    # The schema declares it, and P.8's scope table declares it DEAD (never split); neither
    # reads its value.
    assert readers == ["modules/settings_schema.py", "modules/settings_scope.py"], readers
    from modules.settings_scope import DEAD, scope_of
    assert scope_of("netbox_remove_on_list_delete")[0] == DEAD
