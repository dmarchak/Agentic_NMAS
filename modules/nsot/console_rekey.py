"""Re-key a console server (C1560): keep the SSH host key a console server (or the SSH jump host
in front of a raw TCP console) answers with now, in place of the one Mercury holds, after a
person has looked at both, from Settings › Installation › Console servers.

Mercury keeps a console server's host key on first contact and refuses a different one before
its key is offered (`connection.open_pinned_transport`, `host_keys.check`), naming both and
pointing here (`REMEDY`). A console server rebuilt, or its key generated anew, legitimately
answers with a new key; this is the reviewed way to take it, the device page's re-key
(`rekey_op`) keyed by a console-server port's record instead of a device:

- the preview READS the key the SSH host presents now, with no credential (the key exchange
  only, `connection.read_host_key`), and shows it beside the key Mercury holds;
- the confirm is bound to the plan's hash, which covers the host and both fingerprints: if the
  host answers with yet another key by the time you confirm, or the record moved, nothing is
  kept;
- the apply reads the key again, replaces the record compare-and-swap (the held key must still
  be the one previewed, `host_keys.replace`), then reads the record back (`rekey_op.verify`);
- the record keeps the old key in its history, with who replaced it and when.

It sends nothing to the console server and opens no console.
"""

import hashlib
import json
import logging
import time

log = logging.getLogger(__name__)

#: What a refused console-server key tells the person to do (C1560): this page's Re-key…, never
#: the device page's, which a console server does not have.
REMEDY = ("If the console server was rebuilt or its key generated anew, re-key it on Settings › "
          "Installation › Console servers (Re-key… on its port's row); otherwise something "
          "else answers at its address")

#: The apply's steps, in order (the manual names each: `modules/manual.OPERATIONS`).
STEPS = (("read", "Read the key the console server presents now, with no credential"),
         ("keep", "Keep it in place of the held key, if the held key is still the one "
                  "previewed"),
         ("verify", "Read the record back: it holds the new key"),
         ("record", "The old key kept in the record's history, with who and when"))

NOT_DOING = (
    "nothing is sent to the console server: its key is read in the key exchange, before any "
    "sign-in, and no credential is used",
    "no console is opened and no device is touched",
    "no other host's key changes",
    "the old key is not forgotten: the record keeps it in its history, with who replaced it",
)


def ssh_endpoint(record: dict) -> tuple:
    """``(host, port, "")`` of the SSH server a console-server port's *record* signs in to (the
    console server for ``command_bridge``, the jump host for ``raw_tcp`` through one), or
    ``("", 0, why)`` when it signs in to none."""
    from modules.nsot import console_transport as T

    record = record or {}
    if record.get("driver") == "command_bridge":
        return record.get("host") or "", int(record.get("ssh_port") or T.SSH_PORT), ""
    if record.get("driver") == "raw_tcp" and record.get("jump_host"):
        return record["jump_host"], int(record.get("ssh_port") or T.SSH_PORT), ""
    return "", 0, (f"the {record.get('driver') or 'unknown'} driver with no jump host speaks no "
                   "SSH, so it has no host key to re-key")


