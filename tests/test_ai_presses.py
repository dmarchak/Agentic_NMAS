"""One press, one provider request (C1854; modules/ai/presses.py, through `gateway.ask`).

The operator's Walk 2 (2026-10-27): s1's pack was explained twice, 12 s apart, both calls
reaching the provider. Every AI call passes through the gateway, so every feature has:

- **a key already seen returns its call:** a retry of a press with the same key, after the call
  ended or while it is in flight, makes no new provider request and returns the call's result,
  its join the joiner's own row (verdict ``joined``, cost 0, the call's id); a retry under
  another access scope is refused (``other_scope``), never handed the call;
- **the same request in flight is joined:** a double click (two presses, two keys, the same
  feature, network, subject, data, prompt, model and access scope), or a press after a refresh
  dropped the first answer, makes one provider request between them; both get the one call's
  result; another feature or another access scope with the same bytes is another request;
- **a press after the call ended is a new call** (pressing again is a choice: Explain again);
- **across processes:** a slot another PROCESS holds is waited on and joined (a module-level
  dict would not see it);
- **bounded:** a slot held past the wait is refused (``in_flight``), recorded, nothing sent;
- **one way to the provider:** the adapter's send is reached only from the gateway's spending
  part, and that only through `presses.once` (by parsing), so no feature goes around it.

On tests/test_ai_gateway.py's world (hosted AI allowed, a key, a fake send) with the gateway's
connection check as the feature, and Explain's own world for a second feature.
"""
import ast
import os
import subprocess
import sys
import threading
import time

import pytest

from modules.ai import triggers
from tests.ai_person import pressed_by
from modules.ai import anthropic_adapter as A
from modules.ai import calls, connection, gateway, presses
from tests.test_ai_gateway import KEY, own_record, world  # noqa: F401 (fixtures)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACTOR = "operator@example.com"
PING = {"content": [{"type": "text", "text": '{"echo": "w"}'}], "stop_reason": "end_turn",
        "usage": {"input_tokens": 120, "output_tokens": 8}}


@pytest.fixture
def app():
    import app as APP
    return APP.app


def _ask(world, app, key=None, actor=ACTOR):
    """One press as a route makes it: in a request carrying *key* (or none)."""
    from flask import g

    from modules import identity
    headers = {presses.HEADER: key} if key else {}
    with app.test_request_context("/x", method="POST", headers=headers):
        # The request's verified person, as the gate leaves it: a person trigger inside a
        # request must name the request's own verified actor (C1843).
        g.nmas_identity = identity.Identity(actor=actor, email=actor, kind="person",
                                            verified=True, outcome="ok", peer_trusted=True)
        return gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                           actor=actor, trigger=triggers.person(actor), send=world.send,
                           today="2026-10-25")


def _uses():
    return [r for rows in calls.uses().values() for r in rows]


def _joins():
    """The joiners' own rows in the record of AI calls (verdict ``joined``)."""
    return [r for r in calls.read()["rows"] if r.get("verdict") == calls.JOINED]


def _about(scope=None):
    """The connection check's identity beside its body, as `ask` names it, its scope this
    context's (`identity.access_scope`) unless given."""
    from modules import identity
    from modules.ai import profiles as P
    return {"network": "", "subject": {}, "prompt": "ping.v1",
            "model": P.TASKS["connection_check"]["model"],
            "scope": identity.access_scope() if scope is None else scope}


@pytest.fixture
def slow(world):
    """The world's send held open until `release` is set, counting each request."""
    world.answer = PING
    started, release = threading.Event(), threading.Event()
    real = world.send

    def send(body, key):
        started.set()
        assert release.wait(20), "the test never released the send"
        return real(body, key)
    world.send = send
    world.started, world.release = started, release
    return world


def _in_thread(fn):
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("got", fn()), daemon=True)
    t.start()
    return t, out


# ------------------------------------------------------------------------------- the key

def test_a_retry_with_the_same_key_sends_nothing_and_returns_the_call(world, app):
    world.answer = PING
    first = _ask(world, app, key="k" * 32)
    again = _ask(world, app, key="k" * 32)
    assert first["ok"] and again["ok"] and len(world.sent) == 1
    assert again["call_id"] == first["call_id"] and again["joined"] == first["call_id"]
    assert again["output"].echo == "w"
    (join,) = _joins()
    assert join["joined"] == first["call_id"] and join["actor"] == ACTOR
    assert "key was seen" in join["detail"]
    assert _uses() == [], "the join is the joiner's own row, not a use of the call"


