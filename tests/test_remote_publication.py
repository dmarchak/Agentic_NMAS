"""C223: whether a list's history is ON its remote, measured by asking the
remote for its branch, never taken from the push hook's own record.

The operator's R10 demo, 2026-09-29: abandon's commit `7a72258` stayed on the
host while GitHub held `cf4d96d`, and the Git tab read "Everything is
committed". Every state is driven here against real git repositories (a bare
repository as the remote, reached through the list repository's own
`origin`), and the one sentence is executed where the screens draw it.
"""

import json
import os
import subprocess
import time

import pytest

from modules.readers import remote_publication as P


def _g(repo, *args):
    out = subprocess.run(["git", "-C", repo, "-c", "user.email=t@example.com",
                          "-c", "user.name=T", *args], capture_output=True, text=True)
    assert out.returncode == 0, (args, out.stderr)
    return out.stdout.strip()


def _commit(repo, name, when=None):
    with open(os.path.join(repo, name), "w") as fh:
        fh.write(name + "\n")
    _g(repo, "add", name)
    env = dict(os.environ)
    if when:
        env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = f"@{int(when)} +0000"
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@example.com", "-c", "user.name=T",
                    "commit", "-q", "-m", f"{name} commit"], check=True, env=env)
    return _g(repo, "rev-parse", "HEAD")


@pytest.fixture
def lab(tmp_path):
    """A list directory with a config repository, and a bare remote as origin."""
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    list_dir = tmp_path / "lists" / "default"
    repo = list_dir / "config_repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _g(str(repo), "remote", "add", "origin", str(bare))
    (list_dir / "remote.json").write_text(json.dumps(
        {"owner": "acct", "repo": "nsot", "ssh_alias": "a", "branch": "main"}))
    return {"repo": str(repo), "dir": str(list_dir), "bare": str(bare), "tmp": tmp_path}


def _push(lab):
    _g(lab["repo"], "push", "-q", "origin", "HEAD:refs/heads/main")


