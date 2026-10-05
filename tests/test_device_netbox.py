"""The device page's NetBox tab (NSOT_GUI_BRIEF 3.3; step 4), from
`modules/device_netbox`.

On NetBox's REAL records of r3 and r6, captured read-only from the host on
2026-10-01 and trimmed to the fields the tab reads
(`tests/fixtures/netbox/device_records.json`, the host's address replaced by a
documentation name). Who owns the record comes from NMAS's REAL provenance
writers (`record_created`, `record_adopted`, `record_modified`) in the test
store. The platform NetBox holds (`ios`, register A4) is said beside the
inventory's. Read-only: nothing here writes to NetBox or opens a device
session.
"""

import copy
import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "netbox", "device_records.json")
BASE = "http://netbox.example.test:8000"
LIST = "Lab"


class Resp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeNetBox:
    def __init__(self):
        self.cap = json.load(open(CAPTURE, encoding="utf-8"))
        self.asked, self.extra, self.fail = [], [], None

    def get(self, url, params=None, timeout=None):
        self.asked.append((url, dict(params or {})))
        if self.fail:
            raise self.fail
        path = url[len(BASE) + len("/api/"):].rstrip("/")
        if path == "dcim/devices":
            hits = [copy.deepcopy(c["device"]) for c in self.cap.values()
                    if isinstance(c, dict) and c.get("device") and c["device"]["name"] == params["name"]]
            hits += [copy.deepcopy(d) for d in self.extra if d["name"] == params["name"]]
            return Resp({"count": len(hits), "results": hits})
        for c in self.cap.values():
            if isinstance(c, dict) and c.get("device") and c["device"]["id"] == params.get("device_id"):
                return Resp({"count": c["counts"][path], "results": []})
        return Resp({"count": 0, "results": []})


@pytest.fixture(autouse=True)
def records(tmp_path, monkeypatch):
    """Each test's own provenance records, so none inherits another's."""
    from modules import netbox_guard
    for name in ("_CREATED_IDS_FILE", "_MODIFIED_FILE", "_ADOPTED_FILE"):
        monkeypatch.setattr(netbox_guard, name, str(tmp_path / f"{name.strip('_').lower()}.json"))


@pytest.fixture
def nb(monkeypatch):
    fake = FakeNetBox()
    monkeypatch.setattr("modules.netbox_client._nb_ready", lambda: (True, "", fake, BASE))
    return fake


def _ref():
    from types import SimpleNamespace
    return SimpleNamespace(name=LIST)


def _view(host, platform="cisco_iosxe"):
    from modules import device_netbox
    return device_netbox.for_device(_ref(), {"hostname": host, "platform": platform})


class TestTheRecord:
    def test_r3_as_netbox_holds_it(self, nb):
        v = _view("r3")
        r = v["record"]
        assert (r["id"], r["status"], r["role"], r["platform"], r["site"]) == \
            (7, "Active", "Router", "IOS", "Default")
        assert r["primary_ip4"] == "10.255.1.13/32" and r["tags"] == ["BGP", "CDP", "OSPF"]
        assert v["counts"] == {"interfaces": 5, "addresses": 10}
        assert v["ui_url"] == f"{BASE}/dcim/devices/7/"
        # Exact name, and three reads.
        assert nb.asked[0][1] == {"name": "r3"} and len(nb.asked) == 3

    def test_netboxs_ios_beside_the_inventorys_iosxe_is_said(self, nb):
        """A4, drawn where people look: `ios` maps to no dialect."""
        note = _view("r3")["platform_note"]
        assert "NetBox holds the platform IOS (ios), which names no platform this tool knows" in note
        assert "the inventory says cisco_iosxe" in note and "register A4" in note

    def test_a_platform_that_agrees_says_nothing(self, nb):
        nb.cap["r3"]["device"]["platform"]["slug"] = "cisco-ios-xe"
        assert _view("r3")["platform_note"] == ""

    def test_ios_names_no_dialect_and_is_never_defaulted(self):
        from modules.nsot.platform import dialect_for_netbox_slug, platform_for_device
        assert dialect_for_netbox_slug("ios") == ""
        assert dialect_for_netbox_slug("cisco-ios-xe") == "cisco_iosxe"
        # platform_for_device still resolves through the same function.
        assert platform_for_device({"_platform": "cisco-ios-xe"}) == "cisco_iosxe"


