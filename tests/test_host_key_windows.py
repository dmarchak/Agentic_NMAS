"""C906's follow-up (the operator, 2026-10-16): every SSH host key a planned window accepts
is recorded, and once the window has closed ONE summary stays on Needs attention until a
person acknowledges it.

On test_persist_screen's lab (r2 at 192.0.2.12 and s9 at 192.0.2.99, network Lab), through
the real host-key record (`host_keys.check`, given real RSA keys generated for the run: the
comparison of a key a real server presents is tests/test_host_keys.py's), the real planned
window writer, the real reader (`modules/readers/host_key_windows.py`), History's real
timeline, Needs attention's real page and the real acknowledge route.

- a window that expects new keys takes two: two History rows, each naming the device, the
  new key, the key it replaced and the window's reason; nothing on Needs attention while the
  window is open; once it has closed (its end plus the slack, or, C1389, once every device it
  covers has answered with its new key) ONE row, "2 new host keys
  accepted during 'lab redeploy'", until a person acknowledges it, then gone;
- a new key outside any declared window (one closed, one not yet open) is refused, and the
  key held stays;
- the summary is written once, however often the reader runs, and by two runs at once;
- a window that kept no key is summed up in History and raises no row; a summaries file that
  cannot be read is the source's own row.
"""

import os
import stat
import threading
import time

import paramiko
import pytest

from modules import host_keys as HK
from modules import restarts
from tests.test_persist_screen import lab  # noqa: F401 (the fixture)

R2, S9 = "192.0.2.12", "192.0.2.99"
WHY = "lab redeploy"
#: When a window declared `_window(now)` can take no more keys: its end plus the slack.
CLOSES = 600 + restarts.PLANNED_SLACK_SECONDS


@pytest.fixture(scope="module")
def keys():
    """Four RSA keys: r2's and s9's before the redeploy, and after."""
    return [paramiko.RSAKey.generate(1024) for _ in range(4)]


def _fp(key) -> str:
    return HK.offered(key)["fingerprint"]


def _window(now, devices=("r2", "s9"), start=-60, end=600, why=WHY):
    out = restarts.record_planned(list(devices), now + start, now + end, "op@example.invalid",
                                  why, "test", list_name="Lab", new_host_keys=True)
    assert out["ok"], out
    return out["record"]


def _reader(now):
    from modules.readers import host_key_windows as W
    return W.read(clock=lambda: now)


def _only_windows(monkeypatch):
    """Needs attention with only this source, so the test reads its own rows."""
    from modules import attention
    monkeypatch.setattr(attention, "SOURCES", [attention.host_key_window_source])


def _page():
    from modules import attention
    return attention.needs_attention()


def _ack(client, row, why):
    return client.post("/attention/acknowledge",
                       json={"row": row["id"], "event": row["event"], "why": why})


def _summaries(lab):  # noqa: F811
    path = os.path.join(lab["data"], HK.SUMMARIES)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [line for line in fh if line.strip()]


class TestAWindowThatTakesTwoKeys:
    def test_two_rows_then_one_summary_until_acknowledged(self, lab, keys,  # noqa: F811
                                                          monkeypatch):
        from modules import history_sources
        from modules.nsot.listref import resolve

        _only_windows(monkeypatch)
        HK.check(R2, keys[0], owner="test:first-contact")
        HK.check(S9, keys[1], owner="test:first-contact")
        now = time.time()
        _window(now)
        assert HK.check(R2, keys[2], owner="test:redeploy")["state"] == "window"

        # Open (inside the slack, s9 not yet met): nothing summed up, nothing on Needs
        # attention. (C1389: once every device it covers has answered with its new key, the
        # window ends then, so this is read before s9's key.)
        assert _reader(now + CLOSES - 5)["written"] == []
        assert _summaries(lab) == [] and _page()["rows"] == []

        assert HK.check(S9, keys[3], owner="test:redeploy")["state"] == "window"

        # Two History rows: the device, the new key, the key it replaced, the reason.
        tl = history_sources.timeline(resolve("Lab"), kinds=["hostkeys"])
        taken = {e["devices"][0]: e for e in tl["events"]
                 if e["what"] == "SSH host key kept under a planned window"}
        assert sorted(taken) == ["r2", "s9"], [e["what"] for e in tl["events"]]
        for host, new, old in (("r2", keys[2], keys[0]), ("s9", keys[3], keys[1])):
            e = taken[host]
            assert e["detail"] == (f"{_fp(new)} (ssh-rsa), replacing {_fp(old)}, during "
                                   f"'{WHY}'"), e["detail"]
            assert dict(e["record"])["Replaced"] == _fp(old)
            assert dict(e["record"])["Window"] == f"op@example.invalid: {WHY}"

        # Closed: ONE row naming the count and the reason, the devices and both keys each.
        got = _reader(now + CLOSES + 5)
        assert [(w["count"], w["why"]) for w in got["written"]] == [(2, WHY)]
        rows = _page()["rows"]
        assert len(rows) == 1, rows
        row = rows[0]
        assert row["what"] == f"2 new host keys accepted during '{WHY}'"
        assert row["acknowledge"] is True and row["clears"]["ways"] == ["acknowledge"]
        assert sorted(row["devices"]) == ["r2", "s9"]
        for k in keys:
            assert _fp(k) in row["cause"], "each new key and the one it replaced are named"
        # Its network's History (C493: an action that is an address keeps the row's network).
        assert row["action"]["href"] == "/v2/history?kind=hostkeys&since=30&list=Lab"

        # History draws the summary too, once.
        tl = history_sources.timeline(resolve("Lab"), kinds=["hostkeys"])
        assert [e["what"] for e in tl["events"]].count(
            f"2 new host keys accepted during '{WHY}'") == 1

        # A person acknowledges it: the row goes, and stays gone.
        r = _ack(lab["client"], row, "compared both new keys with the rebuilt devices")
        assert r.status_code == 200, r.get_data(as_text=True)
        assert _page()["rows"] == []
        _reader(now + CLOSES + 65)
        assert _page()["rows"] == []


