"""Explain's answer card first, Monitoring › Alerts counted by kind, citations as chips, and
the alert states (board AlertsExplain revised 2026-10-29, "the answer card first"; the
operator's order of 2026-10-29, items 3 and 4a: C2172 item 3 and C2173's first step).

**Why:** a person reading an alert asks "what most likely caused this, and do I need to look?",
and the evidence that answers "why does it say so?" belongs one level down. Before this the
answer was a list under the control and the pack's sections were drawn open, so a page of
evidence pushed the answer off the screen; past firings were drawn red beside what fires now,
and "resolved" said something was fixed when only the condition had stopped. The defect class:
a wrong thing that looks right (a cleared alert read as a live one, a stopped condition read
as a fix), and an answer buried under its evidence.

**What is held here:**
- the card's order and labels for each answer kind (an answer with three hypotheses, one, no
  fault found, Mercury's needs a person, a refusal, hosted AI off), and who a hypothesis names
  drawn as the model's or as Mercury's;
- Other possibilities collapsed; the pack's sections collapsed, each with its count;
- the firing alerts counted by kind, each count a filter, at 900 alerts in three kinds;
- every citation chip drawn names a piece on the same page (a scan over rendered cards, with a
  planted chip it finds), and the script that opens and highlights it (duktape);
- nothing that has stopped firing is red (a scan over the states drawn and their classes, with
  a planted red past firing it finds); and no alert's end says "resolved";
- Explain again busy on itself.
"""
import copy
import json
import os
import re
from html import unescape

import pytest

from modules import evidence_pack as EP
from tests.test_ai_explain import _answer, _refs, world  # noqa: F401 (the fixture)
from tests.test_alert_history_packs import history  # noqa: F401 (the fixture)
from tests.test_device_v2 import _store, lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import V4, _alerts, _with_packs, pack_lab  # noqa: F401
from tests.test_explain_needs_human_guard import _no_fault

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _press(world, answer, again=False):  # noqa: F811
    world.answer = answer
    r = world.lab["client"].post(f"/v2/monitoring/alerts/pack/{world.pack['id']}/explain",
                                 data={"again": "1"} if again else {},
                                 headers={"HX-Request": "true"})
    assert r.status_code == 200, r.status_code
    return unescape(r.get_data(as_text=True))


def _pack_page(world):  # noqa: F811
    r = world.lab["client"].get(f"/v2/monitoring/alerts/pack/{world.pack['id']}",
                                headers={"HX-Request": "true"})
    assert r.status_code == 200, r.status_code
    return unescape(r.get_data(as_text=True))


def _three(pack):
    """An answer with three hypotheses, most likely first, each citing what the pack holds."""
    logs = _refs(pack, "logs")
    return _answer(pack, needs_human=True, hypotheses=[
        {"claim": "A configuration change on r1 preceded the errors.",
         "evidence_refs": [logs[0], "alert"], "confirm_with": "show interfaces | include errors"},
        {"claim": "The interface's cabling is failing.", "evidence_refs": [logs[1]],
         "confirm_with": "show interfaces"},
        {"claim": "A scrape artefact, not the device.", "evidence_refs": ["alert"],
         "confirm_with": "show version"}])


def _order(html, marks):
    """Each mark's first index in *html*, asserting each is found and they come in order."""
    at = []
    for m in marks:
        i = html.find(m)
        assert i >= 0, (m, html[:3000])
        at.append(i)
    assert at == sorted(at), list(zip(marks, at))


# ── the card's order and labels, for each answer kind ─────────────────────────────────────

def test_an_answer_with_three_hypotheses_is_most_likely_then_the_others_collapsed(world):  # noqa: F811
    html = _press(world, _three(world.pack))
    card = re.search(r'<article class="answer-card".*?</article>', html, re.S).group(0)
    _order(card, ['<header class="answer-head">', "Explain's answer</h3>", "Advisory (beta)",
                  ">Most likely cause<", "A configuration change on r1 preceded the errors.",
                  '<span class="faint">Why:</span>', "Other possibilities · 2",
                  "The interface's cabling is failing.", "A scrape artefact, not the device.",
                  'data-part="needs-a-person"', "The evidence does not settle the cause.",
                  "Was this right?", "Explain again"])
    # The header first, the label in it; the ranks as the answer ordered them.
    assert card.index("Advisory (beta)") < card.index("</header>") < card.index("Most likely")
    assert re.findall(r'data-rank="(\d)"', card) == ["1", "2", "3"]
    likely = re.search(r'<section class="answer-likely" data-part="most-likely".*?</section>',
                       card, re.S).group(0)
    assert "A configuration change on r1" in likely and "cabling" not in likely
    # Other possibilities collapsed: a disclosure with no `open`, holding the other two.
    others = re.search(r'<details class="answer-others"[^>]*>', card).group(0)
    assert " open" not in others, others
    assert card.index("The interface's cabling") > card.index("<summary>Other possibilities")


