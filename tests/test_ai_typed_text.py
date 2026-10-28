"""What a person types or pastes into an AI feature is masked at the gateway before it leaves,
and the person is told what was masked, in words, never the value (C1845; PHASE8_PLAN 18.1 A1
prerequisite (b); the irreversible tier, its hand check in docs/TIER_HAND_CHECK.md).

- **One home:** `gateway.TYPED_PARTS` names every pinned task's typed parts (or none), and a
  task it does not name is refused before anything is built, so no new feature can reach a
  model without saying which of its data a person wrote. Every field each route into the
  gateway reads (found by parsing, tests/test_ai_entry_points.py's population) is declared
  here, typed or not, and each typed one lands in a typed part; a planted field is found.
- **Masked by position and by value**, IPv4 and IPv6 shaped lines alike, through the real
  `ask`: the value is in no byte sent, no row, no result and no log line; the address stays.
  Lines are named when the text has more than one.
- **Nothing to mask, nothing changed:** a question with no secret is sent byte for byte as it
  was before this mask existed, and nothing is said.
- **Mercury's own data untouched:** an Explain call's evidence pack (15.11's classes) is sent
  exactly as the request's one mask makes it, a second pass changing nothing, and the person
  is told nothing of it.
- **Words for every mask:** each of redact's labels has its words here, so a new shape added
  to redact cannot be said as nothing.

Each entry point's own screen (Ask in words on both builders, Change it in words) is held in
its own file: tests/test_ai_nl_query.py, tests/test_ai_nl_logs.py and
tests/test_ai_intent_change.py, `..._is_masked_and_the_person_told`.
"""
import ast
import json
import logging
import os

import pytest

from modules import redact
from modules.ai import anthropic_adapter as A
from modules.ai import calls, connection, explain, gateway, profiles, prompts, triggers
from modules.ai import intent_words  # noqa: F401 (it registers feature 7's schema)
from modules.ai import nl_query  # noqa: F401 (it registers its schemas)
from modules.sdn import closed_loop  # noqa: F401 (it registers sdn_classify's schema)
from tests import test_ai_controls as T
from tests.ai_person import pressed_by
from tests.test_ai_entry_points import entry_points
from tests.test_ai_explain import _answer as _explained
from tests.test_ai_explain import world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)

KEY = "sk-planted-typed-text-0123456789"
ACTOR = "operator@example.com"
PING_OK = {"content": [{"type": "text", "text": '{"echo": "w"}'}], "stop_reason": "end_turn",
           "usage": {"input_tokens": 100, "output_tokens": 10}}


@pytest.fixture
def gw(tmp_path, monkeypatch):
    """Hosted AI allowed, a key set, default caps, the record this test's own; a fake `send`
    keeping the exact bytes it was handed; the connection check's word declared typed, so the
    gateway's own mask is driven through the real `ask`."""
    settings = {"ai_hosted": {"by": ACTOR, "at": "2026-10-28T05:00:00Z",
                              "reason": "the lab's proof of concept"},
                "ai_cap_usd_per_day": 1.50}
    from modules import settings_schema
    monkeypatch.setattr(settings_schema, "get_setting", lambda k, d=None: settings.get(k, d))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    monkeypatch.setitem(gateway.TYPED_PARTS, "connection_check", ("word",))
    sent = []

    def send(body, key):
        sent.append({"bytes": json.dumps(body), "body": body})
        return A.Reply(status=200, body=PING_OK, attempts=1, latency_s=0.2)

    class W:
        pass
    w = W()
    w.sent, w.send, w.record = sent, send, tmp_path / "ai_calls.jsonl"
    return w


def _ask(gw, word, **parts):
    with pressed_by(ACTOR):
        return gateway.ask("connection_check", ("ping", 1), connection.Ping,
                           dict(parts, word=word), actor=ACTOR, trigger=triggers.person(ACTOR),
                           send=gw.send, today="2026-10-28")


def _row():
    (row,) = calls.read()["rows"]
    return row


def _data(body, name):
    """The part *name* exactly as the request carries it."""
    content = body["messages"][0]["content"]
    head = f'<data name="{name}">\n'
    return content.split(head, 1)[1].split("\n</data>", 1)[0]


