"""Feature 7's call (PHASE8_PLAN 15.16): a sentence becomes a patch per device, previewed by the
intent editor, on the host's REAL committed lab (tests/test_committed_before_p1's `host`: r2
and s1 committed as the host holds them), the gateway allowed with a fake `send`.

- The request: the prompt, the operations as the cached prefix, and three data blocks, the
  devices' slices among them; nothing else of the intent is in the bytes sent (s1's real
  descriptions, its users, SNMP, and a planted secret reference).
- An answer is previewed by the intent editor and writes nothing; a question back, a refusal,
  an answer changing a device the sentence did not name, and one naming an interface the
  device lacks are each said, with nothing previewed, and recorded as what became of it.
- A sentence naming no device, or a device with no committed intent, is Mercury's own answer:
  no call.
- History: the call reads "AI call, intent_patch on an intent change on s1: ...".
"""
import json

import pytest
import yaml

from modules.ai import anthropic_adapter as A
from modules.ai import calls, gateway, intent_words, nl_query
from tests.test_committed_before_p1 import host  # noqa: F401 (the fixture)

KEY = "sk-planted-test-key-0123456789"


@pytest.fixture
def world(host, monkeypatch, tmp_path):  # noqa: F811
    from modules import settings_schema
    hosts = settings_schema.get_setting
    extra = {"ai_hosted": {"by": "operator@example.com", "at": "2026-10-25T05:00:00Z",
                           "reason": "the lab's proof of concept"},
             "ai_cap_usd_per_day": 1.50}
    monkeypatch.setattr(settings_schema, "get_setting",
                        lambda k, d=None: extra[k] if k in extra else hosts(k, d))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    monkeypatch.setattr(nl_query, "_inventory", lambda name: [
        {"hostname": "r2", "role": "router", "platform": "cisco_iosxe"},
        {"hostname": "s1", "role": "switch", "platform": "cisco_ios"}])

    class W:
        pass
    w = W()
    w.sent, w.answer = [], None

    def send(body, key):
        w.sent.append({"bytes": json.dumps(body), "body": body})
        return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(
            w.answer)}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 1500, "output_tokens": 120}}, attempts=1, latency_s=0.4)
    w.send = send
    monkeypatch.setattr(A, "send", send)
    return w


def _op(op, **fields):
    base = {"op": op, "interface": "", "description": "", "vlan": 0, "vlan_name": "",
            "process": 0, "prefix": "", "area": ""}
    base.update(fields)
    return base


def _answer(*patches, outcome="answer", question="", why_not=""):
    return {"outcome": outcome, "question": question, "why_not": why_not,
            "patches": [{"hostname": h, "operations": list(ops)} for h, ops in patches]}


DESCRIBE = _answer(("s1", [_op("set_description", interface="GigabitEthernet0/1",
                               description="uplink to edge1")]))


def _change(world, sentence="describe s1's GigabitEthernet0/1 as uplink to edge1"):
    return intent_words.change("Lab", sentence, actor="operator@example.com",
                               send=world.send, today="2026-10-26")


def _committed(name):
    from modules.nsot import intent_edit
    return intent_edit.open_doc("Lab", name)["base"]


def test_the_request_holds_the_prompt_the_operations_and_the_slice_only(world):
    from modules.ai import prompts
    from modules.nsot import intent_edit
    world.answer = DESCRIBE
    _change(world)
    body = world.sent[-1]["body"]
    assert body["system"][0]["text"] == prompts.load(*intent_words.PROMPT)["text"]
    assert "set_description: interface, description" in body["system"][1]["text"]
    user = body["messages"][0]["content"]
    import re
    data = re.findall(r'<data name="([^"]+)">', user)      # in the gateway's own order
    assert sorted(data) == ["devices", "devices_named", "sentence"]
    sent = world.sent[-1]["bytes"]
    doc = yaml.safe_load(intent_edit.open_doc("Lab", "s1")["yaml"])
    # The sentence touches GigabitEthernet0/1 alone: every other interface's description stays.
    described = [i["description"] for i in doc["interfaces"]
                 if i.get("description") and i["name"] != "GigabitEthernet0/1"]
    assert len(described) >= 5, "the floor: s1's real descriptions"
    for text in described:
        assert text not in sent, text
    assert "GigabitEthernet0/2" not in user, "an interface the sentence did not name"
    for section in ("users", "snmp", "ntp_servers", "logging"):
        assert section not in sent, section
    assert '"r2' not in user and "r2:" not in user, "a device the sentence did not name"