class TestAKeyOutsideAWindowIsRefused:
    def test_a_closed_window_and_one_not_yet_open_take_nothing(self, lab, keys):  # noqa: F811
        HK.check(R2, keys[0], owner="test:first-contact")
        now = time.time()
        _window(now, devices=("r2",), start=-7200, end=-CLOSES - 60)   # closed
        _window(now, devices=("r2",), start=3600, end=7200)            # not open yet
        with pytest.raises(HK.HostKeyRefused) as got:
            HK.check(R2, keys[2], owner="test:outside")
        assert _fp(keys[0]) in str(got.value) and _fp(keys[2]) in str(got.value)
        rec = HK.held(R2)
        assert rec["fingerprint"] == _fp(keys[0]) and rec["refused"]["fingerprint"] == \
            _fp(keys[2])
        # The closed window is summed up as having taken nothing, and raises no row.
        got = _reader(now)
        assert [w["count"] for w in got["written"]] == [0]
        from modules import attention
        assert attention.host_key_window_source()["rows"] == []


class TestTheSummaryIsWrittenOnce:
    def test_two_runs_one_after_the_other_and_two_at_once(self, lab, keys):  # noqa: F811
        HK.check(R2, keys[0], owner="test:first-contact")
        now = time.time()
        _window(now, devices=("r2",))
        assert HK.check(R2, keys[2], owner="test:redeploy")["state"] == "window"
        after = now + CLOSES + 5
        assert len(_reader(after)["written"]) == 1
        assert _reader(after)["written"] == []
        errors = []

        def run():
            try:
                _reader(after + 60)
            except Exception as exc:                 # noqa: BLE001 - the test reads it
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert errors == []
        assert len(_summaries(lab)) == 1, _summaries(lab)
        from modules import attention
        rows = attention.host_key_window_source()["rows"]
        assert [r["what"] for r in rows] == [f"1 new host key accepted during '{WHY}'"]
        mode = stat.S_IMODE(os.stat(os.path.join(lab["data"], HK.SUMMARIES)).st_mode)
        assert mode == 0o600, oct(mode)


class TestTheReaderIsRegistered:
    def test_job_health_watches_it(self):
        from modules import reader_job
        assert "modules.readers.host_key_windows" in reader_job.DECLARED_MODULES
        r = next(r for r in reader_job.readers() if r.name == "host-key-windows")
        assert r.invalidates == ("host_keys",) and r.interval_seconds == 60


class TestAnUnreadableSummaryIsARow:
    def test_the_source_says_so_and_the_reader_refuses(self, lab):  # noqa: F811
        from modules import attention
        path = os.path.join(lab["data"], HK.SUMMARIES)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json\n")
        got = attention.host_key_window_source()
        assert got["state"] == "unreadable" and got["rows"][0]["kind"] == "unreadable"
        now = time.time()
        _window(now, devices=("r2",), start=-7200, end=-CLOSES - 60)
        with pytest.raises(RuntimeError, match="could not be read"):
            _reader(now)
