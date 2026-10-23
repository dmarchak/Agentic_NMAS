"""Platform console profiles as versioned, validated data (modules/nsot/console_profiles.py;
docs/LAB9_PLAN.md section 8, piece 3, O1).

A profile is approved like a template, so its loader is the gate: every field validated, an
unknown key refused, the commands it names reads only, no credential word and no console
timeout of its own in the kick-start template, and a sha256 over a canonical form that moves
with every field and with nothing else."""

import copy
import hashlib
import json
import os
import re

import pytest

from modules.nsot import console_profiles as P

HERE = P.HERE


def shipped_data(name="cisco_ios_switch") -> dict:
    with open(os.path.join(HERE, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def refused(data, match, expected_name=None):
    with pytest.raises(P.ProfileError, match=re.escape(match)):
        P.validate(data, expected_name)


# ── The shipped profiles ──────────────────────────────────────────────────────────────────

def test_both_shipped_profiles_load_under_their_file_names():
    assert P.shipped() == ["cisco_ios_router", "cisco_ios_switch"]
    for name in P.shipped():
        prof = P.load(name)
        assert (prof.name, prof.platform, prof.version) == (name, "cisco_ios", 1)


def test_the_hash_is_sha256_over_the_canonical_form():
    data = shipped_data()
    prof = P.load("cisco_ios_switch")
    expected = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=True).encode()).hexdigest()
    assert prof.sha256 == expected
    assert P.canonical(data) == json.dumps(data, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=True).encode()


def test_the_hash_ignores_key_order_and_whitespace():
    data = shipped_data()
    reordered = json.loads(json.dumps(dict(reversed(list(data.items())))), )
    assert P.validate(reordered).sha256 == P.validate(data).sha256
    assert P.load_text(json.dumps(data, indent=8)).sha256 == P.validate(data).sha256


@pytest.mark.parametrize("path,value", [
    (("version",), 2), (("description",), "another"), (("prompts", "more"), ["-- More --"]),
    (("kickstart", "lines"), ["configure terminal", " no shutdown", "end"]),
    (("blank_check", "command"), "dir flash:"),
])
def test_the_hash_moves_with_every_field(path, value):
    data = shipped_data()
    changed = copy.deepcopy(data)
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert P.validate(changed).sha256 != P.validate(data).sha256


def test_the_two_shipped_profiles_hash_differently():
    assert P.load("cisco_ios_switch").sha256 != P.load("cisco_ios_router").sha256


def test_the_profiles_properties_read_its_data():
    prof = P.load("cisco_ios_switch")
    assert prof.blank_command == "dir nvram:"
    assert prof.mac_command == "show version"
    # C1592: the switch types the plan's static address, mask and gateway.
    assert prof.kickstart_params == {"hostname": "hostname", "interface": "interface",
                                     "vlan": "vlan", "address": "ipv4_address",
                                     "mask": "ipv4_mask", "gateway": "ipv4_address"}
    assert prof.kickstart_lines[0] == "configure terminal"
    assert prof.kickstart_lines[-1] == "end"
    prof.kickstart_params["x"] = "vlan"
    assert "x" not in prof.kickstart_params


def test_the_profiles_reading_patterns_are_compiled_and_read_their_lines():
    """Loaded inside the test, so a measurement of which tests reach the loader sees it (the
    mutation sample of 2026-10-22: the MAC pattern dropped from the Profile survived, every
    reader of it holding a profile loaded at import)."""
    prof = P.validate(shipped_data())
    m = prof.mac_pattern.search("Base ethernet MAC Address : 52:54:00:ab:cd:ef")
    assert m.group(1) == "52:54:00:ab:cd:ef"
    m = prof.startup_entry.search("  254  -rw-   7   <no date>  startup-config")
    assert m.group(1) == "7"
    assert prof.ignore and prof.ignore[1].search("%SYS-5-CONFIG_I: Configured from console")


def test_a_command_that_is_not_text_is_refused_naming_its_field():
    """The mutation sample of 2026-10-22: the field's name dropped from the refusal survived."""
    data = shipped_data()
    data["mac"]["command"] = 5
    refused(data, "mac.command is 5, not a non-empty string")


def test_every_prompt_state_is_compiled_in_classification_order():
    prof = P.load("cisco_ios_router")
    assert set(prof.prompts) == set(P.PROMPT_STATES)
    assert P.PROMPT_STATES.index(P.CONFIG) < P.PROMPT_STATES.index(P.PRIV_EXEC)
    assert P.PROMPT_STATES[:3] == (P.MORE, P.LOGIN_PASSWORD, P.LOGIN_USER)
    assert all(hasattr(p, "search") for ps in prof.prompts.values() for p in ps)


# ── Refusals: shape ───────────────────────────────────────────────────────────────────────

def test_an_unknown_top_level_key_is_refused():
    data = shipped_data()
    data["extra"] = 1
    refused(data, "the profile has unknown key(s) ['extra']")


@pytest.mark.parametrize("key", P.TOP_KEYS)
def test_a_missing_top_level_key_is_refused(key):
    data = shipped_data()
    del data[key]
    refused(data, f"the profile lacks ['{key}']")


