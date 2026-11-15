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

**An incident's fix** (C3694, the operator's R1, 2026-11-14): the catalog's operations
(`modules/heal/catalog.py`) are step kinds too, each previewed by the fix-it check
(`fixit.plan.step_preview`: the incident's scope, the heal guards, committed intent, a repeat of
a failed attempt refused) and applied by Re-subscribe's own apply as the approver, its run
naming the incident; the plan ``incident-fix`` (`INCIDENT_FIX`) is an incident's proposal, its
steps the proposal's, approved on the incident's page (routes/fixit_v2.py, ``approve``).

**The plan's own record** is one run record in the operations' record (`privileged.record`,
key `KEY`), with each step's outcome, its receipt and the plan's hash, and its steps on THE
stepper (`op_progress`, its declared steps `step_labels`).

**Who proposes.** The toolbar assistant may name a plan and its parameters
(`modules/ai/assistant.py`); `checked` holds that to the schema before anything is previewed.
The person sees the preview and approves it; nothing an AI wrote runs. A secret is never a
plan's parameter: no step here takes one.

**What Mercury holds is derived, never asked for** (the operator's test B1, 2026-11-14: a
reservation asked a person for "a Kea subnet id"). A reservation's subnet is the subnet of the
network's DHCP that contains its address (`dhcp_subnet_for`, through the DHCP page's own Kea
read); its preview names what was found and from where (Kea's subnet; the NetBox prefix
holding it, when NetBox has one), its ``resolved`` subnet is bound in the plan's hash, and the
apply uses exactly that one. ``subnet`` is accepted only as a person's choice when several
contain the address; none is refused in plain words.
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
    """Empty (Mercury finds it), Kea's own number for it, or its prefix: the person's choice
    among the subnets that contain the address, as Mercury offered them (`dhcp_subnet_for`)."""
    if not isinstance(value, str):
        return kind_of(value)
    if value == "" or re.fullmatch(r"[0-9]{1,9}", value):
        return ""
    if "/" in value:
        try:
            ipaddress.ip_network(value, strict=True)
            return ""
        except ValueError:
            pass
    return said(value)


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
#: Optional (B1, the operator's test 2026-11-14: a request for "a Kea subnet id" is jargon and a
#: value Mercury holds): left out, Mercury finds the subnet of its DHCP that contains the
#: address (`dhcp_subnet_for`); given only as a person's choice when several contain it.
SUBNET = Param("subnet", "optional, and left out unless the person chose it: Mercury finds the "
                         "subnet of its DHCP that contains the address; when several do, the "
                         "person's choice, the subnet's prefix as Mercury offered it "
                         "(192.0.2.0/24)", _subnet)


def _held(params, schema, what: str, optional=()) -> dict:
    """*params* held to *schema* (a tuple of `Param`): exactly its names, each of its shape; a
    name in *optional* may be left out, and is then held as ``""``."""
    names = [p.name for p in schema]
    if isinstance(params, dict):
        params = dict(params, **{n: "" for n in optional if n in names and n not in params})
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
    #: Its parameters that may be left out (held as ``""``), each one Mercury derives.
    optional: tuple = ()
    #: Its apply is a device operation that refuses anyone but a verified person itself (a
    #: catalog operation's, `resubscribe.apply`): it is handed how the approver was verified.
    as_person: bool = False


# ── Where an address lives in Mercury's DHCP (B1: derived by code, never asked for) ─────────

def _kea(network: str):
    """The network's Kea, as the DHCP page's own reads ask it (`dhcp_reservations._plan`)."""
    from modules.integrations.kea import KeaIntegration

    return KeaIntegration(list_name=network)


def _family(address: str) -> str:
    return "IPv6" if ipaddress.ip_address(address).version == 6 else "IPv4"


