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

    #: The address the MANAGER reaches this device on, and where it goes.
    #:
    #: **Not the containerlab management interface** -- see the two-namespace
    #: note in `bootstrap_config`. `mgmt_ip` was collected and displayed long
    #: before anything emitted it into a config: the refusal below ("no
    #: management address -- the device would be created and unreachable")
    #: has been correct since 4C.1, while the generator produced a config
    #: that could not use the value. **The refusal existed; the fulfilment
    #: did not.**
    mgmt_ip: str = ""
    mgmt_mask: str = ""
    #: Chosen, never defaulted -- on a C8000v, Gi1 belongs to vrnetlab.
    manager_interface: str = ""
    #: Omitted unless the manager is on another subnet. See
    #: `manager_interface_lines()` for why that is a conditional and not a
    #: property of bootstrap configs.
    manager_gateway: str = ""

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

    #: The render refused outright. **Kept apart from `unsendable`**, which
    #: it used to be folded into: "3 lines contain characters an IOS CLI
    #: cannot accept" is a precise, checkable claim, and reporting a missing
    #: netmask under it told the operator to go looking for an em dash.
    #: Found by reading the refusals this step's own change produced.
    render_error: str = ""

    #: Set when the stores could not be consulted. **Not** the same as "no
    #: collision": a check that could not run has not passed.
    unchecked: tuple = field(default_factory=tuple)

    #: Preconditions the RUN needs and the plan can already see are missing.
    #:
    #: **Found at plan time, never mid-run.** The review screen promises
    #: *"nothing has been created yet"*; discovering that NetBox writes are
    #: disabled after the credential has been bound breaks that promise, and
    #: a run that stops halfway is a partial state the operator did not
    #: agree to. Anything the run requires is checked before anything is
    #: offered.
    unmet_preconditions: tuple = field(default_factory=tuple)

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

        # The lookup is on a DIALECT. A slug reaching here would miss and
        # return None, which in a gate reads as "allowed" -- measured once,
        # in `/onboard/platforms`. `build_plan` asserts the namespace at the
        # boundary so it cannot happen silently again.
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
        elif not self.mgmt_mask:
            reasons.append(f"no network mask for {self.mgmt_ip} — a /24 "
                           "assumption is how a tool works in exactly one lab")

        # Never defaulted, and refused separately from the address so the
        # operator is told which half is missing. On a C8000v the first
        # interface is vrnetlab's, and a management address landing there is
        # the failure 4C.8 exists to prevent.
        if self.mgmt_ip and not self.manager_interface:
            reasons.append(
                "no interface chosen for the management address — it cannot "
                "be defaulted, because on this platform vrnetlab may own the "
                "first interface and a guess is a silent one")

        if self.render_error:
            reasons.append("the bootstrap config could not be rendered: "
                           + self.render_error)

        if self.unsendable:
            reasons.append(
                f"{len(self.unsendable)} line(s) of the bootstrap config "
                "contain characters an IOS CLI cannot accept: "
                + "; ".join(self.unsendable[:2])
                + ("…" if len(self.unsendable) > 2 else ""))

        # Preconditions, named individually. "The run would fail" is not
        # actionable; "NetBox writes are disabled" is.
        reasons.extend(self.unmet_preconditions)

        # A check that could not run has not passed. Reported as its own
        # refusal rather than folded into the collision flags, because
        # "NetBox says no such device" and "NetBox could not be reached" are
        # different facts and only one of them is evidence.
        for what in self.unchecked:
            reasons.append(f"could not verify {what} — a check that did not "
                           "run has not passed")

        return reasons

    @property
    def advisories(self) -> list:
        """True, useful, and **not** reasons to refuse.

        Template state used to be two blocking reasons here, and it was
        keyed on the wrong property. The artefact this path emits is
        `render_bootstrap()`'s output; `templates/` has no part in producing
        it, and no step in `run_onboarding` reads `self.template` at all.
        That is the Phase 3c rule generalised -- gate on what the artefact
        actually depends on.

        **Measured: the gate could not be satisfied by any first device.**
        `approval.approve()` refuses an empty device set ("nothing to
        validate it against", correctly -- that is the assertion-over-an-
        empty-set failure). So a fresh list cannot approve a template,
        cannot therefore onboard, and cannot therefore acquire the device
        the approval needs. **The onboarding wizard could not onboard the
        first device of a network.**

        What the old gate protected is already checked where it belongs: the
        deploy path validates approval on every plan, per device, with the
        offending lines named. Checking it here was early, duplicated, and
        blocking on something the operator can fix afterwards.

        So it is said rather than enforced -- and said as a **next step**,
        naming what to do and why it cannot be done yet. A warning about
        nothing trains the reader to skip warnings.
        """
        notes = []
        if not self.platform:
            return notes

        if not self.template:
            notes.append(
                f"No template is bound for platform '{self.platform}' in "
                f"list '{self.list_name}'. Onboarding is unaffected — the "
                f"startup config below comes from the bootstrap generator, "
                f"not from a template — but you will not be able to deploy "
                f"to this device until one is bound and approved.")
        elif not self.template_approved:
            notes.append(
                f"You cannot deploy to this device until "
                f"'{self.template}' is approved for list "
                f"'{self.list_name}', which needs a captured device to "
                f"validate against. Onboard this device, capture its "
                f"config, then approve the template on the Templates tab. "
                f"Approval does not carry between lists: it is keyed on the "
                f"template hash plus the bound device set in this repo.")
        return notes

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
            # Shown alongside the address, because an address on its own
            # and an address with a mask and an interface are different
            # claims -- and only the second is a config a device can boot.
            "mgmt_mask":         self.mgmt_mask,
            "manager_interface": self.manager_interface,
            "manager_gateway":   self.manager_gateway,
            "cred_source":    self.cred_source,
            "template":       self.template,
            "netbox_objects": len(self.netbox_plan),
            "writes_csv":     self.writes_devices_csv,
            "onboardable":    self.onboardable,
            "blocking_reasons": self.blocking_reasons,
            # Separate key, never merged into the list above: a renderer that
            # concatenated them would make an advisory look like a refusal,
            # and one day make a refusal look like an advisory.
            "advisories":     self.advisories,
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
               netbox_plan=(), cred_source: str = "",
               mgmt_mask: str = "", manager_interface: str = "",
               manager_gateway: str = "") -> OnboardPlan:
    """The only constructor. Always validates; never writes anything.

    *secret* is the one-time bootstrap credential (4C.2). It reaches the
    rendered config and nothing else here — this function does not store it,
    and `OnboardPlan` does not carry it, so a plan can be logged or returned
    over HTTP without a redaction step having to remember.
    """
    import os

    from modules.config import get_list_data_dir

    # VALIDATE BEFORE TOUCHING THE FILESYSTEM. A dialect, not a slug and not
    # a Netmiko driver -- refused loudly rather than missing a table lookup
    # and defaulting to "allowed".
    #
    # First, and deliberately: `get_list_data_dir()` calls `os.makedirs()`,
    # so merely resolving the repo path creates a list directory. A refused
    # plan that had already created one would leave a directory for a device
    # that was never onboarded, named after a list that may not exist.
    if platform:
        from modules.nsot.platform import assert_dialect

        assert_dialect(platform, where="build_plan(platform=…)")

    repo = os.path.join(get_list_data_dir(list_name), "config_repo")

    in_manifest, manifest_ok = _name_in_manifest(repo, hostname)
    in_netbox, netbox_ok = _name_in_netbox(hostname)

    unchecked = []
    if not manifest_ok:
        unchecked.append("the repository manifest")
    if not netbox_ok:
        unchecked.append("NetBox")

    template, approved = _template_for(repo, hostname, platform)
    config, unsendable, render_error = _render(
        platform, hostname, secret, domain,
        mgmt_interface, manager_interface=manager_interface,
        manager_address=mgmt_ip, manager_mask=mgmt_mask,
        manager_gateway=manager_gateway)

    return OnboardPlan(
        unmet_preconditions=tuple(unmet_preconditions(netbox_plan)),
        hostname=hostname, platform=platform, list_name=list_name,
        source_kind=source_kind, mgmt_ip=mgmt_ip, mgmt_mask=mgmt_mask,
        manager_interface=manager_interface, manager_gateway=manager_gateway,
        bootstrap_config=config, cred_source=cred_source,
        netbox_plan=tuple(netbox_plan), host_vars=dict(host_vars or {}),
        template=template, template_approved=approved,
        name_taken_in_manifest=in_manifest, name_taken_in_netbox=in_netbox,
        unsendable=tuple(unsendable), unchecked=tuple(unchecked),
        render_error=render_error,
    )


