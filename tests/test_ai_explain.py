"""P1's Explain (PHASE8_PLAN 15.9, card P1's one AI step; modules/ai/explain.py), against
planted answers (live cases wait for Allow): the pack is tests/test_evidence_pack.py's, built
from the real captures by the real builder (r1 by IPv6, the planted community line in its logs,
an instruction planted in an interface description), the gateway allowed with a fake `send`.

- The request: its prompt and the pack's format as the cached prefix, exactly three data
  blocks (the network around the device, the pack and the alert, in that order; prompt v2,
  tests/test_ai_explain_topology.py), no tool offered, the prompt under its task's bound; the planted
  instruction only in the data; a stored secret's value the pack kept is not in the bytes sent.
- The check: an answer citing only the pack's references and naming a read on the allowlist is
  shown; a reference the pack does not hold, a confirming command that is not a read, an
  answer citing nothing, more than three hypotheses, or a schema failure is "couldn't analyse"
  and nothing of it is shown; a refusal says why.
- The pack: one changed since it was built is not explained; one not kept says so; hosted AI
  off is said as information, the pack still drawn.
- The card, through the real routes and in a real browser: Explain draws the hypotheses in the
  pack, each reference a link to its piece.
"""
import json
import re

import pytest

from modules.ai import triggers
from tests.ai_person import pressed_by
from modules import evidence_pack as EP
from modules.ai import anthropic_adapter as A
from modules.ai import calls, explain, gateway, profiles
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import (INJECTION, V6, _alerts, _build, _section,  # noqa: F401
                                      pack_lab)

KEY = "sk-planted-test-key-0123456789"


@pytest.fixture
def world(pack_lab, monkeypatch, tmp_path):
    settings = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                              "reason": "the lab's proof of concept"},
                "ai_cap_usd_per_day": 1.50}
    from modules import settings_schema
    monkeypatch.setattr(settings_schema, "get_setting", lambda k, d=None: settings.get(k, d))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    # The AI controls ask whether a key is stored, presence only (modules/ai/controls.py).
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    # The answers kept with their packs (C1853): each test its own, as its record of calls.
    from modules.ai import explain_answers
    monkeypatch.setattr(explain_answers, "_path", lambda: str(tmp_path / "explain_answers.jsonl"))
    pack = _build(_alerts(V6, extra_labels={"ifAlias": INJECTION}))
    assert EP.record(pack)["ok"]

    class W:
        pass
    w = W()
    w.lab, w.pack, w.sent, w.answer, w.settings = pack_lab, pack, [], None, settings

    def send(body, key):
        w.sent.append({"bytes": json.dumps(body), "body": body})
        # As a model answers: in the shape the request's schema asks for, so one planted
        # answer serves a v1 call (no `checked`) and a v4 call alike (C1742).
        asked = body["output_config"]["format"]["schema"].get("properties") or {}
        ans = ({k: v for k, v in w.answer.items() if k in asked}
               if isinstance(w.answer, dict) and asked else w.answer)
        return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(
            ans) if not isinstance(ans, str) else ans}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 4000, "output_tokens": 300}},
            attempts=1, latency_s=0.9)
    w.send = send
    monkeypatch.setattr(A, "send", send)
    return w


def _refs(pack, section):
    return [p["ref"] for p in _section(pack, section)["pieces"]]


def _answer(pack, **over):
    a = {"outcome": "answer",
         "rationale": "Input errors rose on r1 while its log shows a configuration change.",
         "hypotheses": [{"claim": "A configuration change on r1 preceded the errors.",
                         "evidence_refs": [_refs(pack, "logs")[0], "alert"],
                         "confirm_with": "show interfaces | include errors"}],
         "checked": [], "needs_human": False, "why_not": ""}
    a.update(over)
    return a


def _explain(world):
    with pressed_by("operator@example.com"):
        return explain.explain(world.pack["id"], actor="operator@example.com",
                               trigger=triggers.person("operator@example.com"), send=world.send,
                               today="2026-10-25")


# ---------------------------------------------------------------------------- the request

