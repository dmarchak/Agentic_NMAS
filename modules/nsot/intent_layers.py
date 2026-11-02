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

import contextlib
import contextvars
import copy
import os
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


#: A fleet change's proposed layer, planned before it is committed (PHASE8_PLAN 22.2 (2)):
#: ``(realpath of the repository, rank, slug, doc)`` or None. Set only by `proposed`, for the
#: duration of one plan in one thread of control; every reader of the layers (the chain's
#: render, the plan's attribution) then sees the network's layers with this one in its place.
_PROPOSED = contextvars.ContextVar("intent_layers_proposed", default=None)


@contextlib.contextmanager
def proposed(repo: str, rank: str, slug: str, doc: dict):
    """Within the block, `read_layers` for *repo* returns its committed layers with the layer
    *rank*/*slug* replaced by *doc* (or added, a new layer): the plan renders what the change
    would commit, through the one chain, without committing it. Nothing is written."""
    token = _PROPOSED.set((os.path.realpath(repo), rank, slug, doc))
    try:
        yield
    finally:
        _PROPOSED.reset(token)


def read_layers(repo: str, ref: str = "HEAD") -> list:
    """The network's committed layers at *ref*: ``[(rank, slug, label, doc)]``, by file name.
    ``[]`` when there is no `layers/` folder (today's networks). A file whose name is not a
    layer's, or that is not YAML, RAISES `LayersRefused` naming it: a render never quietly
    drops what a layer says. Inside `proposed`, the proposed layer stands in its file's place."""
    layers = _committed_layers(repo, ref)
    want = _PROPOSED.get()
    if want is None or not repo or os.path.realpath(repo) != want[0]:
        return layers
    _repo, rank, slug, doc = want
    kept = [lay for lay in layers if (lay[0], lay[1]) != (rank, slug)]
    return kept + [(rank, slug, layer_label(rank, slug), doc)]


def _committed_layers(repo: str, ref: str) -> list:
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


def layer_file(rank: str, slug: str = "") -> str:
    """The committed file a layer lives in: ``layers/network.yml``, ``layers/tag-<slug>.yml``."""
    return f"{LAYERS_DIR}/network.yml" if rank == "network" else f"{LAYERS_DIR}/{rank}-{slug}.yml"


def last_change(repo: str, rel: str, ref: str) -> dict:
    from modules.nsot import repo as R

    rc, out, _err = R.git(repo, "log", "-1", "--format=%H%x09%s", ref, "--", rel)
    sha, _, subject = (out or "").partition("\t") if rc == 0 else ("", "", "")
    return {"sha": sha, "subject": subject}


def shown_path(path: str) -> str:
    """``users[lab]`` as ``users › lab``, ``snmp.settings[location]`` as ``snmp › settings ›
    location``: how the Intent tab names a value (FC3)."""
    return " › ".join(p for p in re.split(r"[.\[\]]+", path) if p)


def shown_value(path: str, value) -> str:
    if isinstance(value, dict):
        key = path.rsplit("[", 1)[-1].rstrip("]") if path.endswith("]") else None
        return " · ".join(f"{k} {v}" for k, v in value.items() if str(v) != key)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def provenance(repo: str, row_of, intent: dict, ref: str = "HEAD") -> dict:
    """Where the device's values come from, for its Intent tab (FC3): ``{"layers": [{"label",
    "file", "sha", "subject"}], "rows": [{"path", "value", "from", "over"}], "own": [section],
    "error"}``. *rows* are the values a layer supplies and the device's own values that override
    a layer's (*over*: ``{"from", "value"}``, the layer's); *own* names the sections only the
    device sets. No layer applies: every list empty, and *row_of* is not called when the network
    has none. A layer that cannot be read or merged is *error*, its words, never a guess."""
    out = {"layers": [], "rows": [], "own": [], "error": ""}
    try:
        layers = read_layers(repo, ref)
        if not layers:
            return out
        row = row_of() or {}
        chosen = applicable(layers, row)
        if not chosen:
            return out
        got = merge(chosen, intent)
        base = merge(chosen, {})
    except LayersRefused as exc:
        out["error"] = str(exc)
        return out
    why = got["problems"] + [c["path"] for c in got["conflicts"]]
    if why:
        out["error"] = "the intent layers cannot be merged: " + "; ".join(why)
        return out
    files = {label: layer_file(rank, slug) for rank, slug, label, _doc in layers}
    out["layers"] = [{"label": label, "file": files[label], **last_change(repo, files[label], ref)}
                     for _rank, label, _doc in sorted(chosen, key=lambda c: RANKS.index(c[0]))]
    merged, mine, theirs = leaves(got["doc"]), leaves(intent or {}), leaves(base["doc"])
    for p, value in merged.items():
        frm = got["from"].get(p, DEVICE)
        if frm != DEVICE:
            out["rows"].append({"path": shown_path(p), "value": shown_value(p, value),
                                "from": frm, "over": None})
        elif p in theirs:
            out["rows"].append({"path": shown_path(p), "value": shown_value(p, value),
                                "from": DEVICE, "over": {"from": base["from"][p],
                                                         "value": shown_value(p, theirs[p])}})
    touched = {p.split(".", 1)[0].split("[", 1)[0] for p in theirs}
    out["own"] = sorted({p.split(".", 1)[0].split("[", 1)[0] for p in mine} - touched)
    return out
