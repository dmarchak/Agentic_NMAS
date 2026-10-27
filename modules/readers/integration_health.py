"""Integration health as a reader job: the fourth instance of
modules/reader_job.py, consumed by the status bar on every page AND by Needs
attention (the operator's question, decided 2026-09-28).

**One producer, two consumers.** "Prometheus is unreachable" is a Needs
attention row with a cause and an action, and the status bar is a colour
drawn from the SAME stored value. Built as a tenth source, the bar would
have probed every integration on every page load (the section 0a shape job
health left) and been a second answer to one question.

**A check stays live** (rule 11): the Settings panel's per-integration Test
button is a person asking NOW, and keeps calling `test_connection()`
directly. Only the strip and the bar, which describe, read this value.

**The probes run in parallel**, so a read is bounded by the slowest single
integration (its 5 s timeout and two retries, about 16 s) rather than by
their sum, which with every integration down would outlast the interval.

An integration left unconfigured is a STATE, not a fault: stored as
`not_configured`, never a row. Where its emptiness switches a guard off,
job health's `unset_guard` row already says so.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from modules import reader_job

INTERVAL_SECONDS = 60


def _probe(name, cls) -> dict:
    t0 = time.monotonic()
    try:
        st = cls().status()
    except Exception as exc:                            # noqa: BLE001
        st = {"state": "down", "label": getattr(cls, "label", name),
              "message": f"the probe raised {type(exc).__name__}: {exc}"}
    try:
        from modules.redact import redact_text
        message = redact_text(str(st.get("message") or ""))
    except Exception:                                   # noqa: BLE001
        message = "(the message could not be redacted, so it is withheld)"
    return {"name": name, "label": st.get("label") or getattr(cls, "label", name),
            "state": st.get("state") or "down", "message": message,
            "took_ms": int((time.monotonic() - t0) * 1000)}


def _probe_controller(probe: dict) -> dict:
    """One SDN controller connection (PHASE8_PLAN 17.1 S2): its driver's `test()`, bounded by
    the connection's timeout, as a row the strip counts with the integrations."""
    t0 = time.monotonic()
    try:
        st = probe["probe"]()
    except Exception as exc:                            # noqa: BLE001
        st = {"state": "down", "message": f"the probe raised {type(exc).__name__}: {exc}"}
    try:
        from modules.redact import redact_text
        message = redact_text(str(st.get("message") or ""))
    except Exception:                                   # noqa: BLE001
        message = "(the message could not be redacted, so it is withheld)"
    return {"name": probe["name"], "label": probe["label"], "kind": "sdn_controller",
            "state": st.get("state") or "down", "message": message,
            "took_ms": int((time.monotonic() - t0) * 1000)}


def _controller_probes() -> list:
    try:
        from modules.sdn.connections import health_probes
        return health_probes()
    except Exception as exc:                            # noqa: BLE001 - said as a row
        words = f"the controller connections could not be listed ({type(exc).__name__}: {exc})"
        return [{"name": "sdn", "label": "SDN controllers",
                 "probe": lambda: {"state": "down", "message": words}}]


def read(registry=None, controllers=None) -> dict:
    """Every registered integration, probed, and every SDN controller connection across the
    networks (``controllers``, kept apart: the top bar counts both, while Needs attention's
    integration rows are the registered integrations', a controller's rows coming with its
    screens, PHASE8_PLAN 17.1 S11). *controllers*: the probes (`health_probes()` when None)."""
    from modules.integrations import REGISTRY

    reg = REGISTRY if registry is None else registry
    if not reg:
        raise ValueError("no integrations are registered, so none can be probed")
    probes = _controller_probes() if controllers is None else controllers
    jobs = [("integration", kv) for kv in reg.items()] + [("controller", p) for p in probes]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        done = list(pool.map(lambda job: _probe(*job[1]) if job[0] == "integration"
                             else _probe_controller(job[1]), jobs))
    items, ctl = done[:len(reg)], done[len(reg):]
    counts = {"up": 0, "down": 0, "refused": 0, "not_configured": 0}
    for i in items:
        counts[i["state"]] = counts.get(i["state"], 0) + 1
    out = {"integrations": items, "counts": counts}
    if ctl:
        out["controllers"] = ctl
    return out


READER = reader_job.register(reader_job.Reader(
    name="integrations",
    what="whether each integration Mercury depends on answers, for the status bar and Needs attention",
    endpoints=("each integration's own health endpoint (its test_connection)",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("all ten probed in 266 ms on the host when up (measured 2026-09-28); one "
                    "that is down is bounded by its 5 s timeout and two retries, and the probes "
                    "run in parallel, so an outage is named within a minute"),
    read=read,
    invalidates=("integration_health",),
    remedy="Read the error above: it names what the probe could not do",
    window="the state at the read",
))
