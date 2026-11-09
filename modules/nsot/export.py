"""The NSOT snapshot export (the SDN platform design revision 6, section 5, C): what NetBox says
about a network at a moment, as one deterministic JSON document kept in the network's own NSoT
repository, so every plan made from it reads the same bytes, offline, and names their hash.

**The format** (`SCHEMA_VERSION`): ``{"schema_version", "network", "netbox_version", "sha256",
"body"}``, serialised with sorted keys, two-space indent and one trailing newline. The body holds
the objects a network's features read, each projected to its declared fields (`_device`,
`_interface`, `_vlan`, `_prefix`, `_service`, `_cable`), and every list sorted by its natural key:

- ``devices`` by name: id, status, role, platform, site, device type, primary and OOB addresses,
  custom fields, tags and the RENDERED config context;
- ``interfaces`` by device then name: type, enabled, ``mgmt_only``, mode, untagged and tagged
  VLANs, parent, LAG and bridge, tags, custom fields (``openflow_port`` among them) and
  addresses;
- ``vlans`` by site then VID; ``prefixes`` by prefix; ``services`` by parent then name; and
  ``cables`` by their two ends;
- ``hosts`` by name (C2776, 2026-11-09): every device tagged ``mercury-end-host`` (`HOST_TAG`)
  at one of the network's sites, read by its tag whatever the list's filters, and never one of
  ``devices`` (so never managed, polled or protected as a device): its id, site, status, role
  and tags, and each interface's MAC, addresses and the far end of its cable (``attached``).
  `host_ports` resolves each to its switch's DPID and the port's OpenFlow number, naming a
  value NetBox does not record. A document from before the kind has no ``hosts`` key, which
  `hosts_of` answers as None (not recorded), never as no hosts.

**Nothing time-varying is in the document**: no ``created``, ``last_updated``, URL or read time
(the read time is the commit's). Two builds of an unchanged NetBox are byte-identical, so an
unchanged export commits nothing. ``sha256`` is the SHA-256 of the document's canonical bytes
WITHOUT the ``sha256`` key, so the schema version, the network and NetBox's version are inside
what it hashes.

**Where it lives:** ``nsot/export.json`` in the network's configuration repository, committed by
`write` through `repo._commit_paths` (``Source: nsot_export``, with ``Actor:``). `read` takes
what is COMMITTED (HEAD), never the working tree, and refuses a document whose recomputed hash
is not the one it carries, naming both. The export is installation data: it lives under
``data/`` and never in Mercury's public repository (only masked fixtures do).

**Reads only:** `collect` reads NetBox through the client's one GET (`netbox_client._nb_get`),
whole lists by filter, never one request per device; nothing here writes to NetBox.
"""

import hashlib
import ipaddress
import json
import logging
import os

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
PATH = "nsot/export.json"
SOURCE = "nsot_export"
#: The body's lists, in the order the document names them.
KINDS = ("devices", "interfaces", "vlans", "prefixes", "services", "cables", "hosts")
#: The end hosts (C2776, the operator's replan of 2026-11-09): a NetBox device tagged
#: ``mercury-end-host`` at one of the network's sites is an END HOST, not a device Mercury
#: manages: it is the export's ``hosts`` kind and never one of its ``devices``. Added to schema 1
#: as an optional key (expand, then contract): a document from before has no ``hosts`` key, which
#: `hosts_of` answers as None (not recorded), never as "no hosts".
HOST_TAG = "mercury-end-host"
#: NetBox's list filters take many ids at once; this many per request.
CHUNK = 100


class Refused(ValueError):
    """An export that cannot be built, written or read, in words."""


# --------------------------------------------------------------------------- projection

def _slug(obj) -> str:
    if isinstance(obj, dict):
        return str(obj.get("slug") or obj.get("value") or obj.get("name") or "")
    return str(obj or "")


def _name(obj) -> str:
    if isinstance(obj, dict):
        return str(obj.get("name") or obj.get("display") or "")
    return str(obj or "")


