"""Are the scheduled jobs NMAS depends on actually succeeding?

Measured 2026-09-25: ``clab-sync.service`` failed every 30 minutes for ~36
hours (72 runs) with ``nmas-clab-targets: command not found``. The script
refused correctly, into a journal nobody read, and r6's startup config fell a
day behind its branch-site config. The evidence was durable and nothing
surfaced it -- the third such place in one session.

So each job NMAS depends on is DECLARED here with the age its last success
may reach, and this reads systemd and the journal and says, per job:

* ``ok`` -- the last run succeeded and the last success is recent enough;
* ``failing`` -- the last run failed; with how many in a row, since when,
  and the job's own last error line (its reason, not systemd's summary);
* ``stale`` -- nothing has failed, and nothing has succeeded recently either:
  a timer stopped, disabled, or never firing;
* ``never_succeeded`` -- failures in the journal window and no success;
* ``not_installed`` -- **never ok**: measured, systemd reports
  ``Result=success`` for a unit that does not exist, so a check reading
  ``Result`` alone calls a job that was never installed healthy.

A job NMAS depends on and cannot see is the failure this exists to catch, so
a systemctl or journal that cannot be asked is ``unknown``, never ``ok``.
"""

import logging
import os
import re
import subprocess
import time

log = logging.getLogger(__name__)

#: The jobs, what they are for, and how old their last success may get
#: (a few missed runs, never one). A job added to the host without a line
#: here is invisible -- adding it is part of installing it.
JOBS = (
    {"unit": "clab-sync", "max_age_minutes": 90,
     "what": "Oxidized configs into containerlab startup files, every 30 min"},
    {"unit": "nmas-netbox-backup", "max_age_minutes": 180,
     "what": "NetBox dump + config, hourly (NSOT_PLAN P.2)"},
    {"unit": "nmas-netbox-restore-test", "max_age_minutes": 50 * 60,
     "what": "NetBox restore into a scratch postgres, daily (P.2)"},
    {"unit": "nmas-heartbeat-check", "max_age_minutes": 180,
     "what": "each device's heartbeat window still fits its measured rate, hourly (C16)"},
)

JOURNAL_DAYS = 14

import re as _re

_NAMES_A_FAILURE = _re.compile(
    r"not found|REFUSED|FAILED|ERROR|Error|Traceback|denied|No such", _re.I)


def _run(cmd: list) -> tuple:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)


def _show(unit: str, run) -> dict:
    rc, out = run(["systemctl", "show", unit, "-p", "LoadState",
                   "-p", "ActiveState", "-p", "Result", "-p", "ExecMainStatus"])
    if rc != 0:
        return {}
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def _journal(unit: str, run) -> tuple:
    """``(ok, [(unix_ts, text)])``."""
    rc, out = run(["journalctl", "-u", unit, "-o", "short-unix", "--no-pager",
                   "--since", f"-{JOURNAL_DAYS}d"])
    if rc != 0:
        return False, []
    rows = []
    for line in out.splitlines():
        head, _, rest = line.partition(" ")
        try:
            rows.append((float(head), rest))
        except ValueError:
            continue
    return True, rows


def job_status(job: dict, now: float = None, run=None) -> dict:
    # Resolved at CALL time: a default of `run=_run` is bound when the
    # function is defined, so a replaced `_run` never reaches it -- which let
    # this module's own route test pass by asking the laptop's real systemd.
    run = run or _run
    now = now or time.time()
    unit = job["unit"] + ".service"
    out = {"unit": job["unit"], "what": job["what"],
           "max_age_minutes": job["max_age_minutes"]}
    show = _show(unit, run)
    if not show:
        return {**out, "state": "unknown",
                "detail": "systemctl could not be asked -- not the same as ok"}
    if show.get("LoadState") == "not-found":
        return {**out, "state": "not_installed",
                "detail": f"{unit} is not installed (systemd reports "
                          f"Result={show.get('Result', '?')} for it anyway)"}
    ok, rows = _journal(unit, run)
    if not ok:
        return {**out, "state": "unknown",
                "detail": "the journal could not be read -- not the same as ok"}

    # THE CAUSE, not the last line. A refusal is several lines and its last is
    # a continuation ("...into another lab."), measured live. So each run's
    # own output is collected, and the error is its first line that names a
    # failure -- here `nmas-clab-targets: command not found` -- falling back
    # to the run's first line.
    last_ok, last_fail, streak, last_error = None, None, 0, ""
    run_lines: list = []
    for ts, text in rows:
        if "systemd[" in text:
            if "Starting " in text or "Started " in text:
                run_lines = []
        elif text.strip():
            run_lines.append(text.split(": ", 1)[-1].strip())
        if "Deactivated successfully" in text:
            last_ok, streak = ts, 0
        elif "Failed with result" in text:
            last_fail, streak = ts, streak + 1
            named = [l for l in run_lines if _NAMES_A_FAILURE.search(l)]
            last_error = (named or run_lines or [""])[0]
            run_lines = []

    def ago(ts):
        return f"{int((now - ts) // 60)} min ago" if ts else "never"

    max_age = job["max_age_minutes"] * 60
    failed_last = last_fail is not None and (last_ok is None or last_fail > last_ok)
    if failed_last and last_ok is None:
        state = "never_succeeded"
    elif failed_last:
        state = "failing"
    elif last_ok is None or now - last_ok > max_age:
        state = "stale"
    else:
        state = "ok"
    detail = (f"last success {ago(last_ok)}"
              + (f"; {streak} consecutive failure(s), last {ago(last_fail)}"
                 if failed_last else "")
              + (f"; last error: {last_error}" if failed_last and last_error else ""))
    return {**out, "state": state, "detail": detail,
            "last_success": last_ok, "last_failure": last_fail,
            "consecutive_failures": streak if failed_last else 0,
            "last_error": last_error if failed_last else "",
            "active_state": show.get("ActiveState", "")}


