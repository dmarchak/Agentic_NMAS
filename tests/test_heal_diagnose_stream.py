"""The "a telemetry stream lost" runbook (C2828; modules/heal/diagnose_stream.py), read-only and
deterministic, on the diagnosis engine: the device to its collector on the stream's port, both
ends, and the time since the stream's cause was put back.

On the fleet's real intent (tests/test_heal_diagnose.py's `fleet`: r2's two real subscriptions,
101 and 102), each edited minimally where a scenario needs it, the edit said beside it (r2's
receiver and one interface moved to the documentation ranges, as the socket captures are), and
real captures: r6's `show telemetry ietf subscription all` (tests/fixtures/diagnose/), r2's
pings (H18's), and a kernel's socket and address tables (tests/fixtures/diagnose/collector/,
its README naming each edit). The receiver read has no capture (C2890): it is sent and never
interpreted, so the hypotheses that need it say their evidence is incomplete.

- **H11 W8, measured:** r7's streams down 40 minutes after r6 was put back, the collector
  holding an established session from r7 while r7 had given it up: the diagnosis leads with
  the stream outliving its cause, then the half-open session, never "no cause found".
- **Stale against outlived:** a cause put back sooner than the alert can clear is said as
  that (diagnose again later), never as a stream stuck.
- **IPv4 and IPv6:** the collector's IPv4 sessions on a dual-stack listener (printed as
  ``::ffff:<v4>``) read as IPv4; an IPv6 receiver pinged with `ping ipv6` and its session
  read from `tcp6`.
- **Each rule** (`STREAM_RULES`) with a planted case; the words name no template letter.
"""
import os
import re
import shutil

import pytest

from tests.test_heal_diagnose import ACTOR, Fleet, fleet, quiet
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "diagnose")
COLLECTOR = os.path.join(FIX, "collector")
_DEVICES = [{"hostname": h, "ip": f"192.0.2.{n}", "device_type": t}
            for h, n, t in (("r1", 11, "cisco_xe"), ("r2", 12, "cisco_xe"),
                            ("s1", 21, "cisco_ios"))]
#: When the diagnosis runs, and when the stream was lost (H11 W8's times: lost 20:04:50 UTC,
#: r6's change 20:00:51, put back 20:05, diagnosed about 20:45).
NOW = 1_794_170_700.0                                # 2026-11-08T20:45:00Z
LOST = NOW - 2410.0                                  # 20:04:50
CHANGED = NOW - 2649.0                               # 20:00:51
BACK = NOW - 2400.0                                  # 20:05:00


def text(*parts) -> str:
    with open(os.path.join(FIX, *parts), encoding="utf-8") as fh:
        return fh.read()


BRIEF = text("r6__show_telemetry_ietf_subscription_all.txt")
#: r2's real pings, the destination in the text written as the collector (the parser reads
#: the summary line only).
PING_OK = text("r2__ping_10.255.1.14_source_Loopback0_repeat_5_timeout_2.txt").replace(
    "10.255.1.14", "192.0.2.10")
PING_NONE = text("r2__ping_10.255.3.99_repeat_5_timeout_2.txt").replace("10.255.3.99",
                                                                        "192.0.2.10")
PING6_OK = text("r2__ping_ipv6_2001_DB8_1_14_source_Loopback0_repeat_5_timeout_2.txt").replace(
    "2001:DB8:1::14", "2001:DB8::10")
V4_RECEIVER = "receiver ip address 192.0.2.10 57000 protocol grpc-tcp"
V6_RECEIVER = "receiver ip address 2001:db8::10 57000 protocol grpc-tcp"


def at_collector(receiver=V4_RECEIVER):
    """The edit: r2's subscriptions' receiver *receiver* (the lab's 10.255.1.10 57000 in the
    documentation range), and r2 Gi2 at 192.0.2.6 and 2001:DB8:4::6 (the far ends the socket
    captures hold)."""
    def edit(intents):
        for s in intents["r2"]["telemetry"]:
            s["settings"] = [receiver if l.startswith("receiver ") else l
                             for l in s["settings"]]
        for i in intents["r2"]["interfaces"]:
            if i["name"] == "GigabitEthernet2":
                i["ipv4"], i["ipv6"] = "192.0.2.6 255.255.255.0", ["2001:DB8:4::6/64"]
    return edit


