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
  committed intent then (`last_measured()`, which the device page reads too, for its
  one device: `only=`, C855);
- ONE `git ls-tree` over `host_vars/`: which devices have committed intent;
- ONE bounded `git log` over what a device's intent is rendered from (its
  `host_vars/`, the network's monitoring profile, the template library) since the
  oldest measurement, and ONE `git rev-list` over the same window to order those
  commits against the measurements (C532).

**A measurement is any read the tool compared with the golden and recorded**
(2026-10-02, the operator: the list read only golden commits, so a Save All
that found a device unchanged, the best evidence there is, did not count). The
intent state is the newest measurement's, and says which and when. A changing
commit before 2026-10-02 named only the devices whose golden moved
(`Devices-Measured:` names every device read since), so an older unchanged read in
a changing Save All is not recoverable.

**One owner of a device's intent state (C532): `intent_state()`**, which the list
and the device page both draw. The list said s1 "departs (+1)" from its last
measurement's `Intent-Match:` trailer while s1's page, comparing live, said it
matched: an intent commit after the measurement had made the trailer stale, and
the list drew it as current through every refresh. So the recorded state is drawn
only while nothing it was judged against has moved since; once the device's
committed intent, the monitoring profile or the template library has a commit
after its measurement, the state is **intent changed since measured**, naming
what moved and when, never the stale departure or the stale "at intent" (the
wrong state that looks right). The device page draws the same state beside its
live comparison and says which is which.
"""

import logging
import re
import time

log = logging.getLogger(__name__)

#: How far back the one `git log` reads. A device captured less recently than
#: this many golden commits ago says so rather than guessing.
LOG_BOUND = 400

#: How many commits the read of what moved a device's intent takes (C532), newest first,
#: since the oldest measurement it is compared with. Those are intent, profile and template
#: commits only; a window that fills is truncated, and a device measured before its oldest
#: commit says its state is not established rather than guessing.
INTENT_BOUND = 400

#: How many commits, newest first since the oldest measurement, are read to ORDER an intent
#: commit against a measurement (C532). Two commits in one second have one commit time, and
#: an intent edit and the capture after it often do; their place in history decides. Beyond
#: this window, commit times decide, and a tie there is said as moved (the answer that sends
#: a person to measure again, never the one that keeps a stale state).
ORDER_BOUND = 2000

_FIELD, _RECORD = "\x1f", "\x1e"


def _golden_history(repo: str, only: str = None) -> tuple:
    """``({device: {"at", "sha", "commit", "source", "intent"}}, error, full)`` from one
    bounded `git log` over `golden/`: the commit that last CHANGED each device's golden.
    *full* says the read returned its whole bound (so it may be truncated). *only* answers
    for one device by the same log and rule, as `last_measured` does (C855)."""
    from modules.nsot import repo as R

    fmt = _FIELD.join(["%H", "%ct", "%(trailers:key=Device-Name,valueonly,separator=%x2c)",
                       "%(trailers:key=Devices,valueonly,separator=%x2c)",
                       "%(trailers:key=Intent-Match,valueonly)",
                       "%(trailers:key=Source,valueonly)"]) + _RECORD
    rc, out, err = R.git(repo, "log", f"-n{LOG_BOUND}", f"--format={fmt}", "--", "golden/")
    if rc != 0:
        return {}, (err or out or "git log failed").strip(), False
    records = out.split(_RECORD)
    seen = {}
    for record in records:
        parts = record.strip("\n").split(_FIELD)
        if len(parts) < 6:
            continue
        sha, ct, names, devices, intent, source = parts[:6]
        intent = intent.strip()
        for host in _names(names or devices, only):
            if host in seen:
                continue
            seen[host] = {"at": int(ct or 0), "sha": sha[:7], "commit": sha,
                          "source": source.strip(), "intent": _intent_of(host, intent)}
        if only is not None and seen:
            break                                 # the newest is the one asked for
    return seen, "", sum(1 for r in records if r.strip("\n")) >= LOG_BOUND


#: A save's `Source:` in words, for "measured by ...". Anything else reads as its slug.
SOURCE_WORDS = {"save_all": "Save All", "capture": "a capture", "pipeline": "a deploy",
                "save": "a Save", "restore": "a restore", "rotation": "a rotation",
                "scheduled_rotation": "a scheduled rotation",
                "onboarding": "onboarding",
                "adopt": "adoption", "approval": "an approval", "manual": "a save",
                "repair": "a repair", "extraction": "an extraction", "ai": "the agent",
                "intent-edit": "an intent edit"}


def _split(text: str) -> list:
    return [h.strip() for h in (text or "").split(",") if h.strip()]


#: The separator of a trailer's names with the space around it: `_names` reads a list as
#: `_split` does, without a call per name.
_COMMA = re.compile(r"\s*,\s*")


def _listed(text: str) -> bool:
    """Whether a trailer's comma-separated value names any device (`_split` non-empty)."""
    return bool((text or "").replace(",", "").strip())