def test_a_retry_with_the_same_key_while_the_first_is_in_flight_waits_and_joins(slow, app):
    t, out = _in_thread(lambda: _ask(slow, app, key="r" * 32))
    assert slow.started.wait(10)
    t2, out2 = _in_thread(lambda: _ask(slow, app, key="r" * 32))
    time.sleep(0.4)
    assert t2.is_alive(), "the retry waits on the call in flight"
    slow.release.set()
    t.join(10), t2.join(10)
    assert len(slow.sent) == 1
    assert out2["got"]["call_id"] == out["got"]["call_id"] and out2["got"]["ok"]


def test_the_same_key_from_another_person_is_not_their_call(world, app):
    world.answer = PING
    _ask(world, app, key="s" * 32, actor="alex@example.com")
    _ask(world, app, key="s" * 32, actor=ACTOR)
    assert len(world.sent) == 2, "a key is a press's, and a press is its person's"


def _verified(actor=ACTOR):
    """The request's verified person, as the gate leaves it (C1843: a person trigger inside a
    request names the request's own verified actor)."""
    from flask import g

    from modules import identity
    g.nmas_identity = identity.Identity(actor=actor, email=actor, kind="person", verified=True,
                                        outcome="ok", peer_trusted=True)


def _ask_word(world, word):
    """One gateway call of the press being served (inside the caller's request)."""
    _verified()
    return gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": word},
                       actor=ACTOR, trigger=triggers.person(ACTOR), send=world.send,
                       today="2026-10-25")


def test_each_call_of_a_press_is_its_own_and_a_retry_joins_each_in_turn(world, app):
    """A press (one request, one key) that makes two gateway calls makes two provider requests,
    neither joining the other; a retry of that press (the same key) joins its first call to
    the first and its second to the second, sending nothing."""
    world.answer = PING
    headers = {presses.HEADER: "n" * 32}
    with app.test_request_context("/x", method="POST", headers=headers):
        first = [_ask_word(world, "one"), _ask_word(world, "two")]
    assert len(world.sent) == 2 and first[0]["call_id"] != first[1]["call_id"]
    assert not any("joined" in got for got in first) and _joins() == []
    with app.test_request_context("/x", method="POST", headers=headers):
        again = [_ask_word(world, "one"), _ask_word(world, "two")]
    assert len(world.sent) == 2
    assert [got["joined"] for got in again] == [got["call_id"] for got in first]


def test_a_joiner_has_its_own_row_costing_nothing_and_the_join_is_logged(world, app, caplog):
    """The joiner's own row in the record of AI calls: its actor, the feature, its subject and
    prompt, verdict ``joined``, cost 0, the joined call's id, why (which call of the press) and
    its access scope, and no request (nothing was sent). The day's spend counts one call and
    its cost; the log names who joined which call and why."""
    import logging
    world.answer = PING
    caplog.set_level(logging.INFO, logger=presses.__name__)
    first = _ask(world, app, key="u" * 32)
    again = _ask(world, app, key="u" * 32)
    why = "the same press sent again: its key was seen (call 1 of the press)"
    (call,) = [r for r in calls.read()["rows"] if r["id"] == first["call_id"]]
    (join,) = _joins()
    with pressed_by(ACTOR):                               # the press's scope: a verified person's
        scope = _about()["scope"]
    assert join == {
        "id": join["id"], "at": join["at"], "feature": "connection_check", "actor": ACTOR,
        "model": call["model"], "prompt": "ping.v1", "schema": call["schema"],
        "subject": {}, "thinking": call["thinking"], "prompt_sha256": call["prompt_sha256"],
        "trigger": call["trigger"],
        # Its own prompt's size, measured before it joined (C1898): the count, as the call's.
        "prompt_tokens": call["prompt_tokens"], "prompt_count": call["prompt_count"],
        "verdict": "joined", "cost_usd": 0.0, "joined": first["call_id"], "scope": scope,
        "detail": f"joined call {first['call_id']}: {why}"}
    assert join["id"] != first["call_id"] and again["recorded"] is True
    spent = calls.spent_usd(call["at"][:10])
    assert spent["calls"] == 1 and spent["usd"] == pytest.approx(first["cost_usd"])
    assert [r.getMessage() for r in caplog.records if r.name == presses.__name__] == [
        f"ai presses: {ACTOR} joined call {first['call_id']} ({why})"]


