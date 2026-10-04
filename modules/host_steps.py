"""HOST STEPS: what a person does on the host for a release, said in its
commit, and checked by the tool wherever it can be (the operator, 2026-09-30).

A step has a KIND, because the Update page demanded that a580660's step
("install deploy/topology/rcn-topology.py as a symlink") be said done BEFORE
the update, while the file it installs exists only AFTER it. Saying so would
have put a false "done" in the audit trail.

    Host-Step: [<check>] <text>         BEFORE: the update waits until it is done
    Host-Step-After: [<check>] <text>   AFTER: never blocks; once the release
                                        runs, it is a Needs attention row
                                        until done

`[<check>]` names a check in `CHECKS`, so the tool answers "done" itself (the
symlink's target, the service's restart time) instead of asking a person to
say so; a step without one is recorded done by a person, by name, on the
Update page. The root-owned updater parses `Host-Step:` alone, so an AFTER
step never reaches it and needs no re-install of the updater.

`Host-Step-None: <why>` says a host-installed file changed and nothing is
needed (scripts/nmas-host-step-check).
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import time

from modules import config

log = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TRAILER = re.compile(r"^Host-Step(?P<after>-After)?:[ \t]*(?:\[(?P<check>[a-z0-9-]+)\][ \t]*)?"
                     r"(?P<text>\S.*?)[ \t]*$", re.M)

#: Done records for steps no check can answer: who said so, and when.
DONE = os.path.join(config.DATA_DIR, "host_steps_done.jsonl")

#: How far back the running history is read for AFTER steps still owed. A
#: release is a handful of commits; 200 is far past any gap measured here.
HISTORY = 200


def parse(body: str) -> list:
    """``[{"when": "before"|"after", "check": id or "", "step": text}]``."""
    return [{"when": "after" if m.group("after") else "before",
             "check": m.group("check") or "", "step": m.group("text")}
            for m in TRAILER.finditer(body or "")]


def step_id(sha: str, step: str) -> str:
    return f"{sha[:12]}:{hashlib.sha256(step.encode()).hexdigest()[:8]}"


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def _service_started(unit: str, run=subprocess.run):
    """The unit's main process start as epoch seconds, or None."""
    try:
        p = run(["systemctl", "show", unit, "-p", "ExecMainStartTimestamp", "--timestamp=unix"],
                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"=@(\d+)", p.stdout or "")
    return int(m.group(1)) if m else None


#: Where the topology renderer is installed: a symlink to the checkout's copy.
TOPOLOGY_LINK = "/usr/local/bin/rcn-topology.py"
TOPOLOGY_SOURCE_REL = "deploy/topology/rcn-topology.py"
TOPOLOGY_UNIT = "rcn-topology.service"


def check_topology_renderer(root: str = ROOT, link: str = TOPOLOGY_LINK,
                            run=subprocess.run) -> dict:
    """Done when the installed renderer IS the checkout's (a symlink resolving
    to deploy/topology/rcn-topology.py) and rcn-topology.service started after
    that file last changed, so the running process read this release's code."""
    source = os.path.realpath(os.path.join(root, TOPOLOGY_SOURCE_REL))
    if not os.path.islink(link):
        return {"state": "not_done", "detail": (f"{link} is not a symlink to the checkout"
                                                if os.path.exists(link) else f"{link} is absent")}
    if os.path.realpath(link) != source:
        return {"state": "not_done", "detail": f"{link} points to {os.path.realpath(link)}, "
                                               f"not {source}"}
    started = _service_started(TOPOLOGY_UNIT, run=run)
    if started is None:
        return {"state": "unknown", "detail": "the symlink is right; when rcn-topology.service "
                                              "last started could not be read"}
    changed = int(os.path.getmtime(source))
    if started < changed:
        return {"state": "not_done", "detail": "the symlink is right, and rcn-topology.service "
                                               "has not restarted since the file changed"}
    return {"state": "done", "detail": f"{link} is the checkout's, and the service restarted "
                                       "after it changed"}


def check_updater(root: str = ROOT) -> dict:
    """Done when the updater's install check reads ok (update_op.install_state)."""
    from modules import update_op

    st = update_op.install_state(root)
    if st["state"] == "ok":
        return {"state": "done", "detail": "the updater's install check reads ok"}
    if st["state"] == "not_installed":
        return {"state": "done", "detail": "no updater is installed here: nothing to re-install"}
    return {"state": "not_done", "detail": f"the updater's install check reads {st['state']}"
                                           + ("; " + "; ".join(st.get("differs") or [])
                                              if st.get("differs") else "")}


