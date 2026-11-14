"""Intent's ``privilege_exec``: the reads a custom privilege level may run
(`modules/nsot/privilege_exec.py`; the operator, 2026-11-13: "mercury-ro at privilege 3, with
`privilege exec level 3 <command>` lines for exactly the reads that need it, through intent and
the template, previewed and approved by hash").

- **the allowlist is the AI read set's forms**, read from `router_reads.SHAPES` (a floor on
  their number, and the configuration class's read planted as absent);
- **what it refuses, by name**: a level outside 2 to 14, ``configure``, ``debug``, ``clear``,
  ``write``, ``copy``, ``reload``, ``enable`` and every verb that is not a read, the
  configuration class's read, a form the read set leaves out, ``all`` on leading words, an
  abbreviation, a command named twice; at every place intent is authored and written;
- **level 1 only as a restore** (the operator, 2026-11-13: "Let level 1 through intent only for
  a leading word of an entry held at a higher level (here just `show`), with a test that any
  other level-1 line is refused"): ``{level: 1, command: show}`` beside the telemetry entry is
  held; alone, for a read's whole words (``ping``, ``traceroute``), leading nothing held, or
  with ``all``, it is refused by name; the render sends every higher line first, then the
  restore, whatever their order in intent or in a capture;
- **the read-only account's lines are data** (`read_account_lines`): on IOS-XE the telemetry
  line and the ``show`` restore, on IOS nothing, ping's and traceroute's ``all`` lines only
  under the installation choice, each line with what it does to every other account;
- **the parsers read the lines** on IOS and IOS-XE, model only the ones the key may hold, and
  leave every other ``privilege`` line unmodelled, verbatim;
- **a round trip keeps them**, the render writes them before the ``username`` lines, and
  parse, render, parse is a fixed point;
- **a merge-only deploy adds them** and sends nothing where the device holds them, and never a
  ``no``; verify reads each back.

**The device lines here are TYPED in the form a device was measured to store** (C3580): no
capture in tests/fixtures holds a ``privilege`` line (searched 2026-11-13), so each is added to
a REAL capture (tests/fixtures/configs/) before its ``end``, in Cisco's command reference's form
(``privilege mode [all] {level level | reset} command-string``) and with what r4 (IOS-XE)
stored for the approved pair, read from its golden through `scripts/nmas-config-read` on
2026-11-14 (`R4`): a line for each leading word of the telemetry command at level 3, right
after it and longest first, then the restore. Before that measurement the typed lines held the
pair alone, so the render wrote two lines fewer than the device stores and all six IOS-XE
routers departed from intent by two (C3580).

IPv6 beside IPv4: the read set's IPv6 forms (``ping ipv6``, ``traceroute ipv6``, ``show ipv6
route``) are held as forms beside the IPv4 ones; nothing here parses an address.
"""

import os

import pytest

from modules.nsot import hostvars, privilege_exec as PX, roundtrip
from modules.nsot.parsers import get_parser

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "configs")
CAPTURES = {"cisco_iosxe": "r1_c8000v.cfg", "cisco_ios": "s1_vios_l2.cfg"}
PLATFORMS = sorted(CAPTURES)

#: Typed (see the module's words): the lines the key holds, an IPv6 form among them.
#: Each command's leading words are among them, as a device stores them (C3580): `traceroute`
#: for `traceroute ipv6`, `show ipv6` for `show ipv6 route`.
MODELLED = ["privilege exec level 3 show telemetry ietf subscription",
            "privilege exec all level 3 ping",
            "privilege exec all level 3 traceroute ipv6",
            "privilege exec level 3 traceroute",
            "privilege exec level 3 show telemetry ietf",
            "privilege exec level 3 show telemetry",
            "privilege exec level 3 show",
            "privilege exec level 14 show ipv6 route",
            "privilege exec level 14 show ipv6"]
ENTRIES = [{"level": 3, "command": "show telemetry ietf subscription", "all": False},
           {"level": 3, "command": "ping", "all": True},
           {"level": 3, "command": "traceroute ipv6", "all": True},
           {"level": 3, "command": "traceroute", "all": False},
           {"level": 3, "command": "show telemetry ietf", "all": False},
           {"level": 3, "command": "show telemetry", "all": False},
           {"level": 3, "command": "show", "all": False},
           {"level": 14, "command": "show ipv6 route", "all": False},
           {"level": 14, "command": "show ipv6", "all": False}]
#: The operator's approved pair (2026-11-13): the telemetry line, and the level-1 restore of
#: its leading word `show`, as entries and as the lines they render, in the order sent.
TELEMETRY = {"level": 3, "command": "show telemetry ietf subscription", "all": False}
RESTORE = {"level": 1, "command": "show", "all": False}
PAIR = ["privilege exec level 3 show telemetry ietf subscription", "privilege exec level 1 show"]
#: What r4 (IOS-XE) stores for the pair: its golden's privilege lines, in its order, read
#: masked through `scripts/nmas-config-read --grep '^privilege'` on 2026-11-14 (C3580); r1,
#: r3, r6, r7 and r8 hold the same four.
R4 = ["privilege exec level 3 show telemetry ietf subscription",
      "privilege exec level 3 show telemetry ietf",
      "privilege exec level 3 show telemetry",
      "privilege exec level 1 show"]
