"""Every AI call names its trigger (C1843; PHASE8_PLAN 18.3 rules 1, 5 and 9; CLAUDE.md, "AI cost
safety"; `modules/ai/triggers.py`), on test_ai_gateway's world (hosted AI allowed, a key, a fake
`send`).

- **None named is refused before anything is read**: no trigger, a kind not one of the three,
  or one out of shape is refused (`trigger`), recorded, and neither the allowance, the key nor
  the record of spend is read, and nothing is sent.
- **A person** is a person: an evaluation's or a job's actor, or `unverified`, is refused; a
  person trigger outside a request is refused (a script or a job never spends under a
  person's name); inside one the trigger's person must be the request's verified actor; the
  row records the trigger and how the person was established.
- **An evaluation** names its run, its actor `evaluation:<run>` (rule 9: counted under it).
- **A background call** names a known feature, its own task, a job, a network by folder name,
  and the finding deterministic code made, of a kind its feature declares (rule 5); its actor
  is `job:<job>`.
- **By parsing:** every call of `gateway.ask` in the product passes `trigger=` (or a `**` dict
  holding it), and every feature entry the routes and evaluation scripts call takes it.
"""
import ast
import os

import pytest

from modules.ai import background, calls, connection, gateway, triggers
from tests.ai_person import pressed_by
from tests.test_ai_gateway import OK_BODY, own_record, world  # noqa: F401 (fixtures)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACTOR = "operator@example.com"
PING = ("connection_check", ("ping", 1), connection.Ping, {"word": "w"})


def _ask(world, actor=ACTOR, **kw):
    world.answer = OK_BODY
    return gateway.ask(*PING, actor=actor, send=world.send, **kw)


def _row():
    (row,) = calls.read()["rows"]
    return row


@pytest.fixture
def fake_feature(monkeypatch):
    """A background feature as S10 will add one: the connection check's task, on detections."""
    monkeypatch.setitem(background.FEATURES, "fake_loop", {
        "task": "connection_check", "words": "The fake loop", "findings": ("detection",),
        "trigger_words": "a detection rule fires", "calls_per_finding": 1,
        "frequency": lambda network: {"per_day": 4.0, "basis": "planted"}})


# ── none named ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("trigger", [None, {}, "person", {"kind": "robot", "by": ACTOR},
                                     ["person", ACTOR]],
                         ids=["none", "empty", "a-word", "unknown-kind", "a-list"])
def test_no_trigger_is_refused_before_anything_is_read(world, monkeypatch, trigger):
    read = []
    monkeypatch.setattr(gateway, "hosted_allowed", lambda: read.append("allowance") or {})
    monkeypatch.setattr(gateway, "_api_key", lambda: read.append("key") or "k")
    monkeypatch.setattr(calls, "spent_usd", lambda day: read.append("spend") or {})
    got = _ask(world, trigger=trigger)
    assert got["ok"] is False and got.get("error") == "trigger", got
    assert got.get("detail", "") == f"the call {triggers.NONE_WORDS}"
    assert read == [] and world.sent == [], "nothing read, nothing sent"
    row = _row()
    assert row["verdict"] == "trigger" and row["trigger"] is None and row["actor"] == ACTOR


def test_a_call_naming_its_person_is_recorded_with_it(world):
    with pressed_by(ACTOR):
        got = _ask(world, trigger=triggers.person(ACTOR))
    assert got["ok"] is True and len(world.sent) == 1
    assert _row()["trigger"] == {"kind": "person", "by": ACTOR, "verified": "access"}


def test_a_person_trigger_outside_a_request_is_refused(world):
    """A script or a job never spends under a person's name (the parent's decision,
    2026-10-27): scripts name an evaluation run, jobs a background feature."""
    got = _ask(world, trigger=triggers.person(ACTOR))
    assert got.get("error") == "trigger" and world.sent == []
    assert got.get("detail", "") == (
        f"a person trigger ({ACTOR!r}) outside a request: only a request that verified its "
        "person spends under a person's name; a script names an evaluation run, a job a "
        "background feature")
    assert _row()["verdict"] == "trigger" and _row()["trigger"] is None


# ── a person ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("by", ["evaluation:run-1", "job:j1", "unverified", "", "  ", None, 7])
def test_a_person_trigger_that_names_no_person_is_refused(world, by):
    got = _ask(world, actor=by if isinstance(by, str) else ACTOR,
               trigger={"kind": "person", "by": by})
    assert got.get("error") == "trigger" and world.sent == []
    assert f"a person trigger names a verified person; {by!r} is not one" in got.get("detail", "")


def test_an_actor_that_is_not_the_triggers_is_refused(world):
    with pressed_by(ACTOR):
        got = _ask(world, actor="alex@example.com", trigger=triggers.person(ACTOR))
    assert got.get("error") == "trigger" and world.sent == []
    assert got.get("detail", "") == ("the call's actor 'alex@example.com' is not its person "
                                     f"trigger's ({ACTOR!r})")