def proc(tmp_path, *, tcp=True, tcp6=True, tables=None, v6only=None) -> str:
    """A /proc of the collector's captured tables: *tcp* or *tcp6* False keeps only that
    table's heading (its rows dropped); *tables(name, text)* changes a table."""
    root = tmp_path / "proc"
    (root / "net").mkdir(parents=True)
    for name in ("tcp", "tcp6", "if_inet6", "fib_trie"):
        with open(os.path.join(COLLECTOR, name), encoding="ascii") as fh:
            body = fh.read()
        if (name == "tcp" and not tcp) or (name == "tcp6" and not tcp6):
            body = body.splitlines()[0] + "\n"
        if tables:
            body = tables(name, body)
        (root / "net" / name).write_text(body, encoding="ascii")
    if v6only is not None:
        (root / "sys" / "net" / "ipv6").mkdir(parents=True)
        (root / "sys" / "net" / "ipv6" / "bindv6only").write_text(f"{v6only}\n")
    return str(root)


def answers(brief=BRIEF, ping=PING_OK, ping6=None) -> dict:
    out = {("r2", "show telemetry ietf subscription all"): brief,
           ("r2", "show telemetry ietf subscription 101 receiver"): "",
           ("r2", "show telemetry ietf subscription 102 receiver"): ""}
    if ping is not None:
        out[("r2", "ping 192.0.2.10 repeat 5 timeout 2")] = ping
    if ping6 is not None:
        out[("r2", "ping ipv6 2001:db8::10 repeat 5 timeout 2")] = ping6
    return out


def cleared(at=BACK, how="put back") -> dict:
    return {"state": "cleared", "device": "r1", "changed_at": CHANGED, "cleared_at": at,
            "how": how, "why": ""}


def target(cause=None, subs=("101", "102")) -> dict:
    return {"device": "r2", "subscriptions": list(subs), "lost_at": LOST, "settle_s": 150,
            "cause": cause if cause is not None else cleared()}


@pytest.fixture
def world(networks, monkeypatch):  # noqa: F811 (the fixture)
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in _DEVICES])
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, c, read_timeout=None: conn.answer(c))
    return networks


def stream(tmp_path, got_answers=None, tgt=None, edit=None, receiver=V4_RECEIVER,
           session=None, logs=quiet, **pk):
    from modules.heal import diagnose as D
    from modules.heal import diagnose_stream as S
    model, intents = fleet(edit or at_collector(receiver))
    f = session or Fleet(answers() if got_answers is None else got_answers)
    root = proc(tmp_path, **pk)
    got = D.run("Default", "stream_lost", tgt or target(), ACTOR, session=f, logs=logs,
                model=model, intents=intents, now=NOW,
                collector=lambda a, p, s: S.read_collector(a, p, s, proc=root))
    return got, f


def rules(got) -> list:
    return [h["rule"] for h in got["hypotheses"]]


# ── The parsers and the tables, on real captures ────────────────────────────────────────────

class TestTheCaptures:
    def test_the_brief_names_each_subscription_and_its_state(self):
        from modules.heal.diagnose_parse import parse
        got = parse("telemetry_brief", BRIEF)
        assert got["state"] == "parsed", got
        assert got["facts"] == {"101": {"type": "Configured", "state": "Valid",
                                        "filter": "xpath"},
                                "102": {"type": "Configured", "state": "Valid",
                                        "filter": "xpath"}}

    def test_a_brief_with_no_heading_is_unreadable_never_none_held(self):
        from modules.heal.diagnose_parse import parse
        got = parse("telemetry_brief", "  101  Configured  Valid  xpath\n")
        assert got["state"] == "unreadable" and "no subscription table" in got["why"]
        assert parse("telemetry_brief", "% Invalid input detected at '^' marker.\n")[
            "state"] == "unsupported"

    def test_this_hosts_addresses_from_the_trie_and_if_inet6(self, tmp_path):
        import ipaddress

        from modules.heal import diagnose_stream as S
        mine, why = S.local_addresses(proc(tmp_path))
        assert why == ""
        want = {ipaddress.ip_address(a) for a in ("192.0.2.10", "127.0.0.1", "2001:db8::10",
                                                  "::1")}
        assert want <= mine
        assert ipaddress.ip_address("192.0.2.6") not in mine
        assert ipaddress.ip_address("192.0.2.255") not in mine, "a broadcast leaf is not LOCAL"

    def test_an_ipv4_listener_and_session_bound_to_the_collectors_address(self, tmp_path):
        from modules.heal import diagnose_stream as S
        got = S.read_collector("192.0.2.10", 57000, ["192.0.2.6"],
                               proc=proc(tmp_path, tcp6=False))
        assert got["state"] == "read", got
        assert got["listening"] == ["192.0.2.10:57000"]
        assert got["sessions"] == [{"remote": "192.0.2.6", "rport": 60235,
                                    "state": "ESTABLISHED"}]
        assert got["others"] == 1, "192.0.2.7's session is another device's"

    def test_a_dual_stack_listener_reads_an_ipv4_session_as_ipv4(self, tmp_path):
        from modules.heal import diagnose_stream as S
        got = S.read_collector("192.0.2.10", 57000, ["192.0.2.6"],
                               proc=proc(tmp_path, tcp=False))
        assert got["listening"] == ["[::]:57000"], "IPv6's wildcard takes IPv4 (bindv6only 0)"
        assert got["sessions"] == [{"remote": "192.0.2.6", "rport": 60235,
                                    "state": "ESTABLISHED"}]

    def test_an_ipv6_session_on_the_collector(self, tmp_path):
        from modules.heal import diagnose_stream as S
        got = S.read_collector("2001:db8::10", 57000, ["2001:db8:4::6"],
                               proc=proc(tmp_path, tcp=False))
        assert got["listening"] == ["[::]:57000"]
        assert got["sessions"] == [{"remote": "2001:db8:4::6", "rport": 41714,
                                    "state": "ESTABLISHED"}]
        assert got["others"] == 0

    def test_bindv6only_keeps_the_ipv6_wildcard_off_ipv4(self, tmp_path):
        from modules.heal import diagnose_stream as S
        got = S.read_collector("192.0.2.10", 57000, ["192.0.2.6"],
                               proc=proc(tmp_path, tcp=False, v6only=1))
        assert got["listening"] == []

    def test_a_collector_elsewhere_is_not_read_and_a_missing_table_is_unread(self, tmp_path):
        from modules.heal import diagnose_stream as S
        got = S.read_collector("192.0.2.50", 57000, ["192.0.2.6"], proc=proc(tmp_path))
        assert got["state"] == "elsewhere"
        assert got["why"] == ("192.0.2.50 is not an address of Mercury's host, so the "
                              "collector's listener and sessions are not read here")
        os.remove(os.path.join(str(tmp_path), "proc", "net", "tcp6"))
        got = S.read_collector("192.0.2.10", 57000, ["192.0.2.6"],
                               proc=os.path.join(str(tmp_path), "proc"))
        assert got["state"] == "unread" and "tcp6 could not be read" in got["why"]