def test_one_hypothesis_draws_no_other_possibilities(world):  # noqa: F811
    html = _press(world, _answer(world.pack))
    assert ">Most likely cause<" in html and "A configuration change on r1" in html
    assert "Other possibilities" not in html and "answer-others" not in html
    assert 'data-part="needs-a-person"' not in html, "the answer did not ask for a person"


def test_no_fault_found_draws_what_was_checked_in_the_place_of_a_cause(world):  # noqa: F811
    html = _press(world, _no_fault(world.pack, needs_human=True))
    card = re.search(r'<article class="answer-card".*?</article>', html, re.S).group(0)
    _order(card, ["Advisory (beta)", ">No fault found<", "r1's log lines show nothing wrong.",
                  '<span class="faint">Checked</span>', 'class="pack-ref cite-chip"',
                  'data-part="needs-a-person"', "Something in the pack could not be read.",
                  "Was this right?", "Explain again"])
    assert "Most likely cause" not in card and "Other possibilities" not in card


def test_a_needs_a_person_mercury_set_is_drawn_as_mercury_s(world):  # noqa: F811
    html = _press(world, _no_fault(world.pack))
    card = re.search(r'<article class="answer-card".*?</article>', html, re.S).group(0)
    _order(card, ["Advisory (beta)", ">No fault found<", 'data-part="needs-a-person"',
                  "needs a person", "set by Mercury", "The model found no fault",
                  "Was this right?", "Explain again"])
    assert "Something in the pack could not be read." not in card


def test_a_refusal_and_ai_off_draw_no_card_and_the_primary_explain(world):  # noqa: F811
    html = _press(world, _answer(world.pack, hypotheses=[
        {"claim": "A cause.", "evidence_refs": ["logs:999"], "confirm_with": "show version"}]))
    assert "Not explained: couldn't analyse" in html and "answer-card" not in html
    form = re.search(r'<form class="explain-ask"[^>]*>.*?</form>', html, re.S).group(0)
    assert "btn-outline" not in form and 'class="explain-beta"' in form
    world.settings.pop("ai_hosted")
    page = _pack_page(world)
    assert "answer-card" not in page
    form = re.search(r'<form class="explain-ask"[^>]*>.*?</form>', page, re.S).group(0)
    assert 'disabled aria-disabled="true"' in form and "hosted AI is off" in form


def _render(name, **ctx):
    from flask import render_template

    from app import app
    with app.test_request_context("/"):
        return unescape(render_template(name, **ctx))


def _golden(pack):
    return next(p for s in pack["sections"] if s["name"] == "history"
                for p in s["pieces"] if p["kind"] == "golden")


