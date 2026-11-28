"""The lines an image prints when nothing sets them (Restore or keep's prerequisite,
docs/RESTORE_OR_KEEP_DESIGN.md item 1; `platform_defaults.PRINTED`; C4300, C1538).

A C8000v booted from a startup file prints nine lines nothing set (measured 2026-11-28 on three
routers' goldens): its licence level, `spanning-tree extend system-id`, four `mgcp behavior`
lines and `mgcp profile default`, and `no mop enabled` and `no mop sysid` under each interface.
Intent-Match (`roundtrip.compare`) read each as a departure, so a first boot never read at
intent until a person copied them into intent by hand. They are left out of the DEVICE's side
only, where intent lacks the line; a changed value still differs, a line intent declares is
compared as before, and the deploy's program is untouched (a printed default never joins
`HIDDEN`, whose target lines a deploy never sends).
"""
from modules.nsot import platform_defaults, roundtrip

BASE = ("hostname edge1\ninterface GigabitEthernet1\n ip address 192.0.2.1 255.255.255.0\n"
        "{iface}end\n")
DEFAULTS_TOP = ("license boot level network-premier addon dna-premier\n"
                "spanning-tree extend system-id\n"
                "mgcp behavior rsip-range tgcp-only\nmgcp behavior comedia-role none\n"
                "mgcp behavior comedia-check-media-src disable\n"
                "mgcp behavior comedia-sdp-force disable\nmgcp profile default\n")
DEFAULTS_IFACE = " no mop enabled\n no mop sysid\n"


def _device(top=DEFAULTS_TOP, iface=DEFAULTS_IFACE):
    return BASE.format(iface=iface).replace("interface GigabitEthernet1\n",
                                            top + "interface GigabitEthernet1\n")


def _missing(report):
    return sorted(m["line"] for m in report["details"]["missing"])


def _extra(report):
    return sorted(m["line"] for m in report["details"]["extra"])


def test_the_premise_every_line_is_a_rule_and_nothing_else_is():
    assert len(platform_defaults.PRINTED) == 9
    assert platform_defaults.printed("", "spanning-tree extend system-id")
    assert platform_defaults.printed("interface GigabitEthernet3", "no mop sysid")
    assert not platform_defaults.printed("", "no mop enabled"), "an interface's line only"
    assert not platform_defaults.printed("interface Gi1 > service-policy x", "no mop enabled")
    assert not platform_defaults.printed("", "mop enabled")


def test_a_first_boot_with_intent_lacking_them_reads_at_intent():
    intent = BASE.format(iface="")
    before = _missing(roundtrip.compare(_device(), intent))
    assert before == [], before
    assert roundtrip.compare(_device(), intent)["round_trip_fidelity"] == 100.0


def test_a_changed_value_still_differs():
    intent = BASE.format(iface="")
    changed = _device(top=DEFAULTS_TOP.replace("network-premier addon dna-premier",
                                               "network-advantage"),
                      iface=" mop enabled\n no mop sysid\n")
    assert _missing(roundtrip.compare(changed, intent)) == [
        "license boot level network-advantage", "mop enabled"]


def test_a_line_intent_declares_is_compared_as_before():
    """Intent stating a default the device does not print is still intent ahead of it (the
    device prints `mop enabled`): the table never hides intent's own line."""
    intent = BASE.format(iface=" no mop enabled\n")
    device = _device(iface=" mop enabled\n no mop sysid\n")
    report = roundtrip.compare(device, intent)
    assert "mop enabled" in _missing(report) and "no mop enabled" in _extra(report), report
    both = roundtrip.compare(_device(), intent)
    assert _missing(both) == [] and _extra(both) == [], "held on both sides: equal"


def test_the_deploy_still_sends_intents_default_to_a_device_that_changed_it():
    """A printed default is not `HIDDEN`: intent's `no mop enabled` reaches a device that prints
    `mop enabled`, as before."""
    from modules.nsot.deploy import merge_commands
    intent = BASE.format(iface=" no mop enabled\n")
    device = _device(iface=" mop enabled\n no mop sysid\n")
    sent = [c.strip() for c in merge_commands(intent, device)]
    assert "no mop enabled" in sent, sent
    assert not platform_defaults.hidden(["interface GigabitEthernet1"], " no mop enabled")
