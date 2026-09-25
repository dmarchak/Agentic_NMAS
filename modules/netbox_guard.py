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

import datetime
import hashlib
import json
import logging
import os
import stat
import threading

from modules.config import DATA_DIR, list_slug

log = logging.getLogger(__name__)

#: Tag applied to every object NMAS creates.
MANAGED_TAG = "nmas-managed"
MANAGED_TAG_SLUG = "nmas-managed"

_CREATED_IDS_FILE = os.path.join(DATA_DIR, "netbox_created_ids.json")

#: What NMAS has MODIFIED, which is a different claim from what it created.
#:
#: Deliberately a **separate file**, keyed the same way. The created-id record
#: means *"NMAS created this"* and is one half of removal's `tagged AND
#: recorded` test -- so putting an update in it would make a human's object
#: deletable by NMAS, which is exactly the ownership claim an update must not
#: make. Two files means *"what has NMAS touched here"* is answerable without
#: being confusable with *"what may NMAS remove"*.
#:
#: This exists because the 2026-09-24 address incident was a PATCH:
#: ``_ensure_ip_address()`` moved one object between six devices, the object
#: never disappeared, and so the tag, the created-id record and the census
#: -- every defence there was -- had nothing to report. Weeks of silence.
_MODIFIED_FILE = os.path.join(DATA_DIR, "netbox_modified.json")

#: A before-value that could not be read. **Not** ``None`` and not absent: a
#: field NetBox did not return and a field that was genuinely null are
#: different facts, and the second is a real before-value.
UNKNOWN_BEFORE = "<unknown>"

#: Longest before/after value recorded, measured on the **serialised** form.
#:
#: Measured by SIZE, never by type. The first version capped strings only, so
#: `local_context_data` -- a dict holding a device's whole running config --
#: went in untouched: **113,767 bytes from one sync of ten devices**, two
#: complete configs per device. *Bulk is not evidence*, which the
#: `skipped_drifted` entry proved by carrying a whole device config and
#: neither of the two hashes it had compared; this is the same error inside
#: the fix for a different one.
#:
#: Anything larger is recorded as *changed, this big, this hash* -- which is
#: the finding. The bytes are not.
_MAX_VALUE_BYTES = 200
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
    _write_json_atomic(_CREATED_IDS_FILE, data)


