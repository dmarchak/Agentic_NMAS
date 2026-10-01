"""The v2 Devices list (NSOT_GUI_BRIEF 3.3; step 4): every device of a list,
pending onboardings among them, each with its status, address, platform,
role, intent state and the age of its last capture.

**No per-device work per request** (the brief's scale rule, measured at 900
devices: a `git log` per device is 7.2 s). The whole list costs a fixed
number of reads, whatever its size:

- the inventory (one read) and the manifest's pending devices (one read);
- the reachability reader's stored value (one read, never a probe);
- ONE bounded `git log` over `golden/`: each golden commit names its devices
  and, in `Intent-Match:`, which of them departed from committed intent when
  captured (C89 (d)), so a device's newest commit gives its capture's age and
  its state at that capture;
- ONE `git ls-tree` over `host_vars/`: which devices have committed intent.

So the intent state is **"as of its last capture"**, and says so: an intent
commit since then is the device page's live comparison (its Overview), never
this list's claim. A device whose newest golden commit is older than the
bound is "older than the last N golden commits", never "no golden".
"""

import logging
import re
import time

log = logging.getLogger(__name__)

#: How far back the one `git log` reads. A device captured less recently than
#: this many golden commits ago says so rather than guessing.
LOG_BOUND = 400

_FIELD, _RECORD = "\x1f", "\x1e"


def _golden_history(repo: str) -> tuple:
    """``({device: {"at", "intent"}}, error)`` from one bounded `git log`."""
    from modules.nsot import repo as R

    fmt = _FIELD.join(["%H", "%ct", "%(trailers:key=Device-Name,valueonly,separator=%x2c)",
                       "%(trailers:key=Devices,valueonly,separator=%x2c)",
                       "%(trailers:key=Intent-Match,valueonly)"]) + _RECORD
    rc, out, err = R.git(repo, "log", f"-n{LOG_BOUND}", f"--format={fmt}", "--", "golden/")
    if rc != 0:
        return {}, (err or out or "git log failed").strip()
    seen = {}
    for record in out.split(_RECORD):
        parts = record.strip("\n").split(_FIELD)
        if len(parts) < 5:
            continue
        _sha, ct, names, devices, intent = parts[:5]
        hosts = [h.strip() for h in (names or devices).split(",") if h.strip()]
        intent = intent.strip()
        for host in hosts:
            if host in seen:
                continue
            seen[host] = {"at": int(ct or 0), "intent": _intent_of(host, intent)}
    return seen, ""


def _intent_of(host: str, trailer: str) -> dict:
    """One device's state in a commit's `Intent-Match:` trailer."""
    if not trailer:
        return {"state": "unrecorded", "words": "not recorded at capture"}
    if trailer.startswith("yes"):
        return {"state": "at_intent", "words": "at intent"}
    m = re.search(rf"(?:^no: |; ){re.escape(host)} \(([^)]*)\)", trailer)
    if not m:
        return {"state": "at_intent", "words": "at intent"}
    detail = m.group(1)
    if detail.startswith("unknown"):
        return {"state": "unknown", "words": detail}
    return {"state": "departs", "words": f"departs ({detail})"}


def _with_intent(repo: str) -> tuple:
    from modules.nsot import repo as R

    rc, out, err = R.git(repo, "ls-tree", "--name-only", "HEAD", "host_vars/")
    if rc != 0:
        return set(), (err or "git ls-tree failed").strip()
    return {line.rsplit("/", 1)[-1][:-4] for line in out.splitlines()
            if line.endswith(".yml")}, ""


def _status(reach: dict, ip: str) -> dict:
    row = ((reach or {}).get("devices") or {}).get(ip)
    if reach is None or not row:
        return {"state": "unknown", "words": "not probed yet"}
    return ({"state": "ok", "words": "Answering"} if row.get("answering") else
            {"state": "danger", "words": "Not answering", "since": row.get("since")})


def _iso(ts) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


STATES = ("at_intent", "departs", "no_intent", "no_golden", "pending", "unknown")


def listing(ref, *, q: str = "", state: str = "", platform: str = "", now: float = None) -> dict:
    """The list as the page draws it, filtered by *q* (a substring of the name
    or address), *state* (one of `STATES`) and *platform*."""
    from modules.device import load_saved_devices
    from modules.device_page import _cached
    from modules.nsot import manifest
    from modules.nsot.platform import platform_for_device

    now = now or time.time()
    errors = []
    try:
        inventory = list(load_saved_devices(ref.csv_path))
    except Exception as exc:                      # noqa: BLE001
        return {"list": ref.name, "error": f"the inventory could not be read: {exc}",
                "rows": [], "total": 0, "platforms": [], "counts": {}}
    history, hist_err = _golden_history(ref.repo_dir)
    err = hist_err
    if err:
        errors.append(f"the golden history could not be read ({err}): intent states and "
                      "capture ages are unknown")
    with_intent, err = _with_intent(ref.repo_dir)
    if err:
        errors.append(f"committed intent could not be listed ({err})")
    reach, _at, _why = _cached("reachability")
    try:
        pending = manifest.pending_devices(ref.repo_dir)
    except Exception as exc:                      # noqa: BLE001
        pending = []
        errors.append(f"pending onboardings could not be read ({exc})")

    rows = []
    for dev in inventory:
        host = dev.get("hostname", "")
        h = history.get(host)
        if hist_err:
            intent = {"state": "unknown", "words": "unknown: the history could not be read"}
        elif host not in with_intent:
            intent = {"state": "no_intent", "words": "no intent"}
        elif h is None:
            intent = {"state": "no_golden", "words": (
                "no golden" if len(history) < LOG_BOUND else
                f"no golden in the last {LOG_BOUND} golden commits")}
        else:
            intent = dict(h["intent"])
            if intent["state"] in ("at_intent", "departs"):
                intent["words"] += ", as of its last capture"
        rows.append({"name": host, "pending": False, "status": _status(reach, dev.get("ip", "")),
                     "address": dev.get("ip", ""), "platform": platform_for_device(dev) or "",
                     "role": dev.get("role", ""), "intent": intent,
                     "captured_at": (h or {}).get("at"),
                     "captured_iso": _iso((h or {}).get("at"))})
    for p in pending:
        rows.append({"name": p.get("name", ""), "pending": True,
                     "status": {"state": "warn", "words": "Pending onboarding"},
                     "address": p.get("mgmt_ip") or (
                         f"awaiting DHCP ({p['reserved_address']})" if p.get("reserved_address")
                         else "no address recorded"),
                     "platform": "", "role": "", "captured_at": None, "captured_iso": "",
                     "intent": {"state": "pending", "words": "pending: not reached yet"}})

    total = len(rows)
    counts = {s: sum(1 for r in rows if r["intent"]["state"] == s) for s in STATES}
    platforms = sorted({r["platform"] for r in rows if r["platform"]})
    q = (q or "").strip().lower()
    shown = [r for r in rows
             if (not q or q in r["name"].lower() or q in (r["address"] or "").lower())
             and (not state or r["intent"]["state"] == state)
             and (not platform or r["platform"] == platform)]
    return {"list": ref.name, "error": "; ".join(errors), "rows": shown, "total": total,
            "counts": counts, "platforms": platforms, "q": q, "state": state,
            "platform": platform, "bound": LOG_BOUND}
