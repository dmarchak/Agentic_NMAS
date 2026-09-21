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


class TestTheShebangIsPartOfTheSecurity:
    """A root-run script must not let its caller choose the interpreter."""

    def test_it_is_exactly_the_isolated_absolute_interpreter(self):
        first = open(HELPER, encoding="utf-8").readline().rstrip("\n")
        assert first == "#!/usr/bin/python3 -I", repr(first)

    def test_it_does_not_use_env(self):
        """`env` resolves through PATH, which the caller controls."""
        first = open(HELPER, encoding="utf-8").readline()
        assert "/usr/bin/env" not in first

    def test_isolated_mode_is_requested(self):
        """-I ignores PYTHON* and the CALLING user's site-packages.

        sudo's env_reset and secure_path give the same properties — but they
        are defaults in a file someone else maintains, and a script that is
        safe only while a sudoers option stays set is safe by coincidence.
        """
        assert open(HELPER, encoding="utf-8").readline().rstrip().endswith(" -I")

    def test_the_script_still_runs_under_that_interpreter(self, db):
        """The shebang has to be correct, not merely well-intentioned."""
        import stat
        os.chmod(HELPER, os.stat(HELPER).st_mode | stat.S_IXUSR)
        proc = subprocess.run(
            [HELPER, "--file", str(db), "--ip", "10.255.1.12", "--no-backup"],
            input=json.dumps({"username": "admin", "password": "NewPassword2"}),
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["ok"] is True

    def test_isolated_mode_actually_ignores_pythonpath(self, db, tmp_path):
        """Prove -I, rather than trusting the flag is spelled right.

        A module planted on PYTHONPATH that would break the script must have
        no effect.
        """
        evil = tmp_path / "evil"
        evil.mkdir()
        (evil / "json.py").write_text("raise RuntimeError('hijacked')\n",
                                      encoding="utf-8")
        proc = subprocess.run(
            [HELPER, "--file", str(db), "--ip", "10.255.1.12", "--no-backup"],
            input=json.dumps({"username": "admin", "password": "NewPassword2"}),
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(evil)})
        assert "hijacked" not in proc.stderr
        assert proc.returncode == 0, proc.stderr


class TestTheInstalledHelperMustMatchTheRepo:
    """The installed copy is a snapshot; the tests describe the repo copy.

    A repo whose tests pass while a different script runs as root is a test
    suite describing something that is not deployed.
    """

    def test_a_missing_install_is_refused_with_the_command(self, monkeypatch):
        from modules.nsot import credential_rotation as cr

        monkeypatch.setattr(cr, "HELPER_INSTALLED", "/nonexistent/nmas-helper")
        status = cr.helper_status()

        assert status["ok"] is False
        assert status["state"] == "not_installed"
        assert "sudo install -o root -g root -m 0755" in status["reinstall"]
        assert status["reinstall"].endswith("/nonexistent/nmas-helper")

    def test_drift_is_detected_and_named(self, tmp_path, monkeypatch):
        from modules.nsot import credential_rotation as cr

        fake = tmp_path / "installed"
        fake.write_text("# an older copy\n", encoding="utf-8")
        monkeypatch.setattr(cr, "HELPER_INSTALLED", str(fake))

        status = cr.helper_status()
        assert status["ok"] is False
        assert status["state"] == "drifted"
        assert "describe the repo copy" in status["reason"]
        assert status["installed_sha"] != status["source_sha"]

    def test_an_identical_copy_passes_the_hash_check(self, tmp_path,
                                                      monkeypatch):
        import shutil

        from modules.nsot import credential_rotation as cr

        fake = tmp_path / "installed"
        shutil.copyfile(HELPER, fake)
        monkeypatch.setattr(cr, "HELPER_INSTALLED", str(fake))

        status = cr.helper_status()
        # Ownership will not be root in a test, which is the next check —
        # but the hashes must match.
        assert status["installed_sha"] == status["source_sha"]
        assert status["state"] in ("ok", "not_root_owned")

    def test_a_world_writable_install_is_refused(self, tmp_path, monkeypatch):
        """A sudoers entry pointing at a writable file is a root shell."""
        import shutil

        from modules.nsot import credential_rotation as cr

        fake = tmp_path / "installed"
        shutil.copyfile(HELPER, fake)
        os.chmod(fake, 0o777)
        monkeypatch.setattr(cr, "HELPER_INSTALLED", str(fake))
        monkeypatch.setattr(os, "stat", os.stat)

        status = cr.helper_status()
        assert status["ok"] is False
        assert status["state"] in ("not_root_owned", "group_or_world_writable")


