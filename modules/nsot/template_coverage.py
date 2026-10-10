"""modules/nsot/template_coverage.py — how much of each device's golden its template reproduces,
across one network: Templates › Coverage on v2 (the board drawn 2026-10-10 under the Phase 7
mode; CUTOVER's "Template coverage" row, whose JSON route `/templatize/report` no screen called).

For every device the manifest gives a COMMITTED golden: the golden parsed, rendered through the
device's own template (`templates_repo.render_source`), and compared (`roundtrip.validate_device`,
the check seed and Approve run). The answer is a fact about the repository at one commit, so it
is measured as a JOB a person starts, never per request: one render per device. It reads git
and writes nothing; it reaches no device.

The sample lines it keeps are golden lines, so a caller masks them on the way out.
"""

import logging
import time

log = logging.getLogger(__name__)

#: The outcome groups, worst first: what to act on leads.
OUTCOMES = (("unreadable", "could not be checked", "danger"),
            ("partly", "not fully reproduced", "warn"),
            ("reproduced", "reproduced exactly", "ok"))

#: The check's steps, per device and then once, named on the manual's Templates page.
STEPS = (
    ("golden", "Read its committed golden", "the manifest's golden at HEAD, never a file on disk"),
    ("render", "Render it through its template",
     "the golden parsed into intent, rendered through the template the device is bound to"),
    ("compare", "Compare", "line by line: reproduced, missing, rendered but not in the golden"),
    ("keep", "Keep the answer", "masked, dated, with the commit it measured, for the tab"),
)

#: Each device keeps this many of its missing and extra lines (the rest is counted).
SAMPLE = 20

ANNOUNCER = "template-coverage"


def measure(list_name: str, *, now=None) -> dict:
    """The coverage of every device of *list_name* with a committed golden."""
    from modules.nsot import listref
    from modules.nsot import manifest as _m
    from modules.nsot import templates_repo
    from modules.nsot.repo import committed_golden_for, git
    from modules.nsot.roundtrip import rank_unmodeled, validate_device

    repo = listref.resolve(list_name).repo_dir
    _rc, head, _err = git(repo, "rev-parse", "HEAD")
    devices, reports = [], []
    # Serial: one render per device in this one job, CPU-bound and reaching no device
    # (fanout.read_each is for reads across devices).
    for _identity, entry in sorted(_m.load(repo)["devices"].items(),
                                   key=lambda kv: (kv[1].get("name") or "").lower()):
        host = entry.get("name") or ""
        if not entry.get("golden"):
            continue
        platform = entry.get("platform") or ""
        got = committed_golden_for(repo, entry)
        if not got.get("text"):
            devices.append({"host": host, "outcome": "unreadable", "why": (
                got.get("refused") or "the manifest names a golden no commit holds")})
            continue
        try:
            src = templates_repo.render_source(repo, host, platform)
            r = validate_device(got["text"], platform, template_root=src["root"],
                                template_name=src["name"])
        except Exception as exc:                  # noqa: BLE001 (said on its row)
            log.exception("template_coverage: %s could not be checked", host)
            r = {"error": f"{type(exc).__name__}: {exc}"}
        if r.get("error"):
            devices.append({"host": host, "outcome": "unreadable", "why": r["error"]})
            continue
        reports.append(dict(r, hostname=host))
        details = r.get("details") or {}
        missing = [m["line"] for m in details.get("missing", [])]
        extra = [e["line"] for e in details.get("extra", [])]
        devices.append({
            "host": host, "outcome": "reproduced" if r.get("ok") else "partly",
            "fidelity": r.get("round_trip_fidelity"), "coverage": r.get("modeled_coverage"),
            "unmodeled": r.get("unmodeled", 0), "template": src.get("name", ""),
            "missing": missing[:SAMPLE], "missing_more": max(0, len(missing) - SAMPLE),
            "extra": extra[:SAMPLE], "extra_more": max(0, len(extra) - SAMPLE)})
    groups = [{"key": k, "words": w, "level": lvl,
               "devices": [d for d in devices if d["outcome"] == k]} for k, w, lvl in OUTCOMES]
    return {"list": list_name, "commit": (head or "").strip(),
            "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                         time.gmtime(now if now is not None else time.time())),
            "total": len(devices), "groups": [g for g in groups if g["devices"]],
            "counts": {g["key"]: len(g["devices"]) for g in groups},
            "next": rank_unmodeled(reports)}


def _path(list_name: str) -> str:
    """Kept beside the list's inventory, never in its repository: a measurement, not intent.
    Resolved through `listref`, which creates nothing (a read may not make a list)."""
    import os

    from modules.nsot import listref
    return os.path.join(listref.resolve(list_name).data_dir, "template_coverage.json")


def latest(list_name: str):
    """The last measurement kept for *list_name*, masked: None when none was ever kept, or
    ``{"unreadable": why}`` when the file cannot be read (a different state from absent)."""
    import json
    import os

    path = _path(list_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"unreadable": f"{os.path.basename(path)} could not be read: {exc}"}
    return got if isinstance(got, dict) else {"unreadable": "it does not hold a measurement"}


def start(list_name: str, actor: str) -> str:
    """Measure as a job, keep the answer (masked) for the tab to read, and announce
    `templates` when it ends."""
    import json

    from modules import invalidation
    from modules.filestore import write_atomic
    from modules.nsot import capture_job
    from modules.outbound import mask_payload

    def work(_job_id):
        out = mask_payload(dict(measure(list_name), asked_by=actor))
        write_atomic(_path(list_name), json.dumps(out, indent=1, sort_keys=True))
        return out

    return capture_job.start(list_name, f"template coverage of {list_name}", actor, work,
                             kind="template-coverage",
                             announce_keys=invalidation.ANNOUNCERS[ANNOUNCER],
                             announcer=ANNOUNCER)