def test_an_answer_is_previewed_by_the_intent_editor_and_writes_nothing(world):
    world.answer = DESCRIBE
    before = _committed("s1")
    got = _change(world)
    assert got["ok"] is True, got
    (p,) = got["previews"]
    assert p["hostname"] == "s1" and p["changed"] is True
    added = [l[1:].strip() for l in p["vs_intent"].splitlines()
             if l.startswith("+") and not l.startswith("+++")]
    assert added == ["description uplink to edge1"]
    assert _committed("s1") == before, "a preview writes nothing"
    (use,) = calls.uses()[got["call_id"]]
    assert use["use"] == "previewed in the intent editor"


@pytest.mark.parametrize("sentence,answer,error,said,use", [
    ("shut s1's Gi0/1 or Gi0/2", _answer(outcome="ask", question="Which interface on s1?"),
     "ask", "one question first: Which interface on s1?", "asked a question back"),
    ("give s1's Gi0/1 the address 192.0.2.9/24",
     _answer(outcome="refuse", why_not="no operation sets an address"), "unanswerable",
     "this change cannot be drafted in words: no operation sets an address",
     "shown: the operations cannot make it"),
    ("shut s1's Gi0/1", _answer(("r2", [_op("shutdown", interface="GigabitEthernet3")])),
     "couldnt_change", "the answer changes 'r2', a device outside the request (it names s1); "
     "nothing is previewed", "refused by validation"),
    ("shut s1's Gi0/1", _answer(("s1", [_op("shutdown", interface="GigabitEthernet0/2")])),
     "couldnt_change", "s1's operation 0 (shutdown) changes the interface 'GigabitEthernet0/2', "
     "which the request does not name; nothing is previewed", "refused by validation"),
    ("shut GigabitEthernet9/9 on s1",
     _answer(("s1", [_op("shutdown", interface="GigabitEthernet9/9")])), "intent",
     "s1: operations[0] names the interface 'GigabitEthernet9/9', and s1's intent holds no "
     "such interface", "refused by the intent"),
], ids=["ask", "refuse", "other-device", "other-interface", "no-such-interface"])
def test_what_is_not_an_answer_previews_nothing_and_says_why(world, sentence, answer, error,
                                                             said, use):
    world.answer = answer
    before = _committed("s1")
    got = _change(world, sentence)
    assert got["ok"] is False and got["error"] == error, got
    assert said in got["detail"], got["detail"]
    assert not any(p.get("ok") for p in got.get("previews") or [])
    assert _committed("s1") == before
    assert calls.uses()[got["call_id"]][-1]["use"] == use


@pytest.mark.parametrize("sentence,devices,error,said", [
    ("shut Gi2 on the core switch", None, "no_device", "the sentence names no device of Lab"),
    ("shut the uplink on s1", None, "nothing_named",
     "the sentence names no interface, VLAN or OSPF network to change"),
    ("", None, "empty", "type the change first"),
], ids=["no-device", "nothing-named", "empty"])
def test_mercury_answers_what_needs_no_model(world, sentence, devices, error, said):
    got = intent_words.change("Lab", sentence, actor="operator@example.com", send=world.send,
                              today="2026-10-26", devices=devices)
    assert got["ok"] is False and got["error"] == error and said in got["detail"], got
    assert world.sent == [] and calls.read()["rows"] == [], "no call, nothing spent"


def test_on_a_device_s_tab_the_device_needs_no_naming(world):
    world.answer = DESCRIBE
    got = intent_words.change("Lab", "describe GigabitEthernet0/1 as uplink to edge1",
                              actor="operator@example.com", send=world.send,
                              today="2026-10-26", devices=["s1"])
    assert got["ok"] is True, got


def test_on_a_tab_a_description_naming_another_device_is_drafted(world):
    """C1770: the first measurement's cases 11 and 12 ("uplink to r1") were refused before any
    call, every run, because the sentence named a device of the network. On a device's tab
    another device's name is only words: the call is made and the draft previewed."""
    world.answer = _answer(("s1", [_op("set_description", interface="GigabitEthernet0/1",
                                       description="uplink to r2")]))
    got = intent_words.change("Lab", "describe GigabitEthernet0/1 as uplink to r2",
                              actor="operator@example.com", send=world.send,
                              today="2026-10-26", devices=["s1"])
    assert got["ok"] is True, got
    assert len(world.sent) == 1
    (p,) = got["previews"]
    assert p["hostname"] == "s1" and "description uplink to r2" in p["vs_intent"]


