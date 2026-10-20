"""modules/dhcp_leases.py — releasing a Kea lease: THE one home for it (C1403; C697's request,
pulled forward by the operator, 2026-10-19).

Kea holds a lease until it ends. A lease nobody will renew (a device retired, an onboarding
abandoned, a VM recreated with a new client identifier) holds its address for the whole of its
lifetime, and a reservation of that address for anyone else is then refused as a conflict:
measured in 0d's run 2 (2026-10-19), where a redeployed device asked with a new client-id, Kea
logged ``ALLOC_ENGINE_V4_DISCOVER_ADDRESS_CONFLICT`` against run 1's 7-day lease, and answered
none of 238 requests until the lease was deleted by hand with ``lease4-del``.

Three callers, one code path:

- **Retire** (`modules/nsot/retire.py`, its ``leases`` step) and **Abandon**
  (`modules/nsot/onboard.py`, its ``leases`` step) read every lease Kea holds for the device's
  MAC or any address it was known by (:func:`for_device`), name them in the plan and the dry
  run, and release them at apply (:func:`release_for_device`);
- **DHCP › Leases › Release lease…** (`routes/dhcp_v2.py`): one lease, previewed (:func:`plan`)
  and confirmed by hash as a verified person with a reason (:func:`apply`).

Each release goes through the Kea integration's one client (`modules/integrations/kea.py`):
``lease4-del`` or ``lease6-del`` with the lease's address (and, for IPv6, its type), through
Kea's control agent and its `lease_cmds` hook. Read back: Kea's leases read again, each
released address holding no lease for that client. Recorded: ``dhcp/released-leases.yml`` in
the Kea owner's repository (`dhcp_reservations.commit_in_owner`), as the person, with the
reason in the commit.

Addresses are compared PARSED (an IPv6 address has many spellings), never as text; IPv4 and
IPv6 are handled alike, the family named on every lease.
"""

import hashlib
import ipaddress
import json
import logging
import time

log = logging.getLogger(__name__)

FAMILIES = ("IPv4", "IPv6")
#: Kea's command per family (the `lease_cmds` hook, configured on the lab's Kea 2.4.1, read
#: 2026-09-26 in docs/P6_ZTP.md's survey of its 51 commands).
DELETE = {"IPv4": "lease4-del", "IPv6": "lease6-del"}
SVC = {"IPv4": "dhcp4", "IPv6": "dhcp6"}
#: Kea's lease states (lease_cmds): 0 active, 1 declined, 2 expired-reclaimed.
STATES = {0: "active", 1: "declined", 2: "expired-reclaimed"}
#: The release's steps, in order (the DHCP page's Release lease…; the manual's page
#: docs/manual/how-it-works/dhcp-lease-release.md names each, tests/test_manual.py holds it).
STEPS = (
    ("plan", "Plan again", "Kea's leases read again, and the hash compared with the preview's"),
    ("release", "Release", "lease4-del or lease6-del through Kea's control agent, for this "
                           "address alone"),
    ("read-back", "Read back", "Kea's leases read again: the address holds no lease for this "
                               "client"),
    ("record", "Record", "dhcp/released-leases.yml committed as you, with your reason"),
)
#: THE stepper's steps for a release (`dhcp_page.write_run`), keyed as `apply` notes ``at``.
RUN_STEPS = (("release", "Lease released"), ("read_back", "Read back"), ("record", "Recorded"))
RECORD = "dhcp/released-leases.yml"
ASKS = ("family", "address")


class Refused(Exception):
    pass


# ── addresses and identities ────────────────────────────────────────────────────────────────

def addr(value) -> str:
    """An address in one spelling (IPv6 compressed), or "" when *value* is not one."""
    try:
        return ipaddress.ip_address(str(value or "").strip()).compressed
    except ValueError:
        return ""


def mac(value) -> str:
    """A MAC in Kea's spelling: lower case, colons."""
    return str(value or "").strip().lower().replace("-", ":")


def _duid_mac(duid: str) -> str:
    """The MAC a DUID-LL (type 3) or DUID-LLT (type 1) of hardware type 1 carries, or ""."""
    octets = mac(duid).split(":")
    if octets[:4] == ["00", "03", "00", "01"] and len(octets) == 10:
        return ":".join(octets[4:])
    if octets[:4] == ["00", "01", "00", "01"] and len(octets) == 14:
        return ":".join(octets[8:])
    return ""


def _iso(ts) -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(ts)))
    except (TypeError, ValueError, OverflowError):
        return ""