def _write_json_atomic(path: str, data: dict) -> bool:
    """Write *data* to *path* via a temp file and :func:`os.replace`.

    Never ``open(path, "w")``. Truncate-in-place leaves a window in which the
    file is a fragment, and a fragment of either of these records reads as
    **empty** -- which for the created-id record means Remove can no longer
    find objects it created (they become *tagged and unrecorded*, the one
    combination it cannot act on) and for the modified record means *"NMAS
    changed nothing"*. That is how `user_settings.json` erased itself: a
    partial read returned ``{}``, the next write persisted it.
    """
    try:
        from modules.config import open_secure

        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        # 0600 at CREATION, and the temp file carries it so the replace
        # cannot leave a world-readable window.
        with open_secure(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as exc:
        log.error("netbox_guard: could not persist %s: %s",
                  os.path.basename(path), exc)
        return False


#: Fields whose list value is a **set** in NetBox's model, so a different
#: order is not a different value.
#:
#: **Named, never "every list".** Order carries meaning in plenty of places —
#: an ACL, a route-map, a prefix-list — and this project already learned that
#: once for config sections, where `section_is_unordered()` is an allowlist
#: and *order-significant anywhere wins*. The default here is likewise
#: **ordered**, and a field earns its place by being a many-to-many reference,
#: which NetBox returns in whatever order it pleases:
#:
#: * ``tags``          — m2m to tags; reaches a PATCH via the protocol-tag merge
#: * ``tagged_vlans``  — m2m to VLANs on an interface; reaches the interface PATCH
#: * ``object_types``  — m2m to content types on a custom-field definition
#:
#: Cable ``a_terminations``/``b_terminations`` are deliberately absent: they
#: are POST-only today, and a list of dicts needs a stable identity to sort on,
#: which is a different problem from this one.
UNORDERED_LIST_FIELDS = frozenset({"tags", "tagged_vlans", "object_types"})


def _sort_key(value):
    """Total order over mixed scalars, so sorting cannot raise."""
    return (type(value).__name__, repr(value))


def _unordered(field: str, value):
    """*value*, sorted, when *field* is a set rather than a sequence."""
    if field in UNORDERED_LIST_FIELDS and isinstance(value, list):
        return sorted(value, key=_sort_key)
    return value


def _comparable(value):
    """NetBox's nested form reduced to what a payload would carry.

    A PATCH sends ``{"region": 5}``; a GET returns
    ``{"region": {"id": 5, "name": "...", "url": "..."}}``. Comparing those
    raw makes **every** field look changed, so the log would record a
    modification on every no-op sync and stop meaning anything.
    """
    if isinstance(value, dict):
        if "id" in value:
            return value["id"]
        # NetBox renders an ENUM as {"value": x, "label": X} and accepts a
        # bare "x" — so without this an unchanged enum compares unequal and
        # the record logs a change that did not happen. Reachable today:
        # `_ensure_ip_address` PATCHes its whole payload when only the
        # description or VRF differs, and that payload carries `status`.
        # The same churn class as the sync timestamps, living in the
        # comparison itself rather than in a field.
        #
        # Keyed on the exact shape, so an arbitrary dict that happens to have
        # a "value" key is left alone.
        if set(value) <= {"value", "label"} and "value" in value:
            return value["value"]
        return {k: _comparable(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_comparable(v) for v in value]
    return value


def _redact(text: str) -> str:
    """Mask a value on its way into the record. **Fails closed.**

    The log filter fails *open* -- a record that cannot be redacted is written
    unredacted, because a log that silently loses entries is the worse failure
    in the file an operator reaches for when something has already gone wrong.
    **This file is not that file.** Nobody diagnoses an outage from the
    modification record, so a dropped value costs a detail and a leaked one
    costs a credential. It therefore returns a marker rather than the value
    when redaction cannot run.
    """
    try:
        from modules.redact import redact_text
        return redact_text(text)
    except Exception as exc:               # pragma: no cover - defensive
        log.warning("netbox_guard: could not redact a recorded value: %s", exc)
        return "<unredactable — not recorded>"


def _redact_leaves(value):
    """Redact every string inside a structure, leaving the shape intact.

    Per leaf rather than over the serialised blob: positional redaction reads
    config-line syntax, and running it across JSON punctuation would mangle
    the document it is meant to protect.
    """
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, dict):
        return {k: _redact_leaves(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_leaves(v) for v in value]
    return value


def _serialise(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def record_value(value):
    """What is safe to write down for *value*.

    Small values are kept, **redacted**. Large ones become
    ``{summarised, bytes, sha256}`` -- *"changed, 14.2 KB → 15.1 KB, sha
    3f2a… → 9c81…"* is the finding, and it is also the only form that stays
    readable.

    **The hash is of the RAW value, deliberately.** Hashing the masked form
    would make a credential rotation hash-identical to no change at all --
    the one movement most worth noticing, rendered invisible by the masking
    meant to protect it. A truncated digest of a multi-kilobyte config is no
    practical oracle, and a value short enough to be guessable never reaches
    this path: it is under the cap, so it is redacted and stored instead.
    """
    if isinstance(value, dict) and value.get("summarised"):
        return value                      # already a summary; do not re-wrap
    blob = _serialise(value)
    if len(blob) > _MAX_VALUE_BYTES:
        return {
            "summarised": True,
            "bytes": len(blob),
            "sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12],
        }
    return _redact_leaves(value)


def changed_fields(before_obj, payload: dict):
    """What this payload actually changes: ``{field: {before, after}}``.

    ``None`` when *before_obj* is ``None`` -- the object could not be read, so
    what changed is **unknown**, which is not the same as nothing having
    changed. ``{}`` means the payload sets every field to the value it already
    holds, and that is genuinely not a modification.

    **The before is the whole point.** *"NMAS set assigned_object_id to 60"* is
    a fact; *"NMAS moved it from 44 to 60"* is the finding.
    """
    if before_obj is None:
        return None
    out = {}
    for field, after in (payload or {}).items():
        before = (_unordered(field, _comparable(before_obj[field]))
                  if field in before_obj else UNKNOWN_BEFORE)
        now = _unordered(field, _comparable(after))
        if before == now:
            continue
        # COMPARE RAW, RECORD SAFE. The comparison must see the real values
        # or a rotation looks like no change; the record must not carry them.
        out[field] = {"before": record_value(before), "after": record_value(now)}
    return out


def record_modified(list_name: str, endpoint: str, obj_id: int, fields,
                    name: str = "", actor: str = "") -> None:
    """Record that NMAS modified *obj_id*. Does **not** claim it created it.

    *fields* is :func:`changed_fields`' answer: a mapping (recorded), ``{}``
    (nothing changed -- recorded nowhere, because the object's content did not
    move) or ``None`` (the before-state was unreadable, recorded **as
    unknown** so the count cannot quietly omit it).
    """
    if obj_id is None or obj_id < 0:
        return
    if fields == {}:
        return
    endpoint = endpoint.strip("/")
    entry = {
        "id": obj_id,
        "name": name,
        "at": datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # An actor nothing set is named rather than blank: an empty string
        # reads as "nobody", and the truth is "this write carried no
        # identity" -- the same distinction as inconclusive against failed.
        "actor": actor or get_current_actor() or "unattributed",
    }
    if fields is None:
        entry["before_unknown"] = True
        entry["note"] = ("the object could not be read before the write, so "
                         "what changed is unknown")
    else:
        entry["fields"] = fields
    with _file_lock:
        data = _load_modified()
        slug = list_slug(list_name) if list_name else "_unattributed"
        data.setdefault(slug, {}).setdefault(endpoint, []).append(entry)
        _write_json_atomic(_MODIFIED_FILE, data)


def _load_modified() -> tuple:
    """The modified record, or ``{}``. See :func:`read_modified` for the
    version that can say *unreadable*."""
    data, _ = read_modified()
    return data or {}


def read_modified() -> tuple:
    """``(data, None)`` or ``(None, reason)``.

    **Absent and unreadable are different facts.** No file means nothing has
    ever been recorded -- an honest zero. An unreadable file means the count
    is unknown, and a reader told *"0 modified"* in that case has been given
    the most reassuring of the possible answers.
    """
    if not os.path.exists(_MODIFIED_FILE):
        return {}, None
    try:
        with open(_MODIFIED_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        return None, f"{_MODIFIED_FILE} is not readable JSON: {exc}"
    except OSError as exc:
        return None, f"{_MODIFIED_FILE} could not be read: {exc}"
    if not isinstance(data, dict):
        return None, f"{_MODIFIED_FILE} is not a modification record"
    return data, None


def modified_since(since: str = "", list_name: str = "") -> dict:
    """Summarise recorded modifications, optionally after an ISO timestamp.

    ``scope`` says which question was answered: ``since`` when *since* was
    supplied, ``all`` when it was not -- because a baseline with no
    ``taken_at`` cannot scope the answer, and reporting an unscoped count as
    though it were scoped would attribute old modifications to this run.
    """
    data, reason = read_modified()
    if reason:
        return {"ok": False, "reason": reason, "count": 0,
                "unknown_before": 0, "entries": [], "scope": "unknown",
                "total_recorded": 0, "exists": True}

    want = list_slug(list_name) if list_name else ""
    entries = []
    for slug, endpoints in data.items():
        if want and slug != want:
            continue
        for endpoint, rows in (endpoints or {}).items():
            for row in rows:
                if since and (row.get("at") or "") <= since:
                    continue
                entries.append({**row, "endpoint": endpoint, "list": slug})

    entries.sort(key=lambda e: e.get("at") or "")

    # `total_recorded` and `exists` are what stop a zero reading as assurance.
    # "0 modified since the baseline" out of 40 recorded proves the mechanism
    # runs and found nothing in this window. The same zero with NO RECORD AT
    # ALL is the mechanism never having written anything -- which on an
    # install that has run imports means it is not reaching the file, and a
    # bare "0 modified" would be the most reassuring reading of a broken
    # recorder. Same shape as "checked 7 of 9" against a number that reads
    # as complete.
    total = sum(len(rows) for endpoints in data.values()
                for rows in (endpoints or {}).values())
    return {
        "ok": True,
        "reason": "",
        "count": len(entries),
        "unknown_before": sum(1 for e in entries if e.get("before_unknown")),
        "entries": entries,
        "scope": "since" if since else "all",
        "total_recorded": total,
        "exists": os.path.exists(_MODIFIED_FILE),
    }


def sanitise_modified() -> dict:
    """Rewrite the existing record through today's summarisation and masking.

    The first version of this recorder capped strings only, so a sync wrote
    two complete running configs per device -- 113,767 bytes in one run, with
    a device's `secret 9` hash and a `username … password 0` line among them.
    Fixing the writer does nothing about what is already on disk, and *"a
    tightened mode does not undo exposure"* applies to a record as much as to
    a file: this is what makes the existing one safe to keep.

    Kept rather than deleted, because that file holds two genuine findings --
    r6's loopback prefix, and a month-stale config copy the sync refreshed --
    and the summary preserves both. Returns counts; writes nothing when
    nothing changes.
    """
    data, reason = read_modified()
    if reason:
        return {"ok": False, "reason": reason, "entries": 0, "rewritten": 0,
                "bytes_before": 0, "bytes_after": 0}
    if not data:
        return {"ok": True, "reason": "", "entries": 0, "rewritten": 0,
                "bytes_before": 0, "bytes_after": 0}

    before_bytes = len(_serialise(data))
    entries = rewritten = 0
    for endpoints in data.values():
        for rows in (endpoints or {}).values():
            for row in rows:
                entries += 1
                fields = row.get("fields")
                if not fields:
                    continue
                new_fields = {
                    name: {side: record_value(pair.get(side))
                           for side in ("before", "after") if side in pair}
                    for name, pair in fields.items()
                }
                if new_fields != fields:
                    row["fields"] = new_fields
                    rewritten += 1

    after_bytes = len(_serialise(data))

    # ALWAYS write, even with nothing to rewrite.
    #
    # Measured: with `rewritten == 0` the old version returned without
    # touching the file, so a record already within the cap but created
    # group-readable by an older version stayed that way -- and
    # `nmas-check-secret-storage` reports the mode while naming THIS command
    # as the remedy. A refusal whose named remedy does not fix the thing is
    # the "says what to do without saying how to do it right" failure, one
    # step worse: here the remedy runs, reports success, and changes nothing.
    #
    # The write is what tightens the mode, because `os.replace` swaps in the
    # temp file's 0600 inode.
    with _file_lock:
        wrote = _write_json_atomic(_MODIFIED_FILE, data)

    mode = ""
    try:
        mode = oct(stat.S_IMODE(os.stat(_MODIFIED_FILE).st_mode))
    except OSError:
        pass

    return {"ok": True, "reason": "", "entries": entries, "rewritten": rewritten,
            "bytes_before": before_bytes, "bytes_after": after_bytes,
            "written": wrote, "mode": mode}


def get_modified(list_name: str, endpoint: str = "") -> dict:
    """Recorded modifications for *list_name*, optionally one endpoint."""
    data = _load_modified().get(list_slug(list_name), {})
    if endpoint:
        return {endpoint.strip("/"): data.get(endpoint.strip("/"), [])}
    return data


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
    """Attribute writes made inside this block to *list_name*.

    *actor* is optional and only ever **adds** attribution: a block that does
    not name one leaves modifications recorded as ``unattributed``, which is
    what they were. It cannot loosen anything, so its absence is safe -- the
    rule about a default fallback being how a caller bypasses a resolver
    applies to an argument whose absence *weakens a check*.
    """

    def __init__(self, list_name: str, actor: str = ""):
        self.list_name = list_name
        self.actor = actor

    def __enter__(self):
        self._previous = getattr(_local, "list_name", None)
        self._previous_actor = getattr(_local, "actor", None)
        _local.list_name = self.list_name
        if self.actor:
            _local.actor = self.actor
        return self

    def __exit__(self, *exc):
        _local.list_name = self._previous
        _local.actor = self._previous_actor
        return False


def get_current_list() -> str:
    return getattr(_local, "list_name", None) or ""


def get_current_actor() -> str:
    return getattr(_local, "actor", None) or ""


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
