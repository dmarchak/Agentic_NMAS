"""Inventory entry (the SDN design, revision 4, section 9a; its test plan's T19, T20, T21 and
T22's kind cases; C2604 to C2608), against a NetBox list of every lab platform.

The records are r3's real capture (tests/fixtures/netbox/device_records.json), copied once per
device with the minimal edits each case needs: its id, name, platform slug, role slug, primary
address (192.0.2.x), and, for the observe-only cases, its rendered ``config_context`` and its
``local_context_data``. Nothing else is typed.

- T20 (C2604, C2605): a ``platform:<slug>`` profile covers exactly that platform's devices and
  no other, and wins over the kind and the site; a role profile matches by ``mercury_kind``,
  and one named for a NetBox role matches nothing; the page refuses a name no device can match,
  naming the scope and what exists.
- T21 (C2607): a device no login covers loads in its "no login" state naming the scopes, a
  session to it is refused naming that (IPv4 and IPv6), one Needs attention row per network
  counts them and clears when they resolve; no platform and no primary IPv4 stay named skips.
- T19 (C2606, change D's merge cases): the mark is read from the RENDERED context; observe by a
  local context, observe by an assigned (tag) context, manage under a role context's observe
  when the local says manage (NetBox's merge), and a local/rendered disagreement judged by the
  rendered one; an observe device is refused by every change path (the hold, the pipeline's
  gate, heal) naming the key and where NetBox set it, while its reads and captures are held.
- T22's kind cases (C2608): ``host`` is a kind NetBox's field accepts; a ``linux`` (the design's
  ``linux_host``) session reads its capture list and its shapes only; its one held write is
  declared and refused naming P6; a host is refused by goldens, deploys, heal and features
  (the hold and the gate) and left out of config drift and interface monitoring.
"""

import copy
import json
import os
import re
import threading
from html import unescape

import pytest

from modules import credentials
from modules.inventory import management as M
from modules.inventory import netbox_source

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = json.load(open(os.path.join(ROOT, "tests", "fixtures", "netbox",
                                      "device_records.json"), encoding="utf-8"))["r3"]["device"]

#: (name, NetBox platform slug, NetBox role slug, address): every platform the lab holds.
LAB = (("router", "cisco-ios", "edge-router", "192.0.2.11"),
       ("mgmt-sw", "cisco-ios", "mgmt-switch", "192.0.2.12"),
       ("of-sw1", "arista-eos", "openflow-switch", "192.0.2.13"),
       ("of-sw2", "arista-eos", "openflow-switch", "192.0.2.14"),
       ("of-sw3", "hp-procurve", "openflow-switch", "192.0.2.15"),
       ("ovs1", "ovs", "ovs-host", "192.0.2.16"),
       ("ovs2", "ovs", "ovs-host", "192.0.2.17"),
       ("controller", "linux", "controller", "192.0.2.18"))
#: NetBox's classification (`role_kind.read`'s shape): each role's mercury_kind.
KINDS = {"field": True, "kinds": {"edge-router": "router", "mgmt-switch": "switch",
                                  "openflow-switch": "switch", "ovs-host": "switch",
                                  "controller": "host"}}
PLATFORM_MAP = {"cisco-ios": {"netmiko_device_type": "cisco_ios"},
                "arista-eos": {"netmiko_device_type": "arista_eos"},
                "hp-procurve": {"netmiko_device_type": "hp_procurve"},
                "ovs": {"netmiko_device_type": "ovs_linux"},
                "linux": {"netmiko_device_type": "linux"}}


def record(name, platform, role, address, nb_id, *, context=None, local=None, site="lab"):
    """r3's capture, edited only where the case needs it."""
    r = copy.deepcopy(CAPTURE)
    r.update(id=nb_id, name=name, display=name)
    r["platform"] = dict(r["platform"], slug=platform, name=platform, display=platform)
    r["role"] = dict(r["role"], slug=role, name=role, display=role)
    r["primary_ip4"] = dict(r["primary_ip4"], address=f"{address}/24", display=f"{address}/24")
    r["site"] = dict(r["site"], slug=site, name=site, display=site)
    if context is not None:
        r["config_context"] = context
    if local is not None:
        r["local_context_data"] = local
    return r


def lab_records(**per_device):
    return [record(n, p, r, a, i, **per_device.get(n, {}))
            for i, (n, p, r, a) in enumerate(LAB, start=1)]


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "creds.json"))
    monkeypatch.setattr(netbox_source, "get_setting",
                        lambda key, default=None: PLATFORM_MAP if key == "platform_map" else "")
    return credentials


def adapt(records=None):
    devices, skipped, warnings = netbox_source.adapt_devices(
        lab_records() if records is None else records, kinds=KINDS)
    return {d["hostname"]: d for d in devices}, skipped, warnings


# ------------------------------------------------------------------ T20: credential profiles

