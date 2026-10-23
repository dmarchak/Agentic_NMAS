"""C1593 and C1594: the static kick-start reads back what it typed and verifies the copy that
fetches its bootstrap (modules/nsot/console_kickstart.py: `readback_plan`, `compare_readback`,
`readback_verdict`, `mac_in`, `copy_line`, `verify_copy`). In the 0-survivor blocking set.

The reads' answers are IOS's `show running-config` in its documented normalisation
(tests/console_ios.py), and the MAC read is s1's real `show interfaces Vlan10`
(tests/fixtures/console/vios_l2_show_interfaces_vlan10.txt). The copy's wording is IOS's
documented one, NOT yet captured on vIOS-L2 (no copy has run on s5): its first run is the
measurement."""

import pytest

from modules import readonly_commands
from modules.nsot import console_kickstart as K
from modules.nsot import console_profiles as P
from modules.nsot import console_survey as V
from tests.console_ios import FIXTURE_MAC, copy_answers, read_answer, readback_answers, running

SWITCH = P.load("cisco_ios_switch")
ROUTER = P.load("cisco_ios_router")
PARAMS = {"hostname": "s5", "interface": "GigabitEthernet0/1", "vlan": 1,
          "address": "192.0.2.14", "mask": "255.255.255.252", "gateway": "192.0.2.13"}
LINES = V.render_kickstart(SWITCH, PARAMS)
PLAN = K.readback_plan(LINES)
READ_UPLINK = "show running-config interface GigabitEthernet0/1"
READ_SVI = "show running-config interface Vlan1"
READ_CON = "show running-config | section line con 0"
READ_GLOBAL = "show running-config | include ^hostname|^ip default-gateway"
READ_MAC = "show interfaces Vlan1"


def answers(config=None, **over) -> dict:
    """Each read's text as the session receives it (echo, answer, prompt), from *config*
    (`running`'s: a device that took every line by default); *over* replaces one read's."""
    config = config or running(LINES)
    out = {cmd: read_answer(cmd, config, "s5#").decode() for cmd in PLAN["reads"]}
    out.update({k.replace("_", " "): v for k, v in over.items()})
    return out


def with_lines(header: str, body: list, config=None) -> dict:
    config = config or running(LINES)
    config["sections"][header] = list(body)
    return config


# ── The plan ──────────────────────────────────────────────────────────────────────────────

def test_the_switch_reads_each_section_typed_then_the_globals_then_the_mac():
    assert PLAN["reads"] == (READ_UPLINK, READ_SVI, READ_CON, READ_GLOBAL, READ_MAC)
    assert PLAN["mac_read"] == READ_MAC
    assert PLAN["not_read"] == (("vlan 1", K.NOT_READ_BACK["vlan"]),)


def test_every_read_is_a_read():
    for cmd in PLAN["reads"] + K.readback_plan(V.render_kickstart(
            ROUTER, {"hostname": "r9", "interface": "Gi1"}))["reads"]:
        assert readonly_commands.refusal(cmd) == "", cmd


def test_each_typed_setting_has_its_exact_expectation():
    got = [(e.typed, e.read, e.section, e.key, e.want) for e in PLAN["expect"]]
    up, svi, con = "interface GigabitEthernet0/1", "interface Vlan1", "line con 0"
    assert got == [
        ("switchport mode access", READ_UPLINK, up, "switchport mode",
         (("switchport mode access",),)),
        ("switchport access vlan 1", READ_UPLINK, up, "switchport access vlan",
         (("switchport access vlan 1",), ())),
        ("no shutdown", READ_UPLINK, up, "shutdown", ((),)),
        ("ip address 192.0.2.14 255.255.255.252", READ_SVI, svi, "ip address",
         (("ip address 192.0.2.14 255.255.255.252",),)),
        ("ip address 192.0.2.14 255.255.255.252", READ_SVI, svi, "no ip address", ((),)),
        ("no shutdown", READ_SVI, svi, "shutdown", ((),)),
        ("exec-timeout 15 0", READ_CON, con, "exec-timeout", (("exec-timeout 15 0",),)),
        ("hostname s5", READ_GLOBAL, "", "hostname", (("hostname s5",),)),
        ("ip default-gateway 192.0.2.13", READ_GLOBAL, "", "ip default-gateway",
         (("ip default-gateway 192.0.2.13",),)),
    ]


