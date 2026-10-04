"""The running commit's CI verdict as a reader job: the fifth instance of
modules/reader_job.py, and the status bar's version item.

**One implementation of each answer** (the operator, 2026-09-28: two
implementations of "what is running" is the pattern this project keeps
removing):
- WHAT IS RUNNING is `routes.health._COMMIT`, what this process loaded, as
  `/health` serves it to `nmas-deploy`;
- WHETHER IT IS THE CHECKOUT'S COMMIT is `job_health.version_rows()` (C129),
  read from the job-health reader's stored value, never computed again;
- ITS CI VERDICT is `ci_verdict()` in `scripts/nmas-deploy`, the gate the
  deploy itself runs, including C170's walk. This reader LOADS that script
  and calls it; there is no second copy of the verdict logic.

**Why a reader.** The verdict needs GitHub, an outside service, so it is
never asked on a page load (rule 1). GitHub's unauthenticated API allows
60 requests an hour per address, shared with `nmas-deploy` on the same host.
A verdict costs one request, and up to eleven when it walks back through
commits with no run (C170), so every 15 min bounds this reader to about four
requests an hour typically and 44 at worst.

The value names the commit it judged. A process that restarted onto a new
commit before the next read shows that its commit is not judged yet, never
the previous commit's verdict as its own.
"""

import importlib.machinery
import importlib.util
import os
import re
import threading

from modules import reader_job

INTERVAL_SECONDS = 900
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "nmas-deploy")

_loaded = None
_mu = threading.Lock()


def deploy_script():
    """`scripts/nmas-deploy`, loaded once as a module: the ONE implementation
    of the CI verdict. It has no side effects at import (a `__main__` guard)."""
    global _loaded
    with _mu:
        if _loaded is None:
            loader = importlib.machinery.SourceFileLoader("nmas_deploy_script", SCRIPT)
            spec = importlib.util.spec_from_loader("nmas_deploy_script", loader)
            mod = importlib.util.module_from_spec(spec)
            loader.exec_module(mod)
            _loaded = mod
        return _loaded


def state_of(mod, code) -> str:
    """The script's exit code, in the words its constants name."""
    return {mod.OK: "verified", mod.CI_REFUSED: "failed", mod.COULD_NOT_ASK: "could_not_ask",
            mod.CI_PENDING: "pending", mod.CI_CANCELLED: "cancelled"}.get(code, f"code {code}")


#: The run a verdict's sentence names, in each of `ci_verdict()`'s forms: ", #373, concluded"
#: (a run of its own), "run #373" (still running; an ancestor's run), "(#373)" (an ancestor
#: still running). The first match is the run judged: the other runs are listed after it.
_RUN_NUMBER = re.compile(r"(?:\brun |, |\()#(\d+)\b")
_RUN_URL = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/actions/runs/(\d+)")


def run_of(sentence: str) -> dict:
    """``{"number", "url", "slug", "id"}`` of the run a verdict sentence names, each None when
    the sentence does not carry it (an ancestor's run is named without its link)."""
    sentence = sentence or ""
    n, u = _RUN_NUMBER.search(sentence), _RUN_URL.search(sentence)
    return {"number": n.group(1) if n else None, "url": u.group(0) if u else None,
            "slug": u.group(1) if u else None, "id": u.group(2) if u else None}


def failed_steps(run: dict, get=None) -> dict:
    """Where a failed run failed: ``{"steps": [{"step", "jobs"}]}``, the first failed step of
    each failed job, jobs that failed at the same step together; or ``{"error"}``. One request
    (GitHub's jobs listing for the run), asked once per tip, since a failed verdict is final."""
    if not run.get("id"):
        return {"error": "the verdict names no run of this commit's own to ask about"}
    get = get or deploy_script().github_get
    _status, body, reason = get(f"/repos/{run['slug']}/actions/runs/{run['id']}/jobs?per_page=50")
    if body is None:
        return {"error": f"GitHub's jobs for run {run['id']} could not be read ({reason})"}
    where = {}
    for job in body.get("jobs") or []:
        if job.get("conclusion") != "failure":
            continue
        step = next((s.get("name") for s in job.get("steps") or []
                     if s.get("conclusion") == "failure"), None) or "no step marked failed"
        where.setdefault(step, []).append(job.get("name") or "?")
    if not where:
        return {"error": f"run {run['id']} lists no failed job"}
    return {"steps": [{"step": s, "jobs": sorted(j)} for s, j in where.items()]}


def failed_words(ci: dict) -> str:
    """Where it failed, in a person's words: "promtool for the PromQL tests, in test (a),
    test (b)"; "" when not known."""
    return "; ".join(f"{w['step']}, in {', '.join(w['jobs'])}" for w in ci.get("failed_at") or [])


def read(commit=None, verdict=None) -> dict:
    from routes import health

    commit = health._COMMIT if commit is None else commit
    if not commit:
        raise RuntimeError(f"the loaded commit is unknown: {health._COMMIT_ERROR}")
    mod = deploy_script()
    code, sentence = (verdict or mod.ci_verdict)(ROOT, commit)
    return {"commit": commit, "code": code, "state": state_of(mod, code), "sentence": sentence}


READER = reader_job.register(reader_job.Reader(
    name="ci-verdict",
    what="the running commit's CI verdict, by nmas-deploy's own gate, for the status bar",
    endpoints=("GitHub Actions runs for the running commit (and its ancestors when it has none)",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("GitHub allows 60 unauthenticated requests an hour per address, shared with "
                    "nmas-deploy; a verdict costs 1, up to 11 walking back (C170), so every "
                    "15 min is about 4 an hour and 44 at worst"),
    read=read,
    invalidates=("ci_verdict",),
    remedy="Read the error above: it names what could not be asked",
    window="the verdict at the read, for the commit named in the value",
))