# ── The plan, from intent alone ─────────────────────────────────────────────────────────────

class TestThePlan:
    def plan(self, tgt, edit=None):
        from modules.heal import diagnose as D
        model, intents = fleet(edit or at_collector())
        return D.plan("Default", "stream_lost", tgt, model=model, intents=intents)

    def test_the_device_its_lost_subscriptions_and_its_collector(self):
        p = self.plan(target())
        assert p["words"] == "r2's subscriptions 101 and 102 to 192.0.2.10 port 57000"
        assert [c["command"] for c in p["reads"]["r2"]] == [
            "show telemetry ietf subscription all",
            "show telemetry ietf subscription 101 receiver",
            "show telemetry ietf subscription 102 receiver",
            "ping 192.0.2.10 repeat 5 timeout 2"]
        assert "192.0.2.6" in p["addresses"] and "2001:db8:4::6" in p["addresses"]

    def test_an_ipv6_receiver_is_pinged_with_ping_ipv6(self):
        p = self.plan(target(), at_collector(V6_RECEIVER))
        assert p["reads"]["r2"][-1]["command"] == "ping ipv6 2001:db8::10 repeat 5 timeout 2"
        assert p["words"].endswith("to 2001:db8::10 port 57000")

    @pytest.mark.parametrize("sub", ["101 | redirect flash:x", "101\nreload", "x101",
                                     "2147483648", ""])
    def test_a_subscription_id_spliced_is_one_token_of_its_shape(self, sub):
        from modules.heal import diagnose as D
        assert D.render("telemetry_receiver", "cisco_iosxe", sub="2147483647") == (
            "show telemetry ietf subscription 2147483647 receiver")       # the control
        with pytest.raises(D.Refused, match="is not a telemetry subscription id"):
            D.render("telemetry_receiver", "cisco_iosxe", sub=sub)

    def test_a_device_with_no_subscription_is_refused_by_name(self):
        from modules.heal import diagnose as D
        with pytest.raises(D.Refused, match="intent declares no telemetry subscription on s1"):
            self.plan({"device": "s1", "subscriptions": ["101"]})

    def test_a_subscription_intent_lacks_is_said_and_not_read(self):
        p = self.plan(target(subs=("101", "103")))
        assert p["subscriptions"] == ["101"]
        assert "subscription 103 is not in r2's intent, so not read" in p["outside"]

    def test_a_receiver_without_address_and_port_reads_no_collector(self):
        def edit(intents):
            at_collector()(intents)
            for s in intents["r2"]["telemetry"]:
                s["settings"] = [l for l in s["settings"] if not l.startswith("receiver ")]
        p = self.plan(target(), edit)
        assert p["collectors"] == [] and len(p["reads"]["r2"]) == 3
        assert ("subscription 101's collector is not read: intent gives it no receiver "
                "address and port") in p["outside"]


# ── Runs, through the one reads engine ──────────────────────────────────────────────────────

