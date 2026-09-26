"""P.3 step 7: every use of the break-glass terminal is recorded.

WHO opened it, for WHICH device, from WHERE, and WHEN it opened and closed,
in `data/terminal_audit.jsonl`, 0600. Refused attempts too. **Never a
keystroke**: a record of what was typed would hold every password typed into
a device. A closed tab is a close as well; there was no handler for the socket
disconnecting, so a session that ended that way would never have been closed
in the record.
"""

import json
import os
import stat

import pytest

TYPED = "SECRET-TYPED-3f9a2b"


@pytest.fixture
def term(monkeypatch, tmp_path):
    import app as A
    import modules.config as C
    monkeypatch.setattr(C, "DATA_DIR", str(tmp_path))
    opened = []
    monkeypatch.setattr(A, "ensure_terminal_session",
                        lambda ip, sessions: opened.append(ip))
    monkeypatch.setattr(A, "start_terminal_reader", lambda *a, **k: None)
    monkeypatch.setattr(A, "get_current_device_list", lambda: ("Lab", "x.csv"))
    monkeypatch.setattr(A, "load_saved_devices",
                        lambda p: [{"hostname": "s1", "ip": "192.0.2.21"}])
    path = tmp_path / "terminal_audit.jsonl"

    def rows():
        if not path.exists():
            return []
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    client = A.socketio.test_client(A.app)
    return {"client": client, "rows": rows, "path": path, "opened": opened}


def test_opening_writes_who_what_where_and_when(term):
    from tests.conftest import TEST_PERSON
    term["client"].emit("connect_terminal", {"ip": "192.0.2.21"})
    rows = term["rows"]()
    assert [r["event"] for r in rows] == ["opened"]
    row = rows[0]
    assert row["actor"] == TEST_PERSON and row["kind"] == "person"
    assert row["device_ip"] == "192.0.2.21" and row["hostname"] == "s1"
    assert row["session"] and row["at"].endswith("Z")
    assert "peer" in row


def test_keystrokes_are_never_recorded(term):
    term["client"].emit("connect_terminal", {"ip": "192.0.2.21"})
    before = len(term["rows"]())
    term["client"].emit("terminal_input", {"ip": "192.0.2.21", "input": TYPED + "\r"})
    assert len(term["rows"]()) == before, "typing wrote a row"
    assert TYPED not in term["path"].read_text()


def test_closing_from_the_page_is_recorded(term):
    term["client"].emit("connect_terminal", {"ip": "192.0.2.21"})
    term["client"].emit("disconnect_terminal", {"ip": "192.0.2.21"})
    rows = term["rows"]()
    assert [r["event"] for r in rows] == ["opened", "closed"]
    assert rows[1]["reason"] == "closed from the page"
    assert rows[1]["session"] == rows[0]["session"]


def test_a_closed_tab_is_recorded_as_a_close(term):
    """There was no disconnect handler: this session would never have closed."""
    term["client"].emit("connect_terminal", {"ip": "192.0.2.21"})
    term["client"].disconnect()
    rows = term["rows"]()
    assert [r["event"] for r in rows] == ["opened", "closed"]
    assert rows[1]["reason"] == "browser disconnected"


def test_a_disconnect_with_no_terminal_records_nothing(term):
    """Control for the one above: the handler is not a blanket 'closed' row."""
    term["client"].disconnect()
    assert term["rows"]() == []


@pytest.mark.real_identity
def test_a_refused_attempt_is_recorded_and_opens_nothing(term):
    term["client"].emit("connect_terminal", {"ip": "192.0.2.21"})
    rows = term["rows"]()
    assert [r["event"] for r in rows] == ["refused"]
    assert rows[0]["device_ip"] == "192.0.2.21"
    assert rows[0]["actor"] == "unauthenticated"
    assert term["opened"] == []


def test_a_failed_open_is_recorded_with_its_cause_class(term, monkeypatch):
    import app as A

    def _fail(ip, sessions):
        raise RuntimeError("Authentication failed for 192.0.2.21")
    monkeypatch.setattr(A, "ensure_terminal_session", _fail)
    term["client"].emit("connect_terminal", {"ip": "192.0.2.21"})
    rows = term["rows"]()
    assert [r["event"] for r in rows] == ["open_failed"]
    assert rows[0]["reason"] == "RuntimeError"


def test_the_file_is_owner_only(term):
    if os.name == "nt":
        pytest.skip("POSIX modes")
    term["client"].emit("connect_terminal", {"ip": "192.0.2.21"})
    assert stat.S_IMODE(os.stat(term["path"]).st_mode) == 0o600


def test_a_recorder_failure_is_counted_and_never_breaks_the_terminal(term, monkeypatch, caplog):
    from modules import terminal_audit

    def _boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr("modules.config.open_secure", _boom)
    before = terminal_audit.health()["failed"]
    term["client"].emit("connect_terminal", {"ip": "192.0.2.21"})
    assert term["opened"] == ["192.0.2.21"], "the terminal still opened"
    assert terminal_audit.health()["failed"] == before + 1
    assert any("COULD NOT RECORD" in r.getMessage() for r in caplog.records)


def test_the_input_handler_never_touches_the_record():
    import inspect

    import app as A
    src = inspect.getsource(A.socket_terminal_input)
    assert "_terminal_audit" not in src and "terminal_audit" not in src


def test_the_secret_storage_checker_knows_the_file():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, "scripts", "nmas-check-secret-storage"), encoding="utf-8").read()
    assert '("terminal_audit.jsonl", "no-secret")' in src