def test_the_request_is_the_pack_as_data_with_no_tool(world):
    from modules.ai import prompts
    world.answer = _answer(world.pack)
    assert _explain(world)["ok"] is True
    body = world.sent[0]["body"]
    assert "tools" not in body and set(body) == {"model", "max_tokens", "system", "messages",
                                                 "output_config"}
    assert body["model"] == profiles.TASKS["explain"]["model"]
    assert body["system"][0]["text"] == prompts.load(*explain.PROMPT)["text"]
    assert "evidence pack has sections" in body["system"][1]["text"]
    data = re.findall(r'<data name="([^"]+)">', body["messages"][0]["content"])
    # Prompt v2 (15.15): the network around the device beside the pack, the alert last
    # (tests/test_ai_explain_topology.py holds what the topology carries).
    assert data == ["network_topology", "pack", "the_alert"]
    assert gateway.prompt_tokens(body) <= profiles.TASKS["explain"]["max_prompt_tokens"]


def test_the_planted_instruction_rides_only_as_data(world):
    world.answer = _answer(world.pack)
    _explain(world)
    body = world.sent[0]["body"]
    marker = "Ignore all previous instructions"
    assert marker in body["messages"][0]["content"]
    assert marker not in json.dumps(body["system"])


def test_a_stored_secret_the_pack_kept_is_masked_in_the_bytes_sent(world, monkeypatch):
    """The pack was built before this value was a known secret, so it holds it; the egress
    mask, by value, keeps it from the bytes sent."""
    from modules import redact
    alias = _section(world.pack, "alert")["pieces"][0]["labels"]["ifAlias"]
    stored = alias.split()[2]                       # "previous", of the planted description
    assert len(stored) >= 8 and stored in json.dumps(world.pack)
    monkeypatch.setattr(redact, "known_secret_values", lambda: {stored: "Lab:enable"})
    world.answer = _answer(world.pack)
    assert _explain(world)["ok"] is True
    assert stored not in world.sent[0]["bytes"]


# ---------------------------------------------------------------------------- the check

def test_an_answer_citing_the_pack_with_an_allowed_read_is_shown(world):
    world.answer = _answer(world.pack)
    got = _explain(world)
    assert got["ok"] is True
    assert got["answer"]["hypotheses"][0]["confirm_with"] == "show interfaces | include errors"


@pytest.mark.parametrize("change,words", [
    ({"evidence_refs": ["logs:999"]}, "cites 'logs:999', which is not in the pack"),
    ({"evidence_refs": []}, "cites nothing in the pack"),
    ({"confirm_with": "configure terminal"}, "is not a read Mercury allows"),
    ({"confirm_with": "reload"}, "is not a read Mercury allows"),
])
def test_an_answer_the_pack_does_not_bear_out_is_couldnt_analyse(world, change, words):
    a = _answer(world.pack)
    a["hypotheses"][0].update(change)
    world.answer = a
    got = _explain(world)
    assert got["ok"] is False and got["error"] == "couldnt_analyse", got
    assert words in got["detail"] and "answer" not in got


def test_more_than_three_hypotheses_is_couldnt_analyse(world):
    a = _answer(world.pack)
    a["hypotheses"] = a["hypotheses"] * 4
    world.answer = a
    assert _explain(world)["error"] == "couldnt_analyse"


def test_a_schema_failure_shows_nothing(world):
    world.answer = '{"outcome": "answer", "rationale": "x"}'
    got = _explain(world)
    assert got["ok"] is False and got["error"] == "schema" and "answer" not in got


def test_a_refusal_says_why(world):
    world.answer = _answer(world.pack, outcome="refuse", rationale="", hypotheses=[],
                           needs_human=True, why_not="every section is unreadable")
    got = _explain(world)
    assert got["error"] == "unanswerable" and "every section is unreadable" in got["detail"]


# ---------------------------------------------------------------------------- the pack

def test_a_pack_changed_since_it_was_built_is_not_explained(world, monkeypatch):
    changed = json.loads(json.dumps(world.pack))
    changed["rule"] = "something else"
    monkeypatch.setattr(EP, "find", lambda pid: (changed, "ok", ""))
    got = _explain(world)
    assert got["error"] == "changed" and world.sent == []


