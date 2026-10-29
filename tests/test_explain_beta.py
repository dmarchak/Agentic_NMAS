"""Explain's "Advisory (beta)" label (PHASE8_PLAN 15.12, Explain's ship ruling of 2026-10-29,
condition (b); board AlertsExplain revised 2026-10-29): modules/ai/explain.py (`MEASURED`,
`beta`), templates/v2/_explain_beta.html and every template drawing an Explain answer or its
control.

**Why:** the stop rule was reached (v4 with the fact sheet and the guard: 17 of 21 recorded cases
reliable, 81%, under the 90% bar; confidently wrong 0 of 210 runs as shown), and the operator
ruled that Explain ships as advisory, its screens showing the measured reliability and "a person
should confirm". The defect class: a model's reliability below the bar presented as an answer
to rely on, or a figure on a screen that no longer matches what was measured.

**What is held here:**
- every Explain answer drawn (an answer, no fault found, no fault found with Mercury's needs a
  person) opens with the whole label; a refusal draws none on itself, and its control draws the
  whole label;
- every Explain control carries the label: the chip alone with an answer drawn under it, the
  whole label without one, on an alert's card and on a past alert's row with no pack;
- the figure comes from the one record: a record changed is a page changed, a pin the record is
  not of says Not measured, and no template holds a figure of its own;
- every field of the record is drawn (on the chip's hover);
- every template that includes the answer partial or draws Explain's control calls the label
  (a scan of the Jinja AST, with a planted template that lacks it).
"""
import os
import re
from html import unescape

import pytest

from modules.ai import explain
from tests.test_ai_explain import _answer, world  # noqa: F401 (the fixture)
from tests.test_alert_history_packs import history  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)
from tests.test_explain_needs_human_guard import _no_fault

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "templates", "v2")
BETA = "v2/_explain_beta.html"
ANSWER = "v2/_explain.html"

#: The record's figure in the label's words, as the ruling reads it (2026-10-29).
FIGURE = "81% of recorded cases reliable in measurement (2026-10-29, 21 cases, 10 runs)"


def _press(world, answer):
    world.answer = answer
    r = world.lab["client"].post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
                                 headers={"HX-Request": "true"})
    assert r.status_code == 200
    return unescape(r.get_data(as_text=True))


def _parts(html):
    """The block's control (its form) and its answer (the `.explain` div), apart."""
    form = re.search(r'<form class="explain-ask".*?</form>', html, re.S).group(0)
    answer = html[html.index('<div class="explain"'):]
    return form, answer


def _labels(html):
    return re.findall(r'<p class="explain-beta" data-explain-beta="(\w+)">(.*?)</p>', html, re.S)


def _whole(label):
    state, body = label
    assert state == "measured", label
    assert "Advisory (beta)" in body and FIGURE + "." in body, body
    assert "A person should confirm." in body, body
    link = re.search(r'<a class="info-link info-words" href="([^"]+)"[^>]*>([^<]+)</a>', body)
    assert link and link.groups() == ("/v2/help/alert-evidence#beta", "How was this measured?")


def _chip_only(form):
    assert re.search(r'<span class="explain-beta-chip" data-explain-beta="measured">'
                     r'<span class="badge badge-info" title="Explain is advisory while in beta'
                     r'[^"]*">Advisory \(beta\)</span></span>', form), form
    assert not _labels(form), "the answer under it carries the whole label"


# ── on every answer drawn, and beside its control ─────────────────────────────────────────

@pytest.mark.parametrize("kind", ["answer", "no_fault_found", "no_fault_found_set_by_mercury"])
def test_every_answer_opens_with_the_label_and_its_control_the_chip(world, kind):  # noqa: F811
    answer = {"answer": lambda p: _answer(p),
              "no_fault_found": lambda p: _no_fault(p, needs_human=True),
              "no_fault_found_set_by_mercury": lambda p: _no_fault(p)}[kind](world.pack)
    html = _press(world, answer)
    form, drawn = _parts(html)
    labels = _labels(drawn)
    assert len(labels) == 1, labels
    _whole(labels[0])
    # First in the answer, before its rationale.
    assert drawn.index('class="explain-beta"') < drawn.index('class="explain-why"')
    if kind == "no_fault_found_set_by_mercury":
        assert drawn.index('class="explain-beta"') < drawn.index("explain-mercury-needs-human")
    _chip_only(form)


def test_a_refusal_draws_no_label_and_its_control_the_whole_label(world):  # noqa: F811
    html = _press(world, _answer(world.pack, hypotheses=[{
        "claim": "A cause.", "evidence_refs": ["logs:999"], "confirm_with": "show version"}]))
    form, drawn = _parts(html)
    assert "Not explained: couldn't analyse" in drawn
    assert not _labels(drawn) and "explain-beta-chip" not in html
    labels = _labels(form)
    assert len(labels) == 1
    _whole(labels[0])


