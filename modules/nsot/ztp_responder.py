"""P.6 step 2: the ZTP config responder (D2, D5, D6).

A node that booted with no configuration asks for one by TFTP (M3: `RRQ
"<hostname>.cfg" octet`, 21 bytes, no options, to port 69). This answers it
with the device's bootstrap config, RENDERED AT THE MOMENT OF THE REQUEST
from committed intent and the staged credential (`bootstrap_artifact()`),
and writes nothing but the audit row.

**What it will serve, decided per request, never cached:**
  - only to an address the tool itself reserved (a reservation in the
    fragment the writer owns). The reservation is what makes the requesting
    address mean something: a device-facing path has no person to ask;
  - only the file that reservation names in option 67. A different name is
    refused with both names, because a device asking for a file it was not
    told about is not in the state the tool thinks it is;
  - only for a device that is PENDING and onboarded as `ztp`, found in the
    manifest at request time, so promoting or abandoning it stops the
    serving at once;
  - only after the fetch's reveal row is written. The config carries the
    one-time credential, and nobody is watching this path.

Everything else is refused, and every refusal is recorded too.

**Read requests only (D6).** There is no write path to guard because none
exists: a write request gets a TFTP error and a recorded refusal. Octet mode
only, no TFTP options (RFC 2347 lets a server ignore them; the node asked
for none), 512-byte blocks, retransmission on timeout.

**The port (D5).** systemd binds udp/69 on the ZTP interface and hands the
socket over (`deploy/systemd/nmas-ztp-responder.socket`), so this process
holds no capability at all.
"""

import hashlib
import logging
import os
import socket
import struct
import threading

log = logging.getLogger(__name__)

OP_RRQ, OP_WRQ, OP_DATA, OP_ACK, OP_ERROR = 1, 2, 3, 4, 5
BLOCK = 512
ERR_NOT_FOUND, ERR_ACCESS, ERR_ILLEGAL = 1, 2, 4

#: What the device is told on a refusal. Deliberately the same short text
#: for every reason: the reason goes to the audit row, where a person reads
#: it, not to whatever is asking.
REFUSAL_TEXT = "refused; this request is recorded"


class BadRequest(Exception):
    pass


def parse_request(data: bytes) -> tuple:
    """``(opcode, filename, mode)`` of an RRQ or WRQ. Raises BadRequest."""
    if len(data) < 4:
        raise BadRequest("shorter than any TFTP request")
    (op,) = struct.unpack(">H", data[:2])
    if op not in (OP_RRQ, OP_WRQ):
        raise BadRequest(f"opcode {op} is not a request")
    parts = data[2:].split(b"\0")
    if len(parts) < 3:
        raise BadRequest("the filename or mode is not NUL-terminated")
    try:
        filename, mode = parts[0].decode("ascii"), parts[1].decode("ascii").lower()
    except UnicodeDecodeError:
        raise BadRequest("the filename or mode is not ASCII")
    if not filename:
        raise BadRequest("empty filename")
    return op, filename, mode


def error_packet(code: int, text: str) -> bytes:
    return struct.pack(">HH", OP_ERROR, code) + text.encode("ascii") + b"\0"


# ── the decision ───────────────────────────────────────────────────────────

def _fragment_entries() -> list:
    from modules.nsot import ztp
    from modules.list_settings import default_layer   # one fragment serves every list (P.7)

    path = default_layer("kea_ztp_fragment", "")
    if not path:
        raise LookupError("kea_ztp_fragment is not configured, so no address was "
                          "reserved by the tool and none can be served")
    return ztp._read_fragment(path)


def _pending_ztp_devices() -> list:
    """``[(list_name, repo, entry)]`` for every pending `ztp` device in every
    list, read from each list's manifest NOW. Never creates a list directory."""
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists
    from modules.nsot import manifest

    out = []
    for item in get_device_lists():
        repo = os.path.join(LISTS_DIR, item["filename"], "config_repo")
        if not os.path.isdir(repo):
            continue
        for entry in manifest.pending_devices(repo):
            if entry.get("address_source") == "ztp":
                out.append((item["name"], repo, entry))
    return out


def _artifact(repo: str, hostname: str) -> dict:
    from modules.nsot.onboard import bootstrap_artifact

    return bootstrap_artifact(repo, hostname)


