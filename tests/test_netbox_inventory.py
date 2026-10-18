"""NetBox-sourced device lists.

The contract is **shape fidelity**: a device dict produced by the adapter must
be indistinguishable from one loaded from a CSV, because ~79 call sites across
11 modules consume it without knowing which kind of list they are looking at.

Also covers the amendments: dispatch does no network I/O, credentials come from
one designated list, roles map to valid topology values, stale devices are
inert, and an unmapped platform skips unless a default type is configured.
"""

import json
import time

import pytest

from modules import credentials, inventory
from modules.inventory import netbox_source
from modules.inventory.source_config import SOURCE_NETBOX


def _raw(name="R1", ip="203.0.113.1", platform="cisco-ios-xe",
         role="router", site="lab", nb_id=1):
    return {
        "id": nb_id, "name": name,
        "primary_ip4": {"address": f"{ip}/24"} if ip else None,
        "platform": {"slug": platform} if platform else None,
        "role": {"slug": role} if role else None,
        "site": {"slug": site, "name": site.title()},
        "status": {"value": "active"},
    }


@pytest.fixture
def creds(tmp_path, monkeypatch):
    """A default credential profile in an isolated store."""
    monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "creds.json"))
    credentials.save_profile("default", "admin", "pw", "en")
    return credentials


class TestShapeFidelity:
    """The adapter's output must match a CSV row key for key."""

    CSV_FIELDS = {"hostname", "device_type", "ip", "username", "password", "secret", "role"}

    def test_produces_every_csv_field(self, creds):
        devices, skipped, _w = netbox_source.adapt_devices([_raw()])
        assert skipped == []
        assert self.CSV_FIELDS.issubset(set(devices[0]))

    def test_credentials_are_encrypted_like_a_csv_row(self, creds):
        """Callers decrypt at use; an adapter returning plaintext would break them."""
        from modules.device import decrypt_field
        devices, _s, _w = netbox_source.adapt_devices([_raw()])
        dev = devices[0]
        assert dev["password"] != "pw"
        assert decrypt_field(dev["password"]) == "pw"
        assert decrypt_field(dev["secret"]) == "en"

    def test_ip_has_no_prefix_length(self, creds):
        devices, _s, _w = netbox_source.adapt_devices([_raw(ip="203.0.113.7")])
        assert devices[0]["ip"] == "203.0.113.7"

    def test_values_are_valid_not_just_present(self, creds):
        """Amendment 3: assert the values are usable, not merely that keys exist."""
        devices, _s, _w = netbox_source.adapt_devices([_raw()])
        dev = devices[0]
        assert dev["role"] in netbox_source.VALID_ROLES
        assert dev["device_type"] == "cisco_xe"
        assert dev["hostname"] and dev["ip"] and dev["username"]

    def test_metadata_is_stripped_before_netmiko(self, creds):
        devices, _s, _w = netbox_source.adapt_devices([_raw()])
        clean = inventory.strip_metadata(devices[0])
        assert set(clean) == self.CSV_FIELDS
        assert not any(k.startswith("_") for k in clean)


class TestSkipSemantics:
    """A device that cannot be represented is skipped, never fatal."""

    def test_missing_primary_ip_is_skipped(self, creds):
        devices, skipped, _w = netbox_source.adapt_devices([_raw(ip=None)])
        assert devices == []
        assert skipped[0]["field"] == "primary_ip4"
        assert "no primary IPv4" in skipped[0]["reason"]

    def test_unmapped_platform_is_skipped(self, creds):
        devices, skipped, _w = netbox_source.adapt_devices([_raw(platform="arista-eos")])
        assert devices == []
        assert skipped[0]["field"] == "platform"

    def test_missing_credentials_is_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "empty.json"))
        devices, skipped, _w = netbox_source.adapt_devices([_raw()])
        assert devices == []
        assert skipped[0]["field"] == "credentials"

    def test_one_bad_device_does_not_fail_the_list(self, creds):
        """The central promise: nine good devices out of ten still work."""
        raws = [_raw(f"R{i}", f"203.0.113.{i}", nb_id=i) for i in range(1, 10)]
        raws.append(_raw("R99", ip=None, nb_id=99))
        devices, skipped, _w = netbox_source.adapt_devices(raws)
        assert len(devices) == 9
        assert len(skipped) == 1
        assert skipped[0]["name"] == "R99"

    def test_skip_reason_names_the_device_and_field(self, creds):
        _d, skipped, _w = netbox_source.adapt_devices([_raw("R7", ip=None, nb_id=42)])
        entry = skipped[0]
        assert entry["name"] == "R7" and entry["netbox_id"] == 42 and entry["field"]


