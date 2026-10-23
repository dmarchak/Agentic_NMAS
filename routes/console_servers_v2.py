"""routes/console_servers_v2.py — Settings › Installation › Console servers (O8 of out-of-band
ZTP, docs/LAB9_PLAN.md section 8; board A of docs/boards/console-ztp.html, drawn under the
Phase 7 mode and logged in docs/STANDING_APPROVAL_LOG.md).

The installation's console servers, every network's: how Mercury reaches each console-server
port NetBox holds (`modules/nsot/console_servers.py`, keyed by the port's NetBox id), the
console servers' SSH keys (`modules/nsot/console_keys.py`: only the public half ever shown),
and each console server's SSH host key, re-keyed here (C1560, `modules/nsot/console_rekey.py`).

- the region (`region`): the port records with their NetBox port, the NetBox ports with no
  record, the keys, and the store's last changes; it reads itself again on ``console_servers``;
- Add a port record… / Edit… (`port_form`, `port_save`): the store's own validation, each
  refusal drawn in place, naming every field;
- Remove… (`port_remove_form`, `port_remove`): says what survives;
- Generate a key… (`key_form`, `key_generate`): the public key, its fingerprint and the exact
  ``authorized_keys`` line, never the private half;
- Re-key… (`rekey_preview`, `rekey_confirm`): both keys, the confirm bound to them.

Every card opens in ``#cs-op``, outside the region, so the region's redraw after a change never
takes away the answer drawn there. Nothing here contacts a device; only the re-key's preview and
confirm contact a console server, in the SSH key exchange only.
"""

import logging

from flask import Blueprint, render_template, request

from routes.device_v2 import _strict

log = logging.getLogger(__name__)

bp = Blueprint("console_servers_v2", __name__,
               url_prefix="/v2/settings/installation/console-servers")

#: The port record's form fields, in the form's order: every field any driver holds
#: (`console_servers.FIELDS`); `port_save` keeps only the chosen driver's.
FIELDS = ("driver", "host", "ssh_port", "container", "tcp_port", "jump_host", "credential_ref")
#: How many of the store's last changes the region draws.
CHANGES_SHOWN = 10


# ── the region's data ──────────────────────────────────────────────────────────────────────

def netbox_ports() -> dict:
    """NetBox's console-server ports, one paged list read: ``{"state": "read" | "unreadable",
    "ports": {id: {"id", "name", "server"}}, "error"}``. A read that failed is said, never
    "none" (Mercury's token is refused on the console model until C1535's grant)."""
    from modules.nsot import console_path as CP

    session, base, err = CP._ready(None, "")             # noqa: SLF001 - the one reader
    if err:
        return {"state": "unreadable", "ports": {}, "error": err}
    rows, err = CP._list(session, base, CP.EP_SERVER_PORTS)   # noqa: SLF001
    if rows is None:
        return {"state": "unreadable", "ports": {}, "error": err}
    ports = {}
    for r in rows:
        pid = r.get("id")
        if isinstance(pid, int) and not isinstance(pid, bool):
            dev = r.get("device") if isinstance(r.get("device"), dict) else {}
            ports[pid] = {"id": pid, "name": r.get("name") or r.get("display") or "",
                          "server": dev.get("name") or dev.get("display") or ""}
    return {"state": "read", "ports": ports, "error": ""}


def _held(host: str) -> dict:
    """The host key Mercury holds for *host*: ``{"state": "none" | "held" | "refused" |
    "unreadable", "fingerprint", "refused", "error"}``."""
    from modules import host_keys

    if not host:
        return {"state": "none", "fingerprint": "", "refused": "", "error": ""}
    try:
        rec = host_keys.held(host)
    except host_keys.HostKeyStoreUnreadable as exc:
        return {"state": "unreadable", "fingerprint": "", "refused": "", "error": str(exc)}
    if not rec:
        return {"state": "none", "fingerprint": "", "refused": "", "error": ""}
    refused = (rec.get("refused") or {}).get("fingerprint", "")
    return {"state": "refused" if refused else "held",
            "fingerprint": rec.get("fingerprint", ""), "refused": refused, "error": ""}


def _key(ref: str) -> dict:
    """What is stored under credential reference *ref*: ``{"ref", "state": "stored" |
    "absent" | "none", "username", "fingerprint", "created"}``, never a private half."""
    from modules import credentials
    from modules.nsot import console_keys as K

    if not ref:
        return {"ref": "", "state": "none", "username": "", "fingerprint": "", "created": ""}
    try:
        info = credentials.ssh_key_info(ref)
    except ValueError:
        info = None
    if not info:
        return {"ref": ref, "state": "absent", "username": "", "fingerprint": "",
                "created": ""}
    try:
        fp = K.fingerprint(info["public_key"])
    except Exception:                                    # noqa: BLE001 - a malformed public key
        fp = "unreadable"
    return {"ref": ref, "state": "stored", "username": info.get("username", ""),
            "fingerprint": fp, "created": info.get("created") or ""}