# ── one home ─────────────────────────────────────────────────────────────────────────────

def test_every_pinned_task_names_its_typed_parts():
    assert set(gateway.TYPED_PARTS) == set(profiles.TASKS), \
        sorted(set(gateway.TYPED_PARTS) ^ set(profiles.TASKS))
    for task, names in gateway.TYPED_PARTS.items():
        assert isinstance(names, tuple) and all(isinstance(n, str) and n for n in names), task
    # The floor: the two features a person types into today.
    assert gateway.TYPED_PARTS["nl_query"] == ("question",)
    assert gateway.TYPED_PARTS["intent_patch"] == ("sentence",)


def test_a_task_naming_no_typed_parts_is_refused_and_nothing_is_sent(gw, monkeypatch):
    monkeypatch.delitem(gateway.TYPED_PARTS, "connection_check")
    got = _ask(gw, "w")
    assert got["ok"] is False and got["error"] == "typed_undeclared", got
    assert "'connection_check' names no typed parts" in got["detail"]
    assert gw.sent == [] and _row()["verdict"] == "typed_undeclared"


# ── masked by position and by value ──────────────────────────────────────────────────────

#: Lines a person might paste, each with the value that must not leave, the address that must,
#: and the words the person is told. IPv4 and IPv6 shaped alike (192.0.2.x, 2001:db8::).
PASTED = [
    ("snmp-server host 192.0.2.10 traps version 2c Wombat77Comm", ["Wombat77Comm"],
     "192.0.2.10", "an SNMP community"),
    ("snmp-server host 2001:db8::10 traps version 2c Wombat77Comm", ["Wombat77Comm"],
     "2001:db8::10", "an SNMP community"),
    ("neighbor 192.0.2.2 password 7 0822455D0A16544541", ["0822455D0A16544541"],
     "192.0.2.2", "a neighbor's password"),
    ("neighbor 2001:db8::2 password 7 0822455D0A16544541", ["0822455D0A16544541"],
     "2001:db8::2", "a neighbor's password"),
    # C745's shapes C1845 measured in clear through the egress mask (2026-10-28).
    ("crypto isakmp key Wallaby3IkeKey address 192.0.2.3", ["Wallaby3IkeKey"], "192.0.2.3",
     "an IKE (ISAKMP) key"),
    ("crypto isakmp key 6 Wallaby3IkeKey address ipv6 2001:db8::3/128", ["Wallaby3IkeKey"],
     "2001:db8::3/128", "an IKE (ISAKMP) key"),
    ("ip ospf authentication-key Wallaby3Ospf", ["Wallaby3Ospf"], None,
     "an OSPF authentication key"),
    (" key 7 0475071A0B", ["0475071A0B"], None, "a server's or group's key"),
    ("standby 1 authentication Wallaby3Hsrp", ["Wallaby3Hsrp"], None,
     "an HSRP, VRRP or GLBP authentication string"),
    ("ntp authentication-key 1 md5 Wallaby3NtpKey", ["Wallaby3NtpKey"], None,
     "an NTP authentication key"),
    ("pre-shared-key address 192.0.2.1 key Kangaroo99Psk", ["Kangaroo99Psk"], "192.0.2.1",
     "a pre-shared key"),
    ("pre-shared-key address 2001:db8::1 key Kangaroo99Psk", ["Kangaroo99Psk"], "2001:db8::1",
     "a pre-shared key"),
    ("username admin privilege 15 algorithm-type scrypt secret 9 $9$PlantedScrypt01$abcdef",
     ["$9$PlantedScrypt01$abcdef"], None, "a user's password"),
    ("enable secret 5 $1$mERr$plantedMd5Crypt.", ["$1$mERr$plantedMd5Crypt."], None,
     "an enable secret"),
    ("key-string 7 Platypus1KeyStr", ["Platypus1KeyStr"], None, "a key string"),
    ("tacacs-server key 7 Platypus1Tacacs", ["Platypus1Tacacs"], None,
     "a TACACS or RADIUS key"),
    ("snmp-server user u g v3 auth sha plantedAuthPass1 priv aes 128 plantedPrivPass1",
     ["plantedAuthPass1", "plantedPrivPass1"], None,
     "an SNMPv3 user's authentication password and an SNMPv3 user's privacy password"),
]