def test_a_pack_not_kept_says_so(world):
    with pressed_by("operator@example.com"):
        got = explain.explain("ep-0000000000", actor="operator@example.com",
                              trigger=triggers.person("operator@example.com"), send=world.send)
    assert got["error"] == "no_pack" and world.sent == []


def test_hosted_ai_off_sends_nothing_and_the_pack_still_draws(world):
    world.settings.pop("ai_hosted")
    got = _explain(world)
    assert got["error"] == "ai_off" and world.sent == []
    from html import unescape
    c = world.lab["client"]
    html = unescape(c.get(f"/v2/monitoring/alerts/pack/{world.pack['id']}").get_data(as_text=True))
    assert "Explain" in html and 'data-op="alert-evidence"' in html
    r = c.post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
               headers={"HX-Request": "true"})
    assert "hosted AI is off until it is allowed" in unescape(r.get_data(as_text=True))


def test_explain_is_an_ai_control_and_the_pack_stays_drawn(world, monkeypatch):
    """PHASE8_PLAN 15.13, through the pack's real route: Explain carries the AI mark with its
    task, model and cap; while hosted AI cannot answer it is disabled with the reason in place
    (the AI card's link for a person who may configure), and the evidence pack is drawn whole
    beside it."""
    from tests import ai_controls_check as AIC

    def get():
        return world.lab["client"].get(
            f"/v2/monitoring/alerts/pack/{world.pack['id']}").get_data(as_text=True)

    def parity(html):
        assert f'data-pack="{world.pack["id"]}"' in html
        assert html.count('class="pack-section"') == len(world.pack["sections"]), \
            "every section of the pack is drawn"
    AIC.check_screen(monkeypatch, get, "explain", parity)


# ---------------------------------------------------------------------------- the card

def test_explain_draws_the_hypotheses_in_the_pack(world):
    from html import unescape
    world.answer = _answer(world.pack)
    c = world.lab["client"]
    r = c.post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
               headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and "A configuration change on r1 preceded the errors." in html
    ref = _refs(world.pack, "logs")[0]
    assert f'href="#{world.pack["id"]}-{ref}"' in html
    assert "show interfaces | include errors" in html and "Nothing was run" in html
    page = unescape(c.get(f"/v2/monitoring/alerts/pack/{world.pack['id']}").get_data(as_text=True))
    assert f'id="{world.pack["id"]}-{ref}"' in page, "a cited piece has its anchor"


def test_a_couldnt_analyse_shows_none_of_the_answer(world):
    from html import unescape
    a = _answer(world.pack)
    a["hypotheses"][0]["evidence_refs"] = ["logs:999"]
    world.answer = a
    r = world.lab["client"].post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
                                 headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert "Not explained: couldn't analyse" in html
    assert "A configuration change on r1" not in html


def test_explain_in_a_real_browser(world):
    """In Firefox: the card opened, its pack drawn, Explain pressed: the hypotheses draw inside
    the pack, the cited reference a link to its piece; nothing scrolls sideways at 1440."""
    from tests import browser
    from tests.test_evidence_pack import _with_packs
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as APP

    value = _with_packs(world.lab)
    six = next(i for i in EP.firing(value) if i["labels"]["instance"] == V6)
    key = EP.alert_key(six)
    pack, _s, _e = EP.find(EP.pack_id(key))
    world.answer = _answer(pack)
    sel = f'details[data-keep="pack-{key}"]'
    with browser.Served(APP.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1440, "height": 1000})
            b.go(srv.url("/v2/monitoring/alerts"))
            b.wait_for("return !!(window.htmx && document.querySelector('details.pack-card'))")
            b.click(f"{sel} > summary")
            # The form arrives in a swap: clicked before htmx has processed it, it would submit
            # as a plain form and leave the page (a race seen twice in three runs).
            b.wait_for(f"var f = document.querySelector('{sel} form.explain-ask');"
                       "return !!(f && f['htmx-internal-data'])", 15)
            b.js(f"document.querySelector('{sel} [data-op=alert-evidence]').click(); return 1")
            try:
                b.wait_for(f"return !!document.querySelector('{sel} .explain-list li')", 15)
            except AssertionError:
                raise AssertionError(b.js("return location.href + ' | ' + "
                                          "document.body.innerHTML.slice(0, 400)")) from None
            claim = b.js(f"return document.querySelector('{sel} .explain-list li strong')"
                         ".textContent")
            href = b.js(f"return document.querySelector('{sel} .explain-list a.pack-ref')"
                        ".getAttribute('href')")
            target = b.js(f"return !!document.getElementById("
                          f"'{href[1:]}')") if href else False
            wide = b.js("return document.documentElement.scrollWidth <= window.innerWidth")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert claim == "A configuration change on r1 preceded the errors.", claim
    assert target is True and wide is True, (href, target, wide)


