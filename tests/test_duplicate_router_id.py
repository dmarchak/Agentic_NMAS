"""C2446: a duplicate OSPF router-id, which only the devices' log says, raised as a CRITICAL
Needs attention row naming both routers and the id, and read again by heal to intent's R8
verify ("no duplicate router-id logged").

**The lines are REAL**: CLI session 6's R8, 2026-11-03, read from Loki through Mercury's own
integration, read-only. Each is kept as Loki gave it: its receive time (the event's time, never
the device's clock) and the raw line. **The one edit:** each 10.255.a.b address moved to
192.0.2.0/24 consistently, the same address to the same replacement everywhere (10.255.1.14 ->
192.0.2.14, 10.255.4.2 -> 192.0.2.42, 10.255.4.1 -> 192.0.2.41, 10.255.1.16 -> 192.0.2.16);
everything else byte for byte, both header shapes included (r4's carries its name and `UTC`,
r6's an address in place of the name and no `UTC`).

**Not captured:** OSPFv3's line (Cisco's documented `%OSPFv3-4-DUP_RTRID_NBR` form, its
neighbour an IPv6 link-local address; docs/IPV6_PARITY.md's standing rule) and the area
variant (`%OSPF-4-DUP_RTRID_AREA`, Cisco's documented form). The lab logged neither.

- each shape parsed, attributed to its own device by name, and a non-matching line is none;
- the reader groups both routers' reports of one id, over its own window, a full page refused;
- Needs attention: one CRITICAL row naming both routers, the id and each interface, saying
  which departed from intent, clearing once no line is within the quiet time; one device alone
  named alone; nothing raised by a line that is not one;
- heal to intent: the duplicate is a symptom trigger, sighted, and R8's verify finds it still
  logged on the real lines and gone once they stop.
"""

import calendar

import pytest

from modules import attention as A
from modules import reader_job
from modules.heal import act
from modules.heal import incidents as I
from modules.readers import adjacency_log as AL


def _epoch(iso: str) -> float:
    """Loki's receive time, ``2026-11-03T01:22:37.666791+00:00``, as an epoch."""
    whole, frac = iso[:19], iso[19:].split("+")[0]
    return calendar.timegm(tuple(int(x) for x in whole.replace("T", "-").replace(":", "-")
                                 .split("-")) + (0, 0, 0)) + float(frac or 0)


#: r4's line: received 2026-11-03T01:22:37.666791Z, labels device=r4, job=network_syslog.
R4_AT = _epoch("2026-11-03T01:22:37.666791+00:00")
R4 = ("Nov  3 01:22:37 r4 5236: r4: Nov  3 01:22:36.487 UTC: %OSPF-4-DUP_RTRID_NBR: OSPF "
      "detected duplicate router-id 192.0.2.14 from 192.0.2.42 on interface GigabitEthernet5")
#: r6's line: received 2026-11-03T01:22:39.938405Z, labels device=r6, job=network_syslog.
R6_AT = _epoch("2026-11-03T01:22:39.938405+00:00")
R6 = ("Nov  3 01:22:39 192.0.2.16 8670: r6: Nov  3 01:22:38.888: %OSPF-4-DUP_RTRID_NBR: OSPF "
      "detected duplicate router-id 192.0.2.14 from 192.0.2.41 on interface GigabitEthernet2")
#: NOT a capture: Cisco's documented OSPFv3 form, an IPv6 link-local neighbour.
V3 = ("Nov  3 01:30:00 r4 5300: r4: Nov  3 01:30:00.000 UTC: %OSPFv3-4-DUP_RTRID_NBR: OSPFv3 "
      "detected duplicate router-id 192.0.2.14 from FE80::5054:FF:FE04:2 on interface "
      "GigabitEthernet5")
#: NOT a capture: Cisco's documented area form.
AREA = ("Nov  3 01:30:00 r7 900: r7: Nov  3 01:30:00.000 UTC: %OSPF-4-DUP_RTRID_AREA: Detected "
        "router with duplicate router ID 192.0.2.14 in area 0")
