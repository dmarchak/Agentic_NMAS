"""Creating and deleting a network on v2 (board I's pattern; networks live in Settings, the
operator's decision 3 of 2026-10-05). Each is a preview, a confirm bound to it, and a record in the
installation's settings record, as a verified person.

**Create** (`CREATE_STEPS`): the name is checked as the folder it derives (`device.list_name_refusal`:
a name whose folder another network uses, or that exists on disk unregistered, is refused, C639),
then the network is registered with an empty inventory on this host, inheriting every group of
settings from Default; its own settings page offers the rest.

**Delete** (`DELETE_STEPS`): the preview counts what the network holds (devices, committed goldens,
commits, its remote) and says where the data goes; the confirm takes the network's name typed and
the preview's fingerprint. Its folder is MOVED to ``lists_removed/<folder>-<UTC>``, never erased,
inside its repository lock, refused while any of its devices is held or its drift run is in
progress (R38). Default, the base layer, is never deleted. Its record names the folder the data
went to.

**Deleted stays deleted** (C1029, C1074): `is_deleted` is the one answer to "was this network
deleted, and is it not one now" (unregistered, its folder moved aside), and `deletion` is what
its page says (when, by whom, where the data is). `listref.exists` and the folder accessor
(`config.get_list_data_dir`) ask it, so a folder something leaves at a deleted network's path
neither makes it a network again nor is made by the accessor.
"""

import hashlib
import json
import logging
import os

log = logging.getLogger(__name__)

CREATE_STEPS = ("check", "create", "record")
DELETE_STEPS = ("check", "move", "unregister", "record")


class Refused(ValueError):
    """Nothing was done; the message names what was compared."""


