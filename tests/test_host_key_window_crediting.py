"""C1389 (the operator, 2026-10-19): a new SSH host key is credited to the window that was the
operative statement when it was met, and a window that covers nothing more is not left open.

On the lab's redeploy two windows expecting new keys were declared: W1 for an attempt that
was abandoned, then W2 for the redeploy that ran. Eight new keys were met while both covered
their devices and `host_keys._window_for` took the FIRST in the record, so they named W1
(the abandoned one), and Needs attention drew W1's id ("Default|19:16:50Z|19:16:50Z"), which
read as a start and an end that were equal.

Through the real host-key record (`host_keys.check`, real RSA keys), the real planned-window
record and its ends, the real reader (`modules/readers/host_key_windows.py`), Needs
attention's real page, History's real timeline, the real API and the real host commands, on a
network whose devices are kept by IPv4 and IPv6 address alike (the store is keyed by
address):

- two overlapping windows: the key is credited to the LATER declaration, a device in the
  earlier one only stays with it, and a superseded window never takes a later key instead;
- the summaries count by credited window, so the superseded window claims none;
- the window is drawn by its own times, never by its id;
- the correction (`host_keys.recredit`, `scripts/nmas-host-key-recredit`) moves a key, keeps
  the old crediting on the record and in History, corrects the summaries, and refuses when
  the rule gives the same window, and over an unreadable record;
- abandoning: a window is ended at once (`POST /restarts/planned` with `end`,
  `nmas-planned-restart --end`), covers no later key or restart, and is summed up then;
- completing: a window every device of which has answered with its new key ends then, and its
  summary appears at once, not at its declared end plus the slack.
"""

import json
import os
import re
import time

import paramiko
import pytest

from modules import host_keys as HK
from modules import restarts

#: The network's devices: d1 by IPv4, d2 by IPv6 (both windows), d3 by IPv4 (the later window
#: only, as r6 was), d4 by IPv6 (the earlier window only).
ADDR = {"d1": "192.0.2.21", "d2": "2001:db8::22", "d3": "192.0.2.23", "d4": "2001:db8::24"}
WHY1 = "lab redeploy, first attempt"
WHY2 = "lab redeploy after the lab host's reboot"
BY = "op@example.invalid"


@pytest.fixture
def net(tmp_path, monkeypatch):
    import app as A
    from modules import device

    lists = tmp_path / "lists"
    list_dir = lists / "lab"
    list_dir.mkdir(parents=True)
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("modules.config.LISTS_DIR", str(lists))
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))
    monkeypatch.setattr("modules.device.get_device_lists",
                        lambda: [{"name": "Lab", "filename": "lab"}])
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
    f = device.fernet
    rows = [{"hostname": h, "device_type": "cisco_xe", "ip": ip, "username": "admin",
             "password": f.encrypt(b"Crediting-Pw-4k").decode(),
             "secret": f.encrypt(b"").decode(), "platform": "cisco_iosxe"}
            for h, ip in ADDR.items()]
    device.write_devices_csv(rows, str(list_dir / "devices.csv"))
    return {"client": A.app.test_client(), "data": str(data)}


@pytest.fixture(scope="module")
def keys():
    """Two RSA keys per device: before the redeploy, and after; and a third for d1."""
    out = {h: [paramiko.RSAKey.generate(1024) for _ in range(2)] for h in ADDR}
    out["d1"].append(paramiko.RSAKey.generate(1024))
    return out


def _fp(key) -> str:
    return HK.offered(key)["fingerprint"]


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _declare(devices, start, end, recorded, why):
    """A window as `restarts.record_planned` writes it (its fields, its silence's shape),
    appended to the real record at a chosen recording time, so two windows a few minutes
    apart are two seconds of the record apart as they were on the host."""
    row = {"devices": list(devices), "list": "Lab", "from": _iso(start), "until": _iso(end),
           "by": BY, "why": why, "via": "nmas-planned-restart", "recorded_at": _iso(recorded),
           "new_host_keys": True,
           "silence": {"state": "not_configured", "silences": [], "ends_at": "",
                       "error": "Grafana is not configured for this network"}}
    restarts._append("planned_restarts.jsonl", row)
    return row


def _first_contact(keys, hosts):
    for h in hosts:
        assert HK.check(ADDR[h], keys[h][0], owner="test:first-contact")["state"] == "kept"


def _overlapping(now, w1=("d1", "d2"), w2=("d1", "d2", "d3")):
    """The host's two windows: W1 recorded and open from ten minutes ago, W2 recorded and
    open from one minute ago, both for an hour."""
    a = _declare(w1, now - 600, now + 3000, now - 600, WHY1)
    b = _declare(w2, now - 60, now + 3540, now - 60, WHY2)
    return a, b


