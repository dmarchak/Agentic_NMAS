"""Six of the installation's own logs on the records database (K31 part 2b), through the one
line-store seam `records_migrate.store_rows` / `store_append`: the reveal record, the host steps
said done, the heartbeat windows' re-measures, NetBox's removals, and the alerts' evidence packs
(PHASE8_PLAN 15.9, P1; `evidence_pack.record` and `evidence_pack.read`), and the alert history
(`alert_history.record` and `alert_history.read`, 2026-10-26), against a REAL PostgreSQL
shaped as host step 6a makes it (tests/pg_instance.py; skipped with its reason here, a failure in
CI).

Each is written by its owner's own writer where one runs without a device or an outside service
(`reveal_audit.record`, `host_steps.record_done`, `netbox_guard.record_removal`; the heartbeat
re-measure through the seam, its writer needing Loki) and read back through the owner's reader
(`reveal_audit.read`, `host_steps.done_records`, `heartbeat_windows.records`,
`netbox_guard.read_removals`).
"""

import os
import stat

import pytest

from modules import alert_history, evidence_pack, heartbeat_windows, host_steps, netbox_guard
from modules import records_db
from modules import records_migrate as RM
from modules import reveal_audit
from tests.test_records_restarts import pg  # noqa: F401 (the module's real server)
from tests.test_records_restarts import db as _db  # noqa: F401


@pytest.fixture
def db(_db, tmp_path, monkeypatch):  # noqa: F811
    """The real server's settings, and the two owners whose paths are fixed at import pointed
    into this test's own data folder."""
    monkeypatch.setattr(host_steps, "DONE", str(tmp_path / "host_steps_done.jsonl"))
    monkeypatch.setattr(netbox_guard, "_REMOVALS_FILE", str(tmp_path / "netbox_removals.jsonl"))
    return _db


def _reveal(n):
    assert reveal_audit.record(actor="alex@example.com", kind="person", what="golden_config",
                               target=f"r{n}", detail=f"ref{n}")["recorded"]


def _host_step(n):
    assert host_steps.record_done(f"{n:040x}", f"step {n}", "alex@example.com")["ok"]


def _remeasure(n):
    RM.store_append("heartbeat_rules", heartbeat_windows._record_path(),
                    {"at": f"2026-10-1{n}T00:00:00Z", "actor": "alex@example.com",
                     "fingerprint": f"f{n}", "path": "/tmp/rules.yaml", "changes": n,
                     "windows": {f"r{n}": 750}})


def _removal(n):
    assert netbox_guard.record_removal("Default", "alex@example.com",
                                       {"ok": True, "deleted": [{"endpoint": "dcim/devices",
                                                                 "id": n, "name": f"r{n}"}]})["ok"]


def _pack(n):
    """A pack as `evidence_pack.build` shapes one (no source asked: the alert alone, the rest
    absent), kept through its owner's writer."""
    EP = evidence_pack
    sections = [EP._section("alert", "Grafana's alert state", "2026-10-15T08:24:00Z", "ok",
                            pieces=[{"rule": "Interface error rate elevated",
                                     "labels": {"instance": f"192.0.2.{n}"}}])]
    pack = {"schema": EP.SCHEMA, "id": EP.pack_id(f"{n:020x}"), "alert_key": f"{n:020x}",
            "built_at": f"2026-10-1{n}T00:00:00Z", "sections": sections}
    pack["hash"] = EP.digest(pack)
    assert EP.record(pack)["ok"]


def _transition(n):
    """A transition from Grafana's captured state history (tests/fixtures/grafana/
    alert_history/), its time moved n minutes so each is its own, kept through its owner's
    recorder (`alert_history.record`, the store's lock across its read and append)."""
    from modules import alert_history
    from tests.test_alert_history import ann, load

    a = dict(ann(load("annotations_72h"), 17895), time=1792950000000 + n * 60000)
    assert alert_history.record([alert_history.from_annotation(a, "grafana-alerts")])["added"]


def _explain_answers():
    from modules.ai import explain_answers
    return explain_answers


def _explain_answer(n):
    """An Explain answer kept with its pack (C1853), through its owner's keeper (which reads the
    store first, so an answer's call is kept once)."""
    from modules.ai import explain_answers
    pack = {"id": evidence_pack.pack_id(f"{n:020x}"), "hash": f"{n:064x}"}
    result = {"ok": True, "error": "", "call_id": f"ai-{n:016x}", "cost_usd": 0.001,
              "pack_id": pack["id"], "answer": {"rationale": f"answer {n}", "hypotheses": []}}
    assert explain_answers.keep(pack, result, "alex@example.com")["kept"]


#: Each store: its writer, its owner's read as a list of rows, and its file.
CASES = {
    "explain_answers": (_explain_answer, lambda: _explain_answers().read()["rows"],
                        lambda: _explain_answers()._path()),
    "alert_history": (_transition, lambda: alert_history.read()["rows"],
                      lambda: alert_history._path()),
    "evidence_packs": (_pack, lambda: evidence_pack.read()["rows"],
                       lambda: evidence_pack._path()),
    "reveals": (_reveal, lambda: reveal_audit.read()["rows"], lambda: reveal_audit._path()),
    "host_steps_done": (_host_step, lambda: sorted(host_steps.done_records().values(),
                                                   key=lambda r: r["id"]),
                        lambda: host_steps.DONE),
    "heartbeat_rules": (_remeasure, lambda: heartbeat_windows.records()["rows"],
                        lambda: heartbeat_windows._record_path()),
    "netbox_removals": (_removal, lambda: netbox_guard.read_removals()["rows"],
                        lambda: netbox_guard._REMOVALS_FILE),
}


