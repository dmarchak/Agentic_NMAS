"""The spending limits enforced live (7b0bb884, the operator, 2026-11-16: "the cap is enforced
live ... Billing stops at the abort"; the debt pass of 2026-11-18, docs/FAST_LANE_DEBT.md).

A visible-output call (thinking off) is held at its counted prompt plus its typical answer, and
while its answer streams its running cost is judged again against the remaining cap
(`gateway._capped_send`'s `progress`, `reservations.live_check`): once it would pass, the
stream is closed, the call recorded ``budget_ran_out`` with its running cost, nothing of the
answer parsed; with room under the cap the same stream runs to its end. On
tests/test_ai_gateway.py's world, the adapter's send replaced by a stream that reports its
output tokens to the gateway's hook as the real one does (`anthropic_adapter._read_stream`).
No network, no live AI call.
"""
import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, connection, gateway, profiles, triggers
from tests.ai_person import pressed_by
from tests.test_ai_gateway import world  # noqa: F401 (the fixture)

ACTOR = "operator@example.com"
MODEL = profiles.TASKS["connection_check"]["model"]
#: How far the planted stream runs, and the output between two of its events (a few tokens a
#: delta, as a real stream reports them).
STREAM_TOKENS, STEP = 40000, 5
#: The installation's day cap: the call's hold (its counted prompt and the typical answer, about
#: $0.0001 on the task's model) fits under it, the planted stream's whole answer (40,000 output
#: tokens, $0.02 at the model's $0.50 a million) does not.
CAP = 0.004


def _stream(answer: str = '{"echo": "w"}'):
    """The adapter's send as a stream: after each event it asks the gateway's hook
    (*progress*), and closes the stream the moment the hook says why, raising `StreamAborted`
    with what it measured as `anthropic_adapter._read_stream`'s ``failed`` does (the prompt's
    usage, and the output the provider reported)."""
    seen = {"checked": 0, "last": 0}

    def send(body, key, progress=None, **_kw):
        usage = {"input_tokens": 120, "cache_creation_input_tokens": 0,
                 "cache_read_input_tokens": 0}
        for n in range(STEP, STREAM_TOKENS + 1, STEP):
            seen["last"] = n
            why = progress({"output_tokens": n, "usage": usage, "how": "reported"}) \
                if progress else ""
            seen["checked"] += 1
            if why:
                raise A.StreamAborted(why, usage=dict(usage), partial=True, output_began=True,
                                      stream={"events": seen["checked"], "longest_gap_s": 0.0,
                                              "output_began": True, "output_estimated": n,
                                              "output_reported": n})
        return A.Reply(status=200, body={"content": [{"type": "text", "text": answer}],
                                         "stop_reason": "end_turn",
                                         "usage": dict(usage, output_tokens=8)},
                       attempts=1, latency_s=0.01, headers={})
    return send, seen


def _ask():
    with pressed_by(ACTOR):
        return gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                           actor=ACTOR, trigger=triggers.person(ACTOR), thinking="off",
                           today="2026-10-25")


def _spent(monkeypatch, usd):
    monkeypatch.setattr(calls, "spent_usd", lambda day: {"state": "ok", "usd": usd,
                                                         "calls": 1, "error": ""})


def test_a_stream_passing_the_cap_is_closed_live_and_recorded(world, monkeypatch):  # noqa: F811
    send, seen = _stream()
    monkeypatch.setattr(A, "send", send)
    world.settings["ai_cap_usd_per_day"] = CAP
    _spent(monkeypatch, 0.0)
    got = _ask()
    assert got["ok"] is False and got["error"] == "budget_ran_out", got
    assert "budget ran out mid-answer" in got["detail"], got["detail"]
    assert "the installation's day cap" in got["detail"], got["detail"]
    assert seen["last"] < STREAM_TOKENS, "the stream was closed before its end"
    (row,) = calls.read()["rows"]
    assert row["verdict"] == "budget_ran_out" and row.get("partial") is True, row
    # Billing stops at the abort: its prompt and the output the provider reported to then.
    assert row["cost_usd"] == pytest.approx(profiles.cost_usd(MODEL, 120, seen["last"]),
                                            abs=1e-6), (row["cost_usd"], seen)
    assert row["cost_usd"] <= CAP


def test_the_same_stream_with_room_runs_to_its_end(world, monkeypatch):  # noqa: F811
    send, seen = _stream()
    monkeypatch.setattr(A, "send", send)
    world.settings["ai_cap_usd_per_day"] = None
    _spent(monkeypatch, 0.0)
    got = _ask()
    assert got["ok"] is True, got
    assert seen["last"] == STREAM_TOKENS


@pytest.mark.parametrize("spent", [0.0, 0.002])
def test_the_abort_comes_before_the_running_cost_passes_the_remaining(world, monkeypatch,  # noqa: F811
                                                                      spent):
    send, seen = _stream()
    monkeypatch.setattr(A, "send", send)
    world.settings["ai_cap_usd_per_day"] = CAP
    _spent(monkeypatch, spent)
    got = _ask()
    assert got["error"] == "budget_ran_out", got
    rate = profiles.prices_for(MODEL, 120)["output"] / 1_000_000
    prompt = profiles.cost_usd(MODEL, 120, 0)
    assert prompt + seen["last"] * rate <= CAP - spent, (seen, got["detail"])
