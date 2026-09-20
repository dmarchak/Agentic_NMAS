"""netbox_guard.py

Write safety for NetBox.

Three things live here:

1. **The write gate.** ``netbox_allow_writes`` defaults to off. With it off,
   :func:`assert_writes_allowed` raises and no POST / PATCH / DELETE can reach
   NetBox. ``_nb_post`` / ``_nb_patch`` / ``_nb_delete`` in
   :mod:`modules.netbox_client` are the only write paths, so gating those three
   gates everything.

2. **Dry run.** Inside :func:`dry_run`, those same three helpers record the
   operation they *would* have performed and return a synthetic object instead
   of writing. The sync logic runs unmodified and produces a create/update
   preview. Reads still hit NetBox, which is what makes the preview accurate.

3. **Provenance.** NMAS tags every object it creates ``nmas-managed`` and
   records the ids per device list in ``data/netbox_created_ids.json``.
   Removal deletes only objects in the intersection of those two — never a
   pre-existing region, site, VRF, or device.

Background: ``remove_list_from_netbox`` used to collect devices with
``site_id=`` and delete everything it found, whether NMAS had created it or
not, and that cascade also ran automatically when a device list was deleted.
Against a hand-curated NetBox that is unrecoverable data loss.
"""

import json
import logging
import os
import threading

from modules.config import DATA_DIR, list_slug

log = logging.getLogger(__name__)

#: Tag applied to every object NMAS creates.
MANAGED_TAG = "nmas-managed"
MANAGED_TAG_SLUG = "nmas-managed"

_CREATED_IDS_FILE = os.path.join(DATA_DIR, "netbox_created_ids.json")
_file_lock = threading.Lock()

# Per-thread dry-run state: sync runs on a background thread, so this must not
# be global. None = writes execute normally.
_local = threading.local()


class NetBoxWriteBlocked(RuntimeError):
    """Raised when a write is attempted with ``netbox_allow_writes`` off."""


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def writes_allowed() -> bool:
    """True if the operator has enabled NetBox writes."""
    from modules.settings_schema import get_setting
    return bool(get_setting("netbox_allow_writes", False))


def assert_writes_allowed(operation: str = "write") -> None:
    """Raise :class:`NetBoxWriteBlocked` unless writes are enabled.

    A dry run is always permitted — it performs no write.
    """
    if is_dry_run():
        return
    if not writes_allowed():
        raise NetBoxWriteBlocked(
            f"NetBox {operation} blocked: writes are disabled. "
            "Enable 'Allow writes to NetBox' in Settings → Integrations, or use "
            "the import preview, which asks for confirmation before writing."
        )


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

#: Endpoints excluded from a plan: NMAS's own bookkeeping, not network
#: inventory. The ``nmas-managed`` tag object is created at most once per
#: NetBox and would only be noise in a preview of what is about to change.
PLAN_EXCLUDED_ENDPOINTS = ("extras/tags",)


def params_match(obj: dict, params: dict) -> bool:
    """Approximate NetBox's list filtering against a locally-held object.

    Only needs to be good enough for the get-or-create pattern, which filters on
    ``slug``, ``name``, or a foreign key like ``device_id``.
    """
    for key, value in (params or {}).items():
        if key in ("limit", "offset", "brief", "depth"):
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
            return False        # filtered on a field the object does not carry
    return True


class _DryRunPlan:
    """Collects the operations a dry run would have performed.

    Also holds a **virtual store** of the objects it pretended to create. Without
    it, a get-or-create helper called once per device would miss the object the
    dry run "created" for the previous device and plan a duplicate — so a
    three-device import would preview three manufacturers instead of one.
    """

    def __init__(self):
        self.creates: list = []
        self.updates: list = []
        self.deletes: list = []
        self.virtual: dict = {}
        self._next_id = -1

    def synthetic_id(self) -> int:
        """A negative placeholder id, so callers chaining on ``result['id']`` work."""
        self._next_id -= 1
        return self._next_id

    def add_virtual(self, endpoint: str, obj: dict) -> None:
        """Remember an object this dry run pretended to create."""
        self.virtual.setdefault(endpoint.strip("/"), []).append(obj)

    def find_virtual(self, endpoint: str, params: dict) -> list:
        """Objects this dry run already pretended to create that match *params*."""
        return [o for o in self.virtual.get(endpoint.strip("/"), [])
                if params_match(o, params)]

    def summary(self) -> dict:
        def _counts(items):
            out: dict = {}
            for it in items:
                out[it["endpoint"]] = out.get(it["endpoint"], 0) + 1
            return out
        return {
            "creates": self.creates,
            "updates": self.updates,
            "deletes": self.deletes,
            "create_count": len(self.creates),
            "update_count": len(self.updates),
            "delete_count": len(self.deletes),
            "creates_by_type": _counts(self.creates),
            "updates_by_type": _counts(self.updates),
            "deletes_by_type": _counts(self.deletes),
        }