def test_who_a_hypothesis_names_is_the_model_s_or_mercury_s(world):  # noqa: F811
    """`who` as Explain carries it (C2172 item 1; `who.who_of`, merged with WHO 2026-10-29):
    the model's words drawn plainly when the claim names the actor, Mercury's from the record
    the hypothesis cites under "who, added by Mercury" when it does not, each with the piece as
    a chip; a hypothesis citing no change, and an answer kept before who existed, draw none."""
    piece = _golden(world.pack)
    ref, pid = piece["ref"], world.pack["id"]
    html = _press(world, _answer(world.pack, needs_human=True, hypotheses=[
        {"claim": "The golden recorded before the errors changed r1.",
         "evidence_refs": [ref, "alert"], "confirm_with": "show interfaces | include errors"},
        {"claim": f"{piece['who']} recorded the golden before the errors.",
         "evidence_refs": [ref], "confirm_with": "show archive log config all"},
        {"claim": "A scrape artefact, not the device.", "evidence_refs": ["alert"],
         "confirm_with": "show version"}]))
    chip = (rf'<span class="faint">from</span> <a class="pack-ref cite-chip" '
            rf'href="#{re.escape(pid)}-{re.escape(ref)}"')
    likely = re.search(r'data-part="most-likely".*?</section>', html, re.S).group(0)
    assert re.search(r'data-who-by="mercury" data-actor="' + re.escape(piece["who"])
                     + r'" data-refs="' + re.escape(ref) + r'"[^>]*><span class="faint">Who:'
                     r'</span> ' + re.escape(piece["who"]) + r' \([^)<]+\) <span class="badge '
                     r'badge-neutral"[^>]*>who, added by Mercury</span> ' + chip, likely), likely
    others = re.search(r'<details class="answer-others".*?</details>', html, re.S).group(0)
    assert re.search(r'data-who-by="model"[^>]*><span class="faint">Who:</span> '
                     + re.escape(piece["who"]) + r' \([^)<]+\) ' + chip, others), others
    assert "added by Mercury" not in others
    assert html.count("Who:</span>") == 2, "the third cites no change and carries none"
    # An answer kept before who existed (no `who` on its hypotheses) draws none.
    from modules.ai import explain_answers
    x = explain_answers.as_drawn(explain_answers.kept(world.pack)["answer"])
    for h in x["answer"]["hypotheses"]:
        h.pop("who")
    plain = _render("v2/_explain.html", x=x, explain_model="m")
    assert "Who:" not in plain and "added by Mercury" not in plain


# ── the pack collapsed, each section with its count ───────────────────────────────────────

def test_every_section_is_collapsed_and_names_its_count(world):  # noqa: F811
    html = _pack_page(world)
    sections = re.findall(r'<details class="pack-section" data-ref="([^"]+)" id="[^"]+"'
                          r' data-keep="[^"]+"(\s+open)?>\s*<summary>(.*?)</summary>', html, re.S)
    assert len(sections) == len(world.pack["sections"]) >= 10, len(sections)
    for ref, opened, summary in sections:
        assert not opened, ref
        s = next(s for s in world.pack["sections"] if s["ref"] == ref)
        assert s["words"] in summary, (ref, summary)
        want = EP.section_count(s)
        if want:
            assert f'<span class="pack-count" data-count="{ref}">· {want}</span>' in summary
    logs = next(s for s in world.pack["sections"] if s["name"] == "logs")
    n = len(logs["pieces"])
    assert n > 1 and EP.section_count(logs) in (
        f"{n} lines", f"{n} of {logs.get('total')} lines")


@pytest.mark.parametrize("section, words", [
    ({"name": "logs", "state": "ok", "pieces": [{}] * 14}, "14 lines"),
    ({"name": "logs", "state": "ok", "pieces": [{}] * 14, "subset": True, "total": 40},
     "14 of 40 lines"),
    ({"name": "logs", "state": "ok", "pieces": [{}]}, "1 line"),
    ({"name": "logs", "state": "empty", "pieces": []}, "no lines"),
    ({"name": "logs", "state": "unreadable", "pieces": []}, ""),
    ({"name": "neighbours", "state": "ok", "pieces": [{"kind": "protocol"}]
      + [{"state": "up"}] * 4 + [{"state": "down"}]}, "1 down, 4 up; 1 protocol measured"),
    ({"name": "neighbours", "state": "ok", "pieces": [{"state": "not_seen"}]}, "1 not seen"),
    ({"name": "concurrent", "state": "ok", "pieces": [{"state": "firing"}, {"state": "resolved"},
                                                      {"state": "resolved"}]},
     "3 other alerts: 1 firing then, 2 cleared"),
    ({"name": "health", "state": "ok", "pieces": [{"device": "r1"}, {"device": "r1"},
                                                  {"device": "r2"}]}, "2 devices, 3 figures"),
    ({"name": "intent", "state": "ok", "pieces": [{"state": "differs"}]}, "differs"),
    ({"name": "observed", "state": "ok", "pieces": [{"state": "up"}, {"state": "down"}]},
     "1 down, 1 up"),
    ({"name": "sdn", "state": "ok", "pieces": [{}] * 3, "counts": {"flows": 2, "ports": 1}},
     "2 flows, 1 port"),
    ({"name": "something new", "state": "ok", "pieces": [{}, {}]}, "2 pieces"),
])
def test_a_section_s_count_in_words(section, words):
    assert EP.section_count(section) == words


# ── the firing alerts counted by kind, each a filter, at a large fleet's size ─────────────

