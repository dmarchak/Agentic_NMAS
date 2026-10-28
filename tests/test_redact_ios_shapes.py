"""C745: the IOS credential shapes `redact._POSITIONAL` did not know, each masked by position
in every form IOS gives it, and nothing else moved. C2074 (its own section below): the shapes
still in clear after C745, by the same method.

**Where the lines come from.** No capture holds any of these shapes: the fleet's captured
configurations were scanned (`TestTheFleetsCaptures` below, counts only) and none appears, nor
in the first D15 or Oxidized archive (C745's own measurement, 2026-10-13). So each line is the
vendor's documented command form, from Cisco's IOS and IOS XE command references (named per
shape below), with an invented value; the `7` and `6` forms carry a value of the type's shape,
invented too. Addresses are 192.0.2.x and 2001:db8::.

**What each case asserts.** The expected output is built by plain string replacement of the
planted value with its placeholder, a path independent of the patterns under test, so a case
holds that the value is gone AND that every other byte of the line (its keywords, key number,
encryption type, algorithm, addresses) is kept.

**The ordering hazards** (each a named test): NTP's `ntp authentication-key 1 md5 <k>` read by
a bare `authentication-key` rule gives `1` as the type and masks `md5`, leaving the key in
clear (C1845's warning), so no rule here is bare and NTP's names its carrier; a key chain's
`key 1` is an ID, not a server's key; a `\\s` between tokens would let a match run onto the
next line.
"""
import fnmatch
import os
import re

import pytest

from modules import redact
from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The labels C745 added, in `_POSITIONAL`.
C745_LABELS = ("ospf_key", "neighbor_password", "snmp_user_auth", "snmp_user_priv",
               "isakmp_key", "server_key", "fhrp_authentication", "ntp_key")


def _p(label):
    return f"<redacted:{label}>"


#: (line, [(label, planted value)]): each value occurs once in its line.
FORMS = [
    # OSPF, an interface's keys: `ip ospf message-digest-key key-id md5 [0|7] key` and
    # `ip ospf authentication-key [0|7] password` (IOS IP Routing: OSPF Command Reference).
    (" ip ospf message-digest-key 1 md5 PlantedOspfMd5", [("ospf_key", "PlantedOspfMd5")]),
    (" ip ospf message-digest-key 1 md5 7 0605027D1D4F5D", [("ospf_key", "0605027D1D4F5D")]),
    (" ip ospf message-digest-key 255 md5 0 PlantedOspfMd5", [("ospf_key", "PlantedOspfMd5")]),
    (" ip ospf authentication-key PlantedOspfAk", [("ospf_key", "PlantedOspfAk")]),
    (" ip ospf authentication-key 7 0822455D0A16", [("ospf_key", "0822455D0A16")]),
    # A clear value of digits alone is the value, never an encryption type.
    (" ip ospf authentication-key 12345678", [("ospf_key", "12345678")]),
    # BGP: `neighbor {ip-address | ipv6-address | peer-group-name} password [0|7] string` (IP
    # Routing: BGP Command Reference); LDP's `mpls ldp neighbor ip-address password [0|7]
    # password` (MPLS Command Reference) is the same shape.
    (" neighbor 192.0.2.7 password PlantedBgpPw", [("neighbor_password", "PlantedBgpPw")]),
    (" neighbor 192.0.2.7 password 7 0822455D0A16544541",
     [("neighbor_password", "0822455D0A16544541")]),
    (" neighbor 2001:db8::7 password PlantedBgpPw", [("neighbor_password", "PlantedBgpPw")]),
    (" neighbor 2001:db8::7 password 7 0822455D0A16544541",
     [("neighbor_password", "0822455D0A16544541")]),
    (" neighbor PEERS password 0 PlantedBgpPw", [("neighbor_password", "PlantedBgpPw")]),
    ("mpls ldp neighbor 192.0.2.3 password PlantedLdpPw", [("neighbor_password", "PlantedLdpPw")]),
    ("mpls ldp neighbor 192.0.2.3 password 7 0822455D0A16",
     [("neighbor_password", "0822455D0A16")]),
    # SNMPv3: `snmp-server user username group-name [remote host [udp-port port] [vrf vrf]] v3
    # [encrypted] [auth {md5 | sha} auth-password] [priv {des | 3des | aes {128 | 192 | 256}}
    # privpassword]` (Network Management Command Reference).
    ("snmp-server user ops OPS v3 auth sha PlantedAuthPw1 priv aes 128 PlantedPrivPw1",
     [("snmp_user_auth", "PlantedAuthPw1"), ("snmp_user_priv", "PlantedPrivPw1")]),
    ("snmp-server user ops OPS v3 auth md5 PlantedAuthPw1 priv des PlantedPrivPw1",
     [("snmp_user_auth", "PlantedAuthPw1"), ("snmp_user_priv", "PlantedPrivPw1")]),
    ("snmp-server user ops OPS v3 auth sha PlantedAuthPw1 priv 3des PlantedPrivPw1 access 10",
     [("snmp_user_auth", "PlantedAuthPw1"), ("snmp_user_priv", "PlantedPrivPw1")]),
    ("snmp-server user ops OPS v3 auth sha PlantedAuthPw1", [("snmp_user_auth", "PlantedAuthPw1")]),
    ("snmp-server user ops OPS v3 encrypted auth sha 3A1B2C3D4E5F60718293 priv aes 256 "
     "4F5E6D7C8B9A0A1B2C3D",
     [("snmp_user_auth", "3A1B2C3D4E5F60718293"), ("snmp_user_priv", "4F5E6D7C8B9A0A1B2C3D")]),
    ("snmp-server user ops OPS remote 192.0.2.40 udp-port 162 vrf MGMT v3 auth sha "
     "PlantedAuthPw1 priv aes 128 PlantedPrivPw1",
     [("snmp_user_auth", "PlantedAuthPw1"), ("snmp_user_priv", "PlantedPrivPw1")]),
    ("snmp-server user ops OPS remote 2001:db8::40 v3 auth sha PlantedAuthPw1 priv aes 192 "
     "PlantedPrivPw1",
     [("snmp_user_auth", "PlantedAuthPw1"), ("snmp_user_priv", "PlantedPrivPw1")]),
    # A user named `auth` in a group named `sha`: the keywords are read by position, never
    # by resemblance.
    ("snmp-server user auth sha v3 auth sha PlantedAuthPw1 priv aes 128 PlantedPrivPw1",
     [("snmp_user_auth", "PlantedAuthPw1"), ("snmp_user_priv", "PlantedPrivPw1")]),
    # IKE: `crypto isakmp key [0|6] keystring {address peer-address [mask] | address ipv6
    # {ipv6-address/ipv6-prefix} | hostname hostname} [no-xauth]` (Security Command Reference).
    ("crypto isakmp key PlantedIkeKey address 192.0.2.1", [("isakmp_key", "PlantedIkeKey")]),
    ("crypto isakmp key 0 PlantedIkeKey address 0.0.0.0 0.0.0.0 no-xauth",
     [("isakmp_key", "PlantedIkeKey")]),
    ("crypto isakmp key 6 PlantedType6Ike address ipv6 2001:db8::1/128",
     [("isakmp_key", "PlantedType6Ike")]),
    ("crypto isakmp key PlantedIkeKey hostname peer1.example.net",
     [("isakmp_key", "PlantedIkeKey")]),
    # A one-character key that looks like a type: the value, never the keyword after it.
    ("crypto isakmp key 7 address 192.0.2.1", [("isakmp_key", "7")]),
    # A server block's key: `tacacs server name` / `radius server name`, then `key [0|7]
    # string` (Security Command Reference); and an ISAKMP client group's `key name`.
    (" key 7 0475071A0B", [("server_key", "0475071A0B")]),
    (" key 0 PlantedSrvKey", [("server_key", "PlantedSrvKey")]),
    (" key PlantedSrvKey", [("server_key", "PlantedSrvKey")]),
    (" key 6 PlantedType6Srv", [("server_key", "PlantedType6Srv")]),
    ("key 7 0475071A0B", [("server_key", "0475071A0B")]),
    # HSRP: `standby [group-number] authentication {text string | md5 {key-string [0|7] key |
    # key-chain name}}`, and the pre-12.3(2)T form with no `text`; VRRP: `vrrp group
    # authentication {text text-string | md5 ...}`; GLBP: `glbp group authentication {text
    # string | md5 ...}` (First Hop Redundancy Protocols Command Reference).
    (" standby 1 authentication PlantedHsrpStr", [("fhrp_authentication", "PlantedHsrpStr")]),
    (" standby 1 authentication text PlantedHsrpStr",
     [("fhrp_authentication", "PlantedHsrpStr")]),
    (" standby authentication PlantedHsrpStr", [("fhrp_authentication", "PlantedHsrpStr")]),
    (" standby 10 authentication text md5", [("fhrp_authentication", "md5")]),
    (" vrrp 1 authentication text PlantedVrrpStr", [("fhrp_authentication", "PlantedVrrpStr")]),
    (" glbp 1 authentication text PlantedGlbpStr", [("fhrp_authentication", "PlantedGlbpStr")]),
    # Their `md5 key-string` forms were `key_string`'s already, and stay so.
    (" standby 1 authentication md5 key-string 7 PlantedHsrpKs",
     [("key_string", "PlantedHsrpKs")]),
    (" vrrp 1 authentication md5 key-string PlantedVrrpKs", [("key_string", "PlantedVrrpKs")]),
    # NTP: `ntp authentication-key number md5 key [encryption-type]` (Basic System Management
    # Command Reference): IOS prints the type AFTER the value; a type before it is read too.
    ("ntp authentication-key 1 md5 PlantedNtpKey", [("ntp_key", "PlantedNtpKey")]),
    ("ntp authentication-key 1 md5 104D000A0618 7", [("ntp_key", "104D000A0618")]),
    ("ntp authentication-key 1 md5 7 104D000A0618", [("ntp_key", "104D000A0618")]),
    ("ntp authentication-key 42 md5 PlantedNtpKey 0", [("ntp_key", "PlantedNtpKey")]),
    # A type 7 value can be digits alone (each pair is hex): the value, never a type, with
    # the type after it.
    ("ntp authentication-key 1 md5 110219001105 7", [("ntp_key", "110219001105")]),
]

