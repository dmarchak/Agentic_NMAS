"""Golden configs: THE capture (its preview job and its apply) and THE restore plan, with no
routes of their own. Each device page's Capture… and Devices › Save (`routes/device_v2.py`,
`modules/save_page.py`) start and apply a capture through `start_capture_preview` and
`apply_captures`; a device's Restore from… and History › Baselines › Re-apply… plan through
`restore_plan`.

Today's routes here left at 7.8 (2026-10-17, P7-27; restore point tag `pre-remove/v1-pages`)
with today's index, their one caller: the golden timeline's JSON (GET /golden/history/<host>,
/golden/version/<host>, /golden/diff/<host>; the device's History tab and
`/v2/history/commit/<sha>` draw each version, a reveal recorded first) and the capture's
(POST /golden/capture/preview and /apply, GET /golden/capture/preview/<job>; today's Save All
Configs and Capture devices with no golden).
"""

import logging
import os

from flask import request

log = logging.getLogger(__name__)


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


# Today's Baselines panel and its routes (GET /golden/baselines, GET /golden/restore_points/<host>,
# POST /golden/restore/preview and /golden/restore/apply) left at 7.8 (2026-10-17, P7-21) with
# today's Git tab, as did today's device page's Restore from… that bounced to the panel's restore
# dialog. History › Baselines draws the network's baselines from the `baseline-usability` reader
# and Re-apply… restores every device a baseline holds as one batch (`routes/v2.py`), and a
# device's Restore from… (`routes/device_v2.py`) chooses its moment, previews and confirms; both
# through THE restore plan below and a restore job (`deploy_job.start_restore`).


def restore_points_for(list_name: str, hostname: str, checked: int = None) -> list:
    """Where *hostname* can be restored from, newest first, each with its credential state at
    that moment (``current``, ``refused``, ``silent``: an account added back, ``no_golden``).
    ONE reading for the v2 device page's chooser (board 9). Reads only.

    *checked*: check the credential of only the newest so many moments (the v2 chooser draws
    five; checking all 32 of r2's took 5.5 to 7.3 s on the host, C399); the rest are
    ``unchecked``, never called current."""
    from modules.nsot.repo import device_restore_points
    from modules.nsot.restore import baseline_credential_gaps

    from modules.nsot import manifest as _mf
    from modules.nsot.repo import committed_golden_for, git

    repo = _repo_for(list_name)
    points = device_restore_points(repo, hostname)
    # Which moments hold the SAME golden as now: every golden commit is tagged, so the newest
    # tag is usually today's, and re-applying it sends nothing, as the golden now does (the
    # program is a moment's golden against today's). One blob id per moment, compared.
    rel = committed_golden_for(repo, _mf.find_by_name(repo, hostname)[1]).get("path") or ""

    def blob(ref):
        rc, out, _e = git(repo, "rev-parse", f"{ref}:{rel}") if rel else (1, "", "")
        return out.strip() if rc == 0 else ""
    now = blob("HEAD")
    for i, point in enumerate(points):
        point["same_as_now"] = bool(now) and blob(point["ref"]) == now
        if point["kind"] == "head":
            point["credential"] = "current"
            continue
        if checked is not None and i >= checked:
            point["credential"] = "unchecked"
            continue
        gaps = baseline_credential_gaps(repo, point["ref"], list_name, [hostname])
        if hostname in gaps["no_golden"]:
            point["credential"] = "no_golden"
        elif hostname in gaps["silent"]:
            point["credential"] = "silent"
        elif hostname in set(gaps["refused"]) | set(gaps["guarded"]):
            point["credential"] = "refused"
        else:
            point["credential"] = "current"
    return points