def test_an_access_vlan_other_than_the_default_must_be_printed():
    plan = K.readback_plan(V.render_kickstart(SWITCH, dict(PARAMS, vlan=10)))
    e = next(e for e in plan["expect"] if e.key == "switchport access vlan")
    assert e.want == (("switchport access vlan 10",),)
    assert plan["mac_read"] == "show interfaces Vlan10"


def test_the_router_s_dhcp_line_is_read_back_as_typed():
    plan = K.readback_plan(V.render_kickstart(ROUTER, {"hostname": "r9", "interface": "Gi1"}))
    assert plan["reads"] == ("show running-config interface Gi1", READ_CON,
                             "show running-config | include ^hostname", "show interfaces Gi1")
    e = next(e for e in plan["expect"] if e.key == "ip address")
    assert e.want == (("ip address dhcp",),)


@pytest.mark.parametrize("lines,words", [
    (["configure terminal", "interface Vlan1", " description x", "end"],
     "no read-back is defined for 'description x' under 'interface Vlan1'"),
    (["configure terminal", "vlan 5", " name mgmt", "end"],
     "no read-back is defined for 'name mgmt' under 'vlan'"),
    (["configure terminal", " ip address dhcp", "end"],
     "no read-back is defined for 'ip address dhcp' under 'no section'"),
    (["configure terminal", "line con 0", " logging synchronous", "end"],
     "no read-back is defined for 'logging synchronous' under 'line con 0'"),
    (["configure terminal", "ip routing", "end"],
     "no read-back is defined for 'ip routing': the kick-start types only what it can read "
     "back"),
    (["configure terminal", "interface Vlan1", "ip domain-name x", "end"],
     "no read-back is defined for 'ip domain-name x'"),
    # The hand mutation of 2026-10-23: each shape below was taken by a mutant.
    (["configure terminal", "interface range Gi0/1 - 2", "end"],
     "no read-back is defined for 'interface range Gi0/1 - 2'"),
    (["configure terminal", "line vty 0 4", "end"],
     "no read-back is defined for 'line vty 0 4'"),
    (["configure terminal", "vlan 5", " exec-timeout 1 0", "end"],
     "no read-back is defined for 'exec-timeout 1 0' under 'vlan'"),
    (["configure terminal", "ip default-gatewayx 192.0.2.1", "end"],
     "no read-back is defined for 'ip default-gatewayx 192.0.2.1'"),
    (["configure terminal", "hostnamex", "end"], "no read-back is defined for 'hostnamex'"),
    (["configure terminal", "interface Vlan1", " shutdown", "end"],
     "no read-back is defined for 'shutdown' under 'interface Vlan1'"),
])
def test_a_line_with_no_read_back_is_refused_naming_it(lines, words):
    with pytest.raises(ValueError, match=words.replace("(", r"\(").replace(")", r"\)")):
        K.readback_plan(lines)


def test_a_section_entered_twice_is_read_once_and_two_addressed_interfaces_read_no_mac():
    plan = K.readback_plan(["configure terminal", "interface Vlan1", " ip address 192.0.2.1 "
                            "255.255.255.0", "interface Gi0/2", " ip address 192.0.2.5 "
                            "255.255.255.252", "interface Vlan1", " no shutdown", "end"])
    assert plan["reads"] == ("show running-config interface Vlan1",
                             "show running-config interface Gi0/2")
    assert plan["mac_read"] == ""


def test_a_global_typed_twice_is_one_key_in_the_include():
    plan = K.readback_plan(["configure terminal", "hostname a", "hostname b", "end"])
    assert plan["reads"] == ("show running-config | include ^hostname",)


