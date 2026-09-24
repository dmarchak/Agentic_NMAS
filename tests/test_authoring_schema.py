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
        action rather than only the absence."""
        _n, _p, host_vars = next(iter(_fleet()))
        document = copy.deepcopy(host_vars)
        del document["logging"]
        with pytest.raises(Exception) as exc:
            roundtrip.render(document, "cisco_iosxe",
                             secret_lookup=lambda _n: "x")
        message = str(exc.value)
        assert "logging" in message
        assert "filled automatically" in message, \
            "the message does not tell the author that omitting is fine"


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
        document = ("hostname: r6\n"
                    "interfaces:\n"
                    "- name: Loopback0\n"
                    "  descripton: branch site identity\n")
        response = client.post("/templatize/committed/r6/preview",
                               json={"yaml": document})
        assert response.status_code == 400
        body = response.get_json()
        assert body["stage"] == "schema"
        assert body["line"] == 4, body
        assert "descripton" in body["error"]
        assert "Omitting a key is fine" in body["error"], \
            "the refusal must separate the harmless case from this one"
