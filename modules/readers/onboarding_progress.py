"""modules/readers/onboarding_progress.py — where each pending onboarding has got to, read
again on its own, so its page tells a person when to press Verify (C1193, the operator's walk
W4, 2026-10-17: no live refresh, no probe after "fetched", no elapsed time, no stop rule).

Every pending onboarding in every network (the manifest's `pending_devices`): for a ZTP device
its stage (`ztp.progress`: Kea's running reservation, Kea's lease, the responder's fetches
since its Create); and, once there is something to answer (a ZTP device that FETCHED its
config, or a static or DHCP device's address), the reachability reader's own read-only probe of
its address (`readers.reachability.probe`: ICMP from Mercury, then a TCP connection to port 22,
2 s each). No login is tried and nothing is sent: a device that accepts the connection is
"answering: ready to Verify", which is the claim the probe measured and no more (M4 fetched,
applied its config and still refused SSH; Verify is what reaches it).

It announces `pending` when a device's stage, its answer or the stop rule moves (never for a
read's own time), so the pending page's progress card and the top bar's In progress chip
(`in_progress`) draw it again. Nothing polls in a page.

**The stop rule** (the operator, W4): no fetch 15 minutes after boot: stop. The tool cannot
see the boot, only the Create before it, so a ZTP device 15 minutes past its Create with no
fetch of its own is marked `stop`, and the page says it as the rule with that measure.
"""

import calendar
import logging
import os
import time

from modules import reader_job

log = logging.getLogger(__name__)

READER_NAME = "onboarding-progress"
#: AutoInstall on IOS-XE 17.6 asks about every 8 s and gives up after about 2.5 minutes (M4,
#: measured in the lab); Kea answers in milliseconds (3 to 77 ms, the DHCP reader's, 2026-10-11)
#: and each probe is bounded at 2 s per transport. Read every 10 s, a fetch is on the page within
#: about one AutoInstall retry.
INTERVAL_SECONDS = 10
KEEPALIVE_SECONDS = 600
#: The operator's stop rule (W4, 2026-10-17): no fetch 15 minutes after boot: stop.
STOP_AFTER_S = 900
#: The ZTP stages before a fetch of its own: the ones the stop rule judges.
NOT_FETCHED = ("reserved_not_leased", "leased_not_fetched", "asked_not_served")


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _since(stamp: str, now: float):
    try:
        return max(0, int(now - calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))))
    except (TypeError, ValueError):
        return None


def key(list_name: str, name: str) -> str:
    """A pending device's key in the value: its network and its name."""
    return f"{list_name}/{name}"


def population() -> list:
    """``[(network, pending row)]`` across every network: the manifest's pending onboardings.
    A network whose manifest cannot be read is logged and skipped (its devices then read as
    not known, never as nothing pending: the page says the reader holds no row for them)."""
    from modules import integration_groups as IG
    from modules.config import list_data_path
    from modules.nsot import manifest

    out = []
    # The registry's names (`network_names`: no list's devices loaded), each through the path
    # that only asks (`config.list_data_path`, C51): a read creates no list.
    for name in IG.network_names():
        repo = os.path.join(list_data_path(name), "config_repo")
        if not os.path.isdir(repo):
            continue
        try:
            out += [(name, row) for row in manifest.pending_devices(repo)]
        except Exception as exc:                       # noqa: BLE001 (a read, logged)
            log.error("onboarding-progress: %s's pending onboardings could not be read: %s",
                      name, exc)
    return out


def address(row: dict) -> str:
    """Where the device will answer: its reserved address (DHCP, ZTP), else its static one."""
    return row.get("reserved_address") or row.get("mgmt_ip") or ""


def judge(list_name: str, row: dict, now: float, *, progress=None, probe=None) -> dict:
    """One pending device's progress: its stage (ZTP), and the probe once there is something
    to answer. *progress* and *probe* are `ztp.progress` and `reachability.probe` by default,
    so a test stands the device's answers in for Kea and the network."""
    ztp = row.get("address_source") == "ztp"
    out = {"name": row.get("name", ""), "list": list_name,
           "source": row.get("address_source") or "static",
           "onboarded_at": row.get("onboarded_at", ""), "address": address(row),
           "stage": "", "summary": "", "answering": None, "claim": "", "probed_at": "",
           "stop": False}
    if ztp:
        if progress is None:
            from modules.nsot.ztp import progress
        p = progress(row, list_name=list_name) or {}
        out.update(stage=p.get("stage", "unknown"), summary=p.get("summary", ""))
        age = _since(out["onboarded_at"], now)
        out["stop"] = bool(out["stage"] in NOT_FETCHED and age is not None
                           and age >= STOP_AFTER_S)
    asks = (out["stage"] == "fetched_not_reached") if ztp else True
    if asks and out["address"]:
        if probe is None:
            from modules.readers.reachability import probe
        answered, claim = probe(out["address"])
        out.update(answering=bool(answered), claim=claim, probed_at=_iso(now))
    return out