def test_a_retry_under_another_access_scope_is_refused_and_handed_nothing(world, app,
                                                                         monkeypatch):
    """A press's key sent again under another access scope than its call was made under is
    refused (``other_scope``), recorded naming both scopes, with no answer and nothing sent.
    Under C1843 a person's trigger runs only as the request's verified person, and every
    verified person shares one scope today, so the scope itself is varied here: what the
    comparison reads (`identity.access_scope`) answers another scope on the replay."""
    world.answer = PING
    first = _ask(world, app, key="v" * 32)
    with pressed_by(ACTOR):
        before = _about()["scope"]
    from modules import identity
    after = "service svc; may no gated action"
    monkeypatch.setattr(identity, "access_scope", lambda: after)
    assert after != before
    again = _ask(world, app, key="v" * 32)
    assert len(world.sent) == 1 and "output" not in again and _joins() == []
    assert again["ok"] is False and again["error"] == "other_scope"
    assert again["detail"] == (
        f"this press's key was answered by call {first['call_id']} under the access scope "
        f"{before!r}, and it is sent again under {after!r}: a call is never handed across "
        "access scopes, so nothing was returned and nothing was sent")
    (row,) = [r for r in calls.read()["rows"] if r["verdict"] == "other_scope"]
    assert row["actor"] == ACTOR and row["cost_usd"] == 0.0 and row["detail"] == again["detail"]


@pytest.mark.parametrize("first,second", [
    ({"network": "Lab"}, {"network": "Other"}),
    ({"subject": {"kind": "query", "id": "Lab", "devices": []}},
     {"subject": {"kind": "query", "id": "Lab", "devices": ["r1"]}}),
    ({"prompt": ("ping", 1)}, {"prompt": ("ping", 2)}),
], ids=["network", "subject", "prompt version"])
def test_the_gateway_names_each_part_of_a_request_s_identity(slow, app, monkeypatch, first,
                                                             second):
    """Through `ask`: the same body in flight for another network, another subject, or another
    prompt version with the same text (planted: version 2 loads version 1's file) is another
    request, so each press makes its own call."""
    from modules.ai import prompts
    real = prompts.load
    monkeypatch.setattr(prompts, "load", lambda name, version: real(name, 1))

    def press(kw):
        kw = dict(kw)
        prompt = kw.pop("prompt", ("ping", 1))
        with app.test_request_context("/x", method="POST"):
            _verified()
            return gateway.ask("connection_check", prompt, connection.Ping, {"word": "w"},
                               actor=ACTOR, trigger=triggers.person(ACTOR), send=slow.send,
                               today="2026-10-25", **kw)
    t1, _out1 = _in_thread(lambda: press(first))
    assert slow.started.wait(10)
    t2, _out2 = _in_thread(lambda: press(second))
    time.sleep(0.4)
    slow.release.set()
    t1.join(10), t2.join(10)
    assert len(slow.sent) == 2 and slow.sent[0]["bytes"] == slow.sent[1]["bytes"]
    assert _joins() == []


def test_two_access_scopes_never_join_each_others_call(slow, app, monkeypatch):
    """The same request in flight under another access scope is not joined: each makes its
    own. (Under C1843 every press here is a verified person's, who share one scope today, so
    the second press's scope is varied where the digest reads it, `identity.access_scope`.)"""
    from modules import identity
    t1, out1 = _in_thread(lambda: _ask(slow, app, key="w" * 32))
    assert slow.started.wait(10)
    monkeypatch.setattr(identity, "access_scope", lambda: "service svc; may no gated action")
    t2, out2 = _in_thread(lambda: _ask(slow, app, key="x" * 32))
    time.sleep(0.4)
    slow.release.set()
    t1.join(10), t2.join(10)
    assert len(slow.sent) == 2 and _joins() == []
    assert out1["got"]["call_id"] != out2["got"]["call_id"]


@pytest.mark.parametrize("outcome", ["answered", "answered_wrong", "refused_unsent"])
def test_a_joined_press_gets_exactly_what_the_press_it_joined_got(world, app, outcome):
    """A retry's result is the call's own (`gateway.from_row`): an answer, or a failure's kind,
    words and cost, recorded; a call refused before sending cost nothing, and so does its
    join."""
    if outcome == "answered":
        world.answer = PING
    elif outcome == "answered_wrong":
        world.answer = dict(PING, content=[{"type": "text", "text": '{"other": 1}'}])
    else:
        def down(body, key):
            raise A.Overloaded("HTTP 529 after 3 attempts: busy", status=529, attempts=3)
        world.send = down
    first = _ask(world, app, key="j" * 32)
    again = _ask(world, app, key="j" * 32)
    assert first["ok"] is (outcome == "answered")
    if outcome == "refused_unsent":
        assert "cost_usd" not in first, "a refusal says no cost: its join says 0"
        first = dict(first, cost_usd=0.0)
    else:
        assert first["cost_usd"] > 0
    assert first["recorded"] is True
    assert again == dict(first, joined=first["call_id"])


