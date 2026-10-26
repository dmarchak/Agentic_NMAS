"""An out-of-band change, then a Capture, never reads as clean (C1819, the operator's Walk 3,
2026-10-26).

The walk: a `description drift walk` typed at s1's console, then Capture. The capture made it the
golden, the drift check (device against golden) found nothing changed, and the device page's
Checks drew "Drift: clean at the last run" directly above "Intent: departs (+1 -1)". The
operator's rule: an out-of-band change must never read as clean; the golden history marks a
capture that departs from intent, with how the device's own log says it was changed.

What was chosen, and why: the drift check's row is named for what it measures, **Since last
capture** (the device against its golden, the record of its last capture), and a last capture
that took in a change made outside Mercury that departs from intent is said on it, the row a
warning, never a pass. Making the row compare against intent would have made it a second copy
of the Intent row and dropped the measurement the drift queue's Capture item rests on.

On `test_profile_apply`'s lab: r2's REAL configuration as its golden with its committed intent
(at intent). r2's running configuration is then that one with one interface description changed
by hand (the walk's own edit). The capture is the REAL preview and apply (`capture_core`, the
cores v2's Capture card runs), the device read faked at `_read_running`. The device's log is
s3's REAL `%SYS-5-CONFIG_I` line (`tests/fixtures/loki/lines_s3.json`) as r2's, received after
the previous golden, through `test_drift_overview`'s fake Loki, which applies the query's own
line filters. The drift run's record is written as the run writes it, finding r2 at its golden.
"""

import json
import os
import re
import time

import pytest

from tests.test_drift_overview import S3_LINES, loki  # noqa: F401  (the fixture)
from tests.test_profile_apply import lab  # noqa: F401  (the fixture)

DESCRIPTION = " description P2P to s2 Gi0/2 - RIPng\n"
BY_HAND = " description drift walk\n"


def _ref():
    from modules.nsot import listref
    return listref.resolve("Lab")


def _dev():
    return {"hostname": "r2", "ip": "203.0.113.12", "platform": "cisco_iosxe",
            "device_type": "cisco_xe"}


def _config_i_line_as_r2():
    """s3's real console configuration line, its device name edited to r2."""
    cap = json.load(open(S3_LINES, encoding="utf-8"))
    line = next(l for s in cap["answer"]["data"]["result"] for _ns, l in s["values"]
                if "%SYS-5-CONFIG_I:" in l)
    return line.replace(" s3 ", " r2 ").replace(" s3: ", " r2: ")


def _capture(lab, monkeypatch):  # noqa: F811
    """The device changed by hand, then the real Capture preview and confirm."""
    import routes.golden as golden
    from tests import capture_core

    running = lab["captured"].replace(DESCRIPTION, BY_HAND, 1)
    assert running != lab["captured"], "r2's capture moved: re-take the edit"
    monkeypatch.setattr(golden, "_read_running", lambda d, phases=None: (running, ""))
    d = capture_core.preview({"devices": ["r2"]})
    target = next(t for t in d["preview"]["what"]["targets"] if t["name"] == "r2")
    got = capture_core.apply({"confirmations": {"r2": target["select_data"]["hash"]}})
    assert got["ok"], got
    return running


def _drift_clean():
    """The drift run's record as the run writes it: r2 read and found at its golden."""
    from modules import drift_check
    drift_check._save_state({"last_check_ts": time.time(), "last_result": {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "clean": 1,
        "drifted_devices": [], "skipped": [], "unreachable": []}}, "Lab")


def _checks():
    from modules import device_page
    return {c["name"]: c for c in device_page.checks(_ref(), _dev())}


def _last_message(repo):
    from modules.nsot import repo as R
    return R.git(repo, "log", "-1", "--format=%B", "--", "golden/r2.cfg")[1]


@pytest.fixture
def walked(lab, loki, monkeypatch):  # noqa: F811
    """The walk: r2 at intent, its log holding the console line, changed by hand, captured."""
    loki["corpus"] = [(int(time.time() * 1e9), _config_i_line_as_r2())]
    _capture(lab, monkeypatch)
    _drift_clean()
    return lab


class TestTheCaptureKeepsHowItChanged:
    def test_the_commit_says_it_departs_and_how_the_device_was_changed(self, walked):
        msg = _last_message(walked["repo"])
        assert "Source: capture" in msg
        assert re.search(r"^Intent-Match: no: r2 \(\+1 -1\)$", msg, re.M), msg
        oob = re.search(r"^Out-Of-Band: r2: (.+)$", msg, re.M)
        assert oob, msg
        assert oob.group(1).startswith("by console per SYS-5-CONFIG_I, received "), oob.group(1)
        assert "Configured from console by <user> on vty0" in oob.group(1)

    def test_a_capture_at_intent_keeps_no_out_of_band_line(self, lab, loki, monkeypatch):  # noqa: F811
        """The control: the same capture with the device at its intent (a capture that changes
        its golden by a line intent has too) carries no `Out-Of-Band:` and asks Loki nothing."""
        import routes.golden as golden
        from tests import capture_core
        from modules.nsot import out_of_band

        assert not out_of_band.trailers(lab["repo"], [])
        monkeypatch.setattr(golden, "_read_running",
                            lambda d, phases=None: (lab["captured"] + "!\n", ""))
        d = capture_core.preview({"devices": ["r2"]})
        target = next(t for t in d["preview"]["what"]["targets"] if t["name"] == "r2")
        capture_core.apply({"confirmations": {"r2": target["select_data"]["hash"]}})
        assert "Out-Of-Band:" not in _last_message(lab["repo"])
        assert not [a for a in loki["asked"] if "CONFIG_I" in a[1].get("query", "")]

    def test_a_log_that_cannot_be_read_says_so_never_no_change(self, lab, loki, monkeypatch):  # noqa: F811
        loki["fail"] = "connection refused"
        _capture(lab, monkeypatch)
        msg = _last_message(lab["repo"])
        assert re.search(r"^Out-Of-Band: r2: its log could not be read: Loki could not be asked: "
                         r"connection refused$", msg, re.M), msg


