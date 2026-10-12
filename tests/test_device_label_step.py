"""C722's host step (scripts/host-steps/c722-device-label.sh): Alloy sets a `device` label from
each line, by the SAME pattern Mercury reads a line's device with (`device_logs.LOGQL_FIELDS`,
the one definition), so the label and the regex that reads lines older than the label never
disagree about which device a line is from.

Held here: the Alloy stage's syslog expression and the step's own proof query are that pattern
(parsed out of the script, never matched as a substring of prose); each finds the device in the
captured lines of tests/fixtures/loki/device_logs.json (r3's, and s3's unsynchronised clock), and
the trap expression finds it in a trap's first line as snmptrapd writes it (shape read from the
NMAS host's journal, 2026-10-12, its addresses replaced by documentation ones).
"""

import json
import os
import re
import subprocess

from modules import device_logs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "host-steps", "c722-device-label.sh")
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "loki", "device_logs.json")
TRAP = "2026-09-29 04:19:47 s4 [UDP: [192.0.2.14]:64055->[192.0.2.211]:162]:"


def _text():
    with open(SCRIPT, encoding="utf-8") as fh:
        return fh.read()


def _process_expression(name: str) -> str:
    """The `expression` of the `loki.process "<name>"` block, as the heredoc writes it (an
    escaped backtick is a backtick in the file Alloy reads)."""
    block = re.search(r'^loki\.process "%s" \{\n(.*?)^\}' % re.escape(name), _text(),
                      re.M | re.S)
    assert block, f"no loki.process {name!r} block"
    expr = re.search(r"^\s+expression = \\`(.*)\\`$", block.group(1), re.M)
    assert expr, f"loki.process {name!r} has no backtick expression"
    return expr.group(1)


def _named_in_the_proof() -> str:
    m = re.search(r'^NAMED = \(r"(.*)"\n\s+r"(.*)"\)$', _text(), re.M)
    assert m, "the proof's NAMED pattern"
    return m.group(1) + m.group(2)


#: Mercury's pattern up to the mnemonic: the device's own name before its timestamp.
MERCURY = device_logs.LOGQL_FIELDS.split("(?P<mn>")[0]


def test_the_alloy_stage_and_the_proof_use_mercury_s_one_pattern():
    assert MERCURY.startswith(r"\s(?P<dev>") and MERCURY.endswith(r":\s+")
    assert _process_expression("syslog_device") == MERCURY.replace("(?P<dev>", "(?P<device>")
    assert _named_in_the_proof() == MERCURY


def test_the_stage_finds_the_device_in_captured_lines():
    with open(FIXTURE, encoding="utf-8") as fh:
        captured = json.load(fh)
    pattern = re.compile(_process_expression("syslog_device"))
    seen = 0
    for device in ("r3", "s3"):
        for stream in captured[device]["body"]["data"]["result"]:
            for _ts, line in stream["values"]:
                m = pattern.search(line)
                assert m and m.group("device") == device, ("a line the label misses", line)
                seen += 1
    assert seen >= 80, seen                          # the floor: 40 captured lines each


def test_a_trap_s_first_line_names_its_device():
    m = re.search(_process_expression("trap_device"), TRAP)
    assert m and m.group("device") == "s4"
    assert not re.search(_process_expression("trap_device"),
                         TRAP.replace(" s4 ", " 192.0.2.14 ")), "an address is no device's name"


class _Answer:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def _loki(stamps_ns, seen):
    def ask(query, start, end):
        seen.append(query)
        return {"ok": True, "response": _Answer({"data": {"result": (
            [{"stream": {"device": "r3"}, "values": [[str(ns), "x"] for ns in stamps_ns]}]
            if stamps_ns else [])}})}
    return ask


class TestTheSelectorFollowsTheLabel:
    """Mercury selects a device's lines by the label from when Loki's first labelled line
    arrived (measured), and by the line regex for any window reaching earlier."""

    def test_a_window_after_the_label_began_selects_by_it_and_earlier_by_the_line(
            self, monkeypatch):
        monkeypatch.setattr(device_logs, "_LABEL", {"since": None, "asked": None})
        seen, now = [], 2_000_000_000.0
        since = device_logs.label_since(now=now, ask=_loki([int((now - 3600) * 1e9)], seen))
        assert since == now - 3600 and seen == ['{job="network_syslog", device=~".+"}']
        monkeypatch.setattr(device_logs.time, "time", lambda: now)
        assert device_logs.selector("r3", start=now - 600) == \
            '{job="network_syslog", device="r3"}'
        assert device_logs.selector("r3", start=now - 7200) == \
            '{job="network_syslog"} |= "r3:" |~ `\\sr3:\\s`'
        assert device_logs.selector("r3") == device_logs.selector("r3", start=now - 7200)
        assert len(seen) == 1, "asked once an hour, not per selector"

    def test_none_labelled_or_loki_unanswering_reads_by_the_line(self, monkeypatch):
        monkeypatch.setattr(device_logs, "_LABEL", {"since": None, "asked": None})
        seen, now = [], 2_000_000_000.0
        assert device_logs.label_since(now=now, ask=_loki([], seen)) is None
        monkeypatch.setattr(device_logs, "_LABEL", {"since": None, "asked": None})
        assert device_logs.label_since(now=now, ask=lambda q, s, e: {
            "ok": False, "error": "refused"}) is None
        assert device_logs._LABEL["asked"] is None, "a failed ask is asked again next time"


def test_the_host_step_s_check_reads_the_measurement():
    """Update's after-step row for C722 is checked by the tool (`device-label`): done once Loki
    holds a labelled line, not done until then."""
    from modules import host_steps

    assert "device-label" in host_steps.CHECKS
    done = host_steps.check_device_label(since=2_000_000_000.0)
    assert done["state"] == "done" and "2033-05-18 03:33 UTC" in done["detail"]
    assert host_steps.check({"check": "device-label"})["state"] in ("unknown", "not_done")


def test_the_script_parses_and_puts_the_config_back_on_failure():
    assert subprocess.run(["bash", "-n", SCRIPT], capture_output=True).returncode == 0
    text = _text()
    assert re.search(r"^ON_FAIL=.*sudo install .*'\$BEFORE' '\$CONFIG'.*restart alloy", text, re.M)
    assert re.search(r"^check \"the new config is valid Alloy\" rc0 \"\" \"alloy fmt ", text, re.M)
