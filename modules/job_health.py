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
     # C144: the row says what it covers. A restore test beside encrypted
     # off-box copies reads as covering them, and it restores the PLAIN local
     # copy; the off-box copies are proven only by NETBOX_BACKUP 6g, by hand.
     "what": "NetBox restore of the plain LOCAL hourly copy into a scratch postgres, "
             "daily (P.2); it does not read the encrypted off-box copies (NETBOX_BACKUP 6g)"},
    {"unit": "nmas-heartbeat-check", "max_age_minutes": 180,
     "what": "each device's heartbeat window still fits its measured rate, hourly (C16)",
     # Both of its failures (a device with no rule, C151; a rate that moved)
     # are fixed by regenerating the rules (NSOT_PLAN P.1 step 5).
     "remedy": {"label": "Re-measure the heartbeat windows: each device's installed and new "
                         "window previewed, confirmed, then the one host step that installs them",
                "href": "/v2/monitoring/heartbeat",
                "reference": "NSOT_PLAN P.7"}},
    {"unit": "nmas-startup-check", "max_age_minutes": 180,
     "what": "every device's startup config carries the credential NMAS holds, hourly (C53)"},
)

JOURNAL_DAYS = 14

import re as _re

_NAMES_A_FAILURE = _re.compile(
    r"not found|REFUSED|FAILED|ERROR|Error|Traceback|denied|No such", _re.I)

