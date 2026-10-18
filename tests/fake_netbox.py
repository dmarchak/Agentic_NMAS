"""An in-memory stand-in for the NetBox REST API.

Not named test_* so pytest does not collect it. Implements just enough of the
API surface that modules/netbox_client.py uses: paginated list GETs with simple
equality filtering, GET-by-id, POST (assigning ids), PATCH (merging), DELETE.

Used to compare a dry-run preview against a real execution against identical
starting state.
"""

import copy
import json
import re


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    @property
    def ok(self):
        return self.status_code < 400

    @property
    def text(self):
        return json.dumps(self._payload)

    def json(self):
        # A COPY, as a real response is decoded afresh from its bytes (C1010). Returning the
        # stored object let a later PATCH mutate a before-state already read, so `_nb_patch`
        # compared the after with itself and recorded no change.
        return copy.deepcopy(self._payload)

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


#: Fields NetBox 4.2 and later no longer have on an object, which a write DROPS without an error
#: (C1010, a deliberate model of the version the lab runs, 4.6.9). NetBox 4.2.0's release notes
#: ("Breaking Changes"): "The `site` foreign key field on `ipam.Prefix` has been replaced by the
#: `scope` generic foreign key". 4.6.9's PrefixSerializer declares no `site`, and its serializer
#: ignores a field it does not declare, so a POST carrying `site` answers 201 and the prefix holds
#: no site: measured on the host 2026-10-16, all 3 prefixes Mercury created carry neither a `site`
#: nor a `scope_type`. The fake keeps what was SENT in `posts` and `patches` and stores what NetBox
#: would hold, so a test that reads an object back sees the dropped field missing.
REMOVED_FIELDS = {"ipam/prefixes": ("site",)}

#: Objects that take NetBox 4.2+'s generic scope, stored as `scope_type` ("app.model") and
#: `scope_id`, both null when unset, and returned with a read-only nested `scope` (the scoped
#: object's brief form) as NetBox renders it. 4.6.9 limits a prefix's scope type to region,
#: sitegroup, site and location (`dcim.constants.LOCATION_SCOPE_TYPES`).
SCOPED_ENDPOINTS = {"ipam/prefixes"}
_SCOPE_STORE = {"dcim.site": "dcim/sites", "dcim.region": "dcim/regions",
                "dcim.sitegroup": "dcim/site-groups", "dcim.location": "dcim/locations"}


#: A cable filter on one end -> the field holding that end's terminations. NetBox 4.x's
#: ``CableFilterSet`` matches ``termination_a_id`` against any termination on end A, whatever its
#: type; a cable is stored with ``a_terminations``/``b_terminations``, each a list of
#: ``{object_type, object_id}``, as it is POSTed and as NetBox returns it (C1220). Kept apart
#: from the product's matcher (`netbox_guard.params_match`) on purpose: this is NetBox's answer,
#: the expectation the product's dry run is compared with.
CABLE_ENDS = {"termination_a_id": "a_terminations", "termination_b_id": "b_terminations"}

#: An object filter -> the store holding the one kind of object it names (C1240). Written from
#: NetBox's filter names, apart from the product's code on purpose: this is NetBox's answer, the
#: expectation a test compares the product with. NetBox declares such a filter as a choice of
#: existing objects, so an id no object of that kind holds answers 400, as a negative one does:
#: measured on the lab's NetBox 2026-10-17 for ``dcim/devices/?site_id=<an unused id>`` (400; a
#: real ``site_id`` 200), and 2026-10-18 for ``dcim/interfaces/?device_id=`` (400). The other
#: names below are applied BY NAME and were not measured; where NetBox implements one as a
#: method over plain numbers it answers an empty 200 instead, as ``ipam/ip-addresses/?device_id=``
#: does (measured 2026-10-18: 200, count 0), listed in ``METHOD_FILTERS`` and answered so.
KIND_FILTERS = {
    "region_id": "dcim/regions", "site_group_id": "dcim/site-groups",
    "site_id": "dcim/sites", "location_id": "dcim/locations",
    "manufacturer_id": "dcim/manufacturers", "device_type_id": "dcim/device-types",
    "platform_id": "dcim/platforms", "device_id": "dcim/devices",
    "interface_id": "dcim/interfaces", "vrf_id": "ipam/vrfs", "vlan_id": "ipam/vlans",
    "tunnel_id": "vpn/tunnels", "tag_id": "extras/tags", "tenant_id": "tenancy/tenants",
}

