"""Whether the two CI runners agree, as a reader job (workstream 0; docs/LOCAL_CI.md): GitHub
Actions' verdict and the local runner's (scripts/nmas-local-ci) for each recent commit on main.

**The operator's rule, 2026-11-03:** "A GitHub verdict that disagrees with the local one raises a
Needs attention row"; "Refuse only when a GitHub red is known at deploy time ... A GitHub red
that arrives after a deploy raises a Needs attention row naming the step, with a rollback
recommendation. A red may be rerun once: a green rerun clears it." The deploy gate refuses what
it can see; this reader sees what arrives after.

**One implementation of each verdict.** GitHub's is `verdict_of_runs` and the local runner's
`local_verdict`, both in `scripts/nmas-deploy` (loaded through `ci_verdict.deploy_script()`);
nothing here judges a run. Where a red failed is `ci_verdict.failed_steps`.

**Its asking.** One request for main's last :data:`PER_PAGE` push runs, and one more per commit
whose GitHub red is new to a row (a failed verdict is final, so it is asked once and kept in
the value). The local verdicts are file reads. Every 15 min: 4 requests an hour, plus one per
new red, against GitHub's 60 shared with `nmas-deploy` and the other readers.

It stores what each runner said, never a row: `judge` makes the rows at each read of the page.
"""

import os

from modules import reader_job

NAME = "ci-agreement"
INTERVAL_SECONDS = 900
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PER_PAGE = 50
#: "A red may be rerun once": the attempt after which a rerun is no longer offered.
RERUNS_OFFERED = 1
#: Local states that are a verdict; any other is no verdict to agree or disagree with.
CONCLUSIVE = {"passed": "PASSED", "failed": "FAILED"}
UNREAD = ("unreadable", "untrusted", "other-tree")


def read(root: str = ROOT, get=None, store=None, running=None, previous=None) -> dict:
    """``{"slug", "running", "deployed", "commits"}``: each commit GitHub lists among main's last
    push runs, newest first, with GitHub's state and run and the local runner's state. A red
    GitHub run's failed steps are asked once and carried from *previous* (the last value)."""
    from modules.readers import ci_verdict as CV
    from routes import health

    mod = CV.deploy_script()
    get = get or mod.github_get
    running = health._COMMIT if running is None else running
    if previous is None:
        got = reader_job.read_cached(NAME)
        previous = (((got.get("doc") or {}).get("last_good") or {}).get("value") or {}) \
            if got.get("state") == "ok" else {}
    slug = mod.slug_of(mod.git(root, "remote", "get-url", "origin"))
    _status, body, reason = get(f"/repos/{slug}/actions/runs?branch=main&event=push"
                                f"&per_page={PER_PAGE}")
    if body is None:
        raise RuntimeError(f"GitHub's runs on main could not be read ({reason})")
    by_sha = {}
    for r in body.get("workflow_runs") or []:
        if r.get("path") == mod.WORKFLOW_PATH and r.get("head_sha"):
            by_sha.setdefault(r["head_sha"], []).append(r)
    known = {c["sha"]: c for c in ((previous or {}).get("commits") or [])}
    commits = []
    for sha, runs in sorted(by_sha.items(), key=lambda kv: -max(mod._run_order(r)
                                                                  for r in kv[1])[0]):
        state, run, _all = mod.verdict_of_runs(runs)
        lv = mod.local_verdict(root, sha, store)
        entry = {"sha": sha, "github": state,
                 "run": {"number": run.get("run_number"), "attempt": run.get("run_attempt") or 1,
                         "url": run.get("html_url"), "id": run.get("id")},
                 "order": max(mod._run_order(r) for r in runs)[0],
                 "local": lv["state"], "local_words": lv["words"]}
        if state == "FAILED":
            old = known.get(sha) or {}
            if old.get("github") == "FAILED" and (old.get("run") or {}).get("id") == run.get("id") \
                    and old.get("failed_at") is not None:
                entry["failed_at"] = old["failed_at"]
            else:
                where = CV.failed_steps({"slug": slug, "id": str(run.get("id") or "")}, get=get)
                entry["failed_at"] = where.get("steps") or []
        commits.append(entry)
    return {"slug": slug, "running": running, "deployed": mod.deployed_shas(root),
            "commits": commits}


def judge(value: dict) -> list:
    """The rows the stored value calls for, ``[{"kind", "sha", ...}]``, one per commit at most:

    * ``red-after-deploy``: the RUNNING commit's GitHub verdict is FAILED while the local runner
      passed it (it was deployed on the local green): roll back, or rerun once;
    * ``disagree``: a commit the host does not run, one runner passed and the other failed,
      unless a NEWER commit's two verdicts agree (superseded);
    * ``unread``: the local runner's record for a listed commit could not be trusted or read.
    """
    commits = value.get("commits") or []
    running = value.get("running")
    agreed = [c["order"] for c in commits
              if CONCLUSIVE.get(c.get("local")) and CONCLUSIVE[c["local"]] == c.get("github")]
    newest_agreed = max(agreed) if agreed else None
    out = []
    for c in commits:
        local = CONCLUSIVE.get(c.get("local"))
        gh = c.get("github")
        if c.get("local") in UNREAD:
            out.append(dict(c, kind="unread"))
            continue
        if not local or gh not in ("PASSED", "FAILED") or local == gh:
            continue
        if c["sha"] == running and gh == "FAILED":
            reruns = max(0, int((c.get("run") or {}).get("attempt") or 1) - 1)
            out.append(dict(c, kind="red-after-deploy",
                            rerun_left=reruns < RERUNS_OFFERED,
                            rollback_to=_previous(value, c["sha"])))
            continue
        if newest_agreed is not None and newest_agreed > c["order"]:
            continue                                           # superseded
        out.append(dict(c, kind="disagree"))
    return out


def _previous(value: dict, sha: str):
    """The commit the host ran before *sha* (its reflog, newest first), the rollback's target."""
    deployed = value.get("deployed") or []
    later = deployed[deployed.index(sha) + 1:] if sha in deployed else deployed
    return later[0] if later else None


READER = reader_job.register(reader_job.Reader(
    name=NAME,
    what=("whether GitHub's CI and the local runner agree on each recent commit on main, for "
          "Needs attention (workstream 0)"),
    endpoints=("GitHub Actions push runs on main, and a red run's jobs",
               "the local CI runner's verdict store (/var/lib/nmas-local-ci)"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("GitHub allows 60 unauthenticated requests an hour per address, shared with "
                    "nmas-deploy and the other readers; a read costs one, plus one per new red, "
                    "so every 15 min is about 4 an hour; a red after a deploy is said within "
                    "15 min of GitHub recording it"),
    read=read,
    invalidates=("ci_agreement",),
    remedy="Read the error above: it names what GitHub answered",
    window=f"main's last {PER_PAGE} push runs at the read",
))
