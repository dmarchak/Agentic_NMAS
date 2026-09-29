"""C182: does the break-glass record hold the credential NMAS holds NOW?

The record lives on the operator's laptop; the credentials NMAS holds live on
the host, encrypted with the host's key. `verify` proved the record opens and
compared it with nothing, and a rotation made it stale with nothing saying so.
Both sides now compute the same salted digest: `digests` on the host,
`verify --against` beside the record. No credential crosses, none is printed,
and no device is contacted. Each export is logged (digests only), so job
health names a device whose entry a rotation has made stale, and the rotation
message says to export again.
"""

import json
import os
import socket

import pytest

import modules.breakglass as bg
from tests.test_breakglass import _cli

PASS = "a-long-enough-passphrase"
RECORD = [{"hostname": h, "ip": f"192.0.2.{i}", "username": "admin", "password": pw,
           "platform": "cisco_iosxe"}
          for i, (h, pw) in enumerate((("r1", "old-r1-pass-1234"), ("s1", "old-s1-pass-1234"),
                                       ("bp-ztp-a", "probe-pass-12345")), 1)]
NOW = {"r1": "old-r1-pass-1234",          # unchanged
       "s1": "new-s1-pass-5678",          # rotated since the export
       "r2": "r2-pass-never-exported"}    # managed, not in the record


def _now_digests():
    return {h: bg.currency_digest(h, "admin", pw) for h, pw in NOW.items()}


class TestTheDigest:
    def test_it_is_salted_by_hostname_and_covers_the_username(self):
        a = bg.currency_digest("r1", "admin", "same")
        assert a == bg.currency_digest("r1", "admin", "same")
        assert a != bg.currency_digest("r2", "admin", "same"), "two devices, one password"
        assert a != bg.currency_digest("r1", "other", "same")
        assert "same" not in a

    def test_compare_names_each_state(self):
        rows = {r["device"]: r["state"] for r in bg.compare(
            bg.digests_of(RECORD), _now_digests())}
        assert rows == {"r1": "current", "s1": "differs", "bp-ztp-a": "left",
                        "r2": "missing"}


@pytest.fixture
def record(tmp_path, monkeypatch):
    path = str(tmp_path / "rcn.bg")
    bg.write_record(path, bg.build_payload(RECORD, list_name="default",
                                           fernet_key=b"k" * 44), PASS)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASS)
    return path


class TestVerifyAgainstTheHost:
    def _run(self, capsys, monkeypatch, *argv):
        cli = _cli()
        monkeypatch.setattr("sys.argv", ["nmas-breakglass", *argv])
        rc = cli.main()
        return rc, capsys.readouterr().out

    def test_each_device_is_named_with_its_state_and_no_value_is_printed(
            self, record, tmp_path, capsys, monkeypatch):
        against = tmp_path / "digests.json"
        against.write_text(json.dumps({"list": "default", "devices": _now_digests()}))
        # Verification contacts no device: any connect attempt fails the test.
        monkeypatch.setattr(socket, "create_connection",
                            lambda *a, **k: pytest.fail("verify tried to connect"))
        rc, out = self._run(capsys, monkeypatch, "verify", record, "--against", str(against))
        assert rc == 1
        compare = out[out.index("compare :"):]
        assert "r1          current" in compare
        assert "s1          DIFFERS" in compare
        assert "bp-ztp-a    left management" in compare
        assert "r2          MISSING" in compare
        for value in [d["password"] for d in RECORD] + list(NOW.values()):
            assert value not in out

    def test_all_current_exits_zero(self, record, tmp_path, capsys, monkeypatch):
        same = {d["hostname"]: bg.currency_digest(d["hostname"], d["username"], d["password"])
                for d in RECORD}
        against = tmp_path / "digests.json"
        against.write_text(json.dumps({"list": "default", "devices": same}))
        rc, out = self._run(capsys, monkeypatch, "verify", record, "--against", str(against))
        assert "3 current, 0 not: nothing to do" in out

    def test_the_host_side_prints_json_only_and_no_value(self, capsys, monkeypatch):
        cli = _cli()
        monkeypatch.setattr(cli, "_devices", lambda ln: [
            {"hostname": h, "username": "admin", "password": pw} for h, pw in NOW.items()])
        monkeypatch.setattr("sys.argv", ["nmas-breakglass", "digests", "--list", "default"])
        assert cli.main() == 0
        out = capsys.readouterr().out
        doc = json.loads(out)
        assert doc["devices"] == _now_digests() and doc["list"] == "default"
        assert not [v for v in NOW.values() if v in out]


class TestTheExportIsLogged:
    def test_digests_only_and_owner_only(self, tmp_path):
        row = bg.record_export(str(tmp_path), list_name="default", devices=RECORD,
                               path="/media/x.bg", key_fingerprint="fp", actor="op")
        path = tmp_path / bg.EXPORT_LOG
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"
        text = path.read_text()
        assert not [d["password"] for d in RECORD if d["password"] in text]
        assert row["devices"] == bg.digests_of(RECORD)
        assert bg.last_exports(str(tmp_path))["by_list"]["default"]["path"] == "/media/x.bg"

    def test_absent_and_unreadable_are_different_answers(self, tmp_path):
        assert bg.last_exports(str(tmp_path))["state"] == "absent"
        (tmp_path / bg.EXPORT_LOG).write_text("{not json\n")
        assert bg.last_exports(str(tmp_path))["state"] == "unreadable"


