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
requests an hour typically and 44 at worst. A red of the commit's own adds one
request for its run's jobs and one per failed job's annotations (its failed
tests), once per failed attempt (C3425): the runs themselves are the verdict's
own answer, recorded as it is made, never asked again.

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


def source_of(mod, sentence: str) -> str:
    """Which CI runner judged it, by the script's own `verdict_source` ("local", "github",
    "both", "override"); "github" from a script that predates the local runner."""
    fn = getattr(mod, "verdict_source", None)
    return fn(sentence) if fn else "github"


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


# ---------------------------------------------------------------------------
# The running commit's own runs, and the red the row draws (C3425, the operator, 2026-11-13:
# "When runs on the same sha disagree (#1679 passed, #1680 failed), say so: list both, name
# the failed job and test, say whether a re-run is in progress").
# ---------------------------------------------------------------------------

#: A completed run's conclusions that are a red (GitHub's names); cancelled and skipped are
#: abandoned attempts (`nmas-deploy`'s ABANDONED), never a verdict.
FAILED_CONCLUSIONS = ("failure", "timed_out", "startup_failure")
#: How many failed tests of one job are kept: GitHub keeps ten annotations a step, and the
#: suite's conftest writes one per failed test (`pytest_terminal_summary`), so the row names
#: the first few and counts the rest.
TESTS_KEPT = 5


def runs_of(body: dict, workflow: str) -> list:
    """GitHub's runs listing for one sha, *workflow*'s runs only, in the fields the row draws:
    ``[{"number", "attempt", "status", "conclusion", "url", "id", "completed_at"}]``, oldest
    first. *completed_at* is a completed run's ``updated_at`` (the listing has no
    ``completed_at``; a completed run is not updated after it), None while it runs."""
    out = []
    for r in (body or {}).get("workflow_runs") or []:
        if r.get("path") != workflow:
            continue
        done = r.get("status") == "completed"
        out.append({"number": r.get("run_number"), "attempt": int(r.get("run_attempt") or 1),
                    "status": r.get("status"), "conclusion": r.get("conclusion"),
                    "url": r.get("html_url"), "id": r.get("id"),
                    "completed_at": r.get("updated_at") if done else None})
    return sorted(out, key=run_order)


def run_order(r: dict) -> tuple:
    """`nmas-deploy`'s `_run_order` over the fields `runs_of` keeps: run number, then
    attempt, then id."""
    return (r.get("number") or 0, r.get("attempt") or 0, r.get("id") or 0)


def _failed_tests(slug: str, job: dict, get) -> tuple:
    """``(tests, error)``: the failed tests GitHub's annotations name for one failed *job*,
    ``[{"job", "test", "line"}]`` (the conftest's annotation: the test's node id as its title,
    its first error line as its message), at most TESTS_KEPT, and how many more. One request."""
    _status, body, reason = get(f"/repos/{slug}/check-runs/{job.get('id')}/annotations"
                                "?per_page=50")
    if not isinstance(body, list):
        return [], f"the annotations of {job.get('name') or '?'} could not be read ({reason})"
    tests = []
    for a in body:
        title = str(a.get("title") or "")
        if a.get("annotation_level") != "failure" or "::" not in title:
            continue
        line = str(a.get("message") or "").strip().splitlines()[:1]
        line = line[0].lstrip("E").strip()[:200] if line else ""
        tests.append({"job": job.get("name") or "?", "test": title, "line": line})
    return tests, None


def where_failed(run: dict, get=None) -> dict:
    """Where a failed run failed: ``{"steps", "tests", "more", "error"}``: each failed job's
    first failed step (as `failed_steps`), and the failed tests its annotations name. One
    request for the run's jobs and one per failed job's annotations, asked once per failed
    attempt (a failed attempt is final; the reader carries it)."""
    slug, rid = run_of(run.get("url") or "")["slug"], run.get("id")
    if not slug or not rid:
        return {"steps": [], "tests": [], "more": 0,
                "error": "the run names no address to ask GitHub about"}
    get = get or deploy_script().github_get
    _status, body, reason = get(f"/repos/{slug}/actions/runs/{rid}/jobs?per_page=50")
    if body is None:
        return {"steps": [], "tests": [], "more": 0,
                "error": f"GitHub's jobs for run {rid} could not be read ({reason})"}
    where, tests, errors = {}, [], []
    for job in body.get("jobs") or []:
        if job.get("conclusion") != "failure":
            continue
        step = next((s.get("name") for s in job.get("steps") or []
                     if s.get("conclusion") == "failure"), None) or "no step marked failed"
        where.setdefault(step, []).append(job.get("name") or "?")
        got, error = _failed_tests(slug, job, get)
        tests += got
        if error:
            errors.append(error)
    return {"steps": [{"step": s, "jobs": sorted(j)} for s, j in where.items()],
            "tests": tests[:TESTS_KEPT], "more": max(0, len(tests) - TESTS_KEPT),
            "error": "; ".join(errors) or (None if where else f"run {rid} lists no failed job")}


