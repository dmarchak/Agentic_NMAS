"""C1179: a NetBox dry run never sends one of its own placeholder ids to NetBox.

A dry run plans the objects it would create and gives each a negative placeholder id
(`netbox_guard._DryRunPlan.synthetic_id`), so the next step can chain on ``result["id"]``. A
lookup filtered by such an id (``dcim/devices/?name=s6&site_id=-3`` for a network whose site
does not exist yet) was sent to the real NetBox, which answers 400 to a negative id (4.6.9,
measured in W4's step 29, 2026-10-17: Adopt's NetBox gate failed for a network with no site).
Nothing in NetBox can be filed under an object that does not exist, so such a query is answered
from the dry run's own plan and never sent; a query by real ids is sent as before.
"""

import pytest

from modules import netbox_client as nb
from modules import netbox_guard


class _Answer:
    def __init__(self, status: int, results: list):
        self.status_code = status
        self._results = results

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} Client Error: Bad Request")

    def json(self):
        return {"results": self._results, "next": None}


class _NetBox:
    """NetBox 4.6.9 as measured: a negative id in a filter is a 400; otherwise it answers with
    what it holds (here: one device in site 7)."""

    def __init__(self):
        self.asked = []

    def get(self, url, params=None, timeout=None):
        self.asked.append((url, dict(params or {})))
        if any(isinstance(v, int) and v < 0 for v in (params or {}).values()):
            return _Answer(400, [])
        held = [{"id": 11, "name": "r1", "site": {"id": 7}}]
        hits = [d for d in held if (params or {}).get("site_id") in (None, 7)
                and (params or {}).get("name") in (None, d["name"])]
        return _Answer(200, hits)


BASE = "http://netbox.invalid"


@pytest.mark.parametrize("lookup", ["first", "get"])
def test_a_lookup_by_a_planned_object_is_answered_from_the_plan(lookup):
    s = _NetBox()
    with netbox_guard.dry_run() as plan:
        site = plan.synthetic_id()
        plan.add_virtual("dcim/devices/", {"id": plan.synthetic_id(), "name": "s6",
                                           "site_id": site})
        if lookup == "first":
            got = nb._nb_first(s, BASE, "dcim/devices/", name="s6", site_id=site)
            assert got and got["name"] == "s6"
            assert nb._nb_first(s, BASE, "dcim/devices/", name="s5", site_id=site) is None
        else:
            got = nb._nb_get(s, BASE, "dcim/devices/", site_id=site)
            assert [d["name"] for d in got] == ["s6"]
    assert not [p for _u, p in s.asked
                if any(isinstance(v, int) and v < 0 for v in p.values())], s.asked


@pytest.mark.parametrize("lookup", ["first", "get"])
def test_a_lookup_by_real_ids_still_asks_netbox(lookup):
    """The control: a real id is sent, in a dry run and out of one."""
    for ctx in (netbox_guard.dry_run, None):
        s = _NetBox()
        if ctx:
            with ctx():
                got = (nb._nb_first(s, BASE, "dcim/devices/", name="r1", site_id=7)
                       if lookup == "first" else nb._nb_get(s, BASE, "dcim/devices/", site_id=7))
        else:
            got = (nb._nb_first(s, BASE, "dcim/devices/", name="r1", site_id=7)
                   if lookup == "first" else nb._nb_get(s, BASE, "dcim/devices/", site_id=7))
        assert s.asked and s.asked[0][1].get("site_id") == 7
        assert (got["name"] if lookup == "first" else got[0]["name"]) == "r1"


