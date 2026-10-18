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


#: C1248: the (endpoint, filter) pairs the lab's NetBox answered 400 for a value naming no object
#: (or no choice), measured 2026-10-18 ~00:5x UTC, status only. Typed here from that measurement,
#: never read from the fake: each is the expectation the fake is compared with.
MEASURED_400 = [
    ("dcim/devices", "site"), ("dcim/devices", "role"), ("dcim/devices", "tag"),
    ("dcim/devices", "platform"), ("dcim/devices", "manufacturer"),
    ("dcim/devices", "region"), ("dcim/devices", "site_group"),
    ("dcim/devices", "location"), ("dcim/devices", "tenant"),
    ("dcim/devices", "device_type"), ("dcim/devices", "status"),
    ("dcim/interfaces", "device"), ("dcim/interfaces", "tag"),
    ("ipam/ip-addresses", "vrf"), ("ipam/ip-addresses", "tag"), ("ipam/ip-addresses", "role"),
    ("ipam/prefixes", "site"), ("ipam/prefixes", "vrf"), ("ipam/prefixes", "tag"),
    ("ipam/prefixes", "role"),
    ("ipam/vlans", "site"), ("ipam/vlans", "tag"), ("ipam/vlans", "role"),
    ("dcim/sites", "region"), ("dcim/sites", "tag"),
    ("dcim/device-types", "manufacturer"), ("dcim/platforms", "manufacturer"),
    ("vpn/tunnels", "tag"),
]

#: The same measurement's 200 pairs: a plain field, or a method filter, answers an unknown value
#: with an empty 200 (count 0). The unknown value sent, where a pair needs one of its own shape.
MEASURED_200 = [
    ("dcim/devices", "name"), ("dcim/devices", "serial"), ("dcim/interfaces", "name"),
    ("ipam/ip-addresses", "device"), ("ipam/ip-addresses", "address"),
    ("dcim/sites", "slug"), ("dcim/sites", "name"),
    ("dcim/device-roles", "slug"), ("dcim/device-roles", "name"),
    ("dcim/device-types", "slug"), ("dcim/manufacturers", "slug"), ("dcim/platforms", "slug"),
    ("dcim/regions", "slug"), ("extras/tags", "slug"), ("extras/tags", "name"),
    ("ipam/roles", "slug"), ("ipam/vrfs", "name"), ("ipam/vrfs", "rd"),
    ("vpn/tunnels", "name"), ("extras/custom-fields", "name"),
    ("extras/config-templates", "name"),
]
UNKNOWN_VALUE = {("ipam/ip-addresses", "address"): "192.0.2.254/24",
                 ("ipam/vrfs", "rd"): "65000:999"}

#: The value that names a real object (or choice) for each 400 pair, in the field NetBox's filter
#: matches: a slug for most; a device's NAME on interfaces; a VRF's route distinguisher for `vrf`
#: (NetBox's filter is labelled "VRF (RD)": ``field_name='vrf__rd'``, ``to_field_name='rd'``, read
#: from NetBox's ipam filtersets, not measured); a choice's value for `status` and an IP address's
#: `role`. On devices `role` is a Device Role's slug, on prefixes and VLANs an IPAM Role's.
REAL = {"site": "lab", "tag": "managed", "platform": "ios-xe", "manufacturer": "cisco",
        "region": "west", "site_group": "campus", "location": "rack-1", "tenant": "ops",
        "device_type": "c8000v", "status": "active", "device": "r1", "vrf": "65000:1"}
REAL_ROLE = {"dcim/devices": "router", "ipam/ip-addresses": "loopback",
             "ipam/prefixes": "core", "ipam/vlans": "core"}

#: What each endpoint's seeded object is called in an answer.
HELD = {"dcim/devices": "r1", "dcim/interfaces": "Gi1", "ipam/ip-addresses": "192.0.2.1/24",
        "ipam/prefixes": "192.0.2.0/24", "ipam/vlans": "v10", "dcim/sites": "Lab",
        "dcim/device-types": "C8000v", "dcim/platforms": "IOS-XE", "vpn/tunnels": "t1"}


def _real(endpoint, key):
    return REAL_ROLE[endpoint] if key == "role" else REAL[key]


