"""RE-KEY, from the device's page (C906): keep the SSH host key a device answers with now, in
place of the one Mercury holds, after a person has looked at both.

Mercury keeps a device's host key on first contact and refuses a different one, naming both
(`modules/host_keys.py`). A device rebuilt from a fresh disk legitimately answers with a new
key; this is the reviewed way to take it. It is an operation like every other change:

- the preview READS the key the device presents now, with no credential (the key exchange
  only, `connection.read_host_key`), and shows it beside the key Mercury holds, with what is
  known of why it might have changed (a restart recorded since the key was kept, and the
  planned window that covered it, if any);
- the confirm is bound to the plan's hash, which covers both fingerprints: if the device
  answers with yet another key by the time you confirm, or the record moved, nothing is kept;
- the apply holds the device, reads the key again, replaces the record compare-and-swap (the
  held key must still be the one previewed), then reads the record back (verify);
- the record keeps the old key in its history, with who replaced it and when, and History
  draws it.

It sends nothing to the device and changes no configuration.
"""

import hashlib
import json
import logging
import time

log = logging.getLogger(__name__)

#: The apply's steps, in order (the manual names each: `modules/manual.OPERATIONS`).
STEPS = (("read", "Read the key the device presents now, with no credential"),
         ("keep", "Keep it in place of the held key, if the held key is still the one "
                  "previewed"),
         ("verify", "Read the record back: it holds the new key"),
         ("record", "The old key kept in the record's history, with who and when"))

#: Each refusal the plan can make, as the gate that draws it: the plan's `refused_by` keys
#: (a test holds the two sets equal, as persist's).
GATES = (
    ("list", "a list of that name exists", "the list is in the registry"),
    ("present", "the device is in this list's inventory", "it has an inventory row with its "
                                                          "address"),
    ("store", "Mercury's record of host keys can be read", "the record was read"),
    ("held", "Mercury holds a key for it", "a key was kept for its address"),
    ("read", "the device answered with its key now", "read with no credential"),
    ("changed", "the key it answers with differs from the one held",
     "a re-key replaces a key that changed"),
)

NOT_DOING = (
    "nothing is sent to the device: its key is read in the key exchange, before any sign-in, "
    "and no credential is used",
    "no configuration changes, on the device or in the repository",
    "no other device's key changes",
    "the old key is not forgotten: the record keeps it in its history, with who replaced it",
)


def _restart_words(list_name: str, hostname: str, since: str) -> str:
    """What the restart record says happened to the device since its key was kept: a key
    changes when a device boots from a fresh disk or someone generates a new one, so no
    recorded restart is worth saying aloud."""
    from modules import restarts

    try:
        got = restarts.events(device=hostname, list_name=list_name)
    except Exception as exc:                       # noqa: BLE001
        return f"the restart record could not be read ({exc})"
    if got.get("state") == "unreadable":
        return f"the restart record could not be read ({got.get('error', '')})"
    after = [r for r in got.get("rows") or []
             if restarts._epoch(r.get("at", "")) >= restarts._epoch(since or "")]
    if not after:
        return ("NO restart recorded since the key was kept: a key that changes without a "
                "restart is what something else answering at its address looks like")
    r = after[0]
    try:
        r = restarts.judged([r], restarts.planned_rows())[0]
    except RuntimeError:
        pass
    how = (f"as planned ({r.get('planned_by', '')}: {r.get('planned_why', '')})"
           if r.get("planned") else "unexpectedly")
    return f"restarted {how} at {r.get('at', '?')}" + (
        f", and {len(after) - 1} more time(s) since" if len(after) > 1 else "")