KINDS = (("Device unreachable (SNMP)", 540), ("IP SLA probe failing", 270),
         ("NMAS heartbeat missing", 90))


def _fleet():
    """900 firing alerts in three kinds, from the capture's one instance: the per-device rule
    of the third named for its device ("NMAS heartbeat missing: d7"), as Grafana names it."""
    one = _alerts(V4)["instances"][0]
    out, n = [], 0
    for rule, count in KINDS:
        for _ in range(count):
            inst = copy.deepcopy(one)
            n += 1
            device = f"d{n}"
            inst["rule"] = f"{rule}: {device}" if rule.startswith("NMAS") else rule
            inst["device"] = device
            inst["labels"] = dict(inst["labels"], instance=f"192.0.2.{n % 250}", n=str(n))
            inst["active_at"] = f"2026-10-15T08:{n % 60:02d}:00Z"
            out.append(inst)
    return {"instances": out}


def test_the_kinds_are_counted_over_everything_firing_and_each_filters(pack_lab):  # noqa: F811
    _store("grafana-alerts", _fleet(), at="2026-10-15T08:24:00Z")
    c = pack_lab["client"]
    html = unescape(c.get("/v2/monitoring/alerts").get_data(as_text=True))
    assert "900 firing</strong>" in html
    nav = re.search(r'<nav class="alert-kinds".*?</nav>', html, re.S).group(0)
    chips = re.findall(r'<a class="kind-chip[^"]*" href="([^"]+)" data-kind="([^"]+)"[^>]*>'
                       r'<strong>(\d+)</strong> ([^<]+)</a>', nav)
    assert [(k, int(n)) for _h, k, n, _w in chips] == list(KINDS), chips
    assert all(k == w for _h, k, _n, w in chips)
    # Three groups, each drawing at most GROUP_SHOWN of its alerts (a large fleet: no long list).
    assert html.count('class="card pack-group"') == 3
    assert html.count('class="pack-card"') == sum(min(n, EP.GROUP_SHOWN) for _k, n in KINDS)
    # Each count filters to its group, the kinds still counted over everything firing.
    for href, kind, n, _w in chips:
        page = unescape(c.get(unescape(href)).get_data(as_text=True))
        assert page.count('class="card pack-group"') == 1, kind
        group = re.search(r'<section class="card pack-group">.*?</section>', page, re.S).group(0)
        assert f"<h2>{kind}</h2>" in group and f">{n} firing<" in group
        nav = re.search(r'<nav class="alert-kinds".*?</nav>', page, re.S).group(0)
        on = re.findall(r'<a class="kind-chip on" href="[^"]+" data-kind="([^"]+)" '
                        r'aria-current="true">', nav)
        assert on == [kind], (kind, on)
        assert len(re.findall(r'data-kind="', nav)) == 3 and ">Every kind</a>" in nav
        assert f"{n} of 900 firing shown" in nav
        # The list redraws itself with its filter.
        assert re.search(r'id="alert-evidence" hx-get="[^"]*kind=', page)
    # The filter by text inside a kind, and a kind nothing fires of.
    # The IP SLA kind's devices are d541 to d810: "d60" matches d600 to d609 among them.
    page = unescape(c.get("/v2/monitoring/alerts?kind=IP+SLA+probe+failing&q=d60")
                    .get_data(as_text=True))
    assert 'name="kind" value="IP SLA probe failing"' in page
    group = re.search(r'<section class="card pack-group">.*?</section>', page, re.S).group(0)
    assert "<h2>IP SLA probe failing</h2>" in group and ">10 firing<" in group
    assert "10 of 900 firing match “d60” of the kind “IP SLA probe failing”" in page
    page = unescape(c.get("/v2/monitoring/alerts?kind=Nothing+like+it").get_data(as_text=True))
    assert "data-kind-none" in page and 'class="card pack-group"' not in page


def test_the_tab_counts_kinds_in_one_pass_over_the_stores(pack_lab, monkeypatch):  # noqa: F811
    """No per-alert read: the kinds come from the cards the tab already built."""
    from modules import reader_job
    _store("grafana-alerts", _fleet(), at="2026-10-15T08:24:00Z")
    reads = []
    real = reader_job.read_cached
    monkeypatch.setattr(reader_job, "read_cached", lambda n: reads.append(n) or real(n))
    got = EP.tab("", "IP SLA probe failing")
    assert [k["count"] for k in got["kinds"]] == [n for _k, n in KINDS]
    assert got["counts"]["shown"] == 270 and len(got["groups"]) == 1
    assert len(reads) == len(set(reads)) <= 2, reads