#: The two lines the device writes for the telemetry command's leading words, which the
#: render lacked: r4's "departs (-2)".
HEADS = R4[1:3]
#: Typed: lines the key may NOT hold, each staying unmodelled, whole.
NOT_MODELLED = ["privilege exec level 5 configure terminal",
                "privilege exec level 15 show telemetry ietf subscription",
                # Level 1 that restores nothing: `show` is held at 3 above (a command's second
                # line), `ping` is a read's whole words, nothing held begins `show ip `, and
                # `all` at level 1 is never a restore.
                "privilege exec level 1 show",
                "privilege exec level 1 ping",
                "privilege exec level 1 show ip",
                "privilege exec all level 1 show ipv6",
                "privilege exec all level 3 show",
                "privilege exec level 3 show running-config",
                "privilege exec level 3 debug all",
                "privilege exec level 3 show version",
                "privilege configure level 5 interface",
                "privilege interface level 5 shutdown",
                "privilege exec level 3 show  telemetry"]


def _capture(platform):
    with open(os.path.join(FIXTURES, CAPTURES[platform]), encoding="utf-8") as fh:
        return fh.read()


def _with(platform, lines):
    text = _capture(platform)
    assert text.count("\nend") == 1
    return text.replace("\nend", "\n" + "\n".join(lines) + "\nend", 1)


def _parse(text, platform):
    return get_parser(platform).parse(text)


# ── The allowlist ─────────────────────────────────────────────────────────────────────────────

class TestTheFormsAreTheAiReadSets:
    def test_every_device_state_read_s_fixed_words_are_a_whole_form(self):
        from modules.ai import router_reads as RR

        forms = PX.forms()
        whole = 0
        for name, send, _args, _against, cls, _words in RR.SHAPES:
            fixed = []
            for word in send.split():
                if word.startswith("{"):
                    break
                fixed.append(word)
            command = " ".join(fixed)
            if cls is None:
                assert forms.get(command) is True, (name, command)
                whole += 1
            else:
                assert command not in forms, f"{name}: the {cls} class's read is no form"
        assert whole >= 30, "the floor: the read set's device state reads"
        assert "show running-config" not in forms, "planted: the configuration class's"

    def test_the_measured_refusals_are_forms_ipv6_beside_ipv4(self):
        """The eight reads privilege 1 refused on an IOS-XE router, 2026-11-13."""
        forms = PX.forms()
        for command in ("show telemetry ietf subscription", "ping", "ping ipv6", "traceroute",
                        "traceroute ipv6"):
            assert forms[command] is True, command

    def test_leading_words_are_forms_and_never_whole(self):
        forms = PX.forms()
        for command in ("show", "show ip", "show ipv6", "show telemetry", "show telemetry ietf"):
            assert forms[command] is False, command
        assert set(c.split()[0] for c in forms) == {"show", "ping", "traceroute"}


# ── What it refuses, by name ──────────────────────────────────────────────────────────────────

def _entry(command, level=3, **more):
    return dict({"level": level, "command": command}, **more)


class TestWhatAnEntryMayHold:
    @pytest.mark.parametrize("entry", ENTRIES + [
        _entry("ping ipv6", all=True), _entry("traceroute", level=2, all=True),
        _entry("show ip route", all=True), _entry("show ip"), _entry("ping")])
    def test_a_read_of_the_read_set_at_2_to_14_is_held(self, entry):
        assert PX.problem(entry) == ""

    @pytest.mark.parametrize("verb,command", [
        ("configure", "configure terminal"), ("debug", "debug all"), ("clear", "clear counters"),
        ("write", "write memory"), ("copy", "copy running-config startup-config"),
        ("reload", "reload"), ("enable", "enable"), ("disable", "disable"),
        ("terminal", "terminal monitor"), ("delete", "delete flash:x"), ("test", "test aaa")])
    def test_a_verb_that_is_not_a_read_is_refused_by_name(self, verb, command):
        why = PX.problem(_entry(command))
        assert f"`{command}` is not a read: `{verb}` is never moved to a level" in why, why
        assert "show, ping or traceroute" in why
        assert PX.problem(_entry(command, all=True)) == why, "with `all` as without"

    @pytest.mark.parametrize("level", [0, 15, 16, -3])
    def test_a_level_outside_2_to_14_is_refused_naming_it(self, level):
        """Level 1 is `TestLevelOneOnlyAsARestore`'s: refused too, in its own words."""
        why = PX.problem(_entry("ping", level=level))
        assert f"level {level} is not 2 to 14" in why, why
        assert PX.problem(_entry("show", level=level), [TELEMETRY]) == why, \
            "whatever else the intent holds"

    @pytest.mark.parametrize("level", ["3", 3.0, True, None, [3]])
    def test_a_level_that_is_not_a_whole_number_is_refused(self, level):
        assert "is not a whole number, 2 to 14" in PX.problem(_entry("ping", level=level))

    def test_the_configuration_class_s_read_is_refused_naming_the_class(self):
        for command in ("show running-config", "show running-config interface"):
            why = PX.problem(_entry(command))
            assert f"`{command}` is the configuration class's read" in why, why

    @pytest.mark.parametrize("command,reason", [
        ("show users", "it prints a secret's position"),
        ("show startup-config", "it prints configuration in another form"),
        ("show logging", "the logs reach the model only from Loki")])
    def test_a_form_the_read_set_leaves_out_is_refused_with_its_reason(self, command, reason):
        why = PX.problem(_entry(command))
        assert "left out of the AI read set on purpose" in why and reason in why, why

    @pytest.mark.parametrize("command", ["show version", "show ip ospf database", "ping vrf",
                                         "show telemetry ietf subscription all extra"])
    def test_a_read_that_only_resembles_one_is_refused(self, command):
        why = PX.problem(_entry(command))
        assert f"`{command}` is not one of the AI read set's forms beginning" in why, why

    @pytest.mark.parametrize("command", ["show", "show ip", "show telemetry", "show ipv6"])
    def test_all_on_leading_words_is_refused(self, command):
        """`all` on `show` would lower every show command, `show running-config` among them."""
        assert PX.problem(_entry(command)) == ""
        why = PX.problem(_entry(command, all=True))
        assert f"`all` on `{command}` would move every command under it" in why, why

    @pytest.mark.parametrize("command", ["sh ip route", "Show ip route", "show  ip route",
                                         " ping", "ping ", "show ip route | include x",
                                         "show ip route\nconfigure terminal", "ping;reload"])
    def test_only_whole_lower_case_words_as_the_device_prints_them(self, command):
        assert PX.problem(_entry(command)) != ""

    def test_a_malformed_entry_is_refused(self):
        assert "is not a mapping" in PX.problem("privilege exec level 3 ping")
        assert "'mode'" in PX.problem(_entry("ping", mode="configure"))
        assert "is not true or false" in PX.problem(_entry("ping", all="yes"))
        assert "is not a command" in PX.problem({"level": 3})

    def test_the_document_s_problems_name_each_entry_and_a_command_named_twice(self):
        doc = {"privilege_exec": [_entry("ping", all=True), _entry("configure terminal"),
                                  _entry("ping", level=5)]}
        got = PX.problems(doc)
        assert len(got) == 2, got
        assert got[0].startswith("privilege_exec[1]: `configure terminal` is not a read")
        assert got[1].startswith("privilege_exec[2] names `ping` (level 5), which "
                                 "privilege_exec[0] names already (level 3)")
        assert PX.problems({"privilege_exec": ENTRIES}) == []
        assert PX.problems({}) == [] and PX.problems({"privilege_exec": []}) == []
        assert "it is a list" in PX.problems({"privilege_exec": {"level": 3}})[0]


