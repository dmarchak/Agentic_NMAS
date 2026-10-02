"""The v2 Devices list (NSOT_GUI_BRIEF 3.3; step 4): every device of a list,
pending onboardings among them, each with its status, address, platform,
role, intent state, when it was last MEASURED and when its golden last changed.

**No per-device work per request** (the brief's scale rule, measured at 900
devices: a `git log` per device is 7.2 s). The whole list costs a fixed
number of reads, whatever its size:

- the inventory (one read) and the manifest's pending devices (one read);
- the reachability reader's stored value (one read, never a probe);
- ONE bounded `git log` over `golden/`: when each device's golden last CHANGED;
- ONE bounded `git log` over the commits carrying `Intent-Match:` (every save
  since C89, the decision a Save All records when nothing changed included):
  when each device was last MEASURED, by which workflow, and its state against
  committed intent then (`last_measured()`, which the device page reads too);
- ONE `git ls-tree` over `host_vars/`: which devices have committed intent.

**A measurement is any read the tool compared with the golden and recorded**
(2026-10-02, the operator: the list read only golden commits, so a Save All
that found a device unchanged, the best evidence there is, did not count). The
intent state is the newest measurement's, and says which and when; an intent
commit since then is the device page's live comparison (its Overview), never
this list's claim. A changing commit before 2026-10-02 named only the devices
whose golden moved (`Devices-Measured:` names every device read since), so an
older unchanged read in a changing Save All is not recoverable.
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
    """``({device: {"at", "sha", "intent"}}, error)`` from one bounded `git log` over
    `golden/`: the commit that last CHANGED each device's golden."""
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
        sha, ct, names, devices, intent = parts[:5]
        hosts = [h.strip() for h in (names or devices).split(",") if h.strip()]
        intent = intent.strip()
        for host in hosts:
            if host in seen:
                continue
            seen[host] = {"at": int(ct or 0), "sha": sha[:7], "intent": _intent_of(host, intent)}
    return seen, ""


#: A save's `Source:` in words, for "measured by ...". Anything else reads as its slug.
SOURCE_WORDS = {"save_all": "Save All", "capture": "a capture", "pipeline": "a deploy",
                "restore": "a restore", "rotation": "a rotation", "onboarding": "onboarding",
                "adopt": "adoption", "approval": "an approval", "manual": "a save",
                "repair": "a repair", "extraction": "an extraction", "ai": "the agent"}


def _split(text: str) -> list:
    return [h.strip() for h in (text or "").split(",") if h.strip()]


def last_measured(repo: str, bound: int = LOG_BOUND) -> tuple:
    """``({device: {"at", "sha", "source", "how", "changed", "baseline", "intent"}}, error)``:
    each device's NEWEST measurement, from ONE bounded `git log` over the commits carrying
    `Intent-Match:` (only a save writes it). A device is measured by a commit that names it
    in `Devices-Measured:` (every device read) or, before that trailer, in `Device-Name:` /
    `Devices:` (the goldens that moved). *changed* says whether its golden moved then."""
    from modules.nsot import repo as R

    fmt = _FIELD.join(["%H", "%ct", "%(trailers:key=Source,valueonly)",
                       "%(trailers:key=Device-Name,valueonly,separator=%x2c)",
                       "%(trailers:key=Devices,valueonly,separator=%x2c)",
                       "%(trailers:key=Devices-Measured,valueonly,separator=%x2c)",
                       "%(trailers:key=Intent-Match,valueonly)",
                       "%(trailers:key=Baseline,valueonly)"]) + _RECORD
    rc, out, err = R.git(repo, "log", f"-n{bound}", "-E", "--grep=^Intent-Match: ",
                         f"--format={fmt}")
    if rc != 0:
        return {}, (err or out or "git log failed").strip()
    seen = {}
    for record in out.split(_RECORD):
        parts = record.strip("\n").split(_FIELD)
        if len(parts) < 8:
            continue
        sha, ct, source, names, devices, measured, intent, baseline = parts[:8]
        moved = set(_split(names) or _split(devices))
        source = source.strip()
        for host in _split(measured) or sorted(moved):
            if host in seen:
                continue
            changed = host in moved
            seen[host] = {"at": int(ct or 0), "sha": sha[:7], "source": source,
                          "how": SOURCE_WORDS.get(source, source.replace("_", " ") or "a save"),
                          "changed": changed, "baseline": baseline.strip().startswith("earned"),
                          "intent": _intent_of(host, intent.strip())}
    return seen, ""


def measured_words(m: dict) -> str:
    """"Save All, no change" / "a deploy, golden changed", plus a baseline it earned."""
    return (f"{m['how']}, {'golden changed' if m['changed'] else 'no change'}"
            + (", which earned a baseline" if m.get("baseline") else ""))


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
        # A short word in the row and the reason on its hover (the operator, 2026-10-02: the
        # whole sentence in a no-wrap badge pushed Last measured off the table). The trailer's
        # nested parenthesis is cut by the pattern above, so the reason is taken whole here.
        why = detail[len("unknown"):].strip().lstrip("(").strip()
        return {"state": "unknown", "words": "unknown", "why": why or "not established"}
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
    history, gold_err = _golden_history(ref.repo_dir)
    measured, meas_err = last_measured(ref.repo_dir)
    hist_err = gold_err or meas_err
    if hist_err:
        errors.append(f"the golden history could not be read ({hist_err}): intent states and "
                      "measurement ages are unknown")
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
        # The newest MEASUREMENT: a save that read the device, whether or not its golden
        # moved. A golden commit older than the measurement log's reach (before C89 wrote
        # `Intent-Match:`) is still a measurement, so the newer of the two counts.
        m = measured.get(host)
        if h and (m is None or h["at"] > m["at"]):
            m = {"at": h["at"], "sha": h["sha"], "source": "", "how": "a save",
                 "changed": True, "baseline": False, "intent": h["intent"]}
        if hist_err:
            intent = {"state": "unknown", "words": "unknown: the history could not be read"}
        elif host not in with_intent:
            intent = {"state": "no_intent", "words": "no intent"}
        elif h is None and m is None:
            intent = {"state": "no_golden", "words": (
                "no golden" if len(history) < LOG_BOUND else
                f"no golden in the last {LOG_BOUND} golden commits")}
        else:
            intent = dict(m["intent"])
        rows.append({"name": host, "pending": False, "status": _status(reach, dev.get("ip", "")),
                     "address": dev.get("ip", ""), "platform": platform_for_device(dev) or "",
                     "role": dev.get("role", ""), "intent": intent,
                     "measured": ({"at": m["at"], "iso": _iso(m["at"]), "sha": m["sha"],
                                   "words": measured_words(m), "changed": m["changed"]}
                                  if m and not hist_err else None),
                     "golden_changed": ({"at": h["at"], "iso": _iso(h["at"]), "sha": h["sha"]}
                                        if h and not hist_err else None)})
    for p in pending:
        rows.append({"name": p.get("name", ""), "pending": True,
                     "status": {"state": "warn", "words": "Pending onboarding"},
                     "address": p.get("mgmt_ip") or (
                         f"awaiting DHCP ({p['reserved_address']})" if p.get("reserved_address")
                         else "no address recorded"),
                     "platform": "", "role": "", "measured": None, "golden_changed": None,
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