def test_a_key_of_another_shape_is_no_key(world, app):
    world.answer = PING
    for _ in range(2):
        _ask(world, app, key="short")
    assert len(world.sent) == 2


# ------------------------------------------------------------------- the same request in flight

def test_a_double_click_is_one_provider_request(slow, app, caplog):
    """Two presses (two keys) of one request in flight make one provider request; the second
    is a join, its own row saying why, and the log naming who joined which call."""
    import logging
    caplog.set_level(logging.INFO, logger=presses.__name__)
    t1, out1 = _in_thread(lambda: _ask(slow, app, key="a" * 32))
    assert slow.started.wait(10)
    t2, out2 = _in_thread(lambda: _ask(slow, app, key="b" * 32))
    time.sleep(0.4)
    slow.release.set()
    t1.join(10), t2.join(10)
    assert len(slow.sent) == 1
    assert out1["got"]["ok"] and out2["got"]["ok"]
    assert out2["got"]["call_id"] == out1["got"]["call_id"] == out2["got"]["joined"]
    (join,) = _joins()
    why = ("the same request was in flight: connection_check, the same network, subject, "
           "data, prompt, model and access scope")
    assert join["detail"] == f"joined call {out1['got']['call_id']}: {why}"
    assert [r.getMessage() for r in caplog.records if r.name == presses.__name__] == [
        f"ai presses: {ACTOR} joined call {out1['got']['call_id']} ({why})"]


def test_a_press_that_joined_a_call_in_flight_is_that_call_when_its_key_is_sent_again(slow, app):
    """A double click's second press joined the first's call; its own key sent again (a
    retry) returns that same call, sending nothing, rather than making one."""
    t1, out1 = _in_thread(lambda: _ask(slow, app, key="x" * 32))
    assert slow.started.wait(10)
    t2, out2 = _in_thread(lambda: _ask(slow, app, key="y" * 32))
    time.sleep(0.4)
    slow.release.set()
    t1.join(10), t2.join(10)
    assert out2["got"]["joined"] == out1["got"]["call_id"]
    again = _ask(slow, app, key="y" * 32)
    assert len(slow.sent) == 1 and again["joined"] == out1["got"]["call_id"]


def test_a_key_seen_by_a_release_that_recorded_no_scope_is_refused(world, app):
    """A key's marker an earlier release wrote (a finished call, no scope recorded) is not
    handed across: the retry is refused, saying the scope was not recorded."""
    world.answer = PING
    first = _ask(world, app, key="o" * 32)
    with app.test_request_context("/x", method="POST", headers={presses.HEADER: "o" * 32}):
        slot = presses._Slot(presses.current_press(ACTOR)["slot"])
        scope = _about()["scope"]
    slot.mark(state="done", call_id=first["call_id"])
    again = _ask(world, app, key="o" * 32)
    assert again["error"] == "other_scope" and len(world.sent) == 1
    assert f"under the access scope 'not recorded', and it is sent again under {scope!r}" \
        in again["detail"]


def test_a_press_after_a_refresh_mid_call_joins_it(slow, app):
    """The page reloaded while the call ran (its answer had nowhere to land), and the person
    pressed again: a new key, no key at all (a form posted without the script), the same
    request: one provider request."""
    t1, out1 = _in_thread(lambda: _ask(slow, app, key="c" * 32))
    assert slow.started.wait(10)
    t2, out2 = _in_thread(lambda: _ask(slow, app, key=None))
    time.sleep(0.4)
    slow.release.set()
    t1.join(10), t2.join(10)
    assert len(slow.sent) == 1 and out2["got"]["call_id"] == out1["got"]["call_id"]


def test_a_press_after_the_call_ended_is_a_new_call(world, app):
    world.answer = PING
    first = _ask(world, app, key="d" * 32)
    second = _ask(world, app, key="e" * 32)
    assert len(world.sent) == 2 and second["call_id"] != first["call_id"]
    assert "joined" not in second and _joins() == []


