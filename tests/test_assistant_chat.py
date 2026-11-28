"""The toolbar assistant as a continuous chat (the operator's order of 2026-11-28; board
assistant-chat; routes/assistant_v2.py, modules/ai/assistant_turns.py,
modules/ai/assistant_threads.py, modules/ai/answer_text.py). The gateway is real (its trigger,
caps, mask and record), the provider a fake answering each pass in turn (tests/
test_ai_assistant_stage2's `lab`); no provider, device or network is reached. Its browser
behaviour is tests/test_assistant_chat_browser.py's.

- **Send answers at once:** the press keeps its turn and starts its job; the turn is drawn
  working, with Stop in Send's place, and once the job ends its answer is drawn, Send back.
- **Progress steps, not a stream:** each step the answer takes is kept on the turn as it runs,
  in a person's words, and announced.
- **Stop:** a stop read before the next call makes no further call or read; the exchange is
  kept as stopped with the calls it made; the gateway is handed the stop to close a stream.
- **One question at a time:** a second press while one is answered is refused, naming why.
- **Each message records its page:** the path it was asked on is kept with the exchange.
- **Past conversations:** New conversation keeps the current one, as it is, under the past
  ones; Reopen makes one current again, the current one kept in its place; nothing is deleted,
  and the current conversation's file keeps the shape the release before reads.
- **A lost turn** (no sign of life past `LOST_S`) is drawn as lost, never working for ever,
  and a read of it writes nothing.
- **The answer's words** are markdown drawn by Mercury, every character escaped.
"""
import json
import os
import re
import time
from html import unescape

import pytest

from modules.ai import assistant, assistant_threads, calls
from tests import assistant_ask
from tests.conftest import TEST_PERSON
from tests.test_ai_assistant import world  # noqa: F401 (the fixture)
# Not stage 2's `as_person`: every press here is the client's own request, whose verified
# person is the harness's (tests/conftest.py, TEST_PERSON), and a request context held open
# around it would lend its app context's identity to the client's reads.
from tests.test_ai_assistant_stage2 import DEVICE_PATH, lab, panel, reads_on, show, words  # noqa: F401
from tests.test_committed_before_p1 import host  # noqa: F401 (the fixture)

Q = "How do I reload a device safely?"


def _chosen(q=Q):
    from modules.ai import manual_index
    chosen = manual_index.select(q)
    assert chosen, "the premise: a passage is chosen"
    return chosen


def _press(lab, question=Q, path=DEVICE_PATH):
    r = lab["client"].post("/v2/assistant/ask?list=Lab",
                           data={"question": question, "screen": "", "path": path})
    return r, unescape(r.get_data(as_text=True))


def _act(html: str) -> str:
    """The box's control slot's opening tag, as the panel draws it."""
    m = re.search(r'<span class="asst-act[^"]*" id="asst-act">', html)
    assert m, html[-600:]
    return m.group(0)


