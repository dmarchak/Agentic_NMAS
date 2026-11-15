"""Every AI troubleshooting request is one the provider can compile (the operator, 2026-11-15).

s1's "Ask the AI again" at 2026-11-15 17:18 UTC (prompt v8) was refused by the provider before
any token: HTTP 400 "The compiled grammar is too large ... Simplify your tool schemas". The
request carries no tools; its grammar is the answer's schema in ``output_config.format``, and
v8's held 20 parameters with a union type where the provider's documented limit is 16 (the
structured-outputs reference, "Schema complexity limits", read 2026-11-15: 24 optional and 16
union parameters per request, past which, or past an unstated bound on the compiled grammar,
a request is refused). Fakes answer any schema, so a fake could never catch it; these hold the
shape that the provider compiles, and the AI card's Test asks the provider itself
(`connection.compile_check`).

- **The schemas sent are within the provider's limits, by construction:** v9 and v10 are v7 and
  v8 flattened (`schemas.flatten`: every property required, none nullable, no union), so 0
  optional and 0 union parameters, and no larger than the largest troubleshooting schema
  measured to compile on the host (v5, 3,955 characters, answered at 07:13:52 UTC that day).
  v8, the one refused, is over the limit by the same count (the count shown able to fail).
- **The request built for an incident is exactly that schema:** the press's own request, as the
  provider would receive it.
- **A flattened answer reads in v7's shape** (`unflatten`): "" and [] for none read as None, an
  empty gap or improvement as none, and an answer recorded in that shape reads back unchanged
  (a joined press rebuilds a call's answer from its row).
- **A refused request is said as one (B):** "The AI didn't answer: the request was rejected
  (its schema too large). Nothing was sent to any device." on the card and in the record,
  never "The AI named no fix", which is said only of an answer that named none.
- **The AI card's Test says whether each schema compiles** (tests/test_ai_card_compile_check.py):
  a provider that refuses the schema fails the Test, naming it; one that compiles it (an
  answer cut at max_tokens included) passes.

No device, no network, no live AI: the provider is stood in.
"""
import json

import pytest

from modules.ai import anthropic_adapter as AD
from modules.ai import connection, gateway, schemas
from modules.ai import fixit_troubleshoot as FT
from modules.fixit import incident as F
from tests.test_fixit_troubleshoot import ai, incident, press, sec_of, stopped  # noqa: F401
from tests.test_fixit_section_v2 import NET, web  # noqa: F401 (the fixture `ai` builds on)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

#: The largest troubleshooting answer schema measured to compile: v5's, as sent (3,955
#: characters; its call ai-2c349452c6004b2c answered on the host, 2026-11-15 07:13:52 UTC).
MEASURED_COMPILES_CHARS = 3955

REFUSED = ("HTTP 400: invalid_request_error: The compiled grammar is too large, which would "
           "cause performance issues. Simplify your tool schemas or reduce the number of "
           "strict tools.")


def sent_schema(model) -> dict:
    return schemas.schema_for(model)


# ── The schemas sent ────────────────────────────────────────────────────────────────────────

def test_each_schema_troubleshooting_sends_is_within_the_provider_s_limits():
    asked = connection.compiled_schemas()
    # The investigation's three passes since C3797 (its first, a later one and its last).
    assert len(asked) == 3, asked
    for name, version, model in asked:
        s = sent_schema(model)
        c = schemas.complexity(s)
        assert c["union"] == 0 and c["optional"] == 0, (name, version, c)
        assert c["union"] <= schemas.PROVIDER_UNION_LIMIT
        assert c["optional"] <= schemas.PROVIDER_OPTIONAL_LIMIT
        assert len(json.dumps(s)) <= MEASURED_COMPILES_CHARS, (name, version,
                                                               len(json.dumps(s)))


