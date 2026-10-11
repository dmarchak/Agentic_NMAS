"""The lab sync's sanitiser, run under bash on the nine REAL fleet configs (lab tooling,
`lab/clab-sync/clab-startup-sync.sh`).

These classes were in tests/test_lab_startup.py beside the product's lab-startup check. C663
took that check out of Mercury; the sanitiser is the lab's, and its tests moved here unchanged:
every golden line reaches the startup file or is reported by a named rule (C604), device state
is split by reason (C610), and the removed report stays in proportion (C609).
"""

import re
import subprocess

import pytest

from tests.test_clab_sync_commit import _function

FLEET = "tests/fixtures/configs/fleet"
HOSTS = ["r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4"]
DIALECT = {h: ("cisco_iosxe" if h.startswith("r") else "cisco_ios") for h in HOSTS + ["r5"]}


def _golden(h):
    return open(f"{FLEET}/{h}.cfg", encoding="utf-8").read()


#: The management profile's two lines, as every golden carries them since its deploy (the
#: operator's C553 walk, 2026-10-09): the edit made to each real fleet config below.
PROFILE_LINES = ["ip ssh source-interface Loopback0", "ip tftp source-interface Loopback0"]
ALL = HOSTS + ["r5"]
STRUCTURE = ("!", "", "end")


def _with_profile(h, extra=()):
    """*h*'s real config with the management profile's lines (and *extra*) where IOS puts
    global lines: before `line con 0`."""
    text = _golden(h)
    i = text.index("\nline con 0") + 1
    return text[:i] + "".join(f"{l}\n" for l in [*PROFILE_LINES, *extra]) + text[i:]


def _render_reporting(h, golden):
    """``(file, report lines)``: the sync's own render, its stderr kept."""
    script = (_function("kind_for") + _function("sanitise") + _function("render_device")
              + f'\nrender_device {h} "$(kind_for {DIALECT[h]})" "$(cat)"\n')
    out = subprocess.run(["bash", "-c", script], input=golden, capture_output=True, text=True,
                         check=True)
    return out.stdout, [l for l in out.stderr.splitlines() if l.strip()]


class TestEveryGoldenLineSurvivesOrIsReported:
    """C604 (the operator's C553 walk, 2026-10-09): the sync dropped `ip tftp
    source-interface Loopback0` from all nine startup files by a rule with no reason, and said
    nothing. Every golden line reaches the file unless a NAMED rule removes it, and every
    removal is reported, by rule and device."""

    @pytest.mark.parametrize("h", ALL)
    def test_each_line_is_in_the_file_or_reported_by_a_named_rule(self, h):
        golden = _with_profile(h)
        text, report = _render_reporting(h, golden)
        kept = set(text.splitlines())
        reported = {}
        for line in report:
            assert line.startswith(f"REMOVED {h} "), line
            rule, _sep, removed = line[len(f"REMOVED {h} "):].partition(": ")
            assert rule and " " not in rule, line
            reported.setdefault(removed, rule)
        lost = [l for l in golden.splitlines()
                if l.strip() not in STRUCTURE and l not in kept and l not in reported]
        assert lost == [], f"{h}: lines neither in the file nor reported: {lost[:5]}"
        assert set(reported) <= set(golden.splitlines()), "a report names only golden lines"

    @pytest.mark.parametrize("h", ALL)
    def test_the_management_profile_s_lines_reach_every_file(self, h):
        text, report = _render_reporting(h, _with_profile(h))
        for line in PROFILE_LINES:
            assert line in text.splitlines(), f"{h}: {line!r} dropped; reported {report}"

    def test_a_source_naming_the_removed_management_interface_is_dropped_and_said(self):
        """The narrowed rule: the router's management interface is removed, so a source on it
        would point at nothing at boot; the switch removes no interface, so its line stays."""
        line = "ip tftp source-interface GigabitEthernet1"
        text, report = _render_reporting("r2", _with_profile("r2", [line]))
        assert line not in text.splitlines()
        assert f"REMOVED r2 source-on-removed-interface: {line}" in report
        assert "ip tftp source-interface Loopback0" in text.splitlines()
        sw = "ip tftp source-interface GigabitEthernet0/0"
        text, report = _render_reporting("s1", _with_profile("s1", [sw]))
        assert sw in text.splitlines() and not any(sw in r for r in report)

    def test_vrnetlab_s_own_bootstrap_lines_are_removed_by_their_named_rule(self):
        text, report = _render_reporting(
            "r2", _with_profile("r2", ["ip domain name example.com", "ip ssh maxstartups 128"]))
        assert "REMOVED r2 vrnetlab-bootstrap: ip domain name example.com" in report
        assert "REMOVED r2 vrnetlab-bootstrap: ip ssh maxstartups 128" in report