#: A real adjacency line of the same week (tests/test_adjacency_log.py's OSPF_DOWN): no
#: duplicate, so nothing here.
ADJCHG = ("Oct 18 01:41:46 r1 9973: r1: Oct 18 01:41:45.392 UTC: %OSPF-5-ADJCHG: Process 1, "
          "Nbr 192.0.2.24 on GigabitEthernet2 from 2WAY to DOWN, Neighbor Down: Dead timer "
          "expired")

POP = [("Lab", "r4"), ("Lab", "r6"), ("Lab", "r7"), ("Lab", "r1")]
#: Committed intent's answers for Lab (`attention._peer_names`): r4 holds the id and
#: 192.0.2.41, r6 holds 192.0.2.42 (as in R8: r6 was given r4's id).
PEERS = {"192.0.2.14": "r4", "192.0.2.41": "r4", "192.0.2.42": "r6",
         "fe80::5054:ff:fe04:2": "r6"}
KEY = AL.duplicate_key("Lab", "OSPF", "192.0.2.14")


def _ns(epoch):
    return int(epoch * 1e9)


def _read(lines, now=R6_AT + 60):
    """The reader at *now*, Loki answering the duplicate query with *lines* and the adjacency
    query with none."""
    def ask(query, start, end):
        return list(lines) if AL.DUP_PATTERN in query else []
    return AL.read(clock=lambda: now, population=POP, job='job="network_syslog"', ask=ask)


def _cached(value, at):
    return {"state": "ok", "doc": {"last_good": {"value": value, "value_at": AL._iso(at),
                                                 "read_started": at},
                                   "stale_after_seconds": 300}}


def _rows(value, at, monkeypatch, peers=None):
    monkeypatch.setattr(A, "_peer_names", lambda ln, cache: dict(PEERS if peers is None
                                                                 else peers))
    res = A.adjacency_log_source(cached=_cached(value, at), planned=[],
                                 receipts=lambda ln, dev: [])
    return res, [r for r in res["rows"] if r["kind"] == "duplicate_router_id"]


BOTH = [(_ns(R4_AT), R4), (_ns(R6_AT), R6)]


class TestTheLines:
    def test_r4_s_real_line(self):
        assert AL.duplicate(R4, "r4") == {"protocol": "OSPF", "variant": "NBR",
                                          "router_id": "192.0.2.14", "from": "192.0.2.42",
                                          "interface": "GigabitEthernet5", "area": ""}

    def test_r6_s_real_line_its_header_an_address(self):
        e = AL.duplicate(R6, "r6")
        assert (e["router_id"], e["from"], e["interface"]) == ("192.0.2.14", "192.0.2.41",
                                                                "GigabitEthernet2")

    def test_a_line_is_its_own_device_s_only(self):
        assert AL.duplicate(R4, "r6") == {} and AL.duplicate(R6, "r4") == {}

    def test_ospfv3_s_ipv6_neighbour(self):
        e = AL.duplicate(V3, "r4")
        assert (e["protocol"], e["router_id"], e["from"]) == ("OSPFv3", "192.0.2.14",
                                                              "fe80::5054:ff:fe04:2")

    def test_the_area_variant(self):
        e = AL.duplicate(AREA, "r7")
        assert (e["variant"], e["router_id"], e["area"], e["from"]) == ("AREA", "192.0.2.14",
                                                                          "0", "")

    @pytest.mark.parametrize("line", [
        ADJCHG,
        R4.replace("192.0.2.14", "r6-loopback"),                  # no router id where one is
        R4.replace("from 192.0.2.42", "from somewhere"),          # no address where one is
        R4.replace("DUP_RTRID_NBR", "DUP_RTRID_NBRX"),            # another mnemonic
        R4.replace("%OSPF-4-", "OSPF-4-"),                        # no mnemonic
        "r4: OSPF detected duplicate router-id 192.0.2.14 from 192.0.2.42 on interface G5",
    ])
    def test_a_line_that_is_not_one_is_none(self, line):
        assert AL.duplicate(line, "r4") == {}


