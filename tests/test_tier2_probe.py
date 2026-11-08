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


def _tier2(name):
    with open(os.path.join(ROOT, "tests", "fixtures", "tier2", name), encoding="utf-8") as fh:
        return fh.read()


SUMMARY = _cap("r3__show_ip_bgp_summary.txt")
BRIEF = _cap("r1__show_ip_interface_brief.txt")


def _args(**kw):
    base = {"list_name": "Lab", "device": "r2", "actor": "op@example.invalid", "apply": False,
            "interface": "", "arp_interface": "", "allow_live_bgp": False,
            "bgp_peer": "", "out": "", "step": []}
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
    @pytest.mark.parametrize("h, m, inside", [(8, 29, False), (8, 30, True), (9, 29, True),
                                              (9, 30, False)])
    def test_the_backup_window(self, h, m, inside):
        """2026-10-08, under MDT: 02:30 to 03:30 America/Denver is 08:30 to 09:30 UTC."""
        assert P.in_backup_window(_utc(h, m)) is inside
        why = P.refusal(_args(apply=True), now=_utc(h, m))
        assert ("backup window" in why) is inside

    @pytest.mark.parametrize("h, m, inside", [(8, 30, False), (9, 9, False), (9, 29, False),
                                              (9, 30, True), (10, 29, True), (10, 30, False)])
    def test_the_backup_window_moves_with_daylight_saving(self, h, m, inside):
        """C2613: the job is scheduled at 02:30 in the hypervisor's zone, so on 2026-11-06,
        under MST, the window is 09:30 to 10:30 UTC, and 08:30 UTC is outside it (measured from
        the hypervisor's task list: 02:30 local every night either side of 2026-11-01)."""
        now = calendar.timegm((2026, 11, 6, h, m, 0, 0, 0, 0))
        assert P.in_backup_window(now) is inside
        why = P.refusal(_args(apply=True), now=now)
        assert ("backup window" in why) is inside
        if inside:
            assert ("02:30 to 03:30 America/Denver (09:30 to 10:30 UTC on 2026-11-06)"
                    in why), why

    def test_a_zone_this_machine_cannot_read_refuses(self, monkeypatch):
        """A guard that cannot ask refuses: no zone data, and every instant is held."""
        monkeypatch.setattr(P, "BACKUP_ZONE", "Nowhere/Invalid")
        noon = calendar.timegm((2026, 11, 6, 12, 0, 0, 0, 0, 0))
        assert P.in_backup_window(noon) is True
        why = P.refusal(_args(apply=True), now=noon)
        assert "cannot read the zone Nowhere/Invalid" in why, why

    @pytest.mark.parametrize("kw, words", [
        ({"interface": "Lo0;reload"}, "is not one interface name"),
        ({"arp_interface": "Gi2 Gi3"}, "is not one interface name"),
        ({"bgp_peer": "all"}, "is not an address"),
        ({"apply": True, "actor": ""}, "needs --list, --device and --actor")])
    def test_an_argument_out_of_shape(self, kw, words):
        assert words in P.refusal(_args(**kw), now=_utc(12, 0))

    def test_only_the_steps_named_run(self):
        """A BGP-only run on r4 must not also clear its log buffer and counters."""
        rows = P.plan(_args(step=["bgp-soft"], allow_live_bgp=True, bgp_peer="198.51.100.3"))
        assert [(s["key"], s["command"]) for s in rows] == [
            ("bgp-soft", "clear ip bgp 198.51.100.3 soft")]
        assert "no such step: clear-everything" in P.refusal(_args(step=["clear-everything"]),
                                                             now=_utc(12, 0))

    def test_steps_not_asked_for_are_not_measured(self):
        rows = {s["key"]: s for s in P.plan(_args())}
        assert rows["clear-arp"]["unmeasured"] == "no --arp-interface named"
        assert "--allow-live-bgp" in rows["bgp-soft"]["unmeasured"]
        assert rows["clear-counters"]["unmeasured"] == "no --interface named (a data interface)"
        named = {s["key"]: s for s in P.plan(_args(interface="Loopback0"))}
        assert named["clear-counters"]["command"] == "clear counters Loopback0"
        assert "unmeasured" not in named["clear-counters"]


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
            "show ip bgp summary": [SUMMARY, SUMMARY.replace("4d13h", "4d14h")],
            # H21: the neighbour's own read before and after (r4's, 2026-11-07, its peer
            # renamed to r3's summary's).
            "show ip bgp neighbors 198.51.100.1": [
                _tier2("r4__show_ip_bgp_neighbors_established_before_soft.txt").replace(
                    "198.51.100.3", "198.51.100.1"),
                _tier2("r4__show_ip_bgp_neighbors_established_after_soft.txt").replace(
                    "198.51.100.3", "198.51.100.1")]}