def test_a_whole_import_preview_for_a_network_netbox_has_never_seen(monkeypatch):
    """The path W4's step 29 took: an import dry run (Adopt's NetBox gate runs one) for a
    network with no region, site or VRF in NetBox yet, against a NetBox that answers a negative
    id with 400 as 4.6.9 does. It completes, plans the network's objects and the device, and
    sends no placeholder id."""
    import modules.netbox_client as nbc
    from tests.fake_netbox import FakeNetBox

    class NetBox469(FakeNetBox):
        def __init__(self):
            super().__init__()
            self.asked = []

        def get(self, url, params=None, **k):
            self.asked.append(dict(params or {}))
            if any(isinstance(v, int) and v < 0 for v in (params or {}).values()):
                return _Answer(400, [])
            return super().get(url, params=params, **k)

    fake = NetBox469()
    monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                           "token": "t"})
    monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: fake)
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    out = nbc.sync_list_to_netbox(
        "probe-fresh", [{"hostname": "s6", "ip": "192.0.2.61", "platform": "cisco_iosxe",
                         "role": "router",
                         "preview_config": "hostname s6\ninterface GigabitEthernet2\n"
                                           " ip address 192.0.2.61 255.255.255.0\n!\nend\n"}],
        dry_run=True)
    assert out.get("ok") and not out.get("failed"), (out.get("error"), out.get("failed"))
    created = (out.get("plan") or {}).get("creates_by_type") or {}
    assert created.get("dcim/devices", 0) >= 1 and created.get("dcim/sites", 0) == 1, created
    assert not [p for p in fake.asked
                if any(isinstance(v, int) and v < 0 for v in p.values())], "a placeholder was sent"
    assert fake.posts == [] and fake.patches == [], "a dry run wrote to NetBox"


def test_outside_a_dry_run_a_negative_id_is_still_sent():
    """A negative id outside a dry run is no placeholder of Mercury's: NetBox says what it says."""
    s = _NetBox()
    with pytest.raises(Exception):
        nb._nb_first(s, BASE, "dcim/devices/", name="x", site_id=-3)
    assert s.asked and s.asked[0][1]["site_id"] == -3


class TestTheSharedFakeAnswersANegativeIdAsNetBoxDoes:
    """C1223: tests/fake_netbox.py, which 28 test files share, answered a negative id with an
    empty 200, so none of them would catch a new path that sends a placeholder (C1179's class).
    It answers 400 now, in every shape a request can carry one: an int, a numeric string, a list
    member, and a path segment (whose real answer was not measured; refused loudly, never read
    as "gone"). Only the two fakes above modelled it before."""

    URL = "http://nb.invalid/api/dcim/devices/"

    @pytest.mark.parametrize("value", [-3, "-3", [7, -3], ("-3",)])
    def test_a_negative_id_in_a_filter_is_a_400(self, value):
        from tests.fake_netbox import FakeNetBox

        fake = FakeNetBox()
        fake.seed("dcim/devices", {"name": "r1", "site": {"id": 7}})
        got = fake.get(self.URL, params={"name": "r1", "site_id": value})
        assert got.status_code == 400, (value, got.json())
        assert "site_id" in got.json()

    @pytest.mark.parametrize("verb", ["get", "patch", "delete"])
    def test_a_negative_id_in_the_path_is_a_400(self, verb):
        from tests.fake_netbox import FakeNetBox

        fake = FakeNetBox()
        kwargs = {"json": {"name": "x"}} if verb == "patch" else {}
        got = getattr(fake, verb)(self.URL + "-3/", **kwargs)
        assert got.status_code == 400, (verb, got.json())
        assert fake.patches == [] and fake.deletes == [], "a refused request changed nothing"

    def test_a_real_id_is_answered_as_before(self):
        """The control: a positive id, as an int or a string, in a filter or a path. The site
        is seeded, so the id names a real object (C1240: a filter naming none is a 400)."""
        from tests.fake_netbox import FakeNetBox

        fake = FakeNetBox()
        fake.seed("dcim/sites", {"id": 7, "name": "lab", "slug": "lab"})
        dev = fake.seed("dcim/devices", {"name": "r1", "site": {"id": 7}})
        for value in (7, "7"):
            got = fake.get(self.URL, params={"site_id": value})
            assert got.status_code == 200 and [d["name"] for d in got.json()["results"]] == ["r1"]
        assert fake.get(f"{self.URL}{dev['id']}/").json()["name"] == "r1"
        assert fake.get(f"{self.URL}999/").status_code == 404

    def _import(self, monkeypatch):
        import modules.netbox_client as nbc
        from tests.fake_netbox import FakeNetBox

        class Counting(FakeNetBox):
            """The shared fake, unchanged, counting the requests it answered 400."""

            def __init__(self):
                super().__init__()
                self.refused = []

            def get(self, url, params=None, **k):
                got = super().get(url, params=params, **k)
                if got.status_code == 400:
                    self.refused.append((url, dict(params or {})))
                return got

        fake = Counting()
        monkeypatch.setattr(nbc, "get_netbox_config", lambda: {"url": "http://127.0.0.1:9",
                                                               "token": "t"})
        monkeypatch.setattr(nbc, "_session_from_config", lambda cfg: fake)
        monkeypatch.setattr(nbc, "_managed_tag_ids", {})
        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
        out = nbc.sync_list_to_netbox(
            "probe-fresh", [{"hostname": "s6", "ip": "192.0.2.61", "platform": "cisco_iosxe",
                             "role": "router",
                             "preview_config": "hostname s6\ninterface GigabitEthernet2\n"
                                               " ip address 192.0.2.61 255.255.255.0\n!\nend\n"}],
            dry_run=True)
        return out, fake

    def test_the_whole_import_preview_on_the_shared_fake_sends_no_placeholder(self, monkeypatch):
        out, fake = self._import(monkeypatch)
        assert out.get("ok") and not out.get("failed"), (out.get("error"), out.get("failed"))
        assert (out.get("plan") or {}).get("creates_by_type", {}).get("dcim/sites") == 1, \
            "floor: the network's site is planned, so its placeholder id exists to be sent"
        assert fake.refused == [], fake.refused

    def test_the_shared_fake_catches_a_placeholder_sent(self, monkeypatch):
        """The planted case: with the plan-only answer turned off (C1179's defect put back), the
        same preview on the shared fake is answered 400 and does not pass as a clean preview."""
        monkeypatch.setattr(nb, "_planned_only", lambda params: False)
        out, fake = self._import(monkeypatch)
        assert fake.refused, "a placeholder reached the shared fake and it answered 200"
        assert any(isinstance(v, int) and v < 0 for _u, p in fake.refused for v in p.values())
        assert not out.get("ok") or out.get("failed"), "the preview read a 400 as success"


