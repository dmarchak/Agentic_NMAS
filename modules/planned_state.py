"""A device under a planned operation, in the one state every screen draws (PHASE8_PLAN 20.3;
board PS, approved 2026-11-01, C2274).

The attribution rule (20.2, `restarts.explained_by`) keeps a signal an operation explains off
Needs attention. This module says the same thing where people look: the device page's header,
Devices and Topology draw ONE amber state, linked to the operation, for

- a device an operation holds (`device_ops`): "Reloading · by <person> · step 4 of 6 (wait) ·
  back by ~01:12 UTC", its words the operation's (`STATE_WORDS`), its steps its card's stepper
  (`device_actions.job_steps`), "back by" its planned window's end when it declared one;
- a device inside a planned-restart window with no hold (a window a person or the lab's
  redeploy declared), while it is not answering: "Restarting as planned · by <person> · back
  by ~…" (one back inside its window answers, and is drawn so);
- a device the operation predicted Mercury loses its path to (the window's
  ``expected.unreachable``), only while it is NOT answering: "Unreachable as expected · edge1
  reloading · back by ~…", back by the window's end plus the settle time. One that answers is
  drawn as answering, never as an expectation that did not happen;

and red once a device is still not answering past that time, naming the operation it outlasted:
"Not answering · overdue after edge1's reload (back by 01:31 UTC)".

The same function the sources consult decides it (`restarts.window_end`, `SETTLE_SECONDS`, the
window's own and expected devices), never a second list. A READ: holds, windows and their ends
are read once per network (`read`), so a list of any size does no per-device work; `state`
answers one device from that.
"""

import logging
import time

log = logging.getLogger(__name__)

#: A held device's state, in the operation's words (board PS's decision 1). Every operation
#: `device_ops.OPERATION_WORDS` names is here or in `READS`, so a new operation is placed
#: before it is drawn (tests/test_planned_state.py).
STATE_WORDS = {
    "reload": "Reloading", "deploy": "Deploying", "restore": "Restoring",
    "rotate": "Rotating its credential", "onboard": "Onboarding", "persist": "Persisting",
    "retire": "Retiring", "save": "Saving (write memory)", "command": "Running a command",
    "bulk": "Changing by a bulk operation", "file": "Changing by a file action",
    "probe": "Probing removal shapes",
    "port bounce": "Bouncing a port (self-healing)",
    "session clear": "Clearing a BGP neighbour (self-healing)",
    "monitoring profile apply": "Applying its monitoring profile",
    "IP SLA send": "Sending its IP SLA probes",
    "monitoring templates deploy": "Sending its monitoring templates",
    "console kick-start": "Kick-starting over its console",
    "console onboard": "Onboarding over its console",
    "sdn flows": "Changing its flows",
    "controller app deploy": "Deploying its controller apps",
}
#: Holds that only read the device: it is not under an operation a person should wait for,
#: and a read lasts seconds, so its row draws as it always did.
READS = ("read", "capture", "console survey")

#: A window's operation (its ``via``) as the predicted device's words name it: "edge1
#: reloading", "overdue after edge1's reload". Any other window is a planned restart.
VIA_WORDS = {"reload": ("reloading", "reload")}
PLANNED_WORDS = ("restarting", "planned restart")

#: How far back a window that ended can still make a device overdue: a device down since
#: before the window ended is overdue after it until it answers, at most this long (the
#: restarts row's own horizon, `restarts.ATTENTION_DAYS`).
OVERDUE_DAYS = 7


def _clock(epoch: float) -> str:
    return time.strftime("%H:%M UTC", time.gmtime(epoch))


def read(list_name: str, now: float = None) -> dict:
    """What decides every device's state in *list_name* at *now*, read once:
    ``{"holds": {device: in-flight row}, "windows": [(window, end)], "error"}``. *windows*
    holds only those still open, or ended inside `OVERDUE_DAYS`. An unreadable store decides
    nothing (each device draws as it did) and is named in *error*."""
    from modules import restarts as R
    from modules.nsot import device_ops

    now = time.time() if now is None else now
    out = {"holds": {}, "windows": [], "error": ""}
    errors = []
    try:
        out["holds"] = {h.get("device", ""): h for h in device_ops.held(list_name)
                        if h.get("operation") not in READS}
    except OSError as exc:
        errors.append(f"what holds its devices could not be read ({exc})")
    try:
        ended = R.ends()
        for p in R.planned_rows():
            if p.get("list") and list_name and p.get("list") != list_name:
                continue
            end = R.window_end(p, ended)
            if R._epoch(p.get("from", "")) - 60 <= now and end >= now - OVERDUE_DAYS * 86400:
                out["windows"].append((p, end))
    except RuntimeError as exc:
        errors.append(f"its planned-restart windows could not be read ({exc})")
    out["error"] = "; ".join(errors)
    return out


def _own(p: dict, host: str, list_name: str) -> bool:
    from modules import restarts as R

    return R._names(p, host, list_name)


def _expects(p: dict, host: str) -> bool:
    return host in ((p.get("expected") or {}).get("unreachable") or [])


