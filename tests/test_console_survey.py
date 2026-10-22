"""The console survey's reading and the kick-start's lines (modules/nsot/console_survey.py;
docs/LAB9_PLAN.md section 8, O3, and the operator's additions of 2026-10-22).

- blank only when the startup-config entry is there and 0 bytes (the real `dir nvram:` output);
  absent, doubled or garbage is UNKNOWN, never blank;
- a console found signed in is "not factory-blank as found", whatever nvram says;
- the base MAC, or None said so;
- the kick-start's exact lines: declared parameters only, each to its shape, a finite console
  timeout always, no credential ever, printable ASCII only."""

import copy
import os
import re

import pytest

from modules.nsot import console_profiles as P
from modules.nsot import console_survey as V

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "console")
SWITCH = P.load("cisco_ios_switch")
ROUTER = P.load("cisco_ios_router")


def nvram_output() -> str:
    """The real `dir nvram:` answer from the diagnostic session's transcript."""
    with open(os.path.join(FIXTURES, "s5-session-enable-dir-nvram.txt"), encoding="ascii") as fh:
        text = fh.read()
    return text.split(">>> send 'dir nvram:\\r'\n", 1)[1]


REAL = nvram_output()
REAL_ENTRY = "  254  -rw-           0                    <no date>  startup-config"


def with_profile_data(change) -> P.Profile:
    data = copy.deepcopy(SWITCH.data)
    change(data)
    return P.validate(data)


# ── The blank check ───────────────────────────────────────────────────────────────────────

def test_the_real_output_with_a_zero_byte_startup_config_is_blank():
    assert REAL_ENTRY in REAL
    check = V.blank_check(REAL, SWITCH)
    assert (check.blank, check.size) == (True, 0)
    assert check.reason == "startup-config is 0 bytes in 'dir nvram:''s output"


def test_a_startup_config_with_bytes_is_not_blank_and_names_its_size():
    text = REAL.replace(REAL_ENTRY, "  254  -rw-        1342                    <no date>  "
                                    "startup-config")
    check = V.blank_check(text, SWITCH)
    assert (check.blank, check.size) == (False, 1342)
    assert "startup-config is 1342 bytes" in check.reason
    assert "holds a saved configuration" in check.reason


def test_one_byte_is_not_blank():
    text = REAL.replace(REAL_ENTRY, "  254  -rw-           1    <no date>  startup-config")
    assert V.blank_check(text, SWITCH).blank is False


def test_an_absent_startup_config_entry_is_unknown_never_blank():
    text = REAL.replace(REAL_ENTRY + "\n", "")
    assert "private-config" in text and "startup-config" not in text
    check = V.blank_check(text, SWITCH)
    assert (check.blank, check.size) == (None, None)
    assert check.reason == ("no startup-config entry in 'dir nvram:''s output, so blank is "
                            "unknown")


@pytest.mark.parametrize("text", [
    "", None, "% Invalid input detected at '^' marker.", "Switch#",
    "\x00\x01garbage\n\n", "startup-config", "  254  -rw-   zero   <no date>  startup-config",
    "  254  -rw-  0  <no date>  startup-config.bak",
])
def test_unparseable_output_is_unknown_never_blank(text):
    check = V.blank_check(text, SWITCH)
    assert (check.blank, check.size) == (None, None)


def test_two_startup_config_entries_are_unknown():
    text = REAL.replace(REAL_ENTRY, REAL_ENTRY + "\n" + REAL_ENTRY)
    check = V.blank_check(text, SWITCH)
    assert (check.blank, check.size) == (None, None)
    assert check.reason == ("2 startup-config entries in 'dir nvram:''s output ([0, 0]), so "
                            "blank is unknown")


def test_the_blank_check_reads_the_profiles_own_pattern():
    other = with_profile_data(lambda d: d["blank_check"].update(
        startup_entry=r"^startup is (\d+)$"))
    assert V.blank_check("startup is 0\n", other).blank is True
    assert V.blank_check(REAL, other).blank is None


# ── The survey's verdict: the signed-in rule ──────────────────────────────────────────────

