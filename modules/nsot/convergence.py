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


def wait_for(check: str, probe, is_converged, sleep=time.sleep) -> dict:
    """Poll *probe* until *is_converged* or the window expires.

    ``probe()`` returns the current observation; ``is_converged(observation)``
    says whether it is settled. Neither is called before ``initial_wait``
    elapses, because the first poll after a change is the one most likely to be
    misleading.

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

    while True:
        attempts += 1
        try:
            observation = probe()
            if is_converged(observation):
                log.info("convergence[%s]: converged after %.0fs (%d poll(s))",
                         check, started, attempts)
                return {"state": CONVERGED, "attempts": attempts,
                        "elapsed": started, "observation": observation,
                        "window": timing}
        except Exception as exc:               # noqa: BLE001
            last_error = str(exc)
            log.debug("convergence[%s]: probe error: %s", check, exc)

        if started >= deadline:
            break
        sleep(timing["interval"])
        started += timing["interval"]

    log.info("convergence[%s]: not settled within %ss (%d poll(s))",
             check, deadline, attempts)
    return {"state": NOT_YET, "attempts": attempts, "elapsed": started,
            "observation": observation, "window": timing, "error": last_error}


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