def kea_config_of(network: str, family: str, *, kea=None, cache: dict = None) -> dict:
    """``{"state": "ok"|"unconfigured"|"unreadable", "config", "words"}``: Kea's configuration
    for *family*, through the DHCP page's own read (`dhcp_reservations.kea_config`), once per
    *cache* (a dict a caller keeps for one question). A read: nothing is written."""
    from modules import dhcp_reservations as D

    cache = {} if cache is None else cache
    if family in cache:
        return cache[family]
    if "kea" not in cache:
        cache["kea"] = kea if kea is not None else _kea(network)
    k = cache["kea"]
    svc = D.FAMILY[family]["svc"]
    try:
        configured = k.is_configured()
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        configured, why = False, f"its settings could not be read ({type(exc).__name__})"
    else:
        why = ""
    if not configured:
        from modules.installation_settings import settings_place
        got = {"state": "unconfigured", "config": None, "words": (
            why or f"Kea is not configured for {network} ({settings_place('kea', 'Kea')})")}
    else:
        try:
            got = {"state": "ok", "config": D.kea_config(k, family), "words": ""}
        except D.Refused as exc:
            got = {"state": "unreadable", "config": None, "words": str(exc)}
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            got = {"state": "unreadable", "config": None,
                   "words": f"Kea's {svc} could not be read ({type(exc).__name__})"}
    cache[family] = got
    return got


def kea_subnets(network: str, family: str, *, kea=None, cache: dict = None) -> dict:
    """``{"state", "words", "subnets": [{"id", "prefix", "shared", "comment", "family"}]}``:
    every subnet Kea's *family* configuration holds, those in shared networks too
    (`dhcp_reservations._subnets`). A read."""
    from modules import dhcp_reservations as D

    got = kea_config_of(network, family, kea=kea, cache=cache)
    if got["state"] != "ok":
        return {"state": got["state"], "words": got["words"], "subnets": []}
    out = []
    for s, shared in D._subnets(got["config"], family):
        comment = (s.get("user-context") or {}).get("comment") if isinstance(
            s.get("user-context"), dict) else ""
        out.append({"id": s.get("id"), "prefix": s.get("subnet", ""), "shared": shared or "",
                    "comment": str(comment or "")[:80], "family": family})
    return {"state": "ok", "words": "", "subnets": out}


def subnet_label(s: dict) -> str:
    more = [f"Kea subnet {s['id']}"]
    if s.get("shared"):
        more.append(f"shared network {s['shared']}")
    if s.get("comment"):
        more.append(s["comment"])
    return f"{s['prefix']} ({', '.join(more)})"


def _subnet_found(address: str, s: dict) -> dict:
    svc = "DHCPv6" if s.get("family") == "IPv6" else "DHCPv4"
    return {"what": f"the subnet of Mercury's DHCP containing {address}",
            "value": subnet_label(s), "source": f"Kea's {svc} configuration, read now"}


def dhcp_subnet_for(network: str, address: str, chosen: str = "", *, kea=None,
                    cache: dict = None) -> dict:
    """The subnet of the network's DHCP holding *address* (B1: found by code, never asked of a
    person or a model): ``{"state", "subnet", "candidates", "choices", "words", "found"}``.

    *state* ``found`` (one subnet, or the one *chosen* among several), ``several`` (more than
    one contains it and none is chosen: *choices* each ``{"label", "value"}``, *value* the
    subnet's prefix, what the plan's ``subnet`` takes), ``none`` ("192.0.2.50 is in no subnet
    Mercury's DHCP serves"), ``not_in_chosen`` (*chosen* is not one that contains it),
    ``unconfigured`` or ``unreadable`` (Kea, said). *found* the facts drawn with where each
    came from. *chosen* is Kea's number for the subnet or its prefix. A read: nothing is
    written."""
    out = {"state": "", "subnet": None, "candidates": [], "choices": [], "words": "",
           "found": []}
    try:
        family = _family(address)
    except ValueError:
        return dict(out, state="none", words=f"{said(address)} is not an address")
    got = kea_subnets(network, family, kea=kea, cache=cache)
    if got["state"] != "ok":
        return dict(out, state=got["state"], words=got["words"])
    inside = [s for s in got["subnets"] if _contains(s["prefix"], address)]
    out["candidates"] = inside
    if not inside:
        return dict(out, state="none", words=(
            f"{address} is in no subnet Mercury's DHCP serves (Kea's "
            f"{'DHCPv6' if family == 'IPv6' else 'DHCPv4'} configuration, read now: "
            f"{len(got['subnets'])} subnets)"))
    choices = [{"label": subnet_label(s), "value": s["prefix"]} for s in inside]
    if chosen:
        hit = [s for s in inside if str(s["id"]) == chosen or same_prefix(s["prefix"], chosen)]
        if len(hit) != 1:
            return dict(out, state="not_in_chosen", choices=choices, words=(
                f"{address} is not in the subnet {chosen}: of the subnets Mercury's DHCP "
                f"serves, {listed(c['label'] for c in choices)} "
                f"{'contains' if len(choices) == 1 else 'contain'} it"))
        inside = hit
    if len(inside) > 1:
        return dict(out, state="several", choices=choices, words=(
            f"{address} is in {len(inside)} of the subnets Mercury's DHCP serves: "
            f"{listed(c['label'] for c in choices)}. Which one should hold it?"))
    s = inside[0]
    return dict(out, state="found", subnet=s, words=f"{address} is in {subnet_label(s)}",
                found=[_subnet_found(address, s)])


