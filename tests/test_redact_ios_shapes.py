"""C745: the IOS credential shapes `redact._POSITIONAL` did not know, each masked by position
in every form IOS gives it, and nothing else moved.

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
