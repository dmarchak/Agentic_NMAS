"""The golden-config read path: where a device's golden is, as committed, and the list of
goldens. Moved out of modules/ai_assistant.py unchanged (2026-10-14): drift, NetBox sync,
onboarding, the deploy plan and the pipeline read goldens through it, and the AI family that
held it is being removed (Phase 7's order: its shared pieces out first). ai_assistant imports
these names back for its own uses until it goes."""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


# One file per device per list — latest known-good startup-config snapshot.

def _get_golden_configs_dir() -> str:
    from modules.config import get_current_list_data_dir
    path = os.path.join(get_current_list_data_dir(), "golden_configs")
    os.makedirs(path, exist_ok=True)
    return path


def _safe_device_name(hostname: str) -> str:
    """Sanitise a hostname into a safe filename component (no dots, slashes, spaces)."""
    import re as _re2
    name = hostname.strip()
    # Replace anything that isn't alphanumeric, dash, or underscore
    name = _re2.sub(r"[^\w\-]", "_", name)
    return name or "unknown"


def _migrate_golden_configs() -> None:
    """
    One-time migration: rename legacy IP-based golden config files
    (e.g. 192_168_0_4.cfg) to hostname-based names (e.g. P1.cfg).
    Reads the hostname from the file header and renames in place.
    Safe to call repeatedly — already-migrated files are ignored.
    """
    import re as _re3
    if _nsot_migrated():
        return          # golden_configs/ is read-only after the migration
    gdir = _get_golden_configs_dir()
    ip_pattern = _re3.compile(r"^\d+_\d+_\d+_\d+\.cfg$")
    for fname in list(os.listdir(gdir)):
        if not ip_pattern.match(fname):
            continue
        fpath = os.path.join(gdir, fname)
        try:
            with open(fpath, encoding="utf-8") as fh:
                first = fh.readline()
            m = _re3.search(r"—\s*(.+?)\s*\((\d[\d.]+)\)", first)
            if not m:
                continue
            hostname = m.group(1).strip()
            safe     = _safe_device_name(hostname)
            new_path = os.path.join(gdir, f"{safe}.cfg")
            if not os.path.exists(new_path):
                os.rename(fpath, new_path)
                logger.info("golden config migrated: %s → %s", fname, f"{safe}.cfg")
        except Exception as exc:
            logger.warning("golden config migration skip %s: %s", fname, exc)


def _nsot_repo_dir() -> str:
    """The current list's NSoT repo."""
    from modules.config import get_current_list_data_dir
    return os.path.join(get_current_list_data_dir(), "config_repo")


def _legacy_header_scan(device_ip: str) -> Optional[str]:
    """Find a golden file by scanning headers for the IP — the pre-Phase-2 way.

    Kept as the last link in the resolution chain for the deprecation release.
    A device whose management IP changed outside NMAS is not in the manifest
    under its new IP, and losing its golden config silently would be worse than
    a slow scan.
    """
    gdir = _get_golden_configs_dir()
    if not os.path.isdir(gdir):
        return None
    for fname in sorted(os.listdir(gdir)):
        if not fname.endswith(".cfg"):
            continue
        fpath = os.path.join(gdir, fname)
        try:
            with open(fpath, encoding="utf-8") as fh:
                header = fh.readline()
            if f"({device_ip})" in header:
                return fpath
        except Exception:
            pass
    return None


def _nsot_migrated() -> bool:
    """True once this list's repo carries the migration marker."""
    try:
        from modules.nsot.migrate import read_marker
        return read_marker(_nsot_repo_dir()) is not None
    except Exception:                          # noqa: BLE001
        return False


#: Devices already reported as resolving through the deprecated header scan.
#: Process-lifetime, deliberately: this is log volume control, not state.
_LEGACY_SCAN_WARNED: set = set()


def _find_golden_config_file(device_ip: str) -> Optional[str]:
    """Locate a device's golden config. Signature unchanged.

    Resolution chain:
      1. manifest by identity (NetBox id / device_uid)
      2. manifest by management IP
      3. legacy header scan in golden_configs/  (deprecated, logs a warning)
      4. None

    Step 3 is the **only** remaining reason to touch ``golden_configs/``, it is
    reached only when the manifest has no entry for the device, and it is
    strictly read-only. Nothing writes there any more: saves go through
    ``repo.save_golden``, and the in-place legacy rename turns itself off once
    the migration marker exists. The old store is a fallback, not a second
    source of truth that could drift against the repo.
    """
    repo = _nsot_repo_dir()

    try:
        from modules.nsot import manifest as _m

        identity = _identity_for_ip(device_ip)
        if identity:
            entry = _m.find_by_identity(repo, identity)
            if entry:
                path = _m.golden_path_for(repo, entry)
                if os.path.exists(path):
                    return path

        _ident, entry = _m.find_by_ip(repo, device_ip)
        if entry:
            path = _m.golden_path_for(repo, entry)
            if os.path.exists(path):
                return path
    except Exception as exc:                   # noqa: BLE001
        logger.debug("golden: manifest lookup failed for %s: %s", device_ip, exc)

    legacy = _legacy_header_scan(device_ip)
    if legacy and device_ip not in _LEGACY_SCAN_WARNED:
        # Once per device per process. This is on the read path for the drift
        # checker and the AI tools, so warning on every call buried the fact
        # in its own repetition -- and the point of the warning is that it
        # names the devices standing between here and deleting the directory.
        _LEGACY_SCAN_WARNED.add(device_ip)
        logger.warning("golden: %s resolved via the legacy header scan — "
                    "golden_configs/ is deprecated and will be removed", device_ip)
    return legacy