class TestEachStateFromRealRepositories:
    def test_in_sync(self, lab):
        _commit(lab["repo"], "a")
        _push(lab)
        out = P.judge(lab["repo"], lab["dir"])
        assert out["state"] == "in_sync" and out["ahead"] == 0
        assert out["remote"] == "acct/nsot" and out["head"] == out["remote_head"]

    def test_the_operators_case_one_commit_not_pushed(self, lab):
        """cf4d96d pushed (onboarding), 7a72258 not (abandon)."""
        _commit(lab["repo"], "onboarding")
        _push(lab)
        when = time.time() - 12 * 60
        abandon = _commit(lab["repo"], "abandon", when=when)
        out = P.judge(lab["repo"], lab["dir"])
        assert (out["state"], out["ahead"], out["oldest_sha"]) == ("ahead", 1, abandon)
        assert abs(out["oldest_at"] - int(when)) < 2
        said = P.describe(out, now=int(when) + 12 * 60)
        # Twelve minutes is past UNPUSHED_DANGER_S (2026-10-01): not lag, red.
        assert said["level"] == "danger"
        assert said["clause"] == (f"1 commit(s) not pushed to acct/nsot (oldest: {abandon[:7]}, "
                                  "12 min): auto-push has not sent it, and a commit pushes "
                                  "within seconds")

    def test_the_next_pushed_commit_sends_both(self, lab):
        """The operator's acceptance: after the fix, the next commit's push
        (or Push now) sends the unpushed one with it."""
        _commit(lab["repo"], "onboarding")
        _push(lab)
        _commit(lab["repo"], "abandon")
        _commit(lab["repo"], "next")
        assert P.judge(lab["repo"], lab["dir"])["ahead"] == 2
        _push(lab)
        assert P.judge(lab["repo"], lab["dir"])["state"] == "in_sync"

    def test_the_oldest_is_the_first_unpushed_not_the_newest(self, lab):
        _commit(lab["repo"], "a")
        _push(lab)
        first = _commit(lab["repo"], "b", when=time.time() - 3600)
        _commit(lab["repo"], "c")
        out = P.judge(lab["repo"], lab["dir"])
        assert out["ahead"] == 2 and out["oldest_sha"] == first

    def test_the_remote_holds_a_commit_this_repository_lacks(self, lab):
        _commit(lab["repo"], "a")
        _push(lab)
        other = str(lab["tmp"] / "other")
        subprocess.run(["git", "clone", "-q", lab["bare"], other], check=True)
        _commit(other, "elsewhere")
        _g(other, "push", "-q", "origin", "HEAD:refs/heads/main")
        out = P.judge(lab["repo"], lab["dir"])
        assert out["state"] == "remote_ahead" and "never force-pushes" in out["reason"]
        assert P.describe(out)["level"] == "danger"

    def test_diverged(self, lab):
        _commit(lab["repo"], "a")
        _push(lab)
        other = str(lab["tmp"] / "other")
        subprocess.run(["git", "clone", "-q", lab["bare"], other], check=True)
        _commit(other, "theirs")
        _g(other, "push", "-q", "origin", "HEAD:refs/heads/main")
        _g(lab["repo"], "fetch", "-q", "origin")          # their commit is known here
        _commit(lab["repo"], "ours")
        assert P.judge(lab["repo"], lab["dir"])["state"] == "diverged"

    def test_a_remote_with_no_branch_counts_every_commit(self, lab):
        _commit(lab["repo"], "a")
        _commit(lab["repo"], "b")
        out = P.judge(lab["repo"], lab["dir"])
        assert (out["state"], out["ahead"]) == ("no_branch", 2)

    def test_a_remote_that_cannot_be_asked_is_not_asked_never_in_sync(self, lab):
        _commit(lab["repo"], "a")
        _g(lab["repo"], "remote", "set-url", "origin", str(lab["tmp"] / "absent.git"))
        out = P.judge(lab["repo"], lab["dir"])
        assert out["state"] == "not_asked" and "ls-remote failed" in out["reason"]
        assert P.describe(out)["clause"].startswith("whether it is pushed is unknown")

    def test_a_remote_that_does_not_answer_in_time_is_not_asked(self, lab, monkeypatch):
        _commit(lab["repo"], "a")
        real = P._git

        def slow(repo, *args, timeout=P.LOCAL_GIT_TIMEOUT_S):
            if args and args[0] == "ls-remote":
                assert timeout == P.LS_REMOTE_TIMEOUT_S, "the bound is the measured one"
                raise subprocess.TimeoutExpired(["git"], timeout)
            return real(repo, *args, timeout=timeout)
        monkeypatch.setattr(P, "_git", slow)
        out = P.judge(lab["repo"], lab["dir"])
        assert out["state"] == "not_asked" and f"within {P.LS_REMOTE_TIMEOUT_S} s" in out["reason"]

    def test_an_unreadable_record_still_compares_through_origin_and_says_so(self, lab):
        _commit(lab["repo"], "a")
        _push(lab)
        _commit(lab["repo"], "b")
        with open(os.path.join(lab["dir"], "remote.json"), "w") as fh:
            fh.write("{not json")
        out = P.judge(lab["repo"], lab["dir"])
        assert (out["state"], out["ahead"], out["record"]) == ("ahead", 1, "unreadable")
        said = P.describe(out)
        assert said["level"] == "danger" and ("cannot be read, so the push hook refuses every "
                                              "push until it is repaired") in said["clause"]

    def test_no_origin_and_no_record_is_no_remote(self, lab):
        _commit(lab["repo"], "a")
        _g(lab["repo"], "remote", "remove", "origin")
        os.remove(os.path.join(lab["dir"], "remote.json"))
        out = P.judge(lab["repo"], lab["dir"])
        assert out["state"] == "no_remote"
        assert P.describe(out)["clause"] == "no remote: the history is on this host only"

    def test_the_read_covers_every_list_with_a_repository(self, lab, monkeypatch):
        monkeypatch.setattr("modules.config.LISTS_DIR", str(lab["tmp"] / "lists"))
        _commit(lab["repo"], "a")
        out = P.read(lists={"Default": "default", "Empty": "empty"})
        assert set(out["lists"]) == {"Default"}, "a list with no repository is not read"


class TestTheSentence:
    def test_in_sync_reads_as_pushed(self):
        said = P.describe({"state": "in_sync", "remote": "acct/nsot", "branch": "main",
                           "head": "a" * 40, "remote_head": "a" * 40, "asked_at": 100},
                          now=130)
        assert said == {"level": "success", "state": "in_sync",
                        "clause": "and pushed to acct/nsot",
                        "detail": "HEAD aaaaaaa, acct/nsot main at aaaaaaa; compared 30 s ago"}

    def test_nothing_read_yet_is_said_and_is_not_green(self):
        said = P.describe({})
        assert said["level"] == "secondary" and "not yet compared" in said["clause"]


