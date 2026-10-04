"""The Oxidized helper edits ONE router.db and keeps few backups (the operator's review of
c2440a6, 2026-10-04).

C414: `scripts/nmas-oxidized-cred` runs as root through one sudoers entry and took `--file`
from the unprivileged app. As root it now acts only on the path the root-owned
`/etc/nmas/oxidized-cred.conf` names, refusing any other and naming both. Not as root it holds
no privilege its caller lacks, so the pin is not asked (which is also how the subprocess tests
run it). Root is stood in for by calling the script's own functions with ``euid=0`` and the
test's uid as the trusted owner; `main()` is driven the same way with `os.geteuid` patched.

C415: each write's backup holds every password at that moment. After a successful write the
helper keeps the newest three (`KEEP_BACKUPS`: a rotation and its rollback are two writes,
and one more for a mistake found a write late) and removes the older ones; a file that does
not have a backup's exact name is never touched.

The app side reads the pin (0644) as its own user: `helper_status` says `unpinned` with the
command that installs it, so the rotation's preflight refuses, job health's row names it, and
the `[oxidized-cred]` host-step check is not done until it is right.
"""

import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys

import pytest

HELPER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "nmas-oxidized-cred")
ROWS = "192.0.2.11:ios:admin:OldPassword1\n192.0.2.12:ios:admin:OldPassword1\n"
ME = os.getuid()


@pytest.fixture
def helper():
    loader = importlib.machinery.SourceFileLoader("nmas_oxidized_cred_pin", HELPER)
    spec = importlib.util.spec_from_loader("nmas_oxidized_cred_pin", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "router.db"
    path.write_text(ROWS, encoding="utf-8")
    return path


def _pin(tmp_path, *lines, mode=0o644):
    pin = tmp_path / "oxidized-cred.conf"
    pin.write_text("".join(f"{l}\n" for l in lines), encoding="utf-8")
    os.chmod(pin, mode)
    return pin


# ------------------------------------------------------------------ C414, the pin

class TestAsRootItActsOnlyOnThePinnedFile:
    def test_the_pinned_file_is_the_one_acted_on(self, helper, tmp_path, db):
        pin = _pin(tmp_path, "# the one router.db", str(db))
        assert helper.pinned_path(str(db), euid=0, pin=str(pin), trusted_uid=ME) == str(db)

    def test_another_file_is_refused_naming_both(self, helper, tmp_path, db):
        other = tmp_path / "shadow"
        other.write_text(ROWS, encoding="utf-8")
        pin = _pin(tmp_path, str(db))
        with pytest.raises(ValueError) as got:
            helper.pinned_path(str(other), euid=0, pin=str(pin), trusted_uid=ME)
        assert f"--file {other} is not the pinned router.db {db} (from {pin})" in str(got.value)

    def test_a_link_to_the_pinned_file_acts_on_the_file_never_the_link(self, helper, tmp_path,
                                                                        db):
        link = tmp_path / "link.db"
        link.symlink_to(db)
        pin = _pin(tmp_path, str(link))
        got = helper.pinned_path(str(db), euid=0, pin=str(pin), trusted_uid=ME)
        assert got == os.path.realpath(db)

    def test_no_pin_refuses_every_write(self, helper, tmp_path, db):
        with pytest.raises(ValueError, match="no router.db is pinned"):
            helper.pinned_path(str(db), euid=0, pin=str(tmp_path / "absent"), trusted_uid=ME)

    def test_a_pin_another_user_owns_is_refused(self, helper, tmp_path, db):
        pin = _pin(tmp_path, str(db))
        with pytest.raises(ValueError, match=f"owner uid {ME}"):
            helper.pinned_path(str(db), euid=0, pin=str(pin), trusted_uid=ME + 1)

    @pytest.mark.parametrize("mode", [0o664, 0o646])
    def test_a_pin_others_can_write_is_refused(self, helper, tmp_path, db, mode):
        pin = _pin(tmp_path, str(db), mode=mode)
        with pytest.raises(ValueError, match="writable by no one else"):
            helper.pinned_path(str(db), euid=0, pin=str(pin), trusted_uid=ME)

    def test_a_pin_that_is_a_link_is_refused(self, helper, tmp_path, db):
        real = _pin(tmp_path, str(db))
        link = tmp_path / "pin-link"
        link.symlink_to(real)
        with pytest.raises(ValueError, match="not a regular file"):
            helper.pinned_path(str(db), euid=0, pin=str(link), trusted_uid=ME)

    @pytest.mark.parametrize("lines", [(), ("/a/router.db", "/b/router.db"), ("router.db",)])
    def test_a_pin_naming_other_than_one_absolute_path_is_refused(self, helper, tmp_path, db,
                                                                   lines):
        pin = _pin(tmp_path, *lines)
        with pytest.raises(ValueError, match="exactly one absolute path"):
            helper.pinned_path(str(db), euid=0, pin=str(pin), trusted_uid=ME)

    def test_not_as_root_the_pin_is_not_asked(self, helper, tmp_path, db):
        assert helper.pinned_path(str(db), euid=ME or 1000,
                                  pin=str(tmp_path / "absent")) == str(db)

    def test_the_helper_and_the_app_name_one_pin(self, helper):
        from modules.nsot import credential_rotation as cr
        assert helper.PIN == cr.HELPER_PIN == "/etc/nmas/oxidized-cred.conf"
        assert helper.TRUSTED_UID == 0


def _main_as_root(helper, monkeypatch, argv, stdin=""):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["nmas-oxidized-cred", *argv])
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    try:
        helper.main()
    except SystemExit:
        pass
    return json.loads(out.getvalue())


