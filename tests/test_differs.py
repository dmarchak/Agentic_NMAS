"""P2's rules (docs/PHASE8_PLAN.md 15.9, card P2; 15.12: rules only this sprint): why an Intent
check that "differs" differs, each line classed by rule (`modules/nsot/differs.py`), carried in
`intent_match`'s result and said in the device page's Intent row.

On real captures with minimal edits: s3's and s4's goldens (VTP server, their `! VTP:` capture
header, no `vlan` line) against intent holding the VLANs C1649 measured in their databases; s1's
(transparent: it prints its VLANs); the two switches' `show vtp status` answers
(tests/fixtures/console/); r3's access list reordered; r2 with a not-modelled applet and line;
r2's self-signed certificate. Each class, a rule winning over unexplained line by line, order
only against a real change, IPv6 lines beside IPv4.
"""

import os
import types

import pytest

from modules.nsot import differs
from modules.nsot import intent_match as im

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
CONSOLE = os.path.join(ROOT, "tests", "fixtures", "console")
SERVER_HEADER = "! VTP: VTP Operating Mode                : Server\n"


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def _fleet(name):
    return _read(FLEET, f"{name}.cfg")


def _with_vlans(text, vlans):
    """*text* with `vlan N` lines where a transparent switch prints them (s1's place: after
    spanning-tree, before `lldp run`): the VLANs C1649 read in the switch's database."""
    block = "".join(f"vlan {v}\n!\n" for v in vlans)
    assert "\nlldp run\n" in text
    return text.replace("\nlldp run\n", "\n" + block + "lldp run\n", 1)


def _replace(text, old, new):
    assert old in text, old
    return text.replace(old, new, 1)


#: r2 with an applet the parser does not model (any but the heartbeat's) and an interface line
#: it does not model: typed, since no capture holds one.
APPLET = ('event manager applet PEER-DOWN\n event syslog pattern "BGP-5-ADJCHANGE"\n'
          ' action 1.0 syslog msg "peer 10.255.1.13 down"\n action 2.0 cli command "enable"\n')


def _r2_unmodelled(text):
    text = _replace(text, "\nnetconf-yang\n", "\n" + APPLET + "netconf-yang\n")
    return _replace(text, "interface GigabitEthernet2\n",
                    "interface GigabitEthernet2\n carrier-delay msec 0\n")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """A list's repository holding one device's committed intent (test_intent_match's lab,
    any device): ``make(host, platform, intent_text)`` parses the text, commits it as the
    device's intent and returns the repository."""
    from modules.nsot import hostvars, manifest, templates_repo
    from modules.nsot.parsers import get_parser
    from tests.intent_fixture import commit_intent

    list_dir = tmp_path / "lab"
    repo = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo, "golden"), exist_ok=True)
    os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
    templates_repo.seed_templates(repo)
    secrets = {}
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hostvars.hydrate_secrets",
                        lambda hv, host, ln="": {**hv, "secrets": dict(secrets)})
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost"}.get(key, default))

    def make(host, platform, intent_text):
        manifest.upsert_device(repo, f"uid:{host}", host, "192.0.2.10", platform=platform)
        intent = get_parser(platform).parse(intent_text)
        secrets.update(intent.get("secrets") or {})
        hostvars.write_committed(repo, intent)
        commit_intent(repo)
        return repo
    return make


def _check(lab, host, platform, intent_text, golden):
    repo = lab(host, platform, intent_text)
    return im.intent_match(repo, "Lab", host, golden, platform)


def _by_class(result):
    return {c["class"]: c for c in result["classes"]}


class TestTheVtpMode:
    """Read where Mercury holds it: a `show vtp status` answer, or the capture's `! VTP:` header,
    or a transparent switch's own `vtp mode` line; never inferred from an absence."""

    @pytest.mark.parametrize("name, mode", [("s5", "server"), ("s1", "transparent")])
    def test_a_show_vtp_status_answer(self, name, mode):
        assert differs.vtp_mode(_read(CONSOLE, f"vios_l2_{name}_show_vtp_status.txt")) == mode

    @pytest.mark.parametrize("name, mode", [("s3", "server"), ("s4", "server"),
                                            ("s1", "transparent"), ("s2", "transparent")])
    def test_a_captures_header(self, name, mode):
        assert differs.vtp_mode(_fleet(name)) == mode

    def test_a_transparent_switch_says_so_in_its_configuration_without_the_header(self):
        text = "".join(l for l in _fleet("s1").splitlines(True) if not l.startswith("! VTP:"))
        assert differs.vtp_mode(text) == "transparent"

    def test_a_server_switch_without_the_header_says_nothing_and_neither_does_a_router(self):
        """A server prints no `vtp` line, and neither does a router: absence is no mode."""
        assert differs.vtp_mode(_replace(_fleet("s3"), SERVER_HEADER, "")) == ""
        assert differs.vtp_mode(_fleet("r2")) == ""
        assert differs.vtp_mode("") == "" and differs.vtp_mode(None) == ""

    def test_an_indented_vtp_mode_line_is_not_the_switchs(self):
        assert differs.vtp_mode("interface Vlan1\n vtp mode transparent\n") == ""