def _operating(p: dict) -> str:
    """The device a window's operation restarts, when it names one (its page opens the
    operation's card); "" for a window over several or a whole network."""
    names = [d for d in p.get("devices") or [] if d != "*"]
    return names[0] if len(names) == 1 and "*" not in (p.get("devices") or []) else ""


def _steps(hold: dict, list_name: str, host: str, now: float) -> str:
    """"step 4 of 6 (wait)" from the operation's card stepper, or "" when it draws none."""
    from modules import device_actions

    op = hold.get("operation", "")
    if op not in device_actions.JOB_STEPPERS:
        return ""
    try:
        rows = device_actions.job_steps(op, list_name, host, now=now, holder=hold)
    except Exception:                                 # noqa: BLE001 (drawn without its step)
        log.warning("planned_state: %s's steps could not be read", host, exc_info=True)
        return ""
    for i, s in enumerate(rows):
        if s.get("state") == "running":
            return f"step {i + 1} of {len(rows)} ({s['key']})"
    return ""


def state(ctx: dict, host: str, list_name: str, reach: dict = None, now: float = None):
    """*host*'s planned state from *ctx* (`read`) and its reachability row *reach*
    (``{"answering", "since"}``, or None when not probed), or None when no operation explains
    it. ``{"level": "plan"|"danger", "parts": [...], "words", "short", "tag", "title",
    "link"}``: *words* the header's, *short* a list row's (no person), *tag* the map's;
    *link* the device whose page opens the operation's card, or ""."""
    from modules import restarts as R

    now = time.time() if now is None else now
    hold = ctx["holds"].get(host)
    windows = ctx["windows"]
    margin = R.SETTLE_SECONDS
    # The window's own device until its end, a predicted one until its end and the settle
    # time: the reachability source's own two holds (`attention._planned_down`), so the state
    # and Needs attention change at the same moment.
    open_own = next(((p, end) for p, end in reversed(windows)
                     if _own(p, host, list_name) and now <= end), None)
    if hold:
        op = hold.get("operation", "")
        lead = STATE_WORDS.get(op) or op[:1].upper() + op[1:]
        step = _steps(hold, list_name, host, now)
        back = f"back by ~{_clock(open_own[1])}" if open_own else ""
        parts = [lead, f"by {hold.get('actor') or 'an unrecorded person'}", step, back]
        return _drawn("plan", parts, lead, back, host,
                      f"{lead}, by {hold.get('actor') or 'an unrecorded person'}: its card is "
                      f"on {host}'s page")
    answering = bool((reach or {}).get("answering"))
    # A device back inside its window answers, and is drawn so (the device page's B3 rule).
    if open_own and not answering:
        p, end = open_own
        back = f"back by ~{_clock(end)}"
        parts = ["Restarting as planned", f"by {p.get('by') or 'an unrecorded person'}", back]
        return _drawn("plan", parts, "Restarting as planned", back, _operating(p),
                      f"Inside the planned-restart window {p.get('why') or ''}: Needs "
                      "attention raises it only if it is still down when the window and its "
                      "settle time end")
    if reach is None or answering:
        return None
    for p, end in reversed(windows):
        if not _expects(p, host) or _own(p, host, list_name):
            continue
        doing, noun = VIA_WORDS.get(p.get("via", ""), PLANNED_WORDS)
        who = ", ".join(d for d in p.get("devices") or [] if d != "*") or "the network"
        back_at = end + margin
        if now <= back_at:
            back = f"back by ~{_clock(back_at)}"
            parts = ["Unreachable as expected", f"{who} {doing}", back]
            return _drawn("plan", parts, "Unreachable as expected", back, _operating(p),
                          f"The {noun} of {who} predicted Mercury loses its path to {host} "
                          "while it runs")
    since = R._epoch((reach or {}).get("since") or "") or now
    for p, end in reversed(windows):
        own = _own(p, host, list_name)
        if not (own or _expects(p, host)):
            continue
        back_at = end if own else end + margin
        if since <= back_at < now:
            _doing, noun = VIA_WORDS.get(p.get("via", ""), PLANNED_WORDS)
            who = ", ".join(d for d in p.get("devices") or [] if d != "*") or "the network"
            owner = f"its {noun}" if own else f"{who}'s {noun}"
            words = f"overdue after {owner} (back by {_clock(back_at)})"
            return _drawn("danger", ["Not answering", words], "Not answering", words,
                          _operating(p), f"Still not answering past the {noun}'s window"
                                         + ("" if own else f" and its settle time "
                                                           f"({margin // 60} min)"))
    return None


# ---------------------------------------------------------------------------
# The operation's card: its Expected effects (board PS, part 2)
# ---------------------------------------------------------------------------

#: The Needs attention sources that hold a signal for a planned window (PHASE8_PLAN 20.2), each
#: returning what it held as `held` (`attention._held`): the card reads THEIR decisions, never
#: a second list (board PS's decision 4).
HOLDING = ("drift_source", "grafana_source", "reachability_source", "adjacency_source",
           "adjacency_log_source")
