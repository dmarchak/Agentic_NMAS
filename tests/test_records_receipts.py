"""Deploy receipts on the records database (Phase 4, docs/NSOT_PHASE4_RECORDS_POSTGRES.md
section 7): the store's PostgreSQL backend, the move from the files and back, and the check,
against a REAL PostgreSQL shaped as host step 6a makes it (tests/pg_instance.py; skipped with
its reason here, a failure in CI).

The receipt lines are made by the receipts module's own builders (`rows_for`, `pending_row`,
`completion`) from a deploy result shaped as `_deploy_one` returns it, with the three kinds the
host's file holds: rows, completions filling in a pending row's commit, and a row written before
commit states existed.
"""

import json
import os
import stat

import pytest

from modules import records_db, records_migrate as RM
from modules.nsot import receipts
from tests.test_deploy_receipts import _rows, _sent
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

# About the real path: each test's `db` fixture points the lists folder at its own.
pytestmark = pytest.mark.real_receipts_path


@pytest.fixture(scope="module")
def pg():
    from tests import pg_instance

    inst = pg_instance.start()
    yield inst
    inst.stop()


@pytest.fixture
def db(pg, tmp_path, monkeypatch):
    """The settings pointed at the real server, receipts on files; the data folder this
    test's own; the table dropped first."""
    from tests import pg_instance

    values = {"records_db_host": "127.0.0.1", "records_db_port": pg.port,
              "records_db_name": "mercury", "records_db_user": "mercury",
              "records_store_receipts": "file"}
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: values.get(key, default))
    monkeypatch.setattr("modules.secrets_store.get_secret",
                        lambda key, default="": pg_instance.MERCURY_PW
                        if key == "records_db_password" else default)
    monkeypatch.setattr("modules.secrets_store.is_set", lambda key: True)
    written = []

    def write_settings(changes, actor=""):
        values.update(changes)
        written.append((dict(changes), actor))
        return {"ok": True, "error": ""}
    monkeypatch.setattr("modules.settings_schema.write_settings", write_settings)
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path / "lists"))
    with pg.connect() as c:
        c.execute("drop schema if exists audit cascade")
    return {"values": values, "written": written, "pg": pg, "tmp": tmp_path}


def _file_with_every_kind(list_name="Default"):
    """A network's receipts file as deploys write it: two finished rows, a pending row and its
    completion, a refused row, and a row from before commit states (no `commit_state`)."""
    finished = _rows([_sent(), _sent(device="r4")])
    pending = receipts.pending_row(_sent(device="r5"), list_name=list_name, action="deploy",
                                   actor="test-person@example.invalid", actor_kind="person",
                                   run_id="run-1")
    final = dict(pending, commit_state=receipts.COMMITTED, golden_commit="def456",
                 batch_id="b-2")
    refused = _rows([_sent(device="r6", outcome="refused", commands=[])])
    legacy = dict(_rows([_sent(device="r7")])[0])
    legacy.pop("commit_state")
    lines = finished + [pending, receipts.completion(final, pending["id"])] + refused + [legacy]
    os.makedirs(os.path.dirname(receipts.path_for(list_name)), exist_ok=True)
    assert receipts.write(list_name, lines)["ok"]
    return lines


def _move(**kw):
    return RM.move(RM.plan()["fingerprint"], "test-person@example.invalid", "verified", **kw)


class TestTheBackend:
    def test_the_merge_is_equal_on_both_backends(self, db):
        _file_with_every_kind()
        on_files = receipts.read("Default", limit=10 ** 6)
        assert on_files["state"] == "ok" and len(on_files["rows"]) == 5
        got = _move()
        assert got["ok"], got
        assert receipts.on_database()
        on_db = receipts.read("Default", limit=10 ** 6)
        assert on_db == on_files
        pending = next(r for r in on_db["rows"] if r["device"] == "r5")
        assert pending["commit_state"] == "committed" and pending["golden_commit"] == "def456"
        legacy = next(r for r in on_db["rows"] if r["device"] == "r7")
        assert legacy["commit_state"] == "committed"

    def test_a_write_on_the_database_is_one_transaction(self, db):
        _file_with_every_kind()
        assert _move()["ok"]
        before = len(RM.table_lines("Default"))
        good = _rows([_sent(device="r8")])[0]
        bad = dict(good, id="x", reason="a NUL \u0000 jsonb refuses")
        got = receipts.write("Default", [good, bad])
        assert got["ok"] is False and "records database" in got["error"]
        assert len(RM.table_lines("Default")) == before, "the first line was not kept alone"
        assert receipts.write("Default", [good])["ok"]
        assert len(RM.table_lines("Default")) == before + 1

    def test_a_database_that_does_not_answer_reads_unreadable_naming_why(self, db):
        _file_with_every_kind()
        assert _move()["ok"]
        db["values"]["records_db_port"] = 1
        got = receipts.read("Default")
        assert got["state"] == "unreadable" and "did not accept the connection" in got["error"]

    def test_a_network_with_no_line_is_absent(self, db):
        _file_with_every_kind()
        assert _move()["ok"]
        assert receipts.read("Other")["state"] == "absent"