class TestTheVtpDatabase:
    """C1646, C1649: a switch in VTP server or client mode keeps its VLANs in vlan.dat and never
    prints them, so intent's VLANs never appear in its golden."""

    @pytest.mark.parametrize("name, vlans", [("s3", (99, 100)), ("s4", (100,))])
    def test_a_server_switchs_vlans_are_its_vlan_database(self, lab, name, vlans):
        golden = _fleet(name)
        got = _check(lab, name, "cisco_ios", _with_vlans(golden, vlans), golden)
        assert got["state"] == "differs" and got["adds"] == len(vlans), got
        assert got["vtp_mode"] == "server"
        assert [c["class"] for c in got["classes"]] == ["vtp_database"], got["classes"]
        cls = got["classes"][0]
        assert cls["lines"] == [f"+ vlan {v}" for v in vlans]
        assert "vlan.dat" in cls["why"] and "VTP server mode" in cls["why"]

    def test_a_vlans_name_under_it_is_the_database_too(self, lab):
        golden = _fleet("s3")
        intent = _replace(_with_vlans(golden, (99, 100)), "vlan 100\n", "vlan 100\n name CORE\n")
        got = _check(lab, "s3", "cisco_ios", intent, golden)
        assert _by_class(got)["vtp_database"]["lines"] == ["+ vlan 99", "+ vlan 100",
                                                          "+ name CORE"]
        assert list(_by_class(got)) == ["vtp_database"]

    def test_the_same_lines_on_a_transparent_switch_are_unexplained(self, lab):
        """The control by the mode alone: s3's header says Transparent (one word edited), and a
        transparent switch prints its VLANs, so a VLAN its golden lacks is a departure."""
        golden = _replace(_fleet("s3"), ": Server\n", ": Transparent\n")
        got = _check(lab, "s3", "cisco_ios", _with_vlans(golden, (99, 100)), golden)
        assert got["vtp_mode"] == "transparent"
        assert [c["class"] for c in got["classes"]] == ["unexplained"]
        assert "VTP mode was not read" not in got["classes"][0]["why"]

    def test_a_mode_not_read_leaves_them_unexplained_and_says_why(self, lab):
        golden = _replace(_fleet("s3"), SERVER_HEADER, "")
        got = _check(lab, "s3", "cisco_ios", _with_vlans(golden, (99, 100)), golden)
        assert got["vtp_mode"] == ""
        [cls] = got["classes"]
        assert cls["class"] == "unexplained" and cls["lines"] == ["+ vlan 99", "+ vlan 100"]
        assert "2 of them are VLAN lines" in cls["why"] and "VTP mode was not read" in cls["why"]

    def test_a_transparent_switch_missing_a_vlan_it_prints_is_unexplained(self, lab):
        """s1, transparent and printing its VLANs, its golden without VLAN 30's stanza."""
        intent = _fleet("s1")
        golden = _replace(intent, "vlan 30\n name IPV6\n", "")
        got = _check(lab, "s1", "cisco_ios", intent, golden)
        assert got["vtp_mode"] == "transparent"
        assert [c["class"] for c in got["classes"]] == ["unexplained"]
        assert got["classes"][0]["lines"] == ["+ vlan 30", "+ name IPV6"]

    def test_the_rule_wins_line_by_line_with_ipv4_and_ipv6_beside_it(self, lab):
        """The VLAN lines are the database; an IPv4 and an IPv6 address intent adds to
        Loopback0 are not, and stay unexplained: a rule classifies its lines and no others."""
        golden = _fleet("s3")
        intent = _replace(_with_vlans(golden, (99, 100)), " ipv6 address 2001:DB8:1::23/128\n",
                          " ipv6 address 2001:DB8:1::23/128\n ipv6 address 2001:DB8:1::99/128\n")
        intent = _replace(intent, " ip address 10.255.1.23 255.255.255.255\n",
                          " ip address 10.255.1.23 255.255.255.255\n"
                          " ip address 10.255.9.23 255.255.255.255 secondary\n")
        got = _check(lab, "s3", "cisco_ios", intent, golden)
        by = _by_class(got)
        assert list(by) == ["vtp_database", "unexplained"], got["classes"]
        assert by["vtp_database"]["lines"] == ["+ vlan 99", "+ vlan 100"]
        unexplained = "\n".join(by["unexplained"]["lines"])
        assert "2001:DB8:1::99/128" in unexplained and "10.255.9.23" in unexplained
        assert "vlan" not in unexplained

    @pytest.mark.parametrize("top, cls", [
        ("vlan 10", "vtp_database"), ("vlan 10,20", "vtp_database"),
        ("vlan 10-12", "vtp_database"), ("vlan internal allocation policy ascending",
                                         "unexplained"),
        ("vlan dot1q tag native", "unexplained")])
    def test_only_a_vlan_line_is_one(self, top, cls):
        got = differs.classify({"extra": [{"section": "", "line": top, "kind": "child"}]},
                               vtp_mode="server")
        assert [c["class"] for c in got] == [cls]

    def test_a_vlan_line_the_golden_printed_is_never_the_database(self):
        """A `-` line is one the golden HOLDS: printed, so not kept out of the configuration."""
        got = differs.classify({"missing": [{"section": "", "line": "vlan 10", "kind": "child"}]},
                               vtp_mode="client")
        assert [c["class"] for c in got] == ["unexplained"]
        got = differs.classify({"extra": [{"section": "", "line": "vlan 10", "kind": "child"}]},
                               vtp_mode="client")
        assert [c["class"] for c in got] == ["vtp_database"]


