"""The AI caps reserved atomically (C2039; the operator's decision of 2026-10-28;
`modules/ai/reservations.py`, `gateway._capped_send`).

Before it, the gateway read today's spend and compared it plus a call's worst case with each
cap, then sent, with no lock: two calls at once each passed against the same spend and together
passed the cap. Now each call's worst case is reserved under one cross-process lock before it
is sent, and settled once its row is recorded:

- **two calls at once** whose worst cases together pass the day cap, each alone under it:
  exactly one is sent, the other refused before any provider request, its words naming the
  spend, what is reserved in flight, its worst case and the cap; threads, and a second PROCESS
  holding the store's lock (the refused call waits for it, then reads what it reserved);
- **a background feature's** own day cap counts its calls in flight on its network, and only
  those;
- **settled to the actual cost** whatever the outcome: an answer (the reservation was the
  worst case while in flight, gone after, the day's spend the actual cost), a provider failure,
  an answer that is not the schema, and an exception (its row counts the worst case, said);
- **a reservation left by a process that died** expires after `gateway.reservation_ttl_s`
  (2.5 times the adapter's own bound on one call), and is dropped, logged; one not yet expired
  is held against the cap;
- **an unreadable store refuses** the call (fail closed, said, nothing sent), never read as
  nothing reserved, until it is older than a reservation lives, when it is kept aside and
  replaced;
- the store is owner-only.

On tests/test_ai_gateway.py's world (hosted AI allowed, a key, a fake send) and
tests/test_ai_background.py's for the background feature.
"""
import json
import os
import stat
import subprocess
import sys
import threading
import time

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, connection, gateway, reservations, triggers
from tests.ai_person import pressed_by
from tests.test_ai_background import bg  # noqa: F401 (the fixture)
from tests.test_ai_gateway import KEY, own_record, world  # noqa: F401 (fixtures)

ACTOR = "operator@example.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PING = {"content": [{"type": "text", "text": '{"echo": "w"}'}], "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 5}}


def _ask(world, word="w", send=None):
    world.answer = world.answer or PING
    with pressed_by(ACTOR):
        return gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": word},
                           actor=ACTOR, trigger=triggers.person(ACTOR),
                           send=send or world.send, today="2026-10-25")


def _worst(world, word="w"):
    """The worst case `ask` reserves for the call with *word*: its request's counted tokens
    (the tests' typical count) as cache writes, plus all of max_tokens."""
    seen = {}

    def keep(body, key):
        seen["body"] = body
        return A.Reply(status=200, body=PING, attempts=1, latency_s=0.01)
    _ask(world, word, send=keep)
    open(calls._path(), "w").close()                      # nothing spent by the measurement
    body = seen["body"]
    return gateway.worst_case_usd(body["model"], body, A.count_tokens(body, KEY).tokens)


def _in_thread(fn):
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("got", fn()), daemon=True)
    t.start()
    return t, out


def _store():
    return reservations._path()


# ── two calls at once ─────────────────────────────────────────────────────────────────────

def test_two_calls_at_once_cannot_pass_the_day_cap_together(world):
    """The first call is in flight (its send held open) when the second is judged: each alone
    fits the day cap, both would pass it, so the second is refused before any provider request,
    naming what the first reserved. The first, released, is sent and recorded; nothing is left
    reserved."""
    worst = _worst(world, "a")
    assert _worst(world, "b") == pytest.approx(worst), "the two calls cost the same"
    world.settings["ai_cap_usd_per_day"] = worst * 1.5
    inside, release, sent = threading.Event(), threading.Event(), []

    def slow(body, key):
        sent.append(body)
        inside.set()
        assert release.wait(10)
        return A.Reply(status=200, body=PING, attempts=1, latency_s=0.01)
    t, first = _in_thread(lambda: _ask(world, "a", send=slow))
    assert inside.wait(10), "the first call reached its send"
    held = reservations.open_reservations()["held"]
    assert len(held) == 1 and next(iter(held.values()))["usd"] == pytest.approx(worst)
    second = _ask(world, "b", send=slow)
    release.set()
    t.join(10)
    assert first["got"]["ok"] is True and len(sent) == 1, "only the first reached the provider"
    assert second["ok"] is False and second["error"] == "over_cap"
    assert second["detail"] == (
        f"today's spend $0.0000 plus ${worst:.4f} reserved by 1 call(s) in flight plus this "
        f"call's worst case ${worst:.4f} is over the day cap ${worst * 1.5:.4f}")
    assert reservations.open_reservations()["held"] == {}, "the first was settled"