class TestSendAnswersAtOnce:
    def test_the_press_draws_its_turn_working_with_stop_then_the_answer_with_send(
            self, lab, monkeypatch):
        """The press's answer is the turn, working (it re-reads on each announced step), and the
        panel drawn meanwhile puts Stop in Send's place; once its job ends, the turn's read is
        the answer and the panel's control is Send again."""
        import threading
        gate = threading.Event()
        real = assistant.answer

        def held(*a, **k):
            # The job's answer waits until the test has read the working turn.
            assert gate.wait(10), "the test never let the answer go"
            return real(*a, **k)
        monkeypatch.setattr(assistant, "answer", held)
        lab["state"]["answer"] = words("Open the device page, then **Actions › Reload…**.",
                                       cites=[_chosen()[0]["link"]])
        r, html = _press(lab)
        assert r.status_code == 200, html[:400]
        turn = assistant_ask.turn_id(html)
        assert turn and 'data-turn-state="working"' in html, html[:600]
        assert re.search(rf'hx-get="/v2/assistant/turn/{turn}[?"]', html), html[:300]
        assert 'hx-trigger="nmas:assistant from:body"' in html
        assert f'<p class="asst-q">{Q}</p>' in html, "the question is drawn at once"
        _r, drawn = panel(lab)
        assert "asst-working" in _act(drawn), _act(drawn)
        assert "hx-post=\"/v2/assistant/stop" in drawn and \
            "hx-target=\"#asst-answer .asst-turn[data-turn-state='working']\"" in drawn
        assert lab["sent"] == [], "nothing was asked before the job ran"
        gate.set()
        assistant_ask.wait_all()
        got = lab["client"].get(f"/v2/assistant/turn/{turn}")
        body = unescape(got.get_data(as_text=True))
        assert 'data-turn-state="done"' in body and "hx-trigger" not in body, body[:600]
        assert "<strong>Actions › Reload…</strong>" in body, "the answer's markdown, drawn"
        _r, drawn = panel(lab)
        assert "asst-working" not in _act(drawn), _act(drawn)
        assert len(lab["sent"]) == 1

    def test_a_question_refused_before_any_call_is_said_at_once_and_kept_nowhere(self, lab):
        r, html = _press(lab, question="   ")
        assert r.status_code == 200 and "Ask a question first." in html, html[:400]
        assert not assistant_threads._turns(TEST_PERSON), "no turn was kept"
        assert assistant_threads.read(TEST_PERSON)["rows"] == []
        assert lab["sent"] == []


class TestProgressSteps:
    def test_each_step_is_kept_on_the_turn_as_it_runs_and_announced(self, lab, monkeypatch):
        """The steps a press takes, kept as it runs (the read loop's two calls and its round of
        reads), each announced under ``assistant``."""
        from modules import invalidation
        from modules.ai import assistant_turns
        reads_on(monkeypatch)
        steps, heard = [], []
        real_step = assistant_threads.step
        monkeypatch.setattr(assistant_threads, "step",
                            lambda actor, turn, w, now=None: (steps.append(w),
                                                              real_step(actor, turn, w, now)))
        monkeypatch.setattr(invalidation, "announce",
                            lambda keys, by, ok=True: heard.append((tuple(keys), by)) or {})
        chosen = _chosen("What version is r2 running? reload")
        lab["queue"].extend([words("Reading r2's version first.", covered=False, reads=[show()]),
                             words("r2 runs 17.09.01a.", cites=[chosen[0]["link"], "read:1"])])
        r = assistant_ask.ask(lab["client"], {"question": "What version is r2 running? reload",
                                              "screen": "", "path": DEVICE_PATH},
                              query_string={"list": "Lab"})
        assert "r2 runs 17.09.01a." in unescape(r.get_data(as_text=True))
        assert steps == ["Choosing the manual's passages", "Asking the model",
                         "Running the 1 read it asked for", "Answering from the reads (call 2)"]
        assert heard.count((assistant_turns.STEP_KEYS, assistant_turns.ANNOUNCER)) == len(steps)


