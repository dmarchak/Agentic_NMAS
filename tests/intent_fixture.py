"""Commit what a fixture writes (not a test module).

Committed intent and goldens are read from ``HEAD`` since C104 (2026-09-27):
the working tree is ignored. A fixture that writes ``host_vars/`` and never
commits is therefore testing a device with NO committed intent, which is what
the editor fixtures learned earlier and every other fixture learned at once.
One helper, so the commit carries the trailer the readers require.
"""

from modules.nsot import repo as R


def commit_paths(repo: str, paths=("host_vars",), message="fixture: commit intent",
                 source="extraction") -> str:
    """``git add`` *paths* and commit them in *repo*, initialising it first.
    Returns HEAD. Content identical to what is committed is already
    committed, so nothing new is made; a commit that FAILS refuses loudly."""
    R.init_repo(repo)
    for path in paths:
        rc, _out, err = R.git(repo, "add", "-A", "--", path)
        assert rc == 0, f"git add {path}: {err}"
    staged, _o, _e = R.git(repo, "diff", "--cached", "--quiet")
    if staged == 0:                       # identical content: already committed
        return R.git(repo, "rev-parse", "HEAD")[1].strip()
    rc, _out, err = R.git(repo, "commit", "-m",
                          f"{message}\n\nSource: {source}\nActor: test\n")
    assert rc == 0, f"fixture commit failed: {err}"
    _rc, head, _err = R.git(repo, "rev-parse", "HEAD")
    return head.strip()


def commit_intent(repo: str, message="fixture: commit intent") -> str:
    return commit_paths(repo, ("host_vars",), message)