def unmet_preconditions(netbox_plan=()) -> list:
    """What the RUN needs and does not have, checked before anything is offered.

    **The master switch is never flipped as a side effect.** An operation
    that enables NetBox writes because the operator confirmed something else
    is the same defect as a push exceeding its preview: the operator agreed
    to one thing and a second thing happened. `netbox_allow_writes` is a
    persistent decision and stays one — so the wizard *reports* it as a
    blocking reason and the operator turns it on deliberately.

    Checked only when the plan would actually write to NetBox. A local list
    on an installation with no NetBox needs no switch, and a precondition
    that fires when it does not apply is a refusal people learn to ignore.
    """
    unmet = []

    if netbox_plan:
        try:
            from modules.netbox_guard import writes_allowed

            if not writes_allowed():
                unmet.append(
                    "NetBox writes are disabled, and this run would create "
                    f"{len(netbox_plan)} object(s). Enable 'Allow writes to "
                    "NetBox' in Settings → Integrations first — the wizard "
                    "will not turn it on for you, because a switch flipped as "
                    "a side effect of confirming something else is not a "
                    "decision anybody made.")
        except Exception as exc:               # noqa: BLE001
            log.error("onboard: could not read the NetBox write gate: %s", exc)
            unmet.append("could not read the NetBox write gate — a check that "
                         "did not run has not passed")

    return unmet


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
            mgmt_interface: str, *, manager_interface: str = "",
            manager_address: str = "", manager_mask: str = "",
            manager_gateway: str = ""):
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
        return "", (), ""
    try:
        from modules.nsot.bootstrap_config import render_bootstrap
        from modules.nsot.deploy import UnsendableCommand

        config = render_bootstrap(platform, hostname=hostname,
                                  username="admin", secret=secret or "unset",
                                  domain=domain,
                                  mgmt_interface=mgmt_interface,
                                  manager_interface=manager_interface,
                                  manager_address=manager_address,
                                  manager_mask=manager_mask,
                                  manager_gateway=manager_gateway)
    except UnsendableCommand as exc:
        # The ONE failure that belongs in `unsendable`, keyed on the type
        # rather than on "the render raised". `assert_sendable` names the
        # command number, the codepoint and the column, and that message is
        # carried through rather than re-implemented.
        log.error("onboard: bootstrap config is unsendable for %r: %s",
                  hostname, exc)
        return "", (str(exc),), ""
    except Exception as exc:                   # noqa: BLE001
        # Everything else. Split out because a missing netmask was being
        # announced as "lines contain characters an IOS CLI cannot accept",
        # which sent the reader looking for an em dash -- and the first
        # version of that split was too coarse the other way, folding the
        # genuine unsendable finding in here too. The exception type is the
        # thing that actually distinguishes them.
        log.error("onboard: bootstrap render failed for %r: %s", hostname, exc)
        return "", (), str(exc)

    return config, (), ""


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


