"""The line stores kept one file per network on the records database (K31 part 2b): each network's
settings changes, onboarding runs and inventory edits, in its list folder, against a REAL
PostgreSQL shaped as host step 6a makes it (tests/pg_instance.py; skipped with its reason here, a
failure in CI).

Each table holds every network's rows by network: the network is the list folder's name,
verbatim (never re-slugged, so a folder a registry names is matched as itself), and a network's
read returns its own rows only, before and after a move. Written and read through each owner:
`list_settings._record` / `changes`, `onboard.record_run` / `read_runs`, and the inventory edits
through the seam with `inventory_edit.history` reading them (its writer needs a real inventory).
"""

import os
import types

import pytest

from modules import config, inventory_edit, list_settings, records_db
from modules import records_migrate as RM
from modules.nsot import onboard
from tests.test_records_restarts import db, pg  # noqa: F401 (the server and the settings)

#: Two networks; "branch-2" is a folder name `list_slug` would rewrite ("branch_2").
FOLDERS = {"Default": "default", "Branch 2": "branch-2"}


def _folder(network):
    return os.path.join(config.LISTS_DIR, FOLDERS[network])


@pytest.fixture
def nets(db, monkeypatch):
    for f in FOLDERS.values():
        os.makedirs(os.path.join(config.LISTS_DIR, f, "config_repo"), exist_ok=True)
    monkeypatch.setattr("modules.config.list_data_path",
                        lambda name: _folder(name) if name in FOLDERS else
                        os.path.join(config.LISTS_DIR, config.list_slug(name)))
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: types.SimpleNamespace(name=name, data_dir=_folder(name)))
    return db


def _settings(network, n):
    entry = list_settings._record(network, {"kind": "group_switch", "group": f"g{n}",
                                            "actor": "alex@example.com",
                                            "actor_verified": "access"})
    assert entry["recorded"], entry
    return entry


def _run(network, n):
    repo = os.path.join(_folder(network), "config_repo")
    got = onboard.record_run(repo, "verify", network, f"d{n}", "alex@example.com",
                             {"ok": True, "steps": [{"step": "read", "ok": True}]})
    assert got["ok"], got


def _edit(network, n):
    path = os.path.join(_folder(network), inventory_edit.AUDIT_FILE)
    RM.store_append(inventory_edit.AUDIT_STORE, path,
                    {"at": f"2026-10-1{n}T00:00:00Z", "list": network, "device": f"d{n}",
                     "field": "role", "before": "", "after": "switch",
                     "reason": "the device is an access switch in rack two",
                     "actor": "alex@example.com", "actor_verified": "access"},
                    network=FOLDERS[network])


#: Each store: its writer and its owner's read for one network, newest first or oldest first
#: as the owner answers.
CASES = {
    "network_settings_record": (_settings, lambda net: list_settings.changes(net)["rows"]),
    "onboarding_runs": (_run, lambda net: onboard.read_runs(
        os.path.join(_folder(net), "config_repo"))["rows"]),
    "inventory_edits": (_edit, lambda net: inventory_edit.history(net)["rows"]),
}


def _move(store):
    return RM.move(RM.plan(store=store)["fingerprint"], "alex@example.com", "access", store=store)


def test_each_is_a_store_kept_per_network():
    for store in CASES:
        assert store in records_db.STORES and RM.store_of(store).per_network


@pytest.mark.parametrize("store", sorted(CASES))
class TestEachStore:
    def test_the_preview_counts_each_network_s_file(self, nets, store):
        write, _read = CASES[store]
        write("Default", 1), write("Branch 2", 2), write("Branch 2", 3)
        rows = {r["network"]: r["lines"] for r in RM.plan(store=store)["networks"]}
        assert rows == {"default": 1, "branch-2": 2}, rows

    def test_the_move_keeps_each_network_s_rows_apart(self, nets, store):
        write, read = CASES[store]
        write("Default", 1), write("Branch 2", 2)
        before = {n: read(n) for n in FOLDERS}
        out = _move(store)
        assert out["ok"], out["steps"]
        assert {n: read(n) for n in FOLDERS} == before
        write("Branch 2", 3)
        assert len(read("Branch 2")) == 2 and len(read("Default")) == 1
        assert RM.check(store=store)["ok"]

    def test_the_move_back_returns_each_line_to_its_own_folder(self, nets, store):
        write, read = CASES[store]
        write("Default", 1)
        assert _move(store)["ok"]
        write("Branch 2", 2)
        moved = {n: read(n) for n in FOLDERS}
        back = RM.move_back(RM.plan(store=store)["fingerprint"], "alex@example.com", "access",
                            store=store)
        assert back["ok"], back["steps"]
        assert {n: read(n) for n in FOLDERS} == moved
        assert os.path.exists(os.path.join(_folder("Branch 2"),
                                           os.path.basename(RM.store_of(store).path_for(
                                               "branch-2"))))

    def test_a_database_that_does_not_answer_is_unreadable_never_none(self, nets, store):
        _write, read = CASES[store]
        nets["values"][f"records_store_{store}"] = "postgres"
        nets["values"]["records_db_port"] = 1
        assert read("Default") == []
        path = RM.store_of(store).path_for("default")
        got = RM.store_rows(store, path, network="default")
        assert got["state"] == "unreadable" and "the records database" in got["error"]


class TestEachOwnerSaysAFailedRecord:
    @pytest.fixture
    def down(self, nets):
        for store in CASES:
            nets["values"][f"records_store_{store}"] = "postgres"
        nets["values"]["records_db_port"] = 1
        return nets

    def test_a_settings_switch_says_its_record_was_not_kept(self, down):
        entry = list_settings._record("Default", {"kind": "group_switch", "actor": "a",
                                                  "actor_verified": "access"})
        assert entry["recorded"] is False and "did not accept" in entry["record_error"]
        assert list_settings.changes("Default")["state"] == "unreadable"

    def test_an_onboarding_run_says_its_record_was_not_written(self, down):
        repo = os.path.join(_folder("Default"), "config_repo")
        got = onboard.record_run(repo, "verify", "Default", "d1", "a", {"ok": True})
        assert got["ok"] is False and got["error"]
        assert onboard.read_runs(repo)["state"] == "unreadable"

    def test_inventory_history_says_unreadable(self, down):
        assert inventory_edit.history("Default")["state"] == "unreadable"
