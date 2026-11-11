"""What Mercury knows of an OpenFlow fabric from NetBox (modules/sdn/known.py; C3013, C3010,
C2950): each switch's NetBox name by its datapath id, and the interfaces a trace's end or a
learnt host can be named by, read once from the network's committed NSOT export.

NetBox is the Lab 9 records (tests/fixtures/nsot_export/lab9_records.json: ovs1 is datapath 3
and ovs2 datapath 4, each OpenFlow port with its number), built and parsed by the real export
(`export.document`, `export.parse`), or committed to the network's repository by the real
operation (tests/test_nsot_export_op.py's `lab`); a case adds, in NetBox's REST shapes, the
device, interface or cable it needs, where it is used.

- **The read:** the committed export, in the network's own repository; a network with no
  repository, and a name no network answers to, are ``absent`` and nothing is created; an
  export that does not verify, or a read that raises, is ``unreadable``, with why.
- **The rows:** an end host's interface, a device's interface that records a MAC or is cabled
  to a switch, and the far end of a switch port's cable that the export holds no interface
  for; each with its switch's datapath id and port number where NetBox records them, IPv4
  beside IPv6. A switch's own interfaces are never an end.
- **A switch's name:** NetBox's by datapath id first, else the description the switch gives of
  itself, never "None"; a switch in neither is said by its datapath id.

Every import of the module is inside its test: the module is new, and each test fails by its
own body where it is missing.
"""
import copy
import os

import pytest

from tests.test_nsot_export_op import _commit, lab  # noqa: F401 (the fixture)
from tests.test_openflow_golden import _records
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"


def _device(name, ident, tags=()):
    return {"id": ident, "name": name, "status": {"value": "active"}, "role": {"slug": "router"},
            "site": {"id": 1, "slug": "lab"}, "custom_fields": {},
            "tags": [{"slug": t} for t in tags]}


def _iface(device, dev_id, name, ident, mac, addresses):
    return {"id": ident, "device": {"id": dev_id, "name": device}, "name": name,
            "type": {"value": "1000base-t"}, "enabled": True, "mgmt_only": False, "tags": [],
            "custom_fields": {}, "primary_mac_address": {"mac_address": mac} if mac else None,
            "ip_addresses": [{"address": a} for a in addresses]}


def _cable(a, b):
    def end(e):
        return [{"object": {"device": {"name": e[0]}, "name": e[1]}}]
    return {"a_terminations": end(a), "b_terminations": end(b),
            "status": {"value": "connected"}, "label": ""}


def _export(records):
    from modules.nsot import export as X
    return X.parse(X.document(NET, records["netbox_version"], records))


def _records_with_ends():
    """The Lab 9 records and three ends: a router (a device, no switch) whose Gi0/0 holds a MAC
    and both families' addresses, cabled to ovs1 eno4; an end host (tagged) on ovs2 eno3; and a
    cable from ovs1 eno3 to a device the export holds no record of."""
    r = copy.deepcopy(_records())
    r["devices"].append(_device("edge-rtr", 90))
    r["hosts"] = [_device("srv-a", 91, tags=("mercury-end-host",))]
    r["interfaces"] += [
        _iface("edge-rtr", 90, "Gi0/0", 900, "0A:00:00:00:00:10",
               ("198.51.100.10/24", "2001:db8::10/64")),
        _iface("edge-rtr", 90, "Loopback0", 901, "", ("198.51.100.200/32",)),
        _iface("srv-a", 91, "eth0", 910, "0a:00:00:00:00:aa",
               ("198.51.100.77/24", "2001:db8::77/64"))]
    r["cables"] += [_cable(("edge-rtr", "Gi0/0"), ("ovs1", "eno4")),
                    _cable(("srv-a", "eth0"), ("ovs2", "eno3")),
                    _cable(("ovs1", "eno3"), ("outside-rtr", "eth9"))]
    return r


# ── the rows ──────────────────────────────────────────────────────────────────────────────────