#: Lines in these shapes' neighbourhood that hold no secret: masking leaves each whole.
NO_SECRET = [
    "key chain OSPF-KEYS",
    " key 1",
    # A name or prose that leads with "key" (the break-glass preview's operands): an
    # unindented `key` is a server's only with its type number.
    "key fingerprint",
    "key opens",
    "key 1 of 1 stored value(s)",
    # A traceback's source line in a log: an assignment, not a server's key.
    "    key = live_key()",
    " key 2147483647",
    "  key-string 7 <redacted:key_string>",
    " ip ospf authentication message-digest",
    " ip ospf authentication key-chain OSPF-KEYS",
    " ip ospf authentication null",
    " ip ospf authentication",
    " ip ospf cost 10",
    " standby 1 authentication md5 key-chain HSRP-KEYS",
    " vrrp 1 authentication md5 key-chain VRRP-KEYS",
    " standby version 2",
    " standby 1 ip 192.0.2.1",
    " standby 1 ipv6 2001:db8::1/64",
    " standby 1 priority 110",
    " vrrp 1 address-family ipv4",
    "ntp authenticate",
    "ntp trusted-key 1",
    "ntp server 192.0.2.10 key 1",
    "ntp server 2001:db8::10 key 1",
    " neighbor 192.0.2.7 remote-as 65001",
    " neighbor 2001:db8::7 remote-as 65001",
    " neighbor PEERS peer-group",
    "snmp-server user ops OPS v2c",
    "snmp-server group OPS v3 priv",
    "crypto isakmp policy 10",
    "crypto isakmp keepalive 10 3",
    " address ipv4 192.0.2.5",
    " address ipv6 2001:db8::5",
]


def _expected(line, planted):
    out = line
    for label, value in planted:
        assert out.count(value) == 1, (value, out)
        out = out.replace(value, _p(label))
    return out


@pytest.mark.parametrize("line,planted", FORMS, ids=[f[0].strip()[:50] for f in FORMS])
class TestEachForm:
    def test_the_value_is_masked_and_every_other_byte_kept(self, line, planted):
        assert redact.redact_positional(line) == _expected(line, planted)

    def test_redact_text_masks_it_and_the_egress_mask_keeps_its_label(self, line, planted):
        """`redact_text` masks it by position; the egress mask, which runs it first, keeps
        each carrier's label (no egress rule relabels a placeholder). The egress mask may
        over-mask by resemblance (a user named `auth` loses the `v3` after it), never less."""
        want = _expected(line, planted)
        assert redact.redact_text(line, values={}) == want
        out = redact.redact_egress(line, values={})
        for label, value in planted:
            assert value not in out.split() and _p(label) in out, out
        assert out == want or "auth sha <redacted:egress_snmp_auth>" in out, out

    def test_masking_twice_changes_nothing(self, line, planted):
        once = redact.redact_positional(line)
        assert redact.redact_positional(once) == once

    def test_the_parsers_and_the_config_check_find_the_same_values(self, line, planted):
        """`replace_positional_values` (the parsers' secret references, the config check's
        secret-position check) reaches exactly the values masking hides, with their labels."""
        found = []
        redact.replace_positional_values(
            line, lambda label, value, _prefix: (found.append((label, value)), value)[1])
        assert sorted(found) == sorted(planted)


def test_each_c745_label_has_forms_here():
    labels = {label for _line, planted in FORMS for label, _v in planted}
    assert set(C745_LABELS) <= labels, sorted(set(C745_LABELS) - labels)
    assert set(C745_LABELS) <= {label for label, _p in redact._POSITIONAL}


@pytest.mark.parametrize("line", NO_SECRET)
def test_a_line_holding_no_secret_is_left_whole(line):
    assert redact.redact_positional(line) == line
    assert redact.redact_text(line, values={}) == line


