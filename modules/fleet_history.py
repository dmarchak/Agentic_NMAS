"""History (NSOT_GUI_BRIEF 3.4; the mockup signed off by the operator, 2026-10-02).

What happened to a network's record: its commits, its baselines and the Oxidized
divergences people authorised, with the remote's state at the top.

**A fixed number of reads, never one per commit** (the scale rule, plan §0a):
the commit list is ONE bounded ``git log`` whose filters (device, person,
workflow, time) are applied by git itself, plus one more for the filter
choices. A row's diff is fetched only when a person opens it, and is masked on
the way out like every config text (C77).

**Every claim says how it was established**: an actor carries how it was
verified (``Actor-Verified:``), a baseline what its commit recorded it earned,
and a commit whose record is known to be wrong carries that exception beside
it (``record_exceptions``), so git is never drawn as ground truth.
"""

import logging
import re

log = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 800
SINCE_CHOICES = (("7", "7 days"), ("30", "30 days"), ("365", "a year"), ("", "all time"))
#: A workflow's words (its ``Source:`` trailer); any other is drawn as given.
WORKFLOW_WORDS = {"pipeline": "deploy", "save_all": "save all", "bulk-intent": "bulk intent",
                  "extraction": "intent", "ip-sla": "IP SLA", "capture": "capture",
                  "restore": "restore", "rotation": "rotation", "onboarding": "onboarding",
                  "profile": "profile", "seed": "seed", "revert": "revert", "adopt": "adopt",
                  "retire": "retire", "approval": "approval", "manual": "manual"}
#: How an ``Actor-Verified:`` value is said beside the actor.
VERIFIED_WORDS = {"access": "", "host-shell": "host login, not verified",
                  "none": "not verified", "": "before verification was recorded"}

_US, _RS = "\x1f", "\x1e"
_FIELDS = ("sha", "short", "at", "subject", "source", "actor", "verified", "baseline",
           "intent_match", "decorations")
_FORMAT = _RS + _US.join((
    "%H", "%h", "%cI", "%s",
    "%(trailers:key=Source,valueonly,separator=%x2C)",
    "%(trailers:key=Actor,valueonly,separator=%x2C)",
    "%(trailers:key=Actor-Verified,valueonly,separator=%x2C)",
    "%(trailers:key=Baseline,valueonly,separator=%x2C)",
    "%(trailers:key=Intent-Match,valueonly,separator=%x2C)",
    "%D"))
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._@+-]{1,128}$")


class HistoryError(ValueError):
    """A filter the history refuses (a value that is not a name)."""


def _ere(value: str) -> str:
    """*value* as a literal inside a git extended regular expression."""
    return re.sub(r"([.\[\]()*+?{}|^$\\])", r"\\\1", value)


def workflow_words(source: str) -> str:
    return WORKFLOW_WORDS.get(source, source.replace("_", " ").replace("-", " ")) if source else ""


def actor_words(actor: str, verified: str) -> dict:
    """``{"who", "how"}``: the actor, and how it was established."""
    return {"who": actor or "nobody recorded", "how": VERIFIED_WORDS.get(verified, verified)}


def baseline_words(decision: str, tags: list) -> dict:
    """``{"state", "words", "tag"}`` for the Baseline column: earned (its tag),
    not taken (a deploy that did not cover the network), denied (and why),
    unrecorded (a tag on a commit that recorded nothing), or none."""
    tag = next((t for t in tags if t.startswith("baseline/")), "")
    d = (decision or "").strip()
    if d == "earned":
        return {"state": "earned", "words": "earned", "tag": tag}
    if d.startswith("denied"):
        why = d.partition(":")[2].strip()
        m = re.match(r"(\d+) device\(s\) not targeted", why)
        if m:
            return {"state": "not_taken", "words": f"not taken: {m.group(1)} not targeted",
                    "tag": tag}
        m = re.search(r"\(([^)]*skipped)\)", why)
        return {"state": "denied", "words": "denied: " + (m.group(1) if m else why)[:80],
                "tag": tag}
    if tag:
        return {"state": "unrecorded", "words": "not recorded", "tag": tag}
    return {"state": "", "words": "", "tag": ""}


