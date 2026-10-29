"""A rollback undoes an added INSTANCE of a repeatable command by its own `no` form.

Found 2026-10-29 by the change-record agent on r3's real config: after a deploy that ADDED
`ntp server 192.0.2.10` beside r3's own `ntp server 10.255.1.10`, `rollback_commands`
re-sent `ntp server 10.255.1.10` and never sent `no ntp server 192.0.2.10`, so the rollback
left the added server on the device. The cause: a line's setting key is the line without
its last word, so two NTP servers were "one setting at two values", and the rollback
"restored the old value". IOS keeps one line per server: the old one was never replaced.

The class (the survey of the eleven captures under tests/fixtures/configs/): a command IOS
keeps several of, one line per instance (`ntp server`, `logging host`, `ip route`, `ipv6
route`, `ipv6 address`, `ip helper-address`, `passive-interface`, a RIP `network`, flags
sharing a first word such as `ipv6 cef` beside `ipv6 unicast-routing`). Declared in
`deploy.REPEATABLE_COMMANDS`; such a line is undone by its own `no` form only when no line
the device held is the SAME instance (a held instance is restored, never negated), and
never beside a blanket (`passive-interface default`). Anything not declared is restored as
before, and the read-back names a pushed line still there beside what was re-sent.

Real captures, minimal edits; the pipeline's own rollback stage runs over a fake device.
"""

import os
import threading

import pytest

from modules.nsot.deploy import (REPEATABLE_COMMANDS, assert_rollback_provenance,
                                 landed_between, rollback_commands)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")


def _read(name):
    return open(os.path.join(FLEET, name), encoding="utf-8").read()


R3 = _read("r3.cfg")
S1 = _read("s1.cfg")
R1 = _read("r1.cfg")


def _with(config: str, *lines: str) -> str:
    return config.rstrip("\n") + "\n" + "\n".join(lines) + "\n"


def _lines(config: str) -> list:
    return [line.rstrip() for line in config.splitlines()]


def _held(config: str, start: str, end: str = "") -> str:
    """The one line of *config* starting with *start* and ending with *end*: read from the
    capture, so no address of it is typed here."""
    found = [line for line in _lines(config) if line.startswith(start) and line.endswith(end)]
    assert len(found) == 1, (start, end, len(found))
    return found[0]


#: r3's own static route to Null0 and its management VRF's default route, and s1's RIP
#: network, as the captures hold them.
NULL_ROUTE = _held(R3, "ip route ", " Null0")
MGMT_DEFAULT = _held(R3, "ip route vrf clab-mgmt 0.0.0.0 0.0.0.0 ")
SECOND_HOP = NULL_ROUTE.rsplit(" ", 1)[0] + " 192.0.2.1"
RIP_NETWORK = _held(S1, " network ")


def _undo(pushed, pre, post=None):
    """The rollback with nothing read (a completed push) and with the post-push capture."""
    landed = None if post is None else landed_between(pre, post)
    out = rollback_commands(pushed, pre, landed=landed)
    assert_rollback_provenance(out, pushed, pre)
    return out


class TestTheFixtureCanExhibitTheCase:
    def test_r3_holds_one_of_each_instance_the_cases_add_beside(self):
        lines = _lines(R3)
        for held in ("ntp server 10.255.1.10", "logging host 10.255.1.10",
                     NULL_ROUTE, MGMT_DEFAULT,
                     "ipv6 route 2001:DB8:1::23/128 2001:DB8:3::23",
                     " ipv6 address 2001:DB8::2/64", " ip nat inside", " ip nat outside",
                     "logging trap critical"):
            assert held in lines, held
        assert not any("192.0.2." in line or "2001:DB8::10" in line for line in lines)

    def test_s1_holds_the_flags_and_the_rip_passives(self):
        lines = _lines(S1)
        assert {"ipv6 cef", "ipv6 unicast-routing", " passive-interface Vlan10",
                " passive-interface Vlan20", RIP_NETWORK} <= set(lines)
        assert len(RIP_NETWORK.split()) == 2

    def test_r1_holds_a_blanket_passive_interface(self):
        assert " passive-interface default" in _lines(R1)