class TestPlatformDefault:
    """Amendment 6: an optional default type trades a skip for a warning."""

    def test_default_type_replaces_the_skip(self, creds, monkeypatch):
        monkeypatch.setattr(netbox_source, "get_setting", lambda key, default=None: {
            "platform_map": {}, "platform_default_netmiko_type": "cisco_ios",
        }.get(key, default))
        devices, skipped, warnings = netbox_source.adapt_devices([_raw(platform="arista-eos")])
        assert skipped == []
        assert devices[0]["device_type"] == "cisco_ios"
        assert warnings[0]["field"] == "platform"

    def test_empty_default_means_skip(self, creds):
        _d, skipped, _w = netbox_source.adapt_devices([_raw(platform="arista-eos")])
        assert skipped and skipped[0]["field"] == "platform"


class TestTheKindIsNetBoxs:
    """C665: a device's kind is its NetBox Device Role's `mercury_kind`, read once per load;
    a role without one is not classified in NetBox, said with where to set it, never guessed
    from a map or a hostname."""

    KINDS = {"field": True, "kinds": {"core-router": "router", "access-switch": "switch"},
             "roles": []}

    def test_a_classified_role_gives_its_kind(self, creds):
        devices, _s, warnings = netbox_source.adapt_devices(
            [_raw(role="core-router"), _raw("S1", "203.0.113.2", role="access-switch", nb_id=2)],
            kinds=self.KINDS)
        assert [d["role"] for d in devices] == ["router", "switch"] and warnings == []

    def test_an_unclassified_role_is_said_with_where_to_set_it(self, creds):
        devices, _s, warnings = netbox_source.adapt_devices([_raw(name="SW-1", role="spine")],
                                                            kinds=self.KINDS)
        assert devices[0]["role"] == "", "never guessed from the hostname SW-1"
        assert warnings[0]["field"] == "role"
        assert "not classified in NetBox: its role 'spine' has no Mercury kind" in \
            warnings[0]["reason"]

    def test_no_field_in_netbox_is_said_as_that(self, creds):
        _d, _s, warnings = netbox_source.adapt_devices([_raw(role="core-router")],
                                                       kinds={"field": False, "kinds": {}})
        assert "NetBox has no `mercury_kind` field on device roles" in warnings[0]["reason"]

    def test_a_device_with_no_role_has_no_kind_and_no_warning(self, creds):
        devices, _s, warnings = netbox_source.adapt_devices([_raw(role="")], kinds=self.KINDS)
        assert devices[0]["role"] == "" and warnings == []

    def test_the_load_reads_the_classification_with_the_devices(self, monkeypatch):
        from tests.fake_netbox import FakeNetBox
        nb = FakeNetBox()
        nb.seed("dcim/devices", {"name": "R1"})
        nb.seed("extras/custom-fields", {"name": "mercury_kind"})
        nb.seed("dcim/device-roles", {"slug": "core-router",
                                      "custom_fields": {"mercury_kind": "router"}})
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (True, "", nb, "http://netbox.example.invalid"))
        got = netbox_source.fetch_netbox_devices({})
        assert got["ok"] and got["kinds"]["kinds"] == {"core-router": "router"}


