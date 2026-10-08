"""Test the logging path (modules/nsot/logging_path.py; NSOT_READS.md section 11).

Lines are REAL: r3's and s3's heartbeat lines as Loki returned them
(`tests/fixtures/loki/device_logs.json`, captured 2026-10-01), the heartbeat's text replaced by
the run's token and nothing else. No `send log` line had reached this Loki when this was
written (0 in seven days, measured 2026-10-08), so the watch relies on nothing IOS wraps around
one: only the device's anchored name and the token.

Loki and the clock are faked at the watch's seams (`ask`, `clock`, `sleep`); the send goes
through the real reads engine with its session faked, so the refusal, the hold and the record
run for real.
"""

import json
import os

import pytest

from modules.nsot import logging_path as LP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN = "20261008T161300123456Z-0123456789abcdef0123456789abcdef"
TOKEN = LP.token(RUN)


def _real_line(host: str) -> str:
    with open(os.path.join(ROOT, "tests", "fixtures", "loki", "device_logs.json"),
              encoding="utf-8") as fh:
        body = json.load(fh)[host]["body"]
    line = next(v[1] for s in body["data"]["result"] for v in s["values"]
                if "NMAS-HEARTBEAT: NMAS-HEARTBEAT" in v[1])
    return line.replace("NMAS-HEARTBEAT: NMAS-HEARTBEAT", TOKEN)


class Loki:
    """Loki at the watch's seam: each host's line appears at its own time; every query
    counted."""

    def __init__(self, arrive=None, why="", lines=None):
        self.arrive, self.why, self.queries = dict(arrive or {}), why, []
        self.lines = lines or {h: _real_line(h) for h in ("r3", "s3")}

    def __call__(self, start_ns, end_ns, tok, limit):
        self.queries.append((start_ns, end_ns, tok, limit))
        if self.why:
            return None, self.why
        out = [(int(t * 1e9), self.lines[h]) for h, t in self.arrive.items()
               if start_ns <= int(t * 1e9) <= end_ns]
        assert tok == TOKEN
        return out, ""


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s


def _watch(sent_at, loki, clock=None):
    clock = clock or Clock(max(sent_at.values()) if sent_at else 1000.0)
    return LP.watch(sent_at, TOKEN, ask=loki, clock=clock, sleep=clock.sleep), loki, clock


class TestTheWatch:
    def test_received_after_n_seconds_and_not_received_within_30(self):
        got, loki, clock = _watch({"r3": 1000.0, "s3": 1000.0}, Loki(arrive={"r3": 1003.4}))
        assert got["r3"]["state"] == LP.RECEIVED and got["r3"]["after_s"] == 3.4
        assert got["r3"]["words"] == "received after 3.4 s"
        assert got["s3"]["state"] == LP.NOT_RECEIVED
        assert got["s3"]["words"] == "not received within 30 s"
        assert got["s3"]["sent_iso"] == "1970-01-01T00:16:40Z"
        assert got["s3"]["until_iso"] == "1970-01-01T00:17:10Z"
        assert clock.now >= 1000.0 + LP.WAIT_SECONDS, "it waited the whole window for s3"

    def test_it_stops_as_soon_as_every_line_is_in(self):
        got, loki, clock = _watch({"r3": 1000.0, "s3": 1000.0},
                                  Loki(arrive={"r3": 1001.0, "s3": 1002.5}))
        assert {h: r["state"] for h, r in got.items()} == {"r3": LP.RECEIVED, "s3": LP.RECEIVED}
        assert clock.now < 1000.0 + 6, clock.now

    def test_one_query_per_poll_for_the_whole_run_never_one_per_device(self):
        """Enterprise scale: 900 devices are one query a poll, its page sized to the run."""
        hosts = {f"x{i}": 1000.0 for i in range(900)}
        _got, loki, _clock = _watch(hosts, Loki())
        polls = LP.WAIT_SECONDS / LP.POLL_SECONDS + 1
        assert len(loki.queries) <= polls, len(loki.queries)
        assert loki.queries[0][3] >= 900

    def test_a_name_is_anchored_never_a_prefix(self):
        """r30's line is not r3's (the Logs tab's anchor, C13). r30's line is r3's real line
        with its two names edited, nothing else."""
        r30 = _real_line("r3").replace(" r3 ", " r30 ").replace(" r3: ", " r30: ")
        assert " r30: " in r30 and " r3: " not in r30
        loki = Loki(arrive={"r30": 1001.0}, lines={"r30": r30})
        got, _loki, _clock = _watch({"r3": 1000.0}, loki)
        assert got["r3"]["state"] == LP.NOT_RECEIVED, got
        got, _loki, _clock = _watch({"r30": 1000.0}, loki)
        assert got["r30"]["state"] == LP.RECEIVED, "the control: r30's own line is found"

    def test_late_is_said_as_late(self):
        got, _l, _c = _watch({"r3": 1000.0}, Loki(arrive={"r3": 1031.0}),
                             clock=Clock(1031.0))
        assert got["r3"]["state"] == LP.NOT_RECEIVED
        assert "received after 31.0 s, past the 30 s window" == got["r3"]["words"]

    @pytest.mark.parametrize("why", ["Loki could not be asked: Could not connect to <loki>",
                                     "Loki's answer was cut at its page size (100 lines)"])
    def test_an_unreadable_watch_decides_nothing(self, why):
        """Never "not received" when Mercury could not look."""
        got, _l, _c = _watch({"r3": 1000.0}, Loki(why=why))
        assert got["r3"]["state"] == LP.UNKNOWN and why in got["r3"]["words"], got

    def test_a_full_page_is_a_cut_answer(self, monkeypatch):
        class Resp:
            def json(self):
                return {"data": {"result": [{"values": [[str(i), "x"] for i in range(100)]}]}}

        class Fake:
            def _get(self, path, **kw):
                return {"ok": True, "response": Resp()}

        monkeypatch.setattr(LP, "_loki", lambda: Fake())
        lines, why = LP._ask(0, 1, TOKEN, 100)
        assert lines is None and "cut at its page size (100 lines)" in why