class TestStop:
    def test_a_stop_before_the_next_call_makes_no_call_or_read_and_is_kept_stopped(
            self, lab, monkeypatch):
        reads_on(monkeypatch)
        chosen = _chosen("What version is r2 running? reload")
        lab["queue"].extend([words("Reading r2's version first.", covered=False, reads=[show()]),
                             words("never asked", cites=[chosen[0]["link"]])])
        handed = []
        from modules.ai import gateway
        real_ask = gateway.ask

        def ask(*a, stop_if=None, **k):
            handed.append(stop_if)
            got = real_ask(*a, stop_if=stop_if, **k)
            # The person presses Stop while the first call streams.
            assistant_threads.stop(TEST_PERSON, next(iter(assistant_threads._turns(
                TEST_PERSON))))
            return got
        monkeypatch.setattr(gateway, "ask", ask)
        r = assistant_ask.ask(lab["client"], {"question": "What version is r2 running? reload",
                                              "screen": "", "path": DEVICE_PATH},
                              query_string={"list": "Lab"})
        body = unescape(r.get_data(as_text=True))
        assert len(lab["sent"]) == 1, "no call after Stop"
        assert lab["ran"] == [], "no read after Stop"
        assert callable(handed[0]), "the gateway was handed the stop, to close its stream"
        assert "Stopped by you." in body and "never asked" not in body, body[:800]
        (row,) = assistant_threads.read(TEST_PERSON)["rows"]
        assert row["got"]["state"] == "stopped" and len(row["got"]["calls"]) == 1, row
        assert re.search(r'href="/v2/history\?call=ai-[0-9a-f]{16}', body), "its call's link"
        assert len(calls.read()["rows"]) == 1, "the one call made is recorded"

    def test_stop_marks_the_turn_and_draws_it_stopping(self, lab):
        got = assistant_threads.begin(TEST_PERSON, Q, "Devices · Lab", "/v2/devices")
        r = lab["client"].post("/v2/assistant/stop")
        body = unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and "Stopping: closing the model's answer…" in body, body
        assert f'id="asst-turn-{got["turn"]}" data-turn-state="working"' in body
        assert assistant_threads.stop_asked(TEST_PERSON, got["turn"])
        assistant_threads.finish(TEST_PERSON, got["turn"], {"state": "stopped"})
        r = lab["client"].post("/v2/assistant/stop")
        assert r.status_code == 409 and "no question of yours is being answered now" in \
            unescape(r.get_data(as_text=True))


class TestOneAtATime:
    def test_a_second_press_while_one_is_answered_is_refused_naming_why(self, lab):
        first = assistant_threads.begin(TEST_PERSON, Q, "Devices · Lab", "/v2/devices")
        assert first["ok"]
        r, html = _press(lab, "And another?")
        assert r.status_code == 409 and "your last question is still being answered" in html
        assert 'id="asst-turn-' not in html, "the working turn is left as it is"
        assert lab["sent"] == []


class TestEachMessageRecordsItsPage:
    def test_the_path_asked_on_is_kept_with_the_exchange_and_on_its_hover(self, lab):
        lab["state"]["answer"] = words(cites=[_chosen()[0]["link"]])
        r = assistant_ask.ask(lab["client"], {"question": Q, "screen": "", "path": DEVICE_PATH},
                              query_string={"list": "Lab"})
        (row,) = assistant_threads.read(TEST_PERSON)["rows"]
        assert row.get("page") == DEVICE_PATH and row.get("turn") and row.get("took_s", -1) >= 0, \
            row
        assert row["looking_at"] == "r2 (device) · Lab"
        body = unescape(r.get_data(as_text=True))
        assert f'title="Asked on {DEVICE_PATH}"' in body
        assert re.search(r"· <span title=\"From Send to the answer kept\">\d+ s</span>", body)