def _contains(prefix: str, address: str) -> bool:
    try:
        return ipaddress.ip_address(address) in ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return False


def same_prefix(a: str, b: str) -> bool:
    try:
        return ipaddress.ip_network(a, strict=False) == ipaddress.ip_network(b, strict=False)
    except ValueError:
        return False


def netbox_prefix_found(address: str) -> list:
    """The NetBox prefix most specific among those containing *address*, as a found fact
    (`modules/ai/netbox_reads.py`'s read of IPAM › Prefixes): one fact, its absence a fact too,
    NetBox not configured nothing, a failed read said. A read (one GET)."""
    from modules.ai import netbox_reads

    got = netbox_reads.read("netbox_prefixes", {"contains": address})
    what = f"NetBox's prefix containing {address}"
    if got["state"] == "unconfigured":
        return []
    if got["state"] != "ok":
        return [{"what": what, "value": f"not read: {got['why']}", "source": got["source"]}]
    rows = sorted(got["rows"], key=lambda r: prefixlen(r.get("prefix")), reverse=True)
    if not rows:
        return [{"what": what, "value": f"none: {got['said']}", "source": got["source"]}]
    top = rows[0]
    more = ", ".join(x for x in (top.get("description") or "", top.get("site") or "") if x)
    return [{"what": what, "value": f"{top.get('prefix')}" + (f" ({more})" if more else ""),
             "source": got["source"]}]


def prefixlen(prefix) -> int:
    try:
        return ipaddress.ip_network(str(prefix), strict=False).prefixlen
    except ValueError:
        return -1


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
    """The reservation's own preview (`dhcp_reservations.plan`) on the subnet Mercury found for
    the address (`dhcp_subnet_for`, B1), or the person's choice among several: ``resolved``
    names it (the plan's hash binds it, `plan_hash`), and ``found`` what was found and from
    where (Kea's subnet; NetBox's prefix, when NetBox holds one), drawn first among the checks.
    Several subnets, none, or a choice that is not one is refused in plain words, with the
    candidates as ``choices``."""
    from modules import dhcp_reservations as D

    why = _owner_refusal(network)
    if why:
        return {"ok": False, "refused": why}
    home = dhcp_subnet_for(network, p["address"], p.get("subnet") or "")
    if home["state"] != "found":
        return {"ok": False, "refused": home["words"], "code": home["state"],
                "choices": home["choices"]}
    q = dict(p, subnet=str(home["subnet"]["id"]))
    got = D.plan(network, _reservation_values(q))
    if not got.get("ok"):
        return {"ok": False, "refused": got.get("refused") or "the reservation's own preview "
                                                                "refused it"}
    found = list(home["found"]) + netbox_prefix_found(p["address"])
    return {"ok": True, "hash": got["hash"], "resolved": {"subnet": q["subnet"]},
            "found": found, "drawn": {
                "title": got.get("title") or "", "change": got.get("change") or "",
                "found": found,
                "checks": [f"Found: {f['value']}, {f['what']} ({f['source']})" for f in found]
                + [str(c) for c in got.get("checks") or []],
                "not_done": [str(c) for c in got.get("not_done") or []]}}


def _reservation_apply(network: str, p: dict, confirmed: str, *, actor: str,
                       reason: str) -> dict:
    """The reservation's own apply (`dhcp_reservations.apply`): its own hash re-checked, the
    file tested, written and reloaded, read back (its verify), committed (its record). *p*
    carries the subnet the approved preview resolved (`_run`); one that does not is resolved
    again, and refused unless it is found."""
    from modules import dhcp_reservations as D

    why = _owner_refusal(network)
    if why:
        return {"ok": False, "outcome": "refused", "words": why, "receipt": {}}
    if not str(p.get("subnet") or "").isdigit():
        home = dhcp_subnet_for(network, p["address"], p.get("subnet") or "")
        if home["state"] != "found":
            return {"ok": False, "outcome": "refused", "words": home["words"], "receipt": {}}
        p = dict(p, subnet=str(home["subnet"]["id"]))
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


