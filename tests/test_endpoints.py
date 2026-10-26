"""The endpoint layer (PHASE8_PLAN 15.15; C1772; modules/endpoints.py, modules/readers/endpoints.py,
modules/lease_sources.py), on the real captures of s1 and r1 (tests/fixtures/endpoints/, read
2026-10-26 through Mercury's read path) and Kea's leases as the DHCP reader stored them.

- The platform pack: every entry's command is one the read-only allowlist takes whole, and its
  pattern reads the real captures (s1's five trunk-learned MACs, its ARP's hosts, r1's IPv6
  neighbours).
- Location: a MAC learned on a trunk or an uplink locates nothing; one learned on an access port
  locates its endpoint there, named by its lease and addressed by ARP; a location not seen in
  this read is kept with its last-seen, and dropped after the retention.
- The reader: a pack command the allowlist refuses is never sent, and said; a device that could
  not be read is said, never empty; the value per network joins the reads, the leases and the
  last value.
"""
import json
import os

import pytest

from modules import endpoints as E
from modules.readers import endpoints as R

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "endpoints")


def _cap(host, command):
    with open(os.path.join(FIX, f"{host}__{command.replace(' ', '_')}.txt"),
              encoding="utf-8") as fh:
        return fh.read()


def _reads(host, dialect, extra_mac_lines=""):
    return {"mac_table": E.parse(dialect, "mac_table",
                                 _cap(host, "show mac address-table dynamic") + extra_mac_lines),
            "arp": E.parse(dialect, "arp", _cap(host, "show ip arp")),
            "ipv6_neighbors": E.parse(dialect, "ipv6_neighbors",
                                      _cap(host, "show ipv6 neighbors"))}


with open(os.path.join(FIX, "leases.json"), encoding="utf-8") as fh:
    LEASES = json.load(fh)
#: s1's ports that locate nothing, from its committed intent and neighbours: the trunk to s2,
#: the uplink to r1.
S1_PORTS = {"s1": {"trunks": {"GigabitEthernet0/3"}, "uplinks": {"GigabitEthernet0/2"}}}
#: h1 heard on its access port: the one line an active host adds to s1's table.
H1_ON_GI10 = "\n  10    aac1.ab99.f6e2    DYNAMIC     Gi1/0\n"


# ── the pack ─────────────────────────────────────────────────────────────────

def test_every_pack_command_is_a_read_the_allowlist_takes_whole():
    from modules import readonly_commands as rc
    packs = E.entries()
    assert set(packs) == {"cisco_ios", "cisco_iosxe"}
    for dialect, reads in packs.items():
        assert set(reads) == set(E.READS), dialect
        for read, entry in reads.items():
            assert rc.refusal(entry["command"]) == "", (dialect, read)


def test_the_pack_reads_the_real_captures():
    s1 = _reads("s1", "cisco_ios")
    assert [(r["vlan"], r["mac"], r["port"]) for r in s1["mac_table"]] == [
        ("10", "0c:00:6f:31:80:0a", "Gi0/3"), ("20", "00:00:5e:00:01:14", "Gi0/3"),
        ("20", "00:00:5e:00:02:14", "Gi0/3"), ("20", "0c:00:6f:31:80:14", "Gi0/3"),
        ("30", "0c:00:6f:31:80:1e", "Gi0/3")]
    arp = {r["address"]: (r["mac"], r["interface"]) for r in s1["arp"]}
    assert len(s1["arp"]) == 12
    assert arp["10.10.10.100"] == ("aa:c1:ab:99:f6:e2", "Vlan10")
    assert s1["ipv6_neighbors"] == []
    r1 = _reads("r1", "cisco_iosxe")
    assert r1["mac_table"] == [] and len(r1["arp"]) == 8 and len(r1["ipv6_neighbors"]) == 4


def test_a_dialect_with_no_entry_reads_nothing():
    assert E.parse("fortinet", "arp", _cap("s1", "show ip arp")) == []


# ── location ─────────────────────────────────────────────────────────────────