def test_the_schema_is_registered_and_committed():
    from modules.ai import schemas
    assert schemas.REGISTRY[("explain", 1)] is explain.Explanation
    with open(schemas.committed_path("explain", 1), encoding="utf-8") as fh:
        assert fh.read() == schemas.committed_text(explain.Explanation)
    assert schemas.REGISTRY[("explain", 2)] is explain.ExplanationV2
    with open(schemas.committed_path("explain", 2), encoding="utf-8") as fh:
        assert fh.read() == schemas.committed_text(explain.ExplanationV2)


def test_each_prompt_asks_for_the_schema_it_was_written_for(world):
    """v1 to v3 knew no "no fault found" (a replay asks them as they were); v4 does (C1742)."""
    assert explain.PROMPT == ("explain", 4)
    assert {v: s.__ai_schema__ for v, s in explain.SCHEMA_OF.items()} == {
        1: ("explain", 1), 2: ("explain", 1), 3: ("explain", 1), 4: ("explain", 2),
        5: ("explain", 2), 6: ("explain", 3)}
    world.answer = {k: v for k, v in _answer(world.pack).items() if k != "checked"}
    with pressed_by("operator@example.com"):
        got = explain.explain_pack(world.pack, actor="operator@example.com",
                                   trigger=triggers.person("operator@example.com"), send=world.send,
                                   today="2026-10-25", prompt=("explain", 3))
    assert got["ok"] is True, got
    assert world.sent[-1]["body"]["output_config"]["format"]["schema"]["properties"][
        "outcome"]["$ref"] == "#/$defs/Outcome"
    assert "no_fault_found" not in json.dumps(world.sent[-1]["body"]["output_config"])
    world.answer = _answer(world.pack)
    assert _explain(world)["ok"] is True
    assert "no_fault_found" in json.dumps(world.sent[-1]["body"]["output_config"])


# ------------------------------------- v6, the network-context version (2026-10-26)

V6_PROMPT = ("explain", 6)


def test_v6_is_a_candidate_built_from_v4_and_says_what_it_adds():
    """The operator, 2026-10-26: built from v4 (v5 stays rejected) with the coverage line,
    the needs wiring, the pack's endpoints and the rebuilt-evidence marks (C1808)."""
    from modules.ai import prompts, schemas
    assert V6_PROMPT in explain.CANDIDATES and explain.PROMPT == ("explain", 4)
    assert schemas.REGISTRY[("explain", 3)] is explain.ExplanationV3
    with open(schemas.committed_path("explain", 3), encoding="utf-8") as fh:
        assert fh.read() == schemas.committed_text(explain.ExplanationV3)
    text = " ".join(prompts.load(*V6_PROMPT)["text"].split())
    for said in ("coverage header", "never infer it from another layer", '"endpoints"',
                 '"looked_up"', '"provenance"', "never call it observed",
                 "its absence is no evidence either way"):
        assert said in text, said
    v4 = " ".join(prompts.load("explain", 4)["text"].split())
    assert "common cause" not in text and "common cause" not in v4, "v5's line stays out"


