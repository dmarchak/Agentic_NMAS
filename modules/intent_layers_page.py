"""Source of Truth › Intent: a network's intent layers (board FC's FC2; PHASE8_PLAN 22.1 (8)(c);
C2283), read-only in phase 1.

Every layer committed under the network's `layers/` folder, in merge order (network, site,
role, tag), each with the devices it reaches and its values; the chosen one with each value's
reach (the devices whose render takes it, and those whose own value or a later layer's
overrides it), the secret references it names and its file's last commit; and every same-rank
conflict, by path and the devices it stops rendering.

**Scale:** a fixed number of reads whatever the fleet: the layers (one `ls-tree` and a `show`
a layer), the inventory once, and every device's committed intent in two (`neighbours.
committed_intents`); the merge per device is in memory. **An unreadable inventory refuses**
the reach by name: no group is taken from an earlier read (22.1 (2)).
"""

import logging

log = logging.getLogger(__name__)


def layer_key(rank: str, slug: str = "") -> str:
    """A layer's key on this page, its file's stem: ``network``, ``tag-blind-lab``."""
    return "network" if rank == "network" else f"{rank}-{slug}"


def view(ref, chosen: str = "") -> dict:
    """``{"layers": [{"key", "rank", "slug", "label", "file", "devices", "count"}],
    "chosen": {...} or None, "conflicts": [{"path", "layers", "devices"}], "error",
    "inventory_error", "intent_error"}``. *chosen* is a layer's key; the first layer when it
    names none."""
    from modules import neighbours
    from modules.nsot import intent_layers as L
    from modules.nsot import secret_refs
    from modules.redact import redact_text

    out = {"layers": [], "chosen": None, "conflicts": [], "error": "",
           "inventory_error": "", "intent_error": ""}
    try:
        layers = L.read_layers(ref.repo_dir)
    except L.LayersRefused as exc:
        out["error"] = str(exc)
        return out
    if not layers:
        return out
    try:
        from modules.nsot.restore import _devices_of
        rows = [r for r in _devices_of(ref.name) if r.get("hostname")]
    except Exception as exc:                          # noqa: BLE001
        log.warning("intent layers: the inventory of %s could not be read: %s", ref.name, exc)
        out["inventory_error"] = f"{type(exc).__name__}: {exc}"
        rows = []
    docs, out["intent_error"] = neighbours.committed_intents(ref.repo_dir)

    # Each device's merge, in memory: which layers it takes, where each of its values comes from.
    reach, origin, clashes = {}, {}, {}
    for row in rows:
        host = row["hostname"]
        took = L.applicable(layers, row)
        if not took:
            continue
        for _rank, label, _doc in took:
            reach.setdefault(label, []).append(host)
        got = L.merge(took, docs.get(host) or {})
        origin[host] = got["from"]
        for c in got["conflicts"]:
            k = (c["path"], tuple(c["layers"]))
            clashes.setdefault(k, []).append(host)
    out["conflicts"] = [{"path": L.shown_path(p),
                         "layers": [(label, redact_text(L.shown_value(p, v)))
                                    for label, v in said],
                         "devices": sorted(hosts)}
                        for (p, said), hosts in sorted(clashes.items(), key=lambda kv: kv[0][0])]

    for rank, slug, label, doc in layers:
        out["layers"].append({"key": layer_key(rank, slug), "rank": rank, "slug": slug,
                              "label": label, "file": L.layer_file(rank, slug),
                              "devices": sorted(reach.get(label, [])),
                              "count": len(L.leaves(doc))})
    pick = next((lay for lay in out["layers"] if lay["key"] == chosen), out["layers"][0])
    rank, slug, label, doc = next(lay for lay in layers if lay[2] == pick["label"])
    values = []
    for p, v in L.leaves(doc).items():
        hosts = pick["devices"]
        over = {h: origin[h].get(p, L.DEVICE) for h in hosts if origin[h].get(p) != label}
        values.append({"path": L.shown_path(p), "value": redact_text(L.shown_value(p, v)),
                       "edit": p.split("[", 1)[0],
                       "takes": [h for h in hosts if h not in over],
                       "over": sorted(over.items())})
    out["chosen"] = dict(pick, rows=values,
                         refs=sorted(secret_refs._uses(doc).items()),
                         **L.last_change(ref.repo_dir, pick["file"], "HEAD"))
    return out