def test_inside_a_request_the_person_is_the_requests_verified_actor(world):
    with pressed_by("alex@example.com"):
        got = _ask(world, trigger=triggers.person(ACTOR))
    assert got.get("error") == "trigger" and world.sent == []
    assert got.get("detail", "") == (f"the person trigger names {ACTOR!r}, and this request's "
                                     "verified actor is 'alex@example.com'")
    with pressed_by(ACTOR):
        got = _ask(world, trigger=triggers.person(ACTOR))
    assert got["ok"] is True and len(world.sent) == 1
    assert calls.read()["rows"][0]["trigger"] == {"kind": "person", "by": ACTOR,
                                                  "verified": "access"}


# ── an evaluation ─────────────────────────────────────────────────────────────────────────────

def test_an_evaluation_names_its_run_and_is_recorded_under_it(world):
    got = _ask(world, actor="evaluation:nl-cases-20261027T0900Z",
               trigger=triggers.evaluation("evaluation:nl-cases-20261027T0900Z"))
    assert got["ok"] is True
    assert _row()["trigger"] == {"kind": "evaluation", "run": "nl-cases-20261027T0900Z"}


@pytest.mark.parametrize("actor", [ACTOR, "evaluation:", "evaluation:has space"])
def test_an_evaluation_without_a_run_is_refused(world, actor):
    got = _ask(world, actor=actor, trigger=triggers.evaluation(actor))
    assert got.get("error") == "trigger" and world.sent == []
    assert "an evaluation trigger names its run" in got.get("detail", "")


# ── a background job, on a finding ────────────────────────────────────────────────────────────

def _bg(**over):
    t = triggers.background("fake_loop", "j1", "Lab", "detection", "scan-192.0.2.7")
    t.update(over)
    return t


def test_a_background_trigger_names_a_feature_mercury_knows(world):
    got = _ask(world, actor="job:j1", trigger=_bg())
    assert got.get("error") == "trigger" and world.sent == []
    # The SDN loop's classify (PHASE8_PLAN 17.1 S7) is the one feature Mercury declares.
    assert got.get("detail", "") == ("'fake_loop' is not a background feature Mercury knows; "
                                     "known: sdn_classify")


@pytest.mark.parametrize("over,said", [
    ({"finding": None}, "calls the model only on a finding deterministic code made"),
    ({"finding": {"kind": "detection", "id": ""}}, "calls the model only on a finding"),
    ({"finding": {"kind": "a hunch", "id": "x"}}, "(detection, with its id)"),
    ({"job": ""}, "a background trigger names its job's id; '' is not one"),
    ({"network": "Lab"}, "names its network by its folder name; 'Lab' is not one"),
    ({"network": ""}, "names its network by its folder name; '' is not one"),
], ids=["no-finding", "finding-without-id", "finding-of-another-kind", "no-job",
        "network-by-display-name", "no-network"])
def test_a_background_trigger_out_of_shape_is_refused(world, fake_feature, over, said):
    got = _ask(world, actor="job:j1", trigger=_bg(**over))
    assert got.get("error") == "trigger" and world.sent == [] and said in got.get("detail", ""), got


def test_a_background_feature_calls_only_its_own_task(world, fake_feature, monkeypatch):
    monkeypatch.setitem(background.FEATURES["fake_loop"], "task", "explain")
    got = _ask(world, actor="job:j1", trigger=_bg())
    assert got.get("detail", "") == "the background feature fake_loop calls the task explain, not " \
                            "connection_check"


def test_a_background_calls_actor_is_its_job(world, fake_feature):
    got = _ask(world, actor=ACTOR, trigger=_bg())
    assert got.get("error") == "trigger"
    assert got.get("detail", "") == f"the call's actor {ACTOR!r} is not its background trigger's ('job:j1')"


def test_a_background_trigger_is_recorded_whole(world, fake_feature, monkeypatch):
    monkeypatch.setattr(background, "admit", lambda t: "off, planted")
    got = _ask(world, actor="job:j1", trigger=_bg())
    assert got.get("error") == "feature_off"
    assert _row()["trigger"] == {"kind": "background", "feature": "fake_loop", "job": "j1",
                                 "network": "lab", "finding": {"kind": "detection",
                                                               "id": "scan-192.0.2.7"}}


# ── by parsing: every caller passes it ────────────────────────────────────────────────────────

def _product_files():
    from tests.source_index import tracked
    paths = tracked("app.py") + tracked("routes", suffix=".py", recursive=False)
    paths += tracked("modules", suffix=".py")
    paths += [os.path.join(ROOT, "scripts", n) for n in ("nmas-nl-cases", "nmas-intent-cases",
                                                         "nmas-pack-replay")]
    return paths


def _passes_trigger(call, func) -> bool:
    if any(k.arg == "trigger" for k in call.keywords):
        return True
    # `**kw`, where kw is a dict literal in the same function holding "trigger".
    for k in call.keywords:
        if k.arg is None and isinstance(k.value, ast.Name):
            for node in ast.walk(func):
                if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
                        and any(isinstance(t, ast.Name) and t.id == k.value.id
                                for t in node.targets)
                        and any(isinstance(key, ast.Constant) and key.value == "trigger"
                                for key in node.value.keys)):
                    return True
    return False


