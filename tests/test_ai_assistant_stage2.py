"""The toolbar assistant's stage 2 (docs/design/assistant.md as amended 2026-11-23; the week plan's
Stage 4; modules/ai/assistant.py, modules/ai/assistant_context.py, modules/ai/assistant_threads.py,
routes/assistant_v2.py). The gateway is real (its trigger, caps, mask and record), the provider
a fake answering each pass in turn; the reads engine a fake recording what it was asked; no
provider, device or network is reached.

- **What it is looking at:** the page's path resolved by the server's own URL map into the
  screen, the network, the device and the incident, and said in the panel's head; a path that
  is not one of Mercury's pages, or not on this host, names nothing.
- **The reads:** on a device's page, with the device state class on, the answer's reads go
  through the read loop's check and the reads engine (kind ``ai_analysis``, as the assistant
  asked by the person), are logged in the send log, and are answered on in one more call; a
  read of another device is refused by name and never run; with the class off, or no device in
  view, the one pass is the plain one and nothing is read.
- **Every answer shows** its sources with Open (a passage its section, a read its device tab
  and its record on History › Reads), the model, the cost and each call's History link.
- **A change is handed off,** never applied: Change it in words… opens the device's Intent tab
  with its box filled and nothing drafted; on an incident, Open AI troubleshooting; a hand-off
  with nothing in view to hand to is dropped and said.
- **The thread** is kept per person, owner-only, named by a digest, the newest 20, the question
  masked; the panel draws it again with no call.
- **The button** is always drawn: disabled while the Assistant is off (its title saying where
  it is turned on), greyed while hosted AI is off, and plain when it can answer.
"""
import json
import os
import re
import stat
from html import unescape

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import assistant, assistant_threads, calls, triggers
from modules.ai import router_reads as RR
from tests.ai_person import PERSON, pressed_by
from tests.test_ai_assistant import world  # noqa: F401 (the fixture)
from tests.test_committed_before_p1 import host  # noqa: F401 (the fixture)

DEVICE_PATH = "/v2/device/r2?tab=overview&list=Lab"
INCIDENT = "hi-0123abcd"


@pytest.fixture(autouse=True)
def as_person():
    with pressed_by(PERSON):
        yield


@pytest.fixture
def lab(world, monkeypatch, tmp_path):
    """The stage 1 world, the provider answering each pass from a queue (then the world's own
    answer), the thread's folder the test's own, and the reads engine a fake."""
    queue, ran = [], []

    def send(body, key, **_kw):
        world["sent"].append({"bytes": json.dumps(body), "body": body})
        answer = queue.pop(0) if queue else world["state"]["answer"]
        return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(
            answer)}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 3000, "output_tokens": 200}}, attempts=1, latency_s=0.2)
    monkeypatch.setattr(A, "send", send)
    monkeypatch.setattr(assistant_threads, "_dir", lambda: str(tmp_path / "assistant_threads"))
    # The capture lab's list 'Lab' is the current one but in no registry (tests/test_capture.py):
    # here it is a network, as a person's own is, so its pages and its id answer.
    from modules.nsot import listref
    real_exists, real_id = listref.exists, listref.network_id
    monkeypatch.setattr(listref, "exists", lambda n: str(n).lower() == "lab" or real_exists(n))
    monkeypatch.setattr(listref, "network_id", lambda n: "lab" if str(
        getattr(n, "name", n)).lower() == "lab" else real_id(n))
    from modules.nsot import reads
    run_id = reads.new_id()

    def fake_run(list_name, hosts, commands, actor, *, by="person", purpose="", **kw):
        ran.append({"list": list_name, "hosts": list(hosts), "commands": list(commands),
                    "actor": actor, "by": by})
        return {"id": run_id, "results": {hosts[0]: {
            "answers": [{"state": "answered", "command": c,
                         "answer": "Cisco IOS XE Software, Version 17.09.01a"} for c in commands],
            "signed_in_as": {"username": "mercury-ro", "source": "the read-only account"}}}}
    monkeypatch.setattr(reads, "run", fake_run)
    world.update(queue=queue, ran=ran, run_id=run_id, tmp=tmp_path)
    return world


