"""Gate 2's review (2026-11-15): a person's call that counts for a background feature (C3751, a
turn-on catch-up's investigation) is held to that feature's day and month caps at the gateway,
each call of it, as a background call is (`gateway`'s judge, `triggers.counted_feature`).

Before, only background calls were judged against a feature's caps: a catch-up investigation's
plan reserved its worst case and settled it at its first call, so its second call, and every
other planner after that first call, never saw the feature's cap. So two catch-up starts and
an automatic start could pass a feature's cap together.

Through Settings › AI's own world (tests/test_settings_ai_v2.py: the real gateway, the record of
AI calls in the test's folder, a planted feature, a fake provider). No live AI call.

One purpose: with a feature's day cap at exactly its spend so far, a counted person's
call is refused at the feature's cap, naming it, and the provider is not asked; a person's call
that counts for nothing is not held to it.
"""
import pytest

from modules.ai import background as B
from modules.ai import connection, gateway, spend, triggers
from tests.conftest import TEST_PERSON
from tests.test_settings_ai_v2 import NET, TASK, _call, _turn_on, ai  # noqa: F401
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture `ai` builds on)


def _person_call(w, counts=True):
    trig = triggers.person(TEST_PERSON, counts_for={"feature": "fake_loop",
                                                    "network": B._network(NET)}
                           if counts else None)
    import app as APP
    with APP.app.test_request_context("/v2/"):
        return gateway.ask(TASK, ("ping", 1), connection.Ping, {"word": "w"},
                           actor=TEST_PERSON,
                           trigger=trig, send=w.send)


def test_a_counted_person_call_is_held_to_the_features_cap(ai):  # noqa: F811
    r, _html = _turn_on(ai, day="0.50", month="10.00")
    assert r.status_code == 200
    first = _call(ai)
    assert first.get("ok"), first
    x = spend.feature_spent(B._network(NET), "fake_loop")["day_usd"]
    assert x > 0
    B.set_caps(NET, "fake_loop", day_cap_usd=x, month_cap_usd=10.0,
               actor="admin@example.com", verified="access")
    sent = len(ai.sent)
    got = _person_call(ai)
    assert got.get("error") == "feature_cap" and "fake_loop" in got.get("detail", ""), got
    assert len(ai.sent) == sent, "the provider was not asked"
    # A person's call that counts for no feature is held to the day cap alone.
    assert _person_call(ai, counts=False).get("ok"), "uncounted: not the feature's cap"


@pytest.fixture(autouse=True)
def _as_a_person(monkeypatch):
    """The gateway asks a person's call to be this request's verified person: stood in as the
    test's person (the identity layer's own tests hold that check)."""
    from modules import identity
    monkeypatch.setattr(identity, "request_actor", lambda: TEST_PERSON, raising=False)
