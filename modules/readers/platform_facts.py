"""C426: what each device IS, as it says over SNMP: a reader job.

A device's model was read only from its committed golden: the capture
header's `! Chassis type:` line, else `license udi pid`, else the header's
image line. A golden captured without that header names nothing (measured on
the deployment host, read-only, 2026-10-04: no switch's golden there carried
one), and an unknown model folds no platform rule, so a switch's
not-reported panels drew empty where a router's equivalent folded with its
reason.

`sysDescr` is a measured read every SNMP-polled device answers, and the
system group is scraped with the rest (measured the same day: 9 of 9 devices,
the switches' naming their image `vios_l2`). So the fleet's answer is ONE
instant query of Prometheus per read, never a device session, and a page
reads the stored value, never Prometheus.

What it keeps per device: `sysDescr`'s first line, the image it names, and
`sysObjectID`. It announces `device_state` when any device's answer changes,
with a keepalive.
"""

import logging
import re
import time

from modules import reader_job

log = logging.getLogger(__name__)

NAME = "platform-facts"
#: sysDescr changes only with the device's software, which arrives with a
#: restart; ten minutes bounds how long a new device stays unnamed.
INTERVAL_SECONDS = 600
KEEPALIVE_SECONDS = 3600

#: The image a Cisco IOS or IOS-XE sysDescr names: `Cisco IOS Software,
#: vios_l2 Software (...)`, `Cisco IOS Software [Bengaluru], Virtual XE
#: Software (...)`.
_IMAGE = re.compile(r"^Cisco IOS Software(?: \[[^\]]*\])?, (.+?) Software \(")


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def image_of(descr: str) -> str:
    m = _IMAGE.match((descr or "").strip())
    return m.group(1) if m else ""


def prometheus_all() -> tuple:
    """``(configured, {device: {"descr", "object_id"}})`` for the whole fleet.
    Raises when Prometheus is configured and cannot be asked, so a failure is
    a job-health row, never "no device reports a model"."""
    from modules.integrations.prometheus import PrometheusIntegration

    prom = PrometheusIntegration()
    if not prom.is_configured():
        return False, {}
    out = {}
    for metric, field in (("sysDescr", "descr"), ("sysObjectID", "object_id")):
        r = prom._get("api/v1/query", query=metric)
        if not r.get("ok"):
            raise RuntimeError(f"Prometheus could not be asked for {metric}: {r.get('error')}")
        for row in (r["response"].json().get("data") or {}).get("result") or []:
            labels = row.get("metric") or {}
            dev = labels.get("device")
            if dev and labels.get(metric):
                out.setdefault(dev, {})[field] = labels[metric]
    return True, out


def read(source=None) -> dict:
    configured, raw = (source or prometheus_all)()
    if not configured:
        return {"configured": False, "devices": {}}
    devices = {}
    for dev, got in sorted(raw.items()):
        descr = (got.get("descr") or "").strip().splitlines()
        first = descr[0] if descr else ""
        devices[dev] = {"descr": first, "image": image_of(first),
                        "object_id": got.get("object_id") or ""}
    return {"configured": True, "devices": devices}


def changed(previous: dict, value: dict) -> bool:
    return ((previous or {}).get("devices") or {}) != ((value or {}).get("devices") or {})


def facts() -> tuple:
    """``(devices, value_at, why)``: the stored answer, or ``({}, "", why
    not)``. Absent, unreadable and unconfigured are each said."""
    got = reader_job.read_cached(NAME)
    if got["state"] != "ok":
        return {}, "", ("sysDescr has not been read yet" if got["state"] == "absent"
                        else got["why"])
    good = (got["doc"] or {}).get("last_good") or {}
    if not good:
        error = ((got["doc"] or {}).get("last_attempt") or {}).get("error") or "no read succeeded"
        return {}, "", f"sysDescr has not been read: {error}"
    value = good.get("value") or {}
    if not value.get("configured"):
        return {}, "", "Prometheus is not configured, so sysDescr is not read"
    return value.get("devices") or {}, good.get("value_at") or "", ""


def measured(hostname: str, known: tuple = None) -> tuple:
    """``(model, basis)`` from the device's own sysDescr, or ``("", why
    not)``. *known* is a `facts()` answer, read once by a caller that asks
    for many devices."""
    devices, _at, why = known if known is not None else facts()
    if why:
        return "", why
    d = devices.get(hostname)
    if not d:
        return "", f"Prometheus holds no sysDescr for {hostname}"
    if not d.get("image"):
        return "", f"{hostname}'s sysDescr names no image"
    # No read time in the words: the reader announces only a changed answer (CHANGE_ONLY).
    return d["image"], ("the device's SNMP sysDescr, as Prometheus holds it (the image; the "
                        "device reports no chassis model)")


READER = reader_job.register(reader_job.Reader(
    name=NAME,
    what="what each device is, from its own SNMP sysDescr (C426)",
    endpoints=("Prometheus: GET /api/v1/query sysDescr and sysObjectID (the whole fleet)",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("sysDescr changes only with a device's software, which arrives with a "
                    "restart; ten minutes bounds how long a new or upgraded device reads its "
                    "old answer, at two queries a read"),
    read=read,
    invalidates=("device_state",),
    remedy="Read the error above: it names what Prometheus answered",
    window="Prometheus's last sample of each device's system group",
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
