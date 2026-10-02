"""Each device's lab startup file against what its committed golden would
produce (the operator, 2026-10-01, after the afternoon's redeploy; module
``modules/lab_startup.py``, reader ``lab-startup``, Needs attention).

The golden is rendered through the clab sync's OWN sanitiser and compared
line for line with the file, its header aside. Measured on the host the same
day: equal on all nine devices. Here the startup files are made from the nine
REAL fleet configs by the full script's functions, lifted by the clab sync
test's own helper (a different path from the module's), and every difference
is a minimal edit of one.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest

from modules import lab_startup as L
from tests.test_clab_sync_commit import _function

FLEET = "tests/fixtures/configs/fleet"
HOSTS = ["r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4"]
DIALECT = {h: ("cisco_iosxe" if h.startswith("r") else "cisco_ios") for h in HOSTS + ["r5"]}
CDIR = "labs/lab/configs"


def _golden(h):
    return open(f"{FLEET}/{h}.cfg", encoding="utf-8").read()


def _synced(h, golden=None):
    """What the clab sync writes for *h* from Oxidized's copy (here the golden)."""
    script = (_function("kind_for") + _function("sanitise") + _function("render_device")
              + f'\nrender_device {h} "$(kind_for {DIALECT[h]})" "$(cat)"\n')
    out = subprocess.run(["bash", "-c", script], input=golden or _golden(h),
                         capture_output=True, text=True, check=True)
    return out.stdout


def _legacy(h, sha="a" * 40):
    """A file the sync wrote before C313: its provenance header, then the same text."""
    return f"!\n! {h} - from Oxidized HEAD {sha}\n!\n" + _synced(h)


TAG = "baseline/20261001T235242Z"


def _check(files, hosts=HOSTS, golden=None, target=None, reads=None, source=None):
    """The check, its SOURCE (what the sync builds from: plan item 4) the fleet
    config itself unless given, and the current golden the same unless given."""
    ref = SimpleNamespace(name="Lab")
    devices = [(ref, {"hostname": h, "platform": DIALECT[h]}) for h in hosts]

    def reader(host, cdir):
        if reads is not None:
            reads.append((host, cdir))
        return dict(files)

    return L.check(population=lambda: devices,
                   golden=golden or (lambda r, h: _golden(h)),
                   reader=reader,
                   source=source or (lambda r, h: {"text": _golden(h), "tag": TAG}),
                   target=target or (lambda ln, h: {"host": "lab-host", "configs_dir": CDIR,
                                                    "lab": "default", "named": True}))


def _by(result):
    return {d["device"]: d for d in result["devices"]}