def test_trunk_learned_macs_locate_nothing_and_a_host_is_named_by_its_lease():
    got = E.locate({"s1": _reads("s1", "cisco_ios")}, LEASES, S1_PORTS, now=1000)
    assert got["ignored"] == 5, "every MAC s1 learned on its trunk is ignored for location"
    (h1,) = E.find(got["endpoints"], "h1")
    assert h1["device"] == "" and h1["interface"] == "", "not located: idle, its MAC aged out"
    assert "10.10.10.100" in h1["addresses"] and "s1's ARP" in h1["sources"]
    assert "Kea's lease" not in h1["sources"] and "a DHCP lease" in h1["sources"]


def test_a_host_heard_on_its_access_port_is_located_there():
    got = E.locate({"s1": _reads("s1", "cisco_ios", H1_ON_GI10)}, LEASES, S1_PORTS, now=1000)
    (h1,) = E.find(got["endpoints"], "h1")
    assert (h1["device"], h1["interface"], h1["vlan"]) == ("s1", "GigabitEthernet1/0", "10")
    assert h1["last_seen"] == "1970-01-01T00:16:40Z" and h1["hostname"] == "h1"
    assert E.find(got["endpoints"], "10.10.10.100") == [h1]
    assert E.find(got["endpoints"], "aac1.ab99.f6e2") == [h1]


def test_a_mac_on_an_uplink_locates_nothing():
    uplink = "\n  10    aac1.ab99.f6e2    DYNAMIC     Gi0/2\n"
    got = E.locate({"s1": _reads("s1", "cisco_ios", uplink)}, LEASES, S1_PORTS, now=1000)
    (h1,) = E.find(got["endpoints"], "h1")
    assert h1["device"] == "" and got["ignored"] == 6


def test_a_location_not_seen_now_is_kept_with_its_age_then_dropped():
    first = E.locate({"s1": _reads("s1", "cisco_ios", H1_ON_GI10)}, LEASES, S1_PORTS, now=1000)
    later = E.locate({"s1": _reads("s1", "cisco_ios")}, LEASES, S1_PORTS,
                     previous=first["endpoints"], now=1000 + 3600)
    (h1,) = E.find(later["endpoints"], "h1")
    assert (h1["device"], h1["interface"]) == ("s1", "GigabitEthernet1/0")
    assert h1["last_seen"] == "1970-01-01T00:16:40Z", "its last-seen, never now"
    gone = E.locate({"s1": _reads("s1", "cisco_ios")}, LEASES, S1_PORTS,
                    previous=first["endpoints"], now=1000 + E.RETAIN_SECONDS + 1)
    (h1,) = E.find(gone["endpoints"], "h1")
    assert h1["device"] == "", "past the retention, its location is no longer kept"
    assert first["version"] != later["version"] or first["endpoints"] != later["endpoints"]


# ── the reader ───────────────────────────────────────────────────────────────

class _Conn:
    def __init__(self, outputs):
        self.outputs, self.sent = outputs, []

    def enable(self):
        pass

    def send_command(self, command):
        self.sent.append(command)
        return self.outputs.get(command, "")

    def disconnect(self):
        pass


@pytest.fixture
def stored_credential(monkeypatch):
    monkeypatch.setattr("modules.device.open_stored", lambda row: ("pw", ""))
    monkeypatch.setattr("modules.nsot.credential_rotation.enable_secret", lambda row: "")


def test_the_reader_sends_only_the_pack_s_reads(stored_credential):
    outputs = {c: _cap("s1", c) for c in ("show mac address-table dynamic", "show ip arp",
                                          "show ipv6 neighbors")}
    conn = _Conn(outputs)
    got = R.read_device({"hostname": "s1", "device_type": "cisco_ios", "ip": "192.0.2.21"},
                        "cisco_ios", connect=lambda **kw: conn)
    assert conn.sent == ["show mac address-table dynamic", "show ip arp", "show ipv6 neighbors"]
    assert got["error"] == "" and len(got["mac_table"]) == 5 and len(got["arp"]) == 12


