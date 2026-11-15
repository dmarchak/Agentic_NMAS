"""The incident page leads with its bottom line (MERCURY_CHARTER, "Two standing rules", R2; the
operator's design change of 2026-11-14): three plain lines at the top (what happened, its
impact, the one next action), then ONE card where What to do and AI troubleshooting were two,
and everything else collapsed below. `templates/v2/_fixit_section.html` draws both from the
section model (`modules/fixit/section.py`), `templates/v2/incident.html` hands it the
incident's own Needs attention action, and `modules/incident_page.page` composes the top for a
section model that carries none yet (`incident_page.composed`).

Through the real app on tests/test_fixit_section_v2.py's lab: r2's real configuration on a box,
a self-healing incident opened by the incidents store's own writer from two lost-stream alerts
(101 and 102), each attempt a real Re-subscribe run whose verify reads no data: the shape of
r7's incident hi-22cfdc299000 (Mercury's fix, a re-subscribe, tried and failed, recorded
before the AI started by itself), "the legacy incident" below. The section model's new fields
(``bluf``, ``status``, ``proposal`` with its steps, ``actions``, ``other_actions``,
``holds``, ``cap``) are the backend's contract; until its model draws them they are planted
over the real model's answer (`contract`), the rest of the page as the real model draws it.
No device, no network, no AI call.

- **The three lines lead the page:** the BLUF is the page's first card under its header, its
  lines in order, the one card next, and every other part of the page collapsed.
- **The legacy incident's one Start button:** with Mercury's fix failed and nothing else
  offered, the page's one primary is Start AI troubleshooting, posting its route.
- **Nothing that failed is the next action:** a Re-subscribe that failed here is in Attempts
  and Other actions only, whether the model said so (the contract) or the page composed it
  (the item's own Re-subscribe dropped); with nothing tried it IS the action (the control).
- **A hold is one plain line**, never red and never "failed".
- **Approve, Modify… and Deny…** are drawn for the AI's plan and post their routes (Approve
  by the plan's hash; Modify's and Deny's words in their modals); each busy on itself, each
  with How does this work?.
- **A refused preflight step** is drawn refused with why, and Approve is not offered.
- **Cancel and Retry with more information are gone**, in every state.
- **Needs attention's row about an incident** leads with the BLUF's what, impact and fix.
- **In a real browser at 1280 and 390 px** (headless Firefox, unconfined): the BLUF is at the
  top, the Start button inside the first screen, nothing scrolls sideways.
"""
import re
from html import unescape

import pytest

from modules.fixit import section as S
from tests import test_fixit_section_v2 as FX
from tests.test_fixit_section_v2 import web  # noqa: F401  (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401  (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

NET = FX.NET
WHAT = "r2 stopped sending telemetry at 09:30"
IMPACT = "Mercury can't see r2's interfaces or CPU; traffic is unaffected"
HOLD = ("Self-healing won't write to r2 until its saved config matches intent (2 lines "
        "differ). This doesn't block the fix below.")
FAILED_OP = "Re-subscribe r2's telemetry (101, 102)"
KINDS = ("approve", "modify", "deny", "ask_again", "start", "hand_over")


def href(iid, what):
    return f"/v2/incident/{iid}/fixit/{what}?list={NET}"


def plan(iid, refused=""):
    """The AI's plan as the contract draws it: two steps, the second refused at its preflight
    when *refused* says why."""
    return {"hash": "a" * 64, "approvable": not refused,
            "found": "the collector holds a stale half-open session for r2",
            "why_refused": f"step 2 was refused at its preflight: {refused}" if refused else "",
            "steps": [
                {"n": 1, "operation": "telemetry-collector-close",
                 "words": "Close the collector's stale session for r2", "params": "subs: 101, 102",
                 "hash": "b" * 64, "preflight": {"ok": True, "refused": ""}},
                {"n": 2, "operation": "telemetry-readd-receiver",
                 "words": "Re-add r2's receiver for 102", "params": "sub: 102", "hash": "c" * 64,
                 "preflight": {"ok": not refused, "refused": refused}}]}


