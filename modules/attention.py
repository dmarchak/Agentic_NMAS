"""Needs attention: one list, every source, one row shape (Stage 7.2).

NSOT_STAGE7_PLAN section 1a, and NSOT_PLAN 8.6 for what Stage 8 needs left
room for. "Approvals", "Jobs" and "Drift" as places would each be one source
of needs attention, which is the four-places failure the operator named, so
each is a SOURCE here and this module is the one place that joins them.

THE ROW. Every row, from every source, has the same parts: WHAT is wrong,
which DEVICES (or none: a job is not a device), SINCE when (None when the
source does not record it, drawn as "not recorded", never as now), the CAUSE
in the source's own words, the OPERANDS it compared, the ONE ACTION that
addresses it, a LEVEL (decided here, only drawn in the browser), and an empty
TRIAGE slot that Stage 8's report fills. `row()` is the only constructor and
refuses a row with no cause or no action, as `preview_confirm` refuses a
silent part: a row that says something is wrong and not why, or not what to
do, is the complaint every other panel in this tool was rebuilt to stop
making. An action a source does not record is stated as not known
(``known: False``), never invented.

THE SOURCE. Each source is read into one result: its state (``read`` or
``unreadable``), WHEN it was read, how long the read took, and WHAT it looked
at. A source that could not be read is a ROW, never an absence, because "the
check could not run" and "the check found nothing" otherwise print the same
empty list. An empty page therefore names every source and its time: an empty
list must say what was looked at.

Nothing here does per-device work per request (section 0a). job health is
read live because its cost is per JOB, not per device; its read time is
reported beside it, so the host's measurement decides whether it moves to a
cache, rather than a guess.
"""

import logging
import time

log = logging.getLogger(__name__)

#: Worst first. The browser draws the level; it never decides it. There is no
#: information level (the operator, 2026-10-02): a fact nobody can act on
#: ("a new release is available", "a retired device's lab file is still
#: there") is true and is not wrong, so it belongs on its own page's detail,
#: and every row here names something wrong and what a person does about it.
LEVELS = ("danger", "warning", "unknown")

#: EVERY kind of row a source can emit, with what is wrong and the action a
#: person takes (the operator, 2026-10-02: "every Needs attention row must name
#: something wrong AND an action a person can take"). `row()` refuses a kind not
#: declared here, so a new kind arrives with its action or not at all; a scan
#: holds every `row(` call in this module to a declared kind, both ways. The
#: row's own action names the specifics; this is the kind's contract.
#: Source ``*`` is a kind any source emits.
ROW_KINDS = {
    ("*", "unreadable"): ("a source could not be read, so what it would show is unknown",
                          "find why it cannot be read: the cause names what failed"),
    ("job_health", "job"): ("a job or check is failing, stale, not installed or could not ask",
                            "its own remedy, or read its output on the host, or install it"),
    ("drift", "disabled"): ("drift checking is switched off", "switch it back on"),
    ("drift", "never"): ("drift has never been checked", "run a drift check"),
    ("drift", "failed"): ("the last drift check failed", "run it again and read its reason"),
    ("drift", "stale"): ("the last drift check is old", "run a drift check"),
    ("drift", "drifted"): ("a device differs from its golden", "capture it, or put it back"),
    ("drift", "skipped"): ("a device was not checked for drift",
                           "capture its golden, or clear what the reason names and run again"),
    ("drift", "unreachable"): ("a device could not be checked for drift",
                               "check it answers, then run a drift check"),
    ("approvals", "pending"): ("an approval is waiting for a person", "review it"),
    ("onboarding", "credential"): ("a pending device's staged credential cannot be found",
                                   "abandon it and onboard it again"),
    ("onboarding", "overdue"): ("a device onboarded long ago was never reached",
                                "verify it, or abandon it"),
    ("rollback", "record"): ("the rolled-back record cannot be read, blocking every plan",
                             "repair it from its preserved copy"),
    ("rollback", "blocked"): ("a device's next plan is blocked by a rolled-back change",
                              "revert the failed intent, or authorise a retry"),
    ("deploys", "failed"): ("the last deploy or restore to a device did not succeed",
                            "read its receipt, then plan again"),
    ("baseline", "denied"): ("the last baseline was not earned", "resolve each departure, then Save All"),
    ("baseline", "unusable"): ("no stored baseline can be re-applied", "take a current baseline"),
    ("authorisations", "repeated"): ("one line is authorised again and again",
                                     "read the reasons; move the line into intent, or its cause"),
    ("grafana", "stalled"): ("Grafana stopped evaluating a rule group", "check its scheduler"),
    ("grafana", "incident"): ("an alert is firing", "check its path, or read the rule"),
    ("grafana", "series"): ("an alert is firing on one series",
                            "read the rule, or acknowledge a chronic one within its band"),
    ("grafana", "rule"): ("a rule reads no data or cannot evaluate", "read its query in Grafana"),
    ("grafana", "heartbeat-floor"): ("a device has no heartbeat rule Grafana shows",
                                     "regenerate the rules, then check the reader's role"),
    ("freshness", "not-compared"): ("Oxidized's copies could not be compared",
                                    "check Oxidized answers; the comparison runs again"),
    ("freshness", "unapproved"): ("Oxidized holds a change nobody approved",
                                  "capture it if wanted, or put it back"),
    ("freshness", "inconclusive"): ("whether Oxidized's copy is approved cannot be told",
                                    "decide whether its copy is wanted: capture it, or put it back"),
    ("integrations", "down"): ("an integration is down", "check it at its configured URL"),
    ("integrations", "refused"): ("an integration refuses the tool's credential",
                                  "renew it where the service issues it and put it in Settings"),
    ("credential-health", "expiry"): ("a credential expires soon, or has expired",
                                      "renew it where the service issues it and put it in Settings"),
    ("credential-health", "age"): ("a credential is older than the age it is kept",
                                   "rotate it"),
    ("credential-health", "unread"): ("a credential's expiry cannot be read",
                                      "read it where the service shows it"),
    ("ci", "verdict"): ("the running commit has no CI pass",
                        "update to a release CI passed, or find why CI could not be asked"),
    ("reachability", "not-answering"): ("devices are not answering", "check the path, then each"),
    ("netbox-secrets", "held"): ("NetBox holds a credential in a device's context",
                                 "mask it, remove it by hand, or repair the record first"),
    ("pushed", "release"): ("the host runs a release that is wrong to keep running",
                            "update, or find where the running commit came from"),
    ("pushed", "ci_failed"): ("CI failed (or was cancelled) for the newest pushed commit, so the "
                              "Update button refuses it", "the developer fixes forward"),
    ("remote", "publication"): ("a list's history is not on its remote",
                                "push, acknowledge, repair the remote, or verify it"),
    ("host_steps", "owed"): ("a host step a release asked for is not done", "do it, then say so"),
    ("adjacencies", "link"): ("an adjacency intent implies is not up",
                              "check the link and both ends"),
    ("adjacencies", "unmeasured"): ("adjacencies cannot be judged", "check the Prometheus targets"),
    ("restarts", "unplanned"): ("a device restarted and nothing planned it",
                                "read the device's reason and crash file, and check the host then"),
    ("operations", "interrupted"): ("an operation on a device did not finish: the process ended "
                                    "while it held the device",
                                    "read each device as it is now and compare it with its "
                                    "golden before changing it, then acknowledge what you found"),
    ("adjacencies", "error"): ("a list's intent could not be read for its adjacencies",
                               "fix the intent file the reason names"),
    ("lab-startup", "moved"): ("a device moved since the baseline its lab file is built from",
                               "Save All earns a new baseline"),
    ("lab-startup", "differs"): ("a lab startup file is not what the sync builds",
                                 "read the lab sync's job-health row"),
    ("lab-startup", "not_built"): ("the sync builds no file for a device",
                                   "Save All earns a baseline that holds it"),
    ("lab-startup", "missing"): ("a managed device has no lab startup file", "check the sync's run"),
    ("lab-startup", "unknown"): ("lab startup files could not be compared",
                                 "check the lab host answers"),
}

#: The ways a row leaves the page (the operator, 2026-10-02): the CONDITION RESOLVING (the
#: source reads it fixed: by the action, or by itself), a person ACKNOWLEDGING it with a
#: reason, or TIME passing.
CLEAR_WAYS = ("resolves", "acknowledge", "time")

#: HOW EVERY KIND CLEARS, drawn on the row as "Clears when …" (the operator, 2026-10-02:
#: "for EVERY row kind … state how it clears"). Each entry is the ways (CLEAR_WAYS) and the
#: words; a test holds this to ROW_KINDS both ways, and the words to what each source's code
#: actually does. A row that could never clear is a defect this table makes visible: the
#: repeated authorisation's count only grows, so it was a row for ever until a person could
#: acknowledge it.
CLEARS = {
    ("*", "unreadable"): (("resolves",), "the source is read again successfully"),
    ("job_health", "job"): (("resolves",), "the job's next run or check reads ok (job health "
                            "re-reads every 5 minutes; a root-installed helper's row is asked "
                            "again at the next read of this page)"),
    ("drift", "disabled"): (("resolves",), "drift checking is switched back on"),
    ("drift", "never"): (("resolves",), "a drift check runs for this list"),
    ("drift", "failed"): (("resolves",), "a later drift check completes"),
    ("drift", "stale"): (("resolves",), "a drift check runs"),
    ("drift", "drifted"): (("resolves",), "a later drift check finds it matching its golden, "
                           "or a golden is recorded for it (a capture answers the stored run)"),
    ("drift", "skipped"): (("resolves",), "a later drift check checks it"),
    ("drift", "unreachable"): (("resolves",), "a later drift check reaches it"),
    ("approvals", "pending"): (("resolves", "time"), "a person approves or rejects it, or 48 h "
                               "pass and it expires (expiry executes nothing)"),
    ("onboarding", "credential"): (("resolves",), "the device is abandoned"),
    ("onboarding", "overdue"): (("resolves",), "Verify reaches it, or it is abandoned"),
    ("rollback", "record"): (("resolves",), "the rolled-back record can be read again"),
    ("rollback", "blocked"): (("resolves",), "its intent no longer sends what was rolled back "
                              "(reverted or edited), or a retry is authorised with a reason"),
    ("deploys", "failed"): (("resolves",), "a later deploy or restore to the device finishes "
                            "clean"),
    ("baseline", "denied"): (("resolves",), "a later save earns a baseline"),
    ("baseline", "unusable"): (("resolves",), "a stored baseline can be re-applied: a new one "
                               "is earned"),
    ("authorisations", "repeated"): (("acknowledge",), "a person acknowledges it with a reason; "
                                     "the line authorised once more raises it again"),
    ("grafana", "stalled"): (("resolves",), "Grafana evaluates the group again"),
    ("grafana", "incident"): (("resolves",), "the alert stops firing in Grafana (a silence "
                              "keeps it a row, saying who silenced it)"),
    ("grafana", "series"): (("resolves", "acknowledge"), "the alert stops firing, or a person "
                            "acknowledges it within its measured 7-day band; it comes back, "
                            "naming the band and the value, when the value leaves the band"),
    ("grafana", "rule"): (("resolves",), "the rule reads data and evaluates again"),
    ("grafana", "heartbeat-floor"): (("resolves",), "Grafana shows a heartbeat rule for the "
                                     "device"),
    ("freshness", "not-compared"): (("resolves",), "Oxidized's copies are compared again"),
    ("freshness", "unapproved"): (("resolves", "acknowledge"), "Oxidized's copy matches the "
                                  "golden again (captured, or put back and fetched), or a person "
                                  "authorises that one divergence with a reason, for 24 h"),
    ("freshness", "inconclusive"): (("resolves",), "a later comparison can tell whether the "
                                    "copy was approved"),
    ("integrations", "down"): (("resolves",), "it answers the next probe (every 60 s)"),
    ("integrations", "refused"): (("resolves",), "the next probe (every 60 s) is accepted"),
    ("credential-health", "expiry"): (("resolves",), "the reader (hourly) reads an expiry more "
                                      "than 30 days away"),
    ("credential-health", "age"): (("resolves",), "the reader (hourly) reads it set within "
                                   "180 days"),
    ("credential-health", "unread"): (("resolves",), "the reader (hourly) reads its expiry"),
    ("ci", "verdict"): (("resolves",), "the host runs a commit CI passed"),
    ("reachability", "not-answering"): (("resolves",), "every device answers its probe again "
                                        "(every 5 s)"),
    ("netbox-secrets", "held"): (("resolves",), "NetBox no longer holds the credential (masked "
                                 "or removed), at the next hourly read"),
    ("pushed", "release"): (("resolves",), "the host runs the commit the remote holds"),
    ("pushed", "ci_failed"): (("resolves",), "a newer commit is pushed (its update is offered "
                              "once CI passes it), or the host runs this one"),
    ("remote", "publication"): (("resolves",), "the remote holds the list's history: pushed, "
                                "after a held push is acknowledged on the Remote card"),
    ("host_steps", "owed"): (("resolves", "acknowledge"), "its check finds it done, or a person "
                             "says it is done on the Update page"),
    ("adjacencies", "link"): (("resolves",), "the next read finds the adjacency up"),
    ("adjacencies", "unmeasured"): (("resolves",), "Prometheus scrapes the protocol again"),
    ("adjacencies", "error"): (("resolves",), "the intent file can be read"),
    ("operations", "interrupted"): (("acknowledge",), "a person acknowledges it with a reason, "
                                    "after reading the devices; the record stays in the list's "
                                    "interrupted.jsonl"),
    ("restarts", "unplanned"): (("acknowledge", "time"), "a person acknowledges it with a "
                                "reason, or 7 days after the restart; History keeps it either "
                                "way"),
    ("lab-startup", "moved"): (("resolves",), "an earned baseline holds the device as it is "
                               "now"),
    ("lab-startup", "differs"): (("resolves",), "the lab sync writes the file it builds"),
    ("lab-startup", "not_built"): (("resolves",), "a baseline holds the device and the sync "
                                   "builds its file"),
    ("lab-startup", "missing"): (("resolves",), "the lab sync writes the file"),
    ("lab-startup", "unknown"): (("resolves",), "the lab host answers the next read"),
}

#: The kinds a person acknowledges HERE, with "Acknowledge…" on the row (modules/
#: acknowledgements.py): an event that cannot un-happen. Each row of these kinds carries
#: its *event*, so an acknowledgement covers that event and never a later one. Other kinds
#: whose CLEARS names acknowledge do it through their own control, named in their words.
ACKNOWLEDGED_HERE = frozenset({("restarts", "unplanned"), ("authorisations", "repeated"),
                               ("operations", "interrupted"),
                               # Within its measured band, never for good (C433).
                               ("grafana", "series")})

#: Words that say there is nothing to do: an action is a thing a person does.
NOT_AN_ACTION = ("nothing to do", "it is information", "is what is known",
                 "is all that is recorded", "no remedy is recorded", "whole of what is known")


class RowRefused(ValueError):
    """A row missing a part it must have."""


