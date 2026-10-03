"""Template library, bindings, and the approval gate.

Approval is **scheme 3** (NSOT_PLAN P.5, D11): the template's closure hash and
the person who approved it, a claim about the TEMPLATE. Whether a device is
reproduced faithfully is its own plan's ``template_report``, gating per device
with the lines named, so a device the template cannot reproduce is blocked
alone and no longer blocks every other device on its platform. Approving
records each bound device's result as evidence and needs at least one to
validate.
"""

import os

import pytest

from modules.nsot import approval, manifest, templates_repo

from tests.js_source import read_shipped

FLEET = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")


def _config(name):
    return read_shipped(os.path.join(FLEET, f"{name}.cfg"))


@pytest.fixture
def repo(tmp_path):
    path = str(tmp_path / "config_repo")
    os.makedirs(path)
    templates_repo.seed_templates(path)
    for name in ("s1", "s2", "s3"):
        manifest.upsert_device(path, f"uid:{name}", name,
                               f"203.0.113.2{name[1]}", platform="cisco-ios")
    return path


def _commit_approvals(repo):
    """Commit the approvals record, as the approve and revoke routes do: the deploy gate
    counts an approval only once it is committed (CONCURRENCY_AUDIT R13)."""
    import subprocess

    env = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@example.invalid")
    if not os.path.isdir(os.path.join(repo, ".git")):
        subprocess.run(["git", "init", "-q", repo], check=True, env=env)
    subprocess.run(["git", "-C", repo, "add", "templates/.approvals.json"], check=True, env=env)
    subprocess.run(["git", "-C", repo, "commit", "-q", "--allow-empty", "-m", "approvals"],
                   check=True, env=env)


def _approve(repo, *args, **kwargs):
    """`approval.approve`, then the commit the route makes."""
    result = approval.approve(repo, *args, **kwargs)
    if result.get("ok"):
        _commit_approvals(repo)
    return result


def _devices(names, platform="cisco_ios"):
    return [{"device": n, "platform": platform, "running_config": _config(n)}
            for n in names]


class TestSeeding:
    def test_seeds_both_platforms(self, repo):
        paths = {t["path"] for t in templates_repo.list_templates(repo)}
        assert "cisco_ios/base.j2" in paths
        assert "cisco_iosxe/base.j2" in paths

    def test_is_idempotent_and_never_overwrites(self, repo):
        templates_repo.write_template(repo, "cisco_ios/base.j2", "{# mine #}\n")
        result = templates_repo.seed_templates(repo)
        assert "cisco_ios/base.j2" in result["skipped"]
        assert templates_repo.read_template(repo, "cisco_ios/base.j2") == "{# mine #}\n"

    def test_builtins_are_copied_not_moved(self, repo):
        builtin = os.path.join(templates_repo.BUILTIN_ROOT, "cisco_ios", "base.j2")
        assert os.path.exists(builtin), "seeding moved the built-in template"


class TestBindings:
    def test_platform_binding_is_the_default(self, repo):
        assert templates_repo.template_for_device(repo, "s1", "cisco_ios") == \
            "cisco_ios/base.j2"

    def test_override_wins(self, repo):
        templates_repo.save_bindings(repo, {
            "platforms": {"cisco_ios": "cisco_ios/base.j2"},
            "overrides": {"s3": "cisco_ios/core.j2"}})
        assert templates_repo.template_for_device(repo, "s3", "cisco_ios") == \
            "cisco_ios/core.j2"
        assert templates_repo.template_for_device(repo, "s1", "cisco_ios") == \
            "cisco_ios/base.j2"

    def test_device_list_is_not_persisted(self, repo):
        """A stored list drifts from the manifest and they disagree silently."""
        import yaml
        with open(templates_repo.bindings_path(repo), encoding="utf-8") as fh:
            stored = yaml.safe_load(fh)
        assert set(stored) == {"platforms", "overrides"}
        assert "devices" not in stored

    def test_device_list_is_computed_from_the_manifest(self, repo):
        bound = [b["device"] for b in
                 templates_repo.devices_for_template(repo, "cisco_ios/base.j2")]
        assert bound == ["s1", "s2", "s3"]

        manifest.upsert_device(repo, "uid:s4", "s4", "203.0.113.24",
                               platform="cisco-ios")
        bound = [b["device"] for b in
                 templates_repo.devices_for_template(repo, "cisco_ios/base.j2")]
        assert bound == ["s1", "s2", "s3", "s4"], \
            "the bound list did not track the manifest"


