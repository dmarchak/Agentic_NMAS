"""A commit that weakens a test names it with a registered reason (CLAUDE.md, "Measurement and
testing"; the operator's spec, 2026-10-18): scripts/nmas-test-weakening-check, the commit-msg
hook and CI over the pushed range.

Driven against REAL git repositories, as tests/test_host_step_check.py is: for each kind of
weakening, a seeded commit is refused and the same commit with a `Test-Weakened:` trailer naming
a real register row passes; a trailer naming a row that does not exist is refused; a rename, a
move, a list that shrank and a ceiling lowered pass. The registry of ratchets
(tests/ratchet_lists.py) is held complete by a scan with a floor and a planted case.

Its first run over the repository's last 60 commits (2026-10-18) refused 11 of them, every one
before the rule was written: v1 removals' deleted tests and lowered floors, and four trailers
without their register row (docs/TESTING.md, its row).
"""
import ast
import importlib.machinery
import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.source_index import tracked

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "nmas-test-weakening-check"


@pytest.fixture(scope="module")
def wk():
    loader = importlib.machinery.SourceFileLoader("nmas_test_weakening_check", str(SCRIPT))
    spec = importlib.util.spec_from_loader("nmas_test_weakening_check", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    return subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                          capture_output=True, text=True).stdout.strip()


REGISTER = """# Open findings

## C. Tooling that reports wrongly

| # | Finding | Status | Where |
|---|---|---|---|
| C1 | **an open finding** | **[C]** open | tests/ |

## Closed

| # | Finding | Closed | Reason |
|---|---|---|---|
| C2 | **a closed finding** | 2026-10-01 | fixed |
"""

REGISTRY = """RATCHETS = (
    ("tests/test_lists.py", "KNOWN_GAPS", "shrinks"),
    ("tests/test_lists.py", "GAPS_CEILING", "ceiling"),
    ("tests/test_lists.py", "POPULATION_FLOOR", "floor"),
    ("tests/test_lists.py", "BLOCKED_FORMS", "grows"),
    ("tests/ratchet_lists.py", "RATCHETS", "registry"),
)
"""

TEST_A = """import pytest


class TestThing:
    def test_one(self):
        assert 1 + 1 == 2

    def test_two(self):
        assert "a" in "abc"


def test_three():
    found = [1, 2, 3]
    assert len(found) >= 3
"""

TEST_LISTS = """KNOWN_GAPS = {"a": "why a", "b": "why b"}
GAPS_CEILING = 2
POPULATION_FLOOR = 10
BLOCKED_FORMS = {"git restore": "git restore x", "git clean": "git clean -fd"}


def test_gaps():
    assert len(KNOWN_GAPS) <= GAPS_CEILING
"""

MODULE = """def f(x):
    if x:
        return 1
    return 2
"""


def _write(repo, path, text):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    for path, text in (("docs/OPEN_FINDINGS.md", REGISTER), ("tests/ratchet_lists.py", REGISTRY),
                       ("tests/test_a.py", TEST_A), ("tests/test_lists.py", TEST_LISTS),
                       ("modules/m.py", MODULE)):
        _write(tmp_path, path, text)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "start")
    return tmp_path


def _edit(repo, path, old, new):
    p = repo / path
    text = p.read_text()
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1))


def _commit(repo, message):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _run(repo, *args):
    return subprocess.run(["python3", str(SCRIPT), *args], cwd=repo,
                          capture_output=True, text=True)


def _range(repo):
    return _run(repo, "--range", "HEAD~1..HEAD")


