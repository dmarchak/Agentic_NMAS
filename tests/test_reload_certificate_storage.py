"""Reload's "running against startup" gate on a C8000v (walk W1, 2026-10-16, a cutover
blocker): IOS-XE keeps a certificate chain's certificates in nvram: as files, so startup
holds a pointer (` certificate ca 01 nvram:CiscoLicensi#1CA.cer`) where running prints the
certificate inline, and `show startup-config` prints its own header line (`Using N out of M
bytes`). The gate counted both as unsaved lines and refused every C8000v reload, after a
successful Persist too: "4 line(s) differ".

Built from two real captures:
- r6's own difference, `tests/fixtures/reload/r6_archive_config_differences.txt` (the
  operator's capture in walk W1, 2026-10-16 ~00:51Z: `show archive config differences
  nvram:startup-config system:running-config`), split into its startup side (the `-` lines)
  and its running side (the `+` lines) under their chain headers (`_r6_sides`);
- r1's whole running and startup, `tests/fixtures/transcripts/r1/` (read together through the
  tool's own session on the NMAS host, 2026-10-01; README there), with the one edit Netmiko's
  `send_command(strip_prompt=True, strip_command=True)` makes, the prompts and the echo out
  (`_read`): the same chains, certificates and files as r6's, asserted, and the same 4 lines
  differing before the fix.

- r6's pair, and r1's, with `dir nvram:` listing both files: the gate passes, saying the 2
  certificates are kept as files (both present) and running shows them inline.
- A pointer whose file `dir nvram:` does not list: fails, naming it; an error read lists none.
- A real line differing as well: the old wording, its count leaving the certificate storage out.
- A different certificate (another serial) in startup's pointer: still a difference.
- vIOS (s1's real pair): no certificate pointer, so no `dir nvram:` read and no certificate
  words; its startup header is not a difference either.
- The read: `dir nvram:` is sent only when startup keeps a certificate there, and every
  command the preview sends is a Tier 1 read.
"""

import os

import pytest

from modules import readonly_commands
from modules.nsot import normalize, reload_op, roundtrip
from tests.test_device_capture_v2 import lab  # noqa: F401 (the fixture)
from tests.test_reload_v2 import _gate, _reads

T = os.path.join(os.path.dirname(__file__), "fixtures", "transcripts")
#: r6's `show archive config differences nvram:startup-config system:running-config`, the
#: operator's capture in walk W1, 2026-10-16 (tests/fixtures/reload/README.md).
R6_DIFF = os.path.join(os.path.dirname(__file__), "fixtures", "reload",
                       "r6_archive_config_differences.txt")


def _r6_sides() -> dict:
    """r6's two sides of the difference, from its archive diff: each chain header with its
    `-` lines (startup's) and its `+` lines (running's), the marker taken out of each line."""
    sides, opened, header = {"startup": [], "running": []}, {}, ""
    with open(R6_DIFF, encoding="utf-8") as fh:
        for line in fh.read().splitlines():
            if not line.strip() or line.startswith("!"):
                continue
            if not line[:1].isspace():
                header = line
                continue
            body = line.lstrip()
            side = {"+": "running", "-": "startup"}[body[0]]
            if opened.get(side) != header:
                sides[side].append(header)
                opened[side] = header
            sides[side].append(line[:len(line) - len(body)] + body[1:])
    return {k: "\n".join(v) for k, v in sides.items()}

#: `dir nvram:` on r6, a real capture: one allowlisted read through Mercury's reads engine on
#: the host, 2026-10-16 01:42Z (run 20261016T014249797070Z), unedited.
DIR_NVRAM = """Directory of nvram:/

10      -rw-              820                    <no date>  IOS-Self-Sig#1.cer
9       -rw-              805                    <no date>  CiscoLicensi#1CA.cer
8       -rw-              136                    <no date>  ifIndex-table
7       -rw-               17                    <no date>  ecfm_ieee_mib
6       ----              351                    <no date>  persistent-data
5       -rw-               60                    <no date>  ma_trap_keyword
3       -rw-             1507                    <no date>  sdwan_trap.eci
2       ----                4                    <no date>  private-KS1
1       ----               31                    <no date>  vudi
32771   -rw-             4219                    <no date>  underlying-config
32770   ----             7202                    <no date>  private-config
32769   -rw-             4219                    <no date>  startup-config

33554432 bytes total (33532719 bytes free)
"""


