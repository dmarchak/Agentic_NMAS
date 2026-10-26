"""The needs round, once, for every feature (PHASE8_PLAN 15.15, item 3; the operator's ruling of
2026-10-26: "the needs round lives once, in a shared module that every feature calls; features
never loop themselves").

An answer may name what it lacked (`needs`, each a kind from the fixed `NeedKind` and its
subject). This module, never the feature and never the gateway:
- **validates** each need: an unknown kind, or a malformed one, is refused, naming it;
- **looks each up**, read-only, through the existing stores (the endpoint layer, the network's
  neighbours, committed intent). A lookup that fails is reported as unfulfilled, never retried;
  a kind no store answers yet (routes) is unfulfilled, saying so;
- **applies the egress class**: every kind is the topology class, so with the network's topology
  switch off each need is unfulfilled (egress), and the answer says so;
- **makes at most one follow-up**, an ordinary `gateway.ask` the feature hands in (*follow*),
  its call linked to the first (``subject["parent"]``); a second round, or a round on a call
  that is itself a follow-up, is refused;
- **records** the needs, fulfilled or not, on the first call's use row (`calls.record_use`).
"""

import json
import logging
from enum import Enum

from modules.ai.schemas import StrictModel

log = logging.getLogger(__name__)

#: The follow-ups a first call may have: one.
MAX_ROUNDS = 1


class NeedKind(str, Enum):
    endpoint_location = "endpoint_location"
    interface_state = "interface_state"
    neighbour = "neighbour"
    route = "route"


class Need(StrictModel):
    """One thing an answer lacked: its kind, and what it is about (an endpoint's name, address
    or MAC; a device; a device and an interface as ``device interface``)."""
    kind: NeedKind
    subject: str


def validate(raw) -> dict:
    """``{"needs": [Need], "refused": [why]}`` from an answer's *raw* needs (JSON values)."""
    out, refused = [], []
    for i, item in enumerate(raw or []):
        try:
            out.append(Need.model_validate_json(json.dumps(item)))
        except Exception as exc:                        # noqa: BLE001 (refused, naming it)
            kind = item.get("kind") if isinstance(item, dict) else None
            refused.append(f"need {i}: " + (f"the kind {kind!r} is not one Mercury looks up"
                                           if kind not in {k.value for k in NeedKind}
                                           else f"not a need ({type(exc).__name__})"))
    return {"needs": out, "refused": refused}


def lookup(network: str, need: Need) -> dict:
    """``{"kind", "subject", "state": "fulfilled"|"unfulfilled", "why", "data"}``: one need
    looked up, read-only, once. Never raises."""
    from modules.ai import egress_classes
    base = {"kind": need.kind.value, "subject": need.subject, "state": "unfulfilled",
            "why": "", "data": None}
    gate = egress_classes.topology_allowed(network)
    if not gate["allowed"]:
        return dict(base, why=f"egress: {gate['why']}")
    try:
        data, why = _LOOKUPS[need.kind](network, need.subject)
    except Exception as exc:                            # noqa: BLE001 (unfulfilled, never retried)
        return dict(base, why=f"the lookup failed ({type(exc).__name__}: {exc}); not retried")
    if why:
        return dict(base, why=why)
    return dict(base, state="fulfilled", data=data)


def _endpoint(network, subject):
    from modules import endpoints as E
    got = E.stored(network)
    if got["state"] != "read":
        return None, f"no endpoint read for {network} ({got['why']})"
    hours = E.stale_after_hours(network)
    found = [dict({k: e.get(k) for k in ("mac", "addresses", "hostname", "device", "interface",
                                         "vlan", "last_seen")},
                  **{k: v for k, v in E.seen(e, stale_hours=hours).items()
                     if k in ("said", "stale")})
             for e in E.find(got.get("endpoints") or [], subject)]
    return (found, "") if found else (None, f"{subject} is not observed (read "
                                            f"{got.get('read_at') or 'never'})")


def _neighbour(network, subject):
    from modules.ai import intent_names
    nb = intent_names.neighbours_of(network, subject)
    ports = nb.get("ports") or {}
    if not ports:
        return None, "; ".join(nb.get("said") or []) or f"{subject} has no known neighbour"
    return ports, ""


def _interface(network, subject):
    from modules.ai import intent_names
    from modules.nsot import hostvars, intent_edit, ifnames
    device, _sp, iface = subject.partition(" ")
    opened = intent_edit.open_doc(network, device)
    if not opened["ok"]:
        return None, f"{device} has no committed intent ({opened['error']})"
    for i in intent_names.interfaces_of(hostvars.from_yaml(opened["yaml"]) or {}):
        if ifnames.same_interface(i["name"], iface):
            return {"device": device, "interface": i["name"], "shutdown": i["shutdown"],
                    "mode": i["mode"], "description": i["description"],
                    "source": "committed intent"}, ""
    return None, f"{device} has no interface {iface!r} in its committed intent"


def _route(network, subject):
    return None, "no route table is read (the route layer is not collected)"


_LOOKUPS = {NeedKind.endpoint_location: _endpoint, NeedKind.neighbour: _neighbour,
            NeedKind.interface_state: _interface, NeedKind.route: _route}


def run(parent_call_id: str, network: str, raw, *, actor: str, follow) -> dict:
    """The needs round for the call *parent_call_id*: validated, looked up and recorded, then
    at most one follow-up, ``follow(results, subject_link)`` (the feature's own
    `gateway.ask`, its subject carrying *subject_link*). ``{"ok", "error", "results",
    "refused", "follow_up"}``; refused, with nothing looked up, for a second round."""
    from modules.ai import calls
    found = calls.find(parent_call_id)
    row = found.get("row") or {}
    if found["state"] != "ok":
        return {"ok": False, "error": f"the call {parent_call_id} is not recorded", "results": [],
                "refused": [], "follow_up": None}
    if (row.get("subject") or {}).get("parent"):
        return {"ok": False, "error": f"{parent_call_id} is itself a follow-up: a second round "
                                      f"is refused (at most {MAX_ROUNDS})",
                "results": [], "refused": [], "follow_up": None}
    if any(u.get("use") == "needs round" for u in found.get("uses") or []):
        return {"ok": False, "error": f"{parent_call_id} had its round: a second is refused "
                                      f"(at most {MAX_ROUNDS})",
                "results": [], "refused": [], "follow_up": None}
    checked = validate(raw)
    results = [lookup(network, n) for n in checked["needs"]]
    calls.record_use(parent_call_id, "needs round", actor=actor,
                     detail="; ".join(f"{r['kind']} {r['subject']}: {r['state']}"
                                      + (f" ({r['why']})" if r["why"] else "")
                                      for r in results)[:400]
                     + ("; refused: " + "; ".join(checked["refused"]) if checked["refused"]
                        else ""),
                     needs=[{k: r[k] for k in ("kind", "subject", "state", "why")}
                            for r in results] + [{"refused": w} for w in checked["refused"]])
    follow_up = None
    if results:
        follow_up = follow(results, {"parent": parent_call_id})
    return {"ok": True, "error": "", "results": results, "refused": checked["refused"],
            "follow_up": follow_up}
