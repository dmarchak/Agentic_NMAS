"""No path retries without a person (the operator's test 1, 2026-11-11: "FAIL: STOP. Never
retry on its own"), for everything but the AI gateway, which comes with the AI's own call (the
fix-it plan's S4; board recurring-fixes v2, guard G3: "there is no screen for this, because
there is no control for it").

- **By parsing:** every definition in the program that reaches a proposer (`modules/fixit/
  proposers.py`, Mercury's own, and the AI's, `modules/ai/fixit_troubleshoot.troubleshoot`,
  S5) is exactly the section's `retry`, the route that calls it and the `troubleshoot` route,
  and each route is served by POST alone and declared in `modules/route_gates.py` as a
  verified person's configure gate (the gateway's own entry points: tests/test_ai_entry_points
  .py). The set is compared whole,
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


def reaching(planted: str = "") -> set:
    """The program's definitions outside the proposers module that reach a proposer; with
    *planted*, a module's text, as if routes/planted_v2.py held it."""
    got = FI.program()
    refs = dict(got["refs"])
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
        assert ("routes.fixit_v2", "retry") in refs and ("modules.fixit.section", "retry") in refs

    def test_every_caller_of_a_proposer_is_the_retry_route(self):
        assert reaching() == {("modules.fixit.section", "retry"), ("routes.fixit_v2", "retry"),
                              ("routes.fixit_v2", "troubleshoot")}

    @pytest.mark.parametrize("endpoint", ["fixit_v2.retry", "fixit_v2.troubleshoot"])
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
         "    return section.retry('Default', {}, actor='', actor_verified='', person=False)\n"),
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
        found = reaching(planted)
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
        # The section's module parses, and its retry is the only definition that names a
        # proposer there.
        with open(os.path.join(ROOT, "modules", "fixit", "section.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        named = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)
                 and "proposers" in ast.unparse(n)}
        assert named == {"retry"}
