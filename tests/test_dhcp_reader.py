"""The DHCP reader (C529 step 1, board A), on Kea's own answers: tests/fixtures/kea/ holds the
lab's Kea 2.4.1 answering version-get, config-get and lease4/6-get-all (captured 2026-10-11
through Mercury's own client, keys naming a secret masked; none did). The lab's Kea had no
reservation at the capture, so reservations are planted into a copy of the answer, named.

- both families read, each subnet as Kea runs it (pools, lease times beside the global ones),
  every lease with when it ends, a DHCPv6 client's "." hostname read as none;
- ZTP's subnet by ZTP's own rule;
- a family that cannot be asked keeps its last good value, named with the read that failed,
  and never blanks the other; both failing raise (the reader keeps its last good value);
- not configured says so; the change test ignores the read's own time.
"""

import copy
import json
import os

import pytest

from modules.readers import dhcp as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEA = os.path.join(ROOT, "tests", "fixtures", "kea")


def _answer(svc, cmd):
    with open(os.path.join(KEA, f"{svc}-{cmd}.json"), encoding="utf-8") as fh:
        return json.load(fh)


class FakeKea:
    """Kea's Control Agent answering from the captures; *fail* names (service, command)s that
    are refused, *plant* edits a service's config-get answer."""

    def __init__(self, fail=(), plant=None, configured=True):
        self.fail, self.plant, self.configured, self.asked = set(fail), plant, configured, []

    def is_configured(self):
        return self.configured

    def command(self, cmd, svc):
        self.asked.append((svc, cmd))
        if (svc, cmd) in self.fail:
            return {"ok": False, "error": "Could not connect to <kea>"}
        result = _answer(svc, cmd)
        if self.plant and cmd == "config-get":
            result = self.plant(svc, copy.deepcopy(result))
        return {"ok": True, "result": result}


def _read(**kw):
    return D.read("Lab", kea=kw.pop("kea", FakeKea()), clock=lambda: 1791680000,
                  previous=kw.pop("previous", {}), ztp_ids=kw.pop("ztp_ids", [255]), **kw)


def test_both_families_each_subnet_as_kea_runs_it():
    v = _read()
    assert v["configured"] and set(v["families"]) == {"dhcp4", "dhcp6"}
    v4, v6 = v["families"]["dhcp4"], v["families"]["dhcp6"]
    assert v4["ok"] and v6["ok"] and v4["version"] == "2.4.1" and v4["words"] == "IPv4"
    assert [s["id"] for s in v4["subnets"]] == [10, 20, 255]
    assert [s["id"] for s in v6["subnets"]] == [10, 20, 30]
    ten = v4["subnets"][0]
    assert ten["prefix"] == "10.10.10.0/24" and ten["pools"] == ["10.10.10.100-10.10.10.200"]
    # Kea's file sets the lease times once, globally; config-get fills them into every subnet
    # (measured), so the page can only say "the same as the global", never "inherited".
    assert ten["times"]["valid"] == ten["global_times"]["valid"] == 31536000
    assert v6["subnets"][0]["times"]["preferred"] == 31536000
    assert [s["ztp"] for s in v4["subnets"]] == [False, False, True]
    assert v4["subnets"][2]["pools"] == []


def test_every_lease_with_when_it_ends():
    v = _read()
    v4, v6 = v["families"]["dhcp4"]["leases"], v["families"]["dhcp6"]["leases"]
    assert len(v4) == 3 and len(v6) == 6
    first = v4[0]
    assert first["by"] == "MAC" and first["identity"] == first["mac"]
    raw = _answer("dhcp4", "lease4-get-all")[0]["arguments"]["leases"]
    match = next(l for l in raw if l["ip-address"] == first["address"])
    assert first["ends"] == D._iso(match["cltt"] + match["valid-lft"])
    assert all(l["state"] == "active" for l in v4 + v6)
    # DHCPv6: keyed by DUID; Kea writes "." for a client that sent no name.
    assert all(l["by"] == "DUID" for l in v6)
    assert all(l["hostname"] != "." for l in v6)
    assert sum(1 for l in v6 if l["subnet_id"] == 10) == 4


