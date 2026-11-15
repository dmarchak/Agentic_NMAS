"""NetBox's prefix read for the DHCP reservation plan's subnet lookup (`plan_engine.
netbox_prefix_found`, B1): plan code's own read, its answer drawn among the plan's checks in
its preview, before anyone approves.

**Outside the AI's read loop** (the operator, 2026-11-14: "NetBox reads have no person-facing
home (C3719), so the AI's read loop must not reach them. Keep netbox_reads.py for the DHCP
plan's subnet lookup only (plan code, shown in the preview), outside the AI's read loop"): this
module declares no read family, imports nothing of the read loop, and no module of the read
loop imports it (tests/test_ai_read_loop_never_reaches_netbox.py).

**Reads only.** The one kind (`KINDS`) is one NetBox list endpoint asked by GET, through
netbox_client's own session (`netbox_client._nb_ready`: its URL, token and TLS setting), one
page of at most `PAGE` rows: never a POST, PATCH, PUT or DELETE (tests/test_ai_netbox_reads.py
scans this file's syntax tree for one). A read is bounded: one page, and a count beyond it is
said (``truncated``, "20 shown of 57"), never quietly dropped.

**A fixed field list** (`_prefix_row`): the prefix, its status, VRF, role, VLAN id, site and
description. Never a custom field, a comment, a config context or a local context, never a
token or anything secret NetBox holds; every known person's display name in a row's free text
is their stable label (`_unnamed`). **The residual:** a third party's name typed into a
description, a person Mercury holds no display name for, is not recognisable as a name and is
drawn as typed.

**An absence is a fact** (`said`): "no NetBox prefix contains 192.0.2.50", never an empty list
to interpret. An unconfigured NetBox, or one that does not answer, is said as that, never as
nothing found. An argument is one token of its shape (an address, a prefix), checked before
anything is asked.
"""
import ipaddress
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

#: The rows one read asks NetBox for (its ``limit``): one page; a count past it is said.
PAGE = 20
#: The bound on one GET, seconds: netbox_client's own (`_nb_get`, 15 s), so a read here waits
#: no longer than Mercury's other NetBox reads do.
TIMEOUT_S = 15


def _name(obj) -> str:
    if not isinstance(obj, dict):
        return str(obj or "") if isinstance(obj, (str, int)) else ""
    return str(obj.get("name") or obj.get("display") or obj.get("model") or "")


def _value(obj) -> str:
    if isinstance(obj, dict):
        return str(obj.get("value") or obj.get("label") or "")
    return str(obj or "") if isinstance(obj, (str, int)) else ""


def _text(value, most: int = 200) -> str:
    return str(value or "")[:most] if isinstance(value, (str, int, float)) else ""


def _unnamed(rows: list) -> list:
    """*rows* with no known person named in their free text: each display name Mercury holds
    (`display_names.known`) replaced by that person's stable label wherever it stands as a
    word, and each email-shaped identity labelled (`display_names.unnamed`). The residual: a
    third party's name typed into a description (someone Mercury holds no display name for)
    is not recognisable as a name, and is drawn as typed."""
    from modules import display_names

    people = display_names.known()

    def clean(value):
        if isinstance(value, str):
            return display_names.unnamed(value, people)
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        return value
    return [clean(r) for r in rows]


def _prefix_row(p: dict) -> dict:
    vlan = p.get("vlan") or {}
    return {"prefix": _text(p.get("prefix"), 64), "status": _value(p.get("status")),
            "vrf": _name(p.get("vrf")), "role": _name(p.get("role")),
            "vlan": vlan.get("vid") if isinstance(vlan, dict) else None,
            "site": _name(p.get("scope") or p.get("site")),
            "description": _text(p.get("description"))}


def _address(value) -> str:
    """Why *value* is not one IPv4 or IPv6 address, or ``""``."""
    try:
        ipaddress.ip_address(str(value))
    except ValueError:
        return f"{str(value)[:64]!r} is not one IPv4 or IPv6 address"
    return ""


def _prefix(value) -> str:
    """Why *value* is not one IPv4 or IPv6 prefix, or ``""``."""
    try:
        ipaddress.ip_network(str(value), strict=False)
    except ValueError:
        return f"{str(value)[:64]!r} is not one IPv4 or IPv6 prefix"
    return "" if "/" in str(value) else f"{str(value)[:64]!r} is not one IPv4 or IPv6 prefix"


@dataclass(frozen=True)
class Kind:
    """One NetBox read: its name, the endpoint it GETs, its noun in words, its arguments (each
    a shape check) and the NetBox filter each is sent as, the row it keeps (the fixed field
    list), and *needs*, the arguments of which at least one is given (a read of every object
    is refused)."""
    op: str
    path: str
    noun: str
    args: dict
    filters: dict
    row: object
    needs: tuple = ()


KINDS = {k.op: k for k in (
    Kind("netbox_prefixes", "/api/ipam/prefixes/", "prefix",
         {"contains": _address, "prefix": _prefix},
         {"contains": "contains", "prefix": "prefix"}, _prefix_row, needs=("contains", "prefix")),
)}

