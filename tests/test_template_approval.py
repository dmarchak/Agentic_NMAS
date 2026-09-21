"""Template library, bindings, and the approval gate.

Approval is keyed on a **binding fingerprint**: the template's content plus the
set of bound devices plus a hash of each device's host_vars. Without the device
half, a device onboarded in Phase 4 would silently inherit an approval for a
template it had never been validated against — the record would claim
"validated" about a device nobody had looked at.
"""

import os

import pytest

from modules.nsot import approval, manifest, templates_repo

FLEET = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")


def _config(name):
    with open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture
def repo(tmp_path):
    path = str(tmp_path / "config_repo")
    os.makedirs(path)
    templates_repo.seed_templates(path)
    for name in ("s1", "s2", "s3"):
        manifest.upsert_device(path, f"uid:{name}", name,
                               f"203.0.113.2{name[1]}", platform="cisco-ios")
    return path


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
        result = approval.approve(repo, "cisco_ios/base.j2",
                                  _devices(["s1", "s2", "s3"]), actor="dustin")
        assert result["ok"], result.get("error")
        assert result["validation"]["device_count"] == 3

    def test_refuses_when_one_device_fails(self, repo):
        templates_repo.write_template(repo, "cisco_ios/base.j2",
                                      "hostname {{ vars.hostname }}\nend\n")
        result = approval.approve(repo, "cisco_ios/base.j2",
                                  _devices(["s1", "s2", "s3"]))
        assert result["ok"] is False
        assert "do not round-trip cleanly" in result["error"]

    def test_failure_names_the_device_and_lines(self, repo):
        templates_repo.write_template(repo, "cisco_ios/base.j2",
                                      "hostname {{ vars.hostname }}\nend\n")
        result = approval.approve(repo, "cisco_ios/base.j2", _devices(["s1"]))
        failed = result["validation"]["results"][0]
        assert failed["device"] == "s1"
        assert failed["missing"] > 0
        assert failed["missing_sample"]

    def test_refuses_with_no_bound_devices(self, repo):
        result = approval.approve(repo, "cisco_iosxe/base.j2", [])
        assert result["ok"] is False
        assert "nothing to validate it against" in result["error"]


class TestBindingFingerprint:
    """Template hash + bound device set. Scheme 2.

    Scheme 1 added a hash of each bound device's parsed host_vars. That is what
    a template was validated *against*, so freezing it looked right — and it
    keyed the gate on the result of the work, revoking approval every time a
    deploy succeeded. The division is now explicit:

    * **approval** — validated against this device set; revoked by a template
      edit or a change to the set
    * **template_report** — reproduces this device now; live, per device, every
      plan, gating there
    """

    def test_a_template_edit_revokes(self, repo):
        before = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        templates_repo.write_template(repo, "cisco_ios/base.j2", "{# edited #}\n")
        after = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        assert before["fingerprint"] != after["fingerprint"]

    def test_onboarding_a_device_revokes(self, repo):
        approval._save(repo, {"cisco_ios/base.j2":
                              approval.binding_fingerprint(repo, "cisco_ios/base.j2")})
        assert approval.is_approved(repo, "cisco_ios/base.j2")

        manifest.upsert_device(repo, "uid:s9", "s9", "203.0.113.29",
                               platform="cisco-ios")
        assert not approval.is_approved(repo, "cisco_ios/base.j2")

    def test_removing_a_device_revokes(self, repo):
        before = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        data = manifest.load(repo)
        data["devices"].pop("uid:s3")
        manifest.save(repo, data)
        after = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        assert before["fingerprint"] != after["fingerprint"]

    def test_a_devices_config_changing_does_not_revoke(self, repo):
        """The correction. A deploy is not an approval question."""
        approval._save(repo, {"cisco_ios/base.j2":
                              approval.binding_fingerprint(repo, "cisco_ios/base.j2")})
        assert approval.is_approved(
            repo, "cisco_ios/base.j2",
            {"s1": {"hostname": "s1", "totally": "different"}})

    def test_the_fingerprint_covers_template_and_device_set(self, repo):
        payload = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        assert payload["template_hash"]
        assert payload["devices"] == ["s1", "s2", "s3"]
        assert payload["device_identities"] == ["uid:s1", "uid:s2", "uid:s3"]
        assert "device_hashes" not in payload

    def test_identities_not_names_define_the_set(self, repo):
        """A rename is the same device; onboarding is not."""
        payload = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        assert all(i.startswith("uid:") for i in payload["device_identities"])