class TestPlatformProfiles:
    def test_a_platform_profile_covers_exactly_that_platforms_devices(self, lab):
        lab.save_profile("platform:arista-eos", "eos-user", "eos-pw")
        devices, skipped, _w = adapt()
        assert skipped == [] and len(devices) == len(LAB)
        covered = {h for h, d in devices.items()
                   if d["_cred_source"] == "profile:platform:arista-eos"}
        assert covered == {"of-sw1", "of-sw2"}
        assert {h for h, d in devices.items() if d["_login"]} == set(devices) - covered

    def test_platform_wins_over_the_kind_and_the_site(self, lab):
        lab.save_profile("platform:ovs", "ovs-user", "ovs-pw")
        lab.save_profile("role:switch", "sw-user", "sw-pw")
        lab.save_profile("site:lab", "site-user", "site-pw")
        devices, _s, _w = adapt()
        got = {h: d["_cred_source"] for h, d in devices.items()}
        assert got["ovs1"] == got["ovs2"] == "profile:platform:ovs"
        assert {got[h] for h in ("mgmt-sw", "of-sw1", "of-sw2", "of-sw3")} \
            == {"profile:role:switch"}
        assert got["router"] == got["controller"] == "profile:site:lab"
        assert devices["ovs1"]["username"] == "ovs-user"

    def test_the_resolver_order_is_platform_then_kind_then_site(self, lab):
        lab.save_profile("platform:linux", "p", "p")
        lab.save_profile("role:host", "r", "r")
        assert credentials.resolve("192.0.2.18", role="host", site="lab",
                                   platform="linux")["source"] == "profile:platform:linux"
        assert credentials.resolve("2001:db8::18", role="host", site="lab",
                                   platform="other")["source"] == "profile:role:host"

    def test_a_role_profile_matches_by_mercury_kind_not_the_netbox_role(self, lab):
        lab.save_profile("role:openflow-switch", "by-role-slug", "pw")
        devices, _s, _w = adapt()
        assert all(d["_login"] for d in devices.values())    # the NetBox slug matched nothing
        lab.save_profile("role:switch", "by-kind", "pw")
        devices, _s, _w = adapt()
        assert {h for h, d in devices.items() if d["_cred_source"] == "profile:role:switch"} \
            == {"mgmt-sw", "of-sw1", "of-sw2", "of-sw3", "ovs1", "ovs2"}

    def test_scheduled_rotation_follows_the_same_order(self):
        from modules.nsot import scheduled_rotation as SR
        dev = {"role": "switch", "_platform": "ovs", "_site": "lab"}
        assert SR.governing_profile(dev, {"platform:ovs", "role:switch", "default"}) \
            == "platform:ovs"
        assert SR.governing_profile(dev, {"site:lab", "default"}) == "site:lab"


class TestThePageRefusesANameNoDeviceCanMatch:
    KNOWN = {"kinds": {"router": ["edge-router"], "switch": ["openflow-switch"],
                       "firewall": [], "host": ["controller"]},
             "platforms": ["arista-eos", "linux"], "sites": ["lab"]}

    def test_each_scope_that_can_match_is_named(self):
        from modules import credential_profiles_page as P
        for kind, value, name in (("platform", "arista-eos", "platform:arista-eos"),
                                  ("role:host", "", "role:host"), ("role", "switch", "role:switch"),
                                  ("site", "lab", "site:lab"), ("default", "", "default")):
            assert P.name_of(kind, value, self.KNOWN) == (name, ""), kind

    @pytest.mark.parametrize("kind,value,names", [
        ("role", "openflow-switch", ("role:openflow-switch", "router, switch, firewall, host")),
        ("platform", "junos", ("platform:junos", "arista-eos, linux")),
        ("site", "elsewhere", ("site:elsewhere", "lab"))])
    def test_a_name_no_device_can_match_is_refused_naming_the_scope_and_what_exists(
            self, kind, value, names):
        from modules import credential_profiles_page as P
        name, problem = P.name_of(kind, value, self.KNOWN)
        assert name == "" and all(n in problem for n in names), problem

    def test_the_form_offers_each_kind_naming_the_netbox_roles_it_covers(self):
        from modules import credential_profiles_page as P
        offered = dict(P.choices(self.KNOWN))
        assert set(offered) == {"platform", "role:router", "role:switch", "role:firewall",
                                "role:host", "site", "default"}
        assert "openflow-switch" in offered["role:switch"]
        assert "no loaded NetBox device has it yet" in offered["role:firewall"]

    def test_a_role_profile_stored_under_a_netbox_role_says_it_is_read_by_nothing(self):
        from modules import credential_profiles_page as P
        assert P.covers("role:openflow-switch")["read"] is False
        assert P.covers("role:switch")["read"] is True
        assert P.covers("platform:ovs")["words"] == "every device on the platform ovs"

    def test_what_exists_is_read_from_the_loaded_inventories(self, monkeypatch):
        from modules import credential_profiles_page as P
        from modules import inventory
        from modules.nsot import listref
        monkeypatch.setattr(listref, "_registry", lambda: {"lab9": "lab9"})
        rows = [{"hostname": "of-sw1", "role": "switch", "_role_slug": "openflow-switch",
                 "_site": "lab"},
                {"hostname": "controller", "role": "host", "_role_slug": "controller",
                 "_site": "lab"}]
        monkeypatch.setattr(inventory, "loaded_rows", lambda name: rows)
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: PLATFORM_MAP)
        got = P.exists()
        assert got["kinds"]["switch"] == ["openflow-switch"]
        assert got["kinds"]["host"] == ["controller"] and got["kinds"]["router"] == []
        assert got["sites"] == ["lab"] and "linux" in got["platforms"]