#: Each kind of weakening: (file, the text replaced, its replacement, what the refusal names,
#: the test or list a trailer names).
WEAKENINGS = {
    "a test deleted": (
        "tests/test_a.py", "    def test_two(self):\n        assert \"a\" in \"abc\"\n", "",
        "test deleted: TestThing.test_two", "TestThing.test_two"),
    "a skip": (
        "tests/test_a.py", "    def test_one(self):",
        "    @pytest.mark.skip(reason=\"later\")\n    def test_one(self):",
        "skip added: TestThing.test_one (pytest.mark.skip x0 -> pytest.mark.skip x1)",
        "TestThing.test_one"),
    "a skipif": (
        "tests/test_a.py", "    def test_one(self):",
        "    @pytest.mark.skipif(True, reason=\"later\")\n    def test_one(self):",
        "skip added: TestThing.test_one (pytest.mark.skipif x0 -> pytest.mark.skipif x1)",
        "test_one"),
    "an xfail": (
        "tests/test_a.py", "def test_three():", "@pytest.mark.xfail\ndef test_three():",
        "skip added: test_three (pytest.mark.xfail x0 -> pytest.mark.xfail x1)", "test_three"),
    "a skip call": (
        "tests/test_a.py", "    found = [1, 2, 3]\n",
        "    pytest.skip(\"later\")\n    found = [1, 2, 3]\n",
        "skip added: test_three (pytest.skip() x0 -> pytest.skip() x1)", "test_three"),
    "a pragma": (
        "modules/m.py", "    if x:\n", "    if x:  # pragma: no cover\n",
        "pragma: no cover added: f (pragma: no cover x0 -> pragma: no cover x1)",
        "modules/m.py"),
    "a ceiling raised": (
        "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 3",
        "ceiling raised: GAPS_CEILING (2 -> 3)", "GAPS_CEILING"),
    "a floor lowered": (
        "tests/test_lists.py", "POPULATION_FLOOR = 10", "POPULATION_FLOOR = 8",
        "floor lowered: POPULATION_FLOOR (10 -> 8)", "POPULATION_FLOOR"),
    "a list added to": (
        "tests/test_lists.py", '"b": "why b"}', '"b": "why b", "c": "why c"}',
        "list added to: KNOWN_GAPS (2 members -> +1: 'c')", "KNOWN_GAPS"),
    "a refused form removed": (
        "tests/test_lists.py", ', "git clean": "git clean -fd"}', "}",
        "list removed from: BLOCKED_FORMS (2 members -> -1: 'git clean')", "BLOCKED_FORMS"),
    "a bound in an assert lowered": (
        "tests/test_a.py", "assert len(found) >= 3", "assert len(found) >= 2",
        "floor loosened: test_three: len(found) (3 -> 2)", "test_three"),
}


@pytest.mark.parametrize("kind", sorted(WEAKENINGS))
class TestEachWeakening:
    def test_it_is_refused_naming_the_file_the_name_and_both_values(self, repo, kind):
        path, old, new, says, _named = WEAKENINGS[kind]
        _edit(repo, path, old, new)
        sha = _commit(repo, f"{kind}, said nowhere")
        p = _range(repo)
        assert p.returncode == 1, p.stderr
        assert f"REFUSED: {sha[:12]} {path}: {says}" in p.stderr, p.stderr
        assert p.stderr.count("REFUSED") == 1, p.stderr

    def test_with_a_trailer_naming_an_open_row_it_passes(self, repo, kind):
        path, old, new, _says, named = WEAKENINGS[kind]
        _edit(repo, path, old, new)
        _commit(repo, f"{kind}\n\nTest-Weakened: {named} — C1: the reason, stated")
        p = _range(repo)
        assert p.returncode == 0, p.stderr

    def test_a_closed_row_and_a_hyphen_do_too(self, repo, kind):
        path, old, new, _says, named = WEAKENINGS[kind]
        _edit(repo, path, old, new)
        _commit(repo, f"{kind}\n\nTest-Weakened: {named} - C2: the reason, stated")
        assert _range(repo).returncode == 0

    def test_a_trailer_naming_a_row_that_does_not_exist_is_refused(self, repo, kind):
        path, old, new, says, named = WEAKENINGS[kind]
        _edit(repo, path, old, new)
        _commit(repo, f"{kind}\n\nTest-Weakened: {named} — C999: no such row")
        p = _range(repo)
        assert p.returncode == 1
        assert "Test-Weakened names C999, which is not a row of docs/OPEN_FINDINGS.md" in p.stderr
        assert says in p.stderr                 # and the weakening is still unnamed

    def test_a_trailer_naming_something_else_does_not_cover_it(self, repo, kind):
        path, old, new, says, _named = WEAKENINGS[kind]
        _edit(repo, path, old, new)
        _commit(repo, f"{kind}\n\nTest-Weakened: test_unrelated — C1: another change")
        p = _range(repo)
        assert p.returncode == 1 and says in p.stderr