# ── The comparison ────────────────────────────────────────────────────────────────────────

def test_a_device_that_took_every_line_matches_and_its_mac_is_read():
    v = K.readback_verdict(PLAN, answers())
    assert v == {"ok": True, "differs": [], "mac": "0c:00:6c:e9:80:0a",
                 "mac_why": f"the MAC in use, from {FIXTURE_MAC}"}


def test_ios_printing_the_default_access_vlan_also_matches():
    config = with_lines("interface GigabitEthernet0/1",
                        [" switchport access vlan 1", " switchport mode access"])
    assert K.compare_readback(PLAN, answers(config)) == []


def _differs(config=None, **over):
    return K.compare_readback(PLAN, answers(config, **over))


@pytest.mark.parametrize("body,typed,found", [
    ([" ip address dhcp"], "ip address 192.0.2.14 255.255.255.252", ("ip address dhcp",)),
    ([" ip address 192.0.2.15 255.255.255.252"], "ip address 192.0.2.14 255.255.255.252",
     ("ip address 192.0.2.15 255.255.255.252",)),
    ([], "ip address 192.0.2.14 255.255.255.252", ()),
    ([" ip address 192.0.2.14 255.255.255.252", " ip address 192.0.2.1 255.255.255.0 "
      "secondary"], "ip address 192.0.2.14 255.255.255.252",
     ("ip address 192.0.2.14 255.255.255.252", "ip address 192.0.2.1 255.255.255.0 secondary")),
    ([" ip address 192.0.2.14 255.255.255.252", " no ip address"],
     "ip address 192.0.2.14 255.255.255.252", ("no ip address",)),
    ([" ip address 192.0.2.14 255.255.255.252", " shutdown"], "no shutdown", ("shutdown",)),
])
def test_each_kind_of_svi_difference_names_typed_and_read(body, typed, found):
    got = _differs(with_lines("interface Vlan1", body))
    assert [(d["typed"], d["read"], d["found"]) for d in got] == [(typed, READ_SVI, found)]
    words = ", ".join(repr(x) for x in found) if found else "nothing for it"
    assert got[0]["why"].startswith(f"typed {typed!r}; {READ_SVI!r} shows {words} (it must "
                                    "show ")


def test_no_ip_address_alone_is_two_differences():
    got = _differs(with_lines("interface Vlan1", [" no ip address"]))
    assert [(d["typed"], d["found"]) for d in got] == [
        ("ip address 192.0.2.14 255.255.255.252", ()),
        ("ip address 192.0.2.14 255.255.255.252", ("no ip address",))]


def test_the_why_names_every_acceptable_answer():
    got = _differs(with_lines("interface GigabitEthernet0/1",
                              [" switchport access vlan 2", " switchport mode access"]))
    assert got == [{"typed": "switchport access vlan 1", "read": READ_UPLINK,
                    "found": ("switchport access vlan 2",),
                    "why": f"typed 'switchport access vlan 1'; {READ_UPLINK!r} shows "
                           "'switchport access vlan 2' (it must show 'switchport access vlan "
                           "1' or nothing for it)"}]


@pytest.mark.parametrize("body,typed", [
    ([" switchport mode trunk"], "switchport mode access"),
    ([], "switchport mode access"),
    ([" switchport mode access", " switchport mode access"], "switchport mode access"),
    ([" switchport mode access", " shutdown"], "no shutdown"),
])
def test_each_kind_of_uplink_difference(body, typed):
    got = _differs(with_lines("interface GigabitEthernet0/1", body))
    assert [d["typed"] for d in got] == [typed]