def contract(iid, fix="start", proposal=None, offered=(), status="", **more):
    """The section model's new fields for incident *iid* (the backend's contract): the BLUF
    with *fix* its kind, the actions in *offered* offered (each posting its own route), the
    failed re-subscribe among Other actions and one hold."""
    actions = {k: {"offered": k in offered, "href": href(iid, k.replace("hand_over", "handover")),
                   "refused": ""} for k in KINDS}
    actions["hand_over"]["offered"] = True
    return dict({
        "bluf": {"what": WHAT, "impact": IMPACT, "fix": {"kind": fix, "label": ""}},
        "status": status or "Mercury's fix failed once. The AI has not been asked yet.",
        "proposal": proposal, "actions": actions,
        "other_actions": [{"key": "resubscribe", "label": FAILED_OP,
                           "words": "failed in attempt 1: the stream did not come back"}],
        "holds": [HOLD], "cap": {"state": "ok", "which": "", "words": ""}}, **more)


def planted(monkeypatch, iid, **kw):
    """The real section model's answer with the contract's fields over it."""
    real = S.view

    def view(*a, **k):
        return dict(real(*a, **k), **contract(iid, **kw))
    monkeypatch.setattr(S, "view", view)


def text_of(html):
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def outside_modals(html):
    return re.sub(r"<dialog\b.*?</dialog>", "", html, flags=re.S)


def primaries(html):
    """Every primary control in *html* outside its modals: ``(tag, attributes, words)``, the
    words of a busy-on-itself button its idle words."""
    html = re.sub(r'<span class="op-busy">.*?</span>', "", outside_modals(html), flags=re.S)
    return [(t, unescape(a), text_of(w)) for t, a, w in re.findall(
        r'<(a|button|summary)\b([^>]*\bbtn-primary\b[^>]*)>(.*?)</\1>', html, re.S)]


def press_of(html, words):
    """The press whose idle words are *words* in *html*: ``{"post", "target", "include",
    "busy", "fields"}``, the hidden fields its `.bluf-form` carries by name, or the test fails."""
    for m in re.finditer(r'<span class="bluf-form">(.*?)</span>\s*(?=<span class="bluf-form">|'
                         r'<span class="op-act"><button type="button" class="bluf-link|</div>)',
                         html, re.S):
        part = m.group(1)
        b = re.search(r'<button\b([^>]*)><span class="op-idle">([^<]*)</span>'
                      r'<span class="op-busy">([^<]*)</span>', part)
        if b and unescape(b.group(2)) == words:
            fields = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)">',
                                     part))
            return {"post": attr(b.group(1), "hx-post"), "target": attr(b.group(1), "hx-target"),
                    "include": attr(b.group(1), "hx-include"), "busy": b.group(3),
                    "disabled": attr(b.group(1), "hx-disabled-elt"), "fields": fields}
    raise AssertionError(f"no press {words!r} is drawn")


def bluf(html):
    return html.split('id="inc-bluf"', 1)[1].split("</section>", 1)[0]


def card(html):
    return html.split('id="inc-ai"', 1)[1].split("</section>", 1)[0]


def lines_of(html):
    """The BLUF's lines: ``[(its name, its words)]``, in order."""
    return [(n, text_of(w)) for n, w in re.findall(
        r'<div class="bluf-line" data-bluf="(\w+)"><dt>[^<]*</dt><dd>(.*?)</dd></div>',
        bluf(html), re.S)]


def legacy(web):  # noqa: F811
    """The legacy incident: Mercury's re-subscribe tried in it and failed (attempt 1)."""
    iid = FX.plant()
    FX.attempt(web)
    return iid


def body_of(web, iid):  # noqa: F811
    """The incident's page, held each time to the page's first property: a read, leaving
    every file of the store as it was (tests/test_incident_page.py's `read`)."""
    from tests import test_incident_page as TP

    before = TP.stores()
    r, html = FX.page(web, iid)
    assert r.status_code == 200, html
    assert TP.stores() == before, "drawing the incident's page wrote nothing"
    return html


def modal(html, mid):
    m = re.search(rf'<dialog class="modal" id="{re.escape(mid)}"[^>]*>(.*?)</dialog>', html,
                  re.S)
    assert m, f"no modal {mid} is drawn"
    return m.group(1)


def attr(attrs, name):
    m = re.search(rf'\b{name}="([^"]*)"', attrs)
    return unescape(m.group(1)) if m else None


# ── The three lines lead the page ──────────────────────────────────────────────────────────