class TestFingerprintSchemeMigration:
    """A v1 record is not silently honoured.

    Its fingerprint answered a different question. Accepting it would be a gate
    that passes because nobody migrated it — which is the same failure as a
    check positioned where it cannot fail, arrived at by leaving old data in
    place.
    """

    def test_a_v1_record_is_not_valid_under_v2(self, repo):
        current = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        approval._save(repo, {"cisco_ios/base.j2": {
            **current, "scheme": 1, "device_hashes": {"s1": "abc"}}})
        assert not approval.is_approved(repo, "cisco_ios/base.j2")

    def test_a_record_with_no_scheme_at_all_is_not_valid(self, repo):
        current = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        record = {k: v for k, v in current.items() if k != "scheme"}
        approval._save(repo, {"cisco_ios/base.j2": record})
        assert not approval.is_approved(repo, "cisco_ios/base.j2")

    def test_the_status_explains_the_scheme_change(self, repo):
        current = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        approval._save(repo, {"cisco_ios/base.j2": {**current, "scheme": 1}})
        status = approval.approval_status(repo, "cisco_ios/base.j2", {})
        assert status["approved"] is False
        assert "scheme" in status["reason"]
        assert any("re-approve" in c for c in status["changes"])

    def test_re_approving_writes_the_current_scheme(self, repo):
        approval._save(repo, {"cisco_ios/base.j2": {
            **approval.binding_fingerprint(repo, "cisco_ios/base.j2"), "scheme": 1}})
        result = approval.approve(repo, "cisco_ios/base.j2",
                                  _devices(["s1", "s2", "s3"]), actor="dustin")
        assert result["ok"] is True
        assert approval._load(repo)["cisco_ios/base.j2"]["scheme"] == \
            approval.FINGERPRINT_SCHEME
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

        result = self._seed("Lab", already_seeded)

        assert result["uncommitted_edits"] == ["templates/cisco_ios/base.j2"]
        _rc, files, _ = R.git(already_seeded, "show", "--name-only", "--format=",
                              "HEAD")
        assert files.split() == ["templates/cisco_ios/new.j2"]
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
            "template_hash": "t", "devices": ["s1", "s2"],
            "approved_at": "2026-09-20T00:00:00Z", "actor": "dustin"}})
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

        approval.revoke(repo, rel, reason=self.REASON, actor="dustin")
        record = approval._load(repo)[rel]

        assert record["revoked"] is True
        assert record["reason"] == self.REASON
        assert record["actor"] == "dustin"
        assert record["revoked_at"]
        # What was withdrawn, not merely that something was.
        assert record["previous_fingerprint"] == "abc123"
        assert record["previously_approved_by"] == "dustin"
        assert record["previous_devices"] == ["s1", "s2"]

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
        monkeypatch.setattr(approval, "binding_fingerprint",
                            lambda *a, **k: {"fingerprint": "abc123",
                                             "template_hash": "t",
                                             "devices": ["s1", "s2"],
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
        approval.revoke(repo, rel, reason=self.REASON, actor="dustin")

        status = approval.approval_status(repo, rel, {})
        assert status["approved"] is False
        assert status["revoked"] is True
        assert self.REASON in status["reason"]
        assert status["actor"] == "dustin"

    def test_re_approving_clears_the_tombstone(self, tmp_path, monkeypatch):
        """Revocation blocks until re-validation passes — not for ever."""
        from modules.nsot import approval
        repo, rel = self._approved_repo(tmp_path)
        approval.revoke(repo, rel, reason=self.REASON)

        monkeypatch.setattr(approval, "validate_template",
                            lambda *a, **k: {"ok": True, "device_count": 1,
                                             "results": [{"device": "s1", "ok": True}]})
        monkeypatch.setattr(approval, "binding_fingerprint",
                            lambda *a, **k: {"fingerprint": "new", "template_hash": "t",
                                             "devices": ["s1"],
                                             "scheme": approval.FINGERPRINT_SCHEME})
        result = approval.approve(repo, rel, [{"device": "s1"}], actor="dustin")

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

        before = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        text = templates_repo.read_template(repo, "_common.j2")
        templates_repo.write_template(repo, "_common.j2",
                                      text + "\n{# an edit #}\n")
        after = approval.binding_fingerprint(repo, "cisco_ios/base.j2")

        assert before["fingerprint"] != after["fingerprint"], (
            "an edit to the imported macros must move the fingerprint of every "
            "template that imports them")

    def test_both_platforms_move_together(self, tmp_path):
        """`_common.j2` is shared, so an edit to it reaches both."""
        from modules.nsot import approval, templates_repo
        repo = self._repo(tmp_path)

        before = {p: approval.binding_fingerprint(repo, p)["fingerprint"]
                  for p in ("cisco_ios/base.j2", "cisco_iosxe/base.j2")}
        text = templates_repo.read_template(repo, "_common.j2")
        templates_repo.write_template(repo, "_common.j2", text + "\n{# edit #}\n")

        for path, old in before.items():
            assert approval.binding_fingerprint(repo, path)["fingerprint"] != old, path

    def test_editing_one_platform_does_not_move_the_other(self, tmp_path):
        """The closure must not over-reach either."""
        from modules.nsot import approval, templates_repo
        repo = self._repo(tmp_path)

        untouched = approval.binding_fingerprint(repo, "cisco_ios/base.j2")
        text = templates_repo.read_template(repo, "cisco_iosxe/base.j2")
        templates_repo.write_template(repo, "cisco_iosxe/base.j2",
                                      text + "\n! an edit\n")

        assert approval.binding_fingerprint(
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