def _names(text: str, only: str = None) -> list:
    """The devices a trailer's value names (`_split`); with *only*, ``[only]`` if it is one
    of them, else ``[]``: a test on the text, so one device's question costs no call per
    device the trailer names (C855: a Save All's commit names the whole network)."""
    if only is None:
        return _split(text)
    if not only or "," in only or only != only.strip():
        return []                                 # `_split` yields no such name
    return [only] if f",{only}," in "," + _COMMA.sub(",", (text or "").strip()) + "," else []


def _measured_by(names: str, devices: str, measured: str, only: str = None) -> tuple:
    """``(hosts, moved)``: the devices one measurement commit READ, and the set whose golden
    MOVED. The one rule for the list and the page: `Devices-Measured:` names every device
    read; before that trailer, `Device-Name:` (else `Devices:`) named only the goldens that
    moved, and those are the devices read. With *only*, that device's part of the answer."""
    moved = set(_names(names if _listed(names) else devices, only))
    return (_names(measured, only) if _listed(measured) else sorted(moved)), moved


def last_measured(repo: str, bound: int = LOG_BOUND, only: str = None) -> tuple:
    """``({device: {"at", "sha", "source", "how", "changed", "baseline", "intent"}}, error)``:
    each device's NEWEST measurement, from ONE bounded `git log` over the commits carrying
    `Intent-Match:` (only a save writes it). A device is measured by a commit that names it
    in `Devices-Measured:` (every device read) or, before that trailer, in `Device-Name:` /
    `Devices:` (the goldens that moved). *changed* says whether its golden moved then.

    *only* (a device's page, C855) answers for that one device, ``{only: ...}`` or ``{}``, by
    the same log and the same rule, with no work per device the log's commits name: the page
    read every device's measurement to draw one, about 460 Python calls per device at 900."""
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
        hosts, moved = _measured_by(names, devices, measured, only)
        source = source.strip()
        for host in hosts:
            if host in seen:
                continue
            changed = host in moved
            seen[host] = {"at": int(ct or 0), "sha": sha[:7], "commit": sha, "source": source,
                          "how": SOURCE_WORDS.get(source, source.replace("_", " ") or "a save"),
                          "changed": changed, "baseline": baseline.strip().startswith("earned"),
                          "intent": _intent_of(host, intent.strip())}
        if only is not None and seen:
            break                                 # the newest is the one asked for
    return seen, ""


def measured_words(m: dict) -> str:
    """"Save All, no change" / "a deploy, golden changed", plus a baseline it earned."""
    return (f"{m['how']}, {'golden changed' if m['changed'] else 'no change'}"
            + (", which earned a baseline" if m.get("baseline") else ""))


def _departure(host: str, trailer: str):
    """*host*'s detail in a ``no: a (d1); b (d2)`` trailer, or None when it is not named: the
    first ``no: <host> (`` at the start or ``; <host> (`` anywhere, up to the next ``)``.
    Literal, so nothing is compiled per device (C855: a pattern built from each host was
    compiled for every device, and past `re`'s 512-entry cache, compiled every time)."""
    head = f"no: {host} ("
    if trailer.startswith(head):
        start = len(head)
    else:
        at = trailer.find(f"; {host} (")
        if at < 0:
            return None
        start = at + len(host) + 4
    end = trailer.find(")", start)
    return None if end < 0 else trailer[start:end]


