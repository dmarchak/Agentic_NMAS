"""`scripts/nmas-stage-guard`: a staged secret or stray is refused before the
suite runs and before a commit (the operator, 2026-09-29).

The gate stages with `git add -A` into a PUBLIC repository, the unscoped add
that once committed clab-r6's CA private key. Every case here is a real
repository in a temporary directory, staged with `git add -A` as the gate
does. The private-key header is built by concatenation, so this file never
holds one itself.
"""

import os
import subprocess
from importlib.machinery import SourceFileLoader

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = SourceFileLoader("stage_guard", os.path.join(ROOT, "scripts", "nmas-stage-guard")).load_module()
KEY_BLOCK = "-----BEGIN " + "PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END " + "PRIVATE KEY-----\n"


def _git(repo, *args):
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@example.com", "-c", "user.name=T",
                    *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A repository whose HEAD has the tops docs/, tests/ and README.md."""
    r = str(tmp_path)
    _git(r, "init", "-q")
    for rel in ("docs/a.md", "tests/test_a.py", "README.md"):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("clean\n")
    (tmp_path / ".gitignore").write_text("ignored.key\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    return tmp_path


def _write(repo, rel, text="x\n"):
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    _git(str(repo), "add", "-A")


def _run(repo, *extra):
    return G.main(["--repo", str(repo), *extra])


class TestSecretsAreRefused:
    @pytest.mark.parametrize("rel", ["docs/lab.key", "tests/fixtures/ca.pem", "id_ed25519",
                                     "docs/.env", "docs/.env.local", "docs/rcn-breakglass.bg",
                                     "data/lab_hosts.json", "tests/key.key",
                                     "tests/credential_profiles.json", "docs/backup.gpg"])
    def test_a_secret_shaped_new_file_is_refused_by_name(self, repo, rel, capsys):
        _write(repo, rel)
        assert _run(repo) == 1
        assert rel in capsys.readouterr().err

    def test_a_private_key_block_in_an_ordinary_new_file_is_refused(self, repo, capsys):
        _write(repo, "docs/notes.md", "see below\n" + KEY_BLOCK)
        assert _run(repo) == 1
        assert "docs/notes.md: its staged content holds a private-key block" in capsys.readouterr().err

    def test_a_key_pasted_into_an_existing_file_is_refused(self, repo, capsys):
        _write(repo, "docs/a.md", "clean\n" + KEY_BLOCK)
        assert _run(repo) == 1 and "docs/a.md" in capsys.readouterr().err

    def test_an_ignored_key_is_never_staged_so_never_seen(self, repo, capsys):
        _write(repo, "ignored.key", KEY_BLOCK)
        assert _run(repo) == 0


class TestStraysAreRefusedUnlessNamed:
    def test_a_new_top_level_entry_is_refused(self, repo, capsys):
        _write(repo, "stray/thing.txt")
        assert _run(repo) == 1
        assert "'stray' is new" in capsys.readouterr().err

    def test_it_passes_when_named_by_flag_or_environment(self, repo, monkeypatch):
        _write(repo, "stray/thing.txt")
        assert _run(repo, "--allow", "stray/thing.txt") == 0
        monkeypatch.setenv("NMAS_STAGE_ALLOW", "stray/thing.txt")
        assert _run(repo) == 0

    def test_naming_a_stray_never_excuses_a_secret(self, repo):
        _write(repo, "stray/lab.key")
        assert _run(repo, "--allow", "stray/lab.key") == 1


class TestWhatItReports:
    def test_every_new_file_is_listed_and_a_modified_one_is_not(self, repo, capsys):
        _write(repo, "docs/new_page.md")
        (repo / "docs" / "a.md").write_text("changed\n")
        _git(str(repo), "add", "-A")
        assert _run(repo) == 0
        out = capsys.readouterr().out
        assert "  new  docs/new_page.md" in out and "docs/a.md" not in out
        assert "2 staged file(s), 1 new" in out

    def test_a_rename_is_a_new_path(self, repo, capsys):
        _git(str(repo), "mv", "docs/a.md", "docs/moved.key")
        assert _run(repo) == 1 and "docs/moved.key" in capsys.readouterr().err

    def test_an_unreadable_index_is_never_a_pass(self, tmp_path, capsys):
        assert G.main(["--repo", str(tmp_path / "not-a-repo")]) == 2


class TestItRunsWhereTheCommitHappens:
    def test_the_pre_commit_hook_runs_the_guard_first(self):
        hook = open(os.path.join(ROOT, "scripts", "hooks", "pre-commit"), encoding="utf-8").read()
        assert hook.index("nmas-stage-guard") < hook.index("check_removed_definitions.py")
        assert "|| exit 1" in hook