def plan(list_name: str, hostname: str, *, read=None) -> dict:
    """Everything a re-key would keep, what it will not do, and why it would refuse. Reads the
    registry, the inventory, the host-key record, the restart record and the device's key
    (no credential). *read* replaces `connection.read_host_key` (a test)."""
    from modules import host_keys
    from modules.device import load_saved_devices
    from modules.nsot.listref import UnknownList, resolve

    out = {"ok": True, "list_name": list_name, "hostname": hostname, "refusals": [],
           "refused_by": {}, "not_doing": list(NOT_DOING), "steps": [k for k, _w in STEPS]}

    def refuse(key, text):
        out["refusals"].append(text)
        out["refused_by"][key] = text

    row = None
    try:
        ref = resolve(list_name)
        row = next((d for d in load_saved_devices(ref.csv_path)
                    if d.get("hostname") == hostname), None)
    except UnknownList as exc:
        refuse("list", f"no device list named {list_name!r} ({exc})")
    if row is None and "list" not in out["refused_by"]:
        refuse("present", f"{hostname!r} is not in list {list_name!r}'s inventory")
    ip = (row or {}).get("ip", "").strip()
    out["ip"] = ip
    held = None
    if ip:
        try:
            held = host_keys.held(ip)
        except host_keys.HostKeyStoreUnreadable as exc:
            refuse("store", str(exc))
        if held is None and "store" not in out["refused_by"]:
            refuse("held", f"Mercury holds no key for {hostname} ({ip}): its next session "
                           "keeps the key it answers with, so there is nothing to replace")
    out["held"] = {k: (held or {}).get(k, "") for k in ("type", "fingerprint", "kept_at",
                                                        "kept_by", "how")}
    out["refused_key"] = dict((held or {}).get("refused") or {})
    now = {}
    if ip and held is not None:
        try:
            from modules.connection import read_host_key
            now = (read or read_host_key)(ip, owner="rekey:preview")
        except Exception as exc:                   # noqa: BLE001 - said as the gate
            refuse("read", f"{hostname} ({ip}) did not answer with a key: "
                           f"{type(exc).__name__}: {exc}"[:300])
    out["now"] = {k: now.get(k, "") for k in ("type", "fingerprint", "key")}
    if now and held is not None and now.get("fingerprint") == held.get("fingerprint") \
            and now.get("type") == held.get("type"):
        refuse("changed", f"{hostname} answers with the key Mercury holds "
                          f"({held.get('fingerprint')}): there is nothing to re-key")
    out["restart"] = (_restart_words(list_name, hostname, held.get("kept_at", ""))
                      if held else "")
    out["ok"] = not out["refusals"]
    out["hash"] = hashlib.sha256(json.dumps({
        "list": list_name, "device": hostname, "ip": ip,
        "held": out["held"]["fingerprint"], "now": out["now"]["fingerprint"],
        "type": out["now"]["type"]}, sort_keys=True).encode()).hexdigest()[:16]
    return out


def verify(ip: str, fingerprint: str) -> bool:
    """The record, read back, holds *fingerprint* for *ip*."""
    from modules import host_keys
    return (host_keys.held(ip) or {}).get("fingerprint") == fingerprint


def apply(list_name: str, hostname: str, *, actor: str, confirmed_hash: str,
          read=None) -> dict:
    """Keep the key *hostname* answers with now, holding the device, as *actor*.
    ``{"ok", "state", "detail", "plan", "record"}``. The plan is computed again (the key read
    again) and a different hash refuses with nothing kept, naming what moved."""
    from modules import host_keys
    from modules.nsot import device_ops

    try:
        with device_ops.hold(list_name, hostname, "rekey", actor):
            device_ops.note("read")
            p = plan(list_name, hostname, read=read)
            if not p["ok"]:
                return {"ok": False, "state": "refused", "plan": p,
                        "detail": "; ".join(p["refusals"]) + ". Nothing was kept."}
            if confirmed_hash != p["hash"]:
                return {"ok": False, "state": "refused", "plan": p, "detail": (
                    f"the plan changed since the preview you confirmed ({confirmed_hash} -> "
                    f"{p['hash']}): {hostname} now answers with {p['now']['fingerprint']} and "
                    f"Mercury holds {p['held']['fingerprint']}. Nothing was kept; preview "
                    "again")}
            device_ops.note("keep")
            got = host_keys.replace(p["ip"], expected=p["held"]["fingerprint"], new=p["now"],
                                    by=actor, why=f"re-keyed from the device page; {p['restart']}")
            if not got["ok"]:
                return {"ok": False, "state": "refused", "plan": p,
                        "detail": got["error"] + "."}
            device_ops.note("verify")
            verified = verify(p["ip"], p["now"]["fingerprint"])
    except device_ops.DeviceBusy as exc:
        return {"ok": False, "state": "refused", "plan": {"hostname": hostname,
                                                          "list_name": list_name},
                "detail": f"{exc}. Nothing was kept."}
    log.info("rekey: %s/%s by %s: %s -> %s (%s)", list_name, hostname, actor,
             p["held"]["fingerprint"], p["now"]["fingerprint"],
             "verified" if verified else "NOT verified")
    return {"ok": verified, "state": "rekeyed" if verified else "not_verified", "plan": p,
            "record": got["record"], "ended": time.time(),
            "detail": ("the record holds the new key" if verified else
                       "the record, read back, does not hold the new key")}
