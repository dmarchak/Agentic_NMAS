"""Out-of-band ZTP's operations (modules/nsot/console_ztp.py; docs/LAB9_PLAN.md section 8, O6a):
the console survey and the console kick-start, each through the device-operation lifecycle.

End to end on loopback: the shared fake NetBox (tests/fake_netbox.py) holds the device and its
console path, Mercury's console-server store holds the port's record, and a fake console server
(tests/console_fakes.py, a raw TCP console on IPv4 and IPv6 loopback, counting every byte it
receives) answers with the real console text (tests/fixtures/console/, README.md there): s5's
"Press RETURN" release, its diagnostic session's answers to the wake, `enable` and
`dir nvram:`. What no capture holds (the pager's echo, the configuration lines' prompts) is
written in the captured session's shape: the echo, a line break, the next prompt.

- the survey: blank when the console printed its prompt first and nvram's startup file is 0
  bytes (the MAC unknown, read from s5's own hardware summary; read from a MAC line on the
  router); a console found signed in is recorded not blank and nothing more is sent; refused
  when its hash moved;
- the kick-start: refused without a blank survey (naming which), for an actor who is not a
  verified person, when the hash moved (naming both), and when another operation holds the
  device (by name); it sends EXACTLY the previewed lines (the bytes the fake received) and
  records them; a password prompt mid-run stops it with nothing more sent, records the partial
  transcript and raises a Needs attention row; a recheck finding a saved configuration types
  nothing of it;
- Needs attention: a not-blank survey and a failed kick-start are rows naming what was found,
  the cause, the action and how they clear; a later good run clears them; one is acknowledged;
- retirement (C1553) removes the device's console path, its index entries and its runs;
- the one home for the host and credential-reference rules (C1558).
"""

import json
import os
import socket
import threading

import pytest

from modules.nsot import console_profiles as P
from modules.nsot import console_ztp as Z
from tests.console_fakes import Console, RawServer
from tests.fake_netbox import FakeNetBox
from tests.test_console_session import PNP, session_fixture

LIST = "console-o6"
BASE = "http://nb.invalid"
ACTOR = "p@example.invalid"
FAST = Z.Timings(settle_s=0.05, quiet_s=0.3, step_timeout_s=3.0, poll_s=0.02,
                 survey_bound_s=20.0, kickstart_bound_s=20.0)
PARAMS = {"hostname": "edge1", "interface": "GigabitEthernet0/1", "vlan": 10}
FAMILIES = pytest.mark.parametrize("family", [socket.AF_INET, socket.AF_INET6],
                                   ids=["ipv4", "ipv6"])


def _real():
    """The diagnostic session's answers: the wake's (banner and `Switch>`), `enable`'s and
    `dir nvram:`'s (startup-config 0 bytes)."""
    _sends, answers = session_fixture()
    return answers


