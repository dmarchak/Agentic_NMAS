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
  how far behind is unknown (said, never guessed). The reader FETCHES it
  (the Update operation, 2026-09-30), so this stays only when the fetch fails,
  and the value names why;
- ``not_on_remote``: the running commit is not an ancestor of the tip (a local
  commit, or a rewritten remote).
A remote that cannot be asked within the bound raises, so the reader keeps
the last good value and says the read failed (rule 3), never "up to date".

Behind the tip it also records what the Update operation previews
(`enrich()`): the commits between, their `Host-Step:` trailers, which of the
updater's sources the release changes, whether the checkout is clean, the
tip's CI verdict by `nmas-deploy`'s own gate, and since when the tip has been
ahead of this running commit. The page reads it; no page load asks GitHub.
"""

import os
import re
import time

from modules import reader_job
from modules.readers.remote_publication import LOCAL_GIT_TIMEOUT_S, LS_REMOTE_TIMEOUT_S, _git

INTERVAL_SECONDS = 300
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


#: A fetch of origin's main, bounded. NOT measured: about 30x the measured
#: `ls-remote` (about 1 s); a fetch that fails leaves the tip unfetched and
#: says so, never "up to date".
FETCH_TIMEOUT_S = 30

#: How many commits between the running commit and the tip are listed; more
#: are counted and the list says it is cut.
COMMITS_SHOWN = 50

#: The files the Update operation's ROOT-OWNED copies come from
#: (docs/UPDATE.md). A release that changes one needs the host step that
#: re-installs it, and the preview says so.
UPDATER_SOURCES = ("deploy/update/nmas-update", "scripts/nmas-deploy",
                   "deploy/systemd/nmas-update.path", "deploy/systemd/nmas-update.service")

#: A commit that needs a person's step on the host before its code can run
#: (a new unit, a package, a sudoers change) carries this trailer, one per
#: step; the Update operation lists each and the updater refuses a release
#: whose steps the person has not said are done.
HOST_STEP = re.compile(r"^Host-Step:\s*(.+?)\s*$", re.M)

#: The CI states that never change for a commit, so a tip's verdict is asked
#: once; anything else is asked again at the next read.
FINAL_CI = ("verified", "failed", "cancelled")


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def enrich(root: str, v: dict, previous: dict = None, verdict=None, git=_git,
           now: float = None, jobs=None) -> dict:
    """What the Update operation shows about a tip ahead of the running
    commit: the commits between, their `Host-Step:` trailers, which updater
    sources the release changes, whether the checkout is clean, the tip's CI
    verdict (asked ONCE per tip when final, by `nmas-deploy`'s own gate), and
    SINCE WHEN origin/main has been ahead of this running commit: first seen
    by this reader, kept while the running commit stays, said as that."""
    now = time.time() if now is None else now
    previous = previous or {}
    running, tip = v["running"], v["tip"]
    out = dict(v)
    if v["state"] == "at_tip":
        return out
    same = previous.get("running") == running and previous.get("state") != "at_tip"
    out["behind_since"] = (previous.get("behind_since") if same and previous.get("behind_since")
                           else _iso(now))
    out["behind_since_basis"] = (f"first seen by this reader, which asks every "
                                 f"{INTERVAL_SECONDS} s")
    if v["state"] != "behind":
        return out
    rc, text, err = git(root, "log", f"--max-count={COMMITS_SHOWN}",
                        "--format=%H%x1f%s%x1f%an%x1f%cI", f"{running}..{tip}")
    out["commits"] = ([dict(zip(("sha", "subject", "author", "at"), line.split("\x1f")))
                       for line in text.splitlines() if line] if rc == 0 else [])
    out["commits_cut"] = rc == 0 and (v.get("behind") or 0) > len(out["commits"])
    if rc != 0:
        out["commits_error"] = err[:200] or f"git log exited {rc}"
    rc, text, err = git(root, "log", "--format=%H%x1f%B%x1e", f"{running}..{tip}")
    # Each step's KIND (modules/host_steps.py): BEFORE blocks the update,
    # AFTER never does and is owed once the release runs.
    from modules import host_steps as HS
    out["host_steps"] = HS.steps_in(text, when="before") if rc == 0 else []
    out["after_steps"] = HS.steps_in(text, when="after") if rc == 0 else []
    if rc != 0:
        out["host_steps_error"] = err[:200] or f"git log exited {rc}"
    rc, text, _err = git(root, "diff", "--name-only", running, tip, "--", *UPDATER_SOURCES)
    out["updater_changes"] = [p for p in text.splitlines() if p] if rc == 0 else None
    rc, text, _err = git(root, "status", "--porcelain", "--untracked-files=no")
    out["checkout_changes"] = [p for p in text.splitlines() if p][:10] if rc == 0 else None
    ci = previous.get("ci") or {}
    if not (ci.get("tip") == tip and ci.get("state") in FINAL_CI):
        from modules.readers import ci_verdict as CV

        try:
            mod = CV.deploy_script()
            code, sentence = (verdict or mod.ci_verdict)(root, tip)
            ci = {"tip": tip, "state": CV.state_of(mod, code), "sentence": sentence,
                  "asked_at": _iso(now)}
            if ci["state"] == "failed":
                # Where it failed (C418): the Needs attention row leads with it. Asked once,
                # with the verdict, since a failed verdict is final.
                where = CV.failed_steps(CV.run_of(sentence), get=jobs)
                ci.update(failed_at=where.get("steps") or [], failed_at_error=where.get("error"))
        except Exception as exc:                          # noqa: BLE001
            ci = {"tip": tip, "state": "could_not_ask", "asked_at": _iso(now),
                  "sentence": f"the verdict raised {type(exc).__name__}: {exc}"}
    out["ci"] = ci
    return out


def read(running=None, root=ROOT, git=_git, previous=None, verdict=None) -> dict:
    from modules import reader_job
    from routes import health

    running = health._COMMIT if running is None else running
    if not running:
        raise RuntimeError(f"the loaded commit is unknown: {health._COMMIT_ERROR}")
    v = judge(root, running, git=git)
    if v["state"] == "behind_unfetched":
        # Fetch what is pushed, so the gap can be counted and listed: the
        # Update operation's preview names every commit it would run.
        rc, _out, err = git(root, "fetch", "--quiet", "origin", BRANCH, timeout=FETCH_TIMEOUT_S)
        if rc == 0:
            v = judge(root, running, git=git)
        else:
            v = dict(v, fetch_error=err[:200] or f"git fetch exited {rc}")
    if previous is None:
        got = reader_job.read_cached(READER.name)
        previous = (((got.get("doc") or {}).get("last_good") or {}).get("value") or {}) \
            if got.get("state") == "ok" else {}
    return enrich(root, v, previous, verdict=verdict, git=git)


def words(v: dict) -> str:
    """The one sentence, for About and the row alike. In the PAST tense, as
    of the last ask (the operator, 2026-09-30): a stored answer is what was
    known when it was asked, never a statement about now. About said "the
    running commit b27c786ac0 is the tip" four minutes after 19910bf was
    pushed. The time of the ask is drawn beside it."""
    run, tip = str(v.get("running") or "")[:10], str(v.get("tip") or "")[:10]
    state = v.get("state")
    if state == "at_tip":
        return f"the running commit {run} was the tip of origin/{BRANCH} when last asked"
    if state == "behind":
        n = v.get("behind")
        return (f"when last asked, the host ran {n if n is not None else 'an unknown number of'} "
                f"commit{'' if n == 1 else 's'} behind what was pushed: running {run}, "
                f"origin/{BRANCH} was {tip}")
    if state == "behind_unfetched":
        return (f"when last asked, the host ran {run} and origin/{BRANCH} was {tip}, a commit this "
                "checkout had not fetched, so how far behind was unknown"
                + (f" (the fetch failed: {v['fetch_error']})" if v.get("fetch_error")
                   else " until it is fetched"))
    if state == "not_on_remote":
        return (f"when last asked, the running commit {run} was not on origin/{BRANCH} ({tip}): "
                "a local commit, or a remote rewritten under it")
    return f"unknown state {state!r}"


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
    after_store=lambda: _release_waiting_update(),
))


def _release_waiting_update():
    """Update when CI passes: the wait is released by THIS reader, which asks
    CI every run while a verdict is pending (modules/update_op.py)."""
    from modules import update_op

    return update_op.release_deferred()
