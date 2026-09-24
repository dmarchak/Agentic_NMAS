"""What the DATABASE takes with an object, beyond what NMAS asks it to delete.

Stage 4C, after the probe's teardown deleted two objects NMAS did not
create. The delete list was correct and every provenance check passed:
request `263695a3` deleted `dcim/interfaces` id 60, and the database removed
the two IP addresses assigned to it. **Provenance protects an OBJECT; a
cascade travels a RELATIONSHIP, and nothing checked relationships.**

The two findings from that night are deliberately separate, because they
outlive each other. The lookup key being the address rather than the
interface was a write bug and is fixed at its site. **This is the other
one, and it survives that fix**: any delete of any type can take objects
with it, and the preview must say what will actually go.

**A type absent from `CASCADES` is UNKNOWN, never "takes nothing".**
That is the whole design. An empty answer and an unmeasured one look
identical in a preview, and the one that reads as safe is the one that was
never checked -- the same shape as an empty `failed_checks` beside a failure
state, and as "all 9 clean" over a ten-device inventory.
"""

import logging

log = logging.getLogger(__name__)

#: Endpoint -> the queries that find what the database removes with it.
#: Each entry is ``(child_endpoint, filter_name)``; the object's id is the
#: filter's value. **MEASURED, not inferred from Django's `on_delete`.**
#:
#: `dcim/interfaces` was measured on the real NetBox on 2026-09-24, by the
#: changelog: one DELETE request, three deletions, two of them addresses
#: carrying `assigned_object_id` of the deleted interface.
#:
#: `dcim/devices` follows transitively -- deleting a device removes its
#: interfaces, which removes their addresses -- and `_walk` expands that
#: rather than the map listing addresses under devices, so the two cannot
#: disagree.
#: An empty tuple is **measured to take nothing**, which is a different
#: claim from absence. Request `263695a3` held one DELETE and exactly three
#: deletions -- the interface and its two addresses -- so the addresses'
#: own removal produced nothing further, from the same evidence. Keeping
#: them absent instead would have made every preview unproven, and a warning
#: that fires on everything trains the reader to skip warnings.
CASCADES = {
    "dcim/interfaces":   (("ipam/ip-addresses", "interface_id"),),
    "dcim/devices":      (("dcim/interfaces", "device_id"),),
    "ipam/ip-addresses": (),
}

#: Types whose cascade behaviour has NOT been measured. Listed rather than
#: inferred from `CASCADES`'s keys so that adding an endpoint to the removal
#: order without measuring it is a visible omission instead of a silent
#: "takes nothing". `_REMOVAL_ORDER` is checked against this by a test.
UNMEASURED = (
    "vpn/tunnels", "ipam/prefixes", "ipam/vlans", "ipam/vrfs",
    "dcim/sites", "dcim/regions",
)

#: A measured-empty entry must be deliberate, so the two sets may not
#: overlap: a type in both would be "we measured it and we did not".
assert not (set(CASCADES) & set(UNMEASURED))


class DependentsUnproven(Exception):
    """The dependents query did not run. **Not the same as none.**"""


def dependents_of(session, base: str, endpoint: str, obj_id: int,
                  _seen: set = None) -> dict:
    """What deleting ``endpoint/obj_id`` takes with it.

    Returns ``{"ok", "objects", "unproven"}``. `unproven` is a list of
    reasons -- an unmeasured type, or a query that failed -- and it is
    **never merged into `objects`**: "I know these will go" and "I do not
    know what else will" are different claims, and a caller that cannot tell
    them apart will render the second as the first.
    """
    from modules.netbox_client import _nb_get

    _seen = _seen if _seen is not None else set()
    key = (endpoint, obj_id)
    if key in _seen:                       # a cycle cannot add anything new
        return {"ok": True, "objects": [], "unproven": []}
    _seen.add(key)

    if endpoint not in CASCADES:
        return {"ok": True, "objects": [],
                "unproven": [f"{endpoint}: what a delete takes with it has "
                             "not been measured on this NetBox"]}

    objects, unproven = [], []
    for child_endpoint, filter_name in CASCADES[endpoint]:
        try:
            rows = _nb_get(session, base, f"{child_endpoint}/",
                           **{filter_name: obj_id})
        except Exception as exc:
            # UNPROVEN, not empty. A failed query rendered as "nothing will
            # cascade" is the preview lying in the direction that reads safe.
            log.warning("netbox: dependents query %s?%s=%s failed: %s",
                        child_endpoint, filter_name, obj_id, exc)
            unproven.append(f"{child_endpoint}?{filter_name}={obj_id}: the "
                            f"query failed ({exc})")
            continue
        for row in rows:
            objects.append({"endpoint": child_endpoint, "id": row.get("id"),
                            "name": _label(row), "via": endpoint})
            deeper = dependents_of(session, base, child_endpoint,
                                   row.get("id"), _seen)
            objects.extend(deeper["objects"])
            unproven.extend(deeper["unproven"])

    return {"ok": not unproven, "objects": objects, "unproven": unproven}


def _label(obj: dict) -> str:
    return str(obj.get("display") or obj.get("name")
               or obj.get("address") or obj.get("id") or "")


def collateral(session, base: str, planned: list, recorded_ids: set) -> dict:
    """Of everything the planned deletes take, what NMAS did NOT create.

    `planned` is the preview's own delete list. `recorded_ids` is the set of
    ``(endpoint, id)`` NMAS has a creation record for. The difference is the
    answer to *"will this delete anything that is not mine"*, which is the
    question the provenance gate was built to answer and could not, because
    it was asked about each object rather than about the consequence.
    """
    taken, unproven = [], []
    seen = set()
    for item in planned:
        res = dependents_of(session, base, item["endpoint"], item["id"])
        unproven.extend(res["unproven"])
        for obj in res["objects"]:
            key = (obj["endpoint"], obj["id"])
            if key in seen:
                continue
            seen.add(key)
            obj = dict(obj, foreign=key not in recorded_ids)
            taken.append(obj)
    return {
        "taken": taken,
        "foreign": [o for o in taken if o["foreign"]],
        "unproven": unproven,
        # A preview that could not ask must not render as one that asked and
        # got nothing.
        "proven": not unproven,
    }