def _read_running(device: dict, phases: dict = None) -> tuple:
    """``(running_config, error)`` read NOW from *device* (the list's own
    row, carried, never looked up in the active list). *phases*, when given,
    is filled with where the time went (C188's second question, the
    operator: the same nine reads took 40.9 s and then 13.7 s three minutes
    apart, so the time is somewhere not yet measured): ``connect_s`` (the SSH
    session opened and `enable`), ``read_s`` (`show running-config`) and
    ``close_s`` (the disconnect). A read that failed before `show` ran has
    ``read_s`` None: the time was all spent connecting."""
    import time

    from modules import config_read
    from modules.connection import with_temp_connection

    marks = {}

    def read(conn):
        marks["read_start"] = time.monotonic()
        try:
            # ONE read, waited for and checked: never the general command
            # runner, whose retry on the same session stitched r2's capture
            # (2026-10-01, modules/config_read.py).
            return config_read.read(conn, device.get("hostname", ""))
        finally:
            marks["read_end"] = time.monotonic()

    started = time.monotonic()
    # A temporary connection, closed when the read ends. It was a persistent
    # connection in a fresh pool nobody kept, so every preview and apply left
    # a session open until the device timed it out (C97). So no capture
    # reuses a session: the preview and the apply each open a fresh one.
    try:
        text = with_temp_connection(device, read)
        error = "" if text else "the device returned an empty running config"
    except Exception as exc:                  # noqa: BLE001
        text, error = None, f"{type(exc).__name__}: {exc}"
    ended = time.monotonic()
    if phases is not None:
        opened = marks.get("read_start", ended)
        phases.update({
            "connect_s": round(opened - started, 1),
            "read_s": (round(marks["read_end"] - marks["read_start"], 1)
                       if "read_end" in marks else None),
            "close_s": (round(ended - marks["read_end"], 1) if "read_end" in marks else None)})
        if not text:
            # WHERE it failed and WHY, kept at the moment it is known (the
            # operator, 2026-09-29: s3's connect failed and the log said only
            # "not reached", the result only "skipped"; the reason sat in a
            # traceback under an address, the C152 shape).
            phases["failed_in"] = "connect" if "read_start" not in marks else "show running-config"
            phases["error"] = error
    return (text, "") if text else (None, error)


def _capture_entry(list_name: str, repo: str, device: dict) -> tuple:
    """``(entry, running_config)`` for one device read for a capture: what
    its golden would become, and how that compares with its committed INTENT
    (C89). The raw config is returned BESIDE the entry, never in it, so it
    cannot reach a response."""
    import difflib

    from modules.nsot.intent_match import intent_match
    from modules.nsot.platform import platform_for_device
    from modules.nsot.repo import golden_body
    from routes.deploy import _capture_hash, _captured_config

    from modules.nsot.device_ops import busy_text

    host, ip = device.get("hostname", ""), device.get("ip", "")
    platform = platform_for_device(device)
    busy = busy_text(list_name, host)                          # C99
    phases = {}
    text, error = _read_running(device, phases=phases)
    if text is None:
        return {"device": host, "read": False, "error": error, "platform": platform,
                "busy": busy, "read_phases": phases}, None
    current = _captured_config(repo, host)
    # Judged against the committed golden too: a read far larger than it is
    # two configurations, whatever else it looks like (modules/config_read.py).
    from modules import config_read
    unreliable = config_read.problems(text, host, previous=current)
    if unreliable:
        return {"device": host, "read": False, "platform": platform, "busy": busy,
                "error": (f"{config_read.UNRELIABLE}: " + "; ".join(unreliable)
                          + ". Nothing will be recorded for it"),
                "read_phases": phases}, None
    incoming = golden_body(host, ip, text)
    # The shrink guard, judged at the preview (C310): what save_golden will
    # say, so a person gives a reason where intent does not explain it.
    from modules.nsot.repo import lost_sections
    shrink = lost_sections(current, incoming) if current else {}
    intent_now = intent_match(repo, list_name, host, text, platform)
    structure = ({"lost": ", ".join(f"{k} {b}->{a}" for k, (b, a) in sorted(shrink.items())),
                  "explained": intent_now.get("state") == "match"} if shrink else {})
    # The device's own self-signed certificate is regenerated at boot: drawn as
    # one labelled line, never as its hex. The golden is recorded verbatim.
    # Comment lines likewise (2026-10-02): one labelled line, the golden still verbatim.
    from modules.nsot.normalize import (comment_note, self_signed_note, strip_comments,
                                        strip_self_signed_certs)
    diff = [l for l in difflib.unified_diff(strip_comments(strip_self_signed_certs(current)),
                                             strip_comments(strip_self_signed_certs(incoming)),
                                             lineterm="", n=1)
            if not l.startswith(("---", "+++"))]
    note = self_signed_note(current, incoming)
    if note:
        diff.append(note)
    c_note = comment_note(current, incoming)
    if c_note:
        diff.append(c_note)
    return ({"device": host, "read": True, "error": "", "platform": platform,
             "capture_hash": _capture_hash(text), "changed": incoming != current,
             "diff": diff, "intent": intent_now, "structure": structure,
             "busy": busy, "read_phases": phases},
            text)