def test_a_different_request_in_flight_is_not_joined(slow, app):
    t1, _out = _in_thread(lambda: _ask(slow, app, key="f" * 32))
    assert slow.started.wait(10)

    def other():
        from flask import g

        from modules import identity
        with app.test_request_context("/x", method="POST"):
            g.nmas_identity = identity.Identity(actor=ACTOR, email=ACTOR, kind="person",
                                                verified=True, outcome="ok", peer_trusted=True)
            return gateway.ask("connection_check", ("ping", 1), connection.Ping,
                               {"word": "another"}, actor=ACTOR, trigger=triggers.person(ACTOR),
                               send=slow.send, today="2026-10-25")
    t2, _out2 = _in_thread(other)
    time.sleep(0.4)
    slow.release.set()
    t1.join(10), t2.join(10)
    assert len(slow.sent) == 2


def test_a_slot_held_past_the_wait_is_refused_recorded_and_sends_nothing(world, monkeypatch):
    """A holder that never lets go: the press waits its bound, then is refused, naming it."""
    world.answer = PING
    body_seen = {}

    def keep_body(body, key):
        body_seen["body"] = body
        return A.Reply(status=200, body=PING, attempts=1, latency_s=0.1)
    with pressed_by(ACTOR):
        gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"}, actor=ACTOR,
                    trigger=triggers.person(ACTOR),
                    send=keep_body, today="2026-10-25")
        about = _about()                                  # the press's scope: a verified person's
    slot = presses._Slot("req-" + presses.request_digest("connection_check", body_seen["body"],
                                                         about))
    slot.claim(1, time.monotonic, time.sleep)
    try:
        monkeypatch.setattr(gateway, "press_wait_s", lambda: 0.3)
        with pressed_by(ACTOR):
            got = gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                              actor=ACTOR,
                              trigger=triggers.person(ACTOR), send=world.send, today="2026-10-25")
    finally:
        slot.release()
    assert got["ok"] is False and got["error"] == "in_flight" and world.sent == []
    assert got["detail"] == (f"an identical connection_check call has been in flight for over "
                             f"0 s (slot {slot.name[:16]}…), the most one call can take; "
                             "nothing was sent")
    assert calls.read()["rows"][0]["verdict"] == "in_flight", "every refusal is a row"


def _hold(feature, body, about):
    slot = presses._Slot("req-" + presses.request_digest(feature, body, about))
    slot.claim(1, time.monotonic, time.sleep)
    return slot


BODY = {"model": "m", "messages": [{"role": "user", "content": "the same"}]}
ABOUT = {"network": "Lab", "subject": {"kind": "alert", "id": "p1", "devices": ["r1"]},
         "prompt": "explain.v6", "model": "m", "scope": "person; may reveal"}


@pytest.mark.parametrize("held_feature,held_about", [
    ("explain", ABOUT),
    ("connection_check", dict(ABOUT, network="Other")),
    ("connection_check", dict(ABOUT, subject=dict(ABOUT["subject"], id="p2"))),
    ("connection_check", dict(ABOUT, prompt="explain.v5")),
    ("connection_check", dict(ABOUT, model="m2")),
    ("connection_check", dict(ABOUT, scope="unverified; may no gated action")),
], ids=["feature", "network", "subject", "prompt", "model", "scope"])
def test_the_same_bytes_under_another_identity_are_never_joined(held_feature, held_about):
    """The same masked body in flight under another feature, network, subject, prompt
    version, model or access scope is another request: this press makes its own call (each
    feature's caps and record its own, and no answer handed across networks or scopes)."""
    held = _hold(held_feature, BODY, held_about)
    made = []
    try:
        got = presses.once("connection_check", BODY, about=ABOUT, actor=ACTOR,
                           make=lambda: made.append(1) or {"ok": True, "call_id": "ai-own"},
                           rebuild=pytest.fail, refuse=lambda *a: pytest.fail(f"refused {a}"),
                           wait_s=0.3)
    finally:
        held.release()
    assert made == [1] and got == {"ok": True, "call_id": "ai-own"}


def test_the_same_identity_in_flight_is_waited_on(monkeypatch):
    """The control beside the cases above: the same feature, identity and body held is the
    same request (the press waits on it, here past its bound: refused, nothing made)."""
    held = _hold("connection_check", BODY, dict(ABOUT))
    try:
        got = presses.once("connection_check", BODY, about=dict(ABOUT), actor=ACTOR,
                           make=pytest.fail, rebuild=pytest.fail,
                           refuse=lambda kind, detail: {"refused": kind}, wait_s=0.3)
    finally:
        held.release()
    assert got == {"refused": "in_flight"}


