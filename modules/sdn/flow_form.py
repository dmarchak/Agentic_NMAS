"""SDN › Flows' editor: a person's Add, Edit and Remove read from the form into the
flow-operation core's ask (`flow_ops`; PHASE8_PLAN 17.1 S16, C1912). Deterministic.

The form carries text a person types:
- **match**: ``field=value`` pairs, one per line or comma-separated, OpenFlow 1.3's OXM names
  (``in_port=1, eth_type=0x0800, ipv4_src=192.0.2.1``); an IPv6 field takes an IPv6 address
  (``ipv6_src=2001:db8::1``);
- **actions**: comma-separated, ``drop`` (alone: no actions), ``output:<port or CONTROLLER,
  NORMAL, FLOOD, ALL, IN_PORT, LOCAL>``, ``meter:<id>``, ``group:<id>``, ``goto_table:<id>``,
  ``set_field:<field>=<value>``;
- table, priority and the idle and hard timeouts as whole numbers.
A Remove carries the flow it names (its table, priority, match and cookie, drawn by the page
from the read). Mercury draws the cookie of a flow it adds when the preview is made; the confirm
carries the preview's ask back unchanged.
"""

import json

from modules.sdn.drivers.base import RESERVED_PORTS


class FormRefused(ValueError):
    """The form's text refused, naming the field and what it holds."""


def _number(name: str, text, low: int, high: int) -> int:
    text = str(text if text is not None else "").strip()
    try:
        value = int(text, 0) if text else None
    except ValueError:
        value = None
    if value is None or not low <= value <= high:
        raise FormRefused(f"{name} is a whole number from {low} to {high}, not {text!r}")
    return value


def parse_match(text: str) -> dict:
    """``field=value`` pairs as a match (values left as typed text; `match_rules.normalise`
    reads the numbers)."""
    from modules.sdn.drivers.base import OXM_FIELDS

    out = {}
    parts = [p.strip() for line in (text or "").splitlines() for p in line.split(",")]
    for part in [p for p in parts if p]:
        field, eq, value = part.partition("=")
        field, value = field.strip(), value.strip()
        if not eq or not field or not value:
            raise FormRefused(f"a match is field=value pairs, and {part!r} is not one")
        if field not in OXM_FIELDS:
            raise FormRefused(f"{field!r} is not an OpenFlow 1.3 match field (OXM name)")
        if field in out:
            raise FormRefused(f"{field} is matched twice")
        out[field] = value
    return out


def parse_actions(text: str) -> list:
    """The comma-separated actions as the drivers' shape; ``drop`` (or nothing) is none."""
    from modules.sdn.drivers.base import OXM_FIELDS

    tokens = [t.strip() for t in (text or "").split(",") if t.strip()]
    if not tokens or [t.lower() for t in tokens] == ["drop"]:
        return []
    out = []
    for t in tokens:
        kind, _colon, arg = t.partition(":")
        kind, arg = kind.strip().lower(), arg.strip()
        if kind == "drop":
            raise FormRefused("drop is the only action when it is given (a drop is no action)")
        if kind == "output":
            port = arg.upper() if arg.upper() in RESERVED_PORTS else _number("output's port",
                                                                             arg, 1, 0xFFFFFF00)
            out.append({"type": "OUTPUT", "port": port})
        elif kind in ("meter", "group", "goto_table"):
            key = {"meter": "meter_id", "group": "group_id", "goto_table": "table_id"}[kind]
            top = 0xFE if kind == "goto_table" else 0xFFFF0000
            out.append({"type": kind.upper(), key: _number(f"{kind}'s id", arg, 0 if
                                                            kind == "goto_table" else 1, top)})
        elif kind == "set_field":
            field, eq, value = arg.partition("=")
            if not eq or field.strip() not in OXM_FIELDS or not value.strip():
                raise FormRefused(f"set_field is set_field:<OXM field>=<value>, not {t!r}")
            value = value.strip()
            out.append({"type": "SET_FIELD", "field": field.strip(),
                        "value": int(value, 0) if value.isdigit() else value})
        else:
            raise FormRefused(f"{t!r} is not an action this editor sends (drop, output, meter, "
                              "group, goto_table, set_field)")
    return out


def flow_from_form(values, cookie: int) -> dict:
    """The flow the form describes, with *cookie*."""
    return {"table_id": _number("Table", values.get("table_id", "0"), 0, 0xFE),
            "priority": _number("Priority", values.get("priority", ""), 0, 0xFFFF),
            "idle_timeout": _number("Idle timeout", values.get("idle_timeout", "0"), 0, 0xFFFF),
            "hard_timeout": _number("Hard timeout", values.get("hard_timeout", "0"), 0, 0xFFFF),
            "match": parse_match(values.get("match", "")),
            "actions": parse_actions(values.get("actions", "")), "cookie": cookie}


def target_of(values) -> dict:
    """The installed flow a Remove or an Edit names, as the page drew it (JSON)."""
    try:
        got = json.loads(values.get("target") or "")
    except ValueError:
        raise FormRefused("the form names no flow (its target)") from None
    if not isinstance(got, dict) or not {"priority", "match", "cookie"} <= set(got):
        raise FormRefused("the form's target names a flow's table, priority, match and cookie")
    return {k: got.get(k, 0 if k == "table_id" else None)
            for k in ("table_id", "priority", "match", "cookie")}


def ask_from_form(values) -> dict:
    """The ask for `flow_ops.plan` from the editor's form: ``do`` is add, edit or remove."""
    from modules.sdn import flow_intent

    do = (values.get("do") or "").strip()
    conn = (values.get("connection") or "").strip()
    dpid = (values.get("dpid") or "").strip()
    if not conn or not dpid:
        raise FormRefused("the form names no controller connection or switch")
    if do == "add":
        change = {"do": "add_flow", "flow": flow_from_form(values, flow_intent.new_cookie())}
    elif do == "edit":
        change = {"do": "edit_flow", "target": target_of(values),
                  "flow": flow_from_form(values, flow_intent.new_cookie())}
    elif do == "remove":
        change = {"do": "remove_flow", "target": target_of(values)}
    else:
        raise FormRefused(f"the form's change is add, edit or remove, not {do!r}")
    return {"connection": conn, "dpid": dpid, "changes": [change]}
