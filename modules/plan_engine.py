"""The plan engine (the operator, 2026-11-14: "the AI may propose a PLAN of catalog operations
... The person approves the plan once by hash; Mercury executes in order, verifies each step,
stops and reports on the first failure, never retries on its own").

**A plan is an ordered list of steps**, each one of Mercury's existing operations with its
parameters held to a strict schema (`STEP_KINDS`, each parameter a `catalog.Param`). A plan is
named from `PLANS` with its own parameters; its steps are derived from them, never typed by
whoever proposed it. Nothing here composes a command.

- `preview(network, plan, params)`: every step's own preview (the operation's own dry run: the
  DHCP reservation's `dhcp_reservations.plan`, the intent patch's `intent_patch.preview`),
  drawn masked, each with its own hash; and the plan's hash over all of them (`plan_hash`). A
  step whose own preview refuses refuses the plan, naming it. Writes nothing.
- `run(...)`: the plan approved ONCE by a verified person, by the plan's hash. The plan is
  previewed again and refused, naming both hashes, when it moved. Then each step in order:
  its own preview again (its hash must be the one approved, or the plan stops there), its own
  apply (which re-checks its own hash), its own verify (the reservation's read-back; the
  intent read back holding the change), and its own record (the reservation's commit in the
  Kea owner's repository, the intent's git commit). **The first step that does not pass stops
  the plan**: it is reported, with why, and no later step runs. Nothing is retried: another
  try is another approval.
- `start(...)`: `run` as a job, the request's verified identity carried into it.

**The plan's own record** is one run record in the operations' record (`privileged.record`,
key `KEY`), with each step's outcome, its receipt and the plan's hash, and its steps on THE
stepper (`op_progress`, its declared steps `step_labels`).

**Who proposes.** The toolbar assistant may name a plan and its parameters
(`modules/ai/assistant.py`); `checked` holds that to the schema before anything is previewed.
The person sees the preview and approves it; nothing an AI wrote runs. A secret is never a
plan's parameter: no step here takes one.
"""

import hashlib
import ipaddress
import json
import logging
import re
import time
from dataclasses import dataclass

from modules.heal.catalog import Param, kind_of, listed, said

log = logging.getLogger(__name__)

#: The run record's key (`privileged.runs`), and the job's kind.
KEY = "plan"
JOB_KIND = "plan"
#: What a plan's end tells open pages: its record, and what its steps write (a reservation;
#: intent and its remote), through its own declared announcer (`invalidation.ANNOUNCERS`).
ANNOUNCE_KEYS = ("privileged", "dhcp", "intent", "remote", "pending", "credentials", "in_progress")
ANNOUNCER = "plan"
#: The most steps a plan holds.
MOST_STEPS = 10
#: The run's steps, as the manual names them (each plan step is ``step-<n>``, `step_labels`).
STEPS = (("approve", "Preview the plan again and compare its hash with the one approved"),
         ("step", "Each step in order: its own preview again, its own apply, verify and "
                  "record; the first that does not pass stops the plan"),
         ("record", "Record the plan's outcome, each step's own"))
#: ``partial``: every step passed, and one leaves work that is its own approval (never green;
#: the record's state the operations' "unverified", drawn warn).
RECORD_STATE = {"done": "done", "partial": "unverified", "stopped": "failed",
                "refused": "refused", "failed": "failed"}
#: A run's outcome as a page job's payload names it (`in_flight.page_finished_row`).
PAGE_STATE = {"done": "done", "partial": "partial", "stopped": "stopped", "refused": "refused",
              "failed": "stopped"}
OUTCOME_WORDS = {"done": "every step ran and was verified",
                 "partial": "every step ran; one leaves its own approval to come",
                 "stopped": "stopped at a step that did not pass; no later step ran",
                 "refused": "nothing ran",
                 "failed": "failed during the run: read each step's own record"}


class Refused(ValueError):
    """Nothing was previewed or run; ``code`` names the check."""

    def __init__(self, code: str, words: str):
        super().__init__(words)
        self.code = code


# ── The parameters' shapes ──────────────────────────────────────────────────────────────────