class TestTheThreeLines:
    def test_they_lead_the_page_and_everything_else_is_collapsed(self, web, monkeypatch):  # noqa: F811
        iid = legacy(web)
        planted(monkeypatch, iid)
        html = body_of(web, iid)
        live = html.split('id="incident-live"', 1)[1]
        assert [n for n, _w in lines_of(html)] == ["what", "impact", "fix"]
        said = dict(lines_of(html))
        assert said["what"] == WHAT and said["impact"] == IMPACT
        # The order: the header (title and state), the BLUF, the one card, then the rest.
        order = [live.index(m) for m in ('class="card inc-head', 'id="inc-bluf"', 'id="inc-ai"',
                                         'id="inc-timings"', 'id="inc-wrong"', 'id="inc-done"',
                                         'class="card tl-record-d')]
        assert order == sorted(order), order
        rest = live.split('id="inc-timings"', 1)[0].rsplit("<details", 1)[1]
        assert " open" not in rest.split(">", 1)[0], "Timings is collapsed"
        for sid in ("inc-wrong", "inc-done"):
            sec = live.split(f'id="{sid}"', 1)[1].split("</section>", 1)[0]
            tag = re.search(r"<details\b[^>]*>", sec).group(0)
            assert " open" not in tag, f"{sid} is collapsed"
        # The header's times are no longer above the BLUF.
        head = live.split('class="card inc-head', 1)[1].split("</section>", 1)[0]
        assert 'data-cell="ttr"' not in head and "inc-times" not in head
        # Inside the card, everything past the status line is collapsed.
        c = card(html)
        for more in ("attempts", "other", "holds", "costs"):
            m = re.search(rf'<details class="fixit-more"[^>]*data-more="{more}"[^>]*>', c)
            assert m and " open" not in m.group(0), more

    def test_the_legacy_incident_s_one_button_is_start_ai_troubleshooting(self, web,  # noqa: F811
                                                                         monkeypatch):
        iid = legacy(web)
        planted(monkeypatch, iid, offered=("start",))
        html = body_of(web, iid)
        (only,) = primaries(html.split('id="incident-live"', 1)[1])
        assert only[2] == "Start AI troubleshooting", only
        form = press_of(bluf(html), "Start AI troubleshooting")
        assert form["post"] == href(iid, "start") and form["target"] == "#inc-fixit"
        assert form["include"] == "closest .bluf-form" and form["busy"]
        assert 'data-fix="start"' in bluf(html)

    def test_a_section_with_no_bluf_of_its_own_is_composed_by_the_page(self, web,  # noqa: F811
                                                                       monkeypatch):
        """A section that draws no BLUF (the device has no identity, so no troubleshooting
        record: the section's state "none"): the page composes the top from what it holds
        (`incident_page.composed`): what happened (the page's title where no item's lead is
        held), the impact said as not known, and the item's own action, the page's one
        primary."""
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path=None: [dict(FX.DEV)])
        iid = FX.plant()
        html = body_of(web, iid)
        assert 'data-state="none"' in html
        said = dict(lines_of(html))
        title = text_of(html.split("<h1", 1)[1].split(">", 1)[1].split("</h1>", 1)[0])
        assert said["what"] and said["what"] in title, (said, title)
        assert said["impact"].startswith("Not known"), said
        (only,) = primaries(html.split('id="incident-live"', 1)[1])
        assert only[2] == "Open r2" and 'data-fix="item"' in bluf(html), only


# ── Nothing that failed is the next action ─────────────────────────────────────────────────

def resubscribe_item(monkeypatch):
    """The incident's Needs attention item offering Re-subscribe, as a lost stream's does."""
    from modules import incident_page as IP

    row = {"action": {"label": "re-subscribe r2's telemetry (101, 102)", "open": "resubscribe",
                      "device": "r2", "subs": ["101", "102"], "list": NET},
           "networks": {"r2": [NET]}, "devices": ["r2"]}
    monkeypatch.setattr(IP, "item_of", lambda *a, **k: {"state": "stands", "first": "resubscribe",
                                                       "level": "danger", "row": dict(row)})