def test_a_pack_command_the_allowlist_refuses_is_never_sent(stored_credential, monkeypatch):
    real = E.entry

    def planted(dialect, read):
        return dict(real(dialect, read), command="clear arp-cache") if read == "arp" else \
            real(dialect, read)
    monkeypatch.setattr(E, "entry", planted)
    conn = _Conn({})
    got = R.read_device({"hostname": "s1", "device_type": "cisco_ios", "ip": "192.0.2.21"},
                        "cisco_ios", connect=lambda **kw: conn)
    assert "clear arp-cache" not in conn.sent and "arp" in got["not_supported"]
    assert "the pack's arp command is not a read Mercury may send" in got["error"]


def test_a_device_that_could_not_be_read_is_said(stored_credential):
    def refused(**kw):
        raise OSError("connection refused")
    got = R.read_device({"hostname": "s1", "device_type": "cisco_ios", "ip": "192.0.2.21"},
                        "cisco_ios", connect=refused)
    assert got["error"] == "could not ask: OSError: connection refused" and "mac_table" not in got


def test_the_read_joins_reads_leases_and_the_last_value():
    items = [("Lab", {"hostname": "s1"}, "cisco_ios"), ("Lab", {"hostname": "r1"},
                                                          "cisco_iosxe")]
    reads = {"s1": dict(_reads("s1", "cisco_ios", H1_ON_GI10), error="", not_supported=[]),
             "r1": {"error": "could not ask: OSError: timed out", "not_supported": []}}
    got = R.read(population_fn=lambda: items, read_fn=lambda row, d: reads[row["hostname"]],
                 clock=lambda: 1000, previous_fn=lambda n: [],
                 leases_fn=lambda n: {"leases": LEASES, "said": []},
                 ports_fn=lambda n, hosts: S1_PORTS)
    lab = got["lists"]["Lab"]
    (h1,) = E.find(lab["endpoints"], "h1")
    assert (h1["device"], h1["interface"]) == ("s1", "GigabitEthernet1/0")
    assert lab["devices"]["r1"]["error"] == "could not ask: OSError: timed out"
    assert lab["devices"]["s1"]["read"] == {"mac_table": 6, "arp": 12, "ipv6_neighbors": 0}


def test_the_endpoint_store_states_its_coverage(monkeypatch):
    from modules import reader_job

    def store(devices):
        return lambda name: {"state": "ok", "doc": {"last_good": {"value": {"lists": {"Lab": {
            "endpoints": [], "read_at": "2026-10-26T09:00:00Z", "devices": devices}}}}}}
    monkeypatch.setattr(reader_job, "read_cached", store({"s1": {"error": ""}}))
    assert E.coverage_layer("Lab")["state"] == "present"
    monkeypatch.setattr(reader_job, "read_cached", store({"s1": {"error": ""},
                                                         "s3": {"error": "timed out"}}))
    got = E.coverage_layer("Lab")
    assert got["state"] == "partial" and got["why"] == "s3 could not be read"
    monkeypatch.setattr(reader_job, "read_cached", lambda name: {"state": "absent", "doc": {}})
    assert E.coverage_layer("Lab")["state"] == "not_collected"


def test_kea_s_leases_come_from_the_dhcp_reader_s_stored_value(monkeypatch):
    from modules import lease_sources, reader_job
    monkeypatch.setattr(reader_job, "read_cached", lambda name: {
        "state": "ok", "doc": {"last_good": {"value_at": "2026-10-26T08:21:20Z", "value": {
            "configured": True, "families": {"dhcp4": {"leases": LEASES}}}}}})
    got = lease_sources.kea("Lab")
    assert got["state"] == "read" and [r["hostname"] for r in got["leases"]] == [
        "h1", "h3", "h2", "r6"]
    monkeypatch.setattr(reader_job, "read_cached", lambda name: {"state": "absent", "doc": {}})
    assert lease_sources.kea("Lab")["state"] == "not_configured"