def plan(port_id, *, read=None) -> dict:
    """Everything a re-key of console-server port *port_id*'s SSH host would keep, and why it
    would refuse: ``{"ok", "port_id", "host", "port", "held", "now", "refusals", "refused_by",
    "not_doing", "steps", "hash"}``. Reads the console-server store, the host-key record and
    the host's key (no credential). *read* replaces `connection.read_host_key` (a test)."""
    from modules import host_keys
    from modules.nsot import console_servers

    out = {"ok": True, "port_id": port_id, "host": "", "port": 0, "refusals": [],
           "refused_by": {}, "not_doing": list(NOT_DOING), "steps": [k for k, _w in STEPS]}

    def refuse(key, text):
        out["refusals"].append(text)
        out["refused_by"][key] = text

    got = console_servers.get_port(port_id)
    if got["state"] != "read":
        refuse("port", f"console-server port {port_id} has no record in Mercury's store"
               if got["state"] == "absent" else
               f"Mercury's console-server store could not be read: {got['error']}")
    host, port, why = ssh_endpoint(got.get("record") or {}) if got["state"] == "read" else \
        ("", 0, "")
    if why:
        refuse("ssh", why)
    out.update(host=host, port=port)
    held = None
    if host:
        try:
            held = host_keys.held(host)
        except host_keys.HostKeyStoreUnreadable as exc:
            refuse("store", str(exc))
        if held is None and "store" not in out["refused_by"]:
            refuse("held", f"Mercury holds no key for {host}: its next session keeps the key "
                           "it answers with, so there is nothing to replace")
    out["held"] = {k: (held or {}).get(k, "") for k in ("type", "fingerprint", "kept_at",
                                                        "kept_by", "how")}
    out["refused_key"] = dict((held or {}).get("refused") or {})
    now = {}
    if host and held is not None:
        try:
            from modules.connection import read_host_key
            now = (read or read_host_key)(host, port=port, owner="console rekey:preview")
        except Exception as exc:                   # noqa: BLE001 - said as the gate
            refuse("read", f"{host} port {port} did not answer with a key: "
                           f"{type(exc).__name__}: {exc}"[:300])
    out["now"] = {k: now.get(k, "") for k in ("type", "fingerprint", "key")}
    if now and held is not None and now.get("fingerprint") == held.get("fingerprint") \
            and now.get("type") == held.get("type"):
        refuse("changed", f"{host} answers with the key Mercury holds "
                          f"({held.get('fingerprint')}): there is nothing to re-key")
    out["ok"] = not out["refusals"]
    out["hash"] = hashlib.sha256(json.dumps({
        "port_id": port_id, "host": host, "port": port, "held": out["held"]["fingerprint"],
        "now": out["now"]["fingerprint"], "type": out["now"]["type"]},
        sort_keys=True).encode()).hexdigest()[:16]
    return out


def apply(port_id, *, actor: str, confirmed_hash: str, read=None) -> dict:
    """Keep the key console-server port *port_id*'s SSH host answers with now, as *actor*.
    ``{"ok", "state", "detail", "plan", "record"}``: the plan is computed again (the key read
    again) and a different hash refuses with nothing kept, naming what moved."""
    from modules import host_keys
    from modules.nsot import rekey_op

    p = plan(port_id, read=read)
    if not p["ok"]:
        return {"ok": False, "state": "refused", "plan": p,
                "detail": "; ".join(p["refusals"]) + ". Nothing was kept."}
    if confirmed_hash != p["hash"]:
        return {"ok": False, "state": "refused", "plan": p, "detail": (
            f"the plan changed since the preview you confirmed ({confirmed_hash or 'no hash'} "
            f"-> {p['hash']}): {p['host']} now answers with {p['now']['fingerprint']} and "
            f"Mercury holds {p['held']['fingerprint']}. Nothing was kept; preview again")}
    got = host_keys.replace(p["host"], expected=p["held"]["fingerprint"], new=p["now"],
                            by=actor, why=f"re-keyed from Settings › Installation › Console "
                                          f"servers (console-server port {port_id})")
    if not got["ok"]:
        return {"ok": False, "state": "refused", "plan": p, "detail": got["error"] + "."}
    verified = rekey_op.verify(p["host"], p["now"]["fingerprint"])
    log.info("console rekey: port %s's host %s by %s: %s -> %s (%s)", port_id, p["host"],
             actor, p["held"]["fingerprint"], p["now"]["fingerprint"],
             "verified" if verified else "NOT verified")
    return {"ok": verified, "state": "rekeyed" if verified else "not_verified", "plan": p,
            "record": got["record"], "ended": time.time(),
            "detail": ("the record holds the new key" if verified else
                       "the record, read back, does not hold the new key")}
