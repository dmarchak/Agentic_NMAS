"""The operations interrupted while they held a device, on the records database (K31: a line store
kept per list folder under `device_ops/`), against a REAL PostgreSQL shaped as host step 6a makes
it (tests/pg_instance.py; skipped with its reason here, a failure in CI).

Written by `device_ops._record_interrupted` (as the next operation to take a device keeps what an
ended process left) and read by `device_ops.interrupted` (Needs attention's and History's read).
The append takes no `records_migrate.store_append` lock file: one would sit among the device lock
files an unindexed folder reads as devices.
"""

import os

import pytest

from modules import config, records_db
from modules import records_migrate as RM
from modules.nsot import device_ops as D
from tests.test_records_restarts import db, pg  # noqa: F401 (the server and the settings)

STORE = "interrupted_holds"


@pytest.fixture
def folders(db):
    for name in ("default", "branch_2"):
        os.makedirs(os.path.join(config.DATA_DIR, "device_ops", name), exist_ok=True)
    return db


def _left(network, host, started):
    D._record_interrupted(network, host, {"device": host, "operation": "deploy",
                                          "actor": "alex@example.com", "started": started,
                                          "pid": 4242}, "capture", "sam@example.com")


def _move():
    return RM.move(RM.plan(store=STORE)["fingerprint"], "alex@example.com", "access", store=STORE)


def _devices(network):
    return [r["device"] for r in D.interrupted(network) if r.get("found_at")]


def test_it_is_a_line_store_kept_per_list_folder():
    assert STORE in records_db.STORES and RM.store_of(STORE).per_network


def test_the_move_keeps_each_folder_s_interruptions_apart(folders):
    _left("Default", "r1", 100), _left("Branch 2", "r2", 200)
    before = {n: _devices(n) for n in ("Default", "Branch 2")}
    assert before == {"Default": ["r1"], "Branch 2": ["r2"]}
    out = _move()
    assert out["ok"], out["steps"]
    assert {n: _devices(n) for n in ("Default", "Branch 2")} == before
    _left("Branch 2", "r3", 300)
    assert _devices("Branch 2") == ["r2", "r3"] and _devices("Default") == ["r1"]
    assert not any(n.endswith(".lock") for n in os.listdir(
        os.path.join(config.DATA_DIR, "device_ops", "branch_2"))), "no lock file in the folder"
    assert RM.check(store=STORE)["ok"]


def test_the_move_back_returns_each_line_to_its_folder(folders):
    _left("Default", "r1", 100)
    assert _move()["ok"]
    _left("Branch 2", "r2", 200)
    back = RM.move_back(RM.plan(store=STORE)["fingerprint"], "alex@example.com", "access",
                        store=STORE)
    assert back["ok"], back["steps"]
    assert _devices("Branch 2") == ["r2"] and _devices("Default") == ["r1"]


def test_a_database_that_does_not_answer_is_unreadable_never_none(folders):
    folders["values"]["records_store_interrupted_holds"] = "postgres"
    folders["values"]["records_db_port"] = 1
    with pytest.raises(D.HoldsUnreadable, match="the records database"):
        D.interrupted("Default")
