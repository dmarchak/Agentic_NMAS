"""C1453's one-off on the lab host (lab/clab-sync/c1453-startup-files-owner-only.sh), run here
against a lab folder made to look as the lab host's did on 2026-10-20: the startup files and a
backup 0664, the backup untracked. It makes them owner-only, ignores the backups, deletes
nothing, and refuses a folder that is not a lab repository."""

import os
import stat
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "lab", "clab-sync", "c1453-startup-files-owner-only.sh")


def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          capture_output=True, text=True, check=True,
                          env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"})


def _lab(tmp_path):
    lab = tmp_path / "lab"
    (lab / "configs").mkdir(parents=True)
    for h in ("r1", "s1"):
        (lab / "configs" / f"{h}.cfg").write_text(f"hostname {h}\nend\n")
        os.chmod(lab / "configs" / f"{h}.cfg", 0o664)
    _git(lab, "init", "-q")
    _git(lab, "add", "-A")
    _git(lab, "commit", "-q", "-m", "init")
    bak = lab / "configs.bak-20261020-010700"
    bak.mkdir()
    (bak / "r1.cfg").write_text("hostname r1\nend\n")
    os.chmod(bak / "r1.cfg", 0o664)
    os.chmod(bak, 0o775)
    return lab


def _mode(p):
    return stat.S_IMODE(os.stat(p).st_mode)


def test_it_makes_the_files_and_backups_owner_only_and_ignores_the_backups(tmp_path):
    lab = _lab(tmp_path)
    got = subprocess.run(["bash", SCRIPT, str(lab)], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stdout + got.stderr
    assert "== RESULT: PASS" in got.stdout
    assert _mode(lab / "configs" / "r1.cfg") == 0o600 and _mode(lab / "configs" / "s1.cfg") == 0o600
    bak = lab / "configs.bak-20261020-010700"
    assert _mode(bak) & 0o077 == 0 and _mode(bak / "r1.cfg") & 0o077 == 0
    assert (bak / "r1.cfg").exists(), "nothing is deleted"
    assert "/configs.bak-*/" in (lab / ".gitignore").read_text().splitlines()
    assert "configs.bak-" not in _git(lab, "status", "--porcelain").stdout


def test_run_twice_it_changes_nothing_more(tmp_path):
    lab = _lab(tmp_path)
    for _ in range(2):
        got = subprocess.run(["bash", SCRIPT, str(lab)], capture_output=True, text=True,
                             timeout=60)
        assert got.returncode == 0, got.stdout
    lines = (lab / ".gitignore").read_text().splitlines()
    assert lines.count("/configs.bak-*/") == 1 and lines.count("/backup-*/") == 1


def test_a_folder_that_is_not_a_lab_repository_is_refused_untouched(tmp_path):
    lab = tmp_path / "notalab"
    (lab / "configs").mkdir(parents=True)
    (lab / "configs" / "r1.cfg").write_text("hostname r1\n")
    os.chmod(lab / "configs" / "r1.cfg", 0o664)
    got = subprocess.run(["bash", SCRIPT, str(lab)], capture_output=True, text=True, timeout=60)
    assert got.returncode == 2 and "REFUSED: " in got.stdout
    assert _mode(lab / "configs" / "r1.cfg") == 0o664
