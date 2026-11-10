"""blacklist_wire over real bytes: a punted frame read down to its question, IPv4 and IPv6, and
the reply a blocked query gets. Plain functions and asserts, Python 3.5 and Mercury's alike.

**Where the bytes come from (2026-11-10, in mercury-harness-apptest:4.34-py3.5).** Each query's
DNS message was made by dnspython 1.16.0 (the image's, an eventlet dependency; the app
allowlist takes no DNS library, so it is not imported here), `dns.message.make_query` with a
fixed ID, and wrapped in Ethernet, IPv4 or IPv6 and UDP headers built by a separate script
with its own checksum code. Each reply below is what `synthesise_reply` gave for that query
with the block page 192.0.2.80 and 2001:db8::80, and dnspython's `dns.message.from_wire` read
it back as:
- `REPLY_A4`: ID 0x1a2b, QR, RD and RA set, NOERROR, `malware.testcategory.com. IN A`, answer
  `malware.testcategory.com. 60 IN A 192.0.2.80`;
- `REPLY_AAAA6`: ID 0x2b3c, NOERROR, answer `malware.testcategory.com. 60 IN AAAA 2001:db8::80`;
- `REPLY_MX4`: ID 0x3c4d, NOERROR, question `IN MX`, no answer (NODATA);
- `REPLY_EDNS4`: ID 0x4d5e, NOERROR, question `Example.COM. IN A` (its case kept), answer
  `Example.COM. 60 IN A 192.0.2.80`.
That script's checksums of each reply's IPv4 header and UDP datagram verified too; the tests
below check them again with their own sum. Addresses are documentation ones.
"""

import struct

try:
    from mercury_app.testing import covers
except ImportError:                     # run with no SDK on the path (the gate reads the import)
    def covers(*_names):
        return lambda test: test

import blacklist_wire as W

PAGE4, PAGE6 = "192.0.2.80", "2001:db8::80"


def hexed(text):
    """*text*'s hex digits as bytes (spaces only group them)."""
    return bytes.fromhex(text.replace(" ", ""))


QUERY_A4 = hexed(
    "020000000001 02000000000a 0800 4500004612344000401 1a433c000020ac0000235"
    "9c40 0035 0032 0afa 1a2b01000001000000000000076d616c776172650c7465737463617465676f7279"
    "03636f6d0000010001")
QUERY_AAAA6 = hexed(
    "020000000001 02000000000a 86dd 6000000000321140 20010db800000000000000000000000a"
    "20010db8000000000000000000000035 9c41 0035 0032 225c 2b3c010000010000000000000"
    "76d616c776172650c7465737463617465676f727903636f6d00001c0001")
QUERY_MX4 = hexed(
    "020000000001 02000000000a 0800 4500004612344000401 1a433c000020ac0000235"
    "9c40 0035 0032 e8c9 3c4d01000001000000000000076d616c776172650c7465737463617465676f7279"
    "03636f6d00000f0001")
QUERY_EDNS4 = hexed(
    "020000000001 02000000000a 0800 4500004412344000401 1a435c000020ac0000235"
    "9c40 0035 0030 dd42 4d5e010000010000000000010 74578616d706c6503434f4d0000010001"
    "0000290500000000000000")
REPLY_A4 = hexed(
    "02000000000a020000000001080045000056000000004011f657c0000235c000020a00359c40004207b9"
    "1a2b81800001000100000000076d616c776172650c7465737463617465676f727903636f6d0000010001"
    "c00c000100010000003c0004c0000250")
REPLY_AAAA6 = hexed(
    "02000000000a02000000000186dd60000000004e114020010db800000000000000000000003520010db8"
    "00000000000000000000000a00359c41004eb2f32b3c81800001000100000000076d616c776172650c74"
    "65737463617465676f727903636f6d00001c0001c00c001c00010000003c001020010db8000000000000"
    "000000000080")
REPLY_MX4 = hexed(
    "02000000000a020000000001080045000046000000004011f667c0000235c000020a00359c4000326849"
    "3c4d81800001000000000000076d616c776172650c7465737463617465676f727903636f6d00000f0001")
REPLY_EDNS4 = hexed(
    "02000000000a020000000001080045000049000000004011f664c0000235c000020a00359c400035c25e"
    "4d5e81800001000100000000074578616d706c6503434f4d0000010001c00c000100010000003c0004c0"
    "000250")


def read(frame):
    got, why = W.parse_frame(frame)
    assert got is not None, why
    query, why = W.parse_query(got["payload"])
    assert query is not None, why
    return got, query


def refusal(frame):
    """Why *frame* is refused, by the frame or the query reader."""
    got, why = W.parse_frame(frame)
    if got is None:
        return why
    query, why = W.parse_query(got["payload"])
    assert query is None
    return why


def sums_verify(reply):
    """The reply's IPv4 header and UDP checksums verify (the whole sums to zero), by this
    test's own sum, not the module's."""
    def total(data):
        if len(data) % 2:
            data += b"\x00"
        s = 0
        for i in range(0, len(data), 2):
            s += (data[i] << 8) | data[i + 1]
        while s >> 16:
            s = (s & 0xffff) + (s >> 16)
        return s

    if reply[12:14] == b"\x08\x00":
        ip, udp = reply[14:34], reply[34:]
        pseudo = ip[12:20] + b"\x00\x11" + struct.pack("!H", len(udp))
        return total(ip) == 0xffff and total(pseudo + udp) == 0xffff
    ip, udp = reply[14:54], reply[54:]
    pseudo = ip[8:40] + struct.pack("!I", len(udp)) + b"\x00\x00\x00\x11"
    return total(pseudo + udp) == 0xffff


