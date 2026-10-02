"""C324 (2026-10-02, found drafting the Backups manual page): a backup name a request
supplies is resolved by ONE function, ``backups.backup_path()``, which refuses a name that is
not a backup's own and a real path outside the list's backups folder.

Before: ``POST /compare_backups`` (ungated: ``not_device``) joined the form's names onto the
folder unchecked, so ``../../key.key`` returned the Fernet key, and an absolute path returned
any file the service could read; masking cannot recognise a key or a ciphertext. Each probe
here drives the real route; the control compares two real backups.
"""

import os

import pytest

from modules import backups as B

SECRET = "Zq7NotABackupButAKeyFile91"


@pytest.fixture
def folder(monkeypatch, tmp_path):
    bdir = tmp_path / "lists" / "lab" / "backups"
    bdir.mkdir(parents=True)
    monkeypatch.setattr(B, "get_backups_dir", lambda: str(bdir))
    (tmp_path / "lists" / "key.key").write_text(SECRET)
    (tmp_path / "outside.cfg").write_text(SECRET)
    os.symlink(str(tmp_path / "outside.cfg"), str(bdir / "r1_192.0.2.1_running_20261001_000000.cfg"))
    (bdir / "r2_192.0.2.2_running_20261001_000000.cfg").write_text("hostname r2\nend\n")
    (bdir / "r2_192.0.2.2_running_20261002_000000.cfg").write_text("hostname r2\nntp server 192.0.2.9\nend\n")
    return tmp_path


def _client():
    import app as A
    return A.app.test_client()


@pytest.mark.parametrize("name", [
    "../../key.key", "../key.key", "/etc/passwd", "..", ".", "",
    "r2_192.0.2.2_running_20261001_000000.cfg/../../key.key", ".hidden.cfg", "a\\..\\b.cfg"])
def test_a_name_that_is_not_a_backup_is_refused(folder, name):
    assert B.backup_path(name) is None
    assert B.get_backup_content(name) is None


def test_a_symlink_inside_the_folder_pointing_out_is_refused(folder):
    assert B.get_backup_content("r1_192.0.2.1_running_20261001_000000.cfg") is None


def test_a_real_backup_resolves(folder):
    assert "hostname r2" in B.get_backup_content("r2_192.0.2.2_running_20261001_000000.cfg")


@pytest.mark.parametrize("name", ["../../key.key", "/etc/hostname", "../../../outside.cfg"])
def test_compare_returns_nothing_outside_the_folder(folder, name):
    r = _client().post("/compare_backups", data={
        "file1": name, "file2": "r2_192.0.2.2_running_20261001_000000.cfg"})
    assert r.status_code == 404
    assert SECRET not in r.get_data(as_text=True)


def test_compare_of_two_real_backups_still_works(folder):
    r = _client().post("/compare_backups", data={
        "file1": "r2_192.0.2.2_running_20261001_000000.cfg",
        "file2": "r2_192.0.2.2_running_20261002_000000.cfg"})
    assert r.status_code == 200 and "ntp server" in r.get_json()["diff"]


def test_delete_refuses_a_name_outside_the_folder(folder):
    assert B.delete_backup("../../key.key") is False
    assert (folder / "lists" / "key.key").exists()
