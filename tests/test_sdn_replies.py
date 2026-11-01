"""C2237: a flood's destination, or a transfer's receiver, is never named a source.

Blind SDN sessions (2026-10-29): F3's ICMP flood h2 to h4 named the victim 192.0.2.4 a source
from its echo replies; BF1 to BF3's bulk TCP named each receiver a source from its ACKs; each
with a rate limit proposed against it. `detect.mark_replies` marks such a detection replying;
`closed_loop` refuses any response against it, a person's choice included.

The cases are Mercury's own detection and collection structures in those runs' shapes (hosts
192.0.2.1 to .4; s1 holds h1 on port 1 and h2 on 2, s2 holds h3 on 1 and h4 on 2), not device
captures: the runs' captures are the locked blind set, and a recorded capture of these shapes
is the operator's to take (the overnight report)."""

import pytest

from modules.sdn import closed_loop, detect

S1, S2 = "0000000000000001", "0000000000000002"


def _det(source, targets, dpid_hex, port, rule="flood"):
    return {"rule": rule, "basis": "rate", "source": source, "sources": [source],
            "targets": list(targets), "connection": "lab", "dpid_hex": dpid_hex, "port": port,
            "key": f"{rule}|{dpid_hex}|{port}", "words": f"port {port} of {dpid_hex}"}


def _collected(*ports):
    """``(dpid_hex, port, pps, mean bytes)`` each: the collection's port rates."""
    switches = {}
    for dh, port, pps, size in ports:
        switches.setdefault(dh, []).append({"port_no": port, "rx_pps": pps,
                                            "rx_bytes_per_s": pps * size})
    return {"controllers": [{"connection": "lab", "switches": [
        {"dpid_hex": dh, "ports": ps} for dh, ps in switches.items()]}]}


def test_a_bulk_transfer_s_receiver_is_marked_replying_and_its_sender_kept():
    """BF1: h1 sends to h3 at line rate; h3's port carries its ACKs, far smaller packets."""
    sender = _det("192.0.2.1", ["192.0.2.3"], S1, 1)
    receiver = _det("192.0.2.3", ["192.0.2.1"], S2, 1)
    got = detect.mark_replies([sender, receiver],
                              _collected((S1, 1, 36616, 1500), (S2, 1, 28455, 66)))
    assert got[0]["source"] == "192.0.2.1" and "replying_to" not in got[0]
    assert got[1]["source"] is None and got[1]["sources"] == []
    assert got[1]["replying_hosts"] == ["192.0.2.3"]
    assert got[1]["replying_to"]["source"] == "192.0.2.1"
    assert "192.0.2.3 is the destination of 192.0.2.1's traffic" in got[1]["words"]


def test_an_icmp_flood_s_two_sides_of_one_size_name_neither():
    """F3: requests and echo replies are the same size, so neither side is named a source."""
    attacker = _det("192.0.2.2", ["192.0.2.4"], S1, 2)
    victim = _det("192.0.2.4", ["192.0.2.2"], S2, 2)
    got = detect.mark_replies([attacker, victim],
                              _collected((S1, 2, 32191, 42), (S2, 2, 30580, 42)))
    assert [g["source"] for g in got] == [None, None]
    assert all(g["replying_to"]["neither"] for g in got)
    assert "are each other's destination" in got[0]["words"]


def test_a_one_way_flood_keeps_its_source():
    """Lab 8's UDP flood h2 to h4: the victim answers nothing, so only the attacker fires."""
    got = detect.mark_replies([_det("192.0.2.2", ["192.0.2.4"], S1, 2)],
                              _collected((S1, 2, 1782.7, 1470)))
    assert got[0]["source"] == "192.0.2.2" and "replying_to" not in got[0]


def test_several_sources_flooding_one_destination_keep_their_sources():
    """F6: h1, h2 and h4 flood h3 over UDP; none is another's destination."""
    dets = [_det(s, ["192.0.2.3"], dh, p) for s, dh, p in
            (("192.0.2.1", S1, 1), ("192.0.2.2", S1, 2), ("192.0.2.4", S2, 2))]
    got = detect.mark_replies(dets, _collected((S1, 1, 1784, 1470), (S1, 2, 1784, 1470),
                                               (S2, 2, 1787, 1470)))
    assert [g["source"] for g in got] == ["192.0.2.1", "192.0.2.2", "192.0.2.4"]


def test_an_address_written_two_ways_is_one_host():
    """IPv6 beside IPv4: the comparison is by address, not by its spelling."""
    sender = _det("2001:db8:8::1", ["2001:db8:8::3"], S1, 1)
    receiver = _det("2001:DB8:8:0::3", ["2001:0db8:8::1"], S2, 1)
    got = detect.mark_replies([sender, receiver],
                              _collected((S1, 1, 36616, 1500), (S2, 1, 28455, 66)))
    assert got[0]["source"] == "2001:db8:8::1" and got[1]["source"] is None


def test_no_response_is_built_against_a_replying_host_even_when_a_person_chooses_it():
    receiver = detect.mark_replies(
        [_det("192.0.2.1", ["192.0.2.3"], S1, 1), _det("192.0.2.3", ["192.0.2.1"], S2, 1)],
        _collected((S1, 1, 36616, 1500), (S2, 1, 28455, 66)))[1]
    for params in ({}, {"source": "192.0.2.3"}):
        with pytest.raises(closed_loop.ResponseRefused) as exc:
            closed_loop._response_source(None, "lab", 2, receiver, dict(params))
        assert "192.0.2.3 sends replies to 192.0.2.1's traffic" in str(exc.value)