class TestRefusedWhereIntentIsWritten:
    BAD = ("hostname: edge1\nprivilege_exec:\n- level: 3\n  command: configure terminal\n"
           "  all: false\n")
    GOOD = ("hostname: edge1\nprivilege_exec:\n- level: 3\n  command: show telemetry ietf "
            "subscription\n  all: false\n- level: 3\n  command: ping\n  all: true\n")

    def test_the_write_refuses_it_by_name_and_writes_nothing(self, tmp_path):
        with pytest.raises(hostvars.PrivilegeExecRefused) as exc:
            hostvars.write_committed_text(str(tmp_path), "edge1", self.BAD)
        assert "privilege_exec[0]: `configure terminal` is not a read" in str(exc.value)
        assert not os.path.exists(hostvars.committed_path(str(tmp_path), "edge1"))

    def test_the_write_takes_a_read(self, tmp_path):
        path = hostvars.write_committed_text(str(tmp_path), "edge1", self.GOOD)
        with open(path, encoding="utf-8") as fh:
            held = hostvars.from_yaml(fh.read())["privilege_exec"]
        assert held == ENTRIES[:2]

    def test_the_editor_s_check_refuses_it_at_its_line(self):
        from modules.nsot import intent_edit

        got = intent_edit.validate("edge1", self.BAD)
        assert got["ok"] is False and got["stage"] == "schema", got
        assert "`configure` is never moved to a level" in got["error"]
        assert got["line"] == 2
        assert intent_edit.validate("edge1", self.GOOD)["ok"] is True

    def test_the_one_rule_is_asked_by_every_authoring_gate(self):
        """The editor, bulk intent and the profile's layers each call `hostvars`' one check (by
        parsing each module, never by its text), and the write does too (the tests above)."""
        import ast

        from tests import source_index

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel in ("modules/nsot/intent_edit.py", "modules/nsot/bulk_intent.py",
                    "modules/nsot/fleet_change.py"):
            calls = [n for n in source_index.nodes(os.path.join(root, rel))
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == "privilege_exec_problems"
                     and isinstance(n.func.value, ast.Name) and n.func.value.id == "hostvars"]
            assert len(calls) == 1, (rel, len(calls))

    def test_the_key_and_its_fields_are_ones_intent_knows(self):
        assert "privilege_exec" in hostvars.known_top_level()
        assert hostvars.unknown_keys({"privilege_exec": ENTRIES}) == []
        (found,) = hostvars.unknown_keys({"privilege_exec": [_entry("ping", al=True)]})
        assert found[:2] == (("privilege_exec", 0), "al")


