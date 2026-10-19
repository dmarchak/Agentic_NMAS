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
import logging
import os
import re
import subprocess
import threading
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

#: Where the retired topology renderer was installed: a symlink to the checkout's copy, run by
#: its own unit. OBSERVE › Topology (the `topology-graph` reader) replaced it; the renderer
#: and its source went at 7.8 (2026-10-12), and `scripts/host-steps/topology-service-removal.sh`
#: removes what was installed.
TOPOLOGY_LINK = "/usr/local/bin/nmas-topology.py"
TOPOLOGY_SOURCE_REL = "deploy/topology/nmas-topology.py"
TOPOLOGY_UNIT = "nmas-topology.service"
TOPOLOGY_UNIT_FILE = "/etc/systemd/system/nmas-topology.service"


def check_topology_renderer_gone(root: str = ROOT, link: str = TOPOLOGY_LINK,
                                 unit_file: str = TOPOLOGY_UNIT_FILE) -> dict:
    """Done when neither the renderer's link nor its unit file is installed: the host step
    stopped and disabled the service, then removed both. A link that dangles (its source
    gone with the release) still counts as installed: `lexists`, never `exists`."""
    left = [p for p in (unit_file, link) if os.path.lexists(p)]
    if left:
        return {"state": "not_done", "detail": " and ".join(left) + (
            " is" if len(left) == 1 else " are") + " still installed; the topology service "
            "was retired (OBSERVE › Topology replaced it)"}
    return {"state": "done", "detail": f"neither {unit_file} nor {link} is installed"}


def check_device_label(root: str = ROOT, since=None) -> dict:
    """Done when Loki holds a line carrying the `device` label Alloy sets (C722's host step),
    measured as `device_logs.label_since`; unknown when Loki is not configured or could not
    say. *since*: that measurement, for tests."""
    from modules import device_logs
    from modules.integrations.loki import LokiIntegration

    if since is None:
        if not LokiIntegration().is_configured():
            return {"state": "unknown", "detail": "Loki is not configured here, so it cannot be "
                                                  "asked whether lines carry a device label"}
        since = device_logs.label_since()
    if since is None:
        return {"state": "not_done", "detail": "Loki holds no line with a device label in the "
                                               "last 30 days (or could not say)"}
    return {"state": "done", "detail": "Loki's first line with a device label arrived "
            + time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(since))}


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


#: How long Loki's answer to a label check is kept before it is asked again (C1246). Each ask
#: is a 30-day "first line" query Loki splits into about a thousand sub-queries (~1.8 s,
#: measured on the host 2026-10-18), and Needs attention runs the checks on every read (about
#: 0.34 a second there), which made Loki 2.2 cores busy and grew its log 58 MB a minute. A
#: found label stays found (a line that arrived stays arrived), so it is kept for the
#: process's life; "none" is re-asked after 5 minutes, the delay before a step just run reads
#: done; "unknown" after a minute, so a Loki that comes back is seen soon.
LOKI_NONE_SECONDS = 300
LOKI_UNKNOWN_SECONDS = 60
_LOKI_MEMO: dict = {}
_LOKI_MEMO_LOCK = threading.Lock()


def _clock() -> float:
    return time.monotonic()


def _loki_first(query: str, ask=None, now: float = None) -> dict:
    """Loki's first line matching *query* within its 30-day query limit: ``{"state": "found",
    "at": epoch}``, ``{"state": "none"}``, or ``{"state": "unknown", "why"}`` when Loki is not
    configured, did not answer, or answered something unreadable (never read as none). Asked of
    the configured Loki, the answer is kept (`LOKI_NONE_SECONDS`, C1246): a found one for good.
    *ask(query, start, end)* returns `LokiIntegration._get`'s answer, for tests, and is never
    kept."""
    if ask is not None:
        return _loki_ask(query, ask, now)
    with _LOKI_MEMO_LOCK:
        kept = _LOKI_MEMO.get(query)
        if kept and (kept[1] is None or _clock() < kept[1]):
            return kept[0]
    got = _loki_ask(query, None, now)
    hold = {"found": None, "none": LOKI_NONE_SECONDS}.get(got["state"], LOKI_UNKNOWN_SECONDS)
    with _LOKI_MEMO_LOCK:
        _LOKI_MEMO[query] = (got, None if hold is None else _clock() + hold)
    return got


def _loki_ask(query: str, ask=None, now: float = None) -> dict:
    """One ask of Loki (`_loki_first`'s, unkept)."""
    now = time.time() if now is None else now
    start, end = int((now - 30 * 86400) * 1e9), int(now * 1e9)
    if ask is None:
        from modules.integrations.loki import LokiIntegration

        loki = LokiIntegration()
        if not loki.is_configured():
            return {"state": "unknown", "why": "Loki is not configured here, so it cannot be "
                                               "asked"}
        r = loki._get("loki/api/v1/query_range", query=query, limit=1, start=start,  # noqa: SLF001
                      end=end, direction="forward")
    else:
        r = ask(query, start, end)
    if not r.get("ok"):
        return {"state": "unknown",
                "why": f"Loki did not answer: {r.get('error') or 'no reason given'}"}
    try:
        streams = (r["response"].json().get("data") or {}).get("result") or []
    except (ValueError, AttributeError) as exc:
        return {"state": "unknown", "why": f"Loki's answer could not be read: {exc}"}
    stamps = [int(ns) for s in streams for ns, _l in s.get("values") or []]
    return {"state": "found", "at": min(stamps) / 1e9} if stamps else {"state": "none"}