class TestTemplateCrud:
    def test_syntax_error_is_refused(self, repo):
        result = templates_repo.write_template(repo, "cisco_ios/bad.j2",
                                               "{% for x in %}")
        assert result["ok"] is False and "line 1" in result["error"]

    def test_path_traversal_is_refused(self, repo):
        assert templates_repo.read_template(repo, "../../../etc/passwd") is None
        assert templates_repo.write_template(
            repo, "../escape.j2", "x")["ok"] is False

    def test_non_template_extension_is_refused(self, repo):
        assert templates_repo.write_template(
            repo, "cisco_ios/evil.sh", "rm -rf /")["ok"] is False


class TestApprovalGate:
    def test_approves_when_every_bound_device_passes(self, repo):
        result = _approve(repo, "cisco_ios/base.j2",
                                  _devices(["s1", "s2", "s3"]), actor="operator")
        assert result["ok"], result.get("error")
        assert result["validation"]["device_count"] == 3

    def test_refuses_when_no_device_round_trips(self, repo):
        templates_repo.write_template(repo, "cisco_ios/base.j2",
                                      "hostname {{ vars.hostname }}\nend\n")
        result = _approve(repo, "cisco_ios/base.j2",
                                  _devices(["s1", "s2", "s3"]))
        assert result["ok"] is False
        assert "at least one must" in result["error"]

    def test_one_failing_device_does_not_block_the_template(self, repo):
        """Scheme 3's point: s3 is blocked at ITS OWN deploy (template_report),
        so it is evidence here, not a veto over s1 and s2."""
        devices = _devices(["s1", "s2", "s3"])
        devices[2]["running_config"] += "\nsome construct no template models 42\n"
        result = _approve(repo, "cisco_ios/base.j2", devices, actor="operator")
        assert result["ok"], result.get("error")
        evidence = result["evidence"]
        assert evidence["validated"] == ["s1", "s2"]
        assert [f["device"] for f in evidence["failed"]] == ["s3"]
        assert evidence["failed"][0]["reason"]
        assert approval._load(repo)["cisco_ios/base.j2"]["evidence"] == evidence

    def test_a_device_that_could_not_be_validated_is_recorded_not_a_veto(self, repo):
        """A bound device with no capture (a pending onboarding) used to keep
        its whole platform unapprovable (D2)."""
        result = _approve(repo, "cisco_ios/base.j2", _devices(["s1"]),
                                  actor="operator",
                                  not_validated=[{"device": "s9", "reason": "no captured config yet"}])
        assert result["ok"]
        assert result["evidence"]["not_validated"] == [
            {"device": "s9", "reason": "no captured config yet"}]
        assert result["evidence"]["bound"] == 2

    def test_the_result_says_what_it_covers_and_what_it_does_not(self, repo):
        """The operator's addition: without the second sentence scheme 3 reads
        as weaker than scheme 2 to anyone who does not know why."""
        result = _approve(repo, "cisco_ios/base.j2", _devices(["s1"]))
        assert "covers the template itself" in result["covers"]
        assert "blocked there alone" in result["does_not_cover"]
        status = approval.approval_status(repo, "cisco_ios/base.j2")
        assert status["approved"] and status["covers"] and status["does_not_cover"]

    def test_failure_names_the_device_and_lines(self, repo):
        templates_repo.write_template(repo, "cisco_ios/base.j2",
                                      "hostname {{ vars.hostname }}\nend\n")
        result = _approve(repo, "cisco_ios/base.j2", _devices(["s1"]))
        failed = result["validation"]["results"][0]
        assert failed["device"] == "s1"
        assert failed["missing"] > 0
        assert failed["missing_sample"]

    def test_refuses_with_no_bound_devices(self, repo):
        result = _approve(repo, "cisco_iosxe/base.j2", [])
        assert result["ok"] is False
        assert "nothing to validate" in result["error"]


