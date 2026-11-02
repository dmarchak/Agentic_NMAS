"""Shared intent layers (board FC, phase 1; PHASE8_PLAN 22.1; C2283): network, site, role and
tag layers merged under a device's own intent, each value knowing where it came from.

**The merge** (`merge`): in rank order network, site, role, tag, then the device, a later value
wins. Dicts merge recursively; a KEYED list (`KEYS`) merges entry by entry, a later entry with
the same key replacing the earlier one whole; any other value of a later layer replaces an
earlier one unless it is empty (the profile's rule, `profile._overlay`). Two layers of ONE rank
that set one path differently are a conflict, returned by name, never resolved: the caller
refuses (22.1 (5)).

**Provenance:** every leaf and keyed entry the merged document holds names the layer that
supplied it (``from``), so the device's Intent tab and a deploy's preview can say "tag
blind-lab" or "this device" for each value (FC3).

**What a layer may carry** (`problems`): the shared sections only, every list in them keyed;
`interfaces` and `routing` describe one device and are refused, as is a list of entries the key
table does not name, never merged by replacement; a list of plain values (NTP servers) is one
value, a later layer's replacing it whole (22.1 (4)).

**Where they come from** (`read_layers`, `applicable`): the committed files under `layers/` in the
network's intent repository (`network.yml`, `site-<slug>.yml`, `role-<slug>.yml`,
`tag-<slug>.yml`), read at a ref as every reader takes what is committed; a device takes the
network layer and each site, role and tag layer its inventory row names (NetBox's slugs). The
chain that renders reads them through `profile.effective_for` (22.1 (3)); no `layers/` folder
is today's render, unchanged.
"""

import copy
import re

#: Where a network's layers are committed, one file a layer.
LAYERS_DIR = "layers"
_FILE = re.compile(r"^(network|(site|role|tag)-([a-z0-9][a-z0-9_-]*))\.yml$")


from modules.nsot.profile import ProfileRefused


class LayersRefused(ProfileRefused):
    """A layer that cannot be read or merged: its words name the file and why. A render
    refuses by name rather than drawing a device without what its layers say. A
    `ProfileRefused`, so every caller of the one chain (`profile.effective_for`) that refuses
    a broken profile by name refuses a broken layer the same way."""


#: The layers' ranks, in merge order; the device's own document comes last.
RANKS = ("network", "site", "role", "tag")
DEVICE = "this device"

#: Sections a layer may never carry: one device's cabling and adjacencies.
PER_DEVICE_SECTIONS = ("interfaces", "routing")


def _setting_key(entry):
    from modules.nsot import profile
    return profile.KEYED_LISTS["snmp.settings"](entry)


def _field(*names):
    def key(entry):
        if not isinstance(entry, dict):
            return None
        got = tuple(entry.get(n) for n in names)
        return got[0] if len(got) == 1 else got
    return key


#: Every list a layer may carry, by its dotted path, and the key that names an entry.
KEYS = {
    "users": _field("name"),
    "snmp.communities": _field("ref"),
    "snmp.hosts": _field("address"),
    "snmp.settings": _setting_key,
    "vlans": _field("id"),
    "static_routes": _field("family", "spec"),
    "prefix_lists": _field("name"),
    "acls": _field("type", "name"),
    "ip_sla": _field("id"),
    "telemetry": _field("subscription"),
    "tracks": _field("id"),
    "lines": _field("spec"),
}


