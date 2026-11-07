"""A controller deploy's post-check, its rollback, and drift (the SDN platform design revision 6,
section 10 H: "Planned restart", "Drift"; P6).

**The bound (`bound`).** A Ryu deploy is a restart, so every switch reconnects. The post-check
waits for every expected switch, every expected link and every enabled app's `/health`, within
2.5 times the slowest switch's measured reconnect (CLAUDE.md: "Bounds are about 2.5x a measured
time"). **That
reconnect is NOT measured yet:** S1 (2026-11-10) reads every switch's reconnect after a controller
restart, the HP's 60 s backoff included. Until then `RECONNECT` holds the operator's figure,
90 s, marked unmeasured, and every result and refusal that names the bound names that it is a
placeholder. When S1's four times are written down, `RECONNECT` takes the slowest, measured.

**The post-check (`evaluate`, `wait`).** Each poll reads the controller (the caller's `read`):
the connected switches (DPIDs), the links (each an unordered pair of switch ports) and each
app's `/health`. An unreadable read neither passes nor fails a poll: it is said, and the
post-check goes on until the bound. A miss at the bound names what is missing, how many polls
ran, and the bound with its source.

**The deploy (`deploy`)**, with the channel injected (the transport is not built): declare the
planned-restart window (the controller, with the switches as expected to drop), stage, apply,
post-check; on a miss, the previous request is applied again and post-checked, and the receipt
says "rolled back" or "rollback failed", with what came back and when. Nothing here dials a host.

**Drift (`drift`).** The controller's service configuration (its drop-in and the command line
systemd holds) against the enabled set's request: each app the controller runs at a version
other than Mercury's record, each app missing or extra, and a drop-in other than the render, is
one line naming both sides and the action ("Preview the redeploy"). The running process's own
command line (its MainPID's) is not in the host capture list's reads, so drift reads what
systemd holds, and says so.
"""

import logging
import time

log = logging.getLogger(__name__)

#: The slowest switch's reconnect after a controller restart. A PLACEHOLDER until S1 measures it.
RECONNECT = {"seconds": 90, "measured": False,
             "source": ("the operator's figure, not measured: S1 (2026-11-10) measures every "
                        "switch's reconnect after a controller restart, the HP's 60 s backoff "
                        "included, and the slowest of the four times replaces it")}
FACTOR = 2.5
POLL_S = 5.0


def bound() -> dict:
    """``{"seconds", "measured", "source", "words"}``: the post-check's bound."""
    seconds = int(round(FACTOR * RECONNECT["seconds"]))
    kind = "measured" if RECONNECT["measured"] else "a placeholder"
    return {"seconds": seconds, "measured": RECONNECT["measured"], "source": RECONNECT["source"],
            "words": (f"{seconds} s, {FACTOR} times the slowest switch's reconnect of "
                      f"{RECONNECT['seconds']} s ({kind}: {RECONNECT['source']})")}


def _pair(link: dict) -> frozenset:
    return frozenset(((link["src"]["dpid"], link["src"]["port_no"]),
                      (link["dst"]["dpid"], link["dst"]["port_no"])))


def evaluate(expected: dict, observed: dict) -> dict:
    """One poll. *expected*: ``{"switches": [dpid], "links": [{"src", "dst"}], "apps": [name]}``;
    *observed*: ``{"switches": driver.switches(), "links": driver.links(), "health": {app:
    {"ok", "error"}}}``. ``{"ok", "missing_switches", "missing_links", "unhealthy",
    "unreadable"}``: ok only when every read answered and nothing is missing."""
    unreadable, missing_sw, missing_links, unhealthy = [], [], [], []
    sw = observed.get("switches") or {}
    if sw.get("ok"):
        have = {s["dpid"] for s in sw.get("switches") or []}
        missing_sw = [d for d in expected.get("switches") or [] if d not in have]
    else:
        unreadable.append(f"the switches ({sw.get('error') or 'no answer'})")
    links = observed.get("links") or {}
    if links.get("ok"):
        have = {_pair(link) for link in links.get("links") or []}
        missing_links = [link for link in expected.get("links") or [] if _pair(link) not in have]
    else:
        unreadable.append(f"the links ({links.get('error') or 'no answer'})")
    health = observed.get("health") or {}
    for app in expected.get("apps") or []:
        got = health.get(app)
        if got is None:
            unreadable.append(f"{app}'s /health (no answer)")
        elif not got.get("ok"):
            unhealthy.append(f"{app} ({got.get('error') or 'not OK'})")
    ok = not (unreadable or missing_sw or missing_links or unhealthy)
    return {"ok": ok, "missing_switches": missing_sw, "missing_links": missing_links,
            "unhealthy": unhealthy, "unreadable": unreadable}


