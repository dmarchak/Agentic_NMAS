"""C589 (Core 1.0's K2): routing adjacencies a managed device LOGGED going down, which a drop
between two scrapes leaves only in the log.

The lines are REAL, captured read-only from the lab's Loki on 2026-10-19 (r1's and r4's), each
address moved to 192.0.2.0/24 (the only edit). The lab logged no BGP adjacency change in the
week, so BGP's lines are IOS's documented `%BGP-5-ADJCHANGE` form, not a capture, with an IPv6
neighbour beside the IPv4 one (docs/IPV6_PARITY.md's standing rule).

- each shape parsed: OSPF and OSPFv3 down and up, BGP down and up, IPv4 and IPv6;
- the reader keeps the DOWN lines of managed devices, per adjacency: the last day's drops, the
  count per day over the week, and its band (the highest day); a full page is refused;
- Needs attention: one row per adjacency, a drop a planned restart or a deploy explains
  counted apart and never raised; the row acknowledged within its band stays hidden while the
  day's count holds, and returns above it.
"""

import time

import pytest

from modules import attention as A
from modules import reader_job
from modules.readers import adjacency_log as AL

OSPF_DOWN = ("Oct 18 01:41:46 r1 9973: r1: Oct 18 01:41:45.392 UTC: %OSPF-5-ADJCHG: Process 1, "
             "Nbr 192.0.2.24 on GigabitEthernet2 from 2WAY to DOWN, Neighbor Down: Dead timer "
             "expired")
OSPF_FULL = ("Oct 17 19:38:07 r4 7161: r4: Oct 17 19:38:06.725 UTC: %OSPF-5-ADJCHG: Process 1, "
             "Nbr 192.0.2.11 on GigabitEthernet3 from LOADING to FULL, Loading Done")
OSPFV3_DOWN = ("Oct 18 19:38:40 r1 10535: r1: Oct 18 19:38:39.298 UTC: %OSPFv3-5-ADJCHG: "
               "Process 1, Nbr 192.0.2.13 on GigabitEthernet2 from 2WAY to DOWN, Neighbor "
               "Down: Dead timer expired")
OSPFV3_FULL = ("Oct 17 13:23:58 r4 7054: r4: Oct 17 13:23:57.930 UTC: %OSPFv3-5-ADJCHG: "
               "Process 1, Nbr 192.0.2.11 on GigabitEthernet3 from LOADING to FULL, Loading "
               "Done")
# IOS's documented form (not captured: the lab logged none in the week).
BGP4_DOWN = ("Oct 18 02:00:00 r2 100: r2: Oct 18 02:00:00.000 UTC: %BGP-5-ADJCHANGE: neighbor "
             "192.0.2.2 Down BGP Notification sent")
BGP6_DOWN = ("Oct 18 02:00:00 r2 101: r2: Oct 18 02:00:00.000 UTC: %BGP-5-ADJCHANGE: neighbor "
             "2001:DB8::2 Down Interface flap")
BGP6_UP = ("Oct 18 02:01:00 r2 102: r2: Oct 18 02:01:00.000 UTC: %BGP-5-ADJCHANGE: neighbor "
           "2001:DB8::2 Up ")

#: The reads happen NOW, by the wall clock: an acknowledgement is stamped by the wall clock, and
#: `acknowledgements.within_band` judges against whichever of it and the reader's value is
#: newer (C533), so a reader value stamped at a fixed past moment would lose to it.
NOW = float(int(time.time()))