class TestNeedsAttention:
    def _cached(self, lists):
        return {"state": "ok", "doc": {"last_good": {"value": {"lists": lists},
                                                     "value_at": "2026-09-29T21:10:00Z"},
                                       "stale_after_seconds": 300}}

    def test_an_unpushed_commit_is_a_row_naming_the_count_and_the_action(self):
        from modules.attention import remote_source

        out = remote_source(cached=self._cached({"Default": {
            "state": "ahead", "ahead": 1, "remote": "acct/nsot", "branch": "main",
            "head": "7a72258" + "0" * 33, "remote_head": "cf4d96d" + "0" * 33,
            "oldest_sha": "7a72258" + "0" * 33, "oldest_at": time.time() - 300,
            "oldest_subject": "abandon: R10 - onboarding withdrawn", "asked_at": time.time(),
            "record": "ok"}}))
        (r,) = out["rows"]
        assert r["what"] == "1 commit(s) on Default not pushed to acct/nsot"
        assert "oldest: 7a72258" in r["cause"] and "Push now" in r["action"]["label"]
        # The button is on the Devices tab; the first text sent the operator to
        # the Git tab, which has no Push (2026-09-29).
        assert "Devices tab" in r["action"]["label"] and "Git tab" not in r["action"]["label"]
        assert r["level"] == "warning" and r["since"]

    def test_published_lists_are_counted_not_rows(self):
        from modules.attention import remote_source

        out = remote_source(cached=self._cached({"Default": {"state": "in_sync", "ahead": 0,
                                                              "record": "ok"}}))
        assert out["rows"] == [] and "published: Default" in out["checked"]

    def test_in_sync_with_an_unreadable_record_is_a_danger_row(self):
        from modules.attention import remote_source

        out = remote_source(cached=self._cached({"Default": {
            "state": "in_sync", "ahead": 0, "record": "unreadable",
            "record_detail": "unreadable: Expecting property name"}}))
        (r,) = out["rows"]
        assert r["level"] == "danger" and "next commit will not be pushed" in r["what"]

    def test_a_reader_that_never_stored_a_value_is_a_row_not_silence(self):
        from modules.attention import remote_source

        out = remote_source(cached={"state": "absent", "why": "no store yet", "doc": None})
        assert out.get("error") or out.get("rows"), out


