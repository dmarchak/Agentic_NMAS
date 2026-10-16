"""SSH host keys: kept on first contact, compared on every connection after (C906).

Mercury signed in to whatever answered at a device's address: `connection_params` passed no
host-key option, so Netmiko's default (`AutoAddPolicy`, nothing loaded, nothing kept) took
any key, and the NETCONF push set `hostkey_verify=False`. A device's credential went to
anything on its path.

**The rule.** The first time Mercury meets a device's key it KEEPS it (trust on first use,
recorded with who and when). Every later connection compares the key the device presents
with the one kept, before any credential is sent (paramiko asks the policy after the key
exchange and before authentication), and a different key is REFUSED naming both
fingerprints. A key that legitimately changed (a rebuilt device) is taken in one of two ways,
each recorded: a person's reviewed re-key (`modules/nsot/rekey_op.py`, a card on the device's
page), or a planned-restart window declared BEFORE the change that says the devices it covers
come back with new host keys (`restarts.record_planned(new_host_keys=True)`: a lab redeploy,
whose fresh disks make every key anew). A window accepts one new key per device, and never a
key it was declared after Mercury had already refused. Each key a window takes is in History
with the key it replaced and the window's reason, and once the window has closed ONE summary
("<n> new host keys accepted during '<reason>'") stays on Needs attention until a person
acknowledges it (`close_windows`, written by a reader; the operator, 2026-10-16).

**A device that leaves** (Retire, or an onboarding Abandoned) has its address's key FORGOTTEN
as a recorded step of that operation (`forget`, C940): the key moves into the record's
history with when, who and why, and the next machine to answer at the address is a first
contact. Never while any other device, in any network, has that address: the key is then
still that device's, and the operation says so naming both.

**The store** is ONE file for the installation, ``<data>/ssh_host_keys.json``, keyed by the
address Mercury connects to, the way OpenSSH's `known_hosts` is: what a key proves is who
answers at an address, and the one opener (`connection.open_ssh`) knows the address and not
the network. Onboarding meets a device before it belongs to any network, and one host
reaches one machine at one address, so two networks naming that address name the same
machine; two records of it could disagree. Owner-only (written through `filestore`, mkstemp
0600, replaced atomically), one writer (this module), every read-modify-write under one lock
across processes (`filestore.PathLock`). A store that exists and cannot be read, or that
someone else can write, REFUSES every connection rather than trusting: nothing kept could be
compared, and keeping a key over an unreadable record is how every pin would be lost.

Public keys are not secrets; the record still names no credential, and nothing here logs one.
"""

import base64
import hashlib
import json
import logging
import os
import stat
import time

log = logging.getLogger(__name__)

STORE = "ssh_host_keys.json"
VERSION = 1

#: The Netmiko/paramiko port a device's SSH answers on; NETCONF's is compared with the SAME
#: record (one device, one SSH server identity).
SSH_PORT = 22
NETCONF_PORT = 830

#: How a record came to hold its key.
FIRST_CONTACT = "first contact"
REKEYED = "re-keyed by a person"
WINDOW = "a planned window that expected new host keys"


class HostKeyRefused(RuntimeError):
    """A device answered with a key Mercury does not hold, or the record cannot be compared:
    the connection is closed before anything is sent."""

    def __init__(self, message: str, *, ip: str = "", offered: dict = None,
                 held: dict = None):
        super().__init__(message)
        self.ip = ip
        self.offered = dict(offered or {})
        self.held = dict(held or {})


class HostKeyStoreUnreadable(HostKeyRefused):
    """The record of host keys exists and cannot be read (or is writable by others)."""


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _epoch(text: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def path() -> str:
    from modules import config
    return os.path.join(config.DATA_DIR, STORE)


# ---------------------------------------------------------------------------
# Fingerprints, as `ssh-keygen -l` prints them
# ---------------------------------------------------------------------------

def fingerprint_of(blob: bytes) -> str:
    """``SHA256:<base64, unpadded>`` of a public key's wire form: `ssh-keygen -l`'s line."""
    return "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")


