"""History (NSOT_GUI_BRIEF 3.4; board D, History as one timeline, signed off 2026-10-03, C369),
on a REAL repository built by the real save path (test_golden_repo's lab), with r2's real
configuration:
- the timeline reads each store ONCE, whatever the number of devices and its filters;
- a commit is one row with its devices (a Save All of two is one row naming both); a row says
  how its person was established; a baseline decision says what it earned, with its tag; a
  commit whose record is known to be wrong is marked, with why;
- filters by device (the fleet's own rows drop out), person, kind (Commits only) and time; a
  cut list says how many it shows of how many; a filter that is not a name is refused, said;
- a commit's change is MASKED (a planted community never leaves);
- the page, its tabs and fragments under the strict policy, with info links; the old Commits
  tab's links open the timeline on commits;
- the client's outcome words for Push now and Verify, executed in duktape.
"""

import os
import types

import pytest

from modules import history_sources as HS
from modules.nsot import repo as R
from tests.test_golden_repo import _seed, lab  # noqa: F401  (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = open(os.path.join(ROOT, "tests/fixtures/configs/fleet/r2.cfg"), encoding="utf-8").read()
COMMUNITY = "Zq7PlantedCommunity91"


def _ref(repo):
    return types.SimpleNamespace(name="Lab", repo_dir=repo, data_dir=os.path.dirname(repo),
                                 csv_path=os.path.join(os.path.dirname(repo), "devices.csv"))


@pytest.fixture
def repo(lab):  # noqa: F811
    _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12", platform="cisco_ios"),
                  R.GoldenItem("s4", R2.replace("hostname r2", "hostname s4"), "203.0.113.24", platform="cisco_ios")],
          source="save_all", actor="test-person@example.invalid")
    planted = R2.replace("hostname r2\n", f"hostname r2\nsnmp-server community {COMMUNITY} RO\n")
    assert R.save_golden("Lab", [R.GoldenItem("r2", planted, "203.0.113.12", platform="cisco_ios")],
                         source="rotation", actor="other@example.invalid", allow_new=False)["ok"]
    return lab


def _timeline(repo, **kw):
    kw.setdefault("since_days", "")
    return HS.timeline(_ref(repo), **kw)


class TestOneRead:
    def test_each_store_is_read_once_whatever_the_number_of_devices(self, repo, monkeypatch):
        calls = []
        real = R.git

        def counting(r, *args):
            calls.append(args[0])
            return real(r, *args)
        monkeypatch.setattr(R, "git", counting)
        _timeline(repo, members=["r2", "s4"])          # as the page passes the list's devices
        two = list(calls)
        calls.clear()
        _seed("Lab", [R.GoldenItem(f"x{i}", R2.replace("hostname r2", f"hostname x{i}"),
                                   f"203.0.113.{40 + i}", platform="cisco_ios") for i in range(5)],
              source="capture", actor="a@example.invalid")
        calls.clear()
        _timeline(repo, members=["r2", "s4"] + [f"x{i}" for i in range(5)])
        assert calls == two, "seven devices read as two did: one read per source, never per device"
        # golden and intent (each with one read of its renames), measured, commits, decisions.
        assert calls.count("log") == 7, calls

    def test_a_device_view_is_a_fixed_number_of_reads_too(self, repo, monkeypatch):
        calls = []
        real = R.git
        monkeypatch.setattr(R, "git", lambda r, *a: calls.append(a[0]) or real(r, *a))
        _timeline(repo, device="r2")
        # golden and intent each follow the device's file, then read those commits whole.
        assert calls.count("log") <= 8, calls


class TestTheRows:
    def test_newest_first_one_row_per_commit_with_its_devices(self, repo):
        events = _timeline(repo)["events"]
        golden = [e for e in events if e["kind"] == "golden"]
        assert golden[0]["what"] == "Golden recorded (rotation)" and golden[0]["devices"] == ["r2"]
        save_all = next(e for e in golden if e["what"] == "Golden recorded (save_all)")
        assert save_all["devices"] == ["r2", "s4"], "a Save All of two is ONE row naming both"
        assert save_all["devices_words"] == "r2, s4"

    def test_how_the_person_was_established_is_said(self, repo):
        e = next(e for e in _timeline(repo)["events"] if e["what"] == "Golden recorded (rotation)")
        _rc, body, _e = R.git(repo, "log", "-1", "--format=%B", e["sha"])
        verified = next((l.split(": ", 1)[1] for l in body.splitlines()
                         if l.startswith("Actor-Verified: ")), "")
        how = HS.VERIFIED_WORDS[verified]
        assert e["who"] == "other@example.invalid" + (f" ({how})" if how else "")
        assert e["who_short"] == "other@example.invalid"

    def test_a_baseline_decision_is_the_fleets_row_with_its_tag(self, repo):
        d = next(e for e in _timeline(repo)["events"] if e["kind"] == "decision")
        assert d["devices"] == [] and d["devices_words"] == "fleet"
        assert d["what"] == "Baseline earned (save_all)" and d["outcome"] == "earned"
        assert dict(d["record"])["Tag"].startswith("baseline/")

    @pytest.mark.parametrize("decision,state,words", [
        ("denied: 8 device(s) not targeted: ['r1', 'r2']", "not_taken", "not taken: 8 not targeted"),
        ("denied: not every inventory device was captured (s3 skipped)", "denied", "denied: s3 skipped"),
        ("earned", "earned", "earned"),
        ("", "", ""),
    ])
    def test_the_baseline_words_from_the_host_s_real_trailers(self, decision, state, words):
        got = HS.baseline_words(decision, [])
        assert (got["state"], got["words"]) == (state, words)

    def test_a_tag_on_a_commit_that_recorded_nothing_is_not_recorded(self):
        assert HS.baseline_words("", ["baseline/20260901T000000Z"])["state"] == "unrecorded"

    def test_a_known_exception_is_marked_with_why(self, repo, monkeypatch):
        from modules.nsot import record_exceptions
        sha = _timeline(repo)["events"][0]["sha"]
        monkeypatch.setitem(record_exceptions.EXCEPTIONS, sha, {
            "field": "Source", "recorded": "manual", "was": "rotation", "finding": "C104",
            "why": "the rotation's commit said manual"})
        e = next(e for e in _timeline(repo)["events"] if e["sha"] == sha)
        assert "record known wrong" in e["marks"]
        assert e["exception"] == "the rotation's commit said manual"


