"""UPDATE: the app updates itself from the GUI (NSOT_STAGE7_PLAN "The tool
updates itself"; docs/UPDATE.md). The app's half, which holds NO privilege.

- THE PREVIEW is what the `app-pushed` reader stored: the running commit, the
  target (origin/main), the commits between, the target's CI verdict by
  `nmas-deploy`'s own gate, the `Host-Step:` trailers, whether the checkout is
  clean, and whether the root-owned updater is installed as it should be. No
  page load fetches or asks GitHub.
- THE CONFIRM is bound to a hash of what the preview showed; the apply
  recomputes it from the same stored value and refuses a preview that moved.
- THE APPLY writes a REQUEST file and nothing else: target, the commit it
  runs, the verified person, the time, the host steps they said are done. The
  root-owned `nmas-update` (started by `nmas-update.path`) re-checks all of it
  itself, CI included, so the most a request can do is run a commit CI passed.
- THE OUTCOME is the updater's record (/var/lib/nmas-update/outcome.json),
  read on the next page load: updated, refused, rolled back, rollback failed.

A person's operation (gate `confirm`, which requires a person): CI decides
WHAT can run, the person decides WHEN.
"""

import hashlib
import json
import logging
import os
import stat
import time

from modules import config

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUEST_DIR = os.path.join(config.DATA_DIR, "update", "requests")
STAGING_DIR = os.path.join(config.DATA_DIR, "update", "staging")
STATE_DIR = "/var/lib/nmas-update"
AUDIT = os.path.join(config.DATA_DIR, "update_requests.jsonl")

#: What the one-time install puts on the host, each root-owned and not
#: writable by the service user: (name, installed path, the repository file it
#: is a copy of, or None for a rendered unit).
INSTALLED = (
    ("the updater", "/usr/local/sbin/nmas-update", "deploy/update/nmas-update"),
    ("the updater's copy of the CI gate", "/usr/local/lib/nmas-update/nmas-deploy",
     "scripts/nmas-deploy"),
    ("the path unit", "/etc/systemd/system/nmas-update.path", None),
    ("the service unit", "/etc/systemd/system/nmas-update.service", None),
)

#: The updater's own bound (deploy/update/nmas-update UP_BOUND_S), stated for
#: the waiting page: the new version, then a rollback, each within it.
UP_BOUND_S = 120

#: The service's TimeoutStartSec: past it the updater cannot still be running,
#: so a page still waiting says the updater has not reported.
UPDATER_TIMEOUT_S = 15 * 60

#: The stepper, in order: the page's two steps (the request written, the
#: updater started), the UPDATER's own step keys (deploy/update/nmas-update
#: STEPS, which its record names while it runs; a test holds the two equal),
#: and the end state.
STEPS = (("request", "Request written"), ("started", "Updater started"),
         ("checkout", "Checkout checked: no local changes"), ("fetch", "Fetched origin"),
         ("ci", "CI re-checked for the target"), ("move", "Checkout moved to <target>"),
         ("restart", "Restarting the app"), ("wait", "Waiting for the new version"),
         ("running", "Running <target>"))

#: The ONE lock a terminal deploy and the updater both take (C242): whoever
#: holds it moves the checkout; the other refuses by name. In the checkout's
#: data/, so the service user can create it and root opens it read-only.
LOCK = os.path.join(config.DATA_DIR, "update", "lock")

OUTCOME_WORDS = {
    "updated": "updated",
    "refused": "refused: nothing was changed",
    "rolled_back": "rolled back: the new version did not come up, the previous one runs again",
    "rollback_failed": "ROLLBACK FAILED: neither the new version nor the previous one came up",
    "failed": "failed: the updater stopped with an error",
    "running": "running",
}


# ---------------------------------------------------------------------------
# What the updater recorded
# ---------------------------------------------------------------------------

def _read_json(path: str) -> dict:
    """``{"state": absent|unreadable|ok, "value"|"error"}``."""
    if not os.path.exists(path):
        return {"state": "absent"}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"state": "ok", "value": json.load(fh)}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "error": f"{type(exc).__name__}: {exc}"}


def outcome() -> dict:
    """The updater's latest record, as it wrote it; absent before any run."""
    return _read_json(os.path.join(STATE_DIR, "outcome.json"))


