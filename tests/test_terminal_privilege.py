"""Register B13: the terminal sent the enable secret whether or not it was
asked for, and the stored secret is the login password.

`ensure_terminal_session` sent `enable`, the secret and a newline on fixed
0.3 s sleeps, reading nothing. Every device here lands a privilege-15 user at
`#`, so `enable` never prompts, and the secret arrived as a COMMAND: echoed to
the browser, then rejected as an unknown host. Measured on s1 2026-09-26, the
last 27 of the 32 characters were on screen.

`privilege_step` sends, READS, then decides. These tests drive it with a
scripted channel. The first is the s1 case: a device already privileged
receives NOTHING.
"""

import pytest

from modules.terminal import privilege_step

SECRET = "not-a-real-secret-0123456789abcdef"


class FakeChan:
    """A shell that answers what is sent to it, from a script.

    `initial` is what the device prints on connect. `replies` maps a sent
    line (without its newline) to what the device prints next, and a list
    value is consumed one item per send.
    """

    def __init__(self, initial, replies=None):
        self._out = [initial] if initial else []
        self.replies = replies or {}
        self.sent = []

    def recv_ready(self):
        return bool(self._out)

    def recv(self, _n):
        return self._out.pop(0).encode()

    def send(self, data):
        self.sent.append(data)
        key = data.rstrip("\n")
        reply = self.replies.get(key)
        if isinstance(reply, list):
            reply = reply.pop(0) if reply else None
        if reply:
            self._out.append(reply)


def test_a_privileged_device_receives_nothing():
    """The s1 case, exactly."""
    chan = FakeChan("\r\ns1#")
    text, outcome = privilege_step(chan, SECRET, timeout=0.5)
    assert chan.sent == []
    assert outcome == "already_privileged"
    assert "s1#" in text


def test_enable_without_a_prompt_never_sends_the_secret():
    chan = FakeChan("\r\ns1>", {"enable": "\r\ns1#"})
    _text, outcome = privilege_step(chan, SECRET, timeout=0.5)
    assert chan.sent == ["enable\n"]
    assert outcome == "enabled_without_prompt"


def test_the_secret_is_sent_only_in_answer_to_a_password_prompt():
    chan = FakeChan("\r\ns1>", {"enable": "\r\nPassword: ", SECRET: "\r\ns1#"})
    _text, outcome = privilege_step(chan, SECRET, timeout=0.5)
    assert chan.sent == ["enable\n", SECRET + "\n"]
    assert outcome == "enabled_with_secret"


def test_a_rejected_secret_is_sent_once_and_never_again():
    chan = FakeChan("\r\ns1>", {"enable": "\r\nPassword: ",
                                SECRET: "\r\n% Access denied\r\nPassword: "})
    _text, outcome = privilege_step(chan, SECRET, timeout=0.5)
    assert chan.sent.count(SECRET + "\n") == 1
    assert outcome == "secret_not_accepted"


def test_no_prompt_means_nothing_is_sent():
    chan = FakeChan("")
    _text, outcome = privilege_step(chan, SECRET, timeout=0.3)
    assert chan.sent == []
    assert outcome == "prompt_not_seen"


def test_a_banner_hash_is_not_mistaken_for_a_prompt():
    """A prompt is the WHOLE last line; a banner line full of # is not one."""
    chan = FakeChan("\r\n####################\r\nAuthorised use only\r\ns1>",
                    {"enable": "\r\ns1#"})
    _text, outcome = privilege_step(chan, SECRET, timeout=0.5)
    assert chan.sent == ["enable\n"]
    assert outcome == "enabled_without_prompt"


def test_the_preamble_reaches_the_browser_first(monkeypatch):
    """What the privilege step read is the start of the session. Without
    this the browser would open blank."""
    from modules import terminal

    emitted = []

    class _SIO:
        def emit(self, event, payload, room=None):
            emitted.append((event, payload["output"]))

    class _Chan:
        closed = False

        def recv_ready(self):
            _Chan.closed = True
            return False

    sessions = {"192.0.2.1": {"chan": _Chan(), "reader_running": False,
                              "preamble": "banner\r\ns1#"}}
    started = []
    monkeypatch.setattr(terminal.threading, "Thread",
                        lambda target, daemon: started.append(target) or
                        type("T", (), {"start": lambda self: None})())
    terminal.start_terminal_reader("192.0.2.1", sessions, _SIO())
    started[0]()
    assert emitted[0] == ("terminal_output", "banner\r\ns1#")
    assert "preamble" not in sessions["192.0.2.1"], "emitted once, not per reader"


def test_the_session_uses_the_step_and_sends_nothing_itself():
    """No bare `chan.send(` of the secret remains in ensure_terminal_session."""
    import inspect
    from modules import terminal

    src = inspect.getsource(terminal.ensure_terminal_session)
    assert "privilege_step(chan" in src
    assert "chan.send(" not in src


def test_the_page_states_what_the_terminal_is_and_is_not():
    """Register B13 F: an unmasked stream is correct for break-glass, and it
    is STATED beside the terminal rather than left as an omission. The
    record sentence says it is recorded, which P.3 step 7 made true."""
    import os
    page = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "templates", "device.html"), encoding="utf-8").read()
    note = page[page.index("data-break-glass-note"):]
    note = note[:note.index("</div>")]
    assert "break-glass path" in note
    assert "unmasked, by design" in note
    assert "only if the device asks for it" in note
    assert "Its use is recorded" in note and "never recorded" in note
    assert "not written yet" not in note, "true since P.3 step 7"
