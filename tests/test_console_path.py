"""O4 (docs/LAB9_PLAN.md section 8): a device's console path in NetBox, read and created
(`modules/nsot/console_path.py`), on the shared fake NetBox (tests/fake_netbox.py).

The fake's console model is MEASURED against the real service first (docs/TESTING.md practice 3):
its rendered cable, console port and console-server port are compared key for key with NetBox
4.6.9's captured answers (tests/fixtures/netbox/console_shapes.json, read-only, 2026-10-22), and
its paging with the captured ``next`` link. Then:

- the read: a path found (each part named); none, naming the query that came back empty; a port
  with no cable, named; a cable whose far end is not a console-server port; paged at one object
  a page; a truncated answer (short of its count, or a full page with no count) and a refused
  query are unreadable, never "no path";
- the create: refused before anything is written when the master switch is off, when no
  authority is declared, and when the authority is another operation's, each naming both; the
  objects it makes tagged ``nmas-managed`` and recorded as created with the authority; a second
  call creates nothing; a port cabled elsewhere refused; a console server that does not exist
  named by its query; the preview writes nothing and its hash holds;
- the removal: only what Mercury created (tagged AND recorded) is deleted; the console server's
  port is kept; a person's port and cable are named and kept.
"""

import json
import os

import pytest

from tests.fake_netbox import FakeNetBox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "netbox", "console_shapes.json")
BASE = "http://nb.invalid"
LIST = "console-o4"


