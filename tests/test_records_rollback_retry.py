"""The rollback blocks and the authorised retries on the records database (K31 part 3: two more
DOCUMENT stores, one per network in its repository's `.nsot/`), against a REAL PostgreSQL shaped
as host step 6a makes it (tests/pg_instance.py; skipped with its reason here, a failure in CI).

Driven through their owner, as the pipeline and a person drive them: a rollback is recorded
(`hostvars.record_rolled_back`), a retry authorised (`authorise_retry`, which writes the retry
log and lifts the block), and read back through `rolled_back_note`, `retry_log_read` and
`intent_ops.retry_history` (C1324: it opened the log itself; it reads through the owner now).
Each keeps its safety contract on a database that does not answer: an unreadable record blocks
every plan, and a retry nobody can record is never authorised.
"""

import os

import pytest

from modules import config, records_docs
from modules import records_migrate as RM
from modules.nsot import hostvars, intent_ops
from tests.test_records_restarts import db, pg  # noqa: F401 (the server and the settings)

FOLDERS = ("default", "branch-2")
PROGRAM = ["interface Gi0/1", " description uplink"]


@pytest.fixture
def repos(db):
    out = {}
    for f in FOLDERS:
        repo = os.path.join(config.LISTS_DIR, f, "config_repo")
        os.makedirs(os.path.join(repo, ".nsot"), exist_ok=True)
        out[f] = repo
    return dict(db, repos=out)


def _rollback(repo, host):
    hostvars.record_rolled_back(repo, host, "c0ffee" * 6 + "abcd", reason="verify failed",
                                pipeline_id="p1", commands=PROGRAM)


def _move(store):
    return RM.move(RM.plan(store=store)["fingerprint"], "alex@example.com", "access", store=store)


def test_both_are_document_stores_kept_per_network():
    for store in ("rollback_blocks", "retry_log"):
        assert records_docs.is_doc_store(store)
    assert records_docs.repo_network("/data/lists/branch-2/config_repo") == "branch-2"


class TestTheBlocks:
    def test_the_move_keeps_each_network_s_blocks_and_new_ones_land_in_the_table(self, repos):
        r = repos["repos"]
        _rollback(r["default"], "r1"), _rollback(r["branch-2"], "r2")
        assert _move("rollback_blocks")["ok"]
        assert hostvars.rolled_back_note(r["default"], "r1", PROGRAM)
        assert hostvars.rolled_back_note(r["branch-2"], "r1", PROGRAM) is None, "kept apart"
        _rollback(r["branch-2"], "r3")
        assert hostvars.rolled_back_note(r["branch-2"], "r3", PROGRAM)
        assert RM.check(store="rollback_blocks")["ok"]

    def test_a_retry_on_the_database_lifts_the_block_and_is_recorded(self, repos):
        r = repos["repos"]
        _rollback(r["default"], "r1")
        assert _move("rollback_blocks")["ok"] and _move("retry_log")["ok"]
        got = hostvars.authorise_retry(r["default"], "r1", actor="alex@example.com",
                                       reason="the neighbour was down for maintenance")
        assert got["ok"], got
        assert hostvars.rolled_back_note(r["default"], "r1", PROGRAM) is None
        log = hostvars.retry_log_read(r["default"])
        assert log["state"] == "ok" and [e["device"] for e in log["rows"]] == ["r1"]
        assert intent_ops.retry_history(r["default"], "r1")["count"] == 1
        assert not os.path.exists(os.path.join(r["default"], hostvars.RETRY_LOG_REL)), \
            "the log was never written to a file"

    def test_a_retry_whose_log_save_is_refused_is_never_authorised(self, repos, monkeypatch):
        """The log read back, the save refused: the block stands, nothing said authorised."""
        r = repos["repos"]
        _rollback(r["default"], "r1")
        assert _move("retry_log")["ok"]

        def refused(*_a, **_k):
            raise RuntimeError("the server refused the write")
        monkeypatch.setattr(records_docs, "save", refused)
        got = hostvars.authorise_retry(r["default"], "r1", actor="alex@example.com",
                                       reason="the neighbour was down for maintenance")
        assert got["ok"] is False and "the block stands" in got["error"], got
        assert "the server refused the write" in got["error"]
        assert hostvars.rolled_back_note(r["default"], "r1", PROGRAM), "still blocked"

    def test_the_move_back_writes_each_network_s_blocks_to_its_file(self, repos):
        r = repos["repos"]
        _rollback(r["default"], "r1")
        assert _move("rollback_blocks")["ok"]
        _rollback(r["branch-2"], "r2")
        back = RM.move_back(RM.plan(store="rollback_blocks")["fingerprint"],
                            "alex@example.com", "access", store="rollback_blocks")
        assert back["ok"], back["steps"]
        assert hostvars.rolled_back_note(r["branch-2"], "r2", PROGRAM)
        assert os.path.exists(os.path.join(r["branch-2"], hostvars.ROLLED_BACK_REL))


class TestADatabaseThatDoesNotAnswer:
    @pytest.fixture
    def down(self, repos):
        for store in ("rollback_blocks", "retry_log"):
            repos["values"][f"records_store_{store}"] = "postgres"
        repos["values"]["records_db_port"] = 1
        return repos

    def test_an_unreadable_record_blocks_every_plan(self, down):
        note = hostvars.rolled_back_note(down["repos"]["default"], "any-device", PROGRAM)
        assert note and note.get("unreadable"), note

    def test_a_rollback_that_cannot_be_kept_is_refused_never_a_lifted_block(self, down):
        with pytest.raises(hostvars.RolledBackRecordUnreadable, match="records database"):
            _rollback(down["repos"]["default"], "r1")

    def test_a_retry_nobody_can_record_is_never_authorised(self, down):
        # The blocks on their file, so the block exists; only the retry log's database is down.
        down["values"]["records_store_rollback_blocks"] = "file"
        repo = down["repos"]["default"]
        _rollback(repo, "r1")
        got = hostvars.authorise_retry(repo, "r1", actor="alex@example.com",
                                       reason="the neighbour was down for maintenance")
        assert got["ok"] is False and "the block stands" in got["error"]
        assert hostvars.rolled_back_note(repo, "r1", PROGRAM), "still blocked"

    def test_the_retry_history_says_unreadable_never_none(self, down):
        got = intent_ops.retry_history(down["repos"]["default"], "r1")
        assert got["count"] is None and "could not be read" in got["unreadable"]
