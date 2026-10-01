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

import calendar
import hashlib
import json
import logging
import os
import re
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

#: UPDATE WHEN CI PASSES (the operator, 2026-09-30): a person confirms the
#: update while CI is still checking the release, and the app requests it the
#: moment CI passes. Recorded here, released by the `app-pushed` reader after
#: each read (it asks CI every 60 s while a verdict is pending), never by a
#: timer of its own. The request it writes is the person's, bound to the
#: release they chose: a newer push, a failed or cancelled CI, or any other
#: gate failing ends the wait in words, and nothing is updated.
DEFERRED = os.path.join(config.DATA_DIR, "update", "deferred.json")
DEFERRED_OUTCOME = os.path.join(config.DATA_DIR, "update", "deferred_outcome.json")
#: nmas-deploy's own audit (one row per run), read for "the last update" by
#: the terminal route.
DEPLOY_AUDIT = os.path.join(config.DATA_DIR, "deploy_audit.jsonl")

#: How long a wait lasts: 2.5x CI's job bound (10 min in ci.yml, itself 2.7x
#: the slowest measured job, 224 s), because a run can queue before it starts.
DEFER_BOUND_S = 1500

#: CI's verdict, in a person's words. nmas-deploy's own sentence names the run
#: and tells a TERMINAL user to run `nmas-deploy --wait`; on this page the
#: button waits instead, so that sentence is the cause on hover, never the line.
CI_PERSON = {
    "verified": "CI passed this release",
    "pending": ("CI is still checking this release (a check takes about 4 minutes here). "
                "You can confirm now, and it updates when CI passes"),
    # Never a promise the tool cannot keep (the operator, 2026-10-01): it does
    # not know that the next release fixes anything.
    "failed": "CI failed for this release: it will not be installed. A fix needs a new release",
    "cancelled": "CI's check of this release was stopped, usually because a newer release "
                 "replaced it: check again for the newer one",
    "could_not_ask": "CI could not be asked about this release just now; Check again asks once more",
}

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


