"""C153: reload is SEND, READ, DECIDE, and its success is the session dropping.

R1, 2026-09-28: bulk reload sent `reload`, then a newline to whatever the
device asked, then waited for output. A reloading device produces none, so a
reload that worked sat at "Executing..." until the session timed out, and would
then have been drawn FAILED: the inverse of C152 in the same screen (the
operator). Each case asserts what reached the device, line by line.
"""

from modules.device_reload import reload_device


class FakeSession:
    def __init__(self, asked, drop_after_reads=None, alive=True):
        self.asked, self.written, self.sent = asked, [], []
        self.reads, self.drop_after, self.alive = 0, drop_after_reads, alive

    def send_command_timing(self, cmd, **kw):
        self.sent.append(cmd)
        return self.asked

    def write_channel(self, text):
        self.written.append(text)

    def is_alive(self):
        return self.alive

    def read_channel(self):
        self.reads += 1
        if self.drop_after is not None and self.reads > self.drop_after:
            raise OSError("Socket is closed")
        return ""


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _run(sess, **kw):
    c = Clock()
    return reload_device(sess, clock=c, sleep=c.sleep, **kw)


def test_confirm_then_the_session_drops_is_success_and_says_what_it_knows():
    s = FakeSession("probe-r1a#reload\nProceed with reload? [confirm]", drop_after_reads=3)
    out = _run(s)
    assert out["ok"] and out["outcome"] == "reloading", out
    assert s.sent == ["reload"] and s.written == ["\n"], (s.sent, s.written)
    assert "Nothing here checks that the device came back up" in out["detail"]
    assert out["dropped_after"] is not None


def test_a_drop_seen_through_is_alive_is_success_too():
    s = FakeSession("Proceed with reload? [confirm]", alive=False)
    assert _run(s)["outcome"] == "reloading"


def test_unsaved_changes_are_refused_and_never_confirmed():
    """Saving writes an unapproved running config over startup; answering no
    loses the change. A person's decision: nothing is confirmed, and the
    prompt is abandoned with Ctrl-C, never answered."""
    s = FakeSession("System configuration has been modified. Save? [yes/no]: ")
    out = _run(s)
    assert not out["ok"] and out["outcome"] == "refused_unsaved", out
    assert s.written == ["\x03"], s.written
    assert "not reloaded" in out["detail"]


def test_an_unexpected_prompt_is_refused_and_named():
    s = FakeSession("Do you really want to do something else? [y/n]")
    out = _run(s)
    assert not out["ok"] and out["outcome"] == "unexpected_prompt", out
    assert s.written == ["\x03"] and "[y/n]" in out["detail"]


def test_a_session_that_never_drops_is_not_called_a_reload():
    """The floor: a confirmed reload whose session stays up is NOT success;
    it is unknown, and says to check the console."""
    s = FakeSession("Proceed with reload? [confirm]", drop_after_reads=None)
    out = _run(s, drop_window=5, poll=1)
    assert not out["ok"] and out["outcome"] == "not_dropped", out
    assert s.written == ["\n"] and "console" in out["detail"]
