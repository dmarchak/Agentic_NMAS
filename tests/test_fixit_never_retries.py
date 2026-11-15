"""No path retries without a person (the operator's test 1, 2026-11-11: "FAIL: STOP. Never
retry on its own"), for everything but the AI gateway, which comes with the AI's own call (the
fix-it plan's S4; board recurring-fixes v2, guard G3: "there is no screen for this, because
there is no control for it").

- **By parsing:** every definition in the program that reaches a proposer (`modules/fixit/
  proposers.py`, Mercury's own, and the AI's, `modules/ai/fixit_troubleshoot.troubleshoot`,
  S5) is exactly a person's presses (`PERSON_CALLERS`: Start AI troubleshooting, Ask the AI again
  and Modify) and, since the operator's R1 (2026-11-14), the notifier's
  automatic start (`AUTO_START`), reached only from its pass, which takes each failure once
  under the incident record's lock; each route is served by POST alone and declared in
  `modules/route_gates.py` as a verified person's configure gate (the gateway's own entry
  points: tests/test_ai_entry_points.py). Mercury's own re-plan (Retry with more information)
  is gone. The set is compared whole,
  here, by the test that holds it; a planted GET route, timer and job reaching a proposer are
  each found by the same scan.
- **By the template:** the section loads and repeats nothing by itself: no ``hx-trigger`` of
  ``load``, ``every``, ``revealed`` or ``intersect``, and no ``hx-get`` but the operation's card
  a person opens (a planted one of each is found).
- **By behaviour:** after a failed attempt, with the page drawn again and again, the
  operation's end announced and the section's own records read, the proposer is called zero
  times, the AI gateway zero times, and no job or device hold is started.
"""
import ast
import os
import re

import pytest

from tests import test_fixit_incident as FI
from tests.test_fixit_section_v2 import attempt, page, plant, section_of
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECTION = os.path.join(ROOT, "templates", "v2", "_fixit_section.html")


#: The AI's proposer (S5): one investigation, its answer through the one door.
AI_PROPOSER = ("modules.ai.fixit_troubleshoot", "troubleshoot")


def proposer_seeds(refs: dict) -> set:
    """Every proposer: each top-level function of modules/fixit/proposers.py whose name is
    not private, and the AI's (`AI_PROPOSER`), read from the program's own references."""
    return {k for k in refs if (k[0] == "modules.fixit.proposers" and not k[1].startswith("_")
                                and k[1] != FI.TOP) or k == AI_PROPOSER}


#: The one path that asks the AI with no person's press (the operator's R1, 2026-11-14: "When
#: Mercury's code fix fails, the AI troubleshoots automatically"): the notifier's automatic
#: investigation, started only by `heal_notice.run_fixit`, which takes each failure ONCE under
#: the incident record's lock (`incident.claim_start`) and only while the network's switch
#: is on. Its investigation proposes; nothing runs without a person's Approve.
AUTO_START = ("modules.heal_notice", "fixit_investigation")
#: The person's presses that ask the AI (routes/fixit_v2.py), each a POST.
PERSON_CALLERS = {("routes.fixit_v2", "_ask"), ("routes.fixit_v2", "ask_again"),
                  ("routes.fixit_v2", "modify"), ("routes.fixit_v2", "start")}


def reaching(planted: str = "", without=()) -> set:
    """The program's definitions outside the proposers module that reach a proposer; with
    *planted*, a module's text, as if routes/planted_v2.py held it; *without*, definitions
    taken out of the program (to ask what reaches a proposer by another path)."""
    got = FI.program()
    refs = {k: v for k, v in got["refs"].items() if k not in without}
    if planted:
        one = {"routes/planted_v2.py": planted}
        refs.update(FI.references(one, FI.module_names(dict(got["sources"], **one))))
    seeds = proposer_seeds(refs)
    return {k for k in FI.starting(refs, seeds) if k not in seeds
            and k[0] != "modules.fixit.proposers"}


