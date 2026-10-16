"""A network's OWN store, and never another's in its place (C487).

Found by the operator, 2026-10-05: Needs attention for a second network (`throwaway`) showed nine
Critical "has drifted" rows naming Default's devices, from a drift check of 2026-08-30, and
"drift checking is switched off for throwaway, by nobody recorded". The drift state's reader
(`drift_check._load_state`) adopted the installation-wide file that predates per-network state
for ANY network whose own file was absent, and WROTE the copy into that network's folder: a new
network was born holding Default's last run and Default's switch.

The rule, for every per-network store:

- a READ of a network that has none of its own says so ("none yet"), never another network's,
  a global file's, or the active network's in its place;
- a WRITE lands only in the named network's own store: `own()` refuses a store with no network
  named, so nothing resolves to "the active one" by default;
- a store kept installation-wide before it became per network is adopted by the ONE network that
  held it then (`LEGACY_OWNER`), and a copy another network took before this rule is read as not
  its own (`without_adopted_copy`), so the next write of that network drops it.
"""

import json
import logging
import os

log = logging.getLogger(__name__)

#: The network that held what the installation kept before its stores were per network: the
#: network a fresh install makes (`device._load_device_lists_config`), which was the active one
#: on every installation those stores were written on. Only it adopts an installation-wide file.
LEGACY_OWNER = "Default"


class NoNetworkNamed(ValueError):
    """A per-network store was asked for with no network named."""


def own(list_name: str, filename: str, *, create: bool = False) -> str:
    """*list_name*'s own *filename*, in its own folder. Refuses an empty name: a store is never
    resolved to the active network, or the installation's, by not naming one. *create* makes the
    folder (a writer); a reader leaves it (C51: a read makes no list)."""
    from modules.config import get_list_data_dir, list_data_path

    name = str(list_name or "").strip()
    if not name:
        raise NoNetworkNamed(f"no network was named for {filename}: a per-network store is "
                             "never the active network's or the installation's in its place")
    return os.path.join(get_list_data_dir(name) if create else list_data_path(name), filename)


def adopts_installation_file(list_name: str) -> bool:
    """Whether *list_name* may adopt the installation-wide copy of a store that predates
    per-network stores: only the network that held it then (`LEGACY_OWNER`)."""
    return str(list_name or "").strip() == LEGACY_OWNER


def without_adopted_copy(list_name: str, data: dict, legacy_path: str,
                         marker: str = "migrated_from") -> dict:
    """*data*, read from *list_name*'s own store, without what it copied from the
    installation-wide file at *legacy_path* when it was not that file's network (before C487
    every network adopted it). The copy carries *marker*; a key whose value is still the
    installation file's own is the copy's and is left out, so the network reads as having none
    of its own. A key the network wrote since (its own run, a person's switch) differs, and
    stays. When the installation file cannot be read, nothing can be compared: the marker alone
    goes, and the caller judges what is left (the drift state keeps a run only when it names its
    network). The owner's data, and data with no marker, are returned unchanged."""
    if not isinstance(data, dict) or marker not in data or adopts_installation_file(list_name):
        return data
    try:
        with open(legacy_path, encoding="utf-8") as fh:
            legacy = json.load(fh)
        if not isinstance(legacy, dict):
            legacy = {}
    except (OSError, ValueError):
        legacy = {}
    kept = {k: v for k, v in data.items()
            if k != marker and not (k in legacy and legacy[k] == v)}
    log.warning("network store: %s holds a copy of %s taken before C487; %d of its key(s) are "
                "the copy's and are not read as its own", list_name,
                os.path.basename(legacy_path), len(data) - len(kept) - 1)
    return kept
