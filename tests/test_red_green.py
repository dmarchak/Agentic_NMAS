"""Red, then green (board TI, item 1; docs/TEST_INTEGRITY.md): `scripts/nmas-red-green` runs
each test function a commit adds or changes against the commit's parent, the commit's tests in
place and the parent's code, and refuses one that is not red there.

Driven as a subprocess against REAL git repositories built here (a package and a tests/ folder,
a base commit and a commit on it), each run through scripts/nmas-test (`--allow-unconfined`:
confined where a namespace can be made, as it says):

- **The rules:** a new test that fails on the parent passes; one that passes there is refused,
  naming its outcome, the parent and the trailer that would excuse it, and passes with
  `Guards-Existing`; a trailer without its reason excuses nothing; a test skipped on the parent
  is refused; an error in setup is red; a parametrized function is red when one of its cases is.
- **Collection apart:** a test file that cannot import on the parent is reported apart and
  refused until `Red-By-Collection` names the file (Guards-Existing does not).
- **Which tests,** by parsing: a changed body is selected and an unchanged function in the same
  file is not; a docstring or a comment changes nothing; a function moved to another file
  unchanged is not selected, and one moved and changed is.
- **Which commit:** the commit being made is the index against HEAD, with the trailers from the
  message file, read without the index's lock (another git holding it), and as a real
  commit-msg hook refuses the commit or lets it be made; a temporary index (`git commit -a`)
  is refused, exit 2; a range names each commit it refuses;
  a commit changing no test passes and says so; a commit that cannot be read is exit 2.
- **Nothing is left, nothing escapes:** the parent's worktree and its temporary folder are
  removed, refused or not, and the checkout's status is what it was; a link under tests/
  reaching outside the worktree is refused, never written.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "nmas-red-green"
#: One run of the script on these repositories: measured 2026-11-03 on the laptop at about 1 s
#: (the 17 tests in 10 s at -n 2; the range's two commits about 2 s). Not 2.5 times that: it is
#: the backstop for a hung child, each pytest run inside being bounded by scripts/nmas-test.
RUN_TIMEOUT = 60

CALC = '''def double(x):
    return x * 2 if x >= 0 else 0
'''

CALC_FIXED = '''def double(x):
    return x * 2


def triple(x):
    return x * 3
'''

TESTS = '''import pytest

from pkg import calc


def test_double():
    """Doubles a positive number."""
    assert calc.double(2) == 4


def test_untouched():
    """Zero stays zero."""
    assert calc.double(0) == 0
'''


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


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _commit(root, {"pytest.ini": "[pytest]\npythonpath = .\n", "pkg/__init__.py": "",
                   "pkg/calc.py": CALC, "tests/test_calc.py": TESTS}, "start")
    return root


@pytest.fixture
def scratch(tmp_path):
    """The script's TMPDIR, so what it leaves there can be read."""
    d = tmp_path / "tmp"
    d.mkdir()
    return d


def run(repo, scratch, *args, message=None, **env):
    if message is not None:
        msg = scratch.parent / "message.txt"
        msg.write_text(message)
        args = (*args, "--message", str(msg))
    return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), "--python",
                           sys.executable, "--allow-unconfined", *args],
                          capture_output=True, text=True,
                          env=_env(TMPDIR=str(scratch), **env), timeout=RUN_TIMEOUT)


def _selected(out):
    return [line.split()[1] + " " + line.split()[2]
            for line in out.splitlines() if line.startswith("  selected ")]


def with_test(body):
    return TESTS + "\n\n" + body.strip() + "\n"


# --- the rules ------------------------------------------------------------------------------

def test_a_new_test_red_on_the_parent_passes(repo, scratch):
    _commit(repo, {"pkg/calc.py": CALC_FIXED, "tests/test_calc.py": with_test(
        "def test_triple():\n    assert calc.triple(2) == 6\n")})
    r = run(repo, scratch)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "red      tests/test_calc.py::test_triple (added): failed on the parent" in r.stdout
    assert "1 selected, 1 red, 0 excused, 0 refused" in r.stdout