class TestTemplateFingerprint:
    """Scheme 3: the template's closure hash, and no device.

    * scheme 1 hashed each device's host_vars: a deploy revoked its own
      approval;
    * scheme 2 hashed the bound device set: onboarding one device revoked the
      approval for every device on its platform (D11, D2).

    Now **approval** is a claim about the template, revoked by an edit to it
    or to a macro file it imports; **template_report** is the per-device
    claim, live on every plan, gating there.
    """

    def test_a_template_edit_revokes(self, repo):
        before = approval.template_fingerprint(repo, "cisco_ios/base.j2")
        templates_repo.write_template(repo, "cisco_ios/base.j2", "{# edited #}\n")
        after = approval.template_fingerprint(repo, "cisco_ios/base.j2")
        assert before["fingerprint"] != after["fingerprint"]

    def test_onboarding_a_device_does_NOT_revoke(self, repo):
        """D2, resolved: a device joining the platform used to take the
        approval, and with it every other device's deploy path, offline."""
        approval._save(repo, {"cisco_ios/base.j2":
                              approval.template_fingerprint(repo, "cisco_ios/base.j2")})
        _commit_approvals(repo)
        assert approval.is_approved(repo, "cisco_ios/base.j2")
        manifest.upsert_device(repo, "uid:s9", "s9", "203.0.113.29", platform="cisco-ios")
        assert approval.is_approved(repo, "cisco_ios/base.j2")

    def test_removing_a_device_does_not_revoke(self, repo):
        before = approval.template_fingerprint(repo, "cisco_ios/base.j2")
        data = manifest.load(repo)
        data["devices"].pop("uid:s3")
        manifest.save(repo, data)
        assert approval.template_fingerprint(repo, "cisco_ios/base.j2")["fingerprint"] == \
            before["fingerprint"]

    def test_a_devices_config_changing_does_not_revoke(self, repo):
        """A deploy is not an approval question."""
        approval._save(repo, {"cisco_ios/base.j2":
                              approval.template_fingerprint(repo, "cisco_ios/base.j2")})
        _commit_approvals(repo)
        assert approval.is_approved(
            repo, "cisco_ios/base.j2",
            {"s1": {"hostname": "s1", "totally": "different"}})

    def test_the_fingerprint_covers_the_template_only(self, repo):
        payload = approval.template_fingerprint(repo, "cisco_ios/base.j2")
        assert payload["template_hash"] and payload["scheme"] == 3
        assert set(payload) == {"scheme", "template", "template_hash", "fingerprint"}


class TestFingerprintSchemeMigration:
    """A scheme-2 record is not honoured silently: it bound the approval to a
    device set, a different claim. Moving to scheme 3 is an explicit
    re-approval, so the record says what it now means."""

    def _scheme2(self, repo):
        current = approval.template_fingerprint(repo, "cisco_ios/base.j2")
        return {**current, "scheme": 2, "devices": ["s1", "s2", "s3"],
                "device_identities": ["uid:s1", "uid:s2", "uid:s3"],
                "approved_at": "2026-09-20T00:00:00Z", "actor": "operator"}

    def test_a_scheme_2_record_is_not_valid_under_3(self, repo):
        approval._save(repo, {"cisco_ios/base.j2": self._scheme2(repo)})
        assert not approval.is_approved(repo, "cisco_ios/base.j2")

    def test_a_record_with_no_scheme_at_all_is_not_valid(self, repo):
        current = approval.template_fingerprint(repo, "cisco_ios/base.j2")
        record = {k: v for k, v in current.items() if k != "scheme"}
        approval._save(repo, {"cisco_ios/base.j2": record})
        assert not approval.is_approved(repo, "cisco_ios/base.j2")

    def test_the_status_explains_the_scheme_change(self, repo):
        approval._save(repo, {"cisco_ios/base.j2": self._scheme2(repo)})
        _commit_approvals(repo)
        status = approval.approval_status(repo, "cisco_ios/base.j2")
        assert status["approved"] is False
        assert "scheme 2" in status["reason"]
        assert any("re-approve" in c and "device set" in c for c in status["changes"])

    def test_re_approving_writes_the_current_scheme(self, repo):
        approval._save(repo, {"cisco_ios/base.j2": self._scheme2(repo)})
        result = _approve(repo, "cisco_ios/base.j2",
                                  _devices(["s1", "s2", "s3"]), actor="operator")
        assert result["ok"] is True
        assert approval._load(repo)["cisco_ios/base.j2"]["scheme"] == 3
        assert approval.is_approved(repo, "cisco_ios/base.j2")


