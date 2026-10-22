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

_SITE, _TAG = ("dcim/sites", "slug"), ("extras/tags", "slug")
_VRF = ("ipam/vrfs", "rd")
_IPAM_ROLE, _MAKER = ("ipam/roles", "slug"), ("dcim/manufacturers", "slug")

#: An object filter by a value other than the id, per endpoint -> (the store of the kind it
#: names, the field its value is matched against) (C1248). Written from the measurement, apart
#: from the product's code on purpose: this is NetBox's answer. Measured on the lab's NetBox
#: 2026-10-18 ~00:5x UTC, status only, with a value naming no object: each pair below answered
#: 400 (``dcim/devices/?site=`` the first; a real ``site`` slug 200 count 10, a real ``tag`` 200
#: count 3, the controls). The FIELD was not measured; it is the one NetBox's filter declares
#: (``to_field_name``): the slug for most; a device's ``name`` (``device`` on interfaces); a VRF's
#: route distinguisher, ``rd``, for ``vrf`` (labelled "VRF (RD)" in NetBox's ipam filtersets).
#: On devices ``role`` is a Device Role, on prefixes and VLANs an IPAM Role. The same
#: measurement answered an empty 200 (count 0) for a plain field or a method filter, which this
#: table leaves out so they answer as before: devices ``name``, ``serial``; interfaces ``name``;
#: ip-addresses ``device`` (a method), ``address``; ``slug``/``name``/``rd`` on the kinds'
#: own endpoints; tunnels, custom fields and config templates by ``name``.
OBJECT_FILTERS = {
    "dcim/devices": {
        "site": _SITE, "role": ("dcim/device-roles", "slug"), "tag": _TAG,
        "platform": ("dcim/platforms", "slug"), "manufacturer": _MAKER,
        "region": ("dcim/regions", "slug"), "site_group": ("dcim/site-groups", "slug"),
        "location": ("dcim/locations", "slug"), "tenant": ("tenancy/tenants", "slug"),
        "device_type": ("dcim/device-types", "slug"),
    },
    "dcim/interfaces": {"device": ("dcim/devices", "name"), "tag": _TAG},
    "ipam/ip-addresses": {"vrf": _VRF, "tag": _TAG},
    "ipam/prefixes": {"site": _SITE, "vrf": _VRF, "tag": _TAG, "role": _IPAM_ROLE},
    "ipam/vlans": {"site": _SITE, "tag": _TAG, "role": _IPAM_ROLE},
    "dcim/sites": {"region": ("dcim/regions", "slug"), "tag": _TAG},
    "dcim/device-types": {"manufacturer": _MAKER},
    "dcim/platforms": {"manufacturer": _MAKER},
    "vpn/tunnels": {"tag": _TAG},
}

#: A choice filter, per (endpoint, filter) -> its choices' values (C1248): a value that is no
#: choice answers 400, measured the same night for ``dcim/devices/?status=`` and
#: ``ipam/ip-addresses/?role=``. The values are NetBox 4.x's ``DeviceStatusChoices`` and
#: ``IPAddressRoleChoices``. ``status`` on the other endpoints was not measured.
CHOICE_FILTERS = {
    ("dcim/devices", "status"): ("offline", "active", "planned", "staged", "failed",
                                 "inventory", "decommissioning"),
    ("ipam/ip-addresses", "role"): ("loopback", "secondary", "anycast", "vip", "vrrp", "hsrp",
                                    "glbp", "carp"),
}

#: Where an object holds the reference a filter matches, when not under the filter's own name:
#: a path of fields, each hop but the last through the store named (NetBox joins the same way:
#: a device's region is its site's). A prefix's site is its scope when scoped to a site (NetBox
#: 4.2+); a region's or a location's descendants are not followed.
REF_PATHS = {
    ("dcim/devices", "region"): (("site", "dcim/sites"), ("region", None)),
    ("dcim/devices", "site_group"): (("site", "dcim/sites"), ("group", None)),
    ("dcim/devices", "manufacturer"): (("device_type", "dcim/device-types"),
                                       ("manufacturer", None)),
}