# ── The parsers and the template ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("platform", PLATFORMS)
class TestParsedAndRendered:
    def test_a_capture_with_no_privilege_line_holds_no_key_and_renders_as_before(self, platform):
        hv = _parse(_capture(platform), platform)
        assert "privilege_exec" not in hv
        assert "privilege" not in "\n".join(
            l for l in roundtrip.render(hv, platform).splitlines() if not l.startswith("username"))

    def test_the_lines_the_key_may_hold_are_modelled_in_order(self, platform):
        hv = _parse(_with(platform, MODELLED + NOT_MODELLED), platform)
        assert hv["privilege_exec"] == ENTRIES

    def test_every_other_privilege_line_stays_unmodelled_whole(self, platform):
        hv = _parse(_with(platform, MODELLED + NOT_MODELLED), platform)
        left = [u["line"] for u in hv["unmodeled"] if u["line"].startswith("privilege")]
        # The parser reads a line with its inner spaces as the capture holds them.
        assert sorted(left) == sorted(NOT_MODELLED), left

    def test_the_render_writes_each_line_before_the_accounts(self, platform):
        hv = _parse(_with(platform, MODELLED), platform)
        lines = roundtrip.render(hv, platform).splitlines()
        at = [lines.index(line) for line in MODELLED]
        assert at == sorted(at) and at == list(range(at[0], at[0] + len(MODELLED))), at
        assert [lines.count(line) for line in MODELLED] == [1] * len(MODELLED), "each once"
        first_user = next(n for n, l in enumerate(lines) if l.startswith("username "))
        assert at[-1] + 1 == first_user, "directly before the first username line"
        assert [PX.render_line(e) for e in ENTRIES] == MODELLED, "the module's line is the template's"

    def test_the_round_trip_reproduces_the_config_nothing_missing_nothing_extra(self, platform):
        report = roundtrip.validate_device(_with(platform, MODELLED + NOT_MODELLED), platform)
        assert not report.get("error"), report.get("error")
        assert report["details"]["missing"] == [], report["details"]["missing"]
        assert report["details"]["extra"] == [], report["details"]["extra"]

    def test_parse_render_parse_is_a_fixed_point(self, platform):
        first = _parse(_with(platform, MODELLED + NOT_MODELLED), platform)
        again = _parse(roundtrip.render(first, platform), platform)
        assert again["privilege_exec"] == first["privilege_exec"]
        assert hostvars.to_yaml(again) == hostvars.to_yaml(first)

    def test_intent_as_committed_renders_the_same_lines(self, platform):
        """Through YAML, as the editor commits it, an entry with no `all` among them."""
        hv = _parse(_capture(platform), platform)
        doc = hostvars.from_yaml(hostvars.to_yaml(hv))
        doc["privilege_exec"] = [{"level": 3, "command": "show telemetry ietf subscription"},
                                 {"level": 3, "command": "ping ipv6", "all": True}]
        doc["secrets"] = hv["secrets"]
        out = roundtrip.render(doc, platform).splitlines()
        assert "privilege exec level 3 show telemetry ietf subscription" in out
        assert "privilege exec all level 3 ping ipv6" in out

    def test_the_shipped_template_names_the_key(self, platform):
        """So the Intent check never says "nothing reads 'privilege_exec'" of a shipped
        template (`config_check.template_reads`)."""
        from modules.nsot import config_check

        assert "privilege_exec" in config_check.template_reads(
            roundtrip.TEMPLATE_ROOT, platform, "base.j2")


# ── Merge-only, and read back ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("platform", PLATFORMS)
class TestAMergeOnlyDeployAddsThem:
    def _rendered(self, platform, entries):
        hv = _parse(_capture(platform), platform)
        hv["privilege_exec"] = entries
        return roundtrip.render(hv, platform)

    def test_the_program_adds_exactly_the_lines_the_device_lacks(self, platform):
        from modules.nsot.deploy import merge_commands

        # Three entries, and the device's lines for the leading words they move (C3580): the
        # telemetry command's three, `show` at 3 since nothing restores it, and `traceroute`.
        sent = [MODELLED[0], "privilege exec level 3 show telemetry ietf",
                "privilege exec level 3 show telemetry", "privilege exec level 3 show",
                MODELLED[1], MODELLED[2], "privilege exec level 3 traceroute"]
        program = merge_commands(self._rendered(platform, ENTRIES[:3]), _capture(platform))
        assert [c for c in program if "privilege" in c and not c.startswith("username")] \
            == sent
        held = _with(platform, MODELLED[:1])
        program = merge_commands(self._rendered(platform, ENTRIES[:3]), held)
        assert [c for c in program if c.startswith("privilege")] == sent[1:]

    def test_a_device_holding_them_is_sent_nothing_and_never_a_no(self, platform):
        from modules.nsot.deploy import merge_commands

        held = _with(platform, MODELLED)
        assert not [c for c in merge_commands(self._rendered(platform, ENTRIES), held)
                    if "privilege exec" in c]
        # An entry taken out of intent: merge-only removes nothing.
        program = merge_commands(self._rendered(platform, ENTRIES[:1]), held)
        assert not [c for c in program if "privilege exec" in c], program

    def test_verify_reads_each_line_back(self, platform):
        from modules.nsot.verify_scope import read_back

        got = read_back(MODELLED[:3], _with(platform, MODELLED[:3]))
        assert got["missing"] == [] and got["checked"] == 3 and got["skipped"] == [], got
        got = read_back(MODELLED[:3], _with(platform, MODELLED[:2]))
        assert got["missing"] == [MODELLED[2]] and got["checked"] == 3, got


# ── Written by an action, for one device or many ──────────────────────────────────────────────