class TestTheSharedFakeAnswersAnUnknownSlugAsNetBoxDoes:
    """C1248: NetBox answers 400 to an object filter whose value names no object of the filter's
    kind (by the field its filter matches), and to a choice filter naming no choice; the shared
    fake answered an empty 200, so a test of a list whose stored site was deleted read "no
    devices" where the product, against NetBox, reads unreadable. Every expectation is typed
    above from the measurement (2026-10-18), apart from the fake's table and the product."""

    URL = "http://nb.invalid/api/{}/"

    @staticmethod
    def _fake():
        """One object of each kind, and one object on each endpoint referring to all of them."""
        from tests.fake_netbox import FakeNetBox

        fake = FakeNetBox()
        seed = fake.seed

        def ref(obj):
            return {"id": obj["id"], "name": obj.get("name", ""), "slug": obj.get("slug", "")}

        region = seed("dcim/regions", {"name": "West", "slug": "west"})
        group = seed("dcim/site-groups", {"name": "Campus", "slug": "campus"})
        tag = seed("extras/tags", {"name": "managed", "slug": "managed"})
        tags = [{"id": tag["id"], "name": "managed", "slug": "managed"}]
        site = seed("dcim/sites", {"name": "Lab", "slug": "lab", "region": ref(region),
                                   "group": ref(group), "tags": tags})
        location = seed("dcim/locations", {"name": "Rack 1", "slug": "rack-1",
                                           "site": ref(site)})
        tenant = seed("tenancy/tenants", {"name": "Ops", "slug": "ops"})
        maker = seed("dcim/manufacturers", {"name": "Cisco", "slug": "cisco"})
        dtype = seed("dcim/device-types", {"model": "C8000v", "name": "C8000v",
                                           "slug": "c8000v", "manufacturer": ref(maker)})
        platform = seed("dcim/platforms", {"name": "IOS-XE", "slug": "ios-xe",
                                           "manufacturer": ref(maker)})
        drole = seed("dcim/device-roles", {"name": "Router", "slug": "router"})
        irole = seed("ipam/roles", {"name": "Core", "slug": "core"})
        vrf = seed("ipam/vrfs", {"name": "blue", "rd": "65000:1"})
        dev = seed("dcim/devices", {
            "name": "r1", "site": ref(site), "role": ref(drole), "platform": ref(platform),
            "device_type": ref(dtype), "location": ref(location), "tenant": ref(tenant),
            "status": {"value": "active", "label": "Active"}, "tags": tags})
        iface = seed("dcim/interfaces", {"name": "Gi1", "device": ref(dev), "tags": tags})
        seed("ipam/ip-addresses", {"address": "192.0.2.1/24", "vrf": {"id": vrf["id"]},
                                   "role": {"value": "loopback", "label": "Loopback"},
                                   "assigned_object_type": "dcim.interface",
                                   "assigned_object_id": iface["id"],
                                   "assigned_object": {"id": iface["id"],
                                                       "device": {"id": dev["id"]}},
                                   "tags": tags})
        seed("ipam/prefixes", {"prefix": "192.0.2.0/24", "scope_type": "dcim.site",
                               "scope_id": site["id"], "vrf": {"id": vrf["id"]},
                               "role": ref(irole), "tags": tags})
        seed("ipam/vlans", {"vid": 10, "name": "v10", "site": ref(site), "role": ref(irole),
                            "tags": tags})
        seed("vpn/tunnels", {"name": "t1", "tags": tags})
        return fake

    @staticmethod
    def _names(got):
        return [o.get("name") or o.get("address") or o.get("prefix")
                for o in got.json()["results"]]

    @pytest.mark.parametrize("shape", ["str", "list"])
    @pytest.mark.parametrize("endpoint,key", MEASURED_400)
    def test_a_value_naming_nothing_is_a_400(self, endpoint, key, shape):
        """The planted case per measured pair, as a string and as a list member beside a real
        value (NetBox refuses the request when any member names nothing)."""
        fake = self._fake()
        value = {"str": "no-such-c1248", "list": [_real(endpoint, key), "no-such-c1248"]}[shape]
        got = fake.get(self.URL.format(endpoint), params={key: value})
        assert got.status_code == 400, (endpoint, key, value, got.json())
        assert key in got.json(), got.json()

    @pytest.mark.parametrize("endpoint,key,other", [
        ("dcim/devices", "role", "core"),           # an IPAM Role's slug, no Device Role's
        ("ipam/prefixes", "role", "router"),        # a Device Role's slug, no IPAM Role's
        ("ipam/vlans", "role", "router"),
        ("ipam/ip-addresses", "role", "core"),      # a Role's slug, not an address role choice
        ("ipam/ip-addresses", "vrf", "blue"),       # the VRF's NAME: the filter matches its RD
        ("ipam/prefixes", "vrf", "blue"),
        ("dcim/interfaces", "device", "lab"),       # a site's slug, no device's name
        ("dcim/devices", "site", "rack-1"),         # a location's slug, no site's
        ("dcim/devices", "status", "Active"),       # the label, not the choice's value
    ])
    def test_a_value_another_kind_holds_is_a_400(self, endpoint, key, other):
        """The kind and the field are the filter's: a value held by some OTHER kind's object,
        or by another field, names nothing here."""
        fake = self._fake()
        got = fake.get(self.URL.format(endpoint), params={key: other})
        assert got.status_code == 400, (endpoint, key, other, got.json())

    @pytest.mark.parametrize("endpoint,key", MEASURED_200)
    def test_a_plain_field_naming_nothing_is_an_empty_200(self, endpoint, key):
        fake = self._fake()
        value = UNKNOWN_VALUE.get((endpoint, key), "no-such-c1248")
        got = fake.get(self.URL.format(endpoint), params={key: value})
        assert got.status_code == 200, (endpoint, key, got.json())
        assert got.json()["results"] == [] and got.json()["count"] == 0

    @pytest.mark.parametrize("endpoint,key", MEASURED_400)
    def test_a_real_value_of_each_kind_answers_its_object(self, endpoint, key):
        """The control: the real value of each kind answers 200 with the object referring to
        it, as a string and as a one-member list."""
        fake = self._fake()
        for value in (_real(endpoint, key), [_real(endpoint, key)]):
            got = fake.get(self.URL.format(endpoint), params={key: value})
            assert got.status_code == 200, (endpoint, key, value, got.json())
            assert self._names(got) == [HELD[endpoint]], (endpoint, key, value, got.json())

    def test_a_deleted_site_turns_its_slug_into_a_400(self):
        """The row's case: a slug that named a site answers 400 once the site is gone."""
        fake = self._fake()
        url = self.URL.format("dcim/devices")
        assert fake.get(url, params={"site": "lab"}).status_code == 200
        site = fake.objects("dcim/sites")[0]
        assert fake.delete(f"{self.URL.format('dcim/sites')}{site['id']}/").status_code == 204
        assert fake.get(url, params={"site": "lab"}).status_code == 400