class TestADeletedSiteReadsUnreadable:
    """C1248: a NetBox list filters by its STORED site slug, and NetBox answers 400 to a slug
    naming no site (measured on the lab's NetBox 2026-10-18). A list whose site was deleted in
    NetBox therefore reads as unreadable, the last good devices kept and flagged stale, never
    as "no devices" (which would mark every device gone). Through the real source on the shared
    fake, which answers as NetBox does."""

    @pytest.fixture
    def lab(self, tmp_path, monkeypatch):
        import modules.config as config_mod
        from tests.fake_netbox import FakeNetBox

        monkeypatch.setattr(config_mod, "LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.device.LISTS_DIR", str(tmp_path), raising=False)
        monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "creds.json"))
        credentials.save_profile("default", "admin", "pw", "en")
        (tmp_path / "sitelist").mkdir()
        (tmp_path / "sitelist" / "source.json").write_text(
            json.dumps({"source": SOURCE_NETBOX, "filters": {"site": "lab"}}), encoding="utf-8")
        monkeypatch.setattr("modules.device._load_device_lists_config",
                            lambda: {"current_list": "SiteList",
                                     "lists": {"SiteList": "sitelist"}})

        nb = FakeNetBox()
        site = nb.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
        nb.seed("extras/custom-fields", {"name": "mercury_kind"})
        nb.seed("dcim/device-roles", {"name": "Router", "slug": "router",
                                      "custom_fields": {"mercury_kind": "router"}})
        raw = _raw("R1", "203.0.113.1", nb_id=None)
        raw.pop("id")
        raw["site"] = {"id": site["id"], "slug": "lab", "name": "Lab"}
        nb.seed("dcim/devices", raw)
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (True, "", nb, "http://netbox.example.invalid"))
        inventory.invalidate()
        yield nb, site
        inventory.invalidate()

    def test_the_list_reads_its_site_while_the_site_exists(self, lab):
        """The control: the stored slug names a site, and the list loads its device."""
        from modules.inventory import load_netbox_devices, refresh_list

        assert refresh_list("SiteList")["ok"]
        devices, _s, meta = load_netbox_devices("SiteList")
        assert [d["hostname"] for d in devices] == ["R1"] and meta["stale"] is False

    def test_fetch_by_a_deleted_site_is_not_ok(self, lab):
        nb, site = lab
        nb.delete(f"http://netbox.example.invalid/api/dcim/sites/{site['id']}/")
        got = netbox_source.fetch_netbox_devices({"site": "lab"})
        assert got["ok"] is False and got["devices"] == [], got
        assert "400" in got["error"], got["error"]

    def test_a_deleted_site_keeps_the_last_good_list_and_says_unreadable(self, lab):
        from modules.inventory import get_stale_devices, load_netbox_devices, refresh_list

        nb, site = lab
        assert refresh_list("SiteList")["ok"]
        nb.delete(f"http://netbox.example.invalid/api/dcim/sites/{site['id']}/")
        got = refresh_list("SiteList")
        assert got["ok"] is False, "a deleted site read as an empty list"
        devices, _s, meta = load_netbox_devices("SiteList")
        assert [d["hostname"] for d in devices] == ["R1"], "the last good list was emptied"
        assert meta["stale"] is True and "400" in meta["error"], meta
        assert get_stale_devices("SiteList") == {}, "R1 was marked gone from NetBox"