class TestNothingThatFailedIsOffered:
    def test_it_is_in_attempts_and_other_actions_only(self, web, monkeypatch):  # noqa: F811
        iid = legacy(web)
        planted(monkeypatch, iid, offered=("start",))
        html = body_of(web, iid)
        assert "Re-subscribe" not in bluf(html)
        c = card(html)
        attempts = c.split('data-more="attempts"', 1)[1].split("</details>", 1)[0]
        other = c.split('data-more="other"', 1)[1].split("</details>", 1)[0]
        assert "Re-subscribe r2&#39;s telemetry (101, 102)" in attempts
        assert "<strong>failed:</strong>" in attempts and "Open the run" in attempts
        assert FAILED_OP in text_of(other) and "failed in attempt 1" in text_of(other)
        assert "Re-subscribe" not in text_of(c.split('<details class="fixit-more"', 1)[0])

    def test_the_item_s_own_re_subscribe_is_dropped_once_it_failed_here(self, web,  # noqa: F811
                                                                         monkeypatch):
        """The section names nothing to press (its fix "none"), so the page offers the item's
        own action (`incident_page.with_item`), but never a Re-subscribe that failed here."""
        resubscribe_item(monkeypatch)
        iid = legacy(web)
        planted(monkeypatch, iid, fix="none")
        html = body_of(web, iid)
        assert "Re-subscribe r2" not in bluf(html), "a failed fix offered again"
        assert 'data-first="resubscribe"' not in html

    def test_with_nothing_tried_the_item_s_re_subscribe_is_the_action(self, web, monkeypatch):  # noqa: F811
        """The control: the same item and the same section, nothing tried, and its Re-subscribe
        IS the next action, so the test above can fail."""
        resubscribe_item(monkeypatch)
        iid = FX.plant()
        planted(monkeypatch, iid, fix="none")
        html = body_of(web, iid)
        (only,) = primaries(bluf(html))
        assert only[0] == "summary" and only[2].startswith("Re-subscribe r2's telemetry"), only


# ── A hold is one plain line ───────────────────────────────────────────────────────────────

class TestAHoldIsAPlainLine:
    def test_drawn_once_in_holds_never_red_never_failed(self, web, monkeypatch):  # noqa: F811
        iid = legacy(web)
        planted(monkeypatch, iid)
        html = body_of(web, iid)
        holds = card(html).split('data-more="holds"', 1)[1].split("</details>", 1)[0]
        (li,) = re.findall(r"<li\b([^>]*)>(.*?)</li>", holds, re.S)
        assert text_of(li[1]) == HOLD
        assert attr(li[0], "class") == "fixit-hold"
        assert not re.search(r"danger|warn|fail|refused", li[0]), li[0]
        assert text_of(html).count("Self-healing won't write to r2") == 1, "said once"
        assert "Find approved state failed" not in html
        with open("static/css/nmas-v2.css", encoding="utf-8") as fh:
            css = fh.read()
        rule = re.search(r"\.fixit-hold\s*\{([^}]*)\}", css)
        assert rule and "danger" not in rule.group(1) and "warn" not in rule.group(1), rule


# ── Approve, Modify… and Deny… ─────────────────────────────────────────────────────────────