class TestTheReportedCase:
    """The change-record agent's case 3, on r3."""

    PUSHED = ["ntp server 192.0.2.10"]

    def test_the_added_server_is_undone_by_its_own_no_form(self):
        post = _with(R3, *self.PUSHED)
        for out in (_undo(self.PUSHED, R3), _undo(self.PUSHED, R3, post)):
            assert out == ["no ntp server 192.0.2.10"], out

    def test_the_held_server_is_never_re_sent(self):
        assert "ntp server 10.255.1.10" not in _undo(self.PUSHED, R3)

    def test_an_ipv6_server_beside_the_ipv4_one(self):
        assert _undo(["ntp server 2001:DB8::10"], R3) == ["no ntp server 2001:DB8::10"]


#: (pushed program, its undo) on r3, each an instance added beside one the device held.
ADDED_BESIDE_A_HELD_INSTANCE = [
    (["logging host 192.0.2.10"], ["no logging host 192.0.2.10"]),
    ([SECOND_HOP], ["no " + SECOND_HOP]),
    (["ipv6 route 2001:DB8:1::23/128 2001:DB8:3::99"],
     ["no ipv6 route 2001:DB8:1::23/128 2001:DB8:3::99"]),
    # The management VRF's default route: a second next hop is removed, the held one kept.
    (["ip route vrf clab-mgmt 0.0.0.0 0.0.0.0 192.0.2.1"],
     ["no ip route vrf clab-mgmt 0.0.0.0 0.0.0.0 192.0.2.1"]),
    (["interface GigabitEthernet1", " ipv6 address 2001:DB8:9::2/64", "exit"],
     ["interface GigabitEthernet1", " no ipv6 address 2001:DB8:9::2/64", "exit"]),
    (["interface GigabitEthernet3", " ip helper-address 192.0.2.67", "exit"],
     None),  # r3 holds no helper: no collision, negated as any new line (the control)
]


class TestEveryDeclaredShapeOnARealConfig:
    @pytest.mark.parametrize("pushed,undo", ADDED_BESIDE_A_HELD_INSTANCE,
                             ids=[" ".join(p[-1 if len(p) == 1 else 1].split()[:2])
                                  for p, _u in ADDED_BESIDE_A_HELD_INSTANCE])
    def test_an_added_instance_is_negated(self, pushed, undo):
        expected = undo or [pushed[0], " no " + pushed[1].strip(), "exit"]
        post_lines = [line for line in pushed if line != "exit"]
        assert _undo(pushed, R3) == expected
        if len(post_lines) == 1:
            assert _undo(pushed, R3, _with(R3, *post_lines)) == expected

    def test_a_flag_beside_its_first_word_sibling(self):
        """s1 holds `ipv6 cef` and `ipv6 unicast-routing` (C201's pair): pushed onto s1
        without `ipv6 cef`, it is undone as itself, never by re-sending the sibling."""
        pre = "\n".join(l for l in S1.splitlines() if l.strip() != "ipv6 cef") + "\n"
        assert _undo(["ipv6 cef"], pre) == ["no ipv6 cef"]

    def test_a_rip_passive_interface_beside_held_ones(self):
        pushed = ["router rip", " passive-interface Vlan30", "exit"]
        assert _undo(pushed, S1) == ["router rip", " no passive-interface Vlan30", "exit"]

    def test_an_ipv6_logging_host_beside_a_held_one(self):
        """`logging host ipv6 ADDR`: the `ipv6` qualifier says where, not which, so two
        IPv6 hosts are two instances, never one by their shared `ipv6` word."""
        pre = _with(R3, "logging host ipv6 2001:DB8::20")
        assert _undo(["logging host ipv6 2001:DB8::10"], pre) == [
            "no logging host ipv6 2001:DB8::10"]

    def test_a_rip_network_beside_a_held_one(self):
        pushed = ["router rip", " network 192.0.2.0", "exit"]
        assert _undo(pushed, S1) == ["router rip", " no network 192.0.2.0", "exit"]


