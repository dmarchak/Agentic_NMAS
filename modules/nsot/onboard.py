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

    #: Where the management address COMES FROM: ``static`` or ``dhcp``.
    #:
    #: **A source, never an "address optional" flag.** `render_bootstrap()`
    #: refuses an empty address because the failure it prevents is silent --
    #: the device boots, reports healthy, answers its console, and is
    #: onboardable by nothing. A checkbox turns that refusal into something a
    #: person switches off, after which "I meant DHCP" and "I forgot the
    #: address" look identical from the wizard. Naming the source keeps them
    #: distinct and lets each carry its own preconditions.
    address_source: str = "static"
    #: DHCP only. The reservation is checked against Kea **at plan time**.
    mgmt_mac: str = ""
    #: What Kea said: ``reserved`` / ``not_reserved`` / ``unknown``.
    reservation_state: str = ""
    reservation_address: str = ""
    reservation_source: str = ""
    reservation_error: str = ""
    #: Chosen, never defaulted -- on a C8000v, Gi1 belongs to vrnetlab.
    manager_interface: str = ""
    #: Omitted unless the manager is on another subnet. See
    #: `manager_interface_lines()` for why that is a conditional and not a
    #: property of bootstrap configs.
    manager_gateway: str = ""

    #: The DNS domain the bootstrap config sets. A `build_plan()` argument
    #: the plan did not carry — which made the artefact un-re-renderable,
    #: because a re-render defaulting to `rcn.lab` would produce a different
    #: config from the one the node booted whenever a caller passed anything
    #: else. Carried now, and committed with the other bootstrap parameters.
    domain: str = "rcn.lab"

    #: The startup config the new node boots from. Rendered here so the
    #: review step shows what will be created, not a description of it.
    bootstrap_config: str = ""

    #: Where the credential came from, per the existing resolution order.
    #: Displayed, because `_cred_source` exists so the origin is visible.
    cred_source: str = ""

    #: What would be created in NetBox. **Phase 1 creates nothing there**,
    #: so this is only ever the empty tuple on this path; it is kept because
    #: `unmet_preconditions()` still reads it to decide whether the write
    #: gate is relevant, and a caller that does plan NetBox objects can pass
    #: one. The review screen no longer shows a count derived from it — it
    #: showed 0 while three objects were created.
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

    #: Why the syslog block (NSOT_PLAN P.1) could not be built. Onboarding
    #: gives every device the whole block as part of its baseline intent, so a
    #: device that would arrive without it is refused rather than onboarded
    #: silent -- which is how r6 came to have no logging at all.
    syslog_error: str = ""

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

        if self.address_source == "dhcp":
            # A PRECONDITION, not an acceptance item. A dynamic lease is
            # correct on the day it is recorded and wrong at some renewal
            # nothing is watching: the manifest, the CSV and NetBox would all
            # agree with each other and all disagree with the device. That is
            # the two-stores-disagreeing shape with a clock attached, and the
            # tool has no watcher for it.
            if not self.mgmt_mac:
                reasons.append(
                    "no MAC address — a DHCP device is identified to Kea by "
                    "its MAC, and without one the reservation cannot be "
                    "checked")
            elif self.reservation_state == "not_reserved":
                reasons.append(
                    f"Kea has no host reservation for {self.mgmt_mac}. A "
                    "dynamic lease would move at a renewal and the record "
                    "here would not — add a reservation and re-plan")
            elif self.reservation_state != "reserved":
                # A check that did not run has not passed.
                reasons.append(
                    "Kea could not be asked whether "
                    f"{self.mgmt_mac} has a reservation"
                    + (f" ({self.reservation_error})" if self.reservation_error
                       else "")
                    + " — refusing rather than assuming, because an unchecked "
                      "precondition and a met one look the same afterwards")
        elif not self.mgmt_ip:
            reasons.append("no management address — the device would be "
                           "created and unreachable")
        elif not self.mgmt_mask:
            reasons.append(f"no network mask for {self.mgmt_ip} — a /24 "
                           "assumption is how a tool works in exactly one lab")

        # Never defaulted, and refused separately from the address so the
        # operator is told which half is missing. On a C8000v the first
        # interface is vrnetlab's, and a management address landing there is
        # the failure 4C.8 exists to prevent.
        if (self.mgmt_ip or self.address_source == "dhcp") \
                and not self.manager_interface:
            reasons.append(
                "no interface chosen for the management address — it cannot "
                "be defaulted, because on this platform vrnetlab may own the "
                "first interface and a guess is a silent one")

        if self.render_error:
            reasons.append("the bootstrap config could not be rendered: "
                           + self.render_error)

        if self.syslog_error:
            reasons.append("the syslog block cannot be built: "
                           + self.syslog_error)

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
        """**False. Onboarding never writes the inventory row.**

        It used to return ``source_kind == "local"`` and the review screen
        showed *"Writes devices.csv: yes"* — while **no step wrote one**. A
        successful run produced a device committed to git, created in
        NetBox, and absent from every inventory.

        The row is written by `promote_device()`, when the tool has reached
        the device. That is not a smaller claim, it is the model: a device
        in the inventory is one the program will poll, back up, drift-check
        and offer in bulk ops, and one that has never answered would read as
        unreachable in nine places and mean nothing in any of them.

        Kept as a property rather than deleted because the review screen has
        to say something here, and *"after it answers"* is the sentence that
        is true.
        """
        return False

    @property
    def inventory_note(self) -> str:
        """What the review step says where the CSV claim used to be."""
        if self.source_kind != "local":
            return ("identity is read-only on a NetBox list — the device "
                    "arrives on the next refresh")
        return "after it answers — promotion adds the row, not onboarding"

    @property
    def address_claim(self) -> str:
        """The address line for the review screen, as a **checkable** claim."""
        if self.address_source != "dhcp":
            return (f"{self.mgmt_ip} {self.mgmt_mask}".strip()
                    or "no address given")
        if self.reservation_state == "reserved":
            where = (f" (from Kea's {self.reservation_source})"
                     if self.reservation_source else "")
            address = self.reservation_address or "an address Kea did not name"
            return (f"assigned by Kea reservation {self.mgmt_mac} → "
                    f"{address}{where}")
        if self.reservation_state == "not_reserved":
            return (f"DHCP, and Kea has NO reservation for {self.mgmt_mac} — "
                    "a dynamic lease moves and this record would not")
        return (f"DHCP, and Kea could not be asked about {self.mgmt_mac}"
                + (f" ({self.reservation_error})" if self.reservation_error
                   else "")
                + " — unchecked, not confirmed")

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
            "address_source":    self.address_source,
            "mgmt_mac":          self.mgmt_mac,
            "reservation_state": self.reservation_state,
            # WHAT THE REVIEW SCREEN SAYS WHERE THE ADDRESS WOULD BE.
            #
            # "assigned by DHCP" is a claim this tool cannot check -- it is a
            # statement about what will happen later, and nothing here would
            # notice if it did not. "assigned by Kea reservation <mac> ->
            # <address>" is a claim it checked a moment ago against Kea, and
            # the address is the one the device will actually get.
            #
            # The honest version is the checkable one, and when the check
            # could not run the screen says THAT rather than falling back to
            # the unfalsifiable sentence.
            "address_claim":     self.address_claim,
            "manager_interface": self.manager_interface,
            "manager_gateway":   self.manager_gateway,
            "cred_source":    self.cred_source,
            "template":       self.template,
            # NOT a count of what phase 1 creates: phase 1 creates nothing
            # in NetBox. `netbox_plan` was a tuple the route never filled, so
            # this always read 0 — displayed on a review screen, next to
            # three objects that had in fact been created. The `next_ts`
            # shape, on the panel whose job is to say what will happen.
            "netbox_note": ("nothing — the NetBox record is created in "
                            "phase 2, from the device's first capture"),
            "writes_csv":     self.writes_devices_csv,
            "inventory_note": self.inventory_note,
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


def _reservation(mac: str, kea=None) -> dict:
    """Ask Kea whether *mac* has a host reservation. **Never raises.**

    An exception, an unconfigured client and an unreachable one all come back
    as `unknown`, which `blocking_reasons` treats as a refusal -- *a check
    that did not run has not passed*, and the alternative is a device
    onboarded against a lease that moves.
    """
    try:
        if kea is None:
            from modules.integrations.kea import KeaIntegration

            kea = KeaIntegration()
        return kea.reservation_for(mac)
    except Exception as exc:                   # noqa: BLE001
        log.warning("onboard: reservation lookup failed for %s: %s", mac, exc)
        return {"state": "unknown", "address": "", "source": "",
                "error": f"{type(exc).__name__}: {exc}"}