class TestTheProposal:
    def test_approve_modify_and_deny_are_drawn_and_post_their_routes(self, web, monkeypatch):  # noqa: F811
        iid = legacy(web)
        planted(monkeypatch, iid, fix="approve", proposal=plan(iid),
                offered=("approve", "modify", "deny"))
        html = body_of(web, iid)
        b = bluf(html)
        (only,) = primaries(html.split('id="incident-live"', 1)[1])
        assert only[2] == "Approve", only
        approve = press_of(b, "Approve")
        assert approve["post"] == href(iid, "approve") and approve["target"] == "#inc-fixit"
        assert approve["fields"]["hash"] == "a" * 64, "Approve is by the plan's hash"
        assert approve["busy"] == "Approving…" and approve["disabled"] == "this"
        for kind, words, field in (("modify", "Modify…", "text"), ("deny", "Deny…", "reason")):
            (opener,) = re.findall(rf'<button\b([^>]*data-modal-open="fixit-{kind}-{iid}"[^>]*)>'
                                   rf'{words}</button>', b)
            assert attr(opener, "aria-haspopup") == "dialog" and "hx-post" not in opener
            body = modal(html, f"fixit-{kind}-{iid}")
            form = re.search(r'<form class="fixit-form" hx-post="([^"]+)" hx-target="#inc-fixit"',
                             body)
            assert form and unescape(form.group(1)) == href(iid, kind), kind
            area = re.search(rf'<textarea\b[^>]*name="{field}"[^>]*>', body)
            assert area, f"{kind}'s box"
            assert (" required" in area.group(0)) == (kind == "modify"), "Deny's reason is optional"
            assert 'name="hash" value="' + "a" * 64 in body
            assert '<span class="op-busy">' in body and 'hx-disabled-elt="this"' in body
        # Each action carries How does this work?, to its own section.
        for section in ("approve", "modify", "deny", "hand-over"):
            assert f'data-manual="fixit-troubleshoot#{section}"' in html, section
        # The plan's steps, each with its preflight; its hash is the record's, not the card's.
        c = card(html)
        steps = re.findall(r'<li class="fixit-step fixit-step-(\w+)" data-step="(\d)"', c)
        assert steps == [("ok", "1"), ("ok", "2")]
        assert text_of(c).count("preflight passed") == 2
        assert "a" * 64 not in text_of(c)
        record = html.split('class="card tl-record-d', 1)[1]
        assert "The plan's hash" in record and "a" * 64 in record
        # Pressed with what it carries: the record holds no such plan (it is planted on the
        # page alone), so the press is refused, drawn under the buttons in place, and nothing
        # is recorded or started.
        from modules.fixit import incident as F
        r = web.post(href(iid, "approve"), data=approve["fields"], headers=FX.HX)
        out = r.get_data(as_text=True)
        assert r.status_code >= 400 and 'id="inc-fixit"' in out, out[:300]
        answer = bluf(out).split('class="bluf-answer"', 1)[1]
        assert "Not done:" in text_of(answer), text_of(answer)[:300]
        assert not [ln for ln in F.read(FX.incident(iid))["lines"]
                    if ln.get("choice") == "approve"]
        assert sum(web.started.values()) == 0, "a refused Approve starts nothing"

    def test_a_refused_preflight_step_is_drawn_and_approve_is_absent(self, web, monkeypatch):  # noqa: F811
        iid = legacy(web)
        why = "r2's intent has no telemetry receiver for 102"
        planted(monkeypatch, iid, fix="approve", proposal=plan(iid, refused=why),
                offered=("modify", "deny"))
        html = body_of(web, iid)
        c = card(html)
        (step,) = re.findall(r'<li class="fixit-step fixit-step-refused" data-step="2".*?</li>',
                             c, re.S)
        assert f"refused at its preflight: {why}" in text_of(step).replace("&#39;", "'")
        assert "/fixit/approve" not in html and ">Approve<" not in html
        assert "Approve isn't offered" in text_of(bluf(html))
        assert f"fixit-modify-{iid}" in bluf(html) and f"fixit-deny-{iid}" in bluf(html)
        assert primaries(html.split('id="incident-live"', 1)[1]) == [], \
            "no primary while nothing can be approved"

    def test_after_a_deny_ask_the_ai_again_and_hand_over(self, web, monkeypatch):  # noqa: F811
        iid = legacy(web)
        planted(monkeypatch, iid, fix="none", offered=("ask_again",),
                status="You denied the AI's plan. Nothing ran.")
        html = body_of(web, iid)
        (only,) = primaries(html.split('id="incident-live"', 1)[1])
        assert only[2] == "Ask the AI again", only
        assert href(iid, "ask_again") in unescape(bluf(html))
        assert "Hand over…" in bluf(html) and "bluf-link" in bluf(html)


# ── Cancel and Retry with more information are gone ────────────────────────────────────────

GONE = ("/fixit/cancel", "/fixit/retry", "Retry with more information", "Cancel troubleshooting",
        "Keep troubleshooting", 'class="fixit-choices"')


class TestCancelAndRetryAreGone:
    def test_in_every_state(self, web, monkeypatch, tmp_path):  # noqa: F811
        iid = FX.plant()
        for when in ("nothing tried", "stopped", "proposed"):
            if when == "stopped":
                FX.attempt(web)
            if when == "proposed":
                FX.diagnosed(iid, tmp_path)
                FX.replan(iid)
            html = body_of(web, iid)
            assert [g for g in GONE if g in html] == [], when
        planted(monkeypatch, iid, fix="approve", proposal=plan(iid),
                offered=("approve", "modify", "deny"))
        html = body_of(web, iid)
        assert [g for g in GONE if g in html] == []


