"""modules/dhcp_exclusions.py — SOURCE OF TRUTH › DHCP › Exclusions (C529 step 3; board D,
`DhcpExclusions.dc.html`, approved 2026-10-06).

Kea has no excluded-address setting, so Mercury models exclusions: each a range in one subnet,
named, with its reason and its source (manual, intent, NetBox), who and when. A person sets a
subnet's pool as ONE range; Kea is given the pieces of that range the exclusions leave
(`pieces`). The range as set and the exclusions are Mercury's record, committed in the network's
repository (`dhcp/exclusions.yml`), read as committed; the pieces are written to Kea through
board C's one write path for subnets (`dhcp_subnets.apply_edit` with this module's planner and
record): Kea's own check, config-reload, a read-back of exactly that subnet, restored on any
difference.

**Conflicts** (board D's first section): a static address committed intent assigns to an
interface, inside a subnet's pool and not excluded, is found by the DHCP reader's intent facts
and listed with where it is assigned and whether Kea has given it out; one click opens the
exclusion's preview with its reason filled from the source.
"""

import hashlib
import ipaddress
import json
import logging
import os
import time

log = logging.getLogger(__name__)

RECORD = "dhcp/exclusions.yml"
ASKS = ("op", "family", "id", "range", "reason", "source", "detail", "was")
SOURCES = ("manual", "intent", "netbox")
#: The apply's steps (board C's one write path for subnets), the record its own.
STEPS = (
    ("plan", "Plan again", "the subnet file's lock taken; Kea, Mercury's subnet file and the "
                           "committed record read again, and the hash compared with the "
                           "preview's"),
    ("test", "Kea's own check", "the subnet file with the pool's pieces tested with kea-dhcp4 -t "
                                "or kea-dhcp6 -t on a copy of the running configuration"),
    ("write", "Write", "Mercury's subnet file replaced by the tested candidate"),
    ("reload", "Reload", "config-reload through Kea's API; a failure restores the file"),
    ("read-back", "Read back", "Kea's configuration read again: exactly this subnet's pools "
                               "changed, every other subnet and setting as before"),
    ("record", "Record", "dhcp/exclusions.yml and dhcp/subnets.yml committed as you, with your "
                         "reason"),
)


class Refused(Exception):
    pass


def _repo(list_name: str) -> str:
    """The Kea owner's repository (C1181): where *list_name*'s Kea's exclusions are recorded,
    and so where they are read from, on the owner's page and on every page inheriting it."""
    from modules import dhcp_reservations as D
    from modules.list_settings import ListSettingsUnreadable

    try:
        return D.record_repo(list_name)
    except ListSettingsUnreadable as exc:
        raise Refused(f"whose Kea this is could not be read: {exc}") from None


def read_committed(list_name: str) -> dict:
    """``{"exclusions": [...], "pools": {"IPv4:10": "a - b"}}`` as committed at HEAD; empty when
    none is recorded. Raises `Refused` when it exists and cannot be read: a record that cannot
    be read is never read as "nothing excluded"."""
    import yaml

    from modules.nsot import repo as R

    repo = _repo(list_name)
    if not os.path.isdir(os.path.join(repo, ".git")):
        return {"exclusions": [], "pools": {}}
    rc, out, err = R.git_raw(repo, "ls-tree", "--name-only", "HEAD", "--", RECORD)
    if rc != 0:
        rc2, _o, _e = R.git_raw(repo, "rev-parse", "--verify", "-q", "HEAD")
        if rc2 != 0:
            return {"exclusions": [], "pools": {}}
        raise Refused(f"{RECORD} could not be listed at HEAD: {err or rc}")
    if not out.strip():
        return {"exclusions": [], "pools": {}}
    rc, text, err = R.git_raw(repo, "show", f"HEAD:{RECORD}")
    if rc != 0:
        raise Refused(f"{RECORD} is at HEAD and could not be read: {err or rc}")
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise Refused(f"{RECORD} at HEAD is not YAML: {exc}") from None
    if not isinstance(doc.get("exclusions", []), list) or not isinstance(doc.get("pools", {}),
                                                                         dict):
        raise Refused(f"{RECORD} at HEAD is not a list of exclusions and a table of pools")
    return {"exclusions": doc.get("exclusions") or [], "pools": doc.get("pools") or {}}


