"""The needs round's one home, `modules/ai/needs.py` (the operator's ruling of 2026-10-26): an
unknown kind refused; a second round refused; a lookup that fails reported as unfulfilled and
never retried; the topology class off making every need unfulfilled (egress); at most one
follow-up, linked to its parent; the needs recorded on the parent's use row."""
import pytest

from modules import endpoints as E
from modules.ai import calls, egress_classes, needs


@pytest.fixture
def record(monkeypatch, tmp_path):
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    monkeypatch.setattr(egress_classes, "topology_allowed",
                        lambda net: {"allowed": True, "why": ""})
    calls.record({"id": "ai-parent", "feature": "explain", "subject": {"network": "lab"},
                  "cost_usd": 0.01})


H1 = {"mac": "aac1.ab99.f6e2", "addresses": ["192.0.2.100"], "hostname": "desk7",
      "device": "edge1", "interface": "GigabitEthernet1/0", "vlan": "10",
      "last_seen": "2026-10-26T08:24:00Z"}


def _stored(monkeypatch, endpoints=(H1,)):
    monkeypatch.setattr(E, "stored", lambda net: {"state": "read", "why": "",
                                                  "endpoints": list(endpoints),
                                                  "read_at": "2026-10-26T08:24:00Z",
                                                  "devices": {}})


class TestValidation:
    def test_an_unknown_kind_is_refused_by_name(self):
        got = needs.validate([{"kind": "packet_capture", "subject": "edge1"},
                              {"kind": "endpoint_location", "subject": "desk7"}])
        assert [n.kind for n in got["needs"]] == [needs.NeedKind.endpoint_location]
        assert got["refused"] == ["need 0: the kind 'packet_capture' is not one Mercury "
                                  "looks up"]

    def test_a_malformed_need_is_refused(self):
        got = needs.validate([{"kind": "neighbour"}, "edge1",
                              {"kind": "neighbour", "subject": "edge1", "why": "x"}])
        assert got["needs"] == [] and len(got["refused"]) == 3

    def test_an_unknown_kind_is_never_looked_up(self, record, monkeypatch):
        looked = []
        monkeypatch.setitem(needs._LOOKUPS, needs.NeedKind.endpoint_location,
                            lambda net, s: looked.append(s) or ([], ""))
        got = needs.run("ai-parent", "lab", [{"kind": "packet_capture", "subject": "x"}],
                        actor="svc", follow=lambda r, link: pytest.fail("no need to follow"))
        assert got["ok"] and got["results"] == [] and looked == []
        assert got["refused"] and got["follow_up"] is None


class TestOneRound:
    def test_the_follow_up_is_linked_to_its_parent(self, record, monkeypatch):
        _stored(monkeypatch)
        followed = []
        got = needs.run("ai-parent", "lab", [{"kind": "endpoint_location", "subject": "desk7"}],
                        actor="svc", follow=lambda r, link: followed.append((r, link)) or "ai-child")
        assert got["follow_up"] == "ai-child"
        (results, link), = followed
        assert link == {"parent": "ai-parent"}
        assert results[0]["state"] == "fulfilled"
        assert results[0]["data"][0]["interface"] == "GigabitEthernet1/0"
        assert results[0]["data"][0]["last_seen"] == "2026-10-26T08:24:00Z"

    def test_a_second_round_on_the_same_call_is_refused(self, record, monkeypatch):
        _stored(monkeypatch)
        need = [{"kind": "endpoint_location", "subject": "desk7"}]
        followed = []
        assert needs.run("ai-parent", "lab", need, actor="svc",
                         follow=lambda r, link: followed.append(1))["ok"]
        again = needs.run("ai-parent", "lab", need, actor="svc",
                          follow=lambda r, link: followed.append(1))
        assert not again["ok"] and "a second is refused" in again["error"]
        assert followed == [1]

    def test_a_round_on_a_follow_up_is_refused(self, record):
        calls.record({"id": "ai-child", "feature": "explain",
                      "subject": {"network": "lab", "parent": "ai-parent"}})
        got = needs.run("ai-child", "lab", [{"kind": "neighbour", "subject": "edge1"}],
                        actor="svc", follow=lambda r, link: pytest.fail("never followed"))
        assert not got["ok"] and "itself a follow-up" in got["error"]

    def test_an_unrecorded_call_has_no_round(self, record):
        got = needs.run("ai-nobody", "lab", [], actor="svc", follow=lambda r, link: None)
        assert not got["ok"] and "not recorded" in got["error"]


class TestLookups:
    def test_a_failing_lookup_is_unfulfilled_and_never_retried(self, record, monkeypatch):
        tries = []

        def broken(net, subject):
            tries.append(subject)
            raise OSError("the store is unreadable")
        monkeypatch.setitem(needs._LOOKUPS, needs.NeedKind.neighbour, broken)
        got = needs.run("ai-parent", "lab", [{"kind": "neighbour", "subject": "edge1"}],
                        actor="svc", follow=lambda r, link: "ai-child")
        (r,) = got["results"]
        assert r["state"] == "unfulfilled" and "not retried" in r["why"]
        assert tries == ["edge1"]

    def test_the_topology_class_off_makes_each_need_unfulfilled_egress(self, record,
                                                                       monkeypatch):
        monkeypatch.setattr(egress_classes, "topology_allowed", lambda net: {
            "allowed": False, "why": "the topology class is off for lab"})
        monkeypatch.setitem(needs._LOOKUPS, needs.NeedKind.endpoint_location,
                            lambda net, s: pytest.fail("never looked up"))
        got = needs.run("ai-parent", "lab", [{"kind": "endpoint_location", "subject": "desk7"}],
                        actor="svc", follow=lambda r, link: "ai-child")
        (r,) = got["results"]
        assert (r["state"], r["why"]) == ("unfulfilled",
                                          "egress: the topology class is off for lab")
        assert r["data"] is None

    def test_an_endpoint_not_observed_is_unfulfilled_saying_when_read(self, record,
                                                                      monkeypatch):
        _stored(monkeypatch)
        r = needs.lookup("lab", needs.Need(kind=needs.NeedKind.endpoint_location,
                                           subject="desk9"))
        assert r["state"] == "unfulfilled"
        assert r["why"] == "desk9 is not observed (read 2026-10-26T08:24:00Z)"

    def test_a_route_is_unfulfilled_its_layer_not_collected(self, record):
        r = needs.lookup("lab", needs.Need(kind=needs.NeedKind.route, subject="192.0.2.0/24"))
        assert r["state"] == "unfulfilled" and "not collected" in r["why"]


class TestRecorded:
    def test_the_round_is_recorded_on_the_parent_fulfilled_or_not(self, record, monkeypatch):
        _stored(monkeypatch)
        needs.run("ai-parent", "lab", [{"kind": "endpoint_location", "subject": "desk7"},
                                       {"kind": "route", "subject": "192.0.2.0/24"},
                                       {"kind": "ping", "subject": "x"}],
                  actor="svc", follow=lambda r, link: "ai-child")
        (use,) = calls.find("ai-parent")["uses"]
        assert use["use"] == "needs round" and use["actor"] == "svc"
        assert [(n.get("kind"), n.get("state")) for n in use["needs"]] == [
            ("endpoint_location", "fulfilled"), ("route", "unfulfilled"), (None, None)]
        assert use["needs"][2] == {"refused": "need 2: the kind 'ping' is not one Mercury "
                                              "looks up"}
        # A use row is no call: the round costs nothing beyond its calls.
        assert [r["id"] for r in calls.read()["rows"]] == ["ai-parent"]