@pytest.mark.parametrize("state", [P.PRIV_EXEC, P.USER_EXEC, P.CONFIG])
def test_a_console_found_signed_in_is_not_factory_blank_whatever_nvram_says(state):
    result = V.survey(state, REAL, SWITCH)
    assert result.blank is False
    assert result.found_signed_in is True
    assert result.found_state == state
    assert result.startup_config_bytes == 0
    assert result.reasons[0] == (f"not factory-blank as found: the console was signed in at "
                                 f"{state} before any line was typed")
    assert "startup-config is 0 bytes" in result.reasons[1]


@pytest.mark.parametrize("state", [P.PRESS_RETURN, P.SETUP_DIALOG])
def test_a_console_found_at_its_first_prompt_is_judged_by_nvram(state):
    result = V.survey(state, REAL, SWITCH)
    assert (result.blank, result.found_signed_in) == (True, False)
    assert result.reasons == ("startup-config is 0 bytes in 'dir nvram:''s output",)


def test_a_console_found_at_its_first_prompt_with_a_saved_config_is_not_blank():
    text = REAL.replace(REAL_ENTRY, "  254  -rw-  99  <no date>  startup-config")
    result = V.survey(P.PRESS_RETURN, text, SWITCH)
    assert (result.blank, result.startup_config_bytes) == (False, 99)


def test_a_console_found_at_its_first_prompt_with_unreadable_nvram_is_unknown():
    result = V.survey(P.PRESS_RETURN, "garbage", SWITCH)
    assert (result.blank, result.found_signed_in) == (None, False)


@pytest.mark.parametrize("state", [P.LOGIN_USER, P.LOGIN_PASSWORD])
def test_a_login_prompt_at_attach_is_not_factory_blank(state):
    result = V.survey(state, REAL, SWITCH)
    assert (result.blank, result.found_signed_in) == (False, False)
    assert result.reasons[0] == (f"not factory-blank as found: the console asked for a login "
                                 f"({state}) at attach")


@pytest.mark.parametrize("state", [None, "idle", P.BOOT, P.MORE, "unknown"])
def test_a_state_at_attach_the_survey_cannot_judge_is_unknown_never_blank(state):
    result = V.survey(state, REAL, SWITCH)
    assert (result.blank, result.found_signed_in) == (None, False)
    assert result.reasons[0] == (f"the state at attach is {state!r}, not one this survey can "
                                 "judge, so blank is unknown")


# ── The base MAC ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("line,mac", [
    ("Base ethernet MAC Address       : 52:54:00:AB:CD:EF", "52:54:00:ab:cd:ef"),
    ("Base Ethernet MAC address: 5254.00ab.cdef", "52:54:00:ab:cd:ef"),
    ("  Base ethernet MAC Address : 52-54-00-ab-cd-ef  ", "52:54:00:ab:cd:ef"),
])
def test_the_base_mac_is_read_and_normalised(line, mac):
    found = V.base_mac("Cisco IOS Software\n" + line + "\nModel number: X\n", SWITCH)
    assert found.value == mac
    assert found.reason == f"from 'show version': {line.strip()}"


@pytest.mark.parametrize("text", [
    "", None, "Cisco IOS Software, vios_l2 Software\nProcessor board ID <serial>\n",
    "Base ethernet MAC Address : 52:54:00:ab:cd", "Base ethernet MAC Address : unknown",
    "Base ethernet MAC Address : 52:54:00:ab:cd:ef:01",
])
def test_no_base_mac_is_none_and_says_so(text):
    found = V.base_mac(text, ROUTER)
    assert found.value is None
    assert found.reason == "no base MAC in 'show version''s output: the MAC is unknown"


def test_the_first_mac_line_wins():
    found = V.base_mac("Base ethernet MAC Address : 52:54:00:00:00:01\n"
                       "Base ethernet MAC Address : 52:54:00:00:00:02\n", SWITCH)
    assert found.value == "52:54:00:00:00:01"


def test_normal_mac_writes_lower_case_colon_pairs():
    assert V.normal_mac("AABB.CCDD.EEFF") == "aa:bb:cc:dd:ee:ff"
    assert V.normal_mac("aa-bb-cc-dd-ee-ff") == "aa:bb:cc:dd:ee:ff"


