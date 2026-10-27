"""The flow-operation core: ONE path for every flow and meter Mercury installs, edits or removes
on an SDN controller (PHASE8_PLAN 17.1 S8, with S16's backend; C1912). A response to a threat
(`closed_loop.respond_to_threat`) and a person's edit on SDN › Flows are the same operation:
preview, confirm by hash, apply holding the switch, verify, roll back on failure, record.

**An operation** is an *ask* (a mapping a form can carry and a confirm can send back, nothing
read from the switch in it) naming a connection, a switch and its changes, in order:
- ``add_flow``: a flow with Mercury's cookie (the caller draws it, `flow_intent.new_cookie`,
  so the preview and the apply send the same body);
- ``edit_flow``: one of Mercury's recorded flows, named by its table, priority, match and
  cookie, given new actions or timeouts by modify-strict; a change of its match, priority or
  table, or of its timeouts where the switch keeps a flow's timeouts on a modify
  (`MODIFY_KEEPS`), is a delete-strict of the old flow and an add of the new one, in one
  operation, and the preview says so;
- ``remove_flow``: delete-strict by table, priority, match and cookie, never a wildcard; the
  table-miss flow refused without its typed confirmation (`TABLE_MISS_WORDS`); a flow the
  controller's application owns warned (a reactive application may install it again);
- ``add_meter``: one meter, its bands checked against the switch's meter features;
- ``remove_meter``: refused while a flow the operation leaves in place still points at it.

**The plan** (`plan`) reads the switch's flow table (and its meters, where a change touches
one) and answers, with no write: the exact requests, each a driver render (method, path, body),
in order; each request's undo; what each does in words; what will not happen; the warnings;
the checks; and the hash (`plan_hash`) over the requests, their undos and the before-state of
every flow the operation touches. A refusal names the comparison it made and both operands.

**OpenFlow 1.3's match prerequisites** are enforced before anything else (`match_rules`): a
field without the field it depends on is refused, naming the field missing and its value.

**The apply** (`apply`) plans again and compares the hash (a moved table or request is refused,
naming both hashes; nothing is sent), holds the switch across processes (`device_ops.hold`),
sends each request through the driver's one send path (`ControllerDriver.apply`, exactly the
rendered body), then **Verify**:
- installed, gating: the table read back (up to `VERIFY_READS` reads `VERIFY_PAUSE` apart,
  since the controller's 200 says sent, not installed): each added or edited flow present with
  its cookie, match, priority, actions and hard timeout; each removed flow absent; each meter
  present with its band, or absent;
- counters, reported: a meter's band counted twice `COUNTER_INTERVAL` apart (the drop count
  rising while the flow matches shows the limit working), a drop flow's packets;
- "unaffected host pairs still pass": REPORTED as the operator's to test by traffic (S20:
  Verify checks installation and counters; testing traffic from the hosts is the operator's).
On a failed send or a failed gating check, **rollback** sends the undo of each request that
landed, newest first, and reads the table back. **The record** (`flow_intent`): each flow added
and kept (``installed``), edited in place (``amended``), Mercury's flow removed
(``withdrawn``), each meter, and the operation's whole run (``operation``), which History
reads (`history_sources.sdn_operations`).

**Timeouts.** Every response flow carries a hard timeout (the network's
`sdn_response_hard_timeout_seconds`, at most `sdn_response_max_seconds`); a meter has no
timeout in OpenFlow, so a response's meter is recorded with its expiry and removed by
`expire_meters` once no flow points at it.
"""

import hashlib
import json
import logging
import secrets
import time

log = logging.getLogger(__name__)

DO = ("add_flow", "edit_flow", "remove_flow", "add_meter", "remove_meter")
#: The operation's steps, as `apply` reports the one reached (``at``) and the manual names them
#: (docs/manual/how-it-works/sdn-flows.md).
STEPS = ("plan", "hash", "hold", "send", "verify", "rollback", "record")
#: What a person types to remove the table-miss flow.
TABLE_MISS_WORDS = "remove table-miss"
#: Whether the switch keeps a flow's timeouts on a modify (OpenFlow 1.3.5 section 6.4: a
#: modify replaces the instructions; the cookie, timeouts, flags and counters are left as they
#: were). Measured on the lab's Open vSwitch 2.17.12 on 2026-10-27: a modify-strict sending a
#: new cookie and new timeouts left both as they were and replaced the actions
#: (tests/fixtures/sdn/lab8/modify_strict.json, its README).
MODIFY_KEEPS = ("cookie", "idle_timeout", "hard_timeout")
#: The table read back after a write: the controller's 200 says sent, not installed.
VERIFY_READS = 4
VERIFY_PAUSE = 0.5
#: A meter's band and its flow counted twice this far apart (seconds), reported.
COUNTER_INTERVAL = 3.0
#: The response flows' priority: above every flow not Mercury's on the switch, by this step,
#: and at least `RESPONSE_PRIORITY_FLOOR` (a documented scheme, never chosen by AI).
RESPONSE_PRIORITY_FLOOR = 300
RESPONSE_PRIORITY_STEP = 10
SETTINGS = {"sdn_response_hard_timeout_seconds": 600, "sdn_response_max_seconds": 3600}
VERIFY_LIMIT = ("Verify checks installation and counters; testing traffic from the hosts is "
                "the operator's (a probe that sends test traffic is registered for later, "
                "C1915)")


class Refused(ValueError):
    """An operation refused before anything is sent, in words."""


# ───────────────────────────────────────────────────────────────────────────── small helpers

def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _identity(flow: dict) -> dict:
    """What OpenFlow knows a flow by (with its cookie): the table, the priority, the match."""
    from modules.sdn.flow_intent import normal_match

    return {"table_id": flow.get("table_id", 0), "priority": flow.get("priority", 0),
            "match": normal_match(flow.get("match")), "cookie": flow.get("cookie", 0)}


def _same_place(a: dict, b: dict) -> bool:
    from modules.sdn.flow_intent import normal_match

    return (a.get("table_id", 0) == b.get("table_id", 0)
            and a.get("priority", 0) == b.get("priority", 0)
            and normal_match(a.get("match")) == normal_match(b.get("match")))


def _snapshot(flow: dict) -> dict:
    """A flow as the hash binds it: everything but its counters and age."""
    from modules.sdn.flow_intent import normal_actions

    keep = _identity(flow)
    keep.update(actions=[list(x) for x in normal_actions(flow.get("actions"))],
                idle_timeout=flow.get("idle_timeout", 0),
                hard_timeout=flow.get("hard_timeout", 0))
    return keep


def match_words(match: dict) -> str:
    from modules.sdn.match_rules import _said

    return ", ".join(f"{k}={_said(k, v)}" for k, v in sorted((match or {}).items())) or \
        "everything"


