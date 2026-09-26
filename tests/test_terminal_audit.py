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
                        lambda ip, sessions, key="": opened.append(ip))
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

    def _fail(ip, sessions, key=""):
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



# ---------------------------------------------------------------------------
# Register D12: a shell per CONNECTION, never per device
# ---------------------------------------------------------------------------

class _Chan:
    def __init__(self):
        self.sent, self.closed = [], False

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True


@pytest.fixture
def two(monkeypatch, tmp_path):
    """Two people with the same device's terminal open."""
    import app as A
    import modules.config as C
    monkeypatch.setattr(C, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(A, "start_terminal_reader", lambda *a, **k: None)
    monkeypatch.setattr(A, "get_current_device_list", lambda: ("Lab", "x.csv"))
    monkeypatch.setattr(A, "load_saved_devices", lambda p: [])
    chans = {}

    def _ensure(ip, sessions, key=""):
        chans[key] = sessions[key] = {"chan": _Chan(), "ssh": _Chan()}
    monkeypatch.setattr(A, "ensure_terminal_session", _ensure)
    monkeypatch.setattr(A, "terminal_sessions", {})
    a, b = A.socketio.test_client(A.app), A.socketio.test_client(A.app)
    a.emit("connect_terminal", {"ip": "192.0.2.21"})
    b.emit("connect_terminal", {"ip": "192.0.2.21"})
    return {"a": a, "b": b, "chans": chans, "A": A, "path": tmp_path / "terminal_audit.jsonl"}


def test_two_connections_get_two_shells(two):
    assert len(two["chans"]) == 2, two["chans"].keys()
    assert all(k.endswith("|192.0.2.21") for k in two["chans"])


def test_what_one_types_reaches_only_their_own_shell(two):
    two["a"].emit("terminal_input", {"ip": "192.0.2.21", "input": "show clock\r"})
    sent = {k: c["chan"].sent for k, c in two["chans"].items()}
    assert sorted(len(v) for v in sent.values()) == [0, 1], sent


def test_one_closing_leaves_the_other_open(two):
    two["a"].emit("disconnect_terminal", {"ip": "192.0.2.21"})
    open_ = [k for k, c in two["chans"].items() if not c["chan"].closed]
    assert len(open_) == 1
    assert list(two["A"].terminal_sessions) == open_


def test_a_closed_tab_closes_only_that_connections_shell(two):
    two["b"].disconnect()
    assert sorted(c["chan"].closed for c in two["chans"].values()) == [False, True]


def test_the_record_has_one_row_per_connection(two):
    rows = [json.loads(l) for l in two["path"].read_text().splitlines()]
    opened = [r for r in rows if r["event"] == "opened"]
    assert len(opened) == 2 and len({r["session"] for r in opened}) == 2


def test_output_goes_to_the_owning_connection_only():
    """The reader emits to the room it is given: the owning connection's."""
    import inspect
    from modules import terminal
    src = inspect.getsource(terminal.start_terminal_reader)
    assert "room=room" in src and "room=ip" not in src
    import app as A
    handler = inspect.getsource(A.socket_connect_terminal)
    assert "room=me" in handler and "join_room" not in handler
