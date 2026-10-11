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

    def test_a_refusal_by_netbox_is_said_and_the_rest_still_written(self, writes_open,
                                                                     monkeypatch):
        """Measured on the lab's NetBox: the token may create the field and may not change a
        device role (403). It crashed with a traceback; now it says so and reads back."""
        from tests.fake_netbox import FakeResponse
        nb = _nb()
        p = RK.plan(MAP, RK.read(nb, BASE))
        monkeypatch.setattr(nb, "patch", lambda url, json=None, timeout=None: FakeResponse(
            {"detail": "You do not have permission to perform this action."}, 403))
        got = RK.apply(p, nb, BASE, "tester")
        assert got["ok"] is False
        assert got["lines"][0] == "created the custom field mercury_kind on device roles"
        assert any(l.startswith("REFUSED by NetBox: role router: PATCH") and "403" in l
                   for l in got["lines"])
        assert "NOT there: router, switch" in got["lines"][-1]

    def test_a_write_that_did_not_land_is_said(self, writes_open, monkeypatch):
        """The control for the read back: a PATCH that answers but changes nothing."""
        nb = _nb()
        p = RK.plan(MAP, RK.read(nb, BASE))
        monkeypatch.setattr(nb, "patch", lambda url, json=None, timeout=None:
                            nb.get(url))
        got = RK.apply(p, nb, BASE, "tester")
        assert got["ok"] is False and "NOT there: router, switch" in got["lines"][-1]


def _writer(nb):
    """The script's write, on the fake: one role's kind by PATCH (looked up at call time, so a
    test can replace the fake's patch)."""
    return lambda role_id, kind: nb.patch(f"{BASE}/api/dcim/device-roles/{role_id}/",
                                          json={"custom_fields": {RK.FIELD: kind}}).status_code


class TestTheAdminPath:
    """The operator's host step (scripts/host-steps/netbox-role-kinds.sh) with an admin's token:
    only the roles the map lists are written; the rest are left alone and said; every role is
    read back; a map naming a kind Mercury has not is refused before anything is sent."""

    def _nb(self):
        nb = _nb(True, {"router": "switch"})
        nb.seed("dcim/device-roles", {"slug": "core-switch", "name": "core-switch",
                                      "custom_fields": {}})
        return nb

    def test_only_listed_roles_are_written_and_each_is_read_back(self):
        nb = self._nb()
        got = RK.admin_apply(nb, BASE, RK.ADMIN_MAP, write=_writer(nb))
        assert got["ok"] is True, got
        rows = {r["slug"]: r for r in got["rows"]}
        assert rows["router"] == {"slug": "router", "before": "switch", "wanted": "router",
                                  "after": "router", "outcome": "set"}
        assert rows["core-switch"]["after"] == "switch"
        assert rows["network-device"]["outcome"] == "not listed: unchanged"
        assert rows["edge-router"]["outcome"] == "listed, but NetBox holds no such role"
        assert {p[1] for p in nb.patches} == {nb.store["dcim/device-roles"][i]["id"]
                                              for i in (1, 2, 3)}

    def test_the_plan_writes_nothing(self):
        nb = self._nb()
        got = RK.admin_apply(nb, BASE, RK.ADMIN_MAP, write=None)
        assert nb.patches == [] and {r["outcome"] for r in got["rows"]} >= {"would set"}

    def test_a_kind_mercury_has_not_is_refused_before_anything_is_sent(self):
        nb = self._nb()
        got = RK.admin_apply(nb, BASE, dict(RK.ADMIN_MAP, **{"core-switch": "l3-switch"}), write=_writer(nb))
        assert got["ok"] is False and "l3-switch" in got["error"] and nb.patches == []

    def test_a_write_that_does_not_land_is_a_fail(self, monkeypatch):
        nb = self._nb()
        monkeypatch.setattr(nb, "patch", lambda url, json=None, timeout=None: nb.get(url))
        got = RK.admin_apply(nb, BASE, RK.ADMIN_MAP, write=_writer(nb))
        assert got["ok"] is False


def test_the_script_takes_the_token_on_stdin_and_never_prints_it(monkeypatch, capsys):
    import importlib.machinery
    import importlib.util
    import io
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts",
                        "nmas-netbox-role-kinds-admin")
    loader = importlib.machinery.SourceFileLoader("role_kinds_admin", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    nb = _nb(True)
    monkeypatch.setattr("modules.netbox_client.get_user_setting",
                        lambda k, d=None: {"netbox_url": BASE + "/api"}.get(k, d))
    seen = {}

    def session(token, verify, scheme):
        seen["token"] = token
        return nb
    monkeypatch.setattr("modules.netbox_client._build_session", session)
    rc = mod.main(["--plan"], stdin=io.StringIO("s3cr3t-admin-token\n"))
    out = capsys.readouterr().out
    assert rc == 0 and seen["token"] == "s3cr3t-admin-token"
    assert "s3cr3t" not in out and "PLAN ONLY" in out and "router" in out
