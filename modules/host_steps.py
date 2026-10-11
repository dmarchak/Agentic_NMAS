"""HOST STEPS: what a person does on the host for a release, said in its
commit, and checked by the tool wherever it can be (the operator, 2026-09-30).

A step has a KIND, because the Update page demanded that a580660's step
("install the topology renderer as a symlink") be said done BEFORE
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


#: Where the topology renderer is installed: a symlink to the checkout's copy. Named for
#: the product since C663 (it carried the lab's name).
TOPOLOGY_LINK = "/usr/local/bin/nmas-topology.py"
TOPOLOGY_SOURCE_REL = "deploy/topology/nmas-topology.py"
TOPOLOGY_UNIT = "nmas-topology.service"


def check_topology_renderer(root: str = ROOT, link: str = TOPOLOGY_LINK,
                            run=subprocess.run) -> dict:
    """Done when the installed renderer IS the checkout's (a symlink resolving
    to deploy/topology/nmas-topology.py) and its service started after
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
        return {"state": "unknown", "detail": f"the symlink is right; when {TOPOLOGY_UNIT} "
                                              "last started could not be read"}
    changed = int(os.path.getmtime(source))
    if started < changed:
        return {"state": "not_done", "detail": f"the symlink is right, and {TOPOLOGY_UNIT} "
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


#: Oxidized retired (Phase 3 step 2, the operator's decision, 2026-10-08): nothing runs its
#: credential helper now, and the host steps remove the helper, its pin and its sudoers line
#: (docs/NSOT_PHASE3_RETIRE_OXIDIZED.md section 5). A step a past commit owes for it, by
#: `[oxidized-cred]` or `[oxidized-pin]`, is therefore done: re-installing a helper nothing
#: calls would be work for nothing, and a row asking for it would be a fact nobody acts on.
OXIDIZED_RETIRED = ("Oxidized is retired (Phase 3): nothing runs its helper, and the host "
                    "steps remove it, so there is nothing to re-install or pin")


def check_oxidized_helper(root: str = ROOT) -> dict:
    """Done: Oxidized is retired (`OXIDIZED_RETIRED`)."""
    return {"state": "done", "detail": OXIDIZED_RETIRED}


def check_oxidized_pin(root: str = ROOT) -> dict:
    """Done: Oxidized is retired (`OXIDIZED_RETIRED`)."""
    return {"state": "done", "detail": OXIDIZED_RETIRED}


def check_kea_reservation_files(root: str = ROOT, kea=None) -> dict:
    """C529 step 2's host step: done when every subnet Kea runs, in both families, takes its
    reservations from Mercury's file (`dhcp_subnets.reservation_files` finds none to add, read
    in the files' shape now: Kea's own before step 5's move, Mercury's subnet file after it).
    Kea is asked for its subnets; its files are read."""
    from modules import dhcp_reservations as D
    from modules import dhcp_subnets as S
    from modules.list_settings import DEFAULT_LIST

    if kea is None:
        from modules.integrations.kea import KeaIntegration
        kea = KeaIntegration()
    left = []
    for family in D.FAMILY:
        try:
            config = D.kea_config(kea, family)
            main = D.main_config(DEFAULT_LIST, family)
            with open(main, encoding="utf-8") as fh:
                text = fh.read()
        except (D.Refused, OSError) as exc:
            return {"state": "unknown", "detail": f"{family}: {exc}"}
        ids = [s.get("id") for s, _n in D._subnets(config, family)]     # noqa: SLF001
        plan = S.reservation_files(text, main, family, ids)
        if plan["refused"]:
            return {"state": "not_done", "detail": f"{family}: {plan['refused']}"}
        left += [f"{family} subnet {sid}" for sid in plan["add"]]
    if left:
        return {"state": "not_done", "detail": "still without Mercury's file: " + ", ".join(left)}
    return {"state": "done", "detail": "every subnet Kea runs takes its reservations from "
                                       "Mercury's file"}


def check_kea_subnet_files(root: str = ROOT) -> dict:
    """C529 step 5's host step: done when both families' Kea configuration takes its subnets
    from Mercury's file (`dhcp_subnets.move_plan` reads "done"). Kea's files are read."""
    from modules import dhcp_reservations as D
    from modules import dhcp_subnets as S
    from modules.list_settings import DEFAULT_LIST

    left = []
    for family in D.FAMILY:
        main = D.main_config(DEFAULT_LIST, family)
        try:
            with open(main, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            return {"state": "unknown", "detail": f"{family}: {main} could not be read: {exc}"}
        p = S.move_plan(text, main, family)
        if p["state"] == "refused":
            return {"state": "not_done", "detail": f"{family}: {p['refused']}"}
        if p["state"] != "done":
            left.append(f"{family} ({main})")
    if left:
        return {"state": "not_done", "detail": "subnets still in Kea's own file: " + ", ".join(left)}
    return {"state": "done", "detail": "both families' subnets come from Mercury's files"}


def check_kea_discovery_range(root: str = ROOT, kea=None, addrs=None) -> dict:
    """Board L's host step: done when Kea RUNS the discovery range (`dhcp_discovery.running`
    reads "on": both confined classes and both pools in the ZTP subnet). Kea is asked."""
    from modules import dhcp_discovery as L
    from modules import dhcp_reservations as D

    if kea is None:
        from modules.integrations.kea import KeaIntegration
        kea = KeaIntegration()
    try:
        r = L.running(D.kea_config(kea, "IPv4"), addrs)
    except D.Refused as exc:
        return {"state": "unknown", "detail": f"IPv4: {exc}"}
    if r["state"] == "on":
        return {"state": "done", "detail": f"Kea runs the discovery range in the ZTP subnet "
                                           f"{r['prefix']}: " + ", ".join(
                                               p["pool"] for p in r["pools"])}
    return {"state": "not_done", "detail": r["problem"] or "Kea runs no discovery range"}


CHECKS = {"topology-renderer": check_topology_renderer, "updater": check_updater,
          "oxidized-cred": check_oxidized_helper, "oxidized-pin": check_oxidized_pin,
          "kea-reservation-files": check_kea_reservation_files,
          "kea-subnet-files": check_kea_subnet_files,
          "kea-discovery-range": check_kea_discovery_range}


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


#: A check a PUSHED commit named that does not test what its step did, corrected by commit:
#: history is never rewritten, so the correction lives here, with its reason (C443, the
#: operator, 2026-10-04: a step must be checked by what THAT step did).
CHECK_CORRECTIONS = {
    "487b1dafcd189b48ecff0121272ec591cfff09b0": (
        "oxidized-pin",
        "its step pinned the helper to a router.db; it named [oxidized-cred], the helper's "
        "hash, so every later helper release reopened it. Its re-install half is superseded "
        "by each later [oxidized-cred] step"),
}


def steps_in(text: str, when: str = None) -> list:
    """[{sha, step, check, when, id}] from `git log` output, oldest first. A step whose
    commit's check is corrected (`CHECK_CORRECTIONS`) carries the corrected one, and
    ``check_corrected`` says why."""
    out = []
    for chunk in reversed(text.split("\x1e")):
        sha, _sep, body = chunk.strip().partition("\x1f")
        for s in parse(body):
            if when is None or s["when"] == when:
                fix = CHECK_CORRECTIONS.get(sha)
                if fix and s["check"]:
                    s = dict(s, check=fix[0], check_corrected=fix[1])
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
    """One row per ARTIFACT, naming every commit that asked for it.

    A checked step is keyed on its CHECK alone (C442, the operator, 2026-10-04: three
    `[oxidized-cred]` re-installs, each worded differently, were three rows cleared by one
    install). The check tests one artifact as it is now, so the NEWEST step's words lead, and
    the older steps are ``superseded`` by it: doing the newest does each. An unchecked step is
    keyed on its words (2026-10-01: one re-install listed for 4a61081 and dde8495), and keeps
    the first commit's ``sha`` and ``id`` (a person's "It is done" is recorded against it).
    ``shas``/``ids`` hold every commit, oldest first."""
    out, by = [], {}
    for s in steps:
        key = ("check", s["check"]) if s.get("check") else ("step", s["step"])
        if key not in by:
            by[key] = dict(s, shas=[], ids=[], superseded=[])
            out.append(by[key])
        g = by[key]
        if key[0] == "check" and g["shas"]:
            g.update(step=s["step"], sha=s["sha"], id=s["id"], when=s["when"])
        g["shas"].append(s["sha"])
        g["ids"].append(s["id"])
        if key[0] == "check":
            g["superseded"] = g["shas"][:-1]
    return out