def _iso(ts) -> str:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def row(*, source: str, kind: str, key: str, what: str, cause: str, action: dict,
        level: str, devices=(), since=None, operands: dict = None,
        attach_to: str = None, event: str = None, clears_at=None, read_at=None) -> dict:
    """The only constructor for a Needs attention row.

    *kind* names the row's declared kind (ROW_KINDS): what is wrong and the
    action a person takes. An undeclared kind, an information level, or an
    action whose words say there is nothing to do is refused: a fact nobody
    can act on goes to its own page's detail, never here.

    *attach_to* names another row's id this one is ABOUT (a queued drift
    item is about its device's drift row). The page merges it into that row
    instead of drawing a second row about one event; it stands alone only
    when that row is absent.

    *event* names the one event a row of an ACKNOWLEDGED_HERE kind is about (a restart's
    time), which an acknowledgement is keyed on; such a row without one is refused, since
    an acknowledgement of it could not tell this event from the next."""
    missing = [n for n, v in (("source", source), ("key", key), ("what", what),
                              ("cause", cause)) if not str(v or "").strip()]
    if not isinstance(action, dict) or not str(action.get("label") or "").strip():
        missing.append("action")
    if missing:
        raise RowRefused(f"a Needs attention row without {', '.join(missing)} "
                         "says something is wrong and not why or what to do")
    if (source, kind) not in ROW_KINDS and ("*", kind) not in ROW_KINDS:
        raise RowRefused(f"row kind {source}/{kind} is not declared in ROW_KINDS with what "
                         "is wrong and the action a person takes")
    if level not in LEVELS:
        raise RowRefused(f"level {level!r} is not one of {LEVELS}: a fact nobody acts on "
                         "belongs on its own page's detail, not in Needs attention")
    said = str(action["label"]).lower()
    if any(p in said for p in NOT_AN_ACTION):
        raise RowRefused(f"the action {action['label']!r} says there is nothing to do: a row "
                         "with no action belongs on its own page's detail")
    declared = (source, kind) if (source, kind) in ROW_KINDS else ("*", kind)
    ways, when = CLEARS[declared]
    acknowledgeable = declared in ACKNOWLEDGED_HERE
    if acknowledgeable and not str(event or "").strip():
        raise RowRefused(f"a {source}/{kind} row is acknowledged per event, and names none")
    return {"id": f"{source}:{key}", "source": source, "kind": kind, "what": what,
            "clears": {"ways": list(ways), "when": when},
            # When a row that clears by TIME will clear (an approval's expiry, an unplanned
            # restart's seven days): nothing announces that moment, so the page and the
            # sidebar's count re-read at it (the operator, 2026-10-02: the count must be right
            # at all times).
            "clears_at": _iso(clears_at) if clears_at else None,
            "event": str(event) if event else None, "acknowledge": acknowledgeable,
            "devices": [d for d in devices if d], "since": _iso(since),
            # When the reading behind the row was taken, for a row drawn from a stored value
            # (C439: a job-health row stayed wrong for minutes, and nothing showed its age).
            "read_at": _iso(read_at) if read_at else None,
            "cause": cause, "operands": dict(operands or {}),
            "action": {"known": True, **action}, "level": level,
            "attach_to": attach_to, "attached": [],
            # Stage 8 attaches its triage HERE, on the row, never as a row of
            # its own (NSOT_PLAN 8.6): two rows about one event is the
            # three-reports problem restated on the page.
            "triage": None}


def source_result(source: str, label: str, *, read_at: float, took_ms: int,
                  rows=None, checked: str = "", error: str = "",
                  value_at: float = None, stale_after_seconds: int = None,
                  reader: str = None, detail: str = "") -> dict:
    """One source, read. *error* makes the source a row of its own.

    *read_at* is when this request read the source; *value_at* is the time of
    the VALUE it shows (section 1a), which for a stored result (the last drift
    run) is earlier, and for a live read (job health) is the same. Collapsing
    them would draw a day-old drift run as read "just now".

    *stale_after_seconds* is how long the value stays current, by the
    source's own promise (a reader's interval times its staleness factor, a
    drift run's interval times two). The PAGE judges age against it on its
    own clock (the live-data contract, 7.2 step 13), so a stored value whose
    producer has stopped is drawn stale without another request. None means
    the value was read for this request, and its freshness is the panel's.

    *reader* names the reader job behind a stored value, so the page can tell
    that job health's row for a stopped reader already covers a stale source
    and not draw the same fact twice.

    *checked* says what was FOUND, for a person; *detail* is the debugger's
    part (endpoints, read costs), drawn one level down, on hover (the
    operator's presentation rule, 2026-09-28)."""
    if error:
        # Kept where it outlives the row (the operator, 2026-09-29): a transient
        # "could not be read: Approvals" cleared on the next read, and nothing
        # anywhere said which read failed or why.
        log.warning("attention: %s could not be read: %s", label, error)
        return {"source": source, "label": label, "state": "unreadable",
                "read_at": _iso(read_at), "value_at": None, "took_ms": took_ms,
                "checked": "nothing: the read failed",
                "rows": [row(source=source, kind="unreadable", key="unreadable", level="unknown",
                             what=f"{label} could not be read",
                             cause=(f"{error}. This is not the same as nothing needing "
                                    "attention: whatever this source would show is "
                                    "unknown until it can be read"),
                             action={"label": "Find why the source cannot be read: "
                                              "the cause above names what failed",
                                     "known": False})]}
    if not checked:
        raise RowRefused(f"source {source!r} read without saying what it looked at: "
                         "an empty result must say what was checked")
    return {"source": source, "label": label, "state": "read",
            "read_at": _iso(read_at),
            "value_at": _iso(read_at if value_at is None else value_at),
            "stale_after_seconds": stale_after_seconds, "reader": reader, "detail": detail,
            "took_ms": took_ms, "checked": checked, "rows": list(rows or [])}


# ---------------------------------------------------------------------------
# Source: job health (the first source; C54's rows already had the shape)
# ---------------------------------------------------------------------------

#: How each job-health state reads as WHAT is wrong, and how loud it is.
_JOB_STATES = {
    "failing": ("is failing", "danger"),
    "never_succeeded": ("has never succeeded", "danger"),
    "not_installed": ("is not installed", "danger"),
    "stale": ("has not succeeded recently", "warning"),
    "unknown": ("could not be checked", "unknown"),
    "unset_guard": ("is an empty setting that switches off a guard", "warning"),
    "contradiction": ("is declared not applicable and is also set", "warning"),
    "not_safe_to_reboot": ("would not survive a reboot", "danger"),
    # The startup check could not READ a device: not the critical finding
    # above (the operator, 2026-10-01), and a warning only once it persists.
    "unread": ("could not read a device this hour", "unknown"),
    "unread_persisting": ("has not read a device for hours", "warning"),
    "not_recorded": ("was rotated and not recorded", "danger"),
    "revert_failed": ("failed a rotation and its revert", "danger"),
    "neither_accepted": ("accepts neither its staged nor its recorded credential", "danger"),
    "at_budget": ("has no SSH session left for the next operation", "warning"),
    "leaked": ("holds an operation's SSH session past ten minutes", "warning"),
    "mixed_version": ("is running a different commit from its checkout", "danger"),
    "socket_down": ("is not listening", "danger"),
    "mismatch": ("does not match what was declared", "warning"),
    "not_run": ("has never run on this host", "warning"),
    "not_monitored": ("is not configured for an integration the network uses", "warning"),
    "breakglass_stale": ("is not recoverable from the break-glass record: it holds an "
                         "older credential", "danger"),
    "breakglass_not_intact": ("break-glass record's last download did not arrive intact",
                              "danger"),
    "breakglass_drill_overdue": ("break-glass record has not been opened offline for 90 days",
                                 "warning"),
    # The Update button's root-owned updater (docs/UPDATE.md).
    "writable": ("is run as root and writable by someone else", "danger"),
    # Oxidized's router.db still holding a device the tool retired (C398).
    "orphaned": ("still holds a device the tool retired", "warning"),
    "cannot_run": ("cannot run: a program it needs is missing or not root's", "danger"),
    "path_inactive": ("is not watching for update requests", "danger"),
    "differs": ("differs from this release's copy", "warning"),
    # The nightly VM images' storage (B6). These four reached the page as
    # "reads will_not_fit" in danger (C288): every state job health can
    # write has its words here, held by test_job_health.
    "will_not_fit": ("has too little free space for the next run's largest image", "warning"),
    "images_missing": ("holds less than the newest images add up to: one was removed", "danger"),
    "inactive": ("is not mounted or is disabled: the next run will fail", "danger"),
    "unsized": ("has no image size yet to judge the next run against", "unknown"),
    "missing": ("no longer lists the image its last run wrote", "danger"),
    "never": ("has no backup task on record", "warning"),
    "not_configured": ("is not configured, so nothing watches it", "unknown"),
    "pool_unhealthy": ("is not ONLINE: a suspended pool stops every write", "danger"),
    "pool_will_pause": ("is near ZFS's reserve: every VM on it pauses there", "danger"),
    "pool_degrading": ("is past the fill where allocation slows", "warning"),
    "pool_filling": ("is filling: an LVM-thin pool that fills stops its VMs' writes", "danger"),
}


def _job_action(job: dict) -> dict:
    """The ONE action for a job-health row, where the source records one."""
    from modules import job_health as J

    # The row's OWN action first (C164): the builder that wrote the remedy
    # into the detail is the one place that knows it, and names it as a field.
    if isinstance(job.get("action"), dict) and job["action"].get("label"):
        return dict(job["action"])
    systemd_units = {j["unit"] for j in J.JOBS}
    unit, state = job.get("unit", ""), job.get("state", "")
    if unit in systemd_units:
        if state == "not_installed":
            return {"label": "Install and enable the unit on the host",
                    "reference": "docs/DEPLOY_LINUX.md"}
        return {"label": "Read the job's own output on the host",
                "command": f"journalctl -u {unit}.service -n 50 --no-pager"}
    # A row with no remedy of its own: the action its STATE implies, never
    # "nothing is known" (the operator, 2026-10-02: every row has an action).
    return dict(_STATE_ACTIONS.get(state, _STATE_ACTIONS["*"]), known=False)


#: The action a job-health row's state implies when its check names none.
_STATE_ACTIONS = {
    "unknown": {"label": "Find why the check could not ask: its detail above names what it "
                         "read, and it asks again on its next run"},
    "stale": {"label": "Find why the check has not run: run it by hand on the host, or read "
                       "its timer's own row"},
    "unset_guard": {"label": "Set it in Settings, or declare it not applicable on the host "
                             "(settings_not_applicable) with a reason"},
    "contradiction": {"label": "Clear the setting, or withdraw its not-applicable declaration: "
                               "only one can be true"},
    "*": {"label": "Fix what its detail above names: the file, setting or service the "
                   "check read"},
}


JOB_HEALTH_READER = "job-health"
#: Job-health states that are expected and need nothing yet: the startup check
#: missing a device for one run (it is booting, or slow; a warning once it
#: persists, as `unread_persisting`). Said in the source's finding, not a row.
EXPECTED_JOB_STATES = ("unread",)


def _install_rows_asked_again(jobs: list) -> list:
    """*jobs* with every stored row about a root-installed file that reads not-ok replaced by
    its check asked now (C439, the operator, 2026-10-04: minutes after a correct install of
    the Oxidized helper, the stored reading still said it differed, while the host-step check
    of the same file, asked live, said done). Only a not-ok row is asked again: the Oxidized
    helper's check runs `sudo -n -l`, so asking an ok one on every page view would be a sudo
    query per view, and the rotation's preflight asks the helper itself, live, so a stale ok
    never lets a wrong install through. A check that raises keeps the stored row."""
    from modules import host_helpers
    from modules import job_health as J

    again = {j.get("unit") for j in jobs
             if j.get("unit") in host_helpers.INSTALL_UNITS and j.get("state") not in J.OK_STATES}
    if not again:
        return jobs
    out = [j for j in jobs if j.get("unit") not in again]
    for unit in sorted(again):
        try:
            fresh = host_helpers.ask_now(unit)
        except Exception as exc:                            # noqa: BLE001
            log.warning("attention: %s could not be asked again: %s", unit, exc)
            fresh = [j for j in jobs if j.get("unit") == unit]
        else:
            at = time.time()
            fresh = [dict(j, _read_at=at) for j in fresh]
        out += fresh
    return out


