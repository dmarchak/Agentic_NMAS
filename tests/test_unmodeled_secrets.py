"""C477: a secret in a line the parsers do not model never reaches intent (the operator's Now
list, 2026-10-07; measured 2026-10-05 with planted lines on r2's and s1's real configurations).

A line no handler claims is kept verbatim in `unmodeled`, and intent is committed and pushed to
GitHub. Every value in a secret position (`redact`'s own positions: a URL's user part, `ip http
client password`, a `key-string`, …) inside an unmodelled line, global or per interface,
becomes a `__secret__:<ref>` marker with its value in `secrets`, which the extraction moves into
the credential store; the templates resolve the marker on render, so the device's configuration
round-trips unchanged. A template that does not resolve it (a network's older copy) cannot send
the marker: the deploy backstop refuses it.
"""

import os

import pytest

from modules.nsot import hostvars, roundtrip
from modules.nsot.parsers import get_parser
from modules.nsot.render_artifact import MaskedContentError, assert_no_mask
from modules.redact import redact_positional

FLEET = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")

SECRETS = ("Pl4nted-Secret-One", "Pl4nted-Secret-Two", "Pl4nted-Secret-Three",
           "Pl4nted-Secret-Four")
PLANTED = ("archive\n path ftp://nmasprobe:Pl4nted-Secret-One@192.0.2.50/$h-$t\n"
           "event manager environment url https://nmasprobe:Pl4nted-Secret-Two@192.0.2.51/x\n"
           "ip http client password 0 Pl4nted-Secret-Three\n")
#: Inside an interface: an HSRP authentication key-string no interface handler models.
IFACE = " standby 1 authentication md5 key-string 7 Pl4nted-Secret-Four\n"


def _planted(name):
    with open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8") as fh:
        text = fh.read()
    head, _sep, _tail = text.rpartition("\nend")
    text = head + "\n" + PLANTED + "end\n"
    return text.replace("interface Loopback0\n", "interface Loopback0\n" + IFACE, 1)


DEVICES = (("r2", "cisco_iosxe"), ("s1", "cisco_ios"))


@pytest.fixture(params=DEVICES, ids=[d[0] for d in DEVICES])
def device(request):
    name, platform = request.param
    config = _planted(name)
    assert all(s in config for s in SECRETS), "the plant landed"
    return {"name": name, "platform": platform, "config": config,
            "parsed": get_parser(platform).parse(config)}


class TestNoSecretReachesIntent:
    def test_the_committed_intent_holds_no_planted_secret(self, device):
        text = hostvars.to_yaml(device["parsed"])
        for secret in SECRETS:
            assert secret not in text, f"{secret} reached {device['name']}'s intent"
        assert text.count("__secret__:unmodeled_") >= 4

    def test_each_value_is_kept_for_the_credential_store(self, device):
        refs = {k: v for k, v in device["parsed"]["secrets"].items()
                if k.startswith("unmodeled_")}
        # A URL's user part is one position (`user:secret`), so its stored value holds both.
        assert len(refs) == 4
        for secret in SECRETS:
            assert sum(secret in v for v in refs.values()) == 1, secret
        labels = {k.rsplit("_", 1)[0] for k in refs}
        assert labels == {"unmodeled_url_userinfo", "unmodeled_http_client_password",
                          "unmodeled_key_string"}

    def test_a_reextraction_keeps_each_reference_s_name(self, device):
        again = get_parser(device["platform"]).parse(device["config"])
        assert sorted(again["secrets"]) == sorted(device["parsed"]["secrets"])

    def test_the_device_s_configuration_round_trips_unchanged(self, device):
        report = roundtrip.validate_device(device["config"], device["platform"])
        assert not report.get("error"), report.get("error")
        assert report["details"]["missing"] == [], report["details"]["missing"][:5]
        assert report["details"]["extra"] == [], report["details"]["extra"][:5]
        rendered = roundtrip.render(device["parsed"], device["platform"])
        assert "ip http client password 0 Pl4nted-Secret-Three" in rendered
        assert "__secret__:" not in rendered