def reads_on(monkeypatch):
    """The device state class on for the network, and r2's scope as `router_reads.scope_for`
    builds it (a read-only account, IOS-XE), so the check reaches each read's comparisons."""
    from modules.ai import egress_classes
    monkeypatch.setattr(egress_classes, "device_state_allowed",
                        lambda network: {"allowed": True, "why": ""})
    monkeypatch.setattr(egress_classes, "classification_marking", lambda network: "")
    asked = []

    def scope_for(network, hosts, **kw):
        asked.append((network, list(hosts)))
        return {"network": network, "addresses": [], "prefixes": [], "reads_as": "mercury",
                "ping_traceroute": False, "actor": "the AI analysis",
                "devices": {h: {"interfaces": ["GigabitEthernet1"], "peers": [],
                                "dialect": "cisco_iosxe", "subscriptions": [],
                                "vlan_database": False, "vlan_database_words": "",
                                "read_account": True, "read_account_why": ""} for h in hosts}}
    monkeypatch.setattr(RR, "scope_for", scope_for)
    return asked


def words(answer="Open the device page, then Actions › Reload…", cites=(), covered=True,
          screens=(), reads=(), handoff=None, plan=None):
    return {"answer": answer, "cites": list(cites), "covered": covered,
            "screens": list(screens), "plan": plan, "handoff": handoff, "reads": list(reads)}


def show(device="r2", what="version"):
    return {"op": "show", "args": {"device": device, "words": what}, "why": "its software",
            "hypothesis": "it runs 17.9"}


def place(path=DEVICE_PATH, network="Lab"):
    import app as APP
    from modules.ai import assistant_context
    with APP.app.test_request_context("/"):
        return assistant_context.resolve(path, network=network)


def ask(lab, question="What version is r2 running?", where=DEVICE_PATH):
    return assistant.answer(question, screen="", place=place(where), actor=PERSON,
                            trigger=triggers.person(PERSON))


def post(lab, question, path=DEVICE_PATH):
    r = lab["client"].post("/v2/assistant/ask?list=Lab",
                           data={"question": question, "screen": "", "path": path})
    return r, unescape(r.get_data(as_text=True))


def kept_text(lab) -> str:
    """Every thread the presses kept, as the files hold them (the route keeps each under the
    verified person who pressed)."""
    folder = lab["tmp"] / "assistant_threads"
    names = sorted(n for n in os.listdir(folder) if n.endswith(".jsonl"))
    assert names, "the press kept its exchange"
    return "".join((folder / n).read_text() for n in names)


def _uses() -> list:
    """What became of every call's answer, as recorded (`calls.record_use`)."""
    return [u["use"] for us in calls.uses().values() for u in us]


def panel(lab, path=DEVICE_PATH, nav=""):
    r = lab["client"].get("/v2/assistant/panel", query_string={"path": path, "nav": nav,
                                                               "list": "Lab"})
    return r, unescape(r.get_data(as_text=True))


# ── what it is looking at ─────────────────────────────────────────────────────────────────────

class TestWhatItIsLookingAt:
    @pytest.mark.parametrize("path,want", [
        (DEVICE_PATH, {"device": "r2", "incident": "", "screen": "Devices", "tab": "overview",
                       "label": "r2 (device) · Lab"}),
        ("/v2/device/r2/intent/edit", {"device": "r2", "screen": "Devices"}),
        (f"/v2/incident/{INCIDENT}?list=Lab", {"device": "", "incident": INCIDENT,
                                               "screen": "Incidents",
                                               "label": f"incident {INCIDENT} · Lab"}),
        ("/v2/devices", {"device": "", "incident": "", "endpoint": "v2.devices"}),
        ("/v2/nowhere/at/all", {"device": "", "incident": "", "endpoint": ""}),
        ("https://example.com/v2/device/r2", {"device": "", "endpoint": ""}),
        ("//example.com/v2/device/r2", {"device": "", "endpoint": ""}),
        ("/v2/incident/not-an-incident", {"incident": "", "endpoint": "incident_v2.incident"}),
    ], ids=["device", "device-subpage", "incident", "a-screen", "not-a-page", "another-host",
            "scheme-relative", "not-an-incident-id"])
    def test_the_path_is_resolved_by_the_url_map(self, lab, path, want):
        got = place(path)
        assert {k: got[k] for k in want} == want, got
        assert got["network"] == "Lab"

    def test_opening_the_panel_says_what_it_looks_at_and_makes_no_call(self, lab):
        """Its head, from the path the server resolved, and its Ask carrying that path back;
        opening it asks the model nothing and records no call."""
        r, html = panel(lab)
        assert r.status_code == 200
        head = re.search(r'<p class="small asst-place"[^>]*>(.*?)</p>', html, re.S).group(1)
        assert "Looking at: <strong>r2 (device) · Lab</strong>" in head, head
        assert 'name="path" value="/v2/device/r2?tab=overview&list=Lab"' in html
        _r, html = panel(lab, "/v2/devices", nav="devices")
        assert "Looking at: <strong>Devices · Lab</strong>" in html
        assert 'name="screen" value="Devices"' in html
        assert lab["sent"] == [] and calls.read()["rows"] == []