class TestEachShape:
    def test_ospf_down(self):
        e = AL.event(OSPF_DOWN, "r1")
        assert (e["protocol"], e["neighbor"], e["interface"], e["from"], e["down"]) == (
            "OSPF", "192.0.2.24", "GigabitEthernet2", "2WAY", True)
        assert e["reason"] == "Neighbor Down: Dead timer expired"

    def test_ospf_up_is_not_a_drop(self):
        e = AL.event(OSPF_FULL, "r4")
        assert e["to"] == "FULL" and e["down"] is False

    def test_ospfv3_down_and_up(self):
        assert AL.event(OSPFV3_DOWN, "r1")["protocol"] == "OSPFv3"
        assert AL.event(OSPFV3_DOWN, "r1")["down"] is True
        assert AL.event(OSPFV3_FULL, "r4")["down"] is False

    def test_bgp_ipv4_and_ipv6_neighbours(self):
        v4, v6 = AL.event(BGP4_DOWN, "r2"), AL.event(BGP6_DOWN, "r2")
        assert (v4["protocol"], v4["neighbor"], v4["down"]) == ("BGP", "192.0.2.2", True)
        assert (v6["neighbor"], v6["down"], v6["reason"]) == ("2001:DB8::2", True,
                                                              "Interface flap")
        assert AL.event(BGP6_UP, "r2")["down"] is False

    def test_another_device_s_line_is_not_this_one_s(self):
        assert AL.event(OSPF_DOWN, "r10") == {} or AL.event(OSPF_DOWN, "r10").get("neighbor")
        assert AL.read(clock=lambda: NOW, population=[("Lab", "r10")], job='job="syslog"',
                       ask=lambda q, s, e: [(int((NOW - 60) * 1e9), OSPF_DOWN)]
                       )["adjacencies"] == {}


def _ns(epoch):
    return int(epoch * 1e9)