def install_state(root: str = ROOT, installed=INSTALLED, active=None, self_test=None) -> dict:
    """``{"state": ok|not_installed|writable|cannot_run|differs|inactive, "files": [...], ...}``.

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
    # CAN it run (C246)? Owned and unwritable said nothing about whether the
    # programs it runs exist: the first real run died on `runuser`. The
    # INSTALLED copy's own self-test, reached only now that it is known to be
    # root-owned and writable by nobody else.
    if self_test is None:
        updater = next((p for _n, p, src in installed if src == "deploy/update/nmas-update"), None)
        self_test = (lambda: installed_self_test(updater)) if updater else (lambda: [])
    try:
        cannot = [str(p) for p in self_test()]
    except Exception as exc:                              # noqa: BLE001
        cannot = [f"its self-test raised {type(exc).__name__}: {exc}"]
    out["cannot_run"] = cannot
    if cannot:
        return dict(out, state="cannot_run")
    if active is None:
        active = _path_active()
    out["path_active"] = active
    if active is not True:
        return dict(out, state="inactive")
    if differs:
        return dict(out, state="differs")
    return dict(out, state="ok")


def installed_self_test(path: str) -> list:
    """The INSTALLED updater's own `self_test()` (C246): every program it runs,
    by the absolute path it runs it by, exists and is root's. Loaded from the
    root-owned copy, never the repository's, because the copy is what runs; a
    copy with no self-test predates the fix and cannot be trusted to run."""
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("nmas_update_installed", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    fn = getattr(mod, "self_test", None)
    if fn is None:
        return ["the installed updater has no self-test: it predates the release that runs "
                "every program by absolute path (C246), and its first run died on `runuser`; "
                "re-install it"]
    return fn()


def _path_active():
    import subprocess

    try:
        out = subprocess.run(["systemctl", "is-active", "nmas-update.path"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() == "active"


INSTALL_ACTION = {"label": "Install the updater, once, on the host, in this checkout as the "
                           "service user (sudo asks for the password):",
                  "reference": "docs/UPDATE.md, \"The one-time install\""}
REINSTALL_ACTION = {"label": "Re-install the updater's root-owned copies from this release, on "
                             "the host, in this checkout as the service user:",
                    "reference": "docs/UPDATE.md, \"Re-install\""}

#: The exact commands, ONE owner: the row shows them with a copy button, and
#: `nmas-update-check` (so `nmas-deploy`'s last lines) prints them. A root step
#: is the one-time exception to "no console command on a row" (the operator,
#: 2026-09-30: a row pointing at a document made them go looking). A test holds
#: each line equal to docs/UPDATE.md's own.
#: The updater's two units, rendered into a FRESH directory and installed by
#: name, in ONE line: a shared folder held units rendered for earlier installs,
#: and a glob over it would have reinstalled them (the operator, 2026-10-01).
#: One line, so nothing depends on a variable set on an earlier line.
UNITS_COMMAND = ('d=$(mktemp -d) && scripts/nmas-render-units --out "$d" '
                 'deploy/systemd/nmas-update.path deploy/systemd/nmas-update.service && '
                 'cat "$d/nmas-update.path" "$d/nmas-update.service" && '
                 'sudo install -o root -g root -m 0644 "$d/nmas-update.path" '
                 '"$d/nmas-update.service" /etc/systemd/system/')
REINSTALL_COMMANDS = (
    "sudo install -o root -g root -m 0755 deploy/update/nmas-update /usr/local/sbin/nmas-update",
    "sudo install -o root -g root -m 0644 scripts/nmas-deploy /usr/local/lib/nmas-update/nmas-deploy",
    UNITS_COMMAND,
    "sudo systemctl daemon-reload",
    "scripts/nmas-update-check",
)
INSTALL_COMMANDS = (
    "sudo install -o root -g root -m 0755 deploy/update/nmas-update /usr/local/sbin/nmas-update",
    "sudo install -d -o root -g root -m 0755 /usr/local/lib/nmas-update",
    "sudo install -o root -g root -m 0644 scripts/nmas-deploy /usr/local/lib/nmas-update/nmas-deploy",
    UNITS_COMMAND,
    "sudo install -d -o root -g root -m 0755 /var/lib/nmas-update",
    "install -d -m 0700 data/update/requests data/update/staging",
    "sudo systemctl daemon-reload",
    "sudo systemctl enable --now nmas-update.path",
    "scripts/nmas-update-check",
)


def commands_for(commands: tuple, root: str = ROOT) -> str:
    """The commands as one block to paste, starting in this checkout."""
    return "\n".join((f"cd {root}",) + tuple(commands))


def condition_since(installed: str = INSTALLED[0][1], started: float = None) -> tuple:
    """(epoch, basis) of when the installed updater and the RUNNING release
    began to disagree (the operator, 2026-09-30: the row read "since not
    recorded"). It cannot be earlier than either of two measured moments, and
    it is the later one: this release starting to run, or the installed copy
    being written. Asked of the app process, whose start is the release's."""
    if started is None:
        from routes import health
        started = health._STARTED                           # noqa: SLF001
    try:
        written = os.stat(installed).st_mtime
    except OSError:
        written = None
    if written is not None and written > started:
        return written, "when the installed copy was written"
    return started, "when this release started running"


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
                           "every program it runs present and root's (its self-test), "
                           "matching this release, and the path unit is watching"}]
    if st == "writable":
        return [{"unit": "updater", "what": what, "state": "writable", "max_age_minutes": 0,
                 "action": {"label": "Make each named file and its directory root-owned and "
                                     "writable only by root, then re-install from this release "
                                     "(docs/UPDATE.md)", "reference": "docs/UPDATE.md"},
                 "detail": "RUN AS ROOT and writable by someone else: " + "; ".join(s["writable"])}]
    since, basis = condition_since() if st in ("cannot_run", "differs") else (None, "")
    if st == "cannot_run":
        return [{"unit": "updater", "what": what, "state": "cannot_run", "max_age_minutes": 0,
                 "since": since, "since_basis": basis,
                 "action": dict(REINSTALL_ACTION, command=commands_for(REINSTALL_COMMANDS)),
                 "detail": ("the updater CANNOT RUN: a request would fail before moving "
                            "anything (its self-test, C246): " + "; ".join(s["cannot_run"])
                            + f". It began {basis}")}]
    if st == "not_installed":
        return [{"unit": "updater", "what": what, "state": "not_installed", "max_age_minutes": 0,
                 "action": dict(INSTALL_ACTION, command=commands_for(INSTALL_COMMANDS)),
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
             "since": since, "since_basis": basis,
             "action": dict(REINSTALL_ACTION, command=commands_for(REINSTALL_COMMANDS)),
             "detail": "; ".join(s["differs"]) + ". The installed copy still works; it is "
                                                 f"the one that runs. It began {basis}"}]