def _read(device: str, command: str) -> str:
    """A transcript as `send_command(strip_prompt=True, strip_command=True)` returns it: what
    the device printed after the command's echo, up to its prompt."""
    with open(os.path.join(T, device, command.replace(" ", "_") + ".txt"),
              encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    echo = next(i for i, line in enumerate(lines)
                if line.removeprefix(f"{device}#") == command)
    out = lines[echo + 1:]
    while out and out[-1].strip() in ("", f"{device}#"):
        out.pop()
    return "\n".join(out)


@pytest.fixture(scope="module")
def r1():
    return {"running": _read("r1", "show running-config"),
            "startup": _read("r1", "show startup-config")}


@pytest.fixture(scope="module")
def s1():
    return {"running": _read("s1", "show running-config"),
            "startup": _read("s1", "show startup-config")}


class TestR6sOwnDifference:
    """r6's archive diff, the operator's capture: startup's pointers against running's inline
    certificates, exactly as r6 printed them."""

    def test_the_capture_holds_both_sides(self):
        sides = _r6_sides()
        assert [p["file"] for p in normalize.certificate_pointers(sides["startup"])] == [
            "nvram:IOS-Self-Sig#1.cer", "nvram:CiscoLicensi#1CA.cer"]
        assert sides["running"].count("quit") == 2, "both certificates inline, each closed"

    def test_r6_s_certificates_are_the_same_when_both_files_are_present(self):
        sides = _r6_sides()
        same = roundtrip.startup_is_running(sides["startup"], sides["running"], DIR_NVRAM)
        assert same["equal"], same
        assert reload_op._unsaved_words("r6", same) == (
            "they are the same; startup keeps r6's 2 certificates as files in nvram: "
            "(both present), running shows them inline")

    def test_r6_s_ca_certificate_absent_from_nvram_fails_naming_it(self):
        sides = _r6_sides()
        listing = DIR_NVRAM.replace("CiscoLicensi#1CA.cer", "something-else.cer")
        same = roundtrip.startup_is_running(sides["startup"], sides["running"], listing)
        assert not same["equal"]
        assert "nvram:CiscoLicensi#1CA.cer" in reload_op._unsaved_words("r6", same)

    def test_the_old_comparison_counted_the_walk_s_4_lines(self, r1):
        """r6's certificate storage is 3 of them (the self-signed chain was already left out);
        the 4th is the header `show startup-config` prints, here r1's real one."""
        sides = _r6_sides()
        old = roundtrip.stored_is_device(sides["startup"], sides["running"])
        assert len(old["only_left"]) + len(old["only_right"]) == 3, old
        header = r1["startup"].splitlines()[0]
        assert normalize.STARTUP_HEADER.match(header), header
        old = roundtrip.stored_is_device(header + "\n" + sides["startup"], sides["running"])
        assert len(old["only_left"]) + len(old["only_right"]) == 4, old

    def test_r1_s_whole_pair_is_the_same_shape(self, r1):
        """r1's real running and startup, read together: the same chains, certificates and
        files as r6's capture, and the same 4 lines differing before the fix."""
        r6 = normalize.certificate_pointers(_r6_sides()["startup"])
        mine = normalize.certificate_pointers(r1["startup"])
        assert [(p["chain"], p["line"]) for p in mine] == [(p["chain"], p["line"]) for p in r6]
        old = roundtrip.stored_is_device(r1["startup"], r1["running"])
        assert len(old["only_left"]) + len(old["only_right"]) == 4, old


class TestTheGate:
    def test_the_pair_with_both_files_present_passes(self, r1):
        same = roundtrip.startup_is_running(r1["startup"], r1["running"], DIR_NVRAM)
        assert same["equal"], same
        assert [p["file"] for p in same["present"]] == [
            "nvram:IOS-Self-Sig#1.cer", "nvram:CiscoLicensi#1CA.cer"]
        assert same["missing"] == []
        assert reload_op._unsaved_words("r6", same) == (
            "they are the same; startup keeps r6's 2 certificates as files in nvram: "
            "(both present), running shows them inline")

    def test_judge_passes_it_on_a_c8000v(self, lab, r1):  # noqa: F811
        reads = _reads(lab, running=r1["running"], startup=r1["startup"])
        reads["dirs"] = dict(reads["dirs"], **{reload_op.NVRAM: DIR_NVRAM})
        g = _gate(reload_op.judge("Lab", "r2", "cisco_iosxe", reads), "unsaved")
        assert g["state"] == "pass", g
        assert "2 certificates as files in nvram: (both present)" in g["detail"]
        assert "lose" not in g["detail"]

    def test_a_pointer_whose_file_is_absent_fails_naming_it(self, r1):
        listing = DIR_NVRAM.replace("CiscoLicensi#1CA.cer", "something-else.cer")
        same = roundtrip.startup_is_running(r1["startup"], r1["running"], listing)
        assert not same["equal"]
        assert [p["file"] for p in same["missing"]] == ["nvram:CiscoLicensi#1CA.cer"]
        words = reload_op._unsaved_words("r6", same)
        assert "certificate ca 01 of SLA-TrustPoint as nvram:CiscoLicensi#1CA.cer" in words
        assert "does not list it" in words
        assert "IOS-Self-Sig" not in words, "the file that is present is not named"
        assert "line(s) differ" not in words, "the storage is not counted as lines"

    @pytest.mark.parametrize("listing", ["", "%Error opening nvram:/ (No such device)"])
    def test_an_empty_or_failed_listing_finds_no_file(self, r1, listing):
        same = roundtrip.startup_is_running(r1["startup"], r1["running"], listing)
        assert not same["equal"] and len(same["missing"]) == 2

    def test_a_real_line_differing_keeps_the_old_wording_and_its_count(self, lab, r1):  # noqa: F811
        running = r1["running"].replace("\nhostname r1\n", "\nhostname r1-new\n")
        assert running != r1["running"]
        reads = _reads(lab, running=running, startup=r1["startup"])
        reads["dirs"] = dict(reads["dirs"], **{reload_op.NVRAM: DIR_NVRAM})
        g = _gate(reload_op.judge("Lab", "r2", "cisco_iosxe", reads), "unsaved")
        assert g["state"] == "fail"
        assert g["detail"] == ("2 line(s) differ: a reload would boot startup and lose them; "
                               "save them first (Persist…)")

    def test_a_different_certificate_is_still_a_difference(self, r1):
        startup = r1["startup"].replace("certificate ca 01 nvram:", "certificate ca 02 nvram:")
        assert startup != r1["startup"]
        same = roundtrip.startup_is_running(startup, r1["running"], DIR_NVRAM)
        assert not same["equal"]
        assert any("certificate ca 02" in line for line in same["only_left"]), same
        assert any("certificate ca 01" in line for line in same["only_right"]), same


class TestVIOS:
    def test_no_pointer_no_certificate_words(self, lab, s1):  # noqa: F811
        assert normalize.certificate_pointers(s1["startup"]) == []
        g = _gate(reload_op.judge("Lab", "r2", "cisco_ios",
                                  _reads(lab, running=s1["running"], startup=s1["startup"])),
                  "unsaved")
        assert (g["state"], g["detail"]) == ("pass", "they are the same: it boots what it runs")

    def test_its_startup_header_is_not_a_difference(self, s1):
        assert normalize.STARTUP_HEADER.match(s1["startup"].splitlines()[0])
        assert roundtrip.startup_is_running(s1["startup"], s1["running"], "")["equal"]


class _Conn:
    def __init__(self, startup):
        self.startup, self.sent = startup, []

    def send_command(self, command, **_kw):
        self.sent.append(command)
        return {"show startup-config": self.startup,
                "show version": 'System image file is "bootflash:packages.conf"\n',
                "show boot": "BOOT variable = bootflash:packages.conf,12;\n",
                "dir nvram:": DIR_NVRAM}.get(command, "")


class TestTheRead:
    @pytest.fixture
    def read(self, monkeypatch):
        monkeypatch.setattr("modules.config_read.read", lambda conn, host: "hostname x\n")

        def go(startup):
            conn = _Conn(startup)
            monkeypatch.setattr("modules.connection.with_temp_connection",
                                lambda device, fn: fn(conn))
            return reload_op.read_device({"hostname": "x"}), conn.sent
        return go

    def test_dir_nvram_is_read_when_startup_keeps_a_certificate_there(self, read, r1):
        got, sent = read(r1["startup"])
        assert "dir nvram:" in sent and got["dirs"][reload_op.NVRAM] == DIR_NVRAM
        for command in sent:
            assert readonly_commands.refusal(command) == "", command

    def test_not_on_vios(self, read, s1):
        got, sent = read(s1["startup"])
        assert "dir nvram:" not in sent and reload_op.NVRAM not in got["dirs"]