@pytest.fixture
def page(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.credentials._FILE", str(tmp_path / "credential_profiles.json"))
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    import app as A
    return {"client": A.app.test_client(), "dir": tmp_path}


def test_the_route_refuses_a_netbox_role_slug_and_writes_nothing(page):
    r = page["client"].post("/v2/credentials/profiles",
                            data={"kind": "role", "value": "openflow-switch",
                                  "username": "u", "password": "Prof-Pass-9917", "secret": ""})
    html = r.get_data(as_text=True)
    assert r.status_code == 400 and "no device can match role:openflow-switch" in html
    assert not (page["dir"] / "credential_profiles.json").exists()


def test_the_form_draws_the_kinds_as_choices_and_a_choice_saves_its_profile(page):
    """C2604: the scope is chosen from Mercury's kinds, never typed; pressing Add with a drawn
    choice saves a profile under exactly that scope (presence alone would not show it works:
    docs/TEST_INTEGRITY.md item 4)."""
    import json
    html = page["client"].get("/v2/credentials/profiles/form").get_data(as_text=True)
    for kind in ("router", "switch", "firewall", "host"):
        assert f'<option value="role:{kind}"' in html, kind
    assert '<option value="platform"' in html and "Platforms in the platform map" in html
    r = page["client"].post("/v2/credentials/profiles",
                            data={"kind": "role:switch", "value": "", "username": "u",
                                  "password": "Prof-Pass-9917", "secret": ""})
    assert r.status_code == 200
    with open(page["dir"] / "credential_profiles.json", encoding="utf-8") as fh:
        saved = json.load(fh)["profiles"]
    assert list(saved) == ["role:switch"] and saved["role:switch"]["username"] == "u"


# ------------------------------------------------------------------ C2984: the scope is chosen

@pytest.fixture
def loaded(page, monkeypatch):
    """The lab's NetBox inventory as loaded, two of its platforms and its site carrying
    NetBox's own names (the capture's records, their names edited), and its platform map."""
    from modules import inventory, settings_schema
    from modules.nsot import listref
    records = lab_records()
    for r in records:
        r["site"]["name"] = "Lab 9"
        if r["platform"]["slug"] == "arista-eos":
            r["platform"]["name"] = "Arista EOS"
    real = settings_schema.get_setting
    monkeypatch.setattr(netbox_source, "get_setting",
                        lambda key, default=None: PLATFORM_MAP if key == "platform_map" else "")
    rows, _skipped, _warnings = netbox_source.adapt_devices(records, kinds=KINDS)
    assert len(rows) == len(LAB), "floor: every lab device loaded"
    monkeypatch.setattr(settings_schema, "get_setting", lambda key, default=None: (
        PLATFORM_MAP if key == "platform_map" else real(key, default)))
    monkeypatch.setattr(listref, "_registry", lambda: {"lab9": "lab9"})
    monkeypatch.setattr(inventory, "loaded_rows", lambda name: rows)
    return page


class TestThePlatformOrSiteIsChosen:
    """C2984 (the operator, the Lab 9 sitting, 2026-11-10: "Make it a dropdown of the known
    platform slugs from the platform map (each with its platform name and device count), and
    of the networks' sites"; the charter's "What Mercury knows is chosen, never typed")."""

    def test_the_inventory_carries_netbox_s_names_and_they_reach_no_session(self, lab):
        from modules import inventory
        records = lab_records()
        records[2]["platform"]["name"] = "Arista EOS"
        records[2]["site"]["name"] = "Lab 9"
        devices, _s, _w = adapt(records)
        assert devices["of-sw1"]["_platform_name"] == "Arista EOS"
        assert devices["of-sw1"]["_site_name"] == "Lab 9"
        sent = inventory.strip_metadata(devices["of-sw1"])
        assert "_platform_name" not in sent and "_site_name" not in sent

    def test_the_form_offers_each_platform_and_site_by_name_slug_and_count(self, loaded):
        html = unescape(loaded["client"].get("/v2/credentials/profiles/form")
                        .get_data(as_text=True))
        assert 'name="value" type="text"' not in html, "no free text: the server takes none"
        field = re.search(r'<select id="cp-value" name="value">(.*?)</select>', html, re.S)
        options = [(v, " ".join(words.split())) for v, words in re.findall(
            r'<option value="([^"]*)"[^>]*>(.*?)</option>', field.group(1), re.S)]
        assert options == [
            ("", "none: it covers a kind, or every device"),
            ("arista-eos", "Arista EOS (arista-eos) · 2 loaded devices"),
            ("cisco-ios", "cisco-ios · 2 loaded devices"),
            ("hp-procurve", "hp-procurve · 1 loaded device"),
            ("linux", "linux · 1 loaded device"),
            ("ovs", "ovs · 2 loaded devices"),
            ("lab", "Lab 9 (lab) · 8 loaded devices")], options
        groups = re.findall(r'<optgroup label="([^"]+)">', field.group(1))
        assert groups == ["Platforms in the platform map", "Sites with a loaded NetBox device"]
        # Each drawn choice saves under exactly its scope (presence alone would not show
        # it): the site as a site profile, a platform as a platform profile.
        body = {"username": "u", "password": "Prof-Pass-9917", "secret": ""}
        for kind, value in (("site", options[-1][0]), ("platform", options[1][0])):
            r = loaded["client"].post("/v2/credentials/profiles",
                                      data=dict(body, kind=kind, value=value))
            assert r.status_code == 200, (kind, value)
        with open(loaded["dir"] / "credential_profiles.json", encoding="utf-8") as fh:
            assert sorted(json.load(fh)["profiles"]) == ["platform:arista-eos", "site:lab"]

    def test_a_drawn_choice_saves_its_profile_and_a_refusal_keeps_it_chosen(self, loaded):
        import json
        c = loaded["client"]
        body = {"username": "u", "password": "Prof-Pass-9917", "secret": ""}
        r = c.post("/v2/credentials/profiles", data=dict(body, kind="platform",
                                                         value="arista-eos"))
        assert r.status_code == 200 and "Saved platform:arista-eos" in r.get_data(as_text=True)
        # A site chosen for a platform profile: refused naming both, and drawn chosen still.
        r = c.post("/v2/credentials/profiles", data=dict(body, kind="platform", value="lab"))
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 400 and "no device can match platform:lab" in html
        assert "arista-eos, cisco-ios, hp-procurve, linux, ovs" in html
        assert '<option value="lab" selected>' in html
        with open(loaded["dir"] / "credential_profiles.json", encoding="utf-8") as fh:
            assert list(json.load(fh)["profiles"]) == ["platform:arista-eos"]

    @pytest.mark.parametrize("kind,words", [
        ("role:switch", "a profile for every switch covers its devices on every platform and "
                        "at every site, and 'lab' was chosen as its platform or site"),
        ("default", "the default profile covers its devices on every platform and at every "
                    "site, and 'lab' was chosen as its platform or site")])
    def test_a_kind_or_the_default_given_a_site_is_refused_naming_both(self, loaded, kind,
                                                                      words):
        r = loaded["client"].post("/v2/credentials/profiles", data={
            "kind": kind, "value": "lab", "username": "u", "password": "Prof-Pass-9917",
            "secret": ""})
        assert r.status_code == 400 and words in unescape(r.get_data(as_text=True))
        assert not (loaded["dir"] / "credential_profiles.json").exists()

    def test_with_nothing_loaded_each_group_says_so(self, page, monkeypatch):
        from modules import settings_schema
        real = settings_schema.get_setting
        monkeypatch.setattr(settings_schema, "get_setting", lambda key, default=None: (
            {} if key == "platform_map" else real(key, default)))
        html = unescape(page["client"].get("/v2/credentials/profiles/form")
                        .get_data(as_text=True))
        assert '<option value="" disabled>no platform is in the platform map</option>' in html
        assert ('<option value="" disabled>no NetBox inventory has loaded a device at a site'
                '</option>') in html
        # The only choice left is none: a platform profile saved with it is refused, naming
        # the scope, and nothing is stored.
        r = page["client"].post("/v2/credentials/profiles", data={
            "kind": "platform", "value": "", "username": "u", "password": "Prof-Pass-9917",
            "secret": ""})
        assert r.status_code == 400 and "name the platform it covers" in unescape(
            r.get_data(as_text=True))
        assert not (page["dir"] / "credential_profiles.json").exists()


# ------------------------------------------------------------------ T21: "no login" as a state

class TestNoLoginIsAState:
    def test_a_device_no_login_covers_loads_naming_the_scopes(self, lab):
        devices, skipped, warnings = adapt()
        assert skipped == [] and len(devices) == len(LAB)
        words = devices["of-sw3"]["_login"]
        assert words.startswith("no login: no credential profile covers")
        assert "platform hp-procurve" in words and "kind switch" in words and "site lab" in words
        assert devices["of-sw3"]["username"] == ""
        assert {w["name"] for w in warnings if w["field"] == "credentials"} == set(devices)

    def test_a_resolving_device_carries_no_state(self, lab):
        lab.save_profile("default", "admin", "pw")
        devices, _s, _w = adapt()
        assert not any(d["_login"] for d in devices.values())

    @pytest.mark.parametrize("ip", ("192.0.2.15", "2001:db8::15"), ids=("ipv4", "ipv6"))
    def test_a_session_to_it_is_refused_naming_the_state(self, lab, ip):
        from modules import connection as C
        devices, _s, _w = adapt()
        dev = dict(devices["of-sw3"], ip=ip)
        with pytest.raises(C.NoLogin) as e:
            C.stored_connection_params(dev)
        assert "no login: no credential profile covers platform hp-procurve" in str(e.value)
        assert "No session was opened" in str(e.value)

    def test_no_platform_and_no_primary_ipv4_stay_named_skips(self, lab):
        raws = lab_records()
        raws[0]["primary_ip4"] = None
        raws[1]["platform"] = None
        devices, skipped, _w = adapt(raws)
        assert {s["name"]: s["field"] for s in skipped} == {"router": "primary_ip4",
                                                            "mgmt-sw": "platform"}
        assert "router" not in devices and "mgmt-sw" not in devices

    def test_one_row_per_network_counts_them_and_clears_when_they_resolve(
            self, lab, tmp_path, monkeypatch):
        from modules import attention, inventory
        folder = tmp_path / "lab9"
        folder.mkdir()
        monkeypatch.setattr("modules.config.list_data_path", lambda name: str(folder))
        monkeypatch.setattr(inventory, "get_list_data_dir", lambda name: str(folder))
        monkeypatch.setattr("modules.inventory.source_config.is_netbox_sourced",
                            lambda name: True)
        devices, skipped, warnings = netbox_source.adapt_devices(lab_records(), kinds=KINDS)
        inventory._persist("lab9", {"devices": devices, "skipped": skipped,
                                    "warnings": warnings, "fetched_at": 1})
        got = attention.netbox_inventory_source(names=["lab9"])
        (row,) = [r for r in got["rows"] if r["kind"] == "no_login"]
        assert row["what"].startswith(f"{len(LAB)} devices in lab9 have no login: add a "
                                      "profile for platform:cisco-ios")
        assert row["operands"]["devices"] == len(LAB)
        assert "platform:linux" in row["operands"]["scopes"]
        assert "Credentials › Profiles" in row["action"]["label"]
        lab.save_profile("default", "admin", "pw")
        devices, skipped, warnings = netbox_source.adapt_devices(lab_records(), kinds=KINDS)
        inventory._persist("lab9", {"devices": devices, "skipped": skipped,
                                    "warnings": warnings, "fetched_at": 2})
        got = attention.netbox_inventory_source(names=["lab9"])
        assert [r for r in got["rows"] if r["kind"] == "no_login"] == []


# ------------------------------------------------------------------ T19: observe-only devices

OBSERVE = {"mercury": {"management": "observe"}}
MANAGE = {"mercury": {"management": "manage"}}


class TestTheMarkIsTheRenderedContext:
    def test_set_in_the_devices_local_context_gives_observe(self):
        got = M.mark(record("router", "cisco-ios", "edge-router", "192.0.2.11", 1,
                            context=OBSERVE, local=OBSERVE))
        assert got == {"mode": "observe", "from": M.FROM_LOCAL, "problem": ""}

    def test_set_by_a_tag_assigned_context_gives_observe(self):
        got = M.mark(record("mgmt-sw", "cisco-ios", "mgmt-switch", "192.0.2.12", 2,
                            context=OBSERVE, local=None))
        assert got["mode"] == "observe" and got["from"] == M.FROM_ASSIGNED

    def test_a_role_contexts_observe_under_a_local_manage_gives_manage(self):
        # NetBox merges the local data last, so the rendered context says manage.
        got = M.mark(record("router", "cisco-ios", "edge-router", "192.0.2.11", 1,
                            context=MANAGE, local=MANAGE))
        assert got["mode"] == "manage" and got["from"] == M.FROM_LOCAL

    def test_a_local_and_rendered_disagreement_is_judged_by_the_rendered(self):
        got = M.mark(record("router", "cisco-ios", "edge-router", "192.0.2.11", 1,
                            context=MANAGE, local=OBSERVE))
        assert got["mode"] == "manage"
        got = M.mark(record("router", "cisco-ios", "edge-router", "192.0.2.11", 1,
                            context={}, local=OBSERVE))
        assert got == {"mode": "manage", "from": M.FROM_DEFAULT, "problem": ""}

    def test_no_rendered_context_is_manage_said_as_not_read(self):
        assert M.mark(CAPTURE) == {"mode": "manage", "from": M.FROM_UNRENDERED, "problem": ""}

    def test_a_value_that_is_neither_word_is_read_as_observe_and_said(self):
        got = M.mark(record("router", "cisco-ios", "edge-router", "192.0.2.11", 1,
                            context={"mercury": {"management": "read-only"}}))
        assert got["mode"] == "observe" and "'read-only'" in got["problem"]

    def test_the_inventory_carries_the_mark_and_the_fetch_asks_for_the_rendered_context(
            self, lab, monkeypatch):
        devices, _s, _w = adapt(lab_records(router={"context": OBSERVE, "local": OBSERVE}))
        assert devices["router"]["_management"] == "observe"
        assert devices["router"]["_management_from"] == M.FROM_LOCAL
        assert devices["mgmt-sw"]["_management"] == "manage"
        asked = []
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (True, "", object(), "http://netbox.example.invalid"))
        monkeypatch.setattr("modules.netbox_client._nb_get",
                            lambda s, b, path, **p: asked.append((path, p)) or [])
        monkeypatch.setattr("modules.inventory.role_kind.read",
                            lambda s, b: {"field": True, "roles": [], "kinds": {}})
        assert netbox_source.fetch_netbox_devices({})["ok"]
        assert asked[0] == ("dcim/devices/", {"limit": 500, "include": "config_context"})