class TestTheTrailer:
    def test_without_its_row_it_is_refused_even_naming_the_test(self, repo):
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 3")
        _commit(repo, "raise\n\nTest-Weakened: GAPS_CEILING raised, measured")
        p = _range(repo)
        assert p.returncode == 1
        assert "a Test-Weakened trailer without its ' — C<n>: <reason>'" in p.stderr
        assert "ceiling raised: GAPS_CEILING (2 -> 3)" in p.stderr

    def test_a_wrapped_trailer_is_read_whole_and_one_per_weakening(self, repo):
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 3")
        _edit(repo, "tests/test_lists.py", "POPULATION_FLOOR = 10", "POPULATION_FLOOR = 8")
        _commit(repo, "two\n\nTest-Weakened: GAPS_CEILING — C1: the reason runs\nonto a second "
                      "line\nTest-Weakened: tests/test_lists.py's\nPOPULATION_FLOOR — C2: "
                      "measured\nCo-Authored-By: t <t@example.com>")
        assert _range(repo).returncode == 0

    def test_one_trailer_does_not_cover_a_second_weakening_it_does_not_name(self, repo):
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 3")
        _edit(repo, "tests/test_a.py", "assert len(found) >= 3", "assert len(found) >= 2")
        _commit(repo, "two\n\nTest-Weakened: GAPS_CEILING — C1: measured")
        p = _range(repo)
        assert p.returncode == 1 and "len(found) (3 -> 2)" in p.stderr
        assert "GAPS_CEILING" not in p.stderr

    def test_the_row_is_read_at_the_commit_not_today(self, repo):
        """A row added by the same commit counts; the register is read at that commit."""
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 3")
        _edit(repo, "docs/OPEN_FINDINGS.md", "| C1 | **an open finding**",
              "| C7 | **the raise** | **[C]** open | tests/ |\n| C1 | **an open finding**")
        _commit(repo, "raise\n\nTest-Weakened: GAPS_CEILING — C7: recorded with it")
        assert _range(repo).returncode == 0

    def test_wk_reads_the_real_registers_open_and_closed_rows(self, wk):
        rows = wk.register_rows((ROOT / "docs" / "OPEN_FINDINGS.md").read_text())
        assert len(rows) >= 1000, len(rows)     # a floor: 1,290 rows read on 2026-10-18
        assert {"C1245", "C1243"} <= rows       # open (in D), and closed
        assert "C999999" not in rows


class TestWhatIsNotAWeakening:
    def test_a_refused_form_added(self, repo):
        """A `grows` list gaining a member is its direction: nothing to name."""
        _edit(repo, "tests/test_lists.py", ', "git clean": "git clean -fd"}',
              ', "git clean": "git clean -fd", "git reset --hard": "git reset --hard"}')
        _commit(repo, "a refused form more")
        assert _range(repo).returncode == 0

    def test_a_pure_rename(self, repo):
        _edit(repo, "tests/test_a.py", "def test_two(self):", "def test_two_renamed(self):")
        _commit(repo, "rename")
        assert _range(repo).returncode == 0

    def test_a_move_to_another_file(self, repo):
        _edit(repo, "tests/test_a.py", "def test_three():\n    found = [1, 2, 3]\n"
                                       "    assert len(found) >= 3\n", "")
        _write(repo, "tests/test_b.py", "def test_three():\n    assert True\n")
        _commit(repo, "move")
        assert _range(repo).returncode == 0

    def test_a_moved_test_takes_its_skip_with_it(self, repo):
        _edit(repo, "tests/test_a.py", "def test_three():", "@pytest.mark.xfail\n"
                                                             "def test_three():")
        _commit(repo, "xfail\n\nTest-Weakened: test_three — C1: measured")
        _edit(repo, "tests/test_a.py", "@pytest.mark.xfail\ndef test_three():\n"
                                       "    found = [1, 2, 3]\n    assert len(found) >= 3\n", "")
        _write(repo, "tests/test_b.py", "import pytest\n\n\n"
                                        "@pytest.mark.xfail\ndef test_three():\n"
                                        "    assert True\n")
        _commit(repo, "move")
        assert _range(repo).returncode == 0

    def test_a_list_that_shrank_a_ceiling_lowered_a_floor_raised(self, repo):
        _edit(repo, "tests/test_lists.py", '{"a": "why a", "b": "why b"}', '{"a": "why a"}')
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 1")
        _edit(repo, "tests/test_lists.py", "POPULATION_FLOOR = 10", "POPULATION_FLOOR = 12")
        _edit(repo, "tests/test_a.py", "assert len(found) >= 3", "assert len(found) >= 4")
        _commit(repo, "tighter")
        assert _range(repo).returncode == 0

    def test_a_reason_edited_is_no_new_member(self, repo):
        _edit(repo, "tests/test_lists.py", '"why b"', '"why b, measured again"')
        _commit(repo, "reworded")
        assert _range(repo).returncode == 0

    def test_a_new_test_with_its_own_guard(self, repo):
        _write(repo, "tests/test_c.py", "import pytest\n\n\ndef test_in_a_browser():\n"
                                        "    pytest.skip(\"no real browser here\")\n")
        _commit(repo, "a new browser test")
        assert _range(repo).returncode == 0

    def test_a_pragma_in_prose_is_not_a_pragma(self, repo):
        _edit(repo, "modules/m.py", "def f(x):\n", "def f(x):\n    \"\"\"No `pragma: no cover`"
                                                  " here.\"\"\"\n")
        _commit(repo, "a docstring")
        assert _range(repo).returncode == 0


