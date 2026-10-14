"""C529 step 3, board D's exclusions (`modules/dhcp_exclusions.py`): a range kept out of a
subnet's pool, named with its reason and source; Kea given the pieces of the range as set;
written through board C's one write path for subnets; conflicts found from committed intent.

On the host's own Kea files after the subnet move (the `moved` fixture of test_dhcp_subnets),
with a fake Kea that loads Mercury's subnet file at `config-reload`.
"""

import pytest

from modules import dhcp_exclusions as E
from modules import dhcp_subnets as S
from tests.test_dhcp_subnets import _intent, _ok_test, moved  # noqa: F401 (the fixture)

EMPTY = {"exclusions": [], "pools": {}}
RIG = {"op": "add", "family": "IPv4", "id": "10", "range": "10.10.10.120 - 10.10.10.129",
       "reason": "lab test rig, fixed addresses", "source": "manual"}


class TestThePieces:
    @pytest.mark.parametrize("pool, cut, want", [
        ("10.10.10.100 - 10.10.10.199", ["10.10.10.120 - 10.10.10.129"],
         ["10.10.10.100 - 10.10.10.119", "10.10.10.130 - 10.10.10.199"]),
        ("10.10.10.100 - 10.10.10.199", ["10.10.10.100"], ["10.10.10.101 - 10.10.10.199"]),
        ("10.10.10.100 - 10.10.10.199", ["10.10.10.1 - 10.10.10.3"],
         ["10.10.10.100 - 10.10.10.199"]),
        ("10.10.10.100 - 10.10.10.199", ["10.10.10.190 - 10.10.10.250"],
         ["10.10.10.100 - 10.10.10.189"]),
        ("2001:db8:10::100 - 2001:db8:10::1ff", ["2001:db8:10::150"],
         ["2001:db8:10::100 - 2001:db8:10::14f", "2001:db8:10::151 - 2001:db8:10::1ff"]),
    ], ids=["middle", "first", "outside", "tail", "ipv6"])
    def test_kea_is_given_what_the_exclusions_leave(self, pool, cut, want):
        assert E.pieces(pool, cut) == want


class TestThePlan:
    def test_an_exclusion_splits_the_pool_and_records_the_range_as_set(self, moved):
        p = E.plan("Lab", RIG, kea=moved["kea"], record=EMPTY)
        assert p["ok"], p["refused"]
        assert [x["pool"] for x in p["after"]["pools"]] == ["10.10.10.100 - 10.10.10.119",
                                                            "10.10.10.130 - 10.10.10.200"]
        assert p["record"]["pools"] == {"IPv4:10": "10.10.10.100 - 10.10.10.200"}
        assert p["record"]["exclusions"][0]["range"] == "10.10.10.120 - 10.10.10.129"
        assert ("pass", "inside the pool 10.10.10.100 - 10.10.10.200: the pool is split around "
                        "it") in p["checks"]

    def test_each_piece_keeps_what_the_pool_says_it_is_for(self, moved):
        """C709: an exclusion splits a described pool; each piece carries its description."""
        values = {"op": "edit", "family": "IPv4", "id": "10", "pool": "",
                  "pool_note": "lab hosts, VLAN 10"}
        got = S.apply_edit("Lab", values, S.plan("Lab", values, kea=moved["kea"])["hash"],
                           actor="p@example.invalid", reason="describe the pool",
                           kea=moved["kea"], run_test=_ok_test,
                           record=lambda l, plan, **k: {"ok": True, "commit": "abc1234"})
        assert got["ok"], got["error"]
        p = E.plan("Lab", RIG, kea=moved["kea"], record=EMPTY)
        assert p["ok"], p["refused"]
        assert [(x["pool"], x.get("user-context")) for x in p["after"]["pools"]] == [
            ("10.10.10.100 - 10.10.10.119", {"description": "lab hosts, VLAN 10"}),
            ("10.10.10.130 - 10.10.10.200", {"description": "lab hosts, VLAN 10"})]

    def test_a_held_address_is_said_with_how_long_its_client_keeps_it(self, moved):
        p = E.plan("Lab", dict(RIG, range="10.10.10.102", source="intent",
                               reason="r7 Gi2 in intent, a static address"),
                   kea=moved["kea"], record=EMPTY)
        held = [n for n in p["leases"] if n.startswith("10.10.10.102 is held by")]
        assert held and "keeps it until its lease ends" in held[0]
        assert "two hosts may answer on it" in held[0]

    @pytest.mark.parametrize("values, words", [
        (dict(RIG, range="10.10.20.5"), "does not lie inside 10.10.10.0/24"),
        (dict(RIG, reason="rig"), "say why these addresses are kept out"),
        (dict(RIG, id="255"), "ZTP's: it has no pool to shape"),
        (dict(RIG, range="10.10.10.100 - 10.10.10.200"), "would leave nothing of the pool"),
    ], ids=["outside", "short-reason", "ztp", "everything"])
    def test_what_it_cannot_do_is_refused_by_name(self, moved, values, words):
        p = E.plan("Lab", values, kea=moved["kea"], record=EMPTY)
        assert not p["ok"] and words in p["refused"], p["refused"]

    def test_an_overlap_with_a_recorded_exclusion_is_refused(self, moved):
        rec = {"exclusions": [dict(family="IPv4", subnet=10, range="10.10.10.125 - 10.10.10.140",
                                   reason="the printers")], "pools": {}}
        p = E.plan("Lab", RIG, kea=moved["kea"], record=rec)
        assert not p["ok"] and "overlaps the exclusion 10.10.10.125 - 10.10.10.140" in p["refused"]

    def test_a_removal_gives_the_addresses_back_and_says_what_survives(self, moved):
        rec = {"exclusions": [dict(family="IPv4", subnet=10, range="10.10.10.120 - 10.10.10.129",
                                   reason="lab test rig", by="p", at="2026-10-07T00:00:00Z")],
               "pools": {"IPv4:10": "10.10.10.100 - 10.10.10.199"}}
        p = E.plan("Lab", {"op": "remove", "family": "IPv4", "id": "10",
                           "was": "10.10.10.120 - 10.10.10.129"}, kea=moved["kea"], record=rec)
        assert p["ok"], p["refused"]
        assert [x["pool"] for x in p["after"]["pools"]] == ["10.10.10.100 - 10.10.10.199"]
        assert p["record"]["exclusions"] == [] and "stays in the repository's history" in \
            p["survives"][0]