class TestANegationNeverReachesAHeldInstance:
    """Mode B's rule, here: a `no` form is sent only where it removes exactly the line
    the push added."""

    def test_the_same_instance_with_other_options_is_restored(self):
        """A route the device held, pushed again with another name: the held line is
        re-sent (IOS keeps one line per prefix and next hop), never `no ip route`."""
        held = "ip route 192.0.2.0 255.255.255.0 Null0 name before"
        pushed = ["ip route 192.0.2.0 255.255.255.0 Null0 name after"]
        assert _undo(pushed, _with(R3, held)) == [held]

    def test_a_blanket_passive_interface_is_never_negated_beside(self):
        """Under r1's `passive-interface default`, a pushed `passive-interface X` changes
        nothing IOS prints; `no passive-interface X` would make X active."""
        pushed = ["router rip", " passive-interface GigabitEthernet9", "exit"]
        out = _undo(pushed, R1)
        assert not any(line.strip().startswith("no passive-interface") for line in out), out

    def test_a_line_the_device_already_held_is_never_negated(self):
        """Everything pushed is treated as applied when nothing was read; a pushed line
        identical to a held one is not a change, and negating it would remove it."""
        pre = _with(R3, "ntp server 192.0.2.11")
        out = _undo(["ntp server 192.0.2.11"], pre)
        assert not any(line.startswith("no ") for line in out), out


class TestWhatIsNotDeclaredIsUnchanged:
    def test_a_single_valued_setting_is_restored_the_control(self):
        assert _undo(["logging trap debugging"], R3) == ["logging trap critical"]

    def test_an_undeclared_shape_is_restored_and_named(self):
        """`ip nat outside` beside r3's `ip nat inside` on one interface: whether IOS keeps
        both is not declared, so the held line is re-sent, never a `no` form whose reach is
        not known, and the pair is handed to the read-back to name."""
        pushed = ["interface GigabitEthernet3", " ip nat outside", "exit"]
        unsure = []
        out = rollback_commands(pushed, R3, unsure=unsure)
        assert out == ["interface GigabitEthernet3", " ip nat inside", "exit"], out
        assert unsure == [{"chain": ["interface GigabitEthernet3"], "line": "ip nat outside",
                           "held": "ip nat inside"}], unsure


class TestTheDeclarationAgainstTheCaptures:
    """Measured, not only declared: every setting key two lines of one section share in a
    real capture (the device holds both, so the command is repeatable) is declared, but the
    section markers the survey also counts."""

    MARKERS = {"address-family", "exit-address-family"}

    def test_every_coexisting_key_in_the_captures_is_declared(self):
        from modules.nsot.deploy import Leaf, _command_keys, _repeatable_identity, config_leaves
        from tests.source_index import tracked

        paths = tracked(os.path.join(ROOT, "tests", "fixtures", "configs"), suffix=".cfg")
        assert len(paths) >= 11
        found, undeclared = 0, []
        for path in paths:
            groups = {}
            for leaf in config_leaves(open(path, encoding="utf-8").read()):
                words = leaf.line.split()
                if not words or words[0] == "no" or words[0] in self.MARKERS:
                    continue
                key = (leaf.chain, _command_keys(leaf)[0])
                groups.setdefault(key, []).append(leaf)
            for (chain, _key), leaves in groups.items():
                if len(leaves) < 2:
                    continue
                found += 1
                for leaf in leaves:
                    if _repeatable_identity(chain, leaf.line) is None:
                        undeclared.append((os.path.basename(path), leaf.line.strip()))
        assert found >= 5, found
        assert not undeclared, undeclared

    def test_the_table_names_no_shape_twice(self):
        keys = [(sections, lead, exact) for sections, lead, _n, exact, _b in REPEATABLE_COMMANDS]
        assert len(keys) == len(set(keys))