class TestTheSharedFakeAnswersAnUnknownIdAsNetBoxDoes:
    """C1240: NetBox answers 400 to an object filter naming an id no object holds (measured on
    the lab's NetBox 2026-10-17, status only: ``dcim/devices/?site_id=<an unused id>`` 400, a
    real ``site_id`` 200), and the shared fake answered an empty 200, so every test on it read
    "none found" where NetBox errors. Each expectation below is written from NetBox's filter
    names, by hand: nothing here is read from the fake's table or from the product."""

    URL = "http://nb.invalid/api/{}/"

    @staticmethod
    def _fake():
        from tests.fake_netbox import FakeNetBox

        fake = FakeNetBox()
        site = fake.seed("dcim/sites", {"name": "lab", "slug": "lab"})
        role = fake.seed("dcim/device-roles", {"name": "Router", "slug": "router"})
        dev = fake.seed("dcim/devices", {"name": "r1", "site": {"id": site["id"]},
                                         "role": {"id": role["id"]}})
        iface = fake.seed("dcim/interfaces", {"name": "Gi1", "device": {"id": dev["id"]}})
        vrf = fake.seed("ipam/vrfs", {"name": "blue"})
        fake.seed("ipam/ip-addresses", {"address": "192.0.2.1/24", "vrf": {"id": vrf["id"]},
                                        "assigned_object_type": "dcim.interface",
                                        "assigned_object_id": iface["id"],
                                        "assigned_object": {"id": iface["id"],
                                                            "device": {"id": dev["id"]}}})
        unused = 1 + max(o["id"] for objs in fake.store.values() for o in objs)
        return fake, {"site": site, "role": role, "device": dev, "interface": iface,
                      "vrf": vrf}, unused

    @pytest.mark.parametrize("shape", ["int", "str", "list"])
    def test_an_unknown_site_id_is_a_400(self, shape):
        """The measured case, in each shape a request can carry the id."""
        fake, real, unused = self._fake()
        value = {"int": unused, "str": str(unused), "list": [real["site"]["id"], unused]}[shape]
        got = fake.get(self.URL.format("dcim/devices"), params={"site_id": value})
        assert got.status_code == 400, (value, got.json())
        assert "site_id" in got.json()

    @pytest.mark.parametrize("endpoint,key,kind", [
        ("dcim/interfaces", "device_id", "device"),
        ("ipam/ip-addresses", "interface_id", "interface"),
        ("ipam/ip-addresses", "vrf_id", "vrf"),
        ("dcim/devices", "role_id", "role"),
    ])
    def test_an_id_of_another_kind_is_a_400(self, endpoint, key, kind):
        """The kind is the filter's, not any object's: an id that some OTHER kind's object
        holds names nothing here. The site's id is held by a site and by no {kind}."""
        fake, real, _unused = self._fake()
        other = real["site"]["id"]
        assert other != real[kind]["id"], "floor: the planted id must not be this kind's"
        got = fake.get(self.URL.format(endpoint), params={key: other})
        assert got.status_code == 400, (endpoint, key, got.json())
        assert key in got.json()

    def test_a_real_id_of_each_kind_is_a_200(self):
        """The control: every planted filter answers 200 with the object when the id is real,
        as an int and a string, and is not refused as a list (the fake does not match a list's
        members, which no product path sends: only the refusal is this row's)."""
        fake, real, _unused = self._fake()
        cases = [("dcim/devices", "site_id", "site", "r1"),
                 ("dcim/devices", "role_id", "role", "r1"),
                 ("dcim/interfaces", "device_id", "device", "Gi1"),
                 ("ipam/ip-addresses", "interface_id", "interface", "192.0.2.1/24"),
                 ("ipam/ip-addresses", "vrf_id", "vrf", "192.0.2.1/24")]
        for endpoint, key, kind, want in cases:
            ident = real[kind]["id"]
            for value in (ident, str(ident)):
                got = fake.get(self.URL.format(endpoint), params={key: value})
                assert got.status_code == 200, (endpoint, key, value, got.json())
                held = [o.get("name") or o.get("address") for o in got.json()["results"]]
                assert held == [want], (endpoint, key, value, held)
            got = fake.get(self.URL.format(endpoint), params={key: [ident]})
            assert got.status_code == 200, (endpoint, key, [ident], got.json())

    @pytest.mark.parametrize("endpoint,key", [
        ("dcim/devices", "id"),
        ("dcim/cables", "termination_a_id"),
        ("ipam/ip-addresses", "assigned_object_id"),
    ])
    def test_a_filter_naming_no_one_kind_is_answered_as_before(self, endpoint, key):
        """`id` and the generic object filters name no single kind, so the fake keeps its empty
        200 for an unknown id there (`dcim/devices/?id=<unused>` measured on the lab's NetBox
        2026-10-18: 200, count 0; the generic ends not measured)."""
        fake, _real, unused = self._fake()
        got = fake.get(self.URL.format(endpoint), params={key: unused})
        assert got.status_code == 200 and got.json()["results"] == [], (key, got.json())

    @pytest.mark.parametrize("endpoint,status", [
        ("ipam/ip-addresses", 200),   # a method filter: an unknown device matches nothing
        ("dcim/interfaces", 400),     # a choice of devices: an unknown one is refused
    ])
    def test_device_id_is_answered_per_endpoint_as_measured(self, endpoint, status):
        """`device_id` with an unused id, measured on the lab's NetBox 2026-10-18, status only:
        on IP addresses 200 with nothing, on interfaces 400. The fake answers each the same."""
        fake, _real, unused = self._fake()
        got = fake.get(self.URL.format(endpoint), params={"device_id": unused})
        assert got.status_code == status, (endpoint, got.json())
        if status == 200:
            assert got.json()["results"] == []