class TestTheRuns:
    def test_w8_the_stream_outlived_its_cause_and_the_session_is_half_open(self, world,
                                                                           tmp_path):
        from modules.nsot import reads
        got, f = stream(tmp_path, tcp6=False)
        assert got["state"] == "done", got
        assert rules(got)[:2] == ["outlived_cause", "half_open"], got["hypotheses"]
        first = got["hypotheses"][0]
        assert first["claim"] == (
            "r2's telemetry hasn't recovered since r1 was put back at 2026-11-08T20:05:00Z, 40 minutes "
            "before this diagnosis: the stream outlived its cause, so it is stuck at r2 or "
            "the collector, not waiting on r1")
        assert got["words"].startswith("2 hypotheses, the first strong: r2's telemetry "
                                       "hasn't recovered since r1 was put back at 2026-11-08T20:05:00Z")
        half = got["hypotheses"][1]
        assert "192.0.2.6 port 60235" in half["claim"] and half["incomplete"], half
        assert "C2890" in half["incomplete"][0]
        assert "remove its receiver, wait about 10 s, add it back" in half["todo"]
        checks = [r["check"] for r in got["ruled_out"]]
        assert "r2 reaches the collector 192.0.2.10: 5 of 5 answered" in checks
        assert ("the collector listens on 192.0.2.10 port 57000, with 1 established "
                "session(s) from other addresses") in checks
        assert "r2's subscriptions 101 and 102 read Valid" in checks
        runs = {r["id"]: r for r in reads.runs("Default")["runs"]}
        assert set(got["runs"]) == set(runs) and len(runs) == 1
        assert all(r["by"] == "diagnosis" for r in runs.values())
        assert {c for _h, c in f.sent} == {c for _h, c in answers()}

    def test_stale_a_cause_put_back_a_minute_ago_is_not_a_stuck_stream(self, world, tmp_path):
        got, _f = stream(tmp_path, tgt=target(cleared(at=NOW - 60)), tcp6=False)
        assert "outlived_cause" not in rules(got)
        just = next(h for h in got["hypotheses"] if h["rule"] == "cause_just_cleared")
        assert just["strength"] == "circumstantial"
        assert just["claim"].startswith("r1 was put back at 2026-11-08T20:44:00Z, 60 s before this "
                                        "diagnosis, sooner than the lost-stream alert can "
                                        "clear (150 s)")
        assert just["todo"] == "Diagnose again after 2026-11-08T20:46:30Z"
        why = next(n["why"] for n in got["not_checked"] if n.get("rule") == "outlived_cause")
        assert why == "r1 was put back 60 s ago, sooner than the lost-stream alert can clear"

    def test_outlived_rules_out_just_cleared(self, world, tmp_path):
        got, _f = stream(tmp_path, tcp6=False)
        assert any(r["rule"] == "cause_just_cleared" and r["check"].startswith(
            "r1 was put back 40 minutes before this diagnosis, longer than the lost-stream "
            "alert takes to clear (150 s)") for r in got["ruled_out"])

    def test_ipv6_a_receiver_over_ipv6_and_its_session(self, world, tmp_path):
        got, f = stream(tmp_path, answers(ping=None, ping6=PING6_OK), receiver=V6_RECEIVER,
                        tcp=False)
        assert ("r2", "ping ipv6 2001:db8::10 repeat 5 timeout 2") in f.sent
        half = next(h for h in got["hypotheses"] if h["rule"] == "half_open")
        assert half["claim"].startswith("the collector still holds an established session "
                                        "from r2 (2001:db8:4::6 port 41714) on 2001:db8::10 "
                                        "port 57000")
        assert any(r["check"] == "r2 reaches the collector 2001:db8::10: 5 of 5 answered"
                   for r in got["ruled_out"])

    def test_the_device_not_reaching_its_collector_is_decisive_first(self, world, tmp_path):
        got, _f = stream(tmp_path, answers(ping=PING_NONE), tcp6=False)
        first = got["hypotheses"][0]
        assert (first["rule"], first["strength"]) == ("collector_unreached", "decisive")
        assert first["claim"] == "r2 does not reach the collector 192.0.2.10 (0 of 5 answered)"
        assert first["todo"] == "Run Can't reach from r2 to 192.0.2.10"

    def test_nothing_listening_on_the_collector(self, world, tmp_path):
        def drop_listener(name, body):
            return "\n".join(l for l in body.splitlines() if " 0A " not in l) + "\n"
        got, _f = stream(tmp_path, tcp6=False, tables=drop_listener)
        first = got["hypotheses"][0]
        assert (first["rule"], first["strength"]) == ("collector_down", "decisive")
        assert first["claim"].startswith("nothing on Mercury's host listens on 192.0.2.10 "
                                         "port 57000")
        assert not {"half_open", "no_session"} & set(rules(got))

    def test_no_session_from_the_device_though_it_reaches_the_collector(self, world, tmp_path):
        def drop_device(name, body):
            return "\n".join(l for l in body.splitlines() if "060200C0" not in l) + "\n"
        got, _f = stream(tmp_path, tcp6=False, tables=drop_device)
        h = next(h for h in got["hypotheses"] if h["rule"] == "no_session")
        assert h["claim"] == ("the collector listens on 192.0.2.10 port 57000 and holds no "
                              "session from r2, though r2 reaches it: r2 is not dialling out "
                              "to it, or something on the path drops port 57000")
        assert h["incomplete"] and "half_open" not in rules(got)

    def test_a_subscription_missing_or_not_valid_on_the_device(self, world, tmp_path):
        gone = BRIEF.replace("  102              Configured  Valid       xpath\n", "")
        got, _f = stream(tmp_path, answers(brief=gone), tcp6=False)
        h = next(h for h in got["hypotheses"] if h["rule"] == "stream_missing")
        assert (h["strength"], h["claim"]) == (
            "decisive", "r2 holds no subscription 102, though intent declares it: removed "
                        "outside intent")
        bad = BRIEF.replace("101              Configured  Valid  ",
                            "101              Configured  Invalid")
        got, _f = stream(tmp_path / "2", answers(brief=bad), tcp6=False)
        h = next(h for h in got["hypotheses"] if h["rule"] == "stream_invalid")
        assert h["claim"].startswith("r2's subscription 101 reads Invalid: r2 does not accept "
                                     "it")

    def test_the_device_not_read_points_at_its_path(self, world, tmp_path):
        def down(dev, fn):
            raise OSError("TCP connection to device failed")
        got, _f = stream(tmp_path, session=down, tcp6=False)
        first = got["hypotheses"][0]
        assert first["rule"] == "device_unread", got["hypotheses"]
        assert first["todo"] == "Run Can't reach toward r2 from its neighbour"
        assert "the stream and Mercury's own path to r2 are both cut" in first["claim"]

    def test_a_collector_elsewhere_is_said_not_checked(self, world, tmp_path):
        got, _f = stream(tmp_path, receiver="receiver ip address 192.0.2.50 57000 protocol "
                                             "grpc-tcp",
                         got_answers={**answers(ping=None),
                                      ("r2", "ping 192.0.2.50 repeat 5 timeout 2"): PING_OK})
        assert not {"collector_down", "half_open", "no_session"} & set(rules(got))
        whys = {n.get("rule"): n["why"] for n in got["not_checked"]}
        assert whys["half_open"] == ("192.0.2.50 port 57000: 192.0.2.50 is not an address of "
                                     "Mercury's host, so the collector's listener and sessions "
                                     "are not read here")

    def test_the_cause_still_standing(self, world, tmp_path):
        stands = {"state": "stands", "device": "r1", "changed_at": CHANGED, "why": ""}
        got, _f = stream(tmp_path, tgt=target(stands), tcp6=False)
        h = next(h for h in got["hypotheses"] if h["rule"] == "cause_stands")
        assert h["claim"] == ("r1's change at 2026-11-08T20:00:51Z, the likely cause, has not been read "
                              "back at intent: the stream waits on it")
        assert "outlived_cause" not in rules(got)

    def test_no_cause_found_is_not_checked_with_why(self, world, tmp_path):
        none = {"state": "none", "why": "no change on another device is in the heal records "
                                        "for the 10 minutes before the stream was lost"}
        got, _f = stream(tmp_path, tgt=target(none), tcp6=False)
        assert rules(got) == ["half_open"]
        whys = {n.get("rule"): n["why"] for n in got["not_checked"]}
        assert whys["outlived_cause"] == none["why"]

    def test_a_configuration_change_on_the_device_is_circumstantial(self, world, tmp_path):
        def logs(network, host, now):
            return {"state": "read", "why": "", "lines": [
                {"mnemonic": "SYS-5-CONFIG_I", "at": "2026-11-08T20:30:00Z", "text": ""}]}
        got, _f = stream(tmp_path, logs=logs, tcp6=False)
        h = next(h for h in got["hypotheses"] if h["rule"] == "stream_config_changed")
        assert h["strength"] == "circumstantial"

    def test_its_words_name_no_template_letter(self, world, tmp_path):
        import re
        got, _f = stream(tmp_path, tcp6=False)
        said = [got["words"], got["runbook_words"]] + [s["words"] for s in got["steps"]] + [
            h["claim"] for h in got["hypotheses"]] + [r["check"] for r in got["ruled_out"]]
        for line in said:
            assert not re.search(r"\b[AB]\b", line), line
        assert got["runbook_words"] == "a telemetry stream lost"

    def test_every_rule_has_a_planted_case_here(self):
        from modules.heal import diagnose_stream as S
        assert {r.name for r in S.STREAM_RULES} == {
            "device_unread", "stream_missing", "stream_invalid", "collector_unreached",
            "collector_down", "half_open", "no_session", "outlived_cause",
            "cause_just_cleared", "cause_stands", "stream_config_changed",
            # C2892: its planted cases are in TestTheStreamItself below.
            "stream_flowing"}