def row(lease: dict, family: str) -> dict:
    """One lease as this module carries it: the facts that name it and its client."""
    cltt, valid = lease.get("cltt"), lease.get("valid-lft")
    ends = (_iso(cltt + valid) if isinstance(cltt, int) and isinstance(valid, int) else "")
    hw = mac(lease.get("hw-address"))
    duid = mac(lease.get("duid"))
    client_id = mac(lease.get("client-id"))
    if family == "IPv6":
        by, identity = ("DUID", duid) if duid else ("MAC", hw)
    else:
        by, identity = ("MAC", hw) if hw else ("client-id", client_id)
    host = (lease.get("hostname") or "").strip()
    return {"family": family, "address": addr(lease.get("ip-address")) or
            str(lease.get("ip-address") or ""), "mac": hw or _duid_mac(duid), "duid": duid,
            "client_id": client_id, "by": by, "identity": identity,
            "hostname": "" if host in ("", ".") else host,
            "subnet_id": lease.get("subnet-id"), "type": lease.get("type") or "",
            "iaid": lease.get("iaid"), "state": STATES.get(lease.get("state", 0),
                                                           str(lease.get("state"))),
            "last_seen": _iso(cltt), "ends": ends}


def _same_client(a: dict, b: dict) -> bool:
    """Whether two lease rows name the same client on the same address (what a hash binds)."""
    keys = ("family", "address", "by", "identity", "type", "iaid")
    return all(a.get(k) == b.get(k) for k in keys)


def bound(r: dict) -> dict:
    """What a preview binds of a lease: its address and its client, never the times a renewal
    moves (a client renewing between preview and confirm is the same lease)."""
    return {k: r.get(k) for k in ("family", "address", "by", "identity", "mac", "type", "iaid",
                                  "subnet_id")}


# ── reading ─────────────────────────────────────────────────────────────────────────────────

def read(kea, family: str) -> list:
    """Every lease Kea holds for *family*, as rows. Raises `Refused` naming the command when Kea
    could not be asked: an unreadable lease list is "could not read", never "none"."""
    from modules import dhcp_reservations as D

    try:
        raw = D.kea_leases(kea, family)
    except D.Refused as exc:
        raise Refused(str(exc)) from None
    return [row(l, family) for l in raw if isinstance(l, dict)]


def matching(rows: list, *, macs=(), addresses=()) -> list:
    """The rows naming one of *macs* (its hardware address, or the MAC its DUID carries) or
    holding one of *addresses* (compared parsed, so IPv6's spellings are one address)."""
    want_macs = {mac(m) for m in macs if mac(m)}
    want_addrs = {addr(a) for a in addresses if addr(a)}
    return [r for r in rows
            if (r["mac"] and r["mac"] in want_macs) or (r["address"] in want_addrs)]


def held(kea, *, macs=(), addresses=(), families=FAMILIES) -> dict:
    """Every lease Kea holds for a client: ``{"ok", "configured", "leases", "error"}``. Kea not
    configured holds nothing (``configured`` False, ``ok`` True); Kea configured and not
    answering is ``ok`` False with the error, never an empty list."""
    out = {"ok": True, "configured": True, "leases": [], "error": ""}
    if not kea.is_configured():
        out["configured"] = False
        return out
    errors = []
    for family in families:
        try:
            out["leases"] += matching(read(kea, family), macs=macs, addresses=addresses)
        except Refused as exc:
            errors.append(f"{family}: {exc}")
    if errors:
        out.update(ok=False, error="; ".join(errors))
    return out


def words(r: dict, times: bool = True) -> str:
    """A lease in a sentence's words: its address, family, client and state, and when it ends
    unless *times* is False (a plan whose hash binds its words leaves out what a renewal
    moves)."""
    who = f"{r.get('by')} {r['identity']}" if r.get("identity") else "no identity"
    host = f", {r['hostname']}" if r.get("hostname") else ""
    state = f", {r['state']}" if r.get("state") not in (None, "active") else ""
    ends = f", ends {r['ends'][:16].replace('T', ' ')} UTC" if times and r.get("ends") else ""
    return f"{r['address']} ({r['family']}, {who}{host}{state}{ends})"


# ── releasing ───────────────────────────────────────────────────────────────────────────────

def _kea_code(result) -> int:
    """Kea's own result code in a control agent answer (one entry per service asked)."""
    entry = result[0] if isinstance(result, list) and result else result
    try:
        return int((entry or {}).get("result"))
    except (TypeError, ValueError):
        return -1