class TestCredentialResolution:
    """Amendment 2: one designated list, never a scan, and always traceable."""

    def test_designated_list_supplies_credentials(self, tmp_path, monkeypatch):
        from modules.device import fernet
        monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "c.json"))

        lists_dir = tmp_path / "lists" / "lab_devices"
        lists_dir.mkdir(parents=True)
        (lists_dir / "devices.csv").write_text(
            "hostname,device_type,ip,username,password,secret,role\n"
            f"R1,cisco_ios,203.0.113.1,csvuser,"
            f"{fernet.encrypt(b'csvpw').decode()},{fernet.encrypt(b'csven').decode()},router\n",
            encoding="utf-8")
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))

        out = credentials.resolve("203.0.113.1", credential_list="Lab Devices")
        assert out["ok"] and out["username"] == "csvuser"
        assert out["source"] == "local-list:Lab Devices"

    def test_the_designated_lists_password_and_secret_are_opened(self, tmp_path, monkeypatch):
        """C1263 (Lab 7's second mutation sample, 2026-10-18): the list's file holds each
        credential as the device writer encrypts it, and `resolve` handed that ciphertext out as
        the password, ok and with the right username and source (a wrong thing that looked
        right). The list is written here by the real writer, `device.save_device`."""
        from modules import device as D

        monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "c.json"))
        lists_dir = tmp_path / "lists" / "lab_devices"
        lists_dir.mkdir(parents=True)
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
        D.save_device({"hostname": "R1", "device_type": "cisco_ios", "ip": "203.0.113.1",
                       "username": "csvuser", "password": "csvpw", "secret": "csven"},
                      filename=str(lists_dir / "devices.csv"))

        out = credentials.resolve("203.0.113.1", credential_list="Lab Devices")
        assert out["ok"] and out["source"] == "local-list:Lab Devices"
        assert (out["username"], out["password"], out["secret"]) == ("csvuser", "csvpw",
                                                                     "csven")

    def test_source_is_recorded_for_traceability(self, creds):
        devices, _s, _w = netbox_source.adapt_devices([_raw()])
        assert devices[0]["_cred_source"] == "profile:default"

    def test_device_override_wins(self, creds):
        credentials.set_device_override("203.0.113.1", "ovr", "ovrpw")
        devices, _s, _w = netbox_source.adapt_devices([_raw()])
        assert devices[0]["username"] == "ovr"
        assert devices[0]["_cred_source"] == "device-override"

    def test_no_scan_of_other_lists(self, creds, monkeypatch):
        """An undesignated list must never supply credentials."""
        called = []
        monkeypatch.setattr(credentials, "_from_credential_list",
                            lambda name, ip: called.append(name))
        credentials.resolve("203.0.113.1", credential_list="")
        assert called == [""]


class TestTheResolverAnswersWhole:
    """Lab 7 (b), the second sample: `credentials.resolve`, the order a NetBox device's login
    comes from (device override, the designated list, role, site, default profile), each
    source answering the WHOLE credential (username, password and enable secret, decrypted)
    and naming itself. The tests above check one field of two sources; the role and site
    profiles, every password and secret, and the miss itself were held by none. The designated
    list's own CSV read is stood in for here: measured with this sample, it returns the CSV's
    stored ciphertext as the password and secret (secrets_store.decrypt_value passes a value
    without its own prefix through unchanged), a defect reported with the sample, not fixed in
    it, so only `resolve`'s handling of what the read returns is held."""

    IP = "192.0.2.9"

    @pytest.fixture
    def store(self, tmp_path, monkeypatch):
        monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "creds.json"))
        credentials.save_profile("role:router", "roleuser", "rolepw", "roleen")
        credentials.save_profile("site:lab", "siteuser", "sitepw", "siteen")
        credentials.save_profile("default", "defuser", "defpw", "defen")
        return credentials

    @staticmethod
    def _whole(user, source):
        return {"ok": True, "username": f"{user}user", "password": f"{user}pw",
                "secret": f"{user}en", "source": source}

    def test_an_override_answers_first(self, store):
        store.set_device_override(self.IP, "ovruser", "ovrpw", "ovren")
        assert store.resolve(self.IP, role="router", site="lab") == self._whole(
            "ovr", "device-override")

    def test_the_designated_list_answers_next(self, store, monkeypatch):
        monkeypatch.setattr(store, "_from_credential_list",
                            lambda name, ip: ("listuser", "listpw", "listen")
                            if (name, ip) == ("Lab Devices", self.IP) else None)
        assert store.resolve(self.IP, role="router", site="lab",
                             credential_list="Lab Devices") == self._whole(
            "list", "local-list:Lab Devices")

    def test_a_list_row_with_no_username_is_no_credential(self, store, monkeypatch):
        monkeypatch.setattr(store, "_from_credential_list",
                            lambda name, ip: ("", "listpw", "listen"))
        assert store.resolve(self.IP, credential_list="Lab Devices") == self._whole(
            "def", "profile:default")

    def test_then_the_role_then_the_site_then_the_default(self, store):
        assert store.resolve(self.IP, role="router", site="lab") == self._whole(
            "role", "profile:role:router")
        assert store.resolve(self.IP, role="switch", site="lab") == self._whole(
            "site", "profile:site:lab")
        assert store.resolve(self.IP, role="switch", site="branch") == self._whole(
            "def", "profile:default")

    def test_nothing_matching_is_a_miss_that_says_where_to_set_one(self, tmp_path, monkeypatch):
        monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "empty.json"))
        assert credentials.resolve(self.IP, role="router", site="lab") == {
            "ok": False, "username": "", "password": "", "secret": "", "source": "",
            "error": ("no credentials — set a device override, a default profile, or a "
                      "credential list for this NetBox list")}

    def test_a_device_with_no_address_takes_nothing_from_the_list(self, tmp_path, monkeypatch):
        """An empty management address is no key: even a list row with no address of its
        own is never its credential."""
        lists = tmp_path / "lists" / "lab_devices"
        lists.mkdir(parents=True)
        (lists / "devices.csv").write_text(
            "hostname,device_type,ip,username,password,secret,role\n"
            "R9,cisco_ios,,rowuser,rowpw,rowen,router\n", encoding="utf-8")
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
        assert credentials._from_credential_list("Lab Devices", "") is None