#: How many devices a capture reads AT ONCE (C188). One per device at the
#: fleet size measured: nine, 2026-09-29, 101 s read one after another with
#: the slowest (s3) at 23-24 s, so concurrency makes the wall time the
#: slowest device's. The cap stops a large list opening every session at once;
#: it is NOT a measured optimum, and is re-derived when a list that large is
#: measured. The per-device limit is open_ssh's own budget (vty lines), which
#: a capture's one session per device stays inside.
CAPTURE_READ_WORKERS = 16


def _read_all(list_name: str, repo: str, devices: list, progress=None) -> tuple:
    """``([(entry, text)] in the devices' order, timing)``: every device read
    CONCURRENTLY, each timed, the slowest named, because a parallel read is
    only as fast as its slowest member (the operator, C188). A read that
    raises is that device's `read: False`, never the whole capture's.
    *progress*, when given, is called ``(done, total, waiting_on)`` as each
    device finishes, for the in-flight panel (step 2)."""
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def one(device):
        started = time.monotonic()
        try:
            entry, text = _capture_entry(list_name, repo, device)
        except Exception as exc:              # noqa: BLE001
            entry, text = ({"device": device.get("hostname", ""), "read": False,
                            "error": f"{type(exc).__name__}: {exc}", "platform": "",
                            "busy": ""}, None)
        # Where this device's time went, kept for the timing and the log and
        # never in the entry the preview is built from.
        return entry, text, round(time.monotonic() - started, 1), entry.pop("read_phases", None)

    workers = max(1, min(CAPTURE_READ_WORKERS, len(devices)))
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="capture-read") as pool:
        futures = {pool.submit(one, d): i for i, d in enumerate(devices)}
        read = [None] * len(devices)
        for n, fut in enumerate(as_completed(futures), 1):
            read[futures[fut]] = fut.result()
            if progress is not None:
                progress(n, len(devices), [devices[i].get("hostname", "")
                                           for i in range(len(devices)) if read[i] is None])
    per = {e["device"]: s for e, _t, s, _p in read}
    phases = {e["device"]: p for e, _t, _s, p in read if p}
    slowest = max(per, key=per.get) if per else ""
    timing = {"wall_s": round(time.monotonic() - started, 1), "workers": workers,
              "series_s": round(sum(per.values()), 1), "per_device_s": per,
              "slowest": slowest, "slowest_s": per.get(slowest, 0),
              "phases_s": phases,
              "connect_series_s": round(sum((p["connect_s"] for p in phases.values()), 0.0), 1),
              "read_series_s": round(sum((p["read_s"] for p in phases.values()
                                          if p["read_s"] is not None), 0.0), 1)}
    for host, p in phases.items():
        if p.get("failed_in"):
            log.warning("capture: %s could not be read after %.1f s: %s failed after %.1f s: %s",
                        host, per.get(host, 0), p["failed_in"],
                        p["connect_s"] if p["failed_in"] == "connect" else (p["read_s"] or 0.0),
                        p.get("error") or "no reason recorded")
            continue
        log.info("capture: %s read in %.1f s: connect %.1f s, show running-config %s, "
                 "disconnect %s", host, per.get(host, 0), p["connect_s"],
                 "not reached" if p["read_s"] is None else f"{p['read_s']:.1f} s",
                 "not reached" if p["close_s"] is None else f"{p['close_s']:.1f} s")
    log.info("capture: read %d device(s) with %d worker(s) in %.1f s (one after another: "
             "%.1f s, of which connecting %.1f s and reading %.1f s); slowest %s at %.1f s",
             len(devices), workers, timing["wall_s"], timing["series_s"],
             timing["connect_series_s"], timing["read_series_s"], slowest or "-",
             timing["slowest_s"])
    return [(e, t) for e, t, _s, _p in read], timing