def _address(obj) -> str:
    """A NetBox address (``{"address": "192.0.2.5/24"}`` or the bare text) as its text."""
    return str((obj or {}).get("address") if isinstance(obj, dict) else obj or "")


def _tags(obj) -> list:
    return sorted({_slug(t) for t in obj.get("tags") or []} - {""})


def _sorted_value(value):
    """*value* with every list inside it in a fixed order (by its canonical JSON), so a config
    context or custom field NetBox returns in another order serialises the same."""
    if isinstance(value, dict):
        return {k: _sorted_value(v) for k, v in value.items()}
    if isinstance(value, list):
        items = [_sorted_value(v) for v in value]
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
    return value


def _vid(vlan):
    return (vlan or {}).get("vid") if isinstance(vlan, dict) else None


def _device(d: dict) -> dict:
    return {"id": d.get("id"), "name": _name(d), "status": _slug(d.get("status")),
            "role": _slug(d.get("role") or d.get("device_role")),
            "platform": _slug(d.get("platform")), "site": _slug(d.get("site")),
            "device_type": _slug(d.get("device_type")),
            "primary_ip4": _address(d.get("primary_ip4")),
            "primary_ip6": _address(d.get("primary_ip6")),
            "oob_ip": _address(d.get("oob_ip")),
            "custom_fields": _sorted_value(d.get("custom_fields") or {}),
            "config_context": _sorted_value(d.get("config_context") or {}),
            "tags": _tags(d)}


def _interface(i: dict, device_names: dict) -> dict:
    device = i.get("device") or {}
    return {"device": _name(device) or device_names.get(device.get("id"), ""),
            "name": _name(i), "type": _slug(i.get("type")), "enabled": bool(i.get("enabled")),
            "mgmt_only": bool(i.get("mgmt_only")), "mode": _slug(i.get("mode")),
            "description": str(i.get("description") or ""),
            "untagged_vlan": _vid(i.get("untagged_vlan")),
            "tagged_vlans": sorted(v for v in (_vid(t) for t in i.get("tagged_vlans") or [])
                                   if v is not None),
            "parent": _name(i.get("parent")), "lag": _name(i.get("lag")),
            "bridge": _name(i.get("bridge")),
            "custom_fields": _sorted_value(i.get("custom_fields") or {}),
            "tags": _tags(i),
            "ip_addresses": sorted(_address(a) for a in i.get("ip_addresses") or [])}


def _vlan(v: dict) -> dict:
    return {"vid": v.get("vid"), "name": str(v.get("name") or ""), "site": _slug(v.get("site")),
            "group": _slug(v.get("group")), "status": _slug(v.get("status")), "tags": _tags(v)}


def _prefix(p: dict) -> dict:
    return {"prefix": str(p.get("prefix") or ""), "site": _slug(p.get("site") or p.get("scope")),
            "vlan": _vid(p.get("vlan")), "status": _slug(p.get("status")),
            "role": _slug(p.get("role")), "tags": _tags(p)}


def _service_parent(s: dict) -> str:
    """The Service's device or virtual machine (NetBox before 4.3: ``device``; after:
    ``parent``)."""
    return _name(s.get("device") or s.get("virtual_machine") or s.get("parent") or {})


def _service(s: dict) -> dict:
    return {"parent": _service_parent(s), "name": str(s.get("name") or ""),
            "protocol": _slug(s.get("protocol")),
            "ports": sorted(int(p) for p in s.get("ports") or []),
            "ipaddresses": sorted(_address(a) for a in s.get("ipaddresses") or []),
            "tags": _tags(s)}


def _end(term: dict) -> list:
    obj = term.get("object") or term
    device = obj.get("device") or {}
    return [_name(device), _name(obj)]


def _cable(c: dict) -> dict:
    ends = sorted([sorted(_end(t) for t in c.get("a_terminations") or []),
                   sorted(_end(t) for t in c.get("b_terminations") or [])])
    return {"a": ends[0], "b": ends[1], "status": _slug(c.get("status")),
            "label": str(c.get("label") or "")}


