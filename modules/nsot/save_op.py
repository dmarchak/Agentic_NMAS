"""SAVE, from the Devices page (C593; 7.4's board C, "one Save does both", approved
2026-10-04): for a selection, each device saves its running config to startup (its own
`write memory`), the startup is read back, and the running config is recorded as its golden,
one commit for the batch (`Source: save`). Its running configuration is not changed, so what
the tool records and what a reboot brings back are the same.

One operation built from the two that exist, never a third copy of either: the device-side save
and read-back are `onboard.persist_on_device` (with its record, `_record_native_persist`), the
device checks and their hash `persist_op.row_checks`, and the golden's read and record are the
capture's (`routes.golden._capture_entry`, `repo.save_golden`). Recording without saving is not
offered here: the record would say one thing and a reboot bring another (the device page's
Capture still records a hand change alone).

A device-changing operation like every other: a plan read from stored records only (the
inventory, the hourly startup check, reachability, the holds), confirmed by its hash as a
verified person; a job holding each device while it saves; the read-back as its verify;
nothing to roll back (a save copies running to startup as it is); the record is the commit, and
each device's persist row.
"""

import hashlib
import json
import logging
import threading

log = logging.getLogger(__name__)

#: The steps, in order, as the manual's How it works page names them.
STEPS = ("plan", "confirm", "hold", "save", "read_back", "read_running", "release", "record")
#: Devices worked at once, each on its own worker holding it: a session for the save and its
#: read-back, then the capture's read of the running config. 6, Show commands' cap (the
#: operator, 2026-10-09, C605; it was 8, half the capture's): not measured on the host, where a
#: timing of a Save every device would set it.
WORKERS = 6
#: What a plan says of each device, the page's groups in the order it leads with.
GROUPS = ("save", "not_answering", "held", "refused")
#: What a run says of each device; the first two are the good ones.
OUTCOMES = ("saved_recorded", "saved_unchanged", "not_persisted", "unread", "held", "refused",
            "not_answering")
GOOD = ("saved_recorded", "saved_unchanged")
#: The commit's `Source:`: a selection's, and the whole network's, which is Save All's (the
#: baseline decision wants a baseline for it, and Devices and History read it as Save All).
SOURCE = "save"
SOURCE_FLEET = "save_all"
#: Each device's row on the run's stepper (C605, board approved 2026-10-09), as
#: `device_actions.stepper` reads them, ``(key, words, waits, names)``, each name noted as its
#: step BEGINS: "save" by `_save_one`, "read_back" by `onboard.persist_on_device`, the rest
#: here. "commit_wait" is a device through its turn, never counted as running.
DEVICE_STEPS = (
    ("save", "Save to startup", "the device's own write memory", ("save",)),
    ("read_back", "Read back", "the startup config, and the running config's accounts",
     ("read_back",)),
    ("read_running", "Read running", "the running config, to record", ("read_running",)),
    ("commit_wait", "Waiting for the commit", "every other device's turn", ("commit_wait",)),
    ("recorded", "Recorded", "", ("recorded",)),
)
_STEP_NAMES = {n for s in DEVICE_STEPS for n in s[3]}

_LIVE: dict = {}
_LIVE_LOCK = threading.Lock()
#: Runs whose rows are kept, newest last: a run's rows are read until its result is drawn.
_LIVE_KEPT = 20


def _reachability(list_name: str) -> dict:
    """``{hostname: answering}`` for *list_name* from the reachability reader's stored value
    (one read; its devices are keyed by address and name their list)."""
    from modules import reader_job

    got = reader_job.read_cached("reachability")
    good = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    return {d["hostname"]: bool(d.get("answering"))
            for d in (good.get("devices") or {}).values()
            if d.get("hostname") and d.get("list") == list_name}


def _startup(list_name: str) -> dict:
    """``{hostname: state}`` from the hourly startup check's stored record (one read);
    ``{"_unreadable": why}`` when the record cannot be read, a different fact from none."""
    from modules.nsot import startup_check

    try:
        results = startup_check.read_results() or {}
    except (OSError, ValueError) as exc:
        return {"_unreadable": f"the startup check's record could not be read ({exc})"}
    return {d.get("device"): d.get("state", "unknown") for d in results.get("devices") or []
            if d.get("list") == list_name}