@pytest.mark.parametrize("line,secrets,address,words", PASTED,
                         ids=[p[0][:40] for p in PASTED])
def test_a_pasted_secret_line_is_masked_by_position_and_the_person_told(gw, caplog, line,
                                                                        secrets, address,
                                                                        words):
    gw_word = f"why does {line} fail" if line.startswith(("snmp", "neighbor")) else line
    with caplog.at_level(logging.DEBUG):
        got = _ask(gw, gw_word)
    assert got["ok"] is True, got
    sent = gw.sent[0]["bytes"]
    for secret in secrets:
        assert secret not in sent, secret
    if address:
        assert address in sent, "addresses are never masked"
    n = len(secrets)
    said = f"{n} value{'s' if n > 1 else ''} {'were' if n > 1 else 'was'} masked before sending: "
    assert got["typed_masked"] == {"values": n, "lines": [1], "said": said + words}, got
    row = _row()
    assert row["typed_masked"] == got["typed_masked"]
    kept = {"result": {k: v for k, v in got.items() if k != "output"}, "row": row,
            "file": gw.record.read_text(encoding="utf-8"), "log": caplog.text}
    for secret in secrets:
        for where, text in kept.items():
            assert secret not in (text if isinstance(text, str) else json.dumps(text)), where


@pytest.mark.parametrize("address", ["192.0.2.7", "2001:db8::7"])
def test_a_value_mercury_holds_is_masked_by_value_and_its_label_never_said(gw, monkeypatch,
                                                                           address):
    stored = "PlantedStoredPw9x"
    monkeypatch.setattr(redact, "known_secret_values", lambda: {stored: "Lab:enable"})
    got = _ask(gw, f"logins with {stored} refused from {address} since 09:00")
    sent = gw.sent[0]["bytes"]
    assert stored not in sent and address in sent and "<redacted:Lab:enable>" in sent
    assert got["typed_masked"]["said"] == ("1 value was masked before sending: "
                                           + gateway.BY_VALUE_WORDS)
    assert "Lab:enable" not in got["typed_masked"]["said"], "the store's label is not said"
    assert stored not in json.dumps(_row())


def test_a_call_refused_after_the_mask_still_says_what_was_masked(gw, monkeypatch):
    """Refused at the cap, nothing sent: the person is still told what of their words was
    masked (it is what would have been sent), and the row says it too."""
    monkeypatch.setattr(profiles, "cap_per_call", lambda name: 0.0000001)
    got = _ask(gw, "snmp-server community Wombat77Comm RO")
    assert got["error"] == "over_cap" and gw.sent == []
    said = {"values": 1, "lines": [1],
            "said": "1 value was masked before sending: an SNMP community"}
    assert got["typed_masked"] == said and _row()["typed_masked"] == said
    assert "Wombat77Comm" not in json.dumps(_row())
    # Refused before the caps (the prompt over its bound): told the same.
    bound = profiles.TASKS["connection_check"]["max_prompt_tokens"]
    got = _ask(gw, "snmp-server community Wombat77Comm RO", pack="x" * (bound * 4))
    assert got["error"] == "prompt_too_long" and gw.sent == []
    assert got["typed_masked"] == said


def test_text_of_several_lines_is_said_line_by_line(gw):
    pasted = ("interface GigabitEthernet0/1\n description uplink to 2001:db8::1\n"
              "snmp-server community Wombat77Comm RO\nline vty 0 4\n"
              " password 7 0822455D0A16544541")
    got = _ask(gw, pasted)
    assert got["typed_masked"] == {
        "values": 2, "lines": [3, 5],
        "said": "2 lines were masked before sending: an SNMP community on line 3; "
                "a line password on line 5"}
    sent = _data(gw.sent[0]["body"], "word")
    assert sent.split("\n")[:2] == pasted.split("\n")[:2], "the lines with nothing kept as typed"
    assert "Wombat77Comm" not in sent and "0822455D0A16544541" not in sent