@pytest.mark.parametrize("include,typed", [
    (["hostname Switch", "ip default-gateway 192.0.2.13"], "hostname s5"),
    (["ip default-gateway 192.0.2.13"], "hostname s5"),
    (["hostname s5"], "ip default-gateway 192.0.2.13"),
    (["hostname s5", "ip default-gateway 192.0.2.1"], "ip default-gateway 192.0.2.13"),
    (["hostname s5", "hostname s5", "ip default-gateway 192.0.2.13"], "hostname s5"),
])
def test_each_kind_of_global_difference(include, typed):
    text = f"{READ_GLOBAL}\r\n" + "".join(f"{x}\r\n" for x in include) + "s5#"
    got = _differs(**{READ_GLOBAL.replace(" ", "_"): text.replace("\r\n", "\n")})
    assert [d["typed"] for d in got] == [typed]


@pytest.mark.parametrize("body", [[" exec-timeout 0 0"], [], [" exec-timeout 15 0",
                                                             " exec-timeout 10 0"]])
def test_the_console_timeout_differences(body):
    got = _differs(with_lines("line con 0", body))
    assert [d["typed"] for d in got] == ["exec-timeout 15 0"]


def test_a_missing_section_fails_every_setting_under_it_naming_the_count():
    config = running(LINES)
    del config["sections"]["interface Vlan1"]
    got = _differs(config)
    assert [(d["typed"], d["found"]) for d in got] == [
        ("ip address 192.0.2.14 255.255.255.252", None),
        ("ip address 192.0.2.14 255.255.255.252", None), ("no shutdown", None)]
    assert got[0]["why"] == (f"typed 'ip address 192.0.2.14 255.255.255.252'; {READ_SVI!r} "
                             "shows 'interface Vlan1' 0 times (it must show it once)")


def test_a_section_shown_twice_is_a_difference():
    text = (f"{READ_SVI}\ninterface Vlan1\n ip address 192.0.2.14 255.255.255.252\n"
            "interface Vlan1\nend\ns5#")
    got = _differs(**{READ_SVI.replace(" ", "_"): text})
    assert got and all("shows 'interface Vlan1' 2 times" in d["why"] for d in got)


def test_a_read_that_answered_nothing_is_read_and_shows_no_section():
    """An empty answer was read (it is not "not read"): its section is shown 0 times (the hand
    mutation of 2026-10-23: an empty answer taken as not read survived)."""
    got = _differs(**{READ_SVI.replace(" ", "_"): ""})
    assert got and all(d["why"].endswith("shows 'interface Vlan1' 0 times (it must show it "
                                         "once)") for d in got)


def test_a_setting_s_words_are_whole_words():
    """A line beginning with the key's words run on is another setting (the hand mutation of
    2026-10-23: the key matched without its following space survived)."""
    config = with_lines("interface Vlan1", [" ip address 192.0.2.14 255.255.255.252",
                                            " ip addressing x", " shutdownable y"])
    assert _differs(config) == []


def test_a_read_that_did_not_happen_is_a_difference():
    got = K.compare_readback(PLAN, {k: v for k, v in answers().items() if k != READ_GLOBAL})
    assert [d["why"] for d in got] == [
        f"typed 'hostname s5'; {READ_GLOBAL!r} was not read",
        f"typed 'ip default-gateway 192.0.2.13'; {READ_GLOBAL!r} was not read"]


def test_the_echo_is_never_read_as_the_answer():
    """The global read's echo names `hostname` and `ip default-gateway` itself: read as an
    answer it would count twice."""
    assert K.answer_lines("show x", "show x\na\nb\ns5#") == ["a", "b"]
    assert K.answer_lines("show x", "\nshow x\na\ns5#") == ["", "a"]
    assert K.answer_lines("show x", "a\nshow x\ns5#") == ["a", "show x"], "only a first line"
    assert K.answer_lines("show x", "show x  \r\nb  \ns5#") == ["b"], "trailing space dropped"


def test_the_last_line_is_the_prompt_and_is_never_read():
    text = f"{READ_GLOBAL}\nhostname s5\nip default-gateway 192.0.2.13"
    got = _differs(**{READ_GLOBAL.replace(" ", "_"): text})
    assert [d["typed"] for d in got] == ["ip default-gateway 192.0.2.13"]