class TestTheReinstallHintNamesTheRightDestination:
    def test_it_follows_a_changed_install_path(self, monkeypatch):
        """Built at call time. Baking it in at import named the old path."""
        from modules.nsot import credential_rotation as cr

        monkeypatch.setattr(cr, "HELPER_INSTALLED", "/opt/custom/nmas-helper")
        assert cr.helper_status()["reinstall"].endswith("/opt/custom/nmas-helper")

class TestTheValueSurvivesTheHelperByteForByte:
    """The value reaching router.db must equal the value the verify proved.

    r2 was stranded with a correct credential, so nothing here was the cause —
    but nothing proved it *wasn't*, either. Establishing it took reading the
    file as root, which is not a check anyone will repeat. This runs the REAL
    helper as a subprocess and compares fingerprints across it, so the claim
    is a test rather than an afternoon.

    Every character of the charset goes through, which is also what catches a
    delimiter being added to the charset later: ':' would make the helper
    refuse, and that refusal lands after the device is already rotated.
    """

    def _run(self, tmp_path, password, ip="10.255.1.12"):
        import hashlib
        import json
        import subprocess

        db = tmp_path / "router.db"
        db.write_text(
            "10.255.1.11:ios:admin:oldone\n"
            f"{ip}:ios:admin:oldtwo\n"
            "10.255.1.13:ios:admin:oldthree\n", encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, HELPER, "--file", str(db), "--ip", ip,
             "--no-backup"],
            input=json.dumps({"username": "admin", "password": password}),
            capture_output=True, text=True, timeout=30)
        body = json.loads(proc.stdout or "{}")

        stored = None
        for line in db.read_text(encoding="utf-8").splitlines():
            if line.startswith(ip + ":"):
                stored = line.split(":")[3] if len(line.split(":")) > 3 else None
        fp = (hashlib.sha256(stored.encode()).hexdigest()[:12]
              if stored is not None else None)
        return body, stored, fp

    def test_every_charset_character_survives_byte_for_byte(self, tmp_path):
        import hashlib

        from modules.nsot.credential_rotation import CHARSET

        # Not a random sample: every character the generator can emit, in one
        # value, so a mangled one cannot hide behind a lucky draw.
        password = "".join(sorted(CHARSET))
        body, stored, fp = self._run(tmp_path, password)

        assert body.get("ok") is True, body
        assert stored == password, "the helper altered the value"
        assert fp == hashlib.sha256(password.encode()).hexdigest()[:12]

    def test_a_generated_password_survives_byte_for_byte(self, tmp_path):
        """The real generator's output, not a hand-written value."""
        import hashlib

        from modules.nsot import credential_rotation as cr

        for _ in range(25):
            password = cr.generate_password("r2")
            body, stored, fp = self._run(tmp_path, password)
            assert body.get("ok") is True, (body, len(password))
            assert stored == password
            assert fp == hashlib.sha256(password.encode()).hexdigest()[:12]

    def test_the_other_rows_are_untouched(self, tmp_path):
        from modules.nsot.credential_rotation import generate_password

        body, _stored, _fp = self._run(tmp_path, generate_password("r2"))
        assert body.get("changed") == 1
        assert body.get("rows") == 3

    def test_a_colon_is_refused_rather_than_corrupting_the_file(self, tmp_path):
        """The charset excludes it; this pins what happens if it returns."""
        body, stored, _fp = self._run(tmp_path, "has:a:colon:in:it")
        assert body.get("ok") is False
        assert "':'" in body.get("error", "")
        assert stored == "oldtwo", "the original row must be untouched"

    def test_whitespace_and_newlines_are_refused_or_preserved(self, tmp_path):
        """A trailing space would silently become a different password."""
        body, stored, _fp = self._run(tmp_path, "trailing ")
        if body.get("ok"):
            assert stored == "trailing ", "whitespace was stripped in transit"
        body, stored, _fp = self._run(tmp_path, "two\nlines")
        assert body.get("ok") is False
