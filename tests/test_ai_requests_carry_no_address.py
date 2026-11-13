"""No person's address or name in what an AI request carries (C3424; the operator, 2026-11-13,
a STOP: "every person is a stable label in every pack (intent, history, approvals,
everywhere)", and "any email address anywhere in the request body becomes a label before it
leaves"). No live AI call: the provider is the `world` fixture's stand-in, which keeps the
exact bytes it was handed.

- **The pack as sent** (`evidence_pack.people_labelled`, through `explain.sent_sections`, the
  one path Explain, the heal analysis and AI troubleshooting send a pack by): an alert's pack
  whose intent was committed by one planted person, whose History holds a golden recorded by
  a second, whose alert carries a Grafana silence created by the first with a comment naming
  the second by address and the first by display name, and whose alert's summary names the
  first, plus a section no builder writes yet with an ``approved_by``: none of the two
  addresses, their local parts or the display name is in the sections sent, each person is
  their label in every section, the same label for the same person; the stored pack keeps the
  identities (the control: the planted values are there to be found).
- **The bytes sent** (`redact.egress_payload`, the safety net): the press, through the real
  gateway, sends none of them; and a request with the addresses in a part no code knows yet,
  in a nested JSON text after an escape, and in a key, sends none of them either, the JSON text
  still JSON; what is no AI request (``people=False``: a notification, a sealed SDN snapshot)
  keeps its people as named.
- **Stable and unrecoverable** (`display_names.label`): two presses give each person the same
  label, which an independent digest of the identity reproduces; a label is ``person-`` and six
  hex digits, with no three characters of the local part or of the domain in it.
- **Who stays the record's:** a hypothesis whose claim names a person by their label is the
  model's naming them, and its ``who`` carries their identity, never the label.
"""
import hashlib
import hmac
import json
import re

import pytest

from modules import display_names
from modules import evidence_pack as EP
from modules.ai import explain, gateway, triggers
from tests.ai_person import pressed_by
from tests.test_ai_explain import _answer, world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture `pack_lab` builds on)
from tests.test_evidence_pack import NOW, V6, _alerts, _section, pack_lab  # noqa: F401

#: Two planted people, at the documentation domains, one written with capitals.
ALICE = "alice.ops@example.com"
BOB = "Bob.Lab@example.org"
#: The first one's display name, set in the store.
ALICE_NAME = "Alice Ops"
NO_TOPOLOGY = {"sent": False, "why": "no network model in the test", "names": {}}


def held(text: str) -> list:
    """Which of the planted values *text* holds: each address, each local part (any case), and
    the display name."""
    low = text.lower()
    out = [a for a in (ALICE, BOB) if a.lower() in low]
    out += [p for p in ("alice.ops", "bob.lab") if p in low]
    return out + ([ALICE_NAME] if ALICE_NAME in text else [])


def _commit_intent_as(repo: str, host: str, actor: str) -> None:
    """*host*'s intent extracted from its committed golden by the real parser and committed by
    the real writer as *actor* (tests/interface_pages.py `_commit_intent`, as another person)."""
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import save_host_vars

    golden = open(f"{repo}/golden/{host}.cfg", encoding="utf-8").read()
    hv = get_parser("cisco_iosxe").parse(golden)
    hv["hostname"] = host
    hostvars.write_committed(repo, hv)
    assert save_host_vars("Lab", [host], actor=actor, source="extraction")["ok"]


@pytest.fixture
def planted(world, monkeypatch, tmp_path):  # noqa: F811
    """`world`'s lab with r1's intent committed by ALICE, a golden of r1 recorded by BOB (both
    by the real writers), ALICE's display name set (the store the test's own), and r1's alert
    built from the captures with its summary naming ALICE and a Grafana silence created by
    ALICE whose comment names BOB by address and ALICE by name (the one edit to the reader's
    value). The pack is recorded, and pressed through `world`'s stand-in provider."""
    from modules.nsot.repo import GoldenItem, save_golden

    monkeypatch.setattr(display_names, "_path", lambda: str(tmp_path / "display_names.json"))
    display_names.set_name(ALICE, ALICE_NAME, by=ALICE, actor_verified="access")
    repo = world.lab["repo"]
    _commit_intent_as(repo, "r1", ALICE)
    body = open(f"{repo}/golden/r1.cfg", encoding="utf-8").read()
    assert save_golden("Lab", [GoldenItem("r1", body + "!\n", V6, platform="cisco_iosxe")],
                       source="capture", actor=BOB, allow_new=True, baseline=False)["ok"]
    inst = EP.firing(_alerts(V6, extra_labels={"summary": f"errors seen by {ALICE}"}))[0]
    inst = dict(inst, silences=[{"id": "s-1", "created_by": ALICE,
                                 "ends_at": "2026-10-15T12:00:00Z",
                                 "comment": f"maintenance; {ALICE_NAME} on call, ask {BOB}",
                                 "unresolved": False}])
    pack = EP.build(inst, store="grafana-alerts", value_at="2026-10-15T08:24:00Z", now=NOW)
    assert EP.record(pack)["ok"]
    world.planted = pack
    return world