class TestTheBackstopAndTheMask:
    def test_an_unresolved_marker_never_reaches_a_device(self):
        with pytest.raises(MaskedContentError):
            assert_no_mask("event manager environment url https://__secret__:unmodeled_x@h/\n")

    def test_the_http_client_password_is_masked_on_the_way_out(self):
        out = redact_positional("ip http client password 0 Pl4nted-Secret-Three")
        assert "Pl4nted-Secret-Three" not in out and out.startswith("ip http client password 0 ")


# ── C2109: a reference's name never depends on its value ────────────────────────────────────

#: Header lines holding a secret, each a line no parser models, IPv4 and IPv6 beside each other
#: (the shapes `tests/test_redact_ios_shapes.py` holds, from Cisco's Security Command
#: Reference): each line's `{v}` is where its value goes. The last is C2098's key-wrap host
#: line, whose server key's prefix holds the two key-wrap keys before it.
HEADER_LINES = (
    "radius-server host 192.0.2.5 key {v}",
    "radius-server host 2001:db8::5 key 6 {v}",
    "ip http client password 0 {v}",
    "crypto isakmp key 6 {v} address ipv6 2001:db8::1/128",
    "crypto isakmp key 6 {v} address 192.0.2.7",
    "radius-server host 192.0.2.9 auth-port 1812 acct-port 1813 key-wrap encryption-key "
    "{v}A message-auth-code-key {v}B format ascii key {v}C",
)


def _refs_of(config: str, platform: str) -> list:
    parsed = get_parser(platform).parse(config)
    return sorted(k for k in parsed["secrets"] if k.startswith("unmodeled_"))


def _legacy_name(label: str, context: str, prefix: str) -> str:
    """A reference's name as the parsers made it before C2109, computed here by its own path
    (the raw context and prefix hashed): an intent committed then holds such a name."""
    import hashlib
    digest = hashlib.sha256(f"{context}\n{prefix}".encode()).hexdigest()[:10]
    return f"unmodeled_{label}_{digest}"