def _close_handed_off(approvals: dict, outcomes: list, list_name: str = "") -> dict:
    """Close the queue items a capture was handed ({host: [ids]}), ONLY for
    devices it recorded: an item closed for a device that moved, could not be
    read or was busy would be the queue claiming work that did not happen,
    and one left pending for a recorded device teaches the operator to clear
    the queue by rejecting things."""
    from modules.approval_queue import mark_done
    from modules.identity import request_actor

    recorded = {o["device"] for o in outcomes if o.get("outcome") in ("captured", "unchanged")}
    closed, left = [], []
    for host, ids in (approvals or {}).items():
        for entry_id in (ids or []):
            if host in recorded:
                out = mark_done(entry_id, f"Recorded {host}'s running config as its golden "
                                          f"through the capture operation, confirmed by "
                                          f"{request_actor()}", actor=request_actor(),
                                list_name=list_name)        # its own network's queue (C487)
                (closed if out.get("ok") else left).append(entry_id)
            else:
                left.append(entry_id)
    return {"closed": closed, "left_pending": left}


def last_baseline_if_current(repo: str) -> dict:
    """The newest EARNED baseline when no golden has been committed since it (its tag's golden
    tree is HEAD's), as ``{tag, at, actor}``, else None (C539 (2)): a Save All that finds every
    device unchanged then repeats it, and the preview says so. Withdrawn and denied baselines
    are never "taken"."""
    from modules.nsot import repo as R

    try:
        newest = next((b for b in R.list_baselines(repo)
                       if not b.get("withdrawn") and not b.get("deleted")
                       and b.get("decision") == "earned"), None)
        if newest is None:
            return None
        tree_at = R.git(repo, "rev-parse", f"{newest['commit']}:golden")[1].strip()
        tree_now = R.git(repo, "rev-parse", "HEAD:golden")[1].strip()
        if not tree_at or tree_at != tree_now:
            return None
        actor = R.git(repo, "log", "-1", "--format=%(trailers:key=Actor,valueonly,separator=%x2C)",
                      newest["commit"])[1].strip()
        return {"tag": newest["tag"], "at": newest.get("created", ""), "actor": actor}
    except Exception as exc:                          # noqa: BLE001
        log.info("capture preview: the last baseline could not be read (%s); no repeat is said",
                 exc)
        return None


def start_capture_preview(list_name: str, inventory: list, devices: list, *, fleet: bool,
                          excluded: list = None) -> str:
    """Start the capture preview's reads as a job and return its id: THE start, for the v2
    device page's Capture (7.3) and Devices › Save alike (today's /golden/capture/preview, its
    third caller, left at 7.8 with today's index, P7-27).

    C188 step 2: the reads run as a JOB, and the request answers at once. It no longer
    waits on a device, so no edge limit can end it (107 s for nine devices read in series,
    past Cloudflare's 100 s). What needs the request (who would confirm) is decided HERE,
    before the thread."""
    from modules import identity, op_progress
    from modules.nsot import capture_job
    from modules.outbound import mask_payload
    from modules.preview_confirm import capture_preview as _parts
    from modules.preview_confirm import confirm_part

    repo = _repo_for(list_name)
    confirm = confirm_part(request, "approve")
    who = identity.identify(request)
    actor = who.actor if who.is_identified else "an unidentified viewer"

    def work(job_id):
        def progress(done, total, waiting):
            op_progress.update(job_id, phase=(
                f"read {done} of {total} device(s)"
                + (f"; waiting on {', '.join(waiting)}" if waiting else "")))
        op_progress.update(job_id, phase=f"reading {len(devices)} device(s) at once")
        read, timing = _read_all(list_name, repo, devices, progress=progress)
        entries = [e for e, _t in read]
        preview = _parts(entries, fleet=fleet, inventory=inventory, confirm=confirm,
                         not_read=excluded or [], timing=timing,
                         repeats=last_baseline_if_current(repo) if fleet else None)
        # The preview alone: it draws each device's read, and its
        # `select_data` carries the hash the confirm is bound to. The raw
        # reads are not sent. `nothing` is always carried (empty here): one
        # payload shape whether or not a scope found anything.
        return mask_payload({"list": list_name, "fleet": fleet, "preview": preview,
                             "nothing": ""})

    return capture_job.start(list_name, f"{list_name}: {len(devices)} device(s)", actor, work)


