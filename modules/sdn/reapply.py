"""A lost mitigation, found and put back by a person (C2018; PHASE8_PLAN 17.1 S8 and S11, HITL).

**Lost.** A response's flows and meter live on the switch until their hard timeout. A switch
that restarts or reboots drops them early, and the response would still read as applied. The
SDN reader judges each of Mercury's records against what the switch holds (`flow_intent.
classify`, `flow_intent.meter_records`). `lost` groups those judged ``missing`` by the response
that installed them, and keeps only the ones whose hard timeout still has time left at the
moment it is asked. It reads the stored value only, never a controller. Needs attention draws
one row per lost response (`attention.sdn_mitigation_source`), and SDN › Flows draws its
Re-apply… on the switch.

**Answered by a newer response (C2070).** A lost response's detection fires again and is
answered as new (C2005), and that newer response is applied. From then on the lost one's threat
is answered, and putting it back would be a second answer nobody needs. `answered_by` finds the
newer response by the loop's own test of what holds a detection off (`loop.holds`, judged
against the stored read through `as_collected`, and `loop.covering`): another response, in
force, for the same rule on the same switch and the same source (or the same detection). Needs
attention's row resolves then, and a Re-apply… pressed on a page drawn before it is refused,
naming that response.

**A response** is a record whose ``response`` has ``kind`` ``response`` (a threat answered
through `closed_loop.respond_to_threat`); its flows and its meter share the operation that
installed them (``response.operation``), which is the group's key. A flow a person added on
SDN › Flows is not a response, and its absence is drawn on Flows only.

**Re-apply** is the flow-operation core's preview, confirm by hash, apply, verify, rollback
and record (`flow_ops`). It puts back exactly the response's missing recorded flows
(``add_flow`` with ``reinstall``) and its missing meter (``add_meter`` with ``reinstall``),
each as recorded. Each flow's hard timeout is the time its record has LEFT, less
`CONFIRM_WINDOW_S`, so the flow never outlives the response's expiry. A confirm later than
that window after the preview is refused, naming both timeouts, and nothing is sent; preview
again. The records stand as they were, so their expiry is unchanged. The operation is
recorded as a re-apply of the response (``response.kind`` ``reapply``, ``of`` its operation)
and given its line in the loop's log. AUTO never re-applies: that waits for the AUTO
production-readiness gate (PHASE8_PLAN 17.7, C2013).
"""

import logging
import time

log = logging.getLogger(__name__)

#: How long a person has between the preview and the confirm. A re-applied flow's hard timeout
#: is the record's time left less this, so a confirm inside it never extends the response; a
#: later confirm is refused. A choice, not a measurement: how long a person takes to read a
#: preview has not been measured.
CONFIRM_WINDOW_S = 60


class Refused(ValueError):
    """A re-apply refused before anything is sent, in words."""


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch)) if epoch else ""


def is_response(response) -> bool:
    """Whether a record's *response* is a threat's response (`closed_loop.respond_to_threat`),
    not a person's flow edit or a meter's expiry."""
    return isinstance(response, dict) and response.get("kind") == "response"


def group_key(response: dict, fallback: str) -> str:
    """The key a response's flows and meter share: the operation that installed them."""
    return str((response or {}).get("operation") or fallback)


def left_words(seconds: float) -> str:
    """Time left as a person reads it: ``9 min 12 s``, ``45 s``."""
    s = max(0, int(seconds))
    if s >= 3600:
        return f"{s // 3600} h {s % 3600 // 60} min"
    if s >= 60:
        return f"{s // 60} min {s % 60} s"
    return f"{s} s"


def response_words(response: dict) -> str:
    """A response as a person names it: its action's label and its source."""
    from modules.sdn import closed_loop

    action = (response or {}).get("action") or ""
    label = closed_loop.CATALOGUE.get(action, {}).get("label") or action or "a response"
    source = ((response or {}).get("detection") or {}).get("source")
    return f"{label}" + (f" ({source})" if source else "")


def matched_source(flows: list) -> str:
    """The one source address a response's recorded *flows* match (``ipv4_src`` or
    ``ipv6_src``: a drop's flow, or a rate limit's pairs), or "" when they match none or more
    than one. What the flows match, not what the detection named: a source chosen among a
    port's hosts (C2002) is the flow's."""
    found = {str(m.get("ipv4_src") or m.get("ipv6_src")) for m in
             ((r.get("match") or {}) for r in flows or [])
             if m.get("ipv4_src") or m.get("ipv6_src")}
    return found.pop() if len(found) == 1 else ""


