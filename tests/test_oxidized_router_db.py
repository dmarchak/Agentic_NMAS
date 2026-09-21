"""The router.db editor — the fifth scripted edit in this project.

Four have destroyed something: modules/nsot/deploy.py grew to 2.4MB of
recursion, a pruning script removed test class headers, a slice-to-EOF deleted
`_deploy_one`, and a regex `sub` that matched nothing reported success while a
follow-up `gsub` deleted two lines of Oxidized's config.

This one edits a file that is the only thing standing between Oxidized and
every device, holds every device password, and is not in any repository. So it
is a *tested* edit: backup, parse, change one row, write a temp file, validate
what was actually written, replace atomically.

The helper is driven as a subprocess deliberately. It is root-owned and must
not import from a user-writable path — a root script importing from a user's
home is a privilege escalation with extra steps — so there is one
implementation and the tests exercise that one.
"""

import json
import os
import subprocess
import sys

import pytest

HELPER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "nmas-oxidized-cred")

ROWS = [
    "10.255.1.11:ios:admin:OldPassword1",
    "10.255.1.12:ios:admin:OldPassword1",
    "10.255.1.21:ios:admin:OldPassword1",
]


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "router.db"
    path.write_text("\n".join(ROWS) + "\n", encoding="utf-8")
    return path


def run(db_path, ip, username="admin", password="NewPassword2", **kw):
    payload = json.dumps({"username": username, "password": password})
    proc = subprocess.run(
        [sys.executable, HELPER, "--file", str(db_path), "--ip", ip,
         *(["--no-backup"] if kw.get("no_backup") else [])],
        input=payload, capture_output=True, text=True)
    try:
        body = json.loads(proc.stdout or "{}")
    except ValueError:
        body = {"ok": False, "error": "non-JSON output", "raw": proc.stdout}
    return proc.returncode, body


def rows_of(db_path):
    return [l for l in db_path.read_text(encoding="utf-8").splitlines() if l.strip()]


class TestTheTargetRowAndOnlyIt:
    def test_the_target_row_changes(self, db):
        code, body = run(db, "10.255.1.12")
        assert code == 0 and body["ok"] is True
        assert body["changed"] == 1

        after = rows_of(db)
        assert "10.255.1.12:ios:admin:NewPassword2" in after

    def test_no_other_row_changes(self, db):
        before = rows_of(db)
        run(db, "10.255.1.12")
        after = rows_of(db)

        differing = [(b, a) for b, a in zip(before, after) if b != a]
        assert len(differing) == 1
        assert differing[0][0].startswith("10.255.1.12:")

    def test_the_row_count_and_order_are_preserved(self, db):
        before = rows_of(db)
        run(db, "10.255.1.21")
        after = rows_of(db)

        assert len(after) == len(before)
        assert [r.split(":")[0] for r in after] == [r.split(":")[0] for r in before]

    def test_the_model_column_survives(self, db):
        """Only the credentials change — not what Oxidized thinks the box is."""
        db.write_text("10.255.1.11:ios:admin:Old1\n"
                      "10.255.1.21:ios-xe:admin:Old1\n", encoding="utf-8")
        run(db, "10.255.1.11")
        assert "10.255.1.21:ios-xe:admin:Old1" in rows_of(db)


class TestItRefusesRatherThanGuessing:
    def test_an_absent_target_ip_is_refused(self, db):
        before = db.read_text(encoding="utf-8")
        code, body = run(db, "10.255.1.99")

        assert code == 1
        assert "not in router.db" in body["error"]
        assert db.read_text(encoding="utf-8") == before, "file must be untouched"

    def test_a_malformed_row_refuses_the_whole_edit(self, db):
        """Not skipped — a dropped line silently removes a device from harvest."""
        db.write_text("10.255.1.11:ios:admin:Old1\n"
                      "this-is-not-a-row\n"
                      "10.255.1.12:ios:admin:Old1\n", encoding="utf-8")
        before = db.read_text(encoding="utf-8")
        code, body = run(db, "10.255.1.11")

        assert code == 1
        assert "malformed" in body["error"]
        assert db.read_text(encoding="utf-8") == before

    def test_a_row_with_the_wrong_field_count_is_refused(self, db):
        db.write_text("10.255.1.11:ios:admin\n", encoding="utf-8")
        code, body = run(db, "10.255.1.11")
        assert code == 1
        assert "4 colon-separated fields" in body["error"]

    def test_a_non_ip_first_field_is_refused(self, db):
        db.write_text("not-an-ip:ios:admin:Old1\n", encoding="utf-8")
        code, body = run(db, "10.255.1.11")
        assert code == 1
        assert "not an IPv4 address" in body["error"]

    def test_a_password_containing_a_colon_is_refused(self, db):
        """router.db is colon-delimited; one colon would split the row."""
        before = db.read_text(encoding="utf-8")
        code, body = run(db, "10.255.1.12", password="has:colon")

        assert code == 1
        assert "':'" in body["error"]
        assert db.read_text(encoding="utf-8") == before

    def test_a_password_containing_a_newline_is_refused(self, db):
        code, body = run(db, "10.255.1.12", password="two\nlines")
        assert code == 1
        assert "newline" in body["error"]

    def test_an_empty_password_is_refused(self, db):
        code, body = run(db, "10.255.1.12", password="")
        assert code == 1
        assert "non-empty" in body["error"]

    def test_a_missing_file_is_refused(self, tmp_path):
        code, body = run(tmp_path / "nope.db", "10.255.1.12")
        assert code == 1
        assert "does not exist" in body["error"]


class TestSafetyOfTheWriteItself:
    def test_a_backup_is_taken(self, db):
        _code, body = run(db, "10.255.1.12")
        backup = body["backup"]
        assert backup and os.path.exists(backup)
        assert "OldPassword1" in open(backup, encoding="utf-8").read()

    def test_the_backup_is_owner_only(self, db):
        """It holds every device password."""
        _code, body = run(db, "10.255.1.12")
        mode = os.stat(body["backup"]).st_mode & 0o777
        assert mode == 0o600, oct(mode)

    def test_file_permissions_are_preserved(self, db):
        os.chmod(db, 0o600)
        run(db, "10.255.1.12")
        assert os.stat(db).st_mode & 0o777 == 0o600

    def test_no_credential_appears_in_the_output(self, db):
        proc = subprocess.run(
            [sys.executable, HELPER, "--file", str(db), "--ip", "10.255.1.12"],
            input=json.dumps({"username": "admin", "password": "SuperSecret9"}),
            capture_output=True, text=True)
        assert "SuperSecret9" not in proc.stdout
        assert "SuperSecret9" not in proc.stderr

    def test_the_password_is_never_in_argv(self):
        """argv is world-readable in /proc for the life of the process."""
        source = open(HELPER, encoding="utf-8").read()
        assert '"--password"' not in source
        assert "'--password'" not in source
        assert "json.load(sys.stdin)" in source

    def test_the_helper_imports_nothing_from_the_repo(self):
        """A root script importing from a user path is an escalation."""
        source = open(HELPER, encoding="utf-8").read()
        for bad in ("from modules", "import modules", "sys.path.insert"):
            assert bad not in source, bad

    def test_running_twice_is_idempotent_in_effect(self, db):
        run(db, "10.255.1.12", password="Same9Value")
        first = rows_of(db)
        code, body = run(db, "10.255.1.12", password="Same9Value")
        # The second run changes nothing, so "exactly one row differs" fails —
        # which is correct: it is a refusal to pretend work happened.
        assert code == 1
        assert "exactly one changed row" in body["error"]
        assert rows_of(db) == first