def test_without_one_in_flight_the_same_two_calls_are_both_sent(world):
    """The control for the test above: the same cap, one after the other (the first settled
    to its actual cost, far under its worst case), both are sent."""
    worst = _worst(world, "a")
    world.settings["ai_cap_usd_per_day"] = worst * 1.5
    assert _ask(world, "a", send=lambda b, k: A.Reply(200, PING))["ok"] is True
    assert _ask(world, "b", send=lambda b, k: A.Reply(200, PING))["ok"] is True


HOLDER = r"""
import fcntl, json, os, sys, time
store, usd, go = sys.argv[1], float(sys.argv[2]), sys.argv[3]
fd = os.open(store + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
print("locked", flush=True)
for _ in range(200):
    if os.path.exists(go):
        break
    time.sleep(0.05)
now = time.time()
with open(store, "w") as fh:
    json.dump({"held": {"ai-otherprocess0001": {
        "usd": usd, "feature": "explain", "network": "", "background": False,
        "day": "2026-10-25", "month": "2026-10", "at": "2026-10-25T00:00:00Z",
        "expires_at": now + 600, "pid": os.getpid()}}}, fh)
fcntl.flock(fd, fcntl.LOCK_UN)
"""


def test_a_reservation_another_process_makes_under_the_lock_is_waited_for_and_counted(
        world, tmp_path):
    """Another worker PROCESS holds the reservations' lock (it is reserving): this call waits
    on it, sends nothing meanwhile, then reads what that process reserved and is refused on
    it. A lock or a list held per process would not see it."""
    worst = _worst(world)
    world.settings["ai_cap_usd_per_day"] = worst * 1.5
    go = str(tmp_path / "go")
    child = subprocess.Popen([sys.executable, "-c", HOLDER, _store(), str(worst), go],
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "locked"
        t, out = _in_thread(lambda: _ask(world))
        time.sleep(0.4)
        assert t.is_alive() and world.sent == [], "the call waits on the other process's lock"
        open(go, "w").close()
        t.join(10)
    finally:
        child.wait(10)
    got = out["got"]
    assert got["error"] == "over_cap" and world.sent == []
    assert f"plus ${worst:.4f} reserved by 1 call(s) in flight" in got["detail"], got


# ── a background feature's caps ──────────────────────────────────────────────────────────

def test_a_background_features_day_cap_counts_its_calls_in_flight_and_only_those(bg):
    from tests import test_ai_background as TB
    w = bg
    TB._on(day=0.50, month=10.0)
    now = time.time()

    def plant(**over):
        entry = dict({"usd": 0.50, "feature": "fake_loop", "network": "lab",
                      "background": True, "day": "2026-10-25", "month": "2026-10",
                      "at": "x", "expires_at": now + 600, "pid": 1}, **over)
        with open(_store(), "w") as fh:
            json.dump({"held": {"ai-inflight000001": entry}}, fh)
    plant(network="branch")                              # another network's: not counted
    assert TB._call(w)["ok"] is True and len(w.sent) == 1
    plant(background=False)                              # a person's press: not counted
    assert TB._call(w)["ok"] is True and len(w.sent) == 2
    plant()
    got = TB._call(w)
    assert got["error"] == "feature_cap" and len(w.sent) == 2
    assert "plus $0.5000 reserved by its 1 call(s) in flight plus this call's worst case" \
        in got["detail"], got


# ── settled to the actual cost ────────────────────────────────────────────────────────────

def test_a_call_is_reserved_at_its_worst_case_and_settled_to_its_actual_cost(world):
    worst = _worst(world)
    during = {}

    def send(body, key):
        during.update(reservations.open_reservations()["held"])
        return A.Reply(status=200, body=PING, attempts=1, latency_s=0.01)
    got = _ask(world, send=send)
    assert got["ok"] is True
    (entry,) = during.values()
    assert entry["usd"] == pytest.approx(worst) and entry["day"] == "2026-10-25"
    assert entry["month"] == "2026-10" and entry["feature"] == "connection_check"
    assert entry["expires_at"] - time.time() <= gateway.reservation_ttl_s()
    assert list(during) == [got["call_id"]]
    assert reservations.open_reservations()["held"] == {}
    spent = calls.spent_usd(calls.today())
    assert spent["usd"] == pytest.approx(got["cost_usd"]) and got["cost_usd"] < worst


@pytest.mark.parametrize("outcome", ["provider_failure", "not_the_schema"])
def test_every_outcome_settles_its_reservation(world, outcome):
    def send(body, key):
        if outcome == "provider_failure":
            raise A.Overloaded("HTTP 529 after 3 attempts: busy", status=529, attempts=3)
        return A.Reply(status=200, body=dict(PING, content=[{"type": "text",
                                                             "text": "not json"}]))
    got = _ask(world, send=send)
    assert got["ok"] is False and got["error"] in ("overloaded", "schema")
    assert reservations.open_reservations()["held"] == {}


def test_an_exception_counts_its_worst_case_and_settles(world):
    """An exception the gateway does not read (not the adapter's, not an answer): whether the
    provider billed it is unknown, so its row counts the worst case, said; the reservation is
    settled and the exception raised."""
    worst = _worst(world)

    def send(body, key):
        raise RuntimeError("a bug after the request left")
    with pytest.raises(RuntimeError):
        _ask(world, send=send)
    (row,) = calls.read()["rows"]
    assert row["verdict"] == "exception" and row["cost_usd"] == pytest.approx(worst)
    assert "whether the provider billed it is unknown" in row["detail"]
    assert reservations.open_reservations()["held"] == {}
    assert calls.spent_usd(calls.today())["usd"] == pytest.approx(worst)


def test_a_row_that_could_not_be_recorded_keeps_its_reservation_unexpiring(world, monkeypatch):
    """Settled only once the row is in the record: a row the record refused keeps the
    reservation (C2047), unexpiring, holding the call's actual cost, with a late row of its
    names and numbers to be asked of the record again."""
    worst = _worst(world)
    monkeypatch.setattr(calls, "record", lambda row: dict(row, recorded=False))
    got = _ask(world, send=lambda b, k: A.Reply(200, PING))
    assert got["ok"] is True and got["recorded"] is False
    (entry,) = reservations.open_reservations(now=time.time() + 10 ** 7)["held"].values()
    assert entry["unrecorded"] is True
    assert entry["usd"] == pytest.approx(got["cost_usd"]) and got["cost_usd"] < worst
    (late,) = entry["rows"]
    assert late["id"] == got["call_id"] and late["verdict"] == "ok"
    assert late["cost_usd"] == pytest.approx(got["cost_usd"]) and late["recorded_late"] is True
    assert late["at"] == entry["at"], "the call's own time, so the record counts its own day"
    assert not {"request", "response", "output", "tokens"} & set(late), sorted(late)


# ── C2047: a sent call whose row the record refused keeps counting ─────────────────────────

def _expire_every_reservation():
    """Every reservation's expiry put in the past, as time passing would."""
    with open(_store()) as fh:
        got = json.load(fh)
    for v in got["held"].values():
        v["expires_at"] = time.time() - 1
    with open(_store(), "w") as fh:
        json.dump(got, fh)


def test_an_unrecorded_call_still_counts_against_the_day_cap_after_its_reservation_expires(
        world, monkeypatch):
    """The defect: a sent and billed call whose row the record refused stopped counting when
    its reservation expired (587.5 s), so the cap read low. Now its reservation never expires:
    the next call is judged with its cost in flight, refused, nothing sent."""
    worst = _worst(world)
    real = calls.record
    monkeypatch.setattr(calls, "record", lambda row: dict(row, recorded=False))
    first = _ask(world, "a", send=lambda b, k: A.Reply(200, PING))
    assert first["ok"] is True and first["recorded"] is False
    _expire_every_reservation()
    cost = first["cost_usd"]
    world.settings["ai_cap_usd_per_day"] = cost + worst * 0.99
    second = _ask(world, "b", send=world.send)
    assert second["error"] == "over_cap" and world.sent == []
    assert (f"today's spend $0.0000 plus ${cost:.4f} reserved by 1 call(s) in flight plus "
            f"this call's worst case ${worst:.4f}") in second["detail"], second["detail"]
    # The control: the cap with room for both, the second is sent (it, too, unrecorded).
    world.settings["ai_cap_usd_per_day"] = cost + worst * 1.01
    monkeypatch.setattr(calls, "record", real)
    assert _ask(world, "c", send=world.send)["ok"] is True


def test_the_record_taking_the_late_row_settles_it_on_the_calls_own_day(world, monkeypatch):
    real = calls.record
    monkeypatch.setattr(calls, "record", lambda row: dict(row, recorded=False))
    first = _ask(world, "a", send=lambda b, k: A.Reply(200, PING))
    (entry,) = reservations.open_reservations()["held"].values()
    monkeypatch.setattr(calls, "record", real)
    assert _ask(world, "b", send=world.send)["ok"] is True
    assert reservations.open_reservations(now=time.time() + 10 ** 7)["held"] == {}
    late = [r for r in calls.read()["rows"] if r["id"] == first["call_id"]]
    assert len(late) == 1 and late[0]["recorded_late"] is True
    assert late[0]["at"] == entry["at"] and late[0]["cost_usd"] == pytest.approx(
        first["cost_usd"])
    assert "recorded late (C2047)" in late[0]["detail"]


def test_a_late_row_still_refused_keeps_the_reservation(world, monkeypatch):
    monkeypatch.setattr(calls, "record", lambda row: dict(row, recorded=False))
    first = _ask(world, "a", send=lambda b, k: A.Reply(200, PING))
    assert _ask(world, "b", send=lambda b, k: A.Reply(200, PING))["ok"] is True
    held = reservations.open_reservations(now=time.time() + 10 ** 7)["held"]
    assert first["call_id"] in held and len(held) == 2
    assert all(v["unrecorded"] for v in held.values())


def test_an_exception_whose_row_is_refused_holds_its_worst_case(world, monkeypatch):
    worst = _worst(world)
    monkeypatch.setattr(calls, "record", lambda row: dict(row, recorded=False))

    def send(body, key):
        raise RuntimeError("a bug after the request left")
    with pytest.raises(RuntimeError):
        _ask(world, send=send)
    (entry,) = reservations.open_reservations(now=time.time() + 10 ** 7)["held"].values()
    assert entry["usd"] == pytest.approx(worst) and entry["rows"][0]["verdict"] == "exception"


def test_a_refusal_whose_row_is_refused_holds_what_its_row_counts(world, monkeypatch):
    """The provider's refusal (the adapter's kinds) is recorded at no cost; its late row holds
    the same, never more and never a guess."""
    monkeypatch.setattr(calls, "record", lambda row: dict(row, recorded=False))

    def send(body, key):
        raise A.Overloaded("HTTP 529 after 3 attempts: busy", status=529, attempts=3)
    got = _ask(world, send=send)
    assert got["error"] == "overloaded"
    (entry,) = reservations.open_reservations(now=time.time() + 10 ** 7)["held"].values()
    assert entry["usd"] == 0.0 and entry["rows"][0]["verdict"] == "overloaded"


def test_needs_attention_names_an_unrecorded_call_until_the_record_takes_it(world, monkeypatch):
    from modules import attention
    real = calls.record
    monkeypatch.setattr(calls, "record", lambda row: dict(row, recorded=False))
    first = _ask(world, "a", send=lambda b, k: A.Reply(200, PING))
    monkeypatch.setattr(calls, "record", real)
    rows = [r for r in attention.ai_spend_source()["rows"] if r["kind"] == "unrecorded"]
    assert len(rows) == 1
    (r,) = rows
    assert r["level"] == "danger" and r["id"] == f"ai_spend:unrecorded:{first['call_id']}"
    assert r["what"] == f"AI call {first['call_id']}'s cost could not be recorded"
    assert f"its cost ${first['cost_usd']:.4f} is held against the AI caps" in r["cause"]
    assert "refuses writes" in r["action"]["label"]
    assert _ask(world, "b", send=world.send)["ok"] is True
    assert [r for r in attention.ai_spend_source()["rows"] if r["kind"] == "unrecorded"] == []


def _plant_unrecorded(rows, call_id="ai-unrecorded00001", at="2026-10-25T00:00:00Z"):
    with open(_store(), "w") as fh:
        json.dump({"held": {call_id: {
            "usd": sum(r["cost_usd"] for r in rows), "feature": "connection_check",
            "network": "", "background": False, "day": "2026-10-25", "month": "2026-10",
            "at": at, "expires_at": time.time() - 1, "pid": 1, "unrecorded": True,
            "rows": [dict(r, at=at) for r in rows]}}}, fh)


def _late(call_id, usd):
    return reservations.late_row({"id": call_id, "feature": "connection_check"},
                                 verdict="ok", cost_usd=usd)


def test_a_late_row_keeps_the_calls_own_time_whenever_it_is_kept(world):
    """`hold_unrecorded` long after the call (a day later): each late row carries the
    reservation's time, the call's, so the record counts it on its own day."""
    _plant(0.25, 60, call_id="ai-heldlater00001")
    assert reservations.hold_unrecorded("ai-heldlater00001", [_late("ai-heldlater00001", 0.2)],
                                        gateway.reservation_ttl_s(), now=time.time() + 86400)
    (entry,) = reservations.open_reservations(now=time.time() + 10 ** 7)["held"].values()
    assert entry["at"] == "2026-10-25T00:00:00Z"
    assert [r["at"] for r in entry["rows"]] == ["2026-10-25T00:00:00Z"]
    assert entry["usd"] == pytest.approx(0.2)


def test_a_late_row_the_record_takes_leaves_the_others_and_their_cost(world, monkeypatch):
    real = calls.record
    _plant_unrecorded([_late("ai-takenfirst00001", 0.30), _late("ai-refusedstill001", 0.45)])
    monkeypatch.setattr(calls, "record", lambda row: real(row) if row["id"] == "ai-takenfirst00001"
                        else dict(row, recorded=False))
    world.settings["ai_cap_usd_per_day"] = 100.0
    assert _ask(world, send=lambda b, k: A.Reply(200, PING))["ok"] is True
    held = reservations.open_reservations(now=time.time() + 10 ** 7)["held"]
    entry = held["ai-unrecorded00001"]
    assert [r["id"] for r in entry["rows"]] == ["ai-refusedstill001"]
    assert entry["usd"] == pytest.approx(0.45)


@pytest.mark.parametrize("still_refused", [False, True], ids=["all-taken", "one-left"])
def test_a_refused_call_still_writes_the_late_rows_the_record_took(world, monkeypatch,
                                                                   still_refused):
    """The record takes a late row and then the call is refused on the cap: the store is
    written all the same, so the row is never asked again (it would count twice), whether
    the entry goes (every row taken) or stays with the rows still refused."""
    real = calls.record
    rows = [_late("ai-takenonce00001", 0.30)] + (
        [_late("ai-refusedstill001", 0.45)] if still_refused else [])
    _plant_unrecorded(rows)
    monkeypatch.setattr(calls, "record", lambda row: dict(row, recorded=False)
                        if row["id"] == "ai-refusedstill001" else real(row))
    world.settings["ai_cap_usd_per_day"] = 0.30
    for _ in range(2):
        got = _ask(world)
        assert got["error"] == "over_cap" and world.sent == []
        held = reservations.open_reservations(now=time.time() + 10 ** 7)["held"]
        assert ([r["id"] for r in held["ai-unrecorded00001"]["rows"]] == ["ai-refusedstill001"]
                if still_refused else held == {}), held
        late = [r for r in calls.read()["rows"] if r["id"] == "ai-takenonce00001"]
        assert len(late) == 1 and late[0]["at"] == "2026-10-25T00:00:00Z"


def test_the_row_stands_while_ai_is_off(world, monkeypatch):
    """An unrecorded call was sent while AI was on; its row is read whatever AI's state now."""
    from modules import attention
    monkeypatch.setattr(calls, "record", lambda row: dict(row, recorded=False))
    first = _ask(world, "a", send=lambda b, k: A.Reply(200, PING))
    world.settings.pop("ai_hosted")
    rows = [r for r in attention.ai_spend_source()["rows"] if r["kind"] == "unrecorded"]
    assert [r["operands"]["call_id"] for r in rows] == [first["call_id"]]


def test_a_reservation_that_cannot_be_kept_is_said_at_critical(world, monkeypatch, caplog):
    """The record refused the row AND the reservations store cannot be written: said at
    CRITICAL; the reservation as it was counts the call until it expires, and the next call,
    which must write the store, is refused."""
    import logging
    from modules import filestore
    caplog.set_level(logging.CRITICAL, logger=reservations.__name__)
    monkeypatch.setattr(calls, "record", lambda row: dict(row, recorded=False))
    real = filestore.write_atomic
    state = {"writes": 0}

    def write(path, data, *a, **kw):
        if path == _store():
            state["writes"] += 1
            if state["writes"] > 1:                      # the reservation itself is written
                raise OSError("No space left on device")
        return real(path, data, *a, **kw)
    monkeypatch.setattr(filestore, "write_atomic", write)
    assert _ask(world, "a", send=lambda b, k: A.Reply(200, PING))["ok"] is True
    assert any("could not be kept" in r.getMessage() and r.levelno == logging.CRITICAL
               for r in caplog.records), caplog.records
    (entry,) = reservations.open_reservations()["held"].values()
    assert "unrecorded" not in entry and entry["expires_at"] > time.time()
    got = _ask(world, "b", send=world.send)
    assert got["error"] == "over_cap" and world.sent == []


# ── a crashed reservation ─────────────────────────────────────────────────────────────────

def test_the_reservations_life_is_two_and_a_half_times_one_calls_longest(world):
    a = A
    one_call = (a.TIMEOUT[0] + a.TIMEOUT[1]) * (a.MAX_RETRIES + 1) + a.MAX_WAIT_S * a.MAX_RETRIES
    assert one_call == 235.0 == gateway.send_bound_s()
    assert gateway.reservation_ttl_s() == 2.5 * 235.0


def _plant(usd, expires_in, call_id="ai-deadprocess00001"):
    with open(_store(), "w") as fh:
        json.dump({"held": {call_id: {"usd": usd, "feature": "explain", "network": "",
                                      "background": False, "day": "2026-10-25",
                                      "month": "2026-10", "at": "2026-10-25T00:00:00Z",
                                      "expires_at": time.time() + expires_in, "pid": 1}}}, fh)


def test_a_reservation_a_dead_process_left_expires_and_is_dropped(world, caplog):
    import logging
    caplog.set_level(logging.WARNING, logger=reservations.__name__)
    _plant(1000.0, -1)
    assert _ask(world)["ok"] is True and len(world.sent) == 1
    assert reservations.open_reservations()["held"] == {}
    assert any("ai-deadprocess00001's reservation of $1000.0000 expired unsettled"
               in r.getMessage() for r in caplog.records), caplog.records


def test_a_refused_call_still_drops_an_expired_reservation_from_the_store(world):
    """The prune is written even when the call is refused, so a dead process's reservation
    is dropped (and logged) once, not at every refusal after it."""
    with open(_store(), "w") as fh:
        now = time.time()
        json.dump({"held": {
            "ai-deadprocess00001": {"usd": 5.0, "expires_at": now - 1, "at": "x"},
            "ai-liveprocess00001": {"usd": 1.5, "expires_at": now + 60, "at": "y"}}}, fh)
    assert _ask(world)["error"] == "over_cap" and world.sent == []
    with open(_store()) as fh:
        assert list(json.load(fh)["held"]) == ["ai-liveprocess00001"]


def test_a_reservation_not_yet_expired_is_held_against_the_cap(world):
    _plant(1.50, 60)
    got = _ask(world)
    assert got["error"] == "over_cap" and world.sent == []
    assert "plus $1.5000 reserved by 1 call(s) in flight" in got["detail"]
    assert list(reservations.open_reservations()["held"]) == ["ai-deadprocess00001"], \
        "a refused call reserves nothing and drops nothing live"


# ── an unreadable store ───────────────────────────────────────────────────────────────────

def test_an_unreadable_store_refuses_the_call_and_sends_nothing(world):
    with open(_store(), "w") as fh:
        fh.write('{"held": {"ai-x": {"usd": ')
    got = _ask(world)
    assert got["ok"] is False and got["error"] == "over_cap" and world.sent == []
    assert got["detail"].startswith(f"the AI caps' reservations ({reservations.NAME}) cannot "
                                    "be read (JSONDecodeError), so what is in flight is "
                                    "unknown"), got["detail"]
    assert got["detail"].endswith("; nothing was sent")
    with open(_store()) as fh:
        assert fh.read() == '{"held": {"ai-x": {"usd": ', "it is left as it was"
    (row,) = calls.read()["rows"]
    assert row["verdict"] == "over_cap"


@pytest.mark.parametrize("text", ['[]', '{"held": []}', '{"held": {"ai-x": {"usd": "1"}}}',
                                  '{"held": {"ai-x": {"usd": 1}}}'])
def test_a_store_out_of_shape_is_unreadable_too(world, text):
    with open(_store(), "w") as fh:
        fh.write(text)
    got = _ask(world)
    assert got["error"] == "over_cap" and "cannot be read" in got["detail"] and world.sent == []


def test_an_unreadable_store_older_than_a_reservation_lives_is_kept_aside_and_replaced(world):
    with open(_store(), "w") as fh:
        fh.write("not json")
    old = time.time() - gateway.reservation_ttl_s() - 5
    os.utime(_store(), (old, old))
    assert _ask(world)["ok"] is True and len(world.sent) == 1
    folder = os.path.dirname(_store())
    kept = [n for n in os.listdir(folder) if n.startswith(reservations.NAME + ".corrupt-")]
    assert len(kept) == 1
    with open(os.path.join(folder, kept[0])) as fh:
        assert fh.read() == "not json"
    assert reservations.open_reservations() == {"state": "ok", "held": {}, "error": ""}


def test_the_store_is_owner_only(world):
    seen = {}

    def send(body, key):
        seen["mode"] = stat.S_IMODE(os.stat(_store()).st_mode)
        return A.Reply(status=200, body=PING)
    assert _ask(world, send=send)["ok"] is True
    assert seen["mode"] == 0o600 and stat.S_IMODE(os.stat(_store()).st_mode) == 0o600


def test_a_store_that_cannot_be_written_refuses_the_call(world, monkeypatch):
    def full(path, held):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(reservations, "_write", full)
    got = _ask(world)
    assert got["error"] == "over_cap" and world.sent == []
    assert got["detail"] == (f"the AI caps' reservations ({reservations.NAME}) could not be "
                             "written (OSError: [Errno 28] No space left on device), so this "
                             "call could not be held against the caps; nothing was sent")


def test_a_reservation_that_cannot_be_settled_is_logged_and_the_answer_returned(world, caplog):
    """The store turned unreadable while the call was in flight: the answer is still returned
    and recorded; the reservation, unsettled, is logged (and the store refuses the next call,
    as any unreadable store does)."""
    import logging
    caplog.set_level(logging.ERROR, logger=reservations.__name__)

    def send(body, key):
        with open(_store(), "w") as fh:
            fh.write("torn")
        return A.Reply(status=200, body=PING)
    got = _ask(world, send=send)
    assert got["ok"] is True and got["recorded"] is True
    assert any(f"{got['call_id']}'s reservation could not be settled" in r.getMessage()
               for r in caplog.records)


def test_two_background_calls_at_once_cannot_pass_the_features_day_cap_together(bg):
    """C1970's case: two calls of one background feature on one network at once, each alone
    under its day cap, both over it: the second is refused on the first's reservation, before
    any provider request, naming it."""
    from modules.ai import background as B
    from tests import test_ai_background as TB
    inside, release = threading.Event(), threading.Event()

    def slow(body, key):
        bg.sent.append(body)
        inside.set()
        assert release.wait(10)
        return A.Reply(status=200, body=PING)

    def call(word, finding, send):
        t = triggers.background("fake_loop", "j1", "Lab", "detection", finding)
        return gateway.ask(TB.TASK, ("ping", 1), connection.Ping, {"word": word},
                           actor=triggers.actor_of(t), trigger=t, send=send)
    # The first call in flight; then the feature's day cap set to one call's worst case and a
    # half (its worst case read from its reservation), as an admin would.
    TB._on(day=1.0, month=10.0)
    th, first = _in_thread(lambda: call("a", "scan-1", slow))
    assert inside.wait(10)
    (entry,) = reservations.open_reservations()["held"].values()
    worst = entry["usd"]
    assert (entry["background"], entry["feature"], entry["network"]) == (True, "fake_loop",
                                                                         "lab")
    B.set_caps("Lab", "fake_loop", day_cap_usd=worst * 1.5, month_cap_usd=10.0,
               actor=TB.ADMIN, verified="access")
    second = call("b", "scan-2", slow)
    release.set()
    th.join(10)
    assert first["got"]["ok"] is True and len(bg.sent) == 1, "only the first was sent"
    assert second["error"] == "feature_cap", second
    assert f"plus ${worst:.4f} reserved by its 1 call(s) in flight" in second["detail"], second
