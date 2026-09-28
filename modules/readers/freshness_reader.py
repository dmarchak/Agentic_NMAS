"""Oxidized freshness as a reader job: the third instance of
modules/reader_job.py.

**Why a reader.** The freshness SIGNAL (is what Oxidized holds the state
somebody approved?) ran `freshness.check()` on every load of the index page:
one Oxidized config fetch and one committed-golden read per device, per
request. That is the section 0a shape (per-device work per request) at nine
devices, and a slow page at 900. It is read here on a schedule, and the page
reads what was stored (rule 1).

The GATE (`POST /freshness/gate`) stays live on purpose: it compares the
exact bytes its caller is about to write, which no stored value can stand
for.

**Every list, one value.** The signal is per device list, and the reader
reads each list the registry holds, so a page showing any list reads the
same stored value. A list whose comparison could not run (no devices,
Oxidized not configured) is stored WITH its reason: a list the reader could
not answer about is never absent from the value.
"""

from modules import reader_job

INTERVAL_SECONDS = 300


def read(check=None, lists=None) -> dict:
    from modules.nsot import freshness
    from modules.device import get_device_lists

    check = check or freshness.check
    names = lists if lists is not None else [d["name"] for d in get_device_lists()]
    if not names:
        raise ValueError("no device lists are registered, so nothing can be compared")
    out = {}
    for name in names:
        try:
            report = check(name)
        except Exception as exc:                        # noqa: BLE001
            report = {"ok": False, "list": name,
                      "error": f"the comparison raised {type(exc).__name__}: {exc}"}
        if report.get("ok"):
            report["summary"] = freshness.gate_summary(report)
        out[name] = report
    return {"lists": out}


READER = reader_job.register(reader_job.Reader(
    name="freshness",
    what="whether each device's Oxidized copy is the state somebody approved, per list",
    endpoints=("Oxidized nodes.json", "Oxidized config per node",
               "the committed goldens (HEAD)"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("NMAS sees a divergence within 5 min of Oxidized recording it; "
                    "Oxidized itself polls each device every 3600 s (`interval: 3600` in "
                    "/opt/oxidized/config on the host, read 2026-09-28; its API does not "
                    "serve it), so its copy can be up to an hour behind the device. The read "
                    "costs 16 ms for the index and about 4 ms per device (measured)"),
    read=read,
    invalidates=("freshness",),
    remedy="Read the error above: it names what the comparison could not ask",
    window="the state at the read: Oxidized's latest copy against HEAD's golden",
))