class TestTheComparison:
    def test_every_real_device_matches_what_the_sync_writes_from_its_golden(self):
        files = {f"{h}.cfg": _synced(h) for h in HOSTS}
        r = _check(files)
        assert {h: d["state"] for h, d in _by(r).items()} == {h: "matches" for h in HOSTS}
        assert r["checked"] == 8 and r["configured"] and r["unowned"] == []

    def test_a_file_written_before_c313_with_its_provenance_header_still_matches(self):
        files = {f"{h}.cfg": _legacy(h) for h in HOSTS}
        assert all(d["state"] == "matches" for d in _check(files)["devices"])

    def test_the_sync_writes_no_provenance_into_the_file(self):
        """C313: the header made every Oxidized commit change every file."""
        assert all("from Oxidized" not in _synced(h) for h in HOSTS)

    def test_a_header_naming_another_device_is_not_provenance(self):
        files = {f"{h}.cfg": _synced(h) for h in HOSTS}
        files["r3.cfg"] = "!\n! r4 - from Oxidized HEAD abc1234\n!\n" + _synced("r3")
        assert _by(_check(files))["r3"]["state"] == "differs"

    def test_a_line_the_device_gained_is_named(self):
        files = {f"{h}.cfg": _synced(h) for h in HOSTS}
        files["r3.cfg"] = _synced("r3", _golden("r3").replace(
            "hostname r3\n", "hostname r3\nip domain lookup source-interface Loopback0\n"))
        d = _by(_check(files))["r3"]
        assert d["state"] == "differs" and d["only_golden_count"] == 0
        assert d["only_file"] == ["ip domain lookup source-interface Loopback0"]

    def test_a_credential_is_named_by_its_slot_never_its_value(self):
        assert "username admin privilege 15 password 0 admin" in _golden("r2")
        files = {f"{h}.cfg": _synced(h) for h in HOSTS}
        files["r2.cfg"] = _synced("r2", _golden("r2").replace(
            "privilege 15 password 0 admin", "privilege 15 password 0 Zq7Unrelated"))
        r = _check(files)
        d = _by(r)["r2"]
        assert d["state"] == "differs"
        assert d["credentials"] == ["username admin privilege 15 password 0 <redacted:user_password>"]
        assert d["only_golden"] == [] and d["only_file"] == []
        assert "Zq7Unrelated" not in json.dumps(r)

    def test_a_missing_file_is_its_own_state(self):
        files = {f"{h}.cfg": _synced(h) for h in HOSTS if h != "s4"}
        assert _by(_check(files))["s4"]["state"] == "missing"

    def test_a_file_no_device_owns_is_named(self):
        # r5's, retired: the host's lab still holds labs/lab/configs/r5.cfg.
        files = {f"{h}.cfg": _synced(h) for h in HOSTS + ["r5"]}
        assert _check(files)["unowned"] == [{"lab": "default", "file": f"{CDIR}/r5.cfg"}]

    def test_a_device_the_baseline_does_not_hold_is_not_built_with_the_sync_s_reason(self):
        files = {f"{h}.cfg": _synced(h) for h in HOSTS}

        def source(r, h):
            if h == "s1":
                raise L.SourceRefused(f"{TAG} holds no golden for s1 (onboarded since)")
            return {"text": _golden(h), "tag": TAG}

        d = _by(_check(files, source=source))["s1"]
        assert d["state"] == "not_built" and "holds no golden for s1" in d["why"]

    def test_a_file_is_compared_with_what_the_baseline_builds_and_names_it(self):
        r = _check({f"{h}.cfg": _synced(h) for h in HOSTS})
        assert {d["baseline"] for d in r["devices"]} == {TAG}

    def test_a_device_moved_since_the_baseline_is_said_while_its_file_matches(self):
        files = {f"{h}.cfg": _synced(h) for h in HOSTS}
        moved = lambda r, h: (_golden(h).replace("hostname r3\n", "hostname r3\nip domain "  # noqa: E731
                                                 "lookup source-interface Loopback0\n")
                              if h == "r3" else _golden(h))
        d = _by(_check(files, golden=moved))
        assert d["r3"]["state"] == "matches"
        assert d["r3"]["since_baseline"]["state"] == "differs"
        assert d["r3"]["since_baseline"]["only_golden"] == [
            "ip domain lookup source-interface Loopback0"]
        assert d["r1"]["since_baseline"]["state"] == "matches"

    def test_a_platform_the_sanitiser_has_no_rules_for_is_unknown(self):
        out = L.compare("x1", "junos", "hostname x1\n", "hostname x1\n")
        assert out["state"] == "unknown" and "no sanitising rules for platform junos" in out["why"]


class TestThePopulation:
    def test_each_lab_is_read_once_never_per_device(self):
        reads = []
        _check({f"{h}.cfg": _synced(h) for h in HOSTS}, reads=reads)
        assert reads == [("lab-host", CDIR)]

    def test_an_unknown_lab_is_unknown_with_its_cause(self):
        target = lambda ln, h: ({"host": "lab-host", "configs_dir": "", "lab": "typo",
                                 "named": False, "why": "lab 'typo' is not in clab_labs"}
                                if h == "r1" else {"host": "lab-host", "configs_dir": CDIR,
                                                   "lab": "default", "named": True})
        d = _by(_check({f"{h}.cfg": _synced(h) for h in HOSTS}, target=target))["r1"]
        assert d["state"] == "unknown" and "not in clab_labs" in d["why"]

    def test_no_lab_host_is_not_configured(self):
        target = lambda ln, h: {"host": "", "configs_dir": CDIR, "lab": "default", "named": True}
        r = _check({}, target=target)
        assert r["configured"] is False
        assert all("clab_host is not configured" in d["why"] for d in r["devices"])

    def test_an_unreadable_directory_makes_every_device_unknown(self):
        ref = SimpleNamespace(name="Lab")

        def reader(host, cdir):
            raise RuntimeError("lab-host:labs/lab/configs could not be read: Permission denied")

        r = L.check(population=lambda: [(ref, {"hostname": "r1", "platform": "cisco_iosxe"})],
                    golden=lambda r_, h: _golden(h), reader=reader,
                    target=lambda ln, h: {"host": "lab-host", "configs_dir": CDIR,
                                          "lab": "default", "named": True})
        assert r["devices"][0]["state"] == "unknown" and "Permission denied" in r["errors"][0]

    def test_the_read_parses_one_command_s_answer(self, monkeypatch):
        seen = []

        def fake(host, cmd, timeout=60):
            seen.append(cmd)
            return {"ok": True, "text": f"{L.SEP}r1.cfg\nhostname r1\n{L.SEP}s1.cfg\nhostname s1\n"}

        monkeypatch.setattr("modules.nsot.credential_rotation._ssh_read", fake)
        assert L.read_lab("lab-host", CDIR) == {"r1.cfg": "hostname r1\n",
                                                "s1.cfg": "hostname s1\n"}
        assert len(seen) == 1 and "for f in *.cfg" in seen[0]