def _identity_for_ip(device_ip: str, list_name: str = "") -> str:
    """Stable identity for a device, from *list_name*'s inventory (C498: a caller that holds
    its list passes it; only one with none reads the active list)."""
    try:
        from modules.device import get_current_device_list, load_saved_devices
        from modules.nsot.manifest import identity_for

        if list_name:
            from modules.nsot import listref
            csv_path = listref.resolve(list_name).csv_path
        else:
            _name, csv_path = get_current_device_list()
        for dev in load_saved_devices(csv_path):
            if dev.get("ip") == device_ip:
                return identity_for(dev.get("_netbox_id"), dev.get("device_uid", ""))
    except Exception:                          # noqa: BLE001
        pass
    return ""


def _golden_record(device_ip: str, list_name: str = "") -> dict:
    """The golden for a device AS COMMITTED (C104's consumers), with why not, in
    *list_name*'s repository (C491, C498: drift, onboarding's NetBox record, NetBox sync and
    the deploy plan each hold a list and read the ACTIVE one's goldens; only a caller with no
    list reads the active list).

    ``{"text", "path", "commit", "source", "refused"}``. ``text`` is None both
    when the device has no golden (``refused`` empty) and when one exists and
    is refused (``refused`` names the path and the reason), so a consumer can
    tell "no golden" from "a golden this tool will not use".

    A device the manifest knows is read from ``HEAD`` through
    :func:`repo.committed_golden`: a working-tree edit is ignored and logged,
    and a golden whose last commit did not come through the save path is
    refused. A legacy-only device (``golden_configs/``, outside git, never
    written since the migration) is still read from its file: it has no
    commit to read, and ``legacy_only_goldens()`` is that store's exit.
    """
    from modules.config import get_current_list_name
    named_other = bool(list_name) and list_name != get_current_list_name()
    if not named_other:
        # The legacy store's one-time rename is the ACTIVE list's: a read of another network
        # never writes in the active one's folder (C487's survey).
        _migrate_golden_configs()
    if named_other:
        from modules.nsot import listref
        repo = listref.resolve(list_name).repo_dir
    else:
        repo = _nsot_repo_dir()            # the active list's, named or not
    entry = None
    try:
        from modules.nsot import manifest as _m

        identity = _identity_for_ip(device_ip, list_name if named_other else "")
        if identity:
            entry = _m.find_by_identity(repo, identity)
        if not entry:
            _ident, entry = _m.find_by_ip(repo, device_ip)
        if entry:
            from modules.nsot import repo as _repo
            rel = os.path.relpath(_m.golden_path_for(repo, entry), repo)
            record = _repo.committed_golden(repo, rel)
            record["path"] = rel.replace(os.sep, "/")
            if record["text"] is not None or record["refused"]:
                if record["refused"]:
                    logger.warning("golden: %s refused: %s", device_ip, record["refused"])
                return record
    except Exception as exc:                   # noqa: BLE001
        logger.debug("golden: manifest lookup failed for %s: %s", device_ip, exc)

    # The legacy `golden_configs/` store is the active list's: never read for another one.
    legacy = None if named_other else _find_golden_config_file(device_ip)
    if legacy and not legacy.startswith(repo):
        try:
            with open(legacy, encoding="utf-8") as fh:
                return {"text": fh.read(), "path": legacy, "commit": "",
                        "source": "legacy", "refused": ""}
        except OSError:
            pass
    return {"text": None, "path": "", "commit": "", "source": "", "refused": ""}


def _load_golden_config_file(device_ip: str, list_name: str = "") -> Optional[str]:
    """The committed golden for a device in *list_name* (else the active list), or None (no
    golden, or refused: :func:`_golden_record` says which, and a refusal is logged by path)."""
    return _golden_record(device_ip, list_name)["text"]


def _list_golden_configs() -> list:
    """Metadata for every device in the current list that HAS a golden config.

    **An adapter over the one enumerator**, :func:`modules.nsot.repo.list_goldens`.
    The returned shape is unchanged (``device_ip``, ``hostname``, ``file``,
    ``saved_at``, ``size_bytes``) because seventeen call sites across nine
    modules depend on it -- the drift checker, the event monitor,
    ``check_runner``, ``pipeline_builder``, ``/templatize/report``,
    ``/list/golden_configs`` and six paths in the AI tool layer.

    It used to be ``os.listdir(golden_configs/)`` and nothing else, while
    :func:`_load_golden_config_file` resolved through the manifest. Enumeration
    and content came from different stores, so a device onboarded after the
    migration -- golden in the repo, no legacy file -- was invisible to every
    one of those readers while its config was right there. Fixing the
    enumerator fixes all of them without touching any of them.

    ``saved_at`` is now the commit time rather than the file's mtime. The
    mtime was provably wrong (measured on s1: "2026-09-15 22:35", exactly the
    legacy file's mtime, for a golden committed the same day), and the
    ``! Saved:`` header was removed precisely so a save would not produce a
    diff on every write -- which makes the commit the only honest record.
    """
    from modules.config import get_current_list_name
    from modules.nsot.repo import list_goldens

    try:
        entries = list_goldens(get_current_list_name())
    except Exception as exc:                   # noqa: BLE001
        # Loud, not silent: this function answering "no goldens" is
        # indistinguishable from a fleet that has none, and several callers
        # treat that as nothing to do.
        logger.error("golden: enumeration failed — %s", exc)
        return []

    return [{
        "device_ip":  e["device_ip"],
        "hostname":   e["hostname"],
        "file":       e["file"],
        "saved_at":   e["saved_at"],
        "size_bytes": e["size_bytes"],
        "legacy":     e["legacy"],
    } for e in entries]