#: What predicted each held signal, as the card's second column says it.
PREDICTED_BY = {"reachability": {"restarting": "the operation's own device",
                                 "unreachable": "the preview's What else goes down"},
                "adjacencies": "an adjacency with the device at one end",
                "adjacency_log": {"restarting": "the logging device's window",
                                  "peer": "the peer's window"},
                "drift": "the window (read again by the next run)"}
ALERTS_PREDICTED = "the window and its settle time"


def window_of(host: str, list_name: str, via: str = "reload", since: str = ""):
    """The newest planned window *host* of *list_name* declared through *via* (its own
    operation's), starting at or after *since* when given; None when there is none or the
    record cannot be read."""
    from modules import restarts as R

    try:
        rows = R.planned_rows()
    except RuntimeError:
        return None
    for p in reversed(rows):
        if (p.get("via") == via and host in (p.get("devices") or [])
                and (not p.get("list") or not list_name or p.get("list") == list_name)
                and (not since or R._epoch(p.get("from", "")) >= R._epoch(since) - 1)):
            return p
    return None


def _predicted_by(entry: dict) -> str:
    words = PREDICTED_BY.get(entry["source"].split("@")[0])
    if words is None:
        return ALERTS_PREDICTED
    return words.get(entry.get("how"), "the window") if isinstance(words, dict) else words


def expected_effects(window: dict, list_name: str, now: float = None, sources=None) -> dict:
    """Board PS's part of an operation's card, for planned *window*: ``{"effects", "unexpected",
    "overdue", "errors", "back_by"}``.

    - *effects*: each signal a holding source held for this window now (its words, what
      predicted it, its devices, "expected back by"), and each device the preview predicted
      unreachable that no source holds now, drawn "answering" (it came back);
    - *unexpected*: each row the same sources raise now, begun since the window opened, naming
      no device in its scope (the window's devices and its predicted ones): raised as usual;
    - *overdue*: each row they raise now naming a device in its scope once its time has passed
      (the window's end for its own device, the end and the settle time for a predicted one).
    A source that cannot be read is named in *errors*, never drawn as no effect."""
    from modules import attention as A
    from modules import restarts as R

    now = time.time() if now is None else now
    wid = R.window_id(window)
    own = {d for d in window.get("devices") or [] if d != "*"}
    predicted = set((window.get("expected") or {}).get("unreachable") or [])
    scope = own | predicted
    start = R._epoch(window.get("from", ""))
    end = R.window_end(window, R.ends())
    srcs = sources if sources is not None else A._with_every_configuration(
        [getattr(A, n) for n in HOLDING])
    effects, raised, errors = [], [], []
    for src in srcs:
        try:
            res = src()
        except Exception as exc:                      # noqa: BLE001 (named on the card)
            errors.append(f"{getattr(src, '__name__', 'a source')}: {type(exc).__name__}: {exc}")
            continue
        if res.get("state") != "read":
            errors.append(f"{res.get('label')} could not be read")
            continue
        effects += [dict(h, predicted_by=_predicted_by(h), state="held")
                    for h in res.get("held") or [] if h.get("window") == wid]
        raised += [dict(r, source_label=res.get("label")) for r in res.get("rows") or []]
    held_devices = {d for e in effects if e["source"] == "reachability" for d in e["devices"]}
    reach_read = not any("Reachability" in e for e in errors)
    for d in sorted(predicted - held_devices):
        down = any(d in (r.get("devices") or []) for r in raised
                   if r.get("source") == "reachability")
        if reach_read and not down:
            effects.append({"source": "reachability", "window": wid, "devices": [d],
                            "what": f"{d} out of Mercury's reach",
                            "predicted_by": PREDICTED_BY["reachability"]["unreachable"],
                            "state": "answering", "back_by": ""})
    overdue, unexpected = [], []
    for r in raised:
        devs = set(r.get("devices") or [])
        if devs & scope:
            back_at = end if devs & own else end + R.SETTLE_SECONDS
            if now > back_at:
                overdue.append({"what": r.get("what"), "devices": sorted(devs),
                                "source": r.get("source_label"), "back_by": R._iso(back_at)})
        elif (r.get("since") or 0) >= start - 60:
            unexpected.append({"what": r.get("what"), "devices": sorted(devs),
                               "source": r.get("source_label"), "since": R._iso(r["since"])})
    effects.sort(key=lambda e: (e["state"] != "held", e["what"]))
    return {"effects": effects, "unexpected": unexpected, "overdue": overdue,
            "errors": errors, "back_by": R._iso(end + R.SETTLE_SECONDS)}


def _drawn(level: str, parts: list, lead: str, back: str, link: str, title: str) -> dict:
    parts = [p for p in parts if p]
    words = " · ".join(parts)
    return {"level": level, "parts": parts, "words": words,
            "short": " · ".join(p for p in parts if not p.startswith("by ")),
            "tag": " · ".join(p for p in (lead, back) if p), "title": title, "link": link}
