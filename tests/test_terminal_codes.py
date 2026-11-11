"""Terminal control sequences never reach what Mercury keeps or draws of a host's answer (C2989).

The operator's Lab 9 sitting, 2026-11-10: "A Linux host's answers carry terminal escape codes
("[?1h=", "[0;1;34m" around systemctl answers)". A Linux host's session is a terminal, so
`systemctl` pages its answer (the pager's keypad mode, `ESC[?1h ESC=`) and colours it (a unit
file's name, `ESC[0;1;34m`); Netmiko's Linux driver removes the codes on its own list and leaves
those. `commands.strip_control_sequences` removes what is left, in the one sender
(`run_device_command`), on a session Netmiko itself marks as writing them, so the reads engine's
record, its SHA-256, the page and the controller's unit readers hold the text alone.

The answers here are NOT captures: the repository's Lab 9 captures were stripped of escape codes
when they were masked (tests/fixtures/lab9_captures/2026-11-06/README.md). They are a `systemctl
cat` and a `systemctl show` answer in the shape of tests/test_controller_app_sources.py's, with
the two sequences the operator quoted placed where a pager and systemd's colouring write them,
and the codes Netmiko's own strip leaves beside them (`ESC>`, the keypad mode's end).
"""

import pytest

from modules import commands

LIST = "Lab"
UNIT = "ryu-manager.service"
ESC = "\x1b"
MANAGER = "/opt/ryu-venv/bin/ryu-manager"
EXEC = f"{MANAGER} --ofp-tcp-listen-port 6653 ryu.app.simple_switch_13 ryu.app.ofctl_rest"

CAT_TEXT = (f"# /etc/systemd/system/{UNIT}\n[Unit]\nDescription=Ryu SDN controller\n"
            f"[Service]\nUser=ryu\nExecStart={EXEC}\n[Install]\nWantedBy=multi-user.target")
#: `systemctl cat <unit>` as the session hands it over: the pager's keypad mode around it, the
#: file's name coloured.
CAT_RAW = (f"{ESC}[?1h{ESC}={ESC}[0;1;34m# /etc/systemd/system/{UNIT}{ESC}[0m\n"
           + CAT_TEXT.split("\n", 1)[1] + f"\n{ESC}[K{ESC}[?1l{ESC}>")
SHOW_TEXT = (f"User=ryu\nExecStart={{ path={MANAGER} ; argv[]={EXEC} ; ignore_errors=no ; "
             "start_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }")
SHOW_RAW = f"{ESC}[?1h{ESC}={SHOW_TEXT}\n{ESC}[?1l{ESC}>"
COMMANDS = {f"systemctl cat {UNIT}": CAT_RAW,
            f"systemctl show -p User -p ExecStart {UNIT}": SHOW_RAW}


class HostSession:
    """A Netmiko Linux session at its boundary: `ansi_escape_codes` set, as `LinuxSSH`'s
    session preparation sets it, and each command answered once by a timing read."""
    ansi_escape_codes = True
    base_prompt = "mercury@ctl:~"

    def __init__(self, answers=None):
        self.answers, self.sent = dict(answers or COMMANDS), []

    def send_command_timing(self, command, **kw):
        self.sent.append(command)
        return self.answers[command]


class IosSession(HostSession):
    """A session Netmiko does not mark (an IOS device's): its answer is the device's bytes."""
    ansi_escape_codes = False
    base_prompt = "r1"


