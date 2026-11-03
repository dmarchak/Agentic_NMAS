"""The bypass scanner (board TI, item 3; docs/TEST_INTEGRITY.md): `scripts/nmas-bypass-scan`
names each way past a test or a guard that a commit ADDS, and refuses it until the commit gives
its reason, `Bypass: <file>:<line> — <reason>`.

Driven as a subprocess against REAL git repositories built here (a package and a tests/ folder,
a base commit and a commit on it):

- **Each kind found, and excused by its trailer:** a skip, skipif and xfail decorator and the
  `pytest.skip(`, `pytest.xfail(` and `pytest.importorskip(` calls; `pragma: no cover`; noqa; a
  bare, `Exception`, `BaseException` and tuple `except` in a test; a monkeypatch or mock of the
  module the test file is named for (by its import, an alias, a patch string, `patch.object`);
  a bound raised at module and class level and a `timeout=` raised at its call site; a guarded
  word built from pieces by `+`, an f-string, a join, `chr`, `.format`, adjacent literals, and
  C2345's exact `"config" + "_repo"`; each with its kind, `file:line` and how it was found.
- **Added only:** every kind already on the parent is not named again; a skip moved to another
  file with its test is credited; "noqa" and "pragma: no cover" inside strings are not
  comments; a lowered bound is nothing; a mock of another module is nothing.
- **The trailer:** one without its reason excuses nothing and is refused; one naming another
  line does not excuse, and is said.
- **Which commit:** the commit being made is the index against HEAD with the message file's
  trailers, nothing written; a temporary index is exit 2; as a real commit-msg hook it refuses
  the commit and, with the trailer, lets it be made; a range names the one commit it refuses;
  an unreadable commit is exit 2; a file that does not parse is matched as text, and says so.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "nmas-bypass-scan"
#: One run of the script on these repositories: measured 2026-11-03 on the laptop at about
#: 0.15 s. Not 2.5 times that: it is the backstop for a hung child (git's own calls are
#: bounded inside, at 30 s each).
RUN_TIMEOUT = 60

CALC = '''import subprocess

TIMEOUT = 30


class Conf:
    MAX_ROWS = 10


def double(x):
    return x * 2


def run():
    return subprocess.run(["true"], timeout=5)
'''

TESTS = '''import pytest

from pkg import calc


def test_double():
    assert calc.double(2) == 4


def test_zero():
    assert calc.double(0) == 0
'''

#: One of every kind, already on the parent.
TESTS_FULL = '''import subprocess  # noqa: F401
from unittest import mock

import pytest

from pkg import calc

STORE = "config" + "_repo"


@pytest.mark.skip(reason="held")
def test_held():
    assert calc.double(2) == 4


def test_guarded(monkeypatch):
    monkeypatch.setattr(calc, "double", lambda x: 4)
    with mock.patch("pkg.calc.run"):
        try:
            assert calc.double(1) == 4
        except Exception:  # pragma: no cover
            pytest.skip("never")
'''


def _env(**more):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com", **more)
    return env


def _git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], check=check, env=_env(),
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


def _make(tmp_path, files):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _commit(root, files, "start")
    return root


@pytest.fixture
def repo(tmp_path):
    return _make(tmp_path, {"pytest.ini": "[pytest]\npythonpath = .\n", "pkg/__init__.py": "",
                            "pkg/calc.py": CALC, "tests/test_calc.py": TESTS})


def run(repo, *args, message=None, **env):
    if message is not None:
        msg = repo.parent / "message.txt"
        msg.write_text(message)
        args = (*args, "--message", str(msg))
    return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), *args],
                          capture_output=True, text=True, env=_env(**env), timeout=RUN_TIMEOUT)


def line_of(text, needle):
    """The 1-based line of *text* holding *needle*, which must be there exactly once."""
    hits = [i for i, row in enumerate(text.splitlines(), 1) if needle in row]
    assert len(hits) == 1, (needle, hits)
    return hits[0]


def _sub(text, old, new):
    assert old in text, old
    return text.replace(old, new, 1)


def _test(body):
    return TESTS + "\n\n" + body.strip("\n") + "\n"


# --- the planted cases: (files changed, kind, path, needle, how it is found) ------------------

def _t(text):
    return {"tests/test_calc.py": text}


def _c(text):
    return {"pkg/calc.py": text}


AST, COMMENT, CALLSITE, ADJACENT = ("parsed: ast", "parsed: tokenize, a comment token",
                                    "parsed: ast, the call site", "adjacent string literals")
CASES = {
    # 1. skips
    "skip decorator": (_t(_sub(TESTS, "def test_zero", "@pytest.mark.skip(reason='slow')\n"
                               "def test_zero")), "skip", "tests/test_calc.py",
                       "@pytest.mark.skip(", AST),
    "skipif decorator": (_t(_sub(TESTS, "def test_zero", "@pytest.mark.skipif(True, reason='x')"
                                 "\ndef test_zero")), "skip", "tests/test_calc.py",
                         "@pytest.mark.skipif(", AST),
    "xfail decorator": (_t(_sub(TESTS, "def test_zero", "@pytest.mark.xfail(reason='x')\n"
                                "def test_zero")), "skip", "tests/test_calc.py",
                        "@pytest.mark.xfail(", AST),
    "pytest.skip call": (_t(_sub(TESTS, "    assert calc.double(0)", "    pytest.skip('no')\n"
                                 "    assert calc.double(0)")), "skip", "tests/test_calc.py",
                         "pytest.skip(", AST),
    "pytest.xfail call": (_t(_sub(TESTS, "    assert calc.double(0)", "    pytest.xfail('no')"
                                  "\n    assert calc.double(0)")), "skip", "tests/test_calc.py",
                          "pytest.xfail(", AST),
    "pytest.importorskip call": (_t(_sub(TESTS, "    assert calc.double(0)",
                                         "    pytest.importorskip('numpy')\n"
                                         "    assert calc.double(0)")), "skip",
                                 "tests/test_calc.py", "pytest.importorskip(", AST),
    # 2, 3. comments
    "pragma no cover": (_c(_sub(CALC, "def run():", "def run():  # pragma: no cover")),
                        "pragma: no cover", "pkg/calc.py", "pragma", COMMENT),
    "noqa": (_c(_sub(CALC, "import subprocess", "import subprocess  # noqa: F401")), "noqa",
             "pkg/calc.py", "noqa", COMMENT),
    # 4. broad excepts
    "bare except": (_t(_test("def test_g():\n    try:\n        calc.double(None)\n"
                             "    except:\n        pass\n")), "broad except",
                    "tests/test_calc.py", "except:", AST),
    "except Exception": (_t(_test("def test_g():\n    try:\n        calc.double(None)\n"
                                  "    except Exception:\n        pass\n")), "broad except",
                         "tests/test_calc.py", "except Exception", AST),
    "except BaseException": (_t(_test("def test_g():\n    try:\n        calc.double(None)\n"
                                      "    except BaseException:\n        pass\n")),
                             "broad except", "tests/test_calc.py", "except BaseException", AST),
    "except in a tuple": (_t(_test("def test_g():\n    try:\n        calc.double(None)\n"
                                   "    except (ValueError, Exception):\n        pass\n")),
                          "broad except", "tests/test_calc.py", "except (ValueError", AST),
    # 5. a mock of the module the file is named for
    "monkeypatch.setattr": (_t(_test("def test_m(monkeypatch):\n    monkeypatch.setattr(calc, "
                                     "'double', lambda x: 4)\n    assert calc.double(1) == 4\n")),
                            "mock of the module under test", "tests/test_calc.py",
                            "monkeypatch.setattr(", AST),
    "monkeypatch.setattr of a string": (_t(_test(
        "def test_m(monkeypatch):\n    monkeypatch.setattr('pkg.calc.double', lambda x: 4)\n"
        "    assert calc.double(1) == 4\n")), "mock of the module under test",
        "tests/test_calc.py", "monkeypatch.setattr(", AST),
    "mock.patch string": (_t(_sub(TESTS, "import pytest", "from unittest import mock\n\nimport "
                                  "pytest") + "\n\ndef test_m():\n    with mock.patch("
                             "'pkg.calc.double', return_value=4):\n        assert "
                             "calc.double(1) == 4\n"), "mock of the module under test",
                          "tests/test_calc.py", "mock.patch(", AST),
    "patch.object": (_t(_sub(TESTS, "import pytest", "from unittest.mock import patch\n\nimport "
                             "pytest") + "\n\ndef test_m():\n    with patch.object(calc, 'double',"
                        " return_value=4):\n        assert calc.double(1) == 4\n"),
                     "mock of the module under test", "tests/test_calc.py", "patch.object(",
                     AST),
    "an alias of the module": (_t(_sub(TESTS, "from pkg import calc", "from pkg import calc\n"
                                       "from pkg import calc as c") + "\n\ndef test_m("
                                  "monkeypatch):\n    monkeypatch.setattr(c, 'double', lambda x:"
                                  " 4)\n    assert c.double(1) == 4\n"),
                               "mock of the module under test", "tests/test_calc.py",
                               "monkeypatch.setattr(", AST),
    # 6. a raised bound
    "module constant raised": (_c(_sub(CALC, "TIMEOUT = 30", "TIMEOUT = 60")), "raised bound",
                               "pkg/calc.py", "TIMEOUT = 60", AST),
    "class constant raised": (_c(_sub(CALC, "MAX_ROWS = 10", "MAX_ROWS = 20")), "raised bound",
                              "pkg/calc.py", "MAX_ROWS = 20", AST),
    "arithmetic raised": (_c(_sub(CALC, "TIMEOUT = 30", "TIMEOUT = 2 * 60")), "raised bound",
                          "pkg/calc.py", "TIMEOUT = 2 * 60", AST),
    "timeout= raised": (_c(_sub(CALC, "timeout=5", "timeout=50")), "raised bound",
                        "pkg/calc.py", "timeout=50", CALLSITE),
    # 7. a guarded word built from pieces
    "C2345's shape": (_c(CALC + '\nSTORE = "config" + "_repo"\n'),
                      "guarded word built from pieces", "pkg/calc.py", "STORE =", AST),
    "an f-string of literals": (_c(CALC + "\nSTORE = f\"golden{'_configs'}\"\n"),
                                "guarded word built from pieces", "pkg/calc.py", "STORE =",
                                AST),
    "a join of literals": (_c(CALC + '\nSTORE = "".join(["pre", "_change"])\n'),
                           "guarded word built from pieces", "pkg/calc.py", "STORE =", AST),
    "chr": (_c(CALC + '\nSTORE = "config" + chr(95) + "repo"\n'),
            "guarded word built from pieces", "pkg/calc.py", "STORE =", AST),
    "format": (_c(CALC + '\nSTORE = "{}_repo".format("config")\n'),
               "guarded word built from pieces", "pkg/calc.py", "STORE =", AST),
    "adjacent literals": (_c(CALC + '\nSTORE = ("back"\n         "ups")\n'),
                          "guarded word built from pieces", "pkg/calc.py", "STORE =", ADJACENT),
    "a test path": (_c(CALC + '\nWHERE = "tes" + "ts/test_calc.py"\n'),
                    "guarded word built from pieces", "pkg/calc.py", "WHERE =", AST),
    "after a variable": (_c(CALC + '\ndef where(base):\n    return base + "config" + "_repo"\n'),
                         "guarded word built from pieces", "pkg/calc.py", "return base", AST),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_each_kind_is_found_named_and_excused_by_its_trailer(repo, case):
    files, kind, path, needle, how = CASES[case]
    _commit(repo, files, f"plant: {case}")
    line = line_of(files[path], needle)
    r = run(repo, "--commit", "HEAD")
    assert r.returncode == 1, r.stdout + r.stderr
    found = [x for x in r.stdout.splitlines() if x.startswith("  REFUSED")]
    assert len(found) == 1, r.stdout
    assert f"  {kind}  {path}:{line}  " in found[0], found[0]
    assert how in found[0], found[0]
    assert f"excuse with: Bypass: {path}:{line} — <reason>" in r.stderr
    r = run(repo, "--commit", "HEAD",
            message=f"plant: {case}\n\nBypass: {path}:{line} — a reason given\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "excused" in r.stdout and "a reason given" in r.stdout
    assert "1 found, 1 excused, 0 refused" in r.stdout


def test_the_reason_in_the_commit_s_own_message_excuses_it(repo):
    text = _sub(TESTS, "    assert calc.double(0)", "    pytest.skip('no')\n    assert calc."
                "double(0)")
    line = line_of(text, "pytest.skip(")
    _commit(repo, _t(text), f"Skip it\n\nBypass: tests/test_calc.py:{line} - the lab is down\n")
    r = run(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "the lab is down" in r.stdout


def test_c2345_s_exact_shape_is_found_in_a_script_without_an_extension(repo):
    """C2345's scratch audit, committed as a script: a python `#!` file, no `.py`, the folder's
    name built from two literals so the config-read hook's words would not match it."""
    text = ('#!/usr/bin/env python3\nimport sys\n\nFOLDER = "config" + "_repo"\n\n\n'
            'def main(base):\n    return base + "/" + FOLDER\n')
    _commit(repo, {"scripts/audit": text})
    r = run(repo)
    assert r.returncode == 1
    row = next(x for x in r.stdout.splitlines() if x.startswith("  REFUSED"))
    assert f"scripts/audit:{line_of(text, 'FOLDER =')}" in row
    assert "'config' + '_repo' makes 'config_repo'" in row
    assert "claude-no-raw-config-reads" in row and "no piece does" in row


