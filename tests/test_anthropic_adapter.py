"""The Anthropic adapter's contract, field by field (`modules/ai/anthropic_adapter.py`, the
irreversible tier's send: PHASE8_PLAN 15.12), through a fake session, no network: what one
request carries, what each answer becomes (its kind, its words, its status, attempts and the
rate-limit headers kept), the waits it sleeps and when it stops. Written from tier run #63's
survivors in `send`, `_error_words`, `_retry_after` and `ratelimit_headers` (2026-10-25):
tests/test_ai_gateway.py held each answer's KIND, and this file holds the rest.
"""
import pytest
import requests

from modules.ai import anthropic_adapter as A
from tests.test_ai_gateway import OK_BODY, _Resp, _Session

KEY = "sk-planted-test-key-0123456789"
BODY = {"model": "claude-haiku-5-5", "max_tokens": 64, "messages": [{"role": "user",
                                                                   "content": "w"}]}
KEPT = {"anthropic-ratelimit-requests-remaining": "49"}


def _err(status, kind="api_error", message="the provider's own words", headers=None):
    return _Resp(status, {"error": {"type": kind, "message": message}}, headers or dict(KEPT))


def _raised(*responses, **kw):
    with pytest.raises(A.AdapterError) as got:
        A.send(BODY, KEY, session=_Session(*responses), sleep=kw.pop("sleep", pytest.fail), **kw)
    return got.value


# ---------------------------------------------------------------------------- one request

def test_one_request_carries_the_body_its_three_headers_and_the_timeout():
    s = _Session(_Resp(200, OK_BODY, dict(KEPT)))
    A.send(BODY, KEY, session=s, sleep=pytest.fail)
    (sent,) = s.sent
    assert sent["json"] == BODY and sent["timeout"] == A.TIMEOUT
    assert sent["headers"] == {"x-api-key": KEY, "anthropic-version": "2023-06-01",
                               "content-type": "application/json"}


def test_a_reply_carries_its_latency_by_the_clock_given():
    ticks = iter([100.0, 102.5])
    reply = A.send(BODY, KEY, session=_Session(_Resp(200, OK_BODY, {})), sleep=pytest.fail,
                   clock=lambda: next(ticks))
    assert reply.latency_s == 2.5


def test_no_key_refuses_in_its_words():
    with pytest.raises(A.KeyRefused) as no_key:
        A.send(BODY, "", session=_Session())
    assert str(no_key.value) == "no API key is set"


# ---------------------------------------------------------------------------- each failure

@pytest.mark.parametrize("status,cls", [(401, A.KeyRefused), (403, A.KeyRefused),
                                        (400, A.BadRequest), (404, A.BadRequest),
                                        (413, A.BadRequest), (405, A.ProviderDown),
                                        (414, A.ProviderDown), (500, A.ProviderDown)])
def test_each_refusal_is_its_kind_with_its_words_status_attempts_and_headers(status, cls):
    got = _raised(_err(status, "some_error", "it said why"))
    assert type(got) is cls, (status, type(got))
    assert str(got) == f"HTTP {status}: some_error: it said why"
    assert (got.status, got.attempts, got.headers) == (status, 1, KEPT)


def test_a_200_that_is_not_json_is_the_provider_down_with_its_fields():
    got = _raised(_Resp(200, None, dict(KEPT), text="<html>"))
    assert type(got) is A.ProviderDown and str(got) == "HTTP 200 with a body that is not JSON"
    assert (got.status, got.attempts, got.headers) == (200, 1, KEPT)


@pytest.mark.parametrize("exc,words", [
    (requests.Timeout("t"), "no answer within 60 s (Timeout)"),
    (requests.ConnectionError("c"), f"could not reach {A.URL} (ConnectionError)"),
])
def test_no_answer_and_no_route_say_which(exc, words):
    got = _raised(exc)
    assert type(got) is A.ProviderDown and str(got) == words and got.attempts == 1


# ---------------------------------------------------------------------------- the waits

def test_a_retry_after_of_zero_is_slept_as_zero():
    slept = []
    A.send(BODY, KEY, session=_Session(_err(429, headers={"retry-after": "0"}),
                                       _Resp(200, OK_BODY, {})), sleep=slept.append)
    assert slept == [0.0]