#: Where each kind is in NetBox's own menus, for the source a person reads.
WHERE = {"netbox_prefixes": "IPAM › Prefixes"}


def _ready():
    """``(ok, why, session, base)``: netbox_client's own (its configuration, its session)."""
    from modules.netbox_client import _nb_ready

    return _nb_ready()


def configured() -> bool:
    try:
        return bool(_ready()[0])
    except Exception:                                   # noqa: BLE001 (unreadable is off)
        return False


def source(op: str) -> str:
    """Where a read's answer came from, in words: NetBox's menu and the endpoint asked."""
    k = KINDS[op]
    return f"NetBox › {WHERE[op]} (GET {k.path})"


def asked(op: str, args: dict) -> str:
    """What a read asks, in words: "NetBox prefixes, contains 192.0.2.50"."""
    k = KINDS[op]
    given = ", ".join(f"{a} {v}" for a, v in sorted((args or {}).items()) if v not in (None, ""))
    return f"NetBox {k.noun}es" + (f", {given}" if given else ", the first page")


def _absent(op: str, args: dict) -> str:
    k = KINDS[op]
    given = {a: v for a, v in (args or {}).items() if v not in (None, "")}
    if op == "netbox_prefixes" and given.get("contains"):
        return f"no NetBox prefix contains {given['contains']}"
    words = " and ".join(f"{a} {v}" for a, v in sorted(given.items()))
    return f"no {k.noun} in NetBox" + (f" with {words}" if words else "")


def refusal(op: str, args: dict) -> str:
    """Why a read of *op* with *args* is not asked, or ``""``: an operation it is not, an
    argument it does not take or not of its shape, or none of the arguments it needs one of
    (`Kind.needs`)."""
    k = KINDS.get(op)
    if k is None:
        return f"{op!r} is not one of the NetBox reads ({', '.join(sorted(KINDS))})"
    given = {a: v for a, v in (args or {}).items() if v not in (None, "")}
    unknown = sorted(set(given) - set(k.args))
    if unknown:
        return f"{op} takes no argument {unknown[0]!r} (it takes: {', '.join(k.args)})"
    for a, v in sorted(given.items()):
        why = k.args[a](v)
        if why:
            return f"{op}'s {a}: {why}"
    if k.needs and not set(given) & set(k.needs):
        return (f"{op} needs one of {' or '.join(k.needs)}: a read of every {k.noun} is not "
                "asked")
    return ""


def read(op: str, args: dict) -> dict:
    """One NetBox read, one page: ``{"state": "ok"|"unconfigured"|"failed"|"refused", "op",
    "kind", "asked", "source", "count", "shown", "truncated", "rows", "said", "why"}``. *rows*
    each the kind's fixed fields (`Kind.row`); *said* the answer in words, an absence as a
    fact. A GET; never raises."""
    k = KINDS.get(op)
    out = {"state": "refused", "op": op, "kind": k.noun if k else "", "asked": "",
           "source": source(op) if k else "NetBox", "count": 0, "shown": 0,
           "truncated": False, "rows": [], "said": "", "why": ""}
    why = refusal(op, args)
    if why:
        return dict(out, why=why, said=f"not read: {why}")
    args = {a: v for a, v in (args or {}).items() if v not in (None, "")}
    out["asked"] = asked(op, args)
    try:
        ok, why, session, base = _ready()
    except Exception as exc:                            # noqa: BLE001 (said, never raised)
        ok, why, session, base = False, f"its settings could not be read ({type(exc).__name__})", \
            None, ""
    if not ok:
        return dict(out, state="unconfigured", why=why or "NetBox is not configured",
                    said=f"NetBox was not read: {why or 'it is not configured'}")
    params = {k.filters[a]: str(v) for a, v in args.items()}
    params["limit"] = PAGE
    try:
        r = session.get(f"{base}{k.path}", params=params, timeout=TIMEOUT_S)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:                            # noqa: BLE001 (said, never raised)
        log.info("netbox reads: %s did not answer: %s", op, type(exc).__name__)
        why = f"NetBox did not answer ({type(exc).__name__})"
        return dict(out, state="failed", why=why, said=f"not read: {why}")
    raw = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        why = "NetBox's answer held no list of results"
        return dict(out, state="failed", why=why, said=f"not read: {why}")
    rows = _unnamed([k.row(x) for x in raw[:PAGE] if isinstance(x, dict)])
    count = data.get("count") if isinstance(data.get("count"), int) else len(rows)
    truncated = count > len(rows)
    if not rows:
        said = _absent(op, args)
    elif truncated:
        said = (f"{len(rows)} shown of {count} {k.noun}es: the rest were not read; a narrower "
                "read names an address or a prefix")
    else:
        said = f"{count} {k.noun}" + ("" if count == 1 else "es") + " found"
    return dict(out, state="ok", count=count, shown=len(rows), truncated=truncated, rows=rows,
                said=said)
