"""Stage 7 acceptance criterion 13 (NSOT_STAGE7_PLAN.md; NSOT_AUTHORIZATION.md section 7):
every gated control's state is read from `may`, and a refused control renders its reason.

A GATED control sends a mutating request to an endpoint whose `route_gates` kind is not
`not_device`: a <button> carrying hx-post/put/patch/delete to one, or a submit button inside
a <form> that posts (hx-post or method="post") to one. Each carries ``{{ gate('<kind>') }}``
in its own tag, with its route's own kind: `preview_confirm.control_gate`, which asks
`identity.may` (the function the gate itself calls) and draws the control disabled with its
reason when refused. The scan here is its own parse of the templates, independent of the
conversion that added the calls.
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPEN = re.compile(r"<(button|form)\b", re.I)
URL = re.compile(r"url_for\(\s*['\"]([\w.]+)['\"]")
MUT = re.compile(r"\bhx-(post|put|patch|delete)\s*=", re.I)
POSTFORM = re.compile(r"\bmethod\s*=\s*\"post\"", re.I)
#: `gate('<kind>')`, or an AI control's `ai.attrs(<control>, '<kind>')`, which renders exactly
#: `gate(kind)` while its control can answer and disables it for everyone while it cannot
#: (PHASE8_PLAN 15.13; pinned by `test_an_ai_control_s_attrs_are_its_gate_while_it_can_answer`).
GATE = re.compile(r"\{\{\s*(?:gate\(|ai\.attrs\(\s*\w+\s*,)\s*'(\w+)'\s*\)\s*\}\}")


def _tag_end(text, i):
    j, quote = i + 1, None
    while j < len(text):
        if quote is None and text[j:j + 2] in ("{{", "{%", "{#"):
            j = text.index({"{{": "}}", "{%": "%}", "{#": "#}"}[text[j:j + 2]], j + 2) + 2
            continue
        c = text[j]
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c == ">":
            return j
        j += 1
    raise AssertionError("an unclosed tag")


def gated_controls():
    """``[(template, endpoint, kind, tag)]``: every gated control in the v2 templates."""
    from modules import route_gates as G
    from tests.source_index import tracked

    out = []
    for path in tracked("templates/v2", suffix=".html"):
        text = open(path, encoding="utf-8").read()
        rel = os.path.relpath(path, ROOT)
        for m in OPEN.finditer(text):
            end = _tag_end(text, m.start())
            tag = text[m.start():end + 1]
            ep = URL.search(tag)
            gate = G.GATES.get(ep.group(1)) if ep else None
            kind = getattr(gate, "kind", None)
            if m.group(1).lower() == "button" and MUT.search(tag):
                if kind and kind != "not_device":
                    out.append((rel, ep.group(1), kind, tag))
            elif m.group(1).lower() == "form" and (MUT.search(tag) or POSTFORM.search(tag)):
                if not kind or kind == "not_device":
                    continue
                close = text.lower().find("</form>", end)
                for b in re.finditer(r"<(button|input)\b", text[end + 1:close], re.I):
                    s = end + 1 + b.start()
                    btag = text[s:_tag_end(text, s) + 1]
                    if b.group(1).lower() == "input" and 'type="submit"' not in btag:
                        continue
                    if re.search(r'type\s*=\s*"(button|reset)"', btag):
                        continue
                    if MUT.search(btag):
                        continue                    # its own request: judged as a button
                    out.append((rel, ep.group(1), kind, btag))
    return out


def test_every_gated_control_consults_may_with_its_routes_kind():
    found = gated_controls()
    assert len(found) >= 80, len(found)                # 82 when this was written
    bad = []
    for rel, ep, kind, tag in found:
        got = GATE.findall(tag)
        if got != [kind]:
            bad.append(f"{rel}: a control posting to {ep} ({kind}) carries "
                       f"{got or 'no gate()'}: {tag[:100]}")
    assert not bad, "\n".join(bad)


def test_a_refused_viewer_sees_the_control_disabled_with_its_reason(monkeypatch):
    import app as A
    from modules import identity
    monkeypatch.setattr(identity, "may", lambda ident, kind, operation="": (
        False, "requires a person"))
    with A.app.test_request_context("/"):
        html = A.app.jinja_env.from_string("<button{{ gate('confirm') }}>Go</button>").render()
    assert "disabled" in html and 'aria-disabled="true"' in html
    assert 'data-refused="Not available to you: requires a person"' in html


def test_a_person_sees_it_unchanged(monkeypatch):
    import app as A
    from modules import identity
    monkeypatch.setattr(identity, "may", lambda ident, kind, operation="": (True, ""))
    with A.app.test_request_context("/"):
        html = A.app.jinja_env.from_string("<button{{ gate('confirm') }}>Go</button>").render()
    assert html == "<button>Go</button>"


@pytest.mark.parametrize("allowed", [True, False], ids=["a-person", "refused"])
def test_an_ai_control_s_attrs_are_its_gate_while_it_can_answer(monkeypatch, allowed):
    """The scan above reads `ai.attrs(c, kind)` as `gate(kind)`: so, while the control can
    answer, the two render the same bytes, for a person and for a refused viewer alike; and
    while it cannot, the control is disabled whoever looks."""
    import app as A
    from modules import identity
    monkeypatch.setattr(identity, "may", lambda ident, kind, operation="": (
        (True, "") if allowed else (False, "requires a person")))
    env = A.app.jinja_env
    with A.app.test_request_context("/"):
        gate = env.from_string("<button{{ gate('configure') }}>Go</button>").render()
        ai = env.from_string("{% import 'v2/_ai.html' as ai %}"
                             "<button{{ ai.attrs(c, 'configure') }}>Go</button>").render(
            c={"ready": True})
        off = env.from_string("{% import 'v2/_ai.html' as ai %}"
                              "<button{{ ai.attrs(c, 'configure') }}>Go</button>").render(
            c={"ready": False, "kind": "ai_off"})
    assert ai == gate
    assert " disabled" in off and 'data-ai-off="ai_off"' in off


def test_the_reason_is_drawn_not_only_on_hover():
    css = open(os.path.join(ROOT, "static", "css", "nmas-v2.css"), encoding="utf-8").read()
    assert re.search(r"button\[data-refused\]::after\s*\{[^}]*attr\(data-refused\)", css)


def test_no_client_script_decides_a_control_by_role():
    """The server's answer only: no v2 script hides or enables a control by a role."""
    from tests.source_index import tracked
    pattern = re.compile(r"\broles?\s*(===|==|\.includes|\[)|isAdmin|hasRole")
    hits = [os.path.relpath(p, ROOT) for p in tracked("static/js", suffix=".js")
            if os.path.basename(p).startswith("nmas_")
            and pattern.search(open(p, encoding="utf-8").read())]
    assert hits == [], hits


@pytest.mark.parametrize("kind", ["confirm", "approve", "configure", "reveal"])
def test_the_gate_answers_as_the_gate_does(monkeypatch, kind):
    """The control asks `identity.may` with the kind it carries: the function the route's
    gate calls, so the drawn state cannot disagree with the request."""
    import app as A
    from modules import identity
    asked = []
    monkeypatch.setattr(identity, "may", lambda ident, k, operation="": (
        asked.append(k) or (False, "x")))
    with A.app.test_request_context("/"):
        A.app.jinja_env.from_string("{{ gate('%s') }}{{ gate('%s') }}" % (kind, kind)).render()
    assert asked == [kind]                               # once per request and kind
