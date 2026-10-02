"""C331 (2026-10-02): the deploy's pre-change snapshot is THIS run's, for THIS run's device.

Stage 4 read the running config by looking the address up in the ACTIVE list
(`_get_running_config_for_golden`), stored it under the active list's `pre_change/`, and the
failure capture and the rollback read it back by address from the active list's folder. So a
list switch during a deploy, or two lists holding one address, gave the rollback another
device's config, or none. Now Stage 4 reads on the run's own session for its carried device,
keeps the text on the run (`ctx.pre_snapshots`), and writes evidence into the CARRIED list's
folder; `_pre_change(ctx, ip)` is the one reader.

The real Stage 4 and the real rollback; the device, its session and the restore are fakes.
"""

import os

import pytest

import modules.pipeline as P
from tests.test_pipeline import _ctx

CARRIED = "interface GigabitEthernet0/0\n description core\n"
FOREIGN = "! Pre-change snapshot — other (192.0.2.31)\n!\ninterface GigabitEthernet0/0\n shutdown\n"


@pytest.fixture
def lists(tmp_path, monkeypatch):
    dirs = {name: tmp_path / name for name in ("carried", "active")}
    for d in dirs.values():
        d.mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(dirs[name]))
    monkeypatch.setattr("modules.config.get_current_list_data_dir", lambda: str(dirs["active"]))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "active")
    # The ACTIVE list holds the same address as another device, with its own stale file.
    (dirs["active"] / "pre_change").mkdir()
    (dirs["active"] / "pre_change" / "other.cfg").write_text(FOREIGN)
    monkeypatch.setattr("modules.device.get_current_device_list", lambda: ("active", "x.csv"))
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [{"ip": "192.0.2.31", "hostname": "other"}])
    return dirs


class _Session:
    """Answers as the device it was opened for: the carried r1, or the active list's
    `other` at the same address."""

    def __init__(self, dev=None):
        self.host = (dev or {}).get("hostname", "R1")

    def send_command(self, cmd, **k):
        return CARRIED if self.host == "R1" else "interface GigabitEthernet0/0\n shutdown\n"


class TestStageFourReadsTheCarriedDevice:
    def test_the_snapshot_is_the_carried_devices_and_kept_on_the_run(self, lists, monkeypatch):
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda dev, pool, lock: _Session(dev))
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, cmd, **k: conn.send_command(cmd))
        monkeypatch.setattr(P, "_capture_operational_snapshot", lambda *a, **k: {})
        ctx = _ctx(list_name="carried", device_ips=["192.0.2.31"],
                   selected_devices=[{"ip": "192.0.2.31", "hostname": "R1"}])
        P._stage_pre_snapshot(ctx)
        assert P._pre_change(ctx, "192.0.2.31") == CARRIED
        written = os.path.join(lists["carried"], "pre_change", "R1.cfg")
        assert CARRIED.strip() in open(written).read()
        assert oct(os.stat(written).st_mode & 0o777) == "0o600"
        assert not os.path.exists(os.path.join(lists["active"], "pre_change", "R1.cfg"))


class TestTheRollbackReadsOnlyTheRunsCopy:
    def test_a_foreign_file_in_the_active_list_is_never_the_undo(self, lists, monkeypatch):
        ctx = _ctx(list_name="carried", device_ips=["192.0.2.31"],
                   selected_devices=[{"ip": "192.0.2.31", "hostname": "R1"}])
        ctx.push_results = {"192.0.2.31": {"ok": False}}
        ctx.confirmed_commands = {"192.0.2.31": ["interface GigabitEthernet0/0", " shutdown", "exit"]}
        sent = []
        monkeypatch.setattr(P, "_restore_config", lambda conn, cmds: sent.extend(cmds))
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda dev, pool, lock: object())
        P._stage_rollback(ctx)
        assert sent == [], "the rollback built an undo from another device's file"
        assert ctx.rollback_outcome["192.0.2.31"]["state"] == "not_attempted"

    def test_the_runs_own_copy_is_the_undo(self, lists, monkeypatch):
        ctx = _ctx(list_name="carried", device_ips=["192.0.2.31"],
                   selected_devices=[{"ip": "192.0.2.31", "hostname": "R1"}])
        ctx.pre_snapshots = {"192.0.2.31": {"running_config": CARRIED}}
        ctx.push_results = {"192.0.2.31": {"ok": False}}
        ctx.confirmed_commands = {"192.0.2.31": ["interface GigabitEthernet0/0", " shutdown", "exit"]}
        sent = []
        monkeypatch.setattr(P, "_restore_config", lambda conn, cmds: sent.extend(cmds))
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda dev, pool, lock: object())
        monkeypatch.setattr("modules.connection.with_temp_connection",
                            lambda dev, func: func(_Session()))
        P._stage_rollback(ctx)
        assert " no shutdown" in sent, sent
