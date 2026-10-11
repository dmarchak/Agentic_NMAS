"""C662's reader (`modules/readers/rip.py`): what RIP and RIPng hear, read from the devices whose
committed intent configures them, on the devices' real answers (tests/fixtures/topology/rip/,
read through Mercury on 2026-10-11).

- It asks only what the read-only allowlist allows, and only what the device's intent needs.
- A device that cannot be read is said with its reason, never as hearing nothing: no stored
  credential, no device type, a session that fails, a read that raises.
- Topology takes the stored answer only while it is current (the reader's promise); past it,
  RIP is drawn as not read, and the read's error says when it was read.
"""

import json
import os

import pytest

from modules import reader_job
from modules.readers import rip as R
from modules.readers import topology_graph as T

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "topology", "rip")


def _out(device, command):
    name = command.replace(" ", "_").replace("-", "_")
    with open(os.path.join(FIX, f"{device}__{name}.txt"), encoding="utf-8") as fh:
        return fh.read()


class _Conn:
    def __init__(self, device):
        self.device, self.sent, self.closed = device, [], False

    def enable(self):
        pass

    def send_command(self, command):
        self.sent.append(command)
        return _out(self.device, command)

    def disconnect(self):
        self.closed = True


@pytest.fixture
def stored(monkeypatch):
    monkeypatch.setattr("modules.device.open_stored", lambda row, field="password": ("x", ""))
    monkeypatch.setattr("modules.nsot.credential_rotation.enable_secret", lambda row: "")


ROW = {"hostname": "s1", "ip": "192.0.2.21", "device_type": "cisco_ios", "username": "u"}


def test_the_commands_are_read_only():
    from modules.readonly_commands import refusal
    assert all(refusal(c) == "" for c in R.COMMANDS.values())


def test_a_device_answers_what_it_hears(stored):
    conns = []

    def connect(**params):
        conns.append(_Conn("s1"))
        return conns[-1]

    got = R.read_device(ROW, {"rip": True, "ripng": True}, connect=connect)
    assert got["error"] == ""
    assert [s["gateway"] for s in got["rip"]] == ["10.255.2.10"]
    assert [(h["interface"], h["paths"]) for h in got["ripng"]] == [
        ("Vlan10", 4), ("Vlan20", 4), ("Vlan30", 4), ("GigabitEthernet0/2", 2)]
    assert conns[0].sent == list(R.COMMANDS.values()) and conns[0].closed


def test_only_what_its_intent_needs_is_asked(stored):
    conns = []
    R.read_device(ROW, {"rip": False, "ripng": True},
                  connect=lambda **p: conns.append(_Conn("s1")) or conns[-1])
    assert conns[0].sent == [R.COMMANDS["ripng"]]


def test_no_credential_is_said_and_nothing_connects(monkeypatch):
    monkeypatch.setattr("modules.device.open_stored", lambda row, field="password": ("", ""))
    got = R.read_device(ROW, {"rip": True, "ripng": True},
                        connect=lambda **p: pytest.fail("connected without a credential"))
    assert got == {"rip": None, "ripng": None, "error": "no stored credential"}


def test_no_device_type_is_never_guessed(stored):
    got = R.read_device(dict(ROW, device_type=""), {"rip": True, "ripng": False},
                        connect=lambda **p: pytest.fail("connected with no device type"))
    assert got["rip"] is None and "not guessed" in got["error"]


def test_a_failed_session_is_said_never_as_hearing_nothing(stored):
    def connect(**params):
        raise TimeoutError("timed out")
    got = R.read_device(ROW, {"rip": True, "ripng": True}, connect=connect)
    assert got["rip"] is None and got["ripng"] is None
    assert got["error"] == "could not ask: TimeoutError: timed out"


def test_rip_configured_and_not_running_is_said(stored):
    class Silent(_Conn):
        def send_command(self, command):
            return "*** IP Routing is NSF aware ***\n"
    got = R.read_device(ROW, {"rip": True, "ripng": False}, connect=lambda **p: Silent("s1"))
    assert got["rip"] == [] and "names no RIP" in got["error"]


def test_the_read_keeps_each_device_and_says_a_raise():
    items = [("Lab", {"hostname": "r1"}, {"rip": True, "ripng": True}),
             ("Lab", {"hostname": "s1"}, {"rip": True, "ripng": True})]

    def read_fn(row, wants):
        if row["hostname"] == "s1":
            raise RuntimeError("boom")
        return {"rip": [], "ripng": [], "error": ""}

    got = R.read(population_fn=lambda: items, read_fn=read_fn, clock=lambda: 0)
    assert got["devices"] == 2
    assert got["lists"]["Lab"]["r1"] == {"rip": [], "ripng": [], "error": "",
                                         "read_at": "1970-01-01T00:00:00Z"}
    assert got["lists"]["Lab"]["s1"]["rip"] is None
    assert got["lists"]["Lab"]["s1"]["error"] == "the read raised RuntimeError: boom"


#: The stored read's time, by the standard library, never typed.
_AT = __import__("calendar").timegm((2026, 10, 11, 6, 40, 0))


def _store(value_at):
    path = reader_job.store_path(R.NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"last_good": {"value": {"lists": {"Lab": {"s1": {"rip": []}}}, "devices": 1},
                                 "value_at": value_at}}, fh)
    return path


class TestTopologyTakesOnlyACurrentAnswer:
    def test_none_stored_is_nothing_and_no_error(self):
        path = reader_job.store_path(R.NAME)
        if os.path.exists(path):
            os.remove(path)
        assert T.rip_answer() == ({}, "")

    def test_current_is_taken(self):
        path = _store("2026-10-11T06:40:00Z")
        try:
            at = _AT
            lists, err = T.rip_answer(clock=lambda: at + R.INTERVAL_SECONDS)
            assert lists == {"Lab": {"s1": {"rip": []}}} and err == ""
        finally:
            os.remove(path)

    def test_past_its_promise_is_not_read_and_says_when(self):
        path = _store("2026-10-11T06:40:00Z")
        try:
            at = _AT
            promise = reader_job.page_promise(R.READER)
            lists, err = T.rip_answer(clock=lambda: at + promise + 1)
            assert lists == {}
            assert err == (f"RIP: last read at 2026-10-11T06:40:00Z, more than {promise} s "
                           "ago; drawn as not read")
        finally:
            os.remove(path)