SENDS = {"clear counters Loopback0": 'Clear "show interface" counters on this interface [confirm]',
         "clear logging": "Clear logging buffer [confirm]",
         "undebug all": "All possible debugging has been turned off\nr2#"}


class TestMeasuring:
    def test_each_step_measured_a_confirm_answered_once(self, device):
        conn = Conn(_reads(), SENDS)
        steps = P.plan(_args(interface="Loopback0", arp_interface="GigabitEthernet2",
                             allow_live_bgp=True))
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
        results, stopped = P.measure(conn, P.plan(_args(interface="Loopback0")), device, {},
                                     sleep=lambda s: None)
        assert stopped == "Proceed with this? [yes/no]:"
        assert results["clear-counters"]["result"] == "stopped"
        assert "\n" not in conn.sent and "clear logging" not in conn.sent, conn.sent

    def test_the_management_interface_is_never_cleared(self, device):
        """C583 (the operator, 2026-10-08): the first version cleared counters on Loopback0, the
        interface carrying the management address in this lab, while saying it never used it."""
        conn = Conn(_reads(), SENDS)
        steps = P.plan(_args(interface=device["mgmt"], arp_interface=device["mgmt"]))
        results, _s = P.measure(conn, steps, device, {}, sleep=lambda s: None)
        for key in ("clear-counters", "clear-arp"):
            assert results[key]["result"] == "not measured", key
            assert "management address" in results[key]["why"], key
        assert not any(c.startswith("clear counters") or c.startswith("clear arp")
                       for c in conn.sent), conn.sent

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


# ── H21: the BGP clears self-healing sends (board H 19.4, N16) ──────────────────────────────

ESTABLISHED = _tier2("r4__show_ip_bgp_neighbors_established_before_soft.txt").replace(
    "198.51.100.3", "198.51.100.1")


def _down(text=ESTABLISHED):
    return text.replace("BGP state = Established, up for 2w2d", "BGP state = Active")


def _back(text=ESTABLISHED):
    return (text.replace("up for 2w2d", "up for 00:00:05")
            .replace("Connections established 1; dropped 0",
                     "Connections established 2; dropped 1"))


class Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s


