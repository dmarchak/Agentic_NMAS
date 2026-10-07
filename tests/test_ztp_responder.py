"""P.6 step 2: the ZTP config responder (D2, D5, D6).

The six controls of P6_ZTP_PROBE.md section 10, each a test here, plus the
TFTP protocol over loopback (the network guard allows it) and the real
manifest wiring. Documentation addresses (RFC 5737) throughout.
"""

import ast
import hashlib
import os
import socket
import struct
import threading

import pytest

from modules.nsot import ztp_responder as r

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEER = "192.0.2.50"
MAC = "aa:bb:cc:00:02:50"
CONFIG = "hostname bp-ztp-a\nusername admin privilege 15 secret 0 x\n"


def _reservation(ip=PEER, mac=MAC, file="bp-ztp-a.cfg"):
    return {"hw-address": mac, "ip-address": ip, "hostname": "bp-ztp-a",
            "option-data": [{"name": "tftp-server-name", "data": "192.0.2.10"},
                            {"name": "boot-file-name", "data": file}]}


def _pending(name="bp-ztp-a", ip=PEER, mac=MAC):
    return [("Lab", "/repo", {"name": name, "reserved_address": ip, "mgmt_mac": mac,
                              "address_source": "ztp"})]


def _decide(peer=PEER, filename="bp-ztp-a.cfg", *, fragment=None, pending=None,
            artifact=None):
    return r.decide(peer, filename,
                    fragment=fragment or (lambda: [_reservation()]),
                    pending=pending or _pending,
                    artifact=artifact or (lambda repo, host: {"ok": True, "config": CONFIG}))


class TestWhatItServes:
    def test_the_pending_device_at_its_reserved_address_asking_for_its_file(self):
        d = _decide()
        assert d["serve"] and d["device"] == "bp-ztp-a" and d["list"] == "Lab"
        assert d["config"] == CONFIG.encode()

    def test_any_other_address_is_refused(self):
        d = _decide(peer="192.0.2.99")
        assert not d["serve"] and "holds no reservation the tool wrote" in d["reason"]

    def test_another_filename_is_refused_naming_both(self):
        d = _decide(filename="network-confg")
        assert not d["serve"]
        assert "'network-confg'" in d["reason"] and "'bp-ztp-a.cfg'" in d["reason"]

    def test_decided_at_request_time_so_promotion_stops_it(self):
        state = {"pending": True}
        pending = lambda: _pending() if state["pending"] else []
        assert _decide(pending=pending)["serve"]
        state["pending"] = False          # promoted between two requests
        d = _decide(pending=pending)
        assert not d["serve"] and "promoted, abandoned" in d["reason"]

    def test_an_abandoned_device_is_not_served(self):
        # Abandon removes the reservation (step 6) and the manifest entry.
        d = _decide(fragment=lambda: [])
        assert not d["serve"]

    def test_a_reservation_for_another_mac_is_not_this_device(self):
        d = _decide(pending=lambda: _pending(mac="aa:bb:cc:00:09:99"))
        assert not d["serve"]

    def test_a_config_that_cannot_be_rendered_is_not_served(self):
        d = _decide(artifact=lambda repo, host: {"ok": False, "reason": "no staged credential"})
        assert not d["serve"] and "no staged credential" in d["reason"]

    def test_unreadable_reservations_refuse(self):
        def boom():
            raise LookupError("kea_ztp_fragment is not configured")
        assert not _decide(fragment=boom)["serve"]


class _Audit:
    def __init__(self, recorded=True):
        self.rows, self.recorded = [], recorded

    def __call__(self, **row):
        self.rows.append(row)
        return dict(row, recorded=self.recorded)