class TestTheReader:
    def test_both_routers_reports_of_one_id_in_one_group(self):
        v = _read(BOTH)
        g = v["duplicates"][KEY]
        assert sorted(g["reports"]) == ["r4", "r6"] and v["duplicate_lines"] == 2
        r4, r6 = g["reports"]["r4"], g["reports"]["r6"]
        assert (r4["neighbors"], r4["interfaces"]) == (["192.0.2.42"], ["GigabitEthernet5"])
        assert (r6["neighbors"], r6["interfaces"]) == (["192.0.2.41"], ["GigabitEthernet2"])
        assert r4["last_epoch"] == pytest.approx(R4_AT), "Loki's receive time, not the device's"
        assert AL.still_logged(g, R6_AT + 60) == ["r4", "r6"]

    def test_its_own_query_and_window(self):
        asked = []
        AL.read(clock=lambda: R6_AT, population=POP, job='job="network_syslog"',
                ask=lambda q, s, e: asked.append((q, s, e)) or [])
        q, s, e = asked[1]
        assert q == '{job="network_syslog"} |~ `' + AL.DUP_PATTERN + "`"
        assert e - s == AL.DUP_WINDOW_SECONDS

    def test_a_full_page_is_refused_as_partial(self, monkeypatch):
        monkeypatch.setattr(AL, "DUP_LIMIT", 2)
        with pytest.raises(reader_job.Truncated):
            _read(BOTH)

    def test_lines_that_are_not_one_make_no_group(self):
        assert _read([(_ns(R4_AT), ADJCHG), (_ns(R4_AT), R4.replace(" r4: ", " r9: "))]
                     )["duplicates"] == {}


class TestTheRow:
    def test_both_routers_the_id_and_each_interface_critical(self, monkeypatch):
        _res, rows = _rows(_read(BOTH), R6_AT + 60, monkeypatch)
        (r,) = rows
        assert r["what"] == "r4 and r6 both claim OSPF router-id 192.0.2.14"
        assert r["level"] == "danger" and r["devices"] == ["r4", "r6"]
        assert "r4 logged it from 192.0.2.42 (r6) on GigabitEthernet5" in r["cause"]
        assert "r6 logged it from 192.0.2.41 (r4) on GigabitEthernet2" in r["cause"]
        assert "Committed intent gives 192.0.2.14 to r4, so r6 departed" in r["cause"]
        assert r["action"]["href"] == "/v2/device/r6?tab=intent&list=Lab"
        assert "r4 and r6" in r["action"]["label"]
        assert r["operands"]["claimers"] == ["r4", "r6"]

    def test_it_clears_when_the_line_stops(self, monkeypatch):
        assert A.CLEARS[("adjacency_log", "duplicate_router_id")][0] == ("resolves",)
        assert f"{AL.QUIET_SECONDS} s" in A.CLEARS[("adjacency_log", "duplicate_router_id")][1]
        _res, rows = _rows(_read(BOTH), R6_AT + 60, monkeypatch)
        assert rows[0]["clears"]["ways"] == ["resolves"] and not rows[0]["acknowledge"]
        later = R6_AT + AL.QUIET_SECONDS + 1
        _res, rows = _rows(_read(BOTH, now=later), later, monkeypatch)
        assert rows == [], "no line within the quiet time: the duplicate no longer logged"

    def test_one_device_alone_is_named_alone_beside_the_address_it_saw(self, monkeypatch):
        one = _read([(_ns(R4_AT), R4)])
        _res, (r,) = _rows(one, R6_AT + 60, monkeypatch, peers={})
        assert r["what"] == ("r4 logged a duplicate OSPF router-id 192.0.2.14 from the "
                             "neighbour at 192.0.2.42")
        assert r["devices"] == ["r4"]
        _res, (r,) = _rows(one, R6_AT + 60, monkeypatch)
        assert r["what"] == ("r4 logged a duplicate OSPF router-id 192.0.2.14: r6 "
                             "(192.0.2.42) claims it too"), "named by committed intent"
        assert r["devices"] == ["r4", "r6"]

    def test_ospfv3_over_ipv6(self, monkeypatch):
        at = R4_AT + 500
        v = _read([(_ns(at), V3)], now=at + 30)
        _res, (r,) = _rows(v, at + 30, monkeypatch)
        assert r["what"] == ("r4 logged a duplicate OSPFv3 router-id 192.0.2.14: r6 "
                             "(fe80::5054:ff:fe04:2) claims it too")
        assert r["level"] == "danger"

    def test_a_line_that_is_not_one_raises_nothing(self, monkeypatch):
        res, rows = _rows(_read([(_ns(R4_AT), ADJCHG)]), R6_AT + 60, monkeypatch)
        assert rows == [] and res["state"] == "read"
        assert "0 id(s) still logged" in res["checked"], "the line Loki gave, counted, not raised"