class TestDispatchDoesNoNetworkIO:
    """Amendment 1: load_saved_devices sits on ~79 call sites."""

    @pytest.fixture(autouse=True)
    def _no_real_data_dir(self, tmp_path, monkeypatch):
        """`invalidate()` and `load_netbox_devices()` resolve the list's cache
        path through `get_list_data_dir()`, which calls `os.makedirs()` -- so
        naming a list that does not exist creates `data/lists/lab/` in the
        working checkout. Caught by conftest's data-directory guard.

        `LISTS_DIR` rather than `get_list_data_dir`, for two reasons.
        `get_list_data_dir()` reads the module global at CALL time, so
        patching it works through this package's module-level
        `from modules.config import get_list_data_dir` -- which patching the
        function itself does not. And it keeps the real per-list layout:
        replacing the function flattened `<tmp>/lab/` to `<tmp>/`, breaking a
        sibling test that asserts where the cache file lands.
        """
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))

    def test_dispatch_serves_cache_without_fetching(self, monkeypatch):
        fetches = []
        monkeypatch.setattr(netbox_source, "fetch_netbox_devices",
                            lambda f: fetches.append(f) or {"ok": True, "devices": []})
        inventory.invalidate("Lab")
        with inventory._lock:
            inventory._memory["Lab"] = {
                "devices": [{"hostname": "R1", "ip": "203.0.113.1"}],
                "skipped": [], "warnings": [], "fetched_at": time.time(),
                "stale": False, "error": "", "stale_reason": "",
            }
        devices, _s, meta = inventory.load_netbox_devices("Lab")
        assert devices[0]["hostname"] == "R1"
        assert fetches == [], "dispatch performed a NetBox fetch"
        assert meta["stale"] is False

    def test_dispatch_returns_a_copy(self, monkeypatch):
        """A caller mutating its result must not corrupt the shared cache."""
        inventory.invalidate("Lab")
        with inventory._lock:
            inventory._memory["Lab"] = {
                "devices": [{"hostname": "R1", "ip": "203.0.113.1"}],
                "skipped": [], "warnings": [], "fetched_at": time.time(),
                "stale": False, "error": "", "stale_reason": "",
            }
        devices, _s, _m = inventory.load_netbox_devices("Lab")
        devices[0]["hostname"] = "MUTATED"
        again, _s, _m = inventory.load_netbox_devices("Lab")
        assert again[0]["hostname"] == "R1"

    def test_persisted_cache_holds_no_credentials(self, tmp_path, monkeypatch):
        """A restart must restore identity, never secrets from disk."""
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        entry = {"devices": [{"hostname": "R1", "ip": "203.0.113.1",
                              "username": "admin", "password": "ENC", "secret": "ENC",
                              "device_type": "cisco_xe", "role": "router"}],
                 "skipped": [], "warnings": [], "fetched_at": time.time()}
        inventory._persist("Lab", entry)
        saved = json.loads((tmp_path / "lab" / "netbox_inventory_cache.json").read_text())
        for dev in saved["devices"]:
            assert "password" not in dev and "secret" not in dev and "username" not in dev
            assert dev["hostname"] == "R1"


