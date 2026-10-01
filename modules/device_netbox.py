"""A device's NetBox record, for the device page's NetBox tab (NSOT_GUI_BRIEF
3.3; step 4): what NetBox holds about it, and NMAS's own PROVENANCE for that
record. Read-only: writes stay on today's NetBox tab, behind its preview and
one-time token.

**Who owns the record is the question a person needs answered before
touching it**, and NetBox cannot answer it: the `nmas-managed` tag says NMAS
created an object (`_nb_post` alone adds it) and the created-object record
says the same from NMAS's side; removal needs BOTH. An adopted device's
objects existed before NMAS managed it and are never deletable by NMAS. A
record that is neither is a person's. A tag without the record (or the
reverse) is a disagreement, drawn as one, never resolved by picking a side.

**What NetBox says that NMAS knows differently is said**: the platform NetBox
holds against the inventory's (register A4: the import has written `ios` for
every device), named rather than shown as if either were simply true.
"""

import logging

log = logging.getLogger(__name__)

ENDPOINT = "dcim/devices"
MANAGED_TAG = "nmas-managed"


def _name(obj):
    if isinstance(obj, dict):
        return obj.get("name") or obj.get("display") or obj.get("label") or ""
    return obj or ""


def provenance(list_name: str, obj_id: int, tags) -> dict:
    """``{state, words, kind, error}`` from the tag and NMAS's two records."""
    from modules import netbox_guard as g
    tagged = MANAGED_TAG in {(_t.get("slug") if isinstance(_t, dict) else _t) for _t in tags or []}
    held, err = g.recorded_objects(list_name)
    recorded = any(ep == ENDPOINT and oid == obj_id for ep, oid, _n in held)
    adopted, aerr = g.get_adopted(list_name)
    is_adopted = any(ep == ENDPOINT and oid == obj_id for ep, oid, _n, _d in adopted)
    error = "; ".join(e for e in (err, aerr) if e)
    if error:
        return {"state": "unknown", "kind": "muted", "error": error,
                "words": f"Who owns this record cannot be said: {error}."}
    if tagged and recorded:
        return {"state": "created", "kind": "info", "error": "",
                "words": "NMAS created this record (tagged nmas-managed and in its record), "
                         "so the NetBox tab's Remove can delete it."}
    if is_adopted:
        return {"state": "adopted", "kind": "muted", "error": "",
                "words": "Adopted: the record existed before NMAS managed the device. "
                         "NMAS updates the fields it imports and never deletes it."}
    if tagged != recorded:
        which = "tagged nmas-managed but missing from NMAS's record" if tagged else \
            "in NMAS's record but not tagged nmas-managed"
        return {"state": "disagrees", "kind": "warn", "error": "",
                "words": f"The record is {which}, so Remove cannot act on it "
                         "(it needs both); nmas-netbox-untagged names every such object."}
    return {"state": "person", "kind": "muted", "error": "",
            "words": "A person's record: NMAS did not create it. NMAS updates the fields "
                     "it imports and never deletes it."}


def modifications(list_name: str, obj_id: int) -> dict:
    """``{count, last, error}``: NMAS's recorded writes to this record."""
    from modules import netbox_guard as g
    from modules.config import list_slug
    data, reason = g.read_modified()
    if reason:
        return {"count": 0, "last": None, "error": reason}
    rows = [m for m in (data.get(list_slug(list_name)) or {}).get(ENDPOINT) or []
            if m.get("id") == obj_id]
    return {"count": len(rows), "last": rows[-1] if rows else None, "error": ""}


def for_device(ref, dev: dict) -> dict:
    """The NetBox tab's view: three reads of NetBox (the device by exact name,
    and two counts) plus NMAS's own records. Never raises; NetBox unreadable is
    said, never drawn as "not in NetBox"."""
    from modules.netbox_client import _nb_ready

    host = dev.get("hostname", "")
    view = {"configured": True, "errors": [], "record": None, "absent": False,
            "counts": {}, "provenance": None, "mods": None, "platform_note": "", "ui_url": ""}
    ok, err, session, base = _nb_ready()
    if not ok:
        view["configured"] = False
        return view
    try:
        r = session.get(f"{base}/api/{ENDPOINT}/", params={"name": host}, timeout=15)
        r.raise_for_status()
        hits = [d for d in r.json().get("results") or [] if d.get("name") == host]
    except Exception as exc:                          # noqa: BLE001
        view["errors"].append(f"NetBox could not be asked for {host}: {exc}")
        return view
    if not hits:
        view["absent"] = True
        return view
    if len(hits) > 1:
        view["errors"].append(f"NetBox holds {len(hits)} devices named {host} "
                              f"(ids {', '.join(str(d.get('id')) for d in hits)}), so none is drawn")
        return view
    d = hits[0]
    view["record"] = {
        "id": d.get("id"), "status": _name(d.get("status")),
        "role": _name(d.get("role") or d.get("device_role")),
        "platform": _name(d.get("platform")), "site": _name(d.get("site")),
        "model": _name((d.get("device_type") or {}).get("model") if isinstance(d.get("device_type"), dict) else ""),
        "primary_ip4": (d.get("primary_ip4") or {}).get("address", "") if isinstance(d.get("primary_ip4"), dict) else "",
        "serial": d.get("serial") or "", "last_updated": (d.get("last_updated") or "")[:19] + "Z"
        if d.get("last_updated") else "", "created": (d.get("created") or "")[:19] + "Z" if d.get("created") else "",
        "tags": [_name(t) for t in d.get("tags") or []],
    }
    view["ui_url"] = f"{base}/{ENDPOINT}/{d.get('id')}/"
    for ep, key in (("dcim/interfaces", "interfaces"), ("ipam/ip-addresses", "addresses")):
        try:
            c = session.get(f"{base}/api/{ep}/", params={"device_id": d.get("id"), "limit": 1},
                            timeout=15)
            c.raise_for_status()
            view["counts"][key] = c.json().get("count")
        except Exception as exc:                      # noqa: BLE001
            view["counts"][key] = None
            view["errors"].append(f"NetBox could not count {key} for {host}: {exc}")
    view["provenance"] = provenance(ref.name, d.get("id"), d.get("tags"))
    view["mods"] = modifications(ref.name, d.get("id"))
    from modules.nsot.platform import dialect_for_netbox_slug, platform_for_device
    mine = platform_for_device(dev)
    nb = d.get("platform") if isinstance(d.get("platform"), dict) else {}
    slug, held = (nb.get("slug") or ""), view["record"]["platform"]
    theirs = dialect_for_netbox_slug(slug)
    if slug and theirs != mine:
        view["platform_note"] = (
            f"NetBox holds the platform {held} ({slug}), "
            + (f"which is {theirs}" if theirs else "which names no platform this tool knows")
            + f"; the inventory says {mine}, and the inventory's is the one the tool uses. "
              "The import has written `ios` for every device (register A4, scheduled into 7.6).")
    return view