# ── the reads ─────────────────────────────────────────────────────────────────────────────────

class TestTheReads:
    def test_a_device_read_runs_through_mercury_s_tools_and_is_answered_on(self, lab,
                                                                         monkeypatch):
        asked = reads_on(monkeypatch)
        lab["queue"].extend([
            words("Reading r2's software version first.", covered=False, reads=[show()]),
            words("r2 runs IOS XE 17.09.01a.", cites=["read:1"])])
        got = ask(lab)
        assert (got["ok"], got["state"]) == (True, "answered"), got
        assert asked == [("Lab", ["r2"])], "the scope is the page's device alone"
        (run,) = lab["ran"]
        assert run["commands"] == ["show version"] and run["hosts"] == ["r2"]
        assert run["by"] == "ai_analysis", "the reads engine's AI kind, its read-only account"
        assert run["actor"] == f"the toolbar assistant, asked by {PERSON}"
        first, second = lab["sent"]
        assert "first pass" in first["bytes"] and "the last pass" in second["bytes"]
        assert "17.09.01a" in second["bytes"] and "17.09.01a" not in first["bytes"]
        assert got["calls"] == [c for c in got["calls"] if c] and len(got["calls"]) == 2
        assert len(got["sources"]) == 1, got["sources"]
        source = got["sources"][0]
        assert (source["kind"], source["id"], source["device"], source["tab"], source["run"]) \
            == ("read", "read:1", "r2", "ask", lab["run_id"])
        from modules.ai import read_log
        (loop,) = read_log.loops()["loops"]
        assert loop["task"] == "assistant" and loop["to_send"] == ["read:1"]
        assert [(e["device"], e["verdict"], e["run"]) for e in loop["reads"]] == [
            ("r2", "run", lab["run_id"])]

    def test_a_read_of_another_device_is_refused_by_name_and_never_run(self, lab, monkeypatch):
        reads_on(monkeypatch)
        lab["queue"].append(words("Reading r6 first.", covered=False, reads=[show("r6")]))
        got = ask(lab)
        assert lab["ran"] == [], "nothing reached the reads engine"
        assert len(lab["sent"]) == 1, "no read ran: no second call"
        (r,) = got["reads"]
        assert r["verdict"] == "refused" and "r6 is not a device" in r["reason"], r

    def test_with_the_class_off_the_one_pass_is_plain_and_nothing_is_read(self, lab,
                                                                         monkeypatch):
        asked = []
        monkeypatch.setattr(RR, "scope_for", lambda *a, **k: asked.append(a) or {})
        lab["queue"].append(words("r2's version is on its Overview.", covered=False,
                                  reads=[show()]))
        got = ask(lab)
        assert asked == [] and lab["ran"] == [], "no scope built, no read run"
        (only,) = lab["sent"]
        assert "the only pass: reads are off for this network" in only["bytes"]
        assert got["reads"] == []

    def test_with_no_device_in_view_nothing_is_read(self, lab, monkeypatch):
        reads_on(monkeypatch)
        lab["queue"].append(words(cites=[], covered=False, reads=[show()]))
        ask(lab, "How do I reload a device safely?", where="/v2/devices")
        (only,) = lab["sent"]
        assert "the only pass" in only["bytes"] and lab["ran"] == []
        sent = only["body"]["messages"][0]["content"]
        assert '"device": ""' in sent or "'device': ''" in sent, "looking_at names no device"


# ── what every answer shows ───────────────────────────────────────────────────────────────────

