"""The approval queue on the records database (K31 part 3: the first DOCUMENT store, one JSON
array per network replaced whole), against a REAL PostgreSQL shaped as host step 6a makes it
(tests/pg_instance.py; skipped with its reason here, a failure in CI).

The queue is driven through its own public API (`add_approval`, `get_pending`, `read_pending`,
`withdraw`, `mark_done`), as drift, a golden commit and Needs attention drive it, for two
networks; the move, the check and the move back go through the same `records_migrate` entry
points the Record stores card calls.
"""

import json
import os
import stat
import types

import pytest

from modules import approval_queue as Q
from modules import config, records_db, records_docs
from modules import records_migrate as RM
from modules.filestore import StoreUnreadable
from tests.test_records_restarts import db, pg  # noqa: F401 (the server and the settings)

STORE = "approval_queue"
FOLDERS = {"Default": "default", "Branch 2": "branch-2"}


@pytest.fixture
def nets(db, monkeypatch):
    for f in FOLDERS.values():
        os.makedirs(os.path.join(config.LISTS_DIR, f), exist_ok=True)
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: types.SimpleNamespace(
                            name=name, data_dir=os.path.join(config.LISTS_DIR, FOLDERS[name])))
    return db


def _add(network, host):
    # One pending item per device address (the queue's own rule), so each host its own.
    return Q.add_approval("config_drift", f"{host} drifted", f"192.0.2.{int(host[1:]) + 10}",
                          host, diff="+ ntp server 192.0.2.9", list_name=network)


def _pending(network):
    return sorted(e["device_hostname"] for e in Q.get_pending(network))


def _move():
    return RM.move(RM.plan(store=STORE)["fingerprint"], "alex@example.com", "access", store=STORE)


def test_it_is_a_document_store():
    assert STORE in records_db.STORES and records_docs.is_doc_store(STORE)
    assert RM.store_of(STORE).qualified == "audit.approval_queue_docs"


class TestTheMove:
    def test_the_preview_counts_each_network_s_items(self, nets):
        _add("Default", "r1"), _add("Branch 2", "r2"), _add("Branch 2", "r3")
        rows = {r["network"]: (r["lines"], r["copied"]) for r in RM.plan(store=STORE)["networks"]}
        assert rows == {"default": (1, 0), "branch-2": (2, 0)}, rows

    def test_the_move_keeps_each_network_s_queue_and_new_items_land_in_the_table(self, nets):
        _add("Default", "r1"), _add("Branch 2", "r2")
        before = {n: Q.get_pending(n) for n in FOLDERS}
        out = _move()
        assert out["ok"], out["steps"]
        assert nets["values"]["records_store_approval_queue"] == "postgres"
        assert {n: Q.get_pending(n) for n in FOLDERS} == before
        path = os.path.join(config.LISTS_DIR, "branch-2", Q.QUEUE_FILE)
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o400
        _add("Branch 2", "r3")
        assert _pending("Branch 2") == ["r2", "r3"] and _pending("Default") == ["r1"]
        assert len(json.load(open(path))) == 1, "the file is not written"
        assert RM.check(store=STORE)["ok"]
        rows = {r["network"]: r["since"] for r in RM.plan(store=STORE)["networks"]}
        assert rows == {"default": 0, "branch-2": 1}, "one save since the move"

    def test_withdraw_and_mark_done_change_the_document_in_place(self, nets):
        first = _add("Default", "r1")
        second = _add("Default", "r2")
        assert _move()["ok"]
        assert Q.withdraw(first, "r1 is at its golden again", "drift check", "Default")["ok"]
        assert Q.mark_done(second, "recorded", actor="alex@example.com",
                           list_name="Default")["ok"]
        assert _pending("Default") == []
        statuses = sorted(e["status"] for e in Q._read("Default"))
        assert statuses == ["approved", "withdrawn"]

    def test_the_move_back_writes_each_network_s_queue_as_the_table_held_it(self, nets):
        _add("Default", "r1")
        assert _move()["ok"]
        _add("Branch 2", "r2")
        moved = {n: Q.get_pending(n) for n in FOLDERS}
        back = RM.move_back(RM.plan(store=STORE)["fingerprint"], "alex@example.com", "access",
                            store=STORE)
        assert back["ok"], back["steps"]
        assert nets["values"]["records_store_approval_queue"] == "file"
        assert {n: Q.get_pending(n) for n in FOLDERS} == moved
        assert RM.plan(store=STORE)["networks"][0]["copied"] == 0, "the rows are gone"

    def test_a_file_changed_after_its_copy_refuses_the_next_copy(self, nets):
        _add("Default", "r1")
        with records_db.connect() as conn:
            for sql in records_docs._schema(records_docs.store_of(STORE)):
                conn.execute(sql)
            conn.commit()
            records_docs.copy(conn, STORE)
        _add("Default", "r9")
        with records_db.connect() as conn:
            with pytest.raises(RM.Refused, match="the file changed after it was copied"):
                records_docs.copy(conn, STORE)

    def test_a_queue_file_that_is_not_a_list_refuses_the_move_naming_it(self, nets):
        path = os.path.join(config.LISTS_DIR, "default", Q.QUEUE_FILE)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('{"not": "a list"}')
        assert "it is not a list" in RM.plan(store=STORE)["networks"][0]["unparsable"]
        with pytest.raises(RM.Refused, match="not JSON"):
            _move()
        assert nets["values"]["records_store_approval_queue"] == "file"


class TestADatabaseThatDoesNotAnswer:
    @pytest.fixture
    def down(self, nets):
        nets["values"]["records_store_approval_queue"] = "postgres"
        nets["values"]["records_db_port"] = 1
        return nets

    def test_a_read_is_unreadable_never_no_approval_waiting(self, down):
        with pytest.raises(StoreUnreadable, match="could not be read from the records database"):
            Q.get_pending("Default")
        pending, why = Q.read_pending("Default")
        assert pending is None and "records database" in why

    def test_a_write_is_refused_and_nothing_falls_back_to_the_file(self, down):
        with pytest.raises(StoreUnreadable):
            _add("Default", "r1")
        assert not os.path.exists(os.path.join(config.LISTS_DIR, "default", Q.QUEUE_FILE))