# ---------------------------------------------------------------------------
# Running it: the order, and what a failure at each step leaves behind
# ---------------------------------------------------------------------------

#: The order, and why it is this one. Chosen by **what is recoverable**, per
#: `docs/NSOT_PHASE4_ONBOARDING.md` §3, with one clarification 4C.3 adds:
#:
#: **The commit is genuinely last among the things that can fail.** Anything
#: fallible after it is a partial state the repository already records, and a
#: repository is not a place where partial states can be quietly tidied: a
#: commit followed by a reset leaves a clean tree, an object still present in
#: `.git`, a reflog entry, and — if the post-commit hook fired in between —
#: a commit on a remote, where nothing local can retract it.
#:
#: That conflicts with §4's step order, which renders *after* committing so
#: nothing downloadable was built from unrecorded intent. Both hold, because
#: there are two renders: `build_plan()` validates the render **before**
#: anything is created, and the downloadable artefact is produced **after**
#: the commit, from committed intent. A render that cannot succeed therefore
#: blocks at the plan, not halfway through a run.
STEPS = ("credentials", "netbox", "commit", "render")


def run_onboarding(plan, *, bind_credentials, create_netbox, commit, render,
                   repo: str = "") -> dict:
    """Execute an onboarding run. Every step is injected, and that is the point.

    The order is :data:`STEPS`, and each callable is passed in rather than
    reached for, so the ordering and the failure behaviour can be tested
    without NetBox, git or a device. A test that has to mock a module's
    internals to check an ordering ends up asserting the mocks.

    Returns ``{"ok", "completed", "failed_at", "reason", "netbox_created",
    "commit", "cleanup_offered"}``.

    **Nothing is retried and nothing is rolled back.** A failure stops the run
    and reports what exists, because the stores are not atomic with each other
    and pretending otherwise is how a half-created device becomes invisible.
    What the run *does* offer is the existing provenance-based Remove when
    NetBox objects were created and the run then failed — rather than leaving
    the operator to find it.
    """
    result = {"ok": False, "completed": [], "failed_at": "", "reason": "",
              "netbox_created": [], "commit": "", "cleanup_offered": False}

    if not plan.onboardable:
        result["failed_at"] = "plan"
        result["reason"] = "; ".join(plan.blocking_reasons)
        return result

    def _fail(step, exc):
        result["failed_at"] = step
        result["reason"] = str(exc)
        # Only NetBox leaves something behind that this run can clean up.
        # Credentials are local and reversible; the commit has not happened.
        result["cleanup_offered"] = bool(result["netbox_created"])
        log.error("onboard: run failed at %s for %s: %s",
                  step, plan.hostname, exc)
        return result

    try:
        bind_credentials(plan)
    except Exception as exc:                   # noqa: BLE001
        return _fail("credentials", exc)
    result["completed"].append("credentials")

    try:
        created = create_netbox(plan) or []
        result["netbox_created"] = list(created)
    except Exception as exc:                   # noqa: BLE001
        return _fail("netbox", exc)
    result["completed"].append("netbox")

    # ── the commit, last among the fallible ─────────────────────────────────
    # One call, one commit: identity, host_vars and the site's group_vars
    # together. A failure here has created no commit at all — not a commit
    # that was later undone.
    try:
        sha = commit(plan)
    except Exception as exc:                   # noqa: BLE001
        return _fail("commit", exc)
    result["commit"] = sha or ""
    result["completed"].append("commit")

    # Pure computation over what is now committed. It cannot fail in a way
    # that leaves a partial state, because the state is already recorded --
    # and `build_plan()` has already proved the render succeeds.
    try:
        render(plan)
    except Exception as exc:                   # noqa: BLE001
        # Reported, not hidden: the device IS onboarded and the artefact is
        # not available. Two facts, and the operator needs both.
        result["ok"] = True
        result["failed_at"] = "render"
        result["reason"] = (f"the device is onboarded and committed; the "
                            f"downloadable config could not be rendered: {exc}")
        return result
    result["completed"].append("render")

    result["ok"] = True
    return result