class TestPastConversations:
    def test_new_keeps_the_current_one_and_reopen_brings_it_back(self, lab):
        lab["state"]["answer"] = words("The first conversation's answer.",
                                       cites=[_chosen()[0]["link"]])
        assistant_ask.ask(lab["client"], {"question": Q, "screen": "", "path": DEVICE_PATH},
                          query_string={"list": "Lab"})
        before = open(assistant_threads.path_of(TEST_PERSON), encoding="utf-8").read()
        r = lab["client"].post("/v2/assistant/new", data={"path": "/v2/devices", "nav": "devices"})
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and "data-asst-empty" in html, html[:600]
        assert "The first conversation's answer." not in html.split('id="asst-answer"')[1]
        (past,) = assistant_threads.past(TEST_PERSON)["rows"]
        assert past["first"] == Q and past["count"] == 1
        assert f'data-conversation="{past["id"]}"' in html and ">Reopen<" in html
        kept = os.path.join(assistant_threads.past_dir(TEST_PERSON), past["id"] + ".jsonl")
        assert open(kept, encoding="utf-8").read() == before, "kept as it was, whole"
        # A second conversation, then the first reopened: the second kept in its place.
        lab["state"]["answer"] = words("The second conversation's answer.",
                                       cites=[_chosen()[0]["link"]])
        assistant_ask.ask(lab["client"], {"question": "And the second?", "screen": "",
                                          "path": DEVICE_PATH}, query_string={"list": "Lab"})
        r = lab["client"].post("/v2/assistant/reopen", data={"conversation": past["id"],
                                                             "path": "/v2/devices"})
        thread = unescape(r.get_data(as_text=True)).split('id="asst-answer"')[1]
        assert "The first conversation's answer." in thread
        assert "The second conversation's answer." not in thread
        rows = assistant_threads.past(TEST_PERSON)["rows"]
        assert [p["first"] for p in rows] == ["And the second?"], rows
        assert not os.path.exists(kept), "moved back, never copied"

    def test_a_reopen_of_an_id_not_the_person_s_is_refused_by_name(self, lab):
        r = lab["client"].post("/v2/assistant/reopen", data={"conversation": "../../etc"})
        assert r.status_code == 409 and "is not a past conversation's id" in unescape(
            r.get_data(as_text=True))
        r = lab["client"].post("/v2/assistant/reopen",
                               data={"conversation": "20261128T000000Z-0123abcd"})
        assert r.status_code == 409 and "no past conversation 20261128T000000Z-0123abcd" in \
            unescape(r.get_data(as_text=True))

    def test_nothing_is_put_aside_while_a_question_is_answered(self, lab):
        assistant_threads.keep(TEST_PERSON, Q, "Devices · Lab", {"state": "answered"})
        assistant_threads.begin(TEST_PERSON, "next", "Devices · Lab", "/v2/devices")
        r = lab["client"].post("/v2/assistant/new")
        assert r.status_code == 409 and "still being answered" in unescape(r.get_data(as_text=True))
        assert assistant_threads.past(TEST_PERSON)["rows"] == []

    def test_the_current_file_keeps_the_shape_the_release_before_reads(self, lab):
        """Expand, then contract: the current conversation is the one file the release before
        read, its rows the shape it drew (``at``, ``question``, ``looking_at``, ``got``), the new
        fields beside them."""
        lab["state"]["answer"] = words(cites=[_chosen()[0]["link"]])
        assistant_ask.ask(lab["client"], {"question": Q, "screen": "", "path": DEVICE_PATH},
                          query_string={"list": "Lab"})
        path = os.path.join(lab["tmp"], "assistant_threads",
                            assistant_threads.key_of(TEST_PERSON) + ".jsonl")
        (row,) = [json.loads(line) for line in open(path, encoding="utf-8")]
        assert {"at", "question", "looking_at", "got"} <= set(row), row
        assert row["got"]["state"] == "answered" and row["got"]["answer"]


class TestALostTurn:
    def test_a_turn_with_no_sign_of_life_is_drawn_lost_and_its_read_writes_nothing(self, lab):
        got = assistant_threads.begin(TEST_PERSON, Q, "Devices · Lab", "/v2/devices",
                                      now=time.time() - assistant_threads.LOST_S - 5)
        before = open(assistant_threads.turns_path(TEST_PERSON), encoding="utf-8").read()
        r = lab["client"].get(f"/v2/assistant/turn/{got['turn']}")
        body = unescape(r.get_data(as_text=True))
        assert "No answer arrived" in body and 'data-turn-state="working"' not in body, body
        assert open(assistant_threads.turns_path(TEST_PERSON),
                    encoding="utf-8").read() == before, "the read wrote nothing"
        # The next press keeps it in the conversation as lost, and may ask again.
        again = assistant_threads.begin(TEST_PERSON, "again", "Devices · Lab", "/v2/devices")
        assert again["ok"], again
        (row,) = assistant_threads.read(TEST_PERSON)["rows"]
        assert row["question"] == Q and row["got"]["state"] == "lost"