# ── The kick-start's lines ────────────────────────────────────────────────────────────────

SWITCH_PARAMS = {"hostname": "sw-new1", "interface": "GigabitEthernet0/0", "vlan": 10}


def test_the_switch_kickstart_is_exactly_its_template_with_the_finite_console_timeout():
    assert V.render_kickstart(SWITCH, SWITCH_PARAMS) == (
        "configure terminal",
        "hostname sw-new1",
        "vlan 10",
        "interface GigabitEthernet0/0",
        " switchport mode access",
        " switchport access vlan 10",
        " no shutdown",
        "interface Vlan10",
        " ip address dhcp",
        " no shutdown",
        "line con 0",
        " exec-timeout 15 0",
        "end",
    )


def test_the_router_kickstart_is_exactly_its_template_with_the_finite_console_timeout():
    assert V.render_kickstart(ROUTER, {"hostname": "r-new", "interface": "Gi0/0/1.20"}) == (
        "configure terminal", "hostname r-new", "interface Gi0/0/1.20", " ip address dhcp",
        " no shutdown", "line con 0", " exec-timeout 15 0", "end")


def test_the_console_timeout_takes_a_chosen_finite_value():
    lines = V.render_kickstart(ROUTER, {"hostname": "r", "interface": "Gi1"},
                               exec_timeout_minutes=35791)
    assert lines[-3:] == ("line con 0", " exec-timeout 35791 0", "end")
    lines = V.render_kickstart(ROUTER, {"hostname": "r", "interface": "Gi1"},
                               exec_timeout_minutes=1)
    assert lines[-2] == " exec-timeout 1 0"


@pytest.mark.parametrize("minutes", [0, -1, 35792, True, 15.0, "15", None])
def test_an_infinite_or_malformed_console_timeout_is_refused(minutes):
    with pytest.raises(ValueError, match=re.escape(f"exec-timeout {minutes!r} minutes is not a "
                                                   "finite timeout from 1 to 35791")):
        V.render_kickstart(ROUTER, {"hostname": "r", "interface": "Gi1"},
                           exec_timeout_minutes=minutes)


def test_a_vlan_given_as_text_renders_the_same():
    assert V.render_kickstart(SWITCH, dict(SWITCH_PARAMS, vlan="10")) == \
        V.render_kickstart(SWITCH, SWITCH_PARAMS)


def test_an_undeclared_parameter_is_refused():
    with pytest.raises(ValueError, match=re.escape("parameter(s) ['vlan'] are not declared by "
                                                   "profile cisco_ios_router (['hostname', "
                                                   "'interface'])")):
        V.render_kickstart(ROUTER, {"hostname": "r", "interface": "Gi1", "vlan": 10})


def test_a_missing_parameter_is_refused():
    with pytest.raises(ValueError, match=re.escape("parameter(s) ['vlan'] are declared by "
                                                   "profile cisco_ios_switch and not given")):
        V.render_kickstart(SWITCH, {"hostname": "s", "interface": "Gi0/0"})


def test_no_parameters_at_all_are_refused_as_missing():
    with pytest.raises(ValueError, match="are declared by profile cisco_ios_router and not "
                                         "given"):
        V.render_kickstart(ROUTER, None)


@pytest.mark.parametrize("name,value", [
    ("interface", "Gi0/0; reload"), ("interface", "Gi0/0\nreload"), ("interface", "Gi 0/0"),
    ("interface", "0/0"), ("interface", "GigabitEthernet"), ("interface", "Gi0/0/0/0/0"),
    ("interface", 5), ("interface", ""), ("interface", "Gi0/0.123456"),
    ("hostname", "sw 1"), ("hostname", "sw1\r"), ("hostname", "1sw"), ("hostname", "sw-"),
    ("hostname", "sw_1"), ("hostname", "a" * 64), ("hostname", "sw{vlan}"), ("hostname", ""),
    ("hostname", None), ("hostname", "sé"),
    ("vlan", 0), ("vlan", 4095), ("vlan", "010"), ("vlan", "10 "), ("vlan", -1),
    ("vlan", True), ("vlan", 10.0), ("vlan", "1e3"), ("vlan", 99999),
])
def test_a_parameter_off_its_shape_is_refused_naming_it(name, value):
    params = dict(SWITCH_PARAMS, **{name: value})
    with pytest.raises(ValueError, match=re.escape(f"parameter {name} {value!r} ")):
        V.render_kickstart(SWITCH, params)