def job_health_source(health=None, now=None, cached=None, readers_now=None) -> dict:
    """Every job-health row that is not ok, as a Needs attention row.

    By default from the job-health READER's stored value, never from systemd
    (rule 1 of modules/reader_job.py): read live, it was 9.8 s of a 10 s
    page (measured on the host, 2026-09-28). *health* is a live read for a
    caller that has one (the tests; `/jobs/health` stays live by design).

    The readers' OWN liveness is judged now, from their stores (*readers_now*,
    a file read each), never taken from the cached value: a stopped
    job-health reader would otherwise report itself ok for ever."""
    from modules import job_health as J
    from modules import reader_job

    started = time.time()
    value_at = None
    if health is not None:
        try:
            h = health()
            jobs = list(h["jobs"])
        except Exception as exc:                   # noqa: BLE001
            log.error("attention: job health could not be read: %s", exc)
            return source_result("job_health", "Job health", read_at=started,
                                 took_ms=int((time.time() - started) * 1000),
                                 error=f"it raised {type(exc).__name__}: {exc}")
        where, promise = "read now", None
    else:
        got = reader_job.read_cached(JOB_HEALTH_READER) if cached is None else cached
        doc = got.get("doc") or {}
        good = doc.get("last_good") or {}
        took = int((time.time() - started) * 1000)
        if got["state"] != "ok" or not good:
            # Never a "nothing needs attention": no value is not an empty value.
            why = (got.get("why") if got["state"] != "ok" else
                   "the job-health reader has never stored a value; its last attempt: "
                   + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
            return source_result("job_health", "Job health", read_at=started, took_ms=took,
                                 error=f"not read yet: {why} (it runs in the app, every "
                                       f"{doc.get('interval_seconds') or 'few'} s)")
        try:
            jobs = [j for j in good["value"]["health"]["jobs"]
                    if not str(j.get("unit", "")).startswith("reader:")]
        except (KeyError, TypeError) as exc:
            return source_result("job_health", "Job health", read_at=started, took_ms=took,
                                 error=f"the stored value has no job rows ({type(exc).__name__})")
        value_at = reader_job._parse_iso(good.get("value_at"))
        jobs = _install_rows_asked_again(jobs)
        promise = doc.get("stale_after_seconds")
        where = f"stored by the reader, read in {good.get('took_ms', '?')} ms"
        try:
            live = (reader_job.health_rows() if readers_now is None else list(readers_now))
        except Exception as exc:                   # noqa: BLE001
            live = [{"unit": "reader:*", "what": "the reader jobs' liveness", "state": "unknown",
                     "detail": f"the readers could not be judged: {type(exc).__name__}: {exc}"}]
        jobs += live
    took = int((time.time() - started) * 1000)
    rows, expected = [], []
    for job in jobs:
        state = job.get("state", "")
        if state in J.OK_STATES:
            continue
        if state in EXPECTED_JOB_STATES:
            # Expected and nothing to do yet (the operator, 2026-10-02): said in
            # this source's finding, never as a row.
            expected.append(job.get("headline") or f"{job.get('unit', '?')}: {state}")
            continue
        # An unmapped state is drawn LOUD with its own name: a state added
        # to job_health later must not arrive here as something quieter.
        words, level = _JOB_STATES.get(state, (f"reads {state}", "danger"))
        device = job.get("device") or job.get("address")
        rows.append(row(
            source="job_health", kind="job", key=job.get("unit", "?"),
            # A row may name its own headline, in the reader's words ("r6 is not
            # monitored by SNMP"); otherwise the unit and its state's words.
            what=job.get("headline") or f"{job.get('unit', '?')} {words}",
            devices=list(job.get("devices") or ([device] if device else [])),
            since=job.get("since"),
            cause=job.get("detail") or f"state {state}, with no detail recorded",
            operands={"job": job.get("what", ""), "state": state},
            action=_job_action(job), level=level,
            read_at=job.get("_read_at") or value_at or started))
    n_ok = len(jobs) - len(rows) - len(expected)
    return source_result("job_health", "Job health", read_at=started, took_ms=took,
                         rows=rows, value_at=value_at, stale_after_seconds=promise,
                         reader=JOB_HEALTH_READER if promise else None, detail=where,
                         checked=f"{len(jobs)} job-health row(s), {n_ok} ok"
                                 + (f"; expected, nothing to do yet: {'; '.join(expected)}"
                                    if expected else ""))


# ---------------------------------------------------------------------------
# Source: drift, with coverage (C96: the checker ran, found drift, and the
# panel drew none of it)
# ---------------------------------------------------------------------------

#: A stored run older than this many intervals is itself a row: the value on
#: the page is from a run that should have been superseded.
DRIFT_STALE_INTERVALS = 2

#: A drifted device's action when nothing is queued for it: both remedies
#: are on its Device page (7.1 steps 4 and 5). A queued drift item, when
#: there is one, attaches and its action replaces this.
_DRIFT_ACTION = {"label": "From its Device page: Capture the running config as the "
                          "golden, or Restore from the golden"}


def drift_source(status=None, now=None) -> dict:
    """The LAST drift run for the list on screen, from its stored record
    (section 0a: nothing re-checks a device to draw this page). Every device
    the run did not clear is a row, and so is the checker's own state: off,
    never run, a failed run, or a stored run too old to describe the network
    now."""
    from modules import drift_check as D

    started = time.time()
    now = now or started
    try:
        st = status() if status else D.get_checker().status()
        interval = D._get_interval()
    except Exception as exc:                       # noqa: BLE001
        log.error("attention: drift status could not be read: %s", exc)
        return source_result("drift", "Drift", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    lst = st.get("list") or "?"
    last, last_ts = st.get("last_run"), st.get("last_ts") or None
    rows = []

    def add(key, what, cause, action, level, devices=(), since=None, operands=None):
        rows.append(row(source="drift", kind=key.split(":", 1)[0], key=f"{lst}:{key}",
                        what=what, cause=cause,
                        action=action, level=level, devices=devices, since=since,
                        operands={"list": lst, **(operands or {})}))

    if st.get("disabled"):
        by = st.get("disabled_by") or "nobody recorded"
        add("disabled", f"Drift checking is switched off for {lst}",
            f"switched off by {by}; nothing compares the devices with their "
            "goldens until it is switched back on",
            {"label": "Switch drift checking back on in the Drift panel"},
            "warning", since=_ts(st.get("disabled_at")))
    if not last:
        add("never", f"Drift has never been checked for {lst}",
            "no drift run is recorded for this list, so whether any device has "
            "drifted is unknown",
            {"label": "Run a drift check from the Drift panel"}, "unknown")
        return source_result("drift", "Drift", read_at=started, took_ms=took, rows=rows,
                             checked=f"list {lst}: no drift run recorded")
    if last.get("ok") is False:
        add("failed", f"The last drift check for {lst} failed",
            last.get("summary") or last.get("error") or "no reason recorded",
            {"label": "Run a drift check from the Drift panel and read its reason"},
            "unknown", since=last_ts)
    elif last_ts and now - last_ts > DRIFT_STALE_INTERVALS * interval:
        add("stale", f"The last drift check for {lst} is old",
            f"it ran {int((now - last_ts) // 3600)} h ago, over "
            f"{DRIFT_STALE_INTERVALS} intervals of {int(interval // 60)} min: "
            "what it found describes the network as it was then",
            {"label": "Run a drift check from the Drift panel"}, "warning",
            since=last_ts + DRIFT_STALE_INTERVALS * interval)
    coverage = f"checked {last.get('checked', 0)} of {last.get('inventory', 0)}"
    for d in last.get("drifted_devices") or []:
        add(f"drifted:{d['hostname']}", f"{d['hostname']} has drifted from its golden",
            f"the running config differs from the committed golden by "
            f"{d.get('diff_lines', '?')} diff line(s), seen by the drift check at "
            f"{_iso(last_ts) or 'an unrecorded time'}; since when it has differed "
            "is not recorded", _DRIFT_ACTION, "danger", devices=[d["hostname"]],
            operands={"diff_lines": d.get("diff_lines"), "coverage": coverage})
    for d in last.get("skipped") or []:
        no_golden = d.get("reason") == "no golden config saved"
        add(f"skipped:{d['hostname']}", f"{d['hostname']} was not checked for drift",
            d.get("reason") or "no reason recorded",
            {"label": "Capture its golden from its Device page, or with Save All's "
                      "no-golden scope"} if no_golden else
            {"label": "Clear what the reason names, then run a drift check from the "
                      "Drift panel", "known": False},
            "warning", devices=[d["hostname"]], operands={"coverage": coverage})
    for d in last.get("errors") or []:
        # During a boot the reachability reader saw the device go silent: said
        # first, so a booting device does not read as a broken one.
        from modules.readers.reachability import outage_words
        booting = outage_words(d["hostname"], _ts(last_ts) or now)
        add(f"unreachable:{d['hostname']}", f"{d['hostname']} could not be checked for drift",
            (f"{booting[0].upper()}{booting[1:]}. The check said: " if booting else "")
            + (d.get("reason") or "no reason recorded"),
            {"label": "Check the device answers (its status on Devices), then run a drift "
                      "check from the Drift panel", "known": False},
            "unknown", devices=[d["hostname"]], operands={"coverage": coverage})
    return source_result("drift", "Drift", read_at=started, took_ms=took, rows=rows,
                         value_at=last_ts,
                         stale_after_seconds=int(DRIFT_STALE_INTERVALS * interval) or None,
                         checked=f"list {lst}, the run of {_iso(last_ts) or 'an unrecorded time'}: "
                                 f"{coverage}, triggered by {last.get('triggered_by') or 'unrecorded'}")


def _ts(value):
    """An epoch from a stored time that may be epoch or ISO text; None if neither."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        import calendar
        return float(calendar.timegm(time.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S")))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Source: the approval queue
# ---------------------------------------------------------------------------

#: The action types drift queues, one item per drifted device. Each is ABOUT
#: that device's drift row and attaches to it.
_DRIFT_ITEM_TYPES = ("update_golden_config",)


def approvals_source(read=None) -> dict:
    """Every pending approval, through a read that writes nothing. A queued
    drift item attaches to its device's drift row (the page must not count
    one event twice); anything else is a row of its own."""
    from modules import approval_queue as Q
    from modules.config import get_current_list_name

    started = time.time()
    try:
        lst = get_current_list_name()
        pending, reason = (read or Q.read_pending)()
    except Exception as exc:                       # noqa: BLE001
        pending, reason = None, f"it raised {type(exc).__name__}: {exc}"
    took = int((time.time() - started) * 1000)
    if reason:
        return source_result("approvals", "Approvals", read_at=started, took_ms=took,
                             error=reason)
    rows = []
    for e in pending:
        host = e.get("device_hostname") or e.get("device_ip") or ""
        drift_item = e.get("action_type") in _DRIFT_ITEM_TYPES and host
        rows.append(row(
            source="approvals", kind="pending", key=e.get("id") or "?",
            what=f"An approval is waiting: {e.get('description') or e.get('action_type')}",
            cause=(e.get("context") or "queued with no context recorded")
                  + "; nothing is done until a person approves it",
            action={"label": "Review it in Approvals"
                             + (": approving opens the capture preview"
                                if e.get("action_type") in Q.CONFIRM_ENDING_ACTIONS else "")},
            level="warning", devices=[host] if host else [], since=e.get("created_ts"),
            clears_at=((e.get("created_ts") or 0) + Q.EXPIRY_HOURS * 3600
                       if e.get("created_ts") else None),
            operands={"kind": e.get("action_type", ""), "list": lst},
            attach_to=f"drift:{lst}:drifted:{host}" if drift_item else None))
    return source_result("approvals", "Approvals", read_at=started, took_ms=took,
                         rows=rows, checked=f"list {lst}: {len(rows)} pending approval(s)")


# ---------------------------------------------------------------------------
# Source: pending onboardings
# ---------------------------------------------------------------------------

def pending_onboarding_source(pending=None, now=None) -> dict:
    """Devices onboarded and never reached. `in_flight` (under a day) is the
    normal state of an onboarding and is counted, not listed; overdue, stale
    and a staged credential nothing can find are rows. ZTP progress is not
    asked here: it asks Kea per device (section 0a); the pending banner
    carries it."""
    import os

    from modules.config import get_current_list_name, get_list_data_dir
    from modules.nsot.manifest import pending_devices

    started = time.time()
    try:
        lst = get_current_list_name()
        devices = (pending or (lambda: pending_devices(
            os.path.join(get_list_data_dir(lst), "config_repo"))))()
    except Exception as exc:                       # noqa: BLE001
        return source_result("onboarding", "Pending onboardings", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    rows = []
    for d in devices:
        name, state = d.get("name") or d.get("identity") or "?", d.get("state")
        since = _ts(d.get("onboarded_at"))
        if d.get("credential_findable") is False:
            rows.append(row(
                source="onboarding", kind="credential", key=f"{lst}:{name}:credential", level="danger",
                what=f"{name} cannot be verified: its staged credential cannot be found",
                cause=("the credential staged for it is not where verification looks, so "
                       "Verify would try a profile the device refuses; nothing has reached "
                       "the device, so there is nothing to undo"),
                action={"label": "Abandon it and onboard it again, from the pending banner"},
                devices=[name], since=since, operands={"list": lst, "state": state}))
        elif state in ("overdue", "stale"):
            hours = int((d.get("age_seconds") or 0) // 3600)
            rows.append(row(
                source="onboarding", kind="overdue", key=f"{lst}:{name}", level="warning",
                what=f"{name} was onboarded {hours} h ago and has never been reached",
                cause=("it is in the manifest and git and not in the inventory: nothing "
                       "polls, backs up or drift-checks it until Verify reaches it"),
                action={"label": "Verify it, or Abandon it, from the pending banner"},
                devices=[name], since=since, operands={"list": lst, "state": state,
                                                       "address_source": d.get("address_source")}))
    quiet = sum(1 for d in devices if d.get("state") == "in_flight"
                and d.get("credential_findable") is not False)
    return source_result("onboarding", "Pending onboardings", read_at=started, took_ms=took,
                         rows=rows,
                         checked=f"list {lst}: {len(devices)} pending, {quiet} within their "
                                 "first day")


# ---------------------------------------------------------------------------
# Source: rollback blocks
# ---------------------------------------------------------------------------

#: Revert intent and retry are the remedies, and both are routes with no
#: page yet; 7.3's Device actions are their home (C164). Stated, not hidden.
_ROLLBACK_ACTION = {"label": "Revert the intent that failed, or authorise a retry: "
                             "neither has a screen yet (7.3's Device actions)",
                    "known": False}


def rollback_source(notes=None) -> dict:
    """Devices whose rolled-back change still blocks their next plan. Uses
    the ONE classifier the listing uses (`rolled_back_notes`): a note blocks
    only while the program a fresh plan would send still contains what failed,
    so a stale note is counted, never listed as needing attention. Its work
    is per NOTED device, bounded by the rollbacks on record."""
    from modules.config import get_current_list_name

    started = time.time()
    try:
        lst = get_current_list_name()
        if notes is None:
            from routes.templatize import rolled_back_notes
            got = rolled_back_notes(lst)
        else:
            got = notes()
    except Exception as exc:                       # noqa: BLE001
        return source_result("rollback", "Rollback blocks", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    rows = []
    if got.get("unreadable"):
        # One row for the list: the record blocks EVERY plan, and a row per
        # device would be one event counted N times.
        rows.append(row(source="rollback", kind="record", key=f"{lst}:record", level="danger",
                        what=f"Every plan on {lst} is blocked: the rolled-back record "
                             "cannot be read",
                        cause=got["unreadable"],
                        action={"label": "Repair the record from its preserved copy; "
                                         "nothing here can rewrite it", "known": False},
                        operands={"list": lst}))
    for host, note in sorted((got.get("applies") or {}).items()):
        unknown = note.get("applicability") == "unknown"
        rows.append(row(
            source="rollback", kind="blocked", key=f"{lst}:{host}", level="unknown" if unknown else "warning",
            what=(f"{host}'s rolled-back change may still block its next plan" if unknown
                  else f"{host}'s next plan is blocked: its intent still sends what was "
                       "rolled back"),
            cause=(f"rolled back at {note.get('at') or 'an unrecorded time'}"
                   + (f" ({note['reason']})" if note.get("reason") else "")
                   + ("; whether the note still applies could not be computed"
                      if unknown else "")),
            action=_ROLLBACK_ACTION, devices=[host], since=_ts(note.get("at")),
            operands={"list": lst, "failed_lines": len(note.get("commands") or []),
                      "intent_commit": (note.get("intent_commit") or "")[:10]}))
    n_stale = len(got.get("stale") or {})
    return source_result("rollback", "Rollback blocks", read_at=started, took_ms=took,
                         rows=rows,
                         checked=(f"list {lst}: the rolled-back record could not be read"
                                  if got.get("unreadable") else
                                  f"list {lst}: {len(got.get('applies') or {})} standing, "
                                  f"{n_stale} no longer blocking"))


# ---------------------------------------------------------------------------
# Source: a deploy or restore that did not finish clean
# ---------------------------------------------------------------------------

def deploy_source(read=None) -> dict:
    """Each device's LATEST deploy or restore receipt, judged by the ONE
    decision the result screen uses (`preview_confirm.result_level`): a row
    unless it finished clean. A later clean run supersedes an earlier
    failure, so a device leaves the page by being deployed, not by aging.
    Danger when a program was SENT (the device may be part-changed), warning
    when nothing was (a refusal changed nothing, and the change it was for
    still has not landed)."""
    from modules.config import get_current_list_name
    from modules.nsot import receipts
    from modules.preview_confirm import OUTCOME_WORDS, result_level

    started = time.time()
    try:
        lst = get_current_list_name()
        got = (read or (lambda: receipts.read(lst, limit=10 ** 6)))()
    except Exception as exc:                       # noqa: BLE001
        got = {"state": "unreadable", "error": f"it raised {type(exc).__name__}: {exc}"}
    took = int((time.time() - started) * 1000)
    if got.get("state") == "unreadable":
        return source_result("deploys", "Deploys and restores", read_at=started, took_ms=took,
                             error=f"the deploy receipts could not be read ({got.get('error')})")
    latest = {}
    for r in got.get("rows") or []:                # newest first
        latest.setdefault(r.get("device") or "?", r)
    rows, pending_named = [], 0
    for host, r in sorted(latest.items()):
        if receipts.is_pending(r) and _pending_is_named(lst, host, r):
            # Written as the device finished, its batch's commit not recorded yet: its batch
            # is still running (the device is held), or its process ended and the
            # interrupted-operation row names it. Either way not clean, and not a second row.
            pending_named += 1
            continue
        if result_level([r], receipt_ok=True) == "success":
            continue
        outcome = r.get("outcome", "")
        rb = r.get("rollback") or {}
        checks = r.get("checks") or {}
        issues = [str(i) for i in checks.get("issues") or []]
        unmet = [str(p) for p in checks.get("intent_unmet") or []]
        unread = [str(p) for p in checks.get("unreadable") or []]
        cause = "; ".join(x for x in (
            r.get("reason"),
            f"stopped at {r['stage']}" if r.get("stage") else "",
            f"verify found: {'; '.join(issues)}" if issues else "",
            f"declared by intent and not up after: {', '.join(unmet)}" if unmet else "",
            f"could not be read reliably after the change: {'; '.join(unread)}"
            if unread else "",
            f"rollback: {rb.get('state')}" if rb.get("performed") else "",
            "the program sent does NOT match the one confirmed"
            if r.get("matches_confirmed") is False else "",
            # Pending, held by nothing and named by no interrupted operation: the line that
            # completes it could not be written (its result said RECEIPT NOT WRITTEN).
            "its receipt was written as the device finished and never completed with its "
            "batch's commit" if receipts.is_pending(r) else "") if x) or \
            f"its receipt records {outcome or 'no outcome'} with no reason"
        words = OUTCOME_WORDS.get(outcome, outcome.replace('_', ' ') or 'no outcome')
        if receipts.is_pending(r):
            words = ("sent" if outcome == "deployed" else words) + ", " + receipts.PENDING_WORDS
        rows.append(row(
            source="deploys", kind="failed", key=f"{lst}:{host}",
            level="danger" if r.get("sent") else "warning",
            what=f"The last {r.get('action') or 'deploy'} to {host}: {words}",
            cause=cause,
            action={"label": "Read its receipt on the device's Changes tab, then plan again"},
            devices=[host], since=_ts(r.get("at")),
            operands={"list": lst, "action": r.get("action"), "outcome": outcome,
                      "sent_lines": r.get("program_lines") if r.get("sent") else 0,
                      "by": r.get("actor")}))
    return source_result("deploys", "Deploys and restores", read_at=started, took_ms=took,
                         rows=rows,
                         checked=(f"list {lst}: no deploy or restore recorded"
                                  if got.get("state") == "absent" else
                                  f"list {lst}: the latest receipt of {len(latest)} device(s), "
                                  f"{len(latest) - len(rows) - pending_named} clean"
                                  + (f", {pending_named} commit PENDING (a batch still "
                                     "running, or an interrupted operation named under "
                                     "Operations that did not finish)" if pending_named
                                     else "")))


def _pending_is_named(lst: str, host: str, r: dict) -> bool:
    """Whether a pending receipt is accounted for elsewhere: its device is held now (its
    batch is still running) or an interrupted operation on it started before the row."""
    from modules.nsot import device_ops

    if device_ops.holder(lst, host):
        return True
    at = _ts(r.get("at")) or 0
    return any(i.get("device") == host and (i.get("started") or 0) <= at + 1
               for i in device_ops.interrupted(lst))


# ---------------------------------------------------------------------------
# Source: the last baseline decision (a baseline that was not earned)
# ---------------------------------------------------------------------------

def baseline_source(log_fn=None) -> dict:
    """The NEWEST `Baseline:` decision recorded in the list's golden history
    (`save_golden()` writes it into the commit it judged). A row when that
    decision was a denial, with its reasons; a later earned baseline
    supersedes it. One `git log`, never a read per device (section 0a).
    Commits before 2026-09-28 carry no decision, and the source says so
    rather than reading their silence as either answer."""
    import os

    from modules.config import get_current_list_name, get_list_data_dir

    started = time.time()
    try:
        lst = get_current_list_name()
        if log_fn is None:
            from modules.nsot.repo import git
            repo = os.path.join(get_list_data_dir(lst), "config_repo")
            rc, out, err = git(repo, "log", "-1", "-E", "--grep=^Baseline: ",
                               "--format=%H%x1f%ct%x1f%B")
            if rc != 0:
                raise RuntimeError(f"git log failed: {err.strip() or rc}")
        else:
            out = log_fn()
    except Exception as exc:                       # noqa: BLE001
        return source_result("baseline", "Baseline", read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"it raised {type(exc).__name__}: {exc}")
    took = int((time.time() - started) * 1000)
    if not out.strip():
        # The host's state on 2026-09-28: no decision recorded yet, and no
        # baseline usable. The usability row must not wait for a decision.
        usability = _baseline_usability_row(lst)
        return source_result("baseline", "Baseline", read_at=started, took_ms=took,
                             rows=usability["rows"],
                             checked=f"list {lst}: no baseline decision recorded yet "
                                     "(decisions are recorded from 2026-09-28); "
                                     + usability["checked"])
    sha, ct, body = out.split("\x1f", 2)
    decision = next((ln.split(":", 1)[1].strip() for ln in body.splitlines()
                     if ln.startswith("Baseline: ")), "")
    source_line = next((ln.split(":", 1)[1].strip() for ln in body.splitlines()
                        if ln.startswith("Source: ")), "")
    at = float(ct)
    rows = []
    reasons = decision.split(":", 1)[1].strip() if ":" in decision else ""
    # ONE row when the last decision was a denial AND no stored baseline is
    # usable: both say "there is no restore point", and the denial names the
    # blocker, which the usability row's remedy must name too (the operator,
    # 2026-09-28: "take a current one with Save All" was followed and could
    # not succeed while r2 departed from its intent).
    blocker = ({"reasons": reasons or "the decision recorded no reason",
                "commit": sha[:10], "at": _iso(at)}
               if decision.startswith("denied") else None)
    usability = _baseline_usability_row(lst, blocker=blocker)
    if decision.startswith("denied") and not usability["rows"]:
        rows.append(row(
            source="baseline", kind="denied", key=f"{lst}:last", level="warning",
            what=f"The network's last baseline was not earned ({source_line or 'a save'})",
            # The decision's OWN commit and time: a Save All that changed
            # nothing since decided without a commit to carry it, so this can
            # be older than the newest save, and the row says whose it is.
            cause=(reasons or "the decision recorded no reason")
                  + f" (decided by commit {sha[:10]} at {_iso(at)}; a save since that made "
                    "no decision, a one-device capture or a Save All that changed nothing, "
                    "leaves it standing)",
            action={"label": "Resolve each departure the reasons name, one of two ways "
                             "that mean opposite things: change the DEVICE (a line intent "
                             "has is deployed; a line only the device has is removed by hand, "
                             "since the tool never removes one) if intent is right, or Edit "
                             "INTENT if the device is right. Then Save All"},
            since=at, operands={"list": lst, "commit": sha[:10], "source": source_line}))
    rows += usability["rows"]
    return source_result("baseline", "Baseline", read_at=started, took_ms=took, rows=rows,
                         value_at=at,
                         checked=f"list {lst}: the last baseline decision, {sha[:10]}: "
                                 f"{decision.split(':', 1)[0] or 'unreadable'}; "
                                 + usability["checked"])


def _baseline_usability_row(lst: str, cached=None, blocker: dict = None) -> dict:
    """No stored baseline can be re-applied (the operator, 2026-09-28): every
    one predates a credential rotation (the restore's guard refuses each,
    C75) or is withdrawn. The Baselines panel said it once per row and never
    once. Read from the `baseline-usability` reader (the per-row check costs
    8 to 9 s on the host); a reader that has not answered is job health's row,
    so this says only what it read."""
    from modules import reader_job

    got = reader_job.read_cached("baseline-usability") if cached is None else cached
    good = ((got.get("doc") or {}).get("last_good") or {})
    value = ((good.get("value") or {}).get("lists") or {}).get(lst)
    if got.get("state") != "ok" or value is None:
        return {"rows": [], "checked": "whether a baseline can be re-applied: not judged yet"}
    if value.get("error"):
        return {"rows": [], "checked": f"whether a baseline can be re-applied: {value['error']}"}
    if value.get("usable"):
        return {"rows": [], "checked": f"{value['usable']} can be re-applied"}
    if not value.get("count"):
        return {"rows": [], "checked": "no baseline is stored yet"}
    newest = next((b for b in value["baselines"] if not b["withdrawn"]), None)
    withdrawn = [b["tag"] for b in value["baselines"] if b["withdrawn"]]
    cause = (f"all {value['count']} stored baseline(s) predate a credential rotation or are "
             "withdrawn, so the restore's credential guard (C75) refuses part of any re-apply."
             + (f" The newest, {newest['tag']}, would change the credential on "
                f"{', '.join(newest['stale'])}." if newest else "")
             + (f" Withdrawn: {', '.join(withdrawn)}." if withdrawn else "")
             + " A baseline's usefulness decays with every rotation."
             + (f" A new one cannot be earned right now: the last Save All was denied "
                f"({blocker['reasons']}; commit {blocker['commit']} at {blocker['at']})."
                if blocker else ""))
    action = ({"label": "Resolve each departure the denial names, one of two ways that mean "
                        "opposite things: change the DEVICE if intent is right (a line only the "
                        "device has is removed by hand: the tool never removes one), or Edit "
                        "INTENT if the device is right. Then Save All. Save All alone will be "
                        "refused again while it departs"}
              if blocker else
              {"label": "Take a current baseline: Save All captures every device, and earns "
                        "a baseline if each is at its committed intent; if not, it records "
                        "the denial and names the device and its lines"})
    return {"rows": [row(
        source="baseline", kind="unusable", key=f"{lst}:unusable", level="warning",
        what=("No stored baseline can be re-applied, and a new one cannot be earned yet"
              if blocker else "No stored baseline can be re-applied"),
        cause=cause,
        action=action,
        operands={"list": lst, "baselines": str(value["count"]),
                  "newest": newest["tag"] if newest else "none"},
        since=_ts(good.get("value_at")))],
        "checked": "no baseline can be re-applied"}


# ---------------------------------------------------------------------------
# Source: a line authorised again and again (C140 (1))
# ---------------------------------------------------------------------------

#: How many authorisations of ONE line on ONE device make a pattern. Twice
#: can be a retry after a failed push; a third time is a routine, and an
#: exception that is routine is what 8.8 wants seen ("ok" typed thirty
#: times is the finding, not a defeat of the control).
REPEAT_THRESHOLD = 3


def authorisation_source(counts=None) -> dict:
    """The same dangerous or secret line authorised on the same device at
    least `REPEAT_THRESHOLD` times, from ONE read of the receipts through the
    counting the preview's aggregate uses. It makes behaviour visible; it
    blocks nothing."""
    from modules.config import get_current_list_name
    from modules.nsot import receipts

    started = time.time()
    try:
        lst = get_current_list_name()
        got = (counts or (lambda: receipts.authorisations_by_device(lst)))()
    except Exception as exc:                       # noqa: BLE001
        got = {"state": "unreadable", "error": f"it raised {type(exc).__name__}: {exc}"}
    took = int((time.time() - started) * 1000)
    if got.get("state") == "unreadable":
        return source_result("authorisations", "Repeated authorisations", read_at=started,
                             took_ms=took,
                             error=f"the deploy receipts could not be read ({got.get('error')})")
    rows, n_lines = [], 0
    for device, lines in sorted((got.get("devices") or {}).items()):
        for line, e in sorted(lines.items()):
            n_lines += 1
            if e.get("count", 0) < REPEAT_THRESHOLD:
                continue
            rows.append(row(
                source="authorisations", kind="repeated", key=f"{lst}:{device}:{line}", level="warning",
                what=f"{line.strip()!r} has been authorised {e['count']} times on {device}",
                cause=(f"last by {e.get('last_actor') or 'an unrecorded actor'} at "
                       f"{e.get('last_at') or 'an unrecorded time'}, stated reason: "
                       f"{e.get('last_reason')}. An exception authorised again and again "
                       "is a routine, not an exception"),
                action={"label": "Read the stated reasons on the device's Changes tab: a line "
                                 "authorised routinely belongs in intent, or its cause does"},
                devices=[device], since=_ts(e.get("first_at")),
                event=f"{e['count']} authorisations, the last at {e.get('last_at') or 'an unrecorded time'}",
                operands={"list": lst, "count": e["count"], "threshold": REPEAT_THRESHOLD,
                          "last_at": e.get("last_at")}))
    return source_result("authorisations", "Repeated authorisations", read_at=started,
                         took_ms=took, rows=rows,
                         checked=(f"list {lst}: no deploy or restore recorded"
                                  if got.get("state") == "absent" else
                                  f"list {lst}: {n_lines} authorised line(s) across "
                                  f"{len(got.get('devices') or {})} device(s), a row from "
                                  f"{REPEAT_THRESHOLD} authorisations"))


#: Every source, in the order a person reads them. Section 1a's other
#: sources (freshness, Grafana alerts) join HERE through `source_result`,
#: both through the reader-job pattern.
# ---------------------------------------------------------------------------
# Source: Grafana's alerts, from the grafana-alerts READER's cache (7.2; the
# reader-job pattern's second instance, and 8.6's constraints on 7.2)
# ---------------------------------------------------------------------------

GRAFANA_READER = "grafana-alerts"

#: Instances whose ONSETS fall within this of the previous one form one
#: incident (8.6: grouping is on the onset, never on startsAt, because
#: per-device windows fire one Loki outage up to 536 s apart). 360 s is a
#: heartbeat onset's own uncertainty: the silence began somewhere in the
#: device's last heartbeat period (300 s), and the rule notices it on its
#: next evaluation (60 s). Two onsets closer than that cannot be told apart.
INCIDENT_GAP_SECONDS = 360

_KIND_WORDS = {"condition": "is alerting", "no_data": "reads no data",
               "error": "cannot evaluate", "unknown_state": "is in a state this page does not know"}


def _onset(inst: dict):
    """(epoch or None, basis). A windowed rule fires one window after the
    silence began, so its onset is the alert's start minus the window."""
    starts, active = _ts(inst.get("starts_at")), _ts(inst.get("active_at"))
    window = inst.get("window_seconds")
    if window and (starts or active):
        return (starts or active) - window, f"the alert's start minus the rule's {window} s window"
    if active:
        return active, "when the condition first held"
    if starts:
        return starts - (inst.get("for_seconds") or 0), "the alert's start minus the rule's pending time"
    return None, "not recorded"


def _incidents(instances: list) -> list:
    """Groups of instances, each group one incident, by onset; an instance
    with no onset is an incident of its own (never merged on a guess)."""
    timed = sorted((i for i in instances if i["onset"] is not None), key=lambda i: i["onset"])
    groups, current = [], []
    for inst in timed:
        if current and inst["onset"] - current[-1]["onset"] > INCIDENT_GAP_SECONDS:
            groups.append(current)
            current = []
        current.append(inst)
    if current:
        groups.append(current)
    return groups + [[i] for i in instances if i["onset"] is None]


def _inventory():
    """(hostnames, address -> hostname), or (None, reason) when unreadable."""
    try:
        from modules.device import load_saved_devices
        devices = load_saved_devices()
    except Exception as exc:                       # noqa: BLE001
        return None, f"the inventory could not be read ({type(exc).__name__})"
    return ({d.get("hostname") for d in devices if d.get("hostname")},
            {d.get("ip"): d.get("hostname") for d in devices if d.get("ip")}), ""


def _member(inst: dict, inv) -> dict:
    """One instance as an incident member, naming where its device came from."""
    names, by_ip = inv if inv else (None, None)
    source = inst.get("device_from")
    device, note = inst.get("device"), ""
    if source == "address":
        addr = inst.get("address")
        device = (by_ip or {}).get(addr)
        note = (f"from the polled address {addr}" if device else
                f"the polled address {addr} matches no device's address in the inventory")
    elif source in ("label", "line"):
        note = ("from the rule's device label" if source == "label" else
                "from the syslog line's origin-id")
        if names is not None and device not in names:
            note += ", and it is NOT in the inventory (a rule left behind by a device that left)"
    else:
        note = "the rule names no device"
    if inv is None:
        note += " (the inventory could not be read, so the name is unchecked)"
    return {"rule": inst.get("rule"), "kind": inst.get("kind"), "device": device,
            "device_from": source, "device_note": note, "state": inst.get("state"),
            "fingerprint": inst.get("fingerprint"), "starts_at": inst.get("starts_at"),
            "onset": _iso(inst["onset"]), "onset_basis": inst["onset_basis"],
            "silenced_by": inst.get("silenced_by") or [],
            "silences": inst.get("silences") or []}


def silence_words(silences: list) -> str:
    """"silenced in Grafana by X until T ("comment")", one clause per
    silence. An unresolved one is named by its id and said to be unresolved:
    who and until when are never guessed."""
    parts = []
    for s in silences or []:
        if s.get("unresolved"):
            parts.append(f"silenced in Grafana by silence {s.get('id')}, whose author and end "
                         "Grafana's silence list did not return")
            continue
        text = f"silenced in Grafana by {s.get('created_by') or 'an unnamed account'}"
        text += f" until {s.get('ends_at') or 'an unrecorded time'}"
        if s.get("comment"):
            text += f" (\"{s['comment']}\")"
        parts.append(text)
    return "; ".join(parts)


def grafana_source(cached=None) -> dict:
    """Grafana's alert state, read from the reader's cache, NEVER from
    Grafana (rule 1 of modules/reader_job.py). The reader's own liveness is
    job health's row (`reader:grafana-alerts`), judged at request time."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached(GRAFANA_READER) if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("grafana", "Grafana alerts", read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    from modules.alert_bands import series_key

    v = good.get("value") or {}
    inv, inv_why = _inventory()
    rows = []
    rules_by_uid = {r.get("uid"): r for r in v.get("rules") or []}

    def add(key, what, cause, action, level, **kw):
        rows.append(row(source="grafana", kind=key.split(":", 1)[0], key=key, what=what,
                        cause=cause, action=action,
                        level=level, **kw))

    # Grafana answering and not evaluating reads exactly like a healthy
    # fleet (8.6: the Proxmox listing's 200 with 0 items).
    for g in v.get("stalled_groups") or []:
        add(f"stalled:{g.get('group')}", f"Grafana has stopped evaluating {g.get('group')}",
            f"its last evaluation was {g.get('last_evaluation') or 'never'}, more than three "
            f"of its {g.get('interval_seconds')} s intervals before the read; every rule in it "
            "reads as quiet whether or not its condition holds",
            {"label": "Check Grafana's alert scheduler: its log, then a restart"}, "danger")

    alerting = [dict(i) for i in v.get("instances") or [] if i.get("kind") != "pending"]
    for inst in alerting:
        inst["onset"], inst["onset_basis"] = _onset(inst)
    heartbeat_rules = {r.get("uid") for r in v.get("rules") or []
                       if (r.get("labels") or {}).get("nmas") == "heartbeat"}
    for group in _incidents(alerting):
        members = [_member(i, inv) for i in group]
        devices = sorted({m["device"] for m in members if m["device"]})
        first = group[0]
        heartbeats = {i.get("rule_uid") for i in group} & heartbeat_rules
        whole_pipeline = bool(heartbeat_rules) and heartbeats == heartbeat_rules
        if whole_pipeline:
            what = "Every device's syslog heartbeat stopped at once"
            cause = ("all " + str(len(heartbeat_rules)) + " heartbeat rules are alerting with "
                     "onsets together, so no heartbeat is arriving from any device: the "
                     "subject is the path they share (rsyslog, Alloy, Loki or the route to "
                     "them), not each device")
            action = {"label": "Check the syslog pipeline first: rsyslog, Alloy and Loki on the "
                               "monitoring host"}
        elif len(members) == 1:
            m = members[0]
            what = (f"{m['rule']} {_KIND_WORDS.get(m['kind'], m['kind'])}"
                    + (f" on {m['device']}" if m["device"] else ""))
            cause = f"{m['state']}; the device is {m['device_note']}"
            action = ({"label": "Check the device's syslog path: the heartbeat cannot say which "
                                "of the device, its logging block, rsyslog, Alloy or Loki stopped"}
                      if first.get("rule_uid") in heartbeat_rules else
                      {"label": f"Read the rule \"{m['rule']}\" in Grafana: this page records that "
                                "it fired and where its device came from, not why",
                       "known": False})
        else:
            what = f"{len(members)} alerts began together"
            cause = ("; ".join(f"{m['rule']}" + (f" on {m['device']}" if m["device"] else "")
                               + f" ({m['kind']})" for m in members)
                     + f". Grouped because their onsets fall within {INCIDENT_GAP_SECONDS} s "
                       "of each other; whether they share a cause is not decided here")
            action = {"label": "Read the members together: one cause may explain them, "
                               "or none", "known": False}
        # A silence set in Grafana hides nothing here (the operator,
        # 2026-09-30): the row keeps its level and says who silenced it and
        # until when, so a silence is a visible decision, never a quiet one.
        silenced = [m for m in members if m["silences"]]
        if silenced:
            what += (" (silenced in Grafana)" if len(silenced) == len(members) else
                     f" ({len(silenced)} of {len(members)} silenced in Grafana)")
            cause += ". " + "; ".join(
                (f"{m['rule']}" + (f" on {m['device']}" if m["device"] else "") + ": "
                 if len(members) > 1 else "") + silence_words(m["silences"])
                for m in silenced)
        level = "danger" if any(m["kind"] == "condition" for m in members) else "unknown"
        operands = {"members": members, "grouped_within_seconds": INCIDENT_GAP_SECONDS,
                    "onset_basis": first["onset_basis"]}
        # ONE series of a rule whose query can be banded (C433): keyed on the SERIES, never
        # its onset, so a chronic alert that re-fires is one row, and a person may
        # acknowledge it within its measured band.
        vexpr = ((rules_by_uid.get(first.get("rule_uid")) or {}).get("value_expr") or ""
                 if len(members) == 1 and not whole_pipeline else "")
        if vexpr and first.get("kind") == "condition":
            series = series_key(first.get("rule_uid"), first.get("labels"))
            action = {"label": f"Read the rule \"{members[0]['rule']}\" in Grafana; if it is "
                               "chronic and its cause known, acknowledge it within its "
                               "measured band", "known": False}
            add(f"series:{series}", what, cause, action, level, devices=devices,
                since=first["onset"], event=series,
                operands={**operands, "value_expr": vexpr, "labels": first.get("labels") or {},
                          "band_reading": (v.get("bands") or {}).get(series)})
            continue
        add(f"incident:{first.get('rule_uid') or first.get('rule')}:{_iso(first['onset']) or 'untimed'}",
            what, cause, action, level, devices=devices, since=first["onset"],
            operands=operands)

    # A rule that cannot see its data, or cannot evaluate, with no alerting
    # instance saying so (C166, C168: rules sat in no-data for days).
    covered = {i.get("rule_uid") for i in alerting}
    for r in v.get("rules") or []:
        health = r.get("health")
        if health in ("nodata", "error") and r.get("uid") not in covered:
            add(f"rule:{r.get('uid')}",
                f"{r.get('title')} {'reads no data' if health == 'nodata' else 'cannot evaluate'}",
                (f"its query returns nothing, so whether its condition holds is unknown "
                 f"(its no-data state is {r.get('no_data_state') or 'unrecorded'})"
                 if health == "nodata" else
                 f"its last evaluation failed: {r.get('last_error') or 'no error recorded'}"),
                {"label": f"Read the rule \"{r.get('title')}\"'s query in Grafana", "known": False},
                "warning" if health == "nodata" else "unknown")

    # The floor (8.6): every device should have a heartbeat rule the reader
    # SEES. Fewer is a permission or provisioning gap, and a monitor's
    # permissions can hide what it monitors behind a 200.
    if inv is not None:
        seen = {(r.get("labels") or {}).get("device") for r in v.get("rules") or []
                if (r.get("labels") or {}).get("nmas") == "heartbeat"}
        missing = sorted(inv[0] - seen)
        if missing:
            add("heartbeat-floor", f"{len(missing)} device(s) have no heartbeat rule Grafana shows",
                "no heartbeat rule the reader can see names " + ", ".join(missing)
                + ": the rule is missing, or the reader's account cannot see it",
                {"label": "Regenerate the heartbeat rules (NSOT_PLAN P.1 step 5), then check "
                          "the reader's Grafana role can read them"}, "warning", devices=missing)

    c = v.get("counts") or {}
    return source_result(
        "grafana", "Grafana alerts", read_at=started, took_ms=took, rows=rows,
        value_at=_ts(good.get("value_at")), stale_after_seconds=doc.get("stale_after_seconds"),
        reader=GRAFANA_READER, detail="read from " + ", ".join(doc.get("endpoints") or []),
        checked=(f"{c.get('rules', 0)} rule(s); "
                 f"{c.get('condition', 0)} alerting, {c.get('no_data', 0)} no data, "
                 f"{c.get('error', 0)} error, {c.get('pending', 0)} pending, "
                 f"{c.get('normal_no_data', 0)} reading no data as healthy by decision"
                 + (f"; {inv_why}" if inv is None else "")))


# ---------------------------------------------------------------------------
# Source: Oxidized freshness, from the freshness READER's cache (7.2): a
# device whose Oxidized copy is not the approved state would come back on it
# at the next redeploy.
# ---------------------------------------------------------------------------

def freshness_source(cached=None) -> dict:
    """UNAPPROVED is a row (a change nobody approved is what a redeploy
    would bake in); INCONCLUSIVE is a row (the comparison cannot say); a
    poll race and an authorised divergence are counted, never rows: the
    first self-corrects at the next poll, the second is a recorded
    decision."""
    from modules import reader_job
    from modules.config import get_current_list_name

    started = time.time()
    got = reader_job.read_cached("freshness") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("freshness", "Freshness", read_at=started, took_ms=took,
                             error=f"not compared yet: {why}")
    lst = get_current_list_name()
    report = ((good.get("value") or {}).get("lists") or {}).get(lst)
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    if report is None:
        return source_result("freshness", "Freshness", read_at=started, took_ms=took,
                             error=f"the stored comparison holds no answer for list {lst}")
    rows = []
    if not report.get("ok"):
        rows.append(row(source="freshness", kind="not-compared", key=f"{lst}:not-compared",
                        level="unknown",
                        what=f"Freshness could not be compared for {lst}",
                        cause=(report.get("error") or report.get("defect") or "no reason recorded")
                              + ". This is not the same as nothing having diverged",
                        action={"label": "Check Oxidized answers at the URL in Settings > "
                                         "Integrations; the comparison runs again every 5 "
                                         "minutes", "known": False}))
        return source_result("freshness", "Freshness", read_at=started, took_ms=took,
                             rows=rows, value_at=value_at, stale_after_seconds=promise,
                             checked=f"list {lst}: not compared")
    from modules.redact import redact_text
    for d in report.get("devices") or []:
        verdict = d.get("verdict")
        if verdict not in ("unapproved", "inconclusive"):
            continue
        extra = [redact_text(l) for l in (d.get("only_right") or [])[:3]]
        rows.append(row(
            source="freshness", kind=verdict, key=f"{lst}:{d.get('device')}",
            what=(f"{d.get('device')}: Oxidized holds a change nobody approved"
                  if verdict == "unapproved" else
                  f"{d.get('device')}: whether Oxidized's copy is approved cannot be told"),
            devices=[d.get("device")], since=_ts(d.get("oxidized_at")),
            cause=redact_text(d.get("reason") or "no reason recorded")
                  + (f"; in Oxidized and not the golden: {extra}" if extra else ""),
            operands={"golden_at": d.get("golden_at"), "oxidized_at": d.get("oxidized_at"),
                      "fingerprint": (d.get("fingerprint") or "")[:16]},
            action=({"label": "Capture the device's golden if the change is wanted, or put "
                              "it back; a redeploy before then boots it"}
                    if verdict == "unapproved" else
                    {"label": "Decide whether Oxidized's copy is wanted: capture the device's "
                              "golden if so, or put the device back", "known": False}),
            level="warning" if verdict == "unapproved" else "unknown"))
    c = report.get("counts") or {}
    return source_result(
        "freshness", "Freshness", read_at=started, took_ms=took, rows=rows,
        value_at=value_at, stale_after_seconds=promise, reader="freshness",
        checked=(f"list {lst}: {report.get('checked', 0)} of {report.get('population', 0)} "
                 f"compared; {c.get('match', 0)} approved, {c.get('poll_race', 0)} poll race, "
                 f"{c.get('authorised', 0)} authorised"))


# ---------------------------------------------------------------------------
# Source: integration health, from the integration-health READER (7.2): the
# same stored value the status bar draws, so the two cannot disagree.
# ---------------------------------------------------------------------------

#: Where each integration's credential is renewed (P.21): the service's own page.
RENEW_AT = {
    "netbox": "NetBox: Admin > API tokens", "grafana": "Grafana: Administration > Service "
    "accounts", "proxmox": "Proxmox: Datacenter > Permissions > API Tokens",
    "prometheus": "the proxy in front of Prometheus", "loki": "the proxy in front of Loki",
    "oxidized": "Oxidized's web authentication", "kea": "the Kea control agent's credentials",
    "topology_service": "the topology service's own token", "nsot_git": "the git host's tokens",
    "s3": "the S3 provider's access keys",
}
#: An expiry a person declares where the service does not let the tool read it (P.21).
DECLARED_EXPIRY = {"grafana": "grafana_token_expires", "proxmox": "proxmox_token_expires"}


def _setting(key: str) -> str:
    from modules.settings_schema import get_setting
    return str(get_setting(key, "") or "").strip()


def integrations_source(cached=None) -> dict:
    """A configured integration that does not answer is a row; one left
    unconfigured is a state, counted (job health names the guard it gates)."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached("integrations") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("integrations", "Integrations", read_at=started, took_ms=took,
                             error=f"not probed yet: {why}")
    v = good.get("value") or {}
    rows = []
    for i in v.get("integrations") or []:
        if i.get("state") == "refused":
            # P.21: the service answered and refused the credential. Danger at once, naming
            # where it is renewed, where it goes, and a declared expiry if one was given.
            name = i.get("name", "?")
            declared = _setting(DECLARED_EXPIRY.get(name, "")) if DECLARED_EXPIRY.get(name) else ""
            rows.append(row(
                source="integrations", kind="refused", key=name, level="danger",
                what=f"{i.get('label')} refuses the tool's credential",
                cause=(f"its probe was refused: {i.get('message') or 'no reason recorded'}"
                       + (f"; the expiry declared for it is {declared}" if declared else "")),
                operands={"probe_ms": i.get("took_ms")},
                action={"label": f"Renew it at {RENEW_AT.get(name, i.get('label'))} and put the "
                                 f"new value in Settings > Integrations > {i.get('label')} "
                                 "(a blank field keeps the old one)"}))
            continue
        if i.get("state") != "down":
            continue
        rows.append(row(source="integrations", kind="down", key=i.get("name", "?"), level="danger",
                        what=f"{i.get('label')} is not answering",
                        cause=f"its health probe failed: {i.get('message') or 'no reason recorded'}",
                        operands={"probe_ms": i.get("took_ms")},
                        action={"label": f"Check {i.get('label')} at the URL set in Settings > "
                                         "Integrations; its Test button probes it now"}))
    c = v.get("counts") or {}
    # Named, never only counted: "2 not configured" hid that one of the two
    # was the NSoT repository committing all evening (C171).
    unset = [i.get("label") for i in v.get("integrations") or []
             if i.get("state") == "not_configured"]
    return source_result(
        "integrations", "Integrations", read_at=started, took_ms=took, rows=rows,
        value_at=_ts(good.get("value_at")), stale_after_seconds=doc.get("stale_after_seconds"),
        reader="integrations",
        checked=(f"{len(v.get('integrations') or [])} integration(s): {c.get('up', 0)} up, "
                 f"{c.get('down', 0)} down, {c.get('refused', 0)} refusing the credential, "
                 f"{c.get('not_configured', 0)} not configured"
                 + (f" ({', '.join(unset)})" if unset else "")))


