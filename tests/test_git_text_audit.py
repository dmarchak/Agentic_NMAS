"""C2340's git audit (`scripts/nmas-git-text-audit`), allowed by the config-read hook by name
(the operator's approval of 2026-11-03, for this tool only): it reads commit messages and
`.nsot/` records, never a golden, and prints every line through the typed mask.

- **Pointed at a golden or a config file, it refuses:** it takes no path argument, and a
  repository that is not one (a file) is "no repository", nothing read.
- **Over a repository holding planted secrets** (a golden with a planted value and a marker
  line, a commit message with a prose password and a pasted configuration line, a `.nsot`
  record with both), its output holds no planted value and no line of the golden.
- **It finds what it is for:** the prose password the old mask let through is listed, its
  commit marked local only, credential-shaped; a pasted line the old mask already masked is not
  listed as credential-shaped.
"""
import importlib.machinery
import importlib.util
import os
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTED = ("Hk3mZ8qTn2Lw", "Pq7rT2wXy9", "Zt5vB8nLc3Qx", "Golden9SecretVal")
GOLDEN_MARKER = "banner motd ^only-in-the-golden-7f3a^"


def _tool():
    path = os.path.join(ROOT, "scripts", "nmas-git-text-audit")
    loader = importlib.machinery.SourceFileLoader("nmas_git_text_audit", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "net1"
    (r / "golden").mkdir(parents=True)
    (r / ".nsot").mkdir()
    _git(tmp_path, "init", "-q", str(r))
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    (r / "golden" / "r1.cfg").write_text(
        f"hostname r1\nenable secret 0 {PLANTED[3]}\n{GOLDEN_MARKER}\n", encoding="utf-8")
    (r / ".nsot" / "receipt.json").write_text(
        '{"reason": "set the password to %s for the lab", '
        '"line": "snmp-server community %s RO"}\n' % (PLANTED[2], PLANTED[3]), encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", f"Why: the password is {PLANTED[0]} now")
    (r / "a").write_text("x\n", encoding="utf-8")
    _git(r, "add", "a")
    _git(r, "commit", "-qm", f"pasted: username admin password 0 {PLANTED[1]}")
    return r


def test_a_golden_or_config_path_given_is_refused_and_nothing_printed(repo, capsys):
    tool = _tool()
    with pytest.raises(SystemExit) as exc:
        tool.main([str(repo / "golden" / "r1.cfg")], values={})
    assert exc.value.code == 2
    printed = capsys.readouterr()
    assert GOLDEN_MARKER not in printed.out + printed.err
    assert not any(v in printed.out + printed.err for v in PLANTED)


def test_a_repository_that_is_a_file_is_no_repository():
    tool = _tool()
    got = tool.audit(["x"], lambda n: os.path.join(ROOT, "tests", "fixtures"), values={})
    assert got["repos"] == [{"name": "x", "missing": True}] and got["matches"] == []


def test_over_planted_secrets_it_prints_masked_lines_only(repo):
    tool = _tool()
    got = tool.audit(["net1"], lambda n: str(repo), values={})
    out = "\n".join(tool.report(got))
    assert not any(v in out for v in PLANTED), out
    assert GOLDEN_MARKER not in out and "hostname r1" not in out
    assert "<redacted:" in out


def test_it_lists_the_prose_password_the_old_mask_let_through(repo):
    tool = _tool()
    got = tool.audit(["net1"], lambda n: str(repo), values={})
    shaped = [m for m in got["matches"] if m["shaped"]]
    wheres = sorted(m["where"] for m in shaped)
    assert wheres == ["message", "record .nsot/receipt.json"], got["matches"]
    assert all(not m["pushed"] for m in got["matches"])
    (msg,) = [m for m in shaped if m["where"] == "message"]
    assert msg["shown"].startswith("Why: the password <redacted:")
    # The pasted line's value was the old mask's already: never listed as credential-shaped.
    assert not [m for m in shaped if "username admin" in m["shown"]]


def test_the_hook_names_it_among_its_readers():
    import runpy
    hook = runpy.run_path(os.path.join(ROOT, "scripts", "hooks", "claude-no-raw-config-reads"))
    assert hook["READERS"] == ("nmas-config-read", "nmas-git-text-audit")