# ---------------------------------------------------------------------------
# 4C.5 — the read-write community a vrnetlab node arrives with
# ---------------------------------------------------------------------------

#: `snmp-server community <name> RW [<acl>]`, and nothing else.
#:
#: **Deliberately narrow.** The nine reference devices each carry
#: `snmp-server community public RO`, acknowledged and kept, and the history
#: scan treated them as read-only communities that are part of the network.
#: Anything **RW** arriving with a new node is a different matter and is
#: removed as part of onboarding.
#:
#: Over-broadening this is the version that costs monitoring: a pattern
#: matching any `snmp-server community` would propose removing all nine and
#: take Prometheus, the SNMP collector and the trap receiver with them. The
#: access mode is what distinguishes them, so the access mode is what the
#: pattern requires — **`RW` is mandatory in the match, not optional**.
_RW_COMMUNITY = re.compile(
    r"^\s*snmp-server\s+community\s+(?P<name>\S+)\s+RW\b", re.IGNORECASE)


def rw_communities(config_text: str) -> list:
    """Every read-write community line in *config_text*, verbatim.

    Verbatim, because the removal is `no <the line exactly as it appears>`.
    A reconstructed line can differ from the device's own in the ACL, the
    view or the spacing, and `no snmp-server community public RW` against a
    device whose line reads `… RW 99` is a command that does not match.
    """
    return [line.rstrip() for line in (config_text or "").splitlines()
            if _RW_COMMUNITY.match(line)]