def md5_of(blob: bytes) -> str:
    """The colon-separated MD5 form, the one ncclient reports for an unknown key."""
    return ":".join(f"{b:02x}" for b in hashlib.md5(blob).digest())


def offered(key) -> dict:
    """``{"type", "fingerprint", "key"}`` for a paramiko key: its type, its SHA256
    fingerprint and its public blob (base64), which NETCONF verifies against."""
    blob = key.asbytes()
    return {"type": key.get_name(), "fingerprint": fingerprint_of(blob),
            "key": base64.b64encode(blob).decode()}


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------

def read() -> dict:
    """``{"version", "keys": {address: record}}``. Absent is EMPTY (no key kept yet); a file
    that cannot be read, is not a host-key record, or that a group or others may write,
    raises `HostKeyStoreUnreadable`, never empty."""
    p = path()
    if not os.path.exists(p):
        return {"version": VERSION, "keys": {}}
    try:
        mode = os.stat(p).st_mode
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise HostKeyStoreUnreadable(
                f"Mercury's record of SSH host keys ({p}) may be written by others (mode "
                f"{stat.S_IMODE(mode):o}, kept 0600), so no key in it can be trusted: nothing "
                "was sent")
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
    except HostKeyStoreUnreadable:
        raise
    except (OSError, ValueError) as exc:
        raise HostKeyStoreUnreadable(
            f"Mercury's record of SSH host keys ({p}) could not be read "
            f"({type(exc).__name__}: {exc}), so no device's key can be compared: nothing was "
            "sent. Repair or restore the file; Mercury never keeps a key over an unreadable "
            "record") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("keys"), dict):
        raise HostKeyStoreUnreadable(
            f"Mercury's record of SSH host keys ({p}) is not a host-key record (no `keys` "
            "table), so no device's key can be compared: nothing was sent")
    return doc


def _write(doc: dict) -> None:
    from modules.filestore import write_atomic
    doc["version"] = VERSION
    write_atomic(path(), json.dumps(doc, indent=1, sort_keys=True) + "\n")


def _lock():
    from modules.filestore import PathLock
    return PathLock(path)


def held(ip: str):
    """The record kept for *ip*, or None: none kept, or the one kept was forgotten when its
    device left (`forget`; the record then holds only its history). Raises
    `HostKeyStoreUnreadable`."""
    rec = read()["keys"].get(ip)
    return dict(rec) if rec and rec.get("fingerprint") else None


def refused() -> list:
    """Every record whose device last answered with a key Mercury refused, as
    ``[(address, record)]``. Raises `HostKeyStoreUnreadable`."""
    return sorted((ip, dict(rec)) for ip, rec in read()["keys"].items() if rec.get("refused"))


def _announce() -> None:
    """`host_keys`: a key was kept, replaced or refused, so Needs attention reads again."""
    try:
        from modules import invalidation
        invalidation.announce(["host_keys"], "host-keys", True)
    except RuntimeError:
        pass                              # a host script's process: nobody to tell
    except Exception:                     # noqa: BLE001 - a refusal never fails on telling
        log.warning("host_keys: the change could not be announced", exc_info=True)


# ---------------------------------------------------------------------------
# Who met the key, and which device answers at an address
# ---------------------------------------------------------------------------

def who(owner: str, ip: str) -> str:
    """Who and what made this connection: the operation holding the device in this thread
    and its actor, else the verified person of this request, else said as no verified person,
    always with the code that opened the session (*owner*)."""
    owner = owner or "an unnamed caller"
    try:
        from modules.nsot import device_ops
        hold = device_ops.held_by_this_thread(ip)
    except Exception:                     # noqa: BLE001 - attribution never blocks a connect
        hold = None
    if hold:
        return (f"{hold.get('actor') or 'an unnamed actor'} "
                f"({hold.get('operation') or 'an operation'}; {owner})")
    try:
        from modules import identity
        actor = identity.request_actor()
        if actor and actor != identity.UNAUTHENTICATED:
            return f"{actor} ({owner})"
    except Exception:                     # noqa: BLE001
        pass
    return f"no verified person ({owner})"