class TestTheMove:
    def test_two_identical_lines_stay_two(self, db):
        row = _rows([_sent()])[0]
        os.makedirs(os.path.dirname(receipts.path_for("Default")), exist_ok=True)
        assert receipts.write("Default", [row, row])["ok"]
        assert _move()["ok"]
        assert len(RM.table_lines("Default")) == 2

    def test_a_changed_line_is_refused_naming_both_hashes(self, db):
        lines = _file_with_every_kind()
        with db["pg"].connect() as conn:
            RM.ensure_schema(conn)
            conn.commit()
            RM.copy(conn)
        path = receipts.path_for("Default")
        texts = open(path).read().splitlines()
        texts[1] = receipts.encode(dict(lines[1], reason="changed after the copy"))
        open(path, "w").write("\n".join(texts) + "\n")
        with db["pg"].connect() as conn, pytest.raises(RM.Refused) as exc:
            RM.copy(conn)
        msg = str(exc.value)
        assert "default: line 2" in msg and msg.count("sha256") == 1 and "table holds" in msg
        assert RM.sha(texts[1]).hex()[:16] in msg

    def test_copying_again_skips_what_is_there(self, db):
        _file_with_every_kind()
        with db["pg"].connect() as conn:
            RM.ensure_schema(conn)
            conn.commit()
            first = RM.copy(conn)
            again = RM.copy(conn)
        assert first["default"] == {"copied": 6, "skipped": 0}
        assert again["default"] == {"copied": 0, "skipped": 6}

    def test_the_move_switches_records_it_and_makes_the_files_read_only(self, db):
        _file_with_every_kind()
        got = _move()
        assert got["ok"] and [s["name"] for s in got["steps"]] == list(RM.MOVE_STEPS)
        assert db["written"] == [({"records_store_receipts": "postgres"},
                                  "test-person@example.invalid")]
        mode = stat.S_IMODE(os.stat(receipts.path_for("Default")).st_mode)
        assert mode == 0o400
        from modules import installation_settings as IS
        rec = IS.changes(kinds=("records_store_move",))
        assert rec["state"] == "ok" and rec["rows"][0]["actor"] == "test-person@example.invalid"
        assert "default: file 6 lines, table 6, merged 5 = 5" in got["check"]["words"]

    def test_a_moved_preview_is_refused_naming_both(self, db):
        _file_with_every_kind()
        old = RM.plan()["fingerprint"]
        receipts.write("Default", _rows([_sent(device="r9")]))
        with pytest.raises(RM.Refused) as exc:
            RM.move(old, "test-person@example.invalid", "verified")
        assert f"preview {old}" in str(exc.value) and "now " in str(exc.value)
        assert db["written"] == [] and not receipts.on_database()

    def test_a_database_that_does_not_answer_refuses_before_anything(self, db):
        _file_with_every_kind()
        db["values"]["records_db_port"] = 1
        p = RM.plan()
        assert p["db"]["ok"] is False and p["networks"][0]["copied"] is None
        with pytest.raises(RM.Refused) as exc:
            RM.move(p["fingerprint"], "test-person@example.invalid", "verified")
        assert "does not answer" in str(exc.value) and db["written"] == []

    def test_a_failed_check_after_the_switch_switches_back(self, db, monkeypatch):
        _file_with_every_kind()
        monkeypatch.setattr(RM, "check", lambda connector=None: {
            "ok": False, "networks": [], "words": "default: file 7 lines, table 6: planted"})
        got = _move()
        assert got["ok"] is False and got["switched_back"] is not None
        assert not receipts.on_database()
        assert [c[0] for c in db["written"]] == [{"records_store_receipts": "postgres"},
                                                 {"records_store_receipts": "file"}]
        assert stat.S_IMODE(os.stat(receipts.path_for("Default")).st_mode) == 0o600