# ── The catalog's operations as steps (C3694: an incident's fix is a plan of them) ─────────

_INCIDENT = re.compile(r"(?:hi-[0-9a-f]{6,40}|resp-[0-9a-f]{6,40}|al-[a-z0-9][a-z0-9-]{0,63})\Z")
_PROPOSAL = re.compile(r"p[0-9]{1,6}\Z")
INCIDENT = Param("incident", "the id of the incident the plan fixes (hi-, resp- or al- and its "
                             "token)", _text(_INCIDENT, "an incident's id"))
PROPOSAL = Param("proposal", "the proposal line of the incident's record the plan is (p and a "
                             "number)", _text(_PROPOSAL, "a proposal's id"))


def _session_refusal(value) -> str:
    if not isinstance(value, str):
        return kind_of(value)
    if len(value) > 60 or any(ch not in "0123456789abcdefABCDEF.:[]" for ch in value):
        return said(value)
    return ""


#: The collector step's session (its device's end, as the close helper's dry run names it):
#: Mercury derives it at Approve, and the plan's hash binds it, so the session closed is the
#: one the approval bound, refused naming both if it moved (as `resubscribe_v2.close_confirm`
#: binds the card's).
SESSION = Param("session", "the collector's session from the device, as the close helper's dry "
                           "run named it when the plan was approved (Mercury derives it)",
                _session_refusal)


def _catalog_params(key: str) -> tuple:
    """A catalog operation's step parameters: the incident and its proposal, then exactly the
    catalog's own schema (`catalog.CATALOG`), held by the catalog's own checks; the collector
    step also its session (`SESSION`, derived)."""
    from modules.heal import resubscribe as R
    from modules.heal.catalog import CATALOG

    return ((INCIDENT, PROPOSAL) + tuple(CATALOG[key].params)
            + ((SESSION,) if key == R.COLLECTOR_KEY else ()))


def collector_session(network: str, device: str, subs) -> dict:
    """``{"session", "refused"}``: the session the collector step would close now, its device's
    end as the close helper's DRY RUN names it (`resubscribe.plan` with ``collector``: it closes
    nothing), or why there is none. Asked at Approve and again at the step's preview and apply,
    each a person's approval or its run, never a page draw."""
    from modules.heal import resubscribe as R

    got = R.plan(network, device, list(subs), collector=True)
    remote = str((got.get("close") or {}).get("remote") or "")
    if not got.get("ok") or not remote:
        return {"session": "", "refused": "; ".join(got.get("refusals") or [])
                or "the collector's session could not be named"}
    return {"session": remote, "refused": ""}


def _catalog_preview(key: str):
    """A catalog step's preview: the operation's own preview held to its incident's scope and
    the heal guards, and refused when it repeats what already failed in the incident
    (`fixit.plan.step_preview`, a read)."""
    def preview(network: str, p: dict) -> dict:
        from modules.fixit import plan as FP

        got = FP.step_preview(network, key, p)
        bound = str(p.get("session") or "")
        if got.get("ok") and bound:
            # The collector step's session, bound at Approve: read again (the close helper's
            # dry run) and refused, naming both, when it moved since.
            now = collector_session(network, p["device"], p.get("subscriptions") or [])
            if now["session"] != bound:
                return {"ok": False, "hash": "", "drawn": got.get("drawn") or {}, "refused": (
                    f"the collector's session moved since the plan was approved: the approval "
                    f"bound the session from {bound}, and the collector holds "
                    f"{('one from ' + now['session']) if now['session'] else 'none'} now"
                    + (f" ({now['refused']})" if now["refused"] else ""))}
        return got
    return preview