class TestTheStrip:
    def test_the_two_sequences_the_operator_saw_are_removed_and_nothing_else(self):
        assert commands.strip_control_sequences(CAT_RAW) == CAT_TEXT + "\n"
        assert commands.strip_control_sequences(SHOW_RAW) == SHOW_TEXT + "\n"

    @pytest.mark.parametrize("raw,text", [
        (f"{ESC}[0;1;34mblue{ESC}[0m", "blue"),                        # colours (SGR)
        (f"{ESC}[1;31mred{ESC}[m {ESC}[38;5;208morange{ESC}[39m", "red orange"),
        (f"{ESC}[?1h{ESC}=paged{ESC}[?1l{ESC}>", "paged"),             # a pager's keypad mode
        (f"{ESC}[?2004hpaste{ESC}[?2004l", "paste"),                   # bracketed paste
        (f"{ESC}[?25l{ESC}[2J{ESC}[1;1Hdrawn{ESC}[K{ESC}[?25h", "drawn"),   # cursor and erase
        (f"{ESC}]0;mercury@ctl: ~\x07prompt", "prompt"),               # OSC, ended by BEL
        (f"{ESC}]2;title{ESC}\\after", "after"),                       # OSC, ended by ST
        (f"{ESC}P1$r0m{ESC}\\kept", "kept"),                           # a DCS string
        (f"{ESC}(B{ESC}7line{ESC}8", "line"),                          # charset, save, restore
        (f"lone{ESC}", "lone"), (f"cut{ESC}[", "cut"),                 # a lone or cut-off escape
    ])
    def test_each_kind_of_sequence_is_removed_whole(self, raw, text):
        assert commands.strip_control_sequences(raw) == text

    @pytest.mark.parametrize("text", [
        "[Unit]\n[Service]\nExecStart=/bin/true", "a literal [0;1;34m and [?1h= with no ESC",
        "● ryu-manager.service - Ryu\n   Loaded: loaded (/etc/systemd/system/x; enabled)",
        "tab\tand\nnewline", "2001:db8::10 and 192.0.2.10", "", "ünïcödé … ●"])
    def test_printable_text_is_never_removed(self, text):
        assert commands.strip_control_sequences(text) == text

    def test_an_unended_string_takes_no_text_with_it(self):
        """An OSC with no end is its two opening bytes, never the answer after it."""
        assert commands.strip_control_sequences(f"{ESC}]0;title with no end\nUser=ryu") == \
            "0;title with no end\nUser=ryu"


class TestTheSender:
    def test_a_host_sessions_answer_is_the_text_alone_and_only_a_host_sessions(self):
        """Only a session Netmiko itself marks (`ansi_escape_codes`): an IOS answer's bytes
        are the device's, a file read by `more` among them."""
        conn = HostSession()
        for command, text in ((f"systemctl cat {UNIT}", CAT_TEXT),
                              (f"systemctl show -p User -p ExecStart {UNIT}", SHOW_TEXT)):
            got = commands.run_device_command(conn, command)
            assert got == text and ESC not in got
        assert conn.sent == list(COMMANDS)
        raw = f"banner{ESC}[1mbold{ESC}[0m"
        ios = IosSession({"more flash:motd.txt": raw})
        ios.send_command = ios.send_command_timing
        assert commands.run_device_command(ios, "more flash:motd.txt") == raw

    def test_the_controllers_unit_reader_parses_a_paged_answer(self):
        """C2989's criterion: `systemctl show`'s reader was fed bytes its fixtures never held."""
        from modules.apps import channel
        got = channel.parse_show(commands.run_device_command(
            HostSession(), f"systemctl show -p User -p ExecStart {UNIT}"))
        assert got["readable"] and got["user"] == "ryu" and got["exec_path"] == MANAGER
        assert got["argv"] == EXEC.split()


@pytest.fixture
def lab(monkeypatch, tmp_path):
    rows = [{"hostname": "ctl4", "ip": "192.0.2.41", "device_type": "linux"},
            {"hostname": "ctl6", "ip": "2001:db8::41", "device_type": "linux"}]
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / name))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: [dict(d) for d in rows])
    monkeypatch.setattr("modules.list_settings.value", lambda ln, key, default=None: default)
    return tmp_path


class TestWhatIsKeptAndDrawn:
    """Through the reads engine with the real sender: the record, its hash and the page."""

    @pytest.mark.parametrize("host", ["ctl4", "ctl6"], ids=("ipv4", "ipv6"))
    def test_the_record_and_the_page_hold_no_control_sequence(self, lab, host):
        import hashlib

        from modules import reads_page
        from modules.nsot import reads
        conn = HostSession()
        record = reads.run(LIST, [host], list(COMMANDS), "op@example.invalid",
                           session=lambda dev, fn: fn(conn))
        cat, show = record["results"][host]["answers"]
        assert (cat["state"], show["state"]) == ("answered", "answered")
        assert cat["answer"] == CAT_TEXT and show["answer"] == SHOW_TEXT
        assert cat["sha256"] == hashlib.sha256(CAT_TEXT.encode()).hexdigest()
        stored = (lab / LIST / "reads" / f"{record['id']}.json").read_text(encoding="utf-8")
        assert ESC not in stored and "\\u001b" not in stored and "[0;1;34m" not in stored
        assert "[?1h" not in stored and f"# /etc/systemd/system/{UNIT}" in stored
        page = reads_page.result(LIST, record["id"])
        drawn = [g["answer"] for c in page["commands"] for g in c["groups"]]
        assert drawn == [CAT_TEXT, SHOW_TEXT]