_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\Z")
_IFNAME = re.compile(r"[A-Za-z][A-Za-z-]{0,30}[0-9][0-9/.:]{0,15}\Z")
_MAC = re.compile(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\Z")


def _text(pattern, words):
    def refusal(value) -> str:
        if not isinstance(value, str):
            return kind_of(value)
        return "" if pattern.match(value) else said(value)
    refusal.words = words
    return refusal


def _address(value) -> str:
    if not isinstance(value, str):
        return kind_of(value)
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return said(value)
    return ""


def _description(value) -> str:
    if not isinstance(value, str):
        return kind_of(value)
    if not (1 <= len(value) <= 240 and value.isascii() and value.isprintable()):
        return f"{said(value)} ({len(value)} characters)"
    from modules.redact import redact_text
    if redact_text(value) != value:
        # Masked on every screen, so a person would approve a value they never saw.
        return "a value that reads as a secret"
    return ""


def _subnet(value) -> str:
    if not isinstance(value, str):
        return kind_of(value)
    return "" if re.fullmatch(r"[0-9]{1,9}", value) else said(value)


DEVICE = Param("device", "one device name of the network (1 to 63 letters, digits, `.`, `_` "
                         "or `-`)", _text(_HOST, "a device name"))
INTERFACE = Param("interface", "an interface name in the platform's shape (GigabitEthernet1)",
                  _text(_IFNAME, "an interface name"))
DESCRIPTION = Param("description", "1 to 240 printable ASCII characters, nothing that reads as a "
                                  "secret (it would be masked, so approved unseen)", _description)
MAC = Param("mac", "a MAC address, six pairs of lower-case hex digits with colons",
            _text(_MAC, "a MAC address"))
ADDRESS = Param("address", "one IPv4 or IPv6 address", _address)
HOSTNAME = Param("hostname", "the name the reservation gives the client (1 to 63 letters, "
                             "digits, `.`, `_` or `-`)", _text(_HOST, "a hostname"))
SUBNET = Param("subnet", "the Kea subnet's id, digits", _subnet)


def _held(params, schema, what: str) -> dict:
    """*params* held to *schema* (a tuple of `Param`): exactly its names, each of its shape."""
    names = [p.name for p in schema]
    if not isinstance(params, dict):
        raise Refused("wrong_type", f"{what}'s parameters are an object giving {listed(names)}, "
                                    f"and {kind_of(params)} was given")
    unknown = [k for k in params if k not in names]
    if unknown:
        raise Refused("unknown_parameter", (
            f"{what} takes exactly the parameters {listed(names)}, and "
            f"{listed(said(k) for k in unknown[:8])} was also given: a parameter the schema "
            "does not name is refused, whatever it holds"))
    missing = [n for n in names if n not in params]
    if missing:
        raise Refused("missing_parameter", f"{what} takes {listed(names)}, and no "
                                           f"{listed(missing)} was given")
    for p in schema:
        value = params[p.name]
        if p.refusal(value):
            # The parameter and its rule, never the value (a wrong-shaped value may be anything
            # a person or a model wrote: it is not echoed into the refusal or the call record).
            given = ("text not of that shape" if isinstance(value, str) else kind_of(value))
            raise Refused("wrong_shape", f"{what}'s parameter {p.name} is {p.takes}, and "
                                         f"{given} was given")
    return {p.name: params[p.name] for p in schema}


def _digest(doc) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()[:16]


# ── The step kinds: each one of Mercury's existing operations ───────────────────────────────

@dataclass(frozen=True)
class StepKind:
    key: str
    words: str
    params: tuple
    preview: object
    apply: object
    #: The route a person uses for the same operation by hand (its own gate and stages).
    by_hand: str
    #: What the step's end says and its level when it passed: ``ok`` (green) or ``partial``
    #: (it passed, and leaves work that is its own approval: never green).
    done_level: str = "ok"
    done_words: str = ""
    #: The keys its own operation announces (`invalidation.DECLARED` of `by_hand`).
    announces: tuple = ()


def _reservation_values(p: dict) -> dict:
    family = "IPv6" if ipaddress.ip_address(p["address"]).version == 6 else "IPv4"
    return {"op": "add", "family": family, "subnet": p["subnet"], "key": "hw-address",
            "identity": p["mac"], "address": p["address"], "hostname": p["hostname"]}


def _owner_refusal(network: str) -> str:
    """The DHCP page's own check (C1181), its one home (`dhcp_reservations.owner_refusal`): a
    reservation is made on the network owning the Kea, never from one inheriting it."""
    from modules import dhcp_reservations as D

    return D.owner_refusal(network)


def _reservation_preview(network: str, p: dict) -> dict:
    from modules import dhcp_reservations as D

    why = _owner_refusal(network)
    if why:
        return {"ok": False, "refused": why}
    got = D.plan(network, _reservation_values(p))
    if not got.get("ok"):
        return {"ok": False, "refused": got.get("refused") or "the reservation's own preview "
                                                                "refused it"}
    return {"ok": True, "hash": got["hash"], "drawn": {
        "title": got.get("title") or "", "change": got.get("change") or "",
        "checks": [str(c) for c in got.get("checks") or []],
        "not_done": [str(c) for c in got.get("not_done") or []]}}


def _reservation_apply(network: str, p: dict, confirmed: str, *, actor: str,
                       reason: str) -> dict:
    """The reservation's own apply (`dhcp_reservations.apply`): its own hash re-checked, the
    file tested, written and reloaded, read back (its verify), committed (its record)."""
    from modules import dhcp_reservations as D

    why = _owner_refusal(network)
    if why:
        return {"ok": False, "outcome": "refused", "words": why, "receipt": {}}
    got = D.apply(network, _reservation_values(p), confirmed, actor=actor, reason=reason)
    receipt = {"outcome": got.get("outcome"), "commit": got.get("commit"),
               "rolled_back": got.get("rolled_back"), "at": got.get("at")}
    if not got.get("ok"):
        return {"ok": False, "outcome": got.get("outcome") or "failed",
                "words": got.get("error") or "the reservation was not made", "receipt": receipt}
    return {"ok": True, "outcome": "done", "receipt": receipt,
            "words": f"reserved {p['address']} for {p['mac']}: read back from Kea, recorded"}


def _description_patch(p: dict):
    from modules.nsot import intent_patch

    patch, why = intent_patch.parse({"hostname": p["device"], "operations": [{
        "op": "set_description", "interface": p["interface"], "description": p["description"]}]})
    if patch is None:
        raise Refused("wrong_shape", f"the description change is refused by intent's own "
                                     f"patch schema: {why}")
    return patch


def _description_preview(network: str, p: dict) -> dict:
    from modules.nsot import intent_patch

    try:
        patch = _description_patch(p)
    except Refused as exc:
        return {"ok": False, "refused": str(exc)}
    # The Intent tab's own authority check (`sdn.authority`, its route DIRECT): a device only
    # its SDN controller configures is never edited here, naming its controller.
    from modules.device import load_saved_devices
    from modules.nsot import listref
    from modules.sdn import authority
    try:
        rows = load_saved_devices(listref.resolve(network).csv_path)
    except Exception as exc:                          # noqa: BLE001 (refused, said)
        return {"ok": False, "refused": f"{network}'s inventory could not be read "
                                        f"({type(exc).__name__}), so who configures "
                                        f"{p['device']} is not known"}
    managed = authority.refusal(network, [p["device"]], rows)
    if managed:
        return {"ok": False, "refused": managed["error"]}
    got = intent_patch.preview(network, p["device"], patch)
    if not got.get("ok"):
        return {"ok": False, "refused": got.get("error") or got.get("message") or
                "the intent change's own preview refused it"}
    if not got.get("changed"):
        return {"ok": False, "refused": got.get("message") or "intent already holds it"}
    return {"ok": True, "hash": _digest({"base": got["base"], "patch": got["patch"],
                                         "yaml": got["yaml"]}),
            "base": got["base"],
            "drawn": {"title": f"{p['device']} {p['interface']}: description "
                               f"\"{p['description']}\"",
                      "change": "; ".join(c.get("summary") or "" for c in got.get("changes")
                                          or []),
                      "checks": [f"intent's version {got['base'][:12]}, the one patched"],
                      "not_done": ["deploys nothing: the device changes only when this intent "
                                   "is deployed"]}}


def _description_apply(network: str, p: dict, confirmed: str, *, actor: str,
                       reason: str) -> dict:
    """Intent's own commit (`intent_patch.commit`), on the version previewed (refused if intent
    moved); verified by reading intent back: the same patch then changes nothing."""
    from modules.nsot import intent_patch

    now = _description_preview(network, p)
    if not now.get("ok") or now.get("hash") != confirmed:
        return {"ok": False, "outcome": "moved", "receipt": {}, "words": (
            f"{p['device']}'s intent is not the one approved (approved {confirmed}, now "
            f"{now.get('hash') or now.get('refused')}): nothing was committed")}
    patch = _description_patch(p)
    got = intent_patch.commit(network, p["device"], patch, reason, now["base"], actor,
                              source="plan")
    receipt = {"commit": got.get("commit") or got.get("sha") or "", "stage": got.get("stage")}
    if not got.get("ok"):
        return {"ok": False, "outcome": "failed", "receipt": receipt,
                "words": got.get("error") or "intent's commit refused it"}
    back = intent_patch.preview(network, p["device"], patch)
    if not back.get("ok") or back.get("changed"):
        return {"ok": False, "outcome": "unverified", "receipt": receipt, "words": (
            f"committed, and {p['device']}'s intent read back does not hold the description")}
    return {"ok": True, "outcome": "done", "receipt": receipt, "words": (
        f"{p['device']} {p['interface']}'s description committed to intent, read back")}


#: Add device by ZTP, its words a plan says (C3078's tier 3, the operator, 2026-11-14).
ZTP_LATER = ("Verify waits for the device to boot and fetch its bootstrap, and is its own "
             "approval on the device's page: its program is read from the device then, so it "
             "cannot be bound into this plan's hash now")
ZTP_SECRET = ("the device's one-time credential is Mercury's: minted at Create and never "
              "shown here, in the plan or to the assistant")


def _ztp_data(network: str, p: dict) -> dict:
    """Add device's form as the ZTP path sends it, from the plan's parameters, through Add
    device's own mapping (`routes.onboard_v2.form_of`: its fields and the network's inventory
    source); what the form leaves to Mercury stays empty, for `build_plan` to derive or refuse.
    Mercury's own ZTP segment only: no DHCP relay (``ztp_router`` empty; the relayed case is
    C3650)."""
    from routes.onboard_v2 import form_of

    return form_of({"list_name": network, "hostname": p["hostname"],
                    "platform": p["platform"], "role": p["role"], "address_source": "ztp",
                    "mgmt_ip": p["address"], "mgmt_mac": p["mac"], "domain": p["domain"],
                    "ztp_router": ""})


def _ztp_built(network: str, p: dict, secret: str):
    from modules.nsot.onboard import build_plan
    from routes.onboard import _plan_args

    return build_plan(**_plan_args(_ztp_data(network, p), network, secret=secret))


def _ztp_preview(network: str, p: dict) -> dict:
    """Add device's own plan (`onboard.build_plan`, with the placeholder secret its review
    uses, so no credential is minted or shown): refused while it is not onboardable; its hash
    the review's own (`onboard.plan_fingerprint` over `plan_shown`), the one Create re-checks
    under its hold."""
    from modules.nsot.onboard import plan_fingerprint, plan_shown

    try:
        built = _ztp_built(network, p, "PLACEHOLDER-not-the-real-credential")
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        return {"ok": False, "refused": f"Add device's own plan failed: {type(exc).__name__}: "
                                        f"{exc}"}
    if not built.onboardable:
        return {"ok": False, "refused": "Add device's own plan refuses it: "
                                        + "; ".join(built.blocking_reasons)}
    shown = plan_shown(built)
    s = built.summary or {}
    return {"ok": True, "hash": plan_fingerprint(shown), "shown": shown, "drawn": {
        "title": f"Create {p['hostname']} by ZTP, reserving {p['address']} for {p['mac']}",
        "change": ("its identity and intent committed, its one-time credential minted, its "
                   f"DHCP reservation {s.get('reservation_state') or 'written'}"),
        "checks": [str(a) for a in s.get("advisories") or []],
        "not_done": [ZTP_LATER, ZTP_SECRET]}}


def _ztp_apply(network: str, p: dict, confirmed: str, *, actor: str, reason: str) -> dict:
    """Add device's own Create (`routes.onboard.create_run`): the hostname held, the plan
    rebuilt and refused unless it is the one previewed, then its steps (the credential minted
    and staged, identity and intent committed, the reservation written, the config rendered).
    Passed only when every one of them ran (its own verify: the reservation `written` or
    `unchanged`); its record is the intent commit and Kea's. The device is then pending."""
    from routes.onboard import create_run

    now = _ztp_preview(network, p)
    if not now.get("ok") or now.get("hash") != confirmed:
        return {"ok": False, "outcome": "moved", "receipt": {}, "words": (
            f"Add device's plan for {p['hostname']} is not the one approved (approved "
            f"{confirmed}, now {now.get('hash') or now.get('refused')}): nothing was created")}
    got, _status = create_run(dict(_ztp_data(network, p), shown=now["shown"],
                                   fingerprint=now["hash"]), actor)
    receipt = {"failed_at": got.get("failed_at") or "", "reason": got.get("reason") or "",
               "reserve_record": got.get("reserve_record") or ""}
    if not got.get("ok") or got.get("failed_at"):
        return {"ok": False, "outcome": "failed", "receipt": receipt, "words": (
            got.get("error") or got.get("reason") or
            f"Create stopped at {got.get('failed_at') or 'a step'}")}
    return {"ok": True, "outcome": "done", "receipt": receipt, "words": (
        f"{p['hostname']} created and pending: {ZTP_LATER}")}


_PLATFORM = re.compile(r"[a-z0-9][a-z0-9_-]{0,48}\Z")
_ROLE = re.compile(r"[a-z0-9][a-z0-9_-]{0,48}\Z")
_DOMAIN = re.compile(r"(?=.{1,253}\Z)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
                     r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+\Z")


def _router(value) -> str:
    if not isinstance(value, str):
        return kind_of(value)
    return "" if value in ("", "relay") else said(value)


ZTP_PARAMS = (
    Param("hostname", "the new device's name (1 to 63 letters, digits, `.`, `_` or `-`)",
          _text(_HOST, "a device name")),
    Param("platform", "the platform's NetBox slug, as Add device lists it (cisco-ios-xe)",
          _text(_PLATFORM, "a platform slug")),
    Param("role", "the device's role slug, as NetBox holds it (router, switch)",
          _text(_ROLE, "a role slug")),
    MAC, Param("address", "the address Mercury reserves for it, on Mercury's own ZTP segment "
                          "(one IPv4 or IPv6 address; a device behind a DHCP relay is not "
                          "served by this plan yet, C3650)", _address),
    Param("domain", "the device's domain name, lower case (example.net)",
          _text(_DOMAIN, "a domain name")),
)


STEP_KINDS = {k.key: k for k in (
    StepKind("dhcp-reservation", "Add a DHCP reservation (Kea, the network's own)",
             (MAC, ADDRESS, HOSTNAME, SUBNET), _reservation_preview, _reservation_apply,
             "dhcp_v2.reservation_confirm", announces=("dhcp",)),
    StepKind("intent-description", "Set an interface's description in a device's intent",
             (DEVICE, INTERFACE, DESCRIPTION), _description_preview, _description_apply,
             "intent_v2.commit", announces=("intent", "remote")),
    StepKind("ztp-create", "Create a device by ZTP (Add device's Create)", ZTP_PARAMS,
             _ztp_preview, _ztp_apply, "onboard_v2.create", done_level="partial",
             done_words="created and pending: Verify is its own approval",
             announces=("pending", "intent", "credentials", "remote", "in_progress")),
)}


# ── The plans: each an ordered list of step kinds, derived from its own parameters ──────────

@dataclass(frozen=True)
class Plan:
    key: str
    words: str
    params: tuple
    steps: object
    title: object


def _link_steps(p: dict) -> list:
    if p["device_a"] == p["device_b"]:
        raise Refused("same_device", (
            f"a link has two ends on two devices, and both ends given are {p['device_a']}'s"))
    return [("intent-description", {"device": p["device_a"], "interface": p["interface_a"],
                                    "description": p["description"]}),
            ("intent-description", {"device": p["device_b"], "interface": p["interface_b"],
                                    "description": p["description"]})]


def _as(name: str, base: Param) -> Param:
    return Param(name, base.takes, base.refusal)


PLANS = {p.key: p for p in (
    Plan("dhcp-reservation", "Reserve an address for a client in the network's DHCP",
         (MAC, ADDRESS, HOSTNAME, SUBNET),
         lambda p: [("dhcp-reservation", dict(p))],
         lambda p: f"Reserve {p['address']} for {p['hostname']} ({p['mac']})"),
    Plan("describe-link", "Describe a link at both ends in intent (two devices' interfaces)",
         (_as("device_a", DEVICE), _as("interface_a", INTERFACE), _as("device_b", DEVICE),
          _as("interface_b", INTERFACE), DESCRIPTION),
         _link_steps,
         lambda p: (f"Describe the link {p['device_a']} {p['interface_a']} – "
                    f"{p['device_b']} {p['interface_b']}")),
    # Tier 3 (the operator, 2026-11-14: "add a ZTP device"). Of Add device's four confirm-bound
    # steps, Create is bound here; Verify reads the device after it boots, so its program is
    # not known at approval and stays its own approval (`ZTP_LATER`); the bootstrap reveal is
    # never a plan's (`ZTP_SECRET`); Abandon is the undo, never a step.
    Plan("add-ztp-device", "Add a device by ZTP: Create it (its identity and intent, its "
                           "one-time credential, its DHCP reservation)",
         ZTP_PARAMS, lambda p: [("ztp-create", dict(p))],
         lambda p: f"Add {p['hostname']} by ZTP at {p['address']} ({p['mac']})"),
)}


def checked(plan, params) -> tuple:
    """``(plan, parameters, steps)``: a named plan held to `PLANS`, its parameters to its schema,
    and its steps derived, each held to its kind's schema; or raises `Refused`. Reads nothing."""
    if not isinstance(plan, str) or plan not in PLANS:
        raise Refused("not_a_plan", (
            f"a plan is one of Mercury's ({listed(sorted(PLANS))}), and "
            f"{said(plan) if isinstance(plan, str) else kind_of(plan)} was named"))
    p = PLANS[plan]
    held = _held(params, p.params, p.key)
    steps = p.steps(held)
    if not 1 <= len(steps) <= MOST_STEPS:
        raise Refused("steps", f"{p.key} derived {len(steps)} steps, past 1 to {MOST_STEPS}")
    out = []
    for n, (kind, sp) in enumerate(steps, 1):
        out.append({"n": n, "kind": kind,
                    "params": _held(sp, STEP_KINDS[kind].params, f"step {n} ({kind})")})
    return p, held, out


def plan_hash(plan: str, params: dict, steps: list, network: str = "") -> str:
    """The plan's one hash: the network it acts on, the plan, its parameters, and each step's
    kind, parameters and own hash, in order. Another network, another order, another parameter
    or a step whose own preview moved is another hash."""
    return _digest({"network": network, "plan": plan, "params": params,
                    "steps": [[s["kind"], s["params"], s.get("hash", "")] for s in steps]})


def preview(network: str, plan, params) -> dict:
    """The plan, every step previewed by its own operation: ``{"ok", "plan", "title", "words",
    "params", "steps", "hash", "refused", "code"}``, each step ``{"n", "kind", "words",
    "params", "ok", "hash", "drawn", "refused"}``. Writes nothing."""
    try:
        p, held, steps = checked(plan, params)
    except Refused as exc:
        return {"ok": False, "code": exc.code, "refused": str(exc), "steps": [], "hash": ""}
    from modules.redact import redact_payload

    refused = ""
    for s in steps:
        got = STEP_KINDS[s["kind"]].preview(network, s["params"])
        s.update(words=STEP_KINDS[s["kind"]].words, ok=bool(got.get("ok")),
                 hash=got.get("hash") or "", drawn=redact_payload(got.get("drawn") or {}),
                 refused=got.get("refused") or "")
        if not s["ok"] and not refused:
            refused = f"step {s['n']} ({s['words']}) is refused by its own preview: {s['refused']}"
    return {"ok": not refused, "code": "step_refused" if refused else "", "refused": refused,
            "plan": p.key, "title": p.title(held), "words": p.words, "params": held,
            "network": network,
            "steps": steps, "hash": "" if refused else plan_hash(p.key, held, steps, network)}


# ── The run ─────────────────────────────────────────────────────────────────────────────────

def step_labels(steps: list) -> list:
    """The plan's declared steps for THE stepper: approve, then one per step, then record."""
    return ([("approve", "Preview the plan again and compare its hash with the one approved")]
            + [(f"step-{s['n']}", f"Step {s['n']}: {s['words']}: its own preview, apply, "
                                  "verify and record") for s in steps]
            + [("record", "Record the plan's outcome, each step's own")])


def person_refusal(actor: str, actor_verified: str, person: bool) -> str:
    """Why the approval is not a verified person's, or ``""`` (an allowlist of the ways a
    request's identity is established, `identity.REQUEST_VERIFICATIONS`)."""
    from modules import identity

    if (person is True and actor and actor != identity.UNVERIFIED
            and isinstance(actor_verified, str)
            and actor_verified in identity.REQUEST_VERIFICATIONS):
        return ""
    return (f"a plan is approved by a verified person, and this request is not one (actor "
            f"{actor or 'none'}, verified {actor_verified or 'none'}): nothing ran")


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _record(network: str, rec: dict) -> dict:
    """The plan's run record, in the operations' record History reads."""
    from modules.nsot import privileged

    return privileged.record(network, rec)


def _announce() -> None:
    try:
        from modules import invalidation
        invalidation.announce(invalidation.ANNOUNCERS[ANNOUNCER], by=ANNOUNCER)
    except Exception as exc:                          # noqa: BLE001 (a page's freshness only)
        log.info("plan engine: a run recorded, not announced: %s", exc)


def run(network: str, plan, params, confirmed: str, *, actor: str, actor_verified: str,
        person: bool, reason: str, run_id: str = "", clock=time.time) -> dict:
    """The approved plan, in order, as *actor*: the run's record, written. Never raises; a
    refusal is a record too, with nothing run."""
    from modules import op_progress
    from modules.nsot import reads

    now = clock()
    rec = {"id": run_id or reads.new_id(), "key": KEY, "list": network, "plan": str(plan)[:64],
           "actor": actor, "actor_verified": (actor_verified if isinstance(actor_verified, str)
                                              and actor_verified else "none"),
           "reason": (reason or "").strip()[:500], "started_at": now, "at": _iso(now),
           "finished_at": None, "state": "running", "outcome": "running", "hash": "",
           "command": f"plan {str(plan)[:64]}", "config_change": False, "plan_steps": [],
           "steps": []}

    def step(name, result, words, **more):
        rec["steps"].append(dict({"step": name, "result": result, "words": words,
                                  "at": _iso(clock())}, **more))
        op_progress.moved()

    def finish(outcome, words):
        rec.update(outcome=outcome, state=RECORD_STATE[outcome], why=words,
                   finished_at=clock())
        step("record", "ok", OUTCOME_WORDS[outcome])
        _record(network, rec)
        _announce()
        log.info("plan engine: %s on %s: %s %s", actor, network, rec["plan"], outcome)
        return rec

    try:
        return _run(network, plan, params, confirmed, rec, step, finish, actor=actor,
                    actor_verified=actor_verified, person=person)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.exception("plan engine: %s on %s failed", rec["plan"], network)
        for kept in rec.get("plan_steps") or []:
            if kept.get("state") == "running":
                # The step that raised: whether its own operation landed is not known.
                kept.update(state="failed", outcome="unknown", words_said=(
                    f"it raised ({type(exc).__name__}: {exc}); whether it landed is unknown: "
                    "read its own record"))
        try:
            return finish("failed", f"{type(exc).__name__}: {exc}; whether the running step "
                                    "landed is unknown: read each step's own record")
        except Exception:                             # noqa: BLE001 (the record itself failed)
            log.exception("plan engine: %s on %s: its record could not be written",
                          rec["plan"], network)
            rec.update(outcome="failed", state="failed")
            return rec


def _run(network, plan, params, confirmed, rec, step, finish, *, actor, actor_verified,
         person) -> dict:
    """`run`'s body, inside its one try: every write and every step's own operation."""
    from modules import op_progress

    why = person_refusal(actor, actor_verified, person)
    p = preview(network, plan, params) if not why else {"ok": False, "steps": []}
    op_progress.attach(step_labels(p.get("steps") or []), rec["steps"], run=rec["id"])
    if why:
        step("approve", "refused", why)
        return finish("refused", why)
    if not p["ok"]:
        step("approve", "refused", p["refused"] + ". Nothing ran")
        return finish("refused", p["refused"] + ". Nothing ran")
    rec.update(hash=p["hash"], title=p["title"])
    if str(confirmed or "") != p["hash"]:
        words = (f"the plan is not the one approved: you approved {confirmed or 'no hash'}, "
                 f"and the plan previewed now is {p['hash']}. Nothing ran; preview it again")
        step("approve", "refused", words)
        return finish("refused", words)
    if len(rec["reason"].split()) < 3:
        words = "a plan is approved with a reason of at least three words. Nothing ran"
        step("approve", "refused", words)
        return finish("refused", words)
    rec["plan_steps"] = [{"n": s["n"], "kind": s["kind"], "words": s["words"],
                          "params": s["params"], "hash": s["hash"], "state": "not_run",
                          "outcome": "", "words_said": "", "receipt": {}} for s in p["steps"]]
    step("approve", "ok", f"the plan is the one approved ({p['hash']}): {p['title']}")
    _record(network, rec)
    for s, kept in zip(p["steps"], rec["plan_steps"]):
        kind = STEP_KINDS[s["kind"]]
        name = f"step-{s['n']}"
        again = kind.preview(network, s["params"])
        if not again.get("ok") or again.get("hash") != s["hash"]:
            words = (f"step {s['n']} ({s['words']}) moved since the plan was approved "
                     f"(approved {s['hash']}, now "
                     f"{again.get('hash') or again.get('refused') or 'refused'}): it and "
                     "every step after it did not run")
            kept.update(state="refused", outcome="moved", words_said=words)
            step(name, "refused", words)
            return finish("stopped", words)
        rec["config_change"] = True
        # Running from here: a step that raises is "failed, whether it landed unknown", never
        # "did not run" (`run`'s except).
        kept["state"] = "running"
        _record(network, rec)
        got = kind.apply(network, s["params"], s["hash"], actor=actor, reason=rec["reason"])
        kept.update(state="done" if got.get("ok") else "failed",
                    outcome=got.get("outcome") or "", words_said=got.get("words") or "",
                    receipt=got.get("receipt") or {})
        _record(network, rec)
        if not got.get("ok"):
            words = (f"step {s['n']} ({s['words']}) did not pass: {got.get('words')}. "
                     "No later step ran, and nothing is retried")
            step(name, "failed", words)
            return finish("stopped", words)
        step(name, "ok", f"step {s['n']}: {got.get('words')}")
    partial = [STEP_KINDS[s["kind"]] for s in p["steps"]
               if STEP_KINDS[s["kind"]].done_level == "partial"]
    if partial:
        return finish("partial", f"{p['title']}: " + "; ".join(k.done_words for k in partial))
    return finish("done", f"{p['title']}: every step ran and was verified")


def start(network: str, plan, params, confirmed: str, *, actor: str, actor_verified: str,
          person: bool, reason: str) -> dict:
    """Refuse now (``{"refused"}``, nothing run) or start `run` as a job (``{"job",
    "run"}``), the request's verified identity carried into it (`capture_job.start`)."""
    from modules.nsot import capture_job, reads

    why = person_refusal(actor, actor_verified, person)
    if why:
        return {"refused": why, "not_a_person": True}
    p = preview(network, plan, params)
    if not p["ok"]:
        return {"refused": p["refused"] + ". Nothing ran"}
    if str(confirmed or "") != p["hash"]:
        return {"refused": (f"the plan is not the one approved: you approved "
                            f"{confirmed or 'no hash'}, and the plan previewed now is "
                            f"{p['hash']}. Nothing ran; preview it again")}
    run_id = reads.new_id()
    # Listed under In progress, its card reopenable at its own address (capture_job's *page*).
    from urllib.parse import quote
    page = (f"/v2/plans/preview?list={quote(network)}&plan={quote(str(plan))}&run={run_id}"
            "&job={job}")
    # What the job's end announces: the record, and what each of its steps' own operations
    # announce (`StepKind.announces`).
    keys = tuple(dict.fromkeys(("privileged",) + tuple(
        k for s in p["steps"] for k in STEP_KINDS[s["kind"]].announces)))

    def work(_job_id):
        rec = run(network, plan, params, confirmed, actor=actor, actor_verified=actor_verified,
                  person=person, reason=reason, run_id=run_id)
        return payload_of(rec)
    job = capture_job.start(network, p["title"], actor, work, kind=JOB_KIND,
                            announce_keys=keys, announcer=ANNOUNCER, page=page)
    return {"job": job, "run": run_id}


def payload_of(rec: dict) -> dict:
    """A run's job payload as In progress reads a page job's (`in_flight.page_finished_row`):
    its ``state`` (`PAGE_STATE`), the record's why as ``stopped`` or ``error``, and its own
    ``words`` (a plan's are not a rollout's)."""
    outcome = rec.get("outcome") or "failed"
    state = PAGE_STATE.get(outcome, "stopped")
    why = str(rec.get("why") or "")[:200]
    out = {"run": rec.get("id"), "state": state,
           "words": f"{OUTCOME_WORDS.get(outcome, outcome)}" + (f": {why}" if why else "")}
    out["stopped" if state in ("stopped", "partial") else "error"] = why
    return out


def record_of(network: str, run_id: str):
    """The plan run *run_id*'s record, or None (not a plan's, or not there yet)."""
    from modules.nsot import privileged

    try:
        rec = privileged.get(network, run_id)
    except (ValueError, OSError):
        return None
    return rec if isinstance(rec, dict) and rec.get("key") == KEY else None