def _link_words(link: dict) -> str:
    return (f"{link['src']['dpid']}:{link['src']['port_no']}-"
            f"{link['dst']['dpid']}:{link['dst']['port_no']}")


def miss_words(result: dict) -> str:
    parts = []
    if result["missing_switches"]:
        parts.append("switches not back: " + ", ".join(str(d) for d in result["missing_switches"]))
    if result["missing_links"]:
        parts.append("links not back: " + ", ".join(_link_words(x)
                                                     for x in result["missing_links"]))
    if result["unhealthy"]:
        parts.append("apps not healthy: " + ", ".join(result["unhealthy"]))
    if result["unreadable"]:
        parts.append("unreadable: " + ", ".join(result["unreadable"]))
    return "; ".join(parts) or "nothing missing"


def wait(read, expected: dict, *, clock=time.monotonic, sleep=time.sleep,
         poll_s: float = POLL_S) -> dict:
    """Poll *read()* until `evaluate` passes or the bound passes. ``{"ok", "polls", "elapsed_s",
    "bound", "last", "came_back": {dpid: seconds}, "words"}``."""
    limit = bound()
    start, polls, came_back, last = clock(), 0, {}, None
    while True:
        polls += 1
        observed = read()
        last = evaluate(expected, observed)
        elapsed = clock() - start
        sw = observed.get("switches") or {}
        if sw.get("ok"):
            for s in sw.get("switches") or []:
                if s["dpid"] in (expected.get("switches") or []):
                    came_back.setdefault(s["dpid"], round(elapsed, 1))
        if last["ok"]:
            return {"ok": True, "polls": polls, "elapsed_s": round(elapsed, 1), "bound": limit,
                    "last": last, "came_back": came_back,
                    "words": (f"every expected switch, link and app's /health was back after "
                              f"{round(elapsed, 1)} s ({polls} reads; the bound is "
                              f"{limit['words']})")}
        if elapsed >= limit["seconds"]:
            return {"ok": False, "polls": polls, "elapsed_s": round(elapsed, 1), "bound": limit,
                    "last": last, "came_back": came_back,
                    "words": (f"the post-check's bound fired after {round(elapsed, 1)} s and "
                              f"{polls} reads of the switches, the links and every enabled "
                              f"app's /health: {miss_words(last)}. The bound is "
                              f"{limit['words']}")}
        sleep(poll_s)


def deploy(plan: dict, *, previous: dict, channel, read, expected: dict, declare_window,
           by: str, clock=time.monotonic, sleep=time.sleep, now=time.time) -> dict:
    """Run an accepted *plan* (`channel.plan`'s, ok) through *channel* (``stage(request)`` and
    ``apply()`` answering the script's outcome), post-check with *read*, and on a miss apply
    *previous* (the request the controller ran before, or None when there was none) and
    post-check again. *declare_window(devices, start, end, by, why, unreachable)* is the
    planned-restart record (`restarts.record_planned`), declared before anything is staged.
    Returns the receipt."""
    receipt = {"plan_sha256": plan.get("plan_sha256"), "by": by, "steps": [],
               "outcome": "refused"}

    def step(name, **fields):
        receipt["steps"].append(dict({"step": name, "at": round(now(), 3)}, **fields))

    if not plan.get("ok"):
        receipt["error"] = "the plan was refused: " + "; ".join(plan.get("refusals") or [])
        return receipt
    start = now()
    win = plan["window"]
    got = declare_window(win["devices"], start, start + win["seconds"], by,
                         f"controller app deploy {plan.get('request_sha256', '')[:12]}",
                         win["unreachable"])
    if not got.get("ok"):
        receipt["error"] = ("the planned-restart window was not recorded, so nothing was staged: "
                            f"{got.get('error')}")
        return receipt
    step("window", seconds=win["seconds"])
    applied = _apply(channel, plan["request"], step)
    if not applied.get("ok"):
        receipt.update(outcome="apply failed", apply=applied,
                       error=applied.get("refused") or applied.get("error") or "")
        return receipt
    check = wait(read, expected, clock=clock, sleep=sleep)
    step("post-check", ok=check["ok"], words=check["words"])
    receipt["post_check"] = check
    if check["ok"]:
        receipt["outcome"] = "deployed"
        return receipt
    if previous is None:
        receipt.update(outcome="rollback failed",
                       error=("the post-check missed and no previous request is recorded to "
                              "roll back to; mercury.conf.prev on the controller is the "
                              "break-glass"))
        return receipt
    back = _apply(channel, previous, step, what="rollback apply")
    if not back.get("ok"):
        receipt.update(outcome="rollback failed", rollback_apply=back,
                       error=back.get("refused") or back.get("error") or "")
        return receipt
    again = wait(read, expected, clock=clock, sleep=sleep)
    step("rollback post-check", ok=again["ok"], words=again["words"])
    receipt["rollback_post_check"] = again
    receipt["outcome"] = "rolled back" if again["ok"] else "rollback failed"
    return receipt


