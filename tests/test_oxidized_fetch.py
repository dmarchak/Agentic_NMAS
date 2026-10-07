"""C314 (the operator, 2026-10-01): after a change the tool waited for
Oxidized's hourly poll, and the lab startup row suggested a capture for a
device that was exactly as recorded. Every golden-changing commit now asks
Oxidized to fetch those devices (`GET /node/next/<node>`), recorded per list.
(The lab startup row's "Oxidized hasn't fetched" wording went the same night:
plan item 4 builds the files from the earned baseline, not from Oxidized.)

Through a REAL commit in the capture lab (r2's real golden); Oxidized is a
fake client recording what was asked."""

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


class TestItWaitsForTheFetchAndReReadsFreshness:
    """C555 (the operator, 2026-10-07): asking is not enough. s2 was asked for at 00:00:59 and
    its next stored copy was 00:16:20; meanwhile freshness accused it. The request now waits,
    bounded, for a fetch that STARTED after it, then re-reads freshness at once."""

    ASKED = 1_791_331_259.0          # 2026-10-07T00:00:59Z

    class Nodes:
        """nodes.json over time: each read returns the next snapshot (the last one repeats)."""

        def __init__(self, snapshots):
            self.snapshots, self.reads = list(snapshots), 0

        def _get(self, path):
            assert path == "nodes.json"
            snap = self.snapshots[min(self.reads, len(self.snapshots) - 1)]
            self.reads += 1
            return {"ok": True, "response": SimpleNamespace(json=lambda: snap)}

    @staticmethod
    def _node(name, start, end, status):
        return {"name": name, "last": {"start": start, "end": end, "status": status}}

    def _run(self, snapshots, now=None):
        from modules import oxidized_fetch as F
        clock = {"t": self.ASKED}
        woke = []

        def sleep(s):
            clock["t"] += s
        out = F.await_fetches(["192.0.2.22"], self.ASKED, self.Nodes(snapshots), sleep=sleep,
                              clock=lambda: clock["t"], wake=lambda: woke.append(clock["t"]))
        return out, woke, clock["t"] - self.ASKED

    def test_a_fetch_that_started_after_the_request_ends_the_wait_and_wakes_freshness(self):
        before = self._node("192.0.2.22", "2026-10-06 22:00:00 UTC", "2026-10-06 22:00:14 UTC",
                            "success")
        after = self._node("192.0.2.22", "2026-10-07 00:01:02 UTC", "2026-10-07 00:01:18 UTC",
                           "success")
        out, woke, waited = self._run([[before], [before], [after]])
        assert out == {"192.0.2.22": "success"}
        assert len(woke) == 1 and waited == 6, "two 3 s polls, then the fetch, then the wake"

    def test_a_failed_fetch_is_named_and_still_wakes_freshness(self):
        failed = self._node("192.0.2.22", "2026-10-07 00:01:02 UTC", "2026-10-07 00:06:10 UTC",
                            "no_connection")
        out, woke, _w = self._run([[failed]])
        assert out == {"192.0.2.22": "no_connection"} and len(woke) == 1

    def test_no_fetch_within_the_bound_is_said_and_still_wakes_freshness(self):
        from modules import oxidized_fetch as F
        stale = self._node("192.0.2.22", "2026-10-06 22:00:00 UTC", "2026-10-06 22:00:14 UTC",
                           "success")
        out, woke, waited = self._run([[stale]])
        assert out == {"192.0.2.22": f"not fetched within {F.AWAIT_FETCH_S} s"}
        assert len(woke) == 1 and F.AWAIT_FETCH_S <= waited < F.AWAIT_FETCH_S + 3

    def test_only_the_real_client_waits(self, monkeypatch):
        """A caller's own client (a test, the rotation that confirms its own fetch) spawns no
        wait; the real one does."""
        from modules import oxidized_fetch as F
        spawned = []
        monkeypatch.setattr("threading.Thread", lambda **kw: SimpleNamespace(
            start=lambda: spawned.append(kw["name"])))
        monkeypatch.setattr(F, "_record_path", lambda name: "/dev/null/never")
        F.request("Lab", [("r2", "192.0.2.12")], "t", client=FakeOxidized())
        assert spawned == []

        class Real(FakeOxidized):
            def __init__(self, timeout=10):
                super().__init__()
        monkeypatch.setattr("modules.integrations.oxidized.OxidizedIntegration", Real)
        monkeypatch.setattr("modules.oxidized_fetch.node_for", lambda h, ip: ip)
        F.request("Lab", [("r2", "192.0.2.12")], "t")
        assert spawned == ["oxidized-await"]

