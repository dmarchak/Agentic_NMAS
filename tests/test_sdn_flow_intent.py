"""Flow intent and the owner of each flow (`modules/sdn/flow_intent.py`, PHASE8_PLAN 17.1 S5),
against Ryu 4.34's captured flow table (tests/fixtures/sdn/ryu/rest_with_peer.json, read through
the Ryu driver) and the specs the capture's writes were made from (test_sdn_ryu.py's).

The capture's table holds seven flows with cookie 0 (the application's table-miss, its L2 and
L4 flows, a WRITE_ACTIONS and a SET_FIELD in table 1) and two of Mercury's: the /24 drop
(cookie ...0001, hard timeout 300) and the metered flow (...0002). Mercury's IPv6 drop (...0003)
was written after the table was read, so it is recorded and not installed.

- **The cookie:** "ME" (0x4d45) in the high 16 bits, a 48-bit id; the capture's cookies are in
  that range; a fresh one is drawn at random and never 0.
- **The store:** append-only lines in the network's folder, under its cross-process lock; a
  cookie recorded once; a withdrawal needs a record and a reason; absent and unreadable apart;
  a non-Mercury cookie, an unsendable flow or no actor refused.
- **Classify:** each installed flow is `mercury`, `mercury_differs` (naming each difference with
  both values), `controller_own` or `unauthorised`; each recorded flow not installed is
  `expired` past its hard timeout, else `missing`, and `not_judged` on a switch not read. A
  switch's own spelling of a match (a dotted mask, `/24`, an IPv6 mask) and its order of
  instructions compare equal; IPv4 and IPv6 alike.
"""
import json

import pytest

from modules.sdn import flow_intent as F
from modules.sdn.drivers import ryu as R
from modules.sdn.drivers.base import Connection
from tests.sdn_fakes import Routes, fixture
from tests.test_sdn_ryu import DROP, LIMIT, MERCURY_1, MERCURY_2, MERCURY_3, V6_DROP

BASE = "http://127.0.0.1:8080"
T0 = 1_790_000_000.0
CONN = {"name": "ctl-1", "own_cookies": [0]}
RESPONSE = {"id": "resp-1", "action": "drop"}


@pytest.fixture
def store(tmp_path, monkeypatch):
    from modules import config
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
    return tmp_path


def installed():
    """The capture's flow table, as the Ryu driver reads it."""
    drv = R.RyuDriver(Connection(BASE), session=Routes(fixture("rest_with_peer.json"), BASE))
    got = drv.flows(1)
    assert got["ok"]
    return got["flows"]


def record(spec, at=T0, connection="ctl-1", network="Default"):
    return F.record_installed(network, connection=connection, flow=dict(spec, dpid=1),
                              actor="op@example.com", response=RESPONSE, at=at)


def as_read(spec, **changed):
    """A flow as a driver reads one back (every field, counters set), from a spec with
    *changed* fields: for a case the capture holds no flow for."""
    from modules.sdn.drivers.base import Flow
    values = dict(spec)
    values.update(changed)
    return Flow(**dict(values, dpid=values.get("dpid", 1)), packet_count=0, byte_count=0,
                duration_sec=1).as_dict()


def by_cookie(result):
    return {f["cookie"]: f for f in result["flows"]}


# ───────────────────────────────────────────────────────────────────────────── the cookie

class TestTheCookie:
    def test_mercury_s_range_is_me_in_the_high_16_bits(self):
        assert F.mercury_cookie(1) == 0x4D45000000000001
        assert all(F.is_mercury(c) for c in (MERCURY_1, MERCURY_2, MERCURY_3)), \
            "the capture's cookies are Mercury's"
        assert not F.is_mercury(0) and not F.is_mercury(0x4D45 << 48), "id 0 is no flow"
        assert not F.is_mercury(0x4D44FFFFFFFFFFFF) and not F.is_mercury(True)

    def test_a_fresh_cookie_is_mercury_s_and_random(self):
        drawn = {F.new_cookie() for _ in range(50)}
        assert len(drawn) == 50 and all(F.is_mercury(c) for c in drawn)

    @pytest.mark.parametrize("bad", [0, 1 << 48, -1, "1"])
    def test_an_id_outside_48_bits_is_refused(self, bad):
        with pytest.raises(F.IntentRefused):
            F.mercury_cookie(bad)


