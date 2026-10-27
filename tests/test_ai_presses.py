"""One press, one provider request (C1854; modules/ai/presses.py, through `gateway.ask`).

The operator's Walk 2 (2026-10-27): s1's pack was explained twice, 12 s apart, both calls
reaching the provider. Every AI call passes through the gateway, so every feature has:

- **a key already seen returns its call:** a retry of a press with the same key, after the call
  ended or while it is in flight, makes no new provider request and returns the call's result,
  its join recorded as a use row ("joined call <id>");
- **the same request in flight is joined:** a double click (two presses, two keys, the same
  feature, subject, data and prompt), or a press after a refresh dropped the first answer,
  makes one provider request between them; both get the one call's result;
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
    headers = {presses.HEADER: key} if key else {}
    with app.test_request_context("/x", method="POST", headers=headers):
        return gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                           actor=actor, send=world.send, today="2026-10-25")


def _uses():
    return [r for rows in calls.uses().values() for r in rows]


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
    (use,) = _uses()
    assert use["use"] == f"joined call {first['call_id']}" and use["actor"] == ACTOR
    assert "key was seen" in use["detail"]
    assert len(calls.read()["rows"]) == 1, "a join is a use row, never a second call"


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


def test_a_key_of_another_shape_is_no_key(world, app):
    world.answer = PING
    for _ in range(2):
        _ask(world, app, key="short")
    assert len(world.sent) == 2


# ------------------------------------------------------------------- the same request in flight

def test_a_double_click_is_one_provider_request(slow, app):
    t1, out1 = _in_thread(lambda: _ask(slow, app, key="a" * 32))
    assert slow.started.wait(10)
    t2, out2 = _in_thread(lambda: _ask(slow, app, key="b" * 32))
    time.sleep(0.4)
    slow.release.set()
    t1.join(10), t2.join(10)
    assert len(slow.sent) == 1
    assert out1["got"]["ok"] and out2["got"]["ok"]
    assert out2["got"]["call_id"] == out1["got"]["call_id"] == out2["got"]["joined"]
    (use,) = _uses()
    assert use["use"] == f"joined call {out1['got']['call_id']}"
    assert "in flight" in use["detail"]


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
    assert "joined" not in second and _uses() == []


def test_a_different_request_in_flight_is_not_joined(slow, app):
    t1, _out = _in_thread(lambda: _ask(slow, app, key="f" * 32))
    assert slow.started.wait(10)

    def other():
        with app.test_request_context("/x", method="POST"):
            return gateway.ask("connection_check", ("ping", 1), connection.Ping,
                               {"word": "another"}, actor=ACTOR, send=slow.send,
                               today="2026-10-25")
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
    gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"}, actor=ACTOR,
                send=keep_body, today="2026-10-25")
    slot = presses._Slot("req-" + presses.request_digest("connection_check", body_seen["body"]))
    slot.claim(1, time.monotonic, time.sleep)
    try:
        monkeypatch.setattr(gateway, "press_wait_s", lambda: 0.3)
        got = gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                          actor=ACTOR, send=world.send, today="2026-10-25")
    finally:
        slot.release()
    assert got["ok"] is False and got["error"] == "in_flight" and world.sent == []
    assert "in flight for over 0 s" in got["detail"] and "nothing was sent" in got["detail"]
    assert calls.read()["rows"][0]["verdict"] == "in_flight", "every refusal is a row"


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
    planted = gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                          actor="alex@example.com", send=keep, today="2026-10-25")
    base = os.path.join(presses._dir(),
                        "req-" + presses.request_digest("connection_check", seen["body"]))
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