class TestAReferenceNeverHoldsItsValue:
    @pytest.mark.parametrize("line", HEADER_LINES)
    @pytest.mark.parametrize("name,platform", DEVICES)
    def test_two_lines_differing_only_in_their_secret_share_each_reference(
            self, line, name, platform):
        with open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8") as fh:
            head, _sep, _tail = fh.read().rpartition("\nend")
        one = head + "\n" + line.format(v="Pl4ntedValueOne") + "\nend\n"
        two = head + "\n" + line.format(v="An0therValueTwo") + "\nend\n"
        first, second = _refs_of(one, platform), _refs_of(two, platform)
        assert first, f"{line!r} made no reference on {name}"
        assert first == second, f"a new value renamed {line!r}'s reference on {name}"

    @pytest.mark.parametrize("platform", ["cisco_ios", "cisco_iosxe"])
    def test_a_value_like_a_word_of_its_prefix_never_renames_the_reference(self, platform):
        """A key-wrap key stands in the server key's prefix; the prefix is masked by that
        key as a whole token, so a key spelled like part of another word there (`auth` or
        `port` in `auth-port`) masks only itself, and the name is the same as for any other
        key. (A key spelled as a whole word of its prefix, `1812`, masks that word too: its
        name then differs, the one limit, and no value is in it either way.)"""
        line = ("radius-server host 192.0.2.9 auth-port 1812 acct-port 1813 key-wrap "
                "encryption-key {v} message-auth-code-key Pl4ntedMacKey12345 format ascii "
                "key Pl4nted Server Key")
        names = [_refs_of(line.format(v=v) + "\nend\n", platform)
                 for v in ("Pl4ntedEncKey123", "auth", "port")]
        assert names[0] and names[0] == names[1] == names[2], names

    @pytest.mark.parametrize("name,platform", DEVICES)
    def test_two_values_of_one_kind_in_one_context_keep_two_references(self, name, platform):
        """Where the two stand tells them apart (the prefix, masked), never their values."""
        with open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8") as fh:
            config = fh.read().replace(
                "interface Loopback0\n", "interface Loopback0\n" + IFACE
                + " standby 2 authentication md5 key-string Pl4ntedClearKey\n", 1)
        parsed = get_parser(platform).parse(config)
        refs = {k: v for k, v in parsed["secrets"].items() if k.startswith("unmodeled_key_string")}
        assert sorted(refs.values()) == ["Pl4nted-Secret-Four", "Pl4ntedClearKey"], refs

    @pytest.mark.parametrize("line", HEADER_LINES)
    def test_no_name_is_the_digest_of_the_line_holding_the_value(self, line):
        """The defect itself: before C2109 a header line's reference hashed the raw line."""
        text = line.format(v="Pl4ntedValueOne")
        parsed = get_parser("cisco_ios").parse(text + "\nend\n")
        legacy = set()
        from modules.redact import replace_positional_values
        replace_positional_values(text, lambda label, value, prefix: legacy.add(
            _legacy_name(label, text, prefix)) or value)
        names = {k for k in parsed["secrets"] if k.startswith("unmodeled_")}
        assert names and not names & legacy, (names, legacy)

    def test_a_rotated_key_keeps_every_reference_in_the_planted_configuration(self, device):
        rotated = device["config"]
        for i, secret in enumerate(SECRETS):
            rotated = rotated.replace(secret, f"R0tated-Value-{i}")
        again = get_parser(device["platform"]).parse(rotated)
        assert sorted(again["secrets"]) == sorted(device["parsed"]["secrets"])
        assert hostvars.to_yaml(again) == hostvars.to_yaml(device["parsed"])

    def test_a_line_with_no_value_in_its_context_keeps_the_name_it_had(self, device):
        """Expand (CLAUDE.md, "Stored data changes expand, then contract"): a block's child
        and an interface's line hashed no value before C2109, so their names, in intent
        committed then, are made again unchanged."""
        child = " path ftp://nmasprobe:Pl4nted-Secret-One@192.0.2.50/$h-$t"
        iface = IFACE.rstrip("\n")
        want = {
            _legacy_name("url_userinfo", "archive", "ftp://"),
            _legacy_name("key_string", "interface Loopback0",
                         "key-string 7 "),
        }
        assert child in device["config"] and iface in device["config"]
        assert want <= set(device["parsed"]["secrets"]), sorted(device["parsed"]["secrets"])

    def test_an_intent_naming_an_old_reference_still_renders_its_value(self, device):
        """An intent committed before C2109 names a header line's reference by the old digest;
        the credential store holds its value under that name, so it renders as before."""
        text = "ip http client password 0 Pl4nted-Secret-Three"
        old = _legacy_name("http_client_password", text, "ip http client password 0 ")
        parsed = dict(device["parsed"])
        new = [k for k in parsed["secrets"] if k.startswith("unmodeled_http_client_password_")]
        assert len(new) == 1 and new[0] != old
        parsed["secrets"] = {**{k: v for k, v in parsed["secrets"].items() if k != new[0]},
                             old: "Pl4nted-Secret-Three"}
        parsed["unmodeled"] = [
            {**e, "line": e["line"].replace(new[0], old)} for e in parsed["unmodeled"]]
        rendered = roundtrip.render(parsed, device["platform"])
        assert text in rendered.splitlines() and "__secret__:" not in rendered

    def test_an_acknowledgement_naming_an_old_reference_still_matches(self, device):
        from modules.nsot.render_artifact import acknowledgement_gap, unmodeled_lines
        text = "ip http client password 0 Pl4nted-Secret-Three"
        old = _legacy_name("http_client_password", text, "ip http client password 0 ")
        lines = unmodeled_lines(device["parsed"])
        acked = [l.replace(l.split("__secret__:")[1], old)
                 if l.startswith("ip http client password") else l for l in lines]
        assert acked != lines, "the acknowledgement names the old reference"
        gap = acknowledgement_gap({**device["parsed"], "unmodeled_ack": {"lines": acked}})
        assert gap["complete"] and not gap["unacknowledged"] and not gap["stale"], gap
        # A line the acknowledgement does not name stays unacknowledged.
        gap = acknowledgement_gap({**device["parsed"], "unmodeled_ack": {"lines": acked[1:]}})
        assert not gap["complete"] and len(gap["unacknowledged"]) == 1, gap
        # The Intent tab's list reads it as the gate does (`intent_edit.unmodelled`).
        from modules.nsot import intent_edit
        rows = intent_edit.unmodelled({**device["parsed"], "unmodeled_ack": {"lines": acked}})
        assert rows and all(r["acknowledged"] for r in rows), rows