@pytest.mark.parametrize("about,given", [
    ({k: "" for k in presses.IDENTITY if k != "scope"}, "model, network, prompt, subject"),
    (dict({k: "" for k in presses.IDENTITY}, extra=""),
     "extra, model, network, prompt, scope, subject"),
    ({}, "none")], ids=["missing", "extra", "empty"])
def test_a_request_s_identity_names_exactly_its_parts(about, given):
    """No caller leaves a part of the identity out, or adds one the digest would not say; the
    refusal names both the parts and what was given."""
    with pytest.raises(ValueError) as got:
        presses.request_digest("explain", BODY, about)
    assert str(got.value) == ("a request's identity names network, subject, prompt, model, "
                              f"scope; given {given}")


def test_a_request_holding_text_that_cannot_be_utf8_has_an_identity(world, app):
    """A lone surrogate in a call's data or its subject (JSON allows one escaped) is digested
    as the adapter sends it (ASCII-escaped), so the call is made, as it was before presses,
    never a crash."""
    world.answer = PING
    with app.test_request_context("/x", method="POST"):
        _verified()
        got = gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w\udcff"},
                          actor=ACTOR, trigger=triggers.person(ACTOR), send=world.send,
                          today="2026-10-25",
                          subject={"kind": "query", "id": "Lab\udcff", "devices": []})
    assert got["ok"] and len(world.sent) == 1


def test_the_same_request_with_its_keys_in_another_order_is_one_request():
    """Equal requests are one request whatever order their dicts were built in (another
    caller, another worker): the identity is the content, not the insertion order."""
    one = {"model": "m", "max_tokens": 64,
           "messages": [{"role": "user", "content": "x"}], "system": [{"type": "text",
                                                                        "text": "p"}]}
    other = {"system": [{"text": "p", "type": "text"}], "messages": [{"content": "x",
                                                                       "role": "user"}],
             "max_tokens": 64, "model": "m"}
    assert one == other and list(one) != list(other)
    about = dict(ABOUT)
    reordered = dict(reversed(list(ABOUT.items())), subject=dict(
        reversed(list(ABOUT["subject"].items()))))
    assert about == reordered and list(about) != list(reordered)
    assert presses.request_digest("explain", one, about) == \
        presses.request_digest("explain", other, reordered)


def test_the_wait_is_the_adapters_worst_case_and_its_margin():
    """The adapter's bounds as measured into its constants (65 s an attempt, three attempts,
    20 s between two), and the margin."""
    worst = (A.TIMEOUT[0] + A.TIMEOUT[1]) * (A.MAX_RETRIES + 1) + A.MAX_WAIT_S * A.MAX_RETRIES
    assert worst == 235.0 and gateway.press_wait_s() == worst + gateway.PRESS_MARGIN_S == 250.0


# --------------------------------------------------------------------------- across processes

HOLDER = r"""
import fcntl, json, os, sys, time
base, call_id, go = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(os.path.dirname(base), exist_ok=True)
fd = os.open(base + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
open(base + ".json", "w").write(json.dumps({"state": "running"}))
print("held", flush=True)
for _ in range(200):
    if os.path.exists(go):
        break
    time.sleep(0.05)
open(base + ".json", "w").write(json.dumps({"state": "done", "call_id": call_id}))
fcntl.flock(fd, fcntl.LOCK_UN)
"""


