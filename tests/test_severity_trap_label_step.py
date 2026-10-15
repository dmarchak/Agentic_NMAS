"""IBN decision 7's host step (scripts/host-steps/ibn7-severity-trap-label.sh): Alloy sets a
`severity` label on syslog lines and a stable `job="snmptrapd"` and `trap_oid` on traps, at
ingest, with the operator's label decisions of 2026-10-14 (severity is the digit 0-7; traps carry
no severity; facility is never a label; trap_oid as snmptrapd prints it, the MIB set it prints
with checked unchanged).

Held here: the severity stage is Mercury's own pattern (`device_logs.LOGQL_FIELDS`) with the
mnemonic's digit named, and on every captured line (tests/fixtures/loki/device_logs.json) it reads
exactly `device_logs.mnemonic_severity`; the trap stages read the newest trap Loki held
(tests/fixtures/loki/trap_lines.json: read 2026-10-15 from the NMAS host, its addresses replaced
by documentation ones), whose host field is `<UNKNOWN>` (C789); the labels each block sets are
exactly the decided ones; and Update's two after-step checks read Loki's answer.
"""

import json
import os
import re
import subprocess

from modules import device_logs, host_steps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "host-steps", "ibn7-severity-trap-label.sh")
LINES = os.path.join(ROOT, "tests", "fixtures", "loki", "device_logs.json")
TRAPS = os.path.join(ROOT, "tests", "fixtures", "loki", "trap_lines.json")


def _text():
    with open(SCRIPT, encoding="utf-8") as fh:
        return fh.read()


def _block(name: str) -> str:
    m = re.search(r'^loki\.process "%s" \{\n(.*?)^\}' % re.escape(name), _text(), re.M | re.S)
    assert m, f"no loki.process {name!r} block"
    return m.group(1)


def _expressions(name: str) -> list:
    """Each `expression` of the block, as the heredoc writes it (an escaped backtick is a
    backtick in the file Alloy reads)."""
    return re.findall(r"^\s+expression = \\`(.*)\\`$", _block(name), re.M)


def _labels(name: str) -> set:
    m = re.search(r"stage\.labels \{\n\s+values = \{ (.*) \}\n", _block(name))
    assert m, f"{name} sets no labels"
    return set(re.findall(r"(\w+) = \"\"", m.group(1)))


def _traps():
    with open(TRAPS, encoding="utf-8") as fh:
        return json.load(fh)


class TestSeverity:
    def test_the_stage_is_mercurys_pattern_with_the_digit_named(self):
        _device, severity = _expressions("syslog_device")
        mercury = device_logs.LOGQL_FIELDS.replace("(?P<dev>", "").replace("(?P<mn>", "")
        mercury = mercury.replace("[A-Za-z0-9._-]*)", "[A-Za-z0-9._-]*", 1)
        assert severity == mercury[:-1].replace("-[0-7]-", "-(?P<severity>[0-7])-")

    def test_on_every_captured_line_it_reads_what_mercury_reads(self):
        with open(LINES, encoding="utf-8") as fh:
            captured = json.load(fh)
        stage = re.compile(_expressions("syslog_device")[1])
        seen = with_severity = 0
        for device in ("r3", "s3"):
            for stream in captured[device]["body"]["data"]["result"]:
                for _ts, line in stream["values"]:
                    m, mn = stage.search(line), re.search(device_logs.LOGQL_FIELDS, line)
                    want = str(device_logs.mnemonic_severity(mn.group("mn"))) if mn else None
                    assert (m.group("severity") if m else None) == want, line
                    seen, with_severity = seen + 1, with_severity + bool(m)
        assert seen >= 80 and with_severity >= 1, (seen, with_severity)

    def test_the_proof_query_reads_the_same_pattern(self):
        m = re.search(r'^MN = \(r"(.*)"\n\s+r"(.*)"\)$', _text(), re.M)
        assert m, "the proof's MN pattern"
        proof = (m.group(1) + m.group(2)).replace("(?P<dev>", "", 1).replace(
            "[A-Za-z0-9._-]*)", "[A-Za-z0-9._-]*", 1).replace("(?P<sev>", "(?P<severity>")
        assert proof == _expressions("syslog_device")[1]