class TestWhoOwnsIt:
    def test_a_record_nmas_did_not_create_is_a_persons(self, nb):
        v = _view("r3")
        assert v["provenance"]["state"] == "person" and "never deletes it" in v["provenance"]["words"]

    def test_tagged_and_recorded_is_nmass_own(self, nb):
        from modules import netbox_guard
        netbox_guard.record_created(LIST, "dcim/devices", 11, "r6")
        p = _view("r6")["provenance"]
        assert p["state"] == "created" and "Remove can delete it" in p["words"]

    def test_tagged_but_not_recorded_disagrees_and_is_never_called_nmass(self, nb):
        p = _view("r6")["provenance"]
        assert p["state"] == "disagrees" and "missing from Mercury's record" in p["words"]

    def test_adopted_is_said(self, nb):
        from modules import netbox_guard
        out = netbox_guard.record_adopted(LIST, "r3", [("dcim/devices", 7, "r3")],
                                          actor="operator@example.com", reason="handed over",
                                          authority="adopt")
        assert out["ok"]
        assert _view("r3")["provenance"]["state"] == "adopted"

    def test_an_unreadable_record_is_unknown_never_a_persons(self, nb):
        from modules import netbox_guard
        os.makedirs(os.path.dirname(netbox_guard._CREATED_IDS_FILE), exist_ok=True)
        with open(netbox_guard._CREATED_IDS_FILE, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        p = _view("r3")["provenance"]
        assert p["state"] == "unknown" and "could not be read" in p["words"]

    def test_nmass_recorded_writes_are_counted(self, nb):
        from modules import netbox_guard
        netbox_guard.record_modified(LIST, "dcim/devices", 7, {"comments": {"before": "a", "after": "b"}},
                                     name="r3", actor="operator@example.com")
        m = _view("r3")["mods"]
        assert m["count"] == 1 and m["last"]["actor"] == "operator@example.com"
        assert _view("r6")["mods"]["count"] == 0


class TestWhatCannotBeRead:
    def test_absent_is_said(self, nb):
        v = _view("r9")
        assert v["absent"] is True and v["record"] is None

    def test_two_records_of_one_name_draw_neither(self, nb):
        dup = copy.deepcopy(nb.cap["r3"]["device"])
        dup["id"] = 99
        nb.extra.append(dup)
        v = _view("r3")
        assert v["record"] is None and "NetBox holds 2 devices named r3 (ids 7, 99)" in v["errors"][0]

    def test_netbox_unreachable_is_an_error_never_absent(self, nb):
        nb.fail = ConnectionError("Could not connect")
        v = _view("r3")
        assert v["absent"] is False and "NetBox could not be asked for r3: Could not connect" in v["errors"][0]

    def test_not_configured_is_said(self, monkeypatch):
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (False, "NetBox URL and API token are not configured", None, ""))
        assert _view("r3")["configured"] is False


# ---------------------------------------------------------------------------
# The page, through the real route.
# ---------------------------------------------------------------------------

from tests.test_profile_apply import lab  # noqa: E402,F401 (the fixture)


@pytest.fixture
def page(lab, nb, monkeypatch):
    from modules import device_page
    from modules.nsot import listref
    monkeypatch.setattr(device_page, "find_device", lambda name, ref=None: (
        listref.resolve(LIST), {"hostname": name, "ip": "192.0.2.1", "platform": "cisco_iosxe"}))

    def no_session(*a, **k):
        raise AssertionError("the NetBox tab opened a session to a device")
    monkeypatch.setattr("modules.connection.open_ssh", no_session)

    def get(url):
        r = lab["client"].get(url)
        return r, r.get_data(as_text=True)
    return get


class TestThePage:
    def test_r3s_record_drawn_and_strict(self, page, nb):
        from modules import csp
        r, html = page("/v2/device/r3/netbox")
        assert r.status_code == 200 and r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert not re.search(r"\sstyle=|\son[a-z]+=", html)
        assert "<div><dt>Primary IPv4</dt><dd class=\"mono\">10.255.1.13/32</dd></div>" in html
        assert "A person&#39;s record" in html or "A person's record" in html
        assert "register A4" in html
        assert f'href="{BASE}/dcim/devices/7/"' in html
        assert all(u.startswith(BASE) for u, _p in nb.asked) and len(nb.asked) == 3

    def test_the_tab_is_built_and_redraws_on_netbox_writes(self, page):
        from modules import invalidation
        _r, html = page("/v2/device/r3?tab=netbox")
        assert 'hx-get="/v2/device/r3/netbox?list=Lab"' in html and 'id="netbox"' in html
        keys = re.findall(r"nmas:(\w+) from:body", re.search(r'id="netbox" hx-get="[^"]*"\s+hx-trigger="([^"]*)"', html).group(1))
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        assert keys == ["netbox"] and "netbox" in invalidation.VOCABULARY
        assert "NMAS.subscribe('netbox'" in src