def test_a_section_s_body_ends_at_its_first_unindented_line():
    lines = ["interface Vlan1", " ip address a b", "!", " shutdown", "interface Vlan2"]
    assert K.section_body(lines, "interface Vlan1") == (["ip address a b"], 1)
    assert K.section_body(lines, "interface Vlan9") == (None, 0)
    assert K.section_body([" interface Vlan1"], "interface Vlan1") == (None, 0), \
        "an indented line is never a header"
    assert K.section_body(["interface Vlan1", " ip address a b", "interface Vlan2",
                           " shutdown"], "interface Vlan1") == (["ip address a b"], 1), \
        "the next section's header ends it, not only a `!`"


@pytest.mark.parametrize("line,header,same", [
    ("interface GigabitEthernet0/1", "interface Gi0/1", True),
    ("interface Gi0/1", "interface GigabitEthernet0/1", True),
    ("interface GigabitEthernet0/2", "interface Gi0/1", False),
    ("interface Vlan1 extra", "interface Vlan1", False),
    ("line con 0", "line con 0", True), ("line vty 0 4", "line con 0", False),
    ("line con 1", "line con 0", False), ("lines con 0", "line con 0", False),
    ("description GigabitEthernet0/1", "interface Gi0/1", False),
])
def test_a_header_is_its_section_by_canonical_name(line, header, same):
    assert K._same_header(line, header) is same                    # noqa: SLF001


# ── The MAC in use ────────────────────────────────────────────────────────────────────────

def test_an_unreadable_mac_fails_the_read_back_saying_so():
    over = {READ_MAC.replace(" ", "_"): f"{READ_MAC}\n% Invalid input\ns5#"}
    v = K.readback_verdict(PLAN, answers(**over))
    assert v["ok"] is False and v["differs"] == [] and v["mac"] is None
    assert v["mac_why"] == ("the interface's read shows 0 'Hardware is ..., address is' lines "
                            "(it must show one), so the MAC in use is not known")


def test_a_mac_read_that_did_not_happen_fails_it():
    got = {k: v for k, v in answers().items() if k != READ_MAC}
    v = K.readback_verdict(PLAN, got)
    assert (v["ok"], v["mac"], v["mac_why"]) == (False, None, f"{READ_MAC!r} was not read")


def test_a_difference_fails_it_with_the_mac_still_read():
    v = K.readback_verdict(PLAN, answers(with_lines("interface Vlan1", [])))
    assert v["ok"] is False and v["mac"] == "0c:00:6c:e9:80:0a" and len(v["differs"]) == 1


def test_a_plan_with_no_mac_read_is_ok_without_one():
    plan = dict(PLAN, mac_read="")
    v = K.readback_verdict(plan, answers())
    assert v == {"ok": True, "differs": [], "mac": None,
                 "mac_why": "no interface was given an address, so no MAC is read"}


@pytest.mark.parametrize("text,mac", [
    ("  Hardware is Ethernet SVI, address is 0C00.0875.8001 (bia 0c00.0875.8001)",
     "0c:00:08:75:80:01"),
    ("Hardware is iGbE, address is 5254.0012.3456 (bia 5254.0012.3456)", "52:54:00:12:34:56"),
])
def test_the_mac_is_read_from_its_one_hardware_line(text, mac):
    assert K.mac_in(f"x\n{text}\ny")[0] == mac


@pytest.mark.parametrize("text", [
    "Hardware is Ethernet SVI", "address is 0c00.0875.8001",
    "  Hardware is Ethernet SVI, address is 0c00.0875.80 (bia x)",
    "Hardware is A, address is 0c00.0875.8001\nHardware is B, address is 0c00.0875.8002",
    "x Hardware is Ethernet SVI, address is 0c00.0875.8001",
])
def test_no_single_hardware_line_is_no_mac(text):
    assert K.mac_in(text)[0] is None