#: Each shape's keywords ending a line with no value (a search, a mention), and the line after.
MENTIONS = [
    " ip ospf authentication-key\n description uplink to r2",
    " ip ospf message-digest-key 1 md5\n description uplink to r2",
    " neighbor 192.0.2.7 password\n neighbor 192.0.2.7 remote-as 65001",
    " neighbor 2001:db8::7 password\n neighbor 2001:db8::7 remote-as 65001",
    "snmp-server user ops OPS v3 auth sha\nsnmp-server location lab",
    "snmp-server user ops OPS v3 auth sha <redacted:x> priv aes 128\nsnmp-server location lab",
    "crypto isakmp key\ncrypto isakmp policy 10",
    "tacacs server TAC1\n key\n address ipv4 192.0.2.5",
    " standby 1 authentication\n standby 1 ip 192.0.2.1",
    " standby 1 authentication text\n standby 1 ip 192.0.2.1",
    " vrrp 1 authentication text\n vrrp 1 ip 192.0.2.1",
    "ntp authentication-key 1 md5\nntp server 192.0.2.10",
]


@pytest.mark.parametrize("text", MENTIONS, ids=[m.split("\n")[0].strip()[:40] for m in MENTIONS])
def test_a_keyword_ending_its_line_takes_nothing_from_the_next(text):
    """A shape's keywords with nothing after them are a mention, and the next line's first
    word belongs to that line: no match crosses a line (`[ \\t]`, never `\\s`, between a
    shape's tokens)."""
    assert redact.redact_positional(text) == text


def test_a_key_chain_read_with_crlf_line_ends_is_left_whole():
    """A device's output over SSH ends its lines `\\r\\n`: a key chain's `key 1` is still its
    ID, not a value."""
    text = "key chain OSPF-KEYS\r\n key 1\r\n  key-string 7 <redacted:key_string>\r\n"
    assert redact.redact_positional(text) == text


@pytest.mark.parametrize("fn", [redact.redact_positional,
                                lambda t: redact.redact_text(t, values={}),
                                lambda t: redact.redact_egress(t, values={})],
                         ids=["redact_positional", "redact_text", "redact_egress"])
@pytest.mark.parametrize("line", [
    "ntp authentication-key 1 md5 PlantedNtpKey",
    "ntp authentication-key 1 md5 104D000A0618 7",
    "ntp authentication-key 1 md5 7 104D000A0618"])
def test_ntps_key_number_and_algorithm_survive_and_its_value_does_not(fn, line):
    """The trap C1845 named: a bare `authentication-key [type] <value>` rule would read NTP's
    key number as the type and mask `md5`, leaving the key in clear. Every mask keeps
    `authentication-key 1 md5` and masks the value, labelled NTP's."""
    out = fn(line)
    assert out.startswith("ntp authentication-key 1 md5 "), out
    assert "PlantedNtpKey" not in out and "104D000A0618" not in out, out
    assert _p("ntp_key") in out, out


def test_a_golden_block_is_masked_line_by_line_and_no_match_crosses_a_line():
    """Inside a configuration: a key chain's `key 1` keeps its ID while its `key-string` is
    masked, and a server's `key` is masked under either family of server address."""
    lines = [
        ("key chain OSPF-KEYS", []),
        (" key 1", []),
        ("  key-string 7 0605027D1D4F5D", [("key_string", "0605027D1D4F5D")]),
        ("interface GigabitEthernet2", []),
        (" ip address 192.0.2.1 255.255.255.252", []),
        (" ipv6 address 2001:db8::1/64", []),
        (" ip ospf message-digest-key 1 md5 7 0822455D0A16", [("ospf_key", "0822455D0A16")]),
        (" standby 1 authentication PlantedHsrpStr", [("fhrp_authentication",
                                                        "PlantedHsrpStr")]),
        ("router bgp 65001", []),
        (" neighbor 192.0.2.2 password 7 0822455D0A16544541",
         [("neighbor_password", "0822455D0A16544541")]),
        (" neighbor 2001:db8::2 password PlantedBgpPw", [("neighbor_password", "PlantedBgpPw")]),
        ("tacacs server TAC1", []),
        (" address ipv4 192.0.2.5", []),
        (" key 7 0475071A0B", [("server_key", "0475071A0B")]),
        ("radius server RAD6", []),
        (" address ipv6 2001:db8::5 auth-port 1812 acct-port 1813", []),
        (" key PlantedRadiusKey", [("server_key", "PlantedRadiusKey")]),
        ("ntp authentication-key 1 md5 104D000A0618 7", [("ntp_key", "104D000A0618")]),
        ("end", []),
    ]
    text = "\n".join(line for line, _p in lines) + "\n"
    want = "\n".join(_expected(line, planted) for line, planted in lines) + "\n"
    assert redact.redact_positional(text) == want
    assert redact.redact_text(text, values={}) == want


#: The lines the egress test planted mid-sentence before C745 (tests/test_redact_egress.py):
#: masked by position now, each labelled by its carrier, never by an egress rule.
QUOTED = [
    ("BGP: neighbor 192.0.2.7 password 7 0822455D0A16544541 refused",
     [("neighbor_password", "0822455D0A16544541")]),
    ("neighbor 2001:db8::7 password plantedClearPw9 for AS 65001",
     [("neighbor_password", "plantedClearPw9")]),
    ("ospf: ip ospf message-digest-key 1 md5 7 0605027D1D4F5D on Gi0/1",
     [("ospf_key", "0605027D1D4F5D")]),
    ("ntp authentication-key 3 md5 plantedNtpKey41 seen in the diff",
     [("ntp_key", "plantedNtpKey41")]),
    ("snmp-server user ops GRP v3 auth sha plantedAuthPass1 priv aes 128 plantedPrivPass2",
     [("snmp_user_auth", "plantedAuthPass1"), ("snmp_user_priv", "plantedPrivPass2")]),
    ("why does crypto isakmp key PlantedIkeKey address 2001:db8::9 fail",
     [("isakmp_key", "PlantedIkeKey")]),
    # A clear value of digits alone with words after it: the value, never a type (an
    # encryption type is one digit), so the word after it is not taken in its place.
    ("ip ospf authentication-key 12345678 set on Gi0/1", [("ospf_key", "12345678")]),
    ("BGP: neighbor 192.0.2.7 password 12345678 refused", [("neighbor_password", "12345678")]),
    ("neighbor 2001:db8::7 password 12345678 refused", [("neighbor_password", "12345678")]),
    ("crypto isakmp key 12345678 was set for the peer", [("isakmp_key", "12345678")]),
]


@pytest.mark.parametrize("line,planted", QUOTED, ids=[q[0][:40] for q in QUOTED])
def test_a_shape_quoted_mid_sentence_is_masked_by_position(line, planted):
    want = _expected(line, planted)
    assert redact.redact_text(line, values={}) == want
    assert redact.redact_egress(line, values={}) == want


# ── the fleet's captures: nothing ordinary is newly masked ──────────────────────────────────

#: Every captured configuration in the fixtures: the goldens (`*.cfg`) and the transcripts'
#: configuration reads.
CAPTURES = sorted(
    tracked("tests/fixtures", suffix=".cfg")
    + [p for p in tracked("tests/fixtures/transcripts")
       if fnmatch.fnmatch(os.path.basename(p), "show_*config*.txt")])

