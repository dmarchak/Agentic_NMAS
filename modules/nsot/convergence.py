"""nsot/convergence.py

Settle windows for post-deploy verification.

Verifying immediately after a config change produces spurious failures: routing
protocols have not re-converged yet. RIP sends updates every 30 seconds, so a
RIP neighbour check run two seconds after a change reliably reports a drop that
is not real. OSPF adjacency comes up in seconds; BGP sits in between.

So verification **polls within a per-protocol window** and distinguishes three
outcomes, which the old immediate-poll design could not:

* ``converged``          — the check passed
* ``not_yet_converged``  — still unsettled when the window expired. Not the same
                           as a failure: the change may be fine and simply slow.
* ``failed``             — the check regressed and stayed regressed

Reporting "not yet converged" as a failure is what makes an operator distrust
the verifier and start skipping it, which is worse than not having one.
"""

import logging
import time

log = logging.getLogger(__name__)

CONVERGED = "converged"
NOT_YET = "not_yet_converged"
FAILED = "failed"
SKIPPED = "skipped"

#: Per-check timing, in seconds. ``initial_wait`` is a pause before the first
#: poll; ``timeout`` is the total window; ``interval`` is the gap between polls.
#:
#: RIP's window spans more than two 30-second update cycles, because a single
#: missed cycle is normal and two consecutive ones are not.
DEFAULT_WINDOWS = {
    "ospf":       {"initial_wait": 5,  "timeout": 45,  "interval": 5},
    "rip":        {"initial_wait": 15, "timeout": 90,  "interval": 15},
    "bgp":        {"initial_wait": 10, "timeout": 60,  "interval": 10},
    "eigrp":      {"initial_wait": 5,  "timeout": 45,  "interval": 5},
    "isis":       {"initial_wait": 5,  "timeout": 45,  "interval": 5},
    "interfaces": {"initial_wait": 2,  "timeout": 20,  "interval": 4},
    # The route table settles AFTER its protocols, so it gets the longest
    # protocol window (RIP's). C115: the route check now runs on deploys.
    "routes":     {"initial_wait": 5,  "timeout": 90,  "interval": 15},
    "default":    {"initial_wait": 5,  "timeout": 45,  "interval": 5},
}


def window_for(check: str) -> dict:
    """Timing for *check*, from settings with the built-in default as fallback."""
    try:
        from modules.settings_schema import get_setting
        configured = get_setting("verify_settle_windows", {}) or {}
    except Exception:                          # noqa: BLE001
        configured = {}
    base = dict(DEFAULT_WINDOWS.get(check, DEFAULT_WINDOWS["default"]))
    base.update({k: v for k, v in (configured.get(check) or {}).items()
                 if isinstance(v, int) and v >= 0})
    return base


#: Consecutive probe errors before giving up early. A device that cannot be
#: reached after a deploy is a failure *now* — waiting out a 90-second RIP
#: window to say so is just a slow way to report the same thing.
MAX_CONSECUTIVE_ERRORS = 3


def wait_for(check: str, probe, is_converged, sleep=time.sleep,
             max_consecutive_errors: int = MAX_CONSECUTIVE_ERRORS) -> dict:
    """Poll *probe* until *is_converged* or the window expires.

    ``probe()`` returns the current observation; ``is_converged(observation)``
    says whether it is settled. Neither is called before ``initial_wait``
    elapses, because the first poll after a change is the one most likely to be
    misleading.

    A probe that raises repeatedly short-circuits: an unreachable device is a
    result, not something to wait out.

    Returns ``{"state", "attempts", "elapsed", "observation", "window"}``.
    """
    timing = window_for(check)
    deadline = timing["timeout"]
    started = 0.0
    attempts = 0
    observation = None
    last_error = ""

    if timing["initial_wait"]:
        sleep(timing["initial_wait"])
        started += timing["initial_wait"]

    consecutive_errors = 0
    while True:
        attempts += 1
        try:
            observation = probe()
            consecutive_errors = 0
            if is_converged(observation):
                log.info("convergence[%s]: converged after %.0fs (%d poll(s))",
                         check, started, attempts)
                return {"state": CONVERGED, "attempts": attempts,
                        "elapsed": started, "observation": observation,
                        "window": timing}
        except Exception as exc:               # noqa: BLE001
            last_error = str(exc)
            consecutive_errors += 1
            log.debug("convergence[%s]: probe error (%d consecutive): %s",
                      check, consecutive_errors, exc)
            if consecutive_errors >= max_consecutive_errors:
                log.warning("convergence[%s]: giving up after %d consecutive "
                            "probe errors: %s", check, consecutive_errors, last_error)
                return {"state": FAILED, "attempts": attempts, "elapsed": started,
                        "observation": observation, "window": timing,
                        "error": last_error}

        if started >= deadline:
            break
        sleep(timing["interval"])
        started += timing["interval"]

    log.info("convergence[%s]: not settled within %ss (%d poll(s))",
             check, deadline, attempts)
    return {"state": NOT_YET, "attempts": attempts, "elapsed": started,
            "observation": observation, "window": timing, "error": last_error}


