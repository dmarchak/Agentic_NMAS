"""The worked app's tests: pytest's format, run by `mercury app check` and by pytest alike."""

from dns_overrides import decide, matches
from modules.jobs import covers

BOTH = {"overrides": {"block": ["blocked.example.invalid"],
                      "allow": ["blocked.example.invalid", "allowed.example.invalid"]}}
ZONE = {"overrides": {"block": ["*.blocked-zone.example.invalid"]}}


@covers("a blocked name is blocked even when it is also allowed")
def test_a_blocked_name_is_blocked_even_when_it_is_also_allowed():
    assert decide(BOTH, "blocked.example.invalid") == "block"
    assert decide(BOTH, "allowed.example.invalid") == "allow"
    assert decide(BOTH, "other.example.invalid") == "ask"


@covers("a zone covers every name under it but not itself")
def test_a_zone_covers_every_name_under_it_but_not_itself():
    assert decide(ZONE, "a.blocked-zone.example.invalid") == "block"
    assert decide(ZONE, "blocked-zone.example.invalid") == "ask"
    assert decide(ZONE, "xblocked-zone.example.invalid") == "ask"


def test_case_and_a_trailing_dot_do_not_matter():
    assert matches("blocked.example.invalid.", "Blocked.Example.Invalid")
    assert matches("blocked.example.invalid", "blocked.example.invalid.")
    assert matches("*.zone.example.invalid", "a.zone.example.invalid.")


def test_an_exact_name_covers_only_itself():
    assert not matches("blocked.example.invalid", "a.blocked.example.invalid")
    assert not matches("blocked.example.invalid", "locked.example.invalid")


def test_no_overrides_leaves_every_name_to_the_verdict_service():
    assert decide({}, "blocked.example.invalid") == "ask"
    assert decide({"overrides": {}}, "blocked.example.invalid") == "ask"