def plan(list_name: str, hostnames: list) -> dict:
    """What Save would do for *hostnames*, from stored records only (no device is asked):
    ``{"devices": [{"host", "group", "why", "startup", "hash"}], "counts", "save", "hash",
    "fleet", "startup_unreadable"}``. A device not in the inventory, without a driver or a
    credential, held by another operation or not answering at the last reachability read is
    left out, named with why."""
    from modules.nsot import device_ops, persist_op
    from modules.nsot.restore import _devices_of

    inventory = [d for d in _devices_of(list_name) if d.get("hostname")]
    by_host = {d["hostname"]: d for d in inventory}
    answering = _reachability(list_name)
    startup = _startup(list_name)
    out = []
    for host in dict.fromkeys(h for h in hostnames or [] if h):
        row = by_host.get(host)
        if row is None:
            out.append({"host": host, "group": "refused", "startup": "", "hash": "",
                        "why": f"{host} is not in {list_name}'s inventory"})
            continue
        refused, digest = persist_op.row_checks(list_name, host, row)
        entry = {"host": host, "startup": startup.get(host, "never"), "hash": digest}
        busy = device_ops.busy_text(list_name, host)
        if refused:
            entry.update(group="refused", why="; ".join(refused.values()))
        elif busy:
            entry.update(group="held", why=busy)
        elif answering.get(host) is False:
            entry.update(group="not_answering",
                         why="not answering at the last reachability read")
        else:
            entry.update(group="save", why="")
        out.append(entry)
    to_save = [d for d in out if d["group"] == "save"]
    counts = {g: sum(1 for d in out if d["group"] == g) for g in GROUPS}
    digest = hashlib.sha256(json.dumps(sorted((d["host"], d["hash"]) for d in to_save))
                            .encode()).hexdigest()[:16]
    return {"list": list_name, "devices": out, "counts": counts,
            "save": [d["host"] for d in to_save], "hash": digest,
            "startup_unreadable": startup.get("_unreadable", ""),
            # The whole managed fleet saved together may earn a baseline, as Save All did;
            # `save_golden` measures whether it does.
            "fleet": bool(to_save) and {d["host"] for d in to_save} == set(by_host)}


def live(job_id: str) -> dict:
    """``{host: {"state", "trail", "detail"}}`` of a running Save, in the order the devices
    joined it, for the card that redraws as each device steps. A device holding its hold is
    read from the hold itself (`device_ops.holder`), its trail live; the trail kept here is
    what it reached when it let go."""
    with _LIVE_LOCK:
        return {h: dict(v, trail=list(v.get("trail") or ()))
                for h, v in (_LIVE.get(job_id) or {}).items()}


def _mark(job_id: str, host: str, state: str, *, trail=None, step: str = "",
          detail: str = "") -> None:
    """*host*'s state in the run; *trail* replaces its kept trail, *step* appends one."""
    if not job_id:
        return
    import time

    with _LIVE_LOCK:
        if job_id not in _LIVE:
            _LIVE[job_id] = {}
            for old in list(_LIVE)[:-_LIVE_KEPT]:
                _LIVE.pop(old, None)
        row = _LIVE[job_id].setdefault(host, {"state": state, "trail": [], "detail": ""})
        row["state"] = state
        if trail is not None:
            row["trail"] = [list(t) for t in trail]
        if step:
            row["trail"].append([step, time.time()])
        if detail:
            row["detail"] = detail


def _trail_of(list_name: str, host: str) -> list:
    """The steps *host*'s hold has noted, Save's own names only (``[[name, at], ...]``)."""
    from modules.nsot import device_ops

    progress = (device_ops.holder(list_name, host) or {}).get("progress") or {}
    return [[n, a] for n, a in progress.get("trail") or [] if n in _STEP_NAMES]


def _save_one(row: dict, actor: str, persist=None, record=None) -> dict:
    """One held device's save and read-back: ``{"ok", "state", "detail"}``, recorded."""
    from modules.device import decrypt_field
    from modules.nsot import credential_rotation as cr
    from modules.nsot import device_ops, onboard

    device_ops.note("save")
    out = (persist or onboard.persist_on_device)(
        row.get("ip", ""), row.get("username", "admin"), decrypt_field(row.get("password", "")),
        cr.enable_secret(row), row.get("device_type", ""))
    (record or onboard._record_native_persist)(row["hostname"], out, actor, via="save")
    return out