def release(kea, rows: list) -> dict:
    """Release each lease in *rows*: ``{"ok", "outcomes": [{"lease", "outcome", "detail"}],
    "error"}``; outcome ``released`` (Kea deleted it and it is gone on the read-back),
    ``absent`` (Kea held no lease there any more), ``kept`` (the address is now leased to
    another client: left), or ``failed``. Kea's leases are read again first, so only the lease
    named is deleted, and again after, so a release is never claimed that Kea does not show."""
    out = {"ok": False, "outcomes": [], "error": ""}
    families = sorted({r["family"] for r in rows})
    try:
        now = {f: read(kea, f) for f in families}
    except Refused as exc:
        out["error"] = f"Kea's leases could not be read again before the release: {exc}"
        return out
    sent = []
    for r in rows:
        here = [x for x in now[r["family"]] if x["address"] == r["address"]]
        if not here:
            out["outcomes"].append({"lease": r, "outcome": "absent",
                                    "detail": f"Kea holds no lease on {r['address']} now"})
            continue
        if not any(_same_client(x, r) for x in here):
            other = here[0]
            out["outcomes"].append({
                "lease": r, "outcome": "kept",
                "detail": (f"{r['address']} is leased now to {other['by']} {other['identity']}"
                           f", not {r['by']} {r['identity']} as read before: that lease is "
                           "another client's and was left")})
            continue
        args = {"ip-address": r["address"]}
        if r["family"] == "IPv6":
            args["type"] = r.get("type") or "IA_NA"
        got = kea.command(DELETE[r["family"]], service=[SVC[r["family"]]], arguments=args)
        if not got.get("ok"):
            out["outcomes"].append({"lease": r, "outcome": "failed",
                                    "detail": f"{DELETE[r['family']]} {r['address']}: "
                                              f"{got.get('error') or 'refused'}"})
            continue
        if _kea_code(got.get("result")) == 3:
            out["outcomes"].append({"lease": r, "outcome": "absent",
                                    "detail": f"{DELETE[r['family']]} {r['address']}: Kea held "
                                              "no lease there"})
            continue
        sent.append(r)
    if sent:
        try:
            after = {f: read(kea, f) for f in {r["family"] for r in sent}}
        except Refused as exc:
            for r in sent:
                out["outcomes"].append({"lease": r, "outcome": "failed", "step": "read_back",
                                        "detail": f"{DELETE[r['family']]} {r['address']} was "
                                                  "answered, and the read-back failed: "
                                                  f"{exc}"})
            sent = []
            after = {}
        for r in sent:
            still = [x for x in after[r["family"]]
                     if x["address"] == r["address"] and _same_client(x, r)]
            if still:
                out["outcomes"].append({"lease": r, "outcome": "failed", "step": "read_back",
                                        "detail": f"{DELETE[r['family']]} {r['address']} was "
                                                  "answered, and Kea still holds the lease"})
            else:
                out["outcomes"].append({"lease": r, "outcome": "released",
                                        "detail": f"{words(r)} released; read back: Kea holds "
                                                  "no lease there for it"})
    bad = [o for o in out["outcomes"] if o["outcome"] == "failed"]
    out["ok"] = not bad
    out["error"] = "; ".join(o["detail"] for o in bad)
    return out


# ── the record ──────────────────────────────────────────────────────────────────────────────

def _committed(owner: str) -> list:
    """The releases recorded at HEAD in *owner*'s repository ([] when none is recorded)."""
    import os

    import yaml

    from modules.config import get_list_data_dir
    from modules.nsot import repo as R

    repo = os.path.join(get_list_data_dir(owner), "config_repo")
    if not os.path.isdir(os.path.join(repo, ".git")):
        return []
    rc, out, _err = R.git_raw(repo, "ls-tree", "--name-only", "HEAD", "--", RECORD)
    if rc != 0 or not out.strip():
        return []
    rc, text, err = R.git_raw(repo, "show", f"HEAD:{RECORD}")
    if rc != 0:
        raise Refused(f"{RECORD} is at HEAD and could not be read: {err or rc}")
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise Refused(f"{RECORD} at HEAD is not YAML: {exc}") from None
    return list(doc.get("released") or [])