class TestAnActionWritesTheEntries:
    """`with_entries`: one structured entry per command, so an action gives a level its reads
    on many devices with one call each, through the intent editor (the operator, 2026-11-13:
    the account becomes an "Add the read-only account…" action, no hand-typed YAML)."""

    WANT = [{"level": 3, "command": "show telemetry ietf subscription"},
            {"level": 3, "command": "ping ipv6", "all": True}]

    def test_a_document_gains_the_entries_it_lacks_and_is_not_changed_itself(self):
        before = {"hostname": "edge1", "users": []}
        doc, added = PX.with_entries(before, self.WANT)
        assert before == {"hostname": "edge1", "users": []}, "the caller's document is its own"
        assert doc["privilege_exec"] == added == [
            {"level": 3, "command": "show telemetry ietf subscription", "all": False},
            {"level": 3, "command": "ping ipv6", "all": True}]
        assert PX.problems(doc) == []

    def test_a_second_run_adds_nothing(self):
        doc, _added = PX.with_entries({"hostname": "edge1"}, self.WANT)
        again, added = PX.with_entries(doc, self.WANT)
        assert added == [] and again == doc

    def test_its_own_entries_stay_first_and_as_they_were(self):
        own = [{"level": 5, "command": "show ip route", "all": False}]
        doc, added = PX.with_entries({"privilege_exec": own}, self.WANT)
        assert doc["privilege_exec"][0] == own[0] and len(doc["privilege_exec"]) == 3
        assert len(added) == 2

    @pytest.mark.parametrize("held", [{"level": 5, "command": "ping ipv6", "all": True},
                                      {"level": 3, "command": "ping ipv6", "all": False}])
    def test_a_command_held_otherwise_is_refused_naming_both_lines(self, held):
        with pytest.raises(ValueError) as exc:
            PX.with_entries({"privilege_exec": [held]}, self.WANT)
        assert f"`{PX.render_line(held)}`" in str(exc.value)
        assert "`privilege exec all level 3 ping ipv6`" in str(exc.value)

    def test_an_entry_the_key_may_not_hold_is_refused_before_anything_is_added(self):
        with pytest.raises(ValueError) as exc:
            PX.with_entries({}, self.WANT + [{"level": 3, "command": "configure terminal"}])
        assert "`configure` is never moved to a level" in str(exc.value)

    def test_what_it_writes_passes_the_editor_s_check_as_yaml(self):
        from modules.nsot import intent_edit

        doc, _added = PX.with_entries({"hostname": "edge1"}, self.WANT)
        got = intent_edit.validate("edge1", hostvars.to_yaml(doc))
        assert got["ok"] is True, got


# ── Level 1, only as a restore ────────────────────────────────────────────────────────────────