class TestEveryAnswerShows:
    def test_sources_model_cost_and_the_calls_in_history(self, lab, monkeypatch):
        reads_on(monkeypatch)
        from modules.ai import manual_index
        chosen = manual_index.select("What version is r2 running? reload", screen="Devices")
        assert chosen, "the premise: a passage is chosen"
        lab["queue"].extend([
            words("Reading r2's version first.", covered=False, reads=[show()]),
            words("r2 runs 17.09.01a; reload it from Actions.",
                  cites=[chosen[0]["link"], "read:1"])])
        r, html = post(lab, "What version is r2 running? reload")
        assert r.status_code == 200, html[:400]
        sources = html[html.index("Sources:"):html.index("</ul>", html.index("Sources:"))]
        assert f'<a href="{chosen[0]["link"]}">Open</a>' in sources
        assert 'href="/v2/device/r2?tab=ask&list=Lab">Open Ask the device</a>' in sources
        assert f'/v2/show-commands/run/{lab["run_id"]}?list=Lab' in sources
        assert "Haiku 5.5" in html and re.search(r"· \$[0-9.]+", html), html[-900:]
        links = re.findall(r'href="/v2/history\?call=(ai-[0-9a-f]{16})[^"]*">Open call [12] in '
                           r'History</a>', html)
        assert len(links) == 2 and len(set(links)) == 2, html[-900:]
        assert len(lab["ran"]) == 1, "the one read, run once through the reads engine"


# ── a change is handed off ────────────────────────────────────────────────────────────────────

class TestAChangeIsHandedOff:
    def test_change_it_in_words_links_the_device_s_intent_tab_with_its_words(self, lab):
        from modules.ai import manual_index
        q = "shut GigabitEthernet4 on r2 intent change in words"
        chosen = manual_index.select(q)
        assert chosen, "the premise: a passage is chosen"
        lab["state"]["answer"] = words(
            "Change it on r2's Intent tab: you preview and commit it there.",
            cites=[chosen[0]["link"]], handoff={"flow": "intent_words",
                                                "words": "shut GigabitEthernet4"})
        r, html = post(lab, q)
        assert r.status_code == 200, html[:400]
        link = re.search(r'<a class="btn btn-small" data-op="assistant" href="([^"]+)"[^>]*>'
                         r'Change it in words…</a>', html)
        assert link, html[-1200:]
        assert link.group(1).startswith("/v2/device/r2?tab=intent&words=shut+GigabitEthernet4")
        assert link.group(1).endswith("#intent-words")
        assert len(lab["sent"]) == 1, "the one call answered; nothing was drafted"

    def test_the_intent_tab_opens_with_the_words_in_its_box_and_nothing_drafted(self, host):
        """The hand-off's address on the host's committed lab (tests/test_committed_before_p1's
        `host`, where s1's Intent tab draws): Change it in words holds the words, nothing is
        drafted and no call is made; without words the box is empty, as before."""
        c = host["client"]
        page = unescape(c.get("/v2/device/s1?tab=intent&list=Lab&words=shut+GigabitEthernet0/3")
                        .get_data(as_text=True))
        found = re.search(r'<input id="iw-words"[^>]*>', page)
        assert found, page[:600]
        assert 'value="shut GigabitEthernet0/3"' in found.group(0), found.group(0)
        assert "Drafting…" in page and "One draft, both ends" not in page
        plain = unescape(c.get("/v2/device/s1?tab=intent&list=Lab").get_data(as_text=True))
        assert 'value=""' in re.search(r'<input id="iw-words"[^>]*>', plain).group(0)
        assert calls.read()["rows"] == [], "opening the tab made no AI call"

    def test_on_an_incident_it_opens_ai_troubleshooting(self, lab):
        from modules.ai import manual_index
        chosen = manual_index.select("fix this incident with AI troubleshooting")
        assert chosen
        lab["state"]["answer"] = words("Open its AI troubleshooting and start it there.",
                                       cites=[chosen[0]["link"]],
                                       handoff={"flow": "ai_troubleshooting",
                                                "words": "find why r2 lost its stream"})
        _r, html = post(lab, "fix this incident with AI troubleshooting",
                        path=f"/v2/incident/{INCIDENT}?list=Lab")
        assert f'href="/v2/incident/{INCIDENT}?list=Lab#inc-fixit"' in html, html[-1200:]
        assert "Open AI troubleshooting</a>" in html
        assert _uses() == ["shown: answered"], "one call, its answer shown; nothing started"

    def test_a_hand_off_with_nothing_in_view_is_dropped_and_said(self, lab):
        from modules.ai import manual_index
        chosen = manual_index.select("How do I reload a device safely?")
        lab["state"]["answer"] = words(cites=[chosen[0]["link"]],
                                       handoff={"flow": "intent_words", "words": "reload it"})
        _r, html = post(lab, "How do I reload a device safely?", path="/v2/devices")
        assert "Change it in words…" not in html
        assert ("Mercury dropped the hand-off the answer named: it hands a change to a device's "
                "Intent tab, and no one device is in view") in html
        assert _uses() == ["shown: answered"]