def lost_on_switch(controller: dict, switch: dict, now: float) -> list:
    """The responses lost on one switch of the stored read: each ``{"key", "response",
    "cookies", "flows", "meter", "expires_at", "left", ...}``, those whose flows and meter are
    all past their expiry left out."""
    from modules.sdn.flow_intent import cookie_hex

    groups = {}
    for r in switch.get("records") or []:
        exp = r.get("expires_at")
        if r.get("state") != "missing" or not is_response(r.get("response")) \
                or not isinstance(exp, (int, float)) or now >= exp:
            continue
        g = groups.setdefault(group_key(r["response"], f"cookie:{r.get('cookie_hex')}"),
                              {"response": r["response"], "cookies": [], "meter": None,
                               "expires_at": exp, "installed": r.get("installed_at") or ""})
        g["cookies"].append(r.get("cookie_hex") or cookie_hex(r.get("cookie")))
        g["expires_at"] = max(g["expires_at"], exp)
    for m in switch.get("meter_records") or []:
        exp = m.get("expires_at")
        if m.get("state") != "missing" or not is_response(m.get("response")) \
                or not isinstance(exp, (int, float)) or now >= exp:
            continue
        g = groups.setdefault(group_key(m["response"], f"meter:{m.get('meter_id')}"),
                              {"response": m["response"], "cookies": [], "meter": None,
                               "expires_at": exp, "installed": m.get("installed_at") or ""})
        g["meter"] = m.get("meter_id")
        g["expires_at"] = max(g["expires_at"], exp)
    out = []
    for key, g in sorted(groups.items()):
        what = ([f"{len(g['cookies'])} flow{'s' if len(g['cookies']) != 1 else ''} "
                 f"({', '.join(g['cookies'])})"] if g["cookies"] else []) + \
            ([f"meter {g['meter']}"] if g["meter"] is not None else [])
        out.append(dict(g, key=key, connection=controller.get("name"),
                        controller_state=controller.get("state"),
                        as_of=controller.get("last_good_at") or controller.get("read_at"),
                        dpid=switch.get("dpid"), dpid_hex=switch.get("dpid_hex"),
                        name=switch.get("name") or "", left=g["expires_at"] - now,
                        missing_words=" and ".join(what),
                        label=response_words(g["response"])))
    return out


def lost(value: dict, now: float = None) -> list:
    """Every lost response in a stored SDN read (*value*, the reader's), oldest key first."""
    now = time.time() if now is None else now
    out = []
    for c in (value or {}).get("controllers") or []:
        for sw in c.get("switches") or []:
            out += lost_on_switch(c, sw, now)
    return out


# ───────────────────────────────────────────────────── answered by a newer response (C2070)

def as_collected(value: dict) -> dict:
    """A stored SDN read (*value*, the reader's) in the shape `loop.holds` judges against (the
    loop's collection: each controller by its ``connection``, its switches' flows). Only the
    controllers that answered in that read: one carried from an earlier read (not answering)
    is left out, so its switches are not judged and nothing on them is called in force."""
    return {"controllers": [dict(c, connection=c.get("name"))
                            for c in (value or {}).get("controllers") or []
                            if c.get("state") in ("connected", "partial")]}


def answered_by(x: dict, judged: dict):
    """The response in force that answers lost response *x*'s threat (a `lost` row, or one in
    its shape: ``key``, ``response``, ``connection``, ``dpid``), or None: among `loop.holds`'
    *judged*, another response that covers *x*'s detection by the loop's own test
    (`loop.covering`: the same rule on the same connection and switch, for the same detection
    or every source it names), and is active. Once one does, re-applying *x* would put back a
    second answer to a threat already answered."""
    from modules.sdn import loop

    if (judged or {}).get("state") != "ok":
        return None
    d = dict((x.get("response") or {}).get("detection") or {},
             connection=x.get("connection"), dpid=x.get("dpid"))
    active, _others = loop.covering(d, [h for h in judged.get("holds") or []
                                        if h.get("key") != x.get("key")])
    return active


def answered_words(hold: dict) -> str:
    """A response that answers a lost one's threat, as a person names it."""
    return (f"response {hold['id']} ({hold['action']}, operation {hold['key']}) holds "
            f"{', '.join(hold['sources']) or 'its detection'} off on switch "
            f"{hold['dpid_hex'] or hold['dpid']} until {_iso(hold['until'])} ({hold['words']})")


