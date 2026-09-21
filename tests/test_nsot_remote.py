"""Phase 2b adopt-first: per-list remote, verification, first-push preview.

Nothing here pushes to a real remote. The write probe is exercised against a
local bare repository, which is enough to establish what it publishes.
"""

import json
import os
import subprocess

import pytest

from modules.nsot import remote as R


@pytest.fixture
def lab(tmp_path, monkeypatch):
    lists = tmp_path / "lists"
    (lists / "default").mkdir(parents=True)
    (lists / "other").mkdir(parents=True)
    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(lists / name))
    return lists


def _git(path, *args, **kw):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True,
                          text=True, env=env, **kw)


class TestAdoptRecordsWhatIsAlreadyThere:
    """The setup exists, made by hand. Adoption records it and changes nothing.

    A wizard that assumed greenfield would duplicate a working deploy key or
    overwrite a working SSH stanza. Adoption is also the cheapest first
    milestone: it makes a list compliant with zero new SSH material.
    """

    def test_it_writes_a_per_list_remote_json(self, lab):
        out = R.adopt("default", ssh_alias="github-nsot", owner="dmarchak",
                      repo="rcn-nsot-config", key_path="~/.ssh/nsot_deploy")
        assert out["ok"]

        saved = json.loads((lab / "default" / "remote.json").read_text())
        assert saved["ssh_alias"] == "github-nsot"
        assert saved["owner"] == "dmarchak"
        assert saved["repo"] == "rcn-nsot-config"

    def test_an_adopted_setup_is_not_managed_by_nmas(self, lab):
        """NMAS verifies and pushes; it never rewrites a human's key or stanza."""
        R.adopt("default", ssh_alias="github-nsot", owner="o", repo="r")
        saved = R.load_remote("default")
        assert saved["managed_by_nmas"] is False

    def test_auto_push_starts_false(self, lab):
        """Turned on after a successful push, never before."""
        R.adopt("default", ssh_alias="a", owner="o", repo="r")
        assert R.load_remote("default")["auto_push"] is False

    def test_nothing_is_acknowledged_yet(self, lab):
        R.adopt("default", ssh_alias="a", owner="o", repo="r")
        assert R.load_remote("default")["acknowledged_secrets"] is None

    def test_adopting_twice_refuses_rather_than_overwriting(self, lab):
        R.adopt("default", ssh_alias="a", owner="o", repo="r")
        again = R.adopt("default", ssh_alias="b", owner="o2", repo="r2")

        assert again["ok"] is False
        assert "already has a remote" in again["error"]
        assert R.load_remote("default")["owner"] == "o", "the first survives"

    def test_absent_means_no_remote(self, lab):
        assert R.load_remote("default") is None

    def test_the_module_never_opens_ssh_config(self):
        """Item 2: NMAS does not edit ~/.ssh/config, or relocate what is in it.

        Structural: no open() anywhere in the module names it. The path does
        appear in a couple of `fix` messages telling the operator where to
        look, which is the opposite of writing to it.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(R))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "open":
                literals = [a.value for a in node.args
                            if isinstance(a, ast.Constant)
                            and isinstance(a.value, str)]
                assert not any("ssh" in v for v in literals), literals


class TestTheKeyScopeIsReadFromTheGreeting:
    """`Hi owner/repo!` is a deploy key. `Hi username!` is account-wide.

    The reply distinguishes them for free, and the difference is the blast
    radius of a leaked key: one repository, or every repository the account
    owns.
    """

    def _scope(self, monkeypatch, reply):
        monkeypatch.setattr(R, "_run", lambda *a, **k: type(
            "P", (), {"stdout": reply, "stderr": "", "returncode": 1})())
        return R.check_key_scope({"ssh_alias": "a", "owner": "dmarchak",
                                  "repo": "rcn-nsot-config",
                                  "key_path": "~/.ssh/k"})

    def test_a_repo_scoped_key_passes(self, monkeypatch):
        out = self._scope(monkeypatch,
                          "Hi dmarchak/rcn-nsot-config! You've successfully "
                          "authenticated, but GitHub does not provide shell access.")
        assert out["ok"] is True

    def test_an_account_wide_key_is_refused(self, monkeypatch):
        out = self._scope(monkeypatch, "Hi dmarchak! You've successfully "
                                       "authenticated")
        assert out["ok"] is False
        assert "ACCOUNT-WIDE" in out["fix"]

    def test_a_key_for_the_wrong_repository_is_refused(self, monkeypatch):
        out = self._scope(monkeypatch, "Hi dmarchak/some-other-repo! hello")
        assert out["ok"] is False
        assert "some-other-repo" in out["fix"]

    def test_no_greeting_at_all_is_refused(self, monkeypatch):
        out = self._scope(monkeypatch, "Permission denied (publickey).")
        assert out["ok"] is False
        assert out["name"] == "key_authenticates"


class TestPrivacyIsAConjunction:
    """404 alone is ambiguous between 'private' and 'does not exist'.

    Privacy is established by the deploy key being able to read the repository
    AND an anonymous client not being able to. The two endpoints answer
    differently on a real private repo — measured: API 404, git 401 — so this
    cannot be a single-code check.
    """

    def _probe(self, monkeypatch, codes):
        import urllib.error
        import urllib.request

        def _urlopen(request, **kw):
            url = request.full_url if hasattr(request, "full_url") else str(request)
            code = codes["api" if "api.github.com" in url else "git"]
            if code == 200:
                return type("R", (), {"status": 200,
                                      "__enter__": lambda s: s,
                                      "__exit__": lambda *a: False})()
            raise urllib.error.HTTPError(url, code, "no", {}, None)

        monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
        return R.check_private({"owner": "o", "repo": "r"})

    def test_the_measured_private_shape_passes(self, monkeypatch):
        assert self._probe(monkeypatch, {"api": 404, "git": 401})["ok"] is True

    def test_a_public_repo_is_refused_on_either_endpoint(self, monkeypatch):
        for codes in ({"api": 200, "git": 401}, {"api": 404, "git": 200}):
            out = self._probe(monkeypatch, codes)
            assert out["ok"] is False, codes
            assert "PUBLIC" in out["fix"]

    def test_an_unrunnable_probe_refuses(self, monkeypatch):
        """Fail-closed: not being able to check is not having checked."""
        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("no dns")))
        out = R.check_private({"owner": "o", "repo": "r"})
        assert out["ok"] is False
        assert "could not verify" in out["fix"]


class TestTheWriteProbePublishesNothing:
    """A read-only deploy key passes read checks and fails only on a write.

    So the property is exercised. But pushing HEAD would publish every commit
    and blob under it — exactly what the acknowledgement gate exists to stop,
    before anything was acknowledged, and deleting the ref afterwards does not
    remove the objects.
    """

    def test_it_pushes_an_orphan_commit_with_no_blobs(self, tmp_path):
        bare = tmp_path / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)

        out = R.check_write_probe({"ssh_alias": str(bare), "owner": "", "repo": "",
                                   "branch": "main"})
        # The alias form would be "path:/" — build the url the probe uses.
        assert out["name"] == "write_works"

    def test_the_probe_commit_carries_an_empty_tree(self, tmp_path, monkeypatch):
        bare = tmp_path / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        monkeypatch.setattr(R, "remote_url", lambda config: str(bare))

        out = R.check_write_probe({"ssh_alias": "x", "owner": "o", "repo": "r"})
        assert out["ok"] is True, out

        # Nothing readable was published: no blobs at all in the bare repo.
        objects = _git(bare, "cat-file", "--batch-all-objects",
                       "--batch-check=%(objecttype)").stdout.split()
        assert "blob" not in objects, f"the probe published content: {objects}"
        assert objects.count("commit") == 1
        assert objects.count("tree") == 1

    def test_the_probe_ref_is_removed(self, tmp_path, monkeypatch):
        bare = tmp_path / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        monkeypatch.setattr(R, "remote_url", lambda config: str(bare))

        out = R.check_write_probe({"ssh_alias": "x", "owner": "o", "repo": "r"})
        assert out["ref_removed"] is True
        refs = _git(bare, "for-each-ref", "--format=%(refname)").stdout
        assert "writeprobe" not in refs

    def test_a_read_only_remote_is_refused_with_the_fix(self, tmp_path,
                                                        monkeypatch):
        monkeypatch.setattr(R, "remote_url",
                            lambda config: str(tmp_path / "nope.git"))
        out = R.check_write_probe({"ssh_alias": "x", "owner": "o", "repo": "r"})
        assert out["ok"] is False


class TestTheRightRepository:
    def _repo(self, tmp_path):
        work = tmp_path / "config_repo"
        work.mkdir()
        _git(work, "init", "-q")
        (work / "f").write_text("x", encoding="utf-8")
        _git(work, "add", "-A")
        _git(work, "commit", "-q", "-m", "seed")
        return str(work)

    def test_another_lists_repository_is_refused(self, lab, tmp_path,
                                                 monkeypatch):
        """Two networks sharing a repository is the silent catastrophe."""
        R.adopt("other", ssh_alias="a", owner="dmarchak", repo="shared")
        monkeypatch.setattr(R, "_run", lambda *a, **k: type(
            "P", (), {"stdout": "", "stderr": "", "returncode": 0})())

        out = R.check_right_repository(
            {"owner": "dmarchak", "repo": "shared", "ssh_alias": "a"},
            "default", self._repo(tmp_path))
        assert out["ok"] is False
        assert "other" in out["detail"]

    def test_an_empty_repository_is_accepted(self, lab, tmp_path, monkeypatch):
        monkeypatch.setattr(R, "_run", lambda *a, **k: type(
            "P", (), {"stdout": "", "stderr": "", "returncode": 0})())
        out = R.check_right_repository(
            {"owner": "o", "repo": "r", "ssh_alias": "a"}, "default",
            self._repo(tmp_path))
        assert out["ok"] is True

    def test_an_unrelated_non_empty_repository_is_refused(self, lab, tmp_path,
                                                          monkeypatch):
        # The remote has refs; the local root commit is a different sha. The
        # mock must answer the two git calls DIFFERENTLY, or it accidentally
        # reports a shared root and proves nothing.
        def _run(args, **kw):
            out = ("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\trefs/heads/main\n"
                   if "ls-remote" in args else "cafebabecafebabecafebabe\n")
            return type("P", (), {"stdout": out, "stderr": "", "returncode": 0})()

        monkeypatch.setattr(R, "_run", _run)
        out = R.check_right_repository(
            {"owner": "o", "repo": "r", "ssh_alias": "a"}, "default",
            self._repo(tmp_path))
        assert out["ok"] is False
        assert "interleave" in out["fix"]


class TestTheHistoryScanClassifiesLiveness:
    """A dead secret is evidence; a live one is an exposure.

    The plan's gate predates the rotations, when every plaintext password in
    this history was live. Asking somebody to acknowledge publishing a value
    the fleet has already moved away from, in the same breath as one still in
    use, wastes the only attention the gate has.
    """

    # `operator` is BOTH the username and the old password here, which is the
    # collision the liveness test has to survive. A synthetic value, chosen
    # not to coincide with any credential this fleet has ever held.
    OLD = ("hostname r1\n"
           "username operator privilege 15 password 0 operator\n"
           "snmp-server community FixtureCommunityA RO 99\n")
    NEW = ("hostname r1\n"
           "username operator privilege 15 secret 9 $9$fixture$hash\n"
           "snmp-server community FixtureCommunityA RO 99\n")

    def _repo(self, tmp_path):
        work = tmp_path / "config_repo"
        (work / "golden").mkdir(parents=True)
        _git(work, "init", "-q")
        (work / "golden" / "r1.cfg").write_text(self.OLD, encoding="utf-8")
        _git(work, "add", "-A")
        _git(work, "commit", "-q", "-m", "before")
        (work / "golden" / "r1.cfg").write_text(self.NEW, encoding="utf-8")
        _git(work, "add", "-A")
        _git(work, "commit", "-q", "-m", "after")
        return str(work)

    def test_a_rotated_password_is_dead(self, tmp_path, monkeypatch):
        """And is NOT live merely because the string survives elsewhere.

        The rotated value is also this device's username. Comparing against
        HEAD's raw text reported every router's old password as live — a short
        secret collides with ordinary config text. Liveness is about the value
        still occupying a SECRET POSITION, not about the string appearing.
        """
        monkeypatch.setattr("modules.redact.known_secret_values", lambda: set())
        out = R.scan_history_secrets(self._repo(tmp_path), "lab")

        row = next(r for r in out["rows"] if r["kind"] == "user_password")
        assert row["live"] == 0, "the username collision made this live"
        assert row["dead"] == 1

    def test_an_unrotated_community_is_live_and_gated(self, tmp_path,
                                                      monkeypatch):
        monkeypatch.setattr("modules.redact.known_secret_values", lambda: set())
        out = R.scan_history_secrets(self._repo(tmp_path), "lab")

        row = next(r for r in out["rows"] if r["kind"] == "snmp_community")
        assert row["live"] == 1 and row["dead"] == 0
        assert out["gated_kinds"] == ["snmp_community"]

    def test_hashes_are_reported_but_never_gated(self, tmp_path, monkeypatch):
        monkeypatch.setattr("modules.redact.known_secret_values", lambda: set())
        out = R.scan_history_secrets(self._repo(tmp_path), "lab")

        row = next(r for r in out["rows"] if r["kind"] == "user_secret_hash")
        assert row["recoverable"] is False
        assert "user_secret_hash" not in out["gated_kinds"]

    def test_it_scans_history_not_head(self, tmp_path, monkeypatch):
        """The push publishes every commit, so HEAD is the wrong question."""
        monkeypatch.setattr("modules.redact.known_secret_values", lambda: set())
        out = R.scan_history_secrets(self._repo(tmp_path), "lab")

        kinds = {r["kind"] for r in out["rows"]}
        assert "user_password" in kinds, (
            "the plaintext password exists only in an older commit")
        assert out["blobs_scanned"] >= 2

    def test_a_value_in_the_credential_store_counts_as_live(self, tmp_path,
                                                            monkeypatch):
        monkeypatch.setattr("modules.redact.known_secret_values",
                            lambda: {"operator"})
        out = R.scan_history_secrets(self._repo(tmp_path), "lab")
        row = next(r for r in out["rows"] if r["kind"] == "user_password")
        assert row["live"] == 1

    def test_the_preview_reports_counts_and_never_values(self, tmp_path,
                                                         monkeypatch, lab):
        monkeypatch.setattr("modules.redact.known_secret_values", lambda: set())
        R.adopt("default", ssh_alias="a", owner="o", repo="r")
        preview = R.first_push_preview("default", self._repo(tmp_path))

        blob = json.dumps(preview)
        assert "FixtureCommunityA" not in blob, "an SNMP community value leaked"
        assert "$9$fixture$hash" not in blob, "a hash value leaked"
        assert preview["commits"] == 2


class TestAReporterCannotPrintAValue:
    """The rule is unconditional, and cannot depend on knowing which is which.

    A report meant to show SNMP access MODES printed a community, because its
    own regex knew `snmp-server community` and not
    `snmp-server host … version 2c <community>`. The project's redactor
    already knew that shape; the reporter had reimplemented a worse one.

    "Never print a secret value" cannot be conditioned on liveness either. The
    reporter cannot know what it is holding — a dead value and a live one are
    the same string to it — so the rule has to hold before that is known.
    """

    LINES = [
        "snmp-server community FixtureCommunityA RO 99",
        "snmp-server host 203.0.113.10 version 2c FixtureCommunityB",
        "snmp-server host 203.0.113.10 traps version 2c FixtureCommunityC",
        "snmp-server host 203.0.113.10 informs version 2c FixtureCommunityD",
        "username operator privilege 15 password 0 FixtureSecretE",
        "enable secret 9 FixtureSecretF",
    ]
    TOKENS = ["FixtureCommunityA", "FixtureCommunityB", "FixtureCommunityC",
              "FixtureCommunityD", "FixtureSecretE", "FixtureSecretF"]

    def test_describe_line_masks_every_shape(self):
        for line in self.LINES:
            out = R.describe_line(line)
            leaked = [t for t in self.TOKENS if t in out]
            assert not leaked, f"{leaked} survived in {out!r}"

    def test_the_trap_host_forms_are_masked_by_the_redactor(self):
        """The gap: `traps`/`informs` sit between the host and the community.

        The old pattern knew only about `version`, so it masked the keyword
        and published the community — a line that LOOKS handled, which is
        worse than one that plainly is not.
        """
        from modules.redact import redact_positional

        for line, token in (
                ("snmp-server host 203.0.113.10 traps version 2c Tok1", "Tok1"),
                ("snmp-server host 203.0.113.10 informs version 2c Tok2", "Tok2"),
                ("snmp-server host 203.0.113.10 vrf M traps version 2c Tok3", "Tok3"),
                ("snmp-server host 203.0.113.10 version 3 priv Tok4", "Tok4"),
                ("snmp-server host 203.0.113.10 Tok5", "Tok5")):
            out = redact_positional(line)
            assert token not in out, f"{token} survived in {out!r}"

    def test_the_canary_covers_the_trap_host_shape(self):
        """So a future edit that reopens the gap is caught by the canary."""
        from modules.redact import CANARY_LINES, CANARY_TOKENS, redact_positional

        labels = [label for label, _line in CANARY_LINES]
        assert "snmp_trap_host" in labels

        for label, line in CANARY_LINES:
            out = redact_positional(line)
            assert CANARY_TOKENS[label] not in out, label


class TestSnmpAccessModes:
    """RW grants configuration write over SNMP — a path no gate here covers."""

    def _repo(self, tmp_path, body):
        work = tmp_path / "config_repo"
        (work / "golden").mkdir(parents=True)
        _git(work, "init", "-q")
        (work / "golden" / "r1.cfg").write_text(body, encoding="utf-8")
        _git(work, "add", "-A")
        _git(work, "commit", "-q", "-m", "seed")
        return str(work)

    def test_read_only_communities_report_all_read_only(self, tmp_path):
        repo = self._repo(tmp_path,
                          "snmp-server community FixtureCommunityA RO 99\n")
        out = R.snmp_access_modes(repo, "HEAD", ["r1"])

        assert out["all_read_only"] is True
        assert out["totals"]["RO"] == 1 and out["totals"]["RW"] == 0
        assert out["per_device"]["r1"]["acl_restricted"] == 1

    def test_a_write_community_is_reported_and_stops_it(self, tmp_path):
        repo = self._repo(tmp_path,
                          "snmp-server community FixtureCommunityA RW\n")
        out = R.snmp_access_modes(repo, "HEAD", ["r1"])

        assert out["all_read_only"] is False
        assert out["totals"]["RW"] == 1

    def test_an_unqualified_community_is_not_assumed_read_only(self, tmp_path):
        """No mode means the device's default, which is RO — but not stated.

        Reporting an unstated default as RO would be inferring the property
        the operator asked to have measured.
        """
        repo = self._repo(tmp_path, "snmp-server community FixtureCommunityA\n")
        out = R.snmp_access_modes(repo, "HEAD", ["r1"])

        assert out["all_read_only"] is False
        assert out["totals"]["unqualified"] == 1

    def test_no_value_appears_in_the_result(self, tmp_path):
        repo = self._repo(tmp_path,
                          "snmp-server community FixtureCommunityA RO 99\n"
                          "snmp-server host 203.0.113.10 traps version 2c "
                          "FixtureCommunityB\n")
        out = R.snmp_access_modes(repo, "HEAD", ["r1"])

        blob = json.dumps(out)
        assert "FixtureCommunityA" not in blob
        assert "FixtureCommunityB" not in blob
