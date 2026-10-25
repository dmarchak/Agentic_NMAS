"""C1654: the egress mask, `redact.redact_egress` and `redact.egress_payload`, applied to what
leaves the host (Phase 8's gateway) and never to what Mercury stores.

Each shape C1654 and C745 measured passing `redact_text` in clear is a planted case here: it
is shown in clear after `redact_text` (the gap, so the case is not vacuous) and masked after
`redact_egress`. The planted values are invented for the test. Around them: what must survive
(the line's words, IPv4 and IPv6 addresses, a hostname), idempotence, a known stored value,
and the payload walk.
"""
import pytest

from modules import redact

#: (label, a line a log or an answer could carry, the planted secret in it). Each line is IOS
#: syntax quoted mid-sentence, where `redact_text`'s line-anchored positions do not reach.
PLANTED = [
    ("egress_password", "applied: enable secret 9 $9$PlantedScryptHashValue01 on r1",
     "$9$PlantedScryptHashValue01"),
    ("egress_password", "BGP: neighbor 192.0.2.7 password 7 0822455D0A16544541 refused",
     "0822455D0A16544541"),
    ("egress_password", "neighbor 2001:db8::7 password plantedClearPw9 for AS 65001",
     "plantedClearPw9"),
    ("egress_key", "ospf: ip ospf message-digest-key 1 md5 7 0605027D1D4F5D on Gi0/1",
     "0605027D1D4F5D"),
    ("egress_key", "ntp authentication-key 3 md5 plantedNtpKey41 seen in the diff",
     "plantedNtpKey41"),
    ("egress_snmp_auth",
     "snmp-server user ops GRP v3 auth sha plantedAuthPass1 priv aes 128 plantedPrivPass2",
     "plantedAuthPass1"),
    ("egress_snmp_priv",
     "snmp-server user ops GRP v3 auth sha plantedAuthPass1 priv aes 128 plantedPrivPass2",
     "plantedPrivPass2"),
    ("egress_hash", "the golden's hash $1$mERr$plantedMd5Crypt. differs from the device's",
     "$1$mERr$plantedMd5Crypt."),
    ("egress_hash", "compare $5$plantedSha256Crypt and $14$plantedType14Hash done",
     "$14$plantedType14Hash"),
    ("egress_hash", "a type 8: $8$plantedPbkdf2Salt$plantedPbkdf2Hash", "$8$plantedPbkdf2Salt$"),
]


@pytest.mark.parametrize("label,line,secret", PLANTED)
def test_each_shape_redact_text_leaves_is_masked_on_egress(label, line, secret):
    assert secret in redact.redact_text(line, values={}), "the gap must be real: " + line
    out = redact.redact_egress(line, values={})
    assert secret not in out, out
    assert f"<redacted:{label}>" in out or "<redacted:" in out, out


def test_a_real_captured_hash_line_is_masked():
    """s1's captured golden carries `username admin privilege 15 secret 5 $1$…`: masked by
    `redact_text` already (its position); quoted mid-sentence it is masked on egress too."""
    with open("tests/fixtures/configs/s1_vios_l2.cfg", encoding="utf-8") as fh:
        line = next(ln.strip() for ln in fh if "secret 5 $1$" in ln)
    token = line.split()[-1]
    quoted = f"Intent check: the device has '{line}' where intent has none"
    assert token not in redact.redact_egress(quoted, values={})


def test_the_words_addresses_and_names_survive():
    line = ("BGP: neighbor 192.0.2.7 password 7 0822455D0A16544541 refused on r1-core;"
            " neighbor 2001:db8::7 remote-as 65001")
    out = redact.redact_egress(line, values={})
    for kept in ("BGP: neighbor 192.0.2.7 password 7 ", " refused on r1-core;",
                 "neighbor 2001:db8::7 remote-as 65001"):
        assert kept in out, out


def test_masking_twice_changes_nothing():
    for _label, line, _secret in PLANTED:
        once = redact.redact_egress(line, values={})
        assert redact.redact_egress(once, values={}) == once, once


def test_a_known_stored_value_is_masked_anywhere():
    line = "the profile's password, plantedStored99, appeared in an error"
    out = redact.redact_egress(line, values={"plantedStored99": "default:password"})
    assert "plantedStored99" not in out and "<redacted:default:password>" in out, out


def test_the_payload_walk_masks_every_string_and_keeps_the_shape():
    payload = {"messages": [{"role": "user", "content": PLANTED[1][1]}],
               "meta": ("snmp-server user a b v3 auth md5 plantedAuthPass1", 3, None)}
    out = redact.egress_payload(payload, values={})
    assert "0822455D0A16544541" not in out["messages"][0]["content"]
    assert "plantedAuthPass1" not in out["meta"][0]
    assert out["meta"][1:] == (3, None) and isinstance(out["meta"], tuple)
    assert set(out) == {"messages", "meta"} and out["messages"][0]["role"] == "user"


def test_nothing_to_mask_is_returned_whole():
    for text in ("", None, "interface GigabitEthernet0/1\n description uplink to s3\n"):
        assert redact.redact_egress(text, values={}) == text


def test_redact_text_is_unchanged_for_what_mercury_stores():
    """The egress shapes are egress-only: `redact_text`, which masks logs and responses, still
    leaves a prose word after "password" alone (the egress mask may over-mask; a stored or
    logged text must not lose words)."""
    line = "the password prompt timed out"
    assert redact.redact_text(line, values={}) == line
    assert redact.redact_egress(line, values={}) != line
