"""Every secret reference an intent document names is resolved at its deploy (the operator's
r2, 2026-11-01, C2284): an account added under ``users`` alone, its value set by Set value…,
was refused at "program built" as masked content, because hydration resolved only the
``secret_refs`` list while the template asks `secret()` for each ``users[].secret_ref``.

- `hostvars.named_refs` is the one list: ``secret_refs`` with each place the shipped templates
  call `secret()` (a user's, the enable secret's, an SNMP community's, a ``__secret__:`` marker),
  and the templates call it nowhere else, so a new call site fails here until the list learns it.
- Hydration resolves an account named under ``users`` alone, and the deploy render through the
  real template sends its value, never a placeholder.
- The Secret references card reads a value as typed only while a person's set is newer than the
  device's last verified deploy: a seeded value, or a deployed community the device keeps as
  typed, reads as the device's own (the operator's question 2).
- The guard's words say what happened, that nothing was sent and what to do (finding 4a); a
  refused build reads refused, never "nothing to send" (finding 4b).
"""

import os
import re

import pytest

from modules import credentials
from modules.nsot import hostvars

TYPED = "Lab-Not-Real-9"
ADMIN_HASH = "$9$RealHashValue$notregenerable"
COMMUNITY = "Community-Not-Real"
INTENT = {
    "hostname": "edge1",
    "secret_refs": ["snmp_community_ro", "user_admin_secret"],
    "users": [{"name": "admin", "privilege": 15, "secret_kind": "secret",
               "secret_ref": "user_admin_secret"},
              {"name": "lab", "privilege": 15, "secret_kind": "secret",
               "secret_ref": "user_lab_secret"}],
    "snmp": {"communities": [{"ref": "snmp_community_ro", "access": "RO"}]},
}


@pytest.fixture
def store(monkeypatch):
    values = {"net:edge1:user_admin_secret": ADMIN_HASH,
              "net:edge1:user_lab_secret": TYPED,
              "net:edge1:snmp_community_ro": COMMUNITY}
    monkeypatch.setattr(credentials, "get_template_secret", lambda name: values.get(name, ""))
    monkeypatch.setattr("modules.config.list_slug", lambda name: name)
    return values


def test_named_refs_reads_every_place_a_template_asks_for_a_secret():
    doc = dict(INTENT, enable_secret_ref="enable_ref",
               ntp_servers=["__secret__:ntp_key_ref@192.0.2.1"])
    assert hostvars.named_refs(doc) == ["enable_ref", "ntp_key_ref", "snmp_community_ro",
                                        "user_admin_secret", "user_lab_secret"]
    assert hostvars.named_refs({}) == []


def test_the_shipped_templates_call_secret_only_where_named_refs_reads():
    """The shape, not the members: each `secret(<expr>)` in a shipped template is one of the
    three places `named_refs` reads (the marker filter is the fourth). A new call site fails
    here until `named_refs` reads it too."""
    root = os.path.join(os.path.dirname(hostvars.__file__), "templates")
    calls, files = set(), 0
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            if name.endswith(".j2"):
                files += 1
                with open(os.path.join(dirpath, name), encoding="utf-8") as fh:
                    calls |= set(re.findall(r"\bsecret\(([^)]*)\)", fh.read()))
    assert files >= 3, f"the scan read {files} template(s): its floor is 3"
    assert calls == {"u.secret_ref", "v.enable_secret_ref", "c.ref"}, calls


def test_hydration_resolves_an_account_named_under_users_alone(store):
    live = hostvars.hydrate_secrets(INTENT, "edge1", "net")
    assert live["secrets"]["user_lab_secret"] == TYPED
    assert set(live["secrets"]) == {"user_admin_secret", "user_lab_secret", "snmp_community_ro"}


FIXTURES = {"cisco_iosxe": "r1_c8000v.cfg", "cisco_ios": "s1_vios_l2.cfg"}


def _committed(platform: str):
    """A real capture's intent as it is committed (references, no values), the lab account
    then added under ``users`` alone, as Intent › Edit adds it; with the capture's own values
    and the typed one, keyed as the store keys them for device edge1 of network net."""
    from modules.nsot.parsers import get_parser
    from tests.js_source import read_shipped

    capture = read_shipped(os.path.join(os.path.dirname(__file__), "fixtures", "configs",
                                        FIXTURES[platform]))
    parsed = get_parser(platform).parse(capture)
    values = {f"net:edge1:{k}": v for k, v in (parsed.get("secrets") or {}).items()}
    values["net:edge1:user_lab_secret"] = TYPED
    doc = hostvars.from_yaml(hostvars.to_yaml(parsed))
    assert "user_lab_secret" not in (doc.get("secret_refs") or [])
    doc["users"].append({"name": "lab", "privilege": 15, "secret_kind": "secret",
                         "secret_ref": "user_lab_secret"})
    return capture, doc, values


@pytest.mark.parametrize("platform", ["cisco_iosxe", "cisco_ios"])
def test_the_deploy_render_sends_the_account_s_value_never_a_placeholder(monkeypatch, platform):
    from modules.nsot.deploy import render_for_deploy
    from modules.nsot.render_artifact import contains_mask

    _capture, doc, values = _committed(platform)
    monkeypatch.setattr(credentials, "get_template_secret", lambda name: values.get(name, ""))
    monkeypatch.setattr("modules.config.list_slug", lambda name: name)
    config = render_for_deploy(hostvars.hydrate_secrets(doc, "edge1", "net"), platform)
    assert not contains_mask(config), [l for l in config.splitlines() if "missing" in l]
    assert f"username lab privilege 15 secret {TYPED}" in config


