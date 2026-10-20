"""Retire a device from NMAS management: the whole exit, not a CSV delete.

OPEN_FINDINGS **C11**. ``POST /device/<ip>/delete`` removes the CSV row and
nothing else, and measured on r5 that leaves the device half-managed in five
places: still bound to its template (every approval keeps validating against
it), still given a heartbeat rule, and its intent and golden in the working
tree. It also destroys the only stored copy of the device's
credential.

**What retire does**, in order, each step skipped if already done so a run
that stops part way is finished by running it again:

1. clears the device's credential override, if it has one;
2. removes ``host_vars/<h>.yml`` and ``golden/<h>.cfg`` and releases the
   identity in ONE commit, so history keeps both and the tree does not.
   Template approvals are NOT withdrawn: scheme 3 approves the template,
   never its devices (P.5), so the plan says so rather than asking for a
   re-approval nobody needs (it did until 2026-09-28, true only before P.5);
0. FIRST, masks the credentials NetBox still holds in the device's stored config
   context, when NetBox writes are on and NMAS recorded writing that context
   (C139: after retire no import reaches the device again, so a credential
   left there stays for good). One implementation with
   `scripts/nmas-netbox-mask-context` (`modules/netbox_context_mask.py`),
   read back after the write. It is the first step, so a failed mask stops
   the retirement with nothing else done;
3. after the commit, deletes the device's file from the deprecated `golden_configs/` store
   (C176), but only when its content survives in the repository (the
   migration's verbatim backup or an equivalent committed golden), and says
   where; a file whose lines exist nowhere else is kept and named;
3a. forgets the SSH host key Mercury kept for its address (C940: `host_keys.forget`, the
   key kept in the record's history with who, when and why), so the next machine there is a
   first contact; KEPT, and said, while another device in any network has the address, and
   refused when whether one does cannot be read;
4. deletes the CSV row, LAST, and only against a break-glass record that
   holds this device's CURRENT credential.

**It leaves nothing a new device of the same name could inherit** (the operator's
device-lifecycle rule, 2026-10-19; C1332 to C1342): every per-device artefact is removed or
archived, and the name is free. :data:`STEPS` is the whole list, in order: besides the above,
the credential overrides at every address the device was known by and its staged credential
(``staged``), its Kea reservations (``reservations``), every Kea lease held for its MAC or an
address it was known by (``leases``, C1403: a lease outlives its reservation and refuses the
address to the next device), its template override (in the commit),
its golden tags archived under ``retired/`` (``tags``), its rollback block archived in the
retire commit and cleared (``rolled_back``), its approval-queue items withdrawn
(``approvals``), its rotation-policy memberships (``rotation_policy``), its Topology
declaration and place (``topology``), its Grafana heartbeat rule (``heartbeat``) and its
NetBox record set to Decommissioning and renamed, Mercury's created-object entry marked
retired (``netbox_record``). Readers keyed by the name (restore points, receipts, rotation
age) count only what came after the name's newest retirement (:func:`retirements`).

The steps were modelled on r5's retirement (`3592113`, 2026-09-25, the
operator's model for 7.3): its six `Not-Done:` trailers are the list the
screen draws before the confirm and again in the result, and the gaps that
retirement left (the legacy file, the heartbeat rule, the scrape targets,
NetBox's stored credentials) are closed here or named with who closes them.

**The credential is a refusal, not a step.** A sequence whose first step can
be skipped will be skipped, and the CSV row is the only copy NMAS holds of a
rotated password. Two bases, and each says which it is:

- the CLI (``nmas-retire --breakglass <file>``) OPENS the record (the
  passphrase read from the terminal) and refuses unless it has an entry for
  this device in this list whose username and password equal the row's;
- the Device page cannot open a record on the operator's laptop, so it
  trusts the EXPORT LOG (C182): the newest export for this list must have
  recorded this device's current credential digest. The log says what was
  WRITTEN; it cannot show the file still exists or that its passphrase is
  known. The screen states that difference (the operator, 2026-09-28).

Either way an export taken before the last rotation does not count.

**What retire does NOT do, stated every time**, because each is correct and
each looks like an omission unless it is named: the NetBox device stays, set to
Decommissioning and renamed (NetBox records what exists, not what NMAS manages); the device's running
configuration is not changed; and a session the app has pooled is not closed by a command
that runs outside it. (Oxidized's polling was named here until Oxidized was retired, Phase 3,
2026-10-08; "backups are kept" until today's Backups left, 7.8, 2026-10-15.)

**What watches it afterwards, in two kinds** (board 12, the operator,
2026-10-03; `_watchers`): GENERATED, dropped at the next regeneration and
said with when (Prometheus's scrape targets, generated from the inventory
when a target directory is set, drop a device with no golden at the
keeper's next run; the heartbeat rule leaves the generated rules file with
retire's own ``heartbeat`` step, and Grafana drops it once the host step
installs that file), and
SURVIVES, named with how it is removed (the NetBox device,
a hand-built dashboard panel, the template's approval).
"""

import hashlib
import json
import logging
import os
import time

log = logging.getLogger(__name__)


class RetireRefused(Exception):
    pass


#: Every step retirement can take, in the order `apply` runs them: `plan()["steps"]`'s keys.
#: The manual's page names each (tests/test_manual.py reads this tuple).
STEPS = ("netbox_mask", "override", "staged", "reservations", "leases", "commit", "tags",
         "rolled_back", "approvals", "rotation_policy", "topology", "heartbeat", "netbox_record",
         "legacy", "host_key", "row")

#: The namespace a retired device's golden tags are archived under:
#: ``retired/<device>/<identity>/<the tag's time>``. Never listed as a restore point.
ARCHIVE_PREFIX = "retired"


def _addr_key(value: str) -> str:
    """An address as one comparable string: an IPv4 or IPv6 address in its compressed form
    (``2001:DB8:0::5`` and ``2001:db8::5`` are one address), anything else stripped."""
    import ipaddress

    text = (value or "").strip()
    try:
        return ipaddress.ip_address(text).compressed
    except ValueError:
        return text.lower()


def retirements_in(repo: str) -> dict:
    """Every retired name in *repo*, newest retirement each: ``{name lowercased: {"name",
    "sha", "at", "epoch"}}``, from the retire commits' `Retired-Device:` trailers (one `git
    log`). A record keyed by a device's NAME (a receipt, a rotation, a tag) from at or before
    its name's newest retirement is the retired device's, never a new device's of that name
    (C1332, C1334, C1336). {} when the history cannot be read."""
    from modules.nsot import repo as R

    rc, out, _err = R.git(repo, "log", "--format=%H%x1f%ct%x1f%cI%x1f%B%x1e",
                          "--fixed-strings", "--grep=Retired-Device: ")
    if rc != 0:
        return {}
    found = {}
    for chunk in (out or "").split("\x1e"):
        parts = chunk.strip().split("\x1f")
        if len(parts) != 4:
            continue
        sha, ct, at, body = parts
        for line in body.splitlines():
            key, sep, value = line.partition(": ")
            if sep and key == "Retired-Device" and value.strip():
                name = value.strip()
                if name.lower() not in found:          # newest first
                    found[name.lower()] = {"name": name, "sha": sha, "at": at,
                                           "epoch": int(ct)}
    return found


def retirements(list_name: str) -> dict:
    """:func:`retirements_in` for *list_name*'s repository, found WITHOUT creating the list
    (C51); {} when it has none."""
    from modules.config import list_data_path

    repo = os.path.join(list_data_path(list_name), "config_repo")
    if not os.path.isdir(os.path.join(repo, ".git")):
        return {}
    return retirements_in(repo)