def acknowledged_reasons(given: dict) -> tuple:
    """``(acknowledged, problem)``: a person's reason per device for a shrink intent does not
    explain (C310), each in the shape of a reason, recorded on the commit as theirs. The one
    check today's capture and v2's Capture card (C486) share; *problem* names the device."""
    from modules.nsot.authorisation import reason_problem

    acknowledged = {}
    for host, reason in (given or {}).items():
        problem = reason_problem({"reason": str(reason or "").strip(),
                                  "line": f"{host}'s structural change"})
        if problem:
            return {}, f"{host}: {problem}"
        acknowledged[host] = str(reason).strip()
    return acknowledged, ""


def apply_captures(list_name: str, confirmations: dict, *, fleet: bool, acknowledged: dict,
                   approvals: dict, mode: str = "") -> dict:
    """Record the confirmed captures: THE apply, for the v2 device page's Capture (7.3)
    (today's `/golden/capture/apply`, its other caller, left at 7.8 with today's index,
    P7-27). Each device is READ AGAIN, and one whose running config moved since the preview is
    refused. One commit, as the verified person, through `save_golden()`, which writes the
    computed `Intent-Match:` trailer and takes a baseline only for a whole-fleet capture with
    every device at its committed intent (C89 (c)).

    ``{"result", "approvals", "outcomes", "save", "timing"}``: the result as `capture_result`
    draws it, the queue items closed, each device's outcome, `save_golden()`'s answer and the
    re-read's timing. Unmasked: the caller masks what it sends."""
    from modules.identity import request_actor
    from modules.nsot.repo import GoldenItem, save_golden
    from modules.nsot.restore import _devices_of
    from modules.preview_confirm import capture_result

    inventory = _devices_of(list_name)
    repo = _repo_for(list_name)
    # One operation per device (C98): a capture recording a device while a
    # deploy or restore changes it would record a half-made state.
    from modules.nsot import device_ops
    # The mode the confirmed preview named, for the in-flight panel's words
    # only; an unknown one is the ordinary capture.
    mode = mode if mode in device_ops.CAPTURE_MODES else "record"
    held, refused_busy = device_ops.acquire_many(
        list_name, [d.get("hostname", "") for d in inventory
                    if d.get("hostname", "") in confirmations], "capture", request_actor(),
        detail=mode)
    busy = {r["device"]: r["reason"] for r in refused_busy}
    try:
        outcomes, items, skipped, texts = [], [], [], {}
        # Every confirmed, held device read AT ONCE (C188), then judged in the
        # inventory's order, as before.
        to_read = [d for d in inventory if d.get("hostname", "") in confirmations
                   and d.get("hostname", "") not in busy]
        read, timing = _read_all(list_name, repo, to_read)
        read_by_host = {e["device"]: (e, t) for e, t in read}
        for device in inventory:
            host = device.get("hostname", "")
            if host not in confirmations:
                skipped.append({"hostname": host, "reason": "not confirmed"})
                continue
            if host in busy:
                outcomes.append({"device": host, "outcome": "busy", "reason": busy[host]})
                skipped.append({"hostname": host, "reason": "another operation holds it"})
                continue
            entry, text = read_by_host[host]
            if not entry["read"]:
                outcomes.append({"device": host, "outcome": "unread", "reason": entry["error"]})
                skipped.append({"hostname": host,
                                "reason": f"could not be read: {entry['error']}"})
                continue
            if entry["capture_hash"] != confirmations[host]:
                outcomes.append({"device": host, "outcome": "moved",
                                 "reason": f"its running config moved since the preview "
                                           f"({confirmations[host]} -> {entry['capture_hash']})",
                                 # Both operands, for a card that names them apart.
                                 "confirmed_hash": confirmations[host],
                                 "current_hash": entry["capture_hash"]})
                skipped.append({"hostname": host, "reason": "moved since the preview"})
                continue
            outcomes.append({"device": host, "outcome": "pending", "diff": entry["diff"],
                             "intent": entry["intent"], "platform": entry["platform"]})
            texts[host] = text
        # The configs to record are the ones just read and matched to the confirmed
        # hash; read once more would be a third read with no one to confirm it.
        pending = [o for o in outcomes if o["outcome"] == "pending"]
        save = {}
        if pending:
            by_host = {d.get("hostname"): d for d in inventory}
            for o in pending:
                d = by_host[o["device"]]
                items.append(GoldenItem(o["device"], texts[o["device"]], d.get("ip", ""),
                                        netbox_id=d.get("_netbox_id"),
                                        device_uid=d.get("device_uid", ""),
                                        platform=o["platform"]))
            # A capture that takes in a change no rule explains, made outside Mercury (C1819):
            # how the device's own log says it changed, kept in the commit for the golden's
            # history and the device page (one Loki ask per such device, at once).
            from modules.nsot import out_of_band
            departing = [by_host[o["device"]] for o in pending
                         if read_by_host[o["device"]][0].get("changed")
                         and out_of_band.unexplained(o["intent"])]
            save = save_golden(list_name, items, source="save_all" if fleet else "capture",
                               extra_trailers=out_of_band.trailers(repo, departing),
                               actor=request_actor(), allow_new=False,
                               inventory_size=len(inventory) if fleet else 0,
                               skipped=skipped, baseline=None if fleet else False,
                               acknowledge_structural_change=acknowledged,
                               # Items handed to this capture close as done below.
                               leave_items=[i for ids in approvals.values()
                                            for i in (ids or [])])
            # Each device's own outcome (C310): a device the save refused is
            # named with ITS reason, never another device's.
            refused = {r["device"]: r for r in (save.get("refused") or [])}
            for o in pending:
                if o["device"] in refused:
                    o.update(outcome="not_recorded", reason=refused[o["device"]]["reason"])
                elif not save.get("ok"):
                    o.update(outcome="unread", reason=save.get("error") or "the save failed")
                else:
                    o["outcome"] = ("captured" if o["device"] in (save.get("changed") or [])
                                    else "unchanged")
                    o["intent"] = (save.get("intent") or {}).get(o["device"], o["intent"])
        result = capture_result(outcomes, save, fleet=fleet, timing=timing)
        closed = _close_handed_off(approvals, outcomes, list_name)
        return {"result": result, "approvals": closed, "outcomes": outcomes, "save": save,
                "timing": timing}
    finally:
        device_ops.release_many(list_name, held)