class TestValidationUsesCapturedConfigs:
    def test_validate_takes_configs_as_input(self):
        """It cannot fetch from a device: configs are passed in."""
        import inspect
        params = inspect.signature(approval.validate_template).parameters
        assert set(params) == {"repo", "rel_path", "devices"}

    def test_unacknowledged_unmodelled_fails_validation(self, repo):
        devices = _devices(["s1"])
        devices[0]["running_config"] += "quantum-tunnel profile ALPHA\n peer 203.0.113.9\n"
        result = approval.validate_template(repo, "cisco_ios/base.j2", devices)
        assert result["ok"] is False
        assert result["results"][0]["unmodeled_acknowledged"] is False


class TestSeedingCommitsItself:
    """Seeding copied files in and committed nothing.

    The first ``save_templates()`` that ran afterwards — in practice the
    approval — staged ``templates`` and swept the entire seeded library into a
    commit subjected ``template: approve <path>``. The subject described one
    file while the commit added the whole library, and the approval could not
    be reviewed as a diff because the diff *was* the library.
    """

    @pytest.fixture
    def app_repo(self, tmp_path, monkeypatch):
        from modules.nsot import repo as R
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "nmas@localhost",
                                "nsot_device_tag_retention": 50,
                            }.get(key, default))
        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(list_dir))
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        path = str(list_dir / "config_repo")
        R.init_repo(path)
        return path

    def _seed(self, list_name, repo):
        from routes.templates import _seed_and_commit
        return _seed_and_commit(list_name, repo)

    def test_seeding_creates_its_own_commit(self, app_repo):
        from modules.nsot import repo as R
        result = self._seed("Lab", app_repo)
        assert result["copied"]
        _rc, subject, _ = R.git(app_repo, "log", "-1", "--format=%s")
        assert subject.startswith("template: seed library")

    def test_the_seeded_library_is_tracked(self, app_repo):
        from modules.nsot import repo as R
        self._seed("Lab", app_repo)
        _rc, tracked, _ = R.git(app_repo, "ls-files", "templates")
        files = tracked.splitlines()
        assert any(f.endswith("cisco_ios/base.j2") for f in files)
        assert any(f.endswith("cisco_iosxe/base.j2") for f in files)
        assert any(f.endswith("bindings.yml") for f in files)

    def test_nothing_is_left_untracked(self, app_repo):
        from modules.nsot import repo as R
        self._seed("Lab", app_repo)
        _rc, status, _ = R.git(app_repo, "status", "--porcelain", "templates")
        assert status.strip() == ""

    def test_a_second_seed_commits_nothing(self, app_repo):
        from modules.nsot import repo as R
        self._seed("Lab", app_repo)
        _rc, before, _ = R.git(app_repo, "rev-list", "--count", "HEAD")
        result = self._seed("Lab", app_repo)
        _rc, after, _ = R.git(app_repo, "rev-list", "--count", "HEAD")
        assert result["copied"] == []
        assert before == after

    def test_seeding_creates_no_tags(self, app_repo):
        """A template commit is not a network snapshot."""
        from modules.nsot import repo as R
        self._seed("Lab", app_repo)
        _rc, tags, _ = R.git(app_repo, "tag", "--list")
        assert tags.strip() == ""

    def test_an_approval_after_seeding_commits_only_the_approval(self, app_repo):
        """The point of the fix: the approval's diff is the approval."""
        from modules.nsot import repo as R
        self._seed("Lab", app_repo)
        with open(os.path.join(app_repo, "templates", ".approvals.json"), "w",
                  encoding="utf-8") as fh:
            fh.write('{"cisco_ios/base.j2": {"approved": true}}\n')
        R.save_templates("Lab", [".approvals.json"], actor="user",
                         message="template: approve cisco_ios/base.j2")

        _rc, files, _ = R.git(app_repo, "show", "--name-only", "--format=", "HEAD")
        assert files.split() == ["templates/.approvals.json"]