def ro_communities(config_text: str) -> list:
    """Read-only communities — reported so the confirm can say what is KEPT.

    Shown next to what is removed, because an operator reading "1 community
    removed" on a device with two of them needs to know which."""
    return [line.rstrip() for line in (config_text or "").splitlines()
            if re.match(r"^\s*snmp-server\s+community\s+\S+\s+RO\b",
                        line, re.IGNORECASE)]


def rw_removal_plan(config_text: str) -> dict:
    """``{"remove": [...], "keep": [...]}`` for the confirm dialog.

    Both halves, always. "What will be removed" without "what will be kept"
    is the half that makes an operator hesitate over a correct change, and
    the half that would have hidden an over-broad match.
    """
    remove = rw_communities(config_text)
    return {"remove": [f"no {line.strip()}" for line in remove],
            "removing": remove,
            "keep": ro_communities(config_text)}


# ---------------------------------------------------------------------------
# 4C.7 — the real steps
# ---------------------------------------------------------------------------
#
# `run_onboarding()` takes its steps as arguments so the ORDERING and the
# failure behaviour can be tested without NetBox, git or a device. These are
# the steps it takes in production, and `real_steps()` is the one place they
# are assembled.
#
# **They are tested through `run_onboarding` itself**, with their
# dependencies faked rather than the steps replaced. Testing the contract
# against stand-ins proves the contract; it does not prove these satisfy it,
# and "the unit was right and the wiring was absent" is the shape this stage
# has already produced twice.


def bind_credentials_step(plan, *, repo: str) -> str:
    """Mint the one-time credential, stage it, and record the override.

    Staged **before** the override is written: the staging file is what makes
    the crash window survivable, and a crash between the two would otherwise
    leave a credential in the store and nothing able to recover it.
    """
    from modules import credentials

    secret = mint_bootstrap_credential()
    stage_bootstrap_credential(repo, plan.hostname, secret)

    # KEYED ON THE MANAGEMENT IP, positionally, because that is what
    # `set_device_override(device_key, username, password, secret)` takes and
    # what `resolve()` looks the override up by --
    # `data["device_overrides"].get(mgmt_ip)`.
    #
    # This call was written as `(plan.list_name, plan.hostname, {…})`: a list
    # name where the key belongs, a hostname where the username belongs, and
    # a dict where a string belongs. `encrypt_value(dict)` raises
    # AttributeError, so `/onboard/create` failed at its first step every
    # time it was called. Fourth inferred-signature finding of this stage,
    # and the first in shipped code rather than in a draft.
    credentials.set_device_override(plan.mgmt_ip, "admin", secret, secret)
    return secret


