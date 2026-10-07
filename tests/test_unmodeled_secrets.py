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