def _intent_of(host: str, trailer: str) -> dict:
    """One device's state in a commit's `Intent-Match:` trailer."""
    if not trailer:
        return {"state": "unrecorded", "words": "not recorded at capture"}
    if trailer.startswith("yes"):
        return {"state": "at_intent", "words": "at intent"}
    detail = _departure(host, trailer)
    if detail is None:
        return {"state": "at_intent", "words": "at intent"}
    if detail.startswith("unknown"):
        # A short word in the row and the reason on its hover (the operator, 2026-10-02: the
        # whole sentence in a no-wrap badge pushed Last measured off the table). The trailer's
        # nested parenthesis is cut by the pattern above, so the reason is taken whole here.
        why = detail[len("unknown"):].strip().lstrip("(").strip()
        return {"state": "unknown", "words": "unknown", "why": why or "not established"}
    return {"state": "departs", "words": f"departs ({detail})"}


def _with_intent(repo: str, only: str = None) -> tuple:
    """``(devices with committed intent, error)``: one `git ls-tree` over `host_vars/`, or
    over *only*'s one file (the device page: no line per device of the network)."""
    from modules.nsot import repo as R

    rc, out, err = R.git(repo, "ls-tree", "--name-only", "HEAD",
                         "host_vars/" if only is None else f"host_vars/{only}.yml")
    if rc != 0:
        return set(), (err or "git ls-tree failed").strip()
    return {line.rsplit("/", 1)[-1][:-4] for line in out.splitlines()
            if line.endswith(".yml")}, ""


def _intent_paths() -> list:
    """What a device's intent is RENDERED from, as `git log` pathspecs: committed intent
    (`host_vars/`), the network's monitoring profile every device inherits, and the template
    library that renders it, less the approvals record (approving a template renders nothing
    differently). `intent_match` reads exactly these to compare a golden with intent; a
    secret's VALUE is not in git and is not among them."""
    from modules.nsot import approval, profile, templates_repo

    return ["host_vars/", profile.PROFILE_REL, templates_repo.TEMPLATES_REL + "/",
            f":(exclude){approval.APPROVALS_REL}"]


def _intent_moves(repo: str, floor: int, only: str = None) -> tuple:
    """``({"devices": {device: move}, "network": move or None, "reach": at or None}, error)``:
    the newest commit since *floor* (the oldest measurement asked about) that moved each
    device's own committed intent, and the newest that moved what every device inherits
    (the profile or the template library). Each move is ``{"commit", "sha", "at", "what"}``.
    *reach* is the oldest commit time read when the read filled `INTENT_BOUND` (it may be
    truncated there), else None. One bounded `git log`, whatever the network's size.

    *only* (the device page) reads the SAME window and answers for that one device by a
    test on each commit's text, so the page and the list agree even where the window is
    truncated, with no work per device a commit names (a bulk intent change names them all)."""
    from modules.nsot import profile, templates_repo
    from modules.nsot import repo as R

    fmt = _RECORD + _FIELD.join(["%H", "%ct"])
    rc, out, err = R.git(repo, "log", f"-n{INTENT_BOUND}", f"--since=@{int(floor)}",
                         f"--format={fmt}", "--name-only", "--", *_intent_paths())
    if rc != 0:
        return {"devices": {}, "network": None, "reach": None}, (
            err or out or "git log failed").strip()
    # `R.git` strips its output, and `str.strip` counts the separator as space: the first
    # record's leading one is gone, so empties are dropped rather than the first.
    records = [r for r in out.split(_RECORD) if r.strip("\n")]
    reach = None
    if len(records) >= INTENT_BOUND:
        reach = int(records[-1].partition("\n")[0].partition(_FIELD)[2] or 0)
    profile_line, library = f"\n{profile.PROFILE_REL}\n", f"\n{templates_repo.TEMPLATES_REL}/"
    mine = f"\nhost_vars/{only}.yml\n" if only is not None else ""
    devices, network = {}, None
    for record in records:
        head, _nl, paths = record.strip("\n").partition("\n")
        sha, _sep, ct = head.partition(_FIELD)
        at, text = int(ct or 0), f"\n{paths}\n"
        if network is None and (profile_line in text or library in text):
            network = {"commit": sha, "sha": sha[:7], "at": at,
                       "what": ("the network's monitoring profile" if profile_line in text
                                else "the template library")}
        if only is None:
            for path in paths.splitlines():
                if path.startswith("host_vars/") and path.endswith(".yml"):
                    host = path[len("host_vars/"):-len(".yml")]
                    if host not in devices:
                        devices[host] = _own_move(host, sha, at)
        elif only and only not in devices and mine in text:
            devices[only] = _own_move(only, sha, at)
        if only is not None and network is not None and (only in devices or not only):
            break                                   # the newest of each is all it needs
    return {"devices": devices, "network": network, "reach": reach}, ""


