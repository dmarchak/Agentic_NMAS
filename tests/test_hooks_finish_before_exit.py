"""A short-lived process must not exit under its own push.

Measured 2026-09-25: `nmas-retire` committed r5's retirement and exited, and
the post-commit push -- running on a daemon thread -- died with the process.
The remote stayed a commit behind and nothing recorded it. Hooks are now
joined at exit, bounded, and an unfinished one is named on stderr.

Driven in a REAL subprocess: an in-process test cannot exhibit a daemon
thread being killed at interpreter exit.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _child(tmp_path, sleep: float, join_seconds: float = None) -> tuple:
    marker = tmp_path / "pushed"
    code = f"""
import sys, time
sys.path.insert(0, {ROOT!r})
from modules.nsot import hooks
hooks.ensure_default_hooks = lambda: []          # no real push in a test
if {join_seconds!r} is not None:
    hooks._EXIT_JOIN_SECONDS = {join_seconds!r}
    import atexit
    atexit.unregister(hooks.wait_for_hooks)
    hooks._exit_join_registered = True
    atexit.register(lambda: hooks.wait_for_hooks({join_seconds!r}))
def slow_push(ctx):
    time.sleep({sleep!r})
    open({str(marker)!r}, "w").write("done")
    return {{"ok": True}}
hooks.register("push", slow_push, timeout=30)
hooks.run_post_commit({{"list_name": "x", "repo": "/nonexistent", "sha": "abc"}})
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=60)
    return marker.exists(), r


def test_a_cli_that_commits_and_exits_still_finishes_its_push(tmp_path):
    pushed, r = _child(tmp_path, sleep=1.5)
    assert r.returncode == 0, r.stderr
    assert pushed, "the process exited under its own push"


def test_a_push_that_cannot_finish_is_named_not_silent(tmp_path):
    pushed, r = _child(tmp_path, sleep=5, join_seconds=0.5)
    assert not pushed
    assert "still running at exit" in r.stderr
    assert "may not have been pushed" in r.stderr