def build_plan(hostname: str, platform: str, list_name: str, *,
               mgmt_ip: str = "", source_kind: str = "local",
               secret: str = "", domain: str = "rcn.lab",
               mgmt_interface: str = "", host_vars: dict = None,
               netbox_plan=(), cred_source: str = "",
               mgmt_mask: str = "", manager_interface: str = "",
               manager_gateway: str = "", address_source: str = "static",
               mgmt_mac: str = "", kea=None) -> OnboardPlan:
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

    # A DHCP PLAN CARRIES NO STATIC ADDRESS. Not merely unused -- actively
    # harmful, and this is the wrong-device path rather than the cosmetic one.
    #
    # `commit_step` records `plan.mgmt_ip` on the manifest, and
    # `verify_device` starts with `mgmt_ip or entry["mgmt_ip"]` -- so a DHCP
    # plan carrying a stray typed address writes it to the manifest, and
    # verification then finds it, **skips the lease discovery entirely**, and
    # tries to reach that address. Measured: a form showing "DHCP" while still
    # displaying a pre-filled Management IP produced exactly that plan.
    #
    # Dropped here rather than in the route, because `build_plan` is the only
    # constructor and this must hold however the arguments arrive.
    if address_source == "dhcp":
        mgmt_ip, mgmt_mask = "", ""

    repo = os.path.join(get_list_data_dir(list_name), "config_repo")

    in_manifest, manifest_ok = _name_in_manifest(repo, hostname)
    in_netbox, netbox_ok = _name_in_netbox(hostname)

    unchecked = []
    if not manifest_ok:
        unchecked.append("the repository manifest")
    if not netbox_ok:
        unchecked.append("NetBox")

    template, approved = _template_for(repo, hostname, platform)

    # THE RESERVATION IS CHECKED HERE, at plan time, so the refusal reaches
    # the review screen rather than a device that has already been created.
    reservation = {"state": "", "address": "", "source": "", "error": ""}
    if address_source == "dhcp" and mgmt_mac:
        reservation = _reservation(mgmt_mac, kea)

    # DHCP emits `ip address dhcp`, so the generator is given no address --
    # and its refusal for a MISSING one still stands for `static`.
    config, unsendable, render_error = _render(
        platform, hostname, secret, domain,
        mgmt_interface, manager_interface=manager_interface,
        manager_address=("dhcp" if address_source == "dhcp" else mgmt_ip),
        manager_mask=("dhcp" if address_source == "dhcp" else mgmt_mask),
        manager_gateway=manager_gateway)

    # THE SYSLOG BLOCK IS PART OF THE BASELINE (NSOT_PLAN P.1). Merged into
    # the initial intent, never over an author's own block: a caller that
    # supplied one has decided, and the commit's whole-or-absent rule still
    # judges it.
    host_vars = dict(host_vars or {})
    syslog_block, syslog_error = syslog_baseline()
    logging_ = dict(host_vars.get("logging") or {})
    if not logging_.get("syslog") and syslog_block:
        logging_.setdefault("settings", [])
        logging_.setdefault("hosts", [])
        logging_["syslog"] = syslog_block
        host_vars["logging"] = logging_
    elif logging_.get("syslog"):
        syslog_error = ""

    return OnboardPlan(
        unmet_preconditions=tuple(unmet_preconditions(netbox_plan)),
        hostname=hostname, platform=platform, list_name=list_name,
        source_kind=source_kind, mgmt_ip=mgmt_ip, mgmt_mask=mgmt_mask,
        address_source=address_source, mgmt_mac=mgmt_mac,
        reservation_state=reservation["state"],
        reservation_address=reservation["address"],
        reservation_source=reservation["source"],
        reservation_error=reservation["error"],
        manager_interface=manager_interface, manager_gateway=manager_gateway,
        domain=domain,
        bootstrap_config=config, cred_source=cred_source,
        netbox_plan=tuple(netbox_plan), host_vars=host_vars,
        syslog_error=syslog_error,
        template=template, template_approved=approved,
        name_taken_in_manifest=in_manifest, name_taken_in_netbox=in_netbox,
        unsendable=tuple(unsendable), unchecked=tuple(unchecked),
        render_error=render_error,
    )


