"""P.6 M5: the helper that reads subnet 255 from kea-dhcp4's control socket
and adds the config-set control reservation. Driven against a fake Kea on a
unix socket in pytest's temporary tree, never the real one."""

import importlib.machinery
import importlib.util
import json
import os
import socket
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "docs", "bootstrap-probe", "kea-m5.py")


def _helper():
    loader = importlib.machinery.SourceFileLoader("kea_m5", HELPER)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _config(reservations=None):
    return {"hash": "abc", "Dhcp4": {"subnet4": [
        {"id": 10, "subnet": "10.10.10.0/24", "reservations": [],
         "option-data": [{"name": "routers"}]},
        {"id": 255, "subnet": "10.255.0.0/24", "reservations": list(reservations or []),
         "option-data": []},
    ]}}


FRAGMENT_ONE = {"hw-address": "aa:bb:cc:00:02:50", "ip-address": "10.255.0.50"}


class TestWithReservation:
    def test_it_adds_to_subnet_255_only(self):
        h = _helper()
        new = h.with_reservation(_config([FRAGMENT_ONE]), "aa:bb:cc:00:02:51", "10.255.0.51")
        assert h.reservations_of(new) == [("aa:bb:cc:00:02:50", "10.255.0.50"),
                                          ("aa:bb:cc:00:02:51", "10.255.0.51")]
        assert h.reservations_of(new, 10) == []

    def test_it_drops_the_hash_and_leaves_the_input_alone(self):
        h = _helper()
        before = _config([FRAGMENT_ONE])
        new = h.with_reservation(before, "aa:bb:cc:00:02:51", "10.255.0.51")
        assert "hash" not in new and before["hash"] == "abc"
        assert h.reservations_of(before) == [("aa:bb:cc:00:02:50", "10.255.0.50")]

    @pytest.mark.parametrize("mac,ip,named", [
        ("AA:BB:CC:00:02:50", "10.255.0.51", "already reserved"),
        ("aa:bb:cc:00:02:51", "10.255.0.50", "already reserved"),
    ])
    def test_it_refuses_a_mac_or_address_already_reserved(self, mac, ip, named):
        h = _helper()
        with pytest.raises(h.Refused, match=named):
            h.with_reservation(_config([FRAGMENT_ONE]), mac, ip)

    def test_it_refuses_when_the_subnet_is_absent(self):
        h = _helper()
        with pytest.raises(h.Refused, match="found 0"):
            h.with_reservation({"Dhcp4": {"subnet4": []}}, "aa:bb:cc:00:02:51", "10.255.0.51")


@pytest.fixture
def fake_kea(tmp_path):
    """A kea-dhcp4 control socket that answers each connection once, like Kea,
    and records what it was sent."""
    path = str(tmp_path / "kea4-ctrl-socket")
    state = {"config": _config([FRAGMENT_ONE]), "sent": []}
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(4)
    stop = threading.Event()

    def serve():
        srv.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            with conn:
                req = json.loads(conn.recv(1 << 20))
                state["sent"].append(req)
                if req["command"] == "config-get":
                    resp = {"result": 0, "arguments": state["config"]}
                elif req["command"] == "config-set":
                    state["config"] = req["arguments"]
                    resp = {"result": 0, "text": "Configuration successful."}
                else:
                    resp = {"result": 0, "text": "Configuration successful."}
                conn.sendall(json.dumps(resp).encode())

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    yield path, state
    stop.set()
    t.join(2)
    srv.close()


class TestAgainstAFakeKea:
    def test_show_prints_the_running_reservations(self, fake_kea, monkeypatch, capsys):
        path, _ = fake_kea
        h = _helper()
        monkeypatch.setattr(h, "SOCKET", path)
        assert h.main(["show"]) == 0
        out = capsys.readouterr().out
        assert "aa:bb:cc:00:02:50 -> 10.255.0.50" in out and "1 reservation(s)" in out

    def test_control_set_sends_config_set_and_never_config_write(self, fake_kea, monkeypatch, capsys):
        path, state = fake_kea
        h = _helper()
        monkeypatch.setattr(h, "SOCKET", path)
        assert h.main(["control-set", "aa:bb:cc:00:02:51", "10.255.0.51"]) == 0
        commands = [r["command"] for r in state["sent"]]
        assert commands == ["config-get", "config-set"], commands
        assert "config-write" not in commands
        assert h.reservations_of(state["config"])[-1] == ("aa:bb:cc:00:02:51", "10.255.0.51")
        assert "hash" not in state["sent"][1]["arguments"]
        assert "MEMORY only" in capsys.readouterr().out

    def test_a_refused_command_exits_nonzero_and_names_the_result(self, tmp_path, monkeypatch, capsys):
        h = _helper()
        monkeypatch.setattr(h, "request", lambda c, a=None: {"result": 1, "text": "bad"})
        assert h.main(["reload"]) == 1
        assert "result 1: bad" in capsys.readouterr().err