# ── Which incidents run it, and the cause from the heal records ─────────────────────────────

def stream_alert(sub: str, labelled=True) -> dict:
    t = {"kind": "alert", "key": f"alert:tel-{sub}", "epoch": LOST, "at": "",
         "rule": f"NMAS telemetry stream lost: r2 subscription {sub}", "interface": "",
         "words": f"the alert fired on r2 (subscription {sub})"}
    if labelled:
        t.update(subscription=sub, detect_seconds="150")
    return t


def change(epoch: float) -> dict:
    return {"kind": "config_change", "key": f"cfg:{epoch}", "epoch": epoch, "words": "CONFIG_I"}


class TestWhichIncidents:
    def test_a_lost_stream_runs_it_before_an_unreachable_alert(self):
        from modules.heal import auto_diagnose as AD
        model, intents = fleet()
        unreachable = {"kind": "alert", "rule": "Device unreachable (SNMP)", "epoch": LOST - 200}
        inc = {"id": "hi-r2", "device": "r2",
               "triggers": [unreachable, stream_alert("101"), stream_alert("102")]}
        got = AD.target_for("Default", inc, model=model, intents=intents, incidents=[],
                            decided=[])
        assert got["runbook"] == "stream_lost", got
        assert got["target"]["subscriptions"] == ["101", "102"]
        assert got["target"]["settle_s"] == 210, "the label's 150 s, and the group's 60 s"
        assert got["words"] == "\"a telemetry stream lost\" on r2 (subscriptions 101 and 102)"

    def test_a_trigger_from_before_the_label_is_read_by_its_title(self):
        from modules.heal import diagnose_stream as S
        assert S.stream_of(stream_alert("101", labelled=False)) == {"subscription": "101",
                                                                    "detect_s": 0}
        assert S.stream_of({"kind": "alert", "rule": "NMAS heartbeat missing: r2"}) == {}
        assert S.stream_of({"kind": "alert",
                            "rule": "NMAS telemetry stream lost: r2 subscription 1 x"}) == {}

    def test_the_cause_put_back_from_the_heal_records(self):
        from modules.heal import diagnose_stream as S
        inc = {"id": "hi-r2", "device": "r2", "triggers": [stream_alert("101")]}
        r1 = {"id": "hi-r1", "device": "r1", "state": "closed",
              "triggers": [change(CHANGED), change(BACK)]}
        decided = [{"incident": "hi-r1", "outcome": "cant_fix", "epoch": CHANGED + 130},
                   {"incident": "hi-r1", "outcome": "nothing", "epoch": BACK + 90}]
        got = S.cause_of(inc, [inc, r1], decided, LOST)
        assert (got["state"], got["device"], got["how"], got["cleared_at"]) == (
            "cleared", "r1", "put back", BACK)
        got = S.cause_of(inc, [inc, dict(r1, triggers=[change(CHANGED)])], decided, LOST)
        assert (got["how"], got["cleared_at"]) == ("read back at intent", BACK + 90)
        got = S.cause_of(inc, [inc, r1], decided[:1], LOST)
        assert got["state"] == "stands"

    def test_several_changed_names_none_and_a_named_one_wins(self):
        from modules.heal import diagnose_stream as S
        inc = {"id": "hi-r2", "device": "r2", "triggers": [stream_alert("101")]}
        r1 = {"id": "hi-r1", "device": "r1", "triggers": [change(CHANGED)]}
        r3 = {"id": "hi-r3", "device": "r3", "triggers": [change(CHANGED + 10)]}
        got = S.cause_of(inc, [r1, r3], [], LOST)
        assert got["state"] == "several" and "r1 and r3 each changed" in got["why"]
        named = dict(inc, triggers=[dict(stream_alert("101"), related=["r1"])])
        assert S.cause_of(named, [r1, r3], [], LOST)["device"] == "r1"
        long_ago = {"id": "hi-r1", "device": "r1", "triggers": [change(LOST - 3600)]}
        assert S.cause_of(inc, [long_ago], [], LOST)["state"] == "none"
        assert S.cause_of(inc, None, None, LOST)["state"] == "unread"

    def test_the_rule_words_reach_the_messages(self):
        from modules.heal import auto_diagnose as AD
        h = {"rule": "half_open", "strength": "strong", "incomplete": ["x"], "evidence": [
            {"read": "the TCP sockets on Mercury's host, port 57000"}]}
        assert AD.said(h) == ("A half-open session: the collector holding a session from the "
                              "device while its stream is lost (strong, evidence incomplete)")

    def test_the_generator_still_writes_what_this_runbook_reads(self):
        from modules.heal import diagnose_stream as S
        from tests.test_telemetry_rules import _load
        T = _load()
        assert S.ALERT_WINDOW_S == T.WINDOW_SECONDS
        doc = T.build({"r2": ["101"]}, "ds-uid")
        group = doc["groups"][0]
        assert group["interval"] == f"{S.ALERT_INTERVAL_S // 60}m"
        rule = group["rules"][0]
        m = S.TITLE.match(rule["title"])
        assert m and (m.group("device"), m.group("sub")) == ("r2", "101")
        assert (rule["labels"]["nmas"], rule["labels"]["subscription"]) == ("telemetry", "101")