class TestLevelOneOnlyAsARestore:
    """The operator, 2026-11-13: "Line 1 (privilege exec level 3 show telemetry ietf
    subscription, IOS-XE) plus `privilege exec level 1 show`. Let level 1 through intent only
    for a leading word of an entry held at a higher level (here just `show`), with a test that
    any other level-1 line is refused"."""

    def test_the_restore_of_a_held_entry_s_leading_word_is_held(self):
        assert PX.problem(RESTORE, [TELEMETRY]) == ""
        assert PX.problems({"privilege_exec": [TELEMETRY, RESTORE]}) == []
        assert PX.problems({"privilege_exec": [RESTORE, TELEMETRY]}) == [], "in either order"
        # Every leading run of the held entry's words, never the whole.
        for command in ("show", "show telemetry", "show telemetry ietf"):
            assert PX.problem(_entry(command, level=1), [TELEMETRY]) == "", command

    def test_alone_it_is_refused_by_name(self):
        for held in ((), None, [RESTORE]):
            why = PX.problem(RESTORE, held or ())
            assert why.startswith("level 1 on `show` restores nothing: no entry of this "
                                  "intent at level 2 to 14 begins `show `"), why
        got = PX.problems({"privilege_exec": [RESTORE]})
        assert len(got) == 1 and got[0].startswith(
            "privilege_exec[0]: level 1 on `show` restores nothing"), got

    @pytest.mark.parametrize("command", ["ping", "traceroute", "ping ipv6", "traceroute ipv6",
                                         "show telemetry ietf subscription", "show ip route",
                                         "show interfaces"])
    def test_a_read_s_whole_words_are_never_opened_to_level_1(self, command):
        """`ping` beside `ping ipv6` at 3 leads a held entry, and is still refused: it is a
        read's whole words (the operator: refused for `ping`, `traceroute`, any whole form)."""
        held = [TELEMETRY, {"level": 3, "command": command + " x", "all": False},
                {"level": 3, "command": "ping ipv6", "all": True},
                {"level": 3, "command": "traceroute ipv6", "all": True}]
        why = PX.problem(_entry(command, level=1), held)
        assert why.startswith(f"level 1 on `{command}`: it is a read's whole words"), why
        assert "a read is never opened to level 1" in why

    @pytest.mark.parametrize("command,held", [
        ("show ip", [TELEMETRY]),                       # leads nothing held
        ("show telemetry", [_entry("show ip route")]),  # nor this
        ("show", [_entry("ping", all=True)]),           # another verb's entry
        ("show", [_entry("show", level=3)]),            # the word itself, not a longer entry
        ("show", [{"level": 1, "command": "show telemetry", "all": False}]),  # a level-1 one
        ("show", [{"level": 15, "command": "show telemetry ietf subscription"}]),  # not 2 to 14
        ("show", [_entry("show version")]),             # an entry the key may not hold
        ("show", ["privilege exec level 3 show telemetry ietf subscription"]),  # no entry at all
    ])
    def test_leading_nothing_held_at_a_higher_level_it_is_refused(self, command, held):
        why = PX.problem(_entry(command, level=1), held)
        assert why.startswith(f"level 1 on `{command}` restores nothing"), why

    def test_all_at_level_1_is_refused_whatever_it_leads(self):
        why = PX.problem(_entry("show", level=1, all=True), [TELEMETRY])
        assert why.startswith("`all` at level 1 on `show` would open every command under it "
                              "to every account"), why
        assert PX.problems({"privilege_exec": [TELEMETRY, _entry("show", level=1, all=True)]})

    @pytest.mark.parametrize("command,said", [
        ("configure", "`configure` is not a read: `configure` is never moved to a level"),
        ("enable", "`enable` is not a read"), ("debug", "`debug` is not a read"),
        ("show running-config", "is the configuration class's read"),
        ("show users", "left out of the AI read set on purpose"),
        ("show version", "is not one of the AI read set's forms"),
        ("sh", "`sh` is not a read"), ("Show", "is not a command as the device prints it")])
    def test_no_other_command_is_let_through_at_level_1(self, command, said):
        held = [TELEMETRY, _entry("show running-config x"), _entry("configure terminal")]
        assert said in PX.problem(_entry(command, level=1), held)

    def test_the_restore_s_command_named_twice_is_refused(self):
        got = PX.problems({"privilege_exec": [TELEMETRY, _entry("show", level=3), RESTORE]})
        assert len(got) == 1 and "names `show` (level 1), which privilege_exec[1] names " \
            "already (level 3)" in got[0], got

    def test_the_write_and_the_editor_hold_the_same_rule(self, tmp_path):
        from modules.nsot import intent_edit

        alone = "hostname: edge1\nprivilege_exec:\n- level: 1\n  command: show\n  all: false\n"
        pair = ("hostname: edge1\nprivilege_exec:\n- level: 3\n  command: show telemetry ietf "
                "subscription\n  all: false\n- level: 1\n  command: show\n  all: false\n")
        with pytest.raises(hostvars.PrivilegeExecRefused) as exc:
            hostvars.write_committed_text(str(tmp_path), "edge1", alone)
        assert "level 1 on `show` restores nothing" in str(exc.value)
        got = intent_edit.validate("edge1", alone)
        assert got["ok"] is False and "restores nothing" in got["error"]
        assert intent_edit.validate("edge1", pair)["ok"] is True
        path = hostvars.write_committed_text(str(tmp_path), "edge1", pair)
        with open(path, encoding="utf-8") as fh:
            assert hostvars.from_yaml(fh.read())["privilege_exec"] == [TELEMETRY, RESTORE]

    def test_an_action_writes_the_pair_and_never_the_restore_alone(self):
        doc, added = PX.with_entries({"hostname": "edge1"}, [RESTORE, TELEMETRY])
        assert added == [RESTORE, TELEMETRY]
        assert doc["privilege_exec"] == [TELEMETRY, RESTORE], "held in the order it is sent"
        again, added = PX.with_entries(doc, [TELEMETRY, RESTORE])
        assert added == [] and again == doc
        with pytest.raises(ValueError) as exc:
            PX.with_entries({"hostname": "edge1"}, [RESTORE])
        assert "level 1 on `show` restores nothing" in str(exc.value)
        # Beside what the document holds already, the restore alone is an edit of its own.
        doc, added = PX.with_entries({"privilege_exec": [TELEMETRY]}, [RESTORE])
        assert added == [RESTORE] and doc["privilege_exec"] == [TELEMETRY, RESTORE]