def _own_move(host: str, sha: str, at: int) -> dict:
    return {"commit": sha, "sha": sha[:7], "at": at,
            "what": f"its committed intent (host_vars/{host}.yml)"}


def _order(repo: str, floor: int) -> tuple:
    """``({full sha: place, newest first}, error)``: one `git rev-list` since *floor*, the
    order commits of one second cannot be told apart by (`ORDER_BOUND`)."""
    from modules.nsot import repo as R

    rc, out, err = R.git(repo, "rev-list", f"-n{ORDER_BOUND}", f"--since=@{int(floor)}",
                         "HEAD")
    if rc != 0:
        return {}, (err or out or "git rev-list failed").strip()
    return {sha: i for i, sha in enumerate(out.split())}, ""


def reads(repo: str, only: str = None) -> dict:
    """Everything `intent_state` decides from, for the whole network or for *only* (the
    device page), in a fixed number of git reads whatever the network's size: the golden
    history, the measurements, which devices have committed intent, and (when any device has
    been measured) what moved their intent since, in order."""
    history, gold_err, full = _golden_history(repo, only)
    measured, meas_err = last_measured(repo, only=only)
    with_intent, intent_err = _with_intent(repo, only)
    out = {"history": history, "history_full": full, "measured": measured,
           "error": gold_err or meas_err, "with_intent": with_intent,
           "intent_error": intent_err,
           "moves": {"devices": {}, "network": None, "reach": None}, "order": {},
           "moves_error": ""}
    ats = [v["at"] for v in history.values()] + [v["at"] for v in measured.values()]
    if ats and not out["error"]:
        floor = min(ats)
        out["moves"], moves_err = _intent_moves(repo, floor, only)
        out["order"], order_err = _order(repo, floor)
        out["moves_error"] = moves_err or order_err
    return out


def newest_measurement(host: str, got: dict):
    """*host*'s newest MEASUREMENT in *got* (`reads`), or None: a save that read it, whether
    or not its golden moved. A golden commit the measurement log does not reach (before C89
    wrote `Intent-Match:`) is still a measurement, so the newer of the two counts."""
    h, m = got["history"].get(host), got["measured"].get(host)
    if h and (m is None or h["at"] > m["at"]):
        return {"at": h["at"], "sha": h["sha"], "commit": h["commit"], "source": h["source"],
                "how": SOURCE_WORDS.get(h["source"], h["source"].replace("_", " ") or "a save"),
                "changed": True, "baseline": False, "intent": h["intent"]}
    return m


def _after(a: dict, b: dict, order: dict) -> bool:
    """Whether commit *a* came after commit *b*: by their place in history where `_order`
    read both, else by commit time; a tie there is said as after (see `ORDER_BOUND`)."""
    if a["commit"] == b["commit"]:
        return False
    ia, ib = order.get(a["commit"]), order.get(b["commit"])
    if ia is not None and ib is not None:
        return ia < ib
    if ia is not None or ib is not None:
        return ia is not None                    # the one outside the window is the older
    return a["at"] >= b["at"]