class TestTheRange:
    def test_two_commits_name_the_one_that_weakened(self, repo):
        _edit(repo, "tests/test_lists.py", "POPULATION_FLOOR = 10", "POPULATION_FLOOR = 11")
        good = _commit(repo, "tighter")
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 5")
        bad = _commit(repo, "looser")
        p = _run(repo, "--range", "HEAD~2..HEAD")
        assert p.returncode == 1
        assert f"REFUSED: {bad[:12]} tests/test_lists.py: ceiling raised" in p.stderr
        assert good[:12] not in p.stderr and p.stderr.count("REFUSED") == 1

    def test_each_commit_is_judged_against_its_own_parent(self, repo):
        """A weakening undone by the next commit is still the first commit's."""
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 5")
        bad = _commit(repo, "looser")
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 5", "GAPS_CEILING = 2")
        _commit(repo, "back")
        p = _run(repo, "--range", "HEAD~2..HEAD")
        assert p.returncode == 1 and bad[:12] in p.stderr

    def test_a_later_commit_is_not_charged_with_an_earlier_ones_weakening(self, repo):
        """Judged against the range's start, the second commit would carry the first's raise."""
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 5")
        _commit(repo, "looser\n\nTest-Weakened: GAPS_CEILING — C1: measured")
        _edit(repo, "tests/test_lists.py", "def test_gaps():", "def test_gaps():  # unchanged")
        _commit(repo, "a comment")
        p = _run(repo, "--range", "HEAD~2..HEAD")
        assert p.returncode == 0, p.stderr

    def test_a_range_git_cannot_read_is_not_a_pass(self, repo):
        p = _run(repo, "--range", "nosuch..HEAD")
        assert p.returncode == 2 and "COULD NOT ASK" in p.stderr

    def test_an_entry_taken_out_of_the_registry_is_still_held_that_commit(self, repo):
        _edit(repo, "tests/ratchet_lists.py", '    ("tests/test_lists.py", "GAPS_CEILING", '
                                              '"ceiling"),\n', "")
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 3")
        _commit(repo, "unregister and raise")
        p = _range(repo)
        assert p.returncode == 1
        assert "ceiling raised: GAPS_CEILING (2 -> 3)" in p.stderr
        assert "ratchet unregistered while its list remains" in p.stderr