class TestJobHealthTracksIt:
    def _rows(self, exports, current):
        from modules.job_health import breakglass_rows
        return breakglass_rows(exports=exports, current=current)

    def _export(self, digests, at=1_790_000_000.0):
        return {"state": "ok", "by_list": {"default": {
            "at": at, "list": "default", "path": "/media/x.bg", "devices": digests}}}

    def test_a_rotation_since_the_export_is_a_stale_row_per_device(self):
        rows = self._rows(self._export(bg.digests_of(RECORD)), {"default": _now_digests()})
        by = {r["unit"]: r for r in rows}
        assert by["breakglass:default/s1"]["state"] == "breakglass_stale"
        assert "rotated since" in by["breakglass:default/s1"]["detail"]
        assert by["breakglass:default/r2"]["state"] == "breakglass_stale"
        assert "no entry" in by["breakglass:default/r2"]["detail"]
        assert "breakglass:default/r1" not in by, "a current device is not a row"
        assert "breakglass:default/bp-ztp-a" not in by, "a device that left is history"
        assert by["breakglass:default/s1"]["action"]["command"].startswith(
            "python3 scripts/nmas-breakglass export --list default --out /dev/shm/")

    def test_all_current_is_one_ok_row_naming_the_count(self):
        (r,) = self._rows(self._export(_now_digests()), {"default": _now_digests()})
        assert r["state"] == "ok" and "3 of 3 device(s) current" in r["detail"]

    def test_no_export_logged_is_unknown_and_says_how_to_settle_it(self):
        (r,) = self._rows({"state": "absent", "by_list": {}}, {"default": _now_digests()})
        assert r["state"] == "unknown" and "--against" in r["detail"]
        assert r["action"]["label"].startswith("Export the break-glass record to establish "
                                               "the baseline")
        assert r["action"]["open"] == "breakglass_export" and r["action"]["list"] == "default", \
            "the row opens the browser export (7.3)"
        assert "/dev/shm/" in r["action"]["command"], "the host's way: never beside data/key.key"

    def test_an_unreadable_log_is_unknown_never_current(self):
        (r,) = self._rows({"state": "unreadable", "by_list": {}, "error": "bad"},
                          {"default": _now_digests()})
        assert r["state"] == "unknown" and "not the same as current" in r["detail"]

    def test_no_devices_is_no_row(self):
        assert self._rows({"state": "absent", "by_list": {}}, {"default": {}}) == []

    def test_needs_attention_draws_the_stale_state_loud_and_named(self):
        from modules.attention import _JOB_STATES
        words, level = _JOB_STATES["breakglass_stale"]
        assert level == "danger" and "older credential" in words


class TestTheRotationNamesTheRecord:
    @pytest.mark.parametrize("state", ["rotated_and_persisted",
                                       "rotated_persistence_not_attempted",
                                       "rotated_persistence_unverified",
                                       "rotated_not_recorded"])
    def test_every_rotated_state_says_to_export_again(self, state):
        from modules.nsot.credential_rotation import summarise
        assert "break-glass record now holds its OLD credential" in summarise(
            {"device": "s1", "state": state})

    @pytest.mark.parametrize("state", ["reverted", "not_started"])
    def test_an_unchanged_device_does_not(self, state):
        from modules.nsot import credential_rotation as CR
        s = {"reverted": CR.REVERTED, "not_started": CR.NOT_STARTED}[state]
        assert "break-glass" not in CR.summarise({"device": "s1", "state": s})


class TestTheCliExportLogsItself:
    """Its control passed until this existed: the log was written by the
    module and nothing drove `export` to show the CLI calls it."""

    def test_an_export_writes_the_log_row_for_its_list(self, tmp_path, capsys, monkeypatch):
        from cryptography.fernet import Fernet

        cli = _cli()
        key = Fernet.generate_key()
        monkeypatch.setattr(cli, "_devices", lambda ln: [dict(d, secret="", list_name=ln,
                                                               container="") for d in RECORD])
        monkeypatch.setattr(cli, "_live_key", lambda data_dir="": key)
        monkeypatch.setattr(cli, "_live_stores", lambda data_dir="": {})
        monkeypatch.setattr(cli, "_data_dir", lambda data_dir="": str(tmp_path))
        monkeypatch.setattr("getpass.getpass", lambda prompt="": PASS)
        out = tmp_path / "rcn.bg"
        monkeypatch.setattr("sys.argv", ["nmas-breakglass", "export", "--list", "default",
                                         "--out", str(out)])
        assert cli.main() == 0
        assert "logged  :" in capsys.readouterr().out
        logged = bg.last_exports(str(tmp_path))["by_list"]["default"]
        assert logged["devices"] == bg.digests_of(RECORD)
        assert logged["path"] == str(out)