def _r3_acl(text, order):
    """r3's access list NAT-PRIVATE with its three entries, as captured, in *order*."""
    head = "ip access-list standard NAT-PRIVATE\n"
    after = text.split(head, 1)[1].splitlines(True)
    entries = after[:next(i for i, l in enumerate(after) if not l.startswith(" "))]
    assert len(entries) == 3, entries
    return _replace(text, head + "".join(entries), head + "".join(entries[i] for i in order))


#: An IPv6 access list beside r3's IPv4 one, its entries in the given order (typed: no capture
#: holds one).
V6 = ["ipv6 access-list V6-MGMT\n", " permit ipv6 2001:DB8:1::/48 any\n",
      " deny ipv6 any any\n"]


def _with_v6_acl(text, order=(0, 1)):
    return _replace(text, "ip prefix-list NO-PRIVATE seq 5",
                    V6[0] + "".join(V6[1:][i] for i in order) + "ip prefix-list NO-PRIVATE seq 5")


class TestOrderOnly:
    def test_the_same_entries_in_another_order_are_order_only(self, lab):
        intent = _with_v6_acl(_fleet("r3"))
        golden = _with_v6_acl(_r3_acl(_fleet("r3"), (1, 0, 2)), order=(1, 0))
        got = _check(lab, "r3", "cisco_iosxe", intent, golden)
        assert got["state"] == "differs" and got["reordered"] == 2, got["classes"]
        assert got["adds"] == got["removes"] == 0
        by = _by_class(got)
        assert list(by) == ["order_only"], got["classes"]
        assert sorted(by["order_only"]["lines"]) == ["ip access-list standard NAT-PRIVATE",
                                                     "ipv6 access-list V6-MGMT"]
        assert "in 2 of them" in by["order_only"]["why"]
        assert "order decides what matches" in by["order_only"]["why"]

    def test_a_changed_entry_is_a_real_change_never_order_only(self, lab):
        """One entry of each list changed. The IPv4 list is modelled, so its change is
        unexplained; the parser carries an IPv6 access list verbatim (docs/IPV6_PARITY.md,
        `parsers/base.py`), so its change is a not-modelled line's."""
        intent = _with_v6_acl(_fleet("r3"))
        golden = _replace(intent, " 20 permit 172.16.0.0 0.15.255.255\n",
                          " 20 permit 172.31.0.0 0.0.255.255\n")
        golden = _replace(golden, " permit ipv6 2001:DB8:1::/48 any\n",
                          " permit ipv6 2001:DB8:2::/48 any\n")
        got = _check(lab, "r3", "cisco_iosxe", intent, golden)
        assert got["reordered"] == 0
        by = _by_class(got)
        assert list(by) == ["unmodelled", "unexplained"], got["classes"]
        assert by["unexplained"]["lines"] == ["+ 20 permit 172.16.0.0 0.15.255.255",
                                              "- 20 permit 172.31.0.0 0.0.255.255"]
        assert by["unmodelled"]["lines"] == ["+ permit ipv6 2001:DB8:1::/48 any",
                                             "- permit ipv6 2001:DB8:2::/48 any"]

    def test_a_section_whose_order_decides_nothing_is_said_so(self):
        got = differs.classify({"reordered": [{"section": "event manager applet PEER-DOWN",
                                               "running": [], "rendered": []}]})
        [cls] = got
        assert cls["class"] == "order_only" and cls["lines"] == ["event manager applet PEER-DOWN"]
        assert "order decides" not in cls["why"]


