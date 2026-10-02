"""C314 (the operator, 2026-10-01): after a change the tool waited for
Oxidized's hourly poll, and the lab startup row suggested a capture for a
device that was exactly as recorded. Every golden-changing commit now asks
Oxidized to fetch those devices (`GET /node/next/<node>`), recorded per list,
and the row says "Oxidized hasn't fetched r3 since its change at HH:MM —
fetch requested at HH:MM".

Through a REAL commit in the capture lab (r2's real golden); Oxidized is a
fake client recording what was asked."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from tests.test_capture import build_capture_lab


class FakeOxidized:
    def __init__(self, configured=True, refuse=()):
        self.configured, self.refuse, self.asked = configured, set(refuse), []

    def is_configured(self):
        return self.configured

    def _get(self, path):
        self.asked.append(path)
        node = path.rsplit("/", 1)[-1]
        if node in self.refuse:
            return {"ok": False, "error": "HTTP 404"}
        return {"ok": True, "response": SimpleNamespace(text="")}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    cap = build_capture_lab(monkeypatch, tmp_path)
    settings = {"oxidized_node_identity": "ip"}
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: settings.get(key, {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost"}.get(key, default)))
    cap["settings"] = settings
    return cap


def _commit_r2(cap, text):
    from modules.nsot.repo import GoldenItem, save_golden
    out = save_golden("Lab", [GoldenItem("r2", text, "203.0.113.12", platform="cisco_iosxe")],
                      source="capture", actor="t", allow_new=False, baseline=False)
    assert out["ok"], out
    return subprocess.run(["git", "-C", cap["repo"], "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


def _hook(cap, sha, client):
    from modules import oxidized_fetch as F
    return F.golden_hook(
        {"repo": cap["repo"], "sha": sha, "list_name": "Lab", "source": "capture"},
        ask=lambda ln, devs, why: F.request(ln, devs, why, client=client,
                                            clock=lambda: 1_790_000_000))


class TestAChangedGoldenAsksOxidized:
    def test_the_device_is_asked_for_by_its_node_and_the_request_recorded(self, lab):
        from modules import oxidized_fetch as F
        sha = _commit_r2(lab, lab["captured"].replace(
            "hostname r2\n", "hostname r2\nip domain lookup source-interface Loopback0\n"))
        client = FakeOxidized()
        got = _hook(lab, sha, client)
        assert got == {"ok": True, "message": "asked Oxidized to fetch r2"}
        assert client.asked == ["node/next/203.0.113.12"]
        rec = F.requests_for("Lab")["r2"]
        assert rec["ok"] and rec["node"] == "203.0.113.12" and rec["at"] == "2026-09-21T14:13:20Z"
        assert rec["why"].startswith(f"commit {sha[:10]} (capture) changed its golden")

    def test_by_hostname_when_oxidized_keeps_devices_by_name(self, lab):
        lab["settings"]["oxidized_node_identity"] = "hostname"
        sha = _commit_r2(lab, lab["captured"] + "!\n")
        client = FakeOxidized()
        _hook(lab, sha, client)
        assert client.asked == ["node/next/r2"]

    def test_a_commit_that_changed_no_golden_asks_nothing(self, lab):
        from modules.nsot.repo import save_host_vars
        from modules.nsot import hostvars
        from modules.nsot.parsers import get_parser
        hv = get_parser("cisco_iosxe").parse(lab["captured"])
        hv["hostname"] = "r2"
        hostvars.write_committed(lab["repo"], {**hv, "snmp": {**(hv.get("snmp") or {}),
                                                              "location": "rack 9"}})
        assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
        sha = subprocess.run(["git", "-C", lab["repo"], "rev-parse", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        client = FakeOxidized()
        assert _hook(lab, sha, client) == {"ok": True, "message": "no golden changed"}
        assert client.asked == []

    def test_not_configured_asks_and_records_nothing(self, lab):
        from modules import oxidized_fetch as F
        sha = _commit_r2(lab, lab["captured"] + "!\n")
        got = _hook(lab, sha, FakeOxidized(configured=False))
        assert "not configured" in got["message"] and F.requests_for("Lab") == {}

    def test_a_refused_ask_is_recorded_and_the_hook_says_so(self, lab):
        from modules import oxidized_fetch as F
        sha = _commit_r2(lab, lab["captured"] + "!\n")
        got = _hook(lab, sha, FakeOxidized(refuse={"203.0.113.12"}))
        assert got == {"ok": False, "error": "r2: HTTP 404"}
        assert F.requests_for("Lab")["r2"]["ok"] is False

    def test_the_hook_is_registered_for_every_commit(self):
        from modules.nsot import hooks
        assert "oxidized-fetch" in hooks.ensure_default_hooks()


class TestTheLagIsRead:
    """`oxidized_lag()` against the real repository: the golden's commit time
    beside Oxidized's last fetch and the request record."""

    def _lag(self, lab, monkeypatch, fetched):
        from modules import lab_startup as L

        class Ox:
            def __init__(self, timeout=10):
                pass

            def is_configured(self):
                return True

            def node_times(self):
                return {"ok": True, "times": fetched}

        monkeypatch.setattr("modules.integrations.oxidized.OxidizedIntegration", Ox)
        ref = SimpleNamespace(name="Lab", repo_dir=lab["repo"])
        return L.oxidized_lag()(ref, "r2", {"hostname": "r2", "ip": "203.0.113.12"})

    def _golden_at(self, lab):
        return subprocess.run(["git", "-C", lab["repo"], "log", "-1", "--format=%cI", "HEAD",
                               "--", "golden/r2.cfg"], capture_output=True, text=True,
                              check=True).stdout.strip()

    def test_a_fetch_older_than_the_golden_is_behind_with_the_request_named(self, lab,
                                                                             monkeypatch):
        from modules import oxidized_fetch as F
        sha = _commit_r2(lab, lab["captured"] + "!\n")
        F.request("Lab", [("r2", "203.0.113.12")], "t", client=FakeOxidized())
        lag = self._lag(lab, monkeypatch, {"203.0.113.12": "2020-01-01 00:00:00 UTC"})
        assert lag["behind"] is True and lag["fetched_at"] == "2020-01-01T00:00:00Z"
        assert lag["requested_at"] is not None and sha

    def test_a_fetch_after_the_golden_is_not_behind(self, lab, monkeypatch):
        _commit_r2(lab, lab["captured"] + "!\n")
        lag = self._lag(lab, monkeypatch, {"203.0.113.12": "2099-01-01 00:00:00 UTC"})
        assert lag["behind"] is False

    def test_no_fetch_at_all_is_behind_and_a_request_before_the_change_is_not_one(
            self, lab, monkeypatch):
        from modules import oxidized_fetch as F
        F.request("Lab", [("r2", "203.0.113.12")], "t", client=FakeOxidized(),
                  clock=lambda: 1_000_000_000)
        _commit_r2(lab, lab["captured"] + "!\n")
        lag = self._lag(lab, monkeypatch, {})
        assert lag["behind"] is True and lag["fetched_at"] is None
        assert lag["requested_at"] is None
        from modules.nsot.credential_rotation import as_utc
        assert as_utc(lag["golden_at"]) == as_utc(self._golden_at(lab))