def view() -> dict:
    """The region: ``{"store", "error", "rows", "unset", "netbox", "key_list", "key_error",
    "changes"}``."""
    from modules import credentials
    from modules.nsot import console_rekey
    from modules.nsot import console_servers as CS

    got = CS.read()
    nb = netbox_ports()
    doc = got["doc"] or {"ports": {}, "log": []}
    rows = []
    for key in sorted(doc["ports"], key=lambda k: int(k) if str(k).isdigit() else 0):
        rec = doc["ports"][key]
        pid = int(key) if str(key).isdigit() else key
        host, port, _why = console_rekey.ssh_endpoint(rec)
        rows.append({"id": pid, "netbox": nb["ports"].get(pid), "record": rec,
                     "ssh_host": host, "ssh_port": port, "host_key": _held(host),
                     "key": _key(rec.get("credential_ref") or "")})
    known = {r["id"] for r in rows}
    unset = [p for pid, p in sorted(nb["ports"].items()) if pid not in known]
    try:
        refs = credentials.ssh_key_refs()
    except Exception as exc:                             # noqa: BLE001 - said, never raised
        refs, nb_keys_error = [], f"{type(exc).__name__}: {exc}"
    else:
        nb_keys_error = ""
    used = {r["record"].get("credential_ref") for r in rows}
    keys = [dict(_key(ref), used=ref in used) for ref in refs]
    changes = list(reversed((doc.get("log") or [])[-CHANGES_SHOWN:]))
    return {"store": got["state"], "error": got["error"], "rows": rows, "unset": unset,
            "netbox": nb, "key_list": keys, "key_error": nb_keys_error,
            "changes": changes}


def _region(code: int = 200, **ctx):
    return _strict(render_template("v2/_console_servers.html", cs=view(), **ctx), code)


def _op(template: str, code: int = 200, **ctx):
    return _strict(render_template(template, **ctx), code)


@bp.route("", methods=["GET"])
def region():
    """The region alone: read again on ``console_servers``. Writes nothing."""
    return _region()


# ── a port's record ────────────────────────────────────────────────────────────────────────

def _port_ctx(port_id, form=None, **extra) -> dict:
    from modules.nsot import console_servers as CS

    record = {}
    if port_id:
        got = CS.get_port(port_id)
        record = dict(got.get("record") or {})
    values = {k: str(record.get(k, "") or "") for k in FIELDS}
    if form is not None:
        values = {k: (form.get(k) or "").strip() for k in FIELDS}
    return dict({"mode": "port", "port_id": port_id or "", "typed": values,
                 "editing": bool(record), "netbox": netbox_ports(),
                 "drivers": CS.DRIVERS}, **extra)


def _port_id(value):
    text = str(value or "").strip()
    return int(text) if text.isdigit() and int(text) > 0 else None


@bp.route("/port/form", methods=["GET"])
def port_form():
    """Add a port record… or Edit…: the form, in place. Writes nothing."""
    pid = _port_id(request.args.get("port"))
    return _op("v2/_console_server_op.html", c=_port_ctx(pid))


@bp.route("/port", methods=["POST"])
def port_save():
    """Store the port's record as the person, through the store's own validation; a refusal
    names every field refused, and nothing is written."""
    from modules import identity
    from modules.nsot import console_servers as CS

    form = request.form
    pid = _port_id(form.get("port_id"))
    driver = (form.get("driver") or "").strip()
    # Every field filled in goes to the store, which refuses one its driver does not hold,
    # naming it: a field typed and silently dropped would be a control that does nothing.
    record = {name: (form.get(name) or "").strip() for name in FIELDS
              if (form.get(name) or "").strip()}
    record["driver"] = driver
    if pid is None:
        got = {"ok": False, "error": (f"Not saved: a console-server port's NetBox id is a "
                                      f"positive number, not {form.get('port_id')!r}")}
    else:
        got = CS.set_port(pid, record, actor=identity.request_actor())
    if not got["ok"]:
        return _op("v2/_console_server_op.html", 409,
                   c=_port_ctx(pid, form, refused=got["error"]))
    log.info("console servers: port %s's record saved by %s (%s)", pid,
             identity.request_actor(), driver)
    return _op("v2/_console_server_op.html",
               c={"mode": "port_saved", "port_id": pid, "record": got["record"]})