def _parse(out: str) -> list:
    from modules.nsot.record_exceptions import exception_for

    rows = []
    for chunk in out.split(_RS):
        if not chunk.strip():
            continue
        first, _nl, rest = chunk.partition("\n")
        parts = first.split(_US)
        if len(parts) < len(_FIELDS):
            continue
        r = dict(zip(_FIELDS, parts))
        tags = [d.strip()[len("tag: "):] for d in r["decorations"].split(",")
                if d.strip().startswith("tag: ")]
        files = [f for f in rest.splitlines() if f.strip()]
        devices = sorted({m.group(2) for f in files
                          for m in [re.match(r"^(golden|host_vars)/([^/]+)\.(cfg|yml)$", f)] if m})
        exc = exception_for(r["sha"])
        rows.append({
            "sha": r["sha"], "short": r["short"], "at": r["at"], "subject": r["subject"],
            "source": r["source"], "workflow": workflow_words(r["source"]),
            **actor_words(r["actor"], r["verified"]),
            "baseline": baseline_words(r["baseline"], tags), "tags": tags,
            "intent_match": r["intent_match"], "files": files, "devices": devices,
            "exception": (f"recorded {exc.get('field', '')}: {exc.get('recorded', '')}, "
                          f"was {exc.get('was', '')} ({exc.get('finding', '')})"
                          if isinstance(exc, dict) else ""),
        })
    return rows


def commits(repo: str, device: str = "", person: str = "", workflow: str = "",
            since_days: str = "7", limit: int = DEFAULT_LIMIT, git=None) -> dict:
    """``{"rows", "cut", "limit", "error"}``, newest first. ONE ``git log``.
    *cut* is true when more commits match than *limit* (the view says so)."""
    from modules.nsot import repo as R

    git = git or R.git
    for name, value in (("device", device), ("person", person), ("workflow", workflow)):
        if value and not _SAFE_NAME.match(value):
            raise HistoryError(f"the {name} filter {value!r} is not a name")
    if since_days and not str(since_days).isdigit():
        raise HistoryError(f"the time filter {since_days!r} is not a number of days")
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    args = ["log", f"--max-count={limit + 1}", f"--format={_FORMAT}", "--name-only",
            "--decorate=short"]
    if since_days:
        args.append(f"--since={int(since_days)} days ago")
    greps = []
    if workflow:
        greps.append(f"--grep=^Source: {_ere(workflow)}$")
    if person:
        greps.append(f"--grep=^Actor: {_ere(person)}$")
    if greps:
        args += ["--extended-regexp", *greps] + (["--all-match"] if len(greps) > 1 else [])
    if device:
        args += ["--", f"golden/{device}.cfg", f"host_vars/{device}.yml"]
    rc, out, err = git(repo, *args)
    if rc != 0:
        return {"rows": [], "cut": False, "limit": limit,
                "error": f"the repository's history could not be read: {(err or '').strip()}"}
    rows = _parse(out or "")
    return {"rows": rows[:limit], "cut": len(rows) > limit, "limit": limit, "error": ""}


def choices(repo: str, since_days: str = "7", git=None) -> dict:
    """The people and workflows seen in the window, for the filters: ONE read."""
    from modules.nsot import repo as R

    git = git or R.git
    args = ["log", "--format=%(trailers:key=Source,valueonly,separator=%x2C)" + _US
            + "%(trailers:key=Actor,valueonly,separator=%x2C)"]
    if since_days and str(since_days).isdigit():
        args.append(f"--since={int(since_days)} days ago")
    rc, out, _err = git(repo, *args)
    people, flows = set(), set()
    for line in (out or "").splitlines() if rc == 0 else []:
        src, _s, actor = line.partition(_US)
        if src.strip():
            flows.add(src.strip())
        if actor.strip():
            people.add(actor.strip())
    return {"people": sorted(people),
            "workflows": sorted(({"value": f, "words": workflow_words(f)} for f in flows),
                                key=lambda w: w["words"])}


def diff(repo: str, sha: str, max_lines: int = 400, git=None) -> dict:
    """One commit's change, MASKED (C77), for the row a person opens:
    ``{"ok", "stat", "text", "cut", "error"}``."""
    from modules.nsot import repo as R
    from modules.redact import redact_text

    git = git or R.git
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha or ""):
        return {"ok": False, "error": f"{sha!r} is not a commit id", "stat": "", "text": "",
                "cut": False}
    rc, out, err = git(repo, "show", "--format=", "--stat", "--patch", sha)
    if rc != 0:
        return {"ok": False, "error": f"the commit could not be read: {(err or '').strip()}",
                "stat": "", "text": "", "cut": False}
    lines = redact_text(out or "").splitlines()
    return {"ok": True, "error": "", "text": "\n".join(lines[:max_lines]),
            "cut": len(lines) > max_lines, "stat": ""}
