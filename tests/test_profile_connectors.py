"""P.9: the monitoring profile is DERIVED FROM THE CONNECTORS, and the fleet is
the cross-check (the operator, 2026-09-30: a proposal built from what the
fleet already agrees on is circular, and a network the tool has never seen has
nothing to agree on).

On `test_profile_apply`'s lab (r2's REAL config and intent, r6 without SNMP).
The connector values are the host's, measured read-only the same day:
syslog_host, the NTP server and the trap host are the NMAS's 10.255.1.10,
Telegraf listens at 10.255.1.10:57000 (grpc), and snmp_exporter's auths are
`public_v1` and `public_v2` (the auth block below is in the host file's shape:
community, security_level, auth_protocol, priv_protocol, version).
"""
import json

import pytest

from tests.test_profile_apply import lab  # noqa: F401  (the fixture)

HOST = "10.255.1.10"


def _exporter(tmp_path, community, auth="public_v2", version=2):
    p = tmp_path / "snmp.yml"
    p.write_text("modules:\n  if_mib:\n    walk:\n    - 1.3.6.1.2.1.2\n"
                 "auths:\n"
                 "  public_v1:\n    community: other\n    security_level: noAuthNoPriv\n"
                 "    auth_protocol: MD5\n    priv_protocol: DES\n    version: 1\n"
                 f"  {auth}:\n    community: {community}\n    security_level: noAuthNoPriv\n"
                 f"    auth_protocol: MD5\n    priv_protocol: DES\n    version: {version}\n")
    return str(p)


PLANTED = "r2-own-community-7731"


def _plant_r2_community():
    """r2's own stored community as a value no word contains (the fixture's
    is a common word, so its absence from a response would prove nothing)."""
    from modules.credentials import set_template_secret, template_secret_key
    set_template_secret(template_secret_key("Lab", "r2", "snmp_community_ro"), PLANTED)


def _r2_community():
    from modules.credentials import get_template_secret, template_secret_key
    return get_template_secret(template_secret_key("Lab", "r2", "snmp_community_ro"))


def _connectors(lab, tmp_path, community=None):  # noqa: F811
    lab["settings"].update({
        # The lab fakes get_setting with a dict, so every key the real one would
        # take from its defaults is given here, at the host's values.
        "loki_url": "http://loki.invalid:3100", "syslog_host": HOST,
        "syslog_trap_level": "notifications", "syslog_origin_id": "hostname",
        "syslog_source_interface": "Loopback0", "syslog_heartbeat_seconds": 300,
        "ntp_servers": [HOST], "telemetry_receiver": f"{HOST}:57000",
        "snmp_trap_host": HOST, "snmp_exporter_auth": "public_v2",
        "snmp_exporter_config": _exporter(tmp_path, community or _r2_community())})


def _section(p, name):
    return next(s for s in p["sections"] if s["section"] == name)


def _strip(lab, host, keys):  # noqa: F811
    """*host*'s committed intent without the monitoring sections: a device
    nobody configured for monitoring."""
    from modules.nsot import hostvars
    from modules.nsot.repo import save_host_vars
    hv = hostvars.read_committed(lab["repo"], host)
    for k in keys:
        if k == "logging":
            (hv.get("logging") or {}).pop("syslog", None)
        elif k == "flags":
            hv["flags"] = {f: v for f, v in (hv.get("flags") or {}).items()
                           if f not in ("lldp run", "cdp run")}
        else:
            hv[k] = {} if isinstance(hv.get(k), dict) else []
    hostvars.write_committed(lab["repo"], hv)
    assert save_host_vars("Lab", [host], actor="t", source="extraction")["ok"]


MONITORING = ("snmp", "ntp_servers", "telemetry", "logging", "flags")


class TestANetworkTheToolHasNeverSeen:
    def test_every_section_comes_from_its_connector_with_nothing_to_agree_on(  # noqa: F811
            self, lab, tmp_path):
        from modules.nsot import profile_propose as pp
        _connectors(lab, tmp_path)
        _strip(lab, "r2", MONITORING)
        _strip(lab, "r6", MONITORING)
        p = pp.propose("Lab")
        for name in ("snmp", "syslog", "ntp", "telemetry", "lldp"):
            s = _section(p, name)
            assert s["proposed"] and s["connector"], (name, s.get("why"))
            assert s["holders"] == [] and s["inherit"] == ["r2", "r6"], name
            assert p["doc"]["sections"][name]["source"] == "connector"
        doc = p["doc"]["sections"]
        assert doc["ntp"]["data"] == {"ntp_servers": [HOST]}
        assert doc["syslog"]["data"]["logging"]["syslog"]["hosts"] == [HOST]
        assert doc["syslog"]["data"]["logging"]["syslog"]["heartbeat"] == 300
        assert doc["telemetry"]["platforms"] == ["cisco_iosxe"]
        assert doc["snmp"]["data"]["snmp"]["hosts"][0]["address"] == HOST
        assert p["secrets"] == {"snmp_community_ro": _r2_community()}
        assert not _section(p, "cdp")["proposed"]       # no connector consumes CDP

    def test_without_the_connectors_the_same_network_proposes_nothing(self, lab):  # noqa: F811
        """The control: the circular proposal the operator named."""
        from modules.nsot import profile_propose as pp
        lab["settings"]["prometheus_url"] = ""
        _strip(lab, "r2", MONITORING)
        _strip(lab, "r6", MONITORING)
        p = pp.propose("Lab")
        assert not [s["section"] for s in p["sections"] if s["proposed"]]