#: systemd's own record of how the main process ended:
#: "Main process exited, code=exited, status=2/INVALIDARGUMENT".
_EXIT_STATUS = _re.compile(r"Main process exited, code=\w+, status=(\S+)")


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
    #
    # And NEVER a line that names nothing (the operator, 2026-10-01): the
    # startup check's 07:04 run failed with no line matching, and its FIRST
    # line was quoted, "s1 PERSISTED the startup config carries ...", a
    # success presented as the error. With no line naming a failure the row
    # says so, with the exit status systemd recorded and where to read more.
    last_ok, last_fail, streak, last_error = None, None, 0, ""
    streak_start = None
    run_lines: list = []
    exit_status = ""
    for ts, text in rows:
        if "systemd[" in text:
            if "Starting " in text or "Started " in text:
                run_lines, exit_status = [], ""
            status = _EXIT_STATUS.search(text)
            if status:
                exit_status = status.group(1)
        elif text.strip():
            run_lines.append(text.split(": ", 1)[-1].strip())
        if "Deactivated successfully" in text:
            last_ok, streak, streak_start = ts, 0, None
        elif "Failed with result" in text:
            if streak == 0:
                streak_start = ts
            last_fail, streak = ts, streak + 1
            named = [l for l in run_lines if _NAMES_A_FAILURE.search(l)]
            last_error = named[0] if named else (
                "no line of its output names the failure"
                + (f" (it exited with status {exit_status})" if exit_status else "")
                + f"; read it with: journalctl -u {unit} -n 50 --no-pager")
            run_lines, exit_status = [], ""

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
    # The row states its own window: "last success 1104 min ago" was read as
    # a missed run on a DAILY timer, and the reader had nothing on the row to
    # judge it against (2026-09-26). A true "ok" must say why it is ok.
    window = job["max_age_minutes"]
    window_text = f"{window // 60} h" if window % 60 == 0 else f"{window} min"
    detail = (f"last success {ago(last_ok)} (stale after {window_text})"
              + (f"; {streak} consecutive failure(s), last {ago(last_fail)}"
                 if failed_last else "")
              + (f"; last error: {last_error}" if failed_last and last_error else ""))
    # SINCE WHEN the state has held (7.2: a Needs attention row says since
    # when). Failing: the streak's first failure in the journal window. Stale:
    # the moment the last success aged past the window. Otherwise not known,
    # and None says so rather than a time that answers a different question.
    since = None
    if state in ("failing", "never_succeeded"):
        since = streak_start
    elif state == "stale" and last_ok is not None:
        since = last_ok + max_age
    remedy = job.get("remedy") if state in ("failing", "never_succeeded") else None
    return {**out, "state": state, "detail": detail, "since": since,
            **({"action": dict(remedy)} if remedy else {}),
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

# ── ZFS pools (register B7) ─────────────────────────────────────────────────
#
# `vmdata` holds every VM, and it was made sparse to fit B6's test restore,
# so it can now overcommit. The figure that says how full it is, is ALLOC
# against SIZE (`zpool list`). Proxmox's own storage percentage counts
# REFRESERVATIONS: it read 85 % when 8 % was written, and 52 % after one
# reservation was dropped, while the data on the pool had not moved.
#
# Two thresholds, and they are different kinds of number:
#: DEGRADING, a convention and not a cliff: as a pool fills, the allocator
#: searches harder for free space, and fragmentation compounds it. Gradual,
#: workload-dependent, and milder on NVMe than on spinning disks.
ZFS_DEGRADING_FRACTION = 0.80
#: WILL PAUSE, a hard point: OpenZFS keeps a "slop" reserve of 1/32 of the
#: pool (capped at 128 GiB) and refuses ordinary writes once free space falls
#: to it. A zvol write then fails with ENOSPC, and QEMU's default for that is
#: to PAUSE the VM. So when this pool fills, every VM on it freezes at once.
#: Warned while the headroom above the reserve is under this share of the pool.
ZFS_PAUSE_HEADROOM_FRACTION = 0.05
ZFS_SLOP_SHIFT = 5
ZFS_MAX_SLOP = 128 * 1024 ** 3


def zfs_slop(size: int) -> int:
    """The reserve below which ZFS refuses ordinary writes (OpenZFS
    `spa_slop_shift` = 5, capped by `spa_max_slop`; from its defaults, not
    measured on this host)."""
    return min(int(size) >> ZFS_SLOP_SHIFT, ZFS_MAX_SLOP)


def zfs_rows(pools: dict) -> list:
    """One row per ZFS pool, from ``disks/zfs``. An empty answer is
    ``unknown``: this token was already shown an empty backup LISTING that
    was hidden rather than absent, so empty never means "none"."""
    what = "ZFS pool on the Proxmox host (B7): how full, from ALLOC/SIZE"

    def row(unit, state, detail):
        return {"unit": unit, "what": what, "state": state, "detail": detail,
                "max_age_minutes": None}

    if not pools["ok"]:
        return [row("zfs-pools", "unknown", f"ZFS pools unreadable: {pools['error']} "
                                            f"-- not the same as ok")]
    if not pools["data"]:
        return [row("zfs-pools", "unknown",
                    "the node reports no ZFS pool. Empty is not the same as none: "
                    "this token has been shown an empty listing that was hidden")]
    rows = []
    for pool in pools["data"]:
        name = pool.get("name", "?")
        size, alloc = int(pool.get("size") or 0), int(pool.get("alloc") or 0)
        free = int(pool.get("free") if pool.get("free") is not None else size - alloc)
        health = str(pool.get("health", "?"))
        if size <= 0:
            rows.append(row(f"zfs-pool:{name}", "unknown", f"{name} reports no size"))
            continue
        fill = alloc / size
        slop = zfs_slop(size)
        headroom = free - slop
        detail = (f"{name} {fill:.1%} allocated ({_gib(alloc)} of {_gib(size)}), "
                  f"frag {pool.get('frag', '?')}%, {health}; "
                  f"{_gib(max(headroom, 0))} before ZFS refuses writes "
                  f"(its reserve is {_gib(slop)})")
        if health != "ONLINE":
            state = "pool_unhealthy"
            detail = f"{name} is {health}, not ONLINE: a suspended pool stops writes. " + detail
        elif headroom < ZFS_PAUSE_HEADROOM_FRACTION * size:
            state = "pool_will_pause"
            detail += ("; at the reserve every VM on this pool PAUSES (QEMU stops a VM "
                       "whose disk write gets ENOSPC)")
        elif fill >= ZFS_DEGRADING_FRACTION:
            state = "pool_degrading"
            detail += (f"; past {ZFS_DEGRADING_FRACTION:.0%}, a convention rather than a "
                       f"cliff: allocation slows as free space fragments")
        else:
            state = "ok"
        rows.append(row(f"zfs-pool:{name}", state, detail))
    return rows
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
        # The images' remedy is on Proxmox, the operator's machine (C164): the
        # action names where to look, never a command run from here.
        if state in ("failing", "missing", "stale", "never", "will_not_fit"):
            extra.setdefault("action", {
                "label": ("Free space on the backup storage, or keep fewer images"
                          if state == "will_not_fit" else
                          "Read the backup task's log in Proxmox (Datacenter > Tasks, "
                          "vzdump) for this VM")})
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

    # A run in progress: a task the node lists with no end time yet.
    running = ([t for t in (tasks["data"] or []) if not t.get("endtime")]
               if tasks["ok"] else [])

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
    elif running:
        # vzdump writes each image BEFORE pruning the one it replaces, so in
        # the middle of a run free space is low by design: measured
        # 2026-10-01, 26.2 GiB read at 08:41 UTC between VM 100's write and its
        # prune, 48.7 GiB at the run's end. Judged when the run ends (C288).
        first = min(running, key=lambda t: t.get("starttime") or now)
        rows.append(row(unit, "backup_running",
                        f"a backup is running (started {_age(now, first.get('starttime') or now)}): "
                        f"{_gib(st['data'].get('avail'))} free now, below what the next run starts "
                        f"with, because vzdump writes each image before pruning the one it "
                        f"replaces; free space is judged once the run ends"))
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

    rows += zfs_rows(client.zfs_pools())
    # The TLS fact belongs to the rows it concerns (the operator, 2026-09-26):
    # printed as a warning above the headline, on every run, it was correct
    # and it was noise, and it pushed the summary line off the top.
    if getattr(client, "verify_tls", True) is False:
        for r in rows:
            r["detail"] += "; TLS not verified (proxmox_verify_tls is off)"
    return rows


# ---------------------------------------------------------------------------
# Settings a guard depends on (register C28)
# ---------------------------------------------------------------------------
#
# After the 2026-09-23 settings erasure nothing re-established which settings
# were LOAD-BEARING. Each empty one was found by the failure it caused:
# clab_host during r6's persistence, oxidized_url during the freshness work,
# clab_sync_script during a credential exposure (B15). One finding, found four
# times. `discover_empty_default_guards()` had derived the class from the code
# all along, and was called only by tests: it answered "which settings gate a
# guard", and nothing ever asked "are they set HERE". These rows ask.

_SETTINGS_WHAT = ("a setting a guard depends on; empty, the guard refuses with "
                  "'not configured', which reads like a check that ran (C28)")

_guard_map_cache = None


def _guard_settings() -> dict:
    """``{key: [where, ...]}``: discovered from the code, plus the recorded list.

    Cached per process: it parses the code, and the code does not change under
    a running app.
    """
    global _guard_map_cache
    if _guard_map_cache is None:
        from modules.settings_schema import (GUARD_GATING_EMPTY_DEFAULTS,
                                             discover_empty_default_guards)
        found = dict(discover_empty_default_guards())
        for key in GUARD_GATING_EMPTY_DEFAULTS:
            found.setdefault(key, ["recorded by hand in "
                                   "settings_schema.GUARD_GATING_EMPTY_DEFAULTS"])
        _guard_map_cache = found
    return _guard_map_cache


def settings_rows(guards: dict = None, load=None) -> list:
    """One row per guard-gating setting: ``ok`` when set, ``unset_guard`` when
    empty. An unreadable settings file is ONE ``unknown`` row, never a set of
    "empty" rows: every key would read as empty, and the loudest possible
    answer would be the wrong one. A scan that finds no such settings is
    ``unknown`` too, since that is a scan that could not run."""
    from modules.config import SettingsUnreadable, load_user_settings
    from modules.settings_schema import DEFAULTS

    def row(unit, state, detail, action=None):
        return {"unit": unit, "what": _SETTINGS_WHAT, "state": state,
                "detail": detail, "max_age_minutes": 0,
                **({"action": action} if action else {})}

    guards = _guard_settings() if guards is None else guards
    if not guards:
        return [row("settings", "unknown",
                    "the scan found no guard-gating settings; that is a scan "
                    "that could not run, not a clean result")]
    try:
        stored = (load or load_user_settings)()
    except SettingsUnreadable as exc:
        return [row("settings", "unknown",
                    f"user_settings.json could not be read ({exc}); whether "
                    "any guard's setting is empty is unknown")]
    # C31: "nothing to set here" is a DECISION, and reported as one, with who
    # and when; "somebody forgot" stays `unset_guard`. The two used to share
    # a state, so a dead consumer and an erased setting looked the same.
    declared = stored.get("settings_not_applicable") or {}
    out = []
    for key in sorted(guards):
        value = stored.get(key, DEFAULTS.get(key, ""))
        where = "; ".join(guards[key])
        decl = declared.get(key)
        said = (f"declared NOT APPLICABLE by {decl.get('by', '?')} at "
                f"{decl.get('at', '?')}: {decl.get('reason', '')}") if decl else ""
        if value in ("", None, [], {}):
            if decl:
                out.append(row(f"setting:{key}", "not_applicable",
                               f"{said}. It gates {where}, which nothing on this "
                               "host uses"))
            else:
                out.append(row(f"setting:{key}", "unset_guard",
                               f"EMPTY. It gates {where}, which will refuse and say "
                               "'not configured' until it is set",
                               {"label": f"Set {key} in Settings, or record on the host that "
                                         "nothing here uses it (a decision with who, when "
                                         "and why)",
                                "command": f"nmas-setting-not-applicable {key} --reason "
                                           "'<why>'"}))
        elif decl:
            out.append(row(f"setting:{key}", "contradiction",
                           f"SET, and also {said}. One of the two is wrong",
                           {"label": f"Clear {key} in Settings, or withdraw the declaration "
                                     "that nothing uses it",
                            "command": f"nmas-setting-not-applicable {key} --withdraw"}))
        else:
            out.append(row(f"setting:{key}", "ok", "set"))
    return out


# ---------------------------------------------------------------------------
# Credential rotations whose boot file is not known SAFE (register B15)
# ---------------------------------------------------------------------------

_ROTATION_WHAT = ("a device's credential rotation; until a persist reads SAFE, "
                  "a reboot or redeploy may bring back the previous password (B15)")


def known_devices() -> tuple:
    """``(names, reason)``: every device NMAS knows, lower-cased, from each
    list's INVENTORY and each list's MANIFEST (a device mid-onboarding is in
    the manifest and not yet the inventory, and has not left). *reason* is
    non-empty when the set could not be established, and an empty set is such
    a case: "no device anywhere" is far likelier an unread store than a fleet
    that has all left, and must never be read as "every device departed"."""
    import os

    from modules import device as _device
    from modules.config import LISTS_DIR
    from modules.nsot import manifest as _m

    names, problems = set(), []
    try:
        lists = _device.get_device_lists()
    except Exception as exc:                   # noqa: BLE001
        return set(), f"the device lists could not be read ({type(exc).__name__})"
    for lst in lists:
        base = os.path.join(LISTS_DIR, lst.get("filename", ""))
        csv = os.path.join(base, "devices.csv")
        try:
            for d in _device.load_saved_devices(csv) if os.path.exists(csv) else []:
                if d.get("hostname"):
                    names.add(d["hostname"].lower())
        except Exception as exc:               # noqa: BLE001
            problems.append(f"{lst.get('name')}: inventory ({type(exc).__name__})")
        repo = os.path.join(base, "config_repo")
        if os.path.isdir(repo):
            try:
                for entry in (_m.load(repo).get("devices") or {}).values():
                    if entry.get("name"):
                        names.add(entry["name"].lower())
            except Exception as exc:           # noqa: BLE001
                problems.append(f"{lst.get('name')}: manifest ({type(exc).__name__})")
    if problems:
        return names, "could not read " + "; ".join(problems)
    if not names:
        return names, "no device is known in any list, so none can be called departed"
    return names, ""


def rotation_rows(records: list = None, known: tuple = None) -> list:
    """One row per device with a recorded rotation, from its LATEST record.

    s1's rotation of an exposed credential left its boot file holding that
    credential, and the only report was a terminal message that is gone. So a
    device stays in front of an operator until a later persist is recorded
    reaching SAFE (`nmas-persist-credential` records one).

    **Derived from the audit AND from where the device is known** (C54, the
    operator's, 2026-09-27). The audit is append-only, so a device that left
    kept its row for ever: `rotation:bp-ztp-a` read `ok` about a device
    destroyed a day earlier, and one whose last record was NOT safe would
    have read `not_safe_to_reboot` for ever, uncleared by anything. A device
    in no list's inventory or manifest is `departed`, its last record named
    as history. When the known set cannot be established, no row is called
    departed (the verdict stands, and the reason is said)."""
    from modules.nsot import credential_rotation as cr

    records = cr.rotation_records() if records is None else records
    names, why_not = known_devices() if known is None else known
    latest = {}
    for rec in records:
        if rec.get("device"):
            latest[rec["device"]] = rec
    rows = []
    for device, rec in sorted(latest.items()):
        state, stage, at = rec.get("state", ""), rec.get("failed_stage", ""), rec.get("at", "")
        if not why_not and device.lower() not in names:
            unsafe = state not in (cr.ROTATED_PERSISTED, cr.REVERTED, cr.NOT_STARTED)
            rows.append({"unit": f"rotation:{device}", "what": _ROTATION_WHAT,
                         "device": device, "state": "departed", "max_age_minutes": 0,
                         "detail": (f"{device} is in no list's inventory or manifest: it has "
                                    f"left management. Its last rotation record ({state} at "
                                    f"{at}) is history, not a claim about a managed device"
                                    + ("; that record was NOT safe to reboot, so if the device "
                                       "still exists somewhere, nothing here manages it"
                                       if unsafe else ""))})
            continue
        act = None
        if state == cr.ROTATED_PERSISTED:
            st, detail = "ok", f"persisted and read SAFE at {at}"
        elif state in (cr.REVERTED, cr.NOT_STARTED):
            st, detail = "ok", f"unchanged: the last rotation ended {state} at {at}"
        elif state == cr.ROTATED_UNVERIFIED and stage == "device_startup_config":
            # P.6 M4: the DEVICE's own startup config, not a containerlab file.
            # `nmas-persist-credential` is the containerlab chain and must not
            # be advised here (for a device outside containerlab it resolves an
            # unknown lab to rcn-lab1's paths, C50).
            st, detail = ("not_safe_to_reboot",
                          f"at {at} the device's startup config did NOT carry the rotated "
                          f"credential: its running config holds the only working one. Do "
                          f"not reload it; run nmas-persist-native {device} --list <list>")
            act = {"label": "Persist the running credential on the device before anything "
                            "reloads it: Persist… on its Device page, or on the host (the "
                            "record names no list: use the device's own)",
                   "command": f"nmas-persist-native {device} --list <its list>"}
        elif state == cr.ROTATED_UNVERIFIED:
            st, detail = ("not_safe_to_reboot",
                          f"rotated at {at}; persistence FAILED at {stage or 'the chain'}. "
                          f"Fix it, then run nmas-persist-credential {device}")
            act = {"label": f"Fix the failed stage ({stage or 'the chain'}), then verify the "
                            "boot file", "command": f"nmas-persist-credential {device}"}
        elif state == cr.ROTATED_NOT_RECORDED:
            st, detail = ("not_recorded",
                          f"rotated at {at} but NOT RECORDED: the device accepts only the "
                          "new password and the tool may hold the old one. Do not rotate "
                          "again or reboot; record it from the kept staging copy")
            act = {"label": "Ask the device which credential it holds and record the kept "
                            "staging copy if it does; do not rotate again or reboot until then",
                   "command": f"nmas-rotation-recover {device} --list <its list>"}
        elif state == cr.STAGED_NEVER_APPLIED:
            st, detail = "ok", (f"at {at} the device refused the staged credential and "
                                "accepted the recorded one: the rotation never landed")
        elif state == cr.NOTHING_STAGED:
            st, detail = "ok", f"at {at} nothing was staged: nothing to recover"
        elif state == cr.NEITHER_ACCEPTED:
            st, detail = ("neither_accepted",
                          f"at {at} the device refused BOTH the staged credential and the "
                          "recorded one: it may be locked out; recover on the console")
            act = {"label": "Recover the device on its console, with the break-glass record"}
        elif state == cr.RECOVERY_INCONCLUSIVE:
            st, detail = "unknown", (f"a recovery at {at} could not settle it; the staged "
                                     "file is kept. Run it again when the device answers")
            act = {"label": "Run the recovery again when the device answers",
                   "command": f"nmas-rotation-recover {device} --list <its list>"}
        elif state == cr.ROTATED_PENDING_PERSIST:
            st, detail = ("not_safe_to_reboot",
                          f"rotated at {at}; persistence NOT ATTEMPTED. Run "
                          f"nmas-persist-credential {device} to verify the boot file")
            act = {"label": "Verify the boot file holds the rotated credential",
                   "command": f"nmas-persist-credential {device}"}
        elif state == cr.REVERT_FAILED:
            st, detail = "revert_failed", (f"the new credential did not verify and the "
                                           f"revert failed at {at}: the device may be "
                                           "locked out; recover on the console")
            act = {"label": "Recover the device on its console, with the break-glass record"}
        else:
            st, detail = "unknown", f"last recorded state {state or '(none)'} at {at}"
        rows.append({"unit": f"rotation:{device}", "what": _ROTATION_WHAT,
                     "device": device, "state": st, "max_age_minutes": 0,
                     **({"action": act} if act else {}),
                     "detail": detail + (f" (whether it has left management is unknown: "
                                         f"{why_not})" if why_not and names else "")})
    return rows


def staged_rotation_rows(lists=None, holder=None) -> list:
    """A credential a rotation STAGED and never cleared (the rotate screen's
    fourth failure mode, 2026-09-29). The password is staged before the push,
    so a process that dies between the push and the record leaves the device on
    a password the inventory does not hold, and the staged file its only copy.
    Nothing read that file. A device someone holds right now is mid-rotation,
    and is left to the in-flight panel."""
    import os

    from modules.config import LISTS_DIR
    from modules.device import get_device_lists
    from modules.nsot import credential_rotation as cr
    from modules.nsot import device_ops

    holder = holder or device_ops.holder
    rows = []
    try:
        entries = get_device_lists() if lists is None else lists
    except Exception as exc:                          # noqa: BLE001
        return [{"unit": "rotation-staged", "what": _ROTATION_WHAT, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": f"the device lists could not be read ({exc})"}]
    from modules.nsot import adopt as _adopt

    for item in entries:
        repo = os.path.join(LISTS_DIR, item["filename"], "config_repo")
        for s in cr.staged_devices(repo):
            if holder(item["name"], s["device"]):
                continue
            since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(s["since"]))
            # AN ADOPTION'S staged password names ITS recovery: the rotation's
            # works from an inventory row, which a device being adopted lacks,
            # so naming it would send a person to a command that stops.
            if _adopt.is_adoption_staged(repo, s["device"]):
                rows.append({
                    "unit": f"rotation-staged:{item['name']}/{s['device']}",
                    "what": _ROTATION_WHAT, "device": s["device"], "list": item["name"],
                    "state": "not_recorded", "max_age_minutes": 0,
                    "detail": (f"an adoption of {s['device']} staged a password for the "
                               f"tool's own account at {since} and never cleared it: the "
                               "device may hold that account while the tool holds no "
                               "credential for it, and the staged file is its only copy"),
                    "action": {"label": "Ask the device whether it holds the tool's account "
                                        "with the staged password, and record it if it does",
                               "command": f"nmas-adopt-recover {s['device']} "
                                          f"--list {item['name']}"}})
                continue
            rows.append({
                "unit": f"rotation-staged:{item['name']}/{s['device']}", "what": _ROTATION_WHAT,
                "device": s["device"], "list": item["name"], "state": "not_recorded",
                "max_age_minutes": 0,
                "detail": (f"a rotation of {s['device']} staged a new password at {since} and "
                           "never cleared it: the device may hold it while the tool holds the "
                           "old one, and the staged file is its only copy. Do not rotate again "
                           "or reboot until it is settled"),
                "action": {"label": "Ask the device which credential it holds, and record the "
                                    "staged one if it does",
                           "command": f"nmas-rotation-recover {s['device']} "
                                      f"--list {item['name']}"}})
    return rows


def sync_owner_rows(run=None, get=None) -> list:
    """`clab_sync_script` must name what the clab-sync timer runs (B15).

    Two owners of one fact: the rotation's persistence chain reads the setting,
    the timer's unit names the script itself. The setting was empty for three
    days while the timer worked, so every rotation's chain stopped at its sync
    stage and a timer closed the window instead."""
    from modules.settings_schema import get_setting

    run = run or _run
    get = get or get_setting
    row = {"unit": "clab-sync-owner", "max_age_minutes": 0,
           "what": "the persistence chain's sync script is the one the timer runs (B15)"}
    rc, out = run(["systemctl", "show", "clab-sync.service", "-p", "LoadState",
                   "-p", "ExecStart"])
    props = dict(l.split("=", 1) for l in out.splitlines() if "=" in l) if rc == 0 else {}
    if not props:
        return [{**row, "state": "unknown",
                 "detail": "systemctl could not be asked -- not the same as ok"}]
    if props.get("LoadState") == "not-found":
        return [{**row, "state": "not_installed",
                 "detail": "clab-sync.service is not installed here"}]
    import re as _re
    m = _re.search(r"path=(\S+)", props.get("ExecStart", ""))
    unit_path = m.group(1) if m else ""
    setting = (get("clab_sync_script", "") or "").strip()
    if not setting:
        return [{**row, "state": "unset_guard",
                 "detail": f"clab_sync_script is EMPTY; the timer runs {unit_path or '?'}",
                 "action": {"label": f"Set clab_sync_script in Settings to the script the "
                                     f"timer runs: {unit_path or '(the unit names none)'}"}}]
    if unit_path and setting != unit_path:
        return [{**row, "state": "mismatch",
                 "detail": f"clab_sync_script is {setting} but the timer runs {unit_path}",
                 "action": {"label": f"Make them one: set clab_sync_script to {unit_path}, or "
                                     "point the timer at the setting's script"}}]
    return [{**row, "state": "ok", "detail": f"both name {setting}"}]


#: A declared not-applicable setting is a recorded decision, not a fault. It
#: is still counted in the headline, so it cannot vanish from view.
#: `settling`: a change not yet taken up where it is being taken up (the
#: generated Prometheus targets, C232), dated with when to ask again. Nothing
#: for a person to do; the next read says whether it settled or differs.
#: `backup_running`: the backup storage is not judged mid-run (C288).
OK_STATES = ("ok", "not_applicable", "departed", "settling", "backup_running")


def ztp_responder_rows(run=None, get=None) -> list:
    """The ZTP responder (P.6): listening, and not failing. None while ZTP is
    not configured.

    A responder that cannot serve does not delay an onboarding, it FAILS one:
    M4 measured IOS-XE 17.6 AutoInstall giving up after about 2.5 minutes and
    nine requests, and the device then needs a reload. So its failures are a
    row of their own. The socket is systemd's (it starts the service on the
    first request), and the service's journal carries `handler FAILED` for
    every request a handler could not finish."""
    from modules.settings_schema import get_setting

    run = run or _run
    get = get or get_setting
    if not (get("kea_ztp_fragment", "") or "").strip():
        return []
    row = {"unit": "nmas-ztp-responder", "max_age_minutes": 0,
           "what": "the ZTP responder is listening and not failing (a device's "
                   "AutoInstall gives up after about 2.5 minutes)"}
    rc, out = run(["systemctl", "show", "nmas-ztp-responder.socket", "-p", "LoadState",
                   "-p", "ActiveState", "-p", "Listen"])
    props = dict(l.split("=", 1) for l in out.splitlines() if "=" in l) if rc == 0 else {}
    if not props:
        return [{**row, "state": "unknown",
                 "detail": "systemctl could not be asked -- not the same as ok"}]
    if props.get("LoadState") == "not-found":
        return [{**row, "state": "not_installed",
                 "detail": "nmas-ztp-responder.socket is not installed (docs/DEPLOY_LINUX.md)",
                 "action": {"label": "Install and enable the socket on the host",
                            "reference": "docs/DEPLOY_LINUX.md"}}]
    if props.get("ActiveState") != "active":
        return [{**row, "state": "socket_down",
                 "detail": f"the socket is {props.get('ActiveState') or '?'}: nothing answers udp/69",
                 "action": {"label": "Start the socket on the host",
                            "command": "sudo systemctl start nmas-ztp-responder.socket"}}]
    ok, lines = _journal("nmas-ztp-responder.service", run)
    if not ok:
        return [{**row, "state": "unknown",
                 "detail": "the responder's journal could not be read -- not the same as ok"}]
    starts = [i for i, (_t, text) in enumerate(lines) if "serving ZTP bootstrap configs" in text]
    since = lines[starts[-1] + 1:] if starts else []
    failed = [t for t, text in since
              if "handler FAILED" in text or "Exception in thread" in text]
    listen = props.get("Listen", "")
    if failed:
        return [{**row, "state": "failing",
                 "detail": (f"{len(failed)} request(s) the handler could not finish since the "
                            f"responder last started, the latest at "
                            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(failed[-1]))}. "
                            "A device that asked then has probably given up and needs a reload"),
                 "action": {"label": "Read the responder's own output on the host",
                            "command": "journalctl -u nmas-ztp-responder.service -n 50 "
                                       "--no-pager"}}]
    return [{**row, "state": "ok",
             "detail": (f"listening on {listen}; " + (
                 "no handler failures since it last started" if starts else
                 "not started yet (systemd starts it on the first request)"))}]


