"""onboard.py — the plan for bringing a device that does not exist yet.

Stage 4C.1. **The plan object only.** Nothing here writes to NetBox, to git,
to the credential store or to a device; `build_plan()` is pure computation
over what the stores already say, and every refusal is visible before anything
is created.

Modelled on :mod:`modules.nsot.render_artifact`, deliberately and closely,
because the lesson it encodes applies here unchanged:

**`onboardable` is a computed property on a frozen dataclass.** There is no
field to set and no argument to pass. A caller that forgot to check cannot
produce a plan that claims to be safe, which is the whole reason
`build_artifact()` is the only constructor of a `RenderArtifact` — and the
reason `template_approved` defaulting to `False` was able to produce a
confident, wrong sentence about an approval store nobody had consulted.

**Every refusal is collected, not the first.** An operator who fixes one
blocker and is handed the next has to run the wizard once per problem. The
wizard is the least-used path in the program by definition — it runs once per
device — so the run that surfaces three problems at once is worth more than
three runs that surface one each.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

#: Platforms whose onboarding is blocked pending a measurement.
#:
#: `cisco_ios` is in both `GENERATES_SSH_KEY` and `CONSOLE_REPLAYED`, so its
#: bootstrap config emits `crypto key generate rsa modulus 2048` into a file
#: vrnetlab TYPES into a console line by line. Whether key generation stalls
#: that replay is **unmeasured** — stage D, `docs/bootstrap-probe/README.md`.
#:
#: What a stall costs is not a broken-looking device: the crypto line is
#: number 17 of 25, and the eight after it are `ip ssh version 2` and the
#: whole `line vty` block. A stalled node reaches `Startup complete`, answers
#: ping, and cannot be reached over SSH.
#:
#: So the wizard refuses rather than discovers. `cisco_iosxe` is in neither
#: set and emits no crypto line at all, which is why r6 is not blocked.
BLOCKED_PENDING_MEASUREMENT = {
    "cisco_ios": ("stage D has not been run: on this platform the bootstrap "
                  "config generates an SSH key inside a console replay, and "
                  "whether that stalls the replay is unmeasured. A stall "
                  "leaves the device reachable by ping and not by SSH. See "
                  "docs/bootstrap-probe/README.md."),
}

#: A hostname a device can actually carry, and a filename the repo can hold.
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,62}$")


@dataclass(frozen=True)
class OnboardPlan:
    """Everything the wizard would create, and every reason it may not.

    Frozen, and `onboardable` is computed. :func:`build_plan` is the only
    constructor and always validates.
    """

    hostname: str
    platform: str
    list_name: str
    #: ``local`` or ``netbox``. Two quite different flows, and the difference
    #: is carried rather than smoothed over: on a NetBox-sourced list identity
    #: is read-only and the device arrives on the next refresh, so the wizard
    #: must not pretend it wrote one.
    source_kind: str = "local"
    mgmt_ip: str = ""

    #: The startup config the new node boots from. Rendered here so the
    #: review step shows what will be created, not a description of it.
    bootstrap_config: str = ""

    #: Where the credential came from, per the existing resolution order.
    #: Displayed, because `_cred_source` exists so the origin is visible.
    cred_source: str = ""

    #: What would be created in NetBox, for the preview. Not executed here.
    netbox_plan: tuple = field(default_factory=tuple)

    #: The device's initial committed intent.
    host_vars: dict = field(default_factory=dict)

    template: str = ""
    template_approved: bool = False

    #: Collisions, as found. Each is fatal; both are reported.
    name_taken_in_manifest: bool = False
    name_taken_in_netbox: bool = False

    #: Lines of `bootstrap_config` an IOS CLI cannot accept.
    unsendable: tuple = field(default_factory=tuple)

    #: Set when the stores could not be consulted. **Not** the same as "no
    #: collision": a check that could not run has not passed.
    unchecked: tuple = field(default_factory=tuple)

    # ── the gate ────────────────────────────────────────────────────────────

    @property
    def blocking_reasons(self) -> list:
        """Why this device may not be onboarded. Empty means it may.

        Every reason, every time. The wizard runs once per device, so a run
        that surfaces three problems is worth three runs that surface one.
        """
        reasons = []

        if not _NAME.match(self.hostname or ""):
            reasons.append(
                f"{self.hostname!r} is not a usable device name — it must "
                "start with a letter and contain only letters, digits, dot, "
                "dash or underscore")

        blocked = BLOCKED_PENDING_MEASUREMENT.get(self.platform)
        if blocked:
            reasons.append(f"platform '{self.platform}' cannot be onboarded: "
                           + blocked)
        elif not self.platform:
            reasons.append("no platform selected — the bootstrap config, the "
                           "template and the transport all depend on it")

        # Both, not the first. A name free in NetBox and taken in the manifest
        # is a different problem from the reverse, and an operator who is told
        # only one of them fixes one and runs again.
        if self.name_taken_in_manifest:
            reasons.append(f"'{self.hostname}' already has an identity in this "
                           "list's manifest")
        if self.name_taken_in_netbox:
            reasons.append(f"'{self.hostname}' already exists in NetBox")

        if not self.mgmt_ip:
            reasons.append("no management address — the device would be "
                           "created and unreachable")

        if self.template and not self.template_approved:
            reasons.append(f"template '{self.template}' is not approved for "
                           f"platform '{self.platform}'")
        elif not self.template:
            reasons.append(f"no template is bound for platform "
                           f"'{self.platform}'")

        if self.unsendable:
            reasons.append(
                f"{len(self.unsendable)} line(s) of the bootstrap config "
                "contain characters an IOS CLI cannot accept: "
                + "; ".join(self.unsendable[:2])
                + ("…" if len(self.unsendable) > 2 else ""))

        # A check that could not run has not passed. Reported as its own
        # refusal rather than folded into the collision flags, because
        # "NetBox says no such device" and "NetBox could not be reached" are
        # different facts and only one of them is evidence.
        for what in self.unchecked:
            reasons.append(f"could not verify {what} — a check that did not "
                           "run has not passed")

        return reasons

    @property
    def onboardable(self) -> bool:
        """Computed. There is no field to set and no way to override."""
        return not self.blocking_reasons

    @property
    def writes_devices_csv(self) -> bool:
        """Does this run add a row to ``devices.csv``?

        Only for a local list. On a NetBox-sourced list identity is read-only
        and the device arrives on the next refresh — and the wizard says so
        rather than writing a row the refresh would then fight with.
        """
        return self.source_kind == "local"

    @property
    def summary(self) -> dict:
        """What the review step shows. No secrets, by construction."""
        return {
            "hostname":       self.hostname,
            "platform":       self.platform,
            "list":           self.list_name,
            "source_kind":    self.source_kind,
            "mgmt_ip":        self.mgmt_ip,
            "cred_source":    self.cred_source,
            "template":       self.template,
            "netbox_objects": len(self.netbox_plan),
            "writes_csv":     self.writes_devices_csv,
            "onboardable":    self.onboardable,
            "blocking_reasons": self.blocking_reasons,
        }


def _name_in_manifest(repo: str, hostname: str):
    """``(taken, checked)``. A lookup that raised has not answered."""
    try:
        from modules.nsot import manifest as _m

        return bool(_m.find_by_name(repo, hostname)[1]), True
    except Exception as exc:                   # noqa: BLE001
        log.error("onboard: manifest lookup failed for %r: %s", hostname, exc)
        return False, False


def _name_in_netbox(hostname: str):
    """``(taken, checked)``. Same contract, and the same reason for it."""
    from modules.integrations import get_integration

    try:
        client = get_integration("netbox")
        if client is None or not client.is_configured():
            # Not configured is a decision, not a failure: a local list can
            # be onboarded without NetBox at all. Reported as checked, since
            # there is no NetBox for the name to collide in.
            return False, True
    except Exception as exc:                   # noqa: BLE001
        log.error("onboard: could not reach the NetBox client: %s", exc)
        return False, False

    try:
        from modules.netbox_client import netbox_get_device

        # `netbox_get_device` returns `{"ok": False, "error": …}` for both
        # "no such device" and "NetBox is unreachable". They are different
        # facts and only one of them is evidence, so the error text decides:
        # anything that is not a clean not-found leaves the check UNRUN.
        hit = netbox_get_device(hostname) or {}
        if hit.get("ok"):
            return True, True
        error = (hit.get("error") or "").lower()
        if "not found" in error or "no device" in error:
            return False, True
        log.error("onboard: NetBox name check for %r did not answer: %s",
                  hostname, hit.get("error", "no error given"))
        return False, False
    except Exception as exc:                   # noqa: BLE001
        log.error("onboard: NetBox name check failed for %r: %s", hostname, exc)
        return False, False


def build_plan(hostname: str, platform: str, list_name: str, *,
               mgmt_ip: str = "", source_kind: str = "local",
               secret: str = "", domain: str = "rcn.lab",
               mgmt_interface: str = "", host_vars: dict = None,
               netbox_plan=(), cred_source: str = "") -> OnboardPlan:
    """The only constructor. Always validates; never writes anything.

    *secret* is the one-time bootstrap credential (4C.2). It reaches the
    rendered config and nothing else here — this function does not store it,
    and `OnboardPlan` does not carry it, so a plan can be logged or returned
    over HTTP without a redaction step having to remember.
    """
    from modules.config import get_list_data_dir
    import os

    repo = os.path.join(get_list_data_dir(list_name), "config_repo")

    in_manifest, manifest_ok = _name_in_manifest(repo, hostname)
    in_netbox, netbox_ok = _name_in_netbox(hostname)

    unchecked = []
    if not manifest_ok:
        unchecked.append("the repository manifest")
    if not netbox_ok:
        unchecked.append("NetBox")

    template, approved = _template_for(repo, hostname, platform)
    config, unsendable = _render(platform, hostname, secret, domain,
                                 mgmt_interface)

    return OnboardPlan(
        hostname=hostname, platform=platform, list_name=list_name,
        source_kind=source_kind, mgmt_ip=mgmt_ip,
        bootstrap_config=config, cred_source=cred_source,
        netbox_plan=tuple(netbox_plan), host_vars=dict(host_vars or {}),
        template=template, template_approved=approved,
        name_taken_in_manifest=in_manifest, name_taken_in_netbox=in_netbox,
        unsendable=tuple(unsendable), unchecked=tuple(unchecked),
    )


def _template_for(repo: str, hostname: str, platform: str):
    """``(template, approved)`` for a platform with no device bound yet.

    Approval is a claim about the **template against its bound devices**, and
    the device being onboarded is not one of them — it does not exist. So the
    question is whether the template is approved as it stands, which is what
    `is_approved()` answers: `binding_fingerprint()` reads the bound set from
    the repo and ignores any host_vars passed to it.
    """
    if not platform:
        return "", False
    try:
        from modules.nsot import approval, templates_repo

        # `template_for_device` takes a device name and falls back to the
        # platform binding when there is no override — which is exactly this
        # case, since the device does not exist and can have no override. Read
        # rather than assumed: there is no `template_for_platform`.
        template = templates_repo.template_for_device(repo, hostname, platform)
        if not template:
            return "", False
        return template, bool(approval.is_approved(repo, template))
    except Exception as exc:                   # noqa: BLE001
        log.error("onboard: template lookup failed for %r: %s", platform, exc)
        return "", False


def _render(platform: str, hostname: str, secret: str, domain: str,
            mgmt_interface: str):
    """``(config, unsendable)``. A render that cannot be sent is a refusal.

    **The ASCII guard is the generator's own**, not a second copy here.
    `render_bootstrap()` ends with `assert_sendable()` over the whole
    artefact — comments included, because the line that hung a vIOS boot
    began with `!` — and raises with the command number, the offending
    codepoint and the column. A scanner here would be a worse message for the
    same property, and two producers of the same answer is how they come to
    disagree.

    What this adds is that the failure becomes a **blocking reason** rather
    than an exception reaching the wizard. The bootstrap config is the one
    artefact that reaches a device without a deploy at all — it is typed into
    a console at boot — so it matters that the refusal is visible in the
    review step rather than as a stack trace.
    """
    if not platform or platform in BLOCKED_PENDING_MEASUREMENT:
        return "", ()
    try:
        from modules.nsot.bootstrap_config import render_bootstrap

        config = render_bootstrap(platform, hostname=hostname,
                                  username="admin", secret=secret or "unset",
                                  domain=domain,
                                  mgmt_interface=mgmt_interface)
    except Exception as exc:                   # noqa: BLE001
        log.error("onboard: bootstrap render failed for %r: %s", hostname, exc)
        return "", (f"the bootstrap config could not be rendered: {exc}",)

    return config, ()


# ---------------------------------------------------------------------------
# The one-time bootstrap credential
# ---------------------------------------------------------------------------

#: Long enough that guessing is not the attack, short enough to type at a
#: console if the wizard dies and somebody has to. `secrets` rather than
#: `random`: this is the only credential the device has for part of its life.
BOOTSTRAP_LENGTH = 24

#: No shell metacharacters, no quotes, no colon. The value reaches a config
#: file, a console and possibly `router.db` (colon-delimited), and a
#: credential that breaks the file it lives in is not a credential.
_BOOTSTRAP_ALPHABET = ("ABCDEFGHJKLMNPQRSTUVWXYZ"
                       "abcdefghijkmnopqrstuvwxyz"
                       "23456789")


def mint_bootstrap_credential() -> str:
    """A fresh random password for one onboarding run.

    It exists to reach the device once, for its first capture, and is replaced
    by a device-generated type-9 secret before the run finishes. It is never a
    durable credential and is never written to ``devices.csv`` or the
    credential store.

    The alphabet excludes look-alikes (`0O1lI`) because the one time anybody
    reads this value is when something has gone wrong and they are typing it
    into a console.
    """
    import secrets

    return "".join(secrets.choice(_BOOTSTRAP_ALPHABET)
                   for _ in range(BOOTSTRAP_LENGTH))


def stage_bootstrap_credential(repo: str, hostname: str, password: str) -> str:
    """Park the bootstrap credential across the crash window, encrypted.

    **Between the device booting with this value and the rotation replacing
    it, it is the only way in.** If it existed only in memory, a wizard crash
    in that interval would leave a reachable device nobody can log into —
    tolerable for a probe, not for r6.

    That is the *same* window `credential_rotation` already covers, between
    the device accepting a password and the credential store being written.
    So this uses **its** staging rather than a second mechanism: same
    directory, same encryption, same 0700/0600, same recovery path. Two
    mechanisms for one window is how one of them stops being maintained.
    """
    from modules.nsot.credential_rotation import stage_plaintext

    return stage_plaintext(repo, hostname, password)


def staged_bootstrap_credential(repo: str, hostname: str):
    """Recover the bootstrap credential after a crash, or ``None``."""
    from modules.nsot.credential_rotation import staged_plaintext

    return staged_plaintext(repo, hostname)


def clear_bootstrap_credential(repo: str, hostname: str) -> None:
    """Drop it — **only** once rotation has succeeded.

    Clearing it on failure would close the crash window by throwing away the
    thing that makes it survivable.
    """
    from modules.nsot.credential_rotation import clear_staged

    clear_staged(repo, hostname)


def finish_bootstrap(repo: str, hostname: str, list_name: str, *,
                     confirmed_fingerprint: str, actor: str = "",
                     actor_kind: str = "", rotate=None) -> dict:
    """Replace the bootstrap credential with a device-generated secret.

    Returns ``{"rotated", "state", "reason", "recoverable"}``.

    **A run whose rotation failed does not report success.** It reports the
    device onboarded and **not rotated**, names why, and says the bootstrap
    credential is still staged and still the way in. That is the `mark_done()`
    rule: an item closed on a failed push is the queue claiming work that did
    not happen, and an operator told "onboarded" walks away from a device
    still holding a throwaway password.

    `confirmed_fingerprint` is passed through rather than invented here: the
    rotation is a device change and its confirm is the wizard's, not this
    function's. A default would be this layer confirming on the operator's
    behalf.

    **`rotation_succeeded()` decides, not a truthiness check.** The rotation
    has five states and two of them mean "the device is rotated and the
    bookkeeping is not finished" — which is a success for the credential and
    a finding for the operator. Reading `result["ok"]` would collapse that,
    and there is no such key.

    The staged value is cleared **only** on success.
    """
    from modules.nsot.credential_rotation import (NOT_STARTED,
                                                  rotation_succeeded)

    if rotate is None:
        from modules.nsot.credential_rotation import rotate

    try:
        result = rotate(list_name, hostname,
                        confirmed_fingerprint=confirmed_fingerprint,
                        actor=actor, actor_kind=actor_kind) or {}
    except Exception as exc:                   # noqa: BLE001
        log.error("onboard: rotation raised for %s: %s", hostname, exc)
        result = {"state": NOT_STARTED, "error": f"rotation raised: {exc}"}

    state = result.get("state", NOT_STARTED)
    if not rotation_succeeded(result):
        reason = result.get("error") or f"rotation ended in state {state!r}"
        log.error("onboard: rotation did not succeed for %s: %s",
                  hostname, reason)
        return {"rotated": False, "state": state, "reason": reason,
                "recoverable": staged_bootstrap_credential(repo, hostname)
                is not None}

    clear_bootstrap_credential(repo, hostname)
    return {"rotated": True, "state": state, "reason": "", "recoverable": False}