def _fp(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def create_preview(name: str) -> dict:
    """``{"name", "folder", "refused", "fingerprint"}``: what Create would make; writes nothing."""
    from modules import device
    from modules.config import list_slug

    name = (name or "").strip()
    why = device.list_name_refusal(name)
    return {"name": name, "folder": f"lists/{list_slug(name)}" if name else "",
            "refused": why, "fingerprint": _fp(["create", name, why])}


def create(name: str, fingerprint: str, actor: str, verified: str) -> dict:
    """Create the network as previewed. Raises `Refused` naming what moved or why not."""
    from modules import device
    from modules import installation_settings as IS

    pv = create_preview(name)                                                 # check
    if pv["refused"]:
        raise Refused(pv["refused"])
    if fingerprint != pv["fingerprint"]:
        raise Refused(f"the preview is out of date (preview {fingerprint}, now "
                      f"{pv['fingerprint']}): preview again")
    ok, msg = device.create_device_list(pv["name"], actor=actor)              # create
    if not ok:
        raise Refused(msg)
    entry = IS._record({"kind": "network_create", "actor": actor, "actor_verified": verified,
                        "fields": [pv["name"]]})                              # record
    return dict(entry, ok=True, name=pv["name"], folder=pv["folder"])


def _git_count(repo_dir: str, *args) -> int:
    from modules.nsot.repo import run_git

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        return 0
    out = run_git(repo_dir, *args, timeout=60)
    if out.returncode != 0:
        return 0
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    return int(lines[0]) if args[:1] == ("rev-list",) and lines else len(lines)


def delete_preview(name: str) -> dict:
    """What deleting *name* would remove from every page, and where its data would go; writes
    nothing. ``{"name", "devices", "goldens", "commits", "remote", "busy", "refused",
    "goes_to", "fingerprint"}``."""
    from modules import device
    from modules import list_settings as L
    from modules.config import list_data_path
    from modules.nsot import listref
    from modules.nsot import remote as R

    name = (name or "").strip()
    if not listref.exists(name):
        raise Refused(f"there is no network {name!r}")
    if L.is_default(name):
        return {"name": name, "refused": "Default is the base layer every inheriting network "
                "takes its settings from: it is never deleted", "fingerprint": ""}
    folder = list_data_path(name)
    csv_path = os.path.join(folder, "devices.csv")
    devices = len(device.load_saved_devices(csv_path)) if os.path.exists(csv_path) else 0
    repo = os.path.join(folder, "config_repo")
    goldens = _git_count(repo, "ls-tree", "--name-only", "HEAD", "golden/")
    commits = _git_count(repo, "rev-list", "--count", "HEAD")
    config, unreadable = R.config_or_refusal(name)
    remote = (f"{config.get('owner')}/{config.get('repo')}" if config else
              ("its remote record cannot be read" if unreadable else ""))
    busy = device._list_busy(name)
    # C645: a NetBox network whose devices take their logins from this one loses them with it
    # (today's delete warned through /inventory/dependents; v2's said nothing).
    from modules.inventory.source_config import lists_depending_on
    dependents = lists_depending_on(name)
    out = {"name": name, "devices": devices, "goldens": goldens, "commits": commits,
           "remote": remote, "busy": busy, "refused": busy, "dependents": dependents,
           "goes_to": f"lists_removed/{os.path.basename(folder)}-<the time of the delete>"}
    out["fingerprint"] = _fp(["delete", name, devices, goldens, commits, remote, bool(busy),
                              dependents])
    return out


def delete(name: str, typed: str, fingerprint: str, actor: str, verified: str) -> dict:
    """Delete the network as previewed: its name typed exactly, the preview's fingerprint."""
    from modules import device
    from modules import installation_settings as IS

    pv = delete_preview(name)                                                 # check
    if pv["refused"]:
        raise Refused(pv["refused"])
    if (typed or "").strip() != pv["name"]:
        raise Refused(f"the name typed was {(typed or '').strip()!r}; to delete it, type "
                      f"{pv['name']!r} exactly")
    if fingerprint != pv["fingerprint"]:
        raise Refused(f"what the network holds changed since the preview (preview {fingerprint}, "
                      f"now {pv['fingerprint']}): preview again")
    ok, msg = device.delete_device_list(pv["name"])                           # move, unregister
    if not ok:
        raise Refused(msg)
    from modules.config import list_slug

    moved = device.removed_folders(list_slug(pv["name"]))
    entry = IS._record({"kind": "network_delete", "actor": actor, "actor_verified": verified,
                        "fields": [pv["name"]],                               # record
                        "folder": _data_relative(moved[-1]) if moved else ""})
    return dict(entry, ok=True, name=pv["name"], said=msg)


def _data_relative(path: str) -> str:
    """*path* as the delete's own words name it: relative to the folder holding ``lists/``
    (``lists_removed/<folder>-<UTC>``)."""
    from modules import config

    return os.path.relpath(path, os.path.dirname(config.LISTS_DIR))


def is_deleted(name: str) -> bool:
    """Is *name* a network that was deleted and is not one now: not registered, its folder
    moved aside under ``lists_removed/``? Reads the registry and the names of the moved-aside
    folders, nothing else, and creates nothing: the folder accessor asks it
    (`config.get_list_data_dir`), and so does `listref.exists`, so a folder a read or a write
    left at a deleted network's path since (C1074) never brings the network back."""
    from modules import device
    from modules.config import list_slug
    from modules.nsot import listref

    name = str(name or "").strip()
    # The moved-aside folders first: the registry's reader makes Default's folder on a fresh
    # install through the accessor that asks this, and a name never deleted (Default's) has
    # none, so the registry is read only for a name that was.
    if not name or not device.removed_folders(list_slug(name)):
        return False
    registry = listref._registry()
    return not (name in registry or list_slug(name) in registry.values())


def deletion(name: str) -> dict:
    """``{}``, unless *name* is a network that was DELETED and is not one now (C1029): not
    registered, and its folder moved aside under ``lists_removed/`` (the delete's own act, by
    either interface). Then ``{"name", "folder", "at", "by", "recorded"}``: *folder* the newest
    one moved aside for its folder's name, relative to the data folder; *at* the delete's time
    (its record's, else the folder's UTC stamp); *by* who, from the installation's settings
    record (``""`` when the delete recorded none, as today's page's did not). Creates nothing."""
    import re

    from modules import device
    from modules import installation_settings as IS
    from modules.config import list_slug

    name = str(name or "").strip()
    if not is_deleted(name):
        return {}
    folder = _data_relative(device.removed_folders(list_slug(name))[-1])
    stamp = re.search(r"-(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z(?:-\d+)?$", folder)
    out = {"name": name, "folder": folder, "by": "", "recorded": False,
           "at": "{}-{}-{}T{}:{}:{}Z".format(*stamp.groups()) if stamp else ""}
    got = IS.changes(kinds=("network_delete",))
    for r in got.get("rows") or []:                                       # newest first
        if (r.get("fields") or [""])[0] != name:
            continue
        # The record of THIS delete: it names the folder (since C1029), or, written before it
        # named one, it is the newest delete of this name.
        if r.get("folder") in (None, "", folder):
            out.update(by=r.get("actor_label") or r.get("actor") or "", recorded=True,
                       at=r.get("at_iso") or out["at"])
        break
    return out