def _apply(channel, req: dict, step, what: str = "apply") -> dict:
    try:
        channel.stage(req)
    except Exception as exc:                          # noqa: BLE001 (the receipt says it)
        out = {"ok": False, "error": f"staging failed ({type(exc).__name__}: {exc})"}
        step(f"{what}: stage", ok=False, error=out["error"])
        return out
    got = channel.apply() or {}
    step(what, ok=bool(got.get("ok")), main_pid_before=got.get("main_pid_before"),
         main_pid_after=got.get("main_pid_after"),
         error=got.get("refused") or got.get("error") or "")
    return got


def running_apps(argv, apps_root: str) -> dict:
    """``{name: version}`` of the managed apps on a ryu-manager command line *argv*."""
    out = {}
    prefix = apps_root.rstrip("/") + "/"
    for word in argv or []:
        if word.startswith(prefix) and word.endswith(".py"):
            parts = word[len(prefix):].split("/")
            if len(parts) == 3 and parts[2] == parts[0] + ".py":
                out[parts[0]] = parts[1]
    return out


def drift(req: dict, *, show_text: str, cat_text: str, unit: str) -> dict:
    """``{"state": "ok"|"drift"|"unreadable", "rows": [...], "read": words}`` for the
    controller's service configuration against the enabled set's request *req*."""
    from modules.apps import channel

    s = channel.script()
    shown = channel.parse_show(show_text)
    read = (f"what systemd holds for {unit} (`systemctl show -p User -p ExecStart {unit}`, "
            f"`systemctl cat {unit}`); the running process's own command line is not among the "
            "host's reads")
    if not shown["readable"]:
        return {"state": "unreadable", "rows": [f"{unit}'s command line cannot be read, so "
                                                "drift can't be told"], "read": read}
    want = {a["name"]: a["version"] for a in req["apps"]}
    have = running_apps(shown["argv"], s.APPS_ROOT)
    rows = []
    for name in sorted(set(want) | set(have)):
        if name not in have:
            rows.append(f"the controller does not run {name}; Mercury's record says "
                        f"{want[name]}; Preview the redeploy")
        elif name not in want:
            rows.append(f"the controller runs {name} {have[name]}, which Mercury's record does "
                        "not enable; Preview the redeploy")
        elif have[name] != want[name]:
            rows.append(f"the controller runs {name} {have[name]}; Mercury's record says "
                        f"{want[name]}; Preview the redeploy")
    if (shown["user"] or "") != s.RYU_USER:
        rows.append(f"{unit} runs as {shown['user']!r}, not {s.RYU_USER}; Preview the redeploy")
    rendered = channel.render_dropin(req, shown["exec_path"] or shown["argv"][0])
    if channel.dropin_before(cat_text, unit) != rendered:
        rows.append(f"{unit}'s drop-in is not the one Mercury's record renders; Preview the "
                    "redeploy")
    return {"state": "drift" if rows else "ok", "rows": rows, "read": read}
