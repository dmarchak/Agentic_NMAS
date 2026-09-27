"""C76: the merge program is keyed on (section, line), never on the text.

`merge_diff()` computed `to_add` as `[l for l in intended if l not in
set(running)]`, so a child line counted as present if the same text sat under
ANY parent. Found 2026-09-27 building the restore preview's fixture: a new
interface's ` shutdown` was dropped because another interface was shut. The
worse case needs no new stanza. Intent adding ` ipv6 ospf 1 area 0` to an
interface on r3, whose other interfaces already carry it, produced an EMPTY
program, reported as "the device already has every line". `classify_diff()`
was chain-aware all along, so the preview's "add" list named the line the
program did not send.

`merge_commands()` then de-duplicated by text, so two new interfaces both
needing ` shutdown` got one between them. And its consistency assertion
compared text sets, so it could not see either drop.

The fleet cases are real configs with ONE real line removed from ONE real
stanza: the pieces are real, and only the arrangement is built (CLAUDE.md,
the fixture rule).
"""

import collections
import glob
import os

import pytest

from modules.nsot.deploy import classify_diff, merge_commands, merge_diff

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = sorted(glob.glob(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet",
                                      "*.cfg")))


def _shared_child_cases():
    """``(device, config, header, line)`` for every interface child line the
    real config carries under two or more interfaces."""
    cases = []
    for path in FLEET:
        text = open(path, encoding="utf-8").read()
        under, header = collections.defaultdict(list), None
        for raw in text.splitlines():
            line = raw.rstrip()
            if line.startswith("interface "):
                header = line
                continue
            if not line.startswith(" "):
                header = None
                continue
            if header and not line.startswith("  "):
                under[line].append(header)
        for line, headers in under.items():
            if len(headers) > 1:
                cases.append((os.path.basename(path)[:-4], text, headers[-1], line))
    return cases


def _without(text, header, line):
    """*text* with *line* removed from *header*'s stanza only."""
    out, inside = [], False
    for raw in text.splitlines():
        if raw.rstrip() == header:
            inside = True
        elif not raw.startswith(" "):
            inside = False
        if inside and raw.rstrip() == line:
            continue
        out.append(raw)
    return "\n".join(out) + "\n"


CASES = _shared_child_cases()


def test_the_fleet_carries_the_case():
    """Floor: measured 2026-09-27 at well over twenty, including
    ` ipv6 ospf 1 area 0` (r1-r4) and ` ip helper-address` (s1, s2)."""
    assert len(CASES) >= 20, len(CASES)
    lines = {c[3] for c in CASES}
    assert " ipv6 ospf 1 area 0" in lines and " ip nat inside" in lines


@pytest.mark.parametrize("device,config,header,line", CASES,
                         ids=[f"{c[0]}:{c[2]}:{c[3].strip()}" for c in CASES])
def test_a_line_missing_from_one_stanza_is_sent_to_that_stanza(device, config, header,
                                                              line):
    running = _without(config, header, line)
    assert running != config
    program = merge_commands(config, running)
    assert program == [header, line, "exit"], program


def test_the_preview_and_the_program_agree_about_what_is_added():
    """`classify_diff` (what the preview names) and the program (what is
    sent) answer one question, so they must agree."""
    config = next(c for c in CASES if c[3] == " ipv6 ospf 1 area 0")
    _dev, text, header, line = config
    running = _without(text, header, line)
    assert classify_diff(text, running)["add"] == [line]
    assert merge_diff(text, running)["to_add"] == [line]
    assert line in merge_commands(text, running)


def test_a_new_interface_gets_a_child_another_already_has():
    running = "hostname r1\ninterface GigabitEthernet3\n shutdown\n"
    intended = running + "interface GigabitEthernet4\n shutdown\n"
    assert merge_commands(intended, running) == ["interface GigabitEthernet4", " shutdown",
                                                 "exit"]


def test_two_new_interfaces_needing_the_same_child_each_get_it():
    """The text-keyed de-duplication gave the second one nothing."""
    intended = "interface GigabitEthernet4\n shutdown\ninterface GigabitEthernet5\n shutdown\n"
    assert merge_commands(intended, "hostname r1\n") == [
        "interface GigabitEthernet4", " shutdown", "exit",
        "interface GigabitEthernet5", " shutdown", "exit"]


def test_the_same_line_in_the_same_section_is_still_present():
    """Control: nothing to send when the line is where intent puts it, and
    every real device's capture against itself is still an empty program."""
    for path in FLEET:
        text = open(path, encoding="utf-8").read()
        assert merge_commands(text, text) == [], path
    assert len(FLEET) == 9


def test_unchanged_count_counts_by_section():
    running = "hostname r1\ninterface GigabitEthernet3\n shutdown\n"
    intended = running + "interface GigabitEthernet4\n shutdown\n"
    diff = merge_diff(intended, running)
    assert diff["to_add"] == ["interface GigabitEthernet4", " shutdown"]
    assert diff["unchanged_count"] == 3


def test_the_consistency_assertion_sees_a_line_the_loop_skipped(monkeypatch):
    """The assertion is keyed and counts EVERY wanted line: a program loop
    that skips one (made to here: its read of intent misses Gi5's child,
    while the diff it was handed did not) refuses by name."""
    import modules.nsot.deploy as D

    intended = ("interface GigabitEthernet4\n shutdown\n"
                "interface GigabitEthernet5\n shutdown\n")
    diff = D.merge_diff(intended, "hostname r1\n")          # computed unpatched
    real = D._section_chains
    monkeypatch.setattr(D, "merge_diff", lambda i, r: diff)
    monkeypatch.setattr(D, "_section_chains", lambda text: [
        (line, chain) for line, chain in real(text)
        if "GigabitEthernet5" not in " ".join(chain)])
    with pytest.raises(RuntimeError, match=r"dropped=\[\(\('interface GigabitEthernet5',\)"):
        D.merge_commands(intended, "hostname r1\n")