class TestTheApply:
    def test_it_goes_through_the_subnet_write_and_its_own_record(self, moved, monkeypatch):
        monkeypatch.setattr(E, "read_committed", lambda list_name: EMPTY)
        p = E.plan("Lab", RIG, kea=moved["kea"])
        recorded = []
        got = S.apply_edit("Lab", RIG, p["hash"], actor="p", reason="keep the rig out",
                           kea=moved["kea"], run_test=_ok_test, planner=E.plan,
                           record=lambda l, plan, **k: recorded.append(plan) or
                           {"ok": True, "commit": "abc"})
        assert got["ok"], got["error"]
        assert [x["pool"] for x in next(s for s in moved["kea"].loaded["dhcp4"]
                                        if s["id"] == 10)["pools"]] == [
            "10.10.10.100 - 10.10.10.119", "10.10.10.130 - 10.10.10.200"]
        assert recorded and recorded[0]["record"]["exclusions"][0]["reason"] == \
            "lab test rig, fixed addresses"


    def test_a_confirm_in_a_later_second_than_its_preview_still_applies(self, moved,
                                                                        monkeypatch):
        """C770: the plan stamps a new exclusion with the clock, and the confirm recomputes the
        plan; with the stamp in the hash, every confirm a second after its preview was refused
        "what the preview showed has changed" (CI #760 lost the race; a person always does).
        The clock is made to move between them; the record written carries the confirm's
        time."""
        clock = iter(["2026-10-14T04:00:00Z", "2026-10-14T04:00:07Z"])
        monkeypatch.setattr(E.time, "strftime", lambda fmt, t=None: next(clock))
        monkeypatch.setattr(E, "read_committed", lambda list_name: EMPTY)
        p = E.plan("Lab", RIG, kea=moved["kea"])
        recorded = []
        got = S.apply_edit("Lab", RIG, p["hash"], actor="p", reason="keep the rig out",
                           kea=moved["kea"], run_test=_ok_test, planner=E.plan,
                           record=lambda l, plan, **k: recorded.append(plan) or
                           {"ok": True, "commit": "abc"})
        assert got["ok"], got["error"]
        assert recorded[0]["record"]["exclusions"][0]["at"] == "2026-10-14T04:00:07Z"


def _value():
    """The DHCP reader's value as the page gets it: one subnet with its pool, and intent giving
    an interface a static address inside it (a router's port on the client VLAN)."""
    return {"intent": {"IPv4": {"10.10.10.0/24": [{"device": "r7", "iface": "GigabitEthernet2",
                                                   "address": "10.10.10.150", "gateway": []}]}},
            "families": {"dhcp4": {"words": "IPv4", "subnets": [
                {"id": 10, "prefix": "10.10.10.0/24", "pools": ["10.10.10.100-10.10.10.200"],
                 "ztp": False}], "leases": [
                {"address": "10.10.10.150", "state": "active", "identity": "aa:c1:ab:21:7f:03",
                 "ends": "2027-10-06T00:00:00Z"}]}}}


class TestTheConflicts:
    def test_a_static_address_inside_a_pool_is_a_conflict_with_whether_it_is_leased(self):
        got = E.conflicts(_value(), EMPTY)
        assert len(got) == 1 and got[0]["address"] == "10.10.10.150"
        assert got[0]["device"] == "r7" and "two hosts may answer on it" in got[0]["leased"]

    def test_an_excluded_address_is_no_conflict(self):
        rec = {"exclusions": [dict(family="IPv4", subnet=10, range="10.10.10.150",
                                   reason="r7 Gi2")], "pools": {}}
        assert E.conflicts(_value(), rec) == []

    def test_the_lab_s_svis_below_the_pools_are_none(self):
        value = _value()
        value["intent"] = {"IPv4": dict(_intent()["IPv4"])}
        assert E.conflicts(value, EMPTY) == []
