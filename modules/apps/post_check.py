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

**Each switch's time is counted from the restart (the board's K8, C2708).** The post-check
starts after the apply script has waited for the unit, so its own first read is already that
long after the restart. `restart_origin` places the restart on the post-check's clock: the
moment the apply's outcome was read back, less the unit's time to active the outcome reports
(the script's `up_after_s`). `wait(restart=...)` then draws each switch "back N s after the
restart" (`after_restart`), the post-check's own time to it plus the unit's time to active and
the time between the outcome and the first read. Those times still read short by what the
outcome does not report: the `systemctl restart` call's own time (the script starts its clock
when the call returns) and the outcome's way back (its write and the session's read). With no
origin (no outcome, or one without `up_after_s`, as when the unit did not come up) the result
says the restart's time is not known and counts from its first read, never silently. The bound
still runs on the post-check's own time, as before. `deploy` takes each origin from the apply
that restarted the unit (the deploy's, then the rollback's), read the moment its outcome came
back.

**The deploy (`deploy`)**, with the channel injected (the transport is not built): declare the
planned-restart window (the controller, with the switches as expected to drop), stage, apply,
post-check. What it post-checks and what a rollback sends are the confirmed plan's, nothing
else: its ``expected`` and its ``rollback`` (`channel.rollback_target`), both in its hash
(C2706); a rollback request whose hash is not the plan's refuses the deploy before the window
(`rollback_refusal`). A rollback runs on a post-check miss AND on an apply that failed after
the script wrote the new drop-in (C2705: `landed` reads the script's outcome's step, so
rollback undoes what LANDED; a failure before the write rolls nothing back, and an outcome not
read is "unknown", K7, never rolled back by itself). It is the previous request, or on a first
deploy the second request kind, the put-back of the drop-in before (decision K3), then a
second post-check on what the target runs. The receipt's outcome is
one of "deployed", "rolled back", "rollback failed" (a rollback was tried and did not get
there), "not rolled back" (none could be tried: no previous request and no drop-in before;
C2709), "apply failed" (nothing landed), "unknown" or "refused". Nothing here dials a host.

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