def test_a_call_another_process_holds_is_joined(world, app, tmp_path):
    """Another worker process holds the identical request's slot (it is sending): this press
    waits, then joins the call that process recorded, sending nothing."""
    world.answer = PING
    seen = {}

    def keep(body, key):
        seen["body"] = body
        return A.Reply(status=200, body=PING, attempts=1, latency_s=0.1)
    with pressed_by("alex@example.com"):
        planted = gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                              actor="alex@example.com",
                              trigger=triggers.person("alex@example.com"),
                              send=keep, today="2026-10-25")
        about = _about()                                  # the press's scope: a verified person's
    base = os.path.join(presses._dir(),
                        "req-" + presses.request_digest("connection_check", seen["body"], about))
    go = str(tmp_path / "go")
    child = subprocess.Popen([sys.executable, "-c", HOLDER, base, planted["call_id"], go],
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        t, out = _in_thread(lambda: _ask(world, app, key="g" * 32))
        time.sleep(0.4)
        assert t.is_alive(), "the press waits on the other process's call"
        open(go, "w").close()
        t.join(10)
    finally:
        child.wait(10)
    assert world.sent == [] and out["got"]["call_id"] == planted["call_id"]
    assert out["got"]["joined"] == planted["call_id"]


DIED = r"""
import fcntl, json, os, sys, time
base, go = sys.argv[1], sys.argv[2]
os.makedirs(os.path.dirname(base), exist_ok=True)
fd = os.open(base + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
open(base + ".json", "w").write(json.dumps({"state": "running"}))
print("held", flush=True)
for _ in range(200):
    if os.path.exists(go):
        break
    time.sleep(0.05)
os._exit(1)
"""


def test_a_holder_that_dies_mid_call_leaves_the_waiter_to_make_its_own(world, app, tmp_path,
                                                                     caplog):
    """Another process holding the identical request's slot dies mid-call (its lock released
    with it, its marker still running): the waiting press makes its own call, joining
    nothing and warning of no call to join."""
    import logging
    world.answer = PING
    caplog.set_level(logging.INFO, logger=presses.__name__)
    seen = {}

    def keep(body, key):
        seen["body"] = body
        return A.Reply(status=200, body=PING, attempts=1, latency_s=0.1)
    with app.test_request_context("/x", method="POST"):
        _verified("alex@example.com")
        gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                    actor="alex@example.com", trigger=triggers.person("alex@example.com"),
                    send=keep, today="2026-10-25")
        about = _about()
    base = os.path.join(presses._dir(),
                        "req-" + presses.request_digest("connection_check", seen["body"], about))
    go = str(tmp_path / "go")
    child = subprocess.Popen([sys.executable, "-c", DIED, base, go], stdout=subprocess.PIPE,
                             text=True)
    try:
        assert child.stdout.readline().strip() == "held"
        t, out = _in_thread(lambda: _ask(world, app, key="z" * 32))
        time.sleep(0.4)
        assert t.is_alive(), "the press waits on the other process's call"
        open(go, "w").close()
        t.join(10)
    finally:
        child.wait(10)
    assert len(world.sent) == 1 and out["got"]["ok"] and "joined" not in out["got"]
    assert _joins() == []
    assert [r.getMessage() for r in caplog.records if r.name == presses.__name__] == []


# ------------------------------------------------------------------------ the access scope

ALL = "reveal, approve, confirm, publish_remote, configure, break_glass"


def _scope_as(app, monkeypatch, ident):
    from modules import identity
    monkeypatch.setattr(identity, "identify", lambda _request: ident)
    with app.test_request_context("/x"):
        return identity.access_scope()


def test_the_access_scope_is_who_may_sees_and_what_it_allows(world, app, monkeypatch):
    """`identity.access_scope` in words, `may`'s answer over `GATED_ACTIONS` in order: a
    verified person may every gated action; a service, by its label, none (a person is
    required); a requester no assertion verified, none; an identity of no kind, a person."""
    from modules import identity
    seen = dict(email=ACTOR, verified=True, outcome="ok", peer="198.51.100.7",
                peer_trusted=True, header_present=True)
    person = identity.Identity(actor=ACTOR, kind="person", **seen)
    service = identity.Identity(actor="service:svc", kind="service", service_id="svc", **seen)
    kindless = identity.Identity(actor=ACTOR, kind="", **seen)
    assert _scope_as(app, monkeypatch, person) == f"person; may {ALL}"
    assert _scope_as(app, monkeypatch, kindless) == f"person; may {ALL}"
    assert _scope_as(app, monkeypatch, service) == \
        f"service {identity.service_label('svc')}; may no gated action"
    assert _scope_as(app, monkeypatch, identity.Identity()) == "unverified; may no gated action"


def test_an_unverified_scope_names_the_actions_its_gates_leave_open(world, app):
    """Outside a request (a script, no identity carried) the requester is unverified, and the
    scope names each action whose gate an admin opened to anyone (here reveal), by `may`."""
    from modules import identity
    assert identity.access_scope() == "unverified; may no gated action"
    world.settings["require_identity_for_reveal"] = False
    assert identity.access_scope() == "unverified; may reveal"