#: What the routes and scripts call, each a way into the gateway that must carry the trigger.
ENTRIES = {"ask", "check", "explain", "explain_pack", "press", "change", "metrics", "logs"}
OWNERS = {"gateway", "connection", "explain", "explain_answers", "intent_words", "nl_query"}


def missing_triggers(texts: dict) -> list:
    """``["<file>:<line> <call>"]``: each call of a gateway entry (`OWNERS`' `ENTRIES`) that
    passes no trigger."""
    out = []
    for rel, text in texts.items():
        tree = ast.parse(text)
        # Each function with what it holds, so a `**kw` built in an enclosing function (a
        # nested follow-up's) is found where it was built.
        scopes = [(n, set(ast.walk(n))) for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node in ast.walk(tree):
            f = getattr(node, "func", None)
            if not (isinstance(node, ast.Call) and isinstance(f, ast.Attribute)
                    and f.attr in ENTRIES and isinstance(f.value, ast.Name)
                    and f.value.id in OWNERS):
                continue
            around = [func for func, held in scopes if node in held] or [tree]
            if not any(_passes_trigger(node, func) for func in around):
                out.append(f"{rel}:{node.lineno} {f.value.id}.{f.attr}")
    return sorted(out)


def test_every_caller_of_the_gateway_and_its_features_passes_a_trigger():
    texts = {}
    for p in _product_files():
        with open(p, encoding="utf-8") as fh:
            texts[os.path.relpath(p, ROOT)] = fh.read()
    assert len(texts) > 100, "the scan's floor: the product's files"
    calls_seen = sum(1 for t in texts.values() for _ in
                     __import__("re").finditer(r"\bgateway\.ask\(", t))
    assert calls_seen >= 8, "the scan's floor: the gateway's callers"
    assert missing_triggers(texts) == []


def test_the_scan_finds_a_planted_call_without_one():
    planted = {"planted.py": ("from modules.ai import gateway, nl_query\n"
                              "def a():\n    return gateway.ask('t', p, s, {}, actor='x')\n"
                              "def b():\n    kw = {'actor': 'x'}\n"
                              "    return nl_query.metrics('L', 'q', **kw)\n"
                              "def c():\n    kw = {'actor': 'x', 'trigger': t}\n"
                              "    return nl_query.logs('L', 'q', **kw)\n")}
    assert missing_triggers(planted) == ["planted.py:3 gateway.ask",
                                         "planted.py:6 nl_query.metrics"]


# ── the tier hand check's survivors (C1843) ──────────────────────────────────────────────────

def test_a_trigger_taken_says_no_why_and_names_itself(world, fake_feature):
    # `check`'s answer is its docstring's shape, {"ok", "why", "trigger"}, with an empty why when
    # the trigger is taken, for each kind.
    run = "evaluation:nl-cases-20261027T0900Z"
    assert triggers.check(triggers.evaluation(run), run, "connection_check") == {
        "ok": True, "why": "", "trigger": {"kind": "evaluation", "run": "nl-cases-20261027T0900Z"}}
    t = _bg()
    assert triggers.check(t, "job:j1", "connection_check") == {"ok": True, "why": "", "trigger": t}
    with pressed_by(ACTOR):
        assert triggers.check(triggers.person(ACTOR), ACTOR, "connection_check") == {
            "ok": True, "why": "", "trigger": {"kind": "person", "by": ACTOR,
                                               "verified": "access"}}


def test_a_person_trigger_naming_an_evaluation_says_each_kind_names_its_own(world):
    got = _ask(world, actor="job:j1", trigger={"kind": "person", "by": "job:j1"})
    assert got.get("detail", "") == ("a person trigger names a verified person; 'job:j1' is not "
                                     "one (an evaluation or a job names its own kind)")


@pytest.mark.parametrize("over,said", [
    ({"feature": ["fake_loop"]}, "['fake_loop'] is not a background feature Mercury knows"),
    ({"network": 7}, "names its network by its folder name; 7 is not one"),
], ids=["feature-not-a-name", "network-not-a-name"])
def test_a_background_trigger_whose_names_are_not_text_is_refused_not_raised(world, fake_feature,
                                                                             over, said):
    got = _ask(world, actor="job:j1", trigger=_bg(**over))
    assert got.get("error") == "trigger" and world.sent == [] and said in got.get("detail", ""), got


def test_the_refusals_list_every_feature_and_finding_kind(world, fake_feature, monkeypatch):
    monkeypatch.setitem(background.FEATURES, "fake_digest", dict(background.FEATURES["fake_loop"]))
    got = _ask(world, actor="job:j1", trigger=_bg(feature="a_dream"))
    assert got.get("detail", "").endswith("known: fake_digest, fake_loop, sdn_classify")
    monkeypatch.setitem(background.FEATURES["fake_loop"], "findings", ("detection", "digest"))
    got = _ask(world, actor="job:j1", trigger=_bg(finding={"kind": "a hunch", "id": "x"}))
    assert "(detection or digest, with its id)" in got.get("detail", "")