def flow_words(flow: dict) -> str:
    from modules.sdn.flow_intent import action_words, cookie_hex

    times = []
    if flow.get("idle_timeout"):
        times.append(f"idle {flow['idle_timeout']} s")
    if flow.get("hard_timeout"):
        times.append(f"hard {flow['hard_timeout']} s")
    return (f"table {flow.get('table_id', 0)}, priority {flow.get('priority', 0)}, match "
            f"{match_words(flow.get('match'))}, actions {action_words(flow.get('actions'))}, "
            f"cookie {cookie_hex(flow.get('cookie', 0))}"
            + (f", {' and '.join(times)}" if times else ", no timeout"))


def plan_hash(network: str, connection: str, dpid: int, steps: list, before: list) -> str:
    """The sha256 a confirm binds to: the switch, every request and its undo (method, path and
    the exact body), and the before-state of every flow the operation touches."""
    def req(r):
        return [r.get("method"), r.get("path"), r.get("body")] if r else None

    text = json.dumps({"network": network, "connection": connection, "dpid": dpid,
                       "steps": [[s["role"], req(s["request"]), req(s.get("undo"))]
                                 for s in steps],
                       "before": before}, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def settings_of(network: str) -> dict:
    """The network's response timeouts: ``{"ok", "values", "error"}``; one unreadable or out
    of bounds refuses, naming it (a guessed timeout would look like one set)."""
    from modules import list_settings

    values = {}
    for key, default in SETTINGS.items():
        try:
            got = list_settings.value(network, key, default)
        except Exception as exc:                      # noqa: BLE001 (said, never raised)
            return {"ok": False, "values": {},
                    "error": f"{network}'s {key} could not be read ({type(exc).__name__})"}
        if isinstance(got, bool) or not isinstance(got, int) or not 1 <= got <= 0xFFFF:
            return {"ok": False, "values": {},
                    "error": f"{network}'s {key} is {got!r}, not a whole number of seconds from "
                             "1 to 65535"}
        values[key] = got
    if values["sdn_response_hard_timeout_seconds"] > values["sdn_response_max_seconds"]:
        return {"ok": False, "values": {},
                "error": (f"{network}'s sdn_response_hard_timeout_seconds "
                          f"({values['sdn_response_hard_timeout_seconds']}) is above its "
                          f"sdn_response_max_seconds ({values['sdn_response_max_seconds']})")}
    return {"ok": True, "values": values, "error": ""}


def disjoint(a: dict, b: dict) -> bool:
    """Whether no packet can match both matches: a field both name with different exact values
    (an LLDP flow's eth_type 0x88cc and a response's 0x0800). A masked value is never called
    disjoint (it may overlap)."""
    from modules.sdn.flow_intent import normal_match

    a, b = normal_match(a), normal_match(b)
    for key in set(a) & set(b):
        x, y = a[key], b[key]
        if "/" in str(x) or "/" in str(y):
            continue
        if x != y:
            return True
    return False


def response_priority(flows: list, own_cookies=(), intent_cookies=(), match=None) -> int:
    """The priority a response's flow takes on a switch: `RESPONSE_PRIORITY_STEP` above the
    highest flow that is not Mercury's and could match the same packets as *match* (a flow
    disjoint from it, such as the controller's LLDP flow at 65535, cannot shadow it), and at
    least `RESPONSE_PRIORITY_FLOOR`."""
    from modules.sdn.flow_intent import is_mercury

    others = [f.get("priority", 0) for f in flows or []
              if (not is_mercury(f.get("cookie")) or f.get("cookie") not in set(intent_cookies))
              and not (match is not None and disjoint(f.get("match") or {}, match))]
    top = max(others) if others else 0
    return min(0xFFFF, max(RESPONSE_PRIORITY_FLOOR, top + RESPONSE_PRIORITY_STEP))


def free_meter_id(meters: list, features: dict = None, taken=(), flows=()) -> int:
    """The lowest meter id not on the switch, not pointed at by any of its *flows* (a meter
    there would limit that flow too), nor *taken* by an earlier step, within its
    `max_meter`."""
    used = {m.get("meter_id") for m in meters or []} | set(taken) | {
        a.get("meter_id") for f in flows or [] for a in f.get("actions") or []
        if a.get("type") == "METER"}
    top = (features or {}).get("max_meter") or 0xFFFF0000
    for n in range(1, top + 1):
        if n not in used:
            return n
    raise Refused(f"the switch has no free meter id (it holds {len(used)} of {top})")


# ───────────────────────────────────────────────────────────────────────────── reading

def _driver(network: str, name: str, driver=None) -> dict:
    if driver is not None:
        return driver(network, name)
    from modules.sdn import connections

    return connections.driver_for(network, name)


def _read_switch(drv, dpid: int, meters: bool) -> dict:
    """The switch's flow table, and its meters and meter features when *meters*."""
    out = {"ok": False, "error": "", "flows": [], "meters": [], "features": None}
    got = drv.flows(dpid)
    if not got.get("ok"):
        out["error"] = f"the flow table of switch {dpid} could not be read: {got.get('error')}"
        return out
    out["flows"] = got.get("flows") or []
    if meters:
        m = drv.meters(dpid)
        if not m.get("ok"):
            out["error"] = f"the meters of switch {dpid} could not be read: {m.get('error')}"
            return out
        f = drv.meter_features(dpid)
        if not f.get("ok"):
            out["error"] = (f"the meter features of switch {dpid} could not be read: "
                            f"{f.get('error')}")
            return out
        out["meters"], out["features"] = m.get("meters") or [], f.get("features")
    out["ok"] = True
    return out


# ───────────────────────────────────────────────────────────────────────────── the plan

def _spec(dpid: int, flow: dict):
    """A flow to send, its numeric match fields as numbers; raises Refused naming every
    problem, the match prerequisites first."""
    from modules.sdn import match_rules
    from modules.sdn.drivers.base import SpecError, flow_from_spec

    if not isinstance(flow, dict):
        raise Refused(f"a flow is a mapping of its fields, not {type(flow).__name__}")
    values = {k: v for k, v in flow.items()
              if k not in ("packet_count", "byte_count", "duration_sec", "dpid", "id",
                           "owner", "differs", "words", "record")}
    values["match"] = match_rules.normalise(values.get("match") or {})
    problems = match_rules.problems(values["match"]) + match_rules.set_field_problems(
        values["match"], values.get("actions") or [])
    if problems:
        raise Refused("; ".join(problems))
    try:
        return flow_from_spec(dpid, values)
    except SpecError as exc:
        raise Refused(str(exc)) from None


def _find(flows: list, target: dict):
    """The installed flow *target* names (table, priority, match, and its cookie when given),
    or None."""
    hits = [f for f in flows if _same_place(f, target)
            and ("cookie" not in target or f.get("cookie") == target.get("cookie"))]
    return hits[0] if hits else None


def _target_said(target: dict) -> str:
    from modules.sdn.flow_intent import cookie_hex

    return (f"table {target.get('table_id', 0)}, priority {target.get('priority', 0)}, match "
            f"{match_words(target.get('match'))}"
            + (f", cookie {cookie_hex(target['cookie'])}" if "cookie" in target else ""))


def _rendered(answer: dict, what: str) -> dict:
    if not answer.get("ok"):
        raise Refused(f"{what} could not be rendered: {answer.get('error')}")
    return {k: answer[k] for k in ("method", "path", "body")}


def _remaining(flow: dict) -> int:
    """A removed flow's undo keeps its hard timeout's REMAINDER (a rollback never extends a
    flow's life); 0 for a flow with none."""
    hard = flow.get("hard_timeout") or 0
    if not hard:
        return 0
    return max(1, hard - int(flow.get("duration_sec") or 0))


def plan(network: str, ask: dict, *, driver=None) -> dict:
    """The preview of *ask*, reading the switch and writing nothing. See the module's
    docstring. ``{"ok", "error", ...}``: on a refusal ``ok`` is False and ``error`` names the
    comparison made and both operands."""
    from modules.sdn import flow_intent
    from modules.sdn.drivers.base import SpecError, dpid_hex, parse_dpid

    out = {"ok": False, "error": "", "network": network, "ask": ask, "steps": [], "words": [],
           "will_not": [], "warnings": [], "checks": [], "hash": "", "before": [],
           "needs_typed": "", "intent_changes": [], "read_at": ""}
    try:
        if not isinstance(ask, dict):
            raise Refused("an operation is a mapping naming its connection, switch and changes")
        conn_name = ask.get("connection") or ""
        try:
            dpid = parse_dpid(ask.get("dpid"))
        except SpecError as exc:
            raise Refused(str(exc)) from None
        changes = ask.get("changes")
        if not isinstance(changes, list) or not changes:
            raise Refused("an operation names at least one change")
        unknown = [c.get("do") if isinstance(c, dict) else c for c in changes
                   if not isinstance(c, dict) or c.get("do") not in DO]
        if unknown:
            raise Refused(f"a change is one of {', '.join(DO)}, not {unknown[0]!r}")
        out.update(connection=conn_name, dpid=dpid, dpid_hex=dpid_hex(dpid))
        made = _driver(network, conn_name, driver)
        if not made.get("ok"):
            raise Refused(made.get("error") or f"no driver for {conn_name!r}")
        drv = made["driver"]
        conn = made.get("connection") or {"name": conn_name}
        own = set(conn.get("own_cookies") or [0])
        needs_meters = any(c["do"] in ("add_meter", "remove_meter") for c in changes) or any(
            a.get("type") == "METER" for c in changes for a in
            ((c.get("flow") or {}).get("actions") or []) if isinstance(a, dict))
        read = _read_switch(drv, dpid, needs_meters)
        if not read["ok"]:
            raise Refused(read["error"])
        out["read_at"] = _iso(time.time())
        flows, meters, features = read["flows"], read["meters"], read["features"]
        intent = flow_intent.intent(network, conn_name)
        if intent["state"] != "ok":
            raise Refused(f"{network}'s flow intent could not be read ({intent['error']}), so "
                          "no flow can be told Mercury's")
        recorded = {r.get("cookie"): r for r in intent["flows"]}
        response = bool(ask.get("response"))
        limits = settings_of(network) if response else {"ok": True, "values": {}}
        if not limits["ok"]:
            raise Refused(limits["error"])
        # The flows and meters as the operation leaves them, step by step: a later change
        # sees what an earlier one adds or removes.
        table = [dict(f) for f in flows]
        meter_ids = {m.get("meter_id"): m for m in meters}
        steps, before = [], []
        for change in changes:
            do = change["do"]
            if do == "add_meter":
                steps.append(_plan_add_meter(drv, dpid, change, meter_ids, features, table,
                                             out))
            elif do == "remove_meter":
                steps.append(_plan_remove_meter(drv, dpid, change, meter_ids, table, changes,
                                                out))
            elif do == "add_flow":
                steps.append(_plan_add_flow(drv, dpid, change, table, recorded, meter_ids,
                                            response, limits["values"], out))
            elif do == "remove_flow":
                steps.append(_plan_remove_flow(drv, dpid, change, table, recorded, own, ask,
                                               before, out))
            elif do == "edit_flow":
                steps += _plan_edit_flow(drv, dpid, change, table, recorded, meter_ids,
                                         before, out)
        out["steps"] = steps
        out["before"] = before
        out["hash"] = plan_hash(network, conn_name, dpid, steps, before)
        out["will_not"].append("No flow but those named above is added, changed or removed: "
                               "every removal is delete-strict, never a wildcard.")
        if response:
            longest = max([c["flow"].get("hard_timeout") or 0 for c in changes
                           if c["do"] == "add_flow"] or [0])
            out["will_not"].append(
                f"Nothing it adds outlives {longest} s, its hard timeout: a mistaken response "
                "expires by itself (its meter, if any, is removed once its flows have expired).")
        out["checks"] = _checks(steps)
        out["verify_limit"] = VERIFY_LIMIT
        out["ok"] = True
    except Refused as exc:
        out["error"] = str(exc)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.error("sdn flow_ops: the plan for %s failed (%s)", network, type(exc).__name__)
        out["error"] = f"the plan could not be made: {type(exc).__name__}: {exc}"
    return out


def _plan_add_flow(drv, dpid, change, table, recorded, meter_ids, response, limits, out):
    from modules.sdn import flow_intent

    flow = _spec(dpid, change.get("flow"))
    if not flow_intent.is_mercury(flow.cookie):
        raise Refused(f"a flow Mercury adds carries Mercury's cookie, and "
                      f"{flow_intent.cookie_hex(flow.cookie)} is not one")
    reinstall = bool(change.get("reinstall"))
    if reinstall:
        rec = recorded.get(flow.cookie)
        if rec is None or not _same_place(rec, flow.as_dict()) or rec.get("dpid") != dpid:
            raise Refused(f"a reinstall puts back Mercury's recorded flow as recorded, and "
                          f"cookie {flow_intent.cookie_hex(flow.cookie)} has no such record "
                          f"on switch {dpid}")
        if any(f.get("cookie") == flow.cookie for f in table):
            raise Refused(f"Mercury's flow {flow_intent.cookie_hex(flow.cookie)} is installed: "
                          "nothing to reinstall")
    elif flow.cookie in recorded or any(f.get("cookie") == flow.cookie for f in table):
        raise Refused(f"cookie {flow_intent.cookie_hex(flow.cookie)} is already used (recorded "
                      "or installed): preview again for a fresh one")
    held = _find(table, {"table_id": flow.table_id, "priority": flow.priority,
                         "match": flow.match})
    if held is not None:
        raise Refused(f"the switch already holds a flow at table {flow.table_id}, priority "
                      f"{flow.priority} with this match (cookie "
                      f"{flow_intent.cookie_hex(held.get('cookie'))}); an add would replace it "
                      "without a word: edit or remove that flow instead")
    for a in flow.actions:
        if a.get("type") == "METER" and a.get("meter_id") not in meter_ids:
            raise Refused(f"the flow points at meter {a.get('meter_id')}, and switch {dpid} "
                          f"holds meters {sorted(meter_ids) or 'none'}")
    if response:
        top = limits["sdn_response_max_seconds"]
        if not flow.hard_timeout or flow.hard_timeout > top:
            raise Refused(f"a response's flow carries a hard timeout from 1 to {top} s (the "
                          f"network's sdn_response_max_seconds), not {flow.hard_timeout}")
    spec = flow.as_dict()
    request = _rendered(drv.render_add_flow(dpid, spec), "the add")
    undo = _rendered(drv.render_delete_flow_strict(dpid, spec), "its undo")
    table.append(dict(spec))
    out["intent_changes"].append({"kind": "reinstalled" if reinstall else "installed",
                                  "flow": spec})
    out["words"].append(("Put back Mercury's recorded flow" if reinstall else "Add a flow")
                        + f" on {out['dpid_hex']}: {flow_words(spec)}.")
    return {"role": "add_flow", "words": f"add {flow_words(spec)}", "request": request,
            "undo": undo, "undo_words": "delete it (delete-strict)",
            "expect": {"present": spec}, "reinstall": reinstall}


def _plan_remove_flow(drv, dpid, change, table, recorded, own, ask, before, out):
    from modules.sdn import flow_intent
    from modules.sdn.match_rules import is_table_miss, normalise

    target = dict(change.get("target") or {})
    target["match"] = normalise(target.get("match") or {})
    found = _find(table, target)
    if found is None:
        raise Refused(f"no flow at {_target_said(target)} is in switch {dpid}'s table "
                      f"({len(table)} flows read): nothing to remove")
    cookie = found.get("cookie", 0)
    if is_table_miss(found):
        out["needs_typed"] = TABLE_MISS_WORDS
        out["warnings"].append(
            "This is the table-miss flow (priority 0, matching everything): removing it stops "
            f"the switch asking the controller about new traffic. Type {TABLE_MISS_WORDS!r} "
            "to confirm.")
    if cookie in own:
        out["warnings"].append(
            f"A flow of the controller's own (cookie {flow_intent.cookie_hex(cookie)}): a "
            "reactive application may install it again on the next matching packet.")
    owner = ("Mercury's" if cookie in recorded else
             "the controller's own" if cookie in own else "unauthorised")
    spec = {k: found.get(k) for k in ("table_id", "priority", "cookie", "match", "actions",
                                      "idle_timeout")}
    spec["hard_timeout"] = _remaining(found)
    spec["match"] = normalise(found.get("match") or {})
    request = _rendered(drv.render_delete_flow_strict(dpid, spec), "the delete")
    try:
        undo = _rendered(drv.render_add_flow(dpid, spec), "its undo")
    except Refused as exc:
        undo = None
        out["warnings"].append(f"It cannot be put back if the operation fails: {exc}.")
    table.remove(found)
    before.append(_snapshot(found))
    if cookie in recorded:
        out["intent_changes"].append({"kind": "withdrawn", "cookie": cookie})
    out["words"].append(f"Remove {owner} flow on {out['dpid_hex']} by delete-strict (its "
                        f"table, priority, match and cookie exactly): {flow_words(found)}.")
    return {"role": "remove_flow", "words": f"remove {owner} flow: {flow_words(found)}",
            "request": request, "undo": undo,
            "undo_words": "add it back as it was (its hard timeout's remainder)",
            "expect": {"absent": spec}, "owner": owner}


def _plan_edit_flow(drv, dpid, change, table, recorded, meter_ids, before, out):
    from modules.sdn import flow_intent
    from modules.sdn.match_rules import normalise

    target = dict(change.get("target") or {})
    target["match"] = normalise(target.get("match") or {})
    found = _find(table, target)
    if found is None:
        raise Refused(f"no flow at {_target_said(target)} is in switch {dpid}'s table "
                      f"({len(table)} flows read): nothing to edit")
    if found.get("cookie") not in recorded:
        raise Refused(f"edit is for Mercury's own recorded flows, and cookie "
                      f"{flow_intent.cookie_hex(found.get('cookie'))} is not one: remove it "
                      "instead")
    new = _spec(dpid, change.get("flow"))
    moved = [k for k in ("table_id", "priority") if getattr(new, k) != found.get(k, 0)]
    if flow_intent.normal_match(new.match) != flow_intent.normal_match(found.get("match")):
        moved.append("match")
    timeouts = [k for k in ("idle_timeout", "hard_timeout") if getattr(new, k) != found.get(k, 0)]
    for a in new.actions:
        if a.get("type") == "METER" and a.get("meter_id") not in meter_ids:
            raise Refused(f"the flow points at meter {a.get('meter_id')}, and switch {dpid} "
                          f"holds meters {sorted(meter_ids) or 'none'}")
    replace = moved or (timeouts and set(timeouts) & set(MODIFY_KEEPS))
    if not replace:
        if flow_intent.normal_actions(new.actions) == flow_intent.normal_actions(
                found.get("actions")):
            raise Refused("the edit changes nothing: the actions and timeouts are the flow's")
        spec = dict(new.as_dict(), cookie=found.get("cookie"),
                    idle_timeout=found.get("idle_timeout", 0),
                    hard_timeout=found.get("hard_timeout", 0))
        old = {k: found.get(k) for k in ("table_id", "priority", "cookie", "match", "actions",
                                        "idle_timeout", "hard_timeout")}
        old["match"] = normalise(found.get("match") or {})
        request = _rendered(drv.render_modify_flow_strict(dpid, spec), "the modify")
        undo = _rendered(drv.render_modify_flow_strict(dpid, old), "its undo")
        before.append(_snapshot(found))
        found.update(actions=spec["actions"])
        out["intent_changes"].append({"kind": "amended", "cookie": found.get("cookie"),
                                      "changes": {"actions": spec["actions"]}})
        out["words"].append(f"Change the actions of Mercury's flow on {out['dpid_hex']} in "
                            f"place (modify-strict; its match, priority, cookie and timeouts "
                            f"unchanged): {flow_intent.action_words(found.get('actions'))} "
                            f"becomes {flow_intent.action_words(spec['actions'])}.")
        return [{"role": "edit_flow", "words": f"modify {flow_words(spec)}", "request": request,
                 "undo": undo, "undo_words": "modify it back to its old actions",
                 "expect": {"present": spec}}]
    why = (f"a change of its {' and '.join(moved)}" if moved else
           f"a change of its {' and '.join(timeouts)} (OpenFlow 1.3 keeps a flow's timeouts on "
           "a modify)")
    out["words"].append(f"{why[0].upper()}{why[1:]} is a remove and an add as one action: "
                        "delete-strict of the old flow, then an add of the new one; rollback "
                        "restores the old flow.")
    if new.cookie == found.get("cookie") or not flow_intent.is_mercury(new.cookie):
        raise Refused("the replacing flow carries a fresh Mercury cookie, not "
                      f"{flow_intent.cookie_hex(new.cookie)}: preview again")
    remove = _plan_remove_flow(drv, dpid, {"target": _identity(found)}, table, recorded,
                               set(), {}, before, out)
    add = _plan_add_flow(drv, dpid, {"flow": new.as_dict()}, table, recorded, meter_ids,
                         False, {}, out)
    return [remove, add]


def _plan_add_meter(drv, dpid, change, meter_ids, features, table, out):
    from modules.sdn.drivers.base import SpecError, meter_from_spec

    spec = dict(change.get("meter") or {})
    try:
        meter = meter_from_spec(dpid, spec)
    except SpecError as exc:
        raise Refused(str(exc)) from None
    if meter.meter_id in meter_ids:
        raise Refused(f"meter {meter.meter_id} is already on switch {dpid}: preview again for "
                      "a free id")
    pointing = [f for f in table if any(a.get("type") == "METER"
                                        and a.get("meter_id") == meter.meter_id
                                        for a in f.get("actions") or [])]
    if pointing:
        raise Refused(f"a flow already points at meter {meter.meter_id} on switch {dpid} "
                      f"({flow_words(pointing[0])}): a new meter there would limit it too; "
                      "preview again for a free id")
    if not features:
        raise Refused(f"switch {dpid} reports no meter features, so it offers no meters")
    if features.get("max_meter") and meter.meter_id > features["max_meter"]:
        raise Refused(f"meter id {meter.meter_id} is above the switch's max_meter "
                      f"{features['max_meter']}")
    if len(meter.bands) > (features.get("max_bands") or 0):
        raise Refused(f"the meter has {len(meter.bands)} bands and the switch allows "
                      f"{features.get('max_bands') or 0} (max_bands)")
    kinds = {str(t).upper() for t in features.get("band_types") or []}
    caps = {str(c).upper() for c in features.get("capabilities") or []}
    for band in meter.bands:
        if band["type"] not in kinds:
            raise Refused(f"the switch's meter bands are {sorted(kinds) or 'none'}, not "
                          f"{band['type']}")
    for flag in meter.flags:
        if flag not in caps:
            raise Refused(f"the switch's meter capabilities are {sorted(caps) or 'none'}, "
                          f"not {flag}")
    if any(b.get("burst_size") for b in meter.bands) and "BURST" not in meter.flags:
        raise Refused("a band with a burst needs the meter's BURST flag")
    body = meter.as_dict()
    request = _rendered(drv.render_add_meter(dpid, body), "the meter")
    undo = _rendered(drv.render_delete_meter(dpid, {"meter_id": meter.meter_id}), "its undo")
    meter_ids[meter.meter_id] = body
    band = meter.bands[0]
    unit = "kbit/s" if "KBPS" in meter.flags else "packets/s"
    out["intent_changes"].append({"kind": "meter", "meter": body})
    out["words"].append(f"Add meter {meter.meter_id} on {out['dpid_hex']}: {band['type'].lower()} "
                        f"above {band['rate']} {unit}"
                        + (f", burst {band.get('burst_size')}" if band.get("burst_size") else
                           "") + ".")
    return {"role": "add_meter", "words": f"add meter {meter.meter_id}", "request": request,
            "undo": undo, "undo_words": "delete the meter", "expect": {"meter": body}}


def _plan_remove_meter(drv, dpid, change, meter_ids, table, changes, out):
    meter_id = change.get("meter_id")
    held = meter_ids.get(meter_id)
    if held is None:
        raise Refused(f"switch {dpid} holds meters {sorted(meter_ids) or 'none'}, not "
                      f"{meter_id!r}")
    users = [f for f in table if any(a.get("type") == "METER" and a.get("meter_id") == meter_id
                                     for a in f.get("actions") or [])]
    if users:
        raise Refused(f"{len(users)} flow(s) still point at meter {meter_id} "
                      f"({flow_words(users[0])}): remove them first")
    body = {"meter_id": meter_id, "flags": list(held.get("flags") or []),
            "bands": [{k: b.get(k) for k in ("type", "rate", "burst_size")
                       if b.get(k) is not None} for b in held.get("bands") or []]}
    request = _rendered(drv.render_delete_meter(dpid, {"meter_id": meter_id}), "the delete")
    try:
        undo = _rendered(drv.render_add_meter(dpid, body), "its undo")
    except Refused:
        undo = None
    del meter_ids[meter_id]
    out["intent_changes"].append({"kind": "meter_withdrawn", "meter_id": meter_id})
    out["words"].append(f"Remove meter {meter_id} on {out['dpid_hex']}.")
    return {"role": "remove_meter", "words": f"remove meter {meter_id}", "request": request,
            "undo": undo, "undo_words": "add the meter back", "expect": {"no_meter": meter_id}}


def _checks(steps: list) -> list:
    out = []
    for s in steps:
        e = s["expect"]
        if "present" in e:
            out.append(f"the flow read back from the table: cookie, match, priority, actions "
                       f"and hard timeout as sent ({s['words']})")
        elif "absent" in e:
            out.append("the flow read back gone from the table")
        elif "meter" in e:
            out.append(f"meter {e['meter']['meter_id']} read back with its band, and its band's "
                       "counters read twice (the drop count rising while the flow matches)")
        elif "no_meter" in e:
            out.append(f"meter {e['no_meter']} read back gone")
    out.append(VERIFY_LIMIT)
    return out


# ───────────────────────────────────────────────────────────────────────────── verify

def _present(flows: list, spec: dict) -> str:
    """Why *spec* is not in *flows* as sent, or ""."""
    from modules.sdn.flow_intent import cookie_hex, differences

    hit = _find(flows, {"table_id": spec.get("table_id", 0), "priority": spec.get("priority"),
                        "match": spec.get("match"), "cookie": spec.get("cookie")})
    if hit is None:
        return (f"no flow with cookie {cookie_hex(spec.get('cookie'))} at "
                f"{_target_said(spec)} in the table read back")
    record = dict(spec, dpid=hit.get("dpid"))
    diff = [d["words"] for d in differences(record, hit)]
    if spec.get("hard_timeout", 0) != hit.get("hard_timeout", 0):
        diff.append(f"hard timeout {hit.get('hard_timeout', 0)} s, sent "
                    f"{spec.get('hard_timeout', 0)} s")
    return "; ".join(diff)


def verify_installed(drv, dpid: int, steps: list, *, sleep=time.sleep,
                     reads: int = VERIFY_READS, pause: float = VERIFY_PAUSE) -> dict:
    """The gating check: each step's expectation against the table (and meters) read back, up
    to *reads* times *pause* apart until all hold. ``{"ok", "checks", "reads", "flows",
    "meters", "flows_read", "meters_read"}``, *flows_read* and *meters_read* whether the last
    read of each answered (*flows* and *meters* are that read's); a read that fails is itself a
    failed check, never a pass."""
    meters_needed = any("meter" in s["expect"] or "no_meter" in s["expect"] for s in steps)
    checks, flows, meter_rows = [], [], []
    flows_read = meters_read = False
    for attempt in range(1, reads + 1):
        checks = []
        got = drv.flows(dpid)
        flows_read = meters_read = False
        if not got.get("ok"):
            checks = [{"name": "table read back", "state": "fail",
                       "words": f"the table could not be read back: {got.get('error')}"}]
        else:
            flows = got.get("flows") or []
            flows_read = True
            meter_rows = []
            if meters_needed:
                m = drv.meters(dpid)
                if not m.get("ok"):
                    checks.append({"name": "meters read back", "state": "fail",
                                   "words": f"the meters could not be read back: "
                                            f"{m.get('error')}"})
                meter_rows = m.get("meters") or []
                meters_read = bool(m.get("ok"))
            by_id = {m.get("meter_id"): m for m in meter_rows}
            for s in steps:
                e = s["expect"]
                if "present" in e:
                    why = _present(flows, e["present"])
                    checks.append({"name": "installed", "state": "fail" if why else "pass",
                                   "words": why or f"in the table as sent: {s['words']}"})
                elif "absent" in e:
                    hit = _find(flows, {k: e["absent"][k] for k in
                                        ("table_id", "priority", "match", "cookie")})
                    checks.append({"name": "removed", "state": "fail" if hit else "pass",
                                   "words": (f"still in the table: {flow_words(hit)}" if hit
                                             else f"gone from the table: {s['words']}")})
                elif "meter" in e:
                    want = e["meter"]
                    held = by_id.get(want["meter_id"])
                    why = ""
                    if held is None:
                        why = (f"meter {want['meter_id']} is not on the switch (it holds "
                               f"{sorted(by_id) or 'none'})")
                    else:
                        have = [(b.get("type"), b.get("rate"), b.get("burst_size", 0))
                                for b in held.get("bands") or []]
                        sent = [(b.get("type"), b.get("rate"), b.get("burst_size", 0))
                                for b in want.get("bands") or []]
                        if have != sent:
                            why = f"meter {want['meter_id']}'s bands are {have}, sent {sent}"
                    checks.append({"name": "meter installed", "state": "fail" if why else "pass",
                                   "words": why or f"meter {want['meter_id']} on the switch "
                                                   "with its band as sent"})
                elif "no_meter" in e:
                    gone = e["no_meter"] not in by_id
                    checks.append({"name": "meter removed", "state": "pass" if gone else "fail",
                                   "words": f"meter {e['no_meter']} "
                                            + ("gone" if gone else "still on the switch")})
        if checks and all(c["state"] == "pass" for c in checks):
            return {"ok": True, "checks": checks, "reads": attempt, "flows": flows,
                    "meters": meter_rows, "flows_read": flows_read, "meters_read": meters_read}
        if attempt < reads:
            sleep(pause)
    return {"ok": False, "checks": checks, "reads": reads, "flows": flows, "meters": meter_rows,
            "flows_read": flows_read, "meters_read": meters_read}


def read_back(steps: list, verified: dict) -> list:
    """What Verify's last read (*verified*, `verify_installed`'s answer) found for each step,
    the switch's own entries, never the request sent: an added or edited flow as the table
    holds it (``flow``: its table, priority, match, actions, idle and hard timeouts and
    cookie; None when it was not there), with ``reinstall`` for Mercury's flow put back; a
    removed flow (``removed``, as named) and whether it is ``gone``; a meter as the switch
    holds it (``meter``: its id, flags and bands; None when it was not there). ``read`` is
    False where that table or the meters could not be read, and nothing is said of it then."""
    flows = verified.get("flows") or []
    meters = {m.get("meter_id"): m for m in verified.get("meters") or []}
    flows_read, meters_read = bool(verified.get("flows_read")), bool(verified.get("meters_read"))
    keep = ("table_id", "priority", "match", "actions", "idle_timeout", "hard_timeout", "cookie")
    out = []
    for s in steps:
        e = s["expect"]
        if "present" in e:
            spec = e["present"]
            hit = _find(flows, {k: spec.get(k) for k in ("table_id", "priority", "match",
                                                          "cookie")}) if flows_read else None
            out.append({"role": s["role"], "reinstall": bool(s.get("reinstall")),
                        "read": flows_read, "cookie": spec.get("cookie"),
                        "flow": {k: hit.get(k) for k in keep} if hit else None})
        elif "absent" in e:
            named = {k: e["absent"].get(k) for k in ("table_id", "priority", "match", "cookie")}
            hit = _find(flows, named) if flows_read else None
            out.append({"role": s["role"], "read": flows_read, "removed": named,
                        "gone": flows_read and hit is None})
        elif "meter" in e:
            mid = e["meter"]["meter_id"]
            held = meters.get(mid) if meters_read else None
            out.append({"role": s["role"], "read": meters_read, "meter_id": mid,
                        "meter": {k: held.get(k) for k in ("meter_id", "flags", "bands")}
                        if held else None})
        elif "no_meter" in e:
            out.append({"role": s["role"], "read": meters_read, "meter_id": e["no_meter"],
                        "gone": meters_read and e["no_meter"] not in meters})
    return out


def counters(drv, dpid: int, steps: list, *, sleep=time.sleep,
             interval: float = COUNTER_INTERVAL) -> list:
    """The reported counters: each meter's band and the flows pointing at it, and each drop
    flow, read twice *interval* seconds apart. ``[{"name", "state": "reported", "words",
    ...}]``; never gating (traffic may simply not be flowing)."""
    meter_ids = [s["expect"]["meter"]["meter_id"] for s in steps if "meter" in s["expect"]]
    drops = [s["expect"]["present"] for s in steps if "present" in s["expect"]
             and not s["expect"]["present"].get("actions")]
    if not meter_ids and not drops:
        return []

    def sample():
        f = drv.flows(dpid)
        m = drv.meters(dpid) if meter_ids else {"ok": True, "meters": []}
        return f, m

    f1, m1 = sample()
    sleep(interval)
    f2, m2 = sample()
    out = []
    if not (f1.get("ok") and f2.get("ok") and m1.get("ok") and m2.get("ok")):
        return [{"name": "counters", "state": "reported",
                 "words": "the counters could not be read twice, so nothing is said of them"}]

    def flow_packets(read, spec):
        hit = _find(read.get("flows") or [], {k: spec.get(k) for k in
                                              ("table_id", "priority", "match", "cookie")})
        return None if hit is None else hit.get("packet_count")

    def band(read, meter_id):
        m = next((x for x in read.get("meters") or [] if x.get("meter_id") == meter_id), None)
        if not m or not m.get("bands"):
            return None, None
        return m["bands"][0].get("packet_band_count"), m.get("packet_in_count")

    for meter_id in meter_ids:
        (d1, in1), (d2, in2) = band(m1, meter_id), band(m2, meter_id)
        if None in (d1, d2, in1, in2):
            out.append({"name": "meter counters", "state": "reported",
                        "words": f"meter {meter_id}'s counters were not reported"})
            continue
        dropped, seen = d2 - d1, in2 - in1
        if seen <= 0:
            words = (f"no packet reached meter {meter_id} in {interval:g} s: the limit is "
                     "installed and not exercised now")
        elif dropped > 0:
            words = (f"limiting: meter {meter_id} dropped {dropped} of {seen} packets in "
                     f"{interval:g} s (its band's drop count rose from {d1} to {d2})")
        else:
            words = (f"meter {meter_id} passed all {seen} packets in {interval:g} s: the traffic "
                     "is under the limit now")
        out.append({"name": "meter counters", "state": "reported", "words": words,
                    "dropped": dropped, "seen": seen, "interval_s": interval,
                    "band_drops": [d1, d2]})
    for spec in drops:
        p1, p2 = flow_packets(f1, spec), flow_packets(f2, spec)
        if p1 is None or p2 is None:
            continue
        out.append({"name": "drop counters", "state": "reported",
                    "words": f"the drop flow matched {p2 - p1} packets in {interval:g} s "
                             f"({p2} since it was installed)",
                    "matched": p2 - p1, "total": p2, "interval_s": interval})
    return out


# ───────────────────────────────────────────────────────────────────────────── the apply

def hold_name(connection: str, dpid: int) -> str:
    """The name a switch is held by (`device_ops.hold`): one operation per switch, across
    processes."""
    from modules.sdn.drivers.base import dpid_hex

    return f"sdn-{connection}-{dpid_hex(dpid)}"


def _send(drv, steps: list) -> tuple:
    """Each request in order, stopping at the first that fails: ``(sent, failed)``, *sent* the
    steps that landed with their answers."""
    sent = []
    for s in steps:
        got = drv.apply(dict(s["request"], ok=True))
        row = {"role": s["role"], "request": s["request"], "answer": {
            k: got.get(k) for k in ("ok", "status", "error", "note") if k in got}}
        if not got.get("ok"):
            return sent, row
        sent.append(dict(row, step=s))
    return sent, None


def _rollback(drv, dpid: int, sent: list, *, sleep=time.sleep) -> dict:
    """The undo of each step that landed, newest first, then the table read back: what came
    back and what did not, per step."""
    out = {"ran": bool(sent), "steps": [], "ok": True}
    undone = []
    for row in reversed(sent):
        step = row["step"]
        if step.get("undo") is None:
            out["ok"] = False
            out["steps"].append({"role": step["role"], "state": "not undone",
                                 "words": "it has no undo"})
            continue
        got = drv.apply(dict(step["undo"], ok=True))
        out["steps"].append({"role": step["role"], "request": step["undo"],
                             "state": "sent" if got.get("ok") else "failed",
                             "words": step.get("undo_words", ""),
                             "error": got.get("error", "")})
        if got.get("ok"):
            undone.append(_inverse(step))
        else:
            out["ok"] = False
    if undone:
        back = verify_installed(drv, dpid, undone, sleep=sleep)
        out["read_back"] = back["checks"]
        out["ok"] = out["ok"] and back["ok"]
    return out


def _inverse(step: dict) -> dict:
    """What a step's undo should leave: an added flow absent, a removed one present, an added
    meter gone, a removed meter back, an edited flow as it was."""
    e = step["expect"]
    if "present" in e and step["role"] == "add_flow":
        return {"expect": {"absent": e["present"]}, "words": step["words"], "role": "undo"}
    if "absent" in e:
        return {"expect": {"present": e["absent"]}, "words": step["words"], "role": "undo"}
    if "meter" in e:
        return {"expect": {"no_meter": e["meter"]["meter_id"]}, "words": step["words"],
                "role": "undo"}
    if "no_meter" in e:
        return {"expect": {}, "words": step["words"], "role": "undo"}
    if step["role"] == "edit_flow":
        body = json.loads(step["undo"]["body"])
        body.pop("dpid", None)
        return {"expect": {"present": body}, "words": step["words"], "role": "undo"}
    return {"expect": {}, "words": step["words"], "role": "undo"}


def apply(network: str, ask: dict, confirmed_hash: str, *, actor: str, actor_verified: str = "",
          typed: str = "", mode: str = "hitl", autonomous: dict = None, response: dict = None,
          driver=None, sleep=time.sleep, now=time.time, counter_interval: float = None) -> dict:
    """Apply the previewed operation *ask* as *actor*, bound to *confirmed_hash*. See the
    module's docstring. ``{"ok", "error", "at", "outcome", "id", "hash", "plan", "sent",
    "verify", "counters", "rollback", "record"}``; ``at`` the stage reached (plan, hash, hold,
    send, verify, rollback, record) and ``outcome`` one of ``refused``, ``verified``,
    ``rolled_back``, ``rollback_failed``."""
    from modules.nsot import device_ops

    op_id = f"sdnop-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(now()))}-{secrets.token_hex(4)}"
    out = {"ok": False, "error": "", "at": "plan", "outcome": "refused", "id": op_id,
           "hash": "", "plan": None, "sent": [], "verify": {"checks": []}, "counters": [],
           "rollback": {"ran": False}, "record": {"ok": False, "error": ""},
           "mode": mode, "actor": actor}
    if not actor:
        out["error"] = "an operation is applied by someone, and no actor was given"
        return out
    if mode not in ("hitl", "auto"):
        out["error"] = f"the mode is hitl or auto, not {mode!r}"
        return out
    if mode == "auto" and not (autonomous or {}).get("reason"):
        out["error"] = "an autonomous operation names the AUTO setting and its reason"
        return out
    p = plan(network, ask, driver=driver)
    out["plan"] = p
    if not p["ok"]:
        out["error"] = p["error"]
        return out
    out["at"], out["hash"] = "hash", p["hash"]
    if p["hash"] != confirmed_hash:
        out["error"] = (f"the preview's hash was {str(confirmed_hash)[:12] or 'none'}, and the "
                        f"plan made now is {p['hash'][:12]}: the switch's table or the "
                        "requests moved since the preview, so nothing was sent; preview again")
        return out
    if p["needs_typed"] and (typed or "").strip() != p["needs_typed"]:
        out["error"] = (f"removing the table-miss flow needs {p['needs_typed']!r} typed, and "
                        f"{(typed or '').strip()!r} was: nothing was sent")
        return out
    made = _driver(network, p["connection"], driver)
    if not made.get("ok"):
        out["error"] = made.get("error") or "no driver"
        return out
    drv = made["driver"]
    out["at"] = "hold"
    started = now()
    try:
        with device_ops.hold(network, hold_name(p["connection"], p["dpid"]), "sdn flows",
                             actor, detail=f"{len(p['steps'])} request(s) to "
                                           f"{p['connection']}"):
            out["at"] = "send"
            sent, failed = _send(drv, p["steps"])
            out["sent"] = [{k: v for k, v in r.items() if k != "step"} for r in sent]
            if failed is not None:
                out["sent"].append(failed)
                out["error"] = (f"the controller refused request {len(sent) + 1} of "
                                f"{len(p['steps'])} ({failed['role']}): "
                                f"{failed['answer'].get('error')}")
                out["at"] = "rollback"
                out["rollback"] = _rollback(drv, p["dpid"], sent, sleep=sleep)
                out["outcome"] = "rolled_back" if out["rollback"]["ok"] else "rollback_failed"
            else:
                out["at"] = "verify"
                v = verify_installed(drv, p["dpid"], p["steps"], sleep=sleep)
                out["verify"] = {"ok": v["ok"], "checks": v["checks"], "reads": v["reads"],
                                 "read_back": read_back(p["steps"], v)}
                if v["ok"]:
                    out["counters"] = counters(
                        drv, p["dpid"], p["steps"], sleep=sleep,
                        interval=COUNTER_INTERVAL if counter_interval is None
                        else counter_interval)
                    out["outcome"], out["ok"] = "verified", True
                else:
                    failed_checks = [c["words"] for c in v["checks"] if c["state"] == "fail"]
                    out["error"] = "Verify failed: " + "; ".join(failed_checks)
                    out["at"] = "rollback"
                    out["rollback"] = _rollback(drv, p["dpid"], sent, sleep=sleep)
                    out["outcome"] = ("rolled_back" if out["rollback"]["ok"]
                                      else "rollback_failed")
    except device_ops.DeviceBusy as exc:
        out["error"] = f"refused: {exc}"
        out["at"] = "hold"
        return out
    out["verify"].setdefault("checks", [])
    out["verify"]["checks"] = list(out["verify"]["checks"]) + [
        {"name": "unaffected host pairs still pass", "state": "operator",
         "words": VERIFY_LIMIT}]
    out["at"] = "record"
    out["record"] = _record(network, p, out, actor=actor, actor_verified=actor_verified,
                            mode=mode, autonomous=autonomous, response=response,
                            started=started, ended=now())
    if not out["record"]["ok"]:
        out["error"] = ((out["error"] + "; ") if out["error"] else "") + \
            f"the record could not be kept: {out['record']['error']}"
    return out


def _record(network, p, out, *, actor, actor_verified, mode, autonomous, response, started,
            ended) -> dict:
    """The flow intent's rows for what the operation left, then the operation's own row."""
    from modules.sdn import flow_intent

    errors = []
    who = {"actor": actor, "actor_verified": actor_verified}
    kept = out["outcome"] == "verified"
    response = dict(response or {}, operation=out["id"])
    hard = None
    if kept:
        for change in p["intent_changes"]:
            try:
                if change["kind"] == "installed":
                    flow_intent.record_installed(network, connection=p["connection"],
                                                 flow=dict(change["flow"], dpid=p["dpid"]),
                                                 response=response, at=ended, **who)
                    hard = max(hard or 0, change["flow"].get("hard_timeout") or 0)
                elif change["kind"] == "withdrawn":
                    flow_intent.record_withdrawn(network, change["cookie"],
                                                 connection=p["connection"],
                                                 why=f"removed by operation {out['id']}",
                                                 at=ended, **who)
                elif change["kind"] == "amended":
                    flow_intent.record_amended(network, change["cookie"],
                                               connection=p["connection"],
                                               why=f"edited by operation {out['id']}",
                                               changes=change["changes"], at=ended, **who)
            except flow_intent.IntentRefused as exc:
                errors.append(str(exc))
        for change in p["intent_changes"]:
            try:
                if change["kind"] == "meter":
                    flow_intent.record_meter(network, connection=p["connection"],
                                             dpid=p["dpid"], meter=change["meter"],
                                             response=response, at=ended,
                                             expires_at=(ended + hard) if hard else None, **who)
                elif change["kind"] == "meter_withdrawn":
                    flow_intent.record_meter_withdrawn(
                        network, connection=p["connection"], dpid=p["dpid"],
                        meter_id=change["meter_id"], why=f"removed by operation {out['id']}",
                        at=ended, **who)
            except flow_intent.IntentRefused as exc:
                # A meter not Mercury's (removed by a person's edit) has no record to close.
                if change["kind"] != "meter_withdrawn":
                    errors.append(str(exc))
    row = {"id": out["id"], "at": _iso(ended), "started": _iso(started), "ended": _iso(ended),
           "connection": p["connection"], "dpid": p["dpid"], "dpid_hex": p["dpid_hex"],
           "hash": p["hash"], "words": p["words"], "warnings": p["warnings"],
           "requests": [s["request"] for s in p["steps"]],
           "sent": out["sent"], "verify": out["verify"], "counters": out["counters"],
           "rollback": out["rollback"], "outcome": out["outcome"], "error": out["error"],
           "mode": mode, "autonomous": dict(autonomous or {}), "response": response, **who}
    try:
        flow_intent.record_operation(network, row)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        errors.append(f"{type(exc).__name__}: {exc}")
    return {"ok": not errors, "error": "; ".join(errors)}


# ───────────────────────────────────────────────────────────────────────────── meters' expiry

def expire_meters(network: str, *, driver=None, now=time.time, actor: str = "Mercury") -> dict:
    """Remove each of Mercury's recorded meters past its expiry that no flow points at any
    more (its response's flows expired at their hard timeouts): the same operation core,
    recorded as Mercury's own cleanup. ``{"ok", "removed", "kept", "errors"}``."""
    from modules.sdn import flow_intent

    out = {"ok": True, "removed": [], "kept": [], "errors": []}
    got = flow_intent.meters(network)
    if got["state"] != "ok":
        return {"ok": False, "removed": [], "kept": [], "errors": [got["error"]]}
    for m in got["meters"]:
        if not m.get("expires_at") or now() < m["expires_at"]:
            continue
        ask = {"connection": m["connection"], "dpid": m["dpid"],
               "changes": [{"do": "remove_meter", "meter_id": m["meter_id"]}]}
        p = plan(network, ask, driver=driver)
        if not p["ok"]:
            if "holds meters" in p["error"]:
                # Gone already: the record is closed, nothing is sent.
                try:
                    flow_intent.record_meter_withdrawn(
                        network, connection=m["connection"], dpid=m["dpid"],
                        meter_id=m["meter_id"], actor=actor, actor_verified="system",
                        why="expired: no longer on the switch")
                    out["removed"].append(m["meter_id"])
                except flow_intent.IntentRefused as exc:
                    out["errors"].append(str(exc))
                continue
            out["kept"].append({"meter_id": m["meter_id"], "why": p["error"]})
            continue
        done = apply(network, ask, p["hash"], actor=actor, actor_verified="system",
                     response={"kind": "expiry", "meter_id": m["meter_id"]}, driver=driver,
                     counter_interval=0)
        (out["removed"] if done["ok"] else out["errors"]).append(
            m["meter_id"] if done["ok"] else done["error"])
    out["ok"] = not out["errors"]
    return out
