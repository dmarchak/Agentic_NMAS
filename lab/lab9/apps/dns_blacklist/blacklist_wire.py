"""dns_blacklist's wire format, apart from Ryu: a punted frame read down to its DNS question, and
the reply that answers a blocked one. Plain bytes in, plain values out; nothing here sends,
reads a switch or keeps time, so all of it is tested without a controller. Python 3.5 (the
controller's oldest measured interpreter, C2646): no f-strings, no variable annotations, the
standard library's `struct` and `ipaddress` alone. Ryu 4.34 has no DNS packet module and the
app allowlist takes no DNS library, so the parser is written here, small and STRICT: anything
it does not read exactly is refused with why, and the caller then follows the fail mode.

**A frame (`parse_frame`)**: Ethernet II, with any number of 802.1Q or 802.1ad tags (kept, so
the reply goes back on the query's VLAN), then
- IPv4: version 4, a header of 20 to 60 bytes, a total length the frame carries, not a fragment
  (no MF flag, offset 0: a fragment's later parts carry no question), protocol 17;
- IPv6: version 6, a payload length the frame carries, the next header 17 directly (an
  extension header is refused: a DNS query never carries one);
- UDP: a length the IP payload carries, destination port 53.

**A query (`parse_query`)**, RFC 1035 section 4.1: a 12-byte header with QR 0 and OPCODE 0
(QUERY), one question, no answer or authority records and at most one additional (EDNS's OPT);
the question's name as labels of 1 to 63 bytes, 255 bytes in all, NO compression pointer (a
question is the message's first name, so a pointer in it points nowhere legitimate), each byte
a letter, digit, hyphen or underscore (a name of other bytes cannot be asked of the verdict
service as it is, so it is refused, never escaped); class IN. The name is kept in lower case,
without the root's dot. The root name itself is refused: it names no site.

**The reply (`synthesise_reply`)**, for a blocked name when the block page is configured: the
query's Ethernet addresses, IP addresses and UDP ports swapped, its VLAN tags kept; an IPv4
header with its checksum, or an IPv6 one; the UDP checksum (mandatory over IPv6, given over
IPv4 too); the DNS header with the query's ID, QR 1, the query's RD, RA 1, RCODE 0 (NOERROR);
the question copied byte for byte; and one answer, a pointer to the question's name (0xC00C),
when the query asks for A and an IPv4 block page is set, or for AAAA and an IPv6 one is: its
address, for `BLOCK_TTL` seconds. Any other type (MX, TXT, HTTPS, an AAAA with no IPv6 block
page) is answered NOERROR with no answer (NODATA), so the host asks no further for it and a
browser falls back to the address family that has the block page.
"""

import ipaddress
import struct

ETH_IPV4, ETH_IPV6 = 0x0800, 0x86dd
#: The VLAN tag ethertypes kept on the way back: 802.1Q and 802.1ad.
VLAN_TAGS = (0x8100, 0x88a8)
UDP, DNS_PORT = 17, 53
#: RFC 1035's types and the class this app answers.
TYPE_A, TYPE_AAAA, CLASS_IN = 1, 28, 1
TYPE_NAMES = {1: "A", 2: "NS", 5: "CNAME", 6: "SOA", 12: "PTR", 15: "MX", 16: "TXT",
              28: "AAAA", 33: "SRV", 64: "SVCB", 65: "HTTPS", 255: "ANY"}