def test_a_mask_the_person_typed_themselves_is_not_said_as_one_made(gw):
    got = _ask(gw, "rows with <redacted:snmp_community> in them, community Wombat77Comm")
    # Only the community after the word "community" is a new mask: no position names it, so
    # nothing is masked and nothing said.
    assert "typed_masked" not in got
    typed = "snmp-server community Wombat77Comm RO, like <redacted:snmp_community>"
    got = _ask(gw, typed)
    assert got["typed_masked"]["values"] == 1


# ── nothing to mask, nothing changed ─────────────────────────────────────────────────────

@pytest.mark.parametrize("word", [
    "input errors per interface on r1 (192.0.2.1), the top 5 since 09:00",
    "OSPF adjacency changes on 2001:db8::1 and fe80::1%Gi0/1, last 7 days",
    "describe GigabitEthernet0/1 as 'uplink to edge1', shut GigabitEthernet0/2"])
def test_a_question_with_nothing_to_mask_is_sent_byte_identical_and_nothing_said(gw, word):
    got = _ask(gw, word)
    assert got["ok"] is True and "typed_masked" not in got
    assert "typed_masked" not in _row()
    body = gw.sent[0]["body"]
    assert _data(body, "word") == word
    # Exactly the request the gateway built before typed text had a mask of its own.
    pin = profiles.TASKS["connection_check"]
    assert body == redact.egress_payload(gateway.build_request(
        prompts.load("ping", 1), connection.Ping, {"word": word}, pin,
        profile=profiles.profile(pin["model"])))


def test_other_parts_are_the_objects_given(gw):
    """`mask_typed` touches only the typed parts: every other part is the very object given
    (the request's own mask is the only one it passes)."""
    pack = {"lines": ["snmp-server community Wombat77Comm RO"]}
    parts = {"word": "snmp-server community Wombat77Comm RO", "pack": pack,
             "help": "enable secret 9 $9$PlantedScryptHashValue01"}
    got = gateway.mask_typed(parts, ("word",), {})
    assert got["parts"]["pack"] is pack and got["parts"]["help"] is parts["help"]
    assert got["parts"]["word"] == "snmp-server community <redacted:snmp_community> RO"
    assert parts["word"] == "snmp-server community Wombat77Comm RO", "the caller's own unchanged"
    assert gateway.mask_typed(parts, (), {}) == {"parts": parts, "masked": []}


# ── Mercury's own data untouched ─────────────────────────────────────────────────────────

def test_an_explain_pack_is_sent_as_the_request_s_one_mask_makes_it_and_nothing_said(
        world, monkeypatch):  # noqa: F811
    """Explain's evidence pack is Mercury's own data (15.11): no typed part. Its call's request
    is exactly `redact.egress_payload` over the request built from the parts Explain handed the
    gateway, those parts the very objects, a second mask changing nothing (never masked into
    nonsense); the pack's planted community is masked once; the person is told nothing."""
    handed, built = [], []
    real_ask, real_build = gateway.ask, gateway.build_request

    def ask(*a, **k):
        handed.append(a[3])
        return real_ask(*a, **k)

    def build(prompt, schema_model, parts, pin, context=None, profile=None):
        built.append((prompt, schema_model, parts, pin, context, profile))
        return real_build(prompt, schema_model, parts, pin, context=context, profile=profile)
    monkeypatch.setattr(gateway, "ask", ask)
    monkeypatch.setattr(gateway, "build_request", build)
    world.answer = _explained(world.pack)
    with pressed_by(ACTOR):
        got = explain.explain(world.pack["id"], actor=ACTOR, trigger=triggers.person(ACTOR),
                              send=world.send, today="2026-10-28")
    assert got["ok"] is True and "typed_masked" not in got
    (parts,) = handed
    (b,) = built
    assert b[2].keys() == parts.keys() and all(b[2][k] is parts[k] for k in parts)
    body = world.sent[0]["body"]
    assert body == redact.egress_payload(real_build(*b[:4], context=b[4], profile=b[5]))
    assert redact.egress_payload(body) == body, "a second mask changes nothing"
    assert "<redacted:snmp_community>" in world.sent[0]["bytes"], "the pack's planted line"
    assert all("typed_masked" not in r for r in calls.read()["rows"])


# ── words for every mask ─────────────────────────────────────────────────────────────────