def decide(peer: str, filename: str, *, fragment=_fragment_entries,
           pending=_pending_ztp_devices, artifact=_artifact) -> dict:
    """``{"serve", "config", "device", "list", "reason"}``. Every input is
    read at call time; nothing is remembered between requests."""
    out = {"serve": False, "config": b"", "device": "", "list": "", "reason": ""}
    try:
        entries = fragment()
    except Exception as exc:                      # noqa: BLE001
        out["reason"] = f"the tool's reservations could not be read: {exc}"
        return out
    mine = [e for e in entries if isinstance(e, dict) and e.get("ip-address") == peer]
    if len(mine) != 1:
        out["reason"] = (f"{peer} holds no reservation the tool wrote"
                         if not mine else f"{peer} is reserved {len(mine)} times")
        return out
    reservation = mine[0]
    named = next((o.get("data") for o in reservation.get("option-data") or []
                  if o.get("name") == "boot-file-name"), None)
    if filename != named:
        out["reason"] = (f"{peer} asked for {filename!r}; its reservation names "
                         f"{named!r}")
        return out
    mac = (reservation.get("hw-address") or "").lower()
    try:
        devices = [(ln, repo, e) for ln, repo, e in pending()
                   if e.get("reserved_address") == peer
                   and (e.get("mgmt_mac") or "").lower() == mac]
    except Exception as exc:                      # noqa: BLE001
        out["reason"] = f"the manifests could not be read: {exc}"
        return out
    if len(devices) != 1:
        out["reason"] = (f"no pending ZTP device holds the reservation {mac} -> {peer} "
                         "(promoted, abandoned, or never onboarded as ztp)"
                         if not devices else
                         f"{len(devices)} pending ZTP devices claim {peer}")
        return out
    list_name, repo, entry = devices[0]
    out["device"], out["list"] = entry.get("name", ""), list_name
    rendered = artifact(repo, out["device"])
    if not rendered.get("ok"):
        out["reason"] = f"the config could not be rendered: {rendered.get('reason')}"
        return out
    out["config"] = rendered["config"].encode("ascii")
    out["serve"] = True
    return out


def record(peer: str, filename: str, decision: dict, audit=None) -> dict:
    """The audit row: what was served (its HASH, never its text), or why not."""
    if audit is None:
        from modules import reveal_audit
        audit = reveal_audit.record
    extra = {"file": filename, "via": "tftp"}
    if decision.get("serve"):
        extra["sha256"] = hashlib.sha256(decision["config"]).hexdigest()
    return audit(actor=f"ztp:{peer}", kind="device",
                 what=("bootstrap_config" if decision.get("serve")
                       else "bootstrap_config_refused"),
                 target=decision.get("device") or "?",
                 detail=(f"list={decision.get('list')}" if decision.get("serve")
                         else decision.get("reason", "")),
                 peer=peer, extra=extra)


# ── the transfer ───────────────────────────────────────────────────────────

def transfer(sock, client, data: bytes, timeout: float = 2.0, retries: int = 5) -> tuple:
    """Send *data* to *client* in 512-byte DATA blocks, each ACKed. The
    final block is shorter than 512, empty when the length is an exact
    multiple. ``(ok, detail)``."""
    sock.settimeout(timeout)
    blocks = [data[i:i + BLOCK] for i in range(0, len(data), BLOCK)]
    if not blocks or len(blocks[-1]) == BLOCK:
        blocks.append(b"")
    for number, chunk in enumerate(blocks, start=1):
        packet = struct.pack(">HH", OP_DATA, number & 0xFFFF) + chunk
        for _attempt in range(retries):
            sock.sendto(packet, client)
            try:
                while True:
                    reply, source = sock.recvfrom(1024)
                    if source != client:
                        continue          # another host: not this transfer's TID
                    if len(reply) >= 4:
                        op, got = struct.unpack(">HH", reply[:4])
                        if op == OP_ACK and got == (number & 0xFFFF):
                            break
                        if op == OP_ERROR:
                            return False, f"the client aborted at block {number}"
                break
            except socket.timeout:
                continue
        else:
            return False, f"no ACK for block {number} after {retries} tries"
    return True, f"{len(blocks)} block(s), {len(data)} bytes"


def normalise_peer(peer: tuple) -> tuple:
    """``(host, reply_address, family)`` for a `recvfrom` peer.

    systemd's `ListenDatagram=69` is a DUAL-STACK IPv6 socket (measured on the
    host: `Listen=[::]:69`), so an IPv4 device arrives as the 4-tuple
    ``("::ffff:192.0.2.50", port, flowinfo, scope_id)``. M4 found both halves
    of what that breaks: the v4-mapped host matched no reservation (so the
    device was refused as ``?``), and the 4-tuple could not be handed to an
    AF_INET socket (so the refusal itself crashed, and the device heard
    silence). One normalisation, used for BOTH the identity and the reply.
    """
    import ipaddress

    host, port = peer[0], peer[1]
    try:
        ip = ipaddress.ip_address(str(host).split("%", 1)[0])
    except ValueError:
        return str(host), (host, port), socket.AF_INET
    if ip.version == 6 and ip.ipv4_mapped is not None:
        v4 = str(ip.ipv4_mapped)
        return v4, (v4, port), socket.AF_INET
    if ip.version == 6:
        return str(host), (host, port, 0, peer[3] if len(peer) > 3 else 0), socket.AF_INET6
    return str(host), (str(host), port), socket.AF_INET