class TestNeedsAttention:
    @staticmethod
    def _source(value):
        from modules import attention
        cached = {"state": "ok", "doc": {"last_good": {"value": value, "value_at": 1_790_000_000},
                                         "stale_after_seconds": 1500}}
        return attention.lab_startup_source(cached=cached)

    def test_a_difference_is_a_warning_naming_the_file_and_the_lines(self):
        files = {f"{h}.cfg": _synced(h) for h in HOSTS + ["r5"]}
        files["r3.cfg"] = _synced("r3", _golden("r3").replace(
            "hostname r3\n", "hostname r3\nip domain lookup source-interface Loopback0\n"))
        res = self._source(_check(files))
        rows = {r["what"]: r for r in res["rows"]}
        row = rows[f"r3's lab startup file is not what {TAG} builds"]
        assert row["level"] == "warning" and row["devices"] == ["r3"]
        assert f"A redeploy boots {CDIR}/r3.cfg" in row["cause"]
        assert "`ip domain lookup source-interface Loopback0`" in row["cause"]
        assert "capture" not in row["action"]["label"]
        info = rows[f"{CDIR}/r5.cfg is a startup file no managed device owns"]
        assert info["level"] == "info"
        assert "7 holding what the sync builds" in res["checked"]

    def test_a_credential_row_carries_no_value(self):
        files = {f"{h}.cfg": _synced(h) for h in HOSTS}
        files["r2.cfg"] = _synced("r2", _golden("r2").replace(
            "privilege 15 password 0 admin", "privilege 15 password 0 Zq7Unrelated"))
        res = self._source(_check(files))
        assert "a credential differs in value" in json.dumps(res)
        assert "Zq7Unrelated" not in json.dumps(res)
        row = next(r for r in res["rows"] if r["devices"] == ["r2"])
        assert row["level"] == "danger" and row["what"].endswith(": a credential differs")
        assert "a credential the tool no longer holds" in row["cause"]

    def test_a_device_moved_since_the_baseline_is_a_row_saying_a_redeploy_returns_it(self):
        moved = lambda r, h: (_golden(h).replace("hostname r3\n", "hostname r3\nip domain "  # noqa: E731
                                                 "lookup source-interface Loopback0\n")
                              if h == "r3" else _golden(h))
        res = self._source(_check({f"{h}.cfg": _synced(h) for h in HOSTS}, golden=moved))
        assert [r["what"] for r in res["rows"]] == [f"A redeploy returns r3 to {TAG}"]
        row = res["rows"][0]
        assert "+1 / -0 lines: `ip domain lookup source-interface Loopback0`" in row["cause"]
        assert row["action"]["label"] == "Save All earns a new baseline that carries what it runs now"

    def test_a_device_not_built_is_a_row_with_the_sync_s_reason(self):
        def source(r, h):
            if h == "s1":
                raise L.SourceRefused(f"{TAG} holds no golden for s1 (onboarded since)")
            return {"text": _golden(h), "tag": TAG}

        res = self._source(_check({f"{h}.cfg": _synced(h) for h in HOSTS}, source=source))
        row = next(r for r in res["rows"] if r["devices"] == ["s1"])
        assert row["what"] == "The clab sync builds no startup file for s1"
        assert "holds no golden for s1" in row["cause"]

    def test_all_matching_is_no_row_and_says_what_was_compared(self):
        res = self._source(_check({f"{h}.cfg": _synced(h) for h in HOSTS}))
        assert res["rows"] == []
        assert res["checked"] == ("8 device(s) compared over 1 lab(s), 8 holding what the sync "
                                  "builds")

    def test_not_configured_is_said(self):
        res = self._source({"configured": False, "devices": []})
        assert res["rows"] == [] and "no lab host configured" in res["checked"]

    def test_the_reader_is_declared_and_announces_its_key(self):
        from modules import invalidation, reader_job
        assert "modules.readers.lab_startup" in reader_job.DECLARED_MODULES
        assert "lab_startup" in invalidation.VOCABULARY
        from modules.readers import lab_startup as R
        assert R.READER.invalidates == ("lab_startup",)
