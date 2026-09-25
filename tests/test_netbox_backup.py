"""NSOT_PLAN P.2: NetBox backup and restore test.

Docker is never reached: `dump_database`, the media `_run` and
`restore_and_count` are the seams, and everything else -- the partial
directory, hashing, config copying and its modes, retention, status, the
restore comparison -- runs for real against a temp directory.
"""

import datetime
import importlib.machinery
import importlib.util
import json
import os
import stat

import pytest


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


B = _load("backup_under_test", "scripts/nmas-netbox-backup")
R = _load("restore_under_test", "scripts/nmas-netbox-restore-test")

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 9, 25, 12, 0, 0, tzinfo=UTC)


def _name(hours_ago=0, days_ago=0):
    return B._ts(NOW - datetime.timedelta(hours=hours_ago, days=days_ago))


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

class TestRetention:
    def test_old_hourlies_and_dailies_expire(self):
        hourly = [_name(h) for h in (0, 5, 25, 27, 40)]
        daily = [_name(days_ago=d) for d in (0, 3, 14, 16, 30)]
        plan = B.retention_plan(hourly, daily, NOW)
        assert sorted(plan["hourly"]) == sorted([_name(27), _name(40)])
        assert sorted(plan["daily"]) == sorted(
            [_name(days_ago=16), _name(days_ago=30)])

    def test_the_newest_is_kept_however_old(self):
        """A timer that stopped must not prune the last backup there is."""
        plan = B.retention_plan([_name(days_ago=40)], [_name(days_ago=90)],
                                NOW)
        assert plan == {"hourly": [], "daily": []}

    def test_names_it_did_not_make_are_never_deleted(self):
        plan = B.retention_plan(["notes", _name(0), _name(40) + ".partial"],
                                [], NOW)
        assert plan["hourly"] == []

    def test_first_backup_of_a_day_becomes_the_daily(self):
        assert B.needs_daily(_name(0), [])
        assert not B.needs_daily(_name(0), [_name(1)])
        assert B.needs_daily(_name(0), [_name(days_ago=1)])


# ---------------------------------------------------------------------------
# Taking a backup
# ---------------------------------------------------------------------------

@pytest.fixture
def compose(tmp_path):
    d = tmp_path / "netbox-docker"
    (d / "env").mkdir(parents=True)
    (d / "configuration").mkdir()
    env = d / "env" / "netbox.env"
    env.write_text("SECRET_KEY=abc\nAPI_TOKEN_PEPPER_1=def\nDB_HOST=pg\n")
    env.chmod(0o664)  # OPEN_FINDINGS B4: what the originals were
    (d / "configuration" / "configuration.py").write_text("X = 1\n")
    (d / "docker-compose.yml").write_text("services: {}\n")
    return d


@pytest.fixture
def cfg(tmp_path, compose):
    c = B.config_from_env({})
    c.update(root=str(tmp_path / "root"), compose_dir=str(compose))
    return c


def _fake_dump(counts=None):
    def dump(cfg, out_path):
        with open(out_path, "wb") as fh:
            fh.write(b"PGDMP fake")
        return {"snapshot": "0-1", "server_version": "18.6",
                "row_counts": counts or {"dcim_device": 10, "ipam_prefix": 33},
                "postgres_user": "netbox", "postgres_db": "netbox"}
    return dump


def _fake_run(cmd, **kw):
    if kw.get("stdout") is not None and hasattr(kw["stdout"], "write"):
        kw["stdout"].write(b"tar bytes")
    class P:  # noqa: D401
        stdout = "img:1"
        returncode = 0
    return P()


class TestTakeBackup:
    def test_a_backup_is_complete_and_its_hashes_verify(self, cfg,
                                                        monkeypatch):
        monkeypatch.setattr(B, "dump_database", _fake_dump())
        monkeypatch.setattr(B, "_run", _fake_run)
        name = B.take_backup(cfg, NOW)
        d = os.path.join(cfg["root"], "hourly", name)
        manifest = json.load(open(os.path.join(d, "manifest.json")))
        assert B.verify_files(d, manifest) == []
        assert {"netbox.pgdump", "media.tar",
                os.path.join("config", "env", "netbox.env")} <= set(
                    manifest["files"])
        assert manifest["row_counts"]["dcim_device"] == 10

    def test_every_file_is_owner_only_whatever_the_original_was(
            self, cfg, monkeypatch):
        monkeypatch.setattr(B, "dump_database", _fake_dump())
        monkeypatch.setattr(B, "_run", _fake_run)
        d = os.path.join(cfg["root"], "hourly", B.take_backup(cfg, NOW))
        modes = {os.path.relpath(os.path.join(b, f), d):
                 stat.S_IMODE(os.stat(os.path.join(b, f)).st_mode)
                 for b, _, fs in os.walk(d) for f in fs}
        assert modes, "floor: files were written"
        assert set(modes.values()) == {0o600}, modes

    def test_a_failure_leaves_nothing_that_looks_like_a_backup(
            self, cfg, monkeypatch):
        def boom(cfg, out_path):
            open(out_path, "wb").write(b"half")
            raise RuntimeError("pg_dump died")
        monkeypatch.setattr(B, "dump_database", boom)
        with pytest.raises(RuntimeError):
            B.take_backup(cfg, NOW)
        assert os.listdir(os.path.join(cfg["root"], "hourly")) == []

    def test_config_without_the_pepper_is_refused(self, cfg, compose,
                                                  monkeypatch):
        (compose / "env" / "netbox.env").write_text("SECRET_KEY=abc\n")
        monkeypatch.setattr(B, "dump_database", _fake_dump())
        monkeypatch.setattr(B, "_run", _fake_run)
        with pytest.raises(RuntimeError, match="API_TOKEN_PEPPER_1"):
            B.take_backup(cfg, NOW)

    def test_promotion_links_rather_than_copies(self, cfg, monkeypatch):
        monkeypatch.setattr(B, "dump_database", _fake_dump())
        monkeypatch.setattr(B, "_run", _fake_run)
        name = B.take_backup(cfg, NOW)
        got = B.promote_and_prune(cfg["root"], name, NOW)
        assert got["promoted"]
        h = os.path.join(cfg["root"], "hourly", name, "netbox.pgdump")
        d = os.path.join(cfg["root"], "daily", name, "netbox.pgdump")
        assert os.path.samefile(h, d)