class TestNoCheckReadsClean:
    def test_the_since_last_capture_row_flags_the_change_it_took_in(self, walked):
        checks = _checks()
        assert "Drift" not in checks, "the row is named for what it measures (C1819)"
        row, intent = checks["Since last capture"], checks["Intent"]
        assert intent["state"] == "warn" and intent["in_intent"] and intent["on_device"]
        assert row["state"] == "warn", row
        assert row["text"].startswith("unchanged at the last run, but its last capture ("), row
        assert ("took in a change made outside Mercury that departs from intent (+1 -1): "
                "changed out-of-band, by console per SYS-5-CONFIG_I; it is not at its intent "
                "(see Intent)") in row["text"], row["text"]

    def test_no_check_on_the_page_reads_clean(self, walked, monkeypatch):
        from modules import device_page
        monkeypatch.setattr(device_page, "find_device", lambda name, ref=None: (_ref(), _dev()))
        html = walked["client"].get("/v2/device/r2/overview").get_data(as_text=True)
        rows = re.findall(r'<li class="check (check-\w+)[^"]*">.*?<strong>([^<]+)</strong>', html,
                          re.S)
        states = dict((name, kind) for kind, name in rows)
        assert states["Since last capture"] == "check-warn", states
        assert states["Intent"] == "check-warn", states
        assert "clean" not in re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).lower()

    def test_the_control_at_intent_the_row_is_a_pass(self, lab):  # noqa: F811
        """The same record, r2 never changed: unchanged, a pass, nothing taken in."""
        _drift_clean()
        row = _checks()["Since last capture"]
        assert row["state"] == "ok" and row["text"] == "unchanged at the last run", row

    def test_intent_adopting_the_change_clears_the_flag(self, walked):
        """The flag judges the departure NOW: once intent carries the hand-made line, the
        capture took in nothing intent lacks, and the row is a pass again."""
        from modules.nsot import hostvars
        from modules.nsot.parsers import get_parser
        from modules.nsot.repo import save_host_vars

        running = walked["captured"].replace(DESCRIPTION, BY_HAND, 1)
        hostvars.write_committed(walked["repo"], get_parser("cisco_iosxe").parse(running))
        assert save_host_vars("Lab", ["r2"], actor="t", source="edit")["ok"]
        checks = _checks()
        assert checks["Intent"]["state"] == "ok", checks["Intent"]
        assert checks["Since last capture"]["state"] == "ok", checks["Since last capture"]


class TestTheGoldensHistoryMarksIt:
    def test_the_device_history_marks_the_capture(self, walked):
        from modules import history_sources as H
        got = H.timeline(_ref(), device="r2", kinds=["golden"])
        newest = next(e for e in got["events"] if e["kind"] == "golden")
        assert ("captured, departs from intent (+1 -1); changed out-of-band, by console per "
                "SYS-5-CONFIG_I") in newest["marks"], newest
        rec = dict(newest["record"])
        assert rec["Intent-Match"] == "no: r2 (+1 -1)"
        assert rec["Out-of-band"].startswith("r2: by console per SYS-5-CONFIG_I, received ")
        # The control: the onboarding golden before it, at intent, carries no mark.
        older = [e for e in got["events"] if e["kind"] == "golden" and e is not newest]
        assert older and all(not e["marks"] for e in older), older

    def test_the_fleet_history_names_the_device(self, walked):
        from modules import history_sources as H
        got = H.timeline(_ref(), kinds=["golden"])
        newest = next(e for e in got["events"] if e["kind"] == "golden")
        assert any(m.startswith("r2 captured, departs from intent (+1 -1); changed "
                                "out-of-band, by console per SYS-5-CONFIG_I")
                   for m in newest["marks"]), newest["marks"]

    def test_the_device_history_tab_draws_the_mark(self, walked, monkeypatch):
        from modules import device_page
        monkeypatch.setattr(device_page, "find_device", lambda name, ref=None: (_ref(), _dev()))
        html = walked["client"].get("/v2/device/r2/history").get_data(as_text=True)
        assert "captured, departs from intent (+1 -1); changed out-of-band, by console per " \
               "SYS-5-CONFIG_I" in html, html[:400]


class TestTheTrailerReads:
    @pytest.mark.parametrize("value, want", [
        ("yes (9 of 9)", {}),
        ("no: edge1 (+1 -1)", {"edge1": "+1 -1"}),
        ("no: edge1 (+1 -1); edge2 (unknown (no committed intent: nothing says (x)))",
         {"edge1": "+1 -1"}),
        ("no: edge2 (2 reordered); edge3 (-4)", {"edge2": "2 reordered", "edge3": "-4"}),
        ("", {}),
    ])
    def test_departures(self, value, want):
        from modules.nsot import out_of_band
        assert out_of_band.departures(value) == want