def test_a_card_opened_with_no_answer_draws_the_whole_label_beside_explain(world):  # noqa: F811
    r = world.lab["client"].get(f"/v2/monitoring/alerts/pack/{world.pack['id']}")
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200 and 'data-op="alert-evidence"' in html
    form, drawn = _parts(html)
    labels = _labels(form)
    assert len(labels) == 1
    _whole(labels[0])
    assert not _labels(drawn)


def test_a_past_alert_with_no_pack_draws_the_whole_label_beside_its_explain(history):  # noqa: F811
    html = unescape(history["client"].get("/v2/monitoring/alerts/history?range=all&show=all")
                    .get_data(as_text=True))
    rows = re.findall(r'<form class="explain-ask".*?</form>', html, re.S)
    assert rows and all("Build evidence" in f and "build it first" in f for f in rows)
    for f in rows:
        labels = _labels(f)
        assert len(labels) == 1, f
        _whole(labels[0])


# ── the figure is the record's ────────────────────────────────────────────────────────────

def test_the_page_follows_the_record(world, monkeypatch):  # noqa: F811
    """The control: the record changed, the page's figure changes with it, and the ruling's
    figure is gone."""
    monkeypatch.setattr(explain, "MEASURED", dict(explain.MEASURED, at="2026-11-02", cases=24,
                                                   reliable=22, runs=5, round="msgbatch_test"))
    html = _press(world, _answer(world.pack))
    body = _labels(_parts(html)[1])[0][1]
    assert "92% of recorded cases reliable in measurement (2026-11-02, 24 cases, 5 runs)." in body
    assert FIGURE not in html and "81%" not in html
    assert "round msgbatch_test" in html


@pytest.mark.parametrize("moved", [{"prompt": ("explain", 3)}, {"model": "claude-haiku-5-5"}])
def test_a_pin_the_record_is_not_of_says_not_measured(world, monkeypatch, moved):  # noqa: F811
    monkeypatch.setattr(explain, "MEASURED", dict(explain.MEASURED, **moved))
    html = _press(world, _answer(world.pack))
    state, body = _labels(_parts(html)[1])[0]
    assert state == "not_measured"
    got = explain.beta()
    assert got["percent"] is None
    assert body.count("Not measured: Explain now asks explain v4 on ") == 1, body
    assert "the measurement of 2026-10-29 was of explain v" in body
    assert "%" not in body and "A person should confirm." in body
    assert 'data-explain-beta="not_measured"' in _parts(html)[0], "the chip says so too"


def test_the_record_is_the_rulings_and_of_the_pin_now():
    """The record as the round of 2026-10-29 measured it (C2117, C2141), and of what is pinned:
    a pin moved without a new record is drawn Not measured (above), never this figure."""
    from modules.ai import profiles
    m = explain.MEASURED
    assert (m["reliable"], m["cases"], m["runs"], m["passed_runs"]) == (17, 21, 10, 194)
    assert (m["wrong_shown"], m["wrong_raw"], m["blind"]) == (0, 10, None)
    assert tuple(m["prompt"]) == tuple(explain.PROMPT)
    assert m["model"] == profiles.task("explain")["model"]
    assert explain.beta()["state"] == "measured" and explain.beta()["words"] == FIGURE


def figures_typed(texts: dict) -> list:
    """Templates holding a reliability figure of their own: a percentage beside "reliable", or
    "N of M cases", in the text a template draws (comments removed)."""
    out = []
    for name, text in texts.items():
        drawn = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
        if re.search(r"\d+\s*%[^<{]{0,40}reliab|\d+ of \d+ (?:recorded )?cases", drawn):
            out.append(name)
    return out


def test_no_template_types_a_figure_of_its_own():
    texts = {f: open(os.path.join(V2, f), encoding="utf-8").read()
             for f in sorted(os.listdir(V2)) if f.endswith(".html")}
    assert len(texts) >= 100
    assert figures_typed(texts) == []
    planted = {"_planted.html": "<p>{{ badge('Advisory (beta)') }} 81% of recorded cases "
                                "reliable</p>", "_planted2.html": "<p>17 of 21 cases</p>"}
    assert figures_typed(planted) == ["_planted.html", "_planted2.html"]


