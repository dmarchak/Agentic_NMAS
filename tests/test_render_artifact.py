"""The deployability gate.

Two guarantees, both structural rather than procedural:

1. **A device with unmodelled constructs cannot reach a deployable render by
   any code path.** Not a warning — warnings get clicked through at 11pm before
   a demo. ``deployable`` is a computed property on a frozen dataclass, so there
   is no field to set.
2. **Masked content can never reach a device.** ``intended/`` and the preview
   are both rendered masked, which makes them permanently unsuitable as a
   deploy source. Phase 3c must re-render from the template with real secrets
   resolved in memory. Deploying the literal mask string is the failure mode.
"""

import dataclasses
import inspect
import os

import pytest

from modules.nsot import render_artifact as RA
from modules.nsot.parsers import get_parser
from modules.nsot.render_artifact import (
    MASK, MaskedContentError, RenderArtifact, assert_no_mask, build_artifact,
    contains_mask,
)

FLEET = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")


def _config(name):
    with open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8") as fh:
        return fh.read()


UNKNOWN = """quantum-tunnel profile ALPHA
 entanglement-mode paired
 peer 203.0.113.9
!
"""


@pytest.fixture
def clean():
    """A fully modelled device."""
    return build_artifact("s1", _config("s1"), "cisco_ios", template_approved=True)


@pytest.fixture
def dirty():
    """The same device plus a construct no parser models."""
    return build_artifact("s1", _config("s1") + UNKNOWN, "cisco_ios",
                          template_approved=True)


class TestStructuralImmutability:
    def test_artifact_is_frozen(self):
        assert RenderArtifact.__dataclass_params__.frozen is True

    def test_deployable_has_no_backing_field(self):
        names = {f.name for f in dataclasses.fields(RenderArtifact)}
        assert "deployable" not in names
        assert isinstance(RenderArtifact.deployable, property)

    def test_deployable_cannot_be_assigned(self, dirty):
        with pytest.raises(dataclasses.FrozenInstanceError):
            dirty.deployable = True

    def test_report_cannot_be_swapped(self, dirty):
        with pytest.raises(dataclasses.FrozenInstanceError):
            dirty.report = {"missing_from_render": 0}


class TestUnmodelledBlocksDeployment:
    def test_unmodelled_device_is_not_deployable(self, dirty):
        assert dirty.report["unmodeled"] > 0
        assert dirty.deployable is False

    def test_reason_names_the_unmodelled_lines(self, dirty):
        reasons = " ".join(dirty.blocking_reasons)
        assert "not acknowledged" in reasons
        assert "quantum-tunnel" in reasons

    def test_preview_still_renders(self, dirty):
        """Blocking deployment must not block inspection."""
        assert dirty.rendered_masked
        assert "quantum-tunnel profile ALPHA" in dirty.rendered_masked

    def test_clean_device_with_approval_is_deployable(self, clean):
        assert clean.blocking_reasons == []
        assert clean.deployable is True

    def test_unapproved_template_blocks_a_clean_device(self):
        artifact = build_artifact("s1", _config("s1"), "cisco_ios")
        assert artifact.complete is True
        assert artifact.deployable is False
        assert any("not approved" in r for r in artifact.blocking_reasons)

    @pytest.mark.parametrize("field,value", [
        ("missing_from_render", 1), ("extra_in_render", 1), ("reordered_sections", 1),
    ])
    def test_any_validation_failure_blocks(self, clean, field, value):
        broken = RenderArtifact(
            device=clean.device, platform=clean.platform, template=clean.template,
            rendered_masked=clean.rendered_masked,
            report={**clean.report, field: value},
            host_vars=clean.host_vars, template_approved=True)
        assert broken.deployable is False


class TestNoPathToDeployable:
    """The surface test: every public constructor routes through build_artifact."""

    def test_build_artifact_is_the_only_constructor(self):
        constructors = [
            name for name, obj in inspect.getmembers(RA, inspect.isfunction)
            if not name.startswith("_")
            and inspect.signature(obj).return_annotation is RenderArtifact
        ]
        assert constructors == ["build_artifact"], (
            f"another public function returns a RenderArtifact: {constructors}")

    def test_build_artifact_always_validates(self):
        """It cannot be told to skip validation."""
        params = inspect.signature(build_artifact).parameters
        for skip in ("skip_validation", "validate", "force", "deployable"):
            assert skip not in params, f"build_artifact accepts {skip!r}"

    def test_routes_expose_no_deploy_action(self):
        """3b renders and previews. Deploy is 3c and lives elsewhere."""
        import routes.templates as R
        source = inspect.getsource(R)
        for forbidden in ("send_config_set", "ConnectHandler", "deploy(",
                          "push_config", "write_memory"):
            assert forbidden not in source, f"3b route module references {forbidden}"

    def test_every_fleet_device_needs_approval_to_deploy(self):
        for name in ("r1", "r3", "s1", "s4"):
            platform = "cisco_xe" if name.startswith("r") else "cisco_ios"
            assert build_artifact(name, _config(name), platform).deployable is False


