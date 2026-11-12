"""The repository's scheduled quality jobs as a reader job (C2347): each workflow that carries a
``schedule:``, its newest scheduled runs on main, and where the newest failed one failed.

**The operator's rule, 2026-11-03:** a scheduled quality job (mutation, the coverage drill-down)
that fails, or has not succeeded within its period, raises a Needs attention row. Silently
failing safeguards are how automatic greens survive. Measured that morning: the mutation
workflow's runs #57 to #68 had all failed, and the coverage nightly's #32 to #34, unsaid.

**The population is the property, never a list:** every `.github/workflows/*.yml` whose `on:`
carries a `schedule:` cron, read from the checkout this process runs from (a release is a clone,
so it holds them). The CI workflow is not one: it runs on every push, and its verdict for the
running commit is already the ``ci`` row.

**Only scheduled runs count.** A dispatched run is narrowed by its inputs (a mutation run on
named functions), so it is not the scheduled measurement, and its pass does not clear a failed
schedule.

**Its asking.** One request per workflow (its last :data:`PER_PAGE` scheduled runs) and one
more for a failed newest run's jobs (`ci_verdict.failed_steps`), through `nmas-deploy`'s own
`github_get`. GitHub's unauthenticated allowance is 60 an hour per address, shared with
`nmas-deploy` and the ci-verdict reader. Two workflows, every 30 min, is 4 to 8 requests an
hour.

It stores what GitHub said, never a verdict: `judge` makes the verdict at each read of the
page, against the clock.
"""

import calendar
import glob
import os
import time

import yaml

from modules import reader_job

NAME = "scheduled-jobs"
INTERVAL_SECONDS = 1800
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PER_PAGE = 10

#: How late GitHub starts a scheduled run, as a bound. Measured 2026-11-03 from both workflows'
#: scheduled runs (tests/fixtures/github/*_scheduled_runs.json): the coverage nightly's 03:47
#: cron started 5h34m to 7h54m late (10-25 to 11-03), and the mutation run's Sunday 14:00 cron
#: 3h18m and 4h39m late. 2.5 times the worst, 7h54m, is about 20 h.
START_DELAY_SECONDS = 20 * 3600

#: A run that has not finished is not a verdict: the newest COMPLETED run is judged.
FAILED = ("failure", "cancelled", "timed_out", "startup_failure", "action_required", "stale")


def _on(doc: dict) -> dict:
    """The workflow's triggers. YAML 1.1 reads a bare ``on`` key as True."""
    got = doc.get("on", doc.get(True))
    return got if isinstance(got, dict) else {}


def period_of(cron: str):
    """Seconds between a cron's runs, for the shapes a workflow uses: a weekday named (weekly), a
    day of the month named (monthly, 31 days), an hour named (daily), else hourly (every hour, or
    every Nth with ``*/N``). None when the cron is not five fields."""
    fields = str(cron or "").split()
    if len(fields) != 5:
        return None
    _minute, hour, dom, _month, dow = fields
    if dow != "*":
        return 7 * 86400
    if dom != "*":
        return 31 * 86400
    if hour.startswith("*/") and hour[2:].isdigit():
        return int(hour[2:]) * 3600
    if hour != "*":
        return 86400
    return 3600


def _cron_values(text: str, lo: int, hi: int):
    """The values one cron field allows (numbers, ``*``, ranges, lists and ``/N`` steps, as
    GitHub's schedules use them), or None for anything else (a name such as ``MON``): never a
    guess."""
    out = set()
    for part in str(text).split(","):
        base, _sep, step = part.partition("/")
        if _sep and not (step.isdigit() and int(step) >= 1):
            return None
        every = int(step) if _sep else 1
        if base == "*":
            a, b = lo, hi
        elif "-" in base:
            x, _d, y = base.partition("-")
            if not (x.isdigit() and y.isdigit()):
                return None
            a, b = int(x), int(y)
        elif base.isdigit():
            a = int(base)
            b = hi if _sep else a
        else:
            return None
        if a < lo or b > hi or a > b:
            return None
        out.update(range(a, b + 1, every))
    return out