# ---------------------------------------------------------------------------
# The preview
# ---------------------------------------------------------------------------

def _stored(cached=None) -> dict:
    from modules import reader_job

    got = reader_job.read_cached("app-pushed") if cached is None else cached
    good = ((got.get("doc") or {}).get("last_good") or {}) if got.get("state") == "ok" else {}
    return {"value": good.get("value") or {}, "value_at": good.get("value_at"),
            "why": got.get("why") or "", "state": got.get("state")}


def person_ci(ci: dict, target: str = "") -> str:
    """The CI gate's line, in a person's words."""
    if not ci or (target and ci.get("tip") != target):
        return "CI has not been asked about this release yet; Check again asks now"
    if ci.get("state") == "failed":
        # The run, named (the operator, 2026-10-01): "CI failed for this
        # release (run #241): it won't be installed".
        m = re.search(r"run #(\d+)", ci.get("sentence") or "")
        return ("CI failed for this release" + (f" (run #{m.group(1)})" if m else "")
                + ": it will not be installed. A fix needs a new release")
    return CI_PERSON.get(ci.get("state"), f"CI answered {ci.get('state')!r}")


#: A CI verdict's badge, in words (the operator: "could_not_ask" leaked as text).
CI_BADGE = {"verified": "passed", "failed": "failed", "cancelled": "cancelled",
            "pending": "checking", "could_not_ask": "not asked"}

#: The updater's step keys, in words, for a record that names one.
STEP_WORDS = dict(STEPS)


def terminal_deploy(path: str = None) -> dict:
    """The last terminal deploy that moved the app (`nmas-deploy`'s audit row,
    exit 0 with a target), in the updater's record's shape; ``{}`` when none
    is recorded or the record cannot be read."""
    path = path or DEPLOY_AUDIT
    last = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("exit") == 0 and row.get("to") and row.get("from") != row.get("to"):
                    last = row
    except OSError:
        return {}
    if not last:
        return {}
    return {"outcome": "updated", "from": last.get("from") or "", "to": last["to"],
            "requested_by": last.get("user") or "", "route": "terminal",
            "ended_at": str(last.get("ended_at") or "")[:19] + "Z" if last.get("ended_at") else ""}


def last_update(updater: dict = None, terminal: dict = None) -> dict:
    """"The last update" by EITHER route (the operator, 2026-10-01: the panel
    showed the button's e7b80c7 -> 771bead and not the terminal deploy 771bead
    -> 1954ce7 after it): the newer of the updater's record and the last terminal
    deploy, in the updater's record's shape ``{"state", "value"}``."""
    updater = outcome() if updater is None else updater
    terminal = terminal_deploy() if terminal is None else terminal
    uv = (updater.get("value") or {}) if updater.get("state") == "ok" else {}
    u_at = str(uv.get("ended_at") or uv.get("at") or "")
    if terminal and str(terminal.get("ended_at") or "") > u_at:
        return {"state": "ok", "value": terminal}
    return updater