def intent_state(host: str, got: dict) -> dict:
    """THE intent state of *host* (C532), from *got* (`reads`): what the Devices list draws
    in its row and the device page beside its live comparison. ``{"state", "words"}``, with
    ``"why"`` for the hover where there is one; `STATES` lists the states.

    The state its newest measurement recorded (`Intent-Match:`), only while nothing that
    measurement judged against has moved since: a commit after it to the device's intent,
    the monitoring profile or the template library makes it ``intent_moved``, naming what
    and when, because the recorded "departs" or "at intent" may no longer be true."""
    if got["error"]:
        return {"state": "unknown", "words": "unknown: the history could not be read"}
    if got["intent_error"]:
        return {"state": "unknown", "words": "unknown",
                "why": f"committed intent could not be listed ({got['intent_error']})"}
    if host not in got["with_intent"]:
        return {"state": "no_intent", "words": "no intent"}
    m = newest_measurement(host, got)
    if m is None:
        return {"state": "no_golden", "words": (
            f"no golden in the last {LOG_BOUND} golden commits" if got["history_full"]
            else "no golden")}
    recorded = dict(m["intent"])
    if got["moves_error"]:
        return {"state": "unknown", "words": "unknown",
                "why": (f"what moved its intent since it was measured could not be read "
                        f"({got['moves_error']}); it recorded {recorded['words']}")}
    own, network = got["moves"]["devices"].get(host), got["moves"]["network"]
    move = (own if network is None or (own and _after(own, network, got["order"]))
            else network)
    if move and _after(move, m, got["order"]):
        return {"state": "intent_moved", "words": "intent changed since measured",
                "since": _iso(move["at"]), "recorded": recorded,
                "why": (f"{move['what']} changed in {move['sha']} at {_iso(move['at'])}, "
                        f"after its last measurement ({m['sha']}, {_iso(m['at'])}). Its "
                        "device page compares it now; a "
                        "capture or Save All measures it again")}
    reach = got["moves"]["reach"]
    if reach is not None and m["at"] <= reach:
        return {"state": "unknown", "words": "unknown",
                "why": (f"whether its intent changed since it was measured ({_iso(m['at'])}) "
                        f"is not established: the read of intent commits reaches back "
                        f"{INTENT_BOUND} commits, to {_iso(reach)}; it recorded "
                        f"{recorded['words']}")}
    return recorded


def _status(reach: dict, ip: str) -> dict:
    row = ((reach or {}).get("devices") or {}).get(ip)
    if reach is None or not row:
        return {"state": "unknown", "words": "not probed yet"}
    return ({"state": "ok", "words": "Answering"} if row.get("answering") else
            {"state": "danger", "words": "Not answering", "since": row.get("since")})


def _iso(ts) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)) if ts else ""


STATES = ("at_intent", "departs", "intent_moved", "unrecorded", "no_intent", "no_golden",
          "pending", "unknown")


#: The Startup column (C593, board A: "Startup is the hourly startup check's last reading").
#: The check compares the `username` lines only, so the words say ACCOUNTS: "saved" would
#: claim the whole startup config matches running, which nothing measures.
STARTUP_WORDS = {
    "persisted": ("accounts saved", "the hourly check found every username line of the running "
                                    "config in startup; it compares accounts only"),
    "not_persisted": ("accounts not saved", "the hourly check found a username line of the "
                                            "running config missing from startup: a reload "
                                            "would boot without it"),
    "unknown": ("unknown", "the hourly check could not read it"),
}
STARTUP_NEVER = {"state": "never", "words": "not checked",
                 "why": "the hourly startup check has not recorded this device"}