def test_a_retry_after_at_the_bound_is_waited_and_one_over_it_is_not():
    slept = []
    A.send(BODY, KEY, session=_Session(_err(529, headers={"retry-after": "20"}),
                                       _Resp(200, OK_BODY, {})), sleep=slept.append)
    assert slept == [20.0]
    got = _raised(_err(529, "overloaded_error", "busy", headers={"retry-after": "21"}))
    assert type(got) is A.Overloaded
    assert str(got) == ("HTTP 529: the provider asks for 21 s, over the 20 s a waiting call "
                        "allows: overloaded_error: busy")
    assert (got.status, got.attempts, got.headers) == (529, 1, {"retry-after": "21"})


def test_the_last_retry_says_its_attempts_and_keeps_its_fields():
    got = _raised(*[_err(429, "rate_limit_error", "slow down")] * 3, sleep=lambda s: None)
    assert type(got) is A.RateLimited
    assert str(got) == "HTTP 429 after 3 attempts: rate_limit_error: slow down"
    assert (got.status, got.attempts, got.headers) == (429, 3, KEPT)


@pytest.mark.parametrize("second,cls", [
    (_err(401), A.KeyRefused), (_err(400), A.BadRequest), (_err(503), A.ProviderDown),
    (_Resp(200, None, {}, text="<html>"), A.ProviderDown),
    (requests.Timeout("t"), A.ProviderDown), (requests.ConnectionError("c"), A.ProviderDown),
    (_err(529, headers={"retry-after": "60"}), A.Overloaded),
])
def test_an_error_after_a_retry_counts_both_attempts(second, cls):
    got = _raised(_err(429, headers={"retry-after": "1"}), second, sleep=lambda s: None)
    assert type(got) is cls and got.attempts == 2, (type(got), got.attempts)


def test_each_wait_is_logged_with_its_status_attempt_and_seconds(caplog):
    import logging
    caplog.set_level(logging.INFO, logger=A.__name__)
    A.send(BODY, KEY, session=_Session(_err(429, headers={"retry-after": "3"}),
                                       _Resp(200, OK_BODY, {})), sleep=lambda s: None)
    assert [r.getMessage() for r in caplog.records if r.name == A.__name__] == [
        "anthropic: HTTP 429, attempt 1, waiting 3.0 s"]


@pytest.mark.parametrize("headers,wait", [({"retry-after": "3"}, 3.0),
                                          ({"retry-after": "-4"}, 0.0),
                                          ({"retry-after": "soon"}, None), ({}, None),
                                          (None, None)])
def test_retry_after_is_its_seconds_or_none(headers, wait):
    assert A._retry_after(headers) == wait


# ---------------------------------------------------------------------------- the words

@pytest.mark.parametrize("body,words", [
    ({"error": {"type": "invalid_request_error", "message": "bad thing"}},
     "invalid_request_error: bad thing"),
    ({"error": {"message": "only a message"}}, "only a message"),
    ({"error": {"type": "overloaded_error"}}, "overloaded_error"),
    ({"error": {"type": "t", "message": "a value named X"}}, "t: a value named X"),
    ({"error": {}}, "HTTP 500"),
    ({}, "HTTP 500"),
])
def test_the_error_words_are_the_providers_type_and_message(body, words):
    assert A._error_words(_Resp(500, body)) == words


def test_a_body_that_is_not_json_is_its_first_200_characters():
    assert A._error_words(_Resp(502, None, text="x" * 250)) == "x" * 200
    assert A._error_words(_Resp(502, None, text="")) == "HTTP 502"


def test_the_words_are_cut_at_300_and_masked_without_reading_the_store(monkeypatch):
    from modules import redact

    def never():
        raise AssertionError("the error words read the secrets store")
    monkeypatch.setattr(redact, "known_secret_values", never)
    long = A._error_words(_Resp(500, {"error": {"type": "t", "message": "m" * 400}}))
    assert long == ("t: " + "m" * 400)[:300]
    masked = A._error_words(_Resp(500, {"error": {"type": "t",
                                                  "message": "password plantedPw99 refused"}}))
    assert "plantedPw99" not in masked and "<redacted:" in masked


def test_the_rate_limit_headers_kept_are_the_providers_and_retry_after_in_any_case():
    got = A.ratelimit_headers({"Anthropic-RateLimit-Requests-Remaining": "49",
                               "X-RateLimit-Limit": "50", "Retry-After": "3",
                               "Content-Type": "application/json"})
    assert got == {"anthropic-ratelimit-requests-remaining": "49", "x-ratelimit-limit": "50",
                   "retry-after": "3"}