class dry_run:
    """Context manager putting NetBox writes into preview mode.

    >>> with dry_run() as plan:
    ...     sync_list_to_netbox("Lab", devices)
    >>> plan.summary()["create_count"]
    """

    def __enter__(self) -> _DryRunPlan:
        self.plan = _DryRunPlan()
        self._previous = getattr(_local, "plan", None)
        _local.plan = self.plan
        return self.plan

    def __exit__(self, *exc):
        _local.plan = self._previous
        return False


def is_dry_run() -> bool:
    return getattr(_local, "plan", None) is not None


def current_plan():
    return getattr(_local, "plan", None)


def record_intent(kind: str, endpoint: str, payload: dict = None,
                  obj_id=None, name: str = "") -> None:
    """Record an operation a dry run would have performed."""
    plan = current_plan()
    if plan is None:
        return
    if endpoint.strip("/") in PLAN_EXCLUDED_ENDPOINTS:
        return
    entry = {"endpoint": endpoint.strip("/"), "name": name, "id": obj_id,
             "payload": payload or {}}
    getattr(plan, kind).append(entry)


# ---------------------------------------------------------------------------
# Provenance — what NMAS created
# ---------------------------------------------------------------------------

def _load_created() -> dict:
    if not os.path.exists(_CREATED_IDS_FILE):
        return {}
    try:
        with open(_CREATED_IDS_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("netbox_guard: could not read created-id record: %s", exc)
        return {}


def _save_created(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_CREATED_IDS_FILE), exist_ok=True)
        with open(_CREATED_IDS_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError as exc:
        log.error("netbox_guard: could not persist created-id record: %s", exc)


def record_created(list_name: str, endpoint: str, obj_id: int, name: str = "") -> None:
    """Record that NMAS created *obj_id* at *endpoint* for *list_name*."""
    if not list_name or obj_id is None or obj_id < 0:
        return
    endpoint = endpoint.strip("/")
    with _file_lock:
        data = _load_created()
        slug = list_slug(list_name)
        bucket = data.setdefault(slug, {}).setdefault(endpoint, [])
        if not any(e.get("id") == obj_id for e in bucket):
            bucket.append({"id": obj_id, "name": name})
            _save_created(data)


def get_created(list_name: str, endpoint: str = "") -> dict:
    """Return objects NMAS created for *list_name*, optionally one endpoint."""
    data = _load_created().get(list_slug(list_name), {})
    if endpoint:
        return {endpoint.strip("/"): data.get(endpoint.strip("/"), [])}
    return data


def was_created_by_nmas(list_name: str, endpoint: str, obj_id: int) -> bool:
    """True if NMAS's own record says it created this object."""
    entries = _load_created().get(list_slug(list_name), {}).get(endpoint.strip("/"), [])
    return any(e.get("id") == obj_id for e in entries)


def forget_created(list_name: str, endpoint: str = "", obj_id: int = None) -> None:
    """Drop entries from the created-id record.

    With no endpoint, forgets the whole list — this is what "remove from NMAS's
    records without deleting anything in NetBox" does.
    """
    with _file_lock:
        data = _load_created()
        slug = list_slug(list_name)
        if slug not in data:
            return
        if not endpoint:
            data.pop(slug, None)
        elif obj_id is None:
            data[slug].pop(endpoint.strip("/"), None)
        else:
            ep = endpoint.strip("/")
            data[slug][ep] = [e for e in data[slug].get(ep, []) if e.get("id") != obj_id]
        _save_created(data)


def has_managed_tag(obj: dict) -> bool:
    """True if a NetBox object carries the ``nmas-managed`` tag."""
    for tag in (obj.get("tags") or []):
        if isinstance(tag, dict):
            if tag.get("slug") == MANAGED_TAG_SLUG or tag.get("name") == MANAGED_TAG:
                return True
        elif tag == MANAGED_TAG:
            return True
    return False


# ---------------------------------------------------------------------------
# Which device list a write belongs to
# ---------------------------------------------------------------------------
# The write chokepoints are generic helpers with no notion of a device list, so
# sync_list_to_netbox declares the list for the duration of its run. Thread-local
# because sync runs on a background thread.

class for_list:
    """Attribute writes made inside this block to *list_name*."""

    def __init__(self, list_name: str):
        self.list_name = list_name

    def __enter__(self):
        self._previous = getattr(_local, "list_name", None)
        _local.list_name = self.list_name
        return self

    def __exit__(self, *exc):
        _local.list_name = self._previous
        return False


def get_current_list() -> str:
    return getattr(_local, "list_name", None) or ""


#: Endpoints that accept a ``tags`` field and should carry ``nmas-managed``.
#: ``extras/tags/`` is excluded deliberately — tagging the tag endpoint would
#: recurse through ``_ensure_tag``.
TAGGABLE_ENDPOINTS = (
    "dcim/regions/", "dcim/sites/", "dcim/devices/", "dcim/interfaces/",
    "ipam/vrfs/", "ipam/prefixes/", "ipam/vlans/", "ipam/ip-addresses/",
    "vpn/tunnels/",
)


def is_taggable(endpoint: str) -> bool:
    return endpoint.strip("/") + "/" in TAGGABLE_ENDPOINTS