# ---------------------------------------------------------------------------
# The nightly VM images on the Proxmox host (register B6, docs/VM_IMAGES.md)
# ---------------------------------------------------------------------------
#
# PULLED from the Proxmox API, not pushed by its notifications: a
# notification reports a job that ran and failed, and cannot report one that
# STOPPED -- disabled, deleted, a broken schedule, the host down at 02:30.
# That silence is C14's shape, so each VM is judged, like every job above, by
# the age of its newest image.

#: A nightly job, so a day plus two hours before an image is stale.
IMAGE_MAX_AGE_MINUTES = 26 * 60
#: Free space must hold the largest image this much over: vzdump writes the
#: new image BEFORE pruning the oldest, so tonight's needs room beside every
#: kept one. A question about the next run, never a percentage -- 85% full
#: with 40 G free is fine for 12 G images and 60% is not for 60 G ones.
FIT_FACTOR = 1.2
#: An LVM-thin pool this full, in data OR metadata, is reported. A full pool
#: fails writes for every volume in it; full metadata is the worse of the two.
POOL_WARN_FRACTION = 0.80

_IMAGES_WHAT = "nightly VM image (vzdump) on the Proxmox host (B6)"
#: How many finished vzdump tasks' logs to read, newest first, before a VM
#: that no task mentions is reported `never`.
IMAGE_TASK_LOGS = 20
#: The storage must hold at least this share of the newest images' total, or
#: an image was removed after it was written.
PRESENT_FRACTION = 0.95

_GIB = 1024 ** 3
_UNITS = {"B": 1, "KB": 1024, "KIB": 1024, "MB": 1024 ** 2, "MIB": 1024 ** 2,
          "GB": _GIB, "GIB": _GIB, "TB": 1024 ** 4, "TIB": 1024 ** 4}


def _gib(n) -> str:
    """GiB, the unit `df -h` and `ls -h` print. Decimal G printed 121.6 for
    df's 114, which read as a different measurement rather than a unit."""
    return f"{(n or 0) / _GIB:.1f} GiB"


