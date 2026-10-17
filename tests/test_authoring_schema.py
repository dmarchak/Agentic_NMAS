"""Authoring intent by hand: the noisy half and the silent half.

The deliverable of the branch-site stage is that **people author intent**. The
first thing a person doing that meets is

    UndefinedError: 'dict object' has no attribute 'no_switchport'

for a key they have never heard of, which does nothing, on a template that
renders under `StrictUndefined`. A parser emits all thirty interface keys, so
every render this project had ever done was fed a complete dict — the
authoring path was the first document to omit one. That is the shortest
distance between *"this tool lets you write configuration"* and *"this tool
doesn't"*.

Its opposite is silent and is the failure a human actually has:
`StrictUndefined` catches a **missing** key and can never catch a
**misspelled** one. `descripton` is never read, the line does not render, and
nothing says a word. Two halves of one problem, and before this only the wrong
half spoke.
"""

import copy
import os

import pytest

from modules.nsot import hostvars, roundtrip
from modules.nsot.parsers import get_parser

FLEET = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")


def _fleet():
    for name in sorted(os.listdir(FLEET)):
        platform = "cisco_iosxe" if name.startswith("r") else "cisco_ios"
        with open(os.path.join(FLEET, name), encoding="utf-8") as fh:
            yield name, platform, get_parser(platform).parse(fh.read())


class TestTheDeclaredKeysAreTheKeysTheParsersEmit:
    """**One producer.** A second copy of a key list is how the two come to
    disagree — and here the disagreement is a render that raises on a document
    the parser itself produced."""

    def test_every_key_a_parser_emits_is_declared(self):
        emitted = set()
        for _name, _platform, host_vars in _fleet():
            for interface in host_vars["interfaces"]:
                emitted |= set(interface)
        assert emitted, "the scan found no interfaces — it cannot say anything"
        missing = sorted(emitted - set(hostvars.INTERFACE_DEFAULTS))
        assert not missing, (
            f"the parsers emit {missing}, which INTERFACE_DEFAULTS does not "
            "declare — a hand-authored document omitting one would raise")

    def test_every_declared_key_is_one_a_parser_emits(self):
        """The other direction: a declared key nothing emits is a ghost, and
        would silently permit a misspelling that looks official."""
        emitted = set()
        for _name, _platform, host_vars in _fleet():
            for interface in host_vars["interfaces"]:
                emitted |= set(interface)
        extra = sorted(set(hostvars.INTERFACE_DEFAULTS) - emitted)
        assert not extra, f"declared but never emitted: {extra}"

    def test_the_floor(self):
        assert len(hostvars.INTERFACE_DEFAULTS) >= 25, \
            "measured 30; a set this small means the scan is wrong"

    def test_every_default_is_falsy(self):
        """A truthy default would emit a line nobody wrote."""
        for key, value in hostvars.INTERFACE_DEFAULTS.items():
            assert not value, f"{key} defaults to {value!r}, which renders"


class TestOmittingAKeyIsFine:

    def test_the_minimal_dict_a_person_writes_renders(self):
        _n, _p, host_vars = next(iter(_fleet()))
        document = copy.deepcopy(host_vars)
        document["interfaces"] = [{"name": "Loopback0",
                                   "description": "branch site identity",
                                   "ipv4": "10.255.1.16 255.255.255.255"}]
        rendered = roundtrip.render(document, "cisco_iosxe",
                                    secret_lookup=lambda _n: "x")
        assert "interface Loopback0" in rendered
        assert " description branch site identity" in rendered
        assert " ip address 10.255.1.16 255.255.255.255" in rendered

    def test_filling_changes_no_output_for_a_complete_document(self):
        """**The floor, and the reason this is safe to do on every render
        path** — approval, preview and deploy all go through it."""
        checked = 0
        for name, platform, host_vars in _fleet():
            before = roundtrip.render(host_vars, platform,
                                      secret_lookup=lambda _n: "x")
            after = roundtrip.render(hostvars.complete_interfaces(host_vars),
                                     platform, secret_lookup=lambda _n: "x")
            assert before == after, f"{name}: filling changed the render"
            checked += 1
        assert checked >= 9, f"only {checked} devices compared"

    def test_the_document_is_not_mutated(self):
        """The committed file is the record; a render must not edit it."""
        document = {"interfaces": [{"name": "Loopback0"}]}
        hostvars.complete_interfaces(document)
        assert document["interfaces"][0] == {"name": "Loopback0"}

    def test_a_missing_NON_interface_key_still_raises_and_says_what_to_do(self):
        """The guard is narrowed, not removed — and the message names the
        exact path read and what the intent holds there (C568: the words had
        been a guess about interface keys, for a top-level key)."""
        _n, _p, host_vars = next(iter(_fleet()))
        document = copy.deepcopy(host_vars)
        del document["logging"]
        with pytest.raises(Exception) as exc:
            roundtrip.render(document, "cisco_iosxe",
                             secret_lookup=lambda _n: "x")
        message = str(exc.value)
        assert "reads `logging`, and the intent does not hold it: at the intent's top " \
               "level, it holds " in message, message
        assert "interfaces" in message.split("it holds", 1)[1], \
            "the message does not say what the intent holds"