#: What a line masked by position holds, by an independent reading: one of the keywords a
#: secret position follows.
_KNOWN_SHAPE = re.compile(r"(?i)\b(community|snmp-server host|password|secret|key-string|key|"
                          r"authentication|pre-shared-key)\b|://")


def _lines(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def _without_c745(line):
    """*line* through the positional table as it stood before C745 (its entries in order,
    C745's left out)."""
    for label, pattern in redact._POSITIONAL:
        if label in C745_LABELS:
            continue
        line = pattern.sub(
            lambda m, lb=label: m.group(0) if redact._ALREADY.match(m.group(2))
            else m.group(1) + _p(lb) + m.group(3), line)
    return line


class TestTheFleetsCaptures:
    def test_the_population_is_whole(self):
        """The floor: the nine fleet goldens, the two platform captures, the two committed
        goldens and four transcripts' configuration reads, and their lines."""
        assert len(CAPTURES) >= 17, CAPTURES
        assert sum(len(_lines(p)) for p in CAPTURES) >= 3000

    def test_the_c745_rules_change_no_captured_line(self):
        """Measured: none of C745's shapes appears in the captures, so its rules change no
        line, and every captured line masks exactly as it did before them."""
        changed = [(os.path.relpath(p, ROOT), n) for p in CAPTURES
                   for n, line in enumerate(_lines(p), 1)
                   if redact.redact_positional(line) != _without_c745(line)]
        assert changed == []

    def test_a_masked_captured_line_differs_only_by_whole_values_where_a_secret_is_named(self):
        masked = 0
        for path in CAPTURES:
            for line in _lines(path):
                out = redact.redact_positional(line)
                if out == line:
                    continue
                masked += 1
                assert _KNOWN_SHAPE.search(line), line
                before, after = line.split(), out.split()
                assert len(before) == len(after), out
                assert all(a == b or b.startswith("<redacted:") for a, b in zip(before, after)), out
        assert masked >= 20, "the captures' communities and user lines are masked"

    def test_a_shape_planted_in_a_capture_is_found(self):
        """The planted case: one line added to a captured golden under its first interface,
        found by the same comparison at that line, and only there."""
        path = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r1.cfg")
        lines = _lines(path)
        at = next(i for i, line in enumerate(lines) if line.startswith("interface ")) + 1
        lines.insert(at, " ip ospf message-digest-key 1 md5 7 0605027D1D4F5D")
        changed = [n for n, line in enumerate(lines)
                   if redact.redact_positional(line) != _without_c745(line)]
        assert changed == [at]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# C2074: the shapes still in clear after C745
# ═════════════════════════════════════════════════════════════════════════════════════════════
#
# Measured before this change (2026-10-28): 31 planted lines of these shapes, one or more per
# shape, each kept its value through `redact_text`, and 21 of them through the egress mask
# too. No capture holds any of these shapes (`TestC2074AndTheFleetsCaptures` below, counts
# only), so each line is again the vendor's documented command form, from
# Cisco's IOS and IOS XE command references (named per shape), with an invented value. An
# IPv6 address stands wherever the command takes an address, so each rule is shown to read one.

#: The labels C2074 added, in `_POSITIONAL`.
C2074_LABELS = ("server_host_key", "dynamic_author_key", "pac_key", "config_key",
                "nhrp_authentication", "ikev2_pre_share_key", "ospf_virtual_link_key",
                "ospfv3_ipsec_encryption_key", "ospfv3_ipsec_authentication_key",
                "server_block_key")

#: Invented hex keys of the documented lengths (MD5 32 digits, SHA-1 40, DES 16, 3DES 48, AES
#: 128 32 and AES 256 64), each distinct so each occurs once in its line.
_MD5_A = "3544E0F3E843308F7E80548FD3604D40"
_MD5_B = "C6491036338174DF77AD212926E28E9F"
_SHA1_A = "B0C7DC5B51573BD4E2E62C004D47CBEEBD8A8A88"
_3DES_A = "E71E1E85870F80CFF45C576919A7BCD058AEE1FBAE74ED30"
_MD5_C = "2502086AB4691AB934ACF6873143D2A1"
_SHA1_B = "0B8DCEC28FEEE20EDC9F0AF052C69CF14CA4DBB8"
_DES_A = "4E25588C918368EC"
_AES128_A = "2A0C9D69DF4824179DC886DFA30660FD"
_SHA1_C = "3D5B721AE2D1A8DF848671D51DB0BC43EAFD9291"
_MD5_D = "05EB4F74F71D1258C7934AF1DB5A0048"
_AES256_A = "98B354571CD54513E97838DDE8898C31ED7F4EA195F8D42ECF14342F15ED7F38"
_SHA1_D = "E183713C7AE254F9A4C740413034F99C9E527498"
_MD5_E = "9EDB40683783DB2F96F0629858CB4598"
_MD5_F = "64B3B5B4B62C74A8AA63ECAA4BC68429"
_3DES_B = "7995304DD55D084D5A8B09640F0E50F8A2EA2CE95B5CEA32"
_MD5_G = "F3F2DE864ECEF5B72174A66136CFDC28"
_MD5_H = "4D2A35CD65DF271CFFBA170AB5560FAB"

C2074_FORMS = [
    # RADIUS: `radius-server host {hostname | ip-address} [test username user-name [idle-time
    # minutes] [ignore-auth-port] [ignore-acct-port]] [auth-port port] [acct-port port]
    # [timeout seconds] [retransmit retries] [key string] …` (Security Command Reference; the
    # key the last item, its type 0, 6 or 7 as `password encryption aes` or `service
    # password-encryption` prints it).
    ("radius-server host 192.0.2.5 key PlantedRadKey", [("server_host_key", "PlantedRadKey")]),
    ("radius-server host 192.0.2.5 auth-port 1812 acct-port 1813 key 7 0822455D0A16",
     [("server_host_key", "0822455D0A16")]),
    ("radius-server host 192.0.2.5 auth-port 1645 acct-port 1646 timeout 5 retransmit 3 key 0 "
     "PlantedRadKey", [("server_host_key", "PlantedRadKey")]),
    ("radius-server host 2001:db8::5 key 6 PlantedType6Rad",
     [("server_host_key", "PlantedType6Rad")]),
    # A test user named `key`: the last `key` on the line is the carrier, the name kept.
    ("radius-server host 192.0.2.5 test username key idle-time 5 key 7 0822455D0A1655",
     [("server_host_key", "0822455D0A1655")]),
    # A RADIUS server's PAC keyword on the host line: the host line's key, by its carrier.
    ("radius-server host 192.0.2.5 auth-port 1812 acct-port 1813 pac key 7 0822455D0A1677",
     [("server_host_key", "0822455D0A1677")]),
    # TACACS+: `tacacs-server host {host-name | host-ip-address} [key string] [nat] [port
    # [integer]] [single-connection] [timeout [integer]]` (Security Command Reference).
    ("tacacs-server host 192.0.2.6 key PlantedTacKey", [("server_host_key", "PlantedTacKey")]),
    ("tacacs-server host 192.0.2.6 port 49 timeout 5 single-connection key 7 0475071A0B",
     [("server_host_key", "0475071A0B")]),
    ("tacacs-server host 2001:db8::6 key 0 PlantedTacKey", [("server_host_key", "PlantedTacKey")]),
    # A one-character key that looks like a type: the value.
    ("tacacs-server host 192.0.2.6 key 7", [("server_host_key", "7")]),
    # An AAA group's private server: `server-private ip-address [auth-port port] [acct-port
    # port] [non-standard] [timeout seconds] [retransmit retries] [key string]` (RADIUS) and
    # `server-private {ip-address | name} [nat] [single-connection] [port port] [timeout
    # seconds] key [0 | 7] string` (TACACS+) (Security Command Reference).
    (" server-private 192.0.2.7 auth-port 1812 acct-port 1813 key 7 0822455D0A16",
     [("server_host_key", "0822455D0A16")]),
    (" server-private 2001:db8::7 key PlantedPrivKey", [("server_host_key", "PlantedPrivKey")]),
    (" server-private 192.0.2.7 single-connection port 49 timeout 5 key 0 PlantedPrivKey",
     [("server_host_key", "PlantedPrivKey")]),
    # RADIUS dynamic authorization (`aaa server radius dynamic-author`): `client {hostname |
    # ip-address} [server-key [0 | 7] string] [vrf vrf-name]` and `server-key [0 | 7] string`
    # (Security Command Reference).
    (" client 192.0.2.8 server-key PlantedDynKey", [("dynamic_author_key", "PlantedDynKey")]),
    (" client 192.0.2.8 server-key 7 0822455D0A16", [("dynamic_author_key", "0822455D0A16")]),
    (" client 2001:db8::8 vrf MGMT server-key 0 PlantedDynKey",
     [("dynamic_author_key", "PlantedDynKey")]),
    (" client 192.0.2.8 server-key PlantedDynKey vrf MGMT",
     [("dynamic_author_key", "PlantedDynKey")]),
    (" server-key PlantedDynKey", [("dynamic_author_key", "PlantedDynKey")]),
    (" server-key 7 0822455D0A16", [("dynamic_author_key", "0822455D0A16")]),
    # A `radius server` block's `pac key [encryption-type] string` (Security Command Reference).
    (" pac key PlantedPacKey", [("pac_key", "PlantedPacKey")]),
    (" pac key 7 0822455D0A16", [("pac_key", "0822455D0A16")]),
    (" pac key 6 PlantedType6Pac", [("pac_key", "PlantedType6Pac")]),
    # `key config-key password-encrypt [text]` (Security Command Reference): the master key.
    # Indented (a person's paste), it keeps its keyword: `server_key` refuses `config-key`.
    ("key config-key password-encrypt PlantedMasterKey", [("config_key", "PlantedMasterKey")]),
    (" key config-key password-encrypt PlantedMasterKey", [("config_key", "PlantedMasterKey")]),
    # NHRP: `ip nhrp authentication string` and `ipv6 nhrp authentication string` (IP
    # Addressing: NHRP Command Reference; up to eight characters).
    (" ip nhrp authentication PlntNhrp", [("nhrp_authentication", "PlntNhrp")]),
    (" ipv6 nhrp authentication PlntNhrp", [("nhrp_authentication", "PlntNhrp")]),
    # IKEv2 keyring: `pre-shared-key [local | remote] [0 | 6] {line | hex hexadecimal-string}`
    # (Security Command Reference, `pre-shared-key (IKEv2 keyring)`).
    ("  pre-shared-key PlantedIkev2Both", [("pre_shared_key", "PlantedIkev2Both")]),
    ("  pre-shared-key 6 PlantedIkev2Both", [("pre_shared_key", "PlantedIkev2Both")]),
    ("  pre-shared-key local PlantedIkev2Local", [("pre_shared_key", "PlantedIkev2Local")]),
    ("  pre-shared-key local 0 PlantedIkev2Local", [("pre_shared_key", "PlantedIkev2Local")]),
    ("  pre-shared-key remote 6 PlantedIkev2Remote", [("pre_shared_key", "PlantedIkev2Remote")]),
    ("  pre-shared-key local hex 0A1B2C3D4E5F", [("pre_shared_key", "0A1B2C3D4E5F")]),
    ("  pre-shared-key local 7", [("pre_shared_key", "7")]),
    # ISAKMP keyring: `pre-shared-key {address address [mask] | hostname hostname | ipv6
    # {ipv6-address | ipv6-prefix}} key key` (Security Command Reference, `pre-shared-key`
    # under `crypto keyring`); the `address ipv6` spelling read too.
    (" pre-shared-key address 192.0.2.1 key PlantedKeyring", [("pre_shared_key",
                                                               "PlantedKeyring")]),
    (" pre-shared-key address 192.0.2.0 255.255.255.0 key PlantedKeyringMask",
     [("pre_shared_key", "PlantedKeyringMask")]),
    (" pre-shared-key address ipv6 2001:db8::1/128 key PlantedKeyringV6",
     [("pre_shared_key", "PlantedKeyringV6")]),
    (" pre-shared-key ipv6 2001:db8::1/128 key PlantedKeyringV6",
     [("pre_shared_key", "PlantedKeyringV6")]),
    (" pre-shared-key hostname peer1.example.net key PlantedKeyringHost",
     [("pre_shared_key", "PlantedKeyringHost")]),
    # IKEv2 profile: `authentication {local | remote} pre-share [key {0 | 6} password]`
    # (Security Command Reference, `authentication (IKEv2 profile)`).
    (" authentication local pre-share key PlantedIkev2Prof",
     [("ikev2_pre_share_key", "PlantedIkev2Prof")]),
    (" authentication remote pre-share key 6 PlantedIkev2Prof",
     [("ikev2_pre_share_key", "PlantedIkev2Prof")]),
    (" authentication remote pre-share key 0 PlantedIkev2Prof",
     [("ikev2_pre_share_key", "PlantedIkev2Prof")]),
    # OSPF virtual link: `area area-id virtual-link router-id [authentication [message-digest |
    # null | key-chain name]] [hello-interval s] [retransmit-interval s] [transmit-delay s]
    # [dead-interval s] [[authentication-key [0 | 7] key] | [message-digest-key key-id md5 [0 |
    # 7] key]]` (IP Routing: OSPF Command Reference).
    (" area 1 virtual-link 192.0.2.9 authentication-key PlantedVlAk",
     [("ospf_virtual_link_key", "PlantedVlAk")]),
    (" area 1 virtual-link 192.0.2.9 authentication-key 7 0822455D0A16",
     [("ospf_virtual_link_key", "0822455D0A16")]),
    (" area 1 virtual-link 192.0.2.9 authentication-key 12345678",
     [("ospf_virtual_link_key", "12345678")]),
    (" area 1 virtual-link 192.0.2.9 authentication message-digest message-digest-key 1 md5 "
     "PlantedVlMd5", [("ospf_virtual_link_key", "PlantedVlMd5")]),
    (" area 0.0.0.1 virtual-link 192.0.2.9 hello-interval 5 dead-interval 20 "
     "message-digest-key 255 md5 7 0605027D1D4F5D", [("ospf_virtual_link_key", "0605027D1D4F5D")]),
    # OSPFv3 IPsec: `ipv6 ospf authentication {ipsec spi spi authentication-algorithm
    # [key-encryption-type] key | null}`, `ipv6 ospf encryption {ipsec spi spi esp
    # encryption-algorithm [[key-encryption-type] key] authentication-algorithm
    # [[key-encryption-type] key] | null}` (algorithms md5, sha1; des, 3des, aes-cbc {128 | 192
    # | 256}, null), the same under `ospfv3`, an area's `area area-id {authentication |
    # encryption} ipsec spi …` and a virtual link's (IPv6 Command Reference; OSPFv3 Command
    # Reference). Every key on the line is masked.
    (f" ipv6 ospf authentication ipsec spi 256 md5 {_MD5_A}",
     [("ospfv3_ipsec_authentication_key", _MD5_A)]),
    (f" ipv6 ospf authentication ipsec spi 256 md5 7 {_MD5_B}",
     [("ospfv3_ipsec_authentication_key", _MD5_B)]),
    (f" ipv6 ospf authentication ipsec spi 500 sha1 {_SHA1_A}",
     [("ospfv3_ipsec_authentication_key", _SHA1_A)]),
    (f" ipv6 ospf encryption ipsec spi 1001 esp 3des {_3DES_A} md5 {_MD5_C}",
     [("ospfv3_ipsec_encryption_key", _3DES_A), ("ospfv3_ipsec_authentication_key", _MD5_C)]),
    (f" ipv6 ospf encryption ipsec spi 1001 esp aes-cbc 128 {_AES128_A} sha1 {_SHA1_B}",
     [("ospfv3_ipsec_encryption_key", _AES128_A), ("ospfv3_ipsec_authentication_key", _SHA1_B)]),
    (f" ipv6 ospf encryption ipsec spi 1001 esp des 0 {_DES_A} md5 0 {_MD5_D}",
     [("ospfv3_ipsec_encryption_key", _DES_A), ("ospfv3_ipsec_authentication_key", _MD5_D)]),
    (f" ipv6 ospf encryption ipsec spi 1001 esp null sha1 {_SHA1_C}",
     [("ospfv3_ipsec_authentication_key", _SHA1_C)]),
    (f" ospfv3 encryption ipsec spi 1002 esp aes-cbc 256 7 {_AES256_A} sha1 7 {_SHA1_D}",
     [("ospfv3_ipsec_encryption_key", _AES256_A), ("ospfv3_ipsec_authentication_key", _SHA1_D)]),
    (f" ospfv3 authentication ipsec spi 257 md5 {_MD5_E}",
     [("ospfv3_ipsec_authentication_key", _MD5_E)]),
    (f" area 1 authentication ipsec spi 678 md5 {_MD5_F}",
     [("ospfv3_ipsec_authentication_key", _MD5_F)]),
    (f" area 1 encryption ipsec spi 679 esp 3des {_3DES_B} md5 {_MD5_G}",
     [("ospfv3_ipsec_encryption_key", _3DES_B), ("ospfv3_ipsec_authentication_key", _MD5_G)]),
    (f" area 1 virtual-link 192.0.2.9 authentication ipsec spi 940 md5 {_MD5_H}",
     [("ospfv3_ipsec_authentication_key", _MD5_H)]),
]

#: Lines of these shapes' neighbourhood holding no secret: each left whole.
C2074_NO_SECRET = [
    "radius-server host 192.0.2.5 auth-port 1812 acct-port 1813",
    "radius-server host 2001:db8::5",
    "radius-server key 7 <redacted:shared_key>",
    "tacacs-server host 192.0.2.6 single-connection",
    " server-private 192.0.2.7 auth-port 1812 acct-port 1813",
    "aaa server radius dynamic-author",
    " client 192.0.2.8 vrf MGMT",
    " client 2001:db8::8",
    # A name with `server-key` inside it is not a dynamic-authorization client's key.
    "the console-server-key page opens",
    "radius server RAD1",
    " pac key",
    "key config-key password-encrypt",
    " ip nhrp network-id 1",
    " ip nhrp nhs 192.0.2.1",
    " ipv6 nhrp nhs 2001:db8::1",
    " ip nhrp map multicast dynamic",
    "crypto ikev2 keyring KR",
    " peer P1",
    "  address 192.0.2.1",
    "  address 2001:db8::1/128",
    "  pre-shared-key local",
    " authentication local pre-share",
    " authentication remote rsa-sig",
    " keyring local KR",
    " area 1 virtual-link 192.0.2.9",
    " area 1 virtual-link 192.0.2.9 authentication message-digest",
    " area 1 virtual-link 192.0.2.9 authentication key-chain VL-KEYS",
    " area 1 virtual-link 192.0.2.9 hello-interval 5 dead-interval 20",
    " ipv6 ospf authentication null",
    " ipv6 ospf encryption null",
    " area 1 encryption null",
    " ipv6 ospf 1 area 0",
    " key 12345678",
]


@pytest.mark.parametrize("line,planted", C2074_FORMS, ids=[f[0].strip()[:50] for f in C2074_FORMS])
class TestEachC2074Form:
    def test_the_value_is_masked_and_every_other_byte_kept(self, line, planted):
        assert redact.redact_positional(line) == _expected(line, planted)

    def test_redact_text_and_the_egress_mask_give_the_same_line(self, line, planted):
        """`redact_text` masks it by position; the egress mask, which runs it first, adds
        nothing and relabels nothing (the type 7 forms the egress mask alone hid before keep
        their carrier's label now)."""
        want = _expected(line, planted)
        assert redact.redact_text(line, values={}) == want
        assert redact.redact_egress(line, values={}) == want

    def test_masking_twice_changes_nothing(self, line, planted):
        once = redact.redact_positional(line)
        assert redact.redact_positional(once) == once

    def test_the_parsers_and_the_config_check_find_the_same_values(self, line, planted):
        found = []
        redact.replace_positional_values(
            line, lambda label, value, _prefix: (found.append((label, value)), value)[1])
        assert sorted(found) == sorted(planted)


def test_each_c2074_label_has_forms_here():
    labels = {label for _line, planted in C2074_FORMS for label, _v in planted}
    labels |= {"server_block_key"}                      # its block forms are below
    assert set(C2074_LABELS) <= labels, sorted(set(C2074_LABELS) - labels)
    assert set(C2074_LABELS) <= {label for label, _p in redact._POSITIONAL}


@pytest.mark.parametrize("line", C2074_NO_SECRET)
def test_a_c2074_neighbour_holding_no_secret_is_left_whole(line):
    assert redact.redact_positional(line) == line
    assert redact.redact_text(line, values={}) == line


C2074_MENTIONS = [
    "radius-server host 192.0.2.5 key\nradius-server timeout 5",
    "tacacs-server host 2001:db8::6 key\ntacacs-server timeout 5",
    " server-private 192.0.2.7 key\n server-private 192.0.2.8",
    " client 192.0.2.8 server-key\n port 1700",
    " server-key\n port 1700",
    " pac key\n address ipv4 192.0.2.5",
    "key config-key password-encrypt\nservice password-encryption",
    " ip nhrp authentication\n ip nhrp network-id 1",
    " ipv6 nhrp authentication\n ipv6 nhrp network-id 1",
    "  pre-shared-key local\n  pre-shared-key remote",
    "  pre-shared-key local hex\n  pre-shared-key remote",
    " pre-shared-key address 192.0.2.1 key\n pre-shared-key hostname peer1",
    " authentication local pre-share key\n authentication remote pre-share",
    " area 1 virtual-link 192.0.2.9 message-digest-key 1 md5\n area 1 range 192.0.2.0 "
    "255.255.255.0",
    " area 1 virtual-link 192.0.2.9 authentication-key\n area 1 stub",
    " ipv6 ospf authentication ipsec spi 256 md5\n ipv6 ospf cost 10",
    " ipv6 ospf encryption ipsec spi 1001 esp 3des\n ipv6 ospf cost 10",
    " ipv6 ospf encryption ipsec spi 1001 esp aes-cbc 128\n ipv6 ospf cost 10",
    " ipv6 ospf encryption ipsec spi 1001 esp 3des <redacted:x> md5\n ipv6 ospf cost 10",
]


@pytest.mark.parametrize("text", C2074_MENTIONS,
                         ids=[m.split("\n")[0].strip()[:40] for m in C2074_MENTIONS])
def test_a_c2074_keyword_ending_its_line_takes_nothing_from_the_next(text):
    assert redact.redact_positional(text) == text


C2074_QUOTED = [
    ("why is radius-server host 192.0.2.5 key PlantedRadKey refused",
     [("server_host_key", "PlantedRadKey")]),
    ("radius-server host 2001:db8::5 key 12345678 is wrong", [("server_host_key", "12345678")]),
    (f"ospfv3: ipv6 ospf authentication ipsec spi 256 md5 {_MD5_A} rejected on Gi2",
     [("ospfv3_ipsec_authentication_key", _MD5_A)]),
    ("the hub's ip nhrp authentication PlntNhrp does not match",
     [("nhrp_authentication", "PlntNhrp")]),
    ("area 1 virtual-link 192.0.2.9 message-digest-key 1 md5 PlantedVlMd5 is down",
     [("ospf_virtual_link_key", "PlantedVlMd5")]),
    # A clear value of digits alone with words after it: the value, never a type (an
    # encryption type is one digit), so the word after it is not taken in its place.
    ("client 192.0.2.8 server-key 12345678 was refused", [("dynamic_author_key", "12345678")]),
    ("pac key 12345678 is set on RAD1", [("pac_key", "12345678")]),
    ("pre-shared-key local 12345678 is weak", [("pre_shared_key", "12345678")]),
    ("authentication local pre-share key 12345678 is weak",
     [("ikev2_pre_share_key", "12345678")]),
    ("area 1 virtual-link 192.0.2.9 authentication-key 12345678 is set",
     [("ospf_virtual_link_key", "12345678")]),
    ("ipv6 ospf authentication ipsec spi 256 md5 12345678901234567890123456789012 on Gi2",
     [("ospfv3_ipsec_authentication_key", "12345678901234567890123456789012")]),
    (f"ipv6 ospf encryption ipsec spi 1001 esp des 1234567890123456 md5 {_MD5_D} on Gi2",
     [("ospfv3_ipsec_encryption_key", "1234567890123456"),
      ("ospfv3_ipsec_authentication_key", _MD5_D)]),
]


@pytest.mark.parametrize("line,planted", C2074_QUOTED, ids=[q[0][:40] for q in C2074_QUOTED])
def test_a_c2074_shape_quoted_mid_sentence_is_masked_by_position(line, planted):
    want = _expected(line, planted)
    assert redact.redact_text(line, values={}) == want
    assert redact.redact_egress(line, values={}) == want


# ── the ordering hazards ────────────────────────────────────────────────────────────────────

def test_the_keyring_forms_the_first_pre_shared_key_rule_misread_keep_their_keywords():
    """The first `pre_shared_key` rule masked the token after `pre-shared-key` or `address
    <ip>`: an IPv4 mask, `ipv6` or its prefix, `hostname`, IKEv2's `local`, its type or `hex`,
    and printed the key. Each keyword stays now, and the key is masked."""
    for line, keyword in [
            (" pre-shared-key address 192.0.2.0 255.255.255.0 key PlantedK1", "255.255.255.0"),
            (" pre-shared-key address ipv6 2001:db8::1/128 key PlantedK1", "2001:db8::1/128"),
            (" pre-shared-key ipv6 2001:db8::1/128 key PlantedK1", "2001:db8::1/128"),
            (" pre-shared-key hostname peer1.example.net key PlantedK1", "peer1.example.net"),
            ("  pre-shared-key local 0 PlantedK1", "local 0"),
            ("  pre-shared-key remote 6 PlantedK1", "remote 6"),
            ("  pre-shared-key local hex PlantedK1", "local hex")]:
        out = redact.redact_positional(line)
        assert "PlantedK1" not in out and keyword in out, out
        assert out.endswith(" <redacted:pre_shared_key>"), out


def test_each_carrier_keeps_its_own_label_beside_its_neighbours():
    """IKEv2's keyring and profile beside ISAKMP's key, an interface's OSPF key beside a
    virtual link's and OSPFv3's, a server block's key beside the host line's: each value is
    masked once, labelled by its own carrier, whichever rule runs first."""
    lines = [
        ("crypto isakmp key PlantedIke1 address 192.0.2.1", [("isakmp_key", "PlantedIke1")]),
        ("crypto keyring KR1", []),
        (" pre-shared-key address 192.0.2.2 key PlantedRing1", [("pre_shared_key",
                                                                "PlantedRing1")]),
        ("crypto ikev2 keyring KR2", []),
        (" peer P1", []),
        ("  address 2001:db8::2/128", []),
        ("  pre-shared-key local 6 PlantedIkev2L", [("pre_shared_key", "PlantedIkev2L")]),
        ("crypto ikev2 profile PROF", []),
        (" authentication remote pre-share key 0 PlantedIkev2P", [("ikev2_pre_share_key",
                                                                   "PlantedIkev2P")]),
        (" keyring local KR2", []),
        ("interface Tunnel0", []),
        (" ip nhrp authentication PlntNhrp", [("nhrp_authentication", "PlntNhrp")]),
        (" ip ospf message-digest-key 1 md5 7 0605027D1D4F5D", [("ospf_key", "0605027D1D4F5D")]),
        (f" ipv6 ospf authentication ipsec spi 256 md5 {_MD5_A}",
         [("ospfv3_ipsec_authentication_key", _MD5_A)]),
        ("router ospf 1", []),
        (" area 1 virtual-link 192.0.2.9 message-digest-key 1 md5 7 0822455D0A16",
         [("ospf_virtual_link_key", "0822455D0A16")]),
        ("radius-server host 192.0.2.5 auth-port 1812 acct-port 1813 key 7 0475071A0B",
         [("server_host_key", "0475071A0B")]),
        ("radius server RAD1", []),
        (" address ipv4 192.0.2.5 auth-port 1812 acct-port 1813", []),
        (" key 7 0822455D0A1699", [("server_key", "0822455D0A1699")]),
        (" pac key 7 0822455D0A1688", [("pac_key", "0822455D0A1688")]),
        ("aaa server radius dynamic-author", []),
        (" client 192.0.2.8 server-key 7 0822455D0A1666", [("dynamic_author_key",
                                                           "0822455D0A1666")]),
        (" server-key PlantedDynAll", [("dynamic_author_key", "PlantedDynAll")]),
        ("key config-key password-encrypt PlantedMasterKey", [("config_key",
                                                               "PlantedMasterKey")]),
        ("end", []),
    ]
    text = "\n".join(line for line, _p in lines) + "\n"
    want = "\n".join(_expected(line, planted) for line, planted in lines) + "\n"
    assert redact.redact_positional(text) == want
    assert redact.redact_text(text, values={}) == want
    assert redact.redact_egress(text, values={}) == want
    assert redact.redact_positional(want) == want


# ── a server key of digits alone, told from a key chain's ID by its block ───────────────────

#: (text, the digits planted, or None where nothing is a key).
SERVER_BLOCKS = [
    ("radius server RAD1\n address ipv4 192.0.2.5 auth-port 1812 acct-port 1813\n key 12345678\n",
     "12345678"),
    ("tacacs server TAC6\n address ipv6 2001:db8::6\n timeout 5\n key 87654321\n", "87654321"),
    ("radius server RAD1\n key 7\n", "7"),
    ("crypto isakmp client configuration group VPN\n key 24681357\n dns 192.0.2.53\n",
     "24681357"),
    # A device's read over SSH ends its lines `\r\n`.
    ("radius server RAD1\r\n address ipv4 192.0.2.5\r\n key 13572468\r\n", "13572468"),
    # A key chain after a server block, the block ended by `!` or by the chain's own header:
    # the chain's `key 1` is its ID.
    ("radius server RAD1\n address ipv4 192.0.2.5\n!\nkey chain K\n key 1\n", None),
    ("radius server RAD1\n key 7 0822455D0A16\nkey chain K\n key 1\n  key-string 7 "
     "<redacted:key_string>\n", None),
    ("key chain K\n key 12345678\n  key-string 7 <redacted:key_string>\n", None),
    # The header indented (not a configuration's block) or a blank line before the key.
    (" radius server RAD1\n key 12345678\n", None),
    ("radius server RAD1\n\n key 12345678\n", None),
    # Digits followed by more on the line are not a key of digits alone.
    ("radius server RAD1\n key 12345678 extra\n", None),
]


@pytest.mark.parametrize("text,digits", SERVER_BLOCKS,
                         ids=[b[0].split("\n")[0][:30] + f"-{i}" for i, b in
                              enumerate(SERVER_BLOCKS)])
def test_a_server_blocks_key_of_digits_alone_is_masked_and_a_key_chains_id_kept(text, digits):
    out = redact.redact_positional(text)
    if digits is None:
        # No key of digits alone in a server block: the block rule takes nothing, so the
        # text masks as it did before C2074 (a typed key, or one with more after it, is
        # `server_key`'s), and a key chain's ID stays.
        assert out == _without_c2074(text) and "server_block_key" not in out, out
        assert "key chain K\n key 1\n" not in text or "key chain K\n key 1\n" in out, out
        return
    want = text.replace(f" key {digits}\n", " key <redacted:server_block_key>\n").replace(
        f" key {digits}\r\n", " key <redacted:server_block_key>\r\n")
    assert want != text
    assert out == want
    assert redact.redact_text(text, values={}) == want
    assert redact.redact_egress(text, values={}) == want
    assert redact.redact_positional(want) == want
    found = []
    redact.replace_positional_values(
        text, lambda label, value, _prefix: (found.append((label, value)), value)[1])
    assert found == [("server_block_key", digits)]


def test_a_server_key_of_digits_alone_on_its_own_line_is_left_as_a_key_chains_id():
    """The limit, stated: one line alone cannot tell a server's key of digits from a key
    chain's ID, so a caller masking line by line (the config check, the secret comparison,
    the parsers' unmodelled children) leaves it; only the block shows it."""
    assert redact.redact_positional(" key 12345678") == " key 12345678"
    lines = "radius server RAD1\n key 12345678\n".splitlines()
    assert [redact.redact_positional(line) for line in lines] == lines


# ── the fleet's captures: nothing ordinary is newly masked ──────────────────────────────────

#: The two rules C2074 changed, as they stood before it (d2680679), verbatim.
_BEFORE_C2074 = {
    "pre_shared_key": re.compile(
        r"(?i)\b(pre-shared-key\s+(?:address\s+\S+\s+)?(?:key\s+)?)" + redact._VALUE + r"()"),
    "server_key": re.compile(
        r"(?im)^((?:[ \t]+key[ \t]+(?!\d+\s*$|=)(?:[0-9][ \t]+)?"
        r"|key[ \t]+[067][ \t]+))" + redact._VALUE + r"()"),
}


def _without_c2074(text):
    """*text* through the positional table as it stood before C2074."""
    for label, pattern in redact._POSITIONAL:
        if label in C2074_LABELS:
            continue
        pattern = _BEFORE_C2074.get(label, pattern)
        text = pattern.sub(
            lambda m, lb=label: m.group(0) if redact._ALREADY.match(m.group(2))
            else m.group(1) + _p(lb) + m.group(3), text)
    return text


class TestC2074AndTheFleetsCaptures:
    def test_the_c2074_rules_change_no_captured_line_nor_file(self):
        """Measured: none of C2074's shapes appears in the captures, so its rules change no
        line and no whole file (the block rule reads across lines)."""
        assert len(CAPTURES) >= 17
        changed = [(os.path.relpath(p, ROOT), n) for p in CAPTURES
                   for n, line in enumerate(_lines(p), 1)
                   if redact.redact_positional(line) != _without_c2074(line)]
        assert changed == []
        whole = [os.path.relpath(p, ROOT) for p in CAPTURES
                 if redact.redact_positional("\n".join(_lines(p)))
                 != _without_c2074("\n".join(_lines(p)))]
        assert whole == []

    @pytest.mark.parametrize("planted", [
        "radius-server host 192.0.2.5 auth-port 1812 acct-port 1813 key 7 0822455D0A16",
        " ipv6 ospf encryption ipsec spi 1001 esp 3des " + _3DES_A + " md5 " + _MD5_C,
        "  pre-shared-key local 0 PlantedIkev2Local",
    ])
    def test_a_shape_planted_in_a_capture_is_found_at_its_line_only(self, planted):
        path = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r1.cfg")
        lines = _lines(path)
        at = next(i for i, line in enumerate(lines) if line.startswith("interface ")) + 1
        lines.insert(at, planted)
        changed = [n for n, line in enumerate(lines)
                   if redact.redact_positional(line) != _without_c2074(line)]
        assert changed == [at]

    def test_a_server_block_planted_in_a_capture_is_found_at_its_key(self):
        path = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r1.cfg")
        lines = _lines(path)
        at = next(i for i, line in enumerate(lines) if line.startswith("interface "))
        lines[at:at] = ["radius server RAD1", " address ipv4 192.0.2.5", " key 12345678", "!"]
        before = _without_c2074("\n".join(lines)).split("\n")
        after = redact.redact_positional("\n".join(lines)).split("\n")
        assert [n for n, (a, b) in enumerate(zip(after, before)) if a != b] == [at + 2]