def test_a_profile_that_is_not_an_object_is_refused():
    refused([1], "the profile is list, not an object")


def test_text_that_is_not_json_is_refused():
    with pytest.raises(P.ProfileError, match="the profile is not JSON"):
        P.load_text("{nope")


@pytest.mark.parametrize("section,key", [("prompts", "shell"), ("blank_check", "extra"),
                                         ("mac", "extra"), ("kickstart", "extra")])
def test_an_unknown_nested_key_is_refused(section, key):
    data = shipped_data()
    data[section][key] = ["x"]
    refused(data, f"{section} has unknown key(s) ['{key}']")


@pytest.mark.parametrize("section,key", [("prompts", "more"), ("prompts", "boot"),
                                         ("blank_check", "startup_entry"), ("mac", "pattern"),
                                         ("kickstart", "params")])
def test_a_missing_nested_key_is_refused(section, key):
    data = shipped_data()
    del data[section][key]
    refused(data, f"{section} lacks ['{key}']")


@pytest.mark.parametrize("value,match", [
    ("cisco ios", "name 'cisco ios' must match"), ("Cisco", "name 'Cisco' must match"),
    ("", "name is '', not a non-empty string"), (5, "name is 5, not a non-empty string"),
    ("a" * 65, "must match"),
])
def test_a_bad_name_is_refused(value, match):
    data = shipped_data()
    data["name"] = value
    refused(data, match)


def test_a_name_that_is_not_the_files_is_refused():
    refused(shipped_data(), "name 'cisco_ios_switch' is not the file's, 'other'",
            expected_name="other")


@pytest.mark.parametrize("value", [0, -1, True, "1", 1.0, None])
def test_a_version_that_is_not_a_positive_integer_is_refused(value):
    data = shipped_data()
    data["version"] = value
    refused(data, f"version {value!r} is not a positive integer")


@pytest.mark.parametrize("field", ["platform", "description"])
def test_an_empty_or_non_ascii_text_field_is_refused(field):
    data = shipped_data()
    data[field] = "  "
    refused(data, f"{field} is '  ', not a non-empty string")
    data[field] = "café"
    refused(data, f"{field} 'café' holds a character outside printable ASCII")


def test_a_tab_in_a_text_field_is_refused():
    data = shipped_data()
    data["description"] = "a\tb"
    refused(data, "outside printable ASCII")


def test_printable_ascii_at_both_ends_is_accepted():
    data = shipped_data()
    data["description"] = " ~"
    P.validate(data)


@pytest.mark.parametrize("value,match", [
    ([], "prompts.more is [], not a non-empty list of patterns"),
    ("--More--", "prompts.more is '--More--', not a non-empty list of patterns"),
    (["("], "prompts.more[0] '(' is not a regular expression"),
    (["(--More--)"], "prompts.more[0] '(--More--)' has 1 group(s), 0 expected"),
    ([""], "prompts.more[0] is '', not a non-empty string"),
])
def test_a_bad_prompt_pattern_list_is_refused(value, match):
    data = shipped_data()
    data["prompts"]["more"] = value
    refused(data, match)


def test_ignore_may_be_empty_but_must_be_a_list_of_group_free_patterns():
    data = shipped_data()
    data["ignore"] = []
    assert P.validate(data).ignore == ()
    data["ignore"] = "x"
    refused(data, "ignore is 'x', not a list of patterns")
    data["ignore"] = ["(%x)"]
    refused(data, "ignore[0] '(%x)' has 1 group(s), 0 expected")


@pytest.mark.parametrize("section,key", [("blank_check", "startup_entry"), ("mac", "pattern")])
@pytest.mark.parametrize("pattern,groups", [("startup-config", 0), ("(\\d+) (x)", 2)])
def test_a_reading_pattern_must_have_exactly_one_group(section, key, pattern, groups):
    data = shipped_data()
    data[section][key] = pattern
    refused(data, f"{section}.{key} {pattern!r} has {groups} group(s), 1 expected")


@pytest.mark.parametrize("section", ["blank_check", "mac"])
@pytest.mark.parametrize("command", ["write memory", "configure terminal", "reload",
                                     "copy running-config startup-config", "erase nvram:"])
def test_a_profile_command_that_is_not_a_read_is_refused(section, command):
    data = shipped_data()
    data[section]["command"] = command
    refused(data, f"{section}.command {command!r} is not a read: REFUSED")


@pytest.mark.parametrize("section,key", [("prompts", None), ("blank_check", None), ("mac", None),
                                         ("kickstart", None)])
def test_a_section_that_is_not_an_object_is_refused(section, key):
    data = shipped_data()
    data[section] = ["x"]
    refused(data, f"{section} is list, not an object")


# ── Refusals: the kick-start template ─────────────────────────────────────────────────────

def test_params_must_be_an_object():
    data = shipped_data()
    data["kickstart"]["params"] = ["vlan"]
    refused(data, "kickstart.params is ['vlan'], not an object")