_NEGATIVE = re.compile(r"^-\d+$")

#: ── The console model (O4, docs/LAB9_PLAN.md section 8), MEASURED against the real service ──
#: The measurement: tests/fixtures/netbox/console_shapes.json, read-only on the lab's NetBox
#: 4.6.9 on 2026-10-22 (a GET with ``limit=1`` and the OPTIONS field list of a POST, for
#: dcim/console-ports/, dcim/console-server-ports/, dcim/cables/ and the two template
#: endpoints; NetBox's address replaced by netbox.example). What it measured and what it did
#: not, per endpoint the fake answers:
#:
#: - **dcim/cables/**: a whole cable body (cable 1): every field below, the status a
#:   ``{value, label}`` choice, each termination ``{object_type, object_id, object}`` with
#:   ``object`` the terminated port's brief form (`_PORT_BRIEF_FIELDS`, its ``cable`` and
#:   ``device`` briefs as captured). MEASURED, and tests/test_console_path.py compares the
#:   fake's rendered cable with it key for key. ``next`` carried ``?limit=1&offset=1``: the
#:   paging the fake answers below.
#: - **dcim/console-ports/** and **dcim/console-server-ports/**: the field NAMES (OPTIONS,
#:   read-only ones included) MEASURED, compared key for key the same way. The lab held no
#:   console port (count 0), so the VALUES of the computed fields are NetBox 4.x's serializer
#:   as written, NOT measured: ``link_peers`` and ``connected_endpoints`` each a list of the
#:   peer's brief (the same brief a cable termination's ``object`` is, which IS measured),
#:   ``*_type`` the peer's ``app.model``, ``cable_end`` "A"/"B" (None uncabled). The product
#:   reads only a port's ``id``, ``name`` and ``cable`` brief and then the cable by id, all
#:   measured shapes (modules/nsot/console_path.py).
#: - A component's name is unique on its device (NetBox's model constraint): a second POST of
#:   one answers 400. The status is NetBox's for a validation error; the message is not measured.
#: - The two template endpoints answered count 0 and are not faked: the product never reads them.
CONSOLE_ENDPOINTS = ("dcim/console-ports", "dcim/console-server-ports")

#: A console port's and a console-server port's fields, as OPTIONS listed them (measured).
CONSOLE_PORT_FIELDS = (
    "_occupied", "cable", "cable_end", "connected_endpoints", "connected_endpoints_reachable",
    "connected_endpoints_type", "created", "custom_fields", "description", "device", "display",
    "display_url", "id", "label", "last_updated", "link_peers", "link_peers_type",
    "mark_connected", "module", "name", "owner", "speed", "tags", "type", "url")

#: A cable's fields, as the captured cable body held them (measured).
CABLE_FIELDS = (
    "a_terminations", "b_terminations", "bundle", "color", "comments", "created",
    "custom_fields", "description", "display", "display_url", "id", "label", "last_updated",
    "length", "length_unit", "owner", "profile", "status", "tags", "tenant", "type", "url")

#: A terminated port's brief (a cable termination's ``object``), as captured (measured).
_PORT_BRIEF_FIELDS = ("_occupied", "cable", "description", "device", "display", "id", "name",
                      "url")

#: A termination's ``object_type`` -> the store holding that kind of port.
TERMINATION_STORES = {"dcim.interface": "dcim/interfaces",
                      "dcim.consoleport": "dcim/console-ports",
                      "dcim.consoleserverport": "dcim/console-server-ports"}

#: A cable status's label, by value (NetBox's ``LinkStatusChoices``).
CABLE_STATUS_LABELS = {"connected": "Connected", "planned": "Planned",
                       "decommissioning": "Decommissioning"}