def create_netbox_step(plan) -> list:
    """Create this device's NetBox objects, through the Phase 0 gate.

    `sync_list_to_netbox` refuses when `netbox_allow_writes` is off and
    returns `{"blocked": True}` rather than raising. **That refusal is turned
    into an exception here**, because `run_onboarding` reads a raise as "this
    step failed" and a returned dict as success — a blocked write that looked
    like a success would carry the run into the commit.

    The plan has already reported the switch as a blocking reason, so this is
    the second line of defence rather than the first: the state can change
    between the review and the confirm, which is the same reason the deploy
    path recomputes its program at apply.
    """
    from modules.netbox_client import sync_list_to_netbox

    device = {"hostname": plan.hostname, "ip": plan.mgmt_ip,
              "platform": plan.platform, "role": "router"}
    result = sync_list_to_netbox(plan.list_name, [device]) or {}
    if result.get("blocked") or not result.get("ok", True):
        raise RuntimeError(result.get("error")
                           or "NetBox refused the write and did not say why")

    from modules.netbox_guard import get_created

    created = get_created(plan.list_name) or {}
    return [f"{endpoint}:{obj_id}"
            for endpoint, objects in created.items()
            for obj_id in (objects or {})]


def commit_step(plan, *, actor: str) -> str:
    """One call, one commit: the identity and the device's initial intent.

    `save_host_vars` is the existing path and carries the trailers. The
    identity is minted here and only here, through `adopt_identity` — the
    wizard is one of the two callers the decision permits.
    """
    import os

    from modules.config import get_list_data_dir
    from modules.nsot import hostvars, manifest
    from modules.nsot.repo import GoldenItem, adopt_identity, save_host_vars

    repo = os.path.join(get_list_data_dir(plan.list_name), "config_repo")

    # MINTED AND THEN RECORDED. `adopt_identity()` returns a string and
    # persists nothing -- its whole job is to be the one place a new identity
    # is created, separate from `resolve_identity()`. Writing it to the
    # manifest is `upsert_device()` and was missing, so the return value was
    # assigned to nothing and the device was committed to git with no entry
    # in the identity map at all.
    #
    # Measured: after a successful `commit_step`, `manifest.load(repo)
    # ["devices"]` was `{}` and `find_by_name()` returned `(None, None)`.
    # This docstring said "the identity is minted here and only here"; it was
    # minted into a local and discarded. Fourth docstring this stage to teach
    # something the code did not do.
    identity = adopt_identity(repo, GoldenItem(plan.hostname, "", plan.mgmt_ip))
    manifest.upsert_device(repo, identity, plan.hostname,
                           mgmt_ip=plan.mgmt_ip, platform=plan.platform)
    hostvars.write_committed(repo, dict(plan.host_vars or {},
                                        hostname=plan.hostname))
    result = save_host_vars(plan.list_name, [plan.hostname], actor=actor,
                            message=f"onboarding: {plan.hostname}",
                            source="onboarding")
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "the commit did not succeed")
    return result.get("commit", "")