def _mac(i: dict) -> str:
    """An interface's MAC, lower case with colons: NetBox 4.2's ``primary_mac_address``, else the
    ``mac_address`` field of the releases before; "" when it records none."""
    raw = (i.get("primary_mac_address") or {}).get("mac_address") if isinstance(
        i.get("primary_mac_address"), dict) else None
    raw = raw or i.get("mac_address") or ""
    hexes = "".join(c for c in str(raw).lower() if c in "0123456789abcdef")
    return ":".join(hexes[n:n + 2] for n in range(0, 12, 2)) if len(hexes) == 12 else ""


def _host(d: dict, interfaces: list, cables: list) -> dict:
    """An end host: its own fields and each interface with its MAC, its addresses and the far
    end of its cable (``attached``: ``[device, interface]``, or None when no cable is
    recorded)."""
    name = _name(d)
    peer = {}
    for c in cables:
        if c["a"] and c["b"]:
            for mine, theirs in ((c["a"], c["b"]), (c["b"], c["a"])):
                for end in mine:
                    if end[0] == name and len(theirs) == 1:
                        peer[end[1]] = list(theirs[0])
    return {"name": name, "id": d.get("id"), "site": _slug(d.get("site")),
            "status": _slug(d.get("status")), "role": _slug(d.get("role") or
                                                             d.get("device_role")),
            "tags": _tags(d),
            "interfaces": sorted(({"name": _name(i), "mac": _mac(i),
                                   "ip_addresses": sorted(_address(a) for a in
                                                          i.get("ip_addresses") or []),
                                   "attached": peer.get(_name(i))}
                                  for i in interfaces
                                  if ((i.get("device") or {}).get("id") == d.get("id"))),
                                 key=lambda i: i["name"])}


def _addr_key(text: str):
    try:
        net = ipaddress.ip_network(text, strict=False)
        return (net.version, int(net.network_address), net.prefixlen)
    except ValueError:
        return (9, 0, 0)


def body_of(records: dict) -> dict:
    """The body from NetBox *records* (``{kind: [raw NetBox objects]}`` for each of `KINDS`),
    each projected and sorted by its natural key. Pure: the seam the tests use."""
    host_ids = {h.get("id") for h in records.get("hosts") or []}
    devices = [_device(d) for d in records.get("devices") or []
               if d.get("id") not in host_ids and HOST_TAG not in _tags(d)]
    names = {d["id"]: d["name"] for d in devices}
    names.update({h.get("id"): _name(h) for h in records.get("hosts") or []})
    host_ifaces = [i for i in records.get("interfaces") or []
                   if (i.get("device") or {}).get("id") in host_ids]
    cables_all = [_cable(c) for c in records.get("cables") or []]
    out = {
        "devices": sorted(devices, key=lambda d: (d["name"], d["id"] or 0)),
        "interfaces": sorted((_interface(i, names) for i in records.get("interfaces") or []
                              if (i.get("device") or {}).get("id") not in host_ids),
                             key=lambda i: (i["device"], i["name"])),
        "vlans": sorted((_vlan(v) for v in records.get("vlans") or []),
                        key=lambda v: (v["site"], v["group"], v["vid"] or 0, v["name"])),
        "prefixes": sorted((_prefix(p) for p in records.get("prefixes") or []),
                           key=lambda p: (_addr_key(p["prefix"]), p["site"])),
        "services": sorted((_service(s) for s in records.get("services") or []),
                           key=lambda s: (s["parent"], s["name"], s["ports"])),
        "cables": sorted(cables_all, key=lambda c: (c["a"], c["b"])),
    }
    if "hosts" in records:
        out["hosts"] = sorted((_host(h, host_ifaces, cables_all) for h in records["hosts"]),
                              key=lambda h: (h["name"], h["id"] or 0))
    # One object per natural key: a Service read both by device and by name is one Service; a
    # cable read from both of its ends is one cable.
    for kind, key in (("services", lambda s: (s["parent"], s["name"], tuple(s["ports"]))),
                      ("devices", lambda d: (d["name"], d["id"])),
                      ("cables", lambda c: json.dumps([c["a"], c["b"]]))):
        seen, kept = set(), []
        for item in out[kind]:
            if key(item) not in seen:
                seen.add(key(item))
                kept.append(item)
        out[kind] = kept
    return out