# ── the thread ────────────────────────────────────────────────────────────────────────────────

class TestTheThread:
    def test_the_thread_is_drawn_again_and_asks_nothing(self, lab):
        from modules.ai import manual_index
        chosen = manual_index.select("How do I reload a device safely?")
        lab["state"]["answer"] = words("First answer.", cites=[chosen[0]["link"]])
        post(lab, "How do I reload a device safely?")
        lab["state"]["answer"] = words("Second answer.", cites=[chosen[0]["link"]])
        post(lab, "How do I reload a device safely, again?")
        sent = len(lab["sent"])
        r, html = panel(lab, "/v2/devices", nav="devices")
        assert r.status_code == 200 and 'id="asst-answer"' in html, html[:600]
        thread = html[html.index('id="asst-answer"'):html.index('<form class="op-act asst-ask"')]
        assert "First answer." in thread and "Second answer." in thread, thread[:600]
        assert thread.index("First answer.") < thread.index("Second answer."), "oldest first"
        assert "You asked, looking at r2 (device) · Lab:" in thread
        assert len(lab["sent"]) == sent, "drawing the thread made no call"

    def test_kept_owner_only_named_by_a_digest_masked_and_the_newest_20(self, lab):
        secret = "enable secret 9 $9$abcdefghijklmn$opqrstuvwxyz0123456789ABCDEFG"
        for n in range(assistant_threads.KEEP + 2):
            assistant_threads.keep(PERSON, f"question {n} {secret}", "Devices · Lab",
                                   {"state": "answered", "answer": f"answer {n}"})
        (name,) = [n for n in os.listdir(lab["tmp"] / "assistant_threads")
                   if n.endswith(".jsonl")]
        path = lab["tmp"] / "assistant_threads" / name
        assert PERSON not in name and name == assistant_threads.key_of(PERSON) + ".jsonl"
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        text = path.read_text()
        assert "opqrstuvwxyz0123456789" not in text, "the question kept masked"
        assert len(text.splitlines()) == assistant_threads.KEEP, "the file holds the newest 20"
        rows = assistant_threads.read(PERSON)["rows"]
        assert [r["got"]["answer"] for r in rows] == [f"answer {n}" for n in range(2, 22)]

    def test_no_verified_person_keeps_nothing(self, lab):
        from modules import identity
        got = assistant_threads.keep(identity.UNVERIFIED, "q", "", {"state": "answered"})
        assert got["ok"] is False and not os.path.exists(lab["tmp"] / "assistant_threads")
        assert assistant_threads.read(identity.UNVERIFIED) == {"state": "none", "error": "",
                                                              "rows": []}

    def test_an_unreadable_thread_is_said_never_read_as_none(self, lab):
        folder = lab["tmp"] / "assistant_threads"
        folder.mkdir()
        (folder / (assistant_threads.key_of(PERSON) + ".jsonl")).write_text("{not a row\n")
        assert assistant_threads.read(PERSON)["state"] == "unreadable"


# ── the button ────────────────────────────────────────────────────────────────────────────────