@pytest.fixture
def held_lab(lab, monkeypatch):
    """The lab's loaded inventory with the router observe-only (its local context) and the
    controller a host, as `inventory.cached_row` serves it."""
    from modules import inventory
    lab.save_profile("default", "admin", "pw")
    devices, _s, _w = adapt(lab_records(router={"context": OBSERVE, "local": OBSERVE}))
    monkeypatch.setattr(inventory, "cached_row", lambda name, host: devices.get(host)
                        if name == "lab9" else None)
    return devices


class TestAnObserveDeviceIsChangedByNothing:
    @pytest.mark.parametrize("operation", ["deploy", "restore", "persist", "rotate", "save",
                                           "privileged", "openflow config", "adopt",
                                           # C2626: a reload restarts it; C2625: no flow
                                           # onboards a device already in NetBox's inventory.
                                           "reload", "onboard", "onboard (create)"])
    def test_every_changing_hold_is_refused_naming_the_key_and_where(self, held_lab, operation):
        from modules.nsot import device_ops as D
        with pytest.raises(D.NotManaged) as e:
            D.acquire("lab9", "router", operation, "op@example.invalid")
        assert "mercury.management to observe (the device's local config context)" \
            in str(e.value)
        assert operation in str(e.value) and D.holder("lab9", "router") is None

    @pytest.mark.parametrize("operation", ["read", "capture", "seed intent"])
    def test_its_reads_and_captures_are_held(self, held_lab, operation):
        from modules.nsot import device_ops as D
        with D.hold("lab9", "router", operation, "op@example.invalid"):
            assert D.holder("lab9", "router")["operation"] == operation

    @pytest.mark.parametrize("address", ["192.0.2.11", "2001:db8::11", "198.51.100.11"],
                             ids=("primary-ipv4", "primary-ipv6", "out-of-band"))
    def test_an_onboarding_at_an_observe_devices_address_is_refused_by_address(
            self, lab, monkeypatch, address):
        """C2625 (the operator, 2026-11-06): the refusal follows the mark, never the name. The
        router, observe-only, is renamed in NetBox (`edge-gw`), and an onboarding under a new
        name at any of its management addresses is refused, naming the device and the mark."""
        from modules import inventory
        from modules.inventory import management
        from modules.nsot import onboard
        lab.save_profile("default", "admin", "pw")
        records = lab_records(router={"context": OBSERVE, "local": OBSERVE})
        router = next(r for r in records if r["name"] == "router")
        router.update(name="edge-gw", display="edge-gw",
                      primary_ip6={"address": "2001:db8::11/64", "display": "2001:db8::11/64"},
                      oob_ip={"address": "198.51.100.11/24", "display": "198.51.100.11/24"})
        rows = list(adapt(records)[0].values())
        monkeypatch.setattr(inventory, "cached_rows",
                            lambda name: rows if name == "lab9" else [])
        said = onboard._observe_problem("lab9", address)
        assert said.startswith(f"REFUSED: {address} is a management address of edge-gw"), said
        assert "mercury.management observe" in said and "Nothing was sent." in said
        plan = onboard.OnboardPlan(hostname="new-router", platform="ios", list_name="lab9",
                                   observe_problem=said)
        assert said in plan.blocking_reasons

    def test_an_address_no_observe_device_answers_on_is_not_refused(self, lab, monkeypatch):
        from modules import inventory
        from modules.nsot import onboard
        lab.save_profile("default", "admin", "pw")
        rows = list(adapt(lab_records(router={"context": OBSERVE, "local": OBSERVE}))[0]
                    .values())
        monkeypatch.setattr(inventory, "cached_rows", lambda name: rows)
        assert onboard._observe_problem("lab9", "192.0.2.13") == "", "of-sw1 is managed"
        assert onboard._observe_problem("lab9", "192.0.2.99") == "", "nobody's"
        assert onboard._observe_problem("lab9", "") == "", "no address given"

    def test_a_reload_is_refused_saying_to_set_it_to_manage_first(self, held_lab):
        """C2626 (the operator, 2026-11-06): observe means Mercury changes nothing on it, its
        running state included; a router's reload takes down the lab's internet, DHCP and NTP.
        To reload it through Mercury, a person sets it to manage first, on its record."""
        from modules.nsot import device_ops as D
        with pytest.raises(D.NotManaged) as e:
            D.acquire("lab9", "router", "reload", "op@example.invalid")
        said = str(e.value)
        assert "set it to manage first in NetBox, on its record" in said, said
        assert said.endswith("Nothing was sent.") and D.holder("lab9", "router") is None

    def test_a_host_is_still_held_for_a_reload_and_a_managed_device_for_anything(self, held_lab):
        """Each device is judged by its own list (C2625: the host list's operations were
        allowed before the device was read)."""
        from modules.inventory import management
        assert management.hold_refusal("lab9", "controller", "reload") == ""
        assert management.hold_refusal("lab9", "of-sw1", "reload") == ""
        assert management.hold_refusal("lab9", "router", "reload") != ""

    def test_a_batch_refuses_it_alone(self, held_lab):
        from modules.nsot import device_ops as D
        held, refused = D.acquire_many("lab9", ["router", "of-sw1"], "deploy", "op")
        try:
            assert held == ["of-sw1"] and refused[0]["device"] == "router"
            assert "observe" in refused[0]["reason"]
        finally:
            D.release_many("lab9", held)

    def test_the_plan_every_preview_draws_refuses_it_naming_the_mark(self, lab, monkeypatch):
        """C2621: the batch preview, a fleet change's plan and the device page's Deploy… all
        draw `routes.deploy.plan_devices`; an observe device and a host are planned as
        refused, naming the mark, so no preview lists either as a target the apply would then
        refuse. The inventory's rows are read once a plan, never once a device."""
        from modules import inventory
        from modules.preview_confirm import deploy_preview
        from routes import deploy
        lab.save_profile("default", "admin", "pw")
        rows = list(adapt(lab_records(router={"context": OBSERVE, "local": OBSERVE}))[0]
                    .values())
        reads = []
        monkeypatch.setattr(inventory, "cached_rows",
                            lambda name: reads.append(name) or (rows if name == "lab9" else []))
        # A managed device goes on to its build (here, none: nothing in the store to build).
        monkeypatch.setattr(deploy, "_artifact_for", lambda name, host: (None, "not built"))
        got = {e["device"]: e for e in deploy.plan_devices("lab9",
                                                          ["router", "controller", "of-sw1"])}
        assert reads == ["lab9"]
        router, controller = got["router"], got["controller"]
        assert router["deployable"] is False and router["management_refused"]
        assert router["blocking_reasons"][0].startswith("REFUSED: a deploy on router: NetBox's "
                                                        "config context sets mercury.management "
                                                        "to observe (the device's local config "
                                                        "context)"), router["blocking_reasons"]
        assert controller["deployable"] is False and "mercury_kind is host" in \
            controller["blocking_reasons"][0]
        assert got["of-sw1"]["blocking_reasons"] == ["not built"], "a managed device is built"
        assert not got["of-sw1"].get("management_refused")
        import app as A
        with A.app.test_request_context("/"):
            from flask import request
            preview = deploy_preview([router], request)
        target = next(t for t in preview["what"]["targets"] if t["name"] == "router")
        assert target["state"] == "blocked" and target["selectable"] is False
        assert any(w["text"].startswith("Not sent: REFUSED: a deploy on router")
                   for w in preview["what_not"]["items"]), preview["what_not"]

    def test_the_pipelines_gate_refuses_it_before_any_session(self, held_lab):
        from modules.pipeline import PipelineContext, PipelineStageError, _stage_ci_gate
        dev = held_lab["router"]
        ctx = PipelineContext(config_type="interface", device_ips=[dev["ip"]], params={},
                              ip_params_map={}, selected_devices=[dev], connections_pool={},
                              pool_lock=threading.Lock(), config_id="t", list_name="lab9")
        ctx.rendered_commands = {dev["ip"]: ["interface Gi0/1", " description x"]}
        with pytest.raises(PipelineStageError) as e:
            _stage_ci_gate(ctx)
        assert "observe" in str(e.value) and "local config context" in str(e.value)
        assert not ctx.ci_passed

    def test_a_managed_device_passes_the_gate(self, held_lab):
        from modules.pipeline import PipelineContext, _stage_ci_gate
        dev = held_lab["of-sw1"]
        ctx = PipelineContext(config_type="interface", device_ips=[dev["ip"]], params={},
                              ip_params_map={}, selected_devices=[dev], connections_pool={},
                              pool_lock=threading.Lock(), config_id="t", list_name="lab9")
        ctx.rendered_commands = {dev["ip"]: ["interface Et1", " description x"]}
        _stage_ci_gate(ctx)
        assert ctx.ci_passed

    def test_the_actions_menu_offers_no_change_and_names_the_state(self, held_lab):
        from html import unescape
        from flask import render_template
        import app as A
        from routes.device_v2 import _changes_offered
        dev = held_lab["router"]
        with A.app.test_request_context("/v2/device/router"):
            html = unescape(render_template(
                "v2/_actions_menu.html", device=dev, list_name="lab9", tab="overview",
                block={"blocked": False, "why": "no rollback"},
                rekey={"held": False, "why": "x"}, verify_again={"offered": False, "why": "x"},
                changes=_changes_offered(dev)))
        assert "router is observe (the device's local config context)" in html
        for label in ("Plan a deploy…", "Restore from…", "Remove lines (Mode B)…",
                      "Rotate credential…", "Persist", "Run a privileged command…"):
            assert f'>{label}<span class="sr-only"> (not offered: a change on router: ' \
                   f"NetBox's config context sets mercury.management to observe" in html, label
        for op in ("deploy", "restore", "removal", "rotate", "persist", "privileged"):
            assert f'data-op="{op}"' not in html, op
        assert 'data-op="capture"' in html                  # its capture is still offered


