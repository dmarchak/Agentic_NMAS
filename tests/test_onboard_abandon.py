"""Abandon: the inverse of the wizard, and the name given back.

A name that can be taken and never given back means one typo permanently
consumes a hostname. `_name_in_manifest` then blocks re-onboarding it, and
nothing anywhere removed the entry — so a failed onboarding was
unrecoverable rather than annoying.

`release()` alone does not fix that. It correctly refuses while artefacts
reference the device, and the artefacts of a failed onboarding are a commit,
a NetBox object and a credential override, cleared through three separate
mechanisms — one of them the provenance-based Remove, which had never
deleted an object it created. A refusal naming three manual steps is a dead
end with better signposting.

So the refusal became **the check that abandon worked** rather than an
obstacle: abandon removes the artefacts and then calls release, and release
**re-derives the references itself** instead of trusting the steps that ran.
The check and the work are deliberately different code.
"""

import os

import pytest


@pytest.fixture
def repo(tmp_path, monkeypatch):
    from modules.nsot import repo as _repo

    list_dir = tmp_path / "probe"
    repo_dir = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo_dir, "host_vars"), exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda k, d=None: {"nsot_git_author_name": "NMAS",
                                           "nsot_git_author_email": "n@l"}.get(k, d))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda c: None)
    monkeypatch.setattr("modules.credentials._FILE", str(tmp_path / "creds.json"))
    _repo.init_repo(repo_dir)
    return repo_dir


def _onboard(repo, name="bp1", ip="203.0.113.31"):
    """A device in the manifest with intent committed — phase 1's output."""
    from modules.nsot import manifest as _m
    from modules.nsot import repo as _repo
    from modules.nsot.repo import GoldenItem, adopt_identity

    # The real path: mint, then RECORD. `adopt_identity` persists nothing.
    identity = adopt_identity(repo, GoldenItem(name, "", ip))
    _m.upsert_device(repo, identity, name, mgmt_ip=ip, platform="cisco_iosxe")
    with open(os.path.join(repo, "host_vars", f"{name}.yml"), "w") as fh:
        fh.write(f"hostname: {name}\n")
    _repo.git(repo, "add", "-A")
    _repo.git(repo, "-c", "user.email=n@l", "-c", "user.name=N",
              "commit", "-m", f"onboarding: {name}")
    return identity


class TestReleaseRefusesWhileAnythingNamesIt:

    def test_it_refuses_with_the_intent_still_committed(self, repo):
        from modules.nsot import manifest as _m

        identity = _onboard(repo)
        out = _m.release(repo, identity, list_name="probe")
        assert out["ok"] is False
        kinds = {r["kind"] for r in out["references"]}
        assert "intent" in kinds, out["references"]
        assert "host_vars" in out["error"]

    def test_each_reference_says_how_to_clear_it(self, repo):
        """'You must clear these first' is actionable. A bare refusal is
        the same dead end in fewer words."""
        from modules.nsot import manifest as _m

        identity = _onboard(repo)
        for ref in _m.references(repo, identity, "probe"):
            assert ref["how_to_clear"], ref

    def test_it_releases_once_nothing_references_it(self, repo):
        """The control. A release that refused unconditionally would pass
        every test above and give no name back."""
        from modules.nsot import manifest as _m

        identity = _onboard(repo)
        os.remove(os.path.join(repo, "host_vars", "bp1.yml"))
        out = _m.release(repo, identity, list_name="probe")
        assert out["ok"] is True, out
        assert out["released"] == "bp1"
        assert _m.find_by_name(repo, "bp1") == (None, None)

    def test_an_unknown_identity_is_refused_not_ignored(self, repo):
        from modules.nsot import manifest as _m

        out = _m.release(repo, "uid:nope", list_name="probe")
        assert out["ok"] is False
        assert "no device" in out["error"]


