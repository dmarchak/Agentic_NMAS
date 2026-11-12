"""Whether the verdicts on each commit agree, as a reader job (workstream 0; docs/LOCAL_CI.md):
GitHub Actions' verdict against the commit gate's (scripts/nmas-gate step 9, a note on origin)
and the local runner's (scripts/nmas-local-ci, where a host has its store) for each recent
commit on main.

**The operator's rules.** 2026-11-03: "A GitHub verdict that disagrees with the local one raises
a Needs attention row"; "Refuse only when a GitHub red is known at deploy time ... A GitHub red
that arrives after a deploy raises a Needs attention row naming the step, with a rollback
recommendation. A red may be rerun once: a green rerun clears it." 2026-11-11, the deploy bar:
"GitHub still runs after every push. If it goes red on a deployed sha: stop, report it at once,
then fix forward or roll back." The deploy gate refuses what it can see; this reader sees what
arrives after.

**One implementation of each verdict.** GitHub's is `verdict_of_runs`, the gate's
`gate_verdict` and the local runner's `local_verdict`, all in `scripts/nmas-deploy` (loaded
through `ci_verdict.deploy_script()`); nothing here judges a run. Where a red failed is
`ci_verdict.failed_steps`.

**Its asking.** One request for main's last :data:`PER_PAGE` push runs, and one more per commit
whose GitHub red is new to a row (a failed verdict is final, so it is asked once and kept in
the value); one fetch of origin's gate notes (git, not GitHub's API). The gate's and the local
verdicts are then local reads. Every 15 min: 4 requests an hour, plus one per new red, against
GitHub's 60 shared with `nmas-deploy` and the other readers.

It stores what each said, never a row: `judge` makes the rows at each read of the page.
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
#: The gate's states that are a note which cannot be used: a row. A fetch of origin's notes
#: that failed is the source's fact (`gate_notes` in the value), never a row per commit.
GATE_UNREAD = ("unreadable", "other-tree")
#: The gate's state for every commit when origin's notes could not be fetched.
GATE_UNASKED = "unasked"


def read(root: str = ROOT, get=None, store=None, running=None, previous=None,
         fetch=None, notify=None) -> dict:
    """``{"slug", "running", "deployed", "gate_notes", "commits"}``: each commit GitHub lists
    among main's last push runs, newest first, with GitHub's state and run, the gate's state
    (origin's notes fetched once, by *fetch*, by default `nmas-deploy`'s `fetch_gate_notes`)
    and the local runner's. A red GitHub run's failed steps are asked once and carried from
    *previous* (the last value). *notified* is each `ci_disagrees` notice sent, once per
    commit and GitHub run (*notify*, by default `notify_reds`)."""
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
    fstate, fwords = (fetch or mod.fetch_gate_notes)(root)
    commits = []
    for sha, runs in sorted(by_sha.items(), key=lambda kv: -max(mod._run_order(r)
                                                                  for r in kv[1])[0]):
        state, run, _all = mod.verdict_of_runs(runs)
        lv = mod.local_verdict(root, sha, store)
        gv = (mod.gate_verdict(root, sha, fetch=lambda _root: (fstate, fwords))
              if fstate in ("fetched", "absent") else
              {"state": GATE_UNASKED, "words": fwords})
        entry = {"sha": sha, "github": state,
                 "run": {"number": run.get("run_number"), "attempt": run.get("run_attempt") or 1,
                         "url": run.get("html_url"), "id": run.get("id")},
                 "order": max(mod._run_order(r) for r in runs)[0],
                 "local": lv["state"], "local_words": lv["words"],
                 "gate": gv["state"], "gate_words": gv["words"]}
        if state == "FAILED":
            old = known.get(sha) or {}
            if old.get("github") == "FAILED" and (old.get("run") or {}).get("id") == run.get("id") \
                    and old.get("failed_at") is not None:
                entry["failed_at"] = old["failed_at"]
            else:
                where = CV.failed_steps({"slug": slug, "id": str(run.get("id") or "")}, get=get)
                entry["failed_at"] = where.get("steps") or []
        commits.append(entry)
    value = {"slug": slug, "running": running, "deployed": mod.deployed_shas(root),
             "gate_notes": {"state": fstate, "words": fwords}, "commits": commits}
    value["notified"] = (notify or notify_reds)(value, previous)
    return value


#: The notification kind (`notify.message.EVENTS`): the operator, 2026-11-11, "its own
#: notification kind "CI disagrees with the deployed release", on by default for the deployer".
NOTIFY_EVENT = "ci_disagrees"
#: Where it goes, by default, with nothing set: every team a network names as Who is told
#: (`heal_notify`), the installation's configured notification destinations. Per-person
#: preferences, and so the deployer's own address, are a later slice.
NOTIFY_ON_BY_DEFAULT = True


def notice_key(r: dict) -> str:
    """One notice per commit and GitHub run: a rerun that fails again is a new notice."""
    return f"{r['sha']}:{(r.get('run') or {}).get('id') or ''}"


def told_teams(networks=None) -> list:
    """The team ids the installation tells: each network's Who is told team, once each, in
    the networks' order; none when no network names one."""
    from modules import heal_notify
    from modules.integration_groups import network_names

    out = []
    for name in network_names() if networks is None else networks:
        team = heal_notify.read(name).get("team") or ""
        if team and team not in out:
            out.append(team)
    return out


