"""tests/test_pipeline_builder.py

Unit tests for pipeline_builder.py.

All tests run without network access, Jenkins, or real devices.
Golden-config scanning is tested via synthetic config text passed
through monkey-patched helper functions.

Run with:  python -m pytest tests/test_pipeline_builder.py -v
"""

import json
import re
import pytest

from modules.pipeline_builder import (
    NetworkFunction,
    detect_network_functions,
    _build_pipeline_xml,
    _FUNCTION_SCHEDULE,
    _DEFAULT_SCHEDULE,
)
from modules.check_runner import (
    CHECKS,
    check_ospf, check_bgp, check_eigrp, check_mpls,
    _device_params_for,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_check_devices(*ips: str) -> list[dict]:
    return [
        {"hostname": f"R{i + 1}", "ip": ip,
         "username": "admin", "password": "cisco"}
        for i, ip in enumerate(ips)
    ]


def _make_function(ftype: str, ips: list[str], params_by_ip: dict = None) -> NetworkFunction:
    return NetworkFunction(
        function_type=ftype,
        device_ips=ips,
        params_by_ip=params_by_ip or {ip: {} for ip in ips},
    )


# ---------------------------------------------------------------------------
# NetworkFunction helpers
# ---------------------------------------------------------------------------

class TestNetworkFunction:

    def test_job_name_stable(self):
        nf = _make_function("ospf", ["10.0.0.1"])
        assert nf.job_name("mylist") == "nmas-mylist-ospf"

    def test_job_name_slugified(self):
        nf = _make_function("bgp", ["10.0.0.1"])
        assert nf.job_name("My List 1") == "nmas-my-list-1-bgp"

    def test_job_name_includes_function_type(self):
        for ftype in ("ospf", "bgp", "mpls", "eigrp", "nat", "snmp"):
            nf = _make_function(ftype, [])
            assert ftype in nf.job_name("testlist")

    def test_schedule_known_function(self):
        nf = _make_function("ospf", [])
        assert nf.schedule() == _FUNCTION_SCHEDULE["ospf"]

    def test_schedule_unknown_function_returns_default(self):
        nf = _make_function("unknown_proto", [])
        assert nf.schedule() == _DEFAULT_SCHEDULE

    def test_schedule_bgp_is_frequent(self):
        # BGP should be checked at least every 30 minutes.
        nf = _make_function("bgp", [])
        assert "30" in nf.schedule() or "H/30" in nf.schedule()


# ---------------------------------------------------------------------------
# Function detection from (synthetic) golden configs
# ---------------------------------------------------------------------------

class TestDetectNetworkFunctions:
    """detect_network_functions reads golden configs via ai_assistant helpers.
    We patch those helpers to inject synthetic config text."""

    _OSPF_CFG = """\
router ospf 1
 router-id 1.1.1.1
 network 10.0.0.0 0.0.0.255 area 0
!
interface GigabitEthernet0/0
 ip address 10.0.0.1 255.255.255.0
!
interface GigabitEthernet0/1
 ip address 192.168.1.1 255.255.255.0
"""

    _BGP_CFG = """\
router bgp 65001
 bgp router-id 2.2.2.2
 neighbor 10.0.0.2 remote-as 65002
 neighbor 10.0.0.3 remote-as 65003
 network 192.168.0.0
!
"""

    _MPLS_CFG = """\
mpls ldp router-id Loopback0 force
interface GigabitEthernet0/0
 mpls ip
!
"""

    _MULTI_CFG = _OSPF_CFG + _BGP_CFG + _MPLS_CFG

    def _patch_and_detect(self, monkeypatch, cfg_by_ip: dict) -> list[NetworkFunction]:
        """Patch ai_assistant helpers and run detection."""
        import modules.pipeline_builder as pb

        golden_list = [
            {"device_ip": ip, "hostname": f"R-{ip.replace('.', '-')}"}
            for ip in cfg_by_ip
        ]
        monkeypatch.setattr(
            "modules.pipeline_builder.detect_network_functions.__module__",
            "modules.pipeline_builder",
            raising=False,
        )

        # Patch the imports inside detect_network_functions
        import types, sys
        fake_ai = types.ModuleType("modules.ai_assistant")
        fake_ai._list_golden_configs   = lambda: golden_list
        fake_ai._load_golden_config_file = lambda ip: cfg_by_ip.get(ip, "")
        sys.modules["modules.ai_assistant"] = fake_ai

        check_devices = _make_check_devices(*cfg_by_ip.keys())
        try:
            return detect_network_functions(check_devices)
        finally:
            # Restore original module if it was there before
            sys.modules.pop("modules.ai_assistant", None)

    def test_ospf_detected(self, monkeypatch):
        fns = self._patch_and_detect(monkeypatch, {"10.0.0.1": self._OSPF_CFG})
        ftypes = {f.function_type for f in fns}
        assert "ospf" in ftypes

    def test_ospf_process_id_extracted(self, monkeypatch):
        fns = self._patch_and_detect(monkeypatch, {"10.0.0.1": self._OSPF_CFG})
        ospf = next(f for f in fns if f.function_type == "ospf")
        assert ospf.params_by_ip["10.0.0.1"]["process_id"] == "1"

    def test_ospf_router_id_extracted(self, monkeypatch):
        fns = self._patch_and_detect(monkeypatch, {"10.0.0.1": self._OSPF_CFG})
        ospf = next(f for f in fns if f.function_type == "ospf")
        assert ospf.params_by_ip["10.0.0.1"]["router_id"] == "1.1.1.1"

    def test_bgp_detected(self, monkeypatch):
        fns = self._patch_and_detect(monkeypatch, {"10.0.0.2": self._BGP_CFG})
        ftypes = {f.function_type for f in fns}
        assert "bgp" in ftypes

    def test_bgp_as_extracted(self, monkeypatch):
        fns = self._patch_and_detect(monkeypatch, {"10.0.0.2": self._BGP_CFG})
        bgp = next(f for f in fns if f.function_type == "bgp")
        assert bgp.params_by_ip["10.0.0.2"]["local_as"] == "65001"

    def test_mpls_detected(self, monkeypatch):
        fns = self._patch_and_detect(monkeypatch, {"10.0.0.3": self._MPLS_CFG})
        ftypes = {f.function_type for f in fns}
        assert "mpls" in ftypes

    def test_multi_function_device(self, monkeypatch):
        fns = self._patch_and_detect(monkeypatch, {"10.0.0.1": self._MULTI_CFG})
        ftypes = {f.function_type for f in fns}
        assert "ospf" in ftypes
        assert "bgp"  in ftypes
        assert "mpls" in ftypes

    def test_empty_config_detects_nothing(self, monkeypatch):
        fns = self._patch_and_detect(monkeypatch, {"10.0.0.1": "! empty\n"})
        assert fns == []

    def test_device_without_credentials_excluded(self, monkeypatch):
        """A device in golden configs but not in check_devices must be skipped."""
        import types, sys
        fake_ai = types.ModuleType("modules.ai_assistant")
        fake_ai._list_golden_configs    = lambda: [{"device_ip": "10.0.0.99", "hostname": "X"}]
        fake_ai._load_golden_config_file = lambda ip: self._OSPF_CFG
        sys.modules["modules.ai_assistant"] = fake_ai
        try:
            fns = detect_network_functions([])  # empty check_devices
            assert fns == []
        finally:
            sys.modules.pop("modules.ai_assistant", None)

    def test_multi_device_same_function(self, monkeypatch):
        """Two devices both running OSPF → one NetworkFunction with both IPs."""
        fns = self._patch_and_detect(monkeypatch, {
            "10.0.0.1": self._OSPF_CFG,
            "10.0.0.2": self._OSPF_CFG,
        })
        ospf = next(f for f in fns if f.function_type == "ospf")
        assert "10.0.0.1" in ospf.device_ips
        assert "10.0.0.2" in ospf.device_ips


# ---------------------------------------------------------------------------
# Check script generation
# ---------------------------------------------------------------------------

class TestCheckFunctions:
    """check_runner.py exposes real Python functions — test them directly."""

    def _fake_conn(self, responses: dict):
        """Return a mock Netmiko connection whose send_command matches by longest prefix first."""
        class FakeConn:
            def send_command(self_, cmd):
                # Sort by key length descending so longer (more specific) keys
                # win over shorter ones (e.g. "show ip ospf 1 neighbor" before "show ip ospf 1").
                for prefix, resp in sorted(responses.items(), key=lambda x: -len(x[0])):
                    if cmd.startswith(prefix):
                        return resp
                return ""
        return FakeConn()

    def test_check_registry_covers_all_expected_types(self):
        for ftype in ("ospf", "bgp", "eigrp", "mpls", "tunnel", "nat",
                      "snmp", "staticroute", "loopback", "interface"):
            assert ftype in CHECKS, f"'{ftype}' missing from CHECKS"

    def test_check_functions_are_callable(self):
        for fn in CHECKS.values():
            assert callable(fn)

    def test_ospf_pass(self):
        conn = self._fake_conn({
            "show ip ospf 1":          "OSPF Router with ID (1.1.1.1)",
            "show ip ospf 1 neighbor": "10.0.0.2  FULL/DR",
        })
        assert check_ospf(conn, {"hostname": "R1", "ospf_pid": "1"}) is None

    def test_ospf_fail_not_running(self):
        conn = self._fake_conn({"show ip ospf": "% OSPF not enabled"})
        result = check_ospf(conn, {"hostname": "R1", "ospf_pid": "1"})
        assert result is not None
        assert "not running" in result.lower()

    def test_ospf_fail_no_full_neighbors(self):
        conn = self._fake_conn({
            "show ip ospf 1":          "OSPF Router with ID (1.1.1.1)",
            "show ip ospf 1 neighbor": "Neighbor ID  Pri  State\n10.0.0.2  1  INIT/",
        })
        result = check_ospf(conn, {"hostname": "R1", "ospf_pid": "1"})
        assert result is not None
        assert "FULL" in result

    def test_bgp_pass(self):
        # Established peer row ends with a numeric prefix count (last column).
        conn = self._fake_conn({
            "show ip bgp summary": (
                "BGP router identifier 1.1.1.1, local AS number 65001\n"
                "\n"
                "Neighbor        V  AS     MsgRcvd MsgSent TblVer InQ OutQ Up/Down  State/PfxRcd\n"
                "10.0.0.2        4  65002  100     200     10     0   0   5w2d     42\n"
            ),
        })
        assert check_bgp(conn, {"hostname": "R1"}) is None

    def test_bgp_fail_not_running(self):
        conn = self._fake_conn({"show ip bgp summary": "% BGP not enabled"})
        result = check_bgp(conn, {"hostname": "R1"})
        assert result is not None

    def test_eigrp_pass(self):
        conn = self._fake_conn({
            "show ip eigrp neighbors": "H  Address  Interface  Hold  ...\n0  10.0.0.2  Gi0/0  10",
        })
        assert check_eigrp(conn, {"hostname": "R1", "eigrp_as": "1"}) is None

    def test_eigrp_fail_no_neighbors(self):
        conn = self._fake_conn({"show ip eigrp neighbors": ""})
        result = check_eigrp(conn, {"hostname": "R1", "eigrp_as": "1"})
        assert result is not None

    def test_check_fn_returns_none_on_pass(self):
        """Every check function must return None (not "") on pass."""
        conn = self._fake_conn({
            "show ip bgp summary": (
                "BGP router identifier 1.1.1.1\n"
                "10.0.0.2  4  65002  0  0  0  0  0  00:01:23  5\n"  # ends in numeric prefix count
            ),
        })
        result = check_bgp(conn, {"hostname": "R1"})
        assert result is None


class TestDeviceParamsExtraction:
    """_device_params_for extracts per-device params from golden config text."""

    _OSPF_CFG = "router ospf 42\n router-id 5.5.5.5\n network 10.0.0.0 0.0.0.255 area 0\n"
    _BGP_CFG  = "router bgp 65100\n neighbor 10.0.0.2 remote-as 65200\n"

    def test_ospf_pid_extracted(self):
        p = _device_params_for("ospf", self._OSPF_CFG)
        assert p["ospf_pid"] == "42"

    def test_ospf_router_id_extracted(self):
        p = _device_params_for("ospf", self._OSPF_CFG)
        assert p["router_id"] == "5.5.5.5"

    def test_bgp_as_extracted(self):
        p = _device_params_for("bgp", self._BGP_CFG)
        assert p["bgp_as"] == "65100"

    def test_unknown_function_returns_empty(self):
        p = _device_params_for("unknown_proto", "router ospf 1\n")
        assert p == {}

    def test_static_routes_extracted(self):
        cfg = "ip route 192.168.0.0 255.255.255.0 10.0.0.1\nip route 10.0.0.0 255.0.0.0 Null0\n"
        p   = _device_params_for("staticroute", cfg)
        assert len(p["static_routes"]) == 2
        assert p["static_routes"][0]["prefix"] == "192.168.0.0"

    def test_loopbacks_extracted(self):
        cfg = "interface Loopback0\n ip address 1.1.1.1 255.255.255.255\n"
        p   = _device_params_for("loopback", cfg)
        assert any(lb["number"] == "0" for lb in p["loopbacks"])

    def test_tunnel_ids_extracted(self):
        cfg = "interface Tunnel1\n tunnel mode gre ip\ninterface Tunnel2\n tunnel mode gre ip\n"
        p   = _device_params_for("tunnel", cfg)
        assert "1" in p["tunnel_ids"]
        assert "2" in p["tunnel_ids"]


# ---------------------------------------------------------------------------
# Pipeline XML generation
# ---------------------------------------------------------------------------

class TestBuildPipelineXml:

    def _xml(self, job="nmas-list-ospf", ftype="ospf", slug="mylist",
              cron="H/30 * * * *", desc=""):
        return _build_pipeline_xml(job, ftype, slug, cron, description=desc)

    def test_xml_is_valid_xml(self):
        import xml.etree.ElementTree as ET
        xml  = self._xml()
        body = re.sub(r"<\?xml[^?]*\?>", "", xml, count=1).strip()
        ET.fromstring(body)

    def test_cron_schedule_present(self):
        xml = self._xml(cron="H/30 * * * *")
        assert "H/30 * * * *" in xml
        assert "TimerTrigger" in xml

    def test_no_schedule_omits_trigger(self):
        xml = self._xml(cron="")
        assert "TimerTrigger" not in xml

    def test_calls_check_runner_not_check_py(self):
        xml = self._xml(ftype="ospf", slug="testlist")
        assert "check_runner.py" in xml
        assert "writeFile" not in xml

    def test_function_type_and_list_slug_in_command(self):
        xml = self._xml(ftype="bgp", slug="csci5160final")
        assert "--function bgp" in xml
        assert "--list-slug csci5160final" in xml

    def test_flow_definition_root(self):
        assert "<flow-definition" in self._xml()

    def test_sandbox_true(self):
        assert "<sandbox>true</sandbox>" in self._xml()

    def test_description_included(self):
        xml = self._xml(desc="OSPF checks for list-1")
        assert "OSPF checks for list-1" in xml

    def test_no_groovy_string_escaping_artefacts(self):
        # The old approach embedded Python source as a Groovy string — verify
        # the new pipeline XML contains no triple-quote escape sequences.
        xml = self._xml()
        assert "\\\\'" not in xml
        assert "\\'''" not in xml


# ---------------------------------------------------------------------------
# Stable naming — same function, same list → same job name always
# ---------------------------------------------------------------------------

class TestStableNaming:

    def test_same_inputs_same_name(self):
        nf1 = _make_function("ospf", ["10.0.0.1"])
        nf2 = _make_function("ospf", ["10.0.0.1"])
        assert nf1.job_name("mylist") == nf2.job_name("mylist")

    def test_different_function_different_name(self):
        assert (
            _make_function("ospf", []).job_name("l")
            != _make_function("bgp",  []).job_name("l")
        )

    def test_different_list_different_name(self):
        nf = _make_function("ospf", [])
        assert nf.job_name("list-a") != nf.job_name("list-b")

    def test_name_never_contains_timestamp(self):
        import time
        nf   = _make_function("ospf", [])
        name = nf.job_name("mylist")
        # timestamps are 10-digit numbers; job name must not contain them
        assert not re.search(r"\d{10}", name)