class TestFilters:
    def test_device_person_kind(self, repo):
        s4 = _timeline(repo, device="s4")["events"]
        assert s4 and all(HS.about(e, "s4") for e in s4), "the fleet's own rows drop out"
        mine = _timeline(repo, person="test-person@example.invalid")["events"]
        assert mine and {e["who_short"] for e in mine} == {"test-person@example.invalid"}
        commits = _timeline(repo, kinds=["commits"])["events"]
        assert commits and {e["kind"] for e in commits} <= {"golden", "intent", "commit"}
        assert "decision" in _timeline(repo)["counts"]

    def test_since_keeps_the_window(self, repo):
        assert _timeline(repo, since_days="7")["events"]
        old = HS.epoch("2000-01-01T00:00:00Z")
        assert all(HS.epoch(e["at"]) > old for e in _timeline(repo, since_days="7")["events"])

    def test_a_cut_list_says_how_many_of_how_many(self, repo):
        got = _timeline(repo, limit=1)
        assert len(got["events"]) == 1 and got["total"] > 1

    def test_an_unreadable_repository_is_said(self, tmp_path):
        got = HS.timeline(_ref(str(tmp_path / "nothing")), since_days="")
        assert any("could not be read" in e for e in got["errors"])


class TestTheChangeIsMasked:
    def test_a_planted_community_never_leaves(self, repo):
        sha = next(e["sha"] for e in _timeline(repo)["events"]
                   if e["what"] == "Golden recorded (rotation)")
        d = HS.diff(repo, sha)
        assert d["ok"] and COMMUNITY not in d["text"] and "snmp-server community" in d["text"]

    def test_a_commit_id_that_is_not_one_is_refused(self, repo):
        assert HS.diff(repo, "--output=/tmp/x")["ok"] is False


@pytest.fixture
def client(repo, monkeypatch):
    import app as A
    from modules.nsot import listref
    monkeypatch.setattr(listref, "active", lambda: _ref(repo))
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda *a, **k: [{"hostname": "r2"}, {"hostname": "s4"}])
    return A.app.test_client()


def _rows(html):
    """Each History list row's one-line summary and the detail under it, as text."""
    import html as _h
    import re
    text = lambda s: " ".join(_h.unescape(re.sub(r"<[^>]+>", " ", s)).split())  # noqa: E731
    rows = re.findall(r'<details class="hist-row[^"]*"[^>]*>\s*<summary class="hist-sum">(.*?)'
                      r'</summary>\s*<div class="hist-detail[^"]*">(.*?)</div>\s*</details>', html, re.S)
    return [text(s) for s, _d in rows], [text(d) for _s, d in rows]