class TestMaskNeverReachesDeploy:
    def test_render_is_masked(self, clean):
        assert contains_mask(clean.rendered_masked)

    def test_real_secret_is_absent_from_the_render(self, clean):
        for value in (clean.host_vars.get("secrets") or {}).values():
            assert value not in clean.rendered_masked, \
                "a real secret value reached the masked render"

    def test_masked_render_is_refused_on_a_deploy_path(self, clean):
        with pytest.raises(MaskedContentError):
            assert_no_mask(clean.rendered_masked, context="deploy")

    def test_guard_names_the_remedy(self, clean):
        with pytest.raises(MaskedContentError) as exc:
            assert_no_mask(clean.rendered_masked)
        assert "re-render" in str(exc.value).lower()

    def test_unmasked_render_passes_the_guard(self, clean):
        """A genuine deploy render, with real secrets, must not be blocked."""
        from modules.nsot import roundtrip
        truthful = roundtrip.render(clean.host_vars, clean.platform)
        assert_no_mask(truthful, context="deploy")

    @pytest.mark.parametrize("marker", list(RA.MASK_MARKERS))
    def test_every_marker_is_detected(self, marker):
        assert contains_mask(f"ntp server {marker}\n")
        with pytest.raises(MaskedContentError):
            assert_no_mask(f"snmp-server community {marker} RO")

    def test_artifact_exposes_no_unmasked_render(self):
        """The truthful render is a local inside build_artifact, never a field."""
        names = {f.name for f in dataclasses.fields(RenderArtifact)}
        assert "rendered" not in names
        assert "rendered_unmasked" not in names
        assert "rendered_masked" in names

    def test_summary_carries_no_secret_values(self, clean):
        import json
        blob = json.dumps(clean.summary())
        for value in (clean.host_vars.get("secrets") or {}).values():
            assert value not in blob


class TestValidationUsesTheTruthfulRender:
    """Masking must not distort the report it is measured against."""

    def test_clean_device_reports_no_discrepancy(self, clean):
        assert clean.report["missing_from_render"] == 0
        assert clean.report["extra_in_render"] == 0

    def test_secret_lines_are_not_reported_as_churn(self, clean):
        """Comparing a masked render would show each secret as missing+extra."""
        assert clean.report["round_trip_fidelity"] == 100.0


class TestUnmodeledAcknowledgement:
    """The recorded escape hatch: content-bound, committed, not dismissible."""

    def _acked(self, extra_lines=None, lines=None):
        parsed = get_parser("cisco_ios").parse(_config("s1") + UNKNOWN)
        unmodeled = RA.unmodeled_lines(parsed)
        parsed["unmodeled_ack"] = {
            "lines": lines if lines is not None else list(unmodeled) + (extra_lines or []),
            "actor": "dustin", "acknowledged_at": "2026-09-20T12:00:00Z"}
        return build_artifact("s1", _config("s1") + UNKNOWN, "cisco_ios",
                              template_approved=True, host_vars=parsed)

    def test_exact_acknowledgement_unblocks(self):
        assert self._acked().deployable is True

    def test_partial_acknowledgement_does_not_unblock(self):
        parsed = get_parser("cisco_ios").parse(_config("s1") + UNKNOWN)
        parsed["unmodeled_ack"] = {"lines": ["quantum-tunnel profile ALPHA"],
                                   "actor": "dustin"}
        artifact = build_artifact("s1", _config("s1") + UNKNOWN, "cisco_ios",
                                  template_approved=True, host_vars=parsed)
        assert artifact.deployable is False
        assert "not acknowledged" in " ".join(artifact.blocking_reasons)

    def test_a_new_unmodelled_line_reinstates_the_block(self):
        """An acknowledgement is bound to content, not to a click."""
        parsed = get_parser("cisco_ios").parse(_config("s1") + UNKNOWN)
        parsed["unmodeled_ack"] = {"lines": RA.unmodeled_lines(parsed),
                                   "actor": "dustin"}
        approved = build_artifact("s1", _config("s1") + UNKNOWN, "cisco_ios",
                                  template_approved=True, host_vars=parsed)
        assert approved.deployable is True

        # A new unfamiliar construct appears on the device.
        grown = get_parser("cisco_ios").parse(
            _config("s1") + UNKNOWN + "flux-capacitor enable 1.21\n")
        grown["unmodeled_ack"] = parsed["unmodeled_ack"]      # the OLD ack
        artifact = build_artifact("s1", _config("s1") + UNKNOWN +
                                  "flux-capacitor enable 1.21\n", "cisco_ios",
                                  template_approved=True, host_vars=grown)
        assert artifact.deployable is False
        assert "flux-capacitor" in " ".join(artifact.blocking_reasons)

    def test_stale_acknowledgement_blocks(self):
        """Acknowledging a line that is no longer there is not a free pass."""
        artifact = self._acked(extra_lines=["some line that was removed"])
        assert artifact.deployable is False
        assert any("stale" in r for r in artifact.blocking_reasons)

    def test_acknowledgement_is_exact_not_superset(self):
        gap = RA.acknowledgement_gap({
            "unmodeled": [{"line": "a", "children": []}],
            "interfaces": [],
            "unmodeled_ack": {"lines": ["a", "b"]}})
        assert gap["complete"] is False
        assert gap["stale"] == ["b"]

    def test_no_unmodelled_needs_no_acknowledgement(self, clean):
        assert RA.acknowledgement_is_complete(clean.host_vars) is True

    def test_acknowledgement_survives_yaml(self):
        """It is committed to git, so it must round-trip through host_vars."""
        from modules.nsot import hostvars
        parsed = get_parser("cisco_ios").parse(_config("s1") + UNKNOWN)
        parsed["unmodeled_ack"] = {"lines": RA.unmodeled_lines(parsed),
                                   "actor": "dustin",
                                   "acknowledged_at": "2026-09-20T12:00:00Z"}
        restored = hostvars.from_yaml(hostvars.to_yaml(parsed))
        assert restored["unmodeled_ack"]["actor"] == "dustin"
        assert RA.acknowledgement_is_complete(restored) is True