# ------------------------------------------------------------------ T22: the host kind

class TestTheHostKind:
    def test_netboxs_field_accepts_host(self):
        import re
        from modules.inventory import role_kind
        rx = re.compile(role_kind.FIELD_SPEC["validation_regex"])
        assert rx.match("host") and rx.match("switch") and not rx.match("hosts")
        assert "host" in role_kind.KINDS and "host" not in role_kind.NETWORK_KINDS

    def test_a_role_netbox_classifies_host_is_read_as_host(self):
        from modules.inventory import role_kind
        from tests.fake_netbox import FakeNetBox
        nb = FakeNetBox()
        nb.seed("extras/custom-fields", {"name": "mercury_kind"})
        nb.seed("dcim/device-roles", {"slug": "controller",
                                      "custom_fields": {"mercury_kind": "host"}})
        nb.seed("dcim/device-roles", {"slug": "server", "custom_fields": {"mercury_kind": "vm"}})
        got = role_kind.read(nb, "http://netbox.example.invalid")
        assert got["kinds"] == {"controller": "host"}

    def test_the_controller_loads_as_a_host_on_the_linux_driver(self, lab):
        lab.save_profile("platform:linux", "mercury", "pw")
        devices, _s, _w = adapt()
        c = devices["controller"]
        assert (c["role"], c["device_type"], c["_cred_source"]) == \
            ("host", "linux", "profile:platform:linux")

    @pytest.mark.parametrize("command", ["cat /etc/os-release",
                                         "systemctl list-units --type=service --no-pager",
                                         "systemctl status --no-pager ctl.service",
                                         "systemctl show -p User -p ExecStart ctl.service",
                                         "systemctl cat ctl.service", "ls -la /opt/apps"])
    def test_its_capture_list_and_shapes_are_its_reads(self, command):
        from modules import discovery
        assert discovery.command_refusal("linux", command) == ""

    @pytest.mark.parametrize("command", ["systemctl restart ctl.service", "cat /etc/shadow",
                                         "systemctl cat ctl.service; reboot",
                                         "ls -la /opt/../etc", "ls -la /opt/a/b", "sudo -s",
                                         "systemctl status --no-pager a b"])
    def test_anything_else_is_refused_naming_it(self, command):
        from modules import discovery
        why = discovery.command_refusal("linux", command)
        assert why.startswith("REFUSED") and repr(command[:80]) in why

    def test_its_one_held_write_is_declared_and_refused_naming_p6(self):
        from modules import discovery
        assert discovery.DRIVERS["linux"]["held_write"]
        why = discovery.held_write_refusal("linux", "anything")
        assert "P6" in why and "Nothing was sent" in why

    @pytest.mark.parametrize("operation", ["capture", "deploy", "restore", "seed intent",
                                           "persist", "rotate", "save"])
    def test_goldens_deploys_and_intent_refuse_it(self, held_lab, operation):
        from modules.nsot import device_ops as D
        with pytest.raises(D.NotManaged) as e:
            D.acquire("lab9", "controller", operation, "op@example.invalid")
        assert "mercury_kind is host" in str(e.value) and "P6" in str(e.value)

    def test_its_reads_are_held(self, held_lab):
        from modules.nsot import device_ops as D
        with D.hold("lab9", "controller", "read", "op@example.invalid"):
            assert D.holder("lab9", "controller")["operation"] == "read"

    def test_the_pipelines_gate_refuses_it(self, held_lab):
        from modules.pipeline import PipelineContext, PipelineStageError, _stage_ci_gate
        dev = held_lab["controller"]
        ctx = PipelineContext(config_type="interface", device_ips=[dev["ip"]], params={},
                              ip_params_map={}, selected_devices=[dev], connections_pool={},
                              pool_lock=threading.Lock(), config_id="t", list_name="lab9")
        ctx.rendered_commands = {dev["ip"]: ["x"]}
        with pytest.raises(PipelineStageError, match="mercury_kind is host"):
            _stage_ci_gate(ctx)

    def test_heal_is_refused_for_it_and_an_observe_device(self, held_lab):
        """The words heal's guard 4 holds them with (its decision: tests/test_heal_decide.py,
        `test_4_an_observe_device_or_a_host_has_no_state_to_heal_to`)."""
        assert "mercury_kind is host" in M.refusal_for("lab9", "controller", what="heal")
        assert "observe" in M.refusal_for("lab9", "router", what="heal")
        assert M.refusal_for("lab9", "of-sw1", what="heal") == ""

    def test_config_drift_leaves_it_out_by_name(self, held_lab, monkeypatch):
        from modules import drift_check
        devices = [held_lab["controller"], dict(held_lab["of-sw3"], _login="no login: x")]
        monkeypatch.setattr("modules.device.load_saved_devices", lambda path: devices)
        monkeypatch.setattr("modules.nsot.listref.resolve",
                            lambda name: type("R", (), {"csv_path": "x"})())
        # A device in the population with no golden is a named skip: neither is one.
        monkeypatch.setattr("modules.goldens._golden_record",
                            lambda ip, list_name: {"text": None, "refused": ""})
        got = drift_check._run_drift_check(triggered_by="test", list_name="lab9")
        assert (got["inventory"], got["checked"], got["skipped"]) == (0, 0, [])
        assert {e["hostname"] for e in got["excluded"]} == {"controller", "of-sw3"}
        assert "controller (a host: not in config drift)" in got["summary"]

    def test_interface_monitoring_leaves_it_out_by_name(self, held_lab):
        from modules import prometheus_targets as PT
        ref = type("R", (), {"name": "lab9"})()
        got = PT.generate(devices=[(ref, held_lab["controller"])],
                          golden=lambda ref, host: "snmp-server community x RO")
        assert got["devices"] == 0 and "a host" in got["excluded"]["controller"]