def test_a_job_s_scope_is_the_person_it_carries(world):
    """Outside a request, a job a verified person's request started (`carried`) has that
    person's scope, not an unverified one."""
    from modules import identity
    person = identity.Identity(actor=ACTOR, email=ACTOR, kind="person", verified=True,
                               outcome="ok", peer="198.51.100.7", peer_trusted=True,
                               header_present=True)
    with identity.carried(person):
        assert identity.access_scope() == f"person; may {ALL}"


# ------------------------------------------------------------------- the slots and the record

def test_pruning_removes_exactly_the_slot_files_older_than_keep_s(monkeypatch):
    """A file older than `KEEP_S` goes, one exactly `KEEP_S` old and a recent one stay, and a
    file whose age cannot be read is passed over without stopping the rest."""
    folder = presses._dir()
    os.makedirs(folder)
    now = 1_800_000_000.0
    ages = {"key-old.json": presses.KEEP_S + 1, "key-at-bound.json": presses.KEEP_S,
            "req-recent.lock": 10}
    for name, age in ages.items():
        path = os.path.join(folder, name)
        open(path, "w").close()
        os.utime(path, (now - age, now - age))
    os.symlink(os.path.join(folder, "nowhere"), os.path.join(folder, "0-unreadable"))
    listdir = os.listdir
    monkeypatch.setattr(presses.os, "listdir", lambda p: sorted(listdir(p)))   # its order fixed
    presses._prune(now)
    assert sorted(listdir(folder)) == ["0-unreadable", "key-at-bound.json", "req-recent.lock"]


@pytest.mark.parametrize("marker", [None, {}, {"state": "running"}, {"state": "done"},
                                    {"state": "done", "call_id": 7},
                                    {"state": "running", "call_id": "ai-1"}])
def test_a_marker_naming_no_finished_call_names_none(marker):
    """Only a finished call with a string id is a call to join; anything else is none (falsy),
    so the press makes its own without looking one up."""
    assert not presses._done_call(marker)


def test_a_finished_marker_names_its_call():
    """The planted case beside the cases above: a finished call's marker gives its id."""
    assert presses._done_call({"state": "done", "call_id": "ai-1"}) == "ai-1"


def test_a_call_the_record_cannot_give_is_not_joined_and_the_log_says_why(caplog):
    """`_join` of a call not in the record, or with the record unreadable, returns None (the
    press makes its own call), records no use, and logs the call and the record's answer."""
    import logging
    caplog.set_level(logging.WARNING, logger=presses.__name__)
    assert presses._join("ai-gone", pytest.fail, ACTOR, "a reason") is None
    assert _uses() == []
    os.makedirs(calls._path())                                  # the record unreadable
    error = calls.find("ai-gone")["error"]
    assert error.startswith("IsADirectoryError")
    assert presses._join("ai-gone", pytest.fail, ACTOR, "a reason") is None
    made = "; a new call is made"
    assert [r.getMessage() for r in caplog.records if r.name == presses.__name__] == [
        f"ai presses: the call ai-gone to join is not in the record (absent){made}",
        f"ai presses: the call ai-gone to join is not in the record ({error}){made}"]


# --------------------------------------------------------------------------- every feature
#
# Explain, through its route, is tests/test_explain_kept.py's (`TestOnePress`).

def _own_nodes(func):
    """The nodes of *func*'s body, not those of a function defined inside it."""
    stack = list(func.body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))


def _refs_in(func, name: str, attr: str) -> bool:
    return any(isinstance(n, ast.Attribute) and n.attr == attr
               and isinstance(n.value, ast.Name) and n.value.id == name
               for n in ast.walk(func))


def test_the_providers_send_is_reached_only_through_once():
    """By parsing: the adapter's `send` is named in modules/ only by the gateway's spending
    part, and that part is called only by the function `ask` hands `presses.once`."""
    from tests.source_index import tracked
    users = []
    for p in tracked("modules", suffix=".py"):
        with open(p, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and _refs_in(node, "anthropic_adapter", "send"):
                users.append((os.path.relpath(p, ROOT), node.name))
    assert users == [(os.path.join("modules", "ai", "gateway.py"), "_capped_send")], users
    with open(os.path.join(ROOT, "modules", "ai", "gateway.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    callers = sorted({f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                      for n in _own_nodes(f) if isinstance(n, ast.Call)
                      and getattr(n.func, "id", "") == "_capped_send"})
    assert callers == ["spend"], callers
    ask = next(f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == "ask")
    once = [n for n in ast.walk(ask) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "once"]
    assert len(once) == 1 and any(k.arg == "make" and getattr(k.value, "id", "") == "spend"
                                  for k in once[0].keywords)