class TestTheReviewOf20261128:
    """The independent review of the chat (2026-11-28): a job whose turn is gone or ended
    stops at its next check; Stop's words say only what is true; a person's Stop is recorded
    as theirs beside the call; a turn stopping is still busy; a turn ended but not kept is not
    working and is kept by the next press; a question refused at once draws no turn id."""

    def test_a_job_whose_turn_is_gone_or_ended_stops_at_its_next_check(self, lab, monkeypatch):
        old = assistant_threads.begin(TEST_PERSON, Q, "Devices · Lab", "/v2/devices",
                                      now=time.time() - assistant_threads.LOST_S - 5)
        # The next press keeps the lost turn in the conversation and lets it go.
        assert assistant_threads.begin(TEST_PERSON, "next", "Devices · Lab", "/v2/devices")["ok"]
        assert old["turn"] not in assistant_threads._turns(TEST_PERSON)
        assert assistant_threads.stop_asked(TEST_PERSON, old["turn"]) is True, "gone: stop"
        monkeypatch.setattr(assistant_threads, "keep",
                            lambda *a, **k: {"ok": False, "error": "OSError: disk full"})
        (now,) = [k for k in assistant_threads._turns(TEST_PERSON)]
        assistant_threads.finish(TEST_PERSON, now, {"state": "answered", "answer": "x"})
        assert assistant_threads._turns(TEST_PERSON)[now].get("ended") is True
        assert assistant_threads.stop_asked(TEST_PERSON, now) is True, "ended: stop"

    def test_stop_s_words_say_only_what_is_true(self, lab):
        import os as _os
        words_ = assistant.STOPPED
        assert "Nothing more was asked or read" not in words_
        assert "No call was made after Stop" in words_ and "already running" in words_, words_
        _r, html = panel(lab)
        stop = re.search(r'<button[^>]*data-asst-stop[^>]*>', html).group(0)
        assert "nothing more is asked or read" not in stop and "no call is made after it" in \
            stop, stop
        page = open(_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(
            __file__))), "docs", "manual", "how-it-works", "assistant.md"),
            encoding="utf-8").read()
        assert "nothing more is asked or read after it" not in page
        assert "no call is made after it" in page

    def test_a_person_s_stop_is_recorded_as_theirs_beside_the_call(self, lab, monkeypatch):
        reads_on(monkeypatch)
        chosen = _chosen("What version is r2 running? reload")
        lab["queue"].extend([words("Reading r2's version first.", covered=False, reads=[show()]),
                             words("never asked", cites=[chosen[0]["link"]])])
        from modules.ai import gateway
        real_ask = gateway.ask

        def ask(*a, **k):
            got = real_ask(*a, **k)
            assistant_threads.stop(TEST_PERSON, next(iter(assistant_threads._turns(
                TEST_PERSON))))
            return got
        monkeypatch.setattr(gateway, "ask", ask)
        assistant_ask.ask(lab["client"], {"question": "What version is r2 running? reload",
                                          "screen": "", "path": DEVICE_PATH},
                          query_string={"list": "Lab"})
        (row,) = assistant_threads.read(TEST_PERSON)["rows"]
        (call,) = row["got"]["calls"]
        said = [u for u in calls.uses().get(call, []) if u["use"] == "stopped by the person"]
        assert said and said[0]["actor"] == TEST_PERSON, calls.uses().get(call)
        assert "Stopped by the person who asked" in said[0]["detail"], said

    def test_a_turn_stopping_is_still_busy(self, lab):
        got = assistant_threads.begin(TEST_PERSON, Q, "Devices · Lab", "/v2/devices")
        assistant_threads.keep(TEST_PERSON, "earlier", "Devices · Lab", {"state": "answered"})
        assert assistant_threads.stop(TEST_PERSON, got["turn"])["ok"]
        again = assistant_threads.begin(TEST_PERSON, "another", "Devices · Lab", "/v2/devices")
        assert again["ok"] is False and "still being answered" in again["error"], again
        new = assistant_threads.new(TEST_PERSON)
        assert new["ok"] is False and "still being answered" in new["error"], new

    def test_a_turn_ended_but_not_kept_is_not_working_and_the_next_press_keeps_it(
            self, lab, monkeypatch):
        got = assistant_threads.begin(TEST_PERSON, Q, "Devices · Lab", "/v2/devices")
        real_keep = assistant_threads.keep
        monkeypatch.setattr(assistant_threads, "keep",
                            lambda *a, **k: {"ok": False, "error": "OSError: disk full"})
        assistant_threads.finish(TEST_PERSON, got["turn"], {"state": "answered",
                                                            "answer": "kept late"})
        monkeypatch.setattr(assistant_threads, "keep", real_keep)
        again = assistant_threads.begin(TEST_PERSON, "next", "Devices · Lab", "/v2/devices")
        assert again["ok"], again
        rows = assistant_threads.read(TEST_PERSON)["rows"]
        assert [r["got"].get("answer") for r in rows] == ["kept late"], rows
        assert got["turn"] not in assistant_threads._turns(TEST_PERSON)

    def test_a_question_refused_at_once_draws_no_turn_id(self, lab):
        _r, html = _press(lab, question="   ")
        _r, again = _press(lab, question="")
        assert "Ask a question first." in html and 'id="asst-turn-' not in html, html[:300]
        assert 'id="asst-turn-' not in again, "two refusals in one conversation, no id twice"
        # The press's effect: nothing kept, no turn started.
        assert assistant_threads._turns(TEST_PERSON) == {}
        assert assistant_threads.read(TEST_PERSON)["rows"] == [] and lab["sent"] == []