class TestUnmodelled:
    def test_a_line_the_extractor_does_not_model_is_unmodelled_either_side(self, lab):
        """The applet's action changed on the device from an IPv4 peer to an IPv6 one, and its
        interface line dropped: every line is one intent carries verbatim."""
        intent = _r2_unmodelled(_fleet("r2"))
        golden = _replace(intent, 'msg "peer 10.255.1.13 down"', 'msg "peer 2001:DB8:1::13 down"')
        golden = _replace(golden, " carrier-delay msec 0\n", "")
        got = _check(lab, "r2", "cisco_iosxe", intent, golden)
        by = _by_class(got)
        assert list(by) == ["unmodelled"], got["classes"]
        assert sorted(by["unmodelled"]["lines"]) == sorted([
            '+ action 1.0 syslog msg "peer 10.255.1.13 down"', "+ carrier-delay msec 0",
            '- action 1.0 syslog msg "peer 2001:DB8:1::13 down"'])
        assert "does not model" in by["unmodelled"]["why"]
        # C1812: the two `+` lines are intent's not-modelled list's; the `-` line (the device's
        # IPv6 peer) intent does not carry: only the device's golden does, and the words say so.
        assert by["unmodelled"]["carried"] == {"intent": 2, "golden": 1}
        assert differs.words(got["classes"]) == (
            "By rule: 3 lines: lines Mercury does not model: 2 carried verbatim in intent's "
            "not-modelled list, 1 only in the device's golden (intent does not carry them)")

    def test_a_not_modelled_line_only_the_device_has_is_unmodelled_by_its_own_parse(self, lab):
        """Intent without the applet; the golden holds it: the golden's own parse names it, and
        the words say the device's golden carries it, never intent (C1812: they said "carried
        verbatim in intent")."""
        intent = _fleet("r2")
        golden = _r2_unmodelled(intent)
        got = _check(lab, "r2", "cisco_iosxe", intent, golden)
        by = _by_class(got)
        assert list(by) == ["unmodelled"], got["classes"]
        assert "- event manager applet PEER-DOWN" in by["unmodelled"]["lines"]
        n = len(by["unmodelled"]["lines"])
        assert by["unmodelled"]["carried"] == {"intent": 0, "golden": n}
        words = differs.words(got["classes"])
        assert words == (f"By rule: {n} lines: lines Mercury does not model, carried only in "
                         "the device's golden: intent does not carry them"), words
        assert "in intent's not-modelled list" not in words
        assert "intent carries" not in by["unmodelled"]["why"]
        assert "only the device's golden carries" in by["unmodelled"]["why"]

    def test_a_line_intents_list_carries_is_said_as_intents(self):
        pairs = differs.unmodelled_of({"unmodeled": [{"line": "event manager applet A",
                                                      "children": [" action 1.0 x"]}]})
        got = differs.classify({"extra": [{"section": "event manager applet A",
                                           "line": "action 1.0 x", "kind": "child"}]},
                               unmodelled=pairs, golden_unmodelled=pairs)
        assert got[0]["carried"] == {"intent": 1, "golden": 0}
        assert differs.words(got) == ("By rule: 1 line: lines Mercury does not model, carried "
                                      "verbatim in intent's not-modelled list")

    def test_an_acknowledged_line_at_column_0_is_unmodelled_an_indented_one_names_no_block(self):
        hv = {"unmodeled_ack": {"lines": ["quantum-tunnel profile ALPHA", " action 9 x"]}}
        pairs = differs.unmodelled_of(hv)
        assert pairs == {("quantum-tunnel profile ALPHA", "quantum-tunnel profile ALPHA")}
        got = differs.classify({"extra": [
            {"section": "", "line": "quantum-tunnel profile ALPHA", "kind": "child"},
            {"section": "event manager applet X", "line": "action 9 x", "kind": "child"}]},
            unmodelled=pairs)
        assert [(c["class"], c["lines"]) for c in got] == [
            ("unmodelled", ["+ quantum-tunnel profile ALPHA"]), ("unexplained", ["+ action 9 x"])]

    def test_the_same_words_under_another_block_are_not_unmodelled(self):
        pairs = differs.unmodelled_of({"unmodeled": [{"line": "event manager applet A",
                                                      "children": [" action 1.0 x"]}]})
        got = differs.classify({"extra": [{"section": "event manager applet B",
                                           "line": "action 1.0 x", "kind": "child"}]},
                               unmodelled=pairs)
        assert [c["class"] for c in got] == ["unexplained"]