@pytest.mark.parametrize("platform", PLATFORMS)
class TestTheRestoreIsSentAfterItsLine:
    """IOS raises a command's leading words when it takes the higher line, so the restore goes
    after it: in the render and the program, whatever the order in intent or in a capture."""

    @pytest.mark.parametrize("order", [(0, 1, 2, 3), (3, 0, 1, 2)],
                             ids=["as sent", "restore first"])
    def test_a_capture_holding_the_pair_is_modelled_in_the_order_it_is_sent(
            self, platform, order):
        hv = _parse(_with(platform, [R4[n] for n in order]), platform)
        assert hv["privilege_exec"] == [TELEMETRY, _entry("show telemetry ietf", all=False),
                                        _entry("show telemetry", all=False), RESTORE]
        assert not [u for u in hv["unmodeled"] if u["line"].startswith("privilege")]
        assert "_privilege_exec_at" not in hv, "the parser's own bookkeeping never leaves it"

    @pytest.mark.parametrize("entries", [[TELEMETRY, RESTORE], [RESTORE, TELEMETRY]],
                             ids=["as sent", "restore first"])
    def test_the_render_and_the_program_send_the_higher_line_first(self, platform, entries):
        from modules.nsot.deploy import merge_commands

        hv = _parse(_capture(platform), platform)
        hv["privilege_exec"] = [dict(e) for e in entries]
        lines = roundtrip.render(hv, platform).splitlines()
        at = [lines.index(line) for line in R4]
        assert at == list(range(at[0], at[0] + 4)), (at, "r4's four lines, in its order, the "
                                                         "restore directly after them")
        assert [lines.count(line) for line in R4] == [1] * 4
        assert lines[at[-1] + 1].startswith("username "), "and all before the accounts"
        program = merge_commands("\n".join(lines) + "\n", _capture(platform))
        assert [c for c in program if c.startswith("privilege")] == R4
        # A device holding the higher lines and not the restore is sent the restore alone.
        program = merge_commands("\n".join(lines) + "\n", _with(platform, R4[:3]))
        assert [c for c in program if c.startswith("privilege")] == R4[3:]
        assert not [c for c in merge_commands("\n".join(lines) + "\n", _with(platform, R4))
                    if "privilege exec" in c], "holding all four, nothing, and never a `no`"

    def test_several_higher_lines_all_come_before_the_restores(self, platform):
        hv = _parse(_capture(platform), platform)
        hv["privilege_exec"] = [RESTORE, _entry("show ip", level=1), TELEMETRY,
                                _entry("show ip route", level=5)]
        assert PX.problems(hv) == []
        got = [l for l in roundtrip.render(hv, platform).splitlines()
               if l.startswith("privilege")]
        # `show ip route`'s leading words are both restores, so it writes no line for them.
        assert got == ["privilege exec level 3 show telemetry ietf subscription",
                       "privilege exec level 3 show telemetry ietf",
                       "privilege exec level 3 show telemetry",
                       "privilege exec level 5 show ip route",
                       "privilege exec level 1 show", "privilege exec level 1 show ip"]
        assert got == PX.rendered(hv["privilege_exec"])

    @pytest.mark.parametrize("order", [(0, 1, 2, 3), (3, 0, 1, 2)],
                             ids=["as sent", "restore first"])
    def test_the_round_trip_and_the_fixed_point_hold_in_either_order(self, platform, order):
        text = _with(platform, [R4[n] for n in order])
        report = roundtrip.validate_device(text, platform)
        assert not report.get("error"), report.get("error")
        assert report["details"]["missing"] == [] and report["details"]["extra"] == [], report
        first = _parse(text, platform)
        again = _parse(roundtrip.render(first, platform), platform)
        assert hostvars.to_yaml(again) == hostvars.to_yaml(first)

    def test_a_level_1_line_that_restores_nothing_stays_unmodelled_where_it_stood(
            self, platform):
        hv = _parse(_with(platform, ["privilege exec level 1 show"]), platform)
        assert "privilege_exec" not in hv
        left = [u for u in hv["unmodeled"] if u["line"].startswith("privilege")]
        assert [u["line"] for u in left] == ["privilege exec level 1 show"]
        linenos = [u["lineno"] for u in hv["unmodeled"]]
        assert linenos == sorted(linenos), "back at its own line, not at the end"
        report = roundtrip.validate_device(
            _with(platform, ["privilege exec level 1 show"]), platform)
        assert report["details"]["missing"] == [] and report["details"]["extra"] == []

    def test_verify_reads_the_pair_back(self, platform):
        from modules.nsot.verify_scope import read_back

        got = read_back(R4, _with(platform, R4))
        assert got["missing"] == [] and got["checked"] == 4, got
        got = read_back(R4, _with(platform, PAIR))
        assert got["missing"] == HEADS, got


# ── The read-only account's lines, as data ────────────────────────────────────────────────────

class TestTheReadAccountsLines:
    """`read_account_lines`: the operator's approved set, 2026-11-13 ("Ping and traceroute:
    not by default. An installation choice `Let the read-only account ping and traceroute`,
    off by default, whose preview states it removes them from levels 0–2 for every account")."""

    def test_on_ios_xe_the_telemetry_line_then_the_show_restore_and_nothing_else(self):
        got = PX.read_account_lines("cisco_iosxe", ping_traceroute=False)
        # `all` on the telemetry line (C3583): the plain line left the account at 3 refused
        # `show telemetry ietf subscription all` and `... 101 receiver` at their next word
        # (r7's probe, 2026-11-14).
        assert [g["entry"] for g in got] == [dict(TELEMETRY, all=True), RESTORE]
        assert [PX.render_line(g["entry"]) for g in got] == [
            "privilege exec all level 3 show telemetry ietf subscription", PAIR[1]]
        assert PX.rendered([g["entry"] for g in got]) == [
            "privilege exec all level 3 show telemetry ietf subscription"] + R4[1:]
        assert "and every option under it" in got[0]["effect"]
        assert "nothing outside that command changes level" in got[0]["effect"]
        assert got[1]["effect"] == (
            "puts `show` back at level 1, where it was: levels 0 to 2 keep every show command "
            "they had; only `show telemetry ietf subscription` (and its leading words `show "
            "telemetry` and `show telemetry ietf`) sits at 3")
        doc, added = PX.with_entries({}, [g["entry"] for g in got])
        assert PX.problems(doc) == [] and len(added) == 2

    @pytest.mark.parametrize("dialect", ["cisco_ios", "", "junos", "cisco-ios-xe"])
    def test_on_any_other_dialect_nothing(self, dialect):
        """Not measured there (the probe ran on an IOS-XE router): never guessed."""
        assert PX.read_account_lines(dialect, ping_traceroute=False) == []
        assert PX.read_account_lines(dialect, ping_traceroute=True) == []
        assert sorted(PX.MEASURED) == ["cisco_iosxe"]

    def test_the_choice_adds_the_two_all_lines_and_says_what_they_remove(self):
        got = PX.read_account_lines("cisco_iosxe", ping_traceroute=True)
        assert [PX.render_line(g["entry"]) for g in got] == [
            "privilege exec all level 3 show telemetry ietf subscription",
            "privilege exec all level 3 ping", "privilege exec all level 3 traceroute", PAIR[1]]
        for g, command in zip(got[1:3], ("ping", "traceroute")):
            assert f"it REMOVES {command} from levels 0 to 2 for every account on the device" \
                in g["effect"], g["effect"]
            assert "Let the read-only account ping and traceroute" in g["effect"]
        doc, _added = PX.with_entries({}, [g["entry"] for g in got])
        assert PX.problems(doc) == []
        assert [e["level"] for e in doc["privilege_exec"]] == [3, 3, 3, 1]

    def test_the_choice_is_read_from_the_installation_s_setting_off_by_default(
            self, monkeypatch):
        from modules.ai import router_reads

        assert len(PX.read_account_lines("cisco_iosxe")) == 2, "the default: off"
        monkeypatch.setattr(router_reads, "ping_traceroute_on", lambda: True)
        assert len(PX.read_account_lines("cisco_iosxe")) == 4

    def test_another_level_is_written_through(self):
        got = PX.read_account_lines("cisco_iosxe", 5, ping_traceroute=True)
        assert [g["entry"]["level"] for g in got] == [5, 5, 5, 1]
        assert "levels 0 to 4" in got[1]["effect"] and "sits at 5" in got[3]["effect"]