def _outcome(host: str, outcome: str, detail: str = "") -> dict:
    return {"host": host, "outcome": outcome, "detail": detail}


def run(list_name: str, hostnames: list, actor: str, confirmed_hash: str, *, job_id: str = "",
        persist=None, record=None, read_one=None, save_golden=None) -> dict:
    """Save the confirmed selection, as *actor*: the plan made again and refused if its hash
    moved; each device held by its own worker (at most `WORKERS` at once), saved, read back and,
    when the read-back matched, read for its running config, then released; the ones read are
    recorded in one commit. Each device's
    outcome is one of `OUTCOMES`: a device whose read-back did not match is ``not_persisted``
    and is NOT recorded (the record would claim what a reboot would not bring back)."""
    from concurrent.futures import ThreadPoolExecutor

    from modules.nsot import device_ops
    from modules.nsot import repo as R
    from modules.nsot.restore import _devices_of
    from routes.golden import _capture_entry, _repo_for

    p = plan(list_name, hostnames)
    if confirmed_hash != p["hash"]:
        return {"ok": False, "state": "refused", "plan": p, "outcomes": [], "commit": "",
                "save": {},
                "detail": (f"the selection's plan changed since you confirmed it "
                           f"({confirmed_hash} -> {p['hash']}): a device's address, driver, "
                           "account, hold or reachability moved. Nothing was sent; open Save "
                           "again.")}
    outcomes = {d["host"]: _outcome(d["host"], d["group"], d["why"])
                for d in p["devices"] if d["group"] != "save"}
    inventory = {d["hostname"]: d for d in _devices_of(list_name) if d.get("hostname")}
    # A device the manifest does not know cannot be recorded, and `save_golden` refuses the
    # WHOLE batch for one: left out here, named, before anything is sent. Here, not in the plan:
    # each lookup reads the manifest, per-device work the job may do and a request may not.
    repo_dir = _repo_for(list_name)
    to_save = []
    for host in p["save"]:
        d = inventory[host]
        if R.resolve_identity(repo_dir, R.GoldenItem(host, "", d.get("ip", ""),
                                                     netbox_id=d.get("_netbox_id"),
                                                     device_uid=d.get("device_uid", ""))):
            to_save.append(host)
            _mark(job_id, host, "waiting")
        else:
            outcomes[host] = _outcome(host, "refused", (
                f"{host} is not in {list_name}'s manifest, so its golden has nothing to attach "
                "to: onboard or adopt it first. Nothing was sent to it"))
    def one(host):
        """One device on its own worker, which HOLDS it: a session write needs the device held
        by the thread that writes (`device_ops.may_write`), so the job thread cannot hold it
        for the worker. ``(host, outcome or None, (entry, text) or None)``."""
        d = inventory[host]
        try:
            with device_ops.hold(list_name, host, "save", actor,
                                 detail="write memory, then the golden", ip=d.get("ip", "")):
                # Running from here; its steps are read from the hold while it holds, and the
                # trail it reached is kept when it lets go (C605).
                _mark(job_id, host, "running")
                try:
                    got = _save_one(d, actor, persist, record)
                except Exception as exc:              # noqa: BLE001 (that device's outcome)
                    got = {"ok": False, "state": "unknown",
                           "detail": f"{type(exc).__name__}: {exc}"}
                if not got.get("ok"):
                    detail = got.get("detail") or got.get("state", "")
                    _mark(job_id, host, "not_persisted", trail=_trail_of(list_name, host),
                          detail=detail)
                    return host, _outcome(host, "not_persisted", detail), None
                # The running config read while still held: what is recorded is what the
                # device ran when it saved.
                device_ops.note("read_running")
                try:
                    entry, text = (read_one or _capture_entry)(list_name, repo_dir, d)
                except Exception as exc:              # noqa: BLE001 (that device's outcome)
                    entry, text = {"device": host, "read": False,
                                   "error": f"{type(exc).__name__}: {exc}"}, None
                entry.pop("read_phases", None)
                trail = _trail_of(list_name, host)
            if not entry.get("read") or text is None:
                detail = ("saved to startup; its running config could not be read to record: "
                          + (entry.get("error") or "no reason was recorded"))
                _mark(job_id, host, "unread", trail=trail, detail=detail)
                return host, _outcome(host, "unread", detail), None
            # Through its turn: released, waiting for the batch's one commit.
            _mark(job_id, host, "through", trail=trail, step="commit_wait")
            return host, None, (entry, text)
        except device_ops.DeviceBusy as exc:
            _mark(job_id, host, "held", detail=f"{exc}")
            return host, _outcome(host, "held", f"{exc}. Nothing was sent to it"), None

    read = {}
    if to_save:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(to_save)),
                                thread_name_prefix="save") as pool:
            for host, outcome, got in pool.map(one, to_save):
                if outcome:
                    outcomes[host] = outcome
                else:
                    read[host] = got
    items = []
    for host in to_save:
        if host in read:
            entry, text = read[host]
            d = inventory[host]
            items.append(R.GoldenItem(host, text, d.get("ip", ""), netbox_id=d.get("_netbox_id"),
                                      device_uid=d.get("device_uid", ""),
                                      platform=entry.get("platform", "")))
    commit, save = "", {}
    if items:
        # The whole network saved together is Save All, and `save_all` is the source the
        # baseline decision WANTS a baseline for (`repo._baseline_wanted`); `save` would want
        # one only when two goldens changed, so an in-sync network never got its restore point
        # (the operator, 2026-10-09: "v2 save all devices needs to add a new baseline"). Earned
        # or denied by measurement there: coverage of the inventory and every device at intent.
        save = (save_golden or R.save_golden)(
            list_name, items, source=SOURCE_FLEET if p["fleet"] else SOURCE, actor=actor,
            allow_new=False, inventory_size=len(inventory) if p["fleet"] else 0,
            baseline=None if p["fleet"] else False)
        commit = (save.get("commit") or "")[:12]
        refused_save = {r["device"]: r for r in (save.get("refused") or [])}
        for it in items:
            host = it.hostname
            if host in refused_save:
                outcomes[host] = _outcome(host, "unread", "saved to startup; not recorded: "
                                          + refused_save[host]["reason"])
            elif not save.get("ok"):
                outcomes[host] = _outcome(host, "unread", "saved to startup; not recorded: "
                                          + (save.get("error") or "the record failed"))
            else:
                outcomes[host] = _outcome(host, "saved_recorded"
                                          if host in (save.get("changed") or [])
                                          else "saved_unchanged")
            _mark(job_id, host, outcomes[host]["outcome"],
                  step="recorded" if outcomes[host]["outcome"] in GOOD else "",
                  detail=outcomes[host]["detail"])
    rows = [outcomes[d["host"]] for d in p["devices"]]
    good = sum(1 for r in rows if r["outcome"] in GOOD)
    ok = bool(rows) and good == len(rows)
    log.info("save: %s saved and recorded %d of %d in %s (commit %s)", actor, good, len(rows),
             list_name, commit or "none")
    return {"ok": ok, "state": "done" if ok else ("partial" if good else "failed"), "plan": p,
            "outcomes": rows, "commit": commit, "fleet": p["fleet"],
            "save": {k: save[k] for k in ("ok", "error", "baseline", "baseline_denied", "tags",
                                          "decision_only") if k in save}}


def start(list_name: str, hostnames: list, actor: str, confirmed_hash: str) -> dict:
    """Refuse now (a moved plan, nothing to save), or start Save as a job: ``{"refused"}`` or
    ``{"job"}``. A job because each device is an SSH session and a fleet is many."""
    from modules.nsot import capture_job

    p = plan(list_name, hostnames)
    if confirmed_hash != p["hash"]:
        return {"refused": (f"the selection's plan changed since you saw it ({confirmed_hash} "
                            f"-> {p['hash']}). Nothing was sent; open Save again.")}
    if not p["save"]:
        return {"refused": "nothing in the selection can be saved now; each device is named "
                           "with why. Nothing was sent."}

    from modules import invalidation

    def work(job_id):
        return run(list_name, hostnames, actor, confirmed_hash, job_id=job_id)

    # What it announces is declared once, as its announcer's keys (`invalidation.ANNOUNCERS`).
    return {"job": capture_job.start(list_name, f"save {len(p['save'])} device(s)", actor, work,
                                     kind="save", announce_keys=invalidation.ANNOUNCERS["save"],
                                     announcer="save")}