def _networks():
    """Every network in the registry as ``(ref, rows, error)``: its inventory's rows, or why
    they could not be read. Raises when the registry itself cannot be read."""
    from modules.device import get_device_lists, load_saved_devices
    from modules.nsot import listref
    for item in get_device_lists():
        try:
            ref = listref.resolve(item["name"])
            yield ref, load_saved_devices(ref.csv_path), ""
        except Exception as exc:          # noqa: BLE001 - said by the caller that needs it
            yield None, [], f"{item.get('name', '?')}: {type(exc).__name__}: {exc}"


def names_for(ip: str) -> list:
    """``[(network, device)]`` whose inventory names *ip*: read only on a refusal or a
    re-key, never on an ordinary connection."""
    out = []
    try:
        for ref, rows, error in _networks():
            if error:
                continue                  # one unreadable list names fewer
            out += [(ref.name, d.get("hostname", "")) for d in rows
                    if (d.get("ip") or "").strip() == ip and d.get("hostname")]
    except Exception:                     # noqa: BLE001
        log.debug("host_keys: no device named for %s", ip, exc_info=True)
    return out


def label(ip: str) -> str:
    """"r1 (192.0.2.1)", or the address alone when no inventory names it."""
    hosts = sorted({h for _l, h in names_for(ip)})
    return f"{', '.join(hosts)} ({ip})" if hosts else ip


def held_words(rec: dict) -> str:
    """"SHA256:… (ssh-rsa, kept 2026-10-16 by …)"."""
    return (f"{rec.get('fingerprint', '?')} ({rec.get('type', '?')}, kept "
            f"{str(rec.get('kept_at', ''))[:10] or 'at an unrecorded time'} by "
            f"{rec.get('kept_by') or 'an unrecorded caller'})")


def refusal_words(ip: str, got: dict, rec: dict) -> str:
    """The refusal, naming both operands (CLAUDE.md: a refusal names the comparison)."""
    return (f"{label(ip)} answered with SSH host key {got.get('fingerprint')} "
            f"({got.get('type')}) where Mercury holds {held_words(rec)}: nothing was sent. If "
            "the device was rebuilt or its key generated anew, re-key it on its page "
            "(Re-key…); otherwise something else answers at its address")


# ---------------------------------------------------------------------------
# The comparison: every SSH session's key, before any credential
# ---------------------------------------------------------------------------

def window_id(p: dict) -> str:
    """One planned window's identity: its list, when it was recorded, and when it opens."""
    return f"{p.get('list', '')}|{p.get('recorded_at', '')}|{p.get('from', '')}"


def _window_for(ip: str, rec: dict, got: dict, now: float):
    """The planned-restart window that accepts this new key, or None: declared to expect new
    host keys, covering a device at *ip* now, not already used by this device's record, and
    recorded BEFORE Mercury first refused this same key (a window declared after a refusal
    is not a review of it: that is the re-key's)."""
    try:
        from modules import restarts
        planned = restarts.planned_rows()
    except Exception as exc:              # noqa: BLE001 - unreadable plans accept nothing
        log.warning("host_keys: the planned-restart record could not be read (%s); no window "
                    "can accept a new key", exc)
        return None
    refused_at = 0.0
    prior = rec.get("refused") or {}
    if prior.get("fingerprint") == got["fingerprint"]:
        refused_at = _epoch(prior.get("first_at") or prior.get("at") or "")
    for lst, host in names_for(ip):
        for p in planned:
            if not p.get("new_host_keys"):
                continue
            if not restarts._window_covers(p, host, now, lst):
                continue
            wid = window_id(p)
            if rec.get("window", {}).get("id") == wid:
                continue                  # this window already took one new key for it
            if refused_at and _epoch(p.get("recorded_at", "")) >= refused_at:
                continue
            return {"id": wid, "by": p.get("by", ""), "why": p.get("why", ""),
                    "from": p.get("from", ""), "until": p.get("until", ""),
                    "device": host, "list": lst}
    return None