@pytest.mark.parametrize("name,value", [
    ("interface", "Gi1"), ("interface", "TenGigabitEthernet1/0/48"), ("interface", "Vlan4094"),
    ("interface", "Port-channel1"), ("interface", "Gi0/0.10"),
    ("hostname", "a"), ("hostname", "a" * 63), ("hostname", "sw-1-a"), ("hostname", "SW9"),
    ("vlan", 1), ("vlan", 4094), ("vlan", "4094"),
])
def test_a_parameter_on_its_shape_is_accepted(name, value):
    lines = V.render_kickstart(SWITCH, dict(SWITCH_PARAMS, **{name: value}))
    assert any(str(value) in line for line in lines)


def test_the_vlan_refusal_names_the_ceiling():
    with pytest.raises(ValueError, match="is over VLAN 4094"):
        V.check_param("vlan", "vlan", 4095)


def test_the_shape_refusal_names_the_shape_and_its_pattern():
    with pytest.raises(ValueError, match=re.escape("parameter vlan 'x' is not a valid vlan (it "
                                                   "must match [1-9][0-9]{0,3})")):
        V.check_param("vlan", "vlan", "x")
    with pytest.raises(ValueError, match="parameter uplink 'x' is not a valid interface"):
        V.check_param("uplink", "interface", "x")


@pytest.mark.parametrize("hostname,word", [("key", "key"), ("password", "password"),
                                           ("Secret", "Secret")])
def test_a_parameter_that_makes_a_credential_word_is_refused_in_the_rendered_line(hostname,
                                                                                  word):
    with pytest.raises(ValueError, match=re.escape(f"kick-start line 'hostname {hostname}' "
                                                   f"holds {word!r}")):
        V.render_kickstart(ROUTER, {"hostname": hostname, "interface": "Gi1"})


def test_every_rendered_line_is_printable_ascii_and_credential_free():
    for prof, params in ((SWITCH, SWITCH_PARAMS), (ROUTER, {"hostname": "r", "interface": "Gi1"})):
        for line in V.render_kickstart(prof, params):
            assert line and all(" " <= c <= "~" for c in line), line
            assert not re.search(r"\b(username|password|secret|key)\b", line, re.I), line


def test_the_console_timeout_is_always_under_line_con_0_before_end():
    lines = V.render_kickstart(SWITCH, SWITCH_PARAMS)
    i = lines.index("line con 0")
    assert lines[i + 1] == " exec-timeout 15 0"
    assert lines[i + 2:] == ("end",)
    assert sum(1 for line in lines if "exec-timeout" in line) == 1


def test_a_template_that_slipped_past_the_loader_is_checked_again_at_render():
    """A Profile built around validate (its data changed after loading) still cannot type a
    credential or its own console line: render re-checks the template."""
    data = copy.deepcopy(ROUTER.data)
    prof = P.validate(data)
    data["kickstart"]["lines"].insert(1, "enable secret 0 x")
    with pytest.raises(P.ProfileError, match="holds 'secret'"):
        V.render_kickstart(prof, {"hostname": "r", "interface": "Gi1"})
    data["kickstart"]["lines"][1] = "line con 0"
    with pytest.raises(P.ProfileError, match="sets the console line"):
        V.render_kickstart(prof, {"hostname": "r", "interface": "Gi1"})


@pytest.mark.parametrize("line", ["", "a\tb", "café", "x\x7f"])
def test_check_line_refuses_an_empty_or_unprintable_line(line):
    with pytest.raises(ValueError, match="empty or holds a character outside printable ASCII"):
        V.check_line(line)


def test_check_line_passes_printable_ascii_at_both_ends():
    assert V.check_line(" ~") == " ~"
