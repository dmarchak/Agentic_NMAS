"""Is the host running what is pushed? The application's own repository against
origin/main, as a reader job (the operator, 2026-09-30).

The top bar no longer carries the commit; Help > About does, and Needs
attention carries a row when the running commit is not what was pushed. This
reader answers that one question:

- **the running commit** is `routes.health._COMMIT`, what this process loaded
  (the one implementation, as `/health` serves it to `nmas-deploy`);
- **what is pushed** is origin's `refs/heads/main`, asked with `git ls-remote`
  at read time. Never `origin/main` in the checkout, which moves only when
  somebody fetches, so a stale ref would read as "up to date".

Four answers, each in words:
- ``at_tip``: running the pushed tip;
- ``behind``: the tip is newer and this checkout has its objects, so the gap
  is counted (`rev-list --count running..tip`);
- ``behind_unfetched``: the tip is a commit this checkout has not fetched, so
  how far behind is unknown until `nmas-deploy` fetches (said, never guessed);
- ``not_on_remote``: the running commit is not an ancestor of the tip (a local
  commit, or a rewritten remote).
A remote that cannot be asked within the bound raises, so the reader keeps
the last good value and says the read failed (rule 3), never "up to date".
"""

import os

from modules import reader_job
from modules.readers.remote_publication import LOCAL_GIT_TIMEOUT_S, LS_REMOTE_TIMEOUT_S, _git

INTERVAL_SECONDS = 300
KEEPALIVE_SECONDS = 1800
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BRANCH = "main"


def judge(root: str, running: str, git=_git) -> dict:
    """The relation between *running* and origin's tip, in *root*."""
    rc, line, err = git(root, "ls-remote", "origin", f"refs/heads/{BRANCH}",
                        timeout=LS_REMOTE_TIMEOUT_S)
    if rc != 0 or not line:
        raise RuntimeError(f"git ls-remote origin refs/heads/{BRANCH} answered nothing "
                           f"({err[:200] or 'no line'})")
    tip = line.split()[0]
    out = {"running": running, "tip": tip, "branch": BRANCH}
    if tip == running:
        return dict(out, state="at_tip", behind=0)
    has_tip = git(root, "cat-file", "-e", f"{tip}^{{commit}}", timeout=LOCAL_GIT_TIMEOUT_S)[0] == 0
    if not has_tip:
        return dict(out, state="behind_unfetched", behind=None)
    if git(root, "merge-base", "--is-ancestor", running, tip, timeout=LOCAL_GIT_TIMEOUT_S)[0] == 0:
        rc, count, _ = git(root, "rev-list", "--count", f"{running}..{tip}", timeout=LOCAL_GIT_TIMEOUT_S)
        return dict(out, state="behind", behind=int(count) if rc == 0 and count.isdigit() else None)
    return dict(out, state="not_on_remote", behind=None)


def read(running=None, root=ROOT, git=_git) -> dict:
    from routes import health

    running = health._COMMIT if running is None else running
    if not running:
        raise RuntimeError(f"the loaded commit is unknown: {health._COMMIT_ERROR}")
    return judge(root, running, git=git)


def words(v: dict) -> str:
    """The one sentence, for About and the row alike."""
    run, tip = str(v.get("running") or "")[:10], str(v.get("tip") or "")[:10]
    state = v.get("state")
    if state == "at_tip":
        return f"the running commit {run} is the tip of origin/{BRANCH}"
    if state == "behind":
        n = v.get("behind")
        return (f"the host runs {n if n is not None else 'an unknown number of'} commit"
                f"{'' if n == 1 else 's'} behind what is pushed: running {run}, "
                f"origin/{BRANCH} is {tip}")
    if state == "behind_unfetched":
        return (f"the host runs {run} and origin/{BRANCH} is {tip}, a commit this checkout "
                "has not fetched, so how far behind is unknown until nmas-deploy fetches it")
    if state == "not_on_remote":
        return (f"the running commit {run} is not on origin/{BRANCH} ({tip}): a local commit, "
                "or a remote rewritten under it")
    return f"unknown state {state!r}"


def changed(previous: dict, value: dict) -> bool:
    def key(v):
        v = v or {}
        return (v.get("running"), v.get("tip"), v.get("state"), v.get("behind"))
    return key(previous) != key(value)


READER = reader_job.register(reader_job.Reader(
    name="app-pushed",
    what="whether the running commit is what is pushed: this process's commit against origin/main",
    endpoints=("the application repository's origin, by `git ls-remote origin refs/heads/main`",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("a pushed commit waits on a person's deploy, which is minutes, not seconds; "
                    "one ls-remote is about 1 s (measured for the list repositories, "
                    "2026-09-29)"),
    read=read,
    invalidates=("app_version",),
    remedy="Read the error above: it names what could not be asked",
    window="origin/main's tip at the read, against the commit this process loaded",
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
