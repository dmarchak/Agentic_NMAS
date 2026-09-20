"""nsot/render_artifact.py

The deployability gate.

A render is always previewable. It is **deployable** only when the tool can
account for every line of the device's configuration and the template governing
it has been approved against that device.

This is a structural refusal, not a warning. :class:`RenderArtifact` is frozen
and ``deployable`` is computed from the validation report at access time — there
is no field to set, so no code path can hand Phase 3c a deployable artifact for
a device whose config the parser does not fully model. Warnings get clicked
through at 11pm before a demo; a computed property does not.

**Secrets and the deploy path.** Everything this module renders for preview or
for ``intended/`` is **masked**. Masked output is therefore *never* a deploy
source. Phase 3c must re-render from the template with real secrets resolved in
memory at deploy time and must never read ``intended/``. Deploying the literal
mask string to a device is the failure mode this guards against, so
:func:`assert_no_mask` exists to be called on anything about to reach a device.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

#: What a masked secret renders as. Distinctive on purpose: it must be
#: impossible to mistake for a credential and trivial to detect.
MASK = "•" * 8

#: Any of these appearing in text bound for a device means a masked artifact
#: leaked into the deploy path.
MASK_MARKERS = (MASK, "••••", "<masked>", "<missing-secret:")


class MaskedContentError(RuntimeError):
    """Raised when masked content is found on a path that reaches a device."""


def contains_mask(text: str) -> bool:
    return any(marker in (text or "") for marker in MASK_MARKERS)


def assert_no_mask(text: str, context: str = "deploy") -> None:
    """Refuse masked content on a device-bound path.

    ``intended/`` is written masked, so it can never be a deploy source. Phase
    3c re-renders with real secrets; this is the backstop that catches it if
    someone wires 3c to the wrong input.
    """
    if contains_mask(text):
        raise MaskedContentError(
            f"masked content reached the {context} path — this artifact was "
            "rendered for preview and must never be deployed. Re-render from "
            "the template with secrets resolved at deploy time."
        )


# ---------------------------------------------------------------------------
# Unmodelled acknowledgement (the recorded escape hatch)
# ---------------------------------------------------------------------------

def unmodeled_lines(host_vars: dict) -> list:
    """Every line the parser did not model, device-wide, in a stable order."""
    lines = []
    for entry in (host_vars or {}).get("unmodeled", []):
        lines.append(entry["line"].rstrip())
        lines.extend(c.rstrip() for c in entry.get("children", []))
    for iface in (host_vars or {}).get("interfaces", []):
        lines.extend(l.rstrip() for l in iface.get("unmodeled", []))
    return sorted(lines)


def acknowledged_lines(host_vars: dict) -> list:
    """Lines an operator has explicitly acknowledged as unmodelled."""
    ack = (host_vars or {}).get("unmodeled_ack") or {}
    return sorted(l.rstrip() for l in (ack.get("lines") or []))


def acknowledgement_is_complete(host_vars: dict) -> bool:
    """True when the acknowledged set matches the unmodelled set **exactly**.

    Exact equality, not a superset: a newly appearing unmodelled line makes the
    sets differ and the block returns. Acknowledgement is content-bound and
    committed to git, so it is reviewable rather than click-through dismissible.
    """
    unmodeled = unmodeled_lines(host_vars)
    if not unmodeled:
        return True
    return acknowledged_lines(host_vars) == unmodeled


def acknowledgement_gap(host_vars: dict) -> dict:
    """What is missing from, or stale in, an acknowledgement."""
    unmodeled = set(unmodeled_lines(host_vars))
    acked = set(acknowledged_lines(host_vars))
    return {
        "unacknowledged": sorted(unmodeled - acked),
        "stale": sorted(acked - unmodeled),
        "complete": acknowledgement_is_complete(host_vars),
    }


# ---------------------------------------------------------------------------
# The artifact
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RenderArtifact:
    """A rendered config plus everything needed to decide if it may be deployed.

    Construct only through :func:`build_artifact`, which always runs the
    validator. ``deployable`` is a computed property with no backing field.
    """

    device: str
    platform: str
    template: str
    rendered_masked: str
    report: dict
    host_vars: dict
    template_approved: bool = False
    masked_refs: tuple = field(default_factory=tuple)

    # ── the gate ────────────────────────────────────────────────────────────

    @property
    def blocking_reasons(self) -> list:
        """Why this artifact may not be deployed. Empty means it may."""
        reasons = []
        report = self.report or {}

        gap = acknowledgement_gap(self.host_vars)
        if not gap["complete"]:
            count = len(gap["unacknowledged"])
            if count:
                reasons.append(
                    f"{count} unmodelled line(s) not acknowledged: "
                    + ", ".join(repr(l) for l in gap["unacknowledged"][:3])
                    + ("…" if count > 3 else ""))
            if gap["stale"]:
                reasons.append(
                    f"{len(gap['stale'])} acknowledged line(s) no longer present "
                    "— the acknowledgement is stale and must be re-made")

        if report.get("missing_from_render"):
            reasons.append(f"{report['missing_from_render']} line(s) the template "
                           "does not reproduce")
        if report.get("extra_in_render"):
            reasons.append(f"{report['extra_in_render']} line(s) the template "
                           "invents")
        if report.get("reordered_sections"):
            reasons.append(f"{report['reordered_sections']} section(s) reordered — "
                           "order is significant here")
        if not self.template_approved:
            reasons.append(f"template '{self.template}' is not approved for this device")
        return reasons

    @property
    def deployable(self) -> bool:
        """Computed. There is no field to set and no way to override."""
        return not self.blocking_reasons

    @property
    def complete(self) -> bool:
        """Every line accounted for, regardless of template approval."""
        return acknowledgement_is_complete(self.host_vars) and not (
            self.report.get("missing_from_render")
            or self.report.get("extra_in_render")
            or self.report.get("reordered_sections")
        )

    def summary(self) -> dict:
        """UI payload. Never contains a secret value — the render is masked."""
        gap = acknowledgement_gap(self.host_vars)
        return {
            "device": self.device,
            "platform": self.platform,
            "template": self.template,
            "deployable": self.deployable,
            "complete": self.complete,
            "template_approved": self.template_approved,
            "blocking_reasons": self.blocking_reasons,
            "unmodeled": unmodeled_lines(self.host_vars),
            "unacknowledged": gap["unacknowledged"],
            "stale_acknowledgements": gap["stale"],
            "masked_refs": list(self.masked_refs),
            "modeled_coverage": self.report.get("modeled_coverage", 0.0),
            "round_trip_fidelity": self.report.get("round_trip_fidelity", 0.0),
        }


def build_artifact(device: str, running_config: str, platform: str,
                   template: str = "", template_approved: bool = False,
                   host_vars: dict = None) -> RenderArtifact:
    """The only constructor. Always validates; always renders masked.

    *running_config* is a **captured** config — a golden file or a stored
    backup. Nothing here opens a session to a device.
    """
    from modules.nsot import roundtrip
    from modules.nsot.parsers import get_parser

    parser = get_parser(platform)
    parsed = host_vars if host_vars is not None else parser.parse(running_config)
    resolved_platform = parsed.get("platform", platform)

    masked_refs = tuple(sorted((parsed.get("secrets") or {}).keys()))

    # Validate against the TRUE render. Masking replaces every secret with a
    # placeholder, so comparing a masked render against the real config would
    # report each secret line as both missing and invented — a validation
    # result that says nothing about the template.
    #
    # The unmasked render is a local only: it is never stored on the artifact,
    # never returned, and never written to disk. `intended/` and the preview
    # both get the masked one.
    truthful = roundtrip.render(parsed, resolved_platform)
    report = roundtrip.compare(running_config, truthful, parsed)
    del truthful

    rendered = roundtrip.render(parsed, resolved_platform,
                                secret_lookup=lambda _name: MASK)

    return RenderArtifact(
        device=device or parsed.get("hostname", ""),
        platform=resolved_platform,
        template=template or f"{resolved_platform}/base.j2",
        rendered_masked=rendered,
        report=report,
        host_vars=parsed,
        template_approved=bool(template_approved),
        masked_refs=masked_refs,
    )


def host_vars_fingerprint(host_vars: dict) -> str:
    """Stable hash of a device's host_vars, for the approval binding fingerprint."""
    from modules.nsot.hostvars import to_yaml
    return hashlib.sha256(to_yaml(host_vars).encode("utf-8")).hexdigest()[:16]