def render_step(plan) -> str:
    """The downloadable artefact. **Last, deliberately — see below.**

    It returns `render_bootstrap()`'s output, built from the hostname, the
    one-time secret, the domain and the management address. It is **not**
    derived from the committed host_vars, and no template renders it.

    An earlier version of this docstring said "from **committed** intent",
    which described the ORDERING as though it were the DERIVATION. The
    ordering is real and worth keeping: running last means an operator can
    never download an artefact for a device the NSoT has no record of. The
    derivation claim was simply false.

    Third docstring in this stage to teach something the code does not do,
    after `manifest.py`'s slug example and `render_bootstrap`'s "what
    remains is what makes the device reachable". All three were load-bearing
    prose next to correct code, which is the combination that survives
    review.

    `build_plan`
    has already proved the render succeeds, so a failure here is a surprise
    rather than a foreseeable refusal — and it leaves a device that is
    onboarded and an artefact that is missing, which `run_onboarding` reports
    as two facts.
    """
    return plan.bootstrap_config


def real_steps(repo: str, actor: str) -> dict:
    """The production steps, assembled once.

    Two copies of this mapping would be two orderings, and the ordering is
    the thing `test_onboard_ordering.py` exists to pin.
    """
    return {
        "bind_credentials": lambda plan: bind_credentials_step(plan, repo=repo),
        "create_netbox":    create_netbox_step,
        "commit":           lambda plan: commit_step(plan, actor=actor),
        "render":           render_step,
    }


# ---------------------------------------------------------------------------
# Abandon: the inverse of the wizard
# ---------------------------------------------------------------------------

#: Reverse of `STEPS`, minus `render` (which persists nothing).
#:
#: `identity` is last for the same reason `commit` is last in `STEPS`: it is
#: the step whose success is a claim about all the others. Releasing the name
#: first would leave the name free while a NetBox object and a commit still
#: named the device -- which is exactly the state this flow exists to end.
ABANDON_STEPS = ("intent", "netbox", "credentials", "identity")