def _retired(rec: dict, at: float, by: str, why: str) -> dict:
    """An earlier key, kept in the record's history when a new one replaces it."""
    old = {k: rec.get(k) for k in ("type", "fingerprint", "kept_at", "kept_by", "how")}
    # A key kept under a window keeps its window and the key it replaced when it is replaced
    # in turn, so History and the window's summary still name both (the operator, 2026-10-16).
    old.update({k: rec[k] for k in ("window", "replaced") if rec.get(k)})
    old.update(replaced_at=_iso(at), replaced_by=by, replaced_why=why)
    return old


def check(ip: str, key, *, owner: str = "", port: int = SSH_PORT) -> dict:
    """Compare the key *ip* presents with the one kept, before anything is sent.
    ``{"state": "kept" | "matched" | "window", "record"}``; raises `HostKeyRefused` (a
    different key, nothing sent, the refusal recorded for Needs attention) or
    `HostKeyStoreUnreadable`."""
    got = offered(key)
    with _lock():
        # The time is taken UNDER the lock: a window's summary (`close_windows`) counts its
        # keys under this same lock once the window has closed, so no key can be kept under a
        # window after its summary was written.
        now = time.time()
        doc = read()
        rec = doc["keys"].get(ip)
        if rec is None or not rec.get("fingerprint"):
            # Nothing kept, or the key kept was forgotten when its device left (`forget`,
            # C940): the machine answering now is a first contact, and the record's history
            # (the forgotten key, who forgot it and why) stays with it.
            by = who(owner, ip)
            rec = dict(got, ip=ip, kept_at=_iso(now), kept_by=by, how=FIRST_CONTACT,
                       port=port, history=list((rec or {}).get("history") or []))
            doc["keys"][ip] = rec
            _write(doc)
            log.warning("ssh host key: kept %s's %s %s on first contact, for %s (C906)",
                        ip, got["type"], got["fingerprint"], by)
            state = "kept"
        elif rec.get("fingerprint") == got["fingerprint"] and rec.get("type") == got["type"]:
            if rec.get("refused"):
                rec.pop("refused", None)
                _write(doc)
                log.info("ssh host key: %s answers with the key Mercury holds again; its "
                         "refusal is cleared", ip)
                state = "matched"
            else:
                return {"state": "matched", "record": dict(rec)}
        else:
            window = _window_for(ip, rec, got, now)
            if window:
                by = who(owner, ip)
                new = dict(got, ip=ip, kept_at=_iso(now), kept_by=by, how=WINDOW,
                           port=port, window=window, replaced=rec.get("fingerprint", ""),
                           history=list(rec.get("history") or []) + [_retired(
                               rec, now, by, f"replaced under the planned window declared by "
                                             f"{window['by']}: {window['why']}")])
                doc["keys"][ip] = new
                _write(doc)
                log.warning("ssh host key: %s answered with a new key %s (was %s), kept under "
                            "the planned window declared by %s that expected new host keys",
                            ip, got["fingerprint"], rec.get("fingerprint"), window["by"])
                rec, state = new, "window"
            else:
                prior = rec.get("refused") or {}
                same = prior.get("fingerprint") == got["fingerprint"]
                rec["refused"] = {"type": got["type"], "fingerprint": got["fingerprint"],
                                  "at": _iso(now), "by": who(owner, ip), "port": port,
                                  "first_at": prior.get("first_at") if same else _iso(now),
                                  "count": (int(prior.get("count") or 0) + 1) if same else 1}
                _write(doc)
                words = refusal_words(ip, got, rec)
                log.error("ssh host key refused: %s", words)
                _announce()
                raise HostKeyRefused(words, ip=ip, offered=got, held=rec)
    _announce()
    return {"state": state, "record": dict(rec)}


def policy(ip: str, owner: str = "", port: int = SSH_PORT):
    """The paramiko policy every SSH session is opened with (`connection.open_ssh` sets it as
    Netmiko's `key_policy`). With nothing loaded into the client, paramiko asks it for every
    connection, after the key exchange and BEFORE authentication, so a refusal sends
    nothing."""
    import paramiko

    class _Pinned(paramiko.MissingHostKeyPolicy):
        def missing_host_key(self, client, hostname, key):
            check(ip, key, owner=owner, port=port)

    p = _Pinned()
    p.nmas_ip = ip
    return p