def span(text: str) -> tuple:
    """``(first, last)`` addresses of ``a - b`` or of one address."""
    import re
    parts = [p.strip() for p in re.split(r"\s*[-–]\s*", (text or "").strip()) if p.strip()]
    try:
        if len(parts) == 1:
            a = ipaddress.ip_address(parts[0])
            return a, a
        if len(parts) == 2:
            a, b = (ipaddress.ip_address(x) for x in parts)
            if a > b:
                raise Refused(f"the range {text!r} ends before it starts")
            return a, b
    except ValueError as exc:
        raise Refused(f"the range {text!r}: {exc}") from None
    raise Refused(f"the range {text!r} is not an address or first - last")


def words(a, b) -> str:
    return str(a) if a == b else f"{a} - {b}"


def pieces(pool: str, excluded: list) -> list:
    """The pieces of *pool* (``a - b``) that the excluded ranges (``a - b`` each) leave, as Kea
    pool strings, in order; [] when nothing is left."""
    lo, hi = span(pool)
    cuts = sorted(span(x) for x in excluded)
    out, at = [], lo
    for a, b in cuts:
        if b < at or a > hi:
            continue
        if a > at:
            out.append((at, a - 1))
        at = max(at, b + 1)
        if at > hi:
            break
    if at <= hi:
        out.append((at, hi))
    return [words(a, b) for a, b in out]


def _key(family: str, sid) -> str:
    return f"{family}:{sid}"


def ask(values) -> dict:
    s = {k: (values.get(k) or "").strip() for k in ASKS}
    where = (values.get("where") or "").strip()
    if where and ":" in where:
        s["family"], s["id"] = (x.strip() for x in where.split(":", 1))
    s["op"] = s["op"] or "add"
    s["source"] = s["source"] if s["source"] in SOURCES else "manual"
    return s


def plan(list_name: str, values, kea=None, intent=None, record=None) -> dict:
    """Board D's exclusion preview, shaped as board C's subnet plan (op "edit") so board C's
    one write path applies it: ``{ok, refused, op, family, id, prefix, title, change, checks,
    leases, survives, ack, before, after, path, version, hash, subject, exclusion, record}``.
    A read: Kea is asked, Mercury's subnet file and the committed record are read."""
    from modules import dhcp_reservations as D
    from modules import dhcp_subnets as S

    s = ask(values)
    p = {"ok": False, "refused": "", "ask": s, "op": "edit", "family": s["family"], "id": None,
         "prefix": "", "title": "", "change": [], "checks": [], "leases": [], "survives": [],
         "ack": False, "before": None, "after": None, "path": "", "version": "", "hash": "",
         "subject": "", "exclusion": None, "record": None, "kind": s["op"]}
    try:
        _plan(list_name, s, p, kea, intent, record, D, S)
    except (Refused, S.Refused, D.Refused) as exc:
        p["refused"] = str(exc)
        return p
    p["hash"] = hashlib.sha256(json.dumps(
        {**{k: p[k] for k in ("kind", "family", "id", "before", "after", "version")},
         "record": _unstamped(p["record"])},
        sort_keys=True, default=str).encode("utf-8")).hexdigest()
    p["ok"] = True
    return p


def _unstamped(record):
    """The record as the confirm binds it: every exclusion less its `at` and `by` stamps. The
    plan stamps a new exclusion with the clock, and the confirm recomputes the plan, so a stamp
    in the hash refused every confirm made in a later second than its preview (C770: CI caught
    the race; a person's confirm always loses it). The record written carries the apply's own
    time."""
    if not record:
        return record
    return dict(record, exclusions=[{k: v for k, v in e.items() if k not in ("at", "by")}
                                    for e in record.get("exclusions") or []])