def _reader(now):
    from modules.readers import host_key_windows as W
    return W.read(clock=lambda: now)


def _window_rows():
    from modules import attention
    return attention.host_key_window_source()["rows"]


def _timeline():
    from modules import history_sources
    from modules.nsot.listref import resolve
    return history_sources.timeline(resolve("Lab"), kinds=["hostkeys"])["events"]


def _summary_lines(net):
    path = os.path.join(net["data"], HK.SUMMARIES)
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


class TestTheLaterDeclarationTakesTheKey:
    def test_both_windows_cover_it_and_the_later_one_takes_it(self, net, keys):
        _first_contact(keys, ADDR)
        now = time.time()
        w1, w2 = _overlapping(now, w1=("d1", "d2", "d4"))
        for h in ("d1", "d2", "d3", "d4"):
            assert HK.check(ADDR[h], keys[h][1], owner="test:redeploy")["state"] == "window"
        held = {h: HK.held(ADDR[h])["window"] for h in ADDR}
        # d1 (IPv4) and d2 (IPv6), in both windows: the later declaration's.
        assert held["d1"]["id"] == HK.window_id(w2) and held["d1"]["why"] == WHY2
        assert held["d2"]["id"] == HK.window_id(w2) and held["d2"]["why"] == WHY2
        # d3, in the later one only: the later one's, as r6's was.
        assert held["d3"]["id"] == HK.window_id(w2)
        # d4 (IPv6), in the earlier one only: still the earlier one's.
        assert held["d4"]["id"] == HK.window_id(w1) and held["d4"]["why"] == WHY1
        assert held["d1"]["recorded_at"] == w2["recorded_at"]

    def test_a_superseded_window_never_takes_a_later_key_instead(self, net, keys):
        """W2 took d1's new key; a second new key for d1, while both still cover it, is
        refused: W1 was superseded, and is never the one a later key is credited to."""
        _first_contact(keys, ("d1",))
        now = time.time()
        _overlapping(now)
        assert HK.check(ADDR["d1"], keys["d1"][1], owner="test:redeploy")["state"] == "window"
        with pytest.raises(HK.HostKeyRefused):
            HK.check(ADDR["d1"], keys["d1"][2], owner="test:a-second-key")
        assert HK.held(ADDR["d1"])["fingerprint"] == _fp(keys["d1"][1])


class TestTheSummariesCountByCreditedWindow:
    def test_the_superseded_window_claims_none(self, net, keys):
        _first_contact(keys, ("d1", "d2", "d3"))
        now = time.time()
        w1, w2 = _overlapping(now)
        for h in ("d1", "d2", "d3"):
            HK.check(ADDR[h], keys[h][1], owner="test:redeploy")
        later = now + 3540 + restarts.PLANNED_SLACK_SECONDS + 5
        _reader(later)
        counts = {s["window"]: s["count"] for s in _summary_lines(net)}
        assert counts == {HK.window_id(w1): 0, HK.window_id(w2): 3}, counts
        rows = _window_rows()
        assert [(r["what"], r["operands"]["count"]) for r in rows] == [
            (f"3 new host keys accepted during '{WHY2}'", 3)], rows
        assert sorted(rows[0]["devices"]) == ["d1", "d2", "d3"]


class TestTheWindowIsDrawnByItsTimes:
    def test_the_row_says_from_and_until_and_never_the_id(self, net, keys, monkeypatch):
        from modules import attention
        monkeypatch.setattr(attention, "SOURCES", [attention.host_key_window_source])
        _first_contact(keys, ("d1",))
        now = time.time()
        _w1, w2 = _overlapping(now, w1=("d1",), w2=("d1",))
        HK.check(ADDR["d1"], keys["d1"][1], owner="test:redeploy")
        _reader(now + 3540 + restarts.PLANNED_SLACK_SECONDS + 5)
        row = _window_rows()[0]
        wid = HK.window_id(w2)
        start = w2["from"].replace("T", " ").rstrip("Z")
        # `until` carries its date when it falls on another day than `from`: this test runs at the
        # real time, and a window recorded after 23:00 UTC ends the next day (the gate, 23:23 UTC,
        # 2026-10-19; `test_a_window_past_midnight_names_its_until_date` pins that case).
        until = (w2["until"][11:19] if w2["until"][:10] == w2["from"][:10]
                 else w2["until"].replace("T", " ").rstrip("Z"))
        assert row["operands"]["window"].startswith(f"from {start} until {until} UTC"), row
        assert f"recorded {w2['recorded_at'].replace('T', ' ').rstrip('Z')} UTC" in \
            row["operands"]["window"]
        assert wid not in row["operands"]["window"] and wid not in row["cause"]
        # The page a person reads: the id is the row's key and event (attributes), never text.
        html = net["client"].get("/v2/attention").get_data(as_text=True)
        assert f"from {start} until {until} UTC" in html
        text = re.sub(r"<[^>]*>", " ", html)
        assert "1 new host key accepted" in text and wid not in text