def restore_plan(list_name: str, ref: str, devices_asked, *, un_onboard=None,
                 authorise: dict = None, req=None, advisory_diff: str = "",
                 approval_id: str = "") -> dict:
    """THE restore preview, unmasked: every device's program, gates and intent half, and the
    six parts. One computation for the v2 device page's restore (board 9) and History's
    Re-apply… (today's /golden/restore/preview, its JSON caller, left at 7.8, 2026-10-17);
    raises `WithdrawnBaseline` for a withdrawn restore point. Each caller masks what it draws,
    AFTER every hash is computed from the truthful program (C77).

    **Additive.** A restore re-applies stored configuration; it does not remove lines a device
    has gained since. Three categories keep that visible rather than implied: ``add`` (in the
    stored config, absent from the device), ``replace`` (in the stored config, the device sets
    it to something else) and ``residue`` (on the device, the stored config does not mention
    it). Only ``residue`` is left behind, so only it is reported as "will not be removed"."""
    from modules.nsot.deploy import (NotAuthorised, assert_authorised,
                                     command_fingerprint, dangerous_in,
                                     merge_diff, prepare_restore,
                                     residue_in_context)
    from modules.nsot import normalize
    from modules.nsot.restore import build_targets
    from routes.deploy import _capture_hash

    # Per device, exactly as the deploy plan (`plan_devices`): an authorisation for one device
    # never covers another. It is folded into the command hash, so the apply
    # (run_targets) recomputes both, and a restore can now carry a dangerous
    # line that a person authorised. It could not before (P.3 step 4).
    authorise = authorise or {}
    targets, skipped = build_targets(list_name, ref, devices_asked, un_onboard=un_onboard,
                                     authorise=authorise)
    devices = []
    for target in targets:
        # A device refused ONLY because it would add a secret (C79) is waiting
        # on an authorisation, like an unauthorised dangerous line, not
        # blocked: its program must be shown, or the line it needs could be
        # neither seen nor authorised (found by test_authorised_lines.py).
        failing = [n for n, st, _d in target.checks if st == "fail"]
        awaits_authorisation = failing == ["no secret re-added"]
        entry = {"device": target.device, "platform": target.platform,
                 "deployable": target.deployable or awaits_authorisation,
                 "blocking_reasons": target.blocking_reasons,
                 "capture_hash": _capture_hash(target.captured),
                 # The restore's own gates, by name: the list its refusal is
                 # computed from, so the preview and the refusal cannot differ.
                 "checks": [{"name": n, "state": st, "detail": dt}
                            for n, st, dt in target.checks],
                 # The intent half of the same unit, stated before it happens.
                 "intent": _intent_preview(list_name, target)}
        entry["secret_readded"] = target.reintroduced_secrets
        try:
            if awaits_authorisation:
                # prepare_restore's own refusal is this check; the mask
                # backstop it would also run still runs.
                from modules.nsot.deploy import assert_no_mask
                assert_no_mask(target.target_config, context="restore")
                prepared = {"config": target.target_config}
            else:
                prepared = prepare_restore(target)
            diff = merge_diff(prepared["config"], target.captured)
            # The deploy's own program (one computation, `_program`): a running
            # IP SLA operation the ref defines differently is re-created, never
            # edited in place (the device refuses that), or refused with why.
            from modules.nsot import recreate as _recreate
            from routes.deploy import _program
            full = _program(prepared["config"], target.captured, [], None, target.platform)
            commands = full["commands"]
            if full["recreate"]["units"]:
                entry["recreates"] = [_recreate.describe(u) for u in full["recreate"]["units"]]
            if full["recreate"]["refused"]:
                entry["deployable"] = False
                entry["blocking_reasons"] = list(entry.get("blocking_reasons") or []) + [
                    r["reason"] for r in full["recreate"]["refused"]]
            entry.update({
                "add": diff["add"],
                "replace": diff["replace"],
                "residue": diff["residue"],
                # Each residue line under its section (C73, which the deploy
                # preview had and this path had too).
                "residue_in_context": residue_in_context(diff["residue"],
                                                         target.captured),
                # Blocks a re-apply cannot send at all — certificate chains,
                # licence UDI, banners. Correct to exclude, and the operator
                # has to know: a drifted banner on s3 is NOT re-applied by
                # this, and "100%" would otherwise imply it was.
                "excluded_unrenderable": normalize.excluded_unrenderable(
                    target.target_config),
                "commands": commands,
                "dangerous": dangerous_in(commands),
                "unchanged_count": diff["unchanged_count"],
            })
            # One mechanism for both classes (C140, C79): a dangerous line
            # and a secret-position line this re-apply would ADD, each
            # authorised with the person's stated reason.
            from modules.nsot import authorisation as _auth
            from routes.deploy import _prior_authorised
            secret = entry["secret_readded"]
            authorised = _auth.normalise(authorise.get(target.device))
            entry["authorised"] = authorised
            entry["command_hash"] = command_fingerprint(commands, authorised)
            entry["prior_authorised"] = _prior_authorised(
                list_name, target.device, _auth.flagged(commands, secret))
            if entry["dangerous"] or secret or authorised:
                try:
                    assert_authorised(commands, authorised, extra=secret)
                    entry["authorisation_ok"] = True
                except NotAuthorised as exc:
                    entry["authorisation_ok"] = False
                    entry["authorisation_error"] = str(exc)
        except Exception as exc:              # noqa: BLE001
            entry.update({"add": [], "replace": [], "residue": [],
                          "commands": [],
                          "excluded_unrenderable": normalize.excluded_unrenderable(
                              target.target_config),
                          "error": str(exc)})
        devices.append(entry)

    from modules.nsot.restore import coverage
    cov = coverage(list_name, devices_asked, skipped)
    residue_total = sum(len(d.get("residue") or []) for d in devices)
    excluded_total = sum(len(d.get("excluded_unrenderable") or [])
                         for d in devices)
    intent_restored = [d["device"] for d in devices
                       if (d.get("intent") or {}).get("action") == "restore"]
    un_onboarding = [d["device"] for d in devices
                     if (d.get("intent") or {}).get("action") == "un_onboard"]
    scope = ("Device configuration AND committed intent from this ref — "
             "one unit per device, one commit. Never templates, bindings "
             "or approvals: those are code, and rolling them back to fix "
             "a network would silently revert template fixes.")
    summary = (
        f"Re-applying stored configuration to {len(devices)} of "
        f"{cov['denominator']} device(s) {cov['scope_words']}."
        + (" This ref is a PARTIAL restore point: it predates "
           + ", ".join(s["hostname"] for s in skipped if s.get("not_at_ref"))
           + ", which will be left exactly as they are."
           if cov["partial"] else "")
        + (f" {residue_total} line(s) present on devices are absent from "
           "this ref and will NOT be removed." if residue_total else "")
        + (f" {excluded_total} block(s) cannot be re-applied at all "
           "(certificates, licence UDI, banners)." if excluded_total else "")
        + (f" Committed intent moves back to this ref for "
           f"{len(intent_restored)} device(s)." if intent_restored else "")
        + (f" UN-ONBOARDING (committed intent removed): "
           f"{', '.join(un_onboarding)}." if un_onboarding else "")
        + (f" Skipped: {', '.join(s['hostname'] for s in skipped)}."
           if skipped else ""))
    # Stage 7.1: the six parts, from the one builder, drawn by the one
    # renderer. The fields below stay: the apply's confirmations are read
    # from them by the same client.
    from modules.nsot.device_ops import busy_text
    for d in devices:
        d["busy"] = busy_text(list_name, d.get("device", ""))    # C99
    from modules.preview_confirm import restore_preview as _parts
    preview = _parts(devices, skipped, ref=ref, summary=summary, scope=scope,
                     request=req if req is not None else request)
    # UNMASKED: every caller masks on the way out, after the hashes (C77).
    return {
        "ok": True, "ref": ref, "list": list_name, "mode": "re-apply",
        "devices": devices, "skipped": skipped, "preview": preview,
        "intent_restored": intent_restored, "un_onboarding": un_onboarding,
        # Echoed back so the confirm dialog can show "what the agent saw"
        # beside the freshly computed program. Never an input to anything.
        "advisory_diff": advisory_diff,
        "approval_id": approval_id,
        "scope": scope,
        # C23: the denominator is the INVENTORY for a whole restore and the
        # selection for a scoped one, never "whatever the ref happened to
        # hold". A device the ref predates is named in `skipped`.
        "inventory_size": cov["inventory_size"],
        "partial": cov["partial"],
        "summary": summary,
    }