def _hardware_summary() -> bytes:
    """`show version`'s answer: s5's own hardware summary, as its boot printed it (the tail of
    the boot fixture from its `Cisco IOSv` line), echoed and ended by the prompt."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "console",
                           "s5-boot-to-release.txt"), "rb") as fh:
        boot = fh.read()
    tail = boot[boot.index(b"Cisco IOSv ("):]
    return b"show version\r\n" + tail + b"\r\nSwitch#"


def _echo(line: str, prompt: str) -> bytes:
    return f"{line}\r\n{prompt}".encode()


def blank_answers():
    """A blank switch's answers to the survey after its prompt: RETURN, enable, the pager,
    show version, dir nvram:, disable."""
    wake, enable, nvram = _real()
    return [wake, enable, _echo("terminal length 0", "Switch#"), _hardware_summary(), nvram,
            _echo("disable", "Switch>")]


#: What the survey sends after the console's first prompt (RETURN), every phase.
SURVEY_SENDS = b"\renable\rterminal length 0\rshow version\rdir nvram:\rdisable\r"


def kick_answers(lines, recheck=None, cut=None):
    """A blank switch at `Switch>` (where its survey left it) answering the kick-start: the
    wake, enable, the recheck, then each line's echo and the prompt it leaves (`cut`: the index
    of the line answered by a password prompt instead)."""
    _wake, enable, nvram = _real()
    out = [b"\r\nSwitch>", enable, recheck or nvram]
    name = "Switch"
    for i, line in enumerate(lines):
        if cut is not None and i == cut:
            out.append(f"{line}\r\nPassword: ".encode())
            break
        if line.startswith("hostname "):
            name = line.split()[1]
        if line == "end":
            prompt = f"{name}#"
        elif line.startswith("vlan"):
            prompt = f"{name}(config-vlan)#"
        elif line.startswith("interface"):
            prompt = f"{name}(config-if)#"
        elif line.startswith("line"):
            prompt = f"{name}(config-line)#"
        elif line.startswith(" "):
            prompt = {"switchport": f"{name}(config-if)#", "ip": f"{name}(config-if)#",
                      "no": f"{name}(config-if)#", "exec-timeout": f"{name}(config-line)#"}[
                line.split()[0]]
        else:
            prompt = f"{name}(config)#"
        out.append(_echo(line, prompt))
    return out


class World:
    """The fake NetBox, the console-server store and a fake console server, wired."""

    def __init__(self, tmp_path, monkeypatch, family):
        from modules import config, netbox_guard
        import modules.netbox_client as nbc

        data = tmp_path / "data"
        data.mkdir()
        monkeypatch.setattr(config, "DATA_DIR", str(data))
        monkeypatch.setattr(config, "LISTS_DIR", str(tmp_path / "lists"))
        monkeypatch.setattr("modules.nsot.listref.exists", lambda n: n == LIST)
        monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE", str(tmp_path / "created.json"))
        monkeypatch.setattr(netbox_guard, "_MODIFIED_FILE", str(tmp_path / "modified.json"))
        monkeypatch.setattr(nbc, "_managed_tag_ids", {})
        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
        self.fake = fake = FakeNetBox()
        self.dev = fake.seed("dcim/devices", {"name": "edge1", "status": "planned"})
        self.cs = fake.seed("dcim/devices", {"name": "cons-1", "status": "active"})
        self.port = fake.seed("dcim/console-ports", {"device": self.dev["id"], "name": "con 0"})
        self.sport = fake.seed("dcim/console-server-ports", {"device": self.cs["id"],
                                                             "name": "port 5"})
        self.cable = fake.seed("dcim/cables", {
            "a_terminations": [{"object_type": "dcim.consoleport",
                                "object_id": self.port["id"]}],
            "b_terminations": [{"object_type": "dcim.consoleserverport",
                                "object_id": self.sport["id"]}],
            "status": "connected", "label": ""})
        self.consoles = []                      # what each connection is answered with, in order
        self.server = RawServer(self._next, family=family)
        self.set_port()

    def _next(self):
        greeting, answers = self.consoles.pop(0)
        return Console(greeting=greeting, answers=answers)

    def set_port(self, **over):
        from modules.nsot import console_servers
        record = {k: v for k, v in dict({"driver": "raw_tcp", "host": self.server.host,
                                         "tcp_port": self.server.port}, **over).items()
                  if v is not None}
        got = console_servers.set_port(self.sport["id"], record, actor=ACTOR)
        assert got["ok"], got

    def nb(self):
        return {"session": self.fake, "base": BASE}

    def survey_preview(self, profile="cisco_ios_switch"):
        return Z.survey_preview(LIST, self.dev["id"], profile=profile, values={}, **self.nb())

    def survey(self, greeting=b"", answers=(), profile="cisco_ios_switch"):
        self.consoles.append((greeting, list(answers)))
        p = self.survey_preview(profile)
        assert p["ok"], p["refusals"]
        return Z.survey_run(LIST, self.dev["id"], profile=profile, confirmed_hash=p["hash"],
                            actor=ACTOR, actor_verified=Z.VERIFIED, timings=FAST, values={},
                            **self.nb())

    def kick_preview(self, params=None):
        return Z.kickstart_preview(LIST, self.dev["id"], dict(params or PARAMS), values={},
                                   **self.nb())

    def kick_with_greeting(self, greeting, answers):
        """A kick-start on a console that prints *greeting* as it is reached."""
        return self.kick(answers, greeting=greeting)

    def kick(self, answers, *, confirmed=None, actor=ACTOR, verified=Z.VERIFIED,
             params=None, greeting=b""):
        p = self.kick_preview(params)
        self.consoles.append((greeting, list(answers)))
        return Z.kickstart_apply(LIST, self.dev["id"],
                                 p["hash"] if confirmed is None else confirmed, actor, verified,
                                 params=dict(params or PARAMS), timings=FAST, values={},
                                 **self.nb())

    def received(self, index=0) -> bytes:
        return self.server.finished(index).received


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, socket.AF_INET)
    yield w
    w.server.close()


@pytest.fixture
def world6(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, socket.AF_INET6)
    yield w
    w.server.close()


def _lines():
    from modules.nsot import console_survey as V
    return V.render_kickstart(P.load("cisco_ios_switch"), PARAMS)


def _recorded_as_sent(rec, sent: bytes, seen: str, attach):
    """A run that stopped records what it sent, how many bytes, what the console showed, and
    the state it was found in: the partial record is the evidence."""
    assert rec["sent"] == sent.decode() and rec["bytes_written"] == len(sent)
    assert seen in rec["transcript"] and rec["attach_state"] == attach
    assert Z.get_run(LIST, rec["id"])["transcript"] == rec["transcript"]


# ── The survey ─────────────────────────────────────────────────────────────────────────────

class TestSurveyPreview:
    def test_it_names_the_path_the_port_the_transport_the_profile_and_the_program(self, world):
        p = world.survey_preview()
        assert p["ok"], p["refusals"]
        assert p["device"] == "edge1" and p["port_id"] == world.sport["id"]
        assert p["path"]["server"]["name"] == "cons-1"
        assert p["path"]["server_port"]["name"] == "port 5"
        assert p["path"]["console_port"]["name"] == "con 0"
        assert p["transport"] == (f"console-server port {world.sport['id']} (127.0.0.1 port "
                                  f"{world.server.port})")
        prof = P.load("cisco_ios_switch")
        assert p["profile"] == {"name": prof.name, "version": prof.version,
                                "sha256": prof.sha256}
        assert p["program"]["wake"] == [["idle", "\r"]]
        assert p["program"]["reads"] == [["priv_exec", "terminal length 0\r"],
                                         ["priv_exec", "show version\r"],
                                         ["priv_exec", "dir nvram:\r"]]
        assert len(p["hash"]) == 64
        assert world.server.accepted == 0, "a preview contacts no console"

    def test_it_writes_nothing(self, world, tmp_path):
        before = sorted(os.listdir(tmp_path / "data"))
        world.survey_preview()
        assert sorted(os.listdir(tmp_path / "data")) == before
        assert not (tmp_path / "lists").exists()

    def test_the_hash_moves_with_the_port_record(self, world):
        first = world.survey_preview()["hash"]
        world.set_port(tcp_port=world.server.port + 1 if world.server.port < 65535 else 1)
        assert world.survey_preview()["hash"] != first

    def test_no_port_record_is_refused_naming_the_port(self, world):
        from modules.nsot import console_servers
        console_servers.remove_port(world.sport["id"], actor=ACTOR)
        p = world.survey_preview()
        assert not p["ok"] and p["hash"] == ""
        assert p["refused_by"]["port"].startswith(
            f"console-server port {world.sport['id']} (cons-1 port 5) has no record")

    def test_no_console_path_is_refused_saying_which_read_was_empty(self, world):
        world.fake.store["dcim/cables"] = []
        world.port["cable"] = None
        p = world.survey_preview()
        assert not p["ok"] and "has no cable" in p["refused_by"]["path"]

    def test_an_unknown_profile_is_refused(self, world):
        p = world.survey_preview(profile="no_such_profile")
        assert not p["ok"] and "no_such_profile" in p["refused_by"]["profile"]

    def test_a_profile_for_a_platform_with_no_session_lines_is_refused(self, world,
                                                                       monkeypatch):
        monkeypatch.setattr(Z, "SESSION_LINES", {"cisco_xe": {}})
        p = world.survey_preview()
        assert p["refused_by"]["profile"] == ("profile cisco_ios_switch's platform 'cisco_ios' "
                                              "has no session lines here (['cisco_xe'])")

    @pytest.mark.parametrize("case,key,words", [
        ("list", "list", "no network named 'elsewhere'"),
        ("id", "device", "a NetBox device id is a positive number, not 0"),
        ("gone", "device", "dcim/devices/999/ is gone"),
        ("nameless", "device", "has no name to hold it by"),
        ("netbox", "netbox", "NetBox is not reachable"),
        ("identity", "device", "edge1 in console-o6 is NetBox device 4242, not"),
        ("two", "path", "has 2 console paths (con 0 to cons-1 port 5, con 1 to cons-1 port 6)"),
        ("store", "port", "Mercury's console-server store could not be read"),
        ("bridge", "transport", "the console's container name was refused before connecting"),
    ])
    def test_each_refusal_names_what_it_compared(self, world, monkeypatch, case, key, words):
        dev_id, list_name, nb = world.dev["id"], LIST, world.nb()
        if case == "list":
            list_name = "elsewhere"
        elif case == "id":
            dev_id = 0
        elif case == "gone":
            dev_id = 999
        elif case == "nameless":
            dev_id = world.fake.seed("dcim/devices", {"name": "", "status": "planned"})["id"]
        elif case == "netbox":
            nb = {}
            monkeypatch.setattr("modules.netbox_client._nb_ready",
                                lambda: (False, "NetBox URL and API token are not configured",
                                         None, ""))
        elif case == "identity":
            from modules.config import list_data_path
            from modules.nsot import manifest
            repo = os.path.join(list_data_path(LIST), "config_repo")
            os.makedirs(os.path.join(repo, ".nsot"))
            manifest.upsert_device(repo, manifest.new_device_uid(), "edge1", netbox_id=4242)
        elif case == "two":
            port = world.fake.seed("dcim/console-ports", {"device": dev_id, "name": "con 1"})
            sport = world.fake.seed("dcim/console-server-ports", {"device": world.cs["id"],
                                                                  "name": "port 6"})
            world.fake.seed("dcim/cables", {
                "a_terminations": [{"object_type": "dcim.consoleport", "object_id": port["id"]}],
                "b_terminations": [{"object_type": "dcim.consoleserverport",
                                    "object_id": sport["id"]}], "status": "connected"})
        elif case == "store":
            from modules.nsot import console_servers
            with open(console_servers.path(), "w", encoding="utf-8") as fh:
                fh.write("{")
        elif case == "bridge":
            # A store file holding a name the wrapper refuses (`--`), as a hand-edited or
            # corrupted store would: the store's own writes refuse it since C1565, so it is
            # planted in the file; the transport must still refuse it before connecting.
            import json

            from modules.nsot import console_servers
            world.set_port(driver="command_bridge", tcp_port=None, ssh_port=22,
                           container="edge-a", credential_ref="console-bridge")
            with open(console_servers.path(), encoding="utf-8") as fh:
                doc = json.load(fh)
            for rec in doc["ports"].values():
                rec["container"] = "edge--a"
            with open(console_servers.path(), "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
        p = Z.survey_preview(list_name, dev_id, profile="cisco_ios_switch", values={}, **nb)
        assert not p["ok"] and p["hash"] == ""
        assert words in p["refused_by"][key], p["refused_by"]

    def test_a_command_bridge_port_is_described_by_its_container(self, world):
        world.set_port(driver="command_bridge", tcp_port=None, ssh_port=2222,
                       container="edge-a", credential_ref="console-bridge")
        p = world.survey_preview()
        assert p["ok"], p["refusals"]
        assert p["transport"] == (f"console-server port {world.sport['id']} ('edge-a' on "
                                  f"{world.server.host} port 2222)")

    def test_an_unknown_driver_is_refused_before_anything_is_built(self):
        from modules.nsot import console_transport as T
        with pytest.raises(T.ConsoleRefused, match="driver 'ssh_user_port' is not one of"):
            Z.build_transport({"driver": "ssh_user_port"}, 5)


class TestSurveyRun:
    @FAMILIES
    def test_a_blank_console_that_printed_its_prompt_first_is_blank(self, tmp_path,
                                                                   monkeypatch, family):
        w = World(tmp_path, monkeypatch, family)
        try:
            rec = w.survey(greeting=PNP, answers=blank_answers())
            assert (rec["outcome"], rec["blank"], rec["found_signed_in"]) == (
                "surveyed", True, False), rec
            assert rec["attach_state"] == P.PRESS_RETURN
            assert rec["mac"] is None and "the MAC is unknown" in rec["mac_reason"]
            assert w.received() == SURVEY_SENDS
            assert rec["bytes_written"] == len(SURVEY_SENDS)
            assert rec["startup_config_bytes"] == 0
        finally:
            w.server.close()

    def test_a_console_found_signed_in_is_not_blank_and_nothing_more_is_sent(self, world):
        rec = world.survey(answers=[b"\r\nSwitch#"])
        assert (rec["outcome"], rec["blank"], rec["found_signed_in"]) == (
            "stopped", False, True), rec
        assert rec["reasons"][0].startswith("not factory-blank as found: the console was "
                                            "signed in at priv_exec")
        assert world.received() == b"\r"

    def test_a_user_prompt_at_the_wake_is_recorded_and_nvram_decides(self, world):
        """D3: a blank switch whose banner printed before Mercury attached answers the wake with
        `Switch>` (the real wake answer). Recorded, then enabled and surveyed; blank."""
        wake, *rest = blank_answers()
        rec = world.survey(answers=[wake] + rest[:])
        assert (rec["outcome"], rec["blank"], rec["found_signed_in"], rec["attach_state"]) == (
            "surveyed", True, False, P.USER_EXEC), rec
        assert rec["reasons"][0].startswith("the console was at user_exec at attach: recorded")
        assert world.received() == SURVEY_SENDS

    def test_a_console_not_left_at_the_user_prompt_is_not_a_finished_survey(self, world):
        """The reads stand, but a survey whose release did not end is no ground for a
        kick-start, and is a row."""
        answers = blank_answers()
        answers[-1] = b"disable\r\nPassword: "
        rec = world.survey(greeting=PNP, answers=answers)
        assert (rec["outcome"], rec["blank"]) == ("aborted", True), rec
        assert rec["reason"].startswith("release: ")
        assert Z.problem(Z.read_index()["devices"][f"{LIST}|{world.dev['id']}"]) == "failed"
        p = world.kick_preview()
        assert "ended aborted" in p["refused_by"]["survey"]

    def test_a_login_prompt_at_the_wake_is_not_blank(self, world):
        rec = world.survey(answers=[b"\r\nUsername: "])
        assert (rec["outcome"], rec["blank"]) == ("stopped", False)
        assert world.received() == b"\r"

    def test_the_setup_dialog_is_declined_and_then_surveyed(self, world):
        """A configless device at the setup dialog: declined, RETURN, then the reads."""
        dialog = (b"\r\n         --- System Configuration Dialog ---\r\n\r\nWould you like to "
                  b"enter the initial configuration dialog? [yes/no]: ")
        answers = [b"no\r\n\r\n\r\nPress RETURN to get started!\r\n\r\n"] + blank_answers()
        rec = world.survey(greeting=dialog, answers=answers)
        assert (rec["outcome"], rec["blank"], rec["attach_state"]) == (
            "surveyed", True, P.SETUP_DIALOG), rec
        assert world.received() == b"no\r" + SURVEY_SENDS

    def test_a_password_at_enable_stops_the_survey_unknown(self, world):
        wake, _enable, _nvram = _real()
        rec = world.survey(greeting=PNP, answers=[wake, b"enable\r\nPassword: "])
        assert (rec["outcome"], rec["blank"]) == ("aborted", None), rec
        assert rec["reasons"][0].startswith("the survey stopped in its prelude phase (expected")
        assert world.received() == b"\renable\r"
        assert Z.problem(Z.read_index()["devices"][f"{LIST}|{world.dev['id']}"]) == "failed"

    def test_the_mac_is_read_from_its_line(self, world):
        answers = blank_answers()
        answers[3] = (b"show version\r\nCisco IOS Software\r\nBase ethernet MAC Address"
                      b"       : 52:54:00:AB:CD:EF\r\nSwitch#")
        rec = world.survey(greeting=PNP, answers=answers)
        assert rec["mac"] == "52:54:00:ab:cd:ef"

    def test_it_is_recorded_and_indexed(self, world):
        rec = world.survey(greeting=PNP, answers=blank_answers())
        assert Z.get_run(LIST, rec["id"])["outcome"] == "surveyed"
        survey, why = Z.latest_survey(LIST, world.dev["id"])
        assert why == "" and survey["id"] == rec["id"] and survey["blank"] is True
        assert ">>> sent 'dir nvram:\\r'" in rec["transcript"]

    def test_a_console_that_cannot_be_opened_is_recorded_unreachable(self, world):
        p = world.survey_preview()
        world.server.close()
        rec = Z.survey_run(LIST, world.dev["id"], profile="cisco_ios_switch",
                           confirmed_hash=p["hash"], actor=ACTOR, timings=FAST, values={},
                           **world.nb())
        assert (rec["outcome"], rec["blank"]) == ("unreachable", None)
        assert rec["reason"].startswith("the console could not be opened: ")

    def test_no_actor_and_a_refused_preview_send_nothing(self, world):
        with pytest.raises(Z.Refused, match="no actor was given"):
            Z.survey_run(LIST, world.dev["id"], profile="cisco_ios_switch",
                         confirmed_hash="x", actor=" ", timings=FAST, values={}, **world.nb())
        with pytest.raises(Z.Refused, match="no_such_profile"):
            Z.survey_run(LIST, world.dev["id"], profile="no_such_profile",
                         confirmed_hash="x", actor=ACTOR, timings=FAST, values={}, **world.nb())
        assert world.server.accepted == 0

    def test_a_device_held_by_another_operation_is_refused_by_name(self, world):
        from modules.nsot import device_ops
        p = world.survey_preview()
        holding, done = threading.Event(), threading.Event()

        def other():
            with device_ops.hold(LIST, "edge1", "capture", "other@example.invalid"):
                holding.set()
                done.wait(10)

        t = threading.Thread(target=other)
        t.start()
        try:
            assert holding.wait(10)
            with pytest.raises(Z.Refused, match="edge1 is being captured by other@example"):
                Z.survey_run(LIST, world.dev["id"], profile="cisco_ios_switch",
                             confirmed_hash=p["hash"], actor=ACTOR, timings=FAST, values={},
                             **world.nb())
        finally:
            done.set()
            t.join(10)
        assert world.server.accepted == 0

    def test_a_moved_hash_is_refused_naming_both_and_nothing_is_sent(self, world):
        p = world.survey_preview()
        with pytest.raises(Z.Refused) as exc:
            Z.survey_run(LIST, world.dev["id"], profile="cisco_ios_switch",
                         confirmed_hash="0" * 64, actor=ACTOR, timings=FAST, values={},
                         **world.nb())
        assert f"({'0' * 64} -> {p['hash']})" in str(exc.value)
        assert world.server.accepted == 0


# ── The kick-start ─────────────────────────────────────────────────────────────────────────

class TestKickstartRefusals:
    def test_without_a_survey_it_is_refused(self, world):
        p = world.kick_preview()
        assert not p["ok"] and p["hash"] == ""
        assert p["refused_by"]["survey"] == (f"NetBox device {world.dev['id']} has no console "
                                             f"survey in {LIST}: survey its console first")
        with pytest.raises(Z.Refused, match="survey its console first. Nothing was sent."):
            world.kick([])
        assert world.server.accepted == 0

    def test_a_survey_that_did_not_find_it_blank_refuses_naming_which(self, world):
        rec = world.survey(answers=[b"\r\nSwitch#"])
        p = world.kick_preview()
        assert not p["ok"]
        assert p["refused_by"]["survey"].startswith(
            f"the survey of {rec['at']} by {ACTOR} did not find it factory-blank and end "
            "(blank: False, ended stopped")

    def test_an_actor_who_is_not_a_verified_person_is_refused(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        for actor, verified, said in ((ACTOR, "none", f"{ACTOR!r}, verified 'none'"),
                                      (ACTOR, "", f"{ACTOR!r}, verified 'none'"),
                                      ("service:abc", Z.VERIFIED, "'service:abc', verified "
                                                                  "'access'"),
                                      ("unverified", Z.VERIFIED, "'unverified', verified "
                                                                 "'access'"),
                                      ("", Z.VERIFIED, "'none', verified 'access'")):
            with pytest.raises(Z.Refused) as exc:
                world.kick([], actor=actor, verified=verified)
            assert str(exc.value) == (f"a kick-start is confirmed by a verified person: the "
                                      f"actor is {said}, and it needs a person verified "
                                      "'access'. Nothing was sent.")
        assert world.server.accepted == 1, "only the survey reached the console"

    def test_a_moved_hash_is_refused_naming_both(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        p = world.kick_preview()
        with pytest.raises(Z.Refused) as exc:
            world.kick([], confirmed="f" * 64)
        assert str(exc.value) == (f"the kick-start changed since the preview you confirmed "
                                  f"({'f' * 64} -> {p['hash']}): its lines, profile, console "
                                  "path, port or survey moved. Nothing was sent; preview again.")
        assert world.server.accepted == 1

    def test_every_refusal_of_the_preview_is_said_together(self, world):
        with pytest.raises(Z.Refused) as exc:
            world.kick([], params=dict(PARAMS, vlan=0))
        assert str(exc.value) == (f"NetBox device {world.dev['id']} has no console survey in "
                                  f"{LIST}: survey its console first. Nothing was sent.")
        world.survey(answers=[b"\r\nSwitch#"])
        with pytest.raises(Z.Refused) as exc:
            world.kick([], params=dict(PARAMS, vlan=0))
        said = str(exc.value)
        assert said.endswith(". Nothing was sent.") and "; parameter vlan 0 is not a valid " \
            "vlan" in said and said.count("; ") >= 1

    def test_the_netbox_it_reads_and_the_masking_are_the_callers(self, world):
        """The run reads NetBox through the session and base it is given (none: the base is
        the session's own), and masks its record with the values it is given."""
        seen = []

        class Recording:
            def get(self, url, *a, **k):
                seen.append(url)
                return world.fake.get(url, *a, **k)

        world.survey(greeting=PNP, answers=blank_answers())
        values = {"GigabitEthernet0/1": "a test value"}
        p = Z.kickstart_preview(LIST, world.dev["id"], dict(PARAMS), session=Recording(),
                                values=values)
        world.consoles.append((b"", kick_answers(_lines())))
        rec = Z.kickstart_apply(LIST, world.dev["id"], p["hash"], ACTOR, Z.VERIFIED,
                                params=dict(PARAMS), timings=FAST, values=values,
                                session=Recording())
        assert rec["outcome"] == "done", rec
        assert seen and all(u.startswith("/api/") for u in seen), seen
        assert "interface <redacted:a test value>" in rec["lines"]
        assert "GigabitEthernet0/1" not in rec["sent"] + rec["transcript"]
        for run in (lambda: Z.kickstart_preview(LIST, world.dev["id"], dict(PARAMS),
                                                session=Recording(), base=BASE, values={}),
                    lambda: Z.survey_preview(LIST, world.dev["id"], profile="cisco_ios_switch",
                                             session=Recording(), base=BASE, values={})):
            seen.clear()
            run()
            assert seen and all(u.startswith(BASE + "/api/") for u in seen), seen

    def test_a_device_held_by_another_operation_is_refused_by_name(self, world):
        from modules.nsot import device_ops
        world.survey(greeting=PNP, answers=blank_answers())
        holding, done = threading.Event(), threading.Event()

        def other():
            with device_ops.hold(LIST, "edge1", "deploy", "other@example.invalid"):
                holding.set()
                done.wait(10)

        t = threading.Thread(target=other)
        t.start()
        try:
            assert holding.wait(10)
            with pytest.raises(Z.Refused) as exc:
                world.kick(kick_answers(_lines()))
            assert "edge1 is being deployed to by other@example.invalid" in str(exc.value)
        finally:
            done.set()
            t.join(10)
        assert world.server.accepted == 1


class TestKickstartRun:
    @FAMILIES
    def test_it_sends_exactly_the_previewed_lines_and_records_them(self, tmp_path, monkeypatch,
                                                                    family):
        w = World(tmp_path, monkeypatch, family)
        try:
            survey = w.survey(greeting=PNP, answers=blank_answers())
            p = w.kick_preview()
            assert p["ok"], p["refusals"]
            lines = _lines()
            assert p["lines"] == list(lines)
            rec = w.kick(kick_answers(lines))
            assert (rec["outcome"], rec["verify"]["ok"]) == ("done", True), rec
            program = b"\renable\rdir nvram:\r" + b"".join(f"{l}\r".encode() for l in lines)
            assert w.received(1) == program
            assert rec["bytes_written"] == len(program)
            assert rec["hash"] == p["hash"] and rec["survey_id"] == survey["id"]
            assert rec["actor"] == ACTOR and rec["actor_verified"] == Z.VERIFIED
            assert rec["lines"] == list(lines)
            assert Z.get_run(LIST, rec["id"])["outcome"] == "done"
        finally:
            w.server.close()

    def test_a_password_prompt_mid_run_stops_with_nothing_more_sent(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        lines = _lines()
        rec = world.kick(kick_answers(lines, cut=2))
        assert rec["outcome"] == "aborted", rec
        assert "found login_password" in rec["reason"]
        program = b"\renable\rdir nvram:\r" + b"".join(f"{l}\r".encode() for l in lines[:3])
        assert world.received(1) == program
        assert "Password:" in rec["transcript"]
        assert Z.get_run(LIST, rec["id"])["outcome"] == "aborted"

    def test_a_saved_configuration_at_the_recheck_types_nothing(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        saved = (b"dir nvram:\r\nDirectory of nvram:/\r\n\r\n  254  -rw-        1203"
                 b"                    <no date>  startup-config\r\n\r\nSwitch#")
        rec = world.kick(kick_answers(_lines(), recheck=saved))
        why = ("startup-config is 1203 bytes in 'dir nvram:''s output: the device holds a saved "
               "configuration")
        assert rec["outcome"] == "not_blank"
        assert rec["recheck"] == {"blank": False, "size": 1203, "reason": why}
        assert rec["reason"] == (f"the recheck found it not factory-blank ({why}): nothing of "
                                 "the kick-start was typed")
        assert world.received(1) == b"\renable\rdir nvram:\r"
        _recorded_as_sent(rec, b"\renable\rdir nvram:\r", "1203", P.USER_EXEC)

    def test_a_blank_recheck_is_recorded(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        rec = world.kick(kick_answers(_lines()))
        assert rec["recheck"] == {"blank": True, "size": 0,
                                  "reason": "startup-config is 0 bytes in 'dir nvram:''s output"}

    def test_each_phase_is_noted_on_the_held_device(self, world, monkeypatch):
        """The hold's progress (what a refusal and the In progress chip name), in order."""
        from modules.nsot import device_ops
        noted, real = [], device_ops.note
        monkeypatch.setattr(device_ops, "note", lambda step, *a, **k: (
            noted.append(step), real(step, *a, **k)))
        world.survey(greeting=PNP, answers=blank_answers())
        # C1579: the verdict and the record are noted too, so THE stepper fills to the end.
        assert noted == ["opening the console", "waking the console", "survey: prelude",
                         "survey: mac", "survey: blank", "survey: release", "survey: verify",
                         "survey: record"]
        noted.clear()
        world.kick(kick_answers(_lines()))
        assert noted == ["opening the console", "waking the console", "kick-start: recheck",
                         "kick-start: typing", "kick-start: verify", "kick-start: record"]

    def test_the_final_record_is_written_before_the_hold_ends(self, world, monkeypatch):
        """C1579: the card reads a running run's steps from the hold and its result from the
        record; written after the release, a redraw between the two drew the first step
        running again on a run that had finished."""
        from modules.nsot import device_ops
        at_release, real = [], device_ops.release

        def release(list_name, hostname):
            at_release.append([r["outcome"] for r in Z.runs(LIST)["runs"]])
            return real(list_name, hostname)

        monkeypatch.setattr(device_ops, "release", release)
        world.survey(greeting=PNP, answers=blank_answers())
        world.kick(kick_answers(_lines()))
        assert at_release == [["surveyed"], ["done", "surveyed"]], at_release

    def test_a_run_that_stops_early_never_notes_its_record(self, world, monkeypatch):
        """C1579: the record is noted as begun only by a run that reached its verdict, so the
        steps a stopped run never ran are never drawn done (`device_actions.stepper`)."""
        from modules.nsot import device_ops
        noted, real = [], device_ops.note
        monkeypatch.setattr(device_ops, "note", lambda step, *a, **k: (
            noted.append(step), real(step, *a, **k)))
        rec = world.survey(answers=[b"\r\nSwitch#"])
        assert rec["outcome"] == "stopped"
        assert noted == ["opening the console", "waking the console"]

    def test_an_end_prompt_not_naming_the_hostname_is_unverified(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        answers = kick_answers(_lines())
        answers[-1] = b"end\r\nSwitch#"
        rec = world.kick(answers)
        assert (rec["outcome"], rec["verify"]["ok"]) == ("unverified", False)
        assert rec["reason"] == ("it ended at 'Switch#', which names 'Switch', not the "
                                 "hostname typed, 'edge1'")

    def test_a_config_prompt_at_the_wake_types_nothing(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        rec = world.kick([b"\r\nSwitch(config)#"])
        assert rec["outcome"] == "refused_state"
        assert rec["reason"].startswith("the console was found at config, which a kick-start "
                                        "does not type from")
        assert world.received(1) == b"\r"

    def test_a_privileged_prompt_at_the_wake_types_nothing(self, world):
        """D3: `#` is signed in. The survey left the console at `>`, so a `#` means someone
        signed in since: nothing of the kick-start is typed."""
        world.survey(greeting=PNP, answers=blank_answers())
        rec = world.kick([b"\r\nSwitch#"])
        assert rec["outcome"] == "refused_state"
        assert rec["reason"] == ("the console was found at priv_exec, which a kick-start does "
                                 "not type from (press_return, setup_dialog, user_exec): "
                                 "nothing more was sent")
        assert world.received(1) == b"\r"
        _recorded_as_sent(rec, b"\r", "Switch#", P.PRIV_EXEC)

    def test_a_console_that_printed_its_prompt_first_is_kickstarted_from_it(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        lines = _lines()
        wake, *rest = kick_answers(lines)
        rec = world.kick_with_greeting(PNP, [_real()[0]] + rest)
        assert rec["outcome"] == "done", rec
        assert world.received(1) == (b"\renable\rdir nvram:\r"
                                     + b"".join(f"{l}\r".encode() for l in lines))

    def test_a_console_that_cannot_be_opened_is_recorded_unreachable(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        p = world.kick_preview()
        world.server.close()
        rec = Z.kickstart_apply(LIST, world.dev["id"], p["hash"], ACTOR, Z.VERIFIED,
                                params=dict(PARAMS), timings=FAST, values={}, **world.nb())
        assert rec["outcome"] == "unreachable" and "could not be opened" in rec["reason"]
        assert Z.problem(Z.read_index()["devices"][f"{LIST}|{world.dev['id']}"]) == "failed"

    def test_a_survey_with_another_profile_hash_refuses(self, world, monkeypatch):
        world.survey(greeting=PNP, answers=blank_answers())
        real = P.load("cisco_ios_switch")
        monkeypatch.setattr(P, "load", lambda name, *a: real.__class__(
            **{**real.__dict__, "sha256": "e" * 64}))
        p = world.kick_preview()
        assert not p["ok"] and "survey again" in p["refused_by"]["survey"]
        assert f"that profile is {'e' * 12} now" in p["refused_by"]["survey"]

    def test_a_survey_over_another_port_refuses(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        world.fake.store["dcim/cables"][0]["b_terminations"][0]["object_id"] = (
            world.fake.seed("dcim/console-server-ports", {"device": world.cs["id"],
                                                          "name": "port 9"})["id"])
        p = world.kick_preview()
        assert not p["ok"] and "survey again" in p["refused_by"]["survey"]
        assert f"was over console-server port {world.sport['id']}" in p["refused_by"]["survey"]

    def test_a_login_prompt_at_the_wake_types_nothing(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        rec = world.kick([b"\r\nUsername: "])
        assert rec["outcome"] == "aborted" and "found login_user" in rec["reason"]
        assert world.received(1) == b"\r"
        _recorded_as_sent(rec, b"\r", "Username:", P.LOGIN_USER)

    def test_a_recheck_that_does_not_end_types_nothing(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        rec = world.kick([b"\r\nSwitch>", _real()[1], b"dir nvram:\r\n --More-- "])
        assert rec["outcome"] == "aborted" and rec["reason"].startswith("recheck: ")
        assert world.received(1) == b"\renable\rdir nvram:\r"
        _recorded_as_sent(rec, b"\renable\rdir nvram:\r", "--More--", P.USER_EXEC)

    @pytest.mark.parametrize("prompt,ok,why", [
        ("edge1#", True, "it ended at 'edge1#', naming the hostname typed"),
        ("edge1>", False, "it ended at 'edge1>', not a privileged prompt"),
        ("", False, "it ended at '', not a privileged prompt"),
        ("edge2#", False, "it ended at 'edge2#', which names 'edge2', not the hostname typed, "
                          "'edge1'"),
    ])
    def test_the_end_prompt_is_judged(self, prompt, ok, why):
        assert Z.verify_kickstart(prompt, PARAMS, P.load("cisco_ios_switch")) == {
            "ok": ok, "why": why}

    def test_each_survey_refusal_is_said_exactly(self, world):
        """The survey a kick-start stands on, named by its time and who ran it, and each
        comparison it failed with both values."""
        from modules.nsot import reads
        prof = P.load("cisco_ios_switch")
        base = {"kind": Z.KIND_SURVEY, "list": LIST, "device_id": world.dev["id"],
                "device": "edge1", "at": "2026-10-22T10:00:00Z", "port_id": world.sport["id"],
                "profile": {"name": prof.name, "version": prof.version, "sha256": prof.sha256},
                "path": {"server_port": {"id": world.sport["id"]}}}

        def refused(**rec):
            Z.record(LIST, dict(base, id=reads.new_id(), **rec))
            p = world.kick_preview()
            return p["survey_words"], p["refused_by"].get("survey")

        words, why = refused(actor="", outcome="stopped", blank=False)
        assert words == "the survey of 2026-10-22T10:00:00Z by someone"
        assert why == ("the survey of 2026-10-22T10:00:00Z by someone did not find it "
                       "factory-blank and end (blank: False, ended stopped; no reason): a "
                       "kick-start types only on a device its survey found blank")
        _w, why = refused(actor=ACTOR, outcome="aborted", blank=None, reason="the far end")
        assert why.endswith("(blank: None, ended aborted; the far end): a kick-start types "
                            "only on a device its survey found blank")
        _w, why = refused(actor=ACTOR, outcome="surveyed", blank=False, reasons=["a", "b"])
        assert why.endswith("(blank: False, ended surveyed; a; b): a kick-start types only on "
                            "a device its survey found blank")
        _w, why = refused(actor=ACTOR, outcome="surveyed", blank=True,
                          profile=dict(base["profile"], sha256="1234567890abcdef"))
        assert why == (f"the survey of 2026-10-22T10:00:00Z by {ACTOR} used profile "
                       f"cisco_ios_switch 1234567890ab, and that profile is {prof.sha256[:12]} "
                       "now: survey again")
        _w, why = refused(actor=ACTOR, outcome="surveyed", blank=True,
                          path={"server_port": {"id": 999}})
        assert why == (f"the survey of 2026-10-22T10:00:00Z by {ACTOR} was over console-server "
                       f"port 999, and the device's console path is port {world.sport['id']} "
                       "now: survey again")
        words, why = refused(actor=ACTOR, outcome="surveyed", blank=True)
        assert why is None and words == f"the survey of 2026-10-22T10:00:00Z by {ACTOR}"

    def test_the_preview_draws_the_whole_program_by_state(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        p = world.kick_preview()
        lines = _lines()
        enable = ["user_exec", "enable\r"]
        assert p["program"] == {
            "wake": [["idle", "\r"]],
            "prelude": {"press_return": [["press_return", "\r"], enable],
                        "setup_dialog": [["setup_dialog", "no\r"], ["press_return", "\r"],
                                         enable],
                        "user_exec": [enable]},
            "recheck": [["priv_exec", "dir nvram:\r"]],
            "lines": [["priv_exec", lines[0] + "\r"]] + [["config", l + "\r"]
                                                          for l in lines[1:]],
            "ends": "priv_exec",
            "stops": "a privileged, config or login prompt at the wake (signed in since its "
                     "survey left it at the user prompt), or a saved startup configuration at "
                     "the recheck: nothing of the kick-start is typed"}

    def test_bad_parameters_are_refused_naming_them(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        p = world.kick_preview(dict(PARAMS, vlan=5000))
        assert not p["ok"] and "over VLAN 4094" in p["refused_by"]["params"]


# ── The records ────────────────────────────────────────────────────────────────────────────

class TestRecords:
    def test_runs_are_read_per_device_and_an_unreadable_one_is_named(self, world):
        mine = world.survey(answers=[b"\r\nSwitch#"])
        folder = os.path.join(Z._folder(LIST), "20261022T000000000000Z-" + "0" * 32 + ".json")
        with open(folder, "w", encoding="utf-8") as fh:
            fh.write("{")
        Z.record(LIST, dict(mine, id="20261022T000000000001Z-" + "1" * 32, device_id=77,
                            device="edge2"))
        got = Z.runs(LIST, device_id=world.dev["id"])
        assert [r["id"] for r in got["runs"]] == [mine["id"]]
        assert got["unreadable"] == ["20261022T000000000000Z-" + "0" * 32 + ".json"]
        assert len(Z.runs(LIST, limit=1)["runs"]) == 1
        assert Z.get_run(LIST, "20261022T000000000002Z-" + "2" * 32) is None
        with pytest.raises(ValueError, match="not a run id"):
            Z.get_run(LIST, "../x")

    def test_an_unreadable_index_is_said_on_the_record_and_refuses_a_kickstart(self, world):
        with open(Z.index_path(), "w", encoding="utf-8") as fh:
            fh.write("[]")
        rec = world.survey(answers=[b"\r\nSwitch#"])
        assert "is not a console ZTP index" in rec["index_error"]
        assert Z.read_index()["state"] == "unreadable"
        p = world.kick_preview()
        assert p["refused_by"]["survey"].startswith("the console ZTP index could not be read")

    def test_a_run_announces_its_end_and_a_failed_announcement_fails_nothing(self, monkeypatch):
        from modules import invalidation
        heard = []
        monkeypatch.setattr(invalidation, "announce",
                            lambda keys, by, ok=True: heard.append((tuple(keys), by)))
        Z._announce()
        assert heard == [(Z.ANNOUNCE_KEYS, Z.ANNOUNCER)]
        for exc in (OSError("no socket"), RuntimeError("no emitter: a script's process")):
            def fail(*_a, exc=exc, **_k):
                raise exc
            monkeypatch.setattr(invalidation, "announce", fail)
            Z._announce()

    def test_a_run_past_its_bound_between_phases_sends_nothing_more(self, world):
        """The whole run's budget: a phase begun after it passed ends `bound` at once."""
        rec = world.survey(greeting=PNP, answers=blank_answers())
        assert rec["outcome"] == "surveyed"
        world.consoles.append((b"", [b"\r\nSwitch#"]))
        p = world.survey_preview()
        ticks = iter([0.0] + [10 ** 6] * 10 ** 4)
        rec = Z.survey_run(LIST, world.dev["id"], profile="cisco_ios_switch",
                           confirmed_hash=p["hash"], actor=ACTOR, timings=FAST, values={},
                           clock=lambda: next(ticks), **world.nb())
        assert rec["outcome"] == "bound" and world.received(1) == b""


# ── Needs attention ────────────────────────────────────────────────────────────────────────

class TestNeedsAttention:
    def _rows(self):
        from modules import attention
        return attention.console_ztp_source()["rows"]

    def test_a_not_blank_survey_is_a_row_naming_what_why_and_how_it_clears(self, world):
        rec = world.survey(answers=[b"\r\nSwitch#"])
        (row,) = self._rows()
        assert (row["source"], row["kind"], row["level"]) == ("console_ztp", "not_blank",
                                                              "warning")
        assert row["what"] == ("edge1's console survey found it not factory-blank: no "
                               "kick-start types on it")
        assert "signed in at priv_exec" in row["cause"] and rec["at"] in row["cause"]
        assert row["action"]["label"].startswith("Return edge1 to its factory state")
        assert row["clears"]["ways"] == ["resolves", "acknowledge"]
        assert row["event"] == rec["id"] and row["acknowledge"] is True
        assert row["devices"] == ["edge1"]

    def test_an_aborted_kickstart_is_a_danger_row_and_a_good_run_clears_it(self, world):
        world.survey(greeting=PNP, answers=blank_answers())
        assert self._rows() == []
        rec = world.kick(kick_answers(_lines(), cut=1))
        (row,) = self._rows()
        assert (row["kind"], row["level"], row["event"]) == ("failed", "danger", rec["id"])
        assert row["what"] == "edge1's console kick-start stopped before its end (aborted)"
        assert "found login_password" in row["cause"]
        assert row["action"]["label"] == (f"Read the run's transcript, check console-server "
                                          f"port {world.sport['id']} and edge1, then survey "
                                          "its console again")
        world.survey(greeting=PNP, answers=blank_answers())
        assert self._rows() == []

    def test_it_is_acknowledged_for_that_run_only(self, world, monkeypatch):
        """The acknowledgement record is the installation's (this test's data folder)."""
        from modules import attention
        monkeypatch.setattr("modules.nsot.retire.name_cuts_everywhere", lambda: {})
        rec = world.survey(answers=[b"\r\nSwitch#"])
        (row,) = self._rows()
        got = attention.acknowledge(row["id"], rec["id"], "left signed in on purpose, known",
                                    by=ACTOR, verified=Z.VERIFIED)
        assert got["ok"], got
        kept, gone, _problem = attention._without_acknowledged(self._rows())
        assert kept == [] and [g["id"] for g in gone] == [row["id"]]
        assert attention.acknowledge(row["id"], "other", "a later run is its own event",
                                     by=ACTOR, verified=Z.VERIFIED)["ok"] is False
        later = world.survey(answers=[b"\r\nSwitch#"])
        kept, _gone, _problem = attention._without_acknowledged(self._rows())
        assert [r["event"] for r in kept] == [later["id"]]

    def test_an_unreadable_index_is_a_row_of_its_own(self, world):
        from modules import attention
        with open(Z.index_path(), "w", encoding="utf-8") as fh:
            fh.write("{")
        got = attention.console_ztp_source()
        assert got["state"] == "unreadable"
        assert got["rows"][0]["kind"] == "unreadable"

    @pytest.mark.parametrize("latest,kind", [
        ({"kind": "survey", "outcome": "surveyed", "blank": True}, None),
        ({"kind": "survey", "outcome": "surveyed", "blank": False}, "not_blank"),
        ({"kind": "survey", "outcome": "stopped", "blank": False}, "not_blank"),
        ({"kind": "survey", "outcome": "surveyed", "blank": None}, "failed"),
        ({"kind": "survey", "blank": None}, "failed"),
        ({"kind": "survey", "outcome": "aborted", "blank": True}, "failed"),
        ({"kind": "survey", "outcome": "unreachable", "blank": None}, "failed"),
        ({"kind": "kickstart", "outcome": "done"}, None),
        ({"kind": "kickstart", "outcome": "not_blank"}, "not_blank"),
        ({"kind": "kickstart", "outcome": "aborted"}, "failed"),
        ({"kind": "kickstart", "outcome": "unverified"}, "failed"),
        ({"kind": "kickstart", "outcome": "unreachable"}, "failed"),
    ])
    def test_what_a_latest_run_leaves(self, latest, kind):
        assert Z.problem({"latest": latest}) == kind


# ── What each step hands on (the mutation run of 2026-10-22, #16) ──────────────────────────
#
# The run found these unchecked: what reaches the transport from the port's record, what the
# device hold and the port lock name, what each way a survey ends records, what the preview
# reads and shows, and the masking of a previewed program. Each test names the behaviour.

KEY_REF = "console-lab"
KEY_USER = "mercury"


@pytest.fixture(scope="module")
def host_key():
    """The console server's (or jump host's) RSA host key, generated for this run."""
    import paramiko
    return paramiko.RSAKey.generate(2048)


def _client_key(monkeypatch, tmp_path) -> dict:
    """The key Mercury holds for the console server or the jump host, stored under KEY_REF in
    this test's credential store (as test_console_transport.py stores it)."""
    from modules.nsot import console_keys
    monkeypatch.setattr("modules.credentials._FILE",
                        str(tmp_path / "data" / "credential_profiles.json"))
    return console_keys.generate(KEY_REF, username=KEY_USER,
                                 wrapper_path="/usr/local/bin/bridge",
                                 allowlist_path="/etc/nmas/allow")


class _Reading:
    """A NetBox session over the fake that records each URL it is asked for, and answers
    HTTP 500 for any URL holding *failing* (NetBox up, that read failing)."""

    def __init__(self, fake, failing: str = ""):
        self.fake, self.failing, self.seen = fake, failing, []

    def get(self, url, *a, **k):
        from tests.fake_netbox import FakeResponse
        self.seen.append(str(url))
        if self.failing and self.failing in str(url):
            return FakeResponse({"detail": "server error"}, status_code=500)
        return self.fake.get(url, *a, **k)


class TestTheRecordReachesTheTransport:
    """Every field of the port's record reaches what is opened: the jump host, its SSH port and
    the key under the record's reference (raw TCP), the console server's SSH port, key and
    container (the bridge), and whose run the session is (the host-key record names it)."""

    @FAMILIES
    def test_a_survey_through_a_jump_host_reaches_the_console_through_it(
            self, tmp_path, monkeypatch, family, host_key):
        from modules import host_keys as HK
        from tests.console_fakes import SshServer
        w = World(tmp_path, monkeypatch, family)
        key = _client_key(monkeypatch, tmp_path)
        jump = SshServer(host_key, user=KEY_USER, client_public=key["public_key"], family=family)
        try:
            w.set_port(jump_host=jump.host, ssh_port=jump.port, credential_ref=KEY_REF)
            assert w.survey_preview()["transport"] == (
                f"console-server port {w.sport['id']} ({w.server.host} port {w.server.port} "
                f"via {jump.host} port {jump.port})")
            rec = w.survey(greeting=PNP, answers=blank_answers())
            assert rec["outcome"] == "surveyed", rec
            assert jump.destinations == [(w.server.host, w.server.port)]
            assert jump.auth == [(KEY_USER, "ssh-ed25519", key["public_key"].split()[1])]
            assert w.received() == SURVEY_SENDS
            assert HK.held(jump.host)["kept_by"] == (
                f"{ACTOR} (console survey; {ACTOR}'s console run on edge1)")
        finally:
            jump.close()
            w.server.close()

    def test_a_survey_over_a_command_bridge_runs_its_container_with_the_records_key(
            self, world, tmp_path, monkeypatch, host_key):
        from modules import host_keys as HK
        from tests.console_fakes import SshServer
        key = _client_key(monkeypatch, tmp_path)
        bridge = SshServer(host_key, user=KEY_USER, client_public=key["public_key"],
                           allow=("edge-a",), make=world._next)
        try:
            world.set_port(driver="command_bridge", host=bridge.host, tcp_port=None,
                           ssh_port=bridge.port, container="edge-a", credential_ref=KEY_REF)
            rec = world.survey(greeting=PNP, answers=blank_answers())
            assert rec["outcome"] == "surveyed", rec
            assert bridge.commands == [b"edge-a"]
            assert bridge.auth == [(KEY_USER, "ssh-ed25519", key["public_key"].split()[1])]
            assert bridge.finished().received == SURVEY_SENDS
            assert HK.held(bridge.host)["kept_by"] == (
                f"{ACTOR} (console survey; {ACTOR}'s console run on edge1)")
        finally:
            bridge.close()

    def test_a_transport_built_for_no_one_holds_its_port_as_an_unnamed_caller(self, world):
        """A preview's transport is built naming no one; opened, it holds the port in the
        transport's own words for that, which a second session's refusal repeats."""
        from modules.nsot import console_transport as T
        record = {"driver": "raw_tcp", "host": world.server.host,
                  "tcp_port": world.server.port}
        world.consoles.append((b"", []))
        first = Z.build_transport(record, world.sport["id"]).open()
        try:
            with pytest.raises(T.PortBusy) as exc:
                Z.build_transport(record, world.sport["id"], owner="a second run").open()
            assert str(exc.value) == (
                f"console-server port {world.sport['id']} is held by an unnamed caller (pid "
                f"{os.getpid()}), so a second run was refused (one session per console port; "
                "never queued)")
        finally:
            first.close()


class TestWhatASurveyRecords:
    """Each way a survey ends records its outcome, why, what was sent and what the console
    showed, and the hold and the port lock name the operation and whose it is."""

    def test_a_finished_survey_has_no_reason_and_only_its_verdicts_reasons(self, world):
        rec = world.survey(greeting=PNP, answers=blank_answers())
        assert (rec["outcome"], rec["reason"]) == ("surveyed", "")
        assert rec["reasons"] == ["startup-config is 0 bytes in 'dir nvram:''s output"]

    def test_a_release_that_does_not_end_says_so_in_its_reasons(self, world):
        answers = blank_answers()
        answers[-1] = b"disable\r\nPassword: "
        rec = world.survey(greeting=PNP, answers=answers)
        assert rec["outcome"] == "aborted" and rec["reason"].startswith("release: ")
        why = rec["reason"][len("release: "):]
        assert rec["reasons"] == [
            "startup-config is 0 bytes in 'dir nvram:''s output",
            f"the console was not left at the user prompt ({why}): a kick-start's wake will "
            "find it signed in and refuse until it is"]

    def test_a_console_found_signed_in_records_what_was_sent_and_why_it_stopped(self, world):
        rec = world.survey(answers=[b"\r\nSwitch#"])
        assert rec["outcome"] == "stopped"
        assert rec["reason"] == "the console was found at priv_exec: nothing more was sent"
        assert "mac" in rec and rec["mac"] is None, "unknown is a field, never an absence"
        _recorded_as_sent(rec, b"\r", "Switch#", P.PRIV_EXEC)

    def test_a_wake_that_ends_another_way_records_the_runs_own_reason(self, world):
        """A console that answers the wake with nothing was found in no state: the run's own
        outcome and words, never "found at" (nothing was found), and blank unknown."""
        rec = world.survey(answers=[])
        assert (rec["outcome"], rec["blank"], rec["attach_state"]) == ("aborted", None, None)
        assert rec["reason"] == ("expected one of setup_dialog, press_return, user_exec, "
                                 "priv_exec, config (the plan's end) within 3 s, found idle")
        assert world.received() == b"\r"

    def test_a_survey_stopped_in_a_phase_records_why_what_it_sent_and_no_mac(self, world):
        wake, _enable, _nvram = _real()
        rec = world.survey(greeting=PNP, answers=[wake, b"enable\r\nPassword: "])
        assert rec["outcome"] == "aborted" and rec["blank"] is None
        assert rec["found_signed_in"] is False
        assert rec["reason"] == ("expected priv_exec (step 3 of 3), found login_password: "
                                 "'Password:'")
        assert rec["reasons"] == [f"the survey stopped in its prelude phase ({rec['reason']}), "
                                  "so blank is unknown"]
        assert "mac" in rec and rec["mac"] is None, "unknown is a field, never an absence"
        _recorded_as_sent(rec, b"\renable\r", "Password:", P.PRESS_RETURN)

    def test_the_hold_and_the_port_lock_name_the_survey_and_whose_it_is(self, world,
                                                                         monkeypatch):
        """What another operation's refusal and the In progress chip name (the hold), and what
        a second console session's refusal names (the port's lock record), while it runs."""
        from modules.nsot import console_transport as T
        from modules.nsot import device_ops
        seen, real = {}, device_ops.note

        def note(step, *a, **k):
            if step == "waking the console":
                seen["hold"] = device_ops.holder(LIST, "edge1")
                with open(T.PortLock(world.sport["id"], "probe").path(),
                          encoding="utf-8") as fh:
                    seen["port"] = fh.read()
            return real(step, *a, **k)

        monkeypatch.setattr(device_ops, "note", note)
        world.survey(greeting=PNP, answers=blank_answers())
        hold = seen["hold"]
        assert (hold["operation"], hold["actor"], hold["detail"]) == (
            Z.OP_SURVEY, ACTOR, f"console-server port {world.sport['id']}")
        assert seen["port"] == f"{ACTOR}'s console run on edge1 (pid {os.getpid()})"

    def test_the_run_id_and_how_the_actor_was_verified_are_the_callers(self, world):
        from modules.nsot import reads
        run_id = reads.new_id()
        p = world.survey_preview()

        def run(**over):
            world.consoles.append((b"", [b"\r\nSwitch#"]))
            return Z.survey_run(LIST, world.dev["id"], profile="cisco_ios_switch",
                                confirmed_hash=p["hash"], actor=ACTOR, timings=FAST,
                                values={}, **world.nb(), **over)

        rec = run(actor_verified=Z.VERIFIED, run_id=run_id)
        assert (rec["id"], rec["actor_verified"]) == (run_id, Z.VERIFIED)
        assert Z.get_run(LIST, run_id)["actor_verified"] == Z.VERIFIED
        rec = run()
        assert rec["actor_verified"] == "" and rec["id"] != run_id

    @pytest.mark.parametrize("actor", ["", None, " \t"])
    def test_no_actor_is_refused_with_nothing_sent(self, world, actor):
        with pytest.raises(Z.Refused) as exc:
            Z.survey_run(LIST, world.dev["id"], profile="cisco_ios_switch", confirmed_hash="x",
                         actor=actor, timings=FAST, values={}, **world.nb())
        assert str(exc.value) == ("a survey names who ran it, and no actor was given. Nothing "
                                  "was sent.")
        assert world.server.accepted == 0

    def test_the_netbox_a_survey_reads_is_the_callers(self, world):
        """Through the session and base it is given (no base: the session's own)."""
        for base, prefix in (("", "/api/"), (BASE, BASE + "/api/")):
            nb = _Reading(world.fake)
            p = Z.survey_preview(LIST, world.dev["id"], profile="cisco_ios_switch",
                                 session=nb, base=base, values={})
            world.consoles.append((b"", [b"\r\nSwitch#"]))
            nb.seen.clear()
            kw = {"base": base} if base else {}
            rec = Z.survey_run(LIST, world.dev["id"], profile="cisco_ios_switch",
                               confirmed_hash=p["hash"], actor=ACTOR, timings=FAST, values={},
                               session=nb, **kw)
            assert rec["outcome"] == "stopped", rec
            assert nb.seen and all(u.startswith(prefix) for u in nb.seen), nb.seen

    def test_a_console_that_cannot_be_opened_names_what_refused_it(self, world):
        p = world.survey_preview()
        world.server.close()
        rec = Z.survey_run(LIST, world.dev["id"], profile="cisco_ios_switch",
                           confirmed_hash=p["hash"], actor=ACTOR, timings=FAST, values={},
                           **world.nb())
        assert rec["reason"].startswith("the console could not be opened: "
                                        "ConnectionRefusedError: "), rec["reason"]

    def test_the_values_given_mask_what_the_console_printed(self, world):
        """A value the caller holds as a secret, printed by the console, is masked in the
        transcript the record keeps (the values reach the session, not the store's)."""
        answers = blank_answers()
        answers[3] = b"show version\r\nProcessor board ID 9SECRET0VALUE1\r\nSwitch#"
        world.consoles.append((PNP, answers))
        values = {"9SECRET0VALUE1": "a test value"}
        p = Z.survey_preview(LIST, world.dev["id"], profile="cisco_ios_switch", values=values,
                             **world.nb())
        rec = Z.survey_run(LIST, world.dev["id"], profile="cisco_ios_switch",
                           confirmed_hash=p["hash"], actor=ACTOR, timings=FAST, values=values,
                           **world.nb())
        assert rec["outcome"] == "surveyed", rec
        assert "Processor board ID <redacted:a test value>" in rec["transcript"]
        assert "9SECRET0VALUE1" not in json.dumps(Z.get_run(LIST, rec["id"]))


class TestWhatThePreviewReads:
    """What the preview reads from NetBox and the store, shows, and hashes."""

    def test_the_port_is_shown_and_hashed_as_how_it_is_reached_not_who_saved_it(self, world):
        from modules.nsot import console_servers
        p = world.survey_preview()
        assert p["port"] == {"driver": "raw_tcp", "host": world.server.host,
                             "tcp_port": world.server.port}
        got = console_servers.set_port(world.sport["id"], dict(p["port"]),
                                       actor="other@example.invalid")
        assert got["ok"], got
        assert console_servers.get_port(world.sport["id"])["record"]["by"] == \
            "other@example.invalid"
        assert world.survey_preview()["hash"] == p["hash"], "saved again, reached the same"

    def test_a_refused_preview_names_no_device_it_did_not_read(self, world):
        p = Z.survey_preview(LIST, 0, profile="cisco_ios_switch", values={}, **world.nb())
        assert p["refused_by"] == {"device": "a NetBox device id is a positive number, not 0"}
        assert p["device"] == ""

    def test_a_device_netbox_did_not_give_is_said_with_netboxs_answer(self, world):
        gone = Z.survey_preview(LIST, 999, profile="cisco_ios_switch", values={},
                                **world.nb())
        assert gone["refused_by"]["device"] == "dcim/devices/999/ is gone"
        nb = _Reading(world.fake, failing="/dcim/devices/")
        p = Z.survey_preview(LIST, world.dev["id"], profile="cisco_ios_switch", values={},
                             session=nb, base=BASE)
        assert p["refused_by"]["device"] == (f"dcim/devices/{world.dev['id']}/ is unreadable: "
                                             "NetBox answered HTTP 500")

    def test_a_console_path_netbox_could_not_read_names_that_read(self, world):
        nb = _Reading(world.fake, failing="/dcim/console-ports/")
        p = Z.survey_preview(LIST, world.dev["id"], profile="cisco_ios_switch", values={},
                             session=nb, base=BASE)
        assert p["refused_by"]["path"] == (f"dcim/console-ports/?device_id={world.dev['id']} "
                                           "answered HTTP 500")

    def _manifest(self, list_name, netbox_id):
        from modules.config import list_data_path
        from modules.nsot import manifest
        repo = os.path.join(list_data_path(list_name), "config_repo")
        os.makedirs(os.path.join(repo, ".nsot"), exist_ok=True)
        manifest.upsert_device(repo, manifest.new_device_uid(), "edge1", netbox_id=netbox_id)

    @pytest.mark.parametrize("held", ["this", ""])
    def test_the_name_held_by_this_device_or_by_none_yet_is_not_refused(self, world, held):
        self._manifest(LIST, world.dev["id"] if held == "this" else "")
        p = world.survey_preview()
        assert p["ok"] and p["refused_by"] == {}, p["refused_by"]

    def test_another_device_holding_the_name_is_refused_naming_both(self, world):
        self._manifest(LIST, 4242)
        p = world.survey_preview()
        assert p["refused_by"] == {"device": (
            f"edge1 in {LIST} is NetBox device 4242, not {world.dev['id']}: another device "
            "holds this name in the network")}

    def test_a_network_that_does_not_exist_is_refused_alone(self, world):
        """Its folder, left behind, is never read as the network's: one refusal, the network."""
        self._manifest("elsewhere", 4242)
        p = Z.survey_preview("elsewhere", world.dev["id"], profile="cisco_ios_switch",
                             values={}, **world.nb())
        assert p["refused_by"] == {"list": "no network named 'elsewhere'"}

    def test_a_kickstart_on_a_profile_with_no_session_lines_is_refused_not_broken(
            self, world, monkeypatch):
        """The survey's profile is refused for its platform: no profile, so no lines, no
        program and no hash; a refusal naming it, never an error."""
        world.survey(greeting=PNP, answers=blank_answers())
        monkeypatch.setattr(Z, "SESSION_LINES", {"cisco_xe": {}})
        p = world.kick_preview()
        assert not p["ok"] and p["hash"] == "" and p["profile"] is None
        assert p["refused_by"]["profile"] == ("profile cisco_ios_switch's platform 'cisco_ios' "
                                              "has no session lines here (['cisco_xe'])")
        assert (p["lines"], p["program"]) == ([], None)

    def test_the_preview_draws_the_whole_survey_program_by_state(self, world):
        enable = ["user_exec", "enable\r"]
        assert world.survey_preview()["program"] == {
            "wake": [["idle", "\r"]],
            "prelude": {"press_return": [["press_return", "\r"], enable],
                        "setup_dialog": [["setup_dialog", "no\r"], ["press_return", "\r"],
                                         enable],
                        "user_exec": [enable]},
            "reads": [["priv_exec", "terminal length 0\r"], ["priv_exec", "show version\r"],
                      ["priv_exec", "dir nvram:\r"]],
            "release": [["priv_exec", "disable\r"]],
            "ends": "user_exec",
            "stops": "any other state the wake finds: nothing more is sent"}

    def test_a_value_held_as_a_secret_is_masked_in_the_previewed_program(self, world):
        """No pattern masks an interface name; the value the caller holds does, in every
        state's steps (the hash is over what is sent, unmasked)."""
        world.survey(greeting=PNP, answers=blank_answers())
        p = Z.kickstart_preview(LIST, world.dev["id"], dict(PARAMS),
                                values={"GigabitEthernet0/1": "a test value"}, **world.nb())
        assert p["ok"], p["refusals"]
        assert ["config", "interface <redacted:a test value>\r"] in p["program"]["lines"]
        assert "GigabitEthernet0/1" not in json.dumps(p["program"])
        assert p["hash"] == world.kick_preview()["hash"]


# ── The declarations O6b registers ────────────────────────────────────────────────────────

def test_every_stage_reference_resolves_or_says_why():
    """The stages O6b's two confirm routes declare (operation_stages.STAGES is keyed on route
    endpoints, which O6b adds): each verify and record an importable function, each n/a with
    a reason, the hash a field the confirm reads."""
    import importlib
    assert set(Z.STAGES) == {"survey", "kickstart"}
    for name, st in Z.STAGES.items():
        assert st.hash == "hash", name
        for value in (st.verify, st.rollback, st.record):
            if value.startswith("n/a:"):
                assert len(value.split(":", 1)[1].split()) >= 3, value
                continue
            mod, _, attr = value.rpartition(".")
            assert callable(getattr(importlib.import_module(mod), attr)), value


def test_the_runs_announce_what_needs_attention_listens_for():
    from modules import attention, invalidation
    assert invalidation.ANNOUNCERS[Z.ANNOUNCER] == Z.ANNOUNCE_KEYS
    assert attention.SOURCE_KEYS["console_ztp_source"] == Z.ANNOUNCE_KEYS
    assert all(k in invalidation.VOCABULARY for k in Z.ANNOUNCE_KEYS)


def test_the_holds_are_worded():
    from modules.nsot import device_ops
    for op in (Z.OP_SURVEY, Z.OP_KICKSTART):
        assert op in device_ops.OPERATION_WORDS


# ── One home for the host and credential-reference rules (C1558) ───────────────────────────

@pytest.mark.parametrize("host", [
    "192.0.2.10", "2001:db8::1", "[2001:db8::1]", "fe80::1%eth0", "[fe80::1%eth0]",
    "Console-1.Example.NET", "console.example.", "[192.0.2.1]", "192.0.2.1%eth0",
    "fe80::1%eth 0", "fe80::1%eth0\n", "fe80::1%", "192.0.2.300", "2001:db8::zz", " cons",
    "cons;reboot", "", None, "a..b", "x" * 254])
def test_the_store_keeps_exactly_what_the_transport_connects_to(host):
    from modules.nsot import console_servers as CS
    from modules.nsot import console_transport as T
    try:
        expected = (T.canonical_host(host), "")
    except T.ConsoleRefused as exc:
        expected = ("", str(exc))
    assert CS.host_refusal(host) == expected


@pytest.mark.parametrize("ref", ["console-bridge", "lab:@profile:jump", "@x", "hunter2 pass",
                                 "console-bridge\n", "", None, "a" * 129, "a" * 128,
                                 "ssh-ed25519 AAAA"])
def test_the_store_takes_a_reference_the_credential_store_takes(ref):
    from modules import credentials
    from modules.nsot import console_servers as CS
    try:
        credentials.check_ssh_key_ref(ref)
        takes = True
    except ValueError:
        takes = False
    assert (CS.credential_ref_refusal(ref) == "") is takes


def test_neither_rule_has_a_second_home_in_the_store():
    """The store's module holds no host, reference or container pattern of its own (parsed, not
    grepped): no `ipaddress` import and no compiled pattern at all (the container name's rule is
    the wrapper's since C1565)."""
    import ast
    from modules.nsot import console_servers as CS
    tree = ast.parse(open(CS.__file__, encoding="utf-8").read())
    imports = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
               for a in n.names}
    assert "ipaddress" not in imports
    patterns = [t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
                and isinstance(n.value, ast.Call)
                and getattr(n.value.func, "attr", "") == "compile" for t in n.targets]
    assert patterns == []


@pytest.mark.parametrize("host,why", [
    ("fe80::1%eth0\n", "the IPv6 zone 'eth0\\n' is not an interface name"),
    ("fe80::1%", "the IPv6 zone '' is not an interface name"),
    ("192.0.2.1%eth0", "only an IPv6 address carries a zone"),
    ("[192.0.2.1]", "only an IPv6 address is written in brackets"),
    ("2001:db8::zz", "it is not an IPv6 address"),
    ("192.0.2.300", "it is not an IPv4 address"),
])
def test_the_transport_says_why_a_host_is_refused(host, why):
    """The rule's one home now refuses a zone a line break rides in (it was kept whole, and
    keyed the host-key record with it) and says which part of a host is wrong."""
    from modules.nsot import console_transport as T
    with pytest.raises(T.ConsoleRefused) as exc:
        T.canonical_host(host)
    assert str(exc.value) == f"{host!r} is not an IPv4 or IPv6 address or a hostname: {why}"