class TestDeviceStateIsSplitByReason:
    """The operator, 2026-10-09: `device-state` lumped configuration with reported state.
    Version, boot markers and the licence UDI stay; `platform console serial` is vrnetlab's
    serial console; what IOS-XE writes itself is its own rule; `license boot level` passes, so
    the startup file matches the golden. On r2's real capture."""

    def test_each_line_goes_to_its_rule_and_the_licence_level_passes(self):
        text, report = _render_reporting("r2", _golden("r2"))
        lines = text.splitlines()
        assert "license boot level network-premier addon dna-premier" in lines
        assert not any("license boot level" in r for r in report)
        want = {
            "license udi pid C8000V sn 9XXXXXXXXXX": "device-state",
            "platform console serial": "vrnetlab-serial-console",
            "memory free low-watermark processor 68484": "ios-xe-written",
            "diagnostic bootup level minimal": "ios-xe-written",
            "platform punt-keepalive disable-kernel-core": "ios-xe-written",
            "platform qfp utilization monitor load 80": "ios-xe-written",
        }
        for line, rule in want.items():
            assert f"REMOVED r2 {rule}: {line}" in report, (line, rule)
            assert line not in lines
        assert any(r.startswith("REMOVED r2 device-state: version ") for r in report)


def _report_removed(tmp_path, run_lines, extra_stderr=""):
    """The sync's report_removed, run under bash: (stdout, stderr)."""
    run = tmp_path / "run.txt"
    run.write_text("".join(f"{l}\n" for l in run_lines) + extra_stderr)
    kept = tmp_path / "state" / "removed-last.txt"
    script = _function("report_removed") + f"\nreport_removed {str(run)!r} {str(kept)!r}\n"
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    return out.stdout, out.stderr, kept


class TestTheRemovedReportIsInProportion:
    """The operator, 2026-10-09: 642 identical REMOVED lines every 30 minutes. One line per rule
    with its count and devices; per line only what the previous run did not remove; the full
    list kept on the host, owner-only."""

    RUN = ["REMOVED r1 certificate: 3082 0101", "REMOVED r2 certificate: 3082 0202",
           "REMOVED s1 banner: banner motd ^C", "REMOVED r1 ios-xe-written: memory free x"]

    def test_the_first_run_summarises_says_all_are_new_and_keeps_the_list(self, tmp_path):
        out, _err, kept = _report_removed(tmp_path, self.RUN)
        assert "Removed by the sanitiser: 4 line(s)" in out
        assert re.search(r"REMOVED certificate:\s+2 on r1 r2\n", out), out
        assert re.search(r"REMOVED banner:\s+1 on s1\n", out), out
        assert "every line is new to this run" in out and out.count("  NEW REMOVED ") == 4
        assert kept.read_text().splitlines() == self.RUN
        assert oct(kept.stat().st_mode & 0o777) == "0o600"

    def test_a_run_like_the_last_prints_no_line_detail(self, tmp_path):
        _report_removed(tmp_path, self.RUN)
        out, _err, _kept = _report_removed(tmp_path, self.RUN)
        assert "NEW " not in out and "The previous run removed every one of these too." in out
        assert len(out.splitlines()) == 1 + 3 + 1, out      # the total, 3 rules, the sentence

    def test_only_a_line_the_last_run_did_not_remove_is_detailed(self, tmp_path):
        _report_removed(tmp_path, self.RUN)
        out, _err, kept = _report_removed(tmp_path, self.RUN + ["REMOVED r6 device-state: version 17.6"])
        assert out.count("  NEW ") == 1 and "  NEW REMOVED r6 device-state: version 17.6" in out
        assert len(kept.read_text().splitlines()) == 5

    def test_anything_else_on_the_render_s_stderr_is_passed_on(self, tmp_path):
        _out, err, kept = _report_removed(tmp_path, self.RUN, "awk: a warning\n")
        assert "awk: a warning" in err and "awk" not in kept.read_text()