def test_v6_sends_nothing_looked_up_first_and_a_need_is_looked_up_once(world, monkeypatch):
    """C1780: v6's first call says nothing was looked up; an answer naming a need is looked up
    once (`needs.run`) and asked once more, the follow-up's answer the one checked and shown,
    the cost the round's."""
    from modules.ai import needs
    monkeypatch.setitem(needs._LOOKUPS, needs.NeedKind.neighbour,
                        lambda net, subject: ({"Gi0/1": "s4"}, ""))
    monkeypatch.setattr("modules.ai.egress_classes.topology_allowed",
                        lambda net: {"allowed": True, "why": ""})
    answers = [dict(_answer(world.pack), needs=[{"kind": "neighbour", "subject": "r1"}]),
               dict(_answer(world.pack), needs=[])]
    plain = world.send

    def send(body, key):
        world.answer = answers.pop(0)
        return plain(body, key)
    with pressed_by("operator@example.com"):
        got = explain.explain_pack(world.pack, actor="operator@example.com",
                                   trigger=triggers.person("operator@example.com"), send=send,
                                   today="2026-10-25", prompt=V6_PROMPT)
    assert got["ok"] is True and len(world.sent) == 2, got
    first, second = (s["body"]["messages"][0]["content"] for s in world.sent)
    assert '<data name="looked_up">\n(nothing looked up)\n</data>' in first
    assert 'neighbour r1: {"Gi0/1": "s4"}' in second
    assert got["parent_call_id"] and got["parent_call_id"] != got["call_id"]
    assert "neighbour r1: fulfilled" in got["needs_said"]


def _sent_refs(sel, name):
    return [p["ref"] for s in sel["sections"] if s.get("name") == name
            for p in s.get("pieces") or []]