def _answered_on_switch(network: str, connection: str, dpid: int, key: str, response: dict,
                        flows: list, now: float) -> str:
    """Why re-applying response *key* is refused because a newer response answers its threat
    on the switch whose table was read now (*flows*), in words; "" when none does."""
    from modules.sdn import loop

    newer = answered_by({"key": key, "response": response, "connection": connection,
                         "dpid": dpid}, loop.holds(network, {"controllers": [{
                             "connection": connection, "switches": [{
                                 "dpid": dpid, "active_flows": len(flows), "flows": flows}]}]},
                             now))
    if newer is None:
        return ""
    return (f"response {key}'s threat ({response_words(response)}) is answered by a newer "
            f"response: {answered_words(newer)}, as read now")


# ───────────────────────────────────────────────────────────────────────────── the operation

def _members(network: str, connection: str, dpid: int, key: str) -> tuple:
    """The response *key*'s recorded flows and meters on the switch: ``(flows, meters)``, each
    a list of records; raises Refused when the intent cannot be read or holds none."""
    from modules.sdn import flow_intent

    intent = flow_intent.intent(network, connection)
    meters = flow_intent.meters(network)
    if intent["state"] != "ok" or meters["state"] != "ok":
        raise Refused(f"{network}'s flow intent could not be read "
                      f"({intent.get('error') or meters.get('error')}), so no record of the "
                      "response can be found")
    flows = [r for r in intent["flows"] if r.get("dpid") == dpid and is_response(
        r.get("response")) and group_key(r["response"], f"cookie:{r.get('cookie_hex')}") == key]
    ms = [m for m in meters["meters"] if m.get("connection") == connection
          and m.get("dpid") == dpid and is_response(m.get("response"))
          and group_key(m["response"], f"meter:{m.get('meter_id')}") == key]
    if not flows and not ms:
        raise Refused(f"no response {key} is recorded on switch {dpid} ({connection}) with a "
                      "flow or meter Mercury still expects")
    return flows, ms