class TestTheCheck:
    def _moved(self, db):
        _file_with_every_kind()
        assert _move()["ok"]
        path = receipts.path_for("Default")
        os.chmod(path, 0o600)
        return path

    def test_it_passes_when_both_hold_the_same(self, db):
        self._moved(db)
        got = RM.check()
        assert got["ok"] and got["networks"][0]["merged"] == [5, 5]

    def test_a_moved_count_fails_naming_both(self, db):
        path = self._moved(db)
        with open(path, "a") as fh:
            fh.write(receipts.encode(_rows([_sent(device="r9")])[0]) + "\n")
        got = RM.check()
        assert got["ok"] is False
        assert got["networks"][0]["differs"] == "line 7 is in the file and not in the table"
        assert "file 7 lines, table 6" in got["words"]

    def test_a_changed_line_fails_naming_it(self, db):
        path = self._moved(db)
        texts = open(path).read().splitlines()
        texts[0] = texts[0].replace('"r3"', '"r3x"')
        open(path, "w").write("\n".join(texts) + "\n")
        got = RM.check()
        assert got["ok"] is False and got["networks"][0]["differs"].startswith("line 1 differs")

    def test_a_merged_difference_fails(self, db):
        """The table's body changed under an unchanged hash: only the merge sees it."""
        self._moved(db)
        with db["pg"].connect() as c:
            c.execute("update audit.receipt_lines set body = jsonb_set(body, '{outcome}', "
                      "'\"failed\"') where source_line = 1")
        got = RM.check()
        assert got["ok"] is False and got["networks"][0]["differs"].startswith(
            "the merged receipts differ from row")


class TestTheMoveBack:
    def test_back_exports_what_was_written_since_and_reads_the_same(self, db):
        _file_with_every_kind()
        assert _move()["ok"]
        assert receipts.write("Default", _rows([_sent(device="r9")]))["ok"]
        on_db = receipts.read("Default", limit=10 ** 6)
        got = RM.move_back(RM.plan()["fingerprint"], "test-person@example.invalid", "verified")
        assert got["ok"], got
        assert [s["name"] for s in got["steps"]] == list(RM.BACK_STEPS)
        assert "default: 1 line(s)" in got["steps"][1]["detail"]
        assert not receipts.on_database()
        assert receipts.read("Default", limit=10 ** 6) == on_db
        assert stat.S_IMODE(os.stat(receipts.path_for("Default")).st_mode) == 0o600
        # Moved again, the exported line is copied once, never twice.
        assert _move()["ok"]
        assert len(RM.table_lines("Default")) == 7
        assert receipts.read("Default", limit=10 ** 6) == on_db

    def test_back_is_refused_when_the_store_is_on_files(self, db):
        _file_with_every_kind()
        with pytest.raises(RM.Refused) as exc:
            RM.move_back(RM.plan()["fingerprint"], "test-person@example.invalid", "verified")
        assert "on file now, not postgres" in str(exc.value)


@pytest.fixture
def app_db(networks, pg):
    """The real app on a temporary store (tests/test_settings_v2's `networks`), its records
    database saved and its password replaced through the card's own routes, and Default's
    receipts file written; the table dropped first."""
    from tests import pg_instance

    with pg.connect() as c:
        c.execute("drop schema if exists audit cascade")
    _post(networks, "/v2/settings/installation/records/save",
          {"records_db_host": "127.0.0.1", "records_db_port": str(pg.port),
           "records_db_name": "mercury", "records_db_user": "mercury"})
    _r, html = _post(networks, "/v2/settings/installation/records/replace",
                     {"records_db_password": pg_instance.MERCURY_PW})
    assert "Test passed" in html
    _file_with_every_kind()
    return networks


def _post(n, path, data=None):
    r = n["client"].post(path, data=data or {}, headers={"HX-Request": "true"})
    return r, r.get_data(as_text=True)


def _stores(html):
    import re

    m = re.search(r'<section class="card set-card[^"]*" id="records-stores".*?</section>', html,
                  re.S)
    assert m, "no record stores section"
    return re.sub(r"\s+", " ", m.group(0))


def _fingerprint(html):
    import re

    return re.search(r'name="fingerprint" value="([0-9a-f]+)"', html).group(1)