#: IOS's BGP hold time when nothing configures one (keepalive 60, hold 180).
IOS_BGP_DEFAULT_HOLD = 180


def bgp_hold_times(config: str) -> dict:
    """``{"peers": {neighbor: {"hold", "basis"}}, "max", "basis"}`` from a
    running config: each BGP neighbor's CONFIGURED hold time (C178).

    Why a hold time matters: IOS keeps a session up until its hold timer
    expires, so a change that breaks BGP without resetting the TCP session at
    once (a filter on TCP 179, a lost route to a multihop peer) reads
    Established for up to the hold time. A reading taken before that could
    not have shown the failure, and is not evidence that there was none.

    Precedence, as IOS applies it: ``neighbor X timers K H``, then the
    neighbor's peer-group's, then ``timers bgp K H`` for the process, then
    IOS's default. The NEGOTIATED hold time is the lower of both sides', and
    this reads only ours, so it is an UPPER BOUND: waiting it out is
    conservative, never short. Each peer names which basis applied."""
    import re as _re

    in_bgp, neighbors, groups, member_of = False, set(), {}, {}
    per_nbr, process = {}, None
    for raw in (config or "").splitlines():
        if not raw.strip() or raw.strip() == "!":
            continue
        if not raw.startswith(" "):
            in_bgp = raw.startswith("router bgp ")
            continue
        if not in_bgp:
            continue
        line = raw.strip()
        m = _re.match(r"timers bgp \d+ (\d+)", line)
        if m:
            process = int(m.group(1))
            continue
        m = _re.match(r"neighbor (\S+) (.*)$", line)
        if not m:
            continue
        nbr, rest = m.group(1), m.group(2)
        if rest == "peer-group":
            groups.setdefault(nbr, None)
            continue
        t = _re.match(r"timers \d+ (\d+)", rest)
        if t:
            per_nbr[nbr] = int(t.group(1))
            continue
        g = _re.match(r"peer-group (\S+)$", rest)
        if g:
            member_of[nbr] = g.group(1)
        if rest.startswith("remote-as ") or g:
            neighbors.add(nbr)
    peers = {}
    for nbr in sorted(neighbors - set(groups)):
        group = member_of.get(nbr)
        if nbr in per_nbr:
            peers[nbr] = {"hold": per_nbr[nbr], "basis": f"neighbor {nbr} timers"}
        elif group and group in per_nbr:
            peers[nbr] = {"hold": per_nbr[group], "basis": f"peer-group {group} timers"}
        elif process is not None:
            peers[nbr] = {"hold": process, "basis": "timers bgp"}
        else:
            peers[nbr] = {"hold": IOS_BGP_DEFAULT_HOLD,
                          "basis": f"IOS default {IOS_BGP_DEFAULT_HOLD} s (no timers configured)"}
    if not peers:
        return {"peers": {}, "max": 0, "basis": "no BGP neighbor in the configuration"}
    top = max(peers.values(), key=lambda p: p["hold"])
    return {"peers": peers, "max": top["hold"], "basis": top["basis"]}


def classify(pre_count: int, post_count: int, settled: bool) -> str:
    """Turn a neighbour-count comparison into a verification state.

    A count that recovered is converged. A count still short when the window
    expired is *not yet converged* — reported distinctly from a failure,
    because on a slow protocol it very often is not one.
    """
    if pre_count < 0 or post_count < 0:
        return SKIPPED                          # no protocol detected
    if post_count >= pre_count:
        return CONVERGED
    return FAILED if settled else NOT_YET


def summarise(results: dict) -> dict:
    """Aggregate per-check states into a device-level verdict."""
    states = list(results.values())
    return {
        "checks": results,
        "failed": [k for k, v in results.items() if v == FAILED],
        "not_yet_converged": [k for k, v in results.items() if v == NOT_YET],
        "converged": [k for k, v in results.items() if v == CONVERGED],
        "skipped": [k for k, v in results.items() if v == SKIPPED],
        # A device only *fails* verification on a genuine regression. Something
        # still converging is surfaced, not counted against the deploy.
        "ok": not any(s == FAILED for s in states),
        "pending": any(s == NOT_YET for s in states),
    }
