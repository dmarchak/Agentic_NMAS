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


def read(registry=None) -> dict:
    from modules.integrations import REGISTRY

    reg = REGISTRY if registry is None else registry
    if not reg:
        raise ValueError("no integrations are registered, so none can be probed")
    with ThreadPoolExecutor(max_workers=len(reg)) as pool:
        items = list(pool.map(lambda kv: _probe(*kv), reg.items()))
    counts = {"up": 0, "down": 0, "not_configured": 0}
    for i in items:
        counts[i["state"]] = counts.get(i["state"], 0) + 1
    return {"integrations": items, "counts": counts}


READER = reader_job.register(reader_job.Reader(
    name="integrations",
    what="whether each integration NMAS depends on answers, for the status bar and Needs attention",
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