class TestTraps:
    def test_the_newest_trap_gets_its_oid_and_no_device_for_unknown(self):
        trap = _traps()[1]["line"]
        device, oid = (re.compile(e) for e in _expressions("trap_device"))
        assert trap.split(" ", 3)[2] == "<UNKNOWN>", "the capture is C789's trap"
        assert not device.search(trap), "<UNKNOWN> is no device's name"
        assert oid.search(trap).group("trap_oid") == "IF-MIB::linkUp"
        named = trap.replace(" <UNKNOWN> ", " s4 ", 1)
        assert device.search(named).group("device") == "s4"

    def test_the_oid_is_taken_as_printed_in_each_form(self):
        trap = _traps()[1]["line"]
        oid = re.compile(_expressions("trap_device")[1])
        for printed in ("IF-MIB::linkDown", ".1.3.6.1.6.3.1.1.5.4",
                        "SNMPv2-SMI::enterprises.9.9.41.2.0.1"):
            assert oid.search(trap.replace("IF-MIB::linkUp", printed)).group("trap_oid") == printed

    def test_a_line_that_is_no_trap_gets_neither(self):
        start = _traps()[0]["line"]
        assert start.startswith("NET-SNMP version")
        for e in _expressions("trap_device"):
            assert not re.search(e, start)

    def test_the_job_is_set_after_the_source_and_named_snmptrapd(self):
        block = _block("trap_device")
        assert re.search(r'stage\.static_labels \{\n\s+values = \{ job = "snmptrapd" \}', block)
        assert _traps()[1]["labels"]["job"] == "loki.source.journal.snmptrapd", \
            "what Loki stored before the step (C790)"


class TestTheDecidedLabels:
    def test_each_block_sets_exactly_its_labels(self):
        assert _labels("syslog_device") == {"device", "severity"}
        assert _labels("trap_device") == {"device", "trap_oid"}

    def test_no_facility_label_and_no_severity_on_traps(self):
        alloy = re.search(r"<<ALLOY\n(.*?)\nALLOY\n", _text(), re.S).group(1)
        assert "facility" not in alloy
        assert "severity" not in _block("trap_device")

    def test_the_mib_set_is_checked_before_anything_changes(self):
        text = _text()
        assert re.search(r'^MIBSET_MEASURED="\d+ files [0-9a-f]{16}"$', text, re.M)
        check = text.index('check "the MIB set snmptrapd prints trap OIDs with is the one measured"')
        assert check < text.index('step "install the new config"')
        fn = re.search(r"^mibset\(\) \{\n(.*?)^\}", text, re.S | re.M).group(1)
        for part in ("/usr/share/snmp/mibs /root/.snmp/mibs", "sha256sum",
                     "/etc/snmp/snmp.conf /etc/snmp/snmptrapd.conf", "ExecStart", "Environment"):
            assert part in fn, part


class _Answer:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def _loki(stamps_ns, seen):
    def ask(query, start, end):
        seen.append(query)
        return {"ok": True, "response": _Answer({"data": {"result": (
            [{"stream": {"job": "x"}, "values": [[str(ns), "x"] for ns in stamps_ns]}]
            if stamps_ns else [])}})}
    return ask


class TestUpdatesAfterStepChecks:
    def test_both_are_checks_update_can_run(self):
        assert host_steps.CHECKS["severity-label"] is host_steps.check_severity_label
        assert host_steps.CHECKS["trap-label"] is host_steps.check_trap_label

    def test_done_once_loki_holds_a_labelled_line_and_by_the_decided_selector(self):
        for fn, query in ((host_steps.check_severity_label,
                           '{job="network_syslog", severity=~"[0-7]"}'),
                          (host_steps.check_trap_label, '{job="snmptrapd", trap_oid=~".+"}')):
            seen = []
            done = fn(ask=_loki([2_000_000_000 * 10**9], seen))
            assert done["state"] == "done" and "2033-05-18 03:33 UTC" in done["detail"]
            assert seen == [query]

    def test_none_is_not_done_and_a_failed_ask_is_unknown(self):
        for fn in (host_steps.check_severity_label, host_steps.check_trap_label):
            assert fn(ask=_loki([], []))["state"] == "not_done"
            got = fn(ask=lambda q, s, e: {"ok": False, "error": "HTTP 502"})
            assert got == {"state": "unknown", "detail": "Loki did not answer: HTTP 502"}
            unread = fn(ask=lambda q, s, e: {"ok": True, "response": None})
            assert unread["state"] == "unknown"
        assert host_steps.check({"check": "trap-label"})["state"] in ("unknown", "not_done")


def test_the_script_parses_and_puts_the_config_back_on_failure():
    assert subprocess.run(["bash", "-n", SCRIPT], capture_output=True).returncode == 0
    text = _text()
    assert re.search(r"^ON_FAIL=.*sudo install .*'\$BEFORE' '\$CONFIG'.*restart alloy", text, re.M)
    assert re.search(r'^check "the new config is valid Alloy" rc0 "" "alloy validate ', text, re.M)
    assert text.index('check "the installed config is C722') < text.index('step "install the new config"')