class TestByParsing:
    def test_the_population_and_its_seed(self):
        refs = FI.program()["refs"]
        assert ("modules.fixit.proposers", "mercury") in proposer_seeds(refs)
        assert AI_PROPOSER in proposer_seeds(refs)
        assert AUTO_START in refs and PERSON_CALLERS <= set(refs)
        # Retry with more information is gone (R1: Deny and Modify replace it).
        assert ("routes.fixit_v2", "retry") not in refs
        assert ("modules.fixit.section", "retry") not in refs

    def test_every_caller_of_a_proposer_is_a_persons_press_or_the_automatic_start(self):
        # With the automatic start taken out, only a person's presses reach a proposer.
        assert reaching(without=[AUTO_START]) == PERSON_CALLERS
        # And the automatic start is reached only through the notifier's pass, which takes
        # each failure once before it starts one (`claim_start`, by reference).
        refs = FI.program()["refs"]
        callers = {k for k, named in refs.items() if AUTO_START in named}
        assert callers == {("modules.heal_notice", "run_fixit")}
        assert ("modules.fixit.incident", "claim_start") in refs[("modules.heal_notice",
                                                                  "run_fixit")]
        # And the pass is the notifier's alone: run_fixit is called by heal_notice.run only,
        # and run by the heal runner's notify step only.
        run_fixit, run = ("modules.heal_notice", "run_fixit"), ("modules.heal_notice", "run")
        assert {k for k, named in refs.items() if run_fixit in named} == {run}
        assert {k for k, named in refs.items() if run in named} == {
            ("modules.heal.detect", "_notify_step")}

    @pytest.mark.parametrize("endpoint", ["fixit_v2.modify",
                                          "fixit_v2.ask_again", "fixit_v2.start"])
    def test_the_retry_route_is_a_post_a_person_makes(self, endpoint):
        import app as A
        from modules.route_gates import GATES
        rules = [r for r in A.app.url_map.iter_rules() if r.endpoint == endpoint]
        assert len(rules) == 1
        assert rules[0].methods - {"OPTIONS"} == {"POST"}
        assert GATES[endpoint].kind == "configure"

    @pytest.mark.parametrize("planted", [
        # a GET route
        ("from flask import Blueprint\nfrom modules.fixit import section\n"
         "bp = Blueprint('planted', __name__)\n\n"
         "@bp.route('/x', methods=['GET'])\ndef look():\n"
         "    from modules.fixit import proposers\n"
         "    return proposers.mercury(section, {})\n"),
        # a timer
        ("import threading\nfrom modules.fixit import proposers\n\n"
         "def every_minute(i):\n"
         "    threading.Timer(60, lambda: proposers.mercury(i, {})).start()\n"),
        # a job
        ("from modules.nsot import capture_job\nfrom modules.fixit import proposers\n\n"
         "def background(i):\n"
         "    return capture_job.start('Default', 'x', 'y', lambda j: proposers.mercury(i))\n"),
        # a failure's handler asking the AI (S5)
        ("from modules.ai import fixit_troubleshoot\n\n"
         "def on_failed(i):\n"
         "    return fixit_troubleshoot.troubleshoot('Default', {}, i, actor='', "
         "actor_verified='', person=False)\n"),
    ], ids=["a GET route", "a timer", "a job", "a failure's handler asking the AI"])
    def test_a_planted_caller_is_found(self, planted):
        found = reaching(planted, without=[AUTO_START])
        assert {k for k in found if k[0] == "routes.planted_v2"}, found


TRIGGERS = re.compile(r'hx-trigger="[^"]*\b(load|every|revealed|intersect)\b')


def section_problems(text: str) -> list:
    """What in the section's template would load or repeat a request with no person's press."""
    out = [f"hx-trigger {m.group(1)}" for m in TRIGGERS.finditer(text)]
    out += [f"an hx-get on a <{m.group(1)}> that is no button"
            for m in re.finditer(r"<(\w+)\b[^>]*\bhx-get=", text) if m.group(1) != "button"]
    return out


class TestTheTemplate:
    def test_the_section_loads_and_repeats_nothing(self):
        with open(SECTION, encoding="utf-8") as fh:
            text = fh.read()
        assert "hx-post" in text and "<button" in text
        assert section_problems(text) == []

    @pytest.mark.parametrize("planted,found", [
        ('<div hx-get="/x" hx-trigger="load">', "hx-trigger load"),
        ('<div hx-post="/x" hx-trigger="every 30s">', "hx-trigger every"),
        ('<p hx-trigger="revealed" hx-post="/x">', "hx-trigger revealed"),
        ('<span hx-get="/x">', "an hx-get on a <span> that is no button"),
    ])
    def test_a_planted_trigger_is_found(self, planted, found):
        assert found in section_problems(planted)


class TestByBehaviour:
    def test_after_a_fail_nothing_asks_or_starts_anything(self, web, monkeypatch):
        from modules import invalidation
        from modules.fixit import proposers
        calls = []
        monkeypatch.setattr(proposers, "mercury", lambda *a, **k: calls.append(a) or {})
        iid = plant()
        attempt(web)
        for _ in range(3):
            r, html = page(web, iid)
            assert r.status_code == 200 and 'data-state="stopped"' in section_of(html)
        # The run's end announced as its job announces it, heard by an open page (which draws
        # the page again, as below); the readers it would wake are not this test's.
        heard = []
        monkeypatch.setattr(invalidation, "_emitter", lambda event, msg: heard.append(msg))
        monkeypatch.setattr("modules.reader_wakes.wake", lambda keys, by: None)
        invalidation.announce(["privileged", "drift"], by="telemetry re-subscribe")
        assert heard and heard[0]["keys"] == ["privileged", "drift"]
        r, html = page(web, iid)
        assert 'data-state="stopped"' in section_of(html)
        assert calls == [], "a page drawn or an announcement never re-plans"
        assert web.started == {"ask": 0, "hold": 0, "job": 0, "relay": 0}

    def test_the_parsed_population_is_real_python(self):
        # The section's module parses, and no definition there names a proposer (Retry with
        # more information, the one that did, is gone: R1, 2026-11-14); a planted one is seen.
        with open(os.path.join(ROOT, "modules", "fixit", "section.py"), encoding="utf-8") as fh:
            text = fh.read()

        def named(source):
            return {n.name for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
                    and "proposers" in ast.unparse(n)}
        assert len(ast.parse(text).body) > 30
        assert named(text) == set()
        assert named(text + "\n\ndef planted(i):\n    from modules.fixit import proposers\n"
                     "    return proposers.mercury(i, {})\n") == {"planted"}