def _startup_states(list_name: str, errors: list) -> dict:
    """``{hostname: {"state", "words", "why"}}`` from the hourly startup check's ONE stored
    record; an unreadable record is said in *errors*, never drawn as "not checked"."""
    from modules.nsot import startup_check

    try:
        results = startup_check.read_results() or {}
    except (OSError, ValueError) as exc:
        errors.append(f"the startup check's record could not be read ({exc}): Startup is "
                      "unknown")
        return {}
    at = results.get("at")
    out = {}
    for d in results.get("devices") or []:
        if d.get("list") != list_name:
            continue
        words, why = STARTUP_WORDS.get(d.get("state"), STARTUP_WORDS["unknown"])
        out[d.get("device")] = {"state": d.get("state", "unknown"), "words": words,
                                "why": why + (f": {d['detail']}" if d.get("detail") else ""),
                                "at": _iso(at) if at else ""}
    return out


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
    got = reads(ref.repo_dir)
    history, hist_err = got["history"], got["error"]
    if hist_err:
        errors.append(f"the golden history could not be read ({hist_err}): intent states and "
                      "measurement ages are unknown")
    if got["intent_error"]:
        errors.append(f"committed intent could not be listed ({got['intent_error']})")
    if got["moves_error"]:
        errors.append(f"what moved intent since each measurement could not be read "
                      f"({got['moves_error']}): intent states are unknown")
    reach, _at, _why = _cached("reachability")
    try:
        pending = manifest.pending_devices(ref.repo_dir)
    except Exception as exc:                      # noqa: BLE001
        pending = []
        errors.append(f"pending onboardings could not be read ({exc})")

    # Drained, MEASURED (modules/drained.py, C551): one cached read for the whole network.
    from modules import drained as _drained
    try:
        drained_now = _drained.current(ref.name)
    except Exception as exc:                      # noqa: BLE001
        drained_now = {}
        errors.append(f"whether a device is drained could not be measured ({exc})")

    startup = _startup_states(ref.name, errors)

    rows = []
    for dev in inventory:
        host = dev.get("hostname", "")
        h = history.get(host)
        m = newest_measurement(host, got)
        intent = intent_state(host, got)          # THE state, the device page's too (C532)
        rows.append({"name": host, "pending": False, "status": _status(reach, dev.get("ip", "")),
                     "address": dev.get("ip", ""), "platform": platform_for_device(dev) or "",
                     "role": dev.get("role", ""), "intent": intent,
                     "startup": startup.get(host) or STARTUP_NEVER,
                     "drained": (_drained.words(drained_now[host]) + "; " + _drained.HOVER
                                 if host in drained_now
                                 else ""),
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
                     "startup": {"state": "none", "words": "none", "why": "not onboarded yet"},
                     "drained": "", "intent": {"state": "pending", "words": "pending: not reached yet"}})

    total = len(rows)
    counts = {s: sum(1 for r in rows if r["intent"]["state"] == s) for s in STATES}
    platforms = sorted({r["platform"] for r in rows if r["platform"]})
    q = (q or "").strip().lower()
    shown = [r for r in rows
             if (not q or q in r["name"].lower() or q in (r["address"] or "").lower())
             and (not state or r["intent"]["state"] == state)
             and (not platform or r["platform"] == platform)]
    return {"list": ref.name, "error": "; ".join(errors), "rows": shown, "total": total,
            "managed": len(inventory),
            "counts": counts, "platforms": platforms, "q": q, "state": state,
            "platform": platform, "bound": LOG_BOUND}


def matching(ref, values):
    """The devices an action on Devices' selection names when the selection is ALL MATCHING
    (the operator's walk, 2026-10-18, B): None unless *values* (a request's) carry
    ``match=1``; then every device of *ref* the list shows under the search and filters they
    carry that can be ticked (a pending onboarding cannot), resolved HERE from the same
    `listing` the page drew. A ``device`` sent beside ``match`` is never read, so the page's
    names neither widen nor narrow it, and a selection of 900 never travels as 900 names."""
    if (values.get("match") or "") != "1":
        return None
    got = listing(ref, q=values.get("q", ""), state=values.get("state", ""),
                  platform=values.get("platform", ""))
    return [r["name"] for r in got["rows"] if not r["pending"] and r["name"]]