# ── The device's lines for a command's leading words (C3580) ─────────────────────────────────

#: Entry sets whose render the template and `PX.rendered` must agree on, each a shape the
#: leading-word rule has a branch for.
SHAPES = {
    "the approved pair": [TELEMETRY, RESTORE],
    "the pair, restore first": [RESTORE, TELEMETRY],
    "the pair with all": [dict(TELEMETRY, all=True), RESTORE],
    "no restore": [TELEMETRY],
    "a head named at another level": [TELEMETRY, _entry("show telemetry", level=5, all=False),
                                      RESTORE],
    "two lines sharing heads": [TELEMETRY, _entry("show ip route", all=False), RESTORE],
    "one word": [_entry("ping", all=True)],
    "the whole typed set": ENTRIES,
}


@pytest.mark.parametrize("platform", PLATFORMS)
class TestTheDeviceWritesTheLeadingWords:
    """r4's "departs (-2)" (C3580): IOS-XE stores a line for each leading word of a command it
    moved, at that line's level, right after it and longest first; the render wrote the entry's
    line alone, so every IOS-XE router given the read-only account departed from its intent by
    those two lines. The render writes them now, and intent reads back as the device stores it."""

    def _lines(self, platform, entries):
        hv = _parse(_capture(platform), platform)
        hv["privilege_exec"] = [dict(e) for e in entries]
        return [l for l in roundtrip.render(hv, platform).splitlines()
                if l.startswith("privilege")]

    def test_the_approved_pair_renders_what_r4_stores_line_for_line(self, platform):
        assert self._lines(platform, [TELEMETRY, RESTORE]) == R4

    def test_r4_s_golden_against_the_pair_s_intent_departs_by_nothing(self, platform):
        """The comparison guard 4 and the device list read: the render of the pair's intent
        against a config holding r4's four lines, nothing missing and nothing extra."""
        from modules.nsot.deploy import merge_commands

        hv = _parse(_capture(platform), platform)
        hv["privilege_exec"] = [dict(TELEMETRY), dict(RESTORE)]
        rendered = roundtrip.render(hv, platform)
        stored = _with(platform, R4)
        assert [l for l in rendered.splitlines() if l.startswith("privilege")] == R4
        assert sorted(l for l in stored.splitlines() if l.startswith("privilege")) \
            == sorted(R4), "the stored config holds exactly the four"
        assert not [c for c in merge_commands(rendered, stored) if "privilege" in c]

    @pytest.mark.parametrize("shape", sorted(SHAPES))
    def test_the_template_writes_what_the_module_says(self, platform, shape):
        got = self._lines(platform, SHAPES[shape])
        assert got == PX.rendered(SHAPES[shape]), shape
        assert len(got) == len(set(got)), "no line twice"

    def test_a_head_an_entry_names_is_that_entry_s_line_alone(self, platform):
        got = self._lines(platform, SHAPES["a head named at another level"])
        assert got == ["privilege exec level 3 show telemetry ietf subscription",
                       "privilege exec level 3 show telemetry ietf",
                       "privilege exec level 5 show telemetry",
                       "privilege exec level 1 show"]

    def test_lines_sharing_a_head_write_it_once_after_the_first(self, platform):
        got = self._lines(platform, SHAPES["two lines sharing heads"])
        assert got == R4[:3] + ["privilege exec level 3 show ip route",
                                "privilege exec level 3 show ip", R4[3]]

    def test_an_all_line_writes_its_heads_without_all(self, platform):
        """Cisco's command reference, `privilege`: `all` "changes the privilege level for all
        the suboptions to the same level", and "the commands starting with the first word will
        also have the specified access level"."""
        got = self._lines(platform, SHAPES["the pair with all"])
        assert got == ["privilege exec all level 3 show telemetry ietf subscription"] + R4[1:]

    def test_with_no_restore_show_is_written_at_the_line_s_level(self, platform):
        assert self._lines(platform, [TELEMETRY]) == R4[:3] + ["privilege exec level 3 show"]

    def test_a_one_word_command_has_no_head(self, platform):
        assert self._lines(platform, SHAPES["one word"]) == ["privilege exec all level 3 ping"]