def test_the_masked_list_names_every_reference(monkeypatch):
    from modules.nsot.render_artifact import build_artifact

    capture, doc, _values = _committed("cisco_iosxe")
    art = build_artifact("edge1", capture, "cisco_iosxe", host_vars=doc,
                         template="cisco_iosxe/base.j2", template_approved=True)
    assert "user_lab_secret" in art.masked_refs, art.masked_refs
    assert "user_lab_secret" in art.summary()["masked_refs"]


# ── the card's states ───────────────────────────────────────────────────────────────────

@pytest.fixture
def states(monkeypatch):
    from modules.nsot import receipts, secret_refs as SR

    kinds, sets, deploys = {}, [], []
    monkeypatch.setattr(credentials, "template_secret_kind", lambda name: kinds.get(name, ""))
    monkeypatch.setattr("modules.config.list_slug", lambda name: name)
    monkeypatch.setattr(SR, "_repo", lambda list_name: "/nonexistent")
    monkeypatch.setattr(SR, "read_records", lambda repo: {"state": "ok", "rows": list(sets),
                                                          "error": ""})
    monkeypatch.setattr(receipts, "read", lambda list_name, device="", limit=50: {
        "state": "ok", "rows": [r for r in deploys if r["device"] == device]})
    return {"kinds": kinds, "sets": sets, "deploys": deploys, "SR": SR}


def test_a_seeded_plaintext_value_reads_as_the_device_s_own_not_typed(states):
    states["kinds"]["net:edge1:snmp_community_ro"] = "plaintext"
    assert states["SR"]._state("net", "edge1", "snmp_community_ro") == "device_value"
    assert states["SR"].STATES["device_value"] == "the device's value, as it keeps it"


def test_a_person_s_set_is_typed_until_a_verified_deploy_carries_it(states):
    SR = states["SR"]
    states["kinds"]["net:edge1:snmp_community_ro"] = "plaintext"
    states["sets"].append({"at": "2026-11-01T20:36:36Z", "device": "edge1",
                           "ref": "snmp_community_ro", "state": "typed"})
    states["deploys"].append({"device": "edge1", "outcome": "deployed",
                              "completed_at": "2026-11-01T19:00:00Z"})
    assert SR._state("net", "edge1", "snmp_community_ro") == "typed"
    states["deploys"].insert(0, {"device": "edge1", "outcome": "rolled_back",
                                 "completed_at": "2026-11-01T21:00:00Z"})
    assert SR._state("net", "edge1", "snmp_community_ro") == "typed"
    states["deploys"].insert(0, {"device": "edge1", "outcome": "deployed",
                                 "completed_at": "2026-11-01T21:05:00Z"})
    assert SR._state("net", "edge1", "snmp_community_ro") == "device_value"


def test_the_card_lists_every_reference_the_deploy_resolves(monkeypatch):
    from modules.nsot import secret_refs as SR

    doc = dict(INTENT, enable_secret_ref="enable_ref")
    assert set(SR._uses(doc)) == set(hostvars.named_refs(doc))
    assert SR._uses(doc)["snmp_community_ro"].startswith("SNMP community")


# ── a mask named by its reference (C2293) ──────────────────────────────────────────────

def test_a_masked_secret_is_named_by_the_reference_intent_gives_it():
    """C2293 (the operator's finding 6, 2026-11-01: "<redacted:user_password>" named the kind):
    after masking, an account's and the enable secret's masks read their reference; an account
    intent does not name keeps its kind; no value is ever involved."""
    from modules import redact
    from modules.nsot import secret_refs

    lines = ["username lab privilege 15 secret 9 $9$NotRealHash$abc",
             "username guest privilege 1 secret Plain-Not-Real",
             "enable secret 9 $9$AlsoNotReal$def"]
    masked = [redact.redact_text(l) for l in lines]
    assert all("<redacted:" in m for m in masked), masked
    intent = {"users": [{"name": "lab", "secret_ref": "user_lab_secret"}],
              "enable_secret_ref": "enable_ref"}
    named = secret_refs.label_by_ref({"program": {"lines": masked}}, intent)["program"]["lines"]
    assert named[0] == "username lab privilege 15 secret 9 <redacted:user_lab_secret>", named
    assert named[1] == masked[1], "an account intent does not name keeps its kind"
    assert named[2].endswith("<redacted:enable_ref>"), named
    assert secret_refs.label_by_ref(masked, {}) == masked
    assert "NotReal" not in " ".join(named)


# ── the words ───────────────────────────────────────────────────────────────────────────

def test_the_guard_says_what_happened_and_that_nothing_was_sent():
    from modules.nsot.render_artifact import (MaskedContentError, assert_no_mask,
                                              refusal_words)

    with pytest.raises(MaskedContentError) as exc:
        assert_no_mask("username lab privilege 15 secret <missing-secret:user_lab_secret>\n")
    words = str(exc.value)
    assert "no value for user_lab_secret" in words and "Nothing was sent" in words
    assert "Set value" in words and "rendered for preview" not in words
    masked = refusal_words("snmp-server community •••••••• RO\n")
    assert "preview copy" in masked and "fault in Mercury" in masked
    assert "Nothing was sent" in masked


def test_a_refused_build_reads_refused_never_nothing_to_send(monkeypatch):
    from types import SimpleNamespace

    from modules import device_actions

    monkeypatch.setattr(device_actions, "_one_target", lambda preview, host, viewer: {
        "target": {"program": {"lines": [], "none": "Nothing is sent to this device: x"},
                   "operands": []},
        "chosen": {}, "gates": [], "failing": [], "what_not": [], "may": False})
    card = device_actions.deploy_card(
        SimpleNamespace(name="net"), "edge1",
        {"error": "Mercury stopped before the deploy", "deployable": True}, {"confirm": {}},
        {"verified": True})
    assert "refused while building the program" in card["summary"]
    assert "nothing to send" not in card["summary"]