# ── The copy (C1594) ──────────────────────────────────────────────────────────────────────

def test_the_copy_line_is_exactly_ios_s():
    assert K.copy_line("192.0.2.10", "s5.cfg") == "copy tftp://192.0.2.10/s5.cfg running-config"
    assert K.copy_steps("x") == [[P.PRIV_EXEC, "x"], [P.COPY_DESTINATION, ""]]


@pytest.mark.parametrize("server,why", [
    ("2001:db8::10", "the config server 2001:db8::10 is IPv6: out-of-band ZTP reserves and "
                     "serves IPv4 (DHCPv4) addresses only (C1245)"),
    ("[2001:db8::10]", "is IPv6"),
    ("server.example", "the config server 'server.example' is not an IPv4 address"),
    ("", "the config server '' is not an IPv4 address"),
    (None, "the config server None is not an IPv4 address"),
    ("192.0.2.300", "is not an IPv4 address"),
])
def test_a_server_that_is_not_ipv4_is_refused_by_name(server, why):
    with pytest.raises(ValueError, match=why.replace("(", r"\(").replace(")", r"\)")
                       .replace("[", r"\[").replace(".", r"\.")):
        K.copy_line(server, "s5.cfg")


@pytest.mark.parametrize("name", ["", None, "a/b.cfg", "../s5.cfg", "-x.cfg", "s5 .cfg",
                                  "s5.cfg running-config", "a" * 129])
def test_a_boot_file_that_is_not_a_file_name_is_refused(name):
    with pytest.raises(ValueError, match="is not a file name"):
        K.copy_line("192.0.2.10", name)


def test_a_boot_file_up_to_its_length_is_taken():
    assert K.copy_line("192.0.2.10", "a" * 128).endswith("/" + "a" * 128 + " running-config")


def _transfer(**kw) -> str:
    return copy_answers("copy tftp://192.0.2.10/s5.cfg running-config", "s5#", **kw)[1].decode()


def test_a_copy_that_moved_bytes_is_verified():
    assert K.verify_copy(_transfer(size=1203), SWITCH) == {
        "ok": True, "bytes": 1203, "refused": "", "why": "the copy printed '[OK - 1203 bytes]'"}


def test_the_key_generation_s_lines_in_the_copy_are_not_refusals():
    """The bootstrap generates the SSH key as it is applied (measured 39.5 s on vIOS-L2, C712):
    IOS's informational `%` lines then are messages, never a refusal."""
    keys = ("The name for the keys will be: s5.example.net\r\n% The key modulus size is 2048 "
            "bits\r\n% Generating 2048 bit RSA keys, keys will be non-exportable...\r\n[OK] "
            "(elapsed time was 39 seconds)\r\n")
    text = _transfer().replace("1203 bytes copied", keys + "1203 bytes copied")
    assert K.verify_copy(text, SWITCH)["ok"] is True


@pytest.mark.parametrize("size,why", [
    (0, "the copy printed '[OK - 0 bytes]': it must move more than 0 bytes"),
])
def test_a_copy_of_nothing_fails(size, why):
    v = K.verify_copy(_transfer(size=size), SWITCH)
    assert v == {"ok": False, "bytes": 0, "refused": "", "why": why}


def test_a_copy_of_one_byte_is_more_than_nothing():
    assert K.verify_copy(_transfer(size=1), SWITCH)["ok"] is True


def test_an_error_fails_it_naming_ios_s_words():
    err = "%Error opening tftp://192.0.2.10/s5.cfg (Timed out)"
    v = K.verify_copy(_transfer(transfer="Accessing tftp://192.0.2.10/s5.cfg...\r\n"
                                          f"{err}\r\n"), SWITCH)
    assert v == {"ok": False, "bytes": None, "refused": err,
                 "why": f"the copy's answer holds a refusal: {err!r} (after 'Accessing "
                        "tftp://192.0.2.10/s5.cfg...')"}


