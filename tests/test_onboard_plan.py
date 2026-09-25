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

from modules.settings_schema import DEFAULTS as _SCHEMA_DEFAULTS


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
                                           "nsot_git_author_email": "n@l",
                                           # P.1: onboarding gives every device the syslog block.
                                           "syslog_host": "192.0.2.10"}.get(
                                               k, _SCHEMA_DEFAULTS.get(k, d)))
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

    # `mgmt_mask` and `manager_interface` are required as of 4C.8: an
    # address with no mask and no interface cannot be emitted into a config,
    # so a plan carrying one is not onboardable. Supplied here so the tests
    # below exercise the reason they are each about.
    args = dict(hostname="r6", platform="cisco_iosxe", list_name="probe",
                mgmt_ip="203.0.113.6", mgmt_mask="255.255.255.0",
                manager_interface="GigabitEthernet2",
                secret="bootstrap-only")
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

    def test_three_problems_are_all_reported(self, lab):
        """Three GENUINE blockers.

        This used an unapproved template as its third, which 4C.8 demoted to
        an advisory — the artefact is `render_bootstrap()`'s output and no
        step of the run reads the template. The property under test is "every
        reason at once", not "these three reasons", so it keeps its meaning
        with a real third blocker and would have lost it with a note dressed
        as one.
        """
        reasons = _plan(hostname="9bad", mgmt_ip="",
                        platform="cisco_ios").blocking_reasons
        assert any("usable device name" in r for r in reasons)
        assert any("management address" in r for r in reasons)
        assert any("cannot be onboarded" in r for r in reasons)   # stage D
        assert len(reasons) >= 3

    # `test_an_unapproved_template_refuses_with_the_reason` was REMOVED in
    # 4C.8 and its removal is pinned by
    # `TestTemplateStateIsAnAdvisoryNotARefusal` below: the refusal it
    # asserted could not be satisfied by any first device, because
    # `approval.approve()` correctly refuses an empty device set.

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

    def test_onboarding_writes_no_csv_row_on_either_kind(self, lab):
        """This asserted `True` for a local list while **no step wrote a
        row**. The property it named was never true; what made it look true
        was that nothing checked the other end.

        The row is written by `promote_device()`, when the device has
        answered. A device in the inventory is one the tool will poll, back
        up, drift-check and offer in bulk ops, and one that has never
        answered reads as unreachable in nine places and means nothing in
        any of them.
        """
        assert _plan().writes_devices_csv is False
        assert _plan(source_kind="netbox").writes_devices_csv is False

    def test_the_review_says_when_the_row_appears(self, lab):
        """Not nothing, and not "no" — the sentence that is true."""
        assert "after it answers" in _plan().inventory_note

    def test_a_netbox_list_says_why_it_differs(self, lab):
        """Identity there is read-only; the device arrives on the next
        refresh, and the wizard must not pretend it wrote a row."""
        note = _plan(source_kind="netbox").inventory_note
        assert "read-only" in note and "refresh" in note


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


class TestPreconditionsAreFoundAtPlanTime:
    """The review screen promises *"nothing has been created yet"*.
    Discovering that NetBox writes are disabled **after** the credential has
    been bound breaks that promise, and leaves a partial state the operator
    never agreed to. So anything the run requires is checked before anything
    is offered.

    **These tests exist because a negative control found they did not.**
    Removing the precondition from `build_plan` changed nothing in this file
    — the check was written and unexercised, which is the same shape as the
    slug/dialect gate one layer along: present, correct, and proving nothing.
    """

    def test_the_write_gate_being_off_is_a_blocking_reason(self, lab,
                                                           monkeypatch):
        monkeypatch.setattr("modules.netbox_guard.writes_allowed",
                            lambda: False)
        plan = _plan(netbox_plan=("dcim/devices/",))
        assert plan.onboardable is False
        assert any("NetBox writes are disabled" in r
                   for r in plan.blocking_reasons)

    def test_it_says_the_wizard_will_not_turn_it_on(self, lab, monkeypatch):
        """A switch flipped as a side effect of confirming something else is
        not a decision anybody made — the same defect as a push exceeding its
        preview."""
        monkeypatch.setattr("modules.netbox_guard.writes_allowed",
                            lambda: False)
        reasons = _plan(netbox_plan=("dcim/devices/",)).blocking_reasons
        assert any("will not turn it on for you" in r for r in reasons)

    def test_with_writes_enabled_it_is_not_a_blocker(self, lab, monkeypatch):
        monkeypatch.setattr("modules.netbox_guard.writes_allowed",
                            lambda: True)
        plan = _plan(netbox_plan=("dcim/devices/",))
        assert not any("NetBox writes" in r for r in plan.blocking_reasons)

    def test_a_plan_that_creates_nothing_in_netbox_needs_no_switch(self, lab,
                                                                   monkeypatch):
        """A precondition that fires when it does not apply is a refusal
        people learn to ignore."""
        monkeypatch.setattr("modules.netbox_guard.writes_allowed",
                            lambda: False)
        plan = _plan()                       # no netbox_plan
        assert not any("NetBox writes" in r for r in plan.blocking_reasons)

    def test_an_unreadable_gate_blocks_rather_than_assuming(self, lab,
                                                            monkeypatch):
        monkeypatch.setattr("modules.netbox_guard.writes_allowed",
                            lambda: (_ for _ in ()).throw(OSError("x")))
        reasons = _plan(netbox_plan=("dcim/devices/",)).blocking_reasons
        assert any("did not run has not passed" in r for r in reasons)

    def test_the_reason_reaches_the_review_screen(self, lab, monkeypatch):
        """Named on screen, not only in the object — `blocking_reasons` is
        what `onboardReviewHtml` renders, and it renders all of them."""
        monkeypatch.setattr("modules.netbox_guard.writes_allowed",
                            lambda: False)
        summary = _plan(netbox_plan=("dcim/devices/",)).summary
        assert any("NetBox writes are disabled" in r
                   for r in summary["blocking_reasons"])


