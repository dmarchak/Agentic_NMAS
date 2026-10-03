"""Golden config repository blueprint: timeline, diffs, baselines, migration."""

import logging
import os

from flask import Blueprint, jsonify, request

from modules.identity import request_actor

log = logging.getLogger(__name__)

bp = Blueprint("golden", __name__, url_prefix="/golden")


def _repo_for(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _active_list(payload=None) -> str:
    from modules.config import get_current_list_name
    name = (payload or {}).get("list_name") or request.args.get("list_name") or ""
    return name.strip() or get_current_list_name()


def _serve_config(text: str, *, what: str, target: str, detail: str = ""):
    """``(payload, status)`` for config text, masked unless revealed. The
    pattern lives in `modules/outbound.py` since register C56, so the backup
    download and these routes are one pattern rather than two."""
    from modules import outbound

    return outbound.config_text(request, text, what=what, target=target, detail=detail)


@bp.route("/history/<path:hostname>", methods=["GET"])
def history(hostname):
    """Promotion timeline for one device, following renames."""
    from modules.nsot.repo import get_ci_note, golden_history

    list_name = _active_list()
    repo = _repo_for(list_name)
    try:
        entries = golden_history(repo, hostname)
        for entry in entries:
            entry["ci"] = get_ci_note(repo, entry["sha"])
        return jsonify({"ok": True, "hostname": hostname, "list": list_name,
                        "history": entries})
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: history failed for %s", hostname)
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/version/<path:hostname>", methods=["GET"])
def version(hostname):
    """One device's golden config at a given ref."""
    from modules.nsot.repo import golden_at

    ref = request.args.get("ref", "HEAD")
    content = golden_at(_repo_for(_active_list()), hostname, ref)
    if content is None:
        return jsonify({"ok": False,
                        "error": f"No golden config for {hostname} at {ref}"}), 404

    payload, status = _serve_config(content, what="golden_config",
                                    target=hostname, detail=ref)
    payload["config"] = payload.pop("text")
    return jsonify({**payload, "hostname": hostname, "ref": ref}), status


@bp.route("/diff/<path:hostname>", methods=["GET"])
def diff(hostname):
    """Unified diff of one device's golden config between two refs."""
    import difflib

    from modules.nsot.repo import golden_at

    repo = _repo_for(_active_list())
    ref_a = request.args.get("a", "")
    ref_b = request.args.get("b", "HEAD")
    if not ref_a:
        return jsonify({"ok": False, "error": "Parameter 'a' is required"}), 400

    left, right = golden_at(repo, hostname, ref_a), golden_at(repo, hostname, ref_b)
    if left is None or right is None:
        return jsonify({"ok": False,
                        "error": "One of the versions has no golden config"}), 404

    lines = list(difflib.unified_diff(
        left.splitlines(), right.splitlines(),
        fromfile=f"{hostname}@{ref_a}", tofile=f"{hostname}@{ref_b}", lineterm=""))

    # A diff of two configs carries the same secrets as either of them, on the
    # `-` and `+` lines. Easy to leave masked-by-default behind when adding a
    # view, which is why both go through one helper.
    payload, status = _serve_config("\n".join(lines), what="golden_diff",
                                    target=hostname,
                                    detail=f"{ref_a}..{ref_b}")
    payload["diff"] = payload.pop("text")
    return jsonify({**payload, "hostname": hostname, "a": ref_a, "b": ref_b,
                    "changed": bool(lines)}), status


@bp.route("/baselines", methods=["GET"])
def baselines():
    """Network-wide restore points."""
    from modules.nsot.repo import devices_at, list_baselines

    repo = _repo_for(_active_list())
    try:
        from modules.nsot.restore import baseline_credential_gaps

        list_name = _active_list()
        entries = list_baselines(repo)
        # The population, read ONCE for all baselines.
        from modules.device import load_saved_devices
        from modules.config import get_list_data_dir
        inventory = {d.get("hostname", "") for d in load_saved_devices(
            os.path.join(get_list_data_dir(list_name), "devices.csv"))}

        for entry in entries:
            if entry.get("deleted"):
                continue        # no tag to read: drawn from its record
            if entry.get("withdrawn"):
                # Both halves, local and the remote the tags are pushed to,
                # chained so the second runs only if the first did. The
                # person runs them: a write to the record and to the remote.
                entry["delete_commands"] = [
                    f"git -C {repo} tag -d {entry['tag']} && "
                    f"git -C {repo} push origin --delete refs/tags/{entry['tag']}"]
            devices = devices_at(repo, entry["tag"])
            entry["device_count"] = len(devices)
            # The scope chooser (C80) lists these, none ticked.
            entry["devices"] = sorted(devices)
            # PARTIAL RELATIVE TO TODAY'S FLEET, named rather than left to
            # arithmetic. The count alone made an older baseline read "9"
            # and a newer one "10" with nothing saying the first covers less
            # than the network does now -- visible as a number, and a number
            # is not a statement. A device onboarded after the tag has no
            # golden at it, so re-applying leaves that device untouched:
            # correct, and not what "restore the network" sounds like.
            entry["inventory_size"] = len(inventory)
            entry["missing_devices"] = sorted(inventory - set(devices))
            entry["partial"] = bool(entry["missing_devices"])
            # Which devices' credentials this ref predates, computed here so
            # it can be shown BESIDE the re-apply button rather than after
            # the operator has committed to the operation.
            gaps = baseline_credential_gaps(repo, entry["tag"], list_name,
                                            devices)
            entry["credential_stale"] = sorted(gaps["stale"])
            entry["credential_detail"] = gaps["stale"]
            # Stale AND refused by neither guard. Since C75 nothing that
            # rewrites a held credential passes, so these would only ADD an
            # account the baseline has and the device lacks.
            entry["credential_silent"] = gaps["silent"]
            entry["credential_refused"] = gaps["refused"]
            # The restore's own credential guard refuses these (C75).
            entry["credential_guarded"] = gaps["guarded"]
            entry["no_intent"] = gaps["no_golden"]
        return jsonify({"ok": True, "baselines": entries,
                        "last_decision": _last_baseline_decision(repo)})
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


def _last_baseline_decision(repo: str) -> dict:
    """The newest `Baseline:` decision the history records (a changing save's
    commit, or, since 2026-09-28, an empty decision commit when nothing
    changed): what the panel's remedy must name, so it never recommends an
    action the last attempt showed would be refused. ``{}`` when none."""
    from modules.nsot.repo import git

    rc, out, _err = git(repo, "log", "-1", "-E", "--grep=^Baseline: ",
                        "--format=%H%x1f%cI%x1f%B")
    if rc != 0 or not (out or "").strip():
        return {}
    sha, at, body = out.split("\x1f", 2)
    line = next((l[len("Baseline: "):].strip() for l in body.splitlines()
                 if l.startswith("Baseline: ")), "")
    return {"commit": sha[:12], "at": at.strip(),
            "state": "earned" if line == "earned" else "denied",
            "reasons": line.split(":", 1)[1].strip() if line.startswith("denied:") else ""}


@bp.route("/restore_points/<path:hostname>", methods=["GET"])
def restore_points(hostname):
    """Where one device can be restored from (C80, 7.1 step 5): the Device
    page's "Restore from…" chooser. Reads only.

    Each point carries this device's credential state at that ref, measured
    the way the Baselines panel measures it, so the chooser warns BEFORE the
    click: ``current``, ``refused`` (the restore's own guards stop it),
    ``silent`` (an account the ref has and the device lacks would be ADDED
    back) or ``no_golden``. The username lines themselves never leave."""

    list_name = _active_list()
    try:
        points = restore_points_for(list_name, hostname)
        for point in points:
            # Drawn by the v2 chooser only: today's pages gain no capability (they shrink
            # until cutover), so it is not carried to a page that would not draw it.
            point.pop("same_as_now", None)
        return jsonify({"ok": True, "hostname": hostname, "list": list_name,
                        "points": points})
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: restore points failed for %s", hostname)
        return jsonify({"ok": False, "error": str(exc)}), 500


def restore_points_for(list_name: str, hostname: str, checked: int = None) -> list:
    """Where *hostname* can be restored from, newest first, each with its credential state at
    that moment (``current``, ``refused``, ``silent``: an account added back, ``no_golden``).
    ONE reading for today's chooser and the v2 device page's (board 9). Reads only.

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


def _close_handed_off(approvals: dict, outcomes: list) -> dict:
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
                                          f"{request_actor()}", actor=request_actor())
                (closed if out.get("ok") else left).append(entry_id)
            else:
                left.append(entry_id)
    return {"closed": closed, "left_pending": left}


@bp.route("/capture/preview", methods=["POST"])
def capture_preview():
    """Record running configs as goldens: the PREVIEW (7.1 step 4, C82, C89).

    Reads each device NOW and shows what its golden would become and how that
    compares with its committed intent. No `devices` is the whole fleet (what
    Save All now opens). Masked on the way out; writes nothing."""
    from modules.nsot.restore import _devices_of

    data = request.get_json(silent=True) or {}
    list_name = _active_list(data)
    inventory = _devices_of(list_name)
    wanted = [d for d in (data.get("devices") or []) if d]
    names = {d.get("hostname") for d in inventory}
    unknown = sorted(set(wanted) - names)
    if unknown:
        return jsonify({"ok": False, "error": f"not in {list_name}: {', '.join(unknown)}"}), 404
    repo = _repo_for(list_name)
    scope = data.get("scope") or ""
    if scope and scope != "no_golden":
        return jsonify({"ok": False, "error": f"unknown capture scope {scope!r}"}), 400
    excluded = []
    if scope == "no_golden":
        # What Auto-Create was, as a scope of the ONE capture operation
        # (minimalism, NSOT_STAGE7_PLAN section 6a): every device with no
        # COMMITTED golden, or a refused one (a refusal's own remedy is to
        # capture the device). Decided from git, never from files on disk.
        from modules.nsot import manifest as _m
        from modules.nsot.repo import committed_golden_for
        devices = []
        for d in inventory:
            record = committed_golden_for(repo, _m.find_by_name(repo, d.get("hostname", ""))[1])
            if record["text"] is None:
                devices.append(d)
            else:
                excluded.append(d.get("hostname", ""))
        if not devices:
            return jsonify({"ok": True, "list": list_name, "fleet": False, "preview": None,
                            "nothing": (f"Every device in {list_name} has a committed golden "
                                        f"({len(excluded)} device(s)): nothing to capture, "
                                        f"and nothing was read.")})
        fleet = False
    else:
        fleet = not wanted
        devices = [d for d in inventory if fleet or d.get("hostname") in set(wanted)]
    names = [d.get("hostname", "") for d in devices]
    job = start_capture_preview(list_name, inventory, devices, fleet=fleet, excluded=excluded)
    # `nothing` is always carried (empty here): one payload shape with the
    # nothing-to-capture answer above, so the client reads a key that is there.
    return jsonify({"ok": True, "list": list_name, "job": job, "devices": names,
                    "nothing": ""}), 202


def start_capture_preview(list_name: str, inventory: list, devices: list, *, fleet: bool,
                          excluded: list = None) -> str:
    """Start the capture preview's reads as a job and return its id: THE start, for
    `/golden/capture/preview` and the v2 device page's Capture (7.3) alike.

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
                         not_read=excluded or [], timing=timing)
        # The preview alone: it draws each device's read, and its
        # `select_data` carries the hash the confirm is bound to. The raw
        # reads are not sent. `nothing` is always carried (empty here): one
        # payload shape whether or not a scope found anything.
        return mask_payload({"list": list_name, "fleet": fleet, "preview": preview,
                             "nothing": ""})

    return capture_job.start(list_name, f"{list_name}: {len(devices)} device(s)", actor, work)