class TestR8Verify:
    """R8's verify, "no duplicate router-id logged" (docs/HEAL_TO_INTENT.md section 15 row 6),
    reads the trigger's store again (`act.read_symptom`)."""

    TRIGGER = {"kind": "duplicate_router_id", "source": "adjacency-log", "protocol": "OSPF",
               "router_id": "192.0.2.14", "related": ["r4"], "words": "r6 logged it"}

    def test_it_is_a_symptom_trigger_an_incident_takes(self):
        assert act.symptom_triggers([self.TRIGGER]) == [self.TRIGGER]
        assert "duplicate_router_id" in I.SYMPTOM_KINDS
        assert act._store_for(self.TRIGGER) == "adjacency-log"

    def test_still_logged_on_the_real_lines_is_present(self):
        doc = _cached(_read(BOTH), R6_AT + 60)["doc"]
        assert act.judge(self.TRIGGER, doc, "Lab", "r6", since=R4_AT - 30) == "present"

    def test_gone_once_the_lines_stop(self):
        later = R6_AT + AL.QUIET_SECONDS + 1
        doc = _cached(_read(BOTH, now=later), later)["doc"]
        assert act.judge(self.TRIGGER, doc, "Lab", "r6", since=R4_AT - 30) == "gone"

    def test_a_line_before_the_change_is_not_this_change_s(self):
        doc = _cached(_read(BOTH), R6_AT + 60)["doc"]
        assert act.judge(self.TRIGGER, doc, "Lab", "r6", since=R6_AT + 1) == "gone"

    def test_another_network_s_id_is_not_this_one_s(self):
        doc = _cached(_read(BOTH), R6_AT + 60)["doc"]
        assert act.judge(self.TRIGGER, doc, "Branch", "r6", since=R4_AT - 30) == "gone"

    def test_a_value_read_with_no_loki_configured_is_neither_gone_nor_present(self):
        """The reader's value with no Loki configured holds no line because none was read
        (`AL.read`, ``configured`` False): the verify waits, and never passes on it."""
        value = AL.read(clock=lambda: R6_AT + 60, population=[("Lab", "r4"), ("Lab", "r6")],
                        configured=False)
        doc = _cached(value, R6_AT + 60)["doc"]
        assert value["configured"] is False and value["duplicates"] == {}
        assert act.judge(self.TRIGGER, doc, "Lab", "r6", since=R4_AT - 30) == "stale"

    def test_the_verify_fires_still_logged_at_its_bound(self):
        clock = {"t": R6_AT + 10}

        def read(store):
            assert store == "adjacency-log"
            # Each read finds the device still logging it, about every 66 s (C2327).
            lines = BOTH + [(_ns(clock["t"] - 20), R6)]
            return _cached(_read(lines, now=clock["t"]), clock["t"])

        got = act.read_symptom("Lab", "r6", [self.TRIGGER], since=R4_AT - 30,
                               clock=lambda: clock["t"],
                               sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
                               read=read, request=lambda store: True)
        assert got["state"] == "present", got
        assert f"after {act.SYMPTOM_SECONDS['duplicate_router_id']} s" in got["words"]