class TestMainAsRoot:
    def test_a_write_to_another_file_is_refused_and_nothing_changes(self, helper, monkeypatch,
                                                                    tmp_path, db):
        other = tmp_path / "shadow"
        other.write_text(ROWS, encoding="utf-8")
        helper.PIN, helper.TRUSTED_UID = str(_pin(tmp_path, str(db))), ME
        got = _main_as_root(helper, monkeypatch, ["--file", str(other), "--ip", "192.0.2.12"],
                            json.dumps({"username": "admin", "password": "NewPassword2"}))
        assert got["ok"] is False and "is not the pinned router.db" in got["error"]
        assert other.read_text(encoding="utf-8") == ROWS

    def test_a_write_to_the_pinned_file_lands(self, helper, monkeypatch, tmp_path, db):
        helper.PIN, helper.TRUSTED_UID = str(_pin(tmp_path, str(db))), ME
        got = _main_as_root(helper, monkeypatch, ["--file", str(db), "--ip", "192.0.2.12"],
                            json.dumps({"username": "admin", "password": "NewPassword2"}))
        assert got["ok"] is True and got["changed"] == 1
        assert "192.0.2.12:ios:admin:NewPassword2" in db.read_text(encoding="utf-8")

    def test_the_addresses_read_is_pinned_too(self, helper, monkeypatch, tmp_path, db):
        other = tmp_path / "shadow"
        other.write_text(ROWS, encoding="utf-8")
        helper.PIN, helper.TRUSTED_UID = str(_pin(tmp_path, str(db))), ME
        got = _main_as_root(helper, monkeypatch, ["--file", str(other), "--addresses"])
        assert got["ok"] is False and "is not the pinned router.db" in got["error"]

    def test_no_backup_is_refused_as_root(self, helper, monkeypatch, tmp_path, db):
        helper.PIN, helper.TRUSTED_UID = str(_pin(tmp_path, str(db))), ME
        got = _main_as_root(helper, monkeypatch,
                            ["--file", str(db), "--ip", "192.0.2.12", "--no-backup"],
                            json.dumps({"username": "admin", "password": "NewPassword2"}))
        assert got["ok"] is False and "--no-backup is for tests only" in got["error"]
        assert db.read_text(encoding="utf-8") == ROWS


# ------------------------------------------------------------------ C415, few backups

def _backups(db):
    return sorted(p.name for p in db.parent.iterdir() if p.name.startswith("router.db.nmas-bak"))


def _write(db, *flags, password="NewPassword2", ip="192.0.2.12"):
    proc = subprocess.run([sys.executable, HELPER, "--file", str(db), "--ip", ip, *flags],
                          input=json.dumps({"username": "admin", "password": password}),
                          capture_output=True, text=True, timeout=30)
    return json.loads(proc.stdout)


class TestOnlyTheNewestBackupsAreKept:
    OLD = ["router.db.nmas-bak-20260901-000000", "router.db.nmas-bak-20260902-000000",
           "router.db.nmas-bak-20260903-000000", "router.db.nmas-bak-20260904-000000",
           "router.db.nmas-bak-20260905-000000"]

    def _old(self, db):
        for name in self.OLD:
            (db.parent / name).write_text(ROWS, encoding="utf-8")

    def test_a_write_keeps_three_its_own_among_them(self, db):
        self._old(db)
        got = _write(db)
        assert got["ok"] is True and got["backups_removed"] == 3
        kept = _backups(db)
        assert len(kept) == 3 and os.path.basename(got["backup"]) in kept
        assert kept[:2] == self.OLD[-2:]

    def test_a_removal_prunes_too(self, db):
        self._old(db)
        proc = subprocess.run([sys.executable, HELPER, "--file", str(db), "--ip", "192.0.2.12",
                               "--remove"], capture_output=True, text=True, timeout=30)
        got = json.loads(proc.stdout)
        assert got["removed"] == 1 and got["backups_removed"] == 3 and len(_backups(db)) == 3

    def test_a_file_without_a_backups_exact_name_is_never_touched(self, db):
        self._old(db)
        keep = ["router.db.nmas-bak-notes", "router.db.nmas-bak-20260901-000000.gz",
                "other.db.nmas-bak-20260901-000000"]
        for name in keep:
            (db.parent / name).write_text("x", encoding="utf-8")
        _write(db)
        assert all((db.parent / name).exists() for name in keep)

    def test_nothing_written_prunes_nothing(self, db):
        self._old(db)
        _write(db)
        before = _backups(db)
        got = _write(db)                              # already current: no write
        assert got.get("already_current") is True and _backups(db) == before

    def test_three_or_fewer_are_all_kept(self, db):
        (db.parent / self.OLD[0]).write_text(ROWS, encoding="utf-8")
        got = _write(db)
        assert got["backups_removed"] == 0 and len(_backups(db)) == 2

    def test_a_pruning_failure_is_said_and_the_write_stands(self, helper, tmp_path):
        got = helper.pruned(str(tmp_path / "gone" / "router.db"), "a-backup")
        assert got["backups_removed"] == 0 and "FileNotFoundError" in got["prune_error"]


