"""A failing timer must be visible (modules/job_health.py). The shapes below
are what systemd and the journal return, measured on the NMAS host."""

import pytest

from modules import job_health as J

NOW = 1790370000.0
JOB = {"unit": "clab-sync", "max_age_minutes": 90, "what": "sync"}


def _runner(show: str, journal: str, show_rc=0, journal_rc=0):
    def run(cmd):
        if cmd[0] == "systemctl":
            return show_rc, show
        return journal_rc, journal
    return run


LOADED = "LoadState=loaded\nActiveState=failed\nResult=exit-code\nExecMainStatus=2\n"


def _line(ts, text):
    return f"{ts:.6f} nmas {text}"


def _fail(ts, why="REFUSED - the NMAS could not be asked where configs belong."):
    return "\n".join([
        _line(ts - 2, "systemd[1]: Starting clab-sync.service - Sync Oxidized configs..."),
        _line(ts - 1, "clab-sync[1]: ./oxidized-to-config.sh: line 137: nmas-clab-targets: command not found"),
        _line(ts - 0.5, f"clab-sync[1]: {why}"),
        _line(ts - 0.4, "clab-sync[1]: config boots from writes one device's credentials into another lab."),
        _line(ts, "systemd[1]: clab-sync.service: Main process exited, code=exited, status=2/INVALIDARGUMENT"),
        _line(ts, "systemd[1]: clab-sync.service: Failed with result 'exit-code'."),
    ])


def _ok(ts):
    return _line(ts, "systemd[1]: clab-sync.service: Deactivated successfully.")


def test_the_measured_shape_is_failing_with_its_own_reason():
    """The live state: one success, then 72 failures every 30 minutes."""
    journal = "\n".join([_ok(NOW - 73 * 1800)] +
                        [_fail(NOW - k * 1800) for k in range(72, 0, -1)])
    s = J.job_status(JOB, NOW, _runner(LOADED, journal))
    assert s["state"] == "failing"
    assert s["consecutive_failures"] == 72
    # The CAUSE, which comes first; not the refusal's continuation line.
    assert s["last_error"].endswith("nmas-clab-targets: command not found"), s["last_error"]


def test_a_unit_that_does_not_exist_is_never_ok():
    """Measured: systemd reports Result=success for a not-found unit."""
    show = "LoadState=not-found\nActiveState=inactive\nResult=success\nExecMainStatus=0\n"
    s = J.job_status(JOB, NOW, _runner(show, ""))
    assert s["state"] == "not_installed" and "Result=success" in s["detail"]


def test_quiet_and_old_is_stale_not_ok():
    s = J.job_status(JOB, NOW, _runner(LOADED, _ok(NOW - 5 * 3600)))
    assert s["state"] == "stale"


def test_recent_success_is_ok():
    s = J.job_status(JOB, NOW, _runner(LOADED, _ok(NOW - 600)))
    assert s["state"] == "ok" and s["consecutive_failures"] == 0


def test_failures_and_no_success_is_never_succeeded():
    s = J.job_status(JOB, NOW, _runner(LOADED, _fail(NOW - 60)))
    assert s["state"] == "never_succeeded"


@pytest.mark.parametrize("show_rc,journal_rc", [(1, 0), (0, 1)])
def test_could_not_ask_is_unknown_not_ok(show_rc, journal_rc):
    s = J.job_status(JOB, NOW, _runner(LOADED, _ok(NOW - 60), show_rc, journal_rc))
    assert s["state"] == "unknown"


def test_a_recovery_clears_the_streak():
    journal = "\n".join([_fail(NOW - 1200), _fail(NOW - 900), _ok(NOW - 300)])
    s = J.job_status(JOB, NOW, _runner(LOADED, journal))
    assert s["state"] == "ok" and s["last_error"] == ""