def history(limit: int = 10) -> dict:
    path = os.path.join(STATE_DIR, "history.jsonl")
    if not os.path.exists(path):
        return {"state": "absent", "rows": []}
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        return {"state": "ok", "rows": [json.loads(l) for l in lines[-limit:] if l.strip()][::-1]}
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{type(exc).__name__}: {exc}"}


def lock_holder() -> str:
    """"" when nothing holds the shared lock (C242), else who might: a
    terminal deploy or the updater. Asked without creating anything: no lock
    file means nobody has ever taken it, so nobody holds it now."""
    import fcntl

    try:
        fd = os.open(LOCK, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return ""
    except OSError as exc:
        return f"the lock could not be opened ({exc.strerror}), so whether one runs is unknown"
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return ""
    except BlockingIOError:
        return "a terminal deploy (nmas-deploy) or the updater is moving the checkout now"
    finally:
        os.close(fd)


def pending() -> list:
    """Request files the updater has not taken yet."""
    try:
        return sorted(n for n in os.listdir(REQUEST_DIR) if n.endswith(".json"))
    except FileNotFoundError:
        return []


# ---------------------------------------------------------------------------
# The install: root-owned, and not writable by this process's user
# ---------------------------------------------------------------------------

def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def install_state(root: str = ROOT, installed=INSTALLED, active=None) -> dict:
    """``{"state": ok|not_installed|writable|differs|inactive, "files": [...], ...}``.

    WRITABLE is asked of THIS process (`os.access`): the app runs as the
    service user, so "not writable by the service user" is measured, not
    inferred from modes. A file root does not own, or one the service user
    can write, is the danger: the updater runs it as root."""
    files, missing, writable, differs = [], [], [], []
    for name, path, source in installed:
        row = {"name": name, "path": path}
        try:
            st = os.stat(path, follow_symlinks=False)
        except FileNotFoundError:
            missing.append(name)
            files.append(dict(row, state="absent"))
            continue
        except OSError as exc:
            files.append(dict(row, state="unreadable", error=exc.strerror))
            writable.append(f"{name} ({path}) could not be examined: {exc.strerror}")
            continue
        parent = os.path.dirname(path)
        bad = []
        if st.st_uid != 0:
            bad.append("not owned by root")
        if not stat.S_ISREG(st.st_mode):
            bad.append("not a regular file")
        if st.st_mode & 0o022:
            bad.append(f"mode {stat.S_IMODE(st.st_mode):04o} lets others write it")
        if os.access(path, os.W_OK):
            bad.append("the service user can write it")
        if os.access(parent, os.W_OK):
            bad.append(f"the service user can write its directory {parent}")
        if bad:
            writable.append(f"{name} ({path}): " + ", ".join(bad))
        row["problems"] = bad
        if source:
            try:
                same = _sha(path) == _sha(os.path.join(root, source))
            except OSError as exc:
                same = None
                row["compare_error"] = exc.strerror
            row["matches_release"] = same
            if same is False:
                differs.append(f"{name} ({path}) differs from this release's {source}")
        files.append(dict(row, state="present"))
    out = {"files": files, "missing": missing, "writable": writable, "differs": differs}
    if len(missing) == len(installed):
        return dict(out, state="not_installed")
    if writable:
        return dict(out, state="writable")
    if missing:
        return dict(out, state="not_installed")
    if active is None:
        active = _path_active()
    out["path_active"] = active
    if active is not True:
        return dict(out, state="inactive")
    if differs:
        return dict(out, state="differs")
    return dict(out, state="ok")


def _path_active():
    import subprocess

    try:
        out = subprocess.run(["systemctl", "is-active", "nmas-update.path"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() == "active"


INSTALL_ACTION = {"label": "Install the updater on the host (a one-time step: docs/UPDATE.md)",
                  "reference": "docs/UPDATE.md"}
REINSTALL_ACTION = {"label": "Re-install the updater's root-owned copies from this release "
                             "(docs/UPDATE.md, \"Re-install\")", "reference": "docs/UPDATE.md"}


def install_rows(state: dict = None) -> list:
    """Job health's row for the updater's install (the operator's check: the
    script and units are root-owned and not writable by the service user)."""
    what = ("the Update button's root-owned updater is installed, and nothing the service "
            "user can write is run as root")
    try:
        s = install_state() if state is None else state
    except Exception as exc:                              # noqa: BLE001
        return [{"unit": "updater", "what": what, "state": "unknown", "max_age_minutes": 0,
                 "detail": f"the check raised {type(exc).__name__}: {exc} -- not the same as ok"}]
    st = s["state"]
    if st == "ok":
        return [{"unit": "updater", "what": what, "state": "ok", "max_age_minutes": 0,
                 "detail": "installed, root-owned, not writable by the service user, "
                           "matching this release, and the path unit is watching"}]
    if st == "writable":
        return [{"unit": "updater", "what": what, "state": "writable", "max_age_minutes": 0,
                 "action": {"label": "Make each named file and its directory root-owned and "
                                     "writable only by root, then re-install from this release "
                                     "(docs/UPDATE.md)", "reference": "docs/UPDATE.md"},
                 "detail": "RUN AS ROOT and writable by someone else: " + "; ".join(s["writable"])}]
    if st == "not_installed":
        return [{"unit": "updater", "what": what, "state": "not_installed", "max_age_minutes": 0,
                 "action": dict(INSTALL_ACTION),
                 "detail": ("the Update button cannot act until it is installed; missing: "
                            + ", ".join(s["missing"]))}]
    if st == "inactive":
        return [{"unit": "updater", "what": what, "state": "path_inactive", "max_age_minutes": 0,
                 "action": {"label": "Enable the path unit on the host",
                            "command": "sudo systemctl enable --now nmas-update.path"},
                 "detail": ("nmas-update.path is not active, so a request would wait for ever"
                            if s.get("path_active") is False else
                            "whether nmas-update.path is active could not be asked")}]
    return [{"unit": "updater", "what": what, "state": "differs", "max_age_minutes": 0,
             "action": dict(REINSTALL_ACTION),
             "detail": "; ".join(s["differs"]) + ". The installed copy still works; it is "
                                                 "the one that runs"}]


# ---------------------------------------------------------------------------
# The preview
# ---------------------------------------------------------------------------

def _stored(cached=None) -> dict:
    from modules import reader_job

    got = reader_job.read_cached("app-pushed") if cached is None else cached
    good = ((got.get("doc") or {}).get("last_good") or {}) if got.get("state") == "ok" else {}
    return {"value": good.get("value") or {}, "value_at": good.get("value_at"),
            "why": got.get("why") or "", "state": got.get("state")}


def plan(cached=None, install=None, running=None, pending_now=None, now_outcome=None,
         holder=None) -> dict:
    """What the Update preview draws, with its gates and its hash."""
    from modules.readers import app_pushed
    from routes import health

    stored = _stored(cached)
    v = stored["value"]
    running = health._COMMIT if running is None else running
    install = install_state() if install is None else install
    pend = pending() if pending_now is None else pending_now
    last = outcome() if now_outcome is None else now_outcome
    gates = []

    def gate(name, ok, detail):
        gates.append({"name": name, "state": "pass" if ok else "fail", "detail": detail})

    fresh = bool(v) and v.get("running") == running
    gate("the comparison is for the commit running now", fresh,
         (f"stored {stored['value_at']}" if fresh else
          ("the reader has not compared the running commit yet"
           + (f": {stored['why']}" if stored["why"] else ""))))
    behind = fresh and v.get("state") == "behind"
    gate("origin/main is ahead of the running commit, and fetched", behind,
         app_pushed.words(v) if v else "nothing stored yet")
    ci = v.get("ci") or {}
    gate("CI passed the target", behind and ci.get("tip") == v.get("tip")
         and ci.get("state") == "verified",
         (ci.get("sentence") or "not asked yet") + (f" (asked {ci['asked_at']})"
                                                     if ci.get("asked_at") else ""))
    changes = v.get("checkout_changes")
    gate("the checkout has no local changes", changes == [],
         "clean" if changes == [] else ("could not be read" if changes is None
                                        else "; ".join(changes)))
    gate("the updater is installed, root-owned, and the path unit is watching",
         install["state"] in ("ok", "differs"),
         {"ok": "yes", "differs": "yes; " + "; ".join(install.get("differs") or []),
          "not_installed": "not installed (docs/UPDATE.md)",
          "writable": "DANGER: " + "; ".join(install.get("writable") or []),
          "inactive": "nmas-update.path is not active"}.get(install["state"], install["state"]))
    running_now = (last.get("value") or {}).get("outcome") == "running"
    held = lock_holder() if holder is None else holder
    gate("no update or terminal deploy is waiting or running",
         not pend and not running_now and not held,
         ("the updater is running: " + str((last.get("value") or {}).get("step") or "")
          if running_now else f"{len(pend)} request(s) not taken yet" if pend
          else held or "none"))
    steps = v.get("host_steps") or []
    facts = {"running": running, "target": v.get("tip") or "", "behind": v.get("behind"),
             "commits": v.get("commits") or [], "commits_cut": bool(v.get("commits_cut")),
             "ci": ci, "host_steps": steps, "updater_changes": v.get("updater_changes") or [],
             "behind_since": v.get("behind_since") or "",
             "behind_since_basis": v.get("behind_since_basis") or "",
             "value_at": stored["value_at"], "state": v.get("state") or ""}
    digest = hashlib.sha256(json.dumps(
        {"running": running, "target": facts["target"], "ci": ci.get("state"),
         "steps": [s["sha"] + s["step"] for s in steps]}, sort_keys=True).encode()).hexdigest()[:16]
    ok = all(g["state"] == "pass" for g in gates)
    return {"facts": facts, "gates": gates, "selectable": ok, "hash": digest,
            "why_not": "; ".join(f"{g['name']}: {g['detail']}" for g in gates
                                 if g["state"] != "pass"),
            "last": last, "install": install}


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------

def request(confirmed_hash: str, acknowledged: list, actor: str, **plan_kw) -> dict:
    """Write the request the root-owned updater acts on, after recomputing
    the preview. ``{"ok": False, "reason"}`` when refused; nothing written."""
    from modules.filestore import write_atomic

    p = plan(**plan_kw)
    if not actor:
        return {"ok": False, "reason": "no verified person: an update is a person's step"}
    if not p["selectable"]:
        return {"ok": False, "reason": "refused: " + p["why_not"], "plan": p}
    if p["hash"] != confirmed_hash:
        return {"ok": False, "plan": p,
                "reason": (f"what the preview showed has changed ({confirmed_hash} -> "
                           f"{p['hash']}): the target, its CI verdict or its host steps moved. "
                           "Nothing was requested; preview again")}
    steps = {s["sha"] for s in p["facts"]["host_steps"]}
    ack = sorted(set(a for a in (acknowledged or []) if a in steps))
    if steps - set(ack):
        return {"ok": False, "plan": p,
                "reason": "every host step must be done first, and said to be done: "
                          + "; ".join(f"{s['sha'][:10]}: {s['step']}"
                                      for s in p["facts"]["host_steps"] if s["sha"] not in ack)}
    rid = os.urandom(8).hex()
    doc = {"id": rid, "target": p["facts"]["target"], "from": p["facts"]["running"],
           "requested_by": actor, "requested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                time.gmtime()),
           "acknowledged_host_steps": ack}
    config.secure_dir(STAGING_DIR)
    config.secure_dir(REQUEST_DIR)
    # Written OUTSIDE the watched directory and renamed in: the path unit
    # starts the updater on a directory that is not empty, and must never see
    # a half-written temporary file there.
    staged = os.path.join(STAGING_DIR, f"{rid}.json")
    write_atomic(staged, json.dumps(doc, sort_keys=True))
    os.replace(staged, os.path.join(REQUEST_DIR, f"{rid}.json"))
    try:
        with config.open_secure(AUDIT, "a") as fh:
            fh.write(json.dumps(dict(doc, preview_hash=p["hash"]), sort_keys=True) + "\n")
    except OSError as exc:
        log.error("update: the request %s could not be recorded in %s: %s", rid, AUDIT, exc)
    log.info("update: %s requested %s -> %s (request %s)", actor, doc["from"][:10],
             doc["target"][:10], rid)
    return {"ok": True, "id": rid, "target": doc["target"], "from": doc["from"],
            "up_bound_s": UP_BOUND_S, "updater_timeout_s": UPDATER_TIMEOUT_S}


def status() -> dict:
    """The waiting page's facts: what runs, what is waiting, what the updater
    last said. Never a guess: absent and unreadable are said."""
    from routes import health

    return {"running": health._COMMIT or "", "pending": pending(), "outcome": outcome(),
            "outcome_words": OUTCOME_WORDS}