# ---------------------------------------------------------------------------
# NETCONF: the same record, never a first contact of its own
# ---------------------------------------------------------------------------

def _pinned_handler(device: str):
    """ncclient's device handler for *device*, kept from replacing Mercury's unknown-host
    answer. MEASURED against a real server (tests/test_host_keys.py): ncclient's IOS-XE
    handler (and its CSR and IOS-XR ones) sets ``unknown_host_cb`` to a function that answers
    True, "ignore the unknown host check", overriding the caller's, so `hostkey_verify=True`
    with a pinned key still signed in to ANY key. This subclass lets the handler add what it
    adds, then puts Mercury's answer back."""
    from ncclient import manager

    base = type(manager.make_device_handler({"name": device}))

    class Pinned(base):
        def add_additional_ssh_connect_params(self, kwargs):
            ours = kwargs.get("unknown_host_cb")
            super().add_additional_ssh_connect_params(kwargs)
            if ours is not None:
                kwargs["unknown_host_cb"] = ours

    Pinned.__name__ = f"Pinned{base.__name__}"
    return Pinned


def netconf_args(ip: str, device: str = "iosxe") -> tuple:
    """``(kwargs, seen)`` for `ncclient.manager.connect`: verify against the key kept for
    *ip* (``hostkey_b64``), and refuse anything else (``unknown_host_cb``), before
    authentication, with *device*'s handler kept from overriding that answer
    (`_pinned_handler`). *seen* collects what the device offered when it was refused.
    NETCONF keeps no key on first contact: a device with no record is refused, since its SSH
    session (every operation reads over SSH first) is where a key is kept and attributed."""
    rec = held(ip)
    if rec is None:
        raise HostKeyRefused(
            f"{label(ip)} has no SSH host key on record, and NETCONF never keeps one: "
            "nothing was sent. A session over SSH (any read of the device) keeps it first",
            ip=ip)
    seen = {}

    def unknown_host(host, fingerprint):
        seen["md5"] = fingerprint
        return False

    return {"hostkey_verify": True, "hostkey_b64": rec["key"],
            "unknown_host_cb": unknown_host,
            "device_params": {"name": device, "handler": _pinned_handler(device)}}, seen


def netconf_refusal(ip: str, md5: str) -> HostKeyRefused:
    """The refusal for a NETCONF session whose key was not the one kept. ncclient reports the
    offered key's MD5 only, so both are named in that form, with the held key's SHA256."""
    now = time.time()
    with _lock():
        doc = read()
        rec = doc["keys"].get(ip) or {}
        held_md5 = md5_of(base64.b64decode(rec.get("key") or "")) if rec.get("key") else "?"
        if rec:
            prior = rec.get("refused") or {}
            rec["refused"] = {"type": "", "fingerprint": f"MD5:{md5}", "at": _iso(now),
                              "by": who("pipeline:netconf", ip), "port": NETCONF_PORT,
                              "first_at": prior.get("first_at") or _iso(now),
                              "count": int(prior.get("count") or 0) + 1}
            _write(doc)
    _announce()
    words = (f"{label(ip)} answered NETCONF (port {NETCONF_PORT}) with a host key whose MD5 is "
             f"{md5}, where Mercury holds MD5 {held_md5}, {held_words(rec)}: nothing was "
             "sent")
    log.error("ssh host key refused: %s", words)
    return HostKeyRefused(words, ip=ip, offered={"md5": md5}, held=rec)


# ---------------------------------------------------------------------------
# A reviewed re-key: replace the kept key, compare-and-swap
# ---------------------------------------------------------------------------