# ── The device's receiver and the stream itself (C2890, C2892) ──────────────────────────────

#: The receiver reads, real captures (tests/fixtures/diagnose/README.md): r7's, Connected on
#: connection 496 while it was NOT streaming.
R7_101 = text("r7__show_telemetry_ietf_subscription_101_receiver.txt")
R7_102 = text("r7__show_telemetry_ietf_subscription_102_receiver.txt")


def with_receivers(a101=R7_101, a102=R7_102) -> dict:
    out = answers()
    out[("r2", "show telemetry ietf subscription 101 receiver")] = a101
    out[("r2", "show telemetry ietf subscription 102 receiver")] = a102
    return out


def flowing_run(tmp_path, series, got_answers=None, ss=None, **pk):
    from modules.heal import diagnose as D
    from modules.heal import diagnose_stream as S
    model, intents = fleet(at_collector())
    root = proc(tmp_path, **pk)
    return D.run("Default", "stream_lost", target(), ACTOR,
                 session=Fleet(got_answers or with_receivers()), logs=quiet, model=model,
                 intents=intents, now=NOW, series=series,
                 collector=lambda a, p, s: S.read_collector(a, p, s, proc=root, ss=ss))


PRESENT = {"state": "present", "count": 1, "why": "1 series with a sample in the last 90 s"}
ABSENT = {"state": "absent", "count": 0, "why": "no sample in the last 90 s"}