#: ``role_id`` names a different kind on each endpoint: a device's role is a Device Role, a
#: prefix's or a VLAN's an IPAM Role (an IP address's role is a choice, not an object).
ROLE_KINDS = {"dcim/devices": "dcim/device-roles", "ipam/prefixes": "ipam/roles",
              "ipam/vlans": "ipam/roles"}

#: (endpoint, filter) pairs NetBox implements as a method over plain numbers: an unknown id
#: matches nothing (an empty 200), measured on the lab's NetBox 2026-10-18.
METHOD_FILTERS = {("ipam/ip-addresses", "device_id")}

#: ``_id`` filters that name no single kind, answered as before (an unknown id matches nothing,
#: 200): ``id`` itself, and the generic ends whose kind is another field (a cable's termination,
#: a tunnel termination's, an address's assigned object, a prefix's scope). Any other ``_id``
#: name outside the two tables above is not modelled either and is answered as before.
UNMODELLED_ID_FILTERS = ("id", "termination_id", "termination_a_id", "termination_b_id",
                         "assigned_object_id", "scope_id", "object_id")

_NEGATIVE = re.compile(r"^-\d+$")


def _members(value) -> list:
    """The ids a filter value carries: itself, or each member of a list. Nothing for a value a
    request drops (None) or sends empty, or a bool (never an id)."""
    values = list(value) if isinstance(value, (list, tuple, set)) else [value]
    return [v for v in values
            if v is not None and not isinstance(v, bool) and str(v).strip() != ""]


def _is_negative_id(value) -> bool:
    """A negative id in any shape a request can carry it: an int, a numeric string, or a member
    of a list (C1223)."""
    if isinstance(value, (list, tuple, set)):
        return any(_is_negative_id(v) for v in value)
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value < 0
    return isinstance(value, str) and bool(_NEGATIVE.match(value.strip()))


def _negative_id_answer(where: str, value) -> "FakeResponse":
    """NetBox 4.6.9's answer to a negative id in a filter (C1179, measured in W4 step 29:
    ``400 Client Error: Bad Request`` for ``dcim/devices/?name=s6&site_id=-3``): an object
    filter is a choice of existing objects, and no object has a negative id. The fake answers
    a negative id in a PATH the same way (C1223): NetBox's answer there was not measured (its
    router's lookup would likely answer 404, which a caller reads as "gone"); a 400 makes a
    placeholder sent by path fail loudly in a test instead of reading as a deleted object.
    The same answer serves a positive id no object of the filter's kind holds (C1240)."""
    return FakeResponse({where: [f"Select a valid choice. {value} is not one of the available "
                                 "choices."]}, 400)