def syslog_baseline() -> tuple:
    """``(block, error)``: the syslog block every onboarded device is given.

    From settings, read through `settings_schema.get_setting` so an unset key
    is its default rather than nothing. The block is whole or not at all --
    `hostvars.syslog_block_problems()` is the arbiter, so this cannot build a
    block the commit would then refuse.
    """
    from modules.nsot import hostvars
    from modules.settings_schema import get_setting

    host = (get_setting("syslog_host") or "").strip()
    if not host:
        return None, ("syslog_host is not configured -- every onboarded "
                      "device is given the syslog block, and a block with no "
                      "host is silence nobody receives")
    block = {
        "trap": get_setting("syslog_trap_level"),
        "origin_id": get_setting("syslog_origin_id"),
        "source_interface": get_setting("syslog_source_interface"),
        "hosts": [host],
        "heartbeat": int(get_setting("syslog_heartbeat_seconds") or 0),
    }
    problems = hostvars.syslog_block_problems(
        {"logging": {"syslog": block}})
    if problems:
        return None, "; ".join(problems)
    return block, ""


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
                     actor_kind: str = "", rotate=None,
                     device: dict = None, capture: str = "",
                     record: str = "override") -> dict:
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
        # `device`, `capture` and `record` carried through rather than
        # re-derived: this device has no inventory row (promotion writes it,
        # last) and no golden yet (the capture is in hand and is not written
        # until the RW community has been removed from it). `record` defaults
        # to "override" here because every caller of THIS function is
        # onboarding a pending device — the inventory default belongs to
        # `rotate`, whose other callers are rotating inventory devices.
        result = rotate(list_name, hostname,
                        confirmed_fingerprint=confirmed_fingerprint,
                        actor=actor, actor_kind=actor_kind,
                        device=device, capture=capture, record=record) or {}
    except Exception as exc:                   # noqa: BLE001
        log.error("onboard: rotation raised for %s: %s", hostname, exc)
        result = {"state": NOT_STARTED, "error": f"rotation raised: {exc}"}

    state = result.get("state", NOT_STARTED)
    if not rotation_succeeded(result):
        # ROTATE'S OWN REASON FIRST. This preferred `error`, a key `rotate()`
        # never sets, and fell through to a sentence naming only the state —
        # so "the confirmation does not match this device's current state"
        # was computed, returned, and thrown away one frame later.
        reason = (result.get("reason") or result.get("error")
                  or f"rotation ended in state {state!r}")
        log.error("onboard: rotation did not succeed for %s: %s",
                  hostname, reason)
        return {"rotated": False, "state": state, "reason": reason,
                # Carried so the caller can name the exit, not only the state.
                "steps": result.get("steps") or [],
                "preflight_checks": result.get("preflight_checks") or [],
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
#: Phase 1. **Three steps, and NetBox is not one of them.**
#:
#: A NetBox device record is a claim that the device EXISTS, written into the
#: source of truth about something nobody has seen. That is the claim
#: `pending` was built not to make, so making it here contradicted the model
#: the two-phase split established.
#:
#: The name-reservation argument for keeping it does not hold: the manifest
#: already reserves the name and `build_plan()` already checks NetBox for a
#: collision. An object whose only content is "do not use this name"
#: duplicates the manifest, and two reservations in two stores is how they
#: come to disagree.
#:
#: **The ordering rationale, re-derived for three.** 4C.3 ordered these by
#: what a failure leaves behind, commit last because it is the only step that
#: publishes. With NetBox gone the whole of phase 1 is LOCAL, and the order
#: now reads:
#:
#:   credentials -- a store write and a staging file, both removable, and
#:                  staged before the override so a crash between them is
#:                  survivable;
#:   commit      -- the only step that creates something durable, and still
#:                  last among the fallible;
#:   render      -- pure, cannot fail in a way that leaves state, and runs
#:                  after the commit so no artefact exists for a device the
#:                  NSoT has no record of.
#:
#: The 4C.3 property survives unchanged and is now cheaper to hold: a failure
#: at any step leaves **nothing external at all**, so abandoning a failed
#: onboarding is a commit plus a staged credential and never touches NetBox.
STEPS = ("credentials", "commit", "render")


def run_onboarding(plan, *, bind_credentials, commit, render,
                   repo: str = "") -> dict:
    """Execute an onboarding run. Every step is injected, and that is the point.

    The order is :data:`STEPS`, and each callable is passed in rather than
    reached for, so the ordering and the failure behaviour can be tested
    without NetBox, git or a device. A test that has to mock a module's
    internals to check an ordering ends up asserting the mocks.

    Returns ``{"ok", "completed", "failed_at", "reason", "commit",
    "cleanup_offered"}``.

    **Nothing is retried and nothing is rolled back.** A failure stops the run
    and reports what exists, because the stores are not atomic with each other
    and pretending otherwise is how a half-created device becomes invisible.
    What the run *does* offer is the existing provenance-based Remove when
    NetBox objects were created and the run then failed — rather than leaving
    the operator to find it.
    """
    result = {"ok": False, "completed": [], "failed_at": "", "reason": "",
              "commit": "", "cleanup_offered": False}

    if not plan.onboardable:
        result["failed_at"] = "plan"
        result["reason"] = "; ".join(plan.blocking_reasons)
        return result

    def _fail(step, exc):
        result["failed_at"] = step
        result["reason"] = str(exc)
        # NOTHING EXTERNAL IS LEFT BY A PHASE-1 FAILURE. NetBox creation
        # moved to phase 2, so the only artefacts are a credential override,
        # a staged credential and — if it got that far — a commit. All three
        # are removable by `abandon_onboarding()` without touching NetBox,
        # which is the point of moving it: the failure path is the one that
        # has never worked, and it is now almost trivial.
        result["cleanup_offered"] = False
        log.error("onboard: run failed at %s for %s: %s",
                  step, plan.hostname, exc)
        return result

    try:
        bind_credentials(plan)
    except Exception as exc:                   # noqa: BLE001
        return _fail("credentials", exc)
    result["completed"].append("credentials")

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
    # THE RESERVED ADDRESS FOR A DHCP DEVICE, because the override is keyed on
    # the management IP and a DHCP device has none at plan time -- so this was
    # keying the credential under the empty string, and `resolve()` at verify
    # would look under the discovered address and find nothing.
    #
    # The reservation is the right key precisely because it is the address the
    # device is guaranteed to get: that guarantee is why a reservation is a
    # precondition. And if the lease ever disagrees with it,
    # `discover_dhcp_address()` refuses before anything asks for a credential,
    # so a wrong key can never be silently used.
    key = plan.mgmt_ip or plan.reservation_address
    # The login credential once, not twice (B14): no enable secret exists, and
    # the connection falls back to the password.
    credentials.set_device_override(key, "admin", secret, "")
    return secret


def create_netbox_record(repo: str, hostname: str, list_name: str, *,
                         sync=None) -> dict:
    """Create this device's NetBox objects. **Phase 2, after a capture.**

    It was step 2 of phase 1 and could not work there. `sync_list_to_netbox`
    is an IMPORTER: it builds every object from the device's golden config
    (`_scan_device_from_golden`), and a device being onboarded has no golden
    by definition. So the device landed in the sync's `failed` list, the
    `for result in scanned:` loop skipped it, and **no device, interface or
    IP was ever created** — while the region, site and list-level VRF, built
    unconditionally before that loop, were.

    Measured on the live NetBox: 3 objects tagged `nmas-managed` — a region,
    a site and a VRF, all named after the list — and no device. The run
    reported *"Device onboarded."*

    **It runs after promotion**, because that is the first moment a capture
    can exist. Without one it does not guess: it reports `deferred` with the
    reason, rather than creating the list scaffolding for a device that is
    not going to be created in this call.

    Returns ``{"ok", "deferred", "created", "failed", "reason"}``.
    """
    import os

    out = {"ok": False, "deferred": False, "created": [], "failed": [],
           "reason": ""}

    # NO CAPTURE, NO IMPORT. The importer reads the golden config; calling it
    # without one creates the scaffolding and nothing else, which is exactly
    # the state this function exists to stop producing.
    try:
        from modules.ai_assistant import _load_golden_config_file
        from modules.nsot import manifest as _m

        _identity, entry = _m.find_by_name(repo, hostname)
        mgmt_ip = (entry or {}).get("mgmt_ip", "")
        if not mgmt_ip or not _load_golden_config_file(mgmt_ip):
            out["deferred"] = True
            out["reason"] = (
                f"'{hostname}' has no captured config yet, and the NetBox "
                f"import builds every object from one. Deferred until the "
                f"first capture — nothing was created.")
            return out
    except Exception as exc:                   # noqa: BLE001
        out["reason"] = f"could not check for a capture: {exc}"
        return out

    if sync is None:
        from modules.netbox_client import sync_list_to_netbox as sync

    # THE LEASED ADDRESS, and it reached here because verification discovered
    # it. `mgmt_ip` is the caller's, and the caller is phase 2, which took it
    # from `verify_device`'s result rather than from the manifest -- the
    # manifest had none to give.
    device = {"hostname": hostname, "ip": mgmt_ip,
              # The subnet the address is really on, when it is known. For a
              # DHCP device the lease carries it and the manifest recorded it
              # at verification; absent, NetBox keeps its host-route last
              # resort, which is honest about not knowing.
              "prefix_len": (entry or {}).get("mgmt_prefix_len") or 0,
              "platform": (entry or {}).get("platform", ""), "role": "router"}
    result = sync(list_name, [device]) or {}

    if result.get("blocked"):
        out["reason"] = result.get("error") or "NetBox writes are disabled"
        return out

    # `ok` MEANS "THE SYNC RAN", NOT "THE DEVICES LANDED".
    #
    # `_sync_list_to_netbox_impl` returns `{"ok": True, ..., "failed": [...]}`
    # with every device in `failed`, and the previous caller checked only
    # `ok`. So a sync in which nothing was created reported success, and the
    # onboarding run said "Device onboarded" for a device NetBox has no
    # record of. Third instance of `success` meaning *no exception reached
    # the top*, after the background agent's 27 runs and
    # `bind_credentials_step`.
    failed = list(result.get("failed") or [])
    out["failed"] = failed
    if failed:
        out["reason"] = ("NetBox reported "
                         + "; ".join(f"{f.get('hostname', '?')}: "
                                     f"{f.get('error', 'no reason given')}"
                                     for f in failed[:3]))
        return out
    if not result.get("ok", False):
        out["reason"] = result.get("error") or "the sync did not report success"
        return out

    from modules.netbox_guard import get_created

    created = get_created(list_name) or {}
    out["created"] = [f"{endpoint}:{obj_id}"
                      for endpoint, objects in created.items()
                      for obj_id in (objects or {})]
    out["device_id"] = _device_id_from(created, hostname)
    out["ok"] = True
    return out


def _device_id_from(created: dict, hostname: str):
    """The NetBox id of the device just created, or ``None``.

    Pulled out because it is what `netbox_id` was declared for and never
    given: `create_netbox_step` collected every created id, returned them as
    strings, and `commit_step` never received them — so the manifest field
    existed and nothing could write it. The `next_ts` shape, in the identity
    map.
    """
    for entry in (created.get("dcim/devices") or []):
        if (entry.get("name") or "").lower() == hostname.lower():
            return entry.get("id")
    return None


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
    # PENDING. The device is in the manifest, in NetBox and in git, and
    # deliberately **not** in the inventory: a device in the inventory is one
    # the tool will poll, back up, drift-check, pool a connection for and
    # offer in bulk ops, and one that has never answered would read as
    # unreachable in nine places and mean nothing in any of them. That is
    # why stale devices were made inert rather than removed, and this is the
    # same animal arriving from the other direction.
    #
    # `promote_device()` is the exit, and it existed before this flag did.
    manifest.upsert_device(repo, identity, plan.hostname,
                           mgmt_ip=plan.mgmt_ip, platform=plan.platform,
                           pending=True,
                           address_source=plan.address_source,
                           mgmt_mac=plan.mgmt_mac,
                           reserved_address=plan.reservation_address)
    # THE BOOTSTRAP PARAMETERS ARE COMMITTED AS INTENT.
    #
    # Phase 1's entire product is a config the operator boots the node with,
    # and it was rendered, validated and **thrown away**: `render(plan)`'s
    # return value was discarded, the result carried no config, and the
    # artefact existed only on the review screen BEFORE Create. After the
    # toast cleared there was no way to get it back except abandoning and
    # re-creating -- which mints a new credential, so the staged one on disk
    # would no longer match what was booted.
    #
    # **The durable half and the usable half must have the same lifetime.**
    # The credential is durable and encrypted; the config carrying it was
    # ephemeral, which left the recoverable half the one you cannot use.
    #
    # So the config is not stored -- it is made RE-DERIVABLE. Everything
    # `render_bootstrap()` needs except the secret is ordinary intent and
    # goes in committed host_vars; the secret comes from the staging file.
    # The artefact is then available exactly while the credential is staged,
    # which is exactly the window in which it is useful: after rotation the
    # device has a different credential and the old config would not log in.
    # Same lifetime by construction rather than by two stores agreeing.
    bootstrap_intent = {
        "address":   plan.mgmt_ip,
        "mask":      plan.mgmt_mask,
        "interface": plan.manager_interface,
        "gateway":   plan.manager_gateway,
        "domain":    plan.domain,
        "platform":  plan.platform,
        # WHAT MAKES THE SET COMPLETE, recorded with it. A DHCP device has no
        # address and no mask by construction, so completeness cannot be
        # judged against the static shape -- `bootstrap_artifact()` read
        # `address` alone and reported a device created two minutes ago as one
        # "onboarded before these were recorded", whose remedy is to abandon
        # and re-create. That would have destroyed a correct device and
        # produced the identical result the second time.
        "source":    plan.address_source,
        "mac":       plan.mgmt_mac,
    }
    hostvars.write_committed(repo, dict(plan.host_vars or {},
                                        hostname=plan.hostname,
                                        bootstrap=bootstrap_intent))
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

    # ABANDON IS FOR AN UNFINISHED ONBOARDING, AND A PROMOTED DEVICE IS NOT
    # ONE. It is in the inventory, which is a different claim — that the
    # device is finished and belongs there — and removing it is the existing
    # delete path, not an onboarding undo.
    #
    # Refused rather than handled: `promoted and unfinished` was reachable
    # only while promotion ran second of three, and with it last that state
    # cannot occur. Teaching abandon about it would be building for a case
    # the ordering has removed — and `references()` does not check the
    # inventory row, so abandoning a promoted device would hand the name
    # back while the row remained.
    if (entry or {}).get("verified_at"):
        result["error"] = (
            f"'{hostname}' is promoted — it is in the inventory and phase 2 "
            f"has run for it, so this is not an unfinished onboarding. "
            f"Remove it through the device list rather than by abandoning "
            f"an onboarding that finished.")
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

            # `git()` RETURNS (rc, stdout, stderr) and never raises -- 127
            # when git is missing, 124 on timeout. Discarding it would have
            # this step report success on a commit that never happened,
            # which is precisely the failure this whole flow exists to
            # prevent. Found by auditing the four steps for discarded
            # return values after `adopt_identity` turned out to be one.
            rc, _out, err = _repo.git(repo, "add", "-A")
            if rc == 0:
                rc, _out, err = _repo.git(
                    repo, "-c", "user.email=nmas@local",
                    "-c", "user.name=NMAS", "commit", "-m",
                    f"abandon: {hostname} - onboarding withdrawn")
            if rc != 0:
                raise RuntimeError(err or f"git exited {rc}")
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

        # EVERY KEY THAT COULD HOLD THIS DEVICE'S CREDENTIAL, not just
        # `mgmt_ip`.
        #
        # This read `mgmt_ip` alone, guarded by `if mgmt_ip` -- and a pending
        # DHCP device has none until verification discovers it, so the override
        # keyed on the RESERVED address survived abandon untouched. Measured on
        # the live store: an `''` key left behind by a device created before
        # the key was corrected, still there after that device was abandoned.
        #
        # A staged credential outliving the device it was staged for is a
        # secret with no owner, in the one file where a device-specific
        # credential lives. Both keys are cleared, and the pair is listed so
        # the report says which.
        cleared = []
        for key in dict.fromkeys([(entry or {}).get("mgmt_ip", ""),
                                  (entry or {}).get("reserved_address", "")]):
            if key and credentials.has_device_override(key):
                if not dry_run:
                    credentials.clear_device_override(key)
                cleared.append(f"override {key}")
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


def promote_device(repo: str, hostname: str, list_name: str, *,
                   actor: str = "", device_type: str = "",
                   username: str = "", password: str = "",
                   secret: str = "") -> dict:
    """Phase 2's last step: the device answered, so it joins the inventory.

    **The exit from pending, and it was built with the flag rather than
    after it.** A state an operator cannot clear is the trap that was just
    removed from the identity map wearing a different name.

    This is what makes *"adds to inventory: after it answers"* true of the
    code and not only of the screen. `writes_devices_csv` was reported as
    `yes` on the review step while **no step wrote a row**, so a successful
    onboarding produced a device that was committed to git, created in
    NetBox, and absent from every inventory — invisible to the connection
    pool, backups, the terminal, bulk ops, drift and the AI tools, because
    `load_saved_devices()` is the single dispatch point for all of them.

    **It does not decide that the device answered.** The caller establishes
    that by reaching it; this records the consequence. A function that both
    tested reachability and promoted on its own finding would be its own
    witness.

    Identity is read-only on a NetBox-sourced list, so there the row is not
    written and the device arrives on the next refresh — reported, not
    silently skipped.
    """
    from modules.nsot import manifest as _m

    result = {"ok": False, "device": hostname, "list": list_name,
              "csv_row": False, "verified": False, "error": ""}

    identity, entry = _m.find_by_name(repo, hostname)
    if not identity:
        result["error"] = (f"'{hostname}' has no identity in this list's "
                           f"manifest — it was never onboarded")
        return result
    if not entry.get("onboarded_at"):
        result["error"] = (f"'{hostname}' is not a pending device — nothing "
                           f"to promote")
        return result

    # THE BOOTSTRAP CREDENTIAL MUST NOT BE THE ONE THAT LANDS HERE.
    #
    # It exists to reach the device once and is replaced by a device-
    # generated secret before onboarding finishes; `mint_bootstrap_credential`
    # states it is "never written to devices.csv or the credential store".
    # Promotion is the first call that writes a durable row, so it is where
    # that sentence stops being a convention. Refused rather than warned:
    # a throwaway password stored as the device's durable credential is a
    # wrong thing that would look exactly like a working one.
    staged = staged_bootstrap_credential(repo, hostname)
    if password and staged and password == staged:
        result["error"] = (
            "refusing to store the one-time bootstrap credential as this "
            "device's durable password — rotate it first, then promote")
        return result

    try:
        from modules.config import get_list_data_dir
        from modules.device import (DEVICE_CSV_FIELDS, load_saved_devices,
                                    write_devices_csv)
        from modules.inventory.source_config import is_netbox_sourced

        if is_netbox_sourced(list_name):
            result["csv_row"] = False
            result["note"] = ("identity is read-only on a NetBox-sourced "
                              "list; the device arrives on the next refresh")
        else:
            import os

            csv_path = os.path.join(get_list_data_dir(list_name), "devices.csv")
            rows = load_saved_devices(csv_path) if os.path.exists(csv_path) else []
            if any((r.get("hostname") or "").lower() == hostname.lower()
                   for r in rows):
                result["csv_row"] = False
                result["note"] = "already in the inventory"
            else:
                from modules.device import fernet

                row = {f: "" for f in DEVICE_CSV_FIELDS}
                row.update({
                    "hostname": hostname,
                    "ip": entry.get("mgmt_ip", ""),
                    "device_type": device_type or "cisco_xe",
                    "username": username or "admin",
                    "password": (fernet.encrypt(password.encode()).decode()
                                 if password else ""),
                    "secret": (fernet.encrypt(secret.encode()).decode()
                               if secret else ""),
                    "device_uid": identity,
                    "platform": entry.get("platform", ""),
                })
                write_devices_csv(rows + [row], csv_path)
                result["csv_row"] = True
    except Exception as exc:                   # noqa: BLE001
        log.exception("promote: inventory write failed for %r", hostname)
        result["error"] = f"could not add to the inventory: {exc}"
        return result

    marked = _m.mark_verified(repo, identity, actor=actor)
    if not marked.get("ok"):
        result["error"] = marked.get("error", "could not mark verified")
        return result
    result["verified"] = True
    result["verified_at"] = marked.get("verified_at", "")
    result["ok"] = True
    return result


# ---------------------------------------------------------------------------
# Phase 2: reach the device, and diagnose when you cannot
# ---------------------------------------------------------------------------

#: What a verification attempt established. **Three outcomes, not two.**
#:
#: `ANSWERED` is a fact about the device: it proves the management interface
#: was right, the node booted the generated config, and the address is the
#: one the tool was told.
#:
#: The other two prove nothing about WHY. A device that did not answer may
#: have a mistyped interface, may never have been booted with the config, or
#: may be at a different address — and the tool cannot tell which from the
#: outside. So the state records **what happened**, and the causes below are
#: offered as possibilities in the order they are worth checking. Recording
#: "wrong interface" on a timeout would be the classifier reading a
#: connection failure as a device verdict, which is the mistake the rotation
#: path already had to correct.
ANSWERED = "answered"
REFUSED_CREDENTIAL = "answered_but_refused_the_credential"
DID_NOT_ANSWER = "did_not_answer"


#: The only credential source that is correct during onboarding. An
#: ALLOWLIST of one, deliberately: a denylist of suspicious sources has to
#: anticipate every source `credentials.resolve()` might grow, and the one it
#: did not anticipate -- `profile:default` -- walked straight past it.
STAGED_CREDENTIAL_SOURCE = "device-override"


def _causes(state: str, mgmt_ip: str, interface: str, repo: str,
            hostname: str, cred_source: str = "") -> list:
    """Likely causes, most-worth-checking first, each with what settles it.

    Ordered by *what the operator cannot otherwise find out*. The management
    interface is first because it is the one thing the wizard could not
    validate at plan time -- a well-formed name for a port the model does
    not have renders, boots and goes unreachable, and nothing before this
    moment could have caught it.
    """
    console = ("On the node's console (`docker logs`/`telnet` to it, or "
               "`containerlab exec`), run:")
    if state == REFUSED_CREDENTIAL:
        causes = []
        # ANYTHING THAT IS NOT THE STAGED OVERRIDE IS A FINDING, and the
        # condition used to be a LIST of suspicious sources -- `none`,
        # `unresolved`, `caller` -- which is a denylist, so
        # `profile:default` walked past it. Measured 2026-09-24: the tool
        # reported `credential_source: "profile:default"`, knew perfectly well
        # it had fallen back to the list's default profile, and printed *"only
        # the credential is wrong"* with a console command.
        #
        # **A device mid-onboarding falling back to a profile is always
        # wrong**: the whole point of the staged bootstrap credential is that
        # the device has never had any other, so a profile cannot be right
        # even by accident. An allowlist of one says that; a denylist has to
        # anticipate every source `resolve()` might grow.
        if cred_source != STAGED_CREDENTIAL_SOURCE:
            # FIRST, because it is the one the tool can answer about itself.
            # Measured 2026-09-24: Netmiko with the staged password reached
            # the device on the first try while phase 2 reported
            # "Authentication to device failed" -- the credential was right
            # and never reached the connection. The diagnosis was correct
            # about the evidence ("something answered, so only the
            # credential is wrong") and wrong about the cause.
            fell_back = str(cred_source or "").startswith("profile:")
            causes.append({
                "cause": ("the tool fell back to a profile instead of the "
                          "staged bootstrap credential" if fell_back
                          else "the tool did not use the credential it holds"),
                "why": (f"the credential offered came from '{cred_source}' "
                        f"rather than the device override onboarding staged. "
                        + ("A device mid-onboarding has never held any "
                           "credential but the staged one, so a profile "
                           "cannot be right here even by accident: the "
                           "override is missing or is stored under a "
                           "different key than " + (mgmt_ip or "this address")
                           + ". "
                           if fell_back else "")
                        + f"Check that a credential resolves for {mgmt_ip}"),
                "command": "python scripts/nmas-check-credential "
                           f"--ip {mgmt_ip}",
                "where": "On the NMAS host:",
            })
        return causes + [{
            "cause": "the credential was rotated or never applied",
            "why": ("something answered SSH at this address, so the "
                    "interface and the address are right — only the "
                    "credential is wrong"),
            "command": "show running-config | include ^username",
            "where": console,
        }]

    return [
        {
            "cause": f"the management address is not on {interface or 'the chosen interface'}",
            "why": ("the interface name is checked for spelling and **not** "
                    "against the device, because the device did not exist "
                    "when the config was generated. A valid name for a port "
                    "this model does not have renders and boots and is "
                    "unreachable — this is the first thing to rule out"),
            "command": "show ip interface brief",
            "where": console,
        },
        {
            "cause": "the node did not boot the generated config",
            "why": ("vrnetlab concatenates its own user line ahead of the "
                    "startup config; if the launch patch is missing the "
                    "node comes up on its injected credential and reports "
                    "healthy either way"),
            "command": "show running-config | include ^hostname|^username",
            "where": console,
        },
        {
            "cause": f"the address {mgmt_ip} is not the one it booted with",
            "why": "nothing has confirmed the address since it was typed",
            "command": f"ping {mgmt_ip}",
            "where": "From the NMAS host:",
        },
    ]


def _recovery(repo: str, hostname: str) -> dict:
    """How to get back in while the bootstrap credential is still staged.

    This is the reason 4C.2 stages it at all: between the device booting
    with the value and rotation replacing it, it is the only way in. The
    command is given with the **real repo path** rather than a placeholder,
    because an operator reading this is already having a bad day.
    """
    staged = staged_bootstrap_credential(repo, hostname)
    if not staged:
        return {"available": False,
                "note": ("no bootstrap credential is staged for this device "
                         "— either rotation completed and cleared it, or "
                         "onboarding never reached the credential step")}
    return {
        "available": True,
        "note": ("the one-time bootstrap credential is still staged. It is "
                 "what the node booted with, and the console accepts it."),
        "command": (
            'python -c "from modules.nsot.onboard import '
            'staged_bootstrap_credential; '
            f"print(staged_bootstrap_credential('{repo}', '{hostname}'))\""),
    }


def discover_dhcp_address(mac: str, reserved: str = "", kea=None) -> dict:
    """The address a DHCP device **actually holds**, from Kea's lease.

    ``{"ok", "address", "source", "reserved", "disagreement", "reason"}``

    **The lease, never the reservation.** A reservation is a statement of
    intent; a lease is a fact about the device. They are normally equal, which
    is the point of requiring one — and they can differ: a reservation edited
    after the device leased, or a device still holding an older lease.

    So when they disagree this **refuses and names both**. It is not a
    tiebreak: the tool cannot know which is right, and picking one would write
    an address into the inventory that something else disagrees with — two
    stores disagreeing, which is the shape the reservation precondition exists
    to prevent in the first place.

    And it never falls back to the reservation when there is no lease. *"What
    the device has"* has no answer then, and answering *"probably this"* is how
    an inventory acquires an address nobody verified.
    """
    try:
        if kea is None:
            from modules.integrations.kea import KeaIntegration

            kea = KeaIntegration()
        lease = kea.lease_for(mac)
    except Exception as exc:                   # noqa: BLE001
        log.warning("onboard: lease lookup failed for %s: %s", mac, exc)
        lease = {"state": "unknown", "address": "",
                 "error": f"{type(exc).__name__}: {exc}"}

    if lease["state"] == "unknown":
        return {"ok": False, "address": "", "source": "", "prefix_length": 0,
                "reserved": reserved,
                "disagreement": False, "reason": (
                    f"Kea could not be asked which address {mac} holds"
                    + (f" ({lease['error']})" if lease.get("error") else "")
                    + ". Refusing rather than using the reservation: that is "
                      "what the address was meant to be, not what the device "
                      "has.")}
    if lease["state"] != "found":
        return {"ok": False, "address": "", "source": "", "prefix_length": 0,
                "reserved": reserved,
                "disagreement": False, "reason": (
                    f"Kea holds no active lease for {mac}. The device has not "
                    "asked yet, or is not on the segment Kea answers on — "
                    "either way there is no address to verify against, and the "
                    "reservation is not a substitute for one.")}

    if reserved and lease["address"] != reserved:
        return {"ok": False, "address": lease["address"], "source": "lease",
                "prefix_length": lease.get("prefix_length") or 0,
                "reserved": reserved, "disagreement": True, "reason": (
                    f"the lease and the reservation disagree: Kea has {mac} on "
                    f"{lease['address']} and the reservation says {reserved}. "
                    "This is a finding, not a tiebreak — one of them is stale, "
                    "and writing either into the inventory would make two "
                    "stores disagree about the same device.")}

    return {"ok": True, "address": lease["address"], "source": "lease",
            # The subnet the lease belongs to. NetBox described the interface
            # as a /32 without it, which is a claim about the network rather
            # than about the address.
            "prefix_length": lease.get("prefix_length") or 0,
            "reserved": reserved, "disagreement": False, "reason": ""}


def verify_device(repo: str, hostname: str, list_name: str, *,
                  mgmt_ip: str = "", username: str = "admin",
                  password: str = "", secret: str = "",
                  device_type: str = "cisco_xe", interface: str = "",
                  online=None, reach=None, kea=None) -> dict:
    """Reach the device. **Reaching is the verification; failing is not.**

    Returns ``{"state", "answered", "prompt", "causes", "recovery",
    "error"}``.

    `online` and `reach` are injected so the whole diagnosis can be tested
    without a network, and so that this function does exactly one thing:
    turn two observations into an honest account of what is known.
    """
    from modules.nsot import manifest as _m

    identity, entry = _m.find_by_name(repo, hostname)
    if not identity:
        return {"state": DID_NOT_ANSWER, "answered": False, "causes": [],
                "recovery": {"available": False},
                "error": f"'{hostname}' is not in this list's manifest"}

    mgmt_ip = mgmt_ip or (entry or {}).get("mgmt_ip", "")

    # A DHCP DEVICE'S ADDRESS IS DISCOVERED, NOT READ FROM THE MANIFEST.
    #
    # The tool never wrote it, so `mgmt_ip` is empty here by construction, and
    # everything downstream -- the credential lookup, `online()`, `reach()` --
    # would have been handed "" and reported `did_not_answer` with a list of
    # causes every one of which is wrong.
    #
    # It comes from Kea's LEASE, not the reservation: the reservation is what
    # the address was meant to be and the lease is what the device has. A
    # disagreement refuses and names both rather than picking one.
    dhcp_note = ""
    dhcp_prefix = 0
    if not mgmt_ip and (entry or {}).get("address_source") == "dhcp":
        found = discover_dhcp_address((entry or {}).get("mgmt_mac", ""),
                                      (entry or {}).get("reserved_address", ""),
                                      kea=kea)
        if not found["ok"]:
            return {"state": DID_NOT_ANSWER, "answered": False, "causes": [],
                    "recovery": {"available": False},
                    "error": found["reason"]}
        mgmt_ip = found["address"]
        dhcp_prefix = found.get("prefix_length") or 0
        dhcp_note = (f"address discovered from Kea's lease for "
                     f"{(entry or {}).get('mgmt_mac', '')}"
                     + (f", on a /{dhcp_prefix}" if dhcp_prefix else ""))

    # RESOLVE THE CREDENTIAL THE TOOL ALREADY HOLDS.
    #
    # The route took `password` from the request body and the banner sends
    # none -- correctly, since a browser must not carry a credential. So an
    # empty password reached Netmiko and the device refused it, and phase 2
    # reported "Authentication to device failed" while the right credential
    # sat in the store the whole time.
    #
    # `resolve()` is the reader, and the important part is WHICH store: the
    # device override is keyed on the management IP and written by
    # `bind_credentials_step`, so it is found **without touching the
    # inventory**. A pending device has no `devices.csv` row by design, so
    # anything resolving through `load_saved_devices()` cannot find it --
    # that would be the approval deadlock again, phase 2 needing the row
    # only phase 2 writes.
    cred_source = "caller"
    if not password:
        try:
            from modules import credentials

            found = credentials.resolve(mgmt_ip)
            if found.get("ok"):
                username = found.get("username") or username
                password = found.get("password") or ""
                secret = secret or found.get("secret") or ""
                cred_source = found.get("source", "resolver")
            else:
                cred_source = "none"
        except Exception as exc:               # noqa: BLE001
            log.error("verify: could not resolve a credential for %r: %s",
                      hostname, exc)
            cred_source = "unresolved"

    if online is None:
        from modules.connection import is_device_online as online
    if reach is None:
        from modules.connection import verify_device_connection as reach

    prompt, state, error = "", DID_NOT_ANSWER, ""
    try:
        if online(mgmt_ip):
            try:
                prompt = reach(mgmt_ip, username, password, secret,
                               device_type)
                state = ANSWERED
            except Exception as exc:           # noqa: BLE001
                # Something is at the address and would not let us in. That
                # is a different fact from silence, and it rules out the two
                # causes an operator would otherwise start with.
                state = REFUSED_CREDENTIAL
                error = str(exc)
        else:
            error = f"no response from {mgmt_ip} on ICMP or TCP/22"
    except Exception as exc:                   # noqa: BLE001
        log.exception("verify: reachability check failed for %r", hostname)
        state = DID_NOT_ANSWER
        error = f"the reachability check itself failed: {exc}"

    return {
        "state": state,
        "answered": state == ANSWERED,
        "prompt": prompt,
        "mgmt_ip": mgmt_ip,
        # WHERE THE ADDRESS CAME FROM. For a DHCP device the tool never wrote
        # it, so "the address it verified" is a discovered fact and reporting
        # it as though it had been configured would hide which store to trust.
        "address_note": dhcp_note,
        # 0 means unknown, never 32. A host route for an address that is
        # really on a /24 is NetBox being wrong about the network.
        "prefix_length": dhcp_prefix,
        # WHICH credential was tried, never the value. "device-override"
        # means the one onboarding staged; "none" means the tool had none
        # and connected with an empty password, which is the failure this
        # field exists to make visible rather than diagnosable only by
        # reading code.
        "credential_source": cred_source,
        "interface": interface,
        "causes": [] if state == ANSWERED
                  else _causes(state, mgmt_ip, interface, repo, hostname,
                               cred_source),
        "recovery": {"available": False} if state == ANSWERED
                    else _recovery(repo, hostname),
        "error": error,
    }


def verify_and_promote(repo: str, hostname: str, list_name: str, *,
                       actor: str = "", **kw) -> dict:
    """Phase 2 end to end: reach the device, and promote it if it answered.

    **Reaching the device is what verifies the management interface.** There
    is no earlier moment at which that can be established, which is why the
    wizard says the interface is unverified until this runs rather than
    implying the field was checked.

    Promotion is a separate function and is only called on `ANSWERED`, so
    the thing that decides and the thing that records stay apart.
    """
    promote_kw = {k: kw.pop(k) for k in ("device_type", "username",
                                         "password", "secret") if k in kw}
    seen = verify_device(repo, hostname, list_name, **dict(kw, **promote_kw))
    out = {"verify": seen, "promoted": False, "ok": False}
    if not seen.get("answered"):
        out["error"] = seen.get("error") or "the device did not answer"
        return out

    promoted = promote_device(repo, hostname, list_name, actor=actor,
                              **promote_kw)
    out["promote"] = promoted
    out["promoted"] = bool(promoted.get("ok"))
    out["ok"] = out["promoted"]
    if not out["ok"]:
        out["error"] = promoted.get("error", "promotion failed")
        return out

    # NETBOX, LAST, AND NEVER FATAL TO THE PROMOTION.
    #
    # The device has answered and is in the inventory; those are facts about
    # the network and they are already recorded. A NetBox write that fails
    # afterwards is a synchronisation problem with an external system, and
    # failing the whole run for it would put the device back in a pending
    # state it has demonstrably left.
    #
    # Deferred rather than skipped when there is no capture yet, and the
    # distinction is reported: `deferred` says the import has not run and
    # why, where a bare skip would read as "nothing to do".
    out["netbox"] = create_netbox_record(repo, hostname, list_name)
    if out["netbox"].get("device_id") is not None:
        from modules.nsot import manifest as _m

        identity, _entry = _m.find_by_name(repo, hostname)
        if identity:
            _m.upsert_device(repo, identity, hostname,
                             netbox_id=out["netbox"]["device_id"])
    return out


def bootstrap_artifact(repo: str, hostname: str) -> dict:
    """Re-render the config a pending device was onboarded with.

    **Nothing stores the config, and that is deliberate.** It is derived
    from committed intent (address, mask, interface, gateway, domain,
    platform) plus the staged bootstrap credential — so it exists exactly
    while the credential does, which is exactly the window in which it is
    useful. After rotation the device holds a different credential and the
    old config would not log in; producing it then would be handing over
    something that looks usable and is not.

    **Why not `intended/`.** That directory is committed, so writing this
    there would put the bootstrap credential in git in the clear, on a repo
    that may have a remote. Masking it would make the file useless for its
    one purpose — a node cannot boot a masked password — so `intended/` is
    wrong in both directions, and neither is a matter of preference.

    Returns ``{"ok", "config", "reason"}``.
    """
    from modules.nsot import hostvars

    staged = staged_bootstrap_credential(repo, hostname)
    if not staged:
        return {"ok": False, "config": "", "reason": (
            f"no bootstrap credential is staged for '{hostname}'. Either "
            f"rotation completed and cleared it — in which case the device "
            f"has a different credential and this config would no longer "
            f"log in — or onboarding never reached the credential step.")}

    committed = hostvars.read_committed(repo, hostname) or {}
    params = committed.get("bootstrap") or {}

    # COMPLETENESS IS JUDGED PER SOURCE. A DHCP device's committed set is
    # source + interface + mac + domain, and it is complete without an
    # address; checking `address` alone made that state indistinguishable from
    # a device onboarded before any of these were recorded, and reported it
    # with the one explanation the check knew — *abandon and re-create* —
    # which would have destroyed a correct device and produced the identical
    # result the second time.
    #
    # A document with NO source key predates the field: `address` present then
    # means static and is complete, and `address` absent is the genuine legacy
    # state the message below was written for. So the legacy message survives,
    # and now only fires when it is true.
    source = (params.get("source") or ("static" if params.get("address")
                                       else "")).strip()
    if source == "dhcp":
        if not params.get("interface"):
            return {"ok": False, "config": "", "reason": (
                f"'{hostname}' is a DHCP device with no committed interface. "
                "The address comes from Kea, but the interface it lands on is "
                "chosen and never defaulted, so the config cannot be "
                "re-derived without it.")}
    elif not params.get("address"):
        return {"ok": False, "config": "", "reason": (
            f"'{hostname}' has no committed bootstrap parameters, so the "
            f"config cannot be re-derived. Devices onboarded before these "
            f"were recorded are in this state; abandon and re-create.")}

    try:
        from modules.nsot.bootstrap_config import render_bootstrap

        config = render_bootstrap(
            params.get("platform", ""), hostname=hostname, username="admin",
            secret=staged, domain=params.get("domain", "rcn.lab"),
            manager_interface=params.get("interface", ""),
            # The same explicit sentinel the plan uses, so a re-render is
            # byte-identical to what the node booted.
            manager_address=("dhcp" if source == "dhcp"
                             else params.get("address", "")),
            manager_mask=("dhcp" if source == "dhcp"
                          else params.get("mask", "")),
            manager_gateway=params.get("gateway", ""))
    except Exception as exc:                   # noqa: BLE001
        log.error("onboard: could not re-render bootstrap for %r: %s",
                  hostname, exc)
        return {"ok": False, "config": "", "reason": str(exc)}

    return {"ok": True, "config": config, "reason": ""}


# ---------------------------------------------------------------------------
# Phase 2, in full
# ---------------------------------------------------------------------------

#: The order, and **promotion is last because it is the claim**.
#:
#: 4C.3 ordered phase 1 by what a failure leaves behind and put the only
#: durable, publishing step last among the fallible. Phase 2 had promotion
#: SECOND of three, so the one step that changes what the operator sees ran
#: before the four that do the work — and a device could sit promoted with a
#: throwaway password, no golden, no NetBox record and the read-write
#: community still on it, reporting `ok: true`.
#:
#: Two independent arguments put promotion last, which is why it is not a
#: preference:
#:
#: 1. **4C.3's rule, unchanged.** The visible, durable change goes last.
#: 2. **Rotation forces it anyway.** The CSV row must carry the ROTATED
#:    credential, so it cannot be written before rotation without being
#:    wrong — which is exactly what happened.
#:
#: `promoted` is therefore not a state a partial run can reach. See
#: `test_onboard_phase_two.py`, whose control moves promotion earlier and
#: asserts the suite notices.
PHASE_TWO_STEPS = ("verify", "capture", "rotate", "remove_rw", "golden",
                   "netbox", "promote")


def capture_config(mgmt_ip: str, username: str, password: str, secret: str,
                   device_type: str) -> dict:
    """Read the device's running config. Returns ``{"ok", "config", "error"}``.

    Held **in memory** by the caller until the RW community has been removed
    from the device — the golden is the approved record of what a device
    should look like, and its first version must not be a state we
    deliberately do not want, preserved in history where a remote may
    publish it.
    """
    from modules.connection import connection_params

    try:
        from netmiko import ConnectHandler

        conn = ConnectHandler(**connection_params(
            {"device_type": device_type, "ip": mgmt_ip, "username": username},
            password=password, secret=secret))
        try:
            conn.enable()
            config = conn.send_command("show running-config",
                                       read_timeout=_read_timeout())
        finally:
            conn.disconnect()
    except Exception as exc:                   # noqa: BLE001
        log.error("phase2: capture failed for %s: %s", mgmt_ip, exc)
        return {"ok": False, "config": "", "error": str(exc)}

    if len(config.splitlines()) < 10:
        # The same guard the rotation path applies: a short read is a failed
        # command, not a small config, and committing it would replace a
        # device's record with an error message.
        return {"ok": False, "config": config, "error": (
            f"the capture was {len(config.splitlines())} lines — that is a "
            f"failed read, not a configuration")}
    return {"ok": True, "config": config, "error": ""}


def _read_timeout() -> int:
    from modules.settings_schema import get_setting

    return int(get_setting("nsot_config_read_timeout", 120) or 120)


def remove_rw_communities(mgmt_ip: str, username: str, password: str,
                          secret: str, device_type: str,
                          config: str) -> dict:
    """Send the `no snmp-server community …` lines, verbatim.

    Wires `rw_removal_plan()`, which had no production caller. The lines are
    the device's own, verbatim: a rebuilt line drops the ACL, and
    `no snmp-server community public RW` against a device whose line reads
    `… RW 99` is a command that does not match.

    Returns ``{"ok", "removed", "kept", "error"}``. **Nothing to remove is a
    success** — a vrnetlab node arrives with an RW community, a real one may
    not, and refusing would make the common case an error.
    """
    plan = rw_removal_plan(config)
    out = {"ok": True, "removed": [], "kept": plan["keep"], "error": ""}
    if not plan["remove"]:
        return out

    from modules.connection import connection_params

    try:
        from netmiko import ConnectHandler

        conn = ConnectHandler(**connection_params(
            {"device_type": device_type, "ip": mgmt_ip, "username": username},
            password=password, secret=secret))
        try:
            conn.enable()
            conn.send_config_set(plan["remove"], read_timeout=_read_timeout())
        finally:
            conn.disconnect()
    except Exception as exc:                   # noqa: BLE001
        log.error("phase2: RW removal failed for %s: %s", mgmt_ip, exc)
        return {"ok": False, "removed": [], "kept": plan["keep"],
                "error": str(exc)}

    out["removed"] = list(plan["remove"])
    return out


def run_phase_two(repo: str, hostname: str, list_name: str, *, actor: str = "",
                  actor_kind: str = "", online=None, reach=None,
                  capture=None, rotate=None, remove_rw=None, save=None,
                  netbox=None, promote=None) -> dict:
    """Finish onboarding a pending device. **`ok` means all of it.**

    Returns ``{"ok", "steps", "remaining", "reason", ...}`` with one entry
    per :data:`PHASE_TWO_STEPS`. A step that did not run is reported as not
    run, with the reason the previous one gave — a phase that stops halfway
    and reports the steps that did succeed is the defect this replaces.

    **A partial run leaves the device PENDING.** Promotion is the last step
    and is the only thing that clears `verified_at` and writes the inventory
    row, so there is no path to "promoted" that does not pass through every
    step before it. That is not a convention; it is the order, and a control
    in the tests moves promotion earlier and asserts the suite notices.

    Every collaborator is injected for the same reason `run_onboarding`'s
    are: the ordering and the failure behaviour are the thing under test,
    and a test that has to reach a device to check them is not a test.
    """
    from modules.nsot import manifest as _m

    result = {"ok": False, "device": hostname, "list": list_name,
              "steps": [], "remaining": [], "reason": "", "promoted": False}

    def _step(name, ok, detail="", **extra):
        row = {"step": name, "ok": bool(ok), "detail": detail}
        row.update(extra)
        result["steps"].append(row)
        return bool(ok)

    def _finish():
        """**The one place `ok` is decided, and it is decided FROM the steps.**

        `_stop` used to set `result["ok"] = False` itself, so the computation
        below was never the thing that decided anything — and a control that
        forced `ok = True` at the end passed the whole suite. A field named
        for the whole must be computed from the whole, or the next edit sets
        it beside them and nothing notices.
        """
        result["ok"] = bool(result["steps"]) and all(r["ok"]
                                                     for r in result["steps"])
        return result

    def _stop(name, reason):
        """Record why, and name every step that therefore did not run."""
        result["reason"] = reason
        ran = {r["step"] for r in result["steps"]}
        for step in PHASE_TWO_STEPS:
            if step not in ran:
                result["steps"].append({"step": step, "ok": False,
                                        "detail": "did not run"})
                result["remaining"].append({"step": step, "why": reason})
        return _finish()

    identity, entry = _m.find_by_name(repo, hostname)
    if not identity:
        return _stop("verify", f"'{hostname}' is not in this list's manifest")
    if entry.get("verified_at"):
        return _stop("verify", f"'{hostname}' is already promoted — phase 2 "
                               f"has run for it")

    mgmt_ip = entry.get("mgmt_ip", "")
    platform = entry.get("platform", "")
    try:
        from modules.nsot.platform import netmiko_type_for_dialect

        device_type = netmiko_type_for_dialect(platform)
    except Exception as exc:                   # noqa: BLE001
        return _stop("verify", f"no Netmiko driver for '{platform}': {exc}")

    # ---- 1. verify ------------------------------------------------------
    seen = (verify_device if online is None and reach is None
            else verify_device)(repo, hostname, list_name, mgmt_ip=mgmt_ip,
                                device_type=device_type, online=online,
                                reach=reach)
    result["verify"] = seen
    if not _step("verify", seen.get("answered"), seen.get("state", ""),
                 credential_source=seen.get("credential_source", "")):
        return _stop("verify", seen.get("error") or "the device did not answer")

    # ADOPT THE ADDRESS VERIFICATION ACTUALLY USED.
    #
    # For a DHCP device the manifest had none and `verify_device` discovered it
    # from Kea's lease. Without this line every step below -- the credential
    # lookup, the capture, the RW removal, the golden, the CSV row -- would go
    # on using the empty string the manifest gave, and the six of them would
    # fail for a reason none of them could name.
    #
    # `verify_device` is the one place that resolves it, so this is adoption
    # rather than a second derivation.
    mgmt_ip = seen.get("mgmt_ip") or mgmt_ip
    mgmt_prefix = seen.get("prefix_length") or 0
    result["mgmt_ip"] = mgmt_ip
    if seen.get("address_note"):
        result["address_note"] = seen["address_note"]
        # Recorded on the manifest so the pending banner, the inventory and
        # NetBox all name one address afterwards -- the device holds it now,
        # and until this point nothing in the tool did.
        try:
            from modules.nsot import manifest as _mm

            identity = _mm.find_by_name(repo, hostname)[0]
            if identity:
                _mm.upsert_device(repo, identity, hostname, mgmt_ip=mgmt_ip,
                                  mgmt_prefix_len=mgmt_prefix)
        except Exception as exc:               # noqa: BLE001
            log.warning("onboard: could not record %s's leased address: %s",
                        hostname, exc)

    # NO STEP PASSES A CREDENTIAL TO ANOTHER STEP. Each reads it from the
    # override, which is where phase 1 put it and where rotation replaces
    # it — so none of them can pass an empty one, which is how the CSV row
    # came to hold nothing.
    def _cred():
        from modules import credentials

        found = credentials.resolve(mgmt_ip) or {}
        return (found.get("username", "admin"), found.get("password", ""),
                found.get("secret", ""))

    user, pw, sec = _cred()

    # ---- 2. capture, held in memory -------------------------------------
    cap = (capture or capture_config)(mgmt_ip, user, pw, sec, device_type)
    if not _step("capture", cap.get("ok"),
                 f"{len(cap.get('config', '').splitlines())} lines"):
        return _stop("capture", cap.get("error") or "the capture failed")
    config = cap["config"]

    # ---- 3. rotate, and record in the same act ---------------------------
    # A DEVICE DICT CARRIES ITS CREDENTIALS FERNET-ENCRYPTED, like a CSV row.
    #
    # The first version omitted them entirely, and `preflight` refused with
    # `failed_before_any_change` — the lockout defence working, and the
    # result said only that. The check that failed was
    # `live_user_line_read`: `live_user_line()` does
    # `decrypt_field(device.get("password", ""))` and opens a session,
    # because the program depends on whether the account holds a `secret` or
    # a `password` **on the device now**, not in a stored capture. With no
    # password key it connected with "" and the device refused it.
    #
    # The deadlock reappearing at a check the parameterisation did not
    # reach: `device`, `capture` and `record` covered where the device comes
    # from and where the credential is written, and not the credential the
    # device dict itself carries. Encrypted rather than plaintext because
    # that is the established shape — the inventory adapter returns
    # credentials still encrypted "because callers decrypt at use", and
    # `decrypt_field` is what this one calls.
    from modules.device import fernet

    device_row = {"hostname": hostname, "ip": mgmt_ip, "username": user,
                  "device_type": device_type, "platform": platform,
                  "password": fernet.encrypt(pw.encode()).decode() if pw else "",
                  "secret": fernet.encrypt(sec.encode()).decode() if sec else ""}
    rot = (rotate or finish_bootstrap)(
        repo, hostname, list_name,
        confirmed_fingerprint=_phase_two_confirmation(),
        actor=actor, actor_kind=actor_kind,
        device=device_row, capture=config, record="override")
    result["rotate"] = rot
    # THE STATE IS NOT THE REASON, and the reason is not only in the checks.
    #
    # The first version read `preflight_checks` alone, so a refusal from any
    # of rotate's OTHER exits — the confirmation mismatch, an entry-kind
    # recheck, a rejected push — reported `failed_checks: []` beside
    # `failed_before_any_change`: *something stopped me and nothing failed*,
    # which is worse than the state before it, because that one at least did
    # not claim to know.
    #
    # `rotate()` calls `_step(name, False, detail)` on **every** refusal, so
    # its `steps` cover every exit by construction where a hand-maintained
    # list of fields cannot. Checks are still carried, for the detail they
    # add when it IS a preflight refusal.
    refused = _rotation_refusals(rot)
    if not _step("rotate", rot.get("rotated"), rot.get("state", ""),
                 failed_checks=[c for c in (rot.get("preflight_checks") or [])
                                if not c["ok"]],
                 failed_steps=refused):
        base = rot.get("reason") or "the credential was not rotated"
        # Only what the reason does not already say. `_rotation_refusals()`
        # falls back to the reason when the steps name nothing, and appending
        # it to itself produced "the device refused — the device refused".
        extra = "; ".join(r for r in refused if r not in base)
        return _stop("rotate", base + (f" — {extra}" if extra else ""))

    # The credential changed, so everything after this reads it again.
    user, pw, sec = _cred()

    # ---- 4. remove the RW community --------------------------------------
    rw = (remove_rw or remove_rw_communities)(mgmt_ip, user, pw, sec,
                                              device_type, config)
    result["remove_rw"] = rw
    if not _step("remove_rw", rw.get("ok"),
                 f"{len(rw.get('removed') or [])} removed, "
                 f"{len(rw.get('kept') or [])} kept"):
        return _stop("remove_rw", rw.get("error") or "the removal failed")

    # ---- 5. the golden, captured AFTER the removal ------------------------
    # Re-read rather than edited: the golden must be what the device
    # actually holds, and a config with the RW lines filtered out of it is a
    # claim about the device rather than a record of it.
    post = (capture or capture_config)(mgmt_ip, user, pw, sec, device_type)
    if not _step("golden", post.get("ok"), "re-read after the removal"):
        return _stop("golden", post.get("error")
                     or "the device could not be re-read")
    saved = (save or _save_first_golden)(list_name, hostname, mgmt_ip,
                                         platform, post["config"], actor)
    result["golden"] = saved
    if not saved.get("ok"):
        result["steps"][-1]["ok"] = False
        result["steps"][-1]["detail"] = saved.get("error", "")
        return _stop("golden", saved.get("error") or "the golden was not saved")

    # ---- 6. NetBox, now that there is something to import ----------------
    nb = (netbox or create_netbox_record)(repo, hostname, list_name)
    result["netbox"] = nb
    if not _step("netbox", nb.get("ok"),
                 nb.get("reason") or f"{len(nb.get('created') or [])} object(s)"):
        return _stop("netbox", nb.get("reason") or "the NetBox record failed")
    if nb.get("device_id") is not None:
        _m.upsert_device(repo, identity, hostname, netbox_id=nb["device_id"])

    # ---- 7. promote, LAST ------------------------------------------------
    user, pw, sec = _cred()
    prom = (promote or promote_device)(repo, hostname, list_name, actor=actor,
                                       device_type=device_type, username=user,
                                       password=pw, secret=sec)
    result["promote"] = prom
    if not _step("promote", prom.get("ok"), prom.get("error", "")):
        return _stop("promote", prom.get("error") or "promotion failed")

    result["promoted"] = True
    return _finish()


def _rotation_refusals(rot: dict) -> list:
    """Why a rotation refused, from every exit it has. **Never empty.**

    `rotate()` names each refusal with `_step(name, False, detail)`, and
    those cover its exits by construction — preflight, the confirmation
    fingerprint, the entry-kind recheck, the push, the verify. Reading one
    field instead (`preflight_checks`) described one exit and reported
    silence for the rest.

    A **successful** rotation returns `[]` — the rule below is about
    refusals, and applying it to every result made a success report a
    defect in its own reporting.

    **An empty list beside a failure state is impossible here, not merely
    unlikely**: if the steps name nothing, this falls back to the reason,
    then to the state, and finally says plainly that the refusal was
    unattributed — which is a defect report rather than a blank. A result
    claiming "something stopped me and nothing failed" is worse than one
    that admits it does not know.
    """
    # A rotation that WORKED refuses nothing, and must say so. The
    # never-empty rule below is about refusals; without this guard it
    # applied to every result, so a success reported "named no step — that
    # is a defect", which is the invariant eating the distinction it was
    # built to protect. Caught by the control, not by the three tests
    # asserting a refusal is always named: a function that always returns
    # something satisfies all of them.
    if rot.get("rotated"):
        return []
    refused = [f"{st.get('name')}: {st.get('detail')}".rstrip(": ")
               for st in (rot.get("steps") or []) if not st.get("ok")]
    # BOTH SOURCES, not whichever one happens to be populated. A preflight
    # refusal names the failing check in `preflight_checks` and summarises
    # it in a step; another exit names only a step. Reading one described
    # one exit and reported silence for the rest, which is the defect this
    # function replaced — reading both cannot miss, and merging rather than
    # choosing means neither has to be the canonical one.
    for check in (rot.get("preflight_checks") or []):
        if check.get("ok"):
            continue
        named = f"{check.get('name')}: {check.get('detail')}".rstrip(": ")
        if not any(check.get("name") in r for r in refused):
            refused.append(named)
    if refused:
        return refused
    if rot.get("reason"):
        return [rot["reason"]]
    state = rot.get("state") or "unknown"
    return [f"the rotation refused in state {state!r} and named no step — "
            f"that is a defect in the rotation's own reporting"]


def _phase_two_confirmation() -> str:
    """**`SELF_CONFIRMED`, and why phase 2 is entitled to it.**

    The fingerprint check refuses when the device or the plan moved between
    a `plan()` and a `rotate()`. Phase 2 is one click running seven steps
    atomically — no plan step, so no window, and nothing to protect.
    `rotate()` records the skip as a step rather than passing silently.

    Two wrong versions preceded this, and both are worth keeping:

    1. It invented `sha256("onboard-confirmation|host|ip")`, which could
       never equal `fingerprint_for(pre)` — **verbatim the defect that
       function's docstring describes**, whose closing line is the rule it
       broke: *"Two callers computing the same hash from the same data is a
       rule that can be broken. One function is a rule that cannot."* Every
       confirmation was refused, safely and permanently, reporting only
       `failed_before_any_change`.
    2. It called `preflight()` here and hashed it with `fingerprint_for()`.
       Correct about the function — and it put a **live SSH session** inside
       a function whose collaborators are otherwise all injected. Measured:
       ten seconds of connect timeout per call, 221 seconds across the
       suite, traced to `preflight -> live_user_line -> ConnectHandler`.

    Not doing the comparison is right for this caller. Doing it twice was a
    worse way to be wrong than not doing it at all.
    """
    from modules.nsot.credential_rotation import SELF_CONFIRMED

    return SELF_CONFIRMED


def _save_first_golden(list_name: str, hostname: str, mgmt_ip: str,
                       platform: str, config: str, actor: str) -> dict:
    """The device's first golden. **One commit, one true record.**

    Written only after the RW community has been removed and the bootstrap
    credential rotated, so the repository's first record of this device
    contains neither. A golden written earlier and corrected later leaves the
    state we deliberately do not want in history, where a remote may publish
    it.
    """
    from modules.nsot.repo import GoldenItem, save_golden

    try:
        return save_golden(
            list_name,
            [GoldenItem(hostname, config, mgmt_ip=mgmt_ip, platform=platform)],
            source="onboarding", actor=actor or "nmas", allow_new=False,
            message=f"onboarding: {hostname} first capture")
    except Exception as exc:                   # noqa: BLE001
        log.exception("phase2: could not save the first golden for %r",
                      hostname)
        return {"ok": False, "error": str(exc)}