def test_on_a_tab_an_answer_changing_the_device_named_in_words_is_refused(world):
    """The control beside it: on s1's tab, a sentence naming r2 and an answer changing r2 is
    refused by the scope check before any preview, naming r2, and nothing is previewed."""
    world.answer = _answer(("r2", [_op("shutdown", interface="GigabitEthernet3")]))
    before = _committed("s1")
    got = intent_words.change("Lab", "shut Gi0/1 on s1 and r2", actor="operator@example.com",
                              send=world.send, today="2026-10-26", devices=["s1"])
    assert got["ok"] is False and got["error"] == "couldnt_change", got
    assert "the answer changes 'r2', a device outside the request" in got["detail"], got
    assert not got.get("previews") and _committed("s1") == before


# ── part 1 on the tab: names resolved before any call ───────────────────────────────────

WALK = "Set the description on the host port to 'walk F7 test'"


def _post(host, data):  # noqa: F811
    from html import unescape
    r = host["client"].post("/v2/device/s1/intent/words?list=Lab", data=data,
                            headers={"HX-Request": "true"})
    return r, unescape(r.get_data(as_text=True))


def test_the_walk_s_sentence_asks_which_host_port_before_any_call(world, host):  # noqa: F811
    r, html = _post(host, {"words": WALK})
    assert r.status_code == 200
    assert "s1 has 2 host ports (an access port, enabled, with no managed neighbour); which one?" \
        in html
    for label in ("GigabitEthernet1/0 (h1 - VLAN 10)", "GigabitEthernet1/1 (h2 - VLAN 20)",
                  "Both"):
        assert f'<span class="op-idle">{label}</span>' in html, label
    assert 'name="phrase" value="the host port"' in html and f'value="{WALK}"' in html
    assert world.sent == [] and calls.read()["rows"] == [], "no call, nothing spent"


def test_the_choice_continues_the_draft_and_the_model_gets_resolved_names_only(world, host):  # noqa: F811
    world.answer = _answer(("s1", [_op("set_description", interface="GigabitEthernet1/0",
                                       description="walk F7 test")]))
    r, html = _post(host, {"words": WALK, "phrase": "the host port",
                           "pick": "GigabitEthernet1/0"})
    assert "Drafted from your words" in html, html[:800]
    assert "How your words were read" in html
    assert ('<q>the host port</q> → <span class="mono">GigabitEthernet1/0</span> '
            '<span class="muted">(by role)</span>') in html
    sent = world.sent[-1]["bytes"]
    assert "GigabitEthernet1/0" in sent and "host port" not in sent, "resolved names only"
    assert "description walk F7 test" in html, "the editor's preview of the change"


def test_a_name_the_device_lacks_lists_its_interfaces_and_links_neighbours(world, host):  # noqa: F811
    r, html = _post(host, {"words": "shut Gi9/9"})
    assert "Not found:</strong> s1 has no interface Gi9/9" in html
    assert '<span class="op-idle">GigabitEthernet1/0 (h1 - VLAN 10)</span>' in html
    assert "/v2/device/s1?tab=neighbours" in html
    assert world.sent == []


def test_a_draft_that_changes_no_configuration_line_says_already_so(world, host):  # noqa: F811
    """C1771: "bring Gi0/1 up" on an interface already up drafts an explicit `no shutdown`,
    which no configuration line shows: already so, and no check offered."""
    world.answer = _answer(("s1", [_op("no_shutdown", interface="GigabitEthernet0/1")]))
    r, html = _post(host, {"words": "bring Gi0/1 up"})
    assert "Already so:" in html and "nothing to commit" in html, html[:800]
    assert 'class="ie-col"' not in html, "the editor's check is not offered"


# ── part 2: commit a drafted change ──────────────────────────────────────────────────────