def test_the_schemas_asked_are_the_flattened_ones():
    # The investigation's passes since C3797: v11, v12 and v13, each flattened as v9 and v10.
    assert (FT.PROMPT_PLAN_READS, FT.PROMPT_AGAIN, FT.PROMPT_PLAN) == (
        (FT.FEATURE, 11), (FT.FEATURE, 12), (FT.FEATURE, 13))
    assert [m for _n, _v, m in connection.compiled_schemas()] == [
        FT.TroubleshootInvestigate, FT.TroubleshootInvestigateAgain, FT.TroubleshootInvestigated]
    assert all(issubclass(m, schemas.FlatWire) for _n, _v, m in connection.compiled_schemas())
    for _n, _v, model in connection.compiled_schemas():
        assert "fix" not in sent_schema(model)["properties"], "the plan is the fix"


def test_v8_the_schema_the_provider_refused_is_over_its_limit_by_this_count():
    # The count shown able to fail, on the very schema the provider refused.
    c = schemas.complexity(sent_schema(FT.SCHEMA_OF[8]))
    assert c["union"] == 20 > schemas.PROVIDER_UNION_LIMIT, c
    # And v5, which compiled, is within it.
    c5 = schemas.complexity(sent_schema(FT.SCHEMA_OF[5]))
    assert c5["union"] <= schemas.PROVIDER_UNION_LIMIT, c5
    assert len(json.dumps(sent_schema(FT.SCHEMA_OF[5]))) == MEASURED_COMPILES_CHARS


def test_flatten_refuses_a_union_it_cannot_say_as_one_type():
    with pytest.raises(ValueError, match="cannot be flattened"):
        schemas.flatten({"type": "object", "properties": {"x": {"anyOf": [
            {"type": "object", "properties": {}}, {"type": "array", "items": {}}]}}})


# ── The request built for an incident ──────────────────────────────────────────────────────

def test_the_press_s_request_carries_exactly_the_flattened_schema_and_no_tools(ai):  # noqa: F811
    iid = stopped(ai)
    press(ai, iid)
    assert ai.sent, "the press asked the provider"
    for body in ai.sent:
        assert "tools" not in body
        got = body["output_config"]["format"]["schema"]
        assert got in [sent_schema(m) for _n, _v, m in connection.compiled_schemas()], \
            "a schema not one the compile check sends"
        c = schemas.complexity(got)
        assert c["union"] == 0 and c["optional"] == 0, c


# ── The answer read back ────────────────────────────────────────────────────────────────────

FLAT = {"outcome": "answer", "rationale": "Gi1/0 is err-disabled by BPDU guard.",
        "hypotheses": [{"claim": "A switch was plugged into an edge port.",
                        "evidence_refs": ["incident:1"], "confirm_with": "show interfaces status"}],
        "plan": [{"operation": "port-recover", "params": {
            "device": "s1", "subscriptions": [], "subscription": "", "interface": "Gi1/0",
            "cause": "bpduguard", "changes": "", "remove": []},
            "why": "Recovers the port.", "evidence_refs": ["incident:1"]}],
        "gap": {"what": "", "evidence_refs": []},
        "improvement": {"what": "", "saves": "", "steps": [], "shapes": []},
        "needs_human": False, "why_not": "",
        "reads": [{"op": "show", "args": {"device": "s1", "subscription": "",
                                          "words": "interfaces status"},
                   "why": "Is the port err-disabled?", "hypothesis": "BPDU guard"}]}


def test_a_flattened_answer_reads_in_v7_s_shape():
    m = FT.TroubleshootPlanReadsFlat.model_validate_json(json.dumps(FLAT))
    assert m.fix is None and m.gap is None and m.improvement is None
    p = m.plan[0].params
    assert (p.device, p.interface, p.cause) == ("s1", "Gi1/0", "bpduguard")
    assert p.subscriptions is None and p.subscription is None and p.changes is None \
        and p.remove is None
    args = m.reads[0].args
    assert (args.device, args.words, args.subscription) == ("s1", "interfaces status", None)