def read(pop=None, clock=time.time, progress=None, probe=None) -> dict:
    """Every pending onboarding's progress, concurrently (`fanout.read_each`: each one's Kea
    reads and probe at once, C199). One that could not be read is carried as that."""
    from modules.fanout import Failed, read_each

    now = clock()
    pop = population() if pop is None else pop
    got = read_each(lambda item: judge(item[0], item[1], now, progress=progress, probe=probe),
                    pop, name="onboarding-progress")
    devices = {}
    for (list_name, row), g in zip(pop, got):
        if isinstance(g, Failed):
            g = {"name": row.get("name", ""), "list": list_name,
                 "source": row.get("address_source") or "static",
                 "onboarded_at": row.get("onboarded_at", ""), "address": address(row),
                 "stage": "unknown", "summary": f"its progress could not be read: {g}",
                 "answering": None, "claim": "", "probed_at": "", "stop": False}
        devices[key(list_name, g["name"])] = g
    return {"devices": devices, "read_at": _iso(now)}


def changed(previous, value) -> bool:
    """Announce when a device's stage, answer or stop rule moved, or one came or went; never
    for a read's own time or a probe's."""
    def strip(v):
        return {k: {f: x for f, x in d.items() if f != "probed_at"}
                for k, d in ((v or {}).get("devices") or {}).items()}
    return strip(previous) != strip(value)


def stored(list_name: str, name: str):
    """``(the device's last read, its time)`` from the reader's store, or ``(None, why)``. A
    page reads this, never the device (enterprise scale: no per-device work per request)."""
    got = reader_job.read_cached(READER_NAME)
    good = ((got.get("doc") or {}).get("last_good") or {})
    if got["state"] != "ok" or not good:
        return None, got.get("why") or "the reader has not stored a value yet"
    d = ((good.get("value") or {}).get("devices") or {}).get(key(list_name, name))
    if d is None:
        return None, f"its last read ({good.get('value_at') or '?'}) holds no row for it yet"
    return dict(d, read_at=good.get("value_at") or ""), ""


def stored_network(list_name: str) -> tuple:
    """``({name: its last read}, the value's time, why)`` for every pending device of
    *list_name*, from the reader's store in ONE read: the Devices list's rows (C1477; no
    per-device work per request). ``({}, "", why)`` when the reader holds no value."""
    got = reader_job.read_cached(READER_NAME)
    good = ((got.get("doc") or {}).get("last_good") or {})
    if got["state"] != "ok" or not good:
        return {}, "", got.get("why") or "the reader has not stored a value yet"
    devices = ((good.get("value") or {}).get("devices") or {}).values()
    return ({d.get("name", ""): d for d in devices if d.get("list") == list_name},
            good.get("value_at") or "", "")


#: A ZTP stage in a Devices row's few words (C1477); its page's card says it at length.
ZTP_WORDS = {"reservation_missing": "ZTP: reservation missing",
             "reserved_not_leased": "ZTP: no lease yet",
             "leased_not_fetched": "ZTP: leased, not fetched",
             "asked_not_served": "ZTP: asked, not served",
             "fetched_not_reached": "ZTP: fetched its config",
             "unknown": "ZTP: progress unknown"}


def row_words(d: dict, onboarded_at: str = "") -> tuple:
    """``(words, why)``: where a pending device has got to, in a Devices row's few words, from
    its stored read *d* (:func:`stored_network`) as its page reads it (its ZTP stage, and the
    probe's answer); *why* is the stage's summary and the probe's claim, for the row's hover.
    A read made for an earlier device of the name (its Create differs from *onboarded_at*) or
    none at all is said as not read yet, never as this device's progress (C1476)."""
    if not d or (onboarded_at and d.get("onboarded_at") != onboarded_at):
        return "pending: not read yet", ("the onboarding-progress reader has not read it since "
                                         "its Create; its next read is within "
                                         f"{INTERVAL_SECONDS} s")
    claim = (f"{d.get('address')} {d['claim']}" if d.get("claim") else "")
    why = "; ".join(x for x in (d.get("summary"), claim) if x)
    if d.get("answering"):
        return "answering: ready to Verify", why
    if d.get("stop"):
        return f"ZTP: no fetch {STOP_AFTER_S // 60} minutes after its Create: stop", why
    if d.get("source") == "ztp":
        words = ZTP_WORDS.get(d.get("stage") or "unknown", ZTP_WORDS["unknown"])
        return (words + ("; not answering yet" if d.get("answering") is False else "")), why
    if d.get("answering") is False:
        return "pending: not answering yet", why
    return "pending: not probed yet", why or "it has no address to probe"


READER = reader_job.register(reader_job.Reader(
    name=READER_NAME,
    what="where each pending onboarding has got to: a ZTP device's stage (Kea's reservation "
         "and lease, the responder's fetches since its Create) and, once it fetched (or for a "
         "static or DHCP device, at its address), whether it answers ICMP or a TCP connection "
         "on port 22, for its pending page's progress card and the In progress chip (C1193)",
    endpoints=("Kea Control Agent: reservation-get (else config-get) and "
               "lease4-get-by-hw-address (else lease4-get-all) to dhcp4",
               "the ZTP responder's reveal record (data/reveal_audit.jsonl)",
               "ICMP echo, then a TCP connection to port 22, at each pending device's address"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("AutoInstall on IOS-XE 17.6 asks about every 8 s and gives up after about "
                    "2.5 minutes (M4, measured in the lab); Kea answers in 3 to 77 ms "
                    "(2026-10-11) and each probe is bounded at 2 s per transport"),
    read=read,
    invalidates=("pending", "in_progress"),
    remedy="Read the error above: it names the read that failed",
    window="each pending onboarding at the read: its ZTP stage now, its fetches since its "
           "Create, and one probe of its address",
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