class TestTheCommitBeingMade:
    def test_the_staged_diff_and_the_message_are_read(self, repo, tmp_path_factory):
        _edit(repo, "tests/test_lists.py", "GAPS_CEILING = 2", "GAPS_CEILING = 3")
        _git(repo, "add", "-A")
        msg = tmp_path_factory.mktemp("m") / "MSG"
        msg.write_text("raise\n\n# Test-Weakened: GAPS_CEILING — C1: git's template, not said\n")
        p = _run(repo, "--message", str(msg))
        assert p.returncode == 1 and "REFUSED: the commit being made tests/test_lists.py" \
            in p.stderr
        msg.write_text("raise\n\nTest-Weakened: GAPS_CEILING — C1: measured\n")
        assert _run(repo, "--message", str(msg)).returncode == 0

    def test_the_hook_runs_both_checks(self):
        hook = (ROOT / "scripts" / "hooks" / "commit-msg").read_text()
        assert 'nmas-host-step-check" --message "$1"' in hook
        assert 'nmas-test-weakening-check" --message "$1"' in hook
        # Neither replaces the shell, so the second runs whatever the first answered.
        assert not re.search(r"^\s*exec\b", hook, re.M), hook

    def test_the_hook_refuses_when_either_refuses(self, tmp_path):
        """The hook's own logic, run with stand-ins for the two checks."""
        for first, second, want in ((0, 0, 0), (1, 0, 1), (0, 1, 1)):
            root = tmp_path / f"r{first}{second}"
            (root / "scripts" / "hooks").mkdir(parents=True)
            hook = (ROOT / "scripts" / "hooks" / "commit-msg").read_text()
            (root / "scripts" / "hooks" / "commit-msg").write_text(hook)
            for name, code in (("nmas-host-step-check", first),
                               ("nmas-test-weakening-check", second)):
                (root / "scripts" / name).write_text(f"import sys\nsys.exit({code})\n")
            _git(root, "init", "-q")
            p = subprocess.run(["sh", str(root / "scripts" / "hooks" / "commit-msg"), "MSG"],
                               cwd=root, capture_output=True, text=True)
            assert p.returncode == want, (first, second, p.returncode, p.stderr)

    def test_ci_runs_it_over_the_pushed_range_as_the_others_do(self):
        doc = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
        steps = doc["jobs"]["test"]["steps"]
        host = next(s for s in steps if 'nmas-host-step-check --range "$RANGE"' in s.get("run", ""))
        mine = next(s for s in steps
                    if 'nmas-test-weakening-check --range "$RANGE"' in s.get("run", ""))
        # Shard a, or the doc shard a docs-only push runs alone (its matrix has no a): every
        # pushed range is still checked once.
        assert mine["if"] == host["if"] == "matrix.shard == 'a' || matrix.shard == 'docs'"
        assert mine["env"] == host["env"]
        assert mine["run"].replace("nmas-test-weakening-check", "X") == \
            host["run"].replace("nmas-host-step-check", "X")


# --- The registry of ratchets is complete -----------------------------------------------------

#: The stems a ratchet's name carries (the lists CLAUDE.md and docs/PHASE7_BURNDOWN.md section 3
#: name, and the rest found by reading, 2026-10-18).
STEMS = re.compile(r"EXCUS|EXEMPT|EXCEPTION|KNOWN|GAP|ALLOW|PENDING|UNCHECKED|UNDRAWN|UNREACH|"
                   r"UNSIGNED|UNHELD|MISSING|NOT_YET|CEILING|FLOOR|PHANTOM|EMPTY|EQUIVALENT|"
                   r"SECOND_IMPL|ON_TODAYS|UPSTREAM|NON_GUI|STILL_|RETROFIT|UNESCAPED|"
                   r"FALSE_GREEN|UNDECLARED|INVENTORY|LEGACY|DEAD|DUPLICATE|LEAK|WAIVE|TOLERAT|"
                   r"SKIP")
#: A comment that declares the name beneath (or beside) it a ratchet.
DECLARED = re.compile(r"only\s+(?:ever\s+)?(?:shrinks?|goes\s+down|go\s+down|falls?|down)\b|"
                      r"never\s+rises?|may\s+only\s+(?:fall|shrink)", re.I)


def _ratchet_shaped(value):
    """A value a ratchet can be: a collection, a comprehension, an empty-collection call or a
    number (a string, a pattern or an object is never one)."""
    if isinstance(value, (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.DictComp, ast.SetComp,
                          ast.ListComp)):
        return True
    if isinstance(value, ast.Constant):
        return isinstance(value.value, (int, float)) and not isinstance(value.value, bool)
    return isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and \
        value.func.id in ("set", "frozenset", "dict", "tuple", "list")


def ratchet_candidates(path, text):
    """[(path, name)] of the module-level assignments in *text* a ratchet's property finds: an
    upper-case name carrying a stem, or one whose comment says it only shrinks."""
    lines = text.splitlines()
    out = []
    for node in ast.parse(text).body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for t in targets:
            if not isinstance(t, ast.Name) or t.id != t.id.upper() or \
                    not _ratchet_shaped(node.value):
                continue
            comment, i = [lines[node.lineno - 1]], node.lineno - 2
            while i >= 0 and lines[i].lstrip().startswith("#"):
                comment.append(lines[i])
                i -= 1
            if STEMS.search(t.id) or DECLARED.search("\n".join(comment)):
                out.append((path, t.id))
    return out


#: A test that drives a hook under scripts/hooks/ (its path written out or joined).
HOOK_TEST = re.compile(r"scripts/hooks/|[\"']hooks[\"']")