def test_a_window_past_midnight_names_its_until_date():
    """A window's `until` on another day than its `from` is drawn with its date, never a bare
    time that reads as the same day (fixed times, so it does not depend on the clock)."""
    same = HK.window_words({"from": "2026-10-19T19:25:29Z", "until": "2026-10-19T20:25:29Z",
                            "recorded_at": "2026-10-19T19:25:29Z"})
    assert same == ("from 2026-10-19 19:25:29 until 20:25:29 UTC, "
                    "recorded 2026-10-19 19:25:29 UTC")
    late = HK.window_words({"from": "2026-10-19T23:23:30Z", "until": "2026-10-20T00:23:30Z",
                            "recorded_at": "2026-10-19T23:23:30Z"})
    assert late.startswith("from 2026-10-19 23:23:30 until 2026-10-20 00:23:30 UTC"), late


def _old_crediting(monkeypatch, w1, hosts, keys):
    """The host's record: each key met while BOTH windows covered its device, credited to W1
    by the code before C1389 (the first covering window in the record). Made through the real
    `check`, with the planned record read as the old code chose from it (W1 first)."""
    real = restarts.planned_rows
    w1_only = [p for p in real() if HK.window_id(p) == HK.window_id(w1)]
    monkeypatch.setattr(restarts, "planned_rows", lambda: w1_only)
    for h in hosts:
        assert HK.check(ADDR[h], keys[h][1], owner="test:redeploy")["state"] == "window"
    monkeypatch.setattr(restarts, "planned_rows", real)