#: The answer's TTL: short, so a name taken off the list is asked again within a minute.
BLOCK_TTL = 60
#: The hop limit of the reply's IP header.
HOPS = 64
MAX_NAME = 255
MAX_LABEL = 63
_NAME_BYTES = frozenset(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")


def checksum(data):
    """The Internet checksum (RFC 1071) of *data*: the one's complement of the one's complement
    sum of its 16-bit words, an odd last byte padded with zero."""
    if len(data) % 2:
        data = data + b"\x00"
    total = 0
    for (word,) in struct.iter_unpack("!H", data):
        total += word
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return ~total & 0xffff


def parse_frame(data):
    """`(frame, why)`: *data* read as a UDP datagram to port 53 (see the module's docstring),
    as ``{"eth_dst", "eth_src", "tags", "ethertype", "version", "ip_src", "ip_dst",
    "udp_src", "udp_dst", "payload"}`` (addresses as bytes) with why ""; or None and why."""
    if not isinstance(data, (bytes, bytearray)):
        return None, "the frame is %s, not bytes" % type(data).__name__
    data = bytes(data)
    if len(data) < 14:
        return None, "the frame is %d bytes, shorter than an Ethernet header" % len(data)
    eth_dst, eth_src = data[0:6], data[6:12]
    at, tags = 12, []
    (ethertype,) = struct.unpack_from("!H", data, at)
    while ethertype in VLAN_TAGS:
        if len(data) < at + 6:
            return None, "a VLAN tag at byte %d is cut short" % at
        tags.append(data[at:at + 4])
        at += 4
        (ethertype,) = struct.unpack_from("!H", data, at)
    at += 2
    if ethertype == ETH_IPV4:
        ip, why = _ipv4(data, at)
    elif ethertype == ETH_IPV6:
        ip, why = _ipv6(data, at)
    else:
        return None, "the ethertype is 0x%04x, neither IPv4 nor IPv6" % ethertype
    if ip is None:
        return None, why
    version, ip_src, ip_dst, start, end = ip
    if end - start < 8:
        return None, "the IP payload is %d bytes, shorter than a UDP header" % (end - start)
    udp_src, udp_dst, length = struct.unpack_from("!HHH", data, start)
    if length < 8 or start + length > end:
        return None, "the UDP length %d is not what the IP payload carries (%d bytes)" % (
            length, end - start)
    if udp_dst != DNS_PORT:
        return None, "the UDP destination port is %d, not %d" % (udp_dst, DNS_PORT)
    return {"eth_dst": eth_dst, "eth_src": eth_src, "tags": tags, "ethertype": ethertype,
            "version": version, "ip_src": ip_src, "ip_dst": ip_dst, "udp_src": udp_src,
            "udp_dst": udp_dst, "payload": data[start + 8:start + length]}, ""


def _ipv4(data, at):
    if len(data) < at + 20:
        return None, "the IPv4 header at byte %d is cut short" % at
    first = data[at]
    ihl = (first & 0x0f) * 4
    if first >> 4 != 4 or ihl < 20 or len(data) < at + ihl:
        return None, "the IPv4 header's version and length byte 0x%02x is not one read" % first
    (total,) = struct.unpack_from("!H", data, at + 2)
    (frag,) = struct.unpack_from("!H", data, at + 6)
    if total < ihl or at + total > len(data):
        return None, "the IPv4 total length %d is not what the frame carries" % total
    if frag & 0x3fff:
        return None, "the IPv4 packet is a fragment (flags and offset 0x%04x)" % frag
    if data[at + 9] != UDP:
        return None, "the IPv4 protocol is %d, not UDP" % data[at + 9]
    return (4, data[at + 12:at + 16], data[at + 16:at + 20], at + ihl, at + total), ""


def _ipv6(data, at):
    if len(data) < at + 40:
        return None, "the IPv6 header at byte %d is cut short" % at
    if data[at] >> 4 != 6:
        return None, "the IPv6 header's version is %d" % (data[at] >> 4)
    (length,) = struct.unpack_from("!H", data, at + 4)
    if at + 40 + length > len(data):
        return None, "the IPv6 payload length %d is not what the frame carries" % length
    if data[at + 6] != UDP:
        return None, ("the IPv6 next header is %d, not UDP: an extension header is not read"
                      % data[at + 6])
    return (6, data[at + 8:at + 24], data[at + 24:at + 40], at + 40, at + 40 + length), ""


def parse_query(payload):
    """`(query, why)`: *payload* read as a DNS query (see the module's docstring), as ``{"id",
    "rd", "name", "qtype", "type_name", "question"}`` (``question``: the question section's
    bytes) with why ""; or None and why."""
    if len(payload) < 12:
        return None, "the DNS message is %d bytes, shorter than its header" % len(payload)
    ident, flags, qd, an, ns, ar = struct.unpack_from("!HHHHHH", payload, 0)
    if flags & 0x8000:
        return None, "the DNS message is a response (QR 1), not a query"
    if (flags >> 11) & 0x0f:
        return None, "the DNS opcode is %d, not QUERY (0)" % ((flags >> 11) & 0x0f)
    if qd != 1 or an or ns or ar > 1:
        return None, ("the DNS counts are %d questions, %d answers, %d authority and %d "
                      "additional; a query has one question, no answers or authority, and at "
                      "most one additional (EDNS)" % (qd, an, ns, ar))
    at, labels, wire = 12, [], 1
    while True:
        if at >= len(payload):
            return None, "the question's name runs past the message"
        size = payload[at]
        if size == 0:
            at += 1
            break
        if size & 0xc0:
            return None, ("the question's name holds a compression pointer or a reserved "
                          "label type (0x%02x), which a question never needs" % size)
        if at + 1 + size > len(payload):
            return None, "a label of the question's name runs past the message"
        label = payload[at + 1:at + 1 + size]
        if any(b not in _NAME_BYTES for b in label):
            return None, ("a label of the question's name holds a byte that is not a letter, "
                          "digit, hyphen or underscore")
        wire += 1 + size
        if wire > MAX_NAME:
            return None, "the question's name is longer than %d bytes" % MAX_NAME
        labels.append(label.decode("ascii").lower())
        at += 1 + size
    if not labels:
        return None, "the question names the root, which names no site"
    if at + 4 > len(payload):
        return None, "the question's type and class run past the message"
    qtype, qclass = struct.unpack_from("!HH", payload, at)
    if qclass != CLASS_IN:
        return None, "the question's class is %d, not IN (1)" % qclass
    return {"id": ident, "rd": bool(flags & 0x0100), "name": ".".join(labels), "qtype": qtype,
            "type_name": TYPE_NAMES.get(qtype, "TYPE%d" % qtype),
            "question": payload[12:at + 4]}, ""


def block_record(query, block_ipv4, block_ipv6):
    """`(type, rdata)` of the answer a blocked *query* gets, or None for NODATA: an A query
    gets *block_ipv4*, an AAAA query *block_ipv6* (each a text address or None)."""
    if query["qtype"] == TYPE_A and block_ipv4:
        return TYPE_A, ipaddress.IPv4Address(block_ipv4).packed
    if query["qtype"] == TYPE_AAAA and block_ipv6:
        return TYPE_AAAA, ipaddress.IPv6Address(block_ipv6).packed
    return None


def dns_reply(query, record):
    """The DNS reply to *query* carrying *record* (`block_record`'s), its bytes."""
    flags = 0x8000 | 0x0080 | (0x0100 if query["rd"] else 0)
    count = 1 if record is not None else 0
    out = struct.pack("!HHHHHH", query["id"], flags, 1, count, 0, 0) + query["question"]
    if record is not None:
        rtype, rdata = record
        out += struct.pack("!HHHIH", 0xc00c, rtype, CLASS_IN, BLOCK_TTL, len(rdata)) + rdata
    return out


def synthesise_reply(frame, query, block_ipv4, block_ipv6):
    """The whole frame answering *query* (from *frame*, `parse_frame`'s) with the block page's
    address (see the module's docstring)."""
    dns = dns_reply(query, block_record(query, block_ipv4, block_ipv6))
    src, dst = frame["ip_dst"], frame["ip_src"]
    length = 8 + len(dns)
    udp = struct.pack("!HHHH", frame["udp_dst"], frame["udp_src"], length, 0) + dns
    if frame["version"] == 4:
        pseudo = src + dst + struct.pack("!BBH", 0, UDP, length)
    else:
        pseudo = src + dst + struct.pack("!IxxxB", length, UDP)
    udp_sum = checksum(pseudo + udp) or 0xffff
    udp = udp[:6] + struct.pack("!H", udp_sum) + udp[8:]
    if frame["version"] == 4:
        header = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + length, 0, 0, HOPS, UDP, 0, src,
                             dst)
        header = header[:10] + struct.pack("!H", checksum(header)) + header[12:]
        ethertype = ETH_IPV4
    else:
        header = struct.pack("!IHBB16s16s", 0x60000000, length, UDP, HOPS, src, dst)
        ethertype = ETH_IPV6
    return (frame["eth_src"] + frame["eth_dst"] + b"".join(frame["tags"])
            + struct.pack("!H", ethertype) + header + udp)