@covers("a bad site is blocked, over IPv4 and IPv6")
def test_an_ipv4_query_and_an_ipv6_query_are_read_to_their_question():
    frame, query = read(QUERY_A4)
    assert frame["version"] == 4 and frame["udp_src"] == 40000 and frame["tags"] == []
    assert (query["name"], query["type_name"], query["id"], query["rd"]) == \
        ("malware.testcategory.com", "A", 0x1a2b, True)
    frame, query = read(QUERY_AAAA6)
    assert frame["version"] == 6 and frame["ip_src"] == hexed("20010db8" + "0" * 22 + "0a")
    assert (query["name"], query["type_name"], query["id"]) == \
        ("malware.testcategory.com", "AAAA", 0x2b3c)


@covers("a bad site is blocked, over IPv4 and IPv6")
def test_a_blocked_query_is_answered_with_the_block_page_a_real_parser_reads():
    for query_bytes, reply_bytes in ((QUERY_A4, REPLY_A4), (QUERY_AAAA6, REPLY_AAAA6)):
        frame, query = read(query_bytes)
        reply = W.synthesise_reply(frame, query, PAGE4, PAGE6)
        assert reply == reply_bytes
        assert sums_verify(reply)
        # Back to the host: the Ethernet addresses swapped, the host's port the destination.
        assert reply[0:6] == query_bytes[6:12] and reply[6:12] == query_bytes[0:6]


def test_a_query_for_a_type_with_no_block_page_is_answered_nodata():
    frame, query = read(QUERY_MX4)
    assert query["type_name"] == "MX"
    assert W.block_record(query, PAGE4, PAGE6) is None
    reply = W.synthesise_reply(frame, query, PAGE4, PAGE6)
    assert reply == REPLY_MX4 and sums_verify(reply)
    _frame, aaaa = read(QUERY_AAAA6)
    assert W.block_record(aaaa, PAGE4, None) is None
    assert W.block_record(aaaa, None, PAGE6) == (W.TYPE_AAAA, hexed("20010db8" + "0" * 22 + "80"))


def test_a_name_is_read_in_lower_case_and_the_reply_keeps_the_question_as_asked():
    frame, query = read(QUERY_EDNS4)
    assert query["name"] == "example.com" and query["type_name"] == "A"
    reply = W.synthesise_reply(frame, query, PAGE4, None)
    assert reply == REPLY_EDNS4 and b"\x07Example\x03COM\x00" in reply


def test_a_vlan_tag_is_kept_on_the_reply():
    tagged = QUERY_A4[:12] + b"\x81\x00\x00\xc8" + QUERY_A4[12:]
    frame, query = read(tagged)
    assert frame["tags"] == [b"\x81\x00\x00\xc8"]
    reply = W.synthesise_reply(frame, query, PAGE4, None)
    assert reply[12:16] == b"\x81\x00\x00\xc8"
    assert reply[:12] + reply[16:] == REPLY_A4


def _with_dns(frame, at, new):
    """*frame* (an IPv4 query) with its DNS bytes from *at* replaced by *new*; the lengths
    are mended so only the DNS change is refused."""
    dns = frame[42:]
    dns = dns[:at] + new + dns[at + len(new):]
    ip = bytearray(frame[14:34])
    ip[2:4] = struct.pack("!H", 28 + len(dns))
    udp = bytearray(frame[34:42])
    udp[4:6] = struct.pack("!H", 8 + len(dns))
    return frame[:14] + bytes(ip) + bytes(udp) + dns


def test_what_is_not_exactly_a_query_is_refused_with_why():
    cases = [
        (QUERY_A4[:20], "cut short"),
        (QUERY_A4[:12] + b"\x08\x06" + QUERY_A4[14:], "neither IPv4 nor IPv6"),
        (QUERY_A4[:20] + b"\x20\x00" + QUERY_A4[22:], "is a fragment"),
        (QUERY_A4[:23] + b"\x06" + QUERY_A4[24:], "not UDP"),
        (QUERY_A4[:36] + b"\x00\x44" + QUERY_A4[38:], "not 53"),
        (QUERY_AAAA6[:20] + b"\x00" + QUERY_AAAA6[21:], "extension header"),
        (_with_dns(QUERY_A4, 2, b"\x81\x00"), "a response"),
        (_with_dns(QUERY_A4, 2, b"\x29\x00"), "opcode is 5"),
        (_with_dns(QUERY_A4, 4, b"\x00\x02"), "2 questions"),
        (_with_dns(QUERY_A4, 12, b"\xc0\x0c"), "compression pointer"),
        (_with_dns(QUERY_A4, 13, b"m%lware"), "not a letter"),
        (_with_dns(QUERY_A4, 12, b"\x00\x00\x01\x00\x01"), "names the root"),
        (_with_dns(QUERY_A4, 40, b"\x00\x03"), "class is 3"),
    ]
    for frame, words in cases:
        assert words in refusal(frame), (words, refusal(frame))


def test_a_name_longer_than_255_bytes_is_refused():
    labels = b"".join(b"\x3f" + b"a" * 63 for _ in range(4))
    dns = QUERY_A4[42:54] + labels + b"\x00\x00\x01\x00\x01"
    assert "longer than 255" in refusal(_with_dns(QUERY_A4[:42] + dns, 0, b""))


def test_the_checksum_is_rfc_1071s():
    # RFC 1071 section 3's example words sum to 0xddf2, so the checksum is its complement.
    assert W.checksum(hexed("0001f203f4f5f6f7")) == 0xffff - 0xddf2
    assert W.checksum(b"\x01") == 0xfeff
