"""Serve ONE file, ONCE, to ONE device, by TFTP (Phase 2's transfer, D1; measured first).

docs/NSOT_REVERT_BY_RELOAD.md, D1: the revert's boot file is pulled by the device from the
host, served once, to that device's address only, for the run. This is that server, built
first as the measurement M1 needs (2026-10-07): r2 and s1 timed out on a refusal because the
ZTP responder answered from the routed address, not the one asked (C563), and an ERROR alone
cannot say whether a DATA transfer would arrive. It shares the ZTP responder's protocol
pieces (one TFTP implementation): the request parser, the transfer, the reply address.

**What it serves:** exactly *payload*, under exactly *filename*, to a request from one of
*clients*. Anything else is answered with an ERROR from the address asked, and printed:
another address (access violation), another name (file not found, so a device's own words for
an ERROR can be read), a write request. It stops after ONE complete transfer, or at the
deadline. It writes nothing: the payload lives in memory.

**The reply address** is the one the request was sent to (C563). ``reply_from="routed"``
reproduces the old behaviour, so the measurement can show whether it matters.
"""

import hashlib
import socket
import time

from modules.nsot import ztp_responder as R

ERR_NOT_FOUND = R.ERR_NOT_FOUND
ERR_ACCESS = R.ERR_ACCESS
ERR_ILLEGAL = R.ERR_ILLEGAL


def test_payload(name: str, size: int, now: float = None) -> bytes:
    """A harmless text file of about *size* bytes: comment lines only, nothing a device would
    act on, its first line naming what it is."""
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                          time.gmtime(now if now is not None else time.time()))
    lines = [f"! Mercury one-shot TFTP test: {name}, served {stamp}. Nothing to apply."]
    n = 1
    while sum(len(x) + 1 for x in lines) < size:
        lines.append(f"! padding line {n:04d}")
        n += 1
    return ("\n".join(lines) + "\n").encode("ascii")


def serve_once(listener, *, payload: bytes, filename: str, clients, reply_from: str = "asked",
               deadline_s: float = 300.0, clock=time.monotonic, say=print,
               transfer=R.transfer) -> dict:
    """Answer requests on *listener* until one complete transfer of *payload* to a client in
    *clients*, or *deadline_s* passes. ``{"served": bool, "to", "asked", "detail", "sha256",
    "requests": [{"from", "asked", "name", "verdict"}]}``."""
    clients = {str(c) for c in clients}
    sha = hashlib.sha256(payload).hexdigest()
    R.ask_for_destination(listener)
    listener.settimeout(0.5)
    start = clock()
    seen = []
    while clock() - start < deadline_s:
        try:
            packet, peer, asked = R.receive(listener)
        except socket.timeout:
            continue
        host, reply_to, family = R.normalise_peer(peer)
        row = {"from": host, "asked": asked or "?", "name": "", "verdict": ""}
        seen.append(row)
        sock = socket.socket(family, socket.SOCK_DGRAM)
        try:
            source = R.reply_address(asked, family) if reply_from == "asked" else ""
            sock.bind((source, 0))
            row["reply_from"] = source or "routed"
            try:
                op, name, mode = R.parse_request(packet)
            except R.BadRequest as exc:
                row["verdict"] = f"malformed: {exc}"
                sock.sendto(R.error_packet(ERR_ILLEGAL, "malformed request"), reply_to)
                say(_line(row))
                continue
            row["name"] = name
            if op == R.OP_WRQ:
                row["verdict"] = "write request: refused (ERROR 2)"
                sock.sendto(R.error_packet(ERR_ACCESS, "read only"), reply_to)
            elif host not in clients:
                row["verdict"] = "not the device this is served to: refused (ERROR 2)"
                sock.sendto(R.error_packet(ERR_ACCESS, "not served to this address"), reply_to)
            elif name != filename:
                row["verdict"] = "asked for another name: ERROR 1 (file not found)"
                sock.sendto(R.error_packet(ERR_NOT_FOUND, "file not found"), reply_to)
            elif mode not in ("octet", "netascii"):
                row["verdict"] = f"mode {mode!r}: refused (ERROR 4)"
                sock.sendto(R.error_packet(ERR_ILLEGAL, "octet or netascii only"), reply_to)
            else:
                # netascii ends lines CR LF (RFC 1350); octet is the bytes as they are.
                body = payload.replace(b"\n", b"\r\n") if mode == "netascii" else payload
                row["verdict"] = f"mode {mode}; "
                ok, detail = transfer(sock, reply_to, body)
                row["verdict"] += ("SERVED: " if ok else "transfer failed: ") + detail
                say(_line(row))
                if ok:
                    return {"served": True, "to": host, "asked": asked, "detail": detail,
                            "sha256": sha, "requests": seen}
                continue
            say(_line(row))
        finally:
            sock.close()
    return {"served": False, "to": "", "asked": "", "sha256": sha, "requests": seen,
            "detail": f"no complete transfer within {deadline_s:.0f} s"}


def _line(row: dict) -> str:
    return (f"{time.strftime('%H:%M:%SZ', time.gmtime())}  from {row['from']}  "
            f"asked {row['asked']}  reply from {row.get('reply_from', '?')}  "
            f"name {row['name'] or '-'}  {row['verdict']}")