def build(network: str, connection: str, dpid, key: str, *, driver=None,
          now: float = None) -> dict:
    """The ask for re-applying response *key* on *connection*'s switch *dpid*, reading the
    switch's table (and meters) now: ``{"ok", "error", "ask", "response", "words"}``. Refused
    when nothing of it is missing, when a newer response in force already answers its threat
    on the switch as read now (`answered_by`, C2070), or when its hard timeout passes inside
    `CONFIRM_WINDOW_S`."""
    from modules.sdn import closed_loop, flow_ops
    from modules.sdn.drivers.base import SpecError, parse_dpid
    from modules.sdn.flow_intent import cookie_hex

    now = time.time() if now is None else now
    out = {"ok": False, "error": "", "ask": None, "response": {}, "words": ""}
    try:
        try:
            dpid = parse_dpid(dpid)
        except SpecError as exc:
            raise Refused(str(exc)) from None
        flows, meters = _members(network, connection, dpid, key)
        response = (flows or meters)[0]["response"]
        out["response"] = response
        made = flow_ops._driver(network, connection, driver)
        if not made.get("ok"):
            raise Refused(made.get("error") or f"no driver for {connection!r}")
        read = flow_ops._read_switch(made["driver"], dpid, bool(meters) or any(
            a.get("type") == "METER" for r in flows for a in r.get("actions") or []))
        if not read["ok"]:
            raise Refused(read["error"])
        held = {f.get("cookie") for f in read["flows"]}
        held_meters = {m.get("meter_id") for m in read["meters"]}
        gone = [r for r in flows if r.get("cookie") not in held]
        gone_meters = [m for m in meters if m.get("meter_id") not in held_meters]
        if not gone and not gone_meters:
            raise Refused(
                f"nothing of response {key} is missing on switch {dpid}: its flows "
                f"({', '.join(cookie_hex(r.get('cookie')) for r in flows) or 'none'})"
                + (f" and meter{'s' if len(meters) != 1 else ''} "
                   f"{', '.join(str(m.get('meter_id')) for m in meters)}" if meters else "")
                + " are installed as read now")
        # C2070: a newer response already answers the threat (a person on a page drawn before
        # it was applied): putting this one back would be a second answer nobody needs.
        newer = _answered_on_switch(network, connection, dpid, key, response, read["flows"],
                                    now)
        if newer:
            raise Refused(f"{newer}; nothing to re-apply")
        # C2205: a drop or rate limit matches one source address, so putting it back leaves
        # the same host's other family unmatched, as its own preview said (C2148); the host's
        # other addresses read from the controller's topology now, as that preview reads them.
        source = matched_source(flows) or (response.get("detection") or {}).get("source") or ""
        if source and response.get("action") in closed_loop.FAMILY_GAP_VERB:
            out["source"] = source
            out["same_host"] = closed_loop._same_host(made["driver"], source)
        changes = []
        for m in gone_meters:
            exp = m.get("expires_at")
            if isinstance(exp, (int, float)) and now >= exp:
                raise Refused(f"meter {m.get('meter_id')}'s response expired at {_iso(exp)}: "
                              "nothing to re-apply")
            changes.append({"do": "add_meter", "reinstall": True, "meter": {
                "meter_id": m.get("meter_id"), "flags": list(m.get("flags") or []),
                "bands": [dict(b) for b in m.get("bands") or []]}})
        expiry = []
        for r in gone:
            hard, at = r.get("hard_timeout") or 0, r.get("installed_at")
            if not hard or not isinstance(at, (int, float)):
                raise Refused(f"flow {cookie_hex(r.get('cookie'))} has no hard timeout "
                              "recorded, so its time left is not known; a response's flow "
                              "always has one")
            left = int(at + hard - now) - CONFIRM_WINDOW_S
            if left < 1:
                raise Refused(
                    f"flow {cookie_hex(r.get('cookie'))}'s hard timeout ends at "
                    f"{_iso(at + hard)}, {left_words(at + hard - now)} from now, within the "
                    f"{CONFIRM_WINDOW_S} s a confirm may take: nothing to re-apply (answer "
                    "the threat again on SDN › Responses if it is still there)")
            expiry.append(at + hard)
            changes.append({"do": "add_flow", "reinstall": True, "flow": {
                "table_id": r.get("table_id", 0), "priority": r.get("priority"),
                "cookie": r.get("cookie"), "match": r.get("match") or {},
                "actions": r.get("actions") or [], "idle_timeout": r.get("idle_timeout") or 0,
                "hard_timeout": left}})
        ends = max(expiry) if expiry else max((m.get("expires_at") or 0) for m in gone_meters)
        out["ask"] = {"connection": connection, "dpid": dpid, "changes": changes,
                      "response": bool(gone), "action": "reapply",
                      "reapply": {"of": key, "action": response.get("action") or "",
                                  "expires_at": ends,
                                  "cookies": [cookie_hex(r.get("cookie")) for r in gone],
                                  "meters": [m.get("meter_id") for m in gone_meters]}}
        out["words"] = (f"Puts back {response_words(response)}, operation {key}: "
                        + " and ".join(
                            ([f"{len(gone)} flow{'s' if len(gone) != 1 else ''}"] if gone else [])
                            + ([f"meter {', '.join(str(m['meter_id']) for m in gone_meters)}"]
                               if gone_meters else []))
                        + f" missing, as recorded, until {_iso(ends)} (its hard timeout)")
        out["ok"] = True
    except (Refused, flow_ops.Refused) as exc:
        out["error"] = str(exc)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("sdn reapply: the re-apply could not be built (%s)", type(exc).__name__)
        out["error"] = f"the re-apply could not be built: {type(exc).__name__}: {exc}"
    return out


def preview(network: str, connection: str, dpid, key: str, *, driver=None,
            now: float = None) -> dict:
    """The PREVIEW of re-applying response *key*, writing nothing: `build`'s answer with
    ``plan``, `flow_ops.plan`'s exact requests and their hash. A drop's or rate limit's
    What will not happen says the source's other family is not matched, naming the host's
    other addresses the controller's topology lists (`closed_loop.response_family_gap`, the
    sentence the response's own preview said; C2205)."""
    from modules.sdn import closed_loop, flow_ops

    built = build(network, connection, dpid, key, driver=driver, now=now)
    if not built["ok"]:
        return dict(built, plan=None)
    p = flow_ops.plan(network, built["ask"], driver=driver)
    if p["ok"]:
        p["will_not"].append(
            f"Nothing it puts back outlives the response's own hard timeout, "
            f"{_iso(built['ask']['reapply']['expires_at'])}: each flow's hard timeout is the "
            f"time its record has left less {CONFIRM_WINDOW_S} s for your confirm, and a "
            f"confirm more than {CONFIRM_WINDOW_S} s after this preview is refused.")
        p["will_not"].append("Its records are not changed: the response keeps the expiry it "
                             "was applied with.")
        gap = closed_loop.response_family_gap((built.get("response") or {}).get("action"),
                                              built.get("source") or "", built.get("same_host"))
        if gap:
            p["will_not"].append(gap)
    return dict(built, plan=p, ok=p["ok"], error=p["error"])


