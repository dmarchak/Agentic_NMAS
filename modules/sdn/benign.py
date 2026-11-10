"""Benign traffic a detection rule fired on, decided in code (C2305; Lab 9 B3): the evidence
that separates a bulk transfer from a flood, and a set of passive sessions from a scan, read
from a detection's evidence pack, and where code alone can decide, the decision, with no
model call.

**Why** (C2305): sdn_classify answered every benign detection of the blind set a threat (0 of
100 runs said no threat on BF1, BF2, BF3 and BS3), so it never stood between a rule's false
positive and a proposal against a benign sender. The evidence that separates them is already
in the pack, as counters: it is computed here, in code, where a model's reading of it failed.

**A transfer, not a flood** (`transfer_shape`; the flood rule's detections, and High packet
rate's): on the detection's own port, read both ways over the same sample:
- **symmetric**: one direction carries data (a mean of at least `detect.TRANSFER_DATA_BYTES`,
  500 B, a packet) and the other its ACKs (at most `detect.TRANSFER_ACK_BYTES`, 100 B), the
  ACKs at least `detect.TRANSFER_ACK_SHARE` (0.3) and at most `ACK_SHARE_MAX` (2) of the data's
  packets. A flood is one-way: a UDP flood's victim sends back about nothing (F5: 1 packet a
  second against 4,464), and an ICMP or SYN flood's replies are as small as its packets;
- **TCP**: no flow entering the port names another protocol (a flow matching MAC addresses only
  names none, as a reactive L2 application's do on the receiving side);
- **bounded**: at most `detect.TRANSFER_SESSIONS` (4) TCP sessions among the entering flows;
- **under capacity**, where the port's link speed was read (its port description's
  ``curr_speed``, carried on the port's piece when the collection read link status): both
  directions together under `CAPACITY_SHARE` (0.9) of it. At or over it, a transfer crowds its
  link: code does not decide, and the model and a person do. Where the speed was not read, it
  is said, and the shape decides.
**Passive sessions, not a scan** (`session_shape`; the scan rule's detections): the source's
flows each carry a session's data, not a probe: their median packet count at least
`SESSION_PACKETS` (5) and their median mean packet at least `detect.TRANSFER_DATA_BYTES`, to at
most `detect.TRANSFER_SESSIONS` destinations. A scan's flows carry one or two packets (a SYN, a
FIN, a reset) or none (a reactive application installs one on a packet-in).

**What is decided** (`decide`): ``{"decided", "kind", "words", "shape"}``: *decided* True only
when every condition holds; *shape* the figures, said whether or not it decides, for the
classifier's request (`closed_loop.sent_evidence`) and the card. Deciding "no threat" is an
allowing decision by resemblance, so its conditions are all measured, its thresholds the flood
rule's own (C2278), and it proposes no action (a person still sees the card, never AUTO).
"""

import statistics

#: The most ACK packets to data packets a transfer's ACKs make (delayed ACKs make about one per
#: two segments; offloaded segments, one per large packet: BF1's port 0.78).
ACK_SHARE_MAX = 2.0
#: A transfer at or over this share of its link's speed crowds it: code does not decide.
CAPACITY_SHARE = 0.9
#: A flow carrying at least this many packets (the median of the source's) is a session's.
SESSION_PACKETS = 5
KINDS = ("transfer", "sessions")


def _pieces(section: dict, kind: str) -> list:
    return [p for p in (section or {}).get("pieces") or [] if p.get("kind") == kind]


def _detection(section: dict) -> dict:
    return next(iter(_pieces(section, "detection")), {})


def _mean(nbytes, packets):
    return (nbytes / packets) if packets else None