def test_a_gap_and_an_improvement_given_are_kept():
    ans = dict(FLAT, plan=[], gap={"what": "No operation clears port security.",
                                   "evidence_refs": ["incident:1"]},
               improvement={"what": "One command plan.", "saves": "2 steps", "steps": [],
                            "shapes": []})
    m = FT.TroubleshootPlanFlat.model_validate_json(json.dumps(
        {k: v for k, v in ans.items() if k != "reads"}))
    assert m.gap is not None and m.gap.what.startswith("No operation")
    assert m.improvement is not None and m.improvement.saves == "2 steps"


def test_an_answer_recorded_in_v7_s_shape_reads_back_unchanged():
    m = FT.TroubleshootPlanReadsFlat.model_validate_json(json.dumps(FLAT))
    dumped = m.model_dump(mode="json")
    assert dumped["fix"] is None and dumped["gap"] is None
    # `gateway.from_row`: a joined press rebuilds the call's answer from its row.
    again = gateway.from_row({"id": "ai-1", "verdict": "ok", "output": dumped},
                             FT.TroubleshootPlanReadsFlat)
    assert again["ok"] and again["output"].model_dump(mode="json") == dumped


# ── B: a refused request is said as one ─────────────────────────────────────────────────────

def _refuse_every_request(ai, monkeypatch):  # noqa: F811
    def send(body, key):
        ai.sent.append(body)
        raise AD.BadRequest(REFUSED, status=400)
    monkeypatch.setattr(gateway, "anthropic_adapter", type(gateway.anthropic_adapter)(
        **{**vars(gateway.anthropic_adapter), "send": send}))


def test_a_400_is_recorded_and_drawn_as_a_refused_request_never_as_no_fix(ai,  # noqa: F811
                                                                           monkeypatch):
    _refuse_every_request(ai, monkeypatch)
    iid = stopped(ai)
    r, html = press(ai, iid)
    sec = sec_of(html)
    words = ("The AI didn't answer: the request was rejected (its schema too large). Nothing "
             "was sent to any device.")
    assert r.status_code == 200 and ai.sent, "the press asked the provider"
    assert "named no fix" not in sec, sec
    assert words.rstrip(".") in sec, sec
    assert "Couldn't troubleshoot" in sec
    (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
    assert line["words"] == words and line["operation"] == ""


def test_a_line_kept_in_the_old_words_is_drawn_as_a_refused_request(ai):  # noqa: F811
    from modules.fixit import section as S
    from modules import incident_page
    iid = stopped(ai)
    inc = incident(iid)
    F.record_proposal(inc, "ai", words="The AI did not answer (bad_request: " + REFUSED + ")",
                      calls=["ai-0000000000000001"], prompt="fixit_troubleshoot.v8",
                      by="", verified="", note="")
    found = incident_page.resolve(NET, iid)
    status = S.view(NET, found)["status"]
    assert "named no fix" not in status, status
    assert "Couldn't troubleshoot: The AI didn't answer: the request was rejected (its schema " \
        "too large)" in status, status


def test_in_progress_says_the_refusal_in_one_line():
    # The operator, 2026-11-15: "Failed: request rejected. Details on the card".
    from modules import troubleshoot_job
    got = troubleshoot_job.outcome({"state": "done", "payload": {
        "state": "failed", "words": FT.not_answered_words("bad_request", REFUSED)}})
    assert got["badge"] == "failed" and got["level"] == "danger"
    assert got["line"] == "The request was rejected (its schema too large). Details on the card"
    assert "Nothing was sent to any device" in got["full"]


@pytest.mark.parametrize("detail,said", [
    (REFUSED, "the request was rejected (its schema too large)"),
    ("HTTP 429 after 3 attempts: slow down", "the provider is limiting requests"),
    ("HTTP 529: overloaded", "the provider failed (HTTP 529)"),
    ("", "provider_down"),
])
def test_each_failure_says_what_happened_and_that_no_device_was_touched(detail, said):
    got = FT.not_answered_words("provider_down" if not detail else "bad_request", detail)
    assert got.startswith(FT.NOT_ANSWERED + ": ") and said in got, got
    assert got.endswith("Nothing was sent to any device.")