@bp.route("/port/<int:port_id>/remove/form", methods=["GET"])
def port_remove_form(port_id):
    """Remove…: what goes and what survives, in place. Writes nothing."""
    from modules.nsot import console_servers as CS

    got = CS.get_port(port_id)
    return _op("v2/_console_server_op.html",
               c={"mode": "remove", "port_id": port_id, "record": got.get("record"),
                  "state": got["state"], "error": got.get("error", "")})


@bp.route("/port/<int:port_id>/remove", methods=["POST"])
def port_remove(port_id):
    """Forget the port's record as the person; NetBox's port and the key stay."""
    from modules import identity
    from modules.nsot import console_servers as CS

    got = CS.remove_port(port_id, actor=identity.request_actor())
    if not got["ok"]:
        return _op("v2/_console_server_op.html", 409,
                   c={"mode": "remove", "port_id": port_id, "record": None, "state": "refused",
                      "error": got["error"]})
    return _op("v2/_console_server_op.html",
               c={"mode": "removed", "port_id": port_id, "record": got["removed"]})


# ── a console server's key ─────────────────────────────────────────────────────────────────

def _key_ctx(form=None, **extra) -> dict:
    from modules.nsot import console_keys as K

    src = form if form is not None else request.args
    values = {"ref": (src.get("ref") or "").strip(),
              "username": (src.get("username") or "").strip(),
              "wrapper_path": (src.get("wrapper_path") or "").strip() or K.WRAPPER_PATH,
              "allowlist_path": (src.get("allowlist_path") or "").strip() or K.ALLOWLIST_PATH}
    return dict({"mode": "key", "typed": values,
                 "exists": _key(values["ref"])["state"] == "stored"}, **extra)


@bp.route("/key/form", methods=["GET"])
def key_form():
    """Generate a key…: the form, in place. Writes nothing."""
    return _op("v2/_console_server_op.html", c=_key_ctx())


@bp.route("/key", methods=["POST"])
def key_generate():
    """A new key pair: the private half encrypted under its reference, and ONLY the public key,
    its fingerprint and the exact authorized_keys line drawn."""
    from modules import credentials, identity
    from modules.nsot import console_keys as K

    form = request.form
    c = _key_ctx(form)
    v = c["typed"]
    try:
        got = K.generate(v["ref"], username=v["username"], wrapper_path=v["wrapper_path"],
                         allowlist_path=v["allowlist_path"], replace=form.get("replace") == "1")
    except credentials.SshKeyExists as exc:
        return _op("v2/_console_server_op.html", 409, c=dict(c, refused=(
            f"Not generated: {exc}. Tick Replace to make a new one: the console host then "
            "refuses the old key until the new line is installed there")))
    except ValueError as exc:
        return _op("v2/_console_server_op.html", 409, c=dict(c, refused=f"Not generated: {exc}"))
    log.info("console servers: key %s generated by %s (%s)", got["ref"],
             identity.request_actor(), got["fingerprint"])
    return _op("v2/_console_server_op.html", c={"mode": "key_done", "key": {
        k: got[k] for k in ("ref", "username", "public_key", "fingerprint",
                            "authorized_keys_line")}})


# ── a console server's host key (C1560) ────────────────────────────────────────────────────

@bp.route("/port/<int:port_id>/rekey/preview", methods=["POST"])
def rekey_preview(port_id):
    """Read the key the port's SSH host presents now (no credential) beside the one held."""
    from modules.nsot import console_rekey

    p = console_rekey.plan(port_id)
    return _op("v2/_console_server_op.html", 200 if p["ok"] else 409,
               c={"mode": "rekey", "port_id": port_id, "p": p})


@bp.route("/port/<int:port_id>/rekey", methods=["POST"])
def rekey_confirm(port_id):
    """Keep the key the host answers with now, as the verified person, bound to both keys."""
    from modules import identity
    from modules.nsot import console_rekey

    ident, refusal = identity.require(request, action="confirm")
    if refusal is not None:
        return _op("v2/_console_server_op.html", 403,
                   c={"mode": "rekey_done", "port_id": port_id, "ok": False,
                      "detail": refusal.get("error", "a person must confirm")})
    got = console_rekey.apply(port_id, actor=ident.actor,
                              confirmed_hash=(request.form.get("hash") or "").strip())
    return _op("v2/_console_server_op.html", 200 if got["ok"] else 409,
               c={"mode": "rekey_done", "port_id": port_id, "ok": got["ok"],
                  "detail": got["detail"], "p": got["plan"], "state": got["state"]})
