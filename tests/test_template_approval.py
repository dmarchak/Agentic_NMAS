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