def _drafted(world, host):  # noqa: F811
    """The walk's draft through the tab's own routes (Gi1/0 chosen): the commit form's hidden
    fields, read from the raw page and unescaped."""
    import html as H
    import re
    world.answer = _answer(("s1", [_op("set_description", interface="GigabitEthernet1/0",
                                       description="walk F7 test")]))
    r = host["client"].post("/v2/device/s1/intent/words?list=Lab", data={
        "words": WALK, "phrase": "the host port", "pick": "GigabitEthernet1/0"},
        headers={"HX-Request": "true"})
    raw = r.get_data(as_text=True)
    form = raw.split('class="iw-commit"', 1)[1].split("</form>", 1)[0]
    fields = {m.group(1): H.unescape(m.group(2))
              for m in re.finditer(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"', form)}
    assert set(fields) == {"call_id", "base", "patch", "words"}, fields
    return dict(fields, summary="walk F7 test on the host port")


def _commit(host, fields, **headers):  # noqa: F811
    from html import unescape
    r = host["client"].post("/v2/device/s1/intent/words/commit?list=Lab", data=fields,
                            headers=dict({"HX-Request": "true"}, **headers))
    return r, unescape(r.get_data(as_text=True))


def _git(host, *args):  # noqa: F811
    import subprocess
    return subprocess.run(["git", "-C", host["repo"], *args], capture_output=True, text=True,
                          check=True).stdout


def test_a_draft_commits_with_its_trailers_and_the_links_both_ways(world, host):  # noqa: F811
    fields = _drafted(world, host)
    before = _committed("s1")
    r, html = _commit(host, fields)
    assert r.status_code == 200 and "Committed to s1's intent:" in html, html[:800]
    assert _committed("s1") != before
    assert "description: walk F7 test" in intent_words_doc("s1")
    message = _git(host, "log", "-1", "--format=%B")
    for trailer in ("Source: ai-draft", f"AI-Call: {fields['call_id']}", "Actor: "):
        assert trailer in message, (trailer, message)
    assert message.startswith("host_vars: s1 walk F7 test on the host port")
    sha = _git(host, "rev-parse", "HEAD").strip()
    (use,) = [u for u in calls.uses()[fields["call_id"]] if u["use"] == "committed to intent"]
    assert use["detail"] == f"commit {sha[:12]} to s1's intent", use
    assert f"/v2/history?call={fields['call_id']}" in html, "the result links its call"
    page = host["client"].get("/v2/device/s1?tab=history&list=Lab").get_data(as_text=True)
    assert "Open the AI call that drafted it" in page, "the commit's row links back"
    assert f"call={fields['call_id']}" in page


def test_commit_and_plan_deploy_opens_the_deploy_preview_and_confirms_nothing(world, host):  # noqa: F811
    fields = dict(_drafted(world, host), plan="1")
    r, _html = _commit(host, fields)
    assert r.status_code == 204
    assert r.headers["HX-Redirect"] == "/v2/device/s1?tab=intent&op=deploy&list=Lab"


def test_a_patch_other_than_the_drafted_one_is_refused_writing_nothing(world, host):  # noqa: F811
    fields = _drafted(world, host)
    before = _committed("s1")
    fields["patch"] = fields["patch"].replace("walk F7 test", "something else")
    r, html = _commit(host, fields)
    assert r.status_code == 409 and "this is not the drafted change" in html, html[:800]
    assert _committed("s1") == before


def test_intent_moved_since_the_draft_is_refused_naming_it(world, host):  # noqa: F811
    from modules.nsot import intent_patch
    fields = _drafted(world, host)
    moved = intent_patch.commit("Lab", "s1", {"hostname": "s1", "operations": [
        {"op": "set_description", "interface": "GigabitEthernet0/1",
         "description": "moved meanwhile"}]}, "a change made meanwhile",
        _committed("s1"), "someone@example.com")
    assert moved["ok"] and moved["commit"]
    after = _committed("s1")
    r, html = _commit(host, fields)
    assert r.status_code == 409 and "Not committed:" in html, html[:800]
    assert _committed("s1") == after, "nothing written over the change made meanwhile"


def test_a_service_cannot_commit_a_draft(world, host, monkeypatch):  # noqa: F811
    from modules import identity
    fields = _drafted(world, host)
    svc = identity.Identity(actor="service:abc.access", kind="service", service_id="abc.access",
                            verified=True, outcome="ok", peer="198.51.100.7", peer_trusted=True,
                            header_present=True)
    before = _committed("s1")
    monkeypatch.setattr(identity, "identify", lambda _r: svc)
    r = host["client"].post("/v2/device/s1/intent/words/commit?list=Lab", json={})
    assert r.status_code == 403 and (r.get_json(silent=True) or {}).get("requires_person")
    assert _committed("s1") == before


def test_a_deploy_receipt_records_its_intent_commit_and_history_links_both_ways(world, host):  # noqa: F811
    """C1775: AI call ↔ intent commit ↔ deploy receipt. A deploy's receipt records the intent
    commit it rendered; History's receipt row opens it, the commit's row opens its deploys
    (`?commit=`, both rows); a receipt from before C1775 says "not recorded", never a blank;
    a restore's says it sent a golden."""
    from html import unescape
    from modules.nsot import receipts
    fields = _drafted(world, host)
    r, _html = _commit(host, fields)
    assert r.status_code == 200
    sha = _git(host, "rev-parse", "HEAD").strip()
    result = {"device": "s1", "outcome": "sent", "commands": [
        "interface GigabitEthernet1/0", "description walk F7 test"], "program_hash": "f" * 64}
    (row,) = receipts.rows_for({"results": [result], "golden": {}}, list_name="Lab",
                               action="deploy", actor="operator@example.com",
                               actor_kind="person")
    assert row["intent_commit"] == sha
    (restore,) = receipts.rows_for({"results": [result], "golden": {}}, list_name="Lab",
                                   action="restore", actor="operator@example.com",
                                   actor_kind="person")
    assert restore["intent_commit"] is None
    before = {k: v for k, v in row.items() if k != "intent_commit"}
    before.update(id="c1775-before", at="2026-10-20T10:00:00Z")
    restore.update(at="2026-10-21T10:00:00Z")
    assert receipts.write("Lab", [row, before, restore]).get("ok", True) is not False
    c = host["client"]
    both = unescape(c.get(f"/v2/history?commit={sha}&since=&list=Lab").get_data(as_text=True))
    import re
    words = " ".join(re.sub(r"<[^>]+>", " ", both).split())
    assert f"Commit {sha[:12]} and the deploys that sent it: 2 rows" in words, \
        both[both.find("hist-count"):][:400]
    assert both.count("Open the intent change it deployed") == 1
    assert "Open its deploys" in both and f"commit={sha}" in both
    page = unescape(c.get("/v2/history?since=&list=Lab&kind=receipts").get_data(as_text=True))
    assert "not recorded (this receipt is from before the intent commit was recorded)" in page
    assert "none: a restore or re-apply sends a golden, not intent" in page
    assert f"<dd>{sha[:12]}</dd>" in page


def intent_words_doc(name):
    from modules.nsot import intent_edit
    return intent_edit.open_doc("Lab", name)["yaml"]


# ── the stale-expectation check (the operator, 2026-10-26; C1770's premises) ─────────────

def _case(sentence, outcome, ops, said=None, device="s1"):
    expect = {"outcome": outcome, "ops": ops}
    if said:
        expect["said"] = said
    return {"n": 1, "device": device, "sentence": sentence, "expect": expect}


@pytest.mark.parametrize("case,words", [
    (_case("bring GigabitEthernet1/0 up", ["answer"],
           [{"op": "no_shutdown", "interface": "GigabitEthernet1/0"}]),
     "the expected change is already in the committed intent"),
    (_case("remove vlan 30", ["answer"], [{"op": "remove_vlan", "vlan": 30}]),
     "the intent editor refuses the expected change: operations[0] removes VLAN 30"),
    (_case("add vlan 40 named LAB", ["refused_after"],
           [{"op": "add_vlan", "vlan": 40, "name": "LAB"}],
           {"refused_after": "still uses it"}),
     "the case expects the editor's refusal, and the committed intent now takes the change"),
    (_case("shut GigabitEthernet0/1", ["answer"],
           [{"op": "shutdown", "interface": "GigabitEthernet0/2"}]),
     "the expected operations are outside what the sentence names"),
    (_case("shut GigabitEthernet0/1", ["answer"],
           [{"op": "shutdown", "interface": "GigabitEthernet0/1"}], device="r9"),
     "no committed intent to judge it against"),
], ids=["already-up", "vlan-in-use", "now-taken", "outside-the-sentence", "no-intent"])
def test_a_stale_expectation_is_found_by_the_real_path_with_no_call(world, case, words):
    got = intent_words.stale("Lab", case)
    assert len(got) == 1 and words in got[0], got
    assert world.sent == [] and calls.read()["rows"] == [], "no call, nothing spent"


def test_part_1_s_cases_hold_on_the_real_s1_with_its_measured_neighbours(world, monkeypatch):
    """Every case of names.json is fresh against s1 as committed, its neighbours as the host's
    Topology read measured them (tests/test_ai_intent_names.py's NEIGHBOURS): the cases agree
    with the resolver before any call is spent. Control: a case expecting the wrong port."""
    import os
    from modules.ai import cases, intent_names
    from tests.test_ai_intent_names import NEIGHBOURS
    monkeypatch.setattr(intent_names, "neighbours_of", lambda network, device: NEIGHBOURS)
    monkeypatch.setattr(intent_names, "_devices", lambda network: {
        "r1": "router", "s1": "switch", "s2": "switch"})
    data = cases.load(os.path.join(os.path.dirname(__file__), "fixtures", "ai_cases",
                                   "intent_patch", "names.json"))
    assert [p for c in data["cases"] for p in intent_words.stale("Lab", c)] == []
    wrong = dict(data["cases"][5], resolves={"the uplink": ["GigabitEthernet0/3"]})
    (problem,) = intent_words.stale("Lab", wrong)
    assert "expects 'the uplink' to resolve to ['GigabitEthernet0/3']" in problem
    asks = dict(data["cases"][9], expect={"outcome": ["choose"],
                                          "candidates": ["GigabitEthernet1/0"]})
    assert "the case expects Mercury to ask which of" in intent_words.stale("Lab", asks)[0]
    assert world.sent == []


@pytest.mark.parametrize("case", [
    _case("bring GigabitEthernet1/0 up", ["answer", "refuse", "refused_after"],
          [{"op": "no_shutdown", "interface": "GigabitEthernet1/0"}],
          {"refused_after": "the answer changes no device"}),
    _case("remove vlan 30", ["refused_after"], [{"op": "remove_vlan", "vlan": 30}],
          {"refused_after": "removes VLAN 30, and s1's intent still uses it"}),
    _case("shut GigabitEthernet0/1", ["answer"],
          [{"op": "shutdown", "interface": "GigabitEthernet0/1"}]),
    _case("which interface?", ["ask"], []),
], ids=["no-op-allowed", "refusal-expected", "a-change", "ask"])
def test_an_expectation_that_holds_is_not_stale(world, case):
    assert intent_words.stale("Lab", case) == []


def test_the_intent_tab_draws_the_row_and_its_draft_in_the_editor_s_preview(world, host):  # noqa: F811
    """The route on s1's Intent tab: the row with its AI mark; drafted, the changes in words
    and the editor's own preview (what the change does in s1's configuration); the state
    written nowhere."""
    from html import unescape
    c = host["client"]
    page = unescape(c.get("/v2/device/s1?tab=intent&list=Lab").get_data(as_text=True))
    assert 'id="intent-words"' in page and 'data-ai-control="intent_in_words"' in page
    world.answer = DESCRIBE
    before = _committed("s1")
    r = c.post("/v2/device/s1/intent/words?list=Lab",
               data={"words": "describe GigabitEthernet0/1 as uplink to edge1"},
               headers={"HX-Request": "true"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and "Drafted from your words" in html, html[:600]
    assert "GigabitEthernet0/1: description" in html
    assert "description uplink to edge1" in html, "the editor's preview of the change"
    assert _committed("s1") == before


def test_the_row_is_an_ai_control_and_the_intent_stays_shown(world, host, monkeypatch):  # noqa: F811
    """15.13 on the Intent tab: ready, the row's box and button live; not ready (each kind),
    disabled with the reason, and the committed intent beside it drawn as ever (Edit, for a
    viewer who may commit, is the intent card's own and outside the row)."""
    from tests import ai_controls_check as AIC

    def get():
        return host["client"].get("/v2/device/s1?tab=intent&list=Lab").get_data(as_text=True)

    def parity(html):
        assert '<pre class="apply-program intent-doc">' in html, "the committed intent drawn"
    AIC.check_screen(monkeypatch, get, "intent_in_words", parity)


def test_history_names_the_change_and_its_devices(world):
    from modules import history_sources as HS
    world.answer = DESCRIBE
    _change(world)
    (e,) = HS.ai_calls({"device": "s1", "limit": 50})["events"]
    assert e["what"].startswith("AI call, intent_patch on an intent change on s1: "
                                "previewed in the intent editor (claude-sonnet-5-5, $")
    assert HS.ai_calls({"device": "r2", "limit": 50})["events"] == []