class TestMisspellingAKeyIsNot:
    """The silent half. Nothing reads it, the line does not render, and before
    this nothing anywhere said so."""

    def test_an_unknown_key_is_found(self):
        document = {"interfaces": [{"name": "Loopback0",
                                    "descripton": "typo"}]}
        assert hostvars.unknown_interface_keys(document) == [(0, "descripton")]

    def test_a_correct_document_reports_none(self):
        """**The floor.** A checker that flagged everything would satisfy the
        test above and make every real document unwritable."""
        for name, _platform, host_vars in _fleet():
            assert hostvars.unknown_interface_keys(host_vars) == [], name

    def test_the_index_is_reported_so_the_author_can_find_it(self):
        document = {"interfaces": [{"name": "Gi1"},
                                   {"name": "Gi2", "ipv4_address": "x"}]}
        assert hostvars.unknown_interface_keys(document) == [(1, "ipv4_address")]


class TestTheAuthoringGateReportsIt:
    """Reported where a person is, with a line, like a YAML error — because
    the render cannot report it at all."""

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        import app as nmas

        monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        nmas.app.config["TESTING"] = False
        return nmas.app.test_client()

    def test_a_misspelled_key_is_refused_with_a_line(self, client):
        """The intent editor's check, as the Intent tab runs it (`intent_edit.preview`; today's
        /templatize/committed/<host>/preview, this test's vehicle before, left at 7.8 on
        2026-10-17, P7-23)."""
        from modules.nsot import intent_edit

        document = ("hostname: r6\n"
                    "interfaces:\n"
                    "- name: Loopback0\n"
                    "  descripton: branch site identity\n")
        body = intent_edit.preview("lab", "r6", document)
        assert body["status"] == 400
        assert body["stage"] == "schema"
        assert body["line"] == 4, body
        assert "descripton" in body["error"]
        assert "Omitting a key is fine" in body["error"], \
            "the refusal must separate the harmless case from this one"


#: W4 step 48 (2026-10-17, the operator's screenshot 70): s5's BGP block one level up, under
#: `routing` itself, with `bgp: null`. The checks passed and the render dropped all of BGP.
W4_MISPLACED = ("routing:\n"
                "  bgp:\n"
                "  asn: '65099'\n"
                "  settings:\n"
                "  - bgp router-id 10.255.99.1\n"
                "  neighbors:\n"
                "  - neighbor 10.255.98.1 remote-as 65098\n"
                "  - neighbor 10.255.98.1 ebgp-multihop 2\n"
                "  - neighbor 10.255.98.1 update-source Loopback1\n"
                "  networks: []\n"
                "  address_families: []\n"
                "  ospf: []\n")
#: The same block where intent reads it (the control).
W4_PLACED = ("routing:\n"
             "  bgp:\n"
             "    asn: '65099'\n"
             "    settings:\n"
             "    - bgp router-id 10.255.99.1\n"
             "    neighbors:\n"
             "    - neighbor 10.255.98.1 remote-as 65098\n"
             "    - neighbor 10.255.98.1 ebgp-multihop 2\n"
             "    - neighbor 10.255.98.1 update-source Loopback1\n"
             "    networks: []\n"
             "    address_families: []\n"
             "  ospf: []\n")


def _seeded(name):
    """*name*'s real capture as the committed document seeding writes (`hostvars.to_yaml`).
    One minimal edit: the captures predate the heartbeat applet (`heartbeat: 0`), which the
    editor's syslog rule (whole or absent) refuses, so the block is given one."""
    platform = "cisco_iosxe" if name.startswith("r") else "cisco_ios"
    with open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8") as fh:
        host_vars = get_parser(platform).parse(fh.read())
    host_vars["logging"]["syslog"]["heartbeat"] = 300
    return hostvars.to_yaml(host_vars)


