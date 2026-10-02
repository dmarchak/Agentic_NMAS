"""History (NSOT_GUI_BRIEF 3.4; the mockup signed off 2026-10-02), on a REAL
repository built by the real save path (test_golden_repo's lab), with r2's real
configuration:
- the commit list is ONE git read whatever its filters, the filter choices one more;
- filters by workflow, person, device and time, applied by git; a cut list says so;
- each row says how its actor was established and what its commit earned
  (earned with its tag, denied with why, not taken for a partial deploy);
- a commit whose record is known to be wrong carries the exception beside it;
- a commit's change is MASKED (a planted community never leaves);
- the page, its tabs and fragments under the strict policy, with info links;
- the client's outcome words for Push now and Verify, executed in duktape.
"""

import os
import types

import pytest

from modules import fleet_history as FH
from modules.nsot import repo as R
from tests.test_golden_repo import _seed, lab  # noqa: F401  (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = open(os.path.join(ROOT, "tests/fixtures/configs/fleet/r2.cfg"), encoding="utf-8").read()
COMMUNITY = "Zq7PlantedCommunity91"


def _counting(calls):
    def git(repo, *args):
        calls.append(args[0])
        return R.git(repo, *args)
    return git


@pytest.fixture
def repo(lab):  # noqa: F811
    _seed("Lab", [R.GoldenItem("r2", R2, "203.0.113.12"),
                  R.GoldenItem("s4", R2.replace("hostname r2", "hostname s4"), "203.0.113.24")],
          source="save_all", actor="test-person@example.invalid")
    planted = R2.replace("hostname r2\n", f"hostname r2\nsnmp-server community {COMMUNITY} RO\n")
    assert R.save_golden("Lab", [R.GoldenItem("r2", planted, "203.0.113.12")],
                         source="rotation", actor="other@example.invalid", allow_new=False)["ok"]
    return lab


class TestOneRead:
    def test_the_list_is_one_git_read_and_the_choices_one_more(self, repo):
        calls = []
        got = FH.commits(repo, git=_counting(calls), since_days="")
        assert got["error"] == "" and len(got["rows"]) >= 2
        assert calls == ["log"]
        calls.clear()
        FH.commits(repo, workflow="rotation", person="other@example.invalid", device="r2",
                   git=_counting(calls), since_days="30")
        assert calls == ["log"], "filters are applied by git, never per commit"
        calls.clear()
        FH.choices(repo, "", git=_counting(calls))
        assert calls == ["log"]


class TestTheRows:
    def test_newest_first_with_workflow_and_actor(self, repo):
        rows = FH.commits(repo, since_days="")["rows"]
        assert rows[0]["source"] == "rotation" and rows[0]["workflow"] == "rotation"
        assert rows[0]["who"] == "other@example.invalid"
        assert rows[0]["devices"] == ["r2"] and "golden/r2.cfg" in rows[0]["files"]

    def test_how_the_actor_was_established_is_said(self, repo):
        rows = FH.commits(repo, since_days="")["rows"]
        _rc, body, _e = R.git(repo, "log", "-1", "--format=%B", rows[0]["sha"])
        verified = next((l.split(": ", 1)[1] for l in body.splitlines()
                         if l.startswith("Actor-Verified: ")), "")
        assert rows[0]["how"] == FH.VERIFIED_WORDS[verified]

    def test_an_earned_baseline_carries_its_tag(self, repo):
        row = next(r for r in FH.commits(repo, since_days="")["rows"] if r["source"] == "save_all")
        assert row["baseline"]["state"] == "earned"
        assert row["baseline"]["tag"].startswith("baseline/")

    @pytest.mark.parametrize("decision,state,words", [
        ("denied: 8 device(s) not targeted: ['r1', 'r2']", "not_taken", "not taken: 8 not targeted"),
        ("denied: not every inventory device was captured (s3 skipped)", "denied", "denied: s3 skipped"),
        ("earned", "earned", "earned"),
        ("", "", ""),
    ])
    def test_the_baseline_words_from_the_host_s_real_trailers(self, decision, state, words):
        got = FH.baseline_words(decision, [])
        assert (got["state"], got["words"]) == (state, words)

    def test_a_tag_on_a_commit_that_recorded_nothing_is_not_recorded(self):
        assert FH.baseline_words("", ["baseline/20260901T000000Z"])["state"] == "unrecorded"

    def test_a_known_exception_is_drawn_beside_the_record(self, repo, monkeypatch):
        from modules.nsot import record_exceptions
        sha = FH.commits(repo, since_days="")["rows"][0]["sha"]
        monkeypatch.setitem(record_exceptions.EXCEPTIONS, sha, {
            "field": "Source", "recorded": "manual", "was": "rotation", "finding": "C104",
            "why": "x"})
        row = FH.commits(repo, since_days="")["rows"][0]
        assert row["exception"] == "recorded Source: manual, was rotation (C104)"