class TestAFailedBackupIsRecordedNotSilent:
    def test_run_once_records_the_failure_and_exits_nonzero(
            self, cfg, monkeypatch):
        def boom(cfg, out_path):
            raise RuntimeError("pg_dump died")
        monkeypatch.setattr(B, "dump_database", boom)
        assert B.run_once(cfg) == B.EXIT_FAILED
        state = B._read_state(cfg["root"])
        assert "pg_dump died" in state["backup_failure"]["reason"]
        assert "backup_success" not in state

    def test_no_recipient_key_means_nothing_ships_and_it_says_so(
            self, cfg, monkeypatch, capsys):
        monkeypatch.setattr(B, "dump_database", _fake_dump())
        monkeypatch.setattr(B, "_run", _fake_run)
        assert B.run_once(cfg) == B.EXIT_FAILED
        assert "NOT SHIPPED" in capsys.readouterr().err
        assert not os.path.exists(os.path.join(cfg["root"], "outgoing"))


# ---------------------------------------------------------------------------
# Status: never 0 unless everything configured is fresh
# ---------------------------------------------------------------------------

class TestStatus:
    def _cfg(self, **kw):
        c = B.config_from_env({})
        c.update(recipient_file="/k.asc", **kw)
        return c

    def _at(self, hours):
        return {"at": (NOW - datetime.timedelta(hours=hours)).isoformat()}

    def test_no_state_is_unproven_not_ok(self):
        code, lines = B.status_report({}, self._cfg(), NOW)
        assert code == B.EXIT_UNPROVEN and "UNPROVEN" in lines[0]

    def test_fresh_local_and_unconfigured_destinations_are_named(self):
        code, lines = B.status_report({"backup_success": self._at(1)},
                                      self._cfg(), NOW)
        assert code == B.EXIT_OK
        assert sum("NOT CONFIGURED" in l for l in lines) == 2
        assert any("restore test: NEVER RUN" in l for l in lines)

    def test_a_stale_local_backup_fails(self):
        code, lines = B.status_report({"backup_success": self._at(5)},
                                      self._cfg(), NOW)
        assert code == B.EXIT_FAILED and any("STALE" in l for l in lines)

    def test_a_configured_destination_that_never_succeeded_fails(self):
        code, lines = B.status_report(
            {"backup_success": self._at(1),
             "proxmox_failure": {"at": NOW.isoformat(),
                                 "reason": "ssh exited 255"}},
            self._cfg(proxmox_target="u@h"), NOW)
        assert code == B.EXIT_FAILED
        assert any("NEVER SUCCEEDED" in l and "ssh exited 255" in l
                   for l in lines)

    def test_a_failed_restore_test_fails_the_status(self):
        """Measured live: the first version exited 0 beside a FAIL."""
        code, lines = B.status_report(
            {"backup_success": self._at(1),
             "restore_test": {**self._at(1), "result": "FAIL",
                              "detail": "198 table(s) differ"}},
            self._cfg(), NOW)
        assert code == B.EXIT_FAILED
        assert any("restore test: FAIL" in l for l in lines)

    def test_a_passing_but_old_restore_test_fails_the_status(self):
        code, _ = B.status_report(
            {"backup_success": self._at(1),
             "restore_test": {**self._at(60), "result": "PASS"}},
            self._cfg(), NOW)
        assert code == B.EXIT_FAILED

    def test_no_recipient_fails_even_when_local_is_fresh(self):
        c = self._cfg()
        c["recipient_file"] = ""
        code, _ = B.status_report({"backup_success": self._at(1)}, c, NOW)
        assert code == B.EXIT_FAILED


# ---------------------------------------------------------------------------
# Restore test
# ---------------------------------------------------------------------------