def transfer_shape(section: dict) -> dict:
    """The figures a transfer is told from a flood by, on the detection's port: ``{"port",
    "rx_pps", "tx_pps", "rx_mean_bytes", "tx_mean_bytes", "side", "ack_share", "protocols",
    "sessions", "capacity_kbps", "load_share", "holds": {condition: bool}, "words"}``, or None
    when the pack holds no piece of that port."""
    from modules.sdn import detect

    det = _detection(section)
    port = det.get("port")
    piece = next((p for p in _pieces(section, "port") if p.get("port_no") == port), None)
    if piece is None or port is None:
        return None
    rx_pps, tx_pps = float(piece.get("rx_pps") or 0), float(piece.get("tx_pps") or 0)
    rx_mean = _mean(piece.get("rx_bytes_delta") or 0, piece.get("rx_packets_delta") or 0)
    tx_mean = _mean(piece.get("tx_bytes_delta") or 0, piece.get("tx_packets_delta") or 0)
    side, share = "", None
    if rx_mean is not None and tx_mean is not None:
        if rx_mean >= detect.TRANSFER_DATA_BYTES and tx_mean <= detect.TRANSFER_ACK_BYTES:
            side, share = "data", (tx_pps / rx_pps if rx_pps else None)
        elif tx_mean >= detect.TRANSFER_DATA_BYTES and rx_mean <= detect.TRANSFER_ACK_BYTES:
            side, share = "acks", (rx_pps / tx_pps if tx_pps else None)
    entering = [f for f in _pieces(section, "flow") if (f.get("match") or {}).get("in_port")
                == port]
    protocols = sorted({(f.get("match") or {}).get("ip_proto") for f in entering
                        if (f.get("match") or {}).get("ip_proto") is not None})
    sessions = len({(m.get("ipv4_src") or m.get("ipv6_src"), m.get("ipv4_dst") or
                     m.get("ipv6_dst"), m.get("tcp_dst")) for f in entering
                    for m in [f.get("match") or {}] if m.get("ip_proto") == 6})
    speed = piece.get("curr_speed_kbps")
    load = ((float(piece.get("rx_bytes_per_s") or 0) + float(piece.get("tx_bytes_per_s") or 0))
            * 8 / 1000.0)
    load_share = (load / speed) if speed else None
    holds = {
        "symmetric": bool(side) and share is not None and
        detect.TRANSFER_ACK_SHARE <= share <= ACK_SHARE_MAX,
        "tcp": all(p == 6 for p in protocols),
        "bounded": sessions <= detect.TRANSFER_SESSIONS,
        "under_capacity": load_share is None or load_share < CAPACITY_SHARE}
    said = []
    said.append(f"port {port} receives {rx_pps:,.0f} packets a second"
                + (f" at a mean of {rx_mean:,.0f} B" if rx_mean is not None else "")
                + f" and sends {tx_pps:,.0f}"
                + (f" at {tx_mean:,.0f} B" if tx_mean is not None else ""))
    if side:
        sends = "it sends the data" if side == "data" else "it sends the ACKs"
        said.append(f"one way data, the other ACKs at {share:.2f} of the data's packets "
                    f"({sends})" if share is not None else "one way data, the other no packets")
    else:
        said.append("not one way data and the other ACKs")
    said.append("no entering flow names a protocol other than TCP" if holds["tcp"] else
                f"entering flows name protocol{'s' if len(protocols) != 1 else ''} "
                f"{', '.join(str(p) for p in protocols)}")
    said.append(f"{sessions} TCP session{'s' if sessions != 1 else ''} among its entering flows")
    said.append(f"at {load_share:.0%} of its {speed / 1000:,.0f} Mbit/s link" if load_share
                is not None else "the link's speed was not read")
    return {"port": port, "rx_pps": round(rx_pps, 1), "tx_pps": round(tx_pps, 1),
            "rx_mean_bytes": None if rx_mean is None else round(rx_mean, 1),
            "tx_mean_bytes": None if tx_mean is None else round(tx_mean, 1),
            "side": side, "ack_share": None if share is None else round(share, 3),
            "protocols": protocols, "sessions": sessions, "capacity_kbps": speed,
            "load_share": None if load_share is None else round(load_share, 3),
            "holds": holds, "words": "; ".join(said)}


def session_shape(section: dict) -> dict:
    """The figures a set of sessions is told from a scan by: ``{"flows", "median_packets",
    "median_mean_bytes", "destinations", "holds", "words"}``, or None with no flow."""
    from modules.sdn import detect

    det = _detection(section)
    flows = [f for f in _pieces(section, "flow")
             if (f.get("match") or {}).get("ipv4_src", (f.get("match") or {}).get("ipv6_src"))
             == det.get("source")] if det.get("source") else []
    if not flows:
        return None
    packets = [int(f.get("packet_count") or 0) for f in flows]
    means = [(f.get("byte_count") or 0) / f["packet_count"] for f in flows
             if f.get("packet_count")]
    dsts = {(f.get("match") or {}).get("ipv4_dst") or (f.get("match") or {}).get("ipv6_dst")
            for f in flows}
    med_p = statistics.median(packets)
    med_b = statistics.median(means) if means else 0.0
    holds = {"sessions": med_p >= SESSION_PACKETS,
             "data": med_b >= detect.TRANSFER_DATA_BYTES,
             "bounded": len(dsts) <= detect.TRANSFER_SESSIONS}
    words = (f"its {len(flows)} flows carry a median of {med_p:g} packets at a median mean of "
             f"{med_b:,.0f} B, to {len(dsts)} destination{'s' if len(dsts) != 1 else ''}")
    return {"flows": len(flows), "median_packets": med_p, "median_mean_bytes": round(med_b, 1),
            "destinations": len(dsts), "holds": holds, "words": words}


def decide(section: dict) -> dict:
    """Whether code decides the detection in *section* (a pack's sdn section) is benign:
    ``{"decided", "kind", "words", "shape"}`` (see the module's docstring)."""
    det = _detection(section)
    rule = det.get("rule")
    if rule in ("flood", "high_rate"):
        shape, kind = transfer_shape(section), "transfer"
    elif rule == "scan":
        shape, kind = session_shape(section), "sessions"
    else:
        return {"decided": False, "kind": "", "words": "", "shape": None}
    if shape is None:
        return {"decided": False, "kind": kind, "words": "", "shape": None}
    failing = [k for k, ok in shape["holds"].items() if not ok]
    if failing:
        return {"decided": False, "kind": kind, "shape": shape,
                "words": f"not decided in code ({', '.join(failing)} not met): {shape['words']}"}
    what = ("a bulk TCP transfer, not a flood" if kind == "transfer" else
            "sessions carrying data, not a scan's probes")
    return {"decided": True, "kind": kind, "shape": shape,
            "words": f"no threat, decided in code with no AI call: {what}: {shape['words']}"}
