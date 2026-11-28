"""The lines an image prints when nothing sets them (Restore or keep's prerequisite,
docs/RESTORE_OR_KEEP_DESIGN.md item 1; `platform_defaults.PRINTED`; C4300, C1538).

A C8000v booted from a startup file prints eight lines nothing set (measured 2026-11-28 on three
routers' goldens): `spanning-tree extend system-id`, four `mgcp behavior` lines and `mgcp
profile default`, and `no mop enabled` and `no mop sysid` under each interface. Intent-Match
(`roundtrip.compare`) read each as a departure, so a first boot never read at intent until a
person copied them into intent by hand. They are left out of the DEVICE's side only, for the
IOS-XE dialect only, where intent lacks the line; a changed value still differs, a line intent
declares is compared as before, and the deploy's program is untouched (a printed default never
joins `HIDDEN`, whose target lines a deploy never sends). The licence level is configuration
(vrnetlab's install step sets it), never a printed default.
"""
from modules.nsot import platform_defaults, roundtrip

XE = "cisco_iosxe"
BASE = ("hostname edge1\ninterface GigabitEthernet1\n ip address 192.0.2.1 255.255.255.0\n"
        "{iface}end\n")
DEFAULTS_TOP = ("spanning-tree extend system-id\n"
                "mgcp behavior rsip-range tgcp-only\nmgcp behavior comedia-role none\n"
                "mgcp behavior comedia-check-media-src disable\n"
                "mgcp behavior comedia-sdp-force disable\nmgcp profile default\n")
DEFAULTS_IFACE = " no mop enabled\n no mop sysid\n"
LICENCE = "license boot level network-premier addon dna-premier\n"


def _device(top=DEFAULTS_TOP, iface=DEFAULTS_IFACE):
    return BASE.format(iface=iface).replace("interface GigabitEthernet1\n",
                                            top + "interface GigabitEthernet1\n")


def _missing(report):
    return sorted(m["line"] for m in report["details"]["missing"])


def _extra(report):
    return sorted(m["line"] for m in report["details"]["extra"])


def test_the_premise_every_line_is_a_rule_and_nothing_else_is():
    """The eight measured lines, each for IOS-XE only, exactly where it is printed."""
    assert len(platform_defaults.PRINTED) == 8
    assert platform_defaults.printed("", "spanning-tree extend system-id", XE)
    assert platform_defaults.printed("interface GigabitEthernet3", "no mop sysid", XE)
    assert not platform_defaults.printed("", "no mop enabled", XE), "an interface's line only"
    assert not platform_defaults.printed("interface Gi1 > service-policy x", "no mop enabled", XE)
    assert not platform_defaults.printed("", "mop enabled", XE)
    assert not platform_defaults.printed("", "spanning-tree extend system-id", "cisco_ios")
    assert not platform_defaults.printed("", "spanning-tree extend system-id"), "no platform"


def test_a_first_boot_with_intent_lacking_them_reads_at_intent():
    """An IOS-XE device printing the eight lines, intent lacking them: at intent."""
    intent = BASE.format(iface="")
    report = roundtrip.compare(_device(), intent, platform=XE)
    assert _missing(report) == [], report
    assert report["round_trip_fidelity"] == 100.0


def test_the_licence_level_is_configuration_and_still_differs():
    """The review of the first slice: vrnetlab's install step sets `license boot level`, so it
    is no printed default; a device holding it with intent lacking it departs."""
    intent = BASE.format(iface="")
    assert _missing(roundtrip.compare(_device(top=LICENCE + DEFAULTS_TOP), intent,
                                      platform=XE)) == [LICENCE.strip()]


def test_an_ios_device_holding_the_same_lines_still_departs():
    """Measured on IOS-XE only: an IOS device whose person set `spanning-tree extend system-id`
    and `no mop enabled` departs from intent lacking them."""
    intent = BASE.format(iface="")
    assert _missing(roundtrip.compare(_device(), intent, platform="cisco_ios")) == sorted(
        DEFAULTS_TOP.strip().splitlines() + DEFAULTS_IFACE.strip().replace(" no", "no")
        .splitlines())