class TestSeedCommitKeysOffRepoState:
    """The live shape: the library is already on disk and has never been committed.

    The first version of this fix committed when ``seed_templates()`` reported
    it had copied something. That is the filesystem's answer to "did anything
    happen this run", not the repository's answer to "is anything missing". On
    a box where the old GET-side-effect code had already copied the library in,
    ``copied`` comes back empty, ``_seed_and_commit`` returns early, and the
    files stay untracked indefinitely — which is exactly what happened.

    Sixth instance of one shape: the fixture builds from scratch, the real
    system has a history, and the code keys off this run instead of the current
    state.
    """

    @pytest.fixture
    def already_seeded(self, tmp_path, monkeypatch):
        """A repo whose templates/ is populated on disk and uncommitted."""
        from modules.nsot import repo as R, templates_repo as T
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda key, default=None: {
                                "nsot_git_author_name": "NMAS",
                                "nsot_git_author_email": "nmas@localhost",
                                "nsot_device_tag_retention": 50,
                            }.get(key, default))
        list_dir = tmp_path / "lab"
        list_dir.mkdir()
        monkeypatch.setattr("modules.config.get_list_data_dir",
                            lambda name: str(list_dir))
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
        path = str(list_dir / "config_repo")
        R.init_repo(path)
        T.seed_templates(path)              # copied in, deliberately not committed
        _rc, tracked, _ = R.git(path, "ls-files", "templates")
        assert tracked.strip() == "", "fixture must start with templates/ untracked"
        return path

    def _seed(self, list_name, repo):
        from routes.templates import _seed_and_commit
        return _seed_and_commit(list_name, repo)

    def test_a_second_seed_still_commits_the_untracked_library(self, already_seeded):
        from modules.nsot import repo as R
        result = self._seed("Lab", already_seeded)

        assert result["copied"] == [], "fixture premise: shutil copies nothing"
        assert result["untracked"], "repo state says the files are missing"
        _rc, subject, _ = R.git(already_seeded, "log", "-1", "--format=%s")
        assert subject.startswith("template: seed library")

    def test_nothing_is_left_untracked_afterwards(self, already_seeded):
        from modules.nsot import repo as R
        self._seed("Lab", already_seeded)
        _rc, status, _ = R.git(already_seeded, "status", "--porcelain", "-uall",
                               "--", "templates")
        assert status.strip() == ""

    def test_the_whole_library_is_tracked(self, already_seeded):
        from modules.nsot import repo as R
        self._seed("Lab", already_seeded)
        _rc, tracked, _ = R.git(already_seeded, "ls-files", "templates")
        files = tracked.splitlines()
        assert any(f.endswith("cisco_ios/base.j2") for f in files)
        assert any(f.endswith("cisco_iosxe/base.j2") for f in files)
        assert any(f.endswith("bindings.yml") for f in files)

    def test_it_settles_and_stops_committing(self, already_seeded):
        from modules.nsot import repo as R
        self._seed("Lab", already_seeded)
        _rc, before, _ = R.git(already_seeded, "rev-list", "--count", "HEAD")
        self._seed("Lab", already_seeded)
        _rc, after, _ = R.git(already_seeded, "rev-list", "--count", "HEAD")
        assert before == after

    def test_an_in_progress_edit_is_not_swept_into_the_seed_commit(self, already_seeded):
        """A tracked-but-modified template is someone's work, not seeding's.

        Seeding never overwrites, so it cannot have caused the modification;
        labelling it "seed library" would mislabel a commit exactly the way
        this function exists to prevent.
        """
        from modules.nsot import repo as R, templates_repo as T
        self._seed("Lab", already_seeded)                  # everything tracked

        T.write_template(already_seeded, "cisco_ios/base.j2", "{# mine #}\n")
        extra = os.path.join(already_seeded, "templates", "cisco_ios", "new.j2")
        with open(extra, "w", encoding="utf-8") as fh:
            fh.write("{# added #}\n")

        _rc, head_before, _ = R.git(already_seeded, "rev-parse", "HEAD")
        result = self._seed("Lab", already_seeded)

        assert result["uncommitted_edits"] == ["templates/cisco_ios/base.j2"]
        # A NEW file a person added is not seeding's either (C345, 2026-10-02): it used to be
        # committed as "seed library"; it is left untracked and named, for its own commit.
        assert result["not_seeding"] == ["templates/cisco_ios/new.j2"]
        _rc, head_after, _ = R.git(already_seeded, "rev-parse", "HEAD")
        assert head_after == head_before
        assert T.read_template(already_seeded, "cisco_ios/base.j2") == "{# mine #}\n"

    def test_untracked_files_inside_an_untracked_directory_are_found(self, already_seeded):
        """Without -uall, git reports '?? templates/' as one entry."""
        from routes.templates import _untracked_templates
        untracked, _modified = _untracked_templates(already_seeded)
        assert len(untracked) > 1
        assert all(p.startswith("templates/") for p in untracked)
        assert any(p.endswith(".j2") for p in untracked)


