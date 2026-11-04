"""Protected guards (board TI item 2; docs/TEST_INTEGRITY.md, D2, D3): `scripts/nmas-guard-check`
refuses a commit that changes a guard without the operator's quoted approval,
`Approved-By: operator — "<the operator's own words>"`.

Driven as a subprocess against REAL git repositories built here (each with git's GIT_*
variables stripped, so no test's git reaches the checkout this runs in, C2357):

- **The guards:** each guard path of the board's list (written out here, apart from the
  script's own list) changed without the trailer is refused, naming it, the comparison and the
  trailer that would excuse it; the script's own file is one; a non-guard change needs nothing.
- **The trailer:** a proper one passes (curly quotes and a wrapped value too) and approves
  every guard of its commit; one quoting no words or too few, one naming anyone but `operator`,
  and one without its reason are refused, in any commit.
- **docs/TESTING.md by line (D3):** a per-file table row added, changed or removed needs
  nothing; a rule-section line changed, a line after the table, the table's header, a helper's
  row, or a line splitting the table needs the trailer.
- **What a change is:** a guard deleted, renamed away, a file renamed onto a guard's path, and
  a mode change each count.
- **Which commit:** `--range` names the commit it refuses and judges each on its own trailer;
  `--message` reads the index (not the working tree), and as a real commit-msg hook refuses
  the commit or lets it be made; a temporary index is exit 2; a root commit passes, said; an
  unreadable commit is exit 2.
- **The wiring:** CI's job a runs it over the pushed range after red, then green, as the other
  range checks run; the real docs/TESTING.md's per-file table is found by the parser (a floor).
  The commit-msg hook's line is held in tests/test_test_weakening_check.py with the hook's
  other checks.
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "nmas-guard-check"
#: One run on these repositories: measured 2026-11-03 on the laptop at under 0.2 s. Not 2.5
#: times that: the backstop for a hung git.
RUN_TIMEOUT = 30
EXCUSE = 'excuse with: Approved-By: operator — "<the operator\'s own words, quoted>"'
GOOD = 'Approved-By: operator — "change the hook as the board says"'

#: The board's guards (docs/TEST_INTEGRITY.md item 2), written out here rather than read from
#: the script, so a guard dropped from its list fails here.
GUARD_PATHS = ["scripts/hooks/commit-msg", "scripts/hooks/a-new-hook", "scripts/nmas-gate",
               "scripts/nmas-stage-guard", "scripts/nmas-test-weakening-check",
               "scripts/nmas-host-step-check", "scripts/nmas-red-green",
               "scripts/nmas-guard-check", "scripts/nmas-bypass-scan",
               "scripts/nmas-premise-check", "tests/ratchet_lists.py",
               "tests/coverage_baseline.json", "CLAUDE.md",
               # C2358: what runs the checks, and the checks' own tests.
               ".github/workflows/ci.yml", "scripts/nmas-test", "scripts/nmas-control",
               "tests/test_guard_check.py", "tests/test_red_green.py",
               "tests/test_test_weakening_check.py", "tests/test_bypass_scan.py",
               "tests/test_premise_check.py", "tests/test_host_step_check.py",
               "tests/test_stage_guard.py", "tests/test_nmas_gate.py"]

TESTING = """# What the test suite checks

## A rule

Every new check is shown able to fail.

## The per-file table

| File | Covers |
|---|---|
| `test_a.py` | the first |
| `test_b.py` | the second |
| `tests/fake.py` | a helper (not a test module) |

## After the table