def _lines():
    """r1 toward 192.0.2.24 down three times in the last day and five on one day earlier in
    the week; r4's up line; r2's BGP over IPv6 down once; a line of a device not managed."""
    out = [(_ns(NOW - 600), OSPF_DOWN), (_ns(NOW - 3600), OSPF_DOWN),
           (_ns(NOW - 7200), OSPF_DOWN)]
    # Noon of the day three days back, so its five fall on one UTC day whatever the hour now.
    three_days = (NOW // 86400 - 3) * 86400 + 43200
    out += [(_ns(three_days - i * 60), OSPF_DOWN) for i in range(5)]
    out += [(_ns(NOW - 900), OSPF_FULL), (_ns(NOW - 1200), BGP6_DOWN),
            (_ns(NOW - 300), OSPF_DOWN.replace(" r1:", " r9:"))]
    return out


def _read(lines=None):
    return AL.read(clock=lambda: NOW, population=[("Lab", "r1"), ("Lab", "r4"), ("Lab", "r2")],
                   job='job="syslog"', ask=lambda q, s, e: list(lines or _lines()))


class TestTheReader:
    def test_one_entry_per_adjacency_with_the_day_s_drops_and_its_band(self):
        v = _read()
        r1 = v["adjacencies"][AL.key("Lab", "r1", "OSPF", "192.0.2.24")]
        assert len(r1["drops"]) == 3, "the last day's three, never the earlier week's"
        assert r1["drops"][0]["at"] == AL._iso(NOW - 600)            # newest first
        assert sum(r1["by_day"].values()) == 8 and r1["band"] == 5
        bgp = v["adjacencies"][AL.key("Lab", "r2", "BGP", "2001:DB8::2")]
        assert len(bgp["drops"]) == 1, "an IPv6 BGP neighbour, read like an IPv4 one"
        assert v["lines"] == len(_lines()) and v["devices"] == 3

    def test_up_lines_and_unmanaged_devices_make_no_entry(self):
        keys = set(_read()["adjacencies"])
        assert not any("|r4|" in k or "|r9|" in k for k in keys), keys

    def test_a_full_page_is_refused_as_partial(self, monkeypatch):
        monkeypatch.setattr(AL, "LIMIT", 3)
        with pytest.raises(reader_job.Truncated):
            _read([(_ns(NOW - i), OSPF_DOWN) for i in range(3)])

    def test_the_query_names_the_syslog_job_and_the_mnemonics(self):
        asked = []
        AL.read(clock=lambda: NOW, population=[("Lab", "r1")], job='job="syslog"',
                ask=lambda q, s, e: asked.append((q, s, e)) or [])
        q, s, e = asked[0]
        assert q.startswith('{job="syslog"} |~ `') and "OSPF" in q and "BGP-5-ADJCHANGE" in q
        assert e - s == AL.WINDOW_DAYS * AL.DAY_SECONDS


def _cached(value, at=None):
    return {"state": "ok", "doc": {"last_good": {"value": value,
                                                 "value_at": AL._iso(NOW if at is None else at)},
                                   "stale_after_seconds": 300}}


class TestNeedsAttention:
    def test_one_row_per_adjacency_naming_its_count_and_band(self):
        res = A.adjacency_log_source(cached=_cached(_read()), planned=[],
                                     receipts=lambda ln, dev: [])
        rows = {r["id"]: r for r in res["rows"]}
        r = rows[f"adjacency_log:{AL.key('Lab', 'r1', 'OSPF', '192.0.2.24')}"]
        assert r["what"] == "r1's OSPF adjacency to 192.0.2.24 went down 3 times in the last day"
        assert "Dead timer expired" in r["cause"] and "highest daily count" in r["cause"]
        assert r["acknowledge"] and r["operands"]["band"] == 5
        assert r["operands"]["band_reading"]["value"] == 3
        assert r["level"] == "warning" and r["devices"] == ["r1"]
        assert len(rows) == 2, "r1's OSPF and r2's IPv6 BGP"

    def test_a_planned_restart_or_a_deploy_explains_a_drop(self):
        planned = [{"devices": ["r1"], "list": "Lab", "from": AL._iso(NOW - 700),
                    "until": AL._iso(NOW - 500), "by": "op", "why": "a planned reload"}]
        receipts = (lambda ln, dev: [{"at": AL._iso(NOW - 3600 + 120)}] if dev == "r1" else [])
        res = A.adjacency_log_source(cached=_cached(_read()), planned=planned, receipts=receipts)
        r = next(x for x in res["rows"] if "|r1|" in x["id"])
        assert r["what"].endswith("went down 1 time in the last day"), r["what"]
        assert "2 drop(s) inside a planned restart or a deploy, not raised" in res["checked"]

    def test_every_drop_explained_raises_nothing(self):
        planned = [{"devices": ["r1", "r2"], "list": "Lab", "from": AL._iso(NOW - 9000),
                    "until": AL._iso(NOW), "by": "op", "why": "a lab redeploy"}]
        res = A.adjacency_log_source(cached=_cached(_read()), planned=planned,
                                     receipts=lambda ln, dev: [])
        assert res["rows"] == [] and res["state"] == "read"

    def test_an_unread_reader_is_a_source_that_says_so(self):
        res = A.adjacency_log_source(cached={"state": "absent", "why": "never run", "doc": None},
                                     planned=[], receipts=lambda ln, dev: [])
        assert res["state"] == "unreadable"
        assert any("not read yet" in r["cause"] for r in res["rows"]), res["rows"]


class TestAcknowledgedWithinItsBand:
    @pytest.fixture
    def world(self, tmp_path, monkeypatch):
        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        state = {"value": _read(), "at": NOW}
        real = reader_job.read_cached
        monkeypatch.setattr(reader_job, "read_cached",
                            lambda name: _cached(state["value"], state["at"])
                            if name == "adjacency-log" else real(name))
        monkeypatch.setattr("modules.restarts.planned_rows", lambda: [])
        monkeypatch.setattr("modules.nsot.receipts.read",
                            lambda ln, dev="", limit=50: {"state": "absent", "rows": []})
        return state

    def _page(self):
        return A.needs_attention(sources=[A.adjacency_log_source])

    def test_acknowledged_it_stays_hidden_within_its_band_and_returns_above_it(self, world):
        rid = f"adjacency_log:{AL.key('Lab', 'r1', 'OSPF', '192.0.2.24')}"
        got = A.acknowledge(rid, AL.key("Lab", "r1", "OSPF", "192.0.2.24"),
                            "s3 is CPU-starved in the lab, C93: its hellos are late",
                            by="op@example.invalid", verified="access")
        assert got["ok"] and got["hides_now"], got
        assert got["acknowledged"]["band"] == 5
        assert rid not in {r["id"] for r in self._page()["rows"]}
        # The reader's next read, after the acknowledgement: six drops in the last day, above
        # the band of five. The row returns, saying why.
        more = _lines() + [(_ns(NOW - 60 * i - 30), OSPF_DOWN) for i in range(1, 4)]
        world["value"], world["at"] = _read(more), time.time() + 2
        row = next(r for r in self._page()["rows"] if r["id"] == rid)
        assert "above it" in row["cause"]
