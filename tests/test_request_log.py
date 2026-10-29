"""C1836: every request leaves one line for the record, its method, path, status, duration and
verified actor, and nothing a person typed (no query string, no form value)."""

import logging

import pytest

from modules import identity, request_log
from tests.conftest import TEST_PERSON


def _client():
    import app as A
    return A.app, A.app.test_client()


def _lines(caplog):
    return [r.getMessage() for r in caplog.records
            if r.name == request_log.__name__ and r.levelno == logging.INFO]


def test_a_page_leaves_its_line_with_the_verified_person_and_no_query(caplog):
    _app, c = _client()
    caplog.set_level(logging.INFO, logger=request_log.__name__)
    r = c.get("/v2/help/sdn?q=typed-words-nobody-logs")
    assert r.status_code == 200
    lines = _lines(caplog)
    assert len(lines) == 1, lines
    words = lines[0].split()
    assert words[:4] == ["request", "GET", "/v2/help/sdn", "200"], lines[0]
    assert words[4].endswith("ms") and words[4][:-2].isdigit(), lines[0]
    assert words[5] == f"actor={TEST_PERSON}", lines[0]
    assert "typed-words-nobody-logs" not in lines[0]


def test_a_refused_post_is_timed_and_names_who_the_gate_saw_not_its_form(caplog, monkeypatch):
    """The gate refuses an unverified POST before any input is read: its line still has a
    duration (the start is stamped ahead of the gate) and names UNVERIFIED, never a name the
    form carried."""
    _app, c = _client()
    nobody = identity.Identity(outcome="no_assertion", reason="no assertion in the test")
    monkeypatch.setattr(identity, "identify", lambda _request: nobody)
    caplog.set_level(logging.INFO, logger=request_log.__name__)
    r = c.post("/restarts/planned",
               data={"actor": "someone-typed", "reason": "a-reason-nobody-logs"})
    assert r.status_code in (401, 403), r.status_code
    lines = _lines(caplog)
    assert len(lines) == 1, lines
    words = lines[0].split()
    assert words[:4] == ["request", "POST", "/restarts/planned", str(r.status_code)], lines[0]
    assert words[4][:-2].isdigit(), f"the refused request was not timed: {lines[0]}"
    assert words[5] == f"actor={identity.UNVERIFIED}", lines[0]
    assert "someone-typed" not in lines[0] and "a-reason-nobody-logs" not in lines[0]


def test_a_static_file_leaves_no_line_here(caplog):
    _app, c = _client()
    caplog.set_level(logging.INFO, logger=request_log.__name__)
    c.get("/static/css/nmas-v2.css")
    assert _lines(caplog) == []


def test_the_start_is_stamped_before_the_gate_runs():
    """Flask runs before_request hooks in the order installed: the stamp must precede the
    gate's `enforce`, or every refused request would read "?ms"."""
    from modules import route_gates
    app, _c = _client()
    hooks = [f.__name__ for f in app.before_request_funcs.get(None, [])]
    assert hooks.index("_request_started") < hooks.index(route_gates.enforce.__name__), hooks


def test_the_line_reaches_standard_output_which_is_the_journal(capsys):
    """Under systemd standard output is flask-app's journal, the source the C1836 host step
    brings into Loki; the line is there as well as in the log file."""
    _app, c = _client()
    capsys.readouterr()
    c.get("/v2/help/sdn")
    out = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("request ")]
    assert len(out) == 1 and out[0].startswith("request GET /v2/help/sdn 200 "), out


def test_standard_output_is_masked_as_every_handler(capsys):
    _client()
    capsys.readouterr()
    logging.getLogger(request_log.__name__).info("snmp-server community Plant3dCommunity RO")
    out = capsys.readouterr().out
    assert "snmp-server community" in out and "Plant3dCommunity" not in out, out


def _syslog_form():
    """The device syslog form, as the C1836 host step defines it (its `FORM=` line), so this
    test's expectation does not come from the module it checks."""
    import os
    import re
    step = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts", "host-steps", "c1836-flask-app-journal.sh")
    m = re.search(r"^FORM='(.*)'$", open(step, encoding="utf-8").read(), re.M)
    assert m, "the host step defines FORM"
    return m.group(1)


def test_a_path_cannot_write_a_line_of_its_own(caplog):
    """A client's path is decoded text: a newline, or a device's syslog form planted in it, would
    be a line Mercury's syslog reads count once the journal reaches Loki. Percent-encoded, it is
    one token."""
    import re
    _app, c = _client()
    caplog.set_level(logging.INFO, logger=request_log.__name__)
    planted = "/x r1: Oct 29 12:00:00.123: %SYS-5-RESTART: System restarted\nrequest GET /forged"
    c.get(planted.replace(" ", "%20").replace("\n", "%0A"))
    lines = _lines(caplog)
    assert len(lines) == 1 and "\n" not in lines[0], lines
    assert len(lines[0].split()) == 6, lines[0]
    assert not re.search(_syslog_form(), lines[0]), lines[0]
    assert re.search(_syslog_form(), " " + planted.split("/x ", 1)[1]), "the plant is the form"


@pytest.mark.parametrize("ms, want", [(1203.4, "1203ms"), (None, "?ms")])
def test_the_line_says_the_duration_or_that_it_is_unknown(ms, want):
    assert request_log.line("GET", "/v2/", 200, ms, "a@example.invalid") == (
        f"request GET /v2/ 200 {want} actor=a@example.invalid")