def _age(now, ts) -> str:
    minutes = int((now - ts) // 60)
    return f"{minutes // 60} h {minutes % 60} min ago" if minutes >= 60 else f"{minutes} min ago"


def _fraction(used, size):
    """The API reports some pool figures as bytes and some as a 0..1
    fraction, so both are read. Measured: `pve/data data 11%, metadata 1%`
    matched `lvs` on the live host."""
    try:
        used, size = float(used), float(size or 0)
    except (TypeError, ValueError):
        return None
    if 0 <= used <= 1:
        return used
    return used / size if size > 0 else None


_START = re.compile(r"Starting Backup of VM (\d+)")
_FINISHED = re.compile(r"Finished Backup of VM (\d+)")
_FAILED = re.compile(r"ERROR: Backup of VM (\d+) failed\s*-?\s*(.*)")
_ARCHIVE = re.compile(r"creating vzdump archive '([^']+)'")
_SIZE = re.compile(r"archive file size: ([\d.]+)\s*([KMGT]?i?B)", re.I)


def parse_vzdump_log(lines: list) -> dict:
    """Per VM, from one vzdump task's log: ``{vmid: {ok, size, froze,
    archive, error}}``. A job over several VMs is ONE task, so its log is
    split at each `Starting Backup of VM` line. PVE's "GB" is GiB, measured:
    a `25.21GB` archive is 26G in `ls -h`, which decimal would put at 24."""
    out, vmid = {}, None
    for line in lines:
        m = _START.search(line)
        if m:
            vmid = int(m.group(1))
            out[vmid] = {"ok": None, "size": None, "froze": False,
                         "archive": "", "error": ""}
            continue
        m = _FAILED.search(line)
        if m:
            entry = out.setdefault(int(m.group(1)), {"size": None, "froze": False,
                                                     "archive": ""})
            entry.update(ok=False, error=m.group(2).strip() or line.strip())
            continue
        if vmid is None:
            continue
        entry = out[vmid]
        if _FINISHED.search(line) and int(_FINISHED.search(line).group(1)) == vmid:
            entry["ok"] = True if entry["ok"] is None else entry["ok"]
        elif _ARCHIVE.search(line):
            entry["archive"] = _ARCHIVE.search(line).group(1)
        elif _SIZE.search(line):
            num, unit = _SIZE.search(line).groups()
            entry["size"] = int(float(num) * _UNITS.get(unit.upper(), 1))
        elif "fs-freeze" in line and "issuing" in line:
            entry["froze"] = True
    return out


def image_jobs(now: float = None, client=None) -> list:
    """One row per imaged VM, one for the destination, one for the thin pools.

    Per-VM facts come from the vzdump TASK LOGS, because the backup listing
    is empty for an auditor token (measured, docs/VM_IMAGES.md section 6).
    So a VM row claims "the last run wrote this archive", never "the image
    is on disk now"; it says so, and the storage row's used-space check is
    what notices an image removed afterwards. Every read that fails is
    ``unknown`` (not the same as ok), and an unconfigured Proxmox is
    ``not_configured``, never ok.
    """
    now = now or time.time()
    if client is None:
        from modules.integrations.proxmox import ProxmoxIntegration
        client = ProxmoxIntegration()

    def row(unit, state, detail, **extra):
        return {"unit": unit, "what": _IMAGES_WHAT, "state": state,
                "detail": detail, "max_age_minutes": IMAGE_MAX_AGE_MINUTES, **extra}

    missing = client.missing_settings()
    if missing:
        return [row("vm-images", "not_configured",
                    "the Proxmox integration is not configured (" + ", ".join(missing)
                    + "), so the nightly images are not watched -- not the same as ok")]
    try:
        vmids = client.vmids()
    except ValueError as exc:
        return [row("vm-images", "not_configured", str(exc))]
    if not vmids:
        return [row("vm-images", "not_configured", "proxmox_backup_vmids names no VM")]
    storage = client.storage

    # ── per VM, newest task first, reading logs until every VM is answered ──
    tasks = client.vzdump_tasks()
    outcome, log_errors = {}, []
    if tasks["ok"]:
        finished = sorted((t for t in (tasks["data"] or []) if t.get("endtime")),
                          key=lambda t: t.get("starttime") or 0, reverse=True)
        for task in finished[:IMAGE_TASK_LOGS]:
            if all(v in outcome for v in vmids):
                break
            if str(task.get("id") or "") not in ("",) + tuple(str(v) for v in vmids):
                continue
            logged = client.task_log(task["upid"])
            if not logged["ok"]:
                log_errors.append(logged["error"])
                continue
            for vmid, fact in parse_vzdump_log(logged["data"]).items():
                if vmid in vmids and vmid not in outcome:
                    outcome[vmid] = {**fact, "endtime": task["endtime"],
                                     "status": str(task.get("status", ""))}

    listing = client.backups()
    listed = {str(item.get("volid", "")).rsplit("/", 1)[-1]
              for item in (listing.get("data") or [])} if listing["ok"] else set()

    rows, newest_sizes = [], []
    for vmid in vmids:
        unit = f"vm-image:{vmid}"
        fact = outcome.get(vmid)
        if not tasks["ok"]:
            rows.append(row(unit, "unknown", f"vzdump tasks unreadable: {tasks['error']} "
                                             f"-- not the same as ok"))
            continue
        if fact is None:
            why = (f"; {len(log_errors)} task log(s) unreadable ({log_errors[0]})"
                   if log_errors else "")
            state = "unknown" if log_errors else "never"
            rows.append(row(unit, state, f"no vzdump task in the last {IMAGE_TASK_LOGS} "
                                         f"mentions VM {vmid}{why}"))
            continue
        if fact.get("ok") is False:
            rows.append(row(unit, "failing",
                            f"latest vzdump run failed {_age(now, fact['endtime'])}: "
                            f"{fact['error']}"))
            continue
        if fact.get("size"):
            newest_sizes.append(fact["size"])
        archive = os.path.basename(fact.get("archive") or "")
        notes = [f"froze the filesystem: {'yes' if fact.get('froze') else 'NO (crash-consistent image)'}"]
        if fact.get("status", "").startswith("WARNINGS"):
            # Not a failure (the archive was written), and never silent.
            notes.append(f"its vzdump task finished with {fact['status']}")
        if listed and archive and archive not in listed:
            state = "missing"
            detail = (f"the last run wrote {archive} {_age(now, fact['endtime'])}, and the "
                      f"storage no longer lists it")
        elif now - fact["endtime"] > IMAGE_MAX_AGE_MINUTES * 60:
            state = "stale"
            detail = (f"last successful run {_age(now, fact['endtime'])} "
                      f"({_gib(fact.get('size'))}); nothing failed, and nothing has "
                      f"succeeded since")
        else:
            state = "ok"
            detail = f"last run {_age(now, fact['endtime'])} wrote {_gib(fact.get('size'))}"
        if not listed:
            notes.append("from the task log; this token cannot list the images themselves")
        rows.append(row(unit, state, "; ".join([detail] + notes),
                        last_success=fact["endtime"]))

    # ── the destination ─────────────────────────────────────────────────────
    unit = f"vm-images-storage:{storage}"
    st = client.storage_status()
    if not st["ok"]:
        rows.append(row(unit, "unknown", f"storage status unreadable: {st['error']} -- not the same as ok"))
    elif not (st["data"] or {}).get("active"):
        rows.append(row(unit, "inactive",
                        f"{storage} is not active: not mounted, or disabled. Tonight's "
                        f"job will fail (is_mountpoint refusing is this state, made visible)"))
    elif not newest_sizes:
        rows.append(row(unit, "unsized",
                        f"{_gib(st['data'].get('avail'))} free, and no archive size yet "
                        f"to size the next run against"))
    else:
        avail = st["data"].get("avail") or 0
        used = st["data"].get("used")
        largest, total = max(newest_sizes), sum(newest_sizes)
        need = largest * FIT_FACTOR
        if used is not None and used < PRESENT_FRACTION * total:
            rows.append(row(unit, "images_missing",
                            f"the storage holds {_gib(used)}, less than the newest images "
                            f"alone add up to ({_gib(total)}): an image was removed after "
                            f"it was written"))
        elif avail < need:
            rows.append(row(unit, "will_not_fit",
                            f"{_gib(avail)} free < {_gib(need)} ({FIT_FACTOR} x the largest "
                            f"image, {_gib(largest)}). vzdump writes before it prunes, so the "
                            f"next run will not fit beside the kept images"))
        else:
            rows.append(row(unit, "ok", f"{_gib(avail)} free; the largest image "
                                        f"({_gib(largest)}) fits with {_gib(avail - need)} to spare"))

    # ── the thin pools on the node ─────────────────────────────────────────
    pools = client.thin_pools()
    if not pools["ok"]:
        rows.append(row("thin-pools", "unknown", f"LVM-thin pools unreadable: {pools['error']} "
                                                 f"-- not the same as ok"))
    elif not pools["data"]:
        rows.append(row("thin-pools", "unknown",
                        "the node reports no LVM-thin pool, and the destination is "
                        "expected to be on one (docs/VM_IMAGES.md)"))
    else:
        parts, filling = [], []
        for pool in pools["data"]:
            name = f"{pool.get('vg', '?')}/{pool.get('lv', '?')}"
            data = _fraction(pool.get("used"), pool.get("lv_size"))
            meta = _fraction(pool.get("metadata_used"), pool.get("metadata_size"))
            shown = (f"{name} data {'?' if data is None else f'{data:.0%}'}, "
                     f"metadata {'?' if meta is None else f'{meta:.0%}'}")
            parts.append(shown)
            if (data or 0) >= POOL_WARN_FRACTION or (meta or 0) >= POOL_WARN_FRACTION:
                filling.append(shown)
            elif data is None or meta is None:
                filling.append(shown + " (unreadable figure)")
        rows.append(row("thin-pools", "pool_filling" if filling else "ok",
                        ("; ".join(filling) + f" (warn at {POOL_WARN_FRACTION:.0%})")
                        if filling else "; ".join(parts)))
    return rows


def health(now: float = None, run=None, images=None) -> dict:
    """*images*: the image rows, for a caller that has them; by default they
    are read from Proxmox."""
    jobs = [job_status(j, now, run) for j in JOBS]
    jobs += image_jobs(now) if images is None else list(images)
    bad = [j["unit"] for j in jobs if j["state"] != "ok"]
    return {"ok": True, "jobs": jobs, "not_ok": bad,
            "headline": (f"{len(jobs) - len(bad)} of {len(jobs)} job(s) ok"
                         + (f"; not ok: {', '.join(bad)}" if bad else ""))}