def _press(w):
    with pressed_by("operator@example.com"):
        return explain.explain(w.planted["id"], actor="operator@example.com",
                               trigger=triggers.person("operator@example.com"), send=w.send,
                               today="2026-10-25")


def _history(pack, kind, actor):
    return [p for p in _section(pack, "history")["pieces"]
            if p["kind"] == kind and p["who"].lower() == actor.lower()]


# ── the pack as sent ─────────────────────────────────────────────────────────────────────────

def test_the_stored_pack_holds_each_planted_value(planted):
    """The control: the builder's own records carry every planted value (so the tests below
    would see one sent), each person by their identity, as the pack's pages draw them."""
    pack = planted.planted
    assert set(held(json.dumps(pack))) == {ALICE, BOB, "alice.ops", "bob.lab", ALICE_NAME}
    (intent,) = _section(pack, "intent")["pieces"]
    assert intent["intent_commit"]["actor"] == ALICE
    assert _history(pack, "golden", BOB) and _history(pack, "intent", ALICE)
    (alert,) = _section(pack, "alert")["pieces"]
    assert alert["silences"][0]["created_by"] == ALICE


def test_every_person_in_every_section_sent_is_their_label(planted):
    pack = planted.planted
    later = {"ref": "approvals", "name": "approvals", "state": "ok",
             "pieces": [{"ref": "approvals:1", "approved_by": BOB,
                         "words": f"approved by {ALICE_NAME} for {ALICE}"}]}
    sent = explain.sent_sections(dict(pack, sections=pack["sections"] + [later]), NO_TOPOLOGY)
    assert held(json.dumps(sent, ensure_ascii=False)) == []
    a, b = display_names.label(ALICE), display_names.label(BOB)
    assert a != b
    by = {s["name"]: s for s in sent}
    (intent,) = by["intent"]["pieces"]
    assert intent["intent_commit"]["actor"] == a
    (alert,) = by["alert"]["pieces"]
    (silence,) = alert["silences"]
    assert silence["created_by"] == a
    assert silence["comment"] == f"maintenance; {a} on call, ask {b}"
    assert alert["labels"]["summary"] == f"errors seen by {a}"
    hist = {(p["kind"], p["who"]) for p in by["history"]["pieces"]}
    assert ("intent", a) in hist and ("golden", b) in hist
    (approval,) = by["approvals"]["pieces"]
    assert approval == {"ref": "approvals:1", "approved_by": b,
                        "words": f"approved by {a} for {a}"}
    # Applied to what is already labelled, nothing moves; the stored pack is untouched.
    assert EP.people_labelled(sent) == sent
    assert _section(pack, "intent")["pieces"][0]["intent_commit"]["actor"] == ALICE


def test_a_person_who_is_no_address_is_labelled_where_only_a_person_field_names_them():
    """A host login is a person with no "@": named only in the intent commit's `actor`, it is
    found as a person by that field alone, and it leaves as its label (the hand check of
    2026-11-13, mutant E1: `actor` dropped from PERSON_FIELDS survived, the address planted
    elsewhere having been labelled as text)."""
    login = "jsmith"
    sections = [{"ref": "intent", "name": "intent", "state": "ok", "pieces": [
        {"ref": "intent:edge1", "intent_commit": {"sha": "0123456789ab", "actor": login,
                                                  "at": "2026-11-13T06:00:00Z"}}]}]
    sent = EP.people_labelled(sections)
    actor = sent[0]["pieces"][0]["intent_commit"]["actor"]
    assert actor == display_names.label(login) and login not in json.dumps(sent), sent


