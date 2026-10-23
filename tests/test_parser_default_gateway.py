"""``ip default-gateway`` is modelled as ``default_gateway`` and renders back as itself (C1592:
out-of-band ZTP's static switch reaches the manager by its default gateway alone, and its
committed intent carries the key; `parsers.base.BaseParser._h_default_gateway`, the
``routes_and_acls`` macro in ``modules/nsot/templates/_common.j2``).

No real capture in tests/fixtures holds the line (searched: none does), so the capture is a
MINIMAL EDIT of a real one: tests/fixtures/configs/fleet/s1.cfg, a vIOS-L2 switch's running
config, with ONE line inserted where IOS prints it, immediately before ``ip forward-protocol
nd``. The address is a documentation one (RFC 5737). Everything else is the capture as read.

IOS's ``ip default-gateway`` is IPv4 only; an IPv6 default is ``ipv6 route ::/0 <next hop>``, a
static route, and stays one (the IPv6 case beside the IPv4 one)."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "s1.cfg")
PLATFORM = "cisco_ios"
GATEWAY = "192.0.2.13"
LINE = f"ip default-gateway {GATEWAY}"
ANCHOR = "ip forward-protocol nd"


def _capture() -> str:
    with open(CAPTURE, encoding="utf-8") as fh:
        return fh.read()


def _with(*lines: str) -> str:
    """The capture with *lines* inserted before the anchor, where IOS prints the gateway."""
    text = _capture()
    assert text.count(f"\n{ANCHOR}\n") == 1, "floor: the anchor is in the capture once"
    return text.replace(f"\n{ANCHOR}\n", "\n" + "".join(f"{ln}\n" for ln in lines)
                        + f"{ANCHOR}\n")


def _parse(text: str) -> dict:
    from modules.nsot.parsers import get_parser
    return get_parser(PLATFORM).parse(text)


def _render(hv: dict) -> list:
    from modules.nsot import roundtrip
    return roundtrip.render(hv, PLATFORM).splitlines()


def _unmodeled_text(hv: dict) -> str:
    return "\n".join(str(e) for e in hv.get("unmodeled") or [])


def test_the_capture_holds_no_gateway_and_the_edit_adds_exactly_one():
    """The floor every test below stands on: the real capture has no ``ip default-gateway``,
    and the minimal edit adds exactly the one line."""
    assert "ip default-gateway" not in _capture()
    edited = _with(LINE)
    assert edited.count("ip default-gateway") == 1
    assert len(edited.splitlines()) == len(_capture().splitlines()) + 1


def test_the_line_is_parsed_as_default_gateway_and_nothing_else():
    """The line becomes ``default_gateway`` (its address), not an unmodeled line and not a
    static route; every other key is what the unedited capture gives."""
    before, after = _parse(_capture()), _parse(_with(LINE))
    assert after.get("default_gateway") == GATEWAY
    assert "default-gateway" not in _unmodeled_text(after)
    assert after["static_routes"] == before["static_routes"]
    assert {k: v for k, v in after.items() if k != "default_gateway"} == before


def test_it_round_trips_through_the_template():
    """Parsed and rendered, the edited capture gives the line back exactly once, and the
    round-trip comparison finds it matched: nothing missing or extra that the unedited capture's
    comparison does not also have."""
    from modules.nsot import roundtrip
    rendered = _render(_parse(_with(LINE)))
    assert rendered.count(LINE) == 1, [ln for ln in rendered if "gateway" in ln]
    base = roundtrip.validate_device(_capture(), PLATFORM)
    got = roundtrip.validate_device(_with(LINE), PLATFORM)
    assert got["details"]["missing"] == base["details"]["missing"]
    assert got["details"]["extra"] == base["details"]["extra"]
    assert got["matched"] == base["matched"] + 1


def test_absent_stays_absent():
    """A config without the line gives intent without the key, and a render without the line:
    no intent written before the key existed gains one."""
    hv = _parse(_capture())
    assert "default_gateway" not in hv
    assert not [ln for ln in _render(hv) if ln.startswith("ip default-gateway")]


def test_intent_carrying_the_key_renders_the_line():
    """Hand-written intent (the out-of-band onboarding's commit writes the key, C1592): adding
    ``default_gateway`` to the capture's intent renders exactly that line, and removing it
    removes the line."""
    hv = _parse(_capture())
    assert _render(dict(hv, default_gateway=GATEWAY)).count(LINE) == 1
    assert LINE not in _render(dict(hv, default_gateway=""))


def test_an_ipv6_default_is_a_static_route_never_the_gateway():
    """IPv6 beside IPv4: IOS has no IPv6 ``ip default-gateway``; ``ipv6 route ::/0`` stays a
    static route of family ipv6, and renders back as itself."""
    v6 = "ipv6 route ::/0 2001:DB8::D"
    hv = _parse(_with(LINE, v6))
    assert hv.get("default_gateway") == GATEWAY
    assert {"family": "ipv6", "spec": "::/0 2001:DB8::D"} in hv["static_routes"]
    rendered = _render(hv)
    assert rendered.count(v6) == 1 and rendered.count(LINE) == 1


def test_a_second_gateway_line_stays_unmodeled():
    """IOS keeps one default gateway; a config showing two keeps the first as the key and
    carries the second verbatim, so neither is lost."""
    second = "ip default-gateway 192.0.2.14"
    hv = _parse(_with(LINE, second))
    assert hv.get("default_gateway") == GATEWAY
    assert second in _unmodeled_text(hv)
    rendered = _render(hv)
    assert rendered.count(LINE) == 1 and rendered.count(second) == 1
