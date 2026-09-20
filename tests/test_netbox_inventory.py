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
            "role_map": {"router": "router"},
        }.get(key, default))
        devices, skipped, warnings = netbox_source.adapt_devices([_raw(platform="arista-eos")])
        assert skipped == []
        assert devices[0]["device_type"] == "cisco_ios"
        assert warnings[0]["field"] == "platform"

    def test_empty_default_means_skip(self, creds):
        _d, skipped, _w = netbox_source.adapt_devices([_raw(platform="arista-eos")])
        assert skipped and skipped[0]["field"] == "platform"


class TestRoleMapping:
    """Amendment 3: roles drive topology icons and must be valid or blank."""

    def test_mapped_role(self):
        assert netbox_source.map_role("core-router") == "router"
        assert netbox_source.map_role("access-switch") == "switch"
        assert netbox_source.map_role("firewall") == "firewall"

    def test_unmapped_role_is_blank_for_inference(self, creds):
        """Blank lets topology._infer_role(hostname) apply, as for a local list."""
        assert netbox_source.map_role("spine") == ""
        devices, _s, warnings = netbox_source.adapt_devices([_raw(role="spine")])
        assert devices[0]["role"] == ""
        assert warnings[0]["field"] == "role"

    def test_blank_role_still_yields_a_topology_icon(self, creds):
        """A blank role must not break topology, which falls back to the hostname."""
        from modules.topology import _infer_role
        devices, _s, _w = netbox_source.adapt_devices([_raw(name="SW-1", role="spine")])
        assert _infer_role(devices[0]["hostname"]) in ("router", "switch", "firewall")

    def test_invalid_map_value_is_rejected(self, monkeypatch):
        monkeypatch.setattr(netbox_source, "get_setting",
                            lambda key, default=None: {"role_map": {"x": "gateway"}}.get(key, default))
        assert netbox_source.map_role("x") == ""


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


class TestDispatchDoesNoNetworkIO:
    """Amendment 1: load_saved_devices sits on ~79 call sites."""

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

    def test_ai_reports_stale_rather_than_not_found(self, stale_list, monkeypatch):
        import modules.ai_assistant as ai
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: stale_list)
        msg = ai._device_unavailable_message("203.0.113.9")
        assert "no longer in NetBox" in msg
        assert "not found" not in msg

    def test_approval_executor_refuses(self, stale_list, monkeypatch):
        from modules import approval_queue
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: stale_list)
        result = approval_queue._execute({"id": "x", "action_type": "update_golden_config",
                                          "device_ip": "203.0.113.9"})
        assert "no longer in NetBox" in result["error"]


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
        from modules.device import _refuse_if_netbox_sourced
        _refuse_if_netbox_sourced(str(netbox_list / "locallist" / "devices.csv"), "add")

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