def test_a_refusal_inside_the_copied_file_fails_it_even_after_ok():
    text = _transfer().replace("[OK - 1203 bytes]", "[OK - 1203 bytes]\r\nip foo\r\n    ^\r\n"
                               "% Invalid input detected at '^' marker.")
    v = K.verify_copy(text, SWITCH)
    assert v["ok"] is False and v["refused"] == "% Invalid input detected at '^' marker."
    assert v["why"].endswith("(after 'ip foo')")


@pytest.mark.parametrize("text,count", [
    ("Accessing tftp://192.0.2.10/s5.cfg...\r\ns5#", 0),
    ("[OK - 5 bytes]\r\n[OK - 5 bytes]\r\ns5#", 2),
    ("[OK - 5 bytes] trailing\r\ns5#", 0),
    ("[OK - -5 bytes]\r\ns5#", 0),
    ("[OK]\r\ns5#", 0),
])
def test_anything_but_one_ok_line_fails_it(text, count):
    v = K.verify_copy(text, SWITCH)
    assert v["ok"] is False and v["bytes"] is None and v["refused"] == ""
    assert v["why"].endswith(f"it must print one '[OK - N bytes]' line, and printed {count}")


TARGET = {"state": "read", "server": "192.0.2.10", "boot_file": "s5.cfg"}


def test_the_builder_copies_only_for_a_static_profile_with_a_read_onboarding():
    """`console_ztp.build_kickstart`, the one builder (the hand mutation of 2026-10-23: a copy
    for any read onboarding survived; the preview refuses that pairing before a run)."""
    from modules.nsot import console_ztp as Z
    built = Z.build_kickstart(SWITCH, PARAMS, TARGET)
    assert built["copy"] == "copy tftp://192.0.2.10/s5.cfg running-config"
    assert built["lines"] == LINES and built["readback"] == PLAN
    assert built["program"]["copy"] == [[P.PRIV_EXEC, built["copy"] + "\r"],
                                        [P.COPY_DESTINATION, "\r"]]
    router = Z.build_kickstart(ROUTER, {"hostname": "r9", "interface": "Gi1"}, TARGET)
    assert router["copy"] == "" and router["program"]["copy"] == []
    assert Z.build_kickstart(SWITCH, PARAMS, dict(TARGET, state="absent"))["copy"] == ""
    assert Z.build_kickstart(SWITCH, PARAMS, None)["copy"] == ""


class _Bound:
    """A console whose next read-back read ends at the run's bound (no answer, no refusal)."""
    values = {}
    attach_state = "user_exec"

    class session:                                                   # noqa: N801
        refused = None

    def then(self, steps, final, step_timeout_s=None):
        from modules.nsot.console_transport import RunResult
        return RunResult(outcome="bound", reason="the run's bound passed", state="waiting",
                         attach_state=None, sent=b"", bytes_written=0, transcript="")

    def sent(self):
        return b""

    def bytes_written(self):
        return 0

    def transcript(self):
        return ""


def test_a_read_back_read_that_ends_any_way_but_done_stops_the_run():
    """The hand mutation of 2026-10-23: only an aborted read stopping it survived; a read that
    ended at the run's bound must stop it too, with that outcome, never read on."""
    from modules.nsot import console_ztp as Z
    program = Z.build_kickstart(SWITCH, PARAMS, TARGET)["program"]
    rec = {}
    assert Z._readback(_Bound(), SWITCH, program, rec) is False          # noqa: SLF001
    assert rec["outcome"] == "bound" and rec["reason"] == "read-back: the run's bound passed"
    assert "readback_differs" not in rec


def test_the_why_shows_the_copy_s_last_three_lines():
    v = K.verify_copy("a\r\nb\r\n\r\nc\r\nd\r\n", SWITCH)
    assert v["why"].startswith("the copy answered 'b / c / d': ")
    assert K.verify_copy("", SWITCH)["why"].startswith("the copy answered 'nothing': ")