def test_a_new_test_green_on_the_parent_is_refused_naming_the_trailer(repo, scratch):
    parent = _git(repo, "rev-parse", "HEAD")
    _commit(repo, {"tests/test_calc.py": with_test(
        "def test_double_three():\n    assert calc.double(3) == 6\n")})
    r = run(repo, scratch)
    assert r.returncode == 1, r.stdout + r.stderr
    assert (f"tests/test_calc.py::test_double_three: passed on the parent {parent[:12]}, red "
            "(failed or error) required; excuse with: Guards-Existing: "
            "tests/test_calc.py::test_double_three — <reason>") in r.stderr
    assert "1 selected, 0 red, 0 excused, 1 refused" in r.stdout


def test_guards_existing_excuses_a_test_green_on_the_parent(repo, scratch):
    _commit(repo, {"tests/test_calc.py": with_test(
        "def test_double_three():\n    assert calc.double(3) == 6\n")})
    r = run(repo, scratch, "--commit", "HEAD", message=(
        "Hold double\n\nGuards-Existing: tests/test_calc.py::test_double_three — a regression "
        "net before the refactor\n"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "excused  tests/test_calc.py::test_double_three (added): passed on the parent" \
        in r.stdout
    assert "1 selected, 0 red, 1 excused, 0 refused" in r.stdout


def test_a_trailer_without_its_reason_excuses_nothing(repo, scratch):
    _commit(repo, {"tests/test_calc.py": with_test(
        "def test_double_three():\n    assert calc.double(3) == 6\n")})
    r = run(repo, scratch, "--commit", "HEAD",
            message="Hold double\n\nGuards-Existing: tests/test_calc.py::test_double_three\n")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "a Guards-Existing trailer without its ' — <reason>'" in r.stderr
    assert "1 refused" in r.stdout


def test_a_test_skipped_on_the_parent_is_refused(repo, scratch):
    _commit(repo, {"pkg/newmod.py": "def f():\n    return 1\n",
                   "tests/test_calc.py": with_test(
                       "def test_newmod():\n    m = pytest.importorskip('pkg.newmod')\n"
                       "    assert m.f() == 1\n")})
    r = run(repo, scratch)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "REFUSED  tests/test_calc.py::test_newmod (added): skipped on the parent" in r.stdout
    assert "Guards-Existing: tests/test_calc.py::test_newmod — <reason>" in r.stderr


def test_an_error_in_setup_counts_as_red(repo, scratch):
    _commit(repo, {"pkg/calc.py": CALC_FIXED, "tests/test_calc.py": with_test(
        "@pytest.fixture\ndef tripler():\n    return calc.triple\n\n\n"
        "def test_tripler(tripler):\n    assert tripler(1) == 3\n")})
    r = run(repo, scratch)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "red      tests/test_calc.py::test_tripler (added): error on the parent" in r.stdout


def test_a_parametrized_function_is_red_when_one_of_its_cases_is(repo, scratch):
    _commit(repo, {"pkg/calc.py": CALC_FIXED, "tests/test_calc.py": with_test(
        "@pytest.mark.parametrize('x', [1, -1])\n"
        "def test_double_any(x):\n    assert calc.double(x) == x + x\n")})
    r = run(repo, scratch)
    assert r.returncode == 0, r.stdout + r.stderr
    line = next(x for x in r.stdout.splitlines() if "test_double_any" in x)
    assert line.startswith("  red      tests/test_calc.py::test_double_any (added): failed"), line
    assert "test_double_any[1]: passed" in line and "test_double_any[-1]: failed" in line


# --- a file that does not collect -----------------------------------------------------------

NEW_FILE = {"pkg/newmod.py": "def f():\n    return 1\n",
            "tests/test_newmod.py": "from pkg.newmod import f\n\n\n"
                                    "def test_f():\n    assert f() == 1\n"}


def test_a_file_that_cannot_collect_on_the_parent_is_reported_apart(repo, scratch):
    _commit(repo, NEW_FILE)
    r = run(repo, scratch, "--commit", "HEAD", message=(
        "New module\n\nGuards-Existing: tests/test_newmod.py::test_f — not the right trailer\n"))
    assert r.returncode == 1, r.stdout + r.stderr
    assert ("REFUSED  tests/test_newmod.py::test_f (added): tests/test_newmod.py does not "
            "collect on the parent") in r.stdout
    assert "which shows nothing about this test" in r.stdout
    assert "(1 of them in files that do not collect on the parent)" in r.stdout
    assert "Red-By-Collection: tests/test_newmod.py — <reason>" in r.stderr


def test_red_by_collection_naming_the_file_excuses_it(repo, scratch):
    _commit(repo, NEW_FILE)
    r = run(repo, scratch, "--commit", "HEAD", message=(
        "New module\n\nRed-By-Collection: tests/test_newmod.py — its module is new here\n"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 selected, 0 red, 1 excused, 0 refused" in r.stdout


# --- which tests ----------------------------------------------------------------------------

def test_a_changed_body_is_selected_and_an_unchanged_function_is_not(repo, scratch):
    changed = TESTS.replace("assert calc.double(2) == 4", "assert calc.double(-2) == -4")
    # A docstring reworded and a comment added change no test.
    changed = changed.replace('"""Zero stays zero."""', '"""Zero, doubled, is zero."""')
    changed = changed.replace("    assert calc.double(0) == 0\n",
                              "    # a comment\n    assert calc.double(0) == 0\n")
    assert changed.count("Zero, doubled") == 1 and changed.count("# a comment") == 1
    _commit(repo, {"pkg/calc.py": CALC_FIXED, "tests/test_calc.py": changed})
    r = run(repo, scratch, "--plan-only")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _selected(r.stdout) == ["tests/test_calc.py::test_double (changed)"]


def test_a_function_moved_unchanged_is_not_selected_and_one_moved_and_changed_is(repo, scratch):
    _commit(repo, {"tests/test_calc.py": TESTS.split("\n\ndef test_untouched")[0] + "\n",
                   "tests/test_other.py": "from pkg import calc\n\n\n"
                                          "def test_untouched():\n"
                                          '    """Zero stays zero."""\n'
                                          "    assert calc.double(0) == 0\n"})
    r = run(repo, scratch, "--plan-only")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _selected(r.stdout) == []
    assert "no test function added or changed: nothing to run, passes" in r.stdout
    _commit(repo, {"tests/test_other.py": None,
                   "tests/test_more.py": "from pkg import calc\n\n\n"
                                         "def test_untouched():\n"
                                         "    assert calc.double(0) == 0 * 2\n"})
    r = run(repo, scratch, "--plan-only")
    assert _selected(r.stdout) == ["tests/test_more.py::test_untouched (added)"]


def test_a_method_is_named_by_its_class(repo, scratch):
    _commit(repo, {"pkg/calc.py": CALC_FIXED, "tests/test_calc.py": with_test(
        "class TestTriple:\n    def test_two(self):\n        assert calc.triple(2) == 6\n")})
    r = run(repo, scratch)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "red      tests/test_calc.py::TestTriple::test_two (added): failed" in r.stdout


# --- which commit ---------------------------------------------------------------------------

def test_the_commit_being_made_is_the_index_against_head(repo, scratch):
    head = _git(repo, "rev-parse", "HEAD")
    _write(repo, {"tests/test_calc.py": with_test(
        "def test_double_three():\n    assert calc.double(3) == 6\n")})
    _git(repo, "add", "-A")
    status = _git(repo, "status", "--porcelain")
    r = run(repo, scratch, message="Staged\n")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "nmas-red-green: REFUSED: the commit being made tests/test_calc.py::" \
           "test_double_three: passed on the parent" in r.stderr
    r = run(repo, scratch, message=(
        "Staged\n\nGuards-Existing: tests/test_calc.py::test_double_three — a net\n"
        "# Please enter the commit message (git's template)\n"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert _git(repo, "rev-parse", "HEAD") == head, "no commit is made"
    assert _git(repo, "status", "--porcelain") == status, "the index and the tree as they were"


def test_the_commit_being_made_is_read_while_another_git_holds_the_index_lock(repo, scratch):
    # The index is read without taking its lock or writing an object: a read that takes the
    # lock (as `git write-tree` does) fails while another git process holds it.
    _write(repo, {"pkg/calc.py": CALC_FIXED, "tests/test_calc.py": with_test(
        "def test_triple():\n    assert calc.triple(2) == 6\n")})
    _git(repo, "add", "-A")
    lock = repo / ".git" / "index.lock"
    lock.write_bytes((repo / ".git" / "index").read_bytes())
    r = run(repo, scratch, message="Staged\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "red      tests/test_calc.py::test_triple (added): failed on the parent" in r.stdout
    assert lock.exists(), "the lock is git's, left as it was"


def test_as_a_commit_msg_hook_it_refuses_the_commit_and_passes_it_with_its_trailer(
        repo, scratch):
    """A real `git commit` running it as its commit-msg hook, in the environment git gives its
    hooks: refused, no commit is made; with the trailer, the commit is."""
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{SCRIPT}" --repo "$(pwd)" --python '
                    f'"{sys.executable}" --allow-unconfined --message "$1"\n')
    hook.chmod(0o755)
    head = _git(repo, "rev-parse", "HEAD")
    _write(repo, {"tests/test_calc.py": with_test(
        "def test_double_three():\n    assert calc.double(3) == 6\n")})
    _git(repo, "add", "-A")
    msg = scratch.parent / "hook-message.txt"

    def commit(text):
        msg.write_text(text)
        return subprocess.run(["git", "-C", str(repo), "commit", "-q", "-F", str(msg)],
                              capture_output=True, text=True, timeout=RUN_TIMEOUT,
                              env=_env(TMPDIR=str(scratch)))

    r = commit("Hold double\n")
    assert r.returncode != 0, r.stdout + r.stderr
    assert "test_double_three: passed on the parent" in r.stderr
    assert _git(repo, "rev-parse", "HEAD") == head, "the refused commit is not made"
    r = commit("Hold double\n\nGuards-Existing: tests/test_calc.py::test_double_three — a net\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _git(repo, "rev-parse", "HEAD") != head


def test_a_temporary_index_is_refused_never_guessed_at(repo, scratch):
    _write(repo, {"tests/test_calc.py": with_test("def test_more():\n    assert True\n")})
    r = run(repo, scratch, message="commit -a\n", GIT_INDEX_FILE=".git/index.tmp")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "GIT_INDEX_FILE is .git/index.tmp" in r.stderr


def test_a_range_names_each_commit_it_refuses(repo, scratch):
    base = _git(repo, "rev-parse", "HEAD")
    red = _commit(repo, {"pkg/calc.py": CALC_FIXED, "tests/test_calc.py": with_test(
        "def test_triple():\n    assert calc.triple(2) == 6\n")})
    green = _commit(repo, {"tests/test_calc.py": with_test(
        "def test_triple():\n    assert calc.triple(2) == 6\n\n\n"
        "def test_double_three():\n    assert calc.double(3) == 6\n")})
    r = run(repo, scratch, "--range", f"{base}..HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    refused = [x for x in r.stderr.splitlines() if x.startswith("nmas-red-green: REFUSED: ")]
    assert len(refused) == 1 and refused[0].startswith(
        f"nmas-red-green: REFUSED: {green[:12]} tests/test_calc.py::test_double_three"), refused
    assert f"nmas-red-green: {red[:12]} " in r.stdout


def test_a_commit_changing_no_test_passes_and_says_so(repo, scratch):
    _commit(repo, {"pkg/calc.py": CALC_FIXED})
    r = run(repo, scratch)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no test function added or changed: nothing to run, passes" in r.stdout


def test_a_commit_that_cannot_be_read_is_exit_2(repo, scratch):
    r = run(repo, scratch, "--commit", "no-such-commit")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "COULD NOT ASK" in r.stderr


def test_a_link_in_tests_reaching_outside_the_worktree_is_refused_never_written(repo, scratch):
    _write(repo, {"tests/test_calc.py": with_test("def test_more():\n    assert True\n")})
    os.symlink("../../../outside", repo / "tests" / "escape")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "a link")
    r = run(repo, scratch)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "tests/escape links outside the worktree (../../../outside)" in r.stderr


# --- nothing is left ------------------------------------------------------------------------

def test_the_parent_worktree_and_its_folder_are_removed_refused_or_not(repo, scratch):
    _commit(repo, {"pkg/calc.py": CALC_FIXED, "tests/test_calc.py": with_test(
        "def test_triple():\n    assert calc.triple(2) == 6\n\n\n"
        "def test_double_three():\n    assert calc.double(3) == 6\n")})
    status = _git(repo, "status", "--porcelain")
    r = run(repo, scratch)
    assert r.returncode == 1 and "1 red" in r.stdout and "1 refused" in r.stdout, r.stdout
    worktrees = [x for x in _git(repo, "worktree", "list", "--porcelain").splitlines()
                 if x.startswith("worktree ")]
    assert worktrees == [f"worktree {repo}"], worktrees
    assert list(scratch.iterdir()) == [], "the script's temporary folder is removed"
    assert _git(repo, "status", "--porcelain") == status