# --------------------------------------------------------------------------- send, watch, record

DEVICES = [{"hostname": "r3", "ip": "192.0.2.13"}, {"hostname": "s3", "ip": "192.0.2.23"},
           {"hostname": "r1", "ip": "192.0.2.11"}]


@pytest.fixture
def lab(monkeypatch, tmp_path):
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path / n))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda p: [dict(d) for d in DEVICES])
    monkeypatch.setattr("modules.list_settings.value", lambda ln, k, d=None: d)
    sent = []
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, c, **kw: sent.append((conn, c)) or "")

    class Configured:
        def is_configured(self):
            return True

    monkeypatch.setattr(LP, "_loki", lambda: Configured())
    return sent


def _s3_body():
    with open(os.path.join(ROOT, "tests", "fixtures", "loki", "device_logs.json"),
              encoding="utf-8") as fh:
        return json.load(fh)["s3"]["body"]


def _last_line(query):
    """Loki's answer to "s3's last line": its real capture."""
    assert "s3:" in query

    class Resp:
        def json(self):
            return _s3_body()

    return {"ok": True, "response": Resp()}


def _session(dev, fn):
    if dev["hostname"] == "r1":
        raise OSError("TCP connection to device failed (192.0.2.11:22)")
    return fn(dev["hostname"])


class TestTheTest:
    def test_send_watch_record(self, lab):
        from modules.nsot import reads
        import time
        clock = Clock(time.time() + 1)
        loki = Loki(arrive={"r3": clock.now + 2.0})
        record = LP.run("Lab", ["r3", "s3", "r1"], "op@example.invalid", run_id=RUN,
                        session=_session, ask=loki, clock=clock, sleep=clock.sleep,
                        last_ask=_last_line)
        assert sorted(lab) == [("r3", LP.command(RUN)), ("s3", LP.command(RUN))]
        assert LP.command(RUN).startswith("send log 6 MERCURY-LOGTEST ")
        res = record["logging_path"]["results"]
        assert res["r3"]["state"] == LP.RECEIVED
        assert res["s3"]["state"] == LP.NOT_RECEIVED
        last = max(int(v[0]) for s in _s3_body()["data"]["result"] for v in s["values"])
        assert res["s3"]["last_iso"] == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(last / 1e9))
        assert "last_iso" not in res["r3"], "only a device not received is looked up"
        assert res["r1"]["state"] == LP.NOT_SENT and "TCP connection" in res["r1"]["words"]
        assert record["logging_path"]["counts"] == {"received": 1, "not received": 1,
                                                    "not sent": 1}
        stored = reads.get("Lab", RUN)
        assert stored["logging_path"] == record["logging_path"], "recorded with the run"
        assert stored["purpose"] == "test the logging path"

    def test_no_loki_is_a_refusal_before_any_device(self, lab, monkeypatch):
        class Unset:
            def is_configured(self):
                return False

        monkeypatch.setattr(LP, "_loki", lambda: Unset())
        with pytest.raises(LP.Refused, match="Loki is not configured"):
            LP.run("Lab", ["r3"], "op@example.invalid", session=_session)
        assert lab == []
        assert LP.start("Lab", ["r3"], "op@example.invalid")["refused"].startswith(
            "Refused: Loki is not configured")

    def test_the_token_is_the_runs_own(self):
        other = RUN[:-32] + "f" * 32
        assert LP.token(RUN) != LP.token(other)
        from modules import readonly_commands as rc
        assert rc.refusal(LP.command(RUN), rc.EXTRAS) == "", "Tier 1 as the engine judges it"
