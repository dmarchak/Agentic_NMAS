"""C3715 (the operator, 2026-11-14; the live demo's on-camera list): a record shows a person's
display name on screen, never their email. The record keeps the verified actor; a v2 template
draws it through the `people` filter (routes/v2.py: each email-shaped token as that person's
`identity.display_name`).

The population: every ``{{ … }}`` in a v2 template whose expression ends in a field that names
a person (`PERSON_FIELDS`: ``by``, ``who``, ``actor``, ``person``, ``setter``), found by
parsing the expression, not by a substring of the file. Each pipes through ``people``, or is
on `NOT_A_PERSON` with why (a field of that name that holds no person: a DHCP identifier's
kind, a group-by, a layer). The run stepper's words, which name the person an apply ran as
("as <person>, who approved it"), are held too.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "templates", "v2")

PERSON_FIELDS = ("by", "who", "actor", "person", "setter")
EXPR = re.compile(r"\{\{-?\s*(.+?)\s*-?\}\}", re.S)
#: ``(template, expression)``: a field named as a person's that holds none, and why.
NOT_A_PERSON = {
    ("_dhcp_view.html", "by"): "the DHCP identifier's kind (MAC, DUID), a macro parameter",
    ("_dhcp_view.html", "l.by"): "the lease's identifier kind (MAC, DUID)",
    ("_dhcp_view.html", "r.by"): "the reservation's identifier kind (MAC, DUID)",
    ("_history_ask_logs.html", "s.by"): "the query's group-by labels, a form value sent back",
    ("_intent_layers.html", "by"): "the layer that overrides the value",
    ("_fleet_plan.html", "u.by"): "the layer that holds the device's value unchanged",
    ("_intent_words.html", "r.by"): "how each phrase was resolved (the reads it took)",
    ("_explain.html", "w.by"): "who named it: 'model' or 'mercury', in a data attribute",
    ("_oob_onboard.html", "who"): "the device's hostname (`set who = c.hostname`)",
    ("_console_ztp.html", "who"): "the device's hostname (`set who = c.hostname`)",
    ("_timeline.html", "e.who"): ("under 'The identity as recorded', closed (the operator, "
                                  "2026-11-12, C3175: an email appears only there)"),
}


def _raw(expr: str) -> str:
    """The expression's subject when it is a bare person field (``r.held.by``), else ""."""
    head = expr.split("|")[0].strip()
    if not re.fullmatch(r"[A-Za-z_][\w.]*", head):
        return ""
    last = head.rsplit(".", 1)[-1]
    return head if last in PERSON_FIELDS else ""


def raw_actors(texts: dict) -> list:
    """``[(template, expression)]``: each person field drawn without ``people``."""
    out = []
    for name, text in texts.items():
        for m in EXPR.finditer(text):
            expr = m.group(1)
            subject = _raw(expr)
            filters = [f.strip().split("(")[0] for f in expr.split("|")[1:]]
            if subject and "people" not in filters:
                out.append((name, subject))
    return out


def _templates() -> dict:
    return {f: open(os.path.join(V2, f), encoding="utf-8").read()
            for f in sorted(os.listdir(V2)) if f.endswith(".html")}


def test_every_person_field_is_drawn_by_name_or_says_why():
    texts = _templates()
    found = raw_actors(texts)
    population = [(n, _raw(m.group(1))) for n, t in texts.items() for m in EXPR.finditer(t)
                  if _raw(m.group(1))]
    assert len(population) >= 30, len(population)
    left = sorted(set(found) - set(NOT_A_PERSON))
    assert left == [], f"drawn raw, an email would show: {left}"
    stale = sorted(set(NOT_A_PERSON) - set(found))
    assert stale == [], f"declared, and no longer drawn raw: {stale}"


def test_a_planted_raw_actor_is_found():
    planted = {"x.html": "<p>{{ r.held.by }} and {{ e.who | people }} and {{ h.by|upper }}</p>"}
    assert raw_actors(planted) == [("x.html", "r.held.by"), ("x.html", "h.by")]


def test_the_steppers_words_name_people_by_name():
    text = _templates()["_run_stepper.html"]
    assert text.count("ln.words | people") == 3, "a run's step lines name who they ran as"


def test_the_people_filter_draws_a_display_name_never_the_email():
    import app as nmas_app
    from flask import render_template_string

    with nmas_app.app.test_request_context("/v2/"):
        html = render_template_string("{{ w | people }}",
                                      w="applied as dana.lee@example.com, who approved it")
    assert "dana.lee@example.com" not in html and "dana.lee" in html