def replace(ip: str, *, expected: str, new: dict, by: str, why: str) -> dict:
    """Keep *new* (``{"type", "fingerprint", "key"}``) for *ip* in place of the key whose
    fingerprint is *expected*, as *by*, keeping the old one in the record's history.
    ``{"ok", "error", "record"}``: refused, naming both, when the held key is not *expected*
    (someone re-keyed or it was kept meanwhile). The re-key operation's record."""
    now = time.time()
    with _lock():
        doc = read()
        rec = doc["keys"].get(ip)
        if rec is None or rec.get("fingerprint") != expected:
            return {"ok": False, "error": (
                f"Mercury now holds {held_words(rec) if rec else 'no key'} for {ip}, not the "
                f"{expected} the preview showed: nothing was replaced")}
        new_rec = dict({k: new[k] for k in ("type", "fingerprint", "key")}, ip=ip,
                       kept_at=_iso(now), kept_by=by, how=REKEYED, port=SSH_PORT, why=why,
                       history=list(rec.get("history") or []) + [_retired(rec, now, by, why)])
        doc["keys"][ip] = new_rec
        _write(doc)
    log.warning("ssh host key: %s re-keyed by %s: %s -> %s (%s)", ip, by, expected,
                new["fingerprint"], why)
    _announce()
    return {"ok": True, "error": "", "record": dict(new_rec)}


# ---------------------------------------------------------------------------
# A device that leaves: its address's key forgotten, kept in the history (C940)
# ---------------------------------------------------------------------------
#
# Retire and Abandon kept the key of the device that left, so the next machine at its address
# (a reused address, a throwaway onboarding) was refused as a changed key, and a pending device
# has no page to re-key from: onboarding there was blocked with no remedy. Now each forgets it
# as a recorded step, named in its preview: the key moves into the record's history with when,
# who and why, the record holds no key, and the next machine to answer there is a first
# contact (`check`). Never while any OTHER device, in any network, names the address: what a
# key proves is who answers at an address, so that device's key is the same key.

#: How a forgotten key is said in the record's history and on History.
FORGOTTEN = "forgotten when its device left"


def holders(ip: str, *, network: str = "", device: str = "") -> dict:
    """Every device but *device* in *network* whose address is *ip*, in every network: its
    inventory row, or its onboarding record (a pending device is in the manifest only).
    ``{"others": [(network, device)], "unreadable": [why]}``. A network that cannot be read
    is UNREADABLE, never "no other device": whether it names the address cannot be told."""
    from modules.nsot import listref, manifest

    ip = (ip or "").strip()
    me = (listref.resolve(network).name if network else "", device)
    others, unreadable = set(), []
    try:
        networks = list(_networks())
    except Exception as exc:              # noqa: BLE001 - said as the refusal
        return {"others": [], "unreadable": [f"the network registry: {exc}"]}
    for ref, rows, error in networks:
        if error:
            unreadable.append(error)
            continue
        others |= {(ref.name, d.get("hostname", "")) for d in rows
                   if (d.get("ip") or "").strip() == ip and d.get("hostname")}
        path = manifest.manifest_path(ref.repo_dir)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    entries = (json.load(fh) or {}).get("devices") or {}
            except (OSError, ValueError, AttributeError) as exc:
                unreadable.append(f"{ref.name}'s onboarding record ({path}): {exc}")
                continue
            others |= {(ref.name, e.get("name", "")) for e in entries.values()
                       if isinstance(e, dict) and e.get("name") and ip in (
                           (e.get("mgmt_ip") or "").strip(),
                           (e.get("reserved_address") or "").strip())}
    return {"others": sorted(o for o in others if o != me), "unreadable": unreadable}