def _labelled(found: dict, what: str, missing: str) -> dict:
    if found["state"] == "unknown":
        return {"state": "unknown", "detail": found["why"]}
    if found["state"] == "none":
        return {"state": "not_done", "detail": missing}
    return {"state": "done", "detail": f"Loki's first {what} arrived "
            + time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(found["at"]))}


#: IBN decision 7's host step (scripts/host-steps/ibn7-severity-trap-label.sh): the labels Alloy
#: sets at ingest, each asked of Loki by the selector a reader of it would use.
SEVERITY_LABEL_QUERY = '{job="network_syslog", severity=~"[0-7]"}'
TRAP_LABEL_QUERY = '{job="snmptrapd", trap_oid=~".+"}'


def check_severity_label(root: str = ROOT, ask=None) -> dict:
    """Done when Loki holds a syslog line carrying the `severity` label (a digit 0 to 7) Alloy
    sets from the line's mnemonic; unknown when Loki is not configured or could not say."""
    return _labelled(_loki_first(SEVERITY_LABEL_QUERY, ask=ask),
                     "syslog line with a severity label",
                     "Loki holds no syslog line with a severity label in the last 30 days: run "
                     "scripts/host-steps/ibn7-severity-trap-label.sh on Mercury's host")


def check_trap_label(root: str = ROOT, ask=None) -> dict:
    """Done when Loki holds a trap with the stable `job="snmptrapd"` and a `trap_oid` label;
    not done until a trap arrives after the step (a link going down and up on an unused lab
    port sends two); unknown when Loki is not configured or could not say."""
    return _labelled(_loki_first(TRAP_LABEL_QUERY, ask=ask),
                     'trap with job="snmptrapd" and a trap_oid label',
                     'Loki holds no trap with job="snmptrapd" and a trap_oid label in the last '
                     "30 days: after ibn7-severity-trap-label.sh, the next trap proves it (a link "
                     "going down and up on an unused lab port sends two)")


CHECKS = {"topology-renderer-gone": check_topology_renderer_gone, "updater": check_updater,
          "device-label": check_device_label,
          "severity-label": check_severity_label, "trap-label": check_trap_label,
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

#: The done record's store on the records database (K31: one file for the installation).
STORE = "host_steps_done"


def done_records() -> dict:
    """{step id: row}; an unreadable record is said, never read as none. From its file or, once
    moved, the records database (K31)."""
    from modules import records_migrate

    got = records_migrate.store_rows(STORE, DONE)
    if got["state"] == "unreadable":
        return {"__unreadable__": {"error": got["error"]}}
    out = {}
    for row in got["rows"]:
        if "id" not in row:
            return {"__unreadable__": {"error": "KeyError: 'id' (a done row names no step)"}}
        out[row["id"]] = row
    return out


def record_done(sha: str, step: str, actor: str) -> dict:
    if not actor:
        return {"ok": False, "reason": "no verified person: a host step is said done by a person"}
    row = {"id": step_id(sha, step), "sha": sha, "step": step, "by": actor,
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    from modules import records_migrate

    records_migrate.store_append(STORE, DONE, row)
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
    answer or the person who said it done; and the steps already done, by a
    person (``said_done``) or by the tool's own check (``checked_done``, with
    the check's answer: C795, the operator, 2026-10-15: a step the check had
    passed vanished from the Update page, so a person could not see that it
    had been checked, or by what)."""
    try:
        text = log_text if log_text is not None else _log(root, running, HISTORY)
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        return {"ok": False, "steps": [], "error": str(exc)}
    done = done_records()
    if "__unreadable__" in done:
        return {"ok": False, "steps": [], "error": "the host-step record could not be read: "
                                                  + done["__unreadable__"]["error"]}
    out, said, checked = [], [], []
    for s in steps_in(text, when="after"):
        c = check(s, root)
        if c["state"] == "not_checkable" and s["id"] in done:
            said.append(dict(s, by=done[s["id"]].get("by"), at=done[s["id"]].get("at")))
            continue
        if c["state"] == "done":
            checked.append(dict(s, check_state="done", check_detail=c["detail"]))
            continue
        out.append(dict(s, check_state=c["state"], check_detail=c["detail"]))
    # The record read back: who said each step done, and when; and what the tool checked.
    return {"ok": True, "steps": grouped(out), "said_done": grouped(said),
            "checked_done": grouped(checked)}


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