def test_each_end_is_a_row_with_its_mac_its_addresses_and_its_switch_port():
    from modules.sdn import known

    rows = {(r["name"], r["interface"]): r for r in known.rows_of(_export(_records_with_ends()))}
    assert sorted(rows) == [("edge-rtr", "Gi0/0"), ("outside-rtr", "eth9"), ("srv-a", "eth0")]
    assert rows[("edge-rtr", "Gi0/0")] == {
        "name": "edge-rtr", "kind": "device", "interface": "Gi0/0", "mac": "0a:00:00:00:00:10",
        "ipv4": ["198.51.100.10"], "ipv6": ["2001:db8::10"], "switch": "ovs1",
        "switch_interface": "eno4", "dpid": 3, "port_no": 3}
    host = rows[("srv-a", "eth0")]
    assert (host["kind"], host["mac"], host["dpid"], host["port_no"]) == (
        "end host", "0a:00:00:00:00:aa", 4, 2)
    assert host["ipv4"] == ["198.51.100.77"] and host["ipv6"] == ["2001:db8::77"]
    # A cable's far end outside the export: its name and place, no MAC and no address.
    assert rows[("outside-rtr", "eth9")] == {
        "name": "outside-rtr", "kind": "device", "interface": "eth9", "mac": "", "ipv4": [],
        "ipv6": [], "switch": "ovs1", "switch_interface": "eno3", "dpid": 3, "port_no": 2}


def test_a_switch_s_own_interfaces_and_a_port_with_no_number_are_never_placed():
    from modules.sdn import known

    # The Lab 9 records hold switches and their cables to each other only: the Aristas and
    # the ProCurve, whose datapath id NetBox does not record, are switches by their OpenFlow
    # ports, never an end on the Open vSwitch port their cable reaches.
    plain = known.rows_of(_export(copy.deepcopy(_records())))
    assert plain == []
    r = _records_with_ends()
    for i in r["interfaces"]:
        if i["device"]["name"] == "ovs1" and i["name"] == "eno4":
            i["custom_fields"] = {}
    (row,) = [x for x in known.rows_of(_export(r)) if x["name"] == "edge-rtr"]
    assert (row["dpid"], row["port_no"]) == (3, None), "no openflow_port: no port, never a guess"
    assert known.host_names([row]) == {"0a:00:00:00:00:10": ("edge-rtr", "Gi0/0")}


# ── the read ──────────────────────────────────────────────────────────────────────────────────

def test_the_view_is_the_committed_export_s_read_in_the_network_s_own_repository(lab):  # noqa: F811
    from modules import config
    from modules.sdn import known

    before = known.read(NET)
    assert before["state"] == "absent" and "no committed NSOT export" in before["why"]
    assert before["rows"] == [] and before["names"] == {}
    _p, done = _commit()
    assert done["outcome"] == "committed", done
    got = known.read(NET)
    assert got["state"] == "read" and got["why"] == ""
    assert got["names"] == {3: "ovs1", 4: "ovs2"} and got["devices"] == 6
    assert got["sha"] == done["sha256"][:12] and got["hosts"] == 0
    # A name no network answers to: absent, said, and no folder made for it.
    unknown = known.read("zz-no-such-network")
    assert unknown["state"] == "absent" and "zz-no-such-network is not a network" in unknown["why"]
    assert not os.path.exists(config.list_data_path("zz-no-such-network"))


def test_an_export_that_does_not_verify_and_a_read_that_raises_are_unreadable(lab,  # noqa: F811
                                                                               monkeypatch):
    from modules.nsot import export as X
    from modules.sdn import known

    _commit()
    monkeypatch.setattr(X, "read_in", lambda repo, rev="HEAD", network="": {
        "ok": False, "export": None, "sha256": "",
        "error": "the export's sha256 is aa, and its content hashes to bb"})
    got = known.read(NET)
    assert got["state"] == "unreadable" and "hashes to bb" in got["why"] and got["rows"] == []

    def boom(repo, rev="HEAD", network=""):
        raise OSError("the repository is locked")
    monkeypatch.setattr(X, "read_in", boom)
    got = known.read(NET)
    assert got["state"] == "unreadable" and got["why"] == "OSError: the repository is locked"


# ── a switch's name ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("own,netbox,words", [
    ("s1", {}, "s1"),                           # its own description, where it gives one
    ("None", {}, "DPID 0000000000000003"),      # Open vSwitch's placeholder is never a name
    ("", {}, "DPID 0000000000000003"),
    ("None", {3: "ovs1"}, "ovs1"),              # NetBox's name, matched by datapath id
    ("lab9", {3: "ovs1"}, "ovs1"),              # and over any description the switch gives
])
def test_a_switch_is_named_by_netbox_then_by_itself_and_never_by_a_placeholder(own, netbox,
                                                                              words):
    from modules.sdn import known

    fabric = [{"name": "ctl-1", "switches": {3: {"name": own}}, "hosts": []}]
    names = known.labels_of(fabric, {"names": netbox})
    assert known.switch_words(3, names) == words
    assert known.switch_words("0000000000000003", names) == words