def record(list_name: str, outcomes: list, *, actor: str, reason: str, source: str,
           subject: str) -> dict:
    """Commit each released lease in ``dhcp/released-leases.yml`` (the earlier releases kept,
    read as committed) in the Kea owner's repository as *actor*, the reason in the body
    (`dhcp_reservations.commit_in_owner`). ``{"ok", "commit", "owner", "error"}``."""
    import yaml

    from modules import dhcp_reservations as D

    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    new = [dict(bound(o["lease"]), hostname=o["lease"].get("hostname", ""),
                ends=o["lease"].get("ends", ""), at=at, by_person=actor, source=source,
                reason=reason.strip())
           for o in outcomes if o["outcome"] == "released"]
    if not new:
        return {"ok": True, "commit": "", "owner": "", "error": ""}
    problem = []

    def text_for(owner):
        try:
            kept = _committed(owner)
        except Refused as exc:
            problem.append(str(exc))
            kept = []
        return ("# Kea leases Mercury released (C1403): each with who, when, why and from "
                "where; written on each release.\n"
                + yaml.safe_dump({"released": kept + new}, sort_keys=False))

    got = D.commit_in_owner(list_name, RECORD, text_for, f"{subject}\n\n{reason.strip()}",
                            actor=actor)
    if problem:
        return dict(got, ok=False, error=(f"the earlier releases could not be read "
                                          f"({problem[0]}); the record holds only this one"))
    return got


# ── for a device: Retire and Abandon ────────────────────────────────────────────────────────

def _kea_for(list_name: str):
    """The Kea a device's leases are in: its network's Kea OWNER's (`ztp.kea_home`, C1235)."""
    from modules.nsot import ztp

    return ztp._kea(ztp.kea_home(list_name)["owner"])                       # noqa: SLF001


def for_device(list_name: str, *, macs=(), addresses=(), kea=None) -> dict:
    """Every lease Kea holds for a device (any of *macs*, any of *addresses*), both families:
    ``{"ok", "configured", "leases", "error"}``. A read. Raises nothing."""
    from modules.list_settings import ListSettingsUnreadable

    try:
        kea = kea or _kea_for(list_name)
    except ListSettingsUnreadable as exc:
        return {"ok": False, "configured": True, "leases": [],
                "error": f"whose Kea {list_name} uses could not be read ({exc})"}
    return held(kea, macs=macs, addresses=addresses)


def release_for_device(list_name: str, leases: list, *, actor: str, reason: str,
                       source: str, device: str, kea=None) -> dict:
    """Release the leases a plan named for *device* and record them: ``{"ok", "outcomes",
    "commit", "error"}``. A lease now held by another client is left and said."""
    from modules.list_settings import ListSettingsUnreadable

    out = {"ok": False, "outcomes": [], "commit": "", "error": ""}
    if not leases:
        out["ok"] = True
        return out
    try:
        kea = kea or _kea_for(list_name)
    except ListSettingsUnreadable as exc:
        out["error"] = f"whose Kea {list_name} uses could not be read ({exc})"
        return out
    got = release(kea, leases)
    out["outcomes"] = got["outcomes"]
    rec = record(list_name, got["outcomes"], actor=actor, reason=reason, source=source,
                 subject=f"dhcp: {device}'s lease(s) released ({source})")
    out["commit"] = rec.get("commit", "")
    errors = [got["error"]] if got["error"] else []
    if not rec.get("ok"):
        errors.append(f"released in Kea; the record failed: {rec.get('error')}")
    out["ok"] = not errors
    out["error"] = "; ".join(errors)
    return out


def summary(outcomes: list) -> str:
    """The outcomes in words, for a step's detail."""
    return "; ".join(o["detail"] for o in outcomes) or "no lease to release"


# ── the DHCP page: Release lease… ───────────────────────────────────────────────────────────

def ask(values) -> dict:
    return {k: (values.get(k) or "").strip() for k in ASKS}