# ───────────────────────────────────────────────────────────────────────────── the store

@pytest.mark.usefixtures("store")
class TestTheStore:
    def test_a_record_holds_what_mercury_expects_and_who_and_why(self, store):
        row = record(DROP)
        assert row == {
            "kind": "installed", "cookie": MERCURY_1, "cookie_hex": "0x4d45524300000001",
            "network": "Default", "connection": "ctl-1", "dpid": 1, "table_id": 0,
            "priority": 100, "match": DROP["match"], "actions": [], "idle_timeout": 0,
            "hard_timeout": 300, "installed_at": T0, "at": "2026-09-21T14:13:20Z",
            "actor": "op@example.com", "actor_verified": "", "response": RESPONSE}
        lines = (store / "lists" / "default" / "flow_intent.jsonl").read_text().splitlines()
        assert [json.loads(x) for x in lines] == [row]

    def test_absent_and_unreadable_are_different(self, store):
        assert F.intent("Default") == {"state": "ok", "flows": [], "withdrawn": {}, "error": ""}
        assert F.read("Default")["state"] == "absent"
        path = store / "lists" / "default" / "flow_intent.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("{torn\n")
        assert F.intent("Default")["state"] == "unreadable"
        with pytest.raises(F.IntentRefused, match="cannot be read"):
            record(DROP)

    def test_a_cookie_is_recorded_once(self):
        record(DROP)
        with pytest.raises(F.IntentRefused, match="already recorded"):
            record(DROP)

    def test_what_mercury_could_not_have_sent_is_refused(self):
        with pytest.raises(F.IntentRefused, match="not Mercury's"):
            record(dict(DROP, cookie=0))
        with pytest.raises(F.IntentRefused, match="not one Mercury could have sent"):
            record(dict(DROP, match={"nw_src": "192.0.2.1"}))
        with pytest.raises(F.IntentRefused, match="who installed it"):
            F.record_installed("Default", connection="ctl-1", flow=dict(DROP, dpid=1),
                               actor="", response=RESPONSE)

    def test_a_withdrawn_flow_is_no_longer_expected(self):
        record(DROP)
        record(LIMIT)
        F.record_withdrawn("Default", MERCURY_1, connection="ctl-1", actor="op",
                           why="rolled back", at=T0 + 5)
        got = F.intent("Default", "ctl-1")
        assert [r["cookie"] for r in got["flows"]] == [MERCURY_2]
        assert got["withdrawn"][MERCURY_1]["why"] == "rolled back"

    def test_a_withdrawal_needs_a_record_and_a_reason(self):
        with pytest.raises(F.IntentRefused, match="no flow recorded"):
            F.record_withdrawn("Default", MERCURY_1, connection="ctl-1", actor="op", why="x")
        record(DROP)
        with pytest.raises(F.IntentRefused, match="why"):
            F.record_withdrawn("Default", MERCURY_1, connection="ctl-1", actor="op", why=" ")
        with pytest.raises(F.IntentRefused, match="no flow recorded"):
            F.record_withdrawn("Default", MERCURY_1, connection="other", actor="op", why="x")

    def test_networks_are_kept_apart(self):
        record(DROP, network="Branch")
        assert F.intent("Default")["flows"] == []
        assert [r["cookie"] for r in F.intent("Branch")["flows"]] == [MERCURY_1]

    def test_it_is_a_records_store_with_its_switch(self):
        from modules import records_db, records_migrate
        from modules.settings_schema import DEFAULTS
        assert "flow_intent" in records_db.STORES
        assert records_migrate.store_of("flow_intent").per_network
        assert DEFAULTS["records_store_flow_intent"] == "file"


# ───────────────────────────────────────────────────────────────────────────── classify

@pytest.mark.usefixtures("store")
class TestClassify:
    def test_the_capture_s_table_as_recorded(self):
        record(DROP)
        record(LIMIT)
        record(V6_DROP, at=T0 + 30)
        got = F.classify(installed(), CONN, F.intent("Default", "ctl-1"), now=T0 + 60)
        flows = by_cookie(got)
        assert flows[MERCURY_1]["owner"] == "mercury" and flows[MERCURY_2]["owner"] == "mercury"
        assert sum(f["owner"] == "controller_own" for f in got["flows"]) == 7
        (v6,) = got["records"]
        assert v6["cookie"] == MERCURY_3 and v6["state"] == "missing"
        assert got["counts"] == {"mercury": 2, "mercury_differs": 0, "controller_own": 7,
                                 "unauthorised": 0, "missing": 1, "expired": 0,
                                 "not_judged": 0}

    def test_with_no_own_cookie_declared_the_application_s_flows_are_unauthorised(self):
        got = F.classify(installed(), {"name": "ctl-1", "own_cookies": []}, [], now=T0)
        assert got["counts"]["unauthorised"] == 9
        assert "neither Mercury's nor declared" in got["flows"][0]["words"]

    def test_mercury_s_prefix_with_no_record_is_unauthorised(self):
        got = F.classify(installed(), CONN, [], now=T0)
        f = by_cookie(got)[MERCURY_1]
        assert f["owner"] == "unauthorised" and "Mercury's prefix" in f["words"]

    def test_an_unrecorded_mercury_cookie_beside_recorded_ones_is_unauthorised(self):
        record(LIMIT)                                 # ...0002 recorded, ...0001 not
        f = by_cookie(F.classify(installed(), CONN, F.intent("Default"), now=T0))
        assert f[MERCURY_2]["owner"] == "mercury"
        assert f[MERCURY_1]["owner"] == "unauthorised" and f[MERCURY_1]["record"] is None

    def test_a_record_withdrawn_and_still_installed_is_unauthorised(self):
        record(DROP)
        F.record_withdrawn("Default", MERCURY_1, connection="ctl-1", actor="op",
                           why="rolled back", at=T0 + 5)
        f = by_cookie(F.classify(installed(), CONN, F.intent("Default", "ctl-1"), now=T0))
        assert f[MERCURY_1]["owner"] == "unauthorised" and "withdrawn" in f[MERCURY_1]["words"]

    def test_another_connection_s_record_does_not_make_it_mercury_s_here(self):
        record(DROP, connection="ctl-2")
        f = by_cookie(F.classify(installed(), CONN, F.intent("Default")["flows"], now=T0))
        assert f[MERCURY_1]["owner"] == "unauthorised" and "ctl-2" in f[MERCURY_1]["words"]

    def test_a_differing_match_is_named_with_both_values(self):
        record(dict(DROP, match={"eth_type": 2048, "ipv4_src": "192.0.2.0/25"}))
        f = by_cookie(F.classify(installed(), CONN, F.intent("Default"), now=T0))[MERCURY_1]
        assert f["owner"] == "mercury_differs"
        assert f["differs"] == [{"field": "match.ipv4_src", "expected": "192.0.2.0/25",
                                 "installed": "192.0.2.0/24",
                                 "words": "match ipv4_src: installed 192.0.2.0/24, recorded "
                                          "192.0.2.0/25"}]

    def test_differing_actions_priority_and_switch_are_each_named(self):
        record(dict(LIMIT, priority=91,
                    actions=[{"type": "METER", "meter_id": 1}, {"type": "OUTPUT", "port": 3}]))
        f = by_cookie(F.classify(installed(), CONN, F.intent("Default"), now=T0))[MERCURY_2]
        assert [d["field"] for d in f["differs"]] == ["priority", "actions"]
        assert "actions: installed METER:1, OUTPUT:2, recorded METER:1, OUTPUT:3" in f["words"]
        flows = [dict(x, dpid=2) if x["cookie"] == MERCURY_2 else x for x in installed()]
        g = by_cookie(F.classify(flows, CONN, F.intent("Default"), read_switches=[1, 2],
                                 now=T0))[MERCURY_2]
        assert g["differs"][0]["words"] == "on switch 2, recorded for switch 1"

    def test_an_extra_match_field_installed_is_a_difference(self):
        record(dict(DROP, match={"eth_type": 2048}))
        f = by_cookie(F.classify(installed(), CONN, F.intent("Default"), now=T0))[MERCURY_1]
        assert f["differs"][0]["words"] == ("match ipv4_src: installed 192.0.2.0/24, recorded "
                                            "not matched")

    @pytest.mark.parametrize("written", ["192.0.2.0/255.255.255.0", "192.0.2.0/24",
                                         "192.0.2.7/24"])
    def test_a_mask_spelled_either_way_is_the_same_match(self, written):
        record(dict(DROP, match={"eth_type": 2048, "ipv4_src": written}))
        f = by_cookie(F.classify(installed(), CONN, F.intent("Default"), now=T0))[MERCURY_1]
        assert f["owner"] == "mercury", f["differs"]

    @pytest.mark.parametrize("recorded,read", [
        ("2001:db8::/32", "2001:db8::/ffff:ffff::"),
        ("2001:DB8::1", "2001:db8::1"),
        ("2001:db8::/32", "2001:db8:0:0::/32")])
    def test_an_ipv6_match_compares_by_value(self, recorded, read):
        spec = dict(V6_DROP, match={"eth_type": 0x86DD, "ipv6_src": recorded})
        record(spec)
        flow = as_read(spec, match={"eth_type": 0x86DD, "ipv6_src": read})
        got = F.classify([flow], CONN, F.intent("Default"), now=T0)
        assert got["flows"][0]["owner"] == "mercury", got["flows"][0]["differs"]

    def test_an_ipv6_difference_is_named(self):
        record(V6_DROP)
        flow = as_read(V6_DROP, match=dict(V6_DROP["match"], ipv6_src="2001:db8::2"))
        f = F.classify([flow], CONN, F.intent("Default"), now=T0)["flows"][0]
        assert f["owner"] == "mercury_differs"
        assert f["differs"][0]["field"] == "match.ipv6_src"

    def test_instructions_in_the_switch_s_order_compare_equal(self):
        record(dict(LIMIT, actions=[{"type": "OUTPUT", "port": 2},
                                    {"type": "METER", "meter_id": 1}]))
        f = by_cookie(F.classify(installed(), CONN, F.intent("Default"), now=T0))[MERCURY_2]
        assert f["owner"] == "mercury"

    def test_apply_actions_in_another_order_differ(self):
        spec = dict(LIMIT, actions=[{"type": "OUTPUT", "port": 2}, {"type": "OUTPUT", "port": 3}])
        record(spec)
        flow = as_read(spec, actions=list(reversed(spec["actions"])))
        assert F.classify([flow], CONN, F.intent("Default"), now=T0)["flows"][0]["owner"] == \
            "mercury_differs"

    def test_past_its_hard_timeout_a_recorded_flow_is_expired_not_missing(self):
        record(V6_DROP, at=T0)
        before = F.classify(installed(), CONN, F.intent("Default"), now=T0 + 299)["records"]
        after = F.classify(installed(), CONN, F.intent("Default"), now=T0 + 300)["records"]
        assert before[0]["state"] == "missing"
        assert after[0]["state"] == "expired" and "300 s, as set" in after[0]["words"]

    def test_no_hard_timeout_is_missing_whenever(self):
        record(dict(V6_DROP, hard_timeout=0, idle_timeout=30))
        (r,) = F.classify(installed(), CONN, F.intent("Default"), now=T0 + 10 ** 6)["records"]
        assert r["state"] == "missing" and "idle timeout of 30 s" in r["words"]

    def test_a_switch_not_read_is_not_judged(self):
        record(dict(V6_DROP, hard_timeout=0), )
        (r,) = F.classify([], CONN, F.intent("Default"), now=T0)["records"]
        assert r["state"] == "not_judged"
        (r,) = F.classify([], CONN, F.intent("Default"), read_switches=[1], now=T0)["records"]
        assert r["state"] == "missing", "an empty table read whole is judged"

    def test_an_unreadable_intent_classifies_nothing_and_says_so(self, store):
        path = store / "lists" / "default" / "flow_intent.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("{torn\n")
        got = F.classify(installed(), CONN, F.intent("Default"), now=T0)
        assert got["state"] == "unreadable" and got["flows"] == []
        assert "no flow was classified" in got["error"]

    def test_it_is_json_serialisable(self):
        record(DROP)
        json.dumps(F.classify(installed(), CONN, F.intent("Default"), now=T0))