def abandon_onboarding(repo: str, hostname: str, list_name: str, *,
                       actor: str = "", dry_run: bool = False,
                       remove_netbox=None) -> dict:
    """Undo an onboarding, in the reverse of the order that created it.

    **Why this exists rather than `manifest.release()` alone.** Release
    correctly refuses while artefacts reference the device -- and the
    artefacts of a failed onboarding are a commit, a NetBox object and a
    credential override, cleared through three separate mechanisms, one of
    them the provenance-based Remove. A refusal naming three manual steps is
    a dead end with better signposting. The purpose is to make a failed
    onboarding **annoying rather than unrecoverable**, and only running the
    sequence achieves that.

    **The NetBox step exercises the unproven mechanism deliberately.**
    Provenance-based removal has never deleted an object it created. Abandon
    runs it per device, on a device this tool made, which rehearses the
    teardown on something disposable before it is needed on a real one.

    **Partial failure reports what remains.** Each step is recorded as
    `removed` or `refused` with a reason, `ok` is true only when every step
    succeeded **and** the identity was released, and `remaining` names what
    is left with how to finish it. An abandon that half-ran and reported
    success is the defect this whole flow is a response to.

    THE WRONG-AND-LOOKS-RIGHT STATE, and what makes it visible: reporting a
    name reclaimed while a NetBox object or a commit still references it.
    That cannot happen here by construction, because the reclaim is
    `manifest.release()` and release **re-derives the references itself**
    rather than trusting the steps that ran before it. If any step silently
    did nothing, release refuses and `ok` is false with the artefact named.
    The check and the work are deliberately not the same code.
    """
    import os

    from modules.nsot import manifest as _m

    result = {"ok": False, "device": hostname, "list": list_name,
              "dry_run": dry_run, "steps": [], "remaining": [],
              "released": "", "error": ""}

    identity, entry = _m.find_by_name(repo, hostname)
    if not identity:
        result["error"] = (f"'{hostname}' has no identity in this list's "
                           f"manifest — nothing to abandon")
        return result

    def _step(name, ok, detail, how=""):
        result["steps"].append({"step": name, "ok": bool(ok),
                                "detail": detail})
        if not ok:
            result["remaining"].append({"step": name, "detail": detail,
                                        "how_to_finish": how})

    # 1. INTENT. Staged first because it is the only step that needs the
    #    repo lock, and the only one whose failure is purely local.
    rel = os.path.join("host_vars", f"{entry.get('name', hostname)}.yml")
    path = os.path.join(repo, rel)
    if not os.path.exists(path):
        _step("intent", True, f"{rel} was not present")
    elif dry_run:
        _step("intent", True, f"would remove {rel}")
    else:
        try:
            from modules.nsot import repo as _repo

            os.remove(path)
            _repo.git(repo, "add", "-A")
            _repo.git(repo, "-c", "user.email=nmas@local", "-c",
                      "user.name=NMAS", "commit", "-m",
                      f"abandon: {hostname} — onboarding withdrawn",
                      "--author", f"{actor or 'NMAS'} <nmas@local>")
            _step("intent", True, f"removed {rel} and committed the removal")
        except Exception as exc:               # noqa: BLE001
            log.exception("abandon: intent step failed for %r", hostname)
            _step("intent", False, f"could not remove {rel}: {exc}",
                  "remove the file and commit the deletion by hand")

    # 2. NETBOX, through the provenance gate, scoped to this device.
    remover = remove_netbox
    if remover is None:
        from modules.netbox_client import remove_device_from_netbox as remover
    try:
        nb = remover(list_name, hostname, dry_run=dry_run) or {}
        if nb.get("ok"):
            _step("netbox", True,
                  f"{len(nb.get('deleted') or [])} object(s) removed, "
                  f"{len(nb.get('skipped') or [])} left alone")
            result["netbox"] = nb
        else:
            _step("netbox", False, nb.get("error", "removal refused"),
                  "resolve the reason above, then run abandon again")
            result["netbox"] = nb
    except Exception as exc:                   # noqa: BLE001
        log.exception("abandon: netbox step failed for %r", hostname)
        _step("netbox", False, str(exc), "run abandon again once NetBox is "
                                         "reachable")

    # 3. CREDENTIALS. Local and reversible, so it runs after the two that
    #    are not -- a failure here never blocks the expensive steps.
    try:
        from modules import credentials

        mgmt_ip = (entry or {}).get("mgmt_ip", "")
        cleared = []
        if mgmt_ip and credentials.has_device_override(mgmt_ip):
            if not dry_run:
                credentials.clear_device_override(mgmt_ip)
            cleared.append(f"override {mgmt_ip}")
        if staged_bootstrap_credential(repo, hostname):
            if not dry_run:
                clear_bootstrap_credential(repo, hostname)
            cleared.append("staged bootstrap credential")
        _step("credentials", True,
              ", ".join(cleared) if cleared else "nothing to clear")
    except Exception as exc:                   # noqa: BLE001
        log.exception("abandon: credential step failed for %r", hostname)
        _step("credentials", False, str(exc),
              "clear the device override in Settings -> Credentials")

    # 4. IDENTITY, last, and it re-derives the references itself.
    if dry_run:
        outstanding = _m.references(repo, identity, list_name)
        _step("identity", not outstanding,
              "would release" if not outstanding
              else f"would refuse: {len(outstanding)} reference(s) remain")
        result["ok"] = not outstanding and all(s["ok"] for s in result["steps"])
        return result

    released = _m.release(repo, identity, list_name=list_name, actor=actor)
    if released.get("ok"):
        _step("identity", True, f"released '{released.get('released')}'")
        result["released"] = released.get("released", "")
    else:
        _step("identity", False, released.get("error", "release refused"),
              "clear the artefacts named above, then run abandon again")
        result["remaining"].extend(
            {"step": "identity", "detail": f"{r['kind']}: {r['what']}",
             "how_to_finish": r["how_to_clear"]}
            for r in released.get("references") or [])

    result["ok"] = all(s["ok"] for s in result["steps"])
    if not result["ok"]:
        result["error"] = ("abandon did not finish; %d step(s) remain"
                           % len(result["remaining"]))
    return result
