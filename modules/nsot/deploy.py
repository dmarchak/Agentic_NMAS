"""nsot/deploy.py

The Phase 3c deploy contract.

Everything Phase 3b promised, enforced here at the boundary where a socket is
about to open:

* **Re-render from the template with real secrets in memory.** ``intended/`` is
  written masked and is therefore never a deploy source; this module never
  opens it.
* **``assert_no_mask()`` before the socket**, not after. A masked push that
  fails halfway is worse than one that never starts.
* **Refuse any artifact whose ``deployable`` is False.** That property is
  computed on a frozen dataclass, so there is nothing to override here either.

Deploys are **merge-only**. Lines present in the intended config and absent from
the device are pushed. Lines present on the device and absent from the intended
config are reported as **removal warnings** and never negated — no ``no``
command is generated anywhere in this module. ``configure replace`` is a
documented future option, not built.
"""

import logging

from modules.nsot.render_artifact import assert_no_mask

log = logging.getLogger(__name__)


class DeployRefused(RuntimeError):
    """Raised when the 3b contract refuses an artifact before any connection."""


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------

def render_for_deploy(host_vars: dict, platform: str, template_root: str = None,
                      template_name: str = "base.j2") -> str:
    """Render with **real** secrets, resolved in memory.

    Deliberately not reading ``intended/``: that file is written masked for
    display, so using it as a deploy source would push ``••••••••`` to a device.
    """
    from modules.nsot import roundtrip

    def _resolve(name: str) -> str:
        from modules.credentials import get_template_secret
        stored = get_template_secret(name)
        if stored:
            return stored
        # Fall back to the value the extractor captured — for a hashed secret
        # that IS the value, and it can never be re-derived.
        return (host_vars.get("secrets") or {}).get(name, "")

    kwargs = {"secret_lookup": _resolve, "template_name": template_name}
    if template_root:
        kwargs["template_root"] = template_root
    return roundtrip.render(host_vars, platform, **kwargs)


def assert_deployable(artifact) -> None:
    """Refuse a non-deployable artifact. Called before anything connects."""
    if not artifact.deployable:
        raise DeployRefused(
            f"{artifact.device} is not deployable: "
            + "; ".join(artifact.blocking_reasons))


def prepare_device(artifact, template_root: str = None) -> dict:
    """Produce the deploy-ready config for one device.

    Order matters and is asserted by tests: refuse → render with real secrets →
    mask check → only then may a caller open a socket.
    """
    assert_deployable(artifact)

    template_name = (artifact.template or "base.j2").split("/")[-1]
    config = render_for_deploy(artifact.host_vars, artifact.platform,
                               template_root=template_root,
                               template_name=template_name)

    # The backstop. If a secret failed to resolve, the renderer emits a
    # placeholder and this catches it before it reaches a device.
    assert_no_mask(config, context="deploy")

    return {"device": artifact.device, "platform": artifact.platform,
            "config": config, "template": artifact.template}


# ---------------------------------------------------------------------------
# Merge-only diff
# ---------------------------------------------------------------------------

def merge_diff(intended_config: str, running_config: str) -> dict:
    """Lines to add, and lines present only on the device.

    Returns ``{"to_add", "removal_warnings", "unchanged_count"}``. Nothing in
    here generates a ``no`` command: removals are reported for a human to act
    on, never performed.
    """
    from modules.nsot import ifnames, normalize

    def _norm(text):
        return [ifnames.canonicalise_line(l.rstrip())
                for l in normalize.strip_for_roundtrip(text)]

    intended = _norm(intended_config)
    running = _norm(running_config)
    running_set = set(running)
    intended_set = set(intended)

    to_add = [l for l in intended if l not in running_set]
    # Section headers whose children are all present are not "additions".
    removal_warnings = [l for l in running
                        if l not in intended_set and l.strip() not in ("!", "end")]

    return {
        "to_add": to_add,
        "removal_warnings": removal_warnings,
        "unchanged_count": len(intended) - len(to_add),
    }


class NegationSynthesised(RuntimeError):
    """Raised if a command to push did not come from the intended config."""


def assert_merge_only(to_push: list, intended_config: str) -> None:
    """Every pushed command must appear verbatim in the intended config.

    Merge-only does not mean "no ``no`` commands": an operator's template may
    legitimately contain ``no ip http server``, which is real configuration.
    It means this tool never *synthesises* one to remove something the template
    does not mention.

    Checking provenance rather than grepping for ``no`` is what makes that
    distinction enforceable — a synthesised negation is by definition absent
    from the intended config, whatever it looks like.
    """
    from modules.nsot import ifnames, normalize

    allowed = {ifnames.canonicalise_line(l.rstrip())
               for l in normalize.strip_for_roundtrip(intended_config)}
    invented = [c for c in to_push
                if ifnames.canonicalise_line(c.rstrip()) not in allowed]
    if invented:
        raise NegationSynthesised(
            "refusing to push %d command(s) that are not in the intended "
            "config: %s" % (len(invented), ", ".join(repr(c) for c in invented[:5])))


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def transport_for(platform_slug: str) -> str:
    """Resolve the deploy transport for a platform. Never guesses.

    The previous behaviour gated NETCONF on one **global** setting and fell back
    to SSH only *after* a failed attempt. On a nine-device batch containing
    vIOS-L2 — which has no NETCONF at all — that is nine socket timeouts before
    anything happens, and a deploy that looks hung.

    The platform map decides, per device. The global setting survives only as a
    master off-switch: it can disable NETCONF everywhere, never enable it on a
    platform that does not support it.
    """
    from modules.settings_schema import get_setting

    entry = (get_setting("platform_map", {}) or {}).get(platform_slug, {})
    if not entry.get("supports_netconf", False):
        return "ssh"
    if entry.get("deploy_transport", "ssh") != "netconf":
        return "ssh"
    try:
        from modules.config import get_user_setting
        if not get_user_setting("netconf_enabled", False):
            return "ssh"
    except Exception:                          # noqa: BLE001
        return "ssh"
    return "netconf"


# ---------------------------------------------------------------------------
# Batch control
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Stop attempting after N verify failures.

    Distinct from drift. One drifted device means someone touched a box, and
    the batch carries on without it. Repeated *verify* failures mean something
    systemic — a bad template, a broken assumption — and continuing turns one
    mistake into nine.
    """

    def __init__(self, limit: int = None):
        if limit is None:
            from modules.settings_schema import get_setting
            limit = get_setting("deploy_verify_failure_limit", 2)
        self.limit = max(1, int(limit))
        self.verify_failures = 0
        self.tripped_after = None

    def record_verify_failure(self, device: str) -> bool:
        self.verify_failures += 1
        if self.verify_failures >= self.limit and self.tripped_after is None:
            self.tripped_after = device
            log.error("deploy: circuit breaker tripped after %d verify failure(s) "
                      "(last: %s) — remaining devices will not be attempted",
                      self.verify_failures, device)
        return self.is_tripped

    @property
    def is_tripped(self) -> bool:
        return self.tripped_after is not None

    def reason(self) -> str:
        return (f"not attempted — stopped after {self.verify_failures} verify "
                f"failure(s), last on {self.tripped_after}")


def max_workers() -> int:
    """Deploy concurrency. Sequential by default.

    vIOS-L2 has limited vty lines, and Oxidized, the drift checker, the ping
    worker and a nine-device batch can all want the same device at once.
    """
    from modules.settings_schema import get_setting
    try:
        return max(1, min(16, int(get_setting("deploy_max_workers", 1))))
    except (TypeError, ValueError):
        return 1