#: An unreadable device becomes a WARNING once it has been unreadable this
#: long: three hourly runs in a row (the first, and two retries). At 06:03 on
#: 2026-10-01 seven devices were unreadable for one run and read at the next;
#: a run or two is weather, three is a device to look at.
UNREAD_PERSISTS_S = 2 * 3600


def startup_rows(read=None, now: float = None) -> list:
    """C53, from the hourly job's file (never a device session per request).

    One row per device whose startup config does NOT carry the credential
    NMAS holds, or could not be asked; one summary row when every device
    carries it, naming the count so a zero cannot pose as coverage. Nothing
    when the job has never run: its own unit row says that."""
    from modules.nsot import startup_check

    now = time.time() if now is None else now
    what = "the device's startup config carries the credential NMAS holds (C53)"
    try:
        res = (read or startup_check.read_results)()
    except Exception as exc:                          # noqa: BLE001
        return [{"unit": "startup-check", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": f"data/startup_check.json is unreadable: {exc} -- not the same as ok"}]
    if not res:
        return []
    at = res.get("at") or 0
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(at))
    devices = res.get("devices") or []
    if now - at > 3 * 3600:
        return [{"unit": "startup-check", "what": what, "state": "stale",
                 "max_age_minutes": 0,
                 "detail": f"last checked {when}; stale after 3 h"}]
    if not devices:
        # "0 of 0 boot the right credential" is a vacuous pass: a job that
        # found no device has checked nothing.
        return [{"unit": "startup-check", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": f"the last run (at {when}) found NO devices to check"}]
    rows = []
    # A device the run could not READ is not a device that would boot the
    # wrong credential (the operator, 2026-10-01: at 06:03 seven slow reads
    # drew as Critical). They are ONE row naming them, with since when and what
    # to do; quiet for a run or two, a warning once it persists.
    unread = [d for d in devices if d.get("state") not in ("persisted", "not_persisted")]
    if unread:
        # A device the reachability reader saw go silent was booting, not
        # broken (the operator, 2026-10-01): said beside the check's reason.
        from modules.readers.reachability import outage_words
        booting = {d.get("device"): outage_words(d.get("device"), at) for d in unread}
        first = min((d.get("since") or at) for d in unread)
        persisting = at - first >= UNREAD_PERSISTS_S
        names = ", ".join(d.get("device", "?") for d in unread)
        nxt = time.strftime("%H:%M", time.localtime(at + 3600))
        rows.append({
            "unit": "startup-check:unread", "what": what,
            "state": "unread_persisting" if persisting else "unread",
            "headline": (f"The startup check has not read {names} since "
                         f"{time.strftime('%H:%M', time.localtime(first))}" if persisting else
                         f"The startup check could not read {len(unread)} of {len(devices)} "
                         f"device(s) this hour: {names}"),
            "devices": [d.get("device") for d in unread], "since": first,
            "max_age_minutes": 0,
            "action": ({"label": "Check that each answers SSH from the host (its Device page "
                                 "shows whether it is answering), then run the check by hand",
                        "command": "python3 scripts/nmas-startup-check"} if persisting else
                       {"label": f"Nothing to do yet: it reads them again at the next run "
                                 f"(about {nxt}). If a device stays unreadable, check that it "
                                 "answers (its Device page)"}),
            "detail": "; ".join(
                f"{d.get('device')}: "
                + (f"{booting[d.get('device')]}; the check said: "
                   if booting[d.get("device")] else "")
                + f"{startup_check.brief(d.get('detail'))} (since "
                f"{time.strftime('%H:%M', time.localtime(d.get('since') or at))})"
                for d in unread) + f" (checked {when}). Not the same as a startup config "
                                   "that does not carry the credential: that is its own row."})
    for d in devices:
        if d.get("state") != "not_persisted":
            continue
        state = "not_safe_to_reboot"
        rows.append({"unit": f"startup:{d.get('list')}/{d.get('device')}", "what": what,
                     "device": d.get("device"), "list": d.get("list"), "state": state,
                     "since": d.get("since"),
                     **({"action": {"label": "Persist the running credential on the device "
                                             "before anything reloads it: Persist… on its "
                                             "Device page, or on the host",
                                    "command": f"nmas-persist-native {d.get('device')} "
                                               f"--list {d.get('list')}"}}
                        if state == "not_safe_to_reboot" else {}), "max_age_minutes": 0,
                     "detail": f"{d.get('detail', '')} (checked {when})"
                               + ("; a reload would boot a credential NMAS does not hold: "
                                  f"run nmas-persist-native {d.get('device')} --list {d.get('list')}"
                                  if state == "not_safe_to_reboot" else "")})
    if not rows:
        rows.append({"unit": "startup-check", "what": what, "state": "ok",
                     "max_age_minutes": 0,
                     "detail": f"{len(devices)} of {len(devices)} device(s) boot the "
                               f"credential NMAS holds (checked {when})"})
    return rows


def breakglass_rows(exports=None, current=None) -> list:
    """C182: does the break-glass record hold the credential NMAS holds NOW?

    The record lives off the host, so this compares the newest EXPORT this
    host logged (digests only) with the credentials held now, per list. A
    rotation since the export makes that device's entry stale, and this row
    says so until the record is exported again. It claims what was exported
    FROM THIS HOST; a record replaced elsewhere is not visible here, and a
    person checks one by hand with `nmas-breakglass verify <record> --against`.
    Nothing when no list holds a device (nothing to recover)."""
    import modules.breakglass as bg
    from modules.config import DATA_DIR

    what = "the break-glass record holds each device's current credential (C182)"
    # Written to RAM (/dev/shm, tmpfs on the host), never beside data/key.key:
    # the person copies it off the host and removes it, so one record exists.
    export_cmd = ("python3 scripts/nmas-breakglass export --list <list> "
                  "--out /dev/shm/rcn-breakglass.bg")
    try:
        current = _current_credential_digests() if current is None else current
        exports = bg.last_exports(DATA_DIR) if exports is None else exports
    except Exception as exc:                          # noqa: BLE001
        return [{"unit": "breakglass", "what": what, "state": "unknown", "max_age_minutes": 0,
                 "detail": f"could not be checked: {type(exc).__name__}: {exc}"}]
    current = {ln: d for ln, d in current.items() if d}
    if not current:
        return []
    if exports.get("state") == "unreadable":
        return [{"unit": "breakglass", "what": what, "state": "unknown", "max_age_minutes": 0,
                 "detail": f"{bg.EXPORT_LOG} is unreadable ({exports.get('error')}); not the "
                           "same as current"}]
    rows = []
    for list_name, now_digests in sorted(current.items()):
        last = (exports.get("by_list") or {}).get(list_name)
        if not last:
            rows.append({"unit": f"breakglass:{list_name}", "what": what, "state": "unknown",
                         "max_age_minutes": 0,
                         "action": {"label": "Export the break-glass record to establish the "
                                             "baseline its currency is tracked against",
                                    "open": "breakglass_export", "list": list_name,
                                    "command": export_cmd.replace("<list>", list_name)},
                         "detail": (f"no break-glass export of {list_name} is logged on this "
                                    f"host ({bg.EXPORT_LOG} began 2026-09-28), so nothing says "
                                    "whether the record holds the credentials in use; compare "
                                    "one by hand with `nmas-breakglass verify <record> --against "
                                    "<digests>`, or export again")})
            continue
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(last.get("at", 0)))
        # What the host can know, by how the export left (the operator,
        # 2026-09-29): a browser download is known to have been SENT to a
        # person; a host export to have been WRITTEN. Neither says where it went.
        made = (f"downloaded by {last.get('actor') or '?'} at {when}"
                if last.get("via") == "browser" else f"exported from this host at {when}")
        stale = [r for r in bg.compare(last.get("devices") or {}, now_digests)
                 if r["state"] in ("differs", "missing")]
        for r in stale:
            rows.append({"unit": f"breakglass:{list_name}/{r['device']}", "what": what,
                         "device": r["device"], "list": list_name, "state": "breakglass_stale",
                         "max_age_minutes": 0,
                         "action": {"label": "Export the break-glass record again: it cannot "
                                             "recover this device as it stands. Verify the "
                                             "copy on the machine that keeps it (C221): this "
                                             "host logs the export, never where the file went",
                                    "open": "breakglass_export", "list": list_name,
                                    "command": export_cmd.replace("<list>", list_name)},
                         "detail": (f"the record {made} "
                                    + ("holds an older credential: rotated since"
                                       if r["state"] == "differs" else "has no entry for it")
                                    + f" (written to {last.get('path', '?')})")})
        if not stale:
            rows.append({"unit": f"breakglass:{list_name}", "what": what, "state": "ok",
                         "max_age_minutes": 0,
                         # What the host KNOWS (C221, the operator, 2026-09-29): an export
                         # was WRITTEN here at that time. A copy lost on the way off the
                         # host (the operator's first export today, deleted before it
                         # reached the laptop) reads exactly the same, so the row never
                         # claims the record exists anywhere.
                         "action": {"label": "Verify the copy you keep: this host cannot see "
                                             "where the export went",
                                    "command": ("on the host: nmas-breakglass digests --list "
                                                f"{list_name} > digests.json; beside the record: "
                                                "nmas-breakglass verify rcn.bg --against "
                                                "digests.json")},
                         "detail": (f"{len(now_digests)} of {len(now_digests)} device(s) current "
                                    f"in the record {made}. The host logs the export, never "
                                    "where it went or whether it survived: verify the copy "
                                    "you keep")})
    return rows


def _current_credential_digests() -> dict:
    """{list: {hostname: digest}} of the credentials each list holds now."""
    import modules.breakglass as bg
    from modules.config import get_list_data_dir
    from modules.device import decrypt_field, get_device_lists, load_saved_devices

    out = {}
    for entry in get_device_lists():
        name = entry.get("name", "")
        rows = load_saved_devices(os.path.join(get_list_data_dir(name), "devices.csv"))
        out[name] = bg.digests_of([{"hostname": d.get("hostname", ""),
                                    "username": d.get("username", ""),
                                    "password": decrypt_field(d.get("password", ""))
                                    if d.get("password") else ""} for d in rows])
    return out


#: An operation's own session (not a long-lived pool's) held this long is
#: named: a pipeline's longest settle window is 90 s, and the device ends an
#: idle session at ten minutes, so an operation still holding one after that
#: has leaked it (C97).
LEAK_AFTER_SECONDS = 600


def ssh_session_rows(held: dict = None) -> list:
    """The SSH sessions THIS process holds, per device (register C97).

    The tool locked itself out of r2 with its own idle sessions, and nothing
    counted them. A device at its budget (its vty lines minus one kept for a
    person) is not ok, naming every holder; an operation's session held past
    ten minutes is named as a leak; otherwise one row says how many are held,
    so a zero is a statement and not an absence."""
    from modules import connection

    what = "SSH sessions this app holds, within each device's vty budget (C97)"
    try:
        held = connection.held_sessions() if held is None else held
    except Exception as exc:                          # noqa: BLE001
        return [{"unit": "ssh-sessions", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": f"the session count raised {type(exc).__name__}: {exc} "
                           "-- not the same as ok"}]
    rows = []
    for ip, h in sorted(held.items()):
        owners = ", ".join(f"{s['owner']} ({s['age_s']}s, idle {s['idle_s']}s)"
                           for s in h["sessions"])
        if h["held"] >= h["budget"]:
            rows.append({"unit": f"ssh:{ip}", "what": what, "address": ip,
                         "state": "at_budget", "action": {"label": "Read the in-flight panel: it names the operation holding the device, its step and its age (a session held long may be stuck)"},
                         "max_age_minutes": 0,
                         "detail": f"holds {h['held']} of {h['budget']} allowed "
                                   f"({h['lines']} vty lines, one kept for a person): "
                                   f"{owners}. The next operation on it is refused."})
        leaked = [s for s in h["sessions"]
                  if not s["pooled"] and s["age_s"] > LEAK_AFTER_SECONDS]
        if leaked:
            rows.append({"unit": f"ssh-leak:{ip}", "what": what, "address": ip,
                         "state": "leaked", "action": {"label": "Read the in-flight panel: it names the operation holding the device, its step and its age (a session held long may be stuck)"},
                         "max_age_minutes": 0,
                         "detail": "an operation's session held past ten minutes: "
                                   + ", ".join(f"{s['owner']} ({s['age_s']}s)"
                                               for s in leaked)})
    if not rows:
        total = sum(h["held"] for h in held.values())
        rows.append({"unit": "ssh-sessions", "what": what, "state": "ok",
                     "max_age_minutes": 0,
                     "detail": (f"holds {total} session(s) across {len(held)} device(s), "
                                "none at its budget" if total else
                                "holds no SSH session now")})
    return rows


def version_rows(loaded=None, checkout=None) -> list:
    """Is the RUNNING process the checkout's commit? (the operator, 2026-09-27)

    `nmas-deploy` over SSH fast-forwarded the checkout and could not restart
    (sudo needs a password), so the service ran 912e3f1 against a 413f90b
    checkout. A mixed version: this code imports modules inside functions, so
    anything not yet loaded would come from the new commit beside old callers.
    It surfaced only because the tool running the deploy said so; the exit
    code told nobody. *loaded*: what this process imported
    (`routes.health`); *checkout*: the checkout's HEAD now."""
    import subprocess as _sp

    what = "the running process is the checkout's commit (a mixed version is named)"
    try:
        if loaded is None:
            from routes import health as _h
            loaded = _h._COMMIT
        if checkout is None:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            out = _sp.run(["git", "-C", root, "rev-parse", "HEAD"],
                          capture_output=True, text=True, timeout=5)
            checkout = out.stdout.strip() if out.returncode == 0 else None
    except Exception as exc:                          # noqa: BLE001
        return [{"unit": "running-version", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": f"could not compare: {type(exc).__name__}: {exc} "
                           "-- not the same as ok"}]
    if not loaded or not checkout:
        return [{"unit": "running-version", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": ("the loaded commit is unknown" if not loaded else
                            "the checkout's HEAD could not be read")
                           + " -- not the same as ok"}]
    if loaded != checkout:
        return [{"unit": "running-version", "what": what, "state": "mixed_version",
                 "max_age_minutes": 0,
                 "action": {"label": "Restart the service so it runs the checkout's commit "
                                     "(a person's step: CI gates what deploys, the operator "
                                     "when)",
                            "command": "sudo systemctl restart flask-app.service"},
                 "detail": (f"MIXED VERSION: checkout at {checkout[:10]}, service running "
                            f"{loaded[:10]}. Run `sudo systemctl restart flask-app.service` "
                            "(or nmas-deploy in a terminal on the host).")}]
    return [{"unit": "running-version", "what": what, "state": "ok", "max_age_minutes": 0,
             "detail": f"running {loaded[:10]}, the checkout's commit"}]


def ztp_rows() -> list:
    """D4, checked where it could otherwise silently stop holding (P.6)."""
    from modules.nsot import ztp

    try:
        return ztp.posture_rows()
    except Exception as exc:                       # noqa: BLE001
        return [{"unit": "ztp-posture", "state": "unknown", "max_age_minutes": 0,
                 "what": "D4: a ZTP reservation gets no route or resolver",
                 "detail": f"the check raised {type(exc).__name__}: {exc}"}]


def reader_rows() -> list:
    """Each reader job's liveness (modules/reader_job.py, rule 7). A reader
    whose store cannot be judged is one `unknown` row, never no row."""
    try:
        from modules import reader_job
        return reader_job.health_rows()
    except Exception as exc:                            # noqa: BLE001
        return [{"unit": "reader:*", "what": "the reader jobs' liveness",
                 "state": "unknown", "max_age_minutes": 0,
                 "detail": f"the readers could not be judged: {type(exc).__name__}: {exc}"}]


def monitoring_rows() -> list:
    """Each device not configured for an integration the network uses
    (`modules.monitoring_coverage`); none while nothing is expected."""
    try:
        from modules import monitoring_coverage
        return monitoring_coverage.rows()
    except Exception as exc:                            # noqa: BLE001
        return [{"unit": "monitoring:*", "state": "unknown", "max_age_minutes": 0,
                 "what": "every device is configured for the integrations the network uses",
                 "detail": f"the check raised {type(exc).__name__}: {exc} -- not the same as covered"}]


def updater_rows() -> list:
    """The Update button's root-owned updater: installed, root-owned, not
    writable by the service user, the path unit watching (`modules.update_op`)."""
    try:
        from modules import update_op
        return update_op.install_rows()
    except Exception as exc:                            # noqa: BLE001
        return [{"unit": "updater", "state": "unknown", "max_age_minutes": 0,
                 "what": "the Update button's root-owned updater is installed",
                 "detail": f"the check raised {type(exc).__name__}: {exc}"}]


def prometheus_target_rows() -> list:
    """Does the running Prometheus scrape the inventory, labelled (C232)?
    `modules.prometheus_targets` owns the comparison; no row while Prometheus
    is not configured."""
    try:
        from modules import prometheus_targets
        return prometheus_targets.health_rows()
    except Exception as exc:                            # noqa: BLE001
        return [{"unit": "prometheus-targets", "state": "unknown", "max_age_minutes": 0,
                 "what": "Prometheus scrapes the inventory, labelled device and role",
                 "detail": f"the check raised {type(exc).__name__}: {exc}"}]


def health(now: float = None, run=None, images=None, settings=None,
           rotations=None, owner=None, ztp=None, responder=None,
           startup=None, sessions=None, version=None, readers=None,
           breakglass=None, prometheus=None, monitoring=None, updater=None) -> dict:
    """*images*: the image rows, for a caller that has them; by default they
    are read from Proxmox. *settings*, *rotations*, *owner*: likewise."""
    jobs = [job_status(j, now, run) for j in JOBS]
    jobs += image_jobs(now) if images is None else list(images)
    jobs += settings_rows() if settings is None else list(settings)
    jobs += rotation_rows() if rotations is None else list(rotations)
    if rotations is None:
        jobs += staged_rotation_rows()
    jobs += sync_owner_rows(run) if owner is None else list(owner)
    jobs += ztp_rows() if ztp is None else list(ztp)
    jobs += ztp_responder_rows(run) if responder is None else list(responder)
    jobs += startup_rows() if startup is None else list(startup)
    jobs += ssh_session_rows() if sessions is None else list(sessions)
    jobs += version_rows() if version is None else list(version)
    jobs += reader_rows() if readers is None else list(readers)
    jobs += breakglass_rows() if breakglass is None else list(breakglass)
    jobs += prometheus_target_rows() if prometheus is None else list(prometheus)
    jobs += monitoring_rows() if monitoring is None else list(monitoring)
    jobs += updater_rows() if updater is None else list(updater)
    bad = [j["unit"] for j in jobs if j["state"] not in OK_STATES]
    na = sum(1 for j in jobs if j["state"] == "not_applicable")
    gone = sum(1 for j in jobs if j["state"] == "departed")
    return {"ok": True, "jobs": jobs, "not_ok": bad,
            "headline": (f"{len(jobs) - len(bad)} of {len(jobs)} job(s) ok"
                         + (f" ({na} of them declared not applicable)" if na else "")
                         + (f" ({gone} about a device that has left management)" if gone else "")
                         + (f"; not ok: {', '.join(bad)}" if bad else ""))}