def test_every_field_of_the_record_is_drawn_on_the_chips_hover(world):  # noqa: F811
    m = explain.MEASURED
    total = m["cases"] * m["runs"]
    drawn = {"at": f"Measured {m['at']}", "prompt": f"{m['prompt'][0]} v{m['prompt'][1]} on ",
             "model": f"({m['model']})", "fact_sheet": "Mercury's fact sheet",
             "guard": "its needs-a-person guard", "round": f"round {m['round']}",
             "commit": f"on {m['commit']}", "cases": f"{m['cases']} recorded alerts",
             "reliable": f"{m['reliable']} of {m['cases']} cases reliable",
             "runs": f"{m['runs']} runs each",
             "passed_runs": f"{m['passed_runs']} of {total} runs passed",
             "wrong_shown": f"confidently wrong {m['wrong_shown']} of {total} runs as shown",
             "wrong_raw": f"{m['wrong_raw']} as the model answered",
             "blind": "The blind held-out set is not yet measured"}
    assert set(drawn) == set(m), sorted(set(drawn) ^ set(m))
    html = _press(world, _answer(world.pack))
    hover = re.search(r'<span class="badge badge-info" title="([^"]+)">Advisory \(beta\)', html)
    assert hover
    for key, words in drawn.items():
        assert words in hover.group(1), (key, words, hover.group(1))


# ── every template drawing an answer or the control calls the label ───────────────────────

def _ast(source):
    import app as A
    return A.app.jinja_env.parse(source)


def explain_drawers(templates: dict) -> dict:
    """The templates that draw an Explain answer (include the answer partial, or are it) or
    Explain's control (`ai_control('explain')`), by the Jinja AST, never by text: {template:
    (why, whether it calls the label or the chip of `_explain_beta.html`)}."""
    from jinja2 import nodes

    out = {}
    for name, source in templates.items():
        tree = _ast(source)
        includes = {n.template.value for n in tree.find_all(nodes.Include)
                    if isinstance(n.template, nodes.Const)}
        control = any(isinstance(n.node, nodes.Name) and n.node.name == "ai_control"
                      and n.args and isinstance(n.args[0], nodes.Const)
                      and n.args[0].value == "explain" for n in tree.find_all(nodes.Call))
        answer = ANSWER in includes or name == ANSWER
        if not (answer or control):
            continue
        aliases = {n.target for n in tree.find_all(nodes.Import)
                   if isinstance(n.template, nodes.Const) and n.template.value == BETA}
        called = any(isinstance(n.node, nodes.Getattr) and isinstance(n.node.node, nodes.Name)
                     and n.node.node.name in aliases and n.node.attr in ("label", "chip")
                     for n in tree.find_all(nodes.Call))
        out[name] = ("draws an Explain answer" if answer else "draws Explain's control", called)
    return out


def label_missing(templates: dict) -> list:
    """The Explain drawers that call no label: (template, why)."""
    return [(n, why) for n, (why, called) in explain_drawers(templates).items() if not called]


def _v2_templates():
    return {f"v2/{f}": open(os.path.join(V2, f), encoding="utf-8").read()
            for f in sorted(os.listdir(V2)) if f.endswith(".html")}


def test_every_template_drawing_an_answer_or_the_control_calls_the_label():
    texts = _v2_templates()
    population = list(explain_drawers(texts))
    # The floor: the answer, its block (the control), and the past alert's row.
    assert {"v2/_explain.html", "v2/_explain_block.html", "v2/_alert_history.html"} <= \
        set(population), population
    assert label_missing(texts) == []
    # Every route that renders an Explain partial renders one of the population.
    routes = os.path.join(ROOT, "routes")
    rendered = set()
    for f in sorted(os.listdir(routes)):
        if f.endswith(".py"):
            with open(os.path.join(routes, f), encoding="utf-8") as fh:
                rendered |= set(re.findall(r'render_template\(\s*"(v2/_explain[^"]*)"', fh.read()))
    assert rendered and rendered <= set(population), rendered


def test_a_planted_template_without_the_label_is_found():
    planted = {
        "v2/_planted_answer.html": '{% include "v2/_explain.html" %}',
        "v2/_planted_control.html": "{%- set aic = ai_control('explain') %}<button>x</button>",
        # Imported but never called is still missing.
        "v2/_planted_import.html": '{%- import "v2/_explain_beta.html" as beta -%}'
                                   '{% include "v2/_explain.html" %}',
        # In a comment only: the AST has no call.
        "v2/_planted_comment.html": "{# beta.label() #}{% include \"v2/_explain.html\" %}",
        "v2/_drawn.html": '{%- import "v2/_explain_beta.html" as b -%}{{ b.label() }}'
                          '{% include "v2/_explain.html" %}',
        "v2/_unrelated.html": "{%- set aic = ai_control('ask_in_words') %}",
    }
    assert label_missing(planted) == [
        ("v2/_planted_answer.html", "draws an Explain answer"),
        ("v2/_planted_control.html", "draws Explain's control"),
        ("v2/_planted_import.html", "draws an Explain answer"),
        ("v2/_planted_comment.html", "draws an Explain answer")]