def notice(r: dict, deployed: dict, now: float = None) -> dict:
    """The `ci_disagrees` event for a red-after-deploy row *r*: the sha, GitHub's run and
    where it failed, who deployed it and when (*deployed*, `update_op.last_deployed`'s
    record), what to do, and History's updates as the link."""
    import time

    from modules.readers import ci_verdict as CV

    sha, run = r["sha"], r.get("run") or {}
    where = CV.failed_words({"failed_at": r.get("failed_at")})
    mine = deployed if (deployed or {}).get("to") == sha else {}
    by = mine.get("requested_by") or "nobody recorded"
    at = mine.get("ended_at") or "an unrecorded time"
    route = {"terminal": "nmas-deploy", "updater": "the Update button"}.get(mine.get("route"),
                                                                          "")
    back = r.get("rollback_to")
    return {
        "incident": f"ci-{sha[:12]}-{run.get('id') or 'run'}", "event": NOTIFY_EVENT,
        "happened": (f"GitHub's CI failed {sha[:10]}, the release this host runs, after it was "
                     f"deployed on {r.get('by') or 'the gate'}'s green: run #"
                     f"{run.get('number')}, attempt {run.get('attempt')}"
                     + (f", {run['url']}" if run.get("url") else "")
                     + (f"; failed at {where}" if where else "")),
        "outcome": (f"Deployed by {by} at {at}" + (f" ({route})" if route else "")
                    + ". The release keeps running: this is no outage."),
        "detected": "the ci-agreement reader",
        "detected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                     time.gmtime(time.time() if now is None else now)),
        "todo": ("Stop new work. Rerun GitHub's run once (a green rerun clears it); if it "
                 "stays red, fix it forward or roll back: "
                 + (f"scripts/nmas-rollback {back[:10]} --push, then Update" if back else
                    "scripts/nmas-rollback to the release before it, then Update")),
        "link": "/v2/history?kind=updates"}


