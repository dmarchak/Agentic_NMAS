"""nsot/manifest.py

``config_repo/.nsot/manifest.json`` — the identity map for a network's repo.

Devices are keyed on **stable identity**, never on hostname:

* ``nb:<netbox_id>`` for a device that comes from NetBox
* ``uid:<uuid4>``    for a device that comes from a CSV list

That is what lets a rename be a ``git mv`` of the device's golden file rather
than a new file plus an orphaned old one, so ``git log --follow`` keeps working
across renames.

```json
{
  "schema_version": 1,
  "devices": {
    "nb:42": {
      "name": "R1", "mgmt_ip": "…", "netbox_id": 42,
      "platform": "cisco_iosxe", "golden": "golden/R1.cfg",
      "pending_rename": null
    }
  }
}
```

**Inventory refresh never writes to git.** A refresh that notices a renamed
device records ``pending_rename`` here and stops. The ``git mv`` happens at the
next :func:`modules.nsot.repo.save_golden`, or when the operator runs "Sync
device names to repo". Reads resolve through the manifest while a rename is
pending, so the golden config stays reachable under either name.
"""

import calendar
import json
import logging
import os
import threading
import time
import uuid

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
_MANIFEST_REL = os.path.join(".nsot", "manifest.json")
_locks: dict = {}
_locks_guard = threading.Lock()


def _lock_for(repo: str) -> threading.Lock:
    with _locks_guard:
        if repo not in _locks:
            _locks[repo] = threading.Lock()
        return _locks[repo]


def manifest_path(repo: str) -> str:
    return os.path.join(repo, _MANIFEST_REL)


def identity_for(netbox_id=None, device_uid: str = "") -> str:
    """Build a manifest key from whichever stable identifier exists."""
    if netbox_id not in (None, ""):
        return f"nb:{netbox_id}"
    if device_uid:
        return device_uid if device_uid.startswith("uid:") else f"uid:{device_uid}"
    return ""


def new_device_uid() -> str:
    """Mint a local identity for a CSV device."""
    return f"uid:{uuid.uuid4()}"