def _empty(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def problems(doc) -> list:
    """Every reason *doc* cannot be a layer, at once; ``[]`` when it can."""
    if not isinstance(doc, dict):
        return ["a layer is a mapping"]
    out = [f"{s} describes one device, so a layer cannot carry it" for s in PER_DEVICE_SECTIONS
           if s in doc]

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if path == "" and k in PER_DEVICE_SECTIONS:
                    continue
                walk(v, _join(path, str(k)))
        elif isinstance(node, list):
            if path not in KEYS:
                # A list of plain values (NTP servers) is one value, a later layer's replacing
                # it whole; a list of entries no key names cannot merge entry by entry.
                if any(isinstance(e, (dict, list)) for e in node):
                    out.append(f"{path} is a list of entries no key names, so a layer cannot "
                               "merge it entry by entry")
                return
            seen = set()
            for e in node:
                k = KEYS[path](e)
                if k is None or k in seen:
                    out.append(f"{path}: an entry with {'no' if k is None else 'a repeated'} "
                               f"key ({k!r})")
                seen.add(k)
    walk(doc, "")
    return out


def leaves(doc, path: str = "") -> dict:
    """``{dotted path: value}`` for every leaf *doc* sets, a keyed list's entry as one leaf
    (``users[lab]``): what provenance and the same-rank conflict compare."""
    out = {}
    if isinstance(doc, dict):
        for k, v in doc.items():
            out.update(leaves(v, _join(path, str(k))))
    elif isinstance(doc, list) and path in KEYS:
        for e in doc:
            out[f"{path}[{KEYS[path](e)}]"] = e
    elif not _empty(doc):
        out[path] = doc
    return out


def _overlay(base, top, path: str = ""):
    """*top* (a later layer) over *base*: dicts recursively, a keyed list entry by entry (a
    later entry with the same key replaces the earlier one whole, the earlier order kept and
    new keys appended), and any other value of *top* replaces *base*'s unless it is empty."""
    if isinstance(base, dict) and isinstance(top, dict):
        out = dict(base)
        for k, v in top.items():
            p = _join(path, str(k))
            out[k] = _overlay(base[k], v, p) if k in base else copy.deepcopy(v)
        return out
    if path in KEYS and isinstance(base, list) and isinstance(top, list) and top:
        key = KEYS[path]
        later = {key(e): e for e in top}
        kept = [copy.deepcopy(later.pop(key(e), e)) for e in base]
        return kept + [copy.deepcopy(e) for e in top if key(e) in later]
    return copy.deepcopy(base) if _empty(top) else copy.deepcopy(top)


def conflicts(layers: list) -> list:
    """Same-rank layers setting one path differently: ``[{"path", "rank", "layers": [(label,
    value), ...]}]``. *layers* is ``[(rank, label, doc)]``."""
    out = []
    for rank in RANKS:
        mine = [(label, leaves(doc)) for r, label, doc in layers if r == rank]
        paths = sorted({p for _l, flat in mine for p in flat})
        for p in paths:
            said = [(label, flat[p]) for label, flat in mine if p in flat]
            if len(said) > 1 and any(v != said[0][1] for _l, v in said[1:]):
                out.append({"path": p, "rank": rank, "layers": said})
    return out


def merge(layers: list, device_doc: dict) -> dict:
    """The device's merged intent: *layers* (``[(rank, label, doc)]``, any order) in rank
    order, then *device_doc*. ``{"doc", "from": {leaf path: label}, "conflicts", "problems"}``;
    a caller refuses when *conflicts* or *problems* is not empty (both name what they found).
    No layer: the device's document, every leaf from this device."""
    order = sorted((lay for lay in layers), key=lambda lay: RANKS.index(lay[0]))
    bad = [f"{label}: {p}" for _r, label, doc in order for p in problems(doc)]
    out, origin = {}, {}
    for _rank, label, doc in order:
        out = _overlay(out, doc)
        for p in leaves(doc):
            origin[p] = label
    out = _overlay(out, device_doc or {})
    for p in leaves(device_doc or {}):
        origin[p] = DEVICE
    # A leaf the merge no longer holds (a later empty value never replaces, so none) is
    # dropped from the origins only if absent from the result.
    held = leaves(out)
    return {"doc": out, "from": {p: origin.get(p, DEVICE) for p in held},
            "conflicts": conflicts(order), "problems": bad}


def layer_label(rank: str, slug: str = "") -> str:
    """How a layer is named on every screen: "network", "site lab-a", "tag blind-lab"."""
    return rank if rank == "network" else f"{rank} {slug}"


def read_layers(repo: str, ref: str = "HEAD") -> list:
    """The network's committed layers at *ref*: ``[(rank, slug, label, doc)]``, by file name.
    ``[]`` when there is no `layers/` folder (today's networks). A file whose name is not a
    layer's, or that is not YAML, RAISES `LayersRefused` naming it: a render never quietly
    drops what a layer says."""
    import os

    import yaml

    from modules.nsot import repo as R

    # No repository yet (a network born without one) has nothing committed, so no layer: the
    # render is today's, asking git nothing.
    if not repo or not os.path.exists(os.path.join(repo, ".git")):
        return []
    rc, out, err = R.git_raw(repo, "ls-tree", "--name-only", ref, "--", LAYERS_DIR + "/")
    if rc != 0:
        if "Not a valid object name" in (err or "") or "unknown revision" in (err or ""):
            return []                            # a repository with no commit yet
        raise LayersRefused(f"{LAYERS_DIR}/ could not be listed at {ref}: {err or rc}")
    layers = []
    for path in sorted(p for p in out.splitlines() if p.strip()):
        name = path.split("/", 1)[-1]
        m = _FILE.match(name)
        if not m:
            raise LayersRefused(f"{path} is not a layer's name (network.yml, site-, role- or "
                                "tag-<slug>.yml)")
        rc, text, err = R.git_raw(repo, "show", f"{ref}:{path}")
        if rc != 0:
            raise LayersRefused(f"{path} could not be read at {ref}: {err or rc}")
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise LayersRefused(f"{path} is not YAML: {exc}") from exc
        rank = "network" if m.group(1) == "network" else m.group(2)
        slug = m.group(3) or ""
        layers.append((rank, slug, layer_label(rank, slug), doc))
    return layers


def applicable(layers: list, row: dict) -> list:
    """The layers a device takes, ``[(rank, label, doc)]``: the network layer, and each site,
    role and tag layer whose slug its inventory row names (`_site`, `_role_slug` or `role`,
    `_tags`; NetBox's slugs, read with the inventory)."""
    row = row or {}
    site = row.get("_site") or ""
    roles = {r for r in (row.get("_role_slug"), row.get("role")) if r}
    tags = set(row.get("_tags") or [])
    out = []
    for rank, slug, name, doc in layers:
        if (rank == "network" or (rank == "site" and slug == site)
                or (rank == "role" and slug in roles) or (rank == "tag" and slug in tags)):
            out.append((rank, name, doc))
    return out


def for_device(repo: str, row_of, intent: dict, ref: str = "HEAD") -> dict:
    """*intent* with the layers its device takes merged under it (`merge`), or *intent* itself
    when the network has no layer or none applies. *row_of* is called for the device's
    inventory row only when the network has a layer, so a network with none reads no
    inventory. RAISES `LayersRefused` on a conflict or a layer that cannot be one, naming
    each: a render refuses rather than pick between two."""
    layers = read_layers(repo, ref)
    if not layers:
        return intent
    chosen = applicable(layers, row_of())
    if not chosen:
        return intent
    got = merge(chosen, intent)
    why = got["problems"] + [
        f"{c['path']}: " + " and ".join(f"{name} says {value!r}" for name, value in c["layers"])
        for c in got["conflicts"]]
    if why:
        raise LayersRefused("the intent layers cannot be merged: " + "; ".join(why))
    return got["doc"]
