"""A check that could not read a device during its boot says so (the operator,
2026-10-01: during the afternoon's redeploy drift's and the startup check's
rows read "could not be checked" while the reachability reader KNEW the device
was not answering).

The reachability reader keeps the last outage it WATCHED (`down_from`,
`back_at`), never one inferred from a first probe; `outage_words()` turns it
into the sentence both rows lead with. The times follow the redeploy's real
shape (the routers' telemetry gap ran 16:48 to 17:12 UTC, read from
Prometheus).
"""

import calendar
import time

import pytest

from modules import attention as A
from modules import config
from modules import job_health as J
from modules.readers import reachability as RE

T0 = float(calendar.timegm((2026, 10, 1, 16, 40, 0, 0, 0, 0)))
TARGETS = [("192.0.2.13", "r3", "Lab"), ("192.0.2.23", "s3", "Lab")]


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    saved = dict(RE.STATUS)
    yield
    RE.STATUS.clear()
    RE.STATUS.update(saved)


def cycle(answers, previous, t):
    fn = lambda ip: (answers[ip], RE.CLAIM_TCP if answers[ip] else RE.CLAIM_NONE)  # noqa: E731
    return RE.read(probe_fn=fn, targets=TARGETS, previous=previous, clock=lambda: t)


def _boot(down_at, up_at):
    """s3 answering, then silent for its boot, then answering again."""
    v = cycle({"192.0.2.13": True, "192.0.2.23": True}, {}, T0)
    t = down_at
    for _ in range(RE.miss_threshold("Lab", "s3")):
        v = cycle({"192.0.2.13": True, "192.0.2.23": False}, v["devices"], t)
        t += 5
    return cycle({"192.0.2.13": True, "192.0.2.23": True}, v["devices"], up_at)


class TestTheReaderKeepsTheOutageItSaw:
    def test_a_device_that_came_back_carries_its_outage(self):
        v = _boot(T0 + 480, T0 + 1920)
        s3 = v["devices"]["192.0.2.23"]
        assert s3["answering"] and s3["back_at"] == RE._iso(T0 + 1920)
        assert s3["down_from"] == RE._iso(T0 + 480 + 5 * (RE.miss_threshold("Lab", "s3") - 1))

    def test_it_is_held_while_the_device_keeps_answering(self):
        v = _boot(T0 + 480, T0 + 1920)
        v = cycle({"192.0.2.13": True, "192.0.2.23": True}, v["devices"], T0 + 1980)
        assert v["devices"]["192.0.2.23"]["back_at"] == RE._iso(T0 + 1920)

    def test_a_first_probe_is_never_a_device_coming_back(self):
        v = cycle({"192.0.2.13": True, "192.0.2.23": True}, {}, T0)
        assert v["devices"]["192.0.2.23"]["back_at"] is None
        assert v["devices"]["192.0.2.13"]["down_from"] is None


class TestTheWords:
    def test_not_answering_now_is_said_with_since(self):
        v = cycle({"192.0.2.13": True, "192.0.2.23": True}, {}, T0)
        for k in range(RE.miss_threshold("Lab", "s3")):
            v = cycle({"192.0.2.13": True, "192.0.2.23": False}, v["devices"], T0 + 480 + 5 * k)
        w = RE.outage_words("s3", T0 + 600, value=v, now=T0 + 900)
        assert w.startswith("not answering SSH yet: s3 has not answered Mercury since 16:48 UTC")

    def test_a_check_that_ran_during_the_boot_is_said(self):
        v = _boot(T0 + 480, T0 + 1920)
        w = RE.outage_words("s3", T0 + 2100, value=v, now=T0 + 2400)
        assert w == ("not answering SSH yet: s3 did not answer Mercury from 16:48 to 17:12 UTC "
                     "and this ran at 17:15, while it was still coming up (SSH answers last in "
                     "a boot)")

    def test_a_failure_long_after_the_boot_is_not_explained_by_it(self):
        v = _boot(T0 + 480, T0 + 1920)
        assert RE.outage_words("s3", T0 + 1920 + RE.BOOT_TAIL_SECONDS + 60, value=v) == ""

    def test_a_device_that_never_went_silent_says_nothing(self):
        v = _boot(T0 + 480, T0 + 1920)
        assert RE.outage_words("r3", T0 + 2100, value=v) == ""
        assert RE.outage_words("nope", T0 + 2100, value=v) == ""


def _plant(monkeypatch, value):
    real = __import__("modules.reader_job", fromlist=["read_cached"]).read_cached
    monkeypatch.setattr("modules.reader_job.read_cached",
                        lambda name: ({"state": "ok", "doc": {"last_good": {"value": value}}}
                                      if name == "reachability" else real(name)))


class TestTheRowsSayIt:
    def _drift(self, at):
        return lambda: {"list": "Lab", "last_ts": at, "last_run": {
            "inventory": 2, "checked": 1, "errors": [
                {"hostname": "s3", "reason": "SSH error: TCP connection to device failed"}]}}

    def test_drift_s_row_leads_with_the_boot(self, monkeypatch):
        _plant(monkeypatch, _boot(T0 + 480, T0 + 1920))
        res = A.drift_source(status=self._drift(T0 + 2100), now=T0 + 2400)
        r = next(r for r in res["rows"] if r["what"] == "s3 could not be checked for drift")
        assert r["cause"].startswith("Not answering SSH yet: s3 did not answer Mercury from "
                                     "16:48 to 17:12 UTC")
        assert r["cause"].endswith("The check said: SSH error: TCP connection to device failed")

    def test_without_an_outage_the_row_is_the_reason_alone(self, monkeypatch):
        _plant(monkeypatch, cycle({"192.0.2.13": True, "192.0.2.23": True}, {}, T0))
        res = A.drift_source(status=self._drift(T0 + 2100), now=T0 + 2400)
        r = next(r for r in res["rows"] if r["what"] == "s3 could not be checked for drift")
        assert r["cause"] == "SSH error: TCP connection to device failed"

    def test_the_startup_check_s_unread_row_says_it(self, monkeypatch):
        _plant(monkeypatch, _boot(T0 + 480, T0 + 1920))
        res = {"at": T0 + 2100, "devices": [
            {"device": "r3", "list": "Lab", "state": "persisted"},
            {"device": "s3", "list": "Lab", "state": "unread", "since": T0 + 2100,
             "detail": "could not read the device: TCP connection to device failed"}]}
        rows = J.startup_rows(read=lambda: res, now=T0 + 2400)
        unread = next(r for r in rows if r["unit"] == "startup-check:unread")
        assert ("s3: not answering SSH yet: s3 did not answer Mercury from 16:48 to 17:12 UTC"
                in unread["detail"])
        assert "; the check said: " in unread["detail"]