@pytest.fixture
def backup(cfg, monkeypatch):
    monkeypatch.setattr(B, "dump_database", _fake_dump())
    monkeypatch.setattr(B, "_run", _fake_run)
    return os.path.join(cfg["root"], "hourly", B.take_backup(cfg, NOW))


class TestRestoreTest:
    def test_identical_counts_pass(self, backup, cfg, monkeypatch):
        monkeypatch.setattr(R, "restore_and_count", lambda m, d: dict(
            m["row_counts"]))
        code, detail = R.run(backup, cfg["root"])
        assert code == B.EXIT_OK and "identical" in detail

    def test_a_lost_row_fails_naming_the_table(self, backup, cfg,
                                               monkeypatch):
        monkeypatch.setattr(R, "restore_and_count",
                            lambda m, d: {**m["row_counts"],
                                          "dcim_device": 9})
        code, detail = R.run(backup, cfg["root"])
        assert code == B.EXIT_FAILED and "dcim_device" in detail

    def test_a_tampered_file_fails_before_any_restore(self, backup, cfg,
                                                      monkeypatch):
        open(os.path.join(backup, "netbox.pgdump"), "ab").write(b"x")
        called = []
        monkeypatch.setattr(R, "restore_and_count",
                            lambda m, d: called.append(1) or {})
        code, detail = R.run(backup, cfg["root"])
        assert code == B.EXIT_FAILED and "hash differs" in detail
        assert called == []

    def test_nothing_to_test_is_unproven(self, cfg):
        assert R.run("", cfg["root"])[0] == B.EXIT_UNPROVEN
        assert R.newest_backup(cfg["root"]) == ""

    def test_the_newest_complete_backup_is_chosen(self, backup, cfg):
        os.makedirs(os.path.join(cfg["root"], "hourly",
                                 _name(-1) + ".partial"))
        assert R.newest_backup(cfg["root"]) == backup


class TestTheScratchQueryReachesPsql:
    """Measured live: the count query was piped to `docker exec` without
    `-i`, so psql read nothing and every table came back None. The mocked
    seam could not see it, so the call's shape is pinned here."""

    def test_every_docker_exec_fed_stdin_has_dash_i(self, monkeypatch):
        calls = []
        def fake(cmd, **kw):
            calls.append((cmd, kw))
            class P:
                stdout = "dcim_device|10\n"
                returncode = 0
            return P()
        # R loads its OWN copy of the backup module, so patch that one.
        monkeypatch.setattr(R.B, "_run", fake)
        monkeypatch.setattr(R.subprocess, "run", lambda *a, **k: type(
            "P", (), {"returncode": 0})())
        monkeypatch.setattr(R.time, "sleep", lambda s: None)
        dump = os.path.join(os.path.dirname(__file__), "..", "README.md")
        if not os.path.exists(dump):
            dump = __file__
        R.restore_and_count({"postgres_user": "u", "postgres_db": "d",
                             "postgres_image": "pg:18"}, dump)
        fed = [c for c, kw in calls
               if c[:2] == ["docker", "exec"] and ("input" in kw
                                                   or "stdin" in kw)]
        assert len(fed) >= 2, "floor: restore and count both feed stdin"
        assert all(c[2] == "-i" for c in fed), fed


class TestCounting:
    def test_parse_and_compare(self):
        got = B.parse_counts(["a|3", "b|0", "junk", "c|x"])
        assert got == {"a": 3, "b": 0}
        assert B.compare_counts({"a": 3, "b": 0}, got) == []
        assert B.compare_counts({"a": 3}, {"a": 3, "z": 1}) == [
            "z: manifest None restored 1"]


class TestOffboxRetentionIsTheBucketsByDefault:
    """Decided 2026-09-25: the off-box key cannot delete; a lifecycle rule
    expires files. The script must not try to delete unless told to."""

    def _calls(self, monkeypatch, env):
        calls = []
        monkeypatch.setattr(B, "_run", lambda cmd, **kw: calls.append(cmd))
        cfg = B.config_from_env({"NMAS_BACKUP_RCLONE_REMOTE": "b2:bucket", **env})
        B.ship_offbox(cfg, "/x/20260925T000000Z.tar.gpg")
        return calls

    def test_default_copies_and_never_deletes(self, monkeypatch):
        calls = self._calls(monkeypatch, {})
        assert [c[1] for c in calls] == ["copyto"]

    def test_prune_only_when_asked(self, monkeypatch):
        calls = self._calls(monkeypatch, {"NMAS_BACKUP_OFFBOX_PRUNE": "1"})
        assert [c[1] for c in calls] == ["copyto", "delete"]

    def test_status_says_whose_retention_it_is(self):
        cfg = B.config_from_env({"NMAS_BACKUP_RCLONE_REMOTE": "b2:bucket"})
        cfg["recipient_file"] = "/k.asc"
        _code, lines = B.status_report({"backup_success": {"at": NOW.isoformat()}},
                                       cfg, NOW)
        assert any("lifecycle rule" in l and "cannot delete" in l for l in lines)