def _capture():
    with open(CAPTURE, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def nb(tmp_path, monkeypatch):
    """A fake NetBox holding a planned device and a console server, writes on, the provenance
    records in a temp folder. ``nb.fake``, ``nb.dev``, ``nb.cs``, ``nb.cp`` (the module)."""
    import modules.netbox_client as nbc
    from modules import config, netbox_guard
    from modules.nsot import console_path

    monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE", str(tmp_path / "created.json"))
    monkeypatch.setattr(netbox_guard, "_MODIFIED_FILE", str(tmp_path / "modified.json"))
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    fake = FakeNetBox()

    class World:
        pass

    w = World()
    w.fake, w.cp, w.guard = fake, console_path, netbox_guard
    w.dev = fake.seed("dcim/devices", {"name": "edge-a", "status": "planned"})
    w.cs = fake.seed("dcim/devices", {"name": "cons-1", "status": "active"})
    w.auth = console_path.authority_for("edge-a", "p@example.invalid", "ab" * 32)
    return w


def _ensure(w, **over):
    args = dict(port_name="con 0", server_name="cons-1", server_port_name="port 5",
                actor="p@example.invalid", authority=w.auth, session=w.fake, base=BASE)
    args.update(over)
    return w.cp.ensure_console_path(LIST, w.dev["id"], **args)


def _wire(w, port_name="con 0", server_port="port 5", device=None):
    """A console path a PERSON made: untagged and unrecorded."""
    port = w.fake.seed("dcim/console-ports", {"device": (device or w.dev)["id"],
                                              "name": port_name})
    sport = w.fake.seed("dcim/console-server-ports", {"device": w.cs["id"], "name": server_port})
    cable = w.fake.seed("dcim/cables", {
        "a_terminations": [{"object_type": "dcim.consoleport", "object_id": port["id"]}],
        "b_terminations": [{"object_type": "dcim.consoleserverport", "object_id": sport["id"]}],
        "status": "connected", "label": ""})
    return port, sport, cable


# ── the fake, measured against NetBox 4.6.9's answers ───────────────────────────────────────

class TestTheFakeIsMeasured:
    def test_a_cable_is_the_captured_cable_key_for_key(self, nb):
        real = _capture()["endpoints"]["dcim/cables/"]["get_body"]["results"][0]
        a = nb.fake.seed("dcim/interfaces", {"device": nb.dev["id"], "name": "Gi0/3"})
        b = nb.fake.seed("dcim/interfaces", {"device": nb.cs["id"], "name": "Gi0/3"})
        nb.fake.seed("dcim/cables", {
            "a_terminations": [{"object_type": "dcim.interface", "object_id": a["id"]}],
            "b_terminations": [{"object_type": "dcim.interface", "object_id": b["id"]}],
            "status": "connected"})
        mine = nb.fake.get(f"{BASE}/api/dcim/cables/", params={"limit": 1}).json()["results"][0]
        assert sorted(mine) == sorted(real)
        assert sorted(mine["status"]) == sorted(real["status"])
        for end in ("a_terminations", "b_terminations"):
            t, rt = mine[end][0], real[end][0]
            assert sorted(t) == sorted(rt)
            assert sorted(t["object"]) == sorted(rt["object"])
            assert sorted(t["object"]["cable"]) == sorted(rt["object"]["cable"])
            assert sorted(t["object"]["device"]) == sorted(rt["object"]["device"])

    @pytest.mark.parametrize("endpoint", ["dcim/console-ports", "dcim/console-server-ports"])
    def test_a_console_port_carries_the_fields_netbox_lists(self, nb, endpoint):
        fields = _capture()["endpoints"][endpoint + "/"]["post_fields"]
        _wire(nb)
        mine = nb.fake.get(f"{BASE}/api/{endpoint}/").json()["results"][0]
        assert sorted(mine) == sorted(fields)
        assert mine["cable"] and sorted(mine["cable"]) == sorted(
            _capture()["endpoints"]["dcim/cables/"]["get_body"]["results"][0]
            ["a_terminations"][0]["object"]["cable"])

    def test_paging_answers_as_the_captured_next_link(self, nb):
        real = _capture()["endpoints"]["dcim/cables/"]["get_body"]
        _wire(nb)
        _wire(nb, port_name="con 1", server_port="port 6")
        first = nb.fake.get(f"{BASE}/api/dcim/cables/", params={"limit": 1}).json()
        assert first["count"] == 2 and len(first["results"]) == 1
        assert first["next"].split("?")[1] == real["next"].split("?")[1]
        second = nb.fake.get(first["next"]).json()
        assert second["next"] is None and len(second["results"]) == 1
        assert second["results"][0]["id"] != first["results"][0]["id"]


# ── the read ────────────────────────────────────────────────────────────────────────────────

class TestTheRead:
    def test_a_path_is_read_with_each_part_named(self, nb):
        port, sport, cable = _wire(nb)
        got = nb.cp.read_console_path(nb.dev["id"], session=nb.fake, base=BASE)
        assert got["ok"] and got["state"] == "path", got
        assert got["paths"] == [{"console_port": {"id": port["id"], "name": "con 0"},
                                 "cable": {"id": cable["id"], "label": "",
                                           "status": "connected"},
                                 "server_port": {"id": sport["id"], "name": "port 5"},
                                 "server": {"id": nb.cs["id"], "name": "cons-1"}}]

    def test_no_console_port_names_the_query_that_came_back_empty(self, nb):
        got = nb.cp.read_console_path(nb.dev["id"], session=nb.fake, base=BASE)
        assert got["ok"] and got["state"] == "no_path"
        assert f"dcim/console-ports/?device_id={nb.dev['id']} returned nothing" in got["why"]

    def test_a_port_with_no_cable_is_named(self, nb):
        nb.fake.seed("dcim/console-ports", {"device": nb.dev["id"], "name": "con 0"})
        got = nb.cp.read_console_path(nb.dev["id"], session=nb.fake, base=BASE)
        assert got["state"] == "no_path" and "'con 0'" in got["why"] and "no cable" in got["why"]

    def test_a_far_end_that_is_not_a_console_server_port_is_named(self, nb):
        port = nb.fake.seed("dcim/console-ports", {"device": nb.dev["id"], "name": "con 0"})
        iface = nb.fake.seed("dcim/interfaces", {"device": nb.cs["id"], "name": "Gi1"})
        nb.fake.seed("dcim/cables", {
            "a_terminations": [{"object_type": "dcim.consoleport", "object_id": port["id"]}],
            "b_terminations": [{"object_type": "dcim.interface", "object_id": iface["id"]}]})
        got = nb.cp.read_console_path(nb.dev["id"], session=nb.fake, base=BASE)
        assert got["state"] == "no_path" and "dcim.interface" in got["why"]

    def test_it_pages_through_every_port(self, nb, monkeypatch):
        monkeypatch.setattr(nb.cp, "PAGE_SIZE", 1)
        nb.fake.seed("dcim/console-ports", {"device": nb.dev["id"], "name": "aux 0"})
        nb.fake.seed("dcim/console-ports", {"device": nb.dev["id"], "name": "aux 1"})
        port, _sport, _cable = _wire(nb)          # the third port, on the last page
        asked = []
        real_get = nb.fake.get

        def counting(url, params=None, timeout=None):
            if "console-ports" in url:
                asked.append(url)
            return real_get(url, params=params, timeout=timeout)

        monkeypatch.setattr(nb.fake, "get", counting)
        got = nb.cp.read_console_path(nb.dev["id"], session=nb.fake, base=BASE)
        assert len(asked) == 3, asked
        assert got["state"] == "path" and got["paths"][0]["console_port"]["id"] == port["id"]
        assert len(got["gaps"]) == 2

    def test_an_answer_short_of_its_count_is_unreadable(self, nb, monkeypatch):
        _wire(nb)
        real_get = nb.fake.get

        def short(url, params=None, timeout=None):
            r = real_get(url, params=params, timeout=timeout)
            if "console-ports" in url and r.ok:
                r._payload["count"] = 7
            return r

        monkeypatch.setattr(nb.fake, "get", short)
        got = nb.cp.read_console_path(nb.dev["id"], session=nb.fake, base=BASE)
        assert not got["ok"] and got["state"] == "unreadable"
        assert "returned 1 of the 7" in got["error"]

    def test_a_full_page_with_no_count_is_truncated(self, nb, monkeypatch):
        monkeypatch.setattr(nb.cp, "PAGE_SIZE", 1)
        _wire(nb)
        real_get = nb.fake.get

        def countless(url, params=None, timeout=None):
            r = real_get(url, params=params, timeout=timeout)
            if "console-ports" in url and r.ok:
                r._payload.pop("count")
            return r

        monkeypatch.setattr(nb.fake, "get", countless)
        got = nb.cp.read_console_path(nb.dev["id"], session=nb.fake, base=BASE)
        assert got["state"] == "unreadable" and "truncated" in got["error"]

    def test_a_refused_query_is_unreadable_never_no_path(self, nb):
        got = nb.cp.read_console_path(9999, session=nb.fake, base=BASE)
        assert not got["ok"] and got["state"] == "unreadable"
        assert "device_id=9999 answered HTTP 400" in got["error"]

    def test_a_cable_that_is_gone_is_named(self, nb):
        _port, _sport, cable = _wire(nb)
        nb.fake.store["dcim/cables"].clear()
        nb.fake.store["dcim/console-ports"][0]["cable"] = {"id": cable["id"]}
        nb.fake._console_port = lambda endpoint, port: dict(port)   # its stale brief, as held
        got = nb.cp.read_console_path(nb.dev["id"], session=nb.fake, base=BASE)
        assert got["state"] == "no_path" and f"dcim/cables/{cable['id']}/ answered 404" in \
            got["why"]

    @pytest.mark.parametrize("bad", [0, -3, True, "5", None])
    def test_a_device_id_that_is_not_one_is_refused(self, nb, bad):
        got = nb.cp.read_console_path(bad, session=nb.fake, base=BASE)
        assert got["state"] == "unreadable" and "positive number" in got["error"]

    def test_netbox_not_configured_is_said(self, monkeypatch):
        import modules.netbox_client as nbc
        from modules.nsot import console_path

        monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "", "token": ""})
        got = console_path.read_console_path(4)
        assert got["state"] == "unreadable" and "not configured" in got["error"]