def test_prompt_v1_s_parts_carry_each_person_as_their_label(planted):
    """Explain's prompt v1 sends its own parts (`explain.v1_parts`), not `sent_sections`: every
    person in them is their label too, a display name no address mask would catch included
    (the hand check of 2026-11-13, mutant X2: v1's parts unlabelled survived)."""
    pack = planted.planted
    later = {"ref": "history", "name": "history", "state": "ok",
             "pieces": [{"ref": "history:9", "kind": "note", "who": ALICE,
                         "what": f"checked by {ALICE_NAME}"}]}
    parts = explain.v1_parts(dict(pack, sections=pack["sections"] + [later]))
    text = json.dumps(parts, ensure_ascii=False)
    assert held(text) == [], held(text)
    assert ALICE_NAME not in text and display_names.label(ALICE) in text


def test_mercury_and_nobody_are_never_labelled():
    sections = [{"name": "history", "pieces": [
        {"ref": "history:1", "who": "mercury"}, {"ref": "history:2", "who": ""},
        {"ref": "history:3", "who": "mercury:heal"},
        {"ref": "history:4", "who": "alex (host login, not a verified identity)"}]}]
    got = [p["who"] for p in EP.people_labelled(sections)[0]["pieces"]]
    assert got == ["mercury", "", "mercury:heal",
                   "alex (host login, not a verified identity)"]
    assert EP.people_labelled([{"name": "history", "pieces": [{"who": "alex"}]}])[0][
        "pieces"][0]["who"] == display_names.label("alex")


# ── the bytes sent ───────────────────────────────────────────────────────────────────────────

def test_the_press_sends_no_planted_value(planted):
    planted.answer = _answer(planted.planted)
    got = _press(planted)
    assert got["ok"] is True, got
    sent = planted.sent[-1]["bytes"]
    assert held(sent) == []
    assert display_names.label(ALICE) in sent and display_names.label(BOB) in sent


def test_an_address_in_a_part_no_code_knows_never_leaves(planted):
    """Through the real `gateway.request_body`: an address in a part no builder writes yet, in
    the context, and in a nested JSON text right after an escape and as one of its keys; the
    JSON text stays JSON, and an address-shaped URL user part and a git remote are kept as
    written."""
    nested = json.dumps({"note": f"line one\n{ALICE}\tthen {BOB}",
                         "deep": [{BOB: "the key is an address"}]})
    parts = {"pack": "[]", "the_alert": "x on r1", "fact_sheet": "",
             "brand_new_field": f"escalate to <{ALICE}>, cc {BOB}.",
             "nested_json": nested,
             "kept": "clone ssh://git@host/repo or git@git.example.org:org/repo"}
    got = gateway.request_body("explain", explain.PROMPT, explain.ExplanationV2, parts,
                               context={"pack_format": f"written by {BOB}"},
                               kind=triggers.PERSON)
    assert "refused" not in got, got.get("refused")
    sent = json.dumps(got["body"])
    assert held(sent) == []
    a, b = display_names.label(ALICE), display_names.label(BOB)
    content = got["body"]["messages"][0]["content"]
    assert f"escalate to <{a}>, cc {b}." in content
    assert f"written by {b}" in got["body"]["system"][-1]["text"]
    assert "ssh://git@host/repo" in content and "git@git.example.org:org/repo" in content
    inner = re.search(r'<data name="nested_json">\n(.*?)\n</data>', content, re.S).group(1)
    assert json.loads(inner) == {"note": f"line one\n{a}\tthen {b}",
                                 "deep": [{b: "the key is an address"}]}


def test_the_safety_net_labels_keys_and_every_depth():
    """`redact.egress_payload` on a payload no builder made: an address as a key, in a list,
    in a tuple, and in a word it only looks like an address inside (left as written)."""
    from modules import redact

    got = redact.egress_payload({BOB: [{"x": (f"to {ALICE}",)}], "y": "seen@ once", "n": 3},
                                {})
    a, b = display_names.label(ALICE), display_names.label(BOB)
    assert got == {b: [{"x": (f"to {a}",)}], "y": "seen@ once", "n": 3}
    # What is no AI request (a notification, a sealed SDN snapshot) keeps its people as named.
    kept = {"by": ALICE, "words": f"sent to {BOB}"}
    assert redact.egress_payload(kept, {}, people=False) == kept


# ── stable and unrecoverable ─────────────────────────────────────────────────────────────────