class TestTheStreamItself:
    def test_the_devices_side_is_evidence_and_complete(self, world, tmp_path):
        """C2890: with r7's real receiver answers, the half-open hypothesis names the device's
        own side (Connected on connection 496) and its evidence is complete."""
        got = flowing_run(tmp_path, lambda d, s: ABSENT, tcp6=False)
        half = next(h for h in got["hypotheses"] if h["rule"] == "half_open")
        assert ("r2 reads subscription 101's receiver 10.255.1.10 port 57000 Connected on "
                "connection 496") in half["claim"]
        assert half["incomplete"] == [], half["incomplete"]
        assert any(e.get("line") == "State Connected, connection 496"
                   for e in half["evidence"]), half["evidence"]

    def test_one_receiver_unreadable_is_the_only_one_incomplete(self, world, tmp_path):
        got = flowing_run(tmp_path, lambda d, s: ABSENT, with_receivers(a102=""), tcp6=False)
        half = next(h for h in got["hypotheses"] if h["rule"] == "half_open")
        assert len(half["incomplete"]) == 1 and "subscription 102's receiver" in \
            half["incomplete"][0] and "C2890" in half["incomplete"][0]

    def test_the_stream_back_is_the_symptom_gone(self, world, tmp_path):
        from modules.heal import auto_diagnose as AD
        got = flowing_run(tmp_path, lambda d, s: PRESENT, tcp6=False)
        assert got["hypotheses"] == [], got["hypotheses"]
        check = ("r2's subscriptions 101 and 102 have data in Prometheus now (a sample in the "
                 "last 90 s, the lost-stream alert's own query): the stream is back")
        assert {"check": check, "rule": "stream_flowing"} in got["ruled_out"]
        assert AD.symptom_gone(got) == check
        whys = {n.get("rule"): n["why"] for n in got["not_checked"]}
        assert whys["outlived_cause"].startswith("the stream is back")

    def test_the_stream_still_lost_is_said_and_decides_the_rest(self, world, tmp_path):
        from modules.heal import auto_diagnose as AD
        got = flowing_run(tmp_path, lambda d, s: ABSENT, tcp6=False)
        whys = {n.get("rule"): n["why"] for n in got["not_checked"]}
        assert whys["stream_flowing"] == ("subscriptions 101 and 102 on r2 have no sample in "
                                          "Prometheus in the last 90 s: the stream is still lost")
        assert "half_open" in rules(got) and AD.symptom_gone(got) == ""

    def test_prometheus_unread_decides_nothing(self, world, tmp_path):
        got = flowing_run(tmp_path, lambda d, s: {"state": "unread",
                                                  "why": "Prometheus is not configured"},
                          tcp6=False)
        whys = {n.get("rule"): n["why"] for n in got["not_checked"]}
        assert "Prometheus is not configured" in whys["stream_flowing"]
        assert set(rules(got)[:2]) == {"outlived_cause", "half_open"}, "judged as before"
        step = next(s for s in got["steps"] if s["step"] == "stream")
        assert step["result"] == "not_read"

    def test_a_session_receiving_now_is_not_half_open(self, world, tmp_path):
        """C2892: the kernel's socket diagnostics (ss_tni_4's, its device row's lastrcv written
        as 287 ms) say the session carries data, which /proc alone cannot."""
        ss4 = open(os.path.join(COLLECTOR, "ss_tni_4.txt"), encoding="utf-8").read()
        live = ss4.replace("lastrcv:5966281", "lastrcv:287")
        got = flowing_run(tmp_path, lambda d, s: ABSENT, ss=lambda p: (live, ""), tcp6=False)
        assert "half_open" not in rules(got)
        assert any("received data 0 s ago" in r["check"] for r in got["ruled_out"]
                   if r["rule"] == "half_open")
        stale = flowing_run(tmp_path / "2", lambda d, s: ABSENT, ss=lambda p: (ss4, ""),
                            tcp6=False)
        half = next(h for h in stale["hypotheses"] if h["rule"] == "half_open")
        assert "nothing received on it for 99 minutes" in half["claim"]