def forget_plan(ip: str, *, network: str, device: str) -> dict:
    """What forgetting *ip*'s key for *device* leaving *network* would do, reading only:
    ``{"state": "held" | "none" | "shared" | "unreadable", "words", "fingerprint",
    "others"}``. *words* is the preview's sentence; *fingerprint* the key it would forget
    (the apply's compare-and-swap)."""
    ip = (ip or "").strip()
    out = {"state": "none", "fingerprint": "", "others": [], "ip": ip}
    if not ip:
        return dict(out, words=f"{device} has no address: no SSH host key to forget")
    try:
        rec = held(ip)
    except HostKeyStoreUnreadable as exc:
        return dict(out, state="unreadable", words=str(exc))
    if rec is None:
        return dict(out, words=f"Mercury keeps no SSH host key for {ip}: nothing to forget")
    found = holders(ip, network=network, device=device)
    if found["unreadable"]:
        return dict(out, state="unreadable", words=(
            f"whether another device has {ip} could not be told ("
            + "; ".join(found["unreadable"]) + "), so the SSH host key Mercury kept for it "
            "cannot be forgotten: could not read is not no other device"))
    if found["others"]:
        names = ", ".join(f"{h} in {n}" for n, h in found["others"])
        return dict(out, state="shared", others=found["others"], words=(
            f"the SSH host key Mercury kept for {ip} ({rec.get('fingerprint')}) is KEPT, not "
            f"forgotten: {device} in {network} leaves, and {ip} is also the address of "
            f"{names}, so the key is still that device's"))
    return dict(out, state="held", fingerprint=rec.get("fingerprint", ""), words=(
        f"forget the SSH host key Mercury kept for {ip}: {held_words(rec)}. The next machine "
        "to answer there is a first contact; the key stays in the record's history, with who "
        "forgot it and why"))


def forget(ip: str, *, network: str, device: str, by: str, why: str,
           expected: str = "") -> dict:
    """Forget the key kept for *ip* as *device* leaves *network*, as *by*, for *why*: the key
    moves into the record's history (`_retired`, with the device and network it was
    forgotten for) and the record holds no key. ``{"ok", "state", "error", "record",
    "forgot"}``; *state* is ``forgotten``, ``none`` (nothing kept: done already), ``shared``
    or ``unreadable`` (refused, naming why), or ``moved`` (the key held is not *expected*,
    the one the preview showed: nothing forgotten)."""
    from modules.nsot import listref

    ip = (ip or "").strip()
    network = listref.resolve(network).name if network else ""
    plan = forget_plan(ip, network=network, device=device)
    if plan["state"] in ("shared", "unreadable"):
        return {"ok": False, "state": plan["state"], "error": plan["words"], "record": None,
                "others": plan["others"]}
    now = time.time()
    with _lock():
        doc = read()
        rec = doc["keys"].get(ip)
        if not rec or not rec.get("fingerprint"):
            return {"ok": True, "state": "none", "error": "", "record": None,
                    "words": f"Mercury keeps no SSH host key for {ip}: nothing to forget"}
        if expected and rec.get("fingerprint") != expected:
            return {"ok": False, "state": "moved", "record": None, "error": (
                f"Mercury now holds {held_words(rec)} for {ip}, not the {expected} the "
                "preview showed: nothing was forgotten")}
        old = dict(_retired(rec, now, by, why), forgotten=True, device=device,
                   network=network)
        new = {"ip": ip, "history": list(rec.get("history") or []) + [old],
               "forgotten_at": _iso(now), "forgotten_by": by, "forgotten_why": why}
        doc["keys"][ip] = new
        _write(doc)
    log.warning("ssh host key: %s's %s forgotten by %s as %s left %s (%s)", ip,
                old.get("fingerprint"), by, device, network, why)
    _announce()
    return {"ok": True, "state": "forgotten", "error": "", "record": dict(new),
            "forgot": dict(old)}


# ---------------------------------------------------------------------------
# A window's keys, summed up once it has closed (the operator, 2026-10-16)
# ---------------------------------------------------------------------------
#
# A window that expects new host keys takes each one without a person looking at it. Each is
# in History (`history_sources.host_keys`: the device, the new key, the key it replaced, the
# window's reason); once the window can take no more, ONE summary row says how many it took,
# and Needs attention shows it until a person acknowledges it (`attention.host_key_source`).
# The close is OBSERVED by a reader that runs each minute (`modules/readers/
# host_key_windows.py`), never inferred when a page is read, and written once per window.

#: The summaries, one line per closed window: append-only, owner-only (a person's name and
#: reason are in it).
SUMMARIES = "host_key_windows.jsonl"


def summaries_path() -> str:
    from modules import config
    return os.path.join(config.DATA_DIR, SUMMARIES)