class TestTheScreensDrawTheOneSentence:
    def test_the_shipped_remote_card_draws_the_level_and_escapes(self):
        import dukpy
        from tests.payload_render import lift, shipped

        src = shipped("partials__golden_repo.2.js")
        esc = lift(shipped("partials__golden_repo.1.js"), "_gEsc")
        js = esc + "\n" + lift(src, "remotePublicationHtml")
        said = P.describe({"state": "ahead", "ahead": 1, "remote": "a/<b>",
                           "oldest_sha": "7a72258", "oldest_at": 100}, now=400)
        html = dukpy.evaljs(js + f"\nremotePublicationHtml({json.dumps(said)})")
        assert "alert-warning" in html and "1 commit(s) not pushed to a/&lt;b&gt;" in html
        assert "<b>" not in html
        unknown = dukpy.evaljs(js + "\nremotePublicationHtml({level: 'weird', clause: 'x'})")
        assert "alert-warning" in unknown and "success" not in unknown
        assert "not reported" in dukpy.evaljs(js + "\nremotePublicationHtml(null)")

    def test_the_git_tab_says_committed_and_whether_pushed(self):
        """The line the operator read, 'Everything is committed', now carries
        the remote: the shipped renderer, executed."""
        import dukpy
        from tests.payload_render import lift

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        page = open(os.path.join(root, "templates", "index.html"), encoding="utf-8").read()
        js = "\n".join(lift(page, n) for n in ("escHtml", "gitLevel", "_renderGitStatus"))
        stub = ("var els = {gitStatusBar: {className: '', classList: {remove: function(){}}},"
                " gitStatusText: {innerHTML: '', textContent: ''}};"
                "var document = {getElementById: function(i){ return els[i]; }};")

        def draw(status):
            return dukpy.evaljs(stub + js + f"\n_renderGitStatus({json.dumps(status)});"
                                "[els.gitStatusBar.className, els.gitStatusText.innerHTML]")
        ahead = P.describe({"state": "ahead", "ahead": 1, "remote": "acct/nsot",
                            "branch": "main", "head": "7a72258", "remote_head": "cf4d96d",
                            "oldest_sha": "7a72258", "oldest_at": 100}, now=400)
        cls, html = draw({"initialised": True, "ok": True, "uncommitted": [],
                          "last_commit": "7a72258 abandon: R10", "publication": ahead})
        assert "alert-warning" in cls
        assert "<strong>Everything is committed</strong> · <span title=" in html
        assert ">1 commit(s) not pushed to acct/nsot (oldest: 7a72258, 5 min)</span>." in html
        assert "HEAD 7a72258, acct/nsot main at cf4d96d" in html, "the evidence, on hover"
        synced = P.describe({"state": "in_sync", "remote": "acct/nsot"})
        cls, html = draw({"initialised": True, "ok": True, "uncommitted": [],
                          "publication": synced})
        assert "alert-success" in cls and "Everything is committed</strong> <span" in html
        assert "and pushed to acct/nsot" in html
        cls, _ = draw({"initialised": True, "ok": True, "uncommitted": []})
        assert "alert-success" not in cls, "no publication reported is never green"

    def test_the_git_log_has_no_pipeline_column(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        page = open(os.path.join(root, "templates", "index.html"), encoding="utf-8").read()
        assert "Pipeline (before P.4)" not in page and "c.pipeline" not in page
        assert "<summary>How this works</summary>" in page


class TestAManualPushReReads:
    """Push now goes around the post-commit hooks, so the row it answers stayed
    up for a reader cycle after the push (2026-09-29)."""

    def test_the_push_route_re_reads(self):
        import ast
        import inspect

        import routes.remote as RR

        tree = ast.parse(inspect.getsource(RR.push))
        called = {n.func.id for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "_reread_publication" in called

    def test_the_re_read_runs_the_reader_off_the_request(self, monkeypatch):
        import threading

        import routes.remote as RR

        ran = threading.Event()
        monkeypatch.setattr(P, "refresh_hook", lambda ctx: ran.set())
        RR._reread_publication()
        assert ran.wait(5), "the push did not re-read the remote"


class TestAHeldPushIsSaidAndItsTagsFollow:
    """The operator, 2026-10-01: four commits sat on the host for four hours.
    Every one was HELD at the publication gate (r6's golden had gained an SNMP
    community), the reason was in the log alone, and the row said "not
    pushed" with Push now as its action, which could not work until a person
    re-acknowledged. And the baseline tagged while held would not have been
    sent by the next automatic push, which sent only its own save's tags.
    Driven through the REAL push hook against real repositories."""

    @pytest.fixture
    def hooked(self, lab, monkeypatch):
        from modules.nsot import remote as R
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: lab["dir"] if name == "default" else "/nonexistent")
        cfg = json.loads(open(os.path.join(lab["dir"], "remote.json")).read())
        cfg["auto_push"] = True
        R.save_remote("default", cfg)
        lab["decision"] = {"push": False, "held": True, "needs": "re-acknowledgement",
                           "reason": "what would be published has grown since it was "
                                     "acknowledged: more snmp_community"}
        monkeypatch.setattr(R, "auto_push_decision", lambda *a, **k: lab["decision"])
        return lab

    def _hook(self, lab, tags=()):
        from modules.nsot import archive
        return archive.push_hook({"repo": lab["repo"], "list_name": "default",
                                  "tags": list(tags), "devices": ["r6"]})

    def _remote_tags(self, lab):
        return {l.split("refs/tags/")[1] for l in
                _g(lab["repo"], "ls-remote", "--tags", "origin").splitlines()
                if not l.endswith("^{}")}

    def test_the_hold_is_recorded_drawn_red_and_its_action_is_to_acknowledge(self, hooked):
        from modules import attention
        _commit(hooked["repo"], "profile")
        _push(hooked)
        _commit(hooked["repo"], "r6", when=time.time() - 60)
        out = self._hook(hooked, tags=[])
        assert out["held"] is True
        pub = P.judge(hooked["repo"], hooked["dir"])
        assert "more snmp_community" in pub["held"]["reason"]
        said = P.describe(pub)
        assert said["level"] == "danger" and said["state"] == "held"
        assert "auto-push is HELD" in said["clause"] and "more snmp_community" in said["clause"]
        assert "acknowledges publication" in said["clause"]
        cached = {"state": "ok", "doc": {"last_good": {"value": {"lists": {"Default": pub}},
                                                        "value_at": time.time()}}}
        (row,) = attention.remote_source(cached=cached)["rows"]
        assert row["level"] == "danger" and "held back" in row["what"]
        assert "acknowledge it, then Push now" in row["action"]["label"]

    def test_acknowledged_since_the_hold_says_push_now(self, hooked):
        from modules.nsot import remote as R
        _commit(hooked["repo"], "a")
        _push(hooked)
        _commit(hooked["repo"], "b")
        self._hook(hooked)
        cfg = R.load_remote("default")
        cfg["acknowledged_secrets"] = {"at": "2999-01-01T00:00:00Z"}
        R.save_remote("default", cfg)
        said = P.describe(P.judge(hooked["repo"], hooked["dir"]))
        assert "acknowledged since, so Push now sends them" in said["clause"]

    def test_a_tag_made_while_held_goes_with_the_next_automatic_push(self, hooked):
        from modules.nsot import remote as R
        _commit(hooked["repo"], "a")
        _push(hooked)
        _commit(hooked["repo"], "save-all")
        _g(hooked["repo"], "tag", "-a", "baseline/20261001T050133Z", "-m", "b")
        self._hook(hooked, tags=["baseline/20261001T050133Z"])          # held
        assert "baseline/20261001T050133Z" not in self._remote_tags(hooked)
        assert P.judge(hooked["repo"], hooked["dir"])["tags_not_pushed"] == \
            ["baseline/20261001T050133Z"]
        # Controls: a tag outside the tool's namespaces, and one naming a
        # commit this push does not publish, never ride along.
        _g(hooked["repo"], "tag", "-a", "manual/x", "-m", "m")
        _g(hooked["repo"], "checkout", "-q", "-b", "side")
        _commit(hooked["repo"], "side")
        _g(hooked["repo"], "tag", "-a", "golden/r9/off-branch", "-m", "o")
        _g(hooked["repo"], "checkout", "-q", "main")
        hooked["decision"] = {"push": True, "reason": "acknowledgement still covers this"}
        _commit(hooked["repo"], "next")
        out = self._hook(hooked, tags=[])                                # the NEXT commit
        assert out["ok"] is True and "baseline/20261001T050133Z" in out["tags_pushed"]
        there = self._remote_tags(hooked)
        assert "baseline/20261001T050133Z" in there
        assert "manual/x" not in there and "golden/r9/off-branch" not in there
        assert "auto_push_held" not in R.load_remote("default"), "a push clears the hold"
        assert P.describe(P.judge(hooked["repo"], hooked["dir"]))["state"] == "in_sync"

    def test_in_step_with_a_tag_left_on_the_host_is_not_published(self, hooked):
        _commit(hooked["repo"], "a")
        _g(hooked["repo"], "tag", "-a", "baseline/1", "-m", "b")
        _push(hooked)
        said = P.describe(P.judge(hooked["repo"], hooked["dir"]))
        assert said["state"] == "tags_not_pushed" and said["level"] == "warning"
        assert "1 tag(s) not on it (baseline/1)" in said["clause"]

    def test_an_unpushed_commit_with_no_hold_is_red_once_it_is_not_lag(self):
        base = {"state": "ahead", "ahead": 1, "oldest_sha": "abcdef0", "remote": "acct/nsot",
                "head": "h", "remote_head": "r", "branch": "main"}
        now = 10_000.0
        fresh = P.describe(dict(base, oldest_at=now - 60), now=now)
        late = P.describe(dict(base, oldest_at=now - P.UNPUSHED_DANGER_S), now=now)
        assert fresh["level"] == "warning" and "has not sent it" not in fresh["clause"]
        assert late["level"] == "danger" and "auto-push has not sent it" in late["clause"]


def test_the_shipped_card_lists_each_acknowledged_secret_by_fingerprint():
    """The acknowledgement stays reviewable: kind, fingerprint and devices,
    escaped; an acknowledgement before fingerprints says so (2026-10-01)."""
    import dukpy
    from tests.payload_render import lift, shipped

    js = (lift(shipped("partials__golden_repo.1.js"), "_gEsc") + "\n"
          + lift(shipped("partials__golden_repo.2.js"), "remoteAckValuesHtml"))
    html = dukpy.evaljs(js + "\nremoteAckValuesHtml({'a1b2c3d4e5f6': {kind: 'snmp_community', "
                             "devices: ['r1', '<r6>']}})")
    assert "snmp_community" in html and "a1b2c3d4e5f6" in html and "r1, &lt;r6&gt;" in html
    old = dukpy.evaljs(js + "\nremoteAckValuesHtml(undefined)")
    assert "before secrets had fingerprints" in old