def deferred() -> dict:
    """The wait in force, ``{}`` when none (an unreadable file is said)."""
    got = _read_json(DEFERRED)
    if got["state"] == "unreadable":
        return {"unreadable": got["error"]}
    return got.get("value") or {}


def deferred_outcome() -> dict:
    """How the last wait ended, ``{}`` when none has. Its ``words`` are
    computed now from the outcome and the target (`wait_end_words`), never the
    sentence stored when it ended: that sentence says whatever the code that
    wrote it promised (the operator, 2026-10-01: a stored "The next release
    fixes it" outlived the change that removed the promise)."""
    doc = _read_json(DEFERRED_OUTCOME).get("value") or {}
    return dict(doc, words=wait_end_words(doc)) if doc else {}


BOUND_WORDS = "the wait's bound"


def wait_end_words(doc: dict) -> str:
    """How a wait ended, in words built from its OUTCOME, its TARGET and the
    one variable fact it recorded (``detail``: who stopped it, the newer
    release, the refusal), never from stored prose."""
    short = (doc.get("target") or "")[:10] or "the release"
    o, detail = doc.get("outcome") or "", doc.get("detail") or ""
    if o.startswith("ci_"):
        return (person_ci({"state": o[3:], "tip": doc.get("target"), "sentence": detail},
                          doc.get("target") or "")
                + f"; nothing was updated (asked for {short})")
    words = {
        "requested": f"CI passed {short}; the update was requested",
        "stopped": f"stopped{' by ' + detail if detail else ''}: nothing was updated",
        "gave_up": (f"CI had not passed {short} within {detail or BOUND_WORDS}, "
                    "so nothing was updated: Check again, then update"),
        "superseded": (f"a newer release{' (' + detail + ')' if detail else ''} was pushed after "
                       f"you asked for {short}, so nothing was updated: the page shows the newer one"),
        "refused": f"CI passed {short}, but it was not updated" + (f": {detail}" if detail else ""),
        "unreadable": ("the wait record could not be read" + (f" ({detail})" if detail else "")
                       + "; nothing was updated"),
    }
    return words.get(o, f"it ended ({o or 'with no outcome recorded'}); nothing was updated")


CI_GATE = "CI passed the target"