def _intent_preview(list_name: str, target) -> dict:
    """What the intent half of this device's restore will do. Reads only.

    Device and intent move as one unit, so the preview has to show both. The
    three outcomes are ``unchanged`` (the ref's intent is what is committed
    today), ``restore`` (it differs and will be re-committed forward), and
    ``un_onboard`` (the ref predates the device and the operator ticked it).
    """
    import os as _os

    from modules.config import get_list_data_dir
    from modules.nsot import hostvars

    repo = _os.path.join(get_list_data_dir(list_name), "config_repo")
    text = getattr(target, "ref_intent_text", "") or ""

    if getattr(target, "un_onboard", False):
        return {"action": "un_onboard",
                "detail": ("Committed intent for this device will be REMOVED "
                           "by a forward commit — recoverable from git "
                           "history, but it un-does the onboarding review.")}
    if not text:
        return {"action": "none", "detail": "no committed intent at this ref"}

    # Committed intent is what is at HEAD (C104), not the working file.
    current = hostvars.committed_at_head(repo, target.device)[0] or ""
    if current == text:
        return {"action": "unchanged",
                "detail": "committed intent already matches this ref"}
    return {"action": "restore",
            "detail": ("Committed intent will be set back to this ref's "
                       "version by a forward commit." if current else
                       "This device has no committed intent today; the ref's "
                       "will be committed."),
            "had_intent": bool(current)}


# Today's re-apply (POST /golden/restore/apply) left at 7.8 (2026-10-17, P7-21): a restore is
# confirmed on v2 and run as a job, `deploy_job.start_restore`, over the same `restore.
# build_targets` and `routes.deploy.run_targets` (the device page's Restore from… and History's
# Re-apply…). The approval queue's hand-off it closed left with the AI family (D15).