class TestTheBgpClears:
    def test_the_hard_clear_runs_only_when_named_and_only_on_a_named_peer(self):
        assert "bgp-hard" not in [s["key"] for s in P.plan(_args(allow_live_bgp=True,
                                                                 bgp_peer="198.51.100.1"))]
        rows = {s["key"]: s for s in P.plan(_args(step=["bgp-hard"], allow_live_bgp=True))}
        assert "--bgp-peer not given" in rows["bgp-hard"]["unmeasured"]
        rows = {s["key"]: s for s in P.plan(_args(step=["bgp-hard"]))}
        assert "--allow-live-bgp not given" in rows["bgp-hard"]["unmeasured"]
        row = P.plan(_args(step=["bgp-hard"], allow_live_bgp=True, bgp_peer="198.51.100.1"))[0]
        assert (row["command"], row["neighbour"]) == ("clear ip bgp 198.51.100.1",
                                                      "show ip bgp neighbors 198.51.100.1")
        assert "unmeasured" not in row

    def test_the_family_and_the_peer_must_agree(self):
        why = P.refusal(_args(bgp_peer="198.51.100.1", bgp_family="ipv6"), now=_utc(12, 0))
        assert "is an ipv4 address, and --bgp-family is ipv6" in why
        assert "is ipv4 or ipv6" in P.refusal(_args(bgp_family="ipx"), now=_utc(12, 0))
        row = P.plan(_args(step=["bgp-soft"], allow_live_bgp=True, bgp_family="ipv6",
                           bgp_peer="2001:DB8:51:1::2"))[0]
        assert row["command"] == "clear bgp ipv6 unicast 2001:DB8:51:1::2 soft"
        assert row["before"] == "show bgp ipv6 unicast summary"

    def _hard(self, device, declare, reads):
        conn = Conn({**_reads(), "show ip bgp neighbors 198.51.100.1": reads}, SENDS)
        steps = P.plan(_args(step=["bgp-hard"], allow_live_bgp=True, bgp_peer="198.51.100.1"))
        clock = Clock()
        results, _s = P.measure(conn, steps, device, {}, sleep=clock.sleep, clock=clock.time,
                                declare=declare)
        return conn, results["bgp-hard"]

    def test_a_window_first_then_the_seconds_back_to_established(self, device):
        seen = []

        def declare(dev, interface, seconds, why):
            seen.append((dev["hostname"], interface, seconds, list(conn_sent)))
            return {"ok": True, "record": {"from": "a", "until": "b", "via": "nmas-tier2-probe",
                                           "interfaces": [interface]}}

        conn_sent = []
        conn, row = self._hard(device, declare, [ESTABLISHED, _down(), _down(), _back()])
        conn_sent[:] = conn.sent
        assert seen == [("r2", "GigabitEthernet2", P.BGP_WAIT + P.BGP_WINDOW_MARGIN_S, [])]
        assert conn.sent == ["clear ip bgp 198.51.100.1"]
        assert row["result"] == "measured" and row["bgp"]["back_after_s"] == 2.0, row
        assert row["bgp"]["states"] == ["Active", "Established"]
        assert row["session_before"]["dropped"] == 0 and row["session_after"]["dropped"] == 1
        assert row["neighbour_before"] == ESTABLISHED, "the session before is kept"

    def test_no_window_sends_nothing(self, device):
        conn, row = self._hard(device, lambda *a: {"ok": False, "error": "unreadable"},
                               [ESTABLISHED])
        assert conn.sent == [] and row["result"] == "not measured"
        assert "the planned window for the clear could not be recorded (unreadable)" in row["why"]

    def test_a_session_not_back_is_said_with_its_last_state(self, device, monkeypatch):
        monkeypatch.setattr(P, "BGP_WAIT", 3)
        _c, row = self._hard(device, lambda *a: {"ok": True, "record": {}},
                             [ESTABLISHED, _down()])
        assert row["bgp"]["back_after_s"] is None
        assert row["bgp"]["words"] == "not back within 3 s (last state Active)"

    def test_the_ipv6_soft_clear_reads_the_wrapped_summary_row(self, device):
        six = _tier2("r4__show_bgp_ipv6_unicast_neighbors_established.txt")
        summary = _cap("r4__show_bgp_ipv6_unicast_summary.txt")
        conn = Conn({**_reads(), "show bgp ipv6 unicast summary": summary,
                     "show bgp ipv6 unicast neighbors 2001:DB8:51:1::2": six}, SENDS)
        steps = P.plan(_args(step=["bgp-soft"], allow_live_bgp=True, bgp_family="ipv6",
                             bgp_peer="2001:db8:51:1::2"))
        results, _s = P.measure(conn, steps, device, {}, sleep=lambda s: None)
        row = results["bgp-soft"]
        assert conn.sent == ["clear bgp ipv6 unicast 2001:DB8:51:1::2 soft"], row
        assert row["bgp"]["verdict"] == "not reset" and row["session"]["reset"] is False


#: r3's OSPF neighbour table, captured (tests/fixtures/operational/): six adjacencies FULL.
OSPF_FULL = _cap("r3__show_ip_ospf_neighbor.txt") if os.path.exists(os.path.join(
    ROOT, "tests", "fixtures", "operational", "r3__show_ip_ospf_neighbor.txt")) else ""


def _ospf_down(n=2):
    """The same table with its first *n* neighbour rows gone (the adjacencies a reset dropped),
    everything up to and including its header kept as captured."""
    lines = OSPF_FULL.splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.lstrip().startswith("Neighbor ID"))
    return "\n".join(lines[:i + 1] + lines[i + 1 + n:]) + "\n"