class TestTheCorrection:
    def _host(self, net, keys, monkeypatch):
        """W1's summary written with d1's and d2's keys, W2's with d3's, as on the host."""
        _first_contact(keys, ("d1", "d2", "d3"))
        now = time.time()
        w1, w2 = _overlapping(now)
        _old_crediting(monkeypatch, w1, ("d1", "d2"), keys)
        HK.check(ADDR["d3"], keys["d3"][1], owner="test:redeploy")
        assert {h: HK.held(ADDR[h])["window"]["id"] for h in ("d1", "d2", "d3")} == {
            "d1": HK.window_id(w1), "d2": HK.window_id(w1), "d3": HK.window_id(w2)}
        HK.close_windows(now=now + 3000 + restarts.PLANNED_SLACK_SECONDS + 5,
                         planned=[w1])
        HK.close_windows(now=now + 3540 + restarts.PLANNED_SLACK_SECONDS + 5,
                         planned=[w2])
        return w1, w2

    def test_it_moves_the_keys_and_keeps_the_old_crediting(self, net, keys, monkeypatch):
        w1, w2 = self._host(net, keys, monkeypatch)
        before = {s["what"] for s in _window_rows()}
        assert before == {f"2 new host keys accepted during '{WHY1}'",
                          f"1 new host key accepted during '{WHY2}'"}, before
        old_events = {r["id"]: r["event"] for r in _window_rows()}

        plans = dict(HK.recredit_planned())
        assert {ip: p["state"] for ip, p in plans.items()} == {
            ADDR["d1"]: "move", ADDR["d2"]: "move", ADDR["d3"]: "same"}, plans
        out = HK.recredit([ADDR["d1"], ADDR["d2"]], by=BY)
        assert out["ok"], out
        for h in ("d1", "d2"):
            rec = HK.held(ADDR[h])
            assert rec["window"]["id"] == HK.window_id(w2) and rec["window"]["device"] == h
            assert rec["fingerprint"] == _fp(keys[h][1]), "the key itself is unchanged"
            old = rec["recredited"]
            assert len(old) == 1 and old[0]["window"]["id"] == HK.window_id(w1)
            assert old[0]["by"] == BY and old[0]["why"] == HK.RECREDIT_WHY
            assert old[0]["finding"] == HK.RECREDIT_FINDING and old[0]["at"]

        # The summaries: W1's corrected to none, W2's to three; the earlier lines stay.
        lines = _summary_lines(net)
        assert [(s["window"] == HK.window_id(w1), s["count"], bool(s.get("corrected")))
                for s in lines] == [(True, 2, False), (False, 1, False), (True, 0, True),
                                    (False, 3, True)], lines
        rows = _window_rows()
        assert [r["what"] for r in rows] == [f"3 new host keys accepted during '{WHY2}'"]
        assert "Corrected" in rows[0]["cause"] and "it said 1" in rows[0]["cause"]
        # A new event: acknowledging what was said before never covers the correction.
        assert rows[0]["event"] != old_events[rows[0]["id"]]

        # History: the correction of each key, when it was made, naming both windows.
        fixed = [e for e in _timeline() if e["what"] == "SSH host key's window corrected"]
        assert sorted(e["devices"][0] for e in fixed) == ["d1", "d2"], fixed
        for e in fixed:
            assert WHY1 in e["detail"] and WHY2 in e["detail"] and HK.RECREDIT_FINDING in \
                e["detail"] and e["who"] == BY and "corrected" in e["marks"]
        assert any(e["what"] == f"3 new host keys accepted during '{WHY2}' (corrected)"
                   for e in _timeline())

    def test_it_refuses_when_the_rule_gives_the_same_window(self, net, keys, monkeypatch):
        w1, w2 = self._host(net, keys, monkeypatch)
        path = HK.path()
        with open(path, encoding="utf-8") as fh:
            stored = fh.read()
        got = HK.recredit([ADDR["d3"]], by=BY)
        assert not got["ok"] and got["state"] == "same", got
        assert WHY2 in got["error"] and HK.window_words(HK.held(ADDR["d3"])["window"]) in \
            got["error"]
        # One refused, all refused: nothing written for d1 either.
        got = HK.recredit([ADDR["d1"], ADDR["d3"]], by=BY)
        assert not got["ok"] and "nothing was corrected" in got["error"]
        with open(path, encoding="utf-8") as fh:
            assert fh.read() == stored
        # Once moved, the rule gives the window it names: a second run is refused.
        assert HK.recredit([ADDR["d1"]], by=BY)["ok"]
        again = HK.recredit([ADDR["d1"]], by=BY)
        assert not again["ok"] and again["state"] == "same"

    def test_it_refuses_an_unreadable_record(self, net, keys, monkeypatch):
        self._host(net, keys, monkeypatch)
        path = HK.path()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        got = HK.recredit([ADDR["d1"]], by=BY)
        assert not got["ok"] and got["state"] == "unreadable", got
        with open(path, encoding="utf-8") as fh:
            assert fh.read() == "{not json"

    def test_the_host_command_plans_then_applies(self, net, keys, monkeypatch, capsys):
        from importlib.machinery import SourceFileLoader
        w1, w2 = self._host(net, keys, monkeypatch)
        script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts",
                              "nmas-host-key-recredit")
        main = SourceFileLoader("nmas_host_key_recredit", script).load_module().main
        assert main([]) == 0
        out = capsys.readouterr().out
        assert "2 of 3 key(s) would be re-credited" in out
        assert HK.held(ADDR["d1"])["window"]["id"] == HK.window_id(w1), "the plan writes nothing"
        assert main(["--apply", "--every", "--by", BY]) == 0
        out = capsys.readouterr().out
        assert out.count("re-credited:") == 2 and "summary corrected" in out
        assert HK.held(ADDR["d2"])["window"]["id"] == HK.window_id(w2)
        assert main(["--apply", "--every", "--by", BY]) == 1
        assert main(["--apply", ADDR["d3"], "--by", BY]) == 1