def next_run(cron: str, after: float):
    """The epoch of a schedule's next run strictly after *after*, by its cron in UTC (GitHub
    runs schedules in UTC; "0 14 * * 0" is each Sunday at 14:00), or None when a cron cannot be
    read. Several crons ("a; b", as `scheduled_workflows` joins them) give the earliest. This is
    when GitHub is asked to start it, not when it starts (`START_DELAY_SECONDS`). Day of month
    and day of week, both restricted, match either (cron's own rule)."""
    import datetime as dt

    best = None
    for one in str(cron or "").split(";"):
        fields = one.split()
        if len(fields) != 5:
            return None
        minute, hour, dom, month, dow = (
            _cron_values(fields[0], 0, 59), _cron_values(fields[1], 0, 23),
            _cron_values(fields[2], 1, 31), _cron_values(fields[3], 1, 12),
            _cron_values(fields[4], 0, 7))
        if None in (minute, hour, dom, month, dow):
            return None
        dow = {d % 7 for d in dow}
        either = not fields[2].startswith("*") and not fields[4].startswith("*")
        start = dt.datetime.fromtimestamp(int(after) // 60 * 60, dt.timezone.utc)
        found = None
        # Every day for eight years, past the longest gap any cron here can have (a schedule on
        # 29 February, every four years, or eight across a century's skipped leap year).
        for n in range(366 * 8):
            day = (start + dt.timedelta(days=n)).date()
            if day.month not in month:
                continue
            on_dom, on_dow = day.day in dom, (day.isoweekday() % 7) in dow
            if not ((on_dom or on_dow) if either else (on_dom and on_dow)):
                continue
            for h in sorted(hour):
                for m in sorted(minute):
                    t = dt.datetime(day.year, day.month, day.day, h, m,
                                    tzinfo=dt.timezone.utc).timestamp()
                    if t > after:
                        found = t
                        break
                if found is not None:
                    break
            if found is not None:
                break
        if found is None:
            return None
        best = found if best is None else min(best, found)
    return best


def run_bound_of(doc: dict) -> int:
    """A run's longest possible length, in seconds: every job's ``timeout-minutes`` summed, as
    though they ran one after another (the bound, not a measured length). A job with none takes
    GitHub's default, 360 minutes."""
    total = 0
    for job in (doc.get("jobs") or {}).values():
        minutes = (job or {}).get("timeout-minutes")
        total += int(minutes) if isinstance(minutes, (int, float)) else 360
    return total * 60


def scheduled_workflows(root: str = ROOT) -> list:
    """``[{"file", "name", "cron", "period_seconds", "run_bound_seconds"}]`` for every workflow
    file under *root* with a schedule, by file name; a file that does not parse is said by its
    ``error``."""
    found = []
    for path in sorted(glob.glob(os.path.join(root, ".github", "workflows", "*.yml"))):
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as fh:
                doc = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError) as exc:
            found.append({"file": name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        schedule = _on(doc).get("schedule") or []
        crons = [s.get("cron") for s in schedule if isinstance(s, dict) and s.get("cron")]
        if not crons:
            continue
        periods = [p for p in (period_of(c) for c in crons) if p]
        found.append({"file": name, "name": doc.get("name") or name, "cron": "; ".join(crons),
                      "period_seconds": min(periods) if periods else None,
                      "run_bound_seconds": run_bound_of(doc)})
    return found


def _run(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", "run_number", "status", "conclusion", "created_at",
                                  "updated_at", "html_url", "head_sha")}


def read(root: str = ROOT, get=None) -> dict:
    """Each scheduled workflow with its newest scheduled runs on main. A workflow GitHub could
    not be asked about carries its ``error`` and the rest are kept; when none could be asked the
    read fails, so the last good value stands."""
    from modules.readers import ci_verdict as CV

    mod = CV.deploy_script()
    get = get or mod.github_get
    slug = mod.slug_of(mod.git(root, "remote", "get-url", "origin"))
    workflows, tried, asked = [], 0, 0
    for w in scheduled_workflows(root):
        if w.get("error"):
            workflows.append(w)
            continue
        tried += 1
        _status, body, reason = get(f"/repos/{slug}/actions/workflows/{w['file']}/runs"
                                    f"?event=schedule&branch=main&per_page={PER_PAGE}")
        if body is None:
            workflows.append(dict(w, error=f"GitHub's runs could not be read ({reason})"))
            continue
        asked += 1
        runs = [_run(r) for r in body.get("workflow_runs") or []]
        done = [r for r in runs if r.get("status") == "completed"]
        newest = done[0] if done else None
        success = next((r for r in done if r.get("conclusion") == "success"), None)
        failed_at = None
        if newest and newest.get("conclusion") in FAILED:
            where = CV.failed_steps({"slug": slug, "id": str(newest.get("id") or "")}, get=get)
            failed_at = where.get("steps") or None
        workflows.append(dict(w, runs_listed=len(runs), newest=newest, last_success=success,
                              oldest_listed=(runs[-1].get("created_at") if runs else None),
                              failed_at=failed_at))
    if tried and not asked:
        raise RuntimeError("GitHub could not be asked about any scheduled workflow: "
                           + "; ".join(f"{w['file']}: {w['error']}" for w in workflows))
    return {"slug": slug, "workflows": workflows}


def _epoch(stamp):
    try:
        return calendar.timegm(time.strptime(str(stamp), "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def overdue_after(w: dict):
    """How long after its last success a workflow is overdue: its period, GitHub's start delay
    and its run's bound. None when its period could not be read from its cron."""
    period = w.get("period_seconds")
    if not period:
        return None
    return period + START_DELAY_SECONDS + int(w.get("run_bound_seconds") or 0)


def judge(w: dict, now: float = None) -> dict:
    """``{"state": "ok" | "failed" | "overdue" | "unread", "words"}`` for one stored workflow:
    failed when its newest completed scheduled run did not succeed; overdue when it did, or
    none is listed, but no scheduled run has succeeded within :func:`overdue_after`."""
    now = time.time() if now is None else now
    if w.get("error"):
        return {"state": "unread", "words": w["error"]}
    newest, success = w.get("newest"), w.get("last_success")
    if success:
        since = f"last succeeded in run #{success.get('run_number')}, {success.get('updated_at')}"
    else:
        since = (f"no success in its last {w.get('runs_listed') or 0} scheduled runs"
                 + (f", since {w['oldest_listed']}" if w.get("oldest_listed") else ""))
    if newest and newest.get("conclusion") != "success":
        return {"state": "failed",
                "words": f"its newest scheduled run, #{newest.get('run_number')} of "
                         f"{newest.get('created_at')}, ended {newest.get('conclusion')}; {since}"}
    limit = overdue_after(w)
    done_at = _epoch((success or {}).get("updated_at"))
    if limit and (done_at is None or now - done_at > limit):
        return {"state": "overdue",
                "words": f"{since}: more than its {limit // 3600} h (its period, GitHub's start "
                         f"delay and its run's bound) ago"}
    return {"state": "ok", "words": since}


READER = reader_job.register(reader_job.Reader(
    name=NAME,
    what="each scheduled workflow's newest scheduled runs on main, for Needs attention (C2347)",
    endpoints=("GitHub Actions runs of each workflow with a schedule, and a failed run's jobs",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("GitHub allows 60 unauthenticated requests an hour per address, shared with "
                    "nmas-deploy and the ci-verdict reader; a read costs one per scheduled "
                    "workflow and one per failed newest run, so every 30 min is 4 to 8 an hour "
                    "for two workflows, and a daily job's failure is said within 30 min of "
                    "GitHub recording it"),
    read=read,
    invalidates=("scheduled_jobs",),
    remedy="Read the error above: it names the workflow and what GitHub answered",
    window="the newest scheduled runs at the read, up to 10 per workflow",
))