class TestStaleDevices:
    """Amendment 4: artifacts are kept, but the device becomes inert."""

    @pytest.fixture
    def stale_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        (tmp_path / "lab").mkdir(parents=True, exist_ok=True)
        (tmp_path / "lab" / "source.json").write_text(
            json.dumps({"source": SOURCE_NETBOX}), encoding="utf-8")
        (tmp_path / "lab" / "stale_devices.json").write_text(
            json.dumps({"203.0.113.9": {"hostname": "R9", "reason": "gone"}}),
            encoding="utf-8")
        return "Lab"

    def test_is_stale_detects_the_device(self, stale_list):
        assert inventory.is_stale("203.0.113.9", stale_list)
        assert not inventory.is_stale("203.0.113.1", stale_list)

    def test_local_lists_never_have_stale_devices(self, tmp_path, monkeypatch):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        assert inventory.is_stale("203.0.113.9", "PlainLocalList") is False

    def test_message_explains_and_reassures(self, stale_list):
        msg = inventory.stale_message("203.0.113.9", stale_list)
        assert "R9" in msg
        assert "no longer in NetBox" in msg
        assert "still available" in msg        # artifacts are kept


class TestEndToEndDispatch:
    """The acceptance criterion: load_saved_devices serves a NetBox list
    transparently, and a local list is completely unaffected."""

    @pytest.fixture
    def netbox_list(self, tmp_path, monkeypatch):
        import modules.config as config_mod

        monkeypatch.setattr(config_mod, "LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.device.LISTS_DIR", str(tmp_path), raising=False)
        monkeypatch.setattr(credentials, "_FILE", str(tmp_path / "creds.json"))
        credentials.save_profile("default", "admin", "pw", "en")

        for slug in ("netboxlist", "locallist"):
            (tmp_path / slug).mkdir(parents=True, exist_ok=True)
        (tmp_path / "netboxlist" / "source.json").write_text(
            json.dumps({"source": SOURCE_NETBOX}), encoding="utf-8")
        (tmp_path / "locallist" / "devices.csv").write_text(
            "hostname,device_type,ip,username,password,secret,role\n"
            "LOCAL1,cisco_ios,203.0.113.200,localuser,x,y,router\n", encoding="utf-8")

        monkeypatch.setattr("modules.device._load_device_lists_config",
                            lambda: {"current_list": "NetBoxList",
                                     "lists": {"NetBoxList": "netboxlist",
                                               "LocalList": "locallist"}})
        monkeypatch.setattr(netbox_source, "fetch_netbox_devices",
                            lambda filters: {"ok": True, "devices": [
                                _raw("R1", "203.0.113.1", nb_id=1),
                                _raw("R2", "203.0.113.2", nb_id=2)]})
        inventory.invalidate()
        return tmp_path

    def test_load_saved_devices_serves_netbox_devices(self, netbox_list):
        from modules.device import load_saved_devices
        from modules.inventory import refresh_list

        refresh_list("NetBoxList")
        devices = load_saved_devices(str(netbox_list / "netboxlist" / "devices.csv"))
        assert {d["hostname"] for d in devices} == {"R1", "R2"}
        assert all(d["device_type"] == "cisco_xe" for d in devices)

    def test_local_list_is_untouched(self, netbox_list):
        from modules.device import load_saved_devices
        devices = load_saved_devices(str(netbox_list / "locallist" / "devices.csv"))
        assert len(devices) == 1 and devices[0]["hostname"] == "LOCAL1"

    def test_csv_writes_are_refused_on_a_netbox_list(self, netbox_list):
        from modules.device import save_device
        with pytest.raises(PermissionError) as exc:
            save_device({"hostname": "X", "ip": "203.0.113.9", "username": "u",
                         "password": "p", "secret": "s", "device_type": "cisco_ios",
                         "role": "router"},
                        str(netbox_list / "netboxlist" / "devices.csv"))
        assert "NetBox" in str(exc.value)

    def test_csv_writes_still_work_on_a_local_list(self, netbox_list):
        """The NetBox-sourced refusal is for NetBox lists only: a local list's CSV write passes
        it (no refusal returned or raised)."""
        from modules.device import _refuse_if_netbox_sourced
        assert _refuse_if_netbox_sourced(str(netbox_list / "locallist" / "devices.csv"),
                                         "add") is None

    def test_device_order_is_applied(self, netbox_list):
        from modules.device import load_saved_devices
        from modules.inventory import invalidate, refresh_list
        from modules.inventory.source_config import set_device_order

        set_device_order("NetBoxList", ["R2", "R1"])
        invalidate("NetBoxList")
        refresh_list("NetBoxList")
        devices = load_saved_devices(str(netbox_list / "netboxlist" / "devices.csv"))
        assert [d["hostname"] for d in devices] == ["R2", "R1"]

    def test_netbox_outage_keeps_serving_the_last_good_list(self, netbox_list, monkeypatch):
        from modules.device import load_saved_devices
        from modules.inventory import load_netbox_devices, refresh_list

        refresh_list("NetBoxList")
        monkeypatch.setattr(netbox_source, "fetch_netbox_devices",
                            lambda f: {"ok": False, "error": "connection refused",
                                       "devices": []})
        refresh_list("NetBoxList")

        devices = load_saved_devices(str(netbox_list / "netboxlist" / "devices.csv"))
        assert len(devices) == 2, "an outage emptied the list instead of serving cache"
        _d, _s, meta = load_netbox_devices("NetBoxList")
        assert meta["stale"] is True
        assert "connection refused" in meta["stale_reason"]

    def test_restart_during_outage_rehydrates_from_disk(self, netbox_list, monkeypatch):
        from modules.inventory import invalidate, load_netbox_devices, refresh_list

        refresh_list("NetBoxList")
        invalidate()                                  # simulate a process restart
        monkeypatch.setattr(netbox_source, "fetch_netbox_devices",
                            lambda f: {"ok": False, "error": "down", "devices": []})

        devices, _s, meta = load_netbox_devices("NetBoxList")
        assert {d["hostname"] for d in devices} == {"R1", "R2"}
        assert meta["stale"] is True
        # Credentials are not persisted, so they were resolved again on rehydrate.
        from modules.device import decrypt_field
        assert decrypt_field(devices[0]["password"]) == "pw"

    def test_vanished_device_becomes_stale(self, netbox_list, monkeypatch):
        from modules.inventory import get_stale_devices, refresh_list

        refresh_list("NetBoxList")
        monkeypatch.setattr(netbox_source, "fetch_netbox_devices",
                            lambda f: {"ok": True,
                                       "devices": [_raw("R1", "203.0.113.1", nb_id=1)]})
        refresh_list("NetBoxList")

        stale = get_stale_devices("NetBoxList")
        assert "203.0.113.2" in stale
        assert stale["203.0.113.2"]["hostname"] == "R2"