_STAMP = "2026-10-22T00:00:00.000000Z"
_NB = "http://nb.invalid"


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

    def _unknown_value(self, endpoint, params):
        """NetBox's 400 when an object filter's value names no object of its kind by the field
        its filter matches, or a choice filter's value is no choice (C1248), as a string or a
        list member."""
        for key, value in (params or {}).items():
            choices = CHOICE_FILTERS.get((endpoint, key))
            spec = OBJECT_FILTERS.get(endpoint, {}).get(key)
            if choices is None and spec is None:
                continue
            held = set(choices) if choices is not None else {
                str(o.get(spec[1])) for o in self.store.get(spec[0], []) if o.get(spec[1])}
            for member in _members(value):
                if str(member).strip() not in held:
                    return _negative_id_answer(key, member)
        return None

    def _refs(self, endpoint, key, obj):
        """The references *obj* holds for filter *key*: one, or each tag."""
        if endpoint in SCOPED_ENDPOINTS and key == "site":
            return [obj.get("scope")] if obj.get("scope_type") == "dcim.site" else []
        if key == "tag":
            return list(obj.get("tags") or [])
        path = REF_PATHS.get((endpoint, key), ((key, None),))
        ref = obj
        for i, (field, store) in enumerate(path):
            ref = ref.get(field) if isinstance(ref, dict) else None
            if ref is None:
                return []
            if i < len(path) - 1:          # a hop: the full object, by the brief's id
                ident = ref.get("id") if isinstance(ref, dict) else ref
                ref = next((o for o in self.store.get(store, []) if o.get("id") == ident), None)
        return [ref]

    def _refers(self, endpoint, key, obj, value) -> bool:
        """Whether *obj* refers to what *value* names (C1248): an object filter's value names
        the held objects whose field equals it, matched by the reference's id (or, a brief with
        no id, its own field); a choice by its ``value``. A list is any of its members, as
        NetBox's multiple-choice filters are, except ``tag``, which NetBox requires all of."""
        wanted = [str(m).strip() for m in _members(value)]
        if (endpoint, key) in CHOICE_FILTERS:
            held = obj.get(key)
            held = held.get("value") if isinstance(held, dict) else held
            return str(held) in wanted
        store, field = OBJECT_FILTERS[endpoint][key]

        def names(one):
            ids = {o.get("id") for o in self.store.get(store, []) if str(o.get(field)) == one}
            for ref in self._refs(endpoint, key, obj):
                if isinstance(ref, dict):
                    if (ref["id"] in ids) if "id" in ref else str(ref.get(field)) == one:
                        return True
                elif ref in ids or str(ref) == one:
                    return True
            return False

        return (all if key == "tag" else any)(names(one) for one in wanted)

    def _matches(self, obj, params, endpoint=""):
        for key, value in (params or {}).items():
            if key in ("limit", "offset", "brief", "depth"):
                continue
            if (key in OBJECT_FILTERS.get(endpoint, {})
                    or (endpoint, key) in CHOICE_FILTERS):      # by what the value names
                if not self._refers(endpoint, key, obj, value):
                    return False
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
            if key == "device_id" and endpoint == "ipam/ip-addresses" \
                    and obj.get("assigned_object_type") == "dcim.interface":
                # The same join for an address the client POSTed (C1344): its interface, by
                # `assigned_object_id`, and that interface's device. A list is any of its
                # members, as NetBox's repeated filter is.
                iface = next((i for i in self.store.get("dcim/interfaces", [])
                              if i.get("id") == obj.get("assigned_object_id")), None)
                held = (iface or {}).get("device")
                held = held.get("id") if isinstance(held, dict) else held
                if str(held) not in {str(m) for m in _members(value)}:
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
                    # A list is any of its members (C1344): NetBox reads a repeated filter
                    # (`?id=1&id=2`, `?device_id=1&device_id=2`) as one of them.
                    wanted = ({str(m) for m in _members(value)}
                              if isinstance(value, (list, tuple, set)) else {str(value)})
                    if str(actual) not in wanted:
                        return False
                    break
            else:
                return False                      # filtered on a field we lack
        return True

    # ── requests.Session surface ────────────────────────────────────────────

    def get(self, url, params=None, timeout=None):
        # A `next` link carries its query in the URL (`?limit=1&offset=1`, as captured): it is
        # read as the request's parameters, as NetBox reads it.
        url, _, query = str(url).partition("?")
        if query:
            from urllib.parse import parse_qsl
            params = dict(parse_qsl(query), **(params or {}))
        endpoint, obj_id = self._parse(url)
        refused = self._negative(obj_id, params)
        if refused is None and obj_id is None:
            refused = self._unknown(endpoint, params) or self._unknown_value(endpoint, params)
        if refused is not None:
            return refused
        items = self.store.get(endpoint, [])
        if obj_id is not None:
            for obj in items:
                if obj["id"] == obj_id:
                    return FakeResponse(self._rendered(endpoint, obj))
            return FakeResponse({"detail": "Not found."}, 404)
        hits = [o for o in items if self._matches(o, params, endpoint)]
        if endpoint == "dcim/interfaces":
            # NetBox renders an interface's `cable` (read-only: the cable terminating on it, or
            # null), computed from the cables held, never stored on the interface (C1344).
            hits = [dict(o, cable=self._cable_brief(o)) for o in hits]
        else:
            hits = [self._rendered(endpoint, o) for o in hits]
        return self._page(url, params, hits)

    @staticmethod
    def _page(url, params, hits):
        """One page of *hits*. With ``limit`` (and ``offset``) NetBox answers that slice, the
        whole ``count``, and a ``next`` link while more remain (measured: the captured cable
        list's ``next`` was ``...?limit=1&offset=1``). Without a limit the fake answers every
        hit at once, as it always has (NetBox's own default page is 50: not modelled)."""
        try:
            limit = int((params or {}).get("limit") or 0)
            offset = int((params or {}).get("offset") or 0)
        except (TypeError, ValueError):
            limit, offset = 0, 0
        if limit <= 0:
            return FakeResponse({"results": hits, "next": None, "count": len(hits)})
        page = hits[offset:offset + limit]
        more = offset + limit < len(hits)
        if more:
            from urllib.parse import urlencode
            rest = {k: v for k, v in (params or {}).items() if k not in ("limit", "offset")}
            nxt = f"{url}?{urlencode(dict(rest, limit=limit, offset=offset + limit), doseq=True)}"
        return FakeResponse({"results": page, "next": nxt if more else None,
                             "previous": None, "count": len(hits)})

    # ── the console model, rendered as NetBox 4.6.9 answers (CONSOLE_ENDPOINTS, above) ──

    def _rendered(self, endpoint, obj):
        """*obj* as a GET answers it: a console port or a cable in its measured shape; any
        other object as stored."""
        if endpoint in CONSOLE_ENDPOINTS:
            return self._console_port(endpoint, obj)
        if endpoint == "dcim/cables":
            return self._cable(obj)
        return obj

    def _device_brief(self, ref):
        ident = ref.get("id") if isinstance(ref, dict) else ref
        dev = next((d for d in self.store.get("dcim/devices", []) if d.get("id") == ident), None)
        if dev is None:
            return None
        return {"description": dev.get("description", ""), "display": dev.get("name", ""),
                "id": dev["id"], "name": dev.get("name", ""),
                "url": f"{_NB}/api/dcim/devices/{dev['id']}/"}

    def _cable_ref(self, cable):
        return {"description": cable.get("description", ""), "display": f"#{cable['id']}",
                "id": cable["id"], "label": cable.get("label", ""),
                "url": f"{_NB}/api/dcim/cables/{cable['id']}/"}

    def _port_brief(self, object_type, object_id):
        """A terminated port's brief, as a cable termination's ``object`` was captured."""
        store = TERMINATION_STORES.get(object_type)
        port = next((p for p in self.store.get(store or "", [])
                     if str(p.get("id")) == str(object_id)), None)
        if port is None:
            return None
        cable = self._cable_on({"object_type": object_type, "object_id": port["id"]})
        return {"_occupied": cable is not None,
                "cable": self._cable_ref(cable) if cable else None,
                "description": port.get("description", ""),
                "device": self._device_brief(port.get("device")),
                "display": port.get("name", ""), "id": port["id"], "name": port.get("name", ""),
                "url": f"{_NB}/api/{store}/{port['id']}/"}

    def _console_port(self, endpoint, port):
        object_type = {"dcim/console-ports": "dcim.consoleport",
                       "dcim/console-server-ports": "dcim.consoleserverport"}[endpoint]
        cable = self._cable_on({"object_type": object_type, "object_id": port["id"]})
        end, peers, peer_type = None, [], None
        if cable is not None:
            mine = any(t.get("object_type") == object_type
                       and str(t.get("object_id")) == str(port["id"])
                       for t in cable.get("a_terminations") or [])
            end = "A" if mine else "B"
            far = cable.get("b_terminations" if mine else "a_terminations") or []
            peers = [b for b in (self._port_brief(t.get("object_type"), t.get("object_id"))
                                 for t in far) if b is not None]
            peer_type = far[0].get("object_type") if far else None
        out = {
            "_occupied": cable is not None,
            "cable": self._cable_ref(cable) if cable else None,
            "cable_end": end,
            "connected_endpoints": peers or None,
            "connected_endpoints_reachable": True if peers else None,
            "connected_endpoints_type": peer_type if peers else None,
            "created": _STAMP, "custom_fields": {},
            "description": port.get("description", ""),
            "device": self._device_brief(port.get("device")),
            "display": port.get("name", ""),
            "display_url": f"{_NB}/{endpoint}/{port['id']}/",
            "id": port["id"], "label": port.get("label", ""), "last_updated": _STAMP,
            "link_peers": peers, "link_peers_type": peer_type,
            "mark_connected": bool(port.get("mark_connected", False)),
            "module": None, "name": port.get("name", ""), "owner": None,
            "speed": None, "tags": list(port.get("tags") or []), "type": None,
            "url": f"{_NB}/api/{endpoint}/{port['id']}/",
        }
        return out

    def _cable(self, cable):
        def ends(terms):
            return [{"object": self._port_brief(t.get("object_type"), t.get("object_id")),
                     "object_id": t.get("object_id"), "object_type": t.get("object_type")}
                    for t in terms or []]

        status = cable.get("status") or "connected"
        if isinstance(status, str):
            status = {"label": CABLE_STATUS_LABELS.get(status, status), "value": status}
        out = {"bundle": None, "color": "", "comments": "", "created": _STAMP,
               "custom_fields": {}, "description": "", "display": f"#{cable['id']}",
               "display_url": f"{_NB}/dcim/cables/{cable['id']}/", "label": "",
               "last_updated": _STAMP, "length": None, "length_unit": None, "owner": None,
               "profile": None, "tags": [], "tenant": None, "type": None,
               "url": f"{_NB}/api/dcim/cables/{cable['id']}/"}
        out.update({k: v for k, v in cable.items() if k in CABLE_FIELDS})
        out.update(a_terminations=ends(cable.get("a_terminations")),
                   b_terminations=ends(cable.get("b_terminations")), status=status)
        return out

    def _cable_brief(self, iface):
        held = self._cable_on({"object_type": "dcim.interface", "object_id": iface.get("id")})
        return None if held is None else {"id": held["id"], "label": held.get("label", "")}

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
        if endpoint in CONSOLE_ENDPOINTS:
            # A component's name is unique on its device (CONSOLE_ENDPOINTS, above).
            dev = payload.get("device")
            dev = dev.get("id") if isinstance(dev, dict) else dev
            for held in self.store.get(endpoint, []):
                mine = held.get("device")
                mine = mine.get("id") if isinstance(mine, dict) else mine
                if str(mine) == str(dev) and held.get("name") == payload.get("name"):
                    return FakeResponse({"__all__": [
                        "A port with this Device and Name already exists."]}, 400)
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