def _move(store):
    return RM.move(RM.plan(store=store)["fingerprint"], "alex@example.com", "access", store=store)


def test_each_is_a_store_kept_once_for_the_installation():
    for store in CASES:
        assert store in records_db.STORES and not RM.store_of(store).per_network


@pytest.mark.parametrize("store", sorted(CASES))
class TestEachLog:
    def test_the_move_keeps_every_row_and_new_ones_land_in_the_table(self, db, store):
        write, read, path = CASES[store]
        write(1), write(2)
        before = read()
        assert len(before) == 2
        out = _move(store)
        assert out["ok"], out["steps"]
        assert db["values"][f"records_store_{store}"] == "postgres"
        assert read() == before
        assert stat.S_IMODE(os.stat(path()).st_mode) == 0o400
        write(3)
        assert len(read()) == 3 and len(open(path()).read().splitlines()) == 2
        assert RM.check(store=store)["ok"]

    def test_the_move_back_exports_what_was_written_since(self, db, store):
        write, read, _path = CASES[store]
        write(1)
        assert _move(store)["ok"]
        write(2)
        moved = read()
        back = RM.move_back(RM.plan(store=store)["fingerprint"], "alex@example.com", "access",
                            store=store)
        assert back["ok"], back["steps"]
        assert read() == moved and len(moved) == 2

    def test_a_database_that_does_not_answer_is_unreadable_never_none(self, db, store):
        _write, _read, path = CASES[store]
        db["values"][f"records_store_{store}"] = "postgres"
        db["values"]["records_db_port"] = 1
        got = RM.store_rows(store, path())
        assert got["state"] == "unreadable" and "the records database" in got["error"]
        with pytest.raises(records_db.Unavailable, match="did not accept the connection"):
            RM.store_append(store, path(), {"at": "x"})
        assert not os.path.exists(path()), "nothing fell back to the file"


class TestEachOwnerSaysAFailedRecord:
    """On a database that does not answer, each owner keeps its own contract."""

    @pytest.fixture
    def down(self, db):
        for store in CASES:
            db["values"][f"records_store_{store}"] = "postgres"
        db["values"]["records_db_port"] = 1
        return db

    def test_a_reveal_is_not_blocked_and_says_it_was_not_recorded(self, down):
        got = reveal_audit.record(actor="alex@example.com", kind="person", what="golden_config",
                                  target="r1")
        assert got["recorded"] is False
        assert reveal_audit.read()["state"] == "unreadable"

    def test_host_steps_say_unreadable_and_a_done_raises(self, down):
        assert "__unreadable__" in host_steps.done_records()
        with pytest.raises(records_db.Unavailable):
            host_steps.record_done("a" * 40, "step", "alex@example.com")

    def test_a_heartbeat_record_says_it_cannot_be_read(self, down):
        assert heartbeat_windows.records()["error"].startswith("the record cannot be read")
        assert "error" in heartbeat_windows.last_written()

    def test_the_alert_history_records_nothing_and_says_why(self, down):
        from tests.test_alert_history import ann, load
        got = alert_history.record([alert_history.from_annotation(
            ann(load("annotations_72h"), 17895), "grafana-alerts")])
        assert got["ok"] is False and "cannot be read" in got["error"] and got["added"] == 0
        assert alert_history.read()["state"] == "unreadable"

    def test_a_pack_says_it_was_not_kept_and_none_is_built_blind(self, down):
        _write, _read, _path = CASES["evidence_packs"]
        got = evidence_pack.record({"id": "ep-x", "alert_key": "x"})
        assert got["ok"] is False and got["error"]
        assert evidence_pack.read()["state"] == "unreadable"
        assert evidence_pack.known_keys() is None

    def test_a_removal_record_says_it_was_not_written(self, down):
        got = netbox_guard.record_removal("Default", "alex@example.com", {"ok": True})
        assert got["ok"] is False and got["error"]
        assert netbox_guard.read_removals()["state"] == "unreadable"


class TestTheSeamOnFiles:
    def test_absent_unreadable_and_ok_differ(self, db, tmp_path):
        path = str(tmp_path / "logs" / "x.jsonl")
        assert RM.store_rows("reveals", path)["state"] == "absent"
        RM.store_append("reveals", path, {"a": 1})
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600, "owner-only from creation"
        assert RM.store_rows("reveals", path) == {"state": "ok", "rows": [{"a": 1}], "error": ""}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("{torn\n")
        assert RM.store_rows("reveals", path)["state"] == "unreadable"
        assert RM.store_rows("reveals", path, skip_unparsable=True)["rows"] == [{"a": 1}]

    def test_an_append_takes_the_file_s_cross_process_lock(self, db, tmp_path, monkeypatch):
        from modules import filestore

        held = []
        real = filestore.PathLock

        class Spy(real):
            def __enter__(self):
                held.append(self.path())
                return super().__enter__()
        monkeypatch.setattr(filestore, "PathLock", Spy)
        path = str(tmp_path / "y.jsonl")
        RM.store_append("reveals", path, {"a": 1})
        assert held == [path]
