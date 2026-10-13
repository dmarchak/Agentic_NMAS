"""Defaults a device holds without printing them (C737; the operator's Phase 7 list, C14).

`modules/nsot/platform_defaults.py` is the one table, and every comparison of what Mercury
means against what a device prints asks it: the deploy's diff, verify's read-back, Intent-Match
(`roundtrip.canonical_lines`) and the IP SLA comparison. The case is s2's measured one (C713):
` frequency 60` sent under `ip sla 1`, no frequency line printed.
"""

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: s2's pair (tests/test_ip_sla_policy.py's S2_SENT and S2_PRINTED, the real receipt and golden).
SENT = ("hostname s2\nip sla 1\n icmp-echo 10.255.1.21 source-interface Loopback0\n"
        " frequency 60\nip sla schedule 1 life forever start-time now\nend\n")
PRINTED = ("hostname s2\nip sla 1\n icmp-echo 10.255.1.21 source-interface Loopback0\n"
           "ip sla schedule 1 life forever start-time now\nend\n")


def test_the_deploy_diff_sends_nothing_for_a_default_the_device_holds():
    from modules.nsot.deploy import classify_diff
    assert classify_diff(SENT, PRINTED) == {"add": [], "replace": [], "residue": [],
                                            "shares_key": []}


def test_a_printed_other_value_is_still_replaced_back_to_the_default():
    from modules.nsot.deploy import classify_diff
    printed = PRINTED.replace("Loopback0\n", "Loopback0\n frequency 120\n")
    got = classify_diff(SENT, printed)
    assert got["replace"] == [{"line": " frequency 60", "old": " frequency 120",
                               "new": " frequency 60"}] and got["add"] == []


def test_intent_match_calls_them_equal():
    from modules.nsot.roundtrip import change_rows
    got = change_rows(PRINTED, SENT)
    assert got["added"] == [] and got["removed"] == []


def test_ios_xe_nests_it_and_only_the_default_s_line_goes():
    from modules.nsot.platform_defaults import strip
    text = "ip sla 2\n icmp-echo 192.0.2.4\n  frequency 60\nip sla 3\n icmp-echo 192.0.2.5\n" \
           "  frequency 61\n"
    assert strip(text) == ("ip sla 2\n icmp-echo 192.0.2.4\nip sla 3\n icmp-echo 192.0.2.5\n"
                           "  frequency 61\n")


def test_a_frequency_outside_an_ip_sla_section_is_not_a_default():
    from modules.nsot.platform_defaults import hidden
    assert hidden(["interface Gi0/1"], " frequency 60") == ""
    assert hidden([], "frequency 60") == ""


def test_every_comparison_asks_the_one_table():
    """By parsing: each comparison's own function names `platform_defaults`, so a fifth rule
    added to the table reaches all four."""
    where = {"modules/nsot/deploy.py": "classify_diff",
             "modules/nsot/verify_scope.py": "read_back",
             "modules/nsot/roundtrip.py": "canonical_lines",
             "modules/nsot/ip_sla_policy.py": "compare"}
    for rel, fn in where.items():
        tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn)
        names = {getattr(n, "id", getattr(n, "attr", "")) for n in ast.walk(node)}
        assert "platform_defaults" in names, f"{rel} {fn} does not ask platform_defaults"