def _catalog_apply(key: str):
    """A catalog step's apply: the operation's OWN apply (`resubscribe.apply`), as the approver,
    holding the device, with each subscription's hash and the selection's from its plan read
    now and refused unless the selection's is the one approved (*confirmed*); its run record
    names the incident, the attempt and the proposal (`fixit.incident.run_link`), so the run is
    the incident's attempt. The collector step closes exactly the session the approval bound
    (its ``session``, in the plan's hash): read again when the step runs, and refused, naming
    both sessions, when it moved."""
    def apply(network: str, p: dict, confirmed: str, *, actor: str, reason: str,
              actor_verified: str = "", person: bool = False) -> dict:
        from modules.fixit import plan as FP
        from modules.heal import resubscribe as R

        readd = key == R.READD_KEY
        collector = key == R.COLLECTOR_KEY
        subs = [p["subscription"]] if readd else list(p["subscriptions"])
        now = R.plan(network, p["device"], subs, readd=readd)
        if not now.get("ok") or now.get("hash") != confirmed:
            return {"ok": False, "outcome": "moved", "receipt": {}, "words": (
                f"its program moved since it was approved (approved {confirmed}, now "
                f"{now.get('hash') or '; '.join(now.get('refusals') or []) or 'refused'}); "
                "nothing was sent")}
        program, close = now["hash"], ""
        if collector:
            withc = R.plan(network, p["device"], subs, collector=True)
            program = withc.get("hash") or ""
            close = str((withc.get("close") or {}).get("remote") or "")
            bound = str(p.get("session") or "")
            if not bound or close != bound:
                return {"ok": False, "outcome": "moved", "receipt": {}, "words": (
                    f"the collector's session is not the one approved: the approval bound the "
                    f"session from {bound or 'no session'}, and the collector holds "
                    f"{('one from ' + close) if close else 'none to close'} now; nothing was "
                    "sent")}
        rec = R.apply(network, p["device"], subs, actor=actor, actor_verified=actor_verified,
                      person=person, confirmed={u["sub"]: u["hash"] for u in now["units"]},
                      program=program, previewed=",".join(subs), reason=reason, readd=readd,
                      collector=collector, previewed_close=close,
                      fixit=FP.run_link_of(network, p))
        ok = rec.get("state") == "done"
        words = R.OUTCOME_WORDS.get(rec.get("outcome") or "", "") or str(rec.get("why") or "")
        return {"ok": ok, "outcome": rec.get("outcome") or "", "words": words or (
                    "re-subscribed and verified" if ok else "it did not pass"),
                "receipt": {"run": rec.get("id") or "", "state": rec.get("state") or ""}}
    return apply


def _catalog_kinds() -> tuple:
    from modules.heal.catalog import CATALOG

    return tuple(StepKind(k, op.words, _catalog_params(k), _catalog_preview(k),
                          _catalog_apply(k), op.confirm_endpoint, announces=("privileged",),
                          as_person=True,
                          optional=("session",) if any(p.name == "session"
                                                       for p in _catalog_params(k)) else ())
                 for k, op in CATALOG.items())


STEP_KINDS = {k.key: k for k in (
    StepKind("dhcp-reservation", "Add a DHCP reservation (Kea, the network's own)",
             (MAC, ADDRESS, HOSTNAME, SUBNET), _reservation_preview, _reservation_apply,
             "dhcp_v2.reservation_confirm", announces=("dhcp",), optional=("subnet",)),
    StepKind("intent-description", "Set an interface's description in a device's intent",
             (DEVICE, INTERFACE, DESCRIPTION), _description_preview, _description_apply,
             "intent_v2.commit", announces=("intent", "remote")),
    StepKind("ztp-create", "Create a device by ZTP (Add device's Create)", ZTP_PARAMS,
             _ztp_preview, _ztp_apply, "onboard_v2.create", done_level="partial",
             done_words="created and pending: Verify is its own approval",
             announces=("pending", "intent", "credentials", "remote", "in_progress")),
) + _catalog_kinds()}


# ── The plans: each an ordered list of step kinds, derived from its own parameters ──────────

@dataclass(frozen=True)
class Plan:
    key: str
    words: str
    params: tuple
    steps: object
    title: object
    #: Its parameters that may be left out (held as ``""``), each one Mercury derives.
    optional: tuple = ()


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


