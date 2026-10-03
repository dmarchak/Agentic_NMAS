"""C397: what a device generates for itself is the device's own, never intent and never sent.

The parser modelled `crypto pki trustpoint TP-self-signed-<chassis>` into intent
(`pki_trustpoints`), while only the drift, round-trip and golden-diff comparisons stripped it.
Measured on r2's real config with the trustpoint renumbered, as a boot regenerates it: the
merge program added the old trustpoint and an `rsakeypair` the device no longer holds. The
device's own blocks (that trustpoint, every certificate body, the licence UDI) are now one
declared shape (`normalize._opens_device_owned`), removed by `strip_for_roundtrip`, which the
parser, every program and residue (`deploy._section_chains`) and every round trip go through;
`normalize.device_owned` names them for a screen (seed's card, board 8).

On the nine real fleet configs (`tests/fixtures/configs/fleet/`):
- no parse holds the self-signed trustpoint; a CA-signed one (SLA-TrustPoint) stays intent;
- the round trip is unchanged (fully reproduced, nothing unmodelled);
- against a device whose trustpoint regenerated, the program sends none of it, from today's
  intent AND from intent committed before the fix that still holds it;
- `device_owned` names the trustpoint, the certificate bodies and the UDI, and never a banner
  (operator text, excluded for another reason) or a CA-signed trustpoint.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
NAMES = sorted(f[:-4] for f in os.listdir(FLEET) if f.endswith(".cfg"))
#: The C8000v configs: each carries its own self-signed trustpoint.
SELF_SIGNED = re.compile(r"^crypto pki trustpoint (TP-self-signed-\d+)$", re.M)


def _text(name):
    return open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8").read()


def _platform(text):
    return "cisco_iosxe" if SELF_SIGNED.search(text) else "cisco_ios"


def _render(hv, platform):
    from modules.nsot.roundtrip import render
    return render(hv, platform, secret_lookup=lambda n: (hv.get("secrets") or {}).get(n, ""))


def _regenerated(text):
    """The device after a boot made it a new trustpoint (a new chassis-derived name)."""
    old = SELF_SIGNED.search(text).group(1)
    return text.replace(old, "TP-self-signed-1111111111")


def _pki(program):
    return [l for l in program if "pki" in l or "rsakeypair" in l or "self-signed" in l]


def test_the_population():
    with_tp = [n for n in NAMES if SELF_SIGNED.search(_text(n))]
    assert len(NAMES) == 9 and len(with_tp) == 5, (NAMES, with_tp)


@pytest.mark.parametrize("name", NAMES)
def test_no_parse_holds_it_and_the_round_trip_is_unchanged(name):
    from modules.nsot.parsers import get_parser
    from modules.nsot.roundtrip import validate_device
    text = _text(name)
    hv = get_parser(_platform(text)).parse(text)
    names = [t.get("name", "") for t in hv.get("pki_trustpoints") or []]
    assert not [n for n in names if n.startswith("TP-self-signed-")], names
    if SELF_SIGNED.search(text):
        assert names == ["SLA-TrustPoint"], "a CA trustpoint is configuration someone chose"
    r = validate_device(text, _platform(text))
    assert r.get("ok") and r.get("round_trip_fidelity") == 100.0, r.get("details")
    assert not hv.get("unmodeled")


@pytest.mark.parametrize("name", [n for n in NAMES if SELF_SIGNED.search(_text(n))])
def test_a_regenerated_trustpoint_is_never_sent(name):
    from modules.nsot.deploy import merge_commands, merge_diff
    from modules.nsot.parsers import get_parser
    text = _text(name)
    hv = get_parser("cisco_iosxe").parse(text)
    device = _regenerated(text)
    assert _pki(merge_commands(_render(hv, "cisco_iosxe"), device)) == []
    # Intent committed before the fix still holds the trustpoint, and renders it.
    old_tp = SELF_SIGNED.search(text).group(1)
    old = dict(hv, pki_trustpoints=[{"name": old_tp, "settings": [
        "enrollment selfsigned", "revocation-check none", f"rsakeypair {old_tp}"]}]
        + list(hv.get("pki_trustpoints") or []))
    rendered = _render(old, "cisco_iosxe")
    assert f"crypto pki trustpoint {old_tp}" in rendered
    assert _pki(merge_commands(rendered, device)) == []
    # Nor is the device's new one residue to remove.
    assert not [r for r in merge_diff(rendered, device)["residue"] if "self-signed" in str(r)]


def test_device_owned_names_the_devices_own_blocks_and_nothing_else():
    from modules.nsot import normalize
    text = _text("r2").replace("\nend", "\nbanner motd ^C\nAuthorised use only\n^C\nend", 1)
    owned = normalize.device_owned(text)
    assert owned == ["crypto pki trustpoint TP-self-signed-2968666059",
                     "crypto pki certificate chain TP-self-signed-2968666059",
                     "crypto pki certificate chain SLA-TrustPoint",
                     "license udi pid C8000V sn 9XXXXXXXXXX"]
    assert any(h.startswith("banner motd") for h in normalize.excluded_unrenderable(text)), \
        "a banner is excluded for another reason, and is not the device's own"
    assert normalize.device_owned("crypto pki trustpoint MY-CA\n enrollment terminal\n") == []
    assert normalize.device_owned(" crypto pki trustpoint TP-self-signed-1\n") == [], \
        "only a top-level block opens one"