def check_oxidized_helper(root: str = ROOT) -> dict:
    """Done when the installed Oxidized credential helper is this release's copy, root-owned
    and writable by no one else: the helper's own check (`credential_rotation.helper_status`,
    C375), so a person never vouches for what it measures (C416). No helper installed and no
    Oxidized configured: nothing to re-install."""
    from modules.nsot import credential_rotation as cr
    from modules.settings_schema import get_setting

    st = cr.helper_status()
    if st["state"] == "ok":
        return {"state": "done", "detail": f"{cr.HELPER_INSTALLED} is this release's "
                                           f"{cr.HELPER_SOURCE_REL} ({st.get('source_sha')})"}
    if st["state"] == "not_installed" and not str(get_setting("oxidized_url", "") or "").strip():
        return {"state": "done", "detail": "no helper is installed and no Oxidized is "
                                           "configured: nothing to re-install"}
    return {"state": "not_done", "detail": (st.get("reason") or st["state"]) + (
        f" (installed {st['installed_sha']}, this release {st['source_sha']})"
        if st.get("installed_sha") else "")}


CHECKS = {"topology-renderer": check_topology_renderer, "updater": check_updater,
          "oxidized-cred": check_oxidized_helper}


def check(step: dict, root: str = ROOT) -> dict:
    """``{"state": done|not_done|unknown|not_checkable, "detail"}`` for one step."""
    fn = CHECKS.get(step.get("check") or "")
    if fn is None:
        return {"state": "not_checkable",
                "detail": (f"no check named {step['check']!r}" if step.get("check")
                           else "the tool cannot check this step: a person says it is done")}
    try:
        return fn(root)
    except Exception as exc:                            # noqa: BLE001
        log.error("host step check %s raised: %s: %s", step.get("check"), type(exc).__name__, exc)
        return {"state": "unknown", "detail": f"the check raised {type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Done, said by a person
# ---------------------------------------------------------------------------

def done_records() -> dict:
    """{step id: row}; an unreadable record is said, never read as none."""
    out = {}
    try:
        with open(DONE, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    row = json.loads(line)
                    out[row["id"]] = row
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError) as exc:
        return {"__unreadable__": {"error": f"{type(exc).__name__}: {exc}"}}
    return out


def record_done(sha: str, step: str, actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no verified person: a host step is said done by a person"}
    row = {"id": step_id(sha, step), "sha": sha, "step": step, "by": actor,
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with config.open_secure(DONE, "a") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    log.info("host step %s said done by %s", row["id"], actor)
    return {"ok": True, "row": row}


# ---------------------------------------------------------------------------
# What the running release still owes
# ---------------------------------------------------------------------------

def _log(root: str, rng: str, limit: int, run=subprocess.run) -> str:
    p = run(["git", "-C", root, "log", f"--max-count={limit}", "--format=%H%x1f%B%x1e", rng],
            capture_output=True, text=True, timeout=15)
    if p.returncode != 0:
        raise RuntimeError(f"git log {rng} exited {p.returncode}: {p.stderr.strip()[:200]}")
    return p.stdout


def steps_in(text: str, when: str = None) -> list:
    """[{sha, step, check, when, id}] from `git log` output, oldest first."""
    out = []
    for chunk in reversed(text.split("\x1e")):
        sha, _sep, body = chunk.strip().partition("\x1f")
        for s in parse(body):
            if when is None or s["when"] == when:
                out.append(dict(s, sha=sha, id=step_id(sha, s["step"])))
    return out


def owed(running: str, root: str = ROOT, log_text: str = None) -> dict:
    """The AFTER steps of the running history that are not done:
    ``{"ok": bool, "steps": [...], "error"}``, each step with its check's
    answer or the person who said it done."""
    try:
        text = log_text if log_text is not None else _log(root, running, HISTORY)
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        return {"ok": False, "steps": [], "error": str(exc)}
    done = done_records()
    if "__unreadable__" in done:
        return {"ok": False, "steps": [], "error": "the host-step record could not be read: "
                                                  + done["__unreadable__"]["error"]}
    out, said = [], []
    for s in steps_in(text, when="after"):
        c = check(s, root)
        if c["state"] == "not_checkable" and s["id"] in done:
            said.append(dict(s, by=done[s["id"]].get("by"), at=done[s["id"]].get("at")))
            continue
        if c["state"] == "done":
            continue
        out.append(dict(s, check_state=c["state"], check_detail=c["detail"]))
    # The record read back: who said each step done, and when.
    return {"ok": True, "steps": grouped(out), "said_done": grouped(said)}


def grouped(steps: list) -> list:
    """One row per STEP, naming every commit that asked for it (the operator,
    2026-10-01: "re-install the updater's copy of scripts/nmas-deploy" was
    listed twice, for 4a61081 and dde8495, and it is one re-install). Keyed on
    the step's words and its check, oldest commit first; ``sha`` and ``id``
    stay the first commit's, and ``shas``/``ids`` hold them all."""
    out, by = [], {}
    for s in steps:
        key = (s["step"], s.get("check") or "")
        if key not in by:
            by[key] = dict(s, shas=[], ids=[])
            out.append(by[key])
        by[key]["shas"].append(s["sha"])
        by[key]["ids"].append(s["id"])
    return out