def test_the_headline_counts_and_names():
    journal = _ok(NOW - 60)
    # images=[]: this test is about the systemd jobs' count; the Proxmox
    # image rows have their own tests below.
    h = J.health(NOW, _runner(LOADED, journal), images=[])
    assert h["headline"] == f"{len(J.JOBS)} of {len(J.JOBS)} job(s) ok"
    h = J.health(NOW, _runner(LOADED, _fail(NOW - 60)), images=[])
    assert h["headline"].startswith("0 of") and "clab-sync" in h["headline"]


def test_the_route_reports_rather_than_withholds(monkeypatch):
    import app as nmas
    monkeypatch.setattr(J, "_run", _runner(LOADED, _fail(NOW - 60)))
    body = nmas.app.test_client().get("/jobs/health").get_json()
    assert body["ok"] is True and "clab-sync" in body["not_ok"]
    # The STATE, not just "not ok": a route asking the real systemd of a
    # machine without the unit would say not_installed and also be "not ok".
    clab = next(j for j in body["jobs"] if j["unit"] == "clab-sync")
    assert clab["state"] == "never_succeeded", clab



# ---------------------------------------------------------------------------
# The nightly VM images (B6): read from Proxmox, judged like the jobs above
# ---------------------------------------------------------------------------

HOUR = 3600
GIB = 1024 ** 3


def _vm_log(vmid, size="8.12GB", froze=True, ok=True, error="unable to connect"):
    """Lines in the shape the live host's vzdump task logs have
    (2026-09-25), trimmed to the ones the parser reads."""
    lines = [f"INFO: Starting Backup of VM {vmid} (qemu)",
             f"INFO: creating vzdump archive '/mnt/vzdump/dump/vzdump-qemu-{vmid}-2026_09_25-17_46_38.vma.zst'"]
    if froze:
        lines += ["INFO: issuing guest-agent 'fs-freeze' command",
                  "INFO: issuing guest-agent 'fs-thaw' command"]
    if ok:
        lines += [f"INFO: archive file size: {size}", f"INFO: Finished Backup of VM {vmid} (00:07:35)"]
    else:
        lines += [f"ERROR: Backup of VM {vmid} failed - {error}"]
    return lines


class FakeProxmox:
    """Answers the reads with the live host's shapes. The backup LISTING is
    empty by default, because that is what an auditor token gets (measured).
    Each read can fail independently: a failed read must never come out ok."""

    def __init__(self, *, tasks=None, logs=None, listing=(), storage=None, pools=None,
                 missing=(), vmids=(100, 102)):
        self._missing, self._vmids = list(missing), list(vmids)
        self.storage = "vzdump-sda"
        # Default: the manual run measured live -- one task per VM, each with its id.
        self._tasks = tasks if tasks is not None else [
            {"upid": "U100", "id": "100", "starttime": NOW - 7 * HOUR,
             "endtime": NOW - 6 * HOUR, "status": "OK"},
            {"upid": "U102", "id": "102", "starttime": NOW - 8 * HOUR,
             "endtime": NOW - 7 * HOUR, "status": "OK"}]
        self._logs = logs if logs is not None else {
            "U100": _vm_log(100, "25.21GB"), "U102": _vm_log(102, "8.12GB")}
        self._listing = list(listing)
        self._storage = storage if storage is not None else {
            "active": 1, "avail": 114 * GIB, "used": 34 * GIB}
        self._pools = pools if pools is not None else [
            {"vg": "pve", "lv": "data", "lv_size": 348 * GIB, "used": 0.11,
             "metadata_size": GIB, "metadata_used": 0.01}]

    def missing_settings(self):
        return self._missing

    def vmids(self):
        return self._vmids

    @staticmethod
    def _wrap(value):
        return {"ok": False, "error": value.args[0]} if isinstance(value, Exception) \
            else {"ok": True, "data": value}

    def vzdump_tasks(self):
        return self._wrap(self._tasks)

    def task_log(self, upid):
        return self._wrap(self._logs.get(upid, RuntimeError(f"no log for {upid}")))

    def backups(self):
        return self._wrap(self._listing)

    def storage_status(self):
        return self._wrap(self._storage)

    def thin_pools(self):
        return self._wrap(self._pools)