class TestAbandonRunsTheSequenceInReverse:

    def _abandon(self, repo, **kw):
        from modules.nsot.onboard import abandon_onboarding

        kw.setdefault("remove_netbox",
                      lambda lst, host, dry_run=False: {"ok": True,
                                                        "deleted": [{"id": 9}],
                                                        "skipped": []})
        return abandon_onboarding(repo, "bp1", "probe", actor="t", **kw)

    def test_a_clean_abandon_gives_the_name_back(self, repo):
        from modules.nsot import manifest as _m

        _onboard(repo)
        out = self._abandon(repo)
        assert out["ok"] is True, out
        assert out["released"] == "bp1"
        assert _m.find_by_name(repo, "bp1") == (None, None)
        assert [s["step"] for s in out["steps"]] == list(
            __import__("modules.nsot.onboard", fromlist=["x"]).ABANDON_STEPS)

    def test_the_intent_removal_is_committed_not_just_deleted(self, repo):
        import subprocess

        _onboard(repo)
        self._abandon(repo)
        assert not os.path.exists(os.path.join(repo, "host_vars", "bp1.yml"))
        log = subprocess.run(["git", "-C", repo, "log", "--format=%s"],
                             capture_output=True, text=True).stdout
        assert "abandon: bp1" in log, log

    def test_the_credential_override_is_cleared(self, repo):
        import modules.credentials as creds

        _onboard(repo)
        creds.set_device_override("203.0.113.31", "admin", "s3cret", "s3cret")
        assert creds.has_device_override("203.0.113.31")
        self._abandon(repo)
        assert not creds.has_device_override("203.0.113.31")

    def test_a_dry_run_changes_nothing(self, repo):
        from modules.nsot import manifest as _m

        identity = _onboard(repo)
        out = self._abandon(repo, dry_run=True)
        assert os.path.exists(os.path.join(repo, "host_vars", "bp1.yml"))
        assert _m.find_by_name(repo, "bp1")[0] == identity
        assert out["dry_run"] is True


class TestAPartialAbandonNeverReportsSuccess:
    """The defect this whole flow is a response to."""

    def test_a_refused_netbox_step_fails_the_run(self, repo):
        from modules.nsot.onboard import abandon_onboarding

        _onboard(repo)
        out = abandon_onboarding(
            repo, "bp1", "probe",
            remove_netbox=lambda lst, host, dry_run=False: {
                "ok": False, "error": "NetBox writes are disabled"})
        assert out["ok"] is False
        assert any("disabled" in r["detail"] for r in out["remaining"])

    def test_the_name_is_NOT_released_when_netbox_refused(self, repo):
        """**The wrong-and-looks-right state, asserted.**

        Reporting a name reclaimed while a NetBox object still references it
        is the failure mode. It cannot happen because the reclaim is
        `release()`, which re-derives the references itself rather than
        trusting the steps that ran before it.
        """
        from modules.nsot import manifest as _m
        from modules.nsot.onboard import abandon_onboarding

        identity = _onboard(repo)
        # NetBox refuses AND the created record still names the device, so
        # release must find it.
        from modules import netbox_guard
        netbox_guard.record_created("probe", "dcim/devices", 9, "bp1")
        try:
            out = abandon_onboarding(
                repo, "bp1", "probe",
                remove_netbox=lambda lst, host, dry_run=False: {
                    "ok": False, "error": "refused"})
            assert out["ok"] is False
            assert out["released"] == ""
            assert _m.find_by_name(repo, "bp1")[0] == identity, \
                "the name was given back while NetBox still referenced it"
            assert any(r["kind"] == "netbox"
                       for r in _m.references(repo, identity, "probe"))
        finally:
            netbox_guard.forget_created("probe")

    def test_remaining_says_how_to_finish(self, repo):
        from modules.nsot.onboard import abandon_onboarding

        _onboard(repo)
        out = abandon_onboarding(
            repo, "bp1", "probe",
            remove_netbox=lambda lst, host, dry_run=False: {
                "ok": False, "error": "NetBox unreachable"})
        assert out["remaining"]
        for item in out["remaining"]:
            assert item["how_to_finish"], item

    def test_an_unknown_device_is_refused(self, repo):
        from modules.nsot.onboard import abandon_onboarding

        out = abandon_onboarding(repo, "never-existed", "probe")
        assert out["ok"] is False
        assert "no identity" in out["error"]