class TestTheCard:
    def test_the_connections_tab_draws_the_stores_on_files(self, app_db):
        html = app_db["client"].get("/v2/settings/installation").get_data(as_text=True)
        s = _stores(html)
        assert "Deploy receipts" in s and "its files" in s and "Move to the database…" in s
        assert "0 of 1 on the database" in s
        assert 'hx-trigger="nmas:records from:body' in s

    def test_the_preview_counts_every_network_and_writes_nothing(self, app_db):
        r, html = _post(app_db, "/v2/settings/installation/records/stores/move/preview")
        s = _stores(html)
        assert r.status_code == 200 and "Move deploy receipts to the records database" in s
        assert "<td class=\"mono\">default</td><td>6</td><td>5</td><td>1</td><td>0</td>" in s
        assert "Move 6 lines" in s and "hx-trigger" not in s.split(">", 1)[0]
        assert not receipts.on_database()

    def test_the_move_from_the_card_switches_and_draws_each_step(self, app_db):
        _r, pv = _post(app_db, "/v2/settings/installation/records/stores/move/preview")
        r, html = _post(app_db, "/v2/settings/installation/records/stores/move",
                        {"fingerprint": _fingerprint(pv)})
        s = _stores(html)
        assert r.status_code == 200 and "Moved:" in s, s
        assert s.count(">pass<") == len(RM.MOVE_STEPS) and "FAILS" not in s
        assert receipts.on_database()
        page = _stores(app_db["client"].get("/v2/settings/installation").get_data(as_text=True))
        assert "Move back to files…" in page and "1 of 1 on the database" in page

    def test_a_moved_preview_is_refused_and_nothing_changes(self, app_db):
        _r, pv = _post(app_db, "/v2/settings/installation/records/stores/move/preview")
        receipts.write("Default", _rows([_sent(device="r9")]))
        r, html = _post(app_db, "/v2/settings/installation/records/stores/move",
                        {"fingerprint": _fingerprint(pv)})
        assert r.status_code == 409 and "Not moved:" in html and "preview again" in html
        assert not receipts.on_database()

    def test_an_unknown_direction_is_a_404_naming_both(self, app_db):
        r, html = _post(app_db, "/v2/settings/installation/records/stores/sideways/preview")
        assert r.status_code == 404 and "move or back" in html


class TestTheReaderAndNeedsAttention:
    def test_on_files_the_reader_says_nothing_to_compare(self, db):
        from modules.readers import records_check

        _file_with_every_kind()
        got = records_check.read()
        assert got["check"] is None and got["files"] == {"default": 6}

    def test_on_the_database_the_reader_runs_the_check(self, db):
        from modules.readers import records_check

        _file_with_every_kind()
        assert _move()["ok"]
        got = records_check.read()
        assert got["check"]["ok"] and got["backend"] == "postgres"

    def _cached(self, value, attempt_ok=True, error=""):
        return {"state": "ok", "doc": {
            "last_good": {"value": value, "value_at": "2026-10-10T03:00:00Z"},
            "last_attempt": {"at": "2026-10-10T03:05:00Z", "ok": attempt_ok, "error": error},
            "stale_after_seconds": 900}}

    def test_a_mismatch_is_a_row_naming_the_network_and_both_counts(self, db):
        from modules import attention

        db["values"]["records_store_receipts"] = "postgres"
        value = {"backend": "postgres", "files": {"default": 7}, "check": {
            "ok": False, "words": "x", "networks": [
                {"network": "default", "file": 7, "table": 6, "merged": [5, 5], "ok": False,
                 "differs": "line 7 is in the file and not in the table"}]}}
        got = attention.records_source(cached=self._cached(value))
        (row,) = got["rows"]
        assert row["kind"] == "mismatch" and row["level"] == "danger"
        assert "default: file 7 lines, table 6: line 7 is in the file" in row["cause"]

    def test_a_database_that_does_not_answer_is_a_row(self, db):
        from modules import attention

        db["values"]["records_store_receipts"] = "postgres"
        got = attention.records_source(cached=self._cached(
            {"backend": "postgres", "files": {}, "check": {"ok": True, "networks": []}},
            attempt_ok=False, error="connection refused"))
        (row,) = got["rows"]
        assert row["kind"] == "unreachable" and "connection refused" in row["cause"]
        assert "Receipts" not in row["what"] and "receipts cannot be written" in row["what"]

    def test_on_files_there_is_no_row(self, db):
        from modules import attention

        got = attention.records_source(cached=self._cached(
            {"backend": "file", "files": {}, "check": None}, attempt_ok=False, error="x"))
        assert got["rows"] == [] and "nothing to compare" in got["checked"]


def test_only_one_move_at_a_time(db):
    _file_with_every_kind()
    with RM._Lock():
        with pytest.raises(RM.Refused) as exc:
            _move()
    assert "another move" in str(exc.value)


def test_the_backend_reads_anything_but_postgres_as_file(db):
    db["values"]["records_store_receipts"] = "something else"
    assert records_db.backend("receipts") == "file" and records_db.stores() == []
    db["values"]["records_store_receipts"] = "postgres"
    assert records_db.stores() == ["receipts"]
    assert json.loads(receipts.encode({"b": 1, "a": 2})) == {"a": 2, "b": 1}