def refused_form_lists(path, text):
    """[(path, name)]: a hook test's refused forms (the operator, 2026-10-26): each module-level
    collection named REFUSED... in a test that drives a hook. Each is a `grows` ratchet, so a
    refusal the test stops asserting needs a Test-Weakened trailer."""
    if not HOOK_TEST.search(text):
        return []
    out = []
    for node in ast.parse(text).body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        out += [(path, t.id) for t in targets
                if isinstance(t, ast.Name) and t.id.startswith("REFUSED")
                and _ratchet_shaped(node.value) and not isinstance(node.value, ast.Constant)]
    return out


def _population():
    found = []
    for p in tracked("tests", "modules", suffix=".py", root=ROOT):
        rel = os.path.relpath(p, ROOT)
        found += ratchet_candidates(rel, Path(p).read_text(encoding="utf-8"))
    return found


class TestEveryHookTestsRefusedFormsGrow:
    """The operator, 2026-10-26: any hook test's refused-form list is declared `grows` in
    tests/ratchet_lists.py, as ratchet-looking lists already are, so the next hook needs no
    register row to be held."""

    def test_every_one_is_declared_grows(self):
        from tests.ratchet_lists import RATCHETS
        grows = {(f, n) for f, n, k in RATCHETS if k == "grows"}
        found = []
        for p in tracked("tests", suffix=".py", root=ROOT):
            rel = os.path.relpath(p, ROOT)
            found += refused_form_lists(rel, Path(p).read_text(encoding="utf-8"))
        assert len(found) >= 6, found           # the floor: 6 found on 2026-10-26
        missing = sorted(c for c in found if c not in grows)
        assert missing == [], (
            "a hook test's refused-form list that tests/ratchet_lists.py does not declare "
            f"`grows`: {missing}")

    def test_the_scan_finds_a_planted_one_and_only_in_a_hook_test(self):
        planted = ('HOOK = os.path.join(ROOT, "scripts", "hooks", "x")\n'
                   'REFUSED = {"a": "cmd a"}\nREFUSED_BASH = ["cmd b"]\nREFUSED_COUNT = 3\n'
                   'ALLOWED = {"c": "cmd c"}\n')
        assert refused_form_lists("tests/p.py", planted) == [
            ("tests/p.py", "REFUSED"), ("tests/p.py", "REFUSED_BASH")]
        assert refused_form_lists("tests/q.py", 'REFUSED = {"a": "cmd a"}\n') == []


class TestTheRegistryIsComplete:
    def test_every_ratchet_the_scan_finds_is_registered_or_reasoned(self):
        from tests.ratchet_lists import NOT_RATCHETS, RATCHETS
        registered = {(f, n) for f, n, _k in RATCHETS}
        found = _population()
        assert len(found) >= 110, len(found)    # the floor: 125 found on 2026-10-18
        missing = [c for c in found if c not in registered and c not in NOT_RATCHETS]
        assert missing == [], (
            "a list or number shaped like a ratchet that tests/ratchet_lists.py neither "
            f"declares in RATCHETS nor excuses in NOT_RATCHETS with why: {missing}")

    def test_the_scan_finds_a_planted_ratchet_both_ways(self):
        planted = ("import re\n\nKNOWN_GAPS = {'x': 'why'}\nLIMIT_NAME = 'a string'\n"
                   "PATTERN_ALLOWED = re.compile('x')\n\n# Each with why. Only shrinks.\n"
                   "HELD_ELSEWHERE = {'y': 'why'}\nBOUND = 3  # never rises\n")
        assert ratchet_candidates("tests/planted.py", planted) == [
            ("tests/planted.py", "KNOWN_GAPS"), ("tests/planted.py", "HELD_ELSEWHERE"),
            ("tests/planted.py", "BOUND")]

    def test_every_entry_exists_and_reads_as_its_kind(self, wk):
        from tests.ratchet_lists import RATCHETS
        assert len(RATCHETS) >= 90, len(RATCHETS)
        bad = []
        for path, name, kind in RATCHETS:
            assert kind in wk.KINDS, (path, name, kind)
            text = (ROOT / path).read_text(encoding="utf-8")
            value = wk.read_ratchet(text, path, name)
            if value in (wk.ABSENT, wk.UNREADABLE):
                bad.append((path, name, "absent or unreadable"))
            elif kind in ("shrinks", "grows") and wk.members(value) is wk.UNREADABLE:
                bad.append((path, name, "members unreadable"))
            elif kind in ("ceiling", "floor") and wk._numeric(value) is wk.UNREADABLE:
                bad.append((path, name, "not a number"))
            elif kind in ("ceilings", "floors") and wk._table(value) is wk.UNREADABLE:
                bad.append((path, name, "not a table of numbers"))
            elif kind == "uncovered" and wk._uncovered(value) is wk.UNREADABLE:
                bad.append((path, name, "no functions and covered_unit"))
        assert bad == [], bad

    def test_no_excuse_outlives_its_name(self):
        from tests.ratchet_lists import NOT_RATCHETS
        found = set(_population())
        assert [k for k in NOT_RATCHETS if k not in found] == []