class FakeNetBox:
    """A minimal NetBox. ``store`` maps endpoint -> list of object dicts."""

    def __init__(self):
        self.store: dict = {}
        self._next_id = 1
        self.posts: list = []      # (endpoint, payload) in order
        self.patches: list = []    # (endpoint, obj_id, payload)
        self.deletes: list = []    # (endpoint, obj_id)
        #: (endpoint, obj_id) a constrained delete permission refuses: NetBox answers 404 and
        #: keeps the object (C466).
        self.refuse_delete: set = set()
        self.verify = True
        self.headers = {}

    # ── helpers ─────────────────────────────────────────────────────────────

    def seed(self, endpoint, obj):
        """Pre-populate an object, as if a human had created it in NetBox."""
        obj = dict(obj)
        obj.setdefault("id", self._take_id())
        obj.setdefault("tags", [])
        self._as_stored(endpoint.strip("/"), obj)
        self.store.setdefault(endpoint.strip("/"), []).append(obj)
        return obj

    def _as_stored(self, endpoint, obj):
        """*obj* as NetBox 4.2+ holds it: a removed field gone, a scope rendered (above)."""
        for field in REMOVED_FIELDS.get(endpoint, ()):
            obj.pop(field, None)
        if endpoint in SCOPED_ENDPOINTS:
            obj.setdefault("scope_type", None)
            obj.setdefault("scope_id", None)
            obj["scope"] = self._scope(obj["scope_type"], obj["scope_id"])
        return obj

    def _scope(self, scope_type, scope_id):
        if not scope_type or scope_id is None:
            return None
        for o in self.store.get(_SCOPE_STORE.get(scope_type, ""), []):
            if o["id"] == scope_id:
                return {"id": o["id"], "url": f"http://nb.invalid/api/{_SCOPE_STORE[scope_type]}"
                                             f"/{o['id']}/",
                        "display": o.get("name", ""), "name": o.get("name", ""),
                        "slug": o.get("slug", ""), "description": o.get("description", "")}
        return None

    def _take_id(self):
        val = self._next_id
        self._next_id += 1
        return val

    @staticmethod
    def _parse(url):
        """Split an API url into (endpoint, object_id|None)."""
        path = re.sub(r"^.*?/api/", "", url).strip("/")
        parts = path.split("/")
        # A negative segment is an id too (C1223), so it is answered as one, never read as a
        # list endpoint named "dcim/devices/-3" holding nothing.
        if parts and (parts[-1].isdigit() or _NEGATIVE.match(parts[-1])):
            return "/".join(parts[:-1]), int(parts[-1])
        return path, None

    @staticmethod
    def _negative(obj_id, params):
        """NetBox's 400 when the request carries a negative id, in its path or a filter."""
        if obj_id is not None and obj_id < 0:
            return _negative_id_answer("id", obj_id)
        for key, value in (params or {}).items():
            if _is_negative_id(value):
                return _negative_id_answer(key, value)
        return None

    def _unknown(self, endpoint, params):
        """NetBox's 400 when an object filter names an id no object of its kind holds (C1240),
        in each shape: an int, a numeric string, a list member."""
        for key, value in (params or {}).items():
            kind = ROLE_KINDS.get(endpoint) if key == "role_id" else KIND_FILTERS.get(key)
            if kind is None or (endpoint, key) in METHOD_FILTERS:
                continue
            held = {str(o.get("id")) for o in self.store.get(kind, [])}
            for member in _members(value):
                if str(member).strip() not in held:
                    return _negative_id_answer(key, member)
        return None

    @staticmethod
    def _matches(obj, params):
        for key, value in (params or {}).items():
            if key in ("limit", "offset", "brief", "depth"):
                continue
            if key == "q":                       # fuzzy search: substring on name
                if str(value).lower() not in str(obj.get("name", "")).lower():
                    return False
                continue
            if key in CABLE_ENDS:                # a cable by either of its ends (C1220)
                held = obj.get(CABLE_ENDS[key])
                if not isinstance(held, list) or not any(
                        str(t.get("object_id")) == str(value) for t in held):
                    return False
                continue
            if key == "device_id" and "assigned_object" in obj:
                # NetBox supports ?device_id= on ipam/ip-addresses by joining
                # through the assigned interface to its device.
                assigned = obj.get("assigned_object") or {}
                device = (assigned.get("device") or {})
                if str(device.get("id")) != str(value):
                    return False
                continue
            if key == "interface_id" and "assigned_object_type" in obj:
                # NetBox supports ?interface_id= on ipam/ip-addresses by
                # joining through the generic assignment. Added when the
                # lookup key became the interface; the fake had only the
                # device-level join below it.
                if (obj.get("assigned_object_type") or "") != "dcim.interface":
                    return False
                if str(obj.get("assigned_object_id")) != str(value):
                    return False
                continue
            if key == "address":
                # NetBox matches a bare host address against a stored address
                # that carries a prefix length, so "203.0.113.10" finds
                # "203.0.113.10/24".
                stored = str(obj.get("address", ""))
                if stored != str(value) and stored.split("/")[0] != str(value).split("/")[0]:
                    return False
                continue
            candidates = [key]
            if key.endswith("_id"):
                candidates.append(key[:-3])
            for cand in candidates:
                if cand in obj:
                    actual = obj[cand]
                    if isinstance(actual, dict):
                        actual = actual.get("id", actual.get("name"))
                    if str(actual) != str(value):
                        return False
                    break
            else:
                return False                      # filtered on a field we lack
        return True

    # ── requests.Session surface ────────────────────────────────────────────

    def get(self, url, params=None, timeout=None):
        endpoint, obj_id = self._parse(url)
        refused = self._negative(obj_id, params)
        if refused is None and obj_id is None:
            refused = self._unknown(endpoint, params)
        if refused is not None:
            return refused
        items = self.store.get(endpoint, [])
        if obj_id is not None:
            for obj in items:
                if obj["id"] == obj_id:
                    return FakeResponse(obj)
            return FakeResponse({"detail": "Not found."}, 404)
        hits = [o for o in items if self._matches(o, params)]
        return FakeResponse({"results": hits, "next": None, "count": len(hits)})

    def post(self, url, json=None, timeout=None):
        endpoint, _ = self._parse(url)
        payload = dict(json or {})
        if endpoint == "dcim/cables":
            # NetBox refuses a second cable on a termination already cabled (C1220): each
            # termination belongs to one cable.
            for end in ("a_terminations", "b_terminations"):
                for t in payload.get(end) or []:
                    held = self._cable_on(t)
                    if held is not None:
                        return FakeResponse({"__all__": [
                            f"Duplicate termination found for {t.get('object_type')}:"
                            f"{t.get('object_id')}: cable {held['id']}"]}, 400)
        self.posts.append((endpoint, dict(payload)))
        obj = dict(payload)
        obj["id"] = self._take_id()
        obj.setdefault("tags", [])
        # NetBox returns tags as objects; the client sends ids.
        obj["tags"] = [{"id": t, "slug": self._tag_slug(t), "name": self._tag_slug(t)}
                       if isinstance(t, int) else t for t in obj["tags"]]
        self._as_stored(endpoint, obj)
        self.store.setdefault(endpoint, []).append(obj)
        return FakeResponse(obj, 201)

    def _cable_on(self, termination):
        """The stored cable holding *termination* on either end, or None."""
        for cable in self.store.get("dcim/cables", []):
            for end in ("a_terminations", "b_terminations"):
                for t in cable.get(end) or []:
                    if (t.get("object_type") == termination.get("object_type")
                            and str(t.get("object_id")) == str(termination.get("object_id"))):
                        return cable
        return None

    def patch(self, url, json=None, timeout=None):
        endpoint, obj_id = self._parse(url)
        refused = self._negative(obj_id, None)
        if refused is not None:
            return refused
        payload = dict(json or {})
        self.patches.append((endpoint, obj_id, dict(payload)))
        for obj in self.store.get(endpoint, []):
            if obj["id"] == obj_id:
                obj.update(payload)
                self._as_stored(endpoint, obj)
                return FakeResponse(obj)
        return FakeResponse({"detail": "Not found."}, 404)

    def delete(self, url, timeout=None):
        endpoint, obj_id = self._parse(url)
        refused = self._negative(obj_id, None)
        if refused is not None:
            return refused
        self.deletes.append((endpoint, obj_id))
        if (endpoint, obj_id) in self.refuse_delete:
            return FakeResponse({"detail": "Not found."}, 404)
        items = self.store.get(endpoint, [])
        for i, obj in enumerate(items):
            if obj["id"] == obj_id:
                items.pop(i)
                return FakeResponse({}, 204)
        return FakeResponse({"detail": "Not found."}, 404)

    def _tag_slug(self, tag_id):
        for obj in self.store.get("extras/tags", []):
            if obj["id"] == tag_id:
                return obj.get("slug", "")
        return ""

    # ── assertions ──────────────────────────────────────────────────────────

    def created_counts(self):
        counts: dict = {}
        for endpoint, _ in self.posts:
            counts[endpoint] = counts.get(endpoint, 0) + 1
        return counts

    def objects(self, endpoint):
        return self.store.get(endpoint.strip("/"), [])