class TestTheRecord:
    def test_a_fetch_records_the_hash_and_never_the_config(self):
        audit = _Audit()
        row = r.record(PEER, "bp-ztp-a.cfg", _decide(), audit)
        assert row["extra"]["sha256"] == hashlib.sha256(CONFIG.encode()).hexdigest()
        assert "secret" not in repr(audit.rows)
        assert row["what"] == "bootstrap_config" and row["actor"] == f"ztp:{PEER}"

    def test_the_hash_is_of_a_fresh_render(self):
        # The served config is the committed one: the artifact is called per
        # request, so a changed render changes the recorded hash.
        renders = iter([CONFIG, CONFIG + "!\n"])
        artifact = lambda repo, host: {"ok": True, "config": next(renders)}
        a, b = _decide(artifact=artifact), _decide(artifact=artifact)
        assert a["config"] != b["config"]

    def test_a_refusal_is_recorded_with_its_reason(self):
        audit = _Audit()
        r.record(PEER, "x", _decide(filename="x"), audit)
        assert audit.rows[0]["what"] == "bootstrap_config_refused"
        assert "sha256" not in audit.rows[0]["extra"], "nothing was served, so nothing is hashed"
        assert "'x'" in audit.rows[0]["detail"]


class TestNothingIsKept:
    """The module writes no file of any kind: the audit row is written by
    reveal_audit, and the config lives only in memory for one request."""

    def test_no_file_writing_call_in_the_module(self):
        tree = ast.parse(open(r.__file__, encoding="utf-8").read())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        names = {getattr(c.func, "attr", getattr(c.func, "id", "")) for c in calls}
        # Floor: the scan sees the calls the module does make.
        assert {"sendto", "recvfrom"} <= names
        assert not names & {"open", "replace", "rename", "write_text", "write_bytes",
                            "makedirs", "mkstemp", "NamedTemporaryFile", "copy", "copyfile"}


# ── the protocol, over loopback ─────────────────────────────────────────────

@pytest.fixture
def server():
    """A running responder on 127.0.0.1, with a fake decision and audit."""
    audit = _Audit()
    state = {"config": CONFIG.encode(), "serve": True}

    def decide_fn(peer, filename):
        return {"serve": state["serve"], "config": state["config"], "device": "bp-ztp-a",
                "list": "Lab", "reason": "" if state["serve"] else "refused for the test"}

    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(("127.0.0.1", 0))
    stop = threading.Event()
    t = threading.Thread(target=r.serve, args=(listener,), daemon=True,
                         kwargs={"stop": stop, "handle_fn": lambda p, peer, **kw: r.handle(
                             p, peer, decide_fn=decide_fn, audit=audit, **kw)})
    t.start()
    yield listener.getsockname(), state, audit
    stop.set()
    t.join(2)
    listener.close()


def _rrq(name="bp-ztp-a.cfg", mode="octet", op=r.OP_RRQ):
    return struct.pack(">H", op) + name.encode() + b"\0" + mode.encode() + b"\0"


def _fetch(addr, packet=None, drop_first_ack=False):
    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.settimeout(5)
    c.bind(("127.0.0.1", 0))
    c.sendto(packet or _rrq(), addr)
    got, dropped = b"", False
    try:
        while True:
            data, src = c.recvfrom(2048)
            op, num = struct.unpack(">HH", data[:4])
            if op == r.OP_ERROR:
                return {"error": num, "text": data[4:-1].decode()}
            if drop_first_ack and not dropped:
                dropped = True
                continue           # the server must retransmit block 1
            if num == len(got) // r.BLOCK + 1:
                got += data[4:]
            c.sendto(struct.pack(">HH", r.OP_ACK, num), src)
            if len(data) - 4 < r.BLOCK:
                return {"data": got, "server_port": src[1]}
    finally:
        c.close()


