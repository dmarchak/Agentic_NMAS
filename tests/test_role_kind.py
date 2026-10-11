"""A device's kind is NetBox's (C665): the `mercury_kind` custom field on the Device Role, read
like any NetBox fact, and its one-time migration from Mercury's role map, planned, hashed and
applied through the client's chokepoints, then read back. On a fake NetBox."""

import pytest

from modules.inventory import role_kind as RK
from tests.fake_netbox import FakeNetBox

BASE = "http://netbox.example.invalid"
MAP = {"router": "router", "switch": "switch", "edge-router": "router", "firewall": "firewall"}


def _nb(field=False, kinds=None):
    nb = FakeNetBox()
    if field:
        nb.seed("extras/custom-fields", {"name": RK.FIELD})
    for slug in ("network-device", "router", "switch"):
        cf = {RK.FIELD: (kinds or {}).get(slug)} if field else {}
        nb.seed("dcim/device-roles", {"slug": slug, "name": slug, "custom_fields": cf})
    return nb


@pytest.fixture
def writes_open(monkeypatch):
    from modules import netbox_guard
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    monkeypatch.setattr(netbox_guard, "record_modified", lambda *a, **k: None)
    monkeypatch.setattr(netbox_guard, "record_created", lambda *a, **k: None)


class TestReading:
    def test_a_kind_is_read_and_anything_else_is_unclassified(self):
        now = RK.read(_nb(True, {"router": "router", "switch": "Bogus"}), BASE)
        assert now["field"] is True and now["kinds"] == {"router": "router"}

    def test_no_field_is_said(self):
        now = RK.read(_nb(), BASE)
        assert now["field"] is False and now["kinds"] == {}

    def test_an_unreadable_netbox_refuses(self):
        class Down:
            def get(self, *a, **k):
                raise ConnectionError("refused")
        with pytest.raises(RK.KindUnreadable):
            RK.read(Down(), BASE)


class TestThePlan:
    def test_it_creates_the_field_and_copies_the_map_onto_netbox_roles(self):
        p = RK.plan(MAP, RK.read(_nb(), BASE))
        assert p["create_field"] is True
        assert [(s["slug"], s["kind"]) for s in p["set"]] == [("router", "router"),
                                                              ("switch", "switch")]
        assert p["unclassified"] == ["network-device"], "the map does not name it"

    def test_netbox_s_own_kind_wins(self):
        p = RK.plan(MAP, RK.read(_nb(True, {"router": "firewall"}), BASE))
        assert p["create_field"] is False
        assert p["kept"] == [{"slug": "router", "kind": "firewall"}]
        assert [s["slug"] for s in p["set"]] == ["switch"]

    def test_the_hash_moves_with_the_plan(self):
        a = RK.plan(MAP, RK.read(_nb(), BASE))["hash"]
        b = RK.plan(dict(MAP, switch="router"), RK.read(_nb(), BASE))["hash"]
        assert a != b and a == RK.plan(MAP, RK.read(_nb(), BASE))["hash"]


class TestApplying:
    def test_it_writes_and_reads_back(self, writes_open):
        nb = _nb()
        p = RK.plan(MAP, RK.read(nb, BASE))
        got = RK.apply(p, nb, BASE, "tester")
        assert got["ok"] is True, got
        assert RK.read(nb, BASE)["kinds"] == {"router": "router", "switch": "switch"}
        assert got["lines"][-1] == "read back: every write is there"

    def test_without_writes_on_it_writes_nothing(self):
        from modules.netbox_guard import NetBoxWriteBlocked
        nb = _nb()
        p = RK.plan(MAP, RK.read(nb, BASE))
        with pytest.raises(NetBoxWriteBlocked):
            RK.apply(p, nb, BASE, "tester")
        assert nb.posts == [] and nb.patches == []

    def test_a_write_that_did_not_land_is_said(self, writes_open, monkeypatch):
        """The control for the read back: a PATCH that answers but changes nothing."""
        nb = _nb()
        p = RK.plan(MAP, RK.read(nb, BASE))
        monkeypatch.setattr(nb, "patch", lambda url, json=None, timeout=None:
                            nb.get(url))
        got = RK.apply(p, nb, BASE, "tester")
        assert got["ok"] is False and "NOT there: router, switch" in got["lines"][-1]
