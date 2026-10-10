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
progress (R38). Default, the base layer, is never deleted.
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
    ok, msg = device.create_device_list(pv["name"])                           # create
    if not ok:
        raise Refused(msg)
    entry = IS._record({"kind": "network_create", "actor": actor, "actor_verified": verified,
                        "fields": [pv["name"]]})                              # record
    return dict(entry, ok=True, name=pv["name"], folder=pv["folder"])


def _git_count(repo_dir: str, *args) -> int:
    import subprocess

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        return 0
    out = subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True,
                         timeout=60)
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
    out = {"name": name, "devices": devices, "goldens": goldens, "commits": commits,
           "remote": remote, "busy": busy, "refused": busy,
           "goes_to": f"lists_removed/{os.path.basename(folder)}-<the time of the delete>"}
    out["fingerprint"] = _fp(["delete", name, devices, goldens, commits, remote, bool(busy)])
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
    entry = IS._record({"kind": "network_delete", "actor": actor, "actor_verified": verified,
                        "fields": [pv["name"]]})                              # record
    return dict(entry, ok=True, name=pv["name"], said=msg)