def _fix_steps_refusal(value) -> str:
    """What an incident plan's ``steps`` is instead of a list of 1 to `MOST_STEPS` catalog
    operations, each exactly ``{operation, params}`` held to the catalog's schema
    (`catalog.checked`), or ``""``."""
    from modules.heal import catalog

    if not isinstance(value, list):
        return kind_of(value)
    if not 1 <= len(value) <= MOST_STEPS:
        return f"a list of {len(value)}"
    for n, s in enumerate(value, 1):
        if (not isinstance(s, dict) or not {"operation", "params"} <= set(s)
                or set(s) - {"operation", "params", "session"}):
            return (f"a list whose step {n} is not exactly {{operation, params}} (and the "
                    "collector step's session)")
        if "session" in s and _session_refusal(s["session"]):
            return f"a list whose step {n} names no session ({_session_refusal(s['session'])})"
        try:
            catalog.checked(s["operation"], s["params"])
        except catalog.Refused as exc:
            return f"a list whose step {n} the catalog refuses ({exc})"
    return ""


FIX_STEPS = Param("steps", f"1 to {MOST_STEPS} operations of Mercury's catalog, in order, each "
                           "exactly {operation, params} held to its schema", _fix_steps_refusal)


def _fix_steps(p: dict) -> list:
    """An incident plan's steps: each catalog operation with the incident and its proposal."""
    return [(s["operation"], dict({"incident": p["incident"], "proposal": p["proposal"]},
                                  **s["params"], **({"session": s["session"]}
                                                    if s.get("session") else {})))
            for s in p["steps"]]


#: The plan an incident's proposal is (C3694; `modules/fixit/plan.py` previews it before it is
#: drawn and routes/fixit_v2.py's Approve starts it by its hash).
INCIDENT_FIX = "incident-fix"


PLANS = {p.key: p for p in (
    Plan("dhcp-reservation", "Reserve an address for a client in the network's DHCP",
         (MAC, ADDRESS, HOSTNAME, SUBNET),
         lambda p: [("dhcp-reservation", dict(p))],
         lambda p: f"Reserve {p['address']} for {p['hostname']} ({p['mac']})",
         optional=("subnet",)),
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
    # C3694 (the operator's R1, 2026-11-14): an incident's fix, a plan of catalog operations
    # the AI (or Mercury's diagnosis) proposed, each step held to its incident's scope and the
    # heal guards at its own preview (`fixit.plan.step_preview`).
    Plan(INCIDENT_FIX, "Fix an incident: the catalog operations its proposal names, in order",
         (INCIDENT, PROPOSAL, FIX_STEPS), _fix_steps,
         lambda p: (f"Fix {p['incident']}: {len(p['steps'])} step"
                    f"{'s' if len(p['steps']) != 1 else ''}")),
)}


def checked(plan, params) -> tuple:
    """``(plan, parameters, steps)``: a named plan held to `PLANS`, its parameters to its schema,
    and its steps derived, each held to its kind's schema; or raises `Refused`. Reads nothing."""
    if not isinstance(plan, str) or plan not in PLANS:
        raise Refused("not_a_plan", (
            f"a plan is one of Mercury's ({listed(sorted(PLANS))}), and "
            f"{said(plan) if isinstance(plan, str) else kind_of(plan)} was named"))
    p = PLANS[plan]
    held = _held(params, p.params, p.key, p.optional)
    steps = p.steps(held)
    if not 1 <= len(steps) <= MOST_STEPS:
        raise Refused("steps", f"{p.key} derived {len(steps)} steps, past 1 to {MOST_STEPS}")
    out = []
    for n, (kind, sp) in enumerate(steps, 1):
        out.append({"n": n, "kind": kind,
                    "params": _held(sp, STEP_KINDS[kind].params, f"step {n} ({kind})",
                                    STEP_KINDS[kind].optional)})
    return p, held, out


def plan_hash(plan: str, params: dict, steps: list, network: str = "") -> str:
    """The plan's one hash: the network it acts on, the plan, its parameters, and each step's
    kind, parameters and own hash, in order, and what its preview resolved (the subnet Mercury
    found for a reservation's address, B1), when it resolved anything. Another network, another
    order, another parameter, another subnet found, or a step whose own preview moved is
    another hash."""
    return _digest({"network": network, "plan": plan, "params": params,
                    "steps": [[s["kind"], s["params"], s.get("hash", "")]
                              + ([s["resolved"]] if s.get("resolved") else [])
                              for s in steps]})