@pytest.mark.parametrize("name", ["Vlan", "vlan-id", "1x", "", "a b"])
def test_a_param_name_outside_lower_case_words_is_refused(name):
    data = shipped_data()
    data["kickstart"]["params"][name] = "vlan"
    refused(data, f"kickstart.params name {name!r} must match [a-z_]+")


def test_a_param_shape_that_is_not_known_is_refused():
    data = shipped_data()
    data["kickstart"]["params"]["vlan"] = "number"
    refused(data, "kickstart.params.vlan shape 'number' is not one of ['interface', 'vlan', "
                  "'hostname', 'ipv4_address', 'ipv4_mask']")


@pytest.mark.parametrize("line,word", [
    ("username admin privilege 15", "username"), ("enable secret 0 x", "secret"),
    (" password cisco", "password"), ("crypto key generate rsa", "key"),
    ("ENABLE PASSWORD x", "PASSWORD"), ("snmp-server user u g v3 auth sha Secret x", "Secret"),
])
def test_a_template_line_holding_a_credential_word_is_refused(line, word):
    data = shipped_data()
    data["kickstart"]["lines"].insert(1, line)
    refused(data, f"kickstart.lines[1] {line!r} holds {word!r}: no credential crosses")


@pytest.mark.parametrize("line", ["line con 0", " exec-timeout 0 0", "LINE CON 0",
                                  "exec-timeout 15 0"])
def test_a_template_setting_the_console_line_is_refused(line):
    data = shipped_data()
    data["kickstart"]["lines"].insert(1, line)
    refused(data, f"kickstart.lines[1] {line!r} sets the console line")


def test_a_line_that_merely_mentions_a_console_word_is_accepted():
    data = shipped_data()
    data["kickstart"]["lines"].insert(1, "description uplink line card")
    P.validate(data)


def test_an_undeclared_placeholder_is_refused():
    data = shipped_data()
    data["kickstart"]["lines"].insert(1, "ip domain name {domain}")
    refused(data, "kickstart.lines[1] 'ip domain name {domain}' names {domain}, not a declared "
                  "parameter (['address', 'gateway', 'hostname', 'interface', 'mask', 'vlan'])")


@pytest.mark.parametrize("line", ["hostname {hostname", "hostname }x", "hostname {Host}",
                                  "x {hostname.__class__}", "x {0}"])
def test_a_brace_that_is_not_a_placeholder_is_refused(line):
    data = shipped_data()
    data["kickstart"]["lines"].insert(1, line)
    refused(data, "holds a brace that is not a placeholder")


@pytest.mark.parametrize("lines,match", [
    (["hostname x", "end"], "kickstart.lines runs 'hostname x' to 'end'"),
    (["configure terminal", "hostname x"], "runs 'configure terminal' to 'hostname x'"),
    (["configure terminal"], "not a list of at least two lines"),
    ("configure terminal\nend", "not a list of at least two lines"),
    (["configure terminal", "", "end"], "kickstart.lines[1] is '', not a non-empty string"),
    (["configure terminal", "x\ty", "end"], "kickstart.lines[1] 'x\\ty' holds a character"),
])
def test_a_template_of_the_wrong_shape_is_refused(lines, match):
    data = shipped_data()
    data["kickstart"]["lines"] = lines
    refused(data, match)


def test_the_wrong_ends_refusal_names_the_first_and_the_last_line():
    """Three lines, so the last is not the second (the mutation run of 2026-10-22:
    `lines[+1]` for `lines[-1]` survived on two-line templates)."""
    data = shipped_data()
    data["kickstart"]["lines"] = ["configure terminal", "hostname x", "exit"]
    refused(data, "kickstart.lines runs 'configure terminal' to 'exit'; it must run "
                  "'configure terminal' to 'end'")


def test_the_shortest_template_is_accepted():
    data = shipped_data()
    data["kickstart"]["lines"] = ["configure terminal", "end"]
    assert P.validate(data).kickstart_lines == ("configure terminal", "end")


def test_check_template_refuses_on_its_own():
    with pytest.raises(P.ProfileError, match="holds 'secret'"):
        P.check_template(["configure terminal", "enable secret x", "end"], {})


# ── Loading by name ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["../cisco_ios_switch", "cisco_ios_switch.json", "", None,
                                  "a/b"])
def test_a_profile_name_outside_the_shape_is_refused_before_any_read(name):
    with pytest.raises(P.ProfileError, match="must match"):
        P.load(name)


def test_an_absent_profile_is_refused_naming_it():
    with pytest.raises(P.ProfileError, match="profile 'cisco_ios_absent' could not be read"):
        P.load("cisco_ios_absent")


def test_a_profile_from_another_folder_is_validated_the_same(tmp_path):
    data = shipped_data()
    (tmp_path / "mine.json").write_text(json.dumps(data))
    with pytest.raises(P.ProfileError, match="is not the file's, 'mine'"):
        P.load("mine", folder=str(tmp_path))
    data["name"] = "mine"
    (tmp_path / "mine.json").write_text(json.dumps(data))
    assert P.load("mine", folder=str(tmp_path)).name == "mine"
    (tmp_path / "notes.txt").write_text("x")
    assert P.shipped(str(tmp_path)) == ["mine"]