# ── the create ──────────────────────────────────────────────────────────────────────────────

class TestTheCreate:
    def test_the_switch_off_refuses_naming_both_and_writes_nothing(self, nb, monkeypatch):
        monkeypatch.setattr(nb.guard, "writes_allowed", lambda: False)
        got = _ensure(nb)
        assert got["refused"] and not got["ok"]
        assert "OFF (the master switch" in got["error"] and repr(nb.auth) in got["error"]
        assert nb.fake.posts == []

    def test_no_authority_refuses_naming_both(self, nb):
        got = _ensure(nb, authority="")
        assert got["refused"] and "writes are on" in got["error"]
        assert "authority declared is none" in got["error"]
        assert nb.fake.posts == []

    def test_another_operations_authority_is_refused(self, nb):
        got = _ensure(nb, authority="Verify by p@example.invalid")
        assert got["refused"] and "'Verify by p@example.invalid', not this operation's" in \
            got["error"]
        assert nb.fake.posts == []

    def test_no_network_is_refused(self, nb):
        got = nb.cp.ensure_console_path("", nb.dev["id"], port_name="con 0",
                                        server_name="cons-1", server_port_name="port 5",
                                        actor="p", authority=nb.auth, session=nb.fake, base=BASE)
        assert got["refused"] and "no network was named" in got["error"]

    def test_it_creates_tags_and_records_each_object(self, nb):
        got = _ensure(nb)
        assert got["ok"], got
        made = {c["endpoint"]: c for c in got["created"]}
        assert sorted(made) == ["dcim/cables", "dcim/console-ports", "dcim/console-server-ports"]
        for endpoint, c in made.items():
            obj = next(o for o in nb.fake.objects(endpoint) if o["id"] == c["id"])
            assert nb.guard.has_managed_tag(obj), endpoint
            rows = nb.guard.get_created(LIST, endpoint)[endpoint]
            assert [r["id"] for r in rows] == [c["id"]]
            assert rows[0]["authority"] == nb.auth and rows[0]["actor"] == "p@example.invalid"
        assert got["path"]["state"] == "path"
        assert got["path"]["paths"][0]["server"]["name"] == "cons-1"
        cable = nb.fake.objects("dcim/cables")[0]
        assert cable["label"] == "edge-a con 0 to cons-1 port 5"

    def test_a_second_call_creates_nothing(self, nb):
        first = _ensure(nb)
        posts = len(nb.fake.posts)
        again = _ensure(nb)
        assert again["ok"] and again["created"] == [] and len(nb.fake.posts) == posts
        assert {e["endpoint"] for e in again["existing"]} == {
            "dcim/console-ports", "dcim/console-server-ports", "dcim/cables"}
        assert again["cable"]["id"] == first["cable"]["id"]

    def test_a_persons_server_port_is_used_and_never_claimed(self, nb):
        sport = nb.fake.seed("dcim/console-server-ports", {"device": nb.cs["id"],
                                                           "name": "port 5"})
        got = _ensure(nb)
        assert got["ok"] and got["server_port"]["id"] == sport["id"]
        assert "dcim/console-server-ports" not in nb.guard.get_created(LIST)
        assert not nb.guard.has_managed_tag(sport)

    def test_a_port_cabled_elsewhere_is_refused_and_nothing_is_made(self, nb):
        _wire(nb, server_port="port 9")
        got = _ensure(nb)
        assert not got["ok"] and "never re-cables" in got["error"]
        assert "console port 'con 0' is on cable" in got["error"]
        assert nb.fake.posts == []

    def test_a_server_port_cabled_elsewhere_is_refused(self, nb):
        other = nb.fake.seed("dcim/devices", {"name": "edge-b", "status": "active"})
        _wire(nb, device=other)
        got = _ensure(nb)
        assert not got["ok"] and "cons-1 port 'port 5' is on cable" in got["error"]
        assert nb.fake.posts == []

    def test_a_console_server_that_does_not_exist_is_named_by_its_query(self, nb):
        got = _ensure(nb, server_name="cons-9")
        assert not got["ok"] and "dcim/devices/?name=cons-9 returned nothing" in got["error"]
        assert nb.fake.posts == []

    def test_two_console_servers_of_one_name_are_refused(self, nb):
        nb.fake.seed("dcim/devices", {"name": "cons-1", "status": "active"})
        got = _ensure(nb)
        assert not got["ok"] and "returned 2 devices" in got["error"]

    def test_the_device_as_its_own_console_server_is_refused(self, nb):
        got = _ensure(nb, server_name="edge-a")
        assert not got["ok"] and "is the device itself" in got["error"]

    def test_a_device_that_is_gone_is_named(self, nb):
        nb.fake.store["dcim/devices"].remove(nb.dev)
        nb.fake.seed("dcim/devices", {"name": "spare", "status": "active"})
        got = nb.cp.ensure_console_path(LIST, nb.dev["id"], port_name="con 0",
                                        server_name="cons-1", server_port_name="port 5",
                                        actor="p", authority=nb.auth, session=nb.fake,
                                        base=BASE)
        assert not got["ok"] and f"dcim/devices/{nb.dev['id']}/ answered 404" in got["error"]

    @pytest.mark.parametrize("field,value", [("port_name", ""), ("server_port_name", " p"),
                                             ("server_name", "x" * 65),
                                             ("port_name", "con\n0")])
    def test_a_name_netbox_would_not_hold_is_refused(self, nb, field, value):
        got = _ensure(nb, **{field: value})
        assert not got["ok"] and "Not written" in got["error"] and nb.fake.posts == []

    def test_a_write_that_fails_says_what_landed_before_it(self, nb, monkeypatch):
        real_post = nb.fake.post

        def refuse_cables(url, json=None, timeout=None):
            if "dcim/cables" in url:
                from tests.fake_netbox import FakeResponse
                return FakeResponse({"detail": "no"}, 403)
            return real_post(url, json=json, timeout=timeout)

        monkeypatch.setattr(nb.fake, "post", refuse_cables)
        got = _ensure(nb)
        assert not got["ok"] and "POST dcim/cables/ failed (403)" in got["error"]
        assert "dcim/console-ports" in got["error"].split("created before it:")[1]
        assert len(got["created"]) == 2

    def test_a_path_that_does_not_read_back_is_not_ok(self, nb, monkeypatch):
        monkeypatch.setattr(nb.cp, "read_console_path",
                            lambda *a, **k: {"paths": [], "why": "nothing there"})
        got = _ensure(nb)
        assert not got["ok"] and "did not read back: nothing there" in got["error"]

    def test_another_writer_of_the_network_refuses(self, nb, monkeypatch):
        class Busy:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                raise nb.guard.NetBoxBusy(LIST, {"operation": "import", "actor": "q"})

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(nb.guard, "list_writer", Busy)
        got = _ensure(nb)
        assert got["refused"] and "import by q" in got["error"] and nb.fake.posts == []


