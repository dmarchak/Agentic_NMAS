"""Stage 4C.1 — the onboarding plan, and the gate on it.

`OnboardPlan` is frozen and `onboardable` is a **computed property**, for the
same reason `RenderArtifact.deployable` is: a caller that forgot to check
must not be able to produce a plan that claims to be safe. That exact shape
has already bitten once in this project — `build_artifact()` takes
`template_approved` as an ordinary argument defaulting to `False`, and a
route that never called `approval.is_approved()` produced a confident, wrong
sentence about a store nobody had consulted.

**Every refusal is collected, not the first.** The wizard runs once per
device, so a run that surfaces three problems is worth three runs that
surface one each.

Nothing here writes: `build_plan()` is pure computation over what the stores
already say, which is what makes every refusal visible before anything is
created.
"""

import os

import pytest


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A list with a repo, an approved template, and no devices."""
    from modules.nsot import repo as _repo

    list_dir = tmp_path / "probe"
    repo_dir = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo_dir, "golden"), exist_ok=True)

    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name",
                        lambda: "probe")
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda k, d=None: {"nsot_git_author_name": "NMAS",
                                           "nsot_git_author_email": "n@l"}.get(k, d))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda c: None)
    _repo.init_repo(repo_dir)

    # NetBox absent by default: a local list can be onboarded without it, and
    # "not configured" is a decision rather than a failed check.
    monkeypatch.setattr("modules.integrations.get_integration",
                        lambda name: None)
    # Approved template, unless a test says otherwise.
    monkeypatch.setattr("modules.nsot.approval.is_approved",
                        lambda repo, template, host_vars=None: True)
    return {"repo": repo_dir, "dir": list_dir}


def _plan(**over):
    from modules.nsot.onboard import build_plan

    args = dict(hostname="r6", platform="cisco_iosxe", list_name="probe",
                mgmt_ip="203.0.113.6", secret="bootstrap-only")
    args.update(over)
    return build_plan(**args)


class TestTheGateIsComputed:

    def test_a_clean_plan_is_onboardable(self, lab):
        plan = _plan()
        assert plan.onboardable is True, plan.blocking_reasons

    def test_onboardable_cannot_be_set(self, lab):
        """There is no field and no argument — the `deployable` lesson."""
        import dataclasses

        from modules.nsot.onboard import OnboardPlan

        fields = {f.name for f in dataclasses.fields(OnboardPlan)}
        assert "onboardable" not in fields

    def test_the_plan_is_frozen(self, lab):
        import dataclasses

        plan = _plan()
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.hostname = "something-else"

    def test_build_plan_is_the_only_constructor(self):
        """Anything else calling `OnboardPlan(...)` bypasses every check."""
        from tests.astcheck import calls_in

        from modules.nsot import onboard

        callers = [name for name in dir(onboard)
                   if callable(getattr(onboard, name, None))
                   and getattr(getattr(onboard, name), "__module__", "")
                   == onboard.__name__
                   and name != "build_plan"
                   and calls_in(getattr(onboard, name), "OnboardPlan")]
        assert callers == [], callers


class TestCollisionsAreRefusedInBothStores:
    """§4 step 2 of the onboarding doc: a collision in either is a refusal,
    not a warning."""

    def test_a_manifest_collision_refuses(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                            lambda repo, name: ("uid:x", {"name": name}))
        plan = _plan()
        assert plan.onboardable is False
        assert any("manifest" in r for r in plan.blocking_reasons)

    def test_a_netbox_collision_refuses(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.onboard._name_in_netbox",
                            lambda hostname: (True, True))
        plan = _plan()
        assert plan.onboardable is False
        assert any("already exists in NetBox" in r
                   for r in plan.blocking_reasons)

    def test_both_collisions_are_reported_together(self, lab, monkeypatch):
        """Told only one, an operator fixes one and runs again."""
        monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                            lambda repo, name: ("uid:x", {"name": name}))
        monkeypatch.setattr("modules.nsot.onboard._name_in_netbox",
                            lambda hostname: (True, True))
        reasons = _plan().blocking_reasons
        assert any("manifest" in r for r in reasons)
        assert any("NetBox" in r for r in reasons)

    def test_netbox_not_configured_is_not_a_collision(self, lab):
        """A local list can be onboarded without NetBox at all."""
        plan = _plan()
        assert plan.name_taken_in_netbox is False
        assert not any("NetBox" in r for r in plan.blocking_reasons)


class TestACheckThatDidNotRunHasNotPassed:
    """"NetBox says no such device" and "NetBox could not be reached" are
    different facts, and only one of them is evidence."""

    def test_an_unreachable_netbox_blocks(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.onboard._name_in_netbox",
                            lambda hostname: (False, False))
        plan = _plan()
        assert plan.onboardable is False
        assert any("did not run has not passed" in r
                   for r in plan.blocking_reasons)

    def test_an_unreadable_manifest_blocks(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                            lambda repo, name: (_ for _ in ()).throw(OSError("x")))
        plan = _plan()
        assert plan.onboardable is False
        assert any("manifest" in r and "did not run" in r
                   for r in plan.blocking_reasons)

    def test_a_netbox_error_is_not_read_as_absent(self, lab, monkeypatch):
        """The route returns `{"ok": False}` for both cases; the error text
        decides, and anything that is not a clean not-found leaves it unrun."""
        from modules.nsot import onboard

        class _Client:
            def is_configured(self):
                return True

        monkeypatch.setattr("modules.integrations.get_integration",
                            lambda name: _Client())
        monkeypatch.setattr("modules.netbox_client.netbox_get_device",
                            lambda name: {"ok": False, "error": "connection refused"})
        taken, checked = onboard._name_in_netbox("r6")
        assert (taken, checked) == (False, False)

    def test_a_clean_not_found_is_a_real_answer(self, lab, monkeypatch):
        from modules.nsot import onboard

        class _Client:
            def is_configured(self):
                return True

        monkeypatch.setattr("modules.integrations.get_integration",
                            lambda name: _Client())
        monkeypatch.setattr("modules.netbox_client.netbox_get_device",
                            lambda name: {"ok": False, "error": "Device not found"})
        assert onboard._name_in_netbox("r6") == (False, True)


class TestEveryReasonAtOnce:

    def test_three_problems_are_all_reported(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda repo, template, host_vars=None: False)
        reasons = _plan(hostname="9bad", mgmt_ip="").blocking_reasons
        assert any("usable device name" in r for r in reasons)
        assert any("management address" in r for r in reasons)
        assert any("not approved" in r for r in reasons)
        assert len(reasons) >= 3

    def test_an_unapproved_template_refuses_with_the_reason(self, lab,
                                                            monkeypatch):
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda repo, template, host_vars=None: False)
        plan = _plan()
        assert plan.onboardable is False
        assert any("not approved" in r for r in plan.blocking_reasons)

    def test_no_management_address_refuses(self, lab):
        """A device created and unreachable is worse than one not created."""
        assert any("management address" in r
                   for r in _plan(mgmt_ip="").blocking_reasons)


class TestThePlatformBlockedPendingStageD:
    """cisco_ios emits `crypto key generate rsa` into a console replay and
    whether that stalls is unmeasured. A stall leaves the device reachable by
    ping and not by SSH, so the wizard refuses rather than discovers."""

    def test_a_vios_target_is_refused(self, lab):
        plan = _plan(platform="cisco_ios")
        assert plan.onboardable is False
        assert any("stage D" in r for r in plan.blocking_reasons)

    def test_the_refusal_names_where_to_read_about_it(self, lab):
        reasons = _plan(platform="cisco_ios").blocking_reasons
        assert any("bootstrap-probe" in r for r in reasons)

    def test_the_c8000v_is_not_blocked(self, lab):
        """Measured: cisco_iosxe is in neither GENERATES_SSH_KEY nor
        CONSOLE_REPLAYED and emits no crypto line at all."""
        from modules.nsot.bootstrap_config import (CONSOLE_REPLAYED,
                                                   GENERATES_SSH_KEY)

        assert "cisco_iosxe" not in GENERATES_SSH_KEY
        assert "cisco_iosxe" not in CONSOLE_REPLAYED
        assert _plan().onboardable is True

    def test_the_block_list_is_keyed_on_the_measured_property(self):
        """If cisco_ios ever leaves both sets, this block is stale."""
        from modules.nsot.bootstrap_config import (CONSOLE_REPLAYED,
                                                   GENERATES_SSH_KEY)
        from modules.nsot.onboard import BLOCKED_PENDING_MEASUREMENT

        for platform in BLOCKED_PENDING_MEASUREMENT:
            assert platform in GENERATES_SSH_KEY and platform in CONSOLE_REPLAYED, (
                f"{platform} is blocked pending stage D but no longer emits a "
                "key into a console replay — the block measures nothing")


class TestTheAsciiGuardIsOnThisPath:
    """The bootstrap config reaches a device **without a deploy** — it is
    typed into a console at boot. A guard that lives only on the deploy path
    does not cover it, which is how an em dash in a comment hung a vIOS."""

    def test_a_non_ascii_value_refuses(self, lab):
        plan = _plan(domain="rcn—lab")
        assert plan.onboardable is False
        assert any("cannot accept" in r for r in plan.blocking_reasons)

    def test_the_generators_own_message_is_carried(self, lab):
        """Not a second scanner here. `render_bootstrap()` already ends with
        `assert_sendable()` over the whole artefact and raises with the
        command number, the codepoint and the column — a better message than
        a re-implementation, and one producer rather than two.

        What the plan adds is that it becomes a blocking REASON rather than
        an exception reaching the wizard.
        """
        plan = _plan(domain="rcn—lab")
        assert plan.unsendable
        text = plan.unsendable[0]
        assert "U+2014" in text and "column" in text

    def test_a_clean_config_has_none(self, lab):
        assert _plan().unsendable == ()


class TestTheSourceKindIsCarried:
    """Two quite different flows, and the difference is visible to the
    operator rather than smoothed over."""

    def test_a_local_list_writes_the_csv(self, lab):
        assert _plan().writes_devices_csv is True

    def test_a_netbox_list_does_not(self, lab):
        """Identity there is read-only; the device arrives on the next
        refresh, and the wizard must not pretend it wrote a row."""
        assert _plan(source_kind="netbox").writes_devices_csv is False


class TestThePlanCarriesNoSecret:
    """It is returned over HTTP and logged. A plan that carries the bootstrap
    credential would need every one of those paths to remember to redact."""

    def test_the_secret_is_not_a_field(self):
        import dataclasses

        from modules.nsot.onboard import OnboardPlan

        assert "secret" not in {f.name for f in dataclasses.fields(OnboardPlan)}

    def test_the_summary_does_not_carry_it(self, lab):
        summary = _plan(secret="s3cr3t-bootstrap").summary
        assert "s3cr3t-bootstrap" not in str(summary)

    def test_the_rendered_config_does_carry_it(self, lab):
        """It has to — that is the config the device boots with. The point is
        that the config is the ONE place it appears."""
        assert "s3cr3t-bootstrap" in _plan(secret="s3cr3t-bootstrap").bootstrap_config
