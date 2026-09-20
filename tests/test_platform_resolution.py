"""Config dialect vs. Netmiko driver — two questions, two answers.

`device_type` in devices.csv is a Netmiko driver: how to open a session,
handle the prompt, disable paging, save the config. `cisco_ios` is a *correct*
driver for a C8000v running IOS-XE, because the session behaves identically.

Parser selection needs a different answer — which config dialect to parse and
render. A C8000v has `vrf definition` with address families, telemetry
subscriptions and NETCONF settings that a vIOS-L2 does not.

Keying the parser off `device_type` conflates them. The visible symptom is IOS-XE
routers parsing with the IOS parser. The invisible one is worse: the apparent fix
is to change `device_type` to `cisco_xe`, which alters **transport** behaviour to
influence a **parsing** decision.
"""

import csv
import os

import pytest

from modules.nsot.platform import (
    DEFAULT_PLATFORM, describe, netmiko_type_for_device, platform_for_device,
)


class TestExplicitPlatformWins:
    def test_platform_overrides_a_conflicting_device_type(self):
        """The whole point: a C8000v keeps cisco_ios as its driver."""
        device = {"hostname": "r1", "device_type": "cisco_ios",
                  "platform": "cisco_iosxe"}
        assert platform_for_device(device) == "cisco_iosxe"
        assert netmiko_type_for_device(device) == "cisco_ios"

    def test_transport_is_untouched_by_the_platform_column(self):
        device = {"hostname": "r1", "device_type": "cisco_ios",
                  "platform": "cisco_iosxe"}
        assert netmiko_type_for_device(device) == "cisco_ios"

    def test_netbox_slug_form_is_accepted(self):
        assert platform_for_device({"platform": "cisco-ios-xe"}) == "cisco_iosxe"

    def test_source_is_reported_as_explicit(self):
        assert describe({"device_type": "cisco_ios", "platform": "cisco_iosxe"}
                        )["platform_source"] == "explicit"


class TestBackwardCompatibility:
    """Lists written before the column existed must keep working."""

    def test_blank_platform_still_resolves(self):
        assert platform_for_device({"hostname": "s1", "device_type": "cisco_ios"}) \
            == "cisco_ios"

    def test_missing_platform_key_still_resolves(self):
        assert platform_for_device({"device_type": "cisco_ios"}) == "cisco_ios"

    def test_empty_string_is_treated_as_absent(self):
        assert platform_for_device({"device_type": "cisco_xe", "platform": "  "}) \
            == "cisco_iosxe"

    def test_nothing_at_all_defaults(self):
        assert platform_for_device({}) == DEFAULT_PLATFORM

    def test_unknown_driver_defaults_without_raising(self):
        assert platform_for_device({"device_type": "arista_eos"}) == DEFAULT_PLATFORM

    def test_derivation_is_reported_as_a_guess(self):
        assert "derived" in describe({"device_type": "cisco_ios"})["platform_source"]


class TestDerivation:
    @pytest.mark.parametrize("driver,dialect", [
        ("cisco_ios", "cisco_ios"),
        ("cisco_xe", "cisco_iosxe"),
        ("cisco_xe_ssh", "cisco_iosxe"),
        ("cisco_iosxe", "cisco_iosxe"),
    ])
    def test_known_drivers_derive(self, driver, dialect):
        assert platform_for_device({"device_type": driver}) == dialect


class TestNetboxSourcedDevices:
    def test_netbox_slug_is_used_when_no_explicit_platform(self):
        device = {"device_type": "cisco_ios", "_platform": "cisco-ios-xe"}
        assert platform_for_device(device) == "cisco_iosxe"
        assert describe(device)["platform_source"] == "netbox"

    def test_explicit_still_beats_netbox(self):
        device = {"device_type": "cisco_ios", "_platform": "cisco-ios-xe",
                  "platform": "cisco_ios"}
        assert platform_for_device(device) == "cisco_ios"

    def test_unknown_slug_falls_through_to_the_platform_map(self, monkeypatch):
        monkeypatch.setattr(
            "modules.settings_schema.get_setting",
            lambda k, d=None: {"exotic-os": {"template_dir": "exotic-os"}}
            if k == "platform_map" else d)
        assert platform_for_device({"_platform": "exotic-os"}) == "exotic_os"


class TestParserSelectionUsesDialect:
    """The behaviour the whole separation exists to produce."""

    def test_iosxe_dialect_selects_the_iosxe_parser(self):
        from modules.nsot.parsers import CiscoIosXeParser, get_parser
        device = {"device_type": "cisco_ios", "platform": "cisco_iosxe"}
        assert isinstance(get_parser(platform_for_device(device)), CiscoIosXeParser)

    def test_ios_dialect_selects_the_ios_parser(self):
        from modules.nsot.parsers import CiscoIosParser, get_parser
        device = {"device_type": "cisco_ios", "platform": "cisco_ios"}
        assert isinstance(get_parser(platform_for_device(device)), CiscoIosParser)

    def test_a_c8000v_config_models_fully_under_the_right_dialect(self):
        """With device_type alone, a router's VRF and telemetry go unmodelled."""
        from modules.nsot.parsers import get_parser

        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "configs",
                               "fleet", "r1.cfg")
        with open(fixture, encoding="utf-8") as fh:
            config = fh.read()

        wrong = get_parser(platform_for_device({"device_type": "cisco_ios"})).parse(config)
        right = get_parser(platform_for_device(
            {"device_type": "cisco_ios", "platform": "cisco_iosxe"})).parse(config)

        assert len(right["unmodeled"]) < len(wrong["unmodeled"]), (
            "the IOS-XE dialect did not model more of a C8000v config than the "
            "IOS dialect")
        assert right["vrfs"], "vrf definition was not modelled"
        assert right["telemetry"], "telemetry subscriptions were not modelled"


class TestCsvSchema:
    def test_platform_and_device_uid_are_columns(self):
        from modules.device import DEVICE_CSV_FIELDS
        assert "platform" in DEVICE_CSV_FIELDS
        assert "device_uid" in DEVICE_CSV_FIELDS

    def test_device_type_is_retained(self):
        """The driver column does not go away — it answers a real question."""
        from modules.device import DEVICE_CSV_FIELDS
        assert "device_type" in DEVICE_CSV_FIELDS

    def test_field_list_is_defined_once(self):
        """Three copies is how they drift; two of them dropped the new columns."""
        import modules.device as device_module

        with open(device_module.__file__, encoding="utf-8") as fh:
            source = fh.read()
        assert source.count('"hostname", "device_type", "ip"') == 1

    def test_a_legacy_csv_loads_and_resolves(self, tmp_path):
        """Seven columns, no platform — the shape on a real NMAS today."""
        path = tmp_path / "devices.csv"
        path.write_text(
            "hostname,device_type,ip,username,password,secret,role\n"
            "r1,cisco_ios,203.0.113.11,admin,x,y,router\n", encoding="utf-8")
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert platform_for_device(rows[0]) == "cisco_ios"
        assert "platform" not in rows[0]
