"""A device's KIND (router, switch, firewall) is NetBox's (C665, the operator, 2026-10-11).

Mercury kept its own table from NetBox role slug to kind (`role_map`), and the kind drives
behaviour, not only icons: the credential profile a device signs in with (`role:<kind>`), the
monitoring profile's sections, Prometheus's `role` label, an IP SLA probe's end. So the kind
moves to NetBox as a custom field on the Device Role, `mercury_kind`, read like any other
NetBox fact; a role without it is "not classified in NetBox", never guessed from a hostname.

This module reads the field, and plans and applies its one-time migration: the field created
on device roles, and each NetBox role the table named given the table's kind. The migration
writes through the client's chokepoints under a declared authority, and reads every role back.
"""

import hashlib
import json
import logging

log = logging.getLogger(__name__)

FIELD = "mercury_kind"
KINDS = ("router", "switch", "firewall")
#: The field's definition: text constrained to the kinds (NetBox 4's select needs a separate
#: choice set; a validated text field is one object, and NetBox refuses anything else).
FIELD_SPEC = {
    "name": FIELD,
    "label": "Mercury kind",
    "type": "text",
    "object_types": ["dcim.devicerole"],
    "validation_regex": "^(" + "|".join(KINDS) + ")$",
    "description": ("What Mercury treats devices of this role as: router, switch or firewall. "
                    "Empty: not classified (C665)."),
}


class KindUnreadable(Exception):
    """NetBox could not be asked for its roles or the field."""


def read(session, base: str) -> dict:
    """``{"field": bool, "roles": [{"id", "slug", "kind"}], "kinds": {slug: kind}}``. A kind
    that is not one of KINDS reads as unclassified."""
    from modules.netbox_client import _nb_get

    try:
        fields = [f for f in _nb_get(session, base, "extras/custom-fields", name=FIELD)
                  if f.get("name") == FIELD]
        roles = _nb_get(session, base, "dcim/device-roles")
    except Exception as exc:                      # noqa: BLE001
        raise KindUnreadable(f"NetBox's device roles could not be read: {exc}") from exc
    out = []
    for r in roles:
        kind = str((r.get("custom_fields") or {}).get(FIELD) or "").strip().lower()
        out.append({"id": r.get("id"), "slug": r.get("slug") or "",
                    "kind": kind if kind in KINDS else ""})
    return {"field": bool(fields), "roles": sorted(out, key=lambda r: r["slug"]),
            "kinds": {r["slug"]: r["kind"] for r in out if r["kind"]}}


def plan(role_map: dict, now: dict) -> dict:
    """What the migration does: create the field if absent, and give each NetBox role the
    table named its kind, unless NetBox already holds one (NetBox's wins). Roles the table
    does not name stay unclassified, and are listed. Hashed, so --apply runs this plan."""
    table = {k: str(v).strip().lower() for k, v in (role_map or {}).items()
             if str(v).strip().lower() in KINDS}
    sets, kept, unnamed = [], [], []
    for r in now["roles"]:
        if r["kind"]:
            kept.append({"slug": r["slug"], "kind": r["kind"]})
        elif r["slug"] in table:
            sets.append({"id": r["id"], "slug": r["slug"], "kind": table[r["slug"]]})
        else:
            unnamed.append(r["slug"])
    body = {"create_field": not now["field"], "set": sets, "kept": kept,
            "unclassified": unnamed}
    body["hash"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:12]
    return body


def apply(p: dict, session, base: str, actor: str) -> dict:
    """Write the plan, then read every role back. ``{"ok", "lines"}``."""
    from modules.netbox_client import _nb_patch, _nb_post
    from modules.netbox_guard import for_list

    lines = []
    with for_list("", actor=actor, authority=f"nmas-netbox-role-kind --apply {p['hash']}, "
                                             f"by {actor}"):
        if p["create_field"]:
            _nb_post(session, base, "extras/custom-fields/", dict(FIELD_SPEC))
            lines.append(f"created the custom field {FIELD} on device roles")
        for s in p["set"]:
            _nb_patch(session, base, f"dcim/device-roles/{s['id']}/",
                      {"custom_fields": {FIELD: s["kind"]}})
            lines.append(f"role {s['slug']}: {FIELD} = {s['kind']}")
    back = read(session, base)
    wrong = [s["slug"] for s in p["set"] if back["kinds"].get(s["slug"]) != s["kind"]]
    if not back["field"]:
        wrong.append(f"the field {FIELD}")
    lines.append("read back: " + ("every write is there" if not wrong
                                  else "NOT there: " + ", ".join(wrong)))
    return {"ok": not wrong, "lines": lines}