def plan(cached=None, install=None, running=None, pending_now=None, now_outcome=None,
         holder=None, waiting=None) -> dict:
    """What the Update preview draws, with its gates and its hash.

    *waiting* is the wait in force (``deferred()`` when None); the release
    passes ``{}`` so its own wait does not refuse it."""
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
    gate(CI_GATE, behind and ci.get("tip") == v.get("tip")
         and ci.get("state") == "verified", person_ci(ci, v.get("tip") or ""))
    changes = v.get("checkout_changes")
    gate("the checkout has no local changes", changes == [],
         "clean" if changes == [] else ("could not be read" if changes is None
                                        else "; ".join(changes)))
    gate("the updater is installed, root-owned, can run, and the path unit is watching",
         install["state"] in ("ok", "differs"),
         {"ok": "yes", "differs": "yes; " + "; ".join(install.get("differs") or []),
          "not_installed": "not installed (docs/UPDATE.md)",
          "writable": "DANGER: " + "; ".join(install.get("writable") or []),
          "cannot_run": "it would fail before moving anything: "
                        + "; ".join(install.get("cannot_run") or []),
          "inactive": "nmas-update.path is not active"}.get(install["state"], install["state"]))
    running_now = (last.get("value") or {}).get("outcome") == "running"
    held = lock_holder() if holder is None else holder
    wait = deferred() if waiting is None else waiting
    gate("no update or terminal deploy is waiting or running",
         not pend and not running_now and not held and not wait,
         ("the updater is running: " + str((last.get("value") or {}).get("step") or "")
          if running_now else f"{len(pend)} request(s) not taken yet" if pend
          else held if held
          else (f"an update to {str(wait.get('target') or '?')[:10]} is waiting for CI, asked "
                f"by {wait.get('requested_by') or 'someone'}" if wait.get("target")
                else f"the wait record could not be read ({wait['unreadable']})")
          if wait else "none"))
    from modules import host_steps as HS
    # Each BEFORE step checked where the tool can check it (the operator,
    # 2026-09-30): a step the check finds done needs no box; one it finds not
    # done blocks, saying what it found; only a step no check can answer is
    # said done by the person.
    steps = [dict(s, **{("check_" + k): c for k, c in HS.check(s).items()})
             for s in (v.get("host_steps") or [])]
    after = [dict(s, **{("check_" + k): c for k, c in HS.check(s).items()})
             for s in (v.get("after_steps") or [])]
    facts = {"running": running, "target": v.get("tip") or "", "behind": v.get("behind"),
             "commits": v.get("commits") or [], "commits_cut": bool(v.get("commits_cut")),
             "ci": ci, "host_steps": steps, "after_steps": after, "updater_changes": v.get("updater_changes") or [],
             "behind_since": v.get("behind_since") or "",
             "behind_since_basis": v.get("behind_since_basis") or "",
             "value_at": stored["value_at"], "state": v.get("state") or ""}
    digest = hashlib.sha256(json.dumps(
        {"running": running, "target": facts["target"], "ci": ci.get("state"),
         "steps": [s["sha"] + s["step"] for s in steps]}, sort_keys=True).encode()).hexdigest()[:16]
    ok = all(g["state"] == "pass" for g in gates)
    # Waitable: every gate passes but CI's, and CI is still checking THIS
    # target. Then the button reads "Update when CI passes".
    waitable = (not ok and behind and ci.get("tip") == v.get("tip")
                and ci.get("state") == "pending"
                and all(g["state"] == "pass" for g in gates if g["name"] != CI_GATE))
    ended = deferred_outcome()
    last_end = (last.get("value") or {}).get("ended_at") or ""
    ended_unshown = bool(ended and ended.get("outcome") != "requested"
                         and str(ended.get("ended_at") or "") > last_end)
    return {"facts": facts, "gates": gates, "selectable": ok, "hash": digest,
            "why_not": "; ".join(f"{g['name']}: {g['detail']}" for g in gates
                                 if g["state"] != "pass"),
            "waitable": waitable, "waiting": wait, "ci_words": person_ci(ci, v.get("tip") or ""),
            # How the last wait ended, when it ended without an update and
            # after the updater's last record: otherwise "The last update" says it.
            # Above the button only while it concerns the release OFFERED (the
            # operator, 2026-10-01: "CI failed ... (asked for 9fd781bcbf)" sat
            # above "Update to 8f1676c02d", after the newer release passed);
            # about another release it is history, under "Earlier updates".
            "wait_ended": (ended if ended_unshown and ended.get("target") == facts["target"]
                           else {}),
            "wait_ended_earlier": (ended if ended_unshown
                                   and ended.get("target") != facts["target"] else {}),
            "following": following(ended, last, running),
            "last": last, "last_shown": last_update(updater=last), "install": install}


#: The updater's outcomes that end a run (its record names one of these last).
FINISHED = ("updated", "refused", "rolled_back", "rollback_failed", "failed")