class TestTemplateStateIsAnAdvisoryNotARefusal:
    """4C.8. The gate was keyed on a property the artefact does not depend on.

    `run_onboarding`'s four steps are credentials, netbox, commit, render, and
    `render_step` returns `plan.bootstrap_config` -- `render_bootstrap()`'s
    output. **No step reads `plan.template`.** The Phase 3c rule generalised:
    gate on what the artefact actually depends on.

    And the gate could not be satisfied by any first device. `approve()`
    refuses an empty device set, correctly, so a fresh list cannot approve a
    template, cannot therefore onboard, and cannot therefore acquire the
    device the approval needs. **The wizard could not onboard the first
    device of a network.** Only a genuinely fresh list exposes it: a probe
    run against a list that already had nine devices and an approved
    template would have sailed past.
    """

    def test_an_unapproved_template_does_not_block(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda repo, template, host_vars=None: False)
        plan = _plan()
        assert plan.onboardable is True, plan.blocking_reasons
        assert not any("approved" in r for r in plan.blocking_reasons)

    def test_it_is_said_instead(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda repo, template, host_vars=None: False)
        notes = _plan().advisories
        assert notes, "an unapproved template must still be reported"
        text = " ".join(notes)
        # A next step, not a warning about nothing: it names the template,
        # the list, what cannot be done, and what to do about it.
        assert "cannot deploy" in text
        assert "capture" in text
        assert _plan().template in text

    def test_an_approved_template_says_nothing(self, lab):
        """Otherwise the panel carries a note on every run and is skipped."""
        assert _plan().advisories == []

    def test_a_real_blocker_still_blocks_alongside_an_advisory(
            self, lab, monkeypatch):
        """**The control that matters.**

        An advisory list that can swallow a refusal is the failure mode of
        this change. So: an unapproved template AND a genuine blocker, and
        the genuine one must still be a blocker and still refuse.
        """
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda repo, template, host_vars=None: False)
        plan = _plan(mgmt_ip="")

        assert plan.advisories, "the advisory vanished"
        assert plan.onboardable is False, "a real blocker was swallowed"
        assert any("management address" in r for r in plan.blocking_reasons)
        # And the two never merge.
        assert not set(plan.advisories) & set(plan.blocking_reasons)

    def test_the_two_lists_are_separate_in_the_summary(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.approval.is_approved",
                            lambda repo, template, host_vars=None: False)
        summary = _plan().summary
        assert summary["advisories"], summary
        assert summary["blocking_reasons"] == []
        assert summary["onboardable"] is True

    def test_no_step_of_the_run_reads_the_template(self):
        """The reason this is an advisory, asserted rather than asserted-in-
        prose. Parsed, not grepped: the docstrings above name `template`
        repeatedly to explain why it is not used."""
        import ast
        import inspect

        from modules.nsot import onboard as mod

        for name in ("bind_credentials_step", "commit_step", "render_step"):
            fn = getattr(mod, name)
            tree = ast.parse(inspect.getsource(fn).lstrip())
            attrs = {n.attr for n in ast.walk(tree)
                     if isinstance(n, ast.Attribute)}
            assert "template" not in attrs, (
                f"{name} reads plan.template — the gate may belong after all")
            assert "template_approved" not in attrs, name


class TestOnboardingGivesEveryDeviceTheSyslogBlock:
    """NSOT_PLAN P.1: the block is part of the baseline intent, so a device
    cannot be onboarded silent -- which is how r6 came to have no logging."""

    def test_the_plan_carries_the_whole_block(self, lab):
        from modules.nsot import hostvars

        plan = _plan()
        block = plan.host_vars["logging"]["syslog"]
        assert block == {"trap": "notifications", "origin_id": "hostname",
                         "source_interface": "Loopback0",
                         "hosts": ["192.0.2.10"], "heartbeat": 300}
        assert hostvars.syslog_block_problems(plan.host_vars) == []

    def test_no_syslog_host_is_a_named_refusal(self, lab, monkeypatch):
        import modules.settings_schema as ss

        real = ss.get_setting
        monkeypatch.setattr(ss, "get_setting", lambda k, *a, **kw: (
            "" if k == "syslog_host" else real(k, *a, **kw)))
        plan = _plan()
        assert not plan.onboardable
        assert any("syslog_host is not configured" in r
                   for r in plan.blocking_reasons), plan.blocking_reasons
        assert "syslog" not in (plan.host_vars.get("logging") or {})

    def test_an_authors_own_block_is_never_overwritten(self, lab):
        own = {"trap": "informational", "origin_id": "hostname",
               "source_interface": "Loopback1", "hosts": ["192.0.2.99"],
               "heartbeat": 600}
        plan = _plan(host_vars={"logging": {"syslog": own}})
        assert plan.host_vars["logging"]["syslog"] == own
        assert plan.onboardable, plan.blocking_reasons

    def test_the_block_reaches_the_committed_intent(self, lab):
        """Carried, not only computed: the commit writes what the plan holds."""
        import os

        from modules.config import get_list_data_dir
        from modules.nsot import hostvars
        from modules.nsot.onboard import commit_step

        plan = _plan()
        commit_step(plan, actor="t@example.com")
        repo = os.path.join(get_list_data_dir("probe"), "config_repo")
        committed = hostvars.read_committed(repo, "r6")
        assert committed["logging"]["syslog"]["heartbeat"] == 300
        assert committed["logging"]["syslog"]["hosts"] == ["192.0.2.10"]