def test_a_comparison_naming_no_platform_compares_every_line():
    """A template-fidelity question (approval, the template report, restore's gap) passes no
    platform: does the template reproduce the capture, every line of it."""
    intent = BASE.format(iface="")
    assert len(_missing(roundtrip.compare(_device(), intent))) == 8


def test_a_changed_value_still_differs():
    intent = BASE.format(iface="")
    changed = _device(iface=" mop enabled\n no mop sysid\n")
    assert _missing(roundtrip.compare(changed, intent, platform=XE)) == ["mop enabled"]


def test_a_line_intent_declares_is_compared_as_before():
    """Intent stating a default the device does not print is still intent ahead of it (the
    device prints `mop enabled`): the table never hides intent's own line."""
    intent = BASE.format(iface=" no mop enabled\n")
    device = _device(iface=" mop enabled\n no mop sysid\n")
    report = roundtrip.compare(device, intent, platform=XE)
    assert "mop enabled" in _missing(report) and "no mop enabled" in _extra(report), report
    both = roundtrip.compare(_device(), intent, platform=XE)
    assert _missing(both) == [] and _extra(both) == [], "held on both sides: equal"


def test_build_artifact_reads_them_as_intent_match_does(monkeypatch):
    """`build_artifact` (what Intent-Match reads) passes its platform to the intent report; its
    template report, a fidelity question (does the template reproduce the capture), none."""
    from modules.nsot import render_artifact
    calls = []
    real = roundtrip.compare

    def spy(*args, **kwargs):
        calls.append(kwargs.get("platform", ""))
        return real(*args, **kwargs)

    from modules.nsot.parsers import get_parser
    monkeypatch.setattr(roundtrip, "compare", spy)
    intent = get_parser(XE).parse(_device())
    with_intent = render_artifact.build_artifact("edge1", _device(), XE, host_vars=intent)
    assert calls == [XE, ""], calls
    calls.clear()
    alone = render_artifact.build_artifact("edge1", _device(), XE)
    assert calls == [XE, ""], "no intent: the template report still compares every line"
    assert alone.template_report is not alone.report
    assert with_intent.report is not with_intent.template_report


def test_the_intent_editors_departs_rows_leave_them_out_of_the_devices_side():
    """`change_rows(capture, render, device_platform=…)`: the Intent editor's "how the device
    departs" rows and the configuration check's intent-match leave a printed default out, as
    Intent-Match does; a changed value still departs."""
    intent = BASE.format(iface="")
    assert roundtrip.change_rows(_device(), intent, device_platform=XE)["removed"] == []
    changed = _device(iface=" mop enabled\n no mop sysid\n")
    assert roundtrip.change_rows(changed, intent, device_platform=XE)["removed"] == [
        ("interface GigabitEthernet1", "mop enabled")]
    assert len(roundtrip.change_rows(_device(), intent,
                                     device_platform="cisco_ios")["removed"]) == 8


def test_two_renders_still_show_a_deleted_default_as_the_edits_own():
    """Between two renders (the edit's own diff) a deleted default is a change the person made,
    so `change_rows` without a device's platform keeps it."""
    before = BASE.format(iface=" no mop enabled\n")
    after = BASE.format(iface="")
    assert roundtrip.change_rows(before, after)["removed"] == [
        ("interface GigabitEthernet1", "no mop enabled")]


def test_the_editors_diffs_pass_the_device_side():
    """`intent_edit.diffs` reads the capture as the device's side, for its platform: a first
    boot's printed defaults are no departure there."""
    from modules.nsot import intent_edit
    intent = BASE.format(iface="")
    out = intent_edit.diffs("/nonexistent", "edge1", intent, intent, _device(), platform=XE)
    assert out["departs"] == 0 and out["departs_rows"] == [], out


def test_the_deploy_still_sends_intents_default_to_a_device_that_changed_it():
    """A printed default is not `HIDDEN`: intent's `no mop enabled` reaches a device that prints
    `mop enabled`, as before."""
    from modules.nsot.deploy import merge_commands
    intent = BASE.format(iface=" no mop enabled\n")
    device = _device(iface=" mop enabled\n no mop sysid\n")
    sent = [c.strip() for c in merge_commands(intent, device)]
    assert "no mop enabled" in sent, sent
    assert not platform_defaults.hidden(["interface GigabitEthernet1"], " no mop enabled")