def red_of(runs, previous: dict = None, get=None) -> dict:
    """The red the running commit's row draws, or None: the run whose completed attempt failed
    and is the commit's latest conclusive run (an older red a later pass superseded is no
    red), with where it failed (asked once per attempt, carried from *previous*, the last
    stored red); or *previous* itself while the listing shows that run again at a later
    attempt that is still going (GitHub's listing shows a run's latest attempt only, so a
    re-run hides the failed one). *rerun* is the commit's newest run still going after the
    red, or None. A red's facts outlive no re-run that ended: a passed re-run is no red, and a
    failed one is a new red, asked about afresh."""
    if runs is None:
        return None
    previous = previous or {}
    done = [r for r in runs if r.get("status") == "completed"
            and r.get("conclusion") not in ("cancelled", "skipped", None, "")]
    latest = max(done, key=run_order) if done else None
    if latest and latest.get("conclusion") in FAILED_CONCLUSIONS:
        if (previous.get("id") == latest.get("id")
                and previous.get("attempt") == latest.get("attempt")
                and previous.get("failed_at") is not None):
            kept = {k: previous.get(k) for k in ("failed_at", "tests", "more", "where_error")}
        else:
            w = where_failed(latest, get)
            kept = {"failed_at": w["steps"], "tests": w["tests"], "more": w["more"],
                    "where_error": w["error"]}
        red = dict(latest, **kept)
    elif previous.get("id") and any(
            r.get("id") == previous["id"] and r.get("attempt", 0) > previous.get("attempt", 0)
            and r.get("status") != "completed" for r in runs):
        red = {k: v for k, v in previous.items() if k != "rerun"}
    else:
        return None
    live = [r for r in runs if r.get("status") != "completed" and run_order(r) > run_order(red)]
    newest = max(live, key=run_order) if live else None
    red["rerun"] = ({"number": newest["number"], "attempt": newest["attempt"],
                     "status": newest["status"], "url": newest.get("url"),
                     "same_run": newest.get("id") == red.get("id")} if newest else None)
    return red


def read(commit=None, verdict=None, get=None, previous=None, root=None, store=None,
         fetch=None) -> dict:
    """The verdict (`nmas-deploy`'s `ci_verdict`, its one implementation), and from the
    same answer the running commit's own runs: the verdict's GitHub requests are recorded as
    they are made (*get* wraps the script's own), so the runs cost no request of their own.
    A red's jobs and failed tests are asked once per failed attempt (`red_of`). *verdict*
    stands in for the script's whole verdict (its runs then not recorded); *root*, *store*
    and *fetch* for the checkout, the local runner's store and the gate's notes in tests."""
    from routes import health

    commit = health._COMMIT if commit is None else commit
    if not commit:
        raise RuntimeError(f"the loaded commit is unknown: {health._COMMIT_ERROR}")
    mod = deploy_script()
    ask = get or mod.github_get
    seen = {}

    def recording(path, *args, **kwargs):
        got = ask(path, *args, **kwargs)
        if f"head_sha={commit}" in path and got[1] is not None:
            seen["runs"] = runs_of(got[1], mod.WORKFLOW_PATH)
        return got

    if verdict is not None:
        code, sentence = verdict(root or ROOT, commit)
    else:
        code, sentence = mod.ci_verdict(root or ROOT, commit, get=recording, store=store,
                                        fetch=fetch)
    if previous is None:
        got = reader_job.read_cached(READER.name)
        previous = (((got.get("doc") or {}).get("last_good") or {}).get("value") or {}) \
            if got.get("state") == "ok" else {}
    old = (previous or {}).get("red") if (previous or {}).get("commit") == commit else None
    runs = seen.get("runs")
    return {"commit": commit, "code": code, "state": state_of(mod, code), "sentence": sentence,
            "source": source_of(mod, sentence), "runs": runs,
            "red": red_of(runs, old, get=ask)}


READER = reader_job.register(reader_job.Reader(
    name="ci-verdict",
    what="the running commit's CI verdict, by nmas-deploy's own gate, for the status bar",
    endpoints=("GitHub Actions runs for the running commit (and its ancestors when it has none)",
               "a failed run's jobs, and each failed job's annotations (its failed tests)"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("GitHub allows 60 unauthenticated requests an hour per address, shared with "
                    "nmas-deploy; a verdict costs 1, up to 11 walking back (C170), so every "
                    "15 min is about 4 an hour and 44 at worst; a red adds 1 plus 1 per failed "
                    "job, once per failed attempt"),
    read=read,
    invalidates=("ci_verdict",),
    remedy="Read the error above: it names what could not be asked",
    window="the verdict at the read, for the commit named in the value",
))