class TestAnAbandonedAttemptEndsItsWindow:
    def test_the_api_ends_it_and_it_takes_no_later_key(self, net, keys):
        _first_contact(keys, ("d1", "d2"))
        now = time.time()
        w1 = _declare(("d1", "d2"), now - 600, now + 3000, now - 600, WHY1)
        r = net["client"].post("/restarts/planned", json={
            "list": "Lab", "end": w1["recorded_at"], "why": "the attempt failed at r5"})
        assert r.status_code == 200, r.get_data(as_text=True)
        p = restarts.planned_rows()[0]
        assert p["ended_at"] and p["ended_why"] == "the attempt failed at r5"
        # No later key (IPv4 and IPv6 alike), and no later restart beyond the slack.
        for h in ("d1", "d2"):
            with pytest.raises(HK.HostKeyRefused):
                HK.check(ADDR[h], keys[h][1], owner="test:after-the-end")
        ended = restarts._epoch(p["ended_at"])
        assert not restarts._window_covers(p, "d1", ended + restarts.PLANNED_SLACK_SECONDS + 60,
                                           "Lab")
        assert restarts._window_covers(p, "d1", ended - 30, "Lab")
        # Its summary is written at once, not at its declared end plus the slack.
        got = _reader(now + 5)
        assert [w["count"] for w in got["written"]] == [0], got
        # Ending it again is refused, naming its end and the one asked for.
        again = net["client"].post("/restarts/planned", json={
            "list": "Lab", "end": w1["recorded_at"], "why": "the attempt failed at r5"})
        assert again.status_code == 409 and p["ended_at"] in again.get_json()["error"]
        # So is a window that is not there, and a past end without a correction.
        none = net["client"].post("/restarts/planned", json={
            "list": "Lab", "end": "2026-01-01T00:00:00Z", "why": "x"})
        assert none.status_code == 409 and "no planned window" in none.get_json()["error"]

    def test_a_past_end_needs_a_correction(self, net):
        now = time.time()
        w = _declare(("d1",), now - 3000, now + 600, now - 3000, WHY1)
        at = _iso(now - 1800)
        r = net["client"].post("/restarts/planned", json={
            "list": "Lab", "end": w["recorded_at"], "why": "abandoned", "at": at})
        assert r.status_code == 409 and "correction" in r.get_json()["error"]
        r = net["client"].post("/restarts/planned", json={
            "list": "Lab", "end": w["recorded_at"], "why": "abandoned", "at": at,
            "correction": "the attempt was abandoned then and its window was not ended"})
        assert r.status_code == 200, r.get_data(as_text=True)
        p = restarts.planned_rows()[0]
        assert p["ended_at"] == at and p["ended_correction"].startswith("the attempt")

    def test_the_host_command_ends_it(self, net, capsys):
        from importlib.machinery import SourceFileLoader
        now = time.time()
        w = _declare(("d2",), now - 60, now + 3540, now - 60, WHY2)
        script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts",
                              "nmas-planned-restart")
        main = SourceFileLoader("nmas_planned_restart", script).load_module().main
        assert main(["Lab", "--end", w["recorded_at"], "--why", "abandoned", "--by", BY]) == 0
        assert "ended:" in capsys.readouterr().out
        p = restarts.planned_rows()[0]
        assert p["ended_by"] == BY and p["ended_via"] == "nmas-planned-restart"
        assert main(["Lab", "--end", w["recorded_at"], "--why", "again", "--by", BY]) == 1


class TestAWindowEndsOnceEveryDeviceIsMet:
    def test_the_summary_appears_at_the_last_key(self, net, keys):
        _first_contact(keys, ("d1", "d2"))
        now = time.time()
        w = _declare(("d1", "d2"), now - 60, now + 3540, now - 60, WHY2)
        HK.check(ADDR["d1"], keys["d1"][1], owner="test:redeploy")
        # One of two met: the window stays open.
        assert _reader(now + 30)["written"] == []
        assert "ended_at" not in restarts.planned_rows()[0]
        HK.check(ADDR["d2"], keys["d2"][1], owner="test:redeploy")
        last = HK.held(ADDR["d2"])["kept_at"]
        got = _reader(now + 60)
        assert [(x["count"], x["why"]) for x in got["written"]] == [(2, WHY2)], got
        p = restarts.planned_rows()[0]
        assert p["ended_at"] == last and p["ended_by"] == HK.COMPLETED_BY
        assert [r["what"] for r in _window_rows()] == [
            f"2 new host keys accepted during '{WHY2}'"]
        # It covers nothing more: no restart beyond the slack after its end, though its
        # declared end is most of an hour away.
        ended = restarts._epoch(last)
        assert restarts._epoch(w["until"]) > ended + 3000
        assert not restarts._window_covers(p, "d1", ended + restarts.PLANNED_SLACK_SECONDS + 60,
                                           "Lab")

    def test_a_window_taken_over_by_a_later_one_ends_when_the_later_one_opens(self, net,
                                                                              keys):
        _first_contact(keys, ("d1", "d2", "d3"))
        now = time.time()
        w1, w2 = _overlapping(now)
        for h in ("d1", "d2", "d3"):
            HK.check(ADDR[h], keys[h][1], owner="test:redeploy")
        _reader(now + 60)
        ends = {HK.window_id(p): p.get("ended_at") for p in restarts.planned_rows()}
        assert ends[HK.window_id(w1)] == w2["recorded_at"], ends
        assert ends[HK.window_id(w2)] == max(HK.held(ADDR[h])["kept_at"]
                                             for h in ("d1", "d2", "d3"))