class TestTheProtocol:
    def test_a_read_request_gets_the_config(self, server):
        addr, _state, audit = server
        out = _fetch(addr)
        assert out["data"] == CONFIG.encode()
        assert out["server_port"] != addr[1], "each transfer has its own transfer ID"
        assert audit.rows[-1]["what"] == "bootstrap_config"

    def test_an_exact_multiple_of_512_ends_with_an_empty_block(self, server):
        addr, state, _ = server
        state["config"] = b"x" * 1024
        assert _fetch(addr)["data"] == b"x" * 1024

    def test_a_lost_ack_is_retransmitted(self, server):
        addr, _state, _ = server
        assert _fetch(addr, drop_first_ack=True)["data"] == CONFIG.encode()

    def test_a_refusal_is_recorded_before_it_is_sent(self, server, monkeypatch):
        """C169: the refusal was SENT, then recorded, so a client (and this
        suite, under load) could hold the refusal before its row existed. A
        slow recorder makes the order deterministic: sent first, the client
        gets the error while the row is still being written."""
        import time as _time
        addr, _state, audit = server
        real = _Audit.__call__

        def slow(self, **row):
            _time.sleep(0.5)
            return real(self, **row)
        monkeypatch.setattr(_Audit, "__call__", slow)
        for packet in (_rrq(op=r.OP_WRQ), _rrq(mode="netascii"), b"\x00\x01junk"):
            before = len(audit.rows)
            out = _fetch(addr, packet)
            assert "error" in out, out
            assert len(audit.rows) == before + 1, "the refusal arrived before its row"

    def test_a_write_request_is_refused_and_recorded(self, server):
        addr, _state, audit = server
        out = _fetch(addr, _rrq(op=r.OP_WRQ))
        assert out["error"] == r.ERR_ACCESS and out["text"] == r.REFUSAL_TEXT
        assert "no write path" in audit.rows[-1]["detail"]

    def test_netascii_is_refused(self, server):
        addr, _state, audit = server
        assert _fetch(addr, _rrq(mode="netascii"))["error"] == r.ERR_ILLEGAL

    def test_a_refusal_tells_the_device_nothing_and_the_record_everything(self, server):
        addr, state, audit = server
        state["serve"] = False
        out = _fetch(addr)
        assert out["text"] == r.REFUSAL_TEXT
        assert audit.rows[-1]["detail"] == "refused for the test"

    def test_a_malformed_request_is_refused(self, server):
        addr, _state, _ = server
        assert _fetch(addr, b"\x00\x01nonul")["error"] == r.ERR_ILLEGAL


def test_nothing_is_served_unless_the_row_was_written():
    sent = []

    class _Sock:
        def bind(self, a):
            pass

        def sendto(self, data, peer):
            sent.append(data)

        def close(self):
            pass

    out = r.handle(_rrq(), (PEER, 1234), transfer_socket=_Sock,
                   decide_fn=lambda p, f: _decide(), audit=_Audit(recorded=False))
    assert not out["served"] and "audit row" in out["reason"]
    assert all(struct.unpack(">H", d[:2])[0] == r.OP_ERROR for d in sent), sent


# ── the real wiring: manifests read at request time, no list created ────────

def test_pending_ztp_devices_reads_the_real_manifest(tmp_path, monkeypatch):
    from modules import config, device
    from modules.nsot import manifest

    lists = tmp_path / "lists"
    repo = lists / "lab" / "config_repo"
    repo.mkdir(parents=True)
    monkeypatch.setattr(config, "LISTS_DIR", str(lists))
    monkeypatch.setattr(device, "get_device_lists", lambda: [
        {"name": "Lab", "filename": "lab"}, {"name": "Ghost", "filename": "ghost"}])
    manifest.upsert_device(str(repo), "uid:1", "bp-ztp-a", pending=True,
                           address_source="ztp", mgmt_mac=MAC, reserved_address=PEER)
    manifest.upsert_device(str(repo), "uid:2", "bp-dhcp-a", pending=True,
                           address_source="dhcp", mgmt_mac="aa:bb:cc:00:02:40",
                           reserved_address="192.0.2.40")
    found = r._pending_ztp_devices()
    assert [(ln, e["name"]) for ln, _repo, e in found] == [("Lab", "bp-ztp-a")]
    assert not (lists / "ghost").exists(), "reading must never create a list"
    manifest.mark_verified(str(repo), "uid:1")
    assert r._pending_ztp_devices() == [], "a verified device is no longer pending"