def test_every_mask_redact_makes_has_its_words():
    labels = {label for label, _p in redact._POSITIONAL} | {label for label, _p in
                                                           redact._EGRESS}
    assert len(labels) >= 15, labels
    assert set(gateway.MASK_WORDS) == labels, sorted(set(gateway.MASK_WORDS) ^ labels)
    assert len(set(gateway.MASK_WORDS.values())) == len(gateway.MASK_WORDS), "each its own"
    assert gateway.BY_VALUE_WORDS not in gateway.MASK_WORDS.values()


def test_the_words_name_kinds_and_lines_never_a_value():
    said = gateway.typed_said([
        {"part": "question", "line": 1, "lines": 1, "labels": ["snmp_community", "x:y"]}])
    assert said == {"values": 2, "lines": [1], "said": "2 values were masked before sending: "
                    "an SNMP community and a credential Mercury holds"}
    said = gateway.typed_said([
        {"part": "a", "line": 2, "lines": 3, "labels": ["egress_hash"]},
        {"part": "b", "line": 1, "lines": 1, "labels": ["sealed"]}])
    assert said["said"] == ("2 lines were masked before sending in the a and b: a password hash "
                            "on line 2 of the a; an encrypted secret on line 1 of the b")
    assert gateway.typed_said([]) == {}


# ── every field a route into the gateway reads ───────────────────────────────────────────

def TYPED(task, part):
    return f"typed: {task}.{part}"


#: Every field each route into the gateway reads from its request (found by `fields`), and
#: what it is. A field a person types into is TYPED, naming the part it lands in; every other
#: is a choice Mercury offered, a token, or a secret that never becomes a part.
FIELDS = {
    "v2.history_ask_metrics_words": {
        "form.words": TYPED("nl_query", "question"),
        "form.tz": "the browser's timezone name (nl_query.zone), never sent",
        "form.tz_off": "the browser's offset in minutes (nl_query.zone), never sent",
        "form.<whole>": "the builder's own choices, redrawn on a refusal (its view)",
        "args.<whole>": "the builder's own choices, read by its view",
        "request.<passed to submitted_list>": "the network's name (routes.list_param)",
        "request.<passed to named_list>": "the network's name (routes.list_param)",
        "request.<passed to _history_filters>": "History's filters, for its page"},
    "v2.history_ask_logs_words": {
        "form.words": TYPED("nl_query", "question"),
        "form.tz": "the browser's timezone name (nl_query.zone), never sent",
        "form.tz_off": "the browser's offset in minutes (nl_query.zone), never sent",
        "form.<whole>": "the builder's own choices, redrawn on a refusal (its view)",
        "args.<whole>": "the builder's own choices, read by its view",
        "request.<passed to submitted_list>": "the network's name (routes.list_param)",
        "request.<passed to named_list>": "the network's name (routes.list_param)",
        "request.<passed to _history_filters>": "History's filters, for its page"},
    "intent_v2.words": {
        "form.words": TYPED("intent_patch", "sentence"),
        # The person's answers to Mercury's own questions continue the sentence as decided.
        "form.answer": TYPED("intent_patch", "sentence"),
        "form.answer_text": TYPED("intent_patch", "sentence"),
        "form.phrase": TYPED("intent_patch", "sentence"),
        "form.ask": "the kind of Mercury's question answered (a token it drew)",
        "form.pick": "a candidate Mercury offered"},
    "v2.monitoring_alert_explain": {"form.again": "a flag: ask again over a kept answer"},
    "sdn_v2.response_classify": {
        "args.<whole>": "the SDN page's own choices",
        "args.run": "a run's id Mercury drew",
        "request.<passed to submitted_list>": "the network's name (routes.list_param)",
        "request.<passed to named_list>": "the network's name (routes.list_param)"},
    "sdn_v2.loop_set": {
        "form.run": "start or stop",
        "form.interval": "the loop's interval in seconds",
        "args.<whole>": "the SDN page's own choices",
        "args.run": "a run's id Mercury drew",
        "request.<passed to submitted_list>": "the network's name (routes.list_param)",
        "request.<passed to named_list>": "the network's name (routes.list_param)"},
    "settings_v2.install_replace": {
        "form.<named at run time>": "a secret's own fields, kept in the secrets store; the "
                                    "connection check it runs sends Mercury's word"},
    "settings_v2.install_test": {},
}