# ── Its times (the operator, 2026-11-13: raw UTC anywhere left; C3290) ──────────────────────

class TestItsTimesAreInstantsTheScreenDraws:
    """The runbook writes no time words: "put back at 20:05 UTC" was UTC on every screen that
    drew the claim. It writes the instant, and each screen draws it through the `times` filter
    in the viewer's zone, its UTC on the hover."""

    def test_no_string_the_module_builds_says_utc(self):
        """Every string constant in the module, its docstrings left out, by parsing."""
        import ast
        with open(os.path.join(ROOT, "modules", "heal", "diagnose_stream.py"),
                  encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        docs = {id(n.body[0].value) for n in ast.walk(tree)
                if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        said = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
        # About 700 strings on 2026-11-13: a walk that read few of them reads nothing.
        assert len(said) > 300, len(said)
        assert [s for s in said if re.search(r"\bUTC\b", s)] == []

    def test_a_claim_and_its_next_step_carry_the_instant(self, world, tmp_path):
        got, _f = stream(tmp_path, tgt=target(cleared(at=NOW - 60)), tcp6=False)
        just = next(h for h in got["hypotheses"] if h["rule"] == "cause_just_cleared")
        said = " ".join([just["claim"], just["todo"]] + [e.get("line", "")
                                                         for e in just["evidence"]])
        assert "UTC" not in said
        assert re.findall(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", said) == [
            "2026-11-08T20:44:00Z", "2026-11-08T20:46:30Z",
            "2026-11-08T20:00:51Z", "2026-11-08T20:44:00Z"], said

    def test_the_screen_draws_it_in_the_viewers_zone(self, world, tmp_path):
        import app as A
        from flask import render_template_string
        from tests.test_local_times import kept_zone
        got, _f = stream(tmp_path, tcp6=False)
        claim = got["hypotheses"][0]["claim"]
        with kept_zone("Asia/Kolkata"), A.app.test_request_context("/v2/attention"):
            drawn = render_template_string("{{ claim | times }}", claim=claim)
        assert ('since r1 was put back at <time class="clock" datetime="2026-11-08T20:05:00Z"'
                in drawn), drawn
        words = re.sub(r"<[^>]+>", "", drawn)
        # 20:05 UTC on 8 Nov is 01:35 on 9 Nov in Kolkata.
        assert "put back at Nov 9 01:35" in words and "UTC" not in words, words

    def test_every_screen_that_draws_a_hypothesis_draws_it_through_the_clock(self):
        """The population, by property: each v2 template naming a hypothesis's claim or next
        step (`h.claim`, `h.todo`). Each draws it through `times`."""
        from tests import source_index
        found = {}
        for path in source_index.tracked("templates/v2", suffix=".html", recursive=False):
            with open(path, encoding="utf-8") as fh:
                found[os.path.basename(path)] = re.findall(
                    r"\{\{\s*(h\.(?:claim|todo)[^}]*?)\s*\}\}", fh.read())
        drawn = {name: exprs for name, exprs in found.items() if exprs}
        assert {"_diagnose.html", "_attention.html", "_heal_proposal.html",
                "_fixit_section.html"} <= set(drawn), sorted(drawn)
        bare = [f"{name}: {e}" for name, exprs in drawn.items() for e in exprs
                if not re.search(r"\|\s*times\b", e)]
        assert bare == [], bare
