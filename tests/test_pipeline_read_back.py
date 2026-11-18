"""The read-back's section read has one home (the fast-lane catch-up, 2026-11-18): the failure
capture and the rollback's read-back (`pipeline._read_like_before`) read the sections stage 4
read through stage 4's own read path, `commands.run_device_command` (never a second send on a
spent session, an echoed or stitched reply refused), each name held to the interface token stage 4
holds it to. #1817 found it sending `c.send_command` directly (test_one_home_per_action,
test_session_write_guard)."""

from types import SimpleNamespace

import pytest

from modules import pipeline

SECTIONS = {"GigabitEthernet0/3": "interface GigabitEthernet0/3\n description H7\n",
            "GigabitEthernet0/4": "interface GigabitEthernet0/4\n shutdown\n"}


def _ctx(names):
    return SimpleNamespace(pre_snapshots={"192.0.2.5": {"running_config_sections": names}})


@pytest.fixture
def sent(monkeypatch):
    got = []

    def run(conn, command, adaptive_mode=True, read_timeout=60):
        got.append((command, read_timeout))
        name = command.rsplit(" ", 1)[-1]
        return SECTIONS.get(name, "% Invalid input detected at '^' marker.")

    monkeypatch.setattr("modules.commands.run_device_command", run)
    monkeypatch.setattr("modules.connection.with_temp_connection", lambda dev, fn: fn(object()))
    return got


def test_each_section_is_read_through_the_read_path_with_its_timeout(sent):
    got = pipeline._read_like_before(_ctx(list(SECTIONS)), "192.0.2.5", {}, 45)
    assert got == "\n".join(SECTIONS.values())
    assert sent == [("show running-config interface GigabitEthernet0/3", 45),
                    ("show running-config interface GigabitEthernet0/4", 45)]


def test_a_name_that_is_no_interface_is_refused_before_anything_is_sent(sent):
    with pytest.raises(ValueError, match="is not an interface name"):
        pipeline._read_like_before(_ctx(["Gi0/3 | include secret"]), "192.0.2.5", {}, 45)
    assert sent == []


def test_a_refused_section_raises_naming_its_command(sent):
    with pytest.raises(ValueError, match="show running-config interface Loopback9 could not"):
        pipeline._read_like_before(_ctx(["Loopback9"]), "192.0.2.5", {}, 45)