# ── M4's defect: systemd hands over a DUAL-STACK IPv6 socket ────────────────

class TestTheSocketSystemdActuallyHandsOver:
    """`ListenDatagram=69` is `Listen=[::]:69` (measured on the host), so an
    IPv4 device arrives as ("::ffff:<v4>", port, flowinfo, scope_id). Every
    protocol test above used an AF_INET listener, so none could see that the
    v4-mapped host matched no reservation (refused as "?") and that the
    4-tuple crashed the AF_INET reply (the device heard silence)."""

    @pytest.mark.parametrize("peer,host,family", [
        (("::ffff:192.0.2.50", 1234, 0, 0), "192.0.2.50", socket.AF_INET),
        (("192.0.2.50", 1234), "192.0.2.50", socket.AF_INET),
        (("2001:db8::50", 1234, 0, 0), "2001:db8::50", socket.AF_INET6),
    ])
    def test_the_peer_is_normalised_once(self, peer, host, family):
        got_host, reply, got_family = r.normalise_peer(peer)
        assert got_host == host and got_family == family
        assert reply[0] == host and reply[1] == 1234

    @pytest.fixture
    def dual_stack(self):
        audit, seen = _Audit(), []
        state = {"serve": True}

        def decide_fn(peer, filename):
            seen.append(peer)
            return {"serve": state["serve"], "config": CONFIG.encode(), "device": "bp-ztp-a",
                    "list": "Lab", "reason": "" if state["serve"] else "refused for the test"}

        listener = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        listener.bind(("::", 0))
        port = listener.getsockname()[1]
        stop = threading.Event()
        t = threading.Thread(target=r.serve, args=(listener,), daemon=True,
                             kwargs={"stop": stop, "handle_fn": lambda p, peer, **kw: r.handle(
                                 p, peer, decide_fn=decide_fn, audit=audit, **kw)})
        t.start()
        yield ("127.0.0.1", port), state, audit, seen
        stop.set()
        t.join(2)
        listener.close()

    def test_an_ipv4_device_is_identified_by_its_ipv4_address(self, dual_stack):
        addr, _state, audit, seen = dual_stack
        out = _fetch(addr)
        assert seen == ["127.0.0.1"], f"identified as {seen}, not the v4 address"
        assert out["data"] == CONFIG.encode()
        assert audit.rows[-1]["actor"] == "ztp:127.0.0.1"

    def test_a_refusal_reaches_the_device_instead_of_silence(self, dual_stack):
        addr, state, _audit, _seen = dual_stack
        state["serve"] = False
        out = _fetch(addr)
        assert out["error"] == r.ERR_ACCESS and out["text"] == r.REFUSAL_TEXT


def test_a_handler_that_raises_is_logged_as_failed_not_left_to_the_thread(caplog):
    """M4: a handler raising on its own thread printed a traceback and the
    device heard nothing. `handler FAILED` is the line job health counts."""
    def boom(peer, filename):
        raise RuntimeError("the manifests moved")

    class _Sock:
        def bind(self, a):
            pass

        def sendto(self, data, peer):
            pass

        def close(self):
            pass

    import logging
    with caplog.at_level(logging.ERROR, logger="modules.nsot.ztp_responder"):
        out = r.handle(_rrq(), ("::ffff:192.0.2.50", 1234, 0, 0), transfer_socket=_Sock,
                       decide_fn=boom, audit=_Audit())
    assert not out["served"] and "RuntimeError" in out["reason"]
    assert any("handler FAILED" in rec.getMessage() for rec in caplog.records)