class TestThePreview:
    def test_the_preview_plans_the_three_objects_and_writes_nothing(self, nb):
        got = nb.cp.plan_console_path(LIST, nb.dev["id"], port_name="con 0",
                                      server_name="cons-1", server_port_name="port 5",
                                      session=nb.fake, base=BASE)
        assert got["ok"] and nb.fake.posts == []
        assert got["plan"]["creates_by_type"] == {"dcim/console-ports": 1,
                                                  "dcim/console-server-ports": 1,
                                                  "dcim/cables": 1}
        again = nb.cp.plan_console_path(LIST, nb.dev["id"], port_name="con 0",
                                        server_name="cons-1", server_port_name="port 5",
                                        session=nb.fake, base=BASE)
        assert again["hash"] == got["hash"] and not got["changes_nothing"]

    def test_after_the_create_the_preview_changes_nothing(self, nb):
        _ensure(nb)
        got = nb.cp.plan_console_path(LIST, nb.dev["id"], port_name="con 0",
                                      server_name="cons-1", server_port_name="port 5",
                                      session=nb.fake, base=BASE)
        assert got["ok"] and got["changes_nothing"] and got["plan"]["create_count"] == 0


# ── the removal ─────────────────────────────────────────────────────────────────────────────

class TestTheRemoval:
    def _remove(self, w, **over):
        args = dict(port_name="con 0", actor="p@example.invalid", authority=w.auth,
                    session=w.fake, base=BASE)
        args.update(over)
        return w.cp.remove_console_path(LIST, w.dev["id"], **args)

    def test_it_deletes_its_own_cable_and_port_and_keeps_the_server_port(self, nb):
        made = _ensure(nb)
        got = self._remove(nb)
        assert got["ok"], got
        assert [d["endpoint"] for d in got["deleted"]] == ["dcim/cables", "dcim/console-ports"]
        assert nb.fake.objects("dcim/cables") == [] and nb.fake.objects("dcim/console-ports") == []
        assert [p["id"] for p in nb.fake.objects("dcim/console-server-ports")] == \
            [made["server_port"]["id"]]
        held = nb.guard.get_created(LIST)
        assert not held.get("dcim/cables") and not held.get("dcim/console-ports")
        assert held["dcim/console-server-ports"][0]["id"] == made["server_port"]["id"]

    def test_a_persons_path_is_named_and_kept(self, nb):
        _wire(nb)
        got = self._remove(nb)
        assert not got["ok"] and got["deleted"] == [] and nb.fake.deletes == []
        assert "not tagged nmas-managed and not recorded" in got["error"]

    def test_tagged_but_unrecorded_is_kept(self, nb):
        _ensure(nb)
        nb.guard.forget_created(LIST)
        got = self._remove(nb)
        assert got["deleted"] == [] and "is tagged nmas-managed and not recorded" in got["error"]

    def test_the_switch_off_refuses_the_removal(self, nb, monkeypatch):
        _ensure(nb)
        monkeypatch.setattr(nb.guard, "writes_allowed", lambda: False)
        got = self._remove(nb)
        assert got["refused"] and got["error"].startswith("Not removed") and \
            nb.fake.deletes == []

    def test_nothing_to_remove_is_said_as_nothing(self, nb):
        got = self._remove(nb)
        assert got["ok"] and got["deleted"] == [] and got["skipped"] == []


def test_the_authority_names_the_operation_and_passes_the_gate(nb):
    assert nb.auth.startswith(nb.cp.AUTHORITY + " for edge-a, confirmed by p@example.invalid")
    assert "(plan abababababab)" in nb.auth
    assert nb.cp.refusal(LIST, nb.auth) == ""
    assert nb.cp.authority_for("edge-a", "") == "console path for edge-a, confirmed by unknown"