#: r2's own self-signed trustpoint and chain, and its CA-signed SLA trustpoint (a person's).
TP = "crypto pki trustpoint TP-self-signed-2968666059"
CHAIN = "crypto pki certificate chain TP-self-signed-2968666059"


class TestCertificate:
    def test_the_devices_own_certificate_lines_are_certificate(self):
        assert TP in _fleet("r2") and CHAIN in _fleet("r2")
        got = differs.classify({
            "extra": [{"section": TP, "line": "enrollment selfsigned", "kind": "child"},
                      {"section": CHAIN, "line": CHAIN, "kind": "section"}],
            "missing": [{"section": "crypto pki trustpoint SLA-TrustPoint",
                         "line": "revocation-check crl", "kind": "child"},
                        {"section": "", "line": "ip http secure-server", "kind": "child"}]})
        by = {c["class"]: c for c in got}
        assert list(by) == ["certificate", "unexplained"]
        assert by["certificate"]["lines"] == ["+ enrollment selfsigned", f"+ {CHAIN}"]
        assert by["unexplained"]["lines"] == ["- revocation-check crl",
                                              "- ip http secure-server"]

    def test_the_certificate_rule_wins_over_vlan_and_unmodelled(self):
        pairs = {(TP, "enrollment selfsigned")}
        got = differs.classify({"extra": [{"section": TP, "line": "enrollment selfsigned",
                                           "kind": "child"}]}, vtp_mode="server",
                               unmodelled=pairs)
        assert [c["class"] for c in got] == ["certificate"]

    def test_the_intent_check_already_sets_a_regenerated_one_aside(self, lab):
        """C302's case through the Intent check: r2's certificate regenerated under a new name.
        The comparison leaves the device's self-signed blocks out of both sides before any rule
        runs, so it matches: the class is reached only by a difference made elsewhere."""
        intent = _fleet("r2")
        golden = intent.replace("2968666059", "1234567890")
        assert golden != intent
        got = _check(lab, "r2", "cisco_iosxe", intent, golden)
        assert got["state"] == "match" and got["classes"] == [], got


class TestTheResult:
    def test_a_match_and_an_unknown_carry_no_classes(self, lab):
        golden = _fleet("r2")
        got = _check(lab, "r2", "cisco_iosxe", golden, golden)
        assert got["state"] == "match" and got["classes"] == [] and got["vtp_mode"] == ""
        assert im._unknown("x")["classes"] == []

    def test_every_line_is_classed_never_only_the_capped_ones(self, lab):
        golden = _fleet("s3")
        vlans = tuple(range(200, 200 + im.LINE_CAP + 5))
        got = _check(lab, "s3", "cisco_ios", _with_vlans(golden, vlans), golden)
        assert len(got["lines"]) == im.LINE_CAP
        assert len(_by_class(got)["vtp_database"]["lines"]) == len(vlans)

    def test_the_words_count_each_class_and_the_unexplained_rest(self):
        classes = differs.classify({"extra": [
            {"section": "", "line": "vlan 99", "kind": "child"},
            {"section": "", "line": "vlan 100", "kind": "child"},
            {"section": "", "line": "ipv6 unicast-routing", "kind": "child"}]},
            vtp_mode="server")
        assert differs.words(classes, "server") == (
            "By rule: 2 lines: VLANs a VTP server switch keeps in vlan.dat, never in its "
            "configuration; 1 line: not explained by a rule")

    def test_no_rule_says_so_and_no_classes_no_words(self):
        """C1821 (the operator, Walk 3, 2026-10-26): a departure no rule explains said nothing,
        so it was not told apart from an explained one; it says "No rule explains this
        difference" now. The premise "no rule, no words" was the defect, corrected here, not
        loosened: no classes at all (a match) still adds nothing."""
        classes = differs.classify({"extra": [{"section": "", "line": "ip cef",
                                               "kind": "child"}]})
        assert differs.explained(classes) is False
        assert differs.words(classes) == "No rule explains this difference" == differs.NO_RULE
        assert differs.classify({}) == [] and differs.words([]) == ""