@bp.route("/capture/preview/<job>", methods=["GET"])
def capture_preview_result(job):
    """The capture preview a POST started (C188 step 2), by its id: running
    (with what it is doing), done (the preview), or failed (why). A READ; it
    writes nothing. An id this server has no record of is 404 and says why,
    never an empty preview: a restart loses a job, and a person starts it
    again."""
    from modules import op_progress
    from modules.nsot import capture_job

    got = capture_job.get(job)
    if got is None:
        return jsonify({"ok": False, "job": job, "state": "unknown",
                        "error": ("This server has no capture preview " + job[:12]
                                  + ": it finished more than "
                                  + str(capture_job.KEEP_S // 60) + " minutes ago, or the "
                                  "server restarted. Nothing was recorded; start the "
                                  "preview again.")}), 404
    op = op_progress.get(job) or {}
    out = {"ok": got["state"] != "failed", "job": job, "state": got["state"],
           "list": got["list"], "elapsed_s": got["elapsed_s"],
           "step_words": op.get("step_words", ""), "error": got["error"], "fleet": None, "preview": None, "nothing": ""}
    if got["state"] == "done":
        out.update(got["payload"] or {})
    return jsonify(out)


@bp.route("/capture/apply", methods=["POST"])
def capture_apply():
    """Record the confirmed captures: each device is READ AGAIN, and one whose
    running config moved since the preview is refused. One commit, as the
    verified person, through `save_golden()`, which writes the computed
    `Intent-Match:` trailer and takes a baseline only for a whole-fleet
    capture with every device at its committed intent (C89 (c))."""
    from modules.outbound import mask_payload

    data = request.get_json(silent=True) or {}
    confirmations = {k: v for k, v in (data.get("confirmations") or {}).items() if k}
    # A person's reason per device for a shrink intent does not explain
    # (C310), in the shape of a reason, recorded on the commit as theirs.
    from modules.nsot.authorisation import reason_problem
    acknowledged = {}
    for host, reason in (data.get("acknowledge") or {}).items():
        problem = reason_problem({"reason": str(reason or "").strip(),
                                  "line": f"{host}'s structural change"})
        if problem:
            return jsonify({"ok": False, "error": f"{host}: {problem}"}), 400
        acknowledged[host] = str(reason).strip()
    if not confirmations:
        return jsonify({"ok": False, "error": "Nothing confirmed: nothing recorded"}), 400
    list_name = _active_list(data)
    fleet = bool(data.get("fleet"))
    got = apply_captures(list_name, confirmations, fleet=fleet, acknowledged=acknowledged,
                         approvals=data.get("approvals") or {}, mode=data.get("mode") or "")
    return jsonify(mask_payload({"ok": True, "list": list_name, "fleet": fleet,
                                 "result": got["result"], "approvals": got["approvals"]}))


def apply_captures(list_name: str, confirmations: dict, *, fleet: bool, acknowledged: dict,
                   approvals: dict, mode: str = "") -> dict:
    """Record the confirmed captures: THE apply, for `/golden/capture/apply` and the v2
    device page's Capture (7.3) alike. ``{"result", "approvals", "outcomes", "save",
    "timing"}``: the result as `capture_result` draws it, the queue items closed, each
    device's outcome, `save_golden()`'s answer and the re-read's timing. Unmasked: the
    caller masks what it sends."""
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
            save = save_golden(list_name, items, source="save_all" if fleet else "capture",
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
        closed = _close_handed_off(approvals, outcomes)
        return {"result": result, "approvals": closed, "outcomes": outcomes, "save": save,
                "timing": timing}
    finally:
        device_ops.release_many(list_name, held)


@bp.route("/restore/preview", methods=["POST"])
def restore_preview():
    """What re-applying a ref would do, per device, before anything is sent.

    **Additive.** This re-applies stored configuration; it does not remove
    lines a device has gained since. The three categories exist so that
    distinction is visible rather than implied:

    * ``add``     — in the stored config, absent from the device
    * ``replace`` — in the stored config, the device sets it to something else
    * ``residue`` — on the device, the stored config does not mention it

    Only ``residue`` is left behind, so only ``residue`` is reported as "will
    not be removed". The previous report listed every device line absent from
    the target, which included lines about to be overwritten.
    """
    from modules.nsot.restore import WithdrawnBaseline
    from modules.outbound import mask_payload

    data = request.get_json(silent=True) or {}
    ref = (data.get("ref") or "").strip()
    if not ref:
        return jsonify({"ok": False, "error": "ref is required"}), 400
    try:
        plan = restore_plan(_active_list(data), ref, data.get("devices"),
                            un_onboard=data.get("un_onboard"),
                            authorise=data.get("authorise") or {}, req=request,
                            advisory_diff=data.get("advisory_diff") or "",
                            approval_id=data.get("approval_id") or "")
    except WithdrawnBaseline as exc:
        return jsonify({"ok": False, "withdrawn": exc.record, "error": str(exc)}), 409
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: restore preview failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
    # Masked on the way out, AFTER every hash is computed from the truthful
    # program (C77): stored config lines (the program, residue, what a line
    # replaces) came back verbatim.
    return jsonify(mask_payload(plan))


def restore_plan(list_name: str, ref: str, devices_asked, *, un_onboard=None,
                 authorise: dict = None, req=None, advisory_diff: str = "",
                 approval_id: str = "") -> dict:
    """THE restore preview, unmasked: every device's program, gates and intent half, and the
    six parts. One computation for `/golden/restore/preview` and the v2 device page's restore
    (board 9); raises `WithdrawnBaseline` for a withdrawn restore point."""
    from modules.nsot.deploy import (NotAuthorised, assert_authorised,
                                     command_fingerprint, dangerous_in,
                                     merge_diff, prepare_restore,
                                     residue_in_context)
    from modules.nsot import normalize
    from modules.nsot.restore import build_targets
    from routes.deploy import _capture_hash

    # Per device, exactly as /deploy/plan: an authorisation for one device
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


@bp.route("/restore/apply", methods=["POST"])
def restore_apply():
    """Re-apply a ref through the confirmed deploy path.

    Not the approval queue, whose old executor pushed whole-config text with
    none of the guarantees built since. That executor is gone: approving a
    queued revert now hands off to THIS route (`_exec_revert_golden`), so a
    queued item is a request for this operation, never a payload. Until C326
    (2026-10-02) this route still rejected every pending revert on each use,
    the one being acted on included, so an approved revert ended "rejected"
    with no person and no reason, and any restore rejected other devices'.
    """
    from modules.identity import request_actor
    from modules.nsot.restore import WithdrawnBaseline, build_targets
    from routes.deploy import run_targets

    data = request.get_json(silent=True) or {}
    ref = (data.get("ref") or "").strip()
    if not ref:
        return jsonify({"ok": False, "error": "ref is required"}), 400
    confirmations = data.get("confirmations") or {}
    if not confirmations:
        return jsonify({"ok": False,
                        "error": "Nothing confirmed — re-apply refused"}), 400

    list_name = _active_list(data)
    try:
        targets, skipped = build_targets(list_name, ref, list(confirmations),
                                         un_onboard=data.get("un_onboard"),
                                         authorise=data.get("authorise") or {})
    except WithdrawnBaseline as exc:
        return jsonify({"ok": False, "withdrawn": exc.record, "error": str(exc)}), 409
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: restore apply failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

    report = run_targets(list_name, targets, data,
                         label=f"re-apply {ref}", source_ref=ref, skipped=skipped)
    report.update({"ref": ref, "mode": "re-apply", "skipped": skipped})

    # Close the queue item that handed off to this, but ONLY for devices that
    # actually succeeded. An item left pending for ever teaches the operator to
    # clear the queue by rejecting things, which is the habit that makes an
    # approval queue worthless; an item closed on a failed push would be the
    # queue claiming work that did not happen.
    approval_id = (data.get("approval_id") or "").strip()
    if approval_id:
        from modules.approval_queue import mark_done
        from modules.nsot.deploy import DEPLOYED

        succeeded = [r.get("device") for r in (report.get("results") or [])
                     if r.get("outcome") == DEPLOYED]
        if succeeded:
            closed = mark_done(approval_id,
                               f"Re-applied {ref} to {', '.join(succeeded)} "
                               "through the confirmed deploy path", actor=request_actor())
            report["approval_closed"] = closed.get("ok", False)
        else:
            report["approval_closed"] = False
            report["approval_note"] = (
                "left pending: no device completed successfully")

    # Masked on the way out (C77's apply side, measured 2026-09-27: a planted
    # community came back in `results[].commands`). The receipts and the
    # golden commit are written above from the truthful report; nothing
    # reads this response back into a confirm.
    from modules.outbound import mask_payload
    return jsonify(mask_payload({"ok": True, "list": list_name, **report}))


@bp.route("/migrate/plan", methods=["GET", "POST"])
def migrate_plan():
    """Dry-run migration report. Writes nothing — this is the UI default."""
    from modules.nsot.migrate import plan

    data = request.get_json(silent=True) or {}
    try:
        return jsonify(plan(_active_list(data)))
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: migration plan failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/migrate/apply", methods=["POST"])
def migrate_apply():
    """Perform the migration. Requires an explicit confirm."""
    from modules.nsot.migrate import apply as apply_migration

    data = request.get_json(silent=True) or {}
    if not data.get("confirm"):
        return jsonify({"ok": False,
                        "error": "Review the dry-run report and confirm first."}), 400
    try:
        result = apply_migration(_active_list(data),
                                 actor=request_actor())
        # A refused re-run is a conflict, not a server error and not a success.
        # The body carries the marker, so the UI can say when it happened.
        return jsonify(result), (409 if result.get("already_migrated") else 200)
    except Exception as exc:                  # noqa: BLE001
        log.exception("golden: migration failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@bp.route("/renames", methods=["GET"])
def renames():
    """Renames noticed by an inventory refresh but not yet committed."""
    from modules.inventory import pending_renames
    return jsonify({"ok": True, "pending": pending_renames(_active_list())})


@bp.route("/renames/sync", methods=["POST"])
def sync_renames():
    """Apply pending renames as their own commits."""
    from modules.inventory import sync_device_names_to_repo

    data = request.get_json(silent=True) or {}
    try:
        return jsonify(sync_device_names_to_repo(_active_list(data),
                                                 actor=request_actor()))
    except Exception as exc:                  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


def _legacy_action(list_name: str, legacy_dir: str, entry: dict) -> dict:
    """What to DO about one legacy-only file (the operator, 2026-09-28: the
    notice stated a state and a condition for clearing it, and no action).
    Decided from the record, never guessed: a device RETIRED has a commit
    carrying `Retired-Device: <name>` (nmas-retire writes it), and its file is
    residue the retirement did not remove (C176); one still in the inventory
    gets its first repository golden by a capture; anything else is neither,
    and its file may be the only copy of a config, so nothing says delete."""
    from modules.nsot.restore import _devices_of

    host = entry["hostname"]
    path = os.path.join(legacy_dir, entry["file"])
    rc, out, _ = _git_repo(list_name, "log", "-1", "--format=%h %as",
                           "--grep", f"^Retired-Device: {host}$")
    retired = out.strip().split() if rc == 0 and out.strip() else []
    if retired:
        survives = _legacy_survives(list_name, host, path)
        head = (f"{host} was retired ({retired[0]}, "
                f"{retired[1] if len(retired) > 1 else ''}), and nothing reads this file "
                f"for it any more. {survives['words']}")
        if survives["state"] == "lost":
            return {"state": "retired",
                    "action": head + (" Keep a copy of it before deleting it; nothing else "
                                      "holds those lines.")}
        return {"state": "retired", "action": head + f" Delete it on the host: rm {path}"}
    if host in {d.get("hostname", "") for d in _devices_of(list_name)}:
        return {"state": "managed",
                "action": (f"{host} is in the inventory with no repository golden. "
                           "Capture it (Capture as golden on its Device page): its "
                           "first repository golden replaces this file's role.")}
    return {"state": "unknown",
            "action": (f"{host} is neither in the inventory nor retired on record, so "
                       "this file may be the only copy of its config. Find out what it "
                       "was before deleting it; nothing here says it is safe to.")}


def _legacy_survives(list_name: str, host: str, path: str) -> dict:
    """Whether a legacy file's content SURVIVES in the repository, where, and
    what deleting it would lose (the operator's rule, 2026-09-28: an action
    that removes data says all three). Compared with every committed version of
    `golden/<host>.cfg`, newest first: the same configuration (section-aware,
    comments and headers aside) at a commit is survival at that commit; none
    means the lines are nowhere else."""
    from modules.nsot.roundtrip import configs_equivalent

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return {"state": "unknown", "words": f"Its content could not be read ({exc})."}
    # The migration committed each legacy file VERBATIM as a backup (measured
    # on the host: 32dbab7 holds .nsot/migration-backup/golden_configs-r5.cfg,
    # 332 lines), and the store is read-only since: the most exact survival.
    backup = f".nsot/migration-backup/golden_configs-{os.path.basename(path)}"
    rc0, shas0, _ = _git_repo(list_name, "log", "--format=%h", "--diff-filter=AMR",
                              "--", backup)
    for sha in ((shas0 or "").split() if rc0 == 0 else []):
        rc1, body, _ = _git_raw_repo(list_name, "show", f"{sha}:{backup}")
        if rc1 == 0 and body == text:
            return {"state": "survives", "commit": sha,
                    "words": (f"This file survives VERBATIM in the repository as {backup} "
                              f"at {sha} (the migration's backup; git show {sha}:{backup}), "
                              "so deleting it loses nothing but the copy.")}
    rel = f"golden/{host}.cfg"
    # Commits where the file EXISTS: the retire commit deletes it and is not
    # a version of it.
    rc, shas, _ = _git_repo(list_name, "log", "--format=%h", "--diff-filter=AMR",
                            "--", rel)
    versions = [s for s in (shas or "").split() if s] if rc == 0 else []
    for sha in versions:
        rc2, body, _ = _git_repo(list_name, "show", f"{sha}:{rel}")
        if rc2 == 0 and body and configs_equivalent(text, body)["equal"]:
            return {"state": "survives", "commit": sha,
                    "words": (f"Its configuration survives in the repository as {rel} at "
                              f"{sha} (git show {sha}:{rel}), so deleting it loses nothing "
                              "but the copy.")}
    if not versions:
        return {"state": "lost", "words": (f"The repository never held {rel}, so this file "
                                           "is the only copy of its configuration.")}
    return {"state": "lost", "words": (
        f"It differs from all {len(versions)} committed version(s) of {rel} (newest "
        f"{versions[0]}), so deleting it loses the lines only it holds.")}


def _git_raw_repo(list_name: str, *args):
    from modules.nsot.repo import git_raw
    return git_raw(_repo_for(list_name), *args)


def _git_repo(list_name: str, *args):
    from modules.nsot.repo import git
    return git(_repo_for(list_name), *args)


@bp.route("/legacy_store", methods=["GET"])
def legacy_store():
    """What still depends on the deprecated ``golden_configs/`` directory.

    **The retirement condition, made measurable.** "Deprecated" with no exit
    criterion never ends: the directory has been read-only since the
    migration, and until Stage 3.3 it was also the thing every reader
    enumerated. It is now consulted for exactly two purposes -- the last link
    of `_find_golden_config_file`'s resolution chain, for a device whose
    management IP changed outside NMAS, and the legacy-only entries in
    `repo.list_goldens()`.

    When ``only_legacy`` is empty for every list, both can go and so can the
    directory. That number is reported here rather than left to be
    rediscovered by whoever next wonders whether it is safe to delete.
    """
    from modules.config import get_list_data_dir
    from modules.nsot.repo import legacy_only_goldens, list_goldens

    list_name = _active_list()
    try:
        goldens = list_goldens(list_name)
        known = {e["hostname"] for e in goldens if not e["legacy"]}
        only_legacy = legacy_only_goldens(get_list_data_dir(list_name), known)
        legacy_dir = os.path.join(get_list_data_dir(list_name), "golden_configs")
        files = ([f for f in sorted(os.listdir(legacy_dir)) if f.endswith(".cfg")]
                 if os.path.isdir(legacy_dir) else [])
        return jsonify({
            "ok": True,
            "list": list_name,
            "in_repo": len(known),
            "legacy_files": len(files),
            "only_legacy": [{"hostname": e["hostname"],
                             "device_ip": e["device_ip"],
                             "file": e["file"],
                             **_legacy_action(list_name, legacy_dir, e)}
                            for e in only_legacy],
            "retirable": not only_legacy,
        })
    except Exception as exc:                   # noqa: BLE001
        log.exception("golden: legacy store report failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