def before_retirement(cut: dict, name: str, at) -> bool:
    """Is a record about *name* made at *at* (epoch seconds, or an ISO-8601 UTC string) the
    retired device's? True when *name* was retired at or after *at*, or *at* cannot be read
    for a retired name (a record that cannot be dated after the retirement is not the new
    device's). *cut* is :func:`retirements`'s."""
    import calendar

    c = (cut or {}).get((name or "").lower())
    if not c:
        return False
    if isinstance(at, (int, float)):
        return at <= c["epoch"]
    try:
        epoch = calendar.timegm(time.strptime(str(at or "")[:19], "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return True
    return epoch <= c["epoch"]


def _norm(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _list_paths(list_name: str) -> tuple:
    """(list dir, csv path). From the REGISTRY: a mistyped name is refused,
    never created by `get_list_data_dir()`."""
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists

    match = next((l for l in get_device_lists() if l["name"] == list_name), None)
    if match is None:
        raise RetireRefused(f"no device list named {list_name!r}")
    base = os.path.join(LISTS_DIR, match["filename"])
    return base, os.path.join(base, "devices.csv")


def _is_netbox_sourced(list_dir: str) -> bool:
    try:
        with open(os.path.join(list_dir, "source.json"), encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("type") == "netbox"
    except (OSError, ValueError):
        return False


def _netbox_facts(list_name: str, hostname: str) -> dict:
    try:
        from modules import netbox_guard
        from modules.netbox_client import _nb_first, _nb_ready

        ok, err, session, base = _nb_ready()
        if not ok:
            # NOT CONFIGURED is its own fact: there is no NetBox to hold
            # anything. An unreachable one is not (below, `configured` True).
            return {"checked": False, "configured": False, "reason": err}
        dev = _nb_first(session, base, "dcim/devices/", name=hostname)
        if not dev:
            return {"checked": True, "exists": False}
        return {"checked": True, "exists": True, "id": dev["id"], "device": dev,
                "writes": netbox_guard.writes_allowed(),
                "tags": sorted(t.get("slug", "") for t in dev.get("tags") or []),
                "created_by_nmas": netbox_guard.was_created_by_nmas(
                    list_name, "dcim/devices", dev["id"])}
    except Exception as exc:                   # noqa: BLE001
        return {"checked": False, "configured": True, "reason": str(exc)}


def plan(list_name: str, hostname: str, reason: str = "") -> dict:
    """Everything retire would do, everything it will not, and why it would
    refuse. Reads only."""
    from modules.device import load_saved_devices
    from modules.nsot import approval, manifest, repo as R
    from modules.nsot import templates_repo

    out = {"ok": True, "list_name": list_name, "hostname": hostname,
           "reason": reason, "refusals": [], "refused_by": {}, "steps": [],
           "not_doing": [], "advisories": []}
    try:
        list_dir, csv_path = _list_paths(list_name)
    except RetireRefused as exc:
        return {**out, "ok": False, "refusals": [str(exc)], "refused_by": {"list": str(exc)}}
    repo = os.path.join(list_dir, "config_repo")

    def refuse(key, text):
        # Keyed as well as listed: the screen draws each check as a gate by
        # name (REFUSAL_GATES), and a refusal with no gate would be a
        # reason drawn nowhere.
        out["refusals"].append(text)
        out["refused_by"][key] = text

    if not (reason or "").strip():
        refuse("reason", "a reason is required -- it goes into the commit, the "
               "unmapped declaration and the history, and 'retired' on its "
               "own tells the next reader nothing")
    if _is_netbox_sourced(list_dir):
        refuse("source", "this list's inventory is NetBox's: retire the device there")

    row = next((d for d in load_saved_devices(csv_path)
                if d.get("hostname") == hostname), None)
    identity, entry = manifest.find_by_name(repo, hostname)
    from modules.nsot.hostvars import committed_rel
    rel_intent = committed_rel(hostname)      # the one producer (C175)
    rel_golden = f"golden/{hostname}.cfg"
    files = [rel for rel in (rel_intent, rel_golden)
             if os.path.exists(os.path.join(repo, rel))]
    # Its per-device template override (C1337): removed in the retire commit, so a new device
    # of the name is rendered through its platform's template, never the retired one's.
    try:
        override_tpl = templates_repo.load_bindings(repo)["overrides"].get(hostname) or ""
    except templates_repo.BindingsUnreadable as exc:
        refuse("bindings", str(exc))
        override_tpl = ""
    if row is None and identity is None and not files and not override_tpl:
        refuse("present", f"{hostname!r} is not in list {list_name!r}: nothing to retire")
    if hostname in {p.get("name") for p in manifest.pending_devices(repo)}:
        refuse("pending", f"{hostname} is pending onboarding: use abandon, which also "
               "reverses what onboarding created")

    watched = ["host_vars", "golden", ".nsot/manifest.json"] + (
        [_bindings_rel()] if override_tpl else [])
    rc, dirty, _e = R.git(repo, "status", "--porcelain", "--", *watched)
    if rc != 0 or dirty.strip():
        refuse("clean", "uncommitted changes under host_vars/, golden/, the manifest"
               + (" or templates/bindings.yml" if override_tpl else "")
               + " would ride into the retire commit: " + (dirty.strip() or "git status failed"))

    ip = (row or {}).get("ip") or (entry or {}).get("mgmt_ip") or ""
    # EVERY address the device was known by (C1340): its row's, its manifest's and the address
    # ZTP reserved for it, as abandon clears them. An override at an address another device
    # now has is that device's, and is kept.
    from modules import credentials
    known = [a for a in dict.fromkeys([ip, (entry or {}).get("mgmt_ip") or "",
                                       (entry or {}).get("reserved_address") or ""]) if a]
    overrides, kept_overrides = [], []
    try:
        for addr in known:
            if not credentials.has_device_override(addr):
                continue
            if addr != ip:
                from modules import host_keys
                held_by = host_keys.holders(addr, network=list_name, device=hostname)
                if held_by["unreadable"]:
                    raise RuntimeError("whether another device has " + addr + " could not be "
                                       "told (" + "; ".join(held_by["unreadable"]) + ")")
                if held_by["others"]:
                    kept_overrides.append(
                        f"the credential override at {addr} (the address reserved for "
                        f"{hostname}) is KEPT: it is now the address of "
                        + ", ".join(f"{h} in {n}" for n, h in held_by["others"]))
                    continue
            overrides.append(addr)
    except Exception as exc:                   # noqa: BLE001
        refuse("credentials", f"the credential store could not be checked: {exc}")
        overrides = []
    has_override = bool(overrides)

    # Scheme 3 (P.5) approves the TEMPLATE, never its devices: releasing one
    # changes no approval. This listed "this withdraws the approval ...
    # re-approve it" until 2026-09-28, which was true for r5's retirement
    # (2026-09-25, scheme 2) and false from the next day on. Only a LIVE approval stays
    # approved: a revoked template's tombstone is no approval to keep (C955; C936's
    # `unrevoked_templates`, the one listing of approvals that still stand).
    still_approved = [tpl for tpl in approval.unrevoked_templates(repo)
                      if hostname in {b["device"] for b in
                                      templates_repo.devices_for_template(repo, tpl)}]

    def step(key, text, done):
        out["steps"].append({"key": key, "what": text, "done": done})

    # The mask goes FIRST: a failed mask then stops the retirement with
    # nothing else done (C139).
    nb = _netbox_facts(list_name, hostname)
    mask = _mask_facts(nb)
    if mask.get("refuse"):
        refuse("netbox_mask", mask["refuse"])
    if mask.get("step"):
        step("netbox_mask", mask["step"], mask["done"])
    step("override", ("clear the credential override for " + " and ".join(overrides)
                      + (" (every address it was known by)" if len(overrides) > 1 else ""))
         if has_override else "no credential override to clear",
         not has_override)
    out["not_doing"] += kept_overrides

    work = {}

    def take(key, facts):
        """A step from its facts: a refusal by name, what is said as not done, the step."""
        if facts.get("refuse"):
            refuse(key, facts["refuse"])
        out["not_doing"].extend(facts.get("not_doing") or [])
        if facts.get("step"):
            step(key, facts["step"], facts["done"])
        if facts.get("work"):
            work[key] = facts["work"]

    # Its staged credential and an adoption's sidecar (C1340), as abandon clears them.
    take("staged", _staged_facts(repo, hostname, row))
    # Its Kea reservations, ZTP's and the DHCP page's (C1335), before the commit as abandon
    # removes them first: an address reserved for a device nobody knows refuses the next one.
    take("reservations", _reservation_facts(list_name, hostname, entry, known))
    # Every lease Kea holds for it (C1403), after its reservations go: a lease outlives its
    # reservation and refuses the address to the next device until it ends.
    take("leases", _lease_facts(list_name, hostname, entry, known,
                                (work.get("reservations") or {}).get("ztp") or []))
    step("commit", "one commit: remove " + (", ".join(files) or "(nothing)")
         + (f", and its template override ({override_tpl}) from {_bindings_rel()}"
            if override_tpl else "")
         + (f", and release identity {identity}" if identity else "")
         + " -- history keeps all of it",
         identity is None and not files and not override_tpl)
    # What is keyed by its NAME and would pass to a new device of the name (C1332 to C1341),
    # each after the commit: archived or withdrawn, recorded, never deleted unread.
    take("tags", _tag_facts(repo, hostname, identity or _former_identity(repo, hostname)))
    take("rolled_back", _rolled_back_facts(repo, hostname))
    take("approvals", _approval_facts(list_name, hostname, known))
    take("rotation_policy", _policy_facts(list_name, hostname))
    take("topology", _topology_facts(list_name, hostname))
    # Its heartbeat rule never refuses: a rules file that cannot be read is said in what
    # still watches it (`_watchers`), the hourly check naming the rule EXTRA meanwhile.
    hb = _heartbeat_facts(hostname)
    if hb.get("step"):
        step("heartbeat", hb["step"], hb["done"])
    if hb.get("work"):
        work["heartbeat"] = hb["work"]
    # Its NetBox record and Mercury's created-object entry (C1342).
    nbr = _netbox_record_facts(list_name, hostname, nb)
    take("netbox_record", nbr)
    legacy = _legacy_facts(list_name, list_dir, hostname, ip)
    if legacy.get("step"):
        step("legacy", legacy["step"], legacy["done"])
    # The SSH host key Mercury kept for its address (C940): forgotten, so the next machine
    # there is a first contact, unless another device in any network has the address (then
    # the key is still that device's, said below). Before the row: a run that stops after the
    # row could not be run again (no row, no identity, no files: "nothing to retire").
    hk = _host_key_facts(ip, list_name, hostname)
    if hk["state"] == "unreadable":
        refuse("host_key", hk["words"])
    elif hk["state"] == "shared":
        out["not_doing"].append(hk["words"])
    else:
        step("host_key", hk["words"], hk["state"] == "none")
    out["host_key"] = {k: hk.get(k) for k in ("state", "fingerprint", "others")}
    # Oxidized's router.db row (C398) is no longer a step: Oxidized is retired (Phase 3 step 2,
    # 2026-10-08), and its store goes with it (Phase 3 section 5's host steps).
    step("row", f"delete the CSV row for {ip} -- the only stored copy of its "
         "credential, so a break-glass record holding it is required",
         row is None)

    if not nb.get("checked"):
        out["not_doing"].append(f"NetBox: not changed, and could not be asked "
                                f"({nb.get('reason')})")
    elif nb.get("exists"):
        out["not_doing"].append(
            f"NetBox device {nb['id']} is KEPT: NetBox records what exists, not "
            f"what Mercury manages (tags: {', '.join(nb['tags']) or 'none'}). "
            + ("Mercury created it, so its provenance record stays and Remove "
               "could still delete it -- a separate decision."
               if nb["created_by_nmas"] else
               "Mercury did not create it, so Remove cannot touch it.")
            + (" " + mask["kept"] if mask.get("kept") else ""))
    else:
        out["not_doing"].append("NetBox: no device of this name, nothing kept")
    for tpl in still_approved:
        out["not_doing"].append(
            f"the approval of {tpl} is not withdrawn: an approval is of the template, "
            f"never of its devices (scheme 3), so it stays approved; its recorded "
            f"evidence still names {hostname}, as history")
    out["not_doing"] += [n for n in (mask.get("not_doing"), legacy.get("not_doing")) if n]
    # Board 12: what is GENERATED is dropped at its next regeneration, said with when; what
    # SURVIVES is named with how it is removed. Both are the commit's Not-Done trailers too.
    watchers = _watchers(hostname, ip, list_name, hb)
    out["generated"] = [w for w in watchers if w["kind"] == "generated"]
    out["survives"] = [w for w in watchers if w["kind"] == "survives"]
    if nb.get("checked") and nb.get("exists"):
        renamed = (nbr.get("work") or {}).get("patch") or {}
        out["survives"].insert(0, {
            "kind": "survives", "what": f"the NetBox device {nb['id']}",
            "how": (("KEPT, set to Decommissioning and renamed " + renamed["name"]
                     + " so the name is free" if renamed else
                     "KEPT, NOT set to Decommissioning or renamed (NetBox writes are off "
                     "here), so its name stays taken in NetBox")
                    + ", its credential masked: delete it in NetBox if it is gone for good"
                    + (" (Mercury created it, so Remove could also delete it, a separate "
                       "decision)" if nb["created_by_nmas"] else
                       " (Mercury did not create it, so Mercury never deletes it)"))})
    out["survives"] += [{"kind": "survives", "what": f"the approval of {tpl}",
                         "how": "stays: an approval is of the template, never of its devices"}
                        for tpl in still_approved]
    out["not_doing"] += [f"{w['what']}: {w['how']}" for w in watchers]
    out["not_doing"] += [
        "its running configuration is not changed",
        "a session the app has pooled to it is not closed by this command, "
        "which runs outside the app; the app's idle reaper closes it within "
        "two minutes of its last use (C97)",
    ]
    golden_path = os.path.join(repo, rel_golden)
    if os.path.exists(golden_path):
        with open(golden_path, encoding="utf-8", errors="replace") as fh:
            if "event manager applet NMAS-HEARTBEAT" in fh.read():
                out["advisories"].append(
                    "its golden shows the NMAS-HEARTBEAT applet: the device "
                    "still carries Mercury's configuration after it leaves "
                    "management. The deploy path cannot remove it (C12); take "
                    "it off by hand and save the golden first")

    out["ok"] = not out["refusals"]
    if mask.get("advisory"):
        out["advisories"].append(mask["advisory"])
    out["identity"], out["ip"], out["files"] = identity, ip, files
    out["overrides"], out["template_override"] = overrides, override_tpl
    out["work"] = work
    out["legacy_path"] = legacy.get("path", "")
    out["breakglass_log"] = (breakglass_logged(list_name, row) if row is not None
                             else {"ok": True, "why": "", "export": None,
                                   "statement": "no CSV row: no credential to protect"})
    out["hash"] = hashlib.sha256(_norm({
        "steps": out["steps"], "reason": reason, "files": {
            rel: _blob(os.path.join(repo, rel)) for rel in files},
        "row": bool(row), "identity": identity, "work": work}).encode()).hexdigest()[:16]
    return out


def _bindings_rel() -> str:
    """The template bindings' path in the repository (`templates_repo.bindings_path`'s)."""
    from modules.nsot import templates_repo as T

    return f"{T.TEMPLATES_REL}/{T.BINDINGS_FILE}"


def _identity_slug(identity: str) -> str:
    """An identity as one ref-name component (``uid:<uuid>`` has a colon, never in a ref)."""
    import re

    return re.sub(r"[^A-Za-z0-9._-]", "-", identity or "") or "unrecorded"


def _former_identity(repo: str, hostname: str) -> str:
    """The identity *hostname* had before its newest retire commit, for a run finishing a
    retirement whose commit already released it; "" when there is none."""
    rec = retired_record(repo, hostname)
    return _entry_before(repo, rec["sha"], hostname)[0] if rec else ""


def _staged_facts(repo: str, hostname: str, row) -> dict:
    """Its staged credential (`.nsot/staging/credential/<h>.enc`) and an adoption's sidecar
    (C1340): deleted, as abandon deletes them, only when the staged password is the CSV row's,
    which the break-glass export holds. A different one is what an interrupted rotation or
    adoption left, perhaps the only copy of what the device accepts now: refused, naming the
    recovery. Compared in memory; no value is returned."""
    import hmac

    from modules.device import open_stored
    from modules.nsot import adopt as A
    from modules.nsot import credential_rotation as CR

    rel_enc = f"{CR.STAGING_REL}/{hostname}.enc"
    rel_side = f"{A.SIDECAR_REL}/{hostname}.json"
    has_enc = os.path.exists(os.path.join(repo, rel_enc))
    has_side = os.path.exists(os.path.join(repo, rel_side))
    if not has_enc and not has_side:
        return {"step": "no staged credential or adoption sidecar to delete", "done": True}
    if has_enc:
        recovery = "scripts/nmas-adopt-recover" if has_side else "scripts/nmas-rotation-recover"
        try:
            staged = CR.staged_plaintext(repo, hostname) or ""
        except Exception as exc:               # noqa: BLE001 - said as the refusal
            return {"refuse": (f"the staged credential {rel_enc} could not be opened "
                               f"({type(exc).__name__}), so whether it is the only copy of "
                               "the device's password cannot be told: could not read is not "
                               f"nothing there. Settle it with {recovery}, then retire")}
        current, unopened = open_stored(row) if row else ("", "there is no CSV row")
        if unopened or not current or not hmac.compare_digest(staged.encode(),
                                                              current.encode()):
            return {"refuse": (
                f"{rel_enc} holds a staged password that is not the CSV row's: an interrupted "
                + ("adoption" if has_side else "rotation") + " left it, and it may be the "
                "only copy of what the device accepts now. Settle it with " + recovery
                + ", then retire")}
    return {"step": "delete " + " and ".join(x for x in (
        f"the staged credential {rel_enc} (the same password as the CSV row's, which the "
        "break-glass export holds)" if has_enc else "",
        f"the adoption's sidecar {rel_side}" if has_side else "") if x), "done": False}


def _dhcp_held(list_name: str) -> list:
    """Every reservation in Mercury's DHCP subnet files (`dhcp_reservations.held_by_mercury`).
    A seam: a test plants reservations without Kea's files."""
    from modules import dhcp_reservations as D

    return D.held_by_mercury(list_name)


def _reservation_facts(list_name: str, hostname: str, entry, known: list) -> dict:
    """Its Kea reservations (C1335): ZTP's (the fragment, by its recorded MAC or its name)
    and the DHCP page's (Mercury's subnet files, by its name or any address it was known
    by), each removed by its own writer at apply: ZTP's `write_reservations`, the one
    abandon uses, and the DHCP page's `dhcp_reservations.apply`, planned here (Kea is asked)
    and confirmed by its hash. Each records itself in the Kea owner's repository."""
    from modules import dhcp_reservations as D
    from modules.list_settings import ListSettingsUnreadable
    from modules.nsot import ztp

    work = {"ztp": [], "dhcp": []}
    try:
        home = ztp.kea_home(list_name)
    except ListSettingsUnreadable as exc:
        return {"refuse": (f"whose Kea {list_name} uses could not be read ({exc}), so whether "
                           f"a reservation is still held for {hostname} cannot be told")}
    fragment = home["fragment"]
    mac = ztp._mac((entry or {}).get("mgmt_mac") or "")       # noqa: SLF001 - its one form
    if fragment:
        # Every file ZTP's writer owns: the network's fragment and each relayed ZTP subnet's
        # own file (C1346), whose reservations the DHCP page's record leaves to ZTP.
        every, error = ztp.fragments(fragment, home.get("main_config", ""))
        held = []
        try:
            if error:
                raise ztp.Refused(error)
            for _sid, path in every:
                held += ztp._read_fragment(path)              # noqa: SLF001 - a read
        except ztp.Refused as exc:
            return {"refuse": (f"ZTP's reservations could not be read ({exc}), so whether "
                               f"one is held for {hostname} cannot be told: could not read "
                               "is not nothing there")}
        for e in held:
            if not isinstance(e, dict):
                continue
            if (mac and ztp._mac(e.get("hw-address", "")) == mac) or \
                    (e.get("hostname") or "").lower() == hostname.lower():   # noqa: SLF001
                work["ztp"].append({"mac": ztp._mac(e.get("hw-address", "")),  # noqa: SLF001
                                    "address": e.get("ip-address", "")})
    keys = {_addr_key(a) for a in known}
    key_of = {v: k for k, v in D.WORDS.items()}
    not_doing = []
    for r in _dhcp_held(list_name):
        if (r.get("hostname") or "").lower() != hostname.lower() and \
                not keys & {_addr_key(a) for a in r.get("addresses") or []}:
            continue
        values = {"op": "remove", "family": r["family"], "subnet": str(r["subnet"]),
                  "was": f"{key_of.get(r['by'], r['by'])}={r['identity']}"}
        sub = D.plan(list_name, values)
        what = (f"{r['family']} subnet {r['subnet']}: {r['by']} {r['identity']} -> "
                + ", ".join(r.get("addresses") or []))
        if not sub["ok"]:
            return {"refuse": f"its DHCP reservation ({what}) cannot be removed: {sub['refused']}"}
        work["dhcp"].append({"values": values, "hash": sub["hash"], "what": what})
        not_doing += [f"its DHCP reservation ({what}): {n}" for n in sub.get("not_done") or []]
    if not work["ztp"] and not work["dhcp"]:
        return {"step": "no Kea reservation names it" + (
            "" if fragment else " (no ZTP fragment is configured for this network)"),
            "done": True}
    parts = [f"ZTP's reservation for {z['mac']} ({z['address']}) through ZTP's writer, the one "
             "abandon uses, recorded in dhcp/ztp-reservations.yml" for z in work["ztp"]]
    parts += [f"its DHCP reservation {d['what']} through the DHCP page's own removal, "
              "recorded in dhcp/reservations.yml" for d in work["dhcp"]]
    return {"step": ("remove from Kea " + "; ".join(parts) + ", each committed in the Kea "
                     "owner's repository as you: the reservation stays in that record's "
                     "history, and its address is free for a new device"),
            "done": False, "work": work, "not_doing": not_doing}


def _device_leases(list_name: str, macs: list, addresses: list) -> dict:
    """Every Kea lease for the device (`dhcp_leases.for_device`). A seam: a test plants leases
    without a Kea."""
    from modules import dhcp_leases

    return dhcp_leases.for_device(list_name, macs=macs, addresses=addresses)


def _lease_facts(list_name: str, hostname: str, entry, known: list, ztp_work: list) -> dict:
    """Its Kea leases (C1403): every lease Kea holds, either family, for its recorded MAC (and
    the MAC of any ZTP reservation the plan removes) or any address it was known by, each
    named, released at apply through the one release (`dhcp_leases.release_for_device`) and
    recorded in the Kea owner's repository. Kea not answering refuses: could not read is not
    no lease."""
    from modules import dhcp_leases

    macs = [m for m in dict.fromkeys([(entry or {}).get("mgmt_mac") or ""]
                                     + [z.get("mac", "") for z in ztp_work]) if m]
    addresses = list(known) + [z.get("address", "") for z in ztp_work]
    got = _device_leases(list_name, macs, addresses)
    if not got["ok"]:
        return {"refuse": (f"Kea's leases could not be read ({got['error']}), so whether one is "
                           f"held for {hostname} cannot be told: could not read is not none")}
    if not got.get("configured", True):
        return {"step": "no Kea lease to release (Kea is not configured for this network)",
                "done": True}
    leases = got["leases"]
    if not leases:
        return {"step": "no Kea lease names it (its MAC or an address it was known by)",
                "done": True}
    return {"step": ("release from Kea " + "; ".join(dhcp_leases.words(r, times=False)
                                                     for r in leases)
                     + ", with lease4-del or lease6-del, each read back and recorded in "
                       f"{dhcp_leases.RECORD} in the Kea owner's repository as you: the "
                       "address is then free for a new device"),
            "done": False, "work": {"leases": [dhcp_leases.bound(r)
                                               | {"hostname": r["hostname"]}
                                               for r in leases]}}


def _tag_facts(repo: str, hostname: str, identity: str) -> dict:
    """Its golden tags (C1332): archived as ``retired/<h>/<identity>/<time>``, kept in git on
    the same commit with their message, and never listed as a restore point."""
    from modules.nsot import repo as R

    safe = R._safe_name(hostname)                              # noqa: SLF001 - the tags' form
    prefix = f"golden/{safe}/"
    rc, out, err = R.git(repo, "tag", "--list", f"{prefix}*")
    if rc != 0:
        return {"refuse": f"its golden tags could not be listed ({err or f'git exited {rc}'})"}
    tags = sorted(t for t in (out or "").split() if t)
    if not tags:
        return {"step": f"no golden tags ({prefix}*) to archive", "done": True}
    slug = _identity_slug(identity)
    moves = [[t, f"{ARCHIVE_PREFIX}/{safe}/{slug}/{t[len(prefix):]}"] for t in tags]
    return {"step": (f"archive its {len(tags)} golden tag(s) {prefix}* as "
                     f"{ARCHIVE_PREFIX}/{safe}/{slug}/<time>: each kept in git on its commit, "
                     "with its message, and pushed; never offered as a restore point, so a new "
                     f"device named {hostname} is offered none of them. The remote keeps its "
                     "copies under the old names (a push deletes no tag), and a restore point "
                     "at or before this retirement is never offered, whatever its name"),
            "done": False, "work": {"moves": moves}}


def _rolled_back_facts(repo: str, hostname: str) -> dict:
    """Its rollback block (C1333): archived in the retire record, masked, then cleared."""
    from modules.nsot import hostvars
    from modules.redact import redact_text

    note = hostvars.rolled_back_note(repo, hostname)
    if not note:
        return {"step": "no rollback block to clear", "done": True}
    if note.get("unreadable"):
        return {"refuse": note.get("reason") or "the record of rolled-back changes is unreadable"}
    commands = [redact_text(str(c)) for c in note.get("commands") or []]
    block = {"at": note.get("at", ""), "intent_commit": note.get("intent_commit", ""),
             "command_fingerprint": note.get("command_fingerprint", ""),
             "pipeline_id": note.get("pipeline_id", ""),
             "reason": redact_text(note.get("reason") or ""), "commands": commands}
    when = block["at"] or "at an unrecorded time"
    return {"step": (f"clear its rollback block (recorded {when}: {len(commands)} command(s) "
                     "rolled back"
                     + (f", fingerprint {block['command_fingerprint']}"
                        if block["command_fingerprint"] else "")
                     + "), archived first in the retire record's Rollback-Block trailer, its "
                     "commands masked: it survives there, in the repository's history"),
            "done": False, "work": {"block": block}}


def _approval_facts(list_name: str, hostname: str, known: list) -> dict:
    """Its pending approval-queue items (C1339), by its name or any address it was known by:
    withdrawn, recorded in the queue with the reason, never deleted."""
    from modules import approval_queue as Q

    pending, err = Q.read_pending(list_name)
    if err:
        return {"refuse": (f"the approval queue could not be read ({err}), so whether an item "
                           f"for {hostname} waits there cannot be told")}
    keys = {_addr_key(a) for a in known}
    mine = [e for e in pending or [] if e.get("device_hostname") == hostname
            or (e.get("device_ip") and _addr_key(e["device_ip"]) in keys)]
    if not mine:
        return {"step": "no pending approval-queue item names it", "done": True}
    kinds = ", ".join(sorted({e.get("action_type", "?") for e in mine}))
    return {"step": (f"withdraw its {len(mine)} pending approval-queue item(s) ({kinds}), each "
                     "kept in the queue as withdrawn by retire with your reason, so an item for "
                     "a new device at its address is queued again"),
            "done": False, "work": {"ids": [e["id"] for e in mine]}}


def _named_elsewhere(list_name: str, hostname: str) -> list:
    """The other networks with a device named *hostname* in their inventory. Raises when one
    cannot be read: could not read is not no other device."""
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists, load_saved_devices

    found = []
    for lst in get_device_lists():
        if lst["name"] == list_name:
            continue
        csv_path = os.path.join(LISTS_DIR, lst["filename"], "devices.csv")
        if not os.path.exists(csv_path):
            continue
        if any(d.get("hostname") == hostname for d in load_saved_devices(csv_path)):
            found.append(lst["name"])
    return found


def _policy_facts(list_name: str, hostname: str) -> dict:
    """The credential-rotation policies naming it in their device list (C1336): the name
    removed through the policy's own write (`scheduled_rotation.drop_device`); a policy naming
    it alone is turned off, never widened to every device. Kept, and said, while another
    network has a device of the name: the policies name devices across networks."""
    from modules.nsot import scheduled_rotation as SR

    naming = SR.policies_naming(hostname)
    if not naming:
        return {"step": "no credential-rotation policy names it", "done": True}
    try:
        elsewhere = _named_elsewhere(list_name, hostname)
    except Exception as exc:                   # noqa: BLE001 - said as the refusal
        return {"refuse": (f"whether another network has a device named {hostname} could not "
                           f"be told ({exc}), so the rotation policies naming it cannot be "
                           "changed: could not read is not no other device")}
    if elsewhere:
        return {"not_doing": [
            f"the credential-rotation policies naming {hostname} ({', '.join(naming)}) keep "
            f"the name: {hostname} is also a device in {', '.join(elsewhere)}, and a policy "
            "names devices across networks"]}
    alone = [p for p, devices in naming.items() if list(devices) == [hostname]]
    shared = [p for p in naming if p not in alone]
    parts = []
    if shared:
        parts.append(f"remove {hostname} from the device list of the credential-rotation "
                     f"polic{'ies' if len(shared) > 1 else 'y'} of {', '.join(shared)}")
    if alone:
        parts.append(f"turn off the rotation policy of {', '.join(alone)}, which names only "
                     f"{hostname}: a policy naming no device covers every device its profile "
                     "covers, so removing the name alone would widen it")
    return {"step": "; ".join(parts) + " -- a settings write, as you, recorded with the "
                    "credential changes", "done": False, "work": {"profiles": sorted(naming)}}


def _topology_facts(list_name: str, hostname: str) -> dict:
    """Its Topology declaration and place (C1341): the expected-island declaration withdrawn
    and its place on the arranged map removed, each through its own write, recorded in its own
    log (History reads both)."""
    from modules import topology_expected as TE
    from modules import topology_positions as TP

    ex, pos = TE.read(list_name), TP.read(list_name)
    for got in (ex, pos):
        if got["state"] == "unreadable":
            return {"refuse": (f"{got['error']}, so whether it names {hostname} cannot be "
                               "told: could not read is not nothing there")}
    island = (ex.get("islands") or {}).get(hostname)
    placed = hostname in (pos.get("positions") or {})
    if not island and not placed:
        return {"step": "no Topology declaration or arranged place names it", "done": True}
    parts = []
    if island:
        parts.append(f"withdraw its expected-island declaration (\"{island.get('reason', '')}\", "
                     f"by {island.get('by') or 'an unrecorded person'})")
    if placed:
        parts.append("remove its place on the arranged Topology map")
    return {"step": " and ".join(parts) + ", each recorded in the Topology's own log, which "
                                          "History reads",
            "done": False, "work": {"island": bool(island), "placed": placed}}


def _heartbeat_installed_path() -> str:
    """Where Grafana loads the heartbeat rules from. A seam, so a test never reads the host's."""
    from modules import heartbeat_windows as HW

    return HW.INSTALLED


def _heartbeat_facts(hostname: str) -> dict:
    """Its Grafana heartbeat rule (C1338): removed from the generated rules file
    (`heartbeat_windows.drop_plan`), recorded with the re-measures, and installed by the host
    step the plan names. ``state`` is drop_plan's; only ``names`` is a step to do."""
    from modules import heartbeat_windows as HW

    try:
        hb = HW._script()                                      # noqa: SLF001 - the one loader
        got = HW.drop_plan(hostname, H=hb, written_path=_heartbeat_rules_path(hb),
                           installed_path=_heartbeat_installed_path())
    except Exception as exc:                   # noqa: BLE001 - said in what watches it
        return {"state": "unreadable", "error": f"{type(exc).__name__}: {exc}"}
    if got["state"] == "names":
        return dict(got, step=(
            f"remove its Grafana heartbeat rule (window {got['window']} s) from the generated "
            f"rules file {got['written_path']}, recorded with the heartbeat re-measures; the "
            f"host step installs it: {got['host_step']}"), done=False,
            work={"fingerprint": got["fingerprint"]})
    if got["state"] == "grafana":
        return dict(got, step=(
            f"delete its Grafana heartbeat rule {got['uid']}, which Grafana still runs though no "
            f"generated rules file names it (Grafana keeps a provisioned rule its file dropped, "
            f"C1419): a delete file is written beside {got['written_path']}, recorded with the "
            f"heartbeat re-measures; the host step installs it: {got['host_step']}"),
            done=False, work={"fingerprint": got["fingerprint"]})
    if got["state"] == "none":
        return dict(got, step="no generated heartbeat rule names it (the rules file was read)",
                    done=True)
    return got


def _netbox_record_facts(list_name: str, hostname: str, nb: dict) -> dict:
    """Its NetBox record and Mercury's created-object entry (C1342; the operator's ownership
    plan, C556). The record is set to Decommissioning and RENAMED ``<h>-retired-<id>``, kept:
    NetBox holds a device's name unique in its site and tenant, so a new device of the name
    needs it free, and onboarding then creates a NEW record. Only with NetBox writes allowed,
    through the write gate (the before recorded); otherwise said as not done, and why. The
    created-object entry is marked retired (kept, with its id), so nothing matches it by name
    again."""
    from modules import netbox_guard

    try:
        created = (netbox_guard.get_created(list_name, "dcim/devices").get("dcim/devices")
                   or [])
    except Exception as exc:                   # noqa: BLE001 - said as the refusal
        return {"refuse": f"Mercury's created-object record could not be read ({exc})"}
    nb_id = nb.get("id") if nb.get("checked") and nb.get("exists") else None
    mark = [e for e in created if not e.get("retired") and (
        (nb_id is not None and e.get("id") == nb_id)
        or (e.get("name") or "").lower() == hostname.lower())]
    patch, not_doing = None, []
    if nb_id is not None:
        if nb.get("writes"):
            patch = {"id": nb_id, "name": f"{hostname}-retired-{nb_id}"}
        else:
            not_doing.append(
                f"NetBox device {nb_id} is NOT set to Decommissioning or renamed: NetBox writes "
                "are off here (netbox_allow_writes), so its name stays taken in NetBox, and "
                f"onboarding a new device named {hostname} is refused until the record is "
                "renamed or decommissioned there")
    if not mark and not patch:
        return {"step": "nothing to change in NetBox's record or Mercury's created-object "
                        "record", "done": True, "not_doing": not_doing}
    parts = []
    if patch:
        parts.append(f"set NetBox device {nb_id} to Decommissioning and rename it "
                     f"{patch['name']}, through Mercury's NetBox write gate with its before "
                     "recorded, then read back: the record and its history are KEPT, and the "
                     "name is free for a new device (NetBox holds a device's name unique in its "
                     "site and tenant)")
    if mark:
        parts.append("mark Mercury's created-object entry for dcim/devices "
                     + ", ".join(str(e.get("id")) for e in mark) + " retired: kept with its "
                     "id, and never matched by name again")
    return {"step": "; ".join(parts), "done": False, "not_doing": not_doing,
            "work": {"patch": patch, "mark": [e.get("id") for e in mark]}}


def _host_key_facts(ip: str, list_name: str, hostname: str) -> dict:
    """What retiring does about the SSH host key Mercury kept for the device's address
    (C940): `host_keys.forget_plan`, whose state is ``held`` (a step: forget it), ``none``
    (the step done already), ``shared`` (another device has the address: KEPT, said as
    not done) or ``unreadable`` (a refusal: could not read is not nothing there)."""
    from modules import host_keys

    try:
        return host_keys.forget_plan(ip, network=list_name, device=hostname)
    except Exception as exc:                   # noqa: BLE001 - said as the refusal
        return {"state": "unreadable", "fingerprint": "", "others": [],
                "words": f"the SSH host key Mercury kept for {ip} could not be checked: {exc}"}


def _mask_facts(nb: dict) -> dict:
    """What retire does about the credentials NetBox holds in the device's
    stored context (C139). A step only when NMAS may and can mask them;
    otherwise a Not-Done line saying exactly why they stay."""
    # COULD NOT CHECK REFUSES (the operator's decision, 2026-09-29): "couldn't
    # read it" is not "nothing there", absent against unreadable. A NetBox that
    # is not configured at all holds nothing, and proceeds.
    if not nb.get("checked") and nb.get("configured"):
        return {"refuse": (f"NetBox could not be read ({nb.get('reason')}), so whether it "
                           "still holds this device's credentials cannot be told, and once "
                           "it leaves no import reaches it again (C139). Could not read is "
                           "not nothing there: preview again when NetBox answers")}
    if not nb.get("exists"):
        return {}
    from modules.netbox_context_mask import assess_device

    a = assess_device(nb["device"])
    where = f"NetBox device {nb['id']}"
    if a["holds"] is None:
        return {"refuse": (f"{where}: whether it still holds a credential in its stored "
                           f"config context could not be checked ({a['why']}). Could not "
                           "check is not nothing there: preview again when it can be read")}
    if a["holds"] is False:
        return {"step": f"{where} holds no unmasked credential in its stored context: "
                        "nothing to mask", "done": True,
                "kept": "It holds no unmasked credential."}
    if not a["may"]:
        # PROCEEDS (the operator's decision, 2026-09-29): NMAS cannot mask what
        # it did not write, and refusing would block the retirement with no path
        # forward. The exposure it leaves is a Needs attention row, from the
        # netbox-secrets reader, until someone removes it in NetBox.
        return {"not_doing": (f"{where}'s stored config context is NOT masked: {a['why']}. "
                              "It stays a Needs attention row (NetBox holds a credential) "
                              "until someone removes it in NetBox")}
    if not nb.get("writes"):
        # REFUSED, not proceeded past (the operator's decision, 2026-09-29):
        # reads work with writes off, so the tool knows the credential is
        # there, and once the device leaves no import reaches it again. That
        # is C139 recurring, so the retirement waits for the mask.
        return {"refuse": (
            f"{where} still holds credentials in its stored config context "
            f"({a['why'].split(';')[0].replace('NetBox holds ', '')}), and NetBox writes are "
            "off here (netbox_allow_writes), so retire cannot mask them. Once this device "
            "leaves, no import reaches it again (C139). Turn writes on and preview again, or "
            f"run scripts/nmas-netbox-mask-context --device {nb['device'].get('name')} --apply "
            "and then retire")}
    return {"step": (f"mask the credentials {where} still holds in its stored config "
                     f"context ({a['why']}); written with the import's own masking and "
                     "read back"), "done": False}


def legacy_survives(list_name: str, host: str, path: str) -> dict:
    """Whether a legacy file's content SURVIVES in the repository, where, and
    what deleting it would lose (the operator's rule, 2026-09-28: an action
    that removes data says all three). Compared with every committed version of
    `golden/<host>.cfg`, newest first: the same configuration (section-aware,
    comments and headers aside) at a commit is survival at that commit; none
    means the lines are nowhere else. (Moved here from routes/golden.py at 7.8, when the
    legacy store's route left: retire was its only other user, C176.)"""
    from modules.nsot.roundtrip import configs_equivalent

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return {"state": "unknown", "words": f"Its content could not be read ({exc})."}
    # The migration committed each legacy file VERBATIM as a backup (measured
    # on the host: 32dbab7 holds .nsot/migration-backup/golden_configs-r5.cfg,
    # 332 lines), and the store is read-only since: the most exact survival.
    backup = f".nsot/migration-backup/golden_configs-{os.path.basename(path)}"
    rc0, shas0, _ = _legacy_git(list_name, "log", "--format=%h", "--diff-filter=AMR",
                                "--", backup)
    for sha in ((shas0 or "").split() if rc0 == 0 else []):
        rc1, body, _ = _legacy_git_raw(list_name, "show", f"{sha}:{backup}")
        if rc1 == 0 and body == text:
            return {"state": "survives", "commit": sha,
                    "words": (f"This file survives VERBATIM in the repository as {backup} "
                              f"at {sha} (the migration's backup; git show {sha}:{backup}), "
                              "so deleting it loses nothing but the copy.")}
    rel = f"golden/{host}.cfg"
    # Commits where the file EXISTS: the retire commit deletes it and is not
    # a version of it.
    rc, shas, _ = _legacy_git(list_name, "log", "--format=%h", "--diff-filter=AMR",
                              "--", rel)
    versions = [s for s in (shas or "").split() if s] if rc == 0 else []
    for sha in versions:
        rc2, body, _ = _legacy_git(list_name, "show", f"{sha}:{rel}")
        if rc2 == 0 and body and configs_equivalent(text, body)["equal"]:
            return {"state": "survives", "commit": sha,
                    "words": (f"Its configuration survives in the repository as {rel} at "
                              f"{sha} (git show {sha}:{rel}), so deleting it loses nothing "
                              "but the copy.")}
    if not versions:
        return {"state": "lost", "words": (f"The repository never held {rel}, so this file "
                                           "is the only copy of its configuration.")}
    return {"state": "lost", "words": (
        f"It differs from all {len(versions)} committed version(s) of {rel} (newest "
        f"{versions[0]}), so deleting it loses the lines only it holds.")}


def _legacy_repo(list_name: str) -> str:
    from modules.config import get_list_data_dir
    return os.path.join(get_list_data_dir(list_name), "config_repo")


def _legacy_git_raw(list_name: str, *args):
    from modules.nsot.repo import git_raw
    return git_raw(_legacy_repo(list_name), *args)


def _legacy_git(list_name: str, *args):
    from modules.nsot.repo import git
    return git(_legacy_repo(list_name), *args)


def _legacy_facts(list_name: str, list_dir: str, hostname: str, ip: str) -> dict:
    """The device's file in the deprecated `golden_configs/` store (C176):
    deleted only when its content survives in the repository, and the step
    says where; kept and named otherwise (an action that removes data says
    whether the data survives)."""
    from modules.nsot.repo import legacy_only_goldens

    try:
        entries = legacy_only_goldens(list_dir, set())
    except Exception as exc:                   # noqa: BLE001
        return {"not_doing": f"the deprecated golden_configs/ store could not be read ({exc})"}
    entry = next((e for e in entries
                  if (e.get("hostname") or "").lower() == hostname.lower()
                  or (ip and e.get("device_ip") == ip)), None)
    if entry is None:
        return {"step": "no file in the deprecated golden_configs/ store", "done": True}
    path = os.path.join(list_dir, "golden_configs", entry["file"])
    surv = legacy_survives(list_name, hostname, path)      # one survival check (C176)
    if surv["state"] == "survives":
        return {"step": f"delete {path} from the deprecated golden_configs/ store: "
                        + surv["words"], "done": False, "path": path}
    return {"not_doing": (f"{path} in the deprecated golden_configs/ store is KEPT: "
                          f"{surv['words']} Keep a copy before deleting it by hand."),
            "path": ""}


def _heartbeat_rules_path(hb) -> str:
    """Where the generator writes its rules: on the host, never committed.
    A seam, so a test reads a real rules document instead of the checkout's
    (which has none)."""
    return hb.OUT


def _watchers(hostname: str, ip: str, list_name: str = "", hb: dict = None) -> list:
    """What still watches the device after it leaves, each ``{"kind", "what", "how"}``:
    GENERATED (the tool regenerates it from what retire removes, so it is dropped at the next
    regeneration, said with when) or SURVIVES (nobody regenerates it: named with how it is
    removed). Board 12 (the operator, 2026-10-03). Each names what was READ. *hb*: the plan's
    `_heartbeat_facts` (read here when not given)."""
    out = []

    def item(kind, what, how):
        out.append({"kind": kind, "what": what, "how": how})

    hb = _heartbeat_facts(hostname) if hb is None else hb
    state = hb.get("state")
    if state == "names":
        # Retirement removes it itself (C1338): the step writes the rules file without it.
        item("generated", f"its Grafana heartbeat rule (window {hb['window']} s)",
             f"removed by this retirement from the generated rules file "
             f"({hb['written_path']}) and named in its delete file (C1419); Grafana deletes it "
             f"once the host step installs both ({hb['host_step']}), and until then the hourly "
             "check names it EXTRA")
    elif state == "grafana":
        item("generated", f"its Grafana heartbeat rule {hb.get('uid')}",
             "Grafana still runs it though no generated rules file names it; this retirement "
             f"names it in a delete file beside {hb['written_path']} (C1419), and Grafana "
             f"deletes it once the host step installs that ({hb['host_step']})")
    elif state == "none":
        item("generated", "its Grafana heartbeat rule",
             "none names it (the generated rules file was read)")
    elif state == "last":
        item("generated", f"its Grafana heartbeat rule (window {hb['window']} s)",
             "it is the only rule in the generated rules file, and a file with no rules reads "
             "like a fleet that is all heartbeating, so it is not written without it: the "
             "hourly check names it EXTRA until the windows are re-measured (Monitoring, then "
             "its host step)")
    elif state == "absent":
        item("generated", "its Grafana heartbeat rule",
             f"generated from committed intent, which leaves with this commit; the generated "
             f"rules file ({hb.get('written_path')}) is not here, nor the installed one "
             f"({hb.get('installed_path')}), so whether one names it is unknown: the hourly "
             "check names one EXTRA if it does, and re-measuring the heartbeat windows "
             "(Monitoring, then its host step) removes it")
    else:
        item("generated", "its Grafana heartbeat rule",
             f"the generated rules file could not be read ({hb.get('error')}), so whether one "
             "names it is unknown")
    try:
        from modules import prometheus_targets

        # The device's network's Prometheus (K11): its owner's directory and client.
        owner = prometheus_targets.owner_of(list_name)
        if prometheus_targets.target_dir(owner):
            item("generated", "Prometheus's scrape targets",
                 f"generated from the inventory, and a device with no committed golden is no "
                 f"target: retire's commit removes {hostname}'s golden, so the targets keeper "
                 "drops it at its next run, and the result reads the target files back")
        else:
            prom = prometheus_targets.client_for(owner)
            if prom is None or not prom.is_configured():
                item("survives", "Prometheus's scrape targets",
                     f"not generated here (no target directory is set) and Prometheus is not "
                     f"configured, so whether its targets still poll {ip or hostname} is "
                     "unknown: remove it where Prometheus is configured")
            else:
                t = prom.targets_for(ip)
                if not t["ok"]:
                    item("survives", "Prometheus's scrape targets",
                         f"not generated here (no target directory is set), and Prometheus "
                         f"could not be asked ({t['error']}): remove {ip} where its targets "
                         "are configured")
                elif t["count"]:
                    item("survives", "Prometheus's scrape targets",
                         f"Prometheus still scrapes {ip} ({t['count']} target(s), job "
                         f"{', '.join(t['jobs'])}), and its targets are not generated here "
                         "(no target directory is set): remove them where they are "
                         "configured")
                else:
                    item("survives", "Prometheus's scrape targets",
                         f"Prometheus scrapes nothing at {ip} (its active targets were read): "
                         "nothing to remove")
    except Exception as exc:                   # noqa: BLE001
        item("survives", "Prometheus's scrape targets", f"could not be checked ({exc})")
    item("survives", "a hand-built Grafana dashboard panel naming it",
         "stays until removed in Grafana: Mercury does not edit dashboards")
    return out


def targets_after(hostname: str, ip: str, list_name: str = "") -> dict:
    """After retire's commit, regenerate Prometheus's targets now (the keeper the commit
    woke does the same) and READ THE FILES BACK: ``{"state", "statement", "at"}``, state one
    of ``dropped``, ``still`` (a file still names it), ``failed`` (the regeneration did not
    happen) or ``not_managed`` (no target directory is set, so the tool writes none)."""
    from modules import prometheus_targets as PT

    # The device's network's Prometheus owner (K11): its directory, its record.
    owner = PT.owner_of(list_name)
    directory = PT.target_dir(owner)
    if not directory:
        return {"state": "not_managed", "at": "",
                "statement": "Prometheus's targets are not generated here (no target "
                             "directory is set)"}
    rec = PT.sync(f"retire of {hostname}", owner=owner)
    if not rec.get("ok"):
        return {"state": "failed", "at": rec.get("at", ""),
                "statement": (f"Prometheus's targets were NOT regenerated "
                              f"({rec.get('error') or 'no reason recorded'}): the keeper "
                              "tries again at its next run")}
    still = []
    for name in sorted(os.listdir(directory)):
        if not (name.startswith(PT.PREFIX) and name.endswith(".json")):
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as fh:
            groups = json.load(fh) or []
        if any((g.get("labels") or {}).get("device") == hostname
               or (ip and ip in (g.get("targets") or [])) for g in groups):
            still.append(name)
    if still:
        return {"state": "still", "at": rec["at"],
                "statement": (f"Prometheus's targets were regenerated, and still name "
                              f"{hostname} ({', '.join(still)}, read back at {rec['at']})")}
    return {"state": "dropped", "at": rec["at"],
            "statement": f"Prometheus's targets were regenerated without {hostname} (read "
                         f"back at {rec['at']})"}


def retired_record(repo: str, hostname: str):
    """The newest retire commit of *hostname* in *repo* (its `Retired-Device:` trailer, matched
    exactly), as ``{"sha", "at", "actor", "verified", "reason"}``, or None: what the device's
    address shows once it has left (C185; board 12). A read of git only."""
    from modules.nsot import repo as R

    rc, out, _err = R.git(repo, "log", "--format=%H%x1f%cI%x1f%B%x1e", "--fixed-strings",
                          f"--grep=Retired-Device: {hostname}")
    if rc != 0:
        return None
    for chunk in out.split("\x1e"):
        parts = chunk.strip().split("\x1f")
        if len(parts) != 3:
            continue
        sha, at, body = parts
        trailers = {}
        for line in body.splitlines():
            key, sep, value = line.partition(": ")
            if sep and key in ("Retired-Device", "Actor", "Actor-Verified", "Reason"):
                trailers.setdefault(key, value.strip())
        if trailers.get("Retired-Device") == hostname:
            return {"sha": sha, "at": at, "actor": trailers.get("Actor", ""),
                    "verified": trailers.get("Actor-Verified", ""),
                    "reason": trailers.get("Reason", ""),
                    "ip": _address_before(repo, sha, hostname)}
    return None


def _address_before(repo: str, sha: str, hostname: str) -> str:
    """The device's management address as the manifest held it just before its retire commit
    (the commit releases it), or "" when it cannot be read. A read of git only."""
    return (_entry_before(repo, sha, hostname)[1] or {}).get("mgmt_ip") or ""


def _entry_before(repo: str, sha: str, hostname: str) -> tuple:
    """``(identity, entry)`` as the manifest held *hostname* just before commit *sha*, or
    ``("", None)`` when it cannot be read. A read of git only."""
    from modules.nsot import repo as R

    rc, out, _err = R.git(repo, "show", f"{sha}^:{R.MANIFEST_REL}")
    if rc != 0:
        return "", None
    try:
        devices = (json.loads(out) or {}).get("devices") or {}
    except ValueError:
        return "", None
    for identity, entry in devices.items():
        if (entry.get("name") or "").lower() == hostname.lower():
            return identity, entry
    return "", None


def _blob(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def breakglass_covers(payload: dict, list_name: str, row: dict) -> str:
    """"" if *payload* holds this device's CURRENT credential, else why not.
    Compared in memory; nothing is printed or returned but the verdict."""
    from modules.device import open_stored

    want_user = row.get("username", "")
    want_pw, unopened = open_stored(row)
    if unopened:
        return unopened
    if not want_pw:
        return "the CSV row holds no password to compare"
    hits = [e for e in payload.get("devices", [])
            if e.get("hostname") == row.get("hostname")]
    if not hits:
        return (f"the break-glass record has no entry for "
                f"{row.get('hostname')} -- export again, including it")
    if not any((e.get("list_name") or payload.get("list_name")) == list_name
               for e in hits):
        return "the record's entry is for another list"
    if not any(e.get("password") == want_pw and e.get("username") == want_user
               for e in hits):
        return ("the record holds an OLDER credential for "
                f"{row.get('hostname')} than the one in the CSV row -- it was "
                "exported before the last rotation. Export again")
    return ""


def breakglass_logged(list_name: str, row: dict, exports: dict = None) -> dict:
    """Does the EXPORT LOG say a break-glass record holding this device's
    current credential was written? ``{"ok", "why", "export", "statement"}``.

    The Device page's basis, never the CLI's (which opens the record): the
    page cannot reach a file on the operator's laptop. It compares digests
    only (C182's ``currency_digest``), and the NEWEST export for the list
    decides, because an export writes the whole list and the newest is the
    one the operator holds. What it cannot show is said in ``statement``."""
    import time as _t

    from modules import breakglass as bg
    from modules.config import DATA_DIR, script_command
    from modules.device import open_stored

    limit = ("This trusts the export log on this host: it records what an export WROTE, "
             "and cannot show the file still exists or that its passphrase is known. "
             "`nmas-retire --breakglass <file>` opens the record itself.")
    try:
        exports = exports if exports is not None else bg.last_exports(DATA_DIR)
    except Exception as exc:                   # noqa: BLE001
        exports = {"state": "unreadable", "by_list": {}, "error": str(exc)}
    if exports.get("state") == "unreadable":
        return {"ok": False, "export": None, "statement": limit,
                "why": f"the export log could not be read ({exports.get('error')}): "
                       "an unreadable log is not an absent export"}
    newest = (exports.get("by_list") or {}).get(list_name)
    cmd = script_command("nmas-breakglass", "export", "--list", list_name,
                         "--out", "/dev/shm/nmas-breakglass.bg")
    if not newest:
        return {"ok": False, "export": None, "statement": limit,
                "why": f"no break-glass export of {list_name} is logged on this host. "
                       f"Export one ({cmd}), copy it off the host, then preview again"}
    host = row.get("hostname", "")
    # Opened by the one reader that names an unopenable value (C423: it raised).
    pw, unopened = open_stored(row)
    if unopened:
        return {"ok": False, "export": None, "statement": limit, "why": unopened}
    if not pw:
        return {"ok": False, "export": None, "statement": limit,
                "why": "the CSV row holds no password to compare"}
    when = _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(newest.get("at") or 0))
    export = {"at": when, "path": newest.get("path", ""),
              "key_fingerprint": newest.get("key_fingerprint", ""),
              "actor": newest.get("actor", "")}
    logged = (newest.get("devices") or {}).get(host)
    if logged is None:
        return {"ok": False, "export": export, "statement": limit,
                "why": f"the newest export of {list_name} ({when}) did not include {host}. "
                       f"Export again ({cmd})"}
    if logged != bg.currency_digest(host, row.get("username", ""), pw):
        return {"ok": False, "export": export, "statement": limit,
                "why": f"the newest export of {list_name} ({when}) recorded an OLDER "
                       f"credential for {host} than the one it holds now: it was taken "
                       f"before the last rotation. Export again ({cmd})"}
    return {"ok": True, "why": "", "export": export, "statement": limit}


def _holds_the_device(func):
    """Retirement changes the record of a device (its row, its bindings, its
    map entry), so it holds the device like any other change (C98): a
    retirement beside a deploy would remove what the deploy is recording."""
    import functools

    @functools.wraps(func)
    def wrapper(list_name, hostname, *args, **kw):
        from modules.nsot import device_ops

        try:
            with device_ops.hold(list_name, hostname, "retire",
                                 kw.get("actor") or "unknown"):
                return func(list_name, hostname, *args, **kw)
        except device_ops.DeviceBusy as exc:
            return {"ok": False, "error": str(exc)}
    return wrapper


#: The plan's steps (`plan()["steps"]`, by key) in a step's few words on THE stepper; the
#: plan's own sentence is the step's hover.
STEP_WORDS = {"netbox_mask": "NetBox's copy masked", "override": "Overrides cleared",
              "staged": "Staged credential deleted", "reservations": "Kea reservations removed",
              "leases": "Kea leases released",
              "commit": "Intent and golden removed", "tags": "Golden tags archived",
              "rolled_back": "Rollback block archived", "approvals": "Queue items withdrawn",
              "rotation_policy": "Rotation policies updated", "topology": "Topology entries removed",
              "heartbeat": "Heartbeat rule removed", "netbox_record": "NetBox record retired",
              "legacy": "Legacy file deleted", "host_key": "SSH host key forgotten",
              "row": "Inventory row deleted"}


def result_run(host: str, out: dict, plan: dict):
    """Retire's result on THE stepper (`modules.run_stepper`; the one stepper, 2026-10-12): the
    plan's steps, each done (already, or by this run), failed where it stopped with its
    error, or not reached after it. None for a refusal before any step ran (`apply` returns
    no ``done`` then): the card says that refusal and nothing ran."""
    from modules import run_stepper as RS

    if "done" not in out and not out.get("ok"):
        return None
    done, failed_at = set(out.get("done") or []), out.get("failed_at")
    steps, stopped = [], False
    for s in (plan or {}).get("steps") or []:
        words = STEP_WORDS.get(s["key"], s["key"])
        if s["done"]:
            steps.append(RS.step(s["key"], words, "done", note="already done: " + s["what"]))
        elif s["key"] in done or (out.get("ok") and not stopped):
            steps.append(RS.step(s["key"], words, "done", note=s["what"]))
        elif s["key"] == failed_at:
            stopped = True
            steps.append(RS.step(s["key"], words, "failed",
                                 note=out.get("error") or "no reason recorded"))
        else:
            steps.append(RS.step(s["key"], words, "not_reached", note=s["what"]))
    group = "done" if out.get("ok") else "failed"
    return RS.card([RS.row(host, group, steps)], label="Retire", key="retire")


@_holds_the_device
def apply(list_name: str, hostname: str, *, reason: str, actor: str,
          confirmed_hash: str, breakglass: dict = None,
          breakglass_log: bool = False) -> dict:
    """Run the plan's pending steps, in order. Refuses unless the plan is the
    one confirmed, and deletes the CSV row only against *breakglass* (the
    record, opened: the CLI) or, with *breakglass_log*, the export log (the
    Device page). The result names which basis was trusted."""
    from modules import credentials
    from modules.device import delete_device, load_saved_devices
    from modules.nsot import manifest, repo as R

    if not actor:
        return {"ok": False, "error": "an actor is required (who is accountable)"}
    p = plan(list_name, hostname, reason)
    if not p["ok"]:
        return {"ok": False, "error": "; ".join(p["refusals"]), "plan": p}
    if p["hash"] != confirmed_hash:
        return {"ok": False, "plan": p, "error": (
            f"the plan changed since you confirmed it ({confirmed_hash} -> "
            f"{p['hash']}). Nothing was done; re-run the plan")}

    list_dir, csv_path = _list_paths(list_name)
    repo = os.path.join(list_dir, "config_repo")
    row = next((d for d in load_saved_devices(csv_path)
                if d.get("hostname") == hostname), None)
    pending = {s["key"] for s in p["steps"] if not s["done"]}
    basis = {"basis": "", "statement": "no CSV row to delete: no credential to protect"}
    if "row" in pending:
        if breakglass is not None:
            why = breakglass_covers(breakglass, list_name, row)
            basis = {"basis": "record", "statement": (
                "The break-glass record was opened and holds this device's current "
                "credential.")}
        elif breakglass_log:
            logged = breakglass_logged(list_name, row)
            why = logged["why"]
            basis = {"basis": "export_log", "export": logged["export"],
                     "statement": ("The export log says the newest export of this list "
                                   f"({(logged['export'] or {}).get('at', '?')}, to "
                                   f"{(logged['export'] or {}).get('path', '?')}) recorded this "
                                   "device's current credential. " + logged["statement"])}
        else:
            return {"ok": False, "plan": p, "error": (
                "a break-glass record holding this device's current "
                "credential is required before its CSV row -- the only "
                "stored copy -- is deleted: scripts/nmas-breakglass export")}
        if why:
            return {"ok": False, "plan": p, "error": "break-glass: " + why}

    from modules.nsot import device_ops

    class _Done(list):
        """Each completed step is progress on the held device (C98)."""

        def append(self, step):
            device_ops.note(f"done: {step}")
            super().append(step)

    done = _Done()

    def fail(step, exc):
        remaining = [s["what"] for s in p["steps"]
                     if not s["done"] and s["key"] not in done]
        log.error("retire: %s failed at %s: %s", hostname, step, exc)
        return {"ok": False, "failed_at": step, "error": str(exc),
                "done": list(done), "remaining": remaining, "commit": commit,
                "breakglass": basis,
                "note": "run retire again: every step already done is skipped"}

    commit = ""
    if "netbox_mask" in pending:
        from modules.netbox_client import _nb_ready
        from modules.netbox_context_mask import assess_device, checker_scan, mask_one
        from modules.netbox_guard import for_list

        try:
            ok, err, session, base = _nb_ready()
            if not ok:
                raise RuntimeError(f"NetBox is not reachable: {err}")
            nb = _netbox_facts(list_name, hostname)
            a = assess_device(nb["device"]) if nb.get("exists") else {"holds": False}
            if a["holds"]:
                if not a["may"]:
                    raise RuntimeError(a["why"])
                from modules.netbox_guard import list_writer

                # One NetBox writer per list at a time, across processes (R21).
                with list_writer(list_name, f"the mask for retiring {hostname}", actor), \
                        for_list(list_name, actor=actor,
                                 authority=(f"retire of {hostname}, confirmed by {actor} "
                                            f"(plan {p['hash']})")):
                    got = mask_one(session, base, a["item"], checker_scan())
                if not got["ok"]:
                    raise RuntimeError(got["why"])
            done.append("netbox_mask")
        except Exception as exc:               # noqa: BLE001
            return fail("netbox_mask", exc)

    work = p.get("work") or {}
    why = f"{hostname} retired by {actor}: {reason}"
    advisories = list(p["advisories"])

    if "override" in pending:
        try:
            for addr in p.get("overrides") or [p["ip"]]:
                credentials.clear_device_override(addr)
            done.append("override")
        except Exception as exc:               # noqa: BLE001
            return fail("override", exc)

    if "staged" in pending:
        # The staged password and the adoption's sidecar go together (`adopt.clear_staged`).
        from modules.nsot import adopt as A

        try:
            A.clear_staged(repo, hostname)
            done.append("staged")
        except Exception as exc:               # noqa: BLE001
            return fail("staged", exc)

    if "reservations" in pending:
        try:
            _remove_reservations(list_name, hostname, work.get("reservations") or {},
                                 actor=actor, reason=reason)
            done.append("reservations")
        except Exception as exc:               # noqa: BLE001
            return fail("reservations", exc)

    if "leases" in pending:
        try:
            _release_leases(list_name, hostname, (work.get("leases") or {}).get("leases") or [],
                            actor=actor, reason=reason)
            done.append("leases")
        except Exception as exc:               # noqa: BLE001
            return fail("leases", exc)

    block = (work.get("rolled_back") or {}).get("block")
    if "commit" in pending:
        # The removal, the manifest release, the commit and any undo under the repository
        # lock, across processes (CONCURRENCY_AUDIT R1); the undo puts back ONLY the paths
        # retire touched (R25: it reset whole trees, taking another writer's work too).
        bindings = _bindings_rel() if p.get("template_override") else ""
        own = list(p["files"]) + [R.MANIFEST_REL] + ([bindings] if bindings else [])
        with R.repo_lock(repo):
            try:
                for rel in p["files"]:
                    rc, _o, err = R.git(repo, "rm", "--quiet", "--", rel)
                    if rc != 0:
                        raise RuntimeError(f"git rm {rel}: {err}")
                if bindings:
                    # Its per-device template override leaves in the same commit (C1337).
                    from modules.nsot import templates_repo

                    b = templates_repo.load_bindings(repo)
                    b["overrides"].pop(hostname, None)
                    templates_repo.save_bindings(repo, b)
                if p["identity"]:
                    rel = manifest.release(repo, p["identity"], list_name, actor,
                                           against="index", retained=("netbox",))
                    if not rel.get("ok"):
                        raise RuntimeError(rel.get("error"))
                trailers = [f"Actor: {actor}", "Tool: nmas-retire",
                            f"Retired-Device: {hostname}", f"Reason: {reason}"]
                # The plan's steps to do are the record of what this retirement does (each
                # step's own store records it as well); the rollback block is archived HERE,
                # before the block is cleared, its commands masked (C1333).
                trailers += [f"Retire-Step: {s['key']}: {s['what']}" for s in p["steps"]
                             if not s["done"]]
                if block and "rolled_back" in pending:
                    trailers.append("Rollback-Block: " + json.dumps(block, sort_keys=True))
                trailers += [f"Not-Done: {n}" for n in p["not_doing"]]
                # Exactly what retire removed and the manifest, never the trees
                # (C175): another device's uncommitted edit must not leave with r5.
                result = R._commit_paths(list_name, own,
                                         f"retire: {hostname} -- {reason}",
                                         trailers, "retire")
                if not result.get("ok"):
                    raise RuntimeError(result.get("error"))
                commit = result.get("commit", "")
                done.append("commit")
            except Exception as exc:               # noqa: BLE001
                # Put the tree back, or the next plan sees no files and no
                # identity, counts this step as done, and refuses on the dirty
                # tree it left: a half-state with no way forward.
                R.git(repo, "reset", "-q", "HEAD", "--", *own)
                R.git(repo, "checkout", "-q", "HEAD", "--", *own)
                return fail("commit", exc)

    if "tags" in pending:
        try:
            _archive_tags(repo, list_name, hostname, (work.get("tags") or {}).get("moves") or [],
                          actor=actor)
            done.append("tags")
        except Exception as exc:               # noqa: BLE001
            return fail("tags", exc)

    if "rolled_back" in pending:
        from modules.nsot import hostvars

        try:
            if not commit and block:
                # A run finishing a retirement whose commit landed before: the block is
                # archived in a record commit of its own first, never cleared unread.
                _record_commit(repo, list_name, hostname, actor=actor, reason=reason,
                               trailers=["Rollback-Block: " + json.dumps(block, sort_keys=True)])
            hostvars.clear_rolled_back(repo, hostname)
            done.append("rolled_back")
        except Exception as exc:               # noqa: BLE001
            return fail("rolled_back", exc)

    if "approvals" in pending:
        from modules import approval_queue as Q

        try:
            for entry_id in (work.get("approvals") or {}).get("ids") or []:
                got = Q.withdraw(entry_id, why, f"retire ({actor})", list_name)
                if not got.get("ok") and "already" not in (got.get("error") or ""):
                    raise RuntimeError(got.get("error") or "the withdrawal was refused")
            done.append("approvals")
        except Exception as exc:               # noqa: BLE001
            return fail("approvals", exc)

    if "rotation_policy" in pending:
        from modules.nsot import scheduled_rotation as SR

        try:
            got = SR.drop_device(hostname, actor=actor, why=why)
            if not got["ok"]:
                raise RuntimeError(got["error"])
            done.append("rotation_policy")
        except Exception as exc:               # noqa: BLE001
            return fail("rotation_policy", exc)

    if "topology" in pending:
        from modules import topology_expected as TE
        from modules import topology_positions as TP

        try:
            t = work.get("topology") or {}
            for got in ((TE.withdraw(list_name, hostname, actor) if t.get("island") else None),
                        (TP.forget(list_name, hostname, actor) if t.get("placed") else None)):
                if got is not None and not got.get("ok"):
                    raise RuntimeError(got.get("error"))
            done.append("topology")
        except Exception as exc:               # noqa: BLE001
            return fail("topology", exc)

    if "heartbeat" in pending:
        from modules import heartbeat_windows as HW

        try:
            hb = HW._script()                                  # noqa: SLF001 - the one loader
            got = HW.drop_device(hostname, (work.get("heartbeat") or {}).get("fingerprint", ""),
                                 actor=actor, why=why, H=hb,
                                 written_path=_heartbeat_rules_path(hb),
                                 installed_path=_heartbeat_installed_path())
            if not got["ok"]:
                raise RuntimeError(got["error"])
            advisories.append("its heartbeat rule left the generated rules file and is named in "
                              "its delete file (C1419); Grafana deletes it once the host step "
                              f"installs both: {got['host_step']}"
                              + (f". {got['deletes_said']}" if got.get("deletes_said") else ""))
            done.append("heartbeat")
        except Exception as exc:               # noqa: BLE001
            return fail("heartbeat", exc)

    if "netbox_record" in pending:
        try:
            _retire_netbox_record(list_name, hostname, work.get("netbox_record") or {},
                                  actor=actor, authority=(f"retire of {hostname}, confirmed by "
                                                          f"{actor} (plan {p['hash']})"))
            done.append("netbox_record")
        except Exception as exc:               # noqa: BLE001
            return fail("netbox_record", exc)

    if "legacy" in pending:
        try:
            os.remove(p["legacy_path"])
        except FileNotFoundError:
            pass                               # already gone: the step's effect holds
        except Exception as exc:               # noqa: BLE001
            return fail("legacy", exc)
        done.append("legacy")

    if "host_key" in pending:
        # The one write path (`host_keys.forget`, under the record's lock), compare-and-swap
        # with the key the plan named; the key stays in the record's history with who, when
        # and why (C940).
        from modules import host_keys

        try:
            got = host_keys.forget(p["ip"], network=list_name, device=hostname, by=actor,
                                   why=f"{hostname} retired by {actor}: {reason}",
                                   expected=(p.get("host_key") or {}).get("fingerprint", ""))
            if not got["ok"]:
                raise RuntimeError(got["error"])
            done.append("host_key")
        except Exception as exc:               # noqa: BLE001
            return fail("host_key", exc)

    if "row" in pending:
        try:
            delete_device(row["ip"], csv_path)
            done.append("row")
        except Exception as exc:               # noqa: BLE001
            return fail("row", exc)

    return {"ok": True, "done": list(done), "commit": commit, "breakglass": basis,
            "not_doing": p["not_doing"], "advisories": advisories}


def _remove_reservations(list_name: str, hostname: str, w: dict, *, actor: str,
                         reason: str) -> None:
    """Remove the reservations the plan named (C1335), each through its own writer: ZTP's
    `write_reservations` (abandon's), the DHCP page's `dhcp_reservations.apply` with the hash
    the plan read. Raises naming the first that did not go."""
    from modules import dhcp_reservations as D
    from modules.nsot import ztp

    for z in w.get("ztp") or []:
        got = ztp.write_reservations(
            removes=[z["mac"]], list_name=list_name, actor=actor,
            message=(f"ztp: {hostname}'s reservation removed ({z['mac']})\n\n"
                     f"Retirement of {hostname} in {list_name}: {reason}"))
        o = (got.get("outcomes") or {}).get(z["mac"], {})
        if not got.get("ok") or o.get("outcome") not in ("removed", "absent"):
            raise RuntimeError(f"ZTP's reservation for {z['mac']} was not removed: "
                               + (o.get("detail") or got.get("error") or "no reason"))
        kept = got.get("record")
        if kept is not None and not kept.get("ok"):
            raise RuntimeError(f"ZTP's reservation for {z['mac']} was removed from Kea and its "
                               f"record was NOT committed ({kept.get('error')}): the next ZTP "
                               "change commits the whole fragment as its record")
    for d in w.get("dhcp") or []:
        got = D.apply(list_name, d["values"], d["hash"], actor=actor,
                      reason=f"{hostname} retired: {reason}")
        if not got.get("ok"):
            raise RuntimeError(f"the DHCP reservation {d['what']} was not removed: "
                               + (got.get("error") or "no reason"))


def _release_leases(list_name: str, hostname: str, leases: list, *, actor: str,
                    reason: str) -> None:
    """Release the leases the plan named (C1403) through the one release
    (`dhcp_leases.release_for_device`), each read back and recorded. A lease now another
    client's is left (said in its outcome). Raises naming what was not released."""
    from modules import dhcp_leases

    got = dhcp_leases.release_for_device(list_name, leases, actor=actor, reason=reason,
                                         source=f"retirement of {hostname}", device=hostname)
    if not got["ok"]:
        raise RuntimeError(f"its Kea leases were not all released: {got['error']}")


def _archive_tags(repo: str, list_name: str, hostname: str, moves: list, *,
                  actor: str) -> None:
    """Archive each golden tag as the plan named (C1332): an annotated tag of the same commit
    under ``retired/``, carrying the old one's message and where it came from, then the old
    name deleted; the new tags are published (pushed with the list's remote). Under the
    repository lock. A tag already archived is not made twice."""
    from modules.nsot import repo as R

    made = []
    with R.repo_lock(repo):
        for old, new in moves:
            have_old = R.git(repo, "rev-parse", "--verify", "-q", f"refs/tags/{old}")[0] == 0
            have_new = R.git(repo, "rev-parse", "--verify", "-q", f"refs/tags/{new}")[0] == 0
            if have_old and not have_new:
                _rc, body, _e = R.git(repo, "tag", "-l", "--format=%(contents)", old)
                message = ((body or "").strip() + f"\n\nArchived-From: {old}\n"
                           f"Retired-Device: {hostname}\nActor: {actor}\n")
                rc, _o, err = R.git(repo, "tag", "-a", new, "-m", message, f"{old}^{{commit}}")
                if rc != 0:
                    raise RuntimeError(f"git tag {new}: {err or f'git exited {rc}'}")
                made.append(new)
            if have_old:
                rc, _o, err = R.git(repo, "tag", "-d", old)
                if rc != 0:
                    raise RuntimeError(f"git tag -d {old}: {err or f'git exited {rc}'}")
        _rc, head, _e = R.git(repo, "rev-parse", "HEAD")
    if made:
        R.publish(repo, (head or "").strip(), list_name=list_name, source="retire",
                  actor=actor, tags=made)


def _record_commit(repo: str, list_name: str, hostname: str, *, actor: str, reason: str,
                   trailers: list) -> str:
    """An empty commit recording what a run finishing a retirement archives (its rollback
    block) when the retire commit landed in an earlier run. Returns its sha."""
    from modules.nsot import repo as R

    message = (f"retire: {hostname} -- record\n\n" + "\n".join(
        [f"Actor: {actor}", "Tool: nmas-retire", f"Reason: {reason}", *trailers,
         "Source: retire"]) + "\n")
    with R.repo_lock(repo):
        rc, sha, err = R.commit(repo, message, list_name=list_name, allow_empty=True,
                                source="retire", actor=actor)
    if rc != 0:
        raise RuntimeError(f"the record commit failed: {err}")
    return sha


def _retire_netbox_record(list_name: str, hostname: str, w: dict, *, actor: str,
                          authority: str) -> None:
    """Mark Mercury's created-object entries retired, then set the NetBox record to
    Decommissioning and rename it through the write gate (`_nb_patch`: writes allowed, the
    before recorded), and read it back (C1342). The entry is marked first: a run that stops
    after it is finished by running retire again."""
    from modules import netbox_guard

    if w.get("mark"):
        netbox_guard.mark_created_retired(list_name, "dcim/devices", w["mark"],
                                          device=hostname, by=actor)
    patch = w.get("patch")
    if not patch:
        return
    from modules.netbox_client import _nb_get_by_id, _nb_patch, _nb_ready, _status_value

    ok, err, session, base = _nb_ready()
    if not ok:
        raise RuntimeError(f"NetBox is not reachable: {err}")
    with netbox_guard.list_writer(list_name, f"retiring {hostname}", actor), \
            netbox_guard.for_list(list_name, actor=actor, authority=authority):
        _nb_patch(session, base, f"dcim/devices/{patch['id']}/",
                  {"status": "decommissioning", "name": patch["name"]})
    got = _nb_get_by_id(session, base, "dcim/devices", patch["id"]) or {}
    status = _status_value(got)
    if got.get("name") != patch["name"] or status != "decommissioning":
        raise RuntimeError(f"NetBox device {patch['id']} read back as {got.get('name')!r}, "
                           f"status {status!r}: the write did not land")
