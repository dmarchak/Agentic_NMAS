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

import re
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

    def test_the_row_carries_its_unexplained_drops_times(self):
        """C2316: the events an acknowledgement is judged against, oldest first."""
        res = A.adjacency_log_source(cached=_cached(_read()), planned=[],
                                     receipts=lambda ln, dev: [])
        r = next(x for x in res["rows"] if "|r1|" in x["id"])
        assert r["operands"]["events"] == pytest.approx([NOW - 7200, NOW - 3600, NOW - 600])

    def test_an_unread_reader_is_a_source_that_says_so(self):
        res = A.adjacency_log_source(cached={"state": "absent", "why": "never run", "doc": None},
                                     planned=[], receipts=lambda ln, dev: [])
        assert res["state"] == "unreadable"
        assert any("not read yet" in r["cause"] for r in res["rows"]), res["rows"]


class TestNoLokiConfigured:
    """The operator, 2026-11-10, on the Lab 9 kit (no Loki): "reader:adjacency-log … marked
    CRITICAL (severity by impact)". With no Loki URL the read raised (`NoSyslogJob`, "Loki
    could not be asked which job holds the devices' syslog: Not configured"; measured on a
    scratch store 2026-11-11), so the reader never succeeded and job health drew it critical.
    No Loki is a state: the read answers ``configured`` False with nothing asked, the reader
    is ok, and Needs attention says it once under What was checked. A Loki that IS configured
    and does not answer is the failure it was."""

    POP = [("Lab", "r1"), ("Lab", "r2")]

    def _unconfigured(self, monkeypatch):
        """No Loki URL is stored in the run's own data folder, so the reader's real question
        answers no; the syslog job's matcher and Loki's client fail if either is asked."""
        from modules import device_logs
        from modules.integrations.loki import LokiIntegration

        def never(*a, **k):
            raise AssertionError("Loki was asked with none configured")

        assert LokiIntegration().is_configured() is False, "this run's store holds no Loki URL"
        monkeypatch.setattr(device_logs, "job_matcher", never)
        monkeypatch.setattr(LokiIntegration, "_get", never)

    def test_the_read_answers_not_configured_and_asks_nothing(self, monkeypatch):
        self._unconfigured(monkeypatch)
        v = AL.read(clock=lambda: NOW, population=self.POP)
        assert v["configured"] is False
        assert (v["adjacencies"], v["duplicates"], v["lines"], v["duplicate_lines"]) == (
            {}, {}, 0, 0)
        assert v["devices"] == 2 and v["read_at"] == NOW

    def test_a_loki_given_or_configured_is_read_as_before(self):
        v = AL.read(clock=lambda: NOW, population=[("Lab", "r1")], job='job="syslog"',
                    ask=lambda q, s, e: [(_ns(NOW - 600), OSPF_DOWN)], configured=None)
        assert v["configured"] is True and len(v["adjacencies"]) == 1

    def _run(self, monkeypatch, tmp_path, read):
        import dataclasses

        from modules import config

        monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
        reader = dataclasses.replace(AL.READER, read=read)
        doc = reader_job.run_once(reader)
        (row,) = reader_job.health_rows(population=[reader])
        return doc, row

    def test_the_reader_is_ok_with_no_loki_and_failing_with_one_that_does_not_answer(
            self, monkeypatch, tmp_path):
        self._unconfigured(monkeypatch)
        doc, row = self._run(monkeypatch, tmp_path,
                             lambda: AL.read(clock=lambda: NOW, population=self.POP))
        assert doc["last_attempt"]["ok"] is True, doc["last_attempt"]
        assert (row["unit"], row["state"]) == ("reader:adjacency-log", "ok")

        def down(q, s, e):
            raise RuntimeError("Loki could not be asked: Could not connect")

        doc, row = self._run(monkeypatch, tmp_path / "configured",
                             lambda: AL.read(clock=lambda: NOW, population=self.POP,
                                             job='job="syslog"', ask=down))
        assert doc["last_attempt"]["ok"] is False
        assert row["state"] == "never_succeeded", "configured and not answering: a failure"
        assert A._JOB_STATES[row["state"]][1] == "danger", "its severity is as it was"

    def test_needs_attention_says_it_once_under_what_was_checked_and_raises_nothing(
            self, monkeypatch):
        self._unconfigured(monkeypatch)
        value = AL.read(clock=lambda: NOW, population=self.POP)
        res = A.adjacency_log_source(cached=_cached(value), planned=[],
                                     receipts=lambda ln, dev: [])
        assert res["state"] == "read" and res["rows"] == []
        assert res["checked"] == ("no Loki configured: an adjacency that drops and comes back "
                                  "between two scrapes, and a duplicate router-id, are only in "
                                  "the devices' logs, so neither can be seen")
        assert res["reader"] == "adjacency-log" and res["stale_after_seconds"] == 300


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

    K = AL.key("Lab", "r1", "OSPF", "192.0.2.24")

    def _acknowledged(self, hours=""):
        """r1's row acknowledged now; the acknowledgement's own time, by its record."""
        from modules import acknowledgements as ACK
        got = A.acknowledge(f"adjacency_log:{self.K}", self.K, "the R3 walk, done on purpose",
                            by="op@example.invalid", verified="access", hours=hours)
        assert got["ok"] and got["hides_now"], got
        return ACK._epoch(got["acknowledged"]["at"]), got

    def _then(self, world, drops, clock):
        """The reader's next read at *clock*: the week's lines and *drops* more."""
        lines = _lines() + [(_ns(t), OSPF_DOWN) for t in drops]
        world["value"] = AL.read(clock=lambda: clock, population=[("Lab", "r1"), ("Lab", "r2")],
                                 job='job="syslog"', ask=lambda q, s, e: lines)
        world["at"] = time.time() + 2
        return {r["id"]: r for r in self._page()["rows"]}

    def test_one_new_drop_inside_the_band_raises_the_row(self, world):
        """C2316, the operator's case (blind session 6, 2026-11-03: R8's drop 20 min after "R3
        walk done on purpose" was caught only because the count passed the band): after the
        acknowledgement, and after its cycle settled, one drop inside the band raises the row,
        naming the acknowledgement and the drop's time."""
        t, _got = self._acknowledged()
        rows = self._then(world, [t + 1200], t + 1300)
        row = rows[f"adjacency_log:{self.K}"]
        assert row["what"].endswith("went down 4 times in the last day"), row["what"]
        assert row["operands"]["band_reading"]["value"] <= row["operands"]["band"], "in band"
        # Its time as its instant, which the screen draws in its viewer's zone (C3290).
        assert re.search(r"Acknowledged by op@example.invalid at \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ;",
                         row["cause"]), row["cause"]
        assert ("it covers what came before it and the cycle then under way until it "
                "settled, and this came after, at ") in row["cause"], row["cause"]

    def test_the_cycle_under_way_is_covered_until_it_settles(self, world):
        """A drop a minute before the acknowledgement, and another five minutes after it: the
        same down/up cycle, inside the band, still covered; 20 min after that one, raised."""
        t, _got = self._acknowledged()
        rows = self._then(world, [t - 60, t + 300], t + 400)
        assert f"adjacency_log:{self.K}" not in rows
        rows = self._then(world, [t - 60, t + 300, t + 300 + 1200], t + 1600)
        assert f"adjacency_log:{self.K}" in rows

    def test_a_planned_quiet_period_covers_everything_to_its_expiry_and_nothing_after(
            self, world):
        t, got = self._acknowledged(hours="2")
        assert got["acknowledged"]["until"] and "a quiet period until " in got["words"]
        burst = [t + 600 + 60 * i for i in range(6)]            # past the band of five
        rows = self._then(world, burst, t + 1000)
        assert f"adjacency_log:{self.K}" not in rows, "inside the quiet period, band or not"
        page = A.needs_attention(sources=[A.adjacency_log_source])
        assert any(k.get("until") for k in page["acknowledged"]), "its expiry is drawn"
        rows = self._then(world, [t + 2 * 3600 + 60], t + 2 * 3600 + 120)
        row = rows[f"adjacency_log:{self.K}"]
        assert "for a quiet period until " in row["cause"], row["cause"]

    def test_a_quiet_period_is_whole_hours_up_to_a_day(self, world):
        for bad in ("0", "25", "1.5", "an hour"):
            got = A.acknowledge(f"adjacency_log:{self.K}", self.K, "the R3 walk, done on purpose",
                                by="op@example.invalid", verified="access", hours=bad)
            assert got["ok"] is False and "1 to 24 whole hours" in got["error"], (bad, got)
