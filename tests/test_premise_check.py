"""Board TI item 5 (docs/TEST_INTEGRITY.md; the operator, 2026-11-03): a premise correction names
the real behaviour measured that the old premise contradicted, with the measurement.

`scripts/nmas-premise-check` is driven as a subprocess on message files, the commit-msg hook's
form. The sentences that set a rule off are real ones: "premise was wrong" (fad95c6c), "corrected
premises" (a0165710) and "premise corrected" (6eaac570), each refused when the check was first
run over the commits since Phase 8 began (14 of them, 2026-11-03).
"""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-premise-check")
MEASURED = ("Premise-Corrected: tests/test_x.py::test_y — measured: the route answers 409 on "
            "the host, read 2026-11-03, not 400 as the test assumed")


def run(tmp_path, message):
    msg = tmp_path / "message.txt"
    msg.write_text(message)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run([sys.executable, SCRIPT, "--message", str(msg)], capture_output=True,
                          text=True, env=env, timeout=60)


@pytest.mark.parametrize("said", ["the test's premise was wrong", "two corrected premises",
                                  "Premise corrected: the route", "this corrects its premise"])
def test_prose_saying_a_premise_was_corrected_needs_the_trailer(tmp_path, said):
    r = run(tmp_path, f"Fix the route\n\nThe body: {said}, and more.\n")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "carries no Premise-Corrected" in r.stderr


def test_with_its_measured_trailer_it_passes(tmp_path):
    r = run(tmp_path, f"Fix the route\n\nThe test's premise was wrong.\n\n{MEASURED}\n")
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_trailer_without_measured_is_refused(tmp_path):
    r = run(tmp_path, "Fix\n\nPremise-Corrected: tests/test_x.py::test_y — the code was right\n")
    assert r.returncode == 1
    assert "without ' — measured:" in r.stderr


def test_a_measurement_of_too_few_words_is_refused(tmp_path):
    r = run(tmp_path, "Fix\n\nPremise-Corrected: tests/test_x.py::test_y — measured: yes\n")
    assert r.returncode == 1
    assert "under 3 words" in r.stderr


def test_a_wrapped_trailer_is_read_whole(tmp_path):
    r = run(tmp_path, "Fix\n\nThe premise was wrong.\n\nPremise-Corrected: tests/test_x.py::"
                      "test_y — measured:\n  the route answers 409 on the host\n"
                      "Co-Authored-By: someone\n")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("message", [
    "Add the premise check\n\nIt refuses a message saying `premise corrected` with no "
    "trailer.\n",
    "Add the premise check\n\nA message that says \"the premise was wrong\" needs one.\n",
    "Tidy\n\nNothing about tests here: the premises of the building were inspected.\n",
    "Tidy\n\nTest-Weakened: tests/test_x.py::test_y — C1: the premise was wrong\n",
    "Tidy\n\nTest-Weakened: tests/test_x.py::test_y — C1: a reason wrapped\n"
    "  onto a second line: the premise was wrong\n"])
def test_a_quoted_phrase_or_other_words_or_another_trailer_is_not_a_correction(
        tmp_path, message):
    """The phrase quoted (a message about this check), other uses of the word, and the words
    inside another trailer's value are not this commit's prose."""
    r = run(tmp_path, message)
    assert r.returncode == 0, r.stdout + r.stderr


def test_git_comment_lines_and_the_scissors_are_not_the_message(tmp_path):
    r = run(tmp_path, "Fix\n\nBody.\n# the premise was wrong (a comment git drops)\n"
                      "# ------------------------ >8 ------------------------\n"
                      "the premise was wrong, in the diff below the scissors\n")
    assert r.returncode == 0, r.stdout + r.stderr


def test_a_commit_already_made_is_read_from_git(tmp_path):
    """`--commit` reads the message from the repository the script lives in; a synthetic one
    here, the script copied into it, so no test reads this checkout's history."""
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "modules" / "nsot").mkdir(parents=True)
    with open(SCRIPT, encoding="utf-8") as fh:
        (repo / "scripts" / "nmas-premise-check").write_text(fh.read())
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.com", PYTHONPATH=ROOT)

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                              capture_output=True, text=True, timeout=30).stdout.strip()

    git("init", "-q", "-b", "main")
    (repo / "f").write_text("x")
    git("add", "-A")
    git("commit", "-q", "-m", "Fix\n\nThe premise was wrong.")
    r = subprocess.run([sys.executable, str(repo / "scripts" / "nmas-premise-check"), "--commit",
                        git("rev-parse", "HEAD")], capture_output=True, text=True, env=env,
                       timeout=60)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "carries no Premise-Corrected" in r.stderr