def plan(list_name: str, values, kea=None) -> dict:
    """What Release lease…'s preview draws: ``{ok, refused, family, address, lease, title,
    change, checks, survives, hash, subject}``. A read: Kea is asked for its leases and its
    configuration (a reservation of the address is named); nothing is written."""
    from modules import dhcp_reservations as D

    s = ask(values)
    p = {"ok": False, "refused": "", "ask": s, "family": s["family"], "address": "",
         "lease": None, "title": "Release a lease", "change": [], "checks": [], "survives": [],
         "hash": "", "subject": ""}
    try:
        if s["family"] not in FAMILIES:
            raise Refused(f"{s['family']!r} is not IPv4 or IPv6")
        try:
            ip = ipaddress.ip_address(s["address"])
        except ValueError:
            raise Refused(f"{s['address']!r} is not an address") from None
        if (ip.version == 4) != (s["family"] == "IPv4"):
            raise Refused(f"{ip} is not an {s['family']} address")
        p["address"] = ip.compressed
        if kea is None:
            from modules.integrations.kea import KeaIntegration
            kea = KeaIntegration(list_name=list_name)
        if not kea.is_configured():
            raise Refused("Kea is not configured for this network: it holds no lease to "
                          "release")
        here = [r for r in read(kea, s["family"]) if r["address"] == ip.compressed]
        if not here:
            raise Refused(f"Kea holds no lease on {ip.compressed} now (its {s['family']} leases "
                          "read just now): nothing to release")
        if len(here) > 1:
            raise Refused(f"Kea holds {len(here)} leases on {ip.compressed} "
                          f"({'; '.join(words(r) for r in here)}): one is released at a time, "
                          "and which is meant cannot be told from the address")
        lease = here[0]
        try:
            config = D.kea_config(kea, s["family"])
            reserved = [r for r in D.every_reservation(config, s["family"])
                        if ip.compressed in {addr(a) for a in r.get("addresses") or []}]
        except D.Refused as exc:
            raise Refused(f"Kea's configuration could not be read, so whether the address is "
                          f"reserved cannot be said: {exc}") from None
    except Refused as exc:
        p["refused"] = str(exc)
        return p
    p["lease"] = lease
    p["title"] = f"Release {ip.compressed}"
    p["subject"] = f"dhcp: {s['family']} lease {ip.compressed} released ({lease['identity']})"
    p["change"] = [("-", f"lease {words(lease)}")]
    if lease["state"] == "active":
        p["checks"].append(("note", f"active: its client last renewed it "
                                    f"{lease['last_seen'][:16].replace('T', ' ')} UTC. Kea "
                                    "cannot tell whether the client still uses the address: a "
                                    "client that does keeps using it until it next renews, and "
                                    "is then answered afresh"))
    else:
        p["checks"].append(("pass", f"{lease['state']}: no client holds it as active"))
    if reserved:
        r = reserved[0]
        same = (r.get("identity") or "").lower() == (lease.get("identity") or "").lower() or \
            (r.get("key") == "hw-address" and mac(r.get("identity")) == lease.get("mac"))
        p["checks"].append(("note" if same else "pass",
                            f"reserved for {D.WORDS.get(r.get('key'), r.get('key'))} "
                            f"{r.get('identity')}"
                            f"{' (this client)' if same else ''}: the reservation stays, and "
                            "Kea gives the address to that client at its next request"))
    else:
        p["checks"].append(("pass", f"no reservation names {ip.compressed}: the address returns "
                                    "to the subnet's pool, if it lies in one"))
    p["survives"] = [
        f"The release is recorded in {RECORD} in the repository of the network that owns this "
        "Kea, with the lease's client, who and why; Kea keeps no copy of a deleted lease.",
        "Nothing on the client changes: a lease deleted in Kea is not a message to the client.",
    ]
    p["hash"] = hashlib.sha256(json.dumps({"lease": bound(lease), "reserved": bool(reserved)},
                                          sort_keys=True).encode("utf-8")).hexdigest()
    p["ok"] = True
    return p


def apply(list_name: str, values, confirmed_hash: str, *, actor: str, reason: str,
          kea=None, record_with=None) -> dict:
    """``{ok, error, at, outcome, read_back, commit, plan}``: the previewed lease released,
    read back and recorded. ``at`` names the step reached (:data:`RUN_STEPS`)."""
    out = {"ok": False, "error": "", "outcome": "", "read_back": "", "rolled_back": "",
           "commit": "", "plan": None}
    if not (reason or "").strip():
        out["error"] = "a reason is recorded with every release; none was given"
        return out
    if kea is None:
        from modules.integrations.kea import KeaIntegration
        kea = KeaIntegration(list_name=list_name)
    p = plan(list_name, values, kea=kea)
    out["plan"] = p
    if not p["ok"]:
        out["error"] = p["refused"]
        return out
    if p["hash"] != confirmed_hash:
        out["error"] = (f"what the preview showed has changed ({confirmed_hash[:12]} -> "
                        f"{p['hash'][:12]}): Kea's lease on {p['address']} moved since; nothing "
                        "was released. Preview again")
        return out
    out["at"] = "release"
    got = release(kea, [p["lease"]])
    o = (got["outcomes"] or [{"outcome": "failed", "detail": got.get("error") or "no outcome"}])[0]
    if o["outcome"] != "released":
        out["error"] = o["detail"]
        out["at"] = o.get("step") or "release"
        return out
    out["read_back"] = f"Kea holds no lease on {p['address']} for {p['lease']['identity']}"
    out["outcome"] = "released"
    out["at"] = "record"
    rec = (record_with or record)(list_name, got["outcomes"], actor=actor, reason=reason,
                                  source="DHCP › Leases", subject=p["subject"])
    out["commit"] = rec.get("commit", "")
    if not rec.get("ok"):
        out["error"] = f"released in Kea and read back; the record failed: {rec.get('error')}"
        return out
    out["ok"] = True
    return out