def _with_routing(document, block):
    """*document* with its `routing:` mapping replaced by *block* (r2 runs OSPF, no BGP)."""
    start = document.index("\nrouting:\n") + 1
    end = start + len("routing:\n")
    while document[end:end + 2] == "  " or document[end:end + 2] == "- ":
        end = document.index("\n", end) + 1
    return document[:start] + block + document[end:]


class TestEveryKeyIsOneIntentReads:
    """C1183 (the operator, W4 step 48, 2026-10-17): the editor checked interface keys only, so
    a BGP block one level up passed every check and rendered nothing. Every key of a section
    whose keys intent knows is one it reads there; a key read elsewhere is refused naming
    where it belongs, a key read nowhere naming that, each with its line and column."""

    def test_the_w4_misplaced_block_is_refused_naming_routing_asn_s_line(self):
        from modules.nsot import intent_edit
        document = _with_routing(_seeded("r2"), W4_MISPLACED)
        line = document.splitlines().index("  asn: '65099'") + 1
        got = intent_edit.validate("r2", document)
        assert got["ok"] is False and got["stage"] == "schema", got
        assert (got["line"], got["column"]) == (line, 3), got
        assert "routing.asn" in got["error"] and "routing.bgp" in got["error"], got["error"]
        for key in ("settings", "neighbors", "networks", "address_families"):
            assert f"routing.{key}" in got["error"], (key, got["error"])

    def test_the_same_block_where_intent_reads_it_passes(self):
        """The control: the W4 block nested under `bgp`, in the same real document."""
        from modules.nsot import intent_edit
        document = _with_routing(_seeded("r2"), W4_PLACED)
        got = intent_edit.validate("r2", document)
        assert got["ok"] is True, got
        assert got["parsed"]["routing"]["bgp"]["asn"] == "65099"

    @pytest.mark.parametrize("name", sorted(f[:-4] for f in os.listdir(FLEET)
                                            if f.endswith(".cfg")))
    def test_every_real_seeded_document_passes(self, name):
        from modules.nsot import intent_edit
        got = intent_edit.validate(name, _seeded(name))
        assert got["ok"] is True, got

    def test_every_key_path_a_parser_emits_is_declared(self):
        """One producer, read both ways: no key a parser emits on a real capture is refused."""
        problems = [(name, hostvars.unknown_keys(host_vars)) for name, _p, host_vars in _fleet()]
        assert [p for p in problems if p[1]] == [], problems
        assert len(hostvars.INTENT_SECTIONS) >= 20, "a schema this small means the scan is wrong"

    def test_a_key_read_nowhere_is_refused_unless_the_device_s_template_reads_it(self):
        """A key no section knows anywhere (`eigrp`) is allowed only when the device's own
        template names it (a person's template may read a key the shipped one does not, the
        lenient side of config_check's B8); a key the schema reads ELSEWHERE is refused
        whatever the template names."""
        doc = {"hostname": "r9", "interfaces": [],
               "routing": {"eigrp": {"as": 1}, "asn": "65001"}}
        unknown = hostvars.unknown_keys(doc)
        assert [(p, k) for p, k, _w in unknown] == [(("routing",), "eigrp"),
                                                    (("routing",), "asn")], unknown
        assert dict((k, w) for _p, k, w in unknown) == {"asn": ["routing.bgp"], "eigrp": []}
        reads = {"eigrp", "asn"}
        assert [(p, k) for p, k, _w in hostvars.unknown_keys(doc, reads=reads)] == \
            [(("routing",), "asn")]

    def test_a_template_that_cannot_be_read_lets_no_unknown_key_through(self, monkeypatch):
        """The editor's own path: `intent_edit.validate` asks the device's template what it
        reads (`_template_reads`); when that cannot be read (here: its platform cannot be
        resolved), it answers None and no key read nowhere is let through on its word."""
        from modules.nsot import intent_edit

        def unreadable(*_a, **_k):
            raise LookupError("no such network")

        monkeypatch.setattr("routes.templates._platform_for", unreadable)
        assert intent_edit._template_reads("Nowhere", "r9") is None
        text = "hostname: r9\ninterfaces: []\nrouting:\n  eigrp:\n    as: 1\n"
        got = intent_edit.validate("r9", text, list_name="Nowhere")
        assert got["ok"] is False and "eigrp" in got["error"], got

    def test_a_misplaced_key_in_a_list_item_names_its_index(self):
        doc = {"routing": {"bgp": {"asn": "1", "address_families": [
            {"afi": "ipv4", "asn": "2"}]}}}
        assert [(p, k) for p, k, _w in hostvars.unknown_keys(doc)] == \
            [(("routing", "bgp", "address_families", 0), "asn")]