def closes_at(p: dict) -> float:
    """When window *p* can take no more keys: its end plus the slack in which a restart (and
    so a new key) is still the plan's (`restarts.PLANNED_SLACK_SECONDS`, the slack
    `_window_for` gives it through `restarts._window_covers`)."""
    from modules import restarts
    return restarts._epoch(p.get("until", "")) + restarts.PLANNED_SLACK_SECONDS


def accepted_under(wid: str, doc: dict = None) -> list:
    """Every key kept under window *wid*, held now or replaced since: ``[{"device", "list",
    "ip", "type", "fingerprint", "replaced", "kept_at", "kept_by"}]``, by address. *replaced*
    is the key it took the place of. Raises `HostKeyStoreUnreadable`."""
    doc = read() if doc is None else doc
    out = []
    for ip, rec in sorted(doc["keys"].items()):
        chain = list(rec.get("history") or []) + [rec]
        for i, k in enumerate(chain):
            w = k.get("window") or {}
            if k.get("how") != WINDOW or w.get("id") != wid:
                continue
            before = k.get("replaced") or (chain[i - 1].get("fingerprint", "") if i else "")
            out.append({"device": w.get("device", ""), "list": w.get("list", ""), "ip": ip,
                        "type": k.get("type", ""), "fingerprint": k.get("fingerprint", ""),
                        "replaced": before, "kept_at": k.get("kept_at", ""),
                        "kept_by": k.get("kept_by", "")})
    return out


def summaries() -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows", "error"?}``: the closed windows'
    summaries, oldest first. Unreadable is its own answer, never "none written"."""
    from modules import restarts
    return restarts._read_jsonl(summaries_path())


def summary_words(s: dict) -> str:
    """"2 new host keys accepted during 'lab redeploy'" (the operator's words)."""
    n = int(s.get("count") or 0)
    return f"{n} new host key{'' if n == 1 else 's'} accepted during '{s.get('why', '')}'"


def close_windows(now: float = None, planned: list = None) -> dict:
    """Write ONE summary for every window that expected new host keys and has CLOSED (its end
    plus the slack has passed) and has none yet. ``{"written": [summary], "closed",
    "open"}``. Idempotent across runs and processes: under the host-key record's lock (so no
    key is kept meanwhile: `check` takes its time under it) and the summaries' own lock, a
    window already summed up is skipped. Raises `HostKeyStoreUnreadable` or RuntimeError (a
    record that cannot be read), so the reader's failure is a job-health row."""
    from modules import restarts
    from modules.config import open_secure
    from modules.filestore import PathLock

    planned = restarts.planned_rows() if planned is None else planned
    expecting = [p for p in planned if p.get("new_host_keys")]
    with _lock():
        now = time.time() if now is None else now
        closed = [p for p in expecting if now > closes_at(p)]
        written = []
        if closed:
            doc = read()
            with PathLock(summaries_path):
                got = summaries()
                if got["state"] == "unreadable":
                    raise RuntimeError(f"the host-key windows' summaries ({summaries_path()}) "
                                       f"could not be read ({got.get('error')}), so whether a "
                                       "window was summed up already cannot be told: nothing "
                                       "was written")
                done = {r.get("window") for r in got["rows"]}
                for p in closed:
                    wid = window_id(p)
                    if wid in done:
                        continue
                    keys = accepted_under(wid, doc)
                    row = {"window": wid, "list": p.get("list", ""), "by": p.get("by", ""),
                           "why": p.get("why", ""), "from": p.get("from", ""),
                           "until": p.get("until", ""), "devices": list(p.get("devices") or []),
                           "closed_at": _iso(closes_at(p)), "written_at": _iso(now),
                           "count": len(keys), "keys": keys}
                    with open_secure(summaries_path(), "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(row, sort_keys=True) + "\n")
                    done.add(wid)
                    written.append(row)
                    log.warning("ssh host keys: %s (window declared by %s, closed %s)",
                                summary_words(row), row["by"], row["closed_at"])
    if written:
        _announce()
    return {"written": written, "closed": len(closed), "open": len(expecting) - len(closed)}