def handle(packet: bytes, peer: tuple, **kw) -> dict:
    """One request, start to finish, and it NEVER dies silently.

    M4: a handler that raised on its own thread printed a traceback and the
    device heard nothing, and a ZTP device does not retry for ever (IOS-XE
    17.6 gave up after about 2.5 minutes and nine requests, "AUTOINSTALL:
    script execution not successful"). So a failure is logged as
    `handler FAILED`, the line job health counts, rather than left to the
    thread's default hook."""
    try:
        return _handle(packet, peer, **kw)
    except Exception as exc:                      # noqa: BLE001
        log.error("ztp responder: handler FAILED for %s: %s: %s",
                  (peer or ("?",))[0], type(exc).__name__, exc, exc_info=True)
        return {"served": False, "reason": f"handler failed: {type(exc).__name__}: {exc}"}


def _handle(packet: bytes, peer: tuple, *, transfer_socket=None, decide_fn=decide,
            audit=None) -> dict:
    host, peer, family = normalise_peer(peer)
    make = transfer_socket or (lambda: socket.socket(family, socket.SOCK_DGRAM))
    sock = make()
    try:
        sock.bind(("", 0))
        try:
            op, filename, mode = parse_request(packet)
        # Every refusal is RECORDED, THEN SENT (C169): the serve path writes its
        # reveal row before it serves, and a refusal sent first was a claim
        # ("every refusal is recorded") that held only if the process
        # survived the gap between the two lines.
        except BadRequest as exc:
            record(host, "", {"reason": f"malformed request: {exc}"}, audit)
            sock.sendto(error_packet(ERR_ILLEGAL, REFUSAL_TEXT), peer)
            return {"served": False, "reason": str(exc)}
        if op == OP_WRQ:
            record(host, filename, {"reason": "a write request; this server has no write path"}, audit)
            sock.sendto(error_packet(ERR_ACCESS, REFUSAL_TEXT), peer)
            return {"served": False, "reason": "write request"}
        if mode != "octet":
            record(host, filename, {"reason": f"mode {mode!r}; only octet is served"}, audit)
            sock.sendto(error_packet(ERR_ILLEGAL, REFUSAL_TEXT), peer)
            return {"served": False, "reason": f"mode {mode}"}
        decision = decide_fn(host, filename)
        row = record(host, filename, decision, audit)
        if not decision["serve"]:
            sock.sendto(error_packet(ERR_ACCESS, REFUSAL_TEXT), peer)
            return {"served": False, "reason": decision["reason"]}
        if not row.get("recorded"):
            # SERVE ONLY WHAT IS RECORDED. The config carries the one-time
            # credential, and no person is watching this path.
            sock.sendto(error_packet(ERR_ACCESS, REFUSAL_TEXT), peer)
            log.error("ztp responder: NOT serving %s to %s: the audit row could not be written",
                      decision["device"], host)
            return {"served": False, "reason": "the audit row could not be written"}
        ok, detail = transfer(sock, peer, decision["config"])
        log.info("ztp responder: %s %s to %s: %s", "served" if ok else "FAILED to serve",
                 decision["device"], host, detail)
        return {"served": ok, "reason": detail, "device": decision["device"]}
    finally:
        sock.close()


def serve(listener, *, stop=None, handle_fn=handle, threads=True):
    """Answer requests on *listener* until *stop* is set. Each request is
    handled on its own thread and its own socket (its TFTP transfer ID)."""
    stop = stop or threading.Event()
    listener.settimeout(0.5)
    while not stop.is_set():
        try:
            packet, peer = listener.recvfrom(1024)
        except socket.timeout:
            continue
        if threads:
            threading.Thread(target=handle_fn, args=(packet, peer), daemon=True).start()
        else:
            handle_fn(packet, peer)


def systemd_socket():
    """The socket systemd bound for us (fd 3), or None when not activated."""
    if os.environ.get("LISTEN_PID") != str(os.getpid()):
        return None
    if int(os.environ.get("LISTEN_FDS", "0")) < 1:
        return None
    return socket.socket(fileno=3)