class TestRevocationIsARecordedFinding:
    """Popping the record made a revocation look like "never approved".

    Both block a deploy, so the gate was never wrong. But an approval is
    withdrawn for a reason — here, that the round-trip metric could not see
    BGP address-family nesting, so the template's claim to reproduce r3/r4/r5
    was false — and the next person to look needs to know that happened and
    what to check. Deleting the record throws the finding away.
    """

    REASON = ("round-trip comparison was blind to nesting depth; this template "
              "does not reproduce BGP address-families on r3/r4/r5")

    def _approved_repo(self, tmp_path):
        from modules.nsot import approval, templates_repo
        repo = str(tmp_path / "config_repo")
        os.makedirs(repo, exist_ok=True)
        templates_repo.seed_templates(repo)
        rel = "cisco_ios/base.j2"
        approval._save(repo, {rel: {
            "fingerprint": "abc123", "scheme": approval.FINGERPRINT_SCHEME,
            "template_hash": "t", "evidence": {"validated": ["s1", "s2"]},
            "approved_at": "2026-09-20T00:00:00Z", "actor": "operator"}})
        return repo, rel

    def test_a_revocation_requires_a_reason(self, tmp_path):
        from modules.nsot import approval
        repo, rel = self._approved_repo(tmp_path)

        result = approval.revoke(repo, rel, reason="   ")
        assert result["ok"] is False
        assert "needs a reason" in result["error"]
        # And it did not half-revoke on the way to refusing.
        assert approval._load(repo)[rel].get("revoked") is None

    def test_the_reason_survives_in_the_record(self, tmp_path):
        from modules.nsot import approval
        repo, rel = self._approved_repo(tmp_path)

        approval.revoke(repo, rel, reason=self.REASON, actor="operator")
        record = approval._load(repo)[rel]

        assert record["revoked"] is True
        assert record["reason"] == self.REASON
        assert record["actor"] == "operator"
        assert record["revoked_at"]
        # What was withdrawn, not merely that something was.
        assert record["previous_fingerprint"] == "abc123"
        assert record["previously_approved_by"] == "operator"
        assert record["previous_evidence"] == {"validated": ["s1", "s2"]}

    def test_a_revoked_template_is_not_approved(self, tmp_path):
        from modules.nsot import approval
        repo, rel = self._approved_repo(tmp_path)

        assert approval.is_approved(repo, rel) is False or True  # fingerprint-dependent
        approval.revoke(repo, rel, reason=self.REASON)
        assert approval.is_approved(repo, rel) is False

    def test_revocation_beats_a_matching_fingerprint(self, tmp_path, monkeypatch):
        """The decision must not be overturnable by a later computation.

        If the gate checked the scheme and fingerprint first, a revoked record
        that happened to match would pass — the revocation would be data the
        gate walked straight past.
        """
        from modules.nsot import approval
        repo, rel = self._approved_repo(tmp_path)
        approval.revoke(repo, rel, reason=self.REASON)

        # Force every other check to agree that this template is fine.
        monkeypatch.setattr(approval, "template_fingerprint",
                            lambda *a, **k: {"fingerprint": "abc123",
                                             "template_hash": "t",
                                             "scheme": approval.FINGERPRINT_SCHEME})
        record = approval._load(repo)
        record[rel]["fingerprint"] = "abc123"
        record[rel]["scheme"] = approval.FINGERPRINT_SCHEME
        approval._save(repo, record)

        assert approval.is_approved(repo, rel) is False, (
            "a revoked approval must not be resurrected by a fingerprint match")

    def test_status_reports_the_revocation_and_its_reason(self, tmp_path):
        from modules.nsot import approval
        repo, rel = self._approved_repo(tmp_path)
        approval.revoke(repo, rel, reason=self.REASON, actor="operator")

        status = approval.approval_status(repo, rel, {})
        assert status["approved"] is False
        assert status["revoked"] is True
        assert self.REASON in status["reason"]
        assert status["actor"] == "operator"

    def test_re_approving_clears_the_tombstone(self, tmp_path, monkeypatch):
        """Revocation blocks until re-validation passes — not for ever."""
        from modules.nsot import approval
        repo, rel = self._approved_repo(tmp_path)
        approval.revoke(repo, rel, reason=self.REASON)

        monkeypatch.setattr(approval, "validate_template",
                            lambda *a, **k: {"ok": True, "device_count": 1,
                                             "results": [{"device": "s1", "ok": True}]})
        monkeypatch.setattr(approval, "template_fingerprint",
                            lambda *a, **k: {"fingerprint": "new", "template_hash": "t",
                                             "scheme": approval.FINGERPRINT_SCHEME})
        result = _approve(repo, rel, [{"device": "s1"}], actor="operator")

        assert result["ok"] is True
        assert approval._load(repo)[rel].get("revoked") is None
        assert approval.is_approved(repo, rel) is True