# ------------------------------------------------------------------ the app reads the pin

class TestTheAppReadsThePin:
    def _as_root_owned(self, monkeypatch, path):
        real = os.lstat

        def lstat(p, *a, **k):
            st = real(p, *a, **k)
            if str(p) != str(path):
                return st
            fields = list(st)
            fields[4] = 0                              # st_uid
            return os.stat_result(fields)
        monkeypatch.setattr(os, "lstat", lstat)

    def test_a_pin_naming_the_setting_is_ok(self, monkeypatch, tmp_path, db):
        from modules.nsot import credential_rotation as cr
        pin = _pin(tmp_path, str(db))
        self._as_root_owned(monkeypatch, pin)
        got = cr.helper_pin_status(path=str(pin), router_db=str(db))
        assert got["ok"] is True, got

    def test_absent_names_what_it_must_name_and_the_command(self, tmp_path):
        from modules.nsot import credential_rotation as cr
        got = cr.helper_pin_status(path=str(tmp_path / "absent"), router_db="/srv/ox/router.db")
        assert got["ok"] is False and "refuses every write as root until it names " \
                                      "/srv/ox/router.db" in got["reason"]
        assert "printf '%s\\n' /srv/ox/router.db" in got["command"]
        assert "sudo install -o root -g root -m 0644 \"$d/oxidized-cred.conf\" " \
               "/etc/nmas/oxidized-cred.conf" in got["command"]
        assert "mktemp -d" in got["command"] and "*" not in got["command"]

    def test_a_pin_naming_another_file_names_both(self, monkeypatch, tmp_path, db):
        from modules.nsot import credential_rotation as cr
        pin = _pin(tmp_path, "/srv/elsewhere/router.db")
        self._as_root_owned(monkeypatch, pin)
        got = cr.helper_pin_status(path=str(pin), router_db=str(db))
        assert got["ok"] is False
        assert f"names /srv/elsewhere/router.db, and the setting oxidized_router_db is {db}" \
            in got["reason"]

    def test_a_pin_the_app_user_owns_is_not_trusted(self, tmp_path, db):
        from modules.nsot import credential_rotation as cr
        got = cr.helper_pin_status(path=str(_pin(tmp_path, str(db))), router_db=str(db))
        assert got["ok"] is False and f"owner uid {ME}" in got["reason"]

    def test_the_helpers_status_is_unpinned_until_the_pin_is_right(self, monkeypatch, tmp_path):
        """This release's copy, root-owned, and no pin: the rotation's preflight refuses."""
        import shutil

        from modules.nsot import credential_rotation as cr
        installed = tmp_path / "nmas-oxidized-cred"
        shutil.copy(HELPER, installed)
        os.chmod(installed, 0o755)
        real = os.stat

        def stat(p, *a, **k):
            st = real(p, *a, **k)
            if str(p) != str(installed):
                return st
            fields = list(st)
            fields[4] = 0
            return os.stat_result(fields)
        monkeypatch.setattr(os, "stat", stat)
        monkeypatch.setattr(cr, "HELPER_INSTALLED", str(installed))
        monkeypatch.setattr(cr, "HELPER_PIN", str(tmp_path / "absent.conf"))
        got = cr.helper_status()
        assert got["state"] == "unpinned" and got["ok"] is False
        assert "absent.conf is absent" in got["reason"]
        assert "oxidized-cred.conf" in got["reinstall"]

    def test_unpinned_is_job_healths_row_with_the_pin_command(self, monkeypatch):
        from modules import host_helpers
        from modules.nsot import credential_rotation as cr
        monkeypatch.setattr(cr, "helper_status", lambda: {
            "ok": False, "state": "unpinned", "reason": "/etc/nmas/oxidized-cred.conf is absent",
            "reinstall": cr.pin_command("/srv/ox/router.db")})
        row = host_helpers.oxidized_row()
        assert row["state"] == "differs" and row["action"]["label"].startswith("Pin the helper")
        assert "/etc/nmas/oxidized-cred.conf" in row["action"]["command"]

    def test_unpinned_is_not_done_for_the_host_step(self, monkeypatch):
        from modules import host_steps
        from modules.nsot import credential_rotation as cr
        monkeypatch.setattr(cr, "helper_status", lambda: {
            "ok": False, "state": "unpinned", "reason": "/etc/nmas/oxidized-cred.conf is absent"})
        got = host_steps.check({"check": "oxidized-cred"})
        assert got == {"state": "not_done", "detail": "/etc/nmas/oxidized-cred.conf is absent"}