def test_v6_under_the_budget_drops_in_order_and_never_the_onset_window(world, monkeypatch):
    """The operator, 2026-10-26: v6 under the context budget rule. The network context's
    parts in their order, then the pack's (History older than the onset window, oldest first;
    log lines outside it, farthest first; health of devices two hops out, then one), one
    piece at a time, each layer's source last; never a log line inside the onset window,
    never the alert's own device's figures; what was dropped said and kept."""
    from modules.ai import profiles
    pack = world.pack
    topo = explain.topology(pack)
    schema = explain.SCHEMA_OF[6]
    whole = explain.budgeted(pack, topo, V6_PROMPT, schema)
    assert whole["said"]["dropped"] == [] and whole["said"]["pack_dropped"] == {}
    full = whole["said"]["estimate"]
    order = explain._pack_drop_order(pack, explain.sent_sections(pack, topo))
    assert order, "the world's pack holds droppable pieces"
    classes = [c for c, _n, _r in order]
    assert classes == sorted(classes), "History, then log lines, then health"
    onset = explain._epoch(pack["onset"])
    sections = {s["name"]: s for s in explain.sent_sections(pack, topo)}
    # The onset window: the health figures' own, 15 minutes before the onset to the alert's
    # time (the pack's log lines run 15 minutes past the onset; those after the alert fired
    # are the least relevant).
    fired = max(onset, explain._epoch(sections["alert"]["pieces"][0].get("starts_at")))
    inside = {p["ref"] for p in sections.get("logs", {}).get("pieces") or []
              if onset - explain.ONSET_WINDOW_S <= explain._epoch(p.get("at")) <= fired}
    own = {p["ref"] for p in sections.get("health", {}).get("pieces") or [] if not p.get("hop")}
    assert not ({r for _c, _n, r in order} & (inside | own))
    for budget in (full - 50, full - 400, full // 2, 10):
        monkeypatch.setitem(profiles.TASKS, "explain",
                            dict(profiles.TASKS["explain"], max_prompt_tokens=budget))
        sel = explain.budgeted(pack, topo, V6_PROMPT, schema)
        said = sel["said"]
        assert said["budget"] == budget and said["dropped"], budget
        if topo["sent"]:
            from modules.ai import nl_query
            assert said["dropped"][0] == nl_query.CONTEXT_DROPS[0], "the device index first"
            if said["pack_dropped"]:
                assert said["dropped"][:4] == list(nl_query.CONTEXT_DROPS[:4]), \
                    "the network context's four parts before any pack piece"
        assert set(_sent_refs(sel, "logs")) >= (inside & {p["ref"] for p in sections.get(
            "logs", {}).get("pieces") or []}), "never a line inside the onset window"
        assert set(_sent_refs(sel, "health")) >= own, "never the alert's own device"
        if said["estimate"] > budget:
            # Nothing fits: everything droppable was dropped, the source last.
            assert sum(said["pack_dropped"].values()) == len(order), budget
            assert said["dropped"][-1] == "each layer's source", budget
        else:
            assert said["estimate"] <= budget


def test_v6_s_answer_carries_its_level_and_the_prompt_says_omitted_for_size(world):
    from modules.ai import prompts
    world.answer = dict(_answer(world.pack), needs=[])
    with pressed_by("operator@example.com"):
        got = explain.explain_pack(world.pack, actor="operator@example.com",
                                   trigger=triggers.person("operator@example.com"), send=world.send,
                                   today="2026-10-25", prompt=V6_PROMPT)
    assert got["ok"] is True and got["context"]["level"] == 0, got
    assert got["context"]["budget"] == 20000 and got["context"]["dropped"] == []
    text = " ".join(prompts.load(*V6_PROMPT)["text"].split())
    for said in ('"omitted for size"', "is not the same as not_collected or not read",
                 "Lines inside the onset window, and the alert's own device's figures, are "
                 "never left out", "set needs_human true"):
        assert said in text, said


def test_v4_sends_no_looked_up_block(world):
    world.answer = _answer(world.pack)
    assert _explain(world)["ok"] is True
    assert "looked_up" not in world.sent[-1]["body"]["messages"][0]["content"]


# ------------------------------------------------------------ no fault found (C1742)

def _health_or_logs(pack):
    """Pieces of the pack that were read: its log lines (this world's pack predates nothing:
    its sections are the builder's)."""
    return _refs(pack, "logs")[:2]


def _no_fault(pack, **over):
    return _answer(pack, **dict({"outcome": "no_fault_found", "hypotheses": [],
                                 "rationale": "r1's log lines show nothing wrong.",
                                 "checked": _health_or_logs(pack)}, **over))


def test_no_fault_found_citing_what_it_checked_is_shown(world):
    world.answer = _no_fault(world.pack)
    got = _explain(world)
    assert got["ok"] is True, got
    assert got["answer"]["outcome"] == "no_fault_found" and got["answer"]["hypotheses"] == []
    assert [c["ref"] for c in got["answer"]["checked"]] == _health_or_logs(world.pack)
    assert all(c["in_pack"] for c in got["answer"]["checked"])


@pytest.mark.parametrize("over,words", [
    ({"checked": []}, "finds no fault but cites no evidence it checked"),
    ({"checked": ["logs:999"]}, "the evidence checked cites 'logs:999', which is not in the pack"),
    ({"hypotheses": None}, "finds no fault yet holds 1 hypotheses"),
])
def test_no_fault_found_the_pack_does_not_bear_out_is_couldnt_analyse(world, over, words):
    a = _no_fault(world.pack)
    if over.get("hypotheses", 0) is None:
        a["hypotheses"] = _answer(world.pack)["hypotheses"]
    else:
        a.update(over)
    world.answer = a
    got = _explain(world)
    assert got["ok"] is False and got["error"] == "couldnt_analyse", got
    assert words in got["detail"] and "answer" not in got


def test_evidence_checked_that_was_not_read_is_couldnt_analyse(world):
    """Healthy evidence is evidence that was read: a section unreadable or absent is not."""
    import copy
    pack = copy.deepcopy(world.pack)
    history = _section(pack, "history")
    history["state"] = "unreadable"
    answer = explain.ExplanationV2.model_validate_json(
        json.dumps(_no_fault(pack, checked=["history"])))
    assert explain.check(answer, pack) == (
        "the evidence checked cites 'history', which was not read (unreadable)")
    history["state"] = "empty"
    assert explain.check(answer, pack) == "", "empty was read: Loki answered, with nothing"


def test_a_piece_s_own_state_is_what_it_describes_not_whether_it_was_read(world):
    """C1761 (measured live, 2026-10-26: case 2's replay on v4 answered no fault found citing
    r1's neighbours, and was refused, "cites 'neighbours:2', which was not read (up)"). An
    adjacency's "up" and an alert's own state say what they describe; whether a piece was
    read is its section's state."""
    import copy
    pack = copy.deepcopy(world.pack)
    described = [p for name in ("alert", "neighbours", "intent")
                 for p in _section(pack, name)["pieces"]
                 if p.get("state") and p["state"] not in explain.READ_STATES]
    assert {r["ref"].split(":")[0] for r in described} >= {"alert", "neighbours"}, \
        "the floor: pieces whose own state is not a read state"
    answer = explain.ExplanationV2.model_validate_json(
        json.dumps(_no_fault(pack, checked=[p["ref"] for p in described])))
    assert explain.check(answer, pack) == ""
    neighbours = _section(pack, "neighbours")
    neighbours["state"] = "unreadable"
    first = next(p["ref"] for p in described if p["ref"].startswith("neighbours:"))
    assert explain.check(answer, pack) == (
        f"the evidence checked cites {first!r}, which was not read (unreadable)")


def test_a_health_figure_is_read_when_it_was_measured(world):
    """A health figure carries its own read state (C1761's one such section): one not measured
    is not healthy evidence, though its section was read."""
    import copy
    pack = copy.deepcopy(world.pack)
    # Each figure names its device as the builder's do (evidence_health._piece): the answer
    # names r1, so its citation must be r1's (C1897).
    health = {"ref": "health", "name": "health", "state": "ok", "pieces": [
        {"ref": "health:dev:u1:cpu", "dev": "dev:u1", "device": "r1", "figure": "cpu",
         "state": "ok"},
        {"ref": "health:dev:u1:scrapes", "dev": "dev:u1", "device": "r1", "figure": "scrapes",
         "state": "unreadable"}]}
    pack["sections"] = [s for s in pack["sections"] if s["name"] != "health"] + [health]
    ok = explain.ExplanationV2.model_validate_json(
        json.dumps(_no_fault(pack, checked=["health:dev:u1:cpu"])))
    assert explain.check(ok, pack) == ""
    not_measured = explain.ExplanationV2.model_validate_json(
        json.dumps(_no_fault(pack, checked=["health:dev:u1:scrapes"])))
    assert explain.check(not_measured, pack) == (
        "the evidence checked cites 'health:dev:u1:scrapes', which was not read (unreadable)")


def test_no_fault_found_is_drawn_with_what_it_checked(world):
    from html import unescape
    world.answer = _no_fault(world.pack)
    r = world.lab["client"].post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
                                 headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and "no fault found" in html
    assert "r1's log lines show nothing wrong." in html
    for ref in _health_or_logs(world.pack):
        assert f'href="#{world.pack["id"]}-{ref}"' in html
    assert "only what the pack holds was checked" in html and "Nothing was run" in html
    assert "explain-list" not in html


def test_an_explanation_stopped_at_max_tokens_shows_nothing(world):
    """A complete, valid explanation whose stop is max_tokens shows nothing (the operator,
    2026-10-25; tests/test_ai_truncated_answers.py)."""
    from tests.test_ai_truncated_answers import _cut
    with pressed_by("operator@example.com"):
        got = explain.explain(world.pack["id"], actor="operator@example.com",
                              trigger=triggers.person("operator@example.com"),
                              send=_cut(world, json.dumps(_answer(world.pack))), today="2026-10-25")
    bound = profiles.TASKS["explain"]["max_tokens"]
    assert got["ok"] is False and "answer" not in got
    assert got["error"] == "max_tokens"
    assert got["detail"] == f"the answer ran past max_tokens ({bound})"
    (row,) = calls.read()["rows"]
    assert row["verdict"] == "max_tokens" and "output" not in row
    from flask import render_template
    from modules import csp
    from app import app
    with app.test_request_context():
        html = render_template("v2/_explain.html", x=got, csp=csp)
    assert f"Not explained: the answer ran past max_tokens ({bound})." in html
    assert "hypothes" not in html.lower(), "a cut explanation was drawn"