The suite runs confined.
"""

FILES = {
    "CLAUDE.md": "# Rules\n\n- a rule\n",
    "scripts/hooks/commit-msg": "#!/bin/sh\nexit 0\n",
    "scripts/nmas-gate": "#!/bin/sh\necho gate\n",
    "scripts/nmas-guard-check": "#!/bin/sh\necho a stand-in\n",
    "scripts/nmas-other": "#!/bin/sh\necho other\n",
    "tests/ratchet_lists.py": "RATCHETS = []\n",
    "tests/test_x.py": "def test_x():\n    assert True\n",
    "docs/TESTING.md": TESTING,
    "docs/OTHER.md": "# Other\n",
    "modules/m.py": "X = 1\n",
}


def _env(**more):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com", **more)
    return env


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, env=_env(),
                          capture_output=True, text=True, timeout=30).stdout.strip()


def _write(repo, files):
    for path, text in files.items():
        p = repo / path
        if text is None:
            p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def _commit(repo, files, message="a change"):
    _write(repo, files)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _edit(repo, path, old, new):
    text = (repo / path).read_text()
    assert old in text, (path, old)
    return {path: text.replace(old, new, 1)}


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    # Its own repository, never the checkout's (C2357).
    assert Path(_git(root, "rev-parse", "--show-toplevel")).resolve() == root.resolve()
    _commit(root, FILES, "start")
    return root


def run(repo, *args, message=None, **env):
    if message is not None:
        msg = repo.parent / "message.txt"
        msg.write_text(message)
        args = (*args, "--message", str(msg))
    return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), *args],
                          capture_output=True, text=True, env=_env(**env), timeout=RUN_TIMEOUT)


def _head(repo):
    return _git(repo, "rev-parse", "HEAD")[:12]


# --- the guards -----------------------------------------------------------------------------

@pytest.mark.parametrize("path", GUARD_PATHS)
def test_a_guard_changed_without_the_trailer_is_refused_naming_it(repo, path):
    before = (repo / path).read_text() if (repo / path).exists() else ""
    sha = _commit(repo, {path: before + "# loosened\n"})
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"nmas-guard-check: REFUSED: {sha[:12]} {path} (" in r.stderr, r.stderr
    assert f"on the parent {_git(repo, 'rev-parse', 'HEAD~1')[:12]}" in r.stderr, r.stderr
    assert EXCUSE in r.stderr
    assert f"REFUSED   {path} (" in r.stdout


def test_a_changed_guard_names_its_blobs_on_both_sides(repo):
    _commit(repo, _edit(repo, "CLAUDE.md", "- a rule", "- a looser rule"))
    old = _git(repo, "rev-parse", "HEAD~1:CLAUDE.md")[:10]
    new = _git(repo, "rev-parse", "HEAD:CLAUDE.md")[:10]
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1
    assert f"CLAUDE.md (modified): mode and blob 100644 {old} on the parent" in r.stderr
    assert f"100644 {new} at the commit {_head(repo)}" in r.stderr


@pytest.mark.parametrize("path", GUARD_PATHS)
def test_with_a_proper_trailer_it_passes(repo, path):
    before = (repo / path).read_text() if (repo / path).exists() else ""
    _commit(repo, {path: before + "# changed\n"}, f"Change it\n\n{GOOD}\n")
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"approved  {path} (" in r.stdout
    assert "1 guard path(s) changed, 1 approved" in r.stdout


def test_the_scripts_own_file_is_a_guard(repo):
    """Board TI item 2: "the check itself is a guard"."""
    _commit(repo, {"scripts/nmas-guard-check": "#!/bin/sh\nexit 0\n"})
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "scripts/nmas-guard-check (modified)" in r.stderr


def test_a_change_to_no_guard_needs_nothing(repo):
    _commit(repo, {"modules/m.py": "X = 2\n", "scripts/nmas-other": "#!/bin/sh\nexit 1\n",
                   "tests/test_x.py": "def test_x():\n    assert 1\n", "docs/OTHER.md": "# B\n",
                   "scripts/hooksmith": "not under scripts/hooks/\n"})
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no guard changed: passes" in r.stdout


def test_one_proper_trailer_approves_every_guard_of_its_commit(repo):
    _commit(repo, {"CLAUDE.md": "# Rules\n", "scripts/nmas-gate": "#!/bin/sh\n"},
            f"Both\n\n{GOOD}\n")
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "2 guard path(s) changed, 2 approved" in r.stdout


# --- the trailer ----------------------------------------------------------------------------

@pytest.mark.parametrize("trailer", [
    "Approved-By: operator — “curly quotes are the operator's words too”",
    "Approved-By: operator – option (i): \"re-record them as watched,\n  a person decides\"",
    'Approved-By: operator - "a plain hyphen between them"',
])
def test_curly_quotes_a_wrapped_value_and_each_dash_pass(repo, trailer):
    _commit(repo, {"CLAUDE.md": "# Rules\n"}, f"Change it\n\n{trailer}\n")
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("trailer, said", [
    ("Approved-By: operator — the operator agreed to it", "quotes 0 word(s)"),
    ('Approved-By: operator — "fine"', "quotes 1 word(s)"),
    ('Approved-By: operator — "two words"', "quotes 2 word(s)"),
])
def test_a_trailer_quoting_too_few_words_is_refused(repo, trailer, said):
    _commit(repo, {"CLAUDE.md": "# Rules\n"}, f"Change it\n\n{trailer}\n")
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert said in r.stderr and "at least 3 of the operator's own words" in r.stderr
    assert "CLAUDE.md (modified)" in r.stderr and "with no proper Approved-By" in r.stderr


@pytest.mark.parametrize("trailer", [
    'Approved-By: operator — "<…>"',
    'Approved-By: operator — "<the operator\'s own words, quoted>"',
    'Approved-By: operator — "the operator\'s own words, quoted"',
    'Approved-By: operator — “the operator’s own words, quoted”',
    'Approved-By: operator — "approve the change ..."',
    'Approved-By: operator — "approve the change …"',
    'Approved-By: operator — "" and "three more words here"',
    'Approved-By: operator — "   "',
    'Approved-By: operator — "TBD by the operator later"',
    'Approved-By: operator — "tbd: quote the operator here"',
])
def test_a_placeholder_quote_is_refused(repo, trailer):
    """C2409 (the operator, 2026-11-04): angle brackets, an ellipsis, an empty quote, "TBD",
    or the template's own words are a placeholder, never the operator's words, even when
    another span beside it quotes enough words."""
    _commit(repo, {"CLAUDE.md": "# Rules\n"}, f"Change it\n\n{trailer}\n")
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "quoting a placeholder" in r.stderr and "C2409" in r.stderr
    assert "CLAUDE.md (modified)" in r.stderr and "with no proper Approved-By" in r.stderr


@pytest.mark.parametrize("trailer", [
    'Approved-By: operator — "Approved: fix C2409 so the guard check refuses placeholder '
    'approvals, with canaries both ways."',
    'Approved-By: operator — "keep the kill switch, then it may go last" (2026-11-03)',
    'Approved-By: operator — "a quote with less than and greater than said in words"',
])
def test_a_real_quote_beside_the_placeholder_rule_passes(repo, trailer):
    """The other way (C2409's canary): the operator's own words, with no placeholder in them,
    still approve."""
    _commit(repo, {"CLAUDE.md": "# Rules\n"}, f"Change it\n\n{trailer}\n")
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 guard path(s) changed, 1 approved" in r.stdout


@pytest.mark.parametrize("name", ["Alice", "Operator", "the", "operators", "[Author]"])
def test_a_name_other_than_operator_is_refused(repo, name):
    _commit(repo, {"CLAUDE.md": "# Rules\n"},
            f'Change it\n\nApproved-By: {name} — "change the rule as said"\n')
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"naming '{name}', where exactly 'operator'" in r.stderr
    assert "CLAUDE.md (modified)" in r.stderr


def test_a_trailer_without_its_reason_is_refused(repo):
    _commit(repo, {"CLAUDE.md": "# Rules\n"}, "Change it\n\nApproved-By: operator\n")
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "an Approved-By trailer without its ' — <reason>'" in r.stderr


def test_a_bad_trailer_is_refused_in_a_commit_changing_no_guard(repo):
    _commit(repo, {"modules/m.py": "X = 3\n"}, "Other\n\nApproved-By: Alice — \"as she said it\"\n")
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "naming 'Alice'" in r.stderr


def test_the_trailer_is_read_from_the_message_file_given(repo):
    _commit(repo, {"CLAUDE.md": "# Rules\n"}, "Change it\n")
    assert run(repo, "--commit", "HEAD").returncode == 1
    r = run(repo, "--commit", "HEAD", message=f"Change it\n\n{GOOD}\n")
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_commented_trailer_is_not_a_trailer(repo):
    _commit(repo, {"CLAUDE.md": "# Rules\n"})
    r = run(repo, "--commit", "HEAD", message=f"Change it\n\n# {GOOD}\n")
    assert r.returncode == 1, r.stdout + r.stderr


# --- docs/TESTING.md by line (D3) -------------------------------------------------------------

@pytest.mark.parametrize("old, new", [
    ("| `tests/fake.py` |", "| `test_c.py` | the third, new |\n| `tests/fake.py` |"),
    ("| `test_b.py` | the second |", "| `test_b.py` | the second, and more it checks |"),
    ("| `test_b.py` | the second |\n", ""),
    ("| `test_a.py` | the first |", "| `test_a.py` (C1) | the first, with a note on its name |"),
])
def test_a_per_file_table_row_added_changed_or_removed_needs_nothing(repo, old, new):
    _commit(repo, _edit(repo, "docs/TESTING.md", old, new))
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "docs/TESTING.md:" in r.stdout and "free (D3)" in r.stdout
    assert "no guard changed: passes" in r.stdout


@pytest.mark.parametrize("old, new, line", [
    ("Every new check is shown able to fail.", "A check may be shown able to fail.", "-5"),
    ("The suite runs confined.", "The suite may run unconfined.", "-17"),
    ("| File | Covers |", "| File | What |", "-9"),
    ("| `tests/fake.py` | a helper", "| `tests/fake.py` | a looser helper", "-13"),
    ("| `test_b.py` | the second |\n", "| `test_b.py` | the second |\nA rule inside it.\n",
     "+13"),
    ("## A rule\n", "## A rule\nA new rule.\n", "+4"),
])
def test_a_rule_section_line_changed_needs_the_trailer(repo, old, new, line):
    _commit(repo, _edit(repo, "docs/TESTING.md", old, new))
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "docs/TESTING.md (modified, its rule sections)" in r.stderr
    assert "outside the per-file table's test rows" in r.stderr
    assert f"({line}: " in r.stderr, r.stderr
    assert run(repo, "--commit", "HEAD", message=f"Again\n\n{GOOD}\n").returncode == 0


def test_a_rule_change_beside_a_row_change_is_still_refused(repo):
    files = _edit(repo, "docs/TESTING.md", "| `test_b.py` | the second |",
                  "| `test_b.py` | the second, more |")
    files["docs/TESTING.md"] = files["docs/TESTING.md"].replace(
        "Every new check is shown able to fail.", "Checks need not fail.")
    _commit(repo, files)
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "2 changed line(s)" in r.stderr


def test_a_table_row_moved_out_of_the_table_is_a_rule_change(repo):
    files = _edit(repo, "docs/TESTING.md", "| `test_b.py` | the second |\n", "")
    files["docs/TESTING.md"] += "| `test_b.py` | the second |\n"
    _commit(repo, files)
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "docs/TESTING.md (modified, its rule sections)" in r.stderr


# --- what a change is -----------------------------------------------------------------------

@pytest.mark.parametrize("path", ["CLAUDE.md", "scripts/hooks/commit-msg", "docs/TESTING.md",
                                  "scripts/nmas-guard-check"])
def test_a_guard_deleted_counts(repo, path):
    _commit(repo, {path: None})
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"{path} (deleted): present on the parent" in r.stderr


def test_a_guard_renamed_away_counts(repo):
    _git(repo, "mv", "scripts/hooks/commit-msg", "scripts/old-commit-msg")
    _git(repo, "commit", "-q", "-m", "rename")
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "scripts/hooks/commit-msg (deleted)" in r.stderr
    assert "scripts/old-commit-msg" not in r.stderr


def test_a_file_renamed_onto_a_guards_path_counts(repo):
    _commit(repo, {"scripts/nmas-gate": None})
    _git(repo, "mv", "scripts/nmas-other", "scripts/nmas-gate")
    _git(repo, "commit", "-q", "-m", "rename onto")
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "scripts/nmas-gate (added): absent on the parent" in r.stderr


def test_a_mode_change_counts(repo):
    (repo / "scripts/hooks/commit-msg").chmod(0o755)
    _commit(repo, {})
    (repo / "scripts/hooks/commit-msg").chmod(0o644)
    _commit(repo, {})
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "scripts/hooks/commit-msg (modified): mode and blob 100755" in r.stderr


# --- which commit ---------------------------------------------------------------------------

def test_a_range_names_the_commit_it_refuses(repo):
    first = _commit(repo, {"modules/m.py": "X = 5\n"}, "no guard")
    second = _commit(repo, {"CLAUDE.md": "# Rules\n"}, "a guard")
    r = run(repo, "--range", "HEAD~2..HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"REFUSED: {second[:12]} CLAUDE.md (modified)" in r.stderr
    assert f"REFUSED: {first[:12]}" not in r.stderr
    assert f"nmas-guard-check: {first[:12]} no guard" in r.stdout


def test_a_range_judges_each_commit_on_its_own_trailer(repo):
    first = _commit(repo, {"CLAUDE.md": "# Rules\n"}, f"approved\n\n{GOOD}\n")
    second = _commit(repo, {"scripts/nmas-gate": "#!/bin/sh\n"}, "not approved")
    r = run(repo, "--range", "HEAD~2..HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"REFUSED: {second[:12]} scripts/nmas-gate (modified)" in r.stderr
    assert f"REFUSED: {first[:12]}" not in r.stderr
    assert "approved  CLAUDE.md (modified)" in r.stdout


def test_the_commit_being_made_is_the_index_not_the_working_tree(repo):
    head = _git(repo, "rev-parse", "HEAD")
    _write(repo, {"CLAUDE.md": "# Rules, loosened\n"})
    _git(repo, "add", "CLAUDE.md")
    r = run(repo, message="Change it\n")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "REFUSED: the commit being made CLAUDE.md (modified)" in r.stderr
    assert "at the index" in r.stderr
    assert run(repo, message=f"Change it\n\n{GOOD}\n").returncode == 0
    # A guard changed in the working tree but not staged is not the commit's.
    _git(repo, "reset", "-q")
    _write(repo, {"modules/m.py": "X = 9\n"})
    _git(repo, "add", "modules/m.py")
    r = run(repo, message="Other\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _git(repo, "rev-parse", "HEAD") == head, "nothing is committed"


def test_a_temporary_index_is_not_guessed_at(repo):
    r = run(repo, message="commit -a\n", GIT_INDEX_FILE=".git/index.tmp")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "GIT_INDEX_FILE is .git/index.tmp" in r.stderr


def test_as_a_commit_msg_hook_it_refuses_the_commit_and_passes_it_with_its_trailer(repo):
    """A real `git commit` running it as its commit-msg hook, in the environment git gives its
    hooks (GIT_DIR, GIT_INDEX_FILE): refused, no commit made; with the trailer, made."""
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{SCRIPT}" --repo "$(pwd)" '
                    '--message "$1"\n')
    hook.chmod(0o755)
    head = _git(repo, "rev-parse", "HEAD")
    _write(repo, {"scripts/hooks/commit-msg": "#!/bin/sh\nexit 1\n"})
    _git(repo, "add", "-A")
    msg = repo.parent / "hook-message.txt"

    def commit(text):
        msg.write_text(text)
        return subprocess.run(["git", "-C", str(repo), "commit", "-q", "-F", str(msg)],
                              capture_output=True, text=True, timeout=RUN_TIMEOUT, env=_env())

    r = commit("Loosen the hook\n")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "REFUSED: the commit being made scripts/hooks/commit-msg (modified)" in r.stderr
    assert _git(repo, "rev-parse", "HEAD") == head, "the refused commit is not made"
    r = commit(f"Change the hook\n\n{GOOD}\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _git(repo, "rev-parse", "HEAD") != head


def test_a_root_commit_passes_and_says_so(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _commit(root, {"CLAUDE.md": "# Rules\n"}, "first")
    r = run(root, "--commit", "HEAD")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "a root commit, no parent to compare, passes" in r.stdout


def test_a_commit_that_cannot_be_read_is_not_a_pass(repo):
    r = run(repo, "--commit", "0123456789abcdef0123456789abcdef01234567")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "COULD NOT ASK" in r.stderr


# --- the wiring -----------------------------------------------------------------------------

def _module():
    loader = importlib.machinery.SourceFileLoader("nmas_guard_check", str(SCRIPT))
    spec = importlib.util.spec_from_loader("nmas_guard_check", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_the_real_testing_md_table_is_found():
    """The parser finds docs/TESTING.md's per-file table, so a row added there is free: a floor
    (803 rows, 2026-11-03), and a planted rule line beside it is not."""
    gc = _module()
    lines = (ROOT / "docs" / "TESTING.md").read_text().splitlines()
    free = gc.free_lines(lines)
    assert len(free) >= 800, len(free)
    assert all(lines[i].startswith("| `test_") for i in free)
    first = min(free)
    assert lines[first - 2].replace(" ", "") == "|File|Covers|"
    planted = lines[:first + 1] + ["A rule line inside the table."] + lines[first + 1:]
    assert first + 1 not in gc.free_lines(planted)


def test_ci_runs_it_over_the_pushed_range_after_red_then_green():
    doc = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    steps = doc["jobs"]["test"]["steps"]
    runs = [s.get("run", "") for s in steps]
    host = next(s for s in steps if 'nmas-host-step-check --range "$RANGE"' in s.get("run", ""))
    mine = next(s for s in steps if 'nmas-guard-check --range "$RANGE"' in s.get("run", ""))
    red = next(i for i, r in enumerate(runs) if 'nmas-red-green --range "$RANGE"' in r)
    assert steps.index(mine) == red + 1, "the step after red, then green"
    # Shard a, or the doc shard a docs-only push runs alone: a docs-only push can change
    # CLAUDE.md or docs/TESTING.md's rules.
    assert mine["if"] == host["if"] == "matrix.shard == 'a' || matrix.shard == 'docs'"
    assert mine["env"] == host["env"]
    assert mine["run"].replace("nmas-guard-check", "X") == \
        host["run"].replace("nmas-host-step-check", "X")