def preview(network: str, plan, params) -> dict:
    """The plan, every step previewed by its own operation: ``{"ok", "plan", "title", "words",
    "params", "steps", "hash", "refused", "code"}``, each step ``{"n", "kind", "words",
    "params", "ok", "hash", "drawn", "refused", "resolved", "found", "choices"}``: *resolved*
    what its preview derived (a reservation's subnet), *found* what was found and from where
    (drawn among its checks), *choices* the candidates when a value is the person's to choose
    (``{"label", "value"}``; its refusal names them in words). Writes nothing."""
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
                 refused=got.get("refused") or "", resolved=dict(got.get("resolved") or {}),
                 found=redact_payload(list(got.get("found") or [])),
                 choices=redact_payload(list(got.get("choices") or [])))
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


#: Each step kind's label on THE stepper (two to four words, docs/UI_RULES.md); its whole words
#: are the step's hover.
STEP_LABELS = {"dhcp-reservation": "DHCP reservation", "intent-description": "Set a description",
               "ztp-create": "Create by ZTP", "telemetry-resubscribe": "Re-subscribe telemetry",
               "telemetry-readd": "Re-add the receiver",
               "telemetry-collector-resubscribe": "Close, then re-subscribe"}
#: A run's outcome -> its one row's group on THE stepper (never done over a partial or a stop).
ROW_GROUP = {"running": "running", "done": "done", "partial": "partial", "stopped": "failed",
             "refused": "failed", "failed": "failed"}


def run_card(rec: dict) -> dict:
    """A plan's run drawn on THE stepper (`run_stepper.card`, `run_stepper` the one macro,
    tests/test_one_stepper.py) from its own record: one row, the plan, its steps in order, each
    its recorded state (one whose done leaves its own approval to come, ZTP's Create, amber as
    needing a person, never green; a moved or failed one failed), the steps after
    a stop not reached, and before the end each step not yet run waiting its turn."""
    from modules import run_stepper as RS

    outcome = rec.get("outcome") or "running"
    ended = rec.get("state") != "running"
    steps = []
    for s in rec.get("plan_steps") or []:
        kind = STEP_KINDS.get(s.get("kind"))
        state = {"done": "needs" if kind and kind.done_level == "partial" else "done",
                 "running": "running", "failed": "failed", "refused": "failed"}.get(
            s.get("state"), "not_reached" if ended else "waiting")
        steps.append(dict(RS.step(f"step-{s.get('n')}",
                                  STEP_LABELS.get(s.get("kind"), f"Step {s.get('n')}"), state,
                                  note=str(s.get("words_said") or "")[:300]),
                          title=f"Step {s.get('n')}: {s.get('words') or ''}"))
    group = ROW_GROUP.get(outcome, "failed") if ended else "running"
    row = RS.row(rec.get("title") or rec.get("plan") or "the plan", group, steps, device=False,
                 detail="" if steps else str(rec.get("why") or "")[:300])
    return RS.card([row], label="The plan's steps", key="plan",
                   group_words={"partial": "done; a step leaves its own approval to come"})


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
                          "outcome": "", "words_said": "", "receipt": {},
                          **({"resolved": s["resolved"]} if s.get("resolved") else {})}
                         for s in p["steps"]]
    step("approve", "ok", f"the plan is the one approved ({p['hash']}): {p['title']}")
    _record(network, rec)
    for s, kept in zip(p["steps"], rec["plan_steps"]):
        kind = STEP_KINDS[s["kind"]]
        name = f"step-{s['n']}"
        again = kind.preview(network, s["params"])
        if (not again.get("ok") or again.get("hash") != s["hash"]
                or dict(again.get("resolved") or {}) != dict(s.get("resolved") or {})):
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
        # Applied with what the approved preview resolved (a reservation's subnet, bound in
        # the plan's hash), never derived again here.
        got = kind.apply(network, dict(s["params"], **(s.get("resolved") or {})), s["hash"],
                         actor=actor, reason=rec["reason"],
                         **({"actor_verified": actor_verified, "person": person}
                            if kind.as_person else {}))
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
          person: bool, reason: str, run_id: str = "") -> dict:
    """Refuse now (``{"refused"}``, nothing run) or start `run` as a job (``{"job",
    "run"}``), the request's verified identity carried into it (`capture_job.start`). *run_id*
    is the run's id when the caller recorded it first (an incident's approve line)."""
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
    run_id = run_id or reads.new_id()
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