# ── the pipeline's rollback stage, over a device that keeps one line per instance ──

IP = "192.0.2.13"


def _token():
    from modules.device import fernet
    return fernet.encrypt(b"").decode()


class _Device:
    """r3's running config after the push. `no X` removes exactly X; a positive line is
    added when absent: IOS's behaviour for a repeatable command."""

    def __init__(self, post):
        self.running = post
        self.sent = []

    def fresh(self, _dev, func):
        dev = self

        class _Conn:
            def send_command(self, _cmd, read_timeout=None):
                return dev.running
        return func(_Conn())

    def restore(self, _conn, cmds):
        self.sent.extend(cmds)
        lines = self.running.splitlines()
        for cmd in cmds:
            if cmd.strip() == "exit" or cmd.startswith(" "):
                continue                  # global lines only in these cases
            if cmd.startswith("no "):
                lines = [line for line in lines if line != cmd[3:]]
            elif cmd not in lines:
                lines.append(cmd)
        self.running = "\n".join(lines) + "\n"


@pytest.fixture
def run(monkeypatch):
    import modules.connection as C
    import modules.pipeline as P

    def _run(pushed, pre=R3):
        device = _Device(_with(pre, *pushed))
        monkeypatch.setattr(P, "_pre_change", lambda _ctx, ip: pre)
        monkeypatch.setattr(C, "with_temp_connection", device.fresh)
        monkeypatch.setattr(C, "get_persistent_connection", lambda dev, pool, lock: object())
        monkeypatch.setattr(P, "_restore_config", device.restore)
        monkeypatch.setattr(P, "_note_rolled_back_intent", lambda ctx: None)
        monkeypatch.setattr("modules.list_settings.value", lambda _l, _k, d=None: d)
        ctx = P.PipelineContext(
            config_type="template", device_ips=[IP], params={}, ip_params_map={},
            selected_devices=[{"ip": IP, "hostname": "r3", "username": "u",
                               "device_type": "cisco_xe", "password": _token(),
                               "secret": _token()}],
            connections_pool={}, pool_lock=threading.Lock(), config_id="tpl-r3",
            settle_sleep=lambda _s: None)
        ctx.rendered_commands = {IP: list(pushed)}
        ctx.push_results = {IP: {"ok": True, "output": ""}}
        P._capture_failure_state(ctx)
        P._stage_rollback(ctx)
        return ctx, device
    return _run


class TestThePipelineSaysWhatItAchieved:
    def test_the_added_server_is_removed_and_read_back_restored(self, run):
        ctx, device = run(["ntp server 192.0.2.10"])
        assert device.sent == ["no ntp server 192.0.2.10"]
        assert "ntp server 192.0.2.10" not in device.running.splitlines()
        assert "ntp server 10.255.1.10" in device.running.splitlines()
        assert ctx.rollback_outcome[IP]["state"] == "restored", ctx.rollback_outcome[IP]
        assert ctx.final_status == "rolled_back"

    def test_an_undeclared_pair_still_there_is_named_by_the_read_back(self, run):
        """`boot system` is not declared: the held line is re-sent, the fake device keeps
        both, and the read-back says which pushed line is still there and why, never only
        the re-sent line as an undo still needed."""
        import modules.pipeline as P

        held = "boot system bootflash:packages.conf"
        pushed = ["boot system bootflash:other.bin"]
        ctx, device = run(pushed, pre=_with(R3, held))
        out = ctx.rollback_outcome[IP]
        assert device.sent == [held]
        assert out["state"] == "incomplete", out
        assert "`boot system bootflash:other.bin` is still on the device" in out["detail"], out
        assert "REPEATABLE_COMMANDS" in out["detail"], out
        assert ctx.final_status == "rollback_failed"
        assert P.ROLLBACK_OK == ("restored", "nothing_to_undo")