def _rows(client):
    return {r["unit"]: r for r in J.image_jobs(NOW, client)}


class TestTheLogIsParsedPerVm:

    def test_a_job_over_two_vms_is_split_at_each_start_line(self):
        facts = J.parse_vzdump_log(_vm_log(100, "25.21GB") + _vm_log(102, ok=False))
        assert facts[100]["ok"] is True and facts[102]["ok"] is False
        assert "unable to connect" in facts[102]["error"]

    def test_pves_gb_is_gib(self):
        """25.21 "GB" is 26G in `ls -h` on the live host; decimal would be 24."""
        assert J.parse_vzdump_log(_vm_log(100, "25.21GB"))[100]["size"] == int(25.21 * GIB)

    def test_a_run_without_the_freeze_says_so(self):
        assert J.parse_vzdump_log(_vm_log(102, froze=False))[102]["froze"] is False


class TestTheImagesAreWatched:

    def test_the_live_night_is_ok_everywhere_with_its_numbers(self):
        """The host's measured state: two per-VM tasks, an EMPTY listing,
        34 GiB used, 114 GiB free, pve/data at 11% and 1%."""
        rows = _rows(FakeProxmox())
        assert {u: r["state"] for u, r in rows.items()} == {
            "vm-image:100": "ok", "vm-image:102": "ok",
            "vm-images-storage:vzdump-sda": "ok", "thin-pools": "ok"}
        assert "25.2 GiB" in rows["vm-image:100"]["detail"]
        assert "froze the filesystem: yes" in rows["vm-image:100"]["detail"]
        assert "cannot list the images" in rows["vm-image:100"]["detail"]
        assert "114.0 GiB free" in rows["vm-images-storage:vzdump-sda"]["detail"]

    def test_the_empty_listing_no_longer_reads_as_never(self):
        """The live defect: `never` for a VM that HAS an image, because the
        auditor's listing is empty. The listing is now only a presence check."""
        assert _rows(FakeProxmox(listing=[]))["vm-image:102"]["state"] == "ok"

    def test_unconfigured_is_never_ok_and_names_what_is_missing(self):
        rows = J.image_jobs(NOW, FakeProxmox(missing=["proxmox_token_secret"]))
        assert [r["state"] for r in rows] == ["not_configured"]
        assert "proxmox_token_secret" in rows[0]["detail"]

    def test_a_job_that_stopped_is_stale_though_nothing_failed(self):
        old = [{"upid": "U100", "id": "", "starttime": NOW - 51 * HOUR,
                "endtime": NOW - 50 * HOUR, "status": "OK"}]
        logs = {"U100": _vm_log(100) + _vm_log(102)}
        rows = _rows(FakeProxmox(tasks=old, logs=logs))
        assert rows["vm-image:100"]["state"] == "stale"
        assert "nothing has succeeded since" in rows["vm-image:100"]["detail"]

    def test_one_vm_failing_in_a_shared_job_does_not_condemn_the_other(self):
        job = [{"upid": "J", "id": "", "starttime": NOW - HOUR,
                "endtime": NOW - 40 * 60, "status": "job errors"}]
        logs = {"J": _vm_log(100, "25.21GB") + _vm_log(102, ok=False, error="guest agent timeout")}
        rows = _rows(FakeProxmox(tasks=job, logs=logs))
        assert rows["vm-image:100"]["state"] == "ok"
        assert rows["vm-image:102"]["state"] == "failing"
        assert "guest agent timeout" in rows["vm-image:102"]["detail"]

    def test_no_task_mentions_the_vm_is_never(self):
        rows = _rows(FakeProxmox(logs={"U100": _vm_log(100), "U102": _vm_log(100)}))
        assert rows["vm-image:102"]["state"] == "never"

    def test_an_unreadable_log_is_unknown_not_never(self):
        rows = _rows(FakeProxmox(logs={"U100": _vm_log(100)}))
        assert rows["vm-image:102"]["state"] == "unknown"
        assert "unreadable" in rows["vm-image:102"]["detail"]

    def test_listed_but_not_this_archive_is_missing(self):
        """With a token that CAN list, a written archive absent from the
        listing is reported, not assumed present."""
        listing = [{"volid": "vzdump-sda:backup/vzdump-qemu-100-2026_09_25-17_46_38.vma.zst"}]
        rows = _rows(FakeProxmox(listing=listing, logs={
            "U100": _vm_log(100), "U102": [l.replace("-102-2026", "-102-2025") for l in _vm_log(102)]}))
        assert rows["vm-image:100"]["state"] == "ok"
        assert rows["vm-image:102"]["state"] == "missing"

    def test_a_read_that_failed_is_unknown_never_ok(self):
        rows = _rows(FakeProxmox(tasks=RuntimeError("HTTP 403"),
                                 storage=RuntimeError("HTTP 403"),
                                 pools=RuntimeError("HTTP 403")))
        assert {r["state"] for r in rows.values()} == {"unknown"}
        assert all("not the same as ok" in r["detail"] for r in rows.values())


