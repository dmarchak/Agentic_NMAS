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


def _gb(n) -> str:
    return f"{(n or 0) / 1e9:.1f} G"


def _age(now, ts) -> str:
    minutes = int((now - ts) // 60)
    return f"{minutes // 60} h {minutes % 60} min ago" if minutes >= 60 else f"{minutes} min ago"


def _fraction(used, size):
    """The API reports some pool figures as bytes and some as a 0..1
    fraction (not yet measured on this host's version), so both are read."""
    try:
        used, size = float(used), float(size or 0)
    except (TypeError, ValueError):
        return None
    if 0 <= used <= 1:
        return used
    return used / size if size > 0 else None


def image_jobs(now: float = None, client=None) -> list:
    """One row per imaged VM, one for the destination, one for the thin pools.

    Every read that fails is ``unknown`` (not the same as ok), and an
    unconfigured Proxmox is ``not_configured``, never ok: a job NMAS depends
    on and cannot see is the failure this module exists to catch.
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

    rows = []
    backups = client.backups()
    tasks = client.vzdump_tasks()
    finished = sorted((t for t in (tasks.get("data") or []) if t.get("endtime")),
                      key=lambda t: t.get("starttime") or 0, reverse=True)
    newest_sizes = []
    for vmid in vmids:
        unit = f"vm-image:{vmid}"
        if not backups["ok"]:
            rows.append(row(unit, "unknown",
                            f"could not list the backups on {storage}: {backups['error']} "
                            f"-- not the same as ok"))
            continue
        images = [b for b in backups["data"] or []
                  if str(b.get("vmid", "")) == str(vmid) and b.get("ctime")]
        newest = max(images, key=lambda b: b["ctime"]) if images else None
        if newest:
            newest_sizes.append(newest.get("size") or 0)
        # A backup job covering several VMs is one task with an empty id; a
        # single-VM run carries the VM's id.
        task = next((t for t in finished if str(t.get("id") or "") in ("", str(vmid))), None)
        status = str(task.get("status", "")) if task else ""
        task_failed = bool(task) and status != "OK" and not status.startswith("WARNINGS")
        notes = []
        if not tasks["ok"]:
            notes.append(f"vzdump tasks unreadable ({tasks['error']}), so a failure "
                         f"is judged by image age alone")
        elif status.startswith("WARNINGS"):
            notes.append(f"latest vzdump task finished with {status}")

        if task_failed and (newest is None or newest["ctime"] < task.get("starttime", 0)):
            state = "failing"
            detail = (f"latest vzdump task failed {_age(now, task['endtime'])}: {status}; "
                      + (f"newest image {_age(now, newest['ctime'])}" if newest else "no image at all"))
        elif newest is None:
            state, detail = "never", f"no image of VM {vmid} on {storage}"
        elif now - newest["ctime"] > IMAGE_MAX_AGE_MINUTES * 60:
            state = "stale"
            detail = (f"newest image {_age(now, newest['ctime'])} ({_gb(newest.get('size'))}); "
                      f"nothing failed, and nothing has succeeded since")
        else:
            state = "ok"
            detail = f"newest image {_age(now, newest['ctime'])} ({_gb(newest.get('size'))})"
        rows.append(row(unit, state, "; ".join([detail] + notes),
                        last_success=newest["ctime"] if newest else None))

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
                        f"{_gb(st['data'].get('avail'))} free, and no image yet to size "
                        f"the next run against"))
    else:
        avail = st["data"].get("avail") or 0
        largest = max(newest_sizes)
        need = largest * FIT_FACTOR
        if avail < need:
            rows.append(row(unit, "will_not_fit",
                            f"{_gb(avail)} free < {_gb(need)} ({FIT_FACTOR} x the largest "
                            f"image, {_gb(largest)}). vzdump writes before it prunes, so the "
                            f"next run will not fit beside the kept images"))
        else:
            rows.append(row(unit, "ok", f"{_gb(avail)} free; the largest image "
                                        f"({_gb(largest)}) fits with {_gb(avail - need)} to spare"))

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