# ---------------------------------------------------------------------------
# Source: the running commit's CI verdict, from the ci-verdict READER (7.2):
# nmas-deploy's own gate, never a second implementation of it.
# ---------------------------------------------------------------------------

_CI_ROWS = {"failed": ("its CI run failed", "danger"),
            "cancelled": ("its CI run was cancelled, so no verdict exists", "warning"),
            "pending": ("its CI run is still going", "warning"),
            "could_not_ask": ("whether it passed CI could not be asked", "unknown")}


def ci_source(cached=None) -> dict:
    """A running commit CI did not pass is a row; a verified one is not."""
    from modules import reader_job
    from routes import health

    started = time.time()
    got = reader_job.read_cached("ci-verdict") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("ci", "Running commit's CI", read_at=started, took_ms=took,
                             error=f"not judged yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    commit = str(v.get("commit") or "")
    if commit != str(health._COMMIT or ""):
        return source_result("ci", "Running commit's CI", read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise,
                             checked=f"the stored verdict is for {commit[:10]}, not the running "
                                     f"{str(health._COMMIT)[:10]}: not judged yet")
    rows = []
    if v.get("state") in _CI_ROWS:
        words, level = _CI_ROWS[v["state"]]
        rows.append(row(source="ci", kind="verdict", key=commit[:10], level=level,
                        what=f"The running commit {commit[:10]}: {words}",
                        cause=v.get("sentence") or "no sentence recorded",
                        action=({"label": "Update to a release CI passed: the Update page "
                                          "waits for CI when it is still checking",
                                 "open": "app_update"}
                                if v["state"] in ("failed", "cancelled") else
                                {"label": "Find why CI has no verdict: nmas-deploy's sentence "
                                          "above names the run and what it found",
                                 "known": False})))
    return source_result("ci", "Running commit's CI", read_at=started, took_ms=took, rows=rows,
                         value_at=value_at, stale_after_seconds=promise, reader="ci-verdict",
                         checked=f"{commit[:10]}: {v.get('state')}")


# ---------------------------------------------------------------------------
# Source: reachability, from the reachability READER (C92, 7.2): a device not
# answering over consecutive probes, never one miss.
# ---------------------------------------------------------------------------

def reachability_source(cached=None) -> dict:
    """ONE row listing every device not answering, each with its misses and
    since when: C92 measured genuine outages six to eight devices at once (the
    path from the NMAS, not each device), and nine rows would bury that. The
    claim names the probe (on the host, a TCP connection to port 22)."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached("reachability") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("reachability", "Reachability", read_at=started, took_ms=took,
                             error=f"not probed yet: {why}")
    v = good.get("value") or {}
    down = sorted((d for d in (v.get("devices") or {}).values() if not d.get("answering")),
                  key=lambda d: d.get("since") or "")
    rows = []
    if down:
        names = [d.get("hostname") or d.get("address") for d in down]
        rows.append(row(
            source="reachability", kind="not-answering", key="not-answering", level="danger",
            what=(f"{names[0]} is not answering" if len(down) == 1
                  else f"{len(down)} devices are not answering"),
            devices=names, since=_ts(down[0].get("since")),
            cause="; ".join(f"{d.get('hostname') or d.get('address')} ({d.get('address')}): "
                            f"{d.get('consecutive_misses')} consecutive misses, the threshold is "
                            f"{d.get('threshold')}; {d.get('claim')}" for d in down)
                  + (". Several at once is more often the path from the NMAS than each device"
                     if len(down) > 1 else ""),
            operands={"probe": "ICMP, then TCP 22"},
            action={"label": "Check the path from the NMAS first when several stop together; "
                             "one alone, its own management interface",
                    "known": False}))
    c = v.get("counts") or {}
    return source_result(
        "reachability", "Reachability", read_at=started, took_ms=took, rows=rows,
        value_at=_ts(good.get("value_at")), stale_after_seconds=doc.get("stale_after_seconds"),
        reader="reachability",
        checked=(f"{c.get('answering', 0)} answering, {c.get('not_answering', 0)} not answering"
                 + (f", {c.get('missed_last_probe', 0)} missed only the last probe"
                    if c.get("missed_last_probe") else "")))


def credential_health_source(cached=None) -> dict:
    """P.21: a credential whose exposed expiry is within 30 days (warning), 7 days or past
    (danger), one older than 180 days (warning, naming Rotate), or one whose expiry cannot be
    read: each a row naming where it is renewed and where the new value goes. One expiring
    beyond a year, or with no record of its age, is listed (on Credentials, at 7.6), no row.
    Metadata only: the reader never holds a value."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached("credential-health") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("credential-health", "Credential expiry and age", read_at=started,
                             took_ms=took, error=f"not read yet: {why}")
    v = good.get("value") or {}
    rows = []
    for c in v.get("credentials") or []:
        state = c.get("state")
        if state in ("ok", "listed"):
            continue
        where = f"Renew it at {c.get('renew_at')}; put the new value in {c.get('put_at')}"
        if c.get("kind") == "age" and state == "warning":
            rows.append(row(source="credential-health", kind="age", key=c.get("id", "?"),
                            level="warning", what=f"{c.get('label')} is {c.get('days')} days old",
                            cause=(f"last set {c.get('set_at')}, past the {MAX_CREDENTIAL_AGE} days "
                                   "a credential is kept"),
                            action={"label": f"{c.get('renew_at')}"}))
        elif state == "unknown":
            # UNKNOWN, never a Warning (C381): a Warning claims a danger the reader has seen.
            rows.append(row(source="credential-health", kind="unread", key=c.get("id", "?"),
                            level="unknown", what=f"{c.get('label')}'s expiry cannot be read",
                            cause=c.get("why") or "no reason recorded",
                            action={"label": f"Read its expiry at {c.get('renew_at')}; the "
                                             "reader asks again every hour"}))
        elif state in ("expired", "danger", "warning"):
            words = ("has EXPIRED" if state == "expired" else
                     f"expires in {c.get('days')} days")
            rows.append(row(source="credential-health", kind="expiry", key=c.get("id", "?"),
                            level="danger" if state in ("expired", "danger") else "warning",
                            what=f"{c.get('label')} {words}",
                            cause=f"it expires {c.get('expires_at')}"
                                  + (f" ({c.get('why')})" if c.get("why") else ""),
                            action={"label": where}))
    counts = {}
    for c in v.get("credentials") or []:
        counts[c.get("state")] = counts.get(c.get("state"), 0) + 1
    return source_result(
        "credential-health", "Credential expiry and age", read_at=started, took_ms=took,
        rows=rows, value_at=_ts(good.get("value_at")),
        stale_after_seconds=doc.get("stale_after_seconds"), reader="credential-health",
        checked=(f"{len(v.get('credentials') or [])} credential(s): "
                 + ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
                 + (f"; not read: {'; '.join(v.get('errors'))}" if v.get("errors") else "")))