class TestTheRowSaysOxidizedIsBehind:
    @staticmethod
    def _value(lag):
        return {"configured": True, "labs": 1, "checked": 1, "unowned": [],
                "devices": [{"list": "Lab", "device": "r3", "lab": "default",
                             "file": "labs/lab/configs/r3.cfg", "state": "differs",
                             "reordered": False, "credentials": [],
                             "only_golden": [" length 0"], "only_golden_count": 1,
                             "only_file": [], "only_file_count": 0, "lag": lag}]}

    @staticmethod
    def _rows(value):
        from modules import attention
        cached = {"state": "ok", "doc": {"last_good": {"value": value, "value_at": 1_790_000_000},
                                         "stale_after_seconds": 1500}}
        return attention.lab_startup_source(cached=cached)["rows"]

    def test_behind_with_a_request_names_both_times_and_suggests_no_capture(self):
        rows = self._rows(self._value({"golden_at": "2026-10-01T22:10:05Z",
                                       "fetched_at": "2026-10-01T21:58:00Z",
                                       "requested_at": "2026-10-01T22:10:07Z", "behind": True}))
        assert [r["what"] for r in rows] == [
            "Oxidized hasn't fetched r3 since its change at 22:10 UTC — fetch requested at "
            "22:10 UTC"]
        text = json.dumps(rows)
        assert "its last fetch was at 21:58 UTC" in text and "capture" not in text
        assert rows[0]["action"]["label"].startswith("Nothing to do")

    def test_behind_with_no_request_says_it_waits_for_oxidized(self):
        rows = self._rows(self._value({"golden_at": "2026-10-01T22:10:05Z", "fetched_at": None,
                                       "requested_at": None, "behind": True}))
        assert rows[0]["what"] == "Oxidized hasn't fetched r3 since its change at 22:10 UTC"
        assert "Oxidized holds no fetch of it" in rows[0]["cause"]
        assert "no fetch was requested" in rows[0]["action"]["label"]

    def test_not_behind_is_still_the_difference_row(self):
        for lag in ({"behind": False, "golden_at": "x"}, {}):
            rows = self._rows(self._value(lag))
            assert rows[0]["what"] == "r3's lab startup file is not what its golden would produce"
            assert "capture it" in rows[0]["action"]["label"]