# ── Needs attention's row about an incident ────────────────────────────────────────────────

class TestTheRowLeadsWithTheBluf:
    def test_what_impact_and_fix_before_the_rest(self, web, monkeypatch):  # noqa: F811
        """A row about an incident carrying the BLUF (`row.bluf`, the backend's: the same three
        lines as the incident's page) leads its opened body with them, after Open the incident,
        in place of its own cause."""
        from modules import attention

        iid = FX.plant()
        row = {"id": "planted-incident-row", "level": "danger", "what": "r2's telemetry is lost",
               "cause": "the row's own cause, which the BLUF replaces", "source": "heal",
               "incident_page": {"id": iid, "list": NET},
               "bluf": {"what": WHAT, "impact": IMPACT,
                        "fix": {"kind": "start", "label": "Start AI troubleshooting",
                                "href": f"/v2/incident/{iid}?list={NET}#inc-bluf"}},
               "action": {"label": "open the incident", "href": f"/v2/incident/{iid}"},
               "devices": ["r2"], "networks": {"r2": [NET]}}
        real = attention.needs_attention

        def needs(*a, **k):
            got = real(*a, **k)
            return dict(got, rows=[row] + list(got.get("rows") or []))
        monkeypatch.setattr(attention, "needs_attention", needs)
        from modules import attention_store
        attention_store.clear()
        from tests import test_incident_page as TP
        before = TP.stores()
        html = web.get(f"/v2/attention?list={NET}").get_data(as_text=True)
        assert TP.stores() == before, "drawing Needs attention wrote nothing"
        mine = html.split('data-attention-row="planted-incident-row"', 1)
        assert len(mine) == 2, "the planted row is drawn"
        body = mine[1].split('<div class="att-body">', 1)[1].split('<div class="att-todo">', 1)[0]
        said = text_of(body)
        assert said.startswith("Open the incident"), said
        lead = said.split("Open the incident", 1)[1].strip()
        assert lead.startswith(f"What happened {WHAT} Impact {IMPACT} How to fix it"), lead
        assert "the row's own cause" not in said
        link = re.search(r'<a class="att-bluf-fix"[^>]* href="([^"]+)"',
                         body)
        assert link and unescape(link.group(1)).endswith("#inc-bluf")


# ── In a real browser ──────────────────────────────────────────────────────────────────────

#: Where the BLUF, the Start button and the one card are, and whether the page scrolls
#: sideways.
WHERE = """
var r = function (s) { var e = document.querySelector(s); if (!e) return null;
  var q = e.getBoundingClientRect(); return [q.left, q.top, q.right, q.bottom]; };
return {bluf: r('#inc-bluf'), card: r('#inc-ai'), timings: r('#inc-timings'),
        start: r('#inc-bluf .btn-primary'), vh: window.innerHeight,
        vw: document.documentElement.clientWidth,
        wide: document.documentElement.scrollWidth <= document.documentElement.clientWidth};
"""


class TestInARealBrowser:
    @pytest.mark.parametrize("width", [1280, 390])
    def test_the_bluf_is_at_the_top_and_its_button_on_the_first_screen(self, web, monkeypatch,  # noqa: F811
                                                                       width):
        from tests import browser
        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the page's own checks above still run")
        import app as APP
        iid = legacy(web)
        planted(monkeypatch, iid, offered=("start",))
        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": width, "height": 900})
                b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
                b.wait_for("return !!document.querySelector('#inc-bluf .btn-primary')")
                w = b.js(WHERE)
                # Hand over…, the secondary link beside it, opens its modal over the page.
                b.click("#inc-bluf .bluf-link")
                opened = b.wait_for(f"return document.getElementById('fixit-hand-{iid}').open")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        assert w["bluf"][1] < w["card"][1] < w["timings"][1], w
        assert w["start"][3] <= w["vh"], f"the one button is below the first screen: {w}"
        assert w["bluf"][2] <= w["vw"] + 1 and w["wide"], f"the page scrolls sideways: {w}"
        assert opened, "Hand over… opens its modal"