# ── every citation chip names a piece on its page ─────────────────────────────────────────

def chips_without_target(html: str) -> list:
    """The citation chips (`a.cite-chip`) whose href names no element of *html*."""
    ids = set(re.findall(r'\sid="([^"]+)"', html))
    chips = re.findall(r'<a class="[^"]*\bcite-chip\b[^"]*" href="#([^"]+)"', html)
    return [c for c in chips if c not in ids]


def test_every_citation_chip_drawn_opens_a_piece_on_the_same_page(world):  # noqa: F811
    drawn = 0
    for answer in (_three(world.pack), _no_fault(world.pack, needs_human=True),
                   _no_fault(world.pack)):
        _press(world, answer, again=True)
        html = _pack_page(world)
        chips = re.findall(r'<a class="[^"]*\bcite-chip\b', html)
        assert chips, answer["outcome"]
        drawn += len(chips)
        assert chips_without_target(html) == [], answer["outcome"]
    assert drawn >= 6


def test_a_chip_with_no_piece_is_found():
    html = ('<li id="ep-1-logs:1">x</li><a class="pack-ref cite-chip" href="#ep-1-logs:1">'
            '<a class="pack-ref cite-chip" href="#ep-1-logs:9">')
    assert chips_without_target(html) == ["ep-1-logs:9"]


def _duk(body):
    import dukpy
    with open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8") as fh:
        script = fh.read()
    return json.loads(dukpy.evaljs("var window = {};\n" + script + "\n" + body))


#: A stand-in page: the pack card open, a section collapsed holding a piece, another piece
#: highlighted before.
FAKE_DOC = """
var doc = {els: {}, focused: null, scrolled: null,
  getElementById: function (i) { return this.els[i] || null; },
  querySelectorAll: function (sel) { var out = [];
    for (var k in this.els) if (this.els[k].cls['cite-hit']) out.push(this.els[k]);
    return out; }};
function El(tag, id, parent) { var s = this; this.tagName = tag; this.id = id;
  this.parentNode = parent; this.open = false; this.cls = {}; this.attrs = {};
  this.classList = {add: function (c) { s.cls[c] = 1; }, remove: function (c) { delete s.cls[c]; }};
  this.getAttribute = function (k) { return s.attrs[k] || null; };
  this.setAttribute = function (k, v) { s.attrs[k] = v; };
  this.focus = function () { doc.focused = s.id; };
  this.scrollIntoView = function () { doc.scrolled = s.id; };
  doc.els[id] = this; }
var card = new El('DETAILS', 'card', doc); card.open = true;
var sec = new El('DETAILS', 'ep-1-logs', card);
var piece = new El('LI', 'ep-1-logs:3', sec);
var other = new El('LI', 'ep-1-alert', card); other.cls['cite-hit'] = 1;
function state() { return {card: card.open, sec: sec.open, hit: !!piece.cls['cite-hit'],
  other: !!other.cls['cite-hit'], focus: doc.focused, scrolled: doc.scrolled,
  tabindex: piece.getAttribute('tabindex')}; }
"""


def test_a_chip_opens_its_section_scrolls_highlights_and_focuses_its_piece():
    got = _duk(FAKE_DOC + "var ok = window.NMAS_V2.jumpToCite(doc, 'ep-1-logs:3');"
                          "JSON.stringify({ok: ok, s: state()});")
    assert got == {"ok": True, "s": {"card": True, "sec": True, "hit": True, "other": False,
                                     "focus": "ep-1-logs:3", "scrolled": "ep-1-logs:3",
                                     "tabindex": "-1"}}
    # A chip naming nothing on the page changes nothing.
    got = _duk(FAKE_DOC + "var ok = window.NMAS_V2.jumpToCite(doc, 'ep-1-logs:9');"
                          "JSON.stringify({ok: ok, s: state()});")
    assert got == {"ok": False, "s": {"card": True, "sec": False, "hit": False, "other": True,
                                      "focus": None, "scrolled": None, "tabindex": None}}