def load(repo: str) -> dict:
    path = manifest_path(repo)
    if not os.path.exists(path):
        return {"schema_version": SCHEMA_VERSION, "devices": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        log.error("manifest: unreadable at %s (%s) — starting empty", path, exc)
        return {"schema_version": SCHEMA_VERSION, "devices": {}}
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("devices", {})
    return data


def save(repo: str, data: dict) -> None:
    path = manifest_path(repo)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


#: A device onboarded but not yet reached. Past this it is **flagged**, not
#: merely listed.
#:
#: 24 hours, because the gap between phase 1 and phase 2 is one human action
#: -- write the generated config into the topology and boot the node -- and a
#: C8000v boots in about six and a half minutes. Within a session that is
#: minutes; across a maintenance window, hours. **A device still pending
#: after a working day means the plan changed or it was forgotten**, and
#: neither is visible from a count. An hour is normal and must not draw
#: attention, or the flag stops meaning anything.
PENDING_OVERDUE_SECONDS = 24 * 3600

#: Past this it is almost certainly abandoned, and the banner offers the
#: abandon action inline rather than making the operator go and find it.
PENDING_STALE_SECONDS = 7 * 24 * 3600


def upsert_device(repo: str, identity: str, name: str, mgmt_ip: str = "",
                  netbox_id=None, platform: str = "", golden: str = "",
                  pending: bool = False, clab_lab: str = "") -> dict:
    """Record or update a device. Returns its manifest entry.

    *pending* marks a device **onboarded but never reached**: it stamps
    ``onboarded_at`` once and sets ``verified_at`` to ``None``. See
    :func:`mark_verified` for the exit, which is the only thing that makes
    this a state rather than a trap.

    **Both timestamps are written once and never touched again**, which is
    what keeps the rule above them intact: there is deliberately no
    ``last_seen`` here, because a timestamp touched on every call would
    produce a one-line diff on every inventory refresh and make the
    migration non-idempotent. These two are set by onboarding and by
    promotion, each exactly once, and no refresh path writes either.
    """
    if not identity:
        raise ValueError("a manifest entry needs a stable identity")
    with _lock_for(repo):
        data = load(repo)
        entry = data["devices"].get(identity, {})
        entry.update({
            "name":      name or entry.get("name", ""),
            "mgmt_ip":   mgmt_ip or entry.get("mgmt_ip", ""),
            "netbox_id": netbox_id if netbox_id is not None else entry.get("netbox_id"),
            "platform":  platform or entry.get("platform", ""),
            "golden":    golden or entry.get("golden", f"golden/{name}.cfg"),
        })
        # WRITTEN ONLY WHEN SUPPLIED, so the nine devices that predate the
        # setting keep no key at all and resolve to the lab named `default`.
        # An absent value is "the default lab", not "unknown" -- a device
        # whose lab nobody has stated is in the one everything was in before
        # labs were a concept.
        if clab_lab:
            entry["clab_lab"] = clab_lab
        # Deliberately no "last_seen" here. The manifest is version-controlled,
        # so a timestamp touched on every call would produce a one-line diff on
        # every refresh and make the migration non-idempotent. Freshness is
        # runtime state and lives in the (gitignored) inventory cache.
        entry.setdefault("pending_rename", None)
        if pending and not entry.get("onboarded_at"):
            entry["onboarded_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                  time.gmtime())
            entry.setdefault("verified_at", None)
        data["devices"][identity] = entry
        save(repo, data)
        return entry


# ---------------------------------------------------------------------------
# Platform, from the inventory source
# ---------------------------------------------------------------------------

def inventory_index(list_name: str) -> dict:
    """``{mgmt_ip | lowercase hostname: {platform, netbox_id}}`` for a list.

    The inventory — a CSV ``platform`` column for local lists, the NetBox
    platform slug for NetBox lists — is the only thing that knows which config
    dialect a device speaks. A ``.cfg`` file cannot tell you whether the box is
    a C8000v or a vIOS-L2, so migration must not try to infer it from one.

    Reads the dispatch layer, which never does network I/O: a NetBox list is
    served from its cache.
    """
    try:
        from modules.config import get_list_data_dir
        from modules.device import load_saved_devices
        from modules.nsot.platform import platform_for_device
    except ImportError:
        return {}

    try:
        csv_path = os.path.join(get_list_data_dir(list_name), "devices.csv")
        devices = load_saved_devices(csv_path)
    except Exception as exc:                   # noqa: BLE001
        log.debug("manifest: inventory unavailable for '%s': %s", list_name, exc)
        return {}

    index = {}
    for dev in devices:
        record = {"platform": platform_for_device(dev),
                  "netbox_id": dev.get("_netbox_id"),
                  "device_uid": dev.get("device_uid", "")}
        ip = (dev.get("ip") or "").strip()
        name = (dev.get("hostname") or "").strip().lower()
        if ip:
            index[ip] = record
        if name:
            index.setdefault(name, record)
    return index


def sync_platforms(repo: str, list_name: str) -> dict:
    """Refresh every manifest entry's platform from the inventory.

    Called whenever the inventory changes — a NetBox refresh, a devices.csv
    rewrite — not only at migration time. A platform can be corrected after the
    fact, and Phase 4 onboarding reads it from the manifest, so a stale value
    here is a wrong answer given confidently.

    Manifest-only: no repo lock, no commit. The next ``save_golden`` carries it.
    """
    if not os.path.isdir(repo):
        return {"ok": True, "updated": [], "unchanged": 0}

    index = inventory_index(list_name)
    if not index:
        return {"ok": True, "updated": [], "unchanged": 0}

    updated, unchanged = [], 0
    with _lock_for(repo):
        data = load(repo)
        for identity, entry in data["devices"].items():
            record = (index.get((entry.get("mgmt_ip") or "").strip())
                      or index.get((entry.get("name") or "").strip().lower()))
            if not record:
                continue
            resolved = record.get("platform", "")
            if not resolved:
                continue
            if entry.get("platform") == resolved:
                unchanged += 1
                continue
            updated.append({"name": entry.get("name", ""),
                            "from": entry.get("platform", ""), "to": resolved})
            entry["platform"] = resolved
        if updated:
            save(repo, data)

    if updated:
        log.info("manifest: platform updated for %d device(s) in '%s'",
                 len(updated), list_name)
    return {"ok": True, "updated": updated, "unchanged": unchanged}


def record_pending_rename(repo: str, identity: str, new_name: str) -> dict:
    """Note that a device has been renamed, without touching git.

    Called from the inventory refresh, which runs on a background thread and
    must never take the repo lock or create a commit.
    """
    with _lock_for(repo):
        data = load(repo)
        entry = data["devices"].get(identity)
        if entry is None:
            return {"ok": False, "error": f"unknown device identity '{identity}'"}
        old_name = entry.get("name", "")
        if old_name == new_name:
            entry["pending_rename"] = None
            save(repo, data)
            return {"ok": True, "changed": False}
        entry["pending_rename"] = {"from": old_name, "to": new_name,
                                   "noticed_at": time.time()}
        save(repo, data)
    log.info("manifest: pending rename %s → %s (identity %s) — git mv deferred",
             old_name, new_name, identity)
    return {"ok": True, "changed": True, "from": old_name, "to": new_name}


def pending_renames(repo: str) -> list:
    """Renames noticed but not yet applied to the repo."""
    out = []
    for identity, entry in load(repo)["devices"].items():
        pending = entry.get("pending_rename")
        if pending:
            out.append({"identity": identity, **pending})
    return out


def clear_pending_rename(repo: str, identity: str, new_name: str,
                         new_golden: str) -> None:
    """Mark a rename as applied to the repo."""
    with _lock_for(repo):
        data = load(repo)
        entry = data["devices"].get(identity)
        if entry is None:
            return
        entry["name"] = new_name
        entry["golden"] = new_golden
        entry["pending_rename"] = None
        save(repo, data)


# ---------------------------------------------------------------------------
# Resolution — the fallback chain
# ---------------------------------------------------------------------------

def find_by_identity(repo: str, identity: str):
    return load(repo)["devices"].get(identity)


def find_by_ip(repo: str, mgmt_ip: str):
    """Resolve by management IP. Returns ``(identity, entry)`` or ``(None, None)``."""
    if not mgmt_ip:
        return None, None
    for identity, entry in load(repo)["devices"].items():
        if entry.get("mgmt_ip") == mgmt_ip:
            return identity, entry
    return None, None


def find_by_name(repo: str, name: str):
    """Resolve by current name, or by a pending rename in either direction.

    While a rename is pending the golden file is still on disk under the old
    name, so both names must resolve or the config would appear to vanish.
    """
    if not name:
        return None, None
    lowered = name.lower()
    for identity, entry in load(repo)["devices"].items():
        if (entry.get("name") or "").lower() == lowered:
            return identity, entry
        pending = entry.get("pending_rename") or {}
        if lowered in ((pending.get("from") or "").lower(),
                       (pending.get("to") or "").lower()):
            return identity, entry
    return None, None


def golden_path_for(repo: str, entry: dict) -> str:
    """Absolute path of a device's golden file, honouring a pending rename.

    While a rename is pending the file has not moved yet, so the on-disk path is
    still the one recorded in ``golden``.
    """
    return os.path.join(repo, entry.get("golden", ""))


def references(repo: str, identity: str, list_name: str = "") -> list:
    """Everything that still names this device, with how to clear each.

    **Checked, not assumed.** Each entry is
    ``{"kind", "what", "how_to_clear"}`` and the list is what
    :func:`release` refuses on.

    The order matches the abandon sequence, so an operator reading a refusal
    is reading the steps in the order they must be taken.
    """
    import os

    entry = load(repo)["devices"].get(identity) or {}
    name = entry.get("name", "")
    found = []
    if not name:
        return found

    # ON DISK **OR** AT HEAD. Checking only the working tree was wrong in
    # exactly the way this function exists to prevent: abandon deletes the
    # file and then commits, so a commit that failed left no file and a
    # committed artefact — and `release()` would hand the name back while
    # HEAD still carried the device's intent. Found by the test written for
    # the discarded `git()` return value, which is the defect one layer up.
    for kind, rel in (("intent", os.path.join("host_vars", f"{name}.yml")),
                      ("golden", os.path.join("golden", f"{name}.cfg"))):
        on_disk = os.path.exists(os.path.join(repo, rel))
        at_head = False
        if not on_disk:
            try:
                from modules.nsot import repo as _repo

                rc, _out, _err = _repo.git(
                    repo, "cat-file", "-e",
                    "HEAD:" + rel.replace(os.sep, "/"))
                at_head = rc == 0
            except Exception:                  # noqa: BLE001
                # A check that could not run has not passed.
                at_head = True
        if on_disk or at_head:
            found.append({
                "kind": kind,
                "what": rel + ("" if on_disk else " (committed at HEAD)"),
                "how_to_clear": "abandon removes it and commits the removal"})

    if list_name:
        try:
            from modules import netbox_guard

            created = netbox_guard.get_created(list_name) or {}
            hits = [e for e in created.get("dcim/devices", [])
                    if (e.get("name") or "").lower() == name.lower()]
            if hits:
                found.append({
                    "kind": "netbox",
                    "what": f"dcim/devices id {hits[0].get('id')}",
                    "how_to_clear": "abandon runs the provenance-based "
                                    "removal for this device"})
        except Exception as exc:               # noqa: BLE001
            # A check that could not run has not passed -- the same rule the
            # plan applies to its collision checks.
            found.append({"kind": "netbox", "what": "could not be checked",
                          "how_to_clear": f"resolve first: {exc}"})

    mgmt_ip = entry.get("mgmt_ip", "")
    if mgmt_ip:
        try:
            from modules import credentials

            if credentials.has_device_override(mgmt_ip):
                found.append({
                    "kind": "credential", "what": f"device override {mgmt_ip}",
                    "how_to_clear": "abandon clears it"})
        except Exception as exc:               # noqa: BLE001
            found.append({"kind": "credential", "what": "could not be checked",
                          "how_to_clear": f"resolve first: {exc}"})

    return found


def release(repo: str, identity: str, list_name: str = "",
            actor: str = "") -> dict:
    """Give a device name back. **Refuses while anything still names it.**

    A name that can be taken and never given back means one typo permanently
    consumes a hostname: `_name_in_manifest` then blocks the wizard from
    re-onboarding it, and nothing anywhere removes the entry. That turned a
    failed onboarding from annoying into unrecoverable.

    **It refuses rather than warning.** "You must clear these first" is
    actionable; "released, and by the way three things still reference it"
    is a note nobody reads, and it would leave the hostname free while a
    commit and a NetBox object still named the old device -- a wrong thing
    wearing a working result.

    So the refusal is the CHECK THAT ABANDON WORKED, not an obstacle to
    routine use: `abandon_onboarding()` removes the artefacts and then calls
    this, and a refusal here means the sequence did not finish.

    Returns ``{"ok", "released", "references", "error"}``.
    """
    entry = load(repo)["devices"].get(identity)
    if entry is None:
        return {"ok": False, "error": f"no device with identity '{identity}'",
                "references": []}

    blocking = references(repo, identity, list_name)
    if blocking:
        return {"ok": False, "released": "", "references": blocking,
                "error": ("%s still referenced by %d artefact(s): %s"
                          % (entry.get("name", identity), len(blocking),
                             ", ".join(f"{r['kind']} ({r['what']})"
                                       for r in blocking)))}

    with _lock_for(repo):
        data = load(repo)
        removed = data["devices"].pop(identity, None)
        if removed is None:
            return {"ok": False, "error": "released by another caller",
                    "references": []}
        save(repo, data)

    log.info("manifest: released identity %s (%s) by %s",
             identity, removed.get("name", ""), actor or "unknown")
    return {"ok": True, "released": removed.get("name", ""),
            "identity": identity, "references": []}


def mark_verified(repo: str, identity: str, actor: str = "") -> dict:
    """The exit from pending: the tool has reached this device.

    **A state with no exit is a name with no release.** Pending was added
    only once this existed, because a flag an operator cannot clear is the
    trap that was just removed from the identity map wearing a new name.

    Written once. A device that has been reached stays reached; if it later
    stops answering that is drift or an outage, which the drift checker and
    the ping worker already report. Re-stamping it here would turn a
    provenance record into a liveness one and put a diff in the manifest on
    every poll.
    """
    with _lock_for(repo):
        data = load(repo)
        entry = data["devices"].get(identity)
        if entry is None:
            return {"ok": False, "error": f"no device with identity '{identity}'"}
        if entry.get("verified_at"):
            return {"ok": True, "already": True,
                    "verified_at": entry["verified_at"]}
        entry["verified_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        save(repo, data)
    log.info("manifest: %s verified by %s", identity, actor or "unknown")
    return {"ok": True, "already": False, "verified_at": entry["verified_at"]}


def _age_seconds(stamp: str) -> int:
    if not stamp:
        return 0
    try:
        parsed = time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return 0
    return max(0, int(time.time() - calendar.timegm(parsed)))


def pending_devices(repo: str) -> list:
    """Devices onboarded and never reached, **with their age and state**.

    The wrong-and-looks-right state for a pending flag is *pending for ever
    and nobody notices*, so a count is not enough and neither is a list: the
    caller gets `age_seconds` and a `state` of ``in_flight`` /
    ``overdue`` / ``stale``, and the banner is required to distinguish them.
    A row that has sat for a week must not look like one added a minute ago.
    """
    out = []
    for identity, entry in (load(repo)["devices"] or {}).items():
        if not entry.get("onboarded_at") or entry.get("verified_at"):
            continue
        age = _age_seconds(entry["onboarded_at"])
        if age >= PENDING_STALE_SECONDS:
            state = "stale"
        elif age >= PENDING_OVERDUE_SECONDS:
            state = "overdue"
        else:
            state = "in_flight"
        out.append({"identity": identity, "name": entry.get("name", ""),
                    "mgmt_ip": entry.get("mgmt_ip", ""),
                    "onboarded_at": entry["onboarded_at"],
                    "age_seconds": age, "state": state})
    return sorted(out, key=lambda r: -r["age_seconds"])