@pytest.mark.parametrize("word", ["config_repo", "golden_configs", "pre_change", "backups",
                                  "data/lists", "config_cache", "tests/"])
def test_every_guarded_word_built_from_two_halves_is_found(repo, word):
    """The guarded words: the config-read hook's store names, read from the hook, and tests/."""
    half = len(word) // 2
    text = CALC + f'\nWORD = "{word[:half]}" + "{word[half:]}"\n'
    _commit(repo, _c(text))
    r = run(repo)
    assert r.returncode == 1, r.stdout
    assert f"pkg/calc.py:{line_of(text, 'WORD =')}" in r.stdout


# --- added only -----------------------------------------------------------------------------

def test_a_commit_adding_none_passes_and_says_so(repo):
    _commit(repo, _t(_test("def test_more():\n    assert calc.double(3) == 6\n")))
    r = run(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no bypass added: passes" in r.stdout


def test_every_kind_already_on_the_parent_is_not_named_again(tmp_path):
    full_calc = (_sub(_sub(CALC, "def run():", "def run():  # pragma: no cover"),
                      "import subprocess", "import subprocess  # noqa: F401")
                 + '\nSTORE = ("back"\n         "ups")\n')
    repo = _make(tmp_path, {"pkg/__init__.py": "", "pkg/calc.py": full_calc,
                            "tests/test_calc.py": TESTS_FULL})
    _commit(repo, {"tests/test_calc.py": TESTS_FULL + "\n\ndef test_more():\n    assert "
                   "calc.double(3) == 6\n",
                   "pkg/calc.py": full_calc + "\n\ndef triple(x):\n    return x * 3\n"})
    r = run(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no bypass added: passes" in r.stdout


def test_a_second_skip_beside_one_on_the_parent_is_named_once(tmp_path):
    repo = _make(tmp_path, {"pkg/__init__.py": "", "pkg/calc.py": CALC,
                            "tests/test_calc.py": TESTS_FULL})
    text = TESTS_FULL + '''

@pytest.mark.skip(reason="held")
def test_also():
    pass
'''
    _commit(repo, _t(text))
    r = run(repo)
    assert r.returncode == 1
    rows = [x for x in r.stdout.splitlines() if x.startswith("  REFUSED")]
    assert len(rows) == 1, r.stdout
    assert f"tests/test_calc.py:{len(text.splitlines()) - 2}" in rows[0]


def test_a_skip_moved_to_another_file_with_its_test_is_credited(tmp_path):
    held = '@pytest.mark.skip(reason="held")\ndef test_held():\n    assert calc.double(2) == 4\n'
    repo = _make(tmp_path, {"pkg/__init__.py": "", "pkg/calc.py": CALC,
                            "tests/test_calc.py": TESTS + "\n\n" + held})
    _commit(repo, {"tests/test_calc.py": TESTS,
                   "tests/test_other.py": "import pytest\n\nfrom pkg import calc\n\n\n" + held})
    r = run(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "moved from another file (credited)" in r.stdout


def test_noqa_and_pragma_inside_strings_are_not_comments(repo):
    _commit(repo, _c(CALC + '\nMSG = "# noqa: E501 and # pragma: no cover"\n\n\ndef said():\n'
                     '    """A docstring naming # noqa and # pragma: no cover."""\n'
                     '    return MSG\n'))
    r = run(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no bypass added: passes" in r.stdout


def test_a_lowered_bound_is_nothing(repo):
    _commit(repo, _c(_sub(_sub(_sub(CALC, "TIMEOUT = 30", "TIMEOUT = 10"), "MAX_ROWS = 10",
                               "MAX_ROWS = 5"), "timeout=5", "timeout=1")))
    r = run(repo)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no bypass added: passes" in r.stdout


def test_a_mock_of_another_module_is_nothing(repo):
    _commit(repo, _t(_sub(TESTS, "import pytest", "import subprocess\n\nimport pytest")
                     + "\n\ndef test_m(monkeypatch):\n    monkeypatch.setattr(subprocess, 'run',"
                     " lambda *a, **k: None)\n    assert calc.double(1) == 2\n"))
    r = run(repo)
    assert r.returncode == 0, r.stdout + r.stderr


def test_one_literal_holding_a_guarded_word_is_not_built(repo):
    _commit(repo, _c(CALC + '\nSTORE = "config_repo"\nWHERE = "tests/" + "test_calc.py"\n'))
    r = run(repo)
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_file_that_does_not_parse_is_matched_as_text_and_says_so(repo):
    text = TESTS + "\n\ndef test_broken(:\n    pytest.skip('no')\n"
    _commit(repo, _t(text))
    r = run(repo)
    assert r.returncode == 1
    row = next(x for x in r.stdout.splitlines() if x.startswith("  REFUSED"))
    assert f"skip  tests/test_calc.py:{line_of(text, 'pytest.skip(')}" in row
    assert "text: the file does not parse at the commit" in row


def test_where_the_parent_does_not_parse_only_the_lines_the_commit_adds_count(tmp_path):
    held = _sub(TESTS, "def test_zero", "@pytest.mark.skip(reason='held')\ndef test_zero")
    repo = _make(tmp_path, {"pkg/__init__.py": "", "pkg/calc.py": CALC,
                            "tests/test_calc.py": held + "\n\ndef broken(:\n    pass\n"})
    text = _sub(held, "    assert calc.double(2)", "    pytest.skip('no')\n    assert "
                "calc.double(2)") + "\n\ndef broken():\n    pass\n"
    _commit(repo, _t(text))
    r = run(repo)
    assert r.returncode == 1
    rows = [x for x in r.stdout.splitlines() if x.startswith("  REFUSED")]
    assert len(rows) == 1, r.stdout
    assert f"tests/test_calc.py:{line_of(text, 'pytest.skip(')}" in rows[0]
    assert "the parent's does not parse, so only the lines the commit adds count" in rows[0]


# --- the trailer ----------------------------------------------------------------------------

def _plant_noqa(repo):
    text = _sub(CALC, "import subprocess", "import subprocess  # noqa: F401")
    _commit(repo, _c(text))
    return line_of(text, "noqa")


def test_a_trailer_without_its_reason_excuses_nothing_and_is_refused(repo):
    line = _plant_noqa(repo)
    for bare in (f"Bypass: pkg/calc.py:{line}\n", f"Bypass: pkg/calc.py:{line} —\n"):
        r = run(repo, "--commit", "HEAD", message="x\n\n" + bare)
        assert r.returncode == 1, (bare, r.stdout)
        assert "it excuses nothing" in r.stderr
        assert f"REFUSED  noqa  pkg/calc.py:{line}" in r.stdout


def test_a_trailer_naming_another_line_does_not_excuse_and_is_said(repo):
    line = _plant_noqa(repo)
    r = run(repo, "--commit", "HEAD", message=f"x\n\nBypass: pkg/calc.py:{line + 1} — near\n")
    assert r.returncode == 1
    assert f"Bypass: pkg/calc.py:{line + 1} names no finding of this commit" in r.stdout


# --- which commit ---------------------------------------------------------------------------

def test_the_commit_being_made_is_the_index_against_head(repo):
    text = _sub(CALC, "import subprocess", "import subprocess  # noqa: F401")
    _write(repo, _c(text))
    _git(repo, "add", "-A")
    head, status = _git(repo, "rev-parse", "HEAD"), _git(repo, "status", "--porcelain")
    r = run(repo, message="Staged\n")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "the commit being made" in r.stdout and "the commit being made" in r.stderr
    line = line_of(text, "noqa")
    r = run(repo, message=f"Staged\n# a comment line\n\nBypass: pkg/calc.py:{line} — needed\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _git(repo, "rev-parse", "HEAD") == head
    assert _git(repo, "status", "--porcelain") == status


def test_a_temporary_index_is_refused_never_guessed_at(repo):
    r = run(repo, message="commit -a\n", GIT_INDEX_FILE=".git/index.tmp")
    assert r.returncode == 2
    assert "COULD NOT ASK" in r.stderr and "GIT_INDEX_FILE" in r.stderr


def test_as_a_commit_msg_hook_it_refuses_the_commit_and_passes_it_with_its_trailer(repo):
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{SCRIPT}" --repo "$(pwd)" '
                    '--message "$1"\n')
    hook.chmod(0o755)
    head = _git(repo, "rev-parse", "HEAD")
    text = _sub(CALC, "import subprocess", "import subprocess  # noqa: F401")
    _write(repo, _c(text))
    _git(repo, "add", "-A")
    r = subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "No reason"], env=_env(),
                       capture_output=True, text=True, timeout=RUN_TIMEOUT)
    assert r.returncode != 0 and "REFUSED" in r.stderr
    assert _git(repo, "rev-parse", "HEAD") == head
    msg = repo.parent / "hook-message.txt"
    msg.write_text(f"With its reason\n\nBypass: pkg/calc.py:{line_of(text, 'noqa')} — kept\n")
    r = subprocess.run(["git", "-C", str(repo), "commit", "-q", "-F", str(msg)], env=_env(),
                       capture_output=True, text=True, timeout=RUN_TIMEOUT)
    assert r.returncode == 0, r.stderr
    assert _git(repo, "rev-parse", "HEAD") != head
    assert _git(repo, "config", "--bool", "core.bare") == "false"


def test_a_range_names_the_one_commit_it_refuses(repo):
    base = _git(repo, "rev-parse", "HEAD")
    clean = _commit(repo, _t(_test("def test_more():\n    assert calc.double(3) == 6\n")))
    _plant_noqa(repo)
    bad = _git(repo, "rev-parse", "HEAD")
    r = run(repo, "--range", f"{base}..HEAD")
    assert r.returncode == 1
    refused = [x for x in r.stderr.splitlines() if "REFUSED:" in x]
    assert refused and all(bad[:12] in x for x in refused), r.stderr
    assert clean[:12] not in r.stderr
    assert clean[:12] in r.stdout and "no bypass added: passes" in r.stdout


def test_an_unreadable_commit_is_exit_2(repo):
    r = run(repo, "--commit", "0" * 40)
    assert r.returncode == 2
    assert "COULD NOT ASK" in r.stderr
