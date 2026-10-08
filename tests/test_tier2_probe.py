"""The Tier 2 probe (scripts/nmas-tier2-probe; docs/NSOT_TIER2_PRIVILEGED.md section 5).

The probe MEASURES what the Tier 2 commands ask and do, so its tests hold its reading and
deciding, never a claim about the devices: the prompts below are inputs to its parser (what it
must answer, and what it must not), and the BGP and interface reads are real captures
(`tests/fixtures/operational/`). The device session is faked at the probe's seam.
"""

import calendar
import importlib.util
import os
import types
from importlib.machinery import SourceFileLoader

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS = os.path.join(ROOT, "tests", "fixtures", "operational")
PATH = os.path.join(ROOT, "scripts", "nmas-tier2-probe")


def _load():
    spec = importlib.util.spec_from_file_location("tier2probe", PATH,
                                                  loader=SourceFileLoader("tier2probe", PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = _load()


def _cap(name):
    with open(os.path.join(OPS, name), encoding="utf-8") as fh:
        return fh.read()


SUMMARY = _cap("r3__show_ip_bgp_summary.txt")
BRIEF = _cap("r1__show_ip_interface_brief.txt")


def _args(**kw):
    base = {"list_name": "Lab", "device": "r2", "actor": "op@example.invalid", "apply": False,
            "interface": "Loopback0", "arp_interface": "", "allow_live_bgp": False,
            "bgp_peer": "", "out": ""}
    return types.SimpleNamespace(**{**base, **kw})


def _utc(h, m):
    return calendar.timegm((2026, 10, 8, h, m, 0, 0, 0, 0))


class TestReading:
    @pytest.mark.parametrize("text, prompt", [
        ('Clear "show interface" counters on this interface [confirm]', True),
        ("\nClear logging buffer [confirm]\n", True),
        ("r2#", False), ("All possible debugging has been turned off\nr2#", False), ("", False)])
    def test_a_confirm_is_the_one_question_answered(self, text, prompt):
        assert bool(P.confirm_prompt(text)) is prompt
        assert P.question(text) == ""

    @pytest.mark.parametrize("text", ["Proceed with reload? [yes/no]:", "Destination filename?",
                                      "Are you sure? [y/n]"])
    def test_any_other_question_is_named_and_never_answered(self, text):
        assert P.confirm_prompt(text) == "" and P.question(text) == text

    @pytest.mark.parametrize("text, seconds", [
        ("4d13h", (4 * 24 + 13) * 3600), ("01:02:03", 3723), ("2w3d", 17 * 86400),
        ("00:00:05", 5), ("never", None), ("", None)])
    def test_up_down_as_seconds(self, text, seconds):
        assert P.uptime_seconds(text) == seconds

    def test_the_peers_from_a_real_summary(self):
        peers = P.bgp_peers(SUMMARY)
        assert list(peers) == ["198.51.100.1"]
        assert peers["198.51.100.1"]["up"] == "4d13h" and peers["198.51.100.1"]["established"]

    def test_a_soft_refresh_that_reset_the_session_is_said(self):
        before = P.bgp_peers(SUMMARY)["198.51.100.1"]
        reset = P.bgp_peers(SUMMARY.replace("4d13h", "00:00:12"))["198.51.100.1"]
        grown = P.bgp_peers(SUMMARY.replace("4d13h", "4d14h"))["198.51.100.1"]
        assert P.bgp_verdict(before, reset) == {"verdict": "reset",
                                                "why": "Up/Down fell from 4d13h to 00:00:12"}
        assert P.bgp_verdict(before, grown)["verdict"] == "not reset"
        assert P.bgp_verdict(before, None)["verdict"] == "unknown"

    def test_the_management_interface_from_a_real_brief(self):
        first = BRIEF.splitlines()[1].split()
        assert P.management_interface(BRIEF, first[1]) == first[0]
        assert P.management_interface(BRIEF, "192.0.2.250") == ""


class TestRefusedBeforeTouching:
    @pytest.mark.parametrize("h, m, inside", [(8, 29, False), (8, 30, True), (9, 9, True),
                                              (9, 10, False)])
    def test_the_backup_window(self, h, m, inside):
        assert P.in_backup_window(_utc(h, m)) is inside
        why = P.refusal(_args(apply=True), now=_utc(h, m))
        assert ("backup window" in why) is inside

    @pytest.mark.parametrize("kw, words", [
        ({"interface": "Lo0;reload"}, "is not one interface name"),
        ({"arp_interface": "Gi2 Gi3"}, "is not one interface name"),
        ({"bgp_peer": "all"}, "is not an address"),
        ({"apply": True, "actor": ""}, "needs --list, --device and --actor")])
    def test_an_argument_out_of_shape(self, kw, words):
        assert words in P.refusal(_args(**kw), now=_utc(12, 0))

    def test_steps_not_asked_for_are_not_measured(self):
        rows = {s["key"]: s for s in P.plan(_args())}
        assert rows["clear-arp"]["unmeasured"] == "no --arp-interface named"
        assert "--allow-live-bgp" in rows["bgp-soft"]["unmeasured"]
        assert rows["clear-counters"]["command"] == "clear counters Loopback0"


class Conn:
    """A device at the probe's seam: reads answered from a script, sends recorded."""

    def __init__(self, reads, sends):
        self.reads, self.sends, self.sent = reads, sends, []

    def send_command_timing(self, cmd, **kw):
        self.sent.append(cmd)
        return self.sends.get(cmd, "r2#")


@pytest.fixture
def device(monkeypatch):
    first = BRIEF.splitlines()[1].split()
    calls = {}

    def run_device_command(conn, cmd, **kw):
        seq = conn.reads[cmd]
        calls[cmd] = calls.get(cmd, 0) + 1
        return seq[min(calls[cmd], len(seq)) - 1] if isinstance(seq, list) else seq

    monkeypatch.setattr("modules.commands.run_device_command", run_device_command)
    return {"hostname": "r2", "ip": first[1], "mgmt": first[0]}


ARP = "Protocol  Address          Age (min)  Hardware Addr   Type   Interface\n"
ROW = "Internet  198.51.100.{n}      1   5254.0000.000{n}  ARPA   GigabitEthernet2\n"


def _reads(arp_after=None):
    return {"show ip interface brief": BRIEF,
            "show interfaces Loopback0": "Loopback0 is up\n  5 packets input",
            "show ip arp GigabitEthernet2": arp_after or [
                ARP + ROW.format(n=1) + ROW.format(n=2), ARP, ARP + ROW.format(n=1),
                ARP + ROW.format(n=1) + ROW.format(n=2)],
            "show logging": "Syslog logging: enabled\nLog Buffer (8192 bytes):\n*line one",
            "show debugging": "",
            "show ip bgp summary": [SUMMARY, SUMMARY.replace("4d13h", "4d14h")]}


SENDS = {"clear counters Loopback0": 'Clear "show interface" counters on this interface [confirm]',
         "clear logging": "Clear logging buffer [confirm]",
         "undebug all": "All possible debugging has been turned off\nr2#"}


class TestMeasuring:
    def test_each_step_measured_a_confirm_answered_once(self, device):
        conn = Conn(_reads(), SENDS)
        steps = P.plan(_args(arp_interface="GigabitEthernet2", allow_live_bgp=True))
        results, stopped = P.measure(conn, steps, device, {}, sleep=lambda s: None)
        assert stopped == ""
        assert results["clear-counters"]["prompt"].endswith("[confirm]")
        assert conn.sent.count("\n") == 2, "Enter answered the two confirms, nothing else"
        assert results["clear-logging"]["before"].startswith("Syslog logging"), "kept first"
        assert results["undebug-all"]["result"] == "measured" and "prompt" not in results["undebug-all"]
        assert results["clear-arp"]["arp"] == {"before": 2, "after": 2, "back_after_s": 2.0,
                                               "words": "2 of 2 entries back after 2 s"}
        assert results["bgp-soft"]["command"] == "clear ip bgp 198.51.100.1 soft"
        assert results["bgp-soft"]["bgp"]["verdict"] == "not reset"

    def test_another_question_stops_the_run_unanswered(self, device):
        sends = {**SENDS, "clear counters Loopback0": "Proceed with this? [yes/no]:"}
        conn = Conn(_reads(), sends)
        results, stopped = P.measure(conn, P.plan(_args()), device, {}, sleep=lambda s: None)
        assert stopped == "Proceed with this? [yes/no]:"
        assert results["clear-counters"]["result"] == "stopped"
        assert "\n" not in conn.sent and "clear logging" not in conn.sent, conn.sent

    def test_the_management_interface_is_never_cleared(self, device):
        conn = Conn(_reads(), SENDS)
        steps = P.plan(_args(arp_interface=device["mgmt"]))
        results, _s = P.measure(conn, steps, device, {}, sleep=lambda s: None)
        assert results["clear-arp"]["result"] == "not measured"
        assert "management address" in results["clear-arp"]["why"]
        assert not any(c.startswith("clear arp") for c in conn.sent)

    def test_arp_not_back_in_time_is_said_with_the_count(self, device, monkeypatch):
        monkeypatch.setattr(P, "ARP_WAIT", 3)
        conn = Conn(_reads(arp_after=[ARP + ROW.format(n=1) + ROW.format(n=2), ARP]), SENDS)
        steps = P.plan(_args(arp_interface="GigabitEthernet2"))
        results, _s = P.measure(conn, steps, device, {}, sleep=lambda s: None)
        assert results["clear-arp"]["arp"]["words"] == "0 of 2 entries, not back within 3 s"

    def test_a_dry_run_connects_nothing(self, monkeypatch, capsys):
        monkeypatch.setattr(P, "_session", lambda d: pytest.fail("a dry run connected"))
        monkeypatch.setattr("sys.argv", ["nmas-tier2-probe"])
        assert P.main() == 0
        assert "DRY RUN: nothing connects" in capsys.readouterr().out