def confirm(network: str, ask: dict, confirmed_hash: str, *, actor: str,
            actor_verified: str = "", driver=None, now=time.time, **apply_kwargs) -> dict:
    """The APPLY of a previewed re-apply, as *actor*: the ask carried back is held to the
    records again (every change a reinstall of the response's, no flow's hard timeout above
    what its record has left now, and no newer response answering its threat on the switch as
    read now, C2070), then `flow_ops.apply` (the hash compared, the switch held,
    Verify, rollback, record), recorded as a re-apply of the response."""
    from modules.sdn import flow_ops
    from modules.sdn.drivers.base import SpecError, parse_dpid
    from modules.sdn.flow_intent import cookie_hex

    refused = {"ok": False, "outcome": "refused", "id": "", "plan": None}
    if not isinstance(ask, dict) or ask.get("action") != "reapply" or \
            not isinstance(ask.get("reapply"), dict):
        return dict(refused, error="the confirm's preview is not a re-apply: nothing was sent")
    key = str(ask["reapply"].get("of") or "")
    try:
        dpid = parse_dpid(ask.get("dpid"))
        flows, meters = _members(network, ask.get("connection") or "", dpid, key)
    except (SpecError, Refused) as exc:
        return dict(refused, error=f"{exc}: nothing was sent")
    recorded = {r.get("cookie"): r for r in flows}
    recorded_meters = {m.get("meter_id") for m in meters}
    at = now()
    for c in ask.get("changes") or []:
        if not c.get("reinstall") or c.get("do") not in ("add_flow", "add_meter"):
            return dict(refused, error=(f"a re-apply only puts back recorded flows and meters, "
                                        f"and its change {c.get('do')!r} is not a reinstall: "
                                        "nothing was sent"))
        if c["do"] == "add_meter":
            mid = (c.get("meter") or {}).get("meter_id")
            if mid not in recorded_meters:
                return dict(refused, error=(f"meter {mid} is not response {key}'s (it records "
                                            f"{sorted(recorded_meters) or 'none'}): nothing "
                                            "was sent"))
            continue
        flow = c.get("flow") or {}
        rec = recorded.get(flow.get("cookie"))
        if rec is None:
            return dict(refused, error=(f"flow {cookie_hex(flow.get('cookie'))} is not "
                                        f"response {key}'s: nothing was sent"))
        left = int(rec["installed_at"] + (rec.get("hard_timeout") or 0) - at)
        if not isinstance(flow.get("hard_timeout"), int) or flow["hard_timeout"] > left:
            return dict(refused, error=(
                f"flow {cookie_hex(flow.get('cookie'))} would be put back for "
                f"{flow.get('hard_timeout')} s, and its record has {max(left, 0)} s left now: "
                f"the preview is more than {CONFIRM_WINDOW_S} s old, and sending it would "
                "outlive the response; nothing was sent: preview again"))
    # C2070: previewed before a newer response answered the threat, confirmed after it.
    made = flow_ops._driver(network, ask.get("connection") or "", driver)
    if made.get("ok"):
        read = flow_ops._read_switch(made["driver"], dpid, False)
        newer = _answered_on_switch(
            network, ask.get("connection") or "", dpid, key,
            ((flows or meters)[0].get("response") or {}), read["flows"], at) \
            if read["ok"] else ""
        if newer:
            return dict(refused, error=f"{newer}: nothing was sent")
    response = {"kind": "reapply", "of": key,
                "action": ask["reapply"].get("action") or "",
                "detection": ((flows or meters)[0].get("response") or {}).get("detection") or {},
                "cookies": list(ask["reapply"].get("cookies") or []),
                "meters": list(ask["reapply"].get("meters") or [])}
    return flow_ops.apply(network, ask, confirmed_hash, actor=actor,
                          actor_verified=actor_verified, response=response, driver=driver,
                          now=now, **apply_kwargs)