def test_two_presses_give_each_person_the_same_label(planted):
    planted.answer = _answer(planted.planted)
    assert _press(planted)["ok"] is True
    assert _press(planted)["ok"] is True
    one, two = planted.sent[-2]["bytes"], planted.sent[-1]["bytes"]
    key = display_names._label_key()
    for person in (ALICE, BOB):
        # An independent path: the keyed digest written here (C3426: an HMAC-SHA-256 under the
        # installation's key), not read from the code under test.
        mark = "person-" + hmac.new(key, person.lower().encode("utf-8"),
                                    hashlib.sha256).hexdigest()[:6]
        assert display_names.label(person) == display_names.label(person.upper()) == mark
        assert one.count(mark) == two.count(mark) > 0, person


def test_a_label_is_keyed_two_keys_two_labels():
    """C3426 (the operator, 2026-11-13): "the same address gives different labels under two
    keys": the label is the installation's own, never one the code alone determines."""
    one, two = b"installation-one-key", b"installation-two-key"
    for person in (ALICE, BOB, "jsmith"):
        a, b = display_names.label(person, key=one), display_names.label(person, key=two)
        assert a != b, person
        assert a == display_names.label(person.upper(), key=one), "stable under one key"
        assert display_names.LABEL.fullmatch(a) and display_names.LABEL.fullmatch(b), (a, b)


def test_a_label_cannot_be_recomputed_from_the_code_alone(monkeypatch):
    """C3426: "the label can't be recomputed from the code alone": the installation's key is
    generated on its first label, sealed in the credential store (never kept as plain text),
    kept across reads (one key, so labels stay stable), and the label is neither the unkeyed
    digest the code once used nor a digest under an empty or a guessable key."""
    from modules import secrets_store
    from modules.config import get_user_setting
    # A fresh installation: no key stored, none held by this process.
    monkeypatch.delitem(display_names._LABEL_KEY, "key", raising=False)
    secrets_store.set_secret(display_names.LABEL_KEY_SETTING, "")
    assert get_user_setting(display_names.LABEL_KEY_SETTING, "") == "", "no key before"
    first = display_names.label(ALICE)
    raw = get_user_setting(display_names.LABEL_KEY_SETTING, "")
    assert raw.startswith("enc:v1:"), "the key is sealed in the credential store"
    key = secrets_store.get_secret(display_names.LABEL_KEY_SETTING)
    assert len(key) >= 64 and key not in raw, "a 32-byte key, never stored as plain text"
    # Read again, and after this process forgets it: the same key, the same label.
    monkeypatch.delitem(display_names._LABEL_KEY, "key", raising=False)
    assert display_names.label(ALICE) == first
    assert secrets_store.get_secret(display_names.LABEL_KEY_SETTING) == key
    # What the code alone could compute: none of it is the label.
    ident = ALICE.lower().encode("utf-8")
    guesses = ["person-" + hashlib.sha256(b"person-label:" + ident).hexdigest()[:6],
               "person-" + hashlib.sha256(ident).hexdigest()[:6]]
    guesses += ["person-" + hmac.new(k, ident, hashlib.sha256).hexdigest()[:6]
                for k in (b"", b"person-label:", b"person_label_key", b"mercury")]
    assert first not in guesses, (first, guesses)


@pytest.mark.parametrize("address", [ALICE, BOB, "ab@example.com", "x.y_z@sub.example.org"])
def test_a_label_holds_no_part_of_the_address(address):
    mark = display_names.label(address)
    assert display_names.LABEL.fullmatch(mark), mark
    local, domain = address.lower().split("@")
    tail = mark[len("person-"):]
    for piece in [local] + domain.split("."):
        for i in range(len(piece) - 2):
            assert piece[i:i + 3] not in tail, (piece, mark)
    assert "@" not in mark and "." not in mark


# ── who stays the record's ───────────────────────────────────────────────────────────────────

def test_a_claim_naming_the_label_names_the_person_and_who_keeps_the_identity(planted):
    pack = planted.planted
    (golden,) = _history(pack, "golden", BOB)
    planted.answer = _answer(pack, hypotheses=[{
        "claim": f"{display_names.label(BOB)} recorded the golden before the errors.",
        "evidence_refs": [golden["ref"]], "confirm_with": "show archive log config all"}])
    got = _press(planted)
    assert got["ok"] is True, got
    (h,) = got["answer"]["hypotheses"]
    assert [(w["who"], w["by"]) for w in h["who"]] == [(BOB, "model")]
