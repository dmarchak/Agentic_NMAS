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
G = 10 ** 9


class FakeProxmox:
    """Answers the four reads with fixtures shaped like the Proxmox API's
    `data` payloads. Each can be made to fail independently, because a read
    that failed must never come out as ok."""

    def __init__(self, *, backups=None, tasks=None, storage=None, pools=None,
                 missing=(), vmids=(100, 102)):
        self._missing, self._vmids = list(missing), list(vmids)
        self.storage = "vzdump-sda"
        self._backups = backups if backups is not None else [
            {"vmid": 100, "ctime": NOW - 6 * HOUR, "size": 11 * G},
            {"vmid": 102, "ctime": NOW - 6 * HOUR, "size": 14 * G},
            {"vmid": 102, "ctime": NOW - 30 * HOUR, "size": 13 * G}]
        self._tasks = tasks if tasks is not None else [
            {"id": "", "starttime": NOW - 7 * HOUR, "endtime": NOW - 6 * HOUR, "status": "OK"}]
        self._storage = storage if storage is not None else {"active": 1, "avail": 100 * G}
        self._pools = pools if pools is not None else [
            {"vg": "pve", "lv": "data", "lv_size": 348 * G, "used": 40 * G,
             "metadata_size": G, "metadata_used": G // 20}]

    def missing_settings(self):
        return self._missing

    def vmids(self):
        return self._vmids

    @staticmethod
    def _wrap(value):
        return {"ok": False, "error": value.args[0]} if isinstance(value, Exception) \
            else {"ok": True, "data": value}

    def backups(self):
        return self._wrap(self._backups)

    def vzdump_tasks(self):
        return self._wrap(self._tasks)

    def storage_status(self):
        return self._wrap(self._storage)

    def thin_pools(self):
        return self._wrap(self._pools)


def _rows(client):
    return {r["unit"]: r for r in J.image_jobs(NOW, client)}


class TestTheImagesAreWatched:

    def test_a_healthy_night_is_ok_everywhere_with_its_numbers(self):
        rows = _rows(FakeProxmox())
        assert {u: r["state"] for u, r in rows.items()} == {
            "vm-image:100": "ok", "vm-image:102": "ok",
            "vm-images-storage:vzdump-sda": "ok", "thin-pools": "ok"}
        assert "14.0 G" in rows["vm-image:102"]["detail"]     # the NEWEST, not the older

    def test_unconfigured_is_never_ok_and_names_what_is_missing(self):
        rows = J.image_jobs(NOW, FakeProxmox(missing=["proxmox_token_secret"]))
        assert [r["state"] for r in rows] == ["not_configured"]
        assert "proxmox_token_secret" in rows[0]["detail"]
        assert "not the same as ok" in rows[0]["detail"]

    def test_a_job_that_stopped_is_stale_though_nothing_failed(self):
        """What a notification cannot report: the job did not run at all."""
        old = [{"vmid": v, "ctime": NOW - 50 * HOUR, "size": 12 * G} for v in (100, 102)]
        rows = _rows(FakeProxmox(backups=old, tasks=[]))
        assert rows["vm-image:100"]["state"] == "stale"
        assert "nothing has succeeded since" in rows["vm-image:100"]["detail"]

    def test_a_failed_run_is_failing_with_its_own_status_line(self):
        tasks = [{"id": "", "starttime": NOW - HOUR, "endtime": NOW - HOUR + 60,
                  "status": "job errors"}]
        rows = _rows(FakeProxmox(tasks=tasks))
        assert rows["vm-image:100"]["state"] == "failing"
        assert "job errors" in rows["vm-image:100"]["detail"]

    def test_a_vm_whose_image_is_newer_than_the_failed_task_is_not_failing(self):
        """A multi-VM job fails as one task; the VM that succeeded in it
        must not be reported as failing."""
        backups = [{"vmid": 100, "ctime": NOW - 30 * 60, "size": 11 * G},
                   {"vmid": 102, "ctime": NOW - 30 * HOUR, "size": 14 * G}]
        tasks = [{"id": "", "starttime": NOW - HOUR, "endtime": NOW - 20 * 60,
                  "status": "job errors"}]
        rows = _rows(FakeProxmox(backups=backups, tasks=tasks))
        assert rows["vm-image:100"]["state"] == "ok"
        assert rows["vm-image:102"]["state"] == "failing"

    def test_warnings_are_named_and_not_a_failure(self):
        tasks = [{"id": "", "starttime": NOW - 7 * HOUR, "endtime": NOW - 6 * HOUR,
                  "status": "WARNINGS: 1"}]
        row = _rows(FakeProxmox(tasks=tasks))["vm-image:102"]
        assert row["state"] == "ok" and "WARNINGS: 1" in row["detail"]

    def test_no_image_at_all_is_never(self):
        rows = _rows(FakeProxmox(backups=[{"vmid": 100, "ctime": NOW - HOUR, "size": G}]))
        assert rows["vm-image:102"]["state"] == "never"

    def test_a_read_that_failed_is_unknown_never_ok(self):
        rows = _rows(FakeProxmox(backups=RuntimeError("HTTP 403"),
                                 storage=RuntimeError("HTTP 403"),
                                 pools=RuntimeError("HTTP 403")))
        assert {r["state"] for r in rows.values()} == {"unknown"}
        assert all("not the same as ok" in r["detail"] for r in rows.values())


class TestFillingIsAboutTheNextRun:

    def test_will_not_fit_below_one_point_two_times_the_largest_image(self):
        # largest newest image is 14 G -> needs 16.8 G
        row = _rows(FakeProxmox(storage={"active": 1, "avail": 16 * G}))[
            "vm-images-storage:vzdump-sda"]
        assert row["state"] == "will_not_fit"
        assert "16.8 G" in row["detail"] and "writes before it prunes" in row["detail"]

    def test_just_enough_room_fits(self):
        row = _rows(FakeProxmox(storage={"active": 1, "avail": 17 * G}))[
            "vm-images-storage:vzdump-sda"]
        assert row["state"] == "ok"

    def test_a_percentage_does_not_decide_it(self):
        """90% used with plenty free for these images is fine."""
        row = _rows(FakeProxmox(storage={"active": 1, "avail": 40 * G,
                                         "total": 400 * G, "used": 360 * G}))[
            "vm-images-storage:vzdump-sda"]
        assert row["state"] == "ok"

    def test_an_unmounted_destination_is_inactive(self):
        row = _rows(FakeProxmox(storage={"active": 0, "avail": 0}))[
            "vm-images-storage:vzdump-sda"]
        assert row["state"] == "inactive" and "not mounted" in row["detail"]

    def test_no_image_yet_is_unsized_not_ok(self):
        row = _rows(FakeProxmox(backups=[]))["vm-images-storage:vzdump-sda"]
        assert row["state"] == "unsized"

    def test_a_pool_whose_metadata_fills_is_reported(self):
        pools = [{"vg": "pve", "lv": "data", "lv_size": 348 * G, "used": 40 * G,
                  "metadata_size": G, "metadata_used": 0.85 * G}]
        row = _rows(FakeProxmox(pools=pools))["thin-pools"]
        assert row["state"] == "pool_filling" and "metadata 85%" in row["detail"]

    def test_a_pool_reported_as_a_fraction_is_read_as_one(self):
        pools = [{"vg": "pve", "lv": "data", "used": 0.9, "metadata_used": 0.1}]
        row = _rows(FakeProxmox(pools=pools))["thin-pools"]
        assert row["state"] == "pool_filling" and "data 90%" in row["detail"]


def test_health_carries_the_image_rows_in_its_headline():
    h = J.health(NOW, _runner(LOADED, _ok(NOW - 60)),
                 images=J.image_jobs(NOW, FakeProxmox(storage={"active": 0})))
    assert "vm-images-storage:vzdump-sda" in h["not_ok"]
