"""C563 (2026-10-07): a TFTP reply leaves from the address the request was sent to.

M1 measured it: r2 and s1 asked the host's logging address for a file, the ZTP responder
received and refused every request, and both devices timed out. Each refusal went out on a
socket bound to ("", 0), so the kernel chose its source by route (the host's lab-facing
address), and a TFTP client ignores a reply from an address it did not ask. The listener now
asks for each datagram's destination (IP_PKTINFO / IPV6_PKTINFO) and the reply socket binds to
it; `modules/nsot/tftp_once.py` (Phase 2's one-shot transfer, the measurement's DATA half)
shares the same pieces.

Real sockets on loopback: a client on 127.0.0.1 asks 127.0.0.2, so a reply from the address
asked comes from 127.0.0.2, and one chosen by route from 127.0.0.1.
"""

import socket
import struct
import threading

import pytest

from modules.nsot import tftp_once
from modules.nsot import ztp_responder as R

ASKED = "127.0.0.2"
CLIENT = "127.0.0.1"


def _rrq(name, mode="octet"):
    return struct.pack(">H", R.OP_RRQ) + name.encode() + b"\0" + mode.encode() + b"\0"


def _listener(family=socket.AF_INET):
    s = socket.socket(family, socket.SOCK_DGRAM)
    if family == socket.AF_INET6:
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        s.bind(("::", 0))
    else:
        s.bind(("", 0))
    return s


def _fetch(port, name, asked=ASKED):
    """Read a file as a TFTP client that, like IOS, keeps to the address it asked: returns
    ``{"data", "error", "sources"}``, every reply's source address included."""
    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.settimeout(5)
    c.bind((CLIENT, 0))
    c.sendto(_rrq(name), (asked, port))
    got, sources = b"", []
    try:
        while True:
            data, src = c.recvfrom(2048)
            sources.append(src[0])
            op, num = struct.unpack(">HH", data[:4])
            if op == R.OP_ERROR:
                return {"data": got, "error": num, "sources": sources}
            got += data[4:]
            c.sendto(struct.pack(">HH", R.OP_ACK, num), src)
            if len(data) - 4 < R.BLOCK:
                return {"data": got, "error": None, "sources": sources}
    finally:
        c.close()


class TestTheAskedAddress:
    def test_in_pktinfo_gives_the_header_destination(self):
        data = struct.pack("=i4s4s", 3, socket.inet_aton("198.51.100.9"),
                           socket.inet_aton("192.0.2.10"))
        assert R.asked_address([(socket.IPPROTO_IP, socket.IP_PKTINFO, data)]) == "192.0.2.10"

    def test_in6_pktinfo_v4_mapped_is_ipv4(self):
        addr = socket.inet_pton(socket.AF_INET6, "::ffff:192.0.2.10")
        data = addr + struct.pack("=I", 3)
        assert R.asked_address([(socket.IPPROTO_IPV6, socket.IPV6_PKTINFO, data)]) == "192.0.2.10"

    def test_no_ancillary_data_is_unknown(self):
        assert R.asked_address([]) == ""

    def test_the_reply_address_keeps_to_its_family(self):
        assert R.reply_address("192.0.2.10", socket.AF_INET) == "192.0.2.10"
        assert R.reply_address("192.0.2.10", socket.AF_INET6) == ""
        assert R.reply_address("", socket.AF_INET) == ""


@pytest.fixture
def ztp():
    """The ZTP responder's real loop, refusing everything (as it refused r2 and s1)."""
    listener = _listener()
    stop = threading.Event()
    refuse = lambda peer, name: {"serve": False, "reason": "no reservation (test)",  # noqa: E731
                                 "device": "?", "list": "Lab"}

    def handle_fn(packet, peer, **kw):
        return R.handle(packet, peer, decide_fn=refuse, audit=lambda **k: {"recorded": True},
                        **kw)
    t = threading.Thread(target=R.serve, args=(listener,),
                         kwargs={"stop": stop, "handle_fn": handle_fn}, daemon=True)
    t.start()
    yield listener.getsockname()[1]
    stop.set()
    t.join(2)
    listener.close()