class TestTheButton:
    @staticmethod
    def _button(lab):
        page = lab["client"].get("/v2/devices").get_data(as_text=True)
        return page, re.search(r'<button[^>]*id="nmas-assistant"[^>]*>', page).group(0)

    def test_off_it_is_drawn_disabled_saying_where_and_its_ask_is_refused(self, lab):
        from modules import installation_settings as S
        lab["settings"]["ai_assistant_on"] = False
        page, button = self._button(lab)
        assert " disabled" in button and 'aria-disabled="true"' in button
        assert unescape(S.ASSISTANT_OFF_WORDS) in unescape(button)
        assert 'id="asst-panel"' not in page, "no panel while it is off"
        r, _html = post(lab, "How do I reload a device safely?")
        assert r.status_code == 409 and lab["sent"] == [] and calls.read()["rows"] == []

    def test_off_every_assistant_route_refuses_under_the_strict_policy(self, lab):
        """docs/FAST_LANE_DEBT.md's "The Assistant behind a setting" (a61bb071) owed "every
        assistant route refused while off (409 under the strict CSP)": each route of the
        Assistant's blueprint, asked by its own method, answers 409 with the off words and the
        strict policy, and nothing is asked of the model."""
        import app as APP
        from modules import csp
        from modules import installation_settings as S
        lab["settings"]["ai_assistant_on"] = False
        # The population, by the blueprint itself: a route it gains fails here until it is
        # asked below too.
        rules = {(r.rule, "POST" if "POST" in r.methods else "GET")
                 for r in APP.app.url_map.iter_rules() if r.endpoint.startswith("assistant_v2.")}
        assert rules == {("/v2/assistant/panel", "GET"), ("/v2/assistant/ask", "POST")}, rules
        client = lab["client"]
        for r in (client.get("/v2/assistant/panel", headers={"HX-Request": "true"}),
                  client.post("/v2/assistant/ask", data={"question": "hello"},
                              headers={"HX-Request": "true"})):
            body = r.get_data(as_text=True)
            assert r.status_code == 409, (r.request.path, r.status_code)
            assert unescape(S.ASSISTANT_OFF_WORDS) in unescape(body), body[:200]
            assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        assert lab["sent"] == [] and calls.read()["rows"] == []

    def test_a_setting_that_cannot_be_read_reads_off(self, monkeypatch):
        """The same row's "the unreadable setting reading off": only a stored True is on."""
        from modules import installation_settings as S
        from modules import settings_schema

        def unreadable(key, default=None):
            raise RuntimeError("the settings file cannot be read")
        monkeypatch.setattr(settings_schema, "get_setting", unreadable)
        assert S.assistant_on() is False
        monkeypatch.setattr(settings_schema, "get_setting", lambda key, default=None: "true")
        assert S.assistant_on() is False, "a hand-edited string is not a stored True"
        monkeypatch.setattr(settings_schema, "get_setting", lambda key, default=None: True)
        assert S.assistant_on() is True

    def test_hosted_ai_off_greys_it_and_its_panel_still_opens(self, lab, monkeypatch):
        monkeypatch.setattr("modules.ai.controls._hosted", lambda: {"allowed": False,
                                                                    "why": "off"})
        _page, button = self._button(lab)
        assert "asb-off" in button and " disabled" not in button
        assert "hosted AI is off" in unescape(button) and 'x-on:click="openAssistant"' in button
        r, html = panel(lab)
        assert r.status_code == 200 and 'data-ai-off-reason="assistant"' in html
        assert lab["sent"] == [], "drawing the page and the panel asked nothing"

    def test_ready_it_is_plain_and_the_page_s_draw_asks_nothing(self, lab):
        _page, button = self._button(lab)
        assert "asb-off" not in button and " disabled" not in button
        assert lab["sent"] == [] and calls.read()["rows"] == []


# ── in a real browser ─────────────────────────────────────────────────────────────────────────

#: The panel is open: its shell shown (Alpine's x-show) and its body drawn.
PANEL_OPEN = ("var p = document.getElementById('asst-panel');"
              "return !!p && getComputedStyle(p).display !== 'none'"
              " && !!document.getElementById('asst-q');")
ANSWERS = "return document.querySelectorAll('#asst-answer .asst-answer').length;"