def test_reservations_by_their_identity():
    """Planted (the lab's Kea had none at the capture): a MAC reservation in subnet 10, a DUID
    one in IPv6 subnet 10, as board A draws h1 and h3."""
    def plant(svc, result):
        conf = result[0]["arguments"]["Dhcp4" if svc == "dhcp4" else "Dhcp6"]
        key = "subnet4" if svc == "dhcp4" else "subnet6"
        if svc == "dhcp4":
            conf[key][0]["reservations"] = [{"hw-address": "aa:c1:ab:b0:85:65",
                                             "ip-address": "10.10.10.102", "hostname": "h3"}]
        else:
            conf[key][0]["reservations"] = [{"duid": "00:03:00:01:aa:c1:ab:b0:85:65",
                                             "ip-addresses": ["2001:db8:10::103"],
                                             "hostname": "h3"}]
        return result
    v = _read(kea=FakeKea(plant=plant))
    (r4,) = v["families"]["dhcp4"]["subnets"][0]["reservations"]
    assert r4 == {"hostname": "h3", "by": "MAC", "identity": "aa:c1:ab:b0:85:65",
                  "addresses": ["10.10.10.102"], "prefixes": []}
    (r6,) = v["families"]["dhcp6"]["subnets"][0]["reservations"]
    assert r6["by"] == "DUID" and r6["addresses"] == ["2001:db8:10::103"]


def test_a_family_that_cannot_be_asked_keeps_its_last_good_and_blanks_nothing():
    good = _read()
    v = _read(kea=FakeKea(fail={("dhcp6", "lease6-get-all")}), previous=good)
    v4, v6 = v["families"]["dhcp4"], v["families"]["dhcp6"]
    assert v4["ok"] and len(v4["leases"]) == 3
    assert not v6["ok"] and "dhcp6 could not be asked (lease6-get-all)" in v6["error"]
    assert len(v6["leases"]) == 6 and v6["read_at"] == good["families"]["dhcp6"]["read_at"]
    # With no last good read, the family is unknown, never empty.
    v = _read(kea=FakeKea(fail={("dhcp6", "config-get")}))
    assert v["families"]["dhcp6"]["subnets"] is None and v["families"]["dhcp6"]["leases"] is None


def test_both_failing_raise_so_the_reader_keeps_its_last_good():
    with pytest.raises(RuntimeError, match="dhcp4.*dhcp6"):
        _read(kea=FakeKea(fail={("dhcp4", "version-get"), ("dhcp6", "version-get")}))


def test_not_configured_says_so_and_asks_nothing():
    kea = FakeKea(configured=False)
    assert _read(kea=kea) == {"configured": False} and kea.asked == []


def test_ztp_s_subnet_by_ztp_s_own_rule(monkeypatch):
    from modules.nsot import ztp
    monkeypatch.setattr(ztp, "ztp_subnets", lambda dhcp4: [({"id": 255}, "10.255.0.10")])
    v = D.read("Lab", kea=FakeKea(), clock=lambda: 0, previous={})
    assert [s["ztp"] for s in v["families"]["dhcp4"]["subnets"]] == [False, False, True]
    assert not any(s["ztp"] for s in v["families"]["dhcp6"]["subnets"])


def test_the_change_test_ignores_the_read_time():
    a = _read()
    b = D.read("Lab", kea=FakeKea(), clock=lambda: 1791680300, previous={}, ztp_ids=[255])
    assert a["read_at"] != b["read_at"] and not D.changed(a, b)
    c = _read(kea=FakeKea(fail={("dhcp6", "config-get")}), previous=a)
    assert D.changed(a, c)