def test_a_chip_s_target_is_its_own_fragment_only():
    got = _duk("JSON.stringify(['#ep-1-logs:3', '#ep-1-logs%3A3', '#', '', null,"
               " 'https://example.com/#x', '/v2/help#beta'].map(window.NMAS_V2.citeTarget));")
    assert got == ["ep-1-logs:3", "ep-1-logs:3", "", "", "", "", ""]


# ── nothing that has stopped firing is red; no alert ends "resolved" ──────────────────────

#: An alert's state as a badge draws it: the words a badge carries for one.
STATE_WORDS = re.compile(r"^(?:\d+ )?(?:firing|fired|cleared|resolved|ended|pending)\b")
#: The badges that are not an alert's state: a pack's integrity.
NOT_A_STATE = ("changed since built", "its hash does not match")


def red_past_firings(html: str, firing_now: bool) -> list:
    """The red badges (`badge-danger`) naming an alert's state that is not firing now: in a
    view of what fires now (*firing_now*), any red state badge outside the firing groups'
    heads; anywhere else (History, an earlier pack, a pack's other alerts), every red state
    badge. A pack's integrity badge is not a state."""
    if firing_now:
        heads = re.findall(r'<div class="card-head"><h2>[^<]*</h2>(<span class="badge '
                           r'badge-danger">\d+ firing</span>)</div>', html)
        for h in heads:
            html = html.replace(h, "", 1)
    out = []
    for words in re.findall(r'<span class="badge badge-danger"[^>]*>([^<]*)</span>', html):
        if words.startswith(NOT_A_STATE):
            continue
        if STATE_WORDS.match(words.strip()):
            out.append(words)
    return out


def _with_concurrent(pack):
    """*pack* with its other alerts in every state they are stored in at the alert's time."""
    p = copy.deepcopy(pack)
    sec = next(s for s in p["sections"] if s["name"] == "concurrent")
    sec["state"] = "ok"
    sec["pieces"] = [{"ref": f"concurrent:{i}", "rule": "Device unreachable (SNMP)",
                      "device": "r2", "state": st, "started_at": "2026-10-15T08:00:00Z",
                      "fired_at": "2026-10-15T08:01:00Z",
                      "resolved_at": "2026-10-15T08:09:00Z" if st == "resolved" else ""}
                     for i, st in enumerate(("firing", "pending", "resolved"))]
    p["resolved_at"] = "2026-10-15T08:30:00Z"
    p["trigger"] = ("built from the alert history by operator@example.com at 2026-10-15T08:40:00Z"
                    ": r1 fired at 2026-10-15T08:10:00Z, resolved at 2026-10-15T08:30:00Z; "
                    "nothing was captured when it fired")
    return p


def _pack_html(pack):
    """The pack drawn as its route draws it, as served (entities kept: stored text holding
    markup stays text)."""
    from flask import render_template

    from app import app
    with app.test_request_context("/"):
        return render_template(
            "v2/_evidence_pack.html", pack=pack, state="ok", error="", pid=pack["id"],
            intact=True, explain_model="m", explained=None, schema_now=EP.SCHEMA,
            successor=None, rebuild=None, sdn={},
            section_counts={s["ref"]: EP.section_count(s) for s in pack["sections"]})


def _views(lab):
    """Every view on Monitoring › Alerts that draws an alert's state, as (name, html as served,
    whether it is the view of what fires now)."""
    c = lab["client"]
    _with_packs(lab)
    firing = c.get("/v2/monitoring/alerts").get_data(as_text=True)
    assert "2 firing</strong>" in firing and "Earlier · 1 pack" in firing
    earlier = firing[firing.index('<details class="evidence" data-keep="earlier-packs">'):]
    now = firing[:firing.index('<details class="evidence" data-keep="earlier-packs">')]
    out = [("firing", now, True), ("earlier packs", earlier, False)]
    for p in EP.read()["rows"]:
        out.append((f"pack {p['id']}", c.get(f"/v2/monitoring/alerts/pack/{p['id']}")
                    .get_data(as_text=True), False))
    out.append(("a pack's other alerts", _pack_html(_with_concurrent(EP.read()["rows"][0])),
                False))
    return out