class TestTheAnswersWords:
    def test_markdown_is_drawn_and_every_character_the_model_wrote_is_escaped(self):
        from modules.ai import answer_text
        text = ("Two steps:\n\n1. Open **r2**.\n2. Press `Reload…`.\n\n"
                "| Device | Version |\n|---|---|\n| r2 | 17.9 |\n\n"
                "```\nshow version\n```\n"
                "<script>alert(1)</script> and [a link](https://example.com/x) *here*")
        got = str(answer_text.render(text))
        assert "<ol><li>Open <strong>r2</strong>.</li><li>Press <code>Reload…</code>.</li></ol>" \
            in got, got
        assert "<th>Device</th><th>Version</th>" in got and "<td>r2</td><td>17.9</td>" in got
        assert "<pre><code>show version</code></pre>" in got
        assert "<script>" not in got and "&lt;script&gt;alert(1)&lt;/script&gt;" in got
        assert "<a " not in got and "a link (https://example.com/x)" in got, got
        assert "<em>here</em>" in got


class TestThePlace:
    def test_the_chip_is_resolved_by_the_server_for_the_address_now(self, lab):
        r = lab["client"].get("/v2/assistant/place",
                              query_string={"path": "/v2/device/r2?tab=intent&list=Lab",
                                            "list": "Lab"})
        body = unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and "Looking at: <strong>r2 (device) · Lab</strong>" in body
        assert 'data-asked="/v2/device/r2?tab=intent&list=Lab"' in body
        assert "It reads only r2" in body and lab["sent"] == []


class TestThePanel:
    def test_it_draws_the_past_conversations_and_its_head_s_controls(self, lab):
        assistant_threads.keep(TEST_PERSON, "An earlier question", "Devices · Lab",
                               {"state": "answered", "answer": "yes"})
        assistant_threads.new(TEST_PERSON)
        r, html = panel(lab)
        assert r.status_code == 200
        head = html[:html.index('id="asst-answer"')]
        for words_ in ("New conversation", 'aria-label="Past conversations"',
                       'aria-label="About the assistant"', 'aria-label="Close the assistant"',
                       "Beta · advisory", "An earlier question", ">Reopen<"):
            assert words_ in head, words_
        assert re.search(r'<time class="clock" datetime="[^"]+"', head), "when, in the viewer's zone"
        assert "It changes nothing" in head, "behind the ⓘ"
        assert "data-asst-empty" in html and lab["sent"] == []