_REQUEST = {"form", "args", "values", "files", "json", "data", "cookies", "headers"}


def _request_attr(node) -> bool:
    return (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id == "request" and node.attr in _REQUEST)


def _reads(fn) -> set:
    """The request fields *fn* reads: ``form.<name>`` for a named get, ``form.<named at run
    time>`` for one named by a variable, ``form.<whole>`` for the mapping handed on, and
    ``request.<passed to f>`` for the request itself handed to *f*."""
    out, named = set(), set()
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("get", "getlist") and _request_attr(node.func.value)):
            named.add(id(node.func.value))
            arg = node.args[0] if node.args else None
            out.add(f"{node.func.value.attr}.{arg.value}"
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    else f"{node.func.value.attr}.<named at run time>")
    for node in ast.walk(fn):
        if _request_attr(node) and id(node) not in named:
            out.add(f"{node.attr}.<whole>")
        if isinstance(node, ast.Call):
            f = node.func
            if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                    and f.value.id == "request" and f.attr == "get_json"):
                out.add("json.<whole>")
            for a in list(node.args) + [k.value for k in node.keywords]:
                if isinstance(a, ast.Name) and a.id == "request":
                    callee = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "?")
                    out.add(f"request.<passed to {callee}>")
    return out


def fields(sources: dict) -> dict:
    """``{endpoint: {field, ...}}``: every route into the gateway (tests/test_ai_entry_points's
    `entry_points`), and the fields read by it and by every function of its module it names,
    followed through."""
    out = {}
    for (mod, name), r in sorted(entry_points(sources).items()):
        if r["endpoint"] is None:
            continue
        tree = ast.parse(sources[mod.replace(".", os.sep) + ".py"])
        funcs = {f.name: f for f in tree.body
                 if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        todo, seen = [name], set()
        while todo:
            n = todo.pop()
            if n in seen:
                continue
            seen.add(n)
            todo += [node.id for node in ast.walk(funcs[n])
                     if isinstance(node, ast.Name) and node.id in funcs]
        out[r["endpoint"]] = set().union(*(_reads(funcs[n]) for n in seen))
    return out


def test_every_field_a_route_into_the_gateway_reads_is_declared():
    found = fields(T._sources())
    assert len(found) >= 8, f"the floor: the eight routes known ({sorted(found)})"
    assert set(found) == set(FIELDS), sorted(set(found) ^ set(FIELDS))
    for endpoint, got in found.items():
        assert got == set(FIELDS[endpoint]), (endpoint, sorted(got ^ set(FIELDS[endpoint])))


def test_every_typed_field_lands_in_a_typed_part_and_every_typed_part_is_reached():
    reached = set()
    for endpoint, declared in FIELDS.items():
        for field, what in declared.items():
            if what.startswith("typed: "):
                task, part = what[len("typed: "):].split(".")
                assert part in gateway.TYPED_PARTS[task], (endpoint, field, what)
                reached.add((task, part))
    assert reached == {(t, p) for t, names in gateway.TYPED_PARTS.items() for p in names}


PLANTED_ROUTE = ("from flask import Blueprint, request\nbp = Blueprint('planted', __name__)\n"
                 "from modules.ai import nl_query\n"
                 "@bp.route('/x', methods=['POST'])\n"
                 "def planted():\n"
                 "    return nl_query.metrics('L', request.form.get('notes'), actor='a')\n")


def test_a_planted_field_in_a_route_into_the_gateway_is_found():
    sources = dict(T._sources(), **{os.path.join("routes", "planted_ai.py"): PLANTED_ROUTE})
    found = fields(sources)
    assert found["planted.planted"] == {"form.notes"}
    sources[os.path.join("routes", "v2.py")] = sources[os.path.join("routes", "v2.py")].replace(
        'request.form.get("words", "")', 'request.form.get("words", "") + '
                                          'request.form.get("pasted", "")')
    assert "form.pasted" in fields(sources)["v2.history_ask_metrics_words"]