class TestTheFleetIsTheCrossCheck:
    def test_a_device_already_matching_is_a_holder(self, lab, tmp_path):  # noqa: F811
        """r2's real telemetry is exactly what Telegraf's setting derives: the
        constants are the fleet's measured subscriptions."""
        from modules.nsot import profile_propose as pp
        _connectors(lab, tmp_path)
        p = pp.propose("Lab")
        t = _section(p, "telemetry")
        # r6 is r2's config without SNMP and discovery, so it streams too.
        assert t["connector"] and t["holders"] == ["r2", "r6"] and "differs" not in t
        snmp = _section(p, "snmp")
        assert snmp["holders"] == ["r2"] and snmp["inherit"] == ["r6"]
        assert not snmp["secret_differs"]

    def test_a_device_configured_differently_is_named_with_what_it_keeps(  # noqa: F811
            self, lab, tmp_path):
        """r2's real syslog block predates P.1 (trap critical, no heartbeat):
        what the connectors need differs, and r2 is named, keeping its own."""
        from modules.nsot import profile_propose as pp
        _connectors(lab, tmp_path)
        p = pp.propose("Lab")
        sl = _section(p, "syslog")
        assert sl["proposed"] and "r2" in sl["differs"]
        keeps = " ".join(sl["differs"]["r2"]["keeps"])
        assert "critical" in keeps
        lab["settings"]["snmp_trap_host"] = "192.0.2.50"
        snmp = _section(pp.propose("Lab"), "snmp")
        assert snmp["proposed"] and "r2" in snmp["differs"]
        assert any(HOST in k for k in snmp["differs"]["r2"]["keeps"])

    def test_a_differing_stored_secret_is_named_never_shown(self, lab, tmp_path):  # noqa: F811
        from modules.nsot import profile_propose as pp
        _plant_r2_community()
        _connectors(lab, tmp_path, community="exporter-community-0451")
        p = pp.propose("Lab")
        snmp = _section(p, "snmp")
        assert snmp["proposed"]
        assert snmp["secret_differs"] == [{"device": "r2", "ref": "snmp_community_ro"}]
        text = json.dumps(pp.public(p))
        assert "exporter-community-0451" not in text and PLANTED not in text

    def test_an_empty_connector_leaves_the_section_to_the_fleet_and_says_so(  # noqa: F811
            self, lab, tmp_path):
        from modules.nsot import profile_propose as pp
        _connectors(lab, tmp_path)
        lab["settings"]["ntp_servers"] = []
        ntp = _section(pp.propose("Lab"), "ntp")
        assert ntp["proposed"] and not ntp.get("connector")
        assert ntp["basis"] == "the fleet's committed intent, because ntp_servers is not configured"


class TestTheExportersCommunity:
    @pytest.mark.parametrize("setup,words", [
        (lambda t: str(t / "absent.yml"), "could not be read"),
        (lambda t: (t / "x.yml").write_text("modules: {}\n") and str(t / "x.yml"), "no auths section"),
        (lambda t: _exporter(t, "c0mm", auth="other_v2"), "no auth module 'public_v2' (it has: other_v2, public_v1)"),
        (lambda t: _exporter(t, "c0mm", version=3), "SNMP version 3"),
    ])
    def test_each_refusal_names_what_is_missing_and_never_the_value(self, tmp_path, setup, words):
        from modules.nsot import profile_propose as pp
        value, why = pp.exporter_community(setup(tmp_path), "public_v2")
        assert value == "" and words in why and "c0mm" not in why

    def test_the_hosts_shape_is_read(self, tmp_path):
        from modules.nsot import profile_propose as pp
        assert pp.exporter_community(_exporter(tmp_path, "c0mm-r3ad"), "public_v2") == ("c0mm-r3ad", "")


class TestCommitAndPreview:
    def test_the_commit_names_the_connectors_and_stores_the_exporters_value(  # noqa: F811
            self, lab, tmp_path):
        from modules.nsot import profile_propose as pp
        from modules.nsot.repo import git
        _connectors(lab, tmp_path, community="exporter-community-0451")
        out = pp.apply("Lab", pp.propose("Lab")["hash"], "op@example.invalid")
        assert out["outcome"] == "committed", out
        assert lab["stored"]["snmp_community_ro"] == "exporter-community-0451"
        subject = git(lab["repo"], "log", "-1", "--format=%s")[1]
        assert "from the connectors (" in subject and "snmp" in subject

    def test_the_preview_draws_the_basis_and_the_cross_check(self, lab, tmp_path):  # noqa: F811
        _plant_r2_community()
        _connectors(lab, tmp_path, community="exporter-community-0451")
        r = lab["client"].post("/templatize/profile/propose/preview", json={"list_name": "Lab"})
        text = r.get_data(as_text=True)
        assert r.status_code == 200, text[:300]
        assert "derived from snmp_exporter" in text
        assert "configured differently from what the connector needs" in text
        assert PLANTED not in text and "exporter-community-0451" not in text
        assert "secret differs from the connector" in text