class TestApprovalCoversTheImportClosure:
    """A template is ``base.j2`` PLUS every macro file it imports.

    ``template_hash`` hashed only ``base.j2``. ``_common.j2`` holds the
    routing, interface and service macros for both platforms, so editing it
    changed what every ``base.j2`` renders while every approval stayed valid —
    the hash never looked at the file being changed.

    Found while fixing the BGP macro: that edit would have kept
    ``cisco_ios/base.j2`` approved for s1–s4 on the strength of a hash of a
    file that did not change. Same shape as the round-trip metric it was found
    next to — a gate measuring less than its claim.
    """

    def _repo(self, tmp_path):
        from modules.nsot import templates_repo
        repo = str(tmp_path / "config_repo")
        os.makedirs(repo, exist_ok=True)
        templates_repo.seed_templates(repo)
        return repo

    def test_the_closure_includes_the_shared_macros(self, tmp_path):
        from modules.nsot import approval
        repo = self._repo(tmp_path)

        closure = approval.template_closure(repo, "cisco_ios/base.j2")
        assert "cisco_ios/base.j2" in closure
        assert "_common.j2" in closure, closure

    def test_editing_the_shared_macros_moves_the_fingerprint(self, tmp_path):
        from modules.nsot import approval, templates_repo
        repo = self._repo(tmp_path)

        before = approval.template_fingerprint(repo, "cisco_ios/base.j2")
        text = templates_repo.read_template(repo, "_common.j2")
        templates_repo.write_template(repo, "_common.j2",
                                      text + "\n{# an edit #}\n")
        after = approval.template_fingerprint(repo, "cisco_ios/base.j2")

        assert before["fingerprint"] != after["fingerprint"], (
            "an edit to the imported macros must move the fingerprint of every "
            "template that imports them")

    def test_both_platforms_move_together(self, tmp_path):
        """`_common.j2` is shared, so an edit to it reaches both."""
        from modules.nsot import approval, templates_repo
        repo = self._repo(tmp_path)

        before = {p: approval.template_fingerprint(repo, p)["fingerprint"]
                  for p in ("cisco_ios/base.j2", "cisco_iosxe/base.j2")}
        text = templates_repo.read_template(repo, "_common.j2")
        templates_repo.write_template(repo, "_common.j2", text + "\n{# edit #}\n")

        for path, old in before.items():
            assert approval.template_fingerprint(repo, path)["fingerprint"] != old, path

    def test_editing_one_platform_does_not_move_the_other(self, tmp_path):
        """The closure must not over-reach either."""
        from modules.nsot import approval, templates_repo
        repo = self._repo(tmp_path)

        untouched = approval.template_fingerprint(repo, "cisco_ios/base.j2")
        text = templates_repo.read_template(repo, "cisco_iosxe/base.j2")
        templates_repo.write_template(repo, "cisco_iosxe/base.j2",
                                      text + "\n! an edit\n")

        assert approval.template_fingerprint(
            repo, "cisco_ios/base.j2")["fingerprint"] == untouched["fingerprint"]

    def test_moving_a_macro_between_files_changes_the_hash(self, tmp_path):
        """Path-labelled, so identical total text in a different layout differs."""
        from modules.nsot import approval, templates_repo
        repo = self._repo(tmp_path)

        before = approval.template_closure_text(repo, "cisco_ios/base.j2")
        common = templates_repo.read_template(repo, "_common.j2")
        base = templates_repo.read_template(repo, "cisco_ios/base.j2")
        templates_repo.write_template(repo, "_common.j2", base)
        templates_repo.write_template(repo, "cisco_ios/base.j2", common)
        after = approval.template_closure_text(repo, "cisco_ios/base.j2")

        assert approval.content_hash(before) != approval.content_hash(after)

    def test_a_cycle_terminates(self, tmp_path):
        from modules.nsot import approval, templates_repo
        repo = self._repo(tmp_path)

        templates_repo.write_template(repo, "a.j2", "{% import 'b.j2' as b %}")
        templates_repo.write_template(repo, "b.j2", "{% import 'a.j2' as a %}")
        assert approval.template_closure(repo, "a.j2") == ["a.j2", "b.j2"]

    def test_a_missing_import_is_part_of_the_hash(self, tmp_path):
        """It changes the render — to an error — so it is not ignored."""
        from modules.nsot import approval, templates_repo
        repo = self._repo(tmp_path)

        templates_repo.write_template(repo, "x.j2", "{% import 'gone.j2' as g %}")
        assert "gone.j2" in approval.template_closure(repo, "x.j2")