class TestTheOspfReset:
    """C2374 (board H, H5): the probe measures the OSPF process reset the heal's R8 proposal
    sends: its window first, naming every neighbour, the reset's own question alone answered,
    and the seconds until every adjacency formed before is formed again."""

    PROMPT = "Reset OSPF process 1? [no]: "

    def _run(self, device, reads, *, answer=None, declare=None):
        cmd = "clear ip ospf 1 process"
        conn = Conn({**_reads(), "show ip ospf neighbor": reads},
                    {cmd: answer if answer is not None else self.PROMPT})
        steps = P.plan(_args(step=["ospf-reset"], allow_live_ospf=True, ospf_process="1"))
        clock, seen = Clock(), []

        def ok(dev, interface, seconds, why, reset=""):
            seen.append((dev["hostname"], interface, seconds, reset, list(conn.sent)))
            return {"ok": True, "record": {"from": "a", "until": "b", "via": "nmas-tier2-probe",
                                           "expected": {"far_ends": [{"device": "r1",
                                                                      "interface": ""}]}}}
        results, stopped = P.measure(conn, steps, device, {}, sleep=clock.sleep,
                                     clock=clock.time, declare=declare or ok)
        return conn, results["ospf-reset"], seen, stopped

    def test_it_runs_only_when_named_with_its_flag_and_process(self):
        assert "ospf-reset" not in [s["key"] for s in P.plan(_args())], "never in a run of all"
        row = P.plan(_args(step=["ospf-reset"]))[0]
        assert "--allow-live-ospf not given" in row["unmeasured"]
        row = P.plan(_args(step=["ospf-reset"], allow_live_ospf=True))[0]
        assert "no --ospf-process named" in row["unmeasured"]
        row = P.plan(_args(step=["ospfv3-reset"], allow_live_ospf=True, ospf_process="1"))[0]
        assert row["command"] == "clear ipv6 ospf 1 process" and "unmeasured" not in row
        assert row["before"] == "show ipv6 ospf neighbor"
        assert P.refusal(_args(ospf_process="1; reload")).startswith(
            "REFUSED: --ospf-process '1; reload' is not one token of digits")

    def test_a_window_first_its_question_answered_then_the_seconds_back(self, device):
        conn, row, seen, stopped = self._run(
            device, [OSPF_FULL, _ospf_down(), _ospf_down(1), OSPF_FULL])
        assert not stopped and seen == [("r2", "", P.OSPF_WAIT + P.BGP_WINDOW_MARGIN_S,
                                         "clear-ospf-process", [])], seen
        assert conn.sent == ["clear ip ospf 1 process", "yes"], conn.sent
        assert (row["prompt"], row["answer"]) == ("Reset OSPF process 1? [no]:", "yes"), row
        assert row["formed_before"] == 6 and row["ospf"]["dropped"] is True
        # The read after the send shows two gone, the first watch read one gone (the drop
        # seen), and one poll of 2 s later all six formed again.
        assert row["settle_s"] == 2.0 and row["result"] == "measured", row
        assert row["planned_window"]["far_ends"] == [{"device": "r1", "interface": ""}]

    def test_another_question_is_never_answered(self, device):
        conn, row, _seen, stopped = self._run(
            device, [OSPF_FULL], answer="Reset ALL routing processes, and reload? [yes/no]: ")
        assert conn.sent == ["clear ip ospf 1 process"], "nothing answered"
        assert row["result"] == "stopped" and stopped, row

    def test_a_table_that_never_dropped_is_said_not_taken_as_a_return(self, device):
        _conn, row, _seen, _s = self._run(device, [OSPF_FULL])
        assert row["settle_s"] is None and row["ospf"]["words"] == "no drop was seen in the reads"

    def test_no_window_or_no_adjacency_sends_nothing(self, device):
        conn, row, _seen, _s = self._run(
            device, [OSPF_FULL],
            declare=lambda *a, **k: {"ok": False, "error": "the store is unreadable"})
        assert conn.sent == [] and row["result"] == "not measured"
        assert "could not be recorded (the store is unreadable)" in row["why"]
        conn, row, _seen, _s = self._run(device, [_ospf_down(6)])
        assert _ospf_down(6).count("FULL") == 0, "the header kept, every row gone"
        assert conn.sent == [] and "no adjacency formed before the reset (none)" in row["why"]


class TestTheWindowsIntent:
    """C2795: the probe's own window (`_window_for`) reads committed intent to name its far
    ends; one that cannot be read records no window, for a hard clear as for a reset, rather
    than a window naming none."""

    @pytest.mark.parametrize("reset,words", [
        ("clear ip ospf 1 process", "the reset's neighbours"),
        ("", "the cleared peer's device")], ids=["reset", "bgp-clear"])
    def test_intent_that_cannot_be_read_records_no_window(self, monkeypatch, reset, words):
        from modules import restarts
        from modules.heal import bounce
        monkeypatch.setattr(bounce, "committed_intents_of",
                            lambda network: (None, "host_vars/edge1.yml did not parse"))
        monkeypatch.setattr(restarts, "record_planned",
                            lambda *a, **k: pytest.fail("a window was recorded"))
        declare = P._window_for(_args(bgp_peer="198.51.100.3"))
        got = declare({"hostname": "edge1"}, "", 30.0, "a probe's clear", reset=reset)
        assert got == {"ok": False, "error": (
            "committed intent could not be read (host_vars/edge1.yml did not parse), so "
            f"{words} cannot be named")}