def _plan(list_name, s, p, kea, intent, record, D, S) -> None:
    if s["op"] not in ("add", "remove"):
        raise Refused(f"{s['op']!r} is not add or remove")
    subnets, config, kea = S._state(list_name, dict(s), p, kea, None, D)   # noqa: SLF001
    family = s["family"]
    try:
        sid = int(s["id"])
    except ValueError:
        raise Refused(f"{s['id']!r} is not a Kea subnet id") from None
    p["id"] = sid
    hit = [x for x in subnets if x.get("id") == sid]
    if len(hit) != 1:
        raise Refused(f"subnet {sid} is in Mercury's {family} subnet file {len(hit)} times")
    from modules.readers.dhcp import _ztp_ids
    if family == "IPv4" and sid in _ztp_ids(config):
        raise Refused(f"subnet {sid} is ZTP's: it has no pool to shape")
    before = hit[0]
    prefix = before.get("subnet", "")
    p["before"], p["prefix"] = before, prefix
    rec = record if record is not None else read_committed(list_name)
    mine = [e for e in rec["exclusions"] if e.get("family") == family and e.get("subnet") == sid]
    as_set = rec["pools"].get(_key(family, sid))
    if not as_set:
        pools = [x.get("pool", "") for x in before.get("pools") or []]
        if len(pools) != 1:
            raise Refused(f"subnet {sid} has {len(pools)} pools in Kea and no range set in "
                          f"{RECORD}: set its pool as one range on DHCP › Subnets first")
        as_set = pools[0]
    lo, hi = span(as_set)
    net = ipaddress.ip_network(prefix, strict=False)
    if s["op"] == "add":
        a, b = span(s["range"])
        if a not in net or b not in net:
            raise Refused(f"the range {words(a, b)} does not lie inside {prefix}")
        for e in mine:
            x, y = span(e["range"])
            if not (b < x or a > y):
                raise Refused(f"{words(a, b)} overlaps the exclusion {e['range']} "
                              f"({e.get('reason', '')})")
        if len(" ".join(s["reason"].split())) < 8:
            raise Refused("say why these addresses are kept out, in a few words: the reason is "
                          "recorded with the exclusion and shown beside it")
        entry = {"family": family, "subnet": sid, "range": words(a, b),
                 "reason": " ".join(s["reason"].split()), "source": s["source"],
                 "detail": s["detail"][:120]}
        new = mine + [entry]
        p["exclusion"] = entry
        inside = not (b < lo or a > hi)
        p["title"] = f"Exclude {words(a, b)} from {prefix}"
        p["subject"] = f"dhcp: {words(a, b)} excluded from {family} subnet {sid} ({prefix})"
        p["checks"].append(("pass", f"{words(a, b)} lies inside {prefix} and overlaps no "
                                    "exclusion recorded"))
        p["checks"].append(("pass" if inside else "note",
                            f"inside the pool {as_set}: the pool is split around it" if inside
                            else f"outside the pool {as_set} today; kept out if it grows"))
    else:
        was = [e for e in mine if e.get("range") == s["was"]]
        if len(was) != 1:
            raise Refused(f"no exclusion {s['was']!r} is recorded for subnet {sid}")
        new = [e for e in mine if e is not was[0]]
        p["exclusion"] = was[0]
        p["title"] = f"Remove the exclusion {s['was']} from {prefix}"
        p["subject"] = f"dhcp: exclusion {s['was']} removed from {family} subnet {sid}"
        p["survives"] = ["The exclusion stays in the repository's history (dhcp/exclusions.yml); "
                         "adding it back is one Add. Its addresses return to the pool, and Kea "
                         "may give them out from the next request."]
        p["checks"].append(("pass", f"the exclusion {s['was']} is recorded for subnet {sid}"))
    shaped = pieces(as_set, [e["range"] for e in new])
    if not shaped:
        raise Refused(f"the exclusions would leave nothing of the pool {as_set}")
    after = json.loads(json.dumps(before))
    # C709: every piece keeps what the pool says it is for (its user-context, the description).
    ctx = next((dict(x["user-context"]) for x in before.get("pools") or []
                if x.get("user-context")), None)
    after["pools"] = [dict({"pool": x}, **({"user-context": ctx} if ctx else {}))
                      for x in shaped]
    p["after"] = after
    others = [e for e in rec["exclusions"]
              if not (e.get("family") == family and e.get("subnet") == sid)]
    stamp = {"by": "", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    p["record"] = {"exclusions": others + [dict(e, **({} if "at" in e else stamp)) for e in new],
                   "pools": dict(rec["pools"], **{_key(family, sid): as_set})}
    p["change"] = [(" ", f"subnet {sid} ({prefix}): the pool as set, {as_set}")] + [
        ("-", f"pool {x.get('pool')}") for x in before.get("pools") or []] + [
        ("+", f"pool {x}") for x in shaped]
    # Leases now: a client holding an excluded address keeps it until its lease ends.
    if s["op"] == "add":
        a, b = span(s["range"])
        for lease in D.kea_leases(kea, family):
            addr = lease.get("ip-address", "")
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if lease.get("subnet-id") == sid and lease.get("state", 0) == 0 and a <= ip <= b:
                ends = (lease.get("cltt", 0) or 0) + (lease.get("valid-lft", 0) or 0)
                who = lease.get("hw-address") or lease.get("duid") or "?"
                p["leases"].append(f"{addr} is held by {who} now: it " + S.STRANDED_WORDS.format(
                    ends=S._iso(ends)) + ("; until then two hosts may answer on it" if
                                          s["source"] != "manual" else ""))   # noqa: SLF001
        reserved = [r for r in D.every_reservation(config, family)
                    if any(a <= ipaddress.ip_address(x) <= b for x in r["addresses"])]
        for r in reserved:
            p["checks"].append(("note", f"{', '.join(r['addresses'])} is reserved for "
                                        f"{r['identity']}: a reservation for an excluded address "
                                        "is allowed (a fixed address kept out of the pool)"))
    if not p["leases"]:
        p["leases"].append("no lease held now is on these addresses"
                           if s["op"] == "add" else "the addresses return to the pool")
    p["checks"].append(("pending", f"kea-{'dhcp4' if family == 'IPv4' else 'dhcp6'} -t on the "
                                   "candidate, at confirm; the live file untouched until then"))


def record_commit(list_name: str, p: dict, *, actor: str, reason: str) -> dict:
    """Write `dhcp/exclusions.yml` (the plan's record, the new entry stamped with who) and
    `dhcp/subnets.yml` (as Mercury's files hold the subnets now), one commit as *actor*."""
    import yaml

    from modules import dhcp_subnets as S
    from modules.filestore import write_atomic
    from modules.nsot import repo as R

    from modules import dhcp_reservations as D
    from modules.config import get_list_data_dir
    from modules.list_settings import ListSettingsUnreadable

    doc = json.loads(json.dumps(p["record"]))
    for e in doc["exclusions"]:
        if not e.get("by"):
            e["by"] = actor
    try:
        owner, extra = D.record_home(list_name)          # C1181: the Kea owner's repository
    except ListSettingsUnreadable as exc:
        return {"ok": False, "error": f"whose Kea this is could not be read: {exc}"}
    repo = os.path.join(get_list_data_dir(owner), "config_repo")
    with R.repo_lock(repo):
        target = os.path.join(repo, RECORD)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        write_atomic(target, "# DHCP exclusions and each subnet's pool as set (C529, board D); "
                             "Kea is given the pieces.\n" + yaml.safe_dump(doc, sort_keys=False))
        S.write_subnets_record(owner, repo)
        return R._commit_paths(owner, [RECORD, S.RECORD],                        # noqa: SLF001
                               f"{p.get('subject')}\n\n{reason.strip()}",
                               [f"Actor: {actor}", *extra], "dhcp")


def conflicts(value: dict, record: dict) -> list:
    """Board D's conflicts from the DHCP reader's stored value: each static address intent
    assigns to an interface inside a subnet's pool (Kea's pieces) and not excluded:
    ``[{address, family, id, prefix, pool, device, iface, leased: str}]``."""
    intent = value.get("intent") or {}
    excluded = [(e.get("family"), e.get("subnet"), span(e["range"]))
                for e in record.get("exclusions") or []]
    leased = {}
    for fam in (value.get("families") or {}).values():
        for l in fam.get("leases") or []:
            if l.get("state") == "active":
                leased[(fam.get("words"), l.get("address"))] = l
    out = []
    for fam in (value.get("families") or {}).values():
        family = fam.get("words", "")
        for sub in fam.get("subnets") or []:
            if sub.get("ztp"):
                continue
            ranges = []
            for pool in sub.get("pools") or []:
                try:
                    ranges.append(span(pool.replace("-", " - ") if " - " not in pool else pool))
                except Refused:
                    continue
            for e in (intent.get(family) or {}).get(sub.get("prefix", "").lower()
                                                     if family == "IPv6"
                                                     else sub.get("prefix", "")) or []:
                addr = e.get("address")
                try:
                    ip = ipaddress.ip_address(addr)
                except (ValueError, TypeError):
                    continue
                if not any(a <= ip <= b for a, b in ranges):
                    continue
                if any(f == family and i == sub.get("id") and a <= ip <= b
                       for f, i, (a, b) in excluded):
                    continue
                l = leased.get((family, str(ip)))
                out.append({"address": str(ip), "family": family, "id": sub.get("id"),
                            "prefix": sub.get("prefix"), "pool": ", ".join(sub.get("pools") or []),
                            "device": e.get("device"), "iface": e.get("iface"),
                            "leased": (f"yes, to {l.get('identity') or l.get('mac') or '?'} "
                                       f"until {l.get('ends', '?')}: two hosts may answer on it"
                                       if l else "no: Kea has not given it out")})
    return out