#: P.21's signed age (days): a credential with no expiry older than this is a row.
MAX_CREDENTIAL_AGE = 180


def netbox_secrets_source(cached=None) -> dict:
    """A credential NetBox holds in a device's stored config context is a live
    exposure in a shared system (the operator, 2026-09-29): one row per device,
    naming the slot kinds and never a value, with the action that can clear it.
    Where NMAS recorded writing the context it may mask it; where it did not,
    it is somebody's data, and the row says to remove it in NetBox."""
    from modules import reader_job

    started = time.time()
    got = reader_job.read_cached("netbox-secrets") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("netbox-secrets", "NetBox stored credentials", read_at=started,
                             took_ms=took, error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    if not v.get("configured"):
        return source_result("netbox-secrets", "NetBox stored credentials", read_at=started,
                             took_ms=took, value_at=value_at, stale_after_seconds=promise,
                             reader="netbox-secrets",
                             checked=f"no NetBox configured ({v.get('why') or 'no reason'}): "
                                     "nothing to hold one")
    rows = []
    for d in v.get("devices") or []:
        name = d.get("name") or f"device {d.get('id')}"
        held = ", ".join(d.get("slots") or []) or "a credential"
        comm = d.get("communities") or 0
        cause = (f"NetBox device {d.get('id')} ({name}) holds {held} unmasked in its stored "
                 f"config context" + (f", and {comm} structured SNMP community value(s)"
                                      if comm else "")
                 + ": readable by everyone who can read NetBox")
        if d.get("record_unreadable"):
            cause += (f". Whether NMAS wrote it cannot be told: the modification record is "
                      f"unreadable ({d['record_unreadable']})")
            action = {"label": "Repair data/netbox_modified.json from its preserved "
                               ".corrupt- copy: until it reads, NMAS will not mask NetBox's "
                               "context", "known": False}
        elif d.get("wrote"):
            cause += f". NMAS wrote this context ({d['wrote']}), so it may mask it"
            action = {"label": "Mask it with the import's own masking, read back",
                      "command": f"nmas-netbox-mask-context --device {name} --apply"}
        else:
            cause += ". NMAS has no record of writing it, so it is somebody's data and NMAS "
            cause += "will not change it"
            action = {"label": f"Remove the credential lines from {name}'s config context in "
                               "NetBox by hand"}
        rows.append(row(source="netbox-secrets", kind="held", key=f"netbox:{d.get('id')}", level="danger",
                        what=f"NetBox holds a credential for {name}", devices=[name],
                        cause=cause, operands={"netbox_id": d.get("id")}, action=action))
    return source_result(
        "netbox-secrets", "NetBox stored credentials", read_at=started, took_ms=took,
        rows=rows, value_at=value_at, stale_after_seconds=promise, reader="netbox-secrets",
        checked=f"{v.get('scanned', 0)} NetBox device(s) scanned, "
                f"{len(v.get('devices') or [])} holding a credential")


# ---------------------------------------------------------------------------
# Source: history committed and not on its remote (C223)
# ---------------------------------------------------------------------------

_PUSHED_LEVEL = {"behind": "info", "behind_unfetched": "info", "not_on_remote": "warning"}

#: How long the host may run behind the pushed tip before that is itself
#: something wrong: 2.5x the slowest push-to-deploy wait measured on the host
#: (115 deploys to 2026-10-01: median 0.1 h, 90th percentile 0.2 h, slowest 8.0 h).
BEHIND_TOO_LONG_S = 20 * 3600


def pushed_level(v: dict, now: float = None) -> tuple:
    """``(level, why)`` for the app-pushed row. An update being available is
    INFORMATION, and makes no row (``"info"``: said on About and the Update
    page); it is a WARNING only when something is actually wrong: CI
    failed for the release, the tip could not be fetched, the host has run
    behind for longer than BEHIND_TOO_LONG_S, or the running commit is not on
    the remote at all. *why* names the reason ("" for information)."""
    now = time.time() if now is None else now
    state = v.get("state")
    if state == "not_on_remote":
        return "warning", "the running commit is not on the remote"
    ci = v.get("ci") or {}
    if ci.get("tip") == v.get("tip") and ci.get("state") in ("failed", "cancelled"):
        return "warning", f"CI {ci['state']} for {str(v.get('tip') or '')[:7]}"
    if state == "behind_unfetched" and v.get("fetch_error"):
        return "warning", f"the new release could not be fetched: {v['fetch_error']}"
    since = _ts(v.get("behind_since"))
    if since is not None and now - since > BEHIND_TOO_LONG_S:
        return "warning", (f"the host has run behind for {int((now - since) // 3600)} h, longer "
                           f"than the {BEHIND_TOO_LONG_S // 3600} h a release here has ever "
                           "waited (2.5x the slowest of 115 measured)")
    return "info", ""


#: An update that was asked for and did not happen (update_op's outcomes).
_UPDATE_NOT_DONE = ("refused", "rolled_back", "rollback_failed", "failed")


def release_level(v: dict, last: dict = None, now: float = None) -> tuple:
    """``(level, why)`` for the release: pushed_level, raised when the last
    update asked FROM this commit did not happen (a failed rollback is danger).
    The ONE decision the Needs attention row and the top bar's "Update
    available" both read, so the quiet indicator turns into the row exactly
    when the row appears, and never shows beside it."""
    level, why = pushed_level(v, now)
    if last is None:
        from modules import update_op
        last = update_op.outcome().get("value") or {}
    if last.get("outcome") in _UPDATE_NOT_DONE and last.get("from") == v.get("running"):
        level = "danger" if last["outcome"] == "rollback_failed" else "warning"
    return level, why


def update_available(v: dict, last: dict = None, now: float = None):
    """The top bar's quiet "Update available" (the operator, 2026-10-02: an
    update is news, not a problem, and should be noticeable): a dict when
    origin/main is ahead, CI PASSED for its tip, and nothing makes it a Needs
    attention row; None otherwise. CI still checking, or a tip never fetched,
    shows nothing: an update not yet installable is not news to act on."""
    if v.get("state") != "behind":
        return None
    ci = v.get("ci") or {}
    if not (ci.get("tip") == v.get("tip") and ci.get("state") == "verified"):
        return None
    if release_level(v, last, now)[0] != "info":
        return None
    n = v.get("behind")
    behind = (f"{n} commit{'' if n == 1 else 's'} behind" if n is not None
              else "behind by a number of commits not yet counted")
    since = str(v.get("behind_since") or "")
    since = f"{since[:16].replace('T', ' ')} UTC" if len(since) >= 16 else since
    return {"tip": str(v.get("tip") or "")[:7], "running": str(v.get("running") or "")[:7],
            "behind": n, "since": since,
            "title": (f"{behind} origin/{v.get('branch') or 'main'} "
                      f"({str(v.get('running') or '')[:7]} → {str(v.get('tip') or '')[:7]}), "
                      f"CI passed; ahead since {since or 'unknown'}")}


def update_words(v: dict) -> str:
    """The row's headline, in a person's words: "Update available — 1a587a6 →
    2986b5c (2 new commits)"."""
    run, tip = str(v.get("running") or "")[:7], str(v.get("tip") or "")[:7]
    n = v.get("behind")
    count = (f"{n} new commit{'' if n == 1 else 's'}" if n is not None else
             "how many new commits is not known until it is fetched")
    return f"Update available — {run} → {tip} ({count})"


def ci_refused(v: dict) -> bool:
    """CI's final verdict for the pushed tip is not a pass, so the Update button refuses it
    (C418): the row is about the commit, never an update offer."""
    ci = v.get("ci") or {}
    return (v.get("state") != "not_on_remote" and ci.get("tip") == v.get("tip")
            and ci.get("state") in ("failed", "cancelled"))


def ci_refused_words(v: dict) -> tuple:
    """``(headline, action)`` for a tip CI refused: "CI failed on the newest commit, 74a7013 —
    run #373: promtool for the PromQL tests, in test (a), test (b)", and the developer's
    fix-forward, linking the run when the verdict names it."""
    from modules.readers import ci_verdict as CV

    ci, tip = v.get("ci") or {}, str(v.get("tip") or "")[:7]
    run = CV.run_of(ci.get("sentence"))
    named = f" — run #{run['number']}" if run["number"] else ""
    if ci.get("state") == "cancelled":
        what = f"CI was cancelled for the newest commit, {tip}{named}: no verdict"
        label = (f"The developer re-runs CI for {tip} or fixes forward with a newer commit; "
                 "nothing to update until CI passes one")
    else:
        where = CV.failed_words(ci)
        what = f"CI failed on the newest commit, {tip}{named}" + (f": {where}" if where else "")
        label = "The developer fixes forward; nothing to update until CI passes a newer commit"
    action = {"label": label}
    if run["url"]:
        action.update(run_url=run["url"], run=run["number"] or "")
    return what, action


def pushed_source(cached=None) -> dict:
    """The host running something other than what is pushed (the operator,
    2026-09-30: the commit left the top bar, so when it is wrong it is here),
    from the `app-pushed` reader: this process's commit against origin/main,
    asked by `git ls-remote`. Quiet at the tip; a row when behind or off it."""
    from modules import reader_job
    from modules.readers import app_pushed
    from routes import health

    started = time.time()
    got = reader_job.read_cached("app-pushed") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    label = "Running commit against origin/main"
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("pushed", label, read_at=started, took_ms=took,
                             error=f"not compared yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    running = str(v.get("running") or "")
    if running != str(health._COMMIT or ""):
        return source_result("pushed", label, read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise,
                             checked=f"the stored comparison is for {running[:10]}, not the running "
                                     f"{str(health._COMMIT)[:10]}: not compared yet")
    rows = []
    if v.get("state") in _PUSHED_LEVEL:
        from modules import update_op

        sentence = app_pushed.words(v)
        # THE UPDATE BUTTON (the operator, 2026-09-30): the app knows it is out
        # of date, so its action is the Update operation, never a terminal.
        tip = str(v.get("tip") or "")
        action = ({"label": f"Preview the commits and CI's verdict for {tip[:7]}, then "
                            "confirm", "open": "app_update"}
                  if v["state"] != "not_on_remote" else
                  {"label": "The host should run only pushed commits: find where this one came "
                            "from before updating over it", "known": False})
        # How and when it was checked: the evidence, drawn behind a disclosure
        # for information (the operator, 2026-10-01), in the row for a warning.
        cause = (f"origin/{v.get('branch') or 'main'} was asked with git ls-remote at "
                 f"{good.get('value_at') or '?'}; the host moves only when a person updates it")
        last = (update_op.outcome().get("value") or {})
        # An update tried and not done is wrong (the host stays behind what a
        # person asked for); a failed rollback is worse. release_level decides
        # it, the one decision the top bar's indicator also reads.
        level, why = release_level(v, last)
        if why:
            cause = f"{why[0].upper()}{why[1:]}. {cause}"
        if last.get("outcome") in _UPDATE_NOT_DONE and last.get("from") == running:
            # One event, one row: the update that did not happen is this row's
            # cause, not a second row beside it.
            cause += (f". The last update, to {str(last.get('to') or '?')[:10]} by "
                      f"{last.get('requested_by') or '?'}, "
                      f"{update_op.OUTCOME_WORDS.get(last['outcome'], last['outcome'])} "
                      f"({last.get('ended_at') or last.get('at') or '?'}): {last.get('reason')}")
        wait = update_op.deferred()
        if wait.get("target"):
            # Update when CI passes: the row says the update is coming, and
            # its action is still the page, where the wait can be stopped.
            cause += (f". An update to {str(wait["target"])[:10]} is waiting for CI, asked by "
                      f"{wait.get("requested_by") or "?"} at {wait.get("requested_at") or "?"}: "
                      "it starts when CI passes")
            action = dict(action, label=f"Waiting for CI to pass {str(wait["target"])[:10]}: "
                                        "open the Update page to follow it or stop waiting")
        what = (update_words(v) if v["state"] in ("behind", "behind_unfetched")
                else sentence[0].upper() + sentence[1:])
        if ci_refused(v):
            # A commit CI refused is not an update on offer (C418: the row said "Update
            # available ... preview then confirm" for a commit the button refuses). The
            # failure leads; the action is the developer's.
            ci = v.get("ci") or {}
            what, action = ci_refused_words(v)
            cause += (f". CI's verdict, asked at {ci.get('asked_at') or '?'}: "
                      f"{ci.get('sentence') or 'no sentence recorded'}"
                      + (f". Where it failed could not be read: {ci['failed_at_error']}"
                         if ci.get("failed_at_error") else ""))
            rows.append(row(source="pushed", kind="ci_failed", key=tip[:10], level=level,
                            what=what, cause=cause, action=action,
                            since=_ts(ci.get("asked_at")) or _ts(v.get("behind_since"))))
        # A release being available is not wrong (the operator, 2026-10-02):
        # it is said on Help > About and the Update page, and here only once
        # something is (pushed_level names what).
        elif level != "info":
            rows.append(row(source="pushed", kind="release", key=running[:10], level=level,
                            what=what,
                            since=_ts(v.get("behind_since")),
                            cause=cause, action=action))
    return source_result("pushed", label, read_at=started, took_ms=took, rows=rows,
                         value_at=value_at, stale_after_seconds=promise, reader="app-pushed",
                         checked=app_pushed.words(v))


def remote_source(cached=None) -> dict:
    """A list whose commits are not on its remote, from the `remote-publication`
    reader: HEAD against the remote's own branch, asked by `git ls-remote`,
    never the push hook's record (C223: abandon's commit never reached the
    hook, and the hook's record said nothing). Its sentence is
    `remote_publication.describe()`, the one the Git tab and the Remote card
    draw. An unreadable remote record (C172) is named on the row."""
    from modules import reader_job
    from modules.readers import remote_publication as P

    started = time.time()
    got = reader_job.read_cached(P.READER.name) if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("remote", "Publication to the remote", read_at=started,
                             took_ms=took, error=f"not read yet: {why}")
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    lists = (good.get("value") or {}).get("lists") or {}
    rows, fine = [], []
    for name, pub in sorted(lists.items()):
        said = P.describe(pub, now=started)
        if said["state"] in ("in_sync", "no_remote") and said["level"] == "success":
            fine.append(name)
            continue
        if said["state"] == "no_remote":
            continue
        remote = pub.get("remote") or "its remote"
        if said["state"] == "held":
            what = (f"{pub.get('ahead', 0)} commit(s) on {name} held back from {remote}: "
                    "auto-push needs a person")
            since = _ts((pub.get("held") or {}).get("since")) or pub.get("oldest_at")
            action = {"label": (
                "Push now, on the Remote card (the Devices tab, below the device list): "
                "publication was acknowledged since the hold"
                if pub.get("acknowledged_since_hold") else
                "On the Remote card (the Devices tab, below the device list), read what "
                "would be published, acknowledge it, then Push now. Until then nothing is "
                "pushed, by design: auto-push never widens what is published")}
        elif said["state"] == "tags_not_pushed":
            what = f"{len(pub.get('tags_not_pushed') or [])} tag(s) on {name} not on {remote}"
            since = None
            action = {"label": "Push now, on the Remote card (the Devices tab, below the "
                               "device list): it sends every tag with the branch"}
        elif said["state"] == "ahead":
            what = f"{pub.get('ahead', 0)} commit(s) on {name} not pushed to {remote}"
            since = pub.get("oldest_at")
            action = {"label": "Push now, on the Remote card: the Devices tab, below the "
                               "device list, in the golden repository section. The next "
                               "commit's push also sends every commit before it. If it does "
                               "not go, the card names the failure"}
        elif said["state"] == "in_sync":
            # In step today, and the record the push hook reads cannot be read,
            # so the NEXT commit will not be pushed (C172).
            what = f"{name}'s remote record cannot be read, so its next commit will not be pushed"
            since = None
            action = {"label": "Repair or re-adopt the list's remote from the Remote card (the "
                               "Devices tab, below the device list); the record is "
                               "data/lists/<list>/remote.json on the host"}
        elif said["state"] in ("remote_ahead", "diverged"):
            what = f"{name}'s history and {remote} do not match"
            since = None
            action = {"label": "Resolve it by hand on the host: NMAS never force-pushes, so "
                               "compare the two histories and decide which is the record"}
        else:
            what = f"Whether {name}'s history is on {remote} is not known"
            since = None
            action = {"label": "Verify the remote from History's header: it names what "
                               "could not be asked. A remote that cannot be asked also "
                               "cannot be pushed to"}
        rows.append(row(
            source="remote", kind="publication", key=f"{name}:{said['state']}", level=(
                "danger" if said["level"] == "danger" else "warning"),
            what=what, cause=f"{name}: {said['clause']}. {said['detail']}".strip(),
            action=action, since=since,
            operands={"list": name, "head": str(pub.get("head", ""))[:7],
                      "remote_head": str(pub.get("remote_head", ""))[:7],
                      "not_pushed": str(pub.get("ahead", "")), "record": pub.get("record", "")}))
    return source_result(
        "remote", "Publication to the remote", read_at=started, took_ms=took, rows=rows,
        value_at=value_at, stale_after_seconds=promise, reader=P.READER.name,
        checked=(f"{len(lists)} list repository(ies) compared with their remote's branch; "
                 f"published: {', '.join(fine) or 'none'}"))


def host_steps_source(owed=None) -> dict:
    """AFTER host steps a release that runs now still owes (modules/host_steps.py:
    the operator, 2026-09-30, a step that can only be done once the release has
    landed must never block the update, and must not be forgotten after it).
    The tool's check answers where there is one; otherwise a person says it is
    done on the Update page."""
    from modules import host_steps
    from routes import health

    started = time.time()
    label = "Host steps a running release owes"
    if not health._COMMIT:
        return source_result("host_steps", label, read_at=started, took_ms=0,
                             error="the running commit is unknown, so its history cannot be read")
    got = host_steps.owed(health._COMMIT) if owed is None else owed
    took = int((time.time() - started) * 1000)
    if not got["ok"]:
        return source_result("host_steps", label, read_at=started, took_ms=took,
                             error=got["error"])
    rows = [row(source="host_steps", kind="owed", key=s["id"], level="warning",
                what=(f"A host step for {', '.join(x[:10] for x in s.get('shas') or [s['sha']])}"
                      f" is still to do: {s['step']}"),
                cause=(f"checked: {s['check_detail']}" if s["check_state"] != "not_checkable"
                       else "it is done after the update, and nothing can check it"),
                operands={"check": s.get("check") or "", "state": s["check_state"]},
                action={"label": ("Open the Update page and say it is done"
                                  if s["check_state"] == "not_checkable"
                                  else "Do it on the host; this row goes when the check reads done"),
                        "open": "app_update"})
            for s in got["steps"]]
    return source_result("host_steps", label, read_at=started, took_ms=took, rows=rows,
                         checked=f"the last {host_steps.HISTORY} commits of {health._COMMIT[:10]}")


def restart_source(cached=None) -> dict:
    """An UNPLANNED restart (the operator, 2026-10-02: five passed silently): one row per
    restart for `restarts.ATTENTION_DAYS` days, DANGER when the device saved a crash file,
    naming the device's own reason. A planned one (the tool's reload, or a window it was
    told) is in the device's History and is no row."""
    from modules import reader_job
    from modules import restarts as R

    started = time.time()
    got = reader_job.read_cached("restarts") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    label = "Device restarts"
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("restarts", label, read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    if not v.get("configured"):
        return source_result("restarts", label, read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise, reader="restarts",
                             checked="no Prometheus configured: a restart cannot be seen")
    # Judged again against the planned windows recorded NOW (a file read), so a correction
    # recorded a moment ago clears its rows without waiting for the reader's next run.
    try:
        unplanned = [r for r in R.judged(v.get("recent_unplanned") or [], R.planned_rows())
                     if not r.get("planned")]
    except RuntimeError as exc:
        return source_result("restarts", label, read_at=started, took_ms=took, error=str(exc))
    rows = []
    for r in unplanned:
        crash = r.get("crash_file", "")
        action = (f"Read the crash file ({crash}) and check the host at that time" if crash else
                  "Read the device's log around then and check the host at that time")
        rows.append(row(source="restarts", kind="unplanned",
                        key=f"{r.get('list', '')}|{r['device']}|{r['at']}",
                        level="danger" if crash else "warning", what=R.words(r),
                        devices=[r["device"]], since=_ts(r.get("at")), event=r["at"],
                        clears_at=(_ts(r.get("at")) + R.ATTENTION_DAYS * 86400
                                   if _ts(r.get("at")) else None),
                        cause=(f"Its uptime counter reset (found {r.get('seen_at', '?')} in "
                               "Prometheus's sysUpTime), and no reload by the tool and no planned "
                               "window covers it."),
                        operands={"list": r.get("list"), "reason": r.get("reason"),
                                  "crash_file": crash},
                        action={"label": action,
                                "href": f"/v2/device/{r['device']}?tab=history"}))
    cut = " (the read window was cut at 48 h)" if v.get("cut") else ""
    return source_result(
        "restarts", label, read_at=started, took_ms=took, rows=rows, value_at=value_at,
        stale_after_seconds=promise, reader="restarts",
        checked=(f"sysUpTime of {v.get('devices', 0)} device(s) over the last "
                 f"{int(v.get('window', 0)) // 60} min{cut}"
                 + (f"; not managed, not judged: {', '.join(v['unmanaged'])}"
                    if v.get("unmanaged") else "")))


def interrupted_source(found=None) -> dict:
    """An operation whose PROCESS ENDED while it held its devices (CONCURRENCY_AUDIT R5): a
    restart, an update or a crash in the middle of a deploy, restore, capture or rotation.
    The kernel released every hold, so nothing else says it happened, and what reached each
    device, and whether a receipt or a golden was recorded, is unknown. ONE row per
    interrupted operation (the process, the operation and who started it), naming its
    devices and the last step it recorded, until a person acknowledges it."""
    from modules.nsot import device_ops

    started = time.time()
    label = "Operations that did not finish"
    try:
        recs = device_ops.interrupted_anywhere() if found is None else found
    except OSError as exc:
        return source_result("operations", label, read_at=started,
                             took_ms=int((time.time() - started) * 1000),
                             error=f"the device holds could not be read: {exc}")
    groups = {}
    for r in recs:
        key = (str(r.get("list") or ""), r.get("pid"), r.get("operation") or "?",
               r.get("actor") or "")
        groups.setdefault(key, []).append(r)
    rows, pending_by_list = [], {}
    for (lst, pid, op, actor), members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        devices = sorted({m.get("device") or "?" for m in members})
        first = min((m.get("started") or 0) for m in members)
        last = max(members, key=lambda m: ((m.get("progress") or {}).get("at") or 0))
        step = (last.get("progress") or {}).get("step") or "started"
        step_at = (last.get("progress") or {}).get("at") or first
        words = device_ops.STEP_WORDS.get(step, step)
        if lst not in pending_by_list:
            pending_by_list[lst] = _pending_receipts_of(lst)
        # The devices this operation finished before it ended: each has its receipt row,
        # written as it finished, whose batch commit never came (CONCURRENCY_AUDIT R5).
        finished = sorted({p.get("device") for p in pending_by_list[lst]
                           if p.get("device") in devices
                           and (_ts(p.get("at")) or 0) + 1 >= first})
        known = (f" {', '.join(finished)} finished before it ended: each has a receipt, "
                 "commit PENDING, naming the program sent and the checks that ran; their "
                 "golden was not recorded." if finished else "")
        unknown = [d for d in devices if d not in finished]
        rows.append(row(
            source="operations", kind="interrupted",
            key=f"{lst}|{pid}|{op}|{first}", event=str(first),
            level="warning", devices=devices, since=first or None,
            what=(f"A {op} on {', '.join(devices)} did not finish: the process ended while it "
                  "held the device" + ("s" if len(devices) > 1 else "")),
            cause=(f"Started by {actor or 'someone'} at {_iso(first)} (process {pid}, list "
                   f"{lst}); its last recorded step was {words} at {_iso(step_at)}. A process "
                   "that ends (a restart, an update, a crash) releases every hold, so nothing "
                   "else says this happened." + known
                   + (f" What reached {', '.join(unknown)}, and whether a golden was "
                      "recorded, is not known." if unknown else "")),
            operands={"list": lst, "operation": op, "pid": pid, "step": step,
                      **({"pending_receipts": finished} if finished else {})},
            action={"label": (f"Read {devices[0]} as it is now and compare it with its golden "
                              "before changing it" + (", and each other device" if
                                                      len(devices) > 1 else "")
                              + "; then acknowledge what you found"),
                    "href": f"/v2/device/{devices[0]}?tab=history"}))
    return source_result(
        "operations", label, read_at=started, took_ms=int((time.time() - started) * 1000),
        rows=rows,
        checked=(f"every device lock in every list: {len(recs)} hold(s) left by a process "
                 "that ended" if recs else
                 "every device lock in every list: none left by a process that ended"))


def _pending_receipts_of(list_name: str) -> list:
    """The receipt rows of *list_name* still waiting for their batch's commit; none when the
    record cannot be read (the deploy source says that it cannot)."""
    from modules.nsot import receipts

    got = receipts.read(list_name, limit=10 ** 6)
    return [r for r in got.get("rows") or [] if receipts.is_pending(r)]


def adjacency_source(cached=None) -> dict:
    """C38: a routing adjacency committed intent implies and the device does
    not report up, held for two reads (a deploy's settle window passes
    first). ONE row per link, naming the pair and each side's report; a peer
    outside management is seen from one side and says so. A protocol nothing
    scrapes is one unknown row naming the devices, never "all up"."""
    from modules import reader_job
    from modules.readers.adjacencies import PERSIST_READS

    started = time.time()
    got = reader_job.read_cached("adjacencies") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    label = "Routing adjacencies"
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("adjacencies", label, read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    if not v.get("configured"):
        return source_result("adjacencies", label, read_at=started, took_ms=took,
                             value_at=value_at, stale_after_seconds=promise, reader="adjacencies",
                             checked="no Prometheus configured: what the devices report about "
                                     "their neighbours cannot be read")
    rows, settling = [], 0
    for key, a in sorted((v.get("adjacencies") or {}).items()):
        if int(a.get("reads") or 0) < PERSIST_READS:
            settling += 1
            continue
        devs = a.get("devices") or []
        sides = "; ".join(
            f"{s['device']}{(' ' + s['via']) if s.get('via') else ''} reports "
            + ("it " + s["words"] if s["state"] == "down" else "no such neighbour")
            for s in a.get("sides") or [])
        if a.get("managed") and len(devs) == 2:
            what = f"{a['protocol']} between {devs[0]} and {devs[1]} is not up"
        else:
            addr = next((s.get("address") for s in a.get("sides") or [] if s.get("address")), "")
            what = (f"{a['protocol']} from {devs[0] if devs else '?'} to {addr or 'a peer'} "
                    "(outside management) is not up")
        cause = (f"Committed intent implies this adjacency ({a.get('network') or a['protocol']}); "
                 f"{sides}, as Prometheus last scraped them. Held for {a.get('reads')} reads a "
                 "minute apart, so it is not a deploy's settle window")
        first = devs[0] if devs else ""
        rows.append(row(source="adjacencies", kind="link", key=key, level="danger", what=what, devices=devs,
                        since=_ts(a.get("since")), cause=cause,
                        operands={"list": a.get("list"), "sides": a.get("sides")},
                        action={"label": f"Open {first}'s Neighbours and check the link and both "
                                         "ends' routing configuration",
                                "href": f"/v2/device/{first}?tab=neighbours"}))
    un = v.get("unmeasured") or []
    if un:
        names = ", ".join(sorted({f"{u['device']} ({u['protocol']})" for u in un}))
        rows.append(row(source="adjacencies", kind="unmeasured", key="unmeasured", level="unknown",
                        what=f"{len(un)} protocol(s) whose adjacencies cannot be judged",
                        devices=sorted({u["device"] for u in un}),
                        cause=f"Intent implies adjacencies Prometheus does not measure: {names}. "
                              + (un[0].get("why") or ""),
                        action={"label": "Check the Prometheus targets row: the routing jobs' "
                                         "files are generated from the goldens"}))
    for e in v.get("errors") or []:
        rows.append(row(source="adjacencies", kind="error", key=f"error:{e[:40]}",
                        level="unknown",
                        what="A list's committed intent could not be read for its adjacencies",
                        cause=e, action={"label": "Fix the intent file the reason names: "
                                                  "it must parse for its links to be judged",
                                         "known": False}))
    return source_result(
        "adjacencies", label, read_at=started, took_ms=took, rows=rows, value_at=value_at,
        stale_after_seconds=promise, reader="adjacencies",
        checked=(f"{v.get('checked', 0)} adjacency report(s) over {v.get('devices', 0)} device(s)"
                 + (f"; {settling} not up for less than {PERSIST_READS} reads, not raised yet"
                    if settling else "")))


def _moved_row(d: dict, name: str, base: str) -> dict:
    """A device whose current golden has moved since the baseline its file is
    built from: a redeploy returns it there (plan item 4's cross-check, from
    the record)."""
    m = d.get("since_baseline") or {}
    lines = [f"`{l.strip()}`" for l in (m.get("only_golden") or [])[:3]] + \
            [f"`{l.strip()}`" for l in (m.get("only_file") or [])[:3]]
    return row(
        source="lab-startup", kind="moved", key=f"moved:{d.get('list')}:{name}", level="warning",
        what=f"A redeploy returns {name} to {base}",
        devices=[name], operands={"list": d.get("list"), "file": d.get("file") or ""},
        cause=(f"{name}'s current golden differs from its golden at {base} "
               f"(+{m.get('only_golden_count', 0)} / -{m.get('only_file_count', 0)} lines"
               + (": " + "; ".join(lines) if lines else "") + "), and the lab startup file "
               f"is built from {base}"),
        action={"label": "Save All earns a new baseline that carries what it runs now"})


def lab_startup_source(cached=None) -> dict:
    """A device whose lab startup file is not what its committed golden would
    produce (the operator, 2026-10-01): a redeploy boots the file, so the
    device would come back other than as recorded. One row per device, the
    differing lines masked and a credential named by its slot; a file no
    device owns is information, since a redeploy still boots it."""
    from modules import reader_job

    label = "Lab startup files"
    started = time.time()
    got = reader_job.read_cached("lab-startup") if cached is None else cached
    doc = got.get("doc") or {}
    good = doc.get("last_good") or {}
    took = int((time.time() - started) * 1000)
    if got["state"] != "ok" or not good:
        why = (got.get("why") if got["state"] != "ok" else
               "the reader has never stored a value; its last attempt: "
               + ((doc.get("last_attempt") or {}).get("error") or "none recorded"))
        return source_result("lab-startup", label, read_at=started, took_ms=took,
                             error=f"not read yet: {why}")
    v = good.get("value") or {}
    value_at, promise = _ts(good.get("value_at")), doc.get("stale_after_seconds")
    common = dict(read_at=started, took_ms=took, value_at=value_at,
                  stale_after_seconds=promise, reader="lab-startup")
    if not v.get("configured"):
        return source_result("lab-startup", label, **common,
                             checked="no lab host configured (clab_host): no lab file to compare")
    rows = []
    for d in v.get("devices") or []:
        name, where = d["device"], d.get("file") or "its lab's configs directory"
        if d.get("state") == "differs":
            parts = []
            if d.get("only_golden_count"):
                parts.append(f"{d['only_golden_count']} line(s) the build has and the file "
                             "lacks: " + "; ".join(f"`{l.strip()}`" for l in d["only_golden"][:5]))
            if d.get("only_file_count"):
                parts.append(f"{d['only_file_count']} line(s) the file has and the build "
                             "lacks: " + "; ".join(f"`{l.strip()}`" for l in d["only_file"][:5]))
            if d.get("credentials"):
                parts.append("a credential differs in value: "
                             + "; ".join(f"`{l.strip()}`" for l in d["credentials"]))
            if d.get("reordered"):
                parts.append("the same lines in another order")
            base = d.get("baseline") or "the newest earned baseline"
            rows.append(row(
                source="lab-startup", kind="differs", key=f"differs:{d.get('list')}:{name}",
                level="danger" if d.get("credentials") else "warning",
                what=(f"{name}'s lab startup file is not what {base} builds"
                      + (": a credential differs" if d.get("credentials") else "")),
                devices=[name], operands={"list": d.get("list"), "file": where},
                cause=(f"A redeploy boots {where}. The clab sync builds it from {base}, every "
                       f"credential from {name}'s current golden, and the file holds something "
                       "else: " + ". ".join(parts)
                       + (". A redeploy would boot a credential the tool no longer holds"
                          if d.get("credentials") else "")),
                action={"label": ("Read the clab sync's job-health row: it has not run since "
                                  "the change, or it refused. A baseline or credential changed "
                                  "in the last 30 minutes is written by its next run")}))
            moved = d.get("since_baseline") or {}
            if moved.get("state") == "differs":
                rows.append(_moved_row(d, name, base))
            continue
        if d.get("state") == "matches" and (d.get("since_baseline") or {}).get("state") == "differs":
            rows.append(_moved_row(d, name, d.get("baseline") or "the newest earned baseline"))
            continue
        if d.get("state") == "not_built":
            rows.append(row(
                source="lab-startup", kind="not_built", key=f"not_built:{d.get('list')}:{name}", level="warning",
                what=f"The clab sync builds no startup file for {name}",
                devices=[name], operands={"list": d.get("list"), "file": where},
                cause=d.get("why") or "the sync's source names no reason",
                action={"label": "Save All earns a baseline that holds it, and the next clab "
                                 "sync builds its file"}))
            continue
        if d.get("state") == "missing":
            rows.append(row(
                source="lab-startup", kind="missing", key=f"missing:{d.get('list')}:{name}", level="warning",
                what=f"{name} has no lab startup file", devices=[name],
                operands={"list": d.get("list"), "file": where},
                cause=(f"{where} does not exist, so a redeploy boots {name} on the image's own "
                       "defaults, without the credential the tool holds"),
                action={"label": "Check the clab sync's run: it writes the file for every "
                                 "device it maps"}))
    unknown = [d for d in v.get("devices") or [] if d.get("state") == "unknown"]
    if unknown:
        rows.append(row(
            source="lab-startup", kind="unknown", key="unknown", level="unknown",
            what=f"{len(unknown)} device(s) whose lab startup file could not be compared",
            devices=sorted({d["device"] for d in unknown}),
            cause="; ".join(sorted({f"{d['device']}: {d.get('why') or '?'}" for d in unknown})),
            action={"label": "Check the lab host answers SSH from the NMAS (its address in "
                             "Settings); the check reads it again every 10 minutes",
                    "known": False}))
    # A file no managed device owns (r5's, after its retirement) is a FACT, not
    # something wrong, and there is nothing to do about it (the operator,
    # 2026-10-02): it is said in this check's own finding, never as a row.
    unowned = "; ".join(unowned_words(u) for u in v.get("unowned") or [])
    counted = v.get("checked", 0)
    return source_result(
        "lab-startup", label, rows=rows, **common,
        checked=(f"{counted} device(s) compared over {v.get('labs', 0)} lab(s), "
                 f"{sum(1 for d in v.get('devices') or [] if d.get('state') == 'matches')} "
                 "holding what the sync builds"
                 + (f". Startup files no managed device owns (expected after a retirement; "
                    f"nothing to do): {unowned}" if unowned else "")))


def unowned_words(u: dict) -> str:
    """A lab startup file no managed device owns, in one clause: whether the
    lab's topology still boots it, from the topology, never guessed."""
    node, by = u.get("node") or u["file"], u.get("declared_by")
    if by:
        return (f"{u['file']}, used by the topology ({', '.join(by)} declares node {node}), "
                "owned by no managed device")
    if by == []:
        return f"{u['file']}, which nothing boots"
    return f"{u['file']} (whether the topology still boots it was not read)"


SOURCES = (job_health_source, drift_source, approvals_source, pending_onboarding_source,
           rollback_source, deploy_source, baseline_source, authorisation_source,
           grafana_source, freshness_source, integrations_source, ci_source,
           reachability_source, netbox_secrets_source, credential_health_source,
           remote_source, pushed_source,
           host_steps_source, adjacency_source, lab_startup_source, restart_source,
           interrupted_source)


#: What can move each source's rows: the data keys (modules/invalidation.VOCABULARY) whose
#: announcement, or a response's invalidation, means it must be read again. The ONE list
#: the page, the sidebar's count and the client's relays are built from (the operator,
#: 2026-10-02: the count was a hand-kept list, short of keys the page heard); a test holds
#: it to SOURCES both ways and every key to a relay.
SOURCE_KEYS = {
    "job_health_source": ("job_health",),
    "drift_source": ("drift",),
    "approvals_source": ("approvals", "drift"),
    "pending_onboarding_source": ("pending", "inventory"),
    "rollback_source": ("rolled_back", "intent"),
    "deploy_source": ("deploy_job", "goldens"),
    "baseline_source": ("baselines", "goldens"),
    "authorisation_source": ("deploy_job", "goldens"),
    "grafana_source": ("alerts",),
    "freshness_source": ("freshness",),
    "integrations_source": ("integration_health",),
    "ci_source": ("ci_verdict",),
    "reachability_source": ("reachability",),
    "netbox_secrets_source": ("netbox",),
    "credential_health_source": ("credential_health",),
    "remote_source": ("remote", "goldens"),
    "pushed_source": ("app_version",),
    "host_steps_source": ("app_version",),
    "adjacency_source": ("adjacencies",),
    "lab_startup_source": ("lab_startup",),
    "restart_source": ("restarts",),
    # A hold left by a process that ended is found at the next read; the page's catch-up on
    # reconnect (the process that ended was this app) is what re-reads it.
    "interrupted_source": ("deploy_job", "device_state"),
}

#: Every key that can move a row, and a person's acknowledgement.
ATTENTION_KEYS = tuple(sorted({k for ks in SOURCE_KEYS.values() for k in ks}
                              | {"acknowledgements"}))

#: The event the page and the count also re-read on: the moment a row clears by TIME.
DUE_EVENT = "attention_due"


def badge_of(rows: list, results: list) -> dict:
    """The sidebar's count, from the SAME rows the page draws, after attaching, folding and
    acknowledgements (the operator, 2026-10-02: the count was computed apart and left out
    rows the page showed): how many, the worst level, when a row next clears by time, and
    when the oldest source's value passes its promise. The page's own count is this one."""
    worst = min((LEVELS.index(r["level"]) for r in rows), default=None)
    due = [_ts(r["clears_at"]) for r in rows if r.get("clears_at")]
    stale = [_ts(res["value_at"]) + res["stale_after_seconds"] for res in results
             if res.get("value_at") and res.get("stale_after_seconds")]
    unreadable = [res["label"] for res in results if res.get("state") != "read"]
    return {"n": len(rows), "level": LEVELS[worst] if worst is not None else "",
            "next_change_at": _iso(min(due)) if due else None,
            "stale_at": _iso(min(stale)) if stale else None,
            "unreadable": len(unreadable)}


def _attach(rows: list) -> list:
    """Fold each row that is ABOUT another row into it (NSOT_PLAN 8.6: two
    rows about one event is the three-reports problem). The target keeps its
    own cause and takes the attached row's action, since a queued item is the
    prepared path to the fix; an attached row whose target is absent stands
    alone."""
    by_id = {r["id"]: r for r in rows}
    kept = []
    for r in rows:
        target = by_id.get(r.get("attach_to") or "")
        if target is None or target is r:
            kept.append(r)
            continue
        target["attached"].append({"source": r["source"], "what": r["what"],
                                   "since": r["since"]})
        if r.get("attach_action", True):
            target["action"] = r["action"]
    return kept


def _fold_one_cause(rows: list) -> list:
    """Rows from two sources about ONE cause, folded by the attach rule (the operator,
    2026-10-02). The updater's installed copy of `nmas-deploy` differing produced two
    warnings, the host step's ("A host step for ... is still to do") and job health's
    ("updater differs from this release's copy"), cleared together by one re-install. While
    an owed host step is checked by the updater's own check, job health's `differs` row
    attaches to it, and the host step's row keeps its action: it is the one that says what
    to do. Any other updater state (writable, cannot run) is its own danger and stays.

    For EVERY root-installed helper, not the updater alone (C419, the operator, 2026-10-04:
    the Oxidized helper's drift was the host step's row and job health's): the registry
    (`host_helpers.folds`) names each helper's check, its job-health row and the states one
    install clears."""
    from modules import host_helpers

    owed = {}
    for r in rows:
        check = (r.get("operands") or {}).get("check") if r["source"] == "host_steps" else None
        if check and check not in owed:
            owed[check] = r
    if not owed:
        return rows
    for check, (unit_id, states) in host_helpers.folds().items():
        step = owed.get(check)
        if step is None:
            continue
        for r in rows:
            if r["id"] == unit_id and (r.get("operands") or {}).get("state") in states:
                r["attach_to"] = step["id"]
                r["attach_action"] = False
    return rows


def _without_acknowledged(rows: list):
    """``(rows, acknowledged, problem)``: the rows a person has not acknowledged, the ones
    they have (each with who, why and when, for the page's evidence), and a source result
    naming the record when it cannot be read. Unreadable hides NOTHING: every row stays,
    and the page says the record could not be read."""
    from modules import acknowledgements as ACK

    if not any(r.get("acknowledge") for r in rows):
        return rows, [], None
    started = time.time()
    got = ACK.read()
    if got["state"] == "unreadable":
        return rows, [], source_result(
            "acknowledgements", "Acknowledgements", read_at=started,
            took_ms=int((time.time() - started) * 1000),
            error=(f"the acknowledgement record could not be read ({got.get('error')}): every "
                   "row is shown, acknowledged or not"))
    kept, gone = [], []
    for r in rows:
        a = ACK.covering(r["id"], r.get("event"), got["rows"]) if r.get("acknowledge") else None
        if a and a.get("band") is not None:
            # WITHIN ITS BAND ONLY (C433): hidden while the reader's reading is inside the
            # band recorded with the acknowledgement; outside it, or unread, the row stays and
            # says why, naming the band and the value.
            reading = (r.get("operands") or {}).get("band_reading") or {}
            if not reading and a.get("value") is not None:
                # Until the reader's first reading: the value measured with the acknowledgement.
                reading = {"value": float(a["value"]),
                           "in_band": float(a["value"]) <= float(a["band"])}
            if reading.get("in_band"):
                gone.append({"id": r["id"], "what": r["what"], "by": a.get("by"),
                             "why": a.get("why"), "at": a.get("at"),
                             "band": f"within its band: {reading.get('value'):.3g} at or under "
                                     f"{float(a['band']):.3g}"})
                continue
            from modules.alert_bands import words
            r = dict(r)
            now = (f"its value is now {reading['value']:.3g}, above it"
                   if reading.get("value") is not None else
                   "its value now could not be read ("
                   + (reading.get("why") or "the reader has not measured it yet") + ")")
            r["cause"] = (f"{r['cause']}. Acknowledged by {a.get('by')} within a band of "
                          f"{words(float(a['band']))}; {now}, so it is shown")
            kept.append(r)
        elif a:
            gone.append({"id": r["id"], "what": r["what"], "by": a.get("by"),
                         "why": a.get("why"), "at": a.get("at")})
        else:
            kept.append(r)
    return kept, gone, None


#: The source each acknowledgeable row comes from, so an acknowledgement checks the row
#: exists NOW (computed again, never taken from the browser).
_ACK_SOURCES = {"restarts": "restart_source", "authorisations": "authorisation_source",
                "operations": "interrupted_source", "grafana": "grafana_source"}


def acknowledge(row_id: str, event: str, why: str, *, by: str, verified: str) -> dict:
    """A person acknowledges ONE event row. Refused unless the row is on the page now, of a
    kind acknowledged here, about this same event, and the reason has the shape of one."""
    from modules import acknowledgements as ACK
    from modules.nsot.authorisation import reason_problem

    source = (row_id or "").split(":", 1)[0]
    fn = _ACK_SOURCES.get(source)
    if not fn:
        return {"ok": False, "error": f"{row_id!r} is not a row a person acknowledges: it "
                                      "clears when its condition resolves (its row says how)"}
    found = next((r for r in globals()[fn]()["rows"] if r["id"] == row_id), None)
    if found is None:
        return {"ok": False, "error": f"{row_id!r} is not on Needs attention now: nothing to "
                                      "acknowledge"}
    if not found.get("acknowledge"):
        return {"ok": False, "error": f"{row_id!r} clears when its condition resolves (its row "
                                      "says how), not by a person's acknowledgement"}
    if str(found.get("event")) != str(event or ""):
        return {"ok": False, "error": (f"the row is now about {found.get('event')!r}, not "
                                       f"{event!r}: a later event is acknowledged on its own")}
    # The authorisation rule's shape check (not empty, three words, eight characters),
    # with no line to compare against: its messages then begin with the empty line's repr.
    if reason_problem({"line": "", "reason": (why or "").strip()}):
        from modules.nsot.authorisation import MIN_CHARS, MIN_WORDS
        return {"ok": False, "error": (
            f"an acknowledgement needs a reason: at least {MIN_WORDS} words and {MIN_CHARS} "
            "characters saying why this needs nothing more (what you found, or why it was "
            "expected); its quality is never judged")}
    if not by:
        return {"ok": False, "error": "an acknowledgement names the person who made it"}
    got = ACK.read()
    if got["state"] == "unreadable":
        return {"ok": False, "error": "the acknowledgement record could not be read, so "
                                      f"nothing was added to it ({got.get('error')})"}
    extra = {}
    if (found["source"], found["kind"]) == ("grafana", "series"):
        # WITHIN A BAND (C433): the series' 7-day p95, measured now, and its value now; the
        # acknowledgement holds only while the value stays at or under the band.
        from modules.alert_bands import band, current

        ops = found.get("operands") or {}
        b, why_not = band(ops.get("value_expr", ""), ops.get("labels") or {})
        if b is None:
            return {"ok": False, "error": f"Not acknowledged: its band could not be measured "
                                          f"({why_not}), and an acknowledgement here holds only "
                                          "within one"}
        now, _why = current(ops.get("value_expr", ""), ops.get("labels") or {})
        extra = {"band": b, "value": now}
    entry = ACK.record(row_id, found["event"], why=why, by=by, verified=verified,
                       kind=f"{found['source']}/{found['kind']}", what=found["what"], **extra)
    return {"ok": True, "acknowledged": entry}


def needs_attention(sources=None) -> dict:
    """The page: every row from every source, worst first, and every source
    with its read time, so an empty page says what it looked at."""
    results = []
    for src in (SOURCES if sources is None else sources):
        try:
            results.append(src())
        except Exception as exc:                   # noqa: BLE001
            # A source whose ADAPTER raised is still a row, never an absence.
            name = getattr(src, "__name__", "source")
            log.error("attention: source %s raised: %s", name, exc)
            results.append(source_result(name, name, read_at=time.time(), took_ms=0,
                                         error=f"its adapter raised {type(exc).__name__}: {exc}"))
    rows = _attach(_fold_one_cause([r for res in results for r in res["rows"]]))
    rows, acknowledged, ack_result = _without_acknowledged(rows)
    if ack_result:
        results.append(ack_result)
    rows.sort(key=lambda r: (LEVELS.index(r["level"]), r["source"], r["id"]))
    unreadable = [res["label"] for res in results if res["state"] != "read"]
    if rows:
        headline = f"{len(rows)} thing(s) need attention"
    else:
        headline = "Nothing needs attention"
    return {"ok": True, "headline": headline, "rows": rows,
            "unreadable": unreadable, "acknowledged": acknowledged,
            "badge": badge_of(rows, results),
            "sources": [{k: res[k] for k in ("source", "label", "state", "read_at",
                                             "value_at", "took_ms", "checked")}
                        | {"count": len(res["rows"])} for res in results]}