class TestFilters:
    def test_workflow_person_device(self, repo):
        assert [r["source"] for r in FH.commits(repo, workflow="rotation", since_days="")["rows"]] \
            == ["rotation"]
        assert [r["who"] for r in FH.commits(repo, person="test-person@example.invalid",
                                             since_days="")["rows"]] == ["test-person@example.invalid"]
        s4 = FH.commits(repo, device="s4", since_days="")["rows"]
        assert s4 and all("s4" in r["devices"] for r in s4)

    def test_a_regex_character_in_a_filter_is_literal(self, repo):
        # As a pattern, "." would match the real actor test-person@...; literally it does not.
        assert FH.commits(repo, person="test.person@example.invalid", since_days="")["rows"] == []

    def test_a_cut_list_says_so(self, repo):
        got = FH.commits(repo, limit=1, since_days="")
        assert len(got["rows"]) == 1 and got["cut"] is True

    @pytest.mark.parametrize("kw", [{"device": "r2; rm -rf"}, {"person": "a b"},
                                    {"workflow": "../x"}, {"since_days": "7d"}])
    def test_a_filter_that_is_not_a_name_is_refused(self, repo, kw):
        with pytest.raises(FH.HistoryError):
            FH.commits(repo, **kw)

    def test_an_unreadable_repository_is_said(self, tmp_path):
        got = FH.commits(str(tmp_path / "nothing"), since_days="")
        assert got["rows"] == [] and "could not be read" in got["error"]


class TestTheChangeIsMasked:
    def test_a_planted_community_never_leaves(self, repo):
        sha = FH.commits(repo, workflow="rotation", since_days="")["rows"][0]["sha"]
        d = FH.diff(repo, sha)
        assert d["ok"] and COMMUNITY not in d["text"] and "snmp-server community" in d["text"]

    def test_a_commit_id_that_is_not_one_is_refused(self, repo):
        assert FH.diff(repo, "--output=/tmp/x")["ok"] is False


@pytest.fixture
def client(repo, monkeypatch):
    import app as A
    from modules.nsot import listref
    ref = types.SimpleNamespace(name="Lab", repo_dir=repo,
                                csv_path=os.path.join(os.path.dirname(repo), "devices.csv"))
    monkeypatch.setattr(listref, "active", lambda: ref)
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda *a, **k: [{"hostname": "r2"}, {"hostname": "s4"}])
    return A.app.test_client()


class TestThePage:
    def test_the_page_draws_the_rows_under_the_strict_policy(self, client):
        from modules import csp
        r = client.get("/v2/history?since=")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert 'data-commit="' in html and "rotation" in html and "baseline/" in html
        assert 'class="nav-item active" href="/v2/history"' in html
        assert 'data-manual="history#commits"' in html and 'data-manual="history"' in html
        assert COMMUNITY not in html

    def test_the_commit_fragment_is_masked(self, client, repo):
        sha = FH.commits(repo, workflow="rotation", since_days="")["rows"][0]["sha"]
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