def notify_reds(value: dict, previous: dict = None, *, deliver=None, teams=None,
                deployed=None, now: float = None) -> dict:
    """``{notice_key: {"at", "sent", "failed", "teams", "error"}}``: a `ci_disagrees` notice
    sent once for each red-after-deploy row the stored value calls for, the first time it is
    raised; a key the last value (*previous*) holds is carried and never sent again, whatever
    its delivery's outcome (a failure is the delivery log's row and the notify source's, as
    every delivery's). Keys of commits no longer listed are dropped. *deliver*, *teams* and
    *deployed* stand in for `delivery.deliver_event`, `told_teams` and
    `update_op.last_deployed` in tests."""
    import time

    done = {k: v for k, v in ((previous or {}).get("notified") or {}).items()
            if k.split(":", 1)[0] in {c["sha"] for c in value.get("commits") or []}}
    rows = [r for r in judge(value) if r["kind"] == "red-after-deploy"
            and notice_key(r) not in done]
    if not rows or not NOTIFY_ON_BY_DEFAULT:
        return done
    if deliver is None:
        from modules.notify import delivery
        deliver = delivery.deliver_event
    if deployed is None:
        from modules import update_op
        deployed = update_op.last_deployed()
    team_ids = told_teams() if teams is None else list(teams)
    for r in rows:
        try:
            got = deliver(notice(r, deployed, now), team_ids)
        except ValueError as exc:
            got = {"ok": False, "sent": 0, "failed": 0, "error": f"not sent: {exc}"}
        done[notice_key(r)] = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                time.gmtime(time.time() if now is None else now)),
            "sent": got.get("sent", 0), "failed": got.get("failed", 0),
            "teams": len(team_ids), "error": got.get("error", "")}
    return done


def ours(c: dict) -> tuple:
    """``(verdict, by)``: the verdict a commit was or would be deployed on other than GitHub's,
    "PASSED" or "FAILED" and who gave it, or ``(None, None)``. The local runner's red first (it
    refuses a deploy whatever else passed), then the gate's green, then the local runner's
    green: `nmas-deploy`'s `ci_verdict` order."""
    local = CONCLUSIVE.get(c.get("local"))
    if local == "FAILED":
        return local, "the local runner"
    if c.get("gate") == "passed":
        return "PASSED", "the gate"
    if local:
        return local, "the local runner"
    return None, None


def judge(value: dict) -> list:
    """The rows the stored value calls for, ``[{"kind", "sha", ...}]``, one per commit at most:

    * ``red-after-deploy``: the RUNNING commit's GitHub verdict is FAILED while the gate or the
      local runner passed it (it was deployed on that green): stop, then rerun once, fix
      forward or roll back;
    * ``disagree``: a commit the host does not run, one passed and the other failed, unless a
      NEWER commit's two verdicts agree (superseded);
    * ``unread``: the local runner's record, or the gate's note, for a listed commit could not
      be trusted or read (*unread_by* says which, *unread_words* why).
    Each row's *by* names the green or red that is not GitHub's (`ours`)."""
    commits = value.get("commits") or []
    running = value.get("running")
    agreed = [c["order"] for c in commits if ours(c)[0] and ours(c)[0] == c.get("github")]
    newest_agreed = max(agreed) if agreed else None
    out = []
    for c in commits:
        mine, by = ours(c)
        gh = c.get("github")
        if c.get("local") in UNREAD:
            out.append(dict(c, kind="unread", unread_by="the local runner",
                            unread_words=c.get("local_words")))
            continue
        if c.get("gate") in GATE_UNREAD:
            out.append(dict(c, kind="unread", unread_by="the gate",
                            unread_words=c.get("gate_words")))
            continue
        if not mine or gh not in ("PASSED", "FAILED") or mine == gh:
            continue
        if c["sha"] == running and gh == "FAILED":
            reruns = max(0, int((c.get("run") or {}).get("attempt") or 1) - 1)
            out.append(dict(c, kind="red-after-deploy", by=by,
                            rerun_left=reruns < RERUNS_OFFERED,
                            rollback_to=_previous(value, c["sha"])))
            continue
        c = dict(c, by=by)
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
    what=("whether GitHub's CI agrees with the commit gate's verdict (and the local runner's, "
          "where a host has one) on each recent commit on main, for Needs attention "
          "(workstream 0; the deploy bar, 2026-11-11)"),
    endpoints=("GitHub Actions push runs on main, and a red run's jobs",
               "origin's refs/notes/nmas-gate, the commit gate's verdicts (one git fetch)",
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