def test_the_panel_in_a_browser_keeps_its_thread_and_opens_again_on_the_next_page(lab):
    """In Firefox: the Assistant opens the panel; Ask adds the answer under the thread in place;
    on the next page the panel opens again by itself, drawing the same thread with no call and
    taking no focus; closed, the next page leaves it closed."""
    from tests import browser
    if not browser.available()[0]:
        pytest.skip(browser.available()[1])
    import app as APP
    from modules.ai import manual_index

    chosen = manual_index.select("How do I reload a device safely?")
    lab["state"]["answer"] = words("Open the device page, then Actions › Reload….",
                                   cites=[chosen[0]["link"]])
    with browser.Served(APP.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/devices"))
            b.wait_for("return !!window.Alpine", 15)
            b.js("document.getElementById('nmas-assistant').click(); return 1")
            b.wait_for(PANEL_OPEN, 15)
            b.js("document.getElementById('asst-q').value = 'How do I reload a device safely?';"
                 "document.querySelector('[data-op=assistant]').click(); return 1")
            b.wait_for(ANSWERS + " /* one */ ", 15)
            first = b.js(ANSWERS)
            calls_after_ask = len(lab["sent"])
            b.go(srv.url("/v2/devices"))
            b.wait_for("return !!window.Alpine", 15)
            b.wait_for(PANEL_OPEN, 15)
            b.wait_for(ANSWERS, 15)
            again = b.js(ANSWERS)
            focused = b.js("return document.activeElement ? document.activeElement.id : ''")
            said = b.js("return document.getElementById('asst-answer').textContent")
            b.js("document.querySelector('#asst-panel [aria-label=\"Close the assistant\"]')"
                 ".click(); return 1")
            b.go(srv.url("/v2/devices"))
            b.wait_for("return !!window.Alpine && !!document.getElementById('asst-panel')", 15)
            closed = b.js("return getComputedStyle(document.getElementById('asst-panel'))"
                          ".display === 'none'")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert (first, again) == (1, 1), (first, again)
    assert "Actions › Reload…" in said and "How do I reload a device safely?" in said, said
    assert len(lab["sent"]) == calls_after_ask == 1, "the next page drew the thread, asked nothing"
    assert focused != "asst-q", "opened again by itself, it took no focus"
    assert closed is True, "closed, it stays closed on the next page"




# ── what leaves the host and what is kept, masked (the irreversible tier's hand check, ─────────
# ── 2026-11-24, docs/TIER_HAND_CHECK.md) ──────────────────────────────────────────────────────

#: A secret-shaped line: what a person may paste, or a device's configuration may hold.
SECRET_LINE = "enable secret 9 $9$abcdefghijklmn$opqrstuvwxyz0123456789ABCDEFG"
SECRET_VALUE = "opqrstuvwxyz0123456789"


class TestWhatLeavesAndWhatIsKeptIsMasked:
    def test_a_read_s_answer_leaves_with_its_secret_line_withheld(self, lab, monkeypatch):
        """A device read's answer holding a secret-shaped line: pass 2 is sent the answer
        with that line withheld whole and said, never the value (the read loop's mask, under
        the gateway's egress mask)."""
        reads_on(monkeypatch)
        from modules.nsot import reads

        def secret_run(list_name, hosts, commands, actor, **kw):
            lab["ran"].append({"hosts": list(hosts), "commands": list(commands)})
            return {"id": lab["run_id"], "results": {hosts[0]: {
                "answers": [{"state": "answered", "command": c,
                             "answer": f"hostname r2\n{SECRET_LINE}\nline vty 0 4"}
                            for c in commands],
                "signed_in_as": {"username": "mercury-ro", "source": "the read-only account"}}}}
        monkeypatch.setattr(reads, "run", secret_run)
        lab["queue"].extend([
            words("Reading r2 first.", covered=False, reads=[show()]),
            words("r2's vty lines are configured.", cites=["read:1"])])
        got = ask(lab, "What is configured on r2's vty lines?")
        assert lab["ran"], "the premise: the read ran"
        first, second = lab["sent"]
        assert "line vty 0 4" in second["bytes"], "the premise: the read's answer was sent"
        assert SECRET_VALUE not in second["bytes"] and SECRET_VALUE not in first["bytes"]
        assert "1 line withheld: a secret's shape" in second["bytes"], second["bytes"][-800:]
        assert got["state"] == "answered", got

    def test_looking_at_sends_the_page_s_names_never_its_path_or_query(self, lab):
        """What the model is told it is looking at is the five names alone: the page's path
        and query (which may carry words a person typed) never leave the host."""
        from modules.ai import manual_index
        q = "How do I reload a device safely?"
        chosen = manual_index.select(q)
        assert chosen, "the premise: a passage is chosen"
        lab["state"]["answer"] = words(cites=[chosen[0]["link"]])
        ask(lab, q, where="/v2/device/r2?tab=intent&list=Lab&words=zebra-marker-words")
        (only,) = lab["sent"]
        assert "zebra-marker-words" not in only["bytes"]
        sent = assistant.looking_at(place("/v2/device/r2?tab=intent&words=zebra-marker-words"))
        assert sorted(sent) == ["device", "devices", "incident", "network", "screen"], sent

    def test_a_hand_off_s_words_are_masked_in_its_address_and_on_the_page(self, lab):
        from modules.ai import manual_index
        q = "change r2's enable secret intent change in words"
        chosen = manual_index.select(q)
        assert chosen, "the premise: a passage is chosen"
        lab["state"]["answer"] = words("Change it on r2's Intent tab.",
                                       cites=[chosen[0]["link"]],
                                       handoff={"flow": "intent_words", "words": SECRET_LINE})
        r, html = post(lab, q)
        assert r.status_code == 200 and "Change it in words…" in html, html[-1200:]
        assert SECRET_VALUE not in html
        # The press's effect: the exchange kept in the person's thread, its hand-off masked.
        text = kept_text(lab)
        assert "intent_words" in text, text[-600:]
        assert SECRET_VALUE not in text

    def test_the_question_drawn_back_is_masked(self, lab):
        from modules.ai import manual_index
        q = "How do I reload a device safely?"
        chosen = manual_index.select(q)
        lab["state"]["answer"] = words(cites=[chosen[0]["link"]])
        r, html = post(lab, f"{q} {SECRET_LINE}")
        assert r.status_code == 200 and "You asked" in html, html[:600]
        assert SECRET_VALUE not in html
        # The press's effect: the question kept in the person's thread, masked as it left.
        text = kept_text(lab)
        assert q in text, text[-600:]
        assert SECRET_VALUE not in text

    def test_the_answer_kept_is_masked_again_in_an_owner_only_folder(self, lab):
        got = assistant_threads.keep(PERSON, "q", "Devices · Lab",
                                     {"state": "answered",
                                      "answer": f"Set it so:\n{SECRET_LINE}"})
        assert got["ok"], got
        folder = lab["tmp"] / "assistant_threads"
        assert stat.S_IMODE(os.stat(folder).st_mode) == 0o700
        text = (folder / (assistant_threads.key_of(PERSON) + ".jsonl")).read_text()
        assert "enable secret" in text and SECRET_VALUE not in text, text

    def test_a_read_s_answer_is_never_kept_in_the_thread(self, lab, monkeypatch):
        """The thread keeps what the panel drew of each read (its id, words, verdict, links),
        never the read's answer: that stays in the send log's digests and History › Reads."""
        reads_on(monkeypatch)
        from modules.nsot import reads

        def marked_run(list_name, hosts, commands, actor, **kw):
            lab["ran"].append({"hosts": list(hosts)})
            return {"id": lab["run_id"], "results": {hosts[0]: {
                "answers": [{"state": "answered", "command": c,
                             "answer": "Processor board ID quokka-serial-77"} for c in commands],
                "signed_in_as": {"username": "mercury-ro", "source": "the read-only account"}}}}
        monkeypatch.setattr(reads, "run", marked_run)
        lab["queue"].extend([
            words("Reading r2's version first.", covered=False, reads=[show()]),
            words("r2's board is in the read.", cites=["read:1"])])
        r, html = post(lab, "What version is r2 running?")
        assert r.status_code == 200 and lab["ran"], html[:400]
        assert "quokka-serial-77" in lab["sent"][1]["bytes"], "the premise: the read was sent"
        folder = lab["tmp"] / "assistant_threads"
        assert folder.is_dir(), html[-1500:]
        (name,) = [n for n in os.listdir(folder) if n.endswith(".jsonl")]
        kept = (folder / name).read_text()
        assert '"read:1"' in kept and "quokka-serial-77" not in kept, kept

    def test_a_device_name_not_of_a_device_s_shape_names_nothing(self, lab):
        got = place("/v2/device/r2;zz$?tab=overview&list=Lab")
        assert (got["device"], got["label"]) == ("", "Lab"), got