class TestTheIntentRow:
    """The device page's Intent row (`device_page.intent_check`) says each class in its text,
    in the existing row: no new screen, tab or control."""

    def _row(self, lab, monkeypatch, host, platform, intent, golden):
        from modules import device_page
        repo = lab(host, platform, intent)
        monkeypatch.setattr("modules.nsot.repo.committed_golden_for",
                            lambda repo_dir, entry: {"text": golden, "commit": "0123456789"})
        ref = types.SimpleNamespace(repo_dir=repo, name="Lab")
        return device_page.intent_check(ref, {"hostname": host, "platform": platform})

    def test_a_server_switchs_vlans_are_said_as_its_database(self, lab, monkeypatch):
        golden = _fleet("s3")
        row = self._row(lab, monkeypatch, "s3", "cisco_ios", _with_vlans(golden, (99, 100)),
                        golden)
        assert row["state"] == "warn", row            # explained, never cleared
        assert row["in_intent"] == ["vlan 99", "vlan 100"]
        assert row["text"].endswith(". By rule: 2 lines: VLANs a VTP server switch keeps in "
                                    "vlan.dat, never in its configuration"), row["text"]

    def test_a_difference_no_rule_explains_says_so(self, lab, monkeypatch):
        """C1821: the row says "No rule explains this difference" after the departure's own
        words (it added nothing, so it read as an explained one's would), IPv6 and IPv4 beside
        each other; and the walk's own shape, a description changed by hand."""
        golden = _fleet("s3")
        for old, new in ((" ipv6 address 2001:DB8:1::23/128\n",
                          " ipv6 address 2001:DB8:1::23/128\n ipv6 address 2001:DB8:1::99/128\n"),
                         (" ip address 10.255.1.23 255.255.255.255\n",
                          " ip address 10.255.1.23 255.255.255.255\n"
                          " ip address 192.0.2.23 255.255.255.255 secondary\n"),
                         (" description mgmt identity\n", " description drift walk\n")):
            row = self._row(lab, monkeypatch, "s3", "cisco_ios", _replace(golden, old, new),
                            golden)
            assert row["state"] == "warn" and "By rule" not in row["text"], row["text"]
            assert row["text"].endswith(". No rule explains this difference"), row["text"]

    def test_the_rows_text_is_masked_as_the_lines_beside_it(self, lab, monkeypatch):
        """The departure's words name up to three of its lines: a changed credential line's
        value never reaches the row (planted: its last four characters)."""
        intent = _fleet("r2")
        user = next(l for l in intent.splitlines() if l.startswith("username "))
        planted = "QZQZ"
        golden = _replace(intent, user, user[:-4] + planted)
        row = self._row(lab, monkeypatch, "r2", "cisco_iosxe", intent, golden)
        assert row["state"] == "warn", row
        assert "username" in row["text"] and planted not in row["text"], row["text"]
        assert all(planted not in l for l in row["on_device"] + row["in_intent"])

    def test_every_reader_of_the_result_gets_masked_lines(self, lab, monkeypatch):
        """C1688: masked at the source, `intent_match`'s result, so its other readers (Reload's
        gate and the deploy and revert previews through `explain`, Save All's refusal through
        `baseline_denial`, P2's classes) never see the value either."""
        from modules.nsot import intent_match as IM
        intent = _fleet("r2")
        user = next(l for l in intent.splitlines() if l.startswith("username "))
        planted = "QZQZ"
        golden = _replace(intent, user, user[:-4] + planted)
        repo = lab("r2", "cisco_iosxe", intent)
        r = IM.intent_match(repo, "Lab", "r2", golden, "cisco_iosxe")
        assert r["state"] == "differs" and any("username" in l for l in r["lines"]), r
        assert all(planted not in l for l in r["lines"]), r["lines"]
        assert planted not in IM.explain(r)
        assert all(planted not in d for d in IM.baseline_denial({"r2": r}))
        assert all(planted not in l for c in r["classes"] for l in c["lines"])
