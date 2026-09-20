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
    @pytest.fixture
    def approved(self, repo):
        devices = _devices(["s1", "s2", "s3"])
        approval.approve(repo, "cisco_ios/base.j2", devices, actor="dustin")
        host_vars = approval.validate_template(
            repo, "cisco_ios/base.j2", devices)["host_vars_by_device"]
        return repo, host_vars

    def test_approved_state_holds_when_nothing_changes(self, approved):
        repo, host_vars = approved
        assert approval.is_approved(repo, "cisco_ios/base.j2", host_vars) is True

    def test_editing_the_template_revokes(self, approved):
        repo, host_vars = approved
        text = templates_repo.read_template(repo, "cisco_ios/base.j2")
        templates_repo.write_template(repo, "cisco_ios/base.j2", text + "\n{# x #}\n")
        status = approval.approval_status(repo, "cisco_ios/base.j2", host_vars)
        assert status["approved"] is False
        assert "the template was edited" in status["changes"]

    def test_onboarding_a_device_revokes(self, approved):
        """Amendment 2: a Phase 4 device must not inherit an approval."""
        repo, host_vars = approved
        manifest.upsert_device(repo, "uid:s4", "s4", "203.0.113.24",
                               platform="cisco-ios")
        status = approval.approval_status(repo, "cisco_ios/base.j2", host_vars)
        assert status["approved"] is False
        assert any("s4" in c and "now bound" in c for c in status["changes"])

    def test_unbinding_a_device_revokes(self, approved):
        repo, host_vars = approved
        templates_repo.save_bindings(repo, {
            "platforms": {"cisco_ios": "cisco_ios/base.j2"},
            "overrides": {"s3": "cisco_ios/other.j2"}})
        status = approval.approval_status(repo, "cisco_ios/base.j2", host_vars)
        assert status["approved"] is False
        assert any("s3" in c and "no longer bound" in c for c in status["changes"])

    def test_changing_host_vars_revokes(self, approved):
        repo, host_vars = approved
        host_vars["s2"]["hostname"] = "s2-renamed"
        status = approval.approval_status(repo, "cisco_ios/base.j2", host_vars)
        assert status["approved"] is False
        assert any("host_vars for 's2' changed" in c for c in status["changes"])

    def test_fingerprint_covers_all_three_inputs(self, repo):
        devices = _devices(["s1", "s2"])
        host_vars = approval.validate_template(
            repo, "cisco_ios/base.j2", devices)["host_vars_by_device"]
        fp = approval.binding_fingerprint(repo, "cisco_ios/base.j2", host_vars)
        assert fp["template_hash"]
        assert fp["devices"] == ["s1", "s2", "s3"]      # from the manifest
        assert set(fp["device_hashes"]) == {"s1", "s2", "s3"}

    def test_unknown_device_hash_is_marked(self, repo):
        """A bound device with no captured config cannot be silently ignored."""
        fp = approval.binding_fingerprint(repo, "cisco_ios/base.j2", {})
        assert set(fp["device_hashes"].values()) == {"unknown"}


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