class TestTheZtpResponder:
    def test_its_refusal_comes_from_the_address_asked(self, ztp):
        """M1's case: the request is refused, and the refusal now reaches a client that keeps
        to the address it asked (before C563 it came from the routed one, CLIENT's)."""
        out = _fetch(ztp, "mercury-m1-probe.cfg")
        assert out["error"] == R.ERR_ACCESS
        assert out["sources"] == [ASKED]


def _serve(**kw):
    listener = _listener(kw.pop("family", socket.AF_INET))
    port = listener.getsockname()[1]
    box = {}
    t = threading.Thread(target=lambda: box.update(tftp_once.serve_once(
        listener, say=lambda line: None, **kw)), daemon=True)
    t.start()
    return port, t, box, listener


class TestTheOneShotTransfer:
    PAYLOAD = tftp_once.test_payload("mercury-m1-data.txt", 1300, now=0)

    def test_it_serves_the_file_once_from_the_address_asked(self):
        port, t, box, listener = _serve(payload=self.PAYLOAD, filename="mercury-m1-data.txt",
                                        clients=[CLIENT], deadline_s=10)
        out = _fetch(port, "mercury-m1-data.txt")
        t.join(5)
        listener.close()
        assert out["error"] is None and out["data"] == self.PAYLOAD
        assert set(out["sources"]) == {ASKED} and len(out["sources"]) == 3
        assert box["served"] is True and box["asked"] == ASKED and box["to"] == CLIENT
        assert not t.is_alive(), "it stops after one complete transfer"

    def test_routed_reproduces_the_old_reply_address(self):
        """The comparison the operator asked for: `--reply-from routed` answers as the
        responder did before C563, from the address the kernel routes by."""
        port, t, box, listener = _serve(payload=self.PAYLOAD, filename="f.txt",
                                        clients=[CLIENT], reply_from="routed", deadline_s=10)
        out = _fetch(port, "f.txt")
        t.join(5)
        listener.close()
        assert out["sources"] and set(out["sources"]) == {CLIENT}

    def test_another_name_is_error_1_from_the_address_asked(self):
        port, t, box, listener = _serve(payload=self.PAYLOAD, filename="f.txt",
                                        clients=[CLIENT], deadline_s=2)
        out = _fetch(port, "other.txt")
        t.join(5)
        listener.close()
        assert (out["error"], out["sources"]) == (R.ERR_NOT_FOUND, [ASKED])
        assert box["served"] is False and box["requests"][0]["name"] == "other.txt"

    def test_another_address_is_refused(self):
        port, t, box, listener = _serve(payload=self.PAYLOAD, filename="f.txt",
                                        clients=["127.0.0.9"], deadline_s=2)
        out = _fetch(port, "f.txt")
        t.join(5)
        listener.close()
        assert out["error"] == R.ERR_ACCESS and out["data"] == b""
        assert box["served"] is False

    def test_a_dual_stack_listener_reports_an_ipv4_request_as_ipv4(self):
        """systemd's socket is dual-stack: an IPv4 device arrives v4-mapped."""
        try:
            port, t, box, listener = _serve(payload=self.PAYLOAD, filename="f.txt",
                                            clients=[CLIENT], deadline_s=10,
                                            family=socket.AF_INET6)
        except OSError as exc:
            pytest.skip(f"no IPv6 loopback here: {exc}")
        out = _fetch(port, "f.txt")
        t.join(5)
        listener.close()
        assert out["error"] is None and set(out["sources"]) == {ASKED}
        assert box["asked"] == ASKED

    def test_the_test_file_is_comment_lines_only(self):
        lines = self.PAYLOAD.decode("ascii").splitlines()
        assert all(line.startswith("! ") for line in lines) and len(self.PAYLOAD) >= 1300