def _number(value):
    """*value* as a float, or None (a bool or text is not a number)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _seconds(value):
    """*value* as a non-negative number of seconds, or None."""
    got = _number(value)
    return got if got is not None and got >= 0 else None


def restart_origin(outcome, *, read_at) -> dict:
    """When the apply script's restart was, on the post-check's clock (K8, C2708).

    *outcome*: the apply's answer, the script's outcome or the transport's result holding it
    under ``"outcome"``; *read_at*: the post-check's clock (`wait`'s *clock*) when that answer
    came back. ``{"known", "at", "up_after_s", "words"}``: *at* is *read_at* less the unit's
    time to active (the outcome's ``up_after_s``), or None with *words* saying why it is not
    known."""
    got = outcome if isinstance(outcome, dict) else {}
    inner = got.get("outcome")
    if isinstance(inner, dict):
        got = inner
    up, when = _seconds(got.get("up_after_s")), _number(read_at)
    if up is None or when is None:
        if not outcome:
            why = "no apply outcome was read"
        elif up is None:
            why = (f"the apply outcome reports no time to active (its up_after_s is "
                   f"{got.get('up_after_s')!r}; the script reports it only once the unit is "
                   "active with a new MainPID)")
        else:
            why = f"the moment its outcome was read back is not given (read_at {read_at!r})"
        return {"known": False, "at": None, "up_after_s": up,
                "words": f"the restart's time is not known: {why}"}
    return {"known": True, "at": when - up, "up_after_s": round(up, 1),
            "words": (f"counted from the apply script's restart: the unit was active {up:g} s "
                      "after `systemctl restart` returned (the apply outcome's up_after_s), "
                      "and the times read short by the restart call's own time and the "
                      "outcome's way back, which the outcome does not report")}


def wait(read, expected: dict, *, restart=None, clock=time.monotonic, sleep=time.sleep,
         poll_s: float = POLL_S) -> dict:
    """Poll *read()* until `evaluate` passes or the bound passes. *restart*: `restart_origin`'s
    answer, on this *clock*; None is "not known". ``{"ok", "polls", "elapsed_s", "bound",
    "last", "origin", "came_back": {dpid: seconds after the first read}, "after_restart":
    {dpid: seconds after the restart} or None, "after_restart_s", "words"}``: the times drawn
    are *after_restart*'s; with the origin unknown it is None and the words say so."""
    limit = bound()
    origin = restart if isinstance(restart, dict) else {}
    known = origin.get("known") is True and _number(origin.get("at")) is not None
    if not known:
        origin = {"known": False, "at": None, "up_after_s": origin.get("up_after_s"),
                  "words": origin.get("words") or ("the restart's time is not known: no "
                                                   "restart origin was given")}
    start, polls, came_back, after, last = clock(), 0, {}, ({} if known else None), None
    while True:
        polls += 1
        observed = read()
        last = evaluate(expected, observed)
        at = clock()
        elapsed = at - start
        since = at - origin["at"] if known else None
        sw = observed.get("switches") or {}
        if sw.get("ok"):
            for s in sw.get("switches") or []:
                if s["dpid"] in (expected.get("switches") or []):
                    came_back.setdefault(s["dpid"], round(elapsed, 1))
                    if known:
                        after.setdefault(s["dpid"], round(since, 1))
        own = round(elapsed, 1)
        restart_words = (f"{round(since, 1)} s after the restart" if known else
                         f"counted from its first read: {origin['words']}")
        out = {"polls": polls, "elapsed_s": own, "bound": limit, "last": last,
               "origin": origin, "came_back": came_back, "after_restart": after,
               "after_restart_s": round(since, 1) if known else None}
        if last["ok"]:
            back = (f"back {round(since, 1)} s after the restart ({own} s and {polls} reads of "
                    "the post-check's own)" if known else
                    f"back after {own} s and {polls} reads of the post-check's own, "
                    f"{restart_words}")
            return dict(out, ok=True, words=(
                f"every expected switch, link and app's /health was {back}; the bound is "
                f"{limit['words']}"))
        if elapsed >= limit["seconds"]:
            return dict(out, ok=False, words=(
                f"the post-check's bound fired after {own} s and {polls} reads of the "
                f"switches, the links and every enabled app's /health ({restart_words}): "
                f"{miss_words(last)}. The bound runs on the post-check's own time and is "
                f"{limit['words']}"))
        sleep(poll_s)


def rollback_refusal(plan: dict) -> str:
    """"" or why the plan's rollback target (`channel.rollback_target`, in the plan's hash by
    its kind and hashes) is not the request it says it is: the request a rollback would send is
    recomputed by the script's hash and compared with the hashed one, and a put-back's binding
    with the drop-in before, each naming both."""
    from modules.apps import channel

    s = channel.script()
    target = plan.get("rollback")
    if not isinstance(target, dict) or target.get("kind") not in ("request", "dropin_before"):
        return (f"the plan's rollback target is {target!r}, not a rollback_target answer, so "
                "what a miss rolls back to is not known")
    req = target.get("request")
    if req is None:
        if target["kind"] == "request":
            return "the plan's rollback target is a recorded request with no request"
        return ""
    got = s.request_sha256(req)
    if got != target.get("request_sha256"):
        return (f"the rollback request's hash is {got}, and the plan hashed "
                f"{target.get('request_sha256')!r}")
    if target["kind"] == "dropin_before" and req.get("before_sha256") != target.get(
            "dropin_sha256"):
        return (f"the put-back is bound to the drop-in {req.get('before_sha256')!r}, and the plan "
                f"read the drop-in before as {target.get('dropin_sha256')!r}")
    return ""


def _hash_refusal(plan: dict) -> str:
    """"" or why *plan*'s hash, recomputed from what it carries (`channel.plan_hash`), is not
    the hash it was confirmed by, naming both."""
    from modules.apps import channel

    try:
        got = channel.plan_hash(plan)
    except (KeyError, TypeError) as exc:
        return f"the plan lacks what its hash binds ({type(exc).__name__}: {exc})"
    if got != plan.get("plan_sha256"):
        return (f"the plan's hash, recomputed from the request, the drop-in, the expected "
                f"switches, links and apps and the rollback target it carries, is {got}, and "
                f"it was confirmed as {plan.get('plan_sha256')!r}")
    return ""


def deploy(plan: dict, *, channel, read, declare_window, by: str, clock=time.monotonic,
           sleep=time.sleep, now=time.time) -> dict:
    """Run an accepted *plan* (`channel.plan`'s, ok, as confirmed by its hash) through
    *channel* (``stage(request)`` and ``apply()`` answering the script's outcome, or ``{"ok":
    False, "unknown": True, "error"}`` when this run's outcome could not be read), post-check
    with *read* against the plan's ``expected`` (the one the hash binds, C2706), and on a miss,
    or an apply that failed after the drop-in was written (`landed`), roll back to the plan's
    ``rollback`` (`channel.rollback_target`: the request the controller ran before, or the
    put-back of the drop-in before) and post-check again. What is post-checked and what a
    rollback sends come from the plan alone; the previous request reaches the plan from its
    caller (`channel.plan`'s *previous*) until the receipt store holds it (C2677). Each
    post-check counts every switch's time from its restart (`restart_origin` of the apply's
    outcome, K8). *declare_window(devices, start, end, by, why, unreachable)* is the
    planned-restart record (`restarts.record_planned`), declared before anything is staged.
    Returns the receipt."""
    receipt = {"plan_sha256": plan.get("plan_sha256"), "by": by, "steps": [],
               "outcome": "refused"}

    def step(name, **fields):
        receipt["steps"].append(dict({"step": name, "at": round(now(), 3)}, **fields))

    if not plan.get("ok"):
        receipt["error"] = "the plan was refused: " + "; ".join(plan.get("refusals") or [])
        return receipt
    why = rollback_refusal(plan) or _hash_refusal(plan)
    if why:
        receipt["error"] = f"refused before the window, nothing staged: {why}"
        return receipt
    expected = plan["expected"]
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
        receipt["apply"] = applied
        said = applied.get("refused") or applied.get("error") or ""
        what = landed(applied)
        receipt["landed"] = what
        if what == "nothing":
            receipt.update(outcome="apply failed", error=said)
            return receipt
        if what == "unknown":
            # K7: whether the script ran is not known; a rollback is offered, never run.
            receipt.update(outcome="unknown", error=said)
            return receipt
        why = f"the apply failed after the new drop-in was written ({said})"
    else:
        origin = restart_origin(applied, read_at=clock())
        check = wait(read, expected, restart=origin, clock=clock, sleep=sleep)
        step("post-check", ok=check["ok"], words=check["words"])
        receipt["post_check"] = check
        if check["ok"]:
            receipt["outcome"] = "deployed"
            return receipt
        why = f"the post-check missed ({check['words']})"
    return _roll_back(receipt, why, plan=plan, channel=channel, read=read, step=step,
                      clock=clock, sleep=sleep)


#: The script's outcome steps past its write of the new drop-in (the apply script's "What
#: landed, in the outcome"): a failure at any of them left the new drop-in on the controller.
WROTE_DROPIN = ("daemon-reload", "restart", "wait", "after-write", "running")


def landed(outcome: dict) -> str:
    """What a failed apply left on the controller, read from the script's *outcome*: "nothing"
    (a refusal, or an exception before mercury.conf was replaced: the script's outcome then has
    no step), "dropin" (the new drop-in written, and maybe the unit restarted: a step of
    `WROTE_DROPIN`), or "unknown" (the channel could not read this run's outcome: its
    ``unknown`` is true, or the outcome names a step the script does not write). The
    transport's own answer (`transport.send`) counts too: ``command_sent`` false is "nothing",
    since the one command was never sent; its steps after the command are not the script's,
    so they are "unknown"."""
    outcome = outcome or {}
    if outcome.get("unknown"):
        return "unknown"
    if outcome.get("command_sent") is False:
        return "nothing"
    if outcome.get("refused"):
        return "nothing"
    step = outcome.get("step")
    if step is None:
        return "nothing" if outcome.get("error") else "unknown"
    return "dropin" if step in WROTE_DROPIN else "unknown"


def _rollback_expected(expected: dict, target: dict) -> dict:
    """What the rollback's post-check waits for: the plan's switches and links, and the /health
    of the apps the rollback target runs (none of Mercury's after a put-back: the drop-in
    before runs the unit's own command line)."""
    if target["kind"] == "request":
        apps = [a["name"] for a in target["request"].get("apps") or []]
    else:
        apps = []
    return dict(expected, apps=apps)


def _roll_back(receipt, why, *, plan, channel, read, step, clock, sleep) -> dict:
    """The rollback after a miss or an apply that landed (C2705), to the plan's ``rollback``
    (`channel.rollback_target`, the one owner of what a rollback sends), and the receipt's
    outcome: "rolled back" (the rollback applied and its post-check passed), "rollback failed"
    (one was tried and did not get there) or "not rolled back" (none could be tried: no
    previous request and no drop-in before; C2709)."""
    target = plan["rollback"]
    receipt["rollback_target"] = target["kind"]
    if target.get("request") is None:
        receipt.update(outcome="not rolled back",
                       error=(f"{why}; {target['words']}, so no rollback was tried. The "
                              "controller runs what the deploy left"))
        return receipt
    what = "rollback apply" if target["kind"] == "request" else "rollback put-back"
    back = _apply(channel, target["request"], step, what=what)
    if not back.get("ok"):
        said = "put-back" if target["kind"] == "dropin_before" else "previous request"
        receipt.update(outcome="rollback failed", rollback_apply=back,
                       error=(f"{why}; the rollback ({said}) failed: "
                              f"{back.get('refused') or back.get('error') or 'not ok'}"))
        return receipt
    origin = restart_origin(back, read_at=clock())
    again = wait(read, _rollback_expected(plan["expected"], target), restart=origin,
                 clock=clock, sleep=sleep)
    step("rollback post-check", ok=again["ok"], words=again["words"])
    receipt["rollback_post_check"] = again
    receipt["outcome"] = "rolled back" if again["ok"] else "rollback failed"
    receipt["error"] = why if again["ok"] else (f"{why}; the rollback's post-check missed too "
                                                f"({again['words']})")
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