class TestThePage:
    def test_the_page_draws_the_rows_under_the_strict_policy(self, client):
        from modules import csp
        r = client.get("/v2/history?since=")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert 'data-kind="golden"' in html and 'data-kind="decision"' in html
        summaries, details = _rows(html)
        assert any("Golden recorded (rotation)" in s and " r2 " in f" {s} " for s in summaries)
        assert any("Baseline earned (save_all)" in s and "fleet" in s for s in summaries)
        assert 'class="nav-item active" href="/v2/history"' in html
        assert 'data-manual="history#timeline"' in html and 'data-manual="history"' in html
        assert COMMUNITY not in html

    def test_every_filter_is_in_the_address(self, client):
        html = client.get("/v2/history?since=&device=s4&kind=commits").get_data(as_text=True)
        summaries, _d = _rows(html)
        assert summaries and all("s4" in s for s in summaries)
        assert 'name="kind" value="commits" checked' in html
        assert "Commits (golden, intent, profile)" in html     # the kind's summary
        assert "kind=commits" in html                         # the refresh keeps the view

    def test_the_old_commits_tab_opens_the_timeline_on_commits(self, client):
        html = client.get("/v2/history?tab=commits&since=").get_data(as_text=True)
        assert 'name="kind" value="commits" checked' in html
        summaries, _d = _rows(html)
        assert summaries and not any("Baseline earned" in s for s in summaries)

    def test_a_filter_that_is_not_a_name_is_refused_and_said(self, client):
        html = client.get("/v2/history?since=&device=r2;%20rm%20-rf").get_data(as_text=True)
        assert "the device filter &#39;r2; rm -rf&#39; is not a name" in html

    def test_the_timeline_fragment_redraws_alone(self, client):
        html = client.get("/v2/history/timeline?since=&kind=commits").get_data(as_text=True)
        assert html.lstrip().startswith('<section class="card hist-timeline"')
        assert "nmas:goldens from:body" in html and "Golden recorded" in html

    def test_the_commit_fragment_is_masked(self, client, repo):
        sha = next(e["sha"] for e in _timeline(repo)["events"]
                   if e["what"] == "Golden recorded (rotation)")
        html = client.get(f"/v2/history/commit/{sha}").get_data(as_text=True)
        assert "snmp-server community" in html and COMMUNITY not in html

    def test_the_baselines_tab_draws_the_stored_judgement(self, client, monkeypatch):
        from modules import reader_job
        monkeypatch.setattr(reader_job, "read_cached", lambda name: {"doc": {"last_good": {
            "value_at": "2026-10-02T03:00:00Z", "value": {"lists": {"Lab": {"baselines": [
                {"tag": "baseline/20261001T235242Z", "created": "2026-10-01T23:52:42Z",
                 "decision": "earned", "usable": True, "withdrawn": False, "stale": []},
                {"tag": "baseline/20260927T154517Z", "created": "2026-09-27T15:45:17Z",
                 "decision": "earned", "usable": False, "withdrawn": True,
                 "withdrawn_why": "it records r2 broken by hand", "stale": []},
                {"tag": "baseline/20260920T000000Z", "created": "2026-09-20T00:00:00Z",
                 "decision": "unrecorded", "usable": False, "withdrawn": False,
                 "stale": ["s1"]}]}}}}}})
        html = client.get("/v2/history?tab=baselines").get_data(as_text=True)
        assert 'data-baseline="baseline/20261001T235242Z"' in html
        assert "it records r2 broken by hand" in html and "predates a credential change on s1" in html
        assert "not recorded" in html
        # One line per baseline; its reasons open UNDER it (the operator, 2026-10-02: they had
        # squeezed the tag and the action into narrow cells).
        summaries, details = _rows(html)
        assert len(summaries) == 3
        assert all("broken by hand" not in s and "predates" not in s for s in summaries)
        assert "it records r2 broken by hand" in details[1]
        assert "predates a credential change on s1" in details[2]

    def test_the_baselines_tab_before_any_read_says_so(self, client, monkeypatch):
        from modules import reader_job
        monkeypatch.setattr(reader_job, "read_cached", lambda name: {})
        assert "have not been read yet" in client.get("/v2/history?tab=baselines").get_data(
            as_text=True)

    def test_the_authorisations_tab(self, client, monkeypatch):
        from modules.nsot import freshness
        monkeypatch.setattr(freshness, "authorisations", lambda name, include_expired=False: [
            {"device": "r3", "at": "2026-10-01T10:00:00+00:00", "actor": "test-person@example.invalid",
             "reason": "an approved change not yet captured", "expires_at": "2026-10-02T10:00:00+00:00",
             "expired": True}])
        html = client.get("/v2/history?tab=authorisations").get_data(as_text=True)
        assert "an approved change not yet captured" in html and "expired" in html
        summaries, details = _rows(html)
        assert "Stated reason: an approved change not yet captured" in details[0]

    def test_the_remote_header_says_the_sentence(self, client):
        html = client.get("/v2/history/remote").get_data(as_text=True)
        assert 'id="hist-remote"' in html and "Everything is committed" in html
        assert "not yet compared with the remote" in html


class TestTheClientWords:
    def _outcome(self, kind, status, body):
        import json
        import dukpy
        from tests.payload_render import shipped
        return dukpy.evaljs("var window = {};\n" + shipped("nmas_history.js")
                            + f"\nwindow.NMAS_HISTORY.remoteOutcome({json.dumps(kind)}, {status}, "
                            + json.dumps(body) + ")")

    def test_verify_and_push_words(self):
        ok = self._outcome("verify", 200, {"ok": True, "checks": [{"ok": True}] * 4})
        assert ok == {"ok": True, "words": "Verified: 4 of 4 checks passed"}
        bad = self._outcome("verify", 200, {"ok": False, "checks": [
            {"ok": True, "name": "read_works"}, {"ok": False, "name": "is_private", "detail": "public"}]})
        assert bad["words"] == "Not verified: is_private (public)"
        assert self._outcome("push", 200, {"ok": True}) == {"ok": True, "words": "Pushed"}
        assert self._outcome("push", 403, {"error": "a person is required"})["words"] == \
            "Not pushed: a person is required"
        assert self._outcome("push", 500, None)["ok"] is False
