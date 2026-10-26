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
    ("shut Gi0/1 on s1 and r2", ["s1"], "other_device",
     "the sentence names r2 too; a change in words on s1's Intent tab changes s1 only"),
    ("", None, "empty", "type the change first"),
], ids=["no-device", "nothing-named", "other-device-on-a-tab", "empty"])
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