def _canonical(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def digest(doc: dict) -> str:
    """The SHA-256 of *doc*'s canonical bytes without its ``sha256`` key."""
    return hashlib.sha256(_canonical({k: v for k, v in doc.items() if k != "sha256"})).hexdigest()


def document(network: str, netbox_version: str, records: dict) -> bytes:
    """The export's bytes for *network* from *records* (see `body_of`)."""
    doc = {"schema_version": SCHEMA_VERSION, "network": network,
           "netbox_version": str(netbox_version or ""), "body": body_of(records)}
    doc["sha256"] = digest(doc)
    return _canonical(doc)


def parse(data) -> dict:
    """The export document in *data* (bytes or text), its hash checked: raises Refused naming
    what is wrong (not JSON, another schema version, a hash that is not its own, both named)."""
    try:
        doc = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise Refused(f"the export is not JSON: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
        got = doc.get("schema_version") if isinstance(doc, dict) else type(doc).__name__
        raise Refused(f"the export's schema version is {got!r}, and Mercury reads "
                      f"{SCHEMA_VERSION}")
    if doc.get("sha256") != digest(doc):
        raise Refused(f"the export carries sha256 {str(doc.get('sha256'))[:12]}, and its body "
                      f"hashes to {digest(doc)[:12]}: it was edited after it was built")
    return doc


# --------------------------------------------------------------------------- NetBox (reads)

def _chunks(ids: list):
    for i in range(0, len(ids), CHUNK):
        yield ids[i:i + CHUNK]


def collect(network: str, *, get=None, version=None) -> dict:
    """*network*'s records from NetBox, read only: ``{"ok", "records", "netbox_version",
    "error"}``. The devices are the list's own (its source's filters, `source_config`), plus
    each device an ``openflow`` Service names as its parent (a controller outside the filter).
    *get* (``get(path, **params) -> list``) and *version* (``() -> str``) replace the NetBox
    client in tests."""
    from modules.inventory import source_config
    cfg = source_config.load(network)
    if cfg.get("source") != source_config.SOURCE_NETBOX:
        return {"ok": False, "records": {}, "netbox_version": "",
                "error": (f"{network}'s devices come from {cfg.get('source')!r}, not NetBox: "
                          "an NSOT export is NetBox's view of a network")}
    if get is None:
        from modules.netbox_client import _nb_get, _nb_ready
        ok, err, session, base = _nb_ready()
        if not ok:
            return {"ok": False, "records": {}, "netbox_version": "", "error": f"NetBox: {err}"}

        def get(path, **params):
            return _nb_get(session, base, path, **params)

        def version():
            r = session.get(f"{base}/api/status/", timeout=15)
            r.raise_for_status()
            return str((r.json() or {}).get("netbox-version") or "")
    try:
        params = {k: v for k, v in (cfg.get("filters") or {}).items() if v}
        devices = list(get("dcim/devices/", include="config_context", **params))
        services = list(get("ipam/services/", name="openflow"))
        known = {_name(d) for d in devices}
        for parent in sorted({_service_parent(s) for s in services} - known - {""}):
            devices += list(get("dcim/devices/", name=parent, include="config_context"))
        sites = sorted({(d.get("site") or {}).get("id") for d in devices} - {None})
        # The end hosts (C2776): tagged, at the network's sites, whatever the list's filters.
        hosts = list(get("dcim/devices/", tag=HOST_TAG, site_id=sites)) if sites else []
        # A host the list's own filter also returned stays among the raw devices; `body_of`
        # keeps every host out of the export's devices (tests/test_nsot_export.py).
        ids = sorted({d["id"] for d in devices + hosts if d.get("id") is not None})
        interfaces, addresses, cables = [], [], []
        for chunk in _chunks(ids):
            interfaces += get("dcim/interfaces/", device_id=chunk)
            addresses += get("ipam/ip-addresses/", device_id=chunk)
            services += get("ipam/services/", device_id=chunk)
            cables += get("dcim/cables/", device_id=chunk)
        vlans, prefixes = [], []
        if sites:
            vlans = list(get("ipam/vlans/", site_id=sites))
            prefixes = list(get("ipam/prefixes/", site_id=sites))
        nb_version = version() if version else ""
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.warning("nsot export: NetBox read failed for %s: %s", network, exc)
        return {"ok": False, "records": {}, "netbox_version": "",
                "error": f"NetBox could not be read: {type(exc).__name__}: {exc}"[:300]}
    by_iface: dict = {}
    for a in addresses:
        iface = (a.get("assigned_object") or {}).get("id")
        if iface is not None:
            by_iface.setdefault(iface, []).append({"address": a.get("address", "")})
    for i in interfaces:
        i["ip_addresses"] = by_iface.get(i.get("id"), [])
    return {"ok": True, "netbox_version": nb_version, "error": "",
            "records": {"devices": devices, "interfaces": interfaces, "vlans": vlans,
                        "prefixes": prefixes, "services": services, "cables": cables,
                        "hosts": hosts}}


def build(network: str, **kw) -> dict:
    """``{"ok", "bytes", "sha256", "error"}``: *network*'s export from NetBox now (`collect`'s
    *get* and *version* pass through). Writes nothing."""
    got = collect(network, **kw)
    if not got["ok"]:
        return {"ok": False, "bytes": b"", "sha256": "", "error": got["error"]}
    data = document(network, got["netbox_version"], got["records"])
    return {"ok": True, "bytes": data, "sha256": json.loads(data)["sha256"], "error": ""}


# --------------------------------------------------------------------------- the repository

def _repo(network: str) -> str:
    from modules.nsot import listref
    return listref.resolve(network).repo_dir


def committed_blob(network: str, rev: str = "HEAD") -> str:
    """The blob id of the committed ``nsot/export.json`` at *rev*, or "" when none is
    committed: what a preview binds, readable or not (a committed export whose hash is not its
    own is still a file the confirm must not replace unseen)."""
    from modules.nsot.repo import git, has_repository

    repo = _repo(network)
    if not has_repository(repo):
        return ""
    rc, out, _err = git(repo, "rev-parse", "--verify", "--quiet", f"{rev}:{PATH}")
    return out.strip() if rc == 0 else ""


def last_commit(network: str) -> dict:
    """The newest commit that wrote ``nsot/export.json``: ``{"commit", "at", "actor",
    "sha256"}`` from its own trailers, or {} when none did. Read from the repository's history,
    so the record reads the same later."""
    from modules.nsot.repo import git, has_repository

    repo = _repo(network)
    if not has_repository(repo):
        return {}
    rc, out, _err = git(repo, "log", "-1", "--format=%H%x00%cI%x00%B", "--", PATH)
    if rc != 0 or not out.strip():
        return {}
    sha, at, body = (out.split("\x00", 2) + ["", ""])[:3]
    trailers = {}
    for line in body.splitlines():
        key, sep, value = line.partition(": ")
        if sep and key in ("Actor", "Actor-Verified", "Export-Sha256"):
            trailers[key] = value.strip()
    return {"commit": sha.strip(), "at": at.strip(), "actor": trailers.get("Actor", ""),
            "actor_verified": trailers.get("Actor-Verified", ""),
            "sha256": trailers.get("Export-Sha256", "")}


def write(network: str, actor: str, actor_verified: str, *, data: bytes = None,
          base_blob: str = None, **kw) -> dict:
    """Build *network*'s export (or take *data*, already built) and commit it as
    ``nsot/export.json``: ``{"ok", "error", "sha256", "commit", "changed"}``. An export equal to
    the committed one commits nothing (``commit`` empty, ``changed`` False). *base_blob*: the
    committed file's blob id the caller previewed against (`committed_blob`, "" for none);
    with it, a commit made since is refused inside the repository's lock, naming both."""
    from modules.filestore import write_atomic
    from modules.nsot import repo as R

    if not actor or not actor_verified:
        return {"ok": False, "error": "an export is committed as an accountable, verified actor"}
    if data is None:
        built = build(network, **kw)
        if not built["ok"]:
            return {"ok": False, "error": built["error"]}
        data = built["bytes"]
    try:
        doc = parse(data)
    except Refused as exc:
        return {"ok": False, "error": str(exc)}
    if doc.get("network") != network:
        return {"ok": False, "error": (f"the export is {doc.get('network')!r}'s, and it is "
                                       f"being written to {network!r}")}
    repo = _repo(network)
    with R.repo_lock(repo):
        if base_blob is not None:
            now = committed_blob(network)
            if now != base_blob:
                return {"ok": False, "sha256": doc["sha256"], "moved": True,
                        "error": (f"the committed export moved since the preview (now "
                                  f"{_blob_words(now)}; previewed {_blob_words(base_blob)}): "
                                  "nothing was committed")}
        os.makedirs(os.path.join(repo, os.path.dirname(PATH)), exist_ok=True)
        write_atomic(os.path.join(repo, PATH), data.decode("utf-8"))
        got = R._commit_paths(network, [PATH],                                  # noqa: SLF001
                              f"NSOT export: {network} at {doc['sha256'][:12]}",
                              [f"Actor: {actor}", f"Actor-Verified: {actor_verified}",
                               f"Export-Sha256: {doc['sha256']}"], SOURCE)
    if not got.get("ok"):
        return {"ok": False, "error": f"the export's commit failed: {got.get('error')}",
                "sha256": doc["sha256"]}
    return {"ok": True, "error": "", "sha256": doc["sha256"], "commit": got.get("commit", ""),
            "changed": bool(got.get("commit"))}


def read(network: str, rev: str = "HEAD") -> dict:
    """*network*'s committed export at *rev*: ``{"ok", "export", "sha256", "error"}``. Read from
    the repository's history (`repo.git_raw`), never the working tree; a missing export, or one
    whose hash is not its own, is refused in words."""
    from modules.nsot.repo import git_raw
    rc, text, err = git_raw(_repo(network), "show", f"{rev}:{PATH}")
    if rc != 0:
        # ``absent``: nothing committed, apart from one committed that does not verify.
        return {"ok": False, "export": None, "sha256": "", "absent": True,
                "error": f"{network} has no committed NSOT export at {rev} ({PATH}): export it "
                         f"first ({str(err).strip()[:120]})"}
    try:
        doc = parse(text)
    except Refused as exc:
        return {"ok": False, "export": None, "sha256": "", "error": str(exc)}
    return {"ok": True, "export": doc, "sha256": doc["sha256"], "error": ""}


def _blob_words(blob: str) -> str:
    return f"blob {blob[:4]}…{blob[-4:]}" if blob else "none committed"


# --------------------------------------------------------------------------- readers

def _label(kind: str, item: dict) -> str:
    """An object's natural key, in words (the body's own sort keys)."""
    if kind == "devices":
        return item.get("name") or f"id {item.get('id')}"
    if kind == "interfaces":
        return f"{item.get('device')} {item.get('name')}"
    if kind == "vlans":
        where = "/".join(p for p in (item.get("site"), item.get("group")) if p) or "global"
        return f"VLAN {item.get('vid')} {item.get('name') or ''} ({where})".replace("  ", " ")
    if kind == "prefixes":
        return f"{item.get('prefix')}" + (f" ({item['site']})" if item.get("site") else "")
    if kind == "services":
        ports = ",".join(str(p) for p in item.get("ports") or [])
        return f"{item.get('parent')} {item.get('name')} ({ports or 'no port'})"
    if kind == "cables":
        return " to ".join("+".join(":".join(e) for e in side)
                           for side in (item.get("a") or [], item.get("b") or []))
    if kind == "hosts":
        return item.get("name") or f"id {item.get('id')}"
    return json.dumps(item, sort_keys=True)[:80]


def changes(old: dict, new: dict) -> dict:
    """What *new* (an export document) changes against *old* (the committed one, or None):
    ``{"kinds": [{"kind", "added", "removed", "changed"}], "total", "netbox_version":
    (old, new)}``, each list the objects' natural keys in words, sorted. Pure."""
    old_body = (old or {}).get("body") or {}
    new_body = (new or {}).get("body") or {}
    kinds, total = [], 0
    for kind in KINDS:
        before = {_label(kind, i): i for i in old_body.get(kind) or []}
        after = {_label(kind, i): i for i in new_body.get(kind) or []}
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        changed = sorted(k for k in set(after) & set(before) if after[k] != before[k])
        total += len(added) + len(removed) + len(changed)
        kinds.append({"kind": kind, "added": added, "removed": removed, "changed": changed,
                      "count": len(after)})
    return {"kinds": kinds, "total": total,
            "netbox_version": ((old or {}).get("netbox_version", ""),
                               (new or {}).get("netbox_version", ""))}


def device(export: dict, name: str):
    """The export's device *name*, or None."""
    for d in (export.get("body") or {}).get("devices") or []:
        if d.get("name") == name:
            return d
    return None


def interfaces_of(export: dict, name: str) -> list:
    return [i for i in (export.get("body") or {}).get("interfaces") or []
            if i.get("device") == name]


def hosts_of(export: dict):
    """The export's end hosts (C2776), or None when the document predates the kind (it was
    built before hosts were recorded): never an empty list for "not recorded"."""
    body = export.get("body") or {}
    return list(body["hosts"]) if "hosts" in body else None


def host_ports(export: dict) -> list:
    """Each end host's interface where it meets the fabric: ``[{"host", "interface", "mac",
    "ip_addresses", "switch", "switch_interface", "dpid", "port_no", "error"}]``, the switch's
    DPID and the port's number from the switch's OpenFlow values (`openflow_values.from_export`:
    ``openflow.datapath_id`` and ``port.openflow_port``); a value NetBox does not record is None,
    with *error* naming it. An interface with no cable is listed with no switch. Pure."""
    from modules.sdn import openflow_values
    from modules.sdn.drivers.base import SpecError, parse_dpid

    out = []
    for h in hosts_of(export) or []:
        for i in h.get("interfaces") or []:
            row = {"host": h["name"], "interface": i["name"], "mac": i.get("mac") or "",
                   "ip_addresses": list(i.get("ip_addresses") or []), "switch": "",
                   "switch_interface": "", "dpid": None, "port_no": None, "error": ""}
            att = i.get("attached")
            if not att:
                row["error"] = f"{h['name']} {i['name']} has no cable recorded in NetBox"
                out.append(row)
                continue
            row["switch"], row["switch_interface"] = att[0], att[1]
            got = openflow_values.from_export(export, att[0])
            values = got.get("values") or {} if isinstance(got, dict) else {}
            missing = []
            try:
                raw = values.get("openflow.datapath_id")
                row["dpid"] = parse_dpid(raw) if raw not in (None, "") else None
            except SpecError as exc:
                missing.append(f"{att[0]}'s datapath id: {exc}")
            if row["dpid"] is None and not missing:
                missing.append(f"{att[0]} records no openflow.datapath_id")
            port = str((values.get("port.openflow_port") or {}).get(att[1]) or "")
            row["port_no"] = int(port) if port.isdigit() else None
            if row["port_no"] is None:
                missing.append(f"{att[0]} {att[1]} records no openflow_port")
            row["error"] = "; ".join(missing)
            out.append(row)
    return out


def services_named(export: dict, service: str) -> list:
    return [s for s in (export.get("body") or {}).get("services") or []
            if s.get("name") == service]