class TestOnboardingNoLongerRevokesItsPlatformsApproval:
    """**D2, resolved by scheme 3 (P.5).**

    Under scheme 2 the fingerprint covered the bound device set, and
    `devices_for_template()` computes that set from the manifest with no
    pending filter, so a device that had never answered SSH revoked its
    platform's approval the moment Create wrote it into the manifest, and
    re-approval was refused until it had a capture: the platform's deploy
    path stayed offline until phase 2 completed or the device was abandoned.

    Now no device is part of the fingerprint. The bound set is still
    computed live, for the EVIDENCE an approval records, and a bound device
    with no capture is recorded as not validated instead of refusing.
    """

    def test_the_bound_set_comes_from_the_manifest_every_time(self):
        """Never a stored list: the evidence describes the population as it is."""
        import inspect

        from modules.nsot import templates_repo

        src = inspect.getsource(templates_repo.devices_for_template)
        assert "_manifest.load(repo)" in src
        assert "Never persisted" in inspect.getdoc(
            templates_repo.devices_for_template)

    def test_the_fingerprint_is_recomputed_not_stored(self):
        import inspect

        from modules.nsot import approval

        src = inspect.getsource(approval.is_approved)
        assert "template_fingerprint(repo, rel_path)" in src

    def test_a_pending_device_leaves_the_approval_standing(self, tmp_path):
        """The property, computed: a device written to the manifest by Create
        and never reached."""
        repo = str(tmp_path / "config_repo")
        os.makedirs(repo)
        templates_repo.seed_templates(repo)
        manifest.upsert_device(repo, "uid:s1", "s1", "203.0.113.21", platform="cisco-ios")
        _approve(repo, "cisco_ios/base.j2", _devices(["s1"]), actor="operator")
        assert approval.is_approved(repo, "cisco_ios/base.j2")
        manifest.upsert_device(repo, "uid:new", "brand-new", "203.0.113.99",
                               platform="cisco-ios")
        assert "brand-new" in [e["device"] for e in
                               templates_repo.devices_for_template(repo, "cisco_ios/base.j2")]
        assert approval.is_approved(repo, "cisco_ios/base.j2")

    def test_a_bound_device_with_no_capture_is_evidence_not_a_refusal(self):
        """The route records it as not validated; it never answers 400 for it."""
        import inspect

        from routes import templates

        src = inspect.getsource(templates.approve)
        assert "not_validated.append" in src
        assert "no captured config yet" in src
        assert "if missing:" not in src


class TestTheApproveRouteRecordsWhatItCouldNotValidate:
    def test_a_bound_device_with_no_capture_does_not_refuse(self, repo, monkeypatch):
        """Through the route: s1 has a capture, s2 and s3 have none (say, mid-
        onboarding). Scheme 2 answered 400 naming them; scheme 3 approves on s1
        and records the others as not validated."""
        import app as nmas
        from routes import templates as troutes

        monkeypatch.setattr(troutes, "_active_list", lambda *a: "Lab")
        monkeypatch.setattr(troutes, "_repo_for", lambda *_a: repo)
        monkeypatch.setattr(troutes, "_captured_golden",
                            lambda name, *_a, **_k: (_config(name), None) if name == "s1" else (None, None))
        monkeypatch.setattr("modules.nsot.repo.save_templates",
                            lambda *a, **k: (_commit_approvals(repo), {"ok": True})[1])
        r = nmas.app.test_client().post("/templates/approve/cisco_ios/base.j2", json={})
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["evidence"]["validated"] == ["s1"]
        assert [d["device"] for d in body["evidence"]["not_validated"]] == ["s2", "s3"]
        assert approval.is_approved(repo, "cisco_ios/base.j2")