class TestTheReaders:
    def test_a_comprehension_has_the_members_it_makes(self, wk):
        tree = ast.parse("X = {f'{r} {k}': 1 for r in ('GET /a',) for k in ('p', 'q')}")
        assert set(wk.members(tree.body[0].value)) == {"'GET /a p'", "'GET /a q'"}

    def test_a_records_reason_is_not_its_identity_and_its_count_is_its_weight(self, wk):
        tree = ast.parse("X = {'f.py': (4, 'why'), 'g.py': [('a b', 'why')]}")
        assert wk.members(tree.body[0].value) == {"'f.py'": 4, "'g.py'": None,
                                                  "'g.py' 'a b'": None}

    def test_a_count_risen_in_a_record_is_refused(self, wk):
        was = ast.parse("X = {'f.py': (4, 'why')}").body[0].value
        now = ast.parse("X = {'f.py': (5, 'why, again')}").body[0].value
        [w] = wk.judge_ratchet("tests/t.py", "X", "shrinks", was, now)
        assert w.what == "a member's count rose" and "'f.py': 4 -> 5" in w.after

    def test_a_refused_form_is_whole_two_sharing_a_first_item_are_two(self, wk):
        """A `grows` list's member is the whole form: in a `shrinks` list a record's last item
        is its reason, but ("Write", {...a}) and ("Write", {...b}) are two refused forms, and
        removing either is refused (tests/test_claude_md_edit_hook.py's REFUSED_FILE)."""
        was = ast.parse("X = [('Write', {'p': 'a'}), ('Write', {'p': 'b'})]").body[0].value
        now = ast.parse("X = [('Write', {'p': 'a'})]").body[0].value
        [w] = wk.judge_ratchet("tests/t.py", "X", "grows", was, now)
        assert w.what == "list removed from" and "Write" in w.after and "'b'" in w.after
        assert wk.judge_ratchet("tests/t.py", "X", "shrinks", now, was) == [], \
            "a shrinks list still reads a record's last item as its reason"

    def test_the_coverage_baselines_uncovered_count(self, wk):
        was = {"modules/a.py": {"functions": 10, "covered_unit": 8}}
        now = {"modules/a.py": {"functions": 11, "covered_unit": 8}}
        [w] = wk.judge_ratchet("tests/coverage_baseline.json", "modules", "uncovered", was, now)
        assert "modules/a.py: 2 -> 3 uncovered" in w.after
        less = {"modules/a.py": {"functions": 9, "covered_unit": 7}}
        assert wk.judge_ratchet("tests/coverage_baseline.json", "modules", "uncovered",
                                was, less) == []

    def test_a_ceiling_that_stops_being_a_number_is_refused(self, wk):
        was = ast.parse("C = 3").body[0].value
        now = ast.parse("C = len(SOMETHING)").body[0].value
        [w] = wk.judge_ratchet("tests/t.py", "C", "ceiling", was, now)
        assert w.what == "ceiling no longer a number"

    def test_bounds_in_asserts_are_read_both_ways_round(self, wk):
        tree = ast.parse("N = 5\n\ndef test_x():\n    assert len(a) >= 3\n    assert 7 >= b\n"
                         "    assert c > 2\n    assert d <= N\n")
        assert wk.assert_bounds(tree) == {
            ("test_x", "len(a)", "floor"): [3], ("test_x", "b", "ceiling"): [7],
            ("test_x", "c", "floor"): [3], ("<module>", "N", "ceiling"): [5]}

    def test_the_pragma_is_counted_from_comments_only(self, wk):
        text = "def f():\n    s = '# pragma: no cover'\n    return s  # pragma: no cover\n"
        assert wk.pragma_sites(text) == {("f", "pragma: no cover"): 1}