def test_nothing_that_has_stopped_firing_is_red(history):  # noqa: F811
    views = _views(history)
    others = views[-1][1]
    for show in ("fired", "all"):
        page = history["client"].get(f"/v2/monitoring/alerts/history?range=all"
                                     f"&show={show}").get_data(as_text=True)
        views.append((f"history, {show}", page[page.index('id="alert-history"'):], False))
    # The floor: the view of what fires now draws red, every past firing is drawn somewhere.
    assert re.search(r'badge-danger">2 firing<|badge-danger">1 firing<', views[0][1])
    fired = views[-2][1]
    assert "fired and cleared" in fired and re.search(r'badge-muted">\d+ cleared<', fired)
    assert re.search(r'badge-muted">cleared</span> at the alert', others)
    assert re.search(r'badge-warn">firing</span> at the alert', others)
    for name, html, now in views:
        assert red_past_firings(html, now) == [], name


def test_a_red_past_firing_is_found():
    planted = ('<div class="card-head"><h2>X</h2><span class="badge badge-danger">3 firing</span>'
               '</div><span class="badge badge-danger">3 cleared</span>'
               '<span class="badge badge-danger">changed since built</span>')
    assert red_past_firings(planted, True) == ["3 cleared"]
    assert red_past_firings('<span class="badge badge-danger">firing</span>', False) == ["firing"]


def drawn_words(html: str) -> str:
    """What a page as served draws in words: its text and its hovers, without the stored data
    it shows as text (`pack-text`, a log line or label value as kept; `alert-labels`, an
    alert's labels as Grafana holds them: the test pack's planted description says "resolved"
    on purpose), scripts and styles."""
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S)
    html = re.sub(r'<span class="[^"]*\bpack-text\b[^"]*">[^<]*</span>', " ", html)
    html = re.sub(r'<span class="[^"]*\balert-labels\b[^"]*"[^>]*>[^<]*</span>', " ", html)
    hovers = " ".join(re.findall(r'\btitle="([^"]*)"', html))
    return unescape(re.sub(r"<[^>]+>", " ", html) + " " + hovers)


def test_no_alert_s_end_is_drawn_as_resolved(history):  # noqa: F811
    views = _views(history)
    for url in ("/v2/monitoring/alerts/history?range=all&show=all",
                "/v2/monitoring/alerts/history?range=all&show=fired"):
        views.append((url, history["client"].get(url).get_data(as_text=True), False))
    joined = " ".join(drawn_words(h) for _n, h, _f in views)
    # The floor: the ends are drawn, as cleared.
    assert "fired and cleared" in joined and "cleared at 2026-10-15T08:30:00Z" in joined
    assert re.search(r"\bCleared\b", joined) and re.search(r"\bcleared\b", joined)
    for name, html, _f in views:
        # An alert's end in words: "resolved", or "its resolve" as a noun ("resolves an
        # alert's device", a lookup, is another sense).
        found = re.findall(r".{0,60}(?:\bresolved\b|\bresolve not\b|\bits resolve\b).{0,30}",
                           drawn_words(html), re.I)
        assert found == [], (name, found)
    planted = drawn_words('<p title="cleared">x</p><span class="badge">3 resolved</span>')
    assert re.search(r"\bresolved\b", planted), "the scan reads a badge's words"


# ── Explain again, busy on itself ─────────────────────────────────────────────────────────

def test_explain_again_is_a_secondary_button_busy_on_itself(world):  # noqa: F811
    html = _press(world, _three(world.pack))
    form = re.search(r'<form class="explain-ask explain-again"[^>]*>.*?</form>', html, re.S)
    assert form, html
    head = re.search(r'<form[^>]*>', form.group(0)).group(0)
    assert f'hx-post="/v2/monitoring/alerts/pack/{world.pack["id"]}/explain' in head
    assert f'hx-target="#explain-block-{world.pack["id"]}" hx-swap="outerHTML"' in head
    button = re.search(r'<button type="submit"[^>]*>.*?</button>', form.group(0), re.S).group(0)
    assert 'class="btn btn-small btn-outline"' in button and 'hx-disabled-elt="this"' in button
    assert '<span class="op-idle">Explain again</span>' in button
    assert '<span class="op-busy">Explaining again…</span>' in button
    assert '<input type="hidden" name="again" value="1">' in form.group(0)
    assert "A new call, up to $" in form.group(0) and "this answer stays" in form.group(0)
    # Inside the card, at its foot, after Was this right?.
    card = re.search(r'<article class="answer-card".*?</article>', html, re.S).group(0)
    assert card.index("Was this right?") < card.index('class="explain-ask explain-again"') \
        > card.index('<footer class="answer-foot">')