class TestFillingIsAboutTheNextRun:

    def test_will_not_fit_below_one_point_two_times_the_largest_image(self):
        # largest is 25.21 GiB -> needs 30.25 GiB
        row = _rows(FakeProxmox(storage={"active": 1, "avail": 30 * GIB, "used": 34 * GIB}))[
            "vm-images-storage:vzdump-sda"]
        assert row["state"] == "will_not_fit" and "writes before it prunes" in row["detail"]

    def test_just_enough_room_fits(self):
        row = _rows(FakeProxmox(storage={"active": 1, "avail": 31 * GIB, "used": 34 * GIB}))[
            "vm-images-storage:vzdump-sda"]
        assert row["state"] == "ok"

    def test_a_percentage_does_not_decide_it(self):
        row = _rows(FakeProxmox(storage={"active": 1, "avail": 40 * GIB,
                                         "total": 400 * GIB, "used": 360 * GIB}))[
            "vm-images-storage:vzdump-sda"]
        assert row["state"] == "ok"

    def test_less_used_than_the_newest_images_is_images_missing(self):
        """The check that stands in for the listing an auditor cannot read."""
        row = _rows(FakeProxmox(storage={"active": 1, "avail": 140 * GIB, "used": 9 * GIB}))[
            "vm-images-storage:vzdump-sda"]
        assert row["state"] == "images_missing"

    def test_an_unmounted_destination_is_inactive(self):
        row = _rows(FakeProxmox(storage={"active": 0, "avail": 0}))[
            "vm-images-storage:vzdump-sda"]
        assert row["state"] == "inactive" and "not mounted" in row["detail"]

    def test_no_archive_size_yet_is_unsized_not_ok(self):
        row = _rows(FakeProxmox(tasks=[]))["vm-images-storage:vzdump-sda"]
        assert row["state"] == "unsized"

    def test_a_pool_whose_metadata_fills_is_reported(self):
        pools = [{"vg": "pve", "lv": "data", "lv_size": 348 * GIB, "used": 40 * GIB,
                  "metadata_size": GIB, "metadata_used": 0.85 * GIB}]
        row = _rows(FakeProxmox(pools=pools))["thin-pools"]
        assert row["state"] == "pool_filling" and "metadata 85%" in row["detail"]

    def test_the_live_pool_figures_read_as_measured(self):
        row = _rows(FakeProxmox())["thin-pools"]
        assert row["detail"] == "pve/data data 11%, metadata 1%"


def test_health_carries_the_image_rows_in_its_headline():
    h = J.health(NOW, _runner(LOADED, _ok(NOW - 60)),
                 images=J.image_jobs(NOW, FakeProxmox(storage={"active": 0})))
    assert "vm-images-storage:vzdump-sda" in h["not_ok"]