def following(ended: dict, last: dict, running: str, clock=time.time) -> str:
    """The request a wait released, while its update has not finished: the
    page follows its stepper from this id (a redraw can land between the
    release and the page hearing of it). "" once the updater has finished it,
    once the app runs its target, or past the updater's own limit."""
    ended = ended or {}
    rid = ended.get("request_id") or ""
    if ended.get("outcome") != "requested" or not rid or ended.get("target") == running:
        return ""
    lv = (last or {}).get("value") or {}
    if lv.get("id") == rid and lv.get("outcome") in FINISHED:
        return ""
    try:
        at = calendar.timegm(time.strptime(str(ended.get("ended_at")), "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return ""
    return rid if clock() - at <= UPDATER_TIMEOUT_S else ""


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------

def request(confirmed_hash: str, acknowledged: list, actor: str, **plan_kw) -> dict:
    """Write the request the root-owned updater acts on, after recomputing
    the preview. ``{"ok": False, "reason"}`` when refused; nothing written."""
    p = plan(**plan_kw)
    if not actor:
        return {"ok": False, "reason": "no verified person: an update is a person's step"}
    if not p["selectable"]:
        return {"ok": False, "reason": "Not now: " + p["why_not"], "plan": p}
    bad, ack = _confirmed(p, confirmed_hash, acknowledged)
    if bad:
        return {"ok": False, "plan": p, "reason": bad}
    return _write_request(p, ack, actor)


def _confirmed(p: dict, confirmed_hash: str, acknowledged) -> tuple:
    """(refusal or "", the acknowledged host steps) for a confirm of *p*."""
    if p["hash"] != confirmed_hash:
        return (f"what the preview showed has changed ({confirmed_hash} -> {p['hash']}): the "
                "target, its CI verdict or its host steps moved. Nothing was requested; the "
                "page shows the new preview"), []
    return step_gate(p["facts"]["host_steps"], acknowledged)


def step_gate(steps: list, acknowledged) -> tuple:
    """(refusal or "", the acknowledged commits) for the BEFORE steps: a step
    its check finds done needs nothing; one it finds NOT done refuses, naming
    what it found, whatever was ticked; any other is said done by the person
    (their tick). The updater acknowledges by commit, so a commit is
    acknowledged when every one of its steps is."""
    said = set(acknowledged or [])
    blocked, unsaid, ok = [], [], set()
    for s in steps:
        state = s.get("check_state") or "not_checkable"
        if state == "done":
            continue
        if state == "not_done":
            blocked.append(f"{s['sha'][:10]}: {s['step']} (checked: {s.get('check_detail')})")
        elif s["sha"] not in said:
            unsaid.append(f"{s['sha'][:10]}: {s['step']}")
    if blocked:
        return ("a host step this release needs BEFORE it runs is not done yet, as checked: "
                + "; ".join(blocked)), []
    if unsaid:
        return ("a host step this release needs before it runs has not been ticked as done: "
                + "; ".join(unsaid)), []
    ok = sorted({s["sha"] for s in steps})
    return "", ok


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_request(p: dict, ack: list, actor: str) -> dict:
    from modules.filestore import write_atomic

    rid = os.urandom(8).hex()
    doc = {"id": rid, "target": p["facts"]["target"], "from": p["facts"]["running"],
           "requested_by": actor, "requested_at": _now(),
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


# ---------------------------------------------------------------------------
# Update when CI passes
# ---------------------------------------------------------------------------

def defer(confirmed_hash: str, acknowledged: list, actor: str, **plan_kw) -> dict:
    """Confirm the update now and have it requested when CI passes. Refused,
    with nothing recorded, unless CI's check of this target is the ONLY thing
    in the way."""
    from modules.filestore import PathLock, write_atomic

    if not actor:
        return {"ok": False, "reason": "no verified person: an update is a person's step"}
    with PathLock(DEFERRED):
        p = plan(**plan_kw)
        if p["selectable"]:
            # CI passed between the preview and the click: update now.
            return request(confirmed_hash, acknowledged, actor, **plan_kw)
        if not p["waitable"]:
            return {"ok": False, "plan": p, "reason": "Not now: " + p["why_not"]}
        bad, ack = _confirmed(p, confirmed_hash, acknowledged)
        if bad:
            return {"ok": False, "plan": p, "reason": bad}
        doc = {"target": p["facts"]["target"], "from": p["facts"]["running"],
               "requested_by": actor, "requested_at": _now(),
               "acknowledged_host_steps": ack, "preview_hash": p["hash"],
               "bound_s": DEFER_BOUND_S}
        config.secure_dir(os.path.dirname(DEFERRED))
        write_atomic(DEFERRED, json.dumps(doc, sort_keys=True))
    _audit(dict(doc, waiting_for_ci=True))
    log.info("update: %s asked for %s -> %s when CI passes", actor, doc["from"][:10],
             doc["target"][:10])
    return {"ok": True, "waiting": True, "target": doc["target"], "from": doc["from"],
            "bound_s": DEFER_BOUND_S}


def stop_waiting(actor: str) -> dict:
    """End the wait without updating, as *actor*."""
    from modules.filestore import PathLock

    if not actor:
        return {"ok": False, "reason": "no verified person"}
    with PathLock(DEFERRED):
        d = deferred()
        if not d:
            return {"ok": False, "reason": "nothing is waiting for CI"}
        _end(d, "stopped", actor)
    return {"ok": True}


def _audit(row: dict) -> None:
    try:
        with config.open_secure(AUDIT, "a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("update: %s could not be recorded in %s: %s", row, AUDIT, exc)


def _end(d: dict, outcome: str, detail: str = "", request_id: str = "") -> dict:
    """End the wait: the outcome, its target and its ONE variable fact
    (``detail``). ``words`` is stored for the audit's reader, and never drawn:
    the page computes them (`wait_end_words`)."""
    from modules.filestore import write_atomic

    doc = {"outcome": outcome, "detail": detail, "target": d.get("target") or "",
           "requested_by": d.get("requested_by") or "", "requested_at": d.get("requested_at") or "",
           "ended_at": _now(), **({"request_id": request_id} if request_id else {})}
    words = doc["words"] = wait_end_words(doc)
    write_atomic(DEFERRED_OUTCOME, json.dumps(doc, sort_keys=True))
    try:
        os.remove(DEFERRED)
    except FileNotFoundError:
        pass
    _audit(dict(doc, wait_ended=True))
    (log.info if outcome == "requested" else log.warning)(
        "update: the wait for CI on %s ended: %s", doc["target"][:10], words)
    return doc


def release_deferred(clock=time.time, **plan_kw):
    """After each `app-pushed` read: request the waiting update if CI has
    passed its target, end the wait in words if it never will, else keep
    waiting. Returns how the wait ended, or None while it continues."""
    from modules.filestore import PathLock

    with PathLock(DEFERRED):
        d = deferred()
        if not d:
            return None
        if d.get("unreadable"):
            return _end({}, "unreadable", d["unreadable"])
        target = str(d.get("target") or "")
        try:
            asked = calendar.timegm(time.strptime(str(d.get("requested_at")), "%Y-%m-%dT%H:%M:%SZ"))
        except ValueError:
            return _end(d, "unreadable", "it has no readable time")
        if clock() - asked > int(d.get("bound_s") or DEFER_BOUND_S):
            return _end(d, "gave_up", f"{int(d.get('bound_s') or DEFER_BOUND_S) // 60} min")
        p = plan(waiting={}, **plan_kw)
        f, ci = p["facts"], p["facts"]["ci"] or {}
        if f["target"] and f["target"] != target:
            return _end(d, "superseded", f["target"][:10])
        if ci.get("tip") != target or ci.get("state") in ("pending", "could_not_ask", None):
            return None
        if ci.get("state") != "verified":
            run = re.search(r"run #(\d+)", ci.get("sentence") or "")
            return _end(d, f"ci_{ci.get('state')}", f"run #{run.group(1)}" if run else "")
        if not p["selectable"]:
            return _end(d, "refused", p["why_not"])
        bad, ack = step_gate(f["host_steps"], d.get("acknowledged_host_steps") or [])
        if bad:
            return _end(d, "refused", bad)
        # The request is the updater's exact fields (its validate() refuses any
        # other), dated now; the wait itself is in this app's audit and the
        # outcome record.
        got = _write_request(p, ack, d.get("requested_by") or "")
        return _end(d, "requested", request_id=got["id"])


def status() -> dict:
    """The waiting page's facts: what runs, what is waiting, what the updater
    last said. Never a guess: absent and unreadable are said."""
    from routes import health

    return {"running": health._COMMIT or "", "pending": pending(), "outcome": outcome(),
            "outcome_words": OUTCOME_WORDS, "waiting": deferred(),
            "wait_ended": deferred_outcome()}
