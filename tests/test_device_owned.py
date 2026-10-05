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


#: AutoInstall's client-id as tw-ztp-a holds it (2026-10-05): the SHORT name of its interface.
AUTOINSTALL = " ip dhcp client client-id ascii cisco-aabb.cc00.0260-Gi2"


def _with_autoinstall(line=AUTOINSTALL, interface="interface GigabitEthernet2\n"):
    """r2's real capture, one line added inside the interface AutoInstall leased on."""
    return _text("r2").replace(interface, interface + line.rstrip("\n") + "\n", 1)


class TestAutoInstallsClientId:
    """C485 (the operator, 2026-10-05): AutoInstall writes `ip dhcp client client-id ascii
    cisco-<dotted MAC>-<the interface's SHORT name>` inside the interface it took its lease
    on. It is the device's own, like the licence UDI: never intent, never sent, never
    residue, never blocking. Only that exact form, matched against the interface as IOS
    writes it; a client-id a person chose stays configuration."""

    def test_it_is_in_no_parse_and_the_round_trip_is_whole(self):
        from modules.nsot.parsers import get_parser
        from modules.nsot.roundtrip import validate_device
        text = _with_autoinstall()
        hv = get_parser("cisco_iosxe").parse(text)
        held = [l for i in hv.get("interfaces") or [] for l in i.get("unmodeled") or []]
        assert not [l for l in held if "client-id" in l], held
        r = validate_device(text, "cisco_iosxe")
        assert r.get("ok") and r.get("round_trip_fidelity") == 100.0, r.get("details")

    def test_device_owned_names_it_with_its_interface(self):
        from modules.nsot import normalize
        assert ("interface GigabitEthernet2: ip dhcp client client-id ascii "
                "cisco-aabb.cc00.0260-Gi2") in normalize.device_owned(_with_autoinstall())

    def test_it_is_never_sent_and_never_residue(self):
        from modules.nsot.deploy import merge_commands, merge_diff
        from modules.nsot.parsers import get_parser
        device = _with_autoinstall()
        rendered = _render(get_parser("cisco_iosxe").parse(_text("r2")), "cisco_iosxe")
        assert not [l for l in merge_commands(rendered, device) if "client-id" in l]
        assert not [r for r in merge_diff(rendered, device)["residue"] if "client-id" in str(r)]

    @pytest.mark.parametrize("line,interface", [
        # The long name, as the seed wrongly wrote it: not what the device writes.
        (" ip dhcp client client-id ascii cisco-aabb.cc00.0260-GigabitEthernet2",
         "interface GigabitEthernet2\n"),
        # Another interface's name inside this one: not AutoInstall's.
        (" ip dhcp client client-id ascii cisco-aabb.cc00.0260-Gi3", "interface GigabitEthernet2\n"),
        # A client-id a person chose.
        (" ip dhcp client client-id ascii site-12-uplink", "interface GigabitEthernet2\n"),
        (" ip dhcp client client-id GigabitEthernet2", "interface GigabitEthernet2\n"),
    ])
    def test_any_other_client_id_stays_configuration(self, line, interface):
        from modules.nsot import normalize
        text = _with_autoinstall(line, interface)
        assert not [h for h in normalize.device_owned(text) if "client-id" in h]
        assert line.rstrip() in normalize.strip_for_roundtrip(text)


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
