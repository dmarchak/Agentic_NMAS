"""An answer cut off at `max_tokens` is refused whole, never half-applied, on every feature
(the operator, 2026-10-25: two of the first 24 live calls ran past it, C1698): the gateway
reads the stop before it reads the answer, so even a complete, valid answer whose stop is
`max_tokens` fills nothing, shows nothing and is recorded as `max_tokens`; the builder is
redrawn exactly as the person's form carried it, with the reason in words. Each feature's own
world is its tests' (tests/test_ai_nl_query.py here; the logs half's and Explain's, sharing
`_cut`, in tests/test_ai_nl_logs.py and tests/test_ai_explain.py), only the stop changed.
"""
import json

import pytest

from modules.ai import triggers
from tests.ai_person import pressed_by
from modules.ai import anthropic_adapter as A
from modules.ai import calls, nl_query, profiles
from tests.test_ai_nl_query import NOW, _choices, _words, site, web, world  # noqa: F401

BOUND = profiles.TASKS["nl_query"]["max_tokens"]


def cut_words(task: str) -> str:
    """A max_tokens stop at the model's maximum, in words (7b0bb884: never parsed)."""
    most = profiles.max_output(profiles.TASKS[task]["model"])
    return (f"the answer was cut at max_tokens ({most:,}, set by the model's maximum output "
            f"({most // 1000}K)); nothing of it was parsed")


CUT = cut_words("nl_query")


def cut_twice(got: dict, task: str) -> None:
    """A thinking call stopped at max_tokens (7b0bb884, the operator 2026-11-16: thinking calls
    are sized by a "Measured bound, plus ... retry once"): the first call, sized by its task's
    bound (the pin's max_tokens while none is measured), is asked once more as a new call sized
    to what the remaining can pay, at most the model's maximum; both stopped at max_tokens,
    both recorded, nothing of either parsed; the result is the retry's, naming the first."""
    retry, first = calls.read()["rows"]                  # newest first
    pin = profiles.TASKS[task]["max_tokens"]
    assert (first["verdict"], retry["verdict"]) == ("max_tokens", "max_tokens")
    assert "output" not in first and "output" not in retry
    assert first["sized"]["max_tokens"] == pin and first["sized"]["kind"] == "measured_bound"
    assert retry["sized"]["retry"] is True
    assert retry["sized"]["max_tokens"] == profiles.max_output(profiles.TASKS[task]["model"])
    assert got["also_calls"] == [first["id"]] and got["call_id"] == retry["id"]


def _cut(w, text):
    """*w*'s send, answering *text* whole but stopped at max_tokens."""
    def send(body, key, **_kw):
        w.sent.append({"bytes": json.dumps(body), "body": body})
        return A.Reply(status=200, body={"content": [{"type": "text", "text": text}],
                                         "stop_reason": "max_tokens",
                                         "usage": {"input_tokens": 900,
                                                   "output_tokens": BOUND}},
                       attempts=1, latency_s=0.3)
    return send


@pytest.mark.parametrize("text", [json.dumps(_choices()), json.dumps(_choices())[:120]],
                         ids=["complete-and-valid", "cut-mid-answer"])
def test_a_metrics_answer_stopped_at_max_tokens_fills_nothing(world, text):
    with pressed_by("operator@example.com"):
        got = nl_query.metrics("Lab", "input errors per interface, the top 5",
                               actor="operator@example.com",
                               trigger=triggers.person("operator@example.com"),
                               send=_cut(world, text),
                               client=world.prom, now=NOW, today="2026-10-25")
    assert got["ok"] is False and got["error"] == "max_tokens"
    assert got["detail"] == CUT
    assert "values" not in got and "view" not in got and "choices" not in got
    cut_twice(got, "nl_query")


def test_the_builder_is_redrawn_as_the_form_carried_it_with_the_reason(site, monkeypatch):
    from modules.ai import anthropic_adapter
    monkeypatch.setattr(anthropic_adapter, "send", _cut(site.world, json.dumps(_choices())))
    r, html = _words(site, "input errors per interface", m="ifHCInOctets",
                     op=["rate:5m", "bits"])
    assert r.status_code == 200 and "HX-Push-Url" not in r.headers
    assert f"Not filled: {CUT}." in html
    assert "rate(ifHCInOctets" in html, "the builder was not drawn as the form carried it"
    assert "topk(5, rate(ifInErrors" not in html, "the cut answer was applied"
    assert not any(p == "api/v1/query_range" for p, _ in site.asked)
